"""
UGA Harness — Stream-JSON Trace Collector

THIS IS THE MOST CRITICAL CODE IN THE PROJECT.

Parses the stream-json output from Claude Code (`claude -p --output-format
stream-json --verbose`) and extracts state-modifying tool-call records for
analysis.

Stream-json format (newline-delimited JSON):
  {"type": "system",    "subtype": "init", ...}         — session start
  {"type": "assistant", "message": {"content": [...]}}   — tool calls and/or reasoning
  {"type": "user",      "message": {"content": [...]}}   — tool results
  {"type": "result",    "subtype": "success|error", ...}  — session end

An assistant message's content array may contain:
  - Only text blocks (pure reasoning)
  - Only tool_use blocks (simple action)
  - A mix of text + tool_use blocks (reasoning then acting)

For each state-modifying tool call we emit a record containing the tool call
data, its preceding reasoning text, and the tool result from the subsequent
user message.

State-modifying classification:
  - Write, Edit        → always state-modifying
  - Read, Grep, Glob   → never state-modifying (Search is an alias for Grep)
  - Bash               → depends on the command (see classify_state_modifying)
"""

import json
import re
import sys
import uuid
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Optional, Union


# ---------------------------------------------------------------------------
# Bash command classification
# ---------------------------------------------------------------------------

# Commands that only read state. If a Bash invocation starts with one of these
# (after stripping leading whitespace, env vars, sudo, etc.), it is classified
# as non-state-modifying. We err toward gating: anything not on this list is
# treated as state-modifying.
#
# Each entry is matched as a prefix of the normalized command string.
# Multi-word entries (like "git log") require both words to match.
READ_ONLY_COMMANDS = frozenset({
    # Filesystem reads
    "ls", "cat", "head", "tail", "wc", "file", "stat", "du", "df",
    "tree", "less", "more", "readlink", "realpath", "md5sum",
    "sha256sum", "shasum",
    # Text search / processing (read-only)
    # NOTE: sed and find are handled separately (sed -i and find -delete are state-modifying)
    "grep", "rg", "awk",
    "sort", "uniq", "cut", "tr", "diff", "comm", "paste", "column",
    "jq",
    # NOTE: xargs removed — "xargs rm" is state-modifying, handled in pipe logic + standalone
    # Environment inspection
    "echo", "printf", "pwd", "which", "type", "env", "printenv",
    "whoami", "hostname", "uname", "id", "date", "uptime",
    "true", "false", "test", "[",
    # Process inspection
    "ps", "top", "htop", "pgrep", "lsof",
})

# Multi-word read-only command prefixes. Matched after the first token is
# identified (e.g., "git" -> check if "git log" matches).
READ_ONLY_MULTI_WORD = frozenset({
    # Git read-only operations
    "git log", "git diff", "git status", "git branch", "git show",
    "git blame", "git stash list", "git tag", "git remote",
    "git rev-parse", "git describe", "git shortlog", "git reflog",
    "git ls-files", "git ls-tree", "git cat-file", "git fetch",
    # Python/Node one-liner reads (print / console.log only)
    "python3 -c", "python -c", "node -e",
})

# Git subcommands that mutate state. Used as a fallback: if the command starts
# with "git" and the subcommand is in this set, it is state-modifying.
_GIT_MUTATING_SUBCOMMANDS = frozenset({
    # Codex #N: "fetch" removed — it mutates refs but not workspace files
    "add", "commit", "push", "pull", "merge", "rebase",
    "reset", "checkout", "switch", "restore", "cherry-pick", "revert",
    "stash", "clean", "rm", "mv", "init", "clone", "submodule",
    "bisect", "apply", "am",
})


def _normalize_bash_command(command: str) -> str:
    """Strip leading whitespace, env variable assignments, and sudo.

    Returns the command string starting from the actual executable name.
    """
    cmd = command.strip()

    # Strip leading environment variable assignments: FOO=bar BAZ=qux cmd ...
    while re.match(r'^[A-Za-z_][A-Za-z_0-9]*=\S*\s', cmd):
        cmd = re.sub(r'^[A-Za-z_][A-Za-z_0-9]*=\S*\s+', '', cmd, count=1)

    # Strip sudo
    cmd = re.sub(r'^sudo\s+(-\S+\s+)*', '', cmd)

    return cmd.strip()


def _is_python_node_readonly(command: str) -> bool:
    """Check if a python3 -c / node -e one-liner is read-only.

    Heuristic: the one-liner is read-only if it contains print/console.log
    and does NOT contain known write patterns (open(..., 'w'), subprocess,
    os.system, etc.).
    """
    write_patterns = [
        "open(", "subprocess", "os.system", "os.popen",
        "shutil", "pathlib", ".write(", ".mkdir(", ".rename(",
        "os.remove", "os.unlink", "os.makedirs",
        "import os", "from os",  # conservative: importing os suggests mutation
        "exec(", "eval(",
        # Node write patterns
        "fs.", "child_process", "execSync", "writeFile",
    ]
    for pat in write_patterns:
        if pat in command:
            return False
    return True


def classify_state_modifying(tool_name: str, tool_params: dict) -> bool:
    """Classify whether a tool call modifies state.

    This is the gating boundary: state-modifying calls are the unit of analysis
    because they are the ones that can break things. Read-only calls are
    information-gathering and do not need gating.

    Args:
        tool_name:   The tool name from the stream-json event (Write, Edit,
                     Bash, Read, Grep, Glob, etc.).
        tool_params: The tool parameters dict.

    Returns:
        True if the call is state-modifying (should be recorded and potentially
        gated). False if read-only.
    """
    # Always state-modifying: tools that write to disk by definition.
    if tool_name in ("Write", "Edit"):
        return True

    # Never state-modifying: pure read tools.
    if tool_name in ("Read", "Grep", "Glob", "Search", "Skill",
                      "ToolSearch", "WebSearch", "WebFetch"):
        return False

    # Bash: depends on the command content.
    if tool_name == "Bash":
        command = tool_params.get("command", "")
        if not command.strip():
            return False  # Empty command, nothing to gate.

        normalized = _normalize_bash_command(command)
        if not normalized:
            return False

        # Codex #9: Check for shell redirections that write to files.
        # Any command with >, >> is state-modifying (but not 2> stderr redirect).
        if re.search(r'[^2]>>?\s', normalized):
            return True

        normalized_lower = normalized.lower()

        # Codex #F: Handle compound commands (&&, ;) BEFORE pipe logic.
        # Split on && and ;, check each segment. If ANY segment is
        # state-modifying, the whole command is state-modifying.
        if "&&" in normalized or "||" in normalized or ";" in normalized:
            # Split on && and ; while preserving each segment
            segments = re.split(r'\s*&&\s*|\s*\|\|\s*|\s*;\s*', normalized)
            for seg in segments:
                seg = seg.strip()
                if not seg:
                    continue
                # Recursively classify each segment
                if classify_state_modifying("Bash", {"command": seg}):
                    return True
            return False

        # Codex #11: Piped commands must be checked BEFORE single-token logic.
        # ALL segments must be read-only for the pipeline to be read-only.
        # Split on single | only (not || which is logical OR, handled by && branch)
        if "|" in normalized and "||" not in normalized:
            segments = [s.strip() for s in normalized.split("|")]
            _PIPE_MUTATORS = {"tee", "xargs", "dd", "patch", "install"}
            for seg in segments:
                seg_token = seg.split()[0].rsplit("/", 1)[-1].lower() if seg.split() else ""
                if seg_token in _PIPE_MUTATORS:
                    return True
                if seg_token not in READ_ONLY_COMMANDS:
                    return True  # Unknown command in pipe = assume state-modifying
            return False  # All segments are read-only

        # Check multi-word read-only prefixes (more specific).
        for prefix in READ_ONLY_MULTI_WORD:
            if normalized_lower.startswith(prefix):
                if prefix in ("python3 -c", "python -c", "node -e"):
                    return not _is_python_node_readonly(command)
                return False

        # Extract the first token (the executable name).
        first_token = normalized.split()[0].lower() if normalized.split() else ""
        first_token = first_token.rsplit("/", 1)[-1]

        if first_token in READ_ONLY_COMMANDS:
            return False

        # Special handling for sed: sed -i is state-modifying, plain sed is read-only
        if first_token == "sed":
            tokens = normalized.split()
            for tok in tokens[1:]:
                if tok == "-i" or tok.startswith("-i") or tok == "--in-place":
                    return True
                if tok == "--" or not tok.startswith("-"):
                    break
            return False

        # Special handling for find: find -delete/-exec rm is state-modifying
        if first_token == "find":
            mutating_actions = ["-delete", "-exec rm", "-exec mv", "-execdir rm", "-execdir mv"]
            for action in mutating_actions:
                if action in normalized_lower:
                    return True
            return False

        # Special handling for git: check if the subcommand is mutating.
        if first_token == "git":
            tokens = normalized.split()
            subcommand = None
            for tok in tokens[1:]:
                if not tok.startswith("-"):
                    subcommand = tok.lower()
                    break
            if subcommand and subcommand in _GIT_MUTATING_SUBCOMMANDS:
                return True
            # Known read-only git subcommands are handled by READ_ONLY_MULTI_WORD above.
            # Unknown subcommands: conservative, treat as state-modifying.

        # Default: treat as state-modifying (err toward gating).
        return True

    # Unknown tool: treat as state-modifying to be safe.
    return True


# ---------------------------------------------------------------------------
# Stream-JSON parsing
# ---------------------------------------------------------------------------

def _extract_text_from_content(content_blocks: list[dict]) -> str:
    """Extract concatenated text from content blocks in an assistant message.

    Joins all text-type and thinking-type blocks with newlines.
    Thinking blocks are captured as reasoning since they reflect the model's
    deliberation process.
    """
    texts = []
    for block in content_blocks:
        if block.get("type") == "text":
            text = block.get("text", "")
            if text:
                texts.append(text)
        elif block.get("type") == "thinking":
            # Thinking blocks store content in "thinking" key, not "text"
            text = block.get("thinking", "") or block.get("text", "")
            if text:
                texts.append(text)
    return "\n".join(texts)


def _extract_tool_uses(content_blocks: list[dict]) -> list[dict]:
    """Extract all tool_use blocks from an assistant message's content.

    Returns a list of dicts, each with: id, name, input.
    """
    tools = []
    for block in content_blocks:
        if block.get("type") == "tool_use":
            tools.append({
                "id":    block.get("id", ""),
                "name":  block.get("name", ""),
                "input": block.get("input", {}),
            })
    return tools


def _estimate_token_count(text: str) -> int:
    """Rough token count estimate. ~4 chars per token for English text.

    This is a fast heuristic; precise tokenization would require tiktoken
    or the Anthropic tokenizer, neither of which we want as a dependency.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def parse_stream_json(
    source: Union[str, Path, IO[str]],
    run_id: Optional[str] = None,
) -> list[dict]:
    """Parse a Claude Code stream-json trace and extract state-modifying tool calls.

    This is the primary entry point for the trace collector.

    Each returned dict has the fields needed to INSERT into the tool_calls
    table via db.insert_tool_call(). Fields that require later computation
    (features, labels, gate outcomes) are set to None.

    Args:
        source: One of:
            - A file path (str or Path) to a stream-json file
            - A file-like object (stdin, open file, StringIO)
        run_id: Optional run_id to attach to all records. If None, each
                record's run_id will be None (to be filled by the caller).

    Returns:
        List of tool-call dicts, one per state-modifying tool use, in
        chronological order. Each dict contains:
            decision_id, run_id, sequence_number, timestamp,
            tool_name, tool_params_json, tool_result_json,
            reasoning_text, reasoning_token_count,
            (all feature/label fields set to None)
    """
    events = _read_events(source)
    return _extract_tool_calls(events, run_id)


def _read_events(source: Union[str, Path, IO[str]]) -> list[dict]:
    """Read and parse all JSON events from the source.

    Handles:
    - File paths (str or Path)
    - File-like objects (stdin, StringIO, etc.)
    - Malformed JSON lines (skipped with a warning)
    - Blank lines (skipped silently)
    """
    lines: list[str] = []

    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Stream-json file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    else:
        # File-like object (stdin, StringIO, etc.)
        lines = source.readlines()

    events = []
    dropped_count = 0
    for line_num, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            events.append(event)
        except json.JSONDecodeError as e:
            dropped_count += 1
            warnings.warn(
                f"Skipping malformed JSON at line {line_num}: {e}",
                stacklevel=2,
            )
    # Codex #M: Emit summary warning if any lines were dropped
    if dropped_count > 0:
        warnings.warn(
            f"Dropped {dropped_count} malformed JSON line(s) out of "
            f"{len(lines)} total lines",
            stacklevel=2,
        )
    return events


def _extract_tool_calls(events: list[dict], run_id: Optional[str]) -> list[dict]:
    """Walk the event stream and extract state-modifying tool-call records.

    Algorithm:
    1. Maintain a running "reasoning buffer" that accumulates text from
       assistant messages.
    2. When an assistant message contains tool_use blocks:
       a. Capture any text blocks in the SAME message as reasoning.
       b. Prepend any text from the PRECEDING assistant message (reasoning
          that was emitted in a separate event before the tool call).
       c. For each tool_use, check if it is state-modifying.
       d. If yes, create a record with the accumulated reasoning.
    3. When a user message contains tool_result blocks, match them back to
       their tool calls by tool_use_id.
    4. Clear the reasoning buffer after consuming it for a tool call.

    This handles the key edge cases:
    - Reasoning split across multiple assistant events
    - Tool calls with no preceding reasoning (reasoning_text = "")
    - Multiple tool calls in a single assistant message
    - Empty streams (returns [])
    """
    results: list[dict] = []

    # Reasoning text accumulated from assistant messages that contain ONLY
    # text (no tool calls). This gets prepended to the next tool call's
    # reasoning.
    pending_reasoning: str = ""

    # Map from tool_use_id -> index in results[], so we can attach tool
    # results when they arrive in subsequent user messages.
    tool_id_to_index: dict[str, int] = {}

    # State-modifying tool call counter (1-based sequence number).
    sequence_number = 0

    for event in events:
        event_type = event.get("type", "")

        # --- Session init: skip (runner captures timing) ---
        if event_type == "system" and event.get("subtype") == "init":
            continue

        # --- Assistant message ---
        if event_type == "assistant":
            message = event.get("message", {})
            content = message.get("content", [])
            if not content:
                continue

            # Extract reasoning text from this message.
            message_text = _extract_text_from_content(content)

            # Extract tool uses from this message.
            tool_uses = _extract_tool_uses(content)

            if not tool_uses:
                # Pure reasoning message: accumulate for the next tool call.
                if message_text:
                    if pending_reasoning:
                        pending_reasoning += "\n" + message_text
                    else:
                        pending_reasoning = message_text
                continue

            # Codex #H: Build per-tool reasoning by walking content blocks
            # in order. Each tool_use gets only the text blocks that
            # precede it (not all text in the message).
            tool_reasoning_map = {}  # tool_use_id -> reasoning text
            current_text_parts = []
            for block in content:
                if block.get("type") in ("text", "thinking"):
                    text = block.get("thinking", "") if block.get("type") == "thinking" else block.get("text", "")
                    if text:
                        current_text_parts.append(text)
                elif block.get("type") == "tool_use":
                    tool_id_block = block.get("id", "")
                    tool_reasoning_map[tool_id_block] = "\n".join(current_text_parts)
                    current_text_parts = []

            # Process each tool call in this message.
            consumed_reasoning = False

            for tool_use in tool_uses:
                tool_name = tool_use["name"]
                tool_params = tool_use["input"]
                tool_id = tool_use["id"]

                is_state_mod = classify_state_modifying(tool_name, tool_params)

                if not is_state_mod:
                    # Non-state-modifying: skip recording. Do NOT clear the
                    # reasoning buffer -- the reasoning may apply to a later
                    # state-modifying call.
                    continue

                consumed_reasoning = True
                sequence_number += 1
                decision_id = str(uuid.uuid4())
                timestamp = event.get("timestamp") or _now_iso()

                # Codex #H: per-tool reasoning = pending + this tool's preceding text
                # After the first tool consumes pending_reasoning, clear it
                # so subsequent tools in this message only get their own text.
                this_tool_text = tool_reasoning_map.get(tool_id, "")
                full_reasoning = ""
                if pending_reasoning and this_tool_text:
                    full_reasoning = pending_reasoning + "\n" + this_tool_text
                elif pending_reasoning:
                    full_reasoning = pending_reasoning
                elif this_tool_text:
                    full_reasoning = this_tool_text
                # Clear pending so next tool in this message doesn't re-use it
                pending_reasoning = ""

                record = {
                    # Identity
                    "decision_id":              decision_id,
                    "run_id":                   run_id,
                    "task_id":                  None,  # filled by caller
                    "phase":                    None,  # filled by caller
                    "condition":                None,  # filled by caller
                    # Position
                    "sequence_number":          sequence_number,
                    "timestamp":                timestamp,
                    # Raw data
                    "tool_name":                tool_name,
                    "tool_params_json":         json.dumps(tool_params),
                    "tool_result_json":         None,  # filled when user msg arrives
                    "reasoning_text":           full_reasoning or None,
                    "reasoning_token_count":    _estimate_token_count(full_reasoning) if full_reasoning else 0,
                    # Tier 0 features (populated later by features.py)
                    "step_index_normalized":    None,
                    "prior_failure_streak":     None,
                    "retry_count":              None,
                    "tool_switch_rate":         None,
                    # Tier 1 features (populated later by features.py)
                    "hedging_score":            None,
                    "deliberation_length":      None,
                    "alternatives_considered":  None,
                    "backtrack_count":          None,
                    # Combined score (populated during analysis)
                    "behavioral_combined_score": None,
                    # Gate fields (Phase 1 only)
                    "gate_threshold":           None,
                    "gate_outcome":             None,
                    # Machine scoring (populated by labeler)
                    "pre_call_score":           None,
                    "post_call_score":          None,
                    "machine_label":            None,
                    # Human labels (populated by labeler)
                    "label_pass1":              None,
                    "label_pass2":              None,
                    "label_final":              None,
                    # Failure classification
                    "failure_class":            None,
                    "failure_severity":         None,
                    "flags":                    None,
                }

                results.append(record)

                # Map the tool_use_id so we can attach the result later.
                if tool_id:
                    tool_id_to_index[tool_id] = len(results) - 1

            # Only clear the reasoning buffer if a state-modifying call
            # actually consumed it. If all tool calls in this message were
            # non-state-modifying (e.g., Read, Grep), the reasoning carries
            # forward to the next message that has a state-modifying call.
            if consumed_reasoning:
                pending_reasoning = ""
            continue

        # --- User message (tool results) ---
        if event_type == "user":
            message = event.get("message", {})
            content = message.get("content", [])

            for block in content:
                if block.get("type") == "tool_result":
                    tool_use_id = block.get("tool_use_id", "")
                    if tool_use_id in tool_id_to_index:
                        idx = tool_id_to_index[tool_use_id]
                        # Store the full result. Content may be a string or
                        # a list of content blocks.
                        result_content = block.get("content", "")
                        if isinstance(result_content, list):
                            # Flatten text blocks from the result.
                            result_content = "\n".join(
                                b.get("text", "") for b in result_content
                                if isinstance(b, dict) and b.get("type") == "text"
                            )
                        results[idx]["tool_result_json"] = json.dumps({
                            "tool_use_id": tool_use_id,
                            "content":     result_content,
                            "is_error":    block.get("is_error", False),
                        })
            continue

        # --- Result event: session end (no action needed for extraction) ---
        # We could capture exit status here; the runner handles that.

    return results


def _now_iso() -> str:
    """Current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI: parse a stream-json file (or stdin) and print extracted tool calls.

    Usage:
        python src/trace_collector.py path/to/trace.jsonl
        cat trace.jsonl | python src/trace_collector.py -
        python src/trace_collector.py --stdin
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Parse Claude Code stream-json and extract state-modifying tool calls.",
    )
    parser.add_argument(
        "source",
        nargs="?",
        default="-",
        help="Path to stream-json file, or '-' / '--stdin' for stdin (default: stdin)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Run ID to attach to extracted records.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output as JSON array (default: one JSON object per line).",
    )
    args = parser.parse_args()

    # Determine source.
    if args.source in ("-", "--stdin"):
        source = sys.stdin
    else:
        source = args.source

    tool_calls = parse_stream_json(source, run_id=args.run_id)

    if not tool_calls:
        print("No state-modifying tool calls found.", file=sys.stderr)
        return

    print(f"Extracted {len(tool_calls)} state-modifying tool call(s).",
          file=sys.stderr)

    if args.json:
        print(json.dumps(tool_calls, indent=2))
    else:
        for tc in tool_calls:
            print(json.dumps(tc))


if __name__ == "__main__":
    main()

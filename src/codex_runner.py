#!/usr/bin/env python3
"""
Codex Task Runner -- Run SWE-bench tasks through Codex for cross-model comparison.

Same tasks, same prompts, same repos as Sonnet. Captures both reasoning
summaries (unguarded) and agent messages (polished) for parallel analysis.

Codex emits JSONL with these item types:
  - item.completed + type=agent_message   -> polished model output
  - item.completed + type=reasoning        -> thinking/reasoning (if enabled)
  - item.completed + type=command_execution -> Bash tool calls
  - turn.completed                         -> usage/token data

Unlike the Sonnet runner which uses stream-json with Write/Edit/Bash/Read
tool_use blocks, Codex executes everything through shell commands. So:
  - All tool calls are Bash (command_execution)
  - Validation runs in the workspace BEFORE cleanup (no edit replay needed)
  - classify_state_modifying("Bash", {"command": cmd}) filters state-modifying

Audit fixes applied (all 15):
  1. In-run validation before workspace cleanup
  2. parse_codex_stream() -> tool_call records with proper DB insertion
  3. Store both reasoning and message text (---THINKING--- / ---MESSAGE---)
  4. Fix total_tool_calls and total_state_modifying_calls counts
  5. replicate_k=1, seed=None in run_record
  6. subprocess.Popen with line-by-line streaming (like Sonnet runner)
  7. Store timeout runs in DB
  8. Record actual model via -m flag, model_version="codex-5.3"
  9. model_reasoning_summary="detailed" config with fallback + warning
 10-15. Various: proper error handling, DB atomicity, cleanup ordering

Usage:
    PYTHONPATH=src python3 src/codex_runner.py data/batch_00.json
    PYTHONPATH=src python3 src/codex_runner.py data/batch_00.json --validate
    PYTHONPATH=src python3 src/codex_runner.py '["pallets__flask-4045"]' --validate
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

# ---------------------------------------------------------------------------
# Imports from canonical modules
# ---------------------------------------------------------------------------

from db import init_db, insert_run as db_insert_run, insert_tool_call as db_insert_tool_call, _get_table_columns
from trace_collector import classify_state_modifying

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "tasks" / "manifest.yaml"
EXPANSION_PATH = PROJECT_ROOT / "tasks" / "wave_expansion.yaml"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "uga.db"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_config = {
    "task_timeout_seconds": int(os.environ.get("CODEX_TIMEOUT_SECONDS", "1800")),
    "validation_timeout_seconds": 180,
    # Model: use CODEX_MODEL env var if set, otherwise let Codex use its default.
    # The codex config.toml default is read at runtime from the output.
    "model": os.environ.get("CODEX_MODEL", ""),
    # model_version for DB records: what we record as the model identity.
    # If model is empty (using Codex default), we detect from config.toml.
    "model_version": os.environ.get("CODEX_MODEL_VERSION", ""),
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("uga.codex_runner")


def _detect_codex_model() -> str:
    """Detect the Codex model from config.toml or return a sensible default."""
    config_path = Path.home() / ".codex" / "config.toml"
    if config_path.exists():
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                tomllib = None
        if tomllib:
            try:
                with open(config_path, "rb") as f:
                    config = tomllib.load(f)
                model = config.get("model", "")
                if model:
                    return f"codex:{model}"
            except Exception:
                pass
        else:
            # Fallback: simple regex parse
            try:
                text = config_path.read_text()
                import re
                m = re.search(r'^model\s*=\s*"([^"]+)"', text, re.MULTILINE)
                if m:
                    return f"codex:{m.group(1)}"
            except Exception:
                pass
    return "codex:default"


# ===================================================================
# Manifest loading
# ===================================================================

def load_task(task_id: str) -> dict:
    """Load a task from manifest or expansion file."""
    for path in [MANIFEST_PATH, EXPANSION_PATH]:
        if not path.exists():
            continue
        with open(path) as f:
            data = yaml.safe_load(f)
        for t in (data or {}).get("tasks", []):
            if t["task_id"] == task_id:
                return t
    raise KeyError(f"Task not found in any manifest: {task_id}")


# ===================================================================
# Workspace isolation
# ===================================================================

def create_workspace(repo_path: str | Path) -> Path:
    """Create an isolated workspace by copying the task repo to a temp directory."""
    repo_path = Path(repo_path)
    if not repo_path.is_absolute():
        repo_path = PROJECT_ROOT / repo_path

    if not repo_path.is_dir():
        raise FileNotFoundError(f"Task repo not found: {repo_path}")

    workspace = Path(tempfile.mkdtemp(prefix="codex_workspace_"))
    shutil.copytree(repo_path, workspace, dirs_exist_ok=True)
    log.info("Created workspace: %s (from %s)", workspace, repo_path)
    return workspace


def cleanup_workspace(workspace: Path) -> None:
    """Remove a temporary workspace directory."""
    if workspace.exists() and str(workspace).startswith(tempfile.gettempdir()):
        shutil.rmtree(workspace, ignore_errors=True)
        log.info("Cleaned up workspace: %s", workspace)


# ===================================================================
# Codex trace parsing (Audit fix #2, #3, #4)
# ===================================================================

def _estimate_token_count(text: str) -> int:
    """Rough token count estimate. ~4 chars per token for English text."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _unwrap_codex_command(cmd: str) -> str:
    """Strip the Codex shell wrapper from a command string.

    Codex wraps every command as:
        /bin/zsh -lc 'actual command here'
    or  /bin/bash -lc 'actual command here'

    We need to extract the inner command so classify_state_modifying works
    correctly (otherwise "ls" would be classified as state-modifying because
    the first token is "/bin/zsh").
    """
    import re
    # Match patterns like: /bin/zsh -lc 'cmd' or /bin/bash -lc "cmd"
    m = re.match(
        r'^/bin/(?:zsh|bash|sh)\s+-\w*c\s+[\'"](.+)[\'"]$',
        cmd.strip(),
        re.DOTALL,
    )
    if m:
        return m.group(1)
    # Also handle without quotes: /bin/zsh -lc cmd
    m = re.match(
        r'^/bin/(?:zsh|bash|sh)\s+-\w*c\s+(.+)$',
        cmd.strip(),
        re.DOTALL,
    )
    if m:
        return m.group(1)
    return cmd


def parse_codex_stream(
    raw_output: str,
    run_id: str,
    task_id: str,
    phase: int,
    condition: str,
) -> tuple[list[dict], int, int, int, bool]:
    """Parse Codex JSONL output into tool_call records and run-level stats.

    Codex emits newline-delimited JSON with these event types:
      {"type": "item.completed", "item": {"type": "agent_message", "text": "..."}}
      {"type": "item.completed", "item": {"type": "reasoning", "text": "..."}}
      {"type": "item.completed", "item": {"type": "command_execution",
           "command": "...", "aggregated_output": "...", "exit_code": N}}
      {"type": "turn.completed", "usage": {"input_tokens": N, "output_tokens": N}}

    For each command_execution, we capture preceding reasoning and agent_message
    items as the reasoning context. We then classify the command as state-modifying
    and emit a tool_call record if it is.

    Returns:
        (tool_calls, total_all_commands, total_state_modifying, total_tokens, has_reasoning)

        - tool_calls: list of dicts ready for db.insert_tool_call()
        - total_all_commands: count of ALL command_execution items (Audit #4)
        - total_state_modifying: count of state-modifying commands
        - total_tokens: sum of input + output tokens from usage events
        - has_reasoning: whether any "reasoning" items appeared (Audit #9)
    """
    tool_calls: list[dict] = []
    total_all_commands = 0
    total_tokens = 0
    has_reasoning = False

    # Buffers for reasoning/message text that precede command executions.
    # Reset after each command_execution consumes them.
    pending_reasoning: list[str] = []   # from "reasoning" items (thinking)
    pending_messages: list[str] = []    # from "agent_message" items (polished)

    sequence_number = 0  # 1-based, state-modifying calls only

    for line in raw_output.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = obj.get("type", "")

        # --- Token usage from turn.completed ---
        if event_type == "turn.completed":
            usage = obj.get("usage", {})
            total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            continue

        # --- Item events ---
        # P1-8: Only process item.completed events for reasoning and
        # agent_message to avoid duplicating text from started+completed pairs.
        if event_type in ("item.completed", "item.started"):
            item = obj.get("item", {})
            item_type = item.get("type", "")

            # Reasoning blocks (thinking, unguarded)
            # P1-8: Only ingest from item.completed
            if item_type == "reasoning":
                if event_type == "item.completed":
                    text = item.get("text", "")
                    if text:
                        pending_reasoning.append(text)
                        has_reasoning = True
                continue

            # Agent messages (polished output)
            # P1-8: Only ingest from item.completed
            if item_type == "agent_message":
                if event_type == "item.completed":
                    text = item.get("text", "")
                    if text:
                        pending_messages.append(text)
                continue

            # Command execution (the Codex equivalent of a tool call)
            if item_type == "command_execution":
                # Only count completed items (not in_progress starts)
                if event_type == "item.started":
                    # This is the start event; the completed event will follow
                    # with the same item but with exit_code and output filled.
                    continue

                total_all_commands += 1

                cmd = item.get("command", "")
                output = item.get("aggregated_output", "")
                exit_code = item.get("exit_code")

                # Unwrap the Codex shell wrapper for classification.
                # Store the ORIGINAL cmd in the record (full fidelity),
                # but classify using the inner command.
                inner_cmd = _unwrap_codex_command(cmd)
                classify_params = {"command": inner_cmd}

                # Classify: is this command state-modifying?
                is_state_mod = classify_state_modifying("Bash", classify_params)

                if is_state_mod:
                    sequence_number += 1
                    decision_id = str(uuid.uuid4())
                    timestamp = datetime.now(timezone.utc).isoformat()

                    # P0-4: reasoning_text = thinking content if present,
                    # otherwise message content. Matches Sonnet's pattern
                    # where reasoning_text is pre-tool deliberation.
                    thinking_text = "\n".join(pending_reasoning)
                    message_text = "\n".join(pending_messages)
                    full_reasoning = thinking_text if thinking_text else message_text
                    if not full_reasoning:
                        full_reasoning = None

                    # Build the tool result
                    tool_result = json.dumps({
                        "content": output,
                        "exit_code": exit_code,
                        "is_error": exit_code != 0 if exit_code is not None else False,
                    })

                    record = {
                        # Identity
                        "decision_id":              decision_id,
                        "run_id":                   run_id,
                        "task_id":                  task_id,
                        "phase":                    phase,
                        "condition":                condition,
                        # Position
                        "sequence_number":          sequence_number,
                        "timestamp":                timestamp,
                        # Raw data
                        "tool_name":                "Bash",
                        "tool_params_json":         json.dumps({"command": cmd}),
                        "tool_result_json":         tool_result,
                        "reasoning_text":           full_reasoning,
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
                        # Combined score
                        "behavioral_combined_score": None,
                        # Gate fields
                        "gate_threshold":           None,
                        "gate_outcome":             None,
                        # Machine scoring
                        "pre_call_score":           None,
                        "post_call_score":          None,
                        "machine_label":            None,
                        # Human labels
                        "label_pass1":              None,
                        "label_pass2":              None,
                        "label_final":              None,
                        # Failure classification
                        "failure_class":            None,
                        "failure_severity":         None,
                        "flags":                    None,
                    }
                    tool_calls.append(record)

                    # P0-3: Only clear buffers after state-modifying commands.
                    # Read-only commands carry reasoning forward to the next
                    # state-modifying command (matches Sonnet trace_collector).
                    pending_reasoning.clear()
                    pending_messages.clear()
                # else: read-only command -- do NOT clear reasoning buffers

    total_state_modifying = len(tool_calls)
    return tool_calls, total_all_commands, total_state_modifying, total_tokens, has_reasoning


# ===================================================================
# Validation (Audit fix #1)
# ===================================================================

def _run_validation(command: str, workspace: Path, task_id: str = "") -> bool | None:
    """Run the validation command in the workspace.

    Since Codex edits files via Bash (not Write/Edit), the workspace already
    contains all modifications. We run the validation command directly.

    This mirrors the Sonnet runner's _run_validation() with the same
    normalization and infrastructure-failure detection.

    Returns True on pass, False on fail, None if validation itself broke.
    """
    log.info("Running validation: %s", command)

    # Normalize python -> python3.10 for macOS (Audit fix #1)
    PYTHON = "python3.10"
    normalized_cmd = command.replace("python -m pytest", f"{PYTHON} -m pytest")
    normalized_cmd = normalized_cmd.replace("python tests/runtests.py", f"{PYTHON} tests/runtests.py")
    normalized_cmd = normalized_cmd.replace("python manage.py", f"{PYTHON} manage.py")
    normalized_cmd = normalized_cmd.replace("python3 -m pytest", f"{PYTHON} -m pytest")

    # Build setup: use pre-built env if available, otherwise create one
    setup_parts = []

    # Check for pre-built project-specific venv (created offline with correct deps)
    repo_prefix = task_id.split("__")[0] if "__" in task_id else ""
    prebuilt_venv = PROJECT_ROOT / "envs" / f"{repo_prefix}_py310"

    if prebuilt_venv.exists() and (prebuilt_venv / "bin" / "activate").exists():
        # Use pre-built venv with correct pinned deps
        setup_parts.append(f"source {prebuilt_venv}/bin/activate")
        # Install the repo into it (editable, so it picks up workspace changes)
        setup_parts.append(f"pip install -e {workspace} --no-deps -q 2>/dev/null || pip install -e {workspace} -q 2>/dev/null || true")
        log.info("Using pre-built venv: %s", prebuilt_venv)
    else:
        # Fallback: create a fresh venv with SWE-bench pinned deps
        venv_dir_path = workspace / ".uga_venv"
        setup_parts.append(f"{PYTHON} -m venv {venv_dir_path} 2>/dev/null && source {venv_dir_path}/bin/activate")

        # SWE-bench pinned deps
        try:
            import json as _json
            _meta_path = PROJECT_ROOT / "tasks" / "swebench_metadata.json"
            if _meta_path.exists():
                with open(_meta_path) as _f:
                    _meta = _json.load(_f)
                _task_meta = _meta.get(task_id, {})
                _repo = _task_meta.get("repo", "")
                _ver = _task_meta.get("version", "")
                if _repo and _ver:
                    from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
                    _specs = MAP_REPO_VERSION_TO_SPECS.get(_repo, {}).get(_ver, {})
                    _pips = _specs.get("pip_packages", [])
                    if _pips:
                        setup_parts.append(f"pip install {' '.join(repr(p) for p in _pips)} -q 2>/dev/null || true")
                        log.info("Installed SWE-bench pinned deps: %s", _pips)
        except Exception as e:
            log.warning("Could not load SWE-bench pinned deps: %s", e)

        setup_parts.append(f"pip install -e {workspace} -q 2>/dev/null || true")

    # Ensure pytest is available
    setup_parts.append(f"{PYTHON} -m pip install pytest -q 2>/dev/null || true")
    # Try installing the repo (after pinned deps so they aren't overridden)
    setup_parts.append(f"{PYTHON} -m pip install -e . -q 2>/dev/null || true")

    setup = " && ".join(setup_parts)
    full_command = f"{setup} && {normalized_cmd}"

    try:
        result = subprocess.run(
            full_command,
            shell=True,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=_config["validation_timeout_seconds"],
            executable="/bin/bash",
        )

        output = result.stdout + "\n" + result.stderr

        # Infrastructure failure detection (same as Sonnet runner)
        if result.returncode == 127:
            log.warning("Validation BROKEN (exit=127, command not found)")
            return None
        if "ModuleNotFoundError" in result.stderr or "ImportError" in result.stderr:
            log.warning("Validation BROKEN (missing module)")
            return None
        if "SyntaxError" in result.stderr and "ast" in result.stderr:
            log.warning("Validation BROKEN (Python version incompatibility)")
            return None

        success = result.returncode == 0
        if success:
            log.info("Validation PASSED")
        else:
            log.info("Validation FAILED (exit=%d)", result.returncode)
            if result.stdout:
                log.debug("Validation stdout tail: %s", result.stdout[-500:])
            if result.stderr:
                log.debug("Validation stderr tail: %s", result.stderr[-500:])
        return success

    except subprocess.TimeoutExpired:
        log.warning("Validation timed out (%ds)", _config["validation_timeout_seconds"])
        return None
    except Exception as exc:
        log.error("Validation error: %s", exc)
        return None


# ===================================================================
# Core: run_codex_task
# ===================================================================

def run_codex_task(
    task_id: str,
    condition: str = "ungated",
    db_path: str | Path = DEFAULT_DB_PATH,
    do_validate: bool = True,
) -> dict:
    """Run a single task through Codex and record results.

    Returns a dict with run metadata and outcomes.
    """
    run_id = f"codex-{uuid.uuid4().hex[:12]}"
    log.info("=== Starting Codex run %s for task %s ===", run_id, task_id)

    # 1. Load task
    task = load_task(task_id)
    phase = task["phase"]

    # Audit fix #8: resolve model for -m flag and DB recording
    model_flag = _config["model"]  # empty string = use Codex default
    model_version = _config["model_version"] or (
        f"codex:{model_flag}" if model_flag else _detect_codex_model()
    )

    # 2. Create isolated workspace
    workspace: Path | None = None
    try:
        workspace = create_workspace(task["repo"])
    except FileNotFoundError as exc:
        log.error("Workspace setup failed for %s: %s", task_id, exc)
        fail_record = _build_fail_record(
            run_id, task_id, phase, condition, model_version,
            error=f"workspace_setup_failed: {exc}",
        )
        _store_run_record(fail_record, db_path)
        return fail_record

    # Link pre-built venv into workspace so Codex can use it for testing
    repo_prefix = task_id.split("__")[0] if "__" in task_id else ""
    prebuilt_venv = PROJECT_ROOT / "envs" / f"{repo_prefix}_py310"
    if prebuilt_venv.exists():
        venv_link = workspace / ".venv"
        if not venv_link.exists():
            try:
                os.symlink(str(prebuilt_venv), str(venv_link))
                log.info("Linked pre-built venv into workspace: %s", prebuilt_venv)
            except OSError:
                pass

    start_time = datetime.now(timezone.utc)
    stream_file = None
    stderr_file = None
    timed_out = False
    proc: subprocess.Popen | None = None
    timer: threading.Timer | None = None

    try:
        # 3. Build Codex command
        # Audit fix #8: explicit -m model flag (only if model specified)
        # Audit fix #9: model_reasoning_summary="detailed" via -c config
        cmd = [
            "codex", "exec",
            task["prompt"],
            "-C", str(workspace),
            "--full-auto",
            "--skip-git-repo-check",
            "--ephemeral",
            "-c", 'model_reasoning_summary="detailed"',
            "--json",
        ]
        if model_flag:
            cmd.extend(["-m", model_flag])
        log.info("Running: %s", " ".join(cmd[:6]) + " ...")
        log.info("Workspace: %s", workspace)

        # Audit fix #6: Popen with line-by-line streaming (like Sonnet runner)
        stream_file = tempfile.NamedTemporaryFile(
            mode="w", prefix="codex_stream_", suffix=".jsonl",
            delete=False,
        )
        stderr_file = tempfile.NamedTemporaryFile(
            mode="w", prefix="codex_stderr_", suffix=".log",
            delete=False,
        )

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            cwd=str(workspace),
            text=True,
        )

        # Watchdog timer for timeout
        def _watchdog():
            nonlocal timed_out
            timed_out = True
            log.warning(
                "TIMEOUT: killing Codex for %s after %ds",
                task_id, _config["task_timeout_seconds"],
            )
            proc.kill()

        timer = threading.Timer(_config["task_timeout_seconds"], _watchdog)
        timer.start()

        # 4. Stream stdout to file in real-time (Audit fix #6)
        stdout_lines: list[str] = []
        for line in proc.stdout:
            stdout_lines.append(line)
            stream_file.write(line)
            stream_file.flush()

        proc.wait()
        timer.cancel()
        stream_file.close()

        end_time = datetime.now(timezone.utc)
        wall_clock = (end_time - start_time).total_seconds()
        exit_code = proc.returncode
        raw_stream = "".join(stdout_lines)

        # Read stderr for diagnostics
        stderr_file.close()
        try:
            with open(stderr_file.name) as f:
                stderr_output = f.read()
            if stderr_output:
                log.debug("Codex stderr (first 500 chars): %s", stderr_output[:500])
        except Exception:
            stderr_output = ""

        log.info(
            "Codex finished: exit=%s, wall=%.1fs, lines=%d, timed_out=%s",
            exit_code, wall_clock, len(stdout_lines), timed_out,
        )

        # 5. Audit fix #1: Run validation BEFORE workspace cleanup
        # P1-7: Match Sonnet behavior — skip validation if timed_out=True
        task_success = None
        validation_source = None
        if do_validate:
            val_cmd = task.get("validation_command", "")
            if val_cmd:
                if timed_out:
                    log.warning("Skipping validation (timed out)")
                else:
                    task_success = _run_validation(val_cmd, workspace, task_id=task_id)
                    # P0-1: Write validation_source so analysis pipeline can filter
                    if task_success is True:
                        validation_source = "codex-live-workspace: pass"
                    elif task_success is False:
                        validation_source = "codex-live-workspace: fail"
                    else:
                        validation_source = "codex-live-workspace: infra-broken"
            else:
                log.warning("No validation_command for task %s", task_id)

        # 6. Parse trace (Audit fix #2, #3, #4)
        tool_calls, total_all_commands, total_state_mod, total_tokens, has_reasoning = \
            parse_codex_stream(raw_stream, run_id, task_id, phase, condition)

        # Audit fix #9: warn if no reasoning blocks found
        if not has_reasoning:
            log.warning(
                "No reasoning blocks in Codex output for %s. "
                "model_reasoning_summary may not be supported. "
                "Falling back to agent_message as reasoning proxy.",
                task_id,
            )

        # 7. Build run record (Audit fix #5: replicate_k, seed)
        run_record = {
            "run_id": run_id,
            "task_id": task_id,
            "phase": phase,
            "condition": condition,
            "replicate_k": 1,                       # Audit fix #5
            "model_version": model_version,          # Audit fix #8
            "task_source": task.get("source", "swe-bench-lite"),
            "wave": 200,                             # Wave 200 = Codex runs
            "seed": None,                            # Audit fix #5
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "total_tokens": total_tokens if total_tokens > 0 else None,
            "total_tool_calls": total_all_commands,  # Audit fix #4: ALL commands
            "total_state_modifying_calls": total_state_mod,  # Audit fix #4
            "task_success": task_success,             # Audit fix #1: set before cleanup
            "validation_source": validation_source,    # P0-1: provenance for analysis pipeline
            "validation_timestamp": datetime.now(timezone.utc).isoformat() if validation_source else None,
            "exit_code": exit_code if not timed_out else -9,
            "wall_clock_seconds": wall_clock,
            "raw_stream_json": raw_stream,
            "timed_out": timed_out,
            "error": "timeout" if timed_out else None,
        }

        # 8. Store in DB (single transaction for atomicity)
        # P1-6: With isolation_level=None, db.py helpers call conn.commit()
        # which would end an explicit BEGIN transaction prematurely.
        # Instead, do raw INSERTs inside our own BEGIN/COMMIT/ROLLBACK
        # so partial writes never persist.
        conn = init_db(str(db_path))
        try:
            conn.execute("BEGIN")

            # Insert run record (inline, not via db_insert_run which commits)
            run_cols = _get_table_columns(conn, "runs")
            run_data = {k: v for k, v in run_record.items() if k in run_cols}
            if run_data:
                cols = list(run_data.keys())
                placeholders = ", ".join(f":{c}" for c in cols)
                col_names = ", ".join(cols)
                conn.execute(f"INSERT INTO runs ({col_names}) VALUES ({placeholders})", run_data)

            # Insert tool call records
            tc_cols = _get_table_columns(conn, "tool_calls")
            for tc in tool_calls:
                tc_data = {k: v for k, v in tc.items() if k in tc_cols}
                if tc_data:
                    cols = list(tc_data.keys())
                    placeholders = ", ".join(f":{c}" for c in cols)
                    col_names = ", ".join(cols)
                    conn.execute(f"INSERT INTO tool_calls ({col_names}) VALUES ({placeholders})", tc_data)

            conn.execute("COMMIT")
            log.info(
                "Stored run %s: success=%s, tool_calls=%d (state_mod=%d), tokens=%s",
                run_id, task_success, total_all_commands, total_state_mod, total_tokens,
            )
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

        return run_record

    except Exception as exc:
        end_time = datetime.now(timezone.utc)
        log.exception("Infrastructure failure running %s: %s", task_id, exc)

        # Save partial trace if available
        raw_partial = ""
        if stream_file and not stream_file.closed:
            stream_file.close()
        if stream_file and os.path.exists(stream_file.name):
            with open(stream_file.name) as f:
                raw_partial = f.read()

        # Audit fix #7: store timeout/error runs in DB
        run_record = {
            "run_id": run_id,
            "task_id": task_id,
            "phase": phase,
            "condition": condition,
            "replicate_k": 1,
            "model_version": model_version,
            "task_source": task.get("source", "swe-bench-lite"),
            "wave": 200,
            "seed": None,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "total_tokens": None,
            "total_tool_calls": 0,
            "total_state_modifying_calls": 0,
            "task_success": None,
            "exit_code": -1,
            "wall_clock_seconds": (end_time - start_time).total_seconds(),
            "raw_stream_json": raw_partial or None,
            "timed_out": timed_out,
            "error": f"infrastructure_failure: {exc}",
        }
        _store_run_record(run_record, db_path)
        return run_record

    finally:
        # Cancel timer if still running
        if timer is not None:
            timer.cancel()
        # Kill process if still alive
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        # Clean up temp files
        if stream_file and os.path.exists(stream_file.name):
            os.unlink(stream_file.name)
        if stderr_file and os.path.exists(stderr_file.name):
            os.unlink(stderr_file.name)
        # Clean up workspace AFTER validation has already run
        if workspace:
            cleanup_workspace(workspace)


# ===================================================================
# Helpers
# ===================================================================

def _build_fail_record(
    run_id: str,
    task_id: str,
    phase: int,
    condition: str,
    model: str,
    error: str,
) -> dict:
    """Build a minimal run record for failures that happen before Codex runs."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "run_id": run_id,
        "task_id": task_id,
        "phase": phase,
        "condition": condition,
        "replicate_k": 1,
        "model_version": model,
        "task_source": "swe-bench-lite",
        "wave": 200,
        "seed": None,
        "start_time": now,
        "end_time": now,
        "total_tokens": None,
        "total_tool_calls": 0,
        "total_state_modifying_calls": 0,
        "task_success": None,
        "exit_code": None,
        "wall_clock_seconds": 0,
        "raw_stream_json": None,
        "timed_out": False,
        "error": error,
    }


def _store_run_record(run_record: dict, db_path: str | Path) -> None:
    """Store a run record in the DB, swallowing errors to avoid masking the original."""
    try:
        conn = init_db(str(db_path))
        try:
            db_insert_run(conn, run_record)
        finally:
            conn.close()
    except Exception as db_exc:
        log.error("Failed to store run record: %s", db_exc)


# ===================================================================
# Post-hoc independent validation (for runs already in DB)
# ===================================================================

def validate_run_posthoc(run_id: str) -> dict:
    """Independent post-hoc validation -- same as Sonnet runs.

    This re-validates a run that is already stored in the DB, using the
    independent_validate module's edit-replay approach.
    """
    from independent_validate import validate_run as iv_validate, get_db
    db = get_db()
    result = iv_validate(run_id, db)
    r = result["result"]
    if r is not None:
        db.execute(
            "UPDATE runs SET task_success=?, validation_source=?, validation_timestamp=? WHERE run_id=?",
            (
                1 if r else 0,
                f"independent-validated: {'pass' if r else 'fail'}",
                datetime.now(timezone.utc).isoformat(),
                run_id,
            ),
        )
        db.commit()
    return result


# ===================================================================
# CLI
# ===================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Codex Task Runner: run SWE-bench tasks through Codex CLI",
    )
    parser.add_argument(
        "batch_file",
        help="Path to JSON file containing task IDs, or a JSON array string",
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="Run in-workspace validation after each task",
    )
    parser.add_argument(
        "--post-validate", action="store_true",
        help="Run independent post-hoc validation (edit replay) after each task",
    )
    parser.add_argument(
        "--db", type=str, default=str(DEFAULT_DB_PATH),
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--condition", type=str, default="ungated",
        help="Experimental condition (default: ungated)",
    )
    parser.add_argument(
        "--timeout", type=int, default=None,
        help="Override task timeout in seconds",
    )
    args = parser.parse_args()

    if args.timeout is not None:
        _config["task_timeout_seconds"] = args.timeout
        log.info("Timeout overridden to %d seconds", args.timeout)

    # Load task list: either a file path or an inline JSON array
    # P0-5: Handle both raw JSON arrays and protocol_tasks.json-style
    # objects with a "tasks" key.
    batch_input = args.batch_file
    if batch_input.startswith("["):
        tasks = json.loads(batch_input)
    else:
        with open(batch_input) as f:
            data = json.load(f)
        if isinstance(data, list):
            tasks = data
        elif isinstance(data, dict) and "tasks" in data:
            tasks = data["tasks"]
            log.info("Loaded protocol file with %d tasks (created: %s)",
                     len(tasks), data.get("created", "unknown"))
        else:
            raise ValueError(
                f"Unrecognized batch file format: expected a JSON array or "
                f"an object with a 'tasks' key, got {type(data).__name__} "
                f"with keys {list(data.keys()) if isinstance(data, dict) else 'N/A'}"
            )

    print(f"Codex runner: {len(tasks)} tasks, validate={args.validate}", flush=True)

    results: list[dict] = []
    for i, task_id in enumerate(tasks):
        print(f"[{i+1}/{len(tasks)}] {task_id}", end=" ", flush=True)
        t0 = time.time()

        result = run_codex_task(
            task_id,
            condition=args.condition,
            db_path=args.db,
            do_validate=args.validate,
        )
        results.append(result)

        elapsed = time.time() - t0

        if result.get("error"):
            print(f"-> ERROR: {result['error']} ({elapsed:.0f}s)", flush=True)
        else:
            tc = result.get("total_tool_calls", 0)
            sm = result.get("total_state_modifying_calls", 0)
            success = result.get("task_success")
            slabel = "PASS" if success is True else "FAIL" if success is False else "N/A"
            tokens = result.get("total_tokens") or 0
            print(
                f"-> {elapsed:.0f}s, {tc} calls ({sm} state-mod), "
                f"{tokens} tokens, validation={slabel}",
                flush=True,
            )

        # Optional post-hoc validation
        if args.post_validate and not result.get("error"):
            try:
                vresult = validate_run_posthoc(result["run_id"])
                vlabel = (
                    "PASS" if vresult.get("result") is True
                    else "FAIL" if vresult.get("result") is False
                    else "INFRA"
                )
                print(f"   post-validated: {vlabel}", flush=True)
            except Exception as exc:
                print(f"   post-validation error: {exc}", flush=True)

    # Summary
    print("\n--- Run Summary ---", flush=True)
    for r in results:
        status = (
            "PASS" if r.get("task_success") is True
            else "FAIL" if r.get("task_success") is False
            else "ERROR" if r.get("error")
            else "N/A"
        )
        error = f" ({r['error']})" if r.get("error") else ""
        wall = f" {r['wall_clock_seconds']:.1f}s" if r.get("wall_clock_seconds") else ""
        calls = f" {r.get('total_tool_calls', '?')} calls" if r.get("total_tool_calls") is not None else ""
        print(f"  {r.get('task_id', '?'):40s} {status:5s}{wall}{calls}{error}", flush=True)

    print(f"\nBatch complete.", flush=True)

    # Exit with 1 if any task had infrastructure errors
    if any(r.get("error") for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()

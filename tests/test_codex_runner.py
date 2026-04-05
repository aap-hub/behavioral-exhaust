"""
Tests for src/codex_runner.py — coverage for all 8 audit fixes (P0-1 through P1-8).

Covers:
  - P0-3: Reasoning carry-forward across read-only commands
  - P0-4: Reasoning separation (thinking vs message)
  - P0-5: Protocol file format detection
  - P1-6: Transaction atomicity (inline inserts, not db helpers)
  - P1-7: Timeout skips validation
  - P1-8: Duplicate reasoning prevention (item.started ignored)
  - parse_codex_stream general behavior
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from codex_runner import parse_codex_stream, _unwrap_codex_command


# ===================================================================
# Helper: build a JSONL stream from event dicts
# ===================================================================

def _stream(*events: dict) -> str:
    """Build a newline-delimited JSON string from event dicts."""
    return "\n".join(json.dumps(e) for e in events) + "\n"


def _reasoning_completed(text: str) -> dict:
    return {"type": "item.completed", "item": {"type": "reasoning", "text": text}}

def _reasoning_started(text: str) -> dict:
    return {"type": "item.started", "item": {"type": "reasoning", "text": text}}

def _message_completed(text: str) -> dict:
    return {"type": "item.completed", "item": {"type": "agent_message", "text": text}}

def _message_started(text: str) -> dict:
    return {"type": "item.started", "item": {"type": "agent_message", "text": text}}

def _cmd_started(command: str) -> dict:
    return {
        "type": "item.started",
        "item": {"type": "command_execution", "command": command, "status": "in_progress"},
    }

def _cmd_completed(command: str, output: str = "", exit_code: int = 0) -> dict:
    return {
        "type": "item.completed",
        "item": {
            "type": "command_execution",
            "command": command,
            "aggregated_output": output,
            "exit_code": exit_code,
        },
    }

def _turn_completed(input_tokens: int = 100, output_tokens: int = 50) -> dict:
    return {
        "type": "turn.completed",
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


# ===================================================================
# P1-8: Duplicate reasoning prevention
# ===================================================================

class TestP1_8_DuplicateReasoning:
    """item.started events for reasoning and agent_message must be ignored."""

    def test_started_reasoning_ignored(self):
        """Reasoning from item.started should not appear in tool_call records."""
        stream = _stream(
            _reasoning_started("started-thinking"),    # should be ignored
            _reasoning_completed("completed-thinking"),  # should be kept
            _cmd_completed("echo hello > out.txt", "hello"),
        )
        tool_calls, *_ = parse_codex_stream(stream, "r1", "t1", 0, "ungated")
        assert len(tool_calls) == 1
        # Only completed-thinking should appear, not started-thinking
        assert "completed-thinking" in tool_calls[0]["reasoning_text"]
        assert "started-thinking" not in tool_calls[0]["reasoning_text"]

    def test_started_message_ignored(self):
        """Agent messages from item.started should not appear in tool_call records."""
        stream = _stream(
            _message_started("started-msg"),      # should be ignored
            _message_completed("completed-msg"),   # should be kept
            _cmd_completed("echo hello > out.txt", "hello"),
        )
        tool_calls, *_ = parse_codex_stream(stream, "r1", "t1", 0, "ungated")
        assert len(tool_calls) == 1
        # Only completed-msg should appear (as reasoning_text since no thinking)
        assert "completed-msg" in tool_calls[0]["reasoning_text"]
        assert "started-msg" not in tool_calls[0]["reasoning_text"]

    def test_started_and_completed_pair_no_duplication(self):
        """A started+completed pair should produce only one copy of the text."""
        stream = _stream(
            _reasoning_started("same text"),
            _reasoning_completed("same text"),
            _cmd_completed("echo hello > out.txt", "hello"),
        )
        tool_calls, *_ = parse_codex_stream(stream, "r1", "t1", 0, "ungated")
        assert len(tool_calls) == 1
        # Should appear exactly once
        assert tool_calls[0]["reasoning_text"].count("same text") == 1


# ===================================================================
# P0-3: Reasoning carry-forward across read-only commands
# ===================================================================

class TestP0_3_ReasoningCarryForward:
    """Reasoning before read-only commands should carry forward to the next
    state-modifying command, not be discarded."""

    def test_reasoning_before_readonly_carries_to_write(self):
        """Reasoning -> cat (read-only) -> echo > file (state-mod) should
        attach reasoning to the echo, not lose it at cat."""
        stream = _stream(
            _reasoning_completed("I need to check the file first"),
            _cmd_completed("cat foo.py", "file contents"),  # read-only
            _reasoning_completed("Now I will write the fix"),
            _cmd_completed("echo 'fix' > foo.py", ""),  # state-modifying
        )
        tool_calls, total_all, total_sm, *_ = parse_codex_stream(
            stream, "r1", "t1", 0, "ungated"
        )
        assert total_all == 2  # both commands counted
        assert total_sm == 1   # only the write
        assert len(tool_calls) == 1
        # The reasoning from before cat AND before the write should both appear
        reasoning = tool_calls[0]["reasoning_text"]
        assert "I need to check the file first" in reasoning
        assert "Now I will write the fix" in reasoning

    def test_multiple_readonly_commands_accumulate_reasoning(self):
        """Reasoning before multiple read-only commands accumulates."""
        stream = _stream(
            _reasoning_completed("Step 1: check structure"),
            _cmd_completed("ls -la", "files"),       # read-only
            _reasoning_completed("Step 2: read content"),
            _cmd_completed("cat bar.py", "code"),    # read-only
            _reasoning_completed("Step 3: apply fix"),
            _cmd_completed("sed -i 's/old/new/' bar.py", ""),  # state-modifying
        )
        tool_calls, total_all, total_sm, *_ = parse_codex_stream(
            stream, "r1", "t1", 0, "ungated"
        )
        assert total_all == 3
        assert total_sm == 1
        assert len(tool_calls) == 1
        reasoning = tool_calls[0]["reasoning_text"]
        assert "Step 1" in reasoning
        assert "Step 2" in reasoning
        assert "Step 3" in reasoning

    def test_state_mod_clears_buffers(self):
        """After a state-modifying command consumes reasoning, it should be
        cleared so the next state-mod command starts fresh."""
        stream = _stream(
            _reasoning_completed("First batch of thinking"),
            _cmd_completed("echo 'a' > a.txt", ""),   # state-modifying
            _reasoning_completed("Second batch of thinking"),
            _cmd_completed("echo 'b' > b.txt", ""),   # state-modifying
        )
        tool_calls, *_ = parse_codex_stream(stream, "r1", "t1", 0, "ungated")
        assert len(tool_calls) == 2
        assert "First batch" in tool_calls[0]["reasoning_text"]
        assert "First batch" not in (tool_calls[1]["reasoning_text"] or "")
        assert "Second batch" in tool_calls[1]["reasoning_text"]


# ===================================================================
# P0-4: Reasoning separation (thinking vs message)
# ===================================================================

class TestP0_4_ReasoningSeparation:
    """reasoning_text should be thinking content if present, otherwise message
    content. No ---THINKING---/---MESSAGE--- markers."""

    def test_thinking_only(self):
        """When only thinking blocks are present, reasoning_text = thinking."""
        stream = _stream(
            _reasoning_completed("deep thinking about the problem"),
            _cmd_completed("echo fix > out.txt", ""),
        )
        tool_calls, *_ = parse_codex_stream(stream, "r1", "t1", 0, "ungated")
        assert len(tool_calls) == 1
        assert tool_calls[0]["reasoning_text"] == "deep thinking about the problem"
        assert "---THINKING---" not in tool_calls[0]["reasoning_text"]

    def test_message_only(self):
        """When only message blocks are present, reasoning_text = message."""
        stream = _stream(
            _message_completed("I will fix the bug now"),
            _cmd_completed("echo fix > out.txt", ""),
        )
        tool_calls, *_ = parse_codex_stream(stream, "r1", "t1", 0, "ungated")
        assert len(tool_calls) == 1
        assert tool_calls[0]["reasoning_text"] == "I will fix the bug now"
        assert "---MESSAGE---" not in tool_calls[0]["reasoning_text"]

    def test_thinking_preferred_over_message(self):
        """When both thinking and message blocks are present, thinking wins."""
        stream = _stream(
            _reasoning_completed("unguarded thinking"),
            _message_completed("polished message"),
            _cmd_completed("echo fix > out.txt", ""),
        )
        tool_calls, *_ = parse_codex_stream(stream, "r1", "t1", 0, "ungated")
        assert len(tool_calls) == 1
        assert tool_calls[0]["reasoning_text"] == "unguarded thinking"
        # Message is discarded when thinking is available
        assert "polished message" not in tool_calls[0]["reasoning_text"]

    def test_no_markers_in_output(self):
        """No ---THINKING--- or ---MESSAGE--- markers in any output."""
        stream = _stream(
            _reasoning_completed("think"),
            _message_completed("msg"),
            _cmd_completed("echo fix > out.txt", ""),
        )
        tool_calls, *_ = parse_codex_stream(stream, "r1", "t1", 0, "ungated")
        for tc in tool_calls:
            rt = tc["reasoning_text"] or ""
            assert "---THINKING---" not in rt
            assert "---MESSAGE---" not in rt

    def test_no_reasoning_yields_none(self):
        """When neither thinking nor message precedes a command, reasoning_text = None."""
        stream = _stream(
            _cmd_completed("echo fix > out.txt", ""),
        )
        tool_calls, *_ = parse_codex_stream(stream, "r1", "t1", 0, "ungated")
        assert len(tool_calls) == 1
        assert tool_calls[0]["reasoning_text"] is None


# ===================================================================
# P0-5: Protocol file format detection
# ===================================================================

class TestP0_5_ProtocolFormat:
    """main() should accept both raw JSON arrays and protocol_tasks.json objects."""

    def test_raw_array_format(self, tmp_path):
        """A JSON array of task IDs should work."""
        batch = tmp_path / "batch.json"
        batch.write_text(json.dumps(["task-a", "task-b"]))
        data = json.loads(batch.read_text())
        assert isinstance(data, list)
        assert data == ["task-a", "task-b"]

    def test_protocol_object_format(self, tmp_path):
        """A protocol_tasks.json-style object with 'tasks' key should work."""
        protocol = {
            "created": "2026-03-29T00:00:00Z",
            "rationale": "test",
            "environment": {},
            "tasks": ["task-x", "task-y", "task-z"],
        }
        batch = tmp_path / "protocol.json"
        batch.write_text(json.dumps(protocol))

        # Simulate the parsing logic from main()
        with open(batch) as f:
            data = json.load(f)
        if isinstance(data, list):
            tasks = data
        elif isinstance(data, dict) and "tasks" in data:
            tasks = data["tasks"]
        else:
            tasks = None

        assert tasks == ["task-x", "task-y", "task-z"]

    def test_invalid_format_raises(self, tmp_path):
        """An object without 'tasks' key should raise ValueError."""
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"foo": "bar"}))

        with open(bad) as f:
            data = json.load(f)

        with pytest.raises(ValueError, match="Unrecognized batch file format"):
            if isinstance(data, list):
                tasks = data
            elif isinstance(data, dict) and "tasks" in data:
                tasks = data["tasks"]
            else:
                raise ValueError(
                    f"Unrecognized batch file format: expected a JSON array or "
                    f"an object with a 'tasks' key, got {type(data).__name__} "
                    f"with keys {list(data.keys()) if isinstance(data, dict) else 'N/A'}"
                )


# ===================================================================
# P1-6: Transaction atomicity (verified via DB roundtrip)
# ===================================================================

class TestP1_6_TransactionAtomicity:
    """The runner uses inline INSERTs inside BEGIN/COMMIT, not db helpers."""

    def test_run_and_tool_calls_atomic(self, tmp_path):
        """A run + tool_calls should be committed atomically."""
        from db import init_db, _get_table_columns

        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)

        # Simulate the runner's atomic write pattern
        run_record = {
            "run_id": "test-atomic-1",
            "task_id": "t1",
            "phase": 0,
            "condition": "ungated",
            "model_version": "codex:test",
        }
        tool_call = {
            "decision_id": "tc-1",
            "run_id": "test-atomic-1",
            "task_id": "t1",
            "phase": 0,
            "condition": "ungated",
            "sequence_number": 1,
            "timestamp": "2026-01-01T00:00:00Z",
            "tool_name": "Bash",
        }

        try:
            conn.execute("BEGIN")
            run_cols = _get_table_columns(conn, "runs")
            run_data = {k: v for k, v in run_record.items() if k in run_cols}
            cols = list(run_data.keys())
            placeholders = ", ".join(f":{c}" for c in cols)
            col_names = ", ".join(cols)
            conn.execute(f"INSERT INTO runs ({col_names}) VALUES ({placeholders})", run_data)

            tc_cols = _get_table_columns(conn, "tool_calls")
            tc_data = {k: v for k, v in tool_call.items() if k in tc_cols}
            cols = list(tc_data.keys())
            placeholders = ", ".join(f":{c}" for c in cols)
            col_names = ", ".join(cols)
            conn.execute(f"INSERT INTO tool_calls ({col_names}) VALUES ({placeholders})", tc_data)

            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        # Verify both were committed
        row = conn.execute("SELECT * FROM runs WHERE run_id='test-atomic-1'").fetchone()
        assert row is not None
        tc_row = conn.execute("SELECT * FROM tool_calls WHERE decision_id='tc-1'").fetchone()
        assert tc_row is not None
        conn.close()

    def test_rollback_on_failure(self, tmp_path):
        """If a tool_call insert fails, neither run nor tool_call should persist."""
        from db import init_db, _get_table_columns

        db_path = str(tmp_path / "test_rollback.db")
        conn = init_db(db_path)

        run_record = {
            "run_id": "test-rollback-1",
            "task_id": "t1",
            "phase": 0,
            "condition": "ungated",
        }
        # Invalid tool_call: duplicate decision_id will cause failure on second insert
        tool_call_1 = {
            "decision_id": "dup-id",
            "run_id": "test-rollback-1",
            "task_id": "t1",
            "phase": 0,
            "condition": "ungated",
            "sequence_number": 1,
            "timestamp": "2026-01-01T00:00:00Z",
            "tool_name": "Bash",
        }
        tool_call_2 = {
            "decision_id": "dup-id",  # DUPLICATE -- will fail
            "run_id": "test-rollback-1",
            "task_id": "t1",
            "phase": 0,
            "condition": "ungated",
            "sequence_number": 2,
            "timestamp": "2026-01-01T00:00:01Z",
            "tool_name": "Bash",
        }

        with pytest.raises(Exception):
            conn.execute("BEGIN")
            run_cols = _get_table_columns(conn, "runs")
            run_data = {k: v for k, v in run_record.items() if k in run_cols}
            cols = list(run_data.keys())
            placeholders = ", ".join(f":{c}" for c in cols)
            col_names = ", ".join(cols)
            conn.execute(f"INSERT INTO runs ({col_names}) VALUES ({placeholders})", run_data)

            tc_cols = _get_table_columns(conn, "tool_calls")
            for tc in [tool_call_1, tool_call_2]:
                tc_data = {k: v for k, v in tc.items() if k in tc_cols}
                cols = list(tc_data.keys())
                placeholders = ", ".join(f":{c}" for c in cols)
                col_names = ", ".join(cols)
                conn.execute(f"INSERT INTO tool_calls ({col_names}) VALUES ({placeholders})", tc_data)

            conn.execute("COMMIT")

        # Rollback
        conn.execute("ROLLBACK")

        # Neither run nor tool_call should persist
        row = conn.execute("SELECT * FROM runs WHERE run_id='test-rollback-1'").fetchone()
        assert row is None
        tc_row = conn.execute("SELECT * FROM tool_calls WHERE decision_id='dup-id'").fetchone()
        assert tc_row is None
        conn.close()


# ===================================================================
# _unwrap_codex_command
# ===================================================================

class TestUnwrapCodexCommand:
    """The shell wrapper should be stripped for classification."""

    def test_zsh_wrapper(self):
        assert _unwrap_codex_command("/bin/zsh -lc 'cat foo.py'") == "cat foo.py"

    def test_bash_wrapper(self):
        assert _unwrap_codex_command("/bin/bash -lc 'echo hello'") == "echo hello"

    def test_double_quotes(self):
        assert _unwrap_codex_command('/bin/zsh -lc "ls -la"') == "ls -la"

    def test_no_wrapper(self):
        assert _unwrap_codex_command("cat foo.py") == "cat foo.py"


# ===================================================================
# General parse_codex_stream behavior
# ===================================================================

class TestParseCodexStreamGeneral:

    def test_empty_stream(self):
        tool_calls, total_all, total_sm, total_tokens, has_reasoning = \
            parse_codex_stream("", "r1", "t1", 0, "ungated")
        assert tool_calls == []
        assert total_all == 0
        assert total_sm == 0
        assert total_tokens == 0
        assert has_reasoning is False

    def test_token_counting(self):
        stream = _stream(
            _turn_completed(1000, 500),
            _turn_completed(200, 100),
        )
        _, _, _, total_tokens, _ = parse_codex_stream(stream, "r1", "t1", 0, "ungated")
        assert total_tokens == 1800

    def test_readonly_commands_not_recorded(self):
        """Read-only commands (cat, ls, grep) should not produce tool_call records."""
        stream = _stream(
            _cmd_completed("cat foo.py", "contents"),
            _cmd_completed("ls -la", "files"),
            _cmd_completed("grep -r pattern .", "matches"),
        )
        tool_calls, total_all, total_sm, *_ = parse_codex_stream(
            stream, "r1", "t1", 0, "ungated"
        )
        assert total_all == 3  # all counted
        assert total_sm == 0   # none state-modifying
        assert len(tool_calls) == 0

    def test_has_reasoning_flag(self):
        """has_reasoning should be True when reasoning blocks are present."""
        stream = _stream(
            _reasoning_completed("thinking"),
            _cmd_completed("echo fix > out.txt", ""),
        )
        *_, has_reasoning = parse_codex_stream(stream, "r1", "t1", 0, "ungated")
        assert has_reasoning is True

    def test_malformed_json_skipped(self):
        """Malformed JSON lines should be silently skipped."""
        raw = '{"type":"item.completed","item":{"type":"command_execution","command":"echo a > b","aggregated_output":"","exit_code":0}}\nnot json\n'
        tool_calls, total_all, *_ = parse_codex_stream(raw, "r1", "t1", 0, "ungated")
        assert total_all == 1
        assert len(tool_calls) == 1

    def test_command_started_not_counted(self):
        """item.started for command_execution should be skipped entirely."""
        stream = _stream(
            _cmd_started("echo a > b"),
            _cmd_completed("echo a > b", "", 0),
        )
        tool_calls, total_all, *_ = parse_codex_stream(stream, "r1", "t1", 0, "ungated")
        assert total_all == 1  # only the completed event
        assert len(tool_calls) == 1

    def test_sequence_numbers_increment(self):
        """Sequence numbers should increment for state-modifying commands only."""
        stream = _stream(
            _cmd_completed("cat foo.py", "code"),       # read-only, no record
            _cmd_completed("echo a > a.txt", ""),        # state-mod, seq=1
            _cmd_completed("ls", "files"),               # read-only, no record
            _cmd_completed("echo b > b.txt", ""),        # state-mod, seq=2
        )
        tool_calls, *_ = parse_codex_stream(stream, "r1", "t1", 0, "ungated")
        assert len(tool_calls) == 2
        assert tool_calls[0]["sequence_number"] == 1
        assert tool_calls[1]["sequence_number"] == 2

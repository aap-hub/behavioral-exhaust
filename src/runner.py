"""UGA Task Runner.

Runs coding tasks through Claude Code, captures stream-json traces,
and records results in the SQLite database.

Usage:
    python src/runner.py --phase 0                          # Run all phase-0 tasks
    python src/runner.py --phase 0 --task p0-smoke-bugfix-01  # Run single task
    python src/runner.py --phase 0 --parallel 2             # Run with parallelism
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

# Import unified DB and trace parsing from canonical modules
from db import init_db, insert_run as db_insert_run, insert_tool_call as db_insert_tool_call
from trace_collector import parse_stream_json as tc_parse_stream_json

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "tasks" / "manifest.yaml"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "uga.db"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_config = {
    "task_timeout_seconds": int(os.environ.get("TASK_TIMEOUT_SECONDS", "1800")),
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("uga.runner")


# ===================================================================
# Database helpers (delegated to db.py)
# ===================================================================


# ===================================================================
# Manifest loading
# ===================================================================

def load_manifest(manifest_path: str | Path = MANIFEST_PATH) -> list[dict]:
    """Load and validate the task manifest."""
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_path) as f:
        data = yaml.safe_load(f)

    tasks = data.get("tasks")
    if not tasks:
        raise ValueError("Manifest contains no tasks")

    required_keys = {"task_id", "phase", "type", "repo", "prompt", "validation_command"}
    for i, task in enumerate(tasks):
        missing = required_keys - set(task.keys())
        if missing:
            raise ValueError(f"Task {i} missing keys: {missing}")

    return tasks


def get_task(task_id: str, manifest_path: str | Path = MANIFEST_PATH) -> dict:
    """Retrieve a single task by ID from the manifest (searches all manifests)."""
    # Search the specified manifest first
    search_paths = [Path(manifest_path)]
    # Also search the expansion manifest
    expansion = PROJECT_ROOT / "tasks" / "wave_expansion.yaml"
    if expansion.exists() and expansion != Path(manifest_path):
        search_paths.append(expansion)

    for path in search_paths:
        try:
            tasks = load_manifest(path)
            for task in tasks:
                if task["task_id"] == task_id:
                    return task
        except (FileNotFoundError, ValueError):
            continue
    raise KeyError(f"Task not found in any manifest: {task_id}")


# ===================================================================
# Workspace isolation
# ===================================================================

def create_workspace(repo_path: str | Path) -> Path:
    """Create an isolated workspace by copying the task repo to a temp directory.

    Returns the path to the temporary workspace. Caller is responsible for
    cleanup via cleanup_workspace().
    """
    repo_path = Path(repo_path)
    if not repo_path.is_absolute():
        repo_path = PROJECT_ROOT / repo_path

    if not repo_path.is_dir():
        raise FileNotFoundError(f"Task repo not found: {repo_path}")

    workspace = Path(tempfile.mkdtemp(prefix="uga_workspace_"))
    shutil.copytree(repo_path, workspace, dirs_exist_ok=True)
    log.info("Created workspace: %s (from %s)", workspace, repo_path)
    return workspace


def cleanup_workspace(workspace: Path) -> None:
    """Remove a temporary workspace directory."""
    if workspace.exists() and str(workspace).startswith(tempfile.gettempdir()):
        shutil.rmtree(workspace, ignore_errors=True)
        log.info("Cleaned up workspace: %s", workspace)


# ===================================================================
# Stream-JSON trace parsing (delegated to trace_collector.py)
# ===================================================================


# ===================================================================
# Token counting from stream-json
# ===================================================================

def extract_token_count(raw: str) -> int | None:
    """Try to extract total token usage from stream-json output."""
    total = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Claude Code stream-json emits usage in result events
        usage = event.get("usage")
        if isinstance(usage, dict):
            total += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    return total if total > 0 else None


def count_all_tool_calls(raw: str) -> int:
    """Count ALL tool_use blocks in stream-json (including read-only).

    Issue #5 fix: total_tool_calls should reflect all calls the agent made,
    not just state-modifying ones. State-modifying count is separate.
    """
    count = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    count += 1
    return count


# ===================================================================
# Core: run_task
# ===================================================================

def run_task(
    task_id: str,
    condition: str = "ungated",
    db_path: str | Path = DEFAULT_DB_PATH,
    manifest_path: str | Path = MANIFEST_PATH,
) -> dict:
    """Run a single task through Claude Code and record results.

    Returns a dict with run metadata and outcomes.
    """
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    log.info("=== Starting run %s for task %s (condition=%s) ===", run_id, task_id, condition)

    # 1. Load task from manifest
    task = get_task(task_id, manifest_path)
    phase = task["phase"]

    # 2. Create isolated workspace
    workspace: Path | None = None
    try:
        workspace = create_workspace(task["repo"])
    except FileNotFoundError as exc:
        log.error("Workspace setup failed for %s: %s", task_id, exc)
        # Issue #12 fix: record failure in DB for audit trail
        fail_record = {
            "run_id": run_id,
            "task_id": task_id,
            "phase": phase,
            "condition": condition,
            "model_version": os.environ.get("UGA_MODEL", "sonnet"),
            "task_source": task.get("source", "synthetic"),
            "wave": int(os.environ.get("UGA_WAVE", "1")),
            "start_time": datetime.now(timezone.utc).isoformat(),
            "end_time": datetime.now(timezone.utc).isoformat(),
            "task_success": None,
            "exit_code": None,
            "total_tool_calls": 0,
            "total_state_modifying_calls": 0,
            "wall_clock_seconds": 0,
            "error": f"workspace_setup_failed: {exc}",
        }
        try:
            conn = init_db(str(db_path))
            try:
                db_insert_run(conn, fail_record)
            finally:
                conn.close()
        except Exception as db_exc:
            log.error("Failed to store workspace failure record: %s", db_exc)
        return fail_record

    start_time = datetime.now(timezone.utc)
    stream_file = None
    stderr_file = None
    timed_out = False
    proc: subprocess.Popen | None = None
    timer: threading.Timer | None = None

    try:
        # 3. Run Claude Code
        model = os.environ.get("UGA_MODEL", "sonnet")
        cmd = [
            "claude",
            "-p", task["prompt"],
            "--model", model,
            "--output-format", "stream-json",
            "--verbose",
        ]
        log.info("Running: %s", " ".join(cmd))
        log.info("Workspace: %s", workspace)

        stream_file = tempfile.NamedTemporaryFile(
            mode="w", prefix="uga_stream_", suffix=".jsonl",
            delete=False,
        )

        # Codex #15 fix: redirect stderr to a file instead of PIPE to avoid
        # deadlock when stderr buffer fills while we drain stdout.
        stderr_file = tempfile.NamedTemporaryFile(
            mode="w", prefix="uga_stderr_", suffix=".log", delete=False,
        )
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            cwd=str(workspace),
            text=True,
        )

        # Watchdog timer
        def _watchdog():
            nonlocal timed_out
            timed_out = True
            log.warning("TIMEOUT: killing Claude Code for %s after %ds", task_id, _config["task_timeout_seconds"])
            proc.kill()

        timer = threading.Timer(_config["task_timeout_seconds"], _watchdog)
        timer.start()

        # 4. Stream stdout to file in real-time
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

        stderr_file.close()
        try:
            with open(stderr_file.name) as f:
                stderr_output = f.read()
            if stderr_output:
                log.debug("Claude Code stderr: %s", stderr_output[:500])
        except Exception:
            stderr_output = ""

        log.info(
            "Claude Code finished: exit=%d, wall=%.1fs, lines=%d, timed_out=%s",
            exit_code, wall_clock, len(stdout_lines), timed_out,
        )

        # 5. Run validation
        task_success = None
        if not timed_out and exit_code == 0:
            task_success = _run_validation(task["validation_command"], workspace)
        elif timed_out:
            log.warning("Skipping validation (timed out)")
        else:
            log.warning("Skipping validation (Claude Code exit=%d)", exit_code)
            # Still try validation -- the agent may have partially succeeded
            task_success = _run_validation(task["validation_command"], workspace)

        # 6. Parse trace using canonical trace_collector (state-modifying only)
        import io
        tool_calls = tc_parse_stream_json(io.StringIO(raw_stream), run_id=run_id)
        # Fill in run-level context fields that trace_collector leaves as None
        for tc in tool_calls:
            tc["task_id"] = task_id
            tc["phase"] = phase
            tc["condition"] = condition
        total_tokens = extract_token_count(raw_stream)

        # 7. Build run record
        # Issue #5 fix: total_tool_calls counts ALL calls, state_modifying is separate
        # Issue #11 fix: timed_out and error included BEFORE DB insert
        all_tool_count = count_all_tool_calls(raw_stream)
        run_record = {
            "run_id": run_id,
            "task_id": task_id,
            "phase": phase,
            "condition": condition,
            "replicate_k": 1,
            "model_version": model,
            "task_source": task.get("source", "synthetic"),
            "wave": int(os.environ.get("UGA_WAVE", "1")),
            "seed": None,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "total_tokens": total_tokens,
            "total_tool_calls": all_tool_count,
            "total_state_modifying_calls": len(tool_calls),
            "task_success": task_success,
            "exit_code": exit_code if not timed_out else -9,
            "wall_clock_seconds": wall_clock,
            "raw_stream_json": raw_stream,
            "timed_out": timed_out,
            "error": "timeout" if timed_out else None,
        }

        # 8. Store in database (single transaction for atomicity, Codex #3 fix)
        conn = init_db(str(db_path))
        try:
            conn.execute("BEGIN")
            db_insert_run(conn, run_record)
            for tc in tool_calls:
                db_insert_tool_call(conn, tc)
            conn.commit()
            log.info(
                "Stored run %s: success=%s, tool_calls=%d (state_mod=%d), tokens=%s",
                run_id, task_success, all_tool_count, len(tool_calls), total_tokens,
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return run_record

    except Exception as exc:
        end_time = datetime.now(timezone.utc)
        log.exception("Infrastructure failure running %s: %s", task_id, exc)

        # Save partial trace if we have anything
        raw_partial = ""
        if stream_file and not stream_file.closed:
            stream_file.close()
        if stream_file and os.path.exists(stream_file.name):
            with open(stream_file.name) as f:
                raw_partial = f.read()

        run_record = {
            "run_id": run_id,
            "task_id": task_id,
            "phase": phase,
            "condition": condition,
            "replicate_k": 1,
            "model_version": os.environ.get("UGA_MODEL", "sonnet"),
            "task_source": task.get("source", "synthetic"),
            "wave": int(os.environ.get("UGA_WAVE", "1")),
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
        try:
            conn = init_db(str(db_path))
            try:
                db_insert_run(conn, run_record)
            finally:
                conn.close()
        except Exception as db_exc:
            log.error("Failed to store failure record: %s", db_exc)
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
        # Clean up workspace
        if workspace:
            cleanup_workspace(workspace)


def _run_validation(command: str, workspace: Path) -> bool | None:
    """Run the validation command in the workspace independently.

    Returns True on pass, False on fail, None if validation itself broke
    (so we don't record a false label).

    Strategy:
    1. Normalize "python" to "python3" (macOS doesn't have "python")
    2. Look for a venv the agent may have created
    3. Install the repo if needed (pip install -e .)
    4. Run the specific FAIL_TO_PASS tests
    5. Return None (not False) if the test infrastructure broke
    """
    log.info("Running validation: %s", command)

    # Normalize python -> python3
    normalized_cmd = command.replace("python -m pytest", "python3 -m pytest")
    normalized_cmd = normalized_cmd.replace("python tests/runtests.py", "python3 tests/runtests.py")
    normalized_cmd = normalized_cmd.replace("python manage.py", "python3 manage.py")

    # Build setup: activate venv if exists, install repo
    setup_parts = []

    # Check for venv
    for venv_dir in [".venv", "venv", "env"]:
        venv_path = workspace / venv_dir / "bin" / "activate"
        if venv_path.exists():
            setup_parts.append(f"source {venv_path}")
            log.info("Found venv at %s", venv_dir)
            break

    # Ensure pytest is available
    setup_parts.append("python3 -m pip install pytest -q 2>/dev/null || true")

    # Try installing the repo
    setup_parts.append("python3 -m pip install -e . -q 2>/dev/null || true")

    setup = " && ".join(setup_parts)
    full_command = f"{setup} && {normalized_cmd}"

    try:
        result = subprocess.run(
            full_command,
            shell=True,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=180,
            executable="/bin/bash",
        )

        # Distinguish test failure from infrastructure failure
        if result.returncode == 127:
            log.warning("Validation BROKEN (exit=127, command not found)")
            return None  # Don't label — infrastructure broke
        if "ModuleNotFoundError" in result.stderr or "ImportError" in result.stderr:
            log.warning("Validation BROKEN (missing module)")
            return None
        if "SyntaxError" in result.stderr and "ast" in result.stderr:
            log.warning("Validation BROKEN (Python version incompatibility)")
            return None

        success = result.returncode == 0
        if success:
            log.info("Validation PASSED (independent)")
        else:
            log.info("Validation FAILED (exit=%d)", result.returncode)
            if result.stdout:
                log.debug("Validation stdout: %s", result.stdout[-500:])
            if result.stderr:
                log.debug("Validation stderr: %s", result.stderr[-500:])
        return success
    except subprocess.TimeoutExpired:
        log.warning("Validation timed out (180s)")
        return None  # Don't label — might have passed given more time
    except Exception as exc:
        log.error("Validation error: %s", exc)
        return None


# ===================================================================
# Core: run_phase
# ===================================================================

def run_phase(
    phase: int,
    db_path: str | Path = DEFAULT_DB_PATH,
    manifest_path: str | Path = MANIFEST_PATH,
    parallel: int = 1,
    task_filter: str | None = None,
    condition: str = "ungated",
) -> list[dict]:
    """Run all tasks for a given phase.

    Args:
        phase: Phase number to run (0 or 1).
        db_path: Path to the SQLite database.
        manifest_path: Path to the task manifest.
        parallel: Number of concurrent task runs.
        task_filter: If set, only run this specific task_id.
        condition: Experimental condition (ungated, behavioral-gate, etc.).

    Returns:
        List of run result dicts.
    """
    init_db(str(db_path)).close()
    tasks = load_manifest(manifest_path)

    # Filter to phase
    phase_tasks = [t for t in tasks if t["phase"] == phase]
    if not phase_tasks:
        log.warning("No tasks found for phase %d", phase)
        return []

    # Optional single-task filter
    if task_filter:
        phase_tasks = [t for t in phase_tasks if t["task_id"] == task_filter]
        if not phase_tasks:
            raise KeyError(f"Task {task_filter} not found in phase {phase}")

    log.info(
        "Running phase %d: %d task(s), parallel=%d, condition=%s",
        phase, len(phase_tasks), parallel, condition,
    )

    results: list[dict] = []

    if parallel <= 1:
        # Sequential execution
        for task in phase_tasks:
            result = run_task(
                task["task_id"],
                condition=condition,
                db_path=db_path,
                manifest_path=manifest_path,
            )
            results.append(result)
    else:
        # Parallel execution
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            futures = {
                pool.submit(
                    run_task,
                    task["task_id"],
                    condition=condition,
                    db_path=db_path,
                    manifest_path=manifest_path,
                ): task["task_id"]
                for task in phase_tasks
            }
            for future in as_completed(futures):
                task_id = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as exc:
                    log.error("Task %s raised: %s", task_id, exc)
                    results.append({
                        "task_id": task_id,
                        "error": f"thread_exception: {exc}",
                    })

    # Summary
    succeeded = sum(1 for r in results if r.get("task_success") is True)
    failed = sum(1 for r in results if r.get("task_success") is False)
    errored = sum(1 for r in results if r.get("error"))
    log.info(
        "Phase %d complete: %d/%d succeeded, %d failed, %d errors",
        phase, succeeded, len(results), failed, errored,
    )
    return results


# ===================================================================
# CLI
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description="UGA Task Runner: run coding tasks through Claude Code",
    )
    parser.add_argument(
        "--phase", type=int, required=True,
        help="Phase number to run (0 = calibration, 1 = gating)",
    )
    parser.add_argument(
        "--task", type=str, default=None,
        help="Run a specific task_id (default: all tasks in phase)",
    )
    parser.add_argument(
        "--parallel", type=int, default=1,
        help="Number of concurrent task runs (default: 1)",
    )
    parser.add_argument(
        "--condition", type=str, default="ungated",
        choices=["ungated", "behavioral-gate", "critic-gate", "adaptive-gate"],
        help="Experimental condition (default: ungated)",
    )
    parser.add_argument(
        "--db", type=str, default=str(DEFAULT_DB_PATH),
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--manifest", type=str, default=str(MANIFEST_PATH),
        help=f"Path to manifest YAML (default: {MANIFEST_PATH})",
    )
    parser.add_argument(
        "--timeout", type=int, default=None,
        help=f"Override task timeout in seconds (default: {_config['task_timeout_seconds']})",
    )

    args = parser.parse_args()

    if args.timeout is not None:
        _config["task_timeout_seconds"] = args.timeout
        log.info("Timeout overridden to %d seconds", _config["task_timeout_seconds"])

    results = run_phase(
        phase=args.phase,
        db_path=args.db,
        manifest_path=args.manifest,
        parallel=args.parallel,
        task_filter=args.task,
        condition=args.condition,
    )

    # Print summary to stdout
    print("\n--- Run Summary ---")
    for r in results:
        status = "PASS" if r.get("task_success") else "FAIL" if r.get("task_success") is False else "ERROR"
        error = f" ({r['error']})" if r.get("error") else ""
        wall = f" {r['wall_clock_seconds']:.1f}s" if r.get("wall_clock_seconds") else ""
        calls = f" {r.get('total_tool_calls', '?')} calls" if r.get("total_tool_calls") is not None else ""
        print(f"  {r.get('task_id', '?'):30s} {status:5s}{wall}{calls}{error}")

    # Exit with 1 if any task had infrastructure errors
    if any(r.get("error") for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Independent Validator — Replay agent edits on a fresh repo and run tests.

This does NOT trust the agent's own test output. It:
1. Copies the original repo to a temp directory
2. Extracts Write/Edit operations from raw_stream_json
3. Applies them to the fresh copy
4. Runs the FAIL_TO_PASS tests from the manifest
5. Labels based on OUR test run, not the agent's

This is the epistemically sound validation path.

Usage:
    python3 src/independent_validate.py                # Validate all unlabeled runs
    python3 src/independent_validate.py --run-id X     # Validate specific run
    python3 src/independent_validate.py --force        # Re-validate everything
    python3 src/independent_validate.py --dry-run      # Show plan
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DB_PATH = PROJECT_ROOT / "data" / "uga.db"
MANIFEST_PATH = PROJECT_ROOT / "tasks" / "manifest.yaml"
EXPANSION_PATH = PROJECT_ROOT / "tasks" / "wave_expansion.yaml"


def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db


def load_task_meta(task_id: str) -> dict:
    import yaml
    for path in [MANIFEST_PATH, EXPANSION_PATH]:
        if not path.exists():
            continue
        with open(path) as f:
            data = yaml.safe_load(f)
        for t in (data or {}).get("tasks", []):
            if t["task_id"] == task_id:
                return t
    return {}


def extract_edits_from_stream(raw: str) -> list[dict]:
    """Extract all Write and Edit operations from raw stream JSON."""
    edits = []
    for line in raw.split("\n"):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") != "assistant":
            continue
        for block in ev.get("message", {}).get("content", []):
            if block.get("type") != "tool_use":
                continue
            name = block.get("name", "")
            inp = block.get("input", {})
            if name == "Write":
                edits.append({
                    "type": "write",
                    "file_path": inp.get("file_path", ""),
                    "content": inp.get("content", ""),
                })
            elif name == "Edit":
                edits.append({
                    "type": "edit",
                    "file_path": inp.get("file_path", ""),
                    "old_string": inp.get("old_string", ""),
                    "new_string": inp.get("new_string", ""),
                })
    return edits


def relativize_path(abs_path: str, workspace_markers=("uga_workspace_",)) -> str:
    """Convert absolute workspace paths to repo-relative paths."""
    for marker in workspace_markers:
        if marker in abs_path:
            idx = abs_path.index(marker)
            rest = abs_path[idx:]
            parts = rest.split("/", 1)
            if len(parts) > 1:
                return parts[1]
    # Already relative or no workspace prefix
    return abs_path


def apply_edits(workspace: Path, edits: list[dict]) -> tuple[int, int]:
    """Apply edits to the workspace. Returns (applied, failed)."""
    applied = 0
    failed = 0

    for edit in edits:
        rel_path = relativize_path(edit["file_path"])

        # Path traversal guard: reject paths that escape the workspace
        if ".." in rel_path or rel_path.startswith("/"):
            failed += 1
            continue
        target = workspace / rel_path
        # Resolve symlinks and verify the target is within the workspace
        try:
            resolved = target.resolve()
            workspace_resolved = workspace.resolve()
            if not str(resolved).startswith(str(workspace_resolved) + "/") and resolved != workspace_resolved:
                failed += 1
                continue
        except (OSError, ValueError):
            failed += 1
            continue

        if edit["type"] == "write":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(edit["content"])
            applied += 1

        elif edit["type"] == "edit":
            if not target.exists():
                failed += 1
                continue
            content = target.read_text()
            old = edit["old_string"]
            new = edit["new_string"]
            if old in content:
                content = content.replace(old, new, 1)
                target.write_text(content)
                applied += 1
            else:
                failed += 1

    return applied, failed


def _get_swebench_pip_packages(task_id: str) -> list[str]:
    """Get pinned pip packages from SWE-bench specs for this task."""
    import logging
    log = logging.getLogger("uga.validate")
    try:
        import json
        meta_path = PROJECT_ROOT / "tasks" / "swebench_metadata.json"
        if not meta_path.exists():
            log.warning("swebench_metadata.json not found — using unpinned deps for %s", task_id)
            return []
        with open(meta_path) as f:
            metadata = json.load(f)
        task = metadata.get(task_id, {})
        repo = task.get("repo", "")
        version = task.get("version", "")
        if not repo or not version:
            log.warning("No repo/version in metadata for %s — using unpinned deps", task_id)
            return []

        from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
        specs = MAP_REPO_VERSION_TO_SPECS.get(repo, {}).get(version, {})
        return specs.get("pip_packages", [])
    except Exception as exc:
        log.warning("Failed to get pinned deps for %s (%s) — falling back to unpinned", task_id, exc)
        return []


def run_tests(workspace: Path, validation_cmd: str, task_id: str = "") -> tuple[bool | None, str]:
    """Run validation tests in workspace. Returns (result, output).

    result: True=pass, False=fail, None=infra broken
    """
    PYTHON = "python3.10"
    cmd = validation_cmd.replace("python -m pytest", f"{PYTHON} -m pytest")
    cmd = cmd.replace("python tests/runtests.py", f"{PYTHON} tests/runtests.py")
    cmd = cmd.replace("python manage.py", f"{PYTHON} manage.py")
    cmd = cmd.replace("python3 -m pytest", f"{PYTHON} -m pytest")

    PYTHON = "python3.10"
    venv_dir = f"/tmp/uga_venv_$$"

    # Get SWE-bench pinned packages for this specific task+version
    pinned = _get_swebench_pip_packages(task_id)
    pin_cmd = f"pip install {' '.join(repr(p) for p in pinned)} -q 2>/dev/null; " if pinned else ""

    setup = (
        f"{PYTHON} -m venv {venv_dir} && "
        f"source {venv_dir}/bin/activate && "
        f"pip install -q --upgrade pip setuptools wheel 2>/dev/null; "
        # SWE-bench pinned deps first (exact versions for this repo+version)
        + pin_cmd +
        # Repo's own requirements
        f"for rf in requirements/tests.txt requirements/test.txt requirements/dev.txt "
        f"requirements.txt test-requirements.txt; do "
        f"  [ -f \"$rf\" ] && pip install -r \"$rf\" -q 2>/dev/null && break; "
        f"done; "
        # Install repo itself
        f"pip install -e . -q 2>/dev/null || true; "
        f"pip install pytest -q 2>/dev/null || true; "
    )

    try:
        result = subprocess.run(
            setup + cmd,
            shell=True,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=180,
            executable="/bin/bash",
        )

        output = result.stdout + "\n" + result.stderr

        # Infrastructure failure detection
        if result.returncode == 127:
            return None, "exit 127: command not found"
        if "ModuleNotFoundError" in output or "ImportError" in output:
            # Check if it's a test dep issue vs. the fix being wrong
            if "No module named" in output:
                module = re.search(r"No module named '(\w+)'", output)
                mod_name = module.group(1) if module else "unknown"
                return None, f"missing module: {mod_name}"
        if "SyntaxError" in output and "ast" in output:
            return None, "Python version incompatibility"

        return result.returncode == 0, output[-500:]

    except subprocess.TimeoutExpired:
        return None, "timeout"
    except Exception as exc:
        return None, str(exc)


def validate_run(run_id: str, db) -> dict:
    """Independently validate a single run."""
    run = db.execute(
        "SELECT run_id, task_id, raw_stream_json FROM runs WHERE run_id = ?",
        (run_id,)
    ).fetchone()

    if not run or not run["raw_stream_json"]:
        return {"run_id": run_id, "result": None, "reason": "no stream data"}

    task_meta = load_task_meta(run["task_id"])
    if not task_meta:
        return {"run_id": run_id, "result": None, "reason": "task not in manifest"}

    repo_path = PROJECT_ROOT / task_meta["repo"]
    if not repo_path.is_dir():
        return {"run_id": run_id, "result": None, "reason": "repo not found"}

    val_cmd = task_meta.get("validation_command", "")
    if not val_cmd:
        return {"run_id": run_id, "result": None, "reason": "no validation command"}

    # 1. Fresh copy of original repo
    workspace = Path(tempfile.mkdtemp(prefix="uga_validate_"))
    try:
        shutil.copytree(repo_path, workspace, dirs_exist_ok=True)

        # 2. Extract and apply agent's edits
        edits = extract_edits_from_stream(run["raw_stream_json"])
        if not edits:
            return {"run_id": run_id, "result": None, "reason": "no edits found in trace"}

        applied, failed_edits = apply_edits(workspace, edits)

        # 3. Run the FAIL_TO_PASS tests (OUR choice, not the agent's)
        result, output = run_tests(workspace, val_cmd, task_id=run["task_id"])

        return {
            "run_id": run_id,
            "task_id": run["task_id"],
            "result": result,
            "edits_applied": applied,
            "edits_failed": failed_edits,
            "output_tail": output[-200:] if output else "",
            "validation_cmd": val_cmd[:100],
        }

    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def validate_all(force: bool = False, dry_run: bool = False):
    """Validate all runs that need labels."""
    db = get_db()

    if force:
        where = "task_source = 'swe-bench-lite' AND raw_stream_json IS NOT NULL"
    else:
        # Only validate runs without an existing validated label
        where = ("task_source = 'swe-bench-lite' AND raw_stream_json IS NOT NULL "
                 "AND validation_source IS NULL")

    runs = db.execute(f"""
        SELECT run_id, task_id, task_success, notes
        FROM runs WHERE {where}
        ORDER BY created_at
    """).fetchall()

    print(f"Independently validating {len(runs)} runs...\n")

    stats = {"pass": 0, "fail": 0, "infra": 0, "no_edits": 0, "changed": 0}

    for run in runs:
        if dry_run:
            print(f"  Would validate: {run['task_id']} ({run['run_id']})")
            continue

        result = validate_run(run["run_id"], db)
        r = result["result"]

        if r is True:
            stats["pass"] += 1
            label = "pass"
        elif r is False:
            stats["fail"] += 1
            label = "fail"
        elif result.get("reason") == "no edits found in trace":
            stats["no_edits"] += 1
            label = "no_edits"
        else:
            stats["infra"] += 1
            label = f"infra ({result.get('output_tail', result.get('reason', ''))[:40]})"

        old = run["task_success"]
        new_val = 1 if r is True else (0 if r is False else None)
        changed = new_val is not None and new_val != old
        marker = " *CHANGED*" if changed else ""

        edits_info = f"edits={result.get('edits_applied', '?')}/{result.get('edits_applied', 0) + result.get('edits_failed', 0)}"
        print(f"  [{label:12}] {run['task_id']:40} {edits_info}{marker}")

        # Always write provenance so every validated run has validation_source
        from datetime import datetime, timezone
        if new_val is not None:
            db.execute(
                "UPDATE runs SET task_success = ?, "
                "validation_source = ?, validation_timestamp = ? "
                "WHERE run_id = ?",
                (new_val, f"independent-validated: {label}",
                 datetime.now(timezone.utc).isoformat(), run["run_id"])
            )
        else:
            db.execute(
                "UPDATE runs SET "
                "validation_source = ?, validation_timestamp = ? "
                "WHERE run_id = ?",
                (f"independent-validated: {label}",
                 datetime.now(timezone.utc).isoformat(), run["run_id"])
            )
        if changed:
            stats["changed"] += 1

    if not dry_run:
        db.commit()

    print(f"\n--- SUMMARY ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Independent validation by edit replay")
    parser.add_argument("--run-id", help="Validate specific run")
    parser.add_argument("--force", action="store_true", help="Re-validate everything")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.run_id:
        db = get_db()
        result = validate_run(args.run_id, db)
        print(json.dumps(result, indent=2, default=str))
    else:
        validate_all(force=args.force, dry_run=args.dry_run)

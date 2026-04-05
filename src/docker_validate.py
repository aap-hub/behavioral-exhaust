"""
Lightweight Docker validation for UGA runs.

Uses docker/Dockerfile.validate (python:3.10-slim + git + pytest) instead of
the heavy SWE-bench Docker harness. ~200MB image, ~500MB per run.

Wires docker/ into the pipeline (Codex audit issue #1).

Usage:
    python src/docker_validate.py                    # Validate all unvalidated SWE-bench runs
    python src/docker_validate.py --run-id X         # Validate specific run
    python src/docker_validate.py --build            # Build Docker image only
"""

import argparse
import json
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from swebench_validate import extract_patch_from_stream

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "uga.db"
MANIFEST_PATH = PROJECT_ROOT / "tasks" / "manifest.yaml"
EXPANSION_PATH = PROJECT_ROOT / "tasks" / "wave_expansion.yaml"
IMAGE_NAME = "uga-validate"
DOCKERFILE = PROJECT_ROOT / "docker" / "Dockerfile.validate"


def _load_task_meta(task_id: str) -> dict | None:
    """Search both manifest.yaml and wave_expansion.yaml for a task."""
    import yaml
    for path in [MANIFEST_PATH, EXPANSION_PATH]:
        if not path.exists():
            continue
        with open(path) as f:
            data = yaml.safe_load(f)
        for t in (data or {}).get("tasks", []):
            if t["task_id"] == task_id:
                return t
    return None


def build_image() -> bool:
    """Build the lightweight validation Docker image."""
    print(f"Building Docker image '{IMAGE_NAME}'...")
    result = subprocess.run(
        ["docker", "build", "-t", IMAGE_NAME, "-f", str(DOCKERFILE), "."],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Docker build failed:\n{result.stderr[:500]}")
        return False
    print("Docker image built successfully.")
    return True


def ensure_image() -> bool:
    """Check if image exists, build if not."""
    result = subprocess.run(
        ["docker", "image", "inspect", IMAGE_NAME],
        capture_output=True,
    )
    if result.returncode != 0:
        return build_image()
    return True


def validate_run(run_id: str, db_path: str = None) -> dict:
    """Validate a single run using the lightweight Docker container.

    Returns a dict with: run_id, task_id, success, output, error
    """
    db = sqlite3.connect(str(db_path or DB_PATH))
    db.row_factory = sqlite3.Row

    run = db.execute(
        "SELECT run_id, task_id, raw_stream_json FROM runs WHERE run_id = ?",
        (run_id,)
    ).fetchone()

    if not run:
        return {"run_id": run_id, "error": "run not found"}

    task_id = run["task_id"]
    raw = run["raw_stream_json"]

    if not raw:
        return {"run_id": run_id, "task_id": task_id, "error": "no raw_stream_json"}

    # Get validation command from manifest or wave_expansion
    task_meta = _load_task_meta(task_id)
    if not task_meta:
        return {"run_id": run_id, "task_id": task_id, "error": "task not in manifest or wave_expansion"}

    validation_cmd = task_meta["validation_command"]
    repo_path = PROJECT_ROOT / task_meta["repo"]

    if not repo_path.is_dir():
        return {"run_id": run_id, "task_id": task_id, "error": f"repo not found: {repo_path}"}

    # Extract patch from raw stream
    patch = extract_patch_from_stream(raw, str(repo_path))
    if not patch:
        return {"run_id": run_id, "task_id": task_id, "error": "no patch extracted", "success": False}

    # Write patch to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
        f.write(patch)
        patch_path = f.name

    try:
        # Run in Docker
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "--memory=2g",
                "-v", f"{repo_path}:/repo:ro",
                "-v", f"{patch_path}:/patch.diff:ro",
                IMAGE_NAME,
                validation_cmd,
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        output = result.stdout + result.stderr
        success = result.returncode == 0

        # Update DB — Codex #J: write provenance columns, don't overwrite notes
        from datetime import datetime, timezone
        label = "RESOLVED" if success else "UNRESOLVED"
        db.execute(
            "UPDATE runs SET task_success = ?, "
            "validation_source = ?, validation_timestamp = ? "
            "WHERE run_id = ?",
            (1 if success else 0, f"docker-validated: {label}",
             datetime.now(timezone.utc).isoformat(), run_id)
        )
        db.commit()

        return {
            "run_id": run_id,
            "task_id": task_id,
            "success": success,
            "exit_code": result.returncode,
            "output": output[-500:],  # last 500 chars
        }

    except subprocess.TimeoutExpired:
        from datetime import datetime, timezone
        db.execute(
            "UPDATE runs SET task_success = 0, "
            "validation_source = ?, validation_timestamp = ? "
            "WHERE run_id = ?",
            ("docker-validated: TIMEOUT",
             datetime.now(timezone.utc).isoformat(), run_id)
        )
        db.commit()
        return {"run_id": run_id, "task_id": task_id, "success": False, "error": "timeout (300s)"}
    finally:
        os.unlink(patch_path)


def validate_all(db_path: str = None):
    """Validate all SWE-bench runs that haven't been Docker-validated yet."""
    db = sqlite3.connect(str(db_path or DB_PATH))
    db.row_factory = sqlite3.Row

    runs = db.execute("""
        SELECT run_id, task_id FROM runs
        WHERE task_source = 'swe-bench-lite'
          AND model_version = 'sonnet'
          AND (validation_source IS NULL OR validation_source NOT LIKE 'docker-validated%')
        ORDER BY created_at
    """).fetchall()

    if not runs:
        print("All SWE-bench runs already validated.")
        return

    if not ensure_image():
        print("Failed to build Docker image. Aborting.")
        return

    print(f"\nValidating {len(runs)} runs...\n")

    for run in runs:
        print(f"  {run['task_id']:40} ...", end=" ", flush=True)
        result = validate_run(run["run_id"], db_path)
        if result.get("error"):
            print(f"ERROR: {result['error']}")
        elif result.get("success"):
            print("RESOLVED")
        else:
            print("UNRESOLVED")

    # Summary
    resolved = db.execute(
        "SELECT COUNT(*) FROM runs WHERE task_source='swe-bench-lite' AND task_success=1"
    ).fetchone()[0]
    total = db.execute(
        "SELECT COUNT(*) FROM runs WHERE task_source='swe-bench-lite'"
    ).fetchone()[0]
    print(f"\nSummary: {resolved}/{total} resolved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lightweight Docker validation for UGA runs")
    parser.add_argument("--run-id", help="Validate specific run")
    parser.add_argument("--build", action="store_true", help="Build Docker image only")
    args = parser.parse_args()

    if args.build:
        build_image()
    elif args.run_id:
        if not ensure_image():
            exit(1)
        result = validate_run(args.run_id)
        print(json.dumps(result, indent=2))
    else:
        validate_all()

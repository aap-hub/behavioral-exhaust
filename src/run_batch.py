#!/usr/bin/env python3
"""Run a batch of protocol tasks. Designed to be called by parallel subagents.

Usage:
    PYTHONPATH=src python3 src/run_batch.py data/batch_00.json
    PYTHONPATH=src python3 src/run_batch.py data/batch_00.json --validate
"""
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.chdir(str(PROJECT_ROOT))

from db import init_db
from runner import run_task
from independent_validate import validate_run, get_db

DB_PATH = PROJECT_ROOT / "data" / "uga.db"

def main():
    batch_file = sys.argv[1]
    do_validate = "--validate" in sys.argv

    with open(batch_file) as f:
        tasks = json.load(f)

    os.environ["UGA_MODEL"] = "sonnet"
    os.environ["UGA_WAVE"] = "100"  # Wave 100 = protocol wave 2

    init_db(str(DB_PATH)).close()

    for i, task_id in enumerate(tasks):
        print(f"[{i+1}/{len(tasks)}] {task_id}", flush=True)

        # Run
        try:
            result = run_task(task_id, condition="ungated", db_path=str(DB_PATH))
            status = "PASS" if result.get("task_success") else "FAIL"
            calls = result.get("total_state_modifying_calls", 0)
            wall = result.get("wall_clock_seconds", 0)
            print(f"  -> {status} ({wall:.0f}s, {calls} calls)", flush=True)
        except Exception as exc:
            print(f"  -> ERROR: {exc}", flush=True)
            continue

        # Validate independently
        if do_validate:
            try:
                db = get_db()
                vresult = validate_run(result["run_id"], db)
                r = vresult["result"]
                vlabel = "PASS" if r is True else "FAIL" if r is False else "INFRA"
                print(f"  -> validated: {vlabel}", flush=True)

                if r is not None:
                    from datetime import datetime, timezone
                    db.execute(
                        "UPDATE runs SET task_success=?, validation_source=?, validation_timestamp=? WHERE run_id=?",
                        (1 if r else 0, f"independent-validated: {'pass' if r else 'fail'}",
                         datetime.now(timezone.utc).isoformat(), result["run_id"])
                    )
                    db.commit()
            except Exception as exc:
                print(f"  -> validation error: {exc}", flush=True)

    print(f"\nBatch complete: {len(tasks)} tasks", flush=True)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
UGA Phase 0 Protocol — The Repeatable Experiment

This is the single source of truth for the experiment. Everything is fixed:
  1. ENVIRONMENT: Python 3.10, SWE-bench pinned deps per task
  2. TASKS: A fixed set selected for ~30-70% pass rate
  3. RUNNER: Claude Code Sonnet 4.6, ungated, with independent validation
  4. ANALYSIS: Feature extraction + Spearman correlations at task level

Running this script executes one clean cycle of the protocol.

Usage:
    python3 protocol.py run             # Run all 71 tasks once (one wave)
    python3 protocol.py validate        # Independent validation
    python3 protocol.py analyze         # Extract features + correlations
    python3 protocol.py status          # Show current data state
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DB_PATH = PROJECT_ROOT / "data" / "uga.db"
PROTOCOL_FILE = PROJECT_ROOT / "data" / "protocol_tasks.json"

# ═══════════════════════════════════════════════════════════════════════
# 1. ENVIRONMENT (fixed)
# ═══════════════════════════════════════════════════════════════════════

ENVIRONMENT = {
    "agent_model": "sonnet",           # Claude Sonnet 4.6
    "agent_condition": "ungated",       # No gating in Phase 0
    "python_validation": "python3.10",  # For independent validation
    "timeout_seconds": 1800,            # 30 min per task
    "validation_timeout": 300,          # 5 min for test execution
}

# ═══════════════════════════════════════════════════════════════════════
# 2. TASK SELECTION (Phase A)
# ═══════════════════════════════════════════════════════════════════════

# The 71 tasks are locked in data/protocol_tasks.json.
# Each wave runs all 71 once. No task selection phase needed.


def load_protocol_tasks() -> list[str]:
    """Load the locked set of 71 protocol tasks."""
    if not PROTOCOL_FILE.exists():
        print(f"ERROR: {PROTOCOL_FILE} not found. Cannot proceed.")
        sys.exit(1)
    with open(PROTOCOL_FILE) as f:
        protocol = json.load(f)
    return protocol["tasks"]


# ═══════════════════════════════════════════════════════════════════════
# 3. RUNNER (fixed)
# ═══════════════════════════════════════════════════════════════════════

def run_protocol():
    """Phase B: Run all 71 protocol tasks once (one wave)."""
    tasks = load_protocol_tasks()
    db = _get_db()

    # Determine current wave number
    max_wave = db.execute("SELECT COALESCE(MAX(wave), 0) FROM runs").fetchone()[0]
    wave = max_wave + 1

    from runner import run_task

    os.environ["UGA_MODEL"] = ENVIRONMENT["agent_model"]

    print(f"=== WAVE {wave}: running {len(tasks)} tasks ===\n")

    for i, task_id in enumerate(tasks):
        print(f"  [{i+1}/{len(tasks)}] {task_id} ...", end=" ", flush=True)
        try:
            result = run_task(task_id, condition="ungated", db_path=str(DB_PATH))
            status = "PASS" if result.get("task_success") else "FAIL"
            print(f"{status} ({result.get('wall_clock_seconds',0):.0f}s)")
        except Exception as exc:
            print(f"ERROR: {exc}")


# ═══════════════════════════════════════════════════════════════════════
# 4. VALIDATION (fixed)
# ═══════════════════════════════════════════════════════════════════════

def validate_protocol():
    """Phase C: Independent validation of all unvalidated runs."""
    from independent_validate import validate_all
    validate_all()


# ═══════════════════════════════════════════════════════════════════════
# 5. ANALYSIS (fixed)
# ═══════════════════════════════════════════════════════════════════════

# These are the task-level aggregates actually tested in analysis.py
# (not the raw per-call features). Each run's tool calls are aggregated
# into these before correlating with task_success.
FEATURES = [
    "total_calls",
    "hedging_sum",
    "hedging_max",
    "delib_sum",
    "delib_max",
    "alts_sum",
    "back_sum",
    "verif_sum",
    "verif_max",
    "plan_sum",
    "plan_max",
    "calls_with_reasoning",
]

def analyze_protocol():
    """Phase D: Feature extraction + analysis on protocol data only."""
    from analysis import extract_features_for_all, task_level_correlations, call_level_correlations

    db = _get_db()

    # Ensure features extracted
    n = extract_features_for_all(db)
    if n > 0:
        print(f"Extracted features for {n} calls\n")

    # Only analyze protocol tasks with independent validation
    task_list = load_protocol_tasks()
    task_filter = "AND r.task_id IN ({})".format(",".join(f"'{t}'" for t in task_list))

    # Summary
    row = db.execute(f"""
        SELECT COUNT(*) as runs,
               COUNT(DISTINCT task_id) as tasks,
               SUM(CASE WHEN task_success=1 THEN 1 ELSE 0 END) as pass,
               SUM(CASE WHEN task_success=0 THEN 1 ELSE 0 END) as fail
        FROM runs r
        WHERE r.task_source='swe-bench-lite'
          AND r.task_success IS NOT NULL
          AND r.validation_source IS NOT NULL
          {task_filter}
    """).fetchone()

    print("=" * 60)
    print("UGA PHASE 0 PROTOCOL ANALYSIS")
    print("=" * 60)
    print(f"Runs:  {row['runs']} ({row['pass']} pass, {row['fail']} fail)")
    print(f"Tasks: {row['tasks']} unique")
    if row['runs'] > 0:
        print(f"Rate:  {100*row['pass']/row['runs']:.0f}% pass")
    print()

    # Run standard analysis
    task_level_correlations(db)
    call_level_correlations(db)


# ═══════════════════════════════════════════════════════════════════════
# 6. STATUS
# ═══════════════════════════════════════════════════════════════════════

def status():
    """Show current experiment state."""
    db = _get_db()

    print("=" * 60)
    print("UGA PHASE 0 STATUS")
    print("=" * 60)

    # Protocol tasks
    if PROTOCOL_FILE.exists():
        with open(PROTOCOL_FILE) as f:
            protocol = json.load(f)
        tasks = protocol["tasks"]
        print(f"\nProtocol tasks: {len(tasks)}")
        for tid in tasks:
            row = db.execute("""
                SELECT COUNT(*) as n,
                       SUM(CASE WHEN task_success=1 THEN 1 ELSE 0 END) as p,
                       SUM(CASE WHEN task_success=0 THEN 1 ELSE 0 END) as f
                FROM runs WHERE task_id=? AND task_source='swe-bench-lite' AND task_success IS NOT NULL
            """, (tid,)).fetchone()
            rate = row["p"] / row["n"] if row["n"] > 0 else 0
            bar = "#" * row["p"] + "." * row["f"]
            print(f"  {tid:<45} n={row['n']:>3} rate={rate:.0%} [{bar}]")
    else:
        print("\nNo protocol_tasks.json. Run 'select-tasks' first.")

    # Overall data
    total = db.execute("SELECT COUNT(*) FROM runs WHERE task_source='swe-bench-lite'").fetchone()[0]
    verified = db.execute("""
        SELECT COUNT(*) FROM runs WHERE task_source='swe-bench-lite'
        AND validation_source IS NOT NULL
    """).fetchone()[0]
    calls = db.execute("""
        SELECT COUNT(*) FROM tool_calls tc JOIN runs r ON tc.run_id=r.run_id
        WHERE r.task_source='swe-bench-lite'
    """).fetchone()[0]

    print(f"\nTotal runs: {total} ({verified} verified, {total-verified} unverified)")
    print(f"Total state-modifying calls: {calls}")


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db


def main():
    parser = argparse.ArgumentParser(description="UGA Phase 0 Protocol")
    parser.add_argument("command", choices=["run", "validate", "analyze", "status"],
                        help="Protocol phase to execute")
    args = parser.parse_args()

    if args.command == "run":
        run_protocol()
    elif args.command == "validate":
        validate_protocol()
    elif args.command == "analyze":
        analyze_protocol()
    elif args.command == "status":
        status()


if __name__ == "__main__":
    main()

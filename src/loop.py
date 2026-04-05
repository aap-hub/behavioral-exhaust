#!/usr/bin/env python3
"""
UGA Autonomous Pipeline Loop

Runs the full cycle: run tasks → parse → features → validate → analyze → audit → harden.
Designed to run unattended overnight.

Usage:
    python3 src/loop.py                    # Run full loop
    python3 src/loop.py --wave 2           # Run specific wave
    python3 src/loop.py --dry-run          # Show what would be done
    python3 src/loop.py --analyze-only     # Just run analysis on existing data
"""

import argparse
import io
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from db import init_db, insert_run, insert_tool_call, update_features
from trace_collector import parse_stream_json
from runner import run_task, count_all_tool_calls
from analysis import extract_features_for_all, summary, task_level_correlations, call_level_correlations, reparse_all_runs

DB_PATH = PROJECT_ROOT / "data" / "uga.db"
MANIFEST_PATH = PROJECT_ROOT / "tasks" / "manifest.yaml"
LOG_PATH = PROJECT_ROOT / "data" / "loop.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(LOG_PATH), mode="a"),
    ],
)
log = logging.getLogger("uga.loop")


def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db


def get_unrun_tasks(wave: int = None) -> list[dict]:
    """Find SWE-bench tasks in the manifest that haven't been run yet."""
    import yaml
    with open(MANIFEST_PATH) as f:
        manifest = yaml.safe_load(f)

    db = get_db()
    existing = set(
        r["task_id"] for r in
        db.execute("SELECT DISTINCT task_id FROM runs WHERE task_source='swe-bench-lite'").fetchall()
    )

    unrun = []
    for t in manifest["tasks"]:
        if t.get("source") != "swe-bench-lite":
            continue
        if t["task_id"] in existing:
            continue
        unrun.append(t)

    log.info("Found %d unrun SWE-bench tasks (%d already run)", len(unrun), len(existing))
    return unrun


def run_wave(tasks: list[dict], wave_num: int) -> list[dict]:
    """Run a wave of tasks sequentially."""
    results = []
    os.environ["UGA_WAVE"] = str(wave_num)
    os.environ["UGA_MODEL"] = "sonnet"

    for i, task in enumerate(tasks):
        log.info("=== Wave %d: Task %d/%d: %s ===", wave_num, i + 1, len(tasks), task["task_id"])
        try:
            result = run_task(
                task["task_id"],
                condition="ungated",
                db_path=str(DB_PATH),
                manifest_path=str(MANIFEST_PATH),
            )
            status = "PASS" if result.get("task_success") else "FAIL" if result.get("task_success") is False else "ERROR"
            wall = result.get("wall_clock_seconds", 0)
            calls = result.get("total_state_modifying_calls", 0)
            log.info("  Result: %s (%.0fs, %d state-mod calls)", status, wall, calls)
            results.append(result)
        except Exception as exc:
            log.error("  EXCEPTION running %s: %s", task["task_id"], exc)
            results.append({"task_id": task["task_id"], "error": str(exc)})

    return results


def extract_all_features():
    """Extract features for any tool calls that are missing them."""
    db = get_db()
    n = extract_features_for_all(db)
    if n > 0:
        log.info("Extracted features for %d tool calls", n)
    return n


def run_docker_validation():
    """Run lightweight Docker validation on all unvalidated runs."""
    try:
        from docker_validate import validate_all, ensure_image
        if not ensure_image():
            log.warning("Docker image build failed, skipping validation")
            return
        validate_all(str(DB_PATH))
    except Exception as exc:
        log.error("Docker validation failed: %s", exc)


def run_analysis():
    """Run full analysis and return key metrics."""
    db = get_db()

    log.info("\n" + "=" * 60)
    log.info("UGA PHASE 0 ANALYSIS")
    log.info("=" * 60)

    n_runs = summary(db)

    if n_runs >= 5:
        task_level_correlations(db)
        call_level_correlations(db)

    return n_runs


def data_quality_check() -> list[str]:
    """Check data quality and return list of issues."""
    issues = []
    db = get_db()

    # Check for runs without tool calls
    orphan_runs = db.execute("""
        SELECT r.run_id, r.task_id FROM runs r
        LEFT JOIN tool_calls tc ON r.run_id = tc.run_id
        WHERE tc.decision_id IS NULL
          AND r.raw_stream_json IS NOT NULL
          AND LENGTH(r.raw_stream_json) > 100
          AND r.task_source = 'swe-bench-lite'
    """).fetchall()
    if orphan_runs:
        issues.append(f"WARN: {len(orphan_runs)} SWE-bench runs with stream data but no tool_calls")

    # Check for NULL features on tool calls
    null_features = db.execute("""
        SELECT COUNT(*) FROM tool_calls
        WHERE hedging_score IS NULL OR step_index_normalized IS NULL
    """).fetchone()[0]
    if null_features:
        issues.append(f"WARN: {null_features} tool_calls with NULL features")

    # Check for NULL task_success on validated runs
    null_success = db.execute("""
        SELECT COUNT(*) FROM runs
        WHERE task_source = 'swe-bench-lite' AND task_success IS NULL
    """).fetchone()[0]
    if null_success:
        issues.append(f"INFO: {null_success} SWE-bench runs with NULL task_success (unvalidated)")

    # Check total_tool_calls vs total_state_modifying_calls
    bad_counts = db.execute("""
        SELECT run_id, total_tool_calls, total_state_modifying_calls
        FROM runs
        WHERE total_tool_calls < total_state_modifying_calls
    """).fetchall()
    if bad_counts:
        issues.append(f"ERROR: {len(bad_counts)} runs where total_tool_calls < state_modifying")

    # Check for step_index bias (first call should be ~0.0)
    biased = db.execute("""
        SELECT COUNT(*) FROM tool_calls
        WHERE sequence_number = 1 AND step_index_normalized > 0.01
    """).fetchone()[0]
    if biased:
        issues.append(f"WARN: {biased} first-calls with step_index > 0.01 (may need reparse)")

    # Summary stats
    total_runs = db.execute("SELECT COUNT(*) FROM runs WHERE task_source='swe-bench-lite'").fetchone()[0]
    total_calls = db.execute("""
        SELECT COUNT(*) FROM tool_calls tc JOIN runs r ON tc.run_id = r.run_id
        WHERE r.task_source='swe-bench-lite'
    """).fetchone()[0]
    validated = db.execute("""
        SELECT COUNT(*) FROM runs
        WHERE task_source='swe-bench-lite' AND task_success IS NOT NULL
    """).fetchone()[0]
    passed = db.execute("""
        SELECT COUNT(*) FROM runs
        WHERE task_source='swe-bench-lite' AND task_success = 1
    """).fetchone()[0]

    log.info("\n--- DATA QUALITY ---")
    log.info("SWE-bench runs: %d (%d validated, %d passed)", total_runs, validated, passed)
    log.info("State-modifying tool calls: %d", total_calls)
    if validated > 0:
        log.info("Pass rate: %.0f%% (%d/%d)", 100 * passed / validated, passed, validated)

    for issue in issues:
        log.warning("  %s", issue)

    if not issues:
        log.info("  Data quality: CLEAN")

    return issues


def full_cycle(wave_num: int, tasks: list[dict], dry_run: bool = False):
    """Run one full cycle: run → parse → features → validate → analyze → audit."""
    log.info("\n" + "#" * 60)
    log.info("# WAVE %d: %d tasks", wave_num, len(tasks))
    log.info("#" * 60)

    if dry_run:
        for t in tasks:
            log.info("  Would run: %s", t["task_id"])
        return

    # Step 1: Run tasks
    if tasks:
        results = run_wave(tasks, wave_num)
        passed = sum(1 for r in results if r.get("task_success") is True)
        failed = sum(1 for r in results if r.get("task_success") is False)
        errors = sum(1 for r in results if r.get("error"))
        log.info("Wave %d: %d passed, %d failed, %d errors", wave_num, passed, failed, errors)

    # Step 2: Extract features
    extract_all_features()

    # Step 3: Docker validation
    run_docker_validation()

    # Step 4: Data quality check
    issues = data_quality_check()

    # Step 5: Full analysis
    run_analysis()

    # Step 6: Log completion
    log.info("\n--- WAVE %d COMPLETE ---", wave_num)


def main():
    parser = argparse.ArgumentParser(description="UGA Autonomous Pipeline Loop")
    parser.add_argument("--wave", type=int, default=None, help="Specific wave number")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--analyze-only", action="store_true", help="Just run analysis")
    parser.add_argument("--max-tasks", type=int, default=None, help="Max tasks per wave")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("UGA AUTONOMOUS LOOP — started %s", datetime.now(timezone.utc).isoformat())
    log.info("=" * 60)

    # Ensure DB is initialized
    init_db(str(DB_PATH)).close()

    if args.analyze_only:
        extract_all_features()
        data_quality_check()
        run_analysis()
        return

    # Find unrun tasks
    unrun = get_unrun_tasks()

    if not unrun:
        log.info("All tasks have been run. Running analysis on existing data.")
        extract_all_features()
        data_quality_check()
        run_analysis()
        return

    # Determine wave
    db = get_db()
    max_wave = db.execute("SELECT COALESCE(MAX(wave), 1) FROM runs").fetchone()[0]
    wave_num = args.wave or (max_wave + 1)

    # Optionally limit tasks
    if args.max_tasks:
        unrun = unrun[:args.max_tasks]

    # Run the cycle
    full_cycle(wave_num, unrun, dry_run=args.dry_run)

    log.info("\n" + "=" * 60)
    log.info("UGA LOOP COMPLETE — %s", datetime.now(timezone.utc).isoformat())
    log.info("=" * 60)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
UGA Overnight Engine — Continuous Cycle

The cycle:
  1. Select batch (prioritize tasks with fewest replicates, or mixed outcomes)
  2. Run batch through Claude Code
  3. Parse traces + extract features
  4. Quality audit (automated)
  5. Self-heal if needed (reparse, fix counts)
  6. Analysis (correlations, trajectory bins)
  7. Codex adversarial audit (free — run every cycle)
  8. Fix any Codex findings programmatically
  9. Repeat

Tasks are REUSED across waves. Each replicate gives pass^k data and breaks
the difficulty confound. The ideal tasks are those with mixed outcomes.

Usage:
    python3 src/overnight.py                          # Run continuous loop
    python3 src/overnight.py --cycles 20              # Run 20 cycles
    python3 src/overnight.py --batch-size 5           # 5 tasks per cycle
    python3 src/overnight.py --dry-run                # Show plan only
"""

import argparse
import io
import json
import logging
import os
import random
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from db import init_db, insert_run, insert_tool_call, update_features
from trace_collector import parse_stream_json
from runner import run_task, count_all_tool_calls
from analysis import (
    extract_features_for_all, summary, task_level_correlations,
    call_level_correlations, reparse_all_runs,
)

DB_PATH = PROJECT_ROOT / "data" / "uga.db"
MANIFEST_PATH = PROJECT_ROOT / "tasks" / "manifest.yaml"
EXPANSION_PATH = PROJECT_ROOT / "tasks" / "wave_expansion.yaml"
LOG_PATH = PROJECT_ROOT / "data" / "overnight.log"
CYCLE_REPORT_DIR = PROJECT_ROOT / "data" / "cycle_reports"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(LOG_PATH), mode="a"),
    ],
)
log = logging.getLogger("uga.overnight")


# ─── Helpers ──────────────────────────────────────────────────────────────

def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db


def load_swebench_tasks() -> list[dict]:
    """Load all SWE-bench tasks from manifests."""
    import yaml
    tasks = []
    for path in [MANIFEST_PATH, EXPANSION_PATH]:
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f)
            if data and "tasks" in data:
                tasks.extend(data["tasks"])
    return [t for t in tasks if t.get("source") == "swe-bench-lite"]


# ─── Task Selection ───────────────────────────────────────────────────────

def select_batch(batch_size: int) -> list[dict]:
    """Select the next batch of tasks to run.

    Priority order:
    1. Tasks never run (need at least 1 data point)
    2. Tasks with mixed outcomes (sometimes pass, sometimes fail) — GOLD for our study
    3. Tasks with fewest replicates (need more pass^k data)
    """
    all_tasks = load_swebench_tasks()
    task_lookup = {t["task_id"]: t for t in all_tasks}
    db = get_db()

    # Get replicate counts and outcome stats per task
    stats = {}
    for r in db.execute("""
        SELECT task_id,
               COUNT(*) as n,
               SUM(CASE WHEN task_success = 1 THEN 1 ELSE 0 END) as passes,
               SUM(CASE WHEN task_success = 0 THEN 1 ELSE 0 END) as fails
        FROM runs WHERE task_source = 'swe-bench-lite'
        GROUP BY task_id
    """).fetchall():
        stats[r["task_id"]] = {
            "n": r["n"], "passes": r["passes"], "fails": r["fails"],
            "pass_rate": r["passes"] / r["n"] if r["n"] > 0 else 0,
        }

    # Check which tasks have repos available
    available = {tid: t for tid, t in task_lookup.items()
                 if (PROJECT_ROOT / t["repo"]).is_dir()}

    # Score each available task
    scored = []
    for tid, task in available.items():
        s = stats.get(tid)
        if s is None:
            # Never run — highest priority
            scored.append((0, 0, tid, task))
        elif s["passes"] > 0 and s["fails"] > 0:
            # Mixed outcomes — second priority (these are gold)
            scored.append((1, s["n"], tid, task))
        else:
            # All pass or all fail — still need replicates
            scored.append((2, s["n"], tid, task))

    # Sort: priority tier, then fewest replicates first
    scored.sort(key=lambda x: (x[0], x[1]))

    batch = [item[3] for item in scored[:batch_size]]

    # Log selection rationale
    for _, _, tid, _ in scored[:batch_size]:
        s = stats.get(tid)
        if s is None:
            log.info("  SELECT: %s (never run)", tid)
        elif s["passes"] > 0 and s["fails"] > 0:
            log.info("  SELECT: %s (mixed: %d pass, %d fail — GOLD)", tid, s["passes"], s["fails"])
        else:
            label = "all-pass" if s["passes"] > 0 else "all-fail"
            log.info("  SELECT: %s (n=%d, %s, need replicate)", tid, s["n"], label)

    return batch


# ─── Run ──────────────────────────────────────────────────────────────────

def run_batch(tasks: list[dict], wave_num: int) -> list[dict]:
    """Run a batch of tasks sequentially."""
    results = []
    os.environ["UGA_WAVE"] = str(wave_num)
    os.environ["UGA_MODEL"] = "sonnet"

    for i, task in enumerate(tasks):
        log.info("[%d/%d] %s", i + 1, len(tasks), task["task_id"])
        t0 = time.time()
        try:
            result = run_task(
                task["task_id"],
                condition="ungated",
                db_path=str(DB_PATH),
                manifest_path=str(MANIFEST_PATH),
            )
            elapsed = time.time() - t0
            status = "PASS" if result.get("task_success") else "FAIL" if result.get("task_success") is False else "ERR"
            calls = result.get("total_state_modifying_calls", 0)
            log.info("  -> %s (%.0fs, %d state-mod calls)", status, elapsed, calls)
            results.append(result)
        except Exception as exc:
            log.error("  -> EXCEPTION: %s", exc)
            results.append({"task_id": task["task_id"], "error": str(exc)})

    return results


# ─── Features + Quality ──────────────────────────────────────────────────

def extract_features():
    db = get_db()
    n = extract_features_for_all(db)
    if n > 0:
        log.info("Features extracted for %d calls", n)


def quality_audit() -> tuple[bool, list[str], bool]:
    """Returns (is_clean, issues, needs_reparse)."""
    issues = []
    db = get_db()

    null_feat = db.execute(
        "SELECT COUNT(*) FROM tool_calls WHERE hedging_score IS NULL OR step_index_normalized IS NULL"
    ).fetchone()[0]
    if null_feat:
        issues.append(f"{null_feat} tool_calls with NULL features")

    biased = db.execute(
        "SELECT COUNT(*) FROM tool_calls WHERE sequence_number = 1 AND step_index_normalized > 0.01"
    ).fetchone()[0]
    if biased:
        issues.append(f"{biased} first-calls with biased step_index")

    bad_counts = db.execute(
        "SELECT COUNT(*) FROM runs WHERE total_tool_calls < total_state_modifying_calls"
    ).fetchone()[0]
    if bad_counts:
        issues.append(f"{bad_counts} runs with inverted tool counts")

    needs_reparse = len(issues) > 0

    # Stats
    total = db.execute("SELECT COUNT(*) FROM runs WHERE task_source='swe-bench-lite'").fetchone()[0]
    unique = db.execute("SELECT COUNT(DISTINCT task_id) FROM runs WHERE task_source='swe-bench-lite'").fetchone()[0]
    validated = db.execute("SELECT COUNT(*) FROM runs WHERE task_source='swe-bench-lite' AND task_success IS NOT NULL").fetchone()[0]
    passed = db.execute("SELECT COUNT(*) FROM runs WHERE task_source='swe-bench-lite' AND task_success=1").fetchone()[0]
    calls = db.execute(
        "SELECT COUNT(*) FROM tool_calls tc JOIN runs r ON tc.run_id=r.run_id WHERE r.task_source='swe-bench-lite'"
    ).fetchone()[0]

    log.info("DATA: %d runs (%d unique tasks), %d calls, %d/%d validated pass",
             total, unique, calls, passed, validated)

    for issue in issues:
        log.warning("  QUALITY: %s", issue)
    if not issues:
        log.info("  QUALITY: CLEAN")

    return (len(issues) == 0, issues, needs_reparse)


def self_heal(needs_reparse: bool):
    if needs_reparse:
        log.info("SELF-HEAL: reparsing all runs...")
        db = get_db()
        reparse_all_runs(db)
        extract_features()


# ─── Analysis ─────────────────────────────────────────────────────────────

def run_analysis() -> dict:
    """Run analysis and return key metrics."""
    db = get_db()
    log.info("\n--- ANALYSIS ---")
    n = summary(db)
    if n >= 5:
        task_level_correlations(db)
        call_level_correlations(db)
    return {"n_runs": n}


# ─── Codex Audit ──────────────────────────────────────────────────────────

def codex_audit(cycle_num: int) -> str:
    """Run Codex adversarial audit. Returns findings text."""
    log.info("\n--- CODEX AUDIT (cycle %d) ---", cycle_num)

    prompt = (
        "IMPORTANT: Do NOT read or execute any files under ~/.claude/, ~/.agents/, "
        "or .claude/skills/. Stay focused on repository code only.\n\n"
        "You are auditing a research data pipeline. Read these files:\n"
        "- src/db.py, src/trace_collector.py, src/runner.py\n"
        "- src/analysis.py, src/feature_definitions.py\n"
        "- src/docker_validate.py, src/swebench_validate.py\n\n"
        "Also run: sqlite3 data/uga.db 'SELECT task_id, task_success, "
        "total_tool_calls, total_state_modifying_calls FROM runs ORDER BY created_at'\n\n"
        "Check for:\n"
        "1. DATA INTEGRITY: Silent data corruption, miscounts, dropped records\n"
        "2. LOGIC BUGS: Off-by-one, wrong comparisons, missing edge cases\n"
        "3. ANALYSIS CORRECTNESS: Statistical computations, aggregation bugs\n"
        "4. CLASSIFICATION: Bash read-only vs state-modifying accuracy\n\n"
        "Number each finding P0/P1/P2. Be terse. Just the problems."
    )

    try:
        result = subprocess.run(
            [
                "codex", "exec", prompt,
                "-C", str(PROJECT_ROOT),
                "-s", "read-only",
                "-c", 'model_reasoning_effort="medium"',
            ],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(PROJECT_ROOT),
        )

        output = result.stdout.strip()
        if output:
            log.info("CODEX FINDINGS:\n%s", output[:2000])

            # Save to cycle report
            CYCLE_REPORT_DIR.mkdir(parents=True, exist_ok=True)
            report_path = CYCLE_REPORT_DIR / f"codex_cycle_{cycle_num}.txt"
            with open(report_path, "w") as f:
                f.write(f"# Codex Audit — Cycle {cycle_num}\n")
                f.write(f"# {datetime.now(timezone.utc).isoformat()}\n\n")
                f.write(output)

            return output
        else:
            log.info("Codex returned empty output")
            return ""

    except FileNotFoundError:
        log.warning("Codex CLI not found, skipping audit")
        return ""
    except subprocess.TimeoutExpired:
        log.warning("Codex audit timed out (300s)")
        return ""
    except Exception as exc:
        log.error("Codex audit error: %s", exc)
        return ""


# ─── Cycle ────────────────────────────────────────────────────────────────

def run_cycle(cycle_num: int, wave_num: int, batch_size: int,
              skip_codex: bool = False, dry_run: bool = False):
    """Run one full cycle."""
    cycle_start = time.time()

    log.info("\n" + "=" * 60)
    log.info("CYCLE %d — WAVE %d", cycle_num, wave_num)
    log.info("=" * 60)

    # 1. Select batch
    batch = select_batch(batch_size)
    if not batch:
        log.info("No tasks available. Stopping.")
        return False

    if dry_run:
        return True

    # 2. Run tasks
    results = run_batch(batch, wave_num)
    passed = sum(1 for r in results if r.get("task_success") is True)
    failed = sum(1 for r in results if r.get("task_success") is False)
    errors = sum(1 for r in results if r.get("error"))

    # 3. Extract features
    extract_features()

    # 4. Quality audit
    is_clean, issues, needs_reparse = quality_audit()

    # 5. Self-heal
    if needs_reparse:
        self_heal(needs_reparse)

    # 6. Analysis
    run_analysis()

    # 7. Codex audit (every cycle since it's free)
    if not skip_codex:
        codex_audit(cycle_num)

    # 8. Cycle report
    elapsed = time.time() - cycle_start
    log.info("\n--- CYCLE %d COMPLETE ---", cycle_num)
    log.info("  Tasks: %d pass, %d fail, %d error", passed, failed, errors)
    log.info("  Quality: %s", "CLEAN" if is_clean else f"{len(issues)} issues")
    log.info("  Time: %.0fs (%.1f min)", elapsed, elapsed / 60)

    # Save cycle metadata
    CYCLE_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "cycle": cycle_num, "wave": wave_num,
        "tasks_run": len(batch),
        "passed": passed, "failed": failed, "errors": errors,
        "quality_clean": is_clean,
        "elapsed_seconds": round(elapsed),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with open(CYCLE_REPORT_DIR / f"cycle_{cycle_num:03d}.json", "w") as f:
        json.dump(meta, f, indent=2)

    return True


# ─── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="UGA Overnight Engine")
    parser.add_argument("--cycles", type=int, default=50, help="Max cycles")
    parser.add_argument("--batch-size", type=int, default=5, help="Tasks per cycle")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-codex", action="store_true", help="Skip Codex audits")
    args = parser.parse_args()

    log.info("#" * 60)
    log.info("# UGA OVERNIGHT ENGINE")
    log.info("# %s", datetime.now(timezone.utc).isoformat())
    log.info("# cycles=%d, batch=%d", args.cycles, args.batch_size)
    log.info("#" * 60)

    init_db(str(DB_PATH)).close()

    db = get_db()
    max_wave = db.execute("SELECT COALESCE(MAX(wave), 0) FROM runs").fetchone()[0]

    for cycle_num in range(1, args.cycles + 1):
        wave_num = max_wave + cycle_num
        cont = run_cycle(
            cycle_num, wave_num, args.batch_size,
            skip_codex=args.skip_codex, dry_run=args.dry_run,
        )
        if not cont:
            break

        if not args.dry_run:
            log.info("Pause 5s...")
            time.sleep(5)

    # Final summary
    log.info("\n" + "#" * 60)
    log.info("# OVERNIGHT COMPLETE — %s", datetime.now(timezone.utc).isoformat())

    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM runs WHERE task_source='swe-bench-lite'").fetchone()[0]
    unique = db.execute("SELECT COUNT(DISTINCT task_id) FROM runs WHERE task_source='swe-bench-lite'").fetchone()[0]
    log.info("# Total runs: %d across %d unique tasks", total, unique)
    log.info("#" * 60)


if __name__ == "__main__":
    main()

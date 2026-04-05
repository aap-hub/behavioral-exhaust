#!/usr/bin/env python3
"""
UGA Phase 1 Protocol — The Gating Experiment

3x2 + baseline + perturbation design testing whether behavioral gates
improve agent task success.

Conditions:
  C0 — Ungated baseline (same as Phase 0)
  A1 — Early introspective gate
  A2 — Early extrospective gate
  A3 — Early both gates
  B1 — Always introspective gate
  B2 — Always extrospective gate
  B3 — Always both gates
  P1 — Prompt: "always state which file you plan to edit"
  P2 — Adversarial: "your edits will be reviewed"
  P3 — Retroactive critic on Phase 0 data (no new runs)

Design note:
  The introspective gate conditions (A1, B1, A3, B3) and extrospective
  conditions (A2, B2) are applied POST-HOC to existing Phase 0 runs.
  This is a methodological strength: we measure what the gate WOULD HAVE
  done on the exact same trajectories, eliminating between-run variance.

  P1 and P2 require new runs (modified prompt). P3 uses existing data.
  C0 uses existing Phase 0 data.

Usage:
    python3 src/phase1_protocol.py run --condition A1     # Apply gate to all runs
    python3 src/phase1_protocol.py run --condition P1     # New runs with prompt mod
    python3 src/phase1_protocol.py run-all                # All post-hoc conditions
    python3 src/phase1_protocol.py analyze                # Compare conditions
    python3 src/phase1_protocol.py status                 # Show progress
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from db import init_db
from gate import (
    GateConfig, CONDITION_MAP,
    compute_thresholds_from_db, save_config,
    init_gate_decisions_table,
    get_gate_for_condition, get_timing_for_condition,
    CONFIG_PATH,
)
from gated_runner import (
    apply_gate_to_all_runs, apply_gate_posthoc,
    compute_gate_metrics, run_task_with_prompt_mod,
)

DB_PATH = PROJECT_ROOT / "data" / "uga.db"
PROTOCOL_FILE = PROJECT_ROOT / "data" / "protocol_tasks.json"
RESULTS_DIR = PROJECT_ROOT / "data" / "results"

log = logging.getLogger("uga.phase1")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Conditions that can be applied post-hoc (no new runs needed)
POSTHOC_CONDITIONS = ["A1", "A2", "A3", "B1", "B2", "B3"]

# Conditions that require new agent runs
NEW_RUN_CONDITIONS = ["P1", "P2"]

# No-run conditions
NOOP_CONDITIONS = ["C0", "P3"]


# ===================================================================
# Task loading
# ===================================================================

def load_protocol_tasks() -> list[str]:
    """Load the locked set of 71 protocol tasks."""
    if not PROTOCOL_FILE.exists():
        log.error("Protocol tasks file not found: %s", PROTOCOL_FILE)
        sys.exit(1)
    with open(PROTOCOL_FILE) as f:
        protocol = json.load(f)
    return protocol["tasks"]


# ===================================================================
# Phase 1 setup: compute and lock thresholds
# ===================================================================

def setup_phase1(db_path: str = str(DB_PATH)) -> GateConfig:
    """Compute gate thresholds from Phase 0 data and save config.

    This should be run ONCE before any Phase 1 analysis.
    Thresholds are locked in data/phase1_config.json.
    """
    if CONFIG_PATH.exists():
        log.info("Config already exists at %s. Loading.", CONFIG_PATH)
        return GateConfig.from_file()

    log.info("Computing thresholds from Phase 0 data...")
    config = compute_thresholds_from_db(db_path)
    save_config(config)
    log.info("Thresholds locked: %s", config.to_dict())
    return config


# ===================================================================
# Run a single condition
# ===================================================================

def run_condition(
    condition_code: str,
    tasks: list[str] | None = None,
    db_path: str = str(DB_PATH),
) -> dict:
    """Run all tasks for a specific condition.

    For post-hoc conditions (A1-B3): apply gate to existing runs.
    For new-run conditions (P1, P2): run tasks with modified prompts.
    For C0: no action (use existing Phase 0 data).
    For P3: run retroactive critic.

    Args:
        condition_code: One of C0, A1-A3, B1-B3, P1-P3.
        tasks: Task IDs to process (default: all 71 protocol tasks).
        db_path: Database path.

    Returns:
        Summary dict with condition results.
    """
    tasks = tasks or load_protocol_tasks()
    config = setup_phase1(db_path)

    log.info("=" * 60)
    log.info("CONDITION %s: %s", condition_code,
             CONDITION_MAP.get(condition_code, {}))
    log.info("=" * 60)

    if condition_code == "C0":
        return _run_baseline(tasks, db_path)
    elif condition_code == "P3":
        return _run_p3(db_path)
    elif condition_code in POSTHOC_CONDITIONS:
        return _run_posthoc(condition_code, tasks, db_path, config)
    elif condition_code in NEW_RUN_CONDITIONS:
        return _run_new(condition_code, tasks, db_path)
    else:
        raise ValueError(f"Unknown condition: {condition_code}")


def _run_baseline(tasks: list[str], db_path: str) -> dict:
    """C0: Just report Phase 0 results as baseline."""
    db = init_db(db_path)

    task_list_sql = ",".join(f"'{t}'" for t in tasks)
    row = db.execute(f"""
        SELECT COUNT(*) as n,
               SUM(CASE WHEN task_success=1 THEN 1 ELSE 0 END) as pass_count,
               SUM(CASE WHEN task_success=0 THEN 1 ELSE 0 END) as fail_count
        FROM runs
        WHERE task_id IN ({task_list_sql})
          AND validation_source IS NOT NULL
          AND task_success IS NOT NULL
    """).fetchone()
    db.close()

    n = row["n"]
    pass_rate = row["pass_count"] / n if n > 0 else 0

    result = {
        "condition": "C0",
        "description": "Ungated baseline (Phase 0)",
        "total_runs": n,
        "pass_count": row["pass_count"],
        "fail_count": row["fail_count"],
        "pass_rate": round(pass_rate, 4),
    }

    log.info("C0 Baseline: %d runs, %.1f%% pass rate", n, pass_rate * 100)
    return result


def _run_posthoc(
    condition_code: str,
    tasks: list[str],
    db_path: str,
    config: GateConfig,
) -> dict:
    """Apply gate post-hoc to existing validated runs."""
    all_decisions = apply_gate_to_all_runs(
        condition_code,
        db_path=db_path,
        config=config,
        task_filter=tasks,
    )

    # Compute metrics
    metrics = compute_gate_metrics(condition_code, db_path)

    total = sum(len(ds) for ds in all_decisions.values())
    blocked = sum(1 for ds in all_decisions.values() for d in ds if d.verdict == "block")

    result = {
        "condition": condition_code,
        "description": str(CONDITION_MAP.get(condition_code, {})),
        "total_runs": len(all_decisions),
        "total_gate_decisions": total,
        "blocked": blocked,
        "block_rate": round(blocked / total, 4) if total > 0 else 0.0,
        "metrics": metrics,
    }

    log.info(
        "%s: %d runs, %d decisions, %d blocked (%.1f%%)",
        condition_code, len(all_decisions), total, blocked,
        (blocked / total * 100) if total > 0 else 0,
    )
    return result


def _run_new(
    condition_code: str,
    tasks: list[str],
    db_path: str,
) -> dict:
    """Run tasks with modified prompts (P1, P2)."""
    results_list = []
    for i, task_id in enumerate(tasks):
        log.info("[%d/%d] %s condition=%s", i + 1, len(tasks), task_id, condition_code)
        try:
            result = run_task_with_prompt_mod(task_id, condition_code, db_path)
            results_list.append(result)
            status = "PASS" if result.get("task_success") else "FAIL"
            log.info("  %s: %s (%.0fs)", task_id, status,
                    result.get("wall_clock_seconds", 0))
        except Exception as exc:
            log.error("  %s: ERROR %s", task_id, exc)
            results_list.append({"task_id": task_id, "error": str(exc)})

    pass_count = sum(1 for r in results_list if r.get("task_success") is True)
    fail_count = sum(1 for r in results_list if r.get("task_success") is False)

    result = {
        "condition": condition_code,
        "description": f"Perturbation {condition_code}",
        "total_runs": len(results_list),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "pass_rate": round(pass_count / len(results_list), 4) if results_list else 0.0,
        "errors": sum(1 for r in results_list if r.get("error")),
    }
    return result


def _run_p3(db_path: str) -> dict:
    """P3: Retroactive critic on Phase 0 data."""
    from critic import run_retroactive_critic, analyze_retroactive_critic

    results = run_retroactive_critic(db_path=db_path)
    analysis = analyze_retroactive_critic(results)

    # Save results
    os.makedirs(str(RESULTS_DIR), exist_ok=True)
    out_path = RESULTS_DIR / "p3_retroactive_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    result = {
        "condition": "P3",
        "description": "Retroactive critic on Phase 0 data",
        "total_calls_evaluated": len(results),
        "analysis": analysis,
    }
    log.info("P3: %d calls evaluated. Precision=%.3f, Recall=%.3f",
             len(results), analysis.get("precision", 0), analysis.get("recall", 0))
    return result


# ===================================================================
# Run all conditions
# ===================================================================

def run_all(db_path: str = str(DB_PATH)) -> dict:
    """Run all Phase 1 conditions.

    Order:
    1. Setup (compute thresholds)
    2. C0 (baseline — just report)
    3. A1-A3, B1-B3 (post-hoc — fast, no new runs)
    4. P3 (retroactive critic — no new runs, but calls claude -p per edit)
    5. P1, P2 (new runs — slow, 71 tasks each)
    """
    tasks = load_protocol_tasks()
    config = setup_phase1(db_path)

    all_results = {}

    # Baseline
    log.info("\n=== C0: BASELINE ===")
    all_results["C0"] = run_condition("C0", tasks, db_path)

    # Post-hoc conditions (fast)
    for cond in POSTHOC_CONDITIONS:
        log.info("\n=== %s: POST-HOC GATE ===", cond)
        all_results[cond] = run_condition(cond, tasks, db_path)

    # P3 retroactive critic
    log.info("\n=== P3: RETROACTIVE CRITIC ===")
    all_results["P3"] = run_condition("P3", tasks, db_path)

    # P1, P2 new runs (optional, expensive)
    for cond in NEW_RUN_CONDITIONS:
        log.info("\n=== %s: NEW RUNS ===", cond)
        all_results[cond] = run_condition(cond, tasks, db_path)

    # Save all results
    os.makedirs(str(RESULTS_DIR), exist_ok=True)
    out_path = RESULTS_DIR / "phase1_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    log.info("All results saved to %s", out_path)

    return all_results


# ===================================================================
# Analysis
# ===================================================================

def analyze(db_path: str = str(DB_PATH)) -> dict:
    """Compare pass rates and gate metrics across conditions.

    Tests:
    H1: Any gated condition > C0 (ungated baseline)
    H2: Early gate (A*) ~ Always gate (B*)
    H3: Both gates (A3/B3) > either alone
    H4: Extrospective adds value beyond introspective

    Since we're doing post-hoc analysis, "pass rate" for gated conditions
    means: what would the pass rate be if we blocked the agent and gave it
    another chance? We can't know that without live gating.

    What we CAN measure:
    - Gate precision: when it blocks, was the run actually failing?
    - Gate recall: of failing runs, how many had at least one blocked call?
    - Block rate: what fraction of Edit/Write calls would be blocked?
    - Feature tracking: do Phase 0 features still predict within gated data?
    """
    db = init_db(db_path)
    init_gate_decisions_table(db)

    results = {}

    # C0 baseline
    baseline = _run_baseline(load_protocol_tasks(), db_path)
    results["C0"] = baseline

    # Gate metrics for each condition
    for cond in POSTHOC_CONDITIONS:
        metrics = compute_gate_metrics(cond, db_path)
        results[cond] = metrics

    # Summary comparison
    print("\n" + "=" * 70)
    print("PHASE 1 ANALYSIS — GATE COMPARISON")
    print("=" * 70)

    print(f"\n{'Condition':<12} {'Decisions':>10} {'Blocked':>10} {'Block%':>8} "
          f"{'Prec':>8} {'Recall':>8} {'F1':>8}")
    print("-" * 70)

    # Baseline
    print(f"{'C0 (base)':<12} {'n/a':>10} {'n/a':>10} {'n/a':>8} "
          f"{'n/a':>8} {'n/a':>8} {'n/a':>8}")

    for cond in POSTHOC_CONDITIONS:
        m = results.get(cond, {})
        if "error" in m:
            print(f"{cond:<12} {'ERROR':>10} {m['error']}")
            continue
        conf = m.get("confusion", {})
        total = m.get("total_decisions", 0)
        blocked = conf.get("tp", 0) + conf.get("fp", 0)
        print(f"{cond:<12} {total:>10} {blocked:>10} "
              f"{m.get('block_rate', 0)*100:>7.1f}% "
              f"{m.get('precision', 0):>8.3f} "
              f"{m.get('recall', 0):>8.3f} "
              f"{m.get('f1', 0):>8.3f}")

    # Hypothesis tests
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTS")
    print("=" * 70)

    # H1: Any gated condition has better precision than random?
    for cond in POSTHOC_CONDITIONS:
        m = results.get(cond, {})
        if isinstance(m, dict) and "precision" in m:
            prec = m["precision"]
            # Random precision = base_fail_rate (if you block random calls,
            # P(run is failing) = overall fail rate)
            base_fail = baseline["fail_count"] / baseline["total_runs"] if baseline["total_runs"] > 0 else 0.5
            improvement = prec - base_fail
            print(f"  H1 {cond}: precision={prec:.3f} vs random={base_fail:.3f} "
                  f"(delta={improvement:+.3f})")

    # H2: Early vs Always
    for pair in [("A1", "B1"), ("A2", "B2"), ("A3", "B3")]:
        early = results.get(pair[0], {})
        always = results.get(pair[1], {})
        if "f1" in early and "f1" in always:
            print(f"  H2 {pair[0]} vs {pair[1]}: "
                  f"F1 early={early['f1']:.3f} vs always={always['f1']:.3f}")

    # H3: Both > either alone
    for timing in ["A", "B"]:
        intro = results.get(f"{timing}1", {})
        extro = results.get(f"{timing}2", {})
        both = results.get(f"{timing}3", {})
        if all("f1" in m for m in [intro, extro, both]):
            print(f"  H3 {timing}3 vs {timing}1+{timing}2: "
                  f"both={both['f1']:.3f} vs intro={intro['f1']:.3f}, "
                  f"extro={extro['f1']:.3f}")

    # H4: Extrospective adds value
    for timing in ["A", "B"]:
        intro = results.get(f"{timing}1", {})
        extro = results.get(f"{timing}2", {})
        if "f1" in intro and "f1" in extro:
            delta = extro["f1"] - intro["f1"]
            print(f"  H4 {timing}2 vs {timing}1: "
                  f"extro F1={extro['f1']:.3f}, intro F1={intro['f1']:.3f} "
                  f"(delta={delta:+.3f})")

    # Save analysis
    os.makedirs(str(RESULTS_DIR), exist_ok=True)
    out_path = RESULTS_DIR / "phase1_analysis.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nAnalysis saved to {out_path}")

    db.close()
    return results


# ===================================================================
# Status
# ===================================================================

def status(db_path: str = str(DB_PATH)):
    """Show Phase 1 experiment progress."""
    db = init_db(db_path)

    print("=" * 60)
    print("UGA PHASE 1 STATUS")
    print("=" * 60)

    # Config
    if CONFIG_PATH.exists():
        config = GateConfig.from_file()
        print(f"\nGate config: {config.to_dict()}")
    else:
        print("\nGate config: NOT YET COMPUTED")
        print("  Run: python3 src/phase1_protocol.py setup")

    # Baseline data
    tasks = load_protocol_tasks()
    task_list_sql = ",".join(f"'{t}'" for t in tasks)
    row = db.execute(f"""
        SELECT COUNT(*) as n,
               SUM(CASE WHEN task_success=1 THEN 1 ELSE 0 END) as p,
               SUM(CASE WHEN task_success=0 THEN 1 ELSE 0 END) as f
        FROM runs
        WHERE task_id IN ({task_list_sql})
          AND validation_source IS NOT NULL
          AND task_success IS NOT NULL
    """).fetchone()
    print(f"\nBaseline (C0): {row['n']} validated runs "
          f"({row['p']} pass, {row['f']} fail, "
          f"{row['p']/row['n']*100:.0f}% rate)" if row["n"] > 0 else "\nNo baseline data")

    # Gate decisions per condition
    try:
        init_gate_decisions_table(db)
        gate_rows = db.execute("""
            SELECT gate_type, gate_timing, verdict, COUNT(*) as n
            FROM gate_decisions
            GROUP BY gate_type, gate_timing, verdict
            ORDER BY gate_type, gate_timing, verdict
        """).fetchall()

        if gate_rows:
            print("\nGate decisions:")
            current_key = None
            for gr in gate_rows:
                key = f"  {gr['gate_type']}|{gr['gate_timing']}"
                if key != current_key:
                    current_key = key
                    print(f"\n{key}:")
                print(f"    {gr['verdict']}: {gr['n']}")
        else:
            print("\nNo gate decisions recorded yet.")
    except Exception:
        print("\nGate decisions table not yet created.")

    # P1/P2 runs
    for cond in ["P1", "P2"]:
        row = db.execute("""
            SELECT COUNT(*) as n,
                   SUM(CASE WHEN task_success=1 THEN 1 ELSE 0 END) as p
            FROM runs WHERE condition = ?
        """, (cond,)).fetchone()
        if row["n"] > 0:
            print(f"\n{cond} runs: {row['n']} ({row['p']} pass)")

    # P3 results
    p3_path = RESULTS_DIR / "p3_retroactive_results.json"
    if p3_path.exists():
        with open(p3_path) as f:
            p3 = json.load(f)
        print(f"\nP3 retroactive critic: {len(p3)} calls evaluated")

    db.close()


# ===================================================================
# CLI
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description="UGA Phase 1 Protocol — Gating Experiment",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Setup
    sub.add_parser("setup", help="Compute and lock gate thresholds")

    # Run single condition
    run_p = sub.add_parser("run", help="Run a single condition")
    run_p.add_argument("--condition", required=True, choices=list(CONDITION_MAP.keys()) + ["P3"])

    # Run all conditions
    sub.add_parser("run-all", help="Run all conditions sequentially")

    # Analysis
    sub.add_parser("analyze", help="Compare conditions and test hypotheses")

    # Status
    sub.add_parser("status", help="Show experiment progress")

    args = parser.parse_args()

    if args.command == "setup":
        config = setup_phase1()
        print(f"Thresholds: {config.to_dict()}")

    elif args.command == "run":
        result = run_condition(args.condition)
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "run-all":
        results = run_all()
        for cond, res in results.items():
            print(f"\n{cond}: {json.dumps(res, indent=2, default=str)}")

    elif args.command == "analyze":
        analyze()

    elif args.command == "status":
        status()


if __name__ == "__main__":
    main()

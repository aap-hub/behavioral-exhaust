"""
UGA Analysis Pipeline — Phase 0

Computes the interaction matrix, feature correlations, and summary statistics
from the SQLite database. Produces plots and tables for the memo.

Usage:
    python src/analysis.py                # Full Phase 0 analysis
    python src/analysis.py --summary      # Quick summary only
"""

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = _PROJECT_ROOT / "data" / "uga.db"
RESULTS_DIR = _PROJECT_ROOT / "data" / "results"
LEXICON_PATH = _PROJECT_ROOT / "src" / "lexicons" / "hyland_hedges.json"

# Trajectory bins from design doc
BINS = {
    'early': (1, 3),
    'mid': (4, 7),
    'late': (8, float('inf')),
}

H0_RHO_THRESHOLD = 0.2
MIN_CELL_SIZE = 15


def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db


def assign_bin(seq_num):
    for name, (lo, hi) in BINS.items():
        if lo <= seq_num <= hi:
            return name
    return 'late'


def extract_features_for_all(db):
    """Extract and store ALL features (Tier 0 + Tier 1) for tool calls missing them.

    Tier 0 features require run-level context (position in trajectory, prior
    results, tool switches), so we process all calls per run in sequence.
    """
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))
    from feature_definitions import (
        extract_all_tier1,
        extract_step_index_normalized, extract_prior_failure_streak,
        extract_retry_count, extract_tool_switch_rate,
    )
    from db import update_features

    with open(LEXICON_PATH) as f:
        lexicon = json.load(f)

    # Find all calls that need feature extraction (missing any core feature)
    calls_needing = db.execute(
        "SELECT decision_id, run_id FROM tool_calls "
        "WHERE hedging_score IS NULL OR step_index_normalized IS NULL "
        "   OR verification_score IS NULL"
    ).fetchall()

    if not calls_needing:
        return 0

    # Collect unique run_ids that need processing
    run_ids = list({c['run_id'] for c in calls_needing})
    total_updated = 0

    for run_id in run_ids:
        # Get all calls for this run in order
        run_calls = db.execute(
            "SELECT decision_id, sequence_number, tool_name, tool_params_json, "
            "       tool_result_json, reasoning_text "
            "FROM tool_calls WHERE run_id = ? ORDER BY sequence_number",
            (run_id,)
        ).fetchall()

        total_calls = len(run_calls)

        for i, c in enumerate(run_calls):
            text = c['reasoning_text'] or ''
            tool_name = c['tool_name'] or ''

            # --- Tier 0: structural features ---
            # step_index_normalized
            step_idx = extract_step_index_normalized(c['sequence_number'], total_calls)

            # prior_failure_streak: check is_error in preceding tool results
            # Codex #G: missing/unparseable results are treated as failure
            # (conservative: assume failure when unknown, don't reset streak)
            prev_results = []
            for prev in run_calls[:i]:
                result_json = prev['tool_result_json']
                if result_json:
                    try:
                        result = json.loads(result_json)
                        # is_error=True means failure
                        prev_results.append(not result.get('is_error', False))
                    except (json.JSONDecodeError, AttributeError):
                        prev_results.append(False)  # assume failure if unparseable
                else:
                    prev_results.append(False)  # assume failure if missing
            failure_streak = extract_prior_failure_streak(prev_results)

            # retry_count: same (tool_name, file_target) pair in prior calls
            # Extract file target from params
            # Codex #L: Use full command string (not truncated at 80 chars)
            tool_target = ''
            if c['tool_params_json']:
                try:
                    params = json.loads(c['tool_params_json'])
                    tool_target = (params.get('file_path') or params.get('path')
                                   or params.get('command', '') or '')
                except (json.JSONDecodeError, AttributeError):
                    pass

            prior_calls_for_retry = []
            for prev in run_calls[:i]:
                prev_target = ''
                if prev['tool_params_json']:
                    try:
                        pp = json.loads(prev['tool_params_json'])
                        prev_target = (pp.get('file_path') or pp.get('path')
                                       or pp.get('command', '') or '')
                    except (json.JSONDecodeError, AttributeError):
                        pass
                prior_calls_for_retry.append({
                    'tool_name': prev['tool_name'],
                    'tool_target': prev_target,
                })
            retry = extract_retry_count(tool_name, tool_target, prior_calls_for_retry)

            # tool_switch_rate: from recent tool names
            recent_names = [prev['tool_name'] for prev in run_calls[max(0, i-4):i+1]]
            switch_rate = extract_tool_switch_rate(recent_names)

            # --- Tier 1: linguistic features ---
            tier1 = extract_all_tier1(text, lexicon)

            # Merge all features
            features = {
                'step_index_normalized': step_idx,
                'prior_failure_streak': failure_streak,
                'retry_count': retry,
                'tool_switch_rate': switch_rate,
                **tier1,
            }

            update_features(db, c['decision_id'], features)
            total_updated += 1

    return total_updated


def summary(db):
    """Print quick summary of data state."""
    # Only use independently validated labels (not runner's ad-hoc validation)
    _FILTER = ("r.model_version = 'sonnet' AND r.task_source = 'swe-bench-lite'"
               " AND r.validation_source IS NOT NULL")

    runs = db.execute(
        f"SELECT COUNT(*), SUM(task_success), SUM(CASE WHEN task_success=0 THEN 1 ELSE 0 END) "
        f"FROM runs r WHERE {_FILTER}"
    ).fetchone()

    calls = db.execute(
        f"SELECT COUNT(*) FROM tool_calls tc JOIN runs r ON tc.run_id=r.run_id "
        f"WHERE {_FILTER}"
    ).fetchone()

    with_text = db.execute(
        f"SELECT COUNT(*) FROM tool_calls tc JOIN runs r ON tc.run_id=r.run_id "
        f"WHERE {_FILTER} AND tc.reasoning_token_count > 0"
    ).fetchone()

    with_hedging = db.execute(
        f"SELECT COUNT(*) FROM tool_calls tc JOIN runs r ON tc.run_id=r.run_id "
        f"WHERE {_FILTER} AND tc.hedging_score > 0"
    ).fetchone()

    print(f"Runs:        {runs[0]} ({runs[1]} pass, {runs[2]} fail)")
    print(f"Tool calls:  {calls[0]} ({with_text[0]} with reasoning, {with_hedging[0]} with hedging)")
    return runs[0]


def task_level_correlations(db):
    """Compute task-level feature correlations with success."""
    # Issue #6 fix: aggregate by run_id (not task_id) to avoid conflating
    # multiple runs of the same task. Then pick latest run per task for
    # task-level stats.
    # Issue #8 fix: filter to swe-bench-lite only (excludes synthetic phase -1)
    calls = db.execute("""
        SELECT tc.hedging_score, tc.deliberation_length, tc.alternatives_considered,
               tc.backtrack_count, tc.verification_score, tc.planning_score,
               tc.sequence_number, r.task_success, r.task_id, r.run_id,
               r.total_tool_calls, r.created_at
        FROM tool_calls tc JOIN runs r ON tc.run_id = r.run_id
        WHERE r.model_version = 'sonnet'
          AND r.task_source = 'swe-bench-lite'
          AND r.validation_source IS NOT NULL
          AND tc.hedging_score IS NOT NULL
          AND r.task_success IS NOT NULL
    """).fetchall()

    # Aggregate by run_id first (each run is independent)
    runs_agg = {}
    for c in calls:
        rid = c['run_id']
        if rid not in runs_agg:
            runs_agg[rid] = {
                'task_id': c['task_id'],
                'success': c['task_success'],
                'total_calls': c['total_tool_calls'],
                'created_at': c['created_at'],
                'hedging_sum': 0, 'hedging_max': 0,
                'delib_sum': 0, 'delib_max': 0,
                'alts_sum': 0, 'back_sum': 0,
                'verif_sum': 0, 'verif_max': 0,
                'plan_sum': 0, 'plan_max': 0,
                'calls_with_reasoning': 0,
            }
        t = runs_agg[rid]
        t['hedging_sum'] += c['hedging_score'] or 0
        t['hedging_max'] = max(t['hedging_max'], c['hedging_score'] or 0)
        t['delib_sum'] += c['deliberation_length'] or 0
        t['delib_max'] = max(t['delib_max'], c['deliberation_length'] or 0)
        t['alts_sum'] += c['alternatives_considered'] or 0
        t['back_sum'] += c['backtrack_count'] or 0
        t['verif_sum'] += c['verification_score'] or 0
        t['verif_max'] = max(t['verif_max'], c['verification_score'] or 0)
        t['plan_sum'] += c['planning_score'] or 0
        t['plan_max'] = max(t['plan_max'], c['planning_score'] or 0)
        if (c['deliberation_length'] or 0) > 0:
            t['calls_with_reasoning'] += 1

    # Pick latest run per task_id (deduplicate)
    tasks = {}
    for rid, r in runs_agg.items():
        tid = r['task_id']
        if tid not in tasks or r['created_at'] > tasks[tid]['created_at']:
            tasks[tid] = r

    if len(tasks) < 5:
        print(f"Only {len(tasks)} tasks — need more data for meaningful correlations.")
        return

    success = np.array([tasks[t]['success'] for t in tasks])
    features = {
        'total_calls': [tasks[t]['total_calls'] for t in tasks],
        'hedging_sum': [tasks[t]['hedging_sum'] for t in tasks],
        'hedging_max': [tasks[t]['hedging_max'] for t in tasks],
        'delib_sum': [tasks[t]['delib_sum'] for t in tasks],
        'delib_max': [tasks[t]['delib_max'] for t in tasks],
        'alts_sum': [tasks[t]['alts_sum'] for t in tasks],
        'back_sum': [tasks[t]['back_sum'] for t in tasks],
        'verif_sum': [tasks[t]['verif_sum'] for t in tasks],
        'verif_max': [tasks[t]['verif_max'] for t in tasks],
        'plan_sum': [tasks[t]['plan_sum'] for t in tasks],
        'plan_max': [tasks[t]['plan_max'] for t in tasks],
        'calls_with_reasoning': [tasks[t]['calls_with_reasoning'] for t in tasks],
    }

    num_features = len(features)
    print(f"\n=== TASK-LEVEL CORRELATIONS (n={len(tasks)}, {num_features} features, Bonferroni m={num_features}) ===\n")
    print(f"{'Feature':30} {'ρ':>8} {'p_raw':>8} {'p_corr':>8} {'Sig':>6}")
    print("-" * 66)

    for name, values in features.items():
        values = np.array(values, dtype=float)
        if np.std(values) == 0:
            print(f"{name:30} {'—':>8} {'—':>8} {'—':>8} {'no var':>6}")
            continue
        rho, p = spearmanr(values, success)
        p_corrected = min(p * num_features, 1.0)  # Bonferroni
        sig = "***" if p_corrected < 0.001 else "**" if p_corrected < 0.01 else "*" if p_corrected < 0.05 else ""
        print(f"{name:30} {rho:+8.3f} {p:8.4f} {p_corrected:8.4f} {sig:>6}")

    print(f"\nBonferroni correction: m={num_features}. Significance: * p_corr<0.05  ** p_corr<0.01  *** p_corr<0.001")

    # Raw data
    print(f"\n=== RAW TASK DATA ===\n")
    for tid in sorted(tasks.keys()):
        t = tasks[tid]
        status = "PASS" if t['success'] else "FAIL"
        print(f"  [{status}] {tid:45} calls={t['total_calls']:3} "
              f"hedging={t['hedging_sum']:.3f} verif={t['verif_sum']:.3f} "
              f"plan={t['plan_sum']:.3f} delib_max={t['delib_max']:3}")


def call_level_correlations(db):
    """Compute call-level correlations using task success as correctness proxy."""
    # Issue #7 fix: add model_version='sonnet' filter
    # Issue #8 fix: filter to swe-bench-lite only (excludes synthetic/smoke)
    # Codex #12 fix: filter NULL task_success (infra failures)
    calls = db.execute("""
        SELECT tc.hedging_score, tc.deliberation_length, tc.alternatives_considered,
               tc.backtrack_count, tc.verification_score, tc.planning_score,
               tc.sequence_number, r.task_success, r.run_id
        FROM tool_calls tc JOIN runs r ON tc.run_id = r.run_id
        WHERE r.model_version = 'sonnet'
          AND r.task_source = 'swe-bench-lite'
          AND r.validation_source IS NOT NULL
          AND tc.hedging_score IS NOT NULL
          AND r.task_success IS NOT NULL
    """).fetchall()

    if len(calls) < MIN_CELL_SIZE:
        print(f"Only {len(calls)} calls — need {MIN_CELL_SIZE} for analysis.")
        return

    # Assign bins
    data = {'all': [], 'early': [], 'mid': [], 'late': []}
    for c in calls:
        row = {
            'hedging': c['hedging_score'] or 0,
            'deliberation': c['deliberation_length'] or 0,
            'alternatives': c['alternatives_considered'] or 0,
            'backtrack': c['backtrack_count'] or 0,
            'verification': c['verification_score'] or 0,
            'planning': c['planning_score'] or 0,
            'success': c['task_success'],
        }
        data['all'].append(row)
        data[assign_bin(c['sequence_number'])].append(row)

    # Codex #8: report effective n (unique runs) vs raw n (calls)
    unique_runs = len(set(c['run_id'] for c in calls))
    print(f"\n=== CALL-LEVEL CORRELATIONS BY TRAJECTORY BIN ===")
    print(f"    WARNING: task_success is run-level, not call-level. Effective n={unique_runs} runs,")
    print(f"    raw n={len(calls)} calls. Spearman rho inflated. Use task-level for inference.\n")

    features = ['hedging', 'deliberation', 'alternatives', 'backtrack', 'verification', 'planning']
    header = f"{'Feature':20}" + "".join(f"{'  ' + b:>15}" for b in ['early', 'mid', 'late', 'all'])
    print(header)
    print("-" * len(header))

    for feat in features:
        row = f"{feat:20}"
        for bin_name in ['early', 'mid', 'late', 'all']:
            bin_data = data[bin_name]
            if len(bin_data) < MIN_CELL_SIZE:
                row += f"{'n<15':>15}"
                continue
            values = np.array([d[feat] for d in bin_data], dtype=float)
            success = np.array([d['success'] for d in bin_data], dtype=float)
            if np.std(values) == 0:
                row += f"{'no var':>15}"
                continue
            rho, p = spearmanr(values, success)
            sig = "*" if abs(rho) > H0_RHO_THRESHOLD else ""
            row += f"{rho:+.3f}{sig:1} (n={len(bin_data)})".rjust(15)
        print(row)

    # Bin sizes
    print(f"\nBin sizes: " + ", ".join(f"{b}={len(data[b])}" for b in ['early', 'mid', 'late', 'all']))


def reparse_all_runs(db):
    """Re-parse all existing runs from raw_stream_json.

    For each run:
      1. Read raw_stream_json from the runs table
      2. Parse through trace_collector.parse_stream_json (state-modifying only)
      3. DELETE existing tool_calls for that run
      4. INSERT the newly parsed calls
      5. Extract ALL features (Tier 0 + Tier 1)
      6. Print before/after counts
    """
    import io
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))
    from trace_collector import parse_stream_json as tc_parse_stream_json
    from db import insert_tool_call
    from runner import count_all_tool_calls

    runs = db.execute(
        "SELECT run_id, task_id, phase, condition, raw_stream_json "
        "FROM runs WHERE raw_stream_json IS NOT NULL AND raw_stream_json != ''"
    ).fetchall()

    print(f"\n=== REPARSING {len(runs)} RUNS ===\n")

    total_before = db.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0]
    total_new = 0

    for run in runs:
        run_id = run['run_id']
        task_id = run['task_id']
        phase = run['phase']
        condition = run['condition']
        raw = run['raw_stream_json']

        # Count old calls for this run
        old_count = db.execute(
            "SELECT COUNT(*) FROM tool_calls WHERE run_id = ?", (run_id,)
        ).fetchone()[0]

        # Re-parse using canonical trace_collector (state-modifying only)
        # Parse BEFORE delete so we don't lose data on parse failure (Codex #5 fix)
        new_calls = tc_parse_stream_json(io.StringIO(raw), run_id=run_id)

        # Fill in run-level context
        for tc in new_calls:
            tc["task_id"] = task_id
            tc["phase"] = phase
            tc["condition"] = condition

        # Atomic replace: delete + reinsert in single transaction
        all_count = count_all_tool_calls(raw)
        db.execute("BEGIN")
        try:
            db.execute("DELETE FROM tool_calls WHERE run_id = ?", (run_id,))
            for tc in new_calls:
                insert_tool_call(db, tc)
            db.execute(
                "UPDATE runs SET total_tool_calls = ?, total_state_modifying_calls = ? "
                "WHERE run_id = ?",
                (all_count, len(new_calls), run_id)
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        total_new += len(new_calls)
        print(f"  {run_id}: {old_count} -> {len(new_calls)} calls "
              f"({'same' if old_count == len(new_calls) else 'CHANGED'})")

    total_after = db.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0]
    print(f"\n  TOTAL: {total_before} -> {total_after} tool_calls")

    # Now extract all features for the new calls
    print("\nExtracting features for reparsed calls...")
    n_features = extract_features_for_all(db)
    print(f"  Features extracted for {n_features} calls.")

    return total_new


def main():
    import argparse
    parser = argparse.ArgumentParser(description="UGA Phase 0 Analysis")
    parser.add_argument("--summary", action="store_true", help="Quick summary only")
    parser.add_argument("--reparse", action="store_true",
                        help="Re-parse all runs from raw_stream_json before analysis")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    db = get_db()

    # Apply schema updates (adds any new columns if missing)
    from db import init_db
    init_db(str(DB_PATH)).close()

    # Re-parse if requested
    if args.reparse:
        reparse_all_runs(db)
        print()

    # Ensure all features extracted
    n = extract_features_for_all(db)
    if n > 0:
        print(f"Extracted features for {n} new tool calls.\n")

    print("=" * 60)
    print("UGA PHASE 0 ANALYSIS")
    print("=" * 60)
    print()

    n_runs = summary(db)

    if args.summary:
        return

    if n_runs >= 5:
        task_level_correlations(db)
        call_level_correlations(db)
    else:
        print("\nNeed at least 5 runs for analysis.")


if __name__ == "__main__":
    main()

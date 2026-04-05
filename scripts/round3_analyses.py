#!/usr/bin/env python3
"""
Round 3 analyses for reviewer critiques.
Outputs: data/results/round3_analyses.json + human-readable summary to stdout.
"""

import sqlite3
import json
import re
import math
import numpy as np
from collections import defaultdict
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, accuracy_score, brier_score_loss

DB_PATH = "/Users/al/projects/uga-harness/data/uga_phase0_complete_final.db"
OUT_PATH = "/Users/al/projects/uga-harness/data/results/round3_analyses.json"

results = {}


def get_conn():
    return sqlite3.connect(DB_PATH)


# =============================================================================
# ANALYSIS 1: Leave-One-Task-Out Cross-Validation
# =============================================================================
def compute_run_features(conn, model_filter):
    """Compute per-run features from tool_calls table."""
    c = conn.cursor()

    if "codex" in model_filter.lower():
        c.execute("""
            SELECT r.run_id, r.task_id, r.task_success
            FROM runs r
            WHERE r.model_version LIKE '%codex%' AND r.task_success IN (0, 1)
        """)
    else:
        c.execute("""
            SELECT r.run_id, r.task_id, r.task_success
            FROM runs r
            WHERE r.model_version = ? AND r.task_success IN (0, 1)
        """, (model_filter,))

    runs = c.fetchall()
    run_data = []

    for run_id, task_id, task_success in runs:
        # Get tool calls for this run, ordered by sequence
        c.execute("""
            SELECT sequence_number, tool_result_json, reasoning_text
            FROM tool_calls
            WHERE run_id = ?
            ORDER BY sequence_number
        """, (run_id,))
        calls = c.fetchall()

        if not calls:
            continue

        # Determine is_error for each call from tool_result_json
        errors = []
        reasoning_lengths = []
        for seq, result_json, reasoning_text in calls:
            is_err = 0
            if result_json:
                try:
                    rj = json.loads(result_json)
                    if rj.get("is_error", False):
                        is_err = 1
                except (json.JSONDecodeError, TypeError):
                    pass
            errors.append(is_err)
            if reasoning_text and len(reasoning_text.strip()) > 0:
                reasoning_lengths.append(len(reasoning_text))

        n_calls = len(calls)

        # fail_streak_max: max consecutive is_error=1
        max_streak = 0
        current_streak = 0
        for e in errors:
            if e == 1:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0

        # early_error_rate: fraction of first-third calls with is_error=1
        first_third = max(1, n_calls // 3)
        early_errors = sum(errors[:first_third])
        early_error_rate = early_errors / first_third

        # deliberation_length: mean LENGTH(reasoning_text) for non-empty
        delib_length = np.mean(reasoning_lengths) if reasoning_lengths else 0.0

        run_data.append({
            "run_id": run_id,
            "task_id": task_id,
            "task_success": task_success,
            "fail_streak_max": max_streak,
            "early_error_rate": early_error_rate,
            "deliberation_length": delib_length,
            "n_calls": n_calls,
        })

    return run_data


def loo_cv(run_data, feature_names):
    """Leave-one-task-out cross-validation."""
    tasks = list(set(d["task_id"] for d in run_data))
    all_preds = []
    all_true = []

    for held_out_task in tasks:
        train = [d for d in run_data if d["task_id"] != held_out_task]
        test = [d for d in run_data if d["task_id"] == held_out_task]

        if not test or not train:
            continue

        X_train = np.array([[d[f] for f in feature_names] for d in train])
        y_train = np.array([d["task_success"] for d in train])
        X_test = np.array([[d[f] for f in feature_names] for d in test])
        y_test = np.array([d["task_success"] for d in test])

        # Need both classes in training
        if len(set(y_train)) < 2:
            continue

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        clf = LogisticRegression()
        clf.fit(X_train_s, y_train)

        probs = clf.predict_proba(X_test_s)[:, 1]
        preds = clf.predict(X_test_s)

        all_preds.extend(probs.tolist())
        all_true.extend(y_test.tolist())

    all_preds = np.array(all_preds)
    all_true = np.array(all_true)

    if len(set(all_true)) < 2:
        return {"error": "Only one class in held-out predictions"}

    auc = roc_auc_score(all_true, all_preds)
    acc = accuracy_score(all_true, (all_preds >= 0.5).astype(int))
    brier = brier_score_loss(all_true, all_preds)

    return {
        "auc_roc": round(auc, 4),
        "accuracy": round(acc, 4),
        "brier_score": round(brier, 4),
        "n_runs_evaluated": len(all_true),
        "n_tasks": len(tasks),
        "n_positive": int(all_true.sum()),
        "n_negative": int((1 - all_true).sum()),
        "base_rate": round(all_true.mean(), 4),
    }


def analysis_1():
    print("=" * 70)
    print("ANALYSIS 1: Leave-One-Task-Out Cross-Validation")
    print("=" * 70)

    conn = get_conn()

    # Sonnet
    sonnet_data = compute_run_features(conn, "sonnet")
    sonnet_features = ["fail_streak_max", "early_error_rate", "deliberation_length"]
    sonnet_result = loo_cv(sonnet_data, sonnet_features)
    print(f"\nSonnet LOO-CV (features: {sonnet_features}):")
    for k, v in sonnet_result.items():
        print(f"  {k}: {v}")

    # Codex
    codex_data = compute_run_features(conn, "codex")
    codex_features = ["fail_streak_max", "early_error_rate"]
    codex_result = loo_cv(codex_data, codex_features)
    print(f"\nCodex LOO-CV (features: {codex_features}):")
    for k, v in codex_result.items():
        print(f"  {k}: {v}")

    conn.close()

    return {
        "sonnet": {
            "features": sonnet_features,
            **sonnet_result,
        },
        "codex": {
            "features": codex_features,
            **codex_result,
        },
    }


# =============================================================================
# ANALYSIS 2: BH-FDR
# =============================================================================
def bh_fdr(pvalues_dict, q=0.05):
    """Apply Benjamini-Hochberg FDR correction."""
    items = sorted(pvalues_dict.items(), key=lambda x: x[1])
    n = len(items)
    results_list = []
    for rank, (feature, p) in enumerate(items, 1):
        threshold = (rank / n) * q
        results_list.append({
            "feature": feature,
            "p_value": p,
            "rank": rank,
            "bh_threshold": round(threshold, 6),
            "survives": p <= threshold,
        })

    # BH: find largest k where p(k) <= k/n * q, then reject all i <= k
    max_k = 0
    for entry in results_list:
        if entry["p_value"] <= entry["bh_threshold"]:
            max_k = entry["rank"]

    for entry in results_list:
        entry["survives_bh"] = entry["rank"] <= max_k

    return results_list


def analysis_2():
    print("\n" + "=" * 70)
    print("ANALYSIS 2: Benjamini-Hochberg FDR Correction")
    print("=" * 70)

    # Sonnet/sympy p-values (from PHASE0_MEMO Section 4.2)
    sonnet_pvalues = {
        "backtrack_count": 0.0006,
        "fail_streak_max": 0.0058,
        "instead_contrast_density": 0.0081,
        "early_error_rate": 0.0106,
        "unique_files_touched": 0.0179,
        "deliberation_length": 0.0463,
        "metacognitive_density": 0.028,
        "reasoning_to_action_alignment": 0.05,
        "fail_then_switch_rate": 0.10,
        "n_calls": 0.10,
        "think_diagnostic_precision": 0.10,
        "tentative_density": 0.15,
        "first_edit_position": 0.15,
        "insight_density": 0.20,
        "test_run_count": 0.20,
        "recovery_rate": 0.30,
        "self_directive_density": 0.30,
        "edit_churn_rate": 0.30,
        "planning_score": 0.40,
        "verification_score": 0.50,
        "hedging_score": 0.60,
        "precision_naming_score": 0.60,
        "causal_density": 0.70,
    }

    bonferroni_threshold = 0.05 / len(sonnet_pvalues)

    sonnet_bh = bh_fdr(sonnet_pvalues)

    print(f"\nSonnet/sympy within-repo BH-FDR (q=0.05, n={len(sonnet_pvalues)} features):")
    print(f"Bonferroni threshold: {bonferroni_threshold:.6f}")
    print(f"{'Feature':<35} {'p-value':>8} {'Rank':>5} {'BH thresh':>10} {'BH survive':>11} {'Bonf survive':>13}")
    print("-" * 90)
    for entry in sonnet_bh:
        bonf = entry["p_value"] <= bonferroni_threshold
        print(f"{entry['feature']:<35} {entry['p_value']:>8.4f} {entry['rank']:>5} {entry['bh_threshold']:>10.6f} {'YES' if entry['survives_bh'] else 'no':>11} {'YES' if bonf else 'no':>13}")

    bh_survivors = [e["feature"] for e in sonnet_bh if e["survives_bh"]]
    bonf_survivors = [e["feature"] for e in sonnet_bh if e["p_value"] <= bonferroni_threshold]
    print(f"\nBH-FDR survivors: {bh_survivors}")
    print(f"Bonferroni survivors: {bonf_survivors}")

    # CWC Fisher-combined p-values
    cwc_pvalues = {
        "deliberation_length": 0.003,
        "first_edit_position": 0.001,
        "backtrack_count": 0.005,
        "early_error_rate": 0.025,
        "fail_streak_max": 0.026,
    }

    cwc_bh = bh_fdr(cwc_pvalues)
    cwc_bonf_threshold = 0.05 / len(cwc_pvalues)

    print(f"\nCWC Fisher-combined BH-FDR (q=0.05, n={len(cwc_pvalues)} features):")
    print(f"Bonferroni threshold: {cwc_bonf_threshold:.6f}")
    print(f"{'Feature':<30} {'p-value':>8} {'Rank':>5} {'BH thresh':>10} {'BH survive':>11}")
    print("-" * 70)
    for entry in cwc_bh:
        print(f"{entry['feature']:<30} {entry['p_value']:>8.4f} {entry['rank']:>5} {entry['bh_threshold']:>10.6f} {'YES' if entry['survives_bh'] else 'no':>11}")

    cwc_bh_survivors = [e["feature"] for e in cwc_bh if e["survives_bh"]]
    print(f"\nCWC BH-FDR survivors: {cwc_bh_survivors}")

    return {
        "sonnet_sympy": {
            "n_features": len(sonnet_pvalues),
            "q": 0.05,
            "bonferroni_threshold": round(bonferroni_threshold, 6),
            "bh_results": sonnet_bh,
            "bh_survivors": bh_survivors,
            "bonferroni_survivors": bonf_survivors,
        },
        "cwc_fisher": {
            "n_features": len(cwc_pvalues),
            "q": 0.05,
            "bonferroni_threshold": round(cwc_bonf_threshold, 6),
            "bh_results": cwc_bh,
            "bh_survivors": cwc_bh_survivors,
        },
    }


# =============================================================================
# ANALYSIS 3: Confidence Intervals via Fisher z-transform
# =============================================================================
def fisher_z_ci(rho, n, alpha=0.05):
    z = np.arctanh(rho)
    se = 1.0 / math.sqrt(n - 3)
    z_crit = stats.norm.ppf(1 - alpha / 2)
    ci_low = np.tanh(z - z_crit * se)
    ci_high = np.tanh(z + z_crit * se)
    return {
        "rho": rho,
        "n": n,
        "fisher_z": round(z, 4),
        "se": round(se, 4),
        "ci_95_low": round(ci_low, 4),
        "ci_95_high": round(ci_high, 4),
    }


def analysis_3():
    print("\n" + "=" * 70)
    print("ANALYSIS 3: Fisher z-transform Confidence Intervals")
    print("=" * 70)

    # rho=+0.494, n=183 (Sonnet runs)
    ci1 = fisher_z_ci(0.494, 183)
    print(f"\nrho = +0.494 (n=183):")
    print(f"  Fisher z = {ci1['fisher_z']}")
    print(f"  SE = {ci1['se']}")
    print(f"  95% CI = [{ci1['ci_95_low']}, {ci1['ci_95_high']}]")

    # rho=-0.253, n=183
    ci2 = fisher_z_ci(-0.253, 183)
    print(f"\nrho = -0.253 (n=183):")
    print(f"  Fisher z = {ci2['fisher_z']}")
    print(f"  SE = {ci2['se']}")
    print(f"  95% CI = [{ci2['ci_95_low']}, {ci2['ci_95_high']}]")

    return {
        "rho_0.494": ci1,
        "rho_-0.253": ci2,
    }


# =============================================================================
# ANALYSIS 4: Partial Correlations controlling for n_calls
# =============================================================================
def analysis_4():
    print("\n" + "=" * 70)
    print("ANALYSIS 4: Partial Correlations (controlling for n_calls)")
    print("=" * 70)

    conn = get_conn()
    c = conn.cursor()

    # Get Sonnet/sympy runs
    c.execute("""
        SELECT r.run_id, r.task_id, r.task_success
        FROM runs r
        WHERE r.model_version = 'sonnet'
        AND r.task_success IN (0, 1)
        AND r.task_id LIKE 'sympy%'
    """)
    runs = c.fetchall()

    run_features = []
    for run_id, task_id, task_success in runs:
        c.execute("""
            SELECT sequence_number, tool_result_json, reasoning_text
            FROM tool_calls
            WHERE run_id = ?
            ORDER BY sequence_number
        """, (run_id,))
        calls = c.fetchall()

        if not calls:
            continue

        n_calls = len(calls)
        errors = []
        reasoning_lengths = []
        for seq, result_json, reasoning_text in calls:
            is_err = 0
            if result_json:
                try:
                    rj = json.loads(result_json)
                    if rj.get("is_error", False):
                        is_err = 1
                except:
                    pass
            errors.append(is_err)
            if reasoning_text and len(reasoning_text.strip()) > 0:
                reasoning_lengths.append(len(reasoning_text))

        # fail_streak_max
        max_streak = 0
        current = 0
        for e in errors:
            if e == 1:
                current += 1
                max_streak = max(max_streak, current)
            else:
                current = 0

        # early_error_rate
        first_third = max(1, n_calls // 3)
        early_error_rate = sum(errors[:first_third]) / first_third

        # deliberation_length
        delib = np.mean(reasoning_lengths) if reasoning_lengths else 0.0

        # first_edit_position: normalized position of first Edit call
        first_edit_pos = 1.0  # default if no edit
        for seq, result_json, reasoning_text in calls:
            # Need tool_name
            pass

        # Get first_edit_position properly
        c.execute("""
            SELECT MIN(step_index_normalized)
            FROM tool_calls
            WHERE run_id = ? AND tool_name = 'Edit'
        """, (run_id,))
        fep_row = c.fetchone()
        first_edit_pos = fep_row[0] if fep_row[0] is not None else 1.0

        run_features.append({
            "run_id": run_id,
            "task_success": task_success,
            "n_calls": n_calls,
            "deliberation_length": delib,
            "first_edit_position": first_edit_pos,
            "fail_streak_max": max_streak,
            "early_error_rate": early_error_rate,
        })

    conn.close()

    if len(run_features) < 10:
        return {"error": f"Too few Sonnet/sympy runs: {len(run_features)}"}

    # Compute partial correlations
    features_to_test = ["deliberation_length", "first_edit_position", "fail_streak_max", "early_error_rate"]
    partial_results = {}

    arr = {k: np.array([d[k] for d in run_features]) for k in
           features_to_test + ["task_success", "n_calls"]}

    print(f"\nSonnet/sympy: n={len(run_features)} runs")

    for feat in features_to_test:
        # Raw Spearman
        rho_raw, p_raw = stats.spearmanr(arr[feat], arr["task_success"])

        # Rank all variables
        feat_rank = stats.rankdata(arr[feat])
        success_rank = stats.rankdata(arr["task_success"])
        ncalls_rank = stats.rankdata(arr["n_calls"])

        # Regress feature_rank on ncalls_rank, get residuals
        slope1, intercept1, _, _, _ = stats.linregress(ncalls_rank, feat_rank)
        resid_feat = feat_rank - (slope1 * ncalls_rank + intercept1)

        # Regress success_rank on ncalls_rank, get residuals
        slope2, intercept2, _, _, _ = stats.linregress(ncalls_rank, success_rank)
        resid_success = success_rank - (slope2 * ncalls_rank + intercept2)

        # Correlate residuals
        rho_partial, p_partial = stats.spearmanr(resid_feat, resid_success)

        partial_results[feat] = {
            "rho_raw": round(rho_raw, 4),
            "p_raw": round(p_raw, 4),
            "rho_partial": round(rho_partial, 4),
            "p_partial": round(p_partial, 4),
            "change": round(abs(rho_partial) - abs(rho_raw), 4),
        }

        print(f"\n  {feat}:")
        print(f"    Raw Spearman:     rho={rho_raw:.4f}, p={p_raw:.4f}")
        print(f"    Partial (|n_calls): rho={rho_partial:.4f}, p={p_partial:.4f}")
        print(f"    Change in |rho|:  {abs(rho_partial) - abs(rho_raw):+.4f}")

    return {
        "n_runs": len(run_features),
        "repo": "sympy",
        "model": "sonnet",
        "covariate": "n_calls",
        "features": partial_results,
    }


# =============================================================================
# ANALYSIS 5: Thinking-block feature permutation test
# =============================================================================
def extract_thinking_blocks(raw_stream_json):
    """Extract thinking content from raw_stream_json."""
    if not raw_stream_json:
        return ""

    thinking_text = []
    # The raw_stream_json is a sequence of JSON objects, one per line
    for line in raw_stream_json.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Look for thinking blocks in content
        if isinstance(obj, dict):
            # Check for content array with thinking blocks
            content = obj.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "thinking":
                            text = block.get("thinking", "")
                            if text:
                                thinking_text.append(text)
            # Also check message.content
            message = obj.get("message", {})
            if isinstance(message, dict):
                content = message.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "thinking":
                                text = block.get("thinking", "")
                                if text:
                                    thinking_text.append(text)

    return "\n".join(thinking_text)


def compute_density(text, patterns, per_n_chars=1000):
    """Count pattern matches per N chars."""
    if not text or len(text) == 0:
        return 0.0
    count = 0
    for pat in patterns:
        count += len(re.findall(pat, text, re.IGNORECASE))
    return (count / len(text)) * per_n_chars


def analysis_5():
    print("\n" + "=" * 70)
    print("ANALYSIS 5: Thinking-block Feature Permutation Test")
    print("=" * 70)

    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        SELECT run_id, task_id, task_success, raw_stream_json
        FROM runs
        WHERE model_version = 'sonnet'
        AND task_success IN (0, 1)
        AND raw_stream_json IS NOT NULL
    """)
    runs = c.fetchall()
    conn.close()

    tentative_patterns = [r'\blet me try\b', r'\bmaybe\b', r'\bnot sure\b', r'\bmight\b', r'\bperhaps\b']
    actually_patterns = [r'\bactually\b']

    # Group by repo
    repo_data = defaultdict(list)
    n_with_thinking = 0

    for run_id, task_id, task_success, raw_stream_json in runs:
        thinking_text = extract_thinking_blocks(raw_stream_json)

        if not thinking_text or len(thinking_text) < 100:
            continue

        n_with_thinking += 1
        tent_dens = compute_density(thinking_text, tentative_patterns)
        act_dens = compute_density(thinking_text, actually_patterns)

        # Determine repo
        repo = task_id.split("__")[0] if "__" in task_id else "custom"

        repo_data[repo].append({
            "run_id": run_id,
            "task_id": task_id,
            "task_success": task_success,
            "tentative_density": tent_dens,
            "actually_density": act_dens,
            "thinking_chars": len(thinking_text),
        })

    print(f"\nRuns with thinking blocks: {n_with_thinking}")
    print(f"Repos: {list(repo_data.keys())}")
    for repo, data in repo_data.items():
        passes = sum(1 for d in data if d["task_success"] == 1)
        fails = sum(1 for d in data if d["task_success"] == 0)
        print(f"  {repo}: {len(data)} runs ({passes} pass, {fails} fail)")

    # Only use repos with both pass and fail
    valid_repos = {repo: data for repo, data in repo_data.items()
                   if any(d["task_success"] == 1 for d in data) and any(d["task_success"] == 0 for d in data)}

    if len(valid_repos) < 1:
        return {"error": "No repos with both pass and fail outcomes"}

    # Permutation test
    n_perms = 10000
    perm_results = {}

    for feature in ["tentative_density", "actually_density"]:
        # Observed: weighted mean difference across repos
        repo_diffs = []
        repo_ns = []
        for repo, data in valid_repos.items():
            pass_vals = [d[feature] for d in data if d["task_success"] == 1]
            fail_vals = [d[feature] for d in data if d["task_success"] == 0]
            if pass_vals and fail_vals:
                diff = np.mean(pass_vals) - np.mean(fail_vals)
                repo_diffs.append(diff)
                repo_ns.append(len(data))

        if not repo_diffs:
            perm_results[feature] = {"error": "No valid repo comparisons"}
            continue

        total_n = sum(repo_ns)
        weights = [n / total_n for n in repo_ns]
        observed_stat = sum(d * w for d, w in zip(repo_diffs, weights))

        # Permutation
        np.random.seed(42)
        perm_stats = []
        for _ in range(n_perms):
            perm_diffs = []
            for repo, data in valid_repos.items():
                vals = [d[feature] for d in data]
                labels = [d["task_success"] for d in data]
                # Permute labels within repo
                perm_labels = np.random.permutation(labels)
                pass_vals = [v for v, l in zip(vals, perm_labels) if l == 1]
                fail_vals = [v for v, l in zip(vals, perm_labels) if l == 0]
                if pass_vals and fail_vals:
                    perm_diffs.append(np.mean(pass_vals) - np.mean(fail_vals))
                else:
                    perm_diffs.append(0.0)

            perm_stat = sum(d * w for d, w in zip(perm_diffs, weights))
            perm_stats.append(perm_stat)

        perm_stats = np.array(perm_stats)
        # Two-tailed p-value
        p_value = (np.sum(np.abs(perm_stats) >= np.abs(observed_stat)) + 1) / (n_perms + 1)

        perm_results[feature] = {
            "observed_weighted_diff": round(observed_stat, 6),
            "permutation_p_value": round(p_value, 4),
            "n_permutations": n_perms,
            "n_repos": len(valid_repos),
            "repos_used": list(valid_repos.keys()),
            "direction": "pass > fail" if observed_stat > 0 else "fail > pass",
        }

        print(f"\n  {feature}:")
        print(f"    Observed weighted diff (pass-fail): {observed_stat:.6f}")
        print(f"    Permutation p-value (two-tailed): {p_value:.4f}")
        print(f"    Direction: {'pass > fail' if observed_stat > 0 else 'fail > pass'}")

    # Per-repo descriptive stats
    desc_stats = {}
    for repo, data in valid_repos.items():
        for feature in ["tentative_density", "actually_density"]:
            pass_vals = [d[feature] for d in data if d["task_success"] == 1]
            fail_vals = [d[feature] for d in data if d["task_success"] == 0]
            key = f"{repo}/{feature}"
            desc_stats[key] = {
                "pass_mean": round(np.mean(pass_vals), 4) if pass_vals else None,
                "fail_mean": round(np.mean(fail_vals), 4) if fail_vals else None,
                "pass_n": len(pass_vals),
                "fail_n": len(fail_vals),
            }

    return {
        "n_runs_with_thinking": n_with_thinking,
        "permutation_tests": perm_results,
        "descriptive_stats": desc_stats,
    }


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    print("Running Round 3 analyses...\n")

    results["analysis_1_loo_cv"] = analysis_1()
    results["analysis_2_bh_fdr"] = analysis_2()
    results["analysis_3_fisher_ci"] = analysis_3()
    results["analysis_4_partial_correlations"] = analysis_4()
    results["analysis_5_thinking_permutation"] = analysis_5()

    # Save
    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'=' * 70}")
    print(f"Results saved to {OUT_PATH}")
    print(f"{'=' * 70}")

    # Summary
    print("\n" + "=" * 70)
    print("EXECUTIVE SUMMARY")
    print("=" * 70)

    a1 = results["analysis_1_loo_cv"]
    print(f"\n1. LOO-CV:")
    print(f"   Sonnet: AUC={a1['sonnet'].get('auc_roc','N/A')}, "
          f"Acc={a1['sonnet'].get('accuracy','N/A')}, "
          f"Brier={a1['sonnet'].get('brier_score','N/A')}, "
          f"n={a1['sonnet'].get('n_runs_evaluated','N/A')}, "
          f"base_rate={a1['sonnet'].get('base_rate','N/A')}")
    print(f"   Codex:  AUC={a1['codex'].get('auc_roc','N/A')}, "
          f"Acc={a1['codex'].get('accuracy','N/A')}, "
          f"Brier={a1['codex'].get('brier_score','N/A')}, "
          f"n={a1['codex'].get('n_runs_evaluated','N/A')}, "
          f"base_rate={a1['codex'].get('base_rate','N/A')}")

    a2 = results["analysis_2_bh_fdr"]
    print(f"\n2. BH-FDR:")
    print(f"   Sonnet/sympy BH survivors: {a2['sonnet_sympy']['bh_survivors']}")
    print(f"   Bonferroni survivors:       {a2['sonnet_sympy']['bonferroni_survivors']}")
    print(f"   CWC BH survivors:           {a2['cwc_fisher']['bh_survivors']}")

    a3 = results["analysis_3_fisher_ci"]
    print(f"\n3. Confidence Intervals:")
    r1 = a3["rho_0.494"]
    print(f"   rho=+0.494: 95% CI [{r1['ci_95_low']}, {r1['ci_95_high']}]")
    r2 = a3["rho_-0.253"]
    print(f"   rho=-0.253: 95% CI [{r2['ci_95_low']}, {r2['ci_95_high']}]")

    a4 = results["analysis_4_partial_correlations"]
    if "error" not in a4:
        print(f"\n4. Partial Correlations (Sonnet/sympy, n={a4['n_runs']}, controlling for n_calls):")
        for feat, vals in a4["features"].items():
            print(f"   {feat}: raw rho={vals['rho_raw']}, partial rho={vals['rho_partial']} (change={vals['change']:+.4f})")

    a5 = results["analysis_5_thinking_permutation"]
    if "error" not in a5:
        print(f"\n5. Thinking-block Permutation Tests (n={a5['n_runs_with_thinking']} runs):")
        for feat, vals in a5["permutation_tests"].items():
            if "error" not in vals:
                print(f"   {feat}: p={vals['permutation_p_value']}, diff={vals['observed_weighted_diff']:.4f} ({vals['direction']})")

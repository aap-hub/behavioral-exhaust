#!/usr/bin/env python3
"""Round 4: Nested Feature-Selection LOO-CV, Bootstrap AUC CI, and Permutation Test.

Addresses Codex's final concerns about overfitting and statistical validity of
behavioral features as predictors of task success.
"""

import json
import re
import sqlite3
import time
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

DB_PATH = Path(__file__).parent.parent / "data" / "uga_phase0_complete_final.db"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "results" / "round4_nested_cv.json"

FEATURE_NAMES = [
    "fail_streak_max",
    "early_error_rate",
    "deliberation_length",
    "backtrack_count",
    "first_edit_position",
    "unique_files_touched",
    "instead_contrast_density",
]

CONTRAST_PATTERN = re.compile(r"however|but|instead|rather", re.IGNORECASE)
BACKTRACK_PATTERN = re.compile(r"actually|wait|instead", re.IGNORECASE)


def get_repo(task_id: str) -> str:
    """Extract repo name from task_id like 'django__django-12345'."""
    return task_id.split("__")[0]


def load_run_data(conn, model_filter: str) -> list[dict]:
    """Load runs and compute per-run features from tool_calls."""
    if "codex" in model_filter.lower():
        where_model = "r.model_version LIKE '%codex%'"
    else:
        where_model = f"r.model_version = '{model_filter}'"

    runs_sql = f"""
        SELECT r.run_id, r.task_id, r.task_success
        FROM runs r
        WHERE {where_model}
          AND r.task_success IN (0, 1)
          AND r.validation_source IS NOT NULL
        ORDER BY r.run_id
    """
    runs = conn.execute(runs_sql).fetchall()

    # Pre-fetch all tool calls for these runs
    run_ids = [r[0] for r in runs]
    if not run_ids:
        return []

    placeholders = ",".join("?" * len(run_ids))
    tc_sql = f"""
        SELECT tc.run_id, tc.sequence_number, tc.tool_name,
               tc.reasoning_text, tc.tool_params_json,
               json_extract(tc.tool_result_json, '$.is_error') as is_error
        FROM tool_calls tc
        WHERE tc.run_id IN ({placeholders})
        ORDER BY tc.run_id, tc.sequence_number
    """
    tool_calls = conn.execute(tc_sql, run_ids).fetchall()

    # Group tool calls by run_id
    tc_by_run = defaultdict(list)
    for row in tool_calls:
        tc_by_run[row[0]].append(row)

    result = []
    for run_id, task_id, task_success in runs:
        calls = tc_by_run.get(run_id, [])
        if not calls:
            continue

        n_calls = len(calls)
        features = compute_features(calls, n_calls)
        features["run_id"] = run_id
        features["task_id"] = task_id
        features["task_success"] = int(task_success)
        features["repo"] = get_repo(task_id)
        result.append(features)

    return result


def compute_features(calls: list, n_calls: int) -> dict:
    """Compute the 7 behavioral features for a single run."""
    # is_error per call
    errors = [1 if c[5] else 0 for c in calls]

    # fail_streak_max
    max_streak = 0
    cur_streak = 0
    for e in errors:
        if e:
            cur_streak += 1
            max_streak = max(max_streak, cur_streak)
        else:
            cur_streak = 0

    # early_error_rate: fraction of first-third calls with is_error=1
    first_third = max(1, n_calls // 3)
    early_errors = sum(errors[:first_third])
    early_error_rate = early_errors / first_third

    # deliberation_length: mean LENGTH(reasoning_text) for non-null, non-empty
    reasoning_lengths = []
    for c in calls:
        rt = c[3]
        if rt and len(rt.strip()) > 0:
            reasoning_lengths.append(len(rt))
    deliberation_length = np.mean(reasoning_lengths) if reasoning_lengths else 0.0

    # backtrack_count: count of reasoning_text containing pattern / total calls
    backtrack_hits = 0
    for c in calls:
        rt = c[3]
        if rt and BACKTRACK_PATTERN.search(rt):
            backtrack_hits += 1
    backtrack_count = backtrack_hits / n_calls

    # first_edit_position: position of first Edit/Write call / total calls
    first_edit_pos = 0.0
    for i, c in enumerate(calls):
        if c[2] in ("Edit", "Write"):
            first_edit_pos = (i + 1) / n_calls
            break

    # unique_files_touched: count distinct file_path from Edit/Write tool_params_json
    files_touched = set()
    for c in calls:
        if c[2] in ("Edit", "Write") and c[4]:
            try:
                params = json.loads(c[4])
                fp = params.get("file_path") or params.get("path", "")
                if fp:
                    files_touched.add(fp)
            except (json.JSONDecodeError, TypeError):
                pass
    unique_files_touched = len(files_touched)

    # instead_contrast_density: count pattern in reasoning_text / total chars * 1000
    total_chars = 0
    contrast_count = 0
    for c in calls:
        rt = c[3]
        if rt:
            total_chars += len(rt)
            contrast_count += len(CONTRAST_PATTERN.findall(rt))
    instead_contrast_density = (contrast_count / total_chars * 1000) if total_chars > 0 else 0.0

    return {
        "fail_streak_max": max_streak,
        "early_error_rate": early_error_rate,
        "deliberation_length": deliberation_length,
        "backtrack_count": backtrack_count,
        "first_edit_position": first_edit_pos,
        "unique_files_touched": unique_files_touched,
        "instead_contrast_density": instead_contrast_density,
    }


def select_features_on_training(data: list[dict], feature_names: list[str],
                                rho_threshold=0.15, p_threshold=0.10) -> list[str]:
    """Within-repo Spearman feature selection. Select features where
    |rho| > threshold AND p < p_threshold in at least one of sympy or django."""
    selected = []
    for feat in feature_names:
        passes_in_any_repo = False
        for repo in ["sympy", "django"]:
            repo_data = [d for d in data if d["repo"] == repo]
            if len(repo_data) < 5:
                continue
            x = np.array([d[feat] for d in repo_data])
            y = np.array([d["task_success"] for d in repo_data])
            if np.std(x) == 0:
                continue
            rho, p = stats.spearmanr(x, y)
            if abs(rho) > rho_threshold and p < p_threshold:
                passes_in_any_repo = True
                break
        if passes_in_any_repo:
            selected.append(feat)
    return selected


def nested_loo_cv(data: list[dict], feature_names: list[str]):
    """Nested LOO-CV: hold out one task at a time, select features on training,
    train logistic regression, predict on held-out task runs."""
    tasks = sorted(set(d["task_id"] for d in data))
    all_preds = []
    feature_selection_counts = defaultdict(int)
    n_folds = 0

    for held_out_task in tasks:
        train = [d for d in data if d["task_id"] != held_out_task]
        test = [d for d in data if d["task_id"] == held_out_task]

        if not test or not train:
            continue

        # Feature selection on training data only
        selected = select_features_on_training(train, feature_names)
        if not selected:
            # Fallback: use all features if none pass threshold
            selected = feature_names[:]

        n_folds += 1
        for feat in selected:
            feature_selection_counts[feat] += 1

        X_train = np.array([[d[f] for f in selected] for d in train])
        y_train = np.array([d["task_success"] for d in train])
        X_test = np.array([[d[f] for f in selected] for d in test])
        y_test = np.array([d["task_success"] for d in test])

        # Standardize
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        # Check if training labels have both classes
        if len(set(y_train)) < 2:
            # Can't train a classifier with one class - predict base rate
            base_rate = np.mean(y_train)
            for i, d in enumerate(test):
                all_preds.append({
                    "run_id": d["run_id"],
                    "task_id": d["task_id"],
                    "true_label": int(y_test[i]),
                    "pred_prob": float(base_rate),
                })
            continue

        clf = LogisticRegression(max_iter=1000)
        clf.fit(X_train_s, y_train)
        probs = clf.predict_proba(X_test_s)
        # Get probability of class 1
        class_1_idx = list(clf.classes_).index(1)

        for i, d in enumerate(test):
            all_preds.append({
                "run_id": d["run_id"],
                "task_id": d["task_id"],
                "true_label": int(y_test[i]),
                "pred_prob": float(probs[i, class_1_idx]),
            })

    # Feature stability
    feature_stability = {
        feat: feature_selection_counts[feat] / n_folds if n_folds > 0 else 0.0
        for feat in feature_names
    }

    return all_preds, feature_stability, n_folds


def compute_metrics(preds: list[dict]) -> dict:
    """Compute AUC-ROC and accuracy from predictions."""
    y_true = np.array([p["true_label"] for p in preds])
    y_prob = np.array([p["pred_prob"] for p in preds])
    y_pred = (y_prob >= 0.5).astype(int)

    if len(set(y_true)) < 2:
        return {"auc": float("nan"), "accuracy": float(accuracy_score(y_true, y_pred)),
                "n": len(preds)}

    auc = roc_auc_score(y_true, y_prob)
    acc = accuracy_score(y_true, y_pred)
    return {"auc": float(auc), "accuracy": float(acc), "n": len(preds)}


def bootstrap_auc_ci(preds: list[dict], n_bootstrap=2000, ci=0.95):
    """Bootstrap confidence interval for AUC."""
    y_true = np.array([p["true_label"] for p in preds])
    y_prob = np.array([p["pred_prob"] for p in preds])
    n = len(preds)

    rng = np.random.RandomState(42)
    aucs = []
    for _ in range(n_bootstrap):
        idx = rng.choice(n, size=n, replace=True)
        yt = y_true[idx]
        yp = y_prob[idx]
        if len(set(yt)) < 2:
            continue
        aucs.append(roc_auc_score(yt, yp))

    aucs = np.array(aucs)
    alpha = (1 - ci) / 2
    lo = np.percentile(aucs, alpha * 100)
    hi = np.percentile(aucs, (1 - alpha) * 100)
    return {
        "mean_auc": float(np.mean(aucs)),
        "se": float(np.std(aucs, ddof=1)),
        "ci_lo": float(lo),
        "ci_hi": float(hi),
        "n_valid_bootstraps": len(aucs),
    }


def permutation_test(data: list[dict], feature_names: list[str],
                     observed_auc: float, n_perm=10000, time_limit=300):
    """Permutation test: shuffle labels within repo, re-run nested LOO-CV.
    Falls back to simpler permutation if too slow."""

    start = time.time()
    rng = np.random.RandomState(123)

    # First try 10 full nested permutations to estimate time
    null_aucs = []
    for i in range(min(10, n_perm)):
        perm_data = _shuffle_within_repo(data, rng)
        preds, _, _ = nested_loo_cv(perm_data, feature_names)
        if preds:
            metrics = compute_metrics(preds)
            if not np.isnan(metrics["auc"]):
                null_aucs.append(metrics["auc"])

        elapsed = time.time() - start
        if i >= 2 and elapsed > 30:
            # Estimate total time
            per_iter = elapsed / (i + 1)
            total_est = per_iter * n_perm
            if total_est > time_limit:
                print(f"  Full nested permutation too slow ({per_iter:.1f}s/iter, "
                      f"est {total_est:.0f}s for {n_perm}). Reducing to 1000...")
                n_perm = 1000
                if per_iter * 1000 > time_limit:
                    print(f"  Still too slow. Falling back to simple label-shuffle permutation.")
                    return _simple_permutation_test(data, feature_names, observed_auc, rng, n_perm=10000)

    # Continue with remaining permutations
    for i in range(10, n_perm):
        perm_data = _shuffle_within_repo(data, rng)
        preds, _, _ = nested_loo_cv(perm_data, feature_names)
        if preds:
            metrics = compute_metrics(preds)
            if not np.isnan(metrics["auc"]):
                null_aucs.append(metrics["auc"])

        if (time.time() - start) > time_limit:
            print(f"  Time limit reached after {i+1} permutations.")
            break

    null_aucs = np.array(null_aucs)
    p_value = np.mean(null_aucs >= observed_auc) if len(null_aucs) > 0 else float("nan")

    return {
        "method": "nested_loo_cv_permutation",
        "n_permutations": len(null_aucs),
        "observed_auc": float(observed_auc),
        "mean_null_auc": float(np.mean(null_aucs)) if len(null_aucs) > 0 else float("nan"),
        "std_null_auc": float(np.std(null_aucs)) if len(null_aucs) > 0 else float("nan"),
        "p_value": float(p_value),
        "elapsed_seconds": time.time() - start,
    }


def _simple_permutation_test(data, feature_names, observed_auc, rng, n_perm=10000):
    """Simple permutation: shuffle labels, compute AUC on existing LOO-CV structure
    (no re-fitting, just using original predictions with shuffled labels)."""
    # First get original predictions
    preds, _, _ = nested_loo_cv(data, feature_names)
    y_prob = np.array([p["pred_prob"] for p in preds])
    y_true = np.array([p["true_label"] for p in preds])
    task_ids = [p["task_id"] for p in preds]

    # Build repo mapping for within-repo shuffling
    repos = [get_repo(tid) for tid in task_ids]
    repo_indices = defaultdict(list)
    for i, r in enumerate(repos):
        repo_indices[r].append(i)

    null_aucs = []
    for _ in range(n_perm):
        y_perm = y_true.copy()
        for repo, indices in repo_indices.items():
            repo_labels = y_perm[indices]
            rng.shuffle(repo_labels)
            y_perm[indices] = repo_labels

        if len(set(y_perm)) < 2:
            continue
        null_aucs.append(roc_auc_score(y_perm, y_prob))

    null_aucs = np.array(null_aucs)
    p_value = np.mean(null_aucs >= observed_auc) if len(null_aucs) > 0 else float("nan")

    return {
        "method": "simple_label_shuffle_permutation",
        "n_permutations": len(null_aucs),
        "observed_auc": float(observed_auc),
        "mean_null_auc": float(np.mean(null_aucs)) if len(null_aucs) > 0 else float("nan"),
        "std_null_auc": float(np.std(null_aucs)) if len(null_aucs) > 0 else float("nan"),
        "p_value": float(p_value),
    }


def _shuffle_within_repo(data: list[dict], rng) -> list[dict]:
    """Shuffle task_success labels within each repo."""
    by_repo = defaultdict(list)
    for d in data:
        by_repo[d["repo"]].append(d)

    result = []
    for repo, items in by_repo.items():
        labels = [d["task_success"] for d in items]
        rng.shuffle(labels)
        for d, new_label in zip(items, labels):
            new_d = d.copy()
            new_d["task_success"] = new_label
            result.append(new_d)

    return result


def run_analysis(model_name: str, model_filter: str, conn) -> dict:
    """Run all three analyses for a given model."""
    print(f"\n{'='*60}")
    print(f"  {model_name}")
    print(f"{'='*60}")

    data = load_run_data(conn, model_filter)
    print(f"  Loaded {len(data)} runs across {len(set(d['task_id'] for d in data))} tasks")

    y = [d["task_success"] for d in data]
    print(f"  Success rate: {sum(y)}/{len(y)} = {sum(y)/len(y):.3f}")

    repos = set(d["repo"] for d in data)
    print(f"  Repos: {sorted(repos)}")

    # Analysis 1: Nested LOO-CV
    print(f"\n  --- Analysis 1: Nested Feature-Selection LOO-CV ---")
    preds, feature_stability, n_folds = nested_loo_cv(data, FEATURE_NAMES)
    metrics = compute_metrics(preds)

    print(f"  Folds: {n_folds}")
    print(f"  AUC-ROC: {metrics['auc']:.4f}")
    print(f"  Accuracy: {metrics['accuracy']:.4f}")
    print(f"  N predictions: {metrics['n']}")
    print(f"\n  Feature selection stability (fraction of folds selected):")
    for feat in FEATURE_NAMES:
        pct = feature_stability[feat]
        bar = "#" * int(pct * 20)
        print(f"    {feat:30s}  {pct:.2f}  {bar}")

    # Analysis 2: Bootstrap AUC CI
    print(f"\n  --- Analysis 2: Bootstrap AUC 95% CI ---")
    if not np.isnan(metrics["auc"]):
        boot = bootstrap_auc_ci(preds, n_bootstrap=2000)
        print(f"  AUC: {boot['mean_auc']:.4f} [{boot['ci_lo']:.4f}, {boot['ci_hi']:.4f}]")
        print(f"  SE: {boot['se']:.4f}")
        print(f"  Valid bootstrap samples: {boot['n_valid_bootstraps']}")
    else:
        boot = {"mean_auc": float("nan"), "se": float("nan"),
                "ci_lo": float("nan"), "ci_hi": float("nan"),
                "n_valid_bootstraps": 0}
        print(f"  Cannot compute (AUC is NaN)")

    # Analysis 3: Permutation test
    print(f"\n  --- Analysis 3: Permutation Test ---")
    if not np.isnan(metrics["auc"]):
        perm = permutation_test(data, FEATURE_NAMES, metrics["auc"],
                                n_perm=10000, time_limit=300)
        print(f"  Method: {perm['method']}")
        print(f"  Observed AUC: {perm['observed_auc']:.4f}")
        print(f"  Mean null AUC: {perm['mean_null_auc']:.4f}")
        print(f"  Std null AUC: {perm['std_null_auc']:.4f}")
        print(f"  p-value: {perm['p_value']:.4f}")
        print(f"  N permutations: {perm['n_permutations']}")
    else:
        perm = {"method": "skipped", "observed_auc": float("nan"),
                "mean_null_auc": float("nan"), "p_value": float("nan"),
                "n_permutations": 0}
        print(f"  Skipped (AUC is NaN)")

    return {
        "model": model_name,
        "n_runs": len(data),
        "n_tasks": len(set(d["task_id"] for d in data)),
        "success_rate": sum(y) / len(y) if y else 0,
        "nested_loo_cv": {
            "auc": metrics["auc"],
            "accuracy": metrics["accuracy"],
            "n_predictions": metrics["n"],
            "n_folds": n_folds,
            "feature_stability": {k: round(v, 4) for k, v in feature_stability.items()},
        },
        "bootstrap_ci": boot,
        "permutation_test": perm,
    }


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")

    results = {}
    results["sonnet"] = run_analysis("Sonnet", "sonnet", conn)
    results["codex"] = run_analysis("Codex", "codex", conn)

    conn.close()

    # Print summary
    print(f"\n\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")

    for name, r in results.items():
        cv = r["nested_loo_cv"]
        boot = r["bootstrap_ci"]
        perm = r["permutation_test"]
        print(f"\n  {name.upper()} ({r['n_runs']} runs, {r['n_tasks']} tasks)")
        print(f"    Nested LOO-CV AUC:  {cv['auc']:.4f}  (acc={cv['accuracy']:.4f})")
        if not np.isnan(boot.get("ci_lo", float("nan"))):
            print(f"    Bootstrap 95% CI:   [{boot['ci_lo']:.4f}, {boot['ci_hi']:.4f}]  SE={boot['se']:.4f}")
        print(f"    Permutation test:   p={perm['p_value']:.4f}  "
              f"(null={perm['mean_null_auc']:.4f}, method={perm['method']})")

        print(f"    Feature stability:")
        for feat in FEATURE_NAMES:
            stab = cv["feature_stability"].get(feat, 0)
            if stab > 0:
                print(f"      {feat:30s}  {stab:.2f}")

    # Save
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Convert any nan to None for JSON serialization
    def sanitize(obj):
        if isinstance(obj, float) and np.isnan(obj):
            return None
        if isinstance(obj, dict):
            return {k: sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [sanitize(v) for v in obj]
        return obj

    with open(OUTPUT_PATH, "w") as f:
        json.dump(sanitize(results), f, indent=2)
    print(f"\n  Results saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

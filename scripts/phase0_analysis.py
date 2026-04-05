#!/usr/bin/env python3
"""
Phase 0 Definitive Statistical Analysis for UGA
Computes all features, runs all methods, writes results to context/phase0_analysis_opus.md
"""

import sqlite3
import numpy as np
import pandas as pd
import warnings
import re
import json
from scipy.stats import spearmanr, rankdata
import statsmodels.formula.api as smf
from scipy.stats import chi2
from collections import defaultdict

warnings.filterwarnings("ignore")

# ============================================================
# STEP 0: Load raw data
# ============================================================

db = sqlite3.connect("data/uga.db")

# Load runs
runs_df = pd.read_sql_query("""
    SELECT run_id, task_id, task_success, task_source,
           total_tool_calls, total_state_modifying_calls
    FROM runs WHERE phase=0
""", db)

# Extract repo from task_id
def get_repo(task_id):
    if '__' in task_id:
        return task_id.split('__')[0]
    return 'synthetic'

runs_df['repo'] = runs_df['task_id'].apply(get_repo)
print(f"Runs: {len(runs_df)}, unique tasks: {runs_df['task_id'].nunique()}, repos: {runs_df['repo'].nunique()}")
print(f"Pass rate: {runs_df['task_success'].mean()*100:.1f}%")
print(f"Repo breakdown:")
for repo, grp in runs_df.groupby('repo'):
    print(f"  {repo}: n={len(grp)}, pass={grp['task_success'].sum()}, rate={grp['task_success'].mean()*100:.1f}%")

# Load tool calls
tc_df = pd.read_sql_query("""
    SELECT decision_id, run_id, task_id, sequence_number, tool_name,
           tool_params_json, tool_result_json, reasoning_text,
           reasoning_token_count, step_index_normalized,
           prior_failure_streak, retry_count, tool_switch_rate,
           hedging_score, deliberation_length, alternatives_considered,
           backtrack_count, verification_score, planning_score
    FROM tool_calls WHERE phase=0
    ORDER BY run_id, sequence_number
""", db)

print(f"\nTool calls: {len(tc_df)}")
print(f"With reasoning text: {tc_df['reasoning_text'].notna().sum()} ({tc_df[tc_df['reasoning_text'].notna() & (tc_df['reasoning_text'].str.len() > 0)].shape[0]} non-empty)")

# ============================================================
# STEP 1: Compute all features per run
# ============================================================

def is_error(result_json):
    """Check if a tool result indicates an error."""
    if pd.isna(result_json):
        return False
    try:
        r = json.loads(result_json)
        if isinstance(r, dict):
            return r.get('is_error', False) == True
    except:
        pass
    # Fallback: string matching
    return '"is_error": true' in str(result_json).lower() or '"is_error":true' in str(result_json).lower()

def is_test_call(row):
    """Check if a Bash call is a test run."""
    if row['tool_name'] != 'Bash':
        return False
    params = str(row.get('tool_params_json', '') or '')
    return any(kw in params.lower() for kw in ['pytest', 'test', 'unittest', 'nosetests'])

def is_edit_call(row):
    """Check if call is Edit or Write."""
    return row['tool_name'] in ('Edit', 'Write')

# Linguistic feature extraction from reasoning text
HEDGE_WORDS = [
    'might', 'could', 'perhaps', 'possibly', 'probably', 'likely',
    'unlikely', 'suggest', 'appear', 'seem', 'tend', 'assume',
    'approximate', 'roughly', 'generally', 'typically', 'usually',
    'often', 'sometimes', 'occasionally', 'rarely', 'seldom'
]

METACOG_PATTERNS = ['actually', 'wait', 'hmm', 'i see', 'hold on']
TENTATIVE_PATTERNS = ['let me try', 'maybe', 'not sure', 'perhaps']
INSIGHT_PATTERNS = ['i understand', 'the issue is', 'the problem is', 'the bug is', 'actually']
INSTEAD_PATTERNS = ['instead', 'rather than', 'instead of']
SELF_DIRECTIVE_PATTERNS = ['i need to', 'let me', 'i should', "i'll", 'i have to']
WRONG_STUCK_PATTERNS = ['wrong', 'incorrect', 'mistake', 'broken']
CAUSAL_PATTERNS = ['because', 'since', 'therefore', 'due to']
BACKTRACK_MARKERS = ['actually', 'wait', 'no,', 'let me reconsider', 'on second thought', 'hmm', 'hold on']
PLANNING_MARKERS = ['first', 'then', 'next', 'step', 'plan', 'strategy', 'approach']
VERIFICATION_MARKERS = ['verify', 'check', 'confirm', 'test', 'validate', 'ensure', 'make sure']

def count_pattern_density(text, patterns):
    """Count pattern occurrences per token."""
    if not text or len(text.strip()) == 0:
        return 0.0
    text_lower = text.lower()
    tokens = text_lower.split()
    n_tokens = max(len(tokens), 1)
    count = sum(text_lower.count(p) for p in patterns)
    return count / n_tokens

def count_precision_naming(text):
    """Count backtick-quoted terms, CamelCase, snake_case, file paths per token."""
    if not text or len(text.strip()) == 0:
        return 0.0
    tokens = text.split()
    n_tokens = max(len(tokens), 1)
    count = 0
    # Backtick-quoted
    count += len(re.findall(r'`[^`]+`', text))
    # CamelCase
    count += len(re.findall(r'\b[A-Z][a-z]+[A-Z][a-zA-Z]*\b', text))
    # snake_case (at least one underscore, all lowercase parts)
    count += len(re.findall(r'\b[a-z]+(?:_[a-z]+)+\b', text))
    # File paths
    count += len(re.findall(r'[\w/]+\.\w{1,4}\b', text))
    return count / n_tokens

def reasoning_mentions_file(reasoning, params_json):
    """Check if reasoning text mentions the file about to be edited."""
    if not reasoning or not params_json:
        return 0.0
    try:
        params = json.loads(params_json)
        filepath = params.get('file_path', '') or params.get('path', '')
        if not filepath:
            return 0.0
        # Extract filename
        filename = filepath.split('/')[-1]
        return 1.0 if filename in reasoning else 0.0
    except:
        return 0.0


def compute_run_features(run_id, run_tc):
    """Compute all features for a single run."""
    features = {}
    n_calls = len(run_tc)
    features['n_calls'] = n_calls

    if n_calls == 0:
        return features

    # Sort by sequence
    run_tc = run_tc.sort_values('sequence_number').reset_index(drop=True)

    # --- Tier 0: Structural features ---

    # Error detection
    errors = run_tc.apply(lambda r: is_error(r['tool_result_json']), axis=1).values

    # fail_streak_max
    max_streak = 0
    current_streak = 0
    for e in errors:
        if e:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
    features['fail_streak_max'] = max_streak

    # early_error_rate: error rate in first 1/3
    third = max(n_calls // 3, 1)
    early_errors = errors[:third]
    features['early_error_rate'] = np.mean(early_errors) if len(early_errors) > 0 else 0.0

    # first_edit_position: normalized position of first Edit/Write
    edit_mask = run_tc['tool_name'].isin(['Edit', 'Write'])
    if edit_mask.any():
        first_edit_idx = edit_mask.idxmax()
        features['first_edit_position'] = first_edit_idx / max(n_calls - 1, 1)
    else:
        features['first_edit_position'] = 1.0  # never edited

    # unique_files_touched
    files_touched = set()
    for _, row in run_tc[edit_mask].iterrows():
        try:
            params = json.loads(row['tool_params_json'] or '{}')
            fp = params.get('file_path', '')
            if fp:
                files_touched.add(fp)
        except:
            pass
    features['unique_files_touched'] = len(files_touched)

    # edit_churn_rate: re-edits per unique file
    n_edits = edit_mask.sum()
    n_unique_files = max(len(files_touched), 1)
    features['edit_churn_rate'] = n_edits / n_unique_files if n_unique_files > 0 else 0.0

    # recovery_rate: fail->pass transitions / total failures
    total_failures = errors.sum()
    fail_to_pass = 0
    for i in range(1, len(errors)):
        if errors[i-1] and not errors[i]:
            fail_to_pass += 1
    features['recovery_rate'] = fail_to_pass / max(total_failures, 1) if total_failures > 0 else np.nan

    # fail_then_switch_rate: tool switch after error / total errors
    fail_then_switch = 0
    for i in range(1, len(run_tc)):
        if errors[i-1]:
            if run_tc.iloc[i]['tool_name'] != run_tc.iloc[i-1]['tool_name']:
                fail_then_switch += 1
    features['fail_then_switch_rate'] = fail_then_switch / max(total_failures, 1) if total_failures > 0 else np.nan

    # test_run_count
    features['test_run_count'] = run_tc.apply(is_test_call, axis=1).sum()

    # --- Tier 1: Linguistic features (from pre-existing columns) ---
    features['hedging_score'] = run_tc['hedging_score'].mean() if run_tc['hedging_score'].notna().any() else 0.0
    features['deliberation_length'] = run_tc['deliberation_length'].mean() if run_tc['deliberation_length'].notna().any() else 0.0
    features['backtrack_count'] = run_tc['backtrack_count'].mean() if run_tc['backtrack_count'].notna().any() else 0.0
    features['verification_score'] = run_tc['verification_score'].mean() if run_tc['verification_score'].notna().any() else 0.0
    features['planning_score'] = run_tc['planning_score'].mean() if run_tc['planning_score'].notna().any() else 0.0

    # --- Tier 2: Domain-specific linguistic (from reasoning_text) ---
    texts = run_tc['reasoning_text'].dropna()
    texts = texts[texts.str.len() > 0]

    if len(texts) > 0:
        metacog_scores = [count_pattern_density(t, METACOG_PATTERNS) for t in texts]
        tentative_scores = [count_pattern_density(t, TENTATIVE_PATTERNS) for t in texts]
        insight_scores = [count_pattern_density(t, INSIGHT_PATTERNS) for t in texts]
        instead_scores = [count_pattern_density(t, INSTEAD_PATTERNS) for t in texts]
        self_dir_scores = [count_pattern_density(t, SELF_DIRECTIVE_PATTERNS) for t in texts]
        wrong_stuck_scores = [count_pattern_density(t, WRONG_STUCK_PATTERNS) for t in texts]
        causal_scores = [count_pattern_density(t, CAUSAL_PATTERNS) for t in texts]
        precision_scores = [count_precision_naming(t) for t in texts]

        features['metacognitive_density'] = np.mean(metacog_scores)
        features['tentative_density'] = np.mean(tentative_scores)
        features['insight_density'] = np.mean(insight_scores)
        features['instead_contrast_density'] = np.mean(instead_scores)
        features['self_directive_density'] = np.mean(self_dir_scores)
        features['wrong_stuck_density'] = np.mean(wrong_stuck_scores)
        features['causal_density'] = np.mean(causal_scores)
        features['precision_naming_score'] = np.mean(precision_scores)
    else:
        for feat in ['metacognitive_density', 'tentative_density', 'insight_density',
                      'instead_contrast_density', 'self_directive_density',
                      'wrong_stuck_density', 'causal_density', 'precision_naming_score']:
            features[feat] = np.nan

    # --- Interaction: reasoning_to_action_alignment ---
    edit_rows = run_tc[run_tc['tool_name'].isin(['Edit', 'Write'])]
    if len(edit_rows) > 0:
        alignments = [reasoning_mentions_file(row['reasoning_text'], row['tool_params_json'])
                      for _, row in edit_rows.iterrows()]
        features['reasoning_to_action_alignment'] = np.mean(alignments)
    else:
        features['reasoning_to_action_alignment'] = np.nan

    return features


print("\nComputing run-level features...")
run_features = {}
for run_id, grp in tc_df.groupby('run_id'):
    run_features[run_id] = compute_run_features(run_id, grp)

features_df = pd.DataFrame.from_dict(run_features, orient='index')
features_df.index.name = 'run_id'
features_df = features_df.reset_index()

# Merge with runs
analysis_df = runs_df.merge(features_df, on='run_id', how='left')
print(f"Analysis dataframe: {len(analysis_df)} runs x {len(analysis_df.columns)} columns")

# Also add total calls from tool_calls (to handle runs with no calls in tc_df)
# Use n_calls from features where available
analysis_df['n_calls'] = analysis_df['n_calls'].fillna(0)

# ============================================================
# Feature summary
# ============================================================

ALL_FEATURES = [
    # Tier 0
    'fail_streak_max', 'early_error_rate', 'first_edit_position',
    'unique_files_touched', 'edit_churn_rate', 'recovery_rate',
    'fail_then_switch_rate', 'test_run_count', 'n_calls',
    # Tier 1
    'hedging_score', 'deliberation_length', 'backtrack_count',
    'verification_score', 'planning_score',
    # Tier 2
    'metacognitive_density', 'tentative_density', 'insight_density',
    'instead_contrast_density', 'self_directive_density',
    'wrong_stuck_density', 'causal_density', 'precision_naming_score',
    # Interaction
    'reasoning_to_action_alignment'
]

N_FEATURES = len(ALL_FEATURES)
BONFERRONI_ALPHA = 0.05 / N_FEATURES

print(f"\nTotal features: {N_FEATURES}")
print(f"Bonferroni threshold: {BONFERRONI_ALPHA:.5f}")
print("\nFeature descriptive stats:")
for feat in ALL_FEATURES:
    vals = analysis_df[feat].dropna()
    print(f"  {feat}: n={len(vals)}, mean={vals.mean():.4f}, sd={vals.std():.4f}, min={vals.min():.4f}, max={vals.max():.4f}")


# ============================================================
# STEP 2: Three analysis methods
# ============================================================

results = []

# Method A: Mixed-effects logistic regression with random intercept for repo
print("\n" + "="*80)
print("METHOD A: Mixed-effects linear model")
print("="*80)

method_a_results = {}
for feat in ALL_FEATURES:
    subset = analysis_df[['task_success', feat, 'repo']].dropna()
    if len(subset) < 10 or subset[feat].std() < 1e-10:
        method_a_results[feat] = {'coef': np.nan, 'se': np.nan, 'p_raw': np.nan, 'lrt_p': np.nan, 'n': len(subset), 'note': 'insufficient variance'}
        continue

    try:
        # Full model with feature
        formula_full = f"task_success ~ {feat}"
        model_full = smf.mixedlm(formula_full, subset, groups=subset['repo'])
        result_full = model_full.fit(reml=False)

        # Null model (intercept only)
        formula_null = "task_success ~ 1"
        model_null = smf.mixedlm(formula_null, subset, groups=subset['repo'])
        result_null = model_null.fit(reml=False)

        # LRT
        lr_stat = -2 * (result_null.llf - result_full.llf)
        lrt_p = chi2.sf(lr_stat, df=1)

        coef = result_full.params[feat]
        se = result_full.bse[feat]
        p_val = result_full.pvalues[feat]

        method_a_results[feat] = {
            'coef': coef, 'se': se, 'p_raw': p_val,
            'lrt_p': lrt_p, 'n': len(subset),
            'aic_full': result_full.aic, 'aic_null': result_null.aic
        }
        sig = "*" if p_val < 0.05 else ""
        bonf = "**BONF**" if p_val < BONFERRONI_ALPHA else ""
        print(f"  {feat}: coef={coef:.4f}, SE={se:.4f}, p={p_val:.4f} {sig} {bonf}, LRT p={lrt_p:.4f}, n={len(subset)}")
    except Exception as e:
        method_a_results[feat] = {'coef': np.nan, 'se': np.nan, 'p_raw': np.nan, 'lrt_p': np.nan, 'n': len(subset), 'note': str(e)[:80]}
        print(f"  {feat}: FAILED - {str(e)[:80]}")


# Method B: Within-repo Spearman
print("\n" + "="*80)
print("METHOD B: Within-repo Spearman correlations")
print("="*80)

FOCAL_REPOS = {
    'sympy': analysis_df[analysis_df['repo'] == 'sympy'],
    'django': analysis_df[analysis_df['repo'] == 'django'],
    'pytest-dev': analysis_df[analysis_df['repo'] == 'pytest-dev']
}

method_b_results = {}
for repo_name, repo_df in FOCAL_REPOS.items():
    print(f"\n  --- {repo_name} (n={len(repo_df)}, pass={repo_df['task_success'].mean()*100:.1f}%) ---")
    method_b_results[repo_name] = {}
    for feat in ALL_FEATURES:
        vals = repo_df[[feat, 'task_success']].dropna()
        if len(vals) < 5 or vals[feat].std() < 1e-10:
            method_b_results[repo_name][feat] = {'rho': np.nan, 'p': np.nan, 'n': len(vals)}
            continue
        rho, p = spearmanr(vals[feat], vals['task_success'])
        method_b_results[repo_name][feat] = {'rho': rho, 'p': p, 'n': len(vals)}
        sig = "*" if p < 0.05 else ""
        bonf = "**BONF**" if p < BONFERRONI_ALPHA else ""
        print(f"    {feat}: rho={rho:.3f}, p={p:.4f} {sig} {bonf}, n={len(vals)}")


# Method C: Partial Spearman controlling for repo + n_calls
print("\n" + "="*80)
print("METHOD C: Partial Spearman (controlling repo + n_calls)")
print("="*80)

def partial_spearman(x, y, covariates):
    """Compute partial Spearman correlation."""
    # Rank all variables
    rx = rankdata(x)
    ry = rankdata(y)
    rcovs = np.column_stack([rankdata(c) for c in covariates])

    # Residualize x and y on covariates using OLS
    from numpy.linalg import lstsq
    # Add intercept
    X = np.column_stack([np.ones(len(rx)), rcovs])

    # Residualize rx
    beta_x, _, _, _ = lstsq(X, rx, rcond=None)
    res_x = rx - X @ beta_x

    # Residualize ry
    beta_y, _, _, _ = lstsq(X, ry, rcond=None)
    res_y = ry - X @ beta_y

    # Spearman of residuals (which is just Pearson of ranked residuals)
    rho, p = spearmanr(res_x, res_y)
    return rho, p

# Create repo dummies
repo_dummies = pd.get_dummies(analysis_df['repo'], drop_first=True).values

method_c_results = {}
for feat in ALL_FEATURES:
    # When feat is n_calls, we can't control for it; just control for repo
    if feat == 'n_calls':
        cols_needed = ['task_success', 'n_calls', 'repo']
    else:
        cols_needed = ['task_success', feat, 'n_calls', 'repo']
    subset = analysis_df[cols_needed].dropna()
    feat_std = subset[feat].std()
    if isinstance(feat_std, pd.Series):
        feat_std = feat_std.iloc[0]
    if len(subset) < 10 or feat_std < 1e-10:
        method_c_results[feat] = {'rho': np.nan, 'p': np.nan, 'n': len(subset)}
        continue

    # Get repo dummies for this subset
    repo_dum = pd.get_dummies(subset['repo'], drop_first=True).values
    covariates = []
    if feat != 'n_calls':
        covariates.append(subset['n_calls'].values)
    for col_idx in range(repo_dum.shape[1]):
        covariates.append(repo_dum[:, col_idx])

    try:
        rho, p = partial_spearman(subset[feat].values, subset['task_success'].values, covariates)
        method_c_results[feat] = {'rho': rho, 'p': p, 'n': len(subset)}
        sig = "*" if p < 0.05 else ""
        bonf = "**BONF**" if p < BONFERRONI_ALPHA else ""
        print(f"  {feat}: partial_rho={rho:.3f}, p={p:.4f} {sig} {bonf}, n={len(subset)}")
    except Exception as e:
        method_c_results[feat] = {'rho': np.nan, 'p': np.nan, 'n': len(subset)}
        print(f"  {feat}: FAILED - {str(e)[:60]}")

# ============================================================
# STEP 3: Multiple comparison correction
# ============================================================

print("\n" + "="*80)
print("STEP 3: Multiple comparison summary")
print("="*80)

print(f"\nTotal features tested: {N_FEATURES}")
print(f"Bonferroni alpha: 0.05 / {N_FEATURES} = {BONFERRONI_ALPHA:.5f}")

# Collect all p-values across methods
all_p_values = []
for feat in ALL_FEATURES:
    row = {'feature': feat}
    # Method A
    ma = method_a_results.get(feat, {})
    row['A_coef'] = ma.get('coef', np.nan)
    row['A_se'] = ma.get('se', np.nan)
    row['A_p'] = ma.get('p_raw', np.nan)
    row['A_lrt_p'] = ma.get('lrt_p', np.nan)
    row['A_n'] = ma.get('n', 0)
    # Method B - sympy
    mb_s = method_b_results.get('sympy', {}).get(feat, {})
    row['B_sympy_rho'] = mb_s.get('rho', np.nan)
    row['B_sympy_p'] = mb_s.get('p', np.nan)
    row['B_sympy_n'] = mb_s.get('n', 0)
    # Method B - django
    mb_d = method_b_results.get('django', {}).get(feat, {})
    row['B_django_rho'] = mb_d.get('rho', np.nan)
    row['B_django_p'] = mb_d.get('p', np.nan)
    row['B_django_n'] = mb_d.get('n', 0)
    # Method B - pytest
    mb_p = method_b_results.get('pytest-dev', {}).get(feat, {})
    row['B_pytest_rho'] = mb_p.get('rho', np.nan)
    row['B_pytest_p'] = mb_p.get('p', np.nan)
    row['B_pytest_n'] = mb_p.get('n', 0)
    # Method C
    mc = method_c_results.get(feat, {})
    row['C_rho'] = mc.get('rho', np.nan)
    row['C_p'] = mc.get('p', np.nan)
    row['C_n'] = mc.get('n', 0)

    all_p_values.append(row)

summary_df = pd.DataFrame(all_p_values)

# Check which survive Bonferroni
for col in ['A_p', 'A_lrt_p', 'B_sympy_p', 'B_django_p', 'B_pytest_p', 'C_p']:
    summary_df[f'{col}_bonf'] = summary_df[col] < BONFERRONI_ALPHA

print("\nFeatures significant at p<0.05 (uncorrected) in ANY method:")
for _, row in summary_df.iterrows():
    any_sig = False
    methods = []
    for col, label in [('A_p', 'Mixed-eff'), ('B_sympy_p', 'Sympy'), ('B_django_p', 'Django'), ('B_pytest_p', 'Pytest'), ('C_p', 'Partial')]:
        if not np.isnan(row[col]) and row[col] < 0.05:
            any_sig = True
            methods.append(f"{label}(p={row[col]:.4f})")
    if any_sig:
        print(f"  {row['feature']}: {', '.join(methods)}")

print("\nFeatures surviving Bonferroni (p<{:.5f}) in ANY method:".format(BONFERRONI_ALPHA))
for _, row in summary_df.iterrows():
    any_bonf = False
    methods = []
    for col, label in [('A_p', 'Mixed-eff'), ('A_lrt_p', 'LRT'), ('B_sympy_p', 'Sympy'), ('B_django_p', 'Django'), ('B_pytest_p', 'Pytest'), ('C_p', 'Partial')]:
        bcol = f'{col}_bonf' if f'{col}_bonf' in summary_df.columns else None
        if bcol and row.get(bcol, False):
            any_bonf = True
            methods.append(f"{label}(p={row[col]:.6f})")
    if any_bonf:
        print(f"  {row['feature']}: {', '.join(methods)}")

# ============================================================
# STEP 4: Intercorrelation matrix
# ============================================================

print("\n" + "="*80)
print("STEP 4: Intercorrelation matrix (features with p<0.10 in any method)")
print("="*80)

# Find features with p<0.10 anywhere
sig_features = []
for _, row in summary_df.iterrows():
    for col in ['A_p', 'B_sympy_p', 'B_django_p', 'B_pytest_p', 'C_p']:
        if not np.isnan(row[col]) and row[col] < 0.10:
            sig_features.append(row['feature'])
            break

print(f"\nFeatures reaching p<0.10: {len(sig_features)}")
print(f"  {sig_features}")

corr_matrix = None
if len(sig_features) >= 2:
    corr_matrix = pd.DataFrame(index=sig_features, columns=sig_features, dtype=float)
    p_matrix = pd.DataFrame(index=sig_features, columns=sig_features, dtype=float)

    for i, f1 in enumerate(sig_features):
        for j, f2 in enumerate(sig_features):
            if i == j:
                corr_matrix.loc[f1, f2] = 1.0
                p_matrix.loc[f1, f2] = 0.0
            elif j > i:
                vals = analysis_df[[f1, f2]].dropna()
                if len(vals) >= 5 and vals[f1].std() > 1e-10 and vals[f2].std() > 1e-10:
                    rho, p = spearmanr(vals[f1], vals[f2])
                    corr_matrix.loc[f1, f2] = rho
                    corr_matrix.loc[f2, f1] = rho
                    p_matrix.loc[f1, f2] = p
                    p_matrix.loc[f2, f1] = p
                else:
                    corr_matrix.loc[f1, f2] = np.nan
                    corr_matrix.loc[f2, f1] = np.nan

    print("\nPairwise Spearman correlations:")
    for i, f1 in enumerate(sig_features):
        for j, f2 in enumerate(sig_features):
            if j > i:
                r = corr_matrix.loc[f1, f2]
                if not np.isnan(r):
                    flag = " *** COLLINEAR" if abs(r) > 0.5 else ""
                    print(f"  {f1} x {f2}: r={r:.3f}{flag}")

# ============================================================
# STEP 5: Effect size analysis + write output
# ============================================================

print("\n" + "="*80)
print("STEP 5: Writing full results")
print("="*80)

# Build the output document
lines = []
lines.append("# Phase 0 Statistical Analysis (Definitive)")
lines.append("")
lines.append("Generated by phase0_analysis.py using Opus 4.6")
lines.append("Date: 2026-03-28")
lines.append("")
lines.append("## 1. Data Summary")
lines.append("")
lines.append(f"- **Total runs**: {len(analysis_df)}")
lines.append(f"- **Unique tasks**: {analysis_df['task_id'].nunique()}")
lines.append(f"- **Unique repos**: {analysis_df['repo'].nunique()}")
lines.append(f"- **Overall pass rate**: {analysis_df['task_success'].mean()*100:.1f}%")
lines.append(f"- **Total tool calls**: {len(tc_df)}")
lines.append(f"- **Tool calls with reasoning text**: {tc_df[tc_df['reasoning_text'].notna() & (tc_df['reasoning_text'].str.len() > 0)].shape[0]}")
lines.append("")
lines.append("### Repo breakdown")
lines.append("")
lines.append("| Repo | N runs | N tasks | Passes | Pass % |")
lines.append("|------|--------|---------|--------|--------|")
for repo in ['sympy', 'django', 'pytest-dev', 'scikit-learn', 'pylint-dev', 'psf', 'sphinx-doc', 'pallets', 'astropy', 'synthetic']:
    rdf = analysis_df[analysis_df['repo'] == repo]
    if len(rdf) > 0:
        lines.append(f"| {repo} | {len(rdf)} | {rdf['task_id'].nunique()} | {int(rdf['task_success'].sum())} | {rdf['task_success'].mean()*100:.1f}% |")

lines.append("")
lines.append("### Feature count and correction")
lines.append("")
lines.append(f"- **Total features tested**: {N_FEATURES}")
lines.append(f"- **Bonferroni alpha**: 0.05 / {N_FEATURES} = {BONFERRONI_ALPHA:.5f}")
lines.append("")

# Feature descriptives
lines.append("## 2. Feature Descriptive Statistics")
lines.append("")
lines.append("| Feature | Tier | N | Mean | SD | Min | Max |")
lines.append("|---------|------|---|------|----|----|-----|")
tier_map = {}
for f in ['fail_streak_max', 'early_error_rate', 'first_edit_position',
          'unique_files_touched', 'edit_churn_rate', 'recovery_rate',
          'fail_then_switch_rate', 'test_run_count', 'n_calls']:
    tier_map[f] = 0
for f in ['hedging_score', 'deliberation_length', 'backtrack_count',
          'verification_score', 'planning_score']:
    tier_map[f] = 1
for f in ['metacognitive_density', 'tentative_density', 'insight_density',
          'instead_contrast_density', 'self_directive_density',
          'wrong_stuck_density', 'causal_density', 'precision_naming_score']:
    tier_map[f] = 2
tier_map['reasoning_to_action_alignment'] = 'X'

for feat in ALL_FEATURES:
    vals = analysis_df[feat].dropna()
    tier = tier_map.get(feat, '?')
    lines.append(f"| {feat} | {tier} | {len(vals)} | {vals.mean():.4f} | {vals.std():.4f} | {vals.min():.4f} | {vals.max():.4f} |")

lines.append("")

# Method A full results
lines.append("## 3. Method A: Mixed-Effects Linear Model")
lines.append("")
lines.append("Model: `task_success ~ feature + (1 | repo)`")
lines.append("")
lines.append("| Feature | Coef | SE | p (raw) | p (LRT) | Bonf? | N |")
lines.append("|---------|------|----|---------|---------|-------|---|")
for feat in ALL_FEATURES:
    ma = method_a_results.get(feat, {})
    coef = ma.get('coef', np.nan)
    se = ma.get('se', np.nan)
    p = ma.get('p_raw', np.nan)
    lrt = ma.get('lrt_p', np.nan)
    n = ma.get('n', 0)
    note = ma.get('note', '')
    bonf = 'YES' if (not np.isnan(p) and p < BONFERRONI_ALPHA) else 'no'
    if note:
        lines.append(f"| {feat} | -- | -- | -- | -- | -- | {n} | ({note}) |")
    else:
        pstr = f"{p:.4f}" if not np.isnan(p) else "--"
        sig = " *" if (not np.isnan(p) and p < 0.05) else ""
        lines.append(f"| {feat} | {coef:.4f} | {se:.4f} | {pstr}{sig} | {lrt:.4f} | {bonf} | {n} |")

lines.append("")

# Method B full results
lines.append("## 4. Method B: Within-Repo Spearman Correlations")
lines.append("")

for repo_name in ['sympy', 'django', 'pytest-dev']:
    repo_df = FOCAL_REPOS[repo_name]
    lines.append(f"### {repo_name} (n={len(repo_df)}, pass rate={repo_df['task_success'].mean()*100:.1f}%)")
    lines.append("")
    lines.append("| Feature | rho | p (raw) | Bonf? | N |")
    lines.append("|---------|-----|---------|-------|---|")
    for feat in ALL_FEATURES:
        mb = method_b_results[repo_name].get(feat, {})
        rho = mb.get('rho', np.nan)
        p = mb.get('p', np.nan)
        n = mb.get('n', 0)
        bonf = 'YES' if (not np.isnan(p) and p < BONFERRONI_ALPHA) else 'no'
        sig = " *" if (not np.isnan(p) and p < 0.05) else ""
        rstr = f"{rho:.3f}" if not np.isnan(rho) else "--"
        pstr = f"{p:.4f}" if not np.isnan(p) else "--"
        lines.append(f"| {feat} | {rstr} | {pstr}{sig} | {bonf} | {n} |")
    lines.append("")

# Method C full results
lines.append("## 5. Method C: Partial Spearman (controlling repo + n_calls)")
lines.append("")
lines.append("| Feature | Partial rho | p (raw) | Bonf? | N |")
lines.append("|---------|-------------|---------|-------|---|")
for feat in ALL_FEATURES:
    mc = method_c_results.get(feat, {})
    rho = mc.get('rho', np.nan)
    p = mc.get('p', np.nan)
    n = mc.get('n', 0)
    bonf = 'YES' if (not np.isnan(p) and p < BONFERRONI_ALPHA) else 'no'
    sig = " *" if (not np.isnan(p) and p < 0.05) else ""
    rstr = f"{rho:.3f}" if not np.isnan(rho) else "--"
    pstr = f"{p:.4f}" if not np.isnan(p) else "--"
    lines.append(f"| {feat} | {rstr} | {pstr}{sig} | {bonf} | {n} |")

lines.append("")

# Intercorrelation matrix
lines.append("## 6. Intercorrelation Matrix (features with p<0.10 in any method)")
lines.append("")
lines.append(f"Features reaching p<0.10 in at least one method: {len(sig_features)}")
lines.append("")

if len(sig_features) >= 2 and corr_matrix is not None:
    # Header
    header = "| Feature | " + " | ".join(sig_features) + " |"
    sep = "|---------|" + "|".join(["-----"] * len(sig_features)) + "|"
    lines.append(header)
    lines.append(sep)
    for f1 in sig_features:
        row_vals = []
        for f2 in sig_features:
            if f1 == f2:
                row_vals.append("1.000")
            else:
                r = corr_matrix.loc[f1, f2]
                flag = " **" if (not np.isnan(r) and abs(r) > 0.5) else ""
                row_vals.append(f"{r:.3f}{flag}" if not np.isnan(r) else "--")
        lines.append(f"| {f1} | " + " | ".join(row_vals) + " |")

    lines.append("")
    lines.append("** = |r| > 0.5 (collinear)")
    lines.append("")

    # List collinear pairs explicitly
    lines.append("### Collinear pairs (|r| > 0.5)")
    lines.append("")
    collinear_found = False
    for i, f1 in enumerate(sig_features):
        for j, f2 in enumerate(sig_features):
            if j > i:
                r = corr_matrix.loc[f1, f2]
                if not np.isnan(r) and abs(r) > 0.5:
                    lines.append(f"- {f1} x {f2}: r = {r:.3f}")
                    collinear_found = True
    if not collinear_found:
        lines.append("- None")
    lines.append("")

# Cross-method summary
lines.append("## 7. Cross-Method Summary")
lines.append("")
lines.append("### Features significant at p<0.05 (uncorrected)")
lines.append("")
lines.append("| Feature | Mixed-eff | Sympy | Django | Pytest | Partial | # methods |")
lines.append("|---------|-----------|-------|--------|--------|---------|-----------|")
for _, row in summary_df.iterrows():
    methods_sig = 0
    cells = []
    for col, label in [('A_p', 'Mixed-eff'), ('B_sympy_p', 'Sympy'), ('B_django_p', 'Django'), ('B_pytest_p', 'Pytest'), ('C_p', 'Partial')]:
        p = row[col]
        if not np.isnan(p) and p < 0.05:
            methods_sig += 1
            cells.append(f"p={p:.4f}")
        elif np.isnan(p):
            cells.append("--")
        else:
            cells.append(f"ns ({p:.3f})")
    if methods_sig > 0:
        lines.append(f"| {row['feature']} | {' | '.join(cells)} | {methods_sig} |")

lines.append("")
lines.append("### Features surviving Bonferroni correction")
lines.append("")
bonf_survivors = []
for _, row in summary_df.iterrows():
    for col in ['A_p', 'A_lrt_p', 'B_sympy_p', 'B_django_p', 'B_pytest_p', 'C_p']:
        bcol = f'{col}_bonf'
        if bcol in summary_df.columns and row.get(bcol, False):
            bonf_survivors.append(row['feature'])
            break

if bonf_survivors:
    for feat in sorted(set(bonf_survivors)):
        methods_bonf = []
        row = summary_df[summary_df['feature'] == feat].iloc[0]
        for col, label in [('A_p', 'Mixed-eff'), ('A_lrt_p', 'LRT'), ('B_sympy_p', 'Sympy'), ('B_django_p', 'Django'), ('B_pytest_p', 'Pytest'), ('C_p', 'Partial')]:
            bcol = f'{col}_bonf'
            if bcol in summary_df.columns and row.get(bcol, False):
                methods_bonf.append(f"{label}(p={row[col]:.6f})")
        lines.append(f"- **{feat}**: {', '.join(methods_bonf)}")
else:
    lines.append("- **None** -- no features survive Bonferroni correction")

lines.append("")

# Per-repo analysis
lines.append("### Significant features by repo")
lines.append("")
for repo_name in ['sympy', 'django', 'pytest-dev']:
    lines.append(f"**{repo_name}** (p<0.05 uncorrected):")
    found = False
    for feat in ALL_FEATURES:
        mb = method_b_results[repo_name].get(feat, {})
        p = mb.get('p', np.nan)
        rho = mb.get('rho', np.nan)
        if not np.isnan(p) and p < 0.05:
            found = True
            bonf = " (survives Bonferroni)" if p < BONFERRONI_ALPHA else ""
            lines.append(f"  - {feat}: rho={rho:.3f}, p={p:.4f}{bonf}")
    if not found:
        lines.append("  - None")
    lines.append("")

# Features significant in BOTH sympy and django
lines.append("### Features significant in BOTH sympy and django (p<0.05)")
lines.append("")
both_sig = []
for feat in ALL_FEATURES:
    s_p = method_b_results['sympy'].get(feat, {}).get('p', np.nan)
    d_p = method_b_results['django'].get(feat, {}).get('p', np.nan)
    if not np.isnan(s_p) and not np.isnan(d_p) and s_p < 0.05 and d_p < 0.05:
        s_rho = method_b_results['sympy'][feat]['rho']
        d_rho = method_b_results['django'][feat]['rho']
        both_sig.append((feat, s_rho, s_p, d_rho, d_p))
        lines.append(f"- **{feat}**: sympy rho={s_rho:.3f} (p={s_p:.4f}), django rho={d_rho:.3f} (p={d_p:.4f})")
        # Check direction consistency
        if np.sign(s_rho) == np.sign(d_rho):
            lines.append(f"  - Direction: CONSISTENT ({'+' if s_rho > 0 else '-'})")
        else:
            lines.append(f"  - Direction: INCONSISTENT (sympy {'+' if s_rho > 0 else '-'}, django {'+' if d_rho > 0 else '-'})")

if not both_sig:
    lines.append("- None")
lines.append("")

# Pre-registered vs discovered
lines.append("## 8. Pre-registered vs Discovered Features")
lines.append("")
lines.append("### Pre-registered (Tier 0 + Tier 1, from protocol)")
lines.append("")
preregistered = ['fail_streak_max', 'early_error_rate', 'first_edit_position',
                 'unique_files_touched', 'edit_churn_rate', 'recovery_rate',
                 'fail_then_switch_rate', 'test_run_count',
                 'hedging_score', 'deliberation_length', 'backtrack_count',
                 'verification_score', 'planning_score']
for feat in preregistered:
    sig_any = False
    for col in ['A_p', 'B_sympy_p', 'B_django_p', 'B_pytest_p', 'C_p']:
        row = summary_df[summary_df['feature'] == feat].iloc[0]
        if not np.isnan(row[col]) and row[col] < 0.05:
            sig_any = True
            break
    status = "SIG in >=1 method" if sig_any else "not significant"
    lines.append(f"- {feat}: {status}")
lines.append("")

lines.append("### Discovered (Tier 2, post-hoc)")
lines.append("")
discovered = ['metacognitive_density', 'tentative_density', 'insight_density',
              'instead_contrast_density', 'self_directive_density',
              'wrong_stuck_density', 'causal_density', 'precision_naming_score',
              'reasoning_to_action_alignment']
for feat in discovered:
    sig_any = False
    for col in ['A_p', 'B_sympy_p', 'B_django_p', 'B_pytest_p', 'C_p']:
        row = summary_df[summary_df['feature'] == feat].iloc[0]
        if not np.isnan(row[col]) and row[col] < 0.05:
            sig_any = True
            break
    status = "SIG in >=1 method" if sig_any else "not significant"
    lines.append(f"- {feat}: {status}")
lines.append("")

# Narrative summary
lines.append("## 9. Overall Narrative")
lines.append("")

# Compute some summary stats
n_sig_any = sum(1 for _, row in summary_df.iterrows()
                if any(not np.isnan(row[c]) and row[c] < 0.05
                       for c in ['A_p', 'B_sympy_p', 'B_django_p', 'B_pytest_p', 'C_p']))
n_bonf = len(set(bonf_survivors))
n_multi_method = sum(1 for _, row in summary_df.iterrows()
                     if sum(1 for c in ['A_p', 'B_sympy_p', 'B_django_p', 'B_pytest_p', 'C_p']
                            if not np.isnan(row[c]) and row[c] < 0.05) >= 2)

lines.append(f"Out of {N_FEATURES} features tested:")
lines.append(f"- {n_sig_any} reach p<0.05 in at least one method")
lines.append(f"- {n_multi_method} reach p<0.05 in two or more methods")
lines.append(f"- {n_bonf} survive Bonferroni correction")
lines.append(f"- {len(both_sig)} are significant in both sympy and django")
lines.append("")

# Strongest features
lines.append("### Strongest signals (sorted by cross-method consistency)")
lines.append("")
feat_scores = []
for _, row in summary_df.iterrows():
    n_methods = sum(1 for c in ['A_p', 'B_sympy_p', 'B_django_p', 'B_pytest_p', 'C_p']
                    if not np.isnan(row[c]) and row[c] < 0.05)
    min_p = min((row[c] for c in ['A_p', 'B_sympy_p', 'B_django_p', 'B_pytest_p', 'C_p']
                 if not np.isnan(row[c])), default=1.0)
    if n_methods > 0:
        feat_scores.append((row['feature'], n_methods, min_p))

feat_scores.sort(key=lambda x: (-x[1], x[2]))
for rank, (feat, nm, mp) in enumerate(feat_scores, 1):
    row = summary_df[summary_df['feature'] == feat].iloc[0]
    direction_info = []
    if not np.isnan(row['A_coef']):
        direction_info.append(f"mixed-eff coef={row['A_coef']:.4f}")
    if not np.isnan(row['B_sympy_rho']):
        direction_info.append(f"sympy rho={row['B_sympy_rho']:.3f}")
    if not np.isnan(row['B_django_rho']):
        direction_info.append(f"django rho={row['B_django_rho']:.3f}")
    if not np.isnan(row['C_rho']):
        direction_info.append(f"partial rho={row['C_rho']:.3f}")
    lines.append(f"{rank}. **{feat}** ({nm} methods, min p={mp:.4f}): {'; '.join(direction_info)}")

lines.append("")

# Key warnings/limitations
lines.append("## 10. Limitations and Caveats")
lines.append("")
n_with_text = tc_df[tc_df['reasoning_text'].notna() & (tc_df['reasoning_text'].str.len() > 0)].shape[0]
pct_text = n_with_text / len(tc_df) * 100
lines.append(f"1. **Reasoning text sparsity**: Only {n_with_text}/{len(tc_df)} tool calls have non-empty reasoning text ({pct_text:.0f}%). Tier 2 linguistic features are computed only over calls with text, biasing toward runs where text was captured.")
lines.append("2. **Repo confound**: Pass rates vary from 0% (scikit-learn) to 100% (pylint-dev, pallets). Mixed-effects model partially addresses this; within-repo analyses are cleanest.")
lines.append("3. **Task nesting**: Multiple runs per task violate independence. Mixed-effects with (1|repo) helps but (1|task) would be more appropriate -- not enough replicates per task for stable estimation.")
lines.append(f"4. **Multiple comparisons**: {N_FEATURES} features x ~5 tests = ~{N_FEATURES * 5} comparisons. Bonferroni is conservative; some true effects may be missed.")
lines.append("5. **Synthetic runs**: 8 runs from synthetic tasks (100% pass) may inflate correlations. All analyses include them; re-running without would be advisable.")
lines.append("6. **Django ceiling effect**: 84% pass rate means limited variance in outcome, reducing power for within-django analyses.")
lines.append(f"7. **Hedging score**: Near-zero mean ({analysis_df['hedging_score'].mean():.4f}) confirms expected null -- Hyland hedging markers are nearly absent in LLM tool-use reasoning.")
lines.append("")

# Write
output_path = "context/phase0_analysis_opus.md"
with open(output_path, 'w') as f:
    f.write('\n'.join(lines))

print(f"\nResults written to {output_path}")
print(f"Total lines: {len(lines)}")
print("DONE")

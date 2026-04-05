# UGA Analysis Protocol

Specifies the exact sequence of operations from data → answers → report.
This is the complement to the design doc (measurement infrastructure) — it specifies what to compute and how to present it.

## Phase 0 Analysis Sequence

After all Phase 0 data is collected and labeled, run these operations in order:

### Step 1: Data Quality Check

```sql
-- How many total calls? Per trajectory bin?
SELECT
    CASE
        WHEN sequence_number <= 3 THEN 'early'
        WHEN sequence_number <= 7 THEN 'mid'
        ELSE 'late'
    END AS bin,
    COUNT(*) AS n_calls,
    SUM(CASE WHEN lf.label_final = 'correct' THEN 1 ELSE 0 END) AS n_correct,
    SUM(CASE WHEN lf.label_final = 'incorrect' THEN 1 ELSE 0 END) AS n_incorrect,
    SUM(CASE WHEN lf.label_final = 'uncertain' THEN 1 ELSE 0 END) AS n_uncertain,
    SUM(CASE WHEN lf.label_source = 'machine' THEN 1 ELSE 0 END) AS n_machine_labeled,
    SUM(CASE WHEN lf.label_source = 'human' THEN 1 ELSE 0 END) AS n_human_labeled
FROM tool_calls tc
JOIN labels_final lf ON tc.decision_id = lf.decision_id
WHERE tc.phase = 0
GROUP BY bin;
```

**Expected output:** Table showing call counts per bin. Check:
- Total calls ≥ 50 (PHASE0_MIN_TOTAL_CALLS)
- Each bin ≥ 15 (MIN_CELL_SIZE)
- Base rate of incorrect calls (should be 10-40% for meaningful analysis)

**Red flag:** If base rate < 5% or > 80%, the agent is either too good or too bad for the features to discriminate.

### Step 2: Feature Distributions

```sql
-- Feature distributions per trajectory bin
SELECT
    CASE WHEN sequence_number <= 3 THEN 'early'
         WHEN sequence_number <= 7 THEN 'mid' ELSE 'late' END AS bin,
    AVG(hedging_score) AS mean_hedging,
    AVG(deliberation_length) AS mean_deliberation,
    AVG(alternatives_considered) AS mean_alternatives,
    AVG(backtrack_count) AS mean_backtrack,
    AVG(step_index_normalized) AS mean_step_idx,
    AVG(prior_failure_streak) AS mean_failure_streak,
    AVG(retry_count) AS mean_retry,
    AVG(tool_switch_rate) AS mean_switch_rate
FROM tool_calls WHERE phase = 0
GROUP BY bin;
```

**Expected output:** Table showing how features vary across bins.
**What to look for:** Does hedging_score increase late? Does failure_streak increase? Feature distributions that don't vary across bins won't contribute to the trajectory-position analysis.

### Step 3: Per-Feature Correlation with Correctness

```sql
-- Export for Python analysis (Spearman ρ requires scipy)
SELECT
    tc.decision_id,
    tc.task_id,
    CASE WHEN tc.sequence_number <= 3 THEN 'early'
         WHEN tc.sequence_number <= 7 THEN 'mid' ELSE 'late' END AS bin,
    tc.hedging_score, tc.deliberation_length,
    tc.alternatives_considered, tc.backtrack_count,
    tc.step_index_normalized, tc.prior_failure_streak,
    tc.retry_count, tc.tool_switch_rate,
    CASE WHEN lf.label_final = 'correct' THEN 1 ELSE 0 END AS correct
FROM tool_calls tc
JOIN labels_final lf ON tc.decision_id = lf.decision_id
WHERE tc.phase = 0 AND lf.label_final IN ('correct', 'incorrect');
```

In Python:
```python
from scipy.stats import spearmanr
import pandas as pd

df = pd.read_sql(query, conn)
features = ['hedging_score', 'deliberation_length', 'alternatives_considered',
            'backtrack_count', 'step_index_normalized', 'prior_failure_streak',
            'retry_count', 'tool_switch_rate']

# Per-feature, per-bin correlation
results = []
for bin_name in ['early', 'mid', 'late', 'all']:
    subset = df if bin_name == 'all' else df[df['bin'] == bin_name]
    if len(subset) < 15:  # MIN_CELL_SIZE
        results.append({'bin': bin_name, 'status': 'insufficient_data'})
        continue
    for feat in features:
        rho, p = spearmanr(subset[feat], subset['correct'])
        results.append({
            'bin': bin_name, 'feature': feat,
            'rho': rho, 'p': p, 'n': len(subset),
            'passes_h0': abs(rho) > 0.2  # H0_RHO_THRESHOLD
        })
```

**Expected output: The interaction matrix (per-feature).**

```
                     Early (1-3)    Mid (4-7)    Late (8+)    All
hedging_score        ρ = -0.31*     ρ = -0.24*   ρ = -0.15    ρ = -0.25*
deliberation_length  ρ = -0.18      ρ = -0.22*   ρ = -0.28*   ρ = -0.21*
alternatives         ρ = -0.12      ρ = -0.09    ρ = -0.05    ρ = -0.09
backtrack_count      ρ = -0.26*     ρ = -0.19    ρ = -0.11    ρ = -0.20*
step_index_norm      ρ = N/A        ρ = N/A      ρ = N/A      ρ = -0.15
failure_streak       ρ = -0.35*     ρ = -0.30*   ρ = -0.28*   ρ = -0.31*
retry_count          ρ = -0.22*     ρ = -0.25*   ρ = -0.20*   ρ = -0.23*
tool_switch_rate     ρ = -0.08      ρ = -0.12    ρ = -0.18    ρ = -0.12
```
(* = passes H0 threshold of |ρ| > 0.2)

**What to look for:** Which features pass H0? Do they degrade (lower |ρ|) in the late bin? Does Tier 0 (failure_streak, retry_count) already dominate Tier 1 (hedging_score)?

### Step 4: Logistic Regression (Combined Score)

```python
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.metrics import roc_auc_score

# Leave-one-task-out cross-validation
logo = LeaveOneGroupOut()
tier0_features = ['step_index_normalized', 'prior_failure_streak', 'retry_count', 'tool_switch_rate']
tier1_features = ['hedging_score', 'deliberation_length', 'alternatives_considered', 'backtrack_count']
all_features = tier0_features + tier1_features

for feature_set_name, feature_set in [('tier0', tier0_features), ('tier1', tier1_features), ('combined', all_features)]:
    predictions = np.zeros(len(df))
    for train_idx, test_idx in logo.split(df[feature_set], df['correct'], df['task_id']):
        model = LogisticRegression(C=1.0, penalty='l2')
        model.fit(df[feature_set].iloc[train_idx], df['correct'].iloc[train_idx])
        predictions[test_idx] = model.predict_proba(df[feature_set].iloc[test_idx])[:, 1]
    auc = roc_auc_score(df['correct'], predictions)
    print(f"{feature_set_name}: AUC-ROC = {auc:.3f}")
```

**Expected output:**
```
tier0:    AUC-ROC = 0.68
tier1:    AUC-ROC = 0.65
combined: AUC-ROC = 0.73
```

**Key question:** Does combined > tier0? If yes, Tier 1 linguistic features add value. If no, Tier 0 deterministic features are sufficient and the linguistics don't help.

### Step 5: Critic Signal Quality

```sql
SELECT
    CASE WHEN tc.sequence_number <= 3 THEN 'early'
         WHEN tc.sequence_number <= 7 THEN 'mid' ELSE 'late' END AS bin,
    cc.critic_agreement,
    COUNT(*) AS n,
    SUM(CASE WHEN lf.label_final = 'incorrect' THEN 1 ELSE 0 END) AS n_incorrect
FROM tool_calls tc
JOIN critic_comparisons cc ON tc.decision_id = cc.decision_id
JOIN labels_final lf ON tc.decision_id = lf.decision_id
WHERE tc.phase = 0 AND lf.label_final IN ('correct', 'incorrect')
GROUP BY bin, cc.critic_agreement;
```

**Expected output:**
```
Bin    | Agreement | N  | N_incorrect | Error rate
early  | full      | 18 | 2           | 11%
early  | partial   | 5  | 2           | 40%
early  | disagree  | 7  | 5           | 71%
mid    | full      | 15 | 3           | 20%
mid    | partial   | 4  | 2           | 50%
mid    | disagree  | 6  | 4           | 67%
late   | full      | 8  | 3           | 38%
late   | partial   | 3  | 2           | 67%
late   | disagree  | 4  | 3           | 75%
```

**Derived metrics per bin:**
- Critic precision = n_incorrect_when_disagree / n_disagree
- Critic coverage = n_full + n_partial / n_total
- Critic selective risk = n_incorrect_when_agreed / n_agreed

### Step 6: Three-Layer Signal Comparison (Vuong Test)

```python
from scipy.stats import norm

# Layer 1: Proper scoring rule comparison
# Signal A: logistic regression P(correct | features)  [from Step 4, cross-validated]
# Signal B: P(correct | agreement level)  [three binomial proportions]

# Fit Signal B
for level in ['full', 'partial', 'disagree']:
    mask = df['critic_agreement'] == level
    p_correct_given_level = df.loc[mask, 'correct'].mean()
    df.loc[mask, 'p_B'] = p_correct_given_level

# Already have Signal A from Step 4
df['p_A'] = predictions  # cross-validated

# Log-likelihood differences
df['d'] = np.log(np.where(df['correct']==1, df['p_A'], 1-df['p_A'])) - \
          np.log(np.where(df['correct']==1, df['p_B'], 1-df['p_B']))

# Clustered Vuong test (cluster by task_id)
cluster_means = df.groupby('task_id')['d'].mean()
n_clusters = len(cluster_means)
vuong_stat = cluster_means.mean() / (cluster_means.std() / np.sqrt(n_clusters))
vuong_p = 2 * (1 - norm.cdf(abs(vuong_stat)))

# Per-bin Vuong test (for crossover detection)
for bin_name in ['early', 'mid', 'late']:
    subset = df[df['bin'] == bin_name]
    cluster_means_bin = subset.groupby('task_id')['d'].mean()
    # ... same computation
```

**Expected output:**
```
Overall: Vuong stat = 1.83, p = 0.067 (Signal A marginally better)
Early:   Vuong stat = 2.31, p = 0.021 (Signal A significantly better)
Mid:     Vuong stat = 0.92, p = 0.358 (no difference)
Late:    Vuong stat = -1.47, p = 0.142 (Signal B trending better)
```

**Crossover detected:** Signal A wins early, neither wins mid, Signal B trends better late.

### Step 7: Go/No-Go Decision

Check pre-registered thresholds:
- Combined AUC-ROC ≥ 0.65? → Check
- Critic precision ≥ 0.60? → Check
- Interaction matrix shows variation? → Check (Vuong flips direction across bins)

**Decision output for Phase 1:**
- Arms: ungated + behavioral-gate (Signal A) + adaptive-gate (Signal A early, Signal B late)
- Threshold: selected from risk-coverage curve at coverage ≥ 0.60
- Crossover point: switch to critic at trajectory bin boundary (e.g., step 7)

---

## Phase 1 Analysis Sequence

### Step 8: Gating Effect on Task Success (Layer 3 — Trajectory Level)

```sql
SELECT
    r.condition,
    COUNT(DISTINCT r.task_id) AS n_tasks,
    SUM(CASE WHEN r.task_success = 1 THEN 1 ELSE 0 END) AS n_success,
    ROUND(AVG(CASE WHEN r.task_success = 1 THEN 1.0 ELSE 0.0 END), 3) AS success_rate,
    ROUND(AVG(r.wall_clock_seconds), 1) AS mean_time_sec
FROM runs r
WHERE r.phase = 1
GROUP BY r.condition;
```

**Expected output:**
```
Condition       | Tasks | Success | Rate  | Mean time
ungated         | 15    | 9       | 0.600 | 482s
behavioral-gate | 15    | 11      | 0.733 | 541s
adaptive-gate   | 15    | 12      | 0.800 | 568s
```

### Step 9: Per-Task Directional Consistency

```python
# For each task, did the gated arm do at least as well?
for task_id in task_ids:
    ungated_success = runs[(runs.task_id==task_id) & (runs.condition=='ungated')].task_success.mean()
    gated_success = runs[(runs.task_id==task_id) & (runs.condition=='behavioral-gate')].task_success.mean()
    directional_consistency = gated_success >= ungated_success
```

**Check:** Directional consistency ≥ 0.70 (PRE_REG_DIRECTIONAL_CONSISTENCY_MIN)

### Step 10: pass^k Reliability

```python
# For each task-condition pair, success rate across PASS_K replicates
for condition in conditions:
    for task_id in task_ids:
        replicates = runs[(runs.task_id==task_id) & (runs.condition==condition)]
        p = replicates.task_success.mean()  # single-trial success rate
        pass_k = p ** PASS_K  # pass^3
```

---

## Report Structure

### Final Memo Outline

1. **Executive Summary** (1 paragraph)
   Thesis, key finding, recommendation.

2. **Research Question and Design** (1 page)
   The two-factor question. Why behavioral exhaust. Why cross-model comparison. Phase 0 → Phase 1 structure.

3. **Phase 0 Results: Signal Quality Characterization** (2-3 pages)
   - Interaction matrix (per-feature correlations × trajectory bins)
   - Tier 0 vs Tier 1 comparison (does linguistic signal add value?)
   - Three-layer signal comparison (Vuong + selective risk + trajectory completion)
   - Crossover analysis (where does critic beat behavioral?)
   - Faithfulness check results

4. **Phase 1 Results: Gating Experiment** (2-3 pages)
   - Task success rate by condition
   - Directional consistency
   - pass^k reliability
   - Overhead analysis
   - Case studies (3)

5. **Discussion** (1 page)
   - What worked, what didn't
   - Connection to Anthropic's research (faithfulness, calibration, agent reliability)
   - The ergodicity lesson (per-step vs trajectory-level)

6. **Limitations** (0.5 pages)
   - Single labeler (intra-rater only)
   - Small n (10+15 tasks)
   - Single model (Sonnet 4.6)
   - Hyland lexicon may not be optimal for LLM reasoning
   - No control for task difficulty in late-bin analysis

7. **Conclusion and Recommendations** (0.5 pages)
   - Deploy or don't deploy
   - Phase 2 directions (Opus, modal decomposition, more tasks)

### Required Plots

1. **Interaction matrix heatmap** — features × bins, color = |ρ|
2. **Risk-coverage curves** — one per signal type, overlaid, per bin
3. **Vuong test results** — bar chart of V-statistic per bin with significance markers
4. **Feature importance** — logistic regression coefficients (Tier 0 vs Tier 1)
5. **Trajectory completion by condition** — bar chart with CI
6. **Faithfulness perturbation effect** — before/after ρ scatter

### Required Tables

1. **Data quality summary** — calls per bin, base rate, label source distribution
2. **Per-feature interaction matrix** — ρ values with significance markers
3. **Three-layer comparison** — Vuong, selective risk, completion rate per signal per bin
4. **Phase 1 results** — success rate, overhead, directional consistency per condition
5. **pass^k reliability** — per condition

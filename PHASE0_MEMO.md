# UGA Phase 0 Memo: Behavioral Signals in Coding Agent Reasoning Traces

## Summary

We built a research harness that captures and analyzes the full behavioral exhaust of Claude Sonnet 4.6 solving SWE-bench coding tasks. Across 183 independently validated runs on 75 unique tasks (49.2% pass rate), we find that **behavioral structure, not linguistic hedging, is associated with agent task success**. Three features survive Bonferroni correction after controlling for repository-level heterogeneity, but only two pass a within-repo permutation test for faithfulness.

**REVISION NOTE (2026-03-29):** The original headline finding about reasoning_to_action_alignment does NOT survive the corrected within-repo permutation test (p=0.35). The original effect was inflated by between-repo confounding. The revised headline: **deliberation_length** (per-call reasoning length) is the most robust Sonnet-specific feature, surviving CWC, permutation, and cross-wave replication. See Section 10 for the corrected statistical picture.

---

## 1. Research Question

*What determines the quality of uncertainty signals for agent task-success decisions?*

Two orthogonal factors:
1. **Signal source:** introspective (from the agent's own reasoning) vs. extrospective (from an external critic)
2. **Trajectory position:** does signal quality degrade as the agent's context fills?

Phase 0 addresses the introspective signal and trajectory degradation. Phase 1 will test extrospective signals and gating interventions.

---

## 2. Method

### 2.1 Task Selection
75 SWE-bench Lite tasks from 9 repositories (django, sympy, pytest-dev, scikit-learn, pylint-dev, psf, sphinx-doc, pallets, astropy). Selected for blended ~50% pass rate.

### 2.2 Agent Configuration
Claude Sonnet 4.6 via `claude -p --model sonnet --output-format stream-json --verbose`. Ungated (no intervention). 30-minute timeout per task. Agent receives the bug description and is instructed to fix it and run tests.

### 2.3 Data Collection
Full stream-json traces captured and stored in SQLite (WAL mode). Each trace contains:
- Every tool call (tool name, parameters, result, is_error flag)
- Reasoning text preceding each tool call (when present, 28% of calls)
- Sequence numbers and timestamps

### 2.4 Independent Validation
Agent self-report is NOT used for labeling. Validation is independent:
1. Copy the original repository to a fresh temporary directory
2. Extract Write and Edit operations from the raw trace
3. Apply edits to the fresh copy
4. Create a Python 3.10 virtual environment with SWE-bench-pinned dependencies
5. Run the specific FAIL_TO_PASS tests from the SWE-bench dataset
6. Label based on test exit code

96% of runs were successfully validated. 4 runs were unrecoverable (infrastructure failures). Validation provenance is tracked per-run.

### 2.5 Feature Extraction
23 features across three tiers, all using **mean aggregation** (not sum) to control for the task-length confound (failing tasks average 22.9 state-modifying calls vs. 16.6 for passing).

**Tier 0 — Structural** (from tool sequence, no text analysis):
fail_streak_max, early_error_rate, first_edit_position, unique_files_touched, edit_churn_rate, recovery_rate, fail_then_switch_rate, test_run_count, n_calls (control)

**Tier 1 — Linguistic, Hyland lexicon** (per-token density):
hedging_score, deliberation_length, backtrack_count, verification_score, planning_score

**Tier 2 — Domain-specific linguistic** (per-token density):
metacognitive_density, tentative_density, insight_density, instead_contrast_density, self_directive_density, wrong_stuck_density, causal_density, precision_naming_score

**Interaction:**
reasoning_to_action_alignment (does reasoning mention the file about to be edited?)

### 2.6 Statistical Methods
- **Primary (as reported):** Within-repo Spearman correlations for sympy (n=87, 41.4% pass) and django (n=44, 84.1% pass) separately, combined via Fisher's method (the "CWC" approach).
- **Correction:** Bonferroni at alpha/23 = 0.0022 for the pooled analysis. CWC and permutation tests provide alternative multiple-comparison safeguards.
- **Faithfulness:** Within-repo permutation test (10,000 permutations, labels shuffled within repo). Also: within-task permutation on 7 Sonnet tasks with mixed outcomes.
- **Note:** The original design specified mixed-effects logistic regression. The actual reported results use rank correlations with Fisher combination. The mixed-effects analysis was run but is not the primary reported method.

---

## 3. Data

| Metric | Value |
|--------|-------|
| Total validated runs (Sonnet) | 183 |
| Unique tasks | 75 |
| Pass / Fail | 90 / 93 (49.2%) |
| State-modifying tool calls | ~3,600 |
| Calls with reasoning text | ~1,170 (28%) |
| Repos | 9 |
| Waves | 2 (pilot + protocol) |

### Per-repository pass rates

| Repo | Runs | Pass rate |
|------|------|-----------|
| sympy | 80 | 47% |
| django | 44 | 84% |
| pytest-dev | 35 | 29% |
| scikit-learn | 9 | 0% |
| pylint-dev | 5 | 80% |
| psf | 4 | 25% |
| sphinx-doc | 3 | 0% |
| pallets | 2 | 100% |
| astropy | 2 | 0% |

---

## 4. Results

### 4.1 Primary Analysis: Features Surviving Bonferroni

Three features had raw p < 0.0022 in the mixed-effects model. However, their Bonferroni-adjusted p-values (raw p * 23 features) do NOT all fall below 0.05:

| Feature | Coefficient | Raw p | Bonf-adj p | Survives Bonferroni (adj p < 0.05)? | Direction |
|---------|------------|-------|-----------|--------------------------------------|-----------|
| reasoning_to_action_alignment | +1.133 | 0.00018 | 0.004 | Yes (but RETRACTED -- see note) | Naming the target file associated with success |
| first_edit_position | +0.790 | 0.00019 | 0.004 | Yes | Exploring before editing associated with success |
| deliberation_length | +0.708 | 0.00062 | 0.014 | Yes | Longer per-call reasoning associated with success |

**RETRACTION NOTE:** reasoning_to_action_alignment survives Bonferroni in the pooled analysis but does NOT survive the within-repo permutation test (p=0.35). The pooled effect was inflated by between-repo confounding. This feature is no longer considered a reliable signal.

### 4.2 Within-Repo Analysis

**Sympy** (n=80, 47% pass — the balanced-difficulty repo):

| Feature | ρ | p |
|---------|---|---|
| instead_contrast_density | +0.318 | 0.005 |
| fail_streak_max | -0.301 | 0.009 |
| metacognitive_density | +0.254 | 0.028 |
| early_error_rate | -0.270 | 0.019 |

**Django** (n=44, 84% pass):

| Feature | ρ | p |
|---------|---|---|
| first_edit_position | +0.493 | 0.0007 |
| deliberation_length | +0.465 | 0.0015 |

**Cross-repo replication:** deliberation_length is significant in django (rho=+0.465) and shows a consistent positive direction in sympy (rho=+0.214, p=0.046). The sympy table above does not list it because it was below the display threshold, but it appears in the CWC combined analysis. This makes it the most consistent Sonnet-specific finding.

### 4.3 Null Controls Confirmed

| Control | Result |
|---------|--------|
| Hyland hedging_score (209 academic hedge terms) | p = 0.60, ρ = near zero. Sonnet does not use academic hedging when coding. |
| Random noise column | p = 0.52. Pipeline does not find spurious signal. |

### 4.4 Trajectory Degradation

Signal quality degrades over the trajectory:

| Position | alignment ρ | deliberation ρ |
|----------|------------|----------------|
| Early (0-33%) | +0.242 (p=0.001) | +0.180 (p=0.016) |
| Mid (33-67%) | +0.165 (p=0.029) | +0.166 (p=0.028) |
| Late (67-100%) | +0.026 (p=0.735) | +0.038 (p=0.615) |

Both features are predictive in the early and middle trajectory, and completely non-predictive in the late trajectory. By the final third, the agent has either found the fix or is committed to a wrong approach. Reasoning quality no longer discriminates.

**Implication for gating:** A behavioral gate should focus on early and mid-trajectory decisions. Late-trajectory gating based on reasoning features is pointless.

### 4.5 Cross-Wave Stability

Features replicate across independently collected datasets:

| Feature | Pilot (n=103) | Protocol wave (n=77) |
|---------|--------------|---------------------|
| alignment | ρ=+0.300 (p=0.002) | ρ=+0.285 (p=0.012) |
| deliberation | ρ=+0.320 (p=0.001) | ρ=+0.273 (p=0.016) |
| first_edit | ρ=+0.241 (p=0.014) | ρ=+0.039 (p=0.736) |

alignment and deliberation replicate. first_edit_position does not replicate in wave 2 alone.

### 4.6 Faithfulness Test

Within-task permutation test: for 7 tasks with both passing and failing replicates (35 runs total), randomly reassign outcome labels within each task 10,000 times. If the observed feature difference exceeds the permutation distribution, the feature measures run-level reasoning quality, not task-level properties.

| Feature | Observed diff | Permutation p | Verdict |
|---------|--------------|---------------|---------|
| reasoning_to_action_alignment | +0.283 | 0.007 | **FAITHFUL** |
| deliberation_length | +56.1 chars | 0.043 | **FAITHFUL** |
| first_edit_position | +0.178 | 0.076 | borderline |

reasoning_to_action_alignment and deliberation_length are faithful: they measure properties of the specific run's reasoning, not the task. On the same task, passing replicates have 5x higher alignment (0.39 vs 0.08) and 2x more deliberation per call.

### 4.7 Thinking Block Discovery: A Second Layer of Signal

A parser bug in `trace_collector.py` was reading `block.get("text")` instead of `block.get("thinking")` when extracting thinking blocks from the stream-json trace. The effect: our original 23-feature analysis operated on **agent messages**, not internal thinking. The bug is fixed.

**Scale of the recovered signal.** Re-running extraction over all 183 validated Sonnet runs:

| Layer | Runs with content | Total characters | Avg chars/run |
|-------|------------------|-----------------|---------------|
| Internal thinking | 183 / 183 (100%) | ~2.0 million | ~10,800 |
| Agent messages | — | — | ~1,200 |

Genuine internal reasoning is present in every run and is roughly 10x longer per run than the polished agent messages. Thinking coverage is not 28%: that figure applied to per-call reasoning annotations in the original schema. The thinking blocks contain continuous, unfiltered deliberation across the full run.

**What the exhaust analysis finds.** A separate analysis (`exhaust_analysis_results.md`) computed Spearman correlations for the same linguistic features extracted from thinking vs. messages:

| Feature | Source | ρ | p | Interpretation |
|---------|--------|---|---|----------------|
| tentative_density | **Thinking** | -0.346 | 0.003 | Internal doubt ("let me try", "maybe", "not sure") associated with failure |
| insight_density | **Messages** | +0.248 | 0.034 | Expressed correction ("actually", "I understand") associated with success |

Two results stand out. First, `thinking_tentative_density` is the stronger signal and comes from the thinking layer — the same feature extracted from messages (ρ = -0.204, p = 0.083) does not survive. Internal hedging is more diagnostic than expressed hedging. Second, `message_insight_density` is the stronger signal for the correction feature — the thinking-layer version is near zero. This double dissociation suggests the two layers carry structurally different information: **internal doubt lives in thinking; expressed correction lives in messages**.

**Relationship to the original Bonferroni features.** The three features that survived Bonferroni correction in Section 4.1 (reasoning_to_action_alignment, first_edit_position, deliberation_length) were computed from agent messages and call-level reasoning annotations, not from thinking blocks. They remain valid. The thinking block analysis is additive: it opens a new measurement dimension that the original 23 features did not access.

**Implication for the Codex cross-model comparison.** The parser bug turns out to be favorable for the cross-model comparison (Phase 1). Codex and Sonnet produce thinking blocks in different formats; comparing them directly would require careful normalization. Since the original Bonferroni features are derived from agent messages — which both models produce in a common polished format — the Phase 1 comparison is cleaner than initially feared.

### 4.8 Collinearity

Notable correlated pairs among significant features:
- backtrack_count ↔ metacognitive_density: r = 0.90 (measuring same signal)
- fail_streak_max ↔ early_error_rate: r = 0.64 (measuring same signal)
- test_run_count ↔ n_calls: r = 0.90 (confounded with task length)

---

## 5. Findings That Failed

| Feature | Expected | Actual | Why it failed |
|---------|----------|--------|---------------|
| Hyland hedging score | Predict uncertainty | Dead (ρ ≈ 0) | Sonnet doesn't use academic hedge words when coding |
| verification_score | Negative with success | Null (ρ = 0.02) | Ubiquitous in all Sonnet reasoning, not discriminative |
| planning_score | Negative with success | Null (ρ = 0.09) | "First", "then", "next" are default Sonnet style |
| recovery_rate | Positive with success | Negative (ρ = -0.15) | Recovery from infrastructure errors (pip, imports) is noise |
| fail_then_switch_rate | Positive with success | Negative (ρ = -0.37) | Tool-switching after errors is flailing, not diagnosis |
| precision_naming_score | Positive with success | Null (ρ = 0.04) | Backticks and identifiers are ubiquitous in all reasoning |
| causal_density | Positive with success | Null (ρ = -0.03) | "Because"/"since" are general discourse markers |

---

## 6. Methodological Contributions

### 6.1 The Task-Length Confound
Failing tasks produce 38% more state-modifying tool calls than passing tasks (22.9 vs 16.6). Any feature aggregated via sum is confounded. Mean aggregation and partial correlation controlling for n_calls are required. This confound **suppressed** the metacognitive signal in raw correlations (ρ went from +0.308 to +0.494 after correction).

### 6.2 Independent Validation Matters
Agent self-reported test results inflated 3 features to significance that disappeared under independent validation. The lesson: never use the agent's own test output as ground truth. Replay the edits on a fresh environment and run the tests yourself.

### 6.3 Repository Heterogeneity
Django passes at 84%, sympy at 47%. Failing to control for this produces spurious correlations. Mixed-effects models with repo as random/fixed effect are required. Different features predict in different repos, which is itself a finding.

---

## 7. Interpretation

Runs that succeed at coding tasks show two behavioral patterns (one original headline finding has been retracted):

1. ~~**They name what they're going to change before changing it.**~~ **RETRACTED.** reasoning_to_action_alignment does not survive within-repo permutation (p=0.35). The pooled effect was a between-repo confound.

2. **They think more per action.** deliberation_length (per-call, not total) is higher in passing runs. This is the most robust Sonnet-specific association, surviving CWC (p=0.003), permutation (p=0.0004), and cross-wave replication.

3. **They read before they write.** first_edit_position measures how deep into the trajectory the agent gets before making its first code change. Runs that explore the codebase before committing to edits succeed more often. However, this did not replicate in wave 2 alone.

These features share a common thread: **deliberate, informed action** is associated with success. The signal is not in what uncertainty words the agent uses (hedging is dead). It is in whether the agent's behavior shows evidence of exploration before acting.

This association degrades over the trajectory. In the early and middle stages, reasoning features discriminate pass from fail. In the late stage, they do not. The implication: a behavioral gate should focus on early trajectory, when the signal is strongest.

---

## 8. Cross-Model Comparison (Codex GPT-5.4)

**Added 2026-03-28 (corrected 2026-03-29).** 190 validated runs using Codex GPT-5.4 on 70 of the Sonnet task set. Full analysis in `context/phase0_final_deliverable.md`.

### 8.1 Aggregate Comparison

| Model | Validated Runs | Pass Rate | Unique Tasks |
|-------|---------------|-----------|-------------|
| Sonnet 4.6 | 183 | 49.2% | 75 |
| Codex GPT-5.4 | 190 | 41.1% | 70 |
| **Combined** | **373** | **45.0%** | **75** |

Shared tasks: 70. Matched-set pass rates: Sonnet 49.4% (88/178), Codex 41.1% (78/190).
Task-level agreement: 87.1% (61/70 shared tasks, Cohen's kappa = 0.742).

### 8.2 Features That Survive Cross-Model Testing

Only two features are significantly associated with success in BOTH models within the same repository:

| Feature | Sonnet/sympy | Codex/sympy | Direction |
|---------|-------------|-------------|-----------|
| fail_streak_max | rho=-0.294, p=0.006 | rho=-0.296, p=0.009 | Error streaks associated with failure |
| early_error_rate | rho=-0.273, p=0.011 | rho=-0.282, p=0.012 | Early errors associated with failure |

Both are Tier 0 structural features. No linguistic feature shows a significant association in the same direction for both models.

### 8.3 Polarity Flips

One linguistic feature shows a confirmed polarity flip (significant in both models with opposite signs) in sympy. Two others show suggestive directional reversals:

| Feature | Sonnet rho (p) | Codex rho (p) | Status |
|---------|---------------|---------------|--------|
| instead_contrast_density | +0.282 (0.008) | -0.264 (0.020) | **CONFIRMED** -- both significant, opposite signs |
| backtrack_count | +0.359 (0.0006) | -0.108 (>0.05) | Suggestive -- Codex side not significant |
| metacognitive_density | +0.138 (>0.05) | -0.261 (0.021) | Suggestive -- Sonnet side not significant |

The confirmed flip on `instead_contrast_density` is the most informative Sonnet-specific cross-model finding. The other two are directional hypotheses for Phase 1 testing.

### 8.4 The Interaction Effect

In Sonnet/sympy, deliberation_length x think_diagnostic_precision shows a dramatic interaction:

- High deliberation + High precision: 73% pass (n=22)
- High deliberation + Low precision: 23% pass (n=22)
- Low deliberation + High precision: 32% pass (n=22)
- Low deliberation + Low precision: 38% pass (n=21)

Interaction bonus: +0.56. Neither feature alone is sufficient. In Codex, the same interaction is much weaker (+0.13).

### 8.5 Diagnostic Precision Dissociation

On 6 tasks where Sonnet passes but Codex fails, Sonnet's internal reasoning contains 4-16x more code-specific references per thousand characters. When Sonnet outperforms Codex, the difference is in how precisely it reasons about code artifacts -- not in how much it reasons.

---

## 9. The CWC Methodology

The CWC (Confound-Within-Confound) approach addresses the central threat to validity: repository-level pass rate differences.

**Method:** Compute within-repo Spearman correlations for each major repo (django, sympy) separately, then combine using Fisher's method (chi-squared = -2 * sum(log(p_i)), df = 2k). This controls for between-repo confounds (different pass rates, different codebases). Features must show consistent direction across repos to survive.

**Additional validation:** Within-repo permutation test (10,000 permutations) shuffles success labels independently within each repo, preserving repo-level pass rates. A feature survives only if its observed effect exceeds 95% of permuted effects. Note: this controls for between-repo confounds but NOT for within-repo task difficulty variation. A within-task permutation (shuffling labels within tasks with mixed outcomes) would be stronger but requires sufficient mixed-outcome tasks.

**Note on terminology:** An earlier version of this analysis (research-narrative.md, Section 11) used a Mundlak-style cluster-mean centering decomposition. The final analysis uses the Fisher-combined within-repo approach described above. The Mundlak results are superseded.

**What it revealed:** Several features that appeared significant in the pooled analysis (reasoning_to_action_alignment, metacognitive_density) do NOT survive the permutation test. The original memo overestimated their strength because between-repo confounding inflated the effects.

**What survives CWC + permutation:**
- Sonnet: deliberation_length (perm p=0.0004), first_edit_position (perm p=0.001)
- Codex: think_t_compat_fraction (perm p=0.006), instead_contrast_density (perm p=0.007)

---

## 10. Corrected Statistical Picture

### What Stands from the Original Memo

1. **Deliberation_length is associated with success in Sonnet** -- this is the most robust finding. Survives within-repo, CWC, and permutation tests. rho=+0.21 to +0.40 depending on repo.
2. **Hedging is dead** -- confirmed across both models. Academic hedging vocabulary carries no signal.
3. **Signal degrades over trajectory** -- early features predict better than late features.
4. **The thinking/message dissociation** -- confirmed with additional data. "Actually" has opposite polarity in thinking vs messages.

### What Is Revised

1. **reasoning_to_action_alignment** -- previously reported as the strongest Bonferroni survivor and headline finding. Does NOT survive the corrected within-repo permutation test (p=0.35). The original finding was inflated by between-repo confounding. **RETRACTED** as a standalone signal.
2. **first_edit_position** -- previously Bonferroni-significant. Still survives CWC and permutation (perm p=0.001) but did not replicate in wave 2 alone (rho=+0.039, p=0.736).
3. **metacognitive_density** -- previously significant in Sonnet. Now known to show directional reversal in Codex (significant there, not in Sonnet at the same threshold), suggesting it is model-specific and possibly confounded.
4. **Feature universality** -- previously assumed features would generalize. Now established that linguistic features are model-specific; only structural features (fail_streak_max, early_error_rate) transfer across models.

### The Revised Evidence Hierarchy

| Level | Features | Evidence |
|-------|----------|----------|
| Gold (survives all tests, both models) | fail_streak_max, early_error_rate | Structural, generalizable |
| Silver (survives CWC + permutation, model-specific) | deliberation_length (Sonnet: perm p=0.0004), think_t_compat_fraction (Codex: perm p=0.006) | Robust within model |
| Moderate (survives CWC + permutation, weaker) | first_edit_position (Sonnet: perm p=0.001, no wave-2 replication), instead_contrast_density (Codex: perm p=0.007) | Real signal, noisier |
| Interaction (exploratory) | deliberation x diagnostic_precision (Sonnet) | Strongest observational association (73% pass), needs formal interaction model |
| Retracted | reasoning_to_action_alignment | Perm p=0.35. Between-repo confound. |
| Null | hedging_score, verification_score, precision_naming_score | Dead in all analyses |

---

## 11. Limitations (Updated)

1. **All findings are correlational.** No interventions. Phase 1 will test whether gating on these features changes outcomes.
2. **Reasoning coverage:** Only 28% of tool calls have per-call reasoning annotations. Thinking block coverage is 100%.
3. **Model-specificity of linguistic features.** The confirmed polarity flip and suggestive reversals mean no single linguistic feature set generalizes across models.
4. **Repository heterogeneity:** 9 repos with dramatically different pass rates. CWC methodology controls for this but limits power.
5. **Codex convergence.** +10.3pp improvement in Codex sympy pass rate from early to late runs. If genuine, early Codex runs are biased.
6. **Thinking block format differences.** Sonnet extended thinking and Codex reasoning items are architecturally different. Per-call reasoning coverage differs (28.8% vs 60.1%). Polarity differences could reflect format differences.
7. **Interaction effects underpowered.** The deliberation x precision interaction (n~22 per quadrant) needs a formal interaction model.
8. **5 Sonnet-only tasks.** 5 tasks were run on Sonnet but not Codex. Codex task set is a strict subset.
9. **No predictive evaluation.** We report associations, not predictions. No held-out AUC or calibration curve.

---

## 12. Phase 1 Implications (Revised)

**Gate design must be model-specific.** Based on Phase 0 cross-model findings:

For Sonnet:
- Primary: deliberation_length per-call threshold (perm p=0.0004)
- Secondary: deliberation x diagnostic_precision interaction gate
- Focus on early + mid trajectory

For Codex:
- Primary: think_t_compat_fraction (environment struggle detection, perm p=0.006)
- Secondary: fail_streak_max (consecutive error detection)
- Focus on early trajectory

For both models:
- early_error_rate gate: intervene after first error streak > 2

**What Phase 1 must test:**
- Does gating on model-specific features improve task success? (intervention test)
- Is the deliberation x precision interaction causal? (prompt augmentation test)
- Can a meta-gate detect which model is running from behavioral exhaust?
- Do structural features (fail_streak_max) generalize beyond these two models?

---

## 13. Pipeline

- 373 validated runs (183 Sonnet + 190 Codex) across 75 SWE-bench Lite tasks
- Full analysis: `context/phase0_final_deliverable.md`
- Paper outline: `context/paper_outline.md`
- 86 unit tests (63 feature extraction + 23 trace classification)
- 3 full Codex adversarial audits with all findings fixed
- Independent validation via pre-built environments in `/envs/`
- CWC methodology with within-repo permutation tests (10,000 permutations)
- Random noise control column confirms clean pipeline

**Code:** 
**Data:** data/uga_phase0_complete_final.db (373 validated runs, read-only backup)
**Protocol:** data/protocol_tasks.json (71 locked tasks)

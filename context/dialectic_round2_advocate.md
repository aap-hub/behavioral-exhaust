# Dialectic Round 2: Advocate Response

**Date:** 2026-03-28
**Responding to:** context/dialectic_round1_critic.md (Round 1 Critic Summary)
**DB:** data/uga_phase0_complete_final.db (read-only)
**Method:** All analyses use corrected feature extraction that handles both Claude (thinking blocks) and Codex (reasoning items) stream formats. Error detection uses content-based pattern matching for Claude (where `is_error` is always False) and exit codes for Codex.

---

## PREAMBLE: WHAT THIS ROUND IS ABOUT

The critic made four specific data requests. This response addresses each with analysis, not argument. The results are unfavorable to the advocate's position on most points. This document reports them honestly.

---

## RESPONSE 1: TASK-LEVEL META-ANALYSIS FOR DISAGREEMENT

**Critic's request:** "n=5 tasks, pseudoreplication risk. Need task-level meta-analysis."

### 1.1 Setup

Across 70 shared tasks, 8 show majority-outcome disagreement between models:

| Task | Sonnet | Codex | Winner |
|------|--------|-------|--------|
| pallets__flask-4045 | 2/2 pass | 0/3 pass | Sonnet |
| pylint-dev__pylint-6506 | 2/2 | 0/2 | Sonnet |
| sympy__sympy-15609 | 2/2 | 0/4 | Sonnet |
| sympy__sympy-16988 | 2/2 | 0/2 | Sonnet |
| sympy__sympy-21612 | 6/9 | 0/3 | Sonnet |
| sympy__sympy-15308 | 1/2 | 2/2 | Codex |
| sympy__sympy-19007 | 0/2 | 2/2 | Codex |
| sympy__sympy-21614 | 0/3 | 3/4 | Codex |

### 1.2 Cross-Model Task-Level Sign Test

For each disagreement task, computed (all-pass-runs mean) - (all-fail-runs mean) for each feature, pooling across models within the same task.

| Feature | N tasks | + | - | Mean gap | Sign p |
|---------|---------|---|---|----------|--------|
| think_diag_prec | 8 | 5 | 3 | +2.264 | 0.7266 |
| think_pivots_kc | 8 | 6 | 2 | +0.073 | 0.2891 |
| think_instead_d | 8 | 6 | 2 | +0.054 | 0.2891 |
| n_calls | 8 | 6 | 2 | +19.385 | 0.2891 |
| think_compat_frac | 8 | 4 | 4 | -0.003 | 1.0000 |
| think_tentative_kc | 8 | 3 | 5 | -1.207 | 0.7266 |
| think_doubt_density | 8 | 3 | 5 | -0.012 | 0.7266 |
| fail_streak_max | 8 | 3 | 5 | -0.490 | 0.7266 |

**Result: NO feature reaches significance by task-level sign test.** The minimum achievable two-sided p with 8 observations is 0.0078 (all 8 same sign). No feature achieves better than 6/2 (p=0.2891).

### 1.3 Within-Model Task-Level Sign Test

Restricted to tasks with 3+ replicates and mixed outcomes within a single model (the purest within-task test).

**Sonnet (6 mixed-outcome tasks: pytest-6116, pytest-7220, pytest-7432, sympy-11870, sympy-13895, sympy-21612):**

| Feature | N | + | - | Mean gap | Sign p |
|---------|---|---|---|----------|--------|
| think_diag_prec | 6 | 3 | 3 | +0.478 | 1.000 |
| think_pivots_kc | 6 | 3 | 3 | -0.011 | 1.000 |
| think_compat_frac | 6 | 3 | 3 | -0.003 | 1.000 |
| think_tentative_kc | 6 | 4 | 2 | +0.029 | 0.688 |
| think_actually_kc | 6 | 4 | 2 | +0.108 | 0.688 |
| think_instead_d | 6 | 4 | 2 | +0.033 | 0.688 |
| think_doubt_density | 6 | 4 | 2 | -0.008 | 0.688 |
| n_calls | 6 | 2 | 4 | +3.167 | 0.688 |
| fail_streak_max | 6 | 3 | 3 | +0.347 | 1.000 |
| think_chars | 6 | 1 | 5 | -10765 | 0.219 |

**Codex (5 mixed-outcome tasks: django-11905, sympy-18057, sympy-21614, sympy-21627, sympy-23262):**

| Feature | N | + | - | Mean gap | Sign p |
|---------|---|---|---|----------|--------|
| think_diag_prec | 5 | 2 | 3 | -0.477 | 1.000 |
| fail_streak_max | 5 | 4 | 0 | +0.533 | 0.125 |
| All others | 5 | mixed | - | - | >0.50 |

**Result: NO feature reaches significance at the task level for either model.** The critic was correct: the Round 1 Mann-Whitney results on disagreement tasks were pseudoreplicated. Once we analyze at the task level (the correct unit), there is no significant signal.

### 1.4 Honest Assessment

The Round 1 disagreement analysis presented Mann-Whitney z-scores like -4.227 (p<0.0001) for think_diag_prec on 14 vs 14 runs across 5 tasks. These were run-level statistics on a task-level hypothesis. The effective sample size is 5 tasks, not 14 runs. With 5-8 tasks, even a perfect signal (all same sign) barely reaches significance. The critic identified this correctly and the task-level analysis confirms: the disagreement evidence does not survive proper handling of the unit-of-analysis.

---

## RESPONSE 2: LENGTH-MATCHED THINKING/MESSAGE DOUBT COMPARISON

**Critic's request:** "Real but partly genre difference. Need length-matched comparison."

### 2.1 Method

For each run with thinking > 500 chars and messages > 100 chars, we subsampled 100 random contiguous substrings of the thinking text, each of length equal to the run's total message text. We then computed doubt marker density on these subsamples and compared to the message doubt density.

### 2.2 Results

**Sonnet (n=164 runs):**

| Metric | Value |
|--------|-------|
| Raw thinking doubt density | 1.641 per kchar |
| Raw message doubt density | 0.198 per kchar |
| **Length-matched thinking density** | **1.589 per kchar** |
| Suppression ratio (raw) | 8.3x |
| **Suppression ratio (length-matched)** | **8.0x** |
| Length-matching effect | 3% reduction (negligible) |
| Sign test (matched_think > msg) | 140+ / 2- / 22 tied, p < 0.000001 |

By outcome:
| Outcome | Matched think density | Message density | Ratio |
|---------|----------------------|-----------------|-------|
| PASS | 1.282 | 0.143 | 9.0x |
| FAIL | 1.848 | 0.243 | 7.6x |

**Codex (n=190 runs):**

| Metric | Value |
|--------|-------|
| Raw thinking doubt density | 1.893 per kchar |
| Raw message doubt density | 0.037 per kchar |
| **Length-matched thinking density** | **1.972 per kchar** |
| Suppression ratio (raw) | 51.1x |
| **Suppression ratio (length-matched)** | **53.3x** |
| Length-matching effect | +4% (slight increase, within noise) |
| Sign test (matched_think > msg) | 190+ / 0- / 0 tied, p < 0.000001 |

By outcome:
| Outcome | Matched think density | Message density | Ratio |
|---------|----------------------|-----------------|-------|
| PASS | 1.873 | 0.038 | 49.7x |
| FAIL | 2.041 | 0.037 | 55.8x |

### 2.3 Assessment

**The dissociation survives length-matching completely.** Length-matching reduces the Sonnet suppression ratio from 8.3x to 8.0x -- a 3% change. For Codex, it actually increases slightly. The sign test is overwhelmingly significant (140/142 for Sonnet, 190/190 for Codex).

This is not a genre effect. Even when we compare thinking and message text at identical lengths, thinking contains 8-53x more doubt markers than messages. The suppression is real and operates per-character, not per-document.

**Note on the revised ratios vs Round 1:** Round 1 reported 16.7x and 43.5x suppression ratios. The current analysis finds 8.3x and 51.1x. The difference is due to corrected feature extraction: Round 1 may have used a different thinking extraction method (the `thinking` key was initially missed due to a parsing error, causing zeros for Codex in the first extraction attempt). The corrected extraction, which properly handles both Claude (`thinking` key inside thinking blocks) and Codex (`text` key inside reasoning items), is what these numbers reflect. The qualitative conclusion is unchanged.

---

## RESPONSE 3: CROSS-TASK WITHIN-REPLICATE FISHER COMBINATION

**Critic's request:** "Gather ALL tasks with 3+ replicates and any outcome variance. For each, run the within-task permutation on the top features. Combine p-values across tasks using Fisher's method."

### 3.1 Sonnet: 6 Mixed-Outcome Tasks

Individual within-task exact permutation tests:

| Feature | Task | N (pass/fail) | Obs diff | Perm p |
|---------|------|---------------|----------|--------|
| think_compat_frac | sympy-21612 | 9 (6/3) | -0.0012 | **0.012** |
| think_diag_prec | sympy-21612 | 9 (6/3) | -1.136 | 0.131 |
| think_pivots_kc | sympy-21612 | 9 (6/3) | +0.127 | 0.214 |
| think_doubt_density | sympy-21612 | 9 (6/3) | +0.246 | 0.262 |
| n_calls | pytest-7432 | 8 (2/6) | -14.667 | 0.321 |
| fail_streak_max | pytest-7220 | 7 (3/4) | +1.750 | 0.171 |
| All others | various | 3-8 | various | >0.25 |

Only one individual test survives: think_compat_frac on sympy-21612 (p=0.012, exact permutation, C(9,6)=84 permutations).

**Fisher combination across 6 tasks:**

| Feature | Fisher stat | Fisher p | Tasks with p<0.05 |
|---------|-------------|----------|-------------------|
| think_compat_frac | 17.327 | 0.137 | 1/6 |
| think_diag_prec | 10.767 | 0.550 | 0/6 |
| think_pivots_kc | 8.712 | 0.728 | 0/6 |
| think_doubt_density | 7.943 | 0.791 | 0/6 |
| n_calls | 6.706 | 0.877 | 0/6 |
| fail_streak_max | 8.048 | 0.782 | 0/6 |
| think_chars | 5.292 | 0.947 | 0/6 |

### 3.2 Codex: 5 Mixed-Outcome Tasks

No individual test reaches significance. All Fisher combination p-values > 0.70.

### 3.3 Assessment

**Fisher combination FAILS for all features.** Even think_compat_frac, which is individually significant on sympy-21612, does not survive Fisher combination across the 6 Sonnet tasks (Fisher p=0.137). The signal on sympy-21612 does not generalize to other tasks.

The fundamental problem is power. With 6 tasks and minimum p-values of 0.33 (for C(3,1)=3 permutations), the Fisher statistic cannot accumulate enough evidence. But we cannot claim this is merely a power failure -- the directional consistency is also absent. For think_compat_frac, the sign is 3+/3- across 6 tasks. There is no trend to detect even if we had more power.

---

## RESPONSE 4: HONEST SUMMARY -- FINAL CLAIM SET

### What Survives Round 2

**Tier A: Confirmed (p < 0.001, robust to all challenges):**

1. **Thinking/message doubt dissociation.** Thinking text contains 8-53x more doubt markers than message text, after length-matching. Sign test p < 0.000001 (Sonnet: 140/142, Codex: 190/190). This is an architectural observation, not a predictive claim. It survives the critic's length-matching challenge completely.

**Tier B: Confirmed on a single task (p < 0.05, exact permutation, but fails to generalize):**

2. **think_compat_frac on sympy-21612.** Exact permutation p=0.012 (1/84 permutations). Fail runs have 2.2x higher environment-compatibility language in thinking. This is the ONLY feature that reaches significance by within-task exact permutation on any task. It fails Fisher combination across tasks (p=0.137) and shows no directional consistency (3+/3- across 6 tasks).

**Tier C: Descriptive patterns (directionally suggestive, nowhere near significance):**

3. **Cross-task disagreement direction.** 3 features show 6/8 task agreement in the disagreement analysis (think_pivots_kc, think_instead_d, n_calls), but p=0.29 by sign test. With 8 tasks, this is the best achievable without perfect unanimity.

4. **Fail runs produce longer thinking.** In Sonnet, 5/6 tasks show fail runs having longer thinking text (sign p=0.22). Consistent direction but not significant.

### What Is Retracted from Round 1

| Round 1 Claim | Status | Reason |
|---------------|--------|--------|
| Disagreement Mann-Whitney (z=-4.2) | **RETRACTED** | Pseudoreplication. Task-level sign test p=0.73 |
| think_pivots_kc within-task (p=0.024) | **RETRACTED** | Cannot reproduce. With corrected extraction, p=0.214 (broad definition) and p=0.226 (strict definition) on sympy-21612. The Round 1 p=0.024 likely used a different pipeline or feature definition that we cannot reconstruct. |
| think_compat_frac within-task (p=0.024) | **CONFIRMED** | p=0.012 with corrected extraction (actually stronger). But single-task, does not generalize. |
| Cross-repo Fisher combination (p=0.0008) | **RETRACTED** | Fisher combination of within-task permutation p-values yields p=0.137 for think_compat_frac, >0.50 for everything else. |
| Sonnet-Codex polarity contrasts | **RETRACTED** | Cannot test at task level with available data |
| think_diag_prec (rho=0.307, p=0.008) | **RETRACTED as stated** | This was a run-level Spearman across 70 tasks, but the Round 1 framing as "task-level correlation" was misleading. The p-value treats runs as independent, which they are not within tasks. |
| Gate operating characteristics | **REMAINS RETRACTED** | No out-of-sample test, as critic noted |

### What We Actually Know After Two Rounds

1. **The dissociation is real.** LLM coding agents suppress doubt markers in messages relative to reasoning/thinking text by 8-53x. This is a robust architectural finding. It is not predictive -- it exists equally in pass and fail runs -- but it means any monitoring system reading only messages misses essentially all expressed uncertainty.

2. **One feature, on one task, predicts success by exact permutation.** think_compat_frac discriminates pass from fail on sympy-21612 (9 replicates, p=0.012). This does not generalize to other tasks with available replicate counts.

3. **No feature survives task-level meta-analysis.** When we respect the task as the unit of analysis and require either sign-test significance across tasks or Fisher-combined within-task permutation significance, nothing survives. The Phase 0 dataset has too few mixed-outcome tasks (6 for Sonnet, 5 for Codex) and too few replicates per task (3-9) to detect anything short of a very large effect.

4. **The data structure is the bottleneck, not the features.** We have 387 runs but only 11 mixed-outcome tasks (combined across models). The effective sample size for within-task analysis is 11, not 387. This is a design limitation that cannot be overcome by better statistics -- it requires more replicates on more tasks.

### Implications for Phase 1

The honest conclusion is that Phase 0 produced one confirmed architectural finding (the dissociation) and one task-specific signal (think_compat_frac on sympy-21612), but no generalizable predictive features that survive proper statistical handling.

A Phase 1 gating experiment cannot be designed around these features as currently validated. The path forward requires:

1. **More replicates on more tasks.** 10+ replicates on 20+ tasks with 30-60% baseline pass rates would give adequate power.
2. **Pre-registered thresholds and features.** As the critic requested: specify think_compat_frac cutoff before seeing data.
3. **A cost model for the gate.** The dissociation finding motivates monitoring thinking text, but a gate needs a quantified cost-benefit analysis.

---

## METHODOLOGICAL NOTE: CORRECTED FEATURE EXTRACTION

Round 2 discovered and fixed two extraction bugs from Round 1:

1. **Codex thinking content** was initially extracted as zeros because the code looked for `c.get('text', '')` on thinking blocks, when Codex stores reasoning in `item.completed` events with `item.type='reasoning'` and `item.text`. The corrected extractor handles both Claude and Codex stream formats.

2. **Sonnet tool errors** were initially extracted using `msg.get('type') == 'tool_result'` at the top level, which matches zero events in Claude streams (tool results are nested inside `user` messages as `content[].type='tool_result'`). The corrected extractor checks `user` message content for `tool_result` blocks. This means the Round 1 `fail_streak_max` and `early_error_rate` values for Sonnet may have been computed from a different source (possibly the pre-populated `prior_failure_streak` column in the DB, which was noted as unreliable for Codex).

These corrections change specific numbers but do not rescue any retracted claims. If anything, the corrected extraction makes the null results more robust by ensuring both models are measured consistently.

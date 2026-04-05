# Tier 2 Statistical Methods Review

**Reviewer:** Statistical audit
**Date:** 2026-03-28
**Scope:** Methodology audit of the Tier 2 feature analysis as reported in `context/tier2_results.md`, implemented in `src/tier2_features.py`, building on `src/analysis.py`, guided by `context/tier2-semantic-framework.md`.

---

## 1. CONFOUNDERS

### 1.1 Task-length control via partial correlation

**Verdict: Correct approach, but incomplete.**

Partial Spearman correlation controlling for `total_state_modifying_calls` is a defensible first-pass control. It removes the linear rank-association between each feature and task length before correlating with success. This is the standard approach for rank-based analyses when you have a single continuous confound.

However, partial correlation assumes the confounding relationship is monotonic. If the effect of task length on a feature is nonlinear (e.g., metacognitive density is high for short AND very long tasks but low for medium ones), partial correlation will not remove it cleanly.

**Recommendations:**
- Residualization is algebraically equivalent to partial correlation for Pearson r, but not exactly for Spearman. The current partial Spearman is better because it preserves rank assumptions. Keep it.
- Stratification: split tasks into short (<15 calls), medium (15-25), and long (>25) strata. Re-run the top 7 features within each stratum. If the sign of the correlation flips in any stratum, the partial correlation is misleading. This is a quick robustness check, not a replacement. The concern: with n=73 tasks and 3 strata, each stratum has ~24 tasks, barely adequate. Report this as a sensitivity analysis, not a primary result.
- Propensity matching is overkill for a single continuous confound. Save it for multivariate confound adjustment if repo + wave are added.

### 1.2 Confounders not controlled

**MAJOR ISSUE: Repo-level confound.** The 73 tasks span 9 repos with dramatically different pass rates:

| Repo | Tasks | Pass rate |
|------|-------|-----------|
| django | 24 | 79.2% |
| sympy | 30 | 36.7% |
| pytest-dev | 8 | 37.5% |
| scikit-learn | 3 | 0.0% |
| pylint-dev | 3 | 100.0% |

Django tasks pass at 79.2%; sympy tasks at 36.7%. This is a 42.5 percentage-point gap. If Django tasks happen to produce higher metacognitive_density (perhaps because Django bugs are more localized and the agent reaches "actually, the fix is..." more readily), then metacognitive_density is partly measuring "is this a Django task" rather than "is this agent reasoning well."

**Severity:** This is the single most threatening confound in the analysis. The partial correlation controls for task length but not task difficulty. Repo is a proxy for difficulty.

**Fix:** Run partial correlations controlling for BOTH `total_state_modifying_calls` AND repo (as a categorical variable, or as dummy-coded indicators for the two dominant repos: django and sympy). If metacognitive_density rho_partial drops substantially after adding repo, the finding is weaker than reported. Alternatively, compute the correlation separately within django (n=24) and sympy (n=30) and check sign consistency.

**MODERATE ISSUE: Wave confound.** The data spans 16 waves. Early waves (1-3) used swebench-docker validation; later waves used independent validation. Wave 1 has 9 tasks at 66.7% pass; wave 8 has 5 tasks at 100%; wave 11 has 4 tasks at 0%; wave 13 has 5 tasks at 0%. The pass rate varies wildly across waves.

If earlier waves have different validation quality (which the retro findings document), and if early waves systematically have different feature distributions (because the task selection was different), then wave is a confound. The results do not control for wave.

**Fix:** Add `wave` as a covariate in a secondary analysis. Given that wave is partly confounded with task selection (different tasks in different waves), this is hard to fully disentangle. At minimum, report whether the top features are significant in both the first-half and second-half of waves.

**MINOR ISSUE: Bug category.** SWE-bench tasks span different bug types (logic errors, missing imports, configuration issues). The results note that error types are "mostly infrastructure noise" (Section 6.1 of results). If certain error types cluster with certain repos, this amplifies the repo confound. Not independently actionable without a bug taxonomy, but worth noting.

### 1.3 Summary of confound severity

| Confound | Status | Severity | Action |
|----------|--------|----------|--------|
| Task length | Controlled (partial rho) | High, addressed | Add stratified robustness check |
| Repo | NOT controlled | **HIGH** | Add repo-controlled partial correlations |
| Wave | NOT controlled | Moderate | Secondary analysis |
| Bug category | NOT controlled | Low-moderate | Note as limitation |
| Task difficulty (residual) | Partially captured by length | Moderate | Repo control partially addresses |

---

## 2. NORMALIZATION

### 2.1 Mean aggregation

**Verdict: Correct for linguistic features, problematic for some structural features.**

Linguistic features (metacognitive_density, tentative_density, etc.) are computed per-token within each call, then mean-aggregated across calls. This is a double normalization: per-token within call, then per-call across the task. This is defensible because it controls for both within-call verbosity and between-task trajectory length.

However, structural features like `test_run_count` and `unique_files_touched` are raw counts, not mean-aggregated. They are therefore confounded with task length. The partial correlation controls for this post-hoc, but the features themselves are not normalized. This inconsistency means the partial correlation is doing different amounts of work for different features.

**Specific concern:** `fail_then_switch_rate` is already rate-normalized (switches / failures), and `recovery_rate` is rate-normalized (recoveries / failures). These are NOT confounded with task length in the same way that raw counts are. The partial correlation over-controls for these features, potentially removing real signal. The sign flip for `fail_then_switch_rate` (expected positive, got rho_partial = -0.372) might partly be an artifact of over-controlling.

**Fix:** For rate-normalized features (recovery_rate, fail_then_switch_rate), report both the raw and partial correlations and note that the partial may be over-correcting.

### 2.2 The 1/3 cutoff for early_error_rate

**Verdict: Not justified a priori, but not unreasonable.**

The 1/3 cutoff for "early" trajectory is arbitrary. The results show:
- early (first 1/3): rho = -0.349 (significant)
- mid (middle 1/3): rho = -0.302 (significant)
- late (final 1/3): rho = -0.085 (not significant)

The pattern is monotonically decreasing, which suggests the 1/3 cutoff is not a knife-edge boundary. A different split (first 1/4, first 1/2) would likely show the same directional result with somewhat different effect sizes.

**However:** The cutoff was chosen AFTER seeing the data (Discovery 4 in results). This is post-hoc. If this feature is pre-registered for wave 2, the 1/3 cutoff should be locked in advance.

**Fix:** For the current analysis, report a sensitivity analysis with first-1/4 and first-1/2 cutoffs. For wave 2, pre-register the 1/3 cutoff based on the pilot finding.

### 2.3 Controlling for total_tool_calls vs total_state_modifying_calls

**IMPORTANT ISSUE.** The partial correlations control for `total_state_modifying_calls`, but the runs table also stores `total_tool_calls` (including read-only calls like Read, Grep, Glob). The data shows:

- Failing tasks: avg 40.2 total calls, 22.9 state-modifying
- Passing tasks: avg 37.8 total calls, 16.6 state-modifying

The ratio of state-modifying to total calls differs by outcome: failing tasks have 57% state-modifying calls; passing tasks have 44%. This means the information-gathering behavior (read-only calls) differs systematically between pass and fail. Passing tasks do proportionally MORE reading.

Controlling for `total_state_modifying_calls` but not `total_tool_calls` means that the partial correlations do not account for the read-only call volume. If a feature like `first_edit_position` (normalized by state-modifying calls only) correlates with the read-to-write ratio, the current control is insufficient.

**Fix:** Re-run partial correlations controlling for `total_tool_calls` as a secondary analysis. If results differ materially, report both.

---

## 3. MULTIPLE COMPARISONS

### 3.1 BH FDR at q=0.10

**Verdict: Appropriate for this study design, but the q threshold is aggressive.**

BH FDR at q=0.10 means you expect up to 10% of discoveries to be false. With 10 discoveries, you accept ~1 false positive. This is standard for exploratory/discovery-phase work.

However, q=0.10 is on the permissive end. Standard practice in genomics (where BH FDR was developed) uses q=0.05. For a methods paper that will inform gating decisions, q=0.05 would be more defensible. The practical impact: features #8 (mean_edit_expansion, p_partial=0.024) and #9 (error_rate, p_partial=0.028) would still survive at q=0.05. Feature #10 (reasoning_to_action_alignment, p_partial=0.049) would be borderline.

**Recommendation:** Report both q=0.10 and q=0.05 thresholds. The top 7 features (rho_partial >= 0.30) are robust to either threshold.

### 3.2 Pre-registered vs. discovered features

**MAJOR METHODOLOGICAL ISSUE.** The results table includes 20 features. Of these, 4 are marked "(D)" for discovered:
- tentative_density (rho_partial = -0.434)
- early_error_rate (rho_partial = -0.372)
- insight_density (rho_partial = +0.315)
- mean_edit_expansion (rho_partial = +0.265)
- error_rate (rho_partial = -0.257) -- also marked (D)

These features were constructed AFTER examining the data. They are inherently post-hoc. Applying the same BH FDR correction to pre-registered and post-hoc features in the same table conflates confirmatory and exploratory analysis. This inflates the apparent strength of the findings.

**Critically:** `tentative_density` (the 3rd strongest feature) and `early_error_rate` (4th/5th strongest) were discovered from the data. If they are removed from the "10 of 20 survive BH FDR" count, the headline becomes "7 of 15 pre-registered features survive" -- still strong, but a different story.

Furthermore, these discovered features are NOT in `src/tier2_features.py`. The implementation file contains 13 pre-registered features + `random_noise` + `total_state_modifying_calls` = 15 entries in `EXPECTED_DIRECTIONS`. The 5 discovered features were apparently computed in a separate notebook or ad-hoc script that is not in the codebase. This is a reproducibility concern.

**Fix:**
1. Report pre-registered and discovered features in SEPARATE tables with SEPARATE BH corrections.
2. For discovered features, use a stricter threshold (Bonferroni or q=0.05) to compensate for their post-hoc nature.
3. Commit the code that computes the discovered features to `src/tier2_features.py` for reproducibility.
4. In the wave 2 analysis, treat the discovered features as pre-registered (since they will have been locked before wave 2 data collection).

### 3.3 Sequential block testing from the Opus framework

**NOT APPLIED.** The framework (Section 4.5) specified sequential block testing: Block A (structural, 8 features, Bonferroni m=8), Block B (linguistic replacement, 3 features, Bonferroni m=3), Block C (linguistic extension, 5 features, Bonferroni m=5), Block D (interaction, 3 features, Bonferroni m=3). The actual analysis pools all 20 features into a single BH FDR test.

This is a deviation from the pre-registered plan. The sequential design would have given more power (smaller correction factors per block), but the BH FDR approach is arguably more appropriate for exploratory discovery. The deviation should be acknowledged.

**Fix:** Report the BH FDR as the primary analysis (which is what was done). Add a supplementary table showing the sequential block results per the original plan. Note the deviation from protocol.

---

## 4. FEATURE INDEPENDENCE

### 4.1 Collinearity between metacognitive_density and insight_density

**CONFIRMED ISSUE.** Both features include the word "actually":
- `metacognitive_density` patterns: "wait", "actually", "hmm", "hold on", "on second thought", "I was wrong", "that's not right", "let me reconsider", "I see"
- `insight_density` (per results, Discovery 2): "I understand", "Now I understand", "actually", "the issue/problem/bug is"

The overlap on "actually" means these features are NOT independent. Since "actually" is the "strongest single-word predictor" (rho=+0.330), it is likely driving both features. If you remove "actually" from either feature, the correlation would change substantially.

**Severity:** This is a double-counting problem. The same word is being credited as evidence for two different constructs (metacognition and insight). For a gating model that uses both features, this inflates the apparent dimensionality of the signal.

**Fix:**
1. Compute VIF for all features in the recommended 7-feature set (Section 9 of results). Any VIF > 5 indicates problematic collinearity.
2. Remove "actually" from one of the two features. The cleaner design: "actually" belongs in metacognitive_density (it marks self-correction), and insight_density should be restricted to "I understand" and "the issue/problem/bug is" (which mark a declaration of diagnosis without self-correction).
3. Report the correlation between metacognitive_density and insight_density. The intercorrelation matrix (Section 5 of results) does NOT include insight_density, tentative_density, or mean_edit_expansion. This is a gap.

### 4.2 The intercorrelation matrix is incomplete

The reported matrix (Section 5) covers only 5 features: early_error_rate, metacognitive_density, reasoning_to_action_alignment, first_edit_position, wrong_stuck_density. The 10 features that survive BH FDR include 5 others not in the matrix: total_state_modifying_calls, tentative_density, fail_then_switch_rate, insight_density, instead_contrast_density, mean_edit_expansion, error_rate.

**Fix:** Report the full 10x10 (or at least 7x7 for the recommended feature set) intercorrelation matrix. Without this, the collinearity situation is unknown.

### 4.3 Algebraic dependencies

- `error_rate` and `early_error_rate` are algebraically related: `error_rate` is computed over the full trajectory; `early_error_rate` over the first third. They cannot be independent. Including both in a gating model is questionable.
- `metacognitive_density` and `insight_density` share "actually" as noted above.
- `tentative_density` and `self_directive_density` likely overlap: "let me try" would match both `_SELF_DIRECTIVE_PATTERNS` (which includes `\blet me\b`) and the tentative markers. Whether it does depends on the exact regex for tentative_density, which is not in the codebase (see Section 3.2).

**Fix:** For the recommended 7-feature set, drop `error_rate` (keep `early_error_rate` which is more specific and has a stronger theoretical motivation). This reduces to 6 features. Check tentative_density vs self_directive_density overlap.

---

## 5. GAPS

### 5.1 Reasoning text coverage and selection bias

**SIGNIFICANT CONCERN.** Only 583 of 2,025 state-modifying calls (29%) have reasoning text. (Note: the results say "33% mean coverage per task" which is the task-level mean, not the call-level rate.)

The coverage differs by tool type:
- Edit calls: 75-83% have reasoning (higher for passing runs: 83.3% vs 75.3%)
- Bash calls: ~20% have reasoning (similar for pass and fail)

This is a systematic selection pattern: Edit calls carry reasoning much more often than Bash calls. Passing runs have higher reasoning coverage on Edits (83.3% vs 75.3%). This means the linguistic features are computed on a non-random subset of calls, biased toward:
1. Edit calls (which are themselves a success predictor: passing tasks average 3.0 edits vs 2.4 for failing)
2. Within Edits, slightly more complete for passing runs

**Implication:** The linguistic features are not measuring "how the agent reasons" across the full trajectory. They are measuring "how the agent reasons when it is about to make an edit." This is a narrower claim than presented.

**Fix:** Report the reasoning coverage breakdown by tool type and outcome (as above). Acknowledge that linguistic features are effectively "pre-edit reasoning" features. Consider whether this actually strengthens the gating use case (you primarily want to gate edits, not reads).

### 5.2 Reliability at 583 calls

With 583 calls carrying reasoning across 73 tasks, the average is ~8 calls with reasoning per task. For tasks with only 4-6 state-modifying calls (the shortest tasks in the dataset: sympy-18532 and sympy-21612 both have 4 calls), the mean-aggregated linguistic feature is computed from 1-3 data points. This is noisy.

**Fix:** Report the distribution of reasoning-carrying calls per task. Flag tasks where the linguistic features are based on fewer than 3 reasoning-bearing calls. As a sensitivity analysis, re-run the correlations excluding tasks with fewer than 3 reasoning-bearing calls.

### 5.3 Missing features

**Read-only call patterns.** The analysis uses only state-modifying calls (2,025). There are an additional ~15 calls per task of Read/Grep/Glob that are not stored in `tool_calls`. The Opus framework flagged this (S2: `explore_before_act_ratio` requires access to all calls). The finding that passing tasks have a higher ratio of total calls to state-modifying calls (37.8/16.6 = 2.28 vs 40.2/22.9 = 1.76) suggests the read-to-write ratio itself is a predictor.

**Fix:** Parse read-only calls from `raw_stream_json` and compute:
- `read_to_write_ratio`: total_tool_calls / total_state_modifying_calls
- `grep_before_edit_rate`: fraction of Edits preceded by a Read/Grep within 3 calls
These are cheap to compute and the data exists.

**Error categorization.** Section 6.1 of results notes that most errors are infrastructure noise (pip install, command not found). A "substantive_error_rate" that excludes infrastructure errors would likely be a stronger predictor than the current `error_rate`.

**Temporal features.** The framework proposed `error_rate_slope` (Section S5), `reasoning_trend_slope`, and `tool_diversity_trajectory`. None were implemented. The mid-trajectory error spike in failing runs (Section 6.2: mid=17.9% vs early=12.8%) suggests temporal shape features would carry signal.

### 5.4 The full stream vs. state-modifying calls

**YES, you should look at the full stream.** The ratio `total_tool_calls / total_state_modifying_calls` differs by outcome (2.28 pass vs 1.76 fail). This means passing agents do proportionally more information-gathering (Read/Grep/Glob) relative to state-modifying actions. This is arguably the simplest structural predictor available, it requires zero NLP, and it is not currently extracted as a feature.

---

## 6. EFFECT SIZES

### 6.1 Practical significance of rho_partial 0.25-0.50

The partial rho values range from 0.25 (mean_edit_expansion) to 0.494 (metacognitive_density). In behavioral science terms:
- rho = 0.25-0.30: small-to-medium effect (Cohen's conventions, adjusted for Spearman)
- rho = 0.30-0.50: medium effect
- rho > 0.50: large effect

For a binary gating decision, the relevant question is: what AUC does a feature achieve? A single feature with rho=0.494 against a binary outcome (pass/fail) roughly corresponds to an AUC of 0.70-0.75. This is moderate and probably not sufficient for a standalone gate. A model combining the top 3-4 features could plausibly reach AUC 0.80+, which is meaningful.

**For a gating decision:** These effect sizes are strong enough to justify building a gate, but not strong enough for any single feature to be the sole gating criterion. The recommended 7-feature model (Section 9 of results) is the right approach.

### 6.2 Sample size for Bonferroni survival

The results report that `early_error_rate` survives Bonferroni at n=73 (rho=-0.349, p_raw=0.003, p_bonf=0.047 for 15 pre-registered features). For the full 20-feature set, Bonferroni would require p_raw < 0.0025.

For metacognitive_density (rho_partial=0.494, p<0.001): already survives Bonferroni at m=20.

For the next tier of features (rho_partial ~0.30, p~0.01): to achieve p_bonf < 0.05 with m=20, you need p_raw < 0.0025. For rho=0.30, the required sample size is approximately:

- For rho=0.30 to reach p < 0.0025 (two-tailed Spearman): n ~ 120-130 tasks
- For rho=0.25: n ~ 170-190 tasks
- For rho=0.50: n ~ 45-50 tasks (already achieved)

**Implication:** The current n=73 is adequate for the strongest features (rho >= 0.40) but underpowered for the medium-strength features (rho 0.25-0.35) to survive Bonferroni. The 71-task wave 2 will bring the total to ~144 tasks, which is approximately the threshold for rho=0.30 features to survive.

### 6.3 Overfitting risk at n=73, p=20

The ratio of observations to features is 73/20 = 3.65. For CORRELATIONS (bivariate), this is not overfitting in the regression sense -- each correlation is a separate test, not a joint model. The multiple comparisons correction (BH FDR) addresses the false discovery risk.

However, if the 7-feature gating model is fit as a multivariate logistic regression, 73/7 = 10.4 events per variable (using the minority class: 36 passes). The standard EPV (events per variable) guideline requires EPV >= 10. This is borderline. With 5-6 features, the model would be on safer ground. Cross-validation (leave-one-out or 5-fold) is mandatory.

**Fix:** For the gating model, use no more than 5-6 features (EPV >= 12). Use LOOCV or repeated 5-fold CV with proper feature selection INSIDE the CV loop to avoid optimistic bias.

---

## 7. FORWARD-LOOKING

### 7.1 Pre-registered features for wave 2

Lock the following features for confirmatory testing in wave 2:

**Tier A (strongest, most likely to replicate):**
1. `metacognitive_density` (rho_partial = +0.494) -- pre-register positive direction
2. `tentative_density` (rho_partial = -0.434) -- pre-register negative direction
3. `early_error_rate` (rho_partial = -0.372) -- pre-register negative, lock 1/3 cutoff
4. `insight_density` (rho_partial = +0.315) -- pre-register positive, but REMOVE "actually" from lexicon (assign to metacognitive_density only)

**Tier B (medium confidence):**
5. `instead_contrast_density` (rho_partial = +0.300) -- pre-register positive
6. `mean_edit_expansion` (rho_partial = +0.265) -- pre-register positive
7. `error_rate` (rho_partial = -0.257) -- pre-register negative, BUT consider replacing with `substantive_error_rate` (excluding infrastructure errors)

**New features to add for discovery in wave 2:**
8. `read_to_write_ratio` (total_tool_calls / total_state_modifying_calls) -- exploratory, expected positive
9. `substantive_error_rate` (errors excluding pip/import/command-not-found) -- expected negative
10. `mid_error_spike` (mid_error_rate - mean(early, late)) -- expected negative (pilot rho=-0.171, p=0.148)

### 7.2 Lock vs. open feature set

**Recommendation: Lock the 7 confirmatory features. Add 3 exploratory features with separate correction.**

The confirmatory features (1-7 above) should be tested with Bonferroni at m=7 (alpha=0.007 per test). This gives adequate power at n=144 for rho >= 0.25.

The exploratory features (8-10) should be tested with BH FDR at q=0.10, reported separately.

Do NOT combine confirmatory and exploratory features in the same correction pool.

### 7.3 Analysis plan for combining pilot + wave 2

**Option A (preferred): Fixed-effects meta-analysis.**
Compute effect sizes (Fisher-transformed rho) and standard errors separately for pilot (n=73) and wave 2 (n=71). Combine using inverse-variance weighting. This correctly handles heterogeneity between waves and does not require the assumption that both waves sample from identical populations.

**Option B (pooled analysis):**
Combine all ~144 tasks into a single dataset. Re-run partial correlations with `wave` as an additional covariate. This is simpler but assumes the features have the same relationship to success in both waves.

**Why Option A is better:** The pilot data was used to discover some features (tentative_density, early_error_rate, etc.). Pooling treats discovery data and confirmation data identically, which inflates confidence in the discovered features. Meta-analysis keeps them separate: the pilot estimates include the discovery bias; the wave 2 estimates are clean. Only features that replicate in wave 2 should be considered confirmed.

**Mandatory for either option:**
- Pre-register the analysis plan BEFORE wave 2 data collection begins.
- Lock all feature definitions (regex patterns, cutoff thresholds, normalization methods) before wave 2.
- Record the locked specifications in a dated document.

---

## 8. REPRODUCIBILITY CONCERNS

### 8.1 Missing implementation code

Five features reported in the results are NOT implemented in `src/tier2_features.py`:
- `tentative_density`
- `early_error_rate`
- `insight_density`
- `mean_edit_expansion`
- `error_rate`

These were apparently computed in ad-hoc analysis (notebook, REPL, or separate script). The exact regex patterns, aggregation methods, and cutoff definitions are not in version-controlled code. This is a reproducibility failure.

**Fix:** Commit the implementation of all 5 discovered features to `src/tier2_features.py` before wave 2 begins. Include exact pattern lists, normalization denominators, and aggregation methods.

### 8.2 Inconsistency in reported counts

The results header states "583 with reasoning text" but the database query returns 583 for the latest-run-per-task subset. The framework document states "612 with reasoning text" for the full 103-run dataset. These are consistent but could be confusing to readers. Make clear which denominator applies to which count.

Minor: the header says "36 pass, 37 fail" which matches the Python implementation's dict-ordering behavior, but a naive SQL GROUP BY returns "38 pass, 35 fail" due to different deduplication logic. The Python code is correct (it uses dict insertion order from the ORDER BY), but the discrepancy should be documented.

---

## 9. SUMMARY OF ACTIONS

### Critical (do before drawing conclusions):
1. **Control for repo.** Re-run top 7 features with repo as a covariate, or stratify by django vs sympy.
2. **Separate pre-registered from discovered features.** Report in two tables with separate corrections.
3. **Commit discovered feature code** to `src/tier2_features.py`.
4. **Complete the intercorrelation matrix** for all surviving features. Compute VIF for the 7-feature set.

### Important (do before wave 2):
5. **Remove "actually" overlap** between metacognitive_density and insight_density.
6. **Pre-register feature set** with locked definitions.
7. **Write the wave 2 analysis plan** (meta-analysis vs pooled, correction thresholds).
8. **Extract read_to_write_ratio** from the runs table (requires no new parsing).
9. **Add sensitivity analyses:** stratified by task length, with/without tasks having <3 reasoning calls.

### Nice to have:
10. Report BH FDR at both q=0.10 and q=0.05.
11. Parse read-only calls from raw_stream_json for grep_before_edit_rate.
12. Implement substantive_error_rate (exclude infrastructure errors).
13. Acknowledge sequential block testing deviation from pre-registered plan.

---

## 10. OVERALL ASSESSMENT

The analysis is competent and the findings are plausible. The task-length confound control was the right call, and the suppression effect (metacognitive_density going from +0.308 raw to +0.494 partial) is a genuine methodological insight. The random noise control passing is reassuring.

The two serious threats to validity are: (1) the uncontrolled repo confound, which could explain a substantial fraction of the signal, and (2) the mixing of pre-registered and post-hoc features in a single BH FDR correction, which overstates the confirmatory strength of the findings.

If the top features survive the repo-controlled analysis, they are strong enough (rho_partial >= 0.30) to justify a gating experiment. If they do not, the study needs the wave 2 confirmation before proceeding.

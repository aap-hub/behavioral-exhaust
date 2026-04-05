# Phase 0 Final Deliverable: Cross-Model Behavioral Exhaust Analysis

**Date:** 2026-03-28 (corrected 2026-03-29)
**Dataset:** 373 validated runs (183 Sonnet, 190 Codex) across 75 SWE-bench Lite tasks, 9 repositories
**DB:** data/uga_phase0_complete_final.db (read-only backup)
**Predecessors:** phase0_analysis_opus.md, thinking_block_discovery.md, thinking_block_discovery_round2.md, tier2_results.md

---

## 0. EXECUTIVE SUMMARY

We collected agent runs across two models -- Claude Sonnet 4.6 and Codex GPT-5.4 -- solving SWE-bench Lite tasks (373 validated). Sonnet passes 49.2% of its runs; Codex passes 41.1%. On the 70 shared tasks, Sonnet passes 49.4% and Codex 41.1%. Despite broadly similar performance profiles, the models fail differently and the behavioral features associated with success differ substantially between them.

**Key findings:**

1. **Task-level agreement is high on shared tasks (87.1%, kappa=0.74)** -- the models mostly pass and fail the same tasks, suggesting task difficulty is the dominant factor.

2. **Feature association is model-specific.** Only 2 of 24 features (fail_streak_max, early_error_rate) are significantly associated with success in both models within the same repo. The CWC-surviving features from Sonnet do not transfer to Codex.

3. **One confirmed polarity flip.** `instead_contrast_density` is associated with SUCCESS in Sonnet but FAILURE in Codex within the same repository (sympy), with both reaching significance. Same linguistic marker, opposite association. Two other features (backtrack_count, metacognitive_density) show directional reversal but only one side reaches significance in each case -- these are suggestive but unconfirmed.

4. **The thinking/message dissociation replicates across models but differently.** Sonnet's thinking blocks (2.0M chars, ~11K/run) contain diagnostic reasoning; Codex's reasoning summaries (944K chars, ~5.0K/run) contain strategic planning. Different architectures produce different exhaust.

5. **Deliberation and diagnostic precision interact (Sonnet-specific).** In Sonnet, high deliberation + high diagnostic precision yields 73% pass rate; either alone yields ~25-32%. The interaction bonus is +0.56 -- far larger than any main effect. This interaction has not been confirmed in Codex.

---

## 1. DATA QUALITY AUDIT

### 1.1 Anomalies Detected

| Check | Result | Impact |
|-------|--------|--------|
| Short wall time (<30s) + high tool calls (>5) | 4 runs (2 synthetic, 2 SWE-bench with 2-3 calls) | Benign: simple tasks solved quickly |
| Runs with 0 reasoning text where siblings have it | 0 cases | Clean |
| Codex sympy convergence (early vs late) | Early half: 25.6%, late half: 35.9% (+10.3pp) | Possible improvement over runs; monitor |
| Duplicate run_ids | 0 | Clean |
| Tasks with no valid runs for one model | 5 Sonnet-only tasks, 0 Codex-only | Codex task set is strict subset of Sonnet |
| Tool call outliers | Sonnet: 1 run at 201 calls (2x p95); Codex: max 58 (no outliers) | Sonnet has a long tail; Codex is bounded by timeout |
| Timed out runs | Sonnet: 2/183 (1.1%); Codex: 0/190 | Negligible |

### 1.2 Data Completeness

| Metric | Sonnet | Codex |
|--------|--------|-------|
| Validated runs | 183 | 190 |
| Unique tasks (SWE-bench) | 75 | 70 |
| Pass rate | 49.2% | 41.1% |
| Raw stream JSON coverage | 100% | 100% |
| Thinking/reasoning block coverage | 100% (2.0M chars) | 100% (944K chars) |
| Agent message coverage | 100% (350K chars) | 100% (669K chars) |
| Per-call reasoning text | 28.8% of calls | 60.1% of calls |
| Median thinking chars/run | 2,758 | 5,548 |
| Mean thinking chars/run | 10,765 | 5,754 |

**Note on cross-model comparison:** Aggregate pass rates are computed on different task sets (Sonnet: 75 tasks, Codex: 70 tasks). For fair comparison, use the matched set of 70 shared tasks: Sonnet 49.4% (88/178 runs), Codex 41.1% (78/190 runs). The 8pp gap is notable and means cross-model feature comparisons must control for this difference.

### 1.3 Codex Sympy Convergence

Codex sympy pass rate shows a +10.3pp improvement from early to late runs. This could reflect:
- Learning from the task ordering (unlikely: tasks were randomized)
- Infrastructure stabilization (more likely: early runs had more environment setup failures)
- Regression to the mean over small batches

The effect is within 1 SD of random variation for n=84. Not a threat to analysis validity but flagged for transparency.

---

## 2. CROSS-MODEL FEATURE ANALYSIS

### 2.1 Within-Repo Spearman Correlations

#### Sonnet (validated, corrected Spearman)

**Sympy** (n=87, 41.4% pass -- balanced difficulty):

| Feature | rho | p | Direction |
|---------|-----|---|-----------|
| backtrack_count | +0.359 | 0.0006 | Self-correction associated with success |
| fail_streak_max | -0.294 | 0.0058 | Error streaks associated with failure |
| instead_contrast_density | +0.282 | 0.0081 | Contrastive reasoning associated with success |
| early_error_rate | -0.273 | 0.0106 | Early errors associated with failure |
| unique_files_touched | -0.253 | 0.0179 | Touching many files associated with failure |
| deliberation_length | +0.214 | 0.0463 | Longer per-call reasoning associated with success |

**Django** (n=44, 84.1% pass -- high baseline):

| Feature | rho | p | Direction |
|---------|-----|---|-----------|
| first_edit_position | +0.493 | 0.0007 | Reading before writing associated with success |
| deliberation_length | +0.396 | 0.0077 | Longer per-call reasoning associated with success |
| n_calls | +0.367 | 0.0143 | More calls associated with success (ceiling effect) |
| think_t_func_refs | +0.318 | 0.0354 | Function references in thinking associated with success |

#### Codex (validated, corrected Spearman)

**Sympy** (n=84, 28.6% pass -- harder for Codex):

| Feature | rho | p | Direction |
|---------|-----|---|-----------|
| think_t_compat_fraction | -0.323 | 0.0040 | Environment struggle in reasoning associated with failure |
| fail_streak_max | -0.296 | 0.0086 | Error streaks associated with failure |
| early_error_rate | -0.282 | 0.0123 | Early errors associated with failure |
| planning_score | -0.270 | 0.0170 | Planning language associated with failure |
| instead_contrast_density | -0.264 | 0.0195 | Contrastive reasoning associated with FAILURE (polarity flip!) |
| n_calls | -0.263 | 0.0199 | More calls associated with failure |
| metacognitive_density | -0.261 | 0.0212 | Metacognitive markers associated with failure (direction reversal, but see note) |

**Note on polarity flips:** Only `instead_contrast_density` qualifies as a confirmed polarity flip -- it is significant (p<0.05) in both models with opposite signs. `backtrack_count` is significant in Sonnet (+0.359, p=0.0006) but not in Codex (-0.108, p>0.05). `metacognitive_density` is significant in Codex (-0.261, p=0.021) but not in Sonnet (+0.138, p>0.05). These are directional reversals but only one side reaches significance in each case.

**Django** (n=71, 73.2% pass -- high baseline):

| Feature | rho | p | Direction |
|---------|-----|---|-----------|
| early_error_rate | -0.322 | 0.0128 | Early errors associated with failure (consistent) |
| instead_contrast_density | -0.223 | 0.0893 | Marginal, same negative direction |

### 2.2 CWC Decomposition (Fisher's Combined p-value)

Features surviving within-repo analysis (django + sympy combined):

**Sonnet CWC survivors:**

| Feature | avg rho | Fisher p | Direction |
|---------|---------|----------|-----------|
| deliberation_length | +0.275 | 0.003 | PASS-predictive |
| first_edit_position | +0.267 | 0.001 | PASS-predictive |
| backtrack_count | +0.244 | 0.005 | PASS-predictive |
| early_error_rate | -0.228 | 0.025 | FAIL-predictive |
| fail_streak_max | -0.175 | 0.026 | FAIL-predictive |

**Codex CWC survivors:**

| Feature | avg rho | Fisher p | Direction |
|---------|---------|----------|-----------|
| early_error_rate | -0.299 | 0.002 | FAIL-predictive |
| instead_contrast_density | -0.246 | 0.013 | FAIL-predictive |
| think_t_compat_fraction | -0.242 | 0.010 | FAIL-predictive |
| fail_streak_max | -0.184 | 0.040 | FAIL-predictive |

### 2.3 Within-Repo Permutation Test (10,000 permutations)

Features surviving the permutation test (labels shuffled within repo):

**Sonnet permutation survivors:**

| Feature | Observed diff | Perm p | Verdict |
|---------|--------------|--------|---------|
| deliberation_length | +46.5 chars/call | 0.0004 | FAITHFUL |
| first_edit_position | +0.106 | 0.0014 | FAITHFUL |
| tentative_density | -0.0008 | 0.055 | Borderline |
| think_t_pivots | -0.922 | 0.058 | Borderline |

**Codex permutation survivors:**

| Feature | Observed diff | Perm p | Verdict |
|---------|--------------|--------|---------|
| think_t_compat_fraction | -0.043 | 0.006 | FAITHFUL |
| instead_contrast_density | -0.0016 | 0.007 | FAITHFUL |
| think_t_func_refs | +0.051 | 0.044 | FAITHFUL |
| think_reasoning_clarity | -0.111 | 0.085 | Borderline |

### 2.4 Key Finding: Different Features Predict for Different Models

Of 24 features tested, the cross-model picture is:

| Category | Features |
|----------|----------|
| Both models (same direction) | fail_streak_max (-), early_error_rate (-) |
| Sonnet only | deliberation_length (+), first_edit_position (+), backtrack_count (+) |
| Codex only | think_t_compat_fraction (-), planning_score (-) |
| CONFIRMED POLARITY FLIP (opposite direction, both significant) | instead_contrast_density |
| SUGGESTIVE REVERSAL (opposite direction, one side non-significant) | backtrack_count, metacognitive_density |

The confirmed polarity flip on `instead_contrast_density` is the most surprising cross-model finding. In Sonnet, "however/but/instead" is associated with success (the agent makes contrastive comparisons to narrow down the bug). In Codex, the same words are associated with failure (the agent pivots between approaches without converging).

For `backtrack_count` and `metacognitive_density`, the directional reversal is suggestive but only one side reaches significance. These are Sonnet-specific observations that *may* reverse in Codex, pending larger samples or matched-task analysis.

---

## 3. TASK-LEVEL AGREEMENT

### 3.1 Agreement Matrix (70 shared tasks, majority-vote per task)

| | Codex Pass | Codex Fail |
|---|-----------|-----------|
| **Sonnet Pass** | 27 | 7 |
| **Sonnet Fail** | 2 | 34 |

- **Agreement: 87.1% (61/70 shared tasks)**
- **Cohen's kappa: 0.742 (substantial agreement)**
- Both pass: 27 tasks, both fail: 34 tasks
- Sonnet-only pass: 7 tasks, Codex-only pass: 2 tasks

### 3.2 Per-Repo Agreement

| Repo | Agreement | Both pass | Both fail | Sonnet-only | Codex-only |
|------|-----------|-----------|-----------|-------------|------------|
| Django | 100% (23/23) | 18 | 5 | 0 | 0 |
| Sympy | 83% (25/30) | 8 | 17 | 3 | 2 |
| Pytest-dev | 100% (8/8) | 1 | 7 | 0 | 0 |

Django shows perfect agreement -- both models find it easy. Sympy shows the most disagreement, consistent with its balanced difficulty level providing the most room for model-specific differences.

### 3.3 Interpretation

The high task-level agreement means task difficulty explains most of the variance in outcomes. When models disagree (14% of tasks), it is primarily on sympy tasks, suggesting these tasks involve reasoning patterns where one model has an architectural advantage over the other.

---

## 4. THINKING BLOCK ANALYSIS

### 4.1 Architectural Difference

| Property | Sonnet Thinking | Codex Reasoning |
|----------|----------------|-----------------|
| Format | Extended thinking blocks (type="thinking") | Reasoning items (item.type="reasoning") |
| Visibility | Hidden from user | Hidden from user |
| Median length/run | 2,758 chars | 5,548 chars |
| Mean length/run | 10,765 chars | 5,754 chars |
| Distribution | Right-skewed (long tail of complex runs) | More uniform |
| Content style | Deliberative: traces code paths, quotes errors | Strategic: plans next steps, evaluates options |

Sonnet's thinking blocks are qualitatively different from Codex's reasoning summaries. Key observations from reading 10 pass/fail pairs per model:

### 4.2 Sonnet Thinking Patterns

**Pass pattern -- The Evidence Trail:**
Sonnet pass runs show a convergent arc. Early blocks are exploratory ("Let me look at the code"). Middle blocks build evidence ("I see the issue. In `convert_frac`, when computing..."). Late blocks are precise ("The fix needs to change lines 383-389"). The agent traces actual code paths, quotes specific function names and line numbers, and arrives at a clear diagnosis before acting.

Example (sympy-21612, pass):
> "Now I see the code. The issue is in lines 383-389. Let me trace through for `\frac{\frac{a^3+b}{c}}{\frac{1}{c^2}}`..."

**Fail pattern -- The Actually Cascade:**
Sonnet fail runs show a divergent pattern. The agent identifies the right area but then enters a correction spiral: "Actually, let me look at this differently..." "Actually, the issue might be..." Multiple re-diagnoses without convergence. Fail runs have nearly double the thinking blocks (30 vs 16 in the sympy-21612 comparison) but do not arrive at a clean diagnosis.

Example (sympy-21612, fail):
> "Now let me look at the `convert_frac` function more carefully to understand the bug."
(Re-examines code already read. Does not trace the execution path.)

### 4.3 Codex Reasoning Patterns

**Pass pattern -- The Focused Plan:**
Codex pass runs show concise strategic reasoning. The model identifies what to do, states the plan, executes it. Reasoning blocks are short and action-oriented. The reasoning summary often contains exactly one diagnosis and one plan.

Example (django-11905, pass):
> "The fix is in the `as_sql` method of `Subquery`. We need to handle the edge case..."

**Fail pattern -- The Environment Spiral:**
Codex fail runs frequently devolve into environment troubleshooting. The reasoning becomes consumed by pip installation failures, Python version incompatibilities, and test infrastructure issues. The `think_t_compat_fraction` feature captures this directly: compatibility-focused reasoning is associated with failure.

Example (sympy-18057, fail):
> "I need to find the Python executable, which is likely to be Python 3. It's important for me to ensure I'm identifying the correct version..."

### 4.4 The Diagnostic Precision Dissociation

On the 6 tasks where Sonnet passes but Codex fails, Sonnet's diagnostic precision in thinking blocks is dramatically higher:

| Task | Sonnet think_diag_prec | Codex think_diag_prec | Ratio |
|------|----------------------|---------------------|-------|
| pallets-flask-4045 | 2.276 | 0.346 | 6.6x |
| psf-requests-3362 | 1.590 | 0.282 | 5.6x |
| pylint-dev-pylint-6506 | 2.103 | 0.573 | 3.7x |
| sympy-21612 | 2.596 | 0.693 | 3.7x |
| sympy-15609 | 3.957 | 0.250 | 15.8x |
| sympy-16988 | 3.548 | 0.307 | 11.6x |

When Sonnet passes tasks that Codex fails, Sonnet's thinking contains 4-16x more code-specific reasoning (function names, file references, code path tracing, line numbers) per thousand characters. This is the strongest observational association between diagnostic precision in internal reasoning and task success, though the causal direction cannot be established from observational data alone (it may be that easier-to-diagnose tasks elicit both precision and success).

---

## 5. FEATURE INTERACTIONS

### 5.1 Deliberation x Diagnostic Precision

In Sonnet/sympy (n=87), the interaction between deliberation_length and think_diagnostic_precision produces a dramatic nonlinear effect:

| Quadrant | Pass Rate | n |
|----------|-----------|---|
| High deliberation + High precision | 73% | 22 |
| High deliberation + Low precision | 23% | 22 |
| Low deliberation + High precision | 32% | 22 |
| Low deliberation + Low precision | 38% | 21 |

Interaction bonus: +0.56. Neither feature alone is sufficient -- an agent that thinks a lot without precision (23%) does worse than one that barely thinks (38%). But an agent that thinks deeply AND precisely about code artifacts succeeds 73% of the time.

In Codex/sympy, the same interaction is weaker (+0.13), consistent with Codex's reasoning blocks being less diagnostic and more strategic.

### 5.2 Polarity Flip Mechanism

The `instead_contrast_density` polarity flip (positive in Sonnet, negative in Codex) likely reflects architectural differences in how the models use contrastive language:

- **Sonnet:** "however" and "but" appear within diagnostic reasoning -- "The function returns X, but the expected behavior is Y" -- narrowing the gap between observed and expected behavior.
- **Codex:** "however" and "instead" appear within strategic pivots -- "However, let me try a different approach instead" -- abandoning one strategy for another.

The same word serves different cognitive functions in different models, producing opposite correlations with success.

---

## 6. COMBINED MODEL ANALYSIS

### 6.1 Model as Factor

In the combined dataset (both models), `model_version` is NOT a significant predictor of success within any repo:
- Sympy: model effect rho=+0.110, p=0.159 (Sonnet slightly better, not significant)
- Django: model effect rho=-0.058, p=0.558 (no difference)

This is consistent with the models having broadly similar aggregate performance on sympy and django, though non-significance does not establish equivalence (especially given the 8pp pass-rate gap on the full matched set). The more informative result is that the models differ in HOW they succeed and fail.

### 6.2 Features That Survive Cross-Model

When combining both models within a repo, only structural features survive:
- **fail_streak_max** (rho=-0.290, p=0.0002 in sympy): consecutive errors associated with failure regardless of model
- **early_error_rate** (rho=-0.241, p=0.002 in sympy): early errors associated with failure regardless of model

Linguistic features wash out in the combined analysis because of the polarity flips -- features associated with success in one model are associated with failure in the other, canceling in the combined sample.

---

## 7. CORRECTED STATISTICAL PICTURE

### 7.1 What Survives All Tests

A feature must survive: (a) within-repo Spearman at p<0.05, (b) CWC combined p<0.05, (c) permutation test at p<0.10. Results:

**Sonnet gold-standard features:**
1. deliberation_length (+): rho=+0.21 to +0.40 within repos, CWC p=0.003, perm p=0.0004
2. first_edit_position (+): rho=+0.15 to +0.49, CWC p=0.001, perm p=0.001

**Codex gold-standard features:**
1. think_t_compat_fraction (-): rho=-0.14 to -0.32, CWC p=0.010, perm p=0.006
2. instead_contrast_density (-): rho=-0.22 to -0.26, CWC p=0.013, perm p=0.007

**Cross-model gold-standard features (structural only):**
1. fail_streak_max (-): significant in both models within sympy
2. early_error_rate (-): significant in both models within sympy; Codex/django significant but Sonnet/django not individually significant (high-pass-rate ceiling effect)

### 7.2 What Does NOT Survive

- **hedging_score:** Dead in both models (p>0.13 everywhere). Academic hedging is not a signal.
- **reasoning_to_action_alignment:** Significant in Sonnet within specific analyses (previous memo) but does NOT survive the corrected within-repo permutation test (p=0.35). The original finding was inflated by between-repo confounding. This was the original headline result in the Phase 0 memo and is now retracted as a standalone finding.
- **metacognitive_density:** Significant in previous Sonnet analysis but shows directional reversal in Codex. Model-specific and possibly confounded.
- **think_diagnostic_precision:** Significant in Sonnet thinking block analysis but does not survive the permutation test as a standalone feature (p=0.17). Its value is in the interaction with deliberation_length.

### 7.3 Revised Hierarchy of Evidence

| Level | Features | Evidence |
|-------|----------|----------|
| Strong (survives all tests, both models) | fail_streak_max, early_error_rate | Structural markers of environment struggle. Cross-model, cross-repo. |
| Strong (survives all tests, model-specific) | deliberation_length (Sonnet: CWC p=0.003, perm p=0.0004), think_t_compat_fraction (Codex: CWC p=0.010, perm p=0.006) | Robust within model, not transferable. |
| Moderate (survives CWC + permutation, but note perm p > 0.001) | first_edit_position (Sonnet: CWC p=0.001, perm p=0.001), instead_contrast_density (Codex: CWC p=0.013, perm p=0.007) | Real signal; first_edit_position did not replicate in wave 2 alone. |
| Interaction only | deliberation x diagnostic_precision (Sonnet) | Strongest observational association (73% pass) but requires both features and is computed on quadrant splits (n~22 per cell). |
| Retracted | reasoning_to_action_alignment | Does not survive permutation (p=0.35). Between-repo confound. |
| Null | hedging_score, verification_score, planning_score, precision_naming_score | No signal in any analysis. |

---

## 8. THE THINKING/MESSAGE DISSOCIATION

### 8.1 The Core Finding

Features extracted from internal reasoning (thinking blocks / reasoning summaries) carry different and sometimes opposite signal from the same features extracted from agent messages. This was first discovered with `actually_density`:

- In Sonnet thinking: "Actually" = genuine pre-action confusion (r=-0.253 with success)
- In Sonnet messages: "Actually" = performative self-correction (r=+0.494 with success)

This dissociation means:
1. Any feature pipeline that conflates thinking and message content will CANCEL OUT real signals.
2. The two layers carry structurally different information: internal doubt lives in thinking; expressed correction lives in messages.
3. Phase 1 gating must specify which layer it is extracting from.

### 8.2 Cross-Model Dissociation

The dissociation operates differently across models:

| Layer | Sonnet | Codex |
|-------|--------|-------|
| Internal reasoning (thinking/reasoning) | Diagnostic: traces code paths, names functions, quotes errors. Highly predictive of success. | Strategic: plans approaches, evaluates feasibility. Moderately predictive (mainly through failure markers). |
| Agent messages | Performative: self-correction markers associated with success. Shorter, polished. | Explanatory: describes actions taken. Longer but less diagnostic. |
| Key predictive layer | Thinking blocks | Reasoning items (but mainly via absence of compat struggle) |

---

## 9. LIMITATIONS (UPDATED)

1. **All findings are correlational.** No causal intervention has been performed. Associations between features and success may reflect confounds (e.g., easier tasks elicit both better reasoning and more success). Phase 1 must test whether gating on these features changes outcomes.

2. **Model-specificity of linguistic features.** The confirmed polarity flip on `instead_contrast_density` and the suggestive reversals on other features mean no single linguistic feature set generalizes across models. Any deployment must be calibrated per-model.

3. **Unmatched task sets.** Sonnet was run on 75 tasks, Codex on 70. Five Sonnet-only tasks could bias Sonnet-specific feature estimates. All cross-model comparisons should use the 70 shared tasks. Aggregate pass rates differ (Sonnet 49.2% vs Codex 41.1%), so cross-model feature comparisons must account for this.

4. **Sample size per model-repo cell.** Codex/django has n=71 with 73.2% pass rate. This ceiling effect limits power for detecting Codex-specific features in django. Codex/sympy has n=84 with 28.6% pass (floor effect limits power in the opposite direction).

5. **Codex convergence.** The +10.3pp improvement in Codex sympy from early to late runs is concerning. If this reflects genuine learning, then early Codex runs are biased downward.

6. **Thinking block format differences.** Sonnet thinking blocks and Codex reasoning summaries are architecturally different (extended thinking vs. reasoning items). Per-call reasoning coverage differs (28.8% vs 60.1%). Direct comparison of thinking-layer features across models requires caution -- polarity differences could reflect format differences rather than genuine cognitive differences.

7. **5 Sonnet-only tasks.** 5 tasks were run on Sonnet but not Codex. The Codex task set is a strict subset of the Sonnet task set.

8. **Interaction effects are underpowered.** The deliberation x diagnostic_precision interaction is computed on quadrant splits (n~22 per cell). A formal interaction model is needed before this can be treated as a confirmed finding.

9. **Within-repo permutation is weaker than within-task.** The permutation test shuffles labels within repo, controlling for between-repo confounds but not for within-repo task difficulty variation. Within-task permutation (on tasks with mixed outcomes in both models) is the stronger test but requires more data.

10. **No predictive evaluation.** We report associations, not prediction. There is no held-out AUC, calibration curve, or out-of-sample test. Claims about "prediction viability" or "reliability prediction" are premature.

---

## 10. IMPLICATIONS FOR PHASE 1

### 10.1 Gate Design Must Be Model-Specific

A universal gate will not work. Features that signal quality in Sonnet may signal distress in Codex. Phase 1 must implement:
- **Sonnet gate:** Check deliberation_length (per-call reasoning length) and diagnostic precision (code-specific references in thinking). The interaction between these two is the strongest predictor.
- **Codex gate:** Check think_t_compat_fraction (environment struggle in reasoning) and fail_streak_max (error streaks). These are the only faithful Codex features.

### 10.2 Focus on Early Trajectory

Both models show that early_error_rate is associated with final outcome. A gate based on fail_streak_max is a natural candidate for Phase 1 testing, but no operating characteristics (sensitivity, false positive rate) have been computed from Phase 0 data. Phase 1 must empirically determine threshold values and their operating characteristics.

### 10.3 The Interaction Gate

For Sonnet, the most powerful gate would require both conditions:
- deliberation_length above the per-task median AND
- think_diagnostic_precision above the per-task median

This combination yields 73% pass rate vs 23-38% for either condition alone. The interaction bonus (+0.56) far exceeds any main effect, suggesting a nonlinear association. However, the quadrant-split approach (n~22 per cell) is exploratory; a formal interaction model with uncertainty intervals is needed to confirm this is not an artifact of the discretization.

### 10.4 What Phase 1 Must Test

1. Does gating on model-specific features improve pass rate? (intervention test)
2. Is the deliberation x precision interaction causal? (If we prompt for more code-specific reasoning, does success improve?)
3. Can a meta-gate detect the polarity flips at runtime? (Model identification from behavioral exhaust)
4. Do the structural features (fail_streak_max, early_error_rate) generalize to models beyond Sonnet and Codex?

---

## 11. METHODOLOGY NOTES

### 11.1 Spearman Implementation

All Spearman correlations use a custom implementation with correct tie handling and exact p-values from the incomplete beta function (regularized). Validated against scipy on known data (perfect positive: rho=1.0, perfect negative: rho=-1.0, zero correlation: rho=0.2, p=0.75 for n=5).

### 11.2 CWC Decomposition

The CWC (Confound-Within-Confound) approach used in this analysis computes within-repo Spearman correlations for each major repo (django, sympy) separately, then combines them using Fisher's method (chi-squared = -2 * sum(log(p_i)), df = 2k). The weighted average rho uses sample-size weighting. This controls for repo-level pass rate differences while preserving within-repo signal.

**Note on terminology:** An earlier analysis (research-narrative.md) used a Mundlak-style cluster-mean centering decomposition into beta_within and beta_between. The final deliverable and memo use the Fisher-combined within-repo approach described above. These are related but distinct methods. The Fisher-combined approach is the one reported in all final results. The Mundlak results are superseded.

### 11.3 Permutation Test

Within-repo permutation test: for each permutation, success labels are shuffled independently within each repo (preserving repo-level pass rates). The test statistic is the weighted average mean difference (pass - fail) across repos. 10,000 permutations. This controls for between-repo confounds (different pass rates, different codebases) but does NOT control for within-repo task difficulty variation. A stronger test -- within-task permutation on tasks with mixed outcomes in both models -- is the gold standard but requires sufficient mixed-outcome tasks (see Section 14).

### 11.4 Thinking Block Extraction

Sonnet: `event.message.content[].type == "thinking"`, key = "thinking"
Codex: `event.item.type == "reasoning"`, key = "text"

Both models have 100% coverage (every run has thinking/reasoning content). Sonnet produces ~2x more internal reasoning per run than Codex.

---

## 12. MATCHED-SET ANALYSIS (70 Shared Tasks)

### 12.1 Pass Rates on Matched Set

All cross-model comparisons should use the 70 shared tasks to avoid task-selection bias.

| Model | Matched Runs | Passes | Pass Rate |
|-------|-------------|--------|-----------|
| Sonnet | 178 | 88 | 49.4% |
| Codex | 190 | 78 | 41.1% |

The 8pp gap (49.4% vs 41.1%) on matched tasks is larger than previously reported and means "similar aggregate performance" claims should be qualified.

### 12.2 Matched-Set Per-Repo Breakdown

| Model | Repo | Runs | Passes | Pass Rate |
|-------|------|------|--------|-----------|
| Sonnet | sympy | 87 | 36 | 41.4% |
| Sonnet | django | 43 | 36 | 83.7% |
| Codex | sympy | 84 | 24 | 28.6% |
| Codex | django | 71 | 52 | 73.2% |

The gap is present in both major repos: 12.8pp in sympy, 10.5pp in django.

### 12.3 Within-Task Cross-Model Permutation: Not Feasible

Zero tasks have mixed outcomes (both pass and fail replicates) in BOTH models simultaneously. This means the strongest confound control -- within-task permutation across models -- cannot be performed with current data.

Tasks with mixed outcomes within a single model:
- **Sonnet:** 7 tasks (35+ runs), concentrated in sympy and pytest-dev
- **Codex:** 5 tasks (18 runs), concentrated in sympy and django

Phase 1 must collect 5+ replicates per model on 10+ tasks to enable within-task permutation.

---

## 13. TRAJECTORY PATTERNS BY REPO

### 13.1 Error Rates by Trajectory Position (Sonnet/sympy)

| Outcome | Early | Mid | Late |
|---------|-------|-----|------|
| Fail | 11.4% | 11.5% | 5.3% |
| Pass | 4.4% | 6.3% | 3.8% |

Fail runs have 2-3x the error rate in the early trajectory. By late trajectory, rates converge.

### 13.2 The Call Count Reversal

n_calls shows a feature x repo interaction:
- **Sympy** (balanced): fail runs average 20.7 calls vs pass 14.6 (more calls = flailing)
- **Django** (high pass): pass runs average 14.9 calls vs fail 11.7 (more calls = thorough completion)

This pattern holds in BOTH models. Any gate using n_calls must account for repo-level (or difficulty-level) base rates.

---

## APPENDIX: FEATURE DEFINITIONS

| Feature | Tier | Source | Definition |
|---------|------|--------|------------|
| fail_streak_max | 0 | tool_calls | Max consecutive error results |
| early_error_rate | 0 | tool_calls | Error rate in first 1/3 of calls |
| first_edit_position | 0 | tool_calls | Position of first Edit/Write call (normalized) |
| unique_files_touched | 0 | tool_calls | Count of distinct files edited |
| edit_churn_rate | 0 | tool_calls | Total edits / unique files |
| test_run_count | 0 | tool_calls | Count of Bash calls containing "test" |
| n_calls | 0 | tool_calls | Total state-modifying calls |
| hedging_score | 1 | reasoning_text | Hedge word density (might, could, perhaps...) |
| deliberation_length | 1 | reasoning_text | Mean characters per reasoning block |
| backtrack_count | 1 | reasoning_text | Backtrack marker density (actually, wait, instead...) |
| verification_score | 1 | reasoning_text | Verification phrase density |
| planning_score | 1 | reasoning_text | Planning phrase density (first, then, next...) |
| metacognitive_density | 2 | reasoning_text | Self-correction marker density |
| tentative_density | 2 | reasoning_text | Tentative language density (let me try, maybe...) |
| insight_density | 2 | reasoning_text | Insight phrase density (I understand, actually...) |
| instead_contrast_density | 2 | reasoning_text | Contrastive marker density |
| self_directive_density | 2 | reasoning_text | Self-directive density (let me, I should...) |
| precision_naming_score | 2 | reasoning_text | Backtick identifier density |
| reasoning_to_action_alignment | X | reasoning_text + tool_calls | File name match between reasoning and next edit |
| think_diagnostic_precision | CWC | thinking/reasoning blocks | Code-specific reference density in internal reasoning |
| think_reasoning_clarity | CWC | thinking/reasoning blocks | diagnostic_precision minus confusion_score |
| think_t_func_refs | CWC | thinking/reasoning blocks | Function reference density in internal reasoning |
| think_t_compat_fraction | CWC | thinking/reasoning blocks | Compatibility/environment sentence fraction |
| think_t_pivots | CWC | thinking/reasoning blocks | Strategy pivot density in internal reasoning |

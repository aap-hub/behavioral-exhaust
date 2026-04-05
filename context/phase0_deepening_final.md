# Phase 0 Deepening Analysis (Post-Correction)

**Date:** 2026-03-29
**Basis:** All findings below use the corrected DB numbers: 373 validated runs (183 Sonnet, 190 Codex), 75 unique tasks, 70 shared.

---

## PASS 2: What Is the Honest Story?

### The 3-5 Claims We Can Make with Full Confidence

**Claim 1: Task difficulty dominates model differences.**
On 70 shared tasks, 87.1% agreement (kappa=0.742). The models pass and fail the same tasks the vast majority of the time. This means any feature that correlates with success could be indexing task difficulty rather than agent reasoning quality. The CWC and permutation tests partially address this, but within-repo permutation does not control within-repo task difficulty variation.

Evidence: 27 both-pass, 34 both-fail, 7 Sonnet-only, 2 Codex-only. Django: 100% agreement (23/23). Sympy: 83% (25/30). The disagreement cases are concentrated in sympy.

**Claim 2: Structural error features are the most robust cross-model signals.**
fail_streak_max and early_error_rate are associated with failure in both models within sympy. These require no text analysis, no model-specific calibration, and no thinking block access. They are the cheapest, most portable features in the pipeline.

Evidence: Both features are negative-signed and p<0.05 in both Sonnet/sympy and Codex/sympy independently.

**Claim 3: Linguistic features are model-specific.**
No linguistic feature shows the same significant association in both models. The confirmed polarity flip on instead_contrast_density (Sonnet +0.282 p=0.008, Codex -0.264 p=0.020 in sympy) demonstrates that the same surface marker can associate with opposite outcomes. This is not an artifact of aggregation -- it is within the same repo.

Evidence: The flip survives the stringent criterion of significance in both models with opposite signs within sympy.

**Claim 4: The thinking/message dissociation is real (Sonnet-specific observation).**
"Actually" in thinking blocks correlates at -0.253 with success; in messages at +0.494. This is the cleanest example of layer-specific signal. A feature pipeline that conflates thinking and message content will cancel real signals.

Evidence: Observed in Sonnet data. Not tested for Codex due to different reasoning format. Should be framed as a Sonnet-specific observation, not a general law.

**Claim 5: Hedging is dead. Domain-specific markers are alive.**
Hyland's 209-term academic hedging vocabulary carries zero signal (p=0.60). Domain-specific markers (contrastive language, metacognitive markers, tentative language) carry signal, but that signal is model-specific and sometimes repo-specific. The null result on hedging is as important as the positive findings -- it tells us that LLM uncertainty is expressed through domain-specific patterns, not academic prose conventions.

Evidence: hedging_score is null in every analysis, every model, every repo. Random noise control confirms clean pipeline.

### What Needs More Data (Phase 1)

1. **Within-task permutation across models.** Zero tasks in the current dataset have mixed outcomes in BOTH models simultaneously (i.e., both pass and fail replicates in Sonnet AND in Codex for the same task). This means the strongest faithfulness test -- within-task cross-model permutation -- cannot be run. Phase 1 must collect more replicates per task.

2. **Interaction model formalization.** The deliberation x diagnostic_precision interaction (73% pass in the high-high quadrant) is the strongest observational association, but it uses quadrant splits with n~22 per cell. A formal logistic regression with an interaction term, plus bootstrap CIs, is needed.

3. **Codex feature extraction parity.** Codex tool_calls have no per-call linguistic features in the DB (deliberation_length, hedging_score, etc. are all NULL for Codex). The Codex features reported in the deliverable were apparently computed at run-level from a separate extraction pipeline. Phase 1 must ensure feature extraction parity.

4. **Out-of-sample prediction.** No held-out set, no AUC, no calibration. Before any "prediction" language, we need cross-validation or a prospective test set.

5. **The polarity flip mechanism.** The confirmed flip on instead_contrast_density needs a qualitative audit: manually read 10 Sonnet pass cases and 10 Codex fail cases where this marker is high, and characterize the discourse function of the contrastive language. Is Sonnet really doing diagnosis and Codex really doing strategic pivoting? Or is it a format artifact?

### What Is Most Interesting for Anthropic

**The thinking/message dissociation is the Anthropic-specific finding.** Anthropic has invested heavily in extended thinking (the thinking block architecture). Our finding that the thinking layer carries structurally different -- and sometimes opposite -- signal from agent messages is directly relevant to:

1. **Safety monitoring.** If internal reasoning can be monitored for confusion/thrashing patterns (t_compat_fraction, t_pivots), this provides a non-invasive safety signal.

2. **Model evaluation.** The finding that message-layer features are mostly repo confounds while thinking-layer features carry genuine within-repo signal suggests that agent evaluations based on messages alone miss the real behavioral signal.

3. **The polarity flip as a model fingerprint.** The fact that instead_contrast_density flips between Sonnet and Codex is interesting because it suggests models have characteristic reasoning styles that produce different behavioral exhaust. This could be used for model identification from traces, or (more importantly) to understand when a model is reasoning diagnostically vs. strategically.

---

## PASS 3: Structural and Second-Order Effects

### Tool Sequence Patterns

Sonnet sympy shows a clear structural difference between pass and fail runs:
- **Error rates by trajectory position:**
  - Fail runs: early 11.4%, mid 11.5%, late 5.3%
  - Pass runs: early 4.4%, mid 6.3%, late 3.8%
- Fail runs have 2-3x the error rate in the early trajectory. The late trajectory convergence (5.3% vs 3.8%) suggests that by the end, both pass and fail runs have settled into a pattern -- fail runs just started with too many errors.

This supports the early_error_rate finding: the first third of the trajectory is where the signal is strongest.

### Trajectory Degradation by Repo

Sonnet deliberation_length by trajectory phase (sympy):
- Pass runs: early 10.7, mid 13.6, late 11.8 -- deliberation is sustained throughout
- Fail runs: early 6.8, mid 7.6, late 8.1 -- deliberation is low and stays low

Sonnet deliberation_length by trajectory phase (django):
- Pass runs: early 15.2, mid 7.5, late 9.5 -- starts high, drops (because easy tasks resolve quickly)
- Fail runs: early 9.7, mid 1.0, late 8.1 -- mid-trajectory collapse

The trajectory degradation pattern differs by repo:
- In **sympy** (balanced difficulty), pass/fail runs maintain their deliberation gap throughout the trajectory. The signal is persistent.
- In **django** (high pass rate), fail runs show a dramatic mid-trajectory collapse (deliberation drops to 1.0) before partially recovering. The signal is concentrated in the middle trajectory.

This suggests that trajectory-aware gating should be repo-sensitive -- or at least difficulty-sensitive.

### The Call Count Reversal

Interesting second-order pattern:
- **Sympy** (both models): Fail runs have MORE state-modifying calls (Sonnet: 20.7 vs 14.6; Codex: 21.0 vs 17.1). More calls = more flailing.
- **Django** (both models): Pass runs have MORE calls (Sonnet: 14.9 vs 11.7; Codex: 17.5 vs 14.3). More calls = more thorough completion on easy tasks.

This is a feature x repo interaction: n_calls is a failure signal in hard repos and a success signal in easy repos. Any feature pipeline that ignores this interaction will get the wrong sign for n_calls depending on the task mix. This is a concrete example of why repo-level (or difficulty-level) stratification is required.

### Within-Task Replication Data

Sonnet tasks with mixed outcomes (both pass and fail replicates):
- sympy__sympy-21612: 9 runs, 6 pass (67%)
- pytest-dev__pytest-7432: 8 runs, 2 pass (25%)
- pytest-dev__pytest-7220: 7 runs, 3 pass (43%)
- Plus 4 more tasks with 2-3 runs each

These 7 tasks (35+ runs) are the basis for the within-task permutation test used in the memo. The fact that sympy-21612 has 9 replicates makes it the single most informative task in the dataset for run-level behavioral variation.

Codex tasks with mixed outcomes:
- sympy__sympy-18057: 4 runs, 3 pass
- sympy__sympy-21614: 4 runs, 3 pass
- sympy__sympy-23262: 4 runs, 3 pass
- django__django-11905: 3 runs, 2 pass
- sympy__sympy-21627: 3 runs, 2 pass

Zero overlap between Sonnet-mixed and Codex-mixed task sets. This means within-task cross-model comparison of behavioral features (the strongest possible confound control) is currently impossible.

**Phase 1 priority:** Collect 5+ replicates per model on 10 sympy tasks to enable within-task permutation.

### Unresolved Questions

1. **Is the Codex pass rate really 41.1%?** This is substantially lower than the 47.6% reported in the original deliverable (which used different Codex run counts). The corrected number changes the narrative from "equivalent performance" to "Sonnet slightly better" (49.2% vs 41.1%). On the matched set this gap persists (49.4% vs 41.1%).

2. **What explains the Codex run count discrepancy?** The DB has 190 validated Codex runs (171 codex-gpt5.4 + 19 codex:gpt-5.4). The original deliverable reported 164. Were 26 runs added after the original analysis? Or was the original count a filtering error? This needs investigation.

3. **Is the Django ceiling effect obscuring Codex signal?** Codex/django passes at 73.2% (not 88.1% as originally reported). With 71 runs, there is more variance than originally assumed. Re-running Codex/django features on the corrected data might reveal new signals.

4. **The thinking block format question.** Per-call reasoning coverage: Sonnet 28.8%, Codex 60.1%. If Codex has 2x the per-call reasoning density, feature extraction from reasoning text is sampling different proportions of the trajectory for each model. A polarity flip could reflect this sampling difference rather than a genuine cognitive difference.

---

## Summary of Corrections Applied

| Item | Original Claim | Corrected Claim |
|------|----------------|-----------------|
| Total validated runs | 354 | 373 |
| Sonnet runs | 190 | 183 |
| Codex runs | 164 | 190 |
| Shared tasks | 65 | 70 |
| Sonnet-only tasks | 12 | 5 |
| Sonnet pass rate | 47.4% | 49.2% |
| Codex pass rate | 47.6% | 41.1% |
| Agreement | 86.2% (56/65) | 87.1% (61/70) |
| Kappa | 0.723 | 0.742 |
| Confirmed polarity flips | 3 | 1 (instead_contrast_density) |
| reasoning_to_action_alignment | Strongest predictor | RETRACTED (perm p=0.35) |
| Thinking volume (Sonnet) | 2.3M chars | 2.0M chars |
| Codex sympy n | 78 | 84 |
| Codex django n | 59 | 71 |
| Codex sympy pass rate | 30.8% | 28.6% |
| Codex django pass rate | 88.1% | 73.2% |
| Gate operating characteristics | 60%/20% | Removed (unsupported) |
| CWC method | Mundlak + Fisher (conflated) | Fisher-combined within-repo Spearman (standardized) |

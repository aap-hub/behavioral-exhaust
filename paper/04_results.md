# 4. Results

## 4.1 Aggregate Performance

Table 1 summarizes the validated dataset across both models.

**Table 1. Aggregate performance by model.**

| Model | Validated Runs | Pass Rate | Unique Tasks |
|-------|---------------|-----------|--------------|
| Sonnet 4.6 | 183 | 49.2% (90/183) | 75 |
| Codex GPT-5.4 | 190 | 41.1% (78/190) | 70 |
| **Combined** | **373** | **45.0%** | **75** |

Codex was run on a 70-task subset of the Sonnet task set (5 Sonnet-only tasks). All cross-model comparisons use the matched set of 70 shared tasks to avoid task-selection bias. On the matched set, Sonnet passes 49.4% of runs (88/178) and Codex passes 41.1% (78/190), an 8.3 percentage-point gap present in both major repositories: 12.8pp in sympy (Sonnet 41.4% vs. Codex 28.6%) and 10.5pp in django (Sonnet 83.7% vs. Codex 73.2%).

**Task-level agreement.** Despite the pass-rate gap, the models largely succeed and fail on the same tasks. Using majority-vote labeling per task on the 70 shared tasks:

**Table 2. Task-level agreement matrix (70 shared tasks, majority vote).**

|  | Codex Pass | Codex Fail |
|---|-----------|-----------|
| **Sonnet Pass** | 27 | 7 |
| **Sonnet Fail** | 2 | 34 |

Agreement: 87.1% (61/70), Cohen's kappa = 0.742 (substantial). Django shows perfect agreement (23/23 tasks). Sympy shows the most disagreement (25/30, 83%), consistent with its balanced difficulty providing the most room for model-specific differences.

## 4.2 Features Surviving CWC + Permutation

We applied a three-stage filter: (1) within-repo Spearman correlation at p < 0.05 in at least one major repository, (2) Fisher-combined within-repo p-value (CWC) at p < 0.05, and (3) within-repo permutation test (10,000 permutations, labels shuffled within repo) at p < 0.05. Table 3 presents the revised evidence hierarchy.

**Table 3. Revised evidence hierarchy.**

| Level | Features | Key Evidence |
|-------|----------|--------------|
| **Gold** (both models, structural) | fail_streak_max, early_error_rate | Sonnet/sympy: rho = -0.294 (p = 0.006), -0.273 (p = 0.011). Codex/sympy: rho = -0.296 (p = 0.009), -0.282 (p = 0.012). Same direction, both significant. |
| **Silver** (model-specific, all tests) | deliberation_length (Sonnet), think_t_compat_fraction (Codex) | Sonnet: CWC p = 0.003, perm p = 0.0004. Codex: CWC p = 0.010, perm p = 0.006. |
| **Moderate** (CWC + perm, weaker) | first_edit_position (Sonnet), instead_contrast_density (Codex) | Sonnet: CWC p = 0.001, perm p = 0.001, but no wave-2 replication. Codex: CWC p = 0.013, perm p = 0.007. |
| **Retracted** | reasoning_to_action_alignment | Perm p = 0.35; between-repo confound. See Section 4.2.1. |
| **Null** | hedging_score, verification_score, planning_score, precision_naming_score | No signal in any analysis (see Section 4.7). |

The Gold-tier features are both Tier 0 structural measures -- they require no text analysis, only the sequence of tool-call error flags. No linguistic feature is significantly associated with success in the same direction for both models.

**Table 4. Within-repo Spearman correlations for surviving features, sympy.**

| Feature | Sonnet rho (n = 87) | Sonnet p | Codex rho (n = 84) | Codex p |
|---------|-------------------|----------|-------------------|---------|
| fail_streak_max | -0.294 | 0.006 | -0.296 | 0.009 |
| early_error_rate | -0.273 | 0.011 | -0.282 | 0.012 |
| deliberation_length | +0.214 | 0.046 | -- | n.s. |
| instead_contrast_density | +0.282 | 0.008 | -0.264 | 0.020 |
| think_t_compat_fraction | -- | n.s. | -0.323 | 0.004 |
| backtrack_count | +0.359 | 0.0006 | -0.108 | > 0.05 |

**Table 5. Within-repo Spearman correlations for surviving features, django.**

| Feature | Sonnet rho (n = 44) | Sonnet p | Codex rho (n = 71) | Codex p |
|---------|-------------------|----------|-------------------|---------|
| first_edit_position | +0.493 | 0.0007 | -- | n.s. |
| deliberation_length | +0.396 | 0.008 | -- | n.s. |
| early_error_rate | -- | n.s. | -0.322 | 0.013 |

Sonnet's django results for early_error_rate are individually non-significant, likely a ceiling effect from the 84% pass rate compressing the failure distribution. Codex/django (73.2% pass rate, n = 71) retains enough failures for the structural feature to reach significance.

### 4.2.1 Retraction: reasoning_to_action_alignment

The original Phase 0 analysis reported reasoning_to_action_alignment as the strongest Bonferroni survivor (coefficient = +1.133, raw p = 0.00018, Bonferroni-adjusted p = 0.004). This feature measures whether the agent's reasoning text mentions the file it is about to edit. The finding was headline-worthy: agents that "name their target" before acting succeed more.

The finding does not survive the within-repo permutation test (p = 0.35). The pooled effect was inflated by between-repo confounding: repositories where the agent tends to name files (e.g., django, with its explicit file structure) also happen to have high pass rates. Once labels are shuffled within each repo, the association disappears.

We report this retraction prominently because it illustrates why the CWC methodology matters. A feature that appears highly significant in a pooled analysis (p = 0.00018) can be entirely driven by confound structure. The permutation test, by preserving repo-level pass rates, exposes the confound. This is a methodological success, not a failure: the pipeline's self-correction mechanism works.

## 4.3 The Polarity Flip

One feature shows a confirmed polarity flip -- significant in both models within the same repository, with opposite signs.

**Table 6. Polarity flips in sympy.**

| Feature | Sonnet rho (n = 87) | Sonnet p | Codex rho (n = 84) | Codex p | Status |
|---------|-------------------|----------|-------------------|---------|--------|
| instead_contrast_density | +0.282 | 0.008 | -0.264 | 0.020 | **Confirmed flip** |
| backtrack_count | +0.359 | 0.0006 | -0.108 | > 0.05 | Suggestive (Codex n.s.) |
| metacognitive_density | +0.138 | > 0.05 | -0.261 | 0.021 | Suggestive (Sonnet n.s.) |

The confirmed flip on `instead_contrast_density` means that words like "however," "but," and "instead" are associated with success in Sonnet but failure in Codex, within the same task repository. Qualitative inspection suggests the mechanism differs: in Sonnet, contrastive markers appear within diagnostic reasoning ("The function returns X, but the expected behavior is Y"), narrowing the gap between observed and expected behavior. In Codex, the same markers appear within strategic pivots ("However, let me try a different approach instead"), signaling abandonment of one approach for another.

For backtrack_count and metacognitive_density, the directional reversal is suggestive but only one side reaches significance. These remain hypotheses for Phase 1 testing with larger samples.

## 4.4 Thinking/Message Dissociation

A parser bug in the trace collector initially extracted agent messages (`block.get("text")`) rather than internal thinking blocks (`block.get("thinking")`). Correcting this revealed that the same lexical feature carries opposite signal depending on which layer it is extracted from.

**Table 7. The "actually" dissociation in Sonnet.**

| Layer | Feature | Correlation with success | Interpretation |
|-------|---------|------------------------|----------------|
| Internal thinking blocks | "actually" density | r = -0.253 | Genuine pre-action confusion |
| Agent messages | "actually" density | r = +0.494 | Performative self-correction |

Internal reasoning is present in every run (183/183 Sonnet runs, ~2.0M total characters, mean 10,765 chars/run) and is roughly 10x longer than the polished agent messages (~1,200 chars/run). Two additional features show a similar layer dissociation:

**Table 8. Layer-specific feature associations (Sonnet, n = 183).**

| Feature | Thinking rho | Thinking p | Message rho | Message p |
|---------|-------------|------------|-------------|-----------|
| tentative_density | -0.346 | 0.003 | -0.204 | 0.083 |
| insight_density | ~0 | n.s. | +0.248 | 0.034 |

Internal doubt (tentative_density in thinking: rho = -0.346, p = 0.003) is diagnostic; the same feature in messages does not survive (p = 0.083). Expressed correction (insight_density in messages: rho = +0.248, p = 0.034) is diagnostic; the thinking-layer version is near zero. The two layers carry structurally different information: **internal doubt lives in thinking; expressed correction lives in messages**. Any feature pipeline that conflates the layers will cancel real signals.

## 4.5 Trajectory Degradation

Signal quality degrades over the trajectory. We split each run into thirds by normalized call position and computed feature-outcome associations within each segment.

**Table 9. Feature-outcome association by trajectory position (Sonnet, n = 183).**

| Trajectory position | deliberation rho | deliberation p | alignment rho | alignment p |
|---------------------|-----------------|----------------|--------------|-------------|
| Early (0--33%) | +0.180 | 0.016 | +0.242 | 0.001 |
| Mid (33--67%) | +0.166 | 0.028 | +0.165 | 0.029 |
| Late (67--100%) | +0.038 | 0.615 | +0.026 | 0.735 |

Both features are associated with success in the early and middle trajectory segments and are completely non-associated in the late segment. By the final third, the agent has either found the fix or committed to a wrong approach; reasoning quality no longer discriminates. The implication for gating: a behavioral gate should focus on early and mid-trajectory decisions. Late-trajectory gating based on reasoning features is uninformative.

## 4.6 The Interaction Effect

In Sonnet/sympy (n = 87), deliberation_length and think_diagnostic_precision interact to produce a nonlinear association with success. We split both features at their per-repo medians to form four quadrants.

**Table 10. Quadrant analysis: deliberation x diagnostic precision (Sonnet/sympy).**

| Deliberation | Diagnostic Precision | Pass Rate | n |
|-------------|---------------------|-----------|---|
| High | High | 73% | 22 |
| High | Low | 23% | 22 |
| Low | High | 32% | 22 |
| Low | Low | 38% | 21 |

The interaction bonus is +0.56, computed as the excess of the high-high cell over the additive prediction from main effects (0.73 - (0.23 + 0.32 - 0.38) = 0.56). This is larger than any main effect in the dataset. Neither feature alone is sufficient: an agent that deliberates extensively without diagnostic precision (23%) performs worse than one that barely deliberates at all (38%). But an agent that thinks deeply *and* precisely about code artifacts succeeds 73% of the time.

In Codex/sympy, the same interaction is much weaker (+0.13), consistent with Codex's reasoning blocks being more strategic than diagnostic.

**Caveat.** This analysis is exploratory. Each quadrant contains approximately 22 runs. The interaction has not been tested with a formal interaction model, and the median-split approach can inflate apparent effects. These results motivate a formal interaction model in Phase 1 but should not be treated as confirmed.

## 4.7 Null Results

Seven features showed no meaningful association with success in any analysis. We report these because understanding what does not work is as informative as understanding what does.

**Table 11. Features with null results.**

| Feature | Expected Direction | Observed rho | p | Reason for Failure |
|---------|-------------------|-------------|---|-------------------|
| hedging_score (Hyland, 209 terms) | Negative | ~0 | 0.60 | Sonnet does not use academic hedge words when coding. The Hyland lexicon (might, could, perhaps, arguably) targets written prose, not agent reasoning. |
| verification_score | Negative | +0.02 | n.s. | Verification language is ubiquitous in all Sonnet reasoning regardless of outcome. Not discriminative. |
| planning_score | Negative | +0.09 | n.s. | "First," "then," "next" are default Sonnet discourse style, present in both passing and failing runs. |
| precision_naming_score | Positive | +0.04 | n.s. | Backtick-delimited identifiers are universal in Sonnet's code reasoning. No variance to exploit. |
| recovery_rate | Positive | -0.15 | n.s. | Recovery from errors is dominated by infrastructure noise (pip failures, import errors), not diagnostic quality. |
| fail_then_switch_rate | Positive | -0.37 | -- | Tool-switching after errors is associated with flailing, not principled diagnosis. The expected positive association was wrong. |
| causal_density | Positive | -0.03 | n.s. | "Because" and "since" are general discourse markers with no task-success signal. |

The random noise control column returned p = 0.52, confirming that the pipeline does not produce spurious significant results.

The death of Hyland hedging is the most theoretically consequential null. Academic hedging vocabulary -- the foundation of most linguistic uncertainty research -- carries zero signal in agent reasoning traces. Agent uncertainty, to the extent it is linguistically expressed, appears through domain-specific structural markers (tentative_density in thinking blocks, contrastive markers), not through the modal expressions (might, could, arguably) that characterize academic prose.

## 4.8 Cross-Wave Stability

Features were tested for replication across two independently collected waves: the pilot wave (n = 103 Sonnet runs) and the protocol wave (n = 77 Sonnet runs, collected under a locked protocol with pre-registered task set).

**Table 12. Cross-wave replication (Sonnet).**

| Feature | Pilot rho (n = 103) | Pilot p | Protocol rho (n = 77) | Protocol p | Replicates? |
|---------|-------------------|---------|---------------------|------------|-------------|
| deliberation_length | +0.320 | 0.001 | +0.273 | 0.016 | **Yes** |
| reasoning_to_action_alignment | +0.300 | 0.002 | +0.285 | 0.012 | Yes (but retracted on permutation grounds) |
| first_edit_position | +0.241 | 0.014 | +0.039 | 0.736 | **No** |

Deliberation_length replicates: the effect is consistent in direction and significance across both waves, making it the most robust Sonnet-specific finding. First_edit_position does not replicate in wave 2 alone (rho = +0.039, p = 0.736), which is why it is classified as Moderate rather than Silver in the evidence hierarchy despite surviving CWC and permutation. The wave-2 failure suggests the association may be driven by specific task characteristics present in the pilot but not the protocol wave, or by insufficient power in the smaller wave-2 sample.

Reasoning_to_action_alignment shows apparent cross-wave replication but is retracted on permutation grounds (Section 4.2.1). Cross-wave consistency does not protect against a confound that is present in both waves -- both waves contain the same repository structure that drives the spurious association.

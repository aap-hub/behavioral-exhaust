# Paper Outline: Behavioral Exhaust Mining for Agent Task Success

## Title

**Behavioral Exhaust Mining: What Internal Reasoning Structure Reveals About Agent Task Success**

Alternative: *The Thinking/Message Dissociation: Why Same Words Associate with Opposite Outcomes Across Agent Architectures*

---

## Abstract (150 words)

We study whether structural properties of agent reasoning are associated with task success in code repair tasks. Across 373 validated runs (183 Claude Sonnet 4.6, 190 Codex GPT-5.4) on 75 SWE-bench Lite tasks, we extract 24 behavioral features from agent reasoning traces without any API overhead. Despite broadly similar performance profiles (Sonnet 49%, Codex 41% on matched tasks), one linguistic feature -- contrastive marker density -- shows a confirmed polarity flip: it is associated with success in Sonnet but failure in Codex within the same repository. Only two structural features -- error streaks and early error rate -- transfer across models. We discover a thinking/message dissociation: the word "actually" in internal reasoning correlates negatively with success (genuine confusion) while the same word in agent messages correlates positively (performative self-correction). A Sonnet-specific interaction between deliberation length and diagnostic precision yields 73% pass rate, far exceeding either feature alone. These findings establish that behavioral exhaust carries model-specific signal associated with task success but require Phase 1 intervention testing and out-of-sample validation before predictive claims can be made.

---

## 1. Introduction

### The Gap

Agent reliability research has focused on two approaches: (a) eliciting confidence scores from models (verbalized P(True), selective prediction via softmax), and (b) external evaluation (critic models, human review). Both have known limitations:

- Self-reported confidence is near-useless for agents (Rabanser et al. 2026)
- CoT content is unfaithful 75% of the time (Chen et al. 2025)
- External critics add latency and cost per decision

A third approach exists but is underexplored: mining the behavioral exhaust that agents already produce -- reasoning text structure, tool-call patterns, error trajectories -- for predictive signal. This is zero-cost (the exhaust already exists), non-invasive (no prompt modification), and potentially complementary to existing methods.

### Our Contribution

1. A behavioral feature extraction pipeline for agent reasoning traces (24 features, 3 tiers)
2. A cross-model comparison showing model-specific feature associations, including one confirmed polarity flip
3. Discovery of the thinking/message dissociation (same features, opposite polarity across layers)
4. A Sonnet-specific nonlinear interaction effect (deliberation x diagnostic precision) that shows the strongest observational association with success
5. A CWC methodology (Fisher-combined within-repo Spearman + within-repo permutation) for controlling repo-level heterogeneity

### Positioning

This work sits at the intersection of:
- Agent reliability (Rabanser et al. 2026, Anthropic safety research)
- Reasoning faithfulness (Chen et al. 2025, Lanham et al. 2023)
- Selective prediction (Geifman & El-Yaniv 2017, applied to agent actions)
- SWE-bench evaluation methodology (Jimenez et al. 2024)

---

## 2. Related Work

### 2.1 Agent Reliability and Confidence

- Rabanser et al. (2026): "Towards a Science of AI Agent Reliability" -- establishes that self-reported confidence is unreliable for agents. Our work shows behavioral structure can substitute.
- Kadavath et al. (2022): "Language Models (Mostly) Know What They Know" -- P(True) calibration for QA. We extend to agent tool calls where P(True) is unavailable (no API access, OAuth-only constraint).

### 2.2 Reasoning Faithfulness

- Chen et al. (2025): "Reasoning Models Don't Always Say What They Think" -- CoT is unfaithful 75% of time but unfaithful CoTs are systematically LONGER. This structural signal is exactly what we exploit.
- Lanham et al. (2023): "Measuring Faithfulness in Chain-of-Thought Reasoning" -- paraphrasing and early answering tests for CoT faithfulness.
- Our thinking/message dissociation extends this: the SAME feature has opposite polarity in thinking vs messages, confirming that layers carry structurally different information.

### 2.3 Uncertainty Quantification in LLMs

- Xiong et al. (2024): "Can LLMs Express Their Uncertainty?" -- survey of verbalized uncertainty methods.
- Li et al. (2025): "Lexical Hints of Accuracy in LLM Reasoning Chains" -- hedging word density predicts reasoning correctness (F1=0.83). Our work replicates the finding that domain-specific markers outperform academic hedging, and extends it to agent actions.
- Our null result on Hyland hedging vocabulary confirms that LLM uncertainty is expressed through domain-specific markers, not academic prose conventions.

### 2.4 SWE-bench and Code Repair Evaluation

- Jimenez et al. (2024): SWE-bench Lite -- the task corpus we use.
- Anthropic (2025): "A Statistical Approach to Model Evaluations" -- clustered SEs, paired tests, power analysis. We adopt their methodology for within-repo analysis.

---

## 3. Method

### 3.1 Task Selection and Agent Configuration

- 75 SWE-bench Lite tasks from 9 repositories
- Two models: Claude Sonnet 4.6 (183 validated runs), Codex GPT-5.4 (190 validated runs)
- Ungated (no intervention), 30-minute timeout
- Full stream-json traces captured in SQLite

### 3.2 Independent Validation

- Agent self-report NOT used for labeling
- Replay edits on fresh environment, run FAIL_TO_PASS tests
- 95% validation rate (373 validated of ~395 total runs)
- Validation provenance tracked per-run

### 3.3 Behavioral Exhaust Mining

**Tier 0 -- Structural features** (from tool-call sequence, no text analysis): fail_streak_max, early_error_rate, first_edit_position, unique_files_touched, edit_churn_rate, test_run_count, n_calls

**Tier 1 -- Linguistic features** (from per-call reasoning text): hedging_score, deliberation_length, backtrack_count, verification_score, planning_score

**Tier 2 -- Domain-specific features** (from per-call reasoning text): metacognitive_density, tentative_density, insight_density, instead_contrast_density, self_directive_density, precision_naming_score, reasoning_to_action_alignment

**CWC Thinking Features** (from internal reasoning blocks): diagnostic_precision, reasoning_clarity, t_func_refs, t_compat_fraction, t_pivots

All linguistic features use mean aggregation (per-call, per-token density) to control for the task-length confound.

### 3.4 Thinking Block Extraction

- Sonnet: Extended thinking blocks (`message.content[].type == "thinking"`)
- Codex: Reasoning items (`item.type == "reasoning"`)
- 100% coverage for both models
- Sonnet: 2.0M total chars, ~11K/run; Codex: 944K total chars, ~5.0K/run

### 3.5 Statistical Methods

1. **Within-repo Spearman** for django (high pass rate) and sympy (balanced) separately
2. **CWC decomposition**: Fisher's combined p-value across repos (within-repo Spearman, not Mundlak)
3. **Within-repo permutation test**: 10,000 permutations with labels shuffled within repo (controls between-repo confounds but not within-repo task difficulty)
4. **Cross-model comparison**: feature-by-feature direction agreement on the 70 shared tasks
5. **Combined analysis**: Within-repo rank correlations with model as a covariate (note: the original memo promised mixed-effects logistic regression; the actual reported results are primarily rank correlations with Fisher combination)

---

## 4. Results

### 4.1 Aggregate Performance

| Model | Validated Runs | Pass Rate | Unique Tasks |
|-------|---------------|-----------|-------------|
| Sonnet | 183 | 49.2% | 75 |
| Codex | 190 | 41.1% | 70 |

Shared tasks: 70. Matched-set pass rates: Sonnet 49.4%, Codex 41.1%.
Task-level agreement on 70 shared tasks: 87.1% (kappa=0.74).

### 4.2 Features That Survive CWC + Within-Repo Permutation

**Sonnet (model-specific):** deliberation_length (+, CWC p=0.003, perm p=0.0004), first_edit_position (+, CWC p=0.001, perm p=0.001 -- but no wave-2 replication)
**Codex (model-specific):** think_t_compat_fraction (-, CWC p=0.010, perm p=0.006), instead_contrast_density (-, CWC p=0.013, perm p=0.007)
**Both models (structural):** fail_streak_max (-), early_error_rate (-) -- significant within sympy for both models; these survive as cross-model features but were not subjected to the same three-part CWC+permutation criterion (they are within-repo Spearman significant in both models independently)

### 4.3 Polarity Flip

One feature shows a confirmed polarity flip (significant in both models, opposite signs) within sympy:
- instead_contrast_density: +0.282 (p=0.008) in Sonnet, -0.264 (p=0.020) in Codex

Two additional features show suggestive directional reversal (only one side significant):
- backtrack_count: +0.359 (p=0.0006) in Sonnet, -0.108 (p>0.05) in Codex
- metacognitive_density: +0.138 (p>0.05) in Sonnet, -0.261 (p=0.021) in Codex

### 4.4 The Thinking/Message Dissociation

"Actually" in thinking blocks: r=-0.253 with success (genuine confusion)
"Actually" in agent messages: r=+0.494 with success (performative correction)

### 4.5 The Interaction Effect

Deliberation length x diagnostic precision in Sonnet/sympy:
- Both high: 73% pass (n=22)
- Either alone: 23-32% pass
- Both low: 38% pass
- Interaction bonus: +0.56

### 4.6 Diagnostic Precision Dissociation

On 6 tasks where Sonnet passes but Codex fails, Sonnet's diagnostic precision is 4-16x higher per thousand characters of thinking content.

### 4.7 Null Results

hedging_score, verification_score, precision_naming_score, causal_density: null in all analyses. Academic hedging is dead as a signal.

---

## 5. Discussion

### 5.1 What the Human Doesn't See

The strongest behavioral signal lives in layers invisible to the user:
- Internal thinking blocks (not messages)
- Feature interactions (not individual features)
- Model-specific polarities (not universal markers)

A human reviewer reading agent messages would miss the diagnostic precision signal in thinking blocks and might misinterpret contrastive language (positive in Sonnet, negative in Codex).

### 5.2 Implications for Gating

1. **Gates must be model-specific.** Universal feature thresholds will misclassify.
2. **Gates should focus on early trajectory.** Early error rate is the most generalizable feature.
3. **Nonlinear gates outperform linear ones.** The deliberation x precision interaction is the strongest practical predictor.
4. **Gates should operate on the right layer.** Extracting features from the wrong layer (messages vs thinking) can produce opposite signal.

### 5.3 The Polarity Flip Observation

Why might the same words associate with opposite outcomes in different models? The confirmed flip on `instead_contrast_density` suggests:
- Sonnet may use contrastive language diagnostically (narrowing possibilities)
- Codex may use contrastive language strategically (abandoning approaches)
- The word is an epiphenomenon of the reasoning strategy, not a direct measure of uncertainty

This is a Sonnet-specific observation that needs replication on other models. It implies that behavioral exhaust mining, if it works for reliability, would require model-specific calibration -- there is no universal uncertainty lexicon. However, the thinking block format differences between models (extended thinking vs reasoning items, 28.8% vs 60.1% per-call coverage) mean the polarity flip could partly reflect extraction artifacts rather than genuine cognitive differences.

### 5.4 Relationship to Faithfulness

Our thinking/message dissociation is consistent with Chen et al.'s finding that CoT content is unfaithful. But we add nuance: the STRUCTURE of unfaithful content still carries signal. An agent that says "actually" in its public message is performing metacognition for the user; an agent that says "actually" in its private thinking is genuinely confused. Both are useful signals, but they point in opposite directions.

---

## 6. Limitations

1. **All findings are correlational.** No causal intervention. Association, not prediction.
2. **No predictive evaluation.** No held-out AUC, calibration, or out-of-sample test.
3. **Model-specificity:** findings may not transfer to other models
4. **SWE-bench Lite only:** code repair tasks are a narrow domain
5. **Sample size:** n=87 for Sonnet/sympy, n=84 for Codex/sympy
6. **Thinking block format differences** across models may confound polarity comparisons
7. **5 Sonnet-only tasks** mean task sets are not identical
8. **Codex convergence** (+10.3pp from early to late) may bias early runs
9. **Within-repo permutation** does not control within-repo task difficulty
10. **Interaction analysis** uses quadrant splits (n~22 per cell), not a formal interaction model

---

## 7. Future Work: Phase 1 Hook-Based Intervention

Phase 1 will test whether gating on Phase 0 features improves outcomes:

1. **Intervention A -- Model-specific behavioral gate:** Block tool calls when the model's specific failure markers are detected (e.g., Sonnet low deliberation + low precision; Codex high compat_fraction).

2. **Intervention B -- Prompt augmentation:** When the gate triggers, inject a prompt asking the agent to trace the code path before editing (targeting the diagnostic precision feature).

3. **Intervention C -- Cross-model critic:** Use the other model as a critic when the behavioral gate triggers. Exploit the fact that models fail on different tasks 14% of the time.

4. **Outcome metric:** pass^k (probability of at least one success in k runs). Selective risk-coverage curves are a goal but require a working predictive system, which Phase 0 has not established.

5. **Design:** Within-subject (same task, gated vs ungated). Sample size and feature thresholds to be determined by power analysis based on Phase 0 effect sizes. Phase 0 has not produced a validated predictive system, so Phase 1 thresholds must be pre-registered based on the observed associations and then tested prospectively.

---

## 8. References

### Our Analysis Context Files

| File | Content |
|------|---------|
| context/phase0_final_deliverable.md | Full Phase 0 analysis with all numerical results |
| context/phase0_analysis_opus.md | Previous Sonnet-only analysis (204 runs) |
| context/thinking_block_discovery.md | Round 1 thinking block features (9 features) |
| context/thinking_block_discovery_round2.md | Round 2 thinking block features (11 features, AUC=0.833) |
| context/tier2_results.md | Tier 2 feature analysis (20 features, BH FDR) |
| context/tier2_framework_sonnet.md | Tier 2 semantic framework design |
| context/tier2_statistical_review.md | Statistical review of Tier 2 analysis |
| context/anthropic-methods-synthesis.md | Synthesis of 17 Anthropic publications |
| context/design-decision-trail.md | 10 design decisions with rationale |
| context/codex-pipeline-audit.md | First Codex adversarial audit |
| context/codex-pipeline-audit-v2.md | Second Codex audit (17 issues found) |
| PHASE0_MEMO.md | Phase 0 memo (Sonnet-only, to be updated) |
| data/uga_phase0_complete_final.db | SQLite database (373 validated runs) |

### Literature

| Reference | Key Finding Relevant to Our Work |
|-----------|----------------------------------|
| Rabanser et al. (2026) | Self-reported agent confidence is unreliable |
| Chen et al. (2025) | CoT is unfaithful 75% of time but structurally informative |
| Lanham et al. (2023) | Faithfulness measurement via paraphrasing and early answering |
| Kadavath et al. (2022) | P(True) calibration for language models |
| Xiong et al. (2024) | Survey of verbalized uncertainty in LLMs |
| Li et al. (2025) | Lexical hints of accuracy in reasoning chains |
| Jimenez et al. (2024) | SWE-bench evaluation methodology |
| Anthropic (2025) | Statistical approach to model evaluations |
| Kratzer (1991) | Modal semantics (theoretical background for hedging analysis) |
| Geifman & El-Yaniv (2017) | Selective prediction framework |
| Hyland (2005) | Academic hedging vocabulary (our null result) |

---

## Appendix A: Key Quantitative Claims

All claims in this paper are supported by the following numerical evidence (verified from DB 2026-03-29):

1. "Sonnet 49.2%, Codex 41.1%" -- Sonnet 90/183, Codex 78/190 (full sets). Matched set: Sonnet 88/178 = 49.4%, Codex 78/190 = 41.1%.
2. "87.1% task agreement" -- 61/70 shared tasks agree on majority-vote pass/fail
3. "kappa=0.74" -- Cohen's kappa on the 2x2 task-level agreement matrix (70 shared tasks)
4. "73% pass rate" -- 16/22 runs in the high-deliberation, high-precision quadrant (Sonnet/sympy, exploratory)
5. "4-16x diagnostic precision" -- range of Sonnet/Codex precision ratios on disagreement tasks (observational)
6. "+0.56 interaction bonus" -- 0.73 - (0.23 + 0.32 - 0.38) in quadrant analysis (exploratory, needs formal interaction model)
7. "2.0M chars of thinking" -- sum of thinking block characters across 183 Sonnet runs
8. "confirmed polarity flip rho=+0.282 vs -0.264" -- instead_contrast_density in sympy, both p<0.05

## Appendix B: Reproducibility

All analysis can be reproduced from:
- `data/uga_phase0_complete_final.db` (read-only backup)
- Feature extraction code in `src/feature_definitions.py`, `src/trace_collector.py`
- Analysis code in `src/analysis.py`
- The raw_stream_json field in the runs table contains complete agent traces for re-extraction

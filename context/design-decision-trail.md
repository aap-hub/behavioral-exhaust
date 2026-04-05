# UGA Design Decision Trail

Each decision recorded with rationale, alternatives considered, and evidence.
Use this when writing up the final report.

## Decision 1: Research Question Pivot

**From:** "Does gating improve agent reliability?" (obvious)
**To:** "What determines the quality of uncertainty signals for agent tool-call decisions?"

**Rationale:** The original question has an obvious answer (yes, if the signal is good). The novel question is WHEN the signal is trustworthy. Two orthogonal factors: signal source (introspective vs extrospective) and trajectory position (early vs late in task).

**Evidence:** Anthropic's "Towards a Science of AI Agent Reliability" (Rabanser et al. 2026, arXiv:2602.16666) shows self-reported confidence is near-useless. The question isn't whether to gate — it's what signal to gate on and when.

**Decided during:** CEO review, premise challenge phase.

---

## Decision 2: Signal Architecture — Behavioral Exhaust over API Confidence

**From:** API-based confidence elicitation (zero-shot verbalized, P(True), post-hoc)
**To:** Behavioral exhaust mining (introspective) + cross-model comparison (extrospective)

**Rationale:**
1. OAuth-only constraint: no Anthropic API key, so no direct API calls for confidence
2. No log-probs available (Anthropic doesn't expose them via API or Claude Code)
3. Inline confidence injection confounds the task (meta-evaluation changes behavior)
4. Anthropic's faithfulness research (Chen et al. 2025, arXiv:2505.05410) shows CoT content is unfaithful <25% of the time — but STRUCTURAL properties (length, hedging patterns) may be more robust

**Alternatives considered:**
- Sampled P(True) via `claude -p` (20 calls per decision point) — rejected as too costly
- Inline confidence prompt ("output CONFIDENCE: 0.XX") — rejected as confounding
- Direct API calls with API key — rejected by user preference for OAuth economics

**Evidence:** Chen et al. 2025 found unfaithful CoTs are systematically LONGER (2064 vs 1439 tokens). This is a structural signal the model can't easily fake.

**Decided during:** CEO review, auth constraint discussion.

---

## Decision 3: Feature Set — Tier 1 (Hyland Lexicon + Structural)

**From:** Tier 2 (Kratzer-style modal decomposition with spaCy pipeline)
**To:** Tier 1 (Hyland hedge lexicon count + 3 structural features)

**Rationale:**
1. Codex adversarial review: "built linguistics-heavy stack before proving simple baselines insufficient"
2. User: "I think your assumption that Tier 2 won't save it is wrong" — initially chose Tier 2
3. Then user pushed back: "do we need modal quantification, or how else can we measure doubt?"
4. Realized: the selective prediction framework is score-agnostic. It needs g(x) that predicts error, not a theory of doubt.
5. The empiricist's ladder: measure first (Tier 1), decompose later (Tier 2) if signal exists
6. User: "I think we should go with Tier 2 to make it strong from the beginning" — chose Tier 2
7. Then lost the plot in feature engineering complexity
8. Final resolution: "Yes, simplify to Tier 1" — Hyland lexicon + structural counts

**Key insight from user:** "We're just using those modals as strong signals of sentiment, which are there for carving nature at the joints, where nature here is the agent's intent."

**Validating literature (discovered after the decision):**
- "Lexical Hints of Accuracy in LLM Reasoning Chains" (arXiv:2508.15842, Aug 2025) — validates hedging word density as the strongest predictor of LLM reasoning correctness
- "LLM Reasoning Predicts When Models Are Right" (arXiv:2602.09832, Feb 2026) — LIWC tentativeness category achieves F1=0.83 for predicting incorrect predictions; incorrect reasoning is 5x more likely to use epistemic hedging
- "Trace Length is a Simple Uncertainty Signal" (arXiv:2510.10409, Oct 2025, Apple) — validates deliberation_length as a zero-cost uncertainty estimator

**Phase 2 extension:** If Tier 1 shows signal, decompose into Kratzer categories (modal force, flavor, commitment) to understand WHY. Connects to user's modal logic background (PhD, formal systems).

**Decided during:** Eng review, after Codex outside voice and philosophical reflection on measurement.

---

## Decision 4: Model Selection — Sonnet 4.6 Primary

**Choice:** Claude Sonnet 4.6 for Phase 0-1, Opus 4.6 as Phase 2 extension

**Rationale:**
1. Ecological validity: most Claude Code users run Sonnet
2. Anthropic's own agent research uses Sonnet variants (faithfulness papers, tau-bench evaluations)
3. Faithfulness degrades with scale (Lanham et al. 2023): Sonnet may produce MORE faithful reasoning
4. Conservation: more runs per OAuth usage allowance = better statistical power
5. If signals work on Sonnet, Opus becomes a natural Phase 2 extension testing the scale relationship

**Evidence:** Lanham et al. 2023 (arXiv:2307.13702): "For 6/8 tasks, faithfulness gets monotonically worse from 13B to 175B."

**Decided during:** CEO review, model selection discussion.

---

## Decision 5: Statistical Methodology — Anthropic-Aligned

**Choices adopted from Anthropic's published methodology:**
1. Clustered standard errors by task_id (from "A Statistical Approach to Model Evaluations")
2. pass^k reliability metric (from tau-bench, Yao et al. 2024)
3. Power analysis before Phase 0 (from same Anthropic stats paper)
4. Paired bootstrapping for within-subjects CIs
5. Structural faithfulness check (adapted from Chen et al. 2025 intervention-based faithfulness methodology)
6. Distribution shift check for Phase 0 → Phase 1 model transfer (from D'Amour et al. 2020)

**Rationale:** Using published statistical methods from the agent evaluation literature avoids known methodological objections and aligns with established best practices.

**Decided during:** CEO review, after deep reading of 17+ Anthropic publications.

---

## Decision 6: Two-Phase Calibration-First Design

**Choice:** Phase 0 (calibration study) → Phase 1 (gating experiment), with Phase 0 data informing Phase 1 design

**Rationale:** User's philosophy-of-science instinct: "I think we do need to separate these questions of calibration from intervention." Separating measurement from intervention is the epistemically clean move.

**User's exact words:** "Before going fully into the spec of B, we need to get preliminary data and understand the calibration."

**Evidence supporting this structure:**
- Kadavath et al. 2022 established calibration measurement before gating
- Anthropic's own methodology separates measurement (evals) from intervention (training)
- The CEO review's premise challenge confirmed: the calibration question must be answered before the intervention is designed

**Decided during:** Office hours, approach selection.

---

## Decision 7: Pitch Framing — Harness First, Study Second

**From:** "We studied whether LLM confidence predicts tool-call correctness"
**To:** "We built a harness that makes coding agents measurably less likely to break things, and here's the data proving it"

**Rationale:** The JD asks for "a project built on LLMs that showcases your skill at getting them to do complex tasks." UGA as a meta-study reads as analysis. UGA as a working harness reads as building. The harness IS the artifact; the study IS the evidence.

**Decided during:** CEO review, premise challenge.

---

## Decision 8: Cross-Model Comparison via Codex Behavioral (not Judgmental)

**From:** Critic prompt: "Is this tool call correct? YES/NO"
**To:** Behavioral comparison: "What tool call would YOU make next?" + compare

**Rationale:** User: "I'm averse to the critic method because it has its own subprocess with a critic prompt baked in, so it doesn't allow us coverage of controlling that unless the critic prompt is pretty anodyne and neutral."

Asking "is this correct?" primes the critic with a hypothesis. Asking "what would you do?" measures independent judgment. Disagreement between two agents making the same decision is a purer signal.

**Decided during:** CEO review, auth architecture discussion.

---

## Decision 9: No Human Annotation Loop

**Choice:** Automated feature extraction + statistical validation via Phase 0 correlation

**Rationale:** User: "Are you suggesting that I annotate? That would introduce a novel feature of systemic doubt." The features are validated by their predictive power (correlation with correctness), not by matching a human linguist's annotation. Phase 0 IS the validation.

**User's key insight:** "We want to introduce the least variability and we want to be careful."

**Decided during:** Eng review, test fixture discussion.

---

## Key Quotes to Use in Report

User on epistemic precision:
> "These premises are framed in a way that hedges commitment and obscures the true philosophical orientation of the underlying fundamental premises."

User on separating measurement from intervention:
> "I think we do need to separate these questions of calibration from intervention... my gut tells me that before going fully into the spec of B, we need to get preliminary data."

User on modal features as proxies:
> "We're just using those modals as strong signals of sentiment, which are there for carving nature at the joints, where nature here is the agent's intent."

User on simplification:
> "I don't know if we should overindex on edge cases of philosophical import, because they have bearing on the theory of meaning. Here we don't need a theory of meaning."

---

## Decision 10: Three Imports from Codex vNext (Final Revision)

**Context:** Codex adversarial review (round 2, gpt-5.3-codex) rated the design "would not hire" due to overcomplexity, unresolved validity issues, and weak experimental prioritization. Codex proposed a stripped-down vNext protocol. Independent Opus evaluation compared both designs and recommended keeping Design A with 3 surgical imports from B.

**Import 1: Hybrid labeling protocol**
Machine-label via test runner (incorrect if tests fail after tool call). Human-label only ambiguous cases (~40-60% machine-labelable). Eliminates the subjective labeling problem while keeping the experiment feasible.

**Import 2: Pre-registered numeric thresholds**
AUC-ROC ≥ 0.65, critic disagreement precision ≥ 0.60, selective risk reduction ≥ 10%, directional consistency ≥ 0.70. Replaces softer go/no-go criteria with explicit, pre-registered success criteria.

**Import 3: Deterministic feature baseline (Tier 0)**
step_index_normalized, prior_failure_streak, retry_count, tool_switch_rate. No linguistic analysis needed. If these predict correctness as well as hedging features, the linguistics add no value. This answers the "simple baselines first" critique.

**What was NOT imported:**
- 96-task requirement (infeasible for solo researcher)
- 4-week timeline (dishonest for the actual work)
- Single-question framing (too thin for a research contribution)
- Elimination of the interaction matrix (the project's core contribution)

**Evidence:** Independent Opus comparison rated Design A superior across all 5 dimensions (validity, feasibility, Anthropic alignment, novelty, hirability).

**Decided during:** Eng review, after Codex round 2 adversarial review.

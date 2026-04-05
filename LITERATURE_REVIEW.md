# Literature Review: Behavioral Signals in LLM Coding Agent Reasoning Traces

*Compiled 2026-03-29 for paper drafting. Cite these papers and differentiate clearly.*

---

## Positioning Statement

Our contribution is NOT "we analyzed SWE-bench trajectories" (that's been done). Our contribution IS:
1. Linguistic properties of reasoning traces — specifically reasoning-to-action alignment — predict success
2. Thinking blocks carry structurally different signals than agent messages (double dissociation)
3. Hyland hedging is dead for coding (contrasts with QA literature)
4. Signals degrade over trajectory position, with specific implications for gating design
5. Within-task faithfulness test showing run-level reasoning quality, not task difficulty

---

## HIGH OVERLAP — Must Cite and Differentiate

### 1. Majgaonkar et al. (2025) — Closest Paper
**"Understanding Code Agent Behaviour: An Empirical Study of Success and Failure Trajectories"**
- arXiv:2511.00197, Oct 2025
- Analyzes trajectories from OpenHands, SWE-agent, Prometheus on SWE-Bench
- Finds failed trajectories are longer with higher variance, distinct problem-solving strategies enable success
- Fault localization correct even in failures (72-81%)
- **Differentiation:** They analyze *action-level patterns* (what the agent does — file reads, edits, searches). We analyze *reasoning trace content* (what the agent says before acting). Our reasoning-to-action alignment metric bridges the reasoning-action gap, which they don't address.

### 2. Cuadron et al. (2025) — Shepherd
**"Shepherd: Pattern-Guided Trajectory Selection for Coding Agents on SWE-Bench"**
- OpenReview, submitted 2025
- 3,908 execution trajectories across 18 models
- Identifies three failure patterns: failure to interact with environment, issuing interdependent actions simultaneously, premature task completion
- Uses LLM-as-judge to select optimal trajectories, improving o1-low from 21% to 31%
- **Differentiation:** Uses LLM-as-judge (learned discriminator), not hand-crafted interpretable behavioral features. Our features are lightweight, interpretable, and could serve as inputs to a system like Shepherd's.

### 3. Bouzenia & Pradel (2025) — Thought-Action-Result Analysis
**"Understanding Software Engineering Agents: A Study of Thought-Action-Result Trajectories"**
- ASE 2025 (arXiv:2506.18824), Jun 2025
- 120 trajectories, 2,822 LLM interactions from RepairAgent, AutoCodeRover, OpenHands
- Identifies behavioral motifs and anti-patterns distinguishing success/failure
- Focuses on semantic coherence of thoughts-actions-results
- **Differentiation:** Studies program repair broadly (not exclusively SWE-bench). Focuses on semantic coherence rather than specific lexical/structural features like file-name alignment. Our "first_edit_position" may overlap with their premature-actions anti-pattern, but the operationalization is different.

### 4. Zhang et al. (2026) — Agentic Confidence Calibration (HTC)
**"Agentic Confidence Calibration"**
- arXiv:2601.15778, Jan 2026
- Holistic Trajectory Calibration: extracts process-level features from macro dynamics to micro stability
- Interpretable model for trajectory-level calibration across 8 benchmarks
- Cross-domain transferability
- **Differentiation:** HTC uses process-level features (trajectory length, action diversity, token distribution) but does NOT analyze reasoning text content. We add the linguistic dimension — analyzing what the agent *says* in its reasoning, not just what it *does*. HTC also doesn't distinguish thinking vs. message layers.

---

## MEDIUM OVERLAP — Should Cite

### 5. Vanhoyweghen et al. (2025) — Lexical Hints (Important Contrast)
**"Lexical Hints of Accuracy in LLM Reasoning Chains"**
- arXiv:2508.15842, Aug 2025
- Analyzes CoT for length, sentiment volatility, and Hyland-style hedging words
- Finds lexical markers of uncertainty ("guess," "stuck," "hard") are strongest indicators of incorrect responses in QA
- CoT length informative only on moderate-difficulty benchmarks
- **Key contrast:** They find hedging works for QA. We find Hyland hedging is completely non-predictive for coding tasks (ρ ≈ 0). This inverse result is publishable on its own. Their CoT length finding partially overlaps with our deliberation_length, but ours is per-call in an agentic multi-turn setting rather than single-pass QA.

### 6. Zhang et al. (2026) — Agentic Uncertainty Quantification (AUQ)
**"Agentic Uncertainty Quantification"**
- arXiv:2601.15703, Jan 2026 (same lead author as HTC)
- Dual-Process Agentic UQ: transforms verbalized uncertainty into active control signals
- System 1: Uncertainty-Aware Memory; System 2: Uncertainty-Aware Reflection
- **Differentiation:** AUQ *uses* verbalized uncertainty as input. We *evaluate whether* verbalized uncertainty signals are predictive. Different angle, same general space.

### 7. Arcuschin et al. (2025) — CoT Faithfulness
**"Chain-of-thought Reasoning in the Wild is Not Always Faithful"**
- arXiv:2503.08679, Mar 2025 (127 citations)
- Finds CoT not always faithful to internal reasoning, especially in extended thinking
- Tests with Claude 3.7 Sonnet
- **Relevance:** Supports the premise of our "double dissociation" finding — thinking and output layers may carry different information. We provide empirical evidence for this in the coding domain.

### 8. Bachmann et al. (2026) — CoT Potential
**"The Potential of CoT for Reasoning: A Closer Look at Trace Dynamics"**
- arXiv:2602.14903, Feb 2026
- Introduces "potential" — quantifying how much a given part of CoT increases likelihood of correct completion
- Finds non-monotonicity, sharp spikes (reasoning insights)
- **Relevance:** Related to our trajectory position degradation finding (early/mid predictive, late not), but operationalized differently and focused on mathematical reasoning.

### 9. Xuan et al. (2026) — Confidence Dichotomy in Tool-Use Agents
**"The Confidence Dichotomy: Analyzing and Mitigating Miscalibration in Tool-Use Agents"**
- arXiv, Jan 2026
- Studies miscalibration in tool-use agents
- **Relevance:** Our Hyland null result provides complementary evidence about what signals DON'T work for calibration in coding contexts.

---

## LOW OVERLAP — Cite If Space Permits

### 10. Martinez & Franch (2025)
**"Dissecting the SWE-bench Leaderboards: Profiling Submitters and Architectures"**
- arXiv:2506.17208, Jun 2025 (27 citations)
- Taxonomy of SWE-bench approaches. Notes most systems don't exhibit agentic behavior.

### 11. Shojaee et al. (2025)
**"The Illusion of Thinking: Understanding Strengths and Limitations of Reasoning Models"**
- NeurIPS 2025 (arXiv:2506.06941), 468 citations
- Shows accuracy collapse beyond certain complexities in reasoning models
- Tangentially relevant to our deliberation finding

### 12. Srikumar et al. (2025) — Agent Safety Policy Paper
**"Prioritizing Real-Time Failure Detection in AI Agents"**
- Partnership on AI, Sep 2025
- Argues for real-time failure detection. Our work provides the kind of empirical behavioral signals this paper calls for.

### 13. Bai et al. (2025) — Token Consumption
**"How Do Coding Agents Spend Your Money? Analyzing and Predicting Token Consumptions"**
- OpenReview, 2025
- Empirical analysis of agent token consumption. Tangentially related to our task-length confound finding.

---

## What Is Genuinely Novel (Our Contributions)

| Finding | Precedent | Novel? |
|---------|-----------|--------|
| Reasoning-to-action alignment metric | No precedent found | **YES — new metric** |
| Thinking vs. message double dissociation | CoT faithfulness paper supports premise but doesn't demonstrate it | **YES — new empirical finding** |
| Hyland hedging dead for coding | Vanhoyweghen finds it works for QA — our null is the contrast | **YES — novel negative result** |
| Trajectory position degradation with gating implications | Bachmann has related "potential" concept but different domain/operationalization | **Partially novel** |
| Within-task faithfulness permutation test | No direct precedent for this methodology in agent behavioral analysis | **YES — novel methodology** |
| Deliberation length per-call predicts success | Vanhoyweghen has CoT length for QA; ours is per-call agentic | **Incremental** |
| First edit position predicts success | Bouzenia has "premature actions" anti-pattern | **Incremental** |
| Failing tasks have longer trajectories | Well established (Majgaonkar et al.) | **NOT novel** |

---

## Recommended Paper Framing

**Title candidates:**
- "Behavioral Signals in Coding Agent Reasoning Traces Predict Task Success"
- "Reasoning-to-Action Alignment: What LLM Agents Say Before They Edit Predicts Whether They'll Succeed"
- "When Agents Name Their Target: Behavioral Predictors of Coding Agent Success on SWE-bench"

**Framing:** Position as the first study to analyze *linguistic content of reasoning traces* (not just action patterns or trajectory structure) for predicting coding agent success. Emphasize the interpretable, lightweight nature of the features versus LLM-as-judge approaches.

**Key differentiators to emphasize in the intro/related work:**
1. Prior work analyzes what agents DO (action patterns). We analyze what agents SAY (reasoning content).
2. Prior work on lexical signals focuses on QA. We show the signal structure is fundamentally different for coding.
3. We provide the first empirical evidence of structural information differences between thinking blocks and agent messages in coding.
4. Our features are cheap to compute (regex + string matching), not requiring another LLM call.

---

## Venue Deadlines

| Venue | Deadline | Conference | Location | Fit |
|-------|----------|------------|----------|-----|
| COLM 2026 | Mar 31 full paper | Oct 6-9 | San Francisco | Perfect topic fit but 2 days away |
| NeurIPS 2026 | May 4 abstract / May 6 paper | Dec 2026 | TBD | Strong fit, realistic timeline |
| EMNLP 2026 | May 25 via ARR | Oct 24-29 | Budapest | Good fit, most time |
| ICML 2026 workshops | ~May TBD | Jul 10-11 | Seoul | Workshop papers, lower bar |
| NeurIPS 2026 workshops | ~Sep TBD | Dec 2026 | TBD | Workshop papers if main rejected |
| AAAI-27 | ~Aug 2026 | Jan 2027 | TBD | Backup with Phase 1 results |

**Recommendation:** ArXiv preprint this week. NeurIPS May 4 as primary target. EMNLP May 25 as fallback.

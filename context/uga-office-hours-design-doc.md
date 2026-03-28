# UGA Office-Hours Design Doc

Generated on 2026-03-28
Mode: Open source / research (Builder)
Audience optimization: Research scientist reviewer (Anthropic RE, Agents)

## Problem Statement
UGA should demonstrate that selective-prediction style abstention can be operationalized at **agent tool-call decision points** with measurable calibration quality and useful reliability tradeoffs. The artifact must show rigorous methodology, reproducible instrumentation, and honest limits.

## Headline Claim
**Primary claim:** UGA demonstrates calibrated abstention for tool calls.

Why this claim:
- It is more defensible than catastrophic-failure headline claims at pilot scale.
- It is methodologically meaningful: selective prediction adapted from answer-level to action-level decisions.
- It preserves novelty without pretending UGA invented abstention itself.

## Scope Lock (from answers)
1. Task realism: **Hybrid 8 synthetic + 7 real issue traces**.
2. Labeling: no second labeler now; use **blinded self-consistency dual-pass** with 48h gap and report intra-rater kappa.
3. Confidence elicitation: add **few-shot P(True)** arm from day 1.
4. Baseline: add **critic-disagreement gate** baseline.
5. Decision points: tool calls only; **defer pre-final-answer gating to Phase 2**.
6. Evaluation strictness: **confidence-interval-aware criteria**, not brittle threshold theater.
7. Time priority: fewer runs, deeper trace taxonomy and analysis.
8. Release surface: **harness + anonymized traces + memo**.

## Experiment Design (Revised)

### Conditions
1. `ungated` (baseline)
2. `self-confidence-gate-zero-shot` (existing baseline gating)
3. `self-confidence-gate-ptrue-fewshot` (new primary arm)
4. `critic-disagreement-gate` (new comparator baseline)

### Tasks
- Total pilot registry remains 15 tasks.
- Split: 8 synthetic calibration anchors + 7 real issue-style tasks.
- Real tasks must be from repositories with known issue context and deterministic validation harness.

### Unit of Decision
- Decision points = state-modifying or high-cost tool calls only (`Write`, `Edit`, side-effect `Bash`, commit-like operations).
- `Read`/`Search` remain ungated.
- Final-answer gating deferred.

## Measurement Contract

### Primary outcomes
1. Calibration quality of abstention signal at tool-call level.
2. Selective risk-coverage behavior under each gating arm.
3. Per-task consistency of directional effects with uncertainty bounds.

### Supporting outcomes
- Catastrophic/severe/recoverable failure decomposition.
- Repair-loop depth and cascade behavior.
- Overhead decomposition (decision latency, extra tool calls, escalation cost, tokens).

### Statistical posture
- Report effect sizes with bootstrap confidence intervals.
- Use directional consistency and uncertainty bounds for go/no-go.
- Explicitly avoid overclaiming significance at small n.

## Labeling and Annotation Protocol
- Two-pass blinded self-labeling with at least 48-hour separation.
- Compute intra-rater agreement (kappa) on failure class and tool-call correctness labels.
- If kappa < 0.60, treat labeling reliability as a core limitation, not footnote.
- Produce 3 deeply annotated trace case studies:
  1. Uplift case (gated prevents likely bad action)
  2. False abstention case
  3. Critic disagreement case (agreement/disagreement behavior and consequences)

## Novelty Positioning
UGA novelty is **operational**, not foundational:
- Known: reject-option/selective prediction theory.
- New in artifact: calibrated abstention mechanism embedded in agent tool-call loop with trace-level reliability instrumentation and controlled baselines.
- Anti-overclaim line: "UGA extends operational evaluation of selective abstention for agent actions; it does not claim a new abstention theory."

## Open-Source Artifact Plan
Ship:
1. Harness code and schemas
2. Task registry format (with synthetic + real split metadata)
3. Anonymized trace bundle
4. Reproducible analysis scripts
5. Pilot memo with figures + limitations

Do not ship:
- Raw sensitive paths or workspace-identifying metadata
- Non-anonymized logs with local environmental leakage

## Go / No-Go Criteria (CI-aware)
Green-light to expansion (`n=50`) if:
1. Calibration signal is directionally useful with acceptable uncertainty in P(True) arm.
2. At least one gating arm shows improved risk-coverage tradeoff vs ungated.
3. Overhead remains bounded enough to preserve practical throughput envelope.
4. Failure taxonomy evidence indicates useful intervention behavior (not just abstain-everything behavior).

Yellow-light revision if:
- Signal exists but uncertainty too wide; revise elicitation/threshold policy and rerun targeted slice.

Red-light pivot if:
- No calibration signal and no usable risk-coverage advantage across both self-confidence and critic baselines.

## Execution Sequence (7 days)
1. Freeze revised protocol + claim charter.
2. Finalize hybrid tasks and validation harness.
3. Implement added arms (P(True), critic-disagreement).
4. Dry-run for logging correctness and anonymization check.
5. Execute pilot runs with tighter count and deeper trace review.
6. Label, compute agreement, produce CI-aware analysis.
7. Publish memo + artifact package.

## Key Risks and Mitigations
1. Real-task variance overwhelms signal.
   - Mitigation: stratify synthetic vs real in analysis and report separately + pooled.
2. Label reliability weak without second annotator.
   - Mitigation: explicit self-consistency protocol and transparent limitation reporting.
3. Critic baseline dominates and erodes UGA contribution.
   - Mitigation: frame as meaningful negative result or redefine contribution around decision instrumentation quality.
4. Overhead inflation from additional arms.
   - Mitigation: cap run count and prioritize trace quality over volume.

## Deliverables
- `ops/uga-pilot-protocol-v3.md` (protocol freeze)
- `ops/uga-pilot-memo.md` (main result doc)
- `ops/uga-anonymization-spec.md` (trace release rules)
- Anonymized result bundle under harness `data/results/` export path

## Final Recommendation
Proceed with a **credibility-first, scope-disciplined pilot** optimized for research-method rigor: hybrid tasks, P(True) arm, critic-disagreement baseline, CI-aware claims, and deep failure taxonomy analysis.

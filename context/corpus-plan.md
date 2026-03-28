# Corpus Plan for UGA / Readiness-Gated Tool Use

## Scope Guardrails (What This Corpus Is Not)
- Not a general agent-memory brain.
- Not a broad survey of all agent papers.
- Not optimized for corpus size.
- Not centered on vendor-specific orchestration tooling (including Vertex implementation details).

## A. Research Questions the Corpus Must Answer
1. Does readiness gating reduce severe/catastrophic failures, or only shift where failures occur?
2. Which uncertainty signals are actually calibratable at decision time for tool-use actions?
3. What abstention/selective-prediction formulations best map to tool-call go/no-go choices?
4. How should we measure reliability on long-horizon tasks without proxy-metric self-deception?
5. What benchmark design choices most strongly prevent confounds (task leakage, evaluator leakage, instrumentation artifacts)?
6. What are canonical failure taxonomies we can adapt for agent traces (not invent from scratch)?
7. How do coordination and handoff failures manifest in multi-agent settings, and which are gate-addressable vs non-gate problems?
8. What is genuinely novel in UGA relative to known calibration/abstention/control literature?
9. What are likely anti-patterns that produce impressive but invalid benchmark gains?
10. What minimum evidence would make a pilot credible to Anthropic reviewers?

## B. Corpus Buckets

### Bucket 1: Agent evals and long-horizon task performance
Focus: SWE-bench/WebArena/OSWorld/GAIA style environments, runtime trace quality, failure observability.

### Bucket 2: Calibration, abstention, selective prediction, uncertainty
Focus: calibration metrics (ECE/Brier/NLL), reject option, conformal prediction, learning-to-defer.

### Bucket 3: Benchmark design, measurement validity, causal/confound discipline
Focus: internal validity, leakage/contamination, underspecification, robust comparisons.

### Bucket 4: Failure analysis, error taxonomies, reliability engineering
Focus: incident taxonomy, latent conditions, repair-loop framing, resilient operations.

### Bucket 5: Tool use, action gating, decision-time control
Focus: explicit action selection/control, tool-use policy decisions, thresholded intervention points.

### Bucket 6: Multi-agent coordination, communication, handoff failures
Focus: joint intentions/shared plans, delegation breakpoints, stale context handoffs.

### Bucket 7: Software engineering / human-factors analogs
Focus: SRE, human-automation teaming, high-reliability systems lessons directly reusable.

### Bucket 8: Negative evidence / critiques / benchmark pathologies
Focus: overclaiming, benchmark gaming, contamination, weak-proxy pitfalls.

## C. Target Corpus Shape (First Pass)

### Size target
- Ideal first-pass size: 45-60 sources total.
- Hard cap before pilot design lock: 70.
- Preferred operating set for active synthesis: top 25 sources only.

### Ratio target (first pass)
- Surveys/tutorials: 15%
- Canonical foundational: 30%
- Recent empirical (2019+): 35%
- Methods/statistical design references: 15%
- Analog (SRE/human factors/distributed coordination): 5%

### Recentness importance by bucket
- Bucket 1 (agent evals): very high (2023+ dominates usefulness)
- Bucket 2 (calibration/abstention): mixed (classics remain central; recent LLM-specific updates required)
- Bucket 3 (measurement validity): low-to-mixed (many canonical methods older but still authoritative)
- Bucket 4 (failure analysis): mixed (classics + modern AI-specific incidents)
- Bucket 5 (tool use/gating): high (2022+ needed)
- Bucket 6 (multi-agent coordination): mixed (classic theory + recent LLM implementations)
- Bucket 7 (SE/human factors): low (older canonical work still highly useful)
- Bucket 8 (critiques/pathologies): high (recent benchmark-specific critiques matter)

## D. Note-Taking Schema (Design-Oriented)
Use one note per source, max ~250 words plus structured fields.

```yaml
source_id: short-id
citation: full citation
bucket_primary: B1..B8
bucket_secondary: optional
source_type: survey|benchmark|empirical|theory|textbook|critique

core_claim: |
  One-sentence claim in plain language.

most_reusable_method_or_concept: |
  Exact artifact/method we can transplant.

suggested_metric_or_design_choice: |
  Concrete benchmark/metric implication for UGA pilot.

strongest_caution_or_limitation: |
  The main reason this source could mislead us.

project_mapping: |
  Which UGA component this informs (framing, gate policy, labels,
  benchmark protocol, analysis plan, or failure taxonomy).

decision_impact:
  changes_framing: yes|no
  changes_benchmark: yes|no
  changes_metric: yes|no
  changes_intervention_design: yes|no

evidence_strength: high|medium|low
relevance_score: 1-5
novelty_delta_for_uga: known|incremental|meaningful

not_to_overgeneralize: |
  What should NOT be inferred from this source.
```

## What Not To Do During Corpus Build
- Do not ingest broad "agent future" essays without reusable methods.
- Do not treat leaderboard movement as evidence of reliability gains.
- Do not mix benchmark construction and intervention tuning on the same tasks without split discipline.
- Do not overweight shiny 2024-2026 agent demos over measurement literature.
- Do not add sources that only repeat ReAct/Toolformer narratives unless they add methodology.

## Likely Rabbit Holes
- Endless agent-framework comparisons with no measurement contribution.
- Prompt-engineering tricks that improve demo success but not calibrated control.
- Overly abstract alignment arguments that never map to measurable gate behavior.
- Long-context model benchmarks that do not include decision-time abstention/control.
- Retrieval-system architecture debates before corpus utility is proven.


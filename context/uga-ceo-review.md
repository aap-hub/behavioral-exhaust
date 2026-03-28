# UGA CEO Review (HOLD SCOPE)

Date: 2026-03-28
Mode: HOLD SCOPE (maximum rigor, no scope expansion)
Plan inputs reviewed:
- `ops/final-project-recommendation.md`
- `ops/uga-pilot-spec-v2.md`
- `ops/uga-pilot-tasks.md`
- `ops/uga-benchmark-harness-spec.md`
- `ops/lit/corpus-plan.md`
- `ops/lit/open-questions-from-literature.md`
- `ops/office-hours-answers.md`
- `ops/uga-office-hours-design-doc.md`

## Executive Verdict
The plan is strategically strong and now directionally correct after answer-driven scope refinements. The remaining risk is execution credibility, not concept quality.

Decision: **Proceed under HOLD SCOPE with mandatory protocol hardening before full runs.**

If hardening is skipped, likely reviewer outcome: "smart idea, weak evidence hygiene."

## Step 0A: Premise Challenge
1. Is this the right problem?
- Yes. Tool-call false certainty is a tractable, high-consequence failure locus with measurable logs.

2. Is this solving outcome or proxy?
- Mostly outcome. Risk remains that optimizing calibration proxies could detach from practical reliability if taxonomy quality is weak.

3. What if we do nothing?
- You still ship a benchmark harness, but without the calibrated-abstention thesis differentiator. Application artifact becomes less research-distinct.

## Step 0B: Existing Code Leverage
Reuses already in place:
- Existing UGA harness scaffold and schema definitions
- Existing task registry and pilot memo structure
- Existing instrumentation-focused framing docs

Rebuild risk:
- Parallel logic paths for multiple arms can duplicate interception/logging behavior; enforce shared middleware core with strategy plug-ins.

## Step 0C: 12-Month Trajectory

```
CURRENT STATE                     THIS PLAN DELTA                         12-MONTH IDEAL
Spec-complete pilot concept  -->  Credible pilot with calibrated         --> Domain-general action governance
with baseline+gating idea         abstention evidence + trace taxonomy      (coding/web/computer use) with
                                  + comparator baselines                    robust transfer and adaptive policy
```

Assessment: Current plan moves toward ideal if and only if label reliability and baseline interpretation are handled rigorously.

## Step 0C-bis: Implementation Alternatives (within fixed scope)

APPROACH A: Minimal Execution of Revised Plan
- Summary: Implement exactly the four-arm setup and run once per task.
- Effort: M
- Risk: Med
- Pros: Fast completion.
- Cons: Fragile against confounds and reproducibility criticism.
- Reuses: All existing artifacts.

APPROACH B: Protocol-First HOLD SCOPE (Recommended)
- Summary: Freeze protocol, anonymization, and label handbook first; run fewer but cleaner traces.
- Effort: M
- Risk: Low-Med
- Pros: Highest credibility per run; best reviewer trust.
- Cons: Slightly slower start.
- Reuses: Existing harness + office-hours decisions.

APPROACH C: Analysis-Heavy Bias
- Summary: Run early, then backfill protocol details in memo.
- Effort: S/M
- Risk: High
- Pros: Quick data collection.
- Cons: High chance of post-hoc method criticism.
- Reuses: Existing run scripts.

Recommendation: **B**.

## Step 0D (HOLD SCOPE): Complexity Check
- Plan now spans protocol, harness logic, task realism, annotation, and memo quality.
- Complexity is justified, but execution should be constrained by a strict readiness checklist before bulk runs.

Minimum change-set that still achieves goal:
1. Protocol freeze with revised conditions
2. Hybrid task manifest and validation hooks
3. Gate strategy abstraction for 3 gating arms + ungated
4. Annotation handbook + dual-pass process
5. CI-aware analysis scripts and memo templates

## Step 0E: Temporal Interrogation
- Hour 1 (human) / ~5 min (CC): Freeze exact claim language and anti-overclaim rules.
- Hour 2-3 / ~15 min: Implement gating-arm parity so all arms emit identical log fields.
- Hour 4-5 / ~20 min: Run dry-runs; most surprises likely in confidence extraction and critic timeout behavior.
- Hour 6+ / ~20 min: Build taxonomy annotations and produce curated traces; this is where artifact quality is won or lost.

## Critical Findings (ordered by severity)

### 1) Primary claim and current success thresholds are misaligned
- Current spec still anchors heavily on catastrophic-failure percentage thresholds.
- Your chosen headline is calibrated abstention, so pilot success criteria must center on calibration and risk-coverage first.
- Required action: reprioritize metric hierarchy in protocol freeze.

### 2) Multi-arm comparison validity is under-specified
- Adding `P(True)` and critic-disagreement baselines creates arm-specific failure modes (latency, refusal, critic instability).
- Without parity controls, arm deltas are not interpretable.
- Required action: define identical logging, timeout, and fallback policies across arms.

### 3) Label reliability risk remains high without second rater
- Dual-pass self-consistency is acceptable fallback, but only if blind conditions and drift checks are explicit.
- Required action: predefine blind procedure, randomization, and adjudication rule.

### 4) Hybrid task governance lacks anti-leakage protocol
- Real issue traces can leak known fixes into prompts/context.
- Required action: define snapshot timing, context redaction, and issue metadata constraints.

### 5) Anonymization is not yet an enforceable contract
- "Anonymized traces" is currently a goal, not a checked pipeline.
- Required action: automated redaction + validation tests before release bundle generation.

## Architecture Review

### System dependency graph (target state)
```
Task Registry (8 synthetic + 7 real)
        |
        v
Run Orchestrator -----> Workspace Snapshot Manager
        |
        v
Gate Strategy Layer (ungated | zero-shot | P(True) | critic-disagreement)
        |
        v
Tool Interceptor -> Decision Logger -> Outcome Collector -> Analysis Pipeline -> Memo
                              |
                              v
                      Anonymization Pipeline -> OSS Bundle
```

### Data-flow four-path check (decision evaluation)
```
HAPPY:  decision -> confidence/disagreement -> gate outcome -> tool execution -> logged
NIL:    missing confidence/disagreement -> policy fallback -> logged as null_reason
EMPTY:  empty model response -> retry policy -> if fail block/escalate -> logged
ERROR:  model/tool timeout -> bounded retries -> explicit abort state -> logged
```

### Scaling breakpoints (10x / 100x)
- 10x: labeling bandwidth and trace review become bottleneck.
- 100x: storage + log processing and annotation consistency collapse without automation.

## Error & Rescue Map (required)

| Codepath | Failure mode | Exception class | Rescue action | User-visible effect |
|---|---|---|---|---|
| Confidence extraction | malformed numeric output | `ConfidenceParseError` | retry parse; else `confidence=null` + policy fallback | run continues with tagged uncertainty |
| P(True) elicitation | refusal/empty response | `ConfidenceRefusalError` | one retry with reduced prompt; else abstain/escalate | explicit abstain reason in trace |
| Critic baseline call | critic timeout | `CriticTimeoutError` | bounded retry; else `critic_unavailable` state | baseline run still completes, flagged |
| Gate decision | invalid threshold config | `GateConfigError` | fail-fast before run start | run not started; config error |
| Tool execution | side-effect command failure | `ToolExecutionError` | stop + repair step capture | failure trace preserved |
| Logging | schema mismatch | `SchemaValidationError` | fail run and dump raw event buffer | no silent data loss |
| Anonymization | leaked sensitive token/path | `RedactionValidationError` | block export artifact | release bundle not produced |
| Analysis | bootstrap failure due sparse data | `BootstrapComputationError` | fallback robust CI method + warning | CI section marked limited |

Non-negotiable: no catch-all silent rescue; every error must map to explicit trace state.

## Failure Taxonomy Requirements
Use a strict class tree:
1. Uncertainty failure (wrong confidence/disagreement signal)
2. Capability failure (model cannot perform subtask)
3. Coordination failure (critic/actor interaction failure)
4. Spec/task failure (ambiguous or invalid task design)
5. Infrastructure failure (timeouts, tooling, logging, environment)

Every severe/catastrophic event must include exactly one primary class and optional secondary tags.

## Test Strategy Review
Minimum test matrix required before full run:
1. Gate strategy parity tests across all four conditions.
2. Confidence parser robustness tests (numeric ranges, malformed text, refusal).
3. Critic baseline timeout and disagreement-path tests.
4. Schema contract tests for every event type.
5. Redaction tests (path, username, host, token patterns).
6. End-to-end deterministic smoke run on 1 synthetic + 1 real task.

## Observability and Evidence Quality
Required runtime metrics:
- Per-arm: coverage, selective risk, abstention rate, escalation rate, latency overhead, token overhead.
- Per-task: decision count, blocked count, false abstention count, repair depth.
- Reliability: confidence/disagreement extraction failure rates.
- Data quality: missing-field counts, schema validation failure counts.

Mandatory artifacts for memo:
- Risk-coverage curve per arm
- Calibration plot per self-confidence arm
- Disagreement-outcome matrix for critic baseline
- Three annotated traces (uplift, false abstention, critic edge case)

## Security and Release Review
- Sensitive trace leakage is the key release risk.
- Add deterministic redaction pass + validation assertions before writing publishable files.
- Release should include anonymization methodology and known residual leakage risks.

## Deployment / Rollback Posture
Even for research harness, treat as deployable system:
- Feature flags for enabling each arm
- Fast rollback path to two-arm run (ungated + P(True)) if critic baseline unstable
- Versioned protocol hash embedded in every run metadata record

## HOLD SCOPE Decision Log
In scope:
- Hybrid dataset, P(True) arm, critic baseline, CI-aware evaluation, deeper taxonomy, anonymized release.

Out of scope (explicitly deferred):
- Final-answer gating
- Cross-domain transfer expansion
- Adaptive threshold learning

## 7-Day Execution Gates (must-pass)

### Gate 1: Protocol Freeze (Day 1)
Pass criteria:
- Metric hierarchy updated to match headline claim
- Arm parity policy documented
- Anti-overclaim language fixed

### Gate 2: Instrumentation Reliability (Day 2)
Pass criteria:
- All arms emit schema-valid logs
- Confidence/critic extraction failure rates measurable

### Gate 3: Label Process Validity (Day 3)
Pass criteria:
- Dual-pass protocol executed on sample traces
- Intra-rater agreement reported with limitation statement

### Gate 4: Analysis Integrity (Day 5)
Pass criteria:
- CI-aware analysis pipeline runs end-to-end
- Required plots/tables generated from anonymized outputs

### Gate 5: Release Safety (Day 7)
Pass criteria:
- Redaction validation passes
- OSS bundle reproducible from documented steps

## Final CEO Recommendation
Proceed now, but run the project as a **methodology artifact first, benchmark second**. Your upside comes from being the candidate who demonstrates disciplined experimental judgment under constrained data, not from oversized claims.

If forced to choose between one more run and one more deeply annotated failure trace, choose the trace.

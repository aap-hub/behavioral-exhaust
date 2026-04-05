# UGA Pilot Spec — Literature-Grounded Version

**Status:** Literature validation complete — fixes applied, ready for Day 1
**Owner:** Adwait (candidate)

**Pilot Duration:** 7 days

---

## 1. Exact Flagship Framing

### One-Paragraph Project Description
Uncertainty-Gated Autonomy (UGA) is a harness intervention where autonomous agents must pass calibrated readiness gates before executing high-cost or irreversible actions. The core claim is that forcing explicit confidence assessment at decision points reduces catastrophic failures and repair-loop depth without unacceptable overhead. This project builds a benchmark, implements the gating mechanism, and measures whether calibrated stop/go control improves long-horizon agent reliability. UGA applies selective prediction formalism to agent action decisions, drawing from a lineage of reject-option work in classification.

### One-Sentence Thesis
Calibrated readiness gates reduce catastrophic failure rate by ≥25% and repair-loop depth by ≥20% while keeping overhead ≤15%.

### Why UGA Is the Lead Framing
- Targets the highest-cost failure mode in long-horizon autonomy: acting under false certainty
- Produces a mechanism-level contribution (stop/go control law), not just an empirical observation
- Directly maps to Anthropic's "effective agents over longer time horizons" mandate
- Authentic to candidate's real governance intervention experience
- Legible to reviewers: one mechanism, one failure mode, measurable outcome
- Situated within selective prediction literature (Chow 1970, Geifman 2017, SelectiveNet 2019)

### How Readiness-Gated Tool Use Fits Inside UGA
Tool invocation is the **first decision-point class** we instrument and test. It's a clean, high-frequency, high-cost subclass of irreversible actions where:
- The intervention (gate before tool call) is mechanically simple
- Precision/recall metrics are unambiguous
- Downstream task impact is directly measurable
- Results from tool gating provide early signal for broader UGA viability without requiring full long-horizon harness

Tool gating is **evidence slice #1** that validates whether the gating mechanism works before expanding to other decision-point classes (file mutations, external API calls, commit decisions).

---

## 2. Prerequisite Hypothesis: Confidence Signal Validity

### Hypothesis H0 (Prerequisite)
Agent-reported confidence scores have non-trivial rank correlation with tool-call correctness (Spearman ρ > 0.2).

### Rationale
Modern neural networks are poorly calibrated (Guo et al. 2017). Prior work has studied LLM confidence for QA correctness—Jiang et al. (2021) found smaller models are poorly calibrated on QA tasks, while Kadavath et al. (2022) showed larger models can distinguish correct from incorrect answers when using their P(True) method with few-shot examples. However, **confidence for agentic tool-call correctness has not been directly studied.** Tool calls differ from QA in action space complexity, parameter verification requirements, and environmental context dependence. Before proceeding with gating, we must establish that confidence scores have predictive value for this specific decision class.

### Measurement Approach
- Collect confidence scores and corresponding tool call outcomes
- Compute Spearman rank correlation between confidence and binary success indicator
- If ρ ≤ 0.2, pilot stops with negative result report
- If ρ > 0.2, proceed with full gating evaluation

This transforms the core question from "Given calibrated confidence, does gating help?" to "Can we elicit useful confidence signal?" 

---

## 3. Exact 7-Day Pilot Design

### Benchmark Scope
- **Domain:** Coding tasks with irreversible file modifications
- **Task source:** Existing candidate corpus (real tasks from multi-agent work)
- **Task type:** Bug fix + feature implementation + refactoring (each requires file edits)

### Number of Tasks
- **Total:** 15 tasks
- **Distribution:** 5 bug fixes, 5 feature implementations, 5 refactors
- **Selection criteria:**
  - Each task requires ≥1 file edit
  - Ground-truth correct solution is known
  - Task can be completed in ≤10 minutes by a capable agent
- **Additional requirement for pilot:** At least 2 tasks specifically designed to test gate failure modes (CheckList-inspired)

### Baseline Condition
- **Name:** `ungated`
- **Behavior:** Agent proceeds with all tool calls without any readiness check
- **Model:** GPT-5.2 (consistent across all conditions)
- **Prompt:** Standard task prompt, no gate instruction

### Gated Condition
- **Name:** `static-gate-0.7`
- **Behavior:** Before each tool call, agent must output confidence score (0-1). If score < 0.7, tool call is blocked and agent must either: (a) gather more information, (b) request help, or (c) abort task.
- **Confidence elicitation:** "Before calling any tool, output your confidence (0-1) that this tool call is necessary and correctly parameterized. If confidence < 0.7, do not proceed."
- **Elicitation design note:** This uses zero-shot verbalized confidence—the weakest viable elicitation method. Kadavath et al. (2022) shows that few-shot P(True) evaluation significantly improves calibration over zero-shot prompting. We deliberately start with the weakest intervention to establish a lower bound: if even naive confidence produces useful signal, the mechanism is viable and stronger elicitation methods (few-shot P(True), temperature scaling per Guo 2017) become natural extensions.
- **Threshold design note:** SelectiveNet (Geifman et al. 2019) demonstrates that end-to-end trained rejection outperforms post-hoc static thresholding. Our pilot uses post-hoc static thresholds for simplicity and interpretability. If directional signal is positive, end-to-end calibration training is a natural extension.
- **Model:** GPT-5.2 (same as baseline)
- **Prompt:** Same as baseline + gate instruction

### Optional Ablation
- **Name:** `static-gate-0.5` (lower threshold)
- **Only run if:** Day 3 checkpoint shows 0.7 threshold is too aggressive (>50% false abstention)
- **Purpose:** Determine if threshold is the problem vs gating mechanism itself

### What Counts as a Decision Point
A **decision point** is any moment where the agent is about to:
1. Call a tool that modifies state (file write, shell command, API POST)
2. Call a tool that is costly to reverse (git commit, database write)
3. Make a final answer submission

For this pilot, **decision points = tool calls** (specifically: Write, Edit, Bash, commit operations).

### What Counts as a High-Cost / High-Risk Action
- **High-cost:** Any action requiring ≥30 seconds to reverse or retry
- **High-risk:** Any action that, if wrong, causes task failure or requires ≥3 repair steps
- **Operationalized for pilot:**
  - File Write/Edit on non-test files = high-risk
  - Bash commands with side effects (install, delete, git push) = high-risk
  - File Read, Search = low-risk (no gating)

---

## 4. Metric and Label Contract

### Primary Outcomes
1. **Task Success**
   - **Definition:** Final agent output matches ground-truth solution AND no catastrophic failures occurred
   - **Values:** `success` | `failure` | `partial`
   - **Labeling:** Automated test suite + manual review for edge cases

2. **Catastrophic Failure Rate**
   - **Definition:** Fraction of runs with unrecoverable failures
   - **Labeling:** Manual review
   - **Threshold for "unrecoverable":** Would require human intervention to restore working state

3. **Repair-Loop Depth**
   - **Definition:** Mean number of consecutive tool calls made to fix problems caused by the previous tool call
   - **Measurement:** Count of repair-attempt tool calls before returning to productive work
   - **Repair-attempt detection:** Rule-based definition (see below)

4. **Completion Rate**
   - **Definition:** Fraction of tasks that reach successful conclusion (not aborted)
   - **Values:** Float 0-1

5. **Abstention Rate**
   - **Definition:** Fraction of tool calls that were blocked by the gate
   - **Values:** Float 0-1

6. **Escalation Rate**
   - **Definition:** Fraction of runs where agent requested help or aborted task
   - **Values:** Float 0-1

7. **Effective Throughput**
   - **Definition:** (successful completions) / (total time including abstentions and escalations)
   - **Units:** Tasks per hour

### Secondary Outcomes
8. **Severe Failure**
   - **Definition:** Agent action causes significant setback requiring ≥3 repair steps or ≥5 minutes to recover
   - **Labeling:** Manual review + repair step count

9. **Recoverable Failure**
   - **Definition:** Agent action causes minor setback requiring 1-2 repair steps or <2 minutes to recover
   - **Labeling:** Automatic from repair-loop depth

10. **Tool Misuse**
    - **Definition:** Tool call that was unnecessary OR incorrectly parameterized AND caused negative downstream impact
    - **Subtypes:** `unnecessary`, `wrong-params`, `wrong-tool`
    - **Labeling:** Manual review of each tool call + outcome

11. **False Abstention / Over-Caution**
    - **Definition:** Gate blocks a tool call that would have been correct
    - **Primary measure:** Manual review of blocked calls by labelers
    - **Supplementary measure:** Compare blocked tool calls against shadow ungated trace
    - **Labeling:** Primary + cross-condition analysis

12. **Overhead Cost**
    - **Definition:** Additional time/tokens caused by gating mechanism
    - **Measurement:**
      - Wall-clock time: total task time (gated) - total task time (ungated) for same task
      - Token overhead: total tokens (gated) - total tokens (ungated)

### Rule-Based Repair Loop Definition
- A repair loop **starts** when:
  - A tool call produces an error, OR
  - A test fails after a state-modifying action, OR
  - The agent explicitly references a prior mistake in reasoning
- A repair loop **ends** when:
  - Tests pass, OR
  - The error condition clears, OR
  - The agent abandons the repair and moves to a different subtask
- Count only the calls between start and end as repair depth

---

## 5. Instrumentation Contract

### Decision Point Log Schema
```json
{
  "decision_id": "uuid",
  "timestamp": "ISO-8601",
  "task_id": "string",
  "run_id": "string",
  "condition": "ungated | static-gate-0.7 | static-gate-0.5",
  "decision_type": "tool_call",
  "tool_name": "string",
  "tool_params": "object",
  "confidence": "float | null",
  "gate_outcome": "proceed | blocked | escalate | null",
  "reason_if_blocked": "string | null"
}
```

### Tool Call Log Schema
```json
{
  "call_id": "uuid",
  "decision_id": "uuid (FK)",
  "timestamp": "ISO-8-1",
  "tool_name": "string",
  "tool_params": "object",
  "tool_output": "string (truncated if >1000 chars)",
  "tool_success": "boolean",
  "tool_error": "string | null",
  "outcome_label": "correct | unnecessary | wrong-params | wrong-tool | null",
  "downstream_impact": "positive | neutral | negative | unknown"
}
```

### Gate Outcome Log Schema
```json
{
  "gate_id": "uuid",
  "decision_id": "uuid (FK)",
  "timestamp": "ISO-8-1",
  "confidence_reported": "float",
  "threshold": "float",
  "gate_result": "pass | block",
  "agent_response": "proceed_with_info | escalate | abort | n/a",
  "was_correct_decision": "boolean | null"
}
```

### Final Outcome Log Schema
```json
{
  "run_id": "uuid",
  "task_id": "string",
  "condition": "string",
  "start_time": "ISO-8-1",
  "end_time": "ISO-8-1",
  "total_tokens": "integer",
  "total_tool_calls": "integer",
  "task_success": "success | failure | partial",
  "catastrophic_failure": "boolean",
  "severe_failure": "boolean",
  "total_repair_depth": "integer",
  "tool_misuse_count": "integer",
  "false_abstention_count": "integer",
  "escalation_count": "integer",
  "completion_rate": "float",
  "abstention_rate": "float",
  "escalation_rate": "float",
  "effective_throughput": "float"
}
```

### Replay Metadata Schema
```json
{
  "run_id": "uuid",
  "task_id": "string",
  "condition": "string",
  "model": "string",
  "model_version": "string",
  "prompt_hash": "sha256",
  "config_hash": "sha256",
  "random_seed": "integer",
  "temperature": "float",
  "workspace_snapshot": "path/to/snapshot"
}
```

---

## 6. Success Criteria for the Pilot

### Continue UGA Program (Green Light)
**All three must hold:**
1. Catastrophic failure rate: `gated` < `ungated` by ≥20 percentage points OR `gated` = 0 while `ungated` > 0
2. Repair-loop depth: `gated` mean < `ungated` mean with directional signal and per-task consistency (p < 0.1 not required for pilot)
3. Overhead: mean time increase ≤20% AND no task exceeds 50% overhead

**Additionally for confidence calibration:**
- Hypothesis H0 holds (Spearman ρ > 0.2)

### Force Revision (Yellow Light)
**Any of these triggers revision:**
1. Catastrophic failure: no difference between conditions
2. Repair-loop depth: no difference or `gated` worse
3. Overhead: >20% mean increase OR any task >100% overhead
4. False abstention: >30% of blocked calls were correct decisions
5. Hypothesis H0 fails (ρ ≤ 0.2)

**Revision options:** Adjust threshold, change confidence elicitation method, narrow decision-point scope

### Kill or Pivot (Red Light)
**Any of these kills UGA for this application:**
1. `gated` catastrophic failure rate > `ungated` (gating causes more failures)
2. Overhead >50% mean increase across tasks
3. False abstention >50% (gating blocks more correct than incorrect actions)
4. Completion rate <70% in gated condition
5. Unable to collect clean labels (inter-rater Cohen's kappa <0.60 on failure classification; use kappa not raw percent agreement due to potential class imbalance)
6. Hypothesis H0 fails and cannot be remedied

**Pivot direction:** Abandon gating as control mechanism; explore alternative interventions (e.g., post-hoc verification, separate critic model)

---

## 7. Required Outputs by Day 7

### Exact Plots
1. **Catastrophic failure rate by condition** — Bar chart, ungated vs gated, with error bars
2. **Repair-loop depth distribution** — Histogram overlay, ungated vs gated
3. **Overhead distribution** — Box plot of time overhead per task
4. **Tool misuse by condition** — Stacked bar chart (unnecessary, wrong-params, wrong-tool)
5. **Gate outcome breakdown** — Pie chart (proceed, blocked-then-proceed, blocked-then-escalate, blocked-then-abort)
6. **Coverage-risk curve** — Plot selective risk vs coverage for threshold range 0.3-0.95
7. **Confidence calibration diagram** — Reliability plot showing confidence vs actual success rate

### Exact Tables
1. **Summary statistics table:**
   | Metric | Ungated (mean ± std) | Gated (mean ± std) | Delta | Directional Signal |
   |--------|---------------------|-------------------|-------|-------------------|
   | Task success rate | | | | |
   | Catastrophic failure rate | | | | |
   | Mean repair depth | | | | |
   | Mean time (seconds) | | | | |
   | Mean tokens | | | | |
   | Tool misuse count | | | | |
   | Completion rate | | | | |
   | Abstention rate | | | | |
   | Escalation rate | | | | |
   | Effective throughput | | | | |

2. **Per-task breakdown table:**
   | Task ID | Condition | Success | Catastrophic | Repair Depth | Time (s) | Tokens | Completion | Abstention | Escalation |
   |---------|-----------|---------|--------------|--------------|----------|--------|------------|------------|------------|

3. **False abstention analysis table:**
   | Task ID | Blocked Call | What Agent Wanted | Would Have Been Correct? | Impact | Primary Label | Supplementary |
   |---------|--------------|-------------------|-------------------------|--------|--------------|---------------|

4. **Coverage-risk analysis table:**
   | Threshold | Coverage | Risk | Precision | Recall | F1 |
   |-----------|----------|------|-----------|--------|----|

### Exact Memo Sections
1. **Executive summary** (1 paragraph: thesis, method, key result, recommendation)
2. **Method** (benchmark, conditions, metrics)
3. **Confidence calibration results** (H0 test, reliability diagram)
4. **Results** (plots + tables with interpretation)
5. **Failure analysis** (categorize all failures, examples)
6. **Overhead analysis** (time + token cost breakdown, effective throughput)
7. **Coverage-risk analysis** (threshold sweep performance)
8. **Limitations** (pilot scope, labeling uncertainty, generalizability)
9. **Recommendation** (continue/revise/kill with explicit thresholds)
10. **Appendix A:** Full decision-point logs (sample)
11. **Appendix B:** Failure traces (annotated)
12. **Appendix C:** Behavioral test results (gate failure mode testing)

### Exact Examples / Traces to Include
1. **One successful gated task:** Show confidence progression, gate outcomes, final success
2. **One failure in ungated that was prevented in gated:** Side-by-side trace comparison
3. **One false abstention case:** Show what was blocked, why it was wrong to block, downstream impact
4. **One repair-loop cascade in ungated:** Show how one bad tool call led to repair chain
5. **One confidence calibration case:** Show confidence score vs actual outcome

---

## 8. Risks and Anti-Goals

### Biggest Confounds
1. **Task difficulty variance:** Harder tasks may naturally produce more failures regardless of gating
   - *Mitigation:* Stratify analysis by task type (bug/feature/refactor)

2. **Model stochasticity:** Same condition may produce different results on re-run
   - *Mitigation:* Use fixed seed, run each task once per condition (pilot scope), document variance

3. **Labeling subjectivity:** "Severe" vs "recoverable" failure classification may be ambiguous
   - *Mitigation:* Define explicit criteria, have two labelers, measure inter-rater Cohen's kappa (threshold: ≥0.60 for adequate reliability per Landis & Koch 1977)

4. **Confidence calibration quality:** Agent's confidence scores may not reflect true probability
   - *Mitigation:* Measure calibration directly (reliability diagram), treat as analysis output not assumption

### Biggest Measurement Traps
1. **Survivorship bias:** Gated condition may have fewer completions (more aborts), making success rate look artificially high
   - *Mitigation:* Report completion rate separately; analyze aborted cases explicitly

2. **Overhead undercounting:** Confidence elicitation adds tokens/time that isn't attributed to "gating overhead"
   - *Mitigation:* Count all confidence-elicitation tokens/seconds as overhead

3. **False abstention undercounting:** If blocked action is never attempted, we don't know if it was correct
   - *Mitigation:* Use primary (labeler judgment) + supplementary (shadow trace) measures

4. **Cherry-picking favorable tasks:** Pilot tasks may be selected to show gating in good light
   - *Mitigation:* Pre-register task list before running conditions; do not swap tasks mid-pilot

### What NOT to Overclaim from This Pilot
1. **Do not claim:** "Gating works for all agent tasks" — pilot is 15 coding tasks only
2. **Do not claim:** "Confidence is well-calibrated" — calibration is an output, not an assumption; H0 is our test
3. **Do not claim:** "This generalizes to other models" — pilot uses GPT-5.2 only
4. **Do not claim:** "Overhead is acceptable" — acceptable is domain-specific; report numbers, let reviewer judge
5. **Do not claim:** "Gating solves alignment" — this is a reliability intervention, not an alignment solution
6. **Do not claim causal mechanism:** Pilot shows correlation between gating and outcomes; mechanism requires deeper analysis
7. **Do not claim statistical significance:** Pilot generates directional signal, not confirmed hypotheses

---

## 9. Execution Checklist

### Day 1
- [ ] Lock task list (15 tasks, commit to ops/uga-pilot-tasks.md)
- [ ] Build benchmark harness scaffold
- [ ] Implement decision-point logging
- [ ] Implement gate middleware (static threshold 0.7)
- [ ] Write labeling rubric

### Day 2
- [ ] Run 5 tasks in ungated condition
- [ ] Run 5 tasks in gated condition
- [ ] Verify logs are being collected correctly
- [ ] Begin labeling

### Day 3
- [ ] Complete all 15 tasks × 2 conditions = 30 runs
- [ ] Complete labeling
- [ ] Checkpoint: assess false abstention rate
- [ ] Checkpoint: assess confidence calibration (H0)
- [ ] Decision: need 0.5 threshold ablation?

### Day 4
- [ ] Run ablation if needed
- [ ] Generate plots
- [ ] Generate tables
- [ ] Draft memo sections 1-3

### Day 5
- [ ] Draft memo sections 4-7
- [ ] Select example traces
- [ ] Write appendices

### Day 6
- [ ] Full memo review
- [ ] Verify all thresholds/claims against data
- [ ] Remove overclaims

### Day 7
- [ ] Final memo polish
- [ ] Publish to ops/uga-pilot-memo.md
- [ ] Go/no-go decision documented
- [ ] If green: draft 21-day expansion spec

---

## 10. Dependencies

### Required Before Execution
- [ ] Access to GPT-5.2 API (or equivalent) with sufficient quota
- [ ] Benchmark harness code (can be minimal, just needs logging)
- [ ] 15 tasks with ground-truth solutions
- [ ] Labeler available (candidate + 1 other for inter-rater check)

### Code to Write
- [ ] Benchmark runner (load task, run agent, collect logs)
- [ ] Gate middleware (intercept tool calls, elicit confidence, enforce threshold)
- [ ] Log schema implementation (JSON output to files)
- [ ] Analysis scripts (generate plots/tables from logs)

### Code That Can Be Reused
- [ ] OpenClaw agent harness (modify for pilot)
- [ ] Existing task templates from multi-agent work
- [ ] Tool call interception from existing governance layer

---

## 11. UGA as Selective Prediction for Agent Actions

### Lineage and Positioning
UGA applies formal selective prediction techniques to agent action decisions. The selective prediction literature provides the theoretical foundation for our approach:

- **Chow (1970):** Established the reject option for classification problems, showing abstaining from predictions can improve overall performance when the cost of errors exceeds the cost of abstentions. Note: Chow's convexity guarantees for the error-reject tradeoff assume IID data points; agent action trajectories violate this assumption through sequential dependencies. The pilot tests whether the empirical relationship holds despite this theoretical gap.

- **Geifman & El-Yaniv (2017):** Applied selective classification with coverage-risk curves to deep neural networks, demonstrating that selective classification can substantially reduce error rates at moderate coverage loss. The coverage-risk curve concept itself was developed earlier (El-Yaniv & Wiener 2010); Geifman 2017's contribution was adapting this formalism to modern deep networks.

- **SelectiveNet (2019):** Demonstrated that end-to-end training of the reject function alongside classification can outperform post-hoc thresholding on softmax response. This is relevant to our design choice: our pilot uses post-hoc static thresholding as a minimal intervention, and if results are promising, end-to-end calibration training is a natural extension.

### Novel Contribution of UGA
UGA extends this formal framework to agent action decisions, which introduces several new challenges:

1. **Sequential dependencies:** Unlike classification where each instance is independent, agent actions form sequential trajectories where one error compounds to affect future decisions.

2. **Action-specific costs:** Different tools have different reversal costs (file edit vs commit vs API call), requiring more nuanced threshold setting than uniform classification thresholds.

3. **Dynamic context:** Agent confidence must account for changing environment state, not just static input features.

### Research Contribution
UGA contributes:
- A new domain application of selective prediction (agent actions)
- Operational evaluation of reject-option formalism in sequential decision-making
- Empirical evidence for/against confidence-based gating as reliability intervention
- Framework for measuring coverage-risk tradeoffs in agent systems

### Future Directions
Successful UGA could:
- Generalize to other decision-point classes (file mutations, API calls, commits)
- Incorporate adaptive thresholds rather than static ones
- Explore confidence elicitation methods tailored to agent contexts
- Integrate with formal verification methods for critical actions

---

**Document Status:** Complete after literature hardening
**Next Action:** Begin Day 1 checklist or validate against corpus if needed

---
*References: Chow (1970), Geifman & El-Yaniv (2017), SelectiveNet (2019), Guo et al. (2017), Kadavath et al. (2022), Jiang et al. (2021)*
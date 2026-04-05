# UGA Tier 2 Semantic Analysis Framework

**Status:** Pre-registered framework. All expected directions declared before correlations are computed.
**Data:** 103 validated runs across 73 unique tasks (latest-run-per-task: 36 pass, 37 fail). 2,258 state-modifying tool calls (612 with reasoning text, 86 with any Hyland hedge token). 11 tasks have multiple runs (up to 7 replicates).

---

## 0. EXECUTIVE DIAGNOSIS: WHAT THE CURRENT FEATURES ARE AND ARE NOT DOING

### 0.1 The 10 Existing Features — Audit

**Tier 0 (structural):**

| Feature | What it measures | Current aggregation | Problem | Recommendation |
|---|---|---|---|---|
| `step_index_normalized` | Position in trajectory [0,1] | Per-call | Not aggregated to task level in correlations. Cannot correlate with task success because it varies within a task by construction. | DROP from task-level. Keep for trajectory-shape features (see S1). Use as conditioning variable, not predictor. |
| `prior_failure_streak` | Consecutive errors before this call | Per-call; implicitly max'd at task level | The right feature but aggregated wrong. The CURRENT analysis does not include it in task-level correlations. The significant finding (rho=-0.353) comes from the prompt but is not in the `task_level_correlations` output. | INCLUDE in task-level: `fail_streak_max`, `fail_streak_mean`, `fail_streak_sum`. Max is the theoretically motivated one (worst-case consecutive failure). |
| `retry_count` | Repeat of same (tool, target) pair | Per-call; max'd at task level | Conflates intentional retry with accidental repetition. A retry of an Edit on the same file after fixing a typo is different from retrying the same Bash command hoping for different output. | SPLIT into `edit_retry_count` (fixing previous edit) and `command_retry_count` (re-running same command). Motivates the edit precision features below. |
| `tool_switch_rate` | Fraction of adjacent tool changes in window=5 | Rolling average | Window=5 is arbitrary but defensible. The mean aggregation at task level washes out bursts. | ADD `tool_switch_rate_max` (peak switching burst) and `tool_switch_rate_trajectory_slope` (does switching increase over time?). |

**Tier 1 (linguistic):**

| Feature | What it measures | Current aggregation | Problem | Recommendation |
|---|---|---|---|---|
| `hedging_score` | Hyland hedge word density | sum, max | DEAD. rho=-0.122 (p=0.30). Sonnet does not use academic hedge words when coding. 209-term lexicon from academic prose is wrong domain. Only 86/2258 calls have any hedging tokens at all. | REPLACE with domain-specific uncertainty markers (see L1). Do not discard entirely — keep as a control to show the null. |
| `deliberation_length` | Token count of reasoning | sum, max | Not significant at n=73 (rho=+0.107 sum, +0.146 max). Direction flipped from n=14 (was negative). Length correlates with task complexity more than uncertainty. | REFORMULATE as `deliberation_per_action` (reasoning tokens / number of actions taken). Normalizes for task length. Also compute `reasoning_coverage` (fraction of calls with any reasoning). |
| `alternatives_considered` | Count of "I could", "alternatively", etc. | sum | Not significant (rho=+0.047). Too rare — most calls have zero alternatives. 8 patterns is too narrow. | EXPAND pattern set (see L2). Also REFORMULATE: what matters is not whether the agent considers alternatives, but whether it ACTS on a different strategy after considering them (requires combining with structural data). |
| `backtrack_count` | Count of "wait", "actually", "hmm" | sum | Borderline (rho=+0.300, p_corrected=0.12). Positive direction is theoretically sensible: agents that self-correct succeed more. But the backtrack patterns overlap with the metacognitive markers we want to add. | KEEP but REFINE. Split into `self_correction_count` (backtracks that lead to strategy change) and `hesitation_count` (backtracks that do not lead to change). The distinction is whether the next action differs from what preceded the backtrack. |
| `verification_score` | Density of "check", "verify", "test", etc. | sum, max | Was significant at n=14 (rho=-0.602) but COLLAPSED at n=73 (rho=+0.020). The original signal was an artifact of the pass-rate confound (8% pass rate with unvalidated labels). | REFORMULATE. The issue is that verification language is ubiquitous in coding. "Let me check" appears in both good and bad agents. What matters is the TIMING: verification early (exploring) is different from verification late (panicking). Compute `verification_early` vs `verification_late` and compare. |
| `planning_score` | Density of "let me", "first", "then", "next" | sum, max | Same collapse as verification (rho=+0.092 at n=73). Planning language is how Sonnet structures ALL its reasoning, not a signal of uncertainty. | REFORMULATE or DROP. The word "then" appears in nearly every multi-step reasoning trace. If kept, restrict to specific planning patterns: "let me try" (tentative) vs "I will" (committed). |

### 0.2 The Aggregation Problem

The current framework aggregates per-call features to task level via sum and max. Both are confounded:
- **Sum** correlates with task length (more calls = higher sum). Failing tasks average 22.9 calls; passing tasks 16.6. Any per-call feature that is positive on average will show higher sums for failures simply because failures produce more calls.
- **Max** is less confounded but still biased: longer tasks have more chances for an extreme value.

**Resolution:** Every aggregation below uses one of:
1. **Mean** (per-call average, normalized for task length)
2. **Weighted mean** (weighted by step_index_normalized, to capture trajectory position)
3. **Trajectory shape** (slope of the feature over normalized time — is it increasing or decreasing?)
4. **Max** (where theoretical motivation is specifically "the worst moment matters")

---

## 1. NEW STRUCTURAL FEATURES (S-prefix)

These features use only tool_name, tool_params_json, tool_result_json, sequence_number, and timestamp. No reasoning text required.

### S1: Error Recovery Patterns

**Motivation:** fail_streak_max (rho=-0.353 at n=73 per prompt data) is the strongest predictor. But it is a blunt instrument: a streak of 5 failures means different things depending on what happens AFTER. Error recovery patterns capture the sequel.

| Feature | Definition | Extraction | Expected direction | Justification | Potential confound |
|---|---|---|---|---|---|
| `recovery_rate` | (Number of fail->pass transitions) / (total failures) | Walk tool_result_json is_error flags in sequence. Count transitions from is_error=True to is_error=False. Divide by total is_error=True count. | **Positive** (higher recovery -> more success) | Agents that recover from errors are demonstrating effective debugging. Persistent failure without recovery signals the agent is stuck. | Tasks with many easy errors (e.g., import typos) will have high recovery but may still fail the overall task. Recovery from easy errors is less meaningful than recovery from hard errors. |
| `longest_success_streak` | Maximum consecutive non-error calls | Walk is_error flags, find longest run of False | **Positive** (longer success runs -> more success) | Complementary to fail_streak_max. Measures the agent's best sustained productive period. | Correlated with total_calls for tasks where the agent gets it mostly right. May just be measuring "was the task easy." |
| `recovery_latency_mean` | Average number of calls to go from first error in a streak to first success | For each failure streak, count calls until next success. Average over all streaks. | **Negative** (slower recovery -> less success) | Fast recovery suggests the agent quickly identifies what went wrong. Slow recovery suggests flailing. | Short tasks have less room for recovery. Normalize by total_calls or only compute for tasks with at least one failure streak. |
| `fail_then_switch_rate` | Fraction of failures followed by a different tool | After each is_error=True, check if next call uses a different tool_name | **Positive** (switching tools after failure -> more success) | Switching tools after failure (e.g., Bash error -> Read the file -> Edit) suggests the agent is diagnosing rather than retrying blindly. | High switch rate after failure could also indicate undirected flailing. Need to distinguish "informational switch" (to Read/Grep) from "random switch" (to another Edit). |

### S2: Strategy Shift Patterns

**Motivation:** The exhaust mining found "instead" 2.35x more in passes. Strategy shifts — moments when the agent changes approach — may be a structural signature of adaptive problem-solving.

| Feature | Definition | Extraction | Expected direction | Justification | Potential confound |
|---|---|---|---|---|---|
| `phase_count` | Number of distinct "phases" in the trajectory | Detect phases by tool-use composition. A phase is a contiguous run of calls dominated by one tool type (>60% of calls in a window of 5). Count transitions between phases. | **Positive** (more phases -> more success) | Successful agents explore (Read/Bash), then implement (Edit), then verify (Bash test). This produces distinct phases. Failing agents intermix all tools throughout. | Complex tasks may require more phases regardless of success. Partially mitigated by the fact that task complexity is not perfectly correlated with success at 50% pass rate. |
| `explore_before_act_ratio` | (Read-only calls before first state-modifying edit) / (total calls) | Count all calls (including non-state-modifying, from total_tool_calls) before the first Edit or state-modifying Bash. Divide by total_tool_calls. | **Positive** (more exploration before acting -> more success) | Agents that gather information before modifying code are more likely to make the right change. Premature editing suggests poor understanding. This feature requires access to the full call sequence (not just state-modifying calls). | REQUIRES RE-PARSING from raw_stream_json to get Read/Grep calls. Currently only state-modifying calls are stored. This is a significant extraction requirement. Alternative: use `sequence_number` of first Edit call as a proxy — higher first-edit position means more exploration. |
| `first_edit_position` | Normalized position of the first Edit/Write call in the trajectory | `sequence_number_of_first_edit / total_state_modifying_calls` | **Positive** (later first edit -> more success) | Simpler proxy for explore_before_act. No re-parsing needed. | A task that starts with an obvious one-line fix will have an early first edit and also pass — this feature would wrongly predict failure for trivially easy tasks. |
| `edit_to_bash_ratio` | Edit calls / Bash calls | Count tool_name='Edit' and tool_name='Bash' per run | **Direction unclear — include as exploratory** | High edit-to-bash could mean the agent is making many code changes (bad if they are wrong, good if they are right). Low could mean the agent is stuck debugging. | Both directions are plausible. Pre-register as exploratory (no expected direction). |

### S3: Edit Precision Patterns

**Motivation:** The exhaust mining found successful agents "name exact code changes" while failing agents "narrate process." Structural signatures of precision should be visible in the edit operations themselves.

| Feature | Definition | Extraction | Expected direction | Justification | Potential confound |
|---|---|---|---|---|---|
| `unique_files_touched` | Number of distinct file paths in Edit/Write params | Extract file_path from tool_params_json for Edit/Write calls. Count unique values. | **Negative** (more files -> less success) | Focused fixes touch fewer files. Agents that scatter edits across many files are less likely to have a coherent solution. | Complex bugs legitimately span multiple files. Sympy and Django sometimes require multi-file fixes. |
| `edit_churn_rate` | (Number of times the same file is edited) / (unique files edited) | Count total Edit calls per unique file path. Average this ratio. | **Negative** (more churn -> less success) | Re-editing the same file multiple times suggests the agent is making corrections to its own previous edits — i.e., it got it wrong the first time. | Sometimes iterative refinement is the right approach (add feature, then add test, then fix edge case in same file). |
| `edit_size_cv` | Coefficient of variation of edit sizes | For Edit calls, measure len(new_string) - len(old_string) if available, else len(tool_params_json). Compute CV = std/mean across all edits in the run. | **Negative** (high variance -> less success) | Consistent edit sizes suggest a systematic approach. Wildly varying sizes (a 2-character fix followed by a 500-character rewrite) suggest the agent is flailing between small patches and wholesale rewrites. | Edit size is partly determined by the nature of the fix, not agent quality. |
| `late_edit_fraction` | Fraction of Edit calls occurring in the last third of the trajectory | Count Edit calls with step_index_normalized > 0.67. Divide by total Edit calls. | **Negative** (more late edits -> less success) | Late edits suggest the agent is still modifying code near the end of its turn, which means it has not settled on a solution. Early editing followed by verification is the healthy pattern. | Some tasks require late edits (e.g., fixing test expectations after the main fix). |

### S4: Bash Command Sophistication

**Motivation:** 1914/2258 calls are Bash. The current framework treats all Bash commands identically. The CONTENT of the Bash command carries information about the agent's strategy.

| Feature | Definition | Extraction | Expected direction | Justification | Potential confound |
|---|---|---|---|---|---|
| `test_run_count` | Number of Bash calls containing pytest/unittest/test commands | Regex on tool_params_json command: `pytest\b|python.*-m\s+pytest|unittest|test_|_test\.py` | **Positive** (more test runs -> more success) | Running tests is the primary verification mechanism. Agents that run tests more frequently are more likely to catch errors. | Agents stuck in test-fix loops may run tests many times without making progress. Combine with `test_pass_rate` below. |
| `test_pass_rate` | Fraction of test-related Bash calls that succeed | Among test_run commands, fraction where is_error=False in tool_result_json | **Positive** (higher test pass rate -> more success) | Direct measure of whether the agent's changes actually work. | Near-tautological for the final test run (which determines task_success). Exclude the last test call to avoid circularity. Compute over all-but-last test run. |
| `grep_before_edit_rate` | Fraction of Edit calls preceded (within 3 calls) by a Read/Grep/Glob | For each Edit call, look at the 3 preceding calls. Check if any are Read/Grep/Glob (information-gathering). Fraction of Edit calls with at least one preceding information call. | **Positive** (more informed edits -> more success) | Edits preceded by reading are more likely to be correct because the agent has fresh context. Edits made "blind" (without recent reading) suggest the agent is guessing. | REQUIRES access to ALL calls, not just state-modifying ones. Read/Grep are classified as non-state-modifying and not in tool_calls. This feature requires re-parsing or querying the raw stream. Alternatively, look for Bash `cat`/`grep` calls that ARE in the state-modifying set (unlikely — these are correctly classified as read-only). VERDICT: defer unless raw_stream_json is re-parsed to include read-only calls as metadata. |
| `command_complexity` | Average number of pipe/chain operators per Bash call | Count `|`, `&&`, `;` in each Bash command. Average per run. | **Direction unclear — exploratory** | Complex commands could indicate sophisticated use of the shell (positive) or cobbled-together workarounds (negative). Both interpretations are plausible. | Mark as exploratory. |

### S5: Temporal Shape Features

**Motivation:** The trajectory position interaction was a founding hypothesis. These features capture the SHAPE of the trajectory, not just point estimates.

| Feature | Definition | Extraction | Expected direction | Justification | Potential confound |
|---|---|---|---|---|---|
| `error_rate_slope` | Slope of error rate over normalized time | Divide trajectory into 5 equal bins. Compute error rate per bin. Fit OLS slope. | **Negative** (increasing error rate -> less success) | An agent whose error rate increases over time is getting worse, not better. Positive slope = deteriorating performance. | With small numbers of calls per bin, the slope estimate will be noisy. Require at least 10 total calls for this feature to be defined. |
| `action_density_slope` | Slope of (state-modifying calls / time window) over the trajectory | Divide wall_clock_seconds into 5 equal intervals. Count state-modifying calls per interval. Fit slope. | **Direction unclear** | Increasing density could mean the agent is making rapid progress (good) or frantically flailing (bad). | Requires timestamps. Pre-register as exploratory. |
| `tool_diversity_trajectory` | Shannon entropy of tool-name distribution, early half vs late half | Split trajectory at midpoint. Compute Shannon entropy H = -sum(p*log(p)) for tool_name distribution in each half. Return H_late - H_early. | **Negative** (increasing tool diversity late -> less success) | Successful trajectories converge: early exploration (high entropy) followed by focused implementation (low entropy). Increasing entropy late means the agent is still trying different approaches near the end. | Tasks that genuinely require multiple tools throughout will confound this. |

---

## 2. NEW LINGUISTIC FEATURES (L-prefix)

These features require reasoning_text. Available for 612/2258 calls. All features are computed per-call and aggregated to task level via mean (unless noted).

### L1: Domain-Specific Uncertainty Markers (replacing Hyland hedging)

**Motivation:** Hyland hedging is dead for Sonnet (rho=-0.122, 86/2258 calls with any hedging). Sonnet does not write "perhaps" or "might" when debugging code. It writes "I need to", "let me try", "I'm not sure if", "this might not work". The replacement lexicon must be grounded in what Sonnet actually says, which the exhaust mining has partially revealed.

| Feature | Definition | Patterns | Expected direction | Justification | Potential confound |
|---|---|---|---|---|---|
| `coding_uncertainty_score` | Density of Sonnet-specific uncertainty markers | Patterns (all case-insensitive): `\bnot sure\b`, `\bmight not\b`, `\bmay not\b`, `\bnot certain\b`, `\bI think\b` (in uncertainty context — NOT "I think this is the fix"), `\bpossibly\b`, `\bcould be\b`, `\bhard to tell\b`, `\bnot obvious\b`, `\bunclear\b`, `\btricky\b`, `\bcomplicated\b`, `\bconfusing\b`, `\bweird\b`, `\bstrange\b`, `\bunexpected\b` | **Negative** (more uncertainty markers -> less success) | These are the phrases Sonnet actually uses to express doubt in coding contexts. "Not sure" and "might not" are direct uncertainty assertions, unlike the Hyland lexicon's academic hedges. | Some of these phrases ("unexpected", "strange") might appear when the agent correctly identifies a surprising but real behavior in the codebase. Successful debugging sometimes requires noticing unexpected things. Mitigate by checking if the phrase is followed by a successful action. |
| `confidence_assertion_score` | Density of confidence/certainty markers | Patterns: `\bthe (?:issue|problem|bug|fix) is\b`, `\bI (?:will|need to|should)\s+(?:add|remove|change|fix|update|modify)\b`, `\bthis (?:fixes|resolves|addresses)\b`, `\bthe (?:correct|right|proper) (?:way|approach|fix)\b`, `\bspecifically\b`, `\bexactly\b`, `\bprecisely\b` | **Positive** (more confidence markers -> more success) | From exhaust mining: "successful agents name exact code changes." Confidence assertions indicate the agent has diagnosed the problem and knows the fix. Vagueness indicates it does not. | Overconfident agents may assert confidence while being wrong. This feature captures stated confidence, not actual correctness. The question is whether stated confidence is calibrated for Sonnet — if CoT is unfaithful (Chen et al.), it may not be. This is exactly what we are testing. |
| `vague_action_score` | Density of vague/process-narration language | Patterns: `\blet me (?:check|look|see|try|examine|investigate)\b`, `\bnow (?:let me|I (?:will|need to|should))\b`, `\bI'll (?:start|begin) by\b`, `\bfirst,? (?:let me|I (?:will|need to|should))\b` | **Negative** (more vague narration -> less success) | "let me check" (9x fail vs 1x pass), "now let me" (14x fail vs 1x pass) from exhaust mining. Process narration without specifics is filler. The agent is thinking aloud about WHAT to do rather than saying what the fix is. | These patterns will be highly correlated with planning_score, which also captures "let me" and "first". If both are included, they will multicollinear. RESOLUTION: replace planning_score with vague_action_score (strictly more precise). |

### L2: Metacognitive Markers

**Motivation:** The backtrack patterns ("wait", "actually", "hmm") showed borderline significance (rho=+0.300, p_corr=0.12). This suggests metacognition — the agent monitoring and correcting its own reasoning — may carry real signal. The current 8-pattern backtrack set is too coarse.

| Feature | Definition | Patterns | Expected direction | Justification | Potential confound |
|---|---|---|---|---|---|
| `productive_correction_count` | Self-corrections that lead to a different action | Patterns: `\bactually\b`, `\bwait\b`, `\bno,`, `\bI was wrong\b`, `\bthat's not right\b`, `\blet me reconsider\b`, `\bon second thought\b`, `\bhmm\b`. THEN check: does the NEXT tool call differ from the PREVIOUS tool call (different tool_name or different file target)? Count only corrections that lead to changed behavior. | **Positive** (more productive corrections -> more success) | Self-correction that leads to behavioral change is genuine metacognition. Self-correction that does not change behavior is just verbal noise. The existing backtrack_count mixes both. | Detecting "changed behavior" requires comparing consecutive calls, which is structural analysis. The feature is inherently an interaction feature (L+S). |
| `unproductive_hesitation_count` | Self-correction markers NOT followed by changed behavior | Same patterns as above, but the next action is the same as the previous | **Negative** (more unproductive hesitation -> less success) | Verbal hesitation without behavioral change is flailing. The agent says "wait, actually" but then does the same thing anyway. | Hard to define "same behavior" precisely. Two Bash commands are "the same" only if the command string is identical, which is too strict. Use tool_name + file_target match as a proxy. |
| `metacognitive_density` | All metacognitive markers (both productive and unproductive) per token | Union of: backtrack patterns + `\binteresting\b`, `\bI see\b`, `\bah\b`, `\boh\b`, `\bright\b` (discourse markers indicating processing). Normalized by token count. | **Positive** (more metacognition -> more success, based on backtrack direction) | General metacognitive engagement is a proxy for depth of processing. The positive direction of backtrack_count (+0.300) suggests metacognitive activity is constructive for Sonnet. | "I see" and "right" are extremely common discourse markers that may not indicate genuine metacognition. They could be filler. Test with and without these weak markers. |

### L3: Causal Reasoning Markers

**Motivation:** Successful agents in the exhaust mining showed more precise causal reasoning ("because the __init__.py is missing" vs "let me check the imports"). Causal language indicates the agent has formed a hypothesis.

| Feature | Definition | Patterns | Expected direction | Justification | Potential confound |
|---|---|---|---|---|---|
| `causal_density` | Density of causal connectives | Patterns: `\bbecause\b`, `\bsince\b`, `\btherefore\b`, `\bso\b` (sentence-initial or after comma), `\bthis means\b`, `\bwhich means\b`, `\bdue to\b`, `\bcaused by\b`, `\bthe reason\b`, `\bas a result\b`, `\bconsequently\b` | **Positive** (more causal reasoning -> more success) | Causal statements indicate the agent has a diagnosis, not just a symptom description. "The test fails because X" is more informative than "the test fails, let me check." | "So" is extremely common and multi-functional. Sentence-initial "So" is often just a discourse connector, not causal. Restrict to "so that" or "so the" to increase precision. Also: "because" in error messages (which appear in tool_result_json, not reasoning_text) should not count. |
| `diagnosis_specificity` | Whether reasoning references specific code entities | Patterns: backtick-quoted code (`\`[^`]+\``), line number references (`line\s+\d+`), function/class name patterns (`\b(?:def|class|function|method)\s+\w+`), file path references (`\w+\.py`, `\w+/\w+`) | **Positive** (more specific references -> more success) | This operationalizes the exhaust finding that "successful agents name exact code changes." An agent that writes "I need to change the return value of `get_queryset` on line 42 of `views.py`" is more likely to be correct than one that writes "I need to fix the query." | Code entities in reasoning text may come from copy-pasting tool results rather than genuine understanding. An agent can parrot line numbers from a traceback without understanding them. To partially mitigate: measure specificity only in reasoning text that is NOT immediately preceded by a tool result containing those same entities. (Hard to implement cleanly.) |

### L4: Emotional/Evaluative Markers

**Motivation:** The exhaust mining found "wrong" 7x more in fails. Evaluative language may carry signal because it reflects the agent's assessment of the situation.

| Feature | Definition | Patterns | Expected direction | Justification | Potential confound |
|---|---|---|---|---|---|
| `negative_evaluation_score` | Density of negative assessment language | Patterns: `\bwrong\b`, `\bbroken\b`, `\bfailing\b`, `\bdoesn't work\b`, `\bnot working\b`, `\berror\b` (in reasoning, not in tool results), `\bbug\b`, `\bissue\b`, `\bproblem\b` | **Negative** (more negative evaluation -> less success) | "Wrong" 7x more in fails. Agents that repeatedly assess the situation negatively are stuck in a failure mode. | "Error", "bug", and "problem" will appear in all tasks because that is the nature of the work (fixing bugs). The signal is in REPEATED negative evaluation, not single instances. Aggregate as count, not presence/absence. Also: these words in the TASK DESCRIPTION (which may appear in reasoning as quoted context) are noise, not signal. |
| `positive_evaluation_score` | Density of positive assessment language | Patterns: `\bworks\b`, `\bcorrect\b`, `\bfixed\b`, `\bsolved\b`, `\bsuccess\b`, `\bpasses\b`, `\bclean\b`, `\bgood\b`, `\bproperly\b` | **Positive** (more positive evaluation -> more success) | Symmetric counterpart to negative evaluation. | Near-tautological: the agent reports "the test passes" because it does. This feature will be highly correlated with test_pass_rate (S4). Exclude tool-result-derived evaluations if possible, or accept the correlation and check partial correlations. |

---

## 3. INTERACTION FEATURES (I-prefix)

These features combine structural and linguistic signals.

### I1: Reasoning-Action Coherence

**Motivation:** If CoT is unfaithful 75% of the time (Chen et al.), then there should be measurable incoherence between what the agent SAYS and what it DOES. Incoherence is a signal of unfaithful reasoning, which may predict errors.

| Feature | Definition | Extraction | Expected direction | Justification | Potential confound |
|---|---|---|---|---|---|
| `stated_plan_match_rate` | Fraction of calls where reasoning mentions the tool actually used | In reasoning_text, check for mentions of: "edit" before an Edit call, "run" or "test" or "execute" before a Bash call, "write" or "create" before a Write call. Fraction of calls where the verb matches the action. | **Positive** (more plan-action match -> more success) | Plan-action coherence is a proxy for faithful reasoning. An agent that says "let me edit the file" and then actually edits the file is reasoning faithfully. One that says "let me check the tests" and then edits a file is not. | Very noisy. The agent often does not explicitly state what tool it will use. Many reasoning blocks discuss the PROBLEM, not the action. Only compute for calls where reasoning contains an identifiable action verb. Skip calls where reasoning is pure diagnosis. |
| `reasoning_predicts_next_success` | Whether richer reasoning before an action predicts that action's result | For each call with reasoning_text: compute deliberation_length, then check if the next tool_result is_error=False. Spearman rho between reasoning length and next-call success, per run. | **Direction ambiguous** | At n=14, deliberation in early calls correlated with failure (rho=-0.371), suggesting over-thinking. At n=73, not significant. The sign may depend on whether the agent is exploring (thinking is good) or flailing (thinking is bad). Pre-register as EXPLORATORY. | Per-run correlation requires at least 5+ calls with reasoning per run. Many runs will not qualify. |
| `reasoning_action_type_match` | Does reasoning length correlate with action commitment level? | Classify actions as exploratory (Bash read commands, even if classified as state-modifying due to pipes) or committed (Edit, Write, non-trivial Bash). Compute mean reasoning length for exploratory vs committed actions per run. Return ratio. | **Positive** (more reasoning before committed actions -> more success) | Agents that think more before making permanent changes (edits) and think less before exploratory actions (running tests) are demonstrating appropriate calibration of effort. | Edit calls may have short reasoning because the diagnosis was in a preceding reasoning-only block. The reasoning attribution in trace_collector already handles this (pending_reasoning), but it may not be perfect. |

### I2: Trajectory-Level Behavioral Patterns

| Feature | Definition | Extraction | Expected direction | Justification | Potential confound |
|---|---|---|---|---|---|
| `diagnose_implement_verify_score` | Whether the trajectory follows a DIV pattern | Score 0-1 based on whether the trajectory has: (1) an initial phase of mostly Bash/Read (diagnose), (2) a middle phase of mostly Edit (implement), (3) a final phase of mostly Bash with test commands (verify). Use dynamic time warping or a simpler heuristic: divide trajectory into thirds, check dominant tool type in each third. | **Positive** (more DIV-like -> more success) | The canonical successful debugging trajectory is: read the code, understand the bug, make the fix, run the tests. Deviations from this (e.g., editing immediately, never testing) predict failure. | Rigid third-based splitting may miss tasks where the DIV pattern occurs in different proportions. Also, some tasks are simple enough that the pattern is trivially DIV (one read, one edit, one test). These should pass regardless. |
| `reasoning_trend_slope` | Slope of reasoning length over the trajectory | Fit OLS: deliberation_length ~ step_index_normalized, per run. Return slope coefficient. | **Negative** (increasing reasoning length over time -> less success) | Chen et al. found unfaithful CoTs are systematically longer (2064 vs 1439 tokens). If an agent's reasoning gets LONGER as it proceeds, it may be compensating for increasing confusion with verbal output. Successful agents' reasoning should stay constant or decrease as they converge on the solution. | The agent runs out of things to say on later turns because it is repeating itself. Short late reasoning could also indicate the agent has given up and is just trying random things with no thought. |

---

## 4. IMPLEMENTATION PLAN

### 4.1 Extraction Priority (ordered by expected signal strength and implementation cost)

**Tier 2A — Low cost, high expected signal (implement first):**

1. `fail_streak_max` / `fail_streak_mean` — Already computed per-call. Just add to task-level aggregation in analysis.py. [SQL + Python, 30 min]
2. `recovery_rate` — Walk is_error flags, count transitions. [Python in feature_definitions.py, 1 hr]
3. `unique_files_touched` — Parse file_path from tool_params_json for Edit/Write. [SQL, 30 min]
4. `edit_churn_rate` — Count edits per unique file. [SQL, 30 min]
5. `first_edit_position` — Sequence number of first Edit, normalized. [SQL, 30 min]
6. `test_run_count` — Regex on Bash commands. [Python, 1 hr]
7. `late_edit_fraction` — Filter Edit calls by position. [SQL, 30 min]
8. `coding_uncertainty_score` — New lexicon, same scoring method as hedging_score. [Python, 1 hr]
9. `vague_action_score` — Regex patterns from exhaust mining. [Python, 1 hr]
10. `confidence_assertion_score` — Regex patterns. [Python, 1 hr]

**Tier 2B — Medium cost, medium expected signal (implement if 2A shows promise):**

11. `productive_correction_count` — Requires matching backtrack markers to subsequent behavioral change. [Python, 2 hr]
12. `causal_density` — Causal connective regex with "so" disambiguation. [Python, 1 hr]
13. `diagnosis_specificity` — Backtick, line number, file path regex. [Python, 1 hr]
14. `negative_evaluation_score` — Word list with reasoning-vs-result disambiguation. [Python, 1 hr]
15. `error_rate_slope` — Binned error rate with OLS. [Python, 2 hr]
16. `tool_diversity_trajectory` — Shannon entropy per half. [Python, 1 hr]
17. `phase_count` — Sliding window tool composition. [Python, 2 hr]
18. `diagnose_implement_verify_score` — Trajectory thirds heuristic. [Python, 2 hr]

**Tier 2C — High cost or high confound risk (implement only with justification):**

19. `test_pass_rate` — Requires parsing test output from tool_result_json. [Python, 2 hr]
20. `stated_plan_match_rate` — Noisy; requires action-verb detection. [Python, 3 hr]
21. `reasoning_trend_slope` — Requires per-run OLS with adequate data. [Python, 2 hr]
22. `explore_before_act_ratio` — Requires re-parsing raw_stream_json for non-state-modifying calls. [Python, 3 hr]
23. `grep_before_edit_rate` — Same dependency as above. [Python, 3 hr]
24. `command_complexity` — Exploratory, no clear direction. [Python, 1 hr]

### 4.2 Data Requirements Per Feature

| Feature | reasoning_text | tool_params_json | tool_result_json | sequence_number | raw_stream_json |
|---|---|---|---|---|---|
| S1: recovery_rate | | | YES | YES | |
| S1: longest_success_streak | | | YES | YES | |
| S1: recovery_latency_mean | | | YES | YES | |
| S1: fail_then_switch_rate | | | YES | YES | |
| S2: phase_count | | YES (tool_name) | | YES | |
| S2: first_edit_position | | YES (tool_name) | | YES | |
| S2: edit_to_bash_ratio | | YES (tool_name) | | | |
| S3: unique_files_touched | | YES (file_path) | | | |
| S3: edit_churn_rate | | YES (file_path) | | | |
| S3: edit_size_cv | | YES (old_string, new_string) | | | |
| S3: late_edit_fraction | | YES (tool_name) | | YES | |
| S4: test_run_count | | YES (command) | | | |
| S4: test_pass_rate | | YES (command) | YES | | |
| S4: command_complexity | | YES (command) | | | |
| S5: error_rate_slope | | | YES | YES | |
| S5: tool_diversity_trajectory | | YES (tool_name) | | YES | |
| L1: coding_uncertainty_score | YES | | | | |
| L1: confidence_assertion_score | YES | | | | |
| L1: vague_action_score | YES | | | | |
| L2: productive_correction_count | YES | YES (next call) | | YES | |
| L2: metacognitive_density | YES | | | | |
| L3: causal_density | YES | | | | |
| L3: diagnosis_specificity | YES | | | | |
| L4: negative_evaluation_score | YES | | | | |
| L4: positive_evaluation_score | YES | | | | |
| I1: stated_plan_match_rate | YES | YES (tool_name) | | | |
| I2: diagnose_implement_verify_score | | YES (tool_name, command) | | YES | |
| I2: reasoning_trend_slope | YES | | | YES | |

### 4.3 Schema Changes

Add new columns to `tool_calls` table for per-call features:

```sql
-- Tier 2 per-call features (populated by extended feature extraction)
ALTER TABLE tool_calls ADD COLUMN coding_uncertainty_score REAL;
ALTER TABLE tool_calls ADD COLUMN confidence_assertion_score REAL;
ALTER TABLE tool_calls ADD COLUMN vague_action_score REAL;
ALTER TABLE tool_calls ADD COLUMN metacognitive_density REAL;
ALTER TABLE tool_calls ADD COLUMN causal_density REAL;
ALTER TABLE tool_calls ADD COLUMN diagnosis_specificity REAL;
ALTER TABLE tool_calls ADD COLUMN negative_evaluation_score REAL;
ALTER TABLE tool_calls ADD COLUMN positive_evaluation_score REAL;
```

Task-level aggregate features (S-prefix, I-prefix) should be computed in analysis.py and stored in a new `run_features` table or computed on-the-fly during analysis (preferred for now to avoid schema bloat).

### 4.4 Update to analysis.py

The task-level correlation computation needs to include:

```python
# In the task-level aggregation loop, add per-run:
# Structural features (computed from tool_calls directly)
t['fail_streak_max'] = max(tc.prior_failure_streak for tc in run_calls)
t['fail_streak_mean'] = mean(tc.prior_failure_streak for tc in run_calls)
t['recovery_rate'] = count_fail_to_pass_transitions(run_calls) / max(count_failures(run_calls), 1)
t['unique_files_touched'] = count_unique_files(run_calls)
t['edit_churn_rate'] = count_total_edits(run_calls) / max(count_unique_files(run_calls), 1)
t['first_edit_position'] = first_edit_seqnum(run_calls) / max(len(run_calls), 1)
t['test_run_count'] = count_test_commands(run_calls)
t['late_edit_fraction'] = count_late_edits(run_calls) / max(count_edits(run_calls), 1)
# ... etc

# Linguistic features (from reasoning_text)
# Per-call, then aggregated via MEAN (not sum) to normalize for task length
t['coding_uncertainty_mean'] = mean(tc.coding_uncertainty_score for tc in run_calls if tc.reasoning_text)
t['confidence_assertion_mean'] = mean(tc.confidence_assertion_score for tc in run_calls if tc.reasoning_text)
t['vague_action_mean'] = mean(tc.vague_action_score for tc in run_calls if tc.reasoning_text)
```

### 4.5 Bonferroni Accounting

With the current 12 features, Bonferroni divides alpha by 12. Adding features costs statistical power.

**Strategy:** Organize features into BLOCKS tested sequentially:

1. **Block A (structural, 8 features):** fail_streak_max, recovery_rate, unique_files_touched, edit_churn_rate, first_edit_position, test_run_count, late_edit_fraction, error_rate_slope. Bonferroni m=8.
2. **Block B (linguistic replacement, 3 features):** coding_uncertainty_score, confidence_assertion_score, vague_action_score. Bonferroni m=3.
3. **Block C (linguistic extension, 5 features):** productive_correction_count, causal_density, diagnosis_specificity, negative_evaluation_score, metacognitive_density. Bonferroni m=5.
4. **Block D (interaction, 3 features):** diagnose_implement_verify_score, reasoning_trend_slope, stated_plan_match_rate. Bonferroni m=3.

Test Block A first. If any feature is significant, proceed to Block B. This is a sequential testing design that preserves power.

Alternatively: use Benjamini-Hochberg FDR control (q=0.10) instead of Bonferroni, which is more appropriate for exploratory feature discovery. Pre-register this choice.

---

## 5. PRE-REGISTRATION SUMMARY

### 5.1 Primary Hypotheses (Block A — structural)

| # | Feature | Expected direction | Minimum effect size (|rho|) |
|---|---|---|---|
| H1 | `fail_streak_max` | Negative | 0.25 |
| H2 | `recovery_rate` | Positive | 0.20 |
| H3 | `unique_files_touched` | Negative | 0.20 |
| H4 | `first_edit_position` | Positive | 0.20 |
| H5 | `test_run_count` | Positive | 0.20 |
| H6 | `late_edit_fraction` | Negative | 0.20 |

### 5.2 Secondary Hypotheses (Block B — linguistic replacement)

| # | Feature | Expected direction | Minimum effect size (|rho|) |
|---|---|---|---|
| H7 | `coding_uncertainty_score` | Negative | 0.20 |
| H8 | `confidence_assertion_score` | Positive | 0.20 |
| H9 | `vague_action_score` | Negative | 0.25 |

### 5.3 Exploratory Features (no pre-registered direction)

| Feature | Reason for exploratory status |
|---|---|
| `edit_to_bash_ratio` | Both directions plausible |
| `command_complexity` | Both directions plausible |
| `action_density_slope` | Both directions plausible |
| `reasoning_predicts_next_success` | Sign flipped between n=14 and n=73 samples |

### 5.4 Null Hypothesis Controls

Include these to demonstrate the framework is not just finding noise:

| Feature | Expected result | Reason |
|---|---|---|
| `hedging_score` (Hyland) | NOT significant | Already shown dead; confirms the lexicon problem |
| `planning_score` (current) | NOT significant | Already collapsed at n=73; replaced by vague_action_score |
| `random_noise` | NOT significant | Column of random floats; any framework that finds this significant is broken |

---

## 6. KNOWN RISKS AND MITIGATIONS

### 6.1 Multiple Comparisons

Adding 20+ features to a 73-task dataset risks false discovery. Mitigations:
- Sequential block testing (Section 4.5)
- Pre-registered directions (Section 5)
- Effect size thresholds (|rho| >= 0.20), not just significance
- Benjamini-Hochberg FDR as alternative to Bonferroni
- Random noise control column

### 6.2 Task Length as Confounder

Failing tasks have more calls (22.9 vs 16.6). Any feature correlated with task length will appear correlated with failure. Mitigations:
- Use mean (not sum) aggregation
- Include total_calls as a covariate in multivariate analysis
- Compute partial correlations controlling for total_calls
- Report both raw and partial correlations

### 6.3 The 612/2258 Problem

Only 612/2258 calls have reasoning text. Linguistic features are computed on a biased subsample (calls where the model chose to produce visible reasoning). The calls WITHOUT reasoning may be systematically different (e.g., simple actions that needed no deliberation). Mitigations:
- Report `reasoning_coverage` (fraction of calls with reasoning) as a feature itself
- For linguistic features, always report n alongside correlations
- Do NOT impute reasoning features for calls without reasoning

### 6.4 Pass Rate and Task Difficulty

At 50.5% pass rate (53/105), the data is well-balanced for binary discrimination. But at the task level (73 unique tasks, some with multiple runs), the effective sample size depends on task difficulty variation. If most tasks are either trivially easy or impossibly hard, the features have nothing to discriminate on. Mitigations:
- Report the distribution of per-task pass rates (how many tasks are 0%, 50%, 100%?)
- Features should predict success for tasks with MIXED outcomes across runs, not just separate always-pass from always-fail

### 6.5 Structural-Linguistic Correlation

Many "structural" features are partially linguistic (e.g., test_run_count depends on parsing the Bash command string). And many "linguistic" features are partially structural (e.g., productive_correction_count depends on the subsequent action). The taxonomy is heuristic. Mitigations:
- Compute the correlation matrix between all features before testing against success
- Report variance inflation factors (VIF) for any multivariate model
- If two features correlate at r > 0.7, keep only the one with the clearer theoretical motivation

---

## 7. FEATURES DELIBERATELY NOT INCLUDED

| Candidate | Reason for exclusion |
|---|---|
| Token-level entropy from model logits | Not available (no API access, OAuth only) |
| Embedding-based semantic similarity | Requires a separate embedding model. Out of scope for Phase 0. |
| Full dependency parse / POS tagging | Over-engineered. spaCy adds a heavy dependency for marginal gain. Regex-based extraction is sufficient for the precision we need. |
| Topic modeling (LDA) on reasoning text | 612 documents is too few for stable topics. Also, topic =/= uncertainty signal. |
| Sentiment analysis (VADER/TextBlob) | Generic sentiment tools are calibrated for product reviews, not code reasoning. Domain-specific patterns (Section L1-L4) are more appropriate. |
| Modal decomposition (Kratzer/Rubinstein) | Deferred to Phase 2 per design decision. The philosophical framework is sound but the implementation requires distinguishing epistemic from deontic modality, which regex cannot do reliably. If Tier 2 linguistic features show ANY signal, modal decomposition becomes the Tier 3 refinement. |
| Human annotation of uncertainty | Single labeler introduces systematic bias. User quote: "Are you suggesting that I annotate? That would introduce systemic doubt." |

---

## 8. DECISION PROCEDURE

After computing all correlations:

1. **If Block A structural features dominate (2+ significant, linguistic features not significant):** The signal is in behavioral structure, not language. Write the memo around this finding. It directly supports the Anthropic gap: behavioral STRUCTURE predicts action correctness even when linguistic CONTENT does not. This is the strongest research contribution.

2. **If Block B linguistic replacements work (1+ significant):** Sonnet's uncertainty IS expressed linguistically, just not in academic hedging vocabulary. The contribution is the domain-specific lexicon. Combine structural + linguistic in a multivariate model and report the AUC improvement.

3. **If nothing is significant after Bonferroni:** Check if anything survives FDR at q=0.10. If yes, report as suggestive. If no, the honest conclusion is that 73 tasks is underpowered OR that task-level uncertainty signals are too weak to detect with behavioral exhaust alone. This is still a valid negative result for the memo.

4. **If the random noise control IS significant:** The analysis pipeline has a bug. Stop and debug.

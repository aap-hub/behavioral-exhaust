# Tier 2 Feature Analysis Results

**Date:** 2026-03-28
**Dataset:** 73 unique tasks (36 pass, 37 fail), latest validated run per task. 2,258 state-modifying tool calls (583 with reasoning text, 33% mean coverage per task).
**Method:** Spearman rank correlations. Partial correlations control for `total_state_modifying_calls` (the task-length confound: failing tasks avg 22.9 calls vs 16.6 passing). Benjamini-Hochberg FDR at q=0.10 applied to partial p-values.
**Implementation:** `src/tier2_features.py`

---

## 1. HEADLINE RESULTS

**10 of 20 features survive BH FDR at q=0.10 after controlling for task length.** The random noise control is not significant (rho_partial = -0.076, p = 0.524), confirming the pipeline is not finding noise.

The strongest result is a surprise: **metacognitive_density** (rho_partial = +0.494, p < 0.0001). This is the density of self-correction markers ("actually", "wait", "hmm", "I see") in reasoning text. The raw correlation was +0.308 (p = 0.008); controlling for task length *increased* the effect to +0.494. This means the raw correlation was being **suppressed** by the confound: longer tasks (which fail more) also produce more metacognitive markers in absolute terms, but per-token density is dramatically higher in passing runs.

The second strongest pre-registered feature is **early_error_rate** (rho_partial = -0.372, p = 0.001). Errors in the first third of the trajectory predict failure. Late errors do not.

---

## 2. COMPREHENSIVE CORRELATION TABLE

Sorted by absolute partial rho. All partial correlations control for total_state_modifying_calls.

| # | Feature | Type | rho | p | rho_p | p_p | BH | Expected | Match |
|---|---------|------|-----|---|-------|-----|----|----------|-------|
| 1 | metacognitive_density | L | +0.308 | 0.008 | **+0.494** | <0.001 | * | positive | YES |
| 2 | total_state_modifying_calls | S | -0.038 | 0.751 | **-0.476** | <0.001 | * | negative | YES |
| 3 | tentative_density | L(D) | -0.230 | 0.050 | **-0.434** | <0.001 | * | negative | YES |
| 4 | fail_then_switch_rate | S | -0.175 | 0.139 | **-0.372** | 0.001 | * | positive | NO |
| 5 | early_error_rate | S(D) | -0.349 | 0.003 | **-0.372** | 0.001 | * | negative | YES |
| 6 | insight_density | L(D) | +0.308 | 0.008 | **+0.315** | 0.007 | * | positive | YES |
| 7 | instead_contrast_density | L | +0.120 | 0.312 | **+0.300** | 0.010 | * | positive | YES |
| 8 | mean_edit_expansion | S(D) | +0.276 | 0.018 | +0.265 | 0.024 | * | positive | YES |
| 9 | error_rate | S(D) | -0.285 | 0.015 | -0.257 | 0.028 | * | negative | YES |
| 10 | reasoning_to_action_alignment | I | +0.138 | 0.246 | -0.232 | 0.049 | * | positive | **NO** |
| 11 | first_edit_position | S | +0.191 | 0.105 | +0.169 | 0.154 | | positive | YES |
| 12 | causal_density | L | -0.032 | 0.789 | -0.151 | 0.202 | | positive | NO |
| 13 | recovery_rate | S | -0.142 | 0.232 | -0.146 | 0.219 | | positive | NO |
| 14 | unique_files_touched | S | -0.134 | 0.260 | -0.140 | 0.238 | | negative | YES |
| 15 | wrong_stuck_density | L | -0.133 | 0.261 | -0.134 | 0.257 | | negative | YES |
| 16 | self_directive_density | L | -0.086 | 0.470 | -0.083 | 0.486 | | negative | YES |
| 17 | random_noise | ctrl | -0.105 | 0.375 | -0.076 | 0.524 | | null | ctrl |
| 18 | test_run_count | S | -0.101 | 0.394 | -0.047 | 0.696 | | positive | NO |
| 19 | edit_churn_rate | S | +0.043 | 0.719 | +0.046 | 0.697 | | negative | NO |
| 20 | precision_naming_score | L | +0.051 | 0.670 | +0.042 | 0.726 | | positive | YES |

Legend: S = structural, L = linguistic, I = interaction, (D) = discovered during exploration, * = survives BH FDR q=0.10.

---

## 3. PRE-REGISTRATION SCORECARD

### Direction Predictions (raw rho)
- **8/13 pre-registered features** in the expected direction (62%)
- If restricted to features with |rho| > 0.10: 7/10 correct (70%)
- Baseline (coin flip): 50%

### Wrong Directions (noteworthy failures)
1. **recovery_rate** (expected positive, got -0.142): Agents that "recover" from errors more frequently do NOT succeed more. Possible explanation: recovery_rate is high when there are many easy errors to recover from (e.g., pip install failures), which are noise.
2. **fail_then_switch_rate** (expected positive, got -0.175, -0.372 partial): Switching tools after an error is associated with FAILURE, not success. This contradicts the "adaptive diagnosis" hypothesis. Possible explanation: tool-switching after failure reflects undirected flailing, not strategic diagnosis. Successful agents may retry the same tool with corrections rather than switching.
3. **test_run_count** (expected positive, got -0.101): More test runs do NOT predict success. Test count correlates with task length, and mean-aggregation removed the expected signal.
4. **causal_density** (expected positive, got -0.032 raw, -0.151 partial): Causal connectives are not predictive. "Because" and "since" are too common in all reasoning.

### Null Hypothesis Controls (all confirmed)
- **hedging_score** (Hyland): Not tested (already demonstrated dead at rho=-0.122 in Tier 1)
- **random_noise**: rho_partial = -0.076, p = 0.524. NOT significant. Pipeline is clean.

---

## 4. KEY DISCOVERIES FROM DATA EXPLORATION

### Discovery 1: "Actually" is the Strongest Single-Word Predictor
**rho = +0.330, p = 0.004** (single word, per-token density)

"Actually" appeared in 11 passing-run reasoning blocks and only 3 failing-run blocks. Qualitative inspection reveals WHY: "actually" in Sonnet's reasoning marks a **course correction based on evidence**. Examples from passing runs:

- "But actually, `can_use_none_as_rhs` specifically allows `None`, not other non-booleans."
- "Actually, re-reading the code: `self.args` and `self.kwargs` are the original ones..."
- "Actually, I should also deduplicate in the display to avoid showing duplicate paths"
- "Actually, the cleanest fix is to wrap `expr_bot` in a way that forces proper parenthesization."

Every instance shows the agent **revising its plan after reading code/results**. This is not hesitation -- it is evidence-driven self-correction. In failing runs, "actually" appears in more confused contexts: "Actually, the real issue is different..."

**Implication:** "Actually" operationalizes faithful metacognition in Sonnet. When the model says "actually" and changes course, it is responding to evidence, which predicts success.

### Discovery 2: "I Understand" Predicts Success
**rho = +0.251, p = 0.032** (phrase density)

Combined "insight moments" -- "I understand", "Now I understand", "actually", "the issue/problem/bug is" -- form the strongest composite feature: **insight_density rho_partial = +0.315, p = 0.007**.

These phrases mark the moment the agent declares a diagnosis. Passing agents reach this declaration; failing agents often never do, instead narrating process ("let me check", "let me try") without arriving at understanding.

### Discovery 3: "Let Me Try" is the Strongest Failure Marker
**rho = -0.230, p = 0.050** (phrase density)

"Let me try" appeared in 2 passing and 11 failing reasoning blocks (5.5x ratio). In context, "let me try" signals the agent is **experimenting without a hypothesis**: "Let me try a more targeted approach", "Let me try running with --assert=plain". This is distinct from "let me check" (which appeared 1.5x more in passes) -- checking is verification, trying is guessing.

Combined with other tentative markers ("maybe", "not sure", "try another"), **tentative_density** has rho_partial = -0.434 (p < 0.001).

### Discovery 4: Early Errors Matter, Late Errors Don't
**early_error_rate rho = -0.349, p = 0.003** (strongest raw structural feature)
**mid_error_rate rho = -0.302, p = 0.010**
**late_error_rate rho = -0.085, p = 0.473** (not significant)

Errors in the first third of the trajectory (setup failures, import errors, wrong file paths) predict overall failure. Late errors do not -- by the late stage, the agent has either found the fix or is just running final verification (where a test failure is expected and correctable).

This creates a natural asymmetry: early errors indicate the agent is struggling with the environment or problem setup. The agent that navigates setup cleanly has already demonstrated a form of competence.

### Discovery 5: Edit Expansion Size Predicts Success
**mean_edit_expansion rho = +0.276, p = 0.018** (edit calls where new_string > old_string)

Passing agents make LARGER code additions (mean expansion pass=473 chars vs fail=361 chars). This likely reflects that successful fixes are often additive (adding missing logic, new test cases, import statements) while unsuccessful fixes are more often small tweaks that miss the root cause.

Raw edit size stats:
- PASS edits: old=289 chars, new=473 chars, new/old ratio median=1.31
- FAIL edits: old=263 chars, new=361 chars, new/old ratio median=1.21

### Discovery 6: The Task-Length Confound Was Suppressing Linguistic Signals

The single most important methodological finding: controlling for task length via partial correlation **dramatically changed** the results.

| Feature | Raw rho | Partial rho | Change |
|---------|---------|-------------|--------|
| metacognitive_density | +0.308 | +0.494 | +0.186 |
| tentative_density | -0.230 | -0.434 | -0.204 |
| instead_contrast_density | +0.120 | +0.300 | +0.180 |
| total_state_modifying_calls | -0.038 | -0.476 | -0.438 |

Why: Failing tasks are longer. Longer tasks produce more reasoning text. More text means more total metacognitive markers, tentative phrases, etc. in absolute terms. But per-token density (mean aggregation) already partially controls for within-task length. The partial correlation additionally controls for between-task length variation, removing the remaining confound.

`total_state_modifying_calls` itself goes from rho=-0.038 (insignificant) to rho_partial=-0.476 (p<0.001). This means task length IS a strong predictor of failure, but only after you partial out the other features. By itself, it is not significant because the other features already carry the signal.

---

## 5. FEATURE INTERCORRELATION MATRIX

Top features are largely independent (low intercorrelation):

| | metacog | r_t_a_align | first_edit | wrong_stuck |
|---|---------|-------------|------------|-------------|
| early_error_rate | -0.212 | +0.073 | -0.301 | +0.119 |
| metacognitive_density | -- | +0.109 | +0.089 | -0.056 |
| reasoning_to_action_alignment | -- | -- | -0.140 | -0.046 |
| first_edit_position | -- | -- | -- | +0.102 |

The only moderate correlation is early_error_rate x first_edit_position (-0.301), which is expected: early errors delay the first edit.

---

## 6. STRUCTURAL PATTERNS NOT CAPTURED BY FEATURES

### 6.1 Error Types Are Mostly Infrastructure Noise
Examining tool_result_json content for is_error=True calls: the majority are `pip install` failures, `command not found: python` errors, and `pytest` import issues. These are environment setup problems, not reasoning errors. A refined version of error_rate should distinguish "infrastructure errors" (pip, command not found, import errors) from "reasoning errors" (test failures, Edit failures on wrong file).

### 6.2 Mid-Trajectory Error Spike in Failing Runs
Error rates by trajectory third:
- PASS: early=10.6%, mid=10.4%, late=8.6% (flat/declining)
- FAIL: early=12.8%, mid=17.9%, late=11.8% (mid-trajectory spike)

The mid_error_spike feature (mid rate minus average of early+late) was rho=-0.171 (p=0.148), not significant, but the pattern is real. A larger sample might reveal this. The spike likely corresponds to the "implementation attempt" phase where failing agents make incorrect edits and fail tests.

### 6.3 Tool Transition Patterns Are Not Predictive
bash_to_edit, edit_to_bash, edit_to_edit, bash_to_bash transition rates all have |rho| < 0.10. The hypothesis that successful agents have distinct phase transitions (explore -> implement -> verify) is not supported at this sample size. The DIV (diagnose-implement-verify) score from the framework would likely also be null.

### 6.4 Pacing (Seconds Per Call) Is Not Predictive
wall_clock_seconds/calls shows no signal (rho=-0.047). Note: tool_calls timestamps are parse-time artifacts (all within the same second), so inter-call timing cannot be extracted. Wall clock time per call from runs-level data also shows no signal.

---

## 7. FEATURES THAT FAILED

| Feature | rho_partial | Why it failed |
|---------|-------------|---------------|
| precision_naming_score | +0.042 | Backticks, CamelCase, snake_case, and file paths are ubiquitous in ALL reasoning (57% of pass calls, 53% of fail calls have backticks). The per-token density barely differs. |
| causal_density | -0.151 | "Because" and "since" are common discourse connectives used for explanation in both pass and fail. The hypothesis that causal language = diagnosis was wrong: narrating causal chains is part of general Sonnet style, not a success marker. |
| recovery_rate | -0.146 | Recovery from errors is dominated by infrastructure errors (pip failures, env issues) which are easy to recover from. Recovery from substantive errors (wrong edit, failed test) might carry signal but is swamped by noise. |
| test_run_count | -0.047 | After controlling for task length, test count has zero signal. All agents run tests; the question is whether the tests pass, not how many times they run. |
| edit_churn_rate | +0.046 | Re-editing files is normal iterative development, not a failure signal. |

---

## 8. DECISION PROCEDURE OUTCOME

Referencing Section 8 of the framework:

**Outcome: Combination of 1 and 2.** Both structural and linguistic features are significant, but linguistic features dominate after task-length correction.

- Block A structural: early_error_rate survives Bonferroni (rho=-0.349, p_raw=0.003, p_bonf=0.047). But most structural features are null.
- Block B linguistic replacements: metacognitive_density is the strongest overall feature (rho_partial=+0.494). tentative_density and instead_contrast_density also survive.
- Discovered features (insight_density, tentative_density, early_error_rate, error_rate, mean_edit_expansion) add substantial value beyond the pre-registered set.

**The primary research finding:** Sonnet's uncertainty IS expressed linguistically, but through domain-specific metacognitive markers ("actually", "I understand", "wait"), not academic hedging vocabulary. The Hyland lexicon failure at Tier 1 was a measurement problem, not a signal-absence problem. The signal exists; it requires the right operationalization.

**Secondary finding:** The task-length confound is critical. Failing tasks are 38% longer (22.9 vs 16.6 calls). Any analysis using sum aggregation or raw correlations will either miss real signals (metacognitive_density suppressed from +0.308 to +0.494) or find spurious ones.

---

## 9. RECOMMENDATIONS FOR PHASE 1

1. **Feature set for gating model:** metacognitive_density, tentative_density, early_error_rate, insight_density, error_rate, instead_contrast_density, mean_edit_expansion (7 features, all with |rho_partial| > 0.25).

2. **Task-length normalization:** Any gating model MUST include total_state_modifying_calls as a covariate or use per-token/per-call normalization.

3. **"Actually" as a trust signal:** When the agent says "actually" followed by a course correction, that specific moment has high positive predictive value for task success. This could be a simple, interpretable gating rule.

4. **"Let me try" as a warning signal:** When the agent shifts to tentative/experimental language, this predicts failure. A gate could request more information or prompt for a specific hypothesis before allowing the action.

5. **Early error monitoring:** Errors in the first third of the trajectory are a strong negative signal. A gate could intervene early to provide environment setup assistance.

---

## 10. UNRESOLVED QUESTIONS

1. **Is "actually" a faithful signal?** The Chen et al. finding that 75% of CoT is unfaithful would predict that "actually" is performance, not genuine correction. But the correlation with success suggests it IS functional -- the agent genuinely revises its approach when it says "actually". This needs Phase 1 testing: does gating on "actually" moments actually improve outcomes?

2. **Why do recovery_rate and fail_then_switch_rate go opposite to expectation?** Both measure "adaptive behavior after failure" and both are NEGATIVE. The data suggests that "adaptation" after errors is more often flailing than diagnosis. The successful pattern is not "try something different" but "get it right the first time."

3. **Is insight_density causally upstream of success, or an epiphenomenon?** Agents that understand the problem say "I understand" AND write correct fixes. The correlation might be: understanding -> correct fix AND understanding -> "I understand" declaration. The declaration does not cause the fix. But for gating purposes, the declaration is still a useful signal of the agent's internal state.

4. **Will these features generalize beyond SWE-bench-lite on Sonnet?** The lexicon is empirically derived from Sonnet 4.6's coding behavior. Different models (Opus, GPT-4, Gemini) may use different metacognitive markers. The framework should be model-specific.

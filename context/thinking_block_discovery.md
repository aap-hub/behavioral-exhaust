# Thinking Block Feature Discovery

**Date:** 2026-03-28
**Source:** Internal thinking blocks from Sonnet's extended-thinking content
**Dataset:** 73 runs (latest per task) with thinking content. 40 pass, 33 fail.
**Total thinking content:** ~680K chars across 73 runs (avg 9.3K chars/run)
**Method:** Point-biserial correlation (r_pb) of feature values with binary task_success.

---

## 0. WHY THIS MATTERS

All prior Tier 2 features were extracted from **agent messages** (the text the agent writes as part of its visible response). The parser never touched the `thinking` blocks inside `assistant` events. These blocks contain the model's *internal* reasoning -- invisible to the user, not part of the action stream. This is 10x richer content that was sitting in the DB unanalyzed.

The thinking content is qualitatively different from agent messages:
- Agent messages are performative (addressed to the user/system)
- Thinking blocks are deliberative (the model reasoning to itself)
- Thinking blocks contain hypothesis formation, causal tracing, self-doubt, plan formation, and strategy pivots that never appear in messages

Extraction method:
```python
for line in raw_stream_json.split("\n"):
    ev = json.loads(line)
    if ev.get("type") == "assistant":
        for block in ev.get("message",{}).get("content",[]):
            if block.get("type") == "thinking":
                thinking_text = block.get("thinking", "")
```

---

## 1. SIGNIFICANT FEATURES (p < 0.05)

Sorted by absolute r_pb. All features are NEW -- not present in the Tier 2 feature set.

| # | Feature | r_pb | p | Pass mean | Fail mean | Direction |
|---|---------|------|---|-----------|-----------|-----------|
| 1 | compat_fraction | -0.406 | 0.0002 | 0.036 | 0.174 | fail-predictive |
| 2 | env_distraction_fraction | -0.374 | 0.0007 | 0.003 | 0.020 | fail-predictive |
| 3 | pivots_per_kchar | -0.359 | 0.0012 | 0.115 | 0.602 | fail-predictive |
| 4 | approach_pivots | -0.325 | 0.0038 | 0.550 | 3.455 | fail-predictive |
| 5 | focus_score (composite) | +0.278 | 0.0146 | 2.236 | 0.370 | pass-predictive |
| 6 | func_refs_per_kchar | +0.253 | 0.0278 | 1.129 | 0.209 | pass-predictive |
| 7 | env_sentence_fraction | -0.238 | 0.0391 | 0.081 | 0.174 | fail-predictive |
| 8 | compat_struggle_markers | -0.236 | 0.0408 | 0.775 | 2.364 | fail-predictive |
| 9 | dead_end_count | -0.231 | 0.0454 | 0.025 | 0.182 | fail-predictive |

## 2. MARGINAL FEATURES (p < 0.10)

| # | Feature | r_pb | p | Pass mean | Fail mean | Direction |
|---|---------|------|---|-----------|-----------|-----------|
| 10 | backtracking | -0.219 | 0.0581 | 0.675 | 1.545 | fail-predictive |
| 11 | fix_mention_position | +0.214 | 0.0649 | 0.667 | 0.497 | pass-predictive |

## 3. NON-SIGNIFICANT FEATURES (tested and rejected)

| Feature | r_pb | p | Notes |
|---------|------|---|-------|
| self_corrections_per_block | -0.191 | 0.10 | "Wait" / "Actually" per block. Trending but not significant. |
| premature_confidence | -0.122 | 0.30 | "simple fix" / "straightforward". Too rare (n < 10 total). |
| total_thinking_chars | +0.000 | 0.99 | Thinking length does NOT predict success at all. |
| avg_block_length | +0.001 | 0.99 | Nor does block length. |
| num_thinking_blocks | -0.127 | 0.28 | More blocks = slightly worse, but not significant. |
| understanding_declarations | -0.010 | 0.93 | "Now I understand" is noise. |
| plan_statements | +0.010 | 0.93 | "I need to" is noise. |
| causal_hypotheses | -0.061 | 0.61 | Naming causes doesn't help. |
| epistemic_markers | -0.018 | 0.88 | "I think" / "I believe" is noise. |
| backtick_code_refs | -0.008 | 0.95 | Raw code references mean nothing. |
| first_block_vague | +0.095 | 0.42 | Whether first block starts vague doesn't predict. |
| first_block_specific | -0.059 | 0.62 | Whether first block starts specific doesn't predict. |

---

## 4. FEATURE DEFINITIONS AND EXTRACTION

### 4.1 compat_fraction (r = -0.406, p = 0.0002)

**What it measures:** Fraction of thinking characters devoted to compatibility/environment issues (Python version mismatches, deprecated imports, build failures).

**Extraction:**
```python
compat_sentences = re.findall(
    r'[^.]*(?:compat|version|install|deprecated|removed|Python 3\.\d+)[^.]*\.',
    text, re.I)
compat_fraction = sum(len(s) for s in compat_sentences) / total_chars
```

**Why it works:** When the agent's thinking is dominated by environment problems (Python 3.10 removing `collections.Mapping`, Cython build failures, missing `pkg_resources`), it cannot focus on the actual bug. This is the single strongest thinking-block predictor.

**Example (FAIL, sympy__sympy-11870):**
> "The `collections.Mapping` was removed in Python 3.10... This version of SymPy has compatibility issues with modern Python... Let me try to use Python 3.9 or fix the code to work."

**Example (PASS, sympy__sympy-13895):**
> "Now I understand the issue. Looking at `as_numer_denom()` in `power.py`: The code handles the case where the denominator's sign is unknown (lines 1185-1187), but it doesn't handle the case where the numerator's sign is unknown."

### 4.2 env_distraction_fraction (r = -0.374, p = 0.0007)

**What it measures:** Character-level fraction of thinking devoted to environment setup keywords (pip, install, docker, virtualenv, setuptools, ImportError, etc.).

**Extraction:**
```python
env_patterns = r'(?:pip|install|docker|virtualenv|venv|conda|setuptools|' \
               r'pkg_resources|collections\.Mapping|compatibility|deprecated|' \
               r'removed in|can\'t compile|can\'t build|not available|' \
               r'ImportError|ModuleNotFoundError)'
env_chars = sum(len(m.group()) for m in re.finditer(env_patterns, text, re.I))
env_distraction_fraction = env_chars / total_chars
```

**Distinction from compat_fraction:** This is a tighter, keyword-level measure. compat_fraction captures whole sentences; this captures specific technical keywords. Both are significant, suggesting the signal is robust to extraction method.

### 4.3 pivots_per_kchar (r = -0.359, p = 0.0012)

**What it measures:** Rate of strategy changes per 1000 characters of thinking. Matches phrases like "different approach", "let me try a different", "a simpler approach", "instead, let me".

**Extraction:**
```python
pivots = re.findall(
    r'(?:different approach|try (?:a )?(?:different|another)|'
    r'instead,? (?:I\'ll|let me)|let me try|'
    r'a (?:simpler|better|different) (?:approach|way|method|strategy))',
    text, re.I)
pivots_per_kchar = len(pivots) / (total_chars / 1000)
```

**Why it works:** Frequent strategy pivots signal the agent is flailing -- it hasn't locked onto the root cause and is thrashing between approaches. This is the PIVOT SPIRAL pattern.

**Example (FAIL, scikit-learn-15535, 22 pivots across 35 blocks):**
> Block 4: "Let me try with Python 3.11..."
> Block 5: "Let me try to build it first..."
> Block 6: "Let me try a different approach..."
> Block 7: "Let me try a different approach - just test the specific logic by copying..."
> Block 9: "Let me try a different approach - import the specific module..."

**Example (PASS, django__django-14999, 0 pivots across 10 blocks):**
Agent identified the issue in block 2, stated the fix clearly, and executed it without ever needing to change strategy.

### 4.4 approach_pivots (r = -0.325, p = 0.0038)

**What it measures:** Raw count of strategy changes (same regex as pivots_per_kchar but unnormalized).

**Pass mean: 0.55 pivots. Fail mean: 3.46 pivots.** Failing runs have 6.3x more pivots.

### 4.5 focus_score (r = +0.278, p = 0.0146)

**What it measures:** Composite score combining code-structure references (positive), environment distraction (negative), and pivot rate (negative).

**Extraction:**
```python
code_structure = len(re.findall(
    r'\b(?:method|class|module|function|constructor|property|attribute)\b',
    text, re.I))
focus_score = (code_structure / kchars) - (env_distraction_fraction * 10) - (pivots_per_kchar * 2)
```

**Why it works:** Measures whether the agent's thinking is oriented toward the codebase (methods, classes, functions) vs toward the environment (pip, install, compatibility). A composite that captures the "where is the agent's attention?" question.

### 4.6 func_refs_per_kchar (r = +0.253, p = 0.0278)

**What it measures:** Density of function-call references (pattern: `word()`) per 1000 chars of thinking.

**Extraction:**
```python
func_refs = re.findall(r'\b\w+\(\)', text)
func_refs_per_kchar = len(func_refs) / (total_chars / 1000)
```

**Why it works:** When the agent names specific functions in its thinking, it is engaging with the actual codebase at the level of concrete implementation details. This is diagnostic precision -- the agent is reasoning about specific code artifacts rather than vague generalities.

**Within-sympy validation:** Pass mean 1.81 vs fail mean 0.23 (ratio 7.95x). This is not a project-level confound.

**Example (PASS, sympy__sympy-16503):** References `next()`, `pretty()`, `above()`, `right()`, `splitlines()`, `width()`, `height()`, `stack()`, `below()` -- concrete SymPy pretty-printer internals.

### 4.7 dead_end_count (r = -0.231, p = 0.0454)

**What it measures:** Explicit recognition of dead ends in thinking. Matches "this approach won't work", "I can't find/get/make", "there's no way to".

**Extraction:**
```python
dead_ends = re.findall(
    r'(?:this (?:approach|method|strategy) (?:won\'t|doesn\'t|can\'t|isn\'t)|'
    r'that (?:won\'t|doesn\'t) work|'
    r'I (?:can\'t|cannot) (?:find|get|make|run)|'
    r'there(?:\'s| is) no way to)',
    text, re.I)
```

**Why it works:** Dead-end recognition is a sign that the agent has been trying approaches and hitting walls. Pass runs almost never hit dead ends (mean 0.025); fail runs hit them occasionally (mean 0.182).

### 4.8 backtracking (r = -0.219, p = 0.058)

**What it measures:** Explicit direction changes: "let me reconsider", "let me rethink", "I'm getting sidetracked", "I was wrong".

**Pass mean: 0.68. Fail mean: 1.55.** Marginally significant.

### 4.9 fix_mention_position (r = +0.214, p = 0.065)

**What it measures:** Where in the thinking text the agent first mentions "the fix" or "I need to fix". Expressed as fraction of total text (0 = beginning, 1 = never mentioned).

**Counterintuitive result:** Pass runs mention fixes LATER (0.67) than fail runs (0.50). This likely means pass runs spend more proportional time understanding the problem before jumping to fixes, while fail runs jump to "the fix is X" prematurely without full understanding.

---

## 5. CONFOUND ANALYSIS

### 5.1 Is compat_fraction just a project proxy?

The strongest features (compat_fraction, env_distraction) could be confounded with project: sympy tasks have Python version issues that django tasks don't.

**Within-sympy check (n=30, 11 pass, 19 fail):**
- compat_fraction: pass=0.007, fail=0.169. The signal holds WITHIN sympy. It's not just "sympy tasks fail more." It's "sympy tasks where the agent gets stuck on compatibility issues fail more."

**Within-pytest check (n=8, 2 pass, 6 fail):**
- Similar pattern: high compat fractions cluster in failures.

### 5.2 Does func_refs_per_kchar hold within projects?

**Within-sympy:** pass=1.81, fail=0.23 (ratio 7.95x). Extremely strong within-project signal.

### 5.3 Excluding high-compat tasks entirely

After removing all runs with compat_fraction >= 0.05 (n=48, 34 pass, 14 fail):
- func_refs_per_kchar: pass=1.23, fail=0.30. Still strong.
- self_corrections: pass=3.44, fail=5.93. Still directional.
- The pivot features wash out (pass=0.35, fail=0.43), confirming that pivots are partly driven by compat struggles.

### 5.4 Total thinking length is NOT a confound

total_thinking_chars has r_pb = 0.000, p = 0.997. Pass and fail runs produce the same amount of thinking text on average. The features above are measuring thinking QUALITY, not quantity.

---

## 6. RELATIONSHIP TO TIER 2 FEATURES

The Tier 2 features were extracted from **agent messages** (visible text). The thinking-block features are extracted from **internal thinking** (invisible deliberation). Key comparisons:

| Tier 2 Feature | Thinking Feature | Relationship |
|----------------|-----------------|--------------|
| metacognitive_density (+0.494) | self_corrections_per_block (-0.191) | OPPOSITE direction. "Wait/Actually" in messages = good. In thinking = bad (trending). The same words mean different things in different contexts. |
| tentative_density (-0.434) | N/A | No thinking-block analog found. |
| insight_density (+0.315) | understanding_declarations (-0.010) | "Now I understand" in thinking is noise. insight_density in messages captured something different. |
| N/A | compat_fraction (-0.406) | NEW. No Tier 2 analog. This is purely a thinking-block phenomenon. |
| N/A | pivots_per_kchar (-0.359) | NEW. Strategy pivots only visible in internal deliberation. |
| N/A | func_refs_per_kchar (+0.253) | NEW. Diagnostic precision at the function level. |

**Critical finding:** metacognitive_density in messages (r=+0.494) vs self_corrections in thinking (r=-0.191) run in OPPOSITE directions. The same linguistic markers ("Wait", "Actually") are positive in messages but trending negative in thinking. Possible explanation: in messages, self-corrections are performed for the user and reflect genuine course-correction after acting. In thinking, they reflect pre-action confusion and indecision.

---

## 7. KEY QUALITATIVE PATTERNS

### 7.1 The Pivot Spiral (fail pattern)

Failed runs exhibit a distinctive pattern where the agent cycles through approaches without converging:
1. Try approach A --> environment error
2. "Let me try a different approach" --> approach B
3. B also fails --> "Let me try another approach" --> approach C
4. C fails --> "different approach"...

The agent's thinking gets consumed by logistics rather than understanding. In the worst case (scikit-learn-15535), 15 of 35 thinking blocks contain pivot statements.

### 7.2 The Diagnostic Lock (pass pattern)

Successful runs show a pattern where the agent "locks on" to the root cause early and maintains focus:
1. Read the problem description
2. Identify the specific function/method/line responsible
3. Trace the logic through the code
4. Formulate the fix
5. Execute without strategy changes

In sympy-13895 (pass), block 4 contains: "Now I understand the issue. Looking at `as_numer_denom()` in `power.py`: The code handles the case where the denominator's sign is unknown (lines 1185-1187), but it doesn't handle the case where the numerator's sign is unknown." This block names the specific function, specific lines, and the specific logical gap.

### 7.3 The Premature Fix (marginal fail pattern)

fix_mention_position runs opposite to naive intuition: pass runs mention fixes LATER. This suggests that jumping to "the fix is straightforward" before deeply understanding the problem is a failure mode, not efficiency.

---

## 8. RECOMMENDED ADDITIONS TO FEATURE PIPELINE

Priority features to add to `src/tier2_features.py`:

1. **compat_fraction** -- Extract from thinking blocks. Strongest single predictor.
2. **pivots_per_kchar** -- Extract from thinking blocks. Novel and strong.
3. **func_refs_per_kchar** -- Extract from thinking blocks. Best pass-predictive feature.
4. **focus_score** -- Composite. Good candidate for gate feature.
5. **dead_end_count** -- Binary-ish feature, easy to threshold for gating.

These should be added as a separate extraction pass since they require parsing thinking blocks (currently not done by the Tier 2 pipeline).

---

## 9. IMPLICATIONS FOR GATING

The thinking-block features suggest a complementary gating strategy:

- **Real-time monitoring:** If the agent's thinking starts accumulating compat/env keywords (compat_fraction rising), the gate should intervene early rather than letting the pivot spiral develop.
- **Pivot detection:** If pivots_per_kchar exceeds ~0.3, the run is likely failing. This could trigger a "stop and reassess" intervention.
- **Diagnostic quality check:** func_refs_per_kchar below ~0.5 in thinking suggests the agent hasn't engaged with the actual codebase. This is a gate candidate.

The composite focus_score could serve as a single real-time metric: positive = on track, negative = off track.

---

## 10. LIMITATIONS

1. **n=73.** Small sample. Features should be validated on held-out data.
2. **Compat confound partially addressed.** Within-project checks confirm the signal, but the proportion of compat-heavy tasks in the corpus inflates effect sizes.
3. **No causal claim.** These are correlational. The pivot spiral could be a symptom (task is hard) rather than a cause (agent is flailing). However, the within-project signal (same repo, different tasks, different outcomes) argues against pure task-difficulty confounding.
4. **Extraction is regex-based.** More sophisticated NLP (embedding similarity, topic models) could find additional features. The current approach privileges interpretability.
5. **Missing thinking blocks.** 1 of 74 latest-per-task runs had no thinking content (p0-smoke-feature-01, which passed). Some tasks may use non-thinking models.

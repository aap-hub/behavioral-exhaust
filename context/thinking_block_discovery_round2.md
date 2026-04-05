# Thinking Block Feature Discovery -- Round 2

**Date:** 2026-03-28
**Source:** Internal thinking blocks from extended-thinking content
**Dataset:** 76 runs (latest per task) with thinking content. 41 pass, 35 fail.
**Method:** Point-biserial correlation (r_pb) with binary task_success. Confound analysis via within-project checks and orthogonality to Round 1 features. Multivariate comparison via logistic regression with 5-fold CV.
**Predecessor:** `context/thinking_block_discovery.md` (Round 1, 9 features)

---

## 0. WHAT ROUND 1 FOUND (AND WHAT IT MISSED)

Round 1 discovered 9 features, mostly clustered around two phenomena:
1. **Environment struggle** -- compat_fraction, env_distraction, env_sentence_fraction, compat_struggles
2. **Strategy thrashing** -- pivots_per_kchar, approach_pivots, dead_ends, backtracking
3. **Code engagement** -- func_refs_per_kchar, focus_score (composite)

These are all valuable but they mostly answer one question: "Is the agent fighting the environment or flailing between approaches?" They miss:
- **Diagnostic precision** -- HOW specifically does the agent identify root causes?
- **Temporal dynamics** -- Does thinking get MORE or LESS focused over the trajectory?
- **Self-correction patterns** -- Are mid-thought corrections (Actually/Wait) informative?
- **Evidence engagement** -- Does the agent quote actual errors or paraphrase vaguely?
- **Structural markers** -- Do formatting patterns in thinking (dashes, narratives) predict outcomes?

Round 2 finds 11 features addressing these gaps. **7 are significant (p < 0.05), 4 are marginal (p < 0.10).** The combined Round 1 + Round 2 model achieves AUC = 0.833 (5-fold CV), vs 0.733 for Round 1 alone.

---

## 1. SIGNIFICANT FEATURES (p < 0.05)

| # | Feature | r_pb | p | Pass mean | Fail mean | Direction |
|---|---------|------|---|-----------|-----------|-----------|
| 1 | reasoning_clarity | +0.385 | 0.0006 | 0.900 | -0.888 | pass-predictive |
| 2 | confusion_score | -0.335 | 0.0031 | 0.939 | 2.186 | fail-predictive |
| 3 | dash_density | -0.298 | 0.0088 | 0.272 | 0.832 | fail-predictive |
| 4 | diagnostic_precision | +0.254 | 0.0266 | 1.839 | 1.298 | pass-predictive |
| 5 | actually_density | -0.253 | 0.0276 | 0.194 | 0.407 | fail-predictive |
| 6 | code_path_density | +0.246 | 0.0321 | 0.798 | 0.186 | pass-predictive |
| 7 | error_quote_density | +0.238 | 0.0385 | 0.735 | 0.265 | pass-predictive |

## 2. MARGINAL FEATURES (p < 0.10)

| # | Feature | r_pb | p | Pass mean | Fail mean | Direction |
|---|---------|------|---|-----------|-----------|-----------|
| 8 | progressive_understanding | +0.223 | 0.0526 | 2.815 | 0.260 | pass-predictive |
| 9 | interruption_rate | -0.222 | 0.0534 | 0.308 | 0.522 | fail-predictive |
| 10 | specificity_gain | +0.210 | 0.0685 | 2.988 | 0.628 | pass-predictive |
| 11 | narrative_fraction | -0.203 | 0.0783 | 0.201 | 0.305 | fail-predictive |

---

## 3. FEATURE DEFINITIONS AND EXTRACTION

### 3.1 reasoning_clarity (r = +0.385, p = 0.0006) -- COMPOSITE

**What it measures:** Net quality of reasoning, computed as diagnostic_precision minus confusion_score. Positive values mean the agent's thinking contains more code-specific reasoning than self-corrections and pivots; negative values mean confusion dominates.

**Extraction:**
```python
reasoning_clarity = diagnostic_precision - confusion_score
```

**Why it works:** This is the single strongest Round 2 predictor and captures the core finding: successful agents reason about code artifacts (functions, files, line numbers, code paths) while failing agents reason about their own process (corrections, pivots, interruptions). The pass mean is +0.900 (precision exceeds confusion); the fail mean is -0.888 (confusion exceeds precision). The sign flip across the success boundary is the key signal.

**Within-project validation:**
- Sympy (n=29): r = +0.457, p = 0.013 -- significant
- Django (n=24): r = +0.296, p = 0.161 -- directionally consistent, underpowered

### 3.2 confusion_score (r = -0.335, p = 0.0031) -- COMPOSITE

**What it measures:** Aggregate indicator of reasoning confusion. Sums four components:
1. `actually_density` -- sentence-initial "Actually" corrections per kchar
2. `interruption_rate` -- "Actually/Wait/Hmm/Oh/Ah" at sentence boundaries per kchar
3. `pivots_per_kchar` -- strategy change phrases per kchar (from Round 1)
4. `rediagnosis` -- binary flag: 1 if "the issue/problem is" appears 3+ times

**Extraction:**
```python
actually_pk = count(r'(?:^|\n|(?<=\.\s))Actually\b') / kchars
interrupt_pk = count(r'(?:^|\n|(?<=\.\s))(?:Actually|Wait|Hmm|Oh|Ah)\b') / kchars
pivots_pk = # (same regex as Round 1)
rediag = 1 if count('the issue/problem is') >= 3 else 0
confusion_score = actually_pk + interrupt_pk + pivots_pk + rediag
```

**Why it works:** Failing agents exhibit a distinctive pattern of repeatedly correcting themselves mid-thought, interrupting their own reasoning, and re-stating the diagnosis. A confusion_score above 2.0 strongly predicts failure (fail mean = 2.186).

**Distinction from Round 1:** Round 1's `pivots_per_kchar` captures only strategy thrashing. `confusion_score` adds self-corrections ("Actually"), self-interruptions ("Wait"), and re-diagnosis, which together paint a fuller picture of reasoning breakdown.

**Example (FAIL, scikit-learn-15535, confusion_score = 6.8):**
> "Actually, since the installed sklearn is 1.8.0 which is very different..."
> "Actually, a simpler approach: let me just look at what the test file imports..."
> "Actually let me trace the import chain more carefully..."
> "Actually, the test I wrote shows the fix works correctly."
> "Actually, let me think about this differently."
> "Wait, in the standalone script I have..."
> "Actually, the cleanest approach is to..."

22 "Actually" corrections across 35 blocks. The agent keeps correcting itself without converging.

**Example (PASS, django-14999, confusion_score = 0.4):**
Agent has two "Wait" moments that are productive -- each leads to a genuine insight, not a direction change.

### 3.3 dash_density (r = -0.298, p = 0.0088)

**What it measures:** Density of en-dash/em-dash separated phrases per 1000 chars of thinking. Matches `word - word`, `word -- word`, and unicode dash variants.

**Extraction:**
```python
dashes = re.findall(r'\w\s+[-\u2013\u2014]\s+\w', text)
dash_density = len(dashes) / kchars
```

**Why it works:** Dashes in thinking serve as inline pivots and asides. Manual categorization of 307 dash instances shows 30% are pivoting/redirecting ("let me try X - actually let me do Y"), with the remainder being parenthetical insertions that interrupt the logical flow. High dash density (fail mean = 0.832 vs pass mean = 0.272) indicates fragmented reasoning -- the agent is inserting qualifications, corrections, and alternative approaches inline rather than pursuing a single chain.

**Orthogonality:** r = +0.119 with compat_fraction (effectively independent). This is a genuine new signal, not a proxy for environment struggle.

**Example (FAIL, astropy-6938, dash_density = 1.67):**
> "Let me try to test the logic differently - I can directly test the fitsrec.py file"
> "Actually, let me try a different approach - import just the io/fits module directly"

**Example (PASS, django-15902, dash_density = 0.00):**
Agent uses complete sentences with no inline pivots. Clean linear reasoning.

### 3.4 diagnostic_precision (r = +0.254, p = 0.0266) -- COMPOSITE

**What it measures:** Average density of five code-specific reference types in thinking:
1. Function references (`word()` pattern)
2. File references (backtick-wrapped .py files)
3. Code path tracing (X calls/invokes/delegates to Y)
4. Line number references (`line 42`, `lines 185-187`)
5. Backtick identifiers (any `identifier` in backticks)

**Extraction:**
```python
diagnostic_precision = (
    func_refs_per_kchar +
    file_refs_per_kchar +
    code_path_density +
    line_refs_per_kchar +
    backtick_ids_per_kchar
) / 5
```

**Why it works:** When the agent's thinking names specific code artifacts at high density, it demonstrates engagement with the actual codebase rather than operating at the level of vague problem description. Pass mean (1.839) exceeds fail mean (1.298) by 42%.

**Within-sympy:** r = +0.352, p = 0.061 -- marginal, same direction. The signal is not merely a project-level confound.

### 3.5 actually_density (r = -0.253, p = 0.0276)

**What it measures:** Rate of sentence-initial "Actually" per 1000 chars of thinking. "Actually" at sentence boundaries indicates mid-thought correction -- the agent is reversing or modifying a claim it just made.

**Extraction:**
```python
actually_starts = re.findall(r'(?:^|\n|(?<=\.\s))Actually\b', text, re.M)
actually_density = len(actually_starts) / kchars
```

**Why it works:** "Actually" in thinking is NOT the same as "Actually" in agent messages. In messages, self-corrections are performative and correlate with success (metacognitive_density from Tier 2, r = +0.494). In thinking, "Actually" indicates genuine pre-action confusion -- the agent is changing its mind before it has even acted. This is the same word producing OPPOSITE signals depending on whether it appears in thinking vs messages.

**Pass mean: 0.194 per kchar. Fail mean: 0.407 per kchar.** Failing runs have 2.1x more mid-thought self-corrections.

**Within-sympy:** r = -0.378, p = 0.043 -- significant.

**Critical implication:** This confirms that thinking blocks contain qualitatively different signal from agent messages. The "same" linguistic marker has opposite polarity depending on context. Any feature extraction pipeline that conflates thinking and message text will miss or misattribute this signal.

### 3.6 code_path_density (r = +0.246, p = 0.0321)

**What it measures:** Density of code path tracing phrases per 1000 chars. Captures when the agent reasons about how code modules connect: "X calls Y", "from `module` to `handler`", "the flow goes from A to B".

**Extraction:**
```python
code_paths = re.findall(
    r'(?:\w+\s*(?:\u2192|->|=>|calls?|invokes?|delegates?\s+to)\s*\w+)|'
    r'(?:from\s+`\w+`\s+to\s+`\w+`)|'
    r'(?:the\s+(?:flow|chain|sequence)\s+(?:is|goes))',
    text, re.I
)
code_path_density = len(code_paths) / kchars
```

**Why it works:** This is the strongest Round 2 feature in terms of pass/fail ratio: 4.29x (pass = 0.798, fail = 0.186). When the agent traces code paths in its thinking, it is building a causal model of the bug rather than just pattern-matching on symptoms. This is what distinguishes diagnostic reasoning from symptomatic reasoning.

**Orthogonality:** r = -0.172 with compat_fraction. Largely independent of Round 1 features.

**Within-sympy:** r = +0.379, p = 0.042 -- significant.
**Within-pytest:** r = +0.824, p = 0.060 -- marginal (small n).
**Within-django:** r = +0.348, p = 0.096 -- marginal.

This is the most robust across-project feature in Round 2.

**Example (PASS, sympy-13895):**
> "Now I'm tracing through the power simplification: when we have `(-x/4 - 1/12)**x`, this becomes `((-3x - 1)/12)**x`, which should split into..."

The agent traces the exact code transformation chain that produces the bug.

**Example (FAIL, scikit-learn-15535):**
No code path tracing at all. Instead: "The issue is in `check_clusterings`" -- names the location but never traces the execution path.

**Largest coefficient in combined logistic regression:** +1.116 (standardized).

### 3.7 error_quote_density (r = +0.238, p = 0.0385)

**What it measures:** Density of backtick-quoted error messages in thinking. Captures when the agent preserves the EXACT error text rather than paraphrasing it.

**Extraction:**
```python
error_quotes = re.findall(
    r'`[^`]*(?:Error|error|Exception|Warning|warning|failed|invalid)[^`]*`',
    text
)
error_quote_density = len(error_quotes) / kchars
```

**Why it works:** Successful agents treat error messages as evidence -- they quote them exactly in their thinking (backtick-wrapped) and reason from the specific text. Failing agents paraphrase errors vaguely ("it gives an error", "there's a compatibility issue"). Pass mean = 0.735 vs fail mean = 0.265 (2.78x ratio).

**Orthogonality:** r = -0.022 with compat_fraction. Completely independent of Round 1 features. This is a genuinely new signal.

**Example (PASS, django-11742):**
> "The `flatchoices` property throws a `ValueError` when the choices are invalid"

The agent quotes the specific exception type.

**Example (FAIL, django-15061):**
Zero backtick-quoted error messages. Errors are described as "The tests are failing because they expected X but now we're returning Y."

---

## 4. MARGINAL FEATURES (p < 0.10)

### 4.1 progressive_understanding (r = +0.223, p = 0.053)

**What it measures:** Whether the agent's thinking becomes more specific over time without accumulating more self-corrections. Computed as `specificity_gain - actually_acceleration`.

**Why it matters:** Successful agents show a pattern of CONVERGENT reasoning -- early blocks are exploratory (few backtick identifiers), late blocks are precise (many backtick identifiers), and the "Actually" rate does not increase. Failing agents either stagnate (no specificity gain) or get increasingly confused (actually_acceleration > 0).

**Pass mean: 2.815. Fail mean: 0.260.** A 10.8x ratio.

**Correlated with specificity_gain at r = 0.996** -- essentially the same measurement, since actually_acceleration adds minimal variance.

### 4.2 interruption_rate (r = -0.222, p = 0.053)

**What it measures:** Rate of self-interrupting words ("Actually", "Wait", "Hmm", "Oh", "Ah") at sentence boundaries per kchar.

**Correlated with actually_density at r = 0.923.** These are measuring the same phenomenon; "Actually" alone captures most of the signal.

### 4.3 specificity_gain (r = +0.210, p = 0.069)

**What it measures:** Change in backtick identifier density from the first half to the second half of thinking blocks. Positive = thinking gets more specific over time.

**Top specificity_gain runs are ALL passes:**
- p0-bugfix-multi-01: gain = +25.7 (early = 0.0, late = 25.7)
- pallets-flask-4045: gain = +15.4
- django-14411: gain = +14.5
- django-11905: gain = +14.3

**Bottom specificity_gain runs are mostly fails:**
- django-15061: gain = -10.5 (starts specific, becomes vague)
- sympy-11400: gain = -6.4
- sympy-13971: gain = -4.8

**Interpretation:** Successful reasoning converges -- it starts broad and narrows. Failing reasoning diverges or stagnates.

### 4.4 narrative_fraction (r = -0.203, p = 0.078)

**What it measures:** Fraction of thinking blocks that are long (>500 chars) and contain no code fences. These are pure narrative reasoning blocks -- the agent is "talking to itself" at length without referencing code.

**Pass mean: 0.201. Fail mean: 0.305.** Failing runs have 52% more pure-narrative blocks.

**Orthogonality:** r = -0.022 with compat_fraction. Completely independent.

**Within-sympy:** r = -0.341, p = 0.070 -- marginal, consistent direction.

---

## 5. FEATURE INDEPENDENCE ANALYSIS

The 11 features cluster into 6 independent groups:

| Cluster | Features | Best representative | Orthogonal to compat? |
|---------|----------|---------------------|-----------------------|
| 1. Clarity | reasoning_clarity, confusion_score, diagnostic_precision | reasoning_clarity (r=+0.385) | No (r=-0.538) |
| 2. Self-correction | actually_density, interruption_rate | actually_density (r=-0.253) | No (r=+0.514) |
| 3. Temporal convergence | specificity_gain, progressive_understanding | specificity_gain (r=+0.210) | Borderline (r=-0.184) |
| 4. Structure | dash_density | dash_density (r=-0.298) | Yes (r=+0.119) |
| 5. Evidence | error_quote_density | error_quote_density (r=+0.238) | Yes (r=-0.022) |
| 6. Form | narrative_fraction | narrative_fraction (r=-0.203) | Yes (r=-0.022) |

**Key finding:** Clusters 4, 5, and 6 are orthogonal to Round 1's top feature (compat_fraction). These represent genuinely NEW information not captured by environment-struggle features.

---

## 6. CONFOUND ANALYSIS

### 6.1 Within-project validation (sympy, n=29, 11 pass, 18 fail)

| Feature | r_pb | p | Direction holds? |
|---------|------|---|-----------------|
| reasoning_clarity | +0.457 | 0.013 | YES, significant |
| confusion_score | -0.385 | 0.039 | YES, significant |
| code_path_density | +0.379 | 0.042 | YES, significant |
| actually_density | -0.378 | 0.043 | YES, significant |
| func_refs_pk | +0.369 | 0.049 | YES, significant |
| diagnostic_precision | +0.352 | 0.061 | YES, marginal |
| narrative_fraction | -0.341 | 0.070 | YES, marginal |

Six features survive within-project validation in sympy. These are NOT project-level confounds.

### 6.2 After excluding high-compat runs (compat_fraction < 0.05)

With 48 runs (34 pass, 14 fail), none of the Round 2 features reach significance. This is expected: removing all compat-heavy runs dramatically reduces the fail count (14 vs 35), destroying statistical power. The features are DIRECTIONALLY CONSISTENT but underpowered in this subset.

### 6.3 Orthogonality to Round 1

Three features are orthogonal to Round 1's compat_fraction:
- **dash_density** (r = +0.119 with compat): A structural marker independent of environment struggle
- **error_quote_density** (r = -0.022 with compat): Evidence engagement independent of environment struggle
- **narrative_fraction** (r = -0.022 with compat): Reasoning form independent of environment struggle

Three features are correlated with Round 1:
- **reasoning_clarity** (r = -0.538 with compat): Contains compat signal within its components
- **confusion_score** (r = +0.496 with compat): Compat struggles drive confusion
- **actually_density** (r = +0.514 with compat): Self-corrections cluster in compat-struggling runs

**Implication:** The correlated features are partially redundant with Round 1 but provide finer-grained measurement. The orthogonal features add genuinely new predictive information.

---

## 7. MULTIVARIATE MODEL COMPARISON

Using logistic regression with 5-fold cross-validation:

| Model | Features | In-sample AUC | CV AUC (mean +/- std) |
|-------|----------|---------------|----------------------|
| Round 1 only | compat_fraction, pivots_pk, func_refs_pk | 0.753 | 0.733 +/- 0.133 |
| Round 2 orthogonal | code_path_pk, dash_density, error_quote_density, specificity_gain, narrative_fraction | 0.813 | 0.756 +/- 0.091 |
| Combined | All 8 above | 0.863 | **0.833 +/- 0.104** |
| Single composite | reasoning_clarity | 0.707 | 0.732 +/- 0.066 |

**Combined model improves CV AUC from 0.733 to 0.833** (+0.100), with tighter confidence interval. Round 2's orthogonal features contribute substantial incremental predictive power.

**Feature coefficients in combined model (standardized):**
| Feature | Coefficient | Direction |
|---------|------------|-----------|
| code_path_density | +1.116 | Strongest pass predictor |
| error_quote_density | +0.766 | Second strongest pass predictor |
| func_refs_pk | +0.688 | Pass predictor |
| compat_fraction | -0.712 | Strongest fail predictor |
| dash_density | -0.525 | Fail predictor |
| narrative_fraction | -0.460 | Fail predictor |
| specificity_gain | +0.367 | Pass predictor |
| pivots_pk | -0.148 | Weak fail predictor (subsumed by others) |

---

## 8. KEY QUALITATIVE PATTERNS (ROUND 2)

### 8.1 The Actually Cascade (fail pattern)

Failed runs exhibit a pattern where "Actually" corrections accumulate without convergence. Each correction doesn't lead to progress -- it leads to another correction:

> Block 12: "Actually, let me just use the compiled module..."
> Block 13: "Actually, thinking about this differently..."
> Block 14: "Actually, the cleanest approach is..."
> Block 15: "Actually, I should refocus..."
> Block 16: "Actually, a smarter approach..."

This is distinct from Round 1's pivot spiral. Pivots change strategy; "Actually" corrections change understanding mid-sentence. The two often co-occur but measure different aspects of confusion.

### 8.2 The Evidence Trail (pass pattern)

Successful runs quote error messages, name specific functions, trace code paths, and reference line numbers. They build an evidence chain in their thinking:

> "Now I understand the issue. Looking at `as_numer_denom()` in `power.py`: The code handles the case where the denominator's sign is unknown (lines 1185-1187), but it doesn't handle the case where the numerator's sign is unknown."

This single sentence contains: a function name, a file name, specific line numbers, and a causal gap identification. Diagnostic precision density = HIGH.

### 8.3 The Narrative Trap (marginal fail pattern)

Failing runs contain more long narrative blocks without code references. The agent is "thinking out loud" at length but not grounding its reasoning in specific code artifacts. It becomes a philosopher instead of a debugger.

### 8.4 The Convergent Arc (pass temporal pattern)

Successful runs show a temporal arc where early blocks are exploratory (low backtick density) and late blocks are precise (high backtick density). The specificity gain is positive -- the agent is converging on the solution. Failed runs either maintain constant specificity (stagnation) or show negative specificity gain (divergence -- they start specific and become increasingly vague).

---

## 9. RELATIONSHIP TO ROUND 1 FEATURES

| Round 1 Feature | Round 2 Analog | Relationship |
|----------------|----------------|--------------|
| compat_fraction (-0.406) | reasoning_clarity (+0.385) | Partially redundant. reasoning_clarity contains compat signal but also non-compat precision. |
| pivots_per_kchar (-0.359) | confusion_score (-0.335) | Overlapping. confusion_score subsumes pivots and adds self-corrections. |
| func_refs_per_kchar (+0.253) | diagnostic_precision (+0.254) | Overlapping. diagnostic_precision generalizes func_refs to include 4 more specificity measures. |
| N/A | dash_density (-0.298) | NEW. No Round 1 analog. Structural marker of fragmented reasoning. |
| N/A | code_path_density (+0.246) | NEW. Causal tracing, not just naming functions. |
| N/A | error_quote_density (+0.238) | NEW. Evidence preservation vs paraphrasing. |
| N/A | specificity_gain (+0.210) | NEW. Temporal convergence of reasoning. |
| N/A | narrative_fraction (-0.203) | NEW. Proportion of code-free narrative thinking. |

**5 features are genuinely new** (no Round 1 analog). 3 features refine/generalize Round 1 discoveries.

---

## 10. CRITICAL FINDING: CONTEXT-DEPENDENT POLARITY

The most important methodological finding from Round 2:

**"Actually" in agent messages (metacognitive_density) correlates at r = +0.494 with success.**
**"Actually" in thinking blocks (actually_density) correlates at r = -0.253 with success.**

Same word. Opposite direction. Different context.

In messages, "Actually" is performative self-correction -- the agent is demonstrating metacognition to the user/system. In thinking, "Actually" is genuine pre-action confusion -- the agent is changing its mind before acting.

**Implication:** Any feature extraction pipeline that conflates thinking content with message content will CANCEL OUT this signal. The thinking/message distinction is not just a data organization choice -- it determines whether a feature carries positive or negative predictive weight.

---

## 11. RECOMMENDED ADDITIONS TO FEATURE PIPELINE

**Priority 1 (novel, orthogonal to Round 1, p < 0.05):**
1. **dash_density** -- Structural fragmentation marker. Orthogonal to compat.
2. **error_quote_density** -- Evidence preservation. Orthogonal to compat.
3. **code_path_density** -- Causal tracing. Largest coefficient in combined model.

**Priority 2 (refines Round 1, p < 0.05):**
4. **confusion_score** -- Composite aggregation of self-correction signals.
5. **reasoning_clarity** -- Net quality score (precision - confusion). Best single predictor.

**Priority 3 (temporal, marginal):**
6. **specificity_gain** -- Convergence trajectory. Large pass/fail ratio (4.76x).
7. **narrative_fraction** -- Code-free reasoning proportion. Orthogonal to compat.

---

## 12. LIMITATIONS

1. **n=76.** All correlations should be treated as estimates with wide confidence intervals.
2. **In-sample model comparison.** The CV AUC of 0.833 is on 76 samples with 5 folds. This needs held-out validation.
3. **Compat confound partially addressed.** Within-sympy checks confirm signal, but 6 of 11 features correlate with compat_fraction. The 5 orthogonal features are the most trustworthy.
4. **Regex extraction.** All features use regex patterns that may miss edge cases or match false positives. More sophisticated NLP could improve extraction fidelity.
5. **No causal claim.** These are correlational. Code path tracing could be a symptom (easy bugs have traceable paths) rather than a cause (tracing paths leads to fixes).
6. **reasoning_clarity and confusion_score are composites** that include Round 1 components. Their high p-values partly inherit Round 1's signal. The cleanest new discoveries are dash_density, error_quote_density, code_path_density, specificity_gain, and narrative_fraction.

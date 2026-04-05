# Dialectic Final Synthesis

**Date:** 2026-03-28
**Round:** 4 (Final)
**Role:** Advocate, responding to Round 3 Critic
**Status:** Convergence achieved. This document is the capstone.

---

## 1. FINAL THESIS STATEMENT

Coding-agent uncertainty is largely hidden from user-facing messages and concentrated in private reasoning, so message-only monitoring systematically misses the agent's overt doubt. At the same time, apparent run-level behavioral predictors of success on multi-task benchmarks collapse when the task is treated as the unit of inference, showing that task difficulty can manufacture convincing but non-generalizable feature/outcome associations. Phase 0 therefore contributes a monitoring blind-spot result and a methodological warning, not a validated predictive feature set.

Both advocate and critic converge on this formulation. It has three load-bearing claims:

1. **The monitoring blind spot is real.** 96-100% of epistemic doubt markers appear in the reasoning layer, not in messages. This holds across two architectures, six repositories, and multiple lexicon definitions.

2. **The naive search for predictive behavioral signals is badly confounded.** In this benchmark, every run-level-significant candidate we examined (11 of 11) failed to replicate under task-level analysis. The confound mechanism is empirically demonstrated.

3. **No validated predictive feature exists yet.** The strongest single-task signal (think_compat_frac on sympy-21612, exact permutation p=0.012) does not generalize across tasks.

---

## 2. LEXICON SENSITIVITY CHECK

The critic asked: does the dissociation depend on specific word choices? If the finding only holds for one marker set, it is fragile.

### 2.1 Marker Sets Tested

| Set | Markers | Rationale |
|-----|---------|-----------|
| **ORIGINAL_DOUBT** | "maybe", "not sure", "perhaps", "let me try", "might be", "could be" | Epistemic doubt phrases (bigram-disambiguated to avoid polysemy) |
| **STRICT_DOUBT** | "not sure", "I don't know", "unclear", "I'm uncertain" | Only explicit avowals of ignorance |
| **BROAD_DOUBT** | ORIGINAL + "hmm", "wait", "actually", "wondering", "tricky", "difficult", "let me think", "let me reconsider", "I wonder" | Full hedging/metacognitive vocabulary |
| **RAW_LEXICAL** | "let me try", "maybe", "not sure", "perhaps", "might", "could" | Bare lexical match (polysemous -- includes non-epistemic "could") |

### 2.2 Results

**Sonnet (n=182 runs with thinking > 100 chars):**

| Marker Set | Think Count | Msg Count | % in Thinking | Density Ratio | Sign (T>M) |
|-----------|------------|----------|--------------|--------------|------------|
| ORIGINAL_DOUBT | 758 | 28 | 96.4% | **9.1x** | 111/182 |
| STRICT_DOUBT | 13 | 0 | 100.0% | **inf** | 12/182 |
| BROAD_DOUBT | 3,121 | 69 | 97.8% | **9.4x** | 142/182 |
| RAW_LEXICAL | 1,180 | 46 | 96.2% | **6.6x** | 114/182 |

**Codex (n=148 runs):**

| Marker Set | Think Count | Msg Count | % in Thinking | Density Ratio | Sign (T>M) |
|-----------|------------|----------|--------------|--------------|------------|
| ORIGINAL_DOUBT | 1,540 | 0 | 100.0% | **inf** | 148/148 |
| STRICT_DOUBT | 41 | 0 | 100.0% | **inf** | 36/148 |
| BROAD_DOUBT | 2,061 | 46 | 97.8% | **34.0x** | 148/148 |
| RAW_LEXICAL | 3,189 | 99 | 97.0% | **21.1x** | 148/148 |

### 2.3 Interpretation

**The dissociation is lexicon-robust.** Every marker set, from the strictest 4-term list to the broadest 15-term list, shows the same qualitative pattern: thinking text contains overwhelmingly more uncertainty language than messages.

Key observations:

1. **For Codex, the dissociation is total under epistemic markers.** With ORIGINAL_DOUBT and STRICT_DOUBT, zero epistemic doubt markers appear in Codex messages across all 148 runs. The 46 BROAD_DOUBT hits in messages come entirely from "actually" (25) and "wait" (21), which in context are temporal/discourse markers ("I don't actually need network"), not epistemic hedges.

2. **For Sonnet, the ratio ranges from 6.6x (RAW_LEXICAL) to 9.4x (BROAD_DOUBT).** The lower bound (6.6x) occurs because bare "could" and "might" have polysemous non-epistemic uses in messages. Once disambiguated to epistemic bigrams ("could be", "might be"), the ratio rises to 9.1x. The sign test is dominant in all cases (111-142 out of 182).

3. **The RAW_LEXICAL set is the weakest because of polysemy, not because the dissociation fails.** The word "could" appears 98 times in Codex messages, but 97 of those are "could not" / "couldn't" describing environment failures ("pip install couldn't complete"), not epistemic uncertainty. This is an important methodological note: bare lexical matching overstates leakage.

4. **STRICT_DOUBT has too few hits to be useful for monitoring** (13 total for Sonnet, 41 for Codex) but shows perfect suppression: 100% of these markers are in thinking. This confirms the phenomenon is real even at the most conservative definition.

**Verdict:** The 8x+ suppression holds robustly across all marker sets that control for polysemy. The finding does not depend on specific word choices. It depends on the structural fact that agents partition epistemic hedging into the reasoning layer.

### 2.4 Monitoring Gap by Marker Set

The monitoring gap (fail runs detectable only via thinking) is also lexicon-robust:

| Model | Marker Set | Fail Runs Detectable Only via Thinking |
|-------|-----------|---------------------------------------|
| Sonnet | ORIGINAL_DOUBT | 57/94 (60.6%) |
| Sonnet | BROAD_DOUBT | 57/94 (60.6%) |
| Codex | ORIGINAL_DOUBT | 84/84 (100.0%) |
| Codex | BROAD_DOUBT | 60/84 (71.4%) |

For Codex with epistemic markers, 100% of failing runs are invisible to message-only monitoring. For Sonnet, roughly 60% are invisible regardless of marker set.

---

## 3. MANUAL VALIDATION SAMPLE

Ten thinking blocks flagged as containing doubt markers were read in full to assess false positive rate.

### 3.1 Results

| # | Model | Task | Outcome | Markers | Genuine Doubt? | Notes |
|---|-------|------|---------|---------|----------------|-------|
| 1 | Sonnet | sympy-16988 | PASS | "might", "actually" x3 | **Yes** | "I think the domain intersection might be happening inside _solveset itself rather than at the top level" -- genuine diagnostic uncertainty about code behavior |
| 2 | Sonnet | pylint-7080 | PASS | "maybe", "wait" x2, "actually" x2 | **Yes** | "Wait, that can't be right... Actually wait - maybe I'm wrong" -- textbook self-correction under uncertainty |
| 3 | Sonnet | requests-3362 | PASS | "could", "actually" | **Marginal** | "I could install the legacy-cgi package" -- modal of possibility, not pure epistemic doubt. "Actually" is a self-correction. 1 of 2 markers is genuinely epistemic. |
| 4 | Sonnet | sympy-21612 | FAIL | "wait", "actually", "wondering" | **Yes** | "Wait, but this changes behavior too. Let me think again." -- genuine re-evaluation of approach |
| 5 | Sonnet | sympy-16503 | PASS | "maybe", "wait", "actually" x2 | **Yes** | "maybe prettyForm overrides it?... Wait, I just realized something about how newWidth is computed" -- genuine diagnostic exploration |
| 6 | Codex | sympy-14308 | FAIL | "maybe" x2, "perhaps", "might" | **Yes** | "maybe I need to align the baseline properly... perhaps that could fix the issue" -- genuine uncertainty about correct approach |
| 7 | Codex | sympy-13895 | FAIL | "might" x3 | **Marginal** | "There might be issues with different versions" -- genuine but vague. Codex reasoning style is more hedged-narrative than Claude's direct self-questioning |
| 8 | Codex | pytest-7432 | FAIL | "might" x2 | **Yes** | "It looks like I might need to use no-build-isolation" -- genuine uncertainty about environment setup |
| 9 | Codex | django-15819 | PASS | "maybe", "might" x2, "could" | **Yes** | "maybe I should use related_name... It might be best to create a deterministic unique related_name" -- genuine design deliberation |
| 10 | Codex | django-15790 | PASS | "maybe" | **Marginal** | "Should I consider closing it or maybe just ignore that idea?" -- genuine but weak. Codex's summarization style makes some markers feel performative. |

### 3.2 Assessment

- **7 of 10 blocks (70%) express genuine epistemic uncertainty.** The markers correspond to real moments of diagnostic doubt, self-correction, or approach deliberation.
- **3 of 10 blocks (30%) are marginal.** The markers are present but the epistemic content is weaker -- possibility modals rather than avowed uncertainty, or narrative hedging rather than genuine doubt.
- **0 of 10 blocks are clear false positives.** None of the flagged blocks are using the markers in a purely non-epistemic way (e.g., "I could do X and Y" as a capability statement with no uncertainty).

**Verdict:** The markers are imperfect but directionally valid. A 70% genuine-doubt rate with 30% marginal (and 0% clearly false) is adequate for the dissociation claim, which is about the distribution of markers across channels, not about whether each individual marker is a perfect epistemic indicator. Even the marginal cases show reasoning-layer content that is absent from messages.

---

## 4. FINAL EVIDENCE HIERARCHY

### Tier A: Confirmed (robust to all challenges)

**A1. Thinking/message doubt dissociation.**

- Epistemic doubt markers are 9-34x denser in reasoning than in messages (per kilocharacter, after length matching)
- For Codex with epistemic markers: total suppression (0 markers in messages across 148 runs)
- For Sonnet: 96-98% of markers in thinking across all lexicon variants
- Survives: length-matching (Round 2), cross-repo consistency (all 6 repos, both models), lexicon sensitivity (4 marker sets tested in Round 4)
- Manual validation: 70% genuine doubt, 30% marginal, 0% clear false positive
- Sign test p < 0.000001 for both models
- **Monitoring implication:** 60-100% of failing runs expressing doubt are invisible to message-only monitoring

**A2. Run-level behavioral correlations are confounded by task difficulty.**

- 11 features reach run-level significance (many at p < 0.001) across two models
- 0 of 11 survive task-level sign tests across 5-7 mixed-outcome tasks
- Confound mechanism demonstrated: task pass rate correlates with mean feature values (rho = -0.288, p = 0.019 for think_compat_frac)
- **Claim language (corrected per critic):** "In this benchmark, every run-level-significant candidate we examined failed to replicate under task-level analysis." Not: "100% inflation rate" (which overgeneralizes from a selected set)
- **Methodological contribution:** The specific correction (task-level sign test, within-task exact permutation, Fisher combination) is provided

### Tier B: Confirmed on a single task (fails to generalize)

**B1. think_compat_frac on sympy-21612.**

- Within-task exact permutation p = 0.012 (9 replicates, 6 pass / 3 fail)
- Fail runs have 2.2x higher environment-compatibility language in thinking
- Does NOT generalize: Fisher combination across 6 Sonnet tasks yields p = 0.137
- Directional consistency: 3+/3- across tasks (no trend)
- **Status:** Hypothesis-generating for prospective testing. Not a validated general signal.

### Tier C: Exploratory (hypothesis-generating only)

**C1. Error universality.** 92% of both pass and fail runs encounter errors. Failure is not "did an error happen" but "did error accumulation overwhelm recovery." Recovery rate (47.4%) is essentially identical to error-free pass rate (46.7%).

**C2. Tool-use composition asymmetry.** Successful Sonnet runs use 77% more Grep and 34% less Bash per run. Shows 5/7 task-level consistency for Grep but does not reach significance (sign p = 0.45). Interesting because it is observable without reasoning access.

**C3. Density asymmetries in thinking.** Fail runs show 1.5x doubt density, 2.5x recovery language, 2.3x environment-struggle language in thinking. These are run-level effects confounded by task difficulty. They characterize the phenomenology of struggle but do not predict failure.

### What Is Retracted from All Prior Rounds

- All predictive claims for any feature
- All gate proposals and operating characteristics
- All cross-model polarity claims stronger than descriptive observation
- "100% inflation rate" as a general claim about the field
- All causal language
- "Models fail differently" as anything stronger than qualitative hypothesis

---

## 5. CONFIRMATORY VS. EXPLORATORY SPLIT

The critic requested a hard boundary. Here it is.

### Confirmatory (pre-specified hypotheses that survived all tests)

| Finding | Pre-specified? | Test | Result |
|---------|---------------|------|--------|
| Thinking contains more doubt markers than messages | Hypothesized in Phase 0 design | Paired sign test, length-matched | p < 0.000001 both models |
| The dissociation holds across repos | Checked as robustness | Per-repo sign tests | All 6 repos same direction |
| The dissociation is lexicon-robust | Checked in Round 4 | 4 marker sets | All show suppression |
| Run-level features do not survive task-level | Critic-demanded check (Round 2) | Task-level sign test, Fisher | 0/11 survive |

### Exploratory (patterns discovered in this data, require prospective replication)

| Pattern | Evidence | Why Exploratory |
|---------|----------|----------------|
| think_compat_frac on sympy-21612 | Exact permutation p = 0.012 | Single task, fails Fisher, no pre-registration |
| Grep fraction predicts success | 5/7 task-level consistency | Does not reach significance, discovered post-hoc |
| Error accumulation > error occurrence | Pass/fail recovery rates near-identical | Descriptive, no formal test |
| Codex total suppression vs Sonnet partial leakage | Observed | Architectural comparison, not tested |
| Doubt density higher in fail runs | 1.5x within thinking | Confounded by task difficulty at task level |

---

## 6. PRACTITIONER SECTION

### 6.1 If You Have Reasoning Access

You are in the better position. The data say:

1. **Monitor the reasoning layer, not messages.** Messages suppress 96-100% of the agent's expressed uncertainty. If your monitoring system reads only the agent's outward-facing messages, you are flying blind on the agent's own assessment of its situation.

2. **Do not build gates from doubt presence alone.** At a simple presence/absence threshold, thinking-layer doubt monitoring has 85% sensitivity but only 26% specificity for Sonnet. Both successful and failing runs express doubt. Doubt presence is necessary for failure detection but not sufficient.

3. **Investigate doubt density, not doubt presence.** Failing runs show 1.5x higher doubt density in thinking. However, this run-level pattern has not been validated at the task level. Treat any density threshold as a hypothesis to be tested with pre-registered cutoffs on new data, not as a production-ready signal.

4. **Validate any behavioral feature at the task level.** Any feature that looks predictive at the run level may be a task-difficulty confound. The test: compute the feature-outcome association separately for each task, then test whether the direction is consistent across tasks (sign test) or combine within-task permutation p-values (Fisher method). If your mixed-outcome task count is below ~15, you likely lack power to detect anything short of a very large effect.

5. **Pre-register thresholds.** If you identify a candidate signal in exploratory analysis, specify the exact feature, direction, and cutoff before testing on new data. Post-hoc optimization of thresholds on the same data that generated the hypothesis is guaranteed to overfit.

### 6.2 If You Do NOT Have Reasoning Access

This is the harder case. The monitoring blind spot is real and there is no cheap workaround:

1. **Do not assume message tone reflects agent confidence.** Messages are generated in a different register from reasoning. A confidently-phrased message ("Let me look at the function more carefully") may accompany extensive internal doubt ("Wait, that can't be right... maybe I'm wrong"). The dissociation is near-total.

2. **Instrument uncertainty explicitly.** If you cannot read the reasoning layer, the next-best option is to add explicit uncertainty instrumentation to the agent's workflow. For example: periodically prompt the agent to summarize its current confidence in a structured format, or require the agent to flag when it is exploring alternatives. This changes the task (which is why Phase 0 did not do it), but it is better than pretending messages are informative.

3. **Use structural signals as a starting point.** Tool-use composition (Grep vs Bash ratio) and error accumulation (fail_streak_max) are observable without reasoning access. These show suggestive run-level patterns (77% more Grep in successful runs, threshold effects for error streaks) but have NOT been validated at the task level. They are hypotheses, not validated signals.

4. **Monitor error accumulation, not error occurrence.** Errors are nearly universal (92% of runs). A single error is uninformative. But runs with high consecutive error streaks (fail_streak_max >= 3-4) show dramatically reduced pass rates in both models. This is the most promising message-layer signal for further investigation.

5. **Invest in getting reasoning access.** The core finding of this work is that the information you need for uncertainty monitoring lives in a layer you cannot see. The most effective practical recommendation for organizations without reasoning access is to negotiate for it, or to build architectures that externalize reasoning.

### 6.3 For Both Groups

- **Expect the false-positive problem.** Any behavioral feature that looks promising on a multi-task benchmark should be treated with suspicion until validated at the task level. The confound (task difficulty driving both the feature and the outcome) is structural and ubiquitous.
- **Replicate on more tasks.** Phase 0 had 7 mixed-outcome Sonnet tasks and 5 Codex tasks. This is insufficient for detecting moderate effects. A proper validation study needs 15-20+ mixed-outcome tasks with 5-10+ replicates each.
- **Separate calibration from evaluation data.** Any threshold or feature identified in exploratory analysis must be tested on held-out data. The 11/11 false positive rate in Phase 0 is a direct consequence of testing on the same data used for discovery.

---

## 7. LIMITATIONS

Stated squarely, as the critic demanded:

1. **No generalizable predictive feature.** Phase 0 does not identify any behavioral signal that predicts agent success across tasks.
2. **No gate.** No intervention was tested. All findings are observational.
3. **No out-of-sample validation.** All analyses are on the same 338-run dataset.
4. **No causal claims.** The dissociation is correlational. We do not know whether suppressing doubt in messages is a design choice, a training artifact, or an emergent property.
5. **Possible register confound.** Length-matching rules out a verbosity artifact, but not all register/function differences between private reasoning and user-facing messages. What is established is per-character suppression, not a full causal account of why messages differ from thinking.
6. **Two architectures, one domain.** Both models are coding agents on SWE-bench. The dissociation may differ for other domains (e.g., creative writing, customer service) or other architectures.
7. **Small task-level sample.** 7 mixed-outcome Sonnet tasks and 5 Codex tasks provide limited statistical power. The null task-level results may be partly a power failure, not just an absence of signal.
8. **Retrospective claim language.** The "11 of 11 features fail task-level replication" is a retrospective count of features that were selected because they looked good at the run level. It is an accurate description of what happened in this dataset, not an unbiased estimate of the field's false-positive rate.

---

## 8. WHAT THE PAPER IS AND IS NOT

**The paper is:**
- A first quantification of the thinking/message uncertainty dissociation in coding agents
- A methodological demonstration that run-level behavioral predictors are confounded by task difficulty
- A practitioner warning about monitoring blind spots

**The paper is not:**
- A validated predictive model
- A gating system
- A causal account of why agents suppress doubt
- A claim that behavioral features are useless (they may work with proper task-level validation on more data)

---

## 9. CONVERGENCE NOTE

After four rounds of dialectic:

- **Round 1** presented 6 findings with aggressive claims. The critic killed 4, wounded 1, accepted 1.
- **Round 2** retracted the killed claims, presented length-matched dissociation and corrected task-level analysis. The critic accepted the dissociation, confirmed no feature survives task-level.
- **Round 3** reframed the paper as three contributions (dissociation, negative methodological result, exploratory patterns). The critic accepted the frame, asked for tighter claim language and lexicon robustness.
- **Round 4** (this document) provides lexicon sensitivity, manual validation, the confirmatory/exploratory split, and the practitioner section.

The thesis has been stable since Round 3. The Round 4 additions strengthen the robustness of the central finding but do not change the conclusions. This is convergence.

---

*Generated 2026-03-28. Database: data/uga_phase0_complete_final.db (338 validated runs). All analyses reproducible from raw_stream_json.*

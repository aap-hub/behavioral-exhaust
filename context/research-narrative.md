# UGA Research Narrative — Historical Record (SUPERSEDED as Source of Truth)

**Purpose:** Living document tracking every intellectual move, structural fix, and methodological refinement from design through data collection through analysis. Input to the final Anthropic report. Reference for reproducibility.

**IMPORTANT:** This document is a historical record of the research process. Several claims made here have been corrected or superseded by the final deliverable (`context/phase0_final_deliverable.md`) and the Phase 0 memo (`PHASE0_MEMO.md`). Key superseded claims are marked inline. The CWC methodology described in Section 11 (Mundlak-style) has been replaced by the Fisher-combined within-repo approach in the final deliverable.

**Last updated:** 2026-03-29

---

## 1. ORIGIN AND INTENT

**Research question:** "What determines the quality of uncertainty signals for agent tool-call decisions?"

The goal is both a working research harness and a genuine empirical finding about agent behavioral signals.

**Principal investigator background:** PhD in philosophy of science with expertise in modal logic and formal systems. Colleague Matt Mandelkern (MIT) publishes on LLMs and philosophy of language. This background shaped the emphasis on epistemically precise framing, clean measurement/intervention separation, and operational definitions.

**Core constraint:** OAuth-only authentication (no Anthropic API key). This blocked API-based confidence elicitation (log-probs, P(True), verbalized confidence) and forced behavioral exhaust mining — which turned out to be the more interesting approach.

---

## 2. DESIGN PHASE (2026-03-28, sessions 1-2)

### 2.1 Initial framing
Started as "confidence-gated tool calls" — standard selective prediction (Chow 1970, Geifman 2017) applied to agent actions. Design doc went through 12+ adversarial reviews (CEO review, eng review, 2 Codex reviews, 2 Opus mentor reviews).

### 2.2 Three pivots

**Pivot 1 — Research question.** From "does gating help?" (obvious) to "what determines signal quality?" (novel). Two orthogonal factors: signal source (introspective vs extrospective) × trajectory position (does calibration degrade as context fills?).

**Pivot 2 — Signal architecture.** OAuth constraint blocked API-based methods. Pivoted to behavioral exhaust mining: extract uncertainty signals from the structure of reasoning text, not its content. Grounded in Anthropic's own research:
- Self-reported confidence is near-useless (Rabanser et al. 2026)
- CoT content is unfaithful 75% of the time (Chen et al. 2025)
- But unfaithful CoTs are systematically LONGER — a structural signal
- Nobody had studied whether behavioral structure predicts action correctness

**Pivot 3 — Feature grounding.** Initially planned Tier 2 modal features (Kratzer 1991, Rubinstein et al. 2013). Pulled back to Tier 1 Hyland hedge lexicon (209 terms) after Codex critique and philosophical reflection: "We don't need a theory of meaning. We need features that predict."

### 2.3 Design decisions (documented in context/design-decision-trail.md)
- Behavioral exhaust mining as primary signal source
- Sonnet 4.6 as target model (ecological validity)
- SQLite WAL as data store (not JSONL)
- Phase 0/Phase 1 separation (measure before intervening)
- Single labeler with blinded dual-pass protocol
- SWE-bench Lite for task sourcing

### 2.4 Key literature
- Chen et al. 2025, "Reasoning Models Don't Always Say What They Think"
- Rabanser et al. 2026, "Towards a Science of AI Agent Reliability"
- Anthropic, "A Statistical Approach to Model Evaluations"
- arXiv:2508.15842, "Lexical Hints of Accuracy in LLM Reasoning Chains"
- arXiv:2602.09832, "LLM Reasoning Predicts When Models Are Right"
- Hyland 1998, hedging lexicon

---

## 3. BUILD PHASE (2026-03-28, session 2)

### 3.1 Pipeline built
- src/db.py: SQLite schema (runs + tool_calls + critic_comparisons)
- src/trace_collector.py: stream-json parser with Bash classification
- src/runner.py: task execution with workspace isolation
- src/feature_definitions.py: 10 features (4 structural + 6 linguistic)
- src/analysis.py: Spearman correlations at task and call level
- 63 unit tests passing

### 3.2 Initial data collection
- 20 runs (3 Opus smoke, 5 synthetic, 12 SWE-bench)
- 156 state-modifying tool calls after read-only contamination fix

### 3.3 Early findings (later invalidated)
- deliberation_max: ρ = -0.707, p = 0.005 (appeared significant)
- verification_sum: ρ = -0.602, p = 0.023
- These were ARTIFACTS of: (a) run conflation bug, (b) mislabeled data (8% pass rate from broken validation)

---

## 4. VALIDATION CRISIS AND RESOLUTION (2026-03-28 to 2026-03-29)

### 4.1 The problem
Runner validation used `python -m pytest` in the agent's workspace. Exit 127 on almost every run because:
1. macOS has `python3` not `python`
2. Python 3.14 incompatible with SWE-bench repos (ast.Str removed in 3.12)
3. Result: 95 of 105 runs labeled "fail" — almost all wrong

### 4.2 Approaches tried
1. **SWE-bench Docker eval:** Worked for 8 tasks (5 RESOLVED, 2 UNRESOLVED, 1 ERROR). But OOM on large repos. Partial solution.
2. **Trace mining (agent self-report):** Extracted the agent's own test output from raw_stream_json. Found 23 passes. But NOT independent — takes the agent's word for it.
3. **Edit replay with Python 3.10:** The solution. `brew install python@3.10`, create fresh venv with SWE-bench-pinned deps, replay agent's Write/Edit on clean repo copy, run FAIL_TO_PASS tests ourselves. Independent validation without Docker.

### 4.3 Resolution
- Installed Python 3.10 via Homebrew
- Built src/independent_validate.py: edit replay + SWE-bench pinned deps
- 101 of 105 runs independently validated (96% coverage)
- 4 unrecoverable (2 infra failures, 2 where agent re-cloned repo)
- True pass rate: 51% (not 8%)

### 4.4 Impact on findings
- All session 2 "significant" findings DISAPPEARED under independent validation
- Verification, planning, deliberation: all noise
- Only backtrack_count borderline (ρ = +0.340, p = 0.0049)
- Only fail_streak_max significant after Bonferroni (ρ = -0.353, p = 0.0034)

### 4.5 Lesson
The user's insistence on independent validation ("we shouldn't take the agent's word for it") literally changed the conclusion of the study. Self-reported labels inflated 3 features to significance. Independent validation killed them.

---

## 5. PIPELINE HARDENING (2026-03-28 to 2026-03-29)

### 5.1 Codex adversarial audits
Three full audit cycles, each reading all source files:
- **Round 1 (session 2):** 17 issues. All fixed. Data integrity, classification, Docker wiring.
- **Round 2 (overnight):** 18 cycles, 40 findings, 13 unique after dedup. All fixed. Transactions, step_index bias, redirections, pipes, compound commands.
- **Round 3 (session 3):** 13 findings, fresh audit. All fixed. Validation provenance, Bonferroni correction, path traversal, 23 new tests.

### 5.2 Key infrastructure fixes
- conn.commit() inside insert helpers broke explicit transactions → conditional commit
- Revised to isolation_level=None (true autocommit) with explicit BEGIN/COMMIT for atomicity
- step_index_normalized: 1-based to 0-based conversion (was biased)
- sed -i, find -delete: now correctly classified as state-modifying
- Shell redirections (echo > file): now caught
- Compound commands (grep && rm): recursive classification
- Pipe heuristic: check ALL segments, not just first
- || vs |: logical OR handled separately from pipe
- validation_source column: provenance tracking for labels
- Bonferroni correction in analysis output

### 5.3 Test coverage
63 feature tests + 23 trace_collector tests = 86 tests, all passing.

### 5.4 Overnight data collection
18 autonomous cycles via src/overnight.py. 105 total runs across 75 unique tasks. Codex audit every cycle (free). Task selection prioritized unrun tasks, then mixed-outcome tasks, then replicates.

---

## 6. PROTOCOL LOCK (2026-03-29)

### 6.1 The 71-task protocol
- 71 SWE-bench Lite tasks with independently validated labels
- Blended pass rate: 50% (51 pass, 50 fail)
- Stored in data/protocol_tasks.json
- Each future wave runs all 71 tasks exactly once
- No subsetting, no selection — the blend provides the variance

### 6.2 Environment (fixed)
- Agent: Claude Sonnet 4.6, ungated, `claude -p --model sonnet`
- Validation: Python 3.10, SWE-bench pinned deps, edit replay on fresh repo
- Timeout: 30 min agent, 5 min validation
- DB: SQLite, isolation_level=None

### 6.3 Entry point
protocol.py with four verbs: run, validate, analyze, status.

---

## 7. TIER 2 SEMANTIC ANALYSIS (2026-03-29)

### 7.1 Framework design
Two independent frameworks designed by Opus and Sonnet agents, then merged. Key principles:
- Mean aggregation replaces sum (controls for task-length confound)
- Pre-registered expected directions for all features
- Random noise control column
- BH FDR correction at q=0.10

### 7.2 The task-length confound (critical discovery)
Failing tasks average 22.9 state-modifying calls vs 16.6 for passing. This means:
- Sum aggregation artificially inflates features for failing tasks
- Partial correlation controlling for total_calls is required
- This confound SUPPRESSED the metacognitive signal: raw ρ = +0.308, partial ρ = +0.494

### 7.3 Tier 2 results (n=73 unique tasks)
10 of 20 features survive BH FDR q=0.10 after task-length correction:

| Feature | Partial ρ | p | Type | Source |
|---------|-----------|---|------|--------|
| metacognitive_density | +0.494 | <0.001 | Linguistic | Pre-registered |
| tentative_density | -0.434 | <0.001 | Linguistic | Discovered |
| early_error_rate | -0.372 | 0.001 | Structural | Discovered |
| fail_then_switch_rate | -0.372 | 0.001 | Structural | Pre-registered (wrong direction) |
| insight_density | +0.315 | 0.007 | Linguistic | Discovered |
| instead_contrast_density | +0.300 | 0.010 | Linguistic | Pre-registered |
| mean_edit_expansion | +0.265 | 0.024 | Structural | Discovered |
| error_rate | -0.257 | 0.028 | Structural | Discovered |
| reasoning_to_action_alignment | -0.232 | 0.049 | Interaction | Pre-registered (wrong direction) |
| total_state_modifying_calls | -0.476 | <0.001 | Structural | Control variable |

### 7.4 The headline finding
**"Actually" is the single strongest word predictor of agent success** (ρ = +0.330, p = 0.004). When Sonnet says "actually" in reasoning, it's doing evidence-based self-correction. This is not hesitation — it's adaptive revision.

**"Let me try" is the strongest failure marker** (5.5x more frequent in fails). It signals experimentation without a hypothesis.

### 7.5 What this means
Sonnet's uncertainty IS expressed linguistically, but through domain-specific metacognitive markers, not academic hedge words. The Hyland lexicon failure was a measurement problem, not a signal-absence problem. The signal was there; it needed the right operationalization.

### 7.6 What failed at Tier 2
- precision_naming_score: backticks and identifiers are ubiquitous, no discrimination
- causal_density: "because"/"since" too common in all reasoning
- recovery_rate: dominated by infrastructure error recovery (noise)
- test_run_count: all agents run tests; count has no signal after length correction
- fail_then_switch_rate: went OPPOSITE to prediction — switching after errors is flailing, not diagnosis

---

## 8. FEATURES REGISTRY (cumulative)

### Tier 0 — Structural (from trace structure)
| Feature | Status | Finding |
|---------|--------|---------|
| step_index_normalized | Conditioning variable | Not predictive alone; use for trajectory analysis |
| prior_failure_streak / fail_streak_max | SIGNIFICANT (Bonferroni) | ρ = -0.353, p = 0.0034 |
| retry_count | Not significant | |
| tool_switch_rate | Not significant | |

### Tier 1 — Linguistic, original (Hyland + exhaust)
| Feature | Status | Finding |
|---------|--------|---------|
| hedging_score (Hyland 209-term) | DEAD | ρ = -0.122, Sonnet doesn't hedge when coding |
| deliberation_length | Not significant | Length ≠ uncertainty |
| alternatives_considered | Not significant | Too rare |
| backtrack_count / back_sum | Borderline | ρ = +0.340, p = 0.0049 (misses Bonferroni) |
| verification_score | Not significant | Artifact of label leakage in early data |
| planning_score | Not significant | "Let me"/"then" is Sonnet's default style |

### Tier 2 — Structural, refined
| Feature | Status | Finding |
|---------|--------|---------|
| early_error_rate | SIGNIFICANT (FDR) | ρ_partial = -0.372, p = 0.001 |
| error_rate (overall) | Significant (FDR) | ρ_partial = -0.257, p = 0.028 |
| fail_then_switch_rate | Significant (FDR) | ρ_partial = -0.372 (opposite to prediction) |
| mean_edit_expansion | Significant (FDR) | ρ_partial = +0.265, p = 0.024 |
| first_edit_position | Not significant | ρ_partial = +0.169, p = 0.154 |
| unique_files_touched | Not significant | |
| edit_churn_rate | Not significant | |
| test_run_count | Not significant | |
| recovery_rate | Not significant (opposite direction) | |

### Tier 2 — Linguistic, domain-specific
| Feature | Status | Finding |
|---------|--------|---------|
| metacognitive_density | STRONGEST SIGNAL | ρ_partial = +0.494, p < 0.001 |
| tentative_density | SIGNIFICANT (FDR) | ρ_partial = -0.434, p < 0.001 |
| insight_density | SIGNIFICANT (FDR) | ρ_partial = +0.315, p = 0.007 |
| instead_contrast_density | SIGNIFICANT (FDR) | ρ_partial = +0.300, p = 0.010 |
| self_directive_density | Not significant | |
| wrong_stuck_density | Not significant | |
| causal_density | Not significant | |
| precision_naming_score | Not significant | |

### Tier 2 — Interaction
| Feature | Status | Finding |
|---------|--------|---------|
| reasoning_to_action_alignment | Significant but wrong direction | ρ_partial = -0.232, p = 0.049 |

### Controls
| Feature | Status | Finding |
|---------|--------|---------|
| random_noise | NOT significant | ρ_partial = -0.076, p = 0.524 (pipeline clean) |
| total_state_modifying_calls | Significant confound | ρ_partial = -0.476 (failing tasks longer) |

---

## 9. OPEN QUESTIONS

1. Is "actually" a faithful signal or performance? (needs Phase 1 testing)
2. Why does fail_then_switch predict failure? (flailing > diagnosis)
3. Will these features generalize beyond Sonnet 4.6?
4. Is n=73 adequate for 20+ features? (overfitting risk)
5. How to combine pilot data with future wave data?
6. Should discovered features (tentative_density, early_error_rate, insight_density) be pre-registered for wave 2 or treated as exploratory?
7. Statistical review pending (context/tier2_statistical_review.md)

---

## 10. FILE INVENTORY

### Source code
- protocol.py — single entry point for locked experiment
- src/db.py — SQLite schema + helpers
- src/trace_collector.py — stream-json parser + Bash classification (86 tests)
- src/runner.py — task execution with independent validation
- src/analysis.py — Tier 0/1 feature extraction + correlations
- src/feature_definitions.py — 10 original features
- src/tier2_features.py — 13 Tier 2 features + task-level aggregation
- src/independent_validate.py — edit replay validator (Python 3.10)
- src/trace_validate.py — trace mining validator (lower confidence)
- src/swebench_validate.py — SWE-bench Docker integration
- src/docker_validate.py — lightweight Docker validation
- src/overnight.py — continuous loop engine

### Data
- data/uga.db — SQLite with all experimental data
- data/protocol_tasks.json — locked 71-task set
- data/cycle_reports/ — 18 Codex audit reports + cycle metadata
- data/codex_fix_checklist_deduped.md — master checklist of all fixes

### Context documents
- context/research-narrative.md — THIS FILE (source of truth)
- context/tier2-semantic-framework.md — Opus framework for Tier 2
- context/tier2_framework_sonnet.md — Sonnet framework for Tier 2
- context/tier2_results.md — Full Tier 2 correlation results
- context/tier2_statistical_review.md — Statistical methods review (pending)
- context/design-decision-trail.md — 10 design decisions with rationale
- context/analysis-protocol.md — SQL queries and report structure
- context/anthropic-methods-synthesis.md — 17+ Anthropic publications
- context/codex-pipeline-audit.md — Round 1 audit (17 issues)
- context/codex-pipeline-audit-v2.md — Round 2 audit (20 issues)
- context/codex_full_pipeline_audit.txt — Round 3 audit (13 issues)

### Memory files
- memory/uga_phase0_protocol.md — Protocol lock milestone
- memory/uga_session3_audit_fixes.md — Session 3 fixes
- memory/uga_session2_complete.md — Session 2 build state
- memory/uga_intellectual_history.md — Full reasoning topology

### Tests
- tests/test_features.py — 63 feature extraction tests
- tests/test_trace_collector.py — 23 classification tests

---

## 11. CWC DECOMPOSITION (2026-03-29) — SUPERSEDED

**NOTE:** This section describes the Mundlak-style CWC decomposition. The final deliverable uses a different (simpler) CWC approach: Fisher-combined within-repo Spearman correlations. The Mundlak results below are historical and should not be cited. See phase0_final_deliverable.md Section 11.2.

### Method (Historical)
Cluster-Mean Centering (CWC) with the Mundlak device, plus within-repo permutation tests (10,000 permutations). This decomposes each feature into within-repo signal (beta_W) and between-repo signal (beta_B).

### Result
Three features from THINKING blocks have genuine within-repo signal:

| Feature | β_within | p_within | Perm p | ICC | Interpretation |
|---------|----------|----------|--------|-----|----------------|
| t_func_refs_per_kchar | +1.47 | 0.047 | 0.008 | 0.04 | Reasoning about concrete code predicts success |
| t_compat_fraction | -20.1 | 0.043 | 0.023 | 0.09 | Environment struggle predicts failure |
| t_pivots_per_kchar | -3.78 | 0.031 | 0.042 | 0.34 | Strategy thrashing predicts failure |

All message-layer features (metacognitive_density, insight_density, etc.) have NO within-repo signal in the Mundlak decomposition. They were entirely driven by repo differences.

### What this means (partially superseded)
1. The genuine behavioral signal is in THINKING blocks, not agent messages. (Confirmed by final analysis.)
2. The earlier "metacognitive_density is the strongest signal" finding was a repo confound. (Confirmed.)
3. The parser bug that hid thinking data was hiding the real signal. (Confirmed.)
4. The three features that survive CWC are low-ICC (mostly within-repo variance). (Note: the final deliverable uses a different CWC method; the specific survivor list differs.)
5. **CORRECTION:** This section says "within-task" and "between-task" but the decomposition is within-REPO and between-REPO. Within-repo is NOT the same as within-task. The distinction matters for confounding arguments -- within-repo still includes task difficulty variation within the repo.

---

## 12. METHODOLOGICAL INSIGHTS REGISTRY (2026-03-29)

### Statistical Methods Evolution
1. **Raw Spearman** (naive): 10+ features "significant." Confounded by repo difficulty.
2. **Mixed-effects logit** (repo as fixed effect): Most features lost significance. Correct but opaque.
3. **Bonferroni correction**: Too strict for 9-23 tests. Killed borderline features unnecessarily.
4. **BH FDR**: Standard alternative. Controls false discovery rate. Appropriate for our test count.
5. **CWC decomposition** (Mundlak device): The breakthrough. Decomposes each feature into within-repo (β_W) and between-repo (β_B) components. Within-repo signal is the genuine behavioral signal. Between-repo is the difficulty proxy.
6. **Within-repo permutation test**: Non-parametric confirmation. 10,000 permutations, shuffling outcomes within each repo. No distributional assumptions. Our most defensible test.
7. **ICC analysis**: Reveals how much feature variance is between-repo vs within-repo. Low ICC = genuine within-task variation. High ICC = mostly difficulty-indexed.

### Key Methodological Findings
- **Message features were repo confounds.** Every "significant" agent-message feature (metacognitive_density, insight_density, etc.) had NO within-repo signal after CWC decomposition.
- **Thinking features carry genuine signal.** Five features from thinking blocks survive within-repo permutation testing.
- **Same word, opposite polarity across layers.** "Actually" in messages = positive (r=+0.494). In thinking = negative (r=-0.253). Any pipeline conflating layers cancels the signal.
- **Parser bugs hide real data.** The thinking block parser read `text` instead of `thinking` key. 2.3M chars of genuine reasoning was invisible. This is a cautionary tale for exhaust mining.
- **Independent validation changes conclusions.** Agent self-report inflated features to significance. Independent edit replay + Python 3.10 revealed the truth.
- **Task-length confound suppresses linguistic features.** Failing tasks are 38% longer. Sum aggregation is always wrong. Mean normalization required.

### Philosophical Insight: What the Human Doesn't See
The genuine behavioral signal lives in the thinking layer — content the human user never sees. Agent messages are performative (crafted for the user). Thinking blocks are deliberative (the model reasoning to itself). The deliberative layer reveals:
- Whether the agent is reasoning about concrete code (func_refs, code_paths → success)
- Whether the agent is struggling with environment (compat_fraction → failure)
- Whether the agent is thrashing between strategies (pivots → failure)
- Whether the agent's reasoning is precise vs confused (reasoning_clarity → success)

This supports the thesis that agent exhaust — specifically the unguarded internal reasoning — is a rich, underexplored source of information about agent reliability. The preliminary hypothesis for Phase 1: a hook that reads the thinking stream concurrently and intervenes when it detects confusion/thrashing patterns can course-correct the agent before it commits to a failing path.

### Claims Registry (bounded by statistical test) — PARTIALLY SUPERSEDED

**NOTE:** The claims below are from the Mundlak-style CWC analysis. The final deliverable uses Fisher-combined within-repo Spearman. Some claims survive under both methods; others do not. See phase0_final_deliverable.md Section 7 for the corrected hierarchy.

**Tier 1 claims (within-repo permutation, p < 0.01):**
- diagnostic_precision: perm p=0.004, sympy rho=+0.453
- reasoning_clarity: perm p=0.004, sympy rho=+0.533
- t_func_refs: perm p=0.008, sympy rho=+0.362

**Tier 2 claims (within-repo permutation, p < 0.05):**
- t_compat_fraction: perm p=0.023, sympy rho=-0.356
- t_pivots: perm p=0.042

**Tier 3 claims (raw significant but repo-confounded):**
- All message-layer features (metacognitive, insight, tentative, instead_contrast)
- reasoning_to_action_alignment, first_edit_position, deliberation_length
- These predict across repos but NOT within repos. They index difficulty, not behavior.

**Null controls (confirmed non-predictive):**
- Hyland hedging score: dead
- Random noise column: dead
- Total thinking length: dead (r=0.000)
- Epistemic markers ("I think", "I believe"): dead

## 3. Method

### 3.1 Task Selection and Agent Configuration

We selected 75 tasks from SWE-bench Lite (Jimenez et al., 2024) spanning 9 Python repositories: django, sympy, pytest-dev, scikit-learn, pylint-dev, psf, sphinx-doc, pallets, and astropy. Tasks were chosen to produce a blended pass rate near 50%, providing balanced classes for correlation analysis. Repository-level pass rates range from 0% (scikit-learn, sphinx-doc, astropy) to 100% (pallets), with the two largest repositories -- sympy (n=87 Sonnet runs, 41.4% pass) and django (n=44 Sonnet runs, 84.1% pass) -- providing the primary analytical strata.

Two models served as agents. Claude Sonnet 4.6 was invoked via `claude -p --model sonnet --output-format stream-json --verbose`, producing 183 validated runs across all 75 tasks. Codex GPT-5.4 was invoked via `codex exec`, producing 190 validated runs across 70 of the 75 tasks (five tasks were Sonnet-only due to infrastructure constraints). Both agents received the bug description and were instructed to fix it and run tests. No intervention, gating, or prompt augmentation was applied. Each run had a 30-minute wall-clock timeout.

Full stream-json traces were captured and stored in SQLite (WAL mode). Each trace record contains every tool call (tool name, parameters, result, `is_error` flag), reasoning text preceding each tool call (when present), and sequence numbers. Sonnet runs produced approximately 3,600 state-modifying tool calls total, of which 28.8% had per-call reasoning annotations. Codex runs had 60.1% per-call reasoning coverage.

### 3.2 Independent Validation

Agent self-report was not used for outcome labeling. This is a deliberate methodological choice: we discovered that using the agent's own test output as ground truth inflated three features to statistical significance that disappeared under independent validation. The agent has incentive structure (implicit in its training) to report success; its self-assessment cannot be treated as ground truth.

Independent validation proceeds as follows:

1. Copy the original repository to a fresh temporary directory.
2. Extract all Write and Edit operations from the raw stream-json trace.
3. Apply these edits to the fresh copy in sequence order.
4. Create a Python 3.10 virtual environment with SWE-bench-pinned dependencies.
5. Run the specific `FAIL_TO_PASS` tests from the SWE-bench dataset.
6. Label the run as pass or fail based on the test exit code.

Of the total runs attempted, 373 were successfully validated (183 Sonnet, 190 Codex) -- a 96% validation rate. Four runs were unrecoverable due to infrastructure failures (environment setup crashes unrelated to the agent's edits). Validation provenance is tracked per-run in the database. Pre-built validation environments in `/envs/` enable deterministic replay.

### 3.3 Behavioral Feature Extraction

We extract 24 features organized into three tiers plus a set of thinking-block features. All features are defined in Table 1.

**Tier 0 -- Structural features** are computed from the tool-call sequence alone, with no text analysis. These include error-streak length, early error rate, the normalized position of the first code edit, file count, edit churn, test invocation count, and total call count (used as a control variable).

**Tier 1 -- Linguistic features** are computed from per-call reasoning text using the Hyland (2005) hedging lexicon and related marker sets. Features in this tier measure hedge-word density, mean reasoning length per call, backtrack marker density, verification phrase density, and planning phrase density.

**Tier 2 -- Domain-specific features** are also computed from per-call reasoning text but use marker sets developed for this study rather than established lexicons. These capture metacognitive self-correction, tentative language, insight phrases, contrastive markers ("however", "but", "instead"), self-directive language ("let me", "I should"), and backtick identifier density. One cross-tier feature, `reasoning_to_action_alignment`, measures whether the reasoning text preceding an edit names the file about to be edited.

**CWC thinking features** are extracted from internal reasoning blocks (see Section 3.4) rather than from per-call reasoning annotations. These measure diagnostic precision (code-specific reference density), reasoning clarity (diagnostic precision minus confusion score), function reference density, compatibility/environment sentence fraction, and strategy pivot density.

**Aggregation method.** All linguistic and domain-specific features use mean aggregation: per-call values are computed as per-token densities, then averaged across calls within a run. We do not use sum aggregation. This choice controls for the task-length confound: failing runs produce 38% more state-modifying tool calls than passing runs (mean 22.9 vs. 16.6). Any feature aggregated by summation would be mechanically correlated with failure through call count alone. The task-length confound suppressed the metacognitive signal in raw sum correlations (rho rose from +0.308 to +0.494 after switching to mean aggregation with partial correlation controlling for `n_calls`).

**Table 1. Complete feature definitions (24 features).**

| Feature | Tier | Source | Definition |
|---------|------|--------|------------|
| `fail_streak_max` | 0 | tool_calls | Maximum consecutive error results in the tool-call sequence |
| `early_error_rate` | 0 | tool_calls | Fraction of calls returning errors in the first third of the trajectory |
| `first_edit_position` | 0 | tool_calls | Normalized position (0--1) of the first Edit or Write call |
| `unique_files_touched` | 0 | tool_calls | Count of distinct files edited |
| `edit_churn_rate` | 0 | tool_calls | Total edit operations divided by unique files touched |
| `test_run_count` | 0 | tool_calls | Count of Bash calls whose command contains "test" |
| `n_calls` | 0 | tool_calls | Total state-modifying tool calls (control variable) |
| `hedging_score` | 1 | reasoning_text | Density of Hyland hedge terms (might, could, perhaps, ...) per token |
| `deliberation_length` | 1 | reasoning_text | Mean characters per reasoning block across calls |
| `backtrack_count` | 1 | reasoning_text | Density of backtrack markers (actually, wait, instead, ...) per token |
| `verification_score` | 1 | reasoning_text | Density of verification phrases (let me check, verify, confirm, ...) per token |
| `planning_score` | 1 | reasoning_text | Density of planning phrases (first, then, next, ...) per token |
| `metacognitive_density` | 2 | reasoning_text | Density of self-correction markers per token |
| `tentative_density` | 2 | reasoning_text | Density of tentative language (let me try, maybe, not sure, ...) per token |
| `insight_density` | 2 | reasoning_text | Density of insight phrases (I understand, I see, actually, ...) per token |
| `instead_contrast_density` | 2 | reasoning_text | Density of contrastive markers (however, but, instead, ...) per token |
| `self_directive_density` | 2 | reasoning_text | Density of self-directive language (let me, I should, ...) per token |
| `precision_naming_score` | 2 | reasoning_text | Density of backtick-delimited identifiers per token |
| `reasoning_to_action_alignment` | X | reasoning_text + tool_calls | Binary: does reasoning preceding an edit name the target file? Mean across calls |
| `think_diagnostic_precision` | CWC | thinking blocks | Density of code-specific references (function names, file paths, line numbers) per 1K chars of internal reasoning |
| `think_reasoning_clarity` | CWC | thinking blocks | `diagnostic_precision` minus confusion score (hedging + tentative markers in thinking) |
| `think_t_func_refs` | CWC | thinking blocks | Density of function/method references per 1K chars of internal reasoning |
| `think_t_compat_fraction` | CWC | thinking blocks | Fraction of sentences in internal reasoning discussing compatibility or environment issues |
| `think_t_pivots` | CWC | thinking blocks | Density of strategy pivot markers ("let me try a different approach", ...) per 1K chars |

### 3.4 Thinking Block Extraction

Both models produce internal reasoning content that is hidden from the user but present in the stream-json trace. The two models use different formats:

- **Sonnet 4.6** produces extended thinking blocks. These appear in the stream-json trace as content blocks with `type="thinking"`, and the reasoning text is stored in the `"thinking"` key of each block (not the `"text"` key).
- **Codex GPT-5.4** produces reasoning items. These appear in the trace as items with `item.type="reasoning"`, and the reasoning text is stored in the `"text"` key.

Both models have 100% thinking-block coverage: every validated run contains internal reasoning content. Sonnet produced approximately 2.0 million characters of internal reasoning across 183 runs (mean 10,765 chars/run, median 2,758 chars/run, right-skewed). Codex produced approximately 944,000 characters across 190 runs (mean 5,754 chars/run, median 5,548 chars/run, more uniform distribution).

**Parser bug discovery and correction.** The original implementation of `trace_collector.py` read `block.get("text")` for all content blocks, including Sonnet thinking blocks. Because Sonnet stores internal reasoning in the `"thinking"` key rather than `"text"`, this returned empty strings for all thinking blocks. The consequence: the original 23-feature analysis (Tiers 0--2 plus the cross-tier feature) operated entirely on agent messages, not on internal thinking. The per-call reasoning coverage figure of 28.8% for Sonnet reflects the coverage of per-call reasoning annotations in agent messages, not thinking block availability. After fixing the parser to read the correct key, thinking block content was recovered for all 183 Sonnet runs. The five CWC thinking features were computed from this recovered content. This bug had the incidental benefit of keeping the Tier 0--2 feature analysis cleanly separated from thinking block content, and the original Tier 0--2 results remain valid.

### 3.5 Statistical Methods

The primary analytical challenge is repository-level heterogeneity: django passes at 84% while sympy passes at 41%. Pooling across repositories produces spurious correlations between features and outcomes whenever a feature's distribution varies by repository. We address this through a multi-layer statistical framework.

**Within-repo Spearman correlations.** We compute Spearman rank correlations between each feature and binary success (0/1) separately within django and sympy, the two repositories with sufficient sample size for per-repo analysis (Sonnet: django n=44, sympy n=87; Codex: django n=71, sympy n=84). All correlations use a custom implementation with correct tie handling and exact p-values from the regularized incomplete beta function, validated against scipy on known data.

**Fisher's combined p-value (CWC decomposition).** Within-repo p-values from django and sympy are combined using Fisher's method: chi-squared = -2 * sum(log(p_i)), df = 2k, where k is the number of repos. The weighted average rho uses sample-size weighting. This approach controls for between-repo confounds (different pass rates, different codebases) while preserving within-repo signal. A feature must show a consistent direction across repos to survive. An earlier version of the analysis used Mundlak-style cluster-mean centering to decompose within- and between-repo effects; that approach is superseded by the Fisher-combined method reported here.

**Within-repo permutation test.** For each of 10,000 permutations, success labels are shuffled independently within each repository, preserving repo-level pass rates. The test statistic is the weighted average mean difference (pass minus fail feature value) across repos. A feature's observed effect must exceed 95% of permuted effects to be deemed significant. This test controls for between-repo confounds but does not control for within-repo task difficulty variation. A stronger test -- within-task permutation on tasks with mixed pass/fail outcomes across replicates -- was conducted on 7 Sonnet tasks (35 runs) with mixed outcomes and provides a stricter faithfulness check, but requires sufficient mixed-outcome tasks and cannot be applied dataset-wide.

**Cross-model comparison.** For each feature, we compare the direction and significance of within-repo Spearman correlations between Sonnet and Codex on the 70 shared tasks. Features are classified as cross-model (same significant direction in both models), model-specific (significant in one model only), or polarity-flipped (significant in both models with opposite signs).

**Multiple comparison correction.** Bonferroni correction at alpha/23 = 0.0022 is applied to the pooled analysis (23 features excluding `n_calls`, which serves as a control). The CWC decomposition and permutation tests provide independent multiple-comparison safeguards: the CWC approach reduces the effective number of comparisons by requiring within-repo consistency, and the permutation test provides a non-parametric p-value that accounts for the full feature-selection procedure within each permutation.

**What the permutation test controls and does not control.** The within-repo permutation test eliminates between-repo confounds by construction: because labels are shuffled within each repo independently, any feature whose apparent association with success is driven by repo-level pass rate differences will not survive the test. This is precisely the confound that inflated `reasoning_to_action_alignment` to headline significance in the pooled analysis (permutation p = 0.35, retracted). However, the test does not control for within-repo task difficulty variation. If a feature correlates with task difficulty within a repository (e.g., harder tasks produce longer error streaks and also fail more often), the permutation test will still find it significant. The within-task permutation on mixed-outcome tasks partially addresses this but is limited by the small number of such tasks (7 for Sonnet, 5 for Codex).
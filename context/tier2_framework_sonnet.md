# Tier 2 Semantic Analysis Framework — Sonnet's Proposal

## Key Proposals (18 new features in 3 waves)

### Wave A (from existing DB, immediate):
- S1: fail_streak_bash_content — error detection via result content, not just is_error flag
- S2: edit_precision_ratio — surgical vs broad edits (min/max string length ratio)
- S4: file_touch_entropy — how diffuse are the agent's edits across files
- L1: wrong_stuck_density — "wrong", "issue", "bug" in reasoning (negative direction)
- L2: precision_naming_score — backtick-quoted terms, CamelCase, file paths in reasoning (positive)
- L3: self_directive_density — "I need to", "let me", "I should" (negative direction)
- L4: metacognitive_interruption_density — "wait", "actually", "hmm" normalized (positive)
- L5: causal_reasoning_density — "because", "since", "therefore" (positive)
- L6: instead_contrast_density — "instead", "rather than" (positive)

### Wave B (requires re-parsing or computation):
- S3: read_before_write_ratio — read-only calls before each Edit/Write
- S5: error_recovery_pattern — fail->succeed vs fail->fail transition ratio
- S6: bash_command_complexity — pipe/flag/subshell count
- S7: trajectory_front_loading — edit_centroid (when do edits happen)
- S8: test_run_ratio — fraction of Bash calls that are test invocations

### Wave C (interaction, requires Wave A+B):
- I1: reasoning_to_action_alignment — does reasoning mention the file about to be edited
- I2: next_call_error_predictability — do linguistic features predict call-level errors
- I3: reasoning_length_action_type_interaction — more reasoning before committed vs exploratory
- I4: post_error_reasoning_uplift — does agent reason more deeply after errors

### Existing Feature Reforms:
- step_index: use percentile bins (Q1-Q4) not fixed thresholds
- prior_failure_streak: check if is_error is actually populated for Bash (may need content analysis)
- tool_switch_rate: replace with exploration_ratio (reads/total)
- hedging_score: retain for completeness, do not use as primary
- deliberation_length: replace with reasoning_density (length/total_calls) or variance
- alternatives_considered: replace with branching_language ("or", "instead")
- planning_score: compute for first quartile only (early planning)

### Statistical Protocol:
- Bonferroni across full feature set (m=28)
- Pre-registered directions for every feature
- Spearman at task level (n=71)
- Logistic regression with top features only if they clear individual Bonferroni
- Clustered SEs at run level for any call-level analysis

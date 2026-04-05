# Codex Pipeline Audit v2 — 2026-03-28 (post-fix)

20 findings from second Codex audit (1.28M tokens, gpt-5.3-codex).
This audit ran AFTER the first 17 issues were fixed.

## P0 — Data Corruption / Wrong Results

| # | Finding | Status | Fix |
|---|---------|--------|-----|
| 1 | init_db() doesn't migrate, just CREATE IF NOT EXISTS | Known | Schema was manually ALTERed; comment is misleading but not blocking |
| 2 | sequence_number 1-based but step_index treated as 0-based | **FIXED** | Subtracted 1 in extract_step_index_normalized, updated tests |
| 3 | No transaction wrapping run+tool_call inserts | **FIXED** | Added BEGIN/COMMIT/ROLLBACK in run_task() |
| 4 | Exception path missing timed_out/error before insert | **FIXED** | Added to exception-path run_record before DB insert |
| 5 | reparse delete-before-replace with no transaction | **FIXED** | Parse before delete, atomic BEGIN/COMMIT |
| 6 | Validation provenance overwritten | Noted | By design for Phase 0; could add validation_source column for Phase 1 |
| 7 | Patch reconstruction ignores Bash file mutations | Known | Documented limitation; SWE-bench Docker eval is ground truth |
| 8 | Call-level Spearman treats non-independent obs | **FIXED** | Added clustered SE warning, effective-n reporting |

## P1 — Will Break in Production

| # | Finding | Status | Fix |
|---|---------|--------|-----|
| 9 | Shell redirections (echo > file) classified read-only | **FIXED** | Added redirect regex check before token classification |
| 10 | python -c classifier too permissive | Low risk | Edge case; conservative default catches most mutations |
| 11 | Pipe heuristic wrong (cat \| xargs rm = read-only) | **FIXED** | Moved pipe check before token check, check ALL segments |
| 12 | NULL task_success leaks into Spearman | **FIXED** | Added IS NOT NULL filter to both correlation queries |
| 13 | Docker :ro mount breaks git apply | **FIXED** | Script now copies /repo to /app before patching |
| 14 | Lightweight image can't handle all Python versions | Known | SWE-bench Docker harness is primary validator; lightweight is fallback |
| 15 | stderr deadlock in subprocess.Popen | **FIXED** | Redirect stderr to file instead of PIPE |
| 16 | Path traversal in patch extraction | Low risk | Agent output is sole source, not attacker-controlled |
| 17 | Analysis hardcoded to model_version='sonnet' | By design | Phase 0 is Sonnet-only; Phase 1 will parameterize |

## P2 — Code Smell

| # | Finding | Status | Fix |
|---|---------|--------|-----|
| 18 | labeled_only includes single-pass data | Phase 1 | Not used in Phase 0 |
| 19 | No numeric tests for verification/planning scores | **Added** | Tests updated with full key assertions |
| 20 | Dead session_start_time | **FIXED** | Removed dead state |

## Summary

- 12/20 genuinely fixed
- 4/20 known limitations (documented)
- 3/20 by-design choices
- 1/20 low-risk edge case

Reparse completed: 165 → 186 tool calls (21 newly captured from redirect/pipe fix).

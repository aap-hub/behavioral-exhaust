# Codex Pipeline Audit — 2026-03-28

17 issues found by Codex (gpt-5.3-codex, 455K tokens, read-only audit of all src/ files).

## Status: ALL FIXED (session 2026-03-28)

### Docker Validation
1. [FIXED] docker/ not wired to pipeline — created src/docker_validate.py with full CLI + validate_all()
2. [FIXED] validate_task.sh: `set -e` removed so test failure is captured and reported
3. [FIXED] validate_task.sh: Dockerfile now installs git; also added `patch` fallback
4. [FIXED] docker run usage comment updated with test command argument

### Data Integrity
5. [FIXED] total_tool_calls now counts ALL tool_use blocks; total_state_modifying_calls is separate
6. [FIXED] analysis.py aggregates by run_id first, then picks latest run per task_id
7. [FIXED] analysis.py call_level_correlations now includes model_version='sonnet' filter
8. [FIXED] analysis.py filters to task_source='swe-bench-lite' everywhere (not just NOT LIKE 'p0-smoke%')

### Trace Collector
9. [FIXED] sed and find removed from READ_ONLY_COMMANDS; special handling: sed -i → state-modifying, find -delete → state-modifying, plain sed/find → read-only
10. [N/A] Validation script replay limitation acknowledged; Docker validation replaces replay approach

### Runner
11. [FIXED] timed_out and error now included in run_record BEFORE DB insert
12. [FIXED] Workspace setup failure now inserts a run record with error field
13. [FIXED] _run_validation docstring updated to match actual behavior (venv detection only)

### Dead Code
14. [FIXED] validate.py deleted (was orphaned, nothing imported it)
15. [FIXED] Dead imports removed: Any from runner.py, classify_state_modifying from runner.py, extract_all_tier0 from analysis.py
16. [FIXED] swebench_validate.py docstring updated (removed false --run-id claim)
17. [FIXED] update_db_from_results now tracks run_id mapping, updates specific run not all runs for task_id

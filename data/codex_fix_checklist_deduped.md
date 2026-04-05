# Codex Audit Fix Checklist — Deduplicated

40 raw findings from 18 audit cycles. After deduplication: **13 unique issues**.

## ALREADY FIXED (verify only)

- [x] **A: conn.commit() inside insert helpers breaks transactions** (P0-01/03/05, P1-05/16/23)
  Fixed: `if not conn.in_transaction: conn.commit()` in db.py insert_run/insert_tool_call
  VERIFY: the fix is in place and works

- [x] **B: xargs in READ_ONLY_COMMANDS** (P1-02/10/13/20)
  Fixed: removed xargs from READ_ONLY_COMMANDS, handled in pipe logic
  VERIFY: `xargs rm` classified as state-modifying

- [x] **C: Unknown git subcommands default read-only** (P1-11)
  Fixed: unknown git subcommands now fall through to state-modifying
  VERIFY: `git foo` classified as state-modifying

- [x] **D: Redirect regex misses no-space redirections** (P1-19)
  Partially fixed: added redirect check. VERIFY: `echo hi >out.txt` caught

- [x] **E: Call-level Spearman inflated n** (P1-22, P2-04)
  Fixed: added warning about effective n. The analysis prints the caveat.
  VERIFY: warning is displayed

## NEEDS FIXING

- [ ] **F: Compound commands (&&, ;) classified by first token only** (P1-01/07/18/26)
  `grep foo && rm bar` classified as read-only because grep is whitelisted.
  The pipe logic only handles `|`, not `&&` or `;`.
  FIX: Split on `&&` and `;`, check ALL segments, any mutating segment = state-modifying.

- [ ] **G: prior_failure_streak treats missing/bad results as success** (P1-09/24, P2-05/06)
  In analysis.py extract_features_for_all(), unparseable tool_result_json -> True (success).
  FIX: Treat missing/unparseable as None (unknown), don't reset streak.

- [ ] **H: Reasoning misattributed in multi-tool messages** (P1-12)
  If assistant message has text->tool->text->tool, both tools get ALL text.
  FIX: Split reasoning at tool_use boundaries. Each tool gets only preceding text.

- [ ] **I: Patch extraction drops Bash mutations and failed edits** (P0-04, P1-04/06/08/14/15/21/25)
  swebench_validate.py only replays Write/Edit, ignores sed -i/mv/patch.
  Edit replay silently skips when old_string not found.
  NOTE: This is less critical now since independent_validate.py handles validation.
  FIX: Log warnings when edits fail. Don't silently skip.

- [ ] **J: Validation provenance overwritten** (P0-02, P1-03)
  Multiple validators overwrite runs.task_success and notes.
  FIX: Add validation_source and validation_timestamp columns. Don't overwrite docker labels.

- [ ] **K: update_features() commits per row** (P2-01)
  FIX: Respect caller's transaction (same pattern as insert helpers).

- [ ] **L: Retry detection truncates Bash at 80 chars** (P2-07)
  FIX: Use full command or hash of command.

- [ ] **M: Malformed JSON lines silently dropped** (P1-17)
  FIX: Count dropped lines and log warning if > 0. Store count in runs table.

- [ ] **N: git fetch classified as state-modifying** (P2-08)
  FIX: Remove fetch from _GIT_MUTATING_SUBCOMMANDS. It mutates refs but not workspace files.

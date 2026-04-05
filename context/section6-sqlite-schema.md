# §6 Replacement: Data Store — SQLite in WAL Mode

Replace the entire current §6 (from "## 6." to "## 7.") with this content.

## 6. Data Store — SQLite in WAL Mode

All experimental data is stored in a single SQLite database (`data/uga.db`) in WAL (Write-Ahead Logging) mode. WAL enables concurrent reads during writes, supporting parallel task runs. SQLite replaces JSONL files throughout — no sidecar files, no in-place rewrites, full transactional integrity. JSONL is an export format only (for the anonymized release bundle).

**Design principle:** Capture ALL raw exhaust so features can be retroactively re-extracted with different algorithms. Extracted features are computed columns populated on insert; the raw text is always preserved for back-testing theories.

### 6.1 Schema

```sql
-- Run-level metadata (one row per task execution)
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    phase INTEGER NOT NULL,              -- 0 or 1
    condition TEXT NOT NULL,              -- ungated|behavioral-gate|critic-gate|adaptive-gate
    replicate_k INTEGER DEFAULT 1,       -- which of PASS_K replicates
    model_version TEXT,
    seed INTEGER,
    start_time TEXT, end_time TEXT,
    total_tokens INTEGER,
    total_tool_calls INTEGER,
    total_state_modifying_calls INTEGER,
    task_success BOOLEAN,                -- validation_command exit 0
    exit_code INTEGER,
    wall_clock_seconds REAL,
    raw_stream_json TEXT,                -- FULL Claude Code output for replay/re-extraction
    created_at TEXT DEFAULT (datetime('now'))
);

-- Core analysis unit: one row per state-modifying tool call
CREATE TABLE tool_calls (
    decision_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    task_id TEXT NOT NULL,
    phase INTEGER NOT NULL,
    condition TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    -- Raw data (preserved for retroactive re-extraction)
    tool_name TEXT NOT NULL,             -- Write|Edit|Bash
    tool_params_json TEXT,               -- full params as JSON
    tool_result_json TEXT,               -- full result as JSON
    reasoning_text TEXT,                 -- FULL reasoning text preceding this call
    reasoning_token_count INTEGER,
    -- Tier 0 features (deterministic)
    step_index_normalized REAL,
    prior_failure_streak INTEGER,
    retry_count INTEGER,
    tool_switch_rate REAL,
    -- Tier 1 features (linguistic)
    hedging_score REAL,
    deliberation_length INTEGER,
    alternatives_considered INTEGER,
    backtrack_count INTEGER,
    -- Computed (populated during analysis)
    behavioral_combined_score REAL,
    -- Gate (Phase 1 only)
    gate_threshold REAL,
    gate_outcome TEXT,                   -- proceed|blocked|escalate|null
    -- Machine labeling
    pre_call_score REAL,                 -- validation score BEFORE this call
    post_call_score REAL,                -- validation score AFTER this call
    machine_label TEXT,                  -- machine_correct|machine_incorrect|machine_ambiguous
    -- Failure classification
    failure_class TEXT,
    failure_severity TEXT,
    flags TEXT,                          -- JSON array
    created_at TEXT DEFAULT (datetime('now'))
);

-- Human labels (separate table, preserves both passes for kappa)
CREATE TABLE labels (
    label_id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT NOT NULL REFERENCES tool_calls(decision_id),
    pass_number INTEGER NOT NULL,        -- 1 or 2
    label TEXT NOT NULL,                 -- correct|incorrect|uncertain
    labeled_at TEXT DEFAULT (datetime('now')),
    UNIQUE(decision_id, pass_number)
);

-- Final labels (VIEW, not stored — always consistent)
CREATE VIEW labels_final AS
SELECT tc.decision_id, tc.machine_label,
    l1.label AS human_pass1, l2.label AS human_pass2,
    CASE
        WHEN tc.machine_label IN ('machine_correct','machine_incorrect')
            THEN REPLACE(tc.machine_label, 'machine_', '')
        WHEN l1.label IS NOT NULL AND l2.label IS NOT NULL AND l1.label = l2.label
            THEN l2.label
        WHEN l1.label IS NOT NULL AND l2.label IS NOT NULL AND l1.label != l2.label
            THEN 'uncertain'
        WHEN l2.label IS NOT NULL THEN l2.label
        ELSE tc.machine_label
    END AS label_final,
    CASE WHEN tc.machine_label IN ('machine_correct','machine_incorrect')
        THEN 'machine' ELSE 'human' END AS label_source
FROM tool_calls tc
LEFT JOIN labels l1 ON tc.decision_id = l1.decision_id AND l1.pass_number = 1
LEFT JOIN labels l2 ON tc.decision_id = l2.decision_id AND l2.pass_number = 2;

-- Cross-model comparison (preserves full Codex response for re-parsing)
CREATE TABLE critic_comparisons (
    comparison_id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT NOT NULL REFERENCES tool_calls(decision_id),
    critic_model TEXT,
    critic_prompt TEXT,                  -- full prompt sent
    critic_response_raw TEXT,            -- FULL raw response
    critic_proposed_tool TEXT,
    critic_proposed_params TEXT,
    critic_agreement TEXT,               -- full|partial|disagree
    critic_latency_ms INTEGER,
    flags TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Interaction matrix cells (analysis results)
CREATE TABLE analysis_cells (
    cell_id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase INTEGER NOT NULL,
    signal_type TEXT NOT NULL,            -- tier0|tier1|tier0+tier1|critic
    trajectory_bin TEXT NOT NULL,         -- early|mid|late|all
    n_observations INTEGER,
    spearman_rho REAL, spearman_p REAL,
    auc_roc REAL, auc_roc_ci_lower REAL, auc_roc_ci_upper REAL,
    ece REAL,
    critic_precision REAL, critic_recall REAL, critic_fdr REAL,
    computed_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_tc_run ON tool_calls(run_id);
CREATE INDEX idx_tc_task ON tool_calls(task_id);
CREATE INDEX idx_tc_phase ON tool_calls(phase);
CREATE INDEX idx_critic_decision ON critic_comparisons(decision_id);
CREATE INDEX idx_labels_decision ON labels(decision_id);
```

### 6.2 What's Preserved for Retroactive Analysis

| Field | Table | Purpose |
|-------|-------|---------|
| `raw_stream_json` | runs | Full Claude Code output — enables complete replay and re-extraction with different algorithms |
| `reasoning_text` | tool_calls | Raw text from which Tier 1 features are extracted — enables Tier 2 modal decomposition without re-running |
| `tool_params_json`, `tool_result_json` | tool_calls | Full tool call data — enables re-labeling, re-classification |
| `critic_response_raw` | critic_comparisons | Full Codex response — enables re-parsing with different extraction rules |

### 6.3 Schema Invariants

- `behavioral_combined_score` is NULL until logistic regression is fit during analysis
- `gate_outcome` is NULL when `condition == 'ungated'`
- `machine_label` is populated for all calls (automated); `labels` table entries exist only for `machine_ambiguous` calls
- `label_final` (from the VIEW) combines machine and human labels per the hybrid protocol (§5.4)
- `failure_class` and `failure_severity` are non-null only for calls where `label_final == 'incorrect'`
- Failure class values map to §0.4: `uncertainty`, `capability`, `coordination`, `spec`, `infrastructure`
- `flags` is a JSON array; common values: `["critic_unavailable"]`, `["behavioral_extraction_error"]`
- **Label reconciliation** is a VIEW, not a stored value — always consistent, never stale
- **κ computation** uses the `labels` table directly (pass 1 vs pass 2), not the reconciled view

### 6.4 Cross-References Updated for SQLite

All references to "JSONL trace file," "trace record," "sidecar file," and "in-place rewrite" throughout the document should be interpreted as SQLite operations:
- "Write one record to trace" → INSERT INTO tool_calls
- "Append to trace" → INSERT INTO tool_calls
- "Label reconciliation" → SELECT from labels_final VIEW
- "Anonymize traces" → Export from SQLite to anonymized DB/JSONL
- "Schema invariant" → enforced by SQL constraints and the VIEW definition

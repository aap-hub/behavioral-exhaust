"""
UGA Harness — SQLite Data Store (WAL mode)

All experimental data lives in a single SQLite database at data/uga.db.
WAL mode enables concurrent reads during writes, supporting parallel task runs.

Design principle: capture ALL raw exhaust so features can be retroactively
re-extracted with different algorithms. Extracted features are computed columns
populated on insert; the raw text is always preserved for back-testing.

Schema is intentionally denormalized per mentor feedback: labels are flattened
into tool_calls (label_pass1, label_pass2, label_final) rather than living in
a separate table. At ~180 rows, normalization adds complexity without benefit.
"""

import os
import sqlite3
from pathlib import Path
from typing import Any, Optional


# Database lives at data/uga.db relative to project root.
# Resolve from this file's location: src/db.py -> project_root/data/uga.db
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = _PROJECT_ROOT / "data" / "uga.db"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
-- Run-level metadata (one row per task execution)
CREATE TABLE IF NOT EXISTS runs (
    run_id              TEXT PRIMARY KEY,
    task_id             TEXT NOT NULL,
    phase               INTEGER NOT NULL,           -- 0 or 1
    condition           TEXT NOT NULL,               -- ungated|behavioral-gate|critic-gate|adaptive-gate
    replicate_k         INTEGER DEFAULT 1,           -- which of PASS_K replicates
    model_version       TEXT,
    seed                INTEGER,
    start_time          TEXT,
    end_time            TEXT,
    total_tokens        INTEGER,
    task_success        BOOLEAN,                     -- validation_command exit 0
    exit_code           INTEGER,
    wall_clock_seconds  REAL,
    raw_stream_json     TEXT,                         -- FULL Claude Code output for replay/re-extraction
    total_tool_calls    INTEGER,
    total_state_modifying_calls INTEGER,
    timed_out           BOOLEAN DEFAULT 0,
    error               TEXT,
    task_source         TEXT,
    wave                INTEGER DEFAULT 1,
    notes               TEXT,
    validation_source   TEXT,
    validation_timestamp TEXT,
    created_at          TEXT DEFAULT (datetime('now'))
);

-- Core analysis unit: one row per state-modifying tool call.
-- Labels are flattened here (no separate labels table) per mentor guidance:
-- "5 tables for ~180 rows is over-normalized."
CREATE TABLE IF NOT EXISTS tool_calls (
    decision_id                 TEXT PRIMARY KEY,
    run_id                      TEXT NOT NULL REFERENCES runs(run_id),
    task_id                     TEXT NOT NULL,
    phase                       INTEGER NOT NULL,
    condition                   TEXT NOT NULL,

    -- Position in the trajectory
    sequence_number             INTEGER NOT NULL,
    timestamp                   TEXT NOT NULL,

    -- Raw data (preserved for retroactive re-extraction)
    tool_name                   TEXT NOT NULL,           -- Write|Edit|Bash
    tool_params_json            TEXT,                     -- full params as JSON
    tool_result_json            TEXT,                     -- full result as JSON
    reasoning_text              TEXT,                     -- FULL reasoning text preceding this call
    reasoning_token_count       INTEGER,

    -- Tier 0 features (deterministic, zero-cost)
    step_index_normalized       REAL,
    prior_failure_streak        INTEGER,
    retry_count                 INTEGER,
    tool_switch_rate            REAL,

    -- Tier 1 features (linguistic, from reasoning text)
    hedging_score               REAL,
    deliberation_length         INTEGER,
    alternatives_considered     INTEGER,
    backtrack_count             INTEGER,

    -- Tier 1+ features (discovered via exhaust mining)
    verification_score          REAL,
    planning_score              REAL,

    -- Combined score (populated during analysis, NULL until logistic regression is fit)
    behavioral_combined_score   REAL,

    -- Gate fields (Phase 1 only; NULL when condition == 'ungated')
    gate_threshold              REAL,
    gate_outcome                TEXT,                     -- proceed|blocked|escalate|null

    -- Machine scoring
    pre_call_score              REAL,                     -- validation score BEFORE this call
    post_call_score             REAL,                     -- validation score AFTER this call
    machine_label               TEXT,                     -- machine_correct|machine_incorrect|machine_ambiguous

    -- Human labels (flattened — both passes preserved for kappa computation)
    label_pass1                 TEXT,                     -- correct|incorrect|uncertain
    label_pass2                 TEXT,                     -- correct|incorrect|uncertain
    label_final                 TEXT,                     -- reconciled label

    -- Failure classification (non-null only when label_final == 'incorrect')
    failure_class               TEXT,                     -- uncertainty|capability|coordination|spec|infrastructure
    failure_severity            TEXT,
    flags                       TEXT,                     -- JSON array, e.g. ["critic_unavailable"]

    created_at                  TEXT DEFAULT (datetime('now'))
);

-- Cross-model comparison (preserves full Codex response for re-parsing)
CREATE TABLE IF NOT EXISTS critic_comparisons (
    comparison_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id         TEXT NOT NULL REFERENCES tool_calls(decision_id),
    critic_model        TEXT,
    critic_prompt       TEXT,                     -- full prompt sent
    critic_response_raw TEXT,                     -- FULL raw response
    critic_proposed_tool    TEXT,
    critic_proposed_params  TEXT,
    critic_agreement    TEXT,                     -- full|partial|disagree
    critic_latency_ms   INTEGER,
    flags               TEXT,
    created_at          TEXT DEFAULT (datetime('now'))
);

-- Indexes for the queries we actually run (see analysis-protocol.md)
CREATE INDEX IF NOT EXISTS idx_tc_run       ON tool_calls(run_id);
CREATE INDEX IF NOT EXISTS idx_tc_task      ON tool_calls(task_id);
CREATE INDEX IF NOT EXISTS idx_tc_phase     ON tool_calls(phase);
CREATE INDEX IF NOT EXISTS idx_critic_decision ON critic_comparisons(decision_id);
"""


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open a connection to the database with WAL mode and foreign keys enabled.

    Args:
        db_path: Override the default database path. Useful for tests.

    Returns:
        sqlite3.Connection configured for WAL mode.
    """
    path = db_path or str(DB_PATH)

    # Ensure the parent directory exists.
    os.makedirs(os.path.dirname(path), exist_ok=True)

    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # Return rows as sqlite3.Row so callers can use both index and name access.
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Create the database and all tables if they don't already exist.

    This is idempotent — safe to call on every startup.

    Args:
        db_path: Override the default database path. Useful for tests.

    Returns:
        sqlite3.Connection with schema applied.
    """
    conn = get_connection(db_path)
    conn.executescript(_SCHEMA_SQL)
    # Codex #J: Add validation provenance columns if missing (migration)
    existing_cols = _get_table_columns(conn, "runs")
    if "validation_source" not in existing_cols:
        conn.execute("ALTER TABLE runs ADD COLUMN validation_source TEXT")
    if "validation_timestamp" not in existing_cols:
        conn.execute("ALTER TABLE runs ADD COLUMN validation_timestamp TEXT")

    # Phase 1: gate_decisions table for recording gate evaluations
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS gate_decisions (
            decision_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            tool_call_sequence INTEGER,
            gate_type TEXT,
            gate_timing TEXT,
            verdict TEXT,
            reason TEXT,
            alignment_score REAL,
            deliberation_length INTEGER,
            critic_response TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_gd_run ON gate_decisions(run_id);
        CREATE INDEX IF NOT EXISTS idx_gd_verdict ON gate_decisions(verdict);
    """)

    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Insert helpers
# ---------------------------------------------------------------------------

def _get_table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the set of column names for a table."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] if isinstance(row, tuple) else row["name"] for row in rows}


def insert_run(conn: sqlite3.Connection, run: dict) -> None:
    """Insert a single run record.

    Accepts any dict keys that match column names in the runs table.
    Unknown keys are silently ignored.

    Args:
        conn: Active database connection.
        run:  Dict with keys matching the runs table columns.
              At minimum: run_id, task_id, phase, condition.
    """
    valid_cols = _get_table_columns(conn, "runs")
    # Filter to only keys that match actual columns (exclude auto-managed ones)
    data = {k: v for k, v in run.items() if k in valid_cols}
    if not data:
        return

    cols = list(data.keys())
    placeholders = ", ".join(f":{c}" for c in cols)
    col_names = ", ".join(cols)

    conn.execute(
        f"INSERT INTO runs ({col_names}) VALUES ({placeholders})",
        data,
    )
    # With isolation_level=None (autocommit), each statement is its own
    # transaction unless the caller issued an explicit BEGIN.  Callers that
    # need atomicity use BEGIN/COMMIT themselves; this commit is harmless
    # inside an explicit transaction (SQLite ignores nested COMMIT).
    conn.commit()


def insert_tool_call(conn: sqlite3.Connection, tc: dict) -> None:
    """Insert a single tool-call record.

    Accepts any dict keys that match column names in the tool_calls table.
    Unknown keys are silently ignored.

    Args:
        conn: Active database connection.
        tc:   Dict with keys matching the tool_calls table columns.
              At minimum: decision_id, run_id, task_id, phase, condition,
              sequence_number, timestamp, tool_name.
    """
    valid_cols = _get_table_columns(conn, "tool_calls")
    data = {k: v for k, v in tc.items() if k in valid_cols}
    if not data:
        return

    cols = list(data.keys())
    placeholders = ", ".join(f":{c}" for c in cols)
    col_names = ", ".join(cols)

    conn.execute(
        f"INSERT INTO tool_calls ({col_names}) VALUES ({placeholders})",
        data,
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Update helpers
# ---------------------------------------------------------------------------

def update_features(conn: sqlite3.Connection, decision_id: str,
                    features: dict) -> None:
    """Update extracted features on an existing tool-call row.

    Used after the feature extraction pass (features.py) populates
    Tier 0 and Tier 1 columns.

    Args:
        conn:        Active database connection.
        decision_id: The tool-call row to update.
        features:    Dict of column_name -> value for any feature columns.
                     Only keys matching known feature columns are applied.
    """
    # Whitelist of columns that may be updated as features.
    _FEATURE_COLS = {
        "step_index_normalized", "prior_failure_streak", "retry_count",
        "tool_switch_rate", "hedging_score", "deliberation_length",
        "alternatives_considered", "backtrack_count",
        "verification_score", "planning_score",
        "behavioral_combined_score",
    }

    # Filter to only allowed columns.
    updates = {k: v for k, v in features.items() if k in _FEATURE_COLS}
    if not updates:
        return

    set_clause = ", ".join(f"{col} = :{col}" for col in updates)
    updates["decision_id"] = decision_id

    conn.execute(
        f"UPDATE tool_calls SET {set_clause} WHERE decision_id = :decision_id",
        updates,
    )
    conn.commit()


def update_label(conn: sqlite3.Connection, decision_id: str,
                 pass_number: int, label: str) -> None:
    """Record a labeling pass result on a tool-call row.

    Supports the blinded dual-pass protocol: pass 1 and pass 2 are recorded
    independently. After pass 2 is written, label_final is reconciled
    automatically.

    Args:
        conn:        Active database connection.
        decision_id: The tool-call row to update.
        pass_number: 1 or 2.
        label:       One of: correct, incorrect, uncertain.
    """
    if pass_number not in (1, 2):
        raise ValueError(f"pass_number must be 1 or 2, got {pass_number}")
    if label not in ("correct", "incorrect", "uncertain"):
        raise ValueError(f"label must be correct|incorrect|uncertain, got {label}")

    col = f"label_pass{pass_number}"
    conn.execute(
        f"UPDATE tool_calls SET {col} = :label WHERE decision_id = :decision_id",
        {"label": label, "decision_id": decision_id},
    )

    # Reconcile label_final after every update.
    # Rule: if both passes agree, use that. If they disagree, mark uncertain.
    # Machine labels take precedence if present and unambiguous.
    row = conn.execute(
        "SELECT machine_label, label_pass1, label_pass2 FROM tool_calls "
        "WHERE decision_id = :did",
        {"did": decision_id},
    ).fetchone()

    if row is not None:
        ml = row["machine_label"]
        p1 = row["label_pass1"]
        p2 = row["label_pass2"]

        # Machine labels that are decisive take precedence.
        if ml in ("machine_correct", "machine_incorrect"):
            final = ml.replace("machine_", "")
        elif p1 is not None and p2 is not None:
            final = p2 if p1 == p2 else "uncertain"
        elif p2 is not None:
            final = p2
        elif p1 is not None:
            final = p1
        else:
            final = None

        if final is not None:
            conn.execute(
                "UPDATE tool_calls SET label_final = :final "
                "WHERE decision_id = :did",
                {"final": final, "did": decision_id},
            )

    conn.commit()


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_tool_calls_for_analysis(
    conn: sqlite3.Connection,
    phase: Optional[int] = None,
    task_id: Optional[str] = None,
    labeled_only: bool = False,
) -> list[dict]:
    """Retrieve tool-call rows for analysis.

    Returns dicts (not Row objects) so callers can serialize to JSON or
    feed directly into pandas.

    Args:
        conn:         Active database connection.
        phase:        Filter to a specific phase (0 or 1). None = all.
        task_id:      Filter to a specific task. None = all.
        labeled_only: If True, only return rows where label_final is not NULL.

    Returns:
        List of dicts, one per tool-call row.
    """
    clauses = []
    params: dict[str, Any] = {}

    if phase is not None:
        clauses.append("phase = :phase")
        params["phase"] = phase

    if task_id is not None:
        clauses.append("task_id = :task_id")
        params["task_id"] = task_id

    if labeled_only:
        clauses.append("label_final IS NOT NULL")

    where = "WHERE " + " AND ".join(clauses) if clauses else ""

    rows = conn.execute(
        f"SELECT * FROM tool_calls {where} ORDER BY run_id, sequence_number",
        params,
    ).fetchall()

    # Convert sqlite3.Row objects to plain dicts.
    return [dict(row) for row in rows]


def insert_critic_comparison(conn: sqlite3.Connection, comp: dict) -> None:
    """Insert a cross-model critic comparison record.

    Args:
        conn: Active database connection.
        comp: Dict with keys matching the critic_comparisons table columns.
    """
    conn.execute(
        """
        INSERT INTO critic_comparisons (
            decision_id, critic_model, critic_prompt,
            critic_response_raw, critic_proposed_tool,
            critic_proposed_params, critic_agreement,
            critic_latency_ms, flags
        ) VALUES (
            :decision_id, :critic_model, :critic_prompt,
            :critic_response_raw, :critic_proposed_tool,
            :critic_proposed_params, :critic_agreement,
            :critic_latency_ms, :flags
        )
        """,
        {
            "decision_id":          comp.get("decision_id"),
            "critic_model":         comp.get("critic_model"),
            "critic_prompt":        comp.get("critic_prompt"),
            "critic_response_raw":  comp.get("critic_response_raw"),
            "critic_proposed_tool": comp.get("critic_proposed_tool"),
            "critic_proposed_params": comp.get("critic_proposed_params"),
            "critic_agreement":     comp.get("critic_agreement"),
            "critic_latency_ms":    comp.get("critic_latency_ms"),
            "flags":                comp.get("flags"),
        },
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Quick self-test when run directly.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Initializing database at {DB_PATH} ...")
    conn = init_db()

    # Verify tables exist.
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    print(f"Tables: {[t['name'] for t in tables]}")

    # Verify WAL mode.
    mode = conn.execute("PRAGMA journal_mode").fetchone()
    print(f"Journal mode: {mode[0]}")

    conn.close()
    print("Done.")

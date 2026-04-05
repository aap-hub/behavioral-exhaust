"""
Tests for Phase 1 gated runner (src/gated_runner.py).

Covers:
  - Post-hoc gate application to stored runs
  - Gate metric computation
  - Integration with DB schema
"""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import uuid

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from gate import (
    GateConfig, GateDecision, IntrospectiveGate,
    init_gate_decisions_table, store_gate_decision,
)
from gated_runner import compute_gate_metrics


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def populated_db():
    """DB with runs, tool_calls, and gate_decisions for testing metrics."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            phase INTEGER NOT NULL,
            condition TEXT NOT NULL,
            task_success BOOLEAN,
            validation_source TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tool_calls (
            decision_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            phase INTEGER NOT NULL,
            condition TEXT NOT NULL,
            sequence_number INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            tool_params_json TEXT,
            tool_result_json TEXT,
            reasoning_text TEXT,
            reasoning_token_count INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );

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

    # Insert test data: 2 passing runs, 2 failing runs
    runs = [
        ("run-pass1", "task-1", 0, "ungated", 1, "independent"),
        ("run-pass2", "task-2", 0, "ungated", 1, "independent"),
        ("run-fail1", "task-3", 0, "ungated", 0, "independent"),
        ("run-fail2", "task-4", 0, "ungated", 0, "independent"),
    ]
    for r in runs:
        conn.execute(
            "INSERT INTO runs (run_id, task_id, phase, condition, task_success, validation_source) VALUES (?,?,?,?,?,?)",
            r,
        )

    # Gate decisions:
    # - run-pass1: 2 approves (correct: both should approve on passing run)
    # - run-pass2: 1 approve, 1 block (FP: blocked on passing run)
    # - run-fail1: 2 blocks (TP: correctly blocked on failing run)
    # - run-fail2: 2 approves (FN: missed on failing run)
    decisions = [
        ("run-pass1", 1, "introspective", "early", "approve"),
        ("run-pass1", 2, "introspective", "early", "approve"),
        ("run-pass2", 1, "introspective", "early", "approve"),
        ("run-pass2", 2, "introspective", "early", "block"),
        ("run-fail1", 1, "introspective", "early", "block"),
        ("run-fail1", 2, "introspective", "early", "block"),
        ("run-fail2", 1, "introspective", "early", "approve"),
        ("run-fail2", 2, "introspective", "early", "approve"),
    ]
    for d in decisions:
        conn.execute(
            "INSERT INTO gate_decisions (decision_id, run_id, tool_call_sequence, gate_type, gate_timing, verdict) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), *d),
        )

    conn.commit()
    yield conn, path
    conn.close()
    os.unlink(path)


# ===================================================================
# Gate metrics
# ===================================================================

class TestGateMetrics:
    def test_compute_metrics(self, populated_db):
        conn, path = populated_db
        # We need to patch the DB path used by compute_gate_metrics
        # Since it uses init_db which creates tables, we close and pass path
        conn.close()

        # Reconnect via init_db-like setup
        metrics = compute_gate_metrics("A1", db_path=path)

        # TP=2 (fail1 blocked x2), FP=1 (pass2 blocked), FN=2 (fail2 not blocked), TN=3 (pass approved)
        assert metrics["confusion"]["tp"] == 2
        assert metrics["confusion"]["fp"] == 1
        assert metrics["confusion"]["fn"] == 2
        assert metrics["confusion"]["tn"] == 3

        # Precision = TP/(TP+FP) = 2/3
        assert metrics["precision"] == pytest.approx(2/3, abs=0.01)
        # Recall = TP/(TP+FN) = 2/4
        assert metrics["recall"] == pytest.approx(0.5, abs=0.01)


# ===================================================================
# Post-hoc gate application integration
# ===================================================================

class TestPostHocIntegration:
    """Test that IntrospectiveGate produces expected decisions on realistic data."""

    def test_gate_blocks_unaligned_short_reasoning(self):
        config = GateConfig(deliberation_threshold_chars=100)
        gate = IntrospectiveGate(config)

        decision = gate.evaluate(
            reasoning_text="Fix the bug",
            tool_params={"file_path": "django/views.py"},
        )
        assert decision.verdict == "block"

    def test_gate_approves_aligned_long_reasoning(self):
        config = GateConfig(deliberation_threshold_chars=50)
        gate = IntrospectiveGate(config)

        reasoning = "The issue is in views.py where the queryset filter is applied. " * 3
        decision = gate.evaluate(
            reasoning_text=reasoning,
            tool_params={"file_path": "django/views.py"},
        )
        assert decision.verdict == "approve"

    def test_gate_respects_early_timing(self):
        config = GateConfig(deliberation_threshold_chars=100)
        gate = IntrospectiveGate(config)

        # Short reasoning, would normally block
        decision = gate.evaluate(
            reasoning_text="Fix",
            tool_params={"file_path": "django/views.py"},
            sequence_number=20,
            total_calls_estimate=30,
            gate_timing="early",
        )
        # Past cutoff (30/3 = 10), should auto-approve
        assert decision.verdict == "approve"

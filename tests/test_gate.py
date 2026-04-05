"""
Tests for Phase 1 gate logic (src/gate.py).

Covers:
  - IntrospectiveGate alignment and deliberation checks
  - Gate timing (early vs always)
  - GateDecision data structure
  - Condition mapping
  - Config loading
  - DB storage of gate decisions
"""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import sys
import tempfile

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from gate import (
    GateConfig, GateDecision, IntrospectiveGate, ExtrospectiveGate,
    CombinedGate, CONDITION_MAP,
    get_gate_for_condition, get_timing_for_condition, get_prompt_modifier,
    init_gate_decisions_table, store_gate_decision,
    compute_thresholds_from_db, save_config,
)


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def config():
    """Standard test config with known thresholds."""
    return GateConfig(
        alignment_threshold=0.5,
        deliberation_threshold_tokens=29,
        deliberation_threshold_chars=100,
    )


@pytest.fixture
def gate(config):
    return IntrospectiveGate(config)


@pytest.fixture
def temp_db():
    """Temporary SQLite database for gate decision storage tests."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_gate_decisions_table(conn)
    yield conn, path
    conn.close()
    os.unlink(path)


# ===================================================================
# GateDecision dataclass
# ===================================================================

class TestGateDecision:
    def test_defaults(self):
        d = GateDecision()
        assert d.verdict == "approve"
        assert d.gate_type == ""
        assert d.run_id is None
        assert len(d.decision_id) > 0

    def test_to_db_dict(self):
        d = GateDecision(
            run_id="run-abc",
            verdict="block",
            gate_type="introspective",
        )
        db_dict = d.to_db_dict()
        assert db_dict["run_id"] == "run-abc"
        assert db_dict["verdict"] == "block"
        assert "decision_id" in db_dict


# ===================================================================
# IntrospectiveGate — alignment check
# ===================================================================

class TestAlignmentCheck:
    def test_filename_in_reasoning(self, gate):
        aligned, reason = gate.check_alignment(
            "I need to edit views.py to fix the queryset issue",
            {"file_path": "django/views.py"},
        )
        assert aligned is True
        assert "views.py" in reason

    def test_filename_not_in_reasoning(self, gate):
        aligned, reason = gate.check_alignment(
            "I think the issue is in the database layer",
            {"file_path": "django/views.py"},
        )
        assert aligned is False

    def test_partial_path_in_reasoning(self, gate):
        aligned, reason = gate.check_alignment(
            "The fix should be in models/fields.py where the deferred loading happens",
            {"file_path": "/tmp/workspace/django/models/fields.py"},
        )
        assert aligned is True

    def test_empty_reasoning(self, gate):
        aligned, reason = gate.check_alignment(
            "",
            {"file_path": "django/views.py"},
        )
        assert aligned is False

    def test_none_reasoning(self, gate):
        aligned, reason = gate.check_alignment(
            None,
            {"file_path": "django/views.py"},
        )
        assert aligned is False

    def test_no_file_path(self, gate):
        aligned, reason = gate.check_alignment(
            "Some reasoning text",
            {},
        )
        assert aligned is True  # Can't check, pass through

    def test_full_path_in_reasoning(self, gate):
        aligned, reason = gate.check_alignment(
            "I will modify /tmp/workspace/django/db/models/query.py",
            {"file_path": "/tmp/workspace/django/db/models/query.py"},
        )
        assert aligned is True


# ===================================================================
# IntrospectiveGate — deliberation check
# ===================================================================

class TestDeliberationCheck:
    def test_sufficient_deliberation(self, gate):
        text = "x" * 150  # Above 100 char threshold
        ok, reason = gate.check_deliberation(text)
        assert ok is True

    def test_insufficient_deliberation(self, gate):
        text = "x" * 50  # Below 100 char threshold
        ok, reason = gate.check_deliberation(text)
        assert ok is False

    def test_exact_threshold(self, gate):
        text = "x" * 100  # Exactly at threshold
        ok, reason = gate.check_deliberation(text)
        assert ok is True

    def test_empty_text(self, gate):
        ok, reason = gate.check_deliberation("")
        assert ok is False

    def test_none_text(self, gate):
        ok, reason = gate.check_deliberation(None)
        assert ok is False

    def test_whitespace_only(self, gate):
        ok, reason = gate.check_deliberation("   \n\t  ")
        assert ok is False


# ===================================================================
# IntrospectiveGate — full evaluation
# ===================================================================

class TestIntrospectiveEvaluate:
    def test_both_pass(self, gate):
        reasoning = "I need to modify views.py because the queryset filter is wrong. " * 5
        decision = gate.evaluate(
            reasoning_text=reasoning,
            tool_params={"file_path": "django/views.py"},
        )
        assert decision.verdict == "approve"
        assert decision.gate_type == "introspective"
        assert decision.alignment_score == 1.0

    def test_alignment_fail_blocks(self, gate):
        reasoning = "I think the database has an issue with the connection pool. " * 5
        decision = gate.evaluate(
            reasoning_text=reasoning,
            tool_params={"file_path": "django/views.py"},
        )
        assert decision.verdict == "block"
        assert "Alignment" in decision.reason

    def test_deliberation_fail_blocks(self, gate):
        reasoning = "Fix views.py"  # Short but mentions file
        decision = gate.evaluate(
            reasoning_text=reasoning,
            tool_params={"file_path": "django/views.py"},
        )
        assert decision.verdict == "block"
        assert "Deliberation" in decision.reason

    def test_both_fail_blocks(self, gate):
        reasoning = "Fix it"  # Short AND doesn't mention file
        decision = gate.evaluate(
            reasoning_text=reasoning,
            tool_params={"file_path": "django/views.py"},
        )
        assert decision.verdict == "block"
        assert "Both" in decision.reason

    def test_no_reasoning_blocks(self, gate):
        decision = gate.evaluate(
            reasoning_text="",
            tool_params={"file_path": "django/views.py"},
        )
        assert decision.verdict == "block"


# ===================================================================
# Gate timing
# ===================================================================

class TestGateTiming:
    def test_early_gate_within_cutoff(self, gate):
        """Calls within first 1/3 should be gated."""
        reasoning = "Fix views.py because the filter is broken. " * 5
        decision = gate.evaluate(
            reasoning_text=reasoning,
            tool_params={"file_path": "django/views.py"},
            sequence_number=2,
            total_calls_estimate=30,
            gate_timing="early",
        )
        # Within first 1/3 (cutoff=10), should be gated normally
        assert decision.verdict == "approve"

    def test_early_gate_past_cutoff(self, gate):
        """Calls past first 1/3 should auto-approve."""
        reasoning = ""  # Would normally block
        decision = gate.evaluate(
            reasoning_text=reasoning,
            tool_params={"file_path": "django/views.py"},
            sequence_number=15,
            total_calls_estimate=30,
            gate_timing="early",
        )
        # Past cutoff, auto-approve
        assert decision.verdict == "approve"
        assert "cutoff" in decision.reason.lower()

    def test_always_gate_late_call(self, gate):
        """Always-gate should evaluate even late calls."""
        reasoning = ""  # Would block
        decision = gate.evaluate(
            reasoning_text=reasoning,
            tool_params={"file_path": "django/views.py"},
            sequence_number=25,
            total_calls_estimate=30,
            gate_timing="always",
        )
        assert decision.verdict == "block"

    def test_early_gate_zero_total(self, gate):
        """Zero total_calls should not crash."""
        decision = gate.evaluate(
            reasoning_text="",
            tool_params={"file_path": "django/views.py"},
            sequence_number=1,
            total_calls_estimate=0,
            gate_timing="early",
        )
        # Should still evaluate (no cutoff when total=0)
        assert decision.verdict == "block"


# ===================================================================
# Condition mapping
# ===================================================================

class TestConditionMap:
    def test_all_conditions_present(self):
        expected = {"C0", "A1", "A2", "A3", "B1", "B2", "B3", "P1", "P2"}
        assert expected == set(CONDITION_MAP.keys())

    def test_c0_is_ungated(self):
        assert get_gate_for_condition("C0") is None

    def test_a1_is_introspective(self):
        gate = get_gate_for_condition("A1")
        assert isinstance(gate, IntrospectiveGate)

    def test_b2_is_extrospective(self):
        gate = get_gate_for_condition("B2")
        assert isinstance(gate, ExtrospectiveGate)

    def test_a3_is_combined(self):
        gate = get_gate_for_condition("A3")
        assert isinstance(gate, CombinedGate)

    def test_timing_early(self):
        assert get_timing_for_condition("A1") == "early"
        assert get_timing_for_condition("A2") == "early"
        assert get_timing_for_condition("A3") == "early"

    def test_timing_always(self):
        assert get_timing_for_condition("B1") == "always"
        assert get_timing_for_condition("B2") == "always"
        assert get_timing_for_condition("B3") == "always"

    def test_timing_none(self):
        assert get_timing_for_condition("C0") == "none"

    def test_unknown_condition_raises(self):
        with pytest.raises(ValueError):
            get_gate_for_condition("Z9")

    def test_prompt_modifier_p1(self):
        mod = get_prompt_modifier("P1")
        assert mod is not None
        assert "state which file" in mod.lower()

    def test_prompt_modifier_p2(self):
        mod = get_prompt_modifier("P2")
        assert mod is not None
        assert "review" in mod.lower()

    def test_prompt_modifier_a1_is_none(self):
        assert get_prompt_modifier("A1") is None


# ===================================================================
# Config
# ===================================================================

class TestGateConfig:
    def test_defaults(self):
        c = GateConfig()
        assert c.alignment_threshold == 0.5
        assert c.deliberation_threshold_tokens == 29

    def test_from_dict(self):
        c = GateConfig(deliberation_threshold_chars=200)
        assert c.deliberation_threshold_chars == 200

    def test_save_and_load(self, tmp_path):
        c = GateConfig(deliberation_threshold_chars=250)
        path = tmp_path / "test_config.json"
        save_config(c, path)
        loaded = GateConfig.from_file(path)
        assert loaded.deliberation_threshold_chars == 250

    def test_missing_file_returns_defaults(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        c = GateConfig.from_file(path)
        assert c.alignment_threshold == 0.5


# ===================================================================
# Database storage
# ===================================================================

class TestGateDecisionStorage:
    def test_store_and_retrieve(self, temp_db):
        conn, path = temp_db

        d = GateDecision(
            run_id="run-test123",
            tool_call_sequence=3,
            gate_type="introspective",
            gate_timing="early",
            verdict="block",
            reason="alignment failed",
            alignment_score=0.0,
            deliberation_length=45,
        )
        store_gate_decision(conn, d)

        row = conn.execute(
            "SELECT * FROM gate_decisions WHERE decision_id = ?",
            (d.decision_id,),
        ).fetchone()

        assert row is not None
        assert row["run_id"] == "run-test123"
        assert row["verdict"] == "block"
        assert row["gate_type"] == "introspective"
        assert row["alignment_score"] == 0.0

    def test_store_multiple(self, temp_db):
        conn, path = temp_db

        for i in range(5):
            d = GateDecision(
                run_id=f"run-{i}",
                verdict="approve" if i % 2 == 0 else "block",
                gate_type="introspective",
            )
            store_gate_decision(conn, d)

        count = conn.execute("SELECT COUNT(*) FROM gate_decisions").fetchone()[0]
        assert count == 5

        blocked = conn.execute(
            "SELECT COUNT(*) FROM gate_decisions WHERE verdict='block'"
        ).fetchone()[0]
        assert blocked == 2

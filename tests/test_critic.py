"""
Tests for Phase 1 critic logic (src/critic.py).

Covers:
  - Response parsing (APPROVE, CONCERN, REJECT)
  - Fallback parsing for malformed responses
  - CriticCache operations
  - Retroactive critic analysis
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from critic import (
    parse_critic_response,
    CriticCache,
    CriticEvaluator,
    analyze_retroactive_critic,
    CRITIC_PROMPT_TEMPLATE,
)


# ===================================================================
# Response parsing
# ===================================================================

class TestParseCriticResponse:
    def test_approve_standard(self):
        verdict, exp = parse_critic_response("APPROVE - the edit looks correct")
        assert verdict == "approve"

    def test_approve_no_dash(self):
        verdict, exp = parse_critic_response("APPROVE the edit is fine")
        assert verdict == "approve"

    def test_approve_colon(self):
        verdict, exp = parse_critic_response("APPROVE: looks good")
        assert verdict == "approve"

    def test_concern_standard(self):
        verdict, exp = parse_critic_response("CONCERN: might break test_foo.py")
        assert verdict == "concern"
        assert "test_foo.py" in exp

    def test_reject_standard(self):
        verdict, exp = parse_critic_response("REJECT: wrong file being edited")
        assert verdict == "reject"
        assert "wrong file" in exp

    def test_reject_lowercase(self):
        verdict, exp = parse_critic_response("reject: this is completely wrong")
        assert verdict == "reject"

    def test_empty_response(self):
        verdict, exp = parse_critic_response("")
        assert verdict == "approve"  # fail-open
        assert "empty" in exp.lower()

    def test_none_response(self):
        verdict, exp = parse_critic_response(None)
        assert verdict == "approve"  # fail-open

    def test_unparseable_with_reject_keyword(self):
        verdict, exp = parse_critic_response(
            "I think we should reject this change because it modifies the wrong function"
        )
        assert verdict == "reject"

    def test_unparseable_with_concern_keyword(self):
        verdict, exp = parse_critic_response(
            "I have a concern about this edit - it might cause side effects"
        )
        assert verdict == "concern"

    def test_totally_unparseable(self):
        verdict, exp = parse_critic_response("Hello world, nice day today")
        assert verdict == "approve"  # fail-open
        assert "unparseable" in exp.lower()

    def test_multiline_response(self):
        response = """REJECT: The edit modifies add_deferred_loading but the actual issue
is in set_deferred_loading. The agent should be editing a different method."""
        verdict, exp = parse_critic_response(response)
        assert verdict == "reject"
        assert "add_deferred_loading" in exp


# ===================================================================
# Prompt template
# ===================================================================

class TestPromptTemplate:
    def test_template_has_placeholders(self):
        assert "{bug_description}" in CRITIC_PROMPT_TEMPLATE
        assert "{file_path}" in CRITIC_PROMPT_TEMPLATE
        assert "{old_string}" in CRITIC_PROMPT_TEMPLATE
        assert "{new_string}" in CRITIC_PROMPT_TEMPLATE
        assert "{reasoning_text}" in CRITIC_PROMPT_TEMPLATE

    def test_template_formats(self):
        prompt = CRITIC_PROMPT_TEMPLATE.format(
            bug_description="QuerySet.only() bug",
            file_path="django/db/models/query.py",
            old_string="old code here",
            new_string="new code here",
            reasoning_text="agent reasoning here",
        )
        assert "QuerySet.only() bug" in prompt
        assert "django/db/models/query.py" in prompt
        assert "APPROVE" in prompt
        assert "CONCERN" in prompt
        assert "REJECT" in prompt


# ===================================================================
# CriticCache
# ===================================================================

class TestCriticCache:
    def test_cache_miss(self, tmp_path):
        cache = CriticCache(cache_path=tmp_path / "cache.json")
        result = cache.get("foo.py", "old", "new")
        assert result is None

    def test_cache_hit(self, tmp_path):
        cache = CriticCache(cache_path=tmp_path / "cache.json")
        cache.put("foo.py", "old", "new", "approve", "looks good", "APPROVE - looks good")
        result = cache.get("foo.py", "old", "new")
        assert result is not None
        assert result["verdict"] == "approve"

    def test_cache_persistence(self, tmp_path):
        cache_path = tmp_path / "cache.json"

        # Write
        cache1 = CriticCache(cache_path=cache_path)
        cache1.put("foo.py", "old", "new", "reject", "wrong fix", "REJECT: wrong fix")

        # Read in new instance
        cache2 = CriticCache(cache_path=cache_path)
        result = cache2.get("foo.py", "old", "new")
        assert result is not None
        assert result["verdict"] == "reject"

    def test_different_edits_different_keys(self, tmp_path):
        cache = CriticCache(cache_path=tmp_path / "cache.json")
        cache.put("foo.py", "old1", "new1", "approve", "ok", "APPROVE")
        cache.put("foo.py", "old2", "new2", "reject", "bad", "REJECT: bad")

        r1 = cache.get("foo.py", "old1", "new1")
        r2 = cache.get("foo.py", "old2", "new2")
        assert r1["verdict"] == "approve"
        assert r2["verdict"] == "reject"


# ===================================================================
# CriticEvaluator (dry run)
# ===================================================================

class TestCriticEvaluator:
    def test_dry_run(self):
        critic = CriticEvaluator(dry_run=True, use_cache=False)
        verdict, exp = critic.evaluate_edit(
            bug_description="test bug",
            file_path="test.py",
            old_string="old",
            new_string="new",
            reasoning_text="reasoning",
        )
        assert verdict == "approve"
        assert "dry run" in exp.lower()

    def test_cache_prevents_duplicate_calls(self, tmp_path):
        critic = CriticEvaluator(
            dry_run=True,
            use_cache=True,
            cache_path=tmp_path / "cache.json",
        )
        # First call (dry run)
        v1, _ = critic.evaluate_edit("bug", "f.py", "old", "new", "reasoning")
        # Put a fake cached result
        critic.cache.put("f.py", "old", "new", "reject", "cached reject", "REJECT: cached")
        # Second call should hit cache
        v2, e2 = critic.evaluate_edit("bug", "f.py", "old", "new", "reasoning")
        assert v2 == "reject"
        assert "cached" in e2.lower()


# ===================================================================
# Retroactive analysis
# ===================================================================

class TestAnalyzeRetroactiveCritic:
    def test_empty_results(self):
        analysis = analyze_retroactive_critic([])
        assert "error" in analysis

    def test_perfect_predictor(self):
        results = [
            {"task_success": True, "critic_verdict": "approve"},
            {"task_success": True, "critic_verdict": "approve"},
            {"task_success": False, "critic_verdict": "reject"},
            {"task_success": False, "critic_verdict": "reject"},
        ]
        analysis = analyze_retroactive_critic(results)
        assert analysis["precision"] == 1.0
        assert analysis["recall"] == 1.0
        assert analysis["f1"] == 1.0

    def test_all_approve(self):
        results = [
            {"task_success": True, "critic_verdict": "approve"},
            {"task_success": False, "critic_verdict": "approve"},
        ]
        analysis = analyze_retroactive_critic(results)
        assert analysis["precision"] == 0.0  # No rejections, can't compute
        assert analysis["recall"] == 0.0     # Missed the failing run

    def test_mixed_verdicts(self):
        results = [
            {"task_success": True, "critic_verdict": "approve"},
            {"task_success": True, "critic_verdict": "reject"},   # FP
            {"task_success": False, "critic_verdict": "reject"},  # TP
            {"task_success": False, "critic_verdict": "approve"}, # FN
            {"task_success": False, "critic_verdict": "reject"},  # TP
        ]
        analysis = analyze_retroactive_critic(results)
        # TP=2, FP=1, FN=1, TN=1
        assert analysis["confusion"]["tp"] == 2
        assert analysis["confusion"]["fp"] == 1
        assert analysis["confusion"]["fn"] == 1
        assert analysis["confusion"]["tn"] == 1
        assert analysis["precision"] == pytest.approx(2/3, abs=0.01)
        assert analysis["recall"] == pytest.approx(2/3, abs=0.01)

    def test_concern_not_rejected(self):
        """CONCERN counts as non-rejection (only REJECT is a block)."""
        results = [
            {"task_success": False, "critic_verdict": "concern"},
        ]
        analysis = analyze_retroactive_critic(results)
        assert analysis["confusion"]["fn"] == 1  # Missed
        assert analysis["confusion"]["tp"] == 0

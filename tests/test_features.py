"""
Tests for src/feature_definitions.py

Covers all Tier 0 and Tier 1 feature extractors with normal, edge-case,
and realistic-fixture inputs.  At least 25 distinct test cases.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

import pytest

# Ensure src/ is importable
_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from feature_definitions import (
    extract_all,
    extract_all_tier0,
    extract_all_tier1,
    extract_alternatives_considered,
    extract_backtrack_count,
    extract_deliberation_length,
    extract_hedging_score,
    extract_prior_failure_streak,
    extract_retry_count,
    extract_step_index_normalized,
    extract_tool_switch_rate,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def lexicon() -> dict:
    """Load the Hyland hedge lexicon from disk."""
    path = _ROOT / "src" / "lexicons" / "hyland_hedges.json"
    with open(path) as f:
        return json.load(f)


# Five realistic Claude Code reasoning snippets used across multiple tests.

REASONING_IMPORT_FIX = (
    "I need to fix the import error. Let me check the file structure first... "
    "Actually, I think the issue might be in the module path. I could try "
    "updating the import statement, or alternatively I could restructure the "
    "directory. Let me go with updating the import."
)

REASONING_CONFIDENT = (
    "The function is missing a return statement on line 42. I will add "
    "return result at the end of the function body."
)

REASONING_UNCERTAIN = (
    "Hmm, I wonder if this is the right approach. Maybe the tests are "
    "failing because of a race condition, or possibly a stale cache. "
    "I guess I should probably check both. Let me try a different strategy."
)

REASONING_LONG_DELIBERATION = (
    "Let me think through this step by step. The error says ModuleNotFoundError "
    "for 'utils.helpers'. I could check if the __init__.py exists. Actually, "
    "wait -- the directory was renamed last commit. That's not right, the import "
    "path should reflect the new name. On second thought, maybe the issue is "
    "that the CI environment hasn't pulled the latest changes. One option is to "
    "add a conditional import. Another approach would be to use a relative import "
    "instead of an absolute one. I was wrong about the rename -- the directory "
    "name is correct but the __init__.py is missing."
)

REASONING_BACKTRACK_HEAVY = (
    "Wait, actually no, let me reconsider. I was wrong about the config "
    "parsing. Hmm, that's not right either. On second thought the YAML "
    "loader should handle this. Actually, the issue is the encoding."
)


# ===================================================================
# Tier 0 tests
# ===================================================================

class TestStepIndexNormalized:
    """sequence_number is 1-based (from trace_collector)."""

    def test_middle_of_sequence(self):
        # Call 6 of 11 (1-based) -> index 5/10 = 0.5
        assert extract_step_index_normalized(6, 11) == pytest.approx(0.5)

    def test_first_step(self):
        assert extract_step_index_normalized(1, 10) == 0.0

    def test_last_step(self):
        assert extract_step_index_normalized(10, 10) == 1.0

    def test_single_call(self):
        assert extract_step_index_normalized(1, 1) == 0.0

    def test_zero_total(self):
        assert extract_step_index_normalized(0, 0) == 0.0

    def test_none_total(self):
        assert extract_step_index_normalized(3, None) == 0.0

    def test_none_sequence(self):
        assert extract_step_index_normalized(None, 10) == 0.0


class TestPriorFailureStreak:

    def test_no_failures(self):
        assert extract_prior_failure_streak([True, True, True]) == 0

    def test_all_failures(self):
        assert extract_prior_failure_streak([False, False, False]) == 3

    def test_trailing_failures(self):
        assert extract_prior_failure_streak([True, True, False, False]) == 2

    def test_single_trailing_failure(self):
        assert extract_prior_failure_streak([True, False]) == 1

    def test_empty_list(self):
        assert extract_prior_failure_streak([]) == 0

    def test_none_input(self):
        assert extract_prior_failure_streak(None) == 0

    def test_mixed_then_success(self):
        assert extract_prior_failure_streak([False, True, False, True]) == 0


class TestRetryCount:

    def test_no_prior_calls(self):
        assert extract_retry_count("Read", "main.py", []) == 0

    def test_one_match(self):
        prior = [{"tool_name": "Read", "tool_target": "main.py"}]
        assert extract_retry_count("Read", "main.py", prior) == 1

    def test_multiple_matches(self):
        prior = [
            {"tool_name": "Read", "tool_target": "main.py"},
            {"tool_name": "Edit", "tool_target": "main.py"},
            {"tool_name": "Read", "tool_target": "main.py"},
        ]
        assert extract_retry_count("Read", "main.py", prior) == 2

    def test_no_match(self):
        prior = [{"tool_name": "Bash", "tool_target": "ls"}]
        assert extract_retry_count("Read", "main.py", prior) == 0

    def test_none_inputs(self):
        assert extract_retry_count(None, "x", []) == 0
        assert extract_retry_count("Read", None, []) == 0
        assert extract_retry_count("Read", "x", None) == 0


class TestToolSwitchRate:

    def test_no_switches(self):
        assert extract_tool_switch_rate(["Read", "Read", "Read"]) == 0.0

    def test_all_switches(self):
        assert extract_tool_switch_rate(["Read", "Edit", "Bash"]) == 1.0

    def test_half_switches(self):
        assert extract_tool_switch_rate(["Read", "Read", "Edit", "Edit"]) == pytest.approx(1 / 3)

    def test_window_truncation(self):
        # 7 items, window=5 means only last 5 used
        names = ["A", "A", "B", "B", "A", "A", "B"]
        # Last 5: ["B", "A", "A", "B", "B"] -> switches at (B,A), (A,B) -> 2/4 = 0.5
        # Wait: last 5 of the list are index 2..6 => ["B", "B", "A", "A", "B"]
        # switches: (B,B)=0, (B,A)=1, (A,A)=0, (A,B)=1 => 2/4 = 0.5
        assert extract_tool_switch_rate(names, window=5) == pytest.approx(0.5)

    def test_single_element(self):
        assert extract_tool_switch_rate(["Read"]) == 0.0

    def test_empty(self):
        assert extract_tool_switch_rate([]) == 0.0

    def test_none(self):
        assert extract_tool_switch_rate(None) == 0.0


# ===================================================================
# Tier 1 tests
# ===================================================================

class TestHedgingScore:

    def test_known_hedge_count(self, lexicon):
        # "might" and "could" are hedge terms, "the" and "bug" are not.
        text = "might fix the bug could"
        # tokens: might, fix, the, bug, could -> 2 hedges / 5 tokens
        score = extract_hedging_score(text, lexicon)
        assert score == pytest.approx(2 / 5)

    def test_no_hedges(self, lexicon):
        text = "fix the broken test now"
        assert extract_hedging_score(text, lexicon) == 0.0

    def test_empty_text(self, lexicon):
        assert extract_hedging_score("", lexicon) == 0.0

    def test_none_text(self, lexicon):
        assert extract_hedging_score(None, lexicon) == 0.0

    def test_none_lexicon(self):
        assert extract_hedging_score("might work", None) == 0.0

    def test_missing_all_terms_key(self):
        assert extract_hedging_score("might work", {"modal_verbs": ["might"]}) == 0.0

    def test_realistic_import_fix(self, lexicon):
        score = extract_hedging_score(REASONING_IMPORT_FIX, lexicon)
        assert score > 0  # contains "think", "might", "could"

    def test_realistic_confident(self, lexicon):
        # Very few if any hedges in a confident statement
        score_confident = extract_hedging_score(REASONING_CONFIDENT, lexicon)
        score_uncertain = extract_hedging_score(REASONING_UNCERTAIN, lexicon)
        assert score_uncertain > score_confident

    def test_llm_trace_terms_in_lexicon(self, lexicon):
        # Validate terms from arXiv:2508.15842 are in all_terms
        trace_terms = {"guess", "stuck", "likely", "possibly", "depend",
                       "unsure", "unclear", "maybe", "perhaps", "wonder", "suppose"}
        all_set = set(lexicon["all_terms"])
        assert trace_terms.issubset(all_set)


class TestDeliberationLength:

    def test_normal(self):
        assert extract_deliberation_length("one two three") == 3

    def test_empty(self):
        assert extract_deliberation_length("") == 0

    def test_none(self):
        assert extract_deliberation_length(None) == 0

    def test_long_text(self):
        text = " ".join(["word"] * 500)
        assert extract_deliberation_length(text) == 500

    def test_realistic(self):
        length = extract_deliberation_length(REASONING_LONG_DELIBERATION)
        assert length > 50


class TestAlternativesConsidered:

    def test_zero_alternatives(self):
        assert extract_alternatives_considered("Fix the bug directly.") == 0

    def test_one_alternative(self):
        text = "I could try this, or alternatively do that."
        # "I could" + "alternatively" = 2
        assert extract_alternatives_considered(text) == 2

    def test_three_alternatives(self):
        text = (
            "I could use regex. Alternatively, I could parse manually. "
            "Another approach is to use a library."
        )
        # "I could" x2, "alternatively" x1, "another approach" x1 = 4
        assert extract_alternatives_considered(text) == 4

    def test_empty(self):
        assert extract_alternatives_considered("") == 0

    def test_none(self):
        assert extract_alternatives_considered(None) == 0

    def test_case_insensitive(self):
        assert extract_alternatives_considered("ALTERNATIVELY, we proceed.") == 1

    def test_realistic_import_fix(self):
        count = extract_alternatives_considered(REASONING_IMPORT_FIX)
        # Contains "I could" (x2) and "alternatively" (x1)
        assert count >= 2

    def test_instead_of(self):
        assert extract_alternatives_considered("Instead of parsing, use regex.") == 1

    def test_let_me_try_different(self):
        text = "Let me try a different approach to this problem."
        assert extract_alternatives_considered(text) == 1


class TestBacktrackCount:

    def test_zero_backtracks(self):
        assert extract_backtrack_count("I will read the file now.") == 0

    def test_one_backtrack(self):
        assert extract_backtrack_count("Actually, that was wrong.") == 1

    def test_multiple_backtracks(self):
        # "wait", "actually", "hmm"
        text = "Wait, hmm, actually I need to rethink."
        assert extract_backtrack_count(text) == 3

    def test_empty(self):
        assert extract_backtrack_count("") == 0

    def test_none(self):
        assert extract_backtrack_count(None) == 0

    def test_realistic_import_fix(self):
        count = extract_backtrack_count(REASONING_IMPORT_FIX)
        # Contains "Actually"
        assert count >= 1

    def test_realistic_backtrack_heavy(self):
        count = extract_backtrack_count(REASONING_BACKTRACK_HEAVY)
        # "Wait", "actually" (x2), "no,", "let me reconsider",
        # "hmm", "that's not right", "on second thought"
        assert count >= 7

    def test_realistic_long_deliberation(self):
        count = extract_backtrack_count(REASONING_LONG_DELIBERATION)
        # "actually", "wait", "that's not right", "on second thought",
        # "I was wrong"
        assert count >= 4

    def test_no_comma_after_no(self):
        # "no" without comma should NOT match "no,"
        assert extract_backtrack_count("There is no error here.") == 0


# ===================================================================
# Aggregate extractor tests
# ===================================================================

class TestExtractAllTier0:

    def test_returns_all_keys(self):
        result = extract_all_tier0(
            sequence_number=3,
            total_calls=10,
            previous_results=[True, False, False],
            tool_name="Read",
            tool_target="main.py",
            prior_calls=[{"tool_name": "Read", "tool_target": "main.py"}],
            recent_tool_names=["Read", "Edit", "Read"],
        )
        assert set(result.keys()) == {
            "step_index_normalized",
            "prior_failure_streak",
            "retry_count",
            "tool_switch_rate",
        }
        assert result["prior_failure_streak"] == 2
        assert result["retry_count"] == 1


class TestExtractAllTier1:

    def test_returns_all_keys(self, lexicon):
        result = extract_all_tier1(REASONING_IMPORT_FIX, lexicon)
        assert set(result.keys()) == {
            "hedging_score",
            "deliberation_length",
            "alternatives_considered",
            "backtrack_count",
            "verification_score",
            "planning_score",
        }
        assert result["hedging_score"] > 0
        assert result["deliberation_length"] > 0
        assert result["alternatives_considered"] >= 2
        assert result["backtrack_count"] >= 1


class TestExtractAll:

    def test_combined_output(self, lexicon):
        tier0_args = dict(
            sequence_number=0,
            total_calls=5,
            previous_results=[],
            tool_name="Bash",
            tool_target="ls",
            prior_calls=[],
            recent_tool_names=["Bash"],
        )
        tier1_args = dict(
            reasoning_text=REASONING_UNCERTAIN,
            lexicon=lexicon,
        )
        result = extract_all(tier0_args, tier1_args)
        assert "step_index_normalized" in result
        assert "hedging_score" in result
        assert len(result) == 10

    def test_tier0_only(self):
        tier0_args = dict(
            sequence_number=0,
            total_calls=1,
            previous_results=[],
            tool_name="Read",
            tool_target="x.py",
            prior_calls=[],
            recent_tool_names=[],
        )
        result = extract_all(tier0_args, None)
        assert len(result) == 4
        assert "hedging_score" not in result

    def test_tier1_only(self, lexicon):
        tier1_args = dict(
            reasoning_text="maybe this works",
            lexicon=lexicon,
        )
        result = extract_all(None, tier1_args)
        assert len(result) == 6
        assert "step_index_normalized" not in result

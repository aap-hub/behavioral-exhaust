"""
Feature extraction for UGA research harness.

Two tiers of behavioral features extracted from coding agent reasoning traces:
  Tier 0 -- Deterministic features from trace structure (no text analysis).
  Tier 1 -- Linguistic features from reasoning text (hedge word counting).

All functions are pure and handle None / empty-string / empty-list inputs.
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Tier 0 — structural features
# ---------------------------------------------------------------------------

def extract_step_index_normalized(
    sequence_number: int,
    total_calls: int,
) -> float:
    """Position in the trajectory, normalized to [0, 1].

    sequence_number is 1-based (from trace_collector). We convert to 0-based
    internally so the first call maps to 0.0 and the last to 1.0.

    Returns 0.0 when *total_calls* is 0 or 1 (single-step trajectory).
    """
    if total_calls is None or total_calls <= 1:
        return 0.0
    if sequence_number is None:
        return 0.0
    # Convert 1-based sequence_number to 0-based index
    zero_based = sequence_number - 1
    return max(0.0, min(1.0, zero_based / (total_calls - 1)))


def extract_prior_failure_streak(previous_results: list[bool]) -> int:
    """Count consecutive ``False`` values at the *end* of the list.

    An empty or ``None`` list yields 0.
    """
    if not previous_results:
        return 0
    streak = 0
    for result in reversed(previous_results):
        if result is False:
            streak += 1
        else:
            break
    return streak


def extract_retry_count(
    tool_name: str,
    tool_target: str,
    prior_calls: list[dict],
) -> int:
    """How many times the same (tool_name, tool_target) pair already appeared.

    ``prior_calls`` entries are dicts with at least ``"tool_name"`` and
    ``"tool_target"`` keys.  Missing keys or ``None`` inputs are safe.
    """
    if not prior_calls or tool_name is None or tool_target is None:
        return 0
    count = 0
    for call in prior_calls:
        if not isinstance(call, dict):
            continue
        if call.get("tool_name") == tool_name and call.get("tool_target") == tool_target:
            count += 1
    return count


def extract_tool_switch_rate(
    recent_tool_names: list[str],
    window: int = 5,
) -> float:
    """Fraction of adjacent pairs that differ within a sliding *window*.

    Returns 0.0 for lists shorter than 2 or ``None``.
    """
    if not recent_tool_names or len(recent_tool_names) < 2:
        return 0.0
    names = recent_tool_names[-window:]
    if len(names) < 2:
        return 0.0
    switches = sum(
        1 for a, b in zip(names, names[1:]) if a != b
    )
    return switches / (len(names) - 1)


# ---------------------------------------------------------------------------
# Tier 1 — linguistic features
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Lowercase whitespace split.  Returns [] for None / empty."""
    if not text:
        return []
    return text.lower().split()


def extract_hedging_score(text: str, lexicon: dict) -> float:
    """Ratio of hedge tokens to total tokens.

    *lexicon* must contain an ``"all_terms"`` key whose value is an iterable
    of lowercase hedge terms.  Returns 0.0 on empty input or missing key.
    """
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    if not lexicon or "all_terms" not in lexicon:
        return 0.0
    hedge_set = set(lexicon["all_terms"])
    hedge_count = sum(1 for t in tokens if t in hedge_set)
    return hedge_count / len(tokens)


def extract_deliberation_length(text: str) -> int:
    """Whitespace-split token count.  0 for None / empty."""
    return len(_tokenize(text))


# Pre-compiled patterns for alternatives and backtracks ----------------------

_ALTERNATIVE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bi could\b", re.IGNORECASE),
    re.compile(r"\balternatively\b", re.IGNORECASE),
    re.compile(r"\banother approach\b", re.IGNORECASE),
    re.compile(r"\bone option\b", re.IGNORECASE),
    re.compile(r"\bwe could also\b", re.IGNORECASE),
    re.compile(r"\binstead of\b", re.IGNORECASE),
    re.compile(r"\bor we could\b", re.IGNORECASE),
    re.compile(r"\blet me try a different\b", re.IGNORECASE),
]

_BACKTRACK_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bwait\b", re.IGNORECASE),
    re.compile(r"\bactually\b", re.IGNORECASE),
    re.compile(r"\bno,", re.IGNORECASE),
    re.compile(r"\blet me reconsider\b", re.IGNORECASE),
    re.compile(r"\bI was wrong\b", re.IGNORECASE),
    re.compile(r"\bthat's not right\b", re.IGNORECASE),
    re.compile(r"\bhmm\b", re.IGNORECASE),
    re.compile(r"\bon second thought\b", re.IGNORECASE),
]


def extract_alternatives_considered(text: str) -> int:
    """Count distinct alternative-rejection pattern matches in *text*."""
    if not text:
        return 0
    return sum(len(p.findall(text)) for p in _ALTERNATIVE_PATTERNS)


def extract_backtrack_count(text: str) -> int:
    """Count distinct self-correction pattern matches in *text*."""
    if not text:
        return 0
    return sum(len(p.findall(text)) for p in _BACKTRACK_PATTERNS)


# ---------------------------------------------------------------------------
# Aggregate extractors
# ---------------------------------------------------------------------------

def extract_all_tier0(
    sequence_number: int,
    total_calls: int,
    previous_results: list[bool],
    tool_name: str,
    tool_target: str,
    prior_calls: list[dict],
    recent_tool_names: list[str],
) -> dict[str, Any]:
    """Return a dict of all Tier 0 features."""
    return {
        "step_index_normalized": extract_step_index_normalized(
            sequence_number, total_calls,
        ),
        "prior_failure_streak": extract_prior_failure_streak(previous_results),
        "retry_count": extract_retry_count(tool_name, tool_target, prior_calls),
        "tool_switch_rate": extract_tool_switch_rate(recent_tool_names),
    }


def extract_verification_score(text: str) -> float:
    """Count verification-seeking language normalized by total tokens.

    Verification words ("verify", "check", "confirm", "test", "make sure")
    appeared 6x more often in failed agent reasoning than in successful.
    Discovered via exhaust mining on Phase 0 wave 1 data.
    """
    if not text:
        return 0.0
    tokens = text.lower().split()
    if not tokens:
        return 0.0
    verification_set = {"verify", "check", "confirm", "test", "ensure", "validate", "assert"}
    count = sum(1 for t in tokens if t.strip(".,;:!?()") in verification_set)
    count += text.lower().count("make sure")
    return count / len(tokens)


def extract_planning_score(text: str) -> float:
    """Count planning/sequencing language normalized by total tokens.

    Planning words ("let me", "now I", "first", "then", "next")
    appeared 2.2x more often in failed agent reasoning.
    Discovered via exhaust mining on Phase 0 wave 1 data.
    """
    if not text:
        return 0.0
    tokens = text.lower().split()
    if not tokens:
        return 0.0
    text_lower = text.lower()
    count = text_lower.count("let me") + text_lower.count("now i") + text_lower.count("now let")
    planning_set = {"first", "then", "next", "finally"}
    count += sum(1 for t in tokens if t.strip(".,;:!?()") in planning_set)
    return count / len(tokens)


def extract_all_tier1(
    reasoning_text: str,
    lexicon: dict,
) -> dict[str, Any]:
    """Return a dict of all Tier 1 features."""
    return {
        "hedging_score": extract_hedging_score(reasoning_text, lexicon),
        "deliberation_length": extract_deliberation_length(reasoning_text),
        "alternatives_considered": extract_alternatives_considered(reasoning_text),
        "backtrack_count": extract_backtrack_count(reasoning_text),
        "verification_score": extract_verification_score(reasoning_text),
        "planning_score": extract_planning_score(reasoning_text),
    }


def extract_all(
    tier0_args: dict[str, Any],
    tier1_args: dict[str, Any],
) -> dict[str, Any]:
    """Return merged dict of all Tier 0 + Tier 1 features.

    *tier0_args* is passed as kwargs to :func:`extract_all_tier0`.
    *tier1_args* is passed as kwargs to :func:`extract_all_tier1`.
    """
    features: dict[str, Any] = {}
    if tier0_args:
        features.update(extract_all_tier0(**tier0_args))
    if tier1_args:
        features.update(extract_all_tier1(**tier1_args))
    return features

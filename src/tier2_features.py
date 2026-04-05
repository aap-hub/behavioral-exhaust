"""
Tier 2 Feature Extraction for UGA Research Harness.

Pre-registered features from context/tier2-semantic-framework.md.
All linguistic features use MEAN aggregation (not sum) to control for task
length confound: failing tasks avg 22.9 state-modifying calls vs 16.6 passing.

Feature directions are pre-registered. A random noise control column is included
to verify the pipeline does not discover spurious signal.

Usage:
    from tier2_features import compute_tier2_task_level
    features = compute_tier2_task_level(db)  # {task_id: {feature: value, ...}}
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# Regex patterns (compiled once at module load)
# ---------------------------------------------------------------------------

# Structural: test commands in Bash
_TEST_CMD_RE = re.compile(
    r'pytest\b|python.*-m\s+pytest|unittest|test_|_test\.py',
    re.IGNORECASE,
)

# Linguistic: precision naming (backticks, CamelCase, snake_case, file paths)
_BACKTICK_RE = re.compile(r'`[^`]+`')
_CAMEL_RE = re.compile(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b')
_SNAKE_RE = re.compile(r'\b[a-z]+(?:_[a-z]+){1,}\b')
_FILEPATH_RE = re.compile(r'\b\w+\.\w{1,4}\b')  # e.g. views.py, test_foo.py

# Linguistic: self-directive density
_SELF_DIRECTIVE_PATTERNS = [
    re.compile(r'\bI need to\b', re.IGNORECASE),
    re.compile(r'\blet me\b', re.IGNORECASE),
    re.compile(r'\bI should\b', re.IGNORECASE),
    re.compile(r'\bI will\b', re.IGNORECASE),
    re.compile(r'\bI\'ll\b', re.IGNORECASE),
]

# Linguistic: metacognitive density
_METACOG_PATTERNS = [
    re.compile(r'\bwait\b', re.IGNORECASE),
    re.compile(r'\bactually\b', re.IGNORECASE),
    re.compile(r'\bhmm\b', re.IGNORECASE),
    re.compile(r'\bhold on\b', re.IGNORECASE),
    re.compile(r'\bon second thought\b', re.IGNORECASE),
    re.compile(r'\bI was wrong\b', re.IGNORECASE),
    re.compile(r'\bthat\'s not right\b', re.IGNORECASE),
    re.compile(r'\blet me reconsider\b', re.IGNORECASE),
    re.compile(r'\bI see\b', re.IGNORECASE),
]

# Linguistic: causal density
_CAUSAL_PATTERNS = [
    re.compile(r'\bbecause\b', re.IGNORECASE),
    re.compile(r'\bsince\b', re.IGNORECASE),
    re.compile(r'\btherefore\b', re.IGNORECASE),
    re.compile(r'\bdue to\b', re.IGNORECASE),
    re.compile(r'\bthis means\b', re.IGNORECASE),
    re.compile(r'\bwhich means\b', re.IGNORECASE),
    re.compile(r'\bthe reason\b', re.IGNORECASE),
    re.compile(r'\bcaused by\b', re.IGNORECASE),
    re.compile(r'\bas a result\b', re.IGNORECASE),
]

# Linguistic: instead/contrast density
_CONTRAST_PATTERNS = [
    re.compile(r'\binstead\b', re.IGNORECASE),
    re.compile(r'\brather than\b', re.IGNORECASE),
    re.compile(r'\binstead of\b', re.IGNORECASE),
]

# Linguistic: wrong/stuck density
_WRONG_STUCK_PATTERNS = [
    re.compile(r'\bwrong\b', re.IGNORECASE),
    re.compile(r'\bissue\b', re.IGNORECASE),
    re.compile(r'\bbug\b', re.IGNORECASE),
    re.compile(r'\bincorrect\b', re.IGNORECASE),
    re.compile(r'\bnot working\b', re.IGNORECASE),
    re.compile(r'\bdoesn\'t work\b', re.IGNORECASE),
    re.compile(r'\bstill failing\b', re.IGNORECASE),
    re.compile(r'\bbroken\b', re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Per-call linguistic feature extractors
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Whitespace split. Returns [] for None/empty."""
    if not text:
        return []
    return text.split()


def _count_patterns(text: str, patterns: list[re.Pattern]) -> int:
    """Count total matches across all patterns in text."""
    if not text:
        return 0
    return sum(len(p.findall(text)) for p in patterns)


def precision_naming_score(text: str) -> float:
    """Backtick-quoted terms, CamelCase, snake_case, file paths per token.

    Pre-registered direction: POSITIVE (more precise naming -> more success).
    Operationalizes the exhaust finding that successful agents 'name exact
    code changes.'
    """
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    count = (
        len(_BACKTICK_RE.findall(text))
        + len(_CAMEL_RE.findall(text))
        + len(_SNAKE_RE.findall(text))
        + len(_FILEPATH_RE.findall(text))
    )
    return count / len(tokens)


def self_directive_density(text: str) -> float:
    """'I need to', 'let me', 'I should' etc. per token.

    Pre-registered direction: NEGATIVE (more self-directives -> less success).
    Process narration without specifics is filler. 'let me check' appeared
    9x in fails vs 1x in passes in exhaust mining.
    """
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    return _count_patterns(text, _SELF_DIRECTIVE_PATTERNS) / len(tokens)


def metacognitive_density(text: str) -> float:
    """'wait', 'actually', 'hmm', 'hold on', 'I see' etc. per token.

    Pre-registered direction: POSITIVE (more metacognition -> more success).
    backtrack_count showed borderline positive correlation (rho=+0.300).
    'actually' appeared 4x more in passes in our data.
    """
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    return _count_patterns(text, _METACOG_PATTERNS) / len(tokens)


def causal_density(text: str) -> float:
    """'because', 'since', 'therefore', 'due to' etc. per token.

    Pre-registered direction: POSITIVE (more causal reasoning -> more success).
    Causal statements indicate the agent has a diagnosis, not just a
    symptom description.
    """
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    return _count_patterns(text, _CAUSAL_PATTERNS) / len(tokens)


def instead_contrast_density(text: str) -> float:
    """'instead', 'rather than' per token.

    Pre-registered direction: POSITIVE (more contrast -> more success).
    Exhaust mining found 'instead' 2.35x more in passes. Strategy shifts
    indicate adaptive problem-solving.
    """
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    return _count_patterns(text, _CONTRAST_PATTERNS) / len(tokens)


def wrong_stuck_density(text: str) -> float:
    """'wrong', 'issue', 'bug', 'incorrect', 'not working' etc. per token.

    Pre-registered direction: NEGATIVE (more negative evaluation -> less success).
    'wrong' appeared 7x more in fails in exhaust mining.
    """
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    return _count_patterns(text, _WRONG_STUCK_PATTERNS) / len(tokens)


# ---------------------------------------------------------------------------
# Per-call reasoning-action alignment
# ---------------------------------------------------------------------------

def reasoning_to_action_alignment(
    reasoning_text: str,
    tool_name: str,
    tool_params_json: str,
) -> float:
    """Does reasoning mention the file about to be edited?

    Pre-registered direction: POSITIVE (aligned reasoning -> more success).
    Data shows 19.5% alignment rate in passes vs 7.2% in fails.

    Returns 1.0 if the filename appears in reasoning, 0.0 otherwise.
    Returns NaN for non-Edit/Write calls (not applicable).
    """
    if tool_name not in ('Edit', 'Write'):
        return float('nan')
    if not reasoning_text:
        return 0.0
    try:
        params = json.loads(tool_params_json) if tool_params_json else {}
    except (json.JSONDecodeError, TypeError):
        return 0.0
    file_path = params.get('file_path', '')
    if not file_path:
        return 0.0
    filename = file_path.split('/')[-1]
    if filename and filename in reasoning_text:
        return 1.0
    return 0.0


# ---------------------------------------------------------------------------
# Structural features (computed per-run from call sequences)
# ---------------------------------------------------------------------------

def _parse_is_error(tool_result_json: str | None) -> bool | None:
    """Parse is_error from tool_result_json. Returns None if unparseable."""
    if not tool_result_json:
        return None
    try:
        result = json.loads(tool_result_json)
        return result.get('is_error', False)
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None


def _parse_file_path(tool_params_json: str | None) -> str:
    """Extract file_path from tool params."""
    if not tool_params_json:
        return ''
    try:
        params = json.loads(tool_params_json)
        return params.get('file_path', '') or params.get('path', '') or ''
    except (json.JSONDecodeError, AttributeError, TypeError):
        return ''


def _parse_command(tool_params_json: str | None) -> str:
    """Extract command from Bash tool params."""
    if not tool_params_json:
        return ''
    try:
        params = json.loads(tool_params_json)
        return params.get('command', '') or ''
    except (json.JSONDecodeError, AttributeError, TypeError):
        return ''


def compute_structural_features(calls: list[dict]) -> dict[str, float]:
    """Compute structural features from a run's tool call sequence.

    Args:
        calls: list of dicts with keys: tool_name, tool_params_json,
               tool_result_json, sequence_number, reasoning_text

    Returns:
        dict of structural feature name -> value
    """
    if not calls:
        return {
            'recovery_rate': 0.0,
            'fail_then_switch_rate': 0.0,
            'first_edit_position': 0.0,
            'unique_files_touched': 0,
            'edit_churn_rate': 0.0,
            'test_run_count': 0,
        }

    n = len(calls)

    # Parse error flags for each call
    errors = [_parse_is_error(c.get('tool_result_json')) for c in calls]
    # Treat None (unparseable) as False for error analysis
    is_error = [e if e is not None else False for e in errors]

    # --- S1: recovery_rate ---
    # fail->pass transitions / total failures
    total_failures = sum(1 for e in is_error if e)
    fail_to_pass = 0
    for i in range(len(is_error) - 1):
        if is_error[i] and not is_error[i + 1]:
            fail_to_pass += 1
    recovery_rate = fail_to_pass / max(total_failures, 1)

    # --- S1: fail_then_switch_rate ---
    # After error, does agent switch tools?
    fail_then_switch = 0
    fail_count_with_next = 0
    for i in range(len(is_error) - 1):
        if is_error[i]:
            fail_count_with_next += 1
            if calls[i]['tool_name'] != calls[i + 1]['tool_name']:
                fail_then_switch += 1
    fail_then_switch_rate = fail_then_switch / max(fail_count_with_next, 1)

    # --- S2: first_edit_position ---
    # Normalized position of first Edit/Write call
    first_edit_pos = 1.0  # default: no edits (maximally late)
    for c in calls:
        if c['tool_name'] in ('Edit', 'Write'):
            first_edit_pos = (c['sequence_number'] - 1) / max(n - 1, 1)
            break

    # --- S3: unique_files_touched ---
    files_edited = set()
    edit_counts_per_file: dict[str, int] = {}
    for c in calls:
        if c['tool_name'] in ('Edit', 'Write'):
            fp = _parse_file_path(c.get('tool_params_json'))
            if fp:
                files_edited.add(fp)
                edit_counts_per_file[fp] = edit_counts_per_file.get(fp, 0) + 1
    unique_files = len(files_edited)

    # --- S3: edit_churn_rate ---
    # Re-edits per unique file (1.0 = no churn, >1.0 = re-editing)
    total_edits = sum(edit_counts_per_file.values())
    edit_churn = total_edits / max(unique_files, 1)

    # --- S4: test_run_count ---
    test_count = 0
    for c in calls:
        if c['tool_name'] == 'Bash':
            cmd = _parse_command(c.get('tool_params_json'))
            if _TEST_CMD_RE.search(cmd):
                test_count += 1

    return {
        'recovery_rate': recovery_rate,
        'fail_then_switch_rate': fail_then_switch_rate,
        'first_edit_position': first_edit_pos,
        'unique_files_touched': unique_files,
        'edit_churn_rate': edit_churn,
        'test_run_count': test_count,
    }


def compute_linguistic_features_per_call(call: dict) -> dict[str, float]:
    """Compute linguistic features for a single tool call.

    Returns dict of feature_name -> value. Linguistic features are NaN
    when reasoning_text is absent (will be excluded from mean aggregation).
    """
    text = call.get('reasoning_text') or ''
    has_text = len(text.strip()) > 0

    if not has_text:
        return {
            'precision_naming_score': float('nan'),
            'self_directive_density': float('nan'),
            'metacognitive_density': float('nan'),
            'causal_density': float('nan'),
            'instead_contrast_density': float('nan'),
            'wrong_stuck_density': float('nan'),
            'reasoning_to_action_alignment': float('nan'),
        }

    alignment = reasoning_to_action_alignment(
        text,
        call.get('tool_name', ''),
        call.get('tool_params_json', ''),
    )

    return {
        'precision_naming_score': precision_naming_score(text),
        'self_directive_density': self_directive_density(text),
        'metacognitive_density': metacognitive_density(text),
        'causal_density': causal_density(text),
        'instead_contrast_density': instead_contrast_density(text),
        'wrong_stuck_density': wrong_stuck_density(text),
        'reasoning_to_action_alignment': alignment,
    }


# ---------------------------------------------------------------------------
# Task-level aggregation
# ---------------------------------------------------------------------------

def _nanmean(values: list[float]) -> float:
    """Mean ignoring NaN values. Returns 0.0 if all NaN or empty."""
    finite = [v for v in values if not (v != v)]  # NaN != NaN
    if not finite:
        return 0.0
    return sum(finite) / len(finite)


def compute_tier2_task_level(db: sqlite3.Connection) -> dict[str, dict[str, float]]:
    """Compute all Tier 2 features at the task level.

    Strategy:
    - For each task, use the LATEST validated run (by created_at).
    - Structural features are computed from the full call sequence.
    - Linguistic features are computed per-call and MEAN-aggregated.
    - A random_noise control column is included.

    Returns:
        {task_id: {feature_name: value, ...}} for all validated tasks.
    """
    # Step 1: Get latest validated run per task
    latest_runs = db.execute("""
        SELECT run_id, task_id, task_success, total_state_modifying_calls
        FROM runs
        WHERE validation_source IS NOT NULL
          AND task_success IS NOT NULL
        ORDER BY task_id, created_at DESC
    """).fetchall()

    # Deduplicate: keep latest run per task_id
    task_runs: dict[str, dict] = {}
    for r in latest_runs:
        tid = r['task_id']
        if tid not in task_runs:
            task_runs[tid] = dict(r)

    # Step 2: For each task, get all tool calls and compute features
    rng = np.random.RandomState(42)  # fixed seed for reproducibility
    results: dict[str, dict[str, float]] = {}

    for tid, run_info in task_runs.items():
        run_id = run_info['run_id']

        # Get all tool calls for this run
        calls_raw = db.execute("""
            SELECT tool_name, tool_params_json, tool_result_json,
                   sequence_number, reasoning_text
            FROM tool_calls
            WHERE run_id = ?
            ORDER BY sequence_number
        """, (run_id,)).fetchall()

        calls = [dict(c) for c in calls_raw]

        # Structural features (computed from full sequence)
        structural = compute_structural_features(calls)

        # Linguistic features (computed per call, then mean-aggregated)
        ling_per_call = [compute_linguistic_features_per_call(c) for c in calls]

        # Mean-aggregate each linguistic feature (NaN-aware)
        ling_keys = [
            'precision_naming_score', 'self_directive_density',
            'metacognitive_density', 'causal_density',
            'instead_contrast_density', 'wrong_stuck_density',
        ]
        ling_agg = {}
        for key in ling_keys:
            values = [lpc[key] for lpc in ling_per_call]
            ling_agg[key] = _nanmean(values)

        # Reasoning-to-action alignment (only for Edit/Write calls with reasoning)
        alignment_values = [
            lpc['reasoning_to_action_alignment'] for lpc in ling_per_call
        ]
        ling_agg['reasoning_to_action_alignment'] = _nanmean(alignment_values)

        # Combine all features
        task_features = {
            **structural,
            **ling_agg,
            'task_success': run_info['task_success'],
            'total_state_modifying_calls': run_info['total_state_modifying_calls'],
            'random_noise': rng.random(),
        }
        results[tid] = task_features

    return results


# ---------------------------------------------------------------------------
# Pre-registered expected directions
# ---------------------------------------------------------------------------

EXPECTED_DIRECTIONS: dict[str, str] = {
    # Structural features
    'recovery_rate':              'positive',   # H2
    'fail_then_switch_rate':      'positive',   # S1
    'first_edit_position':        'positive',   # H4
    'unique_files_touched':       'negative',   # H3
    'edit_churn_rate':            'negative',   # S3
    'test_run_count':             'positive',   # H5
    # Linguistic features (mean-aggregated)
    'precision_naming_score':     'positive',   # L3 (diagnosis_specificity)
    'self_directive_density':     'negative',   # L1 (vague_action_score proxy)
    'metacognitive_density':      'positive',   # L2
    'causal_density':             'positive',   # L3
    'instead_contrast_density':   'positive',   # exhaust mining
    'wrong_stuck_density':        'negative',   # L4
    # Interaction
    'reasoning_to_action_alignment': 'positive',  # I1
    # Controls
    'random_noise':               'null',
    'total_state_modifying_calls': 'negative',  # known confound: failing tasks longer
}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """Run feature extraction and print results."""
    import sys
    from pathlib import Path
    from scipy.stats import spearmanr

    db_path = Path(__file__).resolve().parent.parent / "data" / "uga.db"
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row

    features = compute_tier2_task_level(db)
    n_tasks = len(features)
    n_pass = sum(1 for f in features.values() if f['task_success'])
    n_fail = n_tasks - n_pass

    print(f"Tier 2 features computed for {n_tasks} tasks ({n_pass} pass, {n_fail} fail)")
    print()

    # Spearman correlations
    task_ids = sorted(features.keys())
    success = np.array([features[t]['task_success'] for t in task_ids], dtype=float)

    feature_names = [k for k in EXPECTED_DIRECTIONS.keys()]

    print(f"{'Feature':35} {'rho':>8} {'p_raw':>8} {'dir_match':>10} {'expected':>10}")
    print("-" * 80)

    for fname in feature_names:
        values = np.array([features[t].get(fname, 0) for t in task_ids], dtype=float)
        if np.std(values) == 0:
            print(f"{fname:35} {'--':>8} {'--':>8} {'no var':>10} {EXPECTED_DIRECTIONS[fname]:>10}")
            continue
        rho, p = spearmanr(values, success)
        expected = EXPECTED_DIRECTIONS[fname]
        if expected == 'null':
            match = 'control'
        elif expected == 'positive':
            match = 'YES' if rho > 0 else 'NO'
        elif expected == 'negative':
            match = 'YES' if rho < 0 else 'NO'
        else:
            match = '?'
        sig = '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else ''
        print(f"{fname:35} {rho:+8.3f} {p:8.4f}{sig:3s} {match:>10} {expected:>10}")

    print(f"\nn={n_tasks} tasks. Significance: * p<0.05  ** p<0.01  *** p<0.001 (uncorrected)")


if __name__ == "__main__":
    main()

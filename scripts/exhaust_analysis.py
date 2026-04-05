#!/usr/bin/env python3
"""
Exhaust Analysis — Extract features from Sonnet's THINKING content.

This script reads the raw_stream_json from the protected database (read-only),
extracts thinking blocks (the unguarded internal reasoning), computes all
features, and writes results to a new analysis DB. No modifications to the
source database.

Two feature sets:
1. "agent_message" features — from text blocks (what we had before)
2. "exhaust" features — from thinking blocks (the new data)

Usage:
    python3 scripts/exhaust_analysis.py
"""

import json
import os
import re
import sqlite3
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
import statsmodels.formula.api as smf
from scipy.stats import chi2
import pandas as pd

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DB = PROJECT_ROOT / "data" / "uga_protected_backup.db"
OUTPUT_DIR = PROJECT_ROOT / "data" / "exhaust_results"

OUTPUT_DIR.mkdir(exist_ok=True)


# ─── Extract thinking vs text from raw streams ───────────────────────────

def extract_blocks_from_stream(raw: str) -> list[dict]:
    """Extract all content blocks with their types from a raw stream."""
    blocks = []
    for line in raw.split("\n"):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") != "assistant":
            continue
        for block in ev.get("message", {}).get("content", []):
            bt = block.get("type", "")
            if bt == "thinking":
                text = block.get("thinking", "") or block.get("text", "")
                if text:
                    blocks.append({"type": "thinking", "text": text})
            elif bt == "text":
                text = block.get("text", "")
                if text:
                    blocks.append({"type": "text", "text": text})
            elif bt == "tool_use":
                blocks.append({
                    "type": "tool_use",
                    "name": block.get("name", ""),
                    "id": block.get("id", ""),
                    "input": block.get("input", {}),
                })
    return blocks


def extract_per_call_reasoning(raw: str) -> list[dict]:
    """For each tool_use, extract preceding thinking and text separately."""
    blocks = extract_blocks_from_stream(raw)

    calls = []
    pending_thinking = []
    pending_text = []

    for block in blocks:
        if block["type"] == "thinking":
            pending_thinking.append(block["text"])
        elif block["type"] == "text":
            pending_text.append(block["text"])
        elif block["type"] == "tool_use":
            calls.append({
                "tool_name": block["name"],
                "tool_id": block["id"],
                "tool_input": block["input"],
                "thinking": "\n".join(pending_thinking),
                "agent_message": "\n".join(pending_text),
                "combined": "\n".join(pending_thinking + pending_text),
            })
            pending_thinking = []
            pending_text = []

    return calls


# ─── Feature extraction (works on any text) ─────────────────────────────

def compute_linguistic_features(text: str) -> dict:
    """Compute all linguistic features from a text block."""
    if not text or len(text) < 10:
        return {k: 0 for k in [
            "metacognitive_density", "tentative_density", "insight_density",
            "instead_contrast_density", "self_directive_density",
            "wrong_stuck_density", "causal_density", "hedging_density",
            "token_count",
        ]}

    text_lower = text.lower()
    tokens = len(text_lower.split())
    if tokens == 0:
        tokens = 1

    features = {
        "metacognitive_density": len(re.findall(
            r'\b(actually|wait|hmm|hold on|i see|oh right|ah)\b', text_lower)) / tokens,
        "tentative_density": len(re.findall(
            r'\b(let me try|maybe|not sure|perhaps|try another|might work)\b', text_lower)) / tokens,
        "insight_density": len(re.findall(
            r'\b(actually|i understand|the issue is|the problem is|the bug is|i see now|that explains)\b', text_lower)) / tokens,
        "instead_contrast_density": len(re.findall(
            r'\b(instead|rather than|instead of|but actually|no wait)\b', text_lower)) / tokens,
        "self_directive_density": len(re.findall(
            r'\b(i need to|i should|let me|i\'ll|i will|i have to|i must)\b', text_lower)) / tokens,
        "wrong_stuck_density": len(re.findall(
            r'\b(wrong|incorrect|mistake|broken|doesn\'t work|not working)\b', text_lower)) / tokens,
        "causal_density": len(re.findall(
            r'\b(because|since|therefore|due to|causes|caused by|so that)\b', text_lower)) / tokens,
        "hedging_density": len(re.findall(
            r'\b(might|may|could|possibly|probably|seems|appears|suggest)\b', text_lower)) / tokens,
        "token_count": tokens,
    }
    return features


def compute_structural_features(calls: list[dict], success: int) -> dict:
    """Compute structural features from the call sequence."""
    n = len(calls)
    if n == 0:
        return {}

    # First edit position
    first_edit = 1.0
    for i, c in enumerate(calls):
        if c["tool_name"] in ("Edit", "Write"):
            first_edit = i / n if n > 0 else 1.0
            break

    # File targets for edits
    edit_files = set()
    for c in calls:
        if c["tool_name"] in ("Edit", "Write"):
            fp = c["tool_input"].get("file_path", "")
            if fp:
                edit_files.add(fp.split("/")[-1])

    # Reasoning-to-action alignment (using thinking, not agent_message)
    align_scores = []
    for c in calls:
        if c["tool_name"] not in ("Edit", "Write"):
            continue
        fp = c["tool_input"].get("file_path", "")
        basename = fp.split("/")[-1].split(".")[0] if fp else ""
        thinking = c["thinking"].lower()
        if basename and len(basename) > 2 and thinking:
            align_scores.append(1 if basename in thinking else 0)

    alignment_thinking = np.mean(align_scores) if align_scores else 0

    # Same but using agent_message
    align_msg = []
    for c in calls:
        if c["tool_name"] not in ("Edit", "Write"):
            continue
        fp = c["tool_input"].get("file_path", "")
        basename = fp.split("/")[-1].split(".")[0] if fp else ""
        msg = c["agent_message"].lower()
        if basename and len(basename) > 2 and msg:
            align_msg.append(1 if basename in msg else 0)

    alignment_message = np.mean(align_msg) if align_msg else 0

    return {
        "first_edit_position": first_edit,
        "unique_files_touched": len(edit_files),
        "n_calls": n,
        "alignment_from_thinking": alignment_thinking,
        "alignment_from_message": alignment_message,
    }


# ─── Main analysis ──────────────────────────────────────────────────────

def main():
    print("EXHAUST ANALYSIS — Thinking vs Agent Message Features")
    print("=" * 60)

    # Open source DB read-only
    db = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row

    runs = db.execute("""
        SELECT run_id, task_id, task_success, raw_stream_json,
               total_state_modifying_calls, validation_source
        FROM runs
        WHERE task_source = 'swe-bench-lite'
          AND task_success IS NOT NULL
          AND validation_source IS NOT NULL
          AND raw_stream_json IS NOT NULL
    """).fetchall()

    print(f"Runs: {len(runs)}")

    # Extract features per run
    all_runs = []

    for run in runs:
        calls = extract_per_call_reasoning(run["raw_stream_json"])
        if not calls:
            continue

        repo = run["task_id"].split("__")[0]

        # Compute linguistic features from THINKING blocks
        thinking_features = []
        for c in calls:
            if c["thinking"]:
                thinking_features.append(compute_linguistic_features(c["thinking"]))

        # Compute linguistic features from AGENT MESSAGE blocks
        message_features = []
        for c in calls:
            if c["agent_message"]:
                message_features.append(compute_linguistic_features(c["agent_message"]))

        # Aggregate: mean across calls
        def mean_features(feat_list, prefix):
            if not feat_list:
                return {f"{prefix}_{k}": 0 for k in feat_list[0].keys()} if feat_list else {}
            result = {}
            for key in feat_list[0].keys():
                vals = [f[key] for f in feat_list]
                result[f"{prefix}_{key}"] = np.mean(vals)
            return result

        thinking_agg = mean_features(thinking_features, "thinking") if thinking_features else {
            f"thinking_{k}": 0 for k in [
                "metacognitive_density", "tentative_density", "insight_density",
                "instead_contrast_density", "self_directive_density",
                "wrong_stuck_density", "causal_density", "hedging_density", "token_count",
            ]
        }

        message_agg = mean_features(message_features, "message") if message_features else {
            f"message_{k}": 0 for k in [
                "metacognitive_density", "tentative_density", "insight_density",
                "instead_contrast_density", "self_directive_density",
                "wrong_stuck_density", "causal_density", "hedging_density", "token_count",
            ]
        }

        structural = compute_structural_features(calls, run["task_success"])

        row = {
            "run_id": run["run_id"],
            "task_id": run["task_id"],
            "repo": repo,
            "success": run["task_success"],
            "n_thinking_blocks": len(thinking_features),
            "n_message_blocks": len(message_features),
            "total_thinking_chars": sum(len(c["thinking"]) for c in calls),
            "total_message_chars": sum(len(c["agent_message"]) for c in calls),
            **thinking_agg,
            **message_agg,
            **structural,
        }
        all_runs.append(row)

    df = pd.DataFrame(all_runs)
    print(f"Processed: {len(df)} runs")
    print(f"Thinking coverage: {(df['n_thinking_blocks'] > 0).mean():.0%} of runs")
    print(f"Avg thinking chars/run: {df['total_thinking_chars'].mean():.0f}")
    print(f"Avg message chars/run: {df['total_message_chars'].mean():.0f}")

    # Deduplicate: latest run per task
    df = df.sort_values("run_id").groupby("task_id").last().reset_index()
    print(f"After dedup (latest per task): {len(df)} tasks")
    print(f"Pass rate: {df['success'].mean():.0%}")

    # ─── Analysis ────────────────────────────────────────────────────

    print(f"\n{'=' * 60}")
    print("THINKING vs MESSAGE: Which source has more signal?")
    print(f"{'=' * 60}\n")

    # Compare same features from thinking vs message
    feature_pairs = [
        ("metacognitive_density", "thinking_metacognitive_density", "message_metacognitive_density"),
        ("tentative_density", "thinking_tentative_density", "message_tentative_density"),
        ("insight_density", "thinking_insight_density", "message_insight_density"),
        ("instead_contrast", "thinking_instead_contrast_density", "message_instead_contrast_density"),
        ("self_directive", "thinking_self_directive_density", "message_self_directive_density"),
        ("wrong_stuck", "thinking_wrong_stuck_density", "message_wrong_stuck_density"),
        ("causal_density", "thinking_causal_density", "message_causal_density"),
        ("hedging_density", "thinking_hedging_density", "message_hedging_density"),
    ]

    success = df["success"].values

    print(f"{'Feature':<25} {'Think rho':>10} {'Think p':>10} {'Msg rho':>10} {'Msg p':>10} {'Winner':>8}")
    print("-" * 75)

    results = []
    for name, think_col, msg_col in feature_pairs:
        if think_col not in df.columns or msg_col not in df.columns:
            continue

        think_vals = df[think_col].values.astype(float)
        msg_vals = df[msg_col].values.astype(float)

        rho_t, p_t = spearmanr(think_vals, success) if np.std(think_vals) > 0 else (0, 1)
        rho_m, p_m = spearmanr(msg_vals, success) if np.std(msg_vals) > 0 else (0, 1)

        winner = "THINK" if abs(rho_t) > abs(rho_m) else "MSG" if abs(rho_m) > abs(rho_t) else "TIE"
        sig_t = "*" if p_t < 0.05 else ""
        sig_m = "*" if p_m < 0.05 else ""

        print(f"  {name:<23} {rho_t:+.3f}{sig_t:1} {p_t:10.4f} {rho_m:+.3f}{sig_m:1} {p_m:10.4f} {winner:>8}")
        results.append((name, rho_t, p_t, rho_m, p_m, winner))

    # Structural features + alignment comparison
    print(f"\n{'=' * 60}")
    print("STRUCTURAL FEATURES + ALIGNMENT")
    print(f"{'=' * 60}\n")

    struct_features = [
        ("first_edit_position", "first_edit_position"),
        ("n_calls", "n_calls"),
        ("alignment_thinking", "alignment_from_thinking"),
        ("alignment_message", "alignment_from_message"),
    ]

    print(f"{'Feature':<25} {'rho':>10} {'p':>10}")
    print("-" * 48)
    for name, col in struct_features:
        if col not in df.columns:
            continue
        vals = df[col].values.astype(float)
        if np.std(vals) == 0:
            continue
        rho, p = spearmanr(vals, success)
        sig = "*" if p < 0.05 else ""
        print(f"  {name:<23} {rho:+.3f}{sig:1} {p:10.4f}")

    # Mixed-effects on the best features
    print(f"\n{'=' * 60}")
    print("MIXED-EFFECTS (repo as fixed effect, 3 largest repos)")
    print(f"{'=' * 60}\n")

    big_repos = df["repo"].value_counts().head(3).index.tolist()
    df_big = df[df["repo"].isin(big_repos)].copy()

    test_features = [
        "thinking_metacognitive_density", "thinking_tentative_density",
        "thinking_insight_density", "thinking_instead_contrast_density",
        "thinking_hedging_density", "thinking_causal_density",
        "message_metacognitive_density", "message_tentative_density",
        "alignment_from_thinking", "alignment_from_message",
        "first_edit_position", "n_calls",
    ]

    # Null model
    null = smf.logit("success ~ C(repo)", df_big).fit(disp=0)
    null_ll = null.llf

    me_results = []
    for feat in test_features:
        if feat not in df_big.columns:
            continue
        col = df_big[feat].astype(float)
        if col.std() == 0:
            continue
        df_big["_f"] = (col - col.mean()) / col.std()
        try:
            m = smf.logit("success ~ _f + C(repo)", df_big).fit(disp=0)
            coef = m.params["_f"]
            p = m.pvalues["_f"]
            lr = 2 * (m.llf - null_ll)
            lr_p = chi2.sf(max(lr, 0), df=1)
            me_results.append((feat, coef, p, lr_p))
        except:
            pass

    me_results.sort(key=lambda x: x[2])
    bonf = 0.05 / len(me_results)

    print(f"{'Feature':<40} {'coef':>8} {'p':>10} {'verdict':>12}")
    print("-" * 72)
    for feat, coef, p, lr_p in me_results:
        v = "***BONF" if p < bonf else "**p<.01" if p < 0.01 else "*p<.05" if p < 0.05 else ""
        print(f"  {feat:<38} {coef:+8.3f} {p:10.4f} {v:>12}")

    print(f"\nBonferroni: p < {bonf:.4f} ({len(me_results)} tests)")

    # Within-repo for sympy
    print(f"\n{'=' * 60}")
    print("WITHIN SYMPY (n={})".format(len(df[df['repo']=='sympy'])))
    print(f"{'=' * 60}\n")

    df_sympy = df[df["repo"] == "sympy"]
    sympy_success = df_sympy["success"].values

    all_features = [f for f in test_features if f in df_sympy.columns]
    sympy_results = []
    for feat in all_features:
        vals = df_sympy[feat].values.astype(float)
        if np.std(vals) == 0:
            continue
        rho, p = spearmanr(vals, sympy_success)
        sympy_results.append((feat, rho, p))

    sympy_results.sort(key=lambda x: x[2])
    for feat, rho, p in sympy_results:
        sig = "*" if p < 0.05 else ""
        print(f"  {feat:<38} rho={rho:+.3f} p={p:.4f} {sig}")

    # Save results
    output_file = OUTPUT_DIR / "exhaust_analysis_results.md"
    with open(output_file, "w") as f:
        f.write("# Exhaust Analysis Results\n\n")
        f.write(f"Runs: {len(runs)}, Tasks: {len(df)}, Pass rate: {df['success'].mean():.0%}\n\n")
        f.write("## Thinking vs Message Feature Comparison\n\n")
        f.write(f"| Feature | Think rho | Think p | Msg rho | Msg p | Winner |\n")
        f.write(f"|---------|-----------|---------|---------|-------|--------|\n")
        for name, rho_t, p_t, rho_m, p_m, winner in results:
            f.write(f"| {name} | {rho_t:+.3f} | {p_t:.4f} | {rho_m:+.3f} | {p_m:.4f} | {winner} |\n")
        f.write("\n## Mixed-Effects Results\n\n")
        for feat, coef, p, lr_p in me_results:
            v = "BONF" if p < bonf else "p<.05" if p < 0.05 else ""
            f.write(f"- {feat}: coef={coef:+.3f}, p={p:.4f} {v}\n")

    print(f"\nResults saved to {output_file}")
    db.close()


if __name__ == "__main__":
    main()

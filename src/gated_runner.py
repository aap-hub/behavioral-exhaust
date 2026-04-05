"""
UGA Phase 1 — Gated Task Runner

Extends the Phase 0 runner with behavioral gates. Before each Edit/Write
tool call, the gate inspects the agent's reasoning and either allows or
blocks the call.

IMPORTANT DESIGN NOTE:
Claude Code's `claude -p` runs autonomously. We cannot intercept mid-stream
to block tool calls in real-time. Instead, Phase 1 uses a two-mode approach:

1. POST-HOC ANALYSIS MODE (default, used for all conditions):
   Run the task ungated (same as Phase 0), capture the full trace, then
   retroactively apply the gate to each Edit/Write call. This tells us
   what the gate WOULD HAVE done, enabling precision/recall computation
   without the overhead of actual intervention.

2. SYSTEM-PROMPT INJECTION MODE (for P1/P2 perturbation conditions):
   Modify the system prompt to include gate-like instructions. The agent
   is told to state files before editing (P1) or that edits will be
   reviewed (P2). This tests whether prompt manipulation alone changes
   behavioral features.

The post-hoc mode is scientifically equivalent to live gating for measuring
gate accuracy (precision/recall), and it enables running all conditions on
the SAME agent trajectory -- which is a massive methodological advantage
because it eliminates between-run variance when comparing gate strategies.

However, it does NOT test whether gating actually improves outcomes (H1),
because the agent never receives gate feedback. For H1, we would need
live gating via Claude Code's pre-tool-use hook feature (if available) or
a custom agent loop. This is noted as a limitation.

Usage:
    python src/gated_runner.py --condition A1 --task django__django-11179
    python src/gated_runner.py --condition B2 --all
    python src/gated_runner.py --analyze --condition A1
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from db import init_db
from gate import (
    GateConfig, GateDecision, IntrospectiveGate, ExtrospectiveGate,
    CombinedGate, CONDITION_MAP,
    get_gate_for_condition, get_timing_for_condition, get_prompt_modifier,
    init_gate_decisions_table, store_gate_decision,
)
from trace_collector import parse_stream_json, classify_state_modifying
from runner import run_task, DEFAULT_DB_PATH

log = logging.getLogger("uga.gated_runner")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ---------------------------------------------------------------------------
# Post-hoc gate application
# ---------------------------------------------------------------------------

def apply_gate_posthoc(
    run_id: str,
    condition_code: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    config: Optional[GateConfig] = None,
) -> list[GateDecision]:
    """Apply a gate retroactively to an existing run's tool calls.

    Reads the run's raw stream-json from the database, re-parses it,
    and applies the gate to each Edit/Write call. Records decisions
    in the gate_decisions table.

    This is the primary analysis mode for Phase 1.

    Args:
        run_id: The run to analyze.
        condition_code: Experimental condition (A1, B2, etc.).
        db_path: Database path.
        config: Gate configuration (thresholds).

    Returns:
        List of GateDecision objects, one per gated call.
    """
    config = config or GateConfig.from_file()
    gate = get_gate_for_condition(condition_code, config)
    timing = get_timing_for_condition(condition_code)

    if gate is None:
        log.info("Condition %s is ungated, no gate to apply", condition_code)
        return []

    db = init_db(str(db_path))
    init_gate_decisions_table(db)

    # Get the run record
    run_row = db.execute(
        "SELECT * FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if not run_row:
        log.error("Run %s not found", run_id)
        db.close()
        return []

    task_id = run_row["task_id"]

    # Get bug description from manifest for extrospective gate
    bug_description = _get_bug_description(task_id)

    # Get all tool calls for this run (state-modifying)
    calls = db.execute("""
        SELECT decision_id, sequence_number, tool_name,
               tool_params_json, reasoning_text
        FROM tool_calls
        WHERE run_id = ?
        ORDER BY sequence_number
    """, (run_id,)).fetchall()

    total_calls = len(calls)
    decisions = []

    for call in calls:
        tool_name = call["tool_name"]

        # Only gate Edit/Write calls
        if tool_name not in ("Edit", "Write"):
            continue

        params = json.loads(call["tool_params_json"]) if call["tool_params_json"] else {}
        reasoning = call["reasoning_text"] or ""
        seq_num = call["sequence_number"]

        # Evaluate the gate
        if isinstance(gate, CombinedGate):
            decision = gate.evaluate(
                reasoning_text=reasoning,
                tool_params=params,
                bug_description=bug_description,
                sequence_number=seq_num,
                total_calls_estimate=total_calls,
                gate_timing=timing,
            )
        elif isinstance(gate, ExtrospectiveGate):
            decision = gate.evaluate(
                reasoning_text=reasoning,
                tool_params=params,
                bug_description=bug_description,
                sequence_number=seq_num,
                total_calls_estimate=total_calls,
                gate_timing=timing,
            )
        elif isinstance(gate, IntrospectiveGate):
            decision = gate.evaluate(
                reasoning_text=reasoning,
                tool_params=params,
                sequence_number=seq_num,
                total_calls_estimate=total_calls,
                gate_timing=timing,
            )
        else:
            continue

        decision.run_id = run_id
        decision.tool_call_sequence = seq_num

        decisions.append(decision)

        # Store in DB
        store_gate_decision(db, decision)

        log.debug(
            "Gate %s seq=%d: %s (%s)",
            condition_code, seq_num, decision.verdict, decision.reason[:80]
        )

    db.close()

    # Summary
    verdicts = {}
    for d in decisions:
        verdicts[d.verdict] = verdicts.get(d.verdict, 0) + 1
    log.info(
        "Post-hoc gate for run %s condition %s: %d calls, verdicts=%s",
        run_id, condition_code, len(decisions), verdicts
    )

    return decisions


def apply_gate_to_all_runs(
    condition_code: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    config: Optional[GateConfig] = None,
    task_filter: Optional[list[str]] = None,
) -> dict[str, list[GateDecision]]:
    """Apply a gate post-hoc to all validated Phase 0 runs.

    Args:
        condition_code: Experimental condition.
        db_path: Database path.
        config: Gate configuration.
        task_filter: If set, only process these task IDs.

    Returns:
        Dict mapping run_id -> list of GateDecisions.
    """
    db = init_db(str(db_path))
    init_gate_decisions_table(db)

    query = """
        SELECT run_id, task_id FROM runs
        WHERE validation_source IS NOT NULL
          AND task_success IS NOT NULL
    """
    params = []

    if task_filter:
        placeholders = ",".join("?" * len(task_filter))
        query += f" AND task_id IN ({placeholders})"
        params = task_filter

    runs = db.execute(query, params).fetchall()
    db.close()

    log.info("Applying condition %s to %d validated runs", condition_code, len(runs))

    all_decisions = {}
    for i, run in enumerate(runs):
        decisions = apply_gate_posthoc(
            run["run_id"], condition_code, db_path, config
        )
        all_decisions[run["run_id"]] = decisions

        if (i + 1) % 20 == 0:
            log.info("Progress: %d/%d runs", i + 1, len(runs))

    return all_decisions


# ---------------------------------------------------------------------------
# Run a task with prompt modification (P1/P2)
# ---------------------------------------------------------------------------

def run_task_with_prompt_mod(
    task_id: str,
    condition_code: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict:
    """Run a task with a modified prompt (P1 or P2 perturbation).

    This creates an ACTUAL new run with the modified prompt.
    The condition is recorded in the runs table.

    Args:
        task_id: Task to run.
        condition_code: P1 or P2.
        db_path: Database path.

    Returns:
        Run result dict (same format as runner.run_task).
    """
    modifier = get_prompt_modifier(condition_code)
    if modifier is None:
        log.warning("No prompt modifier for condition %s, running ungated", condition_code)

    # We need to modify the task prompt. Load the task, append the modifier,
    # and pass it through. The cleanest way is to temporarily modify the
    # manifest task, but that's fragile. Instead, we'll create a custom
    # run using runner internals.
    from runner import (
        get_task, create_workspace, cleanup_workspace,
        extract_token_count, count_all_tool_calls,
        _run_validation, MANIFEST_PATH, _config,
    )
    import subprocess
    import tempfile
    import threading
    import uuid

    run_id = f"run-{uuid.uuid4().hex[:12]}"
    task = get_task(task_id, MANIFEST_PATH)
    phase = task["phase"]

    # Modify the prompt
    original_prompt = task["prompt"]
    modified_prompt = original_prompt + (modifier or "")

    workspace = None
    start_time = datetime.now(timezone.utc)

    try:
        workspace = create_workspace(task["repo"])
        model = os.environ.get("UGA_MODEL", "sonnet")
        cmd = [
            "claude",
            "-p", modified_prompt,
            "--model", model,
            "--output-format", "stream-json",
            "--verbose",
        ]

        stderr_file = tempfile.NamedTemporaryFile(
            mode="w", prefix="uga_stderr_", suffix=".log", delete=False
        )
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=stderr_file,
            cwd=str(workspace), text=True,
        )

        timed_out = False
        def _watchdog():
            nonlocal timed_out
            timed_out = True
            proc.kill()

        timer = threading.Timer(_config["task_timeout_seconds"], _watchdog)
        timer.start()

        stdout_lines = []
        for line in proc.stdout:
            stdout_lines.append(line)

        proc.wait()
        timer.cancel()
        stderr_file.close()

        end_time = datetime.now(timezone.utc)
        raw_stream = "".join(stdout_lines)
        exit_code = proc.returncode

        task_success = None
        if not timed_out:
            task_success = _run_validation(task["validation_command"], workspace)

        tool_calls = parse_stream_json(io.StringIO(raw_stream), run_id=run_id)
        for tc in tool_calls:
            tc["task_id"] = task_id
            tc["phase"] = phase
            tc["condition"] = condition_code

        run_record = {
            "run_id": run_id,
            "task_id": task_id,
            "phase": phase,
            "condition": condition_code,
            "model_version": model,
            "task_source": task.get("source", "synthetic"),
            "wave": int(os.environ.get("UGA_WAVE", "1")),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "total_tokens": extract_token_count(raw_stream),
            "total_tool_calls": count_all_tool_calls(raw_stream),
            "total_state_modifying_calls": len(tool_calls),
            "task_success": task_success,
            "exit_code": exit_code if not timed_out else -9,
            "wall_clock_seconds": (end_time - start_time).total_seconds(),
            "raw_stream_json": raw_stream,
            "timed_out": timed_out,
            "error": "timeout" if timed_out else None,
            "notes": f"prompt_modifier={condition_code}",
        }

        conn = init_db(str(db_path))
        try:
            from db import insert_run as db_insert_run, insert_tool_call as db_insert_tool_call
            conn.execute("BEGIN")
            db_insert_run(conn, run_record)
            for tc in tool_calls:
                db_insert_tool_call(conn, tc)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return run_record

    finally:
        if workspace:
            cleanup_workspace(workspace)
        if 'stderr_file' in dir() and os.path.exists(stderr_file.name):
            os.unlink(stderr_file.name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_bug_description(task_id: str) -> str:
    """Get the bug description for a task from the manifest."""
    try:
        import yaml
        for manifest_name in ["manifest.yaml", "wave_expansion.yaml"]:
            manifest_path = PROJECT_ROOT / "tasks" / manifest_name
            if manifest_path.exists():
                with open(manifest_path) as f:
                    data = yaml.safe_load(f)
                for task in data.get("tasks", []):
                    if task["task_id"] == task_id:
                        return task.get("prompt", task_id)
    except Exception:
        pass
    return f"Fix the bug in {task_id}"


# ---------------------------------------------------------------------------
# Gate analysis utilities
# ---------------------------------------------------------------------------

def compute_gate_metrics(
    condition_code: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict:
    """Compute precision, recall, and F1 for a gate condition.

    Gate precision: when gate blocks, was the edit actually wrong?
    Gate recall: of wrong edits (in failing runs), how many did the gate catch?

    "Wrong edit" is operationalized as: the run ultimately failed.
    This is a conservative proxy -- individual edits in a failing run may
    have been correct, but the run as a whole failed.
    """
    db = init_db(str(db_path))
    init_gate_decisions_table(db)

    # Join gate decisions with run outcomes
    # Match by BOTH gate_type AND gate_timing to distinguish conditions
    spec = CONDITION_MAP.get(condition_code, {})
    source = spec.get("source", "")
    timing = get_timing_for_condition(condition_code)

    rows = db.execute("""
        SELECT gd.verdict, gd.run_id, r.task_success
        FROM gate_decisions gd
        JOIN runs r ON gd.run_id = r.run_id
        WHERE gd.gate_type = ? AND gd.gate_timing = ?
        ORDER BY gd.run_id, gd.tool_call_sequence
    """, (source, timing)).fetchall()

    db.close()

    if not rows:
        return {"error": f"No gate decisions found for condition {condition_code}"}

    # Per-call confusion matrix
    tp = fp = tn = fn = 0
    for row in rows:
        blocked = row["verdict"] == "block"
        failed = not row["task_success"]

        if blocked and failed:
            tp += 1
        elif blocked and not failed:
            fp += 1
        elif not blocked and failed:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    total = tp + fp + tn + fn
    block_rate = (tp + fp) / total if total > 0 else 0.0

    return {
        "condition": condition_code,
        "total_decisions": total,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "block_rate": round(block_rate, 4),
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="UGA Phase 1 Gated Runner",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Run a single task with prompt modification
    run_p = sub.add_parser("run", help="Run a task with prompt modification (P1/P2)")
    run_p.add_argument("--condition", required=True, choices=list(CONDITION_MAP.keys()))
    run_p.add_argument("--task", required=True)
    run_p.add_argument("--db", default=str(DEFAULT_DB_PATH))

    # Apply gate post-hoc to existing runs
    gate_p = sub.add_parser("gate", help="Apply gate post-hoc to existing runs")
    gate_p.add_argument("--condition", required=True, choices=list(CONDITION_MAP.keys()))
    gate_p.add_argument("--run-id", default=None, help="Specific run ID (default: all)")
    gate_p.add_argument("--db", default=str(DEFAULT_DB_PATH))

    # Analyze gate metrics
    analyze_p = sub.add_parser("analyze", help="Compute gate precision/recall")
    analyze_p.add_argument("--condition", required=True, choices=list(CONDITION_MAP.keys()))
    analyze_p.add_argument("--db", default=str(DEFAULT_DB_PATH))

    args = parser.parse_args()

    if args.command == "run":
        if args.condition in ("P1", "P2"):
            result = run_task_with_prompt_mod(args.task, args.condition, args.db)
            status = "PASS" if result.get("task_success") else "FAIL"
            print(f"{args.task}: {status} ({result.get('wall_clock_seconds', 0):.0f}s)")
        else:
            # For gated conditions, run ungated then apply gate post-hoc
            result = run_task(args.task, condition=args.condition, db_path=args.db)
            decisions = apply_gate_posthoc(result["run_id"], args.condition, args.db)
            blocked = sum(1 for d in decisions if d.verdict == "block")
            print(f"{args.task}: {'PASS' if result.get('task_success') else 'FAIL'}")
            print(f"  Gate: {len(decisions)} decisions, {blocked} blocked")

    elif args.command == "gate":
        if args.run_id:
            decisions = apply_gate_posthoc(args.run_id, args.condition, args.db)
            for d in decisions:
                print(f"  seq={d.tool_call_sequence} {d.verdict}: {d.reason[:80]}")
        else:
            all_decisions = apply_gate_to_all_runs(args.condition, db_path=args.db)
            total = sum(len(v) for v in all_decisions.values())
            blocked = sum(1 for ds in all_decisions.values() for d in ds if d.verdict == "block")
            print(f"Condition {args.condition}: {total} decisions across {len(all_decisions)} runs")
            print(f"  Blocked: {blocked} ({100*blocked/total:.1f}%)" if total > 0 else "  No decisions")

    elif args.command == "analyze":
        metrics = compute_gate_metrics(args.condition, args.db)
        print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()

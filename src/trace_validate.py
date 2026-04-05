#!/usr/bin/env python3
"""
Trace Validator — Cross-referenced validation from agent test output.

Epistemically honest approach:
1. Extract ALL test executions from the agent's trace
2. Cross-reference against the FAIL_TO_PASS tests from the manifest
3. Label HIGH confidence only when agent ran the SPECIFIC tests we care about
4. Label MEDIUM when agent ran related tests
5. Leave UNCLEAR when we can't determine

This is not "taking the agent's word for it" — it's auditing the agent's
test output against our known-good test specification.

Usage:
    python3 src/trace_validate.py                # Validate all runs
    python3 src/trace_validate.py --dry-run      # Show without updating
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DB_PATH = PROJECT_ROOT / "data" / "uga.db"
MANIFEST_PATH = PROJECT_ROOT / "tasks" / "manifest.yaml"
EXPANSION_PATH = PROJECT_ROOT / "tasks" / "wave_expansion.yaml"


def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db


def load_task_meta(task_id: str) -> dict:
    import yaml
    for path in [MANIFEST_PATH, EXPANSION_PATH]:
        if not path.exists():
            continue
        with open(path) as f:
            data = yaml.safe_load(f)
        for t in (data or {}).get("tasks", []):
            if t["task_id"] == task_id:
                return t
    return {}


def extract_test_executions(raw: str) -> list[dict]:
    """Extract all Bash commands + results that look like test runs."""
    events = []
    for line in raw.split("\n"):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    # Map tool_use_id -> command
    tool_cmds = {}
    for ev in events:
        if ev.get("type") != "assistant":
            continue
        for block in ev.get("message", {}).get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "Bash":
                cmd = block.get("input", {}).get("command", "")
                tid = block.get("id", "")
                if tid:
                    tool_cmds[tid] = cmd

    # Match results
    executions = []
    for ev in events:
        if ev.get("type") != "user":
            continue
        for block in ev.get("message", {}).get("content", []):
            if block.get("type") != "tool_result":
                continue
            tid = block.get("tool_use_id", "")
            if tid not in tool_cmds:
                continue

            cmd = tool_cmds[tid]
            # Is this a test command?
            cmd_lower = cmd.lower()
            is_test = any(p in cmd_lower for p in [
                "pytest", "unittest", "runtests", "manage.py test",
                "tox", "nox",
            ])
            if not is_test:
                continue

            content = block.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )

            is_error = block.get("is_error", False)
            passed, failed = _parse_counts(content)

            executions.append({
                "command": cmd,
                "output": content,
                "is_error": is_error,
                "passed": passed,
                "failed": failed,
            })

    return executions


def _parse_counts(output: str) -> tuple[int, int]:
    """Extract test pass/fail counts from various test framework outputs."""
    passed = failed = 0

    # pytest: "5 passed, 2 failed in 0.3s"
    m = re.search(r"(\d+)\s+passed", output)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+)\s+failed", output)
    if m:
        failed = int(m.group(1))

    # unittest: "Ran 5 tests ... OK" or "FAILED (failures=2)"
    if not passed and not failed:
        m = re.search(r"Ran\s+(\d+)\s+test", output)
        if m:
            total = int(m.group(1))
            if re.search(r"\bOK\b", output) and "FAILED" not in output:
                passed = total
            elif "FAILED" in output:
                m2 = re.search(r"failures=(\d+)", output)
                failed = int(m2.group(1)) if m2 else 1
                m3 = re.search(r"errors=(\d+)", output)
                errors = int(m3.group(1)) if m3 else 0
                failed += errors
                passed = max(0, total - failed)

    # sympy: "tests finished: 15 passed"
    m = re.search(r"tests finished:\s*(\d+)\s+passed", output)
    if m:
        passed = max(passed, int(m.group(1)))

    return passed, failed


def _extract_test_targets(val_cmd: str) -> list[str]:
    """Extract test identifiers from validation command for cross-referencing."""
    targets = []
    parts = val_cmd.split()
    for p in parts:
        if "::" in p:
            # pytest path::TestClass::test_func
            for segment in p.split("::")[1:]:
                targets.append(segment)
            # Also add the file
            targets.append(p.split("::")[0].split("/")[-1])
        elif ".py" in p:
            targets.append(p.split("/")[-1])
        elif p.startswith("test_") or p.startswith("Test"):
            targets.append(p)
    return targets


def validate_run(run: dict) -> dict:
    """Validate a single run by cross-referencing test output."""
    task_meta = load_task_meta(run["task_id"])
    val_cmd = task_meta.get("validation_command", "")
    val_targets = _extract_test_targets(val_cmd)

    executions = extract_test_executions(run["raw_stream_json"])

    if not executions:
        return {"verdict": "no_tests", "confidence": "none",
                "reason": "agent did not run any tests"}

    # Find the best execution: one that matches our validation targets
    best_match = None
    best_score = -1

    for ex in executions:
        score = 0
        for target in val_targets:
            if target in ex["command"] or target in ex["output"]:
                score += 1

        if score > best_score:
            best_score = score
            best_match = ex

    # If no target match, use the last execution
    if best_score == 0:
        best_match = executions[-1]

    ex = best_match
    target_match = best_score > 0 and val_targets

    # Determine verdict
    if ex["passed"] > 0 and ex["failed"] == 0 and not ex["is_error"]:
        verdict = "pass"
    elif ex["failed"] > 0:
        verdict = "fail"
    elif ex["is_error"]:
        if "ModuleNotFoundError" in ex["output"] or "ImportError" in ex["output"]:
            verdict = "env_error"
        else:
            verdict = "fail"
    else:
        verdict = "unclear"

    # Determine confidence based on how well agent's tests match our spec
    if verdict in ("pass", "fail") and target_match:
        confidence = "high"  # Agent ran OUR tests
    elif verdict in ("pass", "fail") and not target_match:
        confidence = "medium"  # Agent ran SOME tests, not necessarily ours
    else:
        confidence = "low"

    return {
        "verdict": verdict,
        "confidence": confidence,
        "passed": ex["passed"],
        "failed": ex["failed"],
        "target_match": target_match,
        "command": ex["command"][:120],
        "output_tail": ex["output"][-200:] if ex["output"] else "",
    }


def validate_all(dry_run: bool = False):
    db = get_db()

    runs = db.execute("""
        SELECT run_id, task_id, raw_stream_json, task_success, notes, validation_source
        FROM runs
        WHERE task_source = 'swe-bench-lite'
          AND raw_stream_json IS NOT NULL
          AND LENGTH(raw_stream_json) > 100
        ORDER BY created_at
    """).fetchall()

    print(f"Cross-referencing {len(runs)} runs against manifest test specs...\n")

    stats = {"high_pass": 0, "high_fail": 0, "medium_pass": 0, "medium_fail": 0,
             "env_error": 0, "no_tests": 0, "unclear": 0, "changed": 0,
             "docker_preserved": 0}

    for run in runs:
        # Never overwrite ANY existing validated label (docker, independent, etc.)
        if run["validation_source"]:
            stats["docker_preserved"] += 1
            v = "pass" if run["task_success"] == 1 else "fail"
            print(f"  [validated:{v:4}] {run['task_id']:40} (existing label preserved: {run['validation_source'][:30]})")
            continue

        result = validate_run(run)
        v = result["verdict"]
        c = result["confidence"]

        key = f"{c}_{v}" if v in ("pass", "fail") else v
        stats[key] = stats.get(key, 0) + 1

        new_success = None
        if v == "pass" and c == "high":
            new_success = 1
        elif v == "fail" and c == "high":
            new_success = 0
        elif v == "pass" and c == "medium":
            new_success = 1  # Provisionally accept
        elif v == "fail" and c == "medium":
            new_success = 0

        old = run["task_success"]
        changed = new_success is not None and new_success != old

        marker = " *CHANGED*" if changed else ""
        tmatch = "target" if result.get("target_match") else "other"
        print(f"  [{c:6} {v:9}] {run['task_id']:40} "
              f"p={result.get('passed', 0)} f={result.get('failed', 0)} "
              f"tests={tmatch}{marker}")

        if changed and not dry_run:
            db.execute(
                "UPDATE runs SET task_success = ?, notes = ? WHERE run_id = ?",
                (new_success, f"trace-xref: {v} (conf={c}, target={tmatch})", run["run_id"])
            )
            stats["changed"] += 1

    if not dry_run:
        db.commit()

    print(f"\n--- SUMMARY ---")
    print(f"  high-confidence pass:   {stats.get('high_pass', 0)}")
    print(f"  high-confidence fail:   {stats.get('high_fail', 0)}")
    print(f"  medium-confidence pass: {stats.get('medium_pass', 0)}")
    print(f"  medium-confidence fail: {stats.get('medium_fail', 0)}")
    print(f"  env_error:              {stats.get('env_error', 0)}")
    print(f"  no_tests:               {stats.get('no_tests', 0)}")
    print(f"  unclear:                {stats.get('unclear', 0)}")
    print(f"  docker preserved:       {stats['docker_preserved']}")
    print(f"  labels changed:         {stats['changed']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cross-referenced trace validation")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    validate_all(dry_run=args.dry_run)

"""
UGA Phase 1 — Extrospective Critic

Sends proposed edits to a SEPARATE Claude instance for evaluation.
The critic responds with APPROVE, CONCERN, or REJECT.

Uses `claude -p` (Claude Code CLI in pipe mode) to avoid needing API keys.
Responses are cached by (file_path, old_string, new_string) hash to avoid
redundant calls during P3 retroactive analysis.

Usage:
    from critic import CriticEvaluator
    critic = CriticEvaluator()
    verdict, explanation = critic.evaluate_edit(
        bug_description="...",
        file_path="models/fields.py",
        old_string="old code",
        new_string="new code",
        reasoning_text="agent reasoning",
    )
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("uga.critic")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Critic prompt template
# ---------------------------------------------------------------------------

CRITIC_PROMPT_TEMPLATE = """\
You are reviewing a code change proposed by a coding agent. The agent is fixing this bug:

{bug_description}

The agent proposes to edit {file_path}:

OLD (code being replaced):
```
{old_string}
```

NEW (replacement code):
```
{new_string}
```

The agent's reasoning before making this edit:
{reasoning_text}

Is this edit correct and well-targeted? Respond with EXACTLY one of these three formats:

APPROVE - the edit looks correct and well-targeted for the bug
CONCERN: [brief explanation] - the edit might have issues but could be okay
REJECT: [brief explanation] - the edit is likely wrong or poorly targeted

Respond with only one line in the format above. Do not add any other text."""


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def parse_critic_response(raw: str) -> tuple[str, str]:
    """Parse a critic response into (verdict, explanation).

    Expected formats:
        "APPROVE - the edit looks correct"
        "CONCERN: might break other tests"
        "REJECT: wrong file being edited"

    Returns:
        (verdict, explanation) where verdict is one of:
        "approve", "concern", "reject".
        Falls back to "approve" with explanation on parse failure (fail-open).
    """
    if not raw or not raw.strip():
        return "approve", "Empty critic response (fail-open)"

    text = raw.strip()

    # Try each format
    # APPROVE
    m = re.match(r'^APPROVE\s*[-:]?\s*(.*)', text, re.IGNORECASE | re.DOTALL)
    if m:
        return "approve", m.group(1).strip() or "Edit looks correct"

    # CONCERN
    m = re.match(r'^CONCERN\s*[:]\s*(.*)', text, re.IGNORECASE | re.DOTALL)
    if m:
        return "concern", m.group(1).strip() or "Unspecified concern"

    # REJECT
    m = re.match(r'^REJECT\s*[:]\s*(.*)', text, re.IGNORECASE | re.DOTALL)
    if m:
        return "reject", m.group(1).strip() or "Unspecified rejection"

    # Fallback: look for keywords anywhere in the response
    text_lower = text.lower()
    if "reject" in text_lower:
        return "reject", text[:200]
    if "concern" in text_lower:
        return "concern", text[:200]
    if "approve" in text_lower:
        return "approve", text[:200]

    # Total fallback: fail-open
    log.warning("Could not parse critic response, failing open: %s", text[:100])
    return "approve", f"Unparseable response (fail-open): {text[:200]}"


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class CriticCache:
    """Simple file-based cache for critic responses.

    Keyed by hash of (file_path, old_string, new_string).
    Saves to data/critic_cache.json.
    """

    def __init__(self, cache_path: Optional[Path] = None):
        self.cache_path = cache_path or (PROJECT_ROOT / "data" / "critic_cache.json")
        self._cache: dict[str, dict] = {}
        self._load()

    def _load(self):
        if self.cache_path.exists():
            try:
                with open(self.cache_path) as f:
                    self._cache = json.load(f)
                log.info("Loaded critic cache: %d entries", len(self._cache))
            except (json.JSONDecodeError, IOError):
                log.warning("Could not load critic cache, starting fresh")
                self._cache = {}

    def _save(self):
        os.makedirs(self.cache_path.parent, exist_ok=True)
        with open(self.cache_path, "w") as f:
            json.dump(self._cache, f, indent=2)

    @staticmethod
    def _key(file_path: str, old_string: str, new_string: str) -> str:
        h = hashlib.sha256()
        h.update(file_path.encode())
        h.update(old_string.encode())
        h.update(new_string.encode())
        return h.hexdigest()[:16]

    def get(self, file_path: str, old_string: str, new_string: str) -> Optional[dict]:
        key = self._key(file_path, old_string, new_string)
        return self._cache.get(key)

    def put(self, file_path: str, old_string: str, new_string: str,
            verdict: str, explanation: str, raw_response: str) -> None:
        key = self._key(file_path, old_string, new_string)
        self._cache[key] = {
            "verdict": verdict,
            "explanation": explanation,
            "raw_response": raw_response,
            "file_path": file_path,
            "cached_at": time.time(),
        }
        self._save()


# ---------------------------------------------------------------------------
# CriticEvaluator
# ---------------------------------------------------------------------------

class CriticEvaluator:
    """Evaluates proposed edits using a separate Claude instance.

    Calls `claude -p` with the critic prompt. Parses the response.
    Caches results to avoid redundant calls.
    """

    def __init__(
        self,
        model: str = "sonnet",
        timeout: int = 60,
        use_cache: bool = True,
        cache_path: Optional[Path] = None,
        dry_run: bool = False,
    ):
        self.model = model
        self.timeout = timeout
        self.use_cache = use_cache
        self.cache = CriticCache(cache_path) if use_cache else None
        self.dry_run = dry_run

    def evaluate_edit(
        self,
        bug_description: str,
        file_path: str,
        old_string: str,
        new_string: str,
        reasoning_text: str,
    ) -> tuple[str, str]:
        """Evaluate a proposed edit.

        Args:
            bug_description: The bug/task the agent is trying to fix.
            file_path: Path of the file being edited.
            old_string: Code being replaced (for Edit) or "" for Write.
            new_string: Replacement code (for Edit) or full content (for Write).
            reasoning_text: The agent's reasoning before the edit.

        Returns:
            (verdict, explanation) where verdict is "approve", "concern", or "reject".
        """
        # Check cache first
        if self.use_cache and self.cache:
            cached = self.cache.get(file_path, old_string, new_string)
            if cached:
                log.debug("Critic cache hit for %s", file_path)
                return cached["verdict"], cached["explanation"]

        # Build prompt
        # Truncate long strings to avoid overwhelming the critic
        max_code_len = 2000
        display_old = old_string[:max_code_len] + ("..." if len(old_string) > max_code_len else "")
        display_new = new_string[:max_code_len] + ("..." if len(new_string) > max_code_len else "")
        display_reasoning = reasoning_text[:3000] + ("..." if len(reasoning_text) > 3000 else "")

        prompt = CRITIC_PROMPT_TEMPLATE.format(
            bug_description=bug_description[:2000],
            file_path=file_path,
            old_string=display_old or "(new file)",
            new_string=display_new,
            reasoning_text=display_reasoning or "(no reasoning provided)",
        )

        if self.dry_run:
            log.info("DRY RUN critic for %s", file_path)
            return "approve", "Dry run (no actual critic call)"

        # Call claude -p
        raw_response = self._call_claude(prompt)
        verdict, explanation = parse_critic_response(raw_response)

        # Cache the result
        if self.use_cache and self.cache:
            self.cache.put(file_path, old_string, new_string,
                          verdict, explanation, raw_response)

        log.info("Critic verdict for %s: %s - %s", file_path, verdict, explanation[:100])
        return verdict, explanation

    def _call_claude(self, prompt: str) -> str:
        """Call claude -p and return the raw text response."""
        cmd = [
            "claude", "-p", prompt,
            "--model", self.model,
            "--output-format", "text",
        ]

        log.debug("Calling critic: claude -p --model %s", self.model)
        start = time.time()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            elapsed = time.time() - start
            log.debug("Critic responded in %.1fs (exit=%d)", elapsed, result.returncode)

            if result.returncode != 0:
                log.warning("Critic exited with code %d: %s",
                           result.returncode, result.stderr[:200])
                return ""

            return result.stdout.strip()

        except subprocess.TimeoutExpired:
            log.warning("Critic timed out after %ds", self.timeout)
            return ""
        except FileNotFoundError:
            log.error("claude CLI not found. Is Claude Code installed?")
            return ""
        except Exception as exc:
            log.error("Critic call failed: %s", exc)
            return ""


# ---------------------------------------------------------------------------
# Retroactive critic (P3 condition)
# ---------------------------------------------------------------------------

def run_retroactive_critic(
    db_path: Optional[str] = None,
    dry_run: bool = False,
) -> list[dict]:
    """Run critic retroactively on all Phase 0 Edit/Write calls.

    P3 condition: no new agent runs needed. For each Edit/Write in Phase 0
    data, extract the edit and reasoning, send to critic, record verdict.

    Returns list of dicts with results.
    """
    import sqlite3

    path = db_path or str(PROJECT_ROOT / "data" / "uga.db")
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row

    critic = CriticEvaluator(dry_run=dry_run)

    # Get all Edit/Write calls from Phase 0 with reasoning
    rows = db.execute("""
        SELECT tc.decision_id, tc.run_id, tc.tool_name,
               tc.tool_params_json, tc.reasoning_text,
               tc.sequence_number,
               r.task_id, r.task_success
        FROM tool_calls tc
        JOIN runs r ON tc.run_id = r.run_id
        WHERE tc.tool_name IN ('Edit', 'Write')
          AND r.validation_source IS NOT NULL
          AND r.task_success IS NOT NULL
        ORDER BY tc.run_id, tc.sequence_number
    """).fetchall()

    log.info("P3: evaluating %d Edit/Write calls retroactively", len(rows))

    # We need bug descriptions. Get them from the manifest or task prompts.
    # For now, use task_id as a proxy (the actual prompt is in the manifest).
    task_descriptions = _load_task_descriptions()

    results = []
    for i, row in enumerate(rows):
        task_id = row["task_id"]
        bug_desc = task_descriptions.get(task_id, f"Bug in {task_id}")

        params = json.loads(row["tool_params_json"]) if row["tool_params_json"] else {}
        file_path = params.get("file_path", "unknown")
        old_string = params.get("old_string", "")
        new_string = params.get("new_string", params.get("content", ""))
        reasoning = row["reasoning_text"] or ""

        verdict, explanation = critic.evaluate_edit(
            bug_description=bug_desc,
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            reasoning_text=reasoning,
        )

        result = {
            "decision_id": row["decision_id"],
            "run_id": row["run_id"],
            "task_id": task_id,
            "task_success": row["task_success"],
            "tool_name": row["tool_name"],
            "file_path": file_path,
            "sequence_number": row["sequence_number"],
            "critic_verdict": verdict,
            "critic_explanation": explanation,
        }
        results.append(result)

        if (i + 1) % 50 == 0:
            log.info("P3 progress: %d/%d calls evaluated", i + 1, len(rows))

    db.close()

    # Summary
    verdicts = {}
    for r in results:
        v = r["critic_verdict"]
        verdicts[v] = verdicts.get(v, 0) + 1
    log.info("P3 complete: %d calls. Verdicts: %s", len(results), verdicts)

    return results


def _load_task_descriptions() -> dict[str, str]:
    """Load task descriptions from manifests for critic context."""
    import yaml

    descriptions = {}
    manifest_paths = [
        PROJECT_ROOT / "tasks" / "manifest.yaml",
        PROJECT_ROOT / "tasks" / "wave_expansion.yaml",
    ]
    for mp in manifest_paths:
        if mp.exists():
            try:
                with open(mp) as f:
                    data = yaml.safe_load(f)
                for task in data.get("tasks", []):
                    descriptions[task["task_id"]] = task.get("prompt", task["task_id"])
            except Exception:
                pass
    return descriptions


# ---------------------------------------------------------------------------
# P3 Analysis: does critic agreement predict success?
# ---------------------------------------------------------------------------

def analyze_retroactive_critic(results: list[dict]) -> dict:
    """Analyze P3 results: does critic verdict predict task success?

    Computes:
    - Approval rate for passing vs failing runs
    - Per-call precision/recall of critic REJECT as predictor of failure
    - Agreement statistics
    """
    if not results:
        return {"error": "No results to analyze"}

    # Per-call analysis
    tp = fp = tn = fn = 0
    for r in results:
        success = r["task_success"]
        rejected = r["critic_verdict"] == "reject"

        if rejected and not success:
            tp += 1  # Correctly rejected a failing edit
        elif rejected and success:
            fp += 1  # Wrongly rejected a passing edit
        elif not rejected and not success:
            fn += 1  # Missed a failing edit
        else:
            tn += 1  # Correctly approved a passing edit

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    # Verdict distribution by outcome
    from collections import defaultdict
    pass_verdicts = defaultdict(int)
    fail_verdicts = defaultdict(int)
    for r in results:
        if r["task_success"]:
            pass_verdicts[r["critic_verdict"]] += 1
        else:
            fail_verdicts[r["critic_verdict"]] += 1

    return {
        "total_calls": len(results),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "pass_verdicts": dict(pass_verdicts),
        "fail_verdicts": dict(fail_verdicts),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="UGA Critic — Extrospective Edit Evaluator")
    parser.add_argument("command", choices=["retroactive", "analyze", "test"],
                        help="retroactive: run P3. analyze: analyze P3 results. test: single test call.")
    parser.add_argument("--dry-run", action="store_true", help="Don't call Claude, return dummy verdicts")
    parser.add_argument("--db", type=str, default=None, help="Database path override")
    args = parser.parse_args()

    if args.command == "retroactive":
        results = run_retroactive_critic(db_path=args.db, dry_run=args.dry_run)
        # Save results
        out_path = PROJECT_ROOT / "data" / "p3_retroactive_results.json"
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Saved {len(results)} results to {out_path}")

    elif args.command == "analyze":
        results_path = PROJECT_ROOT / "data" / "p3_retroactive_results.json"
        if not results_path.exists():
            print("Run 'retroactive' first to generate results.")
            exit(1)
        with open(results_path) as f:
            results = json.load(f)
        analysis = analyze_retroactive_critic(results)
        print(json.dumps(analysis, indent=2))

    elif args.command == "test":
        critic = CriticEvaluator(dry_run=args.dry_run)
        verdict, explanation = critic.evaluate_edit(
            bug_description="QuerySet.only() doesn't clear deferred fields",
            file_path="django/db/models/sql/query.py",
            old_string="def add_deferred_loading(self, field_names):",
            new_string="def add_deferred_loading(self, field_names):\n    self.deferred_loading = (frozenset(field_names), True)",
            reasoning_text="The issue is in the add_deferred_loading method of query.py. We need to clear existing deferred fields.",
        )
        print(f"Verdict: {verdict}")
        print(f"Explanation: {explanation}")

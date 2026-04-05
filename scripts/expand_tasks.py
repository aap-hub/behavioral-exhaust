#!/usr/bin/env python3
"""
Expand the task manifest with 55 new SWE-bench Lite tasks.
Produces tasks/wave_expansion.yaml and clones repos.
"""

import json
import os
import subprocess
import sys
import yaml
from pathlib import Path
from datasets import load_dataset

ROOT = Path(__file__).resolve().parent.parent
REPOS_DIR = ROOT / "tasks" / "repos"
MANIFEST_PATH = ROOT / "tasks" / "manifest.yaml"
OUTPUT_PATH = ROOT / "tasks" / "wave_expansion.yaml"

# Target repos (well-known, likely to clone+checkout cleanly)
TARGET_REPOS = {
    "pytest-dev/pytest",
    "sympy/sympy",
    "django/django",
    "scikit-learn/scikit-learn",
    "matplotlib/matplotlib",
    "pallets/flask",
    "psf/requests",
    "astropy/astropy",
    "pydata/xarray",
    "mwaskom/seaborn",
    "pylint-dev/pylint",
    "sphinx-doc/sphinx",
}

def get_existing_task_ids():
    with open(MANIFEST_PATH) as f:
        data = yaml.safe_load(f)
    return {t["task_id"] for t in data["tasks"]}

def parse_fail_to_pass(fail_to_pass_str):
    """Parse the FAIL_TO_PASS field into a validation command."""
    try:
        tests = json.loads(fail_to_pass_str)
    except (json.JSONDecodeError, TypeError):
        tests = [fail_to_pass_str]

    if not tests:
        return None

    # Build pytest command from test identifiers
    # Limit to first 3 tests to keep command manageable
    test_args = tests[:3]
    cmd = "python -m pytest " + " ".join(test_args) + " -x"
    return cmd

def build_prompt(problem_statement):
    """Build the task prompt from the problem statement."""
    prefix = (
        "Fix the following issue in this repository. First, set up the environment: "
        "run `pip install -e .` or `pip install -e \".[testing]\"` to install dependencies. "
        "Then find and fix the bug. Run the relevant tests to verify your fix.\n\n"
        "Fix the following issue:\n\n"
    )
    return prefix + problem_statement.strip()

def clone_repo(task_id, repo, base_commit, existing_clones):
    """Clone and checkout the repo for a task. Use --reference if we have a local clone."""
    dest = REPOS_DIR / task_id
    if dest.exists():
        print(f"  [skip] {task_id} already exists")
        return True

    repo_prefix = repo.replace("/", "__").split("__")[0] + "__" + repo.replace("/", "__").split("__")[1]

    # Find a reference repo (any existing clone of the same GitHub repo)
    reference = None
    for existing in existing_clones:
        existing_prefix = "__".join(existing.split("__")[:2])
        if existing_prefix == repo_prefix:
            ref_path = REPOS_DIR / existing
            if (ref_path / ".git").exists():
                reference = ref_path
                break

    github_url = f"https://github.com/{repo}.git"

    try:
        if reference:
            print(f"  [clone --reference] {task_id} from {reference.name}")
            subprocess.run(
                ["git", "clone", "--reference", str(reference), github_url, str(dest)],
                capture_output=True, text=True, timeout=300, check=True
            )
        else:
            print(f"  [clone fresh] {task_id}")
            subprocess.run(
                ["git", "clone", github_url, str(dest)],
                capture_output=True, text=True, timeout=600, check=True
            )

        # Checkout the base commit
        subprocess.run(
            ["git", "checkout", base_commit],
            capture_output=True, text=True, timeout=120, check=True,
            cwd=str(dest)
        )
        print(f"  [ok] {task_id} @ {base_commit[:10]}")
        return True

    except subprocess.CalledProcessError as e:
        print(f"  [FAIL] {task_id}: {e.stderr[:200] if e.stderr else e}")
        # Clean up failed clone
        if dest.exists():
            subprocess.run(["rm", "-rf", str(dest)], capture_output=True)
        return False
    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT] {task_id}")
        if dest.exists():
            subprocess.run(["rm", "-rf", str(dest)], capture_output=True)
        return False

def main():
    print("Loading SWE-bench Lite dataset...")
    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    print(f"  Total: {len(ds)} tasks")

    existing_ids = get_existing_task_ids()
    print(f"  Existing in manifest: {len(existing_ids)}")

    # Filter to target repos, exclude existing
    candidates = []
    for item in ds:
        task_id = item["instance_id"]
        if task_id in existing_ids:
            continue
        if item["repo"] not in TARGET_REPOS:
            continue

        validation_cmd = parse_fail_to_pass(item["FAIL_TO_PASS"])
        if not validation_cmd:
            continue

        candidates.append({
            "task_id": task_id,
            "repo": item["repo"],
            "base_commit": item["base_commit"],
            "problem_statement": item["problem_statement"],
            "validation_command": validation_cmd,
            "prompt_len": len(item["problem_statement"]),
        })

    print(f"  Candidates after filtering: {len(candidates)}")

    # Sort by problem statement length (shorter = likely easier), then pick 55
    candidates.sort(key=lambda x: x["prompt_len"])
    selected = candidates[:55]

    print(f"  Selected: {len(selected)} tasks")
    print(f"  Repos represented:")
    from collections import Counter
    repo_counts = Counter(c["repo"] for c in selected)
    for repo, count in repo_counts.most_common():
        print(f"    {repo}: {count}")

    # Get existing clones for --reference
    existing_clones = [d for d in os.listdir(REPOS_DIR) if (REPOS_DIR / d / ".git").exists()]
    print(f"\nExisting local clones: {len(existing_clones)}")

    # Clone repos
    print(f"\nCloning {len(selected)} repos...")
    successful = []
    failed = []
    for i, task in enumerate(selected):
        print(f"\n[{i+1}/{len(selected)}] {task['task_id']}")
        ok = clone_repo(task["task_id"], task["repo"], task["base_commit"], existing_clones)
        if ok:
            successful.append(task)
            # Add to existing_clones so subsequent clones can reference
            existing_clones.append(task["task_id"])
        else:
            failed.append(task["task_id"])

    print(f"\n\nClone results: {len(successful)} succeeded, {len(failed)} failed")
    if failed:
        print(f"  Failed: {failed}")

    # Write the YAML
    tasks_yaml = []
    for task in successful:
        entry = {
            "task_id": task["task_id"],
            "phase": 0,
            "type": "bugfix",
            "language": "python",
            "source": "swe-bench-lite",
            "repo": f"tasks/repos/{task['task_id']}",
            "prompt": build_prompt(task["problem_statement"]),
            "validation_command": task["validation_command"],
            "expected_min_calls": 5,
        }
        tasks_yaml.append(entry)

    output = {"tasks": tasks_yaml}
    with open(OUTPUT_PATH, "w") as f:
        yaml.dump(output, f, default_flow_style=False, allow_unicode=True, width=120, sort_keys=False)

    print(f"\nWrote {len(tasks_yaml)} tasks to {OUTPUT_PATH}")
    print("Done!")

if __name__ == "__main__":
    main()

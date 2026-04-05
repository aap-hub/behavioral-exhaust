"""
Validate UGA runs using the official SWE-bench Docker-based evaluation harness.

Extracts agent patches from the SQLite database, formats them for SWE-bench,
and runs the official evaluation with proper Python environments.

Usage:
    python src/swebench_validate.py              # Extract patches for all SWE-bench runs
    python src/swebench_validate.py --eval       # Extract + run SWE-bench eval
"""

import json
import logging
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "uga.db"


def extract_patch_from_stream(raw_stream: str, task_repo_path: str) -> str:
    """Extract the agent's changes as a unified diff patch from the raw stream.

    We replay the Write/Edit operations to construct what the agent changed,
    then generate a diff against the original files.
    """
    edits = []
    for line in raw_stream.split('\n'):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            if event.get('type') != 'assistant':
                continue
            for block in event.get('message', {}).get('content', []):
                if block.get('type') != 'tool_use':
                    continue
                name = block.get('name', '')
                inp = block.get('input', {})
                if name in ('Write', 'Edit'):
                    edits.append({
                        'type': name.lower(),
                        'file_path': inp.get('file_path', ''),
                        'content': inp.get('content', ''),
                        'old_string': inp.get('old_string', ''),
                        'new_string': inp.get('new_string', ''),
                    })
        except json.JSONDecodeError:
            continue

    if not edits:
        return ""

    # Determine workspace prefix from the first edit path
    workspace_prefix = None
    for e in edits:
        fp = e['file_path']
        if 'uga_workspace_' in fp:
            idx = fp.index('uga_workspace_')
            # Find the end of the workspace dir name
            rest = fp[idx:]
            parts = rest.split('/')
            if len(parts) >= 2:
                workspace_prefix = fp[:idx] + parts[0] + '/'
            break

    # Build a dict of file modifications
    file_changes = {}  # relative_path -> list of (old, new) for edits or full content for writes

    for e in edits:
        fp = e['file_path']
        # Convert to relative path
        if workspace_prefix and fp.startswith(workspace_prefix):
            rel = fp[len(workspace_prefix):]
        else:
            rel = fp

        if rel not in file_changes:
            file_changes[rel] = {'original': None, 'edits': []}

        if e['type'] == 'write':
            file_changes[rel]['full_write'] = e['content']
        elif e['type'] == 'edit':
            file_changes[rel]['edits'].append((e['old_string'], e['new_string']))

    # Codex #I note: edits list preserves chronological order from the stream,
    # and we process writes before edits per file below.

    # Generate unified diff by applying changes to original files
    patches = []
    repo_path = Path(task_repo_path)

    for rel_path, changes in file_changes.items():
        original_file = repo_path / rel_path

        if 'full_write' in changes:
            # Full file write — diff against original or empty
            if original_file.exists():
                original = original_file.read_text()
            else:
                original = ""
            modified = changes['full_write']
            # Codex #I: Apply edits AFTER write (don't ignore them)
            if changes['edits']:
                for old, new in changes['edits']:
                    if old in modified:
                        modified = modified.replace(old, new, 1)
                    else:
                        logger.warning(
                            "Edit old_string not found in %s after write (skipping): %s",
                            rel_path, old[:80]
                        )
        elif changes['edits']:
            if not original_file.exists():
                continue
            modified = original_file.read_text()
            for old, new in changes['edits']:
                if old in modified:
                    modified = modified.replace(old, new, 1)
                else:
                    # Codex #I: Log warning instead of silently skipping
                    logger.warning(
                        "Edit old_string not found in %s (skipping): %s",
                        rel_path, old[:80]
                    )
            original = original_file.read_text()
        else:
            continue

        # Skip test files — SWE-bench only evaluates source changes
        if '/test' in rel_path or 'test_' in rel_path.split('/')[-1]:
            continue

        # Generate unified diff
        with tempfile.NamedTemporaryFile(mode='w', suffix='.orig', delete=False) as f_orig:
            f_orig.write(original)
            orig_path = f_orig.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mod', delete=False) as f_mod:
            f_mod.write(modified)
            mod_path = f_mod.name

        try:
            result = subprocess.run(
                ['diff', '-u', orig_path, mod_path],
                capture_output=True, text=True
            )
            if result.stdout:
                # Replace temp file names with proper paths
                patch = result.stdout
                patch = patch.replace(orig_path, f'a/{rel_path}')
                patch = patch.replace(mod_path, f'b/{rel_path}')
                patches.append(patch)
        finally:
            os.unlink(orig_path)
            os.unlink(mod_path)

    return '\n'.join(patches)


def create_predictions_file(db_path: str = None) -> tuple[str, list[str], dict]:
    """Create a SWE-bench predictions JSONL file from our database.

    Returns (predictions_path, list_of_instance_ids, task_id_to_run_id_map).
    Issue #17 fix: tracks which run_id was used per task so we update the
    correct run in update_db_from_results.
    """
    db = sqlite3.connect(str(db_path or DB_PATH))
    db.row_factory = sqlite3.Row

    runs = db.execute('''
        SELECT run_id, task_id, raw_stream_json, created_at
        FROM runs WHERE model_version='sonnet' AND task_source='swe-bench-lite'
        ORDER BY created_at
    ''').fetchall()

    # Deduplicate: take the latest run per task
    latest = {}
    for run in runs:
        latest[run['task_id']] = run

    predictions = []
    instance_ids = []
    task_to_run = {}  # task_id -> run_id that was evaluated

    for task_id, run in latest.items():
        repo_path = str(PROJECT_ROOT / 'tasks' / 'repos' / task_id)
        patch = extract_patch_from_stream(run['raw_stream_json'], repo_path)

        if not patch:
            print(f"  WARNING: No source patch extracted for {task_id}")
            continue

        predictions.append({
            'instance_id': task_id,
            'model_name_or_path': 'uga-sonnet-4.6',
            'model_patch': patch,
        })
        instance_ids.append(task_id)
        task_to_run[task_id] = run['run_id']

    # Write predictions file
    pred_path = str(PROJECT_ROOT / 'data' / 'predictions.jsonl')
    with open(pred_path, 'w') as f:
        for pred in predictions:
            f.write(json.dumps(pred) + '\n')

    # Also save the run_id mapping for later use
    map_path = str(PROJECT_ROOT / 'data' / 'prediction_run_map.json')
    with open(map_path, 'w') as f:
        json.dump(task_to_run, f, indent=2)

    print(f"Created {pred_path} with {len(predictions)} predictions")
    return pred_path, instance_ids, task_to_run


def run_swebench_eval(predictions_path: str, instance_ids: list[str]):
    """Run the official SWE-bench evaluation."""
    from swebench.harness.run_evaluation import main as run_eval

    print(f"\nRunning SWE-bench evaluation on {len(instance_ids)} instances...")
    print("This will build Docker containers (may take a while on first run).\n")

    run_eval(
        dataset_name='princeton-nlp/SWE-bench_Lite',
        split='test',
        instance_ids=instance_ids,
        predictions_path=predictions_path,
        max_workers=2,
        force_rebuild=False,
        cache_level='env',
        clean=False,
        open_file_limit=4096,
        run_id='uga-phase0',
        timeout=300,
        namespace=None,
        rewrite_reports=False,
        modal=False,
    )


def update_db_from_results(db_path: str = None, task_to_run: dict = None):
    """Parse SWE-bench evaluation results and update the database.

    Issue #17 fix: updates specific run_id, not all runs for a task_id.
    """
    report_dir = PROJECT_ROOT / 'data'
    results_file = report_dir / 'uga-phase0.json'

    if not results_file.exists():
        for candidate in report_dir.glob('**/uga-phase0*.json'):
            results_file = candidate
            break

    if not results_file.exists():
        print("No results file found. Check SWE-bench output directory.")
        return

    with open(results_file) as f:
        results = json.load(f)

    # Load run_id mapping if not provided
    if task_to_run is None:
        map_path = PROJECT_ROOT / 'data' / 'prediction_run_map.json'
        if map_path.exists():
            with open(map_path) as f:
                task_to_run = json.load(f)
        else:
            task_to_run = {}

    db = sqlite3.connect(str(db_path or DB_PATH))

    resolved = set(results.get('resolved', []))
    all_evaluated = set(results.get('resolved', [])) | set(results.get('unresolved', []))
    print(f"\nSWE-bench results: {len(resolved)} resolved, {len(all_evaluated)} total evaluated")

    for iid in all_evaluated:
        is_resolved = iid in resolved
        label = "RESOLVED" if is_resolved else "UNRESOLVED"

        if iid in task_to_run:
            # Update the specific run that was evaluated
            db.execute(
                "UPDATE runs SET task_success=?, notes=? WHERE run_id=?",
                (1 if is_resolved else 0, f"swebench-validated: {label}", task_to_run[iid])
            )
        else:
            # Fallback: update latest sonnet run (matches old behavior but logged)
            print(f"  WARNING: No run_id mapping for {iid}, updating latest run")
            db.execute(
                "UPDATE runs SET task_success=?, notes=? "
                "WHERE run_id = (SELECT run_id FROM runs WHERE task_id=? "
                "AND model_version='sonnet' ORDER BY created_at DESC LIMIT 1)",
                (1 if is_resolved else 0, f"swebench-validated: {label}", iid)
            )
        print(f"  {label}: {iid}")

    db.commit()


if __name__ == '__main__':
    import sys

    pred_path, instance_ids, task_to_run = create_predictions_file()

    print(f"\nPatches extracted for {len(instance_ids)} tasks.")
    print("Run: python src/swebench_validate.py --eval to run SWE-bench evaluation")

    if '--eval' in sys.argv:
        run_swebench_eval(pred_path, instance_ids)
        update_db_from_results(task_to_run=task_to_run)

#!/bin/bash
# Clone repos for wave expansion tasks
# Uses --reference to speed up clones by sharing git objects
set -euo pipefail

REPOS_DIR="/Users/al/projects/uga-harness/tasks/repos"
TASKS_JSON="/tmp/uga_expansion_tasks.json"

# Reference repos (one per GitHub org/repo)
REFS=(
    "django__django:/Users/al/projects/uga-harness/tasks/repos/django__django-14999"
    "sympy__sympy:/Users/al/projects/uga-harness/tasks/repos/sympy__sympy-13437"
    "psf__requests:/Users/al/projects/uga-harness/tasks/repos/psf__requests-2317"
    "pytest-dev__pytest:/Users/al/projects/uga-harness/tasks/repos/pytest-dev__pytest-5221"
    "pylint-dev__pylint:/Users/al/projects/uga-harness/tasks/repos/pylint-dev__pylint-6506"
    "pallets__flask:/Users/al/projects/uga-harness/tasks/repos/pallets__flask-4045"
)

get_reference() {
    local task_id="$1"
    # Extract repo prefix (e.g., django__django from django__django-14999)
    local prefix=$(echo "$task_id" | sed 's/-[0-9]*$//')
    for ref in "${REFS[@]}"; do
        local ref_prefix="${ref%%:*}"
        local ref_path="${ref##*:}"
        if [ "$prefix" = "$ref_prefix" ] && [ -d "$ref_path/.git" ]; then
            echo "$ref_path"
            return
        fi
    done
}

# Read tasks from JSON and clone each
python3 -c "
import json
with open('$TASKS_JSON') as f:
    tasks = json.load(f)
for t in tasks:
    repo_url = 'https://github.com/' + t['repo'] + '.git'
    print(f\"{t['task_id']}|{repo_url}|{t['base_commit']}\")
" | while IFS='|' read -r task_id repo_url base_commit; do
    dest="$REPOS_DIR/$task_id"

    if [ -d "$dest" ]; then
        echo "[skip] $task_id already exists"
        continue
    fi

    ref=$(get_reference "$task_id")

    if [ -n "$ref" ]; then
        echo "[clone --reference] $task_id (ref: $(basename $ref))"
        if ! git clone --reference "$ref" "$repo_url" "$dest" 2>/dev/null; then
            echo "[FAIL clone] $task_id"
            rm -rf "$dest"
            continue
        fi
    else
        echo "[clone fresh] $task_id"
        if ! git clone "$repo_url" "$dest" 2>/dev/null; then
            echo "[FAIL clone] $task_id"
            rm -rf "$dest"
            continue
        fi
    fi

    # Checkout base commit
    if ! (cd "$dest" && git checkout "$base_commit" 2>/dev/null); then
        echo "[FAIL checkout] $task_id @ ${base_commit:0:10}"
        rm -rf "$dest"
        continue
    fi

    echo "[ok] $task_id @ ${base_commit:0:10}"
done

echo ""
echo "Done cloning."

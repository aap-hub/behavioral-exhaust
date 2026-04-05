#!/bin/bash
# Lightweight SWE-bench task validation.
# Expects:
#   /repo — the task repo (mounted read-only)
#   /patch.diff — the agent's patch (mounted read-only)
#   $1 — the test command (e.g., "pytest testing/test_tmpdir.py::test_foo -x")

# Codex #13 fix: copy repo to writable /app so git apply works
# (source mount is :ro to protect host filesystem)
cp -a /repo /app
cd /app

# Apply the agent's patch
if [ -f /patch.diff ] && [ -s /patch.diff ]; then
    git apply /patch.diff 2>/dev/null || patch -p1 < /patch.diff 2>/dev/null || {
        echo "PATCH_APPLY_FAILED"
        exit 1
    }
    echo "PATCH_APPLIED"
else
    echo "NO_PATCH"
    exit 1
fi

# Install the repo
pip install -e . --quiet 2>/dev/null || pip install -e ".[testing]" --quiet 2>/dev/null || {
    echo "INSTALL_FAILED"
    export PYTHONPATH=/app/src:/app
}

# Run the test
if [ -z "$1" ]; then
    echo "NO_TEST_COMMAND"
    exit 1
fi

echo "RUNNING_TESTS: $1"
eval "$1"
TEST_EXIT=$?

if [ $TEST_EXIT -eq 0 ]; then
    echo "TESTS_PASSED"
else
    echo "TESTS_FAILED (exit=$TEST_EXIT)"
fi

exit $TEST_EXIT

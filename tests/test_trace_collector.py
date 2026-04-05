"""
Tests for src/trace_collector.py — critical-path coverage.

Covers:
  - classify_state_modifying for compound commands, pipes, redirections
  - _read_events counts dropped lines correctly
"""

from __future__ import annotations

import io
import pathlib
import sys
import warnings

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from trace_collector import classify_state_modifying, _read_events


# ===================================================================
# classify_state_modifying — compound commands
# ===================================================================

class TestCompoundCommands:
    """Compound commands (&&, ||, ;) are state-modifying if ANY segment is."""

    def test_two_readonly_segments(self):
        # ls && cat foo.py — both read-only
        assert classify_state_modifying("Bash", {"command": "ls && cat foo.py"}) is False

    def test_readonly_then_write(self):
        # ls && rm foo — rm is state-modifying
        assert classify_state_modifying("Bash", {"command": "ls && rm foo"}) is True

    def test_write_then_readonly(self):
        # touch newfile && ls — touch is state-modifying
        assert classify_state_modifying("Bash", {"command": "touch newfile && ls"}) is True

    def test_semicolon_compound(self):
        # cat foo; echo bar — both read-only
        assert classify_state_modifying("Bash", {"command": "cat foo; echo bar"}) is False

    def test_semicolon_with_write(self):
        # cat foo; rm bar — rm is state-modifying
        assert classify_state_modifying("Bash", {"command": "cat foo; rm bar"}) is True

    def test_or_compound(self):
        # ls || mkdir fallback — mkdir is state-modifying
        assert classify_state_modifying("Bash", {"command": "ls || mkdir fallback"}) is True

    def test_three_segments_all_readonly(self):
        assert classify_state_modifying("Bash", {"command": "echo hi && ls && pwd"}) is False


# ===================================================================
# classify_state_modifying — pipes
# ===================================================================

class TestPipeCommands:
    """Piped commands: all segments must be read-only for the pipeline to be read-only."""

    def test_readonly_pipe(self):
        # cat foo | grep bar — both read-only
        assert classify_state_modifying("Bash", {"command": "cat foo | grep bar"}) is False

    def test_pipe_to_tee(self):
        # echo hi | tee out.txt — tee writes
        assert classify_state_modifying("Bash", {"command": "echo hi | tee out.txt"}) is True

    def test_pipe_to_xargs(self):
        # find . | xargs rm — xargs is a pipe mutator
        assert classify_state_modifying("Bash", {"command": "find . | xargs rm"}) is True

    def test_long_readonly_pipe(self):
        assert classify_state_modifying("Bash", {"command": "cat foo | sort | uniq | wc -l"}) is False


# ===================================================================
# classify_state_modifying — redirections
# ===================================================================

class TestRedirectionCommands:

    def test_stdout_redirect(self):
        # echo foo > out.txt — writes to file
        assert classify_state_modifying("Bash", {"command": "echo foo > out.txt"}) is True

    def test_append_redirect(self):
        # echo foo >> out.txt — writes to file
        assert classify_state_modifying("Bash", {"command": "echo foo >> out.txt"}) is True

    def test_sed_inplace(self):
        # sed -i is state-modifying
        assert classify_state_modifying("Bash", {"command": "sed -i 's/old/new/' file.py"}) is True

    def test_sed_readonly(self):
        # plain sed is read-only
        assert classify_state_modifying("Bash", {"command": "sed 's/old/new/' file.py"}) is False

    def test_find_delete(self):
        assert classify_state_modifying("Bash", {"command": "find . -name '*.pyc' -delete"}) is True

    def test_find_readonly(self):
        assert classify_state_modifying("Bash", {"command": "find . -name '*.py'"}) is False


# ===================================================================
# _read_events — dropped line counting
# ===================================================================

class TestReadEvents:
    """_read_events should count and warn about dropped malformed lines."""

    def test_valid_json_lines(self):
        data = '{"type":"system"}\n{"type":"assistant"}\n'
        events = _read_events(io.StringIO(data))
        assert len(events) == 2

    def test_blank_lines_skipped_silently(self):
        data = '{"type":"system"}\n\n\n{"type":"assistant"}\n'
        events = _read_events(io.StringIO(data))
        assert len(events) == 2

    def test_malformed_lines_dropped_with_warning(self):
        data = '{"type":"system"}\nnot json\n{"type":"assistant"}\n'
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            events = _read_events(io.StringIO(data))
            assert len(events) == 2
            # Should have at least one warning about malformed JSON
            json_warnings = [x for x in w if "malformed JSON" in str(x.message).lower()
                             or "Dropped" in str(x.message)]
            assert len(json_warnings) >= 1

    def test_multiple_malformed_lines_summary_warning(self):
        data = '{"type":"ok"}\nbad1\nbad2\nbad3\n'
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            events = _read_events(io.StringIO(data))
            assert len(events) == 1
            # Should have a summary warning mentioning "3" dropped lines
            summary_warnings = [x for x in w if "Dropped 3" in str(x.message)]
            assert len(summary_warnings) == 1

    def test_all_malformed(self):
        data = 'not json\nalso bad\n'
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            events = _read_events(io.StringIO(data))
            assert len(events) == 0
            summary_warnings = [x for x in w if "Dropped 2" in str(x.message)]
            assert len(summary_warnings) == 1

    def test_empty_input(self):
        events = _read_events(io.StringIO(""))
        assert len(events) == 0

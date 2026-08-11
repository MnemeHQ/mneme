"""Tests for introduced-delta enforcement (issue #259).

The hook used to check the entire materialized file. That meant a violation
already sitting in a file blocked *every* subsequent edit to it, including
edits that touched a different function, edits that changed nothing relevant,
and the remediation edit itself. On any existing repository, installing Mneme
turned pre-existing debt into an immediate wall.

Enforcement at an edit gate is a question about the change, not about the file:
"does this edit introduce a violation?" Auditing a repository is the other
question, and `mneme check --input <file>` still answers that one over whole
files. See ADR-018.

"Introduced" is defined uniformly as the added lines of a diff between the
file's current content and the content the tool is about to write. A brand-new
file diffs against nothing, so all of it is introduced.
"""
import io
import json
import shutil
from pathlib import Path

import pytest

from mneme.integrations.claude_code.hook import (
    ToolEvent,
    introduced_content,
    main,
)

FIXTURE = Path(__file__).parent / "fixtures" / "project_memory.json"

VIOLATION = "import psycopg2"
CLEAN = "import sqlite3"


def _event(tool_name, tool_input, cwd="."):
    return ToolEvent(
        tool_name=tool_name,
        file_path=tool_input.get("file_path", ""),
        cwd=str(cwd),
        tool_input=tool_input,
    )


# ── introduced_content unit behaviour ────────────────────────────────────────

def test_new_file_write_introduces_everything(tmp_path):
    target = tmp_path / "brand_new.py"
    got = introduced_content(
        _event("Write", {"file_path": str(target), "content": f"{VIOLATION}\n"})
    )
    assert VIOLATION in got


def test_non_utf8_write_target_is_checked_as_new_content(tmp_path):
    target = tmp_path / "binary.py"
    target.write_bytes(b"\xff\xfe")

    got = introduced_content(
        _event("Write", {"file_path": str(target), "content": f"{VIOLATION}\n"})
    )
    assert VIOLATION in got


def test_unchanged_line_is_not_introduced(tmp_path):
    """The core fix: a pre-existing violation is not this edit's problem."""
    target = tmp_path / "legacy.py"
    target.write_text(f"{VIOLATION}\ndef handler():\n    pass\n", encoding="utf-8")

    got = introduced_content(_event("Edit", {
        "file_path": str(target),
        "old_string": "    pass",
        "new_string": "    return 1",
    }))
    assert "return 1" in got
    assert VIOLATION not in got, (
        "a violation that was already in the file must not be attributed to an "
        "unrelated edit"
    )


def test_newly_added_line_is_introduced(tmp_path):
    target = tmp_path / "svc.py"
    target.write_text("def handler():\n    pass\n", encoding="utf-8")

    got = introduced_content(_event("Edit", {
        "file_path": str(target),
        "old_string": "    pass",
        "new_string": f"    {VIOLATION}",
    }))
    assert VIOLATION in got


def test_removing_a_violation_introduces_nothing(tmp_path):
    """Remediation must never be blocked by the thing it removes."""
    target = tmp_path / "svc.py"
    target.write_text(f"{VIOLATION}\n", encoding="utf-8")

    got = introduced_content(_event("Edit", {
        "file_path": str(target),
        "old_string": VIOLATION,
        "new_string": CLEAN,
    }))
    assert VIOLATION not in got
    assert CLEAN in got


def test_pure_deletion_introduces_nothing(tmp_path):
    target = tmp_path / "svc.py"
    target.write_text(f"{VIOLATION}\n", encoding="utf-8")

    got = introduced_content(_event("Edit", {
        "file_path": str(target),
        "old_string": f"{VIOLATION}\n",
        "new_string": "",
    }))
    assert got == ""


def test_nonblank_whitespace_replacement_is_still_introduced(tmp_path):
    target = tmp_path / "svc.py"
    target.write_text("value = 1\n", encoding="utf-8")

    got = introduced_content(_event("Edit", {
        "file_path": str(target),
        "old_string": "value = 1",
        "new_string": "    value = 1",
    }))
    assert got == "    value = 1"


def test_write_over_existing_file_only_introduces_the_difference(tmp_path):
    target = tmp_path / "svc.py"
    target.write_text(f"{VIOLATION}\ndef handler():\n    pass\n", encoding="utf-8")

    got = introduced_content(_event("Write", {
        "file_path": str(target),
        "content": f"{VIOLATION}\ndef handler():\n    return 1\n",
    }))
    assert "return 1" in got
    assert VIOLATION not in got


def test_line_move_represented_as_insertion_is_introduced(tmp_path):
    """A moved line is checked when deterministic alignment calls it inserted."""
    target = tmp_path / "svc.py"
    target.write_text(f"def handler():\n    pass\n{VIOLATION}\n", encoding="utf-8")

    got = introduced_content(_event("Write", {
        "file_path": str(target),
        "content": f"{VIOLATION}\ndef handler():\n    pass\n",
    }))
    assert VIOLATION in got


def test_block_aligned_as_unchanged_is_not_claimed_as_semantic_move(tmp_path):
    """Movement attribution follows the diff; it does not infer author intent."""
    target = tmp_path / "svc.py"
    block = f"{VIOLATION}\na\nb\nc\nd"
    target.write_text(f"header\n{block}\n", encoding="utf-8")

    got = introduced_content(_event("Write", {
        "file_path": str(target),
        "content": f"{block}\nheader\n",
    }))
    assert got == "header"
    assert VIOLATION not in got


def test_added_line_starting_with_two_plus_characters_is_introduced(tmp_path):
    """Regression: unified-diff parsing mistook `++...` content for a header."""
    target = tmp_path / "config.txt"
    target.write_text("keep\n", encoding="utf-8")

    got = introduced_content(_event("Write", {
        "file_path": str(target),
        "content": "keep\n++danger\n",
    }))
    assert got == "++danger"


def test_edit_reads_current_file_once(tmp_path, monkeypatch):
    target = tmp_path / "svc.py"
    target.write_text("value = 1\n", encoding="utf-8")
    original_read_text = Path.read_text
    reads: list[Path] = []

    def counted_read_text(path, *args, **kwargs):
        if path == target:
            reads.append(path)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counted_read_text)
    got = introduced_content(_event("Edit", {
        "file_path": str(target),
        "old_string": "value = 1",
        "new_string": "value = 2",
    }))

    assert got == "value = 2"
    assert reads == [target]


def test_multiedit_introduces_only_its_additions(tmp_path):
    target = tmp_path / "svc.py"
    target.write_text(
        f"{VIOLATION}\ndef a():\n    pass\ndef b():\n    pass\n", encoding="utf-8"
    )
    got = introduced_content(_event("MultiEdit", {
        "file_path": str(target),
        "edits": [
            {"old_string": "def a():\n    pass", "new_string": "def a():\n    return 1"},
            {"old_string": "def b():\n    pass", "new_string": "def b():\n    return 2"},
        ],
    }))
    assert "return 1" in got and "return 2" in got
    assert VIOLATION not in got


# ── end to end through the real CLI ──────────────────────────────────────────

@pytest.fixture
def project(tmp_path):
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


def _edit_envelope(cwd, file_path, old, new):
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "cwd": str(cwd),
        "tool_input": {
            "file_path": str(file_path),
            "old_string": old,
            "new_string": new,
        },
    })


@pytest.mark.skipif(shutil.which("mneme") is None, reason="mneme CLI not on PATH")
def test_unrelated_edit_to_a_dirty_file_is_not_blocked(project):
    """#259 end to end: installing on a repo with existing debt must not wall it off."""
    target = project / "legacy.py"
    target.write_text(f"{VIOLATION}\ndef handler():\n    pass\n", encoding="utf-8")

    err = io.StringIO()
    rc = main(
        stdin=io.StringIO(_edit_envelope(project, target, "    pass", "    return 1")),
        stderr=err,
    )
    assert rc == 0, (
        f"an unrelated edit must not be blocked by a pre-existing violation; "
        f"stderr={err.getvalue()}"
    )


@pytest.mark.skipif(shutil.which("mneme") is None, reason="mneme CLI not on PATH")
def test_remediating_edit_is_not_blocked(project):
    target = project / "legacy.py"
    target.write_text(f"{VIOLATION}\n", encoding="utf-8")

    rc = main(
        stdin=io.StringIO(_edit_envelope(project, target, VIOLATION, CLEAN)),
        stderr=io.StringIO(),
    )
    assert rc == 0, "the edit that removes a violation must never be blocked"


@pytest.mark.skipif(shutil.which("mneme") is None, reason="mneme CLI not on PATH")
def test_introducing_a_violation_still_blocks(project):
    """The guarantee that must survive the change."""
    target = project / "svc.py"
    target.write_text("def handler():\n    pass\n", encoding="utf-8")

    err = io.StringIO()
    rc = main(
        stdin=io.StringIO(
            _edit_envelope(project, target, "    pass", f"    {VIOLATION}")
        ),
        stderr=err,
    )
    assert rc == 2
    assert "psycopg2" in err.getvalue() or "test_001" in err.getvalue()

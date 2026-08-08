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


def test_write_over_existing_file_only_introduces_the_difference(tmp_path):
    target = tmp_path / "svc.py"
    target.write_text(f"{VIOLATION}\ndef handler():\n    pass\n", encoding="utf-8")

    got = introduced_content(_event("Write", {
        "file_path": str(target),
        "content": f"{VIOLATION}\ndef handler():\n    return 1\n",
    }))
    assert "return 1" in got
    assert VIOLATION not in got


def test_moving_a_violating_line_counts_as_introducing_it(tmp_path):
    """Deliberately conservative: relocation re-introduces at the new position.

    Attributing a moved violation to the edit that moved it is the safe
    direction -- the alternative lets an agent launder a violation by shuffling
    lines.
    """
    target = tmp_path / "svc.py"
    target.write_text(f"def handler():\n    pass\n{VIOLATION}\n", encoding="utf-8")

    got = introduced_content(_event("Write", {
        "file_path": str(target),
        "content": f"{VIOLATION}\ndef handler():\n    pass\n",
    }))
    assert VIOLATION in got


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

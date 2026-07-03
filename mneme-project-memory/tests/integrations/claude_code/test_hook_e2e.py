"""End-to-end test that calls the real mneme check binary via the hook shim.

Skipped when mneme is not on PATH (e.g. fresh CI before pip install -e .).
Run `pip install -e .` first to make mneme available.
"""
import json
import io
import shutil
from pathlib import Path
import pytest
from mneme.integrations.claude_code.hook import main

FIXTURE = Path(__file__).parent / "fixtures" / "project_memory.json"

# Seed content that will be replaced in Edit envelopes.
SEED_OLD = "# placeholder import line"


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    # Use "storage_db.py" so the query "edit to .../storage_db.py" contains
    # the token "storage", which matches the fixture decision's scope field
    # and ensures the retriever returns a non-zero score.
    target = tmp_path / "storage_db.py"
    target.write_text(SEED_OLD + "\n", encoding="utf-8")
    return tmp_path, target


def _envelope(cwd, file_path, new_string):
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "cwd": str(cwd),
        "tool_input": {
            "file_path": str(file_path),
            "old_string": SEED_OLD,
            "new_string": new_string,
        },
    })


def _write_envelope(cwd, file_path, content):
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "cwd": str(cwd),
        "tool_input": {
            "file_path": str(file_path),
            "content": content,
        },
    })


@pytest.mark.skipif(shutil.which("mneme") is None, reason="mneme CLI not on PATH")
def test_violation_blocks(project):
    cwd, target = project
    err = io.StringIO()
    rc = main(stdin=io.StringIO(_envelope(cwd, target, "import psycopg2")), stderr=err)
    assert rc == 2
    output = err.getvalue()
    assert "test_001" in output or "psycopg2" in output


@pytest.mark.skipif(shutil.which("mneme") is None, reason="mneme CLI not on PATH")
def test_compliant_passes(project):
    cwd, target = project
    rc = main(stdin=io.StringIO(_envelope(cwd, target, "import sqlite3")))
    assert rc == 0


@pytest.mark.skipif(shutil.which("mneme") is None, reason="mneme CLI not on PATH")
def test_violating_write_blocks(project):
    cwd, target = project
    err = io.StringIO()
    rc = main(
        stdin=io.StringIO(_write_envelope(cwd, target, "import psycopg2\n")),
        stderr=err,
    )
    assert rc == 2
    output = err.getvalue()
    assert "test_001" in output or "psycopg2" in output


@pytest.mark.skipif(shutil.which("mneme") is None, reason="mneme CLI not on PATH")
def test_compliant_write_passes(project):
    cwd, target = project
    rc = main(stdin=io.StringIO(_write_envelope(cwd, target, "import sqlite3\n")))
    assert rc == 0

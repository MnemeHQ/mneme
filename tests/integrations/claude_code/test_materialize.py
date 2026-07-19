import pytest
from mneme.integrations.claude_code.hook import (
    ToolEvent,
    materialize_proposed_content,
    MaterializeError,
)


def _evt(tool, file_path, **input_extra):
    return ToolEvent(tool_name=tool, file_path=str(file_path), cwd="", tool_input={"file_path": str(file_path), **input_extra})


def test_write_returns_full_content_even_when_file_absent(tmp_path):
    target = tmp_path / "new.py"  # does not exist
    event = _evt("Write", target, content="import sqlite3\n")
    assert materialize_proposed_content(event) == "import sqlite3\n"


def test_edit_applies_replacement_against_real_file(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("import os\n\ndef f():\n    return None\n", encoding="utf-8")
    event = _evt("Edit", target, old_string="return None", new_string="return 1")
    out = materialize_proposed_content(event)
    assert "import os" in out
    assert "return 1" in out
    assert "return None" not in out


def test_multiedit_applies_edits_in_order(tmp_path):
    target = tmp_path / "db.py"
    target.write_text("X = 0\nY = 0\n", encoding="utf-8")
    event = _evt(
        "MultiEdit", target,
        edits=[
            {"old_string": "X = 0", "new_string": "X = 1"},
            {"old_string": "Y = 0", "new_string": "Y = 2"},
        ],
    )
    out = materialize_proposed_content(event)
    assert out == "X = 1\nY = 2\n"


def test_edit_raises_when_file_missing(tmp_path):
    event = _evt("Edit", tmp_path / "missing.py", old_string="a", new_string="b")
    with pytest.raises(MaterializeError):
        materialize_proposed_content(event)


def test_edit_raises_when_old_string_not_found(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("hello\n", encoding="utf-8")
    event = _evt("Edit", target, old_string="missing", new_string="x")
    with pytest.raises(MaterializeError):
        materialize_proposed_content(event)

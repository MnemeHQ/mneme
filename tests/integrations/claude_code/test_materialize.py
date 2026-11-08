import pytest
from mneme.integrations.claude_code.hook import (
    ToolEvent,
    introduced_content,
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


# --- #571: the snapshot is read from the same path as --target-path ---------

def _rel_evt(tool, rel, cwd, **input_extra):
    return ToolEvent(
        tool_name=tool, file_path=rel, cwd=str(cwd),
        tool_input={"file_path": rel, **input_extra},
    )


def _two_dirs(tmp_path, monkeypatch):
    project, elsewhere = tmp_path / "project", tmp_path / "elsewhere"
    project.mkdir()
    elsewhere.mkdir()
    (project / "app.py").write_text("real\n", encoding="utf-8")
    (elsewhere / "app.py").write_text("decoy\n", encoding="utf-8")
    monkeypatch.chdir(elsewhere)
    return project, elsewhere


def test_relative_edit_reads_snapshot_from_event_cwd(tmp_path, monkeypatch):
    project, _ = _two_dirs(tmp_path, monkeypatch)
    event = _rel_evt("Edit", "app.py", project, old_string="real", new_string="new")
    assert materialize_proposed_content(event) == "new\n"


def test_relative_write_diffs_against_event_cwd_file(tmp_path, monkeypatch):
    project, _ = _two_dirs(tmp_path, monkeypatch)
    event = _rel_evt("Write", "app.py", project, content="decoy\n")
    # Against the real file every line is new; against the decoy nothing is.
    assert introduced_content(event) == "decoy"


def test_relative_path_with_empty_cwd_still_reads_process_cwd(tmp_path, monkeypatch):
    _two_dirs(tmp_path, monkeypatch)
    event = _rel_evt("Edit", "app.py", "", old_string="decoy", new_string="x")
    assert materialize_proposed_content(event) == "x\n"


def test_absolute_path_ignores_event_cwd(tmp_path, monkeypatch):
    project, elsewhere = _two_dirs(tmp_path, monkeypatch)
    event = _rel_evt(
        "Edit", str(elsewhere / "app.py"), project, old_string="decoy", new_string="x"
    )
    assert materialize_proposed_content(event) == "x\n"

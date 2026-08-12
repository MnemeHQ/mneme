"""Tests for `replace_all` handling in proposed-content materialization.

Claude Code's Edit tool accepts a `replace_all` flag. When it is set, every
occurrence of `old_string` is replaced, not just the first. If the hook
materializes only the first replacement, it checks a file that differs from
what Claude Code is actually about to write -- so a violation introduced by
the 2nd..Nth occurrence is never seen.
"""
from mneme.integrations.claude_code.hook import (
    ToolEvent,
    materialize_proposed_content,
)


def _event(tool: str, file_path: str, **tool_input) -> ToolEvent:
    ti = {"file_path": file_path, **tool_input}
    return ToolEvent(
        tool_name=tool,
        file_path=file_path,
        cwd=str(file_path),
        tool_input=ti,
    )


def _target(tmp_path, content: str):
    p = tmp_path / "x.py"
    p.write_text(content, encoding="utf-8")
    return p


# ── Edit ─────────────────────────────────────────────────────────────────────

def test_edit_replace_all_replaces_every_occurrence(tmp_path):
    target = _target(tmp_path, "a = 1\nb = a\nc = a\n")
    out = materialize_proposed_content(
        _event("Edit", str(target), old_string="a", new_string="Z", replace_all=True)
    )
    assert out == "Z = 1\nb = Z\nc = Z\n"


def test_edit_without_replace_all_replaces_only_first(tmp_path):
    """Regression guard: default behaviour must stay single-replacement."""
    target = _target(tmp_path, "a = 1\nb = a\nc = a\n")
    out = materialize_proposed_content(
        _event("Edit", str(target), old_string="a", new_string="Z")
    )
    assert out == "Z = 1\nb = a\nc = a\n"


def test_edit_replace_all_false_replaces_only_first(tmp_path):
    target = _target(tmp_path, "a = 1\nb = a\n")
    out = materialize_proposed_content(
        _event("Edit", str(target), old_string="a", new_string="Z", replace_all=False)
    )
    assert out == "Z = 1\nb = a\n"


def test_edit_replace_all_surfaces_violation_in_later_occurrence(tmp_path):
    """The bug that matters: a banned term introduced by the 2nd occurrence."""
    target = _target(tmp_path, "db = LOCAL\ncache = LOCAL\n")
    out = materialize_proposed_content(
        _event("Edit", str(target), old_string="LOCAL", new_string="postgres",
               replace_all=True)
    )
    assert out.count("postgres") == 2


# ── MultiEdit ────────────────────────────────────────────────────────────────

def test_multiedit_honors_per_edit_replace_all(tmp_path):
    target = _target(tmp_path, "a = 1\nb = a\nq = 9\n")
    out = materialize_proposed_content(
        _event(
            "MultiEdit",
            str(target),
            edits=[
                {"old_string": "a", "new_string": "Z", "replace_all": True},
                {"old_string": "q", "new_string": "W"},
            ],
        )
    )
    assert out == "Z = 1\nb = Z\nW = 9\n"


def test_multiedit_without_replace_all_replaces_only_first(tmp_path):
    target = _target(tmp_path, "a = 1\nb = a\n")
    out = materialize_proposed_content(
        _event(
            "MultiEdit",
            str(target),
            edits=[{"old_string": "a", "new_string": "Z"}],
        )
    )
    assert out == "Z = 1\nb = a\n"

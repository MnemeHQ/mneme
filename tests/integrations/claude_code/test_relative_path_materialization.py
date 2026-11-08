"""#571 through the Claude Code entry point: ``handle_event`` with a relative
``file_path`` and the hook process running outside the payload ``cwd``.

Claude Code sends absolute paths, so this pins the shared materializer at the
boundary rather than describing an observed payload.
"""
import io

from mneme.integrations.claude_code.hook import handle_event
from tests.integrations.relative_paths import (
    BASELINE,
    FORBIDDEN,
    TARGET,
    VIOLATING,
    make_layout,
)


def _handle(cwd, tool, tool_input):
    out, err = io.StringIO(), io.StringIO()
    rc = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "cwd": str(cwd),
            "tool_name": tool,
            "tool_input": tool_input,
        },
        stderr=err,
        stdout=out,
    )
    return rc, out.getvalue(), err.getvalue()


def test_relative_write_identical_decoy_blocked(tmp_path, monkeypatch):
    layout = make_layout(tmp_path, monkeypatch)
    layout.decoy(VIOLATING)
    rc, _out, err = _handle(layout.project, "Write", {"file_path": TARGET, "content": VIOLATING})
    assert rc == 2
    assert FORBIDDEN in err


def test_relative_edit_without_cwd_file_blocked(tmp_path, monkeypatch):
    layout = make_layout(tmp_path, monkeypatch)
    rc, _out, err = _handle(
        layout.project,
        "Edit",
        {"file_path": TARGET, "old_string": BASELINE.strip(), "new_string": f"{FORBIDDEN} = True"},
    )
    assert rc == 2
    assert "cannot materialize" not in err


def test_absolute_write_unchanged(tmp_path, monkeypatch):
    layout = make_layout(tmp_path, monkeypatch)
    layout.decoy(VIOLATING)
    rc, _out, _err = _handle(
        layout.project, "Write", {"file_path": str(layout.real()), "content": VIOLATING}
    )
    assert rc == 2

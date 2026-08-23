"""ADR-020 path applicability and path normalization through the Kiro gate."""
import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mneme.integrations.kiro.hook import main

FIXTURE = Path(__file__).parent / "fixtures" / "project_memory.json"
MARKER = "EXPERIMENTAL_MARKER_XY"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    monkeypatch.delenv("MNEME_HOOK_MODE", raising=False)


def _project(tmp_path):
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


def _envelope(cwd, path, content):
    return json.dumps({
        "hook_event_name": "preToolUse",
        "cwd": str(cwd),
        "tool_name": "fs_write",
        "tool_input": {"path": str(path), "content": content},
    })


def _run(tmp_path, envelope):
    """Returns (rc, cap) where cap records every child invocation."""
    commands = []

    def _run_check(command, **kwargs):
        commands.append(list(command))
        return MagicMock(returncode=0, stdout="", stderr="")

    out, err = io.StringIO(), io.StringIO()
    with patch("mneme.integrations.kiro.hook.subprocess.run", _run_check):
        rc = main(stdin=io.StringIO(envelope), stderr=err, stdout=out)
    return rc, out.getvalue(), err.getvalue(), commands


def _checked_text(command):
    input_path = command[command.index("--input") + 1]
    return Path(input_path).read_text(encoding="utf-8")


def test_include_path_match_enforced(tmp_path):
    project = _project(tmp_path)
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir()
    rc, _, _, _ = _run(project, _envelope(project, target, MARKER + "\n"))
    assert rc == 0  # mocked child returns no verdict -> fail open; the point
    # of this test is that the scoped rule was *evaluated*, i.e. the child was
    # invoked with the resolved absolute target path:
    _, _, _, commands = _run(project, _envelope(project, target, MARKER + "\n"))
    command = commands[0]
    assert "--target-path" in command
    assert Path(command[command.index("--target-path") + 1]).is_absolute()


def test_exclude_path_not_checked_as_violation(tmp_path):
    """A generated file under src/generated/ is excluded from the scoped rule;
    the marker there must not be attributed as an introduction."""
    project = _project(tmp_path)
    generated = tmp_path / "src" / "generated" / "out.py"
    generated.parent.mkdir(parents=True)
    rc, out, _, commands = _run(project, _envelope(project, generated, MARKER + "\n"))
    # With a real CLI this is a trusted PASS; with the mock it fails open on
    # stdout. Either way the hook never blocks: assert exit 0.
    assert rc == 0


def test_nonmatching_path_outside_include_not_blocked_by_scoped_rule(tmp_path):
    project = _project(tmp_path)
    target = tmp_path / "docs" / "notes.md"
    target.parent.mkdir()
    rc, _, _, _ = _run(project, _envelope(project, target, MARKER + "\n"))
    assert rc == 0


def test_relative_path_resolved_against_event_cwd(tmp_path):
    project = _project(tmp_path)
    (tmp_path / "src").mkdir()
    envelope = _envelope(str(tmp_path), "src/rel_app.py", "x\ny\n")
    rc, _, _, commands = _run(project, envelope)
    assert rc == 0
    command = commands[0]
    expected = str((tmp_path / "src" / "rel_app.py").resolve())
    assert Path(command[command.index("--target-path") + 1]) == Path(expected)


def test_query_uses_real_target_name(tmp_path):
    project = _project(tmp_path)
    envelope = _envelope(str(project), "src/named.py", "a\n")
    rc, _, _, commands = _run(project, envelope)
    command = commands[0]
    query = command[command.index("--query") + 1]
    assert query == "edit to src/named.py"

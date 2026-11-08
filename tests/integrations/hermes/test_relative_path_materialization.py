"""#571: Hermes ``write_file`` / ``patch`` (replace) resolve relative paths
against ``project_dir`` for both the snapshot and ``--target-path``."""
from mneme.integrations.hermes.adapter import ACTION_ALLOW, ACTION_DENY, MnemeHermes
from tests.integrations.relative_paths import (
    FORBIDDEN,
    TARGET,
    VIOLATING,
    RecordingRunner,
    make_layout,
)


def _gate(layout, runner):
    return MnemeHermes(project_dir=str(layout.project), mode="strict", check_runner=runner)


def test_relative_write_identical_decoy_denied(tmp_path, monkeypatch):
    layout = make_layout(tmp_path, monkeypatch)
    layout.decoy(VIOLATING)
    runner = RecordingRunner()
    result = _gate(layout, runner).evaluate_tool_call(
        "write_file", {"path": TARGET, "content": VIOLATING}, cwd=str(layout.project)
    )
    assert result.action == ACTION_DENY
    assert FORBIDDEN in runner.sent[0].content
    assert runner.sent[0].target_path == str(layout.real())


def test_relative_write_decoy_with_forbidden_line_denied(tmp_path, monkeypatch):
    layout = make_layout(tmp_path, monkeypatch)
    layout.decoy(f"{FORBIDDEN} = True\n")
    runner = RecordingRunner()
    result = _gate(layout, runner).evaluate_tool_call(
        "write_file", {"path": TARGET, "content": VIOLATING}, cwd=str(layout.project)
    )
    assert result.action == ACTION_DENY


def test_relative_patch_replace_without_cwd_file_denied(tmp_path, monkeypatch):
    layout = make_layout(tmp_path, monkeypatch)
    runner = RecordingRunner()
    result = _gate(layout, runner).evaluate_tool_call(
        "patch",
        {"path": TARGET, "old_string": "TIMEOUT_SECONDS = 5", "new_string": f"{FORBIDDEN} = True"},
        cwd=str(layout.project),
    )
    assert result.action == ACTION_DENY
    assert runner.sent[0].content == f"{FORBIDDEN} = True"


def test_relative_patch_replace_ignores_decoy(tmp_path, monkeypatch):
    layout = make_layout(tmp_path, monkeypatch)
    layout.decoy("unrelated = 0\n")
    runner = RecordingRunner()
    result = _gate(layout, runner).evaluate_tool_call(
        "patch",
        {"path": TARGET, "old_string": "TIMEOUT_SECONDS = 5", "new_string": "TIMEOUT_SECONDS = 10"},
        cwd=str(layout.project),
    )
    assert result.action == ACTION_ALLOW
    assert runner.sent[0].content == "TIMEOUT_SECONDS = 10"


def test_default_cwd_resolves_against_project_dir(tmp_path, monkeypatch):
    """Direct API callers that omit ``cwd`` get ``project_dir``, matching the
    V4A and terminal paths."""
    layout = make_layout(tmp_path, monkeypatch)
    layout.decoy(VIOLATING)
    runner = RecordingRunner()
    result = _gate(layout, runner).evaluate_tool_call(
        "write_file", {"path": TARGET, "content": VIOLATING}
    )
    assert result.action == ACTION_DENY
    assert runner.sent[0].target_path == str(layout.real())


def test_explicit_cwd_is_used_for_snapshot_and_target(tmp_path, monkeypatch):
    """A caller ``cwd`` other than ``project_dir`` names one file for both."""
    layout = make_layout(tmp_path, monkeypatch)
    other = layout.project / "pkg"
    (other / "src").mkdir(parents=True)
    (other / TARGET).write_text(VIOLATING, encoding="utf-8")
    layout.decoy(VIOLATING)
    runner = RecordingRunner()
    result = _gate(layout, runner).evaluate_tool_call(
        "write_file", {"path": TARGET, "content": VIOLATING + "RETRIES = 2\n"}, cwd=str(other)
    )
    assert runner.sent[0].target_path == str(other / TARGET)
    assert runner.sent[0].content == "RETRIES = 2"
    assert result.action == ACTION_ALLOW

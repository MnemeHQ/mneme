"""The #571 regression matrix, shared by the Agent SDK and LangChain suites.

Subclasses provide ``evaluate(layout, runner, tool, tool_input)`` returning a
``GateResult`` and the surface's tool names; pytest collects the inherited
``test_*`` methods once per subclass. Rows are numbered as in #571.
"""
from __future__ import annotations

import pytest

from mneme.integrations.agent_sdk import (
    ACTION_ALLOW,
    ACTION_DENY,
    ACTION_FAIL_OPEN,
)
from tests.integrations.relative_paths import (
    BASELINE,
    FORBIDDEN,
    TARGET,
    VIOLATING,
    RecordingRunner,
    applicability_paths,
    make_layout,
)


class RelativePathMatrix:
    WRITE = "Write"
    EDIT = "Edit"

    def evaluate(self, layout, runner, tool, tool_input):  # pragma: no cover
        raise NotImplementedError

    @pytest.fixture()
    def layout(self, tmp_path, monkeypatch):
        return make_layout(tmp_path, monkeypatch)

    @pytest.fixture()
    def runner(self):
        return RecordingRunner()

    def _write(self, layout, runner, content, path=TARGET):
        return self.evaluate(
            layout, runner, self.WRITE, {"file_path": path, "content": content}
        )

    def _edit(self, layout, runner, old, new, path=TARGET):
        return self.evaluate(
            layout,
            runner,
            self.EDIT,
            {"file_path": path, "old_string": old, "new_string": new},
        )

    def _assert_target(self, layout, runner, rel=TARGET):
        assert runner.sent, "the gate must reach mneme check"
        assert runner.sent[-1].target_path == str(layout.real(rel))

    # Row 1: identical decoy must not turn a violating write into a silent skip.
    def test_row1_write_identical_decoy_is_checked_and_denied(self, layout, runner):
        layout.decoy(VIOLATING)
        result = self._write(layout, runner, VIOLATING)
        assert len(runner.sent) == 1
        assert FORBIDDEN in runner.sent[0].content
        self._assert_target(layout, runner)
        assert result.action == ACTION_DENY

    # Row 2: a decoy sharing the forbidden line must not yield a trusted PASS.
    def test_row2_write_decoy_with_forbidden_line_is_denied(self, layout, runner):
        layout.decoy(f"{FORBIDDEN} = True\n")
        result = self._write(layout, runner, VIOLATING)
        assert result.action == ACTION_DENY
        assert result.verdict != "PASS"
        assert FORBIDDEN in runner.sent[0].content
        self._assert_target(layout, runner)

    # Row 3: the delta is taken against the real target, so a violation that
    # is already present there is not attributed to an unrelated write.
    def test_row3_write_diffs_against_real_target(self, layout, runner):
        layout.real().write_text(VIOLATING, encoding="utf-8")
        result = self._write(layout, runner, VIOLATING + "RETRIES = 2\n")
        assert runner.sent[0].content == "RETRIES = 2"
        self._assert_target(layout, runner)
        assert result.action == ACTION_ALLOW
        assert result.verdict == "PASS"

    # Row 4: a relative edit materializes from the real target, not cwd.
    def test_row4_edit_without_cwd_file_is_denied(self, layout, runner):
        result = self._edit(layout, runner, "TIMEOUT_SECONDS = 5", f"{FORBIDDEN} = True")
        assert result.action == ACTION_DENY
        assert runner.sent[0].content == f"{FORBIDDEN} = True"
        self._assert_target(layout, runner)

    # Row 5: a decoy never supplies the edit's snapshot.
    def test_row5_edit_ignores_decoy_without_old_string(self, layout, runner):
        layout.decoy("unrelated = 0\n")
        result = self._edit(layout, runner, "TIMEOUT_SECONDS = 5", "TIMEOUT_SECONDS = 10")
        assert result.action == ACTION_ALLOW
        assert runner.sent[0].content == "TIMEOUT_SECONDS = 10"
        self._assert_target(layout, runner)

    def test_row5b_edit_does_not_borrow_old_string_from_decoy(self, layout, runner):
        layout.decoy("MARKER = 1\n")
        result = self._edit(layout, runner, "MARKER = 1", f"{FORBIDDEN} = True")
        # The real target has no MARKER line, so the tool would fail too: the
        # gate reports unevaluated instead of checking the decoy's edit.
        assert result.action == ACTION_FAIL_OPEN
        assert "old_string not found" in result.reason
        assert runner.sent == []

    # Row 6: absolute in-project paths are unaffected by a decoy.
    def test_row6_absolute_write_denied(self, layout, runner):
        layout.decoy(VIOLATING)
        result = self._write(layout, runner, VIOLATING, path=str(layout.real()))
        assert result.action == ACTION_DENY
        self._assert_target(layout, runner)

    def test_row6_absolute_edit_denied(self, layout, runner):
        layout.decoy(BASELINE)
        result = self._edit(
            layout, runner, "TIMEOUT_SECONDS = 5", f"{FORBIDDEN} = True",
            path=str(layout.real()),
        )
        assert result.action == ACTION_DENY
        self._assert_target(layout, runner)

    # Row 7: a relative path escaping the policy root stays a visible
    # fail-open (ADR-020 PATH_APPLICABILITY_UNKNOWN), never a PASS.
    def test_row7_relative_escape_fails_open_visibly(self, layout, runner):
        result = self._write(layout, runner, VIOLATING, path="../outside/router.py")
        assert result.action == ACTION_FAIL_OPEN
        assert result.evaluation_complete is False

    # Row 9: applicability is evaluated on the project-relative target.
    def test_row9_applicability_uses_project_target(self, layout, runner):
        layout.decoy(VIOLATING)
        result = self._write(layout, runner, VIOLATING)
        assert result.action == ACTION_DENY
        assert applicability_paths(runner.sent[0]) == [(TARGET, "APPLIED")]

    def test_row9_excluded_path_still_excluded(self, layout, runner):
        layout.decoy("", rel="docs/notes.md")
        result = self._write(layout, runner, f"{FORBIDDEN}\n", path="docs/notes.md")
        assert result.action == ACTION_ALLOW
        assert applicability_paths(runner.sent[0]) == [("docs/notes.md", "EXCLUDED")]
        self._assert_target(layout, runner, rel="docs/notes.md")

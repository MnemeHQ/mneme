"""Mutation-gate policy tests for the Kiro hook (subprocess mocked).

Every verdict-level test drives main() through the same code path Kiro
invokes and pins the documented exit-code contract: 0 = allow, non-zero =
block; fail-open outcomes are always visible on stdout.
"""
import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mneme.integrations.kiro.hook import main

FIXTURE = Path(__file__).parent / "fixtures" / "project_memory.json"

VIOLATION = "legacy_client.connect("
COMPLIANT = "from compat import facade\nfacade.open_session()\n"


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


def _envelope(cwd, path, content, tool="fs_write"):
    return json.dumps({
        "hook_event_name": "preToolUse",
        "cwd": str(cwd),
        "tool_name": tool,
        "tool_input": {"path": str(path), "content": content},
    })


def _verdict(verdict="FAIL", evaluation_complete=True):
    payload = {
        "schema": "mneme.check/v1",
        "verdict": verdict,
        "mode": "strict",
        "violations": [{
            "decision_id": "test_002",
            "decision_text": "Do not call the legacy client directly",
            "severity": verdict,
            "rule_type": "FORBID_LITERAL",
            "rule": VIOLATION,
            "trigger": VIOLATION,
        }],
        "freshness": [],
    }
    if not evaluation_complete:
        payload["evaluation_complete"] = False
        payload["applicability"] = [{
            "decision_id": "test_003",
            "rule_type": "FORBID_LITERAL",
            "rule_value": "EXPERIMENTAL_MARKER_XY",
            "outcome": "UNKNOWN",
            "reason": "outside policy root",
        }]
    return json.dumps(payload)


class _Capture:
    """subprocess.run stand-in that records the command and returns a fixed
    CompletedProcess."""

    def __init__(self, stdout="", stderr="", exc=None):
        self.stdout = stdout
        self.stderr = stderr
        self.exc = exc
        self.commands = []

    def __call__(self, command, **kwargs):
        self.commands.append(list(command))
        input_path = command[command.index("--input") + 1]
        self._record_input(len(self.commands) - 1, input_path)
        if self.exc is not None:
            raise self.exc
        return MagicMock(returncode=0, stdout=self.stdout, stderr=self.stderr)

    def checked_text(self, index=0):
        """The text handed to `mneme check` via --input, captured at call
        time (the hook deletes the temp file after the child exits)."""
        command = self.commands[index]
        input_path = command[command.index("--input") + 1]
        return self._checked[index]

    def _record_input(self, index, path):
        self._checked[index] = Path(path).read_text(encoding="utf-8")

    _checked = None

    def __init__(self, stdout="", stderr="", exc=None):
        self.stdout = stdout
        self.stderr = stderr
        self.exc = exc
        self.commands = []
        self._checked = {}


# --- forbidden literal introduced into a new file -> blocked before disk ---

def test_forbidden_literal_in_new_file_blocked(tmp_path):
    project = _project(tmp_path)
    target = tmp_path / "new_file.py"
    rc, out, err, _ = _gate(
        project, _envelope(project, target, f"x = 1\n{VIOLATION}\n"),
        stdout=_verdict(),
    )
    assert rc != 0
    assert VIOLATION in err or "test_002" in err
    assert out == ""
    assert not target.exists(), "the hook must not touch disk on a block"


# --- forbidden literal introduced through an edit -> blocked ---

def test_forbidden_literal_introduced_by_edit_blocked(tmp_path):
    project = _project(tmp_path)
    target = tmp_path / "existing.py"
    target.write_text("x = 1\n", encoding="utf-8")
    rc, _, err, _ = _gate(
        project, _envelope(project, target, f"x = 1\n{VIOLATION}\n"),
        stdout=_verdict(),
    )
    assert rc != 0


def test_edit_gate_checks_introduced_lines_only(tmp_path):
    """ADR-018 through the Kiro shape: only inserted lines reach the checker."""
    project = _project(tmp_path)
    target = tmp_path / "app.py"
    target.write_text("keep_a\nkeep_b\nkeep_c\n", encoding="utf-8")
    proposed = "keep_a\nkeep_b\nkeep_c\nNEW_INTRODUCED_LINE\n"
    cap = _Capture(stdout=_verdict())
    with patch("mneme.integrations.kiro.hook.subprocess.run", cap):
        rc = main(stdin=io.StringIO(_envelope(project, target, proposed)),
                  stderr=io.StringIO())
    assert rc == 2
    assert cap.checked_text() == "NEW_INTRODUCED_LINE"


# --- compliant write -> allowed ---

def test_compliant_write_allowed(tmp_path):
    project = _project(tmp_path)
    rc, out, _, _ = _gate(
        project, _envelope(project, tmp_path / "ok.py", COMPLIANT),
        stdout=_verdict("PASS"),
    )
    assert rc == 0
    assert out == "", "PASS must not inject anything into agent context"


# --- pure deletion / remediation -> allowed ---

def test_remediation_of_violation_allowed(tmp_path):
    project = _project(tmp_path)
    target = tmp_path / "dirty.py"
    target.write_text(f"a\n{VIOLATION}\nb\n", encoding="utf-8")
    rc, _, _, _ = _gate(
        project, _envelope(project, target, "a\nb\n"), stdout=_verdict("PASS")
    )
    assert rc == 0


def test_pure_deletion_allowed(tmp_path):
    project = _project(tmp_path)
    target = tmp_path / "gone.py"
    target.write_text("line1\nline2\nline3\n", encoding="utf-8")
    cap = _Capture()
    with patch("mneme.integrations.kiro.hook.subprocess.run", cap):
        rc = main(stdin=io.StringIO(_envelope(project, target, "")),
                  stderr=io.StringIO())
    assert rc == 0
    assert not cap.commands, "a deletion introduces nothing to check"


# --- pre-existing violation plus unrelated edit -> allowed ---

def test_preexisting_violation_plus_unrelated_edit_allowed(tmp_path):
    project = _project(tmp_path)
    target = tmp_path / "dirty.py"
    target.write_text(f"{VIOLATION}\nrest\n", encoding="utf-8")
    cap = _Capture(stdout=_verdict("PASS"))
    with patch("mneme.integrations.kiro.hook.subprocess.run", cap):
        rc = main(
            stdin=io.StringIO(_envelope(project, target, f"{VIOLATION}\nrest\nmore\n")),
            stderr=io.StringIO(),
        )
    assert rc == 0
    checked = cap.checked_text()
    assert VIOLATION not in checked, (
        "pre-existing violation must not be attributed to an unrelated edit"
    )
    assert "more" in checked


# --- ADR-017/019: generic filename still enforces a typed literal ---

def test_generic_filename_still_enforces_typed_literal(tmp_path):
    project = _project(tmp_path)
    target = tmp_path / "service.py"  # zero lexical overlap with the decisions
    rc, _, _, _ = _gate(
        project, _envelope(project, target, f"x\n{VIOLATION}\n"), stdout=_verdict()
    )
    assert rc != 0


def _gate(cwd, envelope, stdout="", stderr=""):
    """Run main() against a mocked mneme check; returns (rc, out, err, mock)."""
    fake = MagicMock(returncode=0, stdout=stdout, stderr=stderr)
    out, err = io.StringIO(), io.StringIO()
    with patch("mneme.integrations.kiro.hook.subprocess.run", return_value=fake) as mrun:
        rc = main(stdin=io.StringIO(envelope), stderr=err, stdout=out)
    return rc, out.getvalue(), err.getvalue(), mrun

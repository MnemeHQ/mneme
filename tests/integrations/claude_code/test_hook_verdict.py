"""Tests for trusted-verdict handling and warn-mode feedback.

Two defects are pinned here:

1. The hook used to convert *any* non-zero child exit into exit 2 (block).
   `mneme check --mode strict` returns 1 for a WARN verdict, but Python also
   returns 1 for an uncaught exception -- so a malformed memory file or a CLI
   crash hard-blocked the edit. The documented behaviour is fail-open, so only
   a parsed verdict may block.

2. Warn mode wrote to stderr and exited 0. Claude Code discards stderr from a
   hook that exits 0, so warn mode surfaced nothing at all.
"""
import io
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mneme.integrations.claude_code.hook import (
    format_reason,
    main,
    parse_verdict,
)


def _payload(verdict="FAIL", violations=None):
    return json.dumps({
        "schema": "mneme.check/v1",
        "verdict": verdict,
        "mode": "strict",
        "violations": violations if violations is not None else [{
            "decision_id": "storage_json",
            "decision_text": "Use JSON storage only",
            "severity": verdict,
            "rule": "introduce ORM",
            "trigger": "ORM",
        }],
        "freshness": [],
    })


def _project_with_memory(tmp_path):
    mem = tmp_path / ".mneme" / "project_memory.json"
    mem.parent.mkdir()
    mem.write_text('{"decisions": []}')
    target = tmp_path / "x.py"
    target.write_text("import os\n", encoding="utf-8")
    return mem, target


def _edit_envelope(tmp_path, target):
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "cwd": str(tmp_path),
        "tool_input": {
            "file_path": str(target),
            "old_string": "import os",
            "new_string": "import psycopg2",
        },
    })


def _run(tmp_path, target, *, returncode, stdout, stderr_text=""):
    fake = MagicMock(returncode=returncode, stdout=stdout, stderr=stderr_text)
    err, out = io.StringIO(), io.StringIO()
    with patch("mneme.integrations.claude_code.hook.subprocess.run", return_value=fake):
        rc = main(
            stdin=io.StringIO(_edit_envelope(tmp_path, target)),
            stderr=err,
            stdout=out,
        )
    return rc, err.getvalue(), out.getvalue()


# ── parse_verdict rejects everything untrustworthy ───────────────────────────

@pytest.mark.parametrize("stdout", [
    "",
    "Traceback (most recent call last):\n  File ...\nValueError: bad memory",
    "not json at all",
    "[]",
    "null",
    json.dumps({"verdict": "FAIL"}),                       # no schema
    json.dumps({"schema": "something/else", "verdict": "FAIL"}),
    json.dumps({"schema": "mneme.check/v1"}),              # no verdict
    json.dumps({"schema": "mneme.check/v1", "verdict": "BANANA"}),
])
def test_parse_verdict_returns_none_for_untrusted_output(stdout):
    assert parse_verdict(stdout) is None


def test_parse_verdict_accepts_well_formed_payload():
    assert parse_verdict(_payload("FAIL"))["verdict"] == "FAIL"


# ── crashes must fail open, not block ────────────────────────────────────────

def test_traceback_with_exit_one_fails_open(tmp_path):
    """The exact reported defect: a CLI crash must not hard-block an edit."""
    mem, target = _project_with_memory(tmp_path)
    rc, err, _out = _run(
        tmp_path, target,
        returncode=1,
        stdout="",
        stderr_text="Traceback (most recent call last):\nJSONDecodeError: bad memory",
    )
    assert rc == 0
    assert "failing open" in err.lower()


def test_unparseable_stdout_with_exit_two_fails_open(tmp_path):
    mem, target = _project_with_memory(tmp_path)
    rc, err, _out = _run(tmp_path, target, returncode=2, stdout="FAIL: something")
    assert rc == 0
    assert "failing open" in err.lower()


def test_child_stderr_is_surfaced_when_failing_open(tmp_path):
    mem, target = _project_with_memory(tmp_path)
    _rc, err, _out = _run(
        tmp_path, target, returncode=1, stdout="", stderr_text="ValueError: boom",
    )
    assert "ValueError: boom" in err


# ── strict mode blocks only on a parsed verdict ──────────────────────────────

def test_strict_fail_verdict_blocks(tmp_path):
    mem, target = _project_with_memory(tmp_path)
    rc, err, _out = _run(tmp_path, target, returncode=2, stdout=_payload("FAIL"))
    assert rc == 2
    assert "storage_json" in err


def test_strict_warn_verdict_blocks(tmp_path):
    mem, target = _project_with_memory(tmp_path)
    rc, _err, _out = _run(tmp_path, target, returncode=1, stdout=_payload("WARN"))
    assert rc == 2


def test_pass_verdict_does_not_block_or_emit(tmp_path):
    mem, target = _project_with_memory(tmp_path)
    rc, _err, out = _run(
        tmp_path, target, returncode=0, stdout=_payload("PASS", violations=[]),
    )
    assert rc == 0
    assert out == ""


def test_pass_verdict_trusted_over_nonzero_exit(tmp_path):
    """A PASS payload wins even if the child exits non-zero for some other reason."""
    mem, target = _project_with_memory(tmp_path)
    rc, _err, _out = _run(
        tmp_path, target, returncode=1, stdout=_payload("PASS", violations=[]),
    )
    assert rc == 0


# ── warn mode surfaces violations without blocking ───────────────────────────

def test_warn_mode_emits_structured_output(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    mem, target = _project_with_memory(tmp_path)
    rc, _err, out = _run(tmp_path, target, returncode=0, stdout=_payload("FAIL"))
    assert rc == 0
    emitted = json.loads(out)
    hso = emitted["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert "storage_json" in hso["permissionDecisionReason"]


def test_warn_mode_defers_never_allows(tmp_path, monkeypatch):
    """`allow` would auto-approve the tool call and bypass the user's
    permission prompt. A warning must never weaken permissions."""
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    mem, target = _project_with_memory(tmp_path)
    _rc, _err, out = _run(tmp_path, target, returncode=0, stdout=_payload("FAIL"))
    decision = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
    assert decision == "defer"
    assert decision != "allow"


def test_warn_mode_pass_emits_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    mem, target = _project_with_memory(tmp_path)
    rc, _err, out = _run(
        tmp_path, target, returncode=0, stdout=_payload("PASS", violations=[]),
    )
    assert rc == 0
    assert out == ""


def test_warn_mode_never_blocks_on_fail(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    mem, target = _project_with_memory(tmp_path)
    rc, _err, _out = _run(tmp_path, target, returncode=0, stdout=_payload("FAIL"))
    assert rc == 0


# ── the hook asks for JSON ───────────────────────────────────────────────────

def test_child_pythonpath_pins_hook_package_root(tmp_path):
    """The child CLI must be the same mneme the hook was loaded from.

    Without this, `python -m mneme` can resolve to a different (older) install
    that rejects --json; the hook would then fail open on every edit and
    enforcement would be silently inactive.
    """
    import mneme
    from mneme.integrations.claude_code import hook as hook_mod

    mem, target = _project_with_memory(tmp_path)
    fake = MagicMock(returncode=0, stdout=_payload("PASS", violations=[]), stderr="")
    with patch(
        "mneme.integrations.claude_code.hook.subprocess.run", return_value=fake
    ) as mrun:
        main(stdin=io.StringIO(_edit_envelope(tmp_path, target)),
             stderr=io.StringIO(), stdout=io.StringIO())

    env = mrun.call_args.kwargs["env"]
    expected_root = str(Path(mneme.__file__).resolve().parent.parent)
    assert env["PYTHONPATH"].split(os.pathsep)[0] == expected_root
    assert str(hook_mod._PACKAGE_ROOT) == expected_root


def test_stale_runtime_warns_that_enforcement_is_inactive(tmp_path):
    """An old CLI rejecting --json must produce a loud warning, not silence."""
    mem, target = _project_with_memory(tmp_path)
    rc, err, _out = _run(
        tmp_path, target,
        returncode=2,
        stdout="",
        stderr_text="mneme: error: unrecognized arguments: --json",
    )
    assert rc == 0
    assert "ENFORCEMENT IS INACTIVE" in err
    assert "mneme-hq" in err


def test_check_is_invoked_with_json_flag(tmp_path):
    mem, target = _project_with_memory(tmp_path)
    fake = MagicMock(returncode=0, stdout=_payload("PASS", violations=[]), stderr="")
    with patch(
        "mneme.integrations.claude_code.hook.subprocess.run", return_value=fake
    ) as mrun:
        main(stdin=io.StringIO(_edit_envelope(tmp_path, target)),
             stderr=io.StringIO(), stdout=io.StringIO())
    assert "--json" in mrun.call_args.args[0]


# ── reason formatting ────────────────────────────────────────────────────────

def test_format_reason_includes_rule_and_trigger():
    reason = format_reason(json.loads(_payload("FAIL")))
    assert "introduce ORM" in reason
    assert "ORM" in reason
    assert "storage_json" in reason

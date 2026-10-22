"""C2b charter section 17 (Amendment 1): UNVERIFIABLE proceed delivery, A1-A10.

When a local declaration is present, authorization is
``AUTHORIZATION_UNVERIFIABLE`` and the hook exits 0, it writes exactly one
PreToolUse ``additionalContext`` object. In the warn-mode ``defer`` case the
text is appended to the defer reason instead (one object, delivery not
claimed). Exit codes, stderr and permission behavior are unchanged.

A10 (the C2a and C2b suites pass, apart from the stdout additions) is covered
by ``test_availability_c2a.py`` and ``test_availability_c2b.py``.
"""
from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from mneme import availability_authority as aa
from mneme.availability_authority import (
    AUTHORIZED, REVOKED, UNVERIFIABLE, VERIFIED_ABSENT, Verification,
)
from mneme.integrations.claude_code import availability, hook
from mneme.integrations.claude_code.availability import unverifiable_context
from tests.integrations.check_contract import check_result
from tests.integrations.claude_code.test_availability_c2b import ACTIVE_MEMORY, Baseline

MARKER = "c2b_am1_submitted_content_marker"
REASONS = (
    aa.NETWORK, aa.DNS, aa.TLS_IDENTITY_MISMATCH, aa.AUTH, aa.TIMEOUT,
    aa.VERIFIER_CRASH, aa.REF_MISSING, aa.HISTORY_INCOMPLETE, aa.EVIDENCE_INVALID,
    aa.VERIFIER_CONFIG_MISSING,
)
FORBIDDEN_WORDS = ("checked", "compliant", "safe", "verified edit", "approved",
                   "modified", "written", "you must", "do not", "please")


def _clean_env(monkeypatch):
    for name in ("MNEME_MEMORY", "MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE",
                 "MNEME_HOOK_CHECK_TRANSPORT"):
        monkeypatch.delenv(name, raising=False)


def _envelope(target: Path, content: str = f"{MARKER} = 1\n"):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write",
            "cwd": str(target.parent),
            "tool_input": {"file_path": str(target), "content": content}}


def _run(envelope, response="unset"):
    out, err = io.StringIO(), io.StringIO()
    if response == "unset":
        rc = hook.handle_event(envelope, stderr=err, stdout=out)
    else:
        with patch.object(hook, "_invoke_check", return_value=response):
            rc = hook.handle_event(envelope, stderr=err, stdout=out)
    return rc, out.getvalue(), err.getvalue()


def _objects(stdout: str) -> list[dict]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def _expected(reason: str, mismatch: bool = False) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "additionalContext": unverifiable_context(reason, mismatch)}}


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A repo with memory and a declaration; the verifier result is chosen per test."""
    _clean_env(monkeypatch)
    root = tmp_path / "repo"
    (root / ".mneme").mkdir(parents=True)
    (root / ".mneme" / "project_memory.json").write_bytes(ACTIVE_MEMORY)
    b = Baseline.__new__(Baseline)
    b.normalized, b.branch, b.events = "https://example.com/project", "main", []
    b.add_event("authorize")
    document = b.declaration()
    (root / ".mneme" / "availability.json").write_text(json.dumps(document), encoding="utf-8")

    def use(authorization=UNVERIFIABLE, reason=aa.NETWORK):
        result = Verification(authorization, reason if authorization == UNVERIFIABLE else "",
                              url=b.normalized, branch="main", tip="a" * 40,
                              baseline=document if authorization == AUTHORIZED else None)
        monkeypatch.setattr(availability, "live_verifier", lambda _d: result)
        return root
    return use


# A1: the shipped verifier, no Git repository, memory missing.
def test_a1_unverifiable_missing_memory_writes_one_object(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "availability.json").write_text(json.dumps({
        "schema": "mneme.availability/v1", "availability": "closed",
        "memory_path": ".mneme/project_memory.json"}), encoding="utf-8")
    rc, out, err = _run(_envelope(tmp_path / "service.py"))
    assert rc == 0
    assert _objects(out) == [_expected(aa.VERIFIER_CONFIG_MISSING)]
    assert out.count("\n") == 1
    assert err == (
        "mneme-hook: availability AUTHORIZATION_UNVERIFIABLE(VERIFIER_CONFIG_MISSING); "
        "evaluation=NOT_RUN; availability did not refuse.\n"
        "mneme-hook: canonical memory missing.\n"
        "mneme-hook: check not run\n"
    )


# A2: every closed-set reason, complete PASS.
@pytest.mark.parametrize("reason", REASONS)
def test_a2_each_reason_with_complete_pass(project, reason):
    root = project(UNVERIFIABLE, reason)
    rc, out, err = _run(_envelope(root / "service.py"), check_result("PASS"))
    assert rc == 0
    assert _objects(out) == [_expected(reason)]
    assert f"availability {UNVERIFIABLE}({reason}); evaluation=TRUSTED_COMPLETE" in err


# A3: SS-3 mismatch adds one sentence.
def test_a3_mismatch_sentence(project, tmp_path, monkeypatch):
    root = project(UNVERIFIABLE, aa.DNS)
    other = tmp_path / "other.json"
    other.write_bytes(ACTIVE_MEMORY)
    monkeypatch.setenv("MNEME_MEMORY", str(other))
    rc, out, err = _run(_envelope(root / "service.py"), check_result("PASS"))
    assert rc == 0
    assert _objects(out) == [_expected(aa.DNS, mismatch=True)]
    assert "SS-3 memory path mismatch" in err


# A4: a strict trusted FAIL still blocks; nothing on stdout.
def test_a4_strict_fail_exit_2_no_stdout(project):
    root = project(UNVERIFIABLE, aa.NETWORK)
    rc, out, err = _run(_envelope(root / "service.py"), check_result("FAIL"))
    assert (rc, out) == (2, "")
    assert "architectural decision violated" in err
    assert f"availability {UNVERIFIABLE}({aa.NETWORK})" in err


# A5: warn mode keeps one defer object, with the text appended to its reason.
def test_a5_warn_mode_single_defer_object(project, monkeypatch):
    root = project(UNVERIFIABLE, aa.TIMEOUT)
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    response = check_result("FAIL", mode="warn")
    rc, out, err = _run(_envelope(root / "service.py"), response)
    assert rc == 0
    objects = _objects(out)
    assert len(objects) == 1 and out.count("\n") == 1
    spec = objects[0]["hookSpecificOutput"]
    assert spec["permissionDecision"] == "defer"
    assert "additionalContext" not in spec
    original = hook.format_reason(json.loads(response.stdout))
    assert spec["permissionDecisionReason"] == original + "\n" + unverifiable_context(
        aa.TIMEOUT, False)


def test_a5_warn_mode_without_declaration_unchanged(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_bytes(ACTIVE_MEMORY)
    response = check_result("FAIL", mode="warn")
    rc, out, _ = _run(_envelope(tmp_path / "service.py"), response)
    (obj,) = _objects(out)
    assert rc == 0
    assert obj["hookSpecificOutput"]["permissionDecisionReason"] == hook.format_reason(
        json.loads(response.stdout))


# A6: AUTHORIZED refusals are unchanged: exit 2, empty stdout.
def test_a6_authorized_refusal_unchanged(project):
    root = project(AUTHORIZED)
    (root / ".mneme" / "project_memory.json").unlink()
    rc, out, err = _run(_envelope(root / "service.py"))
    assert (rc, out) == (2, "")
    assert "operational refusal (UNEVALUATED: MEMORY_MISSING)" in err


@pytest.mark.parametrize("response", [
    check_result("PASS", complete=False),
    subprocess.CompletedProcess([], 1, "Traceback", ""),
    None,
])
def test_a6_authorized_unavailable_refusals_unchanged(project, response):
    root = project(AUTHORIZED)
    rc, out, _ = _run(_envelope(root / "service.py"), response)
    assert (rc, out) == (2, "")


def test_a6_authorized_pass_proceeds_silently(project):
    root = project(AUTHORIZED)
    rc, out, _ = _run(_envelope(root / "service.py"), check_result("PASS"))
    assert (rc, out) == (0, "")


# A7: REVOKED and VERIFIED_ABSENT proceeds write nothing to stdout.
@pytest.mark.parametrize("authorization", [REVOKED, VERIFIED_ABSENT])
@pytest.mark.parametrize("memory", [True, False])
def test_a7_revoked_or_absent_no_stdout(project, authorization, memory):
    root = project(authorization)
    if not memory:
        (root / ".mneme" / "project_memory.json").unlink()
    rc, out, err = _run(_envelope(root / "service.py"), check_result("PASS"))
    assert (rc, out) == (0, "")
    assert "availability did not refuse." in err


# A8: no declaration means byte-identical behavior and no verifier call.
@pytest.mark.parametrize("memory", [True, False])
def test_a8_no_declaration_untouched(tmp_path, monkeypatch, memory):
    _clean_env(monkeypatch)
    (tmp_path / ".mneme").mkdir()
    if memory:
        (tmp_path / ".mneme" / "project_memory.json").write_bytes(ACTIVE_MEMORY)

    def forbidden(_declaration):
        raise AssertionError("the verifier must not run without a declaration")
    monkeypatch.setattr(availability, "live_verifier", forbidden)
    rc, out, err = _run(_envelope(tmp_path / "service.py"), check_result("PASS"))
    assert (rc, out, err) == (0, "", "")


# A9: content rules for every emitted text.
def _all_texts(project, tmp_path, monkeypatch) -> list[str]:
    texts = []
    for reason in REASONS:
        root = project(UNVERIFIABLE, reason)
        _, out, _ = _run(_envelope(root / "service.py"), check_result("PASS"))
        texts.append(_objects(out)[0]["hookSpecificOutput"]["additionalContext"])
    other = tmp_path / "other.json"
    other.write_bytes(ACTIVE_MEMORY)
    monkeypatch.setenv("MNEME_MEMORY", str(other))
    root = project(UNVERIFIABLE, aa.DNS)
    _, out, _ = _run(_envelope(root / "service.py"), check_result("PASS"))
    texts.append(_objects(out)[0]["hookSpecificOutput"]["additionalContext"])
    return texts


def test_a9_text_rules(project, tmp_path, monkeypatch):
    for text in _all_texts(project, tmp_path, monkeypatch):
        assert text.isascii()
        assert MARKER not in text
        assert "psycopg2" not in text and "C3-DEC" not in text and "d_ready" not in text
        assert str(tmp_path) not in text and "\\" not in text and "/" not in text
        lowered = text.lower()
        assert not any(word in lowered for word in FORBIDDEN_WORDS), text
        assert text.startswith("Mneme availability: authorization could not be verified")


def test_a9_stdout_is_one_json_line(project):
    root = project(UNVERIFIABLE, aa.AUTH)
    _, out, _ = _run(_envelope(root / "service.py"), check_result("PASS"))
    lines = out.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["hookSpecificOutput"].keys() == {"hookEventName",
                                                                 "additionalContext"}
    assert "permissionDecision" not in out and "systemMessage" not in out


def test_a9_empty_delta_skip_still_reports(project):
    """A SKIPPED proceed is still an exit-0 UNVERIFIABLE proceed (section 17.2)."""
    root = project(UNVERIFIABLE, aa.NETWORK)
    rc, out, _ = _run(_envelope(root / "service.py", content="  \n"))
    assert rc == 0 and _objects(out) == [_expected(aa.NETWORK)]

"""ADR-033 C2a routing, deterministic failure cases and default-open parity.

P1 compares the actual pre-C2a hook from pinned commit 78459d1a with the
current hook on the same envelope and checker response. The CI checkout has
full Git history. It is not merely a reimplementation of the expected output.
C2a never makes an availability refusal: authorized outcomes are seam-only.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

from mneme.integrations.claude_code import hook
from mneme.integrations.claude_code.availability import (
    SCHEMA, MEMORY_PATH, UNVERIFIABLE,
    classify_observation, discover_declaration, emit_availability,
    routing_refuses, verifier_stub,
)
from tests.integrations.check_contract import check_payload, check_result

BASELINE = "78459d1a30a98b7ce78cb2107a9e9d41e148e52d"
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "availability_policy" / "v1"


def _project(tmp_path, *, declaration=True, memory=True):
    directory = tmp_path / ".mneme"
    directory.mkdir(exist_ok=True)
    if declaration:
        (directory / "availability.json").write_bytes((FIXTURES / "valid.json").read_bytes())
    if memory:
        (directory / "project_memory.json").write_text('{"decisions": []}', encoding="utf-8")
    return tmp_path / "new.py"


def _envelope(target, *, tool="Write", **tool_input):
    data = {"file_path": str(target), "content": "value = 1\n"} | tool_input
    return {
        "hook_event_name": "PreToolUse", "tool_name": tool,
        "cwd": str(target.parent), "tool_input": data,
    }


def _invoke(envelope, *, response=None):
    out, err = io.StringIO(), io.StringIO()
    with patch.object(hook, "_invoke_check", return_value=response):
        rc = hook.handle_event(envelope, stderr=err, stdout=out)
    return rc, out.getvalue(), err.getvalue()


@pytest.fixture
def baseline_hook():
    """The pinned, pre-C2a hook is the byte-for-byte comparison oracle."""
    root = Path(__file__).resolve().parents[3]
    try:
        source = subprocess.check_output(
            ["git", "show", BASELINE + ":mneme/integrations/claude_code/hook.py"],
            cwd=root, text=True, stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("pinned pre-C2a baseline absent outside full Git checkout")
    name = "mneme.integrations.claude_code._c2a_pinned_baseline_hook"
    module = types.ModuleType(name)
    module.__file__ = str(root / "mneme/integrations/claude_code/hook.py")
    sys.modules[name] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    yield module
    sys.modules.pop(name, None)


@pytest.mark.parametrize("case", [
    "no_memory", "pass", "warn", "fail", "incomplete", "untrusted",
    "not_run", "materialize_failure", "empty_delta", "read",
])
def test_p1_no_declaration_byte_identical_to_pinned_baseline(
    case, tmp_path, monkeypatch, baseline_hook,
):
    """P1: outputs (including diagnostics) and return values do not change."""
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    monkeypatch.delenv("MNEME_HOOK_MODE", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_MODE", raising=False)
    target = _project(tmp_path, declaration=False, memory=case != "no_memory")
    envelope = _envelope(target)
    response = check_result("PASS")
    if case == "warn":
        response = check_result("WARN")
    elif case == "fail":
        response = check_result("FAIL")
    elif case == "incomplete":
        response = check_result("FAIL", complete=False)
    elif case == "untrusted":
        response = subprocess.CompletedProcess([], 1, "Traceback: bad memory", "")
    elif case == "not_run":
        response = None
    elif case == "materialize_failure":
        target.write_text("unrelated", encoding="utf-8")
        envelope = _envelope(
            target, tool="Edit", old_string="missing", new_string="new",
        )
    elif case == "empty_delta":
        envelope = _envelope(target, content="  \n")
    elif case == "read":
        envelope = _envelope(target, tool="Read")

    def execute(module):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(module, "_invoke_check", return_value=response):
            rc = module.handle_event(envelope, stderr=err, stdout=out)
        return rc, out.getvalue().encode(), err.getvalue().encode()

    assert execute(hook) == execute(baseline_hook)


def test_p2_no_declaration_never_opens_socket(tmp_path, monkeypatch):
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    _project(tmp_path, declaration=False)
    target = tmp_path / "new.py"
    import socket
    with patch.object(socket, "socket", side_effect=AssertionError("network used")):
        assert _invoke(_envelope(target), response=check_result("PASS")) == (0, "", "")


def test_policy_root_is_first_mneme_ancestor(tmp_path):
    root_target = _project(tmp_path)
    nested = tmp_path / "nested"
    (nested / ".mneme").mkdir(parents=True)
    # A nested policy root without a declaration hides the outer one.
    assert discover_declaration(nested) is None
    found = discover_declaration(root_target.parent)
    assert found is not None and found.memory_path == MEMORY_PATH


def test_d1_complete_pass_diagnostic(tmp_path):
    target = _project(tmp_path)
    rc, out, err = _invoke(_envelope(target), response=check_result("PASS"))
    assert (rc, out) == (0, "")
    assert "AUTHORIZATION_UNVERIFIABLE(VERIFIER_CONFIG_MISSING)" in err
    assert "evaluation=TRUSTED_COMPLETE" in err


def test_d2_trusted_fail_still_blocks(tmp_path):
    target = _project(tmp_path)
    rc, out, err = _invoke(_envelope(target), response=check_result("FAIL"))
    assert rc == 2 and out == ""
    assert "architectural decision violated" in err
    assert "AUTHORIZATION_UNVERIFIABLE" in err


def test_d3_missing_memory_reports_but_does_not_refuse(tmp_path):
    target = _project(tmp_path, memory=False)
    rc, out, err = _invoke(_envelope(target))
    assert (rc, out) == (0, "")
    assert "canonical memory missing" in err
    assert "evaluation=NOT_RUN" in err


@pytest.mark.parametrize("raw,problem", [
    ('{broken', "unreadable or invalid JSON"),
    ('{"availability":"closed"}', "invalid schema"),
    ((FIXTURES / "invalid.json").read_text(), "invalid availability"),
    (json.dumps({"schema": SCHEMA, "availability": "closed",
                 "memory_path": "../other.json"}), "invalid memory_path"),
])
def test_d4_invalid_declaration_reports_error(tmp_path, raw, problem):
    target = _project(tmp_path)
    (tmp_path / ".mneme" / "availability.json").write_text(raw, encoding="utf-8")
    rc, _, err = _invoke(_envelope(target), response=check_result("PASS"))
    assert rc == 0 and problem in err and UNVERIFIABLE in err


def test_d5_mneme_memory_override_is_mismatch(tmp_path, monkeypatch):
    target = _project(tmp_path)
    other = tmp_path / "other.json"
    other.write_text('{"decisions": []}', encoding="utf-8")
    monkeypatch.setenv("MNEME_MEMORY", str(other))
    rc, _, err = _invoke(_envelope(target), response=check_result("PASS"))
    assert rc == 0 and "SS-3 memory path mismatch" in err
    assert "not bound to declaration" in err


def test_d6_historical_payload_completeness_unstated(tmp_path):
    target = _project(tmp_path)
    historical = check_payload("PASS")
    historical.pop("evaluation_complete")
    result = subprocess.CompletedProcess([], 0, json.dumps(historical), "")
    rc, _, err = _invoke(_envelope(target), response=result)
    assert rc == 0 and "COMPLETENESS_UNSTATED" in err


def test_d7_incomplete_matched_violation_remains_partial(tmp_path):
    target = _project(tmp_path)
    rc, _, err = _invoke(_envelope(target), response=check_result("FAIL", complete=False))
    assert rc == 0
    assert "INCOMPLETE" in err and "1 violation(s) matched in a partial" in err
    assert "not a complete rule verdict" in err


@pytest.mark.parametrize("response,state", [
    (subprocess.CompletedProcess([], 1, "Traceback", ""), "UNTRUSTED"),
    (None, "NOT_RUN"),
])
def test_d8_untrusted_or_unavailable_does_not_refuse(tmp_path, response, state):
    target = _project(tmp_path)
    rc, _, err = _invoke(_envelope(target), response=response)
    assert rc == 0 and "evaluation=" + state in err


def test_d9_declaration_deletion_silently_disables_trigger(tmp_path):
    target = _project(tmp_path)
    (tmp_path / ".mneme" / "availability.json").unlink()
    assert _invoke(_envelope(target), response=check_result("PASS")) == (0, "", "")


def test_s1_all_authorization_routes_are_seam_only(tmp_path):
    target = _project(tmp_path)
    declaration = discover_declaration(target.parent)
    assert declaration is not None
    assert verifier_stub(declaration) == (
        "AUTHORIZATION_UNVERIFIABLE", "VERIFIER_CONFIG_MISSING",
    )
    for outcome in ("REVOKED", "VERIFIED_ABSENT", UNVERIFIABLE):
        assert not routing_refuses(outcome, "INCOMPLETE", missing_memory=True)
    assert routing_refuses("AUTHORIZED", "INCOMPLETE")
    assert routing_refuses("AUTHORIZED", "NOT_RUN", missing_memory=True)
    assert routing_refuses("AUTHORIZED", "TRUSTED_COMPLETE", invalid_declaration=True)
    assert routing_refuses("AUTHORIZED", "COMPLETENESS_UNSTATED")
    assert not routing_refuses("AUTHORIZED", "TRUSTED_COMPLETE")
    assert not routing_refuses("AUTHORIZED", "SKIPPED", missing_memory=True)
    err = io.StringIO()
    assert emit_availability(
        declaration, "INCOMPLETE", err,
        verifier=lambda _: ("AUTHORIZED", ""),
        memory=tmp_path / ".mneme" / "project_memory.json",
    )


def test_state_classifier_is_not_a_second_verdict_parser():
    assert classify_observation(None, not_run=True) == "NOT_RUN"
    assert classify_observation(None) == "UNTRUSTED"
    assert classify_observation({"verdict": "PASS"}) == "COMPLETENESS_UNSTATED"
    assert classify_observation({"evaluation_complete": False}) == "INCOMPLETE"
    assert classify_observation({"evaluation_complete": True}) == "TRUSTED_COMPLETE"

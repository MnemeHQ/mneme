"""ADR-033 C2a routing, deterministic failure cases and default-open parity.

P1 compares the actual pre-C2a hook from pinned commit 78459d1a with the
current hook on the same envelope and checker response. The CI checkout has
full Git history. It is not merely a reimplementation of the expected output.
C2a never makes an availability refusal: authorized outcomes are seam-only.

Comparison method (charter §7). The baseline is ``git show 78459d1a:
mneme/integrations/claude_code/hook.py`` compiled and executed as its own
module. Its imports (``session_state``, ``cli``, ``inprocess_check``, the
checker itself) resolve to the current tree, so parity is parity of the hook's
own logic under today's dependencies, which is what C2a changes. If the pinned
source cannot be read, the comparison is skipped locally but **fails under
CI** (``CI`` set), so missing baseline evidence is never silently green.

Checker coverage (charter §4, "real ``mneme check``"). The ``*_real_check``
tests run the real hook entry point (``hook.main`` over a stdin envelope) and
the real ``mneme check`` under both transports, with no ``_invoke_check``
patch. Patched checker responses remain only where the current CLI cannot
produce the state: a historical payload without ``evaluation_complete`` (D6),
and a launch failure or timeout (NOT_RUN, D8). The edge cases for content
materialization and empty deltas never reach the checker.
"""
from __future__ import annotations

import io
import json
import os
import socket
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


REAL_MEMORY = (Path(__file__).resolve().parent / "fixtures" / "project_memory.json").read_text(
    encoding="utf-8",
)
# A global literal rule (always applies) plus a path-scoped one. With a target
# outside this memory's root, the scoped rule is UNKNOWN, so the real checker
# returns a coherent incomplete payload that still carries the G1 violation.
MIXED_MEMORY = json.dumps({
    "meta": {"name": "c2a-mixed", "description": "global and path-scoped literal rules"},
    "decisions": [
        {"id": "G1", "decision": "Do not use psycopg2",
         "rules": [{"type": "FORBID_LITERAL", "value": "psycopg2"}]},
        {"id": "S1", "decision": "Scoped installer rule",
         "rules": [{"type": "FORBID_LITERAL", "value": "install legacy-client",
                    "include_paths": ["docs/**"]}]},
    ],
})
DIAG_PREFIX = (
    "mneme-hook: availability AUTHORIZATION_UNVERIFIABLE(VERIFIER_CONFIG_MISSING); "
)


def _diag(state, *extra):
    """The exact C2a diagnostic block emitted before any existing output."""
    lines = [DIAG_PREFIX + f"evaluation={state}; availability did not refuse."]
    lines.extend(extra)
    return "\n".join(lines) + "\n"


def _clean_env(monkeypatch):
    for name in ("MNEME_MEMORY", "MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE",
                 "MNEME_HOOK_CHECK_TRANSPORT"):
        monkeypatch.delenv(name, raising=False)


def _real_project(root, *, declaration=True, memory="real"):
    """A project whose memory the real ``mneme check`` evaluates."""
    directory = root / ".mneme"
    directory.mkdir(parents=True, exist_ok=True)
    if declaration:
        (directory / "availability.json").write_bytes((FIXTURES / "valid.json").read_bytes())
    if memory == "real":
        (directory / "project_memory.json").write_text(REAL_MEMORY, encoding="utf-8")
    elif memory == "malformed":
        (directory / "project_memory.json").write_text("{ not json", encoding="utf-8")
    return root / "service.py"


def _main(module, stdin_text):
    """The real hook entry point: an envelope on stdin, no checker patch."""
    out, err = io.StringIO(), io.StringIO()
    rc = module.main(stdin=io.StringIO(stdin_text), stdout=out, stderr=err)
    return rc, out.getvalue(), err.getvalue()


@pytest.fixture(params=["subprocess", "inprocess"])
def real_transport(request, monkeypatch):
    """Real-check cases hold under both checker transports (issue #60)."""
    _clean_env(monkeypatch)
    monkeypatch.setenv("MNEME_HOOK_CHECK_TRANSPORT", request.param)
    return request.param


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
        message = "pinned pre-C2a baseline 78459d1a is not readable from Git"
        if os.environ.get("CI"):
            pytest.fail(message + " (CI must provide full history; parity evidence missing)")
        pytest.skip(message + "; run in a full Git checkout")
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


@pytest.mark.parametrize("content,expected_rc", [
    ("import sqlite3\n", 0),
    ("import psycopg2\n", 2),
])
def test_p2_no_declaration_real_check_never_opens_socket(
    content, expected_rc, tmp_path, monkeypatch, baseline_hook,
):
    """P2: no declaration, sockets disabled, real ``mneme check`` in process.

    The in-process transport runs the real checker inside this interpreter, so
    the socket guard covers the C2a code path *and* the checker. (A socket
    patch cannot reach a checker in a child process, which is why this case
    pins ``MNEME_HOOK_CHECK_TRANSPORT=inprocess``.) Output must also equal the
    pinned baseline, so a swallowed socket error cannot hide as a fail-open.
    """
    _clean_env(monkeypatch)
    monkeypatch.setenv("MNEME_HOOK_CHECK_TRANSPORT", "inprocess")
    target = _real_project(tmp_path, declaration=False)
    stdin = json.dumps(_envelope(target, content=content))
    opened = []

    def _deny(*args, **kwargs):
        opened.append(args)
        raise OSError("network disabled by C2a P2")

    with patch.object(socket, "socket", side_effect=_deny):
        current = _main(hook, stdin)
    baseline = _main(baseline_hook, stdin)
    assert opened == []
    assert current[0] == expected_rc
    assert current == baseline


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


def test_d2_trusted_fail_blocks_exactly_as_baseline(tmp_path, monkeypatch, baseline_hook):
    """D2: same exit and the baseline's exact block text, plus only the
    availability diagnostic line in front of it."""
    _clean_env(monkeypatch)
    target = _project(tmp_path)
    envelope = _envelope(target)
    response = check_result("FAIL")
    rc, out, err = _invoke(envelope, response=response)
    with patch.object(baseline_hook, "_invoke_check", return_value=response):
        b_out, b_err = io.StringIO(), io.StringIO()
        b_rc = baseline_hook.handle_event(envelope, stderr=b_err, stdout=b_out)
    assert (rc, out) == (b_rc, b_out.getvalue()) == (2, "")
    assert err == _diag("TRUSTED_COMPLETE") + b_err.getvalue()


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


# ── real ``mneme check`` (charter §4): no _invoke_check patch ─────────────────

def _foreign_memory(tmp_path, text):
    """Memory under a different root, selected through MNEME_MEMORY."""
    other = tmp_path / "elsewhere" / ".mneme"
    other.mkdir(parents=True)
    path = other / "project_memory.json"
    path.write_text(text, encoding="utf-8")
    return path


def _real_case(case, tmp_path, monkeypatch, *, declaration):
    """Build a project for one real-check case; return the stdin envelope."""
    memory = {"crash": "malformed", "no_memory": None}.get(case, "real")
    target = _real_project(tmp_path / "repo", declaration=declaration, memory=memory)
    content = "import sqlite3\n"
    if case in ("fail", "incomplete"):
        content = "import psycopg2\n"
    if case == "incomplete":
        monkeypatch.setenv("MNEME_MEMORY", str(_foreign_memory(tmp_path, MIXED_MEMORY)))
    elif case == "mismatch":
        monkeypatch.setenv("MNEME_MEMORY", str(_foreign_memory(tmp_path, REAL_MEMORY)))
    return json.dumps(_envelope(target, content=content))


@pytest.mark.parametrize("case,expected_rc", [
    ("pass", 0), ("fail", 2), ("crash", 0), ("incomplete", 0), ("no_memory", 0),
])
def test_p1_real_check_no_declaration_byte_identical(
    case, expected_rc, tmp_path, monkeypatch, real_transport, baseline_hook,
):
    """P1 against the real checker: identical stdout, stderr and exit."""
    stdin = _real_case(case, tmp_path, monkeypatch, declaration=False)
    current = _main(hook, stdin)
    assert current == _main(baseline_hook, stdin)
    assert current[0] == expected_rc


MISMATCH = "mneme-hook: SS-3 memory path mismatch; evaluation not bound to declaration."


@pytest.mark.parametrize("case,expected_rc,diag", [
    # D1: complete PASS proceeds with the verification diagnostic.
    ("pass", 0, _diag("TRUSTED_COMPLETE")),
    # D2: a trusted strict FAIL blocks with the baseline's exact text.
    ("fail", 2, _diag("TRUSTED_COMPLETE")),
    # D3: missing memory; the checker is not run.
    ("no_memory", 0, _diag("NOT_RUN", "mneme-hook: canonical memory missing.",
                           "mneme-hook: check not run")),
    # D5: MNEME_MEMORY selects other memory; SS-3 mismatch named.
    ("mismatch", 0, _diag("TRUSTED_COMPLETE", MISMATCH)),
    # D7: real incomplete evaluation carrying a matched violation. Reaching
    # UNKNOWN applicability needs a target outside the memory's root, so this
    # case is also an SS-3 mismatch; both facts are reported.
    ("incomplete", 0, _diag(
        "INCOMPLETE", MISMATCH,
        "mneme-hook: 1 violation(s) matched in a partial evaluation, "
        "not a complete rule verdict: G1.",
    )),
    # D8: the real checker crashes on malformed memory; UNTRUSTED, proceed.
    ("crash", 0, _diag("UNTRUSTED")),
])
def test_d_real_check_diagnostic_then_exact_baseline_output(
    case, expected_rc, diag, tmp_path, monkeypatch, real_transport, baseline_hook,
):
    """With a declaration, the hook's output is exactly the C2a diagnostic
    followed by the pinned baseline's output for the same real check."""
    stdin = _real_case(case, tmp_path, monkeypatch, declaration=True)
    rc, out, err = _main(hook, stdin)
    b_rc, b_out, b_err = _main(baseline_hook, stdin)
    assert (rc, out) == (b_rc, b_out)
    assert rc == expected_rc
    assert err == diag + b_err


def test_d4_real_check_invalid_declaration(tmp_path, monkeypatch, real_transport, baseline_hook):
    stdin = _real_case("pass", tmp_path, monkeypatch, declaration=True)
    (tmp_path / "repo" / ".mneme" / "availability.json").write_text("{broken", encoding="utf-8")
    rc, out, err = _main(hook, stdin)
    b_rc, b_out, b_err = _main(baseline_hook, stdin)
    assert (rc, out) == (b_rc, b_out) == (0, "")
    assert err == _diag(
        "TRUSTED_COMPLETE", "mneme-hook: declaration invalid: unreadable or invalid JSON",
    ) + b_err


def test_d9_real_check_deleted_declaration_is_baseline(
    tmp_path, monkeypatch, real_transport, baseline_hook,
):
    stdin = _real_case("fail", tmp_path, monkeypatch, declaration=True)
    (tmp_path / "repo" / ".mneme" / "availability.json").unlink()
    assert _main(hook, stdin) == _main(baseline_hook, stdin)

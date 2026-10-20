"""#260: only a coherent ``mneme check --json`` result is a verdict.

``parse_verdict`` used to trust any payload with the right schema and a known
verdict. ``assess_verdict`` adds the checks that need stdout, exit status and
the requested mode together: envelope, violation records, aggregate
consistency, and process consistency. An incoherent result still fails open
(it proves enforcement failed, not that the edit violated policy), but loudly.

Incomplete path applicability (ADR-020) is exit 2 in either mode whatever the
nominal verdict, and must not be judged against the complete-result matrix.
"""
import io
import json
import subprocess
from unittest.mock import patch

import pytest

from mneme import cli
from mneme.integrations.claude_code import hook
from mneme.integrations.claude_code.hook import (
    assess_verdict,
    main,
    parse_verdict,
)
from tests.integrations.check_contract import (
    check_payload,
    exit_code,
    violation,
)
from tests.test_check_json import _scoped_memory
from tests.test_check_modes import (
    _FAIL_TEXT,
    _PASS_TEXT,
    _WARN_TEXT,
    _input,
    _memory,
)

MODES = ("strict", "warn")
VERDICTS = ("PASS", "WARN", "FAIL")


def _dump(payload):
    return json.dumps(payload)


def _assess(payload, returncode, mode="strict"):
    stdout = payload if isinstance(payload, str) else _dump(payload)
    return assess_verdict(stdout, returncode, mode)


def _assert_untrusted(assessment, fragment):
    assert assessment.payload is None
    assert assessment.inconsistent is True
    assert assessment.problem.startswith("inconsistent verdict payload (")
    assert fragment in assessment.problem
    assert "enforcement inactive" in assessment.problem


# ── valid results keep their existing meaning ───────────────────────────────

@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("verdict", VERDICTS)
def test_complete_result_with_contract_exit_code_is_trusted(mode, verdict):
    payload = check_payload(verdict, mode)
    assessment = _assess(payload, exit_code(verdict, mode), mode)
    assert assessment.payload == payload
    assert assessment.problem == ""
    assert assessment.inconsistent is False


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("verdict", VERDICTS)
def test_incomplete_result_exits_two_in_every_mode_and_is_trusted(mode, verdict):
    """The incomplete contract is exit 2 regardless of mode and verdict."""
    payload = check_payload(verdict, mode, complete=False)
    assessment = _assess(payload, 2, mode)
    assert assessment.payload == payload
    assert assessment.payload["evaluation_complete"] is False


def test_unknown_extra_keys_stay_permitted():
    payload = check_payload("FAIL")
    payload["future_field"] = {"anything": 1}
    payload["violations"][0]["future_detail"] = "x"
    assert _assess(payload, 2).payload == payload


def test_payload_without_optional_fields_is_trusted():
    """``evaluation_complete``, ``applicability`` and ``freshness`` predate or
    may postdate a consumer; their absence is not an inconsistency."""
    payload = {
        "schema": "mneme.check/v1",
        "verdict": "WARN",
        "mode": "strict",
        "violations": [violation("WARN")],
    }
    assert _assess(payload, 1).payload == payload


# ── unparseable output is reported as before ────────────────────────────────

@pytest.mark.parametrize("stdout", [
    "",
    "Traceback (most recent call last):\nValueError: bad memory",
    "[]",
    json.dumps({"schema": "mneme.check/v2", "verdict": "PASS"}),
    json.dumps({"schema": "mneme.check/v1", "verdict": "pass"}),
])
def test_unparseable_output_is_not_a_verdict(stdout):
    assessment = assess_verdict(stdout, 1, "strict")
    assert assessment.payload is None
    assert assessment.inconsistent is False
    assert assessment.problem == "no parseable verdict from mneme check (exit 1)"


@pytest.mark.parametrize("verdict", [["FAIL"], {"v": "FAIL"}, 2, None, True])
def test_non_string_verdict_fails_open_instead_of_raising(verdict):
    """An unhashable verdict used to raise TypeError from the set lookup."""
    stdout = _dump({"schema": "mneme.check/v1", "verdict": verdict})
    assert parse_verdict(stdout) is None


# ── envelope ────────────────────────────────────────────────────────────────

def _with(payload, **changes):
    payload = dict(payload)
    for key, value in changes.items():
        if value is _DROP:
            payload.pop(key, None)
        else:
            payload[key] = value
    return payload


_DROP = object()


@pytest.mark.parametrize("changes, fragment", [
    ({"mode": _DROP}, "missing or invalid mode"),
    ({"mode": "STRICT"}, "missing or invalid mode"),
    ({"mode": "audit"}, "missing or invalid mode"),
    ({"mode": None}, "missing or invalid mode"),
    ({"violations": _DROP}, "violations is not a list"),
    ({"violations": {"0": {}}}, "violations is not a list"),
    ({"freshness": None}, "freshness is not a list"),
    ({"freshness": "stale"}, "freshness is not a list"),
    ({"evaluation_complete": "false"}, "evaluation_complete is not a boolean"),
    ({"evaluation_complete": 0}, "evaluation_complete is not a boolean"),
    ({"applicability": {"outcome": "APPLIED"}}, "applicability is not a list"),
    ({"applicability": ["UNKNOWN"]}, "applicability is not a list"),
])
def test_malformed_envelope_is_untrusted(changes, fragment):
    payload = _with(check_payload("FAIL"), **changes)
    _assert_untrusted(_assess(payload, 2), fragment)


@pytest.mark.parametrize("requested, reported", [("strict", "warn"), ("warn", "strict")])
def test_mode_differing_from_requested_mode_is_untrusted(requested, reported):
    """A result for another mode answers a question nobody asked."""
    payload = check_payload("PASS", reported)
    _assert_untrusted(
        _assess(payload, 0, requested),
        f"mode {reported}, requested {requested}",
    )


def test_incomplete_flag_must_be_backed_by_an_unknown_trace():
    payload = check_payload("PASS", complete=False, applicability=[])
    _assert_untrusted(_assess(payload, 2), "evaluation_complete disagrees")


def test_unknown_trace_contradicts_a_complete_claim():
    payload = check_payload("PASS")
    payload["applicability"] = [{"outcome": "UNKNOWN"}]
    _assert_untrusted(_assess(payload, 0), "evaluation_complete disagrees")


# ── violation records ───────────────────────────────────────────────────────

@pytest.mark.parametrize("record, fragment", [
    ("not an object", "violation 0 is not an object"),
    (violation("FAIL", decision_id=""), "violation 0 has no decision_id"),
    (violation("FAIL", decision_id="   "), "violation 0 has no decision_id"),
    (violation("FAIL", decision_id=7), "violation 0 has no decision_id"),
    ({k: v for k, v in violation("FAIL").items() if k != "decision_text"},
     "violation 0 has no decision_text"),
    (violation("FAIL", decision_text=None), "violation 0 has no decision_text"),
    (violation("PASS"), "violation 0 has invalid severity"),
    (violation("fail"), "violation 0 has invalid severity"),
    (violation(["FAIL"]), "violation 0 has invalid severity"),  # unhashable
    (violation({"FAIL": 1}), "violation 0 has invalid severity"),
    (violation("FAIL", rule=""), "violation 0 has no rule"),
    (violation("FAIL", trigger=""), "violation 0 has no trigger"),
    (violation("FAIL", trigger=None) | {"trigger": None}, "violation 0 has no trigger"),
])
def test_malformed_violation_record_is_untrusted(record, fragment):
    payload = check_payload("FAIL", violations=[record])
    _assert_untrusted(_assess(payload, 2), fragment)


def test_empty_decision_text_is_permitted():
    """The CLI emits the decision's text verbatim; it may legitimately be ""."""
    payload = check_payload("FAIL", violations=[violation("FAIL", decision_text="")])
    assert _assess(payload, 2).payload == payload


def test_later_malformed_record_is_found():
    payload = check_payload(
        "FAIL", violations=[violation("FAIL"), violation("FAIL", rule="")],
    )
    _assert_untrusted(_assess(payload, 2), "violation 1 has no rule")


# ── aggregate consistency ───────────────────────────────────────────────────

@pytest.mark.parametrize("verdict, severities, returncode, fragment", [
    ("PASS", ["WARN"], 0, "PASS with 1 violation(s)"),
    ("PASS", ["FAIL", "FAIL"], 0, "PASS with 2 violation(s)"),
    ("WARN", [], 1, "WARN with no violations"),
    ("WARN", ["WARN", "FAIL"], 1, "WARN with a FAIL violation"),
    ("FAIL", [], 2, "FAIL with no FAIL violation"),
    ("FAIL", ["WARN"], 2, "FAIL with no FAIL violation"),
])
def test_verdict_contradicting_its_violations_is_untrusted(
    verdict, severities, returncode, fragment,
):
    payload = check_payload(
        verdict, violations=[violation(s) for s in severities],
    )
    _assert_untrusted(_assess(payload, returncode), fragment)


def test_fail_verdict_may_carry_warn_violations_too():
    payload = check_payload("FAIL", violations=[violation("WARN"), violation("FAIL")])
    assert _assess(payload, 2).payload == payload


def test_aggregate_rules_apply_to_incomplete_results_too():
    payload = check_payload("PASS", complete=False, violations=[violation("FAIL")])
    _assert_untrusted(_assess(payload, 2), "PASS with 1 violation(s)")


# ── process consistency ─────────────────────────────────────────────────────

_WRONG_EXITS = [
    (mode, verdict, rc)
    for mode in MODES
    for verdict in VERDICTS
    for rc in (0, 1, 2, 3, -1, 137)
    if rc != exit_code(verdict, mode)
]


@pytest.mark.parametrize("mode, verdict, returncode", _WRONG_EXITS)
def test_complete_result_with_wrong_exit_code_is_untrusted(mode, verdict, returncode):
    payload = check_payload(verdict, mode)
    _assert_untrusted(
        _assess(payload, returncode, mode),
        f"{verdict} with exit {returncode} in {mode} mode",
    )


def test_the_issue_case_pass_with_exit_one():
    """Verbatim from #260: the suite used to pin this as trusted."""
    payload = check_payload("PASS")
    assessment = _assess(payload, 1)
    _assert_untrusted(assessment, "PASS with exit 1 in strict mode")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("returncode", [0, 1, 3])
def test_incomplete_result_must_exit_two(mode, returncode):
    """Not judged by the complete matrix: warn-mode exit 0 is still wrong here."""
    payload = check_payload("PASS", mode, complete=False)
    _assert_untrusted(
        _assess(payload, returncode, mode),
        f"incomplete evaluation with exit {returncode}",
    )


@pytest.mark.parametrize("returncode", [None, "2", 2.0, True])
def test_missing_or_non_integer_exit_status_is_untrusted(returncode):
    payload = check_payload("FAIL")
    _assert_untrusted(_assess(payload, returncode), "exit status unavailable")


# ── diagnostics never echo proposed content ─────────────────────────────────

def test_diagnostic_does_not_echo_violation_content():
    secret = "SECRET_PROPOSED_CONTENT_9f3a"
    payload = check_payload(
        "PASS",
        violations=[violation("FAIL", rule=secret, trigger=secret, decision_text=secret)],
    )
    assessment = _assess(payload, 0)
    assert assessment.payload is None
    assert secret not in assessment.problem


def test_diagnostic_does_not_echo_an_arbitrary_mode_value():
    payload = check_payload("PASS")
    payload["mode"] = "SECRET_MODE_VALUE"
    assert "SECRET_MODE_VALUE" not in _assess(payload, 0).problem


# ── the hook's exit-code table cannot drift from the CLI's ──────────────────

def test_exit_code_table_matches_cli():
    cli_table = {
        mode: {severity.value: code for severity, code in by_verdict.items()}
        for mode, by_verdict in cli._EXIT_CODES_BY_MODE.items()
    }
    assert hook._EXIT_CODES_BY_MODE == cli_table


# ── the real CLI's results are all trusted (no regression on valid output) ──

def _real_check(argv, capsys):
    code = cli.main(argv)
    return capsys.readouterr().out, code


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("text, verdict", [
    (_PASS_TEXT, "PASS"), (_WARN_TEXT, "WARN"), (_FAIL_TEXT, "FAIL"),
])
def test_real_cli_complete_results_are_trusted(tmp_path, capsys, mode, text, verdict):
    mem, inp = _memory(tmp_path), _input(tmp_path, text)
    stdout, code = _real_check(
        ["check", "--memory", str(mem), "--input", str(inp),
         "--query", "storage", "--mode", mode, "--json"],
        capsys,
    )
    assessment = assess_verdict(stdout, code, mode)
    assert assessment.problem == ""
    assert assessment.payload["verdict"] == verdict


@pytest.mark.parametrize("mode", MODES)
def test_real_cli_incomplete_result_is_trusted(tmp_path, capsys, mode):
    repo = tmp_path / "repo"
    repo.mkdir()
    mem = _scoped_memory(repo)
    inp = _input(repo, "install legacy-client")
    stdout, code = _real_check(
        ["check", "--memory", str(mem), "--input", str(inp),
         "--target-path", str(tmp_path / "outside" / "guide.md"),
         "--query", "edit docs", "--mode", mode, "--json"],
        capsys,
    )
    assert code == 2
    assessment = assess_verdict(stdout, code, mode)
    assert assessment.problem == ""
    assert assessment.payload["evaluation_complete"] is False


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("text", [_PASS_TEXT, _WARN_TEXT, _FAIL_TEXT])
def test_contract_doubles_match_real_cli_shape(tmp_path, capsys, mode, text):
    """``tests/integrations/check_contract`` must not drift from the CLI."""
    mem, inp = _memory(tmp_path), _input(tmp_path, text)
    stdout, code = _real_check(
        ["check", "--memory", str(mem), "--input", str(inp),
         "--query", "storage", "--mode", mode, "--json"],
        capsys,
    )
    real = json.loads(stdout)
    double = check_payload(real["verdict"], mode)
    assert set(double) <= set(real)
    assert code == exit_code(real["verdict"], mode)
    for record in real["violations"]:
        assert set(violation(record["severity"])) <= set(record)


# ── end to end through the PreToolUse hook ──────────────────────────────────

def _edit(tmp_path):
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_text('{"decisions": []}')
    target = tmp_path / "x.py"
    target.write_text("import os\n", encoding="utf-8")
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


def _hook(tmp_path, payload, returncode):
    proc = subprocess.CompletedProcess([], returncode, _dump(payload), "")
    err, out = io.StringIO(), io.StringIO()
    with patch("mneme.integrations.claude_code.hook.subprocess.run", return_value=proc):
        rc = main(stdin=io.StringIO(_edit(tmp_path)), stderr=err, stdout=out)
    return rc, err.getvalue(), out.getvalue()


@pytest.mark.parametrize("payload, returncode, fragment", [
    (check_payload("FAIL"), 1, "FAIL with exit 1 in strict mode"),
    (check_payload("WARN"), 2, "WARN with exit 2 in strict mode"),
    (check_payload("FAIL", "warn"), 0, "mode warn, requested strict"),
    (check_payload("FAIL", violations=[violation("PASS")]), 2, "invalid severity"),
    (check_payload("WARN", violations=[violation("FAIL")]), 1, "WARN with a FAIL violation"),
    (check_payload("FAIL", complete=False), 1, "incomplete evaluation with exit 1"),
])
def test_contradictory_blocking_payload_never_blocks(tmp_path, payload, returncode, fragment):
    """An incoherent FAIL/WARN must not be enforced: fail open, loudly."""
    rc, err, out = _hook(tmp_path, payload, returncode)
    assert rc == 0
    assert out == ""
    assert "mneme-hook: inconsistent verdict payload (" in err
    assert fragment in err
    assert "Failing open" in err


@pytest.mark.parametrize("verdict, returncode, blocks", [
    ("PASS", 0, False), ("WARN", 1, True), ("FAIL", 2, True),
])
def test_coherent_strict_results_keep_existing_enforcement(
    tmp_path, verdict, returncode, blocks,
):
    rc, err, _out = _hook(tmp_path, check_payload(verdict), returncode)
    assert rc == (2 if blocks else 0)
    assert "inconsistent" not in err


@pytest.mark.parametrize("verdict", VERDICTS)
def test_coherent_warn_results_keep_existing_enforcement(tmp_path, monkeypatch, verdict):
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    rc, err, out = _hook(tmp_path, check_payload(verdict, "warn"), 0)
    assert rc == 0
    assert "inconsistent" not in err
    if verdict == "PASS":
        assert out == ""
    else:
        assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "defer"


def test_coherent_incomplete_result_keeps_applicability_diagnostic(tmp_path):
    rc, err, out = _hook(tmp_path, check_payload("FAIL", complete=False), 2)
    assert rc == 0
    assert out == ""
    assert "typed-rule path applicability is unknown" in err
    assert "inconsistent" not in err

"""Tests for `mneme check --json`.

The Claude Code hook cannot distinguish a policy verdict from a crash by exit
code alone: `mneme check --mode strict` returns 1 for a WARN verdict, and the
Python interpreter also returns 1 for an uncaught exception. `--json` gives
consumers a trusted, explicit verdict so they can fail open on anything they
cannot parse.
"""
import json
from pathlib import Path

from mneme.cli import main

from tests.test_check_modes import (
    _FAIL_TEXT,
    _PASS_TEXT,
    _WARN_TEXT,
    _input,
    _memory,
)


def _run_json(tmp_path, text, capsys, mode="strict"):
    mem = _memory(tmp_path)
    inp = _input(tmp_path, text)
    code = main(["check", "--memory", str(mem), "--input", str(inp),
                 "--query", "storage", "--mode", mode, "--json"])
    return code, json.loads(capsys.readouterr().out)


# ── payload is parseable and well-formed ─────────────────────────────────────

def test_json_output_is_sole_stdout_content(tmp_path, capsys):
    """Nothing may precede or follow the payload, or consumers cannot parse it."""
    _code, payload = _run_json(tmp_path, _FAIL_TEXT, capsys)
    assert payload["schema"] == "mneme.check/v1"


def test_json_declares_verdict_fail(tmp_path, capsys):
    _code, payload = _run_json(tmp_path, _FAIL_TEXT, capsys)
    assert payload["verdict"] == "FAIL"


def test_json_declares_verdict_warn(tmp_path, capsys):
    _code, payload = _run_json(tmp_path, _WARN_TEXT, capsys)
    assert payload["verdict"] == "WARN"


def test_json_declares_verdict_pass(tmp_path, capsys):
    _code, payload = _run_json(tmp_path, _PASS_TEXT, capsys)
    assert payload["verdict"] == "PASS"
    assert payload["violations"] == []


def test_json_echoes_mode(tmp_path, capsys):
    _code, payload = _run_json(tmp_path, _PASS_TEXT, capsys, mode="warn")
    assert payload["mode"] == "warn"


def test_json_violations_carry_decision_and_rule(tmp_path, capsys):
    _code, payload = _run_json(tmp_path, _FAIL_TEXT, capsys)
    v = payload["violations"][0]
    assert v["decision_id"] == "storage_json"
    assert v["severity"] == "FAIL"
    assert v["rule"] and v["trigger"] and v["decision_text"]


def test_json_identifies_typed_rule(tmp_path, capsys):
    mem = tmp_path / "project_memory.json"
    mem.write_text(json.dumps({
        "meta": {"name": "test", "description": "test"},
        "decisions": [{
            "id": "ADR-201",
            "decision": "Use the published distribution name",
            "rules": [{
                "type": "FORBID_LITERAL",
                "value": "pip install mneme",
            }],
        }],
    }), encoding="utf-8")
    inp = _input(tmp_path, "pip install mneme")
    code = main([
        "check", "--memory", str(mem), "--input", str(inp),
        "--query", "edit to README.md", "--json",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    [violation] = payload["violations"]
    assert violation["kind"] == "typed_rule"
    assert violation["rule_type"] == "FORBID_LITERAL"


def _scoped_memory(tmp_path):
    mem = tmp_path / ".mneme" / "project_memory.json"
    mem.parent.mkdir()
    mem.write_text(json.dumps({
        "meta": {"name": "test", "description": "test"},
        "decisions": [{
            "id": "ADR-020",
            "decision": "Scope the install rule",
            "rules": [{
                "type": "FORBID_LITERAL",
                "value": "install legacy-client",
                "include_paths": ["docs/**"],
                "exclude_paths": ["docs/generated/**"],
            }],
        }],
    }), encoding="utf-8")
    return mem


def test_json_target_path_controls_scoped_rule_applicability(tmp_path, capsys):
    mem = _scoped_memory(tmp_path)
    introduced = _input(tmp_path, "install legacy-client")
    target = tmp_path / "docs" / "guide.md"
    code = main([
        "check", "--memory", str(mem), "--input", str(introduced),
        "--target-path", str(target), "--query", "edit docs", "--json",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["evaluation_complete"] is True
    assert payload["applicability"] == [{
        "decision_id": "ADR-020",
        "rule_type": "FORBID_LITERAL",
        "rule_value": "install legacy-client",
        "rule_index": 0,
        "path_scoped": True,
        "input_path": "docs/guide.md",
        "outcome": "APPLIED",
        "selector": "docs/**",
        "reason": "an include selector matched",
    }]
    assert payload["violations"][0]["input_path"] == "docs/guide.md"


def test_json_unknown_applicability_is_operational_failure_even_warn_mode(
    tmp_path,
    capsys,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    mem = _scoped_memory(repo)
    introduced = _input(repo, "install legacy-client")
    outside = tmp_path / "outside" / "guide.md"
    code = main([
        "check", "--memory", str(mem), "--input", str(introduced),
        "--target-path", str(outside), "--query", "edit docs",
        "--mode", "warn", "--json",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["verdict"] == "PASS"
    assert payload["evaluation_complete"] is False
    assert payload["applicability"][0]["outcome"] == "UNKNOWN"


def test_human_output_includes_scoped_applicability_trace(tmp_path, capsys):
    mem = _scoped_memory(tmp_path)
    introduced = _input(tmp_path, "safe text")
    target = tmp_path / "docs" / "generated" / "guide.md"
    code = main([
        "check", "--memory", str(mem), "--input", str(introduced),
        "--target-path", str(target), "--query", "edit docs",
    ])
    out = capsys.readouterr().out
    assert code == 0
    assert "PATH  EXCLUDED" in out
    assert "docs/generated/guide.md via docs/generated/**" in out
    assert "Result: PASS" in out


# ── exit codes are unchanged by --json ───────────────────────────────────────

def test_json_preserves_strict_exit_codes(tmp_path, capsys):
    for text, expected in ((_PASS_TEXT, 0), (_WARN_TEXT, 1), (_FAIL_TEXT, 2)):
        code, _payload = _run_json(tmp_path, text, capsys)
        assert code == expected, f"{text!r} expected exit {expected}"


def test_json_preserves_warn_mode_exit_codes(tmp_path, capsys):
    for text in (_PASS_TEXT, _WARN_TEXT, _FAIL_TEXT):
        code, _payload = _run_json(tmp_path, text, capsys, mode="warn")
        assert code == 0


# ── human output is unaffected when --json is absent ─────────────────────────

def test_without_json_flag_output_stays_human_readable(tmp_path, capsys):
    mem = _memory(tmp_path)
    inp = _input(tmp_path, _FAIL_TEXT)
    main(["check", "--memory", str(mem), "--input", str(inp), "--query", "storage"])
    out = capsys.readouterr().out
    assert "Result: FAIL" in out
    assert "schema" not in out

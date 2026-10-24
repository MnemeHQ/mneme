"""ADR-034 G2-1: ``mneme check --proposed-new-file`` (checker side).

Pinned regression matrix of the accepted behavioral charter
(docs/plans/2026-10-24-adr-034-g2-1-behavioral-charter.md §8.C), items 1-4
and the checker half of item 10. Hook routing, consumer trust, hook outcomes,
evidence, untouched surfaces and the routed-hook half of item 10 live in
``tests/integrations/test_numeric_upper_bound_g2_hook.py``.

Built only from the public contract: ADR-034 §6a/§7a, the charter and the
G1 public regressions. No G2 validation material is used or implied.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from mneme import cli, enforcer, numeric_rule
from mneme.cli import main
from mneme.numeric_rule import NumericContract
from tests.canonical_fixtures import canonical_document

ROUTER = NumericContract(
    max="5",
    unit="seconds",
    symbol="ROUTER_DEADLINE_S",
    call_function="classify",
    call_position=1,
)
WITHIN = b"ROUTER_DEADLINE_S = 3\ndef run(x):\n    return classify(x, 2)\n"
ABOVE = b"ROUTER_DEADLINE_S = 60\ndef run(x):\n    return classify(x, 2)\n"


# ── helpers ──────────────────────────────────────────────────────────────────


def _numeric(include=("src/**",), exclude=()) -> dict:
    record = {
        "type": "FORBID_NUMERIC_ABOVE",
        "value": ROUTER.canonical_value(),
        "include_paths": list(include),
    }
    if exclude:
        record["exclude_paths"] = list(exclude)
    return record


LITERAL = {"type": "FORBID_LITERAL", "value": "psycopg2"}


def _project(root: Path, rules: list[dict]) -> Path:
    legacy = {
        "meta": {"name": "numeric-g2", "description": "ADR-034 G2-1 tests"},
        "items": [],
        "decisions": [
            {
                "id": f"ADR-00{index + 1}",
                "decision": f"Decision {index + 1}",
                "rationale": "test",
                "scope": ["router"],
                "rules": [rule],
                "created_at": "2026-10-24",
                "updated_at": "2026-10-24",
                "status": "active",
            }
            for index, rule in enumerate(rules)
        ],
    }
    memory = root / ".mneme" / "project_memory.json"
    memory.parent.mkdir(parents=True, exist_ok=True)
    memory.write_text(json.dumps(canonical_document(legacy)), encoding="utf-8")
    (root / "src").mkdir(exist_ok=True)
    return memory


def _carrier(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "carrier.txt"
    path.write_bytes(data)
    return path


def _run(capsys, memory: Path, flag: str, carrier: Path, target, *,
         mode="strict", json_out=True):
    argv = ["check", "--memory", str(memory), flag, str(carrier),
            "--query", "edit to src/new.py", "--mode", mode]
    if target is not None:
        argv += ["--target-path", str(target)]
    if json_out:
        argv.append("--json")
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _both(capsys, memory, carrier, target, **kw):
    proposed = _run(capsys, memory, "--proposed-new-file", carrier, target, **kw)
    legacy = _run(capsys, memory, "--input", carrier, target, **kw)
    return proposed, legacy


def _payload(out: str) -> dict:
    return json.loads(out)


def _trace(payload: dict) -> dict:
    traces = [
        item for item in payload["applicability"]
        if item["rule_type"] == "FORBID_NUMERIC_ABOVE"
    ]
    assert len(traces) == 1
    return traces[0]


def _symlink(src: Path, dst: Path, *, directory=False) -> None:
    try:
        os.symlink(src, dst, target_is_directory=directory)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")


# ── §8.C.1 legacy parity ─────────────────────────────────────────────────────


@pytest.mark.parametrize("rules", [
    pytest.param([LITERAL], id="no_numeric_rule"),
    pytest.param([_numeric(include=("lib/**",))], id="all_excluded_no_match"),
    pytest.param([_numeric(exclude=("src/**",))], id="all_excluded_by_exclude"),
])
@pytest.mark.parametrize("data", [ABOVE, b"import psycopg2\r\nX = 1\r\n", b""])
@pytest.mark.parametrize("mode,json_out", [("strict", True), ("warn", True), ("strict", False)])
def test_parity_when_no_numeric_rule_applies(tmp_path, capsys, rules, data, mode, json_out):
    memory = _project(tmp_path, rules)
    carrier = _carrier(tmp_path, data)
    target = tmp_path / "src" / "new.py"
    proposed, legacy = _both(capsys, memory, carrier, target, mode=mode, json_out=json_out)
    assert proposed == legacy
    if json_out:
        assert _payload(proposed[1]).get("subject", {}).get("input_kind") in (
            None, "unverified_input",
        )


def test_parity_when_every_numeric_rule_is_unknown(tmp_path, capsys, monkeypatch):
    """Path applicability UNKNOWN is never APPLIED: nothing is relabelled."""
    from mneme import path_selectors

    memory = _project(tmp_path, [_numeric()])
    carrier = _carrier(tmp_path, ABOVE)
    target = tmp_path / "src" / "new.py"
    real = path_selectors.evaluate_path_selectors

    def unknown(**kwargs):
        selection = real(**kwargs)
        return dataclasses.replace(
            selection, outcome=path_selectors.SelectorOutcome.UNKNOWN,
            input_path=None, reason="forced unknown",
        )

    monkeypatch.setattr(enforcer, "evaluate_path_selectors", unknown)
    proposed, legacy = _both(capsys, memory, carrier, target)
    assert proposed == legacy
    assert _trace(_payload(proposed[1]))["outcome"] == "UNKNOWN"
    assert _payload(proposed[1])["subject"]["input_kind"] == "unverified_input"


def _failed_precondition(tmp_path: Path, case: str) -> Path:
    src = tmp_path / "src"
    if case == "existing_file":
        target = src / "new.py"
        target.write_bytes(WITHIN)
    elif case == "existing_empty_file":
        target = src / "new.py"
        target.write_bytes(b"")
    elif case == "existing_directory":
        target = src / "new.py"
        target.mkdir()
    elif case == "symlink":
        real = src / "real.py"
        real.write_bytes(WITHIN)
        target = src / "new.py"
        _symlink(real, target)
    elif case == "dangling_link":
        target = src / "new.py"
        _symlink(src / "missing.py", target)
    elif case == "link_component":
        (tmp_path / "real_dir").mkdir()
        _symlink(tmp_path / "real_dir", src / "linked", directory=True)
        target = src / "linked" / "new.py"
    elif case == "dotdot_component":
        (src / "pkg").mkdir()
        target = Path(str(src / "pkg") + os.sep + ".." + os.sep + "new.py")
    elif case == "missing_parent":
        target = src / "not_yet" / "new.py"
    elif case == "parent_is_file":
        (src / "mod.py").write_bytes(b"")
        target = src / "mod.py" / "new.py"
    elif case == "out_of_root":
        outside = tmp_path.parent / f"{tmp_path.name}-outside"
        outside.mkdir(exist_ok=True)
        target = outside / "new.py"
    elif case == "non_python":
        target = src / "new.txt"
    elif case == "python_suffix_case":
        target = src / "new.PY"
    else:  # pragma: no cover
        raise AssertionError(case)
    return target


FAILED_PRECONDITIONS = [
    "existing_file", "existing_empty_file", "existing_directory", "symlink",
    "dangling_link", "link_component", "dotdot_component", "missing_parent",
    "parent_is_file", "out_of_root", "non_python", "python_suffix_case",
]


@pytest.mark.parametrize("case", FAILED_PRECONDITIONS)
@pytest.mark.parametrize("data", [ABOVE, b"import psycopg2\nX = 1\n"])
def test_parity_when_a_precondition_fails(tmp_path, capsys, case, data):
    project = tmp_path / "project"
    project.mkdir()
    memory = _project(project, [_numeric(include=("**",)), LITERAL])
    target = _failed_precondition(project, case)
    carrier = _carrier(tmp_path, data)
    proposed, legacy = _both(capsys, memory, carrier, target)
    assert proposed == legacy
    payload = _payload(proposed[1])
    assert payload["subject"]["input_kind"] == "unverified_input"
    trace = _trace(payload)
    if trace["outcome"] == "APPLIED":
        assert trace["primary_reason"] == "INCOMPLETE_SOURCE_INPUT"
    assert payload["verdict"] != "PASS" or payload["evaluation_complete"] is False


# ── §8.C.2 preconditions ─────────────────────────────────────────────────────


def test_positive_case_is_proposed_new_source(tmp_path, capsys):
    memory = _project(tmp_path, [_numeric()])
    carrier = _carrier(tmp_path, WITHIN)
    target = tmp_path / "src" / "new.py"
    code, out, _ = _run(capsys, memory, "--proposed-new-file", carrier, target)
    payload = _payload(out)
    assert code == 0 and payload["verdict"] == "PASS"
    assert payload["evaluation_complete"] is True
    subject = payload["subject"]
    assert list(subject) == [
        "input_kind", "subject_sha256", "source_path", "target_path",
        "memory_path", "governed_path", "absence_verified", "surface",
        "surface_version", "runtime",
    ]
    assert subject["input_kind"] == "proposed_new_source"
    assert subject["source_path"] is None
    assert Path(subject["target_path"]) == target.resolve()
    assert Path(subject["memory_path"]) == memory.resolve()
    assert subject["governed_path"] == "src/new.py"
    assert subject["absence_verified"] is True
    assert subject["surface"] == "mneme check"
    assert subject["runtime"] == numeric_rule.runtime_label()
    assert "target_path_declared" not in subject
    assert not target.exists()


def test_relative_target_resolves_against_the_checker_cwd(tmp_path, capsys, monkeypatch):
    memory = _project(tmp_path, [_numeric()])
    carrier = _carrier(tmp_path, ABOVE)
    monkeypatch.chdir(tmp_path)
    code, out, _ = _run(capsys, memory, "--proposed-new-file", carrier, "src/new.py")
    assert code == 2
    assert _payload(out)["subject"]["governed_path"] == "src/new.py"


def test_lstat_permission_error_is_not_absence(tmp_path, capsys, monkeypatch):
    memory = _project(tmp_path, [_numeric()])
    carrier = _carrier(tmp_path, ABOVE)
    target = tmp_path / "src" / "new.py"
    real = os.lstat

    def denied(path, *args, **kwargs):
        if Path(path).name == "new.py":
            raise PermissionError(13, "denied")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", denied)
    proposed, legacy = _both(capsys, memory, carrier, target)
    assert proposed == legacy
    assert _payload(proposed[1])["subject"]["input_kind"] == "unverified_input"


def test_lstat_other_os_error_is_not_absence(tmp_path, capsys, monkeypatch):
    memory = _project(tmp_path, [_numeric()])
    carrier = _carrier(tmp_path, ABOVE)
    target = tmp_path / "src" / "new.py"
    real = os.lstat

    def broken(path, *args, **kwargs):
        if Path(path).name == "new.py":
            raise OSError(5, "I/O error")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", broken)
    proposed, legacy = _both(capsys, memory, carrier, target)
    assert proposed == legacy


def test_windows_case_insensitive_parent_normalization(tmp_path, capsys):
    memory = _project(tmp_path, [_numeric()])
    carrier = _carrier(tmp_path, ABOVE)
    target = tmp_path / "SRC" / "new.py"
    proposed, legacy = _both(capsys, memory, carrier, target)
    payload = _payload(proposed[1])
    if sys.platform == "win32":
        # The same directory under normcase: precondition 2 holds.
        assert payload["subject"]["input_kind"] == "proposed_new_source"
        assert proposed[0] == 2 and payload["verdict"] == "FAIL"
    else:
        # A different (missing) directory on a case-sensitive file system.
        assert proposed == legacy


def test_missing_target_path_is_an_operational_error(tmp_path, capsys):
    memory = _project(tmp_path, [_numeric()])
    carrier = _carrier(tmp_path, ABOVE)
    code, out, err = _run(capsys, memory, "--proposed-new-file", carrier, None)
    assert code == 2 and out == ""
    assert err.startswith("ERROR: ") and "--target-path" in err


def test_proposed_new_file_is_mutually_exclusive_with_other_inputs(tmp_path):
    memory = _project(tmp_path, [_numeric()])
    carrier = _carrier(tmp_path, ABOVE)
    for other in ("--input", "--source-file"):
        with pytest.raises(SystemExit) as exc:
            main(["check", "--memory", str(memory), "--proposed-new-file", str(carrier),
                  other, str(carrier), "--query", "q"])
        assert exc.value.code == 2


def test_missing_carrier_is_an_operational_error(tmp_path, capsys):
    memory = _project(tmp_path, [_numeric()])
    code, out, err = _run(capsys, memory, "--proposed-new-file",
                          tmp_path / "absent.txt", tmp_path / "src" / "new.py")
    assert code == 2 and out == "" and err.startswith("ERROR: ")


INVALID_UTF8 = {
    "lone_continuation": b"X = 1\n\x80\n",
    "overlong": b"X = '\xc0\xaf'\n",
    "encoded_surrogate": b"X = '\xed\xa0\x80'\n",
    "truncated": b"X = '\xe2\x82'\n",
    "invalid_byte": b"\xff\xfe",
}


@pytest.mark.parametrize("name", sorted(INVALID_UTF8))
@pytest.mark.parametrize("case", [None, "existing_file", "non_python"])
@pytest.mark.parametrize("rules", [[_numeric()], [LITERAL]], ids=["numeric", "literal"])
def test_invalid_utf8_carrier_is_an_operational_error(tmp_path, capsys, name, case, rules):
    project = tmp_path / "project"
    project.mkdir()
    memory = _project(project, rules)
    target = project / "src" / "new.py" if case is None else _failed_precondition(project, case)
    carrier = _carrier(tmp_path, INVALID_UTF8[name])
    for mode in ("strict", "warn"):
        code, out, err = _run(capsys, memory, "--proposed-new-file", carrier, target, mode=mode)
        assert code == 2 and out == ""
        assert err.startswith("ERROR: ") and "UTF-8" in err


def test_invalid_utf8_legacy_inputs_are_unchanged(tmp_path, capsys):
    memory = _project(tmp_path, [_numeric()])
    carrier = _carrier(tmp_path, INVALID_UTF8["lone_continuation"])
    with pytest.raises(UnicodeDecodeError):
        _run(capsys, memory, "--input", carrier, tmp_path / "src" / "new.py")
    source = tmp_path / "src" / "module.py"
    source.write_bytes(INVALID_UTF8["lone_continuation"])
    code = main(["check", "--memory", str(memory), "--source-file", str(source),
                 "--query", "q", "--json"])
    captured = capsys.readouterr()
    assert code == 2 and captured.out == "" and "not valid UTF-8" in captured.err


# ── §8.C.3 binding guard ─────────────────────────────────────────────────────


def test_applicability_path_mismatch_is_an_operational_error(tmp_path, capsys, monkeypatch):
    memory = _project(tmp_path, [_numeric()])
    carrier = _carrier(tmp_path, ABOVE)
    real = cli.check_prompt

    def mismatched(*args, **kwargs):
        result = real(*args, **kwargs)
        subject = kwargs.get("subject")
        if subject is not None and subject.input_kind == "proposed_new_source":
            result.applicability = [
                dataclasses.replace(item, input_path="src/other.py")
                for item in result.applicability
            ]
        return result

    monkeypatch.setattr(cli, "check_prompt", mismatched)
    for mode in ("strict", "warn"):
        code, out, err = _run(capsys, memory, "--proposed-new-file", carrier,
                              tmp_path / "src" / "new.py", mode=mode)
        assert code == 2 and out == ""
        assert err.startswith("ERROR: ") and "governed path" in err


def test_binding_guard_also_runs_when_no_numeric_rule_applies(tmp_path, capsys, monkeypatch):
    """The guard belongs to the input kind, not to the numeric outcome."""
    memory = _project(tmp_path, [_numeric(include=("lib/**",))])
    carrier = _carrier(tmp_path, ABOVE)
    real = cli.check_prompt

    def mismatched(*args, **kwargs):
        result = real(*args, **kwargs)
        if kwargs.get("subject") is not None and kwargs["subject"].input_kind == "proposed_new_source":
            result.applicability = [
                dataclasses.replace(item, input_path="lib/other.py")
                for item in result.applicability
            ]
        return result

    monkeypatch.setattr(cli, "check_prompt", mismatched)
    code, out, _ = _run(capsys, memory, "--proposed-new-file", carrier,
                        tmp_path / "src" / "new.py")
    assert code == 2 and out == ""


# ── §8.C.4 numeric outcomes on proposed_new_source ───────────────────────────


@pytest.mark.parametrize("data,status,outcome,reason,verdict,complete,code", [
    (ABOVE, "RECOGNIZED", "VIOLATION", None, "FAIL", True, 2),
    (WITHIN, "RECOGNIZED", "NO_VIOLATION", None, "PASS", True, 0),
    (b"ROUTER_DEADLINE_S = 3\n", "MATCHER_UNEVALUATED", "UNEVALUATED",
     "SOURCE_NOT_FOUND", "PASS", False, 2),
    (b"ROUTER_DEADLINE_S = compute()\nclassify(x, 2)\n", "MATCHER_UNEVALUATED",
     "UNEVALUATED", "UNRECOGNIZED_FORM", "PASS", False, 2),
    (b"ROUTER_DEADLINE_S = 60\nclassify(x, y)\n", "PARTIAL", "VIOLATION",
     "UNRECOGNIZED_FORM", "FAIL", False, 2),
    (b"def broken(:\n", "MATCHER_UNEVALUATED", "UNEVALUATED", "PARSE_FAILURE",
     "PASS", False, 2),
    (b"\xef\xbb\xbf" + WITHIN, "MATCHER_UNEVALUATED", "UNEVALUATED", "PARSE_FAILURE",
     "PASS", False, 2),
], ids=["exceeds", "within", "source_not_found", "unsupported_form", "partial",
        "parse_failure", "leading_bom"])
def test_numeric_outcomes(tmp_path, capsys, data, status, outcome, reason, verdict,
                          complete, code):
    memory = _project(tmp_path, [_numeric()])
    carrier = _carrier(tmp_path, data)
    got, out, _ = _run(capsys, memory, "--proposed-new-file", carrier, tmp_path / "src" / "new.py")
    payload = _payload(out)
    trace = _trace(payload)
    assert payload["subject"]["input_kind"] == "proposed_new_source"
    assert (trace["matcher_status"], trace["matcher_outcome"], trace["primary_reason"]) == (
        status, outcome, reason
    )
    assert "INCOMPLETE_SOURCE_INPUT" not in json.dumps(payload)
    assert (payload["verdict"], payload["evaluation_complete"], got) == (verdict, complete, code)
    if status == "PARTIAL":
        assert trace["unknown_sources"] == [
            {"kind": "call", "line": 2, "reason": "UNRECOGNIZED_FORM"}
        ]
        assert [v["rule_type"] for v in payload["violations"]] == ["FORBID_NUMERIC_ABOVE"]


def test_warn_mode_keeps_the_exit_matrix(tmp_path, capsys):
    memory = _project(tmp_path, [_numeric()])
    target = tmp_path / "src" / "new.py"
    code, out, _ = _run(capsys, memory, "--proposed-new-file", _carrier(tmp_path, ABOVE),
                        target, mode="warn")
    assert code == 0 and _payload(out)["verdict"] == "FAIL"
    code, out, _ = _run(capsys, memory, "--proposed-new-file",
                        _carrier(tmp_path, b"ROUTER_DEADLINE_S = 60\nclassify(x, y)\n"),
                        target, mode="warn")
    assert code == 2 and _payload(out)["evaluation_complete"] is False


def test_human_output_uses_the_numeric_contract(tmp_path, capsys):
    memory = _project(tmp_path, [_numeric()])
    code, out, _ = _run(capsys, memory, "--proposed-new-file", _carrier(tmp_path, ABOVE),
                        tmp_path / "src" / "new.py", json_out=False)
    assert code == 2
    assert "must not exceed 5 seconds" in out and out.rstrip().endswith("Result: FAIL")


def test_literal_rules_keep_their_verdict_next_to_numeric(tmp_path, capsys):
    memory = _project(tmp_path, [_numeric(), LITERAL])
    carrier = _carrier(tmp_path, b"import psycopg2\n" + WITHIN)
    code, out, _ = _run(capsys, memory, "--proposed-new-file", carrier, tmp_path / "src" / "new.py")
    payload = _payload(out)
    assert code == 2 and payload["verdict"] == "FAIL"
    assert [v["decision_id"] for v in payload["violations"]] == ["ADR-002"]
    assert _trace(payload)["matcher_outcome"] == "NO_VIOLATION"


def test_excluded_target_makes_no_numeric_claim(tmp_path, capsys):
    memory = _project(tmp_path, [_numeric(exclude=("src/new.py",))])
    carrier = _carrier(tmp_path, ABOVE)
    proposed, legacy = _both(capsys, memory, carrier, tmp_path / "src" / "new.py")
    assert proposed == legacy
    trace = _trace(_payload(proposed[1]))
    assert trace["outcome"] == "EXCLUDED" and "matcher_status" not in trace


def test_one_applied_rule_among_excluded_ones_relabels(tmp_path, capsys):
    memory = _project(tmp_path, [_numeric(include=("lib/**",)), _numeric()])
    code, out, _ = _run(capsys, memory, "--proposed-new-file", _carrier(tmp_path, ABOVE),
                        tmp_path / "src" / "new.py")
    payload = _payload(out)
    assert code == 2 and payload["subject"]["input_kind"] == "proposed_new_source"
    outcomes = sorted(
        item["outcome"] for item in payload["applicability"]
        if item["rule_type"] == "FORBID_NUMERIC_ABOVE"
    )
    assert outcomes == ["APPLIED", "EXCLUDED"]


def test_output_is_deterministic(tmp_path, capsys):
    memory = _project(tmp_path, [_numeric()])
    carrier = _carrier(tmp_path, ABOVE)
    target = tmp_path / "src" / "new.py"
    first = _run(capsys, memory, "--proposed-new-file", carrier, target)
    second = _run(capsys, memory, "--proposed-new-file", carrier, target)
    assert first == second


# ── §8.C.10 byte contract (checker) ──────────────────────────────────────────

BYTE_CASES = {
    "lf": b"ROUTER_DEADLINE_S = 60\nclassify(x, 2)\n",
    "crlf": b"ROUTER_DEADLINE_S = 60\r\nclassify(x, 2)\r\n",
    "lone_cr": b"ROUTER_DEADLINE_S = 60\rclassify(x, 2)\r",
    "mixed": b"ROUTER_DEADLINE_S = 60\r\nclassify(x, 2)\rY = 1\n",
    "bom": b"\xef\xbb\xbfROUTER_DEADLINE_S = 60\nclassify(x, 2)\n",
    "non_ascii": (
        "# résumé — 日本\nété = 'über'\n"
        "ROUTER_DEADLINE_S = 60\nclassify(x, 2)\n"
    ).encode("utf-8"),
    "empty": b"",
}


@pytest.fixture
def spy(monkeypatch):
    """Record what the matcher and the literal rules actually receive."""
    seen: dict = {"source": [], "text": []}
    real_eval = numeric_rule.evaluate_source
    real_check = cli.check_prompt

    def evaluate_source(contract, source):
        seen["source"].append(source)
        return real_eval(contract, source)

    def check_prompt(input_text, *args, **kwargs):
        seen["text"].append(input_text)
        return real_check(input_text, *args, **kwargs)

    monkeypatch.setattr(numeric_rule, "evaluate_source", evaluate_source)
    monkeypatch.setattr(cli, "check_prompt", check_prompt)
    return seen


@pytest.mark.parametrize("name", sorted(BYTE_CASES))
def test_byte_contract_on_proposed_new_source(tmp_path, capsys, spy, name):
    data = BYTE_CASES[name]
    memory = _project(tmp_path, [_numeric()])
    carrier = _carrier(tmp_path, data)
    code, out, _ = _run(capsys, memory, "--proposed-new-file", carrier, tmp_path / "src" / "new.py")
    payload = _payload(out)
    digest = hashlib.sha256(data).hexdigest()
    assert carrier.read_bytes() == data
    assert payload["subject"]["input_kind"] == "proposed_new_source"
    assert payload["subject"]["subject_sha256"] == digest
    assert _trace(payload)["subject_sha256"] == digest
    # The matcher and the literal rules see the same strict decoding of the
    # exact bytes: no newline translation, no byte-order-mark stripping.
    assert spy["source"] == [data.decode("utf-8")]
    assert spy["text"] == [data.decode("utf-8")]
    trace = _trace(payload)
    if name == "bom":
        assert (trace["matcher_status"], trace["primary_reason"]) == (
            "MATCHER_UNEVALUATED", "PARSE_FAILURE"
        )
        assert code == 2 and payload["evaluation_complete"] is False
    elif name == "empty":
        assert trace["primary_reason"] == "SOURCE_NOT_FOUND"
    else:
        assert (trace["matcher_status"], trace["matcher_outcome"]) == ("RECOGNIZED", "VIOLATION")


@pytest.mark.parametrize("name", sorted(BYTE_CASES))
def test_byte_contract_parity_cases_match_input(tmp_path, capsys, spy, name):
    data = BYTE_CASES[name]
    memory = _project(tmp_path, [_numeric(include=("lib/**",)), LITERAL])
    carrier = _carrier(tmp_path, data)
    proposed, legacy = _both(capsys, memory, carrier, tmp_path / "src" / "new.py")
    assert proposed == legacy
    # The legacy result evaluates read_text's universal-newline decoding.
    assert spy["text"][-1] == spy["text"][-2] == carrier.read_text(encoding="utf-8")


def test_coding_declaration_never_redecodes_the_subject(tmp_path, capsys, spy):
    """Strict UTF-8 decides the text; a PEP 263 cookie cannot change it."""
    data = "# -*- coding: latin-1 -*-\nROUTER_DEADLINE_S = 60\nclassify(x, 2)\n".encode("utf-8")
    memory = _project(tmp_path, [_numeric()])
    code, out, _ = _run(capsys, memory, "--proposed-new-file", _carrier(tmp_path, data),
                        tmp_path / "src" / "new.py")
    assert spy["source"] == [data.decode("utf-8")]
    assert code == 2 and _trace(_payload(out))["matcher_outcome"] == "VIOLATION"


def test_complete_source_file_keeps_its_byte_snapshot(tmp_path, capsys, spy):
    """G1 is unchanged: ``--source-file`` still hands the matcher bytes."""
    memory = _project(tmp_path, [_numeric()])
    source = tmp_path / "src" / "module.py"
    source.write_bytes(BYTE_CASES["bom"])
    code = main(["check", "--memory", str(memory), "--source-file", str(source),
                 "--query", "q", "--json"])
    capsys.readouterr()
    assert spy["source"] == [BYTE_CASES["bom"]] and code == 2


def test_crlf_literal_is_matched_on_the_exact_text(tmp_path, capsys):
    memory = _project(tmp_path, [_numeric(), LITERAL])
    data = b"import psycopg2\r\n" + BYTE_CASES["crlf"]
    code, out, _ = _run(capsys, memory, "--proposed-new-file", _carrier(tmp_path, data),
                        tmp_path / "src" / "new.py")
    payload = _payload(out)
    assert code == 2
    assert {v["decision_id"] for v in payload["violations"]} == {"ADR-001", "ADR-002"}

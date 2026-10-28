"""R3 corpus-admission positive control, independent synthetic data only.

This is a structural test of the *coverage and verdict logic*. It is not a
blind Mneme evaluation: the observation tuples are contract-authored synthetic
expectations, and G1-G8 pass results are fabricated expressly to exercise
gates.decide. No sealed author files or implementation output are consulted.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.adr034_g2_1_r3 import contract as C
from benchmarks.adr034_g2_1_r3 import coverage, gates, oracle, public_smoke, synthetic


def _public_archive(tmp_path: Path) -> dict:
    """Verify a separately archived, synthetic public smoke set."""
    root = "r3-public-smoke"
    files = {
        f"{cls.lower()}/case.json": json.dumps({
            "case_id": f"synthetic-public-{cls}",
            "schema": C.CASE_SCHEMA,
            "visibility": "public",
            "cls": cls,
        }, sort_keys=True).encode("utf-8")
        for cls in C.CLASS_FLOORS
    }
    manifest = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n"
        for name, data in sorted(files.items())
    ).encode("ascii")
    files["MANIFEST.sha256"] = manifest
    archive = tmp_path / "synthetic-public.tar"
    with tarfile.open(archive, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(f"{root}/{name}")
            info.size = len(data)
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    attestation = public_smoke.verify(archive, expected_sha256=digest)
    assert attestation["verified"]
    assert attestation["public_cases"] == len(C.CLASS_FLOORS)
    return attestation


def _num_rule(adr_id: str, *, include: str, exclude: str | None = None,
              call: bool = False, symbol: str = "LIMIT_S") -> dict:
    source = [
        "- FORBID_NUMERIC_ABOVE:", "    language: python",
    ]
    if call:
        source += ["    call:", "      function: check", "      position: 0"]
    else:
        source += [f"    symbol: {symbol}"]
    source += [
        "    max: 5", "    inclusive: true", "    unit: seconds",
        "    include_paths:", f'      - "{include}"',
    ]
    if exclude:
        source += ["    exclude_paths:", f'      - "{exclude}"']
    return synthetic._adr(adr_id, f"Synthetic numeric {adr_id[4:]}", "\n".join(source) + "\n")


def _literal_rule(adr_id: str, value: str) -> dict:
    return synthetic._adr(adr_id, f"Synthetic literal {adr_id[4:]}",
                          f"- FORBID_LITERAL: {value}\n")


def _fixture_rules(files: list[dict]) -> list[oracle.Rule]:
    """Parse synthetic fixture ADRs under the same memory contract as R3."""
    return oracle.fixture_rules({
        "fixture": {"files": files, "memory": {"compile_from": "docs/adr"}}
    })


def _case(tmp_path: Path, cls: str, i: int) -> tuple[dict, SimpleNamespace, dict]:
    root = tmp_path / f"{cls}-{i}" / "root"
    outside = tmp_path / f"{cls}-{i}" / "outside"
    (root / "src").mkdir(parents=True)
    outside.mkdir(parents=True)
    target_base, target_rel = "root", "src/new.py"
    content = "LIMIT_S = 3\n"
    pre = {"kind": "absent"}
    fixture_files = []
    numeric_outcomes = {}
    applied = []
    literals = []
    mode, cause, disposition = "strict", "none", "proceeded"
    trusted, checker_subject, record_subject = True, "proposed_new_source", "proposed_new_source"

    if cls == "L":
        # Two fixture-distinct cases for each of R1's nine L subtypes.
        kind = i // 2
        if kind == 0:
            target_rel = "src/existing.py"
            (root / target_rel).write_text("a=1" if i % 2 else "a=2")
            pre = {"kind": "file"}
            fixture_files.append({"base": "root", "path": target_rel, "type": "file",
                                  "text": "a=1" if i % 2 else "a=2"})
        elif kind == 1:
            target_rel = "src/existing_empty.py"
            (root / target_rel).write_text("")
            pre = {"kind": "file"}
            fixture_files.append({"base": "root", "path": target_rel, "type": "file", "text": ""})
            # R1 A1.2: blank content cannot be a routed V, but is valid
            # byte variety on a legacy/unrouted L event.
            content = ""
        elif kind == 2:
            target_rel = f"src/link{i}.py"
            (root / "src" / f"actual{i}.py").write_text("a=1")
            (root / target_rel).symlink_to(f"actual{i}.py")
            pre = {"kind": "symlink"}
        elif kind == 3:
            target_rel = f"src/dangling{i}.py"
            (root / target_rel).symlink_to(f"missing-{i}.py")
            pre = {"kind": "symlink"}
        elif kind == 4:
            (root / "real").mkdir()
            (root / f"alias{i}").symlink_to("real", target_is_directory=True)
            target_rel = f"alias{i}/new.py"
        elif kind == 5:
            target_base, target_rel = "outside", f"outside{i}.py"
        elif kind == 6:
            target_rel = f"src/nonpython{i}.txt"
        elif kind == 7:
            target_rel = f"missing{i}/nested/new.py"
        elif kind == 8:
            content = "bad=" + "\ud800"  # deliberately unencodable
        trusted, checker_subject, record_subject = False, "absent", None
    elif cls == "AT":
        sub = [s for s, n in C.AT_SUBCLASS_FLOORS.items() for _ in range(n)][i]
        mode = "warn" if sub == "AT-W0" else "strict"
        cause = "other_rule"
        disposition = "deferred" if sub == "AT-W0" else "refused"
        lit_value = ("eval(" if i % 2 == 0 else "exec(")
        lit = _literal_rule(f"ADR-{9800+i}", lit_value)
        fixture_files.append(lit)
        literals = [(r.rule_id, r.rule_type) for r in _fixture_rules([lit])]
        content = f"result = {lit_value}1)\n"
        # Both AT-SI cases have different literal IDs *and* include scopes.
        if sub == "AT-SI":
            fixture_files.append(_num_rule(f"ADR-{9900+i}", include=f"lib{i}/**"))
            checker_subject = "unverified_input"
        elif sub == "AT-SX":
            target_rel = f"src/excluded{i}/new.py"
            (root / f"src/excluded{i}").mkdir()
            fixture_files.append(_num_rule(
                f"ADR-{9900+i}", include="src/**", exclude=f"src/excluded{i}/**"))
            checker_subject = "unverified_input"
        elif sub == "AT-W0" and i % 2:
            fixture_files.append(_num_rule(f"ADR-{9900+i}", include=f"elsewhere{i}/**"))
            checker_subject = "unverified_input"
        trusted, record_subject = False, None
        if sub == "AT-S0" or (sub == "AT-W0" and i % 2 == 0):
            checker_subject = "absent"
    elif cls == "LIT":
        # The literal and numeric labels must be backed by real, distinct
        # synthetic ADR fixtures; fabricated rule IDs cannot establish this.
        lit = _literal_rule(f"ADR-{9600+i}", "eval(")
        fixture_files.append(lit)
        literals = [(r.rule_id, r.rule_type) for r in _fixture_rules([lit])]
        content = "result = eval('1')\n"
        if i < 4:
            num = _num_rule(f"ADR-{9610+i}", include="src/**")
            fixture_files.append(num)
            rule = next(r for r in _fixture_rules([num]) if r.rule_type == C.NUMERIC)
            applied = [rule.rule_id]
            violated = i < 2
            content = f"LIMIT_S = {8 if violated else 3}\n" + content
            numeric_outcomes = {rule.rule_id: {
                "matcher_status": "RECOGNIZED",
                "matcher_outcome": "VIOLATION" if violated else "NO_VIOLATION",
                "primary_reason": None, "unknown_reasons": [],
            }}
            cause = "numeric_violation" if violated else "other_rule"
        else:
            cause = "other_rule"
        disposition = "refused"
    elif cls == "SC":
        fixture_files.append(_num_rule(f"ADR-97{i:02}", include="src/**", call=True))
        rule = next(r for r in _fixture_rules(fixture_files) if r.rule_type == C.NUMERIC)
        applied = [rule.rule_id]
        if i < 2:
            status, outcome, reason = "RECOGNIZED", "VIOLATION", None
        elif i < 4:
            status, outcome, reason = "RECOGNIZED", "NO_VIOLATION", None
        else:
            status, outcome, reason = "MATCHER_UNEVALUATED", "UNEVALUATED", "AMBIGUOUS_BINDING"
        numeric_outcomes = {rule.rule_id: {
            "matcher_status": status, "matcher_outcome": outcome,
            "primary_reason": reason, "unknown_reasons": [reason] if reason else [],
        }}
        content = ("def check(x): return x\ncheck(7)\n" if i < 2
                   else "def check(x): return x\ncheck(3)\n" if i < 4
                   else "def check(x): return x\ndef wrapper(check):\n    return check(3)\n")
        if i < 4:
            disposition = "refused" if i < 2 else "proceeded"
            cause = "numeric_violation" if i < 2 else "none"
    elif cls == "MR":
        # §7b genuinely has two APPLIED numeric rules with distinct
        # declaration sources; their IDs are derived from typed ADRs.
        a_adr = _num_rule(f"ADR-{9500+i*2}", include="src/**", symbol="LIMIT_S")
        b_adr = _num_rule(f"ADR-{9501+i*2}", include="src/**", symbol="OTHER_S")
        fixture_files.extend([a_adr, b_adr])
        applied = [next(r.rule_id for r in _fixture_rules([adr])
                        if r.rule_type == C.NUMERIC) for adr in (a_adr, b_adr)]
        numeric_outcomes = {}
        content = "LIMIT_S = 8\n" if i in (0, 1) else "LIMIT_S = 3\n"
        if i in (1, 2):
            content += "OTHER_S = 3\n"
        if i in (3, 4):
            lit = _literal_rule(f"ADR-{9570+i}", "eval(")
            fixture_files.append(lit)
            literals = [(r.rule_id, r.rule_type) for r in _fixture_rules([lit])]
            content += "result = eval('1')\n"
        if i == 0:
            statuses = [("RECOGNIZED", "VIOLATION"), ("MATCHER_UNEVALUATED", "UNEVALUATED")]
            event_relevance, complete = True, False
            disposition, cause = "refused", "numeric_violation"
        elif i == 1:
            statuses = [("RECOGNIZED", "VIOLATION"), ("RECOGNIZED", "NO_VIOLATION")]
            event_relevance, complete = True, True
            disposition, cause = "refused", "numeric_violation"
        elif i == 2:
            statuses = [("RECOGNIZED", "NO_VIOLATION"), ("RECOGNIZED", "NO_VIOLATION")]
            event_relevance, complete = True, True
        else:
            statuses = [("RECOGNIZED", "NO_VIOLATION"), ("MATCHER_UNEVALUATED", "UNEVALUATED")]
            event_relevance, complete = (i >= 5), False
            if i in (3, 4):
                disposition, cause = "refused", "other_rule"
        for rid, (status, outcome) in zip(applied, statuses):
            numeric_outcomes[rid] = {"matcher_status": status, "matcher_outcome": outcome,
                                     "primary_reason": None if status == "RECOGNIZED" else "SOURCE_NOT_FOUND",
                                     "unknown_reasons": [] if status == "RECOGNIZED" else ["SOURCE_NOT_FOUND"]}
    if cls == "MR":
        rule_relevance = {rid: event_relevance and (i == 2 or rid == applied[0])
                          for rid in applied}
    elif cls == "LIT":
        event_relevance, complete = i < 2, True
        rule_relevance = {rid: event_relevance for rid in applied}
    elif cls == "SC":
        event_relevance, complete = i < 4, i < 4
        rule_relevance = {rid: event_relevance for rid in applied}
    else:
        rule_relevance = {rid: False for rid in applied}
        event_relevance, complete = False, True

    if cls == "V" and i < 8:
        content = ["x\n", "y\n", "x\r\n", "y\r\n",
                   "x\r", "y\r", "é", "ñ"][i]

    target = (root if target_base == "root" else outside) / target_rel
    case = {
        "case_id": f"synthetic-{cls}-{i}",
        "cls": cls,
        "subclass": ([s for s, n in C.AT_SUBCLASS_FLOORS.items()
                      for _ in range(n)][i] if cls == "AT" else None),
        "visibility": "concealed",
        "fixture": {
            "files": fixture_files,
            "memory": {"compile_from": "docs/adr", "path": ".mneme/project_memory.json"},
        },
        "event": {
            "content": content,
            "target": {"base": target_base, "path": target_rel},
        },
    }
    exp = SimpleNamespace(
        root=str(root), target=str(target), governed_path=target_rel,
        routed=cls != "L", trusted_proposed=trusted,
        literal_violations=literals, numeric_outcomes=numeric_outcomes,
        applied_rule_ids=applied, mode=mode, cause=cause,
        disposition=disposition, checker_subject_kind=checker_subject,
        record_subject=record_subject, event_relevance=event_relevance,
        per_rule_relevance=rule_relevance, evaluation_complete=complete,
    )
    return case, exp, {"pre": pre}


def _synthetic_admission(tmp_path: Path):
    public_evidence = _public_archive(tmp_path)
    cases, passes = [], {}
    for cls, count in C.CLASS_FLOORS.items():
        for i in range(count):
            case, expected, observed = _case(tmp_path, cls, i)
            cases.append(case)
            passes[case["case_id"]] = [(expected, observed)]
    return cases, passes, public_evidence


def _success_results(cases: list) -> list:
    # These fabricated gate outcomes test the corpus verdict aggregator only.
    return [
        {"case_id": c["case_id"], "cls": c["cls"],
         "subclass": c.get("subclass"), "visibility": "concealed",
         "passed": True,
         "gates": {name: {"applies": True, "result": "pass", "failures": []}
                   for name in C.GATES}}
        for c in cases
    ]


def test_synthetic_concealed_only_coverage_positive_and_verdict_pass(tmp_path):
    try:
        cases, passes, public_evidence = _synthetic_admission(tmp_path)
    except OSError as exc:
        # Some Windows hosts cannot create symbolic links without privilege.
        pytest.skip(f"symlink capability unavailable: {type(exc).__name__}")

    assert len(cases) == C.TOTAL_FLOOR == 128
    assert all(c["visibility"] == "concealed" for c in cases)
    assert public_evidence["verified"] and public_evidence["public_cases"] == 14
    coverage_result = coverage.inspect(cases, passes, public_evidence)
    assert coverage_result["met"], coverage_result["shortfalls"]
    assert coverage_result["shortfalls"] == []
    floor = gates.floors(cases, passes, public_evidence)
    assert floor["met"] and floor["coverage"]["met"]
    assert floor["concealed"] == 128 and floor["public"] == 14
    assert floor["public_smoke_rules_met"]
    report = gates.decide(
        _success_results(cases), floor, {"capable": True}, "concealed",
        {"manifest": {"entries": 128, "mismatches": []}},
    )
    assert report["verdict"] == "PASS"
    assert report["cases_scored"] == 128
    assert report["cases_passed"] == 128
    assert all(g["denominator"] == 128 for g in report["per_gate"].values())


def test_synthetic_concealed_only_positive_control_is_sensitive_to_missing_lit(tmp_path):
    try:
        cases, passes, public_evidence = _synthetic_admission(tmp_path)
    except OSError as exc:
        pytest.skip(f"symlink capability unavailable: {type(exc).__name__}")
    for case in cases:
        if case["cls"] == "LIT":
            exp = passes[case["case_id"]][0][0]
            exp.literal_violations = []
    coverage_result = coverage.inspect(cases, passes, public_evidence)
    assert not coverage_result["met"]
    assert "LIT:mixed_violation:below_minimum" in coverage_result["shortfalls"]
    assert "LIT:mixed_clean_refusal:below_minimum" in coverage_result["shortfalls"]
    floor = gates.floors(cases, passes, public_evidence)
    assert not floor["met"]
    outcome = gates.decide(
        _success_results(cases), floor, {"capable": True}, "concealed",
        {"manifest": {"entries": 128, "mismatches": []}},
    )
    assert outcome["verdict"] == "FAIL"


@pytest.mark.parametrize("missing", [
    "public", "manifest", "symlink", "case_failure", "lone_surrogate",
    "sc_ambiguous", "mr_row1",
])
def test_synthetic_positive_control_ablations_fail(tmp_path, missing):
    """Each ablation operates on synthetic data, never a held-out case."""
    try:
        cases, passes, public_evidence = _synthetic_admission(tmp_path)
    except OSError as exc:
        pytest.skip(f"symlink capability unavailable: {type(exc).__name__}")

    passed_results = _success_results(cases)
    integrity = {"manifest": {"entries": 128, "mismatches": []}}
    symlinks = {"capable": True}
    if missing == "public":
        public_evidence = {"verified": False, "public_cases": 0, "classes": []}
    elif missing == "manifest":
        integrity = {"manifest": {"entries": 0, "mismatches": ["missing"]}}
    elif missing == "symlink":
        symlinks["capable"] = False
    elif missing == "case_failure":
        passed_results[0]["passed"] = False
        passed_results[0]["gates"]["G1"] = {
            "applies": True, "result": "fail", "failures": ["synthetic_failure"],
        }
    elif missing == "lone_surrogate":
        for case in cases:
            if case["cls"] == "L" and "\ud800" in case["event"]["content"]:
                case["event"]["content"] = "ordinary text"
    elif missing == "sc_ambiguous":
        for case in cases:
            if case["cls"] == "SC":
                exp = passes[case["case_id"]][0][0]
                for value in exp.numeric_outcomes.values():
                    if value["matcher_outcome"] == "UNEVALUATED":
                        value["primary_reason"] = "SOURCE_NOT_FOUND"
                        value["unknown_reasons"] = ["SOURCE_NOT_FOUND"]
    elif missing == "mr_row1":
        case = next(c for c in cases if c["cls"] == "MR")
        exp = passes[case["case_id"]][0][0]
        exp.event_relevance = False

    floor = gates.floors(cases, passes, public_evidence)
    result = gates.decide(passed_results, floor, symlinks, "concealed", integrity)
    assert result["verdict"] == ("INCOMPLETE" if missing == "symlink" else "FAIL")
    if missing in ("public", "lone_surrogate", "sc_ambiguous", "mr_row1"):
        assert not floor["coverage"]["met"]

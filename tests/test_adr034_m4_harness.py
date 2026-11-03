"""Tests for the ADR-034 M4 scoring harness (benchmarks/adr034_m4/harness.py).

Every case used here is SYNTHETIC (tests/adr034_m4_synthetic_corpus.py),
written from ADR-034 and the frozen criteria only; none is drawn from the
sealed M4 corpus. Gate 12 against the real ``mneme-hq==0.10.0`` reader is in
test_adr034_m4_harness_old_reader.py and is opt-in.
"""
from __future__ import annotations

import copy
import dataclasses
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests import adr034_m4_synthetic_corpus as syn

REPO_ROOT = Path(__file__).resolve().parents[1]
_HARNESS = REPO_ROOT / "benchmarks" / "adr034_m4" / "harness.py"

_spec = importlib.util.spec_from_file_location("adr034_m4_harness", _HARNESS)
h = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = h
_spec.loader.exec_module(h)

TEMPLATE = "cases/{case_id}"
BUILD = h.Interpreter(sys.executable, pythonpath=str(REPO_ROOT))


def synthetic_pins(digests: dict, cases) -> "h.Pins":
    return dataclasses.replace(
        h.M4_PINS,
        python_version=platform.python_version(),
        mneme_tree=h.git_tree_hash(REPO_ROOT / "mneme"),
        files_sha256_digest=digests["files_sha256_digest"],
        files_count=digests["files_count"],
        manifest_sha256=digests["manifest_sha256"],
        w_spec_sha256=digests["w_spec_sha256"],
        counts=h.observed_counts(cases),
        shapes=("S1", "S3"),
        is_m4_frozen=False,
    )


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "corpus"
    digests = syn.build(root)
    cases, _ = h.parse_manifest((root / "manifest.jsonl").read_text(encoding="utf-8"))
    return root, synthetic_pins(digests, cases)


# ── helpers for pure scoring tests ───────────────────────────────────────────

def make_case(**overrides) -> "h.Case":
    record = {
        "case_id": "t-1", "stratum": "A", "category": "A1", "shape": "S1",
        "contract": "contracts/S1",
        "invocation": {"transport": "source_file", "path": "cases/t-1/src/a.py",
                       "target_path": None, "location": None},
        "expected": {"applicability": "APPLIED", "matcher_status": "RECOGNIZED",
                     "matcher_outcome": "VIOLATION", "primary_reason": None,
                     "unknown_sources": None, "evaluation_complete": True},
        "rationale": "synthetic",
    }
    invocation = overrides.pop("invocation", {})
    expected = overrides.pop("expected", {})
    record.update(overrides)
    record["invocation"] = {**record["invocation"], **invocation}
    record["expected"] = {**record["expected"], **expected}
    return h._parse_record(record, 1, [])


def make_obs(result="VIOLATION", **overrides) -> dict:
    status = {"VIOLATION": "RECOGNIZED", "NO_VIOLATION": "RECOGNIZED",
              "UNEVALUATED": "MATCHER_UNEVALUATED"}.get(result)
    obs = {
        "result": result,
        "applicability": "EXCLUDED" if result == "EXCLUDED" else "APPLIED",
        "matcher_status": status,
        "matcher_outcome": result if result in h.MATCHER_OUTCOMES else None,
        "primary_reason": None,
        "unknown_sources": [] if status else None,
        "evaluation_complete": result != "UNEVALUATED",
        "verdict": "FAIL" if result == "VIOLATION" else "PASS",
        "exit_code": 2 if result in ("VIOLATION", "UNEVALUATED") else 0,
        "rule_id": "ADR-901:FORBID_NUMERIC_ABOVE:" + "0" * 32,
        "decision_version_id": "dver-1",
        "has_matcher_record": status is not None,
        "primary_reason_key_present": status is not None,
        "trace_subject_sha256": "a" * 64 if status else None,
        "subject_sha256": "a" * 64,
        "input_kind": "complete_source_file",
        "target_path_declared": None,
        "numeric_violations": ([{"rule_id": "ADR-901:FORBID_NUMERIC_ABOVE:" + "0" * 32,
                                 "decision_version_id": "dver-1", "severity": "FAIL"}]
                               if result == "VIOLATION" else []),
        "other_traces": 0,
        "other_violations": 0,
    }
    obs.update(overrides)
    return obs


def unevaluated(reason, **overrides):
    fields = {"primary_reason": reason,
              "unknown_sources": [{"kind": "symbol", "line": 1, "reason": reason}]}
    fields.update(overrides)
    return make_obs("UNEVALUATED", **fields)


U_CASE = dict(stratum="U", category="U3",
              expected={"matcher_status": "MATCHER_UNEVALUATED", "matcher_outcome": "UNEVALUATED",
                        "primary_reason": "SOURCE_NOT_FOUND", "evaluation_complete": False})
A7_SOURCES = [{"kind": "call", "line": 3, "reason": "UNRECOGNIZED_FORM"}]
A7_CASE = dict(category="A7", shape="S3",
               expected={"matcher_status": "PARTIAL", "primary_reason": "UNRECOGNIZED_FORM",
                         "unknown_sources": A7_SOURCES, "evaluation_complete": False})


def a7_obs(**overrides):
    base = dict(matcher_status="PARTIAL", primary_reason="UNRECOGNIZED_FORM",
                unknown_sources=list(A7_SOURCES), evaluation_complete=False)
    base.update(overrides)
    return make_obs("VIOLATION", **base)


def r_case(index: int, **overrides):
    outcome, reason = h.CRITERIA_R_TABLE[f"R{index}"]
    expected = {
        "matcher_status": "MATCHER_UNEVALUATED" if outcome == "UNEVALUATED" else "RECOGNIZED",
        "matcher_outcome": outcome, "primary_reason": reason,
        "evaluation_complete": outcome != "UNEVALUATED"}
    expected.update(overrides.pop("expected", {}))
    return make_case(stratum="R", category="R", shape=f"R{index}", expected=expected,
                     **overrides)


def r_obs(index: int):
    outcome, reason = h.CRITERIA_R_TABLE[f"R{index}"]
    return unevaluated(reason) if outcome == "UNEVALUATED" else make_obs(outcome)


def perfect_rows():
    """One correct row per scored partition (synthetic), for gate tests."""
    specs = [
        (make_case(case_id="a1"), make_obs("VIOLATION")),
        (make_case(case_id="a6", category="A6", expected={"matcher_outcome": "NO_VIOLATION"}),
         make_obs("NO_VIOLATION")),
        (make_case(case_id="a7", **A7_CASE), a7_obs()),
        (make_case(case_id="a9", category="A9", expected={"applicability": "EXCLUDED",
                                                          "matcher_status": None,
                                                          "matcher_outcome": None}),
         make_obs("EXCLUDED")),
        (make_case(case_id="w1", stratum="W", category="W"), make_obs("VIOLATION")),
        (make_case(case_id="w2", stratum="W", category="W",
                   expected={"matcher_outcome": "NO_VIOLATION"}), make_obs("NO_VIOLATION")),
        (make_case(case_id="u1", **U_CASE), unevaluated("SOURCE_NOT_FOUND")),
        (make_case(case_id="n1", stratum="N", category="N1",
                   expected={"primary_reason": "PARSE_FAILURE"}), unevaluated("PARSE_FAILURE")),
        (make_case(case_id="n2", stratum="N", category="N2",
                   invocation={"transport": "input", "location": "L4"},
                   expected={"primary_reason": "INCOMPLETE_SOURCE_INPUT"}),
         unevaluated("INCOMPLETE_SOURCE_INPUT", applicability="UNKNOWN")),
    ]
    specs += [(r_case(i, case_id=f"r{i}"), r_obs(i)) for i in range(1, 19)]
    return [(c, o, h.score_case(c, o)) for c, o in specs]


def rescore(rows, case_id, obs):
    out = []
    for case, old_obs, score in rows:
        if case.case_id == case_id:
            out.append((case, obs, h.score_case(case, obs)))
        else:
            out.append((case, old_obs, score))
    return out


PINS = dataclasses.replace(h.M4_PINS, shapes=("S1", "S3"))


def gates(rows):
    return {k: v["result"] for k, v in h.compute_gates(rows, PINS).items()}


# ── per-case scoring (criteria §3, §4) ───────────────────────────────────────

def test_perfect_rows_pass_every_scored_gate():
    assert set(gates(perfect_rows()).values()) == {"PASS"}


@pytest.mark.parametrize("case_kwargs, obs, gate", [
    # gate 1: a violation reported as no violation, or as unevaluated, is a miss
    ({}, make_obs("NO_VIOLATION"), "1"),
    ({}, unevaluated("UNRECOGNIZED_FORM"), "1"),
    ({"stratum": "W", "category": "W"}, make_obs("NO_VIOLATION"), "1"),
    # gate 2: a benign case reported as a violation is a false block
    ({"category": "A6", "expected": {"matcher_outcome": "NO_VIOLATION"}},
     make_obs("VIOLATION"), "2"),
])
def test_miss_and_false_block(case_kwargs, obs, gate):
    case = make_case(case_id="x", **case_kwargs)
    rows = perfect_rows() + [(case, obs, h.score_case(case, obs))]
    assert gates(rows)[gate] == "FAIL"


def test_unsafe_pass_on_u_and_n_for_no_violation_and_excluded():
    case = make_case(case_id="u1", **U_CASE)
    for obs in (make_obs("NO_VIOLATION"), make_obs("EXCLUDED")):
        s = h.score_case(case, obs)
        assert s["unsafe_pass"] and s["wrong_primary_reason"] and not s["un_correct"]
        g = gates(rescore(perfect_rows(), "u1", obs))
        assert g["3"] == g["3a"] == g["5"] == "FAIL"


def test_f1_shape_n2_clean_pass_fails_3_3a_5():
    rows = rescore(perfect_rows(), "n2", make_obs("EXCLUDED", input_kind="unverified_input"))
    g = gates(rows)
    assert g["3"] == g["3a"] == g["5"] == "FAIL"


@pytest.mark.parametrize("case_id", ["u1", "n1"])
@pytest.mark.parametrize("outcome", ["VIOLATION", "NO_VIOLATION"])
def test_gate_3a_requires_the_unevaluated_outcome_not_only_status(case_id, outcome):
    """Review F-1: MATCHER_UNEVALUATED with the expected reason but a decided
    outcome is an inconsistent record and fails 3a."""
    rows = perfect_rows()
    case = next(c for c, _, _ in rows if c.case_id == case_id)
    reason = case.expected["primary_reason"]
    obs = make_obs(outcome, matcher_status="MATCHER_UNEVALUATED", primary_reason=reason,
                   unknown_sources=[{"kind": "symbol", "line": 1, "reason": reason}])
    s = h.score_case(case, obs)
    assert s["un_correct"] is False
    assert "un_not_unevaluated_with_expected_reason" in s["failures"]
    assert gates(rescore(rows, case_id, obs))["3a"] == "FAIL"


def test_gate_3a_passes_on_the_fully_correct_record():
    rows = perfect_rows()
    assert all(s["un_correct"] for c, _, s in rows if c.role == "unevaluated")
    assert h.compute_gates(rows, PINS)["3a"]["value"]["correct"] == 3


def test_unexpected_violation_on_u_fails_3a_not_3():
    rows = rescore(perfect_rows(), "u1", make_obs("VIOLATION"))
    detail = h.compute_gates(rows, PINS)
    assert detail["3"]["result"] == "PASS"
    assert detail["3a"]["result"] == "FAIL"
    assert detail["3a"]["value"]["unexpected_un_violations"] == 1
    assert detail["5"]["result"] == "FAIL"


def test_wrong_primary_reason_alone_fails_3a_and_5():
    rows = rescore(perfect_rows(), "u1", unevaluated("UNRECOGNIZED_FORM"))
    g = gates(rows)
    assert g["3"] == "PASS" and g["3a"] == "FAIL" and g["5"] == "FAIL"


def test_path_unknown_is_never_relabelled_unevaluated():
    obs = make_obs("PATH_UNKNOWN", applicability="UNKNOWN", matcher_status=None,
                   matcher_outcome=None, has_matcher_record=False,
                   primary_reason_key_present=False, evaluation_complete=False)
    s = h.score_case(make_case(case_id="u1", **U_CASE), obs)
    assert not s["unevaluated"] and not s["un_correct"] and not s["unsafe_pass"]
    assert s["wrong_primary_reason"]


def test_unevaluated_label_on_a_w_case_is_scored_for_reason():
    case = make_case(case_id="w9", stratum="W", category="W",
                     expected={"matcher_status": "MATCHER_UNEVALUATED",
                               "matcher_outcome": "UNEVALUATED",
                               "primary_reason": "UNRECOGNIZED_FORM"})
    assert not h.score_case(case, unevaluated("UNRECOGNIZED_FORM"))["wrong_primary_reason"]
    s = h.score_case(case, make_obs("NO_VIOLATION"))
    assert s["unsafe_pass"] and s["wrong_primary_reason"]


# ── A7 (gate 4, ruling M4-08) ────────────────────────────────────────────────

def test_a7_correct():
    s = h.score_case(make_case(**A7_CASE), a7_obs())
    assert s["a7_ok"] and not s["miss"]


@pytest.mark.parametrize("obs, failing", [
    (make_obs("VIOLATION"), "partial"),                     # RECOGNIZED, no unknowns
    (a7_obs(evaluation_complete=True), "evaluation_incomplete"),
    (a7_obs(primary_reason="SOURCE_NOT_FOUND"), "primary_reason_match"),
    (a7_obs(unknown_sources=[{"kind": "call", "line": 4, "reason": "UNRECOGNIZED_FORM"}]),
     "unknown_sources_match"),
    (a7_obs(unknown_sources=A7_SOURCES + [{"kind": "symbol", "line": 1,
                                            "reason": "UNRECOGNIZED_FORM"}]),
     "unknown_sources_match"),
    (a7_obs(unknown_sources=[]), "unknown_sources_match"),
])
def test_a7_partial_mismatches_fail_gate_4(obs, failing):
    s = h.score_case(make_case(**A7_CASE), obs)
    assert s["a7"][failing] is False and s["a7_ok"] is False
    assert gates(rescore(perfect_rows(), "a7", obs))["4"] == "FAIL"


def test_a7_unevaluated_is_a_miss_and_fails_gate_4():
    obs = unevaluated("UNRECOGNIZED_FORM")
    s = h.score_case(make_case(**A7_CASE), obs)
    assert s["miss"] and not s["a7_ok"]


def test_a7_unknown_sources_compare_as_a_multiset():
    two = [{"kind": "call", "line": 3, "reason": "UNRECOGNIZED_FORM"},
           {"kind": "call", "line": 5, "reason": "SOURCE_NOT_FOUND"}]
    case = make_case(category="A7", shape="S5", expected={
        "matcher_status": "PARTIAL", "primary_reason": "SOURCE_NOT_FOUND",
        "unknown_sources": two, "evaluation_complete": False})
    obs = a7_obs(primary_reason="SOURCE_NOT_FOUND", unknown_sources=list(reversed(two)))
    assert h.score_case(case, obs)["a7_ok"]


def test_extra_unknown_sources_outside_a7_are_not_scored():
    obs = unevaluated("SOURCE_NOT_FOUND", unknown_sources=[
        {"kind": "symbol", "line": None, "reason": "SOURCE_NOT_FOUND"},
        {"kind": "call", "line": 2, "reason": "UNRECOGNIZED_FORM"}])
    assert h.score_case(make_case(**U_CASE), obs)["un_correct"]


# ── gates 6, 7, 8, 10 ────────────────────────────────────────────────────────

def test_coverage_a_requires_every_case_decided():
    rows = rescore(perfect_rows(), "a6", unevaluated("UNRECOGNIZED_FORM"))
    g = gates(rows)
    assert g["6"] == "FAIL" and g["2"] == "PASS"


def test_coverage_w_floor_is_95_percent():
    def w_rows(decided, total):
        rows = []
        for i in range(total):
            case = make_case(case_id=f"w{i}", stratum="W", category="W",
                             expected={"matcher_outcome": "NO_VIOLATION"})
            obs = make_obs("NO_VIOLATION") if i < decided else unevaluated("UNRECOGNIZED_FORM")
            rows.append((case, obs, h.score_case(case, obs)))
        return rows
    assert h.compute_gates(w_rows(19, 20), PINS)["7"]["result"] == "PASS"
    assert h.compute_gates(w_rows(18, 20), PINS)["7"]["result"] == "FAIL"
    assert h.compute_gates(w_rows(48, 50), PINS)["7"]["result"] == "PASS"
    assert h.compute_gates(w_rows(47, 50), PINS)["7"]["result"] == "FAIL"


@pytest.mark.parametrize("index, obs", [
    (16, make_obs("NO_VIOLATION")),             # 0.1 vs max 0.1 is a violation (O6 (a))
    (11, unevaluated("SOURCE_NOT_FOUND")),      # right status, wrong reason
    (17, make_obs("NO_VIOLATION")),             # non-int exponent must stay UNKNOWN
])
def test_set_r_mismatch_fails_gate_8(index, obs):
    detail = h.compute_gates(rescore(perfect_rows(), f"r{index}", obs), h.M4_PINS)
    assert detail["8"]["result"] == "FAIL"


def test_gate_8_needs_all_18_under_m4_pins():
    rows = [r for r in perfect_rows() if r[0].case_id != "r18"]
    assert h.compute_gates(rows, h.M4_PINS)["8"]["result"] == "FAIL"
    assert h.compute_gates(perfect_rows(), h.M4_PINS)["8"]["result"] == "PASS"


def test_set_r_is_scored_against_the_criteria_table_not_the_manifest():
    case = r_case(1, expected={"matcher_outcome": "NO_VIOLATION"})
    assert h.score_case(case, make_obs("VIOLATION"))["r_match"]
    findings = h.label_findings([case])
    assert any("set R R1" in f["finding"] for f in findings)


@pytest.mark.parametrize("override", [
    {"subject_sha256": None},
    {"rule_id": ""},
    {"decision_version_id": None},
    {"primary_reason_key_present": False},
    {"trace_subject_sha256": "b" * 64},
    {"numeric_violations": []},
])
def test_binding_incomplete_fails_gate_10(override):
    obs = make_obs("VIOLATION", **override)
    assert gates(rescore(perfect_rows(), "a1", obs))["10"] == "FAIL"


A9_CASE = dict(category="A9", expected={"applicability": "EXCLUDED", "matcher_status": None,
                                        "matcher_outcome": None})


def test_binding_exemption_covers_a9_excluded_only():
    """Review F-2: only applicability-only A9 may bind no matcher record."""
    a9 = make_case(case_id="a9", **A9_CASE)
    assert h.binding_complete(make_obs("EXCLUDED"), a9)
    # A9 still needs digest, rule id, version and a consistent excluded result.
    assert not h.binding_complete(make_obs("EXCLUDED", subject_sha256=None), a9)
    assert not h.binding_complete(make_obs("EXCLUDED", decision_version_id=""), a9)
    assert not h.binding_complete(make_obs("EXCLUDED", numeric_violations=[
        {"rule_id": "x", "decision_version_id": "y", "severity": "FAIL"}]), a9)
    # An A9 trace that is not EXCLUDED needs the full record.
    applied_bare = make_obs("NO_VIOLATION", matcher_status=None, matcher_outcome=None,
                            has_matcher_record=False, primary_reason_key_present=False,
                            trace_subject_sha256=None)
    assert not h.binding_complete(applied_bare, a9)


@pytest.mark.parametrize("case_kwargs", [
    {"category": "A6", "expected": {"matcher_outcome": "NO_VIOLATION"}},
    {"stratum": "W", "category": "W"},
    U_CASE,
    {"stratum": "N", "category": "N1", "expected": {"primary_reason": "PARSE_FAILURE"}},
    {"stratum": "R", "category": "R", "shape": "R2",
     "expected": {"matcher_outcome": "NO_VIOLATION"}},
])
def test_excluded_source_file_without_record_is_binding_incomplete_outside_a9(case_kwargs):
    case = make_case(case_id="x", **case_kwargs)
    assert case.transport == "source_file"
    for obs in (make_obs("EXCLUDED"),
                make_obs("PATH_UNKNOWN", applicability="UNKNOWN", matcher_status=None,
                         matcher_outcome=None, has_matcher_record=False,
                         primary_reason_key_present=False, trace_subject_sha256=None)):
        s = h.score_case(case, obs)
        assert s["binding_complete"] is False and "binding_incomplete" in s["failures"]
    rows = perfect_rows() + [(case, make_obs("EXCLUDED"), h.score_case(case, make_obs("EXCLUDED")))]
    assert gates(rows)["10"] == "FAIL"


def test_a9_is_scored_for_applicability_only():
    case = make_case(case_id="a9", category="A9", expected={"applicability": "EXCLUDED"})
    s = h.score_case(case, make_obs("VIOLATION"))
    assert s["a9_match"] is False and not s["miss"] and not s["false_block"]
    assert "a9_applicability_mismatch" in s["failures"]
    assert h.score_case(case, make_obs("EXCLUDED"))["a9_match"]


# ── headline and failure list ────────────────────────────────────────────────

def test_headline_uses_the_criteria_wording():
    lines = h.headline(perfect_rows(), PINS)
    assert lines["S1"] == ("W decided 2 of 2; A decided 2 of 2; "
                           "U unevaluated 1 of 1 (expected 1).")
    assert lines["S3"] == ("W decided 0 of 0; A decided 1 of 1; "
                           "U unevaluated 0 of 0 (expected 0).")
    assert lines["R"] == "R matched 18 of 18."


def test_failure_rows_carry_charter_section_10_fields():
    rows = rescore(perfect_rows(), "n2", make_obs("EXCLUDED"))
    failures = h.failure_rows(rows)
    # A non-source input without its matcher record also breaks the binding.
    assert {f["classification"] for f in failures} == {
        "unsafe_pass", "wrong_primary_reason", "un_not_unevaluated_with_expected_reason",
        "binding_incomplete"}
    row = failures[0]
    assert row["case_id"] == "n2" and row["stratum"] == "N" and row["category"] == "N2"
    assert row["invocation_form"] == "--input (no --target-path)" and row["location"] == "L4"
    assert set(row["expected"]) == set(row["observed"]) - {"applicability"} == {
        "matcher_status", "matcher_outcome", "primary_reason"}
    assert "rationale" not in json.dumps(failures)


# ── manifest validation and the §5 matrix ────────────────────────────────────

@pytest.mark.parametrize("overrides, check", [
    ({"stratum": "A9"}, "stratum"),
    ({"category": "A10"}, "category"),
    ({"stratum": "N", "category": "N2"}, "--input"),
    ({"stratum": "N", "category": "N2", "invocation": {"transport": "input"}}, "location"),
    ({"stratum": "N", "category": "N2a",
      "invocation": {"transport": "input", "target_path": "src/x.py"}}, "makes it N2b"),
    ({"stratum": "N", "category": "N2b",
      "invocation": {"transport": "input", "target_path": "src/x.py", "location": "L1"}},
     "location"),
    ({"invocation": {"target_path": "src/x.py"}}, "target_path"),
    ({"invocation": {"transport": "input"}}, "--source-file"),
    ({"invocation": {"path": "../escape.py"}}, "escapes"),
    ({"invocation": {"path": "/abs/x.py"}}, "absolute"),
    ({"expected": {"matcher_status": "UNEVALUATED"}}, "matcher_status"),
    ({"expected": {"primary_reason": "OTHER"}}, "primary_reason"),
    ({"expected": {"evaluation_complete": "no"}}, "evaluation_complete"),
    ({"stratum": "R", "category": "R", "shape": "R19"}, "R1..R18"),
    ({"shape": "S6"}, "shape"),
])
def test_manifest_matrix_violations_refuse(overrides, check):
    with pytest.raises(h.Refusal) as info:
        make_case(**overrides)
    assert check in str(info.value)


def test_manifest_duplicates_and_omissions():
    record = json.loads(json.dumps(syn.manifest_records()[0]))
    line = json.dumps(record)
    with pytest.raises(h.Refusal, match="duplicate case_id"):
        h.parse_manifest(line + "\n" + line + "\n")
    with pytest.raises(h.Refusal, match="duplicate key"):
        h.parse_manifest('{"case_id": "a", "case_id": "b"}\n')
    with pytest.raises(h.Refusal, match="newline"):
        h.parse_manifest(line)
    del record["invocation"]["location"]
    del record["expected"]["evaluation_complete"]
    cases, findings = h.parse_manifest(json.dumps(record) + "\n")
    assert cases[0].location is None and cases[0].expected["evaluation_complete"] is None
    assert len(findings) == 2


def test_n2_forms_from_target_path():
    n2a = make_case(stratum="N", category="N2",
                    invocation={"transport": "input", "location": "L2"})
    n2b = make_case(stratum="N", category="N2",
                    invocation={"transport": "input", "target_path": "src/x.py"})
    assert (n2a.form, n2b.form) == ("N2a", "N2b")


def test_check_argv_applies_the_section_5_transports(corpus):
    root, _ = corpus
    cases, _ = h.parse_manifest((root / "manifest.jsonl").read_text(encoding="utf-8"))
    layouts = h.resolve_layouts(cases, TEMPLATE, root)
    by_id = {c.case_id: c for c in cases}

    def argv(case_id):
        value = h.check_argv(by_id[case_id], layouts[case_id], root)
        memory = root / "cases" / case_id / ".mneme" / "project_memory.json"
        assert value[:8] == ["check", "--memory", str(memory), "--query", "audit",
                             "--mode", "strict", "--json"]
        return value[8:]

    assert argv("syn-a01") == ["--source-file", str(root / "cases/syn-a01/src/settings.py")]
    # N2a: --input with no --target-path, wherever the input sits (here L4).
    assert argv("syn-n05") == ["--input", str(root / "inputs/stdin-like.txt")]
    # N2b: target_path is relative to the case's policy root (M4-04), not the cwd.
    assert argv("syn-n06") == ["--input", str(root / "cases/syn-n06/incoming/delta.txt"),
                               "--target-path", str(root / "cases/syn-n06/src/db.py")]


def test_case_root_template_problems_refuse(corpus):
    root, _ = corpus
    cases, _ = h.parse_manifest((root / "manifest.jsonl").read_text(encoding="utf-8"))
    with pytest.raises(h.Refusal, match="not a directory"):
        h.resolve_layouts(cases, "{case_id}", root)
    with pytest.raises(h.Refusal, match="cannot render"):
        h.resolve_layouts(cases, "cases/{nope}", root)
    with pytest.raises(h.Refusal, match="share a policy root"):
        h.resolve_layouts(cases, "cases", root)
    memory = root / "cases" / "syn-a01" / ".mneme" / "project_memory.json"
    memory.parent.mkdir()
    memory.write_text("{}", encoding="utf-8")
    with pytest.raises(h.Refusal, match="memory already exists"):
        h.resolve_layouts(cases, TEMPLATE, root)


def test_n2a_location_geometry_is_recorded(corpus):
    root, _ = corpus
    cases, _ = h.parse_manifest((root / "manifest.jsonl").read_text(encoding="utf-8"))
    layouts = h.resolve_layouts(cases, TEMPLATE, root)
    for case in cases:
        if case.form == "N2a":
            assert layouts[case.case_id].geometry["location_consistent"], case.case_id
    assert layouts["syn-n05"].geometry["path_inside_case_root"] is False


# ── FILES.sha256 parsing ─────────────────────────────────────────────────────

@pytest.mark.parametrize("text, match", [
    ("zz  a.py\n", "unparseable"),
    (f"{'0' * 64}  a.py\n{'0' * 64}  ./a.py\n", "duplicate"),
    (f"{'0' * 64}  /etc/x\n", "absolute"),
    (f"{'0' * 64}  ../x\n", "escapes"),
    (f"{'0' * 64}  a.py\n\n", "blank"),
])
def test_files_sha256_parse_refusals(text, match):
    with pytest.raises(h.Refusal, match=match):
        h.parse_files_sha256(text)


def test_files_sha256_accepts_binary_marker_and_dot_slash():
    entries = h.parse_files_sha256(f"{'0' * 64} *./a/b.py\n{'1' * 64}  c.txt\n")
    assert entries == [("0" * 64, "a/b.py"), ("1" * 64, "c.txt")]


# ── git tree hash of the imported package ────────────────────────────────────

def test_git_tree_hash_matches_git(tmp_path):
    git = shutil.which("git")
    if git is None:
        pytest.skip("git not available")
    repo = tmp_path / "repo"
    pkg = repo / "pkg"
    (pkg / "sub").mkdir(parents=True)
    (pkg / "__init__.py").write_bytes(b"x = 1\n")
    (pkg / "sub" / "mod.py").write_bytes(b"y = 2\r\n")
    (pkg / "sub-file.py").write_bytes(b"")
    (pkg / "sub.py").write_bytes(b"z = 3\n")
    subprocess.run([git, "init", "-q", str(repo)], check=True)
    subprocess.run([git, "-C", str(repo), "-c", "core.autocrlf=false", "add", "pkg"], check=True)
    expected = subprocess.run([git, "-C", str(repo), "write-tree", "--prefix=pkg/"],
                              check=True, capture_output=True, text=True).stdout.strip()
    (pkg / "__pycache__").mkdir()
    (pkg / "__pycache__" / "x.cpython-311.pyc").write_bytes(b"\0")
    (pkg / "empty").mkdir()
    assert h.git_tree_hash(pkg) == expected
    (pkg / "stray.py").write_bytes(b"")
    assert h.git_tree_hash(pkg) != expected


# ── normalization and gate 9 ─────────────────────────────────────────────────

ROOT_A = r"C:\Temp\m4-run-a" if sys.platform == "win32" else "/tmp/m4-run-a"
ROOT_B = r"C:\Temp\m4-run-b" if sys.platform == "win32" else "/tmp/m4-run-b"


def summary_text(root, **extra):
    return h.dump_json({"run_root": root, "path": root + "/x", **extra})


def test_normalization_replaces_only_the_run_root():
    text = summary_text(ROOT_A, other="C:/Temp/elsewhere")
    normalized = h.normalize(text, ROOT_A)
    assert ROOT_A.replace("\\", "\\\\") not in normalized
    assert normalized.count(h.ROOT_TOKEN) == 2
    assert "C:/Temp/elsewhere" in normalized


def test_gate9_passes_when_only_the_root_differs():
    gate = h.compare_runs([(summary_text(ROOT_A), ROOT_A), (summary_text(ROOT_B), ROOT_B)])
    assert gate["result"] == "PASS"
    digests = gate["value"]["normalized_summary_sha256"]
    assert digests[0] == digests[1]
    assert gate["value"]["raw_summary_sha256"][0] != gate["value"]["raw_summary_sha256"][1]


@pytest.mark.parametrize("second", [
    summary_text(ROOT_B, extra_field=1),                      # any other difference
    summary_text(ROOT_B).replace("\n", "\r\n"),               # whitespace is not normalized
    h.dump_json({"run_root": ROOT_B, "path": repr(ROOT_B) + "/x"}),  # another spelling
])
def test_gate9_fails_on_anything_but_the_root(second):
    gate = h.compare_runs([(summary_text(ROOT_A), ROOT_A), (second, ROOT_B)])
    assert gate["result"] == "FAIL"


def test_gate9_needs_two_runs():
    assert h.compare_runs([(summary_text(ROOT_A), ROOT_A)])["result"] == "FAIL"


# ── gate 12 evaluation (the real old reader is opt-in) ───────────────────────

GOOD_CONTROL = {"memory_schema": "mneme.decision-index/v1", "exit_codes": [0, 0, 0],
                "payload_schema": "mneme.check/v1", "verdict": "PASS"}
GOOD_REFUSAL = {"memory_schema": "mneme.decision-index/v2",
                "semantic_features": ["numeric_upper_bound_rule"],
                "numeric_rules": ["ADR-001:FORBID_NUMERIC_ABOVE:x"], "exit_code": 1,
                "timed_out": False, "stdout_has_verdict": False, "persistence_error": True,
                "memory_unchanged": True}


def test_gate12_passes_on_explicit_refusal():
    assert h.evaluate_gate12(GOOD_CONTROL, GOOD_REFUSAL)["result"] == "PASS"


@pytest.mark.parametrize("control, refusal", [
    ({"exit_codes": [0, 0, 1]}, {}),                              # control reader broken
    ({"memory_schema": "mneme.decision-index/v2"}, {}),
    ({}, {"exit_code": 0}),                                       # read it: not refused
    ({}, {"stdout_has_verdict": True}),                           # silently dropped
    ({}, {"persistence_error": False}),                           # some other crash
    ({}, {"memory_unchanged": False}),                            # rewrote / downgraded
    ({}, {"timed_out": True, "exit_code": None}),
    ({}, {"semantic_features": []}),                              # not the v2 feature
    ({}, {"numeric_rules": []}),
])
def test_gate12_fails(control, refusal):
    result = h.evaluate_gate12({**GOOD_CONTROL, **control}, {**GOOD_REFUSAL, **refusal})
    assert result["result"] == "FAIL"


# ── preconditions (each refuses before any case runs) ────────────────────────

def _score(root, pins, out, **kwargs):
    kwargs.setdefault("build", BUILD)
    return h.score(corpus=root, template=TEMPLATE, out_dir=out, old=None, old_wheel=None,
                   pins=pins, **kwargs)


@pytest.mark.parametrize("change, check", [
    ({"python_version": "3.12.999"}, "python"),
    ({"python_implementation": "PyPy"}, "python"),
    ({"mneme_tree": "0" * 40}, "mneme_tree"),
    ({"files_sha256_digest": "0" * 64}, "files_sha256"),
    ({"files_count": 1}, "files_sha256"),
    ({"manifest_sha256": "0" * 64}, "manifest"),
    ({"w_spec_sha256": "0" * 64}, "w_spec"),
])
def test_pin_mismatches_refuse(corpus, tmp_path, change, check):
    root, pins = corpus
    out = tmp_path / "out"
    final = _score(root, dataclasses.replace(pins, **change), out)
    assert final["result"] == "REFUSED" and final["refusal"]["check"] == check
    assert sorted(p.name for p in out.iterdir()) == ["summary.json"]


def test_tampered_corpus_file_refuses(corpus, tmp_path):
    root, pins = corpus
    (root / "cases" / "syn-a01" / "src" / "settings.py").write_bytes(b"REQUEST_TIMEOUT_S = 1\n")
    final = _score(root, pins, tmp_path / "out")
    assert final["refusal"]["check"] == "files_sha256"
    assert "FAILED" in final["refusal"]["detail"]


def test_extra_corpus_file_refuses(corpus, tmp_path):
    root, pins = corpus
    (root / "cases" / "syn-a01" / "extra.py").write_bytes(b"")
    final = _score(root, pins, tmp_path / "out")
    assert final["refusal"]["check"] == "corpus_layout"


def test_w_spec_by_path(corpus, tmp_path):
    root, pins = corpus
    final = _score(root, pins, tmp_path / "o1", w_spec="manifest.jsonl")
    assert final["refusal"]["check"] == "w_spec"
    final = _score(root, pins, tmp_path / "o2", w_spec="missing.md")
    assert final["refusal"]["check"] == "w_spec"


def test_counts_mismatch_refuses(corpus, tmp_path):
    root, pins = corpus
    counts = copy.deepcopy(pins.counts)
    counts["n2a_location"]["L1"] += 1
    final = _score(root, dataclasses.replace(pins, counts=counts), tmp_path / "out")
    assert final["refusal"]["check"] == "counts"


def test_m4_counts_are_the_frozen_composition():
    counts = h.M4_PINS.counts
    assert counts["total"]["cases"] == 161 == sum(counts["stratum"].values())
    assert sum(counts["a_scored_shape"].values()) == 48
    assert sum(v for k, v in counts["a_category"].items() if k != "A9") == 48
    assert sum(counts["n_form"].values()) == counts["stratum"]["N"] == 15
    assert sum(counts["n2a_location"].values()) == counts["n_form"]["N2a"] == 8
    assert sum(counts["u_category"].values()) == 25 and sum(counts["w_shape"].values()) == 50


def test_non_empty_output_directory_refuses(corpus, tmp_path):
    root, pins = corpus
    out = tmp_path / "out"
    out.mkdir()
    (out / "old.json").write_text("{}", encoding="utf-8")
    with pytest.raises(h.Refusal, match="not empty"):
        _score(root, pins, out)
    assert sorted(p.name for p in out.iterdir()) == ["old.json"]


def test_cli_requires_the_old_reader_and_uses_the_m4_pins(corpus, tmp_path, capsys):
    root, _ = corpus
    with pytest.raises(SystemExit):
        h.main(["score", "--corpus", str(root), "--case-root-template", TEMPLATE,
                "--out", str(tmp_path / "o1")])
    out = tmp_path / "o2"
    wheel = tmp_path / h.M4_PINS.old_reader_wheel_name
    wheel.write_bytes(b"")
    rc = h.main(["score", "--corpus", str(root), "--case-root-template", TEMPLATE,
                 "--out", str(out), "--old-reader-python", sys.executable,
                 "--old-reader-wheel", str(wheel)])
    assert rc == 2
    final = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert final["result"] == "REFUSED" and final["pins"]["is_m4_frozen"] is True


def test_a_crash_during_a_pass_is_invalid_never_scored(corpus, tmp_path, monkeypatch):
    root, pins = corpus

    def boom(*args, **kwargs):
        raise RuntimeError("synthetic crash")

    monkeypatch.setattr(h, "execute_case", boom)
    final = _score(root, pins, tmp_path / "out", work_dir=tmp_path)
    assert final["result"] == "INVALID"
    assert final["refusal"] == {"check": "harness_error",
                                "detail": "RuntimeError: synthetic crash"}
    assert "gates" not in final
    assert not list(tmp_path.glob("m4-run-*"))


def test_second_pass_refuses_a_run_root_that_was_not_removed(corpus, tmp_path, monkeypatch):
    """Ruling Q14: the repeated root path is valid only after full removal."""
    root, pins = corpus
    calls = []

    def leaky_pass(prep, number, run_root, out_dir, keep):
        calls.append(number)
        run_root.mkdir()
        return "{}\n", str(run_root), {}

    monkeypatch.setattr(h, "run_pass", leaky_pass)
    final = _score(root, pins, tmp_path / "out", work_dir=tmp_path)
    assert calls == [1]
    assert final["result"] == "INVALID" and final["refusal"]["check"] == "run_root"
    assert "previous pass was not removed" in final["refusal"]["detail"]


def test_old_reader_must_lack_the_numeric_type(corpus, tmp_path):
    root, pins = corpus
    wheel = tmp_path / h.M4_PINS.old_reader_wheel_name
    wheel.write_bytes(b"")
    final = h.score(corpus=root, template=TEMPLATE, out_dir=tmp_path / "out", build=BUILD,
                    old=BUILD, old_wheel=wheel, pins=pins)
    assert final["refusal"]["check"] == "old_reader"


# ── end to end against the pinned build (two passes, no old reader) ──────────

# Charter §5.1 erratum (owner ruling G2C-R1, MnemeHQ/mneme#638): from G2-1 on,
# the shared validator trusts a ``complete_source_file`` payload only when the
# caller passes ``expected_input="source_file"``. The unmodified M4 child
# (benchmarks/adr034_m4/m4_child.py) calls the default, so these end-to-end
# cases that score trust through it are historical validation of the build
# M4 pinned. They are kept unedited; the current-build regression is
# tests/test_adr034_post_m4_source_file_compat.py.
PINNED_M4_BUILD_TRUST = pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "historical pinned-build validation: the unmodified M4 child applies the "
        "default assess_verdict, which rejects complete_source_file after G2-1 "
        "(charter §5.1 erratum G2C-R1, MnemeHQ/mneme#638)"
    ),
)


@pytest.fixture(scope="module")
def e2e(tmp_path_factory):
    base = tmp_path_factory.mktemp("m4e2e")
    root = base / "corpus"
    digests = syn.build(root)
    cases, _ = h.parse_manifest((root / "manifest.jsonl").read_text(encoding="utf-8"))
    pins = synthetic_pins(digests, cases)
    out = base / "out"
    final = h.score(corpus=root, template=TEMPLATE, out_dir=out, build=BUILD, old=None,
                    old_wheel=None, pins=pins, work_dir=base)
    return final, out, root


@PINNED_M4_BUILD_TRUST
def test_e2e_every_gate_but_12_passes_on_the_synthetic_corpus(e2e):
    final, out, _ = e2e
    assert final["operational_failures"]["count"] == 0
    results = {k: v["result"] for k, v in final["gates"].items()}
    assert results.pop("12") == "NOT_RUN"
    assert set(results.values()) == {"PASS"}, final["gates"]
    assert final["result"] == "INCOMPLETE"
    assert final["failures"] == []
    assert final["disclosures"] == list(h.DISCLOSURES)
    assert final["a9_applicability"]["gating"] is False
    assert final["a9_applicability"]["matched"] == final["a9_applicability"]["of"] == 1
    assert final["headline"] == {
        "S1": "W decided 2 of 2; A decided 3 of 3; U unevaluated 2 of 2 (expected 2).",
        "S3": "W decided 2 of 2; A decided 3 of 3; U unevaluated 1 of 1 (expected 1).",
        "R": "R matched 3 of 3.",
    }


def test_e2e_runs_are_byte_identical(e2e):
    final, out, _ = e2e
    one = (out / "run-1" / "summary.json").read_bytes()
    two = (out / "run-2" / "summary.json").read_bytes()
    assert one == two
    assert final["runs"][0]["summary_sha256"] == h.sha256_bytes(one)
    assert (out / "run-1" / "cases.jsonl").read_bytes() == (out / "run-2" / "cases.jsonl").read_bytes()


def test_e2e_run_roots_are_removed_and_corpus_untouched(e2e):
    final, _, root = e2e
    assert not Path(final["runs"][0]["run_root"]).exists()
    assert not list(root.rglob("project_memory.json"))


@PINNED_M4_BUILD_TRUST
def test_e2e_records_transport_trust_and_unnormalized_unknown(e2e):
    _, out, _ = e2e
    records = {r["case_id"]: r for r in map(json.loads, (out / "run-1" / "cases.jsonl")
                                            .read_text(encoding="utf-8").splitlines())}
    assert all(r["trust"]["trusted"] for r in records.values())
    l4 = records["syn-n05"]
    assert "--target-path" not in l4["steps"]["check"]["argv"]
    assert l4["observed"]["applicability"] == "UNKNOWN"          # recorded, never normalized
    assert l4["observed"]["matcher_status"] == "MATCHER_UNEVALUATED"
    assert l4["observed"]["target_path_declared"] is False
    n2b = records["syn-n06"]
    assert n2b["steps"]["check"]["argv"][-2] == "--target-path"
    assert n2b["observed"]["applicability"] == "APPLIED"
    assert n2b["observed"]["target_path_declared"] is True
    a7 = records["syn-a06"]
    assert a7["observed"]["matcher_status"] == "PARTIAL" and a7["score"]["a7_ok"]
    assert records["syn-a01"]["observed"]["subject_matches_input_bytes"] is True
    summary = json.loads((out / "run-1" / "summary.json").read_text(encoding="utf-8"))
    recorded = {r["case_id"]: r["applicability"] for r in summary["n2_applicability_recorded"]}
    assert recorded == {"syn-n02": "APPLIED", "syn-n03": "EXCLUDED", "syn-n04": "EXCLUDED",
                        "syn-n05": "UNKNOWN", "syn-n06": "APPLIED"}


def test_e2e_gate11_reproduces_golden_ids(e2e):
    final, _, _ = e2e
    gate = final["gates"]["11"]
    assert gate["value"] == {"reproduced": 4, "of": 4, "forbid_literal_ids_stable": True}


def test_gate11_fails_on_a_wrong_golden_id(tmp_path):
    vectors = list(h.ADR034_GOLDEN)
    vectors[2] = dataclasses.replace(vectors[2], rule_id=vectors[2].rule_id[:-1] + "0")
    pins = dataclasses.replace(h.M4_PINS, golden=tuple(vectors))
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    gate = h.run_gate11(BUILD, tmp_path, cwd, pins)
    assert gate["result"] == "FAIL"
    assert [v["reproduced"] for v in gate["vectors"]] == [True, True, False, True]
    assert gate["value"]["forbid_literal_ids_stable"] is True


@PINNED_M4_BUILD_TRUST
def test_e2e_mislabelled_corpus_reports_failures_by_case(tmp_path):
    """A wrong label must surface as a failure row, never be absorbed."""
    records = syn.manifest_records()
    for record in records:
        if record["case_id"] == "syn-w01":
            record["expected"]["matcher_outcome"] = "VIOLATION"
        if record["case_id"] == "syn-u02":
            record["expected"]["primary_reason"] = "SOURCE_NOT_FOUND"
    root = tmp_path / "corpus"
    digests = syn.build(root, records)
    cases, findings = h.parse_manifest((root / "manifest.jsonl").read_text(encoding="utf-8"))
    pins = synthetic_pins(digests, cases)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    prep = h.prepare(root, TEMPLATE, BUILD, None, None, pins, None, cwd)
    out = tmp_path / "out"
    out.mkdir()
    _, _, summary = h.run_pass(prep, 1, tmp_path / "run-root", out, False)
    assert summary["gates"]["1"]["result"] == "FAIL"
    assert summary["gates"]["3a"]["result"] == "FAIL"
    assert summary["gates"]["5"]["result"] == "FAIL"
    classes = {(f["case_id"], f["classification"]) for f in summary["failures"]}
    assert ("syn-w01", "miss") in classes
    assert ("syn-u02", "wrong_primary_reason") in classes
    assert not (tmp_path / "run-root").exists()

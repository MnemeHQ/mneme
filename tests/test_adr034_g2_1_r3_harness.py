"""R3 scorer-B harness unit tests (no Mneme build needed).

Includes the R3 §3 mandatory public synthetic scorer-negative tests (a)-(g)
and the positive control. Every record below is fabricated here; none is a
D3 regression fixture, an implementation output or a corpus case.
"""

from __future__ import annotations

import base64
import copy
import io
import tarfile
import hashlib
import json
import os
from pathlib import Path

import pytest
import yaml

from benchmarks.adr034_g2_1_r3 import attribution, coverage, gates, oracle, public_smoke, runner, synthetic
from benchmarks.adr034_g2_1_r3 import contract as C

HOST = ("2.1.312", "a" * 64)
LIT_ID = "ADR-9102:FORBID_LITERAL:" + "0" * 32


# ── identity: ADR-034 §5 golden vectors ─────────────────────────────────────


def _numeric_value(**extra):
    obj = {"v": 1, "language": "python", "inclusive": True, "unit": "seconds", **extra}
    return oracle.canonical_json(obj)


@pytest.mark.parametrize("value, expected", [
    (_numeric_value(symbol="ROUTER_DEADLINE_S", call={"function": "classify", "position": 1}, max="5"),
     "ADR-001:FORBID_NUMERIC_ABOVE:29b880066c98c7db4abb997f7cbbb096"),
    (_numeric_value(symbol="ROUTER_DEADLINE_S", max="5"),
     "ADR-001:FORBID_NUMERIC_ABOVE:19aa8ed962b7e693ffe3d71804cf4c7c"),
    (_numeric_value(call={"function": "classify", "position": 1}, max="2.5"),
     "ADR-001:FORBID_NUMERIC_ABOVE:e74969fb22bd8988d5fae6133a8b7a57"),
])
def test_numeric_golden_vectors(value, expected):
    assert oracle.Rule("ADR-001", "", C.NUMERIC, value, ("src/**",), ()).rule_id == expected


def test_literal_golden_vector():
    # ADR-034 §5 row 1: ADR-005's global FORBID_LITERAL, parsed from the declaring
    # ADR itself (the literal is not repeated here; ADR-019 §6 exempts only ADR-005).
    path = next((Path(__file__).resolve().parent.parent / "docs" / "adr").glob("ADR-005-*.md"))
    adr = oracle.parse_adr("docs/adr/" + path.name, path.read_text(encoding="utf-8"))
    (rule,) = [r for r in adr.rules if r.rule_type == C.LITERAL]
    assert rule.include is None and rule.exclude == ()
    assert rule.rule_id == "ADR-005:FORBID_LITERAL:cbf4d271068507ddb12c33abd765e333"


def test_canonical_value_example_text():
    value = _numeric_value(symbol="ROUTER_DEADLINE_S", call={"function": "classify", "position": 1}, max="5")
    assert value == ('{"call":{"function":"classify","position":1},"inclusive":true,'
                     '"language":"python","max":"5","symbol":"ROUTER_DEADLINE_S","unit":"seconds","v":1}')


def test_exclude_paths_enter_identity_only_when_present():
    a = oracle.Rule("ADR-1", "", C.LITERAL, "x(", ("src/**",), ())
    b = oracle.Rule("ADR-1", "", C.LITERAL, "x(", ("src/**",), ("src/legacy/**",))
    assert a.rule_id != b.rule_id
    assert oracle.applicability_object(None, ()) == {}


# ── max grammar (ADR-034 §5) ─────────────────────────────────────────────────


def _scalar(text):
    return yaml.compose(f"max: {text}", Loader=yaml.SafeLoader).value[0][1]


@pytest.mark.parametrize("raw, canonical", [("5", "5"), ("5.000", "5"), ("2.50", "2.5"), ("0.75", "0.75")])
def test_canonical_max(raw, canonical):
    assert oracle.canonical_max(_scalar(raw)) == canonical


@pytest.mark.parametrize("raw", ["05", "5e0", ".5", "5.", "1_000", '"5"', "0", "0.0", "-1", "0x5"])
def test_canonical_max_rejects(raw):
    with pytest.raises(oracle.OracleError):
        oracle.canonical_max(_scalar(raw))


# ── ADR-020 selectors and applicability ──────────────────────────────────────


@pytest.mark.parametrize("pattern, path, expected", [
    ("src/**", "src/a.py", True), ("src/**", "src/a/b/c.py", True), ("src/**", "lib/a.py", False),
    ("**/*.py", "a.py", True), ("**/*.py", "x/y/a.py", True), ("src/*.py", "src/a/b.py", False),
    ("src/*.py", "src/a.py", True), ("Src/**", "src/a.py", False), ("src/a*b.py", "src/axxb.py", True),
])
def test_selector_matches(pattern, path, expected):
    assert oracle.selector_matches(pattern, path) is expected


@pytest.mark.parametrize("pattern", ["/src/**", "src\\a", "src/../x", "a/**b", "src/[ab].py", "!src/**", "", "a//b"])
def test_invalid_selectors(pattern):
    with pytest.raises(oracle.OracleError):
        oracle.validate_selector(pattern)


def test_applicability_mechanisms():
    include_miss = oracle.Rule("A", "", C.NUMERIC, "v", ("lib/**",), ())
    exclude_match = oracle.Rule("A", "", C.NUMERIC, "v", ("src/**",), ("src/legacy/**",))
    glob = oracle.Rule("A", "", C.LITERAL, "v", None, ())
    assert oracle.applicability(include_miss, "src/a.py") == ("EXCLUDED", "include_miss")
    assert oracle.applicability(exclude_match, "src/legacy/a.py") == ("EXCLUDED", "exclude_match")
    assert oracle.applicability(exclude_match, "src/a.py") == ("APPLIED", None)
    assert oracle.applicability(glob, None) == ("APPLIED", None)
    assert oracle.applicability(include_miss, None) == ("UNKNOWN", None)


# ── FORBID_LITERAL (ADR-019 §2-§3) ───────────────────────────────────────────


@pytest.mark.parametrize("literal, text, expected", [
    ("eval(", "return medieval(expr)", False), ("eval(", "x = eval(s)", True),
    ("breakpoint()", "    breakpoint()\n", True), ("import foo", "import foobar", False),
    ("import foo", "import foo.bar", True), ("psycopg2", "psycopg2-binary", False),
    ("time.sleep(", "time.sleep(1)", True), ("Eval(", "eval(", False),
    ("eval(", "medieval( and eval(", True),
])
def test_literal_occurs(literal, text, expected):
    assert oracle.literal_occurs(literal, text) is expected


def test_universal_newlines():
    assert oracle.universal_newlines("a\r\nb\rc\n") == "a\nb\nc\n"


# ── ADR parsing ─────────────────────────────────────────────────────────────


def _adr_text(constraints):
    return f"---\nid: ADR-1\nstatus: accepted\nscope: a.b\n---\n\n## Constraints\n\n{constraints}\n## Next\n"


def test_parse_adr_rules():
    adr = oracle.parse_adr("docs/adr/ADR-1.md", _adr_text(
        "- FORBID_LITERAL: os.system(\n\n- FORBID_NUMERIC_ABOVE:\n    language: python\n"
        "    symbol: X\n    max: 2.50\n    inclusive: true\n    unit: s\n    include_paths:\n      - \"src/**\"\n"))
    assert [(r.rule_type, r.value) for r in adr.rules][0] == (C.LITERAL, "os.system(")
    assert '"max":"2.5"' in adr.rules[1].value


@pytest.mark.parametrize("bad", [
    "- Never call the shell\n",
    "- FORBID_SOMETHING: x\n",
    "- FORBID_NUMERIC_ABOVE:\n    language: python\n    symbol: X\n    symbol: Y\n    max: 5\n"
    "    inclusive: true\n    unit: s\n    include_paths:\n      - \"src/**\"\n",
    "- FORBID_NUMERIC_ABOVE:\n    language: python\n    symbol: X\n    max: 5\n"
    "    inclusive: false\n    unit: s\n    include_paths:\n      - \"src/**\"\n",
])
def test_parse_adr_rejects(bad):
    with pytest.raises(oracle.OracleError):
        oracle.parse_adr("docs/adr/ADR-1.md", _adr_text(bad))


# ── R3 §3 mandatory synthetic scorer-negative tests (a)-(g) ───────────────────

DIGEST = hashlib.sha256(b"synthetic carrier").hexdigest()
EXPECTED = [(LIT_ID, C.LITERAL)]


def _record(violations, trusted=True, subject=None, digest=DIGEST):
    return {"carrier_sha256": digest, "violations": violations,
            "checker": {"trusted": trusted, "subject": subject, "evaluation_complete": True}}


def test_positive_control_correct_identity_passes():
    record = _record([{"rule_id": LIT_ID, "rule_type": C.LITERAL}])
    assert attribution.identity_failures(record, EXPECTED, DIGEST) == []
    assert attribution.attributed_identities(record, DIGEST) == [(LIT_ID, C.LITERAL)]


def test_negative_a_missing_rule_id():
    record = _record([{"rule_type": C.LITERAL}])
    failures = attribution.identity_failures(record, EXPECTED, DIGEST)
    assert failures and f"missing_identity:{LIT_ID}" in failures
    assert attribution.attributed_identities(record, DIGEST) == []


def test_negative_b_empty_rule_id():
    record = _record([{"rule_id": "", "rule_type": C.LITERAL}])
    failures = attribution.identity_failures(record, EXPECTED, DIGEST)
    assert "malformed_rule_id:0" in failures and f"missing_identity:{LIT_ID}" in failures


@pytest.mark.parametrize("value", [None, 0, 7, 1.5, True, [LIT_ID], {"id": LIT_ID}])
def test_negative_c_non_string_rule_id(value):
    record = _record([{"rule_id": value, "rule_type": C.LITERAL}])
    failures = attribution.identity_failures(record, EXPECTED, DIGEST)
    assert "malformed_rule_id:0" in failures and f"missing_identity:{LIT_ID}" in failures
    assert attribution.attributed_identities(record, DIGEST) == []


def test_negative_d_wrong_well_formed_rule_id():
    wrong = "ADR-9102:FORBID_LITERAL:" + "1" * 32
    failures = attribution.identity_failures(
        _record([{"rule_id": wrong, "rule_type": C.LITERAL}]), EXPECTED, DIGEST)
    assert f"extra_identity:{wrong}" in failures and f"missing_identity:{LIT_ID}" in failures


def test_negative_e_duplicate_rule_id():
    entry = {"rule_id": LIT_ID, "rule_type": C.LITERAL}
    failures = attribution.identity_failures(_record([entry, dict(entry)]), EXPECTED, DIGEST)
    assert failures == [f"duplicate_identity:{LIT_ID}"]


def test_negative_f_extraneous_valid_identity():
    other = "ADR-9199:FORBID_LITERAL:" + "2" * 32
    failures = attribution.identity_failures(_record([
        {"rule_id": LIT_ID, "rule_type": C.LITERAL}, {"rule_id": other, "rule_type": C.LITERAL},
    ]), EXPECTED, DIGEST)
    assert failures == [f"extra_identity:{other}"]


@pytest.mark.parametrize("record", [
    _record([{"rule_id": LIT_ID, "rule_type": C.LITERAL}], trusted=False),
    _record([{"rule_id": LIT_ID, "rule_type": C.LITERAL}], trusted="true"),
    _record([{"rule_id": LIT_ID, "rule_type": C.LITERAL}], digest="b" * 64),
    _record([{"rule_id": LIT_ID, "rule_type": C.LITERAL}],
            subject={"input_kind": "proposed_new_source", "subject_sha256": "c" * 64}),
    {"carrier_sha256": DIGEST, "violations": [{"rule_id": LIT_ID, "rule_type": C.LITERAL}],
     "checker": None},
])
def test_negative_g_untrusted_or_inconsistent_checker_data(record):
    failures = attribution.identity_failures(record, EXPECTED, DIGEST)
    assert failures and f"missing_identity:{LIT_ID}" in failures
    assert attribution.attributed_identities(record, DIGEST) == []


def test_wrong_rule_type_fails_and_no_type_only_fallback():
    failures = attribution.identity_failures(
        _record([{"rule_id": LIT_ID, "rule_type": C.NUMERIC}]), EXPECTED, DIGEST)
    assert failures == [f"wrong_rule_type:{LIT_ID}:{C.NUMERIC}"]
    only_type = attribution.identity_failures(_record([{"rule_type": C.LITERAL}]), EXPECTED, DIGEST)
    assert f"missing_identity:{LIT_ID}" in only_type


# ── oracle on scorer-authored synthetic cases ────────────────────────────────


def _symlinks_ok(tmp_path):
    try:
        os.symlink("x", tmp_path / "probe-link", target_is_directory=True)
    except OSError:
        return False
    return True


def _derive(case, tmp_path):
    root, outside = tmp_path / case["case_id"] / "root", tmp_path / case["case_id"] / "outside"
    runner.materialize(case, root, outside)
    (root / ".mneme").mkdir()
    (root / ".mneme" / "project_memory.json").write_text("{}", encoding="utf-8")
    return oracle.derive(case, root.resolve(), outside.resolve())


def _synthetic(case_id):
    return copy.deepcopy(next(c for c in synthetic.build_cases() if c["case_id"] == case_id))


@pytest.mark.parametrize("case", synthetic.build_cases(), ids=lambda c: c["case_id"])
def test_oracle_agrees_with_hand_labels(case, tmp_path):
    if any(f["type"].endswith("symlink") for f in case["fixture"]["files"]) and not _symlinks_ok(tmp_path):
        pytest.skip("symlink capability unavailable")
    exp = _derive(copy.deepcopy(case), tmp_path)
    assert exp.conflicts == [] and exp.notes == []


def test_at_si_semantics(tmp_path):
    exp = _derive(_synthetic("syn-at-si"), tmp_path)
    assert exp.checker_subject_kind == "unverified_input" and exp.record_subject is None
    assert exp.applied_rule_ids == [] and exp.per_rule_relevance == {} and exp.event_relevance is False
    assert exp.cause == "other_rule" and exp.disposition == "refused" and exp.evaluation_complete is True
    (rid, (outcome, mechanism)), = exp.numeric_applicability.items()
    assert (outcome, mechanism) == ("EXCLUDED", "include_miss")


def test_at_sx_uses_exclude_match(tmp_path):
    exp = _derive(_synthetic("syn-at-sx"), tmp_path)
    assert list(exp.numeric_applicability.values()) == [["EXCLUDED", "exclude_match"]]


@pytest.mark.parametrize("mutate, conflict", [
    (lambda l: l["evidence"].update(per_rule_relevance={"x": True}), "evidence.per_rule_relevance"),
    (lambda l: l["checker"].update(subject_kind="proposed_new_source"), "checker.subject_kind"),
    (lambda l: l["evidence"].update(checker_subject="proposed_new_source"), "evidence.checker_subject"),
    (lambda l: l["evidence"]["violations"][0].update(rule_id=LIT_ID), "evidence.violations"),
    (lambda l: l.update(expected_cause="numeric_violation"), "expected_cause"),
    (lambda l: l["checker"]["numeric_rules"][0].update(applicability="APPLIED"), "applicability"),
])
def test_label_disagreement_is_an_oracle_conflict(mutate, conflict, tmp_path):
    case = _synthetic("syn-at-si")
    mutate(case["labels"])
    exp = _derive(case, tmp_path)
    assert any(c.startswith(conflict) for c in exp.conflicts)


def test_participation_is_a_union_and_exemptions_are_not_widened(tmp_path):
    case = _synthetic("syn-at-si")
    case["labels"]["gates"] = ["G3"]
    case["labels"]["g5"]["cr_exception"] = True
    exp = _derive(case, tmp_path)
    assert exp.participation["G1"] and exp.participation["G6"]
    assert exp.g5["cr_exception"] is False


# ── gates on fabricated observations ─────────────────────────────────────────


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _proc(exit_=0, stdout=b"", stderr=b""):
    return {"exit": exit_, "stdout_b64": _b64(stdout), "stderr_b64": _b64(stderr)}


def _good_obs(case, exp):
    """An observation that matches the expectation exactly (the positive control)."""
    subject = None
    if exp.record_subject:
        subject = {"input_kind": exp.record_subject, "subject_sha256": exp.content_sha256,
                   "target_path": str(Path(exp.target).resolve()), "governed_path": exp.governed_path,
                   "absence_verified": True}
    rules = [{"rule_id": rid, "decision_version_id": "dver-x", "governed_path": exp.governed_path,
              "applicability": "APPLIED", "subject_sha256": exp.content_sha256,
              **{k: exp.numeric_outcomes[rid][k] for k in ("matcher_status", "matcher_outcome", "primary_reason")}}
             for rid in exp.applied_rule_ids]
    record = {
        "schema": C.EVIDENCE_SCHEMA, "surface": C.EVIDENCE_SURFACE, "mneme_version": "0.10.0",
        "host": {"version": HOST[0], "executable_sha256": HOST[1]},
        "event": {"tool_name": "Write", "file_path": exp.target, "cwd": exp.root,
                  "identifiers": {"session_id": runner.SESSION_ID}},
        "carrier_sha256": exp.content_sha256,
        "checker": {"trusted": True, "problem": "", "subject": subject,
                    "evaluation_complete": exp.evaluation_complete},
        "rules": rules,
        "violations": [{"rule_id": rid, "rule_type": rt} for rid, rt in exp.violations],
        "hook_outcome": exp.disposition, "disposition": {"mode": exp.mode, "cause": exp.cause},
    }
    traces = [{"rule_id": rid, "rule_type": C.NUMERIC, **exp.numeric_outcomes[rid],
               "unknown_sources": [{"reason": r} for r in exp.numeric_outcomes[rid]["unknown_reasons"]]}
              for rid in exp.applied_rule_ids]
    payload = {"applicability": traces}
    if exp.checker_subject_kind != "absent":
        payload["subject"] = {"input_kind": exp.checker_subject_kind}
    obs = {
        "pre": {"kind": "absent"}, "post_direct": {"kind": "absent"}, "post": {"kind": "absent"},
        "hook": _proc(exp.exit or 0), "direct_payload": payload,
        "records": [record] if exp.record_expected else [],
        "pinned_g6": {"per_rule": dict(exp.per_rule_relevance), "event": exp.event_relevance,
                      "complete": exp.evaluation_complete} if exp.record_expected else None,
    }
    if exp.g5.get("hook_level"):
        obs["base_hook"] = _proc(exp.exit or 0)
    if exp.g5.get("checker_level"):
        obs["parity_proposed"] = obs["parity_input"] = _proc(0, b"{}")
    return obs


def _score(case, exp, obs, obs_b=None):
    obs_b = obs if obs_b is None else obs_b
    expected_versions = {rid: "dver-x" for rid in exp.applied_rule_ids}
    return gates.score_case(case, [(exp, obs), (exp, obs_b)], {"ok": True}, HOST, [],
                            "0.10.0", expected_versions)


def _failures(result, gate):
    return result["gates"][gate]["failures"]


@pytest.fixture
def at_si(tmp_path):
    case = _synthetic("syn-at-si")
    exp = _derive(case, tmp_path)
    return case, exp, _good_obs(case, exp)


@pytest.fixture
def vp_like(tmp_path):
    case = _synthetic("syn-lit-mixed")
    exp = _derive(case, tmp_path)
    return case, exp, _good_obs(case, exp)


def test_positive_control_case_passes(at_si, vp_like):
    for case, exp, obs in (at_si, vp_like):
        assert _score(case, exp, obs)["passed"], _score(case, exp, obs)


def test_g1_refusal_not_observed_is_unsafe_pass(at_si):
    case, exp, obs = at_si
    obs["hook"] = _proc(0)
    assert "A:unsafe_pass:expected_refusal_not_observed" in _failures(_score(case, exp, obs), "G1")


def test_g1_unexpected_relevance_is_unsafe_pass(at_si):
    case, exp, obs = at_si
    obs["pinned_g6"] = {"per_rule": {"ADR-X:FORBID_NUMERIC_ABOVE:1": True}, "event": True, "complete": True}
    failures = _failures(_score(case, exp, obs), "G1")
    assert "A:unsafe_pass:unexpected_event_relevance" in failures


def test_g1_nonclean_observed_clean(vp_like):
    case, exp, obs = vp_like
    rid = exp.applied_rule_ids[0]
    obs["direct_payload"]["applicability"][0]["matcher_outcome"] = "NO_VIOLATION"
    assert f"A:unsafe_pass:nonclean_observed_clean:checker:{rid}" in _failures(_score(case, exp, obs), "G1")


def test_g2_false_block(tmp_path):
    case = _synthetic("syn-p-crlf")
    exp = _derive(case, tmp_path)
    obs = _good_obs(case, exp)
    obs["hook"] = _proc(2)
    assert "A:false_block" in _failures(_score(case, exp, obs), "G2")


def test_g3_target_created(at_si):
    case, exp, obs = at_si
    obs["post"] = {"kind": "file", "sha256": "d" * 64}
    assert "A:target_created" in _failures(_score(case, exp, obs), "G3")


def test_g4_primary_reason_mismatch(tmp_path):
    case = _synthetic("syn-lit-mixed")
    entry = case["labels"]["checker"]["numeric_rules"][0]
    entry.update(matcher_status="PARTIAL", primary_reason="SOURCE_NOT_FOUND", unknown_reasons=["SOURCE_NOT_FOUND"])
    case["labels"]["checker"]["evaluation_complete"] = False
    case["labels"]["evidence"]["evaluation_complete"] = False
    case["labels"]["gates"].append("G4")
    exp = _derive(case, tmp_path)
    assert exp.conflicts == []
    obs = _good_obs(case, exp)
    assert _score(case, exp, obs)["passed"]
    obs["direct_payload"]["applicability"][0]["primary_reason"] = "UNRECOGNIZED_FORM"
    rid = exp.applied_rule_ids[0]
    assert f"A:primary_reason:checker:{rid}" in _failures(_score(case, exp, obs), "G4")


@pytest.mark.parametrize("mutate, code", [
    (lambda o, e: o["records"][0]["checker"].update(subject={"input_kind": "proposed_new_source"}),
     "A:record_subject_unexpected"),
    (lambda o, e: o["records"][0]["violations"].append({"rule_type": C.LITERAL}), "A:attribution:malformed_rule_id:1"),
    (lambda o, e: o["records"][0]["violations"].clear(), "A:attribution:missing_identity:"),
    (lambda o, e: o["records"][0]["rules"].append({"rule_id": "ADR-X:FORBID_NUMERIC_ABOVE:9"}), "A:step1_rule_id_set"),
    (lambda o, e: o["records"][0]["disposition"].update(cause="numeric_violation"), "A:disposition_cause:"),
    (lambda o, e: o["records"][0].update(carrier_sha256="e" * 64), "A:join_digest"),
    (lambda o, e: o["records"][0]["event"].update(file_path="elsewhere.py"), "A:join_path:event"),
    (lambda o, e: o["records"][0]["host"].update(version="2.1.310"), "A:host_identity"),
    (lambda o, e: o["records"].append(copy.deepcopy(o["records"][0])), "A:record_count:2"),
    (lambda o, e: o["direct_payload"].update(subject={"input_kind": "proposed_new_source"}),
     "A:checker_subject_kind:proposed_new_source"),
    (lambda o, e: o["pinned_g6"].update(complete=None), "A:step4_evaluation_complete:None"),
])
def test_g6_failures(at_si, mutate, code):
    case, exp, obs = at_si
    mutate(obs, exp)
    assert any(f.startswith(code) for f in _failures(_score(case, exp, obs), "G6")), code


def test_g6_rule_id_set_is_checked_before_values(vp_like):
    case, exp, obs = vp_like
    obs["records"][0]["rules"] = []
    obs["pinned_g6"] = {"per_rule": {}, "event": False, "complete": True}
    failures = _failures(_score(case, exp, obs), "G6")
    assert "A:step1_rule_id_set" in failures
    assert not any("step2" in f for f in failures)


def test_g6_unrouted_case_must_have_no_record(tmp_path):
    case = _synthetic("syn-l-outside")
    exp = _derive(case, tmp_path)
    obs = _good_obs(case, exp)
    assert _score(case, exp, obs)["passed"]
    obs["records"] = [{"schema": C.EVIDENCE_SCHEMA}]
    assert "A:unexpected_record" in _failures(_score(case, exp, obs), "G6")


def test_routed_fallback_trusted_false_passes_and_null_fails(tmp_path):
    """R2 A2R2.4: trusted legacy ``false`` passes step 4; untrusted ``null`` fails."""
    if not _symlinks_ok(tmp_path):
        pytest.skip("symlink capability unavailable")
    case = _synthetic("syn-l-fallback")
    exp = _derive(case, tmp_path)
    assert exp.evaluation_complete is False and exp.fallback_numeric
    obs = _good_obs(case, exp)
    assert _score(case, exp, obs)["passed"]
    obs["pinned_g6"]["complete"] = None
    assert "A:step4_evaluation_complete:None" in _failures(_score(case, exp, obs), "G6")


_TB = b"Traceback (most recent call last):\n"


@pytest.mark.parametrize("cur, base, ok", [
    (_proc(0, b"", b"x\n"), _proc(0, b"", b"x\n"), True),
    (_proc(0, b"", b"x\n"), _proc(0, b"", b"y\n"), False),
    (_proc(1, b"", _TB + b'  File "h.py", line 920\nE: boom\n'), _proc(1, b"", _TB + b'  File "h.py", line 797\nE: boom\n'), True),
    (_proc(1, b"", _TB + b'  File "h.py", line 920\nE: boom\n'), _proc(1, b"", _TB + b'  File "h.py", line 797\nE: bang\n'), False),
    (_proc(0, b"", b""), _proc(1, b"", _TB + b'  File "h.py", line 1\nE: boom\n'), False),
    (_proc(1, b"", _TB + b'  File "h.py", line 9\nE: boom\nextra\n'), _proc(1, b"", _TB + b'  File "h.py", line 1\nE: boom\n'), False),
])
def test_g5_hook_parity_and_amendment_2(cur, base, ok):
    assert (gates.hook_parity(cur, base) == []) is ok


def test_g5_raw_bytes_outside_amendment_2_scope():
    cur = _proc(1, b"", b"Traceback (most recent call last):\n  File a\nE: x\n")
    base = _proc(0, b"", b"Traceback (most recent call last):\n  File b\nE: x\n")
    assert gates.hook_parity(cur, base) == ["hook_parity:stderr", "hook_parity:exit"]


def test_g7_runs_differ(at_si):
    case, exp, obs = at_si
    other = copy.deepcopy(obs)
    other["hook"] = _proc(2, b"", b"different")
    assert _failures(_score(case, exp, obs, other), "G7") == ["runs_differ"]


def test_g8_operational_failure_fails_every_gate(at_si):
    case, exp, obs = at_si
    result = gates.score_case(case, [(exp, obs), (None, {"error": "harness: timeout"})],
                              {"ok": True}, HOST, [], "0.10.0", {})
    assert not result["passed"] and "harness: timeout" in _failures(result, "G8")
    bad_compile = gates.score_case(case, [(exp, obs), (exp, obs)], {"ok": False}, HOST,
                                   [], "0.10.0", {})
    assert "memory_compile_failed" in _failures(bad_compile, "G8")


# ── corpus decision ─────────────────────────────────────────────────────────


def _result(cid, cls, passed=True, visibility="concealed", subclass=None):
    return {"case_id": cid, "cls": cls, "subclass": subclass, "visibility": visibility, "passed": passed,
            "gates": {g: {"applies": True, "result": "pass" if passed else "fail", "failures": []} for g in C.GATES}}


def _concealed_corpus():
    cases = []
    for cls, floor in C.CLASS_FLOORS.items():
        subs = [s for s, n in C.AT_SUBCLASS_FLOORS.items() for _ in range(n)] if cls == "AT" else [None] * floor
        cases += [{"case_id": f"{cls}-{i}", "cls": cls, "subclass": s, "visibility": "concealed"}
                  for i, s in enumerate(subs)]
    return cases


def test_public_scoring_never_yields_a_verdict():
    decision = gates.decide([_result("a", "V", visibility="public")], {"met": True},
                            {"capable": True}, "public", {"manifest": None})
    assert decision["verdict"] == "NO_VERDICT_PUBLIC_SMOKE"


def test_concealed_floors_and_decision():
    cases = _concealed_corpus()
    floor = gates.floors(cases)
    assert floor["total_floor_met"] and floor["concealed"] == C.TOTAL_FLOOR
    assert not floor["met"] and "coverage_not_checked" in floor["coverage"]["shortfalls"]
    # This unit tests verdict aggregation, not corpus eligibility. Supply a
    # synthetic positive coverage control explicitly; the real entry point
    # requires independent passes and will never infer one from counts.
    floor["coverage"] = {"met": True}
    floor["met"] = True
    results = [_result(c["case_id"], c["cls"], subclass=c["subclass"]) for c in cases]
    ok = {"capable": True}
    valid = {"manifest": {"entries": len(results), "mismatches": []}}
    assert gates.decide(results, floor, ok, "concealed", valid)["verdict"] == "PASS"
    no_manifest = copy.deepcopy(results)
    blocked = gates.decide(no_manifest, floor, ok, "concealed", {"manifest": None})
    assert blocked["verdict"] == "FAIL"
    assert not blocked["integrity_ok"]
    assert blocked["per_gate"]["G8"]["denominator"] == len(results)
    assert len(blocked["per_gate"]["G8"]["failed"]) == len(results)
    assert all("corpus_manifest_integrity" in r["gates"]["G8"]["failures"] for r in no_manifest)
    partial = gates.decide(copy.deepcopy(results), floor, ok, "concealed",
                           {"manifest": {"entries": 1, "mismatches": ["manifest_incomplete_inventory"]}})
    assert partial["verdict"] == "FAIL"
    results[0]["passed"] = False
    assert gates.decide(results, floor, ok, "concealed", valid)["verdict"] == "FAIL"
    assert gates.decide(copy.deepcopy(results), floor, {"capable": False}, "concealed", valid)["verdict"] == "INCOMPLETE"


def test_floor_shortfall_and_superseded_at_sn():
    cases = _concealed_corpus()
    for case in cases:
        if case["subclass"] == "AT-SI":
            case["subclass"] = "AT-SN"
    floor = gates.floors(cases)
    assert not floor["met"] and "AT-SI" in floor["at_floor_shortfalls"]


# ── sealed corpus manifest integrity: synthetic files only ────────────────────


def _synthetic_manifest_corpus(tmp_path):
    root = tmp_path / "synthetic-r3"
    root.mkdir()
    data = {"schema": C.CASE_SCHEMA, "case_id": "synthetic-1"}
    path = root / "synthetic-1" / "case.json"
    path.parent.mkdir()
    path.write_text(__import__("json").dumps(data) + "\n", encoding="utf-8")
    return root, path


def _write_file_manifest(root, paths):
    lines = []
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(root).as_posix()}\n")
    (root / "MANIFEST.sha256").write_text("".join(sorted(lines)), encoding="utf-8")


def test_manifest_complete_synthetic_inventory(tmp_path):
    root, case_path = _synthetic_manifest_corpus(tmp_path)
    readme = root / "README.txt"
    readme.write_text("synthetic metadata\n", encoding="utf-8")
    _write_file_manifest(root, [case_path, readme])
    cases, integrity = runner.load_corpus(root)
    assert len(cases) == 1
    assert integrity["manifest"] == {"entries": 2, "mismatches": []}


def test_manifest_missing_fails_closed(tmp_path):
    root, _ = _synthetic_manifest_corpus(tmp_path)
    _, integrity = runner.load_corpus(root)
    assert "manifest_missing" in integrity["manifest"]["mismatches"]


def test_manifest_subset_fails_closed(tmp_path):
    root, case_path = _synthetic_manifest_corpus(tmp_path)
    extra = root / "metadata.txt"
    extra.write_text("extra", encoding="utf-8")
    _write_file_manifest(root, [case_path])
    _, integrity = runner.load_corpus(root)
    assert "manifest_incomplete_inventory" in integrity["manifest"]["mismatches"]


def test_manifest_missing_case_entry_fails_closed(tmp_path):
    root, case_path = _synthetic_manifest_corpus(tmp_path)
    _write_file_manifest(root, [])
    _, integrity = runner.load_corpus(root)
    assert "manifest_incomplete_inventory" in integrity["manifest"]["mismatches"]


def test_manifest_modified_file_fails_closed(tmp_path):
    root, case_path = _synthetic_manifest_corpus(tmp_path)
    _write_file_manifest(root, [case_path])
    case_path.write_text(case_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    # The payload stays valid JSON; only its digest no longer matches.
    _, integrity = runner.load_corpus(root)
    assert "manifest_digest_mismatch" in integrity["manifest"]["mismatches"]


def test_manifest_duplicate_entry_fails_closed(tmp_path):
    root, case_path = _synthetic_manifest_corpus(tmp_path)
    _write_file_manifest(root, [case_path])
    manifest = root / "MANIFEST.sha256"
    manifest.write_text(manifest.read_text(encoding="utf-8") * 2, encoding="utf-8")
    _, integrity = runner.load_corpus(root)
    assert "manifest_duplicate_entry" in integrity["manifest"]["mismatches"]


@pytest.mark.parametrize("invalid", ["../outside.txt", "/absolute.txt", "folder/../../escape"])
def test_manifest_traversal_fails_closed(tmp_path, invalid):
    root, case_path = _synthetic_manifest_corpus(tmp_path)
    _write_file_manifest(root, [case_path])
    manifest = root / "MANIFEST.sha256"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "0" * 64 + "  " + invalid + "\n",
        encoding="utf-8")
    _, integrity = runner.load_corpus(root)
    assert "manifest_invalid_path" in integrity["manifest"]["mismatches"]


def test_public_scoring_without_manifest_never_claims_pass():
    decision = gates.decide([_result("public-1", "V", visibility="public")],
                            {"met": True}, {"capable": True}, "public",
                            {"manifest": {"entries": 0, "mismatches": ["manifest_missing"]}})
    assert decision["verdict"] == "NO_VERDICT_PUBLIC_SMOKE"
    assert not decision["integrity_ok"]



def test_manifest_rejects_files_outside_inner_root(tmp_path):
    parent = tmp_path / "extracted"
    parent.mkdir()
    root, case_path = _synthetic_manifest_corpus(parent)
    _write_file_manifest(root, [case_path])
    (parent / "unlisted.txt").write_text("unlisted", encoding="utf-8")
    _, integrity = runner.load_corpus(parent)
    assert "file_outside_manifest_scope" in integrity["manifest"]["mismatches"]


def test_manifest_rejects_non_regular_symlink(tmp_path):
    root, case_path = _synthetic_manifest_corpus(tmp_path)
    target = root / "linked"
    try:
        target.symlink_to(case_path)
    except OSError:
        pytest.skip("symlinks not available on this test host")
    _write_file_manifest(root, [case_path])
    _, integrity = runner.load_corpus(root)
    assert "manifest_incomplete_inventory" in integrity["manifest"]["mismatches"]


# ── F1/F2/F3/F4 independent synthetic regression controls ────────────────────


@pytest.mark.parametrize("current, baseline", [
    (b'Traceback (most recent call last):\n  File "a.py", line 1\nE: boom',
     b'Traceback (most recent call last):\n  File "b.py", line 2\nE: boom\n'),
    (b'Traceback (most recent call last):\r\n  File "a.py", line 1\r\nE: boom\r\n',
     b'Traceback (most recent call last):\n  File "b.py", line 2\nE: boom\n'),
    (b'Traceback (most recent call last):\n  File "a.py", line 1\nE: boom\nnext\n',
     b'Traceback (most recent call last):\n  File "b.py", line 2\nE: boom\nnext'),
    (b'Traceback (most recent call last):\n  File "a.py", line 1\nE: boom\n'
     b'During handling of the above exception, another exception occurred:\n'
     b'Traceback (most recent call last):\n  File "a.py", line 3\nF: bang\n',
     b'Traceback (most recent call last):\n  File "b.py", line 2\nE: boom\n'
     b'During handling of the above exception, another exception occurred:\r\n'
     b'Traceback (most recent call last):\n  File "b.py", line 4\nF: bang\n'),
])
def test_f1_amendment2_preserves_nonframe_bytes(current, baseline):
    assert "hook_parity:a2_stderr" in gates.hook_parity(
        _proc(1, b"", current), _proc(1, b"", baseline))


def test_f1_amendment2_still_ignores_only_frame_bytes():
    a = (b'Traceback (most recent call last):\n  File "a.py", line 4\n'
         b'E: boom\nDuring handling of the above exception, another exception occurred:\n'
         b'Traceback (most recent call last):\n  File "a.py", line 5\nF: bang\n')
    b = a.replace(b'a.py", line 4', b'b.py", line 80').replace(
        b'a.py", line 5', b'b.py", line 70')
    assert gates.hook_parity(_proc(1, b"", a), _proc(1, b"", b)) == []


def test_f2_mneme_version_mismatch_fails_g6(at_si):
    case, exp, obs = at_si
    obs["records"][0]["mneme_version"] = "9.9.9"
    assert "A:mneme_version_mismatch" in _failures(_score(case, exp, obs), "G6")


def test_f2_missing_mneme_pin_fails_g6(at_si):
    case, exp, obs = at_si
    result = gates.score_case(case, [(exp, obs), (exp, obs)], {"ok": True},
                              HOST, [], "", {})
    assert "A:mneme_version_mismatch" in _failures(result, "G6")


@pytest.mark.parametrize("version", ["", None, "dver-other"])
def test_f2_wrong_compiled_decision_version_fails_g6(vp_like, version):
    case, exp, obs = vp_like
    obs["records"][0]["rules"][0]["decision_version_id"] = version
    assert any("record_decision_version_id:" in err
               for err in _failures(_score(case, exp, obs), "G6"))


def test_f2_missing_compiled_version_map_fails_g6(vp_like):
    case, exp, obs = vp_like
    result = gates.score_case(case, [(exp, obs), (exp, obs)], {"ok": True},
                              HOST, [], "0.10.0", {})
    assert any("record_decision_version_id:" in err
               for err in _failures(result, "G6"))


def test_f4_wrong_nonrefusing_disposition_is_unsafe_pass(at_si):
    case, exp, obs = at_si
    assert obs["hook"]["exit"] == 2
    obs["records"][0]["hook_outcome"] = "proceeded"
    assert "A:unsafe_pass:expected_refusal_wrong_disposition" in _failures(
        _score(case, exp, obs), "G1")


def test_f3_class_floors_alone_cannot_earn_pass():
    cases = _concealed_corpus()
    floor = gates.floors(cases)
    assert floor["total_floor_met"] and not floor["met"]
    results = [_result(c["case_id"], c["cls"], subclass=c["subclass"]) for c in cases]
    assert gates.decide(results, floor, {"capable": True}, "concealed",
                        {"manifest": {"entries": 128, "mismatches": []}})["verdict"] == "FAIL"


def test_f3_at_si_and_at_sx_mechanism_derived_from_fixture(tmp_path):
    public = _synthetic("syn-at-w0-lit")
    cases, passes = [public], {}
    for cid in ("syn-at-si", "syn-at-sx"):
        case = copy.deepcopy(_synthetic(cid))
        case["visibility"] = "concealed"
        exp = _derive(case, tmp_path)
        cases.append(case)
        passes[cid] = [(exp, _good_obs(case, exp))]
    result = coverage.inspect(cases, passes)
    # Both mechanisms are valid, but one case each is not two distinct pairs.
    assert "AT-SI:wrong_exclusion_mechanism" not in result["shortfalls"]
    assert "AT-SX:wrong_exclusion_mechanism" not in result["shortfalls"]
    assert "AT-SI:not_two_distinct_literal_identities_and_scopes" in result["shortfalls"]
    assert "AT-SX:not_two_distinct_ADR_fixtures_or_literal_identities" in result["shortfalls"]

    si = cases[1]
    si["subclass"] = "AT-SX"
    mislabeled = coverage.inspect(cases, passes)
    assert "AT-SX:wrong_exclusion_mechanism" in mislabeled["shortfalls"]


def test_f3_rejects_incomplete_lit_and_at_w0_distributions(tmp_path):
    public = _synthetic("syn-at-si")
    cases, passes = [public], {}
    for cid in ("syn-lit-mixed", "syn-at-w0-lit"):
        case = copy.deepcopy(_synthetic(cid))
        case["visibility"] = "concealed"
        exp = _derive(case, tmp_path)
        cases.append(case)
        passes[cid] = [(exp, _good_obs(case, exp))]
    coverage_result = coverage.inspect(cases, passes)
    assert coverage_result["counts"]["LIT:mixed_violation"] == 1
    assert "LIT:mixed_violation:below_minimum" in coverage_result["shortfalls"]
    assert "LIT:mixed_clean_refusal:below_minimum" in coverage_result["shortfalls"]
    assert "AT-W0:excluded_numeric:below_minimum" in coverage_result["shortfalls"]
    assert "SC:recognized_clean:below_minimum" in coverage_result["shortfalls"]
    assert "MR:literal_only_refusal_analogue:below_minimum" in coverage_result["shortfalls"]


def test_f3_missing_public_at_smoke_is_admission_failure():
    assert "public_AT_smoke_missing" in coverage.inspect([], {})["shortfalls"]


def test_f2_compiled_version_binding_from_fixture_memory():
    record = {"decision_index": {"rules": [
        {"rule_id": "synthetic-rule-1", "decision_version_id": "dver-synthetic-1"},
        {"rule_id": "synthetic-rule-2", "decision_version_id": "dver-synthetic-2"},
    ]}}
    raw_memory = _b64(json.dumps(record).encode("utf-8"))
    assert runner.compiled_rule_versions(raw_memory) == {
        "synthetic-rule-1": "dver-synthetic-1",
        "synthetic-rule-2": "dver-synthetic-2",
    }


@pytest.mark.parametrize("rules", [
    [{"rule_id": "rule-1", "decision_version_id": ""}],
    [{"rule_id": "rule-1", "decision_version_id": None}],
    [{"rule_id": "rule-1", "decision_version_id": "dver-x"},
     {"rule_id": "rule-1", "decision_version_id": "dver-y"}],
    [None],
])
def test_f2_compiled_version_binding_rejects_bad_memory(rules):
    memory = _b64(json.dumps({"decision_index": {"rules": rules}}).encode("utf-8"))
    with pytest.raises(runner.HarnessError):
        runner.compiled_rule_versions(memory)


def test_f3_rejects_unknown_classes_and_subclasses():
    unknown_class = {"case_id": "synthetic-unknown", "cls": "not-a-class",
                     "visibility": "concealed"}
    unknown_at = {"case_id": "synthetic-at-unknown", "cls": "AT",
                  "subclass": "AT-SN", "visibility": "concealed"}
    status = coverage.inspect([unknown_class, unknown_at], {})
    assert "unknown_class" in status["shortfalls"]
    assert "unknown_AT_subclass" in status["shortfalls"]
    assert not status["met"]


def test_f2_malformed_nonhashable_record_rule_id_fails_step1(vp_like):
    case, exp, obs = vp_like
    obs["records"][0]["rules"][0]["rule_id"] = {"malformed": "id"}
    assert "A:step1_rule_id_set" in _failures(_score(case, exp, obs), "G6")


# ── Frozen #703 public smoke stays in its own tar ─────────────────────────────


def _synthetic_public_tar(tmp_path, *, omit_at=False, damage_manifest=False):
    """An artificial separate public tar with its own complete manifest."""
    files = {}
    for cls in C.CLASS_FLOORS:
        if omit_at and cls == "AT":
            continue
        cid = "synthetic-public-" + cls
        files[f"{cid}/case.json"] = json.dumps({
            "schema": C.CASE_SCHEMA, "case_id": cid,
            "cls": cls, "visibility": "public",
        }, sort_keys=True).encode("utf-8")
    manifest = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n"
        for name, data in sorted(files.items())
    ).encode("ascii")
    if damage_manifest:
        manifest = manifest.replace(b"a", b"b", 1)
    files["MANIFEST.sha256"] = manifest
    archive = tmp_path / "synthetic-public.tar"
    with tarfile.open(archive, "w", format=tarfile.USTAR_FORMAT) as tf:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo("r3-public-smoke/" + name)
            info.size = len(data)
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def test_f3_concealed_only_accepts_verified_separate_public_archive(tmp_path):
    archive, digest = _synthetic_public_tar(tmp_path)
    evidence = public_smoke.verify(archive, digest)
    assert evidence["verified"]
    assert evidence["public_cases"] == 14
    assert set(evidence["classes"]) == set(C.CLASS_FLOORS)
    # No public cases are inserted into the concealed input or its manifest.
    cases = _concealed_corpus()
    floor = gates.floors(cases, passes={}, public_evidence=evidence)
    assert floor["concealed"] == 128
    assert floor["public"] == 14
    assert floor["public_smoke_rules_met"]
    assert "public_AT_smoke_missing" not in floor["coverage"]["shortfalls"]
    assert "public_smoke_separate_archive_not_verified" not in floor["coverage"]["shortfalls"]
    # Other distribution minima remain unproved, so the whole floor stays FAIL.
    assert floor["met"] is False


def test_f3_separate_public_tar_is_required_for_concealed_admission(tmp_path):
    cases = _concealed_corpus()
    missing = gates.floors(cases, passes={}, public_evidence={
        "verified": False, "reason": "public_smoke_tar_not_supplied",
        "public_cases": 0, "classes": [],
    })
    assert "public_smoke_separate_archive_not_verified" in missing["coverage"]["shortfalls"]
    assert missing["met"] is False
    result = gates.decide(
        [_result(c["case_id"], c["cls"], subclass=c["subclass"]) for c in cases],
        missing, {"capable": True}, "concealed",
        {"manifest": {"entries": 128, "mismatches": []}},
    )
    assert result["verdict"] == "FAIL"


def test_f3_public_archive_hash_mismatch_fails_closed(tmp_path):
    archive, _ = _synthetic_public_tar(tmp_path)
    assert public_smoke.verify(archive, "0" * 64)["reason"] == "public_tar_digest_mismatch"


def test_f3_public_archive_missing_at_fails_closed(tmp_path):
    archive, digest = _synthetic_public_tar(tmp_path, omit_at=True)
    assert public_smoke.verify(archive, digest)["reason"] == "public_case_count"


def test_f3_public_archive_manifest_tamper_fails_closed(tmp_path):
    archive, digest = _synthetic_public_tar(tmp_path, damage_manifest=True)
    result = public_smoke.verify(archive, digest)
    assert not result["verified"]
    assert result["reason"] in ("public_manifest_invalid", "public_manifest_digest_mismatch")

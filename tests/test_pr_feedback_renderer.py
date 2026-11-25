"""AP1.1: offline PR feedback renderer (scripts/ci/render_pr_feedback.py).

Acceptance matrix R01-R21 from the AP1.1 charter v2 plus the v2.1 addendum
(N1 aggregate/disposition consistency, N2(a) delimited escaping, N2(b) 17
mandatory keys, nested input_path rule). Expected headings and phrases are
written by hand from the charter, not generated from the renderer. Historical
reports are read in place and only mutated in memory.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RENDERER = REPO_ROOT / "scripts" / "ci" / "render_pr_feedback.py"
B_DIR = REPO_ROOT / "docs" / "validation" / "artifacts" / "verification-step3-e2e-fixture" / "ci-reports"
L_DIR = REPO_ROOT / "docs" / "validation" / "adr033-c4-gate3-live-2026-10-26" / "probes"


def _load():
    spec = importlib.util.spec_from_file_location("render_pr_feedback_under_test", RENDERER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


R = _load()

TITLE = "## Mneme Architecture Protection — offline preview"
H_UNAVAIL = "### Preview unavailable — report could not be displayed"
H_INCONS = "### Preview unavailable — inconsistent report"
H_PASS = "### Reported PASS — evaluated scope only"
H_WARN = "### Reported WARN — advisory findings (warn mode only)"
H_SKIP = "### Reported SKIP — no file required evaluation"
H_VIOL = "### Reported VIOLATION — strict gate failure (strict only)"
H_REF = "### Reported REFUSED — policy or trusted-surface refusal"
H_UNEV_OPEN = "### Reported UNEVALUATED — evaluation incomplete (open only)"
H_UNEV_CLOSED = "### Reported UNEVALUATED — evaluation incomplete (closed only)"
ALL_HEADINGS = [H_UNAVAIL, H_INCONS, H_PASS, H_WARN, H_SKIP, H_VIOL, H_REF, H_UNEV_OPEN, H_UNEV_CLOSED]

FORBIDDEN = ["merge blocked", "merge allowed", "safe to merge", "architecture compliant",
             "all decisions protected", "all rules passed", "relevant enforcement observed",
             "introduced violation", "verified compliant", "tamper-proof", "production ready"]

HIST = {
    "B1": B_DIR / "B1_allow.gate-report.json",
    "B2": B_DIR / "B2_bypass_violation.gate-report.json",
    "B3": B_DIR / "B3_incomplete_symlink.gate-report.json",
    "B4": B_DIR / "B4_missing_identity.gate-report.json",
    "B5": B_DIR / "B5_later_revision.gate-report.json",
    "L1": L_DIR / "L1" / "artifact" / "gate-report.json",
    "L2": L_DIR / "L2" / "artifact" / "gate-report.json",
    "L3": L_DIR / "L3" / "artifact" / "gate-report.json",
    "L4": L_DIR / "L4" / "artifact" / "gate-report.json",
    "L5": L_DIR / "L5" / "artifact" / "gate-report.json",
}


def hist(name):
    return json.loads(HIST[name].read_text(encoding="utf-8"))


def expected_for(report):
    return {"base_sha": report["base_sha"], "head_sha": report["head_sha"],
            "adapter_sha256": report["adapter"]["sha256"],
            "evaluator_commit": report["evaluator"]["commit"],
            "evaluator_wheel_sha256": report["evaluator"]["wheel_sha256"],
            "requested_mode": report["requested_mode"], "posture": report["posture"]["effective"]}


def dump(report):
    return json.dumps(report).encode("utf-8")


def go(report, expected=None):
    exp = expected if expected is not None else expected_for(report)
    return R.render(dump(report), exp)


def strip_spans(text):
    return re.sub(r"`[^`\n]*`", "", text)


def spans(text):
    return re.findall(r"`([^`\n]*)`", text)


def assert_safe(text):
    text.encode("utf-8")  # strict
    assert "\r" not in text
    assert "@" not in text and "<" not in text and ">" not in text and "&" not in text
    assert "](" not in text
    for line in text.split("\n"):
        assert not line.startswith("::")
    prose = strip_spans(text).lower()
    for phrase in FORBIDDEN:
        assert phrase not in prose
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert len(text.encode("utf-8")) <= 64 * 1024


def headings_in(text):
    return [l for l in text.split("\n") if l.startswith("### ")]


def assert_unavailable(code_text, heading=None):
    code, text = code_text
    assert code == 2
    assert text.startswith(TITLE + "\n")
    hs = headings_in(text)
    assert len(hs) == 1 and hs[0] in (H_UNAVAIL, H_INCONS)
    if heading:
        assert hs[0] == heading
    assert "Recorded adapter disposition" not in text
    assert "Reported " not in text
    assert_safe(text)


# ── synthetic builders (independent of the module under test) ────────────────

def stdout_for(verdict, mode, violations=(), applicability=()):
    return json.dumps({"schema": "mneme.check/v1", "verdict": verdict, "mode": mode,
                       "evaluation_complete": True, "applicability": list(applicability),
                       "violations": list(violations)})


def viol(path, **kw):
    v = {"decision_id": "ADR-1", "decision_text": "TXT", "severity": "FAIL", "rule": "RULE-SENTINEL",
         "trigger": "TRIGGER-SENTINEL", "input_path": path, "selector": "docs/**",
         "rule_id": "ADR-1:R:1", "decision_version_id": "dver-1"}
    v.update(kw)
    return v


def app(path, **kw):
    a = {"decision_id": "ADR-1", "decision_version_id": "dver-1", "rule_id": "ADR-1:R:1",
         "input_path": path, "outcome": "APPLIED",
         "rule_value": "VALUE-SENTINEL", "selector": "docs/**"}
    a.update(kw)
    return a


def row(path="docs/a.md", cls="VERIFIED_PASS", kind=None, stdout=None, status="A", mode="100644"):
    r = {"path": path, "status": status, "mode": mode, "classification": cls, "reason": "REASON-SENTINEL"}
    if kind:
        r["kind"] = kind
    if stdout is not None:
        r.update(sha256="0" * 64, exit=0, stdout=stdout, stderr_tail="STDERR-SENTINEL", applicability=[])
    return r


def cond(cls="REFUSED", kind="change_list"):
    return {"classification": cls, "kind": kind, "reason": "REASON-SENTINEL"}


def agg_of(classes, mode):
    s = set(classes)
    if "REFUSED" in s:
        return "REFUSED"
    if mode == "strict" and s & {"VIOLATION", "WARN"}:
        return "VIOLATION"
    if "UNEVALUATED" in s:
        return "UNEVALUATED"
    if s & {"VIOLATION", "WARN"}:
        return "WARN"
    if "VERIFIED_PASS" in s:
        return "PASS"
    return "SKIP"


def disp_of(agg, posture):
    if agg in ("REFUSED", "VIOLATION"):
        return "failure"
    if agg == "UNEVALUATED":
        return "success" if posture == "open" else "failure"
    return "success"


def make(files=(), conds=(), mode="strict", posture="closed", fallback=None):
    rep = copy.deepcopy(hist("B1"))
    rep["requested_mode"] = mode
    rep["posture"] = {"effective": posture, "source": "vars.MNEME_CI_AVAILABILITY", "fallback": fallback}
    rep["files"] = list(files)
    rep["gate_conditions"] = list(conds)
    classes = [r["classification"] for r in rep["files"] + rep["gate_conditions"]]
    agg = agg_of(classes, mode)
    order = ["VERIFIED_PASS", "WARN", "VIOLATION", "UNEVALUATED", "REFUSED", "SKIP"]
    rep["aggregate"] = {"classification": agg, "reason": "AGG-REASON-SENTINEL",
                        "partly_unevaluated": "UNEVALUATED" in classes,
                        "counts": {c: classes.count(c) for c in order if c in classes}}
    rep["disposition"] = disp_of(agg, posture)
    rep["annotations"] = ["::error title=X::ANNOTATION-SENTINEL"]
    rep["summary_written"] = True
    return rep


def viol_row(path="docs/a.md", mode="strict", verdict="FAIL", cls="VIOLATION", violations=None, applicability=None):
    v = [viol(path)] if violations is None else violations
    a = [app(path)] if applicability is None else applicability
    return row(path, cls, stdout=stdout_for(verdict, mode, v, a))


def pass_row(path="docs/p.md", mode="strict"):
    return row(path, "VERIFIED_PASS", stdout=stdout_for("PASS", mode))


# ── R01-R07: historical reports ──────────────────────────────────────────────

@pytest.mark.parametrize("name", ["B1", "L1", "B5"])
def test_r01_pass_reports_scoped_heading(name):
    code, text = go(hist(name))
    assert code == 0
    assert headings_in(text) == [H_PASS]
    assert "Recorded adapter disposition: `success`" in text
    assert "No violations reported in the evaluated scope." in text
    assert "per-rule" not in text.lower() and "allow" not in text.lower()
    assert_safe(text)


@pytest.mark.parametrize("name", ["B2", "L5"])
def test_r02_violation_reports_findings_without_literals(name):
    code, text = go(hist(name))
    assert code == 0
    assert headings_in(text) == [H_VIOL]
    assert "Recorded adapter disposition: `failure`" in text
    assert "`docs/" in text and "ADR-901" in text and "FAIL" in text
    assert "install legacy-client" not in text  # rule/trigger/rule_value
    assert "CI1 fixture" not in text  # decision_text
    assert " line" not in text.lower()
    assert_safe(text)


@pytest.mark.parametrize("name", ["B3", "L2"])
def test_r03_closed_unevaluated_is_not_violation(name):
    code, text = go(hist(name))
    assert code == 0
    assert headings_in(text) == [H_UNEV_CLOSED]
    assert "Recorded adapter disposition: `failure`" in text
    assert "VIOLATION" not in text.replace(H_UNEV_CLOSED, "")
    assert_safe(text)


def test_r04_open_unevaluated_success_is_never_pass():
    code, text = go(hist("L3"))
    assert code == 0
    assert headings_in(text) == [H_UNEV_OPEN]
    assert "Recorded adapter disposition: `success`" in text
    assert "not a successful evaluation" in text
    assert "Reported PASS" not in text
    assert_safe(text)


def test_r05_refused_trusted_surface_uses_kind_label_only():
    code, text = go(hist("L4"))
    assert code == 0
    assert headings_in(text) == [H_REF]
    assert "Trusted-surface path" in text
    assert "`gate/c4-l4-note.txt`" in text
    assert "trusted_surface" not in text  # raw kind never shown
    assert_safe(text)


def test_r06_b4_missing_version_identity_is_unavailable_not_replaced():
    code, text = go(hist("B4"))
    assert code == 0
    assert "version Unavailable" in text
    assert "dver-" not in text
    assert "decision `ADR-901`" in text


@pytest.mark.parametrize("ver", [None, "", "ABSENT"])
def test_r06_synthetic_absent_null_empty_version(ver):
    v = viol("docs/a.md")
    if ver == "ABSENT":
        del v["decision_version_id"]
    else:
        v["decision_version_id"] = ver
    code, text = go(make([viol_row(violations=[v])]))
    assert code == 0 and "version Unavailable" in text and "dver-1" not in text


def test_r07_b5_matching_and_mismatched_context():
    rep = hist("B5")
    code, text = go(rep)
    assert code == 0 and headings_in(text) == [H_PASS]
    pins = dict(l.split(" ", 1) for l in (B_DIR / "pins.txt").read_text().splitlines())
    assert pins["adapter_sha256"] == rep["adapter"]["sha256"]
    assert pins["evaluator_commit"] == rep["evaluator"]["commit"]
    for field, value in [("base_sha", "0" * 40), ("head_sha", "1" * 40), ("adapter_sha256", "2" * 64),
                         ("evaluator_commit", "3" * 40), ("evaluator_wheel_sha256", "4" * 64),
                         ("requested_mode", "warn"), ("posture", "open")]:
        exp = expected_for(rep)
        exp[field] = value
        res = R.render(dump(rep), exp)
        assert_unavailable(res, H_UNAVAIL)
        assert f"context mismatch: {field}" in res[1]
        assert value not in res[1]
        assert "Report context" not in res[1]


# ── R08-R10 ──────────────────────────────────────────────────────────────────

def test_r08_strict_warn_is_violation_and_warn_mode_fail_is_warn():
    rep = make([viol_row(verdict="WARN", cls="WARN", violations=[viol("docs/a.md", severity="WARN")])])
    code, text = go(rep)
    assert code == 0 and headings_in(text) == [H_VIOL]
    assert "severity `WARN`" in text and "WARN: 1" in text
    rep = make([viol_row(mode="warn")], mode="warn")
    code, text = go(rep)
    assert code == 0 and headings_in(text) == [H_WARN]
    assert "severity `FAIL`" in text and "VIOLATION: 1" in text
    assert "Recorded adapter disposition: `success`" in text


def test_r09_mixed_statuses_are_all_preserved():
    rep = make([viol_row("docs/v.md"), row("docs/r.md", "REFUSED", "policy"),
                row("docs/u.md", "UNEVALUATED", "mode"), pass_row("docs/p.md")],
               [cond("REFUSED", "change_list")])
    code, text = go(rep)
    assert code == 0 and headings_in(text) == [H_REF]
    for needle in ["REFUSED: 1", "VIOLATION: 1", "UNEVALUATED: 1", "VERIFIED_PASS: 1",
                   "File rows: 4 (", "Partly unevaluated: yes", "Gate conditions: 1 (REFUSED: 1)",
                   "Change list could not be established", "Policy path", "Not a regular file",
                   "Notice: unevaluated rows", "Notice: refused rows", "Notice: violation rows"]:
        assert needle in text
    rep = make([viol_row(mode="warn", cls="WARN", verdict="WARN",
                         violations=[viol("docs/a.md", severity="WARN")]),
                row("docs/u.md", "UNEVALUATED", "mode")], mode="warn", posture="open")
    code, text = go(rep)
    assert headings_in(text) == [H_UNEV_OPEN] and "WARN: 1" in text and "UNEVALUATED: 1" in text


def test_r10_skip_only_empty_and_deleted():
    code, text = go(make([]))
    assert code == 0 and headings_in(text) == [H_SKIP] and "No violations reported" not in text
    code, text = go(make([row("docs/gone.md", "SKIP", "deleted", status="D")]))
    assert headings_in(text) == [H_SKIP]
    assert "Deleted file, not evaluated" in text and "not an allowance" in text
    assert "Reported PASS" not in text
    assert_safe(text)


# ── R11: unavailable matrix ──────────────────────────────────────────────────

@pytest.mark.parametrize("data", [b"", b"not json", b"[]", b"\xff\xfe", b"\xef\xbb\xbf{}", b'{"a": NaN}', b"null"])
def test_r11_malformed_input_unavailable(data):
    assert_unavailable(R.render(data, expected_for(hist("B1"))), H_UNAVAIL)


def test_r11_unsupported_schema_and_duplicate_keys():
    rep = hist("B1")
    exp = expected_for(rep)
    rep["schema"] = "mneme.c4.gate-report/v2"
    assert_unavailable(R.render(dump(rep), exp), H_UNAVAIL)
    raw = HIST["B1"].read_text(encoding="utf-8")
    dup = raw.replace('"disposition": "success"', '"disposition": "failure", "disposition": "success"', 1)
    assert dup != raw
    assert_unavailable(R.render(dup.encode(), exp), H_UNAVAIL)
    old = '"classification": "VERIFIED_PASS",'
    assert old in raw
    dup = raw.replace(old, old + " " + old, 1)
    assert_unavailable(R.render(dup.encode(), exp), H_UNAVAIL)


def test_r11_refused_row_claimed_pass_is_unavailable():
    rep = make([row("docs/r.md", "REFUSED", "policy")])
    rep["aggregate"]["classification"] = "PASS"
    rep["disposition"] = "success"
    assert_unavailable(go(rep), H_INCONS)


def test_r11_strict_violation_row_claimed_pass_is_unavailable():
    rep = make([viol_row()])
    rep["aggregate"]["classification"] = "PASS"
    rep["disposition"] = "success"
    assert_unavailable(go(rep), H_INCONS)


def test_r11_gate_condition_only_refused_claimed_pass():
    rep = make([], [cond()])
    rep["aggregate"]["classification"] = "PASS"
    rep["disposition"] = "success"
    assert_unavailable(go(rep), H_INCONS)


def test_r11_strict_warn_falsely_aggregated_pass():
    rep = make([viol_row(verdict="WARN", cls="WARN", violations=[viol("docs/a.md", severity="WARN")])])
    rep["aggregate"]["classification"] = "PASS"
    rep["disposition"] = "success"
    assert_unavailable(go(rep), H_INCONS)


def test_r11_unevaluated_falsely_aggregated_pass():
    rep = make([row("docs/u.md", "UNEVALUATED", "mode")], posture="open")
    rep["aggregate"]["classification"] = "PASS"
    assert_unavailable(go(rep), H_INCONS)


@pytest.mark.parametrize("posture", ["open", "closed"])
@pytest.mark.parametrize("build,mode", [
    (lambda: pass_row(), "strict"),
    (lambda: row("docs/u.md", "UNEVALUATED", "mode"), "strict"),
    (lambda: row("docs/r.md", "REFUSED", "policy"), "strict"),
    (lambda: viol_row(), "strict"),
    (lambda: row("docs/g.md", "SKIP", "deleted", status="D"), "strict"),
    (lambda: viol_row(mode="warn"), "warn"),
])
def test_r11_correct_aggregate_wrong_disposition(build, mode, posture):
    rep = make([build()], mode=mode, posture=posture)
    rep["disposition"] = "failure" if rep["disposition"] == "success" else "success"
    assert_unavailable(go(rep), H_INCONS)


def test_r11_counts_and_partial_flag_mismatch():
    rep = make([row("docs/u.md", "UNEVALUATED", "mode")])
    rep["aggregate"]["counts"] = {"UNEVALUATED": 2}
    assert_unavailable(go(rep), H_INCONS)
    rep = make([row("docs/u.md", "UNEVALUATED", "mode")])
    rep["aggregate"]["partly_unevaluated"] = False
    assert_unavailable(go(rep), H_INCONS)
    rep = make([row("docs/u.md", "UNEVALUATED", "mode")])
    rep["aggregate"]["counts"] = {"UNEVALUATED": 1, "SKIP": 0}
    assert_unavailable(go(rep), H_INCONS)


def test_r11_unknown_classification_and_bad_enums():
    rep = make([row("docs/u.md", "UNEVALUATED", "mode")])
    exp = expected_for(rep)
    rep["files"][0]["classification"] = "GREEN"
    assert_unavailable(R.render(dump(rep), exp), H_UNAVAIL)
    for key, val in [("requested_mode", "lenient"), ("disposition", "ok"), ("summary_written", "yes")]:
        rep = make([])
        rep[key] = val
        assert_unavailable(R.render(dump(rep), expected_for(hist("B1"))), H_UNAVAIL)
    rep = make([])
    rep["posture"]["effective"] = "maybe"
    assert_unavailable(R.render(dump(rep), expected_for(hist("B1"))), H_UNAVAIL)
    rep = make([])
    rep["aggregate"]["classification"] = "GREEN"
    assert_unavailable(go(rep), H_UNAVAIL)


def test_r11_impossible_posture_open_with_fallback():
    assert_unavailable(go(make([], posture="open", fallback="x; using closed")), H_INCONS)


def test_r11_invalid_expected_context():
    rep = hist("B1")
    for bad in [None, {}, {**expected_for(rep), "requested_mode": "lenient"}, {**expected_for(rep), "base_sha": ""}]:
        assert_unavailable(R.render(dump(rep), bad), H_UNAVAIL)


# ── R12 / R19: valid producer shapes and missing keys ────────────────────────

MANDATORY = ["schema", "adapter", "evaluator", "base_sha", "head_sha", "merge_base", "requested_mode", "query",
             "posture", "trusted_surface", "memory", "files", "gate_conditions", "aggregate", "disposition",
             "annotations", "summary_written"]


def test_mandatory_key_list_is_the_17_producer_keys():
    assert len(MANDATORY) == 17 and set(MANDATORY) == set(hist("B1"))
    assert set(MANDATORY) == set(R.MANDATORY_KEYS)


@pytest.mark.parametrize("key", MANDATORY)
def test_r12_r19_each_missing_mandatory_key_is_unavailable(key):
    rep = hist("B1")
    exp = expected_for(rep)
    del rep[key]
    assert_unavailable(R.render(dump(rep), exp), H_UNAVAIL)


@pytest.mark.parametrize("key", ["merge_base", "trusted_surface", "memory"])
def test_r12_allowed_nulls(key):
    rep = hist("B1")
    rep[key] = None
    code, text = go(rep)
    assert code == 0 and headings_in(text) == [H_PASS]


def test_r12_nulls_gate_only_condition_early_failure():
    rep = make([], [cond("REFUSED", "change_list")])
    rep["merge_base"] = rep["trusted_surface"] = rep["memory"] = None
    code, text = go(rep)
    assert code == 0 and headings_in(text) == [H_REF]
    assert "- Gate condition: REFUSED (Change list could not be established)" in text
    assert "Details" not in text


def test_r12_summary_written_false_valid_and_missing_fallback_key_not():
    rep = hist("B1")
    rep["summary_written"] = False
    code, text = go(rep)
    assert code == 0 and headings_in(text) == [H_PASS]
    rep = hist("B1")
    exp = expected_for(rep)
    del rep["posture"]["fallback"]
    assert_unavailable(R.render(dump(rep), exp), H_UNAVAIL)


def test_r12_absent_identity_on_violation_row():
    rep = make([viol_row(violations=[{"input_path": "docs/a.md"}])])
    code, text = go(rep)
    assert code == 0 and headings_in(text) == [H_VIOL]
    assert "decision Unavailable, version Unavailable, rule Unavailable, severity Unavailable" in text


@pytest.mark.parametrize("key,val", [("files", {}), ("annotations", "x"), ("base_sha", 5), ("adapter", []),
                                     ("query", None), ("evaluator", {"commit": "a"})])
def test_r12_wrong_types_unavailable(key, val):
    rep = hist("B1")
    exp = expected_for(rep)
    rep[key] = val
    assert_unavailable(R.render(dump(rep), exp), H_UNAVAIL)


# ── escape table, R13 ────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,escaped", [
    ("\\", "\\\\"), ("`", "\\x60"), ("@", "\\x40"), ("<", "\\x3c"), (">", "\\x3e"), ("&", "\\x26"),
    ("[", "\\x5b"), ("]", "\\x5d"), ("(", "\\x28"), (")", "\\x29"), ("|", "\\x7c"),
    ("\n", "\\x0a"), ("\r", "\\x0d"), ("\t", "\\x09"), ("\x00", "\\x00"), ("\x7f", "\\x7f"),
    ("\x85", "\\x85"), ("​", "\\u200b"), ("‮", "\\u202e"), ("﻿", "\\ufeff"),
    ("\ud800", "\\ud800"), ("", "\\ue000"), (" ", "\\u2028"), (" ", "\\u2029"),
    ("͸", "\\u0378"), ("\U000f0000", "\\U000f0000"), ("\U0001d173", "\\U0001d173"),
    ("a b/c.md", "a b/c.md"), ("é中", "é中"), ("*_#!~", "*_#!~"),
])
def test_escape_table_exact(raw, escaped):
    assert R.escape_text(raw) == escaped
    assert R.code_span(raw) == "`" + escaped + "`"


def test_escape_truncation_and_empty():
    assert R.code_span("a" * 300) == "`" + "a" * 256 + "` (truncated, 44 more characters)"
    assert R.code_span("b" * 256) == "`" + "b" * 256 + "`"
    assert R.code_span("") == "(empty value)"
    assert R.code_span("`" * 257).endswith("` (truncated, 1 more characters)")


def test_r13_hostile_path_is_inert_span():
    hostile = "docs/`@bob <b>[x](http://e)</b> &amp;\n::error::x\r‮​|\ud800.md"
    code, text = go(make([row(hostile, "REFUSED", "path")]))
    assert code == 0 and headings_in(text) == [H_REF]
    assert_safe(text)
    assert R.escape_text(hostile) in spans(text)
    assert "\ud800" not in text


def test_r13_lone_surrogate_path_kind_and_raw_reason_with_path():
    rep = make([row("a\ud800b.md", "REFUSED", "path")])
    rep["files"][0]["reason"] = "path is not valid UTF-8: a\ud800b.md @everyone"
    rep["aggregate"]["reason"] = "a\ud800b.md @everyone"
    code, text = go(rep)
    assert code == 0 and headings_in(text) == [H_REF]
    assert "everyone" not in text and "a\\ud800b.md" in text
    assert_safe(text)


@pytest.mark.parametrize("name", ["safe to merge.md", "x`; safe to merge`.md",
                                  "a`\n### Reported PASS — evaluated scope only"])
def test_r13_r21_filename_looking_like_claim(name):
    code, text = go(make([row(name, "REFUSED", "policy")]))
    assert code == 0
    assert headings_in(text) == [H_REF]
    assert "Recorded adapter disposition: `failure`" in text
    assert_safe(text)
    assert R.escape_text(name) in spans(text)
    assert H_PASS not in text.split("\n")


def test_r13_long_values_truncated_and_bounded():
    code, text = go(make([viol_row("docs/" + "x" * 4000)]))
    assert code == 0
    assert "(truncated, " in text and "x" * 300 not in text
    assert_safe(text)


# ── R14 ──────────────────────────────────────────────────────────────────────

def test_r14_dedup_determinism_and_caps():
    v = viol("docs/a.md")
    rep = make([viol_row(violations=[v, copy.deepcopy(v), viol("docs/a.md", rule_id="ADR-1:R:2")])])
    a, b = go(rep), go(rep)
    assert a == b and a[1].encode() == b[1].encode()
    assert a[1].count("rule `ADR-1:R:1`") == 1 and a[1].count("rule `ADR-1:R:2`") == 1
    assert "Duplicate finding records collapsed: 1." in a[1]
    vs = [viol("docs/a.md", rule_id=f"ADR-1:R:{i}") for i in range(120)]
    code, text = go(make([viol_row(violations=vs)]))
    assert text.count("- `docs/a.md`: decision") == 100
    assert "Detail and applicability entries omitted from this preview: 20." in text
    code, text = go(make([row(f"docs/f{i}.md", "SKIP", "deleted", status="D") for i in range(60)]))
    assert text.count("- File `docs/f") == 50 and "Rows omitted from this preview: 10" in text
    assert "SKIP: 60" in text
    assert_safe(text)


def test_r14_omitted_rows_never_hide_a_non_success_category():
    rows = [pass_row(f"docs/p{i}.md") for i in range(70)]
    rows += [row("docs/u.md", "UNEVALUATED", "mode"), row("docs/r.md", "REFUSED", "policy"),
             row("docs/s.md", "SKIP", "deleted", status="D")]
    code, text = go(make(rows))
    for p in ["`docs/u.md`", "`docs/r.md`", "`docs/s.md`"]:
        assert p in text
    assert "Rows omitted" in text


def test_r14_output_size_bound_with_many_wide_findings():
    wide = "\u0001" * 500
    rows = []
    for i in range(20):
        path = f"docs/f{i}.md"
        vs = [viol(path, rule_id=f"{wide}{j}", selector=wide) for j in range(20)]
        rows.append(viol_row(path, violations=vs))
    code, text = go(make(rows))
    assert code == 0 and headings_in(text) == [H_VIOL]
    assert "Detail and applicability entries omitted" in text
    assert_safe(text)


# ── R15, R16, R17 ────────────────────────────────────────────────────────────

def test_r15_coherent_rewritten_report_is_unauthenticated_preview():
    rep = hist("B1")
    rep["files"][0]["path"] = "docs/rewritten.md"
    code, text = go(rep)
    assert code == 0 and headings_in(text) == [H_PASS]
    assert "report-derived, not authenticated" in text.split("\n")[1]
    assert "Not an authoritative gate result" in text


def test_r16_posture_fallback_notice_without_raw_text():
    raw = "MNEME_CI_AVAILABILITY is not exactly 'open' or 'closed' ('" + "Z" * 64 + "'); using closed"
    code, text = go(make([row("docs/u.md", "UNEVALUATED", "mode")], fallback=raw))
    assert code == 0 and "Availability fallback: closed" in text
    assert "ZZZZ" not in text and "MNEME_CI" not in text


def test_r17_summary_write_failure_pass_failure_is_unavailable():
    rep = hist("B1")
    rep["summary_written"] = False
    rep["disposition"] = "failure"
    rep["annotations"] = ["::error::could not write the job summary"]
    assert_unavailable(go(rep), H_INCONS)


# ── R18: detail guard and invariance ─────────────────────────────────────────

def _labels_unchanged(rep, heading, disp):
    code, text = go(rep)
    assert code == 0 and headings_in(text) == [heading]
    assert f"Recorded adapter disposition: `{disp}`" in text
    assert_safe(text)
    return text


@pytest.mark.parametrize("stdout", [
    "garbage", "", "[]", "null", '{"violations": 5}', '{"violations": [1, "x", null]}',
    '{"violations": [], "violations": []}', '{"a": ' * 20 + "1" + "}" * 20,
    json.dumps({"violations": [{"decision_id": 5, "input_path": "docs/a.md"}]}),
    json.dumps({"violations": [{"decision_id": "x" * 513, "input_path": "docs/a.md"}]}),
    json.dumps({"schema": "other", "verdict": "PASS", "exit": 9, "mode": "warn", "violations": []}),
])
def test_r18_malformed_nested_stdout_suppresses_details_only(stdout):
    text = _labels_unchanged(make([row("docs/a.md", "VIOLATION", stdout=stdout)]), H_VIOL, "failure")
    assert "Details unavailable" in text
    assert "STDERR-SENTINEL" not in text


def test_r18_nested_incoherent_verdict_exit_mode_still_renders_findings():
    so = json.dumps({"verdict": "PASS", "mode": "warn", "exit": 7, "evaluation_complete": False,
                     "violations": [viol("docs/a.md", severity="NOTE")],
                     "applicability": [app("docs/a.md")], "unknown_additive": {"k": 1}})
    text = _labels_unchanged(make([row("docs/a.md", "VIOLATION", stdout=so)]), H_VIOL, "failure")
    assert "severity `NOTE`" in text and "outcome `APPLIED`" in text
    assert "unknown_additive" not in text


@pytest.mark.parametrize("input_path", ["docs/a.md", "/abs/work/docs/a.md", None, "docs/other.md", "./docs/a.md"])
def test_r18_input_path_association(input_path):
    v = viol("docs/a.md")
    if input_path is None:
        del v["input_path"]
    else:
        v["input_path"] = input_path
    so = stdout_for("FAIL", "strict", [v], [app("docs/a.md")])
    text = _labels_unchanged(make([row("docs/a.md", "VIOLATION", stdout=so)]), H_VIOL, "failure")
    if input_path == "docs/a.md":
        assert "decision `ADR-1`" in text
    else:
        assert "Details unavailable" in text and "decision `ADR-1`" not in text
        assert "abs/work" not in text and "docs/other.md" not in text


def test_r18_applicability_mismatch_gives_unavailable_outcome():
    for a in [app("docs/zzz.md"), app("docs/a.md", rule_id="OTHER")]:
        code, text = go(make([viol_row(applicability=[a])]))
        assert "outcome Unavailable" in text and "APPLIED" not in text


def test_r18_pass_row_never_renders_findings():
    so = stdout_for("PASS", "strict", [viol("docs/a.md")], [app("docs/a.md")])
    text = _labels_unchanged(make([row("docs/a.md", "VERIFIED_PASS", stdout=so)]), H_PASS, "success")
    assert "ADR-1" not in text


def test_r18_oversized_stdout_suppresses_details():
    big = stdout_for("FAIL", "strict", [viol("docs/a.md")]) + " " * (1024 * 1024)
    text = _labels_unchanged(make([row("docs/a.md", "VIOLATION", stdout=big)]), H_VIOL, "failure")
    assert "Details unavailable" in text


@pytest.mark.parametrize("name", list(HIST))
def test_r18_invariance_garbage_stdout_never_changes_labels(name):
    rep = hist(name)
    exp = expected_for(rep)
    code, before = R.render(dump(rep), exp)
    assert code == 0
    for r in rep["files"]:
        if "stdout" in r:
            r["stdout"] = "}{ not json \u0000 \ud800"
    code, after = R.render(dump(rep), exp)
    assert code == 0
    assert headings_in(after) == headings_in(before)
    pick = lambda t: [l for l in t.split("\n") if l.startswith("Recorded adapter disposition")]
    assert pick(after) == pick(before) and pick(after)
    assert_safe(after)


# ── R19: full inventory ──────────────────────────────────────────────────────

@pytest.mark.parametrize("name", list(HIST))
def test_r19_every_historical_report_renders_with_context_from_itself(name):
    rep = hist(name)
    exp = expected_for(rep)
    rep["extra_outer_key"] = {"secret": "OUTER-SENTINEL"}
    rep["aggregate"]["extra"] = "AGG-EXTRA-SENTINEL"
    for r in rep["files"]:
        r["extra_row"] = "ROW-EXTRA-SENTINEL"
    code, text = R.render(dump(rep), exp)
    assert code == 0
    for s in ["SENTINEL", "stderr", "adr033 c4 trusted gate", "/home/runner",
              rep["evaluator"]["wheel_sha256"], "::error"]:
        assert s not in text
    assert f"- Base commit: `{rep['base_sha']}`" in text
    assert f"- Head commit: `{rep['head_sha']}`" in text
    assert f"- Violation mode: {rep['requested_mode']}" in text
    assert f"- Availability posture: {rep['posture']['effective']}" in text
    assert text.index("Report context") < text.index("### ")
    assert text.index("### ") < text.index("Recorded adapter disposition")
    assert_safe(text)


def test_r19_all_known_kinds_have_controlled_labels():
    kinds = ["path", "policy", "trusted_surface", "deleted", "mode", "timeout", "launch", "untrusted_result",
             "workspace", "memory", "materialize", "adapter_error", "change_list"]
    code, text = go(make([row(f"docs/{k}.md", "UNEVALUATED", k) for k in kinds], posture="open"))
    assert code == 0
    for k in kinds:
        assert f"({R.KIND_LABELS[k]})" in text
    assert "Other reported reason" not in text
    code, text = go(make([row("docs/z.md", "UNEVALUATED", "brand_new_kind <b>")]))
    assert "(Other reported reason)" in text and "brand_new_kind" not in text


# ── R20: limits ──────────────────────────────────────────────────────────────

def test_r20_row_count_boundary():
    skip = lambda: [row(f"d/{i}.md", "SKIP", "deleted", status="D") for i in range(2000)]
    assert go(make(skip()))[0] == 0
    assert_unavailable(go(make(skip(), [cond("UNEVALUATED", "x")])), H_UNAVAIL)


def test_r20_annotation_count_and_field_length_boundary():
    rep = hist("B1")
    exp = expected_for(rep)
    rep["annotations"] = ["a"] * 2000
    assert R.render(dump(rep), exp)[0] == 0
    rep["annotations"] = ["a"] * 2001
    assert_unavailable(R.render(dump(rep), exp), H_UNAVAIL)
    rep = hist("B1")
    rep["files"][0]["path"] = "p" * 4096
    assert R.render(dump(rep), exp)[0] == 0
    rep["files"][0]["path"] = "p" * 4097
    assert_unavailable(R.render(dump(rep), exp), H_UNAVAIL)


def test_r20_input_size_boundary():
    rep = hist("B1")
    exp = expected_for(rep)
    rep["pad"] = ""
    n = len(dump(rep))
    rep["pad"] = "x" * (8 * 1024 * 1024 - n)
    data = dump(rep)
    assert len(data) == 8 * 1024 * 1024 and R.render(data, exp)[0] == 0
    assert_unavailable(R.render(data + b" ", exp), H_UNAVAIL)


def test_r20_depth_boundary():
    rep = hist("B1")
    exp = expected_for(rep)
    nest = 1
    for _ in range(31):
        nest = [nest]
    rep["x"] = nest  # top object (1) + 31 lists = depth 32
    assert R.render(dump(rep), exp)[0] == 0
    rep["x"] = [nest]
    assert_unavailable(R.render(dump(rep), exp), H_UNAVAIL)
    assert_unavailable(R.render(b"[" * 100000 + b"]" * 100000, exp), H_UNAVAIL)


def test_r20_nested_limits_suppress_details_only():
    vs = [viol("docs/a.md", rule_id=f"r{i}") for i in range(2001)]
    text = _labels_unchanged(make([viol_row(violations=vs, applicability=[])]), H_VIOL, "failure")
    assert "Details unavailable" in text and "ADR-1" not in text
    vs = [viol("docs/a.md", rule_id=f"r{i}") for i in range(2000)]
    text = _labels_unchanged(make([viol_row(violations=vs, applicability=[])]), H_VIOL, "failure")
    assert "ADR-1" in text
    deep = {"violations": [], "x": 1}
    for _ in range(16):
        deep = {"d": deep}  # 17 levels
    text = _labels_unchanged(make([row("docs/a.md", "VIOLATION", stdout=json.dumps(deep))]), H_VIOL, "failure")
    assert "Details unavailable" in text


def test_r20_suppressed_fields_with_sentinels_never_leak():
    rep = hist("B2")
    rep["files"][0]["stderr_tail"] = "SECRET-TOKEN-123"
    rep["files"][0]["reason"] = "SECRET-TOKEN-456"
    rep["aggregate"]["reason"] = "SECRET-TOKEN-789"
    rep["annotations"] = ["SECRET-TOKEN-000"]
    rep["evaluator"]["python"] = "/secret/python"
    rep["trusted_surface"]["files"].append("SECRET-SURFACE")
    code, text = go(rep)
    assert code == 0 and "SECRET" not in text and "/secret" not in text


# ── R21: table pairs, forbidden phrases, I/O, CLI ────────────────────────────

CASES = [
    ("PASS-success", lambda: make([pass_row()]), H_PASS),
    ("WARN-success", lambda: make([viol_row(mode="warn")], mode="warn"), H_WARN),
    ("SKIP-success", lambda: make([]), H_SKIP),
    ("VIOLATION-failure", lambda: make([viol_row()]), H_VIOL),
    ("REFUSED-failure", lambda: make([row("a.md", "REFUSED", "policy")]), H_REF),
    ("UNEVALUATED-open", lambda: make([row("a.md", "UNEVALUATED", "mode")], posture="open"), H_UNEV_OPEN),
    ("UNEVALUATED-closed", lambda: make([row("a.md", "UNEVALUATED", "mode")]), H_UNEV_CLOSED),
]


@pytest.mark.parametrize("label,build,heading", CASES, ids=[c[0] for c in CASES])
def test_r21_each_valid_cell_exact_heading_and_safety(label, build, heading):
    code, text = go(build())
    assert code == 0
    assert text.split("\n")[0] == TITLE
    assert [h for h in ALL_HEADINGS if h in text.split("\n")] == [heading]
    assert_safe(text)
    if heading != H_PASS:
        assert "No violations reported in the evaluated scope" not in text


def test_r21_all_invalid_pairs_unavailable():
    for agg in ["PASS", "WARN", "SKIP", "VIOLATION", "REFUSED", "UNEVALUATED"]:
        for disp in ["success", "failure"]:
            for mode in ("strict", "warn"):
                for posture in ("open", "closed"):
                    rep = make([], mode=mode, posture=posture)  # truth is SKIP/success
                    rep["aggregate"]["classification"] = agg
                    rep["disposition"] = disp
                    code, text = go(rep)
                    if (agg, disp) == ("SKIP", "success"):
                        assert code == 0 and headings_in(text) == [H_SKIP]
                    else:
                        assert_unavailable((code, text))


def test_r21_pure_render_never_raises_on_junk():
    exp = expected_for(hist("B1"))
    for data in [b"\x00" * 10, b"{" * 5000, b'{"schema": "mneme.c4.gate-report/v1"}', b'"\\ud800"', b"1e999999"]:
        assert R.render(data, exp)[0] == 2


def _cli(*args):
    return subprocess.run([sys.executable, "-I", str(RENDERER), *args], capture_output=True)


def _cli_args(rep, path):
    e = expected_for(rep)
    return [str(path), "--expected-base-sha", e["base_sha"], "--expected-head-sha", e["head_sha"],
            "--expected-adapter-sha256", e["adapter_sha256"], "--expected-evaluator-commit", e["evaluator_commit"],
            "--expected-evaluator-wheel-sha256", e["evaluator_wheel_sha256"],
            "--expected-mode", e["requested_mode"], "--expected-posture", e["posture"]]


def test_r21_cli_success_stdout_and_output_file_byte_identical(tmp_path):
    rep = hist("B2")
    p = tmp_path / "r.json"
    p.write_bytes(HIST["B2"].read_bytes())
    a = _cli(*_cli_args(rep, p))
    assert a.returncode == 0 and a.stderr == b""
    out = tmp_path / "o.md"
    b = _cli(*_cli_args(rep, p), "--output", str(out))
    assert b.returncode == 0
    assert out.read_bytes() == a.stdout == R.render(p.read_bytes(), expected_for(rep))[1].encode()
    assert b"\r" not in a.stdout


def test_r21_cli_usage_errors_exit_2_without_traceback(tmp_path):
    for args in [[], [str(tmp_path / "x.json")], ["--bogus"]]:
        res = _cli(*args)
        assert res.returncode == 2 and b"Traceback" not in res.stderr
    rep = hist("B1")
    p = tmp_path / "r.json"
    p.write_bytes(HIST["B1"].read_bytes())
    bad = _cli_args(rep, p)
    bad[bad.index("--expected-mode") + 1] = "lenient"
    res = _cli(*bad)
    assert res.returncode == 2 and b"Traceback" not in res.stderr


def test_r21_cli_missing_input_and_context_mismatch_exit_2(tmp_path):
    rep = hist("B1")
    res = _cli(*_cli_args(rep, tmp_path / "missing.json"))
    assert res.returncode == 2 and H_UNAVAIL.encode() in res.stdout
    p = tmp_path / "r.json"
    p.write_bytes(HIST["B1"].read_bytes())
    args = _cli_args(rep, p)
    args[args.index("--expected-head-sha") + 1] = "f" * 40
    res = _cli(*args)
    assert res.returncode == 2 and b"context mismatch: head_sha" in res.stdout and b"Reported" not in res.stdout


def test_r21_cli_output_io_failure_exit_3(tmp_path):
    rep = hist("B1")
    p = tmp_path / "r.json"
    p.write_bytes(HIST["B1"].read_bytes())
    res = _cli(*_cli_args(rep, p), "--output", str(tmp_path))  # a directory
    assert res.returncode == 3 and b"Traceback" not in res.stderr and res.stdout == b""
    res = _cli(*_cli_args(rep, p), "--output", str(tmp_path / "nodir" / "o.md"))
    assert res.returncode == 3


# ── review follow-ups ────────────────────────────────────────────────────────

def test_r18_partial_suppression_says_some_details_unavailable():
    good = viol("docs/a.md")
    bad = viol("docs/a.md", decision_id=5)
    text = _labels_unchanged(make([viol_row(violations=[good, bad])]), H_VIOL, "failure")
    assert "Some details unavailable" in text
    assert "decision `ADR-1`" in text
    assert ": Details unavailable" not in text
    text = _labels_unchanged(make([viol_row(violations=[bad])]), H_VIOL, "failure")
    assert ": Details unavailable" in text and "Some details unavailable" not in text


def _outer(r, lst):
    r["applicability"] = lst
    return r


def _app_entry(**kw):
    e = {"decision_id": "ADR-1", "rule_id": "ADR-1:R:1", "outcome": "APPLIED"}
    e.update(kw)
    return e


def test_r10_mr1_excluded_outcome_shown_on_pass_row_and_is_not_an_allow():
    r = _outer(pass_row("docs/a.md"), [_app_entry(outcome="EXCLUDED")])
    text = _labels_unchanged(make([r]), H_PASS, "success")
    assert "#### Reported applicability" in text
    assert "- `docs/a.md`: decision `ADR-1`, rule `ADR-1:R:1`, outcome `EXCLUDED`" in text
    assert "allow" not in text.lower() and "exempt" not in text.lower() and "per-rule" not in text.lower()
    assert "Details" not in text  # no nested stdout details for PASS rows


def test_mr1_mixed_applied_and_excluded_on_violation_row():
    r = _outer(viol_row(), [_app_entry(), _app_entry(rule_id="ADR-1:R:2", outcome="EXCLUDED")])
    text = _labels_unchanged(make([r]), H_VIOL, "failure")
    assert "outcome `APPLIED`" in text and "outcome `EXCLUDED`" in text
    assert "rule `ADR-1:R:2`" in text


def test_mr1_missing_or_null_trace_shows_nothing_and_malformed_is_unavailable():
    r = pass_row("docs/a.md")
    r.pop("applicability")
    text = _labels_unchanged(make([r]), H_PASS, "success")
    assert "Reported applicability" not in text and "Applicability unavailable" not in text
    text = _labels_unchanged(make([_outer(pass_row("docs/a.md"), None)]), H_PASS, "success")
    assert "Applicability" not in text
    text = _labels_unchanged(make([_outer(pass_row("docs/a.md"), [])]), H_PASS, "success")
    assert "Applicability" not in text
    for bad in ["x", {"a": 1}, [5], [{"decision_id": 7}], [{"outcome": "x" * 513}]]:
        text = _labels_unchanged(make([_outer(pass_row("docs/a.md"), bad)]), H_PASS, "success")
        assert "- `docs/a.md`: Applicability unavailable" in text
    text = _labels_unchanged(make([_outer(pass_row("docs/a.md"), [_app_entry(outcome=None, rule_id="")])]),
                             H_PASS, "success")
    assert "rule Unavailable, outcome Unavailable" in text


def test_mr1_applicability_counts_toward_detail_cap_and_discloses_omission():
    r = _outer(pass_row("docs/a.md"), [_app_entry(rule_id=f"R{i}") for i in range(120)])
    text = _labels_unchanged(make([r]), H_PASS, "success")
    assert text.count("- `docs/a.md`: decision") == 100
    assert "Detail and applicability entries omitted from this preview: 20." in text


def test_mr2_incomplete_identity_is_never_collapsed():
    for key in ("decision_version_id", "rule_id", "decision_id"):
        v1, v2 = viol("docs/a.md"), viol("docs/a.md")
        v1[key] = v2[key] = None
        text = _labels_unchanged(make([viol_row(violations=[v1, v2], applicability=[])]), H_VIOL, "failure")
        assert text.count("- `docs/a.md`: decision") == 2
        assert "Duplicate finding records collapsed" not in text


def test_mr3_outcome_requires_exact_triple_including_version():
    ok = _labels_unchanged(make([viol_row()]), H_VIOL, "failure")
    assert "outcome `APPLIED`" in ok
    bad_ver = app("docs/a.md", decision_version_id="dver-OTHER")
    text = _labels_unchanged(make([viol_row(applicability=[bad_ver])]), H_VIOL, "failure")
    assert "outcome Unavailable" in text and "version `dver-1`" in text
    no_ver = app("docs/a.md")
    del no_ver["decision_version_id"]
    text = _labels_unchanged(make([viol_row(applicability=[no_ver])]), H_VIOL, "failure")
    assert "outcome Unavailable" in text
    v = viol("docs/a.md", decision_version_id="")
    text = _labels_unchanged(make([viol_row(violations=[v], applicability=[app("docs/a.md", decision_version_id="")])]),
                             H_VIOL, "failure")
    assert "version Unavailable" in text and "outcome Unavailable" in text
    conflicting = [app("docs/a.md"), app("docs/a.md", outcome="EXCLUDED")]
    text = _labels_unchanged(make([viol_row(applicability=conflicting)]), H_VIOL, "failure")
    assert "outcome Unavailable" in text


@pytest.mark.parametrize("path", ["/abs/docs/a.md", "C:/work/docs/a.md", r"c:\work\docs\a.md", r"\\srv\x\a.md", r"docs\a.md"])
def test_mr3_absolute_paths_never_associate(path):
    v, a = viol(path), app(path)
    so = stdout_for("FAIL", "strict", [v], [a])
    text = _labels_unchanged(make([row(path, "VIOLATION", stdout=so)]), H_VIOL, "failure")
    assert "Details unavailable" in text and "decision `ADR-1`" not in text and "outcome" not in text


def test_r20_consolidated_sentinels_in_all_suppressed_fields():
    v = viol("docs/a.md", rule="S-RULE", trigger="S-TRIGGER", decision_text="S-DTEXT",
             reason="S-VREASON", rule_value="S-RVALUE")
    a = app("docs/a.md", rule_value="S-APPVALUE", reason="S-APPREASON")
    so = json.dumps({"schema": "mneme.check/v1", "verdict": "FAIL", "mode": "strict",
                     "evaluation_complete": True, "violations": [v], "applicability": [a],
                     "freshness": [{"message": "S-FRESH", "path": "S-FRESHPATH"}]})
    r = row("docs/a.md", "VIOLATION", stdout=so)
    r["stderr_tail"] = "S-STDERR"
    r["reason"] = "S-ROWREASON"
    rep = make([r])
    rep["aggregate"]["reason"] = "S-AGGREASON"
    rep["annotations"] = ["S-ANNOT"]
    rep["posture"]["source"] = "S-SOURCE"
    rep["query"] = "S-QUERY"
    rep["evaluator"]["python"] = "S-PYTHON"
    rep["trusted_surface"] = {"files": ["S-SURFACE"], "dirs": ["S-DIR/"]}
    rep["memory"] = {"path": "S-MEMPATH", "blob": "S-BLOB", "source_commit": "S-SC", "sha256": "S-MSHA"}
    code, text = go(rep)
    assert code == 0 and headings_in(text) == [H_VIOL]
    assert "decision `ADR-1`" in text  # allowlisted fields still shown
    assert "S-" not in text


def test_mr4_context_lines_valid_inconsistent_and_omitted_when_unavailable():
    rep = make([pass_row()])
    code, text = go(rep)
    lines = text.split("\n")
    assert lines[3] == "Report context (report-derived, not authenticated):"
    assert lines[4] == f"- Base commit: `{rep['base_sha']}`"
    assert lines[5] == f"- Head commit: `{rep['head_sha']}`"
    assert lines[6:8] == ["- Violation mode: strict", "- Availability posture: closed"]
    assert "evaluator" not in text.lower() and "blob" not in text and "scripts/ci" not in text
    bad = make([pass_row()])
    bad["disposition"] = "failure"
    code, text = go(bad)
    assert_unavailable((code, text), H_INCONS)
    assert f"- Base commit: `{rep['base_sha']}`" in text and "Violation mode: strict" in text
    # could-not-be-displayed (including context mismatch) carries no context block
    exp = expected_for(rep)
    exp["head_sha"] = "f" * 40
    res = R.render(dump(rep), exp)
    assert_unavailable(res, H_UNAVAIL)
    assert "Report context" not in res[1]
    broken = make([pass_row()])
    del broken["query"]
    assert "Report context" not in R.render(dump(broken), expected_for(rep))[1]


@pytest.mark.parametrize("sha", ["abc", "A" * 40, "g" * 40, "a" * 41, "`" * 40])
def test_mr4_non_40_lowercase_hex_sha_is_unavailable(sha):
    rep = make([pass_row()])
    rep["base_sha"] = sha
    code, text = go(rep)
    assert code == 0 and "- Base commit: Unavailable" in text
    assert_safe(text)


def test_mr4_sha40_with_trailing_newline_is_unavailable():
    for sha in ["a" * 40 + "\n", "a" * 40 + "\r\n", "\n" + "a" * 40]:
        rep = make([pass_row()])
        rep["base_sha"] = sha
        code, text = go(rep)
        assert code == 0 and "- Base commit: Unavailable" in text
        assert_safe(text)

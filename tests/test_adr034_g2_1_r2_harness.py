"""Tests for the ADR-034 G2-1 R2 scoring harness (benchmarks/adr034_g2_1_r2/).

Every case used here is SYNTHETIC (tests/adr034_g2_1_r2_synthetic_corpus.py
and the hand-built observations below), written by the R2 scorer from the
pre-registrations, ADR-034 and the R2 corpus README; none is drawn from the
sealed corpus. The end-to-end tests run the repository's own source as both
builds, so hook-level parity there is trivially true: they test the pipeline,
not G2-1. The pinned-wheel run over the 13 public smoke cases is in
test_adr034_g2_1_r2_harness_smoke.py (opt-in).
"""
from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests import adr034_g2_1_r2_synthetic_corpus as syn

REPO_ROOT = Path(__file__).resolve().parents[1]
_HARNESS = REPO_ROOT / "benchmarks" / "adr034_g2_1_r2" / "harness.py"

_spec = importlib.util.spec_from_file_location("adr034_g2_1_r2_harness", _HARNESS)
h = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = h
_spec.loader.exec_module(h)

HOST = ("2.1.310", "a" * 64)
RID_A = "ADR-901:FORBID_NUMERIC_ABOVE:" + "1" * 32
RID_B = "ADR-902:FORBID_NUMERIC_ABOVE:" + "2" * 32
DIGEST = hashlib.sha256(b"X = 1\n").hexdigest()


# ── pins ─────────────────────────────────────────────────────────────────────

def test_frozen_pins_match_the_r2_preregistration_and_freeze_record():
    p = h.R2_PINS
    assert p.impl_commit == "dbab816f92143875c1ed7c7d24e4403dedc3b345"
    assert p.impl_tree == "6cb14c2b48554482e62685395062bb581dfed5e4"
    assert p.baseline_commit == "f8591102b2693379dabec9b5704862e194eca4ce"
    assert p.python_version == "3.12.10"
    assert p.files_sha256_digest == (
        "70d35226584bead131929deb41e3e3f59a5307d0ae34fe49b29426692a749c0d")
    assert p.files_count == 605
    assert p.corpus_tar_sha256 == (
        "17a46379cfbb04ec41cc7e740a9f52ce1f94e48e154a2178987ca56af22dcfe1")
    assert p.public_files_sha256_digest == (
        "b60394c0076f41f8dd0845c6b290347522bea36d42340050686f04bc3547ab0c")
    assert p.public_files_count == 57
    assert sum(c for c, _ in p.counts.values()) == 143
    assert sum(s for _, s in p.counts.values()) == 13
    assert all(s == 1 for _, s in p.counts.values())
    floors = {"V": 15, "VP": 8, "C": 15, "US": 8, "UF": 8, "UP": 6, "X": 6, "L": 18,
              "LIT": 6, "W": 6, "P": 8, "SC": 10, "MR": 6}
    assert set(p.counts) == set(h.CLASSES) == set(floors)
    assert all(p.counts[k][0] >= floor for k, floor in floors.items())
    assert sum(floors.values()) == 120


def test_pinned_trees_are_the_git_trees_of_the_pinned_commits():
    for commit, tree in ((h.R2_PINS.impl_commit, h.R2_PINS.impl_tree),
                         (h.R2_PINS.baseline_commit, h.R2_PINS.baseline_tree)):
        out = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", f"{commit}:mneme"],
                             capture_output=True, text=True)
        if out.returncode != 0:
            pytest.skip("pinned commits not in this clone")
        assert out.stdout.strip() == tree


def test_the_r1_harness_is_not_imported():
    text = _HARNESS.read_text(encoding="utf-8")
    assert "import harness" not in text and "spec_from_file_location" not in text
    assert "MNEME_G2H_" not in text  # the R1 shim's variable is not reused


# ── corpus loading and preconditions ─────────────────────────────────────────

@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "corpus"
    pins = syn.build(root, h)
    return root, pins


def test_verify_corpus_accepts_the_synthetic_corpus(corpus):
    root, pins = corpus
    record, cases = h.verify_corpus(root, pins, None, None)
    assert record["findings"] == []
    assert len(cases) == len(syn.SPECS)
    assert not any(c.problems for c in cases)


def test_verify_corpus_refuses_a_changed_or_extra_file(corpus):
    root, pins = corpus
    (root / "MANIFEST.json").write_bytes(b"[]\n")
    with pytest.raises(h.Refusal, match="entries fail"):
        h.verify_corpus(root, pins, None, None)


def test_verify_corpus_refuses_an_extra_file(corpus):
    root, pins = corpus
    (root / "stray.txt").write_bytes(b"x")
    with pytest.raises(h.Refusal) as exc:
        h.verify_corpus(root, pins, None, None)
    assert exc.value.check == "files_sha256_layout"


def test_verify_corpus_refuses_wrong_counts_digest_and_tar(corpus, tmp_path):
    root, pins = corpus
    with pytest.raises(h.Refusal, match="digest"):
        h.verify_corpus(root, h.R2_PINS, None, None)
    counts = dict(pins.counts, SC=(5, 0))
    with pytest.raises(h.Refusal) as exc:
        h.verify_corpus(root, h.dataclasses.replace(pins, counts=counts), None, None)
    assert exc.value.check == "counts"
    tar = tmp_path / "corpus.tar"
    tar.write_bytes(b"not the corpus")
    with pytest.raises(h.Refusal) as exc:
        h.verify_corpus(root, pins, tar, None)
    assert exc.value.check == "corpus_tar"


def test_cases_may_sit_one_level_down(tmp_path):
    root = tmp_path / "corpus"
    syn.build(root / "concealed", h)
    (root / "concealed" / "FILES.sha256").unlink()
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    (root / "FILES.sha256").write_text(
        "".join(f"{h.sha256_file(root / f)}  {f}\n" for f in files), encoding="ascii")
    cases, findings = h.load_cases(root)
    assert len(cases) == len(syn.SPECS) and findings == []


def test_public_smoke_folder_is_verified_against_its_pinned_manifest(corpus, tmp_path):
    root, pins = corpus
    public = tmp_path / "public"
    syn.build(public, h, [s for s in syn.SPECS if s[6].get("public")])
    (public / "FILES.sha256").rename(public / "PUBLIC_FILES.sha256")
    with pytest.raises(h.Refusal) as exc:
        h.verify_corpus(root, pins, None, public)
    assert exc.value.check == "public_files_sha256"  # the R2 pinned digest differs
    manifest = (public / "PUBLIC_FILES.sha256").read_bytes()
    test_pins = h.dataclasses.replace(
        pins, public_files_sha256_digest=hashlib.sha256(manifest).hexdigest(),
        public_files_count=len(manifest.splitlines()))
    with pytest.raises(h.Refusal, match="also in the corpus"):
        h.verify_corpus(root, test_pins, None, public)


def test_malformed_case_is_kept_and_fails_g8(corpus):
    root, _ = corpus
    cid = syn.case_id("syn-c")
    path = root / "cases" / cid / "expected.json"
    expected = json.loads(path.read_text())
    del expected["applied_numeric_rule_ids"]
    expected["relevant_enforcement_per_rule"] = {RID_A: "yes"}
    path.write_text(json.dumps(expected))
    case = h.load_case(root / "cases", cid)
    assert "expected.json missing applied_numeric_rule_ids" in case.problems
    assert "expected.json relevant_enforcement_per_rule" in case.problems
    obs = {"operational_failures": list(case.problems)}
    result = h.score_case(case, obs, HOST)
    assert result["gates"]["G8"]["pass"] is False


def test_duplicate_applied_rule_ids_in_a_label_are_a_label_problem():
    expected = _expected(applied_numeric_rule_ids=[RID_A, RID_A])
    assert "expected.json applied_numeric_rule_ids has a duplicate" in h._label_problems(expected)


def test_manifest_differences_are_findings_never_refusals(corpus):
    root, pins = corpus
    rows = json.loads((root / "MANIFEST.json").read_text())
    rows[0]["class"] = "V" if rows[0]["class"] != "V" else "C"
    cases, _ = h.load_cases(root)
    findings = h.manifest_findings(root, cases)
    assert findings == []
    (root / "MANIFEST.json").write_text(json.dumps(rows))
    assert any("MANIFEST class differs" in f for f in h.manifest_findings(root, cases))


def test_run_root_must_be_new_and_free_of_ancestor_memory(tmp_path):
    real = Path(os.path.realpath(tmp_path))
    (real / "exists").mkdir()
    with pytest.raises(h.Refusal):
        h.check_run_root(real / "exists")
    (real / "a" / ".mneme").mkdir(parents=True)
    with pytest.raises(h.Refusal, match="ancestor"):
        h.check_run_root(real / "a" / "b" / "run")
    assert h.check_run_root(real / "fresh") == real / "fresh"


def test_score_refuses_a_malformed_host_identity_before_running(tmp_path):
    final = h.score(corpus=tmp_path, out_dir=tmp_path / "out", impl_python=sys.executable,
                    impl_wheel=tmp_path / "w.whl", base_python=sys.executable,
                    base_wheel=tmp_path / "w.whl", host_version="2.1.310",
                    host_sha256="ABC")
    assert final["result"] == "REFUSED"
    assert final["refusal"]["check"] == "host_identity"
    assert final["cause_mapping"] == list(h.CAUSE_MAPPING)


def test_score_refuses_an_interpreter_without_the_pinned_build(tmp_path):
    final = h.score(corpus=tmp_path, out_dir=tmp_path / "out", impl_python=sys.executable,
                    impl_wheel=tmp_path / "w.whl", base_python=sys.executable,
                    base_wheel=tmp_path / "w.whl", host_version=HOST[0], host_sha256=HOST[1],
                    run_root=Path(os.path.realpath(tmp_path)) / "run")
    assert final["result"] == "REFUSED"


# ── materialization ──────────────────────────────────────────────────────────

def _layout(tmp_path) -> "h.Layout":
    return h.Layout.at(Path(os.path.realpath(tmp_path)) / "c")


def test_envelope_substitution_uses_native_paths_and_keeps_every_other_byte(tmp_path):
    layout = _layout(tmp_path)
    content = "﻿A = 1\r\nB = '${REPO}'\r# \ud800\n"
    text = json.dumps({"cwd": "${REPO}", "session_id": "s", "tool_input": {
        "content": content, "file_path": "${REPO}/src/a b/x.py"},
        "transcript_path": "${CASE}/t.jsonl"}, ensure_ascii=True, indent=1)
    out = h.substitute_envelope(text, layout)
    parsed = json.loads(out)
    assert parsed["tool_input"]["content"] == content
    assert parsed["cwd"] == str(layout.repo)
    assert parsed["tool_input"]["file_path"] == str(layout.repo) + os.sep + os.sep.join(
        ["src", "a b", "x.py"])
    assert parsed["transcript_path"] == str(layout.case) + os.sep + "t.jsonl"
    # The content literal, escapes included, is byte-identical in the raw text.
    literal = json.dumps(content, ensure_ascii=True)
    assert literal in text and literal in out


@pytest.mark.parametrize("value", ["${HOME}/x", "${REPO}x", "pre/${REPO}/x", "${REPO}/${CASE}"])
def test_envelope_substitution_fails_closed_on_unknown_or_misplaced_tokens(tmp_path, value):
    text = json.dumps({"cwd": value, "tool_input": {"content": "", "file_path": "${REPO}/a.py"}})
    with pytest.raises(h.CaseFailure):
        h.substitute_envelope(text, _layout(tmp_path))


def test_materialize_copies_bytes_and_creates_dirs_and_links(tmp_path):
    root = tmp_path / "corpus"
    syn.build(root, h, syn.SPECS + ([syn.FALLBACK_SPEC] if _symlinks(tmp_path) else []))
    cases, _ = h.load_cases(root)
    layout = _layout(tmp_path / "w")
    case = next(c for c in cases if c.case_id == syn.case_id("syn-l-existing"))
    h.materialize(case, layout, b"{}")
    assert (layout.repo / "src" / "existing.py").read_bytes() == b"LIMIT_A = 1\n"
    assert (layout.repo / ".mneme" / "project_memory.json").read_bytes() == b"{}"
    assert h.target_path_of(case, layout) == layout.repo / "src" / "existing.py"
    with pytest.raises(h.CaseFailure, match="exists"):
        h.materialize(case, layout, None)
    h._rmtree(layout.case)
    outside = next(c for c in cases if c.case_id == syn.case_id("syn-l-outside"))
    h.materialize(outside, layout, None)
    assert (layout.outside / "elsewhere").is_dir()
    assert h.target_path_of(outside, layout).parent == layout.outside / "elsewhere"


def test_symlink_failure_is_a_g8_failure_never_an_exclusion(tmp_path, monkeypatch):
    root = tmp_path / "corpus"
    syn.build(root, h, [syn.FALLBACK_SPEC])
    (case,) = h.load_cases(root)[0]

    def refuse(*_a, **_k):
        raise OSError("no privilege")

    monkeypatch.setattr(h.os, "symlink", refuse)
    with pytest.raises(h.CaseFailure, match="INCOMPLETE"):
        h.materialize(case, _layout(tmp_path / "w"), None)


def test_import_plan_uses_one_import_only_for_the_importers_own_listing(tmp_path):
    adr = tmp_path / "docs" / "adr"
    adr.mkdir(parents=True)
    for name in ("ADR-1.md", "ADR-2.md", "README.md"):
        (adr / name).write_text("x")
    P = h.PurePosixPath
    one, two = P("docs/adr/ADR-1.md"), P("docs/adr/ADR-2.md")
    assert h.import_plan(tmp_path, [one, two]) == [[one, two]]
    assert h.import_plan(tmp_path, [two, one]) == [[two], [one]]
    assert h.import_plan(tmp_path, [one]) == [[one]]
    with pytest.raises(h.CaseFailure):
        h.import_plan(tmp_path, [P("docs/adr/README.md")])


def test_memory_compile_order_does_not_change_the_compiled_rules(tmp_path):
    """Both import paths compile the same decisions and typed rules."""
    root = tmp_path / "corpus"
    lit = next(s for s in syn.SPECS if s[0] == "syn-lit")
    reordered = (lit[0] + "-r", lit[1], list(reversed(lit[2])), *lit[3:])
    syn.build(root, h, [lit, reordered])
    cases, _ = h.load_cases(root)
    compiled = []
    for case in cases:
        layout = _layout(tmp_path / case.case_id)
        scratch = tmp_path / ("s" + case.case_id)
        for name in ("tmp", "home"):
            (scratch / name).mkdir(parents=True)
        h.materialize(case, layout, None)
        _, info = h.build_memory(case, layout, sys.executable, scratch, str(REPO_ROOT))
        compiled.append(info)
    assert sorted(c["imports"] for c in compiled) == [1, 2]
    assert compiled[0]["decision_ids"] == compiled[1]["decision_ids"]
    assert compiled[0]["typed_rules"] == compiled[1]["typed_rules"]


def test_memory_compile_failure_is_a_case_failure(tmp_path):
    root = tmp_path / "corpus"
    syn.build(root, h, [syn.SPECS[0]])
    (case,) = h.load_cases(root)[0]
    case.case["memory"]["compile_from"] = ["docs/adr/ADR-999.md"]
    layout = _layout(tmp_path / "w")
    h.materialize(case, layout, None)
    with pytest.raises(h.CaseFailure, match="does not have"):
        h.build_memory(case, layout, sys.executable, tmp_path, str(REPO_ROOT))


def test_target_state_distinguishes_absent_file_and_change(tmp_path):
    target = tmp_path / "t.py"
    assert h.target_state(target) == {"exists": False}
    target.write_bytes(b"a")
    state = h.target_state(target)
    assert state["kind"] == "file" and state["sha256"] == hashlib.sha256(b"a").hexdigest()


def test_observed_disposition():
    assert h.observed_disposition(2, b"") == "refused"
    assert h.observed_disposition(0, b"") == "proceeded"
    defer = json.dumps({"hookSpecificOutput": {"permissionDecision": "defer"}}).encode()
    assert h.observed_disposition(0, defer) == "deferred"
    assert h.observed_disposition(1, b"") == "error"


def test_shim_records_without_changing_stdout_stderr_or_exit(tmp_path):
    code = ("import sys; sys.stdout.write('out\\r\\n\\u00e9'); "
            "sys.stderr.write('err\\n'); sys.exit(3)")
    script = tmp_path / "m"
    (script / "mneme").mkdir(parents=True)
    (script / "mneme" / "__init__.py").write_text("")
    (script / "mneme" / "__main__.py").write_text(code)
    runs = []
    for with_shim in (False, True):
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(
            ([str(h.SHIM_DIR)] if with_shim else []) + [str(script)]),
            PYTHONIOENCODING="utf-8")
        env[h.OBSERVE_LOG_ENV] = str(tmp_path / "log.jsonl")
        runs.append(subprocess.run([sys.executable, "-m", "mneme", "check", "--input", "x"],
                                   capture_output=True, env=env, cwd=tmp_path))
    assert (runs[0].stdout, runs[0].stderr, runs[0].returncode) == \
        (runs[1].stdout, runs[1].stderr, runs[1].returncode)
    (line,) = (tmp_path / "log.jsonl").read_text().splitlines()
    assert json.loads(line)["stdout"] == "out\r\né"


# ── hand-built observations ──────────────────────────────────────────────────

def _rule(rid=RID_A, status="RECOGNIZED", outcome="VIOLATION", reason=None, reasons=()):
    return {"applicability": "APPLIED", "matcher_outcome": outcome, "matcher_status": status,
            "primary_reason": reason, "rule_id": rid, "rule_id_form_verified": True,
            "rule_key": "A", "unknown_source_reason_set": sorted(set(reasons))}


def _expected(**overrides) -> dict:
    e = {
        "applied_numeric_rule_ids": [RID_A], "availability": "open", "case_id": "r2-0000000000",
        "checker_invoked": True, "class": "V", "disposition": "refused",
        "evaluation_complete": True, "evidence_record_expected": True,
        "expected_cause": "numeric_violation", "g6_routed_fallback": False, "hook_exit": 2,
        "hook_mode": "strict", "legacy_baseline_observed": False, "literal_violation": False,
        "numeric_rules": [_rule()], "relevant_enforcement_observed": True,
        "relevant_enforcement_per_rule": {RID_A: True}, "routed": True,
        "routed_cr_parity_exception": False, "subject_kind": "proposed_new_source",
        "target_exists_after_hook": False,
    }
    e.update(overrides)
    return e


def _case(klass="V", **overrides) -> "h.Case":
    expected = _expected(**dict({"class": klass}, **overrides))
    case = {"availability": "open", "case_id": "r2-0000000000", "class": klass,
            "content_utf8_sha256": DIGEST, "hook_mode": expected["hook_mode"]}
    return h.Case("r2-0000000000", klass, False, case, expected, "", Path("."), [])


FACTS = {"file_path": os.path.join(os.path.realpath(os.sep), "ws", "repo", "x.py"),
         "cwd": os.path.join(os.path.realpath(os.sep), "ws", "repo"), "tool_name": "Write",
         "identifiers": {"session_id": "s"}, "content_sha256": DIGEST, "content_has_cr": False}


def _record(rules=None, *, outcome="refused", cause="numeric_violation", mode="strict",
            violations=None, subject=True, ec=True) -> dict:
    rules = [{"rule_id": RID_A, "matcher_status": "RECOGNIZED", "matcher_outcome": "VIOLATION",
              "primary_reason": None}] if rules is None else rules
    full = [dict(r, decision_version_id="dver-1", applicability="APPLIED",
                 governed_path="x.py", subject_sha256=DIGEST) for r in rules]
    if violations is None:
        violations = [{"rule_id": r["rule_id"], "rule_type": h.NUMERIC} for r in rules
                      if r["matcher_outcome"] == "VIOLATION"]
    return {
        "schema": "mneme.hook_evidence/v1", "surface": h.EVIDENCE_SURFACE,
        "mneme_version": "0.10.0",
        "host": {"version": HOST[0], "executable_sha256": HOST[1]},
        "event": {"tool_name": "Write", "file_path": FACTS["file_path"], "cwd": FACTS["cwd"],
                  "identifiers": dict(FACTS["identifiers"])},
        "carrier_sha256": DIGEST,
        "checker": {"trusted": True, "problem": "", "evaluation_complete": ec,
                    "subject": {"input_kind": h.INPUT_KIND_PROPOSED, "subject_sha256": DIGEST,
                                "target_path": FACTS["file_path"], "governed_path": "x.py",
                                "absence_verified": True} if subject else None},
        "rules": full, "violations": violations, "hook_outcome": outcome,
        "disposition": {"mode": mode, "cause": cause},
    }


def _hook(exit_code=2, disposition="refused", records=None, evaluations=None, traces=None,
          before=None, after=None, flag="--proposed-new-file", stdout=b"", stderr=b""):
    records = [_record()] if records is None else records
    evaluations = [{"per_rule": {RID_A: True}, "event": True, "evaluation_complete": True}
                   ] * len(records) if evaluations is None else evaluations
    traces = [{"rule_type": h.NUMERIC, "rule_id": RID_A, "outcome": "APPLIED",
               "matcher_status": "RECOGNIZED", "matcher_outcome": "VIOLATION",
               "primary_reason": None, "unknown_sources": []}] if traces is None else traces
    payload = {"subject": {"input_kind": "proposed_new_source"}, "applicability": traces}
    return {"exit": exit_code, "disposition": disposition,
            "stdout_b64": base64.b64encode(stdout).decode(),
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_b64": base64.b64encode(stderr).decode(),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
            "target_before": before or {"exists": False}, "target_after": after or {"exists": False},
            "evidence_records": records, "evidence_evaluation": evaluations,
            "invocations": [{"input_flag": flag, "stdout": json.dumps(payload)}] if flag else []}


def _obs(impl=None, base=None, **extra) -> dict:
    impl = impl or _hook()
    return dict({"operational_failures": [], "envelope": dict(FACTS),
                 "implementation": impl, "baseline": base or copy.deepcopy(impl)}, **extra)


def _gates(case, obs) -> dict:
    return h.score_case(case, obs, HOST)["gates"]


def _why(case, obs, gate) -> list[str]:
    return _gates(case, obs)[gate]["why"]


def test_a_conforming_v_case_passes_every_gate():
    case, obs = _case(), _obs()
    result = h.score_case(case, obs, HOST)
    assert all(g["pass"] for g in result["gates"].values()), result["gates"]
    assert result["diagnostics"]["conformance"] == []


# G1

def test_g1a_expected_block_observed_proceeding_is_unsafe_whatever_the_labels():
    obs = _obs(_hook(exit_code=0, disposition="proceeded",
                     records=[_record(outcome="proceeded")]))
    assert "a:expected_block_not_refused" in _why(_case(), obs, "G1")


@pytest.mark.parametrize("klass", ["SC", "MR", "LIT", "C", "L"])
def test_g1a_any_labelled_block_expectation_in_any_class_counts(klass):
    obs = _obs(_hook(exit_code=0, disposition="proceeded"))
    assert "a:expected_block_not_refused" in _why(_case(klass), obs, "G1")


def test_g1a_baseline_observed_case_carries_no_block_expectation():
    case = _case("L", hook_exit="baseline_observed", disposition="baseline_observed",
                 legacy_baseline_observed=True, evidence_record_expected=False)
    obs = _obs(_hook(exit_code=1, disposition="error", records=[]))
    assert "a:expected_block_not_refused" not in _why(case, obs, "G1")


def test_g1b_nonclean_expected_observed_no_violation():
    case = _case("MR", numeric_rules=[_rule(), _rule(RID_B, "MATCHER_UNEVALUATED",
                                                       "UNEVALUATED", "SOURCE_NOT_FOUND")])
    traces = [{"rule_type": h.NUMERIC, "rule_id": RID_B, "matcher_outcome": "NO_VIOLATION"}]
    assert "b:nonclean_observed_no_violation" in _why(case, _obs(_hook(traces=traces)), "G1")


def test_g1c_per_rule_true_the_label_does_not_expect_is_unsafe():
    case = _case("MR", applied_numeric_rule_ids=[RID_A, RID_B],
                 relevant_enforcement_per_rule={RID_A: True, RID_B: False})
    evaluations = [{"per_rule": {RID_A: True, RID_B: True}, "event": True,
                    "evaluation_complete": True}]
    why = _why(case, _obs(_hook(evaluations=evaluations)), "G1")
    assert "c:unexpected_relevant_claim_per_rule" in why
    case = _case("LIT", relevant_enforcement_observed=False,
                 relevant_enforcement_per_rule={RID_A: False})
    assert "c:unexpected_relevant_claim" in _why(case, _obs(), "G1")


# G2

@pytest.mark.parametrize("klass,labels,applies", [
    ("C", {}, True), ("W", {}, True), ("L", {"legacy_baseline_observed": True}, False),
    ("C", {"literal_violation": True}, False),
    ("SC", {"hook_exit": 0}, True), ("MR", {"hook_exit": 0}, True),
    ("SC", {"hook_exit": 2}, False), ("MR", {"hook_exit": 2, "literal_violation": True}, False),
    ("V", {}, False), ("LIT", {"hook_exit": 0}, False),
])
def test_g2_covers_proceed_classes_and_sc_mr_labelled_to_proceed(klass, labels, applies):
    case = _case(klass, **labels)
    gate = _gates(case, _obs())["G2"]
    assert gate["applies"] is applies
    assert gate["pass"] is (not applies)  # the observation is an exit 2


# G3

def test_g3_target_after_block_change_and_label():
    obs = _obs(_hook(after={"exists": True, "kind": "file", "sha256": "0" * 64}))
    why = _why(_case(), obs, "G3")
    assert {"target_present_after_block", "target_changed",
            "target_exists_after_hook_label"} <= set(why)
    existing = {"exists": True, "kind": "file", "sha256": "1" * 64}
    case = _case("L", target_exists_after_hook=False)
    obs = _obs(_hook(exit_code=0, disposition="proceeded", records=[], before=existing,
                     after=existing))
    assert _why(case, obs, "G3") == ["target_exists_after_hook_label"]


# G4

def test_g4_scores_primary_reason_for_sc_and_mr_and_reason_sets_are_not_gated():
    rules = [_rule(RID_A, "MATCHER_UNEVALUATED", "UNEVALUATED", "AMBIGUOUS_BINDING",
                   ["AMBIGUOUS_BINDING", "SOURCE_NOT_FOUND"])]
    good = [{"rule_type": h.NUMERIC, "rule_id": RID_A, "outcome": "APPLIED",
             "matcher_status": "MATCHER_UNEVALUATED", "matcher_outcome": "UNEVALUATED",
             "primary_reason": "AMBIGUOUS_BINDING",
             "unknown_sources": [{"reason": "SOURCE_NOT_FOUND"}, {"reason": "AMBIGUOUS_BINDING"},
                                 {"reason": "AMBIGUOUS_BINDING"}]}]
    for klass in ("SC", "MR"):
        case = _case(klass, numeric_rules=rules)
        result = h.score_case(case, _obs(_hook(traces=good)), HOST)
        assert result["gates"]["G4"] == {"applies": True, "pass": True, "why": []}
        assert "numeric_rules.unknown_source_reason_set" not in \
            result["diagnostics"]["conformance"]
    wrong_set = [dict(good[0], unknown_sources=[{"reason": "AMBIGUOUS_BINDING"}])]
    result = h.score_case(_case("SC", numeric_rules=rules), _obs(_hook(traces=wrong_set)), HOST)
    assert result["gates"]["G4"]["pass"] is True
    assert "numeric_rules.unknown_source_reason_set" in result["diagnostics"]["conformance"]
    wrong_primary = [dict(good[0], primary_reason="SOURCE_NOT_FOUND")]
    assert _why(_case("SC", numeric_rules=rules), _obs(_hook(traces=wrong_primary)),
                "G4") == ["primary_reason"]
    assert _gates(_case("C", numeric_rules=rules), _obs(_hook(traces=wrong_primary))
                  )["G4"]["applies"] is False


# G5

def test_g5_hook_parity_raw_bytes_for_p_x_l():
    case = _case("P", hook_exit=0, disposition="proceeded")
    impl = _hook(exit_code=0, disposition="proceeded", stderr=b"a\n")
    base = _hook(exit_code=0, disposition="proceeded", stderr=b"b\n")
    obs = _obs(impl, base, checker_pair={"proposed": {"exit": 0, "stdout_sha256": "x"},
                                         "input": {"exit": 0, "stdout_sha256": "x"}})
    assert _why(case, obs, "G5") == ["hook_stderr"]


@pytest.mark.parametrize("klass", ["P", "X", "L"])
def test_g5_routed_cr_is_scored_at_checker_level_only(klass):
    case = _case(klass, hook_exit=0, disposition="proceeded")
    facts = dict(FACTS, content_has_cr=True)
    assert not h.hook_parity_applies(case, True)
    assert h.checker_parity_applies(case, True)
    impl = _hook(exit_code=0, disposition="proceeded", stdout=b"a")
    base = _hook(exit_code=0, disposition="proceeded", stdout=b"b")
    pair = {"proposed": {"exit": 0, "stdout_sha256": "x"},
            "input": {"exit": 0, "stdout_sha256": "y"}}
    obs = dict(_obs(impl, base, checker_pair=pair), envelope=facts)
    assert _why(case, obs, "G5") == ["checker_stdout"]
    unrouted = _case(klass, routed=False, hook_exit=0, disposition="proceeded")
    assert h.hook_parity_applies(unrouted, True)
    assert not h.checker_parity_applies(unrouted, True)


def test_g5_amendment_2_traceback_frames_only_are_left_out():
    tb = (b"Traceback (most recent call last):\n  File \"x\", line %d, in m\n"
          b"    boom()\nUnicodeEncodeError: 'utf-8' codec\n")
    case = _case("L", routed=False, hook_exit="baseline_observed",
                 disposition="baseline_observed", legacy_baseline_observed=True,
                 evidence_record_expected=False)
    impl = _hook(exit_code=1, disposition="error", records=[], stderr=tb % 920)
    base = _hook(exit_code=1, disposition="error", records=[], stderr=tb % 797)
    result = h.score_case(case, _obs(impl, base), HOST)
    assert result["gates"]["G5"]["pass"] is True
    assert result["diagnostics"]["amendment_2"]["raw_bytes_identical"] is False
    impl = _hook(exit_code=1, disposition="error", records=[], stderr=tb.replace(
        b"codec", b"other") % 920)
    assert _why(case, _obs(impl, base), "G5") == ["a2:exception_summaries"]


# G6

def test_g6_rule_id_set_is_checked_exactly_before_any_value():
    case = _case("MR", applied_numeric_rule_ids=[RID_A, RID_B],
                 relevant_enforcement_per_rule={RID_A: True, RID_B: False})
    rule_b = {"rule_id": RID_B, "matcher_status": "MATCHER_UNEVALUATED",
              "matcher_outcome": "UNEVALUATED", "primary_reason": "SOURCE_NOT_FOUND"}
    rule_a = {"rule_id": RID_A, "matcher_status": "RECOGNIZED", "matcher_outcome": "VIOLATION",
              "primary_reason": None}
    good_eval = [{"per_rule": {RID_A: True, RID_B: False}, "event": True,
                  "evaluation_complete": False}]
    case.expected["evaluation_complete"] = False
    ok = _obs(_hook(records=[_record([rule_a, rule_b], ec=False)], evaluations=good_eval))
    assert _gates(case, ok)["G6"]["pass"], _why(case, ok, "G6")
    bad_eval = [{"per_rule": {}, "event": False, "evaluation_complete": None}]
    for rules in ([rule_a], [rule_a, rule_b, dict(rule_b, rule_id=RID_A[:-1] + "9")],
                  [rule_a, rule_a, rule_b]):
        obs = _obs(_hook(records=[_record(rules, ec=False)], evaluations=bad_eval))
        why = _why(case, obs, "G6")
        assert any(w.startswith("step1:") for w in why)
        assert not any(w.startswith(("step2", "step3", "step4")) for w in why)


def test_g6_empty_set_label_needs_a_record_without_numeric_rules():
    case = _case("P", applied_numeric_rule_ids=[], relevant_enforcement_per_rule={},
                 relevant_enforcement_observed=False, hook_exit=0, disposition="proceeded",
                 expected_cause="no_violation", numeric_rules=[])
    record = _record([], outcome="proceeded", cause="no_violation", subject=False)
    evaluation = [{"per_rule": {}, "event": False, "evaluation_complete": True}]
    impl = _hook(exit_code=0, disposition="proceeded", records=[record],
                 evaluations=evaluation, traces=[])
    pair = {"proposed": {"exit": 0, "stdout_sha256": "x"},
            "input": {"exit": 0, "stdout_sha256": "x"}}
    obs = _obs(impl, checker_pair=pair)
    assert _gates(case, obs)["G6"]["pass"], _why(case, obs, "G6")
    impl["evidence_records"] = [_record(outcome="proceeded", cause="no_violation")]
    assert "step1:rule_id_set" in _why(case, _obs(impl, checker_pair=pair), "G6")


def test_g6_values_come_from_the_builds_evaluation_in_order():
    case = _case()
    for evaluation, reason in (
        ({"per_rule": {RID_A: False}, "event": True, "evaluation_complete": True},
         "step2:per_rule_values"),
        ({"per_rule": {RID_A: True, RID_B: False}, "event": True, "evaluation_complete": True},
         "step2:per_rule_keys"),
        ({"per_rule": {RID_A: True}, "event": False, "evaluation_complete": True},
         "step3:event_level"),
        ({"per_rule": {RID_A: True}, "event": True, "evaluation_complete": None},
         "step4:evaluation_complete"),
    ):
        assert _why(case, _obs(_hook(evaluations=[evaluation])), "G6") == [reason]


def _fallback_case(**overrides) -> "h.Case":
    # The stored evaluation_complete label is null, as R2A1.6 had it written.
    labels = dict(g6_routed_fallback=True, hook_exit=0, disposition="proceeded",
                  expected_cause="fail_open", applied_numeric_rule_ids=[],
                  relevant_enforcement_per_rule={}, relevant_enforcement_observed=False,
                  evaluation_complete=None, numeric_rules=[])
    labels.update(overrides)
    return _case("L", **labels)


def _fallback_hook(trusted: bool, ec) -> dict:
    record = _record([], outcome="proceeded", cause="fail_open", subject=False, ec=ec)
    record["checker"]["trusted"] = trusted
    evaluation = [{"per_rule": {}, "event": False, "evaluation_complete": ec}]
    return _hook(exit_code=0, disposition="proceeded", records=[record],
                 evaluations=evaluation, traces=[], flag="--proposed-new-file")


def test_g6_routed_fallback_expects_a_trusted_false_per_r2_amendment_2():
    """A2R2.2/A2R2.3: a trusted legacy false passes step 4; an untrusted null fails."""
    case = _fallback_case()
    assert h.g6_expectation(case.expected)["evaluation_complete"] is False
    assert _gates(case, _obs(_fallback_hook(True, False)))["G6"]["pass"]
    assert _why(case, _obs(_fallback_hook(False, None)), "G6") == ["step4:evaluation_complete"]
    assert _why(case, _obs(_fallback_hook(True, True)), "G6") == ["step4:evaluation_complete"]
    # The stored null is consistent with the flag; it is not a label finding.
    result = h.score_case(case, _obs(_fallback_hook(True, False)), HOST)
    assert "label_inconsistent_with_r2a1_6" not in result["diagnostics"]["conformance"]


def _no_rule_case() -> "h.Case":
    return _case("P", applied_numeric_rule_ids=[], relevant_enforcement_per_rule={},
                 relevant_enforcement_observed=False, hook_exit=0, disposition="proceeded",
                 expected_cause="no_violation", numeric_rules=[])


def _no_rule_obs() -> dict:
    record = _record([], outcome="proceeded", cause="no_violation", subject=False)
    impl = _hook(exit_code=0, disposition="proceeded", records=[record], traces=[],
                 evaluations=[{"per_rule": {}, "event": False, "evaluation_complete": True}])
    pair = {"proposed": {"exit": 0, "stdout_sha256": "x"},
            "input": {"exit": 0, "stdout_sha256": "x"}}
    return _obs(impl, checker_pair=pair)


@pytest.mark.parametrize("make", [
    lambda: (_fallback_case(), _obs(_fallback_hook(True, False))),
    lambda: (_no_rule_case(), _no_rule_obs()),
    lambda: (_case("LIT", relevant_enforcement_observed=False, hook_exit=2,
                   expected_cause="literal_violation", literal_violation=True,
                   relevant_enforcement_per_rule={RID_A: False},
                   numeric_rules=[_rule(outcome="NO_VIOLATION")]),
             _obs(_hook(records=[_record(
                 [{"rule_id": RID_A, "matcher_status": "RECOGNIZED",
                   "matcher_outcome": "NO_VIOLATION", "primary_reason": None}],
                 cause="other_rule", violations=[{"rule_id": "lit", "rule_type": h.LITERAL}])],
                 evaluations=[{"per_rule": {RID_A: False}, "event": False,
                               "evaluation_complete": True}],
                 traces=[{"rule_type": h.NUMERIC, "rule_id": RID_A, "outcome": "APPLIED",
                          "matcher_status": "RECOGNIZED", "matcher_outcome": "NO_VIOLATION",
                          "primary_reason": None, "unknown_sources": []}]))),
], ids=["routed_fallback", "no_applied_rule", "all_false_relevance"])
@pytest.mark.parametrize("schema", [None, "mneme.hook_evidence/v2", "", "MNEME.HOOK_EVIDENCE/V1"])
def test_g6r_f1_record_schema_must_be_exact_even_when_all_relevance_is_false(make, schema):
    case, obs = make()
    assert _gates(case, obs)["G6"]["pass"], _why(case, obs, "G6")
    record = obs["implementation"]["evidence_records"][0]
    if schema is None:
        del record["schema"]
    else:
        record["schema"] = schema
    assert _why(case, obs, "G6") == ["schema"]


def test_r2_amendment_2_is_keyed_on_the_flag_only():
    """A non-flagged case's null label is never reinterpreted."""
    case = _fallback_case(g6_routed_fallback=False)
    assert h.g6_expectation(case.expected)["evaluation_complete"] is None
    assert _gates(case, _obs(_fallback_hook(False, None)))["G6"]["pass"]
    assert _why(case, _obs(_fallback_hook(True, False)), "G6") == ["step4:evaluation_complete"]


def test_g6_routed_fallback_ignores_other_disagreeing_labels_and_needs_a_record():
    case = _fallback_case(applied_numeric_rule_ids=[RID_A],
                          relevant_enforcement_per_rule={RID_A: False})
    impl = _fallback_hook(True, False)
    result = h.score_case(case, _obs(impl), HOST)
    assert result["gates"]["G6"]["pass"]
    assert "label_inconsistent_with_r2a1_6" in result["diagnostics"]["conformance"]
    impl["evidence_records"], impl["evidence_evaluation"] = [], []
    assert _why(case, _obs(impl), "G6") == ["record_count_0"]


def test_r2_amendment_2_summary_counts_flagged_cases_by_class_with_g6_outcome():
    flagged = _fallback_case()
    plain = _case()
    scored = [(flagged, h.score_case(flagged, _obs(_fallback_hook(True, False)), HOST)),
              (flagged, h.score_case(flagged, _obs(_fallback_hook(False, None)), HOST)),
              (plain, h.score_case(plain, _obs(), HOST))]
    summary = h.r2_amendment_2_summary(scored)
    assert summary["applied"] is True and summary["flagged_cases"] == 2
    assert summary["by_class"] == {"L": {"cases": 2, "g6_fail": 1, "g6_pass": 1}}


def test_g6_unrouted_case_must_have_no_record_and_mode_cause_bindings_are_checked():
    case = _case("L", evidence_record_expected=False, routed=False, hook_exit=0,
                 disposition="proceeded")
    assert _why(case, _obs(_hook(exit_code=0, disposition="proceeded")), "G6") == \
        ["unexpected_record"]
    obs = _obs(_hook(records=[_record(mode="warn", cause="other_rule")]))
    why = _why(_case(), obs, "G6")
    assert "mode" in why and "cause" in why
    record = _record()
    record["carrier_sha256"] = "0" * 64
    assert "binding:carrier_sha256" in _why(_case(), _obs(_hook(records=[record])), "G6")
    record = _record()
    record["host"]["version"] = "other"
    assert "binding:host_identity" in _why(_case(), _obs(_hook(records=[record])), "G6")


@pytest.mark.parametrize("cause,kinds,mapped", [
    ("numeric_violation", [h.NUMERIC], "numeric_violation"),
    ("numeric_violation", [h.NUMERIC, h.LITERAL], "numeric_and_literal_violation"),
    ("other_rule", [h.LITERAL], "literal_violation"),
    ("other_rule", [h.LITERAL, h.NUMERIC], "unmapped:other_rule"),
    ("other_rule", [], "unmapped:other_rule"),
    ("other_rule", ["FORBID_IMPORT"], "unmapped:other_rule"),
    ("no_violation", [], "no_violation"),
    ("fail_open", [], "fail_open"),
    ("availability_refusal", [], "unmapped:availability_refusal"),
    ("not_run", [], "unmapped:not_run"),
    (None, [], "unmapped:None"),
])
def test_cause_mapping_amb_r2_08(cause, kinds, mapped):
    record = {"disposition": {"cause": cause},
              "violations": [{"rule_id": "r", "rule_type": k} for k in kinds]}
    assert h.mapped_cause(record) == mapped
    vocabulary = {"numeric_violation", "literal_violation", "numeric_and_literal_violation",
                  "no_violation", "fail_open"}
    assert (mapped in vocabulary) is not mapped.startswith("unmapped:")


# G8 and aggregation

def test_g8_operational_failure_and_missing_observation_fail_closed():
    result = h.score_case(_case(), {"operational_failures": ["boom"]}, HOST)
    assert not result["gates"]["G8"]["pass"]
    assert all(not result["gates"][g]["pass"] for g in ("G1", "G2", "G3", "G4", "G5", "G6"))
    result = h.score_case(_case(), {"operational_failures": []}, HOST)
    assert result["gates"]["G8"]["why"] == ["not_executed"]


def test_label_conformance_detects_internal_g6_inconsistency():
    case = _case(relevant_enforcement_observed=False)
    result = h.score_case(case, _obs(_hook(evaluations=[
        {"per_rule": {RID_A: True}, "event": False, "evaluation_complete": True}])), HOST)
    assert "label_internal_g6_inconsistency" in result["diagnostics"]["conformance"]


# ── end to end (repository source as both builds) ────────────────────────────

_SYMLINKS = None


def _symlinks(tmp_path) -> bool:
    global _SYMLINKS
    if _SYMLINKS is None:
        _SYMLINKS = h.probe_symlinks(tmp_path / "symprobe")["capable"]
    return _SYMLINKS


def _ctx(root: Path) -> "h.Context":
    return h.Context(sys.executable, sys.executable, HOST[0], HOST[1], root / "w",
                     import_path=str(REPO_ROOT))


def test_end_to_end_synthetic_corpus_passes_every_gate_with_identical_passes(corpus, tmp_path):
    root, pins = corpus
    _, cases = h.verify_corpus(root, pins, None, None)
    run_root = Path(os.path.realpath(tmp_path)) / "run"
    result = h.score_passes(cases, _ctx(run_root), run_root, tmp_path / "out")
    failing = {g: v["failing_cases"] for g, v in result["gates"].items() if not v["pass"]}
    assert failing == {}
    assert result["label_conformance"]["cases_with_mismatch"] == 0
    assert result["public_smoke"]["cases"] == 1
    assert result["public_smoke"]["passes_identical"] is True
    assert result["gates"]["G7"]["applicable"] == len(cases) - 1
    assert result["r2_amendment_2"]["applied"] is True
    assert result["r2_amendment_2"]["flagged_cases"] == 0
    assert result["amendment_2"]["in_scope_by_class"] == {
        "L": {"a2_pass": 1, "cases": 1, "raw_bytes_identical": 1}}
    summary = (tmp_path / "out" / "run-1" / "summary.json").read_text()
    smoke_id = syn.case_id("syn-smoke-v")
    assert smoke_id not in summary and smoke_id not in \
        (tmp_path / "out" / "run-1" / "cases.jsonl").read_text()


def test_end_to_end_routed_fallback_passes_with_a_trusted_false(tmp_path):
    """R2 Amendment 2: at the pinned source a routed link-component fallback writes
    a trusted record whose evaluation_complete is the legacy payload's false. The
    flagged case (stored label null) is scored against false and passes every gate."""
    if not _symlinks(tmp_path):
        pytest.skip("symlinks not available")
    root = tmp_path / "corpus"
    syn.build(root, h, [syn.FALLBACK_SPEC])
    (case,) = h.load_cases(root)[0]
    run_root = Path(os.path.realpath(tmp_path)) / "run"
    run_root.mkdir()
    obs = h.execute_case(case, _ctx(run_root))
    result = h.score_case(case, obs, HOST)
    record = obs["implementation"]["evidence_records"][0]
    assert record["checker"]["subject"] is None and record["rules"] == []
    assert record["checker"]["trusted"] is True
    assert obs["implementation"]["evidence_evaluation"] == [
        {"per_rule": {}, "event": False, "evaluation_complete": False}]
    assert case.expected["evaluation_complete"] is None  # the stored label
    failing = {g: v["why"] for g, v in result["gates"].items() if not v["pass"]}
    assert failing == {}
    assert result["diagnostics"]["conformance"] == []
    assert h.r2_amendment_2_summary([(case, result)])["by_class"] == {
        "L": {"cases": 1, "g6_fail": 0, "g6_pass": 1}}

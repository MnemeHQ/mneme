"""Tests for the ADR-034 G2-1 §8.D scoring harness (benchmarks/adr034_g2_1/).

Every case used here is SYNTHETIC (tests/adr034_g2_1_synthetic_corpus.py),
written by the scorer from the pre-registration, the charter, ADR-034 and
LAYOUT.md; none is drawn from the sealed corpus. The end-to-end tests run
the repository's own source as both builds, so hook-level parity there is
trivially true: they test the pipeline, not G2-1. The pinned-wheel run over
the public smoke cases is in test_adr034_g2_1_harness_smoke.py (opt-in).
"""
from __future__ import annotations

import base64
import copy
import dataclasses
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests import adr034_g2_1_synthetic_corpus as syn

REPO_ROOT = Path(__file__).resolve().parents[1]
_HARNESS = REPO_ROOT / "benchmarks" / "adr034_g2_1" / "harness.py"

_spec = importlib.util.spec_from_file_location("adr034_g2_1_harness", _HARNESS)
h = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = h
_spec.loader.exec_module(h)

HOST = ("2.1.310", "a" * 64)
SYMLINKS = None


def symlinks_capable(tmp_path_factory) -> bool:
    global SYMLINKS
    if SYMLINKS is None:
        SYMLINKS = h.probe_symlinks(tmp_path_factory.mktemp("symprobe"))["capable"]
    return SYMLINKS


def synthetic_pins(values: dict) -> "h.Pins":
    counts = {k: (0, 0) for k in h.CLASSES}
    counts.update(values["counts"])
    return dataclasses.replace(h.G2_PINS, files_sha256_digest=values["files_sha256_digest"],
                               files_count=values["files_count"], counts=counts,
                               is_frozen=False)


# ── pins and preconditions ───────────────────────────────────────────────────

def test_frozen_pins_match_the_preregistration_and_freeze_record():
    p = h.G2_PINS
    assert p.impl_commit == "6e26c534dd78703f811da7d76168f2e2aaaaa23e"
    assert p.baseline_commit == "f8591102b2693379dabec9b5704862e194eca4ce"
    assert p.impl_tree == "34ccbf62b90bac2d6e5e277386a400ac78d86d66"
    assert p.python_version == "3.12.10"
    assert sum(c for c, _ in p.counts.values()) == 122
    assert sum(s for _, s in p.counts.values()) == 7
    assert all(s <= 1 for _, s in p.counts.values())
    floors = {"V": 15, "VP": 8, "C": 15, "US": 8, "UF": 8, "UP": 6, "X": 6, "L": 18,
              "LIT": 6, "W": 6, "P": 8}
    assert all(p.counts[k][0] >= floor for k, floor in floors.items())
    assert set(p.counts) == set(h.CLASSES)


def test_pinned_trees_are_the_git_trees_of_the_pinned_commits():
    for commit, tree in ((h.G2_PINS.impl_commit, h.G2_PINS.impl_tree),
                         (h.G2_PINS.baseline_commit, h.G2_PINS.baseline_tree)):
        out = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", f"{commit}:mneme"],
                             capture_output=True, text=True)
        if out.returncode != 0:
            pytest.skip("pinned commits not in this clone")
        assert out.stdout.strip() == tree


@pytest.fixture
def corpus(tmp_path, tmp_path_factory):
    root = tmp_path / "corpus"
    values = syn.build(root, symlinks=symlinks_capable(tmp_path_factory))
    return root, synthetic_pins(values)


def test_verify_corpus_accepts_the_synthetic_corpus(corpus):
    root, pins = corpus
    record, cases = h.verify_corpus(root, pins, None)
    assert record["files_verified"] == pins.files_count
    assert record["case_index_findings"] == []
    assert all(not c.problems for c in cases)


def test_verify_corpus_refuses_a_changed_file(corpus):
    root, pins = corpus
    target = next((root / "cases").iterdir()) / "expected.json"
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(h.Refusal, match="files_sha256"):
        h.verify_corpus(root, pins, None)


def test_verify_corpus_refuses_an_extra_file(corpus):
    root, pins = corpus
    (root / "cases" / "stray.txt").write_text("x")
    with pytest.raises(h.Refusal, match="corpus_layout"):
        h.verify_corpus(root, pins, None)


def test_verify_corpus_refuses_wrong_counts_and_digest(corpus):
    root, pins = corpus
    counts = dict(pins.counts)
    counts["V"] = (counts["V"][0] + 1, counts["V"][1])
    with pytest.raises(h.Refusal, match="counts"):
        h.verify_corpus(root, dataclasses.replace(pins, counts=counts), None)
    with pytest.raises(h.Refusal, match="files_sha256"):
        h.verify_corpus(root, dataclasses.replace(pins, files_sha256_digest="0" * 64), None)


def test_verify_corpus_checks_the_plaintext_tar_digest(corpus, tmp_path):
    root, pins = corpus
    tar = tmp_path / "corpus.tar"
    tar.write_bytes(b"not the corpus")
    with pytest.raises(h.Refusal, match="corpus_tar"):
        h.verify_corpus(root, pins, tar)
    ok = dataclasses.replace(pins, corpus_tar_sha256=h.sha256_file(tar))
    assert h.verify_corpus(root, ok, tar)[0]["corpus_tar_sha256"] == ok.corpus_tar_sha256


def test_malformed_case_is_kept_and_fails_g8(corpus):
    root, pins = corpus
    directory = next((root / "cases").iterdir())
    expected = json.loads((directory / "expected.json").read_text())
    del expected["numeric_rules"]
    (directory / "expected.json").write_text(json.dumps(expected))
    case = h.load_case(root, directory.name)
    assert "expected.json missing numeric_rules" in case.problems
    obs = {"operational_failures": list(case.problems)}
    gates = h.score_case(case, obs, HOST)["gates"]
    assert not gates["G8"]["pass"]


def test_case_index_shape_is_a_finding_never_a_refusal(corpus):
    root, pins = corpus
    (root / "CASE_INDEX.json").write_text('"opaque"')
    cases = [h.load_case(root, p.name) for p in (root / "cases").iterdir()]
    assert h.case_index_findings(root, cases) == ["CASE_INDEX.json shape not recognized"]


def test_run_root_must_be_new_and_free_of_ancestor_memory(tmp_path):
    existing = tmp_path / "exists"
    existing.mkdir()
    with pytest.raises(h.Refusal, match="exists"):
        h.check_run_root(existing)
    (tmp_path / "parent" / ".mneme").mkdir(parents=True)
    with pytest.raises(h.Refusal, match="ancestor"):
        h.check_run_root(tmp_path / "parent" / "child" / "root")
    assert h.check_run_root(tmp_path / "fresh") == Path(os.path.realpath(tmp_path / "fresh"))


def test_score_refuses_a_malformed_host_identity_before_running(tmp_path):
    final = h.score(corpus=tmp_path / "none", out_dir=tmp_path / "out",
                    impl_python=sys.executable, impl_wheel=tmp_path / "w.whl",
                    base_python=sys.executable, base_wheel=tmp_path / "w.whl",
                    host_version="2.1.310", host_sha256="not-a-digest",
                    run_root=tmp_path / "root")
    assert final["result"] == "REFUSED"
    assert final["refusal"]["check"] == "host_identity"
    assert json.loads((tmp_path / "out" / "summary.json").read_text())["result"] == "REFUSED"


def test_score_refuses_an_interpreter_without_the_pinned_build(tmp_path):
    final = h.score(corpus=tmp_path / "none", out_dir=tmp_path / "out",
                    impl_python=sys.executable, impl_wheel=tmp_path / "w.whl",
                    base_python=sys.executable, base_wheel=tmp_path / "w.whl",
                    host_version="2.1.310", host_sha256="a" * 64,
                    run_root=tmp_path / "root")
    assert final["result"] == "REFUSED"
    assert final["refusal"]["check"] in ("interpreter", "implementation")


def test_git_tree_hash_matches_git_for_the_repository_package():
    out = subprocess.run(["git", "-C", str(REPO_ROOT), "status", "--porcelain", "mneme"],
                         capture_output=True, text=True)
    if out.returncode != 0 or out.stdout.strip():
        pytest.skip("mneme/ is not a clean checkout")
    tree = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD:mneme"],
                          capture_output=True, text=True).stdout.strip()
    assert h.git_tree_hash(REPO_ROOT / "mneme") == tree


def test_wheel_install_verification_detects_a_changed_file(tmp_path):
    import zipfile

    site = tmp_path / "site"
    (site / "mneme").mkdir(parents=True)
    (site / "mneme" / "__init__.py").write_bytes(b"x = 1\n")
    wheel = tmp_path / "mneme_hq-0.0.0-py3-none-any.whl"
    digest = h._urlsafe_sha256(b"x = 1\n")
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("mneme/__init__.py", b"x = 1\n")
        archive.writestr("mneme_hq-0.0.0.dist-info/RECORD",
                         f"mneme/__init__.py,sha256={digest},6\n")
    probe = {"mneme_dir": str(site / "mneme")}
    assert h.verify_wheel_install(probe, wheel, "w")["wheel_files_verified"] == 1
    (site / "mneme" / "extra.py").write_bytes(b"")
    with pytest.raises(h.Refusal, match="not in the wheel"):
        h.verify_wheel_install(probe, wheel, "w")
    (site / "mneme" / "extra.py").unlink()
    (site / "mneme" / "__init__.py").write_bytes(b"x = 2\n")
    with pytest.raises(h.Refusal, match="differs"):
        h.verify_wheel_install(probe, wheel, "w")


# ── fixture materialization ──────────────────────────────────────────────────

def test_envelope_substitution_keeps_every_other_byte(tmp_path):
    raw = ('{"cwd": "{{REPO}}", "tool_input": {"file_path": "{{REPO}}/src/a.py", '
           '"content": "a\\r\\nb\\rc\\ud800\\ufeff"}, "transcript_path": "{{WS}}/t"}')
    ws, repo = Path("C:/w s") if os.name == "nt" else Path("/w s"), None
    repo = ws / "repo"
    out = h.substitute_envelope(raw, ws, repo)
    assert out.count("\\r\\nb\\rc\\ud800\\ufeff") == 1
    parsed = json.loads(out)
    assert parsed["cwd"] == str(repo)
    assert parsed["tool_input"]["file_path"] == f"{repo}/src/a.py"
    assert parsed["tool_input"]["content"] == "a\r\nb\rc\ud800\ufeff"
    with pytest.raises(h.CaseFailure):
        h.substitute_envelope('{"x": "{{OTHER}}"}', ws, repo)


def _case_from_spec(tmp_path, label: str, symlinks: bool = False) -> "h.Case":
    root = tmp_path / "c"
    spec = next(s for s in syn.specs(symlinks) if s["label"] == label)
    cid = syn.write_case(root, spec)
    return h.load_case(root, cid)


def test_materialize_writes_bytes_exactly_and_checks_digests(tmp_path):
    case = _case_from_spec(tmp_path, "l-existing")
    ws = tmp_path / "ws"
    h.materialize(case, ws, ws / "repo", b"{}")
    assert (ws / "repo" / "src" / "router.py").read_bytes() == syn.COMPLIANT.encode()
    assert (ws / "repo" / ".mneme" / "project_memory.json").read_bytes() == b"{}"
    bad = copy.deepcopy(case)
    bad.case["fixture"]["repo_files"][0]["sha256"] = "0" * 64
    with pytest.raises(h.CaseFailure, match="sha256"):
        h.materialize(bad, tmp_path / "ws2", tmp_path / "ws2" / "repo", None)
    escape = copy.deepcopy(case)
    escape.case["fixture"]["repo_files"][0]["path"] = "../outside.py"
    with pytest.raises(ValueError):
        h.materialize(escape, tmp_path / "ws3", tmp_path / "ws3" / "repo", None)


def test_symlink_failure_is_a_g8_failure_never_an_exclusion(tmp_path, monkeypatch):
    case = _case_from_spec(tmp_path, "l-dangling-link", symlinks=True)

    def refuse(*args, **kwargs):
        raise OSError(1314, "A required privilege is not held by the client")

    monkeypatch.setattr(h.os, "symlink", refuse)
    with pytest.raises(h.CaseFailure, match="G2V-F2"):
        h.materialize(case, tmp_path / "ws", tmp_path / "ws" / "repo", None)
    ctx = h.Context(sys.executable, sys.executable, *HOST, tmp_path / "w")
    obs = h.execute_case(case, ctx)
    assert any("G2V-F2" in f for f in obs["operational_failures"])
    gates = h.score_case(case, obs, HOST)["gates"]
    assert not gates["G8"]["pass"]
    assert not (tmp_path / "w" / "ws").exists()


def test_target_state_distinguishes_absent_file_and_change(tmp_path):
    target = tmp_path / "t.py"
    assert h.target_state(target) == {"exists": False}
    target.write_bytes(b"a")
    first = h.target_state(target)
    assert first["kind"] == "file"
    target.write_bytes(b"b")
    assert h.target_state(target) != first


def test_observed_disposition():
    defer = json.dumps({"hookSpecificOutput": {"permissionDecision": "defer"}}).encode()
    assert h.observed_disposition(2, b"") == "refused"
    assert h.observed_disposition(0, defer + b"\n") == "deferred"
    assert h.observed_disposition(0, b"") == "proceeded"
    assert h.observed_disposition(1, b"") == "error"


# ── the observation shim ─────────────────────────────────────────────────────

def test_shim_records_without_changing_stdout_stderr_or_exit(tmp_path):
    fake = tmp_path / "fake"
    (fake / "mneme").mkdir(parents=True)
    (fake / "mneme" / "__init__.py").write_text("")
    (fake / "mneme" / "__main__.py").write_text(
        "import sys\nprint('{\"schema\": \"x\"}')\nsys.stderr.write('err\\n')\nsys.exit(3)\n")
    carrier = tmp_path / "carrier.txt"
    carrier.write_bytes(b"a\r\nb")
    log = tmp_path / "observe.jsonl"
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env["PYTHONPATH"] = os.pathsep.join([str(h.SHIM_DIR), str(fake)])
    argv = [sys.executable, "-m", "mneme", "check", "--input", str(carrier), "--json"]
    without = subprocess.run(argv, capture_output=True, cwd=tmp_path,
                             env=dict(env, PYTHONPATH=str(fake)))
    observed = subprocess.run(argv, capture_output=True, cwd=tmp_path,
                              env=dict(env, MNEME_G2H_OBSERVE_LOG=str(log)))
    assert (observed.returncode, observed.stdout, observed.stderr) == (
        without.returncode, without.stdout, without.stderr) == (
        3, without.stdout, without.stderr)
    (record,) = [json.loads(line) for line in log.read_text().splitlines()]
    assert record["argv"] == ["--input", "<CARRIER>", "--json"]
    assert record["carrier_sha256"] == hashlib.sha256(b"a\r\nb").hexdigest()
    assert json.loads(record["stdout"]) == {"schema": "x"}
    other = subprocess.run([sys.executable, "-c", "print(1)"], capture_output=True,
                           env=dict(env, MNEME_G2H_OBSERVE_LOG=str(tmp_path / "none.jsonl")))
    assert other.stdout.strip() == b"1" and not (tmp_path / "none.jsonl").exists()


# ── scoring: evidence relevance (Amendment 1 A1.3) ───────────────────────────

CONTENT = "X = 1\n"
DIGEST = hashlib.sha256(CONTENT.encode()).hexdigest()
FILE = str(Path(os.path.abspath("/repo/src/a.py")))
CWD = str(Path(os.path.abspath("/repo")))
FACTS = {"file_path": FILE, "cwd": CWD, "tool_name": "Write",
         "identifiers": {"session_id": "s", "tool_use_id": "t"},
         "content_sha256": DIGEST, "content_has_cr": False}
RULE_ID = "ADR-701:FORBID_NUMERIC_ABOVE:" + "1" * 32


def record(outcome="refused", status="RECOGNIZED", result="VIOLATION", reason=None,
           violations=("numeric",), mode="strict", cause="numeric_violation", subject=True):
    rules = [{"rule_id": RULE_ID, "decision_version_id": "dver-1", "governed_path": "src/a.py",
              "applicability": "APPLIED", "matcher_status": status, "matcher_outcome": result,
              "primary_reason": reason, "subject_sha256": DIGEST}] if subject else []
    viol = []
    if "numeric" in violations:
        viol.append({"rule_id": RULE_ID, "rule_type": "FORBID_NUMERIC_ABOVE"})
    if "literal" in violations:
        viol.append({"rule_id": "ADR-702:FORBID_LITERAL:x", "rule_type": "FORBID_LITERAL"})
    return {
        "schema": "mneme.hook_evidence/v1", "surface": "claude_code.PreToolUse",
        "mneme_version": "0.10.0",
        "host": {"version": HOST[0], "executable_sha256": HOST[1]},
        "event": {"tool_name": "Write", "file_path": FILE, "cwd": CWD,
                  "identifiers": {"session_id": "s", "tool_use_id": "t"}},
        "carrier_sha256": DIGEST,
        "checker": {"trusted": True, "problem": None, "subject": {
            "input_kind": "proposed_new_source", "subject_sha256": DIGEST,
            "target_path": str(Path(FILE).resolve()), "governed_path": "src/a.py",
            "absence_verified": True} if subject else None},
        "rules": rules, "violations": viol, "hook_outcome": outcome,
        "disposition": {"mode": mode, "cause": cause},
    }


@pytest.mark.parametrize("rec,mode,expected", [
    (record("proceeded", result="NO_VIOLATION", violations=(), cause="no_violation"),
     "strict", True),
    (record("refused"), "strict", True),
    (record("deferred", mode="warn"), "warn", True),
    (record("refused", status="PARTIAL", reason="UNRECOGNIZED_FORM"), "strict", True),
    (record("proceeded", status="MATCHER_UNEVALUATED", result="UNEVALUATED",
            reason="SOURCE_NOT_FOUND", violations=(), cause="fail_open"), "strict", False),
    (record("refused", result="NO_VIOLATION", violations=("literal",), cause="other_rule"),
     "strict", False),
    (record("deferred", result="NO_VIOLATION", violations=("literal",), mode="warn",
            cause="other_rule"), "warn", False),
    (record("refused", status="PARTIAL", reason="INCOMPLETE_SOURCE_INPUT"), "strict", False),
    (record("proceeded", violations=(), cause="fail_open"), "strict", False),
    (record("proceeded", subject=False, violations=(), cause="no_violation"), "strict", False),
])
def test_scorer_relevance_follows_the_a1_3_table(rec, mode, expected):
    case_value, per_rule = h.scorer_relevance(rec, FACTS, HOST, mode)
    assert case_value is expected
    if rec["rules"]:
        assert per_rule == {"ADR-701": expected}


@pytest.mark.parametrize("mutate", [
    lambda r: r["host"].update(version="2.1.309"),
    lambda r: r["host"].update(executable_sha256="b" * 64),
    lambda r: r.update(carrier_sha256="0" * 64),
    lambda r: r["checker"]["subject"].update(subject_sha256="0" * 64),
    lambda r: r["checker"]["subject"].update(target_path=str(Path(FILE).with_name("b.py"))),
    lambda r: r["checker"]["subject"].update(absence_verified=False),
    lambda r: r["event"].update(identifiers={"session_id": "s"}),
    lambda r: r["rules"][0].update(subject_sha256="0" * 64),
    lambda r: r["rules"][0].update(decision_version_id=""),
    lambda r: r.update(surface="other"),
])
def test_any_binding_mismatch_is_never_relevant(mutate):
    rec = record("refused")
    mutate(rec)
    assert h.record_binding_problems(rec, FACTS, HOST)
    assert h.scorer_relevance(rec, FACTS, HOST, "strict")[0] is False


def test_expected_cause_mapping():
    assert h.expected_cause({"evidence_hook_outcome": "refused",
                             "block_attributed_to": ["literal", "numeric"]}) == "numeric_violation"
    assert h.expected_cause({"evidence_hook_outcome": "refused",
                             "block_attributed_to": ["literal"]}) == "other_rule"
    assert h.expected_cause({"evidence_hook_outcome": "deferred",
                             "block_attributed_to": ["numeric"]}) == "numeric_violation"
    unevaluated = {"ADR-701": {"applicability": "APPLIED", "matcher_status": "MATCHER_UNEVALUATED"}}
    assert h.expected_cause({"evidence_hook_outcome": "proceeded",
                             "numeric_rules": unevaluated}) == "fail_open"
    assert h.expected_cause({"evidence_hook_outcome": "proceeded", "numeric_rules": {}}) == \
        "no_violation"
    assert h.expected_cause({"evidence_hook_outcome": None}) is None


# ── scoring: gates on hand-built observations ────────────────────────────────

def _payload(status, result, reason, kind="proposed_new_source"):
    return json.dumps({"subject": {"input_kind": kind}, "applicability": [
        {"rule_type": "FORBID_NUMERIC_ABOVE", "rule_id": RULE_ID, "outcome": "APPLIED",
         "matcher_status": status, "matcher_outcome": result, "primary_reason": reason,
         "unknown_sources": []}]})


def hook_obs(exit_code=0, disposition="proceeded", stdout=b"", stderr=b"", records=(),
             payload=None, flag="--proposed-new-file", before=None, after=None):
    before = before or {"exists": False}
    return {
        "exit": exit_code, "disposition": disposition,
        "stdout_b64": base64.b64encode(stdout).decode(), "stdout_sha256": h.sha256_bytes(stdout),
        "stderr_b64": base64.b64encode(stderr).decode(), "stderr_sha256": h.sha256_bytes(stderr),
        "target_before": before, "target_after": after or before,
        "evidence_records": list(records),
        "invocations": [] if payload is None else [{"input_flag": flag, "stdout": payload}],
    }


def make_case(klass, mode="strict", **expected) -> "h.Case":
    e = {key: None for key in h.EXPECTED_KEYS}
    e.update({"case_id": "g2h-0000000000", "class": klass, "public_smoke": False,
              "hook_mode": mode, "availability": "open", "expected_from_baseline": False,
              "numeric_rules": {}, "block_attributed_to": [], "literal_violation": False,
              "target_after_hook": "absent", "g2_evidence_record_expected": False,
              "relevant_enforcement_observed_per_rule": {}, "content_utf8_sha256": DIGEST})
    e.update(expected)
    return h.Case("g2h-0000000000", klass, False, {"hook": {"mode": mode}}, e, "", [])


def obs_of(impl, base=None, pair=None, facts=FACTS, failures=()):
    obs = {"implementation": impl, "baseline": base or impl, "envelope": facts,
           "operational_failures": list(failures)}
    if pair is not None:
        obs["checker_pair"] = pair
    return obs


def failing(result, gate):
    return result["gates"][gate]["applies"] and not result["gates"][gate]["pass"]


V_EXPECTED = dict(hook_exit=2, numeric_rules={"ADR-701": {
    "applicability": "APPLIED", "matcher_status": "RECOGNIZED", "matcher_outcome": "VIOLATION",
    "primary_reason": None}}, g2_evidence_record_expected=True, evidence_hook_outcome="refused",
    block_attributed_to=["numeric"], relevant_enforcement_observed=True,
    relevant_enforcement_observed_per_rule={"ADR-701": True}, hook_routed=True)


def test_a_conforming_v_case_passes_every_gate():
    impl = hook_obs(2, "refused", records=[record("refused")],
                    payload=_payload("RECOGNIZED", "VIOLATION", None))
    result = h.score_case(make_case("V", **V_EXPECTED), obs_of(impl), HOST)
    assert all(g["pass"] for g in result["gates"].values()), result


def test_g1a_expected_block_observed_proceeding_is_unsafe_whatever_the_labels():
    impl = hook_obs(0, "proceeded", records=[record("refused")],
                    payload=_payload("RECOGNIZED", "VIOLATION", None))
    result = h.score_case(make_case("V", **V_EXPECTED), obs_of(impl), HOST)
    assert "a:expected_block_not_refused" in result["gates"]["G1"]["why"]
    lit = make_case("LIT", hook_exit=2, literal_violation=True)
    assert failing(h.score_case(lit, obs_of(hook_obs(0)), HOST), "G1")
    warn = make_case("V", mode="warn", **{**V_EXPECTED, "hook_exit": 0})
    assert not failing(h.score_case(warn, obs_of(hook_obs(0)), HOST), "G1")


def test_g1b_nonclean_expected_observed_no_violation():
    expected = dict(numeric_rules={"ADR-701": {"applicability": "APPLIED",
                                               "matcher_status": "MATCHER_UNEVALUATED",
                                               "matcher_outcome": "UNEVALUATED",
                                               "primary_reason": "SOURCE_NOT_FOUND"}})
    impl = hook_obs(payload=_payload("RECOGNIZED", "NO_VIOLATION", None))
    result = h.score_case(make_case("US", **expected), obs_of(impl), HOST)
    assert "b:nonclean_observed_no_violation" in result["gates"]["G1"]["why"]


def test_g1c_relevant_claim_where_none_is_expected():
    impl = hook_obs(2, "refused", records=[record("refused")],
                    payload=_payload("RECOGNIZED", "VIOLATION", None))
    case = make_case("V", **{**V_EXPECTED, "relevant_enforcement_observed": False,
                             "relevant_enforcement_observed_per_rule": {"ADR-701": False}})
    assert "c:unexpected_relevant_claim" in h.score_case(case, obs_of(impl), HOST)["gates"]["G1"]["why"]


def test_g2_false_block_and_its_exclusions():
    assert failing(h.score_case(make_case("C"), obs_of(hook_obs(2, "refused")), HOST), "G2")
    lit = make_case("LIT", literal_violation=True, hook_exit=2)
    assert not h.score_case(lit, obs_of(hook_obs(2, "refused")), HOST)["gates"]["G2"]["applies"]
    a14 = make_case("L", expected_from_baseline=True)
    assert not h.score_case(a14, obs_of(hook_obs(2, "refused")), HOST)["gates"]["G2"]["applies"]
    literal_c = make_case("C", literal_violation=True)
    assert not h.score_case(literal_c, obs_of(hook_obs(2)), HOST)["gates"]["G2"]["applies"]


def test_g3_target_after_block_and_any_change():
    present = {"exists": True, "kind": "file", "sha256": "1" * 64}
    impl = hook_obs(2, "refused", after=present)
    assert "target_present_after_block" in h.score_case(
        make_case("V"), obs_of(impl), HOST)["gates"]["G3"]["why"]
    changed = hook_obs(0, before=present, after={**present, "sha256": "2" * 64})
    result = h.score_case(make_case("L", target_after_hook="unchanged"), obs_of(changed), HOST)
    assert "target_changed" in result["gates"]["G3"]["why"]
    dangling = {"exists": True, "kind": "link", "link_text": "m", "referent": {"exists": False}}
    ok = h.score_case(make_case("L", target_after_hook="unchanged_dangling_link"),
                      obs_of(hook_obs(0, before=dangling)), HOST)
    assert ok["gates"]["G3"]["pass"]


def test_g4_primary_reason_is_scored_for_unevaluated_classes_only():
    expected = dict(numeric_rules={"ADR-701": {"applicability": "APPLIED",
                                               "matcher_status": "MATCHER_UNEVALUATED",
                                               "matcher_outcome": "UNEVALUATED",
                                               "primary_reason": "PARSE_FAILURE"}})
    wrong = hook_obs(payload=_payload("MATCHER_UNEVALUATED", "UNEVALUATED", "UNRECOGNIZED_FORM"))
    assert failing(h.score_case(make_case("UP", **expected), obs_of(wrong), HOST), "G4")
    assert failing(h.score_case(make_case("UP", **expected), obs_of(hook_obs()), HOST), "G4")
    right = hook_obs(payload=_payload("MATCHER_UNEVALUATED", "UNEVALUATED", "PARSE_FAILURE"))
    assert h.score_case(make_case("UP", **expected), obs_of(right), HOST)["gates"]["G4"]["pass"]
    assert not h.score_case(make_case("C", **expected), obs_of(wrong), HOST)["gates"]["G4"]["applies"]


def test_g5_hook_level_is_a_raw_byte_comparison_with_a_diagnostic_only_normalization():
    tb = lambda path, line: (f'Traceback (most recent call last):\n  File "{path}", line {line}, '
                             'in f\n    x()\n    ^^^\nValueError: boom\n').encode()
    impl = hook_obs(1, "error", stderr=tb("/a/hook.py", 920))
    base = hook_obs(1, "error", stderr=tb("/b/hook.py", 797))
    result = h.score_case(make_case("L", expected_from_baseline=True,
                                    target_after_hook="absent"), obs_of(impl, base), HOST)
    assert "hook_stderr" in result["gates"]["G5"]["why"]
    assert result["diagnostics"]["stderr"]["normalized_equal"] is True
    assert result["diagnostics"]["stderr"]["gating"] is False
    other = hook_obs(1, "error", stderr=tb("/a/hook.py", 920).replace(b"boom", b"other"))
    diag = h.score_case(make_case("L"), obs_of(other, base), HOST)["diagnostics"]["stderr"]
    assert diag["normalized_equal"] is False


def test_g5_routed_cr_exception_keeps_checker_level_parity():
    facts = {**FACTS, "content_has_cr": True}
    impl, base = hook_obs(0, stdout=b"a"), hook_obs(0, stdout=b"b")
    pair_ok = {"proposed": {"exit": 0, "stdout_sha256": "x"}, "input": {"exit": 0, "stdout_sha256": "x"}}
    routed_p = make_case("P", hook_routed=True)
    result = h.score_case(routed_p, obs_of(impl, base, pair_ok, facts), HOST)
    assert result["gates"]["G5"]["pass"]
    unrouted_l = make_case("L", hook_routed=False)
    assert failing(h.score_case(unrouted_l, obs_of(impl, base, None, facts), HOST), "G5")
    pair_bad = {"proposed": {"exit": 0, "stdout_sha256": "x"}, "input": {"exit": 2, "stdout_sha256": "y"}}
    why = h.score_case(routed_p, obs_of(impl, impl, pair_bad, facts), HOST)["gates"]["G5"]["why"]
    assert {"checker_exit", "checker_stdout"} <= set(why)
    assert "checker_pair_missing" in h.score_case(routed_p, obs_of(impl, impl, None, facts),
                                                  HOST)["gates"]["G5"]["why"]


def test_g6_record_count_cause_and_unrouted_records():
    payload = _payload("RECOGNIZED", "VIOLATION", None)
    none = hook_obs(2, "refused", payload=payload)
    assert "record_count_0" in h.score_case(make_case("V", **V_EXPECTED), obs_of(none),
                                            HOST)["gates"]["G6"]["why"]
    two = hook_obs(2, "refused", records=[record("refused")] * 2, payload=payload)
    assert "record_count_2" in h.score_case(make_case("V", **V_EXPECTED), obs_of(two),
                                            HOST)["gates"]["G6"]["why"]
    wrong_cause = hook_obs(2, "refused", records=[record("refused", cause="other_rule")],
                           payload=payload)
    assert "cause" in h.score_case(make_case("V", **V_EXPECTED), obs_of(wrong_cause),
                                   HOST)["gates"]["G6"]["why"]
    stray = hook_obs(0, records=[record("proceeded")], flag="--input", payload=payload)
    assert "unexpected_record" in h.score_case(make_case("L"), obs_of(stray),
                                               HOST)["gates"]["G6"]["why"]


def test_g8_operational_failure_and_missing_observation_fail_closed():
    result = h.score_case(make_case("C"), {"operational_failures": ["hook timed out"]}, HOST)
    assert failing(result, "G8")
    assert all(failing(result, g) for g in ("G1", "G2", "G3", "G4", "G5", "G6"))
    captured = h.score_case(make_case("L", expected_from_baseline=True),
                            obs_of(hook_obs(1, "error", stderr=b"Traceback\n")), HOST)
    assert captured["gates"]["G8"]["pass"]


# ── passes, aggregation, G7 ──────────────────────────────────────────────────

def test_smoke_cases_are_never_in_a_gate_denominator(tmp_path, monkeypatch):
    concealed = make_case("C")
    smoke = dataclasses.replace(make_case("V", **V_EXPECTED), case_id="g2h-1111111111",
                                public_smoke=True)
    monkeypatch.setattr(h, "execute_case", lambda case, ctx: obs_of(hook_obs(0)))
    ctx = h.Context(sys.executable, sys.executable, *HOST, tmp_path / "w")
    summary = h.run_pass([concealed, smoke], ctx, HOST, tmp_path / "run")
    assert summary["concealed_cases"] == 1
    assert summary["gates"]["G1"]["applicable"] == 1 and summary["gates"]["G1"]["pass"]
    assert summary["public_smoke"]["gates"]["G1"]["failures"] == 1


def test_g7_compares_two_full_passes_byte_for_byte(tmp_path, monkeypatch):
    calls = []

    def fake(case, ctx):
        calls.append(case.case_id)
        stdout = b"x" if len(calls) <= 2 else b"y"
        return obs_of(hook_obs(0, stdout=stdout))

    cases = [make_case("C"), dataclasses.replace(make_case("C"), case_id="g2h-2222222222")]
    monkeypatch.setattr(h, "execute_case", fake)
    ctx = h.Context(sys.executable, sys.executable, *HOST, tmp_path / "root" / "w")
    result = h.score_passes(cases, ctx, tmp_path / "root", tmp_path / "out")
    assert not result["gates"]["G7"]["pass"]
    assert result["gates"]["G7"]["failing_cases"] == ["g2h-0000000000", "g2h-2222222222"]
    assert not (tmp_path / "root").exists()
    calls.clear()
    monkeypatch.setattr(h, "execute_case", lambda case, ctx: obs_of(hook_obs(0)))
    again = h.score_passes(cases, ctx, tmp_path / "root", tmp_path / "out2")
    assert again["gates"]["G7"]["pass"]


# ── end to end on the synthetic corpus (repository source as both builds) ────

def test_end_to_end_synthetic_corpus_passes_every_gate(corpus, tmp_path):
    root, pins = corpus
    _, cases = h.verify_corpus(root, pins, None)
    run_root = Path(os.path.realpath(tmp_path)) / "run"
    ctx = h.Context(sys.executable, sys.executable, *HOST, run_root / "w",
                    import_path=str(REPO_ROOT))
    result = h.score_passes(cases, ctx, run_root, tmp_path / "out")
    failures = {g: v["failing_cases"] for g, v in result["gates"].items() if not v["pass"]}
    assert failures == {}
    assert result["label_conformance_mismatches"] == {}
    assert result["gates"]["G5"]["applicable"] >= 6
    assert result["gates"]["G4"]["applicable"] == 2
    lines = (tmp_path / "out" / "run-1" / "cases.jsonl").read_text().splitlines()
    by_label = {json.loads(line)["case_id"]: json.loads(line) for line in lines}
    surrogate = by_label[syn.case_id("l-surrogate")]
    assert surrogate["implementation"]["exit"] not in (0, 2)  # captured legacy error (A1.4)
    assert surrogate["score"]["gates"]["G8"]["pass"]
    blank = by_label[syn.case_id("l-blank")]
    assert blank["implementation"]["invocations"] == []  # A1.2: no checker call
    summary = (tmp_path / "out" / "run-1" / "summary.json").read_text()
    assert "syn-" not in summary and "ROUTER_DEADLINE_S" not in summary  # opaque ids only

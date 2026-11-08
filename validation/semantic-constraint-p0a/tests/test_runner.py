"""Tests for the P0-A detector experiment runner and its committed evidence.

The fresh runs here use M1 to M4 only; M0 shells out to the shipped CLI per
subject and is covered by the committed two-run evidence instead. Run
explicitly (not collected by default CI):

    python -m pytest validation/semantic-constraint-p0a/tests -v
"""

import json
import sys
from pathlib import Path

import pytest

P0A_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P0A_DIR / "scripts"))

import run_detectors  # noqa: E402
from run_detectors import NO_VIOLATION, UNEVALUATED, VIOLATION, dump, sha256_bytes  # noqa: E402

FAST = ("M1", "M2", "M3", "M4")
EVIDENCE = P0A_DIR / "evidence" / "detectors"


@pytest.fixture(scope="module")
def fresh():
    return run_detectors.run(FAST)


def test_every_combination_has_exactly_one_valid_verdict(fresh):
    _, rows = fresh
    keys = [(r["method"], r["case"], r["question"], r["probe"], r["sub_constraint"]) for r in rows]
    assert len(keys) == len(set(keys))
    assert {r["verdict"] for r in rows} <= {VIOLATION, NO_VIOLATION, UNEVALUATED}
    static = {(r["method"], r["case"], r["question"]) for r in rows if r["method"] in ("M1", "M2", "M3")}
    for method in ("M1", "M2", "M3"):
        for case in [*"ABCDEF", "G", "H", "I", "J", "K", "L", "M-5", "M-5.0001", "N", "O", "P", "Q", "R", "S", "T", "U"]:
            assert (method, case, "audit") in static
        assert (method, "T", "gate") in static and (method, "U", "gate") in static


def test_every_verdict_is_bound(fresh):
    _, rows = fresh
    manifest_sha = sha256_bytes(run_detectors.run_freeze.MANIFEST.read_bytes())
    for r in rows:
        b = r["binding"]
        assert b["decision_id"] == "ADR-001"
        assert b["method_id"] == r["method"] and b["method_version"]
        assert b["question"] == r["question"] and b["sub_constraint"] == r["sub_constraint"]
        assert b["freeze_commit"] == "f5c910bc0cad7a5cd9bf99ba3c831cdc5ba016bd"
        assert b["manifest_sha256"] == manifest_sha
        assert b["oracle_version"] == "p0a-oracle-v2.0.0"
        assert len(b["case_content_sha256"]) == 64
        assert (b["case_before_sha256"] is not None) == (r["question"] == "gate")


def test_case_digests_match_the_manifest(fresh):
    _, rows = fresh
    manifest = json.loads(run_detectors.run_freeze.MANIFEST.read_bytes())
    pinned = {c["id"]: c["files"]["after"]["sha256"] for c in manifest["set1_cases"]}
    pinned.update({c["id"]: c["content_sha256"] for c in manifest["set0"]["cases"]})
    for r in rows:
        assert r["binding"]["case_content_sha256"] == pinned[r["case"]]


def test_f_is_never_scored(fresh):
    _, rows = fresh
    assert all(not r["scored"] for r in rows if r["case"] == "F")


def test_t_counts_only_at_the_gate_and_c_once_on_audit(fresh):
    _, rows = fresh
    assert all(not r["scored"] for r in rows if r["case"] == "T" and r["question"] != "gate")
    assert any(r["scored"] for r in rows if r["case"] == "T" and r["question"] == "gate")
    assert any(r["scored"] for r in rows if r["case"] == "C" and r["question"] == "audit")


def test_u_is_never_stopped_at_the_gate(fresh):
    _, rows = fresh
    gate_u = [r for r in rows if r["case"] == "U" and r["question"] == "gate"]
    assert gate_u and all(r["verdict"] != VIOLATION for r in gate_u)


def test_edit_deltas(fresh):
    summary, _ = fresh
    assert summary["edit_cases"]["T"]["introduced_line_numbers"] == [3]
    assert summary["edit_cases"]["U"]["introduced_line_numbers"] == []


def test_non_targeted_sub_constraints_are_unevaluated_and_unscored(fresh):
    _, rows = fresh
    for r in rows:
        if r["sub_constraint"] not in run_detectors.TARGETS[r["method"]]:
            assert r["verdict"] == UNEVALUATED and not r["scored"]


def test_m4_reproduces_the_frozen_observations(fresh):
    summary, _ = fresh
    assert summary["m4_matches_frozen_observations"] is True


def test_s_env_enabled_probe_is_supplemental(fresh):
    _, rows = fresh
    enabled = [r for r in rows if r["case"] == "S" and r["probe"] == "env_enabled"]
    assert len(enabled) == 3 and not any(r["scored"] for r in enabled)
    assert next(r for r in enabled if r["sub_constraint"] == "C1")["verdict"] == VIOLATION


def test_fresh_run_is_deterministic(fresh):
    summary, rows = fresh
    again, again_rows = run_detectors.run(FAST)
    assert dump(summary) == dump(again)
    assert run_detectors.to_csv(rows) == run_detectors.to_csv(again_rows)


def test_freeze_failure_stops_before_evaluation(monkeypatch):
    monkeypatch.setattr(run_detectors.run_freeze, "verify", lambda: ["fixture digest mismatch: x"])
    monkeypatch.setattr(run_detectors, "load_subjects", lambda: pytest.fail("evaluated after a failed verify"))
    with pytest.raises(run_detectors.RunError):
        run_detectors.run(FAST)


def test_introduced_line_numbers_skip_blank_lines():
    numbers, introduced, removed = run_detectors.introduced_line_numbers("a\nb\n", "a\n\nc\nb\n")
    assert numbers == (3,) and introduced == ["", "c"] and removed == []


# ── Committed evidence ──────────────────────────────────────────────────────


def committed_summary() -> dict:
    return json.loads((EVIDENCE / "summary.json").read_text(encoding="utf-8"))


def test_committed_static_and_m4_verdicts_match_a_fresh_run(fresh):
    _, rows = fresh
    committed = [r for r in committed_summary()["verdicts"] if r["method"] in FAST]
    assert committed == rows


def test_committed_runs_are_byte_identical():
    repro = json.loads((EVIDENCE / "reproducibility.json").read_text(encoding="utf-8"))
    assert repro["byte_identical"] is True
    digests = list(repro["runs"].values())
    assert len(digests) == 2 and digests[0] == digests[1]
    assert digests[0]["summary.json"] == sha256_bytes((EVIDENCE / "summary.json").read_bytes())
    assert digests[0]["summary.csv"] == sha256_bytes((EVIDENCE / "summary.csv").read_bytes())
    for record in repro["records"].values():
        assert record["git_tree_clean"] is True
        assert record["mneme_runtime_for_m0"]["from_this_checkout"] is True


def test_committed_hypothesis_checks_and_m0_baseline():
    summary = committed_summary()
    assert summary["methods_run"] == ["M0", "M1", "M2", "M3", "M4"]
    assert summary["m0_matches_570_cli_labels"]["all_match"] is True
    for name in ("HA1", "HA2", "HA3"):
        assert all("holds" in c for c in summary["hypotheses"][name]["checks"])

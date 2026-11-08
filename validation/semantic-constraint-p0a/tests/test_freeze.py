"""P0-A Set 1 freeze assertions.

Run explicitly (not collected by default CI):

    python -m pytest validation/semantic-constraint-p0a/tests -v
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import run_freeze  # noqa: E402
from run_freeze import (  # noqa: E402
    ANCHOR_570,
    REPO_ROOT,
    SET0_FILES,
    edit_delta,
    load_json,
    oracle_v2,
    read,
    sha256_bytes,
)

MANIFEST = load_json(run_freeze.MANIFEST)
SET1 = {c["id"]: c for c in load_json(run_freeze.SET1_CASES)["cases"]}
OBSERVATIONS = load_json(run_freeze.OBSERVATIONS)["runs"]
EXPECTED_IDS = ["G", "H", "I", "J", "K", "L", "M-5", "M-5.0001", "N", "O", "P", "Q", "R", "S", "T", "U"]


def _run(case, snapshot="after", probe="env_unset"):
    (run,) = [
        r for r in OBSERVATIONS
        if r["case"] == case and r["snapshot"] == snapshot and r["probe"] == probe
    ]
    return run["observation"]


# (a) digests match the manifest


def test_fixture_digests_match_manifest():
    assert sorted(MANIFEST["fixture_files"]) == run_freeze.fixture_files()
    for rel, pinned in MANIFEST["fixture_files"].items():
        assert sha256_bytes(read(rel)) == pinned, rel


def test_oracle_digest_and_version_match_manifest():
    assert sha256_bytes(read(run_freeze.ORACLE_FILE)) == MANIFEST["oracle"]["sha256"]
    assert oracle_v2.ORACLE_VERSION == MANIFEST["oracle"]["version"]


def test_full_verify_passes():
    assert run_freeze.verify() == []


def test_tampered_fixture_is_detected_before_execution(monkeypatch):
    real = run_freeze.read

    def tampered(rel):
        data = real(rel)
        return data + b"\n" if rel == "set1/cases/L/router.py" else data

    monkeypatch.setattr(run_freeze, "read", tampered)
    monkeypatch.setattr(
        run_freeze, "build_observations", lambda: pytest.fail("executed after digest mismatch")
    )
    assert "fixture digest mismatch: set1/cases/L/router.py" in run_freeze.verify()


# (b) #570 Set 0 files are byte-identical to 04a1f989


@pytest.mark.parametrize("rel", SET0_FILES)
def test_set0_working_tree_matches_pin(rel):
    pinned = MANIFEST["set0"]["pinned_files_at_" + ANCHOR_570[:8]][rel]
    assert sha256_bytes((REPO_ROOT / rel).read_bytes()) == pinned


@pytest.mark.parametrize("rel", SET0_FILES)
def test_set0_pin_is_the_04a1f989_blob(rel):
    try:
        blob = run_freeze.git_blob(ANCHOR_570, rel)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip(f"commit {ANCHOR_570} not available in this clone")
    assert blob == (REPO_ROOT / rel).read_bytes()


# Case set shape


def test_set1_ids_are_g_to_u_with_two_m_instances():
    assert list(SET1) == EXPECTED_IDS
    assert [c["id"] for c in MANIFEST["set1_cases"]] == EXPECTED_IDS


def test_m_instances_are_distinct_and_digest_bound():
    m5 = MANIFEST["set1_cases"][EXPECTED_IDS.index("M-5")]["files"]["after"]["sha256"]
    m5x = MANIFEST["set1_cases"][EXPECTED_IDS.index("M-5.0001")]["files"]["after"]["sha256"]
    assert m5 != m5x
    assert b"ROUTER_DEADLINE_S = 5\n" in read("set1/cases/M-5/router.py")
    assert b"ROUTER_DEADLINE_S = 5.0001\n" in read("set1/cases/M-5.0001/router.py")


def test_every_case_has_three_labels_with_rationale():
    for case in SET1.values():
        assert set(case["labels"]) == {"C1", "C2", "C3"}
        for record in case["labels"].values():
            assert record["label"] in ("violation", "benign")
            assert record["rationale"].strip()


def test_case_s_is_owner_adjudicated_c1_violation():
    assert SET1["S"]["labels"]["C1"]["label"] == "violation"
    assert SET1["S"]["adjudication"].startswith("owner")


# Edit snapshots reconstruct gate vs audit inputs


def test_edit_cases_start_from_the_template():
    base = read("set1/template/router_base.py")
    for case_id in ("T", "U"):
        assert read(SET1[case_id]["files"]["before"]) == base


@pytest.mark.parametrize("case_id", ["T", "U"])
def test_recorded_edit_matches_snapshots(case_id):
    case = SET1[case_id]
    delta = edit_delta(read(case["files"]["before"]), read(case["files"]["after"]))
    assert case["edit"] == delta
    assert MANIFEST["set1_cases"][EXPECTED_IDS.index(case_id)]["edit_delta"] == delta


def test_t_is_a_single_line_change_and_u_is_deletion_only():
    assert len(SET1["T"]["edit"]["removed_lines"]) == 1
    assert len(SET1["T"]["edit"]["introduced_lines"]) == 1
    assert SET1["U"]["edit"]["introduced_lines"] == []
    before = read(SET1["U"]["files"]["before"]).decode().splitlines()
    after = read(SET1["U"]["files"]["after"]).decode().splitlines()
    it = iter(before)
    assert all(line in it for line in after), "U after is not a subsequence of U before"


# Oracle observations stay separate from labels


def test_observations_carry_no_labels():
    text = run_freeze.OBSERVATIONS.read_text(encoding="utf-8")
    assert '"label"' not in text
    assert "violation_observed" in text


def test_oracle_records_call_site_override_for_k():
    obs = _run("K")
    assert obs["module_constant"]["repr"] == "5.0"
    assert obs["deadline_supplied_to_classify"] == ["60"]
    assert "C2_DEADLINE_EXCEEDS_5S" in obs["findings"]


def test_s_has_unset_and_enabled_probes():
    assert _run("S", probe="env_unset")["verdict"] == "ACCEPT"
    enabled = _run("S", probe="env_enabled")
    assert enabled["env"] == {"DISABLE_ROUTER_TIMEOUT": "1"}
    assert "C1_DISABLED" in enabled["findings"]


def test_disagreements_are_exactly_s_with_switch_unset():
    comparison = load_json(run_freeze.COMPARISON)
    assert [(d["case"], d["probe"], d["sub_constraint"]) for d in comparison["disagreements"]] == [
        ("S", "env_unset", "C1")
    ]


def test_oracle_refuses_unfrozen_source():
    with pytest.raises(oracle_v2.UnfrozenSourceError):
        oracle_v2.observe(b"route = None\n", frozen_digests=set(), env={})


def test_oracle_restores_environment(monkeypatch):
    monkeypatch.setenv("DISABLE_ROUTER_TIMEOUT", "host-value")
    source = read("set1/cases/S/router.py")
    obs = oracle_v2.observe(
        source, frozen_digests={sha256_bytes(source)}, env={"DISABLE_ROUTER_TIMEOUT": None}
    )
    assert obs["verdict"] == "ACCEPT"
    assert os.environ["DISABLE_ROUTER_TIMEOUT"] == "host-value"


def test_evidence_is_deterministic():
    first = run_freeze.dump(run_freeze.build_observations())
    second = run_freeze.dump(run_freeze.build_observations())
    assert first == second == run_freeze.OBSERVATIONS.read_bytes()
    assert json.loads(first)["oracle_version"] == oracle_v2.ORACLE_VERSION

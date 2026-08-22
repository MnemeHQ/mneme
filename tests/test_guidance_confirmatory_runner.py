import importlib.util
from pathlib import Path

RUNNER_PATH = (
    Path(__file__).resolve().parents[1] / "scripts"
    / "run_guidance_confirmatory_ab.py"
)
SPEC = importlib.util.spec_from_file_location("guidance_confirmatory_runner", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)

EXPECTED_ROLE_LOCK_HASHES = {
    "docs/validation/pre-generation-guidance-role-r1-lock.json": (
        "873A050A512A7F4ABDD389963EE24C840398D1231DE797BF844CC0F16FA7D5E0"
    ),
    "docs/validation/pre-generation-guidance-role-r2-lock.json": (
        "0BBAA6130D1E9B0100938845775A01723317B880326629EF1086961A59445F13"
    ),
    "docs/validation/pre-generation-guidance-role-r3-lock.json": (
        "741860213095F6CCE21C02BE70498C2B3CF1CBF5C9F3660A55C01D18ADDBF600"
    ),
    "docs/validation/pre-generation-guidance-role-r4-lock.json": (
        "49C4ADAA6C812E86594567CE30DE6169D1DE180EB300FD0BE86BE1E3D939B198"
    ),
    "docs/validation/pre-generation-guidance-role-r5-lock.json": (
        "6A15692479DDDB1214330EF05AE6643BD2D6B920D147E0E74C2A322BAC315DB7"
    ),
}


def test_r6_uses_new_mechanism_only_lock_and_artifact_directory():
    assert RUNNER.EVALUATIONS == ("mechanism_isolation",)
    assert RUNNER.EXPECTED_API_KEY_SOURCE == "none"
    assert RUNNER.EXECUTION_LOCK.name == (
        "pre-generation-guidance-role-r6-execution-lock.json"
    )
    assert RUNNER.OUTPUT_ROOT.name == (
        "pre-generation-guidance-role-r6-2026-08-14"
    )

    schedule = RUNNER._ordered_runs("mechanism_isolation")
    assert len(schedule) == 42
    assert sum(run["arm"] == "baseline" for run in schedule) == 21
    assert sum(run["arm"] == "treatment" for run in schedule) == 21
    assert {run["evaluation"] for run in schedule} == {
        "mechanism_isolation"
    }


def test_r6_preserves_role_locks_r5_lint_gate_and_e66():
    assert RUNNER._role_lock_manifest() == EXPECTED_ROLE_LOCK_HASHES
    assert RUNNER._e66_manifest() == {
        "execution_lock_sha256": (
            "E66ED251BED91D52A55ECB90B1EE6198E80970C45B7AC04759483F0BDF04195C"
        ),
        "file_count": 547,
        "collection_manifest_sha256": (
            "46B215D324A1C90E21615F0233D99DD695A5D883671CE44A72F362D3EEFDF0DE"
        ),
    }

    r5 = RUNNER._r5_validation()
    assert r5["status"] == "R5_LOCKED_READY_FOR_R6"
    assert r5["changed_surface_ruff_gate"]["status"] == "PASS"
    assert r5["changed_surface_ruff_gate"]["findings"] == 0
    assert r5["whole_repository_ruff_baseline"] == {
        "status": "RECORDED_EXCLUDED_FROM_EXPERIMENT_GATE",
        "configuration_present": False,
        "pre_existing_findings": 145,
        "cleanup_authorized": False,
        "new_lint_policy_authorized": False,
    }


def test_r6_candidate_manifest_includes_role_remediation_and_runner():
    required = {
        "mneme/guidance.py",
        "mneme/guidance_applicability_eval.py",
        "mneme/guidance_roles.py",
        "scripts/run_guidance_confirmatory_ab.py",
        "tests/fixtures/guidance_applicability/cases.json",
    }
    assert required.issubset(RUNNER.CANDIDATE_FILES)


def test_offline_enforcement_uses_post_run_canonical_policy_root(tmp_path):
    workspace = tmp_path / "model-visible-workspace"
    workspace.mkdir()
    external_memory = tmp_path / "secret-policy" / "random-memory.json"
    external_memory.parent.mkdir()
    external_memory.write_bytes(RUNNER.MEMORY_FIXTURE.read_bytes())
    pristine = {"docs/setup.md": "# Setup\n\nTODO\n"}
    proposed = {
        "docs/setup.md": "# Setup\n\nInstall with legacy-client.\n",
    }

    evidence = RUNNER._offline_enforcement(
        pristine, proposed, external_memory, workspace,
    )

    assert len(evidence) == 1
    payload = evidence[0]["payload"]
    assert payload["evaluation_complete"] is True
    assert payload["freshness"] == []
    assert payload["verdict"] == "FAIL"
    assert payload["violations"][0]["decision_id"] == "ADR-INSTALL"
    applicability = next(
        item for item in payload["applicability"]
        if item["decision_id"] == "ADR-INSTALL"
    )
    assert applicability["outcome"] == "APPLIED"
    assert applicability["input_path"] == "docs/setup.md"


def test_offline_enforcement_marks_nonmatching_typed_path_excluded(tmp_path):
    workspace = tmp_path / "model-visible-workspace"
    workspace.mkdir()
    external_memory = tmp_path / "secret-policy" / "random-memory.json"
    external_memory.parent.mkdir()
    external_memory.write_bytes(RUNNER.MEMORY_FIXTURE.read_bytes())
    pristine = {"src/sessions.py": "old\n"}
    proposed = {"src/sessions.py": "uses legacy-client text\n"}

    evidence = RUNNER._offline_enforcement(
        pristine, proposed, external_memory, workspace,
    )

    payload = evidence[0]["payload"]
    assert payload["evaluation_complete"] is True
    assert payload["freshness"] == []
    assert payload["verdict"] == "PASS"
    applicability = next(
        item for item in payload["applicability"]
        if item["decision_id"] == "ADR-INSTALL"
    )
    assert applicability["outcome"] == "EXCLUDED"
    assert applicability["input_path"] == "src/sessions.py"

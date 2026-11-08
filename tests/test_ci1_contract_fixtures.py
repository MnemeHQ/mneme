"""CI1.2.1: CI-platform-independent contract fixture for path-scoped enforcement.

Every case runs ``python -m mneme.cli check --json`` as a subprocess, which is
the boundary any CI adapter (GitHub Actions, GitLab CI, Jenkins, ...) crosses.
The fixture corpus, its case manifest and the golden payloads live in
``tests/fixtures/ci1_contract/path_scoped_forbid_literal/v1``; its README is the
contract. Nothing here changes enforcement semantics -- it pins them.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "ci1_contract" / "path_scoped_forbid_literal" / "v1"
SPEC = json.loads((FIXTURE / "cases.json").read_text(encoding="utf-8"))
CASES = SPEC["cases"]
SEED = {
    "meta": {"name": "ci1-fixture", "description": "CI1.2.1 path-scoped fixture"},
    "items": [], "examples": [], "decisions": [],
}


def _env() -> dict[str, str]:
    # Import the tree under test, not whichever mneme is installed.
    return {**os.environ, "PYTHONPATH": str(REPO_ROOT)}


def _cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "mneme.cli", *args],
        cwd=cwd, env=_env(), capture_output=True, text=True, encoding="utf-8",
    )


def _check(case: dict, query: str, top: int) -> tuple[int, dict]:
    args = [
        "check", "--memory", SPEC["memory"], "--input", case["input"],
        "--query", query, "--top", str(top), "--mode", case["mode"],
        "--adr-dir", SPEC["adr_dir"], "--json",
    ]
    if case["target_path"]:
        args += ["--target-path", case["target_path"]]
    proc = _cli(args, FIXTURE)
    # The payload must be the only thing on stdout, or adapters cannot parse it.
    return proc.returncode, json.loads(proc.stdout)


def _classify(exit_code: int, payload: dict | None) -> str:
    """Descriptive classification from CI1.1 A3 -- not a blocking policy."""
    if not payload or payload.get("schema") != SPEC["contract"]:
        return "UNEVALUATED"
    if payload.get("evaluation_complete") is not True:
        return "UNEVALUATED"
    if payload["verdict"] == "PASS" and exit_code == 0:
        return "VERIFIED_PASS"
    if payload["verdict"] == "FAIL":
        return "VIOLATION"
    return payload["verdict"]


def _expected(case: dict) -> dict:
    return json.loads((FIXTURE / case["expected"]).read_text(encoding="utf-8"))


# ── provenance: the memory comes from the supported pipeline ─────────────────

def test_fixture_memory_regenerates_from_source_adrs(tmp_path):
    """The canonical index (rule_id, decision_version_id) is produced by the
    supported CLI, not hand-written; any drift in that pipeline must surface
    here and be answered with a new fixture version."""
    shutil.copytree(FIXTURE / "adr", tmp_path / "adr")
    (tmp_path / "project_memory.json").write_text(json.dumps(SEED), encoding="utf-8")

    migrate = _cli(["decision-index", "migrate", "--memory", "project_memory.json", "--apply"], tmp_path)
    assert migrate.returncode == 0, migrate.stderr
    imported = _cli(["adr", "import", "--memory", "project_memory.json", "--apply", "adr"], tmp_path)
    assert imported.returncode == 0, imported.stderr

    regenerated = json.loads((tmp_path / "project_memory.json").read_text(encoding="utf-8"))
    committed = json.loads((FIXTURE / "project_memory.json").read_text(encoding="utf-8"))
    assert regenerated == committed


def test_fixture_declares_exactly_one_scoped_rule():
    index = json.loads((FIXTURE / "project_memory.json").read_text(encoding="utf-8"))["decision_index"]
    [rule] = index["rules"]
    assert {k: rule[k] for k in ("rule_id", "decision_id", "decision_version_id")} == SPEC["rule"]
    assert rule["rule_type"] == "FORBID_LITERAL"
    assert rule["applicability"] == {
        "include_paths": ["docs/**"], "exclude_paths": ["docs/history/**"],
    }


# ── each case reproduces its golden payload, exit code and classification ────

@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case_matches_golden_contract(case):
    variant = SPEC["query_variants"][0]
    code, payload = _check(case, variant["query"], variant["top"])
    assert payload == _expected(case)
    assert code == case["expected_exit"]
    assert _classify(code, payload) == case["expected_classification"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case_preserves_canonical_rule_identity(case):
    variant = SPEC["query_variants"][0]
    _code, payload = _check(case, variant["query"], variant["top"])
    records = payload["applicability"] + payload["violations"]
    assert records
    for record in records:
        assert record["rule_id"] == SPEC["rule"]["rule_id"]
        assert record["decision_version_id"] == SPEC["rule"]["decision_version_id"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_literal_enforcement_is_query_independent(case):
    """ADR-017: literal-tier results must not move with the retrieval query,
    even at --top 1 with a query that ranks the decoy decision first."""
    results = {
        (v["query"], v["top"]): _check(case, v["query"], v["top"])
        for v in SPEC["query_variants"]
    }
    expected = (case["expected_exit"], _expected(case))
    assert all(result == expected for result in results.values()), results


# ── the hazard the fixture exists to make explicit (CI1.1 F1) ───────────────

def test_unknown_applicability_is_unevaluated_despite_pass_verdict():
    """An UNKNOWN scoped rule reports verdict PASS with evaluation_complete
    false and exit 2 (the strict FAIL code). Neither `verdict` nor the exit
    code alone classifies it correctly; `evaluation_complete` must be read
    first. Pinned deliberately: changing it is a contract change (new fixture
    version), not a silent fix."""
    [case] = [c for c in CASES if c["id"] == "unknown_target_outside_policy_root"]
    variant = SPEC["query_variants"][0]
    code, payload = _check(case, variant["query"], variant["top"])
    assert payload["applicability"][0]["outcome"] == "UNKNOWN"
    assert payload["verdict"] == "PASS"
    assert payload["evaluation_complete"] is False
    assert code == 2
    assert _classify(code, payload) == "UNEVALUATED"

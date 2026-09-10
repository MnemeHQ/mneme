"""Anti-drift guards for the Mneme test policy.

Pins the battery definitions (``scripts/run_test_battery.py``) to the CI
wiring (``.github/workflows/tests.yml``) and to the contributor/release
documentation, so the documented commands and the commands CI actually runs
cannot silently diverge. Checks are structural (workflow YAML, manifest
subset) or targeted token checks — never large-text comparisons.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

from scripts.run_test_battery import (
    BATTERIES,
    GATE_EXCLUDED_PATH_PREFIXES,
    GATE_PATHS,
    PYTEST,
    validate_battery,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_GATE_PATHS: tuple[str, ...] = (
    "tests/test_decision_retriever.py",
    "tests/test_enforcer.py",
    "tests/test_enforcement_scope.py",
    "tests/test_anti_pattern_token_fp.py",
    "tests/test_path_selectors.py",
    "tests/test_adr_parser.py",
    "tests/test_adr_validator.py",
    "tests/test_adr_compile_integration.py",
    "tests/test_adr_lifecycle.py",
    "tests/test_cli.py",
    "tests/test_cli_audit.py",
    "tests/test_cli_setup.py",
    "tests/test_setup_state.py",
    "tests/test_setup_audit_parity.py",
    "tests/test_protection_activation.py",
    "tests/test_packaging_contract.py",
    "tests/test_benchmark.py",
    "tests/test_enforcement_quality_benchmark.py",
    "tests/integrations/claude_code",
    "tests/integrations/codex_cli",
    "tests/integrations/kiro",
    "tests/integrations/agent_sdk",
    "tests/integrations/antigravity",
)

BENCHMARK_COMMAND = (
    "mneme",
    "benchmark",
    "examples/benchmarks/",
    "--memory",
    "examples/project_memory.json",
)


def _load_workflow(name: str) -> dict:
    text = (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    return yaml.safe_load(text)


def _canonical_test_files() -> set[str]:
    return {
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "tests").rglob("test_*.py")
        if "__pycache__" not in path.parts
    }


def test_batteries_are_defined_with_expected_kinds():
    assert set(BATTERIES) == {"gate", "main", "release", "artifact-smoke", "benchmark"}
    assert BATTERIES["gate"].kind == "pytest"
    assert BATTERIES["main"].kind == "pytest"
    assert BATTERIES["release"].kind == "pytest"
    assert BATTERIES["artifact-smoke"].kind == "workflow"
    assert BATTERIES["benchmark"].kind == "command"


def test_targeted_is_deliberately_not_a_battery():
    assert "targeted" not in BATTERIES


def test_gate_manifest_is_subset_of_canonical_suite():
    canonical = _canonical_test_files()
    for rel in GATE_PATHS:
        path = Path(rel)
        if path.suffix == ".py":
            assert rel in canonical, f"gate manifest path is not a test file: {rel}"
        else:
            assert any(
                f.startswith(rel.rstrip("/") + "/") for f in canonical
            ), f"gate manifest directory contains no test files: {rel}"


def test_gate_manifest_covers_critical_architecture_paths():
    missing = [rel for rel in REQUIRED_GATE_PATHS if rel not in GATE_PATHS]
    assert not missing, f"gate manifest missing critical paths: {missing}"


def test_gate_manifest_excludes_experimental_and_repo_tooling_tests():
    for excluded in GATE_EXCLUDED_PATH_PREFIXES:
        assert (REPO_ROOT / excluded).exists(), f"excluded path no longer exists: {excluded}"
        assert excluded not in GATE_PATHS, f"excluded path is in the gate manifest: {excluded}"


def test_main_battery_is_the_bare_canonical_invocation():
    assert BATTERIES["main"].commands == (PYTEST,)
    assert BATTERIES["main"].commands[0][3:] == (), "main battery must select no paths"


def test_release_battery_covers_canonical_suite_plus_langchain():
    assert BATTERIES["release"].commands == (
        PYTEST,
        ("python", "-m", "pytest", "tests/integrations/langchain"),
    )


def test_benchmark_battery_is_the_documented_charter_command():
    assert BATTERIES["benchmark"].commands == (BENCHMARK_COMMAND,)


def test_gate_battery_manifest_matches_its_command():
    battery = validate_battery("gate")
    assert battery.commands == (PYTEST + GATE_PATHS,)


def test_tests_workflow_runs_gate_on_prs_and_full_suite_on_main():
    workflow = _load_workflow("tests.yml")
    jobs = workflow["jobs"]
    assert set(jobs) == {"gate", "main", "pytest-langchain", "release"}

    triggers = workflow[True]
    assert set(triggers) == {"pull_request", "push", "workflow_dispatch"}
    battery_input = triggers["workflow_dispatch"]["inputs"]["battery"]
    assert battery_input["options"] == ["gate", "main", "release"]

    assert "pull_request" in jobs["gate"]["if"]
    assert _battery_steps(jobs["gate"]) == ["python scripts/run_test_battery.py gate"]

    main_if = jobs["main"]["if"]
    assert "'push'" in main_if
    assert "pull_request" not in main_if
    assert "inputs.battery == 'main'" in main_if
    assert _battery_steps(jobs["main"]) == ["python scripts/run_test_battery.py main"]

    langchain_if = jobs["pytest-langchain"]["if"]
    assert "'push'" in langchain_if
    assert "pull_request" not in langchain_if
    assert "python -m pytest tests/integrations/langchain" in _step_runs(
        jobs["pytest-langchain"]
    )
    assert _battery_steps(jobs["pytest-langchain"]) == []

    release_if = jobs["release"]["if"]
    assert release_if == (
        "github.event_name == 'workflow_dispatch' && inputs.battery == 'release'"
    )
    assert _battery_steps(jobs["release"]) == ["python scripts/run_test_battery.py release"]


def test_release_workflow_publishes_without_running_tests():
    workflow = _load_workflow("release.yml")
    runs = [
        step.get("run", "")
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if isinstance(step, dict)
    ]
    assert runs, "release workflow has no run steps"
    assert not any("pytest" in run for run in runs), "release workflow must not run tests"


def test_contributing_documents_the_battery_commands():
    text = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    for command in (
        "python scripts/run_test_battery.py gate",
        "python scripts/run_test_battery.py main",
        "python scripts/run_test_battery.py release",
        " ".join(BENCHMARK_COMMAND),
    ):
        assert command in text, f"CONTRIBUTING.md does not document: {command}"


def test_releasing_documents_the_sha_policy_and_actual_publishing():
    text = (REPO_ROOT / "docs" / "releases" / "RELEASING.md").read_text(encoding="utf-8")
    for token in (
        "battery=release",
        "release-candidate SHA",
        "release-smoke.yml",
        "Publish to PyPI",
        "required again",
        "not required",
    ):
        assert token in text, f"RELEASING.md does not document: {token}"
    assert "there is no PyPI GitHub Actions workflow" not in text, (
        "RELEASING.md still claims publishing is not automated, contradicting release.yml"
    )


def test_run_test_battery_fails_closed_on_unknown_battery():
    result = subprocess.run(
        [sys.executable, "scripts/run_test_battery.py", "does-not-exist", "--dry-run"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 2
    assert "unknown battery" in result.stderr


def test_run_test_battery_dry_run_prints_the_gate_command():
    result = subprocess.run(
        [sys.executable, "scripts/run_test_battery.py", "gate", "--dry-run"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0
    assert result.stdout.startswith("python -m pytest tests/test_decision_retriever.py")


def _step_runs(job: dict) -> list[str]:
    return [
        step["run"]
        for step in job.get("steps", [])
        if isinstance(step, dict) and "run" in step
    ]


def _battery_steps(job: dict) -> list[str]:
    return [run for run in _step_runs(job) if "run_test_battery.py" in run]

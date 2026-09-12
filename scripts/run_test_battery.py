#!/usr/bin/env python3
"""Deterministic test batteries for the Mneme test policy.

Single source of truth for the battery definitions referenced by
CONTRIBUTING.md and docs/releases/RELEASING.md. CI (``.github/workflows/
tests.yml``) invokes this script so the commands a contributor runs locally
and the commands CI runs are identical.

Batteries:

===============  ==================================================  ===============================================
Battery          Purpose                                             Typical trigger
===============  ==================================================  ===============================================
``gate``         Critical regression protection                      pull_request
``main``         Broader confidence (complete canonical suite)       push/merge to ``main``
``release``      Complete source validation                          exact release-candidate SHA (once per SHA)
``artifact-smoke``  Validate published package bytes                 after PyPI publication
``benchmark``    Validate charter-sensitive behavioural semantics    only when retrieval/enforcement/benchmark change
===============  ==================================================  ===============================================

``targeted`` is deliberately NOT a defined battery: local development means
explicitly running the relevant test files or directories, for example::

    python -m pytest tests/test_decision_retriever.py -v

Invariants enforced here (and pinned by ``tests/test_test_policy.py``):

- ``gate`` is an explicit path manifest, strictly inside ``tests/`` and a
  subset of the canonical suite. New test files run on ``main``/``release``
  by default and enter ``gate`` only through a deliberate manifest change.
- Every canonical test module (``test_*.py`` under the testpaths) must be
  either in the ``gate`` manifest or in ``GATE_EXCLUSIONS`` with a concise
  reason; ``tests/test_test_policy.py`` fails on unclassified paths, so the
  manifest cannot silently age.
- ``main`` is the bare canonical pytest invocation (pyproject
  ``[tool.pytest.ini_options]`` ``testpaths = ["tests"]``); the script fails
  closed if that configuration drifts, because the bare invocation must
  remain the complete suite.
- The ``benchmark`` harness is a separate charter instrument. It is never
  folded into the gate/main/release pytest batteries.
- ``artifact-smoke`` validates the package PyPI actually serves, from a
  clean install; it never reruns the source test suite.

Usage::

    python scripts/run_test_battery.py <battery> [--dry-run]
"""
from __future__ import annotations

import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTEST = ("python", "-m", "pytest")
LANGCHAIN_SUITE = ("python", "-m", "pytest", "tests/integrations/langchain")
BENCHMARK_COMMAND = (
    "mneme",
    "benchmark",
    "examples/benchmarks/",
    "--memory",
    "examples/project_memory.json",
)

GATE_CORE_PATHS: tuple[str, ...] = (
    "tests/test_decision_retriever.py",
    "tests/test_enforcer.py",
    "tests/test_enforcement_scope.py",
    "tests/test_anti_pattern_token_fp.py",
    "tests/test_path_selectors.py",
    "tests/test_conflict_detector.py",
    "tests/test_context_builder_decisions.py",
    "tests/test_pipeline.py",
    "tests/test_drift_detection.py",
    "tests/test_schemas.py",
    "tests/test_memory_store_decisions.py",
    "tests/test_check_modes.py",
    "tests/test_check_json.py",
    "tests/test_smoke.py",
)

GATE_CLI_PATHS: tuple[str, ...] = (
    "tests/test_cli.py",
    "tests/test_cli_init.py",
    "tests/test_cli_setup.py",
    "tests/test_cli_missing_paths.py",
    "tests/test_cli_console_encoding.py",
    "tests/test_cli_check_freshness.py",
    "tests/test_cli_audit.py",
    "tests/test_cli_adr_import.py",
)

GATE_ADR_PATHS: tuple[str, ...] = (
    "tests/test_adr_parser.py",
    "tests/test_adr_validator.py",
    "tests/test_adr_constraints.py",
    "tests/test_adr_compile_integration.py",
    "tests/test_adr_lifecycle.py",
    "tests/test_adr_precedence.py",
    "tests/test_adr_freshness.py",
    "tests/test_adr_import.py",
    "tests/test_adr_import_e2e.py",
)

GATE_GOVERNANCE_PATHS: tuple[str, ...] = (
    "tests/test_setup_state.py",
    "tests/test_setup_audit_parity.py",
    "tests/test_protection_activation.py",
    "tests/test_packaging_contract.py",
    "tests/test_example_memory.py",
    "tests/test_test_policy.py",
)

GATE_BENCHMARK_UNIT_PATHS: tuple[str, ...] = (
    "tests/test_benchmark.py",
    "tests/test_benchmark_report.py",
    "tests/test_benchmark_schemas.py",
    "tests/test_benchmark_verifier.py",
    "tests/test_cli_benchmark.py",
    "tests/test_enforcement_quality_benchmark.py",
)

GATE_SHIPPED_PATHS: tuple[str, ...] = (
    "tests/test_cursor_generate.py",
    "tests/integrations/claude_code",
    "tests/integrations/codex_cli",
    "tests/integrations/kiro",
    "tests/integrations/agent_sdk",
    "tests/integrations/antigravity",
)

GATE_AUDIT_EVIDENCE_PATHS: tuple[str, ...] = (
    "tests/test_audit_tier_semantics.py",
    "tests/test_audit_test_evidence.py",
    "tests/test_ci_test_evidence.py",
    "tests/test_github_evidence.py",
)

GATE_PATHS: tuple[str, ...] = (
    GATE_CORE_PATHS
    + GATE_CLI_PATHS
    + GATE_ADR_PATHS
    + GATE_GOVERNANCE_PATHS
    + GATE_BENCHMARK_UNIT_PATHS
    + GATE_AUDIT_EVIDENCE_PATHS
    + GATE_SHIPPED_PATHS
)

GATE_EXCLUSIONS: tuple[tuple[str, str], ...] = (
    (
        "tests/test_check_install_command.py",
        "main-only: repo tooling (dedicated install-command-check.yml workflow)",
    ),
    ("tests/test_check_worktree_context.py", "main-only: repo tooling"),
    ("tests/test_pre_push_main_guard.py", "main-only: repo tooling"),
    ("tests/test_eventcatalog_import.py", "main-only: experimental integration"),
    ("tests/integrations/hermes", "main-only: experimental integration"),
    (
        "tests/integrations/langchain",
        "main-only: optional dependency (langchain extra; dedicated CI job on main)",
    ),
)


def gate_exclusion_reason(rel_path: str) -> str | None:
    """Return the exclusion reason for a canonical test path, if excluded."""
    for path, reason in GATE_EXCLUSIONS:
        if rel_path == path:
            return reason
        if not path.endswith(".py") and rel_path.startswith(path.rstrip("/") + "/"):
            return reason
    return None


def unclassified_canonical_test_paths() -> list[str]:
    """Canonical test modules accounted for by neither gate nor an exclusion.

    The anti-aging invariant: every test_*.py under the canonical testpaths is
    either in the gate manifest (directly or under a gate directory) or in
    GATE_EXCLUSIONS with a reason. Anything else is returned here so
    tests/test_test_policy.py can fail loudly until it is classified.
    """
    canonical = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "tests").rglob("test_*.py")
        if "__pycache__" not in path.parts
    )
    gate_dirs = [p.rstrip("/") + "/" for p in GATE_PATHS if not p.endswith(".py")]
    unclassified = []
    for rel in canonical:
        in_gate = rel in GATE_PATHS or any(rel.startswith(d) for d in gate_dirs)
        if in_gate or gate_exclusion_reason(rel) is not None:
            continue
        unclassified.append(rel)
    return unclassified


@dataclass(frozen=True)
class Battery:
    name: str
    kind: str
    purpose: str
    trigger: str
    commands: tuple[tuple[str, ...], ...] = ()
    note: str = ""


BATTERIES: dict[str, Battery] = {
    "gate": Battery(
        name="gate",
        kind="pytest",
        purpose=(
            "Critical regression protection for Mneme's charter-sensitive "
            "retrieval, enforcement, ADR, setup/protect, audit, packaging, "
            "benchmark-semantics, and shipped-integration paths."
        ),
        trigger="pull_request",
        commands=(PYTEST + GATE_PATHS,),
    ),
    "main": Battery(
        name="main",
        kind="pytest",
        purpose=(
            "Broader confidence: the complete canonical pytest suite "
            "(pyproject [tool.pytest.ini_options] testpaths), including tests "
            "not yet curated into gate."
        ),
        trigger="push or merge to main",
        commands=(PYTEST,),
    ),
    "release": Battery(
        name="release",
        kind="pytest",
        purpose=(
            "Complete source validation of the exact release-candidate SHA: "
            "the canonical suite plus the langchain-extra integration suite. "
            "One successful run is bound to the SHA and recorded as release "
            "evidence; it is not rerun for tag/publish alone."
        ),
        trigger="workflow_dispatch (battery=release) before tagging and publishing",
        commands=(PYTEST, LANGCHAIN_SUITE),
    ),
    "artifact-smoke": Battery(
        name="artifact-smoke",
        kind="workflow",
        purpose="Validate the package bytes that PyPI actually serves.",
        trigger="automatically after every successful Publish to PyPI run; also workflow_dispatch",
        commands=(),
        note=(
            "Owned by .github/workflows/release-smoke.yml: clean pipx install "
            "of the published version, CLI surface checks, and a disposable-repo "
            "setup check against the installed package. It never runs from the "
            "source checkout and never reruns the source test suite."
        ),
    ),
    "benchmark": Battery(
        name="benchmark",
        kind="command",
        purpose=(
            "Validate charter-sensitive retrieval and enforcement behavioural "
            "semantics (deterministic, canned-response benchmark instrument)."
        ),
        trigger=(
            "only when retrieval, enforcement, or benchmark semantics change "
            "(charter obligation; see docs/architecture/layer1-freeze-e73ff7d.md)"
        ),
        commands=(BENCHMARK_COMMAND,),
        note=(
            "A separate charter instrument: never part of the gate/main/release "
            "pytest batteries."
        ),
    ),
}


class BatteryError(Exception):
    """Raised when battery definitions or manifest paths are inconsistent."""


def _canonical_testpaths() -> list[str]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    try:
        return list(data["tool"]["pytest"]["ini_options"]["testpaths"])
    except (KeyError, TypeError) as exc:
        raise BatteryError(
            "pyproject.toml [tool.pytest.ini_options] testpaths not found"
        ) from exc


def validate_battery(name: str) -> Battery:
    battery = BATTERIES.get(name)
    if battery is None:
        raise BatteryError(f"unknown battery: {name!r}")
    if battery.kind == "pytest":
        testpaths = _canonical_testpaths()
        if testpaths != ["tests"]:
            raise BatteryError(
                "pyproject testpaths must remain exactly ['tests'] so the "
                f"'main' battery stays the complete canonical suite; found {testpaths}"
            )
        for cmd in battery.commands:
            for rel in cmd[len(PYTEST):]:
                path = REPO_ROOT / rel
                if not path.exists():
                    raise BatteryError(f"manifest path does not exist: {rel}")
                if Path(rel).parts[0] != "tests":
                    raise BatteryError(f"manifest path escapes tests/: {rel}")
    return battery


def _usage_text() -> str:
    lines = [
        "usage: python scripts/run_test_battery.py <battery> [--dry-run]",
        "",
    ]
    for name, battery in BATTERIES.items():
        lines.append(f"{name} ({battery.kind})")
        lines.append(f"    purpose:  {battery.purpose}")
        lines.append(f"    trigger:  {battery.trigger}")
        if battery.note:
            lines.append(f"    note:     {battery.note}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in args
    names = [a for a in args if not a.startswith("-")]
    if len(names) != 1:
        print(_usage_text(), file=sys.stderr)
        return 2
    try:
        battery = validate_battery(names[0])
    except BatteryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if battery.kind == "workflow":
        print(battery.purpose)
        print(battery.note)
        return 0
    for cmd in battery.commands:
        if dry_run:
            print(" ".join(cmd))
        else:
            result = subprocess.run(cmd, cwd=REPO_ROOT)
            if result.returncode != 0:
                return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())

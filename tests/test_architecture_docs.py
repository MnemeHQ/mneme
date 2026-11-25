"""Tests for deterministic architecture-documentation integrity checks."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.check_architecture_docs import (
    ARCHIVAL_LINK_CHECK_EXCLUSIONS,
    ARCHITECTURE_IMPACT_OPTIONS,
    REQUIRED_ARCHITECTURE_HEADINGS,
    validate_architecture_docs,
    validate_architecture_impact_declaration,
    validate_github_event_architecture_impact,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _adr(adr_id: str, status: str = "accepted") -> str:
    return (
        "---\n"
        f"id: {adr_id}\n"
        f'title: "{adr_id} fixture"\n'
        f"status: {status}\n"
        "priority: foundational\n"
        "date: 2026-01-01\n"
        "scope: fixture\n"
        "---\n\n"
        f"# {adr_id}: Fixture\n"
    )


def _architecture_index(
    *,
    displayed_status: str = "Accepted",
    target_text: str = "ADR-001 is accepted current architecture.",
) -> str:
    headings = "\n\n".join(
        heading + "\n\nFixture content."
        for heading in REQUIRED_ARCHITECTURE_HEADINGS
        if heading not in {
            "## Important current-versus-target boundary",
            "# ADR map",
        }
    )
    return (
        "# Mneme Architecture\n\n"
        "## Important current-versus-target boundary\n\n"
        f"{target_text}\n\n"
        f"{headings}\n\n"
        "# ADR map\n\n"
        "| ADR | Status | Architectural question it answers |\n"
        "| --- | --- | --- |\n"
        f"| [ADR-001](../adr/ADR-001-fixture.md) | {displayed_status} | Fixture. |\n"
    )




def _architecture_impact_body(
    selected: tuple[str, ...],
    *,
    adr_impact: str = "",
    architecture_map_impact: str = "",
    c4_impact: str = "",
    ascii_map_impact: str = "",
) -> str:
    lines = ["## Architecture impact", ""]
    for option in ARCHITECTURE_IMPACT_OPTIONS:
        mark = "x" if option in selected else " "
        lines.append(f"- [{mark}] {option}")
    lines.extend(
        [
            "",
            f"- ADR impact: {adr_impact}",
            f"- Architecture map impact: {architecture_map_impact}",
            f"- C4 impact: {c4_impact}",
            f"- ASCII map impact: {ascii_map_impact}",
            "",
            "## Validation",
            "",
            "Fixture.",
        ]
    )
    return "\n".join(lines)


def _fixture_repo(
    tmp_path: Path,
    *,
    adr_status: str = "accepted",
    displayed_status: str = "Accepted",
    target_text: str = "ADR-001 is accepted current architecture.",
) -> Path:
    _write(
        tmp_path / "docs" / "architecture" / "README.md",
        _architecture_index(
            displayed_status=displayed_status,
            target_text=target_text,
        ),
    )
    _write(
        tmp_path / "docs" / "architecture" / "documentation-governance.md",
        "# Governance\n",
    )
    _write(
        tmp_path / "docs" / "adr" / "ADR-001-fixture.md",
        _adr("ADR-001", adr_status),
    )
    return tmp_path


def test_repository_architecture_docs_are_consistent():
    assert validate_architecture_docs(REPO_ROOT) == []


def test_archival_freeze_artifact_is_explicitly_excluded_from_live_link_checks():
    assert ARCHIVAL_LINK_CHECK_EXCLUSIONS == (
        Path("docs/architecture/layer1-freeze-e73ff7d.md"),
    )
    for rel in ARCHIVAL_LINK_CHECK_EXCLUSIONS:
        assert (REPO_ROOT / rel).is_file()


def test_detects_broken_relative_link(tmp_path):
    repo = _fixture_repo(tmp_path)
    _write(
        repo / "docs" / "architecture" / "extra.md",
        "# Extra\n\n[missing](./does-not-exist.md)\n",
    )

    errors = validate_architecture_docs(repo)

    assert any("broken relative link" in error for error in errors)


def test_detects_adr_map_status_mismatch(tmp_path):
    repo = _fixture_repo(
        tmp_path,
        adr_status="accepted",
        displayed_status="Proposed",
    )

    errors = validate_architecture_docs(repo)

    assert any("ADR map status mismatch for ADR-001" in error for error in errors)


def test_detects_adr_map_label_identity_mismatch(tmp_path):
    repo = _fixture_repo(tmp_path)
    adr_path = repo / "docs" / "adr" / "ADR-001-fixture.md"
    _write(adr_path, _adr("ADR-999", "accepted"))

    errors = validate_architecture_docs(repo)

    assert any("ADR map label ADR-001 points to frontmatter id ADR-999" in error for error in errors)


def test_detects_duplicate_adr_identity(tmp_path):
    repo = _fixture_repo(tmp_path)
    _write(
        repo / "docs" / "adr" / "ADR-001-duplicate.md",
        _adr("ADR-001", "accepted"),
    )

    errors = validate_architecture_docs(repo)

    assert any("duplicate ADR id ADR-001" in error for error in errors)


def test_proposed_map_adr_requires_target_section_reference(tmp_path):
    repo = _fixture_repo(
        tmp_path,
        adr_status="proposed",
        displayed_status="Proposed",
        target_text="No target decision is documented here.",
    )

    errors = validate_architecture_docs(repo)

    assert any(
        "proposed ADR-001 in ADR map is not identified" in error
        for error in errors
    )


def test_proposed_map_adr_requires_explicit_target_marker(tmp_path):
    repo = _fixture_repo(
        tmp_path,
        adr_status="proposed",
        displayed_status="Proposed",
        target_text="ADR-001 appears in this section.",
    )

    errors = validate_architecture_docs(repo)

    assert any(
        "proposed ADR-001 lacks an explicit proposed/target/deferred marker" in error
        for error in errors
    )


def test_detects_missing_required_heading(tmp_path):
    repo = _fixture_repo(tmp_path)
    index = repo / "docs" / "architecture" / "README.md"
    text = index.read_text(encoding="utf-8").replace(
        "# C4 Level 3 — Core Components\n\nFixture content.\n\n",
        "",
    )
    _write(index, text)

    errors = validate_architecture_docs(repo)

    assert any(
        "missing required heading: # C4 Level 3 — Core Components" in error
        for error in errors
    )


def test_pr_architecture_impact_accepts_one_non_architecture_classification():
    body = _architecture_impact_body(("None",))

    assert validate_architecture_impact_declaration(body) == []


def test_pr_architecture_impact_requires_section():
    errors = validate_architecture_impact_declaration("## Summary\n\nFixture.\n")

    assert errors == [
        "pull request body: missing '## Architecture impact' section"
    ]


def test_pr_architecture_impact_requires_exactly_one_selection():
    none_selected = _architecture_impact_body(())
    multiple_selected = _architecture_impact_body(
        ("None", "Representation only")
    )

    assert validate_architecture_impact_declaration(none_selected) == [
        "pull request body: select exactly one architecture impact "
        "classification; selected: none"
    ]
    assert validate_architecture_impact_declaration(multiple_selected) == [
        "pull request body: select exactly one architecture impact "
        "classification; selected: None, Representation only"
    ]


def test_architecture_change_requires_all_four_impact_statements():
    body = _architecture_impact_body(
        ("Architecture change",),
        adr_impact="ADR-030 reviewed",
        architecture_map_impact="updated",
        c4_impact="",
        ascii_map_impact="n/a",
    )

    assert validate_architecture_impact_declaration(body) == [
        "pull request body: 'Architecture change' requires non-empty 'C4 impact'"
    ]


def test_target_architecture_accepts_explicit_non_empty_impact_statements():
    body = _architecture_impact_body(
        ("Target architecture",),
        adr_impact="proposed ADR added",
        architecture_map_impact="target view updated",
        c4_impact="n/a",
        ascii_map_impact="n/a",
    )

    assert validate_architecture_impact_declaration(body) == []


def test_github_pull_request_event_reads_body_and_push_skips(tmp_path):
    body = _architecture_impact_body(("Representation only",))
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({"pull_request": {"body": body}}),
        encoding="utf-8",
    )

    assert validate_github_event_architecture_impact(
        event_name="pull_request",
        event_path=event_path,
    ) == []
    assert validate_github_event_architecture_impact(
        event_name="push",
        event_path=event_path,
    ) == []

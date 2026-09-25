"""Tests for deterministic architecture-documentation integrity checks."""
from __future__ import annotations

from pathlib import Path

from scripts.check_architecture_docs import (
    REQUIRED_ARCHITECTURE_HEADINGS,
    validate_architecture_docs,
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

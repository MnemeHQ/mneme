"""Tests for the ADR corpus validator."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from mneme.adr_compiler import validate_corpus
from mneme.adr_schema import ADR, ADRValidationError


def _make(
    id: str = "ADR-001",
    title: str = "T",
    status: str = "accepted",
    priority: str = "normal",
    date: str = "2026-01-01",
    scope: str = "storage",
    supersedes: list[str] | None = None,
) -> ADR:
    return ADR(
        id=id,
        title=title,
        status=status,  # type: ignore[arg-type]
        priority=priority,  # type: ignore[arg-type]
        date=date,
        scope=scope,
        supersedes=list(supersedes or []),
        source_path=f"/tmp/{id}.md",
    )


def test_validate_corpus_accepts_a_valid_corpus():
    adrs = [_make(id="ADR-001"), _make(id="ADR-002", scope="storage.embeddings")]
    # No exception means valid.
    validate_corpus(adrs)


def test_validate_corpus_accepts_empty_scope_as_global():
    validate_corpus([_make(id="ADR-001", scope="")])


def test_missing_required_field_raises():
    adr = _make(id="ADR-001", title="")
    with pytest.raises(ADRValidationError, match="title"):
        validate_corpus([adr])


def test_id_format_must_match_adr_pattern():
    adr = _make(id="bogus")
    with pytest.raises(ADRValidationError, match="id"):
        validate_corpus([adr])


def test_duplicate_ids_raise():
    a = _make(id="ADR-001")
    b = _make(id="ADR-001", title="other")
    with pytest.raises(ADRValidationError, match="duplicate"):
        validate_corpus([a, b])


def test_invalid_status_enum_raises():
    adr = _make(id="ADR-001", status="approved")
    with pytest.raises(ADRValidationError, match="status"):
        validate_corpus([adr])


def test_invalid_priority_enum_raises():
    adr = _make(id="ADR-001", priority="critical")
    with pytest.raises(ADRValidationError, match="priority"):
        validate_corpus([adr])


def test_invalid_iso_date_raises():
    adr = _make(id="ADR-001", date="01/01/2026")
    with pytest.raises(ADRValidationError, match="date"):
        validate_corpus([adr])


@pytest.mark.parametrize(
    "scope",
    [
        ".storage",            # leading dot
        "storage.",            # trailing dot
        "storage..embeddings", # double dot
        "Storage",             # uppercase letters
        "storage backend",     # whitespace
    ],
)
def test_invalid_scope_format_raises(scope: str):
    adr = _make(id="ADR-001", scope=scope)
    with pytest.raises(ADRValidationError, match="scope"):
        validate_corpus([adr])


def test_supersedes_unknown_ref_raises():
    adr = _make(id="ADR-001", supersedes=["ADR-999"])
    with pytest.raises(ADRValidationError, match="supersedes"):
        validate_corpus([adr])


def test_circular_supersession_two_node_raises():
    a = _make(id="ADR-001", supersedes=["ADR-002"])
    b = _make(id="ADR-002", supersedes=["ADR-001"])
    with pytest.raises(ADRValidationError, match="circular"):
        validate_corpus([a, b])


def test_circular_supersession_three_node_raises():
    a = _make(id="ADR-001", supersedes=["ADR-002"])
    b = _make(id="ADR-002", supersedes=["ADR-003"])
    c = _make(id="ADR-003", supersedes=["ADR-001"])
    with pytest.raises(ADRValidationError, match="circular"):
        validate_corpus([a, b, c])


def test_self_supersession_raises():
    a = _make(id="ADR-001", supersedes=["ADR-001"])
    with pytest.raises(ADRValidationError, match="circular"):
        validate_corpus([a])


def test_validation_error_aggregates_multiple_problems():
    a = _make(id="bad-id")
    b = _make(id="ADR-002", status="approved")
    with pytest.raises(ADRValidationError) as excinfo:
        validate_corpus([a, b])
    # Both errors should be reported, not just the first.
    assert len(excinfo.value.errors) >= 2


# ── Canonical ADR file identity (frontmatter id uniqueness) ──────────────────
#
# Regression: PR #360 landed the Audit-tier ADR as a second ADR-023 after
# PR #359 had already assigned ADR-023 to the Canonical Decision Index.
# The Audit-tier ADR was renumbered to ADR-026; this scan fails if two
# canonical ADR documents ever declare the same frontmatter id again.

ADR_DOCS_DIR = Path(__file__).resolve().parent.parent / "docs" / "adr"
_FRONTMATTER_ID_RE = re.compile(r"^id:\s*(ADR-\d+)\s*$", re.MULTILINE)


def _scan_canonical_adr_ids(directory: Path) -> dict[str, list[str]]:
    """Map each frontmatter ``id:`` to the canonical ADR files declaring it."""
    found: dict[str, list[str]] = {}
    for path in sorted(directory.glob("ADR-*.md")):
        match = _FRONTMATTER_ID_RE.search(path.read_text(encoding="utf-8"))
        if match:
            found.setdefault(match.group(1), []).append(path.name)
    return found


def _find_duplicate_ids(directory: Path) -> dict[str, list[str]]:
    ids = _scan_canonical_adr_ids(directory)
    return {adr_id: files for adr_id, files in ids.items() if len(files) > 1}


def test_canonical_adr_files_have_unique_frontmatter_ids():
    duplicates = _find_duplicate_ids(ADR_DOCS_DIR)
    assert duplicates == {}, (
        f"ADR id collision: {duplicates}"
    )


def test_duplicate_frontmatter_id_is_detected(tmp_path: Path):
    (tmp_path / "ADR-001-alpha.md").write_text(
        "---\nid: ADR-001\ntitle: first\n---\n", encoding="utf-8"
    )
    (tmp_path / "ADR-001-beta.md").write_text(
        "---\nid: ADR-001\ntitle: second\n---\n", encoding="utf-8"
    )
    assert _find_duplicate_ids(tmp_path) == {
        "ADR-001": ["ADR-001-alpha.md", "ADR-001-beta.md"],
    }


def test_canonical_tree_has_exactly_one_adr_023_and_one_adr_026():
    ids = _scan_canonical_adr_ids(ADR_DOCS_DIR)
    assert ids.get("ADR-023") == [
        "ADR-023-canonical-decision-index-and-runtime-projection-boundary.md",
    ]
    assert ids.get("ADR-026") == [
        "ADR-026-audit-tier-semantics-and-mneme-potential.md",
    ]

"""Tests for the ADR corpus validator."""
from __future__ import annotations

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

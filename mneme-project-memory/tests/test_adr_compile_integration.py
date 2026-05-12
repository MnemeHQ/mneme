"""End-to-end integration tests for the ADR compile pipeline.

These tests exercise compile_adrs() against on-disk fixtures, covering
the full Parser -> Validator -> Precedence Engine path and the bridge
into the existing Decision schema used by the runtime pipeline.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mneme.adr_compiler import (
    adrs_to_decisions,
    compile_adrs,
)
from mneme.adr_schema import (
    ADRParseError,
    ADRPrecedenceError,
    ADRValidationError,
)
from mneme.schemas import Decision

FIXTURES = Path(__file__).parent / "fixtures"


def test_compile_adrs_returns_only_active_after_supersedes_and_status_filter():
    out = compile_adrs(FIXTURES / "adrs_e2e_clean")
    ids = [a.id for a in out]
    # ADR-013 is proposed -> excluded.
    # ADR-011 is superseded by ADR-012 -> excluded.
    # ADR-010 (storage, foundational) and ADR-012 (storage.embeddings) survive.
    assert ids == ["ADR-012", "ADR-010"]  # specificity desc, then priority desc


def test_compile_adrs_fails_fast_on_validation_error():
    with pytest.raises(ADRValidationError, match="status"):
        compile_adrs(FIXTURES / "adrs_e2e_invalid")


def test_compile_adrs_fails_fast_on_precedence_ambiguity():
    with pytest.raises(ADRPrecedenceError) as excinfo:
        compile_adrs(FIXTURES / "adrs_e2e_ambiguous")
    assert excinfo.value.scope == "api"
    assert sorted(excinfo.value.ids) == ["ADR-030", "ADR-031"]


def test_compile_adrs_fails_fast_on_parse_error():
    with pytest.raises(ADRParseError):
        compile_adrs(FIXTURES / "adrs_malformed")


# ── Bridge to existing Decision schema ───────────────────────────────────────


def test_adrs_to_decisions_maps_core_fields():
    adrs = compile_adrs(FIXTURES / "adrs_e2e_clean")
    decisions = adrs_to_decisions(adrs)
    assert all(isinstance(d, Decision) for d in decisions)
    by_id = {d.id: d for d in decisions}
    assert "ADR-010" in by_id
    storage = by_id["ADR-010"]
    assert storage.decision == "Use JSON file storage"
    assert storage.scope == ["storage"]
    assert storage.created_at == "2026-01-10"
    assert storage.updated_at == "2026-01-10"


def test_adrs_to_decisions_preserves_compile_order():
    adrs = compile_adrs(FIXTURES / "adrs_e2e_clean")
    decisions = adrs_to_decisions(adrs)
    assert [a.id for a in adrs] == [d.id for d in decisions]


def test_compiled_adrs_drive_existing_decision_retriever():
    """End-to-end sync flow: ADRs -> Decisions -> DecisionRetriever ranking.

    This proves the new compiler integrates with the runtime pipeline
    without changing DecisionRetriever or MemoryStore.
    """
    from mneme.decision_retriever import DecisionRetriever

    decisions = adrs_to_decisions(compile_adrs(FIXTURES / "adrs_e2e_clean"))
    retriever = DecisionRetriever(decisions)
    scored = retriever.retrieve("storage embeddings strategy")
    # Scoring must yield a positive result for at least one ADR-derived
    # decision (proves the dataclass round-trip is wired correctly).
    assert any(s.score > 0 for s in scored)


def test_global_scope_adr_maps_to_empty_string_scope_list():
    """Empty ADR.scope (global) should map to [""] for round-trip clarity."""
    from mneme.adr_schema import ADR

    adr = ADR(
        id="ADR-040",
        title="Global rule",
        status="accepted",
        priority="normal",
        date="2026-01-01",
        scope="",
    )
    [d] = adrs_to_decisions([adr])
    assert d.scope == [""]


def test_adrs_to_decisions_extracts_constraints_section():
    """`## Constraints` directives must populate Decision.constraints."""
    from mneme.adr_compiler import adrs_to_decisions, compile_adrs

    decisions = adrs_to_decisions(compile_adrs(FIXTURES / "adrs_import_basic"))
    by_id = {d.id: d for d in decisions}

    # ADR-101: FORBID_DEPENDENCY: mongodb -> "no mongodb" (enforcer-compatible)
    assert "no mongodb" in by_id["ADR-101"].constraints

    # ADR-102: FORBID_PATH and REQUIRE_PATH persist as opaque strings
    assert "FORBID_PATH src/legacy/billing/**" in by_id["ADR-102"].constraints
    assert "REQUIRE_PATH billing/**" in by_id["ADR-102"].constraints

    # ADR-103 is superseded -> excluded from the active set entirely
    assert "ADR-103" not in by_id


def test_adrs_to_decisions_no_constraints_section_yields_empty_constraints():
    """ADRs without a ## Constraints section retain empty Decision.constraints."""
    from mneme.adr_compiler import adrs_to_decisions, compile_adrs

    decisions = adrs_to_decisions(compile_adrs(FIXTURES / "adrs_e2e_clean"))
    for d in decisions:
        assert d.constraints == []

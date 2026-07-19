"""Tests for the ADR precedence engine."""
from __future__ import annotations

import pytest

from mneme.adr_compiler import resolve_precedence
from mneme.adr_schema import ADR, ADRPrecedenceError


def _make(
    id: str,
    scope: str = "storage",
    status: str = "accepted",
    priority: str = "normal",
    date: str = "2026-01-01",
    supersedes: list[str] | None = None,
) -> ADR:
    return ADR(
        id=id,
        title=f"title {id}",
        status=status,  # type: ignore[arg-type]
        priority=priority,  # type: ignore[arg-type]
        date=date,
        scope=scope,
        supersedes=list(supersedes or []),
        source_path=f"/tmp/{id}.md",
    )


# ── Status filtering ─────────────────────────────────────────────────────────


def test_proposed_adrs_excluded_from_active_set():
    a = _make("ADR-001", status="proposed")
    assert resolve_precedence([a]) == []


def test_deprecated_adrs_excluded_from_active_set():
    a = _make("ADR-001", status="deprecated")
    assert resolve_precedence([a]) == []


def test_status_superseded_excluded_from_active_set():
    a = _make("ADR-001", status="superseded")
    assert resolve_precedence([a]) == []


# ── Explicit supersession ────────────────────────────────────────────────────


def test_explicit_supersedes_removes_target():
    old = _make("ADR-001")
    new = _make("ADR-002", supersedes=["ADR-001"], date="2026-02-01")
    out = resolve_precedence([old, new])
    assert [a.id for a in out] == ["ADR-002"]


def test_explicit_supersedes_wins_over_priority():
    """Rule 1 (supersedes) outranks rule 3 (priority)."""
    foundational = _make("ADR-001", priority="foundational")
    normal_supersedes = _make(
        "ADR-002", priority="normal", supersedes=["ADR-001"], date="2026-02-01"
    )
    out = resolve_precedence([foundational, normal_supersedes])
    assert [a.id for a in out] == ["ADR-002"]


def test_chain_of_supersedes_only_keeps_terminal_record():
    a = _make("ADR-001")
    b = _make("ADR-002", supersedes=["ADR-001"])
    c = _make("ADR-003", supersedes=["ADR-002"])
    out = resolve_precedence([a, b, c])
    assert [r.id for r in out] == ["ADR-003"]


# ── Same scope: priority then date ───────────────────────────────────────────


def test_same_scope_higher_priority_wins():
    a = _make("ADR-001", priority="normal", date="2026-02-01")
    b = _make("ADR-002", priority="foundational", date="2026-01-01")
    out = resolve_precedence([a, b])
    assert [r.id for r in out] == ["ADR-002"]


def test_same_scope_exception_loses_to_normal():
    a = _make("ADR-001", priority="exception")
    b = _make("ADR-002", priority="normal")
    out = resolve_precedence([a, b])
    assert [r.id for r in out] == ["ADR-002"]


def test_same_scope_same_priority_newer_date_wins():
    older = _make("ADR-001", date="2026-01-01")
    newer = _make("ADR-002", date="2026-03-01")
    out = resolve_precedence([older, newer])
    assert [r.id for r in out] == ["ADR-002"]


def test_same_scope_same_priority_same_date_raises():
    a = _make("ADR-001", date="2026-01-01")
    b = _make("ADR-002", date="2026-01-01")
    with pytest.raises(ADRPrecedenceError) as excinfo:
        resolve_precedence([a, b])
    assert excinfo.value.scope == "storage"
    assert sorted(excinfo.value.ids) == ["ADR-001", "ADR-002"]


# ── Different scopes coexist ─────────────────────────────────────────────────


def test_different_scopes_both_active():
    a = _make("ADR-001", scope="storage")
    b = _make("ADR-002", scope="api")
    out = resolve_precedence([a, b])
    assert {r.id for r in out} == {"ADR-001", "ADR-002"}


def test_nested_scopes_coexist_no_conflict():
    """A broader-scope ADR and a narrower one don't conflict at compile time."""
    broad = _make("ADR-001", scope="backend")
    narrow = _make("ADR-002", scope="backend.storage")
    out = resolve_precedence([broad, narrow])
    assert {r.id for r in out} == {"ADR-001", "ADR-002"}


# ── Output ordering ──────────────────────────────────────────────────────────


def test_output_sorted_by_specificity_descending_then_priority():
    g = _make("ADR-001", scope="", priority="normal")
    backend = _make("ADR-002", scope="backend", priority="normal")
    storage = _make("ADR-003", scope="backend.storage", priority="normal")
    foundational_root = _make("ADR-004", scope="api", priority="foundational")
    out = resolve_precedence([g, backend, storage, foundational_root])
    # Most specific scopes first; within equal specificity foundational
    # outranks normal; ties broken by id for determinism.
    assert [r.id for r in out] == ["ADR-003", "ADR-004", "ADR-002", "ADR-001"]


# ── Empty / single-record edge cases ─────────────────────────────────────────


def test_empty_corpus_returns_empty_active_set():
    assert resolve_precedence([]) == []


def test_single_accepted_record_passes_through():
    a = _make("ADR-001")
    assert [r.id for r in resolve_precedence([a])] == ["ADR-001"]

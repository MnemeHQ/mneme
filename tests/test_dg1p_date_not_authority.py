"""DG1P: ADR date is not precedence authority (ADR-031 §2).

Before DG1P, a same-scope, same-priority tie was broken by the newer ADR
``date``. Date records when an ADR was written, not which decision governs,
so a tie is now an ambiguity unless explicit supersession or a different
priority resolves it. The change must never silently deactivate a decision
that is already canonical: a newly ambiguous scope fails closed with an
explicit report and is left untouched.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

from mneme.adr_compiler import (
    PRIORITY_RANK,
    resolve_precedence,
    resolve_precedence_partial,
)
from mneme.adr_import import apply_import, compile_for_import
from mneme.adr_parser import parse_adr_directory
from mneme.adr_schema import ADRPrecedenceError
from mneme.decision_index_persistence import load_decision_index_from_memory_file
from mneme.decision_mcp import load_canonical_index_from_adr_dir
from tests.canonical_fixtures import migrate_memory_fixture

REPO = Path(__file__).resolve().parent.parent


def _write_adr(
    adr_dir: Path,
    adr_id: str,
    scope: str,
    *,
    date: str,
    priority: str = "normal",
    supersedes: tuple[str, ...] = (),
    literal: str = "mongodb",
) -> None:
    supersedes_block = (
        "supersedes:\n" + "".join(f"  - {target}\n" for target in supersedes)
        if supersedes
        else ""
    )
    (adr_dir / f"{adr_id}.md").write_bytes((
        "---\n"
        f"id: {adr_id}\n"
        f"title: {adr_id} title\n"
        "status: accepted\n"
        f"priority: {priority}\n"
        f"date: {date}\n"
        f"scope: {json.dumps(scope)}\n"
        f"{supersedes_block}"
        "---\n\n"
        f"# {adr_id}\n\n"
        "## Constraints\n\n"
        f"- FORBID_LITERAL: {literal}\n"
    ).encode())


def _canonical_memory(tmp_path: Path) -> Path:
    target = tmp_path / "project_memory.json"
    target.write_bytes(json.dumps({
        "meta": {
            "name": "test", "description": "test", "version": "1.0.0",
            "owner": "test", "created": "2026-01-01",
        },
        "items": [], "examples": [], "decisions": [],
    }).encode("utf-8"))
    migrate_memory_fixture(target)
    return target


# ── compiler semantics ──────────────────────────────────────────────────────


def test_newer_date_never_wins_a_same_priority_tie(tmp_path: Path) -> None:
    _write_adr(tmp_path, "ADR-100", "payments", date="2026-01-01")
    _write_adr(tmp_path, "ADR-101", "payments", date="2026-09-01")
    with pytest.raises(ADRPrecedenceError) as excinfo:
        resolve_precedence(parse_adr_directory(tmp_path))
    assert excinfo.value.scope == "payments"
    assert sorted(excinfo.value.ids) == ["ADR-100", "ADR-101"]


def test_partial_resolution_skips_only_the_tied_scope(tmp_path: Path) -> None:
    _write_adr(tmp_path, "ADR-100", "payments", date="2026-01-01")
    _write_adr(tmp_path, "ADR-101", "payments", date="2026-09-01")
    _write_adr(tmp_path, "ADR-200", "storage", date="2026-01-01", literal="sqlite")
    winners, ambiguities = resolve_precedence_partial(parse_adr_directory(tmp_path))
    assert [a.id for a in winners] == ["ADR-200"]
    assert [(e.scope, sorted(e.ids)) for e in ambiguities] == [
        ("payments", ["ADR-100", "ADR-101"])
    ]


def test_explicit_supersession_resolves_a_tie_even_when_older(tmp_path: Path) -> None:
    # Authority comes from the explicit relation, not from recency.
    _write_adr(tmp_path, "ADR-100", "payments", date="2026-09-01")
    _write_adr(tmp_path, "ADR-101", "payments", date="2026-01-01", supersedes=("ADR-100",))
    assert [a.id for a in resolve_precedence(parse_adr_directory(tmp_path))] == ["ADR-101"]


def test_priority_resolves_regardless_of_date(tmp_path: Path) -> None:
    _write_adr(tmp_path, "ADR-100", "payments", date="2026-01-01", priority="foundational")
    _write_adr(tmp_path, "ADR-101", "payments", date="2026-09-01", priority="normal")
    assert [a.id for a in resolve_precedence(parse_adr_directory(tmp_path))] == ["ADR-100"]


def test_decision_mcp_adr_dir_refuses_a_date_only_tie(tmp_path: Path) -> None:
    _write_adr(tmp_path, "ADR-100", "payments", date="2026-01-01")
    _write_adr(tmp_path, "ADR-101", "payments", date="2026-09-01")
    with pytest.raises(ADRPrecedenceError):
        load_canonical_index_from_adr_dir(tmp_path)


def test_mneme_own_adr_corpus_never_relied_on_date() -> None:
    # Every exact-scope group of accepted, non-superseded ADRs has a unique
    # top priority, so removing the date step cannot change its active set.
    parsed = parse_adr_directory(REPO / "docs" / "adr")
    accepted = [a for a in parsed if a.status == "accepted"]
    superseded = {ref for a in accepted for ref in a.supersedes}
    groups: dict[str, list] = defaultdict(list)
    for adr in accepted:
        if adr.id not in superseded:
            groups[adr.scope].append(adr)
    for scope, group in groups.items():
        top = max(PRIORITY_RANK[a.priority] for a in group)
        assert sum(PRIORITY_RANK[a.priority] == top for a in group) == 1, scope
    assert len(resolve_precedence(parsed)) == len(groups)


# ── import: report and refuse, never silently deactivate ───────────────────


def test_import_reports_a_date_only_tie_without_suggesting_date(tmp_path: Path) -> None:
    adr_dir = tmp_path / "adrs"
    adr_dir.mkdir()
    _write_adr(adr_dir, "ADR-100", "payments", date="2026-01-01")
    _write_adr(adr_dir, "ADR-101", "payments", date="2026-09-01")
    report = compile_for_import(adr_dir)
    [diagnostic] = [d for d in report.diagnostics if d.kind == "active_active_contradiction"]
    assert "ADR-100" in diagnostic.adr_id and "ADR-101" in diagnostic.adr_id
    assert "change date" not in diagnostic.message
    assert "date never breaks a tie" in diagnostic.message
    assert report.skipped_scopes == {"payments": ["ADR-100", "ADR-101"]}


def test_reimport_never_deactivates_a_decision_that_already_governs(tmp_path: Path) -> None:
    adr_dir = tmp_path / "adrs"
    adr_dir.mkdir()
    target = _canonical_memory(tmp_path)

    # ADR-100 governs "payments" canonically.
    _write_adr(adr_dir, "ADR-100", "payments", date="2026-09-01")
    assert apply_import(compile_for_import(adr_dir), target_path=target) == ["ADR-100"]
    before_bytes = target.read_bytes()
    before = load_decision_index_from_memory_file(target)
    [governing] = [r for r in before.records if r.decision_id == "ADR-100"]
    assert governing.lifecycle_status == "active"

    # An older, same-priority ADR arrives in the same scope. Before DG1P the
    # newer ADR-100 won by date; now the scope is ambiguous.
    _write_adr(adr_dir, "ADR-101", "payments", date="2026-01-01", literal="couchdb")
    report = compile_for_import(adr_dir)
    assert report.skipped_scopes == {"payments": ["ADR-100", "ADR-101"]}

    with pytest.raises(RuntimeError, match="active-active contradiction"):
        apply_import(report, target_path=target, allow_update=True)
    assert target.read_bytes() == before_bytes

    # Even when the operator approves skipping conflicts, the ambiguous scope
    # is left exactly as it was: ADR-100 stays active, ADR-101 is not added.
    apply_import(report, target_path=target, allow_update=True, approve_conflicts=True)
    after = load_decision_index_from_memory_file(target)
    [still_governing] = [r for r in after.records if r.decision_id == "ADR-100"]
    assert still_governing == governing
    assert "ADR-101" not in {r.decision_id for r in after.records}

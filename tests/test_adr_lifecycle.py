"""
test_adr_lifecycle.py — Lifecycle analyzer tests.

Validates finding codes, deterministic ordering, tolerant parsing,
read-only semantics, the stale-retrievability regression, and per-scope isolation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mneme.adr_lifecycle import (
    analyze_lifecycle,
    DANGLING_SUPERSEDES,
    ORPHAN_SUPERSEDED,
    ACTIVE_CONTRADICTION,
    SILENT_PRECEDENCE_ELIMINATION,
    LEDGER_STATUS_MISMATCH,
)
from mneme.decision_retriever import DecisionRetriever
from mneme.schemas import Decision


def _write_adr(dir: Path, adr_id: str, status: str, scope: str, supersedes=None,
               title="Test", date="2026-01-01", priority="normal", constraints=None):
    supersedes = supersedes or []
    if supersedes:
        supersedes_yaml = "\n" + "".join(f"  - {s}\n" for s in supersedes)
    else:
        supersedes_yaml = " []"
    constraints_yaml = ""
    if constraints:
        constraints_yaml = "\n## Constraints\n" + "".join(f"- {c}\n" for c in constraints)
    # Quote empty scope to avoid YAML null
    scope_yaml = f'"{scope}"' if scope == "" else scope
    text = f"""---
id: {adr_id}
title: {title}
status: {status}
priority: {priority}
date: {date}
scope: {scope_yaml}
supersedes:{supersedes_yaml}
---

# {title}

Body text for {adr_id}.{constraints_yaml}
"""
    (dir / f"{adr_id}-test.md").write_text(text, encoding="utf-8", newline="\n")


def _write_ledger(dir: Path, entries: list[dict]) -> Path:
    """Write a minimal project_memory.json with given decisions."""
    mem = {
        "meta": {"name": "test", "description": "", "version": "0.1.0", "owner": "", "created": "2026-01-01"},
        "items": [],
        "examples": [],
        "decisions": entries,
    }
    p = dir / "project_memory.json"
    p.write_text(json.dumps(mem, indent=2) + "\n", encoding="utf-8", newline="\n")
    return p


def _hashes(dir: Path) -> dict[str, str]:
    """Return {relative_path: sha256} for all files in dir."""
    out = {}
    for p in dir.rglob("*"):
        if p.is_file():
            rel = p.relative_to(dir).as_posix()
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _make_3_5_stale_entry() -> dict:
    """Construct a ledger decision that scores exactly 3.5 for the regression query.

    Query tokens (len>=4, stopwords excluded):
      "embedding vector storage postgres" -> {"embedding", "vector", "storage", "postgres"}
    Target score 3.5 = rationale matches (3) * 0.5 + scope "storage" * 2.0
    """
    return {
        "id": "ADR-999",
        "decision": "Use SQLite for local persistence",
        "rationale": (
            "Local persistence uses SQLite via the stdlib sqlite3 module. "
            "Embedding vector stored in postgres database for now."
        ),
        "scope": ["storage"],
        "constraints": ["no postgres"],
        "anti_patterns": [],
        "rules": [{"type": "FORBID_LITERAL", "value": "postgres"}],
        "created_at": "2026-01-01",
        "updated_at": "2026-01-01",
    }


class TestLifecycleAnalyzer:
    def test_dangling_supersedes(self, tmp_path: Path):
        _write_adr(tmp_path, "ADR-001", "accepted", "", supersedes=["ADR-999"])
        _write_ledger(tmp_path, [])
        findings = analyze_lifecycle(tmp_path, tmp_path / "project_memory.json")
        assert any(f.code == DANGLING_SUPERSEDES and f.adr_id == "ADR-001" for f in findings)

    def test_orphan_superseded(self, tmp_path: Path):
        _write_adr(tmp_path, "ADR-001", "superseded", "")
        _write_ledger(tmp_path, [])
        findings = analyze_lifecycle(tmp_path, tmp_path / "project_memory.json")
        assert any(f.code == ORPHAN_SUPERSEDED and f.adr_id == "ADR-001" for f in findings)

    def test_active_contradiction(self, tmp_path: Path):
        _write_adr(tmp_path, "ADR-010", "accepted", "scope.x", date="2026-01-01",
                   constraints=["FORBID_LITERAL foo"])
        _write_adr(tmp_path, "ADR-011", "accepted", "scope.x", date="2026-01-01",
                   constraints=["FORBID_LITERAL bar"])
        _write_ledger(tmp_path, [])
        findings = analyze_lifecycle(tmp_path, tmp_path / "project_memory.json")
        assert any(f.code == ACTIVE_CONTRADICTION and "ADR-010" in f.adr_id and "ADR-011" in f.adr_id
                   for f in findings)

    def test_silent_precedence_elimination(self, tmp_path: Path):
        # ADR-001 and ADR-002 both accepted in scope 'ci' without supersedes link.
        # ADR-001 is newer (2026-02-01 vs 2026-01-01), so precedence selects ADR-001.
        # ADR-002 is silently eliminated solely by precedence.
        _write_adr(tmp_path, "ADR-001", "accepted", "ci", priority="normal", date="2026-02-01")
        _write_adr(tmp_path, "ADR-002", "accepted", "ci", priority="normal", date="2026-01-01")
        _write_ledger(tmp_path, [])
        findings = analyze_lifecycle(tmp_path, tmp_path / "project_memory.json")
        assert any(f.code == SILENT_PRECEDENCE_ELIMINATION and f.adr_id == "ADR-002"
                   for f in findings)

    def test_ledger_status_mismatch_stale_retrievable(self, tmp_path: Path):
        # Corpus: ADR-004 deprecated on disk
        _write_adr(tmp_path, "ADR-004", "deprecated", "storage")
        # Ledger: decision ADR-004 still present with source pointing at the file
        entry = _make_3_5_stale_entry()
        entry["id"] = "ADR-004"
        entry["source"] = {"type": "adr", "path": "ADR-004-test.md", "sha256": "deadbeef"}
        _write_ledger(tmp_path, [entry])
        findings = analyze_lifecycle(tmp_path, tmp_path / "project_memory.json")
        assert any(f.code == LEDGER_STATUS_MISMATCH and f.adr_id == "ADR-004"
                   for f in findings)

    def test_deterministic_ordering(self, tmp_path: Path):
        # Create multiple finding types in one run
        _write_adr(tmp_path, "ADR-001", "accepted", "", supersedes=["ADR-999"])
        _write_adr(tmp_path, "ADR-002", "superseded", "")
        _write_adr(tmp_path, "ADR-010", "accepted", "scope.x", date="2026-01-01")
        _write_adr(tmp_path, "ADR-011", "accepted", "scope.x", date="2026-01-01")
        _write_adr(tmp_path, "ADR-003", "accepted", "ci", priority="foundational")
        _write_adr(tmp_path, "ADR-004", "accepted", "ci", priority="normal")
        _write_adr(tmp_path, "ADR-005", "deprecated", "storage")
        entry = _make_3_5_stale_entry()
        entry["id"] = "ADR-005"
        entry["source"] = {"type": "adr", "path": "ADR-005-test.md", "sha256": "deadbeef"}
        _write_ledger(tmp_path, [entry])
        findings1 = analyze_lifecycle(tmp_path, tmp_path / "project_memory.json")
        findings2 = analyze_lifecycle(tmp_path, tmp_path / "project_memory.json")
        # Exact same output twice
        assert [(f.code, f.adr_id) for f in findings1] == [(f.code, f.adr_id) for f in findings2]
        # Order respects _CODE_ORDER
        codes = [f.code for f in findings1]
        assert codes == sorted(codes, key=lambda c: [
            DANGLING_SUPERSEDES, ORPHAN_SUPERSEDED,
            ACTIVE_CONTRADICTION, SILENT_PRECEDENCE_ELIMINATION, LEDGER_STATUS_MISMATCH
        ].index(c) if c in [
            DANGLING_SUPERSEDES, ORPHAN_SUPERSEDED,
            ACTIVE_CONTRADICTION, SILENT_PRECEDENCE_ELIMINATION, LEDGER_STATUS_MISMATCH
        ] else 99)

    def test_tolerant_parse_error(self, tmp_path: Path):
        # Write one valid ADR and one malformed ADR
        _write_adr(tmp_path, "ADR-001", "accepted", "")
        (tmp_path / "ADR-002-test.md").write_text("not yaml frontmatter", encoding="utf-8")
        _write_ledger(tmp_path, [])
        findings = analyze_lifecycle(tmp_path, tmp_path / "project_memory.json")
        # Should still process the valid file and report parse error for the bad one
        assert any(f.code == "ADR_UNPARSEABLE" and "ADR-002" in f.adr_id for f in findings)

    def test_read_only_no_mutations(self, tmp_path: Path):
        _write_adr(tmp_path, "ADR-001", "accepted", "")
        _write_adr(tmp_path, "ADR-002", "deprecated", "")
        ledger = _write_ledger(tmp_path, [])
        corpus_hashes = _hashes(tmp_path)
        _ = analyze_lifecycle(tmp_path, ledger)
        # Hashes unchanged
        assert _hashes(tmp_path) == corpus_hashes

    def test_regression_stale_decision_flagged_and_score_unchanged(self, tmp_path: Path):
        """
        Reproduce the M0 3.5-scoring stale decision and prove the analyzer flags it.

        The ledger entry ADR-999 is designed to score 3.5 for the query
        "embedding vector storage postgres" (rationale matches 3 tokens @0.5
        + scope 'storage' @2.0). The corpus ADR is deprecated.
        """
        _write_adr(tmp_path, "ADR-004", "deprecated", "storage")
        entry = _make_3_5_stale_entry()
        entry["id"] = "ADR-004"
        entry["source"] = {"type": "adr", "path": "ADR-004-test.md", "sha256": "deadbeef"}
        ledger = _write_ledger(tmp_path, [entry])

        # Analyzer runs
        findings = analyze_lifecycle(tmp_path, ledger)
        flagged = any(f.code == LEDGER_STATUS_MISMATCH and f.adr_id == "ADR-004"
                      for f in findings)
        assert flagged, "Analyzer should flag the stale ledger entry"

        # Retrieval score unchanged (regression guard)
        raw = json.loads(ledger.read_text(encoding="utf-8"))
        decisions = [
            Decision(id=d["id"], decision=d["decision"], scope=d.get("scope", []),
                     constraints=d.get("constraints", []),
                     anti_patterns=d.get("anti_patterns", []),
                     created_at=d.get("created_at", ""), updated_at=d.get("updated_at", ""))
            for d in raw["decisions"]
        ]
        scored = DecisionRetriever(decisions).retrieve("embedding vector storage postgres")
        target = next(s for s in scored if s.decision.id == "ADR-004")
        # Exact score match from M0 evidence
        assert target.score == pytest.approx(3.5)
        # And the entry is still retrievable (no enforcement change)
        assert target.decision.id == "ADR-004"

    def test_tied_adr_superseding_other_scope_does_not_resurrect_superseded_adr(self, tmp_path: Path):
        """
        Regression: when a tied ADR supersedes an ADR in another scope, the superseded
        ADR must not re-enter consideration or cause false elimination findings.

        Setup:
          Scope 'compute':
            ADR-002: accepted, normal, 2026-01-01, supersedes: [ADR-001]
            ADR-003: accepted, normal, 2026-01-01 (ties with ADR-002)
          Scope 'storage':
            ADR-001: accepted, normal, 2026-01-01 (superseded by ADR-002)
            ADR-004: accepted, normal, 2026-01-01

        Expected findings:
          ACTIVE_CONTRADICTION for ADR-002,ADR-003 in scope 'compute'.
          NO SILENT_PRECEDENCE_ELIMINATION in scope 'storage' (ADR-001 is superseded,
          so ADR-004 is the sole active decision in 'storage').
        """
        _write_adr(tmp_path, "ADR-001", "accepted", "storage", date="2026-01-01")
        _write_adr(tmp_path, "ADR-002", "accepted", "compute", date="2026-01-01", supersedes=["ADR-001"])
        _write_adr(tmp_path, "ADR-003", "accepted", "compute", date="2026-01-01")
        _write_adr(tmp_path, "ADR-004", "accepted", "storage", date="2026-01-01")
        _write_ledger(tmp_path, [])

        findings = analyze_lifecycle(tmp_path, tmp_path / "project_memory.json")
        contradictions = [f for f in findings if f.code == ACTIVE_CONTRADICTION]
        eliminations = [f for f in findings if f.code == SILENT_PRECEDENCE_ELIMINATION]

        assert len(contradictions) == 1
        assert "ADR-002" in contradictions[0].adr_id and "ADR-003" in contradictions[0].adr_id
        # ADR-001 must not re-enter to falsely eliminate ADR-004 or be reported as eliminated
        assert eliminations == [], f"Unexpected eliminations: {eliminations}"


class TestFullFixture:
    """Run a multi-ADR fixture against the analyzer for smoke coverage."""
    def test_full_fixture(self, tmp_path: Path):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        ledger_dir = tmp_path / "ledger"
        ledger_dir.mkdir()

        adrs = [
            ("ADR-001", "accepted", "", [], "foundational"),
            ("ADR-002", "accepted", "ci", [], "normal"),
            ("ADR-003", "accepted", "ci", [], "foundational"),
            ("ADR-004", "deprecated", "storage", [], "normal"),
            ("ADR-005", "accepted", "retrieval", [], "normal"),
            ("ADR-006", "accepted", "retrieval", ["ADR-005"], "normal"),
            ("ADR-007", "superseded", "obs", [], "normal"),
            ("ADR-008", "accepted", "scope.x", [], "normal"),
            ("ADR-009", "accepted", "scope.x", [], "normal"),
            ("ADR-010", "accepted", "", ["ADR-999"], "normal"),
        ]
        for adr_id, status, scope, supersedes, prio in adrs:
            _write_adr(corpus, adr_id, status, scope, supersedes, priority=prio)

        # Ledger entries for actives + stale ADR-004
        ledger_entries = []
        for adr_id, status, scope, supersedes, prio in adrs:
            if status == "accepted" and adr_id not in {"ADR-008", "ADR-009"}:
                entry = {
                    "id": adr_id,
                    "decision": "Test decision",
                    "rationale": "Rationale text with embedding vector storage postgres",
                    "scope": [scope],
                    "constraints": [],
                    "anti_patterns": [],
                    "rules": [],
                    "created_at": "2026-01-01",
                    "updated_at": "2026-01-01",
                    "source": {"type": "adr", "path": f"../corpus/{adr_id}-test.md", "sha256": "x"},
                }
                ledger_entries.append(entry)
        # Stale deprecated
        entry = _make_3_5_stale_entry()
        entry["id"] = "ADR-004"
        entry["source"] = {"type": "adr", "path": "../corpus/ADR-004-test.md", "sha256": "x"}
        ledger_entries.append(entry)

        _write_ledger(ledger_dir, ledger_entries)

        findings = analyze_lifecycle(corpus, ledger_dir / "project_memory.json")
        codes = {f.code for f in findings}
        expected = {DANGLING_SUPERSEDES, ORPHAN_SUPERSEDED,
                    ACTIVE_CONTRADICTION, SILENT_PRECEDENCE_ELIMINATION,
                    LEDGER_STATUS_MISMATCH}
        assert expected.issubset(codes), f"missing: {expected - codes}"


class TestNegativeCases:
    """Negative tests: cases that MUST NOT produce warnings."""

    def test_intentional_tombstones_produce_no_warning(self, tmp_path: Path):
        """A deprecated/superseded ADR file on disk (tombstone) without a stale ledger entry."""
        _write_adr(tmp_path, "ADR-001", "accepted", "storage")
        _write_adr(tmp_path, "ADR-002", "deprecated", "storage")
        _write_ledger(tmp_path, [{
            "id": "ADR-001",
            "decision": "Current decision",
            "scope": ["storage"],
            "constraints": [],
            "anti_patterns": [],
            "rules": [],
            "source": {"type": "adr", "path": "ADR-001-test.md", "sha256": "abc"},
        }])
        findings = analyze_lifecycle(tmp_path, tmp_path / "project_memory.json")
        assert not findings, f"Expected no warnings, got: {[(f.code, f.adr_id) for f in findings]}"

    def test_ordinary_numbering_gaps_produce_no_warning(self, tmp_path: Path):
        """ADR-001 and ADR-003 exist, ADR-002 was never created. No warning."""
        _write_adr(tmp_path, "ADR-001", "accepted", "storage")
        _write_adr(tmp_path, "ADR-003", "accepted", "compute")
        _write_ledger(tmp_path, [])
        findings = analyze_lifecycle(tmp_path, tmp_path / "project_memory.json")
        assert not findings, f"Expected no warnings, got: {[(f.code, f.adr_id) for f in findings]}"

    def test_explicit_supersession_produces_no_silent_elimination_warning(self, tmp_path: Path):
        """Two accepted ADRs in same scope, but ADR-002 explicitly supersedes ADR-001."""
        _write_adr(tmp_path, "ADR-001", "accepted", "storage", supersedes=[])
        _write_adr(tmp_path, "ADR-002", "accepted", "storage", supersedes=["ADR-001"])
        _write_ledger(tmp_path, [])
        findings = analyze_lifecycle(tmp_path, tmp_path / "project_memory.json")
        assert not any(f.code == SILENT_PRECEDENCE_ELIMINATION for f in findings)

    def test_valid_precedence_non_conflicting_produces_no_warning(self, tmp_path: Path):
        """Decisions in different or hierarchical scopes produce no elimination warning."""
        _write_adr(tmp_path, "ADR-001", "accepted", "storage")
        _write_adr(tmp_path, "ADR-002", "accepted", "storage.embeddings")
        _write_adr(tmp_path, "ADR-003", "accepted", "compute")
        _write_ledger(tmp_path, [])
        findings = analyze_lifecycle(tmp_path, tmp_path / "project_memory.json")
        assert not any(f.code == SILENT_PRECEDENCE_ELIMINATION for f in findings)

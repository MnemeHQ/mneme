"""DG1C: effective-decision resolution over v1 semantics (ADR-031 §1, §3, §11).

The resolver introduces no new governance semantics. Its acceptance gate is
parity: for every well-formed canonical state, the effective set equals the
Layer 1 load-time projection, decision for decision and rule for rule.
Beyond parity it must explain ineffective decisions honestly, never guess
an unrecorded cause, report contradictory supersession as an explicit
ambiguity, and be invariant to input order, unrelated decisions, and the
governance context (no context-dependent semantics exist yet).
"""
from __future__ import annotations

import copy
import json
import random
from dataclasses import replace
from pathlib import Path

import pytest

from mneme.decision_governance import (
    CAUSE_AMBIGUOUS,
    CAUSE_LIFECYCLE_DEPRECATED,
    CAUSE_LIFECYCLE_INACTIVE,
    CAUSE_LIFECYCLE_SUPERSEDED,
    FINDING_DANGLING_SUPERSEDES,
    FINDING_SUPERSESSION_LIFECYCLE_CONFLICT,
    GOVERNANCE_SEMANTICS_VERSION,
    GovernanceContext,
    resolve_effective,
    resolve_effective_from_memory_file,
)
from mneme.decision_index import (
    CanonicalArchitectureIndex,
    CanonicalDecisionRecord,
    CanonicalRuleRecord,
)
from mneme.decision_index_persistence import load_decision_index_from_memory_file
from mneme.decision_mcp import load_canonical_index_from_adr_dir
from mneme.decision_projection import project_canonical_index
from tests.canonical_fixtures import canonical_document

REPO = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"

ADR_CORPORA = (
    REPO / "docs" / "adr",
    FIXTURES / "adrs_e2e_clean",
    FIXTURES / "adrs_import_basic",
    FIXTURES / "adrs_literal",
    FIXTURES / "adrs_valid",
)
CANONICAL_MEMORY_FILES = (REPO / ".mneme" / "project_memory.json",)
PRE_D1_MEMORY_FILES = (
    FIXTURES / "d1_parity" / "pre_d1_live_project_memory.json",
    FIXTURES / "memory_v2.json",
)


# ── helpers ──────────────────────────────────────────────────────────────


def _record(
    decision_id: str,
    lifecycle: str = "active",
    supersedes: tuple[str, ...] = (),
    rule_ids: tuple[str, ...] = (),
) -> CanonicalDecisionRecord:
    return CanonicalDecisionRecord(
        decision_id=decision_id,
        version_id=f"dver-{decision_id}",
        statement=f"statement {decision_id}",
        lifecycle_status=lifecycle,
        relationships=tuple(("supersedes", target) for target in supersedes),
        derived_rule_ids=rule_ids,
    )


def _rule(decision_id: str, rule_id: str, lifecycle: str = "active") -> CanonicalRuleRecord:
    return CanonicalRuleRecord(
        rule_id=rule_id,
        decision_id=decision_id,
        decision_version="1",
        decision_version_id=f"dver-{decision_id}",
        rule_type="FORBID_LITERAL",
        rule_payload={"value": f"literal-{rule_id}"},
        lifecycle_status=lifecycle,
    )


def _index(*records: CanonicalDecisionRecord, rules=()) -> CanonicalArchitectureIndex:
    return CanonicalArchitectureIndex(records=tuple(records), rules=tuple(rules))


def _assert_parity(index: CanonicalArchitectureIndex) -> None:
    projected = project_canonical_index(index)
    resolution = resolve_effective(index)
    assert not resolution.findings
    assert not resolution.ambiguities
    assert resolution.effective_ids == tuple(sorted(d.id for d in projected))
    by_id = {r.decision_id: r for r in index.records}
    for decision in resolution.effective:
        record = by_id[decision.decision_id]
        assert decision.decision_version_id == record.version_id
        assert decision.rule_ids == tuple(
            rule.rule_id for rule in index.rules_for_decision(record.decision_id)
        )
        assert decision.rule_ids == record.derived_rule_ids
    projected_rule_counts = {d.id: len(d.rules) for d in projected}
    assert {
        d.decision_id: len(d.rule_ids) for d in resolution.effective
    } == projected_rule_counts


# ── acceptance gate: parity with Layer 1 projection ───────────────────────


@pytest.mark.parametrize("corpus", ADR_CORPORA, ids=lambda p: p.name)
def test_parity_with_projection_for_adr_corpora(corpus: Path) -> None:
    _assert_parity(load_canonical_index_from_adr_dir(corpus))


@pytest.mark.parametrize("path", CANONICAL_MEMORY_FILES, ids=lambda p: p.name)
def test_parity_with_projection_for_canonical_memory(path: Path) -> None:
    _assert_parity(load_decision_index_from_memory_file(path))


@pytest.mark.parametrize("path", PRE_D1_MEMORY_FILES, ids=lambda p: p.name)
def test_parity_with_projection_for_migrated_memory(path: Path, tmp_path: Path) -> None:
    document = canonical_document(json.loads(path.read_text(encoding="utf-8")))
    migrated = tmp_path / "project_memory.json"
    migrated.write_bytes(json.dumps(document).encode("utf-8"))
    _assert_parity(load_decision_index_from_memory_file(migrated))
    from_file = resolve_effective_from_memory_file(migrated)
    assert from_file == resolve_effective(load_decision_index_from_memory_file(migrated))


def test_repo_corpus_resolves_the_superseded_adrs_with_explicit_supersessors() -> None:
    resolution = resolve_effective(load_canonical_index_from_adr_dir(REPO / "docs" / "adr"))
    superseded = {
        d.decision_id: d for d in resolution.ineffective
        if d.cause == CAUSE_LIFECYCLE_SUPERSEDED
    }
    assert superseded
    assert superseded["ADR-003"].superseded_by == ("ADR-016",)
    assert "ADR-031" in resolution.effective_ids


# ── explanation: causes come from recorded state only ─────────────────────


def test_ineffective_causes_follow_lifecycle_and_never_guess() -> None:
    index = _index(
        _record("A"),
        _record("B", "superseded"),
        _record("C", "deprecated"),
        _record("D", "inactive"),
        _record("E", supersedes=("B",)),
    )
    resolution = resolve_effective(index)
    assert resolution.effective_ids == ("A", "E")
    causes = {d.decision_id: d.cause for d in resolution.ineffective}
    assert causes == {
        "B": CAUSE_LIFECYCLE_SUPERSEDED,
        "C": CAUSE_LIFECYCLE_DEPRECATED,
        "D": CAUSE_LIFECYCLE_INACTIVE,
    }
    by_id = {d.decision_id: d for d in resolution.decisions}
    assert by_id["B"].superseded_by == ("E",)
    assert by_id["C"].superseded_by == ()
    assert all(d.cause is None for d in resolution.effective)
    # Over v1 data the reason an inactive decision is inactive is unrecorded.
    inactive_trace = {s.step: s.outcome for s in by_id["D"].trace}
    assert inactive_trace["precedence"] == "not_recorded"


def test_superseded_by_status_alone_needs_no_relationship() -> None:
    resolution = resolve_effective(_index(_record("A", "superseded")))
    (decision,) = resolution.decisions
    assert decision.cause == CAUSE_LIFECYCLE_SUPERSEDED
    assert decision.superseded_by == ()
    assert not resolution.findings


def test_ineffective_decisions_still_report_their_rule_lineage() -> None:
    index = _index(
        _record("A", rule_ids=("A:R1",)),
        _record("B", "superseded", rule_ids=("B:R1", "B:R2")),
        rules=(_rule("A", "A:R1"), _rule("B", "B:R1", "superseded"), _rule("B", "B:R2", "superseded")),
    )
    by_id = {d.decision_id: d for d in resolve_effective(index).decisions}
    assert by_id["A"].rule_ids == ("A:R1",)
    assert by_id["B"].rule_ids == ("B:R1", "B:R2")


def test_rule_lineage_mismatch_fails_closed() -> None:
    index = _index(_record("A", rule_ids=("A:R1",)), rules=(_rule("A", "A:R2"),))
    with pytest.raises(ValueError, match="lineage"):
        resolve_effective(index)


# ── ambiguity and integrity: never select a winner silently ───────────────


def test_active_target_of_in_force_supersession_is_ambiguous() -> None:
    index = _index(_record("A"), _record("B", supersedes=("A",)))
    resolution = resolve_effective(index)
    assert resolution.effective_ids == ("B",)
    (ambiguous,) = resolution.ambiguities
    assert ambiguous.decision_id == "A"
    assert ambiguous.cause == CAUSE_AMBIGUOUS
    assert ambiguous.superseded_by == ("B",)
    assert [(f.code, f.decision_id) for f in resolution.findings] == [
        (FINDING_SUPERSESSION_LIFECYCLE_CONFLICT, "A")
    ]


def test_supersession_declared_by_a_non_effective_decision_is_not_in_force() -> None:
    # An ADR that is only proposed (inactive) may declare supersedes; that
    # relationship has no authority until the declaring decision governs.
    index = _index(_record("A"), _record("B", "inactive", supersedes=("A",)))
    resolution = resolve_effective(index)
    assert resolution.effective_ids == ("A",)
    assert not resolution.ambiguities
    assert not resolution.findings


def test_dangling_supersedes_is_reported_without_changing_the_effective_set() -> None:
    index = _index(_record("A", supersedes=("GHOST",)), _record("B"))
    resolution = resolve_effective(index)
    assert resolution.effective_ids == ("A", "B")
    assert [(f.code, f.decision_id) for f in resolution.findings] == [
        (FINDING_DANGLING_SUPERSEDES, "GHOST")
    ]


def test_duplicate_decision_ids_fail_closed() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        resolve_effective(_index(_record("A"), _record("A", "superseded")))


def test_unknown_lifecycle_fails_closed() -> None:
    with pytest.raises(ValueError, match="lifecycle"):
        resolve_effective(_index(_record("A", "waived")))


# ── invariance ────────────────────────────────────────────────────────────


def _realistic_index() -> CanonicalArchitectureIndex:
    return load_canonical_index_from_adr_dir(REPO / "docs" / "adr")


def test_input_order_invariance() -> None:
    index = _realistic_index()
    baseline = resolve_effective(index)
    rng = random.Random(31)
    for _ in range(5):
        records = list(index.records)
        rules = list(index.rules)
        rng.shuffle(records)
        rng.shuffle(rules)
        assert resolve_effective(
            CanonicalArchitectureIndex(records=tuple(records), rules=tuple(rules))
        ) == baseline


def test_irrelevant_decision_invariance() -> None:
    index = _realistic_index()
    baseline = {d.decision_id: d for d in resolve_effective(index).decisions}
    extended = CanonicalArchitectureIndex(
        records=index.records + (_record("UNRELATED-1"), _record("UNRELATED-2", "deprecated")),
        rules=index.rules,
    )
    after = {d.decision_id: d for d in resolve_effective(extended).decisions}
    assert set(after) == set(baseline) | {"UNRELATED-1", "UNRELATED-2"}
    for decision_id, decision in baseline.items():
        assert after[decision_id] == decision


def test_context_invariance_for_v1_semantics() -> None:
    index = _realistic_index()
    baseline = resolve_effective(index).decisions
    for context in (
        GovernanceContext(paths=("src/payments/adapter.py",)),
        GovernanceContext(paths=("a.py", "b/c.py"), labels=("payments",)),
        GovernanceContext(as_of="2030-01-01T00:00:00Z"),
    ):
        resolution = resolve_effective(index, context)
        assert resolution.decisions == baseline
        assert resolution.context == context


def test_resolution_is_versioned_and_deterministic() -> None:
    index = _realistic_index()
    first = resolve_effective(index)
    second = resolve_effective(copy.deepcopy(index))
    assert first == second
    assert first.semantics_version == GOVERNANCE_SEMANTICS_VERSION
    assert [d.decision_id for d in first.decisions] == sorted(
        d.decision_id for d in first.decisions
    )


# ── GovernanceContext ─────────────────────────────────────────────────────


def test_context_normalizes_order_and_duplicates() -> None:
    assert GovernanceContext(paths=("b.py", "a.py", "b.py")) == GovernanceContext(
        paths=("a.py", "b.py")
    )
    assert GovernanceContext(labels=("y", "x")).labels == ("x", "y")


@pytest.mark.parametrize(
    "bad",
    ["", "/abs/path.py", "C:/abs/path.py", "back\\slash.py", "../escape.py", "a/../b.py"],
)
def test_context_rejects_non_relative_paths(bad: str) -> None:
    with pytest.raises(ValueError):
        GovernanceContext(paths=(bad,))


def test_context_rejects_non_string_values() -> None:
    with pytest.raises(ValueError):
        GovernanceContext(paths=(1,))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        GovernanceContext(as_of="")


def test_resolver_is_pure_over_frozen_records() -> None:
    index = _index(_record("A"), _record("B", "superseded"))
    before = replace(index)
    resolve_effective(index)
    assert index == before

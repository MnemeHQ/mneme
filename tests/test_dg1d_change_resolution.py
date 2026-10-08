"""DG1D: governance change between two supplied snapshots (ADR-031 §9).

The change set is derived only by comparing two DG1C ``resolve_effective``
results computed under one context: no second policy engine, no history
reconstruction, and "affected" limited to mechanically known decision,
version and rule ids.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from mneme.decision_add import add_canonical_decision
from mneme.decision_governance import (
    CAUSE_LIFECYCLE_DEPRECATED,
    CAUSE_LIFECYCLE_SUPERSEDED,
    CHANGE_BECAME_EFFECTIVE,
    CHANGE_BECAME_INEFFECTIVE,
    CHANGE_CAUSE,
    CHANGE_DECISION_ADDED,
    CHANGE_DECISION_REMOVED,
    CHANGE_LIFECYCLE,
    CHANGE_RULE_SET,
    CHANGE_SEMANTICS_VERSION,
    CHANGE_SUPERSEDED_BY,
    CHANGE_VERSION,
    FINDING_DANGLING_SUPERSEDES,
    GovernanceContext,
    compare_resolutions,
    resolve_change,
    resolve_change_from_memory_files,
    resolve_effective,
)
from mneme.decision_index import CanonicalArchitectureIndex
from mneme.decision_index_persistence import DecisionIndexMigrationRequired
from mneme.decision_mcp import load_canonical_index_from_adr_dir
from tests.canonical_fixtures import canonical_document
from tests.test_dg1c_effective_resolver import _index, _record, _rule

REPO = Path(__file__).resolve().parent.parent
LIVE_PRE_D1 = Path(__file__).parent / "fixtures" / "d1_parity" / "pre_d1_live_project_memory.json"


def _kinds(change_set) -> dict[str, tuple[str, ...]]:
    return {change.decision_id: change.kinds for change in change_set.changes}


# ── core change semantics ───────────────────────────────────────────────────


def test_identical_snapshots_produce_no_change() -> None:
    index = load_canonical_index_from_adr_dir(REPO / "docs" / "adr")
    change_set = resolve_change(index, index)
    assert change_set.changes == ()
    assert not change_set.changed
    assert change_set.activated_rule_ids == change_set.retired_rule_ids == ()
    assert change_set.semantics_version == CHANGE_SEMANTICS_VERSION


def test_supersession_moves_governance_and_rules() -> None:
    before = _index(
        _record("A", rule_ids=("A:R1",)),
        rules=(_rule("A", "A:R1"),),
    )
    after = _index(
        _record("A", "superseded", rule_ids=("A:R1",)),
        _record("B", supersedes=("A",), rule_ids=("B:R1",)),
        rules=(_rule("A", "A:R1", "superseded"), _rule("B", "B:R1")),
    )
    change_set = resolve_change(before, after)
    assert _kinds(change_set) == {
        "A": (
            CHANGE_BECAME_INEFFECTIVE,
            CHANGE_LIFECYCLE,
            CHANGE_CAUSE,
            CHANGE_SUPERSEDED_BY,
        ),
        "B": (CHANGE_DECISION_ADDED, CHANGE_BECAME_EFFECTIVE),
    }
    by_id = {c.decision_id: c for c in change_set.changes}
    assert by_id["A"].after.cause == CAUSE_LIFECYCLE_SUPERSEDED
    assert by_id["A"].after.superseded_by == ("B",)
    assert by_id["B"].before is None
    assert change_set.activated_rule_ids == ("B:R1",)
    assert change_set.retired_rule_ids == ("A:R1",)
    assert change_set.affected_decision_ids == ("A", "B")


def test_version_evolution_reports_version_and_rule_changes() -> None:
    def snapshot(version: str, rule_id: str) -> CanonicalArchitectureIndex:
        record = _record("A", rule_ids=(rule_id,))
        rule = _rule("A", rule_id)
        record = type(record)(**{**record.__dict__, "version_id": version})
        rule = type(rule)(**{**rule.__dict__, "decision_version_id": version})
        return CanonicalArchitectureIndex(records=(record,), rules=(rule,))

    change_set = resolve_change(snapshot("dver-1", "A:R1"), snapshot("dver-2", "A:R2"))
    [change] = change_set.changes
    assert change.kinds == (CHANGE_VERSION, CHANGE_RULE_SET)
    assert change.rules_added == ("A:R2",)
    assert change.rules_removed == ("A:R1",)
    assert change_set.activated_rule_ids == ("A:R2",)
    assert change_set.retired_rule_ids == ("A:R1",)


def test_removed_effective_decision_becomes_ineffective() -> None:
    before = _index(_record("A", rule_ids=("A:R1",)), _record("B"), rules=(_rule("A", "A:R1"),))
    after = _index(_record("B"))
    change_set = resolve_change(before, after)
    assert _kinds(change_set) == {"A": (CHANGE_DECISION_REMOVED, CHANGE_BECAME_INEFFECTIVE)}
    assert change_set.retired_rule_ids == ("A:R1",)


def test_added_ineffective_decision_only_reports_addition() -> None:
    change_set = resolve_change(_index(_record("A")), _index(_record("A"), _record("B", "deprecated")))
    assert _kinds(change_set) == {"B": (CHANGE_DECISION_ADDED,)}
    assert change_set.activated_rule_ids == ()


def test_rules_of_ineffective_decisions_are_never_activated() -> None:
    before = _index(_record("A", "deprecated", rule_ids=("A:R1",)), rules=(_rule("A", "A:R1", "deprecated"),))
    after = _index(
        _record("A", "deprecated", rule_ids=("A:R2",)),
        rules=(_rule("A", "A:R2", "deprecated"),),
    )
    change_set = resolve_change(before, after)
    assert _kinds(change_set) == {"A": (CHANGE_RULE_SET,)}
    assert change_set.activated_rule_ids == change_set.retired_rule_ids == ()


def test_findings_are_reported_as_introduced_and_resolved() -> None:
    clean = _index(_record("A"))
    dangling = _index(_record("A", supersedes=("GHOST",)))
    introduced = resolve_change(clean, dangling)
    assert introduced.changes == ()
    assert introduced.changed
    assert [(f.code, f.decision_id) for f in introduced.findings_introduced] == [
        (FINDING_DANGLING_SUPERSEDES, "GHOST")
    ]
    resolved = resolve_change(dangling, clean)
    assert [(f.code, f.decision_id) for f in resolved.findings_resolved] == [
        (FINDING_DANGLING_SUPERSEDES, "GHOST")
    ]


# ── one semantic implementation ─────────────────────────────────────────────


def test_change_is_derived_from_two_resolver_results() -> None:
    before = _index(_record("A"), _record("B", "deprecated"))
    after = _index(_record("A", "deprecated"), _record("B"))
    context = GovernanceContext(paths=("src/a.py",))
    assert resolve_change(before, after, context) == compare_resolutions(
        resolve_effective(before, context), resolve_effective(after, context)
    )
    assert resolve_change(before, after, context).context == context


def test_resolutions_from_different_contexts_are_not_comparable() -> None:
    index = _index(_record("A"))
    with pytest.raises(ValueError, match="different contexts"):
        compare_resolutions(
            resolve_effective(index, GovernanceContext(paths=("a.py",))),
            resolve_effective(index, GovernanceContext(paths=("b.py",))),
        )


def test_resolutions_from_different_semantics_are_not_comparable() -> None:
    index = _index(_record("A"))
    first = resolve_effective(index)
    other = type(first)(**{**first.__dict__, "semantics_version": "other/1"})
    with pytest.raises(ValueError, match="different governance semantics"):
        compare_resolutions(first, other)


def test_change_set_is_input_order_invariant() -> None:
    before = load_canonical_index_from_adr_dir(REPO / "docs" / "adr")
    after = CanonicalArchitectureIndex(
        records=before.records + (_record("NEW-1"),),
        rules=before.rules,
    )
    baseline = resolve_change(before, after)
    rng = random.Random(9)
    for _ in range(3):
        records = list(after.records)
        rules = list(after.rules)
        rng.shuffle(records)
        rng.shuffle(rules)
        shuffled = CanonicalArchitectureIndex(records=tuple(records), rules=tuple(rules))
        assert resolve_change(before, shuffled) == baseline
    assert _kinds(baseline) == {"NEW-1": (CHANGE_DECISION_ADDED, CHANGE_BECAME_EFFECTIVE)}


# ── persisted snapshots (e.g. two git revisions of project memory) ──────────


def _write(path: Path, document: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(document).encode("utf-8"))
    return path


def _live_document() -> dict:
    return canonical_document(json.loads(LIVE_PRE_D1.read_text(encoding="utf-8")))


def test_persisted_snapshots_report_a_real_writer_addition(tmp_path: Path) -> None:
    document = _live_document()
    before = _write(tmp_path / "before" / "project_memory.json", document)
    after = _write(tmp_path / "after" / "project_memory.json", document)
    data = after.read_bytes()
    assert add_canonical_decision(
        after,
        json.loads(data),
        data,
        decision_id="dg1d-new-001",
        statement="Use the outbox pattern for payment events",
        rationale="Exactly-once delivery",
        scope=["payments"],
        constraints=[],
        anti_patterns=[],
        now="2026-10-08T00:00:00Z",
    )
    change_set = resolve_change_from_memory_files(before, after)
    assert _kinds(change_set) == {
        "dg1d-new-001": (CHANGE_DECISION_ADDED, CHANGE_BECAME_EFFECTIVE)
    }
    [change] = change_set.changes
    assert change.after.decision_version_id.startswith("dver-")


def test_persisted_snapshots_report_deprecation_and_retired_rules(tmp_path: Path) -> None:
    document = _live_document()
    before = _write(tmp_path / "before" / "project_memory.json", document)
    rows = document["decision_index"]["decisions"]
    [target] = [row for row in rows if row["decision_id"] == "ADR-005"]
    target["lifecycle_status"] = "deprecated"
    # The compatibility snapshot must keep verifying: a deprecated decision
    # leaves the projection, so drop it from decisions[] as a writer would.
    document["decisions"] = [d for d in document["decisions"] if d["id"] != "ADR-005"]
    after = _write(tmp_path / "after" / "project_memory.json", document)

    change_set = resolve_change_from_memory_files(before, after)
    assert _kinds(change_set) == {
        "ADR-005": (CHANGE_BECAME_INEFFECTIVE, CHANGE_LIFECYCLE, CHANGE_CAUSE)
    }
    [change] = change_set.changes
    assert change.after.cause == CAUSE_LIFECYCLE_DEPRECATED
    assert change_set.retired_rule_ids == change.before.rule_ids != ()
    assert change_set.activated_rule_ids == ()


def test_section_less_snapshots_are_refused(tmp_path: Path) -> None:
    section_less = tmp_path / "project_memory.json"
    section_less.write_bytes(LIVE_PRE_D1.read_bytes())
    with pytest.raises(DecisionIndexMigrationRequired):
        resolve_change_from_memory_files(section_less, section_less)

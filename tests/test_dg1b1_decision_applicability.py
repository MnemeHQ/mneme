"""DG1B1: deterministic decision applicability (ADR-031 §4, §6-§8; charter #473).

Decision applicability is the first persisted DG1 semantic. It is optional
exact project-local ``required_labels`` on a canonical decision, resolved by
deterministic set containment against ``GovernanceContext.labels``:

- absent applicability -> globally eligible (every v1 decision is unchanged);
- lifecycle-inactive    -> the lifecycle cause wins (never ``not_applicable``);
- all required labels present -> effective;
- otherwise             -> ineffective with cause ``not_applicable``.

It persists only under ``mneme.decision-index/v2``. This file pins the
charter's required implementation validation (charter §7) and the closed
schema rules.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from mneme.decision_governance import (
    CAUSE_LIFECYCLE_DEPRECATED,
    CAUSE_LIFECYCLE_SUPERSEDED,
    CAUSE_NOT_APPLICABLE,
    CHANGE_GOVERNED_SCOPE,
    GovernanceContext,
    resolve_change,
    resolve_effective,
    resolve_effective_from_memory_file,
)
from mneme.decision_index_persistence import (
    APPLICABILITY_FEATURE,
    DECISION_INDEX_SCHEMA,
    DECISION_INDEX_SCHEMA_V2,
    DecisionIndexMigrationRequired,
    DecisionIndexPersistenceError,
    apply_memory_migration,
    load_decision_index_from_memory_file,
    load_persisted_decision_index,
    plan_memory_migration,
    set_decision_applicability,
    upgrade_decision_index_v1_to_v2,
)
from mneme.decision_projection import project_canonical_index
from tests.canonical_fixtures import canonical_document, v1_document

WINDOWS_LABELS = ("platform:windows",)


# ── fixtures ──────────────────────────────────────────────────────────────


def _decision(
    decision_id: str,
    status: str = "active",
    anti_patterns=None,
    rules=None,
) -> dict:
    return {
        "id": decision_id,
        "decision": f"{decision_id} governs its area",
        "rationale": "",
        "scope": ["general"],
        "constraints": [],
        "anti_patterns": list(anti_patterns or []),
        "rules": list(rules or []),
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "status": status,
    }


def _forbid(value: str) -> dict:
    return {"type": "FORBID_LITERAL", "value": value}


def _section_less(*decisions: dict) -> dict:
    return {
        "meta": {"name": "dg1b1", "description": "test"},
        "items": [],
        "examples": [],
        "decisions": list(decisions),
    }


def _v2(*decisions: dict) -> dict:
    return canonical_document(_section_less(*decisions))


def _write(path: Path, document: dict) -> Path:
    path.write_bytes(json.dumps(document, indent=2).encode("utf-8") + b"\n")
    return path


def _index(document: dict):
    return load_persisted_decision_index(document["decision_index"])


def _causes(index, labels=()) -> dict:
    resolution = resolve_effective(index, GovernanceContext(labels=labels))
    return {d.decision_id: d.cause for d in resolution.decisions}


def _effective_ids(index, labels=()) -> tuple[str, ...]:
    return resolve_effective(index, GovernanceContext(labels=labels)).effective_ids


# ── 1. explicit v1 -> v2 migration; compatibility default ─────────────────


def test_migrated_section_less_memory_is_v2_with_no_applicability() -> None:
    document = _v2(_decision("A"), _decision("B"))
    section = document["decision_index"]
    assert section["schema"] == DECISION_INDEX_SCHEMA_V2
    assert section["semantic_features"] == []
    assert _effective_ids(_index(document)) == ("A", "B")
    assert _causes(_index(document)) == {"A": None, "B": None}


def test_explicit_v1_to_v2_upgrade_is_lossless_and_globally_eligible(
    tmp_path: Path,
) -> None:
    v1 = v1_document(_v2(_decision("A"), _decision("B")))
    path = _write(tmp_path / "project_memory.json", v1)

    # A plain migrate must NOT upgrade valid v1 memory implicitly.
    assert plan_memory_migration(path).state == "already_canonical"

    plan = plan_memory_migration(path, to_v2=True)
    assert plan.state == "upgrade_to_v2"
    assert apply_memory_migration(plan) is True

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["decision_index"]["schema"] == DECISION_INDEX_SCHEMA_V2
    assert raw["decision_index"]["semantic_features"] == []
    assert raw["decision_index"]["decisions"] == v1["decision_index"]["decisions"]
    assert raw["decision_index"]["versions"] == v1["decision_index"]["versions"]
    assert _effective_ids(
        load_decision_index_from_memory_file(path)
    ) == ("A", "B")

    # Applying again is a byte-identical no-op.
    before = path.read_bytes()
    assert apply_memory_migration(plan_memory_migration(path, to_v2=True)) is False
    assert path.read_bytes() == before


def test_upgrade_refuses_to_promote_a_v1_applicability_v1_ignored(
    tmp_path: Path,
) -> None:
    # v1 silently ignores unknown keys, so a v1 row carrying applicability is
    # globally eligible. Upgrading must refuse rather than silently activate it.
    v1 = v1_document(_v2(_decision("A")))
    v1["decision_index"]["decisions"][0]["applicability"] = {
        "required_labels": list(WINDOWS_LABELS)
    }
    path = _write(tmp_path / "project_memory.json", v1)
    from mneme.decision_index_persistence import DecisionIndexMigrationRefused

    with pytest.raises(DecisionIndexMigrationRefused, match="without losing state"):
        plan_memory_migration(path, to_v2=True)


def test_upgrade_refuses_unknown_v1_keys() -> None:
    v1 = v1_document(_v2(_decision("A")))
    v1["decision_index"]["waivers"] = [{"id": "W-1"}]
    from mneme.decision_index_persistence import DecisionIndexMigrationRefused

    with pytest.raises(DecisionIndexMigrationRefused):
        upgrade_decision_index_v1_to_v2(v1)


# ── 2. v1/0.10.x refusal of v2 ────────────────────────────────────────────


def test_v1_and_v2_schemas_are_distinguishable_at_load() -> None:
    # The 0.10.x loader gates on exact schema equality, so a v2 document (a
    # different schema tag) is refused rather than misresolved. The current
    # loader accepts v2 and an unknown future schema is still rejected.
    assert DECISION_INDEX_SCHEMA == "mneme.decision-index/v1"
    assert DECISION_INDEX_SCHEMA_V2 == "mneme.decision-index/v2"
    v2 = _v2(_decision("A"))
    assert v2["decision_index"]["schema"] != DECISION_INDEX_SCHEMA

    v2["decision_index"]["schema"] = "mneme.decision-index/v3"
    with pytest.raises(DecisionIndexPersistenceError, match="schema must be"):
        load_persisted_decision_index(v2["decision_index"])


def test_v1_row_applicability_is_ignored_and_globally_eligible() -> None:
    v1 = v1_document(_v2(_decision("A")))
    v1["decision_index"]["decisions"][0]["applicability"] = {
        "required_labels": list(WINDOWS_LABELS)
    }
    index = load_persisted_decision_index(v1["decision_index"])
    assert index.records[0].applicability_required_labels == ()
    assert _effective_ids(index) == ("A",)


# ── 3. closed schema: unknown keys and unsupported features ────────────────


def test_v2_rejects_unknown_root_key() -> None:
    document = _v2(_decision("A"))
    document["decision_index"]["waivers"] = []
    with pytest.raises(DecisionIndexPersistenceError, match="unsupported fields"):
        load_persisted_decision_index(document["decision_index"])


def test_v2_rejects_unknown_decision_row_key() -> None:
    document = _v2(_decision("A"))
    document["decision_index"]["decisions"][0]["governs"] = {"paths": []}
    with pytest.raises(DecisionIndexPersistenceError, match="unsupported fields"):
        load_persisted_decision_index(document["decision_index"])


def test_v2_rejects_unknown_version_and_rule_row_keys() -> None:
    document = _v2(_decision("A"))
    document["decision_index"]["versions"][0]["priority"] = "high"
    with pytest.raises(DecisionIndexPersistenceError, match="unsupported fields"):
        load_persisted_decision_index(document["decision_index"])

    document = _v2(_decision("A", rules=[_forbid("legacy-thing")]))
    assert document["decision_index"]["rules"]
    document["decision_index"]["rules"][0]["dg1_probe"] = 1
    with pytest.raises(DecisionIndexPersistenceError, match="unsupported fields"):
        load_persisted_decision_index(document["decision_index"])


def test_v2_rejects_unsupported_semantic_feature() -> None:
    document = _v2(_decision("A"))
    document["decision_index"]["semantic_features"] = ["time_travel"]
    with pytest.raises(DecisionIndexPersistenceError, match="unsupported semantic_features"):
        load_persisted_decision_index(document["decision_index"])


def test_v2_requires_semantic_features_declaration() -> None:
    document = _v2(_decision("A"))
    del document["decision_index"]["semantic_features"]
    with pytest.raises(DecisionIndexPersistenceError, match="semantic_features is required"):
        load_persisted_decision_index(document["decision_index"])


def test_v2_applicability_without_feature_declaration_is_rejected() -> None:
    document = _v2(_decision("A"))
    document["decision_index"]["decisions"][0]["applicability"] = {
        "required_labels": list(WINDOWS_LABELS)
    }
    with pytest.raises(DecisionIndexPersistenceError, match="semantic feature"):
        load_persisted_decision_index(document["decision_index"])


def test_v2_rejects_unknown_applicability_key() -> None:
    document, _ = set_decision_applicability(
        _v2(_decision("A")), decision_id="A", required_labels=WINDOWS_LABELS
    )
    document["decision_index"]["decisions"][0]["applicability"]["paths"] = ["src/**"]
    with pytest.raises(DecisionIndexPersistenceError, match="unsupported fields"):
        load_persisted_decision_index(document["decision_index"])


def test_v2_rejects_empty_required_labels() -> None:
    document = _v2(_decision("A"))
    document["decision_index"]["decisions"][0]["applicability"] = {
        "required_labels": []
    }
    with pytest.raises(DecisionIndexPersistenceError, match="must be non-empty"):
        load_persisted_decision_index(document["decision_index"])


# ── 4-6. deterministic resolution ─────────────────────────────────────────


def test_applicability_absent_matches_dg1c_projection() -> None:
    document = _v2(_decision("A"), _decision("B"))
    index = _index(document)
    assert resolve_effective(index).effective_ids == tuple(
        sorted(d.id for d in project_canonical_index(index))
    )


def test_required_label_present_is_effective() -> None:
    document, changed = set_decision_applicability(
        _v2(_decision("A")), decision_id="A", required_labels=WINDOWS_LABELS
    )
    assert changed is True
    index = _index(document)
    assert _effective_ids(index, labels=WINDOWS_LABELS) == ("A",)
    assert _causes(index, labels=WINDOWS_LABELS) == {"A": None}


def test_required_label_absent_is_not_applicable() -> None:
    document, _ = set_decision_applicability(
        _v2(_decision("A")), decision_id="A", required_labels=WINDOWS_LABELS
    )
    index = _index(document)
    assert _effective_ids(index) == ()
    assert _causes(index) == {"A": CAUSE_NOT_APPLICABLE}
    resolution = resolve_effective(index)
    (decision,) = resolution.decisions
    assert decision.applicability_required_labels == WINDOWS_LABELS
    trace = {step.step: step.outcome for step in decision.trace}
    assert trace["applicability"] == "not_applicable"


def test_non_active_lifecycle_cause_wins_over_applicability() -> None:
    document = _v2(_decision("A", status="superseded"), _decision("B", status="deprecated"))
    for decision_id in ("A", "B"):
        document, _ = set_decision_applicability(
            document, decision_id=decision_id, required_labels=WINDOWS_LABELS
        )
    causes = _causes(_index(document))
    assert causes == {
        "A": CAUSE_LIFECYCLE_SUPERSEDED,
        "B": CAUSE_LIFECYCLE_DEPRECATED,
    }


def test_applicability_is_evaluated_only_after_lifecycle() -> None:
    # An active decision with matching labels is effective; a superseded
    # decision keeps its lifecycle cause even when its labels match.
    document = _v2(_decision("A"), _decision("B", status="superseded"))
    for decision_id in ("A", "B"):
        document, _ = set_decision_applicability(
            document, decision_id=decision_id, required_labels=WINDOWS_LABELS
        )
    causes = _causes(_index(document), labels=WINDOWS_LABELS)
    assert causes == {"A": None, "B": CAUSE_LIFECYCLE_SUPERSEDED}


# ── 8-10. matching semantics and invariance ───────────────────────────────


def test_label_matching_is_exact_and_case_sensitive() -> None:
    document, _ = set_decision_applicability(
        _v2(_decision("A")),
        decision_id="A",
        required_labels=("platform:windows",),
    )
    index = _index(document)
    assert _effective_ids(index, labels=("platform:windows",)) == ("A",)
    assert _effective_ids(index, labels=("Platform:Windows",)) == ()
    assert _effective_ids(index, labels=("platform:windows ",)) == ()
    assert _effective_ids(index, labels=("platform",)) == ()


def test_label_set_is_order_and_duplicate_invariant() -> None:
    first, _ = set_decision_applicability(
        _v2(_decision("A")),
        decision_id="A",
        required_labels=("b", "a", "b"),
    )
    second, _ = set_decision_applicability(
        _v2(_decision("A")),
        decision_id="A",
        required_labels=("a", "b"),
    )
    assert (
        first["decision_index"]["decisions"][0]["applicability"]
        == second["decision_index"]["decisions"][0]["applicability"]
        == {"required_labels": ["a", "b"]}
    )
    assert _index(first) == _index(second)


def test_irrelevant_context_labels_do_not_change_the_result() -> None:
    document, _ = set_decision_applicability(
        _v2(_decision("A")), decision_id="A", required_labels=WINDOWS_LABELS
    )
    index = _index(document)
    assert _effective_ids(index, labels=WINDOWS_LABELS) == ("A",)
    assert _effective_ids(
        index, labels=WINDOWS_LABELS + ("team:payments", "env:prod")
    ) == ("A",)


def test_resolution_is_invariant_to_record_order() -> None:
    document = _v2(_decision("A"), _decision("B"))
    document, _ = set_decision_applicability(
        document, decision_id="A", required_labels=WINDOWS_LABELS
    )
    index = _index(document)
    baseline = resolve_effective(index, GovernanceContext(labels=()))
    reordered = type(index)(
        records=tuple(reversed(index.records)), rules=index.rules
    )
    assert resolve_effective(reordered, GovernanceContext(labels=())) == baseline


def test_applicability_does_not_consult_retrieval_or_timing() -> None:
    # The resolver only reads canonical applicability and context labels: the
    # record carries no retrieval score, and the same inputs give the same
    # result.
    document, _ = set_decision_applicability(
        _v2(_decision("A")), decision_id="A", required_labels=WINDOWS_LABELS
    )
    index = _index(document)
    first = resolve_effective(index, GovernanceContext(labels=()))
    second = resolve_effective(copy.deepcopy(index), GovernanceContext(labels=()))
    assert first == second
    assert first.decisions[0].cause == CAUSE_NOT_APPLICABLE


# ── 11. ADR-020 rule applicability stays independent ──────────────────────


def test_decision_applicability_never_becomes_rule_applicability() -> None:
    document = _v2(_decision("A"))
    document, _ = set_decision_applicability(
        document, decision_id="A", required_labels=WINDOWS_LABELS
    )
    index = _index(document)
    for record in index.records:
        assert not any(
            key in ("include_paths", "exclude_paths")
            for key in record.applicability_required_labels
        )
    # Rule bindings keep their own ADR-020 applicability untouched.
    for rule in index.rules:
        assert set(rule.applicability) <= {"include_paths", "exclude_paths"}


# ── 12. hints never become canonical applicability ────────────────────────


def test_scope_and_source_text_never_become_applicability() -> None:
    # context_scope (and MCP scope hints, O1A classification) are retrieval
    # metadata; a decision that declares only a scope is globally eligible.
    document = _v2(_decision("A"))
    assert document["decision_index"]["decisions"][0].get("applicability") is None
    assert _effective_ids(_index(document)) == ("A",)
    assert not load_persisted_decision_index(
        document["decision_index"]
    ).records[0].applicability_required_labels


def test_only_the_explicit_operation_sets_applicability() -> None:
    base = _v2(_decision("A"))
    with pytest.raises(DecisionIndexPersistenceError, match="does not exist"):
        set_decision_applicability(base, decision_id="MISSING", required_labels=("x",))
    with pytest.raises(DecisionIndexPersistenceError, match="non-empty"):
        set_decision_applicability(base, decision_id="A", required_labels=())


def test_applicability_requires_v2_memory() -> None:
    v1 = v1_document(_v2(_decision("A")))
    with pytest.raises(DecisionIndexMigrationRequired, match="v2"):
        set_decision_applicability(v1, decision_id="A", required_labels=WINDOWS_LABELS)


# ── 13. DG1D governance change from the same resolver ─────────────────────


def test_resolve_change_reports_governed_scope_change() -> None:
    before = _v2(_decision("A"))
    after, _ = set_decision_applicability(
        _v2(_decision("A")), decision_id="A", required_labels=WINDOWS_LABELS
    )
    change = resolve_change(
        _index(before), _index(after), GovernanceContext(labels=())
    )
    assert change.affected_decision_ids == ("A",)
    (delta,) = change.changes
    assert CHANGE_GOVERNED_SCOPE in delta.kinds


def test_resolve_change_reports_effective_set_change_across_contexts() -> None:
    document, _ = set_decision_applicability(
        _v2(_decision("A")), decision_id="A", required_labels=WINDOWS_LABELS
    )
    index = _index(document)
    # Same state, different context: an effective-set change derived only from
    # the shared resolver.
    changes = resolve_change(
        index,
        index,
        GovernanceContext(labels=WINDOWS_LABELS),
    )
    assert not changes.changed
    empty = resolve_effective(index, GovernanceContext(labels=()))
    applied = resolve_effective(
        index, GovernanceContext(labels=WINDOWS_LABELS)
    )
    assert empty.effective_ids == ()
    assert applied.effective_ids == ("A",)


# ── 14. no runtime consumer changes input in B1 ───────────────────────────


def test_projection_ignores_applicability_so_enforcement_inputs_are_unchanged() -> None:
    document, _ = set_decision_applicability(
        _v2(_decision("A")), decision_id="A", required_labels=WINDOWS_LABELS
    )
    index = _index(document)
    # Layer 1 projection still emits the active decision unchanged; only the
    # resolver (DG1F consumer, not yet wired) sees not_applicable.
    projected = project_canonical_index(index)
    assert [d.id for d in projected] == ["A"]
    assert resolve_effective(index, GovernanceContext(labels=())).effective_ids == ()


# ── mutation guards: the predicate and the compatibility default are live ─


def test_compatibility_default_would_fail_if_predicate_were_bypassed() -> None:
    # If absent applicability were treated as not-applicable, this fails.
    document = _v2(_decision("A"))
    assert _effective_ids(_index(document)) == ("A",)


def test_label_predicate_would_fail_if_containment_were_dropped() -> None:
    # If the required-label predicate were skipped, this active decision would
    # stay effective for an empty context.
    document, _ = set_decision_applicability(
        _v2(_decision("A")), decision_id="A", required_labels=WINDOWS_LABELS
    )
    assert _effective_ids(_index(document)) == ()

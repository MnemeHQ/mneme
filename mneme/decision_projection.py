"""
decision_projection.py — Canonical Decision Index to Layer 1 runtime projector.

Deterministic projection from ``mneme.decision_index`` canonical architecture
records into the existing ``mneme.schemas.Decision`` / ``Rule`` runtime
(ADR-023 section 11). The projector is pure: identical canonical input
always produces identical runtime objects, and it never invents rules,
path applicability, lifecycle states, or identity.

Mapping (ADR-023 section 11):

    decision_id              -> Decision.id
    statement                -> Decision.decision
    rationale                -> Decision.rationale
    context_scope            -> Decision.scope
    constraints              -> Decision.constraints
    anti_patterns            -> Decision.anti_patterns
    derived Layer 1 rules    -> Decision.rules
    source provenance        -> Decision.source_path
    lifecycle                -> Decision.status
    decided_at               -> Decision.created_at / updated_at

``memory_path`` is runtime storage provenance (ADR-020 policy root and
ADR-019 policy-source exemption depend on it at enforcement time). It is a
loading-time parameter of the projector, never canonical identity.

Lifecycle projection (ADR-023 section 6):

    active     -> projected as an active runtime Decision
    superseded -> retained in the index, not projected
    deprecated -> retained in the index, not projected
    inactive   -> retained in the index, not projected

D0 validates only the ``architecture`` decision class; a record of any
other class fails closed.
"""
from __future__ import annotations

from mneme.decision_index import (
    CANONICAL_DECISION_CLASS_ARCHITECTURE,
    SOURCE_TYPE_ADR,
    VALID_SOURCE_TYPES,
    CanonicalArchitectureIndex,
    CanonicalDecisionRecord,
    CanonicalRuleRecord,
)
from mneme.schemas import Decision, Rule

PROJECTABLE_LIFECYCLE_STATUSES: frozenset[str] = frozenset({"active"})

ARCHITECTURE_MAPPING = {
    "decision_id": "id",
    "statement": "decision",
    "rationale": "rationale",
    "context_scope": "scope",
    "constraints": "constraints",
    "anti_patterns": "anti_patterns",
    "derived_rules": "rules",
    "source_evidence": "source_path",
    "lifecycle_status": "status",
    "decided_at": "created_at/updated_at",
}


def _test_evidence_entry(evidence) -> dict[str, str]:
    """Rebuild one declared test-evidence entry exactly as the runtime stores it.

    A declaration without a SHA pin round-trips without the ``sha`` key, so
    Audit evidence validation (which treats an absent and an empty pin as
    the same fail-closed state) sees an unchanged record.
    """
    entry = {"selector": evidence.selector}
    if evidence.sha:
        entry["sha"] = evidence.sha
    return entry


def project_canonical_rule(rule: CanonicalRuleRecord) -> Rule:
    """Project one canonical rule into the existing typed ``Rule`` model.

    The ``Rule`` constructor re-validates the type, the non-empty literal,
    and the ADR-020 selectors, so a malformed canonical payload fails
    deterministically instead of silently weakening the rule.
    """
    payload = rule.rule_payload
    value = payload.get("value")
    if not isinstance(value, str):
        raise ValueError(
            f"canonical rule {rule.rule_id!r} payload requires a string 'value'"
        )
    include_raw = rule.applicability.get("include_paths")
    include_paths = tuple(include_raw) if include_raw is not None else None
    exclude_paths = tuple(rule.applicability.get("exclude_paths", ()))
    return Rule(
        type=rule.rule_type,
        value=value,
        include_paths=include_paths,
        exclude_paths=exclude_paths,
    )


def _source_path_of(record: CanonicalDecisionRecord) -> str:
    """Resolve the runtime ``source_path`` from canonical source evidence.

    The provenance type is not consulted: the locator round-trips whatever
    the runtime recorded (an ADR path from the ADR adapter, or an
    unverified runtime locator from the generic adapter), because
    ``Decision.source_path`` feeds the ADR-019/ADR-020 policy-source
    exemptions and must survive the round trip unchanged.
    """
    for evidence in record.source_evidence:
        if evidence.source_type not in VALID_SOURCE_TYPES:
            raise ValueError(
                f"decision {record.decision_id!r} carries unknown "
                f"source_type {evidence.source_type!r} "
                f"(expected one of {sorted(VALID_SOURCE_TYPES)})"
            )
    if record.source_evidence:
        return record.source_evidence[0].source_locator
    return ""


def project_canonical_decision(
    record: CanonicalDecisionRecord,
    rules: tuple[CanonicalRuleRecord, ...] = (),
    memory_path: str = "",
) -> Decision:
    """Project one canonical architecture decision into the Layer 1 runtime.

    Args:
        record:      The canonical decision record. ``decision_class`` must
                     be ``"architecture"`` (D0 validates only this class)
                     and ``lifecycle_status`` must be projectable.
        rules:       The canonical rules derived from this decision version,
                     in derived order.
        memory_path: Runtime policy-memory path that is loading this
                     decision. Preserved for ADR-019/ADR-020 policy-source
                     semantics; never part of canonical identity.

    Raises:
        ValueError: On a non-architecture decision class, a non-projectable
                    lifecycle status, or a rule whose owning decision or
                    version does not match this record.
    """
    if record.decision_class not in (CANONICAL_DECISION_CLASS_ARCHITECTURE,):
        raise ValueError(
            f"decision {record.decision_id!r} has decision_class "
            f"{record.decision_class!r}; D0 projects only "
            f"{CANONICAL_DECISION_CLASS_ARCHITECTURE!r}"
        )
    if record.lifecycle_status not in PROJECTABLE_LIFECYCLE_STATUSES:
        raise ValueError(
            f"decision {record.decision_id!r} has lifecycle_status "
            f"{record.lifecycle_status!r}; D0 projects only "
            f"{sorted(PROJECTABLE_LIFECYCLE_STATUSES)}"
        )
    runtime_rules = [project_canonical_rule(rule) for rule in rules]
    for rule in rules:
        if rule.decision_id != record.decision_id:
            raise ValueError(
                f"canonical rule {rule.rule_id!r} belongs to decision "
                f"{rule.decision_id!r}, not {record.decision_id!r}"
            )
        if rule.decision_version != record.version:
            raise ValueError(
                f"canonical rule {rule.rule_id!r} was derived from decision "
                f"version {rule.decision_version!r}, but record "
                f"{record.decision_id!r} is version {record.version!r}"
            )
        if rule.lifecycle_status != record.lifecycle_status:
            raise ValueError(
                f"canonical rule {rule.rule_id!r} has lifecycle_status "
                f"{rule.lifecycle_status!r}, incompatible with owning "
                f"record {record.decision_id!r} at "
                f"{record.lifecycle_status!r}"
            )
    supplied_rule_ids = tuple(rule.rule_id for rule in rules)
    if supplied_rule_ids != record.derived_rule_ids:
        raise ValueError(
            f"decision {record.decision_id!r} declares derived_rule_ids "
            f"{list(record.derived_rule_ids)} but the supplied rules are "
            f"{list(supplied_rule_ids)}; canonical decision-to-rule "
            f"lineage must match exactly (ADR-023 section 10)"
        )
    return Decision(
        id=record.decision_id,
        decision=record.statement,
        rationale=record.rationale,
        scope=list(record.context_scope),
        constraints=list(record.constraints),
        anti_patterns=list(record.anti_patterns),
        created_at=record.decided_at,
        updated_at=(
            record.updated_at
            if record.updated_at is not None
            else record.decided_at
        ),
        rules=runtime_rules,
        test_evidence=[
            _test_evidence_entry(evidence) for evidence in record.test_evidence
        ],
        source_path=_source_path_of(record),
        memory_path=memory_path,
        status=record.lifecycle_status,
    )


def project_canonical_index(
    index: CanonicalArchitectureIndex,
    memory_path: str = "",
) -> list[Decision]:
    """Project a canonical index into the list of runtime ``Decision``s.

    Only decisions whose lifecycle is projectable are emitted, in record
    order. Non-projectable records (superseded / deprecated / inactive)
    stay in the canonical index for lineage without creating active Layer 1
    governance.
    """
    out: list[Decision] = []
    for record in index.records:
        if record.lifecycle_status not in PROJECTABLE_LIFECYCLE_STATUSES:
            continue
        out.append(project_canonical_decision(
            record,
            rules=index.rules_for_decision(record.decision_id),
            memory_path=memory_path,
        ))
    return out


__all__ = [
    "ARCHITECTURE_MAPPING",
    "PROJECTABLE_LIFECYCLE_STATUSES",
    "project_canonical_decision",
    "project_canonical_index",
    "project_canonical_rule",
]

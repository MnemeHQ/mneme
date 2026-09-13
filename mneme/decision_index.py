"""
decision_index.py — OSS Decision Index kernel (ADR-023, D0).

Canonical, source-independent decision records. This module is the
source-of-truth data contract for the D0 milestone: frozen dataclasses
describing a decision and its derived rules, plus deterministic adapters
from the two representations that already exist on ``main``:

1. ``ADR`` records from the ADR compiler (``adr_compiler.resolve_precedence``
   output) — the ADR-to-canonical adapter;
2. runtime ``Decision`` objects from ``MemoryStore`` — the
   runtime-to-canonical adapter used by parity evidence.

Nothing here changes retrieval, enforcement, conflict detection, Audit, or
benchmark behavior (ADR-023 D0 boundary). No database, no ORM, no hosted
service: the canonical layer is plain deterministic Python records.

Identity and versioning (D0 contract)
-------------------------------------
``decision_id`` is the stable identifier already present in the
authoritative compiler path — the ADR frontmatter ``id`` for ADR-sourced
decisions, the memory ``id`` for persisted decisions. Moving or renaming a
source file never redefines it.

``version`` is ``"1"`` for every D0 record. The current architecture carries
exactly one immutable version per decision id (an ADR is superseded by a
*new* id, not by a new version of the same id), so ``"1"`` is the narrowest
deterministic representation. A richer version contract (multiple immutable
versions per id, explicit active-version resolution) is D1 scope per
ADR-023's sequence and is deliberately not invented here.

Anti-pattern compatibility
--------------------------
``anti_patterns`` and ``constraints`` are carried as separate fields.
The compiler path emits no anti-patterns, but the persisted-memory path
does, and retrieval/enforcement distinguish the two fields. Collapsing
them would silently change legacy enforcement semantics, so the canonical
record keeps them apart losslessly.

Scope vs applicability
----------------------
``context_scope`` records organizational relevance (ADR-023 section 5).
It never becomes typed-rule applicability: applicability lives only on
``CanonicalRuleRecord.applicability`` (ADR-020 selectors), exactly as in
the current runtime.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mneme.adr_compiler import _directive_to_constraint_string
from mneme.adr_constraints import parse_constraints_section
from mneme.adr_import import project_decision_graph
from mneme.adr_schema import ADR
from mneme.schemas import Decision, Rule

CANONICAL_DECISION_CLASS_ARCHITECTURE = "architecture"

VALID_DECISION_CLASSES: frozenset[str] = frozenset({
    CANONICAL_DECISION_CLASS_ARCHITECTURE,
})

# Lifecycle vocabulary reused from the existing graph projection
# (``adr_import.GraphStatus``). "inactive" mirrors an explicitly ``proposed``
# ADR: represented, lineage-only, never projected into Layer 1 governance.
VALID_LIFECYCLE_STATUSES: frozenset[str] = frozenset({
    "active",
    "superseded",
    "deprecated",
    "inactive",
})

CANONICAL_VERSION = "1"


@dataclass(frozen=True)
class CanonicalSourceEvidence:
    """Source provenance for one canonical decision.

    Attributes:
        source_type:    Validated source class. D0 validates ``"adr"`` only.
        source_locator: Deterministic locator (for ADRs, the source path
                        recorded by the parser).
    """

    source_type: str
    source_locator: str


@dataclass(frozen=True)
class CanonicalTestEvidence:
    """Declared test-evidence linkage (ADR-024) preserved losslessly.

    The runtime stores these as plain dicts; the canonical layer keeps the
    same shape so Audit evidence linkage is unchanged after projection.
    """

    selector: str
    sha: str = ""


@dataclass(frozen=True)
class CanonicalRuleRecord:
    """One explicitly derived, typed rule attached to a decision version.

    Attributes:
        rule_id:          Deterministic identity derived from the decision
                          and the rule's position, e.g.
                          ``"ADR-005:FORBID_LITERAL:0"``.
        decision_id:      Owning decision id.
        decision_version: Owning decision version.
        rule_type:        Typed rule type (D0: ``FORBID_LITERAL`` only).
        rule_payload:     Typed payload; ``value`` carries the forbidden
                          literal exactly as the ADR declared it.
        applicability:    ADR-020 path selectors, e.g.
                          ``{"include_paths": [...], "exclude_paths": [...]}``;
                          empty dict means global applicability.
        lifecycle_status: Lifecycle inherited from the owning decision.
    """

    rule_id: str
    decision_id: str
    decision_version: str
    rule_type: str
    rule_payload: dict[str, Any]
    applicability: dict[str, Any] = field(default_factory=dict)
    lifecycle_status: str = "active"


@dataclass(frozen=True)
class CanonicalDecisionRecord:
    """One canonical decision record (ADR-023 section 7).

    ``constraints`` and ``anti_patterns`` are preserved as distinct fields;
    rules are explicit ``CanonicalRuleRecord`` entries only — never inferred
    from prose, and never derived from ``context_scope``.

    ``updated_at`` is optional losslessness for runtime records whose
    last-modified timestamp differs from ``decided_at`` (ADR sources carry a
    single decision date, so the ADR adapter leaves this unset and the
    projector derives both runtime timestamps from ``decided_at``).
    """

    decision_id: str
    version: str = CANONICAL_VERSION
    decision_class: str = CANONICAL_DECISION_CLASS_ARCHITECTURE
    statement: str = ""
    rationale: str = ""
    lifecycle_status: str = "active"
    owner: str = ""
    decided_at: str = ""
    updated_at: str | None = None
    context_scope: tuple[str, ...] = ()
    targets: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    anti_patterns: tuple[str, ...] = ()
    source_evidence: tuple[CanonicalSourceEvidence, ...] = ()
    test_evidence: tuple[CanonicalTestEvidence, ...] = ()
    relationships: tuple[tuple[str, str], ...] = ()
    derived_rule_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CanonicalArchitectureIndex:
    """D0 canonical Decision Index contents for the architecture class.

    A flat, ordered pair of decision records and derived rule records.
    Records appear in adapter input order; rules appear grouped by owning
    decision, in derived order. This is an in-memory view, not storage.
    """

    records: tuple[CanonicalDecisionRecord, ...] = ()
    rules: tuple[CanonicalRuleRecord, ...] = ()

    def rules_for_decision(self, decision_id: str) -> tuple[CanonicalRuleRecord, ...]:
        """Return the rules whose ``decision_id`` matches, in derived order."""
        return tuple(rule for rule in self.rules if rule.decision_id == decision_id)


def _rule_id(decision_id: str, index: int) -> str:
    return f"{decision_id}:FORBID_LITERAL:{index}"


def _rule_applicability(
    include_paths: tuple[str, ...] | None,
    exclude_paths: tuple[str, ...],
) -> dict[str, Any]:
    applicability: dict[str, Any] = {}
    if include_paths is not None:
        applicability["include_paths"] = list(include_paths)
    if exclude_paths:
        applicability["exclude_paths"] = list(exclude_paths)
    return applicability


def _directive_to_canonical_rule(
    decision_id: str,
    version: str,
    lifecycle_status: str,
    index: int,
    directive,  # ConstraintDirective; untyped to avoid a public-name dependency
) -> CanonicalRuleRecord:
    """Translate one ``FORBID_LITERAL`` directive into a canonical rule."""
    return CanonicalRuleRecord(
        rule_id=_rule_id(decision_id, index),
        decision_id=decision_id,
        decision_version=version,
        rule_type="FORBID_LITERAL",
        rule_payload={"value": directive.value},
        applicability=_rule_applicability(
            directive.include_paths, directive.exclude_paths
        ),
        lifecycle_status=lifecycle_status,
    )


def _directives_to_canonical(
    decision_id: str,
    version: str,
    lifecycle_status: str,
    body: str,
) -> tuple[list[CanonicalRuleRecord], list[str]]:
    """Split a ``## Constraints`` body into canonical rules and constraints.

    Mirrors ``adr_compiler.adrs_to_decisions`` exactly: ``FORBID_LITERAL``
    becomes a typed rule; every other directive is rendered as a legacy
    constraint string through the compiler's own renderer so the two paths
    cannot drift.
    """
    rules: list[CanonicalRuleRecord] = []
    constraints: list[str] = []
    rule_index = 0
    for directive in parse_constraints_section(body):
        if directive.kind == "FORBID_LITERAL":
            rules.append(_directive_to_canonical_rule(
                decision_id, version, lifecycle_status, rule_index, directive
            ))
            rule_index += 1
        else:
            constraints.append(_directive_to_constraint_string(directive))
    return rules, constraints


def _record_from_adr(
    adr: ADR,
    lifecycle_status: str,
) -> tuple[CanonicalDecisionRecord, list[CanonicalRuleRecord]]:
    rules, constraints = _directives_to_canonical(
        adr.id, CANONICAL_VERSION, lifecycle_status, adr.body
    )
    record = CanonicalDecisionRecord(
        decision_id=adr.id,
        version=CANONICAL_VERSION,
        decision_class=CANONICAL_DECISION_CLASS_ARCHITECTURE,
        statement=adr.title,
        rationale=adr.body,
        lifecycle_status=lifecycle_status,
        decided_at=adr.date,
        context_scope=(adr.scope,),
        constraints=tuple(constraints),
        anti_patterns=(),
        source_evidence=(
            (CanonicalSourceEvidence(
                source_type="adr", source_locator=adr.source_path
            ),)
            if adr.source_path
            else ()
        ),
        relationships=tuple(("supersedes", ref) for ref in adr.supersedes),
        derived_rule_ids=tuple(rule.rule_id for rule in rules),
    )
    return record, rules


def adrs_to_canonical(active_adrs: list[ADR]) -> CanonicalArchitectureIndex:
    """Adapt compiled (precedence-resolved) ADRs into canonical records.

    Input contract is identical to ``adr_compiler.adrs_to_decisions``: the
    output of ``resolve_precedence``. Each record carries the decision id,
    statement (title), rationale (body), retrieval scope, legacy
    constraints, typed rules with ADR-020 selectors, source provenance,
    timestamps, and lifecycle status exactly as the current compiler path
    represents them. Anti-patterns are empty for the ADR path (the compiler
    emits none); the field exists for the lossless runtime round trip.
    """
    records: list[CanonicalDecisionRecord] = []
    rules: list[CanonicalRuleRecord] = []
    for adr in active_adrs:
        record, adr_rules = _record_from_adr(adr, "active")
        records.append(record)
        rules.extend(adr_rules)
    return CanonicalArchitectureIndex(
        records=tuple(records), rules=tuple(rules)
    )


def decisions_to_canonical(
    decisions: list[Decision],
) -> CanonicalArchitectureIndex:
    """Adapt runtime ``Decision`` records into canonical records.

    Lossless for every runtime-relevant field: statement, rationale, scope,
    constraints, anti-patterns (kept separate), typed rules with selectors,
    declared test evidence, provenance, timestamps, and lifecycle status.
    ``memory_path`` is runtime storage provenance and is deliberately not
    carried — projection re-attaches it as a loading-time parameter.
    """
    records: list[CanonicalDecisionRecord] = []
    rules: list[CanonicalRuleRecord] = []
    for decision in decisions:
        decision_rules: list[CanonicalRuleRecord] = []
        for index, rule in enumerate(decision.rules):
            decision_rules.append(CanonicalRuleRecord(
                rule_id=_rule_id(decision.id, index),
                decision_id=decision.id,
                decision_version=CANONICAL_VERSION,
                rule_type=rule.type,
                rule_payload={"value": rule.value},
                applicability=_rule_applicability(
                    rule.include_paths, rule.exclude_paths
                ),
                lifecycle_status=decision.status,
            ))
        records.append(CanonicalDecisionRecord(
            decision_id=decision.id,
            version=CANONICAL_VERSION,
            decision_class=CANONICAL_DECISION_CLASS_ARCHITECTURE,
            statement=decision.decision,
            rationale=decision.rationale,
            lifecycle_status=decision.status,
            decided_at=decision.created_at,
            updated_at=decision.updated_at,
            context_scope=tuple(decision.scope),
            constraints=tuple(decision.constraints),
            anti_patterns=tuple(decision.anti_patterns),
            source_evidence=(
                (CanonicalSourceEvidence(
                    source_type="adr", source_locator=decision.source_path
                ),)
                if decision.source_path
                else ()
            ),
            test_evidence=tuple(
                CanonicalTestEvidence(
                    selector=str(entry.get("selector", "")),
                    sha=str(entry.get("sha", "")),
                )
                for entry in decision.test_evidence
            ),
            derived_rule_ids=tuple(rule.rule_id for rule in decision_rules),
        ))
        rules.extend(decision_rules)
    return CanonicalArchitectureIndex(
        records=tuple(records), rules=tuple(rules)
    )


def build_canonical_index(
    parsed_adrs: list[ADR],
    active_adrs: list[ADR],
) -> CanonicalArchitectureIndex:
    """Build a corpus-level canonical index from a parsed ADR corpus.

    ``active_adrs`` is the precedence-resolved active set (the same list
    passed to ``adrs_to_decisions``); those records carry
    ``lifecycle_status="active"``. Every other parsed ADR is retained for
    lineage with the lifecycle resolved by the existing graph projection
    (``superseded`` / ``deprecated`` / ``inactive``).

    An ADR that the graph calls ``active`` but that precedence did not pick
    (a same-scope precedence loser) is excluded from the index: the current
    compiler produces no runtime record for it, and representing it as
    active would fabricate governance the compiler never authorized. That
    representation gap is D1 lifecycle-hardening scope (ADR-023 sequence).
    """
    active_ids = {a.id for a in active_adrs}
    graph_status = {
        node.id: node.status for node in project_decision_graph(parsed_adrs)
    }
    records: list[CanonicalDecisionRecord] = []
    rules: list[CanonicalRuleRecord] = []
    for adr in parsed_adrs:
        if adr.id in active_ids:
            status = "active"
        else:
            status = graph_status.get(adr.id, "")
            if status not in VALID_LIFECYCLE_STATUSES or status == "active":
                continue
        record, adr_rules = _record_from_adr(adr, status)
        records.append(record)
        rules.extend(adr_rules)
    return CanonicalArchitectureIndex(
        records=tuple(records), rules=tuple(rules)
    )


def rule_payload_from_runtime(rule: Rule) -> dict[str, Any]:
    """Serialize a runtime ``Rule`` into a canonical rule payload."""
    payload: dict[str, Any] = {"value": rule.value}
    if rule.include_paths is not None:
        payload["include_paths"] = list(rule.include_paths)
    if rule.exclude_paths:
        payload["exclude_paths"] = list(rule.exclude_paths)
    return payload


def canonical_from(
    adrs: list[ADR] | None = None,
    decisions: list[Decision] | None = None,
) -> CanonicalArchitectureIndex:
    """Convenience adapter dispatch for the two existing source types."""
    if decisions is not None:
        return decisions_to_canonical(decisions)
    if adrs is not None:
        return adrs_to_canonical(adrs)
    raise ValueError("canonical_from requires adrs or decisions")


__all__ = [
    "CANONICAL_DECISION_CLASS_ARCHITECTURE",
    "CANONICAL_VERSION",
    "CanonicalArchitectureIndex",
    "CanonicalDecisionRecord",
    "CanonicalRuleRecord",
    "CanonicalSourceEvidence",
    "CanonicalTestEvidence",
    "VALID_DECISION_CLASSES",
    "VALID_LIFECYCLE_STATUSES",
    "adrs_to_canonical",
    "build_canonical_index",
    "canonical_from",
    "decisions_to_canonical",
    "rule_payload_from_runtime",
]

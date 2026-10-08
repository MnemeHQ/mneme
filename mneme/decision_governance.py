"""
decision_governance.py — DG1C effective-decision resolver (ADR-031).

Pure, deterministic resolution of which canonical decisions govern a
``GovernanceContext``, with a per-decision explanation trace. DG1C adds no
governance semantics: it makes the v1 semantics that 0.10.0 already applies
explicit and explainable.

v1 semantics (ADR-030 §11, ADR-031 §2-§3)
-----------------------------------------
- Lifecycle decides effectiveness. Only ``active`` decisions are effective,
  exactly as the Layer 1 projection keeps only ``active`` (ADR-023 §6). This
  is the parity contract: for every well-formed canonical state, the
  effective set equals ``project_canonical_index``.
- ``supersedes`` relationships explain *why* a decision is superseded; the
  relationship drives the lifecycle transition, so the lifecycle is the
  recorded outcome. A relationship counts only when declared by a decision
  that has held authority (any lifecycle except ``inactive``). A relationship
  declared by an ``inactive`` decision (for example a proposed ADR) has no
  authority.
- Precedence is resolved at ADR import and its reason is not persisted in
  v1, so the trace reports it as ``not_recorded`` and never guesses whether
  an ``inactive`` decision was a precedence loser or a proposed ADR.

Inconsistent v1 state is exposed, never resolved (ADR-031 §1, §7). The v1
loader accepts two states that canonical writers never produce:

- an ``active`` decision that an authoritative decision declares it
  supersedes. It stays ``effective`` (lifecycle decides, exactly as the
  projection does) and the resolution carries a
  ``supersession_lifecycle_conflict`` finding;
- a ``supersedes`` target that is not in the index. The effective set is
  unchanged and the resolution carries a ``dangling_supersedes`` finding.

Whether such a finding should block execution is a later decision (DG1F),
not a DG1C semantic. ``ambiguous`` is reserved for genuine governance
ambiguity introduced by later slices (DG1P onward); DG1C never emits it.

The resolver never reads the clock, retrieval scores, or input order.
``GovernanceContext`` is accepted and validated, but no v1 semantic depends
on it: the result is invariant to paths, labels, and ``as_of`` until
decision applicability or waivers exist (ADR-031 §6-§7).

Nothing here is wired into retrieval, enforcement, Audit, or MCP (DG1F).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mneme.decision_index import (
    VALID_LIFECYCLE_STATUSES,
    CanonicalArchitectureIndex,
)
from mneme.decision_index_persistence import load_decision_index_from_memory_file
from mneme.path_selectors import validate_relative_path

GOVERNANCE_SEMANTICS_VERSION = "mneme.governance-semantics/dg1c-1"

STATUS_EFFECTIVE = "effective"
STATUS_INEFFECTIVE = "ineffective"
STATUS_AMBIGUOUS = "ambiguous"

CAUSE_LIFECYCLE_SUPERSEDED = "lifecycle_superseded"
CAUSE_LIFECYCLE_DEPRECATED = "lifecycle_deprecated"
CAUSE_LIFECYCLE_INACTIVE = "lifecycle_inactive"

FINDING_SUPERSESSION_LIFECYCLE_CONFLICT = "supersession_lifecycle_conflict"
FINDING_DANGLING_SUPERSEDES = "dangling_supersedes"

_EFFECTIVE_LIFECYCLE = "active"
_NON_AUTHORITATIVE_LIFECYCLE = "inactive"
_LIFECYCLE_CAUSES = {
    "superseded": CAUSE_LIFECYCLE_SUPERSEDED,
    "deprecated": CAUSE_LIFECYCLE_DEPRECATED,
    "inactive": CAUSE_LIFECYCLE_INACTIVE,
}


@dataclass(frozen=True)
class GovernanceContext:
    """The context a resolution is computed for (ADR-031 §6).

    Attributes:
        paths:  ADR-020 normalized repository-relative paths
                (``path_selectors.validate_relative_path``). Stored sorted and
                de-duplicated.
        as_of:  Explicit instant for time-bound semantics. The resolver never
                reads the clock. ``None`` means no instant was supplied.
        labels: Opaque project-local strings with no identity, team, role or
                organization meaning. Stored sorted and de-duplicated.
    """

    paths: tuple[str, ...] = ()
    as_of: str | None = None
    labels: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        paths = tuple(sorted({validate_relative_path(p) for p in self.paths}))
        for label in self.labels:
            if not isinstance(label, str) or not label:
                raise ValueError("governance context labels must be non-empty strings")
        if self.as_of is not None and (not isinstance(self.as_of, str) or not self.as_of):
            raise ValueError("governance context as_of must be a non-empty string or None")
        object.__setattr__(self, "paths", paths)
        object.__setattr__(self, "labels", tuple(sorted(set(self.labels))))


@dataclass(frozen=True)
class TraceStep:
    """One step of a decision's resolution trace."""

    step: str
    outcome: str
    detail: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionResolution:
    """How one canonical decision resolved for the context.

    Attributes:
        decision_id:         Canonical decision id.
        decision_version_id: Active version id (empty when the source view
                             carries no version identity, e.g. ``--adr-dir``).
        lifecycle_status:    Recorded canonical lifecycle.
        status:              ``effective`` | ``ineffective`` (``ambiguous`` is
                             reserved for later slices; DG1C never emits it).
        cause:               ``None`` when effective; otherwise a cause code.
        rule_ids:            Rule lineage of the active version, in derived order.
        superseded_by:       Authoritative decisions declaring ``supersedes`` on it.
        trace:               Ordered explanation of the resolution.
    """

    decision_id: str
    decision_version_id: str
    lifecycle_status: str
    status: str
    cause: str | None
    rule_ids: tuple[str, ...] = ()
    superseded_by: tuple[str, ...] = ()
    trace: tuple[TraceStep, ...] = ()

    @property
    def effective(self) -> bool:
        return self.status == STATUS_EFFECTIVE


@dataclass(frozen=True)
class GovernanceFinding:
    """An integrity finding about the supplied canonical state."""

    code: str
    decision_id: str
    detail: tuple[str, ...] = ()


@dataclass(frozen=True)
class GovernanceResolution:
    """``EffectiveDecisionSet`` + ``ResolutionTrace`` for one context."""

    semantics_version: str
    context: GovernanceContext
    decisions: tuple[DecisionResolution, ...] = ()
    findings: tuple[GovernanceFinding, ...] = field(default_factory=tuple)

    @property
    def effective(self) -> tuple[DecisionResolution, ...]:
        return tuple(d for d in self.decisions if d.status == STATUS_EFFECTIVE)

    @property
    def ineffective(self) -> tuple[DecisionResolution, ...]:
        return tuple(d for d in self.decisions if d.status == STATUS_INEFFECTIVE)

    @property
    def ambiguities(self) -> tuple[DecisionResolution, ...]:
        return tuple(d for d in self.decisions if d.status == STATUS_AMBIGUOUS)

    @property
    def effective_ids(self) -> tuple[str, ...]:
        return tuple(d.decision_id for d in self.effective)


def _validate(index: CanonicalArchitectureIndex) -> None:
    seen: set[str] = set()
    for record in index.records:
        if record.decision_id in seen:
            raise ValueError(f"duplicate canonical decision id {record.decision_id!r}")
        seen.add(record.decision_id)
        if record.lifecycle_status not in VALID_LIFECYCLE_STATUSES:
            raise ValueError(
                f"decision {record.decision_id!r} has unknown lifecycle "
                f"{record.lifecycle_status!r}"
            )
    for rule in index.rules:
        if rule.decision_id not in seen:
            raise ValueError(
                f"rule {rule.rule_id!r} belongs to unknown decision {rule.decision_id!r}"
            )
    for record in index.records:
        bound = sorted(rule.rule_id for rule in index.rules_for_decision(record.decision_id))
        if bound != sorted(record.derived_rule_ids) or len(set(bound)) != len(bound):
            raise ValueError(
                f"decision {record.decision_id!r} rule lineage does not match its "
                f"bound rules: declared {sorted(record.derived_rule_ids)}, bound {bound}"
            )


def resolve_effective(
    index: CanonicalArchitectureIndex,
    context: GovernanceContext | None = None,
) -> GovernanceResolution:
    """Resolve which canonical decisions govern ``context`` (ADR-031 §1).

    Raises:
        ValueError: On a malformed index (duplicate ids, unknown lifecycle,
                    orphan rules, or rule lineage that does not match).
    """
    context = context if context is not None else GovernanceContext()
    _validate(index)

    lifecycle = {record.decision_id: record.lifecycle_status for record in index.records}
    declarers: dict[str, set[str]] = {}
    findings: list[GovernanceFinding] = []
    for record in index.records:
        if record.lifecycle_status == _NON_AUTHORITATIVE_LIFECYCLE:
            continue
        for rel_type, target in record.relationships:
            if rel_type != "supersedes":
                continue
            declarers.setdefault(target, set()).add(record.decision_id)
    for target in sorted(declarers):
        if target not in lifecycle:
            findings.append(GovernanceFinding(
                code=FINDING_DANGLING_SUPERSEDES,
                decision_id=target,
                detail=tuple(sorted(declarers[target])),
            ))

    decisions: list[DecisionResolution] = []
    for record in sorted(index.records, key=lambda r: r.decision_id):
        superseded_by = tuple(sorted(declarers.get(record.decision_id, ())))
        trace = [
            TraceStep("authority", "canonical"),
            TraceStep("lifecycle", record.lifecycle_status),
            TraceStep(
                "supersession",
                "superseded_by" if superseded_by else "none",
                superseded_by,
            ),
            TraceStep("precedence", "not_recorded"),
        ]
        if record.lifecycle_status == _EFFECTIVE_LIFECYCLE:
            status, cause = STATUS_EFFECTIVE, None
            if superseded_by:
                findings.append(GovernanceFinding(
                    code=FINDING_SUPERSESSION_LIFECYCLE_CONFLICT,
                    decision_id=record.decision_id,
                    detail=superseded_by,
                ))
        else:
            status, cause = STATUS_INEFFECTIVE, _LIFECYCLE_CAUSES[record.lifecycle_status]
        trace.append(TraceStep("result", status, (cause,) if cause else ()))
        decisions.append(DecisionResolution(
            decision_id=record.decision_id,
            decision_version_id=record.version_id,
            lifecycle_status=record.lifecycle_status,
            status=status,
            cause=cause,
            rule_ids=record.derived_rule_ids,
            superseded_by=superseded_by,
            trace=tuple(trace),
        ))

    return GovernanceResolution(
        semantics_version=GOVERNANCE_SEMANTICS_VERSION,
        context=context,
        decisions=tuple(decisions),
        findings=tuple(sorted(findings, key=lambda f: (f.code, f.decision_id, f.detail))),
    )


def resolve_effective_from_memory_file(
    path: str | Path,
    context: GovernanceContext | None = None,
) -> GovernanceResolution:
    """Resolve from the authoritative persisted index in project memory."""
    return resolve_effective(load_decision_index_from_memory_file(path), context)


__all__ = [
    "CAUSE_LIFECYCLE_DEPRECATED",
    "CAUSE_LIFECYCLE_INACTIVE",
    "CAUSE_LIFECYCLE_SUPERSEDED",
    "FINDING_DANGLING_SUPERSEDES",
    "FINDING_SUPERSESSION_LIFECYCLE_CONFLICT",
    "GOVERNANCE_SEMANTICS_VERSION",
    "STATUS_AMBIGUOUS",
    "STATUS_EFFECTIVE",
    "STATUS_INEFFECTIVE",
    "DecisionResolution",
    "GovernanceContext",
    "GovernanceFinding",
    "GovernanceResolution",
    "TraceStep",
    "resolve_effective",
    "resolve_effective_from_memory_file",
]

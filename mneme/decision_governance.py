"""
decision_governance.py — DG1 governance semantics over v1 (ADR-031).

- DG1C ``resolve_effective``: which canonical decisions govern a
  ``GovernanceContext``, with a per-decision explanation trace.
- DG1E ``evidence_identity_of``: the canonical decision version + rule
  identity of an evaluated rule (ADR-029 dimensions 3-4), failing closed.
- DG1D ``resolve_change``: the governance delta between two supplied
  snapshots, derived only by comparing two ``resolve_effective`` results.

None of these adds governance semantics: they make the v1 semantics that
0.10.0 already applies explicit and explainable.

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

Nothing here changes retrieval, enforcement, Audit, or MCP outcomes (DG1F).
The enforcement trace carries canonical identity (DG1E), but no verdict
depends on it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from mneme.decision_index import (
    VALID_LIFECYCLE_STATUSES,
    CanonicalArchitectureIndex,
)
from mneme.decision_index_persistence import load_decision_index_from_memory_file
from mneme.path_selectors import validate_relative_path
from mneme.schemas import VALID_RULE_TYPES

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



# ── DG1E: canonical evidence identity (ADR-031 §10, ADR-029 §2/§4) ─────────

EVIDENCE_IDENTITY_FIELDS = ("decision_id", "decision_version_id", "rule_id")


_VERSION_ID_PATTERN = re.compile(r"dver-[0-9a-f]{32}")
_RULE_DIGEST_PATTERN = re.compile(r"[0-9a-f]{32}")


@dataclass(frozen=True)
class EvidenceIdentity:
    """The ADR-029 decision/rule identity of one evaluated rule.

    ``complete`` only when all three fields are present and structurally
    canonical: ``decision_version_id`` is ``dver-<32 hex>`` (ADR-030 version
    identity) and ``rule_id`` is ``<exact decision id>:<known rule type>:<32
    hex>`` (ADR-030 §7). This covers ADR-029 binding dimensions 3 and 4 only:
    it is necessary, never sufficient, for "relevant enforcement observed".
    Structure is not authority: trust still comes from how the trace was
    built, so an arbitrary caller-made string never becomes canonical
    evidence merely by being well formed. Sources without a canonical
    version (section-less memory, ``--adr-dir``, ADR compile paths) are never
    complete, so binding fails closed.
    """

    decision_id: str
    decision_version_id: str
    rule_id: str

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(
            name for name in EVIDENCE_IDENTITY_FIELDS if not getattr(self, name)
        )

    @property
    def malformed(self) -> tuple[str, ...]:
        """Present fields that are not structurally canonical identities."""
        bad: list[str] = []
        if self.decision_version_id and not _VERSION_ID_PATTERN.fullmatch(
            self.decision_version_id
        ):
            bad.append("decision_version_id")
        if self.rule_id and not self.rule_owned_by_decision:
            bad.append("rule_id")
        return tuple(bad)

    @property
    def rule_owned_by_decision(self) -> bool:
        prefix = f"{self.decision_id}:"
        if not self.decision_id or not self.rule_id.startswith(prefix):
            return False
        rule_type, sep, digest = self.rule_id[len(prefix):].partition(":")
        return (
            bool(sep)
            and rule_type in VALID_RULE_TYPES
            and _RULE_DIGEST_PATTERN.fullmatch(digest) is not None
        )

    @property
    def complete(self) -> bool:
        return not self.missing and not self.malformed


def evidence_identity_of(evaluation: object) -> EvidenceIdentity:
    """Evidence identity of a ``RuleEvaluation`` or typed-rule ``Violation``.

    Legacy prose violations carry no rule id and are never complete.
    """
    return EvidenceIdentity(
        decision_id=getattr(evaluation, "decision_id", "") or "",
        decision_version_id=getattr(evaluation, "decision_version_id", "") or "",
        rule_id=getattr(evaluation, "rule_id", "") or "",
    )


# ── DG1D: governance change between two supplied snapshots (ADR-031 §9) ────

CHANGE_SEMANTICS_VERSION = "mneme.governance-change/dg1d-1"

CHANGE_DECISION_ADDED = "decision_added"
CHANGE_DECISION_REMOVED = "decision_removed"
CHANGE_BECAME_EFFECTIVE = "became_effective"
CHANGE_BECAME_INEFFECTIVE = "became_ineffective"
CHANGE_LIFECYCLE = "lifecycle_changed"
CHANGE_CAUSE = "resolution_cause_changed"
CHANGE_VERSION = "version_changed"
CHANGE_RULE_SET = "rule_set_changed"
CHANGE_SUPERSEDED_BY = "superseded_by_changed"

# Canonical order of change kinds within one DecisionChange.
CHANGE_KINDS = (
    CHANGE_DECISION_ADDED,
    CHANGE_DECISION_REMOVED,
    CHANGE_BECAME_EFFECTIVE,
    CHANGE_BECAME_INEFFECTIVE,
    CHANGE_LIFECYCLE,
    CHANGE_CAUSE,
    CHANGE_VERSION,
    CHANGE_RULE_SET,
    CHANGE_SUPERSEDED_BY,
)


@dataclass(frozen=True)
class DecisionChange:
    """How one decision's resolution differs between two snapshots."""

    decision_id: str
    kinds: tuple[str, ...]
    before: DecisionResolution | None
    after: DecisionResolution | None
    rules_added: tuple[str, ...] = ()
    rules_removed: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionChangeSet:
    """Governance delta between two supplied authoritative snapshots.

    ``activated_rule_ids`` / ``retired_rule_ids`` are the rules of effective
    decisions that start / stop governing. "Affected" is limited to what is
    mechanically known (decision, version and rule ids, plus the supplied
    context); downstream impact is out of scope.
    """

    semantics_version: str
    context: GovernanceContext
    changes: tuple[DecisionChange, ...] = ()
    activated_rule_ids: tuple[str, ...] = ()
    retired_rule_ids: tuple[str, ...] = ()
    findings_introduced: tuple[GovernanceFinding, ...] = ()
    findings_resolved: tuple[GovernanceFinding, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.changes or self.findings_introduced or self.findings_resolved)

    @property
    def affected_decision_ids(self) -> tuple[str, ...]:
        return tuple(change.decision_id for change in self.changes)


def _change_kinds(
    before: DecisionResolution | None,
    after: DecisionResolution | None,
) -> tuple[str, ...]:
    kinds: set[str] = set()
    if before is None and after is not None:
        kinds.add(CHANGE_DECISION_ADDED)
        if after.effective:
            kinds.add(CHANGE_BECAME_EFFECTIVE)
    elif after is None and before is not None:
        kinds.add(CHANGE_DECISION_REMOVED)
        if before.effective:
            kinds.add(CHANGE_BECAME_INEFFECTIVE)
    elif before is not None and after is not None:
        if not before.effective and after.effective:
            kinds.add(CHANGE_BECAME_EFFECTIVE)
        if before.effective and not after.effective:
            kinds.add(CHANGE_BECAME_INEFFECTIVE)
        if before.lifecycle_status != after.lifecycle_status:
            kinds.add(CHANGE_LIFECYCLE)
        if before.cause != after.cause:
            kinds.add(CHANGE_CAUSE)
        if before.decision_version_id != after.decision_version_id:
            kinds.add(CHANGE_VERSION)
        if set(before.rule_ids) != set(after.rule_ids):
            kinds.add(CHANGE_RULE_SET)
        if before.superseded_by != after.superseded_by:
            kinds.add(CHANGE_SUPERSEDED_BY)
    return tuple(kind for kind in CHANGE_KINDS if kind in kinds)


def _effective_rule_ids(resolution: GovernanceResolution) -> set[str]:
    return {rule_id for decision in resolution.effective for rule_id in decision.rule_ids}


def _finding_key(finding: GovernanceFinding) -> tuple[str, str, tuple[str, ...]]:
    return (finding.code, finding.decision_id, finding.detail)


def compare_resolutions(
    before: GovernanceResolution,
    after: GovernanceResolution,
) -> DecisionChangeSet:
    """Compare two resolver outputs computed under the same semantics/context.

    Raises:
        ValueError: If the two resolutions were produced under different
                    semantics versions or contexts (not comparable).
    """
    if before.semantics_version != after.semantics_version:
        raise ValueError(
            "cannot compare resolutions produced under different governance "
            f"semantics: {before.semantics_version!r} vs {after.semantics_version!r}"
        )
    if before.context != after.context:
        raise ValueError("cannot compare resolutions computed for different contexts")

    before_by_id = {d.decision_id: d for d in before.decisions}
    after_by_id = {d.decision_id: d for d in after.decisions}
    changes: list[DecisionChange] = []
    for decision_id in sorted(set(before_by_id) | set(after_by_id)):
        old = before_by_id.get(decision_id)
        new = after_by_id.get(decision_id)
        kinds = _change_kinds(old, new)
        if not kinds:
            continue
        old_rules = set(old.rule_ids) if old else set()
        new_rules = set(new.rule_ids) if new else set()
        changes.append(DecisionChange(
            decision_id=decision_id,
            kinds=kinds,
            before=old,
            after=new,
            rules_added=tuple(sorted(new_rules - old_rules)),
            rules_removed=tuple(sorted(old_rules - new_rules)),
        ))

    before_rules = _effective_rule_ids(before)
    after_rules = _effective_rule_ids(after)
    before_findings = set(before.findings)
    after_findings = set(after.findings)
    return DecisionChangeSet(
        semantics_version=CHANGE_SEMANTICS_VERSION,
        context=after.context,
        changes=tuple(changes),
        activated_rule_ids=tuple(sorted(after_rules - before_rules)),
        retired_rule_ids=tuple(sorted(before_rules - after_rules)),
        findings_introduced=tuple(
            sorted(after_findings - before_findings, key=_finding_key)
        ),
        findings_resolved=tuple(
            sorted(before_findings - after_findings, key=_finding_key)
        ),
    )


def resolve_change(
    before: CanonicalArchitectureIndex,
    after: CanonicalArchitectureIndex,
    context: GovernanceContext | None = None,
) -> DecisionChangeSet:
    """Governance delta between two supplied canonical states (ADR-031 §9).

    Both states are resolved with ``resolve_effective`` under the same
    context; the delta is derived only from those two results. Nothing is
    reconstructed that the caller did not supply.
    """
    context = context if context is not None else GovernanceContext()
    return compare_resolutions(
        resolve_effective(before, context),
        resolve_effective(after, context),
    )


def resolve_change_from_memory_files(
    before_path: str | Path,
    after_path: str | Path,
    context: GovernanceContext | None = None,
) -> DecisionChangeSet:
    """Governance delta between two project-memory files, e.g. two revisions.

    Each file is loaded through the same validated canonical read as any
    other consumer; section-less memory is refused.
    """
    return resolve_change(
        load_decision_index_from_memory_file(before_path),
        load_decision_index_from_memory_file(after_path),
        context,
    )


__all__ = [
    "CAUSE_LIFECYCLE_DEPRECATED",
    "CAUSE_LIFECYCLE_INACTIVE",
    "CAUSE_LIFECYCLE_SUPERSEDED",
    "CHANGE_BECAME_EFFECTIVE",
    "CHANGE_BECAME_INEFFECTIVE",
    "CHANGE_CAUSE",
    "CHANGE_DECISION_ADDED",
    "CHANGE_DECISION_REMOVED",
    "CHANGE_KINDS",
    "CHANGE_LIFECYCLE",
    "CHANGE_RULE_SET",
    "CHANGE_SEMANTICS_VERSION",
    "CHANGE_SUPERSEDED_BY",
    "CHANGE_VERSION",
    "EVIDENCE_IDENTITY_FIELDS",
    "FINDING_DANGLING_SUPERSEDES",
    "FINDING_SUPERSESSION_LIFECYCLE_CONFLICT",
    "GOVERNANCE_SEMANTICS_VERSION",
    "STATUS_AMBIGUOUS",
    "STATUS_EFFECTIVE",
    "STATUS_INEFFECTIVE",
    "DecisionChange",
    "DecisionChangeSet",
    "DecisionResolution",
    "EvidenceIdentity",
    "GovernanceContext",
    "GovernanceFinding",
    "GovernanceResolution",
    "TraceStep",
    "compare_resolutions",
    "evidence_identity_of",
    "resolve_change",
    "resolve_change_from_memory_files",
    "resolve_effective",
    "resolve_effective_from_memory_file",
]

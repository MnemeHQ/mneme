"""
protection.py — Per-decision protection activation (M1.4 P0).

Closes the first complete product loop:

    Audit → Setup → candidate → validate → activate → canonical verify → Protected

Everything here is a thin layer over the frozen P1.2 semantics in
``mneme.enforcer``. ``assess_protection`` / ``generate_protection_report``
remain the single source of truth for Protected / Mneme-ready / Requires
modelling / Guidance; this module never reclassifies a decision and never
reports protection that the canonical assessment does not independently
observe.

Lifecycle (derived, not stored):

    candidate → validated → activated → verified

There is no persistent per-decision lifecycle state. Truth is derived from
repository evidence:

- a decision is an activation candidate iff the canonical assessment classifies
  it ``mneme_ready`` (active, protection-relevant, unprotected);
- the proposed protection is the canonical deterministic typed rule
  (``propose_literal_rule``) — no new rule language, no model involvement;
- activation is an explicit user action that installs exactly that typed rule
  into the decision record of ``project_memory.json``, which is the same
  artifact the existing enforcement path (``mneme check``, hooks) enforces;
- verification re-runs the canonical assessment against the repository from
  disk. Activation is reported verified only when that independent
  assessment observes Protected.

Core invariant:

    activation requested + no observable enforcement evidence
    = decision remains NOT Protected
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from mneme.decision_retriever import ScoredDecision
from mneme.enforcer import (
    ArchitectureProtectionReport,
    ProtectionDecisionReport,
    ProtectionTier,
    assess_protection,
    check_prompt,
    generate_protection_report,
    propose_literal_rule,
)
from mneme.decision_index_persistence import (
    DecisionIndexPersistenceError,
    LegacyDecisionsWriteRefused,
    append_protection_binding,
    load_persisted_decision_index,
    rebuild_compatibility_snapshot,
    refuse_legacy_decisions_write,
    verify_compatibility_snapshot,
)
from mneme.memory_store import MemoryStore
from mneme.path_selectors import SelectorOutcome, policy_root
from mneme.rule_matcher import literal_in_text
from mneme.schemas import Decision, Rule
from mneme.setup import mneme_version
from mneme.setup_state import (
    ACTIVATION_SCHEMA,
    STATE_ACTIVE,
    STATE_SETUP,
    ActivationRecord,
    ActivationStateError,
    ConcurrentModificationError,
    atomic_write_json,
    utc_now,
)

ACTIVATION_RESULT = Literal[
    "verified",
    "already_protected",
    "verification_failed",
    "validation_failed",
    "not_eligible",
]

VALIDATION_STATUS = Literal["valid", "invalid", "unsupported"]

# Frozen enforcement behavior of the activation-ready rule type, for display.
ENFORCEMENT_BEHAVIOR = (
    "FORBID_LITERAL fails on an exact case-sensitive match, enforced "
    "independently of retrieval score; canonical policy sources are exempt "
    "(ADR-019/ADR-020)"
)

# Conservative boundary: M1.4 activates only the guardrail shape the frozen
# Mneme-ready classification proposes (a global FORBID_LITERAL token). The
# canonical assessment never proposes a scoped rule today; anything else is
# refused rather than guessed at.
_ACTIVATION_RULE_TYPE = "FORBID_LITERAL"


class ProtectionError(Exception):
    """A pre-execution protection failure. No filesystem mutation occurred."""


# ── Loading ──────────────────────────────────────────────────────────────────


def load_decisions(memory_path: str | Path) -> list[Decision]:
    """Load and validate project memory, failing safely before any write."""
    store = MemoryStore(memory_path)
    try:
        store.load()
    except Exception as exc:
        raise ProtectionError(
            f"memory file {memory_path} failed validation: {exc}"
        ) from exc
    return store.decisions()


def find_decision(decisions: list[Decision], decision_id: str) -> Decision | None:
    """Return the first decision with the given id, or ``None``."""
    return next((d for d in decisions if d.id == decision_id), None)


# ── Candidate discovery (A) ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ProtectionCandidate:
    """One canonically Mneme-ready, currently unprotected decision."""

    decision_id: str
    decision_text: str
    source_path: str
    guardrail: str  # canonical mneme_guardrail string from the assessment
    proposal: Rule  # the deterministic typed rule activation would install


@dataclass(frozen=True)
class CandidateReport:
    """Activation candidates plus the canonical aggregate they derive from."""

    candidates: tuple[ProtectionCandidate, ...]
    report: ArchitectureProtectionReport


def find_candidates(
    decisions: list[Decision],
    repo_root: str | Path | None = None,
) -> CandidateReport:
    """Discover activation candidates via the frozen P1.2 assessment.

    A candidate is an active decision the canonical assessment classifies
    ``mneme_ready``: protection-relevant, currently unprotected, and carrying
    a concrete safe guardrail. Already-Protected, Requires-modelling and
    Guidance decisions are never candidates; superseded/inactive decisions
    never enter the canonical counts. Eligibility is entirely canonical —
    no model or heuristic decides it.
    """
    report = generate_protection_report(decisions, repo_root=repo_root)
    by_id: dict[str, Decision] = {}
    for decision in decisions:
        by_id.setdefault(decision.id, decision)
    candidates: list[ProtectionCandidate] = []
    for item in report.decisions:
        if item.status != "active" or item.protection_tier != "mneme_ready":
            continue
        decision = by_id.get(item.id)
        if decision is None:
            continue
        proposal = propose_literal_rule(decision)
        if proposal is None:
            # Unreachable under frozen semantics (mneme_ready always carries
            # an explicit guardrail), but never present a candidate without
            # a deterministic proposal.
            continue
        candidates.append(ProtectionCandidate(
            decision_id=decision.id,
            decision_text=decision.decision,
            source_path=decision.source_path,
            guardrail=item.mneme_guardrail or f"{proposal.type}: {proposal.value}",
            proposal=proposal,
        ))
    return CandidateReport(candidates=tuple(candidates), report=report)


# ── Eligibility (frozen; shared by validate and activate) ────────────────────


@dataclass(frozen=True)
class Precheck:
    """Canonical activation eligibility for one decision."""

    decision_id: str
    tier: ProtectionTier
    proposal: Rule | None
    eligible: bool
    reason: str


def activation_precheck(
    decision: Decision,
    repo_root: str | Path | None = None,
) -> Precheck:
    """Classify activation eligibility exclusively from frozen semantics."""
    assessment = assess_protection(decision, repo_root=repo_root)
    tier = assessment.protection_tier
    if decision.status != "active":
        return Precheck(
            decision_id=decision.id,
            tier=tier,
            proposal=None,
            eligible=False,
            reason=(
                f"decision status is {decision.status!r}; only active "
                "decisions can be activated"
            ),
        )
    if tier == "protected":
        return Precheck(
            decision_id=decision.id,
            tier=tier,
            proposal=None,
            eligible=False,
            reason="already Protected under the canonical assessment",
        )
    if tier != "mneme_ready":
        return Precheck(
            decision_id=decision.id,
            tier=tier,
            proposal=None,
            eligible=False,
            reason=f"canonical tier is {tier}; not Mneme-ready",
        )
    proposal = propose_literal_rule(decision)
    if proposal is None:
        return Precheck(
            decision_id=decision.id,
            tier=tier,
            proposal=None,
            eligible=False,
            reason="canonical assessment carries no FORBID_LITERAL proposal",
        )
    return Precheck(
        decision_id=decision.id,
        tier=tier,
        proposal=proposal,
        eligible=True,
        reason=f"FORBID_LITERAL: {proposal.value}",
    )


# ── Deterministic validation (C) ─────────────────────────────────────────────


@dataclass(frozen=True)
class ValidationCheck:
    """One deterministic validation probe and its outcome."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ValidationResult:
    """Deterministic outcome of validating one proposed protection."""

    decision_id: str
    status: str  # "valid" | "invalid" | "unsupported"
    checks: tuple[ValidationCheck, ...]
    proposal: Rule


# Fixed benign fixtures for the permitted case; the first one that does not
# contain the forbidden token is used, keeping validation deterministic for
# every token while never exercising the rule under test.
_BENIGN_TEXTS: tuple[str, ...] = (
    "Use an approved internal helper for this work.",
    "Keep the module small and covered by tests.",
    "Wire the logger through the shared facade.",
)


def _prohibited_text(token: str) -> str:
    return f"Use {token} for this component."


def _permitted_text(token: str) -> str | None:
    for text in _BENIGN_TEXTS:
        if not literal_in_text(token, text):
            return text
    return None


def _proposed_violations(
    result,
    decision_id: str,
    token: str,
):
    """Violations attributable specifically to the proposed rule."""
    return [
        v for v in result.violations
        if v.decision_id == decision_id
        and v.kind == "typed_rule"
        and v.rule_type == _ACTIVATION_RULE_TYPE
        and v.rule == token
    ]


def _proposed_traces(result, decision_id: str, index: int, token: str):
    """Applicability traces for the proposed rule inside a check run."""
    return [
        item for item in result.applicability
        if item.decision_id == decision_id
        and item.rule_type == _ACTIVATION_RULE_TYPE
        and item.rule_value == token
        and item.rule_index == index
    ]


def validate_proposal(
    decision: Decision,
    proposal: Rule,
    memory_path: str | Path | None = None,
) -> ValidationResult:
    """Validate a proposed protection mechanically, before activation.

    Reuses the existing enforcement engine (``check_prompt``) on an
    in-memory copy of the decision carrying the proposed rule; nothing is
    written and no protection is enabled. Checks:

    1. the expected prohibited case is detected as a typed FAIL;
    2. an expected permitted case is not blocked by the proposed rule;
    3. intended applicability is respected: an ordinary artifact path is
       enforced and the canonical policy source (the memory file that would
       carry the rule) stays exempt;
    4. unrelated paths are unaffected: permitted content on a different
       artifact path also passes.

    Only the activation-ready shape (a global ``FORBID_LITERAL``, which is
    what frozen Mneme-ready semantics propose) is validated; any other shape
    returns ``unsupported`` rather than invented behavior. No model judges
    anything and the outcome is deterministic.
    """
    if proposal.type != _ACTIVATION_RULE_TYPE or proposal.include_paths is not None:
        return ValidationResult(
            decision_id=decision.id,
            status="unsupported",
            checks=(),
            proposal=proposal,
        )
    policy_memory = memory_path or decision.memory_path
    if not policy_memory:
        return ValidationResult(
            decision_id=decision.id,
            status="unsupported",
            checks=(),
            proposal=proposal,
        )

    token = proposal.value
    prohibited = _prohibited_text(token)
    permitted = _permitted_text(token)
    index = len(decision.rules)
    candidate = replace(decision, rules=[*decision.rules, proposal])
    scored = [ScoredDecision(decision=candidate, score=1.0, matches={})]

    checks: list[ValidationCheck] = []

    # 1 — prohibited case detected.
    result = check_prompt(prohibited, scored, input_path=None)
    fired = bool(_proposed_violations(result, decision.id, token))
    checks.append(ValidationCheck(
        name="prohibited_detected",
        passed=fired,
        detail=(
            f"input containing {token!r} is a typed FAIL"
            if fired
            else f"input containing {token!r} produced no typed violation"
        ),
    ))

    # 2 — permitted case not blocked.
    if permitted is None:
        checks.append(ValidationCheck(
            name="permitted_allowed",
            passed=False,
            detail="no permitted fixture free of the token could be built",
        ))
    else:
        result = check_prompt(permitted, scored, input_path=None)
        blocked = bool(_proposed_violations(result, decision.id, token))
        checks.append(ValidationCheck(
            name="permitted_allowed",
            passed=not blocked,
            detail=(
                f"permitted input containing {token!r} would be blocked"
                if blocked
                else f"permitted input without {token!r} is not blocked"
            ),
        ))

    # 3 — applicability scope respected (artifact enforced, policy source exempt).
    root = policy_root(policy_memory)
    artifact = (root / "src" / "component.py").resolve()
    result = check_prompt(prohibited, scored, input_path=artifact)
    applied = _proposed_traces(result, decision.id, index, token)
    applied_ok = (
        bool(applied)
        and applied[0].outcome == SelectorOutcome.APPLIED
        and bool(_proposed_violations(result, decision.id, token))
    )
    result = check_prompt(prohibited, scored, input_path=policy_memory)
    exempt = _proposed_traces(result, decision.id, index, token)
    exempt_ok = (
        bool(exempt)
        and exempt[0].outcome == SelectorOutcome.EXCLUDED
        and not _proposed_violations(result, decision.id, token)
    )
    checks.append(ValidationCheck(
        name="path_scope_respected",
        passed=applied_ok and exempt_ok,
        detail=(
            f"artifact path enforced={applied_ok}, "
            f"canonical policy source exempt={exempt_ok}"
        ),
    ))

    # 4 — unrelated paths unaffected by the proposed rule.
    if permitted is None:
        checks.append(ValidationCheck(
            name="unrelated_paths_unaffected",
            passed=False,
            detail="no permitted fixture free of the token could be built",
        ))
    else:
        unrelated = (root / "docs" / "notes.md").resolve()
        result = check_prompt(permitted, scored, input_path=unrelated)
        blocked = bool(_proposed_violations(result, decision.id, token))
        traces = _proposed_traces(result, decision.id, index, token)
        applied = bool(traces) and traces[0].outcome == SelectorOutcome.APPLIED
        checks.append(ValidationCheck(
            name="unrelated_paths_unaffected",
            passed=applied and not blocked,
            detail=(
                f"unrelated artifact path enforced={applied}, "
                f"permitted content blocked={blocked}"
            ),
        ))

    status = "valid" if all(c.passed for c in checks) else "invalid"
    return ValidationResult(
        decision_id=decision.id,
        status=status,
        checks=tuple(checks),
        proposal=proposal,
    )


# ── Explicit activation (D) + canonical verification (3) ─────────────────────


@dataclass(frozen=True)
class ActivationOutcome:
    """Result of one explicit activation request.

    ``result`` distinguishes, without faking success:

    - ``verified``            the artifact was installed (now or earlier) and
                              the canonical assessment independently observes
                              Protected from repository evidence;
    - ``already_protected``   the canonical assessment already observed
                              Protected before this call; nothing written;
    - ``verification_failed`` an artifact was written but the canonical
                              assessment did not observe Protected — the
                              decision remains NOT Protected;
    - ``validation_failed``   deterministic validation rejected the proposal;
                              nothing was written;
    - ``not_eligible``        the decision is not an activation candidate.
    """

    decision_id: str
    result: str
    tier: ProtectionTier | None
    verification_tier: ProtectionTier | None
    detail: str
    rule_installed: bool
    proposal: Rule | None
    validation: ValidationResult | None


def _rule_record_matches(record: object, proposal: Rule) -> bool:
    """Whether a raw memory rule record already carries this exact rule."""
    if not isinstance(record, dict):
        return False
    if record.get("type") != proposal.type or record.get("value") != proposal.value:
        return False
    if "include_paths" in record:
        include = record["include_paths"]
        if not isinstance(include, list):
            return False
        if tuple(include) != proposal.include_paths:
            return False
    elif proposal.include_paths is not None:
        return False
    exclude = record.get("exclude_paths", ())
    if not isinstance(exclude, list):
        return False
    return tuple(exclude) == proposal.exclude_paths


def _install_rule(
    memory_path: Path,
    decision_id: str,
    proposal: Rule,
) -> bool:
    """Install the typed rule for one decision in the memory file.

    Canonical memory (a ``decision_index`` section) gets a ``protection``
    rule binding on the decision's active version (ADR-030 §9, D1E2b),
    written with the re-derived compatibility snapshot and the activation
    record in one guarded write. Section-less memory keeps the legacy
    ``decisions[]`` write until D1E5. Either way the read-modify-write
    preserves every other key verbatim. Idempotent: an identical existing
    rule is left alone and no duplicate is created.

    The explicit activation also completes the frozen M1.3 activation-state
    model (``setup`` = no preventive protection, ``active`` = at least one
    preventive protection explicitly enabled): a ``setup``-state record
    transitions to ``active`` via the frozen transition table, and a
    pre-M1.3 memory file without an activation record — which
    ``derive_activation_state`` already interprets as ``setup`` — gains one
    valid record in ``active`` state with ``activated_at`` set. An already
    ``active`` record is left untouched; an unsupported or invalid record is
    refused before any write.

    Returns ``True`` when this call wrote the file, ``False`` when the rule
    was already installed.

    Raises :class:`ProtectionError` before any write on unsafe input.
    """
    source_bytes = Path(memory_path).read_bytes()
    raw = json.loads(source_bytes.decode("utf-8"))
    if isinstance(raw, dict) and "decision_index" in raw:
        return _install_canonical_rule(
            memory_path, raw, source_bytes, decision_id, proposal
        )

    # Section-less memory keeps the legacy write until D1E5 (ADR-030 §1).
    try:
        refuse_legacy_decisions_write(raw, operation="mneme protect activate")
    except LegacyDecisionsWriteRefused as exc:
        raise ProtectionError(str(exc)) from exc
    entries = raw.get("decisions")
    if not isinstance(entries, list):
        raise ProtectionError(
            f"memory file {memory_path} has no decisions[] list"
        )
    index = next(
        (i for i, entry in enumerate(entries)
         if isinstance(entry, dict) and entry.get("id") == decision_id),
        None,
    )
    if index is None:
        raise ProtectionError(
            f"decision {decision_id!r} not found in {memory_path}"
        )
    entry = entries[index]
    existing = entry.get("rules", [])
    if not isinstance(existing, list):
        raise ProtectionError(
            f"decision {decision_id!r} carries a malformed rules list"
        )
    if any(_rule_record_matches(record, proposal) for record in existing):
        return False

    record: dict[str, object] = {
        "type": proposal.type,
        "value": proposal.value,
    }
    if proposal.include_paths is not None:
        record["include_paths"] = list(proposal.include_paths)
    if proposal.exclude_paths:
        record["exclude_paths"] = list(proposal.exclude_paths)
    entry["rules"] = [*existing, record]

    _activate_project(raw, memory_path)
    atomic_write_json(memory_path, raw)
    return True


def _install_canonical_rule(
    memory_path: Path,
    raw: dict,
    source_bytes: bytes,
    decision_id: str,
    proposal: Rule,
) -> bool:
    """Canonical protection write (ADR-030 §9, D1E2b).

    One ``protection`` binding on the decision's active version, the
    re-derived compatibility snapshot, and the activation-record transition
    land in a single atomic write. The write is refused if the file
    changed after it was read. An already-bound identical rule is a no-op.
    """
    try:
        # Verify the exact canonical state about to be mutated, including the
        # compatibility snapshot, from these same bytes. A divergent
        # decisions[] is refused here, never repaired by the rebuild below
        # (ADR-030 §1/§12: writers do not repair canonical state).
        index = load_persisted_decision_index(raw["decision_index"])
        verify_compatibility_snapshot(raw, index, Path(memory_path))
        document, _, created = append_protection_binding(
            raw, decision_id=decision_id, rule=proposal
        )
        if not created:
            return False
        document = rebuild_compatibility_snapshot(document)
    except DecisionIndexPersistenceError as exc:
        raise ProtectionError(
            f"cannot install canonical protection for {decision_id!r}: {exc}"
        ) from exc

    _activate_project(document, memory_path)
    try:
        atomic_write_json(memory_path, document, expected_bytes=source_bytes)
    except ConcurrentModificationError as exc:
        raise ProtectionError(str(exc)) from exc
    return True


def _activate_project(raw: dict, memory_path: Path) -> None:
    """Complete the frozen M1.3 activation state model in ``raw``.

    A pre-M1.3 memory file with no activation record is de-facto ``setup``
    state (``derive_activation_state``). Explicitly activating the first
    protection persists one valid record in ``active`` state instead of
    leaving the invalid "Protected decision + setup project" combination.
    An already ``active`` record is left untouched; an unsupported or
    invalid record is refused before any write.
    """
    raw_activation = raw.get("activation")
    if raw_activation is None:
        record_state = ActivationRecord(state=STATE_SETUP)
    else:
        if (
            not isinstance(raw_activation, dict)
            or raw_activation.get("schema") not in (None, ACTIVATION_SCHEMA)
        ):
            raise ProtectionError(
                f"activation record in {memory_path} uses unsupported "
                f"schema {raw_activation.get('schema')!r}; refusing to "
                "modify it"
            )
        try:
            record_state = ActivationRecord.from_dict(raw_activation)
        except ActivationStateError as exc:
            raise ProtectionError(
                f"existing activation record in {memory_path} is invalid: {exc}"
            ) from exc
    if record_state.state != STATE_ACTIVE:
        try:
            record_state.require_transition(STATE_ACTIVE)
        except ActivationStateError as exc:
            raise ProtectionError(
                f"activation record in {memory_path} cannot transition "
                f"from {record_state.state!r} to {STATE_ACTIVE!r}: {exc}"
            ) from exc
        record_state.state = STATE_ACTIVE
        record_state.activated_at = utc_now()
        if raw_activation is None:
            record_state.mneme_version = mneme_version()
        raw["activation"] = record_state.to_dict()


def _verify(
    memory_path: Path,
    decision_id: str,
    repo_root: str | Path | None,
) -> tuple[ProtectionTier | None, str, ProtectionDecisionReport | None]:
    """Re-derive protection truth from the repository via canonical assessment.

    Reloads the memory file from disk and runs the frozen P1.2 assessment —
    the same function ``mneme audit`` uses — over the reloaded decision. This
    is the only accepted proof that activation produced real enforcement
    evidence; the caller's claim never verifies anything by itself.
    """
    store = MemoryStore(memory_path)
    try:
        store.load()
    except Exception as exc:
        return None, f"verification could not reload memory: {exc}", None
    decision = find_decision(store.decisions(), decision_id)
    if decision is None:
        return None, "decision disappeared from memory after activation", None
    assessment = assess_protection(decision, repo_root=repo_root)
    return (
        assessment.protection_tier,
        f"canonical assessment reports {assessment.protection_tier}",
        assessment,
    )


def activate_protection(
    decision_id: str,
    memory_path: str | Path,
    repo_root: str | Path | None = None,
) -> ActivationOutcome:
    """Explicitly activate deterministic protection for one decision.

    Requires an explicit caller decision (the CLI ``protect activate``
    command); nothing else may call this. Eligibility comes exclusively from
    the frozen P1.2 assessment. The proposal is deterministically validated
    first; a failed validation writes nothing. Activation installs the
    canonical typed rule into the decision's memory record — the minimum
    enforcement artifact the existing ``mneme check``/hook path enforces —
    then verification re-runs the canonical assessment against the actual
    repository. Only an independently observed Protected tier is reported
    as verified.
    """
    memory_path = Path(memory_path)
    decisions = load_decisions(memory_path)
    decision = find_decision(decisions, decision_id)
    if decision is None:
        raise ProtectionError(
            f"decision {decision_id!r} not found in {memory_path}"
        )
    precheck = activation_precheck(decision, repo_root=repo_root)
    if not precheck.eligible:
        if precheck.tier == "protected":
            return ActivationOutcome(
                decision_id=decision.id,
                result="already_protected",
                tier=precheck.tier,
                verification_tier=precheck.tier,
                detail=precheck.reason,
                rule_installed=False,
                proposal=None,
                validation=None,
            )
        return ActivationOutcome(
            decision_id=decision.id,
            result="not_eligible",
            tier=precheck.tier,
            verification_tier=None,
            detail=precheck.reason,
            rule_installed=False,
            proposal=None,
            validation=None,
        )

    validation = validate_proposal(decision, precheck.proposal)
    if validation.status != "valid":
        failed = [c.name for c in validation.checks if not c.passed]
        return ActivationOutcome(
            decision_id=decision.id,
            result="validation_failed",
            tier=precheck.tier,
            verification_tier=None,
            detail=(
                "deterministic validation failed: " + ", ".join(failed)
            ),
            rule_installed=False,
            proposal=precheck.proposal,
            validation=validation,
        )

    installed = _install_rule(memory_path, decision.id, precheck.proposal)
    tier, detail, _assessment = _verify(memory_path, decision.id, repo_root)
    if tier == "protected":
        return ActivationOutcome(
            decision_id=decision.id,
            result="verified",
            tier=precheck.tier,
            verification_tier=tier,
            detail=detail,
            rule_installed=installed,
            proposal=precheck.proposal,
            validation=validation,
        )
    return ActivationOutcome(
        decision_id=decision.id,
        result="verification_failed",
        tier=precheck.tier,
        verification_tier=tier,
        detail=detail,
        rule_installed=installed,
        proposal=precheck.proposal,
        validation=validation,
    )


# ── Status (derived, not stored) ─────────────────────────────────────────────


@dataclass(frozen=True)
class ProtectionStatus:
    """Canonical protection status of one decision, freshly derived."""

    decision_id: str
    decision_text: str
    lifecycle_status: str
    tier: ProtectionTier
    guardrail: str | None
    evidence_confidence: str
    evidence_sources: tuple[str, ...]
    rule_installed: bool
    proposal: Rule | None


def protection_status(
    decision_id: str,
    memory_path: str | Path,
    repo_root: str | Path | None = None,
) -> ProtectionStatus:
    """Report one decision's canonical protection state from repository evidence."""
    decisions = load_decisions(memory_path)
    decision = find_decision(decisions, decision_id)
    if decision is None:
        raise ProtectionError(
            f"decision {decision_id!r} not found in {memory_path}"
        )
    assessment = assess_protection(decision, repo_root=repo_root)
    return ProtectionStatus(
        decision_id=decision.id,
        decision_text=decision.decision,
        lifecycle_status=decision.status,
        tier=assessment.protection_tier,
        guardrail=assessment.mneme_guardrail,
        evidence_confidence=assessment.evidence_confidence,
        evidence_sources=tuple(assessment.evidence_sources),
        rule_installed=any(
            rule.type == _ACTIVATION_RULE_TYPE for rule in decision.rules
        ),
        proposal=(
            propose_literal_rule(decision)
            if assessment.protection_tier == "mneme_ready"
            else None
        ),
    )


__all__ = [
    "ProtectionError",
    "ProtectionCandidate",
    "CandidateReport",
    "find_candidates",
    "Precheck",
    "activation_precheck",
    "ValidationCheck",
    "ValidationResult",
    "validate_proposal",
    "ActivationOutcome",
    "activate_protection",
    "ProtectionStatus",
    "protection_status",
    "load_decisions",
    "find_decision",
    "ENFORCEMENT_BEHAVIOR",
]

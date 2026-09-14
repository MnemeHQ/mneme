"""
decision_index_service.py — Protocol-independent Decision Index service.

Core/application service for non-authoritative decision proposal ingestion
and consumer retrieval (ADR-027 sections 4-6, issues #365/#362). This
module is independent of MCP: no MCP package, MCP types, HTTP, hosted
APIs, or transport schemas are imported or referenced. A future MCP server
is a thin transport adapter over this service (D2B, out of scope here).

Authority boundary:

```text
external transport later (MCP)
        |
        v
DecisionIndexService          <-- this module
        |
        v
DecisionProposal store        <-- mneme.decision_proposal_store
        |
        v  accept via separate Mneme authority action (D2C, not here)
Canonical Decision Index      <-- mneme.decision_index (read-only here)
        |
        v
existing Audit / modelling / rule / enforcement path
```

What this service deliberately does NOT expose (ADR-027 section 7):
``accept``, ``reject`` (as authority mutation), ``activate``, ``supersede``,
``create_exception``, ``submit_trusted_evidence``. Producer submissions
always enter as ``proposed``; proposal states may represent accepted/
rejected because ADR-027 defines them, but no method here causes those
transitions.

Retrieval semantics (D2B0 consumer-read completeness):

* ``search`` is deterministic text/exact-metadata filtering over BOTH
  proposals and canonical decisions. No vectors, embeddings, LLM search,
  or generic semantic infrastructure. Proposal lifecycle status and
  canonical lifecycle status are separate filter domains
  (``proposal_status`` vs ``canonical_lifecycle_status``) and are never
  collapsed into one vocabulary. Result ordering follows existing
  store/index order; search rank has zero enforcement meaning.
* ``applicable_to`` returns retrieval/context hints only. Proposal
  ``scope_hints`` are never ADR-020 ``Rule.include_paths``/``exclude_paths``,
  never Layer 1 rule applicability, and never enforcement authority. Paths
  supplied to ``applicable_to`` are treated as opaque context strings, not
  glob-evaluated against ADR-020 selectors.
* ``trace`` resolves proposal ids AND canonical decision ids (the service
  owns the record-type distinction; the future transport never guesses).
  It returns only lineage actually known. Missing links are reported
  explicitly and are never fabricated: enforcement points are not modelled
  in the current canonical kernel and are reported absent; declared test
  evidence (ADR-024) is returned as declared and is never upgraded to
  trusted/verified (ADR-025).
* Canonical reads go through the existing ``CanonicalArchitectureIndex``
  and never mutate canonical records. No second canonical decision store
  is created.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence

from mneme.decision_index import (
    VALID_LIFECYCLE_STATUSES,
    CanonicalArchitectureIndex,
    CanonicalDecisionRecord,
    CanonicalRuleRecord,
    CanonicalTestEvidence,
)
from mneme.decision_proposal import (
    ORIGIN_AI_GENERATED,
    ORIGIN_HUMAN_AUTHORED,
    ORIGIN_IMPORTED_UNKNOWN,
    PROPOSAL_STATUS_ACCEPTED,
    PROPOSAL_STATUS_PROPOSED,
    PROPOSAL_STATUS_REJECTED,
    DecisionProposal,
    DecisionProposalCandidate,
    DecisionProposalSourceProvenance,
    content_fingerprint_of,
    merge_provenance,
    producer_key_of,
    proposal_id_of,
)
from mneme.decision_proposal_store import DecisionProposalStore

_VALID_ORIGIN_CLASSIFICATIONS = (
    ORIGIN_AI_GENERATED,
    ORIGIN_HUMAN_AUTHORED,
    ORIGIN_IMPORTED_UNKNOWN,
)
# Proposal lifecycle vocabulary (ADR-027) — distinct from the canonical
# decision lifecycle vocabulary (ADR-023). Never interchangeable.
_VALID_PROPOSAL_STATUS_FILTERS = (
    PROPOSAL_STATUS_PROPOSED,
    PROPOSAL_STATUS_ACCEPTED,
    PROPOSAL_STATUS_REJECTED,
)


class DecisionIndexIntegrityError(ValueError):
    """Internal Decision Index integrity failure (consumer trace boundary).

    Raised when the two canonical representations of rule lineage
    disagree: the record's declared ``derived_rule_ids`` versus the rules
    actually stored for that decision. This is an index-integrity failure,
    not an ordinary partial trace, so the trace fails closed instead of
    returning ambiguous ``derived_rules``. Neither side is silently
    repaired. This protects the consumer trace boundary only; it does not
    change enforcement or projection behavior.
    """


def _default_clock() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class ProposeResult:
    """Outcome of one ``propose`` / per-candidate batch submission.

    ``created=False`` means an identical proposal already existed
    (idempotent resend); the existing record is returned unchanged.
    """

    proposal: DecisionProposal
    created: bool


@dataclass(frozen=True)
class DecisionSearchResult:
    """Deterministic search result with explicit lifecycle separation.

    ``proposals`` are non-authoritative proposal records (proposal
    lifecycle vocabulary: proposed/accepted/rejected). ``canonical_decisions``
    are canonical Decision Index records (canonical lifecycle vocabulary:
    active/superseded/deprecated/inactive). The two lists are never merged
    and never share a status field; each keeps its own domain vocabulary.
    Ordering follows existing store insertion order and canonical record
    order respectively. Search rank has zero enforcement meaning.
    """

    proposals: tuple[DecisionProposal, ...] = ()
    canonical_decisions: tuple[CanonicalDecisionRecord, ...] = ()


@dataclass(frozen=True)
class ProposalScopeHintMatch:
    """One proposal matched by scope hints for retrieval context only.

    These hints never become typed-rule applicability (ADR-020); the type
    carries no rule, selector, or enforcement field by construction.
    """

    proposal_id: str
    matched_hints: tuple[str, ...]


@dataclass(frozen=True)
class ScopeHintResult:
    """Result of ``applicable_to``: retrieval hints, visibly separate.

    ``proposal_hint_matches`` are proposal scope hints (retrieval context
    only). ``canonical_scope_matches`` are canonical decisions whose
    ``context_scope`` overlaps the supplied context (ADR-023 section 5:
    decision scope, not rule applicability). No typed rules, no ADR-020
    selectors, and no enforcement authority are returned.
    """

    proposal_hint_matches: tuple[ProposalScopeHintMatch, ...] = ()
    canonical_scope_matches: tuple[CanonicalDecisionRecord, ...] = ()


@dataclass(frozen=True)
class ProposalTrace:
    """Deterministic lineage actually known for one proposal.

    Every link that does not exist is listed explicitly in
    ``missing_links``; a partial trace is valid and nothing is fabricated.
    Enforcement and trusted-evidence links are never representable for a
    proposal (proposals are never enforceable; producer provenance is
    never trusted evidence).
    """

    proposal_id: str
    proposal: DecisionProposal | None
    source_provenance: DecisionProposalSourceProvenance | None
    accepted_decision_id: str | None
    canonical_record: CanonicalDecisionRecord | None
    canonical_derived_rule_ids: tuple[str, ...]
    missing_links: tuple[str, ...]


@dataclass(frozen=True)
class CanonicalDecisionTrace:
    """Deterministic lineage actually known for one canonical decision.

    Exposes only what the canonical kernel actually carries: the record,
    its derived canonical rules (with ADR-020 applicability exactly as
    stored), and its declared test-evidence linkage (ADR-024) exactly as
    stored. Enforcement points are not modelled in the current canonical
    kernel and are reported explicitly as missing; declared evidence is
    never upgraded to trusted/verified (ADR-025). Nothing is fabricated.
    """

    canonical_decision_id: str
    canonical_record: CanonicalDecisionRecord | None
    derived_rules: tuple[CanonicalRuleRecord, ...]
    declared_test_evidence: tuple[CanonicalTestEvidence, ...]
    missing_links: tuple[str, ...]


@dataclass(frozen=True)
class DecisionTraceNotFound:
    """Explicit not-found result for an unresolved trace identifier.

    The identifier resolved to neither a proposal nor a canonical
    decision; its record type is therefore unknown and is never guessed.
    Both domains are reported explicitly as not found in
    ``missing_links``.
    """

    record_id: str
    missing_links: tuple[str, ...]


class DecisionIndexService:
    """Protocol-independent proposal ingestion and retrieval service.

    Args:
        proposal_store: The dedicated proposal store (required).
        canonical_index: Optional existing ``CanonicalArchitectureIndex``
            for canonical reads only. This service never writes to it and
            never creates a second canonical store.
        clock: Injectable clock returning a timestamp string; used only
            for ``proposed_at`` of newly created proposals. Inject a fixed
            clock in tests for deterministic timestamps. ``proposed_at``
            is excluded from proposal identity, so idempotency never
            depends on the clock.
    """

    def __init__(
        self,
        proposal_store: DecisionProposalStore,
        canonical_index: CanonicalArchitectureIndex | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._store = proposal_store
        self._canonical = canonical_index
        self._clock = clock if clock is not None else _default_clock

    # ── Producer operations (non-authoritative) ──────────────────────────

    def propose(
        self,
        candidate: DecisionProposalCandidate,
        shared_provenance: DecisionProposalSourceProvenance | None = None,
    ) -> ProposeResult:
        """Create or idempotently return a proposal.

        The effective provenance is the deterministic merge of the
        candidate's own provenance with ``shared_provenance`` (candidate
        components win). Every producer-created proposal enters as
        ``proposed``: there is no input path to any other status.

        ``proposed_at`` is owned by the service: it comes only from the
        injected clock (``_default_clock`` in production), never from a
        caller argument, so a producer/transport caller cannot assert
        Mneme's proposal creation timestamp.

        Identical source/version/content resends return the existing
        proposal unchanged (with its original ``proposed_at`` and current
        status); changed content or source version creates a new
        candidate while the previous proposal is retained.
        """
        effective = self._effective_candidate(candidate, shared_provenance)
        assert effective.provenance is not None  # guaranteed by _effective_candidate
        proposal_id = proposal_id_of(effective.provenance, effective)
        existing = self._store.get(proposal_id)
        if existing is not None:
            return ProposeResult(proposal=existing, created=False)
        proposal = DecisionProposal(
            proposal_id=proposal_id,
            status=PROPOSAL_STATUS_PROPOSED,
            candidate=effective,
            producer_key=producer_key_of(effective.provenance),
            content_fingerprint=content_fingerprint_of(effective),
            proposed_at=self._clock(),
        )
        stored, created = self._store.add_if_new(proposal)
        return ProposeResult(proposal=stored, created=created)

    def propose_batch(
        self,
        candidates: Sequence[DecisionProposalCandidate],
        shared_provenance: DecisionProposalSourceProvenance | None = None,
    ) -> tuple[ProposeResult, ...]:
        """Submit multiple candidates with per-candidate independence.

        Equivalent semantics are applied independently to each candidate;
        every candidate receives its own proposal identity. Shared
        provenance is normalized deterministically
        (``merge_provenance``). There are no batch acceptance semantics:
        every result is an ordinary, independently reviewable,
        non-enforceable proposal. ``proposed_at`` is service-owned via
        the injected clock, exactly as in ``propose``.
        """
        return tuple(
            self.propose(candidate, shared_provenance)
            for candidate in candidates
        )

    def _effective_candidate(
        self,
        candidate: DecisionProposalCandidate,
        shared_provenance: DecisionProposalSourceProvenance | None,
    ) -> DecisionProposalCandidate:
        provenance = merge_provenance(candidate.provenance, shared_provenance)
        if provenance is None:
            raise ValueError(
                "proposal requires provenance: supply candidate.provenance "
                "or shared_provenance"
            )
        if candidate.provenance is provenance:
            return candidate
        return dataclasses.replace(candidate, provenance=provenance)

    # ── Retrieval operations ─────────────────────────────────────────────

    def get(self, record_id: str) -> DecisionProposal | CanonicalDecisionRecord | None:
        """Read a proposal or a canonical decision by stable id.

        Proposals come from the proposal store; canonical decisions are
        read through the existing canonical kernel supplied at
        construction. No second canonical decision store is created and
        canonical records are never mutated.
        """
        proposal = self._store.get(record_id)
        if proposal is not None:
            return proposal
        if self._canonical is not None:
            for record in self._canonical.records:
                if record.decision_id == record_id:
                    return record
        return None

    def search(
        self,
        query: str = "",
        proposal_status: str | None = None,
        canonical_lifecycle_status: str | None = None,
        producer_name: str | None = None,
        source_reference: str | None = None,
        origin_classification: str | None = None,
    ) -> DecisionSearchResult:
        """Deterministic text/exact-metadata search over both domains.

        ``query`` is a case-insensitive substring match. For proposals it
        covers title, statement, rationale, source reference, repository
        locator, scope hints, and related decision ids. For canonical
        decisions it covers decision id, statement, rationale, context
        scope, targets, constraints, anti-patterns, and source-evidence
        locators. No new canonical data is invented. An empty query
        matches everything.

        Filters are exact matches. ``proposal_status`` validates against
        the proposal lifecycle vocabulary (proposed/accepted/rejected);
        ``canonical_lifecycle_status`` validates against the canonical
        lifecycle vocabulary (active/superseded/deprecated/inactive). The
        two vocabularies are distinct domains and never interchangeable.

        Results follow existing store insertion order and canonical record
        order respectively. Deterministic, dependency-free: no vectors,
        embeddings, LLM search, or semantic infrastructure. Search rank
        has zero enforcement meaning.
        """
        if proposal_status is not None and (
            proposal_status not in _VALID_PROPOSAL_STATUS_FILTERS
        ):
            raise ValueError(
                f"proposal_status filter {proposal_status!r} is not one of "
                f"{sorted(_VALID_PROPOSAL_STATUS_FILTERS)} (proposal "
                f"lifecycle vocabulary)"
            )
        if canonical_lifecycle_status is not None and (
            canonical_lifecycle_status not in VALID_LIFECYCLE_STATUSES
        ):
            raise ValueError(
                f"canonical_lifecycle_status filter "
                f"{canonical_lifecycle_status!r} is not one of "
                f"{sorted(VALID_LIFECYCLE_STATUSES)} (canonical lifecycle "
                f"vocabulary)"
            )
        if (
            origin_classification is not None
            and origin_classification not in _VALID_ORIGIN_CLASSIFICATIONS
        ):
            raise ValueError(
                f"origin_classification filter {origin_classification!r} "
                f"is not one of {sorted(_VALID_ORIGIN_CLASSIFICATIONS)}"
            )
        needle = query.lower()
        proposals: list[DecisionProposal] = []
        for proposal in self._store.list_proposals():
            if proposal_status is not None and (
                proposal.status != proposal_status
            ):
                continue
            candidate = proposal.candidate
            assert candidate.provenance is not None
            if producer_name is not None and (
                candidate.provenance.producer_name != producer_name
            ):
                continue
            if source_reference is not None and (
                candidate.provenance.source_reference != source_reference
            ):
                continue
            if origin_classification is not None and (
                candidate.provenance.origin_classification
                != origin_classification
            ):
                continue
            if needle and needle not in self._proposal_haystack(proposal):
                continue
            proposals.append(proposal)
        canonical_decisions: list[CanonicalDecisionRecord] = []
        if self._canonical is not None:
            for record in self._canonical.records:
                if canonical_lifecycle_status is not None and (
                    record.lifecycle_status != canonical_lifecycle_status
                ):
                    continue
                if needle and needle not in self._canonical_haystack(record):
                    continue
                canonical_decisions.append(record)
        return DecisionSearchResult(
            proposals=tuple(proposals),
            canonical_decisions=tuple(canonical_decisions),
        )

    @staticmethod
    def _proposal_haystack(proposal: DecisionProposal) -> str:
        candidate = proposal.candidate
        assert candidate.provenance is not None
        parts = [
            candidate.title,
            candidate.statement,
            candidate.rationale,
            candidate.provenance.source_reference,
            candidate.provenance.repository_locator,
            *candidate.scope_hints,
            *candidate.related_decision_ids,
        ]
        return " ".join(parts).lower()

    @staticmethod
    def _canonical_haystack(record: CanonicalDecisionRecord) -> str:
        parts = [
            record.decision_id,
            record.statement,
            record.rationale,
            *record.context_scope,
            *record.targets,
            *record.constraints,
            *record.anti_patterns,
            *(evidence.source_locator for evidence in record.source_evidence),
        ]
        return " ".join(parts).lower()

    def applicable_to(
        self,
        context: Sequence[str] = (),
        paths: Sequence[str] = (),
    ) -> ScopeHintResult:
        """Return retrieval/context hints for a supplied context.

        ``context`` items are opaque context strings; ``paths`` are treated
        as opaque strings too — they are NOT evaluated with the ADR-020
        path-selector grammar and never produce rule applicability. A
        proposal hint matches a context item when the lowercased hint
        occurs as a substring of the lowercased item (or equals it).
        Canonical decisions match the same way on ``context_scope``.

        The result keeps proposal hints and canonical scope visibly
        separate and contains no rules, selectors, or enforcement data.
        """
        context_items = [item.lower() for item in context]
        context_items.extend(item.lower() for item in paths)
        hint_matches: list[ProposalScopeHintMatch] = []
        canonical_matches: list[CanonicalDecisionRecord] = []
        for proposal in self._store.list_proposals():
            matched = tuple(
                hint
                for hint in proposal.candidate.scope_hints
                if self._hint_matches(hint, context_items)
            )
            if matched:
                hint_matches.append(ProposalScopeHintMatch(
                    proposal_id=proposal.proposal_id,
                    matched_hints=matched,
                ))
        if self._canonical is not None:
            for record in self._canonical.records:
                if any(
                    self._hint_matches(scope, context_items)
                    for scope in record.context_scope
                ):
                    canonical_matches.append(record)
        return ScopeHintResult(
            proposal_hint_matches=tuple(hint_matches),
            canonical_scope_matches=tuple(canonical_matches),
        )

    @staticmethod
    def _hint_matches(hint: str, context_items: list[str]) -> bool:
        lowered = hint.lower()
        return any(lowered in item for item in context_items)

    def trace(
        self, record_id: str
    ) -> ProposalTrace | CanonicalDecisionTrace | DecisionTraceNotFound:
        """Return the deterministic lineage actually known for a record.

        The service owns the record-type distinction: it resolves
        ``record_id`` as a proposal id first, then as a canonical decision
        id; the future transport never determines the type itself.
        Unresolved ids return ``DecisionTraceNotFound`` — the identifier
        stays type-unknown and is never classified into the proposal or
        canonical domain (fail closed, deterministic).

        Proposal trace chain: proposal -> source provenance -> accepted
        canonical id (if the proposal was accepted by the separate Mneme
        authority action) -> canonical record -> canonical derived rule
        ids (if they exist). Unaccepted proposals explicitly show missing
        canonical/rule/enforcement links.

        Canonical trace chain: canonical decision -> derived canonical
        rules -> rule applicability exactly as stored (ADR-020 data) ->
        declared test-evidence linkage exactly as stored (ADR-024,
        declared only, never trusted/verified per ADR-025). Enforcement
        points are not modelled in the current canonical kernel and are
        reported explicitly as missing. Nothing is fabricated.

        A disagreement between the canonical record's declared
        ``derived_rule_ids`` and the rules actually stored for that
        decision is an internal index-integrity failure and raises
        ``DecisionIndexIntegrityError`` (fail closed) instead of
        returning ambiguous lineage.
        """
        proposal = self._store.get(record_id)
        if proposal is not None:
            return self._trace_proposal(proposal)
        if self._canonical is not None:
            for record in self._canonical.records:
                if record.decision_id == record_id:
                    return self._trace_canonical(record)
        return DecisionTraceNotFound(
            record_id=record_id,
            missing_links=(
                f"record: not found ({record_id!r} is neither a proposal id "
                "nor a canonical decision id)",
                "proposal: not found",
                "canonical_decision: not found",
                "record_type: unknown (no proposal/canonical classification "
                "is asserted for an unresolved identifier)",
            ),
        )

    def _trace_proposal(self, proposal: DecisionProposal) -> ProposalTrace:
        missing: list[str] = []
        accepted_id = proposal.accepted_decision_id
        canonical_record: CanonicalDecisionRecord | None = None
        derived_rule_ids: tuple[str, ...] = ()
        if accepted_id is None:
            missing.append("accepted_decision_id: absent (proposal not accepted)")
            missing.append("canonical_record: absent (proposal not accepted)")
            missing.append("derived_rules: absent")
        elif self._canonical is None:
            missing.append(
                f"canonical_record: accepted_decision_id {accepted_id!r} "
                "cannot be resolved (no canonical index supplied)"
            )
        else:
            for record in self._canonical.records:
                if record.decision_id == accepted_id:
                    canonical_record = record
                    break
            if canonical_record is None:
                missing.append(
                    f"canonical_record: accepted_decision_id {accepted_id!r} "
                    "not found in canonical index"
                )
            else:
                derived_rule_ids = canonical_record.derived_rule_ids
                if not derived_rule_ids:
                    missing.append(
                        "derived_rules: none recorded for canonical decision"
                    )
        missing.append(
            "enforcement_links: absent (proposals are never enforceable)"
        )
        missing.append(
            "trusted_evidence: absent (producer provenance is never "
            "trusted evidence)"
        )
        return ProposalTrace(
            proposal_id=proposal.proposal_id,
            proposal=proposal,
            source_provenance=proposal.candidate.provenance,
            accepted_decision_id=accepted_id,
            canonical_record=canonical_record,
            canonical_derived_rule_ids=derived_rule_ids,
            missing_links=tuple(missing),
        )

    def _trace_canonical(
        self, record: CanonicalDecisionRecord
    ) -> CanonicalDecisionTrace:
        derived_rules: tuple[CanonicalRuleRecord, ...] = ()
        if self._canonical is not None:
            derived_rules = self._canonical.rules_for_decision(
                record.decision_id
            )
        stored_ids = tuple(rule.rule_id for rule in derived_rules)
        if stored_ids != record.derived_rule_ids:
            raise DecisionIndexIntegrityError(
                f"canonical decision {record.decision_id!r} rule lineage "
                f"integrity failure: record declares derived_rule_ids "
                f"{list(record.derived_rule_ids)} but the canonical index "
                f"stores rules {list(stored_ids)}; the two canonical "
                f"representations must match exactly (ADR-023 section 10)"
            )
        missing: list[str] = []
        if not derived_rules:
            missing.append("derived_rules: none recorded for canonical decision")
        declared_evidence = tuple(record.test_evidence)
        if not declared_evidence:
            missing.append(
                "declared_test_evidence: none declared for canonical decision"
            )
        else:
            missing.append(
                "test_evidence_state: declared only (ADR-024); trusted/"
                "verified execution evidence is a separate ADR-025 concern "
                "and is never inferred from declarations"
            )
        missing.append(
            "enforcement_links: absent (enforcement points are not modelled "
            "in the current canonical kernel)"
        )
        return CanonicalDecisionTrace(
            canonical_decision_id=record.decision_id,
            canonical_record=record,
            derived_rules=derived_rules,
            declared_test_evidence=declared_evidence,
            missing_links=tuple(missing),
        )


__all__ = [
    "CanonicalDecisionTrace",
    "DecisionIndexIntegrityError",
    "DecisionSearchResult",
    "DecisionTraceNotFound",
    "ProposalScopeHintMatch",
    "ProposalTrace",
    "ProposeResult",
    "ScopeHintResult",
    "DecisionIndexService",
]

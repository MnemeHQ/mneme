"""D2A service tests — DecisionIndexService authority boundary (ADR-027).

Proves the D2A invariants: producer submissions always enter ``proposed``,
idempotent identity, append-preserving history, retrieval hints never
become rule applicability, proposals never reach Layer 1 enforcement or
governance projection, canonical reads never mutate canonical records, and
the service carries no MCP/hosted dependency.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from mneme.decision_index import (
    CanonicalArchitectureIndex,
    CanonicalDecisionRecord,
    CanonicalRuleRecord,
    adrs_to_canonical,
)
from mneme.decision_index_service import (
    DecisionIndexService,
    DecisionSearchResult,
    DecisionTraceNotFound,
    ProposalScopeHintMatch,
    ProposalTrace,
    ProposeResult,
    ScopeHintResult,
)
from mneme.decision_proposal import (
    ORIGIN_AI_GENERATED,
    PROPOSAL_STATUS_ACCEPTED,
    PROPOSAL_STATUS_PROPOSED,
    PROPOSAL_STATUS_REJECTED,
    DecisionProposal,
    DecisionProposalCandidate,
    DecisionProposalSourceProvenance,
)
from mneme.decision_proposal_store import (
    InMemoryDecisionProposalStore,
    JsonFileDecisionProposalStore,
)
from mneme.decision_projection import project_canonical_index
from mneme.decision_retriever import DecisionRetriever
from mneme.enforcer import check_prompt
from mneme.schemas import Rule

REPO_ROOT = Path(__file__).resolve().parent.parent
NEW_MODULES = (
    REPO_ROOT / "mneme" / "decision_proposal.py",
    REPO_ROOT / "mneme" / "decision_proposal_store.py",
    REPO_ROOT / "mneme" / "decision_index_service.py",
)

FIXED_TIME = "2026-09-14T12:00:00Z"
LATER_TIME = "2026-09-14T13:00:00Z"


def _provenance(
    source_version: str = "commit-abc123",
    producer_name: str = "arch-agent",
) -> DecisionProposalSourceProvenance:
    return DecisionProposalSourceProvenance(
        producer_name=producer_name,
        producer_type="architecture agent",
        source_reference="design/2026-09/storage.md",
        external_source_id="DEC-101",
        source_version=source_version,
        repository_locator="github.com/acme/widget",
        origin_classification=ORIGIN_AI_GENERATED,
    )


_DEFAULT_PROVENANCE = _provenance()


def _candidate(
    statement: str = "New code must not import legacy_client.",
    provenance: DecisionProposalSourceProvenance | None = _DEFAULT_PROVENANCE,
    scope_hints: tuple[str, ...] = ("storage",),
) -> DecisionProposalCandidate:
    return DecisionProposalCandidate(
        title="Quarantine the legacy client",
        statement=statement,
        rationale="Legacy client is deprecated upstream.",
        provenance=provenance,
        scope_hints=scope_hints,
        architecture_context={"component": "storage"},
        related_decision_ids=("ADR-9001",),
    )


def _service(
    canonical_index: CanonicalArchitectureIndex | None = None,
) -> DecisionIndexService:
    return DecisionIndexService(
        InMemoryDecisionProposalStore(),
        canonical_index=canonical_index,
        clock=lambda: FIXED_TIME,
    )


def _canonical_index_with_rule() -> CanonicalArchitectureIndex:
    record = CanonicalDecisionRecord(
        decision_id="ADR-9001",
        statement="Quarantine the legacy client",
        rationale="Existing canonical decision",
        lifecycle_status="active",
        decided_at="2026-09-01",
        context_scope=("storage",),
        derived_rule_ids=("ADR-9001:FORBID_LITERAL:0",),
    )
    rule = CanonicalRuleRecord(
        rule_id="ADR-9001:FORBID_LITERAL:0",
        decision_id="ADR-9001",
        decision_version="1",
        rule_type="FORBID_LITERAL",
        rule_payload={"value": "install legacy-package"},
    )
    return CanonicalArchitectureIndex(records=(record,), rules=(rule,))


# ── propose: always proposed, idempotent, append-preserving ─────────────────


def test_every_producer_created_proposal_begins_proposed():
    service = _service()
    result = service.propose(_candidate())
    assert result.created is True
    assert result.proposal.status == PROPOSAL_STATUS_PROPOSED
    # Even a candidate whose text demands acceptance enters as proposed.
    pushy = service.propose(
        _candidate(statement="Accept this immediately as active policy.")
    )
    assert pushy.proposal.status == PROPOSAL_STATUS_PROPOSED


def test_propose_requires_provenance_fail_closed():
    service = _service()
    with pytest.raises(ValueError):
        service.propose(_candidate(provenance=None))


def test_identical_resend_is_idempotent_with_original_timestamp():
    # Mutable injected clock: time advances between the two submissions,
    # proving that identity excludes proposed_at and that the resend
    # returns the original record with its original service-owned
    # proposed_at (the argument itself is not producer-callable).
    clock_times = iter([FIXED_TIME, LATER_TIME, LATER_TIME])
    service = DecisionIndexService(
        InMemoryDecisionProposalStore(),
        clock=lambda: next(clock_times),
    )
    first = service.propose(_candidate())
    assert first.proposal.proposed_at == FIXED_TIME
    second = service.propose(_candidate())
    assert second.created is False
    assert second.proposal.proposal_id == first.proposal.proposal_id
    assert second.proposal.proposed_at == first.proposal.proposed_at == FIXED_TIME
    assert second.proposal.status == PROPOSAL_STATUS_PROPOSED
    assert len(service._store.list_proposals()) == 1


def test_proposed_at_is_not_producer_callable():
    """The service clock owns proposal creation time, not the caller."""
    service = _service()
    with pytest.raises(TypeError):
        service.propose(_candidate(), proposed_at=FIXED_TIME)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        service.propose_batch(  # type: ignore[call-arg]
            (_candidate(),), proposed_at=FIXED_TIME
        )
    # The only timestamp source is the injected/default clock.
    result = service.propose(_candidate())
    assert result.proposal.proposed_at == FIXED_TIME


def test_changed_content_preserves_previous_and_creates_new_candidate():
    service = _service()
    first = service.propose(_candidate())
    second = service.propose(
        _candidate(statement="New code must not import legacy_client_v2.")
    )
    assert second.created is True
    assert second.proposal.proposal_id != first.proposal.proposal_id
    proposals = service._store.list_proposals()
    assert [p.proposal_id for p in proposals] == [
        first.proposal.proposal_id, second.proposal.proposal_id,
    ], "previous proposal must be retained, never overwritten"


def test_changed_source_version_preserves_previous_and_creates_new_candidate():
    service = _service()
    first = service.propose(_candidate())
    second = service.propose(_candidate(provenance=_provenance(
        source_version="commit-def456"
    )))
    assert second.created is True
    assert second.proposal.proposal_id != first.proposal.proposal_id
    assert len(service._store.list_proposals()) == 2
    assert service._store.get(first.proposal.proposal_id) == first.proposal


def test_propose_batch_is_independent_per_candidate():
    service = _service()
    shared = DecisionProposalSourceProvenance(
        producer_name="arch-agent",
        producer_type="architecture agent",
        source_reference="design/2026-09/review.md",
        origin_classification=ORIGIN_AI_GENERATED,
    )
    results = service.propose_batch(
        (
            _candidate(provenance=None),
            _candidate(
                statement="Second candidate statement.",
                provenance=DecisionProposalSourceProvenance(
                    producer_name="arch-agent",
                    producer_type="architecture agent",
                    source_reference="design/2026-09/review.md",
                    external_source_id="DEC-202",
                    origin_classification=ORIGIN_AI_GENERATED,
                ),
            ),
        ),
        shared_provenance=shared,
    )
    assert len(results) == 2
    assert all(r.created for r in results)
    assert all(
        r.proposal.status == PROPOSAL_STATUS_PROPOSED for r in results
    ), "no batch acceptance semantics"
    ids = {r.proposal.proposal_id for r in results}
    assert len(ids) == 2, "every candidate has its own proposal identity"
    # Shared provenance filled the absent external id deterministically.
    assert results[0].proposal.candidate.provenance == shared
    # Candidate's own external id wins over the shared default.
    assert results[1].proposal.candidate.provenance.external_source_id == "DEC-202"


def test_propose_batch_reuses_idempotency_per_candidate():
    service = _service()
    shared = _provenance()
    first = service.propose_batch((_candidate(provenance=None),), shared)
    second = service.propose_batch((_candidate(provenance=None),), shared)
    assert second[0].created is False
    assert second[0].proposal.proposal_id == first[0].proposal.proposal_id


# ── get / search / applicable_to ────────────────────────────────────────────


def test_get_reads_proposals_and_canonical_decisions_without_second_store():
    canonical = _canonical_index_with_rule()
    service = _service(canonical_index=canonical)
    results = service.propose_batch(
        (_candidate(), _candidate(statement="Other candidate."))
    )
    proposal = results[0]
    assert service.get(proposal.proposal.proposal_id) == proposal.proposal
    assert service.get("ADR-9001") == canonical.records[0]
    assert service.get("dprop-" + "f" * 32) is None
    assert service.get("ADR-unknown") is None


def test_search_is_deterministic_text_and_metadata_filtering():
    service = _service()
    service.propose_batch(
        (
            _candidate(),
            _candidate(statement="Event schema versioning policy."),
        )
    )
    hits = service.search("legacy_client")
    assert len(hits.proposals) == 1
    assert hits.proposals[0].candidate.statement.startswith("New code")
    assert hits.canonical_decisions == ()
    assert service.search().proposals == service._store.list_proposals()
    assert service.search(
        proposal_status=PROPOSAL_STATUS_PROPOSED
    ).proposals == service._store.list_proposals()
    assert service.search(proposal_status=PROPOSAL_STATUS_ACCEPTED) == (
        DecisionSearchResult()
    )
    assert service.search(producer_name="arch-agent").proposals == (
        service._store.list_proposals()
    )
    assert service.search(producer_name="other") == DecisionSearchResult()
    with pytest.raises(ValueError):
        service.search(proposal_status="bogus")


def test_applicable_to_returns_retrieval_hints_only():
    canonical = _canonical_index_with_rule()
    service = _service(canonical_index=canonical)
    service.propose(_candidate(scope_hints=("storage", "replication")))
    result = service.applicable_to(context=("storage layer design",))
    assert isinstance(result, ScopeHintResult)
    [hint_match] = result.proposal_hint_matches
    assert isinstance(hint_match, ProposalScopeHintMatch)
    assert hint_match.matched_hints == ("storage",)
    [canonical_match] = result.canonical_scope_matches
    assert canonical_match.decision_id == "ADR-9001"
    # The result type carries no rule/applicability/enforcement fields.
    result_fields = {field.name for field in ScopeHintResult.__dataclass_fields__.values()}
    match_fields = {
        field.name for field in ProposalScopeHintMatch.__dataclass_fields__.values()
    }
    forbidden = {"rules", "include_paths", "exclude_paths", "applicability",
                 "enforcement", "rule_ids"}
    assert not forbidden & result_fields
    assert not forbidden & match_fields


def test_scope_hints_never_become_rule_applicability():
    canonical = _canonical_index_with_rule()
    service = _service(canonical_index=canonical)
    service.propose(_candidate(scope_hints=("src/api/**",)))
    # The canonical rule's ADR-020 applicability is untouched.
    [rule] = canonical.rules
    assert rule.applicability == {}
    # Path-like hints are treated as opaque context strings, NOT evaluated
    # with the ADR-020 selector grammar: "src/api/**" does not glob-match.
    result = service.applicable_to(paths=("src/api/handler.py",))
    assert result.proposal_hint_matches == (), (
        "scope hints must not acquire ADR-020 glob semantics"
    )
    assert not hasattr(result, "rules")
    assert not hasattr(result, "applicability")


# ── trace: partial lineage, explicit absence ────────────────────────────────


def test_trace_of_proposed_proposal_reports_missing_links_explicitly():
    service = _service(canonical_index=_canonical_index_with_rule())
    result = service.propose(_candidate())
    trace = service.trace(result.proposal.proposal_id)
    assert isinstance(trace, ProposalTrace)
    assert trace.proposal == result.proposal
    assert trace.source_provenance == result.proposal.candidate.provenance
    assert trace.accepted_decision_id is None
    assert trace.canonical_record is None
    assert trace.canonical_derived_rule_ids == ()
    joined = "\n".join(trace.missing_links)
    assert "accepted_decision_id: absent" in joined
    assert "canonical_record: absent" in joined
    assert "derived_rules" in joined
    assert "enforcement_links: absent" in joined
    assert "trusted_evidence: absent" in joined


def test_trace_of_unknown_proposal_is_explicit():
    trace = _service().trace("dprop-" + "f" * 32)
    assert isinstance(trace, DecisionTraceNotFound)
    assert not isinstance(trace, ProposalTrace)
    assert "proposal: not found" in trace.missing_links
    assert "canonical_decision: not found" in trace.missing_links


def test_trace_of_accepted_fixture_resolves_canonical_lineage():
    """Accepted state exists in the model (ADR-027) but only via fixtures.

    D2A provides no producer path to it; this fixture is constructed
    directly to prove the trace chain when acceptance HAS happened.
    """
    canonical = _canonical_index_with_rule()
    service = _service(canonical_index=canonical)
    result = service.propose(_candidate())
    accepted = DecisionProposal(
        proposal_id="dprop-" + "b" * 32,
        status=PROPOSAL_STATUS_ACCEPTED,
        candidate=result.proposal.candidate,
        producer_key=result.proposal.producer_key,
        content_fingerprint=result.proposal.content_fingerprint,
        proposed_at=result.proposal.proposed_at,
        accepted_decision_id="ADR-9001",
    )
    service._store.add_if_new(accepted)
    trace = service.trace(accepted.proposal_id)
    assert trace.accepted_decision_id == "ADR-9001"
    assert trace.canonical_record == canonical.records[0]
    assert trace.canonical_derived_rule_ids == ("ADR-9001:FORBID_LITERAL:0",)
    joined = "\n".join(trace.missing_links)
    assert "canonical_record" not in joined
    assert "derived_rules" not in joined
    assert "enforcement_links: absent" in joined, (
        "enforcement points are not modelled for the canonical kernel; "
        "the trace must not fabricate them"
    )


def test_trace_with_unresolvable_accepted_id_reports_absence():
    canonical = _canonical_index_with_rule()
    service = _service(canonical_index=canonical)
    result = service.propose(_candidate())
    accepted = DecisionProposal(
        proposal_id="dprop-" + "c" * 32,
        status=PROPOSAL_STATUS_ACCEPTED,
        candidate=result.proposal.candidate,
        producer_key=result.proposal.producer_key,
        content_fingerprint=result.proposal.content_fingerprint,
        proposed_at=result.proposal.proposed_at,
        accepted_decision_id="ADR-does-not-exist",
    )
    service._store.add_if_new(accepted)
    trace = service.trace(accepted.proposal_id)
    assert trace.canonical_record is None
    assert any(
        "not found in canonical index" in link for link in trace.missing_links
    )


# ── Authority API exclusions ────────────────────────────────────────────────


def test_service_exposes_no_authority_mutation_methods():
    forbidden = {
        "accept", "reject", "activate", "supersede", "create_exception",
        "submit_trusted_evidence", "approve", "deactivate",
    }
    method_names = {
        name for name in dir(DecisionIndexService)
        if not name.startswith("_") and callable(
            getattr(DecisionIndexService, name, None)
        )
    }
    assert not forbidden & method_names


def test_producer_evidence_never_becomes_trusted_evidence():
    service = _service()
    result = service.propose(_candidate())
    proposal = result.proposal
    # The proposal model has no field that could feed CanonicalTestEvidence.
    proposal_fields = {
        field.name for field in DecisionProposal.__dataclass_fields__.values()
    }
    assert "test_evidence" not in proposal_fields
    assert "rules" not in proposal_fields
    # The service offers no path from provenance to trusted evidence.
    for name in dir(service):
        if name.startswith("_"):
            continue
        assert "evidence" not in name.lower()
        assert "trust" not in name.lower()


def test_rejected_and_non_authoritative_fixtures_cannot_project_to_governance():
    """Rejected/accepted proposal states exist but never reach governance.

    Fixtures respect the lifecycle invariants: accepted carries the
    canonical id the authority action would have assigned; rejected
    carries none. Neither can be produced through the producer API.
    """
    service = _service()
    result = service.propose(_candidate())
    fixtures = (
        DecisionProposal(
            proposal_id="dprop-" + "d" * 32,
            status=PROPOSAL_STATUS_REJECTED,
            candidate=result.proposal.candidate,
            producer_key=result.proposal.producer_key,
            content_fingerprint=result.proposal.content_fingerprint,
            proposed_at=result.proposal.proposed_at,
        ),
        DecisionProposal(
            proposal_id="dprop-" + "e" * 32,
            status=PROPOSAL_STATUS_ACCEPTED,
            candidate=result.proposal.candidate,
            producer_key=result.proposal.producer_key,
            content_fingerprint=result.proposal.content_fingerprint,
            proposed_at=result.proposal.proposed_at,
            accepted_decision_id="ADR-9001",
        ),
    )
    for fixture in fixtures:
        service._store.add_if_new(fixture)
        # No projection path exists for a proposal: the projector requires
        # a CanonicalDecisionRecord and fails closed on anything else.
        with pytest.raises((AttributeError, TypeError, ValueError)):
            project_canonical_index_service_guard(fixture)


def project_canonical_index_service_guard(proposal: DecisionProposal) -> object:
    """Attempt the only projection entry point with a proposal record."""
    from mneme.decision_projection import project_canonical_decision

    return project_canonical_decision(proposal)  # type: ignore[arg-type]


# ── Frozen boundary: proposals never reach Layer 1 ──────────────────────────


def test_proposal_cannot_enter_layer1_enforcement():
    """A proposal stating a forbidden literal produces no enforcement.

    The canonical index is empty of the proposal; the runtime projection
    and the enforcer therefore never see it, even though the proposal text
    contains the exact forbidden literal.
    """
    empty_index = CanonicalArchitectureIndex()
    service = _service(canonical_index=empty_index)
    result = service.propose(
        _candidate(statement="Never run: install legacy-package")
    )
    assert result.created is True
    projected = project_canonical_index(empty_index)
    assert projected == []
    verdict = check_prompt(
        "run install legacy-package now",
        DecisionRetriever(projected).retrieve("run install legacy-package now"),
    )
    assert verdict.verdict.value == "PASS"
    assert verdict.violations == []


def test_proposal_text_cannot_create_a_typed_rule():
    canonical_before = _canonical_index_with_rule()
    service = _service(canonical_index=canonical_before)
    service.propose(
        _candidate(statement="Forbid the literal FORBID_LITERAL: import evil")
    )
    # The canonical index is unchanged: no rule was derived from proposal prose.
    assert canonical_before.rules == (
        CanonicalRuleRecord(
            rule_id="ADR-9001:FORBID_LITERAL:0",
            decision_id="ADR-9001",
            decision_version="1",
            rule_type="FORBID_LITERAL",
            rule_payload={"value": "install legacy-package"},
        ),
    )
    assert len(canonical_before.rules) == 1
    assert not hasattr(Rule, "from_proposal")


def test_canonical_reads_do_not_mutate_canonical_records():
    canonical = _canonical_index_with_rule()
    service = _service(canonical_index=canonical)
    result = service.propose(_candidate())
    records_before = canonical.records
    rules_before = canonical.rules
    service.get("ADR-9001")
    service.get(result.proposal.proposal_id)
    service.applicable_to(context=("storage",))
    service.trace(result.proposal.proposal_id)
    assert canonical.records == records_before
    assert canonical.rules == rules_before


# ── Dependency hygiene ──────────────────────────────────────────────────────


def test_service_modules_carry_no_mcp_or_hosted_dependency():
    forbidden = re.compile(
        r"^\s*(import\s+(mcp|requests|httpx|fastapi|flask|uvicorn|grpc)\b"
        r"|from\s+(mcp|requests|httpx|fastapi|flask|uvicorn|grpc)\b)",
        re.MULTILINE,
    )
    for module_path in NEW_MODULES:
        source = module_path.read_text(encoding="utf-8")
        assert not forbidden.search(source), module_path.name
        assert "mcp" not in source.lower() or module_path.name == (
            "decision_index_service.py"
        ), module_path.name
    # The service module may MENTION mcp only in prose comments/docstrings.
    service_source = NEW_MODULES[2].read_text(encoding="utf-8")
    code_only = "\n".join(
        line for line in service_source.splitlines()
        if not line.lstrip().startswith(("#", '"', "*"))
    )
    assert "import mcp" not in code_only
    assert "from mcp" not in code_only


def test_importing_service_does_not_load_mcp_modules():
    import subprocess

    result = subprocess.run(
        [
            sys.executable, "-c",
            "import sys; import mneme.decision_index_service;"
            " assert not [m for m in sys.modules if m == 'mcp' or"
            " m.startswith(('mcp.', 'fastapi', 'uvicorn'))]; print('OK')",
        ],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


# ── Deterministic clock / persistence parity ────────────────────────────────


def test_injected_clock_controls_proposed_at_deterministically():
    service = _service()
    first = service.propose(_candidate())
    second = service.propose(_candidate(statement="Second."))
    assert first.proposal.proposed_at == second.proposal.proposed_at == FIXED_TIME


def test_file_store_service_semantics_match_in_memory(tmp_path: Path):
    canonical = _canonical_index_with_rule()
    file_service = DecisionIndexService(
        JsonFileDecisionProposalStore(tmp_path / "proposals.json"),
        canonical_index=canonical,
        clock=lambda: FIXED_TIME,
    )
    memory_service = _service(canonical_index=canonical)
    for candidate in (
        _candidate(),
        _candidate(statement="Second candidate."),
        _candidate(),  # idempotent resend
    ):
        file_result = file_service.propose(candidate)
        memory_result = memory_service.propose(candidate)
        assert file_result.created == memory_result.created
        assert file_result.proposal.proposal_id == memory_result.proposal.proposal_id
        assert file_result.proposal.status == memory_result.proposal.status
        assert file_result.proposal.proposed_at == memory_result.proposal.proposed_at
    assert (
        [p.proposal_id for p in file_service._store.list_proposals()]
        == [p.proposal_id for p in memory_service._store.list_proposals()]
    )

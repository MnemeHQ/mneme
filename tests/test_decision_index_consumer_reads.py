"""D2B0 consumer-read tests — search/trace completeness (issues #362/#365).

Proves the protocol-independent consumer-read completion: deterministic
search over both proposals and canonical decisions with explicit lifecycle
separation, and trace over proposal ids, canonical decision ids, and
unknown ids with explicit missing links. No MCP, no authority mutation,
no enforcement semantics.
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
    CanonicalSourceEvidence,
    CanonicalTestEvidence,
)
from mneme.decision_index_service import (
    CanonicalDecisionTrace,
    DecisionIndexIntegrityError,
    DecisionIndexService,
    DecisionSearchResult,
    DecisionTraceNotFound,
    ProposalTrace,
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
from mneme.decision_proposal_store import InMemoryDecisionProposalStore

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVICE_MODULE = REPO_ROOT / "mneme" / "decision_index_service.py"

FIXED_TIME = "2026-09-14T12:00:00Z"


def _provenance(
    producer_name: str = "arch-agent",
    source_reference: str = "design/2026-09/storage.md",
) -> DecisionProposalSourceProvenance:
    return DecisionProposalSourceProvenance(
        producer_name=producer_name,
        producer_type="architecture agent",
        source_reference=source_reference,
        external_source_id="DEC-101",
        source_version="commit-abc123",
        repository_locator="github.com/acme/widget",
        origin_classification=ORIGIN_AI_GENERATED,
    )


def _candidate(
    statement: str = "New code must not import legacy_client.",
    provenance: DecisionProposalSourceProvenance | None = None,
    scope_hints: tuple[str, ...] = ("storage",),
) -> DecisionProposalCandidate:
    return DecisionProposalCandidate(
        title="Quarantine the legacy client",
        statement=statement,
        rationale="Legacy client is deprecated upstream.",
        provenance=provenance if provenance is not None else _provenance(),
        scope_hints=scope_hints,
        architecture_context={"component": "storage"},
        related_decision_ids=("ADR-9001",),
    )


def _canonical_rule(
    decision_id: str = "ADR-9001",
    include_paths: tuple[str, ...] | None = ("src/api/**",),
    exclude_paths: tuple[str, ...] = ("src/api/generated/**",),
) -> CanonicalRuleRecord:
    applicability: dict[str, object] = {}
    if include_paths is not None:
        applicability["include_paths"] = list(include_paths)
    if exclude_paths:
        applicability["exclude_paths"] = list(exclude_paths)
    return CanonicalRuleRecord(
        rule_id=f"{decision_id}:FORBID_LITERAL:0",
        decision_id=decision_id,
        decision_version="1",
        rule_type="FORBID_LITERAL",
        rule_payload={"value": "install legacy-package"},
        applicability=applicability,
    )


def _canonical_record(
    decision_id: str = "ADR-9001",
    lifecycle_status: str = "active",
    statement: str = "Quarantine the legacy client",
    with_evidence: bool = False,
) -> CanonicalDecisionRecord:
    return CanonicalDecisionRecord(
        decision_id=decision_id,
        statement=statement,
        rationale="Existing canonical decision",
        lifecycle_status=lifecycle_status,
        decided_at="2026-09-01",
        context_scope=("storage",),
        targets=("src/storage",),
        constraints=("no direct legacy client imports",),
        anti_patterns=("import legacy_client directly",),
        source_evidence=(
            (CanonicalSourceEvidence(
                source_type="adr", source_locator="docs/adr/x.md"
            ),)
        ),
        test_evidence=(
            (CanonicalTestEvidence(selector="tests/test_x.py::test_y", sha="abc123"),)
            if with_evidence
            else ()
        ),
        derived_rule_ids=(f"{decision_id}:FORBID_LITERAL:0",),
    )


def _canonical_index() -> CanonicalArchitectureIndex:
    rule = _canonical_rule()
    return CanonicalArchitectureIndex(
        records=(
            _canonical_record("ADR-9001", "active"),
            _canonical_record(
                "ADR-9002",
                "superseded",
                statement="Legacy postgres policy",
            ),
        ),
        rules=(rule,),
    )


def _service(
    canonical_index: CanonicalArchitectureIndex | None = None,
) -> DecisionIndexService:
    return DecisionIndexService(
        InMemoryDecisionProposalStore(),
        canonical_index=canonical_index,
        clock=lambda: FIXED_TIME,
    )


# ── Search: both domains, lifecycle separation ──────────────────────────────


def test_search_can_return_proposals():
    service = _service()
    service.propose(_candidate())
    result = service.search("legacy_client")
    assert isinstance(result, DecisionSearchResult)
    assert len(result.proposals) == 1
    assert result.canonical_decisions == ()


def test_search_can_return_canonical_decisions():
    service = _service(canonical_index=_canonical_index())
    result = service.search("Quarantine")
    assert isinstance(result, DecisionSearchResult)
    assert result.proposals == ()
    assert [r.decision_id for r in result.canonical_decisions] == ["ADR-9001"]


def test_one_query_can_return_both_domains():
    service = _service(canonical_index=_canonical_index())
    service.propose(_candidate())
    result = service.search("legacy client")
    assert len(result.proposals) == 1
    assert [r.decision_id for r in result.canonical_decisions] == [
        "ADR-9001", "ADR-9002",
    ]


def test_proposal_status_filter_does_not_redefine_canonical_lifecycle():
    service = _service(canonical_index=_canonical_index())
    service.propose(_candidate())
    # Proposal vocabulary filters proposals only; canonical records are
    # unaffected by it.
    result = service.search(proposal_status=PROPOSAL_STATUS_PROPOSED)
    assert len(result.proposals) == 1
    assert len(result.canonical_decisions) == 2, (
        "proposal status must not filter canonical decisions"
    )
    with pytest.raises(ValueError):
        service.search(proposal_status="active"), (
            "'active' is canonical vocabulary, not proposal vocabulary"
        )


def test_canonical_lifecycle_filter_does_not_redefine_proposal_status():
    service = _service(canonical_index=_canonical_index())
    service.propose(_candidate())
    result = service.search(canonical_lifecycle_status="superseded")
    assert [r.decision_id for r in result.canonical_decisions] == ["ADR-9002"]
    assert len(result.proposals) == 1, (
        "canonical lifecycle must not filter proposals"
    )
    with pytest.raises(ValueError):
        service.search(canonical_lifecycle_status="proposed"), (
            "'proposed' is proposal vocabulary, not canonical vocabulary"
        )


def test_search_ordering_is_deterministic():
    canonical = CanonicalArchitectureIndex(
        records=(
            _canonical_record("ADR-9101", "active", statement="Storage policy"),
            _canonical_record("ADR-9102", "active", statement="Storage policy"),
            _canonical_record("ADR-9103", "active", statement="Storage policy"),
        ),
    )
    service = _service(canonical_index=canonical)
    service.propose(_candidate(provenance=_provenance(producer_name="agent-a")))
    service.propose(
        _candidate(
            statement="Second storage statement.",
            provenance=_provenance(producer_name="agent-b"),
        )
    )
    first = service.search("storage")
    second = service.search("storage")
    assert first == second
    assert [r.decision_id for r in first.canonical_decisions] == [
        "ADR-9101", "ADR-9102", "ADR-9103",
    ], "canonical ordering follows canonical record order"
    assert [p.producer_key for p in first.proposals] == [
        p.producer_key for p in service._store.list_proposals()
    ], "proposal ordering follows store insertion order"


def test_canonical_search_does_not_mutate_canonical_records():
    canonical = _canonical_index()
    service = _service(canonical_index=canonical)
    records_before = canonical.records
    rules_before = canonical.rules
    service.search("legacy")
    service.search("quarantine", canonical_lifecycle_status="active")
    service.search("", proposal_status=PROPOSAL_STATUS_PROPOSED)
    assert canonical.records == records_before
    assert canonical.rules == rules_before


def test_proposal_search_does_not_mutate_proposal_records():
    service = _service(canonical_index=_canonical_index())
    result = service.propose(_candidate())
    before = service._store.list_proposals()
    service.search("legacy")
    service.search("", proposal_status=PROPOSAL_STATUS_PROPOSED)
    after = service._store.list_proposals()
    assert before == after
    assert service._store.get(result.proposal.proposal_id) == result.proposal


def test_proposal_search_covers_provenance_and_hints():
    service = _service()
    service.propose(_candidate(
        provenance=_provenance(
            source_reference="catalog/domains/payments/adr-01.mdx"
        ),
        scope_hints=("replication",),
    ))
    assert len(service.search("payments").proposals) == 1
    assert len(service.search("github.com/acme").proposals) == 1, (
        "repository locator is searchable"
    )
    assert len(service.search("ADR-9001").proposals) == 1, (
        "related decision ids are searchable"
    )
    assert len(service.search("replication").proposals) == 1, (
        "scope hints are searchable"
    )


def test_canonical_search_covers_stored_canonical_fields_only():
    canonical = CanonicalArchitectureIndex(
        records=(
            _canonical_record(
                "ADR-9001",
                "active",
                statement="Quarantine",
            ),
        ),
        rules=(_canonical_rule(),),
    )
    service = _service(canonical_index=canonical)
    assert len(service.search("src/storage").canonical_decisions) == 1, (
        "targets searchable"
    )
    assert len(service.search("no direct legacy client").canonical_decisions) == 1, (
        "constraints searchable"
    )
    assert len(service.search("import legacy_client directly").canonical_decisions) == 1, (
        "anti-patterns searchable"
    )
    assert len(service.search("docs/adr/x.md").canonical_decisions) == 1, (
        "source evidence locator searchable"
    )
    # Nothing beyond stored canonical fields is searchable: the rule payload
    # value is NOT part of the canonical record's search surface.
    assert service.search("install legacy-package").canonical_decisions == (), (
        "search must not invent canonical data beyond stored record fields"
    )


# ── Trace: proposal ids, canonical ids, unknown ids ─────────────────────────


def test_trace_of_proposal_id_preserves_d2a_behavior():
    canonical = _canonical_index()
    service = _service(canonical_index=canonical)
    result = service.propose(_candidate())
    trace = service.trace(result.proposal.proposal_id)
    assert isinstance(trace, ProposalTrace)
    assert trace.proposal == result.proposal
    assert trace.source_provenance == result.proposal.candidate.provenance
    assert trace.accepted_decision_id is None
    assert trace.canonical_record is None
    joined = "\n".join(trace.missing_links)
    assert "accepted_decision_id: absent" in joined
    assert "canonical_record: absent" in joined
    assert "enforcement_links: absent" in joined


def test_trace_of_canonical_decision_id_resolves_the_record():
    canonical = _canonical_index()
    service = _service(canonical_index=canonical)
    trace = service.trace("ADR-9001")
    assert isinstance(trace, CanonicalDecisionTrace)
    assert trace.canonical_decision_id == "ADR-9001"
    assert trace.canonical_record == canonical.records[0]


def test_canonical_trace_returns_actual_derived_rules_only():
    canonical = _canonical_index()
    service = _service(canonical_index=canonical)
    trace = service.trace("ADR-9001")
    assert trace.derived_rules == canonical.rules_for_decision("ADR-9001")
    assert [rule.rule_id for rule in trace.derived_rules] == [
        "ADR-9001:FORBID_LITERAL:0",
    ]
    assert trace.canonical_record.derived_rule_ids == (
        "ADR-9001:FORBID_LITERAL:0",
    )


def test_canonical_trace_applicability_is_adr020_data_exactly_as_stored():
    canonical = _canonical_index()
    service = _service(canonical_index=canonical)
    trace = service.trace("ADR-9001")
    [rule] = trace.derived_rules
    assert rule.applicability == {
        "include_paths": ["src/api/**"],
        "exclude_paths": ["src/api/generated/**"],
    }, "applicability must round-trip exactly as stored, unmodified"
    assert rule.rule_type == "FORBID_LITERAL"


def test_canonical_trace_reports_declared_evidence_as_declared_only():
    canonical = CanonicalArchitectureIndex(
        records=(_canonical_record(with_evidence=True),),
        rules=(_canonical_rule(),),
    )
    service = _service(canonical_index=canonical)
    trace = service.trace("ADR-9001")
    assert trace.declared_test_evidence == (
        CanonicalTestEvidence(selector="tests/test_x.py::test_y", sha="abc123"),
    )
    joined = "\n".join(trace.missing_links)
    assert "declared only" in joined
    assert "trusted" in joined and "verified" in joined, (
        "declared evidence must be explicitly not trusted/verified"
    )
    # No field on the trace type claims trusted/verified state.
    trace_fields = {
        field.name for field in CanonicalDecisionTrace.__dataclass_fields__.values()
    }
    assert not any("trusted" in name or "verified" in name for name in trace_fields)


def test_canonical_trace_reports_missing_enforcement_explicitly():
    canonical = _canonical_index()
    service = _service(canonical_index=canonical)
    trace = service.trace("ADR-9001")
    joined = "\n".join(trace.missing_links)
    assert "enforcement_links: absent" in joined, (
        "enforcement points are not modelled in the canonical kernel; "
        "the trace must report them missing, never fabricate them"
    )
    assert not hasattr(trace, "enforcement_points")


def test_canonical_trace_without_evidence_is_explicit():
    record = CanonicalDecisionRecord(
        decision_id="ADR-9501",
        statement="Guidance-only decision",
        lifecycle_status="active",
        decided_at="2026-09-01",
    )
    canonical = CanonicalArchitectureIndex(records=(record,))
    service = _service(canonical_index=canonical)
    trace = service.trace("ADR-9501")
    assert trace.declared_test_evidence == ()
    joined = "\n".join(trace.missing_links)
    assert "declared_test_evidence: none declared" in joined
    assert "enforcement_links: absent" in joined


def test_trace_of_unknown_id_returns_not_found_type():
    """Unknown IDs stay type-unknown: never classified as proposal or
    canonical, never guessed."""
    service = _service(canonical_index=_canonical_index())
    trace = service.trace("does-not-exist")
    assert isinstance(trace, DecisionTraceNotFound)
    assert not isinstance(trace, ProposalTrace), (
        "an unresolved identifier must not be classified into the "
        "proposal domain"
    )
    assert not isinstance(trace, CanonicalDecisionTrace), (
        "an unresolved identifier must not be classified into the "
        "canonical domain"
    )
    assert trace.record_id == "does-not-exist"
    joined = "\n".join(trace.missing_links)
    assert "neither a proposal id nor a canonical decision id" in joined
    assert "proposal: not found" in joined
    assert "canonical_decision: not found" in joined
    assert "record_type: unknown" in joined


def test_trace_of_unknown_id_is_deterministic():
    service = _service(canonical_index=_canonical_index())
    first = service.trace("does-not-exist")
    second = service.trace("does-not-exist")
    assert first == second
    assert isinstance(first, DecisionTraceNotFound)
    # Deterministic across service instances too.
    assert _service(canonical_index=_canonical_index()).trace(
        "does-not-exist"
    ) == first


def test_trace_does_not_mutate_canonical_or_proposal_records():
    canonical = _canonical_index()
    service = _service(canonical_index=canonical)
    result = service.propose(_candidate())
    records_before = canonical.records
    rules_before = canonical.rules
    proposals_before = service._store.list_proposals()
    service.trace("ADR-9001")
    service.trace(result.proposal.proposal_id)
    service.trace("unknown")
    assert canonical.records == records_before
    assert canonical.rules == rules_before
    assert service._store.list_proposals() == proposals_before


# ── Canonical rule-lineage integrity (fail closed) ──────────────────────────


def test_matching_canonical_rule_lineage_traces_normally():
    canonical = _canonical_index()
    service = _service(canonical_index=canonical)
    trace = service.trace("ADR-9001")
    assert isinstance(trace, CanonicalDecisionTrace)
    assert [rule.rule_id for rule in trace.derived_rules] == [
        "ADR-9001:FORBID_LITERAL:0",
    ]
    assert trace.canonical_record.derived_rule_ids == (
        "ADR-9001:FORBID_LITERAL:0",
    )


def test_empty_and_empty_canonical_rule_lineage_remains_valid():
    record = CanonicalDecisionRecord(
        decision_id="ADR-9500",
        statement="Guidance-only decision",
        lifecycle_status="active",
        decided_at="2026-09-01",
    )
    canonical = CanonicalArchitectureIndex(records=(record,))
    service = _service(canonical_index=canonical)
    trace = service.trace("ADR-9500")
    assert isinstance(trace, CanonicalDecisionTrace)
    assert trace.derived_rules == ()
    joined = "\n".join(trace.missing_links)
    assert "derived_rules: none recorded" in joined


def test_declared_ids_without_stored_rules_fail_closed():
    record = CanonicalDecisionRecord(
        decision_id="ADR-9601",
        statement="Declares a rule it does not carry",
        lifecycle_status="active",
        decided_at="2026-09-01",
        derived_rule_ids=("ADR-9601:FORBID_LITERAL:0",),
    )
    canonical = CanonicalArchitectureIndex(records=(record,))
    service = _service(canonical_index=canonical)
    with pytest.raises(DecisionIndexIntegrityError) as exc:
        service.trace("ADR-9601")
    assert "ADR-9601" in str(exc.value)
    assert "derived_rule_ids" in str(exc.value)
    assert isinstance(exc.value, ValueError), (
        "the integrity error is a domain ValueError subclass"
    )


def test_stored_rules_without_declared_ids_fail_closed():
    record = CanonicalDecisionRecord(
        decision_id="ADR-9602",
        statement="Carries rules it does not declare",
        lifecycle_status="active",
        decided_at="2026-09-01",
    )
    canonical = CanonicalArchitectureIndex(
        records=(record,), rules=(_canonical_rule("ADR-9602"),)
    )
    service = _service(canonical_index=canonical)
    with pytest.raises(DecisionIndexIntegrityError) as exc:
        service.trace("ADR-9602")
    assert "ADR-9602" in str(exc.value)
    assert "stores rules" in str(exc.value)


def test_mismatched_rule_id_ordering_fails_closed():
    """Ordering is part of the canonical contract (ADR-023 section 10):
    derived_rule_ids must match the stored derived order exactly."""
    record = CanonicalDecisionRecord(
        decision_id="ADR-9603",
        statement="Declares rules in a different order",
        lifecycle_status="active",
        decided_at="2026-09-01",
        derived_rule_ids=(
            "ADR-9603:FORBID_LITERAL:1",
            "ADR-9603:FORBID_LITERAL:0",
        ),
    )
    rules = tuple(
        CanonicalRuleRecord(
            rule_id=f"ADR-9603:FORBID_LITERAL:{index}",
            decision_id="ADR-9603",
            decision_version="1",
            rule_type="FORBID_LITERAL",
            rule_payload={"value": f"forbidden-literal-{index}"},
        )
        for index in (0, 1)
    )
    canonical = CanonicalArchitectureIndex(records=(record,), rules=rules)
    service = _service(canonical_index=canonical)
    with pytest.raises(DecisionIndexIntegrityError) as exc:
        service.trace("ADR-9603")
    assert "ADR-9603" in str(exc.value)


def test_integrity_error_does_not_return_ambiguous_derived_rules():
    record = CanonicalDecisionRecord(
        decision_id="ADR-9604",
        statement="Declares a rule it does not carry",
        lifecycle_status="active",
        decided_at="2026-09-01",
        derived_rule_ids=("ADR-9604:FORBID_LITERAL:0",),
    )
    canonical = CanonicalArchitectureIndex(records=(record,))
    service = _service(canonical_index=canonical)
    with pytest.raises(DecisionIndexIntegrityError):
        service.trace("ADR-9604")
    # No partial trace escaped: the only way to observe lineage is a
    # successful trace, which the mismatch prevents.
    with pytest.raises(DecisionIndexIntegrityError):
        service.trace("ADR-9604")


# ── Capability/authority boundary ───────────────────────────────────────────


def test_no_authority_mutation_method_was_added():
    forbidden = {
        "accept", "reject", "activate", "deactivate", "supersede",
        "create_exception", "bypass", "submit_trusted_evidence",
        "approve", "promote",
    }
    method_names = {
        name for name in dir(DecisionIndexService)
        if not name.startswith("_") and callable(
            getattr(DecisionIndexService, name, None)
        )
    }
    assert not forbidden & method_names


def test_no_mcp_dependency_exists():
    source = SERVICE_MODULE.read_text(encoding="utf-8")
    forbidden = re.compile(
        r"^\s*(import\s+(mcp|requests|httpx|fastapi|flask|uvicorn|grpc)\b"
        r"|from\s+(mcp|requests|httpx|fastapi|flask|uvicorn|grpc)\b)",
        re.MULTILINE,
    )
    assert not forbidden.search(source)
    code_only = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith(("#", '"', "*"))
    )
    assert "import mcp" not in code_only
    assert "from mcp" not in code_only
    result = subprocess_run_import_check()
    assert result == "OK"


def subprocess_run_import_check() -> str:
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
    return result.stdout.strip()


def test_no_second_canonical_store_or_mutable_exposure():
    service = _service(canonical_index=_canonical_index())
    service.propose(_candidate())
    # Internal state is not exposed as mutable public attributes.
    public_attrs = {
        name for name in vars(service) if not name.startswith("_")
    }
    assert public_attrs == set()
    # Search/trace results are frozen dataclasses: no mutable collections.
    for frozen_type in (DecisionSearchResult, ProposalTrace, CanonicalDecisionTrace):
        assert frozen_type.__dataclass_params__.frozen is True


def test_proposal_idempotency_unchanged_after_read_completeness():
    service = _service(canonical_index=_canonical_index())
    first = service.propose(_candidate())
    second = service.propose(_candidate())
    assert second.created is False
    assert second.proposal.proposal_id == first.proposal.proposal_id
    assert len(service._store.list_proposals()) == 1


def test_rejected_proposals_still_cannot_project_to_governance():
    service = _service(canonical_index=_canonical_index())
    result = service.propose(_candidate())
    rejected = DecisionProposal(
        proposal_id="dprop-" + "d" * 32,
        status=PROPOSAL_STATUS_REJECTED,
        candidate=result.proposal.candidate,
        producer_key=result.proposal.producer_key,
        content_fingerprint=result.proposal.content_fingerprint,
        proposed_at=result.proposal.proposed_at,
    )
    service._store.add_if_new(rejected)
    # Rejected proposals are searchable/traceable as non-authoritative
    # records but have no projection path.
    hits = service.search(proposal_status=PROPOSAL_STATUS_REJECTED)
    assert [p.proposal_id for p in hits.proposals] == [rejected.proposal_id]
    trace = service.trace(rejected.proposal_id)
    assert isinstance(trace, ProposalTrace)
    from mneme.decision_projection import project_canonical_decision

    with pytest.raises((AttributeError, TypeError, ValueError)):
        project_canonical_decision(rejected)  # type: ignore[arg-type]


def test_accepted_fixture_trace_links_to_canonical_where_available():
    canonical = _canonical_index()
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
    assert isinstance(trace, ProposalTrace)
    assert trace.canonical_record == canonical.records[0]
    assert trace.canonical_derived_rule_ids == ("ADR-9001:FORBID_LITERAL:0",)

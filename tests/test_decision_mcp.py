"""D2B Decision Index MCP transport tests (ADR-027, issue #362).

Proves the MCP boundary is a thin capability adapter over
``DecisionIndexService``:

* capability inventory — exactly the six approved tools, no authority
  tool, no alias;
* proposal transport — producer-controlled input only, structural
  rejection of authority fields, idempotent resends, provenance
  round trip, deterministic batch ordering;
* reads — explicit proposal/canonical/not-found typing, separate search
  domains, ADR-020 applicability never reinterpreted, trace union
  serialized with explicit result types, integrity failures fail closed;
* transport/architecture — public-service delegation only, no private
  service state access, no mcp imports inside domain modules, no
  HTTP/hosted dependency, real stdio client/server smoke test.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import Client, MCPError, StdioServerParameters
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from mneme.decision_index import (
    CanonicalArchitectureIndex,
    CanonicalDecisionRecord,
    CanonicalRuleRecord,
    CanonicalTestEvidence,
)
from mneme.decision_mcp import (
    APPROVED_TOOLS,
    TOOL_APPLICABLE_TO,
    TOOL_GET,
    TOOL_PROPOSE,
    TOOL_PROPOSE_BATCH,
    TOOL_SEARCH,
    TOOL_TRACE,
    CandidateInput,
    build_server,
    build_server_from_parts,
    canonical_record_to_transport,
    canonical_trace_to_transport,
    candidate_from_input,
    get_result_to_transport,
    open_proposal_store,
    proposal_to_transport,
    proposal_trace_to_transport,
    provenance_from_input,
    provenance_to_transport,
    rule_to_transport,
    scope_hint_result_to_transport,
    search_result_to_transport,
    serve_stdio,
    declared_evidence_to_transport,
    trace_not_found_to_transport,
    trace_to_transport,
)
from mneme.decision_index_service import (
    CanonicalDecisionTrace,
    DecisionIndexIntegrityError,
    DecisionIndexService,
    DecisionTraceNotFound,
    ProposalTrace,
    ScopeHintResult,
    _VALID_PROPOSAL_STATUS_FILTERS,
)
from mneme.decision_index import VALID_LIFECYCLE_STATUSES
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
    candidate_from_dict,
)
from mneme.decision_proposal_store import InMemoryDecisionProposalStore

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_MODULE = REPO_ROOT / "mneme" / "decision_mcp.py"
SERVICE_MODULE = REPO_ROOT / "mneme" / "decision_index_service.py"
PROPOSAL_MODULE = REPO_ROOT / "mneme" / "decision_proposal.py"
STORE_MODULE = REPO_ROOT / "mneme" / "decision_proposal_store.py"
INDEX_MODULE = REPO_ROOT / "mneme" / "decision_index.py"

FIXED_TIME = "2026-09-14T12:00:00Z"

# Every field the producer must never be able to supply over MCP.
FORBIDDEN_AUTHORITY_FIELDS = (
    "status",
    "proposal_id",
    "producer_key",
    "content_fingerprint",
    "proposed_at",
    "accepted_decision_id",
    "lifecycle_status",
    "canonical_lifecycle_status",
    "rules",
    "rule_applicability",
    "include_paths",
    "exclude_paths",
    "trusted_evidence",
    "enforcement_state",
    "verification_status",
)

FORBIDDEN_AUTHORITY_TOOL_NAMES = (
    "decision.accept",
    "decision.reject",
    "decision.activate",
    "decision.deactivate",
    "decision.supersede",
    "decision.create_exception",
    "decision.bypass",
    "decision.submit_evidence",
    "decision.submit_trusted_evidence",
    "decision.protect",
)


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


def _candidate_input(
    title: str = "Quarantine the legacy client",
    statement: str = "New code must not import legacy_client.",
    **overrides: object,
) -> dict:
    data: dict = {
        "title": title,
        "statement": statement,
        "rationale": "Legacy client is deprecated upstream.",
        "provenance": {
            "producer_name": "arch-agent",
            "producer_type": "architecture agent",
            "source_reference": "design/2026-09/storage.md",
            "external_source_id": "DEC-101",
            "source_version": "commit-abc123",
            "repository_locator": "github.com/acme/widget",
            "origin_classification": ORIGIN_AI_GENERATED,
        },
        "scope_hints": ["storage"],
        "architecture_context": {"component": "storage"},
        "related_decision_ids": ["ADR-9001"],
    }
    data.update(overrides)
    return data


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
    scope: tuple[str, ...] = ("storage",),
) -> CanonicalDecisionRecord:
    return CanonicalDecisionRecord(
        decision_id=decision_id,
        statement=statement,
        rationale="Existing canonical decision",
        lifecycle_status=lifecycle_status,
        decided_at="2026-09-01",
        context_scope=scope,
        targets=("src/storage",),
        constraints=("no direct legacy client imports",),
        anti_patterns=("import legacy_client directly",),
        derived_rule_ids=(f"{decision_id}:FORBID_LITERAL:0",),
    )


def _canonical_index() -> CanonicalArchitectureIndex:
    rule = _canonical_rule()
    return CanonicalArchitectureIndex(
        records=(
            _canonical_record("ADR-9001", "active"),
            _canonical_record(
                "ADR-9002", "superseded", statement="Legacy postgres policy",
                scope=("database",),
            ),
        ),
        rules=(rule,),
    )


def _server() -> object:
    return build_server_from_parts(
        InMemoryDecisionProposalStore(),
        canonical_index=_canonical_index(),
        clock=lambda: FIXED_TIME,
    )


def _call(server: object, name: str, arguments: dict | None = None):
    """In-memory client call through the real protocol layer."""
    async def _run() -> object:
        async with Client(server) as client:  # type: ignore[arg-type]
            return await client.call_tool(name, arguments or {})
    return asyncio.run(_run())


def _mcp_errors_in(exc: BaseException) -> list[MCPError]:
    """Collect MCPError leaves out of (possibly nested) exception groups."""
    if isinstance(exc, BaseExceptionGroup):
        found: list[MCPError] = []
        for child in exc.exceptions:
            found.extend(_mcp_errors_in(child))
        return found
    if isinstance(exc, MCPError):
        return [exc]
    return []


def _expect_protocol_error(server: object, record_id: str) -> MCPError:
    """Call decision.trace and return the fail-closed MCPError it raises.

    Works in both plain asyncio (bare MCPError) and pytest/anyio
    environments (nested single-child ExceptionGroups wrapping it).
    """
    try:
        result = _call(server, TOOL_TRACE, {"record_id": record_id})
    except BaseException as exc:
        errors = _mcp_errors_in(exc)
        if len(errors) == 1:
            return errors[0]
        raise
    raise AssertionError(
        f"expected a fail-closed protocol error, got result: {result!r}"
    )


def _list_tool_names(server: object) -> list[str]:
    async def _run() -> list[str]:
        async with Client(server) as client:  # type: ignore[arg-type]
            result = await client.list_tools()
            return [tool.name for tool in result.tools]
    return asyncio.run(_run())


# ── 1-3: Capability inventory ───────────────────────────────────────────────


def test_exactly_six_approved_tools_exposed():
    names = _list_tool_names(_server())
    assert sorted(names) == sorted(APPROVED_TOOLS)
    assert len(names) == 6
    assert sorted(names) == sorted([
        TOOL_PROPOSE,
        TOOL_PROPOSE_BATCH,
        TOOL_GET,
        TOOL_SEARCH,
        TOOL_APPLICABLE_TO,
        TOOL_TRACE,
    ])


def test_forbidden_authority_tools_are_absent():
    names = set(_list_tool_names(_server()))
    for forbidden in FORBIDDEN_AUTHORITY_TOOL_NAMES:
        assert forbidden not in names


def test_no_alias_exposes_authority_operations():
    # The inventory is a fixed closed set: any alias would have to be an
    # additional registered tool, and none exists beyond the six names.
    names = set(_list_tool_names(_server()))
    assert len(names) == 6
    # No registered name contains an authority keyword fragment.
    for name in names:
        for fragment in (
            "accept", "reject", "activat", "supersede", "exception",
            "bypass", "evidence", "protect",
        ):
            assert fragment not in name, (name, fragment)


def test_approved_inventory_is_the_frozen_contract():
    assert APPROVED_TOOLS == (
        "decision.propose",
        "decision.propose_batch",
        "decision.get",
        "decision.search",
        "decision.applicable_to",
        "decision.trace",
    )


def test_read_tools_declare_read_only_annotations():
    async def _run():
        async with Client(_server()) as client:
            result = await client.list_tools()
            return {t.name: t.annotations for t in result.tools}
    annotations = asyncio.run(_run())
    for name in (TOOL_GET, TOOL_SEARCH, TOOL_APPLICABLE_TO, TOOL_TRACE):
        assert isinstance(annotations[name], ToolAnnotations)
        assert annotations[name].read_only_hint is True
        assert annotations[name].destructive_hint is False
    for name in (TOOL_PROPOSE, TOOL_PROPOSE_BATCH):
        assert annotations[name].read_only_hint is False
        assert annotations[name].idempotent_hint is True


# ── 4-8: Proposal transport authority rejection ─────────────────────────────


def test_valid_propose_creates_proposed_proposal():
    result = _call(_server(), TOOL_PROPOSE, {"candidate": _candidate_input()})
    assert result.is_error is False
    payload = result.structured_content
    assert payload["created"] is True
    assert payload["reused"] is False
    assert payload["proposal"]["proposal_status"] == "proposed"
    assert payload["proposal"]["provenance"]["producer_name"] == "arch-agent"


def test_proposal_input_rejects_status_field():
    candidate = _candidate_input(status="accepted")
    result = _call(_server(), TOOL_PROPOSE, {"candidate": candidate})
    assert result.is_error is True
    assert "status" in result.content[0].text


def test_proposal_input_rejects_accepted_decision_id():
    candidate = _candidate_input(accepted_decision_id="ADR-1")
    result = _call(_server(), TOOL_PROPOSE, {"candidate": candidate})
    assert result.is_error is True
    assert "accepted_decision_id" in result.content[0].text


def test_proposal_input_rejects_proposed_at():
    candidate = _candidate_input(proposed_at="2020-01-01T00:00:00Z")
    result = _call(_server(), TOOL_PROPOSE, {"candidate": candidate})
    assert result.is_error is True
    assert "proposed_at" in result.content[0].text


def test_proposal_input_rejects_typed_rules():
    candidate = _candidate_input(rules=[{"rule_type": "FORBID_LITERAL", "value": "x"}])
    result = _call(_server(), TOOL_PROPOSE, {"candidate": candidate})
    assert result.is_error is True
    assert "rules" in result.content[0].text


def test_proposal_input_rejects_trusted_evidence():
    candidate = _candidate_input(trusted_evidence=[{"selector": "t", "sha": "x"}])
    result = _call(_server(), TOOL_PROPOSE, {"candidate": candidate})
    assert result.is_error is True
    assert "trusted_evidence" in result.content[0].text


def test_every_forbidden_authority_field_is_structurally_rejected():
    for field in FORBIDDEN_AUTHORITY_FIELDS:
        candidate = _candidate_input(**{field: "anything"})
        result = _call(_server(), TOOL_PROPOSE, {"candidate": candidate})
        assert result.is_error is True, field
        assert field in result.content[0].text, field
        assert "silently" not in result.content[0].text


def test_proposed_at_is_service_owned_not_producer_callable():
    result = _call(_server(), TOOL_PROPOSE, {"candidate": _candidate_input()})
    assert result.structured_content["proposal"]["proposed_at"] == FIXED_TIME


def test_identical_resend_is_idempotent_through_mcp():
    server = _server()
    first = _call(server, TOOL_PROPOSE, {"candidate": _candidate_input()})
    second = _call(server, TOOL_PROPOSE, {"candidate": _candidate_input()})
    one = first.structured_content
    two = second.structured_content
    assert one["created"] is True
    assert two["created"] is False
    assert two["reused"] is True
    assert (
        one["proposal"]["proposal_id"] == two["proposal"]["proposal_id"]
    )
    assert one["proposal"] == two["proposal"]


def test_provenance_round_trips_losslessly_through_mcp():
    result = _call(_server(), TOOL_PROPOSE, {"candidate": _candidate_input()})
    payload = result.structured_content["proposal"]
    expected = {
        "producer_name": "arch-agent",
        "producer_type": "architecture agent",
        "source_reference": "design/2026-09/storage.md",
        "external_source_id": "DEC-101",
        "source_version": "commit-abc123",
        "repository_locator": "github.com/acme/widget",
        "origin_classification": ORIGIN_AI_GENERATED,
    }
    assert payload["provenance"] == expected
    assert payload["producer_key"]
    assert payload["content_fingerprint"]


def test_batch_preserves_deterministic_candidate_result_ordering():
    candidates = [
        _candidate_input(title=f"Decision {i}", statement=f"Statement {i}")
        for i in range(4)
    ]
    result = _call(
        _server(),
        TOOL_PROPOSE_BATCH,
        {
            "candidates": candidates,
            "shared_provenance": {
                "producer_name": "batch-producer",
                "producer_type": "document tooling",
                "source_reference": "spec.md",
            },
        },
    )
    payload = result.structured_content
    assert [r["created"] for r in payload["results"]] == [True] * 4
    assert [r["proposal"]["title"] for r in payload["results"]] == [
        "Decision 0", "Decision 1", "Decision 2", "Decision 3",
    ]


def test_batch_shared_provenance_applies_to_every_candidate():
    result = _call(
        _server(),
        TOOL_PROPOSE_BATCH,
        {
            "candidates": [
                {"title": "A", "statement": "S1"},
                {"title": "B", "statement": "S2"},
            ],
            "shared_provenance": {
                "producer_name": "batch-producer",
                "producer_type": "document tooling",
                "source_reference": "spec.md",
            },
        },
    )
    for r in result.structured_content["results"]:
        assert r["proposal"]["provenance"]["producer_name"] == "batch-producer"
        assert r["proposal"]["proposal_status"] == "proposed"


def test_candidate_provenance_wins_over_shared_provenance():
    result = _call(
        _server(),
        TOOL_PROPOSE_BATCH,
        {
            "candidates": [_candidate_input(title="A")],
            "shared_provenance": {
                "producer_name": "batch-producer",
                "producer_type": "document tooling",
                "source_reference": "spec.md",
            },
        },
    )
    # Service merge semantics: the candidate's own provenance wins.
    assert (
        result.structured_content["results"][0]["proposal"]["provenance"]
        ["producer_name"]
        == "arch-agent"
    )


def test_batch_without_provenance_fails_closed():
    result = _call(
        _server(),
        TOOL_PROPOSE_BATCH,
        {"candidates": [_candidate_input(title="A", provenance=None)]},
    )
    assert result.is_error is True


def test_shared_provenance_cannot_carry_authority_fields():
    result = _call(
        _server(),
        TOOL_PROPOSE_BATCH,
        {
            "candidates": [_candidate_input(title="A")],
            "shared_provenance": {
                "producer_name": "p",
                "producer_type": "t",
                "source_reference": "s",
                "status": "accepted",
            },
        },
    )
    assert result.is_error is True
    assert "status" in result.content[0].text


# ── 13-16: Reads ────────────────────────────────────────────────────────────


def test_get_distinguishes_proposal_canonical_and_not_found():
    server = _server()
    proposed = _call(server, TOOL_PROPOSE, {"candidate": _candidate_input()})
    proposal_id = proposed.structured_content["proposal"]["proposal_id"]

    got_proposal = _call(server, TOOL_GET, {"record_id": proposal_id})
    assert got_proposal.structured_content["record_type"] == "proposal"
    assert (
        got_proposal.structured_content["proposal"]["proposal_status"]
        == "proposed"
    )

    got_canonical = _call(server, TOOL_GET, {"record_id": "ADR-9001"})
    assert got_canonical.structured_content["record_type"] == "canonical_decision"
    assert (
        got_canonical.structured_content["canonical_decision"]["lifecycle_status"]
        == "active"
    )

    got_missing = _call(server, TOOL_GET, {"record_id": "does-not-exist"})
    assert got_missing.structured_content["record_type"] == "not_found"
    assert got_missing.structured_content["record_id"] == "does-not-exist"


def test_get_never_flattens_lifecycle_into_one_status():
    server = _server()
    proposed = _call(server, TOOL_PROPOSE, {"candidate": _candidate_input()})
    proposal_payload = proposed.structured_content["proposal"]
    assert "proposal_status" in proposal_payload
    assert "status" not in proposal_payload

    canonical_payload = _call(
        server, TOOL_GET, {"record_id": "ADR-9001"}
    ).structured_content["canonical_decision"]
    assert "lifecycle_status" in canonical_payload
    assert "status" not in canonical_payload
    assert "proposal_status" not in canonical_payload


def test_search_preserves_separate_proposal_and_canonical_domains():
    server = _server()
    _call(server, TOOL_PROPOSE, {"candidate": _candidate_input()})
    result = _call(
        server, TOOL_SEARCH,
        {"query": "legacy client"},
    )
    payload = result.structured_content
    assert len(payload["proposals"]) == 1
    assert [
        c["decision_id"] for c in payload["canonical_decisions"]
    ] == ["ADR-9001", "ADR-9002"]
    # Distinct lifecycle vocabularies per domain.
    assert payload["proposals"][0]["proposal_status"] == "proposed"
    assert (
        payload["canonical_decisions"][0]["lifecycle_status"] == "active"
    )
    assert (
        payload["canonical_decisions"][1]["lifecycle_status"] == "superseded"
    )


def test_lifecycle_filters_remain_distinct_vocabularies():
    server = _server()
    _call(server, TOOL_PROPOSE, {"candidate": _candidate_input()})

    ok_proposal = _call(
        server, TOOL_SEARCH, {"proposal_status": "proposed"}
    )
    assert ok_proposal.is_error is False
    assert len(ok_proposal.structured_content["proposals"]) == 1

    ok_canonical = _call(
        server, TOOL_SEARCH, {"canonical_lifecycle_status": "superseded"}
    )
    assert ok_canonical.is_error is False
    assert [
        c["decision_id"]
        for c in ok_canonical.structured_content["canonical_decisions"]
    ] == ["ADR-9002"]

    # Cross-vocabulary values are rejected by the transport schema.
    cross = _call(server, TOOL_SEARCH, {"proposal_status": "active"})
    assert cross.is_error is True
    cross2 = _call(server, TOOL_SEARCH, {"canonical_lifecycle_status": "accepted"})
    assert cross2.is_error is True


def test_invalid_origin_classification_rejected():
    result = _call(
        _server(), TOOL_SEARCH,
        {"origin_classification": "verified_by_producer"},
    )
    assert result.is_error is True
    assert "origin_classification" in result.content[0].text


def test_applicable_to_does_not_reinterpret_scope_hints_as_adr020():
    server = build_server_from_parts(
        InMemoryDecisionProposalStore(),
        canonical_index=_canonical_index(),
        clock=lambda: FIXED_TIME,
    )
    # Candidate whose scope hint is path-shaped. ADR-020 glob semantics
    # would match src/api/users.py via the hint-as-glob; retrieval hints
    # must not.
    result = _call(
        server, TOOL_PROPOSE,
        {
            "candidate": {
                "title": "Glob-looking hint",
                "statement": "S",
                "provenance": {
                    "producer_name": "p", "producer_type": "t", "source_reference": "s",
                },
                "scope_hints": ["src/api/**"],
            }
        },
    )
    assert result.is_error is False
    applicable = _call(
        server, TOOL_APPLICABLE_TO,
        {"paths": ["src/api/users.py", "src/api/admin.py"]},
    )
    payload = applicable.structured_content
    # ADR-020 glob semantics would have matched both paths; retrieval
    # substring matching must not.
    assert payload["proposal_hint_matches"] == []
    # No rules, selectors, or enforcement data exist in the shape at all.
    flat = json.dumps(payload)
    for forbidden in ("rule_payload", "include_paths", "exclude_paths",
                      "applicability", "rule_id", "enforcement"):
        assert forbidden not in flat, forbidden


def test_applicable_to_is_retrieval_context_only():
    server = build_server_from_parts(
        InMemoryDecisionProposalStore(),
        canonical_index=_canonical_index(),
        clock=lambda: FIXED_TIME,
    )
    _call(
        server, TOOL_PROPOSE,
        {
            "candidate": {
                "title": "T", "statement": "S",
                "provenance": {
                    "producer_name": "p", "producer_type": "t", "source_reference": "s",
                },
                "scope_hints": ["storage layer"],
            }
        },
    )
    applicable = _call(
        server, TOOL_APPLICABLE_TO,
        {"context": ["storage layer in the ingestion service"]},
    )
    payload = applicable.structured_content
    assert len(payload["proposal_hint_matches"]) == 1
    match = payload["proposal_hint_matches"][0]
    assert match["matched_hints"] == ["storage layer"]
    assert set(match.keys()) == {"proposal_id", "matched_hints"}


def test_canonical_scope_matches_carry_no_rule_data():
    result = _call(
        _server(), TOOL_APPLICABLE_TO,
        {"context": ["storage"]},
    )
    payload = result.structured_content
    assert [
        c["decision_id"] for c in payload["canonical_scope_matches"]
    ] == ["ADR-9001"]
    for record in payload["canonical_scope_matches"]:
        # Slim context references only: no rules, no ADR-020 selectors,
        # no enforcement linkage.
        assert set(record.keys()) == {
            "decision_id", "version", "statement",
            "lifecycle_status", "context_scope",
        }


# ── 17-20: Trace serialization and fail-closed integrity ────────────────────


def test_proposal_trace_serializes_with_explicit_result_type():
    server = _server()
    proposed = _call(server, TOOL_PROPOSE, {"candidate": _candidate_input()})
    proposal_id = proposed.structured_content["proposal"]["proposal_id"]
    result = _call(server, TOOL_TRACE, {"record_id": proposal_id})
    payload = result.structured_content
    assert payload["result_type"] == "proposal_trace"
    assert payload["proposal_id"] == proposal_id
    assert payload["proposal"]["proposal_status"] == "proposed"
    assert payload["source_provenance"]["producer_name"] == "arch-agent"
    assert payload["accepted_decision_id"] is None
    assert payload["canonical_record"] is None
    missing = payload["missing_links"]
    assert any("accepted_decision_id" in m for m in missing)
    assert any("enforcement" in m for m in missing)
    assert any("trusted_evidence" in m for m in missing)


def test_canonical_trace_serializes_actual_lineage_only():
    server = build_server_from_parts(
        InMemoryDecisionProposalStore(),
        canonical_index=_canonical_index(),
        clock=lambda: FIXED_TIME,
    )
    result = _call(server, TOOL_TRACE, {"record_id": "ADR-9001"})
    payload = result.structured_content
    assert payload["result_type"] == "canonical_trace"
    assert payload["canonical_decision_id"] == "ADR-9001"
    assert [r["rule_id"] for r in payload["derived_rules"]] == [
        "ADR-9001:FORBID_LITERAL:0",
    ]
    rule = payload["derived_rules"][0]
    # ADR-020 applicability is passed through verbatim.
    assert rule["applicability"] == {
        "include_paths": ["src/api/**"],
        "exclude_paths": ["src/api/generated/**"],
    }
    assert rule["rule_type"] == "FORBID_LITERAL"
    # Declared evidence is declared-only; no trusted/verified label exists.
    assert payload["declared_test_evidence"] == []
    flat = json.dumps(payload)
    assert "trusted" not in flat
    assert "verified" not in flat
    missing = payload["missing_links"]
    assert any("enforcement_links: absent" in m for m in missing)


def test_unresolved_trace_remains_type_unknown():
    server = _server()
    result = _call(server, TOOL_TRACE, {"record_id": "never-proposed-xyz"})
    payload = result.structured_content
    assert payload["result_type"] == "trace_not_found"
    assert payload["record_id"] == "never-proposed-xyz"


def test_unresolved_trace_is_not_proposal_not_found():
    server = _server()
    result = _call(server, TOOL_TRACE, {"record_id": "unresolvable-id"})
    payload = result.structured_content
    assert payload["result_type"] == "trace_not_found"
    # Not a proposal-domain classification: no proposal fields at all.
    assert "proposal" not in payload
    assert "proposal_id" not in payload
    assert any("record_type: unknown" in m for m in payload["missing_links"])


def test_canonical_integrity_mismatch_fails_closed_at_mcp_boundary():
    bad_index = CanonicalArchitectureIndex(
        records=(
            CanonicalDecisionRecord(
                decision_id="ADR-9001",
                derived_rule_ids=("ADR-9001:FORBID_LITERAL:0",),
            ),
        ),
        # The record declares a rule the index does not store.
        rules=(),
    )
    server = build_server_from_parts(
        InMemoryDecisionProposalStore(),
        canonical_index=bad_index,
        clock=lambda: FIXED_TIME,
    )
    raised = _expect_protocol_error(server, "ADR-9001")
    assert isinstance(raised, MCPError)
    assert "integrity" in str(raised).lower()
    assert "ADR-9001" in str(raised)


def test_integrity_failure_is_protocol_error_not_partial_trace():
    bad_index = CanonicalArchitectureIndex(
        records=(
            CanonicalDecisionRecord(
                decision_id="ADR-9001",
                derived_rule_ids=("ADR-9001:FORBID_LITERAL:0",),
            ),
        ),
        rules=(
            CanonicalRuleRecord(
                rule_id="ADR-9001:FORBID_LITERAL:1",  # ordering mismatch
                decision_id="ADR-9001",
                decision_version="1",
                rule_type="FORBID_LITERAL",
                rule_payload={"value": "x"},
            ),
        ),
    )
    server = build_server_from_parts(
        InMemoryDecisionProposalStore(),
        canonical_index=bad_index,
        clock=lambda: FIXED_TIME,
    )
    raised = _expect_protocol_error(server, "ADR-9001")
    assert isinstance(raised, MCPError)


def test_integrity_error_is_distinguishable_from_not_found():
    integrity_server = build_server_from_parts(
        InMemoryDecisionProposalStore(),
        canonical_index=CanonicalArchitectureIndex(
            records=(
                CanonicalDecisionRecord(
                    decision_id="X",
                    derived_rule_ids=("X:FORBID_LITERAL:0",),
                ),
            ),
            rules=(),
        ),
        clock=lambda: FIXED_TIME,
    )
    clean_server = _server()
    raised = _expect_protocol_error(integrity_server, "X")
    assert isinstance(raised, MCPError)
    not_found = _call(clean_server, TOOL_TRACE, {"record_id": "missing"})
    # The integrity failure is a fail-closed protocol error; ordinary
    # not-found is a successful trace_not_found result.
    assert not_found.is_error is False
    assert not_found.structured_content["result_type"] == "trace_not_found"


def test_service_integrity_error_types_are_exported_for_tests():
    # Guards the import used by the fail-closed tests.
    assert issubclass(DecisionIndexIntegrityError, ValueError)


# ── 21-24: Transport/architecture boundary ─────────────────────────────────


def test_tool_handlers_delegate_to_public_service_methods():
    """Source-level: handlers call only public DecisionIndexService methods."""
    source = MCP_MODULE_SOURCE
    for public_method in (
        ".propose(", ".propose_batch(", ".get(", ".search(",
        ".applicable_to(", ".trace(",
    ):
        assert public_method in source, public_method
    # The service is only obtained via build_server DI, never constructed
    # from private state.
    assert "DecisionIndexService(" in source


def test_handlers_do_not_access_private_service_state():
    source = MCP_MODULE_SOURCE
    for forbidden in ("._canonical", "._store", "._clock", ".__dict__"):
        assert forbidden not in source, forbidden


def test_mcp_imports_do_not_leak_into_domain_modules():
    for path in (SERVICE_MODULE, PROPOSAL_MODULE, STORE_MODULE, INDEX_MODULE):
        code = path.read_text(encoding="utf-8")
        code_only = "\n".join(
            line for line in code.splitlines()
            if not line.lstrip().startswith("#")
        )
        assert "import mcp" not in code_only, path
        assert "from mcp" not in code_only, path
        assert "decision_mcp" not in code_only, path


def test_importing_service_does_not_load_mcp_modules():
    script = (
        "import sys; import mneme.decision_index_service;"
        " assert not [m for m in sys.modules if m == 'mcp' or"
        " m.startswith(('mcp.', 'pydantic'))]; print('OK')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=True,
    )
    assert proc.stdout.strip().endswith("OK")


def test_no_http_hosted_or_org_dependency_in_mcp_module():
    source = MCP_MODULE_SOURCE
    for forbidden in (
        "fastapi", "uvicorn", "httpx", "starlette", "streamable_http",
        "Authorization", "rbac", "tenancy", "grpc",
    ):
        assert forbidden not in source.lower(), forbidden
    for word in ("sse", "requests", "remote", "hosted"):
        assert not re.search(rf"\b{word}\b", source.lower()), word


# ── 25-26: Server start + stdio end-to-end smoke test ───────────────────────


def test_stdio_server_starts_and_serves_the_six_tools(tmp_path: Path):
    """Real stdio subprocess end-to-end (test #25/#26)."""
    server_script = tmp_path / "stdio_server.py"
    server_script.write_text(
        "import sys\n"
        "from mneme.decision_mcp import build_server_from_parts\n"
        "from mneme.decision_proposal_store import InMemoryDecisionProposalStore\n"
        "server = build_server_from_parts(InMemoryDecisionProposalStore())\n"
        "server.run()\n",
        encoding="utf-8",
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_script)],
        cwd=str(REPO_ROOT),
        env={"PYTHONPATH": str(REPO_ROOT)},
    )

    async def _run() -> tuple[list[str], object, object]:
        async with Client(params) as client:
            listing = await client.list_tools()
            read_result = await client.call_tool(
                "decision.get", {"record_id": "no-such-record"}
            )
            propose_result = await client.call_tool(
                "decision.propose",
                {
                    "candidate": {
                        "title": "Stdio smoke proposal",
                        "statement": "S",
                        "provenance": {
                            "producer_name": "stdio-smoke",
                            "producer_type": "test harness",
                            "source_reference": "test",
                        },
                    }
                },
            )
            return (
                [tool.name for tool in listing.tools],
                read_result,
                propose_result,
            )

    tool_names, read_result, propose_result = asyncio.run(_run())
    assert sorted(tool_names) == sorted(APPROVED_TOOLS)
    assert read_result.structured_content == {
        "record_type": "not_found",
        "record_id": "no-such-record",
    }
    assert propose_result.is_error is False
    payload = propose_result.structured_content
    assert payload["created"] is True
    assert payload["proposal"]["proposal_status"] == "proposed"
    assert payload["proposal"]["provenance"]["producer_type"] == "test harness"


# ── Serialization determinism ───────────────────────────────────────────────


def test_proposal_serialization_is_explicit_and_deterministic():
    service = DecisionIndexService(
        InMemoryDecisionProposalStore(), clock=lambda: FIXED_TIME,
    )
    proposal = service.propose(candidate_from_input(
        CandidateInput.model_validate(_candidate_input())
    )).proposal
    payload = proposal_to_transport(proposal)
    assert list(payload.keys()) == [
        "proposal_id",
        "proposal_status",
        "title",
        "statement",
        "rationale",
        "provenance",
        "scope_hints",
        "architecture_context",
        "related_decision_ids",
        "producer_key",
        "content_fingerprint",
        "proposed_at",
        "accepted_decision_id",
    ]
    assert json.loads(json.dumps(payload)) == payload


def test_canonical_record_serialization_preserves_ordering():
    payload = canonical_record_to_transport(_canonical_record())
    assert payload["context_scope"] == ["storage"]
    assert payload["targets"] == ["src/storage"]
    assert payload["constraints"] == ["no direct legacy client imports"]
    assert payload["anti_patterns"] == ["import legacy_client directly"]
    assert payload["derived_rule_ids"] == ["ADR-9001:FORBID_LITERAL:0"]
    assert list(payload.keys()) == [
        "decision_id",
        "version",
        "decision_class",
        "statement",
        "rationale",
        "lifecycle_status",
        "owner",
        "decided_at",
        "updated_at",
        "context_scope",
        "targets",
        "constraints",
        "anti_patterns",
        "source_evidence",
        "test_evidence",
        "relationships",
        "derived_rule_ids",
    ]


def test_rule_serialization_passes_applicability_verbatim():
    rule = _canonical_rule()
    payload = rule_to_transport(rule)
    assert payload["applicability"] == {
        "include_paths": ["src/api/**"],
        "exclude_paths": ["src/api/generated/**"],
    }
    assert list(payload.keys()) == [
        "rule_id",
        "decision_id",
        "decision_version",
        "rule_type",
        "rule_payload",
        "applicability",
        "lifecycle_status",
    ]


def test_declared_evidence_serialization_has_no_verification_state():
    payload = declared_evidence_to_transport(
        CanonicalTestEvidence(selector="tests/test_x.py::test_y", sha="abc123")
    )
    assert payload == {
        "selector": "tests/test_x.py::test_y",
        "sha": "abc123",
    }
    assert "verification" not in json.dumps(payload)
    assert "trusted" not in json.dumps(payload)


def test_trace_serializers_preserve_union_types():
    from mneme.decision_index_service import (
        DecisionSearchResult,
        ProposalScopeHintMatch,
    )
    proposal = DecisionIndexService(
        InMemoryDecisionProposalStore(), clock=lambda: FIXED_TIME,
    ).propose(candidate_from_input(
        CandidateInput.model_validate(_candidate_input())
    )).proposal
    proposal_trace = ProposalTrace(
        proposal_id=proposal.proposal_id,
        proposal=proposal,
        source_provenance=proposal.candidate.provenance,
        accepted_decision_id=None,
        canonical_record=None,
        canonical_derived_rule_ids=(),
        missing_links=("accepted_decision_id: absent",),
    )
    assert proposal_trace_to_transport(proposal_trace)["result_type"] == (
        "proposal_trace"
    )

    canonical_trace = CanonicalDecisionTrace(
        canonical_decision_id="ADR-9001",
        canonical_record=_canonical_record(),
        derived_rules=(),
        declared_test_evidence=(),
        missing_links=("derived_rules: none recorded",),
    )
    assert canonical_trace_to_transport(canonical_trace)["result_type"] == (
        "canonical_trace"
    )

    not_found = DecisionTraceNotFound(
        record_id="zz",
        missing_links=("proposal: not found", "canonical_decision: not found"),
    )
    not_found_payload = trace_not_found_to_transport(not_found)
    assert not_found_payload["result_type"] == "trace_not_found"
    assert "record_type" not in not_found_payload

    union = trace_to_transport(proposal_trace)
    assert union["result_type"] == "proposal_trace"


def test_get_result_serializer_raises_on_unknown_type():
    with pytest.raises(Exception):
        get_result_to_transport(object())


def test_search_and_scope_serializers_keep_domains_separate():
    service = DecisionIndexService(
        InMemoryDecisionProposalStore(),
        canonical_index=_canonical_index(),
        clock=lambda: FIXED_TIME,
    )
    service.propose(candidate_from_input(
        CandidateInput.model_validate(_candidate_input())
    ))
    search_payload = search_result_to_transport(service.search(""))
    assert set(search_payload.keys()) == {"proposals", "canonical_decisions"}
    assert len(search_payload["proposals"]) == 1
    assert len(search_payload["canonical_decisions"]) == 2

    scope_payload = scope_hint_result_to_transport(
        service.applicable_to(context=["storage"])
    )
    assert set(scope_payload.keys()) == {
        "proposal_hint_matches", "canonical_scope_matches",
    }
    # Slim canonical context references in scope results.
    for match in scope_payload["canonical_scope_matches"]:
        assert "derived_rule_ids" not in match


def test_propose_result_serializer_preserves_created_flag():
    service = DecisionIndexService(
        InMemoryDecisionProposalStore(), clock=lambda: FIXED_TIME,
    )
    result = service.propose(candidate_from_input(
        CandidateInput.model_validate(_candidate_input())
    ))
    payload = {
        "created": result.created,
        "reused": not result.created,
        "proposal": proposal_to_transport(result.proposal),
    }
    assert payload["created"] is True and payload["reused"] is False


# ── Vocabulary mirrors stay in lockstep with the service ────────────────────


def test_transport_vocabulary_mirrors_service_vocabulary():
    from mneme.decision_mcp import (
        VALID_CANONICAL_LIFECYCLE_FILTERS,
        VALID_ORIGIN_FILTERS,
        VALID_PROPOSAL_STATUS_FILTERS,
    )
    assert tuple(sorted(VALID_PROPOSAL_STATUS_FILTERS)) == tuple(
        sorted(_VALID_PROPOSAL_STATUS_FILTERS)
    )
    assert set(VALID_CANONICAL_LIFECYCLE_FILTERS) == set(
        VALID_LIFECYCLE_STATUSES
    )
    assert set(VALID_ORIGIN_FILTERS) == {
        ORIGIN_AI_GENERATED, ORIGIN_HUMAN_AUTHORED, ORIGIN_IMPORTED_UNKNOWN,
    }


# ── Composition helpers ─────────────────────────────────────────────────────


def test_open_proposal_store_defaults_to_in_memory():
    store = open_proposal_store(None)
    assert isinstance(store, InMemoryDecisionProposalStore)


def test_open_proposal_store_uses_json_file_store_for_a_path(tmp_path: Path):
    store = open_proposal_store(tmp_path / "proposals.json")
    assert type(store).__name__ == "JsonFileDecisionProposalStore"


def test_serve_stdio_is_the_single_transport_launch_point():
    import inspect
    from mneme.decision_mcp import serve_stdio as fn
    source = inspect.getsource(fn)
    assert "server.run()" in source
    assert "stdio" in (fn.__doc__ or "").lower()


# ── Capability descriptions are inspectable (human reviewability) ───────────


def test_tool_descriptions_state_the_authority_boundary():
    async def _run():
        async with Client(_server()) as client:
            result = await client.list_tools()
            return {t.name: t.description or "" for t in result.tools}
    descriptions = asyncio.run(_run())
    assert "NO authority" in descriptions[TOOL_PROPOSE]
    assert "non-authoritative" in descriptions[TOOL_PROPOSE]
    assert "NO authority" in descriptions[TOOL_PROPOSE_BATCH]
    assert "never mutates" in descriptions[TOOL_GET]
    assert "never mutates" in descriptions[TOOL_SEARCH]
    assert "NOT typed-rule applicability" in descriptions[TOOL_APPLICABLE_TO]
    assert "fail closed" in descriptions[TOOL_TRACE]


# ── Strict ADR compiler composition (architecture review of D2B) ────────────

_VALID_ADR_BODY = """---
id: ADR-9001
title: "Use deterministic storage for the test corpus"
status: accepted
priority: normal
date: 2026-09-01
scope: storage
---

# ADR-9001: Storage policy fixture

## Constraints

- FORBID_LITERAL: install legacy-package
"""

_INACTIVE_ADR_BODY = """---
id: ADR-9002
title: "Cache policy fixture"
status: proposed
priority: normal
date: 2026-09-02
scope: cache
---

# ADR-9002: Cache policy fixture
"""


def _write_adr(
    directory: Path,
    filename: str,
    body: str,
) -> Path:
    path = directory / filename
    path.write_text(body, encoding="utf-8")
    return path


def _valid_adr_dir(tmp_path: Path) -> Path:
    adr_dir = tmp_path / "valid-adr"
    adr_dir.mkdir()
    _write_adr(adr_dir, "ADR-9001-storage-policy.md", _VALID_ADR_BODY)
    _write_adr(adr_dir, "ADR-9002-cache-policy.md", _INACTIVE_ADR_BODY)
    return adr_dir


def _invalid_priority_adr_dir(tmp_path: Path) -> Path:
    adr_dir = tmp_path / "invalid-enum-adr"
    adr_dir.mkdir()
    body = _VALID_ADR_BODY.replace("priority: normal", "priority: high")
    _write_adr(adr_dir, "ADR-9001-storage-policy.md", body)
    return adr_dir


def _ambiguous_adr_dir(tmp_path: Path) -> Path:
    adr_dir = tmp_path / "ambiguous-adr"
    adr_dir.mkdir()
    first = _VALID_ADR_BODY.replace("ADR-9001", "ADR-9101")
    second = _VALID_ADR_BODY.replace("ADR-9001", "ADR-9102")
    _write_adr(adr_dir, "ADR-9101-storage-policy.md", first)
    _write_adr(adr_dir, "ADR-9102-storage-policy.md", second)
    return adr_dir


def _malformed_adr_dir(tmp_path: Path) -> Path:
    adr_dir = tmp_path / "malformed-adr"
    adr_dir.mkdir()
    _write_adr(
        adr_dir,
        "ADR-9001-storage-policy.md",
        "no frontmatter at all\n",
    )
    return adr_dir


def test_load_canonical_index_strict_valid_corpus_is_validated_and_loaded(
    tmp_path: Path,
):
    from mneme.decision_mcp import load_canonical_index_from_adr_dir

    index = load_canonical_index_from_adr_dir(_valid_adr_dir(tmp_path))
    by_id = {r.decision_id: r for r in index.records}
    assert set(by_id) == {"ADR-9001", "ADR-9002"}
    # Precedence winner is active; the proposed ADR is retained as
    # non-authoritative lineage, not dropped.
    assert by_id["ADR-9001"].lifecycle_status == "active"
    assert by_id["ADR-9002"].lifecycle_status == "inactive"
    assert [r.rule_id for r in index.rules] == [
        "ADR-9001:FORBID_LITERAL:0",
    ]


def test_load_canonical_index_rejects_invalid_adr_enum(tmp_path: Path):
    from mneme.adr_schema import ADRValidationError
    from mneme.decision_mcp import load_canonical_index_from_adr_dir

    with pytest.raises(ADRValidationError):
        load_canonical_index_from_adr_dir(_invalid_priority_adr_dir(tmp_path))


def test_load_canonical_index_rejects_precedence_ambiguity(tmp_path: Path):
    from mneme.adr_schema import ADRPrecedenceError
    from mneme.decision_mcp import load_canonical_index_from_adr_dir

    with pytest.raises(ADRPrecedenceError):
        load_canonical_index_from_adr_dir(_ambiguous_adr_dir(tmp_path))


def test_load_canonical_index_rejects_malformed_adr(tmp_path: Path):
    from mneme.adr_schema import ADRParseError
    from mneme.decision_mcp import load_canonical_index_from_adr_dir

    with pytest.raises(ADRParseError):
        load_canonical_index_from_adr_dir(_malformed_adr_dir(tmp_path))


def test_no_active_zero_degradation_fallback_exists():
    """The strict compiler sequence is used; ambiguity fails hard."""
    source = MCP_MODULE_SOURCE
    # The strict sequence is present, in order.
    load_source = re.search(
        r"def load_canonical_index_from_adr_dir.*?(?=\ndef |\Z)",
        source,
        re.DOTALL,
    ).group(0)
    sequence = [
        "parse_adr_directory(adr_dir)",
        "validate_corpus(parsed)",
        "resolve_precedence(parsed)",
        "build_canonical_index(parsed, active)",
    ]
    position = -1
    for step in sequence:
        found = load_source.find(step)
        assert found != -1, step
        assert found > position, f"out of order: {step}"
        position = found
    # No ADRPrecedenceError catch, no active=[] degradation.
    assert "except ADRPrecedenceError" not in source
    assert "active = []" not in source


class _RecordingServer(MCPServer):
    run_calls: list[bool] = []

    def run(self, *args: object, **kwargs: object) -> object:
        type(self).run_calls.append(True)
        return None


def _serve_stdio_with_recording_run(monkeypatch: pytest.MonkeyPatch):
    from mneme import decision_mcp

    _RecordingServer.run_calls = []
    monkeypatch.setattr(decision_mcp, "MCPServer", _RecordingServer)
    return _RecordingServer


def test_serve_stdio_strict_composes_and_starts_on_valid_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    RecordingServer = _serve_stdio_with_recording_run(monkeypatch)
    serve_stdio(proposal_store_path=None, adr_dir=_valid_adr_dir(tmp_path))
    assert RecordingServer.run_calls == [True]


def test_serve_stdio_fails_closed_on_invalid_adr_enum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    from mneme.adr_schema import ADRValidationError

    RecordingServer = _serve_stdio_with_recording_run(monkeypatch)
    with pytest.raises(ADRValidationError):
        serve_stdio(
            proposal_store_path=None,
            adr_dir=_invalid_priority_adr_dir(tmp_path),
        )
    assert RecordingServer.run_calls == []


def test_serve_stdio_fails_closed_on_ambiguous_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    from mneme.adr_schema import ADRPrecedenceError

    RecordingServer = _serve_stdio_with_recording_run(monkeypatch)
    with pytest.raises(ADRPrecedenceError):
        serve_stdio(
            proposal_store_path=None,
            adr_dir=_ambiguous_adr_dir(tmp_path),
        )
    assert RecordingServer.run_calls == []


def test_cli_default_starts_without_canonical_adr_dir(monkeypatch):
    from mneme import cli as cli_module
    from mneme import decision_mcp

    calls: list[tuple] = []

    def recorder(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(decision_mcp, "serve_stdio", recorder)
    exit_code = cli_module.main(["decision-mcp", "--proposals", ""])
    assert exit_code == 0
    assert len(calls) == 1
    _, kwargs = calls[0]
    assert kwargs["adr_dir"] is None
    assert kwargs["proposal_store_path"] is None  # explicit in-memory store


def test_cli_explicit_adr_dir_passes_strict_canonical_loading(
    tmp_path: Path, monkeypatch,
):
    from mneme import cli as cli_module
    from mneme import decision_mcp

    calls: list[tuple] = []

    def recorder(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(decision_mcp, "serve_stdio", recorder)
    adr_dir = _valid_adr_dir(tmp_path)
    exit_code = cli_module.main([
        "decision-mcp", "--proposals", "", "--adr-dir", str(adr_dir),
    ])
    assert exit_code == 0
    _, kwargs = calls[0]
    assert kwargs["adr_dir"] == str(adr_dir)


def test_cli_rejects_missing_adr_dir_path(tmp_path: Path):
    from mneme import cli as cli_module

    exit_code = cli_module.main([
        "decision-mcp", "--proposals", "",
        "--adr-dir", str(tmp_path / "nope"),
    ])
    assert exit_code == 2


def test_cli_rejects_empty_adr_dir_value():
    from mneme import cli as cli_module

    exit_code = cli_module.main(["decision-mcp", "--proposals", "", "--adr-dir", ""])
    assert exit_code == 2


def test_cli_help_states_adr_dir_is_optional():
    from mneme import cli as cli_module
    parser = cli_module._build_parser()
    for action in parser._subparsers._group_actions[0].choices[
        "decision-mcp"
    ]._actions:
        if getattr(action, "dest", None) == "adr_dir":
            assert "Optional" in action.help
            assert action.default is None
            break
    else:
        raise AssertionError("decision-mcp --adr-dir action not found")


# ── Typed trace union dispatch ──────────────────────────────────────────────


def test_trace_to_transport_fails_closed_on_unexpected_type():
    with pytest.raises(BaseException) as excinfo:
        trace_to_transport(object())
    errors = _mcp_errors_in(excinfo.value)
    assert len(errors) == 1
    assert isinstance(errors[0], MCPError)
    assert "unexpected trace result" in str(errors[0])


def test_trace_dispatch_uses_isinstance_not_class_name_strings():
    fn_source = inspect.getsource(trace_to_transport)
    # No string-based dispatch on the union member names.
    assert re.search(r'type\(trace\)\.__name__\s*==', fn_source) is None
    assert re.search(r'trace\.result_type\s*==', fn_source) is None
    assert "isinstance(trace, ProposalTrace)" in fn_source
    assert "isinstance(trace, CanonicalDecisionTrace)" in fn_source
    assert "isinstance(trace, DecisionTraceNotFound)" in fn_source


# ── MCP stays optional for ordinary package runtime ─────────────────────────


def test_mcp_stays_out_of_core_runtime_dependencies():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    core = re.search(r"^dependencies = \[(.*?)^\]", pyproject, re.DOTALL | re.MULTILINE)
    assert core is not None
    assert "mcp" not in core.group(1)
    # The optional extra is the only place the dependency is declared.
    extra = re.search(r"^mcp = \[(.*?)\]", pyproject, re.MULTILINE | re.DOTALL)
    assert extra is not None
    assert "mcp" in extra.group(1)


def test_importing_core_domain_modules_does_not_load_mcp():
    script = (
        "import sys; import mneme.decision_index, mneme.memory_store,"
        " mneme.decision_index_service, mneme.decision_proposal;"
        " assert not [m for m in sys.modules if m == 'mcp' or"
        " m.startswith(('mcp.', 'pydantic'))]; print('OK')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=True,
    )
    assert proc.stdout.strip().endswith("OK")


def test_workflow_provisioning_includes_mcp_where_mcp_tests_run():
    workflow = (
        REPO_ROOT / ".github" / "workflows" / "tests.yml"
    ).read_text(encoding="utf-8")
    gate = re.search(r"gate:\n.*?Run gate battery", workflow, re.DOTALL).group(0)
    main = re.search(r"\n  main:\n.*?Run main battery", workflow, re.DOTALL).group(0)
    release = re.search(
        r"\n  release:\n.*?Run release battery", workflow, re.DOTALL
    ).group(0)
    langchain_job = re.search(
        r"pytest-langchain:\n.*?Run LangChain integration tests",
        workflow,
        re.DOTALL,
    ).group(0)
    assert 'pip install -e ".[dev,mcp]"' in gate
    assert 'pip install -e ".[dev,mcp]"' in main
    assert 'pip install -e ".[dev,mcp,langchain]"' in release
    # The dedicated LangChain job only runs LangChain integration tests.
    assert 'pip install -e ".[dev,langchain]"' in langchain_job


# ── Module source cache (used by architecture-boundary tests) ───────────────


MCP_MODULE_SOURCE = MCP_MODULE.read_text(encoding="utf-8")

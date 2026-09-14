"""
decision_mcp.py — Decision Index MCP transport adapter (ADR-027, D2B, #362).

A thin local MCP capability boundary over ``DecisionIndexService``. This
module owns transport only: tool registration, input decoding/validation,
output serialization, and protocol-level errors. Every handler delegates
to a public ``DecisionIndexService`` method; no handler touches
``_store``/``_canonical`` or duplicates service semantics.

Authority boundary (ADR-027 sections 2, 3, 7; D2B capability matrix):

* The MCP tool list IS part of the authority boundary. Exactly six tools
  are exposed — ``decision.propose``, ``decision.propose_batch``,
  ``decision.get``, ``decision.search``, ``decision.applicable_to``,
  ``decision.trace`` — and nothing else. There is deliberately no
  accept/reject/activate/supersede/exception/trusted-evidence tool and no
  alias for one. No MCP call can make a proposal enforceable: a proposal
  call may only append or idempotently reuse a non-authoritative
  ``proposed`` proposal; read tools never mutate any state.

* Proposal input is a Pydantic model whose structure excludes every
  authoritative field (status, proposal_id, producer_key, content
  fingerprint, proposed_at, accepted_decision_id, canonical lifecycle,
  rules, rule applicability, trusted evidence, enforcement state).
  ``DecisionProposalInput.model_config['extra'] = 'forbid'`` fails closed:
  a producer that supplies a forbidden authority field is rejected with a
  validation error — the transport never accepts and silently discards it.

* Serialization is explicit and deterministic: ``proposal_to_transport``,
  ``canonical_record_to_transport``, and the other ``*_to_transport``
  helpers below emit plain JSON-safe dicts with stable key order and
  preserve list ordering. ``dataclasses.asdict`` is never used (it would
  make the protocol contract accidental). Proposal lifecycle vocabulary
  (proposed/accepted/rejected) and canonical lifecycle vocabulary
  (active/superseded/deprecated/inactive) remain separate domains with
  separate field names; nothing is flattened into one ambiguous status.

Error contract:

Error contract:

* ``decision.get`` with an unknown record id -> a successful typed
  ``not_found`` result (``record_type: "not_found"``); ``decision.trace``
  with an unknown id -> a successful typed ``trace_not_found`` result
  (``result_type: "trace_not_found"``, identifier stays type-unknown).
  Not-found is data, never an error.
* Invalid or malformed caller input (unknown/extra arguments, forbidden
  authority fields, empty ``record_id``, invalid lifecycle filter or
  origin classification, malformed candidates) -> ``ToolError``: the
  call returns ``is_error=True`` and the model can correct its input.
  Filter-vocabulary validation is service-owned (the handler converts
  the service's ``ValueError``); argument-shape validation is enforced
  by the SDK's input schema before the handler runs.
* ``DecisionIndexIntegrityError`` (canonical rule-lineage mismatch) is
  fail closed: it is re-raised as a protocol-level ``MCPError`` (via
  ``_FailClosedProtocolError``, which the SDK passes through its tool
  wrapper unwrapped) with ``INTERNAL_ERROR``, so the whole ``tools/call``
  request fails as a JSON-RPC error. No successful, partial, or
  ambiguous result is ever produced for an integrity failure, and the
  protocol error is distinguishable from an ordinary not-found.
* Corrupt proposal stores and invalid canonical sources (ADR parse
  failure, schema/validation failure, or precedence ambiguity from the
  strict compiler path) are composition failures that surface at
  server construction — before the server starts. The server never
  serves a degraded or ambiguous canonical authority view.
* No stack traces appear in tool result payloads.

Transport: stdio only (``build_server(...).run()``). No HTTP transport
is included in this release; a served endpoint is out of scope for D2B.

Composition: ``build_server`` accepts the already-constructed
``DecisionIndexService`` (dependency injection for tests) or the raw
pieces (proposal store, canonical index). This module never creates a
second authoritative persistence model and never mutates
``.mneme/project_memory.json``. For canonical ADR sources,
``load_canonical_index_from_adr_dir`` runs the established strict
Mneme compiler sequence (``parse -> validate_corpus ->
resolve_precedence -> build_canonical_index``) with no error
suppression: ambiguity and invalid metadata prevent server startup.
Other callers use the existing D0 adapters or supply an already-built
``CanonicalArchitectureIndex``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Sequence

from mcp import MCPError
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import INTERNAL_ERROR, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from mneme.adr_compiler import resolve_precedence, validate_corpus
from mneme.adr_parser import parse_adr_directory
from mneme.decision_index import (
    CanonicalDecisionRecord,
    CanonicalRuleRecord,
    CanonicalTestEvidence,
    build_canonical_index,
)
from mneme.decision_index_service import (
    CanonicalDecisionTrace,
    DecisionIndexIntegrityError,
    DecisionIndexService,
    DecisionTraceNotFound,
    ProposalTrace,
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
)
from mneme.decision_proposal_store import (
    DecisionProposalStore,
    InMemoryDecisionProposalStore,
    JsonFileDecisionProposalStore,
)

SERVER_NAME = "mneme-decision-index"
SERVER_VERSION = "0.1.0"

# ── Tool names (frozen capability inventory, ADR-027 P0) ────────────────────

TOOL_PROPOSE = "decision.propose"
TOOL_PROPOSE_BATCH = "decision.propose_batch"
TOOL_GET = "decision.get"
TOOL_SEARCH = "decision.search"
TOOL_APPLICABLE_TO = "decision.applicable_to"
TOOL_TRACE = "decision.trace"

APPROVED_TOOLS: tuple[str, ...] = (
    TOOL_PROPOSE,
    TOOL_PROPOSE_BATCH,
    TOOL_GET,
    TOOL_SEARCH,
    TOOL_APPLICABLE_TO,
    TOOL_TRACE,
)

_READ_ANNOTATIONS = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
_PROPOSE_ANNOTATIONS = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

# Vocabulary mirrors kept in lockstep with the service (asserted by tests).
VALID_PROPOSAL_STATUS_FILTERS = (
    PROPOSAL_STATUS_PROPOSED,
    PROPOSAL_STATUS_ACCEPTED,
    PROPOSAL_STATUS_REJECTED,
)
VALID_CANONICAL_LIFECYCLE_FILTERS = ("active", "superseded", "deprecated", "inactive")
VALID_ORIGIN_FILTERS = (ORIGIN_AI_GENERATED, ORIGIN_HUMAN_AUTHORED, ORIGIN_IMPORTED_UNKNOWN)


# ── Input models (capability-shaped, fail closed on authority fields) ───────


class SourceProvenanceInput(BaseModel):
    """Producer/source provenance exactly as the service model defines it."""

    model_config = ConfigDict(extra="forbid")

    producer_name: str = Field(min_length=1)
    producer_type: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    external_source_id: str = ""
    source_version: str = ""
    repository_locator: str = ""
    origin_classification: Literal[
        ORIGIN_AI_GENERATED, ORIGIN_HUMAN_AUTHORED, ORIGIN_IMPORTED_UNKNOWN
    ] = ORIGIN_IMPORTED_UNKNOWN


class CandidateInput(BaseModel):
    """One candidate decision.

    The field set is exactly the producer-controlled subset of
    ``DecisionProposalCandidate``. ``extra='forbid'`` means an
    authority field (``status``, ``proposal_id``, ``accepted_decision_id``,
    ``proposed_at``, ``rules``, ``trusted_evidence``, ...) is a hard
    validation error, never silently discarded.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    rationale: str = ""
    provenance: SourceProvenanceInput | None = None
    scope_hints: list[str] = Field(default_factory=list)
    architecture_context: dict[str, str] = Field(default_factory=dict)
    related_decision_ids: list[str] = Field(default_factory=list)


class BatchInput(BaseModel):
    """Batch envelope: shared provenance only where the service permits it."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[CandidateInput] = Field(min_length=1)
    shared_provenance: SourceProvenanceInput | None = None


# ── Explicit deterministic serialization (module contract) ─────────────────


def provenance_to_transport(
    provenance: DecisionProposalSourceProvenance,
) -> dict[str, Any]:
    """Serialize producer provenance losslessly, in field order."""
    return {
        "producer_name": provenance.producer_name,
        "producer_type": provenance.producer_type,
        "source_reference": provenance.source_reference,
        "external_source_id": provenance.external_source_id,
        "source_version": provenance.source_version,
        "repository_locator": provenance.repository_locator,
        "origin_classification": provenance.origin_classification,
    }


def proposal_to_transport(proposal: DecisionProposal) -> dict[str, Any]:
    """Serialize one stored proposal for the protocol.

    ``status`` is the proposal lifecycle vocabulary
    (proposed/accepted/rejected) under its explicit ``proposal_status`` key;
    candidate content and provenance round-trip losslessly; ``created`` is
    not part of the record and is added by the propose handlers.
    """
    candidate = proposal.candidate
    return {
        "proposal_id": proposal.proposal_id,
        "proposal_status": proposal.status,
        "title": candidate.title,
        "statement": candidate.statement,
        "rationale": candidate.rationale,
        "provenance": (
            provenance_to_transport(candidate.provenance)
            if candidate.provenance is not None
            else None
        ),
        "scope_hints": list(candidate.scope_hints),
        "architecture_context": dict(candidate.architecture_context),
        "related_decision_ids": list(candidate.related_decision_ids),
        "producer_key": proposal.producer_key,
        "content_fingerprint": proposal.content_fingerprint,
        "proposed_at": proposal.proposed_at,
        "accepted_decision_id": proposal.accepted_decision_id,
    }


def declared_evidence_to_transport(evidence: CanonicalTestEvidence) -> dict[str, Any]:
    """Declared test-evidence linkage exactly as stored (ADR-024).

    The transport deliberately carries no ``verification_state`` field:
    declared linkage is never labelled trusted/verified (ADR-025).
    """
    return {
        "selector": evidence.selector,
        "sha": evidence.sha,
    }


def rule_to_transport(rule: CanonicalRuleRecord) -> dict[str, Any]:
    """Serialize a canonical rule with ADR-020 applicability verbatim.

    Applicability is passed through exactly as stored — the transport adds
    no selector, no glob evaluation, and no reinterpretation.
    """
    return {
        "rule_id": rule.rule_id,
        "decision_id": rule.decision_id,
        "decision_version": rule.decision_version,
        "rule_type": rule.rule_type,
        "rule_payload": dict(rule.rule_payload),
        "applicability": dict(rule.applicability),
        "lifecycle_status": rule.lifecycle_status,
    }


def canonical_record_to_transport(
    record: CanonicalDecisionRecord,
) -> dict[str, Any]:
    """Serialize one canonical decision record.

    ``lifecycle_status`` is the canonical lifecycle vocabulary
    (active/superseded/deprecated/inactive) under its explicit key;
    relationships keep their ordered (kind, target) pairs.
    """
    return {
        "decision_id": record.decision_id,
        "version": record.version,
        "decision_class": record.decision_class,
        "statement": record.statement,
        "rationale": record.rationale,
        "lifecycle_status": record.lifecycle_status,
        "owner": record.owner,
        "decided_at": record.decided_at,
        "updated_at": record.updated_at,
        "context_scope": list(record.context_scope),
        "targets": list(record.targets),
        "constraints": list(record.constraints),
        "anti_patterns": list(record.anti_patterns),
        "source_evidence": [
            {"source_type": e.source_type, "source_locator": e.source_locator}
            for e in record.source_evidence
        ],
        "test_evidence": [declared_evidence_to_transport(e) for e in record.test_evidence],
        "relationships": [[kind, target] for kind, target in record.relationships],
        "derived_rule_ids": list(record.derived_rule_ids),
    }


def propose_result_to_transport(
    proposal: DecisionProposal, created: bool
) -> dict[str, Any]:
    """ProposeResult serialization: record plus idempotency outcome."""
    return {
        "created": created,
        "reused": not created,
        "proposal": proposal_to_transport(proposal),
    }


def search_result_to_transport(result: Any) -> dict[str, Any]:
    """Search serialization preserving the proposal/canonical domains.

    The two lists stay separate with their own lifecycle vocabularies
    (``proposal_status`` vs ``lifecycle_status``); nothing is merged.
    """
    return {
        "proposals": [proposal_to_transport(p) for p in result.proposals],
        "canonical_decisions": [
            canonical_record_to_transport(r) for r in result.canonical_decisions
        ],
    }


def scope_hint_result_to_transport(result: Any) -> dict[str, Any]:
    """Applicability serialization: retrieval hints only.

    Proposal scope hints are returned under ``proposal_hint_matches``;
    canonical scope matches are slim context references (identity,
    statement, lifecycle, context scope) — deliberately not full records:
    this result carries no rules, no ADR-020 selectors, no derived rule
    linkage, and no enforcement field. Scope hints are never reinterpreted
    as typed-rule applicability (ADR-020).
    """
    return {
        "proposal_hint_matches": [
            {"proposal_id": m.proposal_id, "matched_hints": list(m.matched_hints)}
            for m in result.proposal_hint_matches
        ],
        "canonical_scope_matches": [
            canonical_scope_ref_to_transport(r)
            for r in result.canonical_scope_matches
        ],
    }


def canonical_scope_ref_to_transport(
    record: CanonicalDecisionRecord,
) -> dict[str, Any]:
    """Slim canonical context reference for retrieval/applicability results.

    Identity, statement, lifecycle, and context scope only: no rules, no
    ADR-020 selectors, no enforcement linkage.
    """
    return {
        "decision_id": record.decision_id,
        "version": record.version,
        "statement": record.statement,
        "lifecycle_status": record.lifecycle_status,
        "context_scope": list(record.context_scope),
    }


def proposal_trace_to_transport(trace: Any) -> dict[str, Any]:
    """Proposal trace serialization with an explicit ``result_type``."""
    return {
        "result_type": "proposal_trace",
        "proposal_id": trace.proposal_id,
        "proposal": (
            proposal_to_transport(trace.proposal) if trace.proposal is not None else None
        ),
        "source_provenance": (
            provenance_to_transport(trace.source_provenance)
            if trace.source_provenance is not None
            else None
        ),
        "accepted_decision_id": trace.accepted_decision_id,
        "canonical_record": (
            canonical_record_to_transport(trace.canonical_record)
            if trace.canonical_record is not None
            else None
        ),
        "canonical_derived_rule_ids": list(trace.canonical_derived_rule_ids),
        "missing_links": list(trace.missing_links),
    }


def canonical_trace_to_transport(trace: Any) -> dict[str, Any]:
    """Canonical trace serialization with an explicit ``result_type``."""
    return {
        "result_type": "canonical_trace",
        "canonical_decision_id": trace.canonical_decision_id,
        "canonical_record": (
            canonical_record_to_transport(trace.canonical_record)
            if trace.canonical_record is not None
            else None
        ),
        "derived_rules": [rule_to_transport(r) for r in trace.derived_rules],
        "declared_test_evidence": [
            declared_evidence_to_transport(e) for e in trace.declared_test_evidence
        ],
        "missing_links": list(trace.missing_links),
    }


def trace_not_found_to_transport(trace: Any) -> dict[str, Any]:
    """Not-found trace serialization: the id stays type-unknown."""
    return {
        "result_type": "trace_not_found",
        "record_id": trace.record_id,
        "missing_links": list(trace.missing_links),
    }


def get_result_to_transport(record: Any) -> dict[str, Any]:
    """Explicit get-result typing: proposal vs canonical_decision.

    The service owns the distinction; the transport never guesses. The two
    lifecycle vocabularies stay in their separate keys.
    """
    if isinstance(record, DecisionProposal):
        return {
            "record_type": "proposal",
            "proposal": proposal_to_transport(record),
        }
    if isinstance(record, CanonicalDecisionRecord):
        return {
            "record_type": "canonical_decision",
            "canonical_decision": canonical_record_to_transport(record),
        }
    raise ToolError(f"record {record!r} has an unsupported transport type")


# ── Input decoding ──────────────────────────────────────────────────────────


def provenance_from_input(
    input_model: SourceProvenanceInput | None,
) -> DecisionProposalSourceProvenance | None:
    """Decode a transport provenance model into the domain type."""
    if input_model is None:
        return None
    return DecisionProposalSourceProvenance(
        producer_name=input_model.producer_name,
        producer_type=input_model.producer_type,
        source_reference=input_model.source_reference,
        external_source_id=input_model.external_source_id,
        source_version=input_model.source_version,
        repository_locator=input_model.repository_locator,
        origin_classification=input_model.origin_classification,
    )


def candidate_from_input(input_model: CandidateInput) -> DecisionProposalCandidate:
    """Decode one candidate; only service-accepted fields are carried."""
    return DecisionProposalCandidate(
        title=input_model.title,
        statement=input_model.statement,
        rationale=input_model.rationale,
        provenance=provenance_from_input(input_model.provenance),
        scope_hints=tuple(input_model.scope_hints),
        architecture_context=dict(input_model.architecture_context),
        related_decision_ids=tuple(input_model.related_decision_ids),
    )


def candidates_from_input(
    input_models: Sequence[CandidateInput],
) -> tuple[DecisionProposalCandidate, ...]:
    """Decode candidates preserving input order (batch result alignment)."""
    return tuple(candidate_from_input(m) for m in input_models)


# ── Server construction / composition (transport only) ──────────────────────


def _tool_error_from_value_error(exc: ValueError) -> ToolError:
    """Convert an ordinary service-side validation ValueError to a ToolError."""
    return ToolError(str(exc))


def _register_tools(server: MCPServer, service: DecisionIndexService) -> None:
    """Register exactly the six approved tools on ``server``."""

    @server.tool(
        name=TOOL_PROPOSE,
        title="Propose a decision (non-authoritative)",
        description=(
            "Submit one candidate architectural decision. The proposal "
            "enters the Mneme decision index as a non-authoritative "
            "proposal with status 'proposed'. This grants NO authority: "
            "the proposal is never enforceable and can only become "
            "canonical through separate Mneme human authority (D2C), "
            "which this MCP does not expose. Repeated identical "
            "source/version/content submissions are idempotent."
        ),
        annotations=_PROPOSE_ANNOTATIONS,
    )
    def decision_propose(candidate: CandidateInput) -> dict[str, Any]:
        """Capability: append/reuse one non-authoritative proposal.

        Changes: at most one new proposal record (status 'proposed').
        Cannot: accept/reject proposals, create canonical decisions,
        activate/supersede decisions, create rules or exceptions, submit
        trusted evidence, or touch any enforcement state.
        """
        try:
            result = service.propose(candidate_from_input(candidate))
        except ValueError as exc:
            raise _tool_error_from_value_error(exc) from exc
        return propose_result_to_transport(result.proposal, result.created)

    @server.tool(
        name=TOOL_PROPOSE_BATCH,
        title="Propose decisions in batch (non-authoritative)",
        description=(
            "Submit multiple candidate architectural decisions from one "
            "producer output. Each candidate receives its own independent "
            "proposal identity and enters as a non-authoritative proposal "
            "with status 'proposed'. There are no batch acceptance "
            "semantics: batch submission grants NO authority, and every "
            "proposal remains independently reviewable."
        ),
        annotations=_PROPOSE_ANNOTATIONS,
    )
    def decision_propose_batch(
        candidates: list[CandidateInput],
        shared_provenance: SourceProvenanceInput | None = None,
    ) -> dict[str, Any]:
        """Capability: append/reuse N non-authoritative proposals.

        Changes: at most one new proposal record per candidate. Cannot:
        anything the single proposal tool cannot; batch submission creates
        no batch authority and no automatic acceptance.
        """
        try:
            results = service.propose_batch(
                candidates_from_input(candidates),
                provenance_from_input(shared_provenance),
            )
        except ValueError as exc:
            raise _tool_error_from_value_error(exc) from exc
        return {
            "results": [
                propose_result_to_transport(r.proposal, r.created) for r in results
            ]
        }

    @server.tool(
        name=TOOL_GET,
        title="Get a proposal or canonical decision",
        description=(
            "Read one record by stable id. Returns record_type "
            "'proposal', 'canonical_decision', or 'not_found'. Read only: "
            "this tool never mutates any state."
        ),
        annotations=_READ_ANNOTATIONS,
    )
    def decision_get(record_id: str) -> dict[str, Any]:
        """Capability: read one record; no state change of any kind."""
        record = service.get(record_id)
        if record is None:
            return {
                "record_type": "not_found",
                "record_id": record_id,
            }
        return get_result_to_transport(record)

    @server.tool(
        name=TOOL_SEARCH,
        title="Search proposals and canonical decisions",
        description=(
            "Deterministic text/exact-metadata search. Proposals "
            "(lifecycle proposed/accepted/rejected) and canonical "
            "decisions (lifecycle active/superseded/deprecated/inactive) "
            "are returned in separate lists and never merged. Read only: "
            "this tool never mutates any state. Search rank has no "
            "enforcement meaning."
        ),
        annotations=_READ_ANNOTATIONS,
    )
    def decision_search(
        query: str = "",
        proposal_status: (
            Literal[PROPOSAL_STATUS_PROPOSED, PROPOSAL_STATUS_ACCEPTED, PROPOSAL_STATUS_REJECTED]
            | None
        ) = None,
        canonical_lifecycle_status: (
            Literal["active", "superseded", "deprecated", "inactive"] | None
        ) = None,
        producer_name: str | None = None,
        source_reference: str | None = None,
        origin_classification: (
            Literal[ORIGIN_AI_GENERATED, ORIGIN_HUMAN_AUTHORED, ORIGIN_IMPORTED_UNKNOWN] | None
        ) = None,
    ) -> dict[str, Any]:
        """Capability: read/search; no state change of any kind."""
        try:
            result = service.search(
                query=query,
                proposal_status=proposal_status,
                canonical_lifecycle_status=canonical_lifecycle_status,
                producer_name=producer_name,
                source_reference=source_reference,
                origin_classification=origin_classification,
            )
        except ValueError as exc:
            raise _tool_error_from_value_error(exc) from exc
        return search_result_to_transport(result)

    @server.tool(
        name=TOOL_APPLICABLE_TO,
        title="Get retrieval/context applicability",
        description=(
            "Return proposals and canonical decisions whose scope hints "
            "or context scope overlap the supplied context/paths. This is "
            "retrieval/context applicability only: proposal scope hints "
            "are NOT typed-rule applicability (ADR-020) and paths are "
            "never glob-evaluated. Read only: this tool never mutates any "
            "state and returns no rules or enforcement data."
        ),
        annotations=_READ_ANNOTATIONS,
    )
    def decision_applicable_to(
        context: list[str] | None = None,
        paths: list[str] | None = None,
    ) -> dict[str, Any]:
        """Capability: retrieval context; no state change of any kind."""
        result = service.applicable_to(
            context=context if context is not None else (),
            paths=paths if paths is not None else (),
        )
        return scope_hint_result_to_transport(result)

    @server.tool(
        name=TOOL_TRACE,
        title="Trace decision lineage",
        description=(
            "Return the deterministic lineage actually known for a "
            "proposal id or canonical decision id. The result_type is "
            "explicit (proposal_trace / canonical_trace / trace_not_found); "
            "unresolved ids stay type-unknown. Read only: this tool never "
            "mutates any state. Canonical rule-lineage integrity failures "
            "fail closed as protocol errors and are never returned as "
            "partial traces."
        ),
        annotations=_READ_ANNOTATIONS,
    )
    def decision_trace(record_id: str) -> dict[str, Any]:
        """Capability: read lineage; no state change of any kind."""
        try:
            trace = service.trace(record_id)
        except DecisionIndexIntegrityError as exc:
            # Fail closed at the protocol boundary: no result, structured
            # or otherwise, escapes an integrity failure.
            raise _FAIL_CLOSED_WRAPPER(
                code=INTERNAL_ERROR,
                message=(
                    f"decision index integrity failure "
                    f"({type(exc).__name__}): {exc}"
                ),
            ) from exc
        return trace_to_transport(trace)

    tools_by_name = {
        TOOL_PROPOSE: decision_propose,
        TOOL_PROPOSE_BATCH: decision_propose_batch,
        TOOL_GET: decision_get,
        TOOL_SEARCH: decision_search,
        TOOL_APPLICABLE_TO: decision_applicable_to,
        TOOL_TRACE: decision_trace,
    }
    if len(tools_by_name) != len(APPROVED_TOOLS):
        raise RuntimeError("MCP tool registration drifted from the approved inventory")


def trace_to_transport(trace: Any) -> dict[str, Any]:
    """Serialize any trace union member deterministically.

    The service owns the D2B0 union (``ProposalTrace`` |
    ``CanonicalDecisionTrace`` | ``DecisionTraceNotFound``); the
    transport preserves the member explicitly via ``result_type`` and
    dispatches on the actual types (``isinstance``), never on guessed
    shapes. Integrity failures never reach this function as results:
    the handler fails closed before serialization (see
    ``decision_trace``), and an unexpected union member is a protocol
    error rather than a guessed shape.
    """
    if isinstance(trace, ProposalTrace):
        return proposal_trace_to_transport(trace)
    if isinstance(trace, CanonicalDecisionTrace):
        return canonical_trace_to_transport(trace)
    if isinstance(trace, DecisionTraceNotFound):
        return trace_not_found_to_transport(trace)
    raise _protocol_error(
        "decision index internal failure: unexpected trace result "
        f"{type(trace).__name__}"
    )


class _FailClosedProtocolError(MCPError):
    """Re-raised from inside a tool body to reach the protocol error path.

    The SDK lets ``MCPError`` pass through its ``Tool.run`` wrapper
    unwrapped, and the server kernel re-raises it as the top-level
    JSON-RPC error of the ``tools/call`` request. This is the
    deterministic fail-closed path for integrity failures: no result,
    structured or otherwise, escapes a fail-closed condition, and the
    failure remains protocol-distinguishable from an ordinary not-found.
    """


_FAIL_CLOSED_WRAPPER: type[MCPError] = _FailClosedProtocolError


def _protocol_error(message: str) -> MCPError:
    return _FailClosedProtocolError(code=INTERNAL_ERROR, message=message)


def build_server(service: DecisionIndexService) -> MCPServer:
    """Build the local stdio MCP server for an injected service.

    Composition stays outside domain logic: callers construct the proposal
    store, canonical index (via the existing D0 adapters or an already
    built ``CanonicalArchitectureIndex``), and service, then inject it
    here. This module creates no persistence and no second authority.
    """
    server = MCPServer(SERVER_NAME, version=SERVER_VERSION)
    _register_tools(server, service)
    return server


def build_server_from_parts(
    proposal_store: DecisionProposalStore,
    canonical_index: Any | None = None,
    clock: Any | None = None,
) -> MCPServer:
    """Compose a server from store + canonical index (transport-side DI)."""
    service = DecisionIndexService(
        proposal_store,
        canonical_index=canonical_index,
        clock=clock,
    )
    return build_server(service)


def open_proposal_store(path: str | Path | None) -> DecisionProposalStore:
    """Open the proposal store for the server.

    ``None``/empty opens the in-memory store; a path opens the existing
    deterministic ``JsonFileDecisionProposalStore``. No other persistence
    model exists, and ``.mneme/project_memory.json`` is never touched.
    """
    if path is None:
        return InMemoryDecisionProposalStore()
    return JsonFileDecisionProposalStore(path)


def load_canonical_index_from_adr_dir(adr_dir: str | Path) -> Any:
    """Build the canonical index from an ADR directory — strict compiler path.

    The established Mneme compiler contract is followed exactly; no
    tolerance, no degradation, no ``active=[]`` fallback:

    ```text
    parse -> validate_corpus -> resolve_precedence -> canonical index
    ```

    A parse failure (``ADRParseError``), a schema/validation failure
    (``ADRValidationError``), or precedence ambiguity
    (``ADRPrecedenceError``) propagates and prevents server startup.
    The MCP must never serve a degraded canonical authority view when
    Mneme cannot determine the authoritative active set. Note that the
    strict validator is a step up from the D0 adapter's own (looser)
    input handling — ambiguity and invalid metadata fail hard here by
    contract.
    """
    parsed = parse_adr_directory(adr_dir)
    validate_corpus(parsed)
    active = resolve_precedence(parsed)
    return build_canonical_index(parsed, active)


def serve_stdio(
    proposal_store_path: str | Path | None = None,
    adr_dir: str | Path | None = None,
) -> None:
    """Compose the service and serve it over the local stdio transport.

    The only launch surface (``mneme decision-mcp``). The proposal store
    is always composed (``open_proposal_store``). Canonical ADR loading
    is optional: ``adr_dir=None`` starts the server with proposal-store
    access only, while an explicit directory must pass the strict Mneme
    ADR compiler path (parse -> validate -> precedence resolve) before
    the server starts — an invalid or ambiguous corpus prevents startup
    rather than degrading canonical authority. It launches the local
    MCP transport and nothing more.
    """
    canonical_index = (
        load_canonical_index_from_adr_dir(adr_dir) if adr_dir is not None else None
    )
    server = build_server_from_parts(
        open_proposal_store(proposal_store_path),
        canonical_index=canonical_index,
    )
    server.run()


__all__ = [
    "APPROVED_TOOLS",
    "SERVER_NAME",
    "SERVER_VERSION",
    "TOOL_APPLICABLE_TO",
    "TOOL_GET",
    "TOOL_PROPOSE",
    "TOOL_PROPOSE_BATCH",
    "TOOL_SEARCH",
    "TOOL_TRACE",
    "BatchInput",
    "CandidateInput",
    "SourceProvenanceInput",
    "build_server",
    "build_server_from_parts",
    "canonical_record_to_transport",
    "canonical_scope_ref_to_transport",
    "canonical_trace_to_transport",
    "candidate_from_input",
    "candidates_from_input",
    "get_result_to_transport",
    "load_canonical_index_from_adr_dir",
    "open_proposal_store",
    "proposal_to_transport",
    "proposal_trace_to_transport",
    "provenance_from_input",
    "provenance_to_transport",
    "rule_to_transport",
    "scope_hint_result_to_transport",
    "search_result_to_transport",
    "serve_stdio",
    "declared_evidence_to_transport",
    "trace_not_found_to_transport",
    "trace_to_transport",
]

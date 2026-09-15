"""D2C1 authority tests — DecisionAuthorityService (ADR-027 authority path).

Proves the D2C1 invariants: only Mneme authority transitions proposals;
accepted proposals carry ``accepted_decision_id``; the canonical decision
id is deterministic in a namespace distinct from proposal ids; acceptance
materializes exactly one bare ``active`` decision into
``project_memory.json`` and verifies BOTH representations (runtime and
``decisions_to_canonical``) before reporting success; crash/retry paths
are idempotent; reverse half-states and collisions fail closed; rejection
never touches memory; and the module is independent of MCP/CLI/frozen
runtime surfaces.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import mneme.decision_authority as da
from mneme.decision_authority import (
    AcceptedProposalIdConflictError,
    AcceptResult,
    CanonicalVerificationError,
    DecisionAuthorityError,
    DecisionAuthorityService,
    DecisionIdCollisionError,
    DecisionIdNamespaceError,
    MaterializationVerificationError,
    MemoryInvalidError,
    MemoryMissingError,
    ProposalAlreadyAcceptedError,
    ProposalAlreadyRejectedError,
    ProposalNotFoundError,
    ProposalStoreCorruptError,
    RejectResult,
    ReverseHalfStateError,
    default_decision_id_of,
    expected_materialization_entry,
)
from mneme.decision_index import (
    CANONICAL_VERSION,
    CanonicalArchitectureIndex,
    decisions_to_canonical,
)
from mneme.decision_index_service import DecisionIndexService
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
from mneme.memory_store import MemoryStore

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTHORITY_MODULE = REPO_ROOT / "mneme" / "decision_authority.py"
MCP_MODULE = REPO_ROOT / "mneme" / "decision_mcp.py"
CLI_MODULE = REPO_ROOT / "mneme" / "cli.py"

FIXED_TIME = "2026-09-14T12:00:00Z"
LATER_TIME = "2026-09-14T13:00:00Z"

FORBIDDEN_AUTHORITY_TOOL_NAMES = (
    "decision.accept",
    "decision.reject",
    "decision.activate",
    "decision.supersede",
    "decision.create_exception",
    "decision.bypass",
    "decision.submit_trusted_evidence",
)

APPROVED_TOOLS = (
    "decision.propose",
    "decision.propose_batch",
    "decision.get",
    "decision.search",
    "decision.applicable_to",
    "decision.trace",
)


# ── Fixtures / helpers ───────────────────────────────────────────────────────


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


def _candidate(
    statement: str = "New code must not import legacy_client.",
    scope_hints: tuple[str, ...] = ("storage", "backend"),
    title: str = "Avoid legacy client imports",
    rationale: str = "legacy_client is unmaintained and blocks Python 3.13.",
) -> DecisionProposalCandidate:
    return DecisionProposalCandidate(
        title=title,
        statement=statement,
        rationale=rationale,
        provenance=_provenance(),
        scope_hints=scope_hints,
    )


def _propose(
    store,
    candidate: DecisionProposalCandidate | None = None,
    clock: str = FIXED_TIME,
) -> DecisionProposal:
    """Create a proposal through the real producer path (always 'proposed')."""
    service = DecisionIndexService(store, clock=lambda: clock)
    result = service.propose(candidate if candidate is not None else _candidate())
    assert result.created
    return result.proposal


def _memory_document() -> dict:
    return {
        "meta": {
            "name": "test-project",
            "description": "Authority test memory",
            "version": "0.1.0",
            "owner": "",
            "created": "",
        },
        "items": [],
        "examples": [],
        "decisions": [],
    }


def _write_memory(tmp_path: Path, document: dict | None = None) -> Path:
    path = tmp_path / "project_memory.json"
    path.write_text(
        json.dumps(
            document if document is not None else _memory_document(), indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _service(
    store,
    memory_path: Path,
    clock=FIXED_TIME,
) -> DecisionAuthorityService:
    return DecisionAuthorityService(
        store,
        memory_path,
        clock=(clock if callable(clock) else (lambda: clock)),
    )


def _accept(
    store,
    memory_path: Path,
    proposal_id: str,
    decision_id: str | None = None,
    clock=FIXED_TIME,
) -> AcceptResult:
    return _service(store, memory_path, clock).accept(proposal_id, decision_id)


def _canonical_index(memory_path: Path) -> CanonicalArchitectureIndex:
    store = MemoryStore(memory_path)
    store.load()
    return decisions_to_canonical(store.decisions())


def _memory_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _entry_for(memory_path: Path, decision_id: str) -> dict:
    with open(memory_path, encoding="utf-8") as handle:
        raw = json.load(handle)
    matches = [e for e in raw["decisions"] if e.get("id") == decision_id]
    assert len(matches) == 1, f"expected exactly one entry for {decision_id!r}"
    return matches[0]


def _crash_state(tmp_path: Path):
    """Crash state: proposal accepted with its decision id, decision missing."""
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    decision_id = default_decision_id_of(proposal)
    store = JsonFileDecisionProposalStore(path)
    store.transition_if_proposed(
        proposal.proposal_id, PROPOSAL_STATUS_ACCEPTED, decision_id
    )
    memory = _write_memory(tmp_path)  # memory exists, decision absent
    return store, memory, proposal, decision_id


# ── Store-level authority transition primitive ───────────────────────────────


def test_store_transition_proposed_to_accepted(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    store = JsonFileDecisionProposalStore(path)
    transitioned, transitioned_ok = store.transition_if_proposed(
        proposal.proposal_id, PROPOSAL_STATUS_ACCEPTED, "ddec-x"
    )
    assert transitioned_ok is True
    assert transitioned.status == PROPOSAL_STATUS_ACCEPTED
    assert transitioned.accepted_decision_id == "ddec-x"


def test_store_transition_proposed_to_rejected(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    store = JsonFileDecisionProposalStore(path)
    transitioned, transitioned_ok = store.transition_if_proposed(
        proposal.proposal_id, PROPOSAL_STATUS_REJECTED
    )
    assert transitioned_ok is True
    assert transitioned.status == PROPOSAL_STATUS_REJECTED
    assert transitioned.accepted_decision_id is None


def test_store_transition_already_at_target_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    store = JsonFileDecisionProposalStore(path)
    store.transition_if_proposed(
        proposal.proposal_id, PROPOSAL_STATUS_ACCEPTED, "ddec-x"
    )
    # Same accepted_decision_id -> valid idempotent retry.
    again, transitioned_ok = store.transition_if_proposed(
        proposal.proposal_id, PROPOSAL_STATUS_ACCEPTED, "ddec-x"
    )
    assert transitioned_ok is False
    assert again.status == PROPOSAL_STATUS_ACCEPTED
    assert again.accepted_decision_id == "ddec-x"

    # Different accepted_decision_id -> NOT idempotent: fail closed.
    with pytest.raises(ValueError):
        store.transition_if_proposed(
            proposal.proposal_id, PROPOSAL_STATUS_ACCEPTED, "ddec-other"
        )

    rejected = _propose(
        store, _candidate(statement="Rejected candidate statement.")
    )
    store.transition_if_proposed(
        rejected.proposal_id, PROPOSAL_STATUS_REJECTED
    )
    re_rejected, rejected_ok = store.transition_if_proposed(
        rejected.proposal_id, PROPOSAL_STATUS_REJECTED
    )
    assert rejected_ok is False
    assert re_rejected.status == PROPOSAL_STATUS_REJECTED
    assert re_rejected.accepted_decision_id is None


def test_store_transition_accepted_id_conflict_is_not_idempotent(
    tmp_path: Path,
) -> None:
    """Parity: both store implementations fail closed on a conflicting
    accepted_decision_id for an already-accepted proposal."""
    for make_store in (
        lambda path: JsonFileDecisionProposalStore(path),
        lambda path: InMemoryDecisionProposalStore(),
    ):
        store = make_store(tmp_path / "in-memory-or-file.json")
        proposal = _propose(store)
        stored, created = store.add_if_new(proposal)
        assert created or stored.status == PROPOSAL_STATUS_PROPOSED
        store.transition_if_proposed(
            proposal.proposal_id, PROPOSAL_STATUS_ACCEPTED, "ddec-original"
        )
        with pytest.raises(ValueError):
            store.transition_if_proposed(
                proposal.proposal_id, PROPOSAL_STATUS_ACCEPTED, "ddec-other"
            )
        # The stored id is unchanged after the failed conflict.
        assert store.get(proposal.proposal_id).accepted_decision_id == (
            "ddec-original"
        )
        # Terminal accepted->rejected and rejected->accepted still fail.
        with pytest.raises(ValueError):
            store.transition_if_proposed(
                proposal.proposal_id, PROPOSAL_STATUS_REJECTED
            )


def test_store_transition_from_terminal_status_fails(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    store = JsonFileDecisionProposalStore(path)
    # accepted -> rejected fails closed.
    store.transition_if_proposed(
        proposal.proposal_id, PROPOSAL_STATUS_ACCEPTED, "ddec-x"
    )
    with pytest.raises(ValueError):
        store.transition_if_proposed(
            proposal.proposal_id, PROPOSAL_STATUS_REJECTED
        )
    # rejected -> accepted fails closed.
    rejected = _propose(
        store, _candidate(statement="Rejected candidate statement.")
    )
    store.transition_if_proposed(
        rejected.proposal_id, PROPOSAL_STATUS_REJECTED
    )
    with pytest.raises(ValueError):
        store.transition_if_proposed(
            rejected.proposal_id, PROPOSAL_STATUS_ACCEPTED, "ddec-x"
        )


def test_store_transition_unknown_id_fails(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    _propose(JsonFileDecisionProposalStore(path))
    store = JsonFileDecisionProposalStore(path)
    with pytest.raises(ValueError):
        store.transition_if_proposed(
            "dprop-unknown", PROPOSAL_STATUS_ACCEPTED, "ddec-x"
        )
    with pytest.raises(ValueError):
        store.transition_if_proposed(
            "dprop-unknown", PROPOSAL_STATUS_REJECTED
        )


def test_store_transition_invalid_args_fail(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    store = JsonFileDecisionProposalStore(path)
    with pytest.raises(ValueError):
        store.transition_if_proposed(
            proposal.proposal_id, PROPOSAL_STATUS_ACCEPTED
        )
    with pytest.raises(ValueError):
        store.transition_if_proposed(
            proposal.proposal_id, PROPOSAL_STATUS_REJECTED, "ddec-x"
        )
    with pytest.raises(ValueError):
        store.transition_if_proposed(proposal.proposal_id, "superseded")
    with pytest.raises(ValueError):
        store.transition_if_proposed(
            proposal.proposal_id, PROPOSAL_STATUS_ACCEPTED, ""
        )


def test_store_file_transition_persists_and_reloads(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    store = JsonFileDecisionProposalStore(path)
    store.transition_if_proposed(
        proposal.proposal_id, PROPOSAL_STATUS_ACCEPTED, "ddec-x"
    )
    reloaded = JsonFileDecisionProposalStore(path)
    stored = reloaded.get(proposal.proposal_id)
    assert stored is not None
    assert stored.status == PROPOSAL_STATUS_ACCEPTED
    assert stored.accepted_decision_id == "ddec-x"


def test_store_file_transition_preserves_other_records_and_order(
    tmp_path: Path,
) -> None:
    path = tmp_path / "p.json"
    first = _propose(JsonFileDecisionProposalStore(path), _candidate())
    second = _propose(
        JsonFileDecisionProposalStore(path),
        _candidate(statement="Second decision statement."),
    )
    store = JsonFileDecisionProposalStore(path)
    store.transition_if_proposed(
        second.proposal_id, PROPOSAL_STATUS_ACCEPTED, "ddec-second"
    )
    reloaded = JsonFileDecisionProposalStore(path)
    assert [p.proposal_id for p in reloaded.list_proposals()] == [
        first.proposal_id,
        second.proposal_id,
    ]
    kept = reloaded.get(first.proposal_id)
    assert kept is not None
    assert kept.status == PROPOSAL_STATUS_PROPOSED
    assert kept.accepted_decision_id is None
    assert kept.candidate == first.candidate
    assert kept.producer_key == first.producer_key
    assert kept.content_fingerprint == first.content_fingerprint
    assert kept.proposed_at == first.proposed_at


def test_store_transition_keeps_candidate_immutable(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    store = JsonFileDecisionProposalStore(path)
    transitioned, _ = store.transition_if_proposed(
        proposal.proposal_id, PROPOSAL_STATUS_ACCEPTED, "ddec-x"
    )
    assert transitioned.candidate == proposal.candidate
    assert transitioned.producer_key == proposal.producer_key
    assert transitioned.content_fingerprint == proposal.content_fingerprint
    assert transitioned.proposed_at == proposal.proposed_at
    assert transitioned.proposal_id == proposal.proposal_id


def test_in_memory_store_transition_matches_file_store(tmp_path: Path) -> None:
    proposal = _propose(InMemoryDecisionProposalStore())
    store = InMemoryDecisionProposalStore()
    store.add_if_new(proposal)
    transitioned, transitioned_ok = store.transition_if_proposed(
        proposal.proposal_id, PROPOSAL_STATUS_ACCEPTED, "ddec-x"
    )
    assert transitioned_ok is True
    assert transitioned.status == PROPOSAL_STATUS_ACCEPTED
    assert transitioned.accepted_decision_id == "ddec-x"

    # Same accepted_decision_id -> idempotent; different -> fail closed.
    again, idempotent = store.transition_if_proposed(
        proposal.proposal_id, PROPOSAL_STATUS_ACCEPTED, "ddec-x"
    )
    assert idempotent is False
    assert again.accepted_decision_id == "ddec-x"
    with pytest.raises(ValueError):
        store.transition_if_proposed(
            proposal.proposal_id, PROPOSAL_STATUS_ACCEPTED, "ddec-other"
        )


# ── Acceptance: normal successful path ───────────────────────────────────────


def test_accept_proposed_to_accepted_works(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    assert isinstance(result, AcceptResult)
    assert result.proposal_id == proposal.proposal_id
    assert result.proposal_status == PROPOSAL_STATUS_ACCEPTED
    assert result.materialized is True
    assert result.already_accepted is False
    assert result.recovered is False
    assert result.verified is True
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert stored.status == PROPOSAL_STATUS_ACCEPTED


def test_accept_records_accepted_decision_id(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert stored.accepted_decision_id == result.decision_id
    assert stored.accepted_decision_id


def test_accept_works_with_in_memory_store(tmp_path: Path) -> None:
    store = InMemoryDecisionProposalStore()
    proposal = _propose(store)
    memory = _write_memory(tmp_path)
    result = _service(store, memory).accept(proposal.proposal_id)
    assert result.verified is True
    assert result.materialized is True
    stored = store.get(proposal.proposal_id)
    assert stored is not None
    assert stored.status == PROPOSAL_STATUS_ACCEPTED
    assert stored.accepted_decision_id == result.decision_id


def test_accept_creates_exactly_one_decisions_entry(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    with open(memory, encoding="utf-8") as handle:
        raw = json.load(handle)
    assert len(raw["decisions"]) == 1
    assert raw["decisions"][0]["id"] == result.decision_id


def test_accept_maps_statement_rationale_scope_exactly(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    entry = _entry_for(memory, result.decision_id)
    assert entry["decision"] == proposal.candidate.statement
    assert entry["rationale"] == proposal.candidate.rationale
    assert entry["scope"] == list(proposal.candidate.scope_hints)


def test_accept_materializes_empty_constraints(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    assert _entry_for(memory, result.decision_id)["constraints"] == []


def test_accept_materializes_empty_anti_patterns(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    assert _entry_for(memory, result.decision_id)["anti_patterns"] == []


def test_accept_materializes_empty_rules(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    assert _entry_for(memory, result.decision_id)["rules"] == []


def test_accept_materializes_empty_test_evidence(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    assert _entry_for(memory, result.decision_id)["test_evidence"] == []


def test_accept_materializes_status_active(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    assert _entry_for(memory, result.decision_id)["status"] == "active"
    runtime = MemoryStore(memory)
    runtime.load()
    decision = next(d for d in runtime.decisions() if d.id == result.decision_id)
    assert decision.status == "active"


def test_accept_timestamps_are_authority_clock_owned(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    entry = _entry_for(memory, result.decision_id)
    assert entry["created_at"] == FIXED_TIME
    assert entry["updated_at"] == FIXED_TIME

    second = _propose(
        JsonFileDecisionProposalStore(path),
        _candidate(statement="Second statement."),
    )
    second_result = _accept(
        JsonFileDecisionProposalStore(path),
        memory,
        second.proposal_id,
        clock=LATER_TIME,
    )
    second_entry = _entry_for(memory, second_result.decision_id)
    assert second_entry["created_at"] == LATER_TIME
    assert second_entry["updated_at"] == LATER_TIME
    # The first entry's authority timestamps are untouched by the later call.
    assert _entry_for(memory, result.decision_id)["created_at"] == FIXED_TIME


def test_accept_scope_hints_never_become_adr020_applicability(
    tmp_path: Path,
) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    entry = _entry_for(memory, result.decision_id)
    assert entry["rules"] == []
    serialized = json.dumps(entry)
    assert "include_paths" not in serialized
    assert "exclude_paths" not in serialized
    index = _canonical_index(memory)
    assert index.rules_for_decision(result.decision_id) == ()
    runtime = MemoryStore(memory)
    runtime.load()
    decision = next(d for d in runtime.decisions() if d.id == result.decision_id)
    assert decision.rules == []
    assert list(decision.scope) == list(proposal.candidate.scope_hints)


def test_accept_title_is_not_materialized(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    entry = _entry_for(memory, result.decision_id)
    assert "title" not in entry
    assert proposal.candidate.title not in json.dumps(entry)


def test_accept_keeps_proposal_content_and_provenance_unchanged(
    tmp_path: Path,
) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert stored.candidate == proposal.candidate
    assert stored.producer_key == proposal.producer_key
    assert stored.content_fingerprint == proposal.content_fingerprint
    assert stored.proposed_at == proposal.proposed_at
    assert stored.proposal_id == proposal.proposal_id


# ── Canonical decision identity ──────────────────────────────────────────────


def test_default_decision_id_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    expected = default_decision_id_of(proposal)
    assert default_decision_id_of(proposal) == expected
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    assert result.decision_id == expected
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert default_decision_id_of(stored) == expected


def test_default_decision_id_matches_pinned_algorithm() -> None:
    proposal = _propose(InMemoryDecisionProposalStore())
    expected = "ddec-" + hashlib.sha256(
        json.dumps(
            [
                proposal.proposal_id,
                proposal.producer_key,
                proposal.content_fingerprint,
            ],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()[:32]
    assert default_decision_id_of(proposal) == expected
    # Pinned golden vector over the documented derivation with fixed input.
    assert (
        "ddec-"
        + hashlib.sha256(
            json.dumps(
                ["dprop-fixed", "producer-key-fixed", "content-fp-fixed"],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()[:32]
        == "ddec-832ab13f18f4f9ad00b957b12a9cde5e"
    )


def test_proposal_and_decision_namespaces_are_distinct() -> None:
    proposal = _propose(InMemoryDecisionProposalStore())
    decision_id = default_decision_id_of(proposal)
    assert proposal.proposal_id.startswith("dprop-")
    assert decision_id.startswith("ddec-")
    assert proposal.proposal_id != decision_id


def test_different_proposals_yield_different_default_ids(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    first = _propose(JsonFileDecisionProposalStore(path), _candidate())
    second = _propose(
        JsonFileDecisionProposalStore(path),
        _candidate(statement="Changed statement."),
    )
    assert default_decision_id_of(first) != default_decision_id_of(second)

    # Identical resend reuses the existing proposal and its default id.
    resend = DecisionIndexService(
        JsonFileDecisionProposalStore(path), clock=lambda: LATER_TIME
    ).propose(_candidate())
    assert resend.created is False
    assert resend.proposal.proposal_id == first.proposal_id
    assert default_decision_id_of(resend.proposal) == default_decision_id_of(first)


def test_explicit_decision_id_is_used(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(
        JsonFileDecisionProposalStore(path),
        memory,
        proposal.proposal_id,
        decision_id="ddec-human-assigned",
    )
    assert result.decision_id == "ddec-human-assigned"
    entry = _entry_for(memory, "ddec-human-assigned")
    assert entry["decision"] == proposal.candidate.statement
    record = next(
        r for r in _canonical_index(memory).records
        if r.decision_id == "ddec-human-assigned"
    )
    assert record.statement == proposal.candidate.statement


def test_explicit_decision_id_colliding_with_proposal_namespace_fails(
    tmp_path: Path,
) -> None:
    path = tmp_path / "p.json"
    first = _propose(JsonFileDecisionProposalStore(path), _candidate())
    second = _propose(
        JsonFileDecisionProposalStore(path),
        _candidate(statement="Second statement."),
    )
    memory = _write_memory(tmp_path)
    with pytest.raises(DecisionIdNamespaceError):
        _accept(
            JsonFileDecisionProposalStore(path),
            memory,
            second.proposal_id,
            decision_id=first.proposal_id,
        )


def test_explicit_decision_id_with_reserved_prefix_rejected(
    tmp_path: Path,
) -> None:
    """A canonical decision id must never inhabit the reserved dprop-
    proposal namespace, even when no proposal with that exact id exists."""
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    with pytest.raises(DecisionIdNamespaceError):
        _accept(
            JsonFileDecisionProposalStore(path),
            memory,
            proposal.proposal_id,
            decision_id="dprop-arbitrary",
        )
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert stored.status == PROPOSAL_STATUS_PROPOSED


def test_explicit_non_ddec_human_id_is_allowed(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(
        JsonFileDecisionProposalStore(path),
        memory,
        proposal.proposal_id,
        decision_id="arch-storage-standard",
    )
    assert result.decision_id == "arch-storage-standard"
    assert _entry_for(memory, "arch-storage-standard")["decision"] == (
        proposal.candidate.statement
    )


def test_default_id_remains_ddec_namespace(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    assert default_decision_id_of(proposal).startswith("ddec-")
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    assert result.decision_id == default_decision_id_of(proposal)
    assert result.decision_id.startswith("ddec-")


def test_accept_retry_tolerates_downstream_protection_enrichment(
    tmp_path: Path,
) -> None:
    """Legitimate downstream enrichment must survive an acceptance retry.

    The rule here is created by the existing protection subsystem's write
    primitive AFTER acceptance; D2C did not create it. The retry must not
    treat the enrichment as an ID collision, must not delete or rewrite
    it, and must still return the idempotent already-accepted result.
    """
    from mneme.protection import _install_rule
    from mneme.schemas import Rule

    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    decision_id = result.decision_id

    # At acceptance time the decision is bare: D2C created no rule.
    bare_entry = _entry_for(memory, decision_id)
    assert bare_entry["rules"] == []
    assert _canonical_index(memory).rules_for_decision(decision_id) == ()

    # Legitimate downstream protection via the existing protection write
    # primitive (the exact primitive protection activation uses).
    rule = Rule(type="FORBID_LITERAL", value="legacy_client")
    assert _install_rule(memory, decision_id, rule) is True
    enriched_entry = _entry_for(memory, decision_id)
    assert enriched_entry["rules"] == [
        {"type": "FORBID_LITERAL", "value": "legacy_client"}
    ]
    snapshot = _memory_bytes(memory)

    # Retry acceptance: idempotent success, no rewrite, rule intact.
    retry = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    assert retry.proposal_id == proposal.proposal_id
    assert retry.decision_id == decision_id
    assert retry.already_accepted is True
    assert retry.materialized is False
    assert retry.recovered is False
    assert retry.verified is True
    assert _memory_bytes(memory) == snapshot
    after_entry = _entry_for(memory, decision_id)
    assert after_entry["rules"] == enriched_entry["rules"]
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert stored.accepted_decision_id == decision_id

    # The canonical record keeps the downstream-derived rule linkage that
    # D2C itself did not create.
    record = next(
        r for r in _canonical_index(memory).records
        if r.decision_id == decision_id
    )
    assert record.derived_rule_ids == (f"{decision_id}:FORBID_LITERAL:0",)


def test_accept_retry_tolerates_declared_test_evidence_linkage(
    tmp_path: Path,
) -> None:
    """Declared test evidence added after acceptance is downstream
    enrichment: a retry must neither claim nor remove it."""
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    decision_id = result.decision_id
    with open(memory, encoding="utf-8") as handle:
        raw = json.load(handle)
    entry = next(e for e in raw["decisions"] if e.get("id") == decision_id)
    entry["test_evidence"] = [
        {"selector": "tests/test_downstream.py::test_rule", "sha": ""}
    ]
    memory.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    snapshot = _memory_bytes(memory)

    retry = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    assert retry.already_accepted is True
    assert retry.materialized is False
    assert retry.verified is True
    assert _memory_bytes(memory) == snapshot
    assert _entry_for(memory, decision_id)["test_evidence"] == [
        {"selector": "tests/test_downstream.py::test_rule", "sha": ""}
    ]


def test_explicit_decision_id_empty_fails(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    with pytest.raises(DecisionIdNamespaceError):
        _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id, "")


def test_accept_without_explicit_id_uses_default(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    expected = default_decision_id_of(proposal)
    memory = _write_memory(tmp_path)
    result = _accept(
        JsonFileDecisionProposalStore(path), memory, proposal.proposal_id, None
    )
    assert result.decision_id == expected


def test_accept_on_unknown_proposal_fails_closed(tmp_path: Path) -> None:
    memory = _write_memory(tmp_path)
    service = _service(InMemoryDecisionProposalStore(), memory)
    with pytest.raises(ProposalNotFoundError):
        service.accept("dprop-unknown")
    with pytest.raises(ProposalNotFoundError):
        service.reject("dprop-unknown")


# ── Recovery / idempotency ───────────────────────────────────────────────────


def test_crash_after_proposal_transition_recovers_idempotently(
    tmp_path: Path,
) -> None:
    store, memory, proposal, decision_id = _crash_state(tmp_path)
    result = _service(store, memory).accept(proposal.proposal_id)
    assert result.decision_id == decision_id
    assert result.already_accepted is True
    assert result.recovered is True
    assert result.materialized is True
    assert result.verified is True
    entry = _entry_for(memory, decision_id)
    assert entry["decision"] == proposal.candidate.statement
    assert entry["status"] == "active"
    assert len(json.loads(memory.read_text(encoding="utf-8"))["decisions"]) == 1
    stored = store.get(proposal.proposal_id)
    assert stored is not None
    assert stored.accepted_decision_id == decision_id


def test_fully_accepted_retry_creates_no_duplicate(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    first = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    entry_before = json.dumps(_entry_for(memory, first.decision_id), sort_keys=True)
    snapshot = _memory_bytes(memory)

    result = _service(JsonFileDecisionProposalStore(path), memory).accept(
        proposal.proposal_id
    )
    assert result.already_accepted is True
    assert result.materialized is False
    assert result.recovered is False
    assert result.verified is True
    assert result.decision_id == first.decision_id
    assert len(json.loads(memory.read_text(encoding="utf-8"))["decisions"]) == 1
    assert json.dumps(_entry_for(memory, first.decision_id), sort_keys=True) == entry_before
    assert _memory_bytes(memory) == snapshot

    # An explicit retry with the SAME stored id is equally idempotent.
    same_id_retry = _accept(
        JsonFileDecisionProposalStore(path),
        memory,
        proposal.proposal_id,
        decision_id=first.decision_id,
    )
    assert same_id_retry.already_accepted is True
    assert same_id_retry.materialized is False
    assert _memory_bytes(memory) == snapshot


def test_proposed_plus_existing_decision_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    decision_id = default_decision_id_of(proposal)
    memory = _write_memory(tmp_path)
    with open(memory, encoding="utf-8") as handle:
        raw = json.load(handle)
    raw["decisions"].append(
        expected_materialization_entry(proposal, decision_id, FIXED_TIME)
    )
    memory.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    snapshot = _memory_bytes(memory)

    with pytest.raises(ReverseHalfStateError):
        _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert stored.status == PROPOSAL_STATUS_PROPOSED
    assert stored.accepted_decision_id is None
    assert _memory_bytes(memory) == snapshot

    # The same guard applies to a mismatching existing entry.
    with open(memory, encoding="utf-8") as handle:
        raw = json.load(handle)
    raw["decisions"][0]["decision"] = "Different statement entirely."
    memory.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ReverseHalfStateError):
        _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert stored.status == PROPOSAL_STATUS_PROPOSED


def test_same_id_different_content_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    with open(memory, encoding="utf-8") as handle:
        raw = json.load(handle)
    raw["decisions"][0]["rationale"] = "Tampered rationale."
    memory.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    tampered = _memory_bytes(memory)

    with pytest.raises(DecisionIdCollisionError):
        _service(JsonFileDecisionProposalStore(path), memory).accept(
            proposal.proposal_id
        )
    with pytest.raises(DecisionIdCollisionError):
        _accept(
            JsonFileDecisionProposalStore(path),
            memory,
            proposal.proposal_id,
            decision_id=result.decision_id,
        )
    assert _memory_bytes(memory) == tampered
    assert len(json.loads(memory.read_text(encoding="utf-8"))["decisions"]) == 1


def test_success_only_after_runtime_and_canonical_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    real_load = MemoryStore.load
    calls = {"n": 0}

    def flaky_load(store_self):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("simulated verification failure")
        return real_load(store_self)

    monkeypatch.setattr(MemoryStore, "load", flaky_load)
    with pytest.raises(DecisionAuthorityError):
        _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    monkeypatch.undo()

    # The writes happened (proposal transitioned, decision present) but no
    # success was ever reported for the failed verification.
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert stored.status == PROPOSAL_STATUS_ACCEPTED
    assert stored.accepted_decision_id is not None
    decision_id = stored.accepted_decision_id
    assert len(json.loads(memory.read_text(encoding="utf-8"))["decisions"]) == 1

    # Retry completes idempotently and verifies both representations.
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    assert result.decision_id == decision_id
    assert result.already_accepted is True
    assert result.materialized is False
    assert result.recovered is False
    assert result.verified is True


# ── Memory validation before mutation ────────────────────────────────────────


def test_accept_missing_memory_fails_before_mutation(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    store = JsonFileDecisionProposalStore(path)
    with pytest.raises(MemoryMissingError):
        _service(store, tmp_path / "absent.json").accept(proposal.proposal_id)
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert stored.status == PROPOSAL_STATUS_PROPOSED
    assert stored.accepted_decision_id is None


def test_accept_invalid_memory_json_fails_before_mutation(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    store = JsonFileDecisionProposalStore(path)
    memory = tmp_path / "project_memory.json"
    memory.write_text("{not json", encoding="utf-8")
    with pytest.raises(MemoryInvalidError):
        _service(store, memory).accept(proposal.proposal_id)
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert stored.status == PROPOSAL_STATUS_PROPOSED


def test_accept_memory_without_meta_fails_before_mutation(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    store = JsonFileDecisionProposalStore(path)
    memory = _write_memory(tmp_path, {"decisions": []})
    with pytest.raises(MemoryInvalidError):
        _service(store, memory).accept(proposal.proposal_id)
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert stored.status == PROPOSAL_STATUS_PROPOSED


def test_accept_memory_decisions_not_a_list_fails(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    store = JsonFileDecisionProposalStore(path)
    memory = _write_memory(tmp_path, {**_memory_document(), "decisions": {}})
    with pytest.raises(MemoryInvalidError):
        _service(store, memory).accept(proposal.proposal_id)
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert stored.status == PROPOSAL_STATUS_PROPOSED


def test_accept_memory_non_object_fails(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    store = JsonFileDecisionProposalStore(path)
    memory = _write_memory(tmp_path, ["not", "an", "object"])
    with pytest.raises(MemoryInvalidError):
        _service(store, memory).accept(proposal.proposal_id)
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert stored.status == PROPOSAL_STATUS_PROPOSED


def test_accept_memory_with_non_object_decision_entry_fails(
    tmp_path: Path,
) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    store = JsonFileDecisionProposalStore(path)
    memory = _write_memory(
        tmp_path, {**_memory_document(), "decisions": ["oops"]}
    )
    with pytest.raises(MemoryInvalidError):
        _service(store, memory).accept(proposal.proposal_id)
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert stored.status == PROPOSAL_STATUS_PROPOSED


def test_accept_missing_decisions_key_initializes_list(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    store = JsonFileDecisionProposalStore(path)
    memory = _write_memory(
        tmp_path,
        {"meta": _memory_document()["meta"], "items": [], "examples": []},
    )
    result = _service(store, memory).accept(proposal.proposal_id)
    assert result.materialized is True
    assert result.verified is True
    assert len(json.loads(memory.read_text(encoding="utf-8"))["decisions"]) == 1


# ── Terminal-state authority rules ──────────────────────────────────────────


def test_accept_rejected_proposal_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    store = JsonFileDecisionProposalStore(path)
    _service(store, memory).reject(proposal.proposal_id)
    snapshot = _memory_bytes(memory)
    with pytest.raises(ProposalAlreadyRejectedError):
        _accept(store, memory, proposal.proposal_id)
    assert _memory_bytes(memory) == snapshot


def test_reject_accepted_proposal_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    store = JsonFileDecisionProposalStore(path)
    _accept(store, memory, proposal.proposal_id)
    snapshot = _memory_bytes(memory)
    with pytest.raises(ProposalAlreadyAcceptedError):
        _service(store, memory).reject(proposal.proposal_id)
    assert _memory_bytes(memory) == snapshot


# ── Canonical projection of the materialized decision ────────────────────────


def test_materialized_decision_projects_to_canonical_record(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    index = _canonical_index(memory)
    record = next(r for r in index.records if r.decision_id == result.decision_id)
    assert record.version == CANONICAL_VERSION == "1"
    assert record.lifecycle_status == "active"
    assert record.statement == proposal.candidate.statement
    assert record.rationale == proposal.candidate.rationale
    assert record.context_scope == tuple(proposal.candidate.scope_hints)
    assert record.constraints == ()
    assert record.anti_patterns == ()
    assert record.derived_rule_ids == ()
    assert record.test_evidence == ()
    assert index.rules_for_decision(result.decision_id) == ()


def test_materialized_decision_carries_no_fabricated_provenance(
    tmp_path: Path,
) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    entry = _entry_for(memory, result.decision_id)
    assert "source" not in entry
    record = next(
        r for r in _canonical_index(memory).records
        if r.decision_id == result.decision_id
    )
    assert record.source_evidence == ()


def test_materialized_memory_loads_through_existing_memorystore(
    tmp_path: Path,
) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _accept(JsonFileDecisionProposalStore(path), memory, proposal.proposal_id)
    store = MemoryStore(memory)
    loaded = store.load()
    assert isinstance(loaded.meta.name, str)
    decisions = store.decisions()
    runtime_decision = next(d for d in decisions if d.id == result.decision_id)
    assert runtime_decision.rules == []
    assert runtime_decision.test_evidence == []
    assert runtime_decision.status == "active"


# ── Rejection ────────────────────────────────────────────────────────────────


def test_reject_proposed_to_rejected_works(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    result = _service(JsonFileDecisionProposalStore(path), memory).reject(
        proposal.proposal_id
    )
    assert isinstance(result, RejectResult)
    assert result.proposal_id == proposal.proposal_id
    assert result.proposal_status == PROPOSAL_STATUS_REJECTED
    assert result.already_rejected is False
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert stored.status == PROPOSAL_STATUS_REJECTED
    assert stored.accepted_decision_id is None


def test_rejection_does_not_touch_project_memory(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    snapshot = _memory_bytes(memory)
    _service(JsonFileDecisionProposalStore(path), memory).reject(
        proposal.proposal_id
    )
    assert _memory_bytes(memory) == snapshot


def test_rejection_produces_no_canonical_record(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    _service(JsonFileDecisionProposalStore(path), memory).reject(
        proposal.proposal_id
    )
    store = MemoryStore(memory)
    store.load()
    assert store.decisions() == []
    assert _canonical_index(memory).records == ()


def test_repeated_rejection_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    service = _service(JsonFileDecisionProposalStore(path), memory)
    first = service.reject(proposal.proposal_id)
    snapshot = _memory_bytes(memory)
    second = service.reject(proposal.proposal_id)
    assert second.proposal_status == PROPOSAL_STATUS_REJECTED
    assert second.already_rejected is True
    assert first.proposal_status == second.proposal_status
    assert _memory_bytes(memory) == snapshot
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert stored.candidate == proposal.candidate


def test_rejected_proposal_remains_inspectable(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    memory = _write_memory(tmp_path)
    _service(JsonFileDecisionProposalStore(path), memory).reject(
        proposal.proposal_id
    )
    stored = JsonFileDecisionProposalStore(path).get(proposal.proposal_id)
    assert stored is not None
    assert stored.candidate == proposal.candidate
    assert stored.producer_key == proposal.producer_key
    assert stored.content_fingerprint == proposal.content_fingerprint
    assert stored.proposed_at == proposal.proposed_at


# ── Producer boundary remains intact ────────────────────────────────────────


def test_producer_service_cannot_create_accepted_or_rejected_state() -> None:
    service = DecisionIndexService(InMemoryDecisionProposalStore())
    for forbidden in ("accept", "reject", "activate", "supersede"):
        assert not hasattr(service, forbidden)
    result = service.propose(_candidate())
    assert result.proposal.status == PROPOSAL_STATUS_PROPOSED
    assert result.proposal.accepted_decision_id is None


def test_producer_store_add_if_new_cannot_change_status(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    proposal = _propose(JsonFileDecisionProposalStore(path))
    store = JsonFileDecisionProposalStore(path)
    attacker = DecisionProposal(
        proposal_id=proposal.proposal_id,
        status=PROPOSAL_STATUS_ACCEPTED,
        candidate=proposal.candidate,
        producer_key=proposal.producer_key,
        content_fingerprint=proposal.content_fingerprint,
        proposed_at=proposal.proposed_at,
        accepted_decision_id="ddec-attacker",
    )
    stored, created = store.add_if_new(attacker)
    assert created is False
    assert stored.status == PROPOSAL_STATUS_PROPOSED
    assert stored.accepted_decision_id is None


def test_proposal_persistence_never_touches_project_memory(
    tmp_path: Path,
) -> None:
    path = tmp_path / "p.json"
    store = JsonFileDecisionProposalStore(path)
    memory = _write_memory(tmp_path)
    snapshot = _memory_bytes(memory)
    _propose(store, _candidate())
    _propose(store, _candidate(statement="Second statement."))
    assert _memory_bytes(memory) == snapshot


# ── Architecture: independence and frozen boundaries ─────────────────────────


def test_authority_module_has_no_mcp_dependency_in_source() -> None:
    source = AUTHORITY_MODULE.read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            assert "mcp" not in stripped.lower(), stripped
    assert "mneme.cli" not in source
    assert "decision_mcp" not in source


def test_authority_module_imports_only_allowed_modules() -> None:
    source = AUTHORITY_MODULE.read_text(encoding="utf-8")
    allowed_mneme_imports = (
        "mneme.decision_index",
        "mneme.decision_proposal",
        "mneme.decision_proposal_store",
        "mneme.memory_store",
        "mneme.setup_state",
    )
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("from mneme"):
            assert any(
                stripped.startswith(f"from {module}")
                for module in allowed_mneme_imports
            ), stripped


def test_importing_authority_module_does_not_load_mcp() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import mneme.decision_authority; "
            "bad = [m for m in sys.modules if m == 'mcp' or "
            "m.startswith('mcp.') or m == 'mneme.decision_mcp']; "
            "assert not bad, bad; print('ok')",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert "ok" in completed.stdout


def test_mcp_six_tool_inventory_unchanged() -> None:
    from mneme.decision_mcp import APPROVED_TOOLS as MCP_APPROVED_TOOLS

    assert tuple(sorted(MCP_APPROVED_TOOLS)) == tuple(sorted(APPROVED_TOOLS))


def test_mcp_module_has_no_authority_operation() -> None:
    source = MCP_MODULE.read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_AUTHORITY_TOOL_NAMES:
        assert forbidden not in source
    assert "decision_authority" not in source
    assert "DecisionAuthorityService" not in source


def test_no_authority_tool_aliases_exist() -> None:
    from mneme.decision_mcp import APPROVED_TOOLS as MCP_APPROVED_TOOLS

    exposed = {t.replace("decision.", "") for t in MCP_APPROVED_TOOLS}
    for forbidden in FORBIDDEN_AUTHORITY_TOOL_NAMES:
        assert forbidden not in MCP_APPROVED_TOOLS
        assert forbidden.replace("decision.", "") not in exposed


def test_cli_imports_only_the_authority_surface() -> None:
    """D2C2 amendment: the CLI may now be a thin authority adapter, but it
    must reach the Core authority layer ONLY through
    ``DecisionAuthorityService`` / ``DecisionAuthorityError`` and must not
    touch authority primitives directly."""
    source = CLI_MODULE.read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("from mneme.decision_authority"):
            assert "DecisionAuthorityService" in stripped
            assert "DecisionAuthorityError" in stripped
    for forbidden in (
        "transition_if_proposed",
        "atomic_write_json",
        "default_decision_id_of",
        "expected_materialization_entry",
        "decisions_to_canonical",
    ):
        assert forbidden not in source


def test_authority_error_taxonomy_is_narrow() -> None:
    error_types = [
        getattr(da, name)
        for name in da.__all__
        if isinstance(getattr(da, name), type)
        and issubclass(getattr(da, name), Exception)
    ]
    required = (
        ProposalNotFoundError,
        ProposalAlreadyRejectedError,
        ProposalAlreadyAcceptedError,
        AcceptedProposalIdConflictError,
        ProposalStoreCorruptError,
        MemoryMissingError,
        MemoryInvalidError,
        DecisionIdCollisionError,
        DecisionIdNamespaceError,
        MaterializationVerificationError,
        CanonicalVerificationError,
    )
    for error_type in required:
        assert error_type in error_types
        assert issubclass(error_type, DecisionAuthorityError)
    assert len(error_types) == 12

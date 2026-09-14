"""D2A proposal domain + store tests (ADR-027, issue #365 PR A).

Covers the frozen proposal model, deterministic identity/idempotency,
lossless provenance round trips, and the local store semantics
(append-preserving history, no silent overwrite, no contact with
``.mneme/project_memory.json``).
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from mneme.decision_proposal import (
    ORIGIN_AI_GENERATED,
    ORIGIN_HUMAN_AUTHORED,
    ORIGIN_IMPORTED_UNKNOWN,
    PROPOSAL_STATUS_ACCEPTED,
    PROPOSAL_STATUS_PROPOSED,
    PROPOSAL_STATUS_REJECTED,
    VALID_ORIGIN_CLASSIFICATIONS,
    VALID_PROPOSAL_STATUSES,
    DecisionProposal,
    DecisionProposalCandidate,
    DecisionProposalSourceProvenance,
    candidate_from_dict,
    candidate_to_dict,
    content_fingerprint_of,
    producer_key_of,
    proposal_from_dict,
    proposal_id_of,
    proposal_to_dict,
    provenance_from_dict,
    provenance_to_dict,
)
from mneme.decision_proposal_store import (
    InMemoryDecisionProposalStore,
    JsonFileDecisionProposalStore,
)


def _provenance(
    producer_name: str = "arch-agent",
    producer_type: str = "architecture agent",
    source_reference: str = "design/2026-09/storage.md",
    external_source_id: str = "DEC-101",
    source_version: str = "commit-abc123",
    repository_locator: str = "github.com/acme/widget",
    origin_classification: str = ORIGIN_AI_GENERATED,
) -> DecisionProposalSourceProvenance:
    return DecisionProposalSourceProvenance(
        producer_name=producer_name,
        producer_type=producer_type,
        source_reference=source_reference,
        external_source_id=external_source_id,
        source_version=source_version,
        repository_locator=repository_locator,
        origin_classification=origin_classification,
    )


_DEFAULT_PROVENANCE = _provenance()


def _candidate(
    title: str = "Quarantine the legacy client",
    statement: str = "New code must not import legacy_client.",
    rationale: str = "Legacy client is deprecated upstream.",
    provenance: DecisionProposalSourceProvenance | None = _DEFAULT_PROVENANCE,
    scope_hints: tuple[str, ...] = ("storage",),
) -> DecisionProposalCandidate:
    return DecisionProposalCandidate(
        title=title,
        statement=statement,
        rationale=rationale,
        provenance=provenance,
        scope_hints=scope_hints,
        architecture_context={"component": "storage"},
        related_decision_ids=("ADR-9001",),
    )


# ── Model shape / authority boundary ────────────────────────────────────────


def test_candidate_cannot_carry_authoritative_fields():
    field_names = {field.name for field in dataclasses.fields(
        DecisionProposalCandidate
    )}
    authoritative = {
        "status", "accepted_decision_id", "rules", "test_evidence",
        "lifecycle_status", "enforcement", "producer_key", "proposal_id",
    }
    assert not authoritative & field_names
    with pytest.raises(TypeError):
        DecisionProposalCandidate(  # type: ignore[call-arg]
            title="t", statement="s", status=PROPOSAL_STATUS_ACCEPTED,
        )
    with pytest.raises(TypeError):
        DecisionProposalCandidate(  # type: ignore[call-arg]
            title="t", statement="s", accepted_decision_id="ADR-1",
        )


def test_candidate_rejects_evidence_like_metadata():
    with pytest.raises(TypeError):
        DecisionProposalCandidate(  # type: ignore[call-arg]
            title="t", statement="s", test_evidence=[{"selector": "x"}],
        )
    with pytest.raises(TypeError):
        DecisionProposalSourceProvenance(  # type: ignore[call-arg]
            producer_name="p", producer_type="t", source_reference="s",
            verified=True,
        )


def test_candidate_validates_required_content_fail_closed():
    with pytest.raises(ValueError):
        DecisionProposalCandidate(title="", statement="s")
    with pytest.raises(ValueError):
        DecisionProposalCandidate(title="t", statement="")
    with pytest.raises(ValueError):
        _provenance(producer_name="")
    with pytest.raises(ValueError):
        _provenance(origin_classification="trusted")


def test_proposal_model_represents_all_adr027_statuses():
    assert VALID_PROPOSAL_STATUSES == {
        PROPOSAL_STATUS_PROPOSED,
        PROPOSAL_STATUS_ACCEPTED,
        PROPOSAL_STATUS_REJECTED,
    }
    # accepted requires a canonical decision id; proposed/rejected must
    # not carry one (domain invariant, fail closed).
    statuses_and_ids = (
        (PROPOSAL_STATUS_ACCEPTED, "ADR-9001"),
        (PROPOSAL_STATUS_PROPOSED, None),
        (PROPOSAL_STATUS_REJECTED, None),
    )
    for status, accepted_id in statuses_and_ids:
        proposal = DecisionProposal(
            proposal_id="dprop-" + "0" * 32,
            status=status,
            candidate=_candidate(),
            producer_key=producer_key_of(_provenance()),
            content_fingerprint=content_fingerprint_of(_candidate()),
            proposed_at="2026-09-14T00:00:00Z",
            accepted_decision_id=accepted_id,
        )
        assert proposal.status == status
    with pytest.raises(ValueError):
        DecisionProposal(
            proposal_id="x", status="active", candidate=_candidate(),
            producer_key="k", content_fingerprint="c",
            proposed_at="2026-09-14T00:00:00Z",
        )


def test_accepted_without_accepted_decision_id_fails_closed():
    with pytest.raises(ValueError) as exc:
        DecisionProposal(
            proposal_id="dprop-" + "1" * 32,
            status=PROPOSAL_STATUS_ACCEPTED,
            candidate=_candidate(),
            producer_key="k",
            content_fingerprint="c",
            proposed_at="2026-09-14T00:00:00Z",
        )
    assert "accepted_decision_id" in str(exc.value)


def test_accepted_with_empty_accepted_decision_id_fails_closed():
    with pytest.raises(ValueError):
        DecisionProposal(
            proposal_id="dprop-" + "1" * 32,
            status=PROPOSAL_STATUS_ACCEPTED,
            candidate=_candidate(),
            producer_key="k",
            content_fingerprint="c",
            proposed_at="2026-09-14T00:00:00Z",
            accepted_decision_id="",
        )


def test_proposed_with_accepted_decision_id_fails_closed():
    with pytest.raises(ValueError):
        DecisionProposal(
            proposal_id="dprop-" + "1" * 32,
            status=PROPOSAL_STATUS_PROPOSED,
            candidate=_candidate(),
            producer_key="k",
            content_fingerprint="c",
            proposed_at="2026-09-14T00:00:00Z",
            accepted_decision_id="ADR-9001",
        )


def test_rejected_with_accepted_decision_id_fails_closed():
    with pytest.raises(ValueError):
        DecisionProposal(
            proposal_id="dprop-" + "1" * 32,
            status=PROPOSAL_STATUS_REJECTED,
            candidate=_candidate(),
            producer_key="k",
            content_fingerprint="c",
            proposed_at="2026-09-14T00:00:00Z",
            accepted_decision_id="ADR-9001",
        )


def test_origin_classification_vocabulary():
    assert VALID_ORIGIN_CLASSIFICATIONS == {
        ORIGIN_AI_GENERATED,
        ORIGIN_HUMAN_AUTHORED,
        ORIGIN_IMPORTED_UNKNOWN,
    }


# ── Deterministic identity and idempotency ──────────────────────────────────


def test_identity_is_deterministic_and_excludes_proposed_at():
    first = proposal_id_of(_provenance(), _candidate())
    second = proposal_id_of(_provenance(), _candidate())
    assert first == second
    assert first.startswith("dprop-")
    # proposed_at is not part of identity: the same candidate produces the
    # same id regardless of when it is submitted.
    assert content_fingerprint_of(_candidate()) == content_fingerprint_of(
        _candidate()
    )


def test_changed_content_creates_new_identity():
    base = proposal_id_of(_provenance(), _candidate())
    changed = proposal_id_of(
        _provenance(), _candidate(statement="New code must not import legacy_client v2.")
    )
    assert changed != base


def test_changed_source_version_creates_new_identity():
    base = proposal_id_of(_provenance(), _candidate())
    changed = proposal_id_of(
        _provenance(source_version="commit-def456"), _candidate()
    )
    assert changed != base


def test_absent_optional_components_use_deterministic_fallback():
    absent = _provenance(
        external_source_id="", source_version="", repository_locator=""
    )
    again = _provenance(
        external_source_id="", source_version="", repository_locator=""
    )
    assert proposal_id_of(absent, _candidate()) == proposal_id_of(
        again, _candidate()
    )
    # The fallback is narrow: supplying any component changes the key.
    assert producer_key_of(absent) != producer_key_of(
        _provenance(external_source_id="", source_version="", repository_locator="x")
    )


def test_producer_key_separates_sources_with_identical_content():
    key_a = producer_key_of(_provenance(producer_name="agent-a"))
    key_b = producer_key_of(_provenance(producer_name="agent-b"))
    assert key_a != key_b
    same_content_different_producer = proposal_id_of(
        _provenance(producer_name="agent-b"), _candidate()
    )
    assert same_content_different_producer != proposal_id_of(
        _provenance(producer_name="agent-a"), _candidate()
    )


# ── Lossless serialization round trips ──────────────────────────────────────


def test_provenance_round_trips_losslessly():
    for provenance in (
        _provenance(),
        _provenance(external_source_id="", source_version=""),
        _provenance(origin_classification=ORIGIN_HUMAN_AUTHORED),
        _provenance(origin_classification=ORIGIN_IMPORTED_UNKNOWN),
    ):
        assert provenance_from_dict(provenance_to_dict(provenance)) == provenance


def test_candidate_round_trips_losslessly():
    for candidate in (
        _candidate(),
        _candidate(provenance=None),
        _candidate(scope_hints=(), rationale=""),
    ):
        assert candidate_from_dict(candidate_to_dict(candidate)) == candidate


def test_proposal_round_trips_losslessly():
    proposal = DecisionProposal(
        proposal_id=proposal_id_of(_provenance(), _candidate()),
        status=PROPOSAL_STATUS_PROPOSED,
        candidate=_candidate(),
        producer_key=producer_key_of(_provenance()),
        content_fingerprint=content_fingerprint_of(_candidate()),
        proposed_at="2026-09-14T12:00:00Z",
    )
    assert proposal_from_dict(proposal_to_dict(proposal)) == proposal


# ── Store semantics (both implementations, identical) ────────────────────────


def _proposal(
    proposal_id: str = "dprop-" + "a" * 32,
    candidate: DecisionProposalCandidate | None = None,
) -> DecisionProposal:
    return DecisionProposal(
        proposal_id=proposal_id,
        status=PROPOSAL_STATUS_PROPOSED,
        candidate=candidate if candidate is not None else _candidate(),
        producer_key=producer_key_of(_provenance()),
        content_fingerprint=content_fingerprint_of(
            candidate if candidate is not None else _candidate()
        ),
        proposed_at="2026-09-14T12:00:00Z",
    )


def test_in_memory_store_add_if_new_is_idempotent():
    store = InMemoryDecisionProposalStore()
    proposal = _proposal()
    stored, created = store.add_if_new(proposal)
    assert created is True
    assert stored is proposal
    again, created_again = store.add_if_new(
        _proposal(candidate=dataclasses.replace(proposal.candidate))
    )
    assert created_again is False
    assert again == proposal, "existing record must be returned unchanged"


def test_json_file_store_add_if_new_is_idempotent(tmp_path: Path):
    store = JsonFileDecisionProposalStore(tmp_path / "proposals.json")
    proposal = _proposal()
    stored, created = store.add_if_new(proposal)
    assert created is True
    before = (tmp_path / "proposals.json").read_bytes()
    again, created_again = store.add_if_new(_proposal())
    assert created_again is False
    assert again == proposal
    assert (tmp_path / "proposals.json").read_bytes() == before, (
        "idempotent re-add must not rewrite the file"
    )


def test_stores_preserve_insertion_order_and_history(tmp_path: Path):
    first = _proposal("dprop-" + "1" * 32)
    second = _proposal("dprop-" + "2" * 32)
    stores = (
        InMemoryDecisionProposalStore(),
        JsonFileDecisionProposalStore(tmp_path / "proposals.json"),
    )
    for store in stores:
        store.add_if_new(first)
        store.add_if_new(second)
        assert [p.proposal_id for p in store.list_proposals()] == [
            first.proposal_id, second.proposal_id,
        ]
        assert store.get(first.proposal_id) == first
        assert store.get(second.proposal_id) == second
        assert store.get("dprop-" + "f" * 32) is None


def test_json_store_reload_preserves_ids_history_and_order(tmp_path: Path):
    path = tmp_path / "proposals.json"
    first = _proposal("dprop-" + "1" * 32)
    second = _proposal("dprop-" + "2" * 32, candidate=_candidate(
        title="Second proposal"
    ))
    JsonFileDecisionProposalStore(path).add_if_new(first)
    JsonFileDecisionProposalStore(path).add_if_new(second)

    reloaded = JsonFileDecisionProposalStore(path)
    assert [p.proposal_id for p in reloaded.list_proposals()] == [
        first.proposal_id, second.proposal_id,
    ]
    assert reloaded.get(first.proposal_id) == first
    assert reloaded.get(second.proposal_id) == second
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["schema"] == "mneme.decision-proposals/v1"
    assert len(document["proposals"]) == 2


def test_json_store_fails_closed_on_corrupt_document(tmp_path: Path):
    path = tmp_path / "proposals.json"
    path.write_text('{"schema": "something/else"}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        JsonFileDecisionProposalStore(path)


def test_proposal_persistence_never_touches_project_memory(tmp_path: Path):
    memory_path = tmp_path / ".mneme" / "project_memory.json"
    memory_path.parent.mkdir()
    memory_path.write_text(
        '{"meta": {"name": "t", "description": "t"}, "decisions": []}\n',
        encoding="utf-8",
    )
    before = memory_path.read_bytes()
    store = JsonFileDecisionProposalStore(tmp_path / "decision_proposals.json")
    store.add_if_new(_proposal())
    assert memory_path.read_bytes() == before, (
        "proposal persistence must never modify .mneme/project_memory.json"
    )
    assert sorted(p.name for p in (tmp_path / ".mneme").iterdir()) == [
        "project_memory.json"
    ]

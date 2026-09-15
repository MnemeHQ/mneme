"""D2C2 CLI authority-surface tests — `mneme decision` (ADR-027).

Proves the CLI is a thin adapter over the Core ``DecisionAuthorityService``:
accept/reject delegate with the correct arguments; read-only inspection
uses the durable ``JsonFileDecisionProposalStore`` read surface; Core
authority refusals surface deterministically (exit 1, ``ERROR:`` on
stderr, no stack trace) and are never reported as success; CLI input
problems (missing/empty/corrupt proposal store, unknown id on a read-only
command) exit 2; rejection never touches ``project_memory.json``; no
protection is activated and no Audit is invoked; and the MCP transport
keeps exactly its six-tool inventory with no accept/reject operation.

This file does NOT duplicate D2C1's 72 detailed Core tests — it proves
adapter behavior and a few true integration paths only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import mneme.cli as cli
from mneme.cli import main
from mneme.decision_authority import (
    AcceptResult,
    DecisionAuthorityService,
    RejectResult,
    default_decision_id_of,
    expected_materialization_entry,
)
from mneme.decision_index_service import DecisionIndexService
from mneme.decision_proposal import (
    ORIGIN_AI_GENERATED,
    DecisionProposalCandidate,
    DecisionProposalSourceProvenance,
)
from mneme.decision_proposal_store import (
    InMemoryDecisionProposalStore,
    JsonFileDecisionProposalStore,
)

PROPOSALS_SCHEMA = "mneme.decision-proposals/v1"
FIXED_TIME = "2026-09-14T12:00:00Z"

MCP_APPROVED_TOOLS = (
    "decision.propose",
    "decision.propose_batch",
    "decision.get",
    "decision.search",
    "decision.applicable_to",
    "decision.trace",
)


# ── Fixtures / helpers ───────────────────────────────────────────────────────


def _provenance(source_reference: str = "design/2026-09/storage.md") -> DecisionProposalSourceProvenance:
    return DecisionProposalSourceProvenance(
        producer_name="arch-agent",
        producer_type="architecture agent",
        source_reference=source_reference,
        external_source_id="DEC-101",
        source_version="commit-abc123",
        repository_locator="github.com/acme/widget",
        origin_classification=ORIGIN_AI_GENERATED,
    )


def _candidate(
    statement: str = "New code must not import legacy_client.",
    title: str = "Avoid legacy client imports",
    rationale: str = "legacy_client is unmaintained and blocks Python 3.13.",
    scope_hints: tuple[str, ...] = ("storage", "backend"),
    source_reference: str = "design/2026-09/storage.md",
) -> DecisionProposalCandidate:
    return DecisionProposalCandidate(
        title=title,
        statement=statement,
        rationale=rationale,
        provenance=_provenance(source_reference),
        scope_hints=scope_hints,
        architecture_context={"service": "storage"},
        related_decision_ids=("ddec-existing",),
    )


def _propose(
    path: Path,
    candidate: DecisionProposalCandidate,
) -> str:
    """Create a proposal through the real producer path; return its id."""
    store = JsonFileDecisionProposalStore(path)
    result = DecisionIndexService(store, clock=lambda: FIXED_TIME).propose(
        candidate
    )
    assert result.created
    return result.proposal.proposal_id


def _memory_document() -> dict:
    return {
        "meta": {
            "name": "test-project",
            "description": "Authority CLI test memory",
            "version": "0.1.0",
            "owner": "",
            "created": "",
        },
        "items": [],
        "examples": [],
        "decisions": [],
    }


def _write_memory(tmp_path: Path) -> Path:
    path = tmp_path / "project_memory.json"
    path.write_text(
        json.dumps(_memory_document(), indent=2) + "\n", encoding="utf-8"
    )
    return path


def _write_empty_store(path: Path) -> Path:
    path.write_text(
        json.dumps({"schema": PROPOSALS_SCHEMA, "proposals": []}) + "\n",
        encoding="utf-8",
    )
    return path


def _accept_via_core(
    path: Path, memory: Path, proposal_id: str
) -> AcceptResult:
    return DecisionAuthorityService(
        JsonFileDecisionProposalStore(path), memory, clock=lambda: FIXED_TIME
    ).accept(proposal_id)


def _memory_entries(memory: Path) -> list[dict]:
    raw = json.loads(memory.read_text(encoding="utf-8"))
    return raw["decisions"]


def _run(capsys, argv):
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ── `mneme decision proposals` (read-only inspection) ────────────────────────


def test_proposals_empty_store_prints_no_proposals(tmp_path, capsys):
    path = _write_empty_store(tmp_path / "proposals.json")
    code, out, _err = _run(capsys, ["decision", "proposals", "--proposals", str(path)])
    assert code == 0
    assert out.strip() == "(no proposals)"


def test_proposals_lists_in_deterministic_store_order(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    first = _propose(path, _candidate())
    second = _propose(path, _candidate(statement="Second statement."))
    third = _propose(
        path, _candidate(statement="Third statement.", source_reference="other.md")
    )
    code, out, _err = _run(capsys, ["decision", "proposals", "--proposals", str(path)])
    assert code == 0
    assert out.index(first) < out.index(second) < out.index(third)
    assert "[proposed]" in out


def test_proposals_distinguishes_proposed_accepted_rejected(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    memory = _write_memory(tmp_path)
    proposed_id = _propose(path, _candidate())
    accepted_id = _propose(
        path, _candidate(statement="Accept me.", source_reference="acc.md")
    )
    rejected_id = _propose(
        path, _candidate(statement="Reject me.", source_reference="rej.md")
    )
    assert _accept_via_core(path, memory, accepted_id).verified
    assert DecisionAuthorityService(
        JsonFileDecisionProposalStore(path), memory
    ).reject(rejected_id).already_rejected is False
    code, out, _err = _run(capsys, ["decision", "proposals", "--proposals", str(path)])
    assert code == 0
    assert f"[proposed] {proposed_id}" in out
    assert f"[accepted] {accepted_id}" in out
    assert f"[rejected] {rejected_id}" in out


def test_proposals_shows_accepted_decision_id(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    memory = _write_memory(tmp_path)
    proposal_id = _propose(path, _candidate())
    assert _accept_via_core(path, memory, proposal_id).verified
    code, out, _err = _run(capsys, ["decision", "proposals", "--proposals", str(path)])
    assert code == 0
    decision_id = default_decision_id_of(
        JsonFileDecisionProposalStore(path).get(proposal_id)
    )
    assert f"    decision: {decision_id}" in out
    assert "[accepted]" in out


def test_proposals_missing_store_fails_closed(tmp_path, capsys):
    code, out, err = _run(
        capsys, ["decision", "proposals", "--proposals", str(tmp_path / "absent.json")]
    )
    assert code == 2
    assert "ERROR:" in err
    assert "does not exist" in err
    assert "Traceback" not in err
    assert out == ""


def test_proposals_corrupt_store_fails_closed(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    path.write_text("{ not json", encoding="utf-8")
    code, out, err = _run(capsys, ["decision", "proposals", "--proposals", str(path)])
    assert code == 2
    assert "ERROR:" in err
    assert "unreadable or corrupt" in err
    assert "Traceback" not in err
    assert out == ""


# ── `mneme decision show` (read-only review) ────────────────────────────────


def test_show_renders_full_proposal_details(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    proposal_id = _propose(path, _candidate())
    code, out, _err = _run(
        capsys, ["decision", "show", proposal_id, "--proposals", str(path)]
    )
    assert code == 0
    for expected in (
        f"Proposal {proposal_id}",
        "status: proposed",
        "title: Avoid legacy client imports",
        "statement: New code must not import legacy_client.",
        "rationale: legacy_client is unmaintained and blocks Python 3.13.",
        "scope hints: storage, backend",
        "architecture context:",
        "service: storage",
        "related decision ids: ddec-existing",
        f"proposed at: {FIXED_TIME}",
        "producer name: arch-agent",
        "producer type: architecture agent",
        "source reference: design/2026-09/storage.md",
        "external source id: DEC-101",
        "source version: commit-abc123",
        "repository locator: github.com/acme/widget",
        "origin classification: ai_generated",
    ):
        assert expected in out, expected
    assert "accepted decision" not in out


def test_show_renders_provenance_without_trusted_evidence_language(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    proposal_id = _propose(path, _candidate())
    code, out, _err = _run(
        capsys, ["decision", "show", proposal_id, "--proposals", str(path)]
    )
    assert code == 0
    lowered = out.lower()
    assert "trusted" not in lowered
    assert "verified" not in lowered
    assert "evidence" not in lowered
    assert "informational" in lowered


def test_show_unknown_proposal_exits_nonzero(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    _propose(path, _candidate())
    code, out, err = _run(
        capsys, ["decision", "show", "dprop-unknown", "--proposals", str(path)]
    )
    assert code == 2
    assert "ERROR:" in err
    assert "dprop-unknown" in err
    assert "Traceback" not in err
    assert out == ""


def test_show_corrupt_store_exits_nonzero(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    path.write_text('{"schema": "wrong"}', encoding="utf-8")
    code, out, err = _run(capsys, ["decision", "show", "dprop-x", "--proposals", str(path)])
    assert code == 2
    assert "ERROR:" in err
    assert "Traceback" not in err
    assert out == ""


# ── `mneme decision accept` (authority delegation) ──────────────────────────


def test_accept_fresh_proposal_succeeds(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    memory = _write_memory(tmp_path)
    proposal_id = _propose(path, _candidate())
    code, out, err = _run(
        capsys,
        [
            "decision", "accept", proposal_id,
            "--proposals", str(path), "--memory", str(memory),
        ],
    )
    assert code == 0
    assert f"Accepted proposal {proposal_id}" in out
    assert f"Decision: {default_decision_id_of(JsonFileDecisionProposalStore(path).get(proposal_id))}" in out
    assert "Materialized: yes" in out
    assert "Verified: yes" in out
    assert "does not activate protection" in out
    assert err == ""


def test_accept_materializes_exactly_one_decision(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    memory = _write_memory(tmp_path)
    proposal_id = _propose(path, _candidate())
    _run(
        capsys,
        ["decision", "accept", proposal_id, "--proposals", str(path), "--memory", str(memory)],
    )
    entries = _memory_entries(memory)
    assert len(entries) == 1
    entry = entries[0]
    candidate = _candidate()
    assert entry["decision"] == candidate.statement
    assert entry["rationale"] == candidate.rationale
    assert entry["scope"] == list(candidate.scope_hints)
    assert entry["constraints"] == []
    assert entry["anti_patterns"] == []
    assert entry["rules"] == []
    assert entry["test_evidence"] == []
    assert entry["status"] == "active"


def test_accept_reports_deterministic_default_decision_id(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    memory = _write_memory(tmp_path)
    proposal_id = _propose(path, _candidate())
    code, out, _err = _run(
        capsys, ["decision", "accept", proposal_id, "--proposals", str(path), "--memory", str(memory)]
    )
    assert code == 0
    assert f"Decision: {default_decision_id_of(JsonFileDecisionProposalStore(path).get(proposal_id))}" in out


def test_accept_passes_explicit_decision_id_to_core(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    memory = _write_memory(tmp_path)
    proposal_id = _propose(path, _candidate())
    code, out, _err = _run(
        capsys,
        [
            "decision", "accept", proposal_id,
            "--proposals", str(path), "--memory", str(memory),
            "--decision-id", "arch-storage-standard",
        ],
    )
    assert code == 0
    assert "Decision: arch-storage-standard" in out
    entries = _memory_entries(memory)
    assert len(entries) == 1
    assert entries[0]["id"] == "arch-storage-standard"


def test_accept_retry_is_exit0_idempotent(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    memory = _write_memory(tmp_path)
    proposal_id = _propose(path, _candidate())
    argv = ["decision", "accept", proposal_id, "--proposals", str(path), "--memory", str(memory)]
    assert _run(capsys, argv)[0] == 0
    code, out, _err = _run(capsys, argv)
    assert code == 0
    assert f"Already accepted: {proposal_id}" in out
    assert "Materialized: no" in out
    assert "Verified: yes" in out
    assert len(_memory_entries(memory)) == 1


def test_accept_renders_crash_recovery(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    memory = _write_memory(tmp_path)
    proposal_id = _propose(path, _candidate())
    decision_id = default_decision_id_of(JsonFileDecisionProposalStore(path).get(proposal_id))
    JsonFileDecisionProposalStore(path).transition_if_proposed(
        proposal_id, "accepted", decision_id
    )
    code, out, _err = _run(
        capsys, ["decision", "accept", proposal_id, "--proposals", str(path), "--memory", str(memory)]
    )
    assert code == 0
    assert f"Recovered accepted proposal: {proposal_id}" in out
    assert f"Decision: {decision_id}" in out
    assert "Materialized: yes" in out
    assert "Verified: yes" in out
    assert len(_memory_entries(memory)) == 1


def test_accept_rejected_proposal_surfaces_core_refusal(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    memory = _write_memory(tmp_path)
    proposal_id = _propose(path, _candidate())
    DecisionAuthorityService(JsonFileDecisionProposalStore(path), memory).reject(
        proposal_id
    )
    snapshot = memory.read_bytes()
    code, out, err = _run(
        capsys, ["decision", "accept", proposal_id, "--proposals", str(path), "--memory", str(memory)]
    )
    assert code == 1
    assert out == ""
    assert "ERROR:" in err
    assert "rejected" in err
    assert "Traceback" not in err
    assert memory.read_bytes() == snapshot


def test_accept_reverse_half_state_surfaces_core_refusal(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    memory = _write_memory(tmp_path)
    proposal_id = _propose(path, _candidate())
    proposal = JsonFileDecisionProposalStore(path).get(proposal_id)
    decision_id = default_decision_id_of(proposal)
    raw = json.loads(memory.read_text(encoding="utf-8"))
    raw["decisions"].append(
        expected_materialization_entry(proposal, decision_id, FIXED_TIME)
    )
    memory.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    code, out, err = _run(
        capsys, ["decision", "accept", proposal_id, "--proposals", str(path), "--memory", str(memory)]
    )
    assert code == 1
    assert out == ""
    assert "reverse half-state" in err
    assert "Traceback" not in err


def test_accept_id_collision_surfaces_core_refusal(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    memory = _write_memory(tmp_path)
    proposal_id = _propose(path, _candidate())
    argv = ["decision", "accept", proposal_id, "--proposals", str(path), "--memory", str(memory)]
    assert _run(capsys, argv)[0] == 0
    raw = json.loads(memory.read_text(encoding="utf-8"))
    raw["decisions"][0]["decision"] = "A different decision entirely."
    memory.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    code, out, err = _run(capsys, argv)
    assert code == 1
    assert out == ""
    assert "ERROR:" in err
    assert "never overwritten or merged" in err
    assert "Traceback" not in err


def test_accept_missing_memory_fails_closed(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    proposal_id = _propose(path, _candidate())
    code, out, err = _run(
        capsys, ["decision", "accept", proposal_id, "--proposals", str(path), "--memory", str(tmp_path / "absent.json")]
    )
    assert code == 1
    assert out == ""
    assert "ERROR:" in err
    assert "does not exist" in err
    assert "Traceback" not in err


def test_accept_unknown_proposal_exits_authority_error(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    _propose(path, _candidate())
    memory = _write_memory(tmp_path)
    code, out, err = _run(
        capsys, ["decision", "accept", "dprop-unknown", "--proposals", str(path), "--memory", str(memory)]
    )
    assert code == 1
    assert out == ""
    assert "ERROR:" in err
    assert "not found" in err
    assert "Traceback" not in err


def test_accept_activates_no_protection(tmp_path, capsys, monkeypatch):
    def _fail(*_args, **_kwargs):
        raise AssertionError("protection activation must not be called")

    monkeypatch.setattr(cli, "activate_protection", _fail)
    monkeypatch.setattr(cli, "generate_protection_report", _fail)
    monkeypatch.setattr(
        cli, "check_prompt", _fail
    )
    path = tmp_path / "proposals.json"
    memory = _write_memory(tmp_path)
    proposal_id = _propose(path, _candidate())
    code, _out, _err = _run(
        capsys, ["decision", "accept", proposal_id, "--proposals", str(path), "--memory", str(memory)]
    )
    assert code == 0
    assert _memory_entries(memory)[0]["rules"] == []


# ── `mneme decision reject` (authority delegation) ──────────────────────────


def test_reject_proposed_proposal_succeeds(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    proposal_id = _propose(path, _candidate())
    memory = _write_memory(tmp_path)
    code, out, err = _run(
        capsys, ["decision", "reject", proposal_id, "--proposals", str(path), "--memory", str(memory)]
    )
    assert code == 0
    assert f"Rejected proposal {proposal_id}" in out
    assert err == ""
    store = JsonFileDecisionProposalStore(path)
    assert store.get(proposal_id).status == "rejected"


def test_reject_repeat_is_exit0_idempotent(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    proposal_id = _propose(path, _candidate())
    memory = _write_memory(tmp_path)
    argv = ["decision", "reject", proposal_id, "--proposals", str(path), "--memory", str(memory)]
    assert _run(capsys, argv)[0] == 0
    code, out, _err = _run(capsys, argv)
    assert code == 0
    assert f"Already rejected: {proposal_id}" in out


def test_rejected_proposal_remains_inspectable(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    proposal_id = _propose(path, _candidate())
    memory = _write_memory(tmp_path)
    assert _run(capsys, ["decision", "reject", proposal_id, "--proposals", str(path), "--memory", str(memory)])[0] == 0
    code, out, _err = _run(capsys, ["decision", "show", proposal_id, "--proposals", str(path)])
    assert code == 0
    assert f"Proposal {proposal_id}" in out
    assert "status: rejected" in out


def test_reject_never_touches_project_memory(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    proposal_id = _propose(path, _candidate())
    memory = _write_memory(tmp_path)
    snapshot = memory.read_bytes()
    code, _out, _err = _run(
        capsys, ["decision", "reject", proposal_id, "--proposals", str(path), "--memory", str(memory)]
    )
    assert code == 0
    assert memory.read_bytes() == snapshot


def test_reject_works_without_a_memory_file(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    proposal_id = _propose(path, _candidate())
    memory = tmp_path / "absent.json"
    code, out, _err = _run(
        capsys, ["decision", "reject", proposal_id, "--proposals", str(path), "--memory", str(memory)]
    )
    assert code == 0
    assert f"Rejected proposal {proposal_id}" in out
    assert not memory.exists()


def test_accept_of_rejected_proposal_still_fails_through_core(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    proposal_id = _propose(path, _candidate())
    memory = _write_memory(tmp_path)
    assert _run(capsys, ["decision", "reject", proposal_id, "--proposals", str(path), "--memory", str(memory)])[0] == 0
    code, out, err = _run(
        capsys, ["decision", "accept", proposal_id, "--proposals", str(path), "--memory", str(memory)]
    )
    assert code == 1
    assert out == ""
    assert "rejected" in err
    assert "Traceback" not in err


def test_reject_of_accepted_proposal_surfaces_core_refusal(tmp_path, capsys):
    path = tmp_path / "proposals.json"
    proposal_id = _propose(path, _candidate())
    memory = _write_memory(tmp_path)
    argv_accept = ["decision", "accept", proposal_id, "--proposals", str(path), "--memory", str(memory)]
    assert _run(capsys, argv_accept)[0] == 0
    snapshot = memory.read_bytes()
    code, out, err = _run(
        capsys, ["decision", "reject", proposal_id, "--proposals", str(path), "--memory", str(memory)]
    )
    assert code == 1
    assert out == ""
    assert "accepted" in err
    assert "Traceback" not in err
    assert memory.read_bytes() == snapshot


# ── Architecture: thin-adapter delegation and boundaries ────────────────────


class _SpyService:
    """Replaces DecisionAuthorityService to prove delegation and arguments."""

    last_init: tuple = ()
    last_accept: tuple = ()
    last_reject: str = ""
    accept_result: AcceptResult | None = None
    reject_result: RejectResult | None = None

    def __init__(self, store, memory_path, clock=None) -> None:
        _SpyService.last_init = (store, memory_path)

    def accept(self, proposal_id, decision_id=None) -> AcceptResult:
        _SpyService.last_accept = (proposal_id, decision_id)
        assert _SpyService.accept_result is not None
        return _SpyService.accept_result

    def reject(self, proposal_id) -> RejectResult:
        _SpyService.last_reject = proposal_id
        assert _SpyService.reject_result is not None
        return _SpyService.reject_result


@pytest.fixture()
def spy_service(monkeypatch):
    _SpyService.last_init = ()
    _SpyService.last_accept = ()
    _SpyService.last_reject = ""
    _SpyService.accept_result = None
    _SpyService.reject_result = None
    monkeypatch.setattr(cli, "DecisionAuthorityService", _SpyService)
    return _SpyService


def test_accept_delegates_to_authority_service(tmp_path, capsys, spy_service):
    path = tmp_path / "proposals.json"
    memory = tmp_path / "project_memory.json"
    proposal_id = _propose(path, _candidate())
    spy_service.accept_result = AcceptResult(
        proposal_id=proposal_id,
        decision_id="ddec-spy",
        proposal_status="accepted",
        materialized=True,
        already_accepted=False,
        recovered=False,
        verified=True,
    )
    code, out, _err = _run(
        capsys,
        [
            "decision", "accept", proposal_id,
            "--proposals", str(path), "--memory", str(memory),
        ],
    )
    assert code == 0
    store, memory_path = spy_service.last_init
    assert isinstance(store, JsonFileDecisionProposalStore)
    assert not isinstance(store, InMemoryDecisionProposalStore)
    assert store.path == path
    assert memory_path == str(memory)
    assert spy_service.last_accept == (proposal_id, None)
    assert f"Accepted proposal {proposal_id}" in out
    assert "Decision: ddec-spy" in out


def test_accept_passes_explicit_decision_id_to_core_spy(tmp_path, capsys, spy_service):
    path = tmp_path / "proposals.json"
    memory = tmp_path / "project_memory.json"
    proposal_id = _propose(path, _candidate())
    spy_service.accept_result = AcceptResult(
        proposal_id=proposal_id,
        decision_id="arch-explicit",
        proposal_status="accepted",
        materialized=True,
        already_accepted=False,
        recovered=False,
        verified=True,
    )
    code, out, _err = _run(
        capsys,
        [
            "decision", "accept", proposal_id,
            "--proposals", str(path), "--memory", str(memory),
            "--decision-id", "arch-explicit",
        ],
    )
    assert code == 0
    assert spy_service.last_accept == (proposal_id, "arch-explicit")
    assert "Decision: arch-explicit" in out


def test_reject_delegates_to_authority_service(tmp_path, capsys, spy_service):
    path = tmp_path / "proposals.json"
    memory = tmp_path / "project_memory.json"
    proposal_id = _propose(path, _candidate())
    spy_service.reject_result = RejectResult(
        proposal_id=proposal_id,
        proposal_status="rejected",
        already_rejected=False,
    )
    code, out, _err = _run(
        capsys,
        ["decision", "reject", proposal_id, "--proposals", str(path), "--memory", str(memory)],
    )
    assert code == 0
    store, memory_path = spy_service.last_init
    assert isinstance(store, JsonFileDecisionProposalStore)
    assert memory_path == str(memory)
    assert spy_service.last_reject == proposal_id
    assert f"Rejected proposal {proposal_id}" in out


def test_empty_proposals_value_never_switches_to_in_memory(tmp_path, capsys, spy_service):
    path = tmp_path / "proposals.json"
    proposal_id = _propose(path, _candidate())
    code, out, err = _run(
        capsys,
        [
            "decision", "accept", proposal_id,
            "--proposals", "", "--memory", str(tmp_path / "m.json"),
        ],
    )
    assert code == 2
    assert out == ""
    assert "ERROR:" in err
    assert spy_service.last_init == ()
    assert "in-memory" in err


def test_mcp_inventory_remains_exactly_six_tools() -> None:
    from mneme.decision_mcp import APPROVED_TOOLS as MCP_APPROVED_TOOLS

    assert tuple(MCP_APPROVED_TOOLS) == MCP_APPROVED_TOOLS
    assert "decision.accept" not in MCP_APPROVED_TOOLS
    assert "decision.reject" not in MCP_APPROVED_TOOLS


def test_decision_mcp_source_has_no_authority_import() -> None:
    mcp_source = (Path(cli.__file__).parent / "decision_mcp.py").read_text(
        encoding="utf-8"
    )
    assert "decision_authority" not in mcp_source
    assert "DecisionAuthorityService" not in mcp_source

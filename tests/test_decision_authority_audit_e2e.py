"""D2C3 cross-component E2E — human-accepted proposal → existing Audit.

Answers the single D2C3 architectural question (ADR-027 "Accepted-proposal
authority path" + ADR-026 tier semantics):

    Does a human-accepted proposal become an ordinary architecture
    Decision that the EXISTING Architecture Audit evaluates correctly,
    without any special proposal-aware Audit logic?

Flow under validation (production paths only; no MCP — D2D covers the
generic producer MCP workflow):

    DecisionIndexService.propose(...)           (protocol-independent Core)
        |
        | mneme decision accept <id> (CLI → DecisionAuthorityService)
        v
    project_memory.json decisions[]
        |
        | mneme audit --json ...  (CLI → MemoryStore → generate_protection_report)
        v
    mneme.audit/v1 report with ADR-026 tier semantics

Proves ACCEPTED != PROTECTED: acceptance makes a decision authoritative
and Audit-visible; it installs no rule, no evidence, and assigns no tier.
Audit classifies the materialized decision exactly as it would any other
equivalent Decision. Also proves the Audit is read-only (proposal store and
project memory byte-identical across Audit), producer provenance stays in
the proposal store and is never promoted to Audit evidence, the MCP
six-tool inventory is unchanged, and the authority CLI surface is unchanged.

Statements are byte-identical to the fixtures already pinned by
tests/test_audit_tier_semantics.py — no tier semantics are invented here.
"""
from __future__ import annotations

import contextlib
import io
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from mneme.cli import main
from mneme.decision_index_service import DecisionIndexService
from mneme.decision_mcp import APPROVED_TOOLS
from mneme.decision_proposal import (
    ORIGIN_AI_GENERATED,
    DecisionProposalCandidate,
    DecisionProposalSourceProvenance,
)
from mneme.decision_proposal_store import JsonFileDecisionProposalStore

PROPOSALS_SCHEMA = "mneme.decision-proposals/v1"
FIXED_TIME = "2026-09-15T12:00:00Z"
AUDIT_SCHEMA = "mneme.audit/v1"

MCP_SIX_TOOLS = frozenset({
    "decision.propose",
    "decision.propose_batch",
    "decision.get",
    "decision.search",
    "decision.applicable_to",
    "decision.trace",
})

# Frozen ADR-026 fixtures (tests/test_audit_tier_semantics.py), verbatim.
MNEME_READY_STATEMENT = (
    "Generated recommendations must not use the term `seamless`."
)
REQUIRES_MODELLING_STATEMENT = (
    "Generated output must contain all required architecture sections; "
    "otherwise fail closed."
)
GUIDANCE_STATEMENT = "Prefer simple architectures where practical."
REJECTED_STATEMENT = "New code must not import legacy_client."


@dataclass(frozen=True)
class Flow:
    proposals_path: Path
    memory_path: Path
    audit_report: Path
    audit_report_rerun: Path
    accepted: dict[str, str]      # proposal_id -> accepted_decision_id
    rejected_proposal_id: str
    pre_audit_proposals: bytes
    pre_audit_memory: bytes

    @property
    def decision_id_by_statement(self) -> dict[str, str]:
        """statement -> accepted decision id (proposal-id-free view)."""
        store = JsonFileDecisionProposalStore(self.proposals_path)
        proposal_id_by_statement = {
            p.candidate.statement: p.proposal_id for p in store.list_proposals()
        }
        return {
            statement: self.accepted[proposal_id_by_statement[statement]]
            for statement in (
                MNEME_READY_STATEMENT,
                REQUIRES_MODELLING_STATEMENT,
                GUIDANCE_STATEMENT,
            )
        }


def _provenance(
    source_reference: str, external_id: str
) -> DecisionProposalSourceProvenance:
    return DecisionProposalSourceProvenance(
        producer_name="arch-agent",
        producer_type="architecture agent",
        source_reference=source_reference,
        external_source_id=external_id,
        source_version="commit-abc123",
        repository_locator="github.com/acme/widget",
        origin_classification=ORIGIN_AI_GENERATED,
    )


def _candidate(
    statement: str, source_reference: str, external_id: str
) -> DecisionProposalCandidate:
    return DecisionProposalCandidate(
        title="Candidate architecture decision",
        statement=statement,
        rationale="Extracted from the generated architecture output.",
        provenance=_provenance(source_reference, external_id),
        scope_hints=("generation",),
        architecture_context={"pipeline": "architecture-generation"},
        related_decision_ids=(),
    )


def _write_memory(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "meta": {
                    "name": "d2c3-e2e",
                    "description": "D2C3 authority to Audit E2E fixture",
                },
                "items": [],
                "examples": [],
                "decisions": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _propose(store_path: Path, candidate: DecisionProposalCandidate) -> str:
    """Create one proposal through the real producer path (no MCP)."""
    service = DecisionIndexService(
        JsonFileDecisionProposalStore(store_path), clock=lambda: FIXED_TIME
    )
    result = service.propose(candidate)
    assert result.created
    return result.proposal.proposal_id


def _run(argv: list[str]) -> tuple[int, str, str]:
    """Run the production CLI entry point, capturing its output."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def _run_e2e_flow(tmp_path: Path) -> Flow:
    """The full D2C3 production-path flow over an isolated fixture.

    propose (Core) -> accept x3 / reject x1 (CLI) -> audit (CLI, twice).
    Byte snapshots are taken around the Audit runs only; acceptance-time
    snapshots belong to the D2C1 suite.
    """
    proposals_path = tmp_path / "decision_proposals.json"
    memory_path = _write_memory(tmp_path / ".mneme" / "project_memory.json")

    specs = (
        (MNEME_READY_STATEMENT, "design/2026-09/banned-terms.md", "DEC-101"),
        (
            REQUIRES_MODELLING_STATEMENT,
            "design/2026-09/output-contract.md",
            "DEC-102",
        ),
        (GUIDANCE_STATEMENT, "design/2026-09/style.md", "DEC-103"),
        (REJECTED_STATEMENT, "design/2026-09/legacy.md", "DEC-104"),
    )
    proposal_ids = tuple(
        _propose(proposals_path, _candidate(*spec)) for spec in specs
    )
    ready_id, modelling_id, guidance_id, rejected_id = proposal_ids

    accepted: dict[str, str] = {}
    for proposal_id in (ready_id, modelling_id, guidance_id):
        code, out, err = _run(
            [
                "decision", "accept", proposal_id,
                "--proposals", str(proposals_path),
                "--memory", str(memory_path),
            ]
        )
        assert code == 0, out + err
        assert f"Accepted proposal {proposal_id}" in out
        assert "does not activate protection" in out
        accepted[proposal_id] = _decision_id_from_output(out)

    # The accepted proposal remains inspectable through the existing
    # review CLI (a small assertion only; D2C2 owns CLI presentation).
    code, out, err = _run(
        ["decision", "show", ready_id, "--proposals", str(proposals_path)]
    )
    assert code == 0 and err == ""
    assert "status: accepted" in out
    assert f"accepted decision: {accepted[ready_id]}" in out

    code, out, err = _run(
        [
            "decision", "reject", rejected_id,
            "--proposals", str(proposals_path),
            "--memory", str(memory_path),
        ]
    )
    assert code == 0, out + err
    assert f"Rejected proposal {rejected_id}" in out

    audit_report = tmp_path / "audit_report.json"
    pre_proposals_bytes = proposals_path.read_bytes()
    pre_memory_bytes = memory_path.read_bytes()
    code, _out, err = _run(
        ["audit", "--memory", str(memory_path), "--json", str(audit_report)]
    )
    assert code == 0, err
    assert audit_report.exists()

    audit_report_rerun = tmp_path / "audit_report_rerun.json"
    code, _out, err = _run(
        [
            "audit", "--memory", str(memory_path),
            "--json", str(audit_report_rerun),
        ]
    )
    assert code == 0, err
    assert audit_report_rerun.exists()

    return Flow(
        proposals_path=proposals_path,
        memory_path=memory_path,
        audit_report=audit_report,
        audit_report_rerun=audit_report_rerun,
        accepted=accepted,
        rejected_proposal_id=rejected_id,
        pre_audit_proposals=pre_proposals_bytes,
        pre_audit_memory=pre_memory_bytes,
    )


def _decision_id_from_output(out: str) -> str:
    line = next(l for l in out.splitlines() if l.startswith("Decision: "))
    return line.removeprefix("Decision: ").strip()


def _load_report(flow: Flow) -> dict:
    return json.loads(flow.audit_report.read_text(encoding="utf-8"))


def _memory_entries(flow: Flow) -> list[dict]:
    return json.loads(flow.memory_path.read_text(encoding="utf-8"))["decisions"]


# ── The main cross-component E2E ─────────────────────────────────────────────


def test_accepted_proposals_reach_the_existing_audit(tmp_path):
    """The complete D2C3 invariant chain over production paths only."""
    flow = _run_e2e_flow(tmp_path)
    store = JsonFileDecisionProposalStore(flow.proposals_path)

    # 1–2. All three accepted proposals carry their accepted_decision_id.
    by_id = {p.proposal_id: p for p in store.list_proposals()}
    accepted_ids = set(flow.accepted)
    assert set(by_id) == accepted_ids | {flow.rejected_proposal_id}
    for proposal_id, decision_id in flow.accepted.items():
        assert by_id[proposal_id].status == "accepted"
        assert by_id[proposal_id].accepted_decision_id == decision_id

    # 3–5. Exactly three materialized decisions, ids linked, all active.
    entries = _memory_entries(flow)
    assert len(entries) == 3
    assert {e["id"] for e in entries} == set(flow.accepted.values())
    assert all(e["status"] == "active" for e in entries)

    # 6–8. Acceptance installed no rule, no evidence, no structure, and
    # activated no protection: the exact ADR-027 materialization shape.
    for entry in entries:
        assert entry["decision"] in (
            MNEME_READY_STATEMENT,
            REQUIRES_MODELLING_STATEMENT,
            GUIDANCE_STATEMENT,
        )
        assert entry["constraints"] == []
        assert entry["anti_patterns"] == []
        assert entry["rules"] == []
        assert entry["test_evidence"] == []

    # 9–12. Rejected negative control: never materialized, never audited.
    rejected = by_id[flow.rejected_proposal_id]
    assert rejected.status == "rejected"
    assert rejected.accepted_decision_id is None
    assert flow.rejected_proposal_id not in flow.accepted.values()
    assert flow.rejected_proposal_id not in {e["id"] for e in entries}

    # Audit report: schema + aggregates.
    report = _load_report(flow)
    assert report["schema"] == AUDIT_SCHEMA
    summary = report["summary"]
    assert summary["total_decisions"] == 3
    assert summary["protected"] == 0
    assert summary["mneme_ready"] == 1
    assert summary["requires_modelling"] == 1
    assert summary["guidance"] == 1
    assert summary["protection_relevant"] == 2
    assert summary["current_protection_pct"] == 0.0
    assert summary["protection_gap_pct"] == 100.0
    assert summary["identified_mneme_potential_pct"] == 100.0

    # Per-decision tiers, mapped by the accepted decision id.
    by_decision_id = {d["id"]: d for d in report["decisions"]}
    assert set(by_decision_id) == set(flow.accepted.values())
    assert flow.rejected_proposal_id not in by_decision_id

    ready = by_decision_id[
        flow.decision_id_by_statement[MNEME_READY_STATEMENT]
    ]
    assert ready["status"] == "active"
    assert ready["intent"] == "deterministic"
    assert ready["protection_tier"] == "mneme_ready"
    assert ready["mneme_guardrail"] == "FORBID_LITERAL: seamless"
    assert ready["evidence_confidence"] == "none"
    assert ready["evidence_sources"] == []

    modelling = by_decision_id[
        flow.decision_id_by_statement[REQUIRES_MODELLING_STATEMENT]
    ]
    assert modelling["status"] == "active"
    assert modelling["intent"] == "deterministic"
    assert modelling["protection_tier"] == "requires_modelling"
    assert modelling["mneme_guardrail"] is None
    assert modelling["evidence_confidence"] == "none"

    guidance = by_decision_id[
        flow.decision_id_by_statement[GUIDANCE_STATEMENT]
    ]
    assert guidance["status"] == "active"
    assert guidance["intent"] == "guidance"
    assert guidance["protection_tier"] == "guidance"
    assert guidance["mneme_guardrail"] is None
    assert guidance["evidence_confidence"] == "none"

    # Identity linkage: proposal.accepted_decision_id == runtime Decision.id
    # == Audit report decision.id, for every accepted proposal.
    for proposal_id, decision_id in flow.accepted.items():
        assert by_id[proposal_id].accepted_decision_id == decision_id
        entry = next(e for e in entries if e["id"] == decision_id)
        assert entry["id"] == decision_id
        assert by_decision_id[decision_id]["id"] == decision_id

    # Producer provenance: retained in the proposal store, never promoted.
    for proposal_id in accepted_ids:
        provenance = by_id[proposal_id].candidate.provenance
        assert provenance is not None
        assert provenance.producer_name == "arch-agent"
        assert provenance.external_source_id
        assert provenance.source_version == "commit-abc123"
    assert all(
        d["evidence_sources"] == [] and d["evidence_confidence"] == "none"
        for d in report["decisions"]
    )

    # Audit read-only: proposal store and project memory byte-identical;
    # only the requested JSON report file was written.
    assert flow.proposals_path.read_bytes() == flow.pre_audit_proposals
    assert flow.memory_path.read_bytes() == flow.pre_audit_memory

    # Determinism: an identical second Audit run is byte-identical.
    assert flow.audit_report_rerun.read_bytes() == flow.audit_report.read_bytes()


# ── Focused D2C3 invariants (shared flow, targeted assertions) ───────────────


def test_acceptance_does_not_install_the_suggested_rule(tmp_path):
    """Mneme-ready derivation is text-derived Audit semantics, not state.

    The accepted decision carries no FORBID_LITERAL rule; acceptance did
    not create the rule the Audit says COULD be created; nothing was
    activated (ACCEPTED != PROTECTED)."""
    flow = _run_e2e_flow(tmp_path)
    entry = next(
        e for e in _memory_entries(flow)
        if e["decision"] == MNEME_READY_STATEMENT
    )
    assert entry["rules"] == []
    assert entry["anti_patterns"] == []
    assert entry["constraints"] == []

    ready = next(
        d for d in _load_report(flow)["decisions"] if d["id"] == entry["id"]
    )
    # Audit derives the guardrail from the decision text only...
    assert ready["protection_tier"] == "mneme_ready"
    assert ready["mneme_guardrail"] == "FORBID_LITERAL: seamless"
    # ...but the decision is NOT protected: no rule was installed and no
    # verified evidence exists merely because a human accepted it.
    assert ready["protection_tier"] != "protected"
    assert ready["evidence_confidence"] == "none"
    assert not any(rule for entry in _memory_entries(flow) for rule in entry["rules"])


def test_accepted_deterministic_decision_is_requires_modelling(tmp_path):
    """Accepted deterministic non-literal decision classifies exactly as an
    equivalent hand-written decision would (Requires modelling)."""
    flow = _run_e2e_flow(tmp_path)
    entry = next(
        e for e in _memory_entries(flow)
        if e["decision"] == REQUIRES_MODELLING_STATEMENT
    )
    decision = next(
        d for d in _load_report(flow)["decisions"] if d["id"] == entry["id"]
    )
    assert decision["intent"] == "deterministic"
    assert decision["protection_tier"] == "requires_modelling"
    assert decision["mneme_guardrail"] is None
    assert decision["evidence_confidence"] == "none"


def test_accepted_advisory_decision_is_guidance(tmp_path):
    """Accepted advisory decision classifies as Guidance and stays outside
    the protection-relevant denominator."""
    flow = _run_e2e_flow(tmp_path)
    entry = next(
        e for e in _memory_entries(flow)
        if e["decision"] == GUIDANCE_STATEMENT
    )
    decision = next(
        d for d in _load_report(flow)["decisions"] if d["id"] == entry["id"]
    )
    assert decision["intent"] == "guidance"
    assert decision["protection_tier"] == "guidance"
    assert decision["mneme_guardrail"] is None
    assert decision["evidence_confidence"] == "none"


def test_rejected_proposal_is_a_negative_control(tmp_path):
    """A rejected proposal never materializes and never appears in Audit."""
    flow = _run_e2e_flow(tmp_path)
    store = JsonFileDecisionProposalStore(flow.proposals_path)
    rejected = store.get(flow.rejected_proposal_id)
    assert rejected.status == "rejected"
    assert rejected.accepted_decision_id is None

    memory = _memory_entries(flow)
    assert rejected.candidate.statement not in {
        e["decision"] for e in memory
    }
    assert len(memory) == 3

    report = _load_report(flow)
    assert rejected.candidate.statement not in {
        d["decision"] for d in report["decisions"]
    }
    assert flow.rejected_proposal_id not in {
        d["id"] for d in report["decisions"]
    }


def test_aggregate_metrics_for_the_isolated_fixture(tmp_path):
    """1 Mneme-ready + 1 Requires modelling + 1 Guidance + 0 Protected
    yields the frozen aggregate semantics: 0/1/1/1, PR=2, 0% protected,
    100% gap, 100% compatibility potential."""
    flow = _run_e2e_flow(tmp_path)
    summary = _load_report(flow)["summary"]
    assert summary["total_decisions"] == 3
    assert summary["protected"] == 0
    assert summary["mneme_ready"] == 1
    assert summary["requires_modelling"] == 1
    assert summary["guidance"] == 1
    assert summary["protection_relevant"] == 2
    assert summary["current_protection_pct"] == 0.0
    assert summary["protection_gap_pct"] == 100.0
    assert summary["identified_mneme_potential_pct"] == 100.0


def test_audit_leaves_proposal_store_and_memory_byte_identical(tmp_path):
    """Audit is read-only: only the requested JSON report file is written;
    proposals are not transitioned and memory is not enriched."""
    flow = _run_e2e_flow(tmp_path)
    assert flow.proposals_path.read_bytes() == flow.pre_audit_proposals
    assert flow.memory_path.read_bytes() == flow.pre_audit_memory

    # Statuses were not touched by Audit; provenance was not reinterpreted.
    store = JsonFileDecisionProposalStore(flow.proposals_path)
    statuses = {p.proposal_id: p.status for p in store.list_proposals()}
    assert set(statuses.values()) == {"accepted", "rejected"}
    for proposal in store.list_proposals():
        if proposal.status == "accepted":
            assert proposal.candidate.provenance is not None


def test_second_identical_audit_run_is_deterministic(tmp_path):
    flow = _run_e2e_flow(tmp_path)
    assert flow.audit_report_rerun.read_bytes() == flow.audit_report.read_bytes()


def test_mcp_six_tool_inventory_unchanged():
    """The MCP transport keeps exactly the six D2B tools; acceptance stays
    a human authority action and never becomes a producer capability."""
    assert set(APPROVED_TOOLS) == MCP_SIX_TOOLS
    assert len(APPROVED_TOOLS) == 6
    assert "decision.accept" not in APPROVED_TOOLS
    assert "decision.reject" not in APPROVED_TOOLS


def test_authority_cli_keeps_the_four_command_surface(tmp_path, capsys):
    """`mneme decision` remains proposals | show | accept | reject."""
    store_path = tmp_path / "decision_proposals.json"
    store_path.write_text(
        json.dumps({"schema": PROPOSALS_SCHEMA, "proposals": []}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as excinfo:
        main(["decision", "--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "{proposals,show,accept,reject}" in out

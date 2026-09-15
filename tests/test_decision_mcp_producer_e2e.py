"""D2D generic MCP producer E2E (ADR-027, ADR-023, issues #362/#365).

The final D2 validation milestone. Answers one architectural question:

    Can a completely generic architecture-producing system submit candidate
    decisions through Mneme's existing MCP contract, without understanding
    Mneme's enforcement schema, after which a human can review/accept them
    through Mneme authority and the ordinary Architecture Audit evaluates
    the resulting decisions?

Flow under validation (production paths only; proposal ingestion goes
through the MCP transport, unlike D2C3 which used the Core path):

    generic producer (source-backed fixture, pinned commit)
        |
        | MCP SDK Client -> build_server_from_parts -> decision.propose_batch
        v
    proposed proposals only (JsonFileDecisionProposalStore)
        |
        | human review CLI: mneme decision proposals / show
        | human authority CLI: mneme decision accept / reject
        v
    project_memory.json decisions[]
        |
        | mneme audit --memory ... --json ...
        v
    existing Architecture Audit (mneme.audit/v1, ADR-026 tier semantics)
        |
        v
    existing protection tiers

The reference producer material is a small source-backed fixture
(``tests/fixtures/d2d_generic_producer/producer_fixture.json``) pinned to
one exact public commit. No Sagarika-specific runtime code exists: the
producer-specific content lives only in this test module and the fixture,
and a dedicated test proves no runtime module gained producer-specific
logic.
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from mcp import Client

from mneme.cli import main
from mneme.decision_authority import default_decision_id_of
from mneme.decision_mcp import (
    APPROVED_TOOLS,
    TOOL_APPLICABLE_TO,
    TOOL_GET,
    TOOL_PROPOSE,
    TOOL_PROPOSE_BATCH,
    TOOL_SEARCH,
    TOOL_TRACE,
    build_server_from_parts,
)
from mneme.decision_proposal import ORIGIN_AI_GENERATED
from mneme.decision_proposal_store import JsonFileDecisionProposalStore

FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "d2d_generic_producer"
    / "producer_fixture.json"
)
RUNTIME_DIR = Path(__file__).resolve().parent.parent / "mneme"
FIXED_TIME = "2026-09-15T12:00:00Z"
AUDIT_SCHEMA = "mneme.audit/v1"
PROPOSALS_SCHEMA = "mneme.decision-proposals/v1"

MCP_SIX_TOOLS = frozenset({
    "decision.propose",
    "decision.propose_batch",
    "decision.get",
    "decision.search",
    "decision.applicable_to",
    "decision.trace",
})

# Runtime-module tokens that would indicate producer-specific logic. The
# first three exist ONLY in one pre-existing ADR-026 provenance comment
# (mneme/enforcer.py, part of the validated pre-D2D baseline); everything
# else must not appear anywhere in runtime code.
PREEXISTING_PROVENANCE_TOKENS = (
    "sagarika",
    "ai-system-architect",
)
FORBIDDEN_RUNTIME_TOKENS = (
    "architecture-boundaries-base",
    "customer_support_chatbot",
    "d2d_generic_producer",
    "producer_fixture.json",
    "Fail closed on a broken architecture output contract",
    "Keep sensitive data within the session window",
)


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _batch_payload() -> dict:
    """The exact MCP batch payload the generic producer would submit.

    Producer-controlled candidate fields only (title, statement, rationale,
    provenance, scope_hints, architecture_context, related_decision_ids) plus
    batch-level shared provenance. No authority field is present anywhere.
    """
    fixture = _fixture()
    candidates: list[dict] = []
    for candidate in fixture["candidates"]:
        entry: dict = {
            "title": candidate["title"],
            "statement": candidate["statement"],
            "rationale": candidate["rationale"],
            "scope_hints": list(candidate["scope_hints"]),
            "architecture_context": dict(candidate["architecture_context"]),
            "related_decision_ids": list(candidate["related_decision_ids"]),
        }
        if "provenance" in candidate:
            # A separate-source candidate carries its own full provenance;
            # the documented service merge makes the candidate's provenance
            # win over the batch shared provenance.
            entry["provenance"] = dict(candidate["provenance"])
        candidates.append(entry)
    return {
        "candidates": candidates,
        "shared_provenance": {
            "producer_name": fixture["shared_provenance"]["producer_name"],
            "producer_type": fixture["shared_provenance"]["producer_type"],
            "source_reference": fixture["shared_provenance"]["source_reference"],
            "source_version": fixture["shared_provenance"]["source_version"],
            "repository_locator": fixture["shared_provenance"]["repository_locator"],
            "origin_classification": ORIGIN_AI_GENERATED,
        },
    }


def _mcp_server(store_path: Path):
    """Compose the real MCP server over the durable proposal store.

    Exactly the composition ``mneme decision-mcp`` uses by default
    (``open_proposal_store(path)`` + no canonical ADR directory). The
    injected clock keeps ``proposed_at`` deterministic; proposal identity
    never depends on it.
    """
    return build_server_from_parts(
        JsonFileDecisionProposalStore(store_path),
        canonical_index=None,
        clock=lambda: FIXED_TIME,
    )


def _call(server: object, name: str, arguments: dict | None = None):
    """In-memory MCP SDK client call through the real protocol layer."""
    async def _run() -> object:
        async with Client(server) as client:  # type: ignore[arg-type]
            return await client.call_tool(name, arguments or {})
    return asyncio.run(_run())


def _list_tool_names(server: object) -> list[str]:
    async def _run() -> list[str]:
        async with Client(server) as client:  # type: ignore[arg-type]
            result = await client.list_tools()
            return [tool.name for tool in result.tools]
    return asyncio.run(_run())


def _run(argv: list[str]) -> tuple[int, str, str]:
    """Run the production CLI entry point, capturing its output."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def _decision_id_from_output(out: str) -> str:
    line = next(l for l in out.splitlines() if l.startswith("Decision: "))
    return line.removeprefix("Decision: ").strip()


def _write_memory(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "meta": {
                    "name": "d2d-producer-e2e",
                    "description": "D2D generic MCP producer E2E fixture",
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


def _memory_entries(memory_path: Path) -> list[dict]:
    return json.loads(memory_path.read_text(encoding="utf-8"))["decisions"]


def _store(proposals_path: Path) -> JsonFileDecisionProposalStore:
    return JsonFileDecisionProposalStore(proposals_path)


@dataclass(frozen=True)
class ProducerFlow:
    proposals_path: Path
    memory_path: Path
    server_before_authority: object
    batch_payload: dict
    proposal_id_by_key: dict[str, str]
    decision_id_by_key: dict[str, str]
    rejected_key: str
    post_authority_proposals: bytes
    post_authority_memory: bytes
    audit_report: Path
    audit_report_rerun: Path

    @property
    def fixture(self) -> dict:
        return _fixture()

    @property
    def accepted_keys(self) -> list[str]:
        return [
            c["key"] for c in self.fixture["candidates"]
            if c["authority_intent"] == "accept"
        ]


def _run_producer_flow(tmp_path: Path) -> ProducerFlow:
    """The full D2D production-path flow over an isolated fixture.

    MCP batch ingestion (SDK client -> real server) -> idempotent resends
    -> MCP reads -> human review CLI -> human accept x3 / reject x1 ->
    isolated-memory Audit (twice).
    """
    proposals_path = tmp_path / "decision_proposals.json"
    memory_path = _write_memory(tmp_path / ".mneme" / "project_memory.json")

    payload = _batch_payload()
    fixture = _fixture()
    keys = [c["key"] for c in fixture["candidates"]]
    rejected_key = next(
        c["key"] for c in fixture["candidates"] if c["authority_intent"] == "reject"
    )
    accept_keys = [
        c["key"] for c in fixture["candidates"] if c["authority_intent"] == "accept"
    ]

    # The long-running server instance is built BEFORE any authority action;
    # the freshness test uses it to observe post-authority staleness.
    server_before_authority = _mcp_server(proposals_path)

    first = _call(server_before_authority, TOOL_PROPOSE_BATCH, payload)
    assert first.is_error is False
    results = first.structured_content["results"]
    proposal_id_by_key = {
        key: result["proposal"]["proposal_id"]
        for key, result in zip(keys, results)
    }

    post_ingestion_proposals = proposals_path.read_bytes()
    post_ingestion_memory = memory_path.read_bytes()

    decision_id_by_key: dict[str, str] = {}
    for key in accept_keys:
        code, out, err = _run(
            [
                "decision", "accept", proposal_id_by_key[key],
                "--proposals", str(proposals_path),
                "--memory", str(memory_path),
            ]
        )
        assert code == 0, out + err
        decision_id_by_key[key] = _decision_id_from_output(out)

    code, out, err = _run(
        [
            "decision", "reject", proposal_id_by_key[rejected_key],
            "--proposals", str(proposals_path),
            "--memory", str(memory_path),
        ]
    )
    assert code == 0, out + err

    # Byte snapshots for the Audit read-only proof: taken after all
    # authority actions, before the Audit runs.
    post_authority_proposals = proposals_path.read_bytes()
    post_authority_memory = memory_path.read_bytes()

    audit_report = tmp_path / "audit_report.json"
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

    return ProducerFlow(
        proposals_path=proposals_path,
        memory_path=memory_path,
        server_before_authority=server_before_authority,
        batch_payload=payload,
        proposal_id_by_key=proposal_id_by_key,
        decision_id_by_key=decision_id_by_key,
        rejected_key=rejected_key,
        post_authority_proposals=post_authority_proposals,
        post_authority_memory=post_authority_memory,
        audit_report=audit_report,
        audit_report_rerun=audit_report_rerun,
    )


def _expected_provenance(fixture: dict, candidate: dict) -> dict:
    shared = fixture["shared_provenance"]
    provenance = {
        "producer_name": shared["producer_name"],
        "producer_type": shared["producer_type"],
        "source_reference": shared["source_reference"],
        "external_source_id": "",
        "source_version": shared["source_version"],
        "repository_locator": shared["repository_locator"],
        "origin_classification": ORIGIN_AI_GENERATED,
    }
    if "provenance" in candidate:
        provenance.update(candidate["provenance"])
    return provenance


# ── Producer reference pinning + source traceability ────────────────────────


def test_reference_producer_is_pinned_to_an_exact_commit():
    """The compatibility fixture is pinned to the exact public source
    commit; it never floats against future producer changes."""
    fixture = _fixture()
    reference = fixture["reference"]
    assert reference["repository"] == "sagarika29/ai-system-architect"
    assert reference["commit_sha"] == "0797e2736a1b288ae136b8f093644e3cc2406f6f"
    assert len(reference["commit_sha"]) == 40
    assert all(len(c) == 40 for c in (s["blob_sha"] for s in reference["sources"]))
    # The shared provenance pins the same commit as the source version.
    assert (
        fixture["shared_provenance"]["source_version"]
        == reference["commit_sha"]
    )
    assert fixture["shared_provenance"]["repository_locator"] == reference["repository"]


def test_every_candidate_is_anchored_to_exact_source_text():
    """Every fixture candidate is traceable to exact recorded source
    passages at the pinned commit; no invented architectural decision."""
    fixture = _fixture()
    paths = {s["path"] for s in fixture["reference"]["sources"]}
    assert len(fixture["candidates"]) == 4
    for candidate in fixture["candidates"]:
        assert candidate["title"] and candidate["statement"]
        assert candidate["source"], candidate["key"]
        for source in candidate["source"]:
            assert source["path"] in paths, candidate["key"]
            assert source["excerpt"], candidate["key"]
        haystack = " ".join(
            s["excerpt"].lower() for s in candidate["source"]
        )
        for term in candidate["anchored_terms"]:
            assert term.lower() in haystack, (candidate["key"], term)
        # The rationale is producer-authored supporting text (never empty).
        assert isinstance(candidate["rationale"], str) and candidate["rationale"]
    # The batch payload submits exactly these candidates, producer fields only.
    payload = _batch_payload()
    assert len(payload["candidates"]) == len(fixture["candidates"])
    allowed_candidate_fields = {
        "title", "statement", "rationale", "provenance", "scope_hints",
        "architecture_context", "related_decision_ids",
    }
    for candidate in payload["candidates"]:
        assert set(candidate) <= allowed_candidate_fields


# ── MCP transport ingestion (the D2D point: through the real boundary) ──────


def test_generic_producer_submits_batch_through_real_mcp_transport(tmp_path):
    """First decision.propose_batch through the MCP SDK client against the
    real registered server: proposals only, nothing else created."""
    proposals_path = tmp_path / "decision_proposals.json"
    memory_path = _write_memory(tmp_path / ".mneme" / "project_memory.json")
    memory_before = memory_path.read_bytes()

    server = _mcp_server(proposals_path)

    # The tool inventory is the frozen six-tool contract, listed through a
    # real MCP SDK client against the registered server.
    assert sorted(_list_tool_names(server)) == sorted(APPROVED_TOOLS)
    assert sorted(_list_tool_names(server)) == sorted(MCP_SIX_TOOLS)

    result = _call(server, TOOL_PROPOSE_BATCH, _batch_payload())
    assert result.is_error is False
    payload = result.structured_content
    fixture = _fixture()
    keys = [c["key"] for c in fixture["candidates"]]
    results = payload["results"]

    # One proposal result per candidate, in order.
    assert len(results) == len(keys)
    assert [r["created"] for r in results] == [True] * len(keys)
    assert [r["reused"] for r in results] == [False] * len(keys)

    proposal_ids = []
    for key, item, candidate in zip(keys, results, fixture["candidates"]):
        proposal = item["proposal"]
        # Every proposal status is proposed; a stable proposal id exists.
        assert proposal["proposal_status"] == "proposed"
        assert proposal["proposal_id"].startswith("dprop-")
        proposal_ids.append(proposal["proposal_id"])
        # No proposal has accepted_decision_id; no canonical state exists.
        assert proposal["accepted_decision_id"] is None
        assert "lifecycle_status" not in proposal
        assert "status" not in proposal
        # Provenance round-trips losslessly (documented merge semantics:
        # the candidate's own provenance wins where supplied).
        assert proposal["provenance"] == _expected_provenance(fixture, candidate)
        assert proposal["producer_key"]
        assert proposal["content_fingerprint"]
        assert proposal["proposed_at"] == FIXED_TIME
        # Producer content round-trips losslessly.
        assert proposal["title"] == candidate["title"]
        assert proposal["statement"] == candidate["statement"]
        assert proposal["rationale"] == candidate["rationale"]
        assert proposal["scope_hints"] == list(candidate["scope_hints"])
        assert proposal["architecture_context"] == dict(
            candidate["architecture_context"]
        )
    assert len(set(proposal_ids)) == len(proposal_ids)

    # Deterministic store persistence: a reconstructed store reproduces the
    # same records, ids, and order.
    persisted = json.loads(proposals_path.read_text(encoding="utf-8"))
    assert persisted["schema"] == PROPOSALS_SCHEMA
    assert [p["proposal_id"] for p in persisted["proposals"]] == proposal_ids

    # No canonical decision is created; project memory is unchanged; no
    # rule/evidence/protection state exists anywhere.
    assert memory_path.read_bytes() == memory_before
    assert _memory_entries(memory_path) == []
    fresh = _mcp_server(proposals_path)
    read = _call(fresh, TOOL_SEARCH, {"canonical_lifecycle_status": "active"})
    assert read.structured_content["canonical_decisions"] == []
    flat = json.dumps(payload)
    for forbidden in (
        "FORBID_LITERAL", "rule_payload", "include_paths", "exclude_paths",
        "trusted_evidence", "enforcement_state", "verification_status",
    ):
        assert forbidden not in flat, forbidden


def test_identical_batch_resend_is_idempotent_in_process_and_across_restart(tmp_path):
    """A byte-identical batch resend creates no duplicates: the same
    proposal ids, per-candidate reuse, both on the same server instance
    and through a fully reconstructed store (durable idempotency)."""
    proposals_path = tmp_path / "decision_proposals.json"
    server = _mcp_server(proposals_path)
    payload = _batch_payload()

    first = _call(server, TOOL_PROPOSE_BATCH, payload).structured_content
    second = _call(server, TOOL_PROPOSE_BATCH, payload).structured_content

    count = len(first["results"])
    assert [r["created"] for r in first["results"]] == [True] * count
    assert [r["created"] for r in second["results"]] == [False] * count
    assert [r["reused"] for r in second["results"]] == [True] * count
    assert [
        r["proposal"]["proposal_id"] for r in first["results"]
    ] == [r["proposal"]["proposal_id"] for r in second["results"]]
    # The proposal records are identical; only the envelope outcome flags
    # differ (created/reused).
    assert [r["proposal"] for r in first["results"]] == [
        r["proposal"] for r in second["results"]
    ]

    # Reconstructed server over the same durable store: still idempotent.
    reconstructed = _mcp_server(proposals_path)
    third = _call(reconstructed, TOOL_PROPOSE_BATCH, payload).structured_content
    assert [r["created"] for r in third["results"]] == [False] * count
    assert [
        r["proposal"]["proposal_id"] for r in first["results"]
    ] == [r["proposal"]["proposal_id"] for r in third["results"]]
    assert [r["proposal"] for r in first["results"]] == [
        r["proposal"] for r in third["results"]
    ]

    # Exactly one proposal record per candidate exists.
    stored = _store(proposals_path).list_proposals()
    assert len(stored) == count
    assert len({p.proposal_id for p in stored}) == len(stored)


def test_producer_cannot_supply_authority_fields_through_mcp(tmp_path):
    """An attempted authority field through MCP is rejected by the
    existing transport schema (extra='forbid'); the schema is not changed
    to make this test pass."""
    proposals_path = tmp_path / "decision_proposals.json"
    server = _mcp_server(proposals_path)
    base = _batch_payload()

    for authority_field, value in (
        ("accepted_decision_id", "ddec-fabricated"),
        ("status", "accepted"),
        ("trusted_evidence", [{"selector": "t", "sha": "x"}]),
        ("include_paths", ["src/**"]),
        ("proposed_at", "2020-01-01T00:00:00Z"),
    ):
        tampered = json.loads(json.dumps(base))
        for candidate in tampered["candidates"]:
            candidate[authority_field] = value
        result = _call(server, TOOL_PROPOSE_BATCH, tampered)
        assert result.is_error is True, authority_field
        assert authority_field in result.content[0].text, authority_field

    # The batch envelope rejects authority fields too (shared provenance).
    tampered = json.loads(json.dumps(base))
    tampered["shared_provenance"]["status"] = "accepted"
    result = _call(server, TOOL_PROPOSE_BATCH, tampered)
    assert result.is_error is True
    assert "status" in result.content[0].text

    # Nothing was ingested through any of the failed attempts.
    assert _store(proposals_path).list_proposals() == ()


def test_mcp_reads_work_on_proposals_before_authority(tmp_path):
    """decision.get / search / applicable_to / trace consume the submitted
    proposals generically per their existing contracts; missing canonical /
    rule / evidence links are explicit and nothing is fabricated."""
    proposals_path = tmp_path / "decision_proposals.json"
    server = _mcp_server(proposals_path)
    payload = _batch_payload()
    fixture = _fixture()
    keys = [c["key"] for c in fixture["candidates"]]

    ingested = _call(server, TOOL_PROPOSE_BATCH, payload).structured_content
    proposal_ids = {
        key: item["proposal"]["proposal_id"]
        for key, item in zip(keys, ingested["results"])
    }

    # decision.get returns the proposal domain, not canonical lifecycle.
    first_id = proposal_ids[keys[0]]
    got = _call(server, TOOL_GET, {"record_id": first_id})
    assert got.structured_content["record_type"] == "proposal"
    proposal_payload = got.structured_content["proposal"]
    assert proposal_payload["proposal_status"] == "proposed"
    assert "lifecycle_status" not in proposal_payload
    assert proposal_payload["accepted_decision_id"] is None

    # decision.search finds the relevant proposals deterministically.
    found = _call(
        server, TOOL_SEARCH,
        {"query": "fail closed", "proposal_status": "proposed"},
    ).structured_content
    assert [p["proposal_id"] for p in found["proposals"]] == [
        proposal_ids["fail_closed_output_contract"]
    ]
    by_producer = _call(
        server, TOOL_SEARCH, {"producer_name": "ai-system-architect"}
    ).structured_content
    assert sorted(
        p["proposal_id"] for p in by_producer["proposals"]
    ) == sorted(proposal_ids.values())
    by_origin = _call(
        server, TOOL_SEARCH, {"origin_classification": ORIGIN_AI_GENERATED}
    ).structured_content
    assert sorted(
        p["proposal_id"] for p in by_origin["proposals"]
    ) == sorted(proposal_ids.values())
    # No canonical record exists in either domain yet.
    assert by_producer["canonical_decisions"] == []

    # applicable_to treats proposal scope hints as retrieval hints only.
    applicable = _call(
        server, TOOL_APPLICABLE_TO,
        {"context": ["architecture-generation pipeline for the producer"]},
    ).structured_content
    hint_ids = {m["proposal_id"] for m in applicable["proposal_hint_matches"]}
    assert proposal_ids["fail_closed_output_contract"] in hint_ids
    assert proposal_ids["reject_empty_input"] in hint_ids
    for match in applicable["proposal_hint_matches"]:
        assert set(match.keys()) == {"proposal_id", "matched_hints"}
    assert applicable["canonical_scope_matches"] == []
    flat = json.dumps(applicable)
    for forbidden in (
        "rule_payload", "include_paths", "exclude_paths",
        "applicability", "rule_id", "FORBID_LITERAL",
    ):
        assert forbidden not in flat, forbidden

    # trace identifies proposal provenance and reports missing links
    # explicitly; nothing canonical/rule/evidence is fabricated.
    for key in keys:
        traced = _call(
            server, TOOL_TRACE, {"record_id": proposal_ids[key]}
        ).structured_content
        assert traced["result_type"] == "proposal_trace"
        assert traced["proposal_id"] == proposal_ids[key]
        assert traced["proposal"]["proposal_status"] == "proposed"
        assert traced["accepted_decision_id"] is None
        assert traced["canonical_record"] is None
        assert traced["canonical_derived_rule_ids"] == []
        assert traced["source_provenance"] == _expected_provenance(
            fixture, fixture["candidates"][keys.index(key)]
        )
        missing = traced["missing_links"]
        assert any("accepted_decision_id" in m for m in missing)
        assert any("canonical_record" in m for m in missing)
        assert any("derived_rules" in m for m in missing)
        assert any("enforcement" in m for m in missing)
        assert any("trusted_evidence" in m for m in missing)

    # Unknown ids stay explicit, never fabricated.
    missing_get = _call(server, TOOL_GET, {"record_id": "ddec-unknown"})
    assert missing_get.structured_content["record_type"] == "not_found"
    assert missing_get.structured_content["record_id"] == "ddec-unknown"
    missing_trace = _call(server, TOOL_TRACE, {"record_id": "ddec-unknown"})
    assert missing_trace.structured_content["result_type"] == "trace_not_found"
    assert missing_trace.structured_content["record_id"] == "ddec-unknown"


# ── Human authority (review + transitions; never a producer capability) ─────


def test_human_cli_can_review_proposals(tmp_path):
    """mneme decision proposals / show render the stored proposals for
    human review, including the full informational provenance."""
    flow = _run_producer_flow(tmp_path)
    fixture = flow.fixture

    code, out, err = _run(
        ["decision", "proposals", "--proposals", str(flow.proposals_path)]
    )
    assert code == 0 and err == ""
    for candidate in fixture["candidates"]:
        proposal_id = flow.proposal_id_by_key[candidate["key"]]
        assert proposal_id in out
        assert candidate["title"] in out
    assert "ai-system-architect (architecture agent)" in out

    for candidate in fixture["candidates"]:
        proposal_id = flow.proposal_id_by_key[candidate["key"]]
        code, out, err = _run(
            [
                "decision", "show", proposal_id,
                "--proposals", str(flow.proposals_path),
            ]
        )
        assert code == 0 and err == ""
        assert f"status: {'accepted' if candidate['authority_intent'] == 'accept' else 'rejected'}" in out
        assert f"statement: {candidate['statement']}" in out
        assert "producer name: ai-system-architect" in out
        assert f"source version: {fixture['reference']['commit_sha']}" in out
        assert "origin classification: ai_generated" in out
        # Informational provenance is never presented as trusted/verified.
        assert "trusted" not in out.lower()
        assert "verified" not in out.lower()


def test_human_authority_accepts_and_rejects_selected_proposals(tmp_path):
    """Human authority accepts 3 and rejects 1: accepted proposals carry
    accepted_decision_id and materialize exactly one active decision each;
    the rejected proposal never materializes; provenance is retained."""
    flow = _run_producer_flow(tmp_path)
    fixture = flow.fixture
    store = _store(flow.proposals_path)
    by_id = {p.proposal_id: p for p in store.list_proposals()}

    # Exactly four proposals exist: three accepted, one rejected.
    assert len(by_id) == 4
    statuses = {p.status for p in by_id.values()}
    assert statuses == {"accepted", "rejected"}
    assert len([p for p in by_id.values() if p.status == "accepted"]) == 3

    # Accepted: proposed -> accepted, accepted_decision_id assigned, and it
    # is exactly the deterministic default id pinned by D2C1.
    for key in flow.accepted_keys:
        proposal_id = flow.proposal_id_by_key[key]
        proposal = by_id[proposal_id]
        decision_id = flow.decision_id_by_key[key]
        assert proposal.status == "accepted"
        assert proposal.accepted_decision_id == decision_id
        assert decision_id == default_decision_id_of(proposal)
        assert decision_id.startswith("ddec-")

    # Rejected: no accepted_decision_id, no project-memory decision.
    rejected_id = flow.proposal_id_by_key[flow.rejected_key]
    rejected = by_id[rejected_id]
    assert rejected.status == "rejected"
    assert rejected.accepted_decision_id is None

    # Producer provenance survives authority actions losslessly.
    for key, candidate in zip(
        [c["key"] for c in fixture["candidates"]], fixture["candidates"]
    ):
        proposal = by_id[flow.proposal_id_by_key[key]]
        assert proposal.candidate.provenance.producer_name == "ai-system-architect"
        assert proposal.candidate.provenance.producer_type == "architecture agent"
        assert (
            proposal.candidate.provenance.source_version
            == fixture["reference"]["commit_sha"]
        )
        assert (
            proposal.candidate.provenance.repository_locator
            == "sagarika29/ai-system-architect"
        )
        assert proposal.candidate.provenance.origin_classification == ORIGIN_AI_GENERATED

    # Materialized runtime shape: exactly one entry per accepted proposal,
    # the exact ADR-027 acceptance shape, nothing else.
    entries = _memory_entries(flow.memory_path)
    assert len(entries) == 3
    assert {e["id"] for e in entries} == set(flow.decision_id_by_key.values())
    statements = {e["decision"] for e in entries}
    rejected_candidate = next(
        c for c in fixture["candidates"] if c["key"] == flow.rejected_key
    )
    assert rejected_candidate["statement"] not in statements
    for key, candidate in zip(
        [c["key"] for c in fixture["candidates"]], fixture["candidates"]
    ):
        if candidate["authority_intent"] != "accept":
            continue
        entry = next(
            e for e in entries
            if e["id"] == flow.decision_id_by_key[key]
        )
        assert entry["decision"] == candidate["statement"]
        assert entry["rationale"] == candidate["rationale"]
        assert entry["scope"] == list(candidate["scope_hints"])
        assert entry["constraints"] == []
        assert entry["anti_patterns"] == []
        assert entry["rules"] == []
        assert entry["test_evidence"] == []
        assert entry["status"] == "active"


def test_rejected_proposal_is_a_full_negative_control(tmp_path):
    """The rejected proposal remains in the store, remains retrievable as
    rejected through the authority and read surfaces, never materializes,
    and never appears as an Audit decision."""
    flow = _run_producer_flow(tmp_path)
    fixture = flow.fixture
    rejected_id = flow.proposal_id_by_key[flow.rejected_key]
    rejected_candidate = next(
        c for c in fixture["candidates"] if c["key"] == flow.rejected_key
    )

    # Retained and retrievable in the store.
    store = _store(flow.proposals_path)
    rejected = store.get(rejected_id)
    assert rejected is not None
    assert rejected.status == "rejected"
    assert rejected.accepted_decision_id is None

    # Retrievable as rejected through MCP search.
    server = _mcp_server(flow.proposals_path)
    found = _call(
        server, TOOL_SEARCH, {"proposal_status": "rejected"}
    ).structured_content
    assert [p["proposal_id"] for p in found["proposals"]] == [rejected_id]
    # ...and through the human authority read surface.
    code, out, err = _run(
        [
            "decision", "show", rejected_id,
            "--proposals", str(flow.proposals_path),
        ]
    )
    assert code == 0 and err == ""
    assert "status: rejected" in out

    # Not in project memory.
    entries = _memory_entries(flow.memory_path)
    assert rejected_candidate["statement"] not in {e["decision"] for e in entries}
    assert len(entries) == 3

    # Not an Audit decision.
    report = json.loads(flow.audit_report.read_text(encoding="utf-8"))
    assert rejected_id not in {d["id"] for d in report["decisions"]}
    assert rejected_candidate["statement"] not in {
        d["decision"] for d in report["decisions"]
    }


def test_mcp_itself_cannot_accept_or_reject(tmp_path):
    """The MCP inventory stays exactly the six tools; no accept/reject/
    authority operation or alias exists anywhere in the transport."""
    proposals_path = tmp_path / "decision_proposals.json"
    server = _mcp_server(proposals_path)
    names = _list_tool_names(server)
    assert sorted(names) == sorted(MCP_SIX_TOOLS)
    assert len(names) == 6
    for name in names:
        for fragment in (
            "accept", "reject", "activat", "supersede", "exception",
            "bypass", "evidence", "protect",
        ):
            assert fragment not in name, (name, fragment)
    assert set(APPROVED_TOOLS) == MCP_SIX_TOOLS

    # The frozen vocabulary keeps accepted/rejected reachable ONLY through
    # the human authority surface: no MCP call produced them here.
    statuses = {p.status for p in _store(proposals_path).list_proposals()}
    assert statuses == set()


# ── Architecture Audit (existing semantics only) ────────────────────────────


def test_accepted_decisions_reach_the_existing_audit(tmp_path):
    """The accepted decisions are evaluated by the EXISTING Architecture
    Audit under frozen ADR-026 semantics; acceptance never assigns a tier
    and never activates protection."""
    flow = _run_producer_flow(tmp_path)
    report = json.loads(flow.audit_report.read_text(encoding="utf-8"))

    assert report["schema"] == AUDIT_SCHEMA
    summary = report["summary"]
    assert summary["total_decisions"] == 3
    assert summary["protected"] == 0
    assert summary["mneme_ready"] == 0
    assert summary["requires_modelling"] == 2
    assert summary["guidance"] == 1
    assert summary["protection_relevant"] == 2
    assert summary["current_protection_pct"] == 0.0
    assert summary["protection_gap_pct"] == 100.0
    assert summary["identified_mneme_potential_pct"] == 100.0

    # Frozen tier semantics only: fail-closed output contract and
    # empty-input rejection are deterministic without a literalizable
    # guardrail (requires_modelling); the unit-testable boundary rule is
    # advisory (guidance). Acceptance did not assign any of these.
    expected_tiers = {
        "fail_closed_output_contract": ("deterministic", "requires_modelling"),
        "reject_empty_input": ("deterministic", "requires_modelling"),
        "testable_decisions_stay_deterministic": ("guidance", "guidance"),
    }
    by_decision_id = {d["id"]: d for d in report["decisions"]}
    assert set(by_decision_id) == set(flow.decision_id_by_key.values())

    for key, (intent, tier) in expected_tiers.items():
        decision_id = flow.decision_id_by_key[key]
        entry = next(
            e for e in _memory_entries(flow.memory_path) if e["id"] == decision_id
        )
        assert entry["rules"] == []
        assert entry["test_evidence"] == []
        audited = by_decision_id[decision_id]
        assert audited["status"] == "active"
        assert audited["intent"] == intent
        assert audited["protection_tier"] == tier
        assert audited["mneme_guardrail"] is None
        # Producer provenance is not enforcement evidence: every audited
        # decision reports no evidence despite rich provenance in the store.
        assert audited["evidence_confidence"] == "none"
        assert audited["evidence_sources"] == []

    # Identity linkage: proposal.accepted_decision_id == runtime Decision.id
    # == Audit decision.id, for every accepted proposal.
    for key in flow.accepted_keys:
        proposal_id = flow.proposal_id_by_key[key]
        decision_id = flow.decision_id_by_key[key]
        proposal = _store(flow.proposals_path).get(proposal_id)
        assert proposal.status == "accepted"
        assert proposal.accepted_decision_id == decision_id
        entry = next(
            e for e in _memory_entries(flow.memory_path) if e["id"] == decision_id
        )
        assert entry["id"] == decision_id
        assert by_decision_id[decision_id]["id"] == decision_id

    # Audit read-only: proposal store and project memory byte-identical
    # across Audit; a second identical run is byte-identical.
    assert flow.proposals_path.read_bytes() == flow.post_authority_proposals
    assert flow.memory_path.read_bytes() == flow.post_authority_memory
    assert flow.audit_report_rerun.read_bytes() == flow.audit_report.read_bytes()


# ── Post-authority MCP visibility + canonical composition boundary ──────────


def test_reconstructed_mcp_sees_durable_accepted_proposal_state(tmp_path):
    """A reconstructed MCP server observes the proposal transition the
    separate human authority surface performed: proposal_status accepted
    with the durable accepted_decision_id; trace reports the currently
    known/missing canonical linkage honestly."""
    flow = _run_producer_flow(tmp_path)
    fixture = flow.fixture
    server = _mcp_server(flow.proposals_path)

    for key in flow.accepted_keys:
        proposal_id = flow.proposal_id_by_key[key]
        decision_id = flow.decision_id_by_key[key]

        got = _call(server, TOOL_GET, {"record_id": proposal_id})
        payload = got.structured_content
        assert payload["record_type"] == "proposal"
        assert payload["proposal"]["proposal_status"] == "accepted"
        assert payload["proposal"]["accepted_decision_id"] == decision_id

        traced = _call(server, TOOL_TRACE, {"record_id": proposal_id})
        trace_payload = traced.structured_content
        assert trace_payload["result_type"] == "proposal_trace"
        assert trace_payload["accepted_decision_id"] == decision_id
        # The accepted canonical decision is NOT composed into this MCP
        # server's canonical index (documented D2 composition boundary):
        # trace reports the missing link explicitly instead of fabricating
        # a canonical record, derived rules, or evidence.
        assert trace_payload["canonical_record"] is None
        assert trace_payload["canonical_derived_rule_ids"] == []
        missing = trace_payload["missing_links"]
        assert any(decision_id in m and "canonical_record" in m for m in missing)
        assert any("enforcement" in m for m in missing)
        assert any("trusted_evidence" in m for m in missing)
        flat = json.dumps(trace_payload)
        for fabricated in ("FORBID_LITERAL", "rule_payload"):
            assert fabricated not in flat, fabricated

    # Canonical accepted-decision visibility, explicitly characterized:
    # the accepted decision id is not an MCP-visible canonical record.
    canonical_id = flow.decision_id_by_key["fail_closed_output_contract"]
    got_canonical = _call(server, TOOL_GET, {"record_id": canonical_id})
    assert got_canonical.structured_content["record_type"] == "not_found"
    traced_canonical = _call(server, TOOL_TRACE, {"record_id": canonical_id})
    assert traced_canonical.structured_content["result_type"] == "trace_not_found"
    assert traced_canonical.structured_content["record_id"] == canonical_id


def test_decision_mcp_composition_has_no_project_memory_input():
    """The current supported MCP composition contract serves the proposal
    store plus an optional strict ADR canonical directory; no supported
    input composes project_memory-backed decisions into the canonical
    index. Recorded, not changed."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        with pytest.raises(SystemExit) as excinfo:
            main(["decision-mcp", "--help"])
    assert excinfo.value.code == 0
    help_text = stdout.getvalue()
    # The supported inputs are the proposal store and an explicit strict
    # canonical ADR directory only.
    assert "--proposals" in help_text
    assert "--adr-dir" in help_text
    assert "--memory" not in help_text


# ── Long-running MCP store freshness ────────────────────────────────────────


def test_long_running_mcp_instance_stays_stale_without_restart(tmp_path):
    """A server instance created BEFORE the external CLI authority action
    does NOT observe the proposal transition without restart; a
    reconstructed server correctly reads the durable proposal state.

    Current behavior, explicitly characterized: the proposal store is
    loaded once at construction (documented D2B store contract); no live
    cross-process refresh is promised, so this is recorded as expected
    behavior and no file-watching/reload behavior is added."""
    proposals_path = tmp_path / "decision_proposals.json"
    memory_path = _write_memory(tmp_path / ".mneme" / "project_memory.json")
    stale_server = _mcp_server(proposals_path)

    ingested = _call(stale_server, TOOL_PROPOSE_BATCH, _batch_payload())
    assert ingested.is_error is False
    proposal_id = ingested.structured_content["results"][0]["proposal"][
        "proposal_id"
    ]

    # A separate human authority surface transitions the proposal against
    # the same durable store path.
    code, out, err = _run(
        [
            "decision", "accept", proposal_id,
            "--proposals", str(proposals_path),
            "--memory", str(memory_path),
        ]
    )
    assert code == 0, out + err
    decision_id = _decision_id_from_output(out)

    # The already-running MCP instance remains stale: it still serves the
    # in-memory proposed record and never sees the transition.
    stale = _call(stale_server, TOOL_GET, {"record_id": proposal_id})
    stale_payload = stale.structured_content["proposal"]
    assert stale_payload["proposal_status"] == "proposed"
    assert stale_payload["accepted_decision_id"] is None

    # A reconstructed server reads the durable proposal state correctly.
    fresh_server = _mcp_server(proposals_path)
    fresh = _call(fresh_server, TOOL_GET, {"record_id": proposal_id})
    fresh_payload = fresh.structured_content["proposal"]
    assert fresh_payload["proposal_status"] == "accepted"
    assert fresh_payload["accepted_decision_id"] == decision_id


# ── No producer-specific runtime logic ──────────────────────────────────────


def _runtime_sources() -> dict[str, list[str]]:
    sources: dict[str, list[str]] = {}
    for path in sorted(RUNTIME_DIR.rglob("*.py")):
        sources[path.name] = path.read_text(encoding="utf-8").splitlines()
    return sources


def test_no_runtime_module_gained_producer_specific_logic():
    """No runtime module contains producer-specific code, parsing, or
    fixture-derived logic. The only permitted runtime occurrence of the
    reference-producer name is the pre-existing ADR-026 provenance comment
    in mneme/enforcer.py (part of the validated pre-D2D baseline); D2D
    added zero runtime occurrences."""
    sources = _runtime_sources()

    # Pre-existing provenance tokens: exactly the one frozen comment line.
    for token in PREEXISTING_PROVENANCE_TOKENS:
        hits = [
            (name, line)
            for name, lines in sources.items()
            for line in lines
            if token in line
        ]
        assert len(hits) == 1, (token, hits)
        assert hits[0][0] == "enforcer.py", (token, hits)

    # Fixture-derived tokens must not appear anywhere in runtime code.
    for token in FORBIDDEN_RUNTIME_TOKENS:
        hits = [
            (name, line)
            for name, lines in sources.items()
            for line in lines
            if token in line
        ]
        assert hits == [], (token, hits)

    # No runtime module reaches the test suite or the fixture.
    for name, lines in sources.items():
        joined = "\n".join(lines)
        assert "import tests" not in joined and "from tests" not in joined, name

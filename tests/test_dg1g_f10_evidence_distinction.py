"""DG1G F10: DG1 never upgrades configured evidence to observed (ADR-029 §6).

ADR-031 §13 requires a DG1-mapped fixture for "configured versus
execution-observed evidence (ADR-029 §6)". The DG1G fixture-floor mapping
(#782, updated #789) classified it *partial*: the Verification track and the
ADR-034 hook tests establish the three evidence concepts, but no DG1 test
asserted that a DG1 resolution or DG1E evidence identity never turns
configured protection into execution-observed or relevant-enforcement-
observed evidence.

This file pins that, across the ADR-029 §6 scenarios, using the real hook
entry point and in-process ``mneme check`` (the only path on which relevant
enforcement is observable today, ADR-029 evidence audit #761 E-1):

- **A (configured only):** an effective decision with a complete canonical
  identity and no runtime record is never relevant; DG1 outputs have no
  observation channel at all.
- **B (EXCLUDED by path applicability):** the hook ran and recorded the
  event, the DG1 identity stays complete, relevance is false.
- **C vs identity:** in one real event, two rules carry equally complete DG1
  identities but only the APPLIED, decided, attributable rule is relevant.
  Complete identity is necessary, never sufficient.
- **D (literal channel):** literal-rule evidence has complete identity but no
  per-rule relevance on any surface (#761 E-8).
- **E (stale version):** after a new decision version with the same rule, the
  relevance boolean (keyed by ``rule_id``) is unchanged, but the complete DG1
  identity of the V1 observation differs from the claim under the active
  V2. A version-specific claim fails closed (#761 §5.1, owner ruling
  condition 2).

Test-only. No runtime, schema or output change.
"""
from __future__ import annotations

import dataclasses
import io
import json
from pathlib import Path

import pytest

from mneme.decision_governance import (
    DecisionResolution,
    EvidenceIdentity,
    GovernanceContext,
    GovernanceResolution,
    resolve_effective,
)
from mneme.decision_index_persistence import (
    append_canonical_version_occurrence,
    load_decision_index_from_memory_file,
    rebuild_compatibility_snapshot,
)
from mneme.integrations.claude_code import hook
from mneme.numeric_rule import NumericContract
from mneme.rule_identity import rule_id_for
from mneme.schemas import Rule
from tests.canonical_fixtures import canonical_document

HOST = ("2.1.303", "cd" * 32)
RULE_A = Rule(
    type="FORBID_NUMERIC_ABOVE",
    value=NumericContract(
        max="5", unit="seconds", symbol="ROUTER_DEADLINE_S",
        call_function="classify", call_position=1,
    ).canonical_value(),
    include_paths=("src/**",),
)
RULE_B = Rule(
    type="FORBID_NUMERIC_ABOVE",
    value=NumericContract(
        max="3", unit="attempts", symbol="RETRY_LIMIT",
        call_function="retry", call_position=1,
    ).canonical_value(),
    include_paths=("src/**",),
)
A_ID = rule_id_for("F10-A", RULE_A)
B_ID = rule_id_for("F10-B", RULE_B)
A_ABOVE = "ROUTER_DEADLINE_S = 60\ndef run(x):\n    return classify(x, 2)\n"
B_WITHIN = "RETRY_LIMIT = 2\ndef go(x):\n    return retry(x, 1)\n"
LITERAL = "import psycopg2\n"


def _numeric(decision_id: str, rule: Rule) -> dict:
    return {
        "id": decision_id, "decision": f"{decision_id} numeric bound", "rationale": "r",
        "scope": ["router"],
        "rules": [{"type": rule.type, "value": rule.value,
                   "include_paths": list(rule.include_paths)}],
        "created_at": "2026-11-10", "updated_at": "2026-11-10", "status": "active",
    }


def _document() -> dict:
    return canonical_document({
        "meta": {"name": "dg1g-f10", "description": "ADR-029 §6 from the DG1 side"},
        "items": [],
        "decisions": [
            {"id": "F10-LIT", "decision": "Do not use psycopg2", "rationale": "r",
             "scope": ["storage"],
             "rules": [{"type": "FORBID_LITERAL", "value": "psycopg2"}],
             "created_at": "2026-11-10", "updated_at": "2026-11-10",
             "status": "active"},
            _numeric("F10-A", RULE_A),
            _numeric("F10-B", RULE_B),
        ],
    })


@pytest.fixture
def project(tmp_path, monkeypatch):
    for name in ("MNEME_MEMORY", "MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE",
                 "MNEME_HOOK_EVIDENCE_LOG", "MNEME_HOOK_EVIDENCE_HOST_VERSION",
                 "MNEME_HOOK_EVIDENCE_HOST_SHA256"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MNEME_HOOK_CHECK_TRANSPORT", "inprocess")
    monkeypatch.setenv("MNEME_HOOK_MODE", "strict")
    (tmp_path / ".mneme").mkdir()
    _memory(tmp_path).write_text(json.dumps(_document()), encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    return tmp_path


@pytest.fixture
def log(project, monkeypatch, tmp_path_factory):
    path = tmp_path_factory.mktemp("evidence") / "events.jsonl"
    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_LOG", str(path))
    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_HOST_VERSION", HOST[0])
    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_HOST_SHA256", HOST[1])
    return path


def _memory(project: Path) -> Path:
    return project / ".mneme" / "project_memory.json"


def _run(project: Path, log: Path, content: str, rel: str = "src/new.py") -> dict:
    envelope = {
        "hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(project),
        "tool_input": {"file_path": str(project / rel), "content": content},
        "session_id": "sess-f10", "tool_use_id": "toolu_f10",
    }
    hook.handle_event(envelope, stderr=io.StringIO(), stdout=io.StringIO())
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return json.loads(lines[-1]) if lines else {}


def _observed_identity(record: dict, rule_id: str) -> EvidenceIdentity:
    """DG1E identity of one hook rule record (decision id is the rule_id prefix)."""
    rule = next(r for r in record["rules"] if r["rule_id"] == rule_id)
    return EvidenceIdentity(
        decision_id=rule["rule_id"].split(":", 1)[0],
        decision_version_id=rule.get("decision_version_id", ""),
        rule_id=rule["rule_id"],
    )


def _claimed_identity(project: Path, rule_id: str) -> EvidenceIdentity:
    """The DG1 claim: the governing decision's active version and that rule."""
    resolution = resolve_effective(
        load_decision_index_from_memory_file(_memory(project)), GovernanceContext()
    )
    decision = next(d for d in resolution.decisions if rule_id in d.rule_ids)
    assert decision.effective
    return EvidenceIdentity(
        decision_id=decision.decision_id,
        decision_version_id=decision.decision_version_id,
        rule_id=rule_id,
    )


# ── A. configured only: no observation channel in DG1 ─────────────────────


def test_a_dg1_outputs_have_no_observation_channel() -> None:
    """DG1 resolution carries governance only. Adding any evidence or
    observation field must be a deliberate, reviewed change to this test."""
    assert {f.name for f in dataclasses.fields(DecisionResolution)} == {
        "decision_id", "decision_version_id", "lifecycle_status", "status",
        "cause", "rule_ids", "superseded_by", "applicability_required_labels",
        "lifecycle_eligible", "applicability_evaluated", "trace", "waiver_ids",
    }
    assert {f.name for f in dataclasses.fields(GovernanceResolution)} == {
        "semantics_version", "context", "decisions", "findings",
    }
    assert {f.name for f in dataclasses.fields(EvidenceIdentity)} == {
        "decision_id", "decision_version_id", "rule_id",
    }


def test_a_configured_identity_without_a_runtime_record_is_never_relevant(project) -> None:
    for rule_id in (A_ID, B_ID):
        claimed = _claimed_identity(project, rule_id)
        assert claimed.complete
    steps = {
        step.step
        for decision in resolve_effective(
            load_decision_index_from_memory_file(_memory(project))
        ).decisions
        for step in decision.trace
    }
    assert steps <= {"authority", "lifecycle", "supersession", "precedence",
                     "applicability", "waiver", "result"}
    assert hook.relevant_enforcement_per_rule(None, HOST) == {}
    assert hook.relevant_enforcement_observed({}, HOST) is False


# ── B. EXCLUDED by path applicability ─────────────────────────────────────


def test_b_excluded_path_is_execution_observed_but_never_relevant(project, log) -> None:
    # Real run outside the rules' ``src/**`` selectors: the hook executed and
    # recorded the event, but carries no applied numeric rule.
    record = _run(project, log, A_ABOVE, rel="docs/new.py")
    assert record["hook_outcome"] == "proceeded"
    assert record["rules"] == []
    for rule_id in (A_ID, B_ID):
        assert _claimed_identity(project, rule_id).complete  # still configured
    assert hook.relevant_enforcement_per_rule(record, HOST) == {}
    assert hook.relevant_enforcement_observed(record, HOST) is False


def test_b_excluded_applicability_drops_relevance_not_identity(project, log) -> None:
    record = _run(project, log, A_ABOVE + B_WITHIN)
    assert hook.relevant_enforcement_per_rule(record, HOST)[A_ID] is True
    rule = next(r for r in record["rules"] if r["rule_id"] == A_ID)
    rule["applicability"] = "EXCLUDED"
    assert hook.relevant_enforcement_per_rule(record, HOST)[A_ID] is False
    assert _observed_identity(record, A_ID) == _claimed_identity(project, A_ID)
    assert _observed_identity(record, A_ID).complete


# ── C. complete identity is necessary, never sufficient ───────────────────


def test_c_equal_complete_identities_do_not_imply_equal_relevance(project, log) -> None:
    record = _run(project, log, A_ABOVE + B_WITHIN)
    relevance = hook.relevant_enforcement_per_rule(record, HOST)
    assert relevance == {A_ID: True, B_ID: False}
    for rule_id in (A_ID, B_ID):
        observed = _observed_identity(record, rule_id)
        assert observed.complete
        assert observed == _claimed_identity(project, rule_id)


# ── D. literal channel stops at execution observed ────────────────────────


def test_d_literal_evidence_has_identity_but_no_relevance(project, log) -> None:
    record = _run(project, log, LITERAL)
    literal_ids = [
        v.get("rule_id") for v in record.get("violations", [])
        if v.get("rule_type") == "FORBID_LITERAL"
    ]
    assert literal_ids, "the literal rule must be reported (execution observed)"
    (literal_id,) = literal_ids
    claimed = _claimed_identity(project, literal_id)
    assert claimed.complete
    assert literal_id not in hook.relevant_enforcement_per_rule(record, HOST)
    assert hook.relevant_enforcement_observed(record, HOST) is False


# ── E. stale version: boolean unchanged, DG1 identity fails closed ────────


def test_e_observation_under_v1_never_establishes_a_claim_under_v2(project, log) -> None:
    record = _run(project, log, A_ABOVE + B_WITHIN)
    assert hook.relevant_enforcement_per_rule(record, HOST)[A_ID] is True
    v1_claim = _claimed_identity(project, A_ID)
    assert _observed_identity(record, A_ID) == v1_claim

    document = json.loads(_memory(project).read_text(encoding="utf-8"))
    (logical,) = [
        row for row in document["decision_index"]["decisions"]
        if row["decision_id"] == "F10-A"
    ]
    evolved, v2, created = append_canonical_version_occurrence(
        document,
        decision_id="F10-A",
        predecessor_version_id=logical["active_version_id"],
        statement="F10-A numeric bound, revised rationale",
        rationale="revised",
        context_scope=["router"],
        constraints=[],
        anti_patterns=[],
        rules=[RULE_A],
        created_at="2026-11-11",
        updated_at="2026-11-11",
        occurrence_source_identity=["F10-A", "rev-2"],
        source_evidence=[],
    )
    assert created
    # As an authority write does: re-project decisions[] from the index.
    evolved = rebuild_compatibility_snapshot(evolved)
    _memory(project).write_text(json.dumps(evolved), encoding="utf-8")

    v2_claim = _claimed_identity(project, A_ID)
    assert v2_claim.decision_version_id == v2 != v1_claim.decision_version_id
    assert v2_claim.rule_id == A_ID  # same rule configuration, same rule_id
    # The standalone boolean is keyed by rule_id and cannot see the version.
    assert hook.relevant_enforcement_per_rule(record, HOST)[A_ID] is True
    # The complete DG1 identity does: the V1 observation is not the V2 claim.
    assert _observed_identity(record, A_ID) != v2_claim

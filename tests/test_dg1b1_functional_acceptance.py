"""DG1B1 functional acceptance on a real-repository decision (ADR-031, charter #473).

Scenario: GSA-TTS/agentic-coding-quickstart ADR-0028 (Windows-native secret
storage), pinned at commit ``8e6160c63acc35bd48d0a3844e133ea3ad52a464``. The
source decision is explicitly *gated to Windows hosts (MSYS/MINGW)* — the
concrete repository case the DG1B1 charter cites as evidence for decision
applicability.

The canonical decision is constructed explicitly through Mneme-owned
persistence interfaces (the migration transform plus
``set_decision_applicability``), with the pinned source provenance recorded.
O1A classification is research data and is deliberately not treated as
canonical authority. The evidence fixture is captured under
``tests/fixtures/dg1b1_functional_acceptance/`` so this test is reproducible and
network-independent after the fixture was established (it was cross-checked
once against the pinned upstream revision).

This file exercises production interfaces only; it does not reimplement
resolver logic.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from mneme.cli import main as cli_main
from mneme.decision_governance import (
    CAUSE_LIFECYCLE_SUPERSEDED,
    CAUSE_NOT_APPLICABLE,
    CHANGE_GOVERNED_SCOPE,
    GovernanceContext,
    resolve_change,
    resolve_effective,
    resolve_effective_from_memory_file,
)
from mneme.decision_index_persistence import (
    APPLICABILITY_FEATURE,
    DECISION_INDEX_SCHEMA,
    DECISION_INDEX_SCHEMA_V2,
    apply_memory_migration,
    load_decision_index_from_memory_file,
    load_persisted_decision_index,
    plan_memory_migration,
    set_decision_applicability,
)
from mneme.decision_projection import project_canonical_index
from mneme.memory_store import MemoryStore
from tests.canonical_fixtures import canonical_document, v1_document

FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "dg1b1_functional_acceptance"
    / "gsa_adr_0028_windows_secret_storage.json"
)

DECISION_ID = "0028-windows-native-secret-storage"
REQUIRED_LABELS = ("platform:windows",)
STATEMENT = (
    "acq stores Windows secrets with the DPAPI-backed keychain-windows "
    "backend, gated to Windows hosts (MSYS/MINGW); the plain file backend "
    "remains the fallback."
)
# A deterministic rule a Mneme author attaches to encode the fail-closed
# plaintext-export prohibition. Test-authored: it is not derived from O1A
# classification and does not claim source authority.
AUTHORED_RULE = {"type": "FORBID_LITERAL", "value": "dpapi-plaintext-export"}
SOURCE_DATE = "2026-09-13T00:00:00Z"


@pytest.fixture(scope="module")
def evidence() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# ── the evidence fixture must be pinned and verifiable ────────────────────


def test_source_evidence_is_pinned_and_verifiable(evidence: dict) -> None:
    assert evidence["repository"] == "GSA-TTS/agentic-coding-quickstart"
    assert (
        evidence["repository_commit_sha"]
        == "8e6160c63acc35bd48d0a3844e133ea3ad52a464"
    )
    assert evidence["source_file"] == "docs/adr/0028-windows-native-secret-storage.md"
    assert evidence["source_location"] == "L1-L12; L106-L140"
    assert (
        hashlib.sha256(evidence["source_evidence"].encode("utf-8")).hexdigest()
        == evidence["source_evidence_sha256"]
    )
    # The exact decision sentence the charter cites, and the accepted status.
    # The source wraps across lines, so compare on normalized whitespace.
    normalized = " ".join(evidence["source_evidence"].split())
    assert "gated to Windows hosts (MSYS/MINGW)" in normalized
    assert "status: accepted" in evidence["source_evidence"]


# ── construction helpers (Mneme-owned interfaces only) ────────────────────


def _pre_d1(evidence: dict, *, status: str = "active") -> dict:
    """A pre-D1 project-memory document carrying the ADR-0028 decision."""
    return {
        "meta": {
            "name": "dg1b1-functional-acceptance",
            "description": "GSA-TTS/agentic-coding-quickstart ADR-0028 scenario",
        },
        "items": [],
        "examples": [],
        "decisions": [
            {
                "id": DECISION_ID,
                "decision": STATEMENT,
                "rationale": evidence["source_evidence"],
                "scope": ["acq.secret-store.windows"],
                "constraints": [],
                "anti_patterns": [],
                "rules": [dict(AUTHORED_RULE)],
                "test_evidence": [],
                "source": {
                    "type": "adr",
                    "path": evidence["source_file"],
                    "sha256": evidence["repository_commit_sha"],
                },
                "created_at": SOURCE_DATE,
                "updated_at": SOURCE_DATE,
                "status": status,
            }
        ],
    }


def _v2(evidence: dict, *, status: str = "active") -> dict:
    return canonical_document(_pre_d1(evidence, status=status))


def _applied(evidence: dict, *, status: str = "active") -> dict:
    document, changed = set_decision_applicability(
        _v2(evidence, status=status),
        decision_id=DECISION_ID,
        required_labels=REQUIRED_LABELS,
    )
    assert changed is True
    return document


def _index(document: dict):
    return load_persisted_decision_index(document["decision_index"])


def _write(path: Path, document: dict) -> Path:
    path.write_bytes(json.dumps(document, indent=2).encode("utf-8") + b"\n")
    return path


def _cause(index, labels=()) -> str | None:
    (decision,) = [
        d for d in resolve_effective(index, GovernanceContext(labels=labels)).decisions
        if d.decision_id == DECISION_ID
    ]
    return decision.cause


# ── F1: canonical v1 decision remains globally eligible ───────────────────


def test_f1_v1_decision_is_globally_eligible(evidence: dict) -> None:
    v1 = v1_document(_v2(evidence))
    index = load_persisted_decision_index(v1["decision_index"])
    assert index.records[0].applicability_required_labels == ()
    resolution = resolve_effective(index)
    assert resolution.effective_ids == (DECISION_ID,)
    assert resolution.decisions[0].cause is None


# ── F2: explicit v1 -> v2 migration preserves identities ──────────────────


def test_f2_v1_to_v2_upgrade_preserves_all_identities(
    evidence: dict, tmp_path: Path
) -> None:
    v1 = v1_document(_v2(evidence))
    path = _write(tmp_path / "project_memory.json", v1)
    before_index = load_decision_index_from_memory_file(path)

    before_decisions = copy.deepcopy(v1["decision_index"]["decisions"])
    before_versions = copy.deepcopy(v1["decision_index"]["versions"])
    before_rules = copy.deepcopy(v1["decision_index"]["rules"])
    before_snapshot = copy.deepcopy(v1["decisions"])

    plan = plan_memory_migration(path, to_v2=True)
    assert plan.state == "upgrade_to_v2"
    assert apply_memory_migration(plan) is True

    raw = json.loads(path.read_text(encoding="utf-8"))
    section = raw["decision_index"]
    assert section["schema"] == DECISION_INDEX_SCHEMA_V2
    assert section["semantic_features"] == []
    # Decision, version, rule and compatibility identities are unchanged.
    assert section["decisions"] == before_decisions
    assert section["versions"] == before_versions
    assert section["rules"] == before_rules
    assert raw["decisions"] == before_snapshot

    after_index = load_decision_index_from_memory_file(path)
    before_record, after_record = before_index.records[0], after_index.records[0]
    assert after_record.decision_id == before_record.decision_id == DECISION_ID
    assert after_record.version_id == before_record.version_id
    assert after_record.content_digest == before_record.content_digest
    assert after_record.derived_rule_ids == before_record.derived_rule_ids
    assert after_record.applicability_required_labels == ()
    assert project_canonical_index(before_index) == project_canonical_index(after_index)


# ── F3-F7: applicability assignment and deterministic resolution ──────────


def test_f3_assign_required_labels(evidence: dict, tmp_path: Path) -> None:
    document = _applied(evidence)
    section = document["decision_index"]
    assert section["schema"] == DECISION_INDEX_SCHEMA_V2
    assert APPLICABILITY_FEATURE in section["semantic_features"]
    (record,) = load_persisted_decision_index(section).records
    assert record.applicability_required_labels == REQUIRED_LABELS
    # Round-trips through the file boundary.
    path = _write(tmp_path / "project_memory.json", document)
    assert (
        load_decision_index_from_memory_file(path).records[0].applicability_required_labels
        == REQUIRED_LABELS
    )


def test_f4_windows_context_is_effective(evidence: dict) -> None:
    index = _index(_applied(evidence))
    resolution = resolve_effective(index, GovernanceContext(labels=("platform:windows",)))
    assert resolution.effective_ids == (DECISION_ID,)
    assert resolution.decisions[0].cause is None


@pytest.mark.parametrize(
    "labels",
    [
        pytest.param(("platform:linux",), id="f5-linux"),
        pytest.param((), id="f6-absent"),
        pytest.param(("Platform:Windows",), id="f7-miscased"),
    ],
)
def test_f5_f7_not_applicable_cases(evidence: dict, labels: tuple[str, ...]) -> None:
    index = _index(_applied(evidence))
    resolution = resolve_effective(index, GovernanceContext(labels=labels))
    assert resolution.effective_ids == ()
    assert _cause(index, labels) == CAUSE_NOT_APPLICABLE
    trace = {step.step: step.outcome for step in resolution.decisions[0].trace}
    assert trace["applicability"] == "not_applicable"


# ── F8: removing applicability restores global eligibility ────────────────


def test_f8_removed_applicability_is_globally_effective(evidence: dict) -> None:
    # No public removal API exists (charter §4). A separate validated state is
    # built by dropping the per-decision key from a validated document and
    # reloading it through the production loader, which re-validates.
    removed = copy.deepcopy(_applied(evidence))
    removed["decision_index"]["decisions"][0].pop("applicability")
    index = load_persisted_decision_index(removed["decision_index"])
    assert index.records[0].applicability_required_labels == ()
    resolution = resolve_effective(index, GovernanceContext(labels=("platform:linux",)))
    assert resolution.effective_ids == (DECISION_ID,)
    assert resolution.decisions[0].cause is None


# ── F9: lifecycle cause takes precedence over applicability ───────────────


def test_f9_superseded_lifecycle_wins_over_applicability(evidence: dict) -> None:
    index = _index(_applied(evidence, status="superseded"))
    assert index.records[0].lifecycle_status == "superseded"
    # Matching labels: lifecycle still wins.
    assert _cause(index, ("platform:windows",)) == CAUSE_LIFECYCLE_SUPERSEDED
    # Missing labels: cause is lifecycle, never not_applicable.
    assert _cause(index, ()) == CAUSE_LIFECYCLE_SUPERSEDED
    for decision in resolve_effective(index).decisions:
        assert decision.cause != CAUSE_NOT_APPLICABLE


# ── F10: snapshot comparison reports governed-scope change ────────────────


def test_f10_resolve_change_reports_governed_scope_change(evidence: dict) -> None:
    change = resolve_change(
        _index(_v2(evidence)),
        _index(_applied(evidence)),
        GovernanceContext(labels=()),
    )
    assert change.affected_decision_ids == (DECISION_ID,)
    (delta,) = change.changes
    assert CHANGE_GOVERNED_SCOPE in delta.kinds


# ── F11: deterministic resolution and idempotent migration replay ─────────


def test_f11_resolution_and_migration_replay_are_deterministic(
    evidence: dict, tmp_path: Path
) -> None:
    document = _applied(evidence)
    index = _index(document)
    context = GovernanceContext(labels=REQUIRED_LABELS)
    assert resolve_effective(index, context) == resolve_effective(index, context)

    path = _write(tmp_path / "project_memory.json", document)
    assert resolve_effective_from_memory_file(path, context) == resolve_effective(
        load_decision_index_from_memory_file(path), context
    )

    # Replaying the v1 -> v2 upgrade on a v2 file is a byte-identical no-op.
    before = path.read_bytes()
    assert apply_memory_migration(plan_memory_migration(path, to_v2=True)) is False
    assert path.read_bytes() == before

    # Re-applying the same applicability is a no-op.
    _, changed = set_decision_applicability(
        document, decision_id=DECISION_ID, required_labels=REQUIRED_LABELS
    )
    assert changed is False


# ── F12: existing runtime projection and enforcement inputs unchanged ─────


def test_f12_runtime_projection_and_enforcement_inputs_unchanged(
    evidence: dict, tmp_path: Path
) -> None:
    with_scope = _applied(evidence)
    without_scope = _v2(evidence)
    # Layer 1 projection (the enforcement input) is identical.
    assert project_canonical_index(_index(with_scope)) == project_canonical_index(
        _index(without_scope)
    )

    # The CLI enforcement verdict is unchanged: a typed literal is enforced
    # corpus-wide regardless of decision applicability (DG1F not wired).
    probe = tmp_path / "probe.txt"
    probe.write_text("export dpapi-plaintext-export to a plaintext file\n", encoding="utf-8")
    verdicts = []
    for name, document in (("without", without_scope), ("with", with_scope)):
        path = _write(tmp_path / f"{name}.json", document)
        verdicts.append(
            cli_main([
                "check", "--memory", str(path), "--input", str(probe),
                "--query", "windows secret storage", "--mode", "strict",
            ])
        )
    assert verdicts[0] == verdicts[1] != 0

    # MemoryStore (the shared runtime loader) exposes the same decisions.
    left = MemoryStore(_write(tmp_path / "store-without.json", without_scope)).load().decisions
    right = MemoryStore(_write(tmp_path / "store-with.json", with_scope)).load().decisions
    assert [d.id for d in left] == [d.id for d in right] == [DECISION_ID]
    assert [d.decision for d in left] == [d.decision for d in right]
    assert [d.rules for d in left] == [d.rules for d in right]

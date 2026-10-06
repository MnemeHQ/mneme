"""D1E2b: canonical ``protect activate`` writer (ADR-030 §9, §9a).

On canonical memory, protection installs one ``protection`` rule binding on
the decision's active version at ``max(sequence) + 1``. The owning version
record and every existing binding stay immutable. The re-derived
compatibility snapshot and the activation record land in one guarded write.
Section-less memory keeps the legacy write until D1E5 (pinned in the
containment and M1.4 activation suites).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.cli import main
from mneme.decision_index_persistence import (
    DecisionIndexPersistenceError,
    append_protection_binding,
    load_decision_index_from_memory_file,
)
from mneme.memory_store import MemoryStore
from mneme.protection import (
    ProtectionError,
    _install_canonical_rule,
    _install_rule,
    activate_protection,
)
from mneme.schemas import Rule
from tests.canonical_fixtures import migrate_memory_fixture

BASE_TS = "2026-01-01T00:00:00Z"

READY = {
    "id": "d_ready",
    "decision": "No postgres in the service layer",
    "rationale": "",
    "scope": ["storage"],
    "constraints": [],
    "anti_patterns": ["postgres"],
    "created_at": BASE_TS,
    "updated_at": BASE_TS,
}

SETUP_ACTIVATION = {
    "schema": "mneme.setup/v1",
    "state": "setup",
    "mneme_version": "0.6.0",
    "setup_started_at": BASE_TS,
    "setup_completed_at": BASE_TS,
    "activated_at": None,
    "audit_ref": "",
    "baseline": None,
    "integrations_detected": [],
    "integrations_configured": [],
    "enforcement": "not_enabled",
}

POSTGRES = Rule(type="FORBID_LITERAL", value="postgres")


def _repo(tmp_path: Path, decisions: list[dict], activation: dict | None = None):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    memory = root / ".mneme" / "project_memory.json"
    memory.parent.mkdir()
    document = {
        "meta": {"name": "d1e2b", "description": "canonical protect"},
        "items": [], "examples": [], "decisions": decisions,
    }
    if activation is not None:
        document["activation"] = activation
    memory.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    migrate_memory_fixture(memory)
    return root, memory


def _section(memory: Path) -> dict:
    return json.loads(memory.read_text(encoding="utf-8"))["decision_index"]


def _active(section: dict, decision_id: str) -> tuple[dict, list[dict]]:
    (logical,) = [r for r in section["decisions"] if r["decision_id"] == decision_id]
    version = next(
        v for v in section["versions"] if v["version_id"] == logical["active_version_id"]
    )
    rules = sorted(
        (r for r in section["rules"] if r["decision_version_id"] == version["version_id"]),
        key=lambda r: r["sequence"],
    )
    return version, rules


# ── Canonical activation ────────────────────────────────────────────────────


@pytest.mark.parametrize("activation", [None, SETUP_ACTIVATION])
def test_activate_writes_protection_binding_and_activation(tmp_path, activation):
    root, memory = _repo(tmp_path, [READY], activation)
    version_before, rules_before = _active(_section(memory), "d_ready")
    assert rules_before == []

    outcome = activate_protection("d_ready", memory, repo_root=root)

    assert outcome.result == "verified"
    assert outcome.rule_installed is True
    raw = json.loads(memory.read_text(encoding="utf-8"))
    version_after, rules_after = _active(raw["decision_index"], "d_ready")
    assert version_after == version_before  # version record untouched
    (binding,) = rules_after
    assert binding["binding_authority"] == "protection"
    assert binding["sequence"] == 0
    assert binding["rule_payload"] == {"value": "postgres"}
    assert binding["decision_version"] == version_before["revision"]
    assert raw["activation"]["state"] == "active"
    load_decision_index_from_memory_file(memory)  # snapshot parity holds
    store = MemoryStore(memory)
    store.load()
    (decision,) = store.decisions()
    assert [(r.type, r.value) for r in decision.rules] == [("FORBID_LITERAL", "postgres")]


def test_protection_appends_after_existing_bindings(tmp_path):
    root, memory = _repo(tmp_path, [{
        **READY,
        "rules": [
            {"type": "FORBID_LITERAL", "value": "alpha_client"},
            {"type": "FORBID_LITERAL", "value": "beta_client"},
        ],
    }])
    _, before = _active(_section(memory), "d_ready")

    assert _install_rule(memory, "d_ready", POSTGRES) is True

    _, after = _active(_section(memory), "d_ready")
    assert after[:2] == before  # existing bindings untouched
    assert [(r["sequence"], r["binding_authority"]) for r in after] == [
        (0, "legacy_unknown"), (1, "legacy_unknown"), (2, "protection"),
    ]


def test_reinstall_is_a_byte_identical_noop(tmp_path):
    _, memory = _repo(tmp_path, [READY])
    assert _install_rule(memory, "d_ready", POSTGRES) is True
    installed = memory.read_bytes()

    assert _install_rule(memory, "d_ready", POSTGRES) is False
    assert memory.read_bytes() == installed


def test_rule_already_bound_as_version_is_a_noop_never_rewritten(tmp_path):
    _, memory = _repo(tmp_path, [{
        **READY, "rules": [{"type": "FORBID_LITERAL", "value": "postgres"}],
    }])
    raw = json.loads(memory.read_text(encoding="utf-8"))
    for row in raw["decision_index"]["rules"]:
        row["binding_authority"] = "version"
    memory.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    before = memory.read_bytes()

    document, _, created = append_protection_binding(
        json.loads(before.decode("utf-8")), decision_id="d_ready", rule=POSTGRES
    )
    assert created is False
    assert _install_rule(memory, "d_ready", POSTGRES) is False
    assert memory.read_bytes() == before
    _, rules = _active(document["decision_index"], "d_ready")
    assert [r["binding_authority"] for r in rules] == ["version"]


def test_primitive_refuses_non_active_decision(tmp_path):
    _, memory = _repo(tmp_path, [{**READY, "status": "superseded"}])
    with pytest.raises(DecisionIndexPersistenceError, match="installs only on active"):
        append_protection_binding(
            json.loads(memory.read_text(encoding="utf-8")),
            decision_id="d_ready", rule=POSTGRES,
        )


def test_write_refused_when_file_changed_after_read(tmp_path):
    _, memory = _repo(tmp_path, [READY])
    stale = memory.read_bytes()
    raw = json.loads(stale.decode("utf-8"))
    memory.write_text(
        json.dumps({**raw, "meta": {**raw["meta"], "description": "changed"}}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    changed = memory.read_bytes()

    with pytest.raises(ProtectionError, match="changed after it was read"):
        _install_canonical_rule(memory, raw, stale, "d_ready", POSTGRES)

    assert memory.read_bytes() == changed


# ── Continuity integration (D1E2a) ──────────────────────────────────────────


def _adr(adr_dir: Path, *literals: str) -> None:
    constraints = "".join(f"- FORBID_LITERAL: {lit}\n" for lit in literals)
    (adr_dir / "ADR-900.md").write_text(
        "---\nid: ADR-900\ntitle: t\nstatus: accepted\npriority: normal\n"
        "date: 2026-04-15\nscope: \"storage\"\n---\n\n"
        f"## Constraints\n\n{constraints}",
        encoding="utf-8",
    )


def test_canonical_protection_is_held_by_continuity_on_adr_edit(tmp_path, capsys):
    adr_dir = tmp_path / "adrs"
    adr_dir.mkdir()
    _, memory = _repo(tmp_path, [])
    _adr(adr_dir, "alpha_client")
    assert main(["adr", "import", str(adr_dir), "--memory", str(memory), "--apply"]) == 0
    assert _install_rule(memory, "ADR-900", POSTGRES) is True
    (protected,) = [
        r for r in _section(memory)["rules"] if r["binding_authority"] == "protection"
    ]
    _adr(adr_dir, "gamma_client")  # unrelated edit
    capsys.readouterr()
    before = memory.read_bytes()

    refused = main([
        "adr", "import", str(adr_dir), "--memory", str(memory),
        "--apply", "--update-existing",
    ])
    assert refused == 2
    assert "would drop protection/legacy_unknown" in capsys.readouterr().err
    assert memory.read_bytes() == before

    assert main([
        "adr", "import", str(adr_dir), "--memory", str(memory),
        "--apply", "--update-existing",
        "--preserve-protection", protected["rule_id"],
    ]) == 0
    _, rules = _active(_section(memory), "ADR-900")
    assert [(r["rule_payload"]["value"], r["binding_authority"]) for r in rules] == [
        ("gamma_client", "version"), ("postgres", "protection"),
    ]


# ── Accepted-proposal retry after protection enrichment (D1E0) ──────────────


def test_accept_retry_survives_canonical_protection_enrichment(tmp_path):
    from mneme.decision_authority import DecisionAuthorityService
    from mneme.decision_proposal_store import JsonFileDecisionProposalStore
    from tests.test_decision_authority import FIXED_TIME, _propose

    proposals = tmp_path / "proposals.json"
    proposal = _propose(JsonFileDecisionProposalStore(proposals))
    _, memory = _repo(tmp_path, [])

    def accept():
        return DecisionAuthorityService(
            JsonFileDecisionProposalStore(proposals), memory,
            clock=lambda: FIXED_TIME,
        ).accept(proposal.proposal_id)

    decision_id = accept().decision_id
    assert _install_rule(
        memory, decision_id, Rule(type="FORBID_LITERAL", value="legacy_client")
    ) is True
    enriched = memory.read_bytes()

    retried = accept()

    assert retried.already_accepted is True
    assert retried.decision_id == decision_id
    assert memory.read_bytes() == enriched


def test_legacy_item_decision_still_not_activatable_on_canonical_memory(tmp_path):
    """Migrated items[] decisions stay non-activatable, as before D1.

    They project with no policy memory path, so deterministic validation
    reports the proposal unsupported and nothing is installed.
    """
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    memory = root / ".mneme" / "project_memory.json"
    memory.parent.mkdir()
    memory.write_text(json.dumps({
        "meta": {"name": "x", "description": "x"},
        "examples": [], "decisions": [],
        "items": [{
            "id": "legacy-anti-1", "type": "anti_pattern", "title": "postgres",
            "content": "no postgres in the service layer",
        }],
    }) + "\n", encoding="utf-8")
    migrate_memory_fixture(memory)
    before = memory.read_bytes()

    outcome = activate_protection("legacy-anti-1", memory, repo_root=root)

    assert outcome.result == "validation_failed"
    assert outcome.rule_installed is False
    assert memory.read_bytes() == before

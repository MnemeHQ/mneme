"""D1E1: canonical migration entry point and binding_authority plumbing.

ADR-030 §12 (migration entry point, lossless-or-refuse migration) and §9a
(binding_authority persistence) as amended by D1E0 and the D1E1 contract.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from mneme.cli import main
from mneme.decision_index_persistence import (
    DecisionIndexMigrationRefused,
    DecisionIndexMigrationRequired,
    DecisionIndexPersistenceError,
    apply_memory_migration,
    append_canonical_version_occurrence,
    load_decision_index_from_memory_file,
    load_persisted_decision_index,
    plan_memory_migration,
)
from tests.canonical_fixtures import canonical_document
from mneme.decision_projection import project_canonical_index
from mneme.memory_store import MemoryStore
from mneme.schemas import Rule

REPO_ROOT = Path(__file__).resolve().parent.parent
TS = "2026-01-01T00:00:00Z"


def _decision(decision_id: str, status: str = "active", **extra) -> dict:
    record = {
        "id": decision_id,
        "decision": f"{decision_id} statement",
        "rationale": "because",
        "scope": ["storage"],
        "constraints": [],
        "anti_patterns": [],
        "rules": [],
        "created_at": TS,
        "updated_at": TS,
        "status": status,
    }
    record.update(extra)
    return record


def _memory(path: Path, decisions: list[dict], items: list[dict] | None = None) -> Path:
    path.write_text(json.dumps({
        "meta": {"name": "d1e1", "description": "D1E1 fixture"},
        "items": items or [],
        "examples": [],
        "decisions": decisions,
    }, indent=2) + "\n", encoding="utf-8")
    return path


def _standard_memory(tmp_path: Path) -> Path:
    return _memory(
        tmp_path / "project_memory.json",
        [
            _decision(
                "D-ACTIVE",
                rules=[{"type": "FORBID_LITERAL", "value": "legacy_queue"}],
            ),
            _decision(
                "D-OLD",
                "superseded",
                rules=[{"type": "FORBID_LITERAL", "value": "retired_client"}],
            ),
            _decision("D-DEPRECATED", "deprecated"),
        ],
        items=[
            {"id": "legacy-rule-1", "type": "rule", "title": "No globals",
             "content": "avoid global state"},
            {"id": "legacy-anti-1", "type": "anti_pattern", "title": "God objects",
             "content": "split responsibilities"},
            {"id": "pref-1", "type": "preference", "title": "Tabs", "content": "no"},
        ],
    )


def _migrate(path: Path, *extra: str) -> int:
    return main(["decision-index", "migrate", "--memory", str(path), *extra])


# ── Preview ──────────────────────────────────────────────────────────────────


def test_preview_is_read_only_and_exits_zero(tmp_path, capsys):
    memory = _standard_memory(tmp_path)
    before = memory.read_bytes()

    assert _migrate(memory) == 0

    out = capsys.readouterr().out
    assert "Preview only; nothing was written" in out
    assert memory.read_bytes() == before


def test_preview_exposes_lifecycle_and_legacy_item_transitions(tmp_path, capsys):
    memory = _standard_memory(tmp_path)

    assert _migrate(memory) == 0

    out = capsys.readouterr().out
    assert "Native decisions:                3" in out
    assert "Non-active leaving Layer 1:      2" in out
    assert "D-OLD (superseded)" in out
    assert "D-DEPRECATED (deprecated)" in out
    assert "Legacy items becoming decisions: 2" in out
    assert "legacy-rule-1" in out and "legacy-anti-1" in out
    assert "pref-1" not in out
    assert "Active after migration:          3" in out
    assert "Migrated rule bindings:          2 (binding authority: legacy_unknown)" in out
    assert "new rule/anti_pattern items no longer synthesize decisions" in out


# ── Apply ────────────────────────────────────────────────────────────────────


def test_apply_writes_exactly_the_planned_migration(tmp_path):
    memory = _standard_memory(tmp_path)
    original = memory.read_bytes()

    plan = plan_memory_migration(memory)
    assert plan.state == "migrate"
    assert plan.source_bytes == original
    assert apply_memory_migration(plan) is True

    written = json.loads(memory.read_text(encoding="utf-8"))
    assert written == plan.document
    load_decision_index_from_memory_file(memory)
    store = MemoryStore(memory)
    store.load()
    assert {d.id for d in store.decisions()} == {
        "D-ACTIVE", "legacy-rule-1", "legacy-anti-1",
    }


def test_cli_apply_then_rerun_is_byte_identical_noop(tmp_path, capsys):
    memory = _standard_memory(tmp_path)

    assert _migrate(memory, "--apply") == 0
    migrated = memory.read_bytes()
    capsys.readouterr()

    assert _migrate(memory, "--apply") == 0
    assert memory.read_bytes() == migrated
    assert "Already migrated" in capsys.readouterr().out
    assert _migrate(memory) == 0
    assert memory.read_bytes() == migrated


def test_already_canonical_live_memory_is_a_noop(tmp_path):
    memory = tmp_path / "project_memory.json"
    shutil.copyfile(REPO_ROOT / ".mneme" / "project_memory.json", memory)
    before = memory.read_bytes()

    plan = plan_memory_migration(memory)

    assert plan.state == "already_canonical"
    assert apply_memory_migration(plan) is False
    assert memory.read_bytes() == before


def test_invalid_canonical_input_refuses_without_repair(tmp_path, capsys):
    memory = _standard_memory(tmp_path)
    assert _migrate(memory, "--apply") == 0
    raw = json.loads(memory.read_text(encoding="utf-8"))
    raw["decision_index"]["versions"][0]["statement"] = "tampered"
    memory.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    before = memory.read_bytes()
    capsys.readouterr()

    assert _migrate(memory, "--apply") == 2

    err = capsys.readouterr().err
    assert "not a repair path" in err
    assert "content_digest mismatch" in err
    assert memory.read_bytes() == before


def test_source_change_between_plan_and_write_refuses(tmp_path):
    memory = _standard_memory(tmp_path)
    plan = plan_memory_migration(memory)
    raw = json.loads(memory.read_text(encoding="utf-8"))
    raw["decisions"].append(_decision("D-LATE"))
    memory.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    changed = memory.read_bytes()

    with pytest.raises(DecisionIndexMigrationRefused, match="changed after it was read"):
        apply_memory_migration(plan)

    assert memory.read_bytes() == changed
    assert not list(tmp_path.glob("*.tmp"))


# ── Lossless or refuse ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "decision, expected",
    [
        pytest.param(
            _decision("D-1", test_evidence=[
                {"selector": "tests/t.py::a", "sha": "s", "unexpected": "x"},
            ]),
            "decision 'D-1' test_evidence[0] contains unsupported field 'unexpected'",
            id="test-evidence-extra-field",
        ),
        pytest.param(
            _decision("D-1", rules=[
                {"type": "FORBID_LITERAL", "value": "v", "severity": "high"},
            ]),
            "decision 'D-1' rules[0] contains unsupported field 'severity'",
            id="nested-rule-extra-field",
        ),
        pytest.param(
            _decision("EC-1", notes="owner: payments", source={
                "type": "eventcatalog", "path": "d/r.md", "sha256": "ab" * 32,
            }),
            "decision 'EC-1' source type 'eventcatalog' has no canonical provenance",
            id="eventcatalog-source",
        ),
        pytest.param(
            _decision("EC-1", notes="owner: payments"),
            "decision 'EC-1' contains unsupported field 'notes'",
            id="unknown-decision-field",
        ),
        pytest.param(
            _decision("ADR-777", source={
                "type": "adr", "path": "docs/adr/ADR-001-other.md", "sha256": "ab",
            }),
            "decision 'ADR-777' source path 'docs/adr/ADR-001-other.md' does not resolve",
            id="unresolvable-adr-source",
        ),
        pytest.param(
            _decision("D-1", test_evidence=["tests/t.py::a"]),
            "decision 'D-1' test_evidence[0] is not an object",
            id="non-object-test-evidence",
        ),
    ],
)
def test_lossy_legacy_state_refuses_byte_identical(tmp_path, capsys, decision, expected):
    memory = _memory(tmp_path / "project_memory.json", [decision])
    before = memory.read_bytes()

    assert _migrate(memory, "--apply") == 2

    err = capsys.readouterr().err
    assert "migration must be lossless" in err
    assert expected in err
    assert "Traceback" not in err
    assert memory.read_bytes() == before


def test_valid_adr_source_and_unknown_top_level_sections_migrate(tmp_path):
    memory = tmp_path / "project_memory.json"
    memory.write_text(json.dumps({
        "meta": {"name": "x", "description": "x"},
        "items": [],
        "examples": [],
        "activation": {"schema": "mneme.setup/v1", "state": "setup"},
        "future_section": {"kept": True},
        "decisions": [_decision("ADR-777", source={
            "type": "adr", "path": "docs/adr/ADR-777-thing.md", "sha256": "ab" * 32,
        })],
    }, indent=2) + "\n", encoding="utf-8")

    assert plan_memory_migration(memory).state == "migrate"
    raw = json.loads(json.dumps(plan_memory_migration(memory).document))
    assert raw["future_section"] == {"kept": True}
    evidence = raw["decision_index"]["versions"][0]["source_evidence"][0]
    assert evidence["source_type"] == "adr"
    assert evidence["source_revision"] == "ab" * 32


# ── binding_authority plumbing (§9a) ─────────────────────────────────────────


def test_migration_persists_legacy_unknown(tmp_path):
    plan = plan_memory_migration(_standard_memory(tmp_path))
    authorities = {
        row["binding_authority"] for row in plan.document["decision_index"]["rules"]
    }
    assert authorities == {"legacy_unknown"}


def test_rows_without_binding_authority_read_legacy_unknown_unrewritten(tmp_path):
    memory = tmp_path / "project_memory.json"
    shutil.copyfile(REPO_ROOT / ".mneme" / "project_memory.json", memory)
    before = memory.read_bytes()
    raw = json.loads(before.decode("utf-8"))
    assert raw["decision_index"]["rules"]
    assert all("binding_authority" not in row for row in raw["decision_index"]["rules"])

    index = load_decision_index_from_memory_file(memory)

    assert {rule.binding_authority for rule in index.rules} == {"legacy_unknown"}
    store = MemoryStore(memory)
    store.load()
    assert memory.read_bytes() == before


@pytest.mark.parametrize("value", ["adr", "", 1, None])
def test_invalid_binding_authority_fails_closed(tmp_path, value):
    section = canonical_document(json.loads(
        _standard_memory(tmp_path).read_text(encoding="utf-8")
    ))["decision_index"]
    section["rules"][0]["binding_authority"] = value

    with pytest.raises(DecisionIndexPersistenceError, match="invalid binding_authority"):
        load_persisted_decision_index(section)


def test_adr_import_bindings_persist_version_authority(tmp_path):
    from mneme.adr_import import apply_import, compile_for_import

    adr_dir = tmp_path / "adrs"
    adr_dir.mkdir()

    def write(literal: str) -> None:
        (adr_dir / "ADR-610.md").write_text(
            "---\nid: ADR-610\ntitle: t\nstatus: accepted\npriority: normal\n"
            f"date: 2026-04-15\nscope: \"storage\"\n---\n\n"
            f"## Constraints\n\n- FORBID_LITERAL: {literal}\n",
            encoding="utf-8",
        )

    memory = _memory(tmp_path / "project_memory.json", [])
    apply_memory_migration(plan_memory_migration(memory))
    write("alpha")
    apply_import(compile_for_import(adr_dir), memory)
    write("beta")
    apply_import(compile_for_import(adr_dir), memory, allow_update=True)

    rows = json.loads(memory.read_text(encoding="utf-8"))["decision_index"]["rules"]
    assert len(rows) == 2
    assert {row["binding_authority"] for row in rows} == {"version"}


def test_projection_ignores_binding_authority(tmp_path):
    document = canonical_document(json.loads(
        _standard_memory(tmp_path).read_text(encoding="utf-8")
    ))
    with_field = project_canonical_index(
        load_persisted_decision_index(document["decision_index"])
    )
    for row in document["decision_index"]["rules"]:
        row.pop("binding_authority")
    without_field = project_canonical_index(
        load_persisted_decision_index(document["decision_index"])
    )
    assert with_field == without_field


def test_mcp_rule_transport_never_emits_binding_authority(tmp_path):
    from mneme.decision_mcp import rule_to_transport

    section = canonical_document(json.loads(
        _standard_memory(tmp_path).read_text(encoding="utf-8")
    ))["decision_index"]
    rules = load_persisted_decision_index(section).rules
    assert rules
    for rule in rules:
        assert rule.binding_authority == "legacy_unknown"
        assert "binding_authority" not in rule_to_transport(rule)


def _occurrence_inputs() -> dict:
    return {
        "decision_id": "D-ACTIVE",
        "statement": "D-ACTIVE statement v2",
        "rationale": "because",
        "context_scope": ["storage"],
        "constraints": [],
        "anti_patterns": [],
        "rules": [Rule(type="FORBID_LITERAL", value="legacy_queue")],
        "created_at": TS,
        "updated_at": TS,
        "occurrence_source_identity": ["D-ACTIVE", "rev-2", "adr-import"],
        "source_evidence": [],
    }


def _evolved(tmp_path: Path) -> tuple[dict, str, str]:
    document = canonical_document(json.loads(
        _standard_memory(tmp_path).read_text(encoding="utf-8")
    ))
    (logical,) = [
        row for row in document["decision_index"]["decisions"]
        if row["decision_id"] == "D-ACTIVE"
    ]
    predecessor = logical["active_version_id"]
    evolved, version_id, created = append_canonical_version_occurrence(
        document, predecessor_version_id=predecessor, **_occurrence_inputs()
    )
    assert created
    return evolved, predecessor, version_id


def test_retry_of_pre_d1e1_occurrence_without_authority_is_noop(tmp_path):
    evolved, predecessor, version_id = _evolved(tmp_path)
    for row in evolved["decision_index"]["rules"]:
        if row["decision_version_id"] == version_id:
            row.pop("binding_authority")  # persisted before the field existed

    retried, same_id, created = append_canonical_version_occurrence(
        evolved, predecessor_version_id=predecessor, **_occurrence_inputs()
    )

    assert (same_id, created) == (version_id, False)
    assert retried["decision_index"] == evolved["decision_index"]


def test_explicit_legacy_unknown_is_not_interchangeable_with_version(tmp_path):
    evolved, predecessor, version_id = _evolved(tmp_path)
    for row in evolved["decision_index"]["rules"]:
        if row["decision_version_id"] == version_id:
            # The re-derived legacy rule keeps legacy_unknown (§9a collapse);
            # an explicitly persisted "version" must not match it.
            assert row["binding_authority"] == "legacy_unknown"
            row["binding_authority"] = "version"

    with pytest.raises(DecisionIndexPersistenceError, match="rule bindings differ"):
        append_canonical_version_occurrence(
            evolved, predecessor_version_id=predecessor, **_occurrence_inputs()
        )


# ── decision-mcp startup (§12) ───────────────────────────────────────────────


def _serve_recorder(monkeypatch) -> list:
    from mneme import decision_mcp

    calls: list = []
    monkeypatch.setattr(
        decision_mcp, "serve_stdio", lambda **kwargs: calls.append(kwargs)
    )
    return calls


def test_mcp_section_less_memory_reports_preview_first(tmp_path, monkeypatch, capsys):
    calls = _serve_recorder(monkeypatch)
    memory = _standard_memory(tmp_path)

    code = main(["decision-mcp", "--proposals", "", "--memory", str(memory)])

    err = capsys.readouterr().err
    assert code == 2
    assert calls == []
    assert "no authoritative decision_index section" in err
    preview = err.index(f"mneme decision-index migrate --memory {memory}\n")
    apply = err.index(f"mneme decision-index migrate --memory {memory} --apply")
    assert preview < apply
    assert "Traceback" not in err


def test_mcp_invalid_canonical_memory_does_not_suggest_migration(
    tmp_path, monkeypatch, capsys
):
    calls = _serve_recorder(monkeypatch)
    memory = _standard_memory(tmp_path)
    apply_memory_migration(plan_memory_migration(memory))
    raw = json.loads(memory.read_text(encoding="utf-8"))
    raw["decision_index"]["versions"][0]["statement"] = "tampered"
    memory.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

    code = main(["decision-mcp", "--proposals", "", "--memory", str(memory)])

    err = capsys.readouterr().err
    assert code == 2
    assert calls == []
    assert "is invalid" in err
    assert "migrate" not in err


def test_mcp_canonical_memory_starts_unchanged(tmp_path, monkeypatch):
    calls = _serve_recorder(monkeypatch)
    memory = _standard_memory(tmp_path)
    apply_memory_migration(plan_memory_migration(memory))

    code = main(["decision-mcp", "--proposals", "", "--memory", str(memory)])

    assert code == 0
    assert len(calls) == 1
    assert calls[0]["memory_path"] == str(memory)


def test_loader_raises_migration_required_for_section_less_memory(tmp_path):
    with pytest.raises(DecisionIndexMigrationRequired):
        load_decision_index_from_memory_file(_standard_memory(tmp_path))


# ── Single transition: canonical writers never migrate (ADR-030 §1) ──────────


def _section_less_lossy(path: Path) -> Path:
    """Section-less memory whose EventCatalog row cannot migrate losslessly."""
    return _memory(path, [{
        "id": "EC-1",
        "decision": "Payments own refunds",
        "source": {"type": "eventcatalog", "path": "d/r.md", "sha256": "ab" * 32},
        "notes": "owner: payments",
    }])


@pytest.mark.parametrize("lossy", [False, True], ids=["clean", "lossy-eventcatalog"])
def test_acceptance_refuses_section_less_memory_before_proposal_transition(
    tmp_path, lossy
):
    from mneme.decision_authority import DecisionAuthorityService
    from mneme.decision_proposal_store import JsonFileDecisionProposalStore
    from tests.test_decision_authority import _propose

    proposals = tmp_path / "proposals.json"
    proposal = _propose(JsonFileDecisionProposalStore(proposals))
    memory = (
        _section_less_lossy(tmp_path / "project_memory.json")
        if lossy
        else _standard_memory(tmp_path)
    )
    memory_before, store_before = memory.read_bytes(), proposals.read_bytes()

    with pytest.raises(DecisionIndexMigrationRequired):
        DecisionAuthorityService(
            JsonFileDecisionProposalStore(proposals), memory
        ).accept(proposal.proposal_id)

    assert memory.read_bytes() == memory_before
    assert proposals.read_bytes() == store_before


def test_cli_accept_on_section_less_memory_reports_preview_first(tmp_path, capsys):
    from mneme.decision_proposal_store import JsonFileDecisionProposalStore
    from tests.test_decision_authority import _propose

    proposals = tmp_path / "proposals.json"
    proposal = _propose(JsonFileDecisionProposalStore(proposals))
    memory = _standard_memory(tmp_path)
    store_before = proposals.read_bytes()

    code = main([
        "decision", "accept", proposal.proposal_id,
        "--proposals", str(proposals), "--memory", str(memory),
    ])

    err = capsys.readouterr().err
    assert code == 2
    assert "no authoritative decision_index section" in err
    assert err.index("migrate --memory") < err.index("--apply")
    assert "Traceback" not in err
    assert proposals.read_bytes() == store_before


def test_cli_adr_import_on_section_less_memory_reports_preview_first(
    tmp_path, capsys
):
    memory = _section_less_lossy(tmp_path / "project_memory.json")
    before = memory.read_bytes()

    code = main([
        "adr", "import", str(REPO_ROOT / "tests" / "fixtures" / "adrs_import_basic"),
        "--memory", str(memory), "--apply",
    ])

    err = capsys.readouterr().err
    assert code == 2
    assert "no authoritative decision_index section" in err
    assert err.index("migrate --memory") < err.index("--apply")
    assert memory.read_bytes() == before


def _primitive_calls() -> list:
    from mneme import decision_index_persistence as p

    return [
        pytest.param(lambda d: p.append_initial_canonical_decision(
            d, decision_id="D-NEW", statement="s", rationale="r",
            context_scope=["x"], lifecycle_status="active", created_at=TS,
            updated_at=TS, occurrence_source_identity=["cli-add", "D-NEW"],
            source_evidence=[],
        ), id="append-initial"),
        pytest.param(lambda d: p.append_canonical_version_occurrence(
            d, predecessor_version_id="dver-" + "0" * 32, **_occurrence_inputs()
        ), id="append-version"),
        pytest.param(lambda d: p.apply_canonical_supersession(
            d, superseding_decision_id="D-ACTIVE",
            target_decision_ids=["D-OLD"], updated_at=TS,
        ), id="supersede"),
        pytest.param(lambda d: p.rebind_legacy_initial_occurrence(
            d, decision_id="D-ACTIVE", occurrence_source_identity=["x"],
            source_evidence=[],
        ), id="rebind"),
        pytest.param(p.rebuild_compatibility_snapshot, id="rebuild-snapshot"),
    ]


@pytest.mark.parametrize("call", _primitive_calls())
def test_canonical_primitives_require_canonical_input(tmp_path, call):
    document = json.loads(_standard_memory(tmp_path).read_text(encoding="utf-8"))
    original = json.loads(json.dumps(document))

    with pytest.raises(DecisionIndexMigrationRequired):
        call(document)

    assert document == original


def test_migration_transformation_is_private_to_the_migration_command():
    """Source boundary: only plan_memory_migration may migrate (ADR-030 §1)."""
    import ast

    from mneme import decision_index_persistence as persistence

    assert "migrate_memory_document" not in persistence.__all__
    assert "_migrate_memory_document" not in persistence.__all__
    assert not hasattr(persistence, "migrate_memory_document")

    names = {"migrate_memory_document", "_migrate_memory_document"}
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "mneme").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel == "mneme/decision_index_persistence.py":
            for func in ast.walk(tree):
                if not isinstance(func, ast.FunctionDef):
                    continue
                for node in ast.walk(func):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id in names
                        and func.name != "plan_memory_migration"
                    ):
                        offenders.append(f"{rel}:{func.name}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in names:
                offenders.append(f"{rel}:{node.lineno}")
            elif isinstance(node, ast.Attribute) and node.attr in names:
                offenders.append(f"{rel}:{node.lineno}")
            elif isinstance(node, ast.alias) and node.name in names:
                offenders.append(f"{rel}:import")
    assert offenders == []

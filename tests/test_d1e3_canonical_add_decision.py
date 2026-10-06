"""D1E3: canonical ``mneme add_decision`` writer (ADR-030 §4, §15).

On canonical memory, ``add_decision`` is an explicit human authority path
with occurrence identity ``["cli-add", decision_id]``. It creates only a
first occurrence, with the no-predecessor sentinel and honest ``runtime``
provenance. An exact retry is a byte-identical no-op; the same id with any
other content, or held by another authority, fails closed. Section-less
memory keeps the legacy write until D1E5 (pinned in the containment suite).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.cli import main
from mneme.decision_add import (
    AddDecisionError,
    add_canonical_decision,
    cli_add_occurrence_identity,
)
from mneme.decision_index_persistence import (
    DecisionIndexMigrationRequired,
    NO_PREDECESSOR,
    content_digest_of,
    load_decision_index_from_memory_file,
    version_id_of,
)
from mneme.memory_store import MemoryStore
from mneme.protection import _install_rule
from mneme.schemas import Rule
from mneme.setup_state import ConcurrentModificationError
from tests.canonical_fixtures import migrate_memory_fixture

BASE_TS = "2026-01-01T00:00:00Z"

EXISTING = {
    "id": "d_existing",
    "decision": "No postgres in the service layer",
    "rationale": "",
    "scope": ["storage"],
    "constraints": [],
    "anti_patterns": ["postgres"],
    "created_at": BASE_TS,
    "updated_at": BASE_TS,
}

ADD_ARGS = [
    "--id", "config-format",
    "--decision", "Use JSON for configuration files",
    "--rationale", "One parser",
    "--scope", "config",
    "--constraint", "Use JSON only",
    "--anti-pattern", "Do not use YAML",
]


def _canonical_memory(tmp_path: Path, decisions: list[dict] | None = None) -> Path:
    memory = tmp_path / ".mneme" / "project_memory.json"
    memory.parent.mkdir(parents=True)
    document = {
        "meta": {"name": "d1e3", "description": "canonical add_decision"},
        "items": [{
            "id": "item-1", "type": "context", "title": "kept", "content": "kept",
        }],
        "examples": [],
        "decisions": list(decisions if decisions is not None else [EXISTING]),
    }
    memory.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    assert migrate_memory_fixture(memory) is True
    return memory


def _add(memory: Path, *extra: str) -> int:
    return main(["add_decision", "--memory", str(memory), *ADD_ARGS, *extra])


def _record(memory: Path, decision_id: str) -> tuple[dict, list[dict], list[dict]]:
    section = json.loads(memory.read_text(encoding="utf-8"))["decision_index"]
    (logical,) = [r for r in section["decisions"] if r["decision_id"] == decision_id]
    versions = [v for v in section["versions"] if v["decision_id"] == decision_id]
    rules = [r for r in section["rules"] if r["decision_id"] == decision_id]
    return logical, versions, rules


# ── Identity ────────────────────────────────────────────────────────────────


def test_cli_add_identity_golden_vector():
    assert cli_add_occurrence_identity("config-format") == ["cli-add", "config-format"]
    digest = content_digest_of(
        "Use JSON for configuration files",
        "One parser",
        ["config"],
        ["Use JSON only"],
        ["Do not use YAML"],
    )
    assert digest == (
        "7e20df484d430bd7d06593e191482b31"
        "8c4c469c3b62c0564fea50bb9025ceb9"
    )
    # No timestamp participates; the first occurrence keys on the sentinel.
    assert version_id_of(
        "config-format",
        digest,
        ["cli-add", "config-format"],
        NO_PREDECESSOR,
    ) == "dver-0a211fb6cbc8fa65a6c7d27436ea13e3"


# ── Canonical first occurrence ──────────────────────────────────────────────


def test_add_creates_canonical_first_occurrence(tmp_path, capsys):
    memory = _canonical_memory(tmp_path)
    before = json.loads(memory.read_text(encoding="utf-8"))
    existing_before = _record(memory, "d_existing")

    assert _add(memory) == 0
    assert "Added decision [config-format]" in capsys.readouterr().out

    logical, (version,), rules = _record(memory, "config-format")
    assert version["version_id"] == "dver-0a211fb6cbc8fa65a6c7d27436ea13e3"
    assert logical["active_version_id"] == version["version_id"]
    assert logical["lifecycle_status"] == "active"
    assert logical["relationships"] == []
    assert logical["test_evidence"] == []
    assert version["occurrence_source_identity"] == ["cli-add", "config-format"]
    assert version["supersedes_version_id"] is None
    assert version["revision"] == "1"
    assert version["statement"] == "Use JSON for configuration files"
    assert version["rationale"] == "One parser"
    assert version["context_scope"] == ["config"]
    assert version["constraints"] == ["Use JSON only"]
    assert version["anti_patterns"] == ["Do not use YAML"]
    # Honest runtime provenance: never ADR or proposal origin.
    assert version["source_evidence"] == [{
        "source_type": "runtime",
        "source_locator": "",
        "source_revision": "",
        "observed_at": "",
        "verification_status": "",
    }]
    assert version["created_at"] and version["created_at"] == logical["updated_at"]
    assert rules == []

    after = json.loads(memory.read_text(encoding="utf-8"))
    assert _record(memory, "d_existing") == existing_before
    for key in ("meta", "items", "examples"):
        assert after[key] == before[key]
    load_decision_index_from_memory_file(memory)  # snapshot parity holds
    (snapshot_row,) = [d for d in after["decisions"] if d["id"] == "config-format"]
    assert "source" not in snapshot_row
    ids = [d.id for d in MemoryStore(memory).load().decisions]
    assert ids == ["d_existing", "config-format"]


def test_add_writes_canonical_serialization(tmp_path):
    memory = _canonical_memory(tmp_path)
    assert _add(memory) == 0
    text = memory.read_text(encoding="utf-8")
    assert text == json.dumps(json.loads(text), indent=2) + "\n"


# ── Retry and collision ─────────────────────────────────────────────────────


def test_exact_retry_is_byte_identical_noop(tmp_path, capsys):
    memory = _canonical_memory(tmp_path)
    assert _add(memory) == 0
    before = memory.read_bytes()
    capsys.readouterr()

    assert _add(memory) == 0

    out = capsys.readouterr().out
    assert "already exists with identical content" in out
    assert "Added decision" not in out
    assert memory.read_bytes() == before


def test_retry_after_canonical_protection_is_still_noop(tmp_path):
    # Rules are Tier 2 bindings, outside the occurrence key (ADR-030 §6).
    memory = _canonical_memory(tmp_path)
    assert _add(memory) == 0
    assert _install_rule(
        memory, "config-format", Rule(type="FORBID_LITERAL", value="yaml")
    ) is True
    before = memory.read_bytes()

    assert _add(memory) == 0
    assert memory.read_bytes() == before


@pytest.mark.parametrize("changed", [
    ["--decision", "Use TOML for configuration files"],
    ["--rationale", "Different"],
    ["--scope", "storage"],
    ["--constraint", "Also JSON5"],
    ["--anti-pattern", "Do not use INI"],
])
def test_same_id_different_content_fails_closed(tmp_path, capsys, changed):
    memory = _canonical_memory(tmp_path)
    assert _add(memory) == 0
    before = memory.read_bytes()
    capsys.readouterr()

    args = list(ADD_ARGS)
    flag, value = changed
    if flag in ("--decision", "--rationale"):
        args[args.index(flag) + 1] = value
    else:
        args += [flag, value]
    code = main(["add_decision", "--memory", str(memory), *args])

    captured = capsys.readouterr()
    assert code == 2
    assert "config-format" in captured.err
    assert "not an edit" in captured.err
    assert "Added decision" not in captured.out
    assert memory.read_bytes() == before


def test_same_id_held_by_another_authority_fails_closed(tmp_path, capsys):
    # Identical content from a migrated legacy decision is a different
    # occurrence (legacy-decisions identity), never a cli-add retry.
    memory = _canonical_memory(tmp_path)
    before = memory.read_bytes()

    code = main([
        "add_decision", "--memory", str(memory),
        "--id", "d_existing",
        "--decision", EXISTING["decision"],
        "--scope", "storage",
        "--anti-pattern", "postgres",
    ])

    assert code == 2
    assert "d_existing" in capsys.readouterr().err
    assert memory.read_bytes() == before


def test_reserved_proposal_namespace_is_refused(tmp_path, capsys):
    memory = _canonical_memory(tmp_path)
    before = memory.read_bytes()

    code = main([
        "add_decision", "--memory", str(memory),
        "--id", "dprop-0123", "--decision", "Something",
    ])

    assert code == 2
    assert "dprop-" in capsys.readouterr().err
    assert memory.read_bytes() == before


# ── Verify before mutate; guarded write ─────────────────────────────────────


def test_divergent_snapshot_is_refused_not_repaired(tmp_path, capsys):
    memory = _canonical_memory(tmp_path)
    raw = json.loads(memory.read_text(encoding="utf-8"))
    raw["decisions"][0]["decision"] = "hand-edited"
    memory.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    before = memory.read_bytes()

    code = _add(memory)

    captured = capsys.readouterr()
    assert code == 2
    assert "diverges" in captured.err
    assert "Added decision" not in captured.out
    assert memory.read_bytes() == before


def test_invalid_canonical_section_is_refused(tmp_path, capsys):
    memory = _canonical_memory(tmp_path)
    raw = json.loads(memory.read_text(encoding="utf-8"))
    raw["decision_index"]["schema"] = "mneme.decision-index/v0"
    memory.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    before = memory.read_bytes()

    assert _add(memory) == 2
    assert "schema" in capsys.readouterr().err
    assert memory.read_bytes() == before


def test_changed_file_after_read_refuses_write(tmp_path):
    memory = _canonical_memory(tmp_path)
    source_bytes = memory.read_bytes()
    raw = json.loads(source_bytes.decode("utf-8"))
    # A concurrent writer changes the file after it was read.
    changed = source_bytes + b"\n"
    memory.write_bytes(changed)

    with pytest.raises(AddDecisionError) as excinfo:
        add_canonical_decision(
            memory,
            raw,
            source_bytes,
            decision_id="config-format",
            statement="Use JSON for configuration files",
            rationale="",
            scope=["config"],
            constraints=[],
            anti_patterns=[],
            now=BASE_TS,
        )
    assert isinstance(excinfo.value.__cause__, ConcurrentModificationError)
    assert memory.read_bytes() == changed


def test_writer_refuses_section_less_document(tmp_path):
    # The canonical writer never migrates (ADR-030 §1); the CLI routes
    # section-less memory to the legacy path before reaching it.
    memory = tmp_path / "project_memory.json"
    memory.write_text('{"decisions": []}\n', encoding="utf-8")
    with pytest.raises(AddDecisionError) as excinfo:
        add_canonical_decision(
            memory,
            {"decisions": []},
            memory.read_bytes(),
            decision_id="x",
            statement="y",
            rationale="",
            scope=[],
            constraints=[],
            anti_patterns=[],
            now=BASE_TS,
        )
    assert isinstance(excinfo.value.__cause__, DecisionIndexMigrationRequired)
    assert memory.read_text(encoding="utf-8") == '{"decisions": []}\n'

"""D1E4: EventCatalog canonical apply is retired for D1 (ADR-030 §12, §15).

The four-case contract:

    canonical + preview       -> supported, read-only
    canonical + --apply       -> explicit D1 retirement refusal, no preview/write
    section-less + preview    -> unchanged
    section-less + --apply    -> unchanged legacy apply

No canonical EventCatalog writer, provenance model, or collision model exists
in D1. A future EventCatalog canonical provenance contract needs a separate
decision.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import mneme.cli as cli
from mneme.cli import main
from mneme.integrations.eventcatalog import apply_import, compile_for_import
from mneme.integrations.eventcatalog.importer import (
    CANONICAL_APPLY_RETIRED,
    detect_collisions,
    format_preview,
)
from mneme.memory_store import MemoryStore
from tests.canonical_fixtures import migrate_memory_fixture

FIXTURES = Path(__file__).parent / "fixtures" / "eventcatalog_import"

BASE_TS = "2026-01-01T00:00:00Z"

# Same id as the fixture's active ADR, so the preview reports a collision.
COLLIDING = {
    "id": "ec-choose-kafka",
    "decision": "Kafka is the event backbone",
    "constraints": [],
    "anti_patterns": [],
    "created_at": BASE_TS,
    "updated_at": BASE_TS,
}

UPDATE_HINT = "--update-existing"
PREVIEW_HEADER = "EventCatalog import preview"


def _memory(tmp_path: Path, *, canonical: bool, decisions=None) -> Path:
    path = tmp_path / ".mneme" / "project_memory.json"
    path.parent.mkdir(parents=True)
    document = {
        "meta": {"name": "d1e4", "description": "EventCatalog retirement"},
        "items": [],
        "examples": [],
        "decisions": list(decisions or []),
    }
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    if canonical:
        assert migrate_memory_fixture(path) is True
    return path


def _run(memory: Path, *extra: str, index: Path | None = None) -> int:
    return main([
        "eventcatalog", "import",
        "--index", str(index or FIXTURES / "index.json"),
        "--catalog-root", str(FIXTURES),
        "--memory", str(memory),
        *extra,
    ])


# ── canonical + preview: supported, read-only ───────────────────────────────


def test_canonical_preview_is_read_only_and_states_retirement(tmp_path, capsys):
    memory = _memory(tmp_path, canonical=True, decisions=[COLLIDING])
    before = memory.read_bytes()

    code = _run(memory)

    out = capsys.readouterr().out
    assert code == 1  # diagnostics present, as before D1E4
    assert PREVIEW_HEADER in out
    assert "[ec-choose-kafka] status=active" in out
    assert "ec-choose-kafka already exists" in out  # collision still reported
    assert UPDATE_HINT not in out  # an impossible action is never suggested
    assert CANONICAL_APPLY_RETIRED in out
    assert memory.read_bytes() == before


def test_canonical_retirement_never_suggests_a_downgrade():
    assert "retired for canonical Decision Index memory in D1" in CANONICAL_APPLY_RETIRED
    assert "Preview remains available" in CANONICAL_APPLY_RETIRED
    for wording in ("remove the decision_index", "downgrade", "go back", "revert"):
        assert wording not in CANONICAL_APPLY_RETIRED


# ── canonical + --apply: explicit retirement, no preview, no write ──────────


@pytest.mark.parametrize("extra", [[], ["--update-existing"]])
def test_canonical_apply_is_refused_before_preview(tmp_path, capsys, extra):
    memory = _memory(tmp_path, canonical=True, decisions=[COLLIDING])
    before = memory.read_bytes()

    code = _run(memory, "--apply", *extra)

    captured = capsys.readouterr()
    assert code == 2
    assert CANONICAL_APPLY_RETIRED in captured.err
    assert "Nothing was written" in captured.err
    assert captured.out == ""  # no preview output
    assert memory.read_bytes() == before
    MemoryStore(memory).load()


def test_canonical_apply_refuses_before_compilation(tmp_path, capsys, monkeypatch):
    memory = _memory(tmp_path, canonical=True)

    def _must_not_compile(*args, **kwargs):
        raise AssertionError("EventCatalog was compiled for a retired apply")

    monkeypatch.setattr(cli, "ec_compile_for_import", _must_not_compile)

    assert _run(memory, "--apply") == 2
    assert CANONICAL_APPLY_RETIRED in capsys.readouterr().err


def test_canonical_apply_keeps_bad_path_errors_first(tmp_path, capsys):
    memory = _memory(tmp_path, canonical=True)

    code = _run(memory, "--apply", index=tmp_path / "missing-index.json")

    err = capsys.readouterr().err
    assert code == 2
    assert "index file" in err and "does not exist" in err
    assert CANONICAL_APPLY_RETIRED not in err


def test_apply_import_refuses_canonical_memory_for_library_callers(tmp_path):
    memory = _memory(tmp_path, canonical=True)
    before = memory.read_bytes()
    report = compile_for_import(FIXTURES / "index.json", FIXTURES)

    for allow_update in (False, True):
        with pytest.raises(RuntimeError) as excinfo:
            apply_import(
                report,
                target_path=memory,
                catalog_root=FIXTURES,
                allow_update=allow_update,
            )
        assert CANONICAL_APPLY_RETIRED in str(excinfo.value)
        assert "Nothing was written" in str(excinfo.value)
    assert memory.read_bytes() == before
    MemoryStore(memory).load()


# ── section-less + preview: unchanged ───────────────────────────────────────


def test_sectionless_preview_is_unchanged(tmp_path, capsys):
    memory = _memory(tmp_path, canonical=False, decisions=[COLLIDING])
    before = memory.read_bytes()
    raw = json.loads(before)
    report = compile_for_import(FIXTURES / "index.json", FIXTURES)

    code = _run(memory)

    out = capsys.readouterr().out
    assert code == 1
    assert out == format_preview(report, detect_collisions(report.nodes, raw)) + "\n"
    assert UPDATE_HINT in out  # the legacy overwrite path still exists here
    assert CANONICAL_APPLY_RETIRED not in out
    assert memory.read_bytes() == before


# ── section-less + --apply: unchanged legacy apply ──────────────────────────


def test_sectionless_apply_is_unchanged_legacy_write(tmp_path, capsys):
    memory = _memory(tmp_path, canonical=False)

    code = _run(memory, "--apply")

    captured = capsys.readouterr()
    assert code == 0
    assert PREVIEW_HEADER in captured.out
    assert "Wrote 1 decisions" in captured.out
    raw = json.loads(memory.read_text(encoding="utf-8"))
    assert "decision_index" not in raw
    (row,) = raw["decisions"]
    assert row["id"] == "ec-choose-kafka"
    assert row["source"]["type"] == "eventcatalog"


def test_sectionless_apply_still_refuses_collision_without_update(tmp_path, capsys):
    memory = _memory(tmp_path, canonical=False, decisions=[COLLIDING])
    before = memory.read_bytes()

    code = _run(memory, "--apply")

    assert code == 2
    assert "same-id collision" in capsys.readouterr().err
    assert memory.read_bytes() == before


# ── formatter ───────────────────────────────────────────────────────────────


def test_format_preview_default_is_the_legacy_preview():
    report = compile_for_import(FIXTURES / "index.json", FIXTURES)
    collisions = detect_collisions(report.nodes, {"decisions": [COLLIDING]})
    assert format_preview(report, collisions) == format_preview(
        report, collisions, canonical=False
    )

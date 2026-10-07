"""DG1A characterization: how 0.10.0 treats data it does not understand.

ADR-031 §8 rests on these facts about the shipped ``mneme.decision-index/v1``
loader and canonical writers. They pin current behavior only; nothing here
introduces DG1 semantics.

- Unknown keys at the document root, the ``decision_index`` root, and on
  decision / version / rule rows are accepted and silently ignored on load,
  and preserved by a canonical writer on rewrite.
- An unknown relationship type, an unknown lifecycle value, and any schema
  other than v1 are rejected at load.

If one of these changes, ADR-031 §8 (persisted DG1 data requires schema v2)
must be re-reviewed.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from mneme.decision_add import add_canonical_decision
from mneme.decision_index_persistence import (
    DECISION_INDEX_SCHEMA,
    DecisionIndexPersistenceError,
    load_decision_index_from_memory_file,
)
from tests.canonical_fixtures import canonical_document

FIXTURE = Path(__file__).parent / "fixtures" / "d1_parity" / "pre_d1_live_project_memory.json"


@pytest.fixture()
def base() -> dict[str, Any]:
    document = canonical_document(json.loads(FIXTURE.read_text(encoding="utf-8")))
    index = document["decision_index"]
    assert index["schema"] == DECISION_INDEX_SCHEMA == "mneme.decision-index/v1"
    assert index["decisions"] and index["versions"] and index["rules"]
    return document


def _write(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "project_memory.json"
    path.write_bytes(json.dumps(document).encode("utf-8"))
    return path


def _with(base: dict[str, Any], mutate: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    document = copy.deepcopy(base)
    mutate(document)
    return document


_IGNORED_UNKNOWN_KEYS: dict[str, Callable[[dict[str, Any]], None]] = {
    "document_root": lambda d: d.__setitem__("dg1_probe", {}),
    "decision_index_root": lambda d: d["decision_index"].__setitem__("waivers", [{"id": "W-1"}]),
    "decision_row": lambda d: d["decision_index"]["decisions"][0].__setitem__(
        "governs", {"paths": ["src/**"]}
    ),
    "version_row": lambda d: d["decision_index"]["versions"][0].__setitem__("priority", "high"),
    "rule_row": lambda d: d["decision_index"]["rules"][0].__setitem__("dg1_probe", 1),
}


@pytest.mark.parametrize("level", sorted(_IGNORED_UNKNOWN_KEYS))
def test_v1_loader_silently_ignores_unknown_keys(
    base: dict[str, Any], tmp_path: Path, level: str
) -> None:
    (tmp_path / "baseline").mkdir()
    (tmp_path / "probed").mkdir()
    baseline = load_decision_index_from_memory_file(_write(tmp_path / "baseline", base))
    probed = load_decision_index_from_memory_file(
        _write(tmp_path / "probed", _with(base, _IGNORED_UNKNOWN_KEYS[level]))
    )
    assert probed == baseline


def test_v1_canonical_writer_preserves_unknown_keys(
    base: dict[str, Any], tmp_path: Path
) -> None:
    document = copy.deepcopy(base)
    for mutate in _IGNORED_UNKNOWN_KEYS.values():
        mutate(document)
    data = json.dumps(document).encode("utf-8")
    path = tmp_path / "project_memory.json"
    path.write_bytes(data)

    assert add_canonical_decision(
        path,
        json.loads(data),
        data,
        decision_id="dg1a-probe-001",
        statement="probe",
        rationale="probe",
        scope=[],
        constraints=[],
        anti_patterns=[],
        now="2026-10-07T00:00:00Z",
    )

    after = json.loads(path.read_bytes())
    index = after["decision_index"]
    assert after["dg1_probe"] == {}
    assert index["waivers"] == [{"id": "W-1"}]
    assert index["decisions"][0]["governs"] == {"paths": ["src/**"]}
    assert index["versions"][0]["priority"] == "high"
    assert index["rules"][0]["dg1_probe"] == 1
    assert any(row["decision_id"] == "dg1a-probe-001" for row in index["decisions"])


_REJECTED: dict[str, tuple[Callable[[dict[str, Any]], None], str]] = {
    "relationship_type": (
        lambda d: d["decision_index"]["decisions"][0]["relationships"].append({
            "type": "waives",
            "target_decision_id": d["decision_index"]["decisions"][1]["decision_id"],
        }),
        "unsupported relationship type 'waives'",
    ),
    "lifecycle_value": (
        lambda d: d["decision_index"]["decisions"][0].__setitem__("lifecycle_status", "waived"),
        "invalid lifecycle_status 'waived'",
    ),
    "schema_version": (
        lambda d: d["decision_index"].__setitem__("schema", "mneme.decision-index/v2"),
        "decision_index schema must be",
    ),
}


@pytest.mark.parametrize("case", sorted(_REJECTED))
def test_v1_loader_rejects_unknown_semantics(
    base: dict[str, Any], tmp_path: Path, case: str
) -> None:
    mutate, message = _REJECTED[case]
    path = _write(tmp_path, _with(base, mutate))
    with pytest.raises(DecisionIndexPersistenceError, match=message):
        load_decision_index_from_memory_file(path)

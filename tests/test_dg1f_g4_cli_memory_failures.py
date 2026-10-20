"""DG1F G4: the CLI never reports success on unusable canonical memory (S2).

The blocking-semantics matrix (`docs/plans/2026-10-14-dg1f-adversarial-blocking-semantics-matrix.md`)
marks CLI S2 (invalid/unreadable canonical memory) as an operational-error
surface. These tests pin that a corrupt canonical document produces an
operational failure and **never** a PASS verdict, so a broken authority file
cannot be mistaken for a clean governance check.

Observed behavior is pinned as-is; this is coverage, not a behavior change.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.cli import main
from mneme.decision_index_persistence import DecisionIndexPersistenceError


def _write_memory(tmp_path: Path, document: object) -> Path:
    memory = tmp_path / ".mneme" / "project_memory.json"
    memory.parent.mkdir(parents=True, exist_ok=True)
    memory.write_text(json.dumps(document), encoding="utf-8")
    return memory


def _probe(tmp_path: Path) -> Path:
    probe = tmp_path / "input.txt"
    probe.write_text("x = 1\n", encoding="utf-8")
    return probe


def _check(memory: Path, probe: Path) -> int:
    return main([
        "check", "--memory", str(memory), "--input", str(probe),
        "--query", "x", "--mode", "strict",
    ])


def test_corrupt_canonical_memory_is_an_operational_error_not_pass(tmp_path: Path) -> None:
    # A canonical decision row missing required fields is unusable authority.
    memory = _write_memory(tmp_path, {
        "meta": {"name": "g4", "description": "corrupt canonical"},
        "decision_index": {
            "schema": "mneme.decision-index/v2",
            "semantic_features": [],
            "decisions": [{"decision_id": "D1"}],  # no decision_class/lifecycle
            "versions": [],
            "rules": [],
        },
        "decisions": [],
    })
    with pytest.raises(DecisionIndexPersistenceError):
        _check(memory, _probe(tmp_path))


def test_malformed_json_memory_is_an_operational_error_not_pass(tmp_path: Path) -> None:
    memory = tmp_path / ".mneme" / "project_memory.json"
    memory.parent.mkdir(parents=True, exist_ok=True)
    memory.write_text("{ this is not valid json", encoding="utf-8")
    with pytest.raises(ValueError):
        _check(memory, _probe(tmp_path))

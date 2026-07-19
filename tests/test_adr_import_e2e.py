# tests/test_adr_import_e2e.py
"""End-to-end: import ADRs, then run them through MemoryStore + retriever +
enforcer to confirm rules flow through the existing pipeline."""
from __future__ import annotations

import json
from pathlib import Path

from mneme.adr_import import apply_import, compile_for_import
from mneme.cli import main as cli_main
from mneme.decision_retriever import DecisionRetriever
from mneme.enforcer import Severity, check_prompt
from mneme.memory_store import MemoryStore

FIXTURES = Path(__file__).parent / "fixtures"


def _seed(target: Path) -> None:
    target.write_text(json.dumps({
        "meta": {"name": "e2e", "description": "e2e", "version": "1.0.0", "owner": "e2e", "created": "2026-01-01"},
        "items": [], "examples": [], "decisions": [],
    }), encoding="utf-8")


def test_imported_forbid_dependency_triggers_enforcer_warn(tmp_path):
    target = tmp_path / "project_memory.json"
    _seed(target)

    report = compile_for_import(FIXTURES / "adrs_import_basic")
    apply_import(report, target_path=target)

    store = MemoryStore(target)
    store.load()
    retriever = DecisionRetriever(store.decisions())
    scored = retriever.retrieve("can we add mongodb for the analytics pipeline?")

    result = check_prompt("Use mongodb for analytics", scored, top=3)
    assert result.verdict == Severity.WARN
    # The triggering rule is the imported "no mongodb" constraint
    assert any(v.rule == "no mongodb" for v in result.violations)


def test_mneme_check_warn_mode_against_imported_memory(tmp_path):
    """Drive the existing `mneme check --mode warn` CLI against an
    imported memory file. Proves zero changes were needed in the check
    code path."""
    target = tmp_path / "project_memory.json"
    _seed(target)
    report = compile_for_import(FIXTURES / "adrs_import_basic")
    apply_import(report, target_path=target)

    input_file = tmp_path / "input.txt"
    input_file.write_text("Switch the storage layer to mongodb.", encoding="utf-8")

    rc = cli_main([
        "check",
        "--memory", str(target),
        "--input", str(input_file),
        "--query", "storage layer change",
        "--mode", "warn",
    ])
    assert rc == 0  # warn mode -> always exit 0

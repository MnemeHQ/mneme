"""Tests for `mneme cursor generate` command and cursor_generator module."""
import json
from pathlib import Path

import pytest

from mneme.cli import main
from mneme.cursor_generator import generate_mdc
from mneme.decision_retriever import DecisionRetriever, ScoredDecision
from mneme.schemas import Decision


# ── fixtures ─────────────────────────────────────────────────────────────────

def _seed_memory(tmp_path: Path) -> Path:
    mem = tmp_path / "project_memory.json"
    mem.write_text(json.dumps({
        "meta": {"name": "t", "description": "t"},
        "items": [],
        "examples": [],
        "decisions": [
            {
                "id": "storage_json",
                "decision": "Use JSON storage only",
                "rationale": "local-first, avoid infra complexity",
                "scope": ["storage", "backend"],
                "constraints": ["no postgres", "no ORM"],
                "anti_patterns": ["introduce ORM", "add migration layer"],
                "created_at": "2026-04-24T00:00:00Z",
                "updated_at": "2026-04-24T00:00:00Z",
            },
            {
                "id": "retrieval_deterministic",
                "decision": "Keep retrieval deterministic",
                "rationale": "Testability requires reproducible results",
                "scope": ["retrieval", "scoring"],
                "constraints": ["no embeddings", "no ML"],
                "anti_patterns": ["add vector db", "use cosine similarity"],
                "created_at": "2026-04-24T00:00:00Z",
                "updated_at": "2026-04-24T00:00:00Z",
            },
            {
                "id": "cli_argparse",
                "decision": "Use argparse for CLI",
                "rationale": "stdlib only, no extra deps",
                "scope": ["cli"],
                "constraints": ["no click", "no typer"],
                "anti_patterns": ["add click dependency"],
                "created_at": "2026-04-24T00:00:00Z",
                "updated_at": "2026-04-24T00:00:00Z",
            },
        ],
    }))
    return mem


def _scored_decisions() -> list[ScoredDecision]:
    decisions = [
        Decision(
            id="storage_json",
            decision="Use JSON storage only",
            rationale="local-first",
            scope=["storage"],
            constraints=["no postgres"],
            anti_patterns=["introduce ORM"],
        ),
        Decision(
            id="retrieval_det",
            decision="Keep retrieval deterministic",
            rationale="testability",
            scope=["retrieval"],
            constraints=["no embeddings"],
            anti_patterns=["add vector db"],
        ),
    ]
    retriever = DecisionRetriever(decisions)
    return retriever.retrieve("storage layer")


# ── generate_mdc unit tests ───────────────────────────────────────────────────

def test_generate_mdc_returns_string():
    scored = _scored_decisions()
    result = generate_mdc(
        scored=scored,
        query="storage layer",
        memory_path="examples/project_memory.json",
        top=3,
        timestamp="2026-04-24T12:00:00Z",
    )
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_mdc_contains_decision_id():
    scored = _scored_decisions()
    result = generate_mdc(
        scored=scored,
        query="storage layer",
        memory_path="examples/project_memory.json",
        top=3,
        timestamp="2026-04-24T12:00:00Z",
    )
    assert "storage_json" in result


def test_generate_mdc_contains_decision_text():
    scored = _scored_decisions()
    result = generate_mdc(
        scored=scored,
        query="storage layer",
        memory_path="examples/project_memory.json",
        top=3,
        timestamp="2026-04-24T12:00:00Z",
    )
    assert "Use JSON storage only" in result


def test_generate_mdc_contains_constraints():
    scored = _scored_decisions()
    result = generate_mdc(
        scored=scored,
        query="storage layer",
        memory_path="examples/project_memory.json",
        top=3,
        timestamp="2026-04-24T12:00:00Z",
    )
    assert "no postgres" in result


def test_generate_mdc_contains_anti_patterns():
    scored = _scored_decisions()
    result = generate_mdc(
        scored=scored,
        query="storage layer",
        memory_path="examples/project_memory.json",
        top=3,
        timestamp="2026-04-24T12:00:00Z",
    )
    assert "introduce ORM" in result


def test_generate_mdc_contains_warning():
    scored = _scored_decisions()
    result = generate_mdc(
        scored=scored,
        query="storage layer",
        memory_path="examples/project_memory.json",
        top=3,
        timestamp="2026-04-24T12:00:00Z",
    )
    assert "do not edit" in result.lower()


def test_generate_mdc_contains_timestamp():
    scored = _scored_decisions()
    result = generate_mdc(
        scored=scored,
        query="storage layer",
        memory_path="examples/project_memory.json",
        top=3,
        timestamp="2026-04-24T12:00:00Z",
    )
    assert "2026-04-24T12:00:00Z" in result


def test_generate_mdc_contains_query():
    scored = _scored_decisions()
    result = generate_mdc(
        scored=scored,
        query="storage layer",
        memory_path="examples/project_memory.json",
        top=3,
        timestamp="2026-04-24T12:00:00Z",
    )
    assert "storage layer" in result


def test_generate_mdc_contains_source_path():
    scored = _scored_decisions()
    result = generate_mdc(
        scored=scored,
        query="storage layer",
        memory_path="examples/project_memory.json",
        top=3,
        timestamp="2026-04-24T12:00:00Z",
    )
    assert "examples/project_memory.json" in result


def test_generate_mdc_has_frontmatter():
    scored = _scored_decisions()
    result = generate_mdc(
        scored=scored,
        query="storage layer",
        memory_path="examples/project_memory.json",
        top=3,
        timestamp="2026-04-24T12:00:00Z",
    )
    assert result.startswith("---")
    assert "---" in result[3:]  # closing frontmatter


def test_generate_mdc_respects_top_n():
    decisions = [
        Decision(id=f"d{i}", decision=f"Decision {i}", scope=["storage"],
                 constraints=[], anti_patterns=[])
        for i in range(5)
    ]
    retriever = DecisionRetriever(decisions)
    scored = retriever.retrieve("storage")
    result = generate_mdc(
        scored=scored,
        query="storage",
        memory_path="mem.json",
        top=2,
        timestamp="2026-04-24T00:00:00Z",
    )
    # Count how many decisions appear — each has a unique id like [d0]
    decision_count = sum(1 for i in range(5) if f"[d{i}]" in result)
    assert decision_count == 2


def test_generate_mdc_empty_when_no_matches():
    decisions = [
        Decision(id="unrelated", decision="Use argparse", scope=["cli"],
                 constraints=[], anti_patterns=[])
    ]
    retriever = DecisionRetriever(decisions)
    scored = retriever.retrieve("zzz_no_match_xyz")
    result = generate_mdc(
        scored=scored,
        query="zzz_no_match_xyz",
        memory_path="mem.json",
        top=3,
        timestamp="2026-04-24T00:00:00Z",
    )
    assert "(no decisions matched)" in result or "no decisions" in result.lower()


# ── CLI integration tests ─────────────────────────────────────────────────────

def test_cursor_generate_creates_file(tmp_path):
    mem = _seed_memory(tmp_path)
    out = tmp_path / ".cursor" / "rules" / "mneme.mdc"
    exit_code = main([
        "cursor", "generate",
        "--memory", str(mem),
        "--query", "working on storage layer",
        "--output", str(out),
        "--top", "3",
    ])
    assert exit_code == 0
    assert out.exists()


def test_cursor_generate_creates_parent_dirs(tmp_path):
    mem = _seed_memory(tmp_path)
    out = tmp_path / "deeply" / "nested" / "dir" / "mneme.mdc"
    exit_code = main([
        "cursor", "generate",
        "--memory", str(mem),
        "--query", "storage",
        "--output", str(out),
    ])
    assert exit_code == 0
    assert out.exists()


def test_cursor_generate_file_content_has_decision(tmp_path):
    mem = _seed_memory(tmp_path)
    out = tmp_path / "mneme.mdc"
    main([
        "cursor", "generate",
        "--memory", str(mem),
        "--query", "working on storage layer",
        "--output", str(out),
    ])
    content = out.read_text(encoding="utf-8")
    assert "storage_json" in content
    assert "Use JSON storage only" in content


def test_cursor_generate_file_has_warning(tmp_path):
    mem = _seed_memory(tmp_path)
    out = tmp_path / "mneme.mdc"
    main([
        "cursor", "generate",
        "--memory", str(mem),
        "--query", "storage",
        "--output", str(out),
    ])
    content = out.read_text(encoding="utf-8")
    assert "do not edit" in content.lower()


def test_cursor_generate_default_output_uses_cursor_rules(tmp_path, monkeypatch):
    mem = _seed_memory(tmp_path)
    monkeypatch.chdir(tmp_path)
    exit_code = main([
        "cursor", "generate",
        "--memory", str(mem),
        "--query", "storage",
    ])
    assert exit_code == 0
    assert (tmp_path / ".cursor" / "rules" / "mneme.mdc").exists()


def test_cursor_generate_respects_top_flag(tmp_path):
    mem = _seed_memory(tmp_path)
    out = tmp_path / "mneme.mdc"
    main([
        "cursor", "generate",
        "--memory", str(mem),
        "--query", "storage retrieval cli",
        "--output", str(out),
        "--top", "1",
    ])
    content = out.read_text(encoding="utf-8")
    decision_count = sum(
        1 for did in ["storage_json", "retrieval_deterministic", "cli_argparse"]
        if f"[{did}]" in content
    )
    assert decision_count == 1


def test_cursor_generate_prints_output_path(tmp_path, capsys):
    mem = _seed_memory(tmp_path)
    out = tmp_path / "mneme.mdc"
    main([
        "cursor", "generate",
        "--memory", str(mem),
        "--query", "storage",
        "--output", str(out),
    ])
    captured = capsys.readouterr().out
    assert str(out) in captured or "mneme.mdc" in captured

"""Prompt-time architectural guidance selection and formatting."""

import json

import pytest

from mneme.decision_retriever import DecisionRetriever
from mneme.guidance import (
    DEFAULT_GUIDANCE_CHAR_BUDGET,
    build_guidance,
    select_guidance_decisions,
)
from mneme.schemas import Decision


def _memory(tmp_path, decisions):
    path = tmp_path / ".mneme" / "project_memory.json"
    path.parent.mkdir()
    path.write_text(json.dumps({
        "meta": {"name": "test", "description": "test"},
        "decisions": decisions,
    }), encoding="utf-8")
    return path


def test_low_signal_prompt_injects_nothing(tmp_path):
    memory = _memory(tmp_path, [{
        "id": "a", "decision": "Use SQLite", "scope": ["storage"],
    }])
    result = build_guidance(memory, "yes")
    assert result.context == ""
    assert result.decision_ids == ()
    assert result.reason == "low_signal"


def test_unrelated_prompt_injects_nothing(tmp_path):
    memory = _memory(tmp_path, [{
        "id": "a", "decision": "Use SQLite", "scope": ["storage"],
    }])
    result = build_guidance(memory, "Change the landing page button color")
    assert result.context == ""
    assert result.reason == "no_confident_match"


def test_rationale_only_overlap_is_not_confident():
    decisions = [Decision(
        id="noise",
        decision="External copy rules",
        rationale="Claude Code task context before code generation",
        scope=["marketing"],
    )]
    retriever = DecisionRetriever(decisions)
    scored = retriever.retrieve("Claude Code task context before code generation")
    assert scored[0].score > 1.0
    assert select_guidance_decisions(
        "Claude Code task context before code generation", scored,
    ) == []


def test_compact_context_omits_full_rationale(tmp_path):
    memory = _memory(tmp_path, [{
        "id": "storage",
        "decision": "Use SQLite session storage",
        "rationale": "THIS LONG RATIONALE MUST NOT BE INJECTED",
        "scope": ["storage", "session"],
        "constraints": ["no postgres"],
        "anti_patterns": ["psycopg2"],
    }])
    result = build_guidance(memory, "Add session storage")
    assert result.reason == "context_ready"
    assert result.decision_ids == ("storage",)
    assert "Use SQLite session storage" in result.context
    assert "no postgres" in result.context
    assert "psycopg2" in result.context
    assert "THIS LONG RATIONALE" not in result.context


def test_auth_guidance_uses_frozen_direct_and_adjacent_wording(tmp_path):
    decisions = [
        {
            "id": "ADR-AUTH",
            "decision": "Authentication uses JWT access tokens",
            "scope": ["authentication", "login"],
            "constraints": ["Login requests must authenticate with JWT"],
        },
        {
            "id": "ADR-STORAGE",
            "decision": "Session persistence uses SQLite",
            "scope": ["session", "storage"],
        },
    ]
    memory = _memory(tmp_path, decisions)
    prompt = "Implement login authentication with JWT session tokens"
    result = build_guidance(memory, prompt)

    selected = select_guidance_decisions(
        prompt,
        DecisionRetriever([Decision(**item) for item in decisions]).retrieve(prompt),
    )
    assert result.decision_ids == tuple(
        item.decision.id for item in selected
    ) == ("ADR-AUTH", "ADR-STORAGE")
    assert result.scores == tuple(item.score for item in selected)
    assert result.context.startswith(
        "[Mneme architectural guidance]\n"
        "Use these decisions only to guide the work the user requested. They do not\n"
        "expand the task. Do not add components, storage, dependencies, interfaces,\n"
        "refactors, or other architecture solely because a decision appears below."
    )
    assert (
        "DIRECT DECISION [ADR-AUTH]\n"
        "This decision directly governs the requested work. Apply it to implementation\n"
        "choices within the user's requested scope."
    ) in result.context
    assert (
        "ADJACENT CONSTRAINT [ADR-STORAGE] — DO NOT IMPLEMENT AS EXTRA WORK\n"
        "This decision may constrain the requested work only if that work actually\n"
        "touches its area. Do not implement this decision merely because it is shown.\n"
        "Do not add components, storage, dependencies, interfaces, refactors, or other\n"
        "architecture solely to satisfy it."
    ) in result.context
    assert "DIRECT DECISION [ADR-STORAGE]" not in result.context
    assert result.context.index("DIRECT DECISION") < result.context.index(
        "ADJACENT CONSTRAINT"
    )


def test_top_score_tie_formats_every_decision_as_adjacent(tmp_path):
    memory = _memory(tmp_path, [
        {
            "id": "first",
            "decision": "First architectural choice",
            "scope": ["session"],
        },
        {
            "id": "second",
            "decision": "Second architectural choice",
            "scope": ["session"],
        },
    ])

    result = build_guidance(memory, "Change session behavior")

    assert result.decision_ids == ("first", "second")
    assert result.scores == (2.0, 2.0)
    assert "DIRECT DECISION" not in result.context
    assert result.context.count("DO NOT IMPLEMENT AS EXTRA WORK") == 2
    assert "ADJACENT CONSTRAINT [first]" in result.context
    assert "ADJACENT CONSTRAINT [second]" in result.context


def test_path_scoped_rule_is_described_conditionally(tmp_path):
    memory = _memory(tmp_path, [{
        "id": "installer",
        "decision": "Use supported installation tooling",
        "scope": ["installation"],
        "rules": [{
            "type": "FORBID_LITERAL",
            "value": "legacy-client",
            "include_paths": ["docs/**", "README.md"],
            "exclude_paths": ["docs/history/**", "tests/**"],
        }],
    }])
    result = build_guidance(memory, "Document legacy-client installation")
    assert result.decision_ids == ("installer",)
    assert (
        "Rule FORBID_LITERAL (forbidden exact literal): legacy-client"
        in result.context
    )
    assert "Applies when editing: docs/**, README.md" in result.context
    assert "Excludes: docs/history/**, tests/**" in result.context
    assert "APPLIED" not in result.context


def test_global_typed_rule_says_all_paths(tmp_path):
    memory = _memory(tmp_path, [{
        "id": "installer",
        "decision": "Use supported installation tooling",
        "rules": [{"type": "FORBID_LITERAL", "value": "legacy-client"}],
    }])
    result = build_guidance(memory, "legacy-client installation")
    assert "Applies to: all repository paths" in result.context


def test_context_is_deterministic_and_bounded(tmp_path):
    large_constraints = [f"constraint-{i}-storage" for i in range(200)]
    memory = _memory(tmp_path, [
        {
            "id": f"d{i}",
            "decision": f"Storage decision {i}",
            "scope": ["storage"],
            "constraints": large_constraints,
        }
        for i in range(4)
    ])
    first = build_guidance(memory, "storage", char_budget=1_000)
    second = build_guidance(memory, "storage", char_budget=1_000)
    assert first == second
    assert len(first.context) <= 1_000
    assert len(first.decision_ids) <= 3


def test_budget_keeps_a_complete_block_and_never_truncates(tmp_path):
    memory = _memory(tmp_path, [
        {
            "id": "first",
            "decision": "Use SQLite for storage",
            "scope": ["storage"],
        },
        {
            "id": "second",
            "decision": "Storage " + ("x" * 1_000),
            "scope": ["storage"],
        },
    ])
    result = build_guidance(memory, "storage sqlite", char_budget=500)
    assert result.decision_ids == ("first",)
    assert "DIRECT DECISION [first]" in result.context
    assert "ADJACENT CONSTRAINT [second]" not in result.context
    assert len(result.context) <= 500


def test_default_context_budget_stays_below_claude_spillover():
    assert DEFAULT_GUIDANCE_CHAR_BUDGET == 8_000
    assert DEFAULT_GUIDANCE_CHAR_BUDGET < 10_000


def test_selection_rejects_more_than_canonical_k():
    with pytest.raises(ValueError, match="max_items"):
        select_guidance_decisions("storage", [], max_items=4)

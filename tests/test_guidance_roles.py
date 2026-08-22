"""Pure guidance-role classifier contract and locked evidence."""

import json
from pathlib import Path

from mneme.decision_retriever import DecisionRetriever, ScoredDecision
from mneme.guidance import select_guidance_decisions
from mneme.guidance_roles import classify_guidance_roles
from mneme.memory_store import MemoryStore
from mneme.schemas import Decision


RETRIEVAL_FIXTURE = (
    Path(__file__).parent / "fixtures" / "guidance_retrieval" / "cases.json"
)


def _scored(identifier: str, score: float) -> ScoredDecision:
    return ScoredDecision(
        decision=Decision(id=identifier, decision=f"Decision {identifier}"),
        score=score,
        matches={"decision": int(score)},
    )


def test_empty_selection_has_no_roles():
    assert classify_guidance_roles([]) == ()


def test_singleton_is_the_unique_direct_anchor():
    item = _scored("direct", 2.0)
    assignments = classify_guidance_roles([item])
    assert len(assignments) == 1
    assert assignments[0].scored_decision is item
    assert assignments[0].role == "direct"
    assert assignments[0].reason_code == "unique_highest_retrieval_rank"
    assert assignments[0].retrieval_rank == 1


def test_unique_top_is_direct_and_lower_candidates_are_adjacent():
    selected = [_scored("a", 8.0), _scored("b", 2.0), _scored("c", 1.5)]
    assignments = classify_guidance_roles(selected)
    assert [item.scored_decision for item in assignments] == selected
    assert [item.role for item in assignments] == [
        "direct", "adjacent_constraint", "adjacent_constraint",
    ]
    assert [item.reason_code for item in assignments] == [
        "unique_highest_retrieval_rank",
        "secondary_retrieval_candidate",
        "secondary_retrieval_candidate",
    ]
    assert [item.retrieval_rank for item in assignments] == [1, 2, 3]


def test_top_score_tie_grants_no_direct_role():
    selected = [_scored("a", 3.0), _scored("b", 3.0), _scored("c", 2.0)]
    assignments = classify_guidance_roles(selected)
    assert [item.role for item in assignments] == [
        "adjacent_constraint",
        "adjacent_constraint",
        "adjacent_constraint",
    ]
    assert [item.reason_code for item in assignments] == [
        "top_score_tie_no_direct_anchor",
        "top_score_tie_no_direct_anchor",
        "secondary_retrieval_candidate",
    ]


def test_classification_preserves_objects_order_scores_and_matches():
    selected = [_scored("a", 5.0), _scored("b", 2.0)]
    before = [
        (id(item), item.decision.id, item.score, dict(item.matches))
        for item in selected
    ]
    assignments = classify_guidance_roles(selected)
    after = [
        (
            id(item.scored_decision),
            item.scored_decision.decision.id,
            item.scored_decision.score,
            dict(item.scored_decision.matches),
        )
        for item in assignments
    ]
    assert after == before


def test_classification_is_deterministic():
    selected = [_scored("a", 5.0), _scored("b", 2.0)]
    assert classify_guidance_roles(selected) == classify_guidance_roles(selected)


def test_locked_retrieval_expected_decision_is_direct_18_of_18():
    fixture = json.loads(RETRIEVAL_FIXTURE.read_text(encoding="utf-8"))
    memory = MemoryStore(RETRIEVAL_FIXTURE.parent / fixture["memory"])
    memory.load()
    retriever = DecisionRetriever(memory.decisions())

    relevant_cases = 0
    direct_hits = 0
    for case in fixture["cases"]:
        expected = set(case.get("expected_ids", []))
        if not expected:
            continue
        relevant_cases += 1
        selected = select_guidance_decisions(
            case["prompt"],
            retriever.retrieve(case["prompt"]),
            max_items=fixture["k"],
        )
        direct = {
            assignment.scored_decision.decision.id
            for assignment in classify_guidance_roles(selected)
            if assignment.role == "direct"
        }
        direct_hits += expected.issubset(direct)

    assert relevant_cases == 18
    assert direct_hits == relevant_cases

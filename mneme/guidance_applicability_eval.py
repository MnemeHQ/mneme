"""Characterize decision applicability at the prompt-guidance boundary.

This evaluator is deliberately outside the production guidance path.  It
records which retrieved decisions directly constrain the submitted task and
which are merely adjacent context, preserves the frozen pre-R4 failure
diagnosis, and verifies the role-aware production formatter independently.

Decision-level guidance applicability is not ADR-020 typed-rule path
applicability.  The latter remains an edit-time rule concern once a target path
is known; this benchmark measures the earlier task-to-decision boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from mneme.context_builder import DEFAULT_MAX_DECISIONS
from mneme.decision_retriever import DecisionRetriever
from mneme.guidance import build_guidance, select_guidance_decisions
from mneme.guidance_roles import classify_guidance_roles
from mneme.memory_store import MemoryStore

EVAL_SCHEMA = "mneme.guidance-decision-applicability-eval/v1"

_GLOBAL_SCOPE_BOUNDARY = (
    "[Mneme architectural guidance]\n"
    "Use these decisions only to guide the work the user requested. They do not\n"
    "expand the task. Do not add components, storage, dependencies, interfaces,\n"
    "refactors, or other architecture solely because a decision appears below."
)

_DIRECT_WORDING = (
    "DIRECT DECISION [{decision_id}]\n"
    "This decision directly governs the requested work. Apply it to implementation\n"
    "choices within the user's requested scope."
)

_ADJACENT_WORDING = (
    "ADJACENT CONSTRAINT [{decision_id}] — DO NOT IMPLEMENT AS EXTRA WORK\n"
    "This decision may constrain the requested work only if that work actually\n"
    "touches its area. Do not implement this decision merely because it is shown.\n"
    "Do not add components, storage, dependencies, interfaces, refactors, or other\n"
    "architecture solely to satisfy it."
)


@dataclass(frozen=True)
class ApplicabilityCaseResult:
    id: str
    prompt: str
    target: str
    direct_ids: list[str]
    adjacent_ids: list[str]
    selected_ids: list[str]
    assigned_direct_ids: list[str]
    assigned_adjacent_constraint_ids: list[str]
    role_assignments: list[dict[str, Any]]
    historical_adjacent_undifferentiated_ids: list[str]
    adjacent_undifferentiated_ids: list[str]
    adjacent_authorizing_ids: list[str]
    unexpected_selected_ids: list[str]
    production_decision_ids: list[str]
    production_scores: list[float]
    direct_recall_at_k: float
    direct_role_recall: float
    baseline_snapshot_matches: bool
    role_snapshot_matches: bool
    role_aware_formatting_matches: bool
    non_authorizing_wording_matches: bool
    selection_preserved: bool
    score_evidence: list[dict[str, Any]]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def evaluate_fixture(path: str | Path) -> dict[str, Any]:
    """Evaluate one locked applicability-characterization fixture."""
    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if payload.get("schema") != EVAL_SCHEMA:
        raise ValueError(
            "unsupported guidance applicability schema: "
            f"{payload.get('schema')!r}"
        )

    k = int(payload.get("k", DEFAULT_MAX_DECISIONS))
    if k != DEFAULT_MAX_DECISIONS:
        raise ValueError(
            f"guidance applicability K must remain "
            f"{DEFAULT_MAX_DECISIONS}, got {k}"
        )

    memory_path = (fixture_path.parent / payload["memory"]).resolve()
    observed_memory_hash = _sha256(memory_path)
    expected_memory_hash = payload["memory_sha256"].upper()
    if observed_memory_hash != expected_memory_hash:
        raise ValueError(
            "guidance applicability memory hash mismatch: "
            f"expected {expected_memory_hash}, got {observed_memory_hash}"
        )

    store = MemoryStore(memory_path)
    store.load()
    retriever = DecisionRetriever(store.decisions())

    results: list[ApplicabilityCaseResult] = []
    for case in payload["cases"]:
        direct = list(case["direct_ids"])
        adjacent = list(case["adjacent_ids"])
        if set(direct) & set(adjacent):
            raise ValueError(
                f"case {case['id']!r} classifies an ID as both direct "
                "and adjacent"
            )

        selected = select_guidance_decisions(
            case["prompt"],
            retriever.retrieve(case["prompt"]),
            max_items=k,
        )
        selected_ids = [item.decision.id for item in selected]
        assignments = classify_guidance_roles(selected)
        assignment_ids = [
            item.scored_decision.decision.id for item in assignments
        ]
        assigned_direct = [
            item.scored_decision.decision.id
            for item in assignments
            if item.role == "direct"
        ]
        assigned_adjacent = [
            item.scored_decision.decision.id
            for item in assignments
            if item.role == "adjacent_constraint"
        ]
        guidance = build_guidance(memory_path, case["prompt"], max_items=k)
        production_ids = list(guidance.decision_ids)
        production_scores = list(guidance.scores)
        direct_set = set(direct)
        adjacent_set = set(adjacent)
        historical_adjacent = [
            decision_id
            for decision_id in selected_ids
            if decision_id in adjacent_set
        ]
        adjacent_undifferentiated = [
            decision_id
            for decision_id in historical_adjacent
            if _ADJACENT_WORDING.format(decision_id=decision_id)
            not in guidance.context
        ]
        adjacent_authorizing = [
            decision_id
            for decision_id in historical_adjacent
            if _DIRECT_WORDING.format(decision_id=decision_id)
            in guidance.context
        ]
        role_aware_formatting_matches = (
            guidance.context == ""
            if not assignments
            else (
                guidance.context.startswith(_GLOBAL_SCOPE_BOUNDARY)
                and all(
                    _DIRECT_WORDING.format(decision_id=decision_id)
                    in guidance.context
                    for decision_id in assigned_direct
                )
                and all(
                    _ADJACENT_WORDING.format(decision_id=decision_id)
                    in guidance.context
                    for decision_id in assigned_adjacent
                )
                and not adjacent_undifferentiated
                and not adjacent_authorizing
            )
        )
        direct_recall = (
            len(direct_set & set(selected_ids)) / len(direct_set)
            if direct_set else 1.0
        )
        direct_role_recall = (
            len(direct_set & set(assigned_direct)) / len(direct_set)
            if direct_set else 1.0
        )
        results.append(ApplicabilityCaseResult(
            id=case["id"],
            prompt=case["prompt"],
            target=case["target"],
            direct_ids=direct,
            adjacent_ids=adjacent,
            selected_ids=selected_ids,
            assigned_direct_ids=assigned_direct,
            assigned_adjacent_constraint_ids=assigned_adjacent,
            role_assignments=[{
                "decision_id": item.scored_decision.decision.id,
                "role": item.role,
                "reason_code": item.reason_code,
                "retrieval_rank": item.retrieval_rank,
                "score": item.scored_decision.score,
                "matches": dict(item.scored_decision.matches),
            } for item in assignments],
            historical_adjacent_undifferentiated_ids=historical_adjacent,
            adjacent_undifferentiated_ids=adjacent_undifferentiated,
            adjacent_authorizing_ids=adjacent_authorizing,
            unexpected_selected_ids=[
                decision_id
                for decision_id in selected_ids
                if decision_id not in direct_set | adjacent_set
            ],
            production_decision_ids=production_ids,
            production_scores=production_scores,
            direct_recall_at_k=direct_recall,
            direct_role_recall=direct_role_recall,
            baseline_snapshot_matches=(
                selected_ids == list(case["expected_current_selected_ids"])
            ),
            role_snapshot_matches=(
                assigned_direct == direct and assigned_adjacent == adjacent
            ),
            role_aware_formatting_matches=role_aware_formatting_matches,
            non_authorizing_wording_matches=(
                not adjacent_undifferentiated and not adjacent_authorizing
            ),
            selection_preserved=(
                assignment_ids == selected_ids
                and production_ids == selected_ids
                and production_scores == [item.score for item in selected]
            ),
            score_evidence=[{
                "decision_id": item.decision.id,
                "score": item.score,
                "matches": dict(item.matches),
            } for item in selected],
        ))

    expected = payload["expected_baseline"]
    historical_adjacent_count = sum(
        len(result.historical_adjacent_undifferentiated_ids)
        for result in results
    )
    adjacent_count = sum(
        len(result.adjacent_undifferentiated_ids) for result in results
    )
    adjacent_authorizing_count = sum(
        len(result.adjacent_authorizing_ids) for result in results
    )
    unexpected_count = sum(
        len(result.unexpected_selected_ids) for result in results
    )
    snapshot_matches = sum(result.baseline_snapshot_matches for result in results)
    role_snapshot_matches = sum(result.role_snapshot_matches for result in results)
    role_formatting_matches = sum(
        result.role_aware_formatting_matches for result in results
    )
    non_authorizing_wording_matches = sum(
        result.non_authorizing_wording_matches for result in results
    )
    direct_macro_recall = (
        sum(result.direct_recall_at_k for result in results) / len(results)
        if results else 1.0
    )
    direct_role_macro_recall = (
        sum(result.direct_role_recall for result in results) / len(results)
        if results else 1.0
    )
    known_adjacent_total = sum(len(result.adjacent_ids) for result in results)
    known_adjacent_role_hits = sum(
        len(
            set(result.adjacent_ids)
            & set(result.assigned_adjacent_constraint_ids)
        )
        for result in results
    )
    unclassified_selected = sum(
        len(result.selected_ids)
        - len(result.assigned_direct_ids)
        - len(result.assigned_adjacent_constraint_ids)
        for result in results
    )
    selection_changed_cases = sum(
        not result.selection_preserved for result in results
    )
    metrics = {
        "case_count": len(results),
        "baseline_snapshot_matches": snapshot_matches,
        "direct_macro_recall_at_k": direct_macro_recall,
        "historical_adjacent_undifferentiated_selections": (
            historical_adjacent_count
        ),
        "adjacent_undifferentiated_selections": adjacent_count,
        "adjacent_authorizing_selections": adjacent_authorizing_count,
        "unexpected_selections": unexpected_count,
        "role_snapshot_matches": role_snapshot_matches,
        "role_aware_formatting_matches": role_formatting_matches,
        "non_authorizing_wording_matches": non_authorizing_wording_matches,
        "direct_role_macro_recall": direct_role_macro_recall,
        "known_adjacent_role_hits": known_adjacent_role_hits,
        "known_adjacent_role_total": known_adjacent_total,
        "unclassified_selected_decisions": unclassified_selected,
        "selection_changed_cases": selection_changed_cases,
    }
    diagnosis_reproduced = (
        snapshot_matches == len(results)
        and direct_macro_recall == expected["direct_macro_recall_at_k"]
        and historical_adjacent_count
        == expected["adjacent_undifferentiated_selections"]
        and unexpected_count == expected["unexpected_selections"]
    )
    role_contract_reproduced = (
        role_snapshot_matches == len(results)
        and direct_role_macro_recall == 1.0
        and known_adjacent_role_hits == known_adjacent_total
        and unclassified_selected == 0
        and selection_changed_cases == 0
    )
    role_formatting_contract_reproduced = (
        role_contract_reproduced
        and role_formatting_matches == len(results)
        and non_authorizing_wording_matches == len(results)
        and adjacent_count == 0
        and adjacent_authorizing_count == 0
    )

    return {
        "schema": EVAL_SCHEMA,
        "locked_on": payload["locked_on"],
        "memory": str(memory_path),
        "memory_sha256": observed_memory_hash,
        "k": k,
        "production_behavior_changed": True,
        "role_classifier_wired_to_production": True,
        "metrics": metrics,
        "diagnosis_reproduced": diagnosis_reproduced,
        "role_contract_reproduced": role_contract_reproduced,
        "role_formatting_contract_reproduced": (
            role_formatting_contract_reproduced
        ),
        "cases": [asdict(result) for result in results],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reproduce the locked guidance-applicability diagnosis"
    )
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args(argv)
    report = evaluate_fixture(args.fixture)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if (
        report["diagnosis_reproduced"]
        and report["role_formatting_contract_reproduced"]
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())

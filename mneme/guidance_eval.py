"""Deterministic task-to-decision evaluation for prompt-time guidance.

This is intentionally separate from ``mneme.benchmark``.  The frozen benchmark
measures the Layer 1 retrieval/enforcement contract; this evaluator measures the
new task-query retrieval surface authorized by the pre-generation guidance
charter.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from mneme.context_builder import DEFAULT_MAX_DECISIONS
from mneme.decision_retriever import DecisionRetriever
from mneme.guidance import select_guidance_decisions
from mneme.memory_store import MemoryStore


EVAL_SCHEMA = "mneme.guidance-retrieval-eval/v1"


@dataclass(frozen=True)
class GuidanceEvalCaseResult:
    id: str
    split: str
    retrieved_ids: list[str]
    expected_ids: list[str]
    recall_at_k: float
    false_injection: bool
    low_signal_injection: bool
    safety_critical: bool


def _selected_ids(retriever: DecisionRetriever, prompt: str, k: int) -> list[str]:
    """Return the IDs an automatic guidance adapter may consider.

    The core retriever's empty-query fallback remains unchanged for existing
    callers.  Automatic guidance deliberately rejects that fallback: an empty
    meaningful-token set is a no-context result.
    """
    selected = select_guidance_decisions(
        prompt,
        retriever.retrieve(prompt),
        max_items=k,
    )
    return [item.decision.id for item in selected]


def evaluate_fixture(path: str | Path) -> dict[str, Any]:
    """Evaluate one locked task corpus and return a JSON-serializable report."""
    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if payload.get("schema") != EVAL_SCHEMA:
        raise ValueError(
            f"unsupported guidance evaluation schema: {payload.get('schema')!r}"
        )

    k = int(payload.get("k", DEFAULT_MAX_DECISIONS))
    if k != DEFAULT_MAX_DECISIONS:
        raise ValueError(
            f"guidance evaluation K must remain {DEFAULT_MAX_DECISIONS}, got {k}"
        )

    memory_path = fixture_path.parent / payload["memory"]
    store = MemoryStore(memory_path)
    store.load()
    retriever = DecisionRetriever(store.decisions())

    results: list[GuidanceEvalCaseResult] = []
    for case in payload["cases"]:
        retrieved = _selected_ids(retriever, case["prompt"], k)
        expected = list(case.get("expected_ids", []))
        expected_set = set(expected)
        recall = (
            len(expected_set & set(retrieved)) / len(expected_set)
            if expected_set
            else 1.0
        )
        no_relevance = bool(case.get("no_relevance", False))
        low_signal = bool(case.get("low_signal", False))
        results.append(GuidanceEvalCaseResult(
            id=case["id"],
            split=case["split"],
            retrieved_ids=retrieved,
            expected_ids=expected,
            recall_at_k=recall,
            false_injection=no_relevance and bool(retrieved),
            low_signal_injection=low_signal and bool(retrieved),
            safety_critical=bool(case.get("safety_critical", False)),
        ))

    relevant_holdout = [
        r for r in results if r.split == "holdout" and r.expected_ids
    ]
    safety = [r for r in results if r.safety_critical]
    no_relevance = [
        r for r, case in zip(results, payload["cases"])
        if case.get("no_relevance", False)
    ]
    low_signal = [
        r for r, case in zip(results, payload["cases"])
        if case.get("low_signal", False)
    ]

    metrics = {
        "holdout_macro_recall_at_k": (
            sum(r.recall_at_k for r in relevant_holdout) / len(relevant_holdout)
            if relevant_holdout else 1.0
        ),
        "safety_critical_recall_at_k": (
            sum(r.recall_at_k for r in safety) / len(safety) if safety else 1.0
        ),
        "no_relevance_false_injection_rate": (
            sum(r.false_injection for r in no_relevance) / len(no_relevance)
            if no_relevance else 0.0
        ),
        "low_signal_injections": sum(r.low_signal_injection for r in low_signal),
    }

    gates = payload["gates"]
    gate_results = {
        "holdout_macro_recall_at_k": (
            metrics["holdout_macro_recall_at_k"]
            >= gates["holdout_macro_recall_at_k"]
        ),
        "safety_critical_recall_at_k": (
            metrics["safety_critical_recall_at_k"]
            >= gates["safety_critical_recall_at_k"]
        ),
        "no_relevance_false_injection_rate": (
            metrics["no_relevance_false_injection_rate"]
            <= gates["max_no_relevance_false_injection_rate"]
        ),
        "low_signal_injections": (
            metrics["low_signal_injections"]
            <= gates["max_low_signal_injections"]
        ),
    }

    return {
        "schema": EVAL_SCHEMA,
        "locked_on": payload["locked_on"],
        "k": k,
        "metrics": metrics,
        "gates": gate_results,
        "passed": all(gate_results.values()),
        "cases": [asdict(r) for r in results],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the locked prompt-time guidance retrieval evaluation"
    )
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args(argv)
    report = evaluate_fixture(args.fixture)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

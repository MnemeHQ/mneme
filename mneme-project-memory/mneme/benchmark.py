"""
benchmark.py — Load and run benchmark scenarios for Mneme.

A scenario is a directory containing:
  query.txt         — The question asked of the LLM
  without_mneme.txt — Canned response with no memory injected (baseline)
  with_mneme.txt    — Canned response with memory injected (enhanced)
  scenario.json     — Metadata: name, description, expected_failure_terms

Verdict logic (Layer 2 — enforcement):
  PASS            — baseline has >= 1 violation; enhanced has 0 violations
  FAIL            — enhanced still has >= 1 violation
  WEAK            — baseline has 0 violations (scenario too weak to prove anything)
  WEAK_RETRIEVAL  — enhanced is clean but expected decisions were missed by retrieval

Layer 1 (retrieval) is scored independently on each scenario per the v1.1
methodology page (site/benchmark/index.html §03, §09). Layer 1 numbers are
recorded on every ScenarioResult regardless of Layer 2 verdict.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from mneme.decision_retriever import DecisionRetriever, ScoredDecision
from mneme.enforcer import check_prompt
from mneme.memory_store import MemoryStore


class ScenarioVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WEAK = "WEAK"
    WEAK_RETRIEVAL = "WEAK_RETRIEVAL"


@dataclass
class Scenario:
    path: Path
    query: str
    without_mneme: str
    with_mneme: str
    metadata: dict


@dataclass
class ScenarioResult:
    name: str
    category: str
    verdict: ScenarioVerdict
    baseline_violation_count: int
    enhanced_violation_count: int
    explanation: str
    baseline_triggers: list[str] = field(default_factory=list)
    enhanced_triggers: list[str] = field(default_factory=list)
    protected_decision_ids_hit: list[str] = field(default_factory=list)
    # Layer 1 — retrieval scoring (v1.1, §03 of methodology page).
    # Defaults are vacuously "perfect" so callers that build ScenarioResult by
    # hand (e.g. report-formatter unit tests) are unaffected.
    layer1_k: int = 5
    layer1_retrieved_ids: list[str] = field(default_factory=list)
    layer1_expected_ids: list[str] = field(default_factory=list)
    layer1_acceptable_ids: list[str] = field(default_factory=list)
    layer1_recall: float = 1.0
    layer1_precision: float = 1.0
    layer1_irrelevant_injection: bool = False


def load_scenario(path: str | Path) -> Scenario:
    """Load a benchmark scenario from a directory.

    Raises:
        FileNotFoundError: If any required file is missing.
    """
    p = Path(path)
    required = ["query.txt", "without_mneme.txt", "with_mneme.txt", "scenario.json"]
    for fname in required:
        if not (p / fname).exists():
            raise FileNotFoundError(f"Missing required file: {p / fname}")

    return Scenario(
        path=p,
        query=(p / "query.txt").read_text(encoding="utf-8").strip(),
        without_mneme=(p / "without_mneme.txt").read_text(encoding="utf-8").strip(),
        with_mneme=(p / "with_mneme.txt").read_text(encoding="utf-8").strip(),
        metadata=json.loads((p / "scenario.json").read_text(encoding="utf-8")),
    )


@dataclass
class Layer1Score:
    """Retrieval score for one scenario, ignoring enforcement.

    `retrieved_ids` is the ordered list of decision IDs in the runner's top-K
    (positive-score, matching what the enforcer actually sees via
    enforcer._top_nonzero). Recall and precision are computed against that
    set; `irrelevant_injection` flips True when at least one retrieved ID is
    neither expected nor explicitly acceptable.
    """

    k: int
    retrieved_ids: list[str]
    expected_ids: list[str]
    acceptable_ids: list[str]
    recall: float
    precision: float
    irrelevant_injection: bool


def score_layer1(
    scored: list[ScoredDecision],
    expected_ids: list[str],
    acceptable_ids: list[str],
    k: int,
) -> Layer1Score:
    """Compute Layer 1 retrieval metrics for one scenario.

    - Recall@K: fraction of expected_ids present in top-K; 1.0 vacuously if
      expected_ids is empty (control scenarios contribute no recall denominator).
    - Precision@K: fraction of top-K that lie in (expected ∪ acceptable);
      1.0 vacuously if nothing was retrieved (nothing was injected, so nothing
      can be wrong).
    - Irrelevant injection: True iff any retrieved ID is outside
      (expected ∪ acceptable). Per methodology §03, this is the per-scenario
      bit aggregated into the suite-level "irrelevant injection rate".
    """
    seen: set[str] = set()
    retrieved: list[str] = []
    for s in scored:
        if s.score <= 0:
            continue
        if s.decision.id in seen:
            continue
        seen.add(s.decision.id)
        retrieved.append(s.decision.id)
        if len(retrieved) >= k:
            break

    expected_set = set(expected_ids)
    relevant_set = expected_set | set(acceptable_ids)

    if expected_ids:
        recall = len([d for d in expected_ids if d in retrieved]) / len(expected_ids)
    else:
        recall = 1.0

    if retrieved:
        precision = len([d for d in retrieved if d in relevant_set]) / len(retrieved)
    else:
        precision = 1.0

    irrelevant = any(d not in relevant_set for d in retrieved)

    return Layer1Score(
        k=k,
        retrieved_ids=retrieved,
        expected_ids=list(expected_ids),
        acceptable_ids=list(acceptable_ids),
        recall=recall,
        precision=precision,
        irrelevant_injection=irrelevant,
    )


class BenchmarkRunner:
    """Evaluates benchmark scenarios against project memory.

    Reuses enforcer.check_prompt() so evaluation is identical to the live product.
    Records Layer 1 (retrieval) and Layer 2 (enforcement) results separately
    per the v1.1 methodology.
    """

    def __init__(self, store: MemoryStore, top: int = 5) -> None:
        self.store = store
        self.retriever = DecisionRetriever(store.decisions())
        self.top = top

    def run_scenario(self, scenario: Scenario) -> ScenarioResult:
        scored = self.retriever.retrieve(scenario.query)

        name = scenario.metadata.get("name", scenario.path.name)
        category = scenario.metadata.get("category", "uncategorised")
        expected_ids: list[str] = scenario.metadata.get(
            "expected_protected_decision_ids", []
        )
        acceptable_ids: list[str] = scenario.metadata.get(
            "acceptable_decision_ids", []
        )

        # Layer 1: retrieval scoring, independent of enforcement.
        l1 = score_layer1(scored, expected_ids, acceptable_ids, self.top)

        # Layer 2: enforcement against the same top-K window.
        baseline_result = check_prompt(scenario.without_mneme, scored, top=self.top)
        enhanced_result = check_prompt(scenario.with_mneme, scored, top=self.top)

        baseline_count = len(baseline_result.violations)
        enhanced_count = len(enhanced_result.violations)
        baseline_triggers = [v.trigger for v in baseline_result.violations]
        enhanced_triggers = [v.trigger for v in enhanced_result.violations]

        protected_hit = [did for did in expected_ids if did in l1.retrieved_ids]
        intended_decisions_retrieved = (not expected_ids) or l1.recall == 1.0

        if baseline_count == 0:
            verdict = ScenarioVerdict.WEAK
            explanation = (
                "Baseline response had no violations - scenario fixtures may be too weak. "
                "Strengthen without_mneme.txt to include more explicit failure terms."
            )
        elif enhanced_count > 0:
            verdict = ScenarioVerdict.FAIL
            explanation = (
                f"Mneme did not prevent the violation. "
                f"Enhanced response still triggered {enhanced_count} violation(s): "
                f"{', '.join(enhanced_triggers[:3])}."
            )
        elif not intended_decisions_retrieved:
            verdict = ScenarioVerdict.WEAK_RETRIEVAL
            missing = [d for d in expected_ids if d not in l1.retrieved_ids]
            explanation = (
                f"Enhanced response was clean, but intended decision(s) were not retrieved: "
                f"{', '.join(missing)}. PASS may be coincidental."
            )
        else:
            verdict = ScenarioVerdict.PASS
            explanation = (
                f"Mneme prevented the violation. "
                f"Baseline triggered {baseline_count} violation(s) "
                f"({', '.join(baseline_triggers[:3])}); "
                f"enhanced response had none. "
                f"Retrieved: {', '.join(protected_hit)}."
            )

        return ScenarioResult(
            name=name,
            category=category,
            verdict=verdict,
            baseline_violation_count=baseline_count,
            enhanced_violation_count=enhanced_count,
            explanation=explanation,
            baseline_triggers=baseline_triggers,
            enhanced_triggers=enhanced_triggers,
            protected_decision_ids_hit=protected_hit,
            layer1_k=l1.k,
            layer1_retrieved_ids=l1.retrieved_ids,
            layer1_expected_ids=l1.expected_ids,
            layer1_acceptable_ids=l1.acceptable_ids,
            layer1_recall=l1.recall,
            layer1_precision=l1.precision,
            layer1_irrelevant_injection=l1.irrelevant_injection,
        )

    def run_suite(self, benchmarks_dir: str | Path) -> list[ScenarioResult]:
        """Run all scenarios found under benchmarks_dir."""
        root = Path(benchmarks_dir)
        scenario_dirs = sorted(
            d for d in root.iterdir()
            if d.is_dir() and (d / "scenario.json").exists()
        )
        return [self.run_scenario(load_scenario(d)) for d in scenario_dirs]

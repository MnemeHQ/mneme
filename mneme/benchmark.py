"""
benchmark.py — Load and run benchmark scenarios for Mneme.

A scenario is a directory containing:
  query.txt         — The question asked of the LLM
  without_mneme.txt — Canned response with no memory injected (baseline)
  with_mneme.txt    — Canned response with memory injected (enhanced)
  scenario.json     — Metadata: name, description, expected_failure_terms

v1.1 Step 2 adds an optional structured-output protocol. A scenario may also
provide:
  with_mneme.json     — JSON variant; preferred over with_mneme.txt
  without_mneme.json  — JSON variant; preferred over without_mneme.txt
  scenario.json["assertions"] — list of forbidden_dependency /
                                forbidden_path_pattern checks

Each side (with / without) is evaluated independently: structured if a
.json file is present and parses, TXT otherwise. Missing .json files
fall back to TXT and emit a UserWarning (no MALFORMED). All shipped
scenarios carry both JSON siblings; a fired warning means an unmigrated
or accidentally-deleted fixture.

Verdict logic (Layer 2 — enforcement):
  PASS            — baseline has >= 1 violation; enhanced has 0 violations
  FAIL            — enhanced still has >= 1 violation
  WEAK            — baseline has 0 violations (scenario too weak to prove anything)
  WEAK_RETRIEVAL  — enhanced is clean but expected decisions were missed by retrieval
  MALFORMED       — a structured fixture exists but failed JSON parse, type
                    validation, or referenced an unknown assertion type.

Layer 1 (retrieval) is scored independently on each scenario per the v1.1
methodology page (site/benchmark/index.html §03, §09). Layer 1 numbers are
recorded on every ScenarioResult regardless of Layer 2 verdict.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from mneme.benchmark_schemas import Assertion, StructuredOutput
from mneme.benchmark_verifier import verify
from mneme.context_builder import DEFAULT_MAX_DECISIONS
from mneme.decision_retriever import DecisionRetriever, ScoredDecision
from mneme.enforcer import check_prompt
from mneme.memory_store import MemoryStore


class ScenarioVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WEAK = "WEAK"
    WEAK_RETRIEVAL = "WEAK_RETRIEVAL"
    MALFORMED = "MALFORMED"


@dataclass
class Scenario:
    path: Path
    query: str
    without_mneme: str
    with_mneme: str
    metadata: dict
    # v1.1 Step 2 — optional structured fixtures and assertion list.
    # When None / [] the runner uses the legacy TXT keyword path.
    without_mneme_structured: StructuredOutput | None = None
    with_mneme_structured: StructuredOutput | None = None
    assertions: list[Assertion] = field(default_factory=list)
    # If non-empty, run_scenario short-circuits to ScenarioVerdict.MALFORMED
    # with this string in the explanation.
    malformed_reason: str = ""


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
    layer1_k: int = DEFAULT_MAX_DECISIONS
    layer1_retrieved_ids: list[str] = field(default_factory=list)
    layer1_expected_ids: list[str] = field(default_factory=list)
    layer1_acceptable_ids: list[str] = field(default_factory=list)
    layer1_recall: float = 1.0
    layer1_precision: float = 1.0
    layer1_irrelevant_injection: bool = False


def _load_optional_structured(json_path: Path) -> tuple[StructuredOutput | None, str]:
    """Load an optional structured fixture sibling.

    Returns (parsed, reason). Reason is non-empty only when the file exists
    but failed to parse — in which case parsed is None and the caller should
    surface ScenarioVerdict.MALFORMED.

    When the sibling is missing, emit a UserWarning (the loader falls back
    to the TXT keyword path; no MALFORMED). All shipped scenarios as of
    Step 3B carry both JSON siblings, so a fired warning means a fixture
    is missing a structured payload.
    """
    if not json_path.exists():
        warnings.warn(
            f"Benchmark scenario {json_path.parent.name}: missing structured "
            f"sibling '{json_path.name}' — falling back to TXT keyword path.",
            UserWarning,
            stacklevel=3,
        )
        return None, ""
    try:
        return StructuredOutput.from_json(
            json_path.read_text(encoding="utf-8")
        ), ""
    except ValueError as e:
        return None, f"{json_path.name}: {e}"


def _load_optional_assertions(metadata: dict) -> tuple[list[Assertion], str]:
    """Parse the optional ``assertions`` array from scenario.json.

    Returns (assertions, reason). Reason is non-empty when the field exists
    but is malformed (not a list, or contains an unknown assertion type).
    """
    raw = metadata.get("assertions")
    if raw is None:
        return [], ""
    if not isinstance(raw, list):
        return [], "scenario.json 'assertions' must be a list"
    parsed: list[Assertion] = []
    for i, entry in enumerate(raw):
        try:
            parsed.append(Assertion.from_dict(entry))
        except ValueError as e:
            return [], f"scenario.json assertions[{i}]: {e}"
    return parsed, ""


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

    metadata = json.loads((p / "scenario.json").read_text(encoding="utf-8"))

    without_structured, without_reason = _load_optional_structured(
        p / "without_mneme.json"
    )
    with_structured, with_reason = _load_optional_structured(
        p / "with_mneme.json"
    )
    assertions, assertions_reason = _load_optional_assertions(metadata)

    reasons = [r for r in (without_reason, with_reason, assertions_reason) if r]
    malformed_reason = "; ".join(reasons)

    return Scenario(
        path=p,
        query=(p / "query.txt").read_text(encoding="utf-8").strip(),
        without_mneme=(p / "without_mneme.txt").read_text(encoding="utf-8").strip(),
        with_mneme=(p / "with_mneme.txt").read_text(encoding="utf-8").strip(),
        metadata=metadata,
        without_mneme_structured=without_structured,
        with_mneme_structured=with_structured,
        assertions=assertions,
        malformed_reason=malformed_reason,
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

    def __init__(self, store: MemoryStore, top: int = DEFAULT_MAX_DECISIONS) -> None:
        self.store = store
        self.retriever = DecisionRetriever(store.decisions())
        self.top = top

    def _evaluate_side(
        self,
        text: str,
        structured: StructuredOutput | None,
        assertions: list[Assertion],
        scored: list[ScoredDecision],
    ) -> tuple[int, list[str]]:
        """Evaluate one side (baseline or enhanced).

        Prefers the structured path when ``structured`` is provided; falls
        back to the legacy keyword-based ``check_prompt`` otherwise. Returns
        ``(violation_count, trigger_list)``.
        """
        if structured is not None:
            result = verify(structured, assertions)
            if result.refused:
                return 0, []
            triggers: list[str] = []
            for ar in result.assertion_results:
                if not ar.passed:
                    triggers.extend(ar.triggers)
            return len(result.violations), triggers

        enforcement = check_prompt(text, scored, top=self.top)
        return (
            len(enforcement.violations),
            [v.trigger for v in enforcement.violations],
        )

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

        # MALFORMED short-circuit (v1.1 Step 2): structured fixture or
        # assertion list failed to parse / validate. Layer 1 is still
        # recorded so retrieval signal is not lost.
        if scenario.malformed_reason:
            return ScenarioResult(
                name=name,
                category=category,
                verdict=ScenarioVerdict.MALFORMED,
                baseline_violation_count=0,
                enhanced_violation_count=0,
                explanation=(
                    f"Malformed structured fixture(s): {scenario.malformed_reason}"
                ),
                baseline_triggers=[],
                enhanced_triggers=[],
                protected_decision_ids_hit=[
                    d for d in expected_ids if d in l1.retrieved_ids
                ],
                layer1_k=l1.k,
                layer1_retrieved_ids=l1.retrieved_ids,
                layer1_expected_ids=l1.expected_ids,
                layer1_acceptable_ids=l1.acceptable_ids,
                layer1_recall=l1.recall,
                layer1_precision=l1.precision,
                layer1_irrelevant_injection=l1.irrelevant_injection,
            )

        # Layer 2: enforcement, per side, structured-or-TXT.
        baseline_count, baseline_triggers = self._evaluate_side(
            scenario.without_mneme,
            scenario.without_mneme_structured,
            scenario.assertions,
            scored,
        )
        enhanced_count, enhanced_triggers = self._evaluate_side(
            scenario.with_mneme,
            scenario.with_mneme_structured,
            scenario.assertions,
            scored,
        )

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

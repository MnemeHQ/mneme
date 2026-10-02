"""
mneme.open_architecture.stage_b_baseline — Frozen Stage B Baseline Provenance and Replay.

Provides durable, offline reproduction of the frozen O1A Batch 01 Stage B
semantic classification baseline without invoking external model APIs.

Binds:
- Frozen baseline identities and configuration hashes
- 100 reference decisions across 5 Batch 01 repositories
- 800 frozen classifier execution outcomes (8 semantic tasks per reference)
- Exact eight-metric composite formula and full-precision metrics:
  stage_b_semantic_score = 0.5171813272250951
- Discloses the legacy historical literal 0.517188 (PR #413) as an approximate constant

Architecture & Boundary Invariants:
- Research-only: zero changes to canonical DecisionRetriever, Enforcer, ConflictDetector,
  DecisionIndex, MemoryStore, or authority services.
- Single scoring authority: delegates all semantic normalization and dimension metrics
  strictly to harness._execute_stage_b_tasks_and_scoring() via OfflineB0Classifier.
- Zero model/API calls: strictly offline evaluation from committed evidence.
- Deterministic fail-closed validation: verifies outcome count, keys, identities, and
  semantic content hash upon loading.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from mneme.open_architecture.classification import (
    ClassifierResult,
    ClassifierTask,
    ClassifierTaskType,
    SemanticClassifier,
)
from mneme.open_architecture.harness import (
    FROZEN_BASELINE_CONFIG_HASH,
    FROZEN_BASELINE_ID,
    FROZEN_REFERENCE_CORPUS_HASH,
    FrozenReferenceDecision,
    _execute_stage_b_tasks_and_scoring,
    load_reference_corpus,
)
from mneme.open_architecture.manifest import Manifest, RepositoryConfig

# Frozen classifier identities
FROZEN_CLASSIFIER_BACKEND: str = "anthropic"
FROZEN_CLASSIFIER_VERSION: str = "0.1"
FROZEN_MODEL_IDENTIFIER: str = "claude-sonnet-4-6"
FROZEN_TAXONOMY_VERSION: str = "0.1"

# Semantic content hash over the 800 outcomes (non-volatile fields)
FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH: str = (
    "sha256:3c215db23a7fae8b8ac98852e65985b1efded354850fd9be65c24bfd1c90682d"
)

# Baseline composites
LEGACY_HISTORICAL_STAGE_B_LITERAL: float = 0.517188
EXACT_STAGE_B_COMPOSITE: float = 0.5171813272250951

# The eight evaluated semantic tasks
STAGE_B_EVALUATED_TASKS: tuple[str, ...] = (
    "decision_classification_accuracy",
    "domain_micro_f1",
    "purpose_micro_f1",
    "authority_accuracy",
    "scope_accuracy",
    "lifecycle_accuracy",
    "relationship_accuracy",
    "enforcement_classification_accuracy",
)

# Expected per-repository composites (full precision)
EXPECTED_REPOSITORY_COMPOSITES: dict[str, float] = {
    "adrkit": 0.5143057222889156,
    "archlint": 0.39479166666666665,
    "gsa_agentic_coding_quickstart": 0.639712525326336,
    "helix": 0.5664556962025317,
    "modonome": 0.4706410256410256,
}


# ── Data Models ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FrozenClassifierOutcome:
    """One immutable classifier execution outcome from the frozen B0 run."""

    candidate_id: str
    task_type: ClassifierTaskType
    backend_id: str
    classifier_version: str
    model_identifier: str | None
    taxonomy_version: str
    run_id: str
    execution_id: str
    output: dict[str, Any]
    confidence: float | None
    latency_ms: float | None
    cost_amount: float | None
    cost_currency: str | None
    escalated: bool
    created_at: str

    def to_classifier_result(self) -> ClassifierResult:
        """Convert to the standard ClassifierResult DTO."""
        return ClassifierResult(
            task_type=self.task_type,
            backend_id=self.backend_id,
            classifier_version=self.classifier_version,
            model_identifier=self.model_identifier,
            taxonomy_version=self.taxonomy_version,
            candidate_id=self.candidate_id,
            output=self.output,
            confidence=self.confidence,
            latency_ms=self.latency_ms,
            cost_amount=self.cost_amount,
            cost_currency=self.cost_currency,
            escalated=self.escalated,
            executed_at=self.created_at,
            execution_id=self.execution_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "candidate_id": self.candidate_id,
            "classifier_version": self.classifier_version,
            "confidence": self.confidence,
            "cost_amount": self.cost_amount,
            "cost_currency": self.cost_currency,
            "created_at": self.created_at,
            "escalated": self.escalated,
            "execution_id": self.execution_id,
            "latency_ms": self.latency_ms,
            "model_identifier": self.model_identifier,
            "output": self.output,
            "run_id": self.run_id,
            "task_type": self.task_type.value,
            "taxonomy_version": self.taxonomy_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FrozenClassifierOutcome:
        return cls(
            candidate_id=str(data["candidate_id"]),
            task_type=ClassifierTaskType(data["task_type"]),
            backend_id=str(data["backend_id"]),
            classifier_version=str(data["classifier_version"]),
            model_identifier=data.get("model_identifier"),
            taxonomy_version=str(data["taxonomy_version"]),
            run_id=str(data["run_id"]),
            execution_id=str(data["execution_id"]),
            output=dict(data["output"]),
            confidence=float(data["confidence"]) if data.get("confidence") is not None else None,
            latency_ms=float(data["latency_ms"]) if data.get("latency_ms") is not None else None,
            cost_amount=float(data["cost_amount"]) if data.get("cost_amount") is not None else None,
            cost_currency=data.get("cost_currency"),
            escalated=bool(data.get("escalated", False)),
            created_at=str(data["created_at"]),
        )


@dataclass(frozen=True)
class StageBRepositoryScore:
    """Per-repository Stage B metric breakdown and composite score."""

    repo_id: str
    reference_count: int
    task_count: int
    metrics: dict[str, float]
    composite_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "reference_count": self.reference_count,
            "task_count": self.task_count,
            "metrics": self.metrics,
            "composite_score": self.composite_score,
        }


@dataclass(frozen=True)
class StageBBaselineEvaluationResult:
    """Complete evaluation outcome reproducing Stage B B0 baseline metrics."""

    baseline_id: str
    classifier_backend: str
    classifier_version: str
    model_identifier: str | None
    taxonomy_version: str
    reference_corpus_hash: str
    semantic_content_hash: str
    total_references: int
    total_outcomes: int
    repository_scores: dict[str, StageBRepositoryScore]
    stage_b_semantic_score: float
    legacy_historical_literal: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_id": self.baseline_id,
            "classifier_backend": self.classifier_backend,
            "classifier_version": self.classifier_version,
            "model_identifier": self.model_identifier,
            "taxonomy_version": self.taxonomy_version,
            "reference_corpus_hash": self.reference_corpus_hash,
            "semantic_content_hash": self.semantic_content_hash,
            "total_references": self.total_references,
            "total_outcomes": self.total_outcomes,
            "repository_scores": {
                r: s.to_dict() for r, s in sorted(self.repository_scores.items())
            },
            "stage_b_semantic_score": self.stage_b_semantic_score,
            "legacy_historical_literal": self.legacy_historical_literal,
        }


# ── Hash Computation ───────────────────────────────────────────────────────────


def compute_stage_b_semantic_content_hash(
    outcomes: Iterable[FrozenClassifierOutcome | dict[str, Any]],
) -> str:
    """Compute deterministic SHA-256 over non-volatile semantic outcome fields."""
    semantic_items: list[dict[str, Any]] = []

    for item in outcomes:
        if isinstance(item, FrozenClassifierOutcome):
            c_id = item.candidate_id
            t_type = item.task_type.value
            b_id = item.backend_id
            c_ver = item.classifier_version
            m_id = item.model_identifier
            tax_ver = item.taxonomy_version
            out = item.output
            esc = item.escalated
        else:
            c_id = item["candidate_id"]
            t_type = item["task_type"]
            b_id = item["backend_id"]
            c_ver = item["classifier_version"]
            m_id = item.get("model_identifier")
            tax_ver = item["taxonomy_version"]
            out = item["output"]
            esc = bool(item.get("escalated", False))

        semantic_items.append({
            "backend_id": b_id,
            "candidate_id": c_id,
            "classifier_version": c_ver,
            "escalated": esc,
            "model_identifier": m_id,
            "output": out,
            "task_type": t_type,
            "taxonomy_version": tax_ver,
        })

    semantic_items.sort(key=lambda x: (x["candidate_id"], x["task_type"]))
    canonical_json = json.dumps(semantic_items, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


# ── Loading & Validation (Fail-Closed) ──────────────────────────────────────────


def load_stage_b_outcomes(
    outcomes_path: str | Path | None = None,
) -> list[FrozenClassifierOutcome]:
    """Load and strictly validate the frozen Stage B B0 classifier outcomes from JSONL.

    Fails closed if:
    - File does not exist
    - Outcome count != 800
    - Reference count != 100
    - Tasks per reference != 8
    - Duplicate (candidate_id, task_type) keys exist
    - Classifier backend, version, model, or taxonomy version mismatch
    - Semantic content hash does not match FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    path = (
        Path(outcomes_path)
        if outcomes_path
        else repo_root
        / "benchmarks"
        / "open_architecture"
        / "batch_01"
        / "baseline_stage_b"
        / "classifier_outcomes.jsonl"
    )

    if not path.is_file():
        raise FileNotFoundError(f"Stage B outcomes file not found: {path}")

    outcomes: list[FrozenClassifierOutcome] = []
    seen_keys: set[tuple[str, str]] = set()
    ref_tasks: dict[str, set[str]] = {}

    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line_str = line.strip()
            if not line_str:
                continue
            data = json.loads(line_str)
            outcome = FrozenClassifierOutcome.from_dict(data)

            key = (outcome.candidate_id, outcome.task_type.value)
            if key in seen_keys:
                raise ValueError(
                    f"Duplicate outcome for ({outcome.candidate_id}, {outcome.task_type.value}) on line {line_no}"
                )
            seen_keys.add(key)
            ref_tasks.setdefault(outcome.candidate_id, set()).add(outcome.task_type.value)

            if outcome.backend_id != FROZEN_CLASSIFIER_BACKEND:
                raise ValueError(f"Backend mismatch: {outcome.backend_id!r} != {FROZEN_CLASSIFIER_BACKEND!r}")
            if outcome.classifier_version != FROZEN_CLASSIFIER_VERSION:
                raise ValueError(f"Version mismatch: {outcome.classifier_version!r} != {FROZEN_CLASSIFIER_VERSION!r}")
            if outcome.model_identifier != FROZEN_MODEL_IDENTIFIER:
                raise ValueError(f"Model mismatch: {outcome.model_identifier!r} != {FROZEN_MODEL_IDENTIFIER!r}")
            if outcome.taxonomy_version != FROZEN_TAXONOMY_VERSION:
                raise ValueError(f"Taxonomy version mismatch: {outcome.taxonomy_version!r} != {FROZEN_TAXONOMY_VERSION!r}")

            outcomes.append(outcome)

    if len(outcomes) != 800:
        raise ValueError(f"Expected exactly 800 outcomes, got {len(outcomes)}")
    if len(ref_tasks) != 100:
        raise ValueError(f"Expected exactly 100 references, got {len(ref_tasks)}")

    for ref_id, tasks in ref_tasks.items():
        if len(tasks) != 8:
            raise ValueError(f"Reference {ref_id} has {len(tasks)} tasks, expected 8")

    outcomes.sort(key=lambda o: (o.candidate_id, o.task_type.value))

    # Enforce semantic content hash fail-closed against frozen benchmark authority
    computed_hash = compute_stage_b_semantic_content_hash(outcomes)
    if computed_hash != FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH:
        raise ValueError(
            f"Stage B semantic content hash mismatch: expected {FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH!r}, "
            f"computed {computed_hash!r}"
        )

    return outcomes


# ── Offline Classifier Replay ──────────────────────────────────────────────────


class OfflineB0Classifier:
    """In-memory SemanticClassifier replaying the frozen 800 B0 baseline outputs."""

    backend_id: str = FROZEN_CLASSIFIER_BACKEND
    classifier_version: str = FROZEN_CLASSIFIER_VERSION
    model_identifier: str | None = FROZEN_MODEL_IDENTIFIER
    taxonomy_version: str = FROZEN_TAXONOMY_VERSION

    def __init__(self, outcomes: list[FrozenClassifierOutcome] | None = None) -> None:
        if outcomes is None:
            outcomes = load_stage_b_outcomes()
        self._results_map: dict[tuple[str, ClassifierTaskType], ClassifierResult] = {
            (o.candidate_id, o.task_type): o.to_classifier_result()
            for o in outcomes
        }

    def execute(self, task: ClassifierTask) -> ClassifierResult:
        key = (task.candidate_id, task.task_type)
        if key not in self._results_map:
            raise KeyError(f"No recorded outcome for task {key}")
        return self._results_map[key]

    def execute_batch(self, tasks: list[ClassifierTask]) -> list[ClassifierResult]:
        return [self.execute(t) for t in tasks]


# ── Scoring Authority Delegation & Composite Calculation ───────────────────────


def score_stage_b_outcomes(
    outcomes: list[FrozenClassifierOutcome],
    references: list[FrozenReferenceDecision],
    manifest: Manifest,
) -> StageBBaselineEvaluationResult:
    """Score pre-recorded classifier outcomes offline using the harness scoring authority.

    Replays outcomes through OfflineB0Classifier into harness._execute_stage_b_tasks_and_scoring()
    and computes the research-only eight-metric composite across all 5 repositories.
    """
    classifier = OfflineB0Classifier(outcomes)
    repo_scores: dict[str, StageBRepositoryScore] = {}

    for repo_cfg in manifest.repositories:
        repo_refs = [r for r in references if r.repository == repo_cfg.github]
        if len(repo_refs) != 20:
            raise ValueError(f"Expected 20 references for '{repo_cfg.id}', got {len(repo_refs)}")

        # Harness owns normalization, task mapping, and per-dimension metric derivation
        harness_result = _execute_stage_b_tasks_and_scoring(
            repository_config=repo_cfg,
            references=repo_refs,
            classifier=classifier,
        )

        metrics = harness_result.metrics
        composite = sum(metrics[t] for t in STAGE_B_EVALUATED_TASKS) / 8.0

        repo_scores[repo_cfg.id] = StageBRepositoryScore(
            repo_id=repo_cfg.id,
            reference_count=len(repo_refs),
            task_count=len(repo_refs) * 8,
            metrics=metrics,
            composite_score=composite,
        )

    macro_composite = sum(s.composite_score for s in repo_scores.values()) / len(repo_scores)
    content_hash = compute_stage_b_semantic_content_hash(outcomes)

    return StageBBaselineEvaluationResult(
        baseline_id=FROZEN_BASELINE_ID,
        classifier_backend=FROZEN_CLASSIFIER_BACKEND,
        classifier_version=FROZEN_CLASSIFIER_VERSION,
        model_identifier=FROZEN_MODEL_IDENTIFIER,
        taxonomy_version=FROZEN_TAXONOMY_VERSION,
        reference_corpus_hash=FROZEN_REFERENCE_CORPUS_HASH,
        semantic_content_hash=content_hash,
        total_references=len(references),
        total_outcomes=len(outcomes),
        repository_scores=repo_scores,
        stage_b_semantic_score=macro_composite,
        legacy_historical_literal=LEGACY_HISTORICAL_STAGE_B_LITERAL,
    )

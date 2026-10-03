"""
mneme.open_architecture.stage_b_relationship_selectivity_experiment — O1A B-T1D Selectivity Experiment.

Implements the research-only B-T1D relationship selectivity treatment scaffold
over the Batch 01 v0.2-grounding reference decision corpus.

Diagnostic & Experimental Purpose:
B-T1D tests ONE variable only: relationship emission selectivity.
It tests whether over-generation (105 extra tuples, 72 depends_on) can be causally
reduced by conditioning extraction upon an explicit formal-relationship emission gate
without modifying relationship-type definitions, target representation, or taxonomy.

Architecture & Boundary Invariants:
- Research-only treatment: does NOT modify DecisionRetriever, ConflictDetector, Enforcer,
  MemoryStore, DecisionIndex, or authority services.
- Does NOT alter production relationship semantics.
- Does NOT modify Taxonomy 0.1.
- Does NOT modify Batch 01 v0.1 or v0.2-grounding reference decisions.
- Does NOT modify historical B0 or B-T1C code, artifacts, or validators.
- Zero model/API/network calls during pre-execution validation.
- Live execution is strictly prohibited until the stop/go gate is satisfied.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mneme.open_architecture.classification import (
    ClassifierResult,
    ClassifierTask,
    ClassifierTaskType,
    normalize_relationships,
)
from mneme.open_architecture.classifiers.anthropic import (
    AnthropicClassifier,
    AnthropicMalformedResponseError,
)
from mneme.open_architecture.export import (
    compute_reference_corpus_content_hash,
    compute_reference_corpus_records_hash,
)
from mneme.open_architecture.harness import (
    FROZEN_BASELINE_CONFIG_HASH,
    FROZEN_BASELINE_ID,
    FrozenReferenceDecision,
    _execute_stage_b_tasks_and_scoring,
    load_reference_corpus,
)
from mneme.open_architecture.manifest import Manifest
from mneme.open_architecture.stage_b_baseline import (
    FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH,
    FrozenClassifierOutcome,
    OfflineB0Classifier,
    STAGE_B_EVALUATED_TASKS,
    load_stage_b_outcomes,
)
from mneme.open_architecture.stage_b_relationship_diagnostic_experiment import (
    classify_target_form,
    parse_adr_alias,
)
from mneme.open_architecture.stage_b_relationship_treatment_experiment import (
    ARM_B_ID,
    ARM_B_RELATIONSHIPS_SCHEMA,
    ARM_B_SYSTEM_PROMPT_EXTENSION,
    BASE_SYSTEM_PROMPT_TEMPLATE,
    FROZEN_CLASSIFIER_BACKEND,
    FROZEN_CLASSIFIER_VERSION,
    FROZEN_MAX_RETRIES,
    FROZEN_MAX_TOKENS,
    FROZEN_MODEL_IDENTIFIER,
    FROZEN_TAXONOMY_VERSION,
    FROZEN_TIMEOUT_SECONDS,
    USER_PROMPT_TEMPLATE,
    compute_treatment_semantic_content_hash,
    load_treatment_outcomes,
    reference_decision_to_record_dict,
)

EXPERIMENT_ID: str = "b-t1d-relationship-selectivity"
ARM_D_ID: str = "treatment_d"

FROZEN_PARENT_MAIN_SHA: str = "90534104a1c517a33088c6139b98df4734672679"
FROZEN_EXECUTION_REFERENCE_CORPUS_HASH: str = "700a569e24bf90707ba14ff65eea2ab5"
FROZEN_SCORING_REFERENCE_CORPUS_HASH: str = "700a569e24bf90707ba14ff65eea2ab5"
HISTORICAL_V01_REFERENCE_CORPUS_HASH: str = "0455bd66aae52551c35b37a63c2d185f"

CONTROL_ARM_B_PROFILE_HASH: str = "e4b6bad47ebcc290924782172fb96d8d"
CONTROL_ARM_B_OUTCOMES_SEMANTIC_HASH: str = (
    "sha256:778f05574d0e835fca893c216c4e240c15e0f30a11893812089dc691b3376092"
)

# ── Arm D Selectivity Treatment Extension ─────────────────────────────────────

FORMAL_RELATIONSHIP_EMISSION_GATE: str = (
    "Formal Relationship Emission Gate:\n"
    "- Before emitting any relationship, first determine whether the supplied evidence explicitly asserts a formal decision-to-decision relationship matching one of the relationship semantics defined below.\n"
    "- Mere mention, citation, indexing/cross-reference, shared context, implementation reuse, or historical reference is insufficient by itself.\n"
    "- Document location does not determine validity. Cross-reference metadata, lifecycle/history text, and ordinary narrative body text may contain valid relationship evidence only when the text itself explicitly asserts a formal relationship.\n"
    "- If no explicit formal relationship is asserted for a target, emit no relationship for that target."
)

ARM_D_SYSTEM_PROMPT_EXTENSION: str = (
    FORMAL_RELATIONSHIP_EMISSION_GATE
    + "\n\n"
    + ARM_B_SYSTEM_PROMPT_EXTENSION
)

ARM_D_RELATIONSHIPS_SCHEMA: dict[str, Any] = copy.deepcopy(ARM_B_RELATIONSHIPS_SCHEMA)

# ── Explicit Immutable Treatment Profile ──────────────────────────────────────

B_T1D_PROFILE_D: dict[str, Any] = {
    "experiment_id": EXPERIMENT_ID,
    "arm_id": ARM_D_ID,
    "parent_main_sha": FROZEN_PARENT_MAIN_SHA,
    "execution_reference_corpus_hash": FROZEN_EXECUTION_REFERENCE_CORPUS_HASH,
    "scoring_reference_corpus_hash": FROZEN_SCORING_REFERENCE_CORPUS_HASH,
    "historical_control_execution_corpus_hash": HISTORICAL_V01_REFERENCE_CORPUS_HASH,
    "control_arm_b_profile_hash": CONTROL_ARM_B_PROFILE_HASH,
    "control_arm_b_semantic_hash": CONTROL_ARM_B_OUTCOMES_SEMANTIC_HASH,
    "baseline_id": FROZEN_BASELINE_ID,
    "baseline_configuration_hash": FROZEN_BASELINE_CONFIG_HASH,
    "classifier_backend": FROZEN_CLASSIFIER_BACKEND,
    "classifier_version": FROZEN_CLASSIFIER_VERSION,
    "model_identifier": FROZEN_MODEL_IDENTIFIER,
    "taxonomy_version": FROZEN_TAXONOMY_VERSION,
    "request_parameters": {
        "max_tokens": FROZEN_MAX_TOKENS,
        "timeout": FROZEN_TIMEOUT_SECONDS,
        "max_retries": FROZEN_MAX_RETRIES,
        "explicit_temperature": None,
    },
    "structured_output_mechanism": {
        "type": "json_schema",
        "output_config_path": "output_config.format.schema",
    },
    "relationship_schema": ARM_D_RELATIONSHIPS_SCHEMA,
    "base_system_prompt_template": BASE_SYSTEM_PROMPT_TEMPLATE,
    "system_prompt_treatment": ARM_D_SYSTEM_PROMPT_EXTENSION,
    "user_prompt_template": USER_PROMPT_TEMPLATE,
    "task_population": "all_100_batch_01_relationship_tasks",
    "treatment_specific_differences": {
        "semantic_narrowing": True,
        "negative_target_boundaries": True,
        "empty_array_default": True,
        "experiment_local_type_disambiguation": True,
        "numeric_adr_target_formatting": True,
        "formal_relationship_emission_gate": True,
    },
    "scorer_boundary": {
        "authority": "harness._execute_stage_b_tasks_and_scoring",
        "scoring_corpus_hash": FROZEN_SCORING_REFERENCE_CORPUS_HASH,
        "mixed_replay_eval_count": 800,
        "b0_baseline_count": 700,
        "treatment_task_count": 100,
    },
    "model_capabilities": {
        "tools_enabled": False,
        "tool_choice": None,
    },
}


def compute_b_t1d_profile_hash(profile: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 digest binding experiment inputs and parameters."""
    payload = json.dumps(profile, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


B_T1D_PROFILE_D_HASH: str = compute_b_t1d_profile_hash(B_T1D_PROFILE_D)


# ── Provenance Sidecar ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BT1DProvenanceSidecar:
    """Durable execution provenance for B-T1D."""

    experiment_id: str
    arm_id: str
    treatment_profile_hash: str
    parent_main_sha: str
    execution_reference_corpus_hash: str
    scoring_reference_corpus_hash: str
    control_arm_b_profile_hash: str
    control_arm_b_semantic_hash: str
    classifier_backend: str
    classifier_version: str
    model_identifier: str
    taxonomy_version: str
    request_parameters: dict[str, Any]
    task_count: int
    actual_outcome_count: int
    treatment_semantic_content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# ── Reference Corpus Validation ───────────────────────────────────────────────


def compute_reference_corpus_hash_from_references(
    references: list[FrozenReferenceDecision],
) -> str:
    """Compute content hash directly from in-memory FrozenReferenceDecision list."""
    records = [reference_decision_to_record_dict(ref) for ref in references]
    return compute_reference_corpus_records_hash(records)


def validate_b_t1d_reference_corpus(
    references: list[FrozenReferenceDecision],
) -> str:
    """Validate reference corpus for B-T1D (strictly Batch 01 v0.2-grounding).

    Enforces:
    1. Exactly 100 reference decisions.
    2. Exact 100 reference candidate IDs matching frozen authority.
    3. Content hash matches FROZEN_SCORING_REFERENCE_CORPUS_HASH (700a569e...).
    4. Fails closed on v0.1 (0455bd66...) or any mutated corpus.
    """
    if len(references) != 100:
        raise ValueError(
            f"Reference corpus count mismatch for B-T1D: expected 100, got {len(references)}"
        )

    expected_ids = {r.reference_decision_id for r in references}
    if len(expected_ids) != 100:
        raise ValueError("Duplicate reference_decision_id detected in corpus")

    computed_hash = compute_reference_corpus_hash_from_references(references)
    if computed_hash != FROZEN_SCORING_REFERENCE_CORPUS_HASH:
        raise ValueError(
            f"Reference corpus content hash mismatch for B-T1D: "
            f"expected '{FROZEN_SCORING_REFERENCE_CORPUS_HASH}', got '{computed_hash}'"
        )
    return computed_hash


def reference_to_task_input_dict(ref: FrozenReferenceDecision) -> dict[str, Any]:
    """Extract classifier task input fields from a reference decision."""
    return {
        "candidate_id": ref.reference_decision_id,
        "repository_identifier": ref.repository,
        "repository_commit_sha": ref.repository_commit_sha,
        "raw_statement": ref.raw_evidence,
        "source_context": ref.raw_evidence,
        "source_path": ref.source_file,
        "source_location": ref.source_location,
        "taxonomy_version": FROZEN_TAXONOMY_VERSION,
    }


def validate_v01_v02_input_invariance(
    v01_refs: list[FrozenReferenceDecision],
    v02_refs: list[FrozenReferenceDecision],
) -> None:
    """Prove deterministically that v0.1 and v0.2 have identical classifier inputs and exactly one label difference."""
    if len(v01_refs) != 100 or len(v02_refs) != 100:
        raise ValueError("Both reference corpora must have exactly 100 decisions")

    m1 = {r.reference_decision_id: r for r in v01_refs}
    m2 = {r.reference_decision_id: r for r in v02_refs}
    if set(m1.keys()) != set(m2.keys()):
        raise ValueError("Reference candidate ID sets do not match between v0.1 and v0.2")

    approved_diff_id = "ref-gsa-agentic-coding-quickstart-005"

    for rid in sorted(m1.keys()):
        r1 = m1[rid]
        r2 = m2[rid]

        # Identical repository identifiers and commit SHAs
        assert r1.repository == r2.repository, f"Repository mismatch on {rid}"
        assert r1.repository_commit_sha == r2.repository_commit_sha, f"Commit SHA mismatch on {rid}"

        # Byte-identical raw evidence and source location
        assert r1.raw_evidence == r2.raw_evidence, f"raw_evidence mismatch on {rid}"
        assert r1.source_file == r2.source_file, f"source_file mismatch on {rid}"
        assert r1.source_location == r2.source_location, f"source_location mismatch on {rid}"

        # Non-relationship ground truth fields identical
        assert r1.normalized_decision == r2.normalized_decision, f"normalized_decision mismatch on {rid}"
        assert r1.classification == r2.classification, f"classification mismatch on {rid}"
        assert r1.authority_status == r2.authority_status, f"authority_status mismatch on {rid}"
        assert r1.authority_evidence == r2.authority_evidence, f"authority_evidence mismatch on {rid}"
        assert r1.effective_date == r2.effective_date, f"effective_date mismatch on {rid}"
        assert r1.expiration_if_any == r2.expiration_if_any, f"expiration_if_any mismatch on {rid}"
        assert r1.lifecycle_status == r2.lifecycle_status, f"lifecycle_status mismatch on {rid}"
        assert r1.supersedes == r2.supersedes, f"supersedes mismatch on {rid}"
        assert r1.superseded_by == r2.superseded_by, f"superseded_by mismatch on {rid}"
        assert r1.decision_domains == r2.decision_domains, f"decision_domains mismatch on {rid}"
        assert r1.decision_purposes == r2.decision_purposes, f"decision_purposes mismatch on {rid}"
        assert r1.enforcement_potential == r2.enforcement_potential, f"enforcement_potential mismatch on {rid}"
        assert r1.candidate_rule == r2.candidate_rule, f"candidate_rule mismatch on {rid}"
        assert r1.scopes == r2.scopes, f"scopes mismatch on {rid}"
        assert r1.sampling_category == r2.sampling_category, f"sampling_category mismatch on {rid}"

        # Classifier task inputs equivalence
        t1 = reference_to_task_input_dict(r1)
        t2 = reference_to_task_input_dict(r2)
        assert t1 == t2, f"Classifier task input mismatch on {rid}"

        # Exactly one approved label change
        if rid == approved_diff_id:
            assert len(r1.relationships) == 1, f"Expected 1 relationship in v0.1 for {approved_diff_id}"
            assert r1.relationships[0]["relationship_type"] == "refines"
            assert r1.relationships[0]["target_reference"] == "0026"
            assert len(r2.relationships) == 0, f"Expected 0 relationships in v0.2 for {approved_diff_id}"
        else:
            assert r1.relationships == r2.relationships, f"Unexpected relationship difference on {rid}"


# ── Task Building & Prompt Construction ───────────────────────────────────────


def build_batch_01_relationship_tasks(
    references: list[FrozenReferenceDecision],
) -> list[ClassifierTask]:
    """Construct exactly 100 relationship tasks strictly binding ref.raw_evidence."""
    tasks: list[ClassifierTask] = []
    for ref in sorted(references, key=lambda r: r.reference_decision_id):
        task = ClassifierTask(
            candidate_id=ref.reference_decision_id,
            task_type=ClassifierTaskType.RELATIONSHIPS,
            raw_statement=ref.raw_evidence,
            source_context=ref.raw_evidence,
            source_path=ref.source_file,
            source_location=ref.source_location,
            repository_identifier=ref.repository,
            repository_commit_sha=ref.repository_commit_sha,
            taxonomy_version=FROZEN_TAXONOMY_VERSION,
        )
        tasks.append(task)
    return tasks


def build_treatment_system_prompt(task: ClassifierTask) -> str:
    """Build the Arm D treatment system prompt."""
    base_prompt = BASE_SYSTEM_PROMPT_TEMPLATE.format(
        taxonomy_version=task.taxonomy_version
    )
    return base_prompt + "\n\n" + ARM_D_SYSTEM_PROMPT_EXTENSION


def build_treatment_user_prompt(task: ClassifierTask) -> str:
    """Build user prompt identical to B0/B-T1C contract."""
    return USER_PROMPT_TEMPLATE.format(
        task_type=task.task_type.value,
        repository_identifier=task.repository_identifier,
        repository_commit_sha=task.repository_commit_sha,
        source_path=task.source_path,
        source_location=task.source_location,
        raw_statement=task.raw_statement,
        source_context=task.source_context,
    )


def build_treatment_request_payload(task: ClassifierTask) -> dict[str, Any]:
    """Build complete JSON-serializable Anthropic API request payload for Arm D."""
    if task.task_type != ClassifierTaskType.RELATIONSHIPS:
        raise ValueError(
            f"B-T1D payload construction is only valid for ClassifierTaskType.RELATIONSHIPS, "
            f"got {task.task_type}"
        )

    system_prompt = build_treatment_system_prompt(task)
    user_prompt = build_treatment_user_prompt(task)

    return {
        "model": FROZEN_MODEL_IDENTIFIER,
        "max_tokens": FROZEN_MAX_TOKENS,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": user_prompt,
            }
        ],
        "output_config": {
            "format": {
                "type": "json_schema",
                "schema": ARM_D_RELATIONSHIPS_SCHEMA,
            }
        },
    }


# ── Classifier Adapter ────────────────────────────────────────────────────────


class TreatmentDClassifierAdapter(AnthropicClassifier):
    """Research adapter for Arm D execution with fail-closed safeguards."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = FROZEN_TIMEOUT_SECONDS,
        max_retries: int = FROZEN_MAX_RETRIES,
        client: Any | None = None,
        live: bool = False,
    ) -> None:
        super().__init__(
            model_identifier=FROZEN_MODEL_IDENTIFIER,
            classifier_version=FROZEN_CLASSIFIER_VERSION,
            api_key=api_key,
            max_tokens=FROZEN_MAX_TOKENS,
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )
        self._live = live
        self._arm_id = ARM_D_ID

    @property
    def arm_id(self) -> str:
        return self._arm_id

    @property
    def live(self) -> bool:
        return self._live

    def get_task_schema(self, task_type: ClassifierTaskType) -> dict[str, Any]:
        if task_type != ClassifierTaskType.RELATIONSHIPS:
            raise ValueError(
                f"Treatment classifier only permits ClassifierTaskType.RELATIONSHIPS, "
                f"got {task_type.value!r}"
            )
        return ARM_D_RELATIONSHIPS_SCHEMA

    def build_system_prompt(self, task: ClassifierTask) -> str:
        if task.task_type != ClassifierTaskType.RELATIONSHIPS:
            raise ValueError(
                f"Treatment classifier only permits ClassifierTaskType.RELATIONSHIPS, "
                f"got {task.task_type.value!r}"
            )
        return build_treatment_system_prompt(task)

    def build_request_payload(self, task: ClassifierTask) -> dict[str, Any]:
        if task.task_type != ClassifierTaskType.RELATIONSHIPS:
            raise ValueError(
                f"Treatment classifier only permits ClassifierTaskType.RELATIONSHIPS, "
                f"got {task.task_type.value!r}"
            )
        return build_treatment_request_payload(task)

    def execute(self, task: ClassifierTask) -> ClassifierResult:
        """Execute a single task with fail-closed safety."""
        if task.task_type != ClassifierTaskType.RELATIONSHIPS:
            raise ValueError(
                f"TreatmentDClassifierAdapter only permits ClassifierTaskType.RELATIONSHIPS, "
                f"got {task.task_type}"
            )

        if not self._live and self._client is None:
            raise RuntimeError(
                "Live model/API calls are strictly prohibited during pre-execution validation. "
                "Supply a static mock client or obtain explicit execution authorization."
            )

        return super().execute(task)

    def execute_batch(
        self,
        tasks: list[ClassifierTask],
    ) -> list[ClassifierResult]:
        """Execute all tasks sequentially without fail-open fallback."""
        results: list[ClassifierResult] = []
        for task in tasks:
            start = time.perf_counter()
            try:
                result = self.execute(task)
            except Exception as exc:
                result = ClassifierResult(
                    task_type=task.task_type,
                    backend_id=self.backend_id,
                    classifier_version=self.classifier_version,
                    model_identifier=self.model_identifier,
                    taxonomy_version=task.taxonomy_version,
                    candidate_id=task.candidate_id,
                    output={"error": str(exc)},
                    confidence=0.0,
                    latency_ms=(time.perf_counter() - start) * 1000.0,
                    cost_amount=None,
                    cost_currency=None,
                    escalated=True,
                    execution_id=f"error-{task.candidate_id}",
                )
            results.append(result)
        return results


# ── Mixed Stage B Outcomes Assembly ───────────────────────────────────────────


def build_mixed_stage_b_outcomes(
    frozen_b0_outcomes: list[FrozenClassifierOutcome],
    treatment_outcomes: list[FrozenClassifierOutcome],
) -> list[FrozenClassifierOutcome]:
    """Assemble mixed Stage B replay evaluation set: 700 B0 + 100 treatment outcomes."""
    if len(frozen_b0_outcomes) != 800:
        raise ValueError(
            f"Expected exactly 800 frozen B0 outcomes, got {len(frozen_b0_outcomes)}"
        )
    if len(treatment_outcomes) != 100:
        raise ValueError(
            f"Expected exactly 100 treatment relationship outcomes, got {len(treatment_outcomes)}"
        )

    treatment_candidates = {o.candidate_id for o in treatment_outcomes}
    if len(treatment_candidates) != 100:
        raise ValueError("Treatment outcomes contain duplicate or fewer than 100 candidate IDs")

    non_rel_b0 = [
        o for o in frozen_b0_outcomes
        if o.task_type != ClassifierTaskType.RELATIONSHIPS
    ]
    if len(non_rel_b0) != 700:
        raise ValueError(
            f"Expected 700 non-relationships B0 outcomes, got {len(non_rel_b0)}"
        )

    b0_rel_candidates = {
        o.candidate_id for o in frozen_b0_outcomes
        if o.task_type == ClassifierTaskType.RELATIONSHIPS
    }
    if treatment_candidates != b0_rel_candidates:
        missing = b0_rel_candidates - treatment_candidates
        extra = treatment_candidates - b0_rel_candidates
        raise ValueError(
            f"Treatment candidate IDs mismatch B0 relationship candidate set: "
            f"missing={missing}, extra={extra}"
        )

    for o in treatment_outcomes:
        if o.task_type != ClassifierTaskType.RELATIONSHIPS:
            raise ValueError(
                f"Treatment outcome {o.candidate_id} has invalid task_type {o.task_type}"
            )

    mixed = non_rel_b0 + list(treatment_outcomes)
    mixed.sort(key=lambda o: (o.candidate_id, o.task_type.value))
    return mixed


# ── B-T1D Scoring Wrapper ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class BT1DScoringResult:
    """Scoring result for B-T1D replay strictly bound to v0.2."""

    experiment_id: str
    arm_id: str
    scoring_reference_corpus_hash: str
    total_references: int
    total_outcomes: int
    composite_score: float
    strict_relationship_accuracy: float
    repository_scores: dict[str, Any]
    harness_raw_scores: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def score_b_t1d_replay(
    mixed_outcomes: list[FrozenClassifierOutcome],
    references: list[FrozenReferenceDecision],
    manifest: Manifest,
) -> BT1DScoringResult:
    """Score mixed Stage B replay delegating directly to harness._execute_stage_b_tasks_and_scoring.

    Does NOT modify historical stage_b_baseline.score_stage_b_outcomes().
    Binds the resulting scoring metadata strictly to v0.2.
    """
    v02_hash = validate_b_t1d_reference_corpus(references)

    if len(mixed_outcomes) != 800:
        raise ValueError(f"Expected exactly 800 mixed outcomes, got {len(mixed_outcomes)}")

    classifier = OfflineB0Classifier(mixed_outcomes)
    repo_scores: dict[str, Any] = {}
    composite_sum = 0.0
    rel_acc_sum = 0.0

    for repo_cfg in manifest.repositories:
        repo_refs = [r for r in references if r.repository == repo_cfg.github]
        if len(repo_refs) != 20:
            raise ValueError(f"Expected 20 references for '{repo_cfg.id}', got {len(repo_refs)}")

        harness_result = _execute_stage_b_tasks_and_scoring(
            repository_config=repo_cfg,
            references=repo_refs,
            classifier=classifier,
        )

        metrics = harness_result.metrics
        composite = sum(metrics[t] for t in STAGE_B_EVALUATED_TASKS) / 8.0
        repo_scores[repo_cfg.id] = {
            "repo_id": repo_cfg.id,
            "reference_count": len(repo_refs),
            "task_count": len(repo_refs) * 8,
            "composite_score": composite,
            "metrics": metrics,
        }
        composite_sum += composite
        rel_acc_sum += metrics.get("relationship_accuracy", 0.0)

    n_repos = len(manifest.repositories)
    avg_composite = composite_sum / n_repos if n_repos else 0.0
    avg_rel_acc = rel_acc_sum / n_repos if n_repos else 0.0

    return BT1DScoringResult(
        experiment_id=EXPERIMENT_ID,
        arm_id=ARM_D_ID,
        scoring_reference_corpus_hash=v02_hash,
        total_references=len(references),
        total_outcomes=len(mixed_outcomes),
        composite_score=avg_composite,
        strict_relationship_accuracy=avg_rel_acc,
        repository_scores=repo_scores,
        harness_raw_scores={
            k: {
                "composite_score": v["composite_score"],
                "metrics": v["metrics"],
                "reference_count": v["reference_count"],
                "task_count": v["task_count"],
            }
            for k, v in repo_scores.items()
        },
    )


# ── Control Recomputation Authority ───────────────────────────────────────────


def validate_treatment_provenance(
    sidecar: BT1DProvenanceSidecar,
    outcomes: list[FrozenClassifierOutcome],
    expected_reference_ids: set[str],
) -> None:
    """Validate B-T1D provenance sidecar against outcomes and frozen authorities fail-closed."""
    if sidecar.experiment_id != EXPERIMENT_ID:
        raise ValueError(
            f"Provenance experiment_id mismatch: expected {EXPERIMENT_ID!r}, got {sidecar.experiment_id!r}"
        )
    if sidecar.arm_id != ARM_D_ID:
        raise ValueError(
            f"Provenance arm_id mismatch: expected {ARM_D_ID!r}, got {sidecar.arm_id!r}"
        )
    if sidecar.treatment_profile_hash != B_T1D_PROFILE_D_HASH:
        raise ValueError(
            f"Provenance profile hash mismatch: expected {B_T1D_PROFILE_D_HASH!r}, "
            f"got {sidecar.treatment_profile_hash!r}"
        )
    if sidecar.parent_main_sha != FROZEN_PARENT_MAIN_SHA:
        raise ValueError(
            f"Provenance parent SHA mismatch: expected {FROZEN_PARENT_MAIN_SHA!r}, "
            f"got {sidecar.parent_main_sha!r}"
        )
    if sidecar.execution_reference_corpus_hash != FROZEN_EXECUTION_REFERENCE_CORPUS_HASH:
        raise ValueError(
            f"Provenance execution_reference_corpus_hash mismatch: expected {FROZEN_EXECUTION_REFERENCE_CORPUS_HASH!r}, "
            f"got {sidecar.execution_reference_corpus_hash!r}"
        )
    if sidecar.scoring_reference_corpus_hash != FROZEN_SCORING_REFERENCE_CORPUS_HASH:
        raise ValueError(
            f"Provenance scoring_reference_corpus_hash mismatch: expected {FROZEN_SCORING_REFERENCE_CORPUS_HASH!r}, "
            f"got {sidecar.scoring_reference_corpus_hash!r}"
        )
    if sidecar.control_arm_b_profile_hash != CONTROL_ARM_B_PROFILE_HASH:
        raise ValueError(
            f"Provenance control_arm_b_profile_hash mismatch: expected {CONTROL_ARM_B_PROFILE_HASH!r}, "
            f"got {sidecar.control_arm_b_profile_hash!r}"
        )
    if sidecar.control_arm_b_semantic_hash != CONTROL_ARM_B_OUTCOMES_SEMANTIC_HASH:
        raise ValueError(
            f"Provenance control_arm_b_semantic_hash mismatch: expected {CONTROL_ARM_B_OUTCOMES_SEMANTIC_HASH!r}, "
            f"got {sidecar.control_arm_b_semantic_hash!r}"
        )
    if sidecar.model_identifier != FROZEN_MODEL_IDENTIFIER:
        raise ValueError(
            f"Provenance model_identifier mismatch: expected {FROZEN_MODEL_IDENTIFIER!r}, "
            f"got {sidecar.model_identifier!r}"
        )
    if sidecar.classifier_backend != FROZEN_CLASSIFIER_BACKEND:
        raise ValueError(
            f"Provenance classifier_backend mismatch: expected {FROZEN_CLASSIFIER_BACKEND!r}, "
            f"got {sidecar.classifier_backend!r}"
        )
    if sidecar.classifier_version != FROZEN_CLASSIFIER_VERSION:
        raise ValueError(
            f"Provenance classifier_version mismatch: expected {FROZEN_CLASSIFIER_VERSION!r}, "
            f"got {sidecar.classifier_version!r}"
        )
    if sidecar.taxonomy_version != FROZEN_TAXONOMY_VERSION:
        raise ValueError(
            f"Provenance taxonomy_version mismatch: expected {FROZEN_TAXONOMY_VERSION!r}, "
            f"got {sidecar.taxonomy_version!r}"
        )
    if sidecar.task_count != 100:
        raise ValueError(
            f"Provenance task_count mismatch: expected 100, got {sidecar.task_count}"
        )
    if sidecar.actual_outcome_count != len(outcomes) or len(outcomes) != 100:
        raise ValueError(
            f"Provenance outcome count mismatch: expected 100, got {sidecar.actual_outcome_count} (outcomes: {len(outcomes)})"
        )
    computed_hash = compute_treatment_semantic_content_hash(outcomes)
    if sidecar.treatment_semantic_content_hash != computed_hash:
        raise ValueError(
            f"Provenance semantic content hash mismatch: expected {sidecar.treatment_semantic_content_hash!r}, "
            f"computed {computed_hash!r}"
        )
    observed_ids = {o.candidate_id for o in outcomes}
    if observed_ids != expected_reference_ids:
        missing = expected_reference_ids - observed_ids
        extra = observed_ids - expected_reference_ids
        errs = []
        if missing:
            errs.append(f"missing candidates: {sorted(missing)}")
        if extra:
            errs.append(f"unexpected candidates: {sorted(extra)}")
        raise ValueError(f"Provenance candidate set mismatch: {'; '.join(errs)}")


def capture_treatment_run(
    run_dir: Path | str,
    adapter: TreatmentDClassifierAdapter,
    references: list[FrozenReferenceDecision],
    force: bool = False,
) -> tuple[list[FrozenClassifierOutcome], BT1DProvenanceSidecar]:
    """Capture live treatment run with fail-closed safety and durable provenance sidecar."""
    rd = Path(run_dir)
    if rd.exists() and any(rd.iterdir()) and not force:
        raise FileExistsError(
            f"Treatment run directory {rd} exists and is non-empty; refusing overwrite."
        )

    # Validate reference corpus before any execution
    validate_b_t1d_reference_corpus(references)

    tasks = build_batch_01_relationship_tasks(references)
    raw_results = adapter.execute_batch(tasks)

    outcomes: list[FrozenClassifierOutcome] = []
    for res in raw_results:
        outcome = FrozenClassifierOutcome(
            backend_id=res.backend_id,
            candidate_id=res.candidate_id,
            classifier_version=res.classifier_version,
            confidence=res.confidence,
            cost_amount=res.cost_amount,
            cost_currency=res.cost_currency,
            created_at=getattr(res, "created_at", "2026-10-03T18:00:00Z"),
            escalated=res.escalated,
            execution_id=res.execution_id,
            latency_ms=res.latency_ms,
            model_identifier=res.model_identifier,
            output=res.output,
            run_id=f"b-t1d-{ARM_D_ID}",
            task_type=res.task_type,
            taxonomy_version=res.taxonomy_version,
        )
        outcomes.append(outcome)

    semantic_hash = compute_treatment_semantic_content_hash(outcomes)

    sidecar = BT1DProvenanceSidecar(
        experiment_id=EXPERIMENT_ID,
        arm_id=ARM_D_ID,
        treatment_profile_hash=B_T1D_PROFILE_D_HASH,
        parent_main_sha=FROZEN_PARENT_MAIN_SHA,
        execution_reference_corpus_hash=FROZEN_EXECUTION_REFERENCE_CORPUS_HASH,
        scoring_reference_corpus_hash=FROZEN_SCORING_REFERENCE_CORPUS_HASH,
        control_arm_b_profile_hash=CONTROL_ARM_B_PROFILE_HASH,
        control_arm_b_semantic_hash=CONTROL_ARM_B_OUTCOMES_SEMANTIC_HASH,
        classifier_backend=FROZEN_CLASSIFIER_BACKEND,
        classifier_version=FROZEN_CLASSIFIER_VERSION,
        model_identifier=FROZEN_MODEL_IDENTIFIER,
        taxonomy_version=FROZEN_TAXONOMY_VERSION,
        request_parameters={
            "max_tokens": FROZEN_MAX_TOKENS,
            "timeout": FROZEN_TIMEOUT_SECONDS,
            "max_retries": FROZEN_MAX_RETRIES,
            "explicit_temperature": None,
        },
        task_count=len(tasks),
        actual_outcome_count=len(outcomes),
        treatment_semantic_content_hash=semantic_hash,
    )

    rd.mkdir(parents=True, exist_ok=True)
    outcomes_file = rd / "outcomes.jsonl"
    provenance_file = rd / "provenance.json"

    lines = [
        json.dumps(dataclasses.asdict(o), sort_keys=True, separators=(",", ":"))
        for o in outcomes
    ]
    outcomes_file.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    provenance_file.write_bytes(
        (json.dumps(sidecar.to_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8")
    )

    return outcomes, sidecar


def load_treatment_run(
    run_dir: Path | str,
    expected_reference_ids: set[str] | list[str],
) -> tuple[list[FrozenClassifierOutcome], BT1DProvenanceSidecar]:
    """Load and validate captured treatment outcomes and provenance sidecar from run directory."""
    rd = Path(run_dir)
    outcomes_file = rd / "outcomes.jsonl"
    provenance_file = rd / "provenance.json"

    if not outcomes_file.is_file():
        raise FileNotFoundError(f"Outcomes file not found in run directory: {outcomes_file}")
    if not provenance_file.is_file():
        raise FileNotFoundError(f"Provenance file not found in run directory: {provenance_file}")

    expected_set = set(expected_reference_ids)
    outcomes = load_treatment_outcomes(outcomes_file, expected_reference_ids=expected_set)
    sidecar_data = json.loads(provenance_file.read_text(encoding="utf-8"))
    sidecar = BT1DProvenanceSidecar(**sidecar_data)
    validate_treatment_provenance(sidecar, outcomes, expected_set)
    return outcomes, sidecar


def recompute_arm_b_v02_control_metrics(
    v02_refs: list[FrozenReferenceDecision],
    arm_b_outcomes: list[FrozenClassifierOutcome],
    residual_artifact_path: Path,
) -> dict[str, Any]:
    """Deterministically assert and recompute all Arm B v0.2 control metrics from frozen evidence."""
    validate_b_t1d_reference_corpus(v02_refs)
    if len(arm_b_outcomes) != 100:
        raise ValueError(f"Expected 100 Arm B outcomes, got {len(arm_b_outcomes)}")

    b_hash = compute_treatment_semantic_content_hash(arm_b_outcomes)
    if b_hash != CONTROL_ARM_B_OUTCOMES_SEMANTIC_HASH:
        raise ValueError(
            f"Control Arm B outcome semantic hash mismatch: "
            f"expected {CONTROL_ARM_B_OUTCOMES_SEMANTIC_HASH}, got {b_hash}"
        )

    if not residual_artifact_path.is_file():
        raise FileNotFoundError(f"Missing residual error artifact: {residual_artifact_path}")

    decomp_data = json.loads(residual_artifact_path.read_text(encoding="utf-8"))

    # Assert exact required values from frozen artifact
    assert decomp_data["total_references"] == 100
    assert decomp_data["passing_references"] == 59
    assert decomp_data["failing_references"] == 41

    sc = decomp_data["structural_class_counts"]
    assert sc["EXPECTED_EMPTY_FALSE_POSITIVE"] == 32
    assert sc["PURE_TYPE_CONFUSION"] == 2
    assert sc["EXACT_EXPECTED_PLUS_EXTRAS"] == 3
    assert sc["TYPE_CONFUSION_PLUS_EXTRAS"] == 4

    ta = decomp_data["target_attribution_totals"]
    assert ta["total_expected_tuples"] == 18
    assert ta["target_entity_recovered_any_type"] == 18
    assert ta["exact_type_exact_target"] == 12
    assert ta["wrong_type_recovery"] == 6
    assert ta["conflicting_type_extra"] == 1

    pb = decomp_data["prediction_behaviour_aggregate_counts"]
    assert pb["extra_relationship"] == 105
    assert pb["depends_on_overproduction"] == 72
    assert pb["wrong_type_recovery"] == 6
    assert pb["target_boundary_anomaly"] == 2
    assert pb["conflicting_type_extra"] == 1

    # Extra-only evidence context counts (excluding 8 exact matches in failure set)
    extra_contexts: dict[str, int] = {}
    expected_empty_extra_count = 0

    for rec in decomp_data["failures"]:
        is_empty_fp = rec["reference_structural_class"] == "EXPECTED_EMPTY_FALSE_POSITIVE"
        for t in rec["per_tuple_diagnostics"]:
            if t["tuple_role"] in ("extra_tuple", "conflicting_type_extra", "wrong_type_target"):
                ctx = t["evidence_context_tag"]
                extra_contexts[ctx] = extra_contexts.get(ctx, 0) + 1
                if is_empty_fp:
                    expected_empty_extra_count += 1

    assert expected_empty_extra_count == 86, f"Expected 86 empty extras, got {expected_empty_extra_count}"
    assert sum(extra_contexts.values()) == 105, f"Expected 105 total extras, got {sum(extra_contexts.values())}"
    assert extra_contexts.get("narrative_body") == 58
    assert extra_contexts.get("contextual_related_metadata") == 31
    assert extra_contexts.get("lifecycle_revision_history") == 6
    assert extra_contexts.get("unresolved") == 10

    return {
        "strict_exact_references": 59,
        "total_references": 100,
        "expected_empty_references": 88,
        "expected_empty_exact": 56,
        "expected_empty_fp_references": 32,
        "expected_empty_extra_tuples": 86,
        "total_extra_tuples": 105,
        "target_entities_recovered": 18,
        "exact_type_exact_target": 12,
        "wrong_type_recovery": 6,
        "missing_target_entities": 0,
        "conflicting_type_extras": 1,
        "target_boundary_anomalies": 2,
        "extra_depends_on_tuples": 72,
        "extra_tuple_evidence_contexts": {
            "narrative_body": 58,
            "contextual_related_metadata": 31,
            "lifecycle_revision_history": 6,
            "unresolved": 10,
        },
    }

"""
mneme.open_architecture.stage_b_relationship_treatment_experiment — B-T1C Treatment Experiment.

Implements the research-only B-T1C relationship treatment scaffold for O1A Batch 01.

Background & Causal Hypotheses:
B-T1B identified a strong mismatch between the broad B0 relationship contract and
the narrow Batch 01 human relationship labels:
- B0 schema described target_reference as "Referenced document, decision, or technology"
  and relationships as "Relationships to other decisions or artifacts", prompting 415
  false-positive tuples across 86/87 expected-empty decisions (dominated by free text and paths).
- B0 showed that 18/19 expected target entities WERE recovered by the model, but 10/18
  were misclassified as 'depends_on' (an unconstrained semantic sink), while 8/18 suffered
  a surface representation mismatch ('ADR-0005' vs bare zero-padded '0005').
- B-T1C tests whether narrowing that classifier contract causally reduces over-generation
  and improves relationship typing.

Staged Experimental Design (A -> B):
- Arm A (Semantic Narrowing Only): Restricts extraction strictly to explicit formal
  decision-to-decision relationships. Excludes technologies, libraries, files, tools,
  and work items. Requires empty array [] when no formal relationship is stated. Provides
  experiment-local type disambiguation. Preserves unconstrained target formatting.
- Arm B (Semantic Narrowing + Canonical ADR Target Representation): Inherits Arm A
  byte-for-byte, adding strictly the instruction to emit 4-digit zero-padded numeric ADR
  identifiers ('0005') when the target is a numeric ADR.

Pre-Registered Hypotheses:
Arm A:
  H1: Expected-empty parsed relationship tuple count < 415.
  H2: Number of expected-empty references producing >= 1 parsed relationships < 86.
  H3: Correct-type ADR-alias recovery > 8.
  H4: Target-entity recovery remains 18 / 19 (preservation condition).
Arm B (relative to Arm A):
  B1: Exact (relationship_type, target_reference) recovery increases.
  B2: Strict frozen relationship accuracy across 100 references increases.
  B3: Target-entity recovery does not decrease from Arm A.
  B4: Expected-empty false-positive reference count and tuple count do not increase from Arm A.

Architecture & Boundary Invariants:
- Research-only sidecar: zero modifications to canonical DecisionRetriever, Enforcer,
  ConflictDetector, DecisionIndex, MemoryStore, or authority services.
- Zero modifications to frozen B0 baseline artifacts, reference corpus, or manifest.
- Single scoring authority: delegates to harness._execute_stage_b_tasks_and_scoring()
  via score_stage_b_outcomes() using mixed 800-outcome replay (700 B0 + 100 treatment).
- Zero live model/API calls in this apparatus setup phase.
- Deterministic profile hashing over canonical JSON.
"""

from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from mneme.open_architecture.classification import (
    ClassifierResult,
    ClassifierTask,
    ClassifierTaskType,
    SemanticClassifier,
    normalize_relationships,
)
from mneme.open_architecture.classifiers.anthropic import (
    AnthropicClassifier,
    AnthropicClassifierError,
    AnthropicMalformedResponseError,
)
from mneme.open_architecture.harness import (
    FROZEN_BASELINE_CONFIG_HASH,
    FROZEN_BASELINE_ID,
    FROZEN_REFERENCE_CORPUS_HASH,
    FrozenReferenceDecision,
    load_reference_corpus,
)
from mneme.open_architecture.manifest import Manifest
from mneme.open_architecture.schemas import VALID_RELATIONSHIP_TYPES
from mneme.open_architecture.stage_b_baseline import (
    FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH,
    FrozenClassifierOutcome,
    StageBBaselineEvaluationResult,
    load_stage_b_outcomes,
    score_stage_b_outcomes,
)
from mneme.open_architecture.stage_b_relationship_diagnostic_experiment import (
    DECOMP_EXACT_TYPE_ALIAS_TARGET,
    DECOMP_EXACT_TYPE_EXACT_TARGET,
    DECOMP_NORMALIZATION_FAILURE,
    DECOMP_TARGET_NOT_PREDICTED_AND_NOT_VISIBLE,
    DECOMP_TARGET_NOT_PREDICTED_BUT_VISIBLE,
    DECOMP_WRONG_TYPE_ALIAS_TARGET,
    EV_GROUNDING_ABSENT,
    EV_GROUNDING_LITERAL,
    EV_GROUNDING_NON_LITERAL,
    GROUNDING_ALIAS,
    GROUNDING_LITERAL,
    GROUNDING_UNSUPPORTED,
    ORDERED_DECOMPOSITION_CATEGORIES,
    ORDERED_TARGET_FORMS,
    TARGET_FORM_ADR,
    TARGET_FORM_BARE_IDENTIFIER,
    TARGET_FORM_FREE_TEXT,
    TARGET_FORM_NULL,
    TARGET_FORM_PACKAGE,
    TARGET_FORM_PATH,
    TARGET_FORM_REPO_OR_URL,
    TARGET_FORM_WORK_ITEM,
    ExpectedRelationshipDiagnostic,
    PopulationVolumeMetrics,
    PredictedRelationshipDiagnostic,
    ReferenceRelationshipAttributionDiagnostic,
    TargetAttributionSummary,
    classify_target_form,
    compute_population_volume_metrics,
    is_adr_visible_in_text,
    parse_adr_alias,
)

EXPERIMENT_ID: str = "b-t1c-relationship-treatment"
ARM_A_ID: str = "treatment_a"
ARM_B_ID: str = "treatment_b"
FROZEN_PARENT_MAIN_SHA: str = "16d2f757d33c0e23c7d8e0a78006daaaefb20097"

FROZEN_MODEL_IDENTIFIER: str = "claude-sonnet-4-6"
FROZEN_CLASSIFIER_BACKEND: str = "anthropic"
FROZEN_CLASSIFIER_VERSION: str = "0.1"
FROZEN_TAXONOMY_VERSION: str = "0.1"
FROZEN_MAX_TOKENS: int = 1024
FROZEN_TIMEOUT_SECONDS: float = 60.0
FROZEN_MAX_RETRIES: int = 2


# ── Treatment Schemas ─────────────────────────────────────────────────────────

ARM_A_RELATIONSHIPS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "DecisionRelationshipsOutput",
    "type": "object",
    "properties": {
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "relationship_type": {
                        "type": "string",
                        "enum": sorted(VALID_RELATIONSHIP_TYPES),
                    },
                    "target_reference": {
                        "type": ["string", "null"],
                        "description": (
                            "Identifier or title of the referenced architectural decision record "
                            "(ADR or formal decision document only). Do not emit technologies, "
                            "libraries, packages, files, or tools."
                        ),
                    },
                    "evidence_reference": {
                        "type": ["string", "null"],
                        "description": "Text evidence for this relationship",
                    },
                },
                "required": ["relationship_type"],
                "additionalProperties": False,
            },
            "description": (
                "Formal relationships between this architectural decision and other architectural decisions. "
                "Return an empty array [] if no formal decision-to-decision relationship is explicitly stated."
            ),
        },
    },
    "required": ["relationships"],
    "additionalProperties": False,
}

ARM_B_RELATIONSHIPS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "DecisionRelationshipsOutput",
    "type": "object",
    "properties": {
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "relationship_type": {
                        "type": "string",
                        "enum": sorted(VALID_RELATIONSHIP_TYPES),
                    },
                    "target_reference": {
                        "type": ["string", "null"],
                        "description": (
                            "Canonical zero-padded 4-digit numeric identifier of the referenced ADR "
                            "(e.g., '0005', '0012') when referencing a numeric ADR, or exact document title if unnumbered. "
                            "Do not include prefixes like 'ADR-', file paths, or file extensions."
                        ),
                    },
                    "evidence_reference": {
                        "type": ["string", "null"],
                        "description": "Text evidence for this relationship",
                    },
                },
                "required": ["relationship_type"],
                "additionalProperties": False,
            },
            "description": (
                "Formal relationships between this architectural decision and other architectural decisions. "
                "Return an empty array [] if no formal decision-to-decision relationship is explicitly stated."
            ),
        },
    },
    "required": ["relationships"],
    "additionalProperties": False,
}


# ── Treatment System Prompt Templates ─────────────────────────────────────────

BASE_SYSTEM_PROMPT_TEMPLATE: str = (
    "You are an objective research semantic classifier for the Mneme Open Architecture Benchmark (Taxonomy {taxonomy_version}).\n"
    "Your sole function is to classify architectural decision evidence identified in open source repositories according to the research taxonomy.\n\n"
    "Core principles:\n"
    "- Classify the supplied repository evidence objectively based ONLY on what the document content and surrounding context state.\n"
    "- Do NOT decide what should be enforced or promote any candidate into project authority.\n"
    "- 'explicitly_accepted' means the source repository evidence indicates the project maintainers accepted this decision. It does NOT grant canonical Mneme authority.\n"
    "- For lifecycle: establish 'lifecycle' status. If the evidence explicitly mentions superseded decisions, superseding decisions, effective date, or expiration date, populate those fields; otherwise return null for each of them. Never invent dates or lineage not explicitly stated in the evidence.\n"
    "- Output MUST conform strictly to the requested JSON schema.\n"
    "- Do NOT include chain-of-thought, reasoning steps, or conversational commentary."
)

ARM_A_SYSTEM_PROMPT_EXTENSION: str = (
    "Task Guidance for Relationships (B-T1C treatment semantics):\n"
    "- Extract ONLY explicit formal relationships between this architectural decision and another architectural decision (such as an ADR).\n"
    "- Prohibited targets: NEVER emit relationships for programming languages, technologies, third-party libraries, packages, source files, directory paths, tools, external services, cloud resources, components, work items, pull requests, issue numbers, or generic architectural concepts.\n"
    "- Strict default: If the evidence does not explicitly record a formal relationship to another architectural decision, return an empty array []. Mentions or technical usage of a tool or library do NOT constitute an architectural relationship.\n"
    "- Relationship type definitions (B-T1C treatment semantics):\n"
    "  * requires: This decision explicitly requires another architectural decision as a mandatory architectural prerequisite.\n"
    "  * refines: This decision explicitly specializes, extends, adapts, or elaborates the rules of another architectural decision.\n"
    "  * supersedes: This decision explicitly replaces, repeals, or renders obsolete an earlier architectural decision.\n"
    "  * prohibits: This decision explicitly forbids an architectural choice established in another decision.\n"
    "  * conflicts_with: This decision is explicitly incompatible with another architectural decision.\n"
    "  * exception_to: This decision is explicitly an authorized exception or carve-out from another architectural decision.\n"
    "  * depends_on: Use ONLY when the evidence explicitly states a formal decision-level dependency that is not an architectural prerequisite (requires), specialization (refines), or replacement (supersedes)."
)

ARM_B_SYSTEM_PROMPT_EXTENSION: str = (
    ARM_A_SYSTEM_PROMPT_EXTENSION
    + "\n\n"
    + "Target representation rules (B-T1C treatment semantics):\n"
    "- When the target decision is an Architectural Decision Record (ADR) identified by a number in the evidence, output ONLY the 4-digit zero-padded numeric identifier (e.g., \"0005\", \"0012\", \"0027\").\n"
    "- Do NOT include prefixes (e.g., write \"0005\", not \"ADR-0005\" or \"ADR 0005\").\n"
    "- Do NOT include filenames or paths (e.g., write \"0002\", not \"0002-postgres.md\" or \"docs/adr/0002.md\")."
)

USER_PROMPT_TEMPLATE: str = (
    "Task: {task_type}\n"
    "Repository: {repository_identifier} @ {repository_commit_sha}\n"
    "Source file: {source_path} ({source_location})\n\n"
    "Extracted statement:\n"
    "\"\"\"\n{raw_statement}\n\"\"\"\n\n"
    "Surrounding document context:\n"
    "\"\"\"\n{source_context}\n\"\"\"\n\n"
    "Classify this architectural evidence according to the schema for '{task_type}'."
)


# ── Explicit Immutable Treatment Profiles ─────────────────────────────────────

B_T1C_PROFILE_A: dict[str, Any] = {
    "experiment_id": EXPERIMENT_ID,
    "arm_id": ARM_A_ID,
    "parent_main_sha": FROZEN_PARENT_MAIN_SHA,
    "baseline_id": FROZEN_BASELINE_ID,
    "baseline_configuration_hash": FROZEN_BASELINE_CONFIG_HASH,
    "reference_corpus_hash": FROZEN_REFERENCE_CORPUS_HASH,
    "frozen_b0_semantic_hash": FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH,
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
    "relationship_schema": ARM_A_RELATIONSHIPS_SCHEMA,
    "system_prompt_treatment": ARM_A_SYSTEM_PROMPT_EXTENSION,
    "user_prompt_template": USER_PROMPT_TEMPLATE,
    "task_population": "all_100_batch_01_relationship_tasks",
    "treatment_specific_differences": {
        "semantic_narrowing": True,
        "negative_target_boundaries": True,
        "empty_array_default": True,
        "experiment_local_type_disambiguation": True,
        "numeric_adr_target_formatting": False,
    },
    "scorer_boundary": {
        "authority": "harness._execute_stage_b_tasks_and_scoring",
        "composite_helper": "score_stage_b_outcomes",
        "metric_name": "relationship_accuracy",
    },
    "model_capabilities": {
        "tools_enabled": False,
        "web_access": False,
        "repo_access": False,
    },
}

B_T1C_PROFILE_B: dict[str, Any] = {
    "experiment_id": EXPERIMENT_ID,
    "arm_id": ARM_B_ID,
    "parent_main_sha": FROZEN_PARENT_MAIN_SHA,
    "baseline_id": FROZEN_BASELINE_ID,
    "baseline_configuration_hash": FROZEN_BASELINE_CONFIG_HASH,
    "reference_corpus_hash": FROZEN_REFERENCE_CORPUS_HASH,
    "frozen_b0_semantic_hash": FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH,
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
    "relationship_schema": ARM_B_RELATIONSHIPS_SCHEMA,
    "system_prompt_treatment": ARM_B_SYSTEM_PROMPT_EXTENSION,
    "user_prompt_template": USER_PROMPT_TEMPLATE,
    "task_population": "all_100_batch_01_relationship_tasks",
    "treatment_specific_differences": {
        "semantic_narrowing": True,
        "negative_target_boundaries": True,
        "empty_array_default": True,
        "experiment_local_type_disambiguation": True,
        "numeric_adr_target_formatting": True,
    },
    "scorer_boundary": {
        "authority": "harness._execute_stage_b_tasks_and_scoring",
        "composite_helper": "score_stage_b_outcomes",
        "metric_name": "relationship_accuracy",
    },
    "model_capabilities": {
        "tools_enabled": False,
        "web_access": False,
        "repo_access": False,
    },
}


def compute_b_t1c_profile_hash(profile: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 (32 hex) over canonical JSON profile representation."""
    canonical_json = json.dumps(profile, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:32]


B_T1C_PROFILE_A_HASH: str = compute_b_t1c_profile_hash(B_T1C_PROFILE_A)
B_T1C_PROFILE_B_HASH: str = compute_b_t1c_profile_hash(B_T1C_PROFILE_B)


# ── Request Construction Functions ───────────────────────────────────────────

def build_treatment_system_prompt(task: ClassifierTask, arm: str) -> str:
    """Construct full system prompt with base research boundary and arm-specific treatment."""
    base = BASE_SYSTEM_PROMPT_TEMPLATE.format(taxonomy_version=task.taxonomy_version)
    if arm == ARM_A_ID:
        extension = ARM_A_SYSTEM_PROMPT_EXTENSION
    elif arm == ARM_B_ID:
        extension = ARM_B_SYSTEM_PROMPT_EXTENSION
    else:
        raise ValueError(f"Unknown treatment arm: {arm!r}. Must be {ARM_A_ID!r} or {ARM_B_ID!r}")
    return f"{base}\n\n{extension}"


def build_treatment_user_prompt(task: ClassifierTask) -> str:
    """Construct deterministic user prompt matching frozen B0 contract."""
    return USER_PROMPT_TEMPLATE.format(
        task_type=task.task_type.value,
        repository_identifier=task.repository_identifier,
        repository_commit_sha=task.repository_commit_sha,
        source_path=task.source_path,
        source_location=task.source_location,
        raw_statement=task.raw_statement,
        source_context=task.source_context,
    )


def build_treatment_request_payload(
    task: ClassifierTask,
    arm: str,
) -> dict[str, Any]:
    """Construct deterministic request payload for Anthropic Messages API.
    
    Invariants:
    - Task type must be ClassifierTaskType.RELATIONSHIPS.
    - Model is claude-sonnet-4-6.
    - Max tokens is strictly 1024.
    - Temperature parameter is explicitly absent.
    - Structured output configured via output_config.format.
    """
    if task.task_type != ClassifierTaskType.RELATIONSHIPS:
        raise ValueError(
            f"Treatment request construction only valid for ClassifierTaskType.RELATIONSHIPS, "
            f"got {task.task_type.value!r}"
        )

    if arm == ARM_A_ID:
        schema = ARM_A_RELATIONSHIPS_SCHEMA
    elif arm == ARM_B_ID:
        schema = ARM_B_RELATIONSHIPS_SCHEMA
    else:
        raise ValueError(f"Unknown treatment arm: {arm!r}. Must be {ARM_A_ID!r} or {ARM_B_ID!r}")

    system_prompt = build_treatment_system_prompt(task, arm)
    user_prompt = build_treatment_user_prompt(task)

    return {
        "model": FROZEN_MODEL_IDENTIFIER,
        "max_tokens": FROZEN_MAX_TOKENS,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
        "output_config": {
            "format": {
                "type": "json_schema",
                "schema": schema,
            }
        },
    }


# ── Task Building & Validation ────────────────────────────────────────────────

def build_batch_01_relationship_tasks(
    references: list[FrozenReferenceDecision],
) -> list[ClassifierTask]:
    """Build the exact 100 relationship tasks from Batch 01 reference decisions.
    
    Invariants:
    - Binds strictly ClassifierTaskType.RELATIONSHIPS.
    - raw_statement and source_context are both ref.raw_evidence.
    - Exactly 100 tasks returned.
    """
    tasks: list[ClassifierTask] = []
    for ref in references:
        tasks.append(
            ClassifierTask(
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
        )

    if len(tasks) != 100:
        raise ValueError(f"Expected exactly 100 relationship tasks, got {len(tasks)}")
    return tasks


# ── Outcome Serialization & Semantic Hashing ──────────────────────────────────

def compute_treatment_semantic_content_hash(
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


def load_treatment_outcomes(
    path: Path | str,
    expected_reference_ids: set[str] | list[str] | None = None,
) -> list[FrozenClassifierOutcome]:
    """Load and strictly validate treatment relationship outcomes from JSONL.

    Fails closed if:
    - File does not exist.
    - Outcome count != 100.
    - Any outcome has task_type != ClassifierTaskType.RELATIONSHIPS.
    - Any outcome has backend_id != 'anthropic'.
    - Any outcome has classifier_version != '0.1'.
    - Any outcome has model_identifier != 'claude-sonnet-4-6'.
    - Any outcome has taxonomy_version != '0.1'.
    - Duplicate candidate_ids exist.
    - Candidate IDs do not match expected_reference_ids (when provided).
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Treatment outcomes file not found: {p}")

    outcomes: list[FrozenClassifierOutcome] = []
    seen_ids: set[str] = set()

    for line_num, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        t_type = ClassifierTaskType(data["task_type"])
        if t_type != ClassifierTaskType.RELATIONSHIPS:
            raise ValueError(
                f"Line {line_num}: Expected task_type 'relationships', got {t_type.value!r}"
            )
        b_id = str(data.get("backend_id"))
        if b_id != FROZEN_CLASSIFIER_BACKEND:
            raise ValueError(
                f"Line {line_num}: Expected backend_id {FROZEN_CLASSIFIER_BACKEND!r}, got {b_id!r}"
            )
        c_ver = str(data.get("classifier_version"))
        if c_ver != FROZEN_CLASSIFIER_VERSION:
            raise ValueError(
                f"Line {line_num}: Expected classifier_version {FROZEN_CLASSIFIER_VERSION!r}, got {c_ver!r}"
            )
        m_id = str(data.get("model_identifier"))
        if m_id != FROZEN_MODEL_IDENTIFIER:
            raise ValueError(
                f"Line {line_num}: Expected model_identifier {FROZEN_MODEL_IDENTIFIER!r}, got {m_id!r}"
            )
        tax_ver = str(data.get("taxonomy_version"))
        if tax_ver != FROZEN_TAXONOMY_VERSION:
            raise ValueError(
                f"Line {line_num}: Expected taxonomy_version {FROZEN_TAXONOMY_VERSION!r}, got {tax_ver!r}"
            )

        cand_id = str(data["candidate_id"])
        if cand_id in seen_ids:
            raise ValueError(f"Line {line_num}: Duplicate candidate_id {cand_id!r}")
        seen_ids.add(cand_id)

        outcome = FrozenClassifierOutcome.from_dict(data)
        outcomes.append(outcome)

    if len(outcomes) != 100:
        raise ValueError(f"Expected exactly 100 treatment outcomes, got {len(outcomes)}")

    if expected_reference_ids is not None:
        expected_set = set(expected_reference_ids)
        if seen_ids != expected_set:
            missing = expected_set - seen_ids
            extra = seen_ids - expected_set
            errs = []
            if missing:
                errs.append(f"missing candidates: {sorted(missing)}")
            if extra:
                errs.append(f"unexpected candidates: {sorted(extra)}")
            raise ValueError(f"Treatment outcome candidate set mismatch: {'; '.join(errs)}")

    outcomes.sort(key=lambda o: o.candidate_id)
    return outcomes


# ── Provenance Sidecar & Validation ───────────────────────────────────────────

@dataclass(frozen=True)
class TreatmentProvenanceSidecar:
    """Durable provenance sidecar bound to captured treatment outcomes."""

    experiment_id: str
    arm_id: str
    treatment_profile_hash: str
    parent_main_sha: str
    baseline_id: str
    baseline_configuration_hash: str
    reference_corpus_hash: str
    frozen_b0_semantic_hash: str
    model_identifier: str
    classifier_backend: str
    classifier_version: str
    taxonomy_version: str
    max_tokens: int
    timeout: float
    max_retries: int
    explicit_temperature: Any | None
    expected_logical_task_count: int
    actual_outcome_count: int
    treatment_semantic_content_hash: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "actual_outcome_count": self.actual_outcome_count,
            "arm_id": self.arm_id,
            "baseline_configuration_hash": self.baseline_configuration_hash,
            "baseline_id": self.baseline_id,
            "classifier_backend": self.classifier_backend,
            "classifier_version": self.classifier_version,
            "created_at": self.created_at,
            "expected_logical_task_count": self.expected_logical_task_count,
            "experiment_id": self.experiment_id,
            "explicit_temperature": self.explicit_temperature,
            "frozen_b0_semantic_hash": self.frozen_b0_semantic_hash,
            "max_retries": self.max_retries,
            "max_tokens": self.max_tokens,
            "model_identifier": self.model_identifier,
            "parent_main_sha": self.parent_main_sha,
            "reference_corpus_hash": self.reference_corpus_hash,
            "taxonomy_version": self.taxonomy_version,
            "timeout": self.timeout,
            "treatment_profile_hash": self.treatment_profile_hash,
            "treatment_semantic_content_hash": self.treatment_semantic_content_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TreatmentProvenanceSidecar:
        return cls(
            actual_outcome_count=int(data["actual_outcome_count"]),
            arm_id=str(data["arm_id"]),
            baseline_configuration_hash=str(data["baseline_configuration_hash"]),
            baseline_id=str(data["baseline_id"]),
            classifier_backend=str(data["classifier_backend"]),
            classifier_version=str(data["classifier_version"]),
            created_at=str(data["created_at"]),
            expected_logical_task_count=int(data["expected_logical_task_count"]),
            experiment_id=str(data["experiment_id"]),
            explicit_temperature=data.get("explicit_temperature"),
            frozen_b0_semantic_hash=str(data["frozen_b0_semantic_hash"]),
            max_retries=int(data["max_retries"]),
            max_tokens=int(data["max_tokens"]),
            model_identifier=str(data["model_identifier"]),
            parent_main_sha=str(data["parent_main_sha"]),
            reference_corpus_hash=str(data["reference_corpus_hash"]),
            taxonomy_version=str(data["taxonomy_version"]),
            timeout=float(data["timeout"]),
            treatment_profile_hash=str(data["treatment_profile_hash"]),
            treatment_semantic_content_hash=str(data["treatment_semantic_content_hash"]),
        )


def validate_treatment_provenance(
    sidecar: TreatmentProvenanceSidecar,
    outcomes: list[FrozenClassifierOutcome],
    expected_arm: str,
    expected_reference_ids: set[str],
) -> None:
    """Validate treatment provenance sidecar against outcomes and frozen authorities fail-closed."""
    if sidecar.experiment_id != EXPERIMENT_ID:
        raise ValueError(
            f"Provenance experiment_id mismatch: expected {EXPERIMENT_ID!r}, got {sidecar.experiment_id!r}"
        )
    if sidecar.arm_id != expected_arm:
        raise ValueError(
            f"Provenance arm_id mismatch: expected {expected_arm!r}, got {sidecar.arm_id!r}"
        )
    expected_profile_hash = (
        B_T1C_PROFILE_A_HASH if expected_arm == ARM_A_ID else B_T1C_PROFILE_B_HASH
    )
    if sidecar.treatment_profile_hash != expected_profile_hash:
        raise ValueError(
            f"Provenance profile hash mismatch: expected {expected_profile_hash!r}, "
            f"got {sidecar.treatment_profile_hash!r}"
        )
    if sidecar.parent_main_sha != FROZEN_PARENT_MAIN_SHA:
        raise ValueError(
            f"Provenance parent SHA mismatch: expected {FROZEN_PARENT_MAIN_SHA!r}, "
            f"got {sidecar.parent_main_sha!r}"
        )
    if sidecar.baseline_id != FROZEN_BASELINE_ID:
        raise ValueError(
            f"Provenance baseline_id mismatch: expected {FROZEN_BASELINE_ID!r}, "
            f"got {sidecar.baseline_id!r}"
        )
    if sidecar.baseline_configuration_hash != FROZEN_BASELINE_CONFIG_HASH:
        raise ValueError(
            f"Provenance baseline_config_hash mismatch: expected {FROZEN_BASELINE_CONFIG_HASH!r}, "
            f"got {sidecar.baseline_configuration_hash!r}"
        )
    if sidecar.reference_corpus_hash != FROZEN_REFERENCE_CORPUS_HASH:
        raise ValueError(
            f"Provenance reference_corpus_hash mismatch: expected {FROZEN_REFERENCE_CORPUS_HASH!r}, "
            f"got {sidecar.reference_corpus_hash!r}"
        )
    if sidecar.frozen_b0_semantic_hash != FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH:
        raise ValueError(
            f"Provenance frozen_b0_semantic_hash mismatch: expected {FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH!r}, "
            f"got {sidecar.frozen_b0_semantic_hash!r}"
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
    if sidecar.max_tokens != FROZEN_MAX_TOKENS:
        raise ValueError(
            f"Provenance max_tokens mismatch: expected {FROZEN_MAX_TOKENS}, got {sidecar.max_tokens}"
        )
    if sidecar.timeout != FROZEN_TIMEOUT_SECONDS:
        raise ValueError(
            f"Provenance timeout mismatch: expected {FROZEN_TIMEOUT_SECONDS}, got {sidecar.timeout}"
        )
    if sidecar.max_retries != FROZEN_MAX_RETRIES:
        raise ValueError(
            f"Provenance max_retries mismatch: expected {FROZEN_MAX_RETRIES}, got {sidecar.max_retries}"
        )
    if sidecar.explicit_temperature is not None:
        raise ValueError(
            f"Provenance explicit_temperature must be None, got {sidecar.explicit_temperature!r}"
        )
    if sidecar.expected_logical_task_count != 100:
        raise ValueError(
            f"Provenance expected_logical_task_count mismatch: expected 100, got {sidecar.expected_logical_task_count}"
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


def load_treatment_run(
    run_dir: Path | str,
    expected_arm: str,
    expected_reference_ids: set[str] | list[str],
) -> tuple[list[FrozenClassifierOutcome], TreatmentProvenanceSidecar]:
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
    sidecar = TreatmentProvenanceSidecar.from_dict(sidecar_data)
    validate_treatment_provenance(sidecar, outcomes, expected_arm, expected_set)
    return outcomes, sidecar


# ── Live Capture Scaffold (Pre-execution Authority) ───────────────────────────

def capture_treatment_run(
    output_dir: Path | str,
    arm: str,
    classifier: TreatmentClassifierAdapter,
    references: list[FrozenReferenceDecision],
    *,
    run_id: str | None = None,
) -> tuple[list[FrozenClassifierOutcome], TreatmentProvenanceSidecar]:
    """Execute treatment arm tasks and persist outcomes and provenance sidecar fail-closed.

    Invariants:
    - Verifies reference corpus (len == 100).
    - Refuses overwrite if output_dir contains existing outcomes.jsonl or provenance.json.
    - Executes exactly 100 relationship tasks in deterministic sorted order.
    - Captures valid results or explicit error/escalated results (never omits a task).
    - Preserves actual runtime execution metadata (latency, timestamp, execution_id).
    - Persists outcomes.jsonl and provenance.json.
    - Validates persisted provenance before returning.
    """
    if len(references) != 100:
        raise ValueError(f"Expected exactly 100 reference decisions, got {len(references)}")
    if arm not in (ARM_A_ID, ARM_B_ID):
        raise ValueError(f"Invalid treatment arm: {arm!r}. Must be {ARM_A_ID!r} or {ARM_B_ID!r}")
    if classifier.arm != arm:
        raise ValueError(
            f"Classifier arm mismatch: classifier configured for {classifier.arm!r}, capture requested {arm!r}"
        )

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    outcomes_file = out_path / "outcomes.jsonl"
    provenance_file = out_path / "provenance.json"

    if outcomes_file.exists() or provenance_file.exists():
        raise FileExistsError(
            f"Treatment run directory already contains artifacts; refusing overwrite: {out_path}"
        )

    effective_run_id = run_id or f"b-t1c-{arm}-{uuid.uuid4().hex[:12]}"
    tasks = build_batch_01_relationship_tasks(references)
    tasks.sort(key=lambda t: t.candidate_id)

    results = classifier.execute_batch(tasks)
    if len(results) != 100:
        raise RuntimeError(f"Expected 100 execution results, got {len(results)}")

    outcomes: list[FrozenClassifierOutcome] = []
    for r in results:
        outcome = FrozenClassifierOutcome(
            candidate_id=r.candidate_id,
            task_type=r.task_type,
            backend_id=r.backend_id,
            classifier_version=r.classifier_version,
            model_identifier=r.model_identifier,
            taxonomy_version=r.taxonomy_version,
            run_id=effective_run_id,
            execution_id=r.execution_id or f"exec-{uuid.uuid4().hex[:12]}",
            output=r.output,
            confidence=r.confidence,
            latency_ms=r.latency_ms,
            cost_amount=r.cost_amount,
            cost_currency=r.cost_currency,
            escalated=r.escalated,
            created_at=r.executed_at or datetime.now(timezone.utc).isoformat(),
        )
        outcomes.append(outcome)

    semantic_hash = compute_treatment_semantic_content_hash(outcomes)
    profile_hash = B_T1C_PROFILE_A_HASH if arm == ARM_A_ID else B_T1C_PROFILE_B_HASH

    sidecar = TreatmentProvenanceSidecar(
        actual_outcome_count=len(outcomes),
        arm_id=arm,
        baseline_configuration_hash=FROZEN_BASELINE_CONFIG_HASH,
        baseline_id=FROZEN_BASELINE_ID,
        classifier_backend=FROZEN_CLASSIFIER_BACKEND,
        classifier_version=FROZEN_CLASSIFIER_VERSION,
        created_at=datetime.now(timezone.utc).isoformat(),
        expected_logical_task_count=100,
        experiment_id=EXPERIMENT_ID,
        explicit_temperature=None,
        frozen_b0_semantic_hash=FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH,
        max_retries=FROZEN_MAX_RETRIES,
        max_tokens=FROZEN_MAX_TOKENS,
        model_identifier=FROZEN_MODEL_IDENTIFIER,
        parent_main_sha=FROZEN_PARENT_MAIN_SHA,
        reference_corpus_hash=FROZEN_REFERENCE_CORPUS_HASH,
        taxonomy_version=FROZEN_TAXONOMY_VERSION,
        timeout=FROZEN_TIMEOUT_SECONDS,
        treatment_profile_hash=profile_hash,
        treatment_semantic_content_hash=semantic_hash,
    )

    lines = [json.dumps(o.to_dict(), sort_keys=True) for o in outcomes]
    outcomes_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    provenance_file.write_text(
        json.dumps(sidecar.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ref_ids = {r.reference_decision_id for r in references}
    validate_treatment_provenance(sidecar, outcomes, arm, ref_ids)
    return outcomes, sidecar


# ── Mixed 800-Outcome Replay & Scoring Authority Delegation ───────────────────

def build_mixed_stage_b_outcomes(
    frozen_b0_outcomes: list[FrozenClassifierOutcome],
    treatment_outcomes: list[FrozenClassifierOutcome],
) -> list[FrozenClassifierOutcome]:
    """Combine 700 frozen B0 outcomes for tasks 1-6 & 8 with 100 treatment outcomes for task 7.

    Guarantees exact 1:1 replacement over the 100 candidate IDs:
    - Frozen B0 must contain exactly 100 relationship outcomes and 700 non-relationship outcomes.
    - Treatment outcomes must contain exactly 100 relationship outcomes.
    - Treatment candidate IDs must match the B0 relationship candidate IDs exactly (no missing, no extra).
    - Result contains exactly 800 outcomes.
    """
    if len(frozen_b0_outcomes) != 800:
        raise ValueError(f"Expected exactly 800 frozen B0 outcomes, got {len(frozen_b0_outcomes)}")

    untouched_b0 = [
        o for o in frozen_b0_outcomes
        if o.task_type != ClassifierTaskType.RELATIONSHIPS
    ]
    b0_relationships = [
        o for o in frozen_b0_outcomes
        if o.task_type == ClassifierTaskType.RELATIONSHIPS
    ]

    if len(untouched_b0) != 700:
        raise ValueError(
            f"Expected exactly 700 untouched B0 outcomes for non-relationship tasks, "
            f"got {len(untouched_b0)}"
        )
    if len(b0_relationships) != 100:
        raise ValueError(
            f"Expected exactly 100 B0 relationship outcomes to be replaced, "
            f"got {len(b0_relationships)}"
        )

    b0_rel_candidates = {o.candidate_id for o in b0_relationships}
    if len(b0_rel_candidates) != 100:
        raise ValueError(
            f"Expected 100 unique candidate IDs in B0 relationships, got {len(b0_rel_candidates)}"
        )

    if len(treatment_outcomes) != 100:
        raise ValueError(
            f"Expected exactly 100 treatment relationship outcomes, "
            f"got {len(treatment_outcomes)}"
        )

    treatment_candidates: set[str] = set()
    for o in treatment_outcomes:
        if o.task_type != ClassifierTaskType.RELATIONSHIPS:
            raise ValueError(
                f"Treatment outcome {o.candidate_id} has invalid task_type {o.task_type.value!r}"
            )
        treatment_candidates.add(o.candidate_id)

    if len(treatment_candidates) != 100:
        raise ValueError(
            f"Treatment outcomes contain duplicate candidate IDs; expected 100 unique, got {len(treatment_candidates)}"
        )

    missing = b0_rel_candidates - treatment_candidates
    extra = treatment_candidates - b0_rel_candidates
    if missing or extra:
        errs = []
        if missing:
            errs.append(f"missing candidates: {sorted(missing)}")
        if extra:
            errs.append(f"extra candidates: {sorted(extra)}")
        raise ValueError(
            f"Treatment candidate IDs do not match B0 relationship candidates: {'; '.join(errs)}"
        )

    mixed = untouched_b0 + treatment_outcomes
    if len(mixed) != 800:
        raise ValueError(f"Expected 800 mixed outcomes, got {len(mixed)}")

    mixed.sort(key=lambda o: (o.candidate_id, o.task_type.value))
    return mixed


def score_treatment_replay(
    mixed_outcomes: list[FrozenClassifierOutcome],
    references: list[FrozenReferenceDecision],
    manifest: Manifest,
) -> StageBBaselineEvaluationResult:
    """Score mixed 800-outcome evaluation set through existing Stage B scoring authority.
    
    Replays the 700 frozen B0 outcomes and 100 treatment relationship outcomes through
    the harness scoring authority, computing the B-T1C treatment composite score without
    altering frozen B0 constants.
    """
    return score_stage_b_outcomes(mixed_outcomes, references, manifest)


# ── Pre-Registered Hypotheses Evaluation ───────────────────────────────────────

@dataclass(frozen=True)
class ArmAHypothesisEvaluation:
    """Pre-registered hypothesis evaluation for Treatment Arm A."""

    h1_empty_tuples_below_415: bool
    h1_observed_empty_tuples: int
    h2_empty_refs_with_fp_below_86: bool
    h2_observed_empty_refs_with_fp: int
    h3_correct_type_alias_above_8: bool
    h3_observed_correct_type_alias: int
    h4_target_entity_recovery_preserved: bool
    h4_observed_target_entity_recovery: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "h1_empty_tuples_below_415": self.h1_empty_tuples_below_415,
            "h1_observed_empty_tuples": self.h1_observed_empty_tuples,
            "h2_empty_refs_with_fp_below_86": self.h2_empty_refs_with_fp_below_86,
            "h2_observed_empty_refs_with_fp": self.h2_observed_empty_refs_with_fp,
            "h3_correct_type_alias_above_8": self.h3_correct_type_alias_above_8,
            "h3_observed_correct_type_alias": self.h3_observed_correct_type_alias,
            "h4_target_entity_recovery_preserved": self.h4_target_entity_recovery_preserved,
            "h4_observed_target_entity_recovery": self.h4_observed_target_entity_recovery,
        }


@dataclass(frozen=True)
class TreatmentDiagnosticEvaluationResult:
    """Diagnostic evaluation over treatment outcomes reusing B-T1B taxonomy semantics."""

    arm: str
    profile_hash: str
    semantic_content_hash: str
    total_references: int
    total_predicted_tuples: int
    global_volume: PopulationVolumeMetrics
    expected_empty_volume: PopulationVolumeMetrics
    expected_non_empty_volume: PopulationVolumeMetrics
    target_attribution_summary: TargetAttributionSummary
    expected_target_records: list[ExpectedRelationshipDiagnostic]
    reference_diagnostics: list[ReferenceRelationshipAttributionDiagnostic]
    arm_a_hypotheses: ArmAHypothesisEvaluation | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "profile_hash": self.profile_hash,
            "semantic_content_hash": self.semantic_content_hash,
            "total_references": self.total_references,
            "total_predicted_tuples": self.total_predicted_tuples,
            "global_volume": self.global_volume.to_dict(),
            "expected_empty_volume": self.expected_empty_volume.to_dict(),
            "expected_non_empty_volume": self.expected_non_empty_volume.to_dict(),
            "target_attribution_summary": self.target_attribution_summary.to_dict(),
            "arm_a_hypotheses": self.arm_a_hypotheses.to_dict() if self.arm_a_hypotheses else None,
            "expected_target_records": [r.to_dict() for r in self.expected_target_records],
        }


def evaluate_treatment_diagnostics(
    treatment_outcomes: list[FrozenClassifierOutcome],
    references: list[FrozenReferenceDecision],
    manifest: Manifest,
    arm: str = ARM_A_ID,
) -> TreatmentDiagnosticEvaluationResult:
    """Evaluate diagnostic metrics over treatment relationship outcomes reusing B-T1B authorities."""
    if len(treatment_outcomes) != 100:
        raise ValueError(f"Expected 100 treatment outcomes, got {len(treatment_outcomes)}")
    if len(references) != 100:
        raise ValueError(f"Expected 100 references, got {len(references)}")

    refs_map: dict[str, FrozenReferenceDecision] = {
        r.reference_decision_id: r for r in references
    }
    profile_hash = (
        B_T1C_PROFILE_A_HASH if arm == ARM_A_ID else B_T1C_PROFILE_B_HASH
    )
    semantic_hash = compute_treatment_semantic_content_hash(treatment_outcomes)

    ref_diagnostics: list[ReferenceRelationshipAttributionDiagnostic] = []
    all_expected_records: list[ExpectedRelationshipDiagnostic] = []
    total_parsed_tuples = 0

    for outcome in sorted(treatment_outcomes, key=lambda o: o.candidate_id):
        ref_id = outcome.candidate_id
        if ref_id not in refs_map:
            raise KeyError(f"Outcome candidate {ref_id} not found in reference decisions")
        ref = refs_map[ref_id]

        raw_evidence = ref.raw_evidence

        is_failed = False
        err_msg: str | None = None
        norm_rels: tuple[Any, ...] = ()

        if "error" in outcome.output:
            is_failed = True
            err_msg = outcome.output["error"]
        else:
            raw_val = outcome.output.get("relationships", [])
            try:
                norm_rels = normalize_relationships(raw_val)
            except Exception as exc:
                is_failed = True
                err_msg = str(exc)

        pred_diags: list[PredictedRelationshipDiagnostic] = []

        if not is_failed:
            for r in norm_rels:
                total_parsed_tuples += 1
                rt = r.relationship_type
                tr = r.target_reference
                ev = r.evidence_reference
                tf = classify_target_form(tr)
                alias = parse_adr_alias(tr)

                if tr and str(tr) in raw_evidence:
                    tg = GROUNDING_LITERAL
                elif alias and is_adr_visible_in_text(alias, raw_evidence):
                    tg = GROUNDING_ALIAS
                else:
                    tg = GROUNDING_UNSUPPORTED

                if ev is None or not str(ev).strip():
                    eg = EV_GROUNDING_ABSENT
                elif str(ev) in raw_evidence:
                    eg = EV_GROUNDING_LITERAL
                else:
                    eg = EV_GROUNDING_NON_LITERAL

                pred_diags.append(
                    PredictedRelationshipDiagnostic(
                        relationship_type=rt,
                        target_reference=tr,
                        target_form=tf,
                        target_adr_alias=alias,
                        target_grounding=tg,
                        evidence_reference=ev,
                        evidence_reference_grounding=eg,
                    )
                )

        exp_diags: list[ExpectedRelationshipDiagnostic] = []
        if ref.relationships:
            pred_tuples = [(p.relationship_type, p.target_reference) for p in pred_diags]
            pred_alias_tuples = [(p.relationship_type, p.target_adr_alias) for p in pred_diags]

            for rel in ref.relationships:
                exp_t = str(rel["relationship_type"])
                exp_targ = rel.get("target_reference")
                exp_alias = parse_adr_alias(exp_targ)

                vis_exact = bool(exp_targ and str(exp_targ) in raw_evidence)
                vis_alias = is_adr_visible_in_text(exp_alias, raw_evidence)
                vis_classifier = vis_exact or vis_alias

                pred_exact = False
                pred_alias = False
                type_used: str | None = None

                if is_failed:
                    cat = DECOMP_NORMALIZATION_FAILURE
                elif (exp_t, exp_targ) in pred_tuples:
                    cat = DECOMP_EXACT_TYPE_EXACT_TARGET
                    pred_exact = True
                    pred_alias = True
                    type_used = exp_t
                elif any(pt == exp_t and pa == exp_alias for pt, pa in pred_alias_tuples if pa is not None):
                    cat = DECOMP_EXACT_TYPE_ALIAS_TARGET
                    pred_exact = False
                    pred_alias = True
                    type_used = exp_t
                elif any(pa == exp_alias for pt, pa in pred_alias_tuples if pa is not None):
                    cat = DECOMP_WRONG_TYPE_ALIAS_TARGET
                    pred_exact = False
                    pred_alias = True
                    for pt, pa in pred_alias_tuples:
                        if pa == exp_alias:
                            type_used = pt
                            break
                elif vis_classifier:
                    cat = DECOMP_TARGET_NOT_PREDICTED_BUT_VISIBLE
                else:
                    cat = DECOMP_TARGET_NOT_PREDICTED_AND_NOT_VISIBLE

                rec = ExpectedRelationshipDiagnostic(
                    reference_id=ref_id,
                    repository=ref.repository,
                    expected_relationship_type=exp_t,
                    expected_target_reference=exp_targ,
                    expected_canonical_adr=exp_alias,
                    classifier_visible_exact=vis_exact,
                    classifier_visible_alias=vis_alias,
                    classifier_visible=vis_classifier,
                    predicted_exact_tuple=pred_exact,
                    predicted_canonical_alias=pred_alias,
                    relationship_type_used_for_recovered_alias=type_used,
                    decomposition_category=cat,
                )
                exp_diags.append(rec)
                all_expected_records.append(rec)

        ref_diagnostics.append(
            ReferenceRelationshipAttributionDiagnostic(
                reference_id=ref_id,
                repository=ref.repository,
                sampling_category=ref.sampling_category,
                is_expected_empty=(len(ref.relationships) == 0),
                is_normalization_failure=is_failed,
                error_message=err_msg,
                expected_relationships=exp_diags,
                predicted_relationships=pred_diags,
                expected_tuple_count=len(ref.relationships),
                predicted_tuple_count=len(pred_diags),
            )
        )

    ref_diagnostics.sort(key=lambda d: d.reference_id)
    all_expected_records.sort(
        key=lambda r: (r.reference_id, r.expected_relationship_type, str(r.expected_target_reference))
    )

    global_vol = compute_population_volume_metrics(ref_diagnostics)
    empty_diags = [d for d in ref_diagnostics if d.is_expected_empty]
    non_empty_diags = [d for d in ref_diagnostics if not d.is_expected_empty]
    empty_vol = compute_population_volume_metrics(empty_diags)
    non_empty_vol = compute_population_volume_metrics(non_empty_diags)
    empty_refs_with_fp = sum(1 for d in empty_diags if d.predicted_tuple_count > 0)

    cat_counts: dict[str, int] = {}
    for r in all_expected_records:
        cat_counts[r.decomposition_category] = cat_counts.get(r.decomposition_category, 0) + 1

    tot_vis = sum(1 for r in all_expected_records if r.classifier_visible)
    tot_not_vis = sum(1 for r in all_expected_records if not r.classifier_visible)
    tot_recovered = sum(1 for r in all_expected_records if r.predicted_canonical_alias)
    corr_type_recovered = sum(
        1 for r in all_expected_records
        if r.decomposition_category in (DECOMP_EXACT_TYPE_EXACT_TARGET, DECOMP_EXACT_TYPE_ALIAS_TARGET)
    )
    wrong_type_recovered = sum(
        1 for r in all_expected_records if r.decomposition_category == DECOMP_WRONG_TYPE_ALIAS_TARGET
    )

    summary = TargetAttributionSummary(
        total_expected_tuples=len(all_expected_records),
        exact_type_exact_target=cat_counts.get(DECOMP_EXACT_TYPE_EXACT_TARGET, 0),
        exact_type_alias_target=cat_counts.get(DECOMP_EXACT_TYPE_ALIAS_TARGET, 0),
        wrong_type_alias_target=cat_counts.get(DECOMP_WRONG_TYPE_ALIAS_TARGET, 0),
        target_not_predicted_but_visible=cat_counts.get(DECOMP_TARGET_NOT_PREDICTED_BUT_VISIBLE, 0),
        target_not_predicted_and_not_visible=cat_counts.get(DECOMP_TARGET_NOT_PREDICTED_AND_NOT_VISIBLE, 0),
        normalization_failure=cat_counts.get(DECOMP_NORMALIZATION_FAILURE, 0),
        classifier_visible_target_count=tot_vis,
        not_classifier_visible_target_count=tot_not_vis,
        target_entity_recovered_any_type=tot_recovered,
        correct_type_target_recovered=corr_type_recovered,
        wrong_type_target_recovered=wrong_type_recovered,
    )

    arm_a_hypotheses: ArmAHypothesisEvaluation | None = None
    if arm == ARM_A_ID:
        arm_a_hypotheses = ArmAHypothesisEvaluation(
            h1_empty_tuples_below_415=(empty_vol.total_predicted_tuples < 415),
            h1_observed_empty_tuples=empty_vol.total_predicted_tuples,
            h2_empty_refs_with_fp_below_86=(empty_refs_with_fp < 86),
            h2_observed_empty_refs_with_fp=empty_refs_with_fp,
            h3_correct_type_alias_above_8=(corr_type_recovered > 8),
            h3_observed_correct_type_alias=corr_type_recovered,
            h4_target_entity_recovery_preserved=(tot_recovered == 18),
            h4_observed_target_entity_recovery=tot_recovered,
        )

    return TreatmentDiagnosticEvaluationResult(
        arm=arm,
        profile_hash=profile_hash,
        semantic_content_hash=semantic_hash,
        total_references=len(ref_diagnostics),
        total_predicted_tuples=total_parsed_tuples,
        global_volume=global_vol,
        expected_empty_volume=empty_vol,
        expected_non_empty_volume=non_empty_vol,
        target_attribution_summary=summary,
        expected_target_records=all_expected_records,
        reference_diagnostics=ref_diagnostics,
        arm_a_hypotheses=arm_a_hypotheses,
    )


# ── Treatment Classifier Adapter ──────────────────────────────────────────────

class TreatmentClassifierAdapter(AnthropicClassifier):
    """Research adapter for executing B-T1C treatment tasks, subclassing AnthropicClassifier.

    Inherits all validated Anthropic client construction, API-key handling, timeout, retry,
    response text extraction, JSON parsing, JSON Schema validation, and latency timing from
    AnthropicClassifier without duplicating them.

    Overrides:
    - Task guard: relationship-only tasks.
    - System prompt: treatment system prompt.
    - Request payload: treatment request payload with treatment schema.
    - get_task_schema: returns treatment schema.
    - Disabled by default (live=False) unless explicit live authorization is provided.
    - Accepts fake/static client for test verification.
    """

    def __init__(
        self,
        arm: str = ARM_A_ID,
        *,
        api_key: str | None = None,
        timeout: float = FROZEN_TIMEOUT_SECONDS,
        max_retries: int = FROZEN_MAX_RETRIES,
        client: Any | None = None,
        live: bool = False,
    ) -> None:
        if arm not in (ARM_A_ID, ARM_B_ID):
            raise ValueError(f"Invalid treatment arm: {arm!r}. Must be {ARM_A_ID!r} or {ARM_B_ID!r}")
        super().__init__(
            model_identifier=FROZEN_MODEL_IDENTIFIER,
            classifier_version=FROZEN_CLASSIFIER_VERSION,
            api_key=api_key,
            max_tokens=FROZEN_MAX_TOKENS,
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )
        self._arm = arm
        self._live = live

    @property
    def arm(self) -> str:
        return self._arm

    def get_task_schema(self, task_type: ClassifierTaskType) -> dict[str, Any]:
        if task_type != ClassifierTaskType.RELATIONSHIPS:
            raise ValueError(
                f"Treatment classifier only permits ClassifierTaskType.RELATIONSHIPS, "
                f"got {task_type.value!r}"
            )
        return ARM_A_RELATIONSHIPS_SCHEMA if self._arm == ARM_A_ID else ARM_B_RELATIONSHIPS_SCHEMA

    def build_system_prompt(self, task: ClassifierTask) -> str:
        if task.task_type != ClassifierTaskType.RELATIONSHIPS:
            raise ValueError(
                f"Treatment classifier only permits ClassifierTaskType.RELATIONSHIPS, "
                f"got {task.task_type.value!r}"
            )
        return build_treatment_system_prompt(task, self._arm)

    def build_request_payload(self, task: ClassifierTask) -> dict[str, Any]:
        if task.task_type != ClassifierTaskType.RELATIONSHIPS:
            raise ValueError(
                f"Treatment classifier only permits ClassifierTaskType.RELATIONSHIPS, "
                f"got {task.task_type.value!r}"
            )
        return build_treatment_request_payload(task, self._arm)

    def execute(self, task: ClassifierTask) -> ClassifierResult:
        if task.task_type != ClassifierTaskType.RELATIONSHIPS:
            raise ValueError(
                f"Treatment classifier only permits ClassifierTaskType.RELATIONSHIPS, "
                f"got {task.task_type.value!r}"
            )

        if not self._live and self._client is None:
            raise RuntimeError(
                "TreatmentClassifierAdapter called in non-live mode without a client. "
                "Live model/API calls are strictly prohibited in this phase."
            )

        return super().execute(task)

    def execute_batch(self, tasks: list[ClassifierTask]) -> list[ClassifierResult]:
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
                )
            results.append(result)
        return results

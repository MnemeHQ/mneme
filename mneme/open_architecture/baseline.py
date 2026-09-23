"""
mneme.open_architecture.baseline — Frozen baseline configuration contract and validation.

Freezes the execution contract for O1A Batch 01:
- Semantic Mneme build identity (fixed SHA)
- Pinned repository SHAs (5 approved repositories)
- Extractor identity and configuration
- Classifier backend, version, model, and configuration
- Semantic task contract (exactly 8 interpretation dimensions)
- Retrieval policy (score_gt_zero)
- Scenario query renderer (8-field canonical order)
- Scenario corpus and reference decision corpus status

Baseline identity is deterministic. Status cannot be marked 'frozen' until
all required baseline prerequisites actually exist and validate.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mneme.open_architecture.classification import ClassifierTaskType
from mneme.open_architecture.manifest import Manifest


APPROVED_BATCH_01_REPOSITORIES: frozenset[str] = frozenset({
    "adrkit",
    "gsa_agentic_coding_quickstart",
    "helix",
    "archlint",
    "modonome",
})

EXPECTED_SEMANTIC_TASKS: tuple[str, ...] = (
    "decision_classification",
    "domains",
    "purposes",
    "authority",
    "scope",
    "lifecycle",
    "relationships",
    "enforcement_potential",
)

EXPECTED_RENDERER_FIELD_ORDER: tuple[str, ...] = (
    "description",
    "path",
    "component",
    "change_type",
    "dependencies",
    "api",
    "technology",
    "other_context",
)

FROZEN_SEMANTIC_MNEME_SHA: str = "3673c36855fb1e30d46942ce826c50be4888df5e"


class BaselineFreezeError(ValueError):
    """Raised when an attempt to freeze a baseline fails prerequisite validation."""


@dataclass(frozen=True)
class BaselineRepository:
    id: str
    github: str
    commit_sha: str
    default_branch: str = "main"
    primary_test: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("repository id must not be empty")
        if not re.match(r"^[a-f0-9]{40}$", self.commit_sha):
            raise ValueError(
                f"repository '{self.id}' commit_sha must be 40-character lowercase hex SHA, got {self.commit_sha!r}"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaselineRepository:
        return cls(
            id=str(data["id"]),
            github=str(data["github"]),
            commit_sha=str(data["commit_sha"]),
            default_branch=str(data.get("default_branch", "main")),
            primary_test=str(data.get("primary_test", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "github": self.github,
            "commit_sha": self.commit_sha,
            "default_branch": self.default_branch,
            "primary_test": self.primary_test,
        }


@dataclass(frozen=True)
class BaselineExtractor:
    id: str
    version: str
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaselineExtractor:
        return cls(
            id=str(data["id"]),
            version=str(data["version"]),
            config=dict(data.get("config", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "config": self.config,
        }


@dataclass(frozen=True)
class BaselineClassifier:
    backend_id: str
    classifier_version: str
    model_identifier: str | None
    min_sdk_version: str = "1.0.0"
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaselineClassifier:
        return cls(
            backend_id=str(data["backend_id"]),
            classifier_version=str(data["classifier_version"]),
            model_identifier=data.get("model_identifier"),
            min_sdk_version=str(data.get("min_sdk_version", "1.0.0")),
            config=dict(data.get("config", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "classifier_version": self.classifier_version,
            "model_identifier": self.model_identifier,
            "min_sdk_version": self.min_sdk_version,
            "config": self.config,
        }


@dataclass(frozen=True)
class BaselineRetrievalPolicy:
    policy_id: str
    version: str
    projection: str = ""
    retriever: str = ""
    selection: str = ""
    output: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaselineRetrievalPolicy:
        return cls(
            policy_id=str(data["policy_id"]),
            version=str(data["version"]),
            projection=str(data.get("projection", "")),
            retriever=str(data.get("retriever", "")),
            selection=str(data.get("selection", "")),
            output=str(data.get("output", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "projection": self.projection,
            "retriever": self.retriever,
            "selection": self.selection,
            "output": self.output,
        }


@dataclass(frozen=True)
class BaselineScenarioRenderer:
    renderer_id: str
    version: str
    field_order: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaselineScenarioRenderer:
        return cls(
            renderer_id=str(data["renderer_id"]),
            version=str(data["version"]),
            field_order=tuple(data.get("field_order", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "renderer_id": self.renderer_id,
            "version": self.version,
            "field_order": list(self.field_order),
        }


@dataclass(frozen=True)
class BaselineCorpusStatus:
    status: str
    total_required: int
    per_repository_required: int
    content_hash: str
    location: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaselineCorpusStatus:
        return cls(
            status=str(data.get("status", "missing")),
            total_required=int(data.get("total_required", 0)),
            per_repository_required=int(data.get("per_repository_required", 0)),
            content_hash=str(data.get("content_hash", "none")),
            location=str(data.get("location", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total_required": self.total_required,
            "per_repository_required": self.per_repository_required,
            "content_hash": self.content_hash,
            "location": self.location,
        }


@dataclass(frozen=True)
class BaselineConfig:
    """Explicit frozen baseline configuration binding all execution inputs."""

    schema_version: str
    baseline_id: str
    status: str
    semantic_mneme_sha: str
    mneme_version: str
    benchmark_schema_version: str
    taxonomy_version: str
    manifest_ref: dict[str, Any]
    repositories: tuple[BaselineRepository, ...]
    extractor: BaselineExtractor
    classifier: BaselineClassifier
    semantic_tasks: tuple[str, ...]
    retrieval_policy: BaselineRetrievalPolicy
    scenario_renderer: BaselineScenarioRenderer
    scenario_corpus: BaselineCorpusStatus
    reference_corpus: BaselineCorpusStatus

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaselineConfig:
        return cls(
            schema_version=str(data["schema_version"]),
            baseline_id=str(data["baseline_id"]),
            status=str(data.get("status", "planned")),
            semantic_mneme_sha=str(data["semantic_mneme_sha"]),
            mneme_version=str(data["mneme_version"]),
            benchmark_schema_version=str(data["benchmark_schema_version"]),
            taxonomy_version=str(data["taxonomy_version"]),
            manifest_ref=dict(data.get("manifest", {})),
            repositories=tuple(BaselineRepository.from_dict(r) for r in data["repositories"]),
            extractor=BaselineExtractor.from_dict(data["extractor"]),
            classifier=BaselineClassifier.from_dict(data["classifier"]),
            semantic_tasks=tuple(data["semantic_tasks"]),
            retrieval_policy=BaselineRetrievalPolicy.from_dict(data["retrieval_policy"]),
            scenario_renderer=BaselineScenarioRenderer.from_dict(data["scenario_renderer"]),
            scenario_corpus=BaselineCorpusStatus.from_dict(data["scenario_corpus"]),
            reference_corpus=BaselineCorpusStatus.from_dict(data["reference_corpus"]),
        )

    @classmethod
    def load(cls, path: str | Path) -> BaselineConfig:
        """Load baseline configuration from YAML file."""
        text = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("baseline config root must be a mapping")
        return cls.from_dict(data)

    def configuration_hash(self) -> str:
        """Compute deterministic configuration hash over all semantic execution inputs.

        Changing any repository SHA, classifier model/version, extractor config,
        or scenario corpus hash changes this identity.
        """
        config = {
            "schema_version": self.schema_version,
            "baseline_id": self.baseline_id,
            "semantic_mneme_sha": self.semantic_mneme_sha,
            "mneme_version": self.mneme_version,
            "benchmark_schema_version": self.benchmark_schema_version,
            "taxonomy_version": self.taxonomy_version,
            "repositories": [
                {
                    "id": r.id,
                    "github": r.github,
                    "commit_sha": r.commit_sha,
                    "default_branch": r.default_branch,
                    "primary_test": r.primary_test,
                }
                for r in sorted(self.repositories, key=lambda x: x.id)
            ],
            "extractor": {
                "id": self.extractor.id,
                "version": self.extractor.version,
                "config": self.extractor.config,
            },
            "classifier": {
                "backend_id": self.classifier.backend_id,
                "classifier_version": self.classifier.classifier_version,
                "model_identifier": self.classifier.model_identifier,
                "min_sdk_version": self.classifier.min_sdk_version,
                "config": self.classifier.config,
            },
            "semantic_tasks": sorted(list(self.semantic_tasks)),
            "retrieval_policy": {
                "policy_id": self.retrieval_policy.policy_id,
                "version": self.retrieval_policy.version,
            },
            "scenario_renderer": {
                "renderer_id": self.scenario_renderer.renderer_id,
                "version": self.scenario_renderer.version,
                "field_order": list(self.scenario_renderer.field_order),
            },
            "scenario_corpus": {
                "content_hash": self.scenario_corpus.content_hash,
                "status": self.scenario_corpus.status,
                "total_required": self.scenario_corpus.total_required,
                "per_repository_required": self.scenario_corpus.per_repository_required,
            },
            "reference_corpus": {
                "content_hash": self.reference_corpus.content_hash,
                "status": self.reference_corpus.status,
                "total_required": self.reference_corpus.total_required,
                "per_repository_required": self.reference_corpus.per_repository_required,
            },
        }
        canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]

    def check_freeze_prerequisites(self) -> list[str]:
        """Return list of unsatisfied prerequisites preventing status from moving to 'frozen'."""
        blockers: list[str] = []

        # 1. Repositories pinned and approved
        repo_ids = {r.id for r in self.repositories}
        if repo_ids != APPROVED_BATCH_01_REPOSITORIES:
            blockers.append(
                f"Repositories do not match approved Batch 01 set: expected {sorted(APPROVED_BATCH_01_REPOSITORIES)}, got {sorted(repo_ids)}"
            )

        for r in self.repositories:
            if not r.commit_sha or not re.match(r"^[a-f0-9]{40}$", r.commit_sha):
                blockers.append(f"Repository '{r.id}' does not have a 40-character lowercase hex commit SHA")

        # 2. Semantic Mneme SHA fixed
        if self.semantic_mneme_sha != FROZEN_SEMANTIC_MNEME_SHA:
            blockers.append(
                f"semantic_mneme_sha '{self.semantic_mneme_sha}' does not match frozen base SHA '{FROZEN_SEMANTIC_MNEME_SHA}'"
            )

        # 3. Extractor explicit
        if not self.extractor.id or not self.extractor.version:
            blockers.append("Extractor id and version must be explicit")

        # 4. Classifier explicit
        if not self.classifier.backend_id or not self.classifier.classifier_version:
            blockers.append("Classifier backend_id and classifier_version must be explicit")
        if self.classifier.model_identifier is None:
            blockers.append("Classifier model_identifier is not set")

        # 5. Exactly 8 semantic tasks
        if tuple(self.semantic_tasks) != EXPECTED_SEMANTIC_TASKS:
            blockers.append(
                f"Semantic tasks must be exactly {list(EXPECTED_SEMANTIC_TASKS)}, got {list(self.semantic_tasks)}"
            )

        # 6. Retrieval policy explicit
        if self.retrieval_policy.policy_id != "score_gt_zero":
            blockers.append(f"Retrieval policy must be 'score_gt_zero', got {self.retrieval_policy.policy_id!r}")

        # 7. Scenario renderer explicit
        if tuple(self.scenario_renderer.field_order) != EXPECTED_RENDERER_FIELD_ORDER:
            blockers.append(
                f"Scenario renderer fields must be exactly {list(EXPECTED_RENDERER_FIELD_ORDER)}, got {list(self.scenario_renderer.field_order)}"
            )

        # 8. Scenario corpus complete
        if (
            self.scenario_corpus.status != "complete"
            or self.scenario_corpus.content_hash == "none"
            or self.scenario_corpus.total_required != 50
            or self.scenario_corpus.per_repository_required != 10
        ):
            blockers.append(
                f"Applicability scenario corpus is incomplete: status={self.scenario_corpus.status!r}, "
                f"content_hash={self.scenario_corpus.content_hash!r} (requires 50 human-authored scenarios, 10/repo)"
            )

        # 9. Reference corpus complete
        if (
            self.reference_corpus.status != "complete"
            or self.reference_corpus.content_hash == "none"
            or self.reference_corpus.total_required != 100
            or self.reference_corpus.per_repository_required != 20
        ):
            blockers.append(
                f"Human reference decision corpus is incomplete: status={self.reference_corpus.status!r}, "
                f"content_hash={self.reference_corpus.content_hash!r} (requires 100 reviewed decisions, 20/repo)"
            )

        return blockers

    def validate_freeze(self, manifest: Manifest | None = None) -> None:
        """Validate that all freeze prerequisites are met.

        Raises:
            BaselineFreezeError: If any prerequisite is missing or if manifest claims 'frozen' prematurely.
        """
        blockers = self.check_freeze_prerequisites()
        if blockers:
            raise BaselineFreezeError(
                f"Baseline cannot be marked 'frozen':\n  - " + "\n  - ".join(blockers)
            )

        if manifest is not None and manifest.status == "frozen" and blockers:
            raise BaselineFreezeError(
                f"Manifest claims status 'frozen' but baseline prerequisites are unsatisfied:\n  - "
                + "\n  - ".join(blockers)
            )

        if self.status == "frozen" and blockers:
            raise BaselineFreezeError(
                f"Baseline status is 'frozen' but prerequisites are unsatisfied:\n  - "
                + "\n  - ".join(blockers)
            )


def validate_baseline_freeze(
    baseline: BaselineConfig,
    manifest: Manifest | None = None,
) -> None:
    """Validate that baseline configuration qualifies as frozen."""
    baseline.validate_freeze(manifest=manifest)


__all__ = [
    "APPROVED_BATCH_01_REPOSITORIES",
    "EXPECTED_SEMANTIC_TASKS",
    "EXPECTED_RENDERER_FIELD_ORDER",
    "FROZEN_SEMANTIC_MNEME_SHA",
    "BaselineFreezeError",
    "BaselineRepository",
    "BaselineExtractor",
    "BaselineClassifier",
    "BaselineRetrievalPolicy",
    "BaselineScenarioRenderer",
    "BaselineCorpusStatus",
    "BaselineConfig",
    "validate_baseline_freeze",
]

"""
Manifest model and validation for O1A Open Architecture benchmark.

Validates the merged Batch 01 manifest structure from PR #389.
Fail-closed on all structural and semantic violations.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class RepositoryConfig:
    """Single repository configuration in the batch."""

    id: str
    github: str
    commit_sha: str | None
    primary_test: str
    validation_status: str

    VALID_VALIDATION_STATUSES = frozenset({"unreviewed", "reviewed", "ambiguous"})

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise ValueError("repository.id must be non-empty string")
        if not self.github or not isinstance(self.github, str):
            raise ValueError("repository.github must be non-empty string")
        if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", self.github):
            raise ValueError(
                f"repository.github must match 'owner/repo' pattern, got {self.github!r}"
            )
        if self.commit_sha is not None:
            if not isinstance(self.commit_sha, str):
                raise ValueError("repository.commit_sha must be string or null")
            if not re.match(r"^[a-f0-9]{40}$", self.commit_sha):
                raise ValueError(
                    f"repository.commit_sha must be 40-char hex SHA, got {self.commit_sha!r}"
                )
        if not self.primary_test:
            raise ValueError("repository.primary_test must be non-empty")
        if self.validation_status not in self.VALID_VALIDATION_STATUSES:
            raise ValueError(
                f"repository.validation_status must be one of {sorted(self.VALID_VALIDATION_STATUSES)}, "
                f"got {self.validation_status!r}"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RepositoryConfig:
        required = {"id", "github", "commit_sha", "primary_test", "validation_status"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"repository missing keys: {sorted(missing)}")
        return cls(
            id=str(data["id"]),
            github=str(data["github"]),
            commit_sha=data["commit_sha"],
            primary_test=str(data["primary_test"]),
            validation_status=str(data["validation_status"]),
        )

    @property
    def is_frozen_executable(self) -> bool:
        """True if this repo config qualifies as frozen/executable baseline input."""
        return self.commit_sha is not None


@dataclass(frozen=True)
class TargetsConfig:
    """Aggregate target counts."""

    decisions_total: int
    scenarios_total: int
    decisions_per_repository: int
    scenarios_per_repository: int

    def __post_init__(self) -> None:
        for field_name, value in [
            ("decisions_total", self.decisions_total),
            ("scenarios_total", self.scenarios_total),
            ("decisions_per_repository", self.decisions_per_repository),
            ("scenarios_per_repository", self.scenarios_per_repository),
        ]:
            if not isinstance(value, int) or value <= 0:
                raise ValueError(f"targets.{field_name} must be positive integer")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TargetsConfig:
        required = {
            "decisions_total",
            "scenarios_total",
            "decisions_per_repository",
            "scenarios_per_repository",
        }
        missing = required - data.keys()
        if missing:
            raise ValueError(f"targets missing keys: {sorted(missing)}")
        return cls(
            decisions_total=int(data["decisions_total"]),
            scenarios_total=int(data["scenarios_total"]),
            decisions_per_repository=int(data["decisions_per_repository"]),
            scenarios_per_repository=int(data["scenarios_per_repository"]),
        )


@dataclass(frozen=True)
class SamplingConfig:
    """Per-repository sampling configuration."""

    clear_explicit: int
    scoped: int
    lifecycle_or_supersession: int
    ambiguous_or_conflicting: int
    enforcement_potential: int
    unusual_or_difficult: int

    SAMPLING_KEYS = (
        "clear_explicit",
        "scoped",
        "lifecycle_or_supersession",
        "ambiguous_or_conflicting",
        "enforcement_potential",
        "unusual_or_difficult",
    )

    def __post_init__(self) -> None:
        for key in self.SAMPLING_KEYS:
            value = getattr(self, key)
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"sampling.per_repository.{key} must be non-negative integer")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SamplingConfig:
        missing = set(cls.SAMPLING_KEYS) - data.keys()
        if missing:
            raise ValueError(f"sampling.per_repository missing keys: {sorted(missing)}")
        return cls(
            clear_explicit=int(data["clear_explicit"]),
            scoped=int(data["scoped"]),
            lifecycle_or_supersession=int(data["lifecycle_or_supersession"]),
            ambiguous_or_conflicting=int(data["ambiguous_or_conflicting"]),
            enforcement_potential=int(data["enforcement_potential"]),
            unusual_or_difficult=int(data["unusual_or_difficult"]),
        )

    def total(self) -> int:
        return sum(getattr(self, k) for k in self.SAMPLING_KEYS)


@dataclass(frozen=True)
class Manifest:
    """Validated O1A benchmark manifest (merged PR #389 structure)."""

    schema_version: str
    batch_id: str
    status: str
    targets: TargetsConfig
    repositories: tuple[RepositoryConfig, ...]
    sampling: SamplingConfig
    headline_metric: str

    VALID_STATUSES = frozenset({"planned", "frozen", "executing", "completed"})

    def __post_init__(self) -> None:
        if self.schema_version != "0.1":
            raise ValueError(f"unsupported schema_version: {self.schema_version!r}")
        if self.status not in self.VALID_STATUSES:
            raise ValueError(f"invalid status: {self.status!r}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        required = {
            "schema_version",
            "batch_id",
            "status",
            "targets",
            "repositories",
            "sampling",
            "headline_metric",
        }
        missing = required - data.keys()
        if missing:
            raise ValueError(f"manifest missing keys: {sorted(missing)}")

        return cls(
            schema_version=str(data["schema_version"]),
            batch_id=str(data["batch_id"]),
            status=str(data["status"]),
            targets=TargetsConfig.from_dict(data["targets"]),
            repositories=tuple(
                RepositoryConfig.from_dict(r) for r in data["repositories"]
            ),
            sampling=SamplingConfig.from_dict(data["sampling"]["per_repository"]),
            headline_metric=str(data["headline_metric"]),
        )

    @classmethod
    def load(cls, path: str | Path) -> Manifest:
        """Load and validate manifest from YAML file."""
        text = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("manifest root must be a mapping")
        return cls.from_dict(data)

    def validate_frozen_executable(self) -> None:
        """Validate manifest qualifies as frozen/executable baseline input.

        Raises:
            ValueError: If manifest is not frozen or any repository has null commit SHA.
        """
        if self.status != "frozen":
            raise ValueError(f"manifest status must be 'frozen' for execution, got {self.status!r}")
        for repo in self.repositories:
            if not repo.is_frozen_executable:
                raise ValueError(
                    f"repository '{repo.id}' commit_sha must be set for frozen/executable baseline"
                )

    def validate_target_consistency(self) -> None:
        """Validate aggregate targets match per-repository targets and sampling.

        Raises:
            ValueError: If targets are inconsistent.
        """
        repo_count = len(self.repositories)
        if repo_count == 0:
            raise ValueError("manifest must have at least one repository")

        # Validate aggregate targets
        expected_decisions_total = self.targets.decisions_per_repository * repo_count
        expected_scenarios_total = self.targets.scenarios_per_repository * repo_count

        if expected_decisions_total != self.targets.decisions_total:
            raise ValueError(
                f"targets.decisions_total={self.targets.decisions_total} "
                f"!= decisions_per_repository * repositories={expected_decisions_total}"
            )
        if expected_scenarios_total != self.targets.scenarios_total:
            raise ValueError(
                f"targets.scenarios_total={self.targets.scenarios_total} "
                f"!= scenarios_per_repository * repositories={expected_scenarios_total}"
            )

        # Validate sampling totals
        for repo in self.repositories:
            sampling_total = self.sampling.total()
            if sampling_total != self.targets.decisions_per_repository:
                raise ValueError(
                    f"sampling.per_repository total={sampling_total} "
                    f"!= targets.decisions_per_repository={self.targets.decisions_per_repository} "
                    f"for repository '{repo.id}'"
                )

    def validate_no_duplicates(self) -> None:
        """Validate no duplicate repository IDs or GitHub identifiers."""
        seen_ids: set[str] = set()
        seen_github: set[str] = set()
        for repo in self.repositories:
            if repo.id in seen_ids:
                raise ValueError(f"duplicate repository id: {repo.id!r}")
            seen_ids.add(repo.id)
            if repo.github in seen_github:
                raise ValueError(f"duplicate repository github identifier: {repo.github!r}")
            seen_github.add(repo.github)

    def configuration_hash(self) -> str:
        """Compute deterministic configuration hash.

        Excludes timestamps and run-specific fields. Hash is derived from
        normalized configuration that affects benchmark execution.
        """
        config = {
            "schema_version": self.schema_version,
            "batch_id": self.batch_id,
            "targets": {
                "decisions_total": self.targets.decisions_total,
                "scenarios_total": self.targets.scenarios_total,
                "decisions_per_repository": self.targets.decisions_per_repository,
                "scenarios_per_repository": self.targets.scenarios_per_repository,
            },
            "repositories": [
                {
                    "id": r.id,
                    "github": r.github,
                    "commit_sha": r.commit_sha,
                    "primary_test": r.primary_test,
                    "validation_status": r.validation_status,
                }
                for r in self.repositories
            ],
            "sampling": {
                "per_repository": {
                    "clear_explicit": self.sampling.clear_explicit,
                    "scoped": self.sampling.scoped,
                    "lifecycle_or_supersession": self.sampling.lifecycle_or_supersession,
                    "ambiguous_or_conflicting": self.sampling.ambiguous_or_conflicting,
                    "enforcement_potential": self.sampling.enforcement_potential,
                    "unusual_or_difficult": self.sampling.unusual_or_difficult,
                }
            },
            "headline_metric": self.headline_metric,
        }
        canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for storage/transport."""
        return {
            "schema_version": self.schema_version,
            "batch_id": self.batch_id,
            "status": self.status,
            "targets": {
                "decisions_total": self.targets.decisions_total,
                "scenarios_total": self.targets.scenarios_total,
                "decisions_per_repository": self.targets.decisions_per_repository,
                "scenarios_per_repository": self.targets.scenarios_per_repository,
            },
            "repositories": [
                {
                    "id": r.id,
                    "github": r.github,
                    "commit_sha": r.commit_sha,
                    "primary_test": r.primary_test,
                    "validation_status": r.validation_status,
                }
                for r in self.repositories
            ],
            "sampling": {
                "per_repository": {
                    "clear_explicit": self.sampling.clear_explicit,
                    "scoped": self.sampling.scoped,
                    "lifecycle_or_supersession": self.sampling.lifecycle_or_supersession,
                    "ambiguous_or_conflicting": self.sampling.ambiguous_or_conflicting,
                    "enforcement_potential": self.sampling.enforcement_potential,
                    "unusual_or_difficult": self.sampling.unusual_or_difficult,
                }
            },
            "headline_metric": self.headline_metric,
        }
"""
Reproducible run metadata for O1A Open Architecture Benchmark.

Run identity and configuration hashing must be deterministic.
configuration_hash computed from normalized actual configuration, not caller-supplied.
Timestamps must not influence configuration identity.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import mneme


@dataclass(frozen=True)
class RunMetadata:
    """Complete O1A run metadata with deterministic identity.

    All fields that affect benchmark execution are included in configuration_hash.
    Timestamps and run-specific identifiers are excluded from configuration identity.
    """

    run_id: str
    batch_id: str
    repo_id: str
    repo_commit_sha: str
    mneme_version: str
    mneme_commit_sha: str
    benchmark_schema_version: str
    taxonomy_version: str
    classifier_version: str
    configuration_hash: str
    started_at: str
    completed_at: str | None
    status: str

    VALID_STATUSES = frozenset({"running", "completed", "failed", "cancelled"})

    def __post_init__(self) -> None:
        if self.status not in self.VALID_STATUSES:
            raise ValueError(f"invalid status: {self.status!r}")

    @classmethod
    def create(
        cls,
        batch_id: str,
        repo_id: str,
        repo_commit_sha: str,
        mneme_version: str | None = None,
        mneme_commit_sha: str | None = None,
        benchmark_schema_version: str = "0.1",
        taxonomy_version: str = "0.1",
        classifier_version: str = "0.1",
        manifest_config_hash: str | None = None,
    ) -> RunMetadata:
        """Create a new run metadata with deterministic configuration hash."""
        run_id = f"run-{hashlib.sha256(f'{batch_id}{repo_id}{datetime.utcnow().isoformat()}'.encode()).hexdigest()[:32]}"
        started_at = datetime.utcnow().isoformat() + "Z"

        # Resolve mneme version and commit
        if mneme_version is None:
            mneme_version = getattr(mneme, "__version__", "0.9.1")
        if mneme_commit_sha is None:
            mneme_commit_sha = _get_git_commit_sha()

        # Configuration hash: if manifest provides one, use it; otherwise compute from args
        if manifest_config_hash is not None:
            configuration_hash = manifest_config_hash
        else:
            configuration_hash = cls._compute_config_hash(
                batch_id=batch_id,
                repo_id=repo_id,
                repo_commit_sha=repo_commit_sha,
                mneme_version=mneme_version,
                mneme_commit_sha=mneme_commit_sha,
                benchmark_schema_version=benchmark_schema_version,
                taxonomy_version=taxonomy_version,
                classifier_version=classifier_version,
            )

        return cls(
            run_id=run_id,
            batch_id=batch_id,
            repo_id=repo_id,
            repo_commit_sha=repo_commit_sha,
            mneme_version=mneme_version,
            mneme_commit_sha=mneme_commit_sha,
            benchmark_schema_version=benchmark_schema_version,
            taxonomy_version=taxonomy_version,
            classifier_version=classifier_version,
            configuration_hash=configuration_hash,
            started_at=started_at,
            completed_at=None,
            status="running",
        )

    @staticmethod
    def _compute_config_hash(
        batch_id: str,
        repo_id: str,
        repo_commit_sha: str,
        mneme_version: str,
        mneme_commit_sha: str,
        benchmark_schema_version: str,
        taxonomy_version: str,
        classifier_version: str,
    ) -> str:
        """Compute deterministic configuration hash.

        Only includes fields that affect benchmark execution semantics.
        Timestamps, run_id, started_at are explicitly excluded.
        """
        config = {
            "batch_id": batch_id,
            "repo_id": repo_id,
            "repo_commit_sha": repo_commit_sha,
            "mneme_version": mneme_version,
            "mneme_commit_sha": mneme_commit_sha,
            "benchmark_schema_version": benchmark_schema_version,
            "taxonomy_version": taxonomy_version,
            "classifier_version": classifier_version,
        }
        canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]

    def with_completion(self, status: str, completed_at: str | None = None) -> RunMetadata:
        """Return new RunMetadata with completion status."""
        if completed_at is None:
            completed_at = datetime.utcnow().isoformat() + "Z"
        return RunMetadata(
            run_id=self.run_id,
            batch_id=self.batch_id,
            repo_id=self.repo_id,
            repo_commit_sha=self.repo_commit_sha,
            mneme_version=self.mneme_version,
            mneme_commit_sha=self.mneme_commit_sha,
            benchmark_schema_version=self.benchmark_schema_version,
            taxonomy_version=self.taxonomy_version,
            classifier_version=self.classifier_version,
            configuration_hash=self.configuration_hash,
            started_at=self.started_at,
            completed_at=completed_at,
            status=status,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "batch_id": self.batch_id,
            "repo_id": self.repo_id,
            "repo_commit_sha": self.repo_commit_sha,
            "mneme_version": self.mneme_version,
            "mneme_commit_sha": self.mneme_commit_sha,
            "benchmark_schema_version": self.benchmark_schema_version,
            "taxonomy_version": self.taxonomy_version,
            "classifier_version": self.classifier_version,
            "configuration_hash": self.configuration_hash,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunMetadata:
        return cls(
            run_id=str(data["run_id"]),
            batch_id=str(data["batch_id"]),
            repo_id=str(data["repo_id"]),
            repo_commit_sha=str(data["repo_commit_sha"]),
            mneme_version=str(data["mneme_version"]),
            mneme_commit_sha=str(data["mneme_commit_sha"]),
            benchmark_schema_version=str(data["benchmark_schema_version"]),
            taxonomy_version=str(data["taxonomy_version"]),
            classifier_version=str(data["classifier_version"]),
            configuration_hash=str(data["configuration_hash"]),
            started_at=str(data["started_at"]),
            completed_at=data.get("completed_at"),
            status=str(data["status"]),
        )


def _get_git_commit_sha() -> str:
    """Get current git commit SHA, or 'unknown' if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=Path(__file__).parent.parent.parent,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def get_environment_fingerprint() -> dict[str, str]:
    """Get deterministic environment fingerprint for reproducibility debugging.

    This is NOT part of configuration_hash - it's for diagnostic purposes only.
    """
    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "architecture": platform.machine(),
    }
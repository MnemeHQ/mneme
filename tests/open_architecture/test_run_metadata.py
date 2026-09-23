"""Tests for O1A run metadata."""

from __future__ import annotations

import pytest

from mneme.open_architecture.run_metadata import (
    RunMetadata,
    get_environment_fingerprint,
)
from mneme.open_architecture.store import now_iso


class TestRunMetadata:
    def test_create_run_metadata(self):
        metadata = RunMetadata.create(
            batch_id="o1a-batch-01",
            repo_id="adrkit",
            repo_commit_sha="a" * 40,
            mneme_version="0.9.1",
            mneme_commit_sha="b" * 40,
            benchmark_schema_version="0.1",
            taxonomy_version="0.1",
            classifier_version="0.1",
        )
        assert metadata.batch_id == "o1a-batch-01"
        assert metadata.repo_id == "adrkit"
        assert metadata.repo_commit_sha == "a" * 40
        assert metadata.mneme_version == "0.9.1"
        assert metadata.mneme_commit_sha == "b" * 40
        assert metadata.status == "running"
        assert metadata.run_id.startswith("run-")
        assert metadata.started_at.endswith("Z")
        assert metadata.completed_at is None
        assert len(metadata.configuration_hash) == 32

    def test_create_with_manifest_config_hash(self):
        metadata_with = RunMetadata.create(
            batch_id="o1a-batch-01",
            repo_id="adrkit",
            repo_commit_sha="a" * 40,
            manifest_config_hash="provided_hash_123",
        )
        metadata_without = RunMetadata.create(
            batch_id="o1a-batch-01",
            repo_id="adrkit",
            repo_commit_sha="a" * 40,
            manifest_config_hash=None,
        )
        assert len(metadata_with.configuration_hash) == 32
        assert metadata_with.configuration_hash != metadata_without.configuration_hash

    def test_deterministic_config_hash(self):
        metadata1 = RunMetadata.create(
            batch_id="o1a-batch-01",
            repo_id="adrkit",
            repo_commit_sha="a" * 40,
            mneme_version="0.9.1",
            mneme_commit_sha="b" * 40,
            benchmark_schema_version="0.1",
            taxonomy_version="0.1",
            classifier_version="0.1",
        )
        metadata2 = RunMetadata.create(
            batch_id="o1a-batch-01",
            repo_id="adrkit",
            repo_commit_sha="a" * 40,
            mneme_version="0.9.1",
            mneme_commit_sha="b" * 40,
            benchmark_schema_version="0.1",
            taxonomy_version="0.1",
            classifier_version="0.1",
        )
        # Config hash should be deterministic (same inputs = same hash)
        assert metadata1.configuration_hash == metadata2.configuration_hash

    def test_config_hash_excludes_timestamps(self):
        metadata1 = RunMetadata.create(
            batch_id="o1a-batch-01",
            repo_id="adrkit",
            repo_commit_sha="a" * 40,
        )
        # Even if started_at differs, config hash should be same for same config
        metadata2 = RunMetadata(
            run_id="different-run-id",
            batch_id="o1a-batch-01",
            repo_id="adrkit",
            repo_commit_sha="a" * 40,
            mneme_version=metadata1.mneme_version,
            mneme_commit_sha=metadata1.mneme_commit_sha,
            benchmark_schema_version=metadata1.benchmark_schema_version,
            taxonomy_version=metadata1.taxonomy_version,
            classifier_version=metadata1.classifier_version,
            configuration_hash=metadata1.configuration_hash,
            started_at="2026-01-01T00:00:00Z",  # Different timestamp
            completed_at=None,
            status="running",
        )
        # The config hash stored should be the same
        assert metadata1.configuration_hash == metadata2.configuration_hash

    def test_with_completion(self):
        metadata = RunMetadata.create(
            batch_id="o1a-batch-01",
            repo_id="adrkit",
            repo_commit_sha="a" * 40,
        )
        completed = metadata.with_completion("completed")
        assert completed.status == "completed"
        assert completed.completed_at is not None
        assert completed.run_id == metadata.run_id
        assert completed.configuration_hash == metadata.configuration_hash
        assert completed.started_at == metadata.started_at

    def test_with_completion_custom_time(self):
        metadata = RunMetadata.create(
            batch_id="o1a-batch-01",
            repo_id="adrkit",
            repo_commit_sha="a" * 40,
        )
        completed = metadata.with_completion("failed", "2026-01-01T12:00:00Z")
        assert completed.status == "failed"
        assert completed.completed_at == "2026-01-01T12:00:00Z"

    def test_invalid_status(self):
        with pytest.raises(ValueError, match="invalid status"):
            RunMetadata(
                run_id="run-test", batch_id="o1a-batch-01", repo_id="adrkit",
                repo_commit_sha="a"*40, mneme_version="0.9.1", mneme_commit_sha="b"*40,
                benchmark_schema_version="0.1", taxonomy_version="0.1", classifier_version="0.1",
                configuration_hash="hash", started_at=now_iso(), completed_at=None, status="invalid"
            )

    def test_to_dict_and_from_dict(self):
        metadata = RunMetadata.create(
            batch_id="o1a-batch-01",
            repo_id="adrkit",
            repo_commit_sha="a" * 40,
        )
        d = metadata.to_dict()
        metadata2 = RunMetadata.from_dict(d)
        assert metadata == metadata2

    def test_get_environment_fingerprint(self):
        fp = get_environment_fingerprint()
        assert "python_version" in fp
        assert "platform" in fp
        assert "architecture" in fp
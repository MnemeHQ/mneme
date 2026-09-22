"""Tests for O1A manifest model and validation (merged PR #389 Batch 01)."""

from __future__ import annotations

import pytest

from mneme.open_architecture.manifest import (
    Manifest,
    RepositoryConfig,
    TargetsConfig,
    SamplingConfig,
)


class TestRepositoryConfig:
    def test_valid_repository(self):
        rc = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=None,
            primary_test="applicability_and_decision_relationships",
            validation_status="unreviewed",
        )
        assert rc.id == "adrkit"
        assert rc.github == "mbeacom/adrkit"
        assert rc.commit_sha is None
        assert rc.is_frozen_executable is False

    def test_valid_repository_with_sha(self):
        rc = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha="a" * 40,
            primary_test="applicability_and_decision_relationships",
            validation_status="unreviewed",
        )
        assert rc.is_frozen_executable is True

    def test_invalid_github_format(self):
        with pytest.raises(ValueError, match="must match 'owner/repo' pattern"):
            RepositoryConfig(
                id="adrkit",
                github="invalid",
                commit_sha=None,
                primary_test="test",
                validation_status="unreviewed",
            )

    def test_invalid_sha_format(self):
        with pytest.raises(ValueError, match="must be 40-char hex SHA"):
            RepositoryConfig(
                id="adrkit",
                github="mbeacom/adrkit",
                commit_sha="not-a-sha",
                primary_test="test",
                validation_status="unreviewed",
            )

    def test_invalid_sha_length(self):
        with pytest.raises(ValueError, match="must be 40-char hex SHA"):
            RepositoryConfig(
                id="adrkit",
                github="mbeacom/adrkit",
                commit_sha="a" * 39,
                primary_test="test",
                validation_status="unreviewed",
            )

    def test_invalid_validation_status(self):
        with pytest.raises(ValueError, match="validation_status must be one of"):
            RepositoryConfig(
                id="adrkit",
                github="mbeacom/adrkit",
                commit_sha=None,
                primary_test="test",
                validation_status="invalid",
            )


class TestTargetsConfig:
    def test_valid_targets(self):
        tc = TargetsConfig(
            decisions_total=100,
            scenarios_total=50,
            decisions_per_repository=20,
            scenarios_per_repository=10,
        )
        assert tc.decisions_total == 100
        assert tc.scenarios_total == 50

    def test_invalid_non_positive(self):
        with pytest.raises(ValueError, match="must be positive integer"):
            TargetsConfig(
                decisions_total=0,
                scenarios_total=50,
                decisions_per_repository=20,
                scenarios_per_repository=10,
            )


class TestSamplingConfig:
    def test_valid_sampling(self):
        sc = SamplingConfig(
            clear_explicit=5,
            scoped=5,
            lifecycle_or_supersession=3,
            ambiguous_or_conflicting=3,
            enforcement_potential=2,
            unusual_or_difficult=2,
        )
        assert sc.total() == 20

    def test_invalid_negative(self):
        with pytest.raises(ValueError, match="must be non-negative integer"):
            SamplingConfig(
                clear_explicit=-1,
                scoped=5,
                lifecycle_or_supersession=3,
                ambiguous_or_conflicting=3,
                enforcement_potential=2,
                unusual_or_difficult=2,
            )


class TestManifest:
    def _base_manifest(self):
        return {
            "schema_version": "0.1",
            "batch_id": "o1a-batch-01",
            "status": "planned",
            "targets": {
                "decisions_total": 100,
                "scenarios_total": 50,
                "decisions_per_repository": 20,
                "scenarios_per_repository": 10,
            },
            "repositories": [
                {
                    "id": "adrkit",
                    "github": "mbeacom/adrkit",
                    "commit_sha": None,
                    "primary_test": "applicability_and_decision_relationships",
                    "validation_status": "unreviewed",
                },
                {
                    "id": "gsa_agentic_coding_quickstart",
                    "github": "GSA-TTS/agentic-coding-quickstart",
                    "commit_sha": None,
                    "primary_test": "prescriptive_intent_and_authority",
                    "validation_status": "unreviewed",
                },
                {
                    "id": "helix",
                    "github": "AZX-PBC-OSS/helix",
                    "commit_sha": None,
                    "primary_test": "authority_conflict_and_document_purpose",
                    "validation_status": "unreviewed",
                },
                {
                    "id": "archlint",
                    "github": "muhammetsafak/archlint",
                    "commit_sha": None,
                    "primary_test": "decision_to_enforceable_rule",
                    "validation_status": "unreviewed",
                },
                {
                    "id": "modonome",
                    "github": "enumind/modonome",
                    "commit_sha": None,
                    "primary_test": "governance_ownership_and_enforcement",
                    "validation_status": "unreviewed",
                },
            ],
            "sampling": {
                "per_repository": {
                    "clear_explicit": 5,
                    "scoped": 5,
                    "lifecycle_or_supersession": 3,
                    "ambiguous_or_conflicting": 3,
                    "enforcement_potential": 2,
                    "unusual_or_difficult": 2,
                }
            },
            "headline_metric": "governing_decision_set_f1",
        }

    def test_load_merged_batch_01_manifest(self):
        m = Manifest.load("benchmarks/open_architecture/batch_01/manifest.yaml")
        assert m.batch_id == "o1a-batch-01"
        assert m.status == "planned"
        assert len(m.repositories) == 5
        assert m.targets.decisions_total == 100
        assert m.targets.scenarios_total == 50
        assert m.targets.decisions_per_repository == 20
        assert m.targets.scenarios_per_repository == 10

    def test_invalid_schema_version(self):
        data = self._base_manifest()
        data["schema_version"] = "1.0"
        with pytest.raises(ValueError, match="unsupported schema_version"):
            Manifest.from_dict(data)

    def test_invalid_status(self):
        data = self._base_manifest()
        data["status"] = "invalid"
        with pytest.raises(ValueError, match="invalid status"):
            Manifest.from_dict(data)

    def test_validate_frozen_executable_success(self):
        data = self._base_manifest()
        data["status"] = "frozen"
        # Set SHAs for all repos
        for repo in data["repositories"]:
            repo["commit_sha"] = "a" * 40
        m = Manifest.from_dict(data)
        m.validate_frozen_executable()  # Should not raise

    def test_validate_frozen_executable_null_sha(self):
        data = self._base_manifest()
        data["status"] = "frozen"
        # Only one repo has SHA
        data["repositories"][0]["commit_sha"] = "a" * 40
        m = Manifest.from_dict(data)
        with pytest.raises(ValueError, match="commit_sha must be set for frozen/executable"):
            m.validate_frozen_executable()

    def test_validate_target_consistency(self):
        data = self._base_manifest()
        m = Manifest.from_dict(data)
        m.validate_target_consistency()  # Should not raise

    def test_validate_target_consistency_mismatch_decisions(self):
        data = self._base_manifest()
        data["targets"]["decisions_total"] = 99  # Should be 100
        m = Manifest.from_dict(data)
        with pytest.raises(ValueError, match="decisions_total=99 != decisions_per_repository"):
            m.validate_target_consistency()

    def test_validate_target_consistency_mismatch_scenarios(self):
        data = self._base_manifest()
        data["targets"]["scenarios_total"] = 49  # Should be 50
        m = Manifest.from_dict(data)
        with pytest.raises(ValueError, match="scenarios_total=49 != scenarios_per_repository"):
            m.validate_target_consistency()

    def test_validate_sampling_total_mismatch(self):
        data = self._base_manifest()
        data["sampling"]["per_repository"]["clear_explicit"] = 6  # Total becomes 21
        m = Manifest.from_dict(data)
        with pytest.raises(ValueError, match="sampling.per_repository total=21 != targets.decisions_per_repository=20"):
            m.validate_target_consistency()

    def test_validate_no_duplicates(self):
        data = self._base_manifest()
        m = Manifest.from_dict(data)
        m.validate_no_duplicates()  # Should not raise

    def test_validate_no_duplicates_id(self):
        data = self._base_manifest()
        data["repositories"].append(data["repositories"][0])  # Duplicate
        m = Manifest.from_dict(data)
        with pytest.raises(ValueError, match="duplicate repository id"):
            m.validate_no_duplicates()

    def test_validate_no_duplicates_github(self):
        data = self._base_manifest()
        data["repositories"][-1]["github"] = "mbeacom/adrkit"  # Duplicate
        m = Manifest.from_dict(data)
        with pytest.raises(ValueError, match="duplicate repository github identifier"):
            m.validate_no_duplicates()

    def test_configuration_hash_deterministic(self):
        data = self._base_manifest()
        data["status"] = "frozen"
        for repo in data["repositories"]:
            repo["commit_sha"] = "a" * 40
        m1 = Manifest.from_dict(data)
        m2 = Manifest.from_dict(data)
        assert m1.configuration_hash() == m2.configuration_hash()

    def test_configuration_hash_excludes_timestamps(self):
        data = self._base_manifest()
        data["status"] = "frozen"
        for repo in data["repositories"]:
            repo["commit_sha"] = "a" * 40
        m = Manifest.from_dict(data)
        hash1 = m.configuration_hash()
        assert len(hash1) == 32
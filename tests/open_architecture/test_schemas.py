"""Tests for O1A schemas - Decision Candidate and Applicability Scenario (merged PR #389)."""

from __future__ import annotations

import pytest
import jsonschema

from mneme.open_architecture.schemas import (
    DecisionCandidate,
    Scope,
    Relationship,
    ApplicabilityScenario,
    ChangeContext,
    validate_candidate,
    validate_scenario,
)


class TestScope:
    def test_valid_scope(self):
        s = Scope(scope_type="repository", scope_expression="**/*.py")
        assert s.scope_type == "repository"
        assert s.scope_expression == "**/*.py"

    def test_invalid_scope_type(self):
        with pytest.raises(ValueError, match="invalid scope_type"):
            Scope(scope_type="invalid", scope_expression=None)

    def test_to_dict_and_from_dict(self):
        s = Scope(scope_type="component", scope_expression="src/storage")
        d = s.to_dict()
        s2 = Scope.from_dict(d)
        assert s == s2


class TestRelationship:
    def test_valid_relationship(self):
        rel = Relationship(
            relationship_type="requires",
            target_candidate_id="cand-123",
            target_reference=None,
            confidence=0.8,
            evidence_reference="ADR-001",
        )
        assert rel.relationship_type == "requires"

    def test_invalid_type(self):
        with pytest.raises(ValueError, match="invalid relationship_type"):
            Relationship(
                relationship_type="invalid",
                target_candidate_id="cand-123",
                target_reference=None,
                confidence=None,
                evidence_reference=None,
            )

    def test_to_dict_and_from_dict(self):
        rel = Relationship(
            relationship_type="supersedes",
            target_candidate_id="cand-456",
            target_reference="ADR-002",
            confidence=0.9,
            evidence_reference="source.md",
        )
        d = rel.to_dict()
        rel2 = Relationship.from_dict(d)
        assert rel == rel2


class TestDecisionCandidate:
    def _minimal_candidate_data(self) -> dict:
        return {
            "candidate_id": "cand-test-123",
            "repository": "MnemeHQ/mneme",
            "source_file": "docs/adr/ADR-001.md",
            "source_location": "line 10",
            "raw_statement": "Use JSON storage",
            "normalized_decision": "Use JSON for all storage",
            "classification": "prescriptive",
            "decision_domains": ["persistence", "data_contract"],
            "decision_purposes": ["constrain", "standardize"],
            "authority_status": "candidate",
            "authority_evidence": None,
            "scopes": [{"scope_type": "repository", "scope_expression": None}],
            "lifecycle_status": "active",
            "relationships": [],
            "enforcement_potential": "deterministic_rule",
            "candidate_rule": None,
            "confidence": 0.9,
            "human_validation_status": "unreviewed",
            "human_corrections": None,
        }

    def test_valid_candidate_merged_vocabulary(self):
        data = self._minimal_candidate_data()
        cand = DecisionCandidate.from_dict(data)
        assert cand.candidate_id == "cand-test-123"
        assert cand.classification == "prescriptive"
        assert cand.decision_domains == ("persistence", "data_contract")
        assert cand.decision_purposes == ("constrain", "standardize")
        assert cand.authority_status == "candidate"
        assert cand.enforcement_potential == "deterministic_rule"
        assert cand.human_validation_status == "unreviewed"

    def test_all_valid_classifications(self):
        for cls in ["prescriptive", "advisory", "descriptive", "historical", "ambiguous"]:
            data = self._minimal_candidate_data()
            data["classification"] = cls
            cand = DecisionCandidate.from_dict(data)
            assert cand.classification == cls

    def test_invalid_classification(self):
        data = self._minimal_candidate_data()
        data["classification"] = "invalid"
        with pytest.raises(jsonschema.ValidationError):
            DecisionCandidate.from_dict(data)

    def test_all_valid_domains(self):
        for domain in ["persistence", "api_interface", "security_privacy", "other"]:
            data = self._minimal_candidate_data()
            data["decision_domains"] = [domain]
            cand = DecisionCandidate.from_dict(data)
            assert cand.decision_domains == (domain,)

    def test_invalid_domain(self):
        data = self._minimal_candidate_data()
        data["decision_domains"] = ["invalid_domain"]
        with pytest.raises(jsonschema.ValidationError):
            DecisionCandidate.from_dict(data)

    def test_all_valid_purposes(self):
        for purpose in ["constrain", "prohibit", "require", "other"]:
            data = self._minimal_candidate_data()
            data["decision_purposes"] = [purpose]
            cand = DecisionCandidate.from_dict(data)
            assert cand.decision_purposes == (purpose,)

    def test_invalid_purpose(self):
        data = self._minimal_candidate_data()
        data["decision_purposes"] = ["invalid_purpose"]
        with pytest.raises(jsonschema.ValidationError):
            DecisionCandidate.from_dict(data)

    def test_all_valid_authorities(self):
        for auth in ["candidate", "explicitly_accepted", "superseded", "rejected", "unknown"]:
            data = self._minimal_candidate_data()
            data["authority_status"] = auth
            cand = DecisionCandidate.from_dict(data)
            assert cand.authority_status == auth

    def test_invalid_authority(self):
        data = self._minimal_candidate_data()
        data["authority_status"] = "canonical"  # Not in merged vocabulary
        with pytest.raises(jsonschema.ValidationError):
            DecisionCandidate.from_dict(data)

    def test_all_valid_scope_types(self):
        for scope_type in ["repository", "service", "package", "directory", "file_pattern", "component", "api", "dependency", "other"]:
            data = self._minimal_candidate_data()
            data["scopes"] = [{"scope_type": scope_type, "scope_expression": None}]
            cand = DecisionCandidate.from_dict(data)
            assert cand.scopes[0].scope_type == scope_type

    def test_invalid_scope_type(self):
        data = self._minimal_candidate_data()
        data["scopes"] = [{"scope_type": "invalid_scope", "scope_expression": None}]
        with pytest.raises(jsonschema.ValidationError):
            DecisionCandidate.from_dict(data)

    def test_all_valid_lifecycles(self):
        for lifecycle in ["active", "superseded", "deprecated", "temporary", "unknown"]:
            data = self._minimal_candidate_data()
            data["lifecycle_status"] = lifecycle
            cand = DecisionCandidate.from_dict(data)
            assert cand.lifecycle_status == lifecycle

    def test_invalid_lifecycle(self):
        data = self._minimal_candidate_data()
        data["lifecycle_status"] = "invalid"
        with pytest.raises(jsonschema.ValidationError):
            DecisionCandidate.from_dict(data)

    def test_all_valid_enforcement_potentials(self):
        for ep in ["deterministic_rule", "contextual_guidance", "warning", "block", "not_mechanically_enforceable", "unknown"]:
            data = self._minimal_candidate_data()
            data["enforcement_potential"] = ep
            cand = DecisionCandidate.from_dict(data)
            assert cand.enforcement_potential == ep

    def test_invalid_enforcement_potential(self):
        data = self._minimal_candidate_data()
        data["enforcement_potential"] = "enforceable"  # Old vocabulary
        with pytest.raises(jsonschema.ValidationError):
            DecisionCandidate.from_dict(data)

    def test_all_valid_human_validation_statuses(self):
        for hvs in ["unreviewed", "correct", "partially_correct", "incorrect", "ambiguous"]:
            data = self._minimal_candidate_data()
            data["human_validation_status"] = hvs
            cand = DecisionCandidate.from_dict(data)
            assert cand.human_validation_status == hvs

    def test_invalid_human_validation_status(self):
        data = self._minimal_candidate_data()
        data["human_validation_status"] = "confirmed"  # Old vocabulary
        with pytest.raises(jsonschema.ValidationError):
            DecisionCandidate.from_dict(data)

    def test_all_valid_relationship_types(self):
        for rel_type in ["requires", "prohibits", "depends_on", "refines", "conflicts_with", "supersedes", "exception_to"]:
            data = self._minimal_candidate_data()
            data["relationships"] = [{
                "relationship_type": rel_type,
                "target_candidate_id": "cand-456",
                "target_reference": None,
                "confidence": 0.5,
                "evidence_reference": None,
            }]
            cand = DecisionCandidate.from_dict(data)
            assert cand.relationships[0].relationship_type == rel_type

    def test_invalid_relationship_type(self):
        data = self._minimal_candidate_data()
        data["relationships"] = [{"relationship_type": "invalid", "target_candidate_id": "cand-456"}]
        with pytest.raises(ValueError, match="invalid relationship_type"):
            DecisionCandidate.from_dict(data)

    def test_confidence_bounds(self):
        data = self._minimal_candidate_data()
        data["confidence"] = 1.5
        with pytest.raises(jsonschema.ValidationError):
            DecisionCandidate.from_dict(data)

    def test_deterministic_serialization(self):
        data = self._minimal_candidate_data()
        cand = DecisionCandidate.from_dict(data)
        json1 = cand.to_json()
        json2 = cand.to_json()
        assert json1 == json2

    def test_json_roundtrip(self):
        data = self._minimal_candidate_data()
        cand = DecisionCandidate.from_dict(data)
        json_str = cand.to_json()
        cand2 = DecisionCandidate.from_json(json_str)
        assert cand == cand2

    def test_validate_candidate_function(self):
        data = self._minimal_candidate_data()
        validate_candidate(data)  # Should not raise

    def test_validate_candidate_fails_on_invalid(self):
        data = self._minimal_candidate_data()
        data["classification"] = "invalid"
        with pytest.raises(jsonschema.ValidationError):
            validate_candidate(data)


class TestApplicabilityScenario:
    def _minimal_scenario_data(self) -> dict:
        return {
            "scenario_id": "scn-test-123",
            "repository": "MnemeHQ/mneme",
            "description": "Test scenario",
            "change_context": {
                "path": "src/main.py",
                "component": "storage",
                "change_type": "modification",
                "dependencies": ["dep1"],
                "api": None,
                "technology": "Python",
                "other_context": None,
            },
            "expected_governing_decision_ids": ["ADR-001", "ADR-002"],
            "mneme_governing_decision_ids": [],
            "human_notes": None,
            "validation_state": "unreviewed",
        }

    def test_valid_scenario_merged_vocabulary(self):
        data = self._minimal_scenario_data()
        scn = ApplicabilityScenario.from_dict(data)
        assert scn.scenario_id == "scn-test-123"
        assert scn.repository == "MnemeHQ/mneme"
        assert scn.expected_governing_decision_ids == ("ADR-001", "ADR-002")
        assert scn.mneme_governing_decision_ids == ()
        assert scn.validation_state == "unreviewed"

    def test_all_valid_validation_states(self):
        for state in ["unreviewed", "reviewed", "ambiguous"]:
            data = self._minimal_scenario_data()
            data["validation_state"] = state
            scn = ApplicabilityScenario.from_dict(data)
            assert scn.validation_state == state

    def test_invalid_validation_state(self):
        data = self._minimal_scenario_data()
        data["validation_state"] = "invalid"
        with pytest.raises(jsonschema.ValidationError):
            ApplicabilityScenario.from_dict(data)

    def test_expected_governing_decision_ids_are_reference_labels(self):
        """Expected governing decision IDs are human reference labels, never auto-derived."""
        data = self._minimal_scenario_data()
        scn = ApplicabilityScenario.from_dict(data)
        # They remain as set explicitly
        assert scn.expected_governing_decision_ids == ("ADR-001", "ADR-002")
        # Mneme predictions start empty
        assert scn.mneme_governing_decision_ids == ()

    def test_with_mneme_predictions(self):
        data = self._minimal_scenario_data()
        scn = ApplicabilityScenario.from_dict(data)
        scn2 = scn.with_mneme_predictions(["ADR-001", "cand-123"])
        assert scn2.mneme_governing_decision_ids == ("ADR-001", "cand-123")
        # Original unchanged
        assert scn.mneme_governing_decision_ids == ()
        # Expected governing decisions unchanged
        assert scn2.expected_governing_decision_ids == scn.expected_governing_decision_ids

    def test_deterministic_serialization(self):
        data = self._minimal_scenario_data()
        scn = ApplicabilityScenario.from_dict(data)
        json1 = scn.to_json()
        json2 = scn.to_json()
        assert json1 == json2

    def test_json_roundtrip(self):
        data = self._minimal_scenario_data()
        scn = ApplicabilityScenario.from_dict(data)
        json_str = scn.to_json()
        scn2 = ApplicabilityScenario.from_json(json_str)
        assert scn == scn2

    def test_validate_scenario_function(self):
        data = self._minimal_scenario_data()
        validate_scenario(data)  # Should not raise

    def test_validate_scenario_fails_on_invalid(self):
        data = self._minimal_scenario_data()
        data["validation_state"] = "invalid"
        with pytest.raises(jsonschema.ValidationError):
            validate_scenario(data)
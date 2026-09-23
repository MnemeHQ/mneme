"""
tests.open_architecture.test_projection — Tests for temporary DecisionCandidate → Decision projection.

Covers items 1-13 of O1A2.4 required coverage.
"""

from __future__ import annotations

import pytest

from mneme.open_architecture.projection import (
    project_candidate_to_decision,
    project_candidates_to_decisions,
)
from mneme.open_architecture.schemas import DecisionCandidate, Scope


def _make_candidate(
    *,
    candidate_id: str = "cand-test-123",
    normalized_decision: str = "Use JSON for storage",
    raw_statement: str | None = "We should use JSON for storage",
    scopes: tuple[Scope, ...] = (
        Scope(scope_type="repository", scope_expression="**/*.py"),
        Scope(scope_type="package", scope_expression="storage"),
    ),
    lifecycle_status: str = "active",
    candidate_rule: str | None = None,
    enforcement_potential: str = "deterministic_rule",
) -> DecisionCandidate:
    return DecisionCandidate(
        candidate_id=candidate_id,
        repository="MnemeHQ/mneme",
        source_file="docs/adr/ADR-001.md",
        source_location="line 10",
        raw_statement=raw_statement,
        normalized_decision=normalized_decision,
        classification="prescriptive",
        decision_domains=("persistence", "data_contract"),
        decision_purposes=("constrain", "standardize"),
        authority_status="candidate",
        authority_evidence=None,
        scopes=scopes,
        lifecycle_status=lifecycle_status,
        relationships=(),
        enforcement_potential=enforcement_potential,
        candidate_rule=candidate_rule,
        confidence=0.9,
        human_validation_status="unreviewed",
        human_corrections=None,
    )


class TestCandidateToDecisionProjection:
    # 1. candidate ID preserved exactly
    def test_candidate_id_preserved_exactly(self):
        candidate = _make_candidate(candidate_id="cand-test-123")
        decision = project_candidate_to_decision(candidate)
        assert decision.id == "cand-test-123"

    # 2. normalized decision maps to Decision.decision
    def test_normalized_decision_maps_to_decision(self):
        candidate = _make_candidate(normalized_decision="Use JSON for all storage")
        decision = project_candidate_to_decision(candidate)
        assert decision.decision == "Use JSON for all storage"

    # 3. raw statement maps to rationale
    def test_raw_statement_maps_to_rationale(self):
        candidate = _make_candidate(raw_statement="We decided to use JSON")
        decision = project_candidate_to_decision(candidate)
        assert decision.rationale == "We decided to use JSON"

    def test_none_raw_statement_maps_to_empty_string(self):
        candidate = _make_candidate(raw_statement=None)
        decision = project_candidate_to_decision(candidate)
        assert decision.rationale == ""

    # 4. scope expressions preserved
    def test_scope_expressions_preserved(self):
        candidate = _make_candidate()
        decision = project_candidate_to_decision(candidate)
        # Should preserve scope_type:scope_expression format
        assert "repository:**/*.py" in decision.scope
        assert "package:storage" in decision.scope

    # 5. empty scope expression does not generate invented scope
    def test_empty_scope_expression_no_invented_scope(self):
        scopes = (Scope(scope_type="repository", scope_expression=None),)
        candidate = _make_candidate(scopes=scopes)
        decision = project_candidate_to_decision(candidate)
        assert decision.scope == ["repository"]
        assert all(":" not in s for s in decision.scope)

    # 6. duplicate scopes handled deterministically
    def test_duplicate_scopes_deterministic(self):
        scopes = (
            Scope(scope_type="repository", scope_expression="**/*.py"),
            Scope(scope_type="repository", scope_expression="**/*.py"),
            Scope(scope_type="package", scope_expression="storage"),
            Scope(scope_type="package", scope_expression="storage"),
        )
        candidate = _make_candidate(scopes=scopes)
        decision = project_candidate_to_decision(candidate)
        # Should deduplicate while preserving deterministic order
        assert len(decision.scope) == 2
        assert decision.scope == ["package:storage", "repository:**/*.py"]

    # 7. constraints remain empty
    def test_constraints_remain_empty(self):
        candidate = _make_candidate()
        decision = project_candidate_to_decision(candidate)
        assert decision.constraints == []

    # 8. anti-patterns remain empty
    def test_anti_patterns_remain_empty(self):
        candidate = _make_candidate()
        decision = project_candidate_to_decision(candidate)
        assert decision.anti_patterns == []

    # 9. typed rules remain empty
    def test_rules_remain_empty(self):
        candidate = _make_candidate()
        decision = project_candidate_to_decision(candidate)
        assert decision.rules == []

    # 10. candidate_rule does not become runtime rule
    def test_candidate_rule_does_not_become_runtime_rule(self):
        candidate = _make_candidate(candidate_rule="forbid_postgres")
        decision = project_candidate_to_decision(candidate)
        assert decision.rules == []
        assert decision.constraints == []

    # 11. enforcement potential does not create enforcement state
    def test_enforcement_potential_does_not_create_enforcement_state(self):
        candidate = _make_candidate(enforcement_potential="deterministic_rule")
        decision = project_candidate_to_decision(candidate)
        assert decision.rules == []
        assert decision.constraints == []
        assert decision.anti_patterns == []

    # 12. projection performs no writes
    def test_projection_performs_no_writes(self, tmp_path):
        # Projection is pure - no file system access
        candidate = _make_candidate()
        decision = project_candidate_to_decision(candidate)
        # No .mneme/ directory should be created
        assert not (tmp_path / ".mneme").exists()

    # 13. projection does not import authority writers
    def test_no_authority_writers_imported(self):
        import mneme.open_architecture.projection as proj_mod

        forbidden = [
            "DecisionAuthorityService",
            "DecisionProposalStore",
            "MemoryStore",
            "JsonFileDecisionProposalStore",
            "audit",
            "enforce",
        ]
        for name in forbidden:
            assert name not in vars(proj_mod), f"Forbidden authority component '{name}' found in projection module"


class TestBatchProjection:
    def test_batch_projection_preserves_order(self):
        candidates = [
            _make_candidate(candidate_id="cand-1"),
            _make_candidate(candidate_id="cand-2"),
            _make_candidate(candidate_id="cand-3"),
        ]
        decisions = project_candidates_to_decisions(candidates)
        assert [d.id for d in decisions] == ["cand-1", "cand-2", "cand-3"]

    # 14. duplicate candidate IDs fail closed
    def test_duplicate_candidate_ids_fail_closed(self):
        candidates = [
            _make_candidate(candidate_id="cand-dup"),
            _make_candidate(candidate_id="cand-dup"),
        ]
        with pytest.raises(ValueError, match="Duplicate candidate_id in projection input"):
            project_candidates_to_decisions(candidates)


class TestLifecycleStatusPassedThrough:
    def test_lifecycle_status_passed_through(self):
        for status in ["active", "superseded", "deprecated", "temporary", "unknown"]:
            candidate = _make_candidate(lifecycle_status=status)
            decision = project_candidate_to_decision(candidate)
            assert decision.status == status

    def test_projection_does_not_filter_by_lifecycle(self):
        """Projection should NOT filter by lifecycle - that's a caller/pipeline decision."""
        candidates = [
            _make_candidate(candidate_id="cand-active", lifecycle_status="active"),
            _make_candidate(candidate_id="cand-superseded", lifecycle_status="superseded"),
            _make_candidate(candidate_id="cand-deprecated", lifecycle_status="deprecated"),
            _make_candidate(candidate_id="cand-temporary", lifecycle_status="temporary"),
            _make_candidate(candidate_id="cand-unknown", lifecycle_status="unknown"),
        ]
        decisions = project_candidates_to_decisions(candidates)
        # All should be projected regardless of lifecycle
        assert len(decisions) == 5
        statuses = {d.status for d in decisions}
        assert statuses == {"active", "superseded", "deprecated", "temporary", "unknown"}


class TestEmptyValues:
    def test_empty_normalized_decision_fails(self):
        cand = _make_candidate()
        object.__setattr__(cand, "normalized_decision", "")
        with pytest.raises(ValueError, match="normalized_decision must be non-empty"):
            project_candidate_to_decision(cand)

    def test_empty_candidate_id_fails(self):
        cand = _make_candidate()
        object.__setattr__(cand, "candidate_id", "")
        with pytest.raises(ValueError, match="candidate_id must be non-empty"):
            project_candidate_to_decision(cand)
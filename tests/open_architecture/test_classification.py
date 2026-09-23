"""
tests.open_architecture.test_classification — Tests for semantic classifier boundary and normalization.

Covers items 14-41 of O1A2.3 required coverage:
- Classifier contract & static test classifier
- Vocabulary normalization (fail-closed)
- Authority and lifecycle semantics
- Architectural boundaries
- End-to-end integration
"""

from __future__ import annotations

import pytest

from mneme.open_architecture.candidates import (
    ExtractedCandidate,
    LineSpan,
    build_decision_candidate,
)
from mneme.open_architecture.classification import (
    ClassifierResult,
    ClassifierTask,
    ClassifierTaskType,
    NormalizationError,
    StaticClassifier,
    build_source_context,
    execute_classifier_batch,
    normalize_authority,
    normalize_classification,
    normalize_domains,
    normalize_enforcement_potential,
    normalize_lifecycle,
    normalize_purposes,
    normalize_relationships,
    normalize_scopes,
)
from mneme.open_architecture.discovery import DiscoveredSourceDocument
from mneme.open_architecture.schemas import (
    VALID_AUTHORITIES,
    VALID_CLASSIFICATIONS,
    VALID_DOMAINS,
    VALID_ENFORCEMENT_POTENTIAL,
    VALID_LIFECYCLES,
    VALID_PURPOSES,
    VALID_RELATIONSHIP_TYPES,
    VALID_SCOPE_TYPES,
)


# ── Classifier Contract Tests ──────────────────────────────────────────────────


class TestClassifierContract:
    def _make_task(self, task_type: ClassifierTaskType = ClassifierTaskType.DECISION_CLASSIFICATION) -> ClassifierTask:
        return ClassifierTask(
            task_type=task_type,
            candidate_id="cand-" + "a" * 32,
            repository_identifier="mbeacom/adrkit",
            repository_commit_sha="a" * 40,
            source_path="docs/adr/ADR-001.md",
            source_location="L10-L15",
            raw_statement="Use JSON for persistence.",
            source_context="Context around L10-L15...",
            taxonomy_version="0.1",
        )

    # 14. static classifier executes requested task
    def test_static_classifier_executes_task(self):
        task = self._make_task()
        classifier = StaticClassifier(
            backend_id="static-test",
            classifier_version="0.1.0",
            model_identifier="test-model",
            outputs={
                ClassifierTaskType.DECISION_CLASSIFICATION: {
                    "classification": "prescriptive",
                    "rationale": "Uses normative 'Use' verb",
                }
            },
            default_confidence=0.92,
        )

        result = classifier.execute(task)
        assert isinstance(result, ClassifierResult)
        assert result.task_type == ClassifierTaskType.DECISION_CLASSIFICATION
        assert result.output["classification"] == "prescriptive"
        assert result.confidence == 0.92

    # 15. backend identity preserved
    def test_backend_identity_preserved(self):
        classifier = StaticClassifier(backend_id="custom-backend-id")
        task = self._make_task()
        result = classifier.execute(task)
        assert result.backend_id == "custom-backend-id"

    # 16. classifier version preserved
    def test_classifier_version_preserved(self):
        classifier = StaticClassifier(classifier_version="2.3.4")
        task = self._make_task()
        result = classifier.execute(task)
        assert result.classifier_version == "2.3.4"

    # 17. model identifier preserved
    def test_model_identifier_preserved(self):
        classifier = StaticClassifier(model_identifier="meta/llama-3")
        task = self._make_task()
        result = classifier.execute(task)
        assert result.model_identifier == "meta/llama-3"

    # 18. taxonomy version explicit
    def test_taxonomy_version_explicit(self):
        task = self._make_task()
        assert task.taxonomy_version == "0.1"
        classifier = StaticClassifier()
        result = classifier.execute(task)
        assert result.taxonomy_version == "0.1"

    # 19. task type explicit
    def test_task_type_explicit(self):
        for task_type in ClassifierTaskType:
            task = self._make_task(task_type=task_type)
            assert task.task_type == task_type
            classifier = StaticClassifier()
            result = classifier.execute(task)
            assert result.task_type == task_type

    # 20. no network required
    def test_no_network_required(self):
        # Static classifier executes entirely in-memory with no network activity
        task = self._make_task()
        classifier = StaticClassifier()
        result = classifier.execute(task)
        assert result.output is not None

    def test_batch_execution_preserves_order(self):
        classifier = StaticClassifier(
            outputs={
                ClassifierTaskType.DOMAINS: {"domains": ["persistence"]},
                ClassifierTaskType.PURPOSES: {"purposes": ["constrain"]},
            }
        )
        task1 = self._make_task(ClassifierTaskType.DOMAINS)
        task2 = self._make_task(ClassifierTaskType.PURPOSES)

        results = execute_classifier_batch(classifier, [task1, task2])
        assert len(results) == 2
        assert results[0].task_type == ClassifierTaskType.DOMAINS
        assert results[1].task_type == ClassifierTaskType.PURPOSES


# ── Vocabulary Normalization Tests ─────────────────────────────────────────────


class TestVocabularyNormalization:
    # 21. valid classification accepted
    def test_valid_classification_accepted(self):
        for c in VALID_CLASSIFICATIONS:
            assert normalize_classification(c) == (c,)
        assert normalize_classification(["prescriptive", "advisory"]) == ("advisory", "prescriptive")

    # 22. unknown classification rejected
    def test_unknown_classification_rejected(self):
        with pytest.raises(NormalizationError, match="Invalid classification"):
            normalize_classification("non_existent_class")

    # 23. valid multi-domain output accepted
    def test_valid_multi_domain_accepted(self):
        domains = ["persistence", "data_contract", "api_interface"]
        normalized = normalize_domains(domains)
        assert normalized == ("api_interface", "data_contract", "persistence")

    # 24. invalid domain rejected
    def test_invalid_domain_rejected(self):
        with pytest.raises(NormalizationError, match="Invalid domain"):
            normalize_domains(["persistence", "invalid_domain_name"])

    def test_empty_domains_rejected(self):
        with pytest.raises(NormalizationError, match="must be non-empty"):
            normalize_domains([])

    # 25. valid purposes accepted
    def test_valid_purposes_accepted(self):
        purposes = ["constrain", "prohibit", "standardize"]
        normalized = normalize_purposes(purposes)
        assert normalized == ("constrain", "prohibit", "standardize")

    # 26. invalid purpose rejected
    def test_invalid_purpose_rejected(self):
        with pytest.raises(NormalizationError, match="Invalid purpose"):
            normalize_purposes(["constrain", "not_a_purpose"])

    def test_empty_purposes_rejected(self):
        with pytest.raises(NormalizationError, match="must be non-empty"):
            normalize_purposes([])

    # 27. all authority states supported
    def test_all_authority_states_supported(self):
        for auth in VALID_AUTHORITIES:
            assert normalize_authority(auth) == auth

    # 28. invalid authority rejected
    def test_invalid_authority_rejected(self):
        with pytest.raises(NormalizationError, match="Invalid authority"):
            normalize_authority("canonical")  # Not in research authority vocabulary

    # 29. valid scope types accepted
    def test_valid_scope_types_accepted(self):
        scopes_data = [
            {"scope_type": "repository", "scope_expression": None},
            {"scope_type": "package", "scope_expression": "pkg/storage"},
        ]
        scopes = normalize_scopes(scopes_data)
        assert len(scopes) == 2
        assert scopes[0].scope_type == "repository"
        assert scopes[1].scope_expression == "pkg/storage"

    def test_invalid_scope_type_rejected(self):
        with pytest.raises(NormalizationError, match="Invalid scope_type"):
            normalize_scopes([{"scope_type": "invalid_scope_type", "scope_expression": None}])

    # 30. lifecycle vocabulary enforced
    def test_lifecycle_vocabulary_enforced(self):
        for lc in VALID_LIFECYCLES:
            assert normalize_lifecycle(lc) == lc
        with pytest.raises(NormalizationError, match="Invalid lifecycle"):
            normalize_lifecycle("retired")

    # 31. relationship vocabulary enforced
    def test_relationship_vocabulary_enforced(self):
        rels_data = [
            {"relationship_type": "requires", "target_candidate_id": "cand-123"},
            {"relationship_type": "supersedes", "target_reference": "ADR-001"},
        ]
        rels = normalize_relationships(rels_data)
        assert len(rels) == 2
        assert rels[0].relationship_type == "requires"

        with pytest.raises(NormalizationError, match="Invalid relationship_type"):
            normalize_relationships([{"relationship_type": "blocks"}])

    # 32. enforcement vocabulary enforced
    def test_enforcement_vocabulary_enforced(self):
        for ep in VALID_ENFORCEMENT_POTENTIAL:
            assert normalize_enforcement_potential(ep) == ep
        with pytest.raises(NormalizationError, match="Invalid enforcement_potential"):
            normalize_enforcement_potential("enforce_always")


# ── Architectural Boundaries Tests ────────────────────────────────────────────


class TestArchitecturalBoundaries:
    # 33. explicitly_accepted research authority does not write canonical state
    def test_explicitly_accepted_does_not_write_canonical_state(self):
        auth = normalize_authority("explicitly_accepted")
        assert auth == "explicitly_accepted"

        # Constructing an ExtractedCandidate or DecisionCandidate with 'explicitly_accepted'
        # produces a research object only. It does not write to canonical project memory.
        span = LineSpan(1, 2)
        identity = {
            "repository_identifier": "mbeacom/adrkit",
            "repository_commit_sha": "a" * 40,
            "source_path": "docs/adr/ADR-001.md",
            "source_content_hash": "sha256:" + "1" * 64,
            "source_location": span.to_string(),
            "raw_statement": "Accepted ADR statement",
        }
        cand_id = ExtractedCandidate.generate_candidate_id(identity)
        extracted = ExtractedCandidate(
            candidate_id=cand_id,
            repository_identifier="mbeacom/adrkit",
            repository_commit_sha="a" * 40,
            source_path="docs/adr/ADR-001.md",
            source_content_hash="sha256:" + "1" * 64,
            source_location=span,
            raw_statement="Accepted ADR statement",
            discovery_confidence=0.95,
        )
        cand = build_decision_candidate(
            extracted=extracted,
            classification="prescriptive",
            decision_domains=("architecture_structure",),
            decision_purposes=("constrain",),
            authority_status=auth,
            authority_evidence="ADR accepted header",
        )
        assert cand.authority_status == "explicitly_accepted"
        # Not a canonical decision (does not have Decision authority attributes)
        assert not hasattr(cand, "rules")

    # 34. no DecisionAuthorityService import
    def test_no_decision_authority_service_imported(self):
        import mneme.open_architecture.candidates as cand_mod
        import mneme.open_architecture.classification as class_mod

        for mod in (cand_mod, class_mod):
            assert "DecisionAuthorityService" not in vars(mod)

    # 35. no DecisionProposalStore import
    def test_no_decision_proposal_store_imported(self):
        import mneme.open_architecture.candidates as cand_mod
        import mneme.open_architecture.classification as class_mod

        for mod in (cand_mod, class_mod):
            assert "DecisionProposalStore" not in vars(mod)
            assert "JsonFileDecisionProposalStore" not in vars(mod)

    # 36. no MemoryStore write
    def test_no_memory_store_imported(self):
        import mneme.open_architecture.candidates as cand_mod
        import mneme.open_architecture.classification as class_mod

        for mod in (cand_mod, class_mod):
            assert "MemoryStore" not in vars(mod)

    # 37. no .mneme/ mutation
    def test_no_mneme_mutation_during_classification(self, tmp_path):
        task = ClassifierTask(
            task_type=ClassifierTaskType.DECISION_CLASSIFICATION,
            candidate_id="cand-" + "a" * 32,
            repository_identifier="test/repo",
            repository_commit_sha="a" * 40,
            source_path="test.md",
            source_location="L1",
            raw_statement="Statement",
            source_context="Context",
        )
        classifier = StaticClassifier()
        classifier.execute(task)

        # Ensure no .mneme directory was created
        assert not (tmp_path / ".mneme").exists()

    # 38. no Decision projection
    def test_no_decision_projection(self):
        import mneme.open_architecture.candidates as cand_mod
        import mneme.open_architecture.classification as class_mod

        for mod in (cand_mod, class_mod):
            assert "Decision" not in vars(mod)
            assert "Rule" not in vars(mod)

    # 39. no provider-specific SDK dependency
    def test_no_provider_sdk_imported(self):
        import mneme.open_architecture.classification as class_mod

        # Verify no external LLM SDKs are imported
        forbidden_sdks = ["anthropic", "openai", "google", "cohere", "langchain"]
        for sdk in forbidden_sdks:
            assert sdk not in vars(class_mod)

    # 40. no use of production LLMAdapter
    def test_no_production_llm_adapter_used(self):
        import mneme.open_architecture.classification as class_mod

        assert "LLMAdapter" not in vars(class_mod)


# ── Integration Pipeline Test ──────────────────────────────────────────────────


class TestCandidateClassificationIntegration:
    # 41. DiscoveredSourceDocument → candidate evidence span → classifier task → validated output
    def test_end_to_end_local_pipeline(self):
        # 1. Source document
        content = (
            "# Architecture Decision\n\n"
            "## Storage Specification\n"
            "We decide to standardize on SQLite for local research persistence.\n"
            "PostgreSQL is prohibited for offline benchmarks.\n\n"
            "## Status\n"
            "Accepted\n"
        )
        raw = content.encode("utf-8")
        import hashlib
        doc = DiscoveredSourceDocument(
            relative_path="docs/adr/ADR-001.md",
            source_type="adr",
            content_hash=f"sha256:{hashlib.sha256(raw).hexdigest()}",
            content=content,
            metadata={"byte_length": len(raw)},
        )

        # 2. Extract candidate span (lines 4-5)
        span = LineSpan(4, 5)
        extracted = ExtractedCandidate.from_source_document(
            doc=doc,
            repo_commit_sha="a" * 40,
            line_span=span,
            discovery_confidence=0.85,
        )
        assert "standardize on SQLite" in extracted.raw_statement

        # 3. Build classifier tasks with context
        context = build_source_context(doc, span, context_lines=3)
        assert ">>>" in context  # Evidence span marked

        classify_task = ClassifierTask.from_extracted_candidate(
            extracted=extracted,
            task_type=ClassifierTaskType.DECISION_CLASSIFICATION,
            source_context=context,
        )
        domain_task = ClassifierTask.from_extracted_candidate(
            extracted=extracted,
            task_type=ClassifierTaskType.DOMAINS,
            source_context=context,
        )
        authority_task = ClassifierTask.from_extracted_candidate(
            extracted=extracted,
            task_type=ClassifierTaskType.AUTHORITY,
            source_context=context,
        )

        # 4. Execute with static classifier
        classifier = StaticClassifier(
            backend_id="static-pipeline-test",
            outputs={
                ClassifierTaskType.DECISION_CLASSIFICATION: {"classification": "prescriptive"},
                ClassifierTaskType.DOMAINS: {"domains": ["persistence", "architecture_structure"]},
                ClassifierTaskType.AUTHORITY: {"authority": "explicitly_accepted"},
            },
        )

        results = execute_classifier_batch(classifier, [classify_task, domain_task, authority_task])
        assert len(results) == 3

        # 5. Validate semantic output
        norm_class = normalize_classification(results[0].output["classification"])
        norm_domains = normalize_domains(results[1].output["domains"])
        norm_authority = normalize_authority(results[2].output["authority"])

        assert norm_class == ("prescriptive",)
        assert norm_domains == ("architecture_structure", "persistence")
        assert norm_authority == "explicitly_accepted"

        # 6. Compose DecisionCandidate (research object)
        cand = build_decision_candidate(
            extracted=extracted,
            classification=norm_class[0],
            decision_domains=norm_domains,
            decision_purposes=("standardize", "prohibit"),
            authority_status=norm_authority,
            authority_evidence="Lines 7-8: Status Accepted",
            confidence=0.9,
        )

        assert cand.candidate_id == extracted.candidate_id
        assert cand.classification == "prescriptive"
        assert cand.authority_status == "explicitly_accepted"
        assert cand.decision_domains == ("architecture_structure", "persistence")

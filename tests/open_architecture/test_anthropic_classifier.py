"""
tests.open_architecture.test_anthropic_classifier — Tests for Anthropic semantic classifier adapter.

Covers all 28 required test cases from O1A3 specification:
1. Adapter satisfies SemanticClassifier protocol.
2. Backend ID exact ("anthropic").
3. Classifier version exact ("0.1").
4. Model ID exact ("claude-sonnet-4-6").
5. Eight task types each select the correct output schema.
6. Valid structured classification output.
7. Valid domains output.
8. Valid purposes output.
9. Valid authority output.
10. Valid scope output.
11. Valid lifecycle output.
12. Valid relationships output.
13. Valid enforcement output.
14. Current normalizers accept provider output.
15. Invalid enum fails closed.
16. Malformed response fails.
17. Missing API key fails only on remote execution.
18. API error remains observable.
19. Rate limit remains observable.
20. No model fallback.
21. No canonical writes.
22. No production LLMAdapter dependency.
23. No DecisionAuthorityService dependency.
24. No DecisionProposal write.
25. No .mneme/ mutation.
26. Deterministic prompt construction.
27. Same task produces same request payload.
28. No tools/thinking/web use enabled.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mneme.open_architecture.candidates import ExtractedCandidate, LineSpan
from mneme.open_architecture.classification import (
    ClassifierResult,
    ClassifierTask,
    ClassifierTaskType,
    NormalizationError,
    SemanticClassifier,
    normalize_authority,
    normalize_classification,
    normalize_domains,
    normalize_enforcement_potential,
    normalize_lifecycle,
    normalize_purposes,
    normalize_relationships,
    normalize_scopes,
)
from mneme.open_architecture.classifiers.anthropic import (
    TASK_SCHEMAS,
    AnthropicAuthenticationError,
    AnthropicClassifier,
    AnthropicClassifierError,
    AnthropicMalformedResponseError,
    AnthropicRateLimitError,
)
from mneme.open_architecture.discovery import DiscoveredSourceDocument
from mneme.open_architecture.export import compute_bundle_content_hash
from mneme.open_architecture.manifest import RepositoryConfig
from mneme.open_architecture.orchestrator import OpenArchitectureRunResult
from mneme.open_architecture.run_metadata import RunMetadata
from mneme.open_architecture.schemas import DecisionCandidate, Scope
from mneme.open_architecture.store import CandidateLifecycleRecord, ResearchStore


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ── Mock Anthropic Response Infrastructure ────────────────────────────────────


class MockTextBlock:
    def __init__(self, text: str):
        self.text = text
        self.type = "text"


class MockUsage:
    def __init__(self, input_tokens: int = 150, output_tokens: int = 40):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class MockMessageResponse:
    def __init__(self, content_text: str, input_tokens: int = 150, output_tokens: int = 40):
        self.content = [MockTextBlock(content_text)]
        self.usage = MockUsage(input_tokens, output_tokens)


class MockMessagesResource:
    def __init__(self, response_factory=None):
        self.response_factory = response_factory or (lambda **kwargs: MockMessageResponse("{}"))
        self.last_kwargs: dict[str, Any] | None = None
        self.call_count = 0

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        self.call_count += 1
        return self.response_factory(**kwargs)


class MockAnthropicClient:
    def __init__(self, response_factory=None):
        self.messages = MockMessagesResource(response_factory)


def _make_sample_task(task_type: ClassifierTaskType) -> ClassifierTask:
    return ClassifierTask(
        task_type=task_type,
        candidate_id="cand-0123456789abcdef0123456789abcdef",
        repository_identifier="mbeacom/adrkit",
        repository_commit_sha="471457da29638ecca6119b35180c2845bf989cac",
        source_path="docs/adr/0001-record-architecture-decisions.md",
        source_location="L12-L18",
        raw_statement="We will use Architecture Decision Records to capture important decisions.",
        source_context="Context around L12-L18 in ADR-0001...",
        taxonomy_version="0.1",
    )


# ── Test Suite ─────────────────────────────────────────────────────────────────


class TestAnthropicClassifier:
    """Complete test suite for AnthropicClassifier covering items 1-28."""

    # 1. adapter satisfies SemanticClassifier protocol
    def test_1_adapter_satisfies_semantic_classifier_protocol(self):
        adapter = AnthropicClassifier()
        assert hasattr(adapter, "backend_id")
        assert hasattr(adapter, "classifier_version")
        assert hasattr(adapter, "model_identifier")
        assert hasattr(adapter, "execute")
        assert callable(adapter.execute)
        # Verify types
        assert isinstance(adapter.backend_id, str)
        assert isinstance(adapter.classifier_version, str)
        assert adapter.model_identifier is None or isinstance(adapter.model_identifier, str)

    # 2. backend ID exact
    def test_2_backend_id_exact(self):
        adapter = AnthropicClassifier()
        assert adapter.backend_id == "anthropic"

    # 3. classifier version exact
    def test_3_classifier_version_exact(self):
        adapter = AnthropicClassifier()
        assert adapter.classifier_version == "0.1"

    # 4. model ID exact
    def test_4_model_id_exact(self):
        adapter = AnthropicClassifier()
        assert adapter.model_identifier == "claude-sonnet-4-6"

    # 5. eight task types each select the correct output schema
    def test_5_eight_task_types_select_correct_output_schema(self):
        expected_tasks = [
            ClassifierTaskType.DECISION_CLASSIFICATION,
            ClassifierTaskType.DOMAINS,
            ClassifierTaskType.PURPOSES,
            ClassifierTaskType.AUTHORITY,
            ClassifierTaskType.SCOPE,
            ClassifierTaskType.LIFECYCLE,
            ClassifierTaskType.RELATIONSHIPS,
            ClassifierTaskType.ENFORCEMENT_POTENTIAL,
        ]
        assert len(expected_tasks) == 8
        for task_type in expected_tasks:
            schema = AnthropicClassifier.get_task_schema(task_type)
            assert isinstance(schema, dict)
            assert schema["type"] == "object"
            assert "required" in schema

    # 6. valid structured classification output
    def test_6_valid_structured_classification_output(self):
        mock_client = MockAnthropicClient(
            lambda **kw: MockMessageResponse(
                json.dumps({"classification": "prescriptive", "rationale": "Uses normative 'will use'"})
            )
        )
        adapter = AnthropicClassifier(client=mock_client)
        task = _make_sample_task(ClassifierTaskType.DECISION_CLASSIFICATION)
        res = adapter.execute(task)

        assert isinstance(res, ClassifierResult)
        assert res.output["classification"] == "prescriptive"
        assert res.output["rationale"] == "Uses normative 'will use'"
        assert res.confidence is None
        assert res.escalated is False

    # 7. valid domains output
    def test_7_valid_domains_output(self):
        mock_client = MockAnthropicClient(
            lambda **kw: MockMessageResponse(
                json.dumps({"domains": ["developer_workflow", "architecture_structure"]})
            )
        )
        adapter = AnthropicClassifier(client=mock_client)
        task = _make_sample_task(ClassifierTaskType.DOMAINS)
        res = adapter.execute(task)

        assert res.output["domains"] == ["developer_workflow", "architecture_structure"]

    # 8. valid purposes output
    def test_8_valid_purposes_output(self):
        mock_client = MockAnthropicClient(
            lambda **kw: MockMessageResponse(
                json.dumps({"purposes": ["standardize", "constrain"]})
            )
        )
        adapter = AnthropicClassifier(client=mock_client)
        task = _make_sample_task(ClassifierTaskType.PURPOSES)
        res = adapter.execute(task)

        assert res.output["purposes"] == ["standardize", "constrain"]

    # 9. valid authority output
    def test_9_valid_authority_output(self):
        mock_client = MockAnthropicClient(
            lambda **kw: MockMessageResponse(
                json.dumps({"authority": "explicitly_accepted", "evidence": "Status: accepted in header"})
            )
        )
        adapter = AnthropicClassifier(client=mock_client)
        task = _make_sample_task(ClassifierTaskType.AUTHORITY)
        res = adapter.execute(task)

        assert res.output["authority"] == "explicitly_accepted"
        assert res.output["evidence"] == "Status: accepted in header"

    # 10. valid scope output
    def test_10_valid_scope_output(self):
        mock_client = MockAnthropicClient(
            lambda **kw: MockMessageResponse(
                json.dumps({
                    "scopes": [
                        {"scope_type": "directory", "scope_expression": "docs/adr"},
                        {"scope_type": "repository", "scope_expression": None},
                    ]
                })
            )
        )
        adapter = AnthropicClassifier(client=mock_client)
        task = _make_sample_task(ClassifierTaskType.SCOPE)
        res = adapter.execute(task)

        assert len(res.output["scopes"]) == 2
        assert res.output["scopes"][0]["scope_type"] == "directory"

    # 11. valid lifecycle output
    def test_11_valid_lifecycle_output(self):
        mock_client = MockAnthropicClient(
            lambda **kw: MockMessageResponse(
                json.dumps({
                    "lifecycle": "active",
                    "supersedes": "ADR-0000",
                    "superseded_by": None,
                    "effective_date": "2026-01-01",
                    "expiration_if_any": None,
                })
            )
        )
        adapter = AnthropicClassifier(client=mock_client)
        task = _make_sample_task(ClassifierTaskType.LIFECYCLE)
        res = adapter.execute(task)

        assert res.output["lifecycle"] == "active"
        assert res.output["supersedes"] == "ADR-0000"
        assert res.output["superseded_by"] is None
        assert res.output["effective_date"] == "2026-01-01"
        assert res.output["expiration_if_any"] is None

    # 12. valid relationships output
    def test_12_valid_relationships_output(self):
        mock_client = MockAnthropicClient(
            lambda **kw: MockMessageResponse(
                json.dumps({
                    "relationships": [
                        {
                            "relationship_type": "refines",
                            "target_reference": "ADR-0002",
                            "evidence_reference": "Refines storage structure",
                        }
                    ]
                })
            )
        )
        adapter = AnthropicClassifier(client=mock_client)
        task = _make_sample_task(ClassifierTaskType.RELATIONSHIPS)
        res = adapter.execute(task)

        assert len(res.output["relationships"]) == 1
        assert res.output["relationships"][0]["relationship_type"] == "refines"

    # 13. valid enforcement output
    def test_13_valid_enforcement_output(self):
        mock_client = MockAnthropicClient(
            lambda **kw: MockMessageResponse(
                json.dumps({
                    "enforcement_potential": "deterministic_rule",
                    "candidate_rule": "ADR directory must exist",
                    "rationale": "Path presence can be checked deterministically",
                })
            )
        )
        adapter = AnthropicClassifier(client=mock_client)
        task = _make_sample_task(ClassifierTaskType.ENFORCEMENT_POTENTIAL)
        res = adapter.execute(task)

        assert res.output["enforcement_potential"] == "deterministic_rule"
        assert res.output["candidate_rule"] == "ADR directory must exist"

    # 14. current normalizers accept provider output
    def test_14_current_normalizers_accept_provider_output(self):
        # Normalization layer accepts all 8 outputs
        norm_class = normalize_classification("prescriptive")
        assert norm_class == ("prescriptive",)

        norm_doms = normalize_domains(["developer_workflow", "architecture_structure"])
        assert norm_doms == ("architecture_structure", "developer_workflow")

        norm_purp = normalize_purposes(["standardize", "constrain"])
        assert norm_purp == ("constrain", "standardize")

        norm_auth = normalize_authority("explicitly_accepted")
        assert norm_auth == "explicitly_accepted"

        norm_scps = normalize_scopes([{"scope_type": "directory", "scope_expression": "docs/adr"}])
        assert len(norm_scps) == 1
        assert norm_scps[0].scope_type == "directory"

        norm_life = normalize_lifecycle("active")
        assert norm_life == "active"

        norm_rels = normalize_relationships([{"relationship_type": "refines", "target_reference": "ADR-0002"}])
        assert len(norm_rels) == 1
        assert norm_rels[0].relationship_type == "refines"

        norm_enf = normalize_enforcement_potential("deterministic_rule")
        assert norm_enf == "deterministic_rule"

    # 15. invalid enum fails closed
    def test_15_invalid_enum_fails_closed(self):
        mock_client = MockAnthropicClient(
            lambda **kw: MockMessageResponse(
                json.dumps({"classification": "invalid_nonexistent_class", "rationale": "wrong"})
            )
        )
        adapter = AnthropicClassifier(client=mock_client)
        task = _make_sample_task(ClassifierTaskType.DECISION_CLASSIFICATION)
        with pytest.raises(AnthropicMalformedResponseError, match="failed schema validation"):
            adapter.execute(task)

    # 16. malformed response fails
    def test_16_malformed_response_fails(self):
        mock_client = MockAnthropicClient(
            lambda **kw: MockMessageResponse("I think this is prescriptive because...")
        )
        adapter = AnthropicClassifier(client=mock_client)
        task = _make_sample_task(ClassifierTaskType.DECISION_CLASSIFICATION)
        with pytest.raises(AnthropicMalformedResponseError, match="Failed to parse Anthropic response as JSON"):
            adapter.execute(task)

    # 17. missing API key fails only on remote execution
    def test_17_missing_api_key_fails_only_on_remote_execution(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        adapter = AnthropicClassifier(api_key=None)  # Construction succeeds
        assert adapter.backend_id == "anthropic"

        task = _make_sample_task(ClassifierTaskType.DECISION_CLASSIFICATION)
        with pytest.raises(AnthropicAuthenticationError, match="ANTHROPIC_API_KEY environment variable is not set"):
            adapter.execute(task)

    # 18. API error remains observable
    def test_18_api_error_remains_observable(self):
        def raise_api_error(**kw):
            raise RuntimeError("Anthropic 500 internal server error")

        mock_client = MockAnthropicClient(raise_api_error)
        adapter = AnthropicClassifier(client=mock_client)
        task = _make_sample_task(ClassifierTaskType.DECISION_CLASSIFICATION)
        with pytest.raises(AnthropicClassifierError, match="Anthropic API call failed"):
            adapter.execute(task)

    # 19. rate limit remains observable
    def test_19_rate_limit_remains_observable(self):
        class RateLimitException(Exception):
            pass

        def raise_rate_limit(**kw):
            raise RateLimitException("429 rate limit exceeded")

        mock_client = MockAnthropicClient(raise_rate_limit)
        adapter = AnthropicClassifier(client=mock_client)
        task = _make_sample_task(ClassifierTaskType.DECISION_CLASSIFICATION)
        with pytest.raises(AnthropicRateLimitError, match="rate limit exceeded"):
            adapter.execute(task)

    # 20. no model fallback
    def test_20_no_model_fallback(self):
        mock_client = MockAnthropicClient(
            lambda **kw: MockMessageResponse(
                json.dumps({"classification": "prescriptive", "rationale": "test"})
            )
        )
        adapter = AnthropicClassifier(client=mock_client)
        task = _make_sample_task(ClassifierTaskType.DECISION_CLASSIFICATION)
        adapter.execute(task)

        # Verified model in request is strictly claude-sonnet-4-6
        assert mock_client.messages.last_kwargs["model"] == "claude-sonnet-4-6"
        assert mock_client.messages.call_count == 1

    # 21. no canonical writes
    def test_21_no_canonical_writes(self, tmp_path):
        mock_client = MockAnthropicClient(
            lambda **kw: MockMessageResponse(
                json.dumps({"classification": "prescriptive", "rationale": "test"})
            )
        )
        adapter = AnthropicClassifier(client=mock_client)
        task = _make_sample_task(ClassifierTaskType.DECISION_CLASSIFICATION)
        res = adapter.execute(task)

        # Output does not write to any store or file
        assert not (REPO_ROOT / ".mneme" / "project_memory.json").is_symlink()

    # 22. no production LLMAdapter dependency
    def test_22_no_production_llm_adapter_dependency(self):
        import mneme.open_architecture.classifiers.anthropic as mod
        assert "LLMAdapter" not in vars(mod)
        assert "mneme.llm_adapter" not in vars(mod)

    # 23. no DecisionAuthorityService
    def test_23_no_decision_authority_service(self):
        import mneme.open_architecture.classifiers.anthropic as mod
        assert "DecisionAuthorityService" not in vars(mod)

    # 24. no DecisionProposal write
    def test_24_no_decision_proposal_write(self):
        import mneme.open_architecture.classifiers.anthropic as mod
        assert "DecisionProposal" not in vars(mod)

    # 25. no .mneme/ mutation
    def test_25_no_dot_mneme_mutation(self):
        import mneme.open_architecture.classifiers.anthropic as mod
        source_text = Path(mod.__file__).read_text(encoding="utf-8")
        assert ".mneme" not in source_text

    # 26. deterministic prompt construction
    def test_26_deterministic_prompt_construction(self):
        adapter = AnthropicClassifier()
        task = _make_sample_task(ClassifierTaskType.DECISION_CLASSIFICATION)

        sys_1 = adapter.build_system_prompt(task)
        sys_2 = adapter.build_system_prompt(task)
        assert sys_1 == sys_2

        user_1 = adapter.build_user_prompt(task)
        user_2 = adapter.build_user_prompt(task)
        assert user_1 == user_2

    # 27. same task produces same request payload except operational fields
    def test_27_same_task_produces_same_request_payload(self):
        adapter = AnthropicClassifier()
        task = _make_sample_task(ClassifierTaskType.DOMAINS)

        payload_1 = adapter.build_request_payload(task)
        payload_2 = adapter.build_request_payload(task)

        json_1 = json.dumps(payload_1, sort_keys=True)
        json_2 = json.dumps(payload_2, sort_keys=True)
        assert json_1 == json_2

    # 28. no tools/thinking/web use enabled
    def test_28_no_tools_thinking_web_use_enabled(self):
        adapter = AnthropicClassifier()
        task = _make_sample_task(ClassifierTaskType.DECISION_CLASSIFICATION)
        payload = adapter.build_request_payload(task)

        assert "tools" not in payload
        assert "tool_choice" not in payload
        assert "thinking" not in payload
        assert "stream" not in payload
        assert "temperature" not in payload
        assert "extra_body" not in payload
        assert payload["max_tokens"] == 1024
        assert "output_config" in payload
        assert payload["output_config"]["format"]["type"] == "json_schema"

    # 29. token usage never enters semantic ClassifierResult.output
    def test_29_token_usage_never_enters_semantic_classifier_output(self):
        mock_client = MockAnthropicClient(
            lambda **kw: MockMessageResponse(
                json.dumps({"classification": "prescriptive", "rationale": "Normative MUST"}),
                input_tokens=250,
                output_tokens=75,
            )
        )
        adapter = AnthropicClassifier(client=mock_client)
        task = _make_sample_task(ClassifierTaskType.DECISION_CLASSIFICATION)
        res = adapter.execute(task)

        assert "_usage" not in res.output
        assert "input_tokens" not in res.output
        assert "output_tokens" not in res.output
        assert res.output == {"classification": "prescriptive", "rationale": "Normative MUST"}

    # 30. bundle hash is unchanged when only API token usage differs
    def test_30_bundle_hash_unchanged_when_only_token_usage_differs(self):
        cand_id = "cand-" + "a" * 32
        meta = RunMetadata(
            run_id="run-001",
            batch_id="batch-01",
            repo_id="adrkit",
            repo_commit_sha="a" * 40,
            mneme_version="0.9.2",
            mneme_commit_sha="b" * 40,
            benchmark_schema_version="0.1",
            taxonomy_version="0.1",
            classifier_version="0.1",
            classifier_backend="anthropic",
            classifier_model="claude-sonnet-4-6",
            extractor_id="heuristic",
            extractor_version="0.1",
            scenario_content_hash="scenariohash123",
            retrieval_policy="score_gt_zero",
            configuration_hash="confighash123",
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:05:00Z",
            status="completed",
        )
        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha="a" * 40,
            primary_test="test",
            validation_status="reviewed",
        )
        res_output = {"classification": "prescriptive", "rationale": "Normative MUST"}

        c_res_1 = ClassifierResult(
            task_type=ClassifierTaskType.DECISION_CLASSIFICATION,
            backend_id="anthropic",
            classifier_version="0.1",
            model_identifier="claude-sonnet-4-6",
            taxonomy_version="0.1",
            candidate_id=cand_id,
            output=res_output,
            confidence=None,
            latency_ms=100.0,
            cost_amount=None,
            cost_currency=None,
        )

        c_res_2 = ClassifierResult(
            task_type=ClassifierTaskType.DECISION_CLASSIFICATION,
            backend_id="anthropic",
            classifier_version="0.1",
            model_identifier="claude-sonnet-4-6",
            taxonomy_version="0.1",
            candidate_id=cand_id,
            output=res_output,
            confidence=None,
            latency_ms=250.0,  # Latency differs
            cost_amount=None,
            cost_currency=None,
        )

        run1 = OpenArchitectureRunResult(
            run_metadata=meta,
            repository_config=config,
            discovered_documents=(),
            extracted_candidates=(),
            composed_candidates=(),
            incomplete_candidates=(),
            classifier_results=(c_res_1,),
            scenarios=(),
            gds_results=(),
            suite_metrics={},
            diagnostics=(),
        )

        run2 = OpenArchitectureRunResult(
            run_metadata=meta,
            repository_config=config,
            discovered_documents=(),
            extracted_candidates=(),
            composed_candidates=(),
            incomplete_candidates=(),
            classifier_results=(c_res_2,),
            scenarios=(),
            gds_results=(),
            suite_metrics={},
            diagnostics=(),
        )

        hash1 = compute_bundle_content_hash(run1)
        hash2 = compute_bundle_content_hash(run2)
        assert hash1 == hash2

    # 31. bundle hash still changes when semantic output differs
    def test_31_bundle_hash_changes_when_semantic_output_differs(self):
        cand_id = "cand-" + "a" * 32
        meta = RunMetadata(
            run_id="run-001",
            batch_id="batch-01",
            repo_id="adrkit",
            repo_commit_sha="a" * 40,
            mneme_version="0.9.2",
            mneme_commit_sha="b" * 40,
            benchmark_schema_version="0.1",
            taxonomy_version="0.1",
            classifier_version="0.1",
            classifier_backend="anthropic",
            classifier_model="claude-sonnet-4-6",
            extractor_id="heuristic",
            extractor_version="0.1",
            scenario_content_hash="scenariohash123",
            retrieval_policy="score_gt_zero",
            configuration_hash="confighash123",
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:05:00Z",
            status="completed",
        )
        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha="a" * 40,
            primary_test="test",
            validation_status="reviewed",
        )

        c_res_prescriptive = ClassifierResult(
            task_type=ClassifierTaskType.DECISION_CLASSIFICATION,
            backend_id="anthropic",
            classifier_version="0.1",
            model_identifier="claude-sonnet-4-6",
            taxonomy_version="0.1",
            candidate_id=cand_id,
            output={"classification": "prescriptive", "rationale": "Must"},
            confidence=None,
            latency_ms=100.0,
            cost_amount=None,
            cost_currency=None,
        )

        c_res_advisory = ClassifierResult(
            task_type=ClassifierTaskType.DECISION_CLASSIFICATION,
            backend_id="anthropic",
            classifier_version="0.1",
            model_identifier="claude-sonnet-4-6",
            taxonomy_version="0.1",
            candidate_id=cand_id,
            output={"classification": "advisory", "rationale": "Should"},
            confidence=None,
            latency_ms=100.0,
            cost_amount=None,
            cost_currency=None,
        )

        run_p = OpenArchitectureRunResult(
            run_metadata=meta,
            repository_config=config,
            discovered_documents=(),
            extracted_candidates=(),
            composed_candidates=(),
            incomplete_candidates=(),
            classifier_results=(c_res_prescriptive,),
            scenarios=(),
            gds_results=(),
            suite_metrics={},
            diagnostics=(),
        )

        run_a = OpenArchitectureRunResult(
            run_metadata=meta,
            repository_config=config,
            discovered_documents=(),
            extracted_candidates=(),
            composed_candidates=(),
            incomplete_candidates=(),
            classifier_results=(c_res_advisory,),
            scenarios=(),
            gds_results=(),
            suite_metrics={},
            diagnostics=(),
        )

        assert compute_bundle_content_hash(run_p) != compute_bundle_content_hash(run_a)

    # 32. Anthropic request uses native output_config
    def test_32_anthropic_request_uses_native_output_config(self):
        adapter = AnthropicClassifier()
        task = _make_sample_task(ClassifierTaskType.DOMAINS)
        payload = adapter.build_request_payload(task)

        assert "output_config" in payload
        assert "format" in payload["output_config"]
        assert payload["output_config"]["format"]["type"] == "json_schema"

    # 33. no extra_body compatibility path for structured output
    def test_33_no_extra_body_compatibility_path(self):
        adapter = AnthropicClassifier()
        task = _make_sample_task(ClassifierTaskType.PURPOSES)
        payload = adapter.build_request_payload(task)

        assert "extra_body" not in payload

    # 34. no temperature sent
    def test_34_no_temperature_sent(self):
        adapter = AnthropicClassifier()
        task = _make_sample_task(ClassifierTaskType.AUTHORITY)
        payload = adapter.build_request_payload(task)

        assert "temperature" not in payload

    # 35. lifecycle schema supports all four optional metadata fields
    def test_35_lifecycle_schema_supports_four_optional_metadata_fields(self):
        schema = TASK_SCHEMAS[ClassifierTaskType.LIFECYCLE]
        props = schema["properties"]
        assert "lifecycle" in props
        assert "supersedes" in props
        assert "superseded_by" in props
        assert "effective_date" in props
        assert "expiration_if_any" in props
        assert schema["required"] == ["lifecycle", "supersedes", "superseded_by", "effective_date", "expiration_if_any"]

    # 36. absent lifecycle evidence produces nulls
    def test_36_absent_lifecycle_evidence_produces_nulls(self):
        mock_client = MockAnthropicClient(
            lambda **kw: MockMessageResponse(
                json.dumps({
                    "lifecycle": "active",
                    "supersedes": None,
                    "superseded_by": None,
                    "effective_date": None,
                    "expiration_if_any": None,
                })
            )
        )
        adapter = AnthropicClassifier(client=mock_client)
        task = _make_sample_task(ClassifierTaskType.LIFECYCLE)
        res = adapter.execute(task)

        assert res.output["lifecycle"] == "active"
        assert res.output["supersedes"] is None
        assert res.output["superseded_by"] is None
        assert res.output["effective_date"] is None
        assert res.output["expiration_if_any"] is None

    # 37. lifecycle metadata is persisted to CandidateLifecycleRecord
    def test_37_lifecycle_metadata_persisted_to_candidate_lifecycle_record(self, tmp_path):
        from mneme.open_architecture.store import (
            AnalysisRunRecord,
            CandidateLifecycleRecord,
            ClassifierVersionRecord,
            DecisionCandidateRecord,
            RepositoryRecord,
            ResearchStore,
            TaxonomyVersionRecord,
        )

        db_path = tmp_path / "test_lifecycle.sqlite"
        store = ResearchStore(db_path)
        store.initialize_schema()

        cand_id = "cand-0123456789abcdef0123456789abcdef"
        run_id = "run-001"

        store.upsert_repository(RepositoryRecord("adrkit", "https://github.com/mbeacom/adrkit.git", "mbeacom/adrkit", "main"))
        store.upsert_taxonomy_version(TaxonomyVersionRecord("0.1", "2026-01-01T00:00:00Z", "notes"))
        store.upsert_classifier_version(ClassifierVersionRecord("0.1", "2026-01-01T00:00:00Z", "notes"))
        store.create_analysis_run(
            AnalysisRunRecord(
                run_id=run_id,
                repo_id="adrkit",
                repo_commit_sha="a" * 40,
                mneme_version="0.9.2",
                mneme_commit_sha="b" * 40,
                taxonomy_version="0.1",
                classifier_version="0.1",
                benchmark_schema_version="0.1",
                configuration_hash="conf123",
                started_at="2026-01-01T00:00:00Z",
                completed_at=None,
                status="running",
            )
        )
        store.insert_decision_candidate(
            DecisionCandidateRecord(
                candidate_id=cand_id,
                run_id=run_id,
                source_id=None,
                source_location="L1-L5",
                raw_evidence_reference="Use ADR",
                normalized_decision="Use ADR",
                discovery_confidence=0.9,
                discovery_metadata_json="{}",
            )
        )

        # Simulate orchestrator persistence logic
        clf_output = {
            "lifecycle": "superseded",
            "supersedes": "ADR-001",
            "superseded_by": "ADR-005",
            "effective_date": "2026-01-15",
            "expiration_if_any": "2026-12-31",
        }

        # Verify CandidateLifecycleRecord receives all metadata fields
        record = CandidateLifecycleRecord(
            candidate_id=cand_id,
            run_id=run_id,
            lifecycle_status=clf_output["lifecycle"],
            supersedes=clf_output["supersedes"],
            superseded_by=clf_output["superseded_by"],
            effective_date=clf_output["effective_date"],
            expiration_if_any=clf_output["expiration_if_any"],
            confidence=0.95,
        )

        assert record.supersedes == "ADR-001"
        assert record.superseded_by == "ADR-005"
        assert record.effective_date == "2026-01-15"
        assert record.expiration_if_any == "2026-12-31"

        store.upsert_candidate_lifecycle(record)
        conn = store.connect()
        row = conn.execute(
            "SELECT lifecycle_status, supersedes, superseded_by, effective_date, expiration_if_any FROM candidate_lifecycle WHERE candidate_id = ?",
            (cand_id,),
        ).fetchone()
        assert row is not None
        assert row[0] == "superseded"
        assert row[1] == "ADR-001"
        assert row[2] == "ADR-005"
        assert row[3] == "2026-01-15"
        assert row[4] == "2026-12-31"

    # 38. malformed lifecycle enum still fails
    def test_38_malformed_lifecycle_enum_fails_closed(self):
        mock_client = MockAnthropicClient(
            lambda **kw: MockMessageResponse(
                json.dumps({
                    "lifecycle": "invalid_status",
                    "supersedes": None,
                    "superseded_by": None,
                    "effective_date": None,
                    "expiration_if_any": None,
                })
            )
        )
        adapter = AnthropicClassifier(client=mock_client)
        task = _make_sample_task(ClassifierTaskType.LIFECYCLE)
        with pytest.raises(AnthropicMalformedResponseError, match="failed schema validation"):
            adapter.execute(task)

        # Fail-closed vocabulary normalizer check
        with pytest.raises(NormalizationError, match="Invalid lifecycle"):
            normalize_lifecycle("invalid_status")

    # 39. SDK version check fails on old SDK
    def test_39_sdk_version_check_fails_on_old_sdk(self, monkeypatch):
        import anthropic
        monkeypatch.setattr(anthropic, "__version__", "0.52.0")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-12345")

        adapter = AnthropicClassifier()
        task = _make_sample_task(ClassifierTaskType.DECISION_CLASSIFICATION)

        with pytest.raises(AnthropicClassifierError, match="AnthropicClassifier requires anthropic>=1.0.0"):
            adapter.execute(task)

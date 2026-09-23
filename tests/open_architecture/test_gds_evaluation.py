"""
tests.open_architecture.test_gds_evaluation — Tests for Governing Decision Set evaluation.

Covers items 14-41 of O1A2.4 required coverage:
- Scenario query rendering (golden output, determinism, null handling)
- Retrieval behavior with frozen DecisionRetriever (positive score, no top-K truncation, empty token fallback)
- Metrics computation (perfect match, partial, missed, false positive, empty sets)
- Architectural boundary enforcement
- End-to-end integration pipeline
"""

from __future__ import annotations

import pytest

from mneme.decision_retriever import DecisionRetriever
from mneme.open_architecture.candidates import (
    ExtractedCandidate,
    LineSpan,
    build_decision_candidate,
)
from mneme.open_architecture.classification import (
    ClassifierTask,
    ClassifierTaskType,
    StaticClassifier,
    build_source_context,
    normalize_authority,
    normalize_classification,
    normalize_domains,
)
from mneme.open_architecture.discovery import DiscoveredSourceDocument
from mneme.open_architecture.gds_evaluation import (
    GoverningDecisionSetResult,
    compute_suite_gds_metrics,
    evaluate_governing_decisions,
    evaluate_governing_decisions_batch,
    render_scenario_query,
)
from mneme.open_architecture.projection import project_candidate_to_decision
from mneme.open_architecture.schemas import (
    ApplicabilityScenario,
    ChangeContext,
    DecisionCandidate,
    Scope,
)


# ── Helpers & Fixtures ─────────────────────────────────────────────────────────


def _make_candidate(
    candidate_id: str,
    normalized_decision: str,
    raw_statement: str = "",
    scopes: tuple[Scope, ...] = (),
) -> DecisionCandidate:
    return DecisionCandidate(
        candidate_id=candidate_id,
        repository="MnemeHQ/mneme",
        source_file="docs/adr/ADR-001.md",
        source_location="L1-L10",
        raw_statement=raw_statement or normalized_decision,
        normalized_decision=normalized_decision,
        classification="prescriptive",
        decision_domains=("persistence",),
        decision_purposes=("constrain",),
        authority_status="explicitly_accepted",
        authority_evidence=None,
        scopes=scopes,
        lifecycle_status="active",
        relationships=(),
        enforcement_potential="deterministic_rule",
        candidate_rule=None,
        confidence=0.9,
        human_validation_status="unreviewed",
        human_corrections=None,
    )


def _make_scenario(
    scenario_id: str = "scn-test-001",
    description: str = "Implement SQLite research store adapter",
    path: str | None = "mneme/open_architecture/store.py",
    component: str | None = "storage",
    change_type: str | None = "feature",
    dependencies: tuple[str, ...] = ("sqlite3",),
    api: str | None = "store",
    technology: str | None = "Python",
    other_context: str | None = "Must preserve research boundaries",
    expected_ids: tuple[str, ...] = ("cand-sqlite-001",),
) -> ApplicabilityScenario:
    return ApplicabilityScenario(
        scenario_id=scenario_id,
        repository="MnemeHQ/mneme",
        description=description,
        change_context=ChangeContext(
            path=path,
            component=component,
            change_type=change_type,
            dependencies=dependencies,
            api=api,
            technology=technology,
            other_context=other_context,
        ),
        expected_governing_decision_ids=expected_ids,
        mneme_governing_decision_ids=(),
        human_notes=None,
        validation_state="unreviewed",
    )


# ── Scenario Rendering Tests ───────────────────────────────────────────────────


class TestScenarioQueryRendering:
    # 14. exact golden query output
    def test_golden_query_output(self):
        scenario = _make_scenario()
        query = render_scenario_query(scenario)

        expected_golden = (
            "Implement SQLite research store adapter\n"
            "path: mneme/open_architecture/store.py\n"
            "component: storage\n"
            "change_type: feature\n"
            "dependencies: sqlite3\n"
            "api: store\n"
            "technology: Python\n"
            "Must preserve research boundaries"
        )
        assert query == expected_golden

    # 15. null optional fields deterministic
    def test_null_optional_fields_deterministic(self):
        scenario = _make_scenario(
            path=None,
            component=None,
            change_type=None,
            dependencies=(),
            api=None,
            technology=None,
            other_context=None,
        )
        query = render_scenario_query(scenario)
        # Only description appears when optional fields are None
        assert query == "Implement SQLite research store adapter"

    # 16. dependencies deterministic ordering
    def test_dependencies_deterministic_ordering(self):
        # Different input orders must produce the exact same rendered query
        sc1 = _make_scenario(dependencies=("sqlite3", "pytest", "pydantic"))
        sc2 = _make_scenario(dependencies=("pydantic", "sqlite3", "pytest"))

        q1 = render_scenario_query(sc1)
        q2 = render_scenario_query(sc2)
        assert q1 == q2
        assert "dependencies: pydantic, pytest, sqlite3" in q1

    # 17. same scenario → byte-identical query
    def test_same_scenario_byte_identical(self):
        scenario = _make_scenario()
        q1 = render_scenario_query(scenario)
        q2 = render_scenario_query(scenario)
        assert q1 == q2
        assert q1.encode("utf-8") == q2.encode("utf-8")

    # 18. no semantic rewriting/synonym expansion
    def test_no_synonym_expansion(self):
        desc = "Do not use PostgreSQL for storage"
        scenario = _make_scenario(description=desc)
        query = render_scenario_query(scenario)
        # Should not expand 'PostgreSQL' into 'postgres' or 'pg'
        assert "postgres" not in query.splitlines()[0]
        assert "PostgreSQL" in query.splitlines()[0]


# ── Retrieval Behavior Tests ───────────────────────────────────────────────────


class TestRetrievalBehavior:
    # 19. actual DecisionRetriever is used
    def test_actual_decision_retriever_used(self, monkeypatch):
        import mneme.open_architecture.gds_evaluation as gds_mod

        called = False
        original_retriever_init = DecisionRetriever.__init__

        def _spy_init(self, decisions):
            nonlocal called
            called = True
            original_retriever_init(self, decisions)

        monkeypatch.setattr(DecisionRetriever, "__init__", _spy_init)

        cand = _make_candidate("cand-1", "Use SQLite database")
        scenario = _make_scenario(expected_ids=("cand-1",))
        evaluate_governing_decisions([cand], scenario)

        assert called, "DecisionRetriever.__init__ was not invoked"

    # 20. positive scores become predicted governing set
    def test_positive_scores_become_predicted(self):
        cand1 = _make_candidate("cand-1", "Use SQLite database for storage")
        cand2 = _make_candidate("cand-2", "Completely unrelated networking topic")
        scenario = _make_scenario(expected_ids=("cand-1",))

        res = evaluate_governing_decisions([cand1, cand2], scenario)
        # cand1 matches query keywords (sqlite, storage) so score > 0
        assert "cand-1" in res.predicted_governing_decision_ids
        assert res.retrieval_scores[res.retrieved_ids.index("cand-1")] > 0

    # 21. zero-score decisions excluded
    def test_zero_score_decisions_excluded(self):
        cand_match = _make_candidate("cand-match", "Implement SQLite store storage")
        cand_zero = _make_candidate("cand-zero", "Quantum entanglement telemetry")
        scenario = _make_scenario(expected_ids=("cand-match",))

        res = evaluate_governing_decisions([cand_match, cand_zero], scenario)
        assert "cand-match" in res.predicted_governing_decision_ids
        assert "cand-zero" not in res.predicted_governing_decision_ids

    # 22. retrieval ordering preserved separately
    def test_retrieval_ordering_preserved_separately(self):
        cand1 = _make_candidate("cand-high", "SQLite storage adapter implementation", scopes=(Scope("repository", "storage"),))
        cand2 = _make_candidate("cand-low", "SQLite usage")
        scenario = _make_scenario(expected_ids=("cand-high", "cand-low"))

        res = evaluate_governing_decisions([cand1, cand2], scenario)
        # All retrieved IDs and their scores are recorded in rank order
        assert len(res.retrieved_ids) == 2
        assert len(res.retrieval_scores) == 2
        assert res.retrieval_scores[0] >= res.retrieval_scores[1]

    # 23. duplicate candidate IDs fail closed
    def test_duplicate_candidate_ids_fail_closed(self):
        cand1 = _make_candidate("cand-dup", "Decision A")
        cand2 = _make_candidate("cand-dup", "Decision B")
        scenario = _make_scenario()

        with pytest.raises(ValueError, match="Duplicate candidate_id"):
            evaluate_governing_decisions([cand1, cand2], scenario)

    # 24. no hidden top-K truncation
    def test_no_hidden_top_k_truncation(self):
        # Create 10 candidates that all match keywords
        cands = [
            _make_candidate(f"cand-{i:02d}", f"SQLite storage component variant {i}")
            for i in range(10)
        ]
        scenario = _make_scenario(expected_ids=tuple(f"cand-{i:02d}" for i in range(10)))

        res = evaluate_governing_decisions(cands, scenario)
        # All 10 with score > 0 must be in predicted, not truncated at K=3
        assert len(res.predicted_governing_decision_ids) == 10
        assert res.recall == 1.0

    # 25. frozen empty-token fallback remains observable
    def test_empty_token_fallback_remains_observable(self):
        # When query has only punctuation or stopwords, DecisionRetriever assigns fallback score 1.0 to all
        cand1 = _make_candidate("cand-1", "Decision One")
        cand2 = _make_candidate("cand-2", "Decision Two")

        empty_query_scenario = _make_scenario(
            description="---",
            path=None,
            component=None,
            change_type=None,
            dependencies=(),
            api=None,
            technology=None,
            other_context=None,
            expected_ids=("cand-1",),
        )

        res = evaluate_governing_decisions([cand1, cand2], empty_query_scenario)
        # In empty query, DecisionRetriever gives all decisions fallback score 1.0
        assert len(res.predicted_governing_decision_ids) == 2
        assert all(s == 1.0 for s in res.retrieval_scores)


# ── Metrics Tests ──────────────────────────────────────────────────────────────


class TestMetricsComputation:
    # 26. perfect governing set
    def test_perfect_governing_set(self):
        cand1 = _make_candidate("cand-1", "SQLite storage adapter")
        scenario = _make_scenario(expected_ids=("cand-1",))

        res = evaluate_governing_decisions([cand1], scenario)
        assert res.precision == 1.0
        assert res.recall == 1.0
        assert res.f1 == 1.0
        assert res.overlap_count == 1

    # 27. partial overlap
    def test_partial_overlap(self):
        cand1 = _make_candidate("cand-1", "SQLite storage adapter")
        cand2 = _make_candidate("cand-2", "Python technology choice")
        # Expected: cand-1 and cand-missing
        # Predicted: cand-1 and cand-2 (both match query keywords)
        scenario = _make_scenario(expected_ids=("cand-1", "cand-missing"))

        res = evaluate_governing_decisions([cand1, cand2], scenario)
        # Expected: 2 (cand-1, cand-missing)
        # Predicted: 2 (cand-1, cand-2)
        # Overlap: 1 (cand-1)
        assert res.expected_count == 2
        assert res.predicted_count == 2
        assert res.overlap_count == 1
        assert res.precision == 0.5
        assert res.recall == 0.5
        assert res.f1 == 0.5

    # 28. missed expected decision
    def test_missed_expected_decision(self):
        # Candidate does not match query tokens
        cand_unrelated = _make_candidate("cand-unrelated", "Telemetry network monitoring")
        scenario = _make_scenario(expected_ids=("cand-expected-missing",))

        res = evaluate_governing_decisions([cand_unrelated], scenario)
        assert res.recall == 0.0
        assert res.f1 == 0.0

    # 29. false-positive candidate
    def test_false_positive_candidate(self):
        # Matches query tokens but was not expected
        cand_fp = _make_candidate("cand-fp", "SQLite storage feature")
        scenario = _make_scenario(expected_ids=("cand-other-id",))

        res = evaluate_governing_decisions([cand_fp], scenario)
        assert "cand-fp" in res.predicted_governing_decision_ids
        assert res.precision == 0.0
        assert res.recall == 0.0
        assert res.f1 == 0.0

    # 30. empty expected set (vacuous truth in GDS metrics)
    def test_empty_expected_set(self):
        cand = _make_candidate("cand-1", "SQLite storage")
        scenario = _make_scenario()
        object.__setattr__(scenario, "expected_governing_decision_ids", ())

        res = evaluate_governing_decisions([cand], scenario)
        assert res.expected_count == 0
        # If predicted non-empty but expected empty: precision=0.0, recall=1.0, f1=0.0
        assert res.precision == 0.0
        assert res.recall == 1.0
        assert res.f1 == 0.0

    # 31. empty predicted set
    def test_empty_predicted_set(self):
        scenario = _make_scenario(expected_ids=("cand-1",))
        # No candidates in corpus
        res = evaluate_governing_decisions([], scenario)
        assert res.predicted_count == 0
        assert res.precision == 1.0  # Vacuous precision
        assert res.recall == 0.0
        assert res.f1 == 0.0

    # 32. expected ID absent from corpus counts as missed
    def test_expected_id_absent_from_corpus_counts_as_missed(self):
        cand1 = _make_candidate("cand-present", "SQLite storage")
        # Expected includes 'cand-absent' which does not exist in corpus
        scenario = _make_scenario(expected_ids=("cand-present", "cand-absent"))

        res = evaluate_governing_decisions([cand1], scenario)
        assert res.expected_count == 2
        assert "cand-absent" not in res.predicted_governing_decision_ids
        assert res.overlap_count == 1
        assert res.recall == 0.5

    # 33. expected labels never modified
    def test_expected_labels_never_modified(self):
        expected_tuple = ("cand-1", "cand-2")
        scenario = _make_scenario(expected_ids=expected_tuple)

        res = evaluate_governing_decisions([], scenario)
        # Original scenario's expected IDs remain immutable
        assert scenario.expected_governing_decision_ids == expected_tuple
        assert res.expected_governing_decision_ids == expected_tuple

    def test_suite_aggregation(self):
        cand = _make_candidate("cand-1", "SQLite storage")
        sc1 = _make_scenario("sc-1", expected_ids=("cand-1",))
        sc2 = _make_scenario("sc-2", expected_ids=("cand-absent",))

        results = evaluate_governing_decisions_batch([cand], [sc1, sc2])
        assert len(results) == 2

        suite_metrics = compute_suite_gds_metrics(results)
        assert "macro_precision" in suite_metrics
        assert "macro_recall" in suite_metrics
        assert "macro_f1" in suite_metrics


# ── Architectural Boundaries Tests ────────────────────────────────────────────


class TestArchitecturalBoundaries:
    # 34. no ConflictDetector use
    def test_no_conflict_detector_used(self):
        import mneme.open_architecture.gds_evaluation as gds_mod
        import mneme.open_architecture.projection as proj_mod

        for mod in (gds_mod, proj_mod):
            assert "ConflictDetector" not in vars(mod)

    # 35. no Enforcer use
    def test_no_enforcer_used(self):
        import mneme.open_architecture.gds_evaluation as gds_mod
        import mneme.open_architecture.projection as proj_mod

        for mod in (gds_mod, proj_mod):
            assert "check_prompt" not in vars(mod)
            assert "enforce" not in vars(mod)

    # 36. no Audit use
    def test_no_audit_used(self):
        import mneme.open_architecture.gds_evaluation as gds_mod
        import mneme.open_architecture.projection as proj_mod

        for mod in (gds_mod, proj_mod):
            assert "audit" not in vars(mod)
            assert "assess_protection" not in vars(mod)

    # 37. no MemoryStore write
    def test_no_memory_store_used(self):
        import mneme.open_architecture.gds_evaluation as gds_mod
        import mneme.open_architecture.projection as proj_mod

        for mod in (gds_mod, proj_mod):
            assert "MemoryStore" not in vars(mod)

    # 38. no Decision Index write
    def test_no_decision_index_write(self):
        import mneme.open_architecture.gds_evaluation as gds_mod
        import mneme.open_architecture.projection as proj_mod

        for mod in (gds_mod, proj_mod):
            assert "DecisionIndex" not in vars(mod)

    # 39. no DecisionProposal write
    def test_no_decision_proposal_write(self):
        import mneme.open_architecture.gds_evaluation as gds_mod
        import mneme.open_architecture.projection as proj_mod

        for mod in (gds_mod, proj_mod):
            assert "DecisionProposal" not in vars(mod)
            assert "DecisionProposalStore" not in vars(mod)

    # 40. no .mneme/ mutation
    def test_no_mneme_mutation(self, tmp_path):
        cand = _make_candidate("cand-1", "SQLite storage")
        scenario = _make_scenario(expected_ids=("cand-1",))

        evaluate_governing_decisions([cand], scenario)
        assert not (tmp_path / ".mneme").exists()


# ── End-to-End Integration Pipeline Test ──────────────────────────────────────


class TestEndToEndPipeline:
    # 41. DiscoveredSourceDocument → ExtractedCandidate → StaticClassifier →
    #     composed DecisionCandidate → temporary projection → scenario query →
    #     DecisionRetriever → GDS metrics
    def test_full_offline_pipeline(self):
        # Step 1: Discovered document
        content = (
            "# Storage Architecture\n\n"
            "## Database Specification\n"
            "We decide to standardize on SQLite for research benchmark data storage.\n"
            "PostgreSQL is prohibited for local runs.\n"
        )
        import hashlib
        raw = content.encode("utf-8")
        doc = DiscoveredSourceDocument(
            relative_path="docs/storage.md",
            source_type="documentation",
            content_hash=f"sha256:{hashlib.sha256(raw).hexdigest()}",
            content=content,
            metadata={"byte_length": len(raw)},
        )

        # Step 2: Extracted candidate
        span = LineSpan(4, 5)
        extracted = ExtractedCandidate.from_source_document(
            doc=doc,
            repo_commit_sha="a" * 40,
            line_span=span,
            discovery_confidence=0.9,
        )

        # Step 3: Classifier outputs
        context = build_source_context(doc, span, context_lines=2)
        task = ClassifierTask.from_extracted_candidate(
            extracted=extracted,
            task_type=ClassifierTaskType.DECISION_CLASSIFICATION,
            source_context=context,
        )
        classifier = StaticClassifier(
            outputs={
                ClassifierTaskType.DECISION_CLASSIFICATION: {"classification": "prescriptive"},
            }
        )
        result = classifier.execute(task)
        norm_class = normalize_classification(result.output["classification"])

        # Step 4: Composed DecisionCandidate
        candidate = build_decision_candidate(
            extracted=extracted,
            classification=norm_class[0],
            decision_domains=("persistence",),
            decision_purposes=("standardize", "prohibit"),
            authority_status="candidate",
            scopes=(Scope(scope_type="repository", scope_expression="storage"),),
        )

        # Step 5: Applicability scenario
        scenario = _make_scenario(
            description="Implement SQLite storage adapter for benchmarks",
            expected_ids=(candidate.candidate_id,),
        )

        # Step 6: Temporary projection & GDS evaluation with DecisionRetriever
        eval_result = evaluate_governing_decisions([candidate], scenario)

        # Step 7: Verify GDS outcome
        assert eval_result.scenario_id == scenario.scenario_id
        assert candidate.candidate_id in eval_result.predicted_governing_decision_ids
        assert eval_result.precision == 1.0
        assert eval_result.recall == 1.0
        assert eval_result.f1 == 1.0

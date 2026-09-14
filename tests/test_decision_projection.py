"""D0 projection tests — Layer 1 parity gates G1-G5, G7, G9 (ADR-023).

Every gate compares the existing runtime output with the Decision-Index-
projected output over the same inputs. No frozen runtime module, benchmark
fixture, or memory file is modified by this suite.

The ADR-005 forbidden install literal is assembled at runtime
(``_ADR005_INPUT``) so this test file can exercise the real rule without
carrying the literal in its own bytes: a typed rule does not enforce against
its declaring ADR or policy memory, but any other new file carrying it is
blocked by the repo's own governance.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from mneme.adr_compiler import adrs_to_decisions, resolve_precedence
from mneme.adr_parser import parse_adr_directory
from mneme.benchmark import BenchmarkRunner, ScenarioResult, ScenarioVerdict
from mneme.conflict_detector import ConflictDetector
from mneme.decision_index import (
    CanonicalDecisionRecord,
    CanonicalRuleRecord,
    CanonicalSourceEvidence,
    adrs_to_canonical,
    decisions_to_canonical,
)
from mneme.decision_projection import (
    project_canonical_decision,
    project_canonical_index,
)
from mneme.decision_retriever import DecisionRetriever
from mneme.enforcer import check_prompt, generate_protection_report
from mneme.memory_store import MemoryStore
from mneme.schemas import Decision, Rule

REPO_ROOT = Path(__file__).resolve().parent.parent

# Assembled at runtime; see module docstring.
_ADR005_INPUT = ("pip " "install mneme\n")

CORPORA = ("docs/adr", "examples/mneme-own-adrs")

MEMORIES = (
    REPO_ROOT / "examples" / "project_memory.json",
    REPO_ROOT / ".mneme" / "project_memory.json",
)

QUERIES = (
    "storage backend json persistence",
    "retrieval determinism scoring",
    "encoding file writes automation",
    "workflow governance review",
    "edit to mneme/storage.py",
    "edit to docs/adr/ADR-005-brand-vs-package-namespace-enforcement.md",
    "",
)


def _project_memory_decisions(memory_path: Path) -> list[Decision]:
    store = MemoryStore(memory_path)
    store.load()
    index = decisions_to_canonical(store.decisions())
    return project_canonical_index(index, memory_path=str(store.path.resolve()))


# ── G1 projection parity ────────────────────────────────────────────────────


def test_g1_projection_parity_adr_corpora():
    for corpus in CORPORA:
        adrs = parse_adr_directory(REPO_ROOT / corpus)
        active = resolve_precedence(adrs)
        current = adrs_to_decisions(active)
        projected = project_canonical_index(adrs_to_canonical(active))
        assert projected == current, corpus


def test_g1_projection_parity_runtime_decisions():
    for memory_path in MEMORIES:
        store = MemoryStore(memory_path)
        store.load()
        index = decisions_to_canonical(store.decisions())
        projected = project_canonical_index(
            index, memory_path=str(store.path.resolve())
        )
        assert len(projected) == len(store.decisions()), memory_path
        for current, projected_decision in zip(store.decisions(), projected):
            assert current.id == projected_decision.id
            assert current.decision == projected_decision.decision
            assert current.rationale == projected_decision.rationale
            assert current.scope == projected_decision.scope
            assert current.constraints == projected_decision.constraints
            assert current.anti_patterns == projected_decision.anti_patterns
            assert current.rules == projected_decision.rules
            assert current.test_evidence == projected_decision.test_evidence
            assert current.status == projected_decision.status
            assert current.created_at == projected_decision.created_at
            assert current.updated_at == projected_decision.updated_at
            assert current.source_path == projected_decision.source_path
            if current.rules or current.memory_path:
                # Native decisions carry their policy-memory provenance;
                # legacy-migrated items never had one.
                assert projected_decision.memory_path == str(
                    store.path.resolve()
                )


# ── G2 DecisionRetriever parity ─────────────────────────────────────────────


def test_g2_decision_retriever_parity():
    for memory_path in MEMORIES:
        store = MemoryStore(memory_path)
        store.load()
        current_retriever = DecisionRetriever(store.decisions())
        projected_retriever = DecisionRetriever(_project_memory_decisions(memory_path))
        for query in QUERIES:
            current = current_retriever.retrieve(query)
            projected = projected_retriever.retrieve(query)
            assert [
                (s.decision.id, s.score, s.matches) for s in current
            ] == [(s.decision.id, s.score, s.matches) for s in projected], (
                memory_path,
                query,
            )
            assert [s.decision.id for s in current[:3]] == [
                s.decision.id for s in projected[:3]
            ], (memory_path, query)


def test_g2_retrieval_parity_with_path_token_queries():
    for memory_path in MEMORIES:
        current_retriever = DecisionRetriever(
            MemoryStore(memory_path).load().decisions
        )
        projected_retriever = DecisionRetriever(_project_memory_decisions(memory_path))
        for query in (
            "edit to tests/test_cli_audit.py",
            "edit to examples/project_memory.json",
            "edit to scripts/run_test_battery.py",
            "edit to README.md",
        ):
            current = current_retriever.retrieve(query)
            projected = projected_retriever.retrieve(query)
            assert [
                (s.decision.id, s.score, s.matches) for s in current
            ] == [(s.decision.id, s.score, s.matches) for s in projected], query


# ── G3 enforcement parity (frozen benchmarks, unchanged fixtures) ───────────


@dataclass
class _DecisionSource:
    """Minimal store-shaped wrapper: BenchmarkRunner only calls decisions()."""

    _decisions: list = field(default_factory=list)

    def decisions(self) -> list:
        return list(self._decisions)


def _suite_results(benchmarks_dir: Path, memory_path: Path) -> tuple:
    store = MemoryStore(memory_path)
    store.load()
    baseline = BenchmarkRunner(store).run_suite(benchmarks_dir)
    projected = BenchmarkRunner(
        _DecisionSource(_decisions=_project_memory_decisions(memory_path))
    ).run_suite(benchmarks_dir)
    return baseline, projected


def _assert_results_equal(baseline, projected, label: str) -> None:
    assert len(baseline) == len(projected), label
    for left, right in zip(baseline, projected):
        assert left.name == right.name, label
        assert left.verdict == right.verdict, (label, left.name, left.explanation)
        assert left.baseline_violation_count == right.baseline_violation_count, label
        assert left.enhanced_violation_count == right.enhanced_violation_count, label
        assert left.baseline_triggers == right.baseline_triggers, label
        assert left.enhanced_triggers == right.enhanced_triggers, label
        assert left.protected_decision_ids_hit == right.protected_decision_ids_hit, label
        assert left.layer1_retrieved_ids == right.layer1_retrieved_ids, label
        assert left.layer1_recall == right.layer1_recall, label
        assert left.layer1_precision == right.layer1_precision, label
        assert (
            left.layer1_irrelevant_injection == right.layer1_irrelevant_injection
        ), label
        assert left.exposed_decision_ids_hit == right.exposed_decision_ids_hit, label
        assert left.verdict != ScenarioVerdict.MALFORMED, label


def test_g3_frozen_benchmark_parity():
    baseline, projected = _suite_results(
        REPO_ROOT / "examples" / "benchmarks",
        REPO_ROOT / "examples" / "project_memory.json",
    )
    _assert_results_equal(baseline, projected, "benchmarks")
    assert all(r.verdict == ScenarioVerdict.PASS for r in projected)


def test_g3_frozen_enforcement_quality_benchmark_parity():
    baseline, projected = _suite_results(
        REPO_ROOT / "examples" / "benchmarks-enforcement-quality",
        REPO_ROOT / "examples" / "benchmarks-enforcement-quality" / "project_memory.json",
    )
    _assert_results_equal(baseline, projected, "benchmarks-enforcement-quality")


def test_g3_strict_verdict_parity_on_violating_and_compliant_inputs():
    for memory_path in MEMORIES:
        current_scored = DecisionRetriever(
            MemoryStore(memory_path).load().decisions
        ).retrieve("storage backend setup")
        projected_scored = DecisionRetriever(
            _project_memory_decisions(memory_path)
        ).retrieve("storage backend setup")
        for text in (
            _ADR005_INPUT,
            "import psycopg2\n",
            "Set-Content -Path out.txt -Value data\n",
            "sqlite storage chosen for simplicity\n",
        ):
            current = check_prompt(text, current_scored)
            projected = check_prompt(text, projected_scored)
            assert current.verdict == projected.verdict, (memory_path, text)
            assert [
                (v.decision_id, v.rule, v.trigger, v.kind, v.severity.value)
                for v in current.violations
            ] == [
                (v.decision_id, v.rule, v.trigger, v.kind, v.severity.value)
                for v in projected.violations
            ], (memory_path, text)
            assert current.applicability == projected.applicability, (
                memory_path,
                text,
            )


# ── G4 ConflictDetector parity ──────────────────────────────────────────────


def _conflict_fixtures(tmp_path: Path) -> list[Decision]:
    project = tmp_path / "project"
    (project / ".mneme").mkdir(parents=True)
    memory = project / ".mneme" / "project_memory.json"
    memory.write_text(
        '{"meta": {"name": "t", "description": "t"}, "decisions": []}\n',
        encoding="utf-8",
    )
    return [
        Decision(
            id="typed-global",
            decision="Forbid the legacy install command",
            rationale="Legacy client drift",
            scope=["enforcement"],
            rules=[Rule(type="FORBID_LITERAL", value="install legacy-package")],
            memory_path=str(memory.resolve()),
        ),
        Decision(
            id="typed-scoped",
            decision="Quarantine generated modules",
            rationale="Generated code is exempt",
            scope=["enforcement"],
            rules=[
                Rule(
                    type="FORBID_LITERAL",
                    value="install legacy-package",
                    include_paths=("src/api/**",),
                    exclude_paths=("src/api/generated/**",),
                )
            ],
            memory_path=str(memory.resolve()),
        ),
        Decision(
            id="legacy-prose",
            decision="No external database",
            rationale="Single-file deployment",
            scope=["storage"],
            constraints=["no mongodb"],
            anti_patterns=["introduce ORM layer"],
            memory_path=str(memory.resolve()),
        ),
    ]


def test_g4_conflict_detector_parity(tmp_path):
    current_decisions = _conflict_fixtures(tmp_path)
    projected_decisions = project_canonical_index(
        decisions_to_canonical(current_decisions),
        memory_path=str(current_decisions[0].memory_path),
    )
    detector = ConflictDetector()
    cases = (
        ("run install legacy-package to connect", None),
        ("generated module contains install legacy-package", "src/api/generated/out.py"),
        ("app code contains install legacy-package", "src/api/routes.py"),
        ("we should use mongodb for storage", "src/db.py"),
        ("introduce ORM layer for persistence", None),
        ("clean compliant response", "src/api/routes.py"),
    )
    for response, target in cases:
        current = detector.evaluate(response, current_decisions, target_path=target)
        projected = detector.evaluate(
            response, projected_decisions, target_path=target
        )
        assert current.conflicts == projected.conflicts, (response, target)
        assert current.applicability == projected.applicability, (response, target)


def test_g4_scoped_unknown_applicability_is_identical(tmp_path):
    current_decisions = _conflict_fixtures(tmp_path)
    projected_decisions = project_canonical_index(
        decisions_to_canonical(current_decisions),
        memory_path=str(current_decisions[0].memory_path),
    )
    current = ConflictDetector().evaluate(
        "contains install legacy-package", current_decisions, target_path=None
    )
    projected = ConflictDetector().evaluate(
        "contains install legacy-package", projected_decisions, target_path=None
    )
    assert current.evaluation_complete == projected.evaluation_complete is False
    assert current.applicability == projected.applicability
    assert current.conflicts == projected.conflicts


def test_g4_detect_raises_identically_on_unknown_applicability(tmp_path):
    current_decisions = _conflict_fixtures(tmp_path)
    projected_decisions = project_canonical_index(
        decisions_to_canonical(current_decisions),
        memory_path=str(current_decisions[0].memory_path),
    )
    detector = ConflictDetector()
    with pytest.raises(RuntimeError) as current_exc:
        detector.detect("install legacy-package", current_decisions, target_path=None)
    with pytest.raises(RuntimeError) as projected_exc:
        detector.detect("install legacy-package", projected_decisions, target_path=None)
    assert type(current_exc.value) is type(projected_exc.value)
    assert str(current_exc.value) == str(projected_exc.value)


# ── G5 Architecture Audit parity ────────────────────────────────────────────


def _assert_audit_equal(baseline, projected, label: str) -> None:
    assert baseline.schema == projected.schema
    assert baseline.total_decisions == projected.total_decisions
    assert baseline.protection_relevant == projected.protection_relevant
    assert baseline.protected == projected.protected
    assert baseline.mneme_ready == projected.mneme_ready
    assert baseline.requires_modelling == projected.requires_modelling
    assert baseline.guidance == projected.guidance
    assert baseline.current_protection_pct == projected.current_protection_pct
    assert (
        baseline.identified_mneme_potential_pct
        == projected.identified_mneme_potential_pct
    )
    assert baseline.protection_gap_pct == projected.protection_gap_pct
    assert len(baseline.decisions) == len(projected.decisions)
    for left, right in zip(baseline.decisions, projected.decisions):
        assert left == right, (label, left.id)


def test_g5_architecture_audit_parity_repo_memory():
    memory_path = REPO_ROOT / ".mneme" / "project_memory.json"
    store = MemoryStore(memory_path)
    store.load()
    baseline = generate_protection_report(store.decisions(), repo_root=REPO_ROOT)
    projected = generate_protection_report(
        _project_memory_decisions(memory_path), repo_root=REPO_ROOT
    )
    assert baseline.memory_path == projected.memory_path
    _assert_audit_equal(baseline, projected, "repo-memory")


def test_g5_architecture_audit_parity_example_memory():
    memory_path = REPO_ROOT / "examples" / "project_memory.json"
    baseline = generate_protection_report(
        MemoryStore(memory_path).load().decisions, repo_root=REPO_ROOT
    )
    projected = generate_protection_report(
        _project_memory_decisions(memory_path), repo_root=REPO_ROOT
    )
    _assert_audit_equal(baseline, projected, "example-memory")


def test_g5_audit_parity_without_repo_root():
    for memory_path in MEMORIES:
        baseline = generate_protection_report(
            MemoryStore(memory_path).load().decisions
        )
        projected = generate_protection_report(_project_memory_decisions(memory_path))
        _assert_audit_equal(baseline, projected, str(memory_path))


# ── G7 no inferred enforcement ──────────────────────────────────────────────


def test_g7_no_inferred_enforcement_from_prose_only_decision():
    canonical = _record(
        decision_id="D0-G7",
        statement="The storage layer must never depend on a network database.",
        rationale="Deployment is single-file sqlite only.",
        scope=("storage",),
        constraints=("no network database",),
    )
    projected = project_canonical_decision(canonical)
    assert projected.rules == [], "no Rule may be invented from prose"

    current_equivalent = Decision(
        id=canonical.decision_id,
        decision=canonical.statement,
        rationale=canonical.rationale,
        scope=list(canonical.context_scope),
        constraints=list(canonical.constraints),
    )
    for text in (
        "use the network database client in storage",
        "storage: postgres is fine here",
        "never depend on a network database",
    ):
        projected_result = check_prompt(
            text, DecisionRetriever([projected]).retrieve(text)
        )
        current_result = check_prompt(
            text, DecisionRetriever([current_equivalent]).retrieve(text)
        )
        assert projected_result.verdict == current_result.verdict, text
        assert not any(
            v.severity.value == "FAIL" for v in projected_result.violations
        ), text
        assert [
            (v.decision_id, v.rule, v.trigger, v.kind)
            for v in projected_result.violations
        ] == [
            (v.decision_id, v.rule, v.trigger, v.kind)
            for v in current_result.violations
        ], text


def test_g7_prose_only_decision_has_no_applicability_trace():
    canonical = _record(
        decision_id="D0-G7-2",
        statement="Document storage boundaries in the ADR directory.",
        rationale="Traceability",
        scope=("documentation",),
        constraints=(),
    )
    projected = project_canonical_decision(canonical)
    result = check_prompt(
        "update the docs", DecisionRetriever([projected]).retrieve("update the docs")
    )
    assert result.applicability == []
    assert result.verdict.value == "PASS"


# ── G9 non-code safety ──────────────────────────────────────────────────────


def test_g9_non_code_target_projects_without_inventing_enforcement():
    canonical = _record(
        decision_id="D0-G9",
        statement="Release sign-off is recorded in the operations log.",
        rationale="Auditability of releases",
        scope=("process",),
        targets=("process:release-checklist",),
    )
    projected = project_canonical_decision(canonical)
    assert projected.rules == []
    assert projected.id == "D0-G9"
    assert projected.decision == canonical.statement
    result = check_prompt(
        "plan the release", DecisionRetriever([projected]).retrieve("plan the release")
    )
    assert result.verdict.value == "PASS"
    assert result.violations == []
    assert result.applicability == []


def test_g9_non_architecture_class_fails_closed():
    canonical = dataclasses.replace(
        _record(decision_id="D0-G9-2"), decision_class="security"
    )
    with pytest.raises(ValueError) as exc:
        project_canonical_decision(canonical)
    assert "architecture" in str(exc.value)


def test_projection_fails_closed_on_lineage_lifecycle():
    canonical = dataclasses.replace(
        _record(decision_id="D0-LINEAGE"), lifecycle_status="deprecated"
    )
    with pytest.raises(ValueError):
        project_canonical_decision(canonical)


def test_projection_fails_closed_on_rule_ownership_mismatch():
    canonical = _record(decision_id="D0-OWNER")
    mismatched = CanonicalRuleRecord(
        rule_id="D0-OTHER:FORBID_LITERAL:0",
        decision_id="D0-OTHER",
        decision_version="1",
        rule_type="FORBID_LITERAL",
        rule_payload={"value": "forbidden-literal-demo"},
    )
    with pytest.raises(ValueError) as exc:
        project_canonical_decision(canonical, rules=(mismatched,))
    assert "D0-OTHER" in str(exc.value)


def test_projection_fails_closed_on_missing_declared_rule():
    canonical = dataclasses.replace(
        _record(decision_id="D0-MISSING"),
        derived_rule_ids=("D0-MISSING:FORBID_LITERAL:0",),
    )
    with pytest.raises(ValueError) as exc:
        project_canonical_decision(canonical, rules=())
    assert "derived_rule_ids" in str(exc.value)


def test_projection_fails_closed_on_extra_undeclared_rule():
    canonical = _record(decision_id="D0-EXTRA")
    undeclared = CanonicalRuleRecord(
        rule_id="D0-EXTRA:FORBID_LITERAL:0",
        decision_id="D0-EXTRA",
        decision_version="1",
        rule_type="FORBID_LITERAL",
        rule_payload={"value": "forbidden-literal-demo"},
    )
    with pytest.raises(ValueError) as exc:
        project_canonical_decision(canonical, rules=(undeclared,))
    assert "derived_rule_ids" in str(exc.value)


def test_projection_fails_closed_on_reordered_declared_rule_ids():
    canonical = dataclasses.replace(
        _record(decision_id="D0-ORDER"),
        derived_rule_ids=(
            "D0-ORDER:FORBID_LITERAL:0",
            "D0-ORDER:FORBID_LITERAL:1",
        ),
    )
    rules = tuple(
        CanonicalRuleRecord(
            rule_id=rule_id,
            decision_id="D0-ORDER",
            decision_version="1",
            rule_type="FORBID_LITERAL",
            rule_payload={"value": f"forbidden-literal-{n}"},
        )
        for rule_id, n in (
            ("D0-ORDER:FORBID_LITERAL:1", 1),
            ("D0-ORDER:FORBID_LITERAL:0", 0),
        )
    )
    with pytest.raises(ValueError) as exc:
        project_canonical_decision(canonical, rules=rules)
    assert "derived_rule_ids" in str(exc.value)


def test_projection_fails_closed_on_rule_lifecycle_mismatch():
    canonical = dataclasses.replace(
        _record(decision_id="D0-LIFECYCLE"),
        derived_rule_ids=("D0-LIFECYCLE:FORBID_LITERAL:0",),
    )
    incompatible = CanonicalRuleRecord(
        rule_id="D0-LIFECYCLE:FORBID_LITERAL:0",
        decision_id="D0-LIFECYCLE",
        decision_version="1",
        rule_type="FORBID_LITERAL",
        rule_payload={"value": "forbidden-literal-demo"},
        lifecycle_status="superseded",
    )
    with pytest.raises(ValueError) as exc:
        project_canonical_decision(canonical, rules=(incompatible,))
    assert "lifecycle_status" in str(exc.value)


def test_projection_fails_closed_on_unknown_source_type():
    canonical = dataclasses.replace(
        _record(decision_id="D0-SRC"),
        source_evidence=(CanonicalSourceEvidence(
            source_type="confluence", source_locator="https://example.test/x"
        ),),
    )
    with pytest.raises(ValueError) as exc:
        project_canonical_decision(canonical)
    assert "source_type" in str(exc.value)


def test_g8_runtime_provenance_round_trips_without_claiming_adr(tmp_path):
    """EventCatalog-style runtime provenance: locator preserved, type honest.

    The source path also feeds the ADR-019/ADR-020 policy-source exemptions
    (policy_paths), so the projected decision must keep the identical
    exemption behavior without the kernel claiming ADR provenance.
    """
    project = tmp_path / "catalog-project"
    (project / ".mneme").mkdir(parents=True)
    memory = project / ".mneme" / "project_memory.json"
    memory.write_text(
        '{"meta": {"name": "t", "description": "t"}, "decisions": []}\n',
        encoding="utf-8",
    )
    event_source = str(
        project / "catalog" / "domains" / "payments" / "decisions" / "adr-01.mdx"
    )
    current = Decision(
        id="ec-payment-adr-01",
        decision="Payments use the posted event schema",
        rationale="EventCatalog ADR",
        scope=["payments"],
        rules=[
            Rule(
                type="FORBID_LITERAL",
                value="legacy-event-schema",
                include_paths=("src/payments/**",),
            )
        ],
        source_path=event_source,
        memory_path=str(memory.resolve()),
    )
    [projected] = project_canonical_index(
        decisions_to_canonical([current]), memory_path=str(memory.resolve())
    )
    assert projected.source_path == current.source_path

    index = decisions_to_canonical([current])
    assert index.records[0].source_evidence[0].source_type == "runtime"

    text = "uses legacy-event-schema in the handler"
    for target in (event_source, "src/payments/handler.py"):
        scored_current = DecisionRetriever([current]).retrieve(target)
        scored_projected = DecisionRetriever([projected]).retrieve(target)
        current_result = check_prompt(
            text, scored_current, input_path=target
        )
        projected_result = check_prompt(
            text, scored_projected, input_path=target
        )
        assert current_result.verdict == projected_result.verdict
        assert current_result.applicability == projected_result.applicability
        assert [
            (v.decision_id, v.rule, v.trigger, v.kind)
            for v in current_result.violations
        ] == [
            (v.decision_id, v.rule, v.trigger, v.kind)
            for v in projected_result.violations
        ]


def _record(
    decision_id: str,
    statement: str = "",
    rationale: str = "",
    scope: tuple[str, ...] = (),
    constraints: tuple[str, ...] = (),
    targets: tuple[str, ...] = (),
):
    return CanonicalDecisionRecord(
        decision_id=decision_id,
        version="1",
        decision_class="architecture",
        statement=statement,
        rationale=rationale,
        lifecycle_status="active",
        decided_at="2026-09-01",
        context_scope=scope,
        targets=targets,
        constraints=constraints,
    )

"""D0 kernel tests — canonical Decision Index models and adapters (ADR-023).

Covers the canonical data contract, the compiled-ADR and runtime-Decision
adapters, lifecycle parity (G6), source independence (G8), and the D0
invariants that no rule is inferred from prose and that decision scope never
becomes typed-rule applicability.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from mneme.adr_compiler import adrs_to_decisions, resolve_precedence
from mneme.adr_import import compile_for_import
from mneme.adr_parser import parse_adr_directory, parse_adr_file
from mneme.decision_index import (
    CANONICAL_DECISION_CLASS_ARCHITECTURE,
    CANONICAL_VERSION,
    CanonicalDecisionRecord,
    CanonicalRuleRecord,
    CanonicalTestEvidence,
    adrs_to_canonical,
    build_canonical_index,
    canonical_from,
    decisions_to_canonical,
)
from mneme.decision_projection import (
    project_canonical_decision,
    project_canonical_index,
    project_canonical_rule,
)
from mneme.enforcer import check_prompt
from mneme.decision_retriever import DecisionRetriever
from mneme.schemas import Decision, Rule

REPO_ROOT = Path(__file__).resolve().parent.parent


def _adr(
    id: str = "ADR-9001",
    status: str = "accepted",
    supersedes: list[str] | None = None,
    body: str = "",
    scope: str = "enforcement.kernel",
) -> object:
    from mneme.adr_schema import ADR

    return ADR(
        id=id,
        title=f"{id} title",
        status=status,  # type: ignore[arg-type]
        priority="normal",
        date="2026-09-01",
        scope=scope,
        supersedes=supersedes or [],
        body=body,
        source_path=str(REPO_ROOT / "docs" / "adr" / f"{id}-fixture.md"),
    )


def _constraint_body() -> str:
    return (
        "## Decision body.\n\n"
        "## Constraints\n"
        "- FORBID_DEPENDENCY: mongodb\n"
        "- FORBID_PATH: src/legacy/**\n"
        "- FORBID_LITERAL:\n"
        "    value: install legacy-package\n"
        "    include_paths:\n"
        "      - src/api/**\n"
        "    exclude_paths:\n"
        "      - src/api/generated/**\n"
        "## Next section\n"
    )


# ── Canonical model shape ────────────────────────────────────────────────────


def test_canonical_records_are_frozen():
    record = CanonicalDecisionRecord(decision_id="ADR-9001")
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.decision_id = "ADR-9002"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.statement = "mutated"  # type: ignore[misc]


def test_canonical_version_is_the_narrow_d0_constant():
    record = CanonicalDecisionRecord(decision_id="ADR-9001")
    assert record.version == CANONICAL_VERSION == "1"
    assert record.decision_class == CANONICAL_DECISION_CLASS_ARCHITECTURE


# ── ADR adapter ──────────────────────────────────────────────────────────────


def test_adr_adapter_preserves_identity_statement_rationale_scope():
    adr = _adr(body=_constraint_body())
    index = adrs_to_canonical([adr])
    [record] = index.records
    assert record.decision_id == "ADR-9001"
    assert record.version == "1"
    assert record.decision_class == "architecture"
    assert record.statement == "ADR-9001 title"
    assert record.rationale == adr.body
    assert record.context_scope == ("enforcement.kernel",)


def test_adr_adapter_splits_constraints_from_typed_rules():
    adr = _adr(body=_constraint_body())
    index = adrs_to_canonical([adr])
    [record] = index.records
    assert record.constraints == ("no mongodb", "FORBID_PATH src/legacy/**")
    assert record.anti_patterns == ()
    [rule] = index.rules
    assert rule.rule_type == "FORBID_LITERAL"
    assert rule.rule_payload == {"value": "install legacy-package"}
    assert rule.applicability == {
        "include_paths": ["src/api/**"],
        "exclude_paths": ["src/api/generated/**"],
    }
    assert rule.decision_id == "ADR-9001"
    assert rule.decision_version == "1"
    assert rule.rule_id == "ADR-9001:FORBID_LITERAL:0"
    assert record.derived_rule_ids == ("ADR-9001:FORBID_LITERAL:0",)


def test_adr_adapter_preserves_provenance_timestamps_and_relationships():
    adr = _adr(supersedes=["ADR-9000"])
    [record] = adrs_to_canonical([adr]).records
    assert record.decided_at == "2026-09-01"
    assert record.relationships == (("supersedes", "ADR-9000"),)
    assert record.source_evidence[0].source_type == "adr"
    assert record.source_evidence[0].source_locator == adr.source_path


def test_adr_adapter_projection_matches_existing_compiler_bridge():
    """G1 kernel side: adapter + projector equals the existing bridge."""
    for corpus in ("docs/adr", "examples/mneme-own-adrs"):
        adrs = parse_adr_directory(REPO_ROOT / corpus)
        active = resolve_precedence(adrs)
        projected = project_canonical_index(adrs_to_canonical(active))
        assert projected == adrs_to_decisions(active), corpus


def test_adr_adapter_infers_no_rule_from_prescriptive_prose():
    adr = _adr(
        body=(
            "The storage layer must never depend on a network database. "
            "Deployment is single-file sqlite only."
        )
    )
    index = adrs_to_canonical([adr])
    assert index.rules == ()
    [record] = index.records
    assert record.constraints == ()
    assert record.derived_rule_ids == ()


def test_decision_scope_never_becomes_rule_applicability():
    adr = _adr(
        scope="src.api",
        body="## Constraints\n- FORBID_LITERAL: install legacy-package\n",
    )
    index = adrs_to_canonical([adr])
    [record] = index.records
    [rule] = index.rules
    assert record.context_scope == ("src.api",)
    assert rule.applicability == {}, (
        "ADR-020: decision scope must not silently become rule applicability"
    )


def test_canonical_from_dispatches_by_source_type():
    adr_index = canonical_from(adrs=[_adr()])
    assert len(adr_index.records) == 1
    decision = Decision(id="ADR-9001", decision="ADR-9001 title")
    decision_index = canonical_from(decisions=[decision])
    assert len(decision_index.records) == 1
    with pytest.raises(ValueError):
        canonical_from()


# ── Runtime Decision adapter ────────────────────────────────────────────────


def _runtime_decision() -> Decision:
    return Decision(
        id="legacy_001",
        decision="Storage stays single-file",
        rationale="Deployment simplicity",
        scope=["storage"],
        constraints=["no postgres", "no external db"],
        anti_patterns=["introduce ORM", "add migration layer"],
        rules=[
            Rule(
                type="FORBID_LITERAL",
                value="install legacy-package",
                include_paths=("src/api/**",),
                exclude_paths=("src/api/generated/**",),
            )
        ],
        test_evidence=[{"selector": "tests/test_x.py::test_y", "sha": "abc123"}],
        source_path=str(REPO_ROOT / "docs" / "adr" / "ADR-9001-fixture.md"),
        memory_path=str(REPO_ROOT / ".mneme" / "project_memory.json"),
        created_at="2026-05-12",
        updated_at="2026-05-12",
        status="active",
    )


def test_runtime_adapter_preserves_anti_patterns_separately_from_constraints():
    decision = _runtime_decision()
    [record] = decisions_to_canonical([decision]).records
    assert record.constraints == ("no postgres", "no external db")
    assert record.anti_patterns == ("introduce ORM", "add migration layer"), (
        "anti-patterns must not be collapsed into constraints (D0 contract)"
    )
    assert record.statement == decision.decision
    assert record.rationale == decision.rationale
    assert record.context_scope == ("storage",)


def test_runtime_adapter_preserves_rules_test_evidence_and_lifecycle():
    decision = _runtime_decision()
    index = decisions_to_canonical([decision])
    [record] = index.records
    [rule] = index.rules
    assert rule.rule_type == "FORBID_LITERAL"
    assert rule.rule_payload == {"value": "install legacy-package"}
    assert rule.applicability == {
        "include_paths": ["src/api/**"],
        "exclude_paths": ["src/api/generated/**"],
    }
    assert record.test_evidence == (
        CanonicalTestEvidence(selector="tests/test_x.py::test_y", sha="abc123"),
    )
    assert record.test_evidence[0].sha == "abc123"
    assert record.lifecycle_status == "active"
    assert record.decided_at == "2026-05-12"
    assert record.source_evidence[0].source_locator == decision.source_path


def test_runtime_adapter_records_runtime_source_type_not_adr():
    """Non-ADR runtime provenance must not be labeled ``adr``.

    The runtime ``Decision`` shape does not carry enough information to
    verify ADR provenance: non-ADR producers (e.g. the EventCatalog
    importer) also construct runtime Decisions with a ``source_path``. The
    generic adapter preserves the locator for parity and records the honest
    ``runtime`` source type.
    """
    decision = _runtime_decision()
    decision.source_path = str(
        REPO_ROOT / "examples" / "eventcatalog-sample" / "adr-01.mdx"
    )
    [record] = decisions_to_canonical([decision]).records
    assert record.source_evidence[0].source_type == "runtime"
    assert record.source_evidence[0].source_locator == decision.source_path
    assert record.source_evidence[0].source_type != "adr"

    [projected] = project_canonical_index(
        decisions_to_canonical([decision]),
        memory_path=str(REPO_ROOT / ".mneme" / "project_memory.json"),
    )
    assert projected.source_path == decision.source_path


def test_runtime_adapter_does_not_carry_memory_path():
    decision = _runtime_decision()
    [record] = decisions_to_canonical([decision]).records
    assert not any(
        field.name == "memory_path"
        for field in dataclasses.fields(CanonicalDecisionRecord)
    )


def test_runtime_adapter_superseded_status_is_carried_not_projected():
    decision = dataclasses.replace(_runtime_decision(), status="superseded")
    index = decisions_to_canonical([decision])
    [record] = index.records
    assert record.lifecycle_status == "superseded"
    assert project_canonical_index(index) == []


def test_runtime_round_trip_is_lossless_mod_memory_path():
    decision = _runtime_decision()
    index = decisions_to_canonical([decision])
    [projected] = project_canonical_index(
        index, memory_path=str(REPO_ROOT / ".mneme" / "project_memory.json")
    )
    assert projected == decision


# ── G6 lifecycle parity ─────────────────────────────────────────────────────


def _write_adr_file(
    path: Path, adr_id: str, status: str, supersedes: str = "", scope: str = "d0.fixtures"
) -> None:
    supersedes_line = f"\nsupersedes: [{supersedes}]" if supersedes else ""
    path.write_text(
        "---\n"
        f"id: {adr_id}\n"
        f'title: "{adr_id} decision"\n'
        f"status: {status}\n"
        "priority: normal\n"
        "date: 2026-09-01\n"
        f"scope: {scope}{supersedes_line}\n"
        "---\n"
        f"# {adr_id}\n\nBody for {adr_id}.\n",
        encoding="utf-8",
    )


def _lifecycle_corpus(tmp_path: Path) -> Path:
    adr_dir = tmp_path / "adr"
    adr_dir.mkdir()
    _write_adr_file(
        adr_dir / "ADR-9101.md", "ADR-9101", "accepted", scope="d0.fixtures.one"
    )
    _write_adr_file(
        adr_dir / "ADR-9102.md",
        "ADR-9102",
        "accepted",
        "ADR-9103",
        scope="d0.fixtures.two",
    )
    _write_adr_file(
        adr_dir / "ADR-9103.md", "ADR-9103", "superseded", scope="d0.fixtures.two"
    )
    _write_adr_file(
        adr_dir / "ADR-9104.md", "ADR-9104", "deprecated", scope="d0.fixtures.four"
    )
    _write_adr_file(
        adr_dir / "ADR-9105.md", "ADR-9105", "proposed", scope="d0.fixtures.five"
    )
    return adr_dir


def test_g6_lifecycle_parity_active_superseded_deprecated(tmp_path):
    adr_dir = _lifecycle_corpus(tmp_path)

    memory = tmp_path / "project_memory.json"
    memory.write_text(
        '{"meta": {"name": "t", "description": "t"}, "decisions": []}\n',
        encoding="utf-8",
    )
    report = compile_for_import(adr_dir)
    current_ids = [d.id for d in report.decisions]

    parsed = parse_adr_directory(adr_dir)
    active = resolve_precedence(parsed)
    index = build_canonical_index(parsed, active)
    projected = project_canonical_index(index)

    assert current_ids == ["ADR-9101", "ADR-9102"]
    assert [d.id for d in projected] == ["ADR-9101", "ADR-9102"]
    assert projected == report.decisions

    statuses = {r.decision_id: r.lifecycle_status for r in index.records}
    assert statuses == {
        "ADR-9101": "active",
        "ADR-9102": "active",
        "ADR-9103": "superseded",
        "ADR-9104": "deprecated",
        "ADR-9105": "inactive",
    }


def test_g6_lineage_records_retained_without_runtime_governance(tmp_path):
    adr_dir = _lifecycle_corpus(tmp_path)
    parsed = parse_adr_directory(adr_dir)
    index = build_canonical_index(parsed, resolve_precedence(parsed))
    lineage = [r for r in index.records if r.lifecycle_status != "active"]
    assert {r.decision_id for r in lineage} == {
        "ADR-9103", "ADR-9104", "ADR-9105",
    }
    assert all(r.decision_class == "architecture" for r in lineage)


def test_g6_same_scope_precedence_loser_retained_as_non_projectable_lineage(
    tmp_path,
):
    """Two accepted same-scope ADRs: precedence picks one runtime winner.

    Required result: both decisions are canonically represented; only the
    precedence winner projects to Layer 1; the loser is retained as
    non-authoritative lineage with the non-projectable ``inactive`` state.
    """
    adr_dir = tmp_path / "adr"
    adr_dir.mkdir()
    _write_adr_file(
        adr_dir / "ADR-9201.md",
        "ADR-9201",
        "accepted",
        scope="d0.precedence",
    )
    _write_adr_file(
        adr_dir / "ADR-9202.md",
        "ADR-9202",
        "accepted",
        scope="d0.precedence",
    )
    _bump_date(adr_dir / "ADR-9201.md", "2026-09-02")

    memory = tmp_path / "project_memory.json"
    memory.write_text(
        '{"meta": {"name": "t", "description": "t"}, "decisions": []}\n',
        encoding="utf-8",
    )
    report = compile_for_import(adr_dir)
    assert [d.id for d in report.decisions] == ["ADR-9201"], (
        "the compiler must still choose exactly one runtime active winner"
    )

    parsed = parse_adr_directory(adr_dir)
    index = build_canonical_index(parsed, resolve_precedence(parsed))
    statuses = {r.decision_id: r.lifecycle_status for r in index.records}
    assert statuses == {"ADR-9201": "active", "ADR-9202": "inactive"}

    projected = project_canonical_index(index)
    assert [d.id for d in projected] == ["ADR-9201"]
    assert projected == report.decisions

    loser = index.rules_for_decision("ADR-9202")
    assert all(rule.lifecycle_status == "inactive" for rule in loser)


def _bump_date(path: Path, date: str) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("date: 2026-09-01", f"date: {date}", 1),
        encoding="utf-8",
    )


def test_g6_retrieval_excludes_non_active_projections(tmp_path):
    adr_dir = _lifecycle_corpus(tmp_path)
    parsed = parse_adr_directory(adr_dir)
    projected = project_canonical_index(build_canonical_index(parsed, resolve_precedence(parsed)))
    retriever = DecisionRetriever(projected)
    scored = retriever.retrieve("d0 fixtures decision")
    assert [s.decision.id for s in scored] == ["ADR-9101", "ADR-9102"]


# ── G8 source independence ──────────────────────────────────────────────────


_ADR_9200_FRONTMATTER = (
    "---\n"
    "id: ADR-9200\n"
    'title: "Quarantine legacy client"\n'
    "status: accepted\n"
    "priority: normal\n"
    "date: 2026-09-01\n"
    "scope: d0.source_independence\n"
    "---\n"
    "Decision body.\n\n"
    "## Constraints\n"
    "- FORBID_DEPENDENCY: legacy-client\n"
)


def test_g8_same_identity_and_equivalent_projection_across_source_locations(
    tmp_path,
):
    dir_a = tmp_path / "corpus-a"
    dir_b = tmp_path / "moved" / "corpus-b"
    dir_b.mkdir(parents=True)
    dir_a.mkdir()
    (dir_a / "ADR-9200.md").write_text(_ADR_9200_FRONTMATTER, encoding="utf-8")
    (dir_b / "ADR-9200-moved.md").write_text(_ADR_9200_FRONTMATTER, encoding="utf-8")

    adr_a = parse_adr_file(dir_a / "ADR-9200.md")
    adr_b = parse_adr_file(dir_b / "ADR-9200-moved.md")

    record_a = adrs_to_canonical([adr_a]).records[0]
    record_b = adrs_to_canonical([adr_b]).records[0]

    assert record_a.decision_id == record_b.decision_id == "ADR-9200"
    assert record_a.version == record_b.version
    assert record_a.statement == record_b.statement
    assert record_a.rationale == record_b.rationale
    assert record_a.constraints == record_b.constraints
    assert record_a.derived_rule_ids == record_b.derived_rule_ids
    assert record_a.source_evidence != record_b.source_evidence, (
        "the provenance locator may differ; logical identity may not"
    )

    projected_a = project_canonical_decision(
        record_a, rules=adrs_to_canonical([adr_a]).rules_for_decision("ADR-9200")
    )
    projected_b = project_canonical_decision(
        record_b, rules=adrs_to_canonical([adr_b]).rules_for_decision("ADR-9200")
    )
    assert projected_a.id == projected_b.id
    assert projected_a.decision == projected_b.decision
    assert projected_a.rationale == projected_b.rationale
    assert projected_a.scope == projected_b.scope
    assert projected_a.constraints == projected_b.constraints
    assert projected_a.rules == projected_b.rules
    assert projected_a.source_path != projected_b.source_path

    query = "edit to service.py"
    scored_a = DecisionRetriever([projected_a]).retrieve(query)
    scored_b = DecisionRetriever([projected_b]).retrieve(query)
    assert [(s.decision.id, s.score, s.matches) for s in scored_a] == [
        (s.decision.id, s.score, s.matches) for s in scored_b
    ]

    verdict_a = check_prompt("run install legacy-package now", scored_a)
    verdict_b = check_prompt("run install legacy-package now", scored_b)
    assert verdict_a.verdict == verdict_b.verdict
    assert [
        (v.decision_id, v.rule, v.trigger, v.kind) for v in verdict_a.violations
    ] == [(v.decision_id, v.rule, v.trigger, v.kind) for v in verdict_b.violations]


def test_canonical_rule_record_round_trips_through_projection():
    rule = CanonicalRuleRecord(
        rule_id="ADR-9300:FORBID_LITERAL:0",
        decision_id="ADR-9300",
        decision_version=CANONICAL_VERSION,
        rule_type="FORBID_LITERAL",
        rule_payload={"value": "forbidden-literal-demo"},
    )
    assert project_canonical_rule(rule) == Rule(
        type="FORBID_LITERAL", value="forbidden-literal-demo"
    )

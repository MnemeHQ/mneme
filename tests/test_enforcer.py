"""Tests for mneme/enforcer.py and `mneme check` CLI command."""
import json
from pathlib import Path

import pytest

from mneme.cli import main
from mneme.decision_retriever import DecisionRetriever, ScoredDecision
from mneme.enforcer import EnforcementResult, Severity, Violation, check_prompt
from mneme.memory_store import MemoryStore
from mneme.schemas import Decision, Rule

EXAMPLE_MEMORY = Path(__file__).parent.parent / "examples" / "project_memory.json"


# ── shared fixtures ───────────────────────────────────────────────────────────

def _scored(decision: Decision, score: float = 1.0) -> ScoredDecision:
    return ScoredDecision(decision=decision, score=score)


STORAGE = Decision(
    id="storage_json",
    decision="Use JSON storage only",
    rationale="local-first, avoid infra complexity",
    scope=["storage"],
    constraints=["no postgres", "no ORM"],
    anti_patterns=["introduce ORM", "add vector db"],
)

RETRIEVAL = Decision(
    id="retrieval_det",
    decision="Keep retrieval deterministic",
    rationale="testability",
    scope=["retrieval"],
    constraints=["no embeddings", "no ML"],
    anti_patterns=["add vector db", "use cosine similarity"],
)


def _memory_file(tmp_path: Path) -> Path:
    mem = tmp_path / "project_memory.json"
    mem.write_text(json.dumps({
        "meta": {"name": "t", "description": "t"},
        "items": [], "examples": [],
        "decisions": [
            {
                "id": "storage_json",
                "decision": "Use JSON storage only",
                "rationale": "local-first",
                "scope": ["storage", "backend"],
                "constraints": ["no postgres", "no ORM"],
                "anti_patterns": ["introduce ORM", "add vector db"],
                "created_at": "2026-04-24T00:00:00Z",
                "updated_at": "2026-04-24T00:00:00Z",
            },
            {
                "id": "retrieval_det",
                "decision": "Keep retrieval deterministic",
                "rationale": "testability",
                "scope": ["retrieval"],
                "constraints": ["no embeddings"],
                "anti_patterns": ["use cosine similarity"],
                "created_at": "2026-04-24T00:00:00Z",
                "updated_at": "2026-04-24T00:00:00Z",
            },
        ],
    }))
    return mem


def _input_file(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "prompt.txt"
    p.write_text(content, encoding="utf-8")
    return p


# ── check_prompt unit tests ───────────────────────────────────────────────────

def test_clean_input_returns_pass():
    scored = [_scored(STORAGE)]
    result = check_prompt("Store all data as flat JSON files on disk.", scored)
    assert result.verdict == Severity.PASS
    assert result.violations == []


def test_anti_pattern_match_returns_fail():
    scored = [_scored(STORAGE)]
    result = check_prompt("We should introduce an ORM for database access.", scored)
    assert result.verdict == Severity.FAIL


def test_anti_pattern_violation_has_fail_severity():
    scored = [_scored(STORAGE)]
    result = check_prompt("introduce an ORM layer", scored)
    fail_violations = [v for v in result.violations if v.severity == Severity.FAIL]
    assert len(fail_violations) >= 1


def test_constraint_violation_returns_warn():
    scored = [_scored(STORAGE)]
    result = check_prompt("What if we used postgres for this?", scored)
    assert result.verdict == Severity.WARN


def test_constraint_violation_has_warn_severity():
    scored = [_scored(STORAGE)]
    result = check_prompt("Store user data in postgres.", scored)
    warn_violations = [v for v in result.violations if v.severity == Severity.WARN]
    assert len(warn_violations) >= 1


def test_fail_verdict_when_both_anti_pattern_and_constraint_violated():
    scored = [_scored(STORAGE)]
    result = check_prompt("Use postgres with an ORM layer.", scored)
    assert result.verdict == Severity.FAIL


def test_only_warn_violations_gives_warn_verdict():
    d = Decision(
        id="d1", decision="D1", scope=[], rationale="",
        constraints=["no postgres"], anti_patterns=[],
    )
    scored = [_scored(d)]
    result = check_prompt("Consider postgres here.", scored)
    assert result.verdict == Severity.WARN


def test_violation_records_decision_id():
    scored = [_scored(STORAGE)]
    result = check_prompt("introduce ORM", scored)
    assert any(v.decision_id == "storage_json" for v in result.violations)


def test_violation_records_decision_text():
    scored = [_scored(STORAGE)]
    result = check_prompt("introduce ORM", scored)
    assert any("JSON storage" in v.decision_text for v in result.violations)


def test_violation_records_triggering_rule():
    scored = [_scored(STORAGE)]
    result = check_prompt("introduce ORM", scored)
    fail_v = next(v for v in result.violations if v.severity == Severity.FAIL)
    assert "introduce ORM" in fail_v.rule or "orm" in fail_v.rule.lower()


def test_violation_records_trigger_term():
    scored = [_scored(STORAGE)]
    result = check_prompt("Use postgres for storage.", scored)
    warn_v = next(v for v in result.violations if v.severity == Severity.WARN)
    assert "postgres" in warn_v.trigger


def test_zero_score_decision_still_enforces_its_literal_rules():
    """Zero retrieval score no longer exempts a decision from enforcement.

    Replaces `test_zero_score_decisions_are_skipped`, which pinned the #254
    defect: `_top_nonzero` dropped every zero-scoring decision, so identical
    content was caught or missed on the strength of the filename alone.

    STORAGE's `no postgres` constraint is a one-term rule, so it applies
    corpus-wide and WARNs here. Its `introduce ORM` anti_pattern is multi-term
    and stays retrieval-gated, so it does not fire -- which is why the verdict
    is WARN and not FAIL. See ADR-017.
    """
    scored = [_scored(STORAGE, score=0.0)]
    result = check_prompt("Use postgres and introduce ORM.", scored)
    assert result.verdict == Severity.WARN
    assert any(v.trigger == "postgres" for v in result.violations)
    assert not any(v.severity == Severity.FAIL for v in result.violations)


def test_zero_score_decision_does_not_apply_multi_term_rules():
    """The #150 guardrail: corpus-wide enforcement is literal rules only.

    A multi-term rule explodes into individual tokens, any one of which fires
    on its own. Applying those to every decision would turn documented
    false-positive noise into a repo-wide edit block, so they remain gated.
    """
    scored = [_scored(STORAGE, score=0.0)]
    # "introduce" alone would trigger the "introduce ORM" anti_pattern under
    # the pre-#254 disjunctive matcher had the decision been retrieved.
    result = check_prompt("Let me introduce the new reporting feature.", scored)
    assert result.verdict == Severity.PASS


def test_top_n_limits_decisions_checked():
    d1 = Decision(
        id="d1", decision="D1", scope=["storage"], rationale="",
        constraints=["no postgres"], anti_patterns=[],
    )
    d2 = Decision(
        id="d2", decision="D2", scope=[], rationale="",
        constraints=[], anti_patterns=["introduce ORM"],
    )
    # d1 is ranked first (score=2.0), d2 second (score=1.0)
    scored = [_scored(d1, 2.0), _scored(d2, 1.0)]
    # top=1 → only d1 checked → "postgres" triggers WARN, "introduce ORM" not checked
    result = check_prompt("Use postgres and introduce ORM.", scored, top=1)
    assert result.verdict == Severity.WARN
    assert all(v.decision_id == "d1" for v in result.violations)


def test_case_insensitive_anti_pattern_match():
    scored = [_scored(STORAGE)]
    result = check_prompt("We will INTRODUCE an ORM framework.", scored)
    assert result.verdict == Severity.FAIL


def test_case_insensitive_constraint_match():
    scored = [_scored(STORAGE)]
    result = check_prompt("POSTGRES would work here.", scored)
    assert result.verdict == Severity.WARN


def test_no_match_when_term_is_embedded_substring():
    # "postgres" should NOT match "postgresql" (word boundary check)
    d = Decision(
        id="d1", decision="D1", scope=[], rationale="",
        constraints=["no postgres"], anti_patterns=[],
    )
    scored = [_scored(d)]
    result = check_prompt("We already use postgresql in staging.", scored)
    # \bpostgres\b does not match inside "postgresql"
    assert result.verdict == Severity.PASS


def test_multiple_decisions_can_each_trigger():
    scored = [_scored(STORAGE, 2.0), _scored(RETRIEVAL, 1.0)]
    # "postgres" triggers STORAGE constraint; "embeddings" triggers RETRIEVAL constraint
    result = check_prompt("Use postgres with embeddings for search.", scored)
    assert result.verdict == Severity.WARN
    decision_ids = {v.decision_id for v in result.violations}
    assert "storage_json" in decision_ids
    assert "retrieval_det" in decision_ids


def test_result_has_verdict_attribute():
    result = check_prompt("clean input", [_scored(STORAGE)])
    assert hasattr(result, "verdict")
    assert isinstance(result.verdict, Severity)


def test_result_has_violations_list():
    result = check_prompt("introduce ORM", [_scored(STORAGE)])
    assert hasattr(result, "violations")
    assert isinstance(result.violations, list)


def test_severity_enum_values():
    assert Severity.PASS == "PASS"
    assert Severity.WARN == "WARN"
    assert Severity.FAIL == "FAIL"


# ── H1 regression: migrated anti-pattern enforcement behavior ─────────────────
#
# Stage 1 (PR #21, squash 096b8be) moved legacy `anti_pattern.content` into
# `Decision.constraints` instead of `Decision.rationale`. Side effect (H1): when
# the migrated content begins with "No ..." it now matches the enforcer's
# `^no\s+(.+)$` constraint regex and produces WARN-severity violations on input
# tokens drawn from the content body.
#
# This is real, intended system behavior — constraints constrain. These tests
# pin it so a future enforcer regex change, stopword tweak, or migration
# refactor can't silently revert it without a failing test.


def test_migrated_anti_pattern_with_no_prefix_content_warns_via_constraint(
    tmp_path,
):
    """A legacy anti_pattern whose content starts with "No ..." migrates into
    `constraints` and triggers WARN-severity enforcement on terms drawn from
    that content body — via the enforcer's `^no\\s+` constraint pathway.

    Pre-Stage-1 (content -> rationale), this WARN was impossible: the enforcer
    only inspects constraints + anti_patterns, never rationale.
    """
    memory_file = tmp_path / "memory.json"
    memory_file.write_text(json.dumps({
        "meta": {"name": "h1-test", "description": "h1 fixture"},
        "items": [
            {
                "id": "anti-h1",
                "type": "anti_pattern",
                "title": "Do not add background workers",
                "content": "No background workers, message queues, or daemon processes.",
                "tags": ["forbidden"],
                "priority": "high",
            },
        ],
        "examples": [],
    }))
    store = MemoryStore(memory_file); store.load()
    decision = next(d for d in store.decisions() if d.id == "anti-h1")

    # Sanity: the migration shape Stage 1 fixed.
    assert decision.constraints == [
        "No background workers, message queues, or daemon processes."
    ]
    assert decision.rationale == ""

    # Input uses tokens unique to the constraint body — none appear in the
    # title-derived anti_patterns entry "Do not add background workers"
    # (which tokenizes to {background, workers}). This isolates the WARN
    # constraint pathway from the FAIL anti_patterns pathway so the verdict
    # is purely WARN.
    scored = [_scored(decision)]
    result = check_prompt(
        "Add message queues and daemon processes for async work.",
        scored,
    )
    assert result.verdict == Severity.WARN
    warn = next(v for v in result.violations if v.severity == Severity.WARN)
    assert warn.decision_id == "anti-h1"
    assert warn.rule.startswith("No background workers"), (
        f"WARN must cite the migrated constraint; got rule={warn.rule!r}"
    )
    assert warn.trigger in {"message", "queues", "daemon", "processes"}


def test_migrated_anti_pattern_without_no_prefix_does_not_warn_via_constraint(
    tmp_path,
):
    """Inverse boundary: when migrated content does NOT begin with "No ...",
    the enforcer's `^no\\s+` constraint pathway is correctly inert. The
    title-as-anti_pattern FAIL pathway is unaffected — this test isolates the
    constraint side specifically."""
    memory_file = tmp_path / "memory.json"
    memory_file.write_text(json.dumps({
        "meta": {"name": "h1-inverse-test", "description": "h1 inverse fixture"},
        "items": [
            {
                "id": "anti-h1-inv",
                "type": "anti_pattern",
                "title": "Some forbidden thing",
                # Content deliberately does NOT begin with "No ".
                "content": "Background workers and message queues add operational weight.",
                "tags": ["forbidden"],
                "priority": "high",
            },
        ],
        "examples": [],
    }))
    store = MemoryStore(memory_file); store.load()
    decision = next(d for d in store.decisions() if d.id == "anti-h1-inv")
    assert decision.constraints == [
        "Background workers and message queues add operational weight."
    ]

    scored = [_scored(decision)]
    result = check_prompt(
        "We could add a background worker queue to handle this.",
        scored,
    )
    # No constraint-driven WARN: the only constraint doesn't begin with "No ".
    constraint_warns = [
        v for v in result.violations
        if v.severity == Severity.WARN and v.decision_id == "anti-h1-inv"
    ]
    assert constraint_warns == [], (
        f"Constraint without `^no\\s+` prefix must not produce WARN; "
        f"got {[v.rule for v in constraint_warns]}"
    )


def test_shipped_anti_002_warns_via_migrated_constraint_on_anchor_term():
    """Pin H1 on the live shipped fixture: anti-002 ("Do not add agentic loops
    in v1") migrates into a constraint beginning with "No tool-use, function
    calling, or multi-turn agent loops…", which produces WARN enforcement on
    inputs containing anchor terms like "function calling" or "tool-use".

    This is the real, observable system behavior introduced by Stage 1
    (PR #21, squash 096b8be) and visible only via direct `check_prompt`
    (the shipped benchmark suite uses the structured Layer 2 path)."""
    store = MemoryStore(EXAMPLE_MEMORY); store.load()
    retriever = DecisionRetriever(store.decisions())
    scored = retriever.retrieve(
        "Should we add multi-agent support to Mneme so it can coordinate between agents?"
    )
    # anti-002 must be in the top-3 retrieval (Stage 1 locks rank 1 here via
    # tests/test_benchmark.py::test_feature_boundary_violation_retrieves_anti_002_at_rank_1).
    top3_ids = [s.decision.id for s in scored if s.score > 0][:3]
    assert "anti-002" in top3_ids, (
        f"Test premise broken: anti-002 not in top-3; got {top3_ids}"
    )

    # Anchor term "function calling" maps to constraint terms "function" and
    # "calling" via the enforcer's `_rule_terms` tokenizer.
    result = check_prompt(
        "Use function calling and a tool-use loop to coordinate workers.",
        scored,
        top=3,
    )
    anti_002_warns = [
        v for v in result.violations
        if v.severity == Severity.WARN and v.decision_id == "anti-002"
    ]
    assert anti_002_warns, (
        f"Expected WARN from anti-002's migrated constraint; got violations="
        f"{[(v.severity, v.decision_id, v.trigger) for v in result.violations]}"
    )
    rule = anti_002_warns[0].rule
    assert rule.lower().startswith("no tool-use"), (
        f"WARN must cite the migrated constraint beginning 'No tool-use…'; "
        f"got rule={rule!r}"
    )
    assert anti_002_warns[0].trigger in {
        "tool", "function", "calling", "multi", "turn", "agent", "loops",
        "module", "mneme", "single", "call", "response", "pipeline",
        "agentic", "behaviour", "separate", "concern", "product", "layer",
    }


# ── CLI integration tests ─────────────────────────────────────────────────────

def test_check_cmd_pass_exits_zero(tmp_path):
    mem = _memory_file(tmp_path)
    inp = _input_file(tmp_path, "Store everything as flat JSON files.")
    exit_code = main([
        "check",
        "--memory", str(mem),
        "--input", str(inp),
        "--query", "working on storage layer",
    ])
    assert exit_code == 0


def test_check_cmd_fail_exits_two(tmp_path):
    mem = _memory_file(tmp_path)
    inp = _input_file(tmp_path, "We should introduce an ORM for our storage layer.")
    exit_code = main([
        "check",
        "--memory", str(mem),
        "--input", str(inp),
        "--query", "storage layer",
    ])
    assert exit_code == 2


def test_check_cmd_warn_exits_one(tmp_path):
    mem = _memory_file(tmp_path)
    inp = _input_file(tmp_path, "Should we move to postgres for the storage backend?")
    exit_code = main([
        "check",
        "--memory", str(mem),
        "--input", str(inp),
        "--query", "storage layer",
    ])
    assert exit_code == 1


def test_check_cmd_prints_verdict(tmp_path, capsys):
    mem = _memory_file(tmp_path)
    inp = _input_file(tmp_path, "Store everything as flat JSON files.")
    main(["check", "--memory", str(mem), "--input", str(inp), "--query", "storage"])
    out = capsys.readouterr().out
    assert "PASS" in out


def test_check_cmd_prints_fail_verdict(tmp_path, capsys):
    mem = _memory_file(tmp_path)
    inp = _input_file(tmp_path, "introduce an ORM now.")
    main(["check", "--memory", str(mem), "--input", str(inp), "--query", "storage"])
    out = capsys.readouterr().out
    assert "FAIL" in out


def test_check_cmd_prints_triggering_decision_id(tmp_path, capsys):
    mem = _memory_file(tmp_path)
    inp = _input_file(tmp_path, "introduce an ORM for storage.")
    main(["check", "--memory", str(mem), "--input", str(inp), "--query", "storage"])
    out = capsys.readouterr().out
    assert "storage_json" in out


def test_check_cmd_prints_triggering_rule(tmp_path, capsys):
    mem = _memory_file(tmp_path)
    inp = _input_file(tmp_path, "introduce an ORM for storage.")
    main(["check", "--memory", str(mem), "--input", str(inp), "--query", "storage"])
    out = capsys.readouterr().out
    assert "introduce ORM" in out or "orm" in out.lower()


def test_check_cmd_respects_top_flag(tmp_path):
    mem = _memory_file(tmp_path)
    # Both decisions have violations: "postgres" (storage) + "cosine" (retrieval)
    # top=1 → only highest-scored decision checked
    inp = _input_file(tmp_path, "Use postgres with cosine similarity search.")
    # Query hits storage strongly (scope=storage,backend match)
    exit_code_top1 = main([
        "check",
        "--memory", str(mem),
        "--input", str(inp),
        "--query", "storage backend",
        "--top", "1",
    ])
    exit_code_top2 = main([
        "check",
        "--memory", str(mem),
        "--input", str(inp),
        "--query", "storage backend",
        "--top", "2",
    ])
    # With top=2, we get more violations (possibly same exit code if both WARN)
    # The key assertion: top=1 exits with some code; top=2 may find more violations
    # Both should be non-zero (violations exist in both cases for this input)
    assert exit_code_top1 in (1, 2)
    assert exit_code_top2 in (1, 2)


def test_check_cmd_reads_input_from_file(tmp_path):
    mem = _memory_file(tmp_path)
    inp = _input_file(tmp_path, "introduce an ORM here")
    exit_code = main([
        "check",
        "--memory", str(mem),
        "--input", str(inp),
        "--query", "storage",
    ])
    assert exit_code == 2


# --- typed deterministic rules (#250) ---

def test_forbid_literal_fails_even_when_decision_scores_zero():
    decision = Decision(
        id="ADR-201",
        decision="Use the published distribution name",
        rules=[Rule(type="FORBID_LITERAL", value="pip install mneme")],
    )
    result = check_prompt(
        "pip install mneme\n",
        [_scored(decision, score=0.0)],
    )
    assert result.verdict == Severity.FAIL
    [violation] = result.violations
    assert violation.kind == "typed_rule"
    assert violation.rule_type == "FORBID_LITERAL"
    assert violation.trigger == "pip install mneme"


def test_forbid_literal_does_not_match_longer_slug():
    decision = Decision(
        id="ADR-201",
        decision="Use the published distribution name",
        rules=[Rule(type="FORBID_LITERAL", value="pip install mneme")],
    )
    result = check_prompt(
        "pip install mneme-hq\n",
        [_scored(decision, score=0.0)],
    )
    assert result.verdict == Severity.PASS


def test_forbid_literal_is_case_sensitive():
    decision = Decision(
        id="ADR-201",
        decision="Use the published distribution name",
        rules=[Rule(type="FORBID_LITERAL", value="pip install mneme")],
    )
    result = check_prompt(
        "PIP INSTALL MNEME\n",
        [_scored(decision, score=0.0)],
    )
    assert result.verdict == Severity.PASS


def test_typed_rule_does_not_flag_its_declaring_adr(tmp_path):
    source = tmp_path / "ADR-201.md"
    source.write_text("- FORBID_LITERAL: pip install mneme\n", encoding="utf-8")
    decision = Decision(
        id="ADR-201",
        decision="Use the published distribution name",
        rules=[Rule(type="FORBID_LITERAL", value="pip install mneme")],
        source_path=str(source),
    )
    result = check_prompt(
        source.read_text(encoding="utf-8"),
        [_scored(decision, score=0.0)],
        input_path=source,
    )
    assert result.verdict == Severity.PASS


def test_typed_rule_does_not_flag_its_policy_memory_file(tmp_path):
    memory = tmp_path / "project_memory.json"
    memory.write_text('"value": "pip install mneme"\n', encoding="utf-8")
    decision = Decision(
        id="ADR-201",
        decision="Use the published distribution name",
        rules=[Rule(type="FORBID_LITERAL", value="pip install mneme")],
        memory_path=str(memory),
    )
    result = check_prompt(
        memory.read_text(encoding="utf-8"),
        [_scored(decision, score=0.0)],
        input_path=memory,
    )
    assert result.verdict == Severity.PASS


def test_scoped_typed_rule_applies_only_to_included_paths(tmp_path):
    memory = tmp_path / ".mneme" / "project_memory.json"
    rule = Rule(
        type="FORBID_LITERAL",
        value="install legacy-client",
        include_paths=("docs/**",),
    )
    decision = Decision(
        id="ADR-020",
        decision="Scope the rule",
        rules=[rule],
        memory_path=str(memory),
    )

    applied = check_prompt(
        "install legacy-client",
        [_scored(decision, score=0.0)],
        input_path=tmp_path / "docs" / "guide.md",
    )
    excluded = check_prompt(
        "install legacy-client",
        [_scored(decision, score=0.0)],
        input_path=tmp_path / "src" / "app.py",
    )

    assert applied.verdict == Severity.FAIL
    assert applied.evaluation_complete
    assert applied.applicability[0].outcome.value == "APPLIED"
    assert applied.applicability[0].selector == "docs/**"
    assert excluded.verdict == Severity.PASS
    assert excluded.applicability[0].outcome.value == "EXCLUDED"


def test_scoped_typed_rule_exclude_overrides_include(tmp_path):
    memory = tmp_path / ".mneme" / "project_memory.json"
    decision = Decision(
        id="ADR-020",
        decision="Scope the rule",
        rules=[Rule(
            type="FORBID_LITERAL",
            value="install legacy-client",
            include_paths=("docs/**",),
            exclude_paths=("docs/generated/**",),
        )],
        memory_path=str(memory),
    )
    result = check_prompt(
        "install legacy-client",
        [_scored(decision, score=0.0)],
        input_path=tmp_path / "docs" / "generated" / "guide.md",
    )
    assert result.verdict == Severity.PASS
    assert result.applicability[0].outcome.value == "EXCLUDED"
    assert result.applicability[0].selector == "docs/generated/**"


def test_scoped_typed_rule_missing_path_reports_unknown():
    decision = Decision(
        id="ADR-020",
        decision="Scope the rule",
        rules=[Rule(
            type="FORBID_LITERAL",
            value="install legacy-client",
            include_paths=("docs/**",),
        )],
        memory_path="project_memory.json",
    )
    result = check_prompt(
        "install legacy-client",
        [_scored(decision, score=0.0)],
    )
    assert result.verdict == Severity.PASS
    assert not result.evaluation_complete
    assert result.applicability[0].outcome.value == "UNKNOWN"

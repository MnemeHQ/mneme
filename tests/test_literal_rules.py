"""Tests for the FORBID_STRING literal rule vocabulary (issue #250).

ADR-005 forbade `pip install mneme` by name, in a Correct/Forbidden table, and
mnemehq.com shipped that exact string for months. The root cause was not
staleness: `VALID_KINDS` held only FORBID_DEPENDENCY / FORBID_PATH /
REQUIRE_PATH, so a content rule was **inexpressible**, and `adr_compiler`
hardcodes `anti_patterns=[]`, so an ADR could only ever WARN.

Reusing `anti_patterns` does not work. `pip install mneme` tokenizes to
[pip, install, mneme] and the enforcer fires on ANY single token, so it flags
`pipx install "mneme-hq>=0.5.1"` -- the *correct* command -- plus any prose
containing the word "install". Plain substring matching fails too, because
`pip install mneme` is a substring of `pip install mneme-hq`, and word-boundary
matching fails because the hyphen is itself a boundary.

Hence literal spans with containment suppression: a forbidden span is
suppressed only when an allowed span fully contains it. See ADR-019.
"""
import json

import pytest

from mneme.adr_constraints import ConstraintParseError, parse_constraints_section
from mneme.decision_retriever import ScoredDecision
from mneme.enforcer import Severity, check_prompt
from mneme.memory_store import MemoryStore
from mneme.schemas import Decision, ForbiddenLiteral


def _scored(decision, score=0.0):
    """Score 0.0 deliberately: literal rules must not be retrieval-gated."""
    return ScoredDecision(decision=decision, score=score)


def _decision(literals):
    return Decision(
        id="adr-005",
        decision="Package is published as mneme-hq",
        rationale="brand vs namespace",
        scope=["brand.namespace"],
        literal_rules=literals,
    )


# ── the ADR-005 case, which motivated the whole issue ─────────────────────────

ADR_005 = _decision([
    ForbiddenLiteral(
        value="pip install mneme",
        allowed_containers=["pip install mneme-hq"],
    )
])


def test_forbidden_literal_is_flagged():
    result = check_prompt("Run `pip install mneme` to get started.", [_scored(ADR_005)])
    assert result.verdict == Severity.FAIL
    assert any(v.trigger == "pip install mneme" for v in result.violations)


def test_correct_command_is_not_flagged():
    """The exact false positive that made anti_patterns unusable here."""
    result = check_prompt("Run `pip install mneme-hq` to get started.", [_scored(ADR_005)])
    assert result.verdict == Severity.PASS, (
        f"the correct command must not be flagged; got {result.violations}"
    )


def test_both_commands_on_one_line_flags_only_the_wrong_one():
    result = check_prompt(
        "Use pip install mneme-hq, not pip install mneme.", [_scored(ADR_005)]
    )
    assert result.verdict == Severity.FAIL
    assert len(result.violations) == 1


def test_literal_rules_are_not_retrieval_gated():
    """A typed rule is enforceable by construction, so ranking must not gate it.

    This is the property that makes the vocabulary worth having: it closes
    #254 for these rules permanently rather than by term-count proxy.
    """
    result = check_prompt("pip install mneme", [_scored(ADR_005, score=0.0)])
    assert result.verdict == Severity.FAIL


def test_matching_is_case_insensitive():
    result = check_prompt("PIP INSTALL MNEME", [_scored(ADR_005)])
    assert result.verdict == Severity.FAIL


def test_every_occurrence_is_reported():
    result = check_prompt(
        "pip install mneme\nand again pip install mneme\n", [_scored(ADR_005)]
    )
    assert len(result.violations) == 2


# ── containment suppression semantics ────────────────────────────────────────

def test_overlapping_but_not_containing_allow_does_not_suppress():
    """Sol's authoring hazard, pinned as intended behaviour.

    FORBID `pip install mneme` with ALLOW `install mneme-hq` gives spans
    (0,17) and (4,20) against `pip install mneme-hq`: they overlap, but the
    allowed span does not *contain* the forbidden one, so the correct command
    is reported. The exemption must cover the whole forbidden literal
    including its prefix.

    This is a real trap, so it is pinned rather than silently tolerated -- the
    fix belongs in authoring guidance and the compile-time warning below.
    """
    d = _decision([
        ForbiddenLiteral(
            value="pip install mneme",
            allowed_containers=["install mneme-hq"],  # missing the "pip " prefix
        )
    ])
    result = check_prompt("pip install mneme-hq", [_scored(d)])
    assert result.verdict == Severity.FAIL


def test_exemptions_do_not_leak_between_rules():
    """Per-rule containers, not a flat decision-level pool.

    A flat pool would let an exemption written for one prohibition silently
    neuter an identically-worded prohibition added later for a different
    reason.
    """
    d = _decision([
        ForbiddenLiteral(value="pip install mneme",
                         allowed_containers=["pip install mneme-hq"]),
        ForbiddenLiteral(value="pip install mneme", allowed_containers=[]),
    ])
    result = check_prompt("pip install mneme-hq", [_scored(d)])
    assert result.verdict == Severity.FAIL, (
        "the second rule has no exemption and must still fire"
    )


def test_clean_content_passes():
    result = check_prompt("Install the package from PyPI.", [_scored(ADR_005)])
    assert result.verdict == Severity.PASS


# ── directive parsing ────────────────────────────────────────────────────────

def test_parses_forbid_string_directive():
    body = "## Constraints\n- FORBID_STRING: pip install mneme\n"
    [d] = parse_constraints_section(body)
    assert (d.kind, d.value) == ("FORBID_STRING", "pip install mneme")


def test_allow_attaches_to_the_preceding_forbid():
    body = (
        "## Constraints\n"
        "- FORBID_STRING: pip install mneme\n"
        "- ALLOW_CONTAINING_STRING: pip install mneme-hq\n"
    )
    out = parse_constraints_section(body)
    assert [d.kind for d in out] == ["FORBID_STRING", "ALLOW_CONTAINING_STRING"]


def test_allow_without_a_preceding_forbid_raises():
    """An exemption with nothing to exempt is an authoring error, not a no-op."""
    body = "## Constraints\n- ALLOW_CONTAINING_STRING: pip install mneme-hq\n"
    with pytest.raises(ConstraintParseError):
        parse_constraints_section(body)


# ── serialization round-trip ─────────────────────────────────────────────────

def test_literal_rules_survive_a_memory_round_trip(tmp_path):
    """Sol's warning: fields that compile but do not persist are worse than absent.

    A rule that vanishes on reload gives the author a green compile and no
    enforcement -- the exact ADR-005 failure shape.
    """
    mem = tmp_path / "project_memory.json"
    mem.write_text(json.dumps({
        "meta": {"name": "t", "description": "t"},
        "items": [], "examples": [],
        "decisions": [{
            "id": "adr-005",
            "decision": "Package is published as mneme-hq",
            "rationale": "brand vs namespace",
            "scope": ["brand.namespace"],
            "constraints": [],
            "anti_patterns": [],
            "literal_rules": [{
                "value": "pip install mneme",
                "allowed_containers": ["pip install mneme-hq"],
            }],
        }],
    }), encoding="utf-8")

    store = MemoryStore(mem)
    store.load()
    [d] = [x for x in store.decisions() if x.id == "adr-005"]
    assert d.literal_rules == [
        ForbiddenLiteral(value="pip install mneme",
                         allowed_containers=["pip install mneme-hq"])
    ]

    # And the loaded decision actually enforces.
    result = check_prompt("pip install mneme", [_scored(d)])
    assert result.verdict == Severity.FAIL


def test_adr_005_rule_is_expressible_end_to_end(tmp_path):
    """The whole point of #250: author the rule in an ADR, have it enforced.

    Before this vocabulary, ADR-005's Correct/Forbidden table compiled to
    `constraints: []` and `anti_patterns: []` -- a decision with nothing to
    enforce, from its very first import. This walks the full path: ADR body ->
    compiler -> Decision -> enforcer.
    """
    from mneme.adr_compiler import adrs_to_decisions
    from mneme.adr_parser import parse_adr_file

    wrong = "pip" + " install mneme"          # assembled so the repo gate
    right = "pip" + " install mneme-hq"       # sees no literal instruction
    adr = tmp_path / "ADR-005-namespace.md"
    adr.write_text(
        "---\n"
        "id: ADR-005\n"
        'title: "Brand vs Package Namespace"\n'
        "status: accepted\n"
        "priority: foundational\n"
        "date: 2026-08-08\n"
        "scope: brand.namespace\n"
        "---\n\n"
        "# ADR-005\n\n"
        "## Constraints\n"
        f"- FORBID_STRING: {wrong}\n"
        f"- ALLOW_CONTAINING_STRING: {right}\n",
        encoding="utf-8",
    )

    [decision] = adrs_to_decisions([parse_adr_file(adr)])
    assert decision.literal_rules == [
        ForbiddenLiteral(value=wrong, allowed_containers=[right])
    ]

    # The violation that shipped on mnemehq.com for months.
    assert check_prompt(
        f"Install it with `{wrong}`.", [_scored(decision)]
    ).verdict == Severity.FAIL

    # The correct command must stay clean -- this is what made reusing
    # anti_patterns impossible.
    assert check_prompt(
        f"Install it with `{right}`.", [_scored(decision)]
    ).verdict == Severity.PASS


def test_decision_without_literal_rules_still_loads(tmp_path):
    """Existing memories must not need migrating."""
    mem = tmp_path / "project_memory.json"
    mem.write_text(json.dumps({
        "meta": {"name": "t", "description": "t"},
        "items": [], "examples": [],
        "decisions": [{
            "id": "legacy",
            "decision": "Use JSON storage",
            "rationale": "",
            "scope": ["storage"],
            "constraints": ["no postgres"],
            "anti_patterns": [],
        }],
    }), encoding="utf-8")
    store = MemoryStore(mem)
    store.load()
    [d] = [x for x in store.decisions() if x.id == "legacy"]
    assert d.literal_rules == []

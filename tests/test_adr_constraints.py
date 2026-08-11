# tests/test_adr_constraints.py
"""Tests for the ## Constraints body directive parser."""
from __future__ import annotations

from mneme.adr_constraints import (
    ConstraintDirective,
    ConstraintParseError,
    parse_constraints_section,
)


def test_parse_forbid_dependency_directive():
    body = """## Decision

Do not use mongo.

## Constraints
- FORBID_DEPENDENCY: mongodb
"""
    out = parse_constraints_section(body)
    assert out == [ConstraintDirective(kind="FORBID_DEPENDENCY", value="mongodb")]


def test_parse_forbid_literal_directive():
    body = "## Constraints\n- FORBID_LITERAL: pip install mneme\n"
    assert parse_constraints_section(body) == [
        ConstraintDirective(kind="FORBID_LITERAL", value="pip install mneme")
    ]


def test_parse_multiple_directives_in_order():
    body = """## Constraints
- FORBID_PATH: src/legacy/billing/**
- REQUIRE_PATH: billing/**
- FORBID_DEPENDENCY: mongodb
"""
    out = parse_constraints_section(body)
    assert [(d.kind, d.value) for d in out] == [
        ("FORBID_PATH", "src/legacy/billing/**"),
        ("REQUIRE_PATH", "billing/**"),
        ("FORBID_DEPENDENCY", "mongodb"),
    ]


def test_no_constraints_section_returns_empty_list():
    body = "## Decision\n\nUse Postgres.\n"
    assert parse_constraints_section(body) == []


def test_constraints_section_with_no_directives_returns_empty_list():
    body = "## Constraints\n\n(none yet)\n"
    assert parse_constraints_section(body) == []


def test_unknown_directive_kind_raises():
    body = "## Constraints\n- BANANA: yellow\n"
    try:
        parse_constraints_section(body)
    except ConstraintParseError as exc:
        assert "BANANA" in str(exc)
    else:
        raise AssertionError("expected ConstraintParseError")


def test_constraints_section_ends_at_next_h2():
    body = """## Constraints
- FORBID_DEPENDENCY: redis

## Notes
- Should not be parsed as a directive
- FORBID_DEPENDENCY: kafka
"""
    out = parse_constraints_section(body)
    assert out == [ConstraintDirective(kind="FORBID_DEPENDENCY", value="redis")]


def test_directive_value_strips_whitespace():
    body = "## Constraints\n- FORBID_DEPENDENCY:    mongodb   \n"
    [d] = parse_constraints_section(body)
    assert d.value == "mongodb"


# ── #258: malformed directives must not be silently dropped ──────────────────
#
# The module documents itself as "a strict, deterministic parser", but that
# strictness only ever applied to lines matching `_DIRECTIVE_LINE`. A bullet
# that was clearly *meant* to be a directive and failed the regex fell through
# `if not m: continue` and vanished. Governance fails in the dangerous
# direction there: the author believes a rule was recorded, the compiler
# emitted nothing, and the decision ships with no enforcement payload.
#
# This matters most right before a new directive vocabulary lands (#250), when
# authors are typing names they have never typed before.

import pytest


@pytest.mark.parametrize("line,reason", [
    ("- forbid_dependency: mongodb", "lowercase kind"),
    ("- Forbid_Dependency: mongodb", "mixed-case kind"),
    ("- FORBID-DEPENDENCY: mongodb", "hyphen instead of underscore"),
    ("- FORBID_DEPENDENCY:", "missing value"),
    ("- FORBID_DEPENDENCY:   ", "whitespace-only value"),
    ("- FORBID_DEPENDENCY mongodb", "missing colon"),
])
def test_malformed_directive_raises_instead_of_being_dropped(line, reason):
    body = f"## Constraints\n{line}\n"
    with pytest.raises(ConstraintParseError) as exc:
        parse_constraints_section(body)
    # The author has to be able to find the offending line.
    assert line.lstrip("- ").split(":")[0].strip() in str(exc.value) or \
        line.strip() in str(exc.value), (
            f"{reason}: error must identify the offending directive, got {exc.value!r}"
        )


def test_malformed_directive_raises_even_alongside_valid_ones():
    """A valid directive must not mask a broken sibling."""
    body = (
        "## Constraints\n"
        "- FORBID_DEPENDENCY: mongodb\n"
        "- forbid_path: src/legacy/**\n"
    )
    with pytest.raises(ConstraintParseError):
        parse_constraints_section(body)


@pytest.mark.parametrize("line", [
    "- Should not be parsed as a directive",
    "- See the migration notes at https://example.com/docs",
    "- Prefer sqlite: it keeps the deployment single-file",
    "- one, two, three",
    "(none yet)",
    "",
])
def test_prose_bullets_are_still_ignored(line):
    """Strictness must not turn ordinary prose into a compile failure.

    The discriminator is deliberately narrow: a bullet counts as a directive
    attempt only when the text before its first colon is a single token that
    looks like a directive name. `Prefer sqlite: ...` has a lowercase one-word
    head with no underscore, so it reads as prose; `forbid_path: ...` does not.
    """
    body = f"## Constraints\n{line}\n"
    assert parse_constraints_section(body) == []


def test_prose_and_valid_directive_coexist():
    body = (
        "## Constraints\n"
        "- These rules apply to the billing subsystem only.\n"
        "- FORBID_DEPENDENCY: mongodb\n"
    )
    assert parse_constraints_section(body) == [
        ConstraintDirective(kind="FORBID_DEPENDENCY", value="mongodb")
    ]


def test_malformed_directive_outside_the_section_is_ignored():
    """Section bounding still wins: strictness applies only inside."""
    body = (
        "## Constraints\n"
        "- FORBID_DEPENDENCY: redis\n"
        "\n"
        "## Notes\n"
        "- forbid_dependency: kafka\n"
    )
    assert parse_constraints_section(body) == [
        ConstraintDirective(kind="FORBID_DEPENDENCY", value="redis")
    ]

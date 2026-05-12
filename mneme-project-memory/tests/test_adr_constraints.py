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

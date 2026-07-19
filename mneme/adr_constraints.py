"""
adr_constraints.py — Parse ``## Constraints`` body directives.

Mneme ADR bodies may include an optional ``## Constraints`` section listing
machine-actionable directives, one per line, in the form::

    ## Constraints
    - FORBID_DEPENDENCY: mongodb
    - FORBID_PATH: src/legacy/**
    - REQUIRE_PATH: billing/**

This module is a strict, deterministic parser. Unknown directive kinds raise.
The section is bounded by the next H2 header or end of body — content beyond
the section boundary is ignored, even if it looks like a directive.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final


VALID_KINDS: Final[frozenset[str]] = frozenset({
    "FORBID_DEPENDENCY",
    "FORBID_PATH",
    "REQUIRE_PATH",
})


@dataclass(frozen=True)
class ConstraintDirective:
    """One parsed directive from a ``## Constraints`` section."""

    kind: str   # one of VALID_KINDS
    value: str  # raw value, trimmed


class ConstraintParseError(Exception):
    """Raised when a ``## Constraints`` section contains an unknown directive kind."""


_SECTION_HEADER = re.compile(r"^##\s+Constraints\s*$", re.MULTILINE)
_NEXT_H2 = re.compile(r"^##\s+\S", re.MULTILINE)
_DIRECTIVE_LINE = re.compile(r"^\s*-\s*([A-Z_]+)\s*:\s*(.+?)\s*$")


def parse_constraints_section(body: str) -> list[ConstraintDirective]:
    """Extract directives from the first ``## Constraints`` section in body.

    Returns an empty list if no section is present or the section has no
    directive lines. Raises ``ConstraintParseError`` for unknown directive
    kinds — silently dropping them would let typos defeat governance.
    """
    header_match = _SECTION_HEADER.search(body)
    if not header_match:
        return []

    section_start = header_match.end()
    next_h2 = _NEXT_H2.search(body, section_start)
    section_end = next_h2.start() if next_h2 else len(body)
    section_text = body[section_start:section_end]

    out: list[ConstraintDirective] = []
    for line in section_text.splitlines():
        m = _DIRECTIVE_LINE.match(line)
        if not m:
            continue
        kind, value = m.group(1), m.group(2).strip()
        if kind not in VALID_KINDS:
            raise ConstraintParseError(
                f"unknown constraint directive {kind!r} "
                f"(expected one of {sorted(VALID_KINDS)})"
            )
        out.append(ConstraintDirective(kind=kind, value=value))
    return out


__all__ = ["ConstraintDirective", "ConstraintParseError", "parse_constraints_section"]

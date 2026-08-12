"""
adr_constraints.py — Parse ``## Constraints`` body directives.

Mneme ADR bodies may include an optional ``## Constraints`` section listing
machine-actionable directives, one per line, in the form::

    ## Constraints
    - FORBID_LITERAL: install legacy-package
    - FORBID_DEPENDENCY: mongodb
    - FORBID_PATH: src/legacy/**
    - REQUIRE_PATH: billing/**

Path-scoped typed rules use a structured mapping::

    - FORBID_LITERAL:
        value: install legacy-package
        include_paths:
          - docs/**
        exclude_paths:
          - docs/generated/**

This module is a strict, deterministic parser. Unknown directive kinds raise,
and so does a bullet that was evidently meant to be a directive but is
malformed — wrong case, wrong separator, empty value, or a missing colon.
Silently dropping those would let a typo defeat governance while the author
believes the rule was recorded (#258).

Ordinary prose bullets are still ignored, so the section can carry a note
without failing compilation. See ``_looks_like_directive`` for where the line
is drawn.

The section is bounded by the next H2 header or end of body — content beyond
the section boundary is ignored, even if it looks like a directive.
"""
from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from typing import Final

import yaml
from yaml.constructor import ConstructorError

from mneme.path_selectors import validate_path_pattern


VALID_KINDS: Final[frozenset[str]] = frozenset({
    "FORBID_LITERAL",
    "FORBID_DEPENDENCY",
    "FORBID_PATH",
    "REQUIRE_PATH",
})


@dataclass(frozen=True)
class ConstraintDirective:
    """One parsed directive from a ``## Constraints`` section."""

    kind: str   # one of VALID_KINDS
    value: str  # raw value, trimmed
    include_paths: tuple[str, ...] | None = None
    exclude_paths: tuple[str, ...] = ()


class ConstraintParseError(Exception):
    """Raised when a ``## Constraints`` section contains an unknown directive kind."""


_SECTION_HEADER = re.compile(r"^##\s+Constraints\s*$", re.MULTILINE)
_NEXT_H2 = re.compile(r"^##\s+\S", re.MULTILINE)
_DIRECTIVE_LINE = re.compile(r"^\s*-\s*([A-Z_]+)\s*:\s*(.+?)\s*$")
_STRUCTURED_HEADER = re.compile(r"^(\s*)-\s*([A-Z_]+)\s*:\s*$")

# A list bullet of any kind, with its content captured.
_BULLET = re.compile(r"^\s*[-*]\s+(.*)$")

# The head of a bullet that reads as an attempted directive name: a single
# token, no whitespace, starting with a letter.
_HEAD_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def _normalise_kind(token: str) -> str:
    """Fold a directive-name token toward its canonical form."""
    return token.upper().replace("-", "_")


def _looks_like_directive(content: str) -> bool:
    """True when a bullet was evidently meant to be a directive.

    Deliberately narrow, because the alternative failure is worse: too broad a
    discriminator turns ordinary prose in a ``## Constraints`` section into a
    compile error, and authors would learn to avoid the section entirely.

    A bullet qualifies when either:

    - the text before its first colon is a single token that looks like a
      directive name -- all-uppercase, or containing ``_`` or ``-``. This
      catches ``forbid_dependency:``, ``FORBID-DEPENDENCY:`` and
      ``FORBID_DEPENDENCY:`` with an empty value, while leaving
      ``Prefer sqlite: it keeps the deployment single-file`` alone, whose
      pre-colon text contains a space; or
    - it has no colon at all, but its first token names a known kind --
      catching ``- FORBID_DEPENDENCY mongodb``.
    """
    head, sep, _ = content.partition(":")
    if sep:
        head = head.strip()
        if _HEAD_TOKEN.match(head) and (
            head.isupper() or "_" in head or "-" in head
        ):
            return True
        return False

    first = content.split()[0] if content.split() else ""
    return _normalise_kind(first) in VALID_KINDS


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _string_list(
    mapping: dict[object, object],
    key: str,
    *,
    required: bool,
) -> tuple[str, ...]:
    if key not in mapping:
        if required:
            raise ConstraintParseError(
                f"structured FORBID_LITERAL requires {key!r}"
            )
        return ()
    value = mapping[key]
    if not isinstance(value, list) or (required and not value):
        qualifier = "non-empty " if required else ""
        raise ConstraintParseError(
            f"structured FORBID_LITERAL {key!r} must be a {qualifier}list"
        )
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ConstraintParseError(
            f"structured FORBID_LITERAL {key!r} must contain non-empty strings"
        )
    patterns = tuple(item.strip() for item in value)
    try:
        for pattern in patterns:
            validate_path_pattern(pattern)
    except ValueError as exc:
        raise ConstraintParseError(
            f"invalid structured FORBID_LITERAL {key!r}: {exc}"
        ) from exc
    return patterns


def _parse_structured_directive(
    kind: str,
    block_lines: list[str],
) -> ConstraintDirective:
    if kind not in VALID_KINDS:
        raise ConstraintParseError(
            f"unknown constraint directive {kind!r} "
            f"(expected one of {sorted(VALID_KINDS)})"
        )
    if kind != "FORBID_LITERAL":
        raise ConstraintParseError(
            f"structured form is not supported for constraint directive {kind!r}"
        )
    try:
        data = yaml.load(
            textwrap.dedent("\n".join(block_lines)),
            Loader=_UniqueKeyLoader,
        )
    except (yaml.YAMLError, TypeError) as exc:
        raise ConstraintParseError(
            f"invalid structured FORBID_LITERAL: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise ConstraintParseError(
            "structured FORBID_LITERAL body must be a mapping"
        )
    allowed = {"value", "include_paths", "exclude_paths"}
    unknown = [key for key in data if key not in allowed]
    if unknown:
        raise ConstraintParseError(
            "unknown structured FORBID_LITERAL fields: "
            f"{sorted(unknown, key=str)!r}"
        )
    value = data.get("value")
    if not isinstance(value, str) or not value.strip():
        raise ConstraintParseError(
            "structured FORBID_LITERAL requires a non-empty string 'value'"
        )
    include_paths = _string_list(data, "include_paths", required=True)
    exclude_paths = _string_list(data, "exclude_paths", required=False)
    return ConstraintDirective(
        kind=kind,
        value=value.strip(),
        include_paths=include_paths,
        exclude_paths=exclude_paths,
    )


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
    lines = section_text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        structured = _STRUCTURED_HEADER.match(line)
        if structured:
            base_indent = len(structured.group(1))
            kind = structured.group(2)
            block_lines: list[str] = []
            index += 1
            while index < len(lines):
                candidate = lines[index]
                if not candidate.strip():
                    block_lines.append(candidate)
                    index += 1
                    continue
                indent = len(candidate) - len(candidate.lstrip())
                if indent <= base_indent:
                    break
                block_lines.append(candidate)
                index += 1
            if not any(item.strip() for item in block_lines):
                raise ConstraintParseError(
                    f"constraint directive {kind!r} has an empty value"
                )
            out.append(_parse_structured_directive(kind, block_lines))
            continue

        m = _DIRECTIVE_LINE.match(line)
        if m:
            kind, value = m.group(1), m.group(2).strip()
            if kind not in VALID_KINDS:
                raise ConstraintParseError(
                    f"unknown constraint directive {kind!r} "
                    f"(expected one of {sorted(VALID_KINDS)})"
                )
            if not value:
                # `(.+?)` can match a lone space, so a whitespace-only value
                # satisfies the regex and then strips to nothing -- a directive
                # that names a real kind and forbids nothing.
                raise ConstraintParseError(
                    f"constraint directive {kind!r} has an empty value: "
                    f"{line.strip()!r}"
                )
            out.append(ConstraintDirective(kind=kind, value=value))
            index += 1
            continue

        # Not a well-formed directive. Before dropping it, decide whether it
        # was meant to be one -- silently discarding an attempted rule is the
        # dangerous direction for governance (#258).
        bullet = _BULLET.match(line)
        if bullet and _looks_like_directive(bullet.group(1).strip()):
            raise ConstraintParseError(
                f"malformed constraint directive: {line.strip()!r}. "
                f"Directives must be written as "
                f"`- KIND: value` with an uppercase, underscore-separated "
                f"KIND and a non-empty value "
                f"(expected one of {sorted(VALID_KINDS)})."
            )
        index += 1
    return out


__all__ = ["ConstraintDirective", "ConstraintParseError", "parse_constraints_section"]

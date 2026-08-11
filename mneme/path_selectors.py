"""Deterministic path applicability for typed Mneme rules.

ADR-020 deliberately defines a smaller grammar than gitignore or shell globs:

* paths and patterns are repository-relative and use forward slashes;
* a single star matches characters within one path segment;
* a complete double-star segment matches zero or more path segments;
* matching is case-sensitive on every operating system.

Keeping the matcher here, independent of rule types, lets schema validation,
the pre-flight enforcer, and post-generation conflict detection share exactly
the same applicability semantics.
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Iterable


class SelectorOutcome(str, Enum):
    """Result of evaluating one rule's artifact applicability."""

    APPLIED = "APPLIED"
    EXCLUDED = "EXCLUDED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PathSelection:
    """Path-only applicability result before rule metadata is added."""

    outcome: SelectorOutcome
    input_path: str | None
    selector: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class RuleEvaluation:
    """Auditable applicability trace for one typed rule."""

    decision_id: str
    rule_type: str
    rule_value: str
    rule_index: int
    path_scoped: bool
    outcome: SelectorOutcome
    input_path: str | None
    selector: str | None = None
    reason: str = ""


_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:/")


def validate_path_pattern(pattern: object) -> str:
    """Validate and return one ADR-020 selector unchanged."""
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("path selector must be a non-empty string")
    if "\\" in pattern:
        raise ValueError(
            f"path selector {pattern!r} must use forward slashes"
        )
    if pattern.startswith("/") or _WINDOWS_ABSOLUTE.match(pattern):
        raise ValueError(f"path selector {pattern!r} must be repository-relative")
    if pattern.startswith("!"):
        raise ValueError(f"path selector {pattern!r} cannot use negation")
    if any(token in pattern for token in ("?", "[", "]")):
        raise ValueError(
            f"path selector {pattern!r} uses unsupported glob syntax"
        )

    segments = pattern.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        raise ValueError(
            f"path selector {pattern!r} contains an empty or dot segment"
        )
    if any("**" in segment and segment != "**" for segment in segments):
        raise ValueError(
            f"path selector {pattern!r} may use ** only as a complete segment"
        )
    return pattern


def path_matches(pattern: str, relative_path: str) -> bool:
    """Return whether a normalized relative path matches pattern."""
    validate_path_pattern(pattern)
    if (
        not isinstance(relative_path, str)
        or not relative_path
        or "\\" in relative_path
        or relative_path.startswith("/")
        or _WINDOWS_ABSOLUTE.match(relative_path)
    ):
        raise ValueError(
            f"relative path {relative_path!r} is not normalized"
        )
    path_segments = relative_path.split("/")
    if any(segment in ("", ".", "..") for segment in path_segments):
        raise ValueError(
            f"relative path {relative_path!r} contains an empty or dot segment"
        )
    pattern_segments = pattern.split("/")

    @lru_cache(maxsize=None)
    def matches(pattern_index: int, path_index: int) -> bool:
        if pattern_index == len(pattern_segments):
            return path_index == len(path_segments)

        segment = pattern_segments[pattern_index]
        if segment == "**":
            return (
                matches(pattern_index + 1, path_index)
                or (
                    path_index < len(path_segments)
                    and matches(pattern_index, path_index + 1)
                )
            )

        return (
            path_index < len(path_segments)
            and fnmatch.fnmatchcase(path_segments[path_index], segment)
            and matches(pattern_index + 1, path_index + 1)
        )

    return matches(0, 0)


def policy_root(memory_path: str | Path) -> Path:
    """Derive the policy root defined by ADR-020."""
    memory = Path(memory_path).resolve()
    if memory.name == "project_memory.json" and memory.parent.name == ".mneme":
        return memory.parent.parent
    return memory.parent


def normalize_input_path(
    input_path: str | Path,
    memory_path: str | Path,
) -> str:
    """Return the case-preserving, policy-root-relative input path."""
    try:
        resolved_input = Path(input_path).resolve()
        root = policy_root(memory_path)
        relative = resolved_input.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(
            f"input path {str(input_path)!r} is outside or cannot be "
            f"resolved against policy root"
        ) from exc

    normalized = relative.as_posix()
    if normalized in ("", "."):
        raise ValueError("input path resolves to the policy root, not an artifact")
    return normalized


def _same_resolved_path(
    input_path: str | Path | None,
    policy_paths: Iterable[str | Path],
) -> bool:
    if input_path is None:
        return False
    try:
        resolved_input = Path(input_path).resolve()
    except (OSError, RuntimeError):
        return False
    for candidate in policy_paths:
        if not candidate:
            continue
        try:
            if resolved_input == Path(candidate).resolve():
                return True
        except (OSError, RuntimeError):
            continue
    return False


def evaluate_path_selectors(
    *,
    include_paths: tuple[str, ...] | None,
    exclude_paths: tuple[str, ...],
    input_path: str | Path | None,
    memory_path: str | Path | None,
    policy_paths: Iterable[str | Path] = (),
) -> PathSelection:
    """Evaluate canonical exemptions and optional path selectors."""
    if _same_resolved_path(input_path, policy_paths):
        normalized: str | None = None
        if input_path is not None and memory_path:
            try:
                normalized = normalize_input_path(input_path, memory_path)
            except ValueError:
                pass
        return PathSelection(
            outcome=SelectorOutcome.EXCLUDED,
            input_path=normalized,
            selector="<canonical-policy-source>",
            reason="the input is this rule's declaring ADR or policy memory",
        )

    # Existing unscoped rules remain global and never depend on path metadata.
    if include_paths is None:
        normalized = None
        if input_path is not None and memory_path:
            try:
                normalized = normalize_input_path(input_path, memory_path)
            except ValueError:
                pass
        return PathSelection(
            outcome=SelectorOutcome.APPLIED,
            input_path=normalized,
            reason="the rule has global applicability",
        )

    if input_path is None:
        return PathSelection(
            outcome=SelectorOutcome.UNKNOWN,
            input_path=None,
            reason="a scoped rule requires an input path",
        )
    if not memory_path:
        return PathSelection(
            outcome=SelectorOutcome.UNKNOWN,
            input_path=None,
            reason="a scoped rule requires its policy memory path",
        )

    try:
        normalized = normalize_input_path(input_path, memory_path)
    except ValueError as exc:
        return PathSelection(
            outcome=SelectorOutcome.UNKNOWN,
            input_path=None,
            reason=str(exc),
        )

    for selector in exclude_paths:
        if path_matches(selector, normalized):
            return PathSelection(
                outcome=SelectorOutcome.EXCLUDED,
                input_path=normalized,
                selector=selector,
                reason="an exclude selector matched",
            )

    for selector in include_paths:
        if path_matches(selector, normalized):
            return PathSelection(
                outcome=SelectorOutcome.APPLIED,
                input_path=normalized,
                selector=selector,
                reason="an include selector matched",
            )

    return PathSelection(
        outcome=SelectorOutcome.EXCLUDED,
        input_path=normalized,
        reason="no include selector matched",
    )


__all__ = [
    "PathSelection",
    "RuleEvaluation",
    "SelectorOutcome",
    "evaluate_path_selectors",
    "normalize_input_path",
    "path_matches",
    "policy_root",
    "validate_path_pattern",
]

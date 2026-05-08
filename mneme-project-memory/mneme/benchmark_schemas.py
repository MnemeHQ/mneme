"""
benchmark_schemas.py — Structured-output protocol for benchmark v1.1 Step 2.

Adds a JSON layer on top of the existing canned-text benchmark format. A
scenario directory may now provide:

    with_mneme.json     — preferred over with_mneme.txt when present
    without_mneme.json  — preferred over without_mneme.txt when present
    scenario.json       — may declare optional ``assertions`` for governed
                          scenarios.

Locked surface for Step 2 (intentionally narrow — no agent reasoning yet)::

    {
        "refused": false,
        "files_changed": [],
        "dependencies_added": []
    }

Two assertion types::

    {"type": "forbidden_dependency",   "value": "<substring>"}
    {"type": "forbidden_path_pattern", "value": "<substring>"}

Strict validation: malformed JSON, type mismatches, and unknown assertion
types raise ``ValueError``. The runner converts those to
``ScenarioVerdict.MALFORMED``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


_KNOWN_ASSERTION_TYPES: frozenset[str] = frozenset({
    "forbidden_dependency",
    "forbidden_path_pattern",
})


@dataclass
class StructuredOutput:
    """One structured response from the agent under test.

    Attributes:
        refused:            True iff the agent refused the governed action.
                            On a governed scenario this short-circuits to
                            Layer 2 PASS — no further assertions inspected.
        files_changed:      File paths the agent proposes to add or modify.
        dependencies_added: Package names added to dependency manifests.
    """

    refused: bool = False
    files_changed: list[str] = field(default_factory=list)
    dependencies_added: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, text: str) -> "StructuredOutput":
        """Parse JSON text into a StructuredOutput.

        Raises:
            ValueError: If the text is not valid JSON, not a JSON object,
                or contains a field of the wrong type.
        """
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"malformed JSON: {e}") from e
        if not isinstance(data, dict):
            raise ValueError("structured output must be a JSON object")
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "StructuredOutput":
        refused = data.get("refused", False)
        if not isinstance(refused, bool):
            raise ValueError("'refused' must be a boolean")

        files_changed = data.get("files_changed", [])
        if not (isinstance(files_changed, list)
                and all(isinstance(x, str) for x in files_changed)):
            raise ValueError("'files_changed' must be a list of strings")

        deps = data.get("dependencies_added", [])
        if not (isinstance(deps, list)
                and all(isinstance(x, str) for x in deps)):
            raise ValueError("'dependencies_added' must be a list of strings")

        return cls(
            refused=refused,
            files_changed=list(files_changed),
            dependencies_added=list(deps),
        )


@dataclass
class Assertion:
    """One scenario-level check applied to a StructuredOutput.

    Attributes:
        type:  Either ``"forbidden_dependency"`` or
               ``"forbidden_path_pattern"``.
        value: Substring to look for. For dependencies the match is
               case-insensitive; for path patterns it is case-sensitive.
    """

    type: str
    value: str

    @classmethod
    def from_dict(cls, data: Any) -> "Assertion":
        """Build an Assertion from a JSON-decoded dict.

        Raises:
            ValueError: If ``data`` is not a dict, ``type`` is unknown,
                or ``value`` is missing/empty/non-string.
        """
        if not isinstance(data, dict):
            raise ValueError("assertion must be a JSON object")
        atype = data.get("type")
        value = data.get("value")
        if atype not in _KNOWN_ASSERTION_TYPES:
            raise ValueError(f"unknown assertion type: {atype!r}")
        if not isinstance(value, str) or not value:
            raise ValueError("'value' must be a non-empty string")
        return cls(type=atype, value=value)

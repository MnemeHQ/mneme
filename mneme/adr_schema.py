"""
adr_schema.py — Dataclass and enums for Architectural Decision Records.

ADRs are the source-of-truth input to the architectural compiler. Each ADR
file has YAML frontmatter (the metadata block) and a markdown body. The
compiler parses, validates, and resolves precedence over a corpus of ADRs
to produce a deterministic active constraint set.

Status meanings
---------------
proposed     Drafted but not yet adopted. Excluded from the active set.
accepted     Adopted and currently in force. Included in the active set
             unless superseded.
deprecated   Adopted in the past but no longer in force. Excluded.
superseded   Replaced by a newer ADR via the ``supersedes`` field. Excluded.

Priority meanings
-----------------
foundational  Architectural invariants that should never be overridden by
              normal-priority decisions.
normal        Default priority for most decisions.
exception     Narrow carve-outs that yield to foundational rules in a tie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ADRStatus = Literal["proposed", "accepted", "deprecated", "superseded"]
ADRPriority = Literal["foundational", "normal", "exception"]

VALID_STATUSES: tuple[str, ...] = ("proposed", "accepted", "deprecated", "superseded")
VALID_PRIORITIES: tuple[str, ...] = ("foundational", "normal", "exception")

PRIORITY_RANK: dict[str, int] = {
    "foundational": 2,
    "normal": 1,
    "exception": 0,
}


@dataclass
class ADR:
    """A parsed Architectural Decision Record.

    Attributes:
        id:           Stable identifier, e.g. "ADR-001". Must match
                      ``ADR-\\d+``.
        title:        One-line human-readable label.
        status:       Lifecycle state — see module docstring.
        priority:     Precedence tier — see module docstring.
        date:         ISO 8601 date (YYYY-MM-DD) when the decision was
                      adopted (or last revised).
        scope:        Dotted-path scope string. Empty string means global.
                      Example: "storage" or "storage.embeddings".
        supersedes:   Ids of ADRs this record replaces.
        body:         Raw markdown body that follows the frontmatter.
        source_path:  Absolute path to the source file (for diagnostics).
    """

    id: str
    title: str
    status: ADRStatus
    priority: ADRPriority
    date: str
    scope: str
    supersedes: list[str] = field(default_factory=list)
    body: str = ""
    source_path: str = ""


# ── Errors ────────────────────────────────────────────────────────────────────


class ADRParseError(Exception):
    """Raised when an ADR file cannot be parsed (missing or malformed YAML)."""


class ADRValidationError(Exception):
    """Raised when the corpus fails schema validation.

    Attributes:
        errors: Human-readable error strings, one per detected problem.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__(
            f"ADR validation failed with {len(self.errors)} error(s): "
            + "; ".join(self.errors)
        )


class ADRPrecedenceError(Exception):
    """Raised when precedence resolution cannot deterministically pick a winner.

    Attributes:
        scope: The scope at which the ambiguity occurred.
        ids:   Candidate ADR ids that tied on every precedence rule.
    """

    def __init__(self, scope: str, ids: list[str]) -> None:
        self.scope = scope
        self.ids = list(ids)
        super().__init__(
            f"Ambiguous precedence at scope {scope!r} between: "
            + ", ".join(sorted(self.ids))
        )

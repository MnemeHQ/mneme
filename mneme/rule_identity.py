"""
rule_identity.py — the single ADR-030 §7 canonical rule identity.

    rule_id = <decision_id>:<RULE_TYPE>:<SHA-256(canonical_json([value, applicability]))[:32]>

Identity depends only on the owning decision, the rule type, the literal
value and the ADR-020 applicability selectors, never on rule order. ADR-031
§10 requires this to be the only ``rule_id`` algorithm in Mneme: persisted
bindings, the D0 adapter (Decision MCP ``--adr-dir``), and the enforcement
trace all use it. This module has no Mneme dependencies beyond the runtime
``Rule`` type so every layer can import it.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from mneme.schemas import Rule


def canonical_json(value: Any) -> str:
    """Canonical JSON used by ADR-030 identity digests."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def sha256_hex(value: Any) -> str:
    """SHA-256 hex digest of ``canonical_json(value)``."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def rule_applicability(
    include_paths: tuple[str, ...] | list[str] | None,
    exclude_paths: tuple[str, ...] | list[str],
) -> dict[str, Any]:
    """Canonical ADR-020 applicability mapping; empty means global."""
    applicability: dict[str, Any] = {}
    if include_paths is not None:
        applicability["include_paths"] = list(include_paths)
    if exclude_paths:
        applicability["exclude_paths"] = list(exclude_paths)
    return applicability


def rule_id_of(
    decision_id: str,
    rule_type: str,
    value: str,
    applicability: dict[str, Any],
) -> str:
    """ADR-030 §7 stable rule identity, independent of rule order."""
    digest = sha256_hex([value, applicability])
    return f"{decision_id}:{rule_type}:{digest[:32]}"


def rule_id_for(decision_id: str, rule: Rule) -> str:
    """ADR-030 §7 ``rule_id`` of one runtime ``Rule``."""
    return rule_id_of(
        decision_id,
        rule.type,
        rule.value,
        rule_applicability(rule.include_paths, rule.exclude_paths),
    )


__all__ = [
    "canonical_json",
    "rule_applicability",
    "rule_id_for",
    "rule_id_of",
    "sha256_hex",
]

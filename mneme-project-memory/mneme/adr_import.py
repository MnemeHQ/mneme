# mneme/adr_import.py
"""
adr_import.py — Import flow for ADR corpora.

Composition module that wires together the existing parser, validator, and
precedence resolver, then adds (a) a graph projection, (b) conflict
detection against a target memory file, (c) preview formatting, and
(d) atomic persistence. Each helper is independent and pure; the CLI
subcommand orchestrates them.

Pipeline modules (MemoryStore, DecisionRetriever, ContextBuilder,
LLMAdapter, Evaluator) are NOT imported here per .mneme/project_memory.json
rule-pipeline-modules. Persistence happens by writing the JSON file
directly; consumers re-load it via MemoryStore.
"""
from __future__ import annotations

import json as _json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from mneme.adr_schema import ADR, ADRPrecedenceError, ADRValidationError
from mneme.adr_compiler import (
    adrs_to_decisions,
    resolve_precedence,
    validate_corpus,
)
from mneme.adr_parser import parse_adr_directory
from mneme.schemas import Decision


GraphStatus = Literal["active", "superseded", "deprecated", "inactive"]


@dataclass(frozen=True)
class DecisionNode:
    """User-facing minimal graph projection of one ADR."""

    id: str
    status: GraphStatus
    supersedes: list[str] = field(default_factory=list)
    superseded_by: str | None = None


def project_decision_graph(adrs: list[ADR]) -> list[DecisionNode]:
    """Project a parsed ADR corpus into the minimal graph.

    Status mapping:
      ADR.status == "accepted" AND not in any other ADR's supersedes -> "active"
      ADR.status == "accepted" AND IS in some other ADR's supersedes -> "superseded"
      ADR.status == "superseded" (explicit in frontmatter)            -> "superseded"
      ADR.status == "deprecated"                                       -> "deprecated"
      ADR.status == "proposed"                                         -> "inactive"

    ``superseded_by`` is the id of the ADR that explicitly supersedes
    this one, or None. If multiple ADRs claim to supersede the same
    target, the lexicographically lowest id wins (deterministic; rare
    in practice and validate_corpus catches the cycle case).
    """
    superseded_by_map: dict[str, str] = {}
    for a in adrs:
        for ref in a.supersedes:
            existing = superseded_by_map.get(ref)
            if existing is None or a.id < existing:
                superseded_by_map[ref] = a.id

    out: list[DecisionNode] = []
    for a in adrs:
        if a.status == "deprecated":
            status: GraphStatus = "deprecated"
        elif a.status == "superseded":
            status = "superseded"
        elif a.status == "proposed":
            status = "inactive"
        elif a.status == "accepted":
            status = "superseded" if a.id in superseded_by_map else "active"
        else:
            status = "inactive"

        out.append(DecisionNode(
            id=a.id,
            status=status,
            supersedes=list(a.supersedes),
            superseded_by=superseded_by_map.get(a.id),
        ))
    return out


DiagnosticKind = Literal[
    "active_active_contradiction",  # same-scope tie the compiler couldn't break
    "same_id",                      # incoming id collides with existing memory id
    "validation_error",             # malformed ADR — shown but doesn't raise
]


@dataclass(frozen=True)
class ImportDiagnostic:
    """One diagnostic produced during ADR import."""

    kind: DiagnosticKind
    adr_id: str
    existing_in: str
    message: str


@dataclass(frozen=True)
class ImportReport:
    """Output of `compile_for_import`."""

    active_nodes: list[DecisionNode]
    all_nodes: list[DecisionNode]
    decisions: list[Decision]
    diagnostics: list[ImportDiagnostic]


def compile_for_import(adr_dir: str | Path) -> ImportReport:
    """Run parse -> validate -> precedence over a directory and produce an ImportReport.

    Unlike ``adr_compiler.compile_adrs``, this function does NOT raise on
    precedence ambiguity — the import flow surfaces it as a diagnostic so
    the user can review and re-run with ``--approve-conflicts``. Schema
    validation errors still raise (a malformed corpus is not importable
    in any mode).
    """
    adrs = parse_adr_directory(adr_dir)
    validate_corpus(adrs)  # still raises; the corpus must be schema-valid

    all_nodes = project_decision_graph(adrs)

    diagnostics: list[ImportDiagnostic] = []
    try:
        active_adrs = resolve_precedence(adrs)
    except ADRPrecedenceError as exc:
        diagnostics.append(ImportDiagnostic(
            kind="active_active_contradiction",
            adr_id=",".join(sorted(exc.ids)),
            existing_in="",
            message=(
                f"Active-active contradiction at scope {exc.scope!r} "
                f"between: {', '.join(sorted(exc.ids))}. Resolve by editing "
                f"the ADRs (mark one superseded, change priority, or change "
                f"date) or pass --approve-conflicts to import the rest of "
                f"the corpus and skip this scope."
            ),
        ))
        active_adrs = []

    active_ids = {a.id for a in active_adrs}
    active_nodes = [n for n in all_nodes if n.id in active_ids]
    decisions = adrs_to_decisions(active_adrs)

    return ImportReport(
        active_nodes=active_nodes,
        all_nodes=all_nodes,
        decisions=decisions,
        diagnostics=diagnostics,
    )


def detect_collisions(
    incoming: list[DecisionNode],
    target_memory: dict[str, Any],
) -> list[ImportDiagnostic]:
    """Return diagnostics for incoming ids that already exist in the target memory.

    MVP: same-id collisions only.
    """
    existing_in_decisions = {
        d.get("id"): "decisions" for d in target_memory.get("decisions", [])
    }
    existing_in_items = {
        i.get("id"): "items" for i in target_memory.get("items", [])
    }

    out: list[ImportDiagnostic] = []
    for node in incoming:
        if node.id in existing_in_decisions:
            out.append(ImportDiagnostic(
                kind="same_id",
                adr_id=node.id,
                existing_in="decisions",
                message=(
                    f"{node.id} already exists in target memory under "
                    f"decisions[]. Pass --update-existing to overwrite, "
                    f"or rename the incoming ADR."
                ),
            ))
        elif node.id in existing_in_items:
            out.append(ImportDiagnostic(
                kind="same_id",
                adr_id=node.id,
                existing_in="items",
                message=(
                    f"{node.id} already exists in target memory under "
                    f"items[] (legacy rule/anti_pattern slot). Imported "
                    f"ADRs land in decisions[]; renaming the incoming "
                    f"ADR is the safest path. --update-existing will "
                    f"refuse to migrate across sections."
                ),
            ))
    return out


def format_preview(
    report: ImportReport,
    collisions: list[ImportDiagnostic],
) -> str:
    """Render an ImportReport + collision list as a deterministic preview.

    Plain text, no colors, no unicode glyphs (CI- and Windows-console-safe).
    Sections appear in a fixed order so output is diffable across runs.
    """
    lines: list[str] = []
    lines.append("ADR import preview")
    lines.append("=" * 60)
    lines.append("")

    # Section: active set
    lines.append(f"Active set ({len(report.active_nodes)} ADRs):")
    if not report.active_nodes:
        lines.append("  (none -- see diagnostics below)")
    for node in report.active_nodes:
        lines.append(f"  [{node.id}] status={node.status}")
        decision = next((d for d in report.decisions if d.id == node.id), None)
        if decision:
            for c in decision.constraints:
                lines.append(f"      constraint: {c}")
            if not decision.constraints:
                lines.append("      (no ## Constraints directives)")
    lines.append("")

    # Section: full corpus (graph view)
    inactive = [n for n in report.all_nodes if n.status != "active"]
    if inactive:
        lines.append(f"Non-active ADRs ({len(inactive)}):")
        for node in inactive:
            extra = (
                f" (superseded_by {node.superseded_by})"
                if node.superseded_by else ""
            )
            lines.append(f"  [{node.id}] status={node.status}{extra}")
        lines.append("")

    # Section: precedence diagnostics
    precedence_diags = [
        d for d in report.diagnostics
        if d.kind == "active_active_contradiction"
    ]
    if precedence_diags:
        lines.append("Active-active contradiction diagnostics:")
        for d in precedence_diags:
            lines.append(f"  - {d.message}")
        lines.append("")
        lines.append(
            "  To proceed despite the contradiction, re-run with "
            "--approve-conflicts."
        )
        lines.append("")

    # Section: collisions vs existing memory
    if collisions:
        lines.append("Conflicts vs existing memory:")
        for c in collisions:
            lines.append(f"  - {c.message}")
        lines.append("")
        lines.append(
            "  To overwrite existing decisions[] entries, re-run with "
            "--update-existing."
        )
        lines.append("")

    return "\n".join(lines)


__all__ = [
    "DecisionNode",
    "GraphStatus",
    "ImportDiagnostic",
    "ImportReport",
    "DiagnosticKind",
    "project_decision_graph",
    "compile_for_import",
    "detect_collisions",
    "format_preview",
]

"""
mneme/integrations/eventcatalog/importer.py — EventCatalog index ingestion.

Reads a pre-generated EventCatalog index JSON (produced by EventCatalog's
SDK `buildIndex()`) and the catalog's ADR markdown files, producing Mneme
`Decision` objects for retrieval-only import.

This module has NO dependency on Node.js or the EventCatalog SDK at runtime.
The EventCatalog index is generated externally (via `npm run build` or
`npx eventcatalog build-index`) and consumed as a stable JSON artifact.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from mneme.schemas import Decision, Rule


# ── Types ─────────────────────────────────────────────────────────────────────

EventCatalogNodeStatus = Literal["active", "superseded", "inactive"]

EventCatalogResourceType = Literal["adr", "domain", "service", "event", "command", "query", "flow", "system", "agent", "container", "data-product"]


@dataclass(frozen=True)
class EventCatalogNode:
    """User-facing graph projection of one EventCatalog resource."""

    type: EventCatalogResourceType
    id: str
    version: str | None
    name: str
    status: EventCatalogNodeStatus
    supersedes: list[str] = field(default_factory=list)
    superseded_by: str | None = None
    applies_to: list[dict[str, str]] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)
    content_path: str = ""
    content_hash: str = ""


@dataclass(frozen=True)
class ImportDiagnostic:
    """One diagnostic produced during EventCatalog import."""

    kind: Literal[
        "retrieval_only",
        "no_adr_mdx",
        "malformed_index",
        "same_id",
    ]
    node_id: str
    existing_in: str
    message: str


@dataclass(frozen=True)
class EventCatalogImportReport:
    """Output of `compile_for_import` for EventCatalog."""

    nodes: list[EventCatalogNode]
    decisions: list[Decision]
    diagnostics: list[ImportDiagnostic]


# ── Helpers ───────────────────────────────────────────────────────────────────

_APPLIES_TO_KEYS = frozenset({"domain", "service", "event", "command", "query", "flow", "system", "agent", "container", "data-product"})


def _flatten_applies_to(applies_to: list[dict[str, str]]) -> list[str]:
    """Flatten appliesTo into scope strings like ['orders domain', 'payment-service', 'payment-accepted']."""
    scope: list[str] = []
    for entry in applies_to:
        if not isinstance(entry, dict) or len(entry) != 1:
            continue
        for key, value in entry.items():
            if key in _APPLIES_TO_KEYS:
                scope.append(f"{value} {key}" if key == "domain" else value)
    return scope


def _extract_section(markdown: str, header: str) -> str:
    """Extract the section content after a markdown header (## Header)."""
    pattern = rf"^##\s+{re.escape(header)}\s*\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, markdown, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def _parse_adr_markdown(path: Path) -> tuple[str, str]:
    """Read ADR markdown and return (decision_text, rationale_text).

    decision_text = '## Decision' section
    rationale_text = '## Context' + '## Consequences' sections combined
    """
    content = path.read_text(encoding="utf-8")
    decision_text = _extract_section(content, "Decision")
    context_text = _extract_section(content, "Context")
    consequences_text = _extract_section(content, "Consequences")
    rationale_parts = [p for p in [context_text, consequences_text] if p]
    rationale_text = "\n\n".join(rationale_parts)
    return decision_text, rationale_text


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compute_ec_node_status(node: dict[str, Any], all_nodes: list[dict[str, Any]]) -> EventCatalogNodeStatus:
    """Compute active/superseded/inactive status from index data."""
    node_type = node.get("type")
    if node_type != "adr":
        return "inactive"

    status = node.get("status", "proposed")
    superseded_by = node.get("supersededBy")

    if status == "accepted":
        if superseded_by:
            return "superseded"
        return "active"
    elif status == "superseded":
        return "superseded"
    else:
        return "inactive"


def _build_superseded_by_map(nodes: list[dict[str, Any]]) -> dict[str, str]:
    """Build mapping from superseded ADR id -> superseding ADR id."""
    superseded_by: dict[str, str] = {}
    for node in nodes:
        if node.get("type") == "adr" and node.get("status") == "accepted":
            for ref in node.get("supersedes", []):
                if ref not in superseded_by:
                    superseded_by[ref] = node["id"]
    return superseded_by


# ── Core compilation ──────────────────────────────────────────────────────────

def compile_for_import(
    index_path: str | Path,
    catalog_root: str | Path,
) -> EventCatalogImportReport:
    """Parse EventCatalog index and produce an import report.

    Args:
        index_path: Path to EventCatalog index JSON (output of `buildIndex()`).
        catalog_root: Root directory of the EventCatalog project (contains adrs/, domains/, etc.).

    Returns:
        EventCatalogImportReport with nodes, decisions, and diagnostics.
    """
    index_path = Path(index_path)
    catalog_root = Path(catalog_root)

    if not index_path.exists():
        raise FileNotFoundError(f"EventCatalog index not found: {index_path}")
    if not catalog_root.exists():
        raise FileNotFoundError(f"EventCatalog catalog root not found: {catalog_root}")

    index_data = json.loads(index_path.read_text(encoding="utf-8"))
    resources = index_data.get("resources", [])

    if not isinstance(resources, list):
        raise ValueError("EventCatalog index 'resources' must be a list")

    superseded_by_map = _build_superseded_by_map(resources)

    nodes: list[EventCatalogNode] = []
    decisions: list[Decision] = []
    diagnostics: list[ImportDiagnostic] = []

    for r in resources:
        if r.get("type") != "adr":
            continue

        node_id = r.get("id", "")
        if not node_id:
            continue

        status = _compute_ec_node_status(r, resources)
        superseded_by = superseded_by_map.get(node_id) or r.get("supersededBy")

        # Only import active ADRs (accepted and not superseded)
        if status != "active":
            nodes.append(EventCatalogNode(
                type="adr",
                id=node_id,
                version=r.get("version"),
                name=r.get("name", node_id),
                status=status,
                supersedes=r.get("supersedes", []),
                superseded_by=superseded_by,
                applies_to=r.get("appliesTo", []),
                owners=r.get("owners", []),
                content_path=r.get("contentPath", ""),
                content_hash=r.get("contentHash", ""),
            ))
            continue

        # Read ADR markdown for decision/rationale
        content_path = r.get("contentPath", "")
        if not content_path:
            diagnostics.append(ImportDiagnostic(
                kind="no_adr_mdx",
                node_id=node_id,
                existing_in="",
                message=f"ADR {node_id} has no contentPath in index",
            ))
            continue

        adr_mdx_path = catalog_root / content_path
        if not adr_mdx_path.exists():
            diagnostics.append(ImportDiagnostic(
                kind="no_adr_mdx",
                node_id=node_id,
                existing_in="",
                message=f"ADR markdown not found at {adr_mdx_path}",
            ))
            continue

        decision_text, rationale_text = _parse_adr_markdown(adr_mdx_path)

        if not decision_text:
            diagnostics.append(ImportDiagnostic(
                kind="malformed_index",
                node_id=node_id,
                existing_in="",
                message=f"ADR {node_id} has no '## Decision' section",
            ))

        scope = _flatten_applies_to(r.get("appliesTo", []))

        decision = Decision(
            id=f"ec-{node_id}",
            decision=decision_text or r.get("name", node_id),
            rationale=rationale_text,
            scope=scope,
            constraints=[],
            anti_patterns=[],
            rules=[],
            created_at=r.get("date", ""),
            updated_at=r.get("date", ""),
            source_path=content_path,
            memory_path="",
        )
        decisions.append(decision)

        # Always retrieval-only for EventCatalog ADRs
        diagnostics.append(ImportDiagnostic(
            kind="retrieval_only",
            node_id=node_id,
            existing_in="",
            message=(
                f"ec-{node_id} imported from EventCatalog: retrieval-only "
                f"(constraints=[], anti_patterns=[], rules=[]). "
                f"Add Mneme-native ADRs for enforceable rules."
            ),
        ))

        nodes.append(EventCatalogNode(
            type="adr",
            id=node_id,
            version=r.get("version"),
            name=r.get("name", node_id),
            status=status,
            supersedes=r.get("supersedes", []),
            superseded_by=superseded_by,
            applies_to=r.get("appliesTo", []),
            owners=r.get("owners", []),
            content_path=content_path,
            content_hash=r.get("contentHash", ""),
        ))

    return EventCatalogImportReport(
        nodes=nodes,
        decisions=decisions,
        diagnostics=diagnostics,
    )


# ── Collision detection ───────────────────────────────────────────────────────

def detect_collisions(
    incoming: list[EventCatalogNode],
    target_memory: dict[str, Any],
) -> list[ImportDiagnostic]:
    """Return diagnostics for incoming decision ids that already exist in target memory."""
    existing_in_decisions = {
        d.get("id"): "decisions" for d in target_memory.get("decisions", [])
    }
    existing_in_items = {
        i.get("id"): "items" for i in target_memory.get("items", [])
    }

    out: list[ImportDiagnostic] = []
    for node in incoming:
        decision_id = f"ec-{node.id}"
        if decision_id in existing_in_decisions:
            out.append(ImportDiagnostic(
                kind="same_id",
                node_id=decision_id,
                existing_in="decisions",
                message=(
                    f"{decision_id} already exists in target memory under "
                    f"decisions[]. Pass --update-existing to overwrite, "
                    f"or rename the incoming EventCatalog ADR."
                ),
            ))
        elif decision_id in existing_in_items:
            out.append(ImportDiagnostic(
                kind="same_id",
                node_id=decision_id,
                existing_in="items",
                message=(
                    f"{decision_id} already exists in target memory under "
                    f"items[] (legacy rule/anti_pattern slot). Imported "
                    f"EventCatalog ADRs land in decisions[]; renaming the "
                    f"incoming ADR is the safest path. --update-existing will "
                    f"refuse to migrate across sections."
                ),
            ))
    return out


# ── Preview formatting ────────────────────────────────────────────────────────

def format_preview(
    report: EventCatalogImportReport,
    collisions: list[ImportDiagnostic],
) -> str:
    """Render an import report as a deterministic preview."""
    lines: list[str] = []
    lines.append("EventCatalog import preview")
    lines.append("=" * 60)
    lines.append("")

    # Active set
    active_nodes = [n for n in report.nodes if n.status == "active"]
    lines.append(f"Active set ({len(active_nodes)} ADRs):")
    if not active_nodes:
        lines.append("  (none -- see diagnostics below)")
    for node in active_nodes:
        lines.append(f"  [ec-{node.id}] status={node.status}")
        decision = next((d for d in report.decisions if d.id == f"ec-{node.id}"), None)
        if decision:
            lines.append(f"      scope: {', '.join(decision.scope) if decision.scope else '(empty)'}")
            if decision.constraints:
                for c in decision.constraints:
                    lines.append(f"      constraint: {c}")
            if decision.anti_patterns:
                for ap in decision.anti_patterns:
                    lines.append(f"      anti_pattern: {ap}")
            if decision.rules:
                for rule in decision.rules:
                    lines.append(f"      rule: {rule.type} {rule.value}")
            if not decision.constraints and not decision.anti_patterns and not decision.rules:
                lines.append("      (retrieval-only: no enforceable directives)")
    lines.append("")

    # Non-active
    inactive = [n for n in report.nodes if n.status != "active"]
    if inactive:
        lines.append(f"Non-active ADRs ({len(inactive)}):")
        for node in inactive:
            extra = f" (superseded_by {node.superseded_by})" if node.superseded_by else ""
            lines.append(f"  [ec-{node.id}] status={node.status}{extra}")
        lines.append("")

    # Retrieval-only warnings
    retrieval_diags = [d for d in report.diagnostics if d.kind == "retrieval_only"]
    if retrieval_diags:
        lines.append("Retrieval-only ADR warnings:")
        for d in retrieval_diags:
            lines.append(f"  - {d.message}")
        lines.append("")

    # Missing markdown warnings
    missing_diags = [d for d in report.diagnostics if d.kind == "no_adr_mdx"]
    if missing_diags:
        lines.append("Missing ADR markdown:")
        for d in missing_diags:
            lines.append(f"  - {d.message}")
        lines.append("")

    # Collisions
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


# ── Persistence ──────────────────────────────────────────────────────────────

def _serialize_rule(rule: Rule) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": rule.type,
        "value": rule.value,
    }
    if rule.include_paths is not None:
        payload["include_paths"] = list(rule.include_paths)
    if rule.exclude_paths:
        payload["exclude_paths"] = list(rule.exclude_paths)
    return payload


def apply_import(
    report: EventCatalogImportReport,
    target_path: str | Path,
    catalog_root: str | Path,
    allow_update: bool = False,
) -> list[str]:
    """Write imported Decisions into target project_memory.json.

    Same-id collisions: if `allow_update` is False and any incoming
    Decision id already exists in `decisions[]` of the target, raises
    RuntimeError. If True, the colliding entry is replaced in place.

    Atomic: writes to a sibling tempfile and os.replace()s into place.

    Returns the list of ids actually written, in input order.
    """
    import os
    import tempfile

    target_path = Path(target_path)
    catalog_root = Path(catalog_root)

    target_memory = json.loads(target_path.read_text(encoding="utf-8"))
    collisions = detect_collisions(report.nodes, target_memory)
    if collisions and not allow_update:
        raise RuntimeError(
            "EventCatalog import refused: same-id collision in target memory. "
            "Pass --update-existing to overwrite, or rename the incoming ADRs."
        )

    raw = target_memory
    raw.setdefault("decisions", [])
    existing_idx = {d.get("id"): i for i, d in enumerate(raw["decisions"])}

    written_ids: list[str] = []
    for decision in report.decisions:
        entry = {
            "id": decision.id,
            "decision": decision.decision,
            "rationale": decision.rationale,
            "scope": list(decision.scope),
            "constraints": list(decision.constraints),
            "anti_patterns": list(decision.anti_patterns),
            "rules": [_serialize_rule(rule) for rule in decision.rules],
            "created_at": decision.created_at,
            "updated_at": decision.updated_at,
        }
        if decision.source_path:
            source_full = catalog_root / decision.source_path
            entry["source"] = {
                "type": "eventcatalog",
                "path": decision.source_path,
                "sha256": _sha256(source_full),
            }
        if decision.id in existing_idx:
            if not allow_update:
                raise RuntimeError(
                    f"EventCatalog import refused: id {decision.id!r} already exists "
                    f"in target memory decisions[]. Pass --update-existing to "
                    f"overwrite, or rename the incoming ADR."
                )
            raw["decisions"][existing_idx[decision.id]] = entry
        else:
            raw["decisions"].append(entry)
        written_ids.append(decision.id)

    # Atomic write
    serialized = json.dumps(raw, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(
        prefix=target_path.name + ".", suffix=".tmp", dir=str(target_path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(serialized)
        os.replace(tmp, str(target_path))
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    return written_ids


__all__ = [
    "EventCatalogNode",
    "EventCatalogImportReport",
    "ImportDiagnostic",
    "compile_for_import",
    "detect_collisions",
    "format_preview",
    "apply_import",
]
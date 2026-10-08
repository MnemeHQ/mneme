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
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from mneme.adr_schema import ADR
from mneme.adr_compiler import (
    adrs_to_decisions,
    resolve_precedence_partial,
    validate_corpus,
)
from mneme.adr_parser import parse_adr_directory
from mneme.schemas import Decision, Rule

# Note: mneme.adr_freshness is imported lazily inside ``apply_import`` to
# avoid a module-init cycle (adr_freshness needs project_decision_graph
# from this module).


GraphStatus = Literal["active", "superseded", "deprecated", "inactive"]


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
      ADR.status == "accepted" AND not in any accepted ADR's supersedes -> "active"
      ADR.status == "accepted" AND IS in some accepted ADR's supersedes -> "superseded"
      ADR.status == "superseded" (explicit in frontmatter)            -> "superseded"
      ADR.status == "deprecated"                                       -> "deprecated"
      ADR.status == "proposed"                                         -> "inactive"

    ``superseded_by`` is the id of the accepted ADR that explicitly supersedes
    this one, or None. If multiple accepted ADRs claim to supersede the same
    target, the lexicographically lowest id wins (deterministic; rare
    in practice and validate_corpus catches the cycle case).
    """
    superseded_by_map: dict[str, str] = {}
    for a in adrs:
        if a.status == "accepted":
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
    "no_enforceable_rules",
    "active_active_contradiction",  # same-scope tie the compiler couldn't break
    "same_id",                      # incoming id collides with existing memory id
    "validation_error",             # malformed ADR — shown but doesn't raise
    "continuity_obligation",        # §9a binding the new source would drop
    "supersession_enforcement",     # §9a: enforcement leaving Layer 1
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
    """Output of `compile_for_import`.

    ``adr_sources_by_id`` carries active-source paths for preview and
    persistence compatibility; ``parsed_adrs`` retains the validated corpus
    used by D1D canonical writes. ``apply_import`` requires that validated
    corpus when decisions are written, so callers cannot fabricate new
    canonical ADR authority by constructing an ``ImportReport`` by hand.

    ``skipped_scopes`` maps each scope excluded by an unresolvable
    active-active tie to the sorted ids that tied there. No ADR from a
    skipped scope appears in ``active_nodes`` or ``decisions``.
    """

    active_nodes: list[DecisionNode]
    all_nodes: list[DecisionNode]
    decisions: list[Decision]
    diagnostics: list[ImportDiagnostic]
    adr_sources_by_id: dict[str, str] = field(default_factory=dict)
    skipped_scopes: dict[str, list[str]] = field(default_factory=dict)
    parsed_adrs: list[ADR] = field(default_factory=list)


def _has_mechanically_enforceable_rule(decision: Decision) -> bool:
    """Return whether the current runtime can enforce any payload."""
    if decision.rules or decision.anti_patterns:
        return True
    return any(
        re.match(r"^no\s+.+$", constraint.strip(), re.IGNORECASE)
        for constraint in decision.constraints
    )


def compile_for_import(adr_dir: str | Path) -> ImportReport:
    """Run parse -> validate -> precedence over a directory and produce an ImportReport.

    Unlike ``adr_compiler.compile_adrs``, this function does NOT raise on
    precedence ambiguity — the import flow surfaces each ambiguous scope as
    a diagnostic so the user can review and re-run with
    ``--approve-conflicts``. Precedence is resolved per scope: every ADR in
    an ambiguous scope is excluded from the active set, and every other
    scope still resolves normally. ``apply_import`` refuses to write the
    partial set unless conflicts are approved. Schema validation errors
    still raise (a malformed corpus is not importable in any mode).
    """
    adrs = parse_adr_directory(adr_dir)
    validate_corpus(adrs)  # still raises; the corpus must be schema-valid

    all_nodes = project_decision_graph(adrs)

    diagnostics: list[ImportDiagnostic] = []
    active_adrs, ambiguities = resolve_precedence_partial(adrs)
    skipped_scopes: dict[str, list[str]] = {}
    for exc in sorted(ambiguities, key=lambda e: e.scope):
        tied = sorted(exc.ids)
        skipped_scopes[exc.scope] = tied
        diagnostics.append(ImportDiagnostic(
            kind="active_active_contradiction",
            adr_id=",".join(tied),
            existing_in="",
            message=(
                f"Active-active contradiction at scope {exc.scope!r} "
                f"between: {', '.join(tied)}. Resolve by editing "
                f"the ADRs (mark one superseded or give one a higher "
                f"priority; ADR date never breaks a tie) or pass "
                f"--approve-conflicts to import the rest of "
                f"the corpus and skip this scope."
            ),
        ))

    active_ids = {a.id for a in active_adrs}
    active_nodes = [n for n in all_nodes if n.id in active_ids]
    decisions = adrs_to_decisions(active_adrs)
    for decision in decisions:
        if not _has_mechanically_enforceable_rule(decision):
            diagnostics.append(ImportDiagnostic(
                kind="no_enforceable_rules",
                adr_id=decision.id,
                existing_in="",
                message=(
                    f"{decision.id} yields 0 mechanically enforceable rules; "
                    f"it will be imported for retrieval only. Add an "
                    f"enforceable directive such as FORBID_LITERAL under "
                    f"## Constraints to make enforcement explicit."
                ),
            ))
    adr_sources_by_id = {a.id: a.source_path for a in active_adrs if a.source_path}

    return ImportReport(
        active_nodes=active_nodes,
        all_nodes=all_nodes,
        decisions=decisions,
        diagnostics=diagnostics,
        adr_sources_by_id=adr_sources_by_id,
        skipped_scopes=skipped_scopes,
        parsed_adrs=adrs,
    )


def detect_collisions(
    incoming: list[DecisionNode],
    target_memory: dict[str, Any],
) -> list[ImportDiagnostic]:
    """Return same-id diagnostics against canonical or legacy authority."""
    section = target_memory.get("decision_index")
    active_version_by_id: dict[str, str] = {}
    if isinstance(section, dict):
        existing_in_decisions = {
            row.get("decision_id"): "decision_index"
            for row in section.get("decisions", [])
            if isinstance(row, dict)
        }
        active_version_by_id = {
            row.get("decision_id"): row.get("active_version_id")
            for row in section.get("decisions", [])
            if isinstance(row, dict)
            and isinstance(row.get("active_version_id"), str)
        }
    else:
        existing_in_decisions = {
            row.get("id"): "decisions"
            for row in target_memory.get("decisions", [])
            if isinstance(row, dict)
        }
    existing_in_items = {
        row.get("id"): "items"
        for row in target_memory.get("items", [])
        if isinstance(row, dict)
    }

    out: list[ImportDiagnostic] = []
    for node in incoming:
        if node.id in existing_in_items:
            out.append(ImportDiagnostic(
                kind="same_id",
                adr_id=node.id,
                existing_in="items",
                message=(
                    f"{node.id} already exists in target memory under items[]. "
                    "ADR authority must not silently replace a legacy item identity."
                ),
            ))
        elif node.id in existing_in_decisions:
            message = (
                f"{node.id} already exists in canonical decision authority. "
                "Pass --update-existing to create or reuse an immutable "
                "version occurrence, or rename the incoming ADR."
            )
            current = active_version_by_id.get(node.id)
            if current:
                # The persisted active pointer as of this read. An operator
                # who later needs to retry this exact apply pins it with
                # --expected-predecessor; reading it creates no identity.
                message += f" current predecessor: {current}"
            out.append(ImportDiagnostic(
                kind="same_id",
                adr_id=node.id,
                existing_in=existing_in_decisions[node.id],
                message=message,
            ))
    return out

def detect_continuity_effects(
    report: ImportReport,
    target_memory: dict[str, Any],
) -> list[ImportDiagnostic]:
    """Preview ADR-030 §9a consequences against canonical target memory.

    - ``continuity_obligation``: an incoming same-id decision that would
      evolve, whose active version carries ``protection``/``legacy_unknown``
      bindings the new source no longer derives. Each must be preserved or
      released explicitly, or the apply refuses.
    - ``supersession_enforcement``: a decision an incoming ADR will
      supersede that carries such bindings. Supersession retires the
      decision, so no per-binding release is needed, but its enforcement
      leaves Layer 1 and the preview says so.

    Section-less or invalid memory yields no diagnostics; the apply path
    refuses it on its own terms.
    """
    from mneme.decision_index_persistence import (
        DecisionIndexPersistenceError,
        content_digest_of,
        continuity_bindings,
        load_persisted_decision_index,
        rule_id_for,
    )

    section = target_memory.get("decision_index")
    if not isinstance(section, dict):
        return []
    try:
        index = load_persisted_decision_index(section)
    except DecisionIndexPersistenceError:
        return []
    records = {record.decision_id: record for record in index.records}
    revisions = {adr.id: adr.source_sha256 for adr in report.parsed_adrs}

    def describe(rows: list[dict[str, Any]]) -> str:
        return ", ".join(
            f"{row['rule_id']} ({row.get('binding_authority', 'legacy_unknown')})"
            for row in rows
        )

    out: list[ImportDiagnostic] = []
    for decision in report.decisions:
        record = records.get(decision.id)
        if record is None:
            continue
        identity = (decision.id, revisions.get(decision.id, ""), "adr-import")
        if (
            record.content_digest == content_digest_of(
                decision.decision,
                decision.rationale,
                decision.scope,
                decision.constraints,
                decision.anti_patterns,
            )
            and record.occurrence_source_identity == identity
        ):
            continue
        derived = {rule_id_for(decision.id, rule) for rule in decision.rules}
        dropped = [
            row for row in continuity_bindings(section, record.version_id)
            if row["rule_id"] not in derived
        ]
        if dropped:
            out.append(ImportDiagnostic(
                kind="continuity_obligation",
                adr_id=decision.id,
                existing_in="decision_index",
                message=(
                    f"{decision.id} version evolution would drop "
                    f"protection/legacy_unknown bindings: {describe(dropped)}. "
                    "Pass --preserve-protection <rule_id> or "
                    "--release-protection <rule_id> for each."
                ),
            ))

    seen: set[str] = set()
    for node in report.active_nodes:
        for target in node.supersedes:
            record = records.get(target)
            if record is None or target in seen or record.lifecycle_status != "active":
                continue
            seen.add(target)
            leaving = continuity_bindings(section, record.version_id)
            if leaving:
                out.append(ImportDiagnostic(
                    kind="supersession_enforcement",
                    adr_id=target,
                    existing_in="decision_index",
                    message=(
                        f"{target} will become superseded by {node.id}; "
                        f"enforcement leaving Layer 1: {describe(leaving)}"
                    ),
                ))
    return out


def format_preview(
    report: ImportReport,
    collisions: list[ImportDiagnostic],
    continuity: list[ImportDiagnostic] | None = None,
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
            for rule in decision.rules:
                lines.append(f"      rule: {rule.type} {rule.value}")
                if rule.include_paths is not None:
                    lines.append(
                        f"        include_paths: {', '.join(rule.include_paths)}"
                    )
                if rule.exclude_paths:
                    lines.append(
                        f"        exclude_paths: {', '.join(rule.exclude_paths)}"
                    )
            for c in decision.constraints:
                lines.append(f"      constraint: {c}")
            if not decision.rules and not decision.constraints:
                lines.append("      (no supported ## Constraints directives)")
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
            "  To import the active set above and skip the conflicting "
            "scope(s), re-run with --approve-conflicts."
        )
        lines.append("")

    unenforceable_diags = [
        d for d in report.diagnostics
        if d.kind == "no_enforceable_rules"
    ]
    if unenforceable_diags:
        lines.append("Retrieval-only ADR warnings:")
        for d in unenforceable_diags:
            lines.append(f"  - {d.message}")
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

    obligations = [
        d for d in (continuity or []) if d.kind == "continuity_obligation"
    ]
    if obligations:
        lines.append("Protection continuity obligations (ADR-030 §9a):")
        for d in obligations:
            lines.append(f"  - {d.message}")
        lines.append("")
    supersession = [
        d for d in (continuity or []) if d.kind == "supersession_enforcement"
    ]
    if supersession:
        lines.append("Supersession enforcement effects:")
        for d in supersession:
            lines.append(f"  - {d.message}")
        lines.append("")

    return "\n".join(lines)


def apply_import(
    report: ImportReport,
    target_path: str | Path,
    allow_update: bool = False,
    approve_conflicts: bool = False,
    expected_predecessor_version_ids: dict[str, str] | None = None,
    preserve_protection: list[str] | tuple[str, ...] = (),
    release_protection: list[str] | tuple[str, ...] = (),
    preservation_validator: Callable[[Decision, Rule], None] | None = None,
) -> list[str]:
    """Apply ADR authority to the canonical Decision Index (D1D).

    ADR-030 §9a continuity: a ``protection``/``legacy_unknown`` binding the
    new ADR content no longer derives must be named in
    ``preserve_protection`` (carried after ``preservation_validator``
    revalidates the exact rule against the new version) or in
    ``release_protection`` (omitted); otherwise version evolution refuses.
    The validator is injected by the caller so this authority module does
    not depend on the protection/enforcement layer.
    """
    from mneme.adr_freshness import relative_source_path
    from mneme.decision_index_persistence import (
        DecisionIndexPersistenceError,
        apply_canonical_supersession,
        append_canonical_version_occurrence,
        append_initial_canonical_decision,
        content_digest_of,
        DecisionIndexMigrationRequired,
        load_persisted_decision_index,
        require_canonical_document,
        rebuild_compatibility_snapshot,
        verify_compatibility_snapshot,
    )

    target_path = Path(target_path)
    has_active_active = any(
        d.kind == "active_active_contradiction" for d in report.diagnostics
    )
    if has_active_active and not approve_conflicts:
        raise RuntimeError(
            "ADR import refused: active-active contradiction in corpus. "
            "Pass approve_conflicts=True (or --approve-conflicts on the CLI) "
            "to import the non-conflicting scopes and skip the conflicting "
            "ones, or fix the contradicting ADRs."
        )

    if report.decisions and not report.parsed_adrs:
        raise RuntimeError(
            "ADR import refused: canonical ADR authority requires an "
            "ImportReport produced by compile_for_import so source provenance "
            "and occurrence identity are validated."
        )

    # ADR import is a canonical authority writer (ADR-030 §1), not a legacy
    # decisions[] writer, so the legacy-writer containment guard does not
    # apply: it validates canonical state before any write, mutates only
    # decision_index, re-derives decisions[] from it, verifies snapshot
    # parity, and replaces the file atomically.
    try:
        raw = _json.loads(target_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise DecisionIndexPersistenceError("project memory must be an object")
        # ADR-030 §1: ADR import never migrates. Section-less memory raises
        # DecisionIndexMigrationRequired before any write.
        working = require_canonical_document(raw)
        initial_index = load_persisted_decision_index(raw["decision_index"])
        verify_compatibility_snapshot(raw, initial_index, target_path)
    except DecisionIndexMigrationRequired:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError(
            f"ADR import refused: target memory is not valid canonical state: {exc}"
        ) from exc

    initial_records_by_id = {
        record.decision_id: record for record in initial_index.records
    }
    initial_existing_ids = set(initial_records_by_id)
    # ADR-030 §5: an unpinned apply is a new authority operation whose
    # predecessor is the active version when it starts. A late retry of an
    # earlier operation must carry that operation's predecessor explicitly;
    # the pin is never re-derived from the current active pointer.
    pinned_predecessors = dict(expected_predecessor_version_ids or {})
    operation_predecessors = {
        decision_id: record.version_id
        for decision_id, record in initial_records_by_id.items()
    }
    if pinned_predecessors:
        if not allow_update:
            raise RuntimeError(
                "ADR import refused: an expected predecessor applies only to "
                "same-id version evolution; pass --update-existing."
            )
        incoming_ids = {decision.id for decision in report.decisions}
        persisted_versions = {
            row.get("version_id"): row.get("decision_id")
            for row in working["decision_index"].get("versions", [])
            if isinstance(row, dict)
        }
        for decision_id, version_id in sorted(pinned_predecessors.items()):
            if decision_id not in incoming_ids:
                raise RuntimeError(
                    f"ADR import refused: expected predecessor names "
                    f"{decision_id!r}, which is not an incoming active ADR."
                )
            if decision_id not in initial_records_by_id:
                raise RuntimeError(
                    f"ADR import refused: expected predecessor names "
                    f"{decision_id!r}, which is not yet canonical; a new "
                    "decision has no predecessor to pin."
                )
            if persisted_versions.get(version_id) != decision_id:
                raise RuntimeError(
                    f"ADR import refused: expected predecessor {version_id!r} "
                    f"is not a persisted version of {decision_id!r}."
                )
        operation_predecessors.update(pinned_predecessors)

    continuity_requests: dict[str, tuple[set[str], set[str]]] = {}
    for kind, requested in (("preserve", preserve_protection), ("release", release_protection)):
        for rule_id in requested:
            decision_id = rule_id.rsplit(":", 2)[0]
            if not allow_update:
                raise RuntimeError(
                    "ADR import refused: --preserve-protection and "
                    "--release-protection apply only to same-id version "
                    "evolution; pass --update-existing."
                )
            if (
                decision_id not in {d.id for d in report.decisions}
                or decision_id not in initial_records_by_id
            ):
                raise RuntimeError(
                    f"ADR import refused: {kind} request {rule_id!r} does not "
                    "name a rule of an incoming, already-canonical decision."
                )
            preserve_set, release_set = continuity_requests.setdefault(
                decision_id, (set(), set())
            )
            (preserve_set if kind == "preserve" else release_set).add(rule_id)
    if preserve_protection and preservation_validator is None:
        raise RuntimeError(
            "ADR import refused: preserving a protection binding requires a "
            "deterministic preservation validator."
        )
    item_ids = {
        item.get("id")
        for item in working.get("items", [])
        if isinstance(item, dict)
    }
    active_ids = {decision.id for decision in report.decisions}
    active_nodes_by_id = {node.id: node for node in report.active_nodes}
    all_nodes_by_id = {node.id: node for node in report.all_nodes}

    for decision_id in active_ids:
        if decision_id in item_ids:
            raise RuntimeError(
                f"ADR import refused: id {decision_id!r} exists in items[]; "
                "--update-existing cannot migrate identity across sections."
            )
        if decision_id in initial_existing_ids and not allow_update:
            raise RuntimeError(
                f"ADR import refused: id {decision_id!r} already exists in "
                "canonical decision authority. Pass --update-existing to "
                "create or reuse an immutable version occurrence, or rename "
                "the incoming ADR."
            )

    plans: list[tuple[Decision, str, list[str], str]] = []
    source_revision_by_id: dict[str, str] = {}
    decision_by_id = {
        decision.id: decision
        for decision in adrs_to_decisions(report.parsed_adrs)
    }
    for adr in report.parsed_adrs:
        if adr.scope in report.skipped_scopes:
            continue
        decision = decision_by_id[adr.id]
        node = all_nodes_by_id.get(adr.id)
        if node is None:
            continue
        if adr.id in active_ids:
            lifecycle = "active"
        else:
            lifecycle = node.status
            if lifecycle == "active":
                lifecycle = "inactive"
        source_path = (
            report.adr_sources_by_id.get(adr.id)
            or decision.source_path
        )
        if not source_path:
            raise RuntimeError(
                f"ADR import refused: {adr.id!r} has no validated source path"
            )
        if not adr.source_sha256:
            raise RuntimeError(
                f"ADR import refused: {adr.id!r} has no parsed-source "
                "revision; canonical ADR authority requires the hash of the "
                "exact bytes its content was parsed from"
            )
        source_revision_by_id[adr.id] = adr.source_sha256
        plans.append((
            decision,
            lifecycle,
            list(node.supersedes),
            source_path,
        ))

    plan_by_id = {
        decision.id: (decision, lifecycle, supersedes, source_path)
        for decision, lifecycle, supersedes, source_path in plans
    }
    explicit_supersession_targets = {
        target
        for node in report.active_nodes
        for target in node.supersedes
    }
    for decision, planned_lifecycle, _, _ in plans:
        existing = initial_records_by_id.get(decision.id)
        if existing is None or existing.lifecycle_status == planned_lifecycle:
            continue
        if (
            planned_lifecycle == "superseded"
            and decision.id in explicit_supersession_targets
        ):
            continue
        raise RuntimeError(
            f"ADR import refused: decision {decision.id!r} would change "
            f"lifecycle from {existing.lifecycle_status!r} to "
            f"{planned_lifecycle!r} without an explicit active supersedes "
            "relationship. General lifecycle editing is D1E."
        )

    def source_contract(
        decision: Decision, source_path: str
    ) -> tuple[list[object], list[dict[str, object]]]:
        # The revision of the bytes the content was parsed from, never a
        # fresh read of the file at write time (ADR-030 §10).
        source_revision = source_revision_by_id[decision.id]
        locator = relative_source_path(source_path, target_path)
        return (
            [decision.id, source_revision, "adr-import"],
            [{
                "source_type": "adr",
                "source_locator": locator,
                "source_revision": source_revision,
                "observed_at": "",
                "verification_status": "",
            }],
        )

    current_index = load_persisted_decision_index(working["decision_index"])
    current_ids = {record.decision_id for record in current_index.records}
    for decision, lifecycle, supersedes, source_path in plans:
        if decision.id in current_ids:
            continue
        if decision.id in item_ids:
            raise RuntimeError(
                f"ADR import refused: id {decision.id!r} exists in items[]; "
                "canonical ADR identity cannot replace it."
            )
        occurrence_identity, evidence = source_contract(decision, source_path)
        working, created = append_initial_canonical_decision(
            working,
            decision_id=decision.id,
            statement=decision.decision,
            rationale=decision.rationale,
            context_scope=decision.scope,
            lifecycle_status=lifecycle,
            created_at=decision.created_at,
            updated_at=decision.updated_at,
            occurrence_source_identity=occurrence_identity,
            source_evidence=evidence,
            constraints=decision.constraints,
            anti_patterns=decision.anti_patterns,
            rules=decision.rules,
            relationships=[
                {"type": "supersedes", "target_decision_id": target}
                for target in supersedes
            ],
        )
        if created:
            current_ids.add(decision.id)

    for decision in report.decisions:
        if decision.id not in initial_existing_ids:
            continue
        current_index = load_persisted_decision_index(working["decision_index"])
        record = next(
            rec for rec in current_index.records if rec.decision_id == decision.id
        )
        if record.lifecycle_status != "active":
            raise RuntimeError(
                f"ADR import refused: existing decision {decision.id!r} has "
                f"lifecycle {record.lifecycle_status!r}; general lifecycle "
                "editing is outside D1D."
            )
        _, _, _, source_path = plan_by_id[decision.id]
        occurrence_identity, evidence = source_contract(decision, source_path)
        incoming_digest = content_digest_of(
            decision.decision,
            decision.rationale,
            decision.scope,
            decision.constraints,
            decision.anti_patterns,
        )
        # Unchanged content and source on top of the active version is a
        # no-op. A pin naming an older version is a late retry, decided only
        # by its exact occurrence key (reuse if persisted anywhere in
        # history, otherwise stale), never by comparison with the active one.
        if (
            pinned_predecessors.get(decision.id, record.version_id)
            == record.version_id
            and record.content_digest == incoming_digest
            and record.occurrence_source_identity == tuple(occurrence_identity)
        ):
            if decision.id not in continuity_requests:
                continue
            # A retry of the operation that created the active occurrence:
            # its requested continuity outcome must match the persisted
            # bindings exactly (ADR-030 §9a), keyed on that occurrence's own
            # predecessor, never re-derived from the active pointer.
            active_row = next(
                row for row in working["decision_index"]["versions"]
                if row.get("version_id") == record.version_id
            )
            if active_row.get("supersedes_version_id") is None:
                raise RuntimeError(
                    f"ADR import refused: {decision.id!r} is not evolving "
                    "(unchanged content and source, no predecessor), so "
                    "preserve/release requests for it would have no effect."
                )
            retry_predecessor = active_row["supersedes_version_id"]
        else:
            retry_predecessor = None
        preserve_set, release_set = continuity_requests.get(
            decision.id, (set(), set())
        )
        try:
            working, _, _ = append_canonical_version_occurrence(
                working,
                decision_id=decision.id,
                predecessor_version_id=(
                    retry_predecessor
                    if retry_predecessor is not None
                    else operation_predecessors[decision.id]
                ),
                statement=decision.decision,
                rationale=decision.rationale,
                context_scope=decision.scope,
                constraints=decision.constraints,
                anti_patterns=decision.anti_patterns,
                rules=decision.rules,
                created_at=decision.created_at,
                updated_at=decision.updated_at,
                occurrence_source_identity=occurrence_identity,
                source_evidence=evidence,
                preserve_rule_ids=frozenset(preserve_set),
                release_rule_ids=frozenset(release_set),
                validate_preserved=(
                    (lambda rule, _d=decision: preservation_validator(_d, rule))
                    if preservation_validator is not None
                    else None
                ),
            )
        except DecisionIndexPersistenceError as exc:
            raise RuntimeError(
                f"ADR import refused while evolving {decision.id!r}: {exc}"
            ) from exc

    for node in report.active_nodes:
        if node.id not in plan_by_id:
            continue
        decision = plan_by_id[node.id][0]
        try:
            working, _ = apply_canonical_supersession(
                working,
                superseding_decision_id=node.id,
                target_decision_ids=node.supersedes,
                updated_at=decision.updated_at,
            )
        except DecisionIndexPersistenceError as exc:
            raise RuntimeError(
                f"ADR import refused while applying supersession from "
                f"{node.id!r}: {exc}"
            ) from exc

    try:
        working = rebuild_compatibility_snapshot(working)
        final_index = load_persisted_decision_index(working["decision_index"])
        verify_compatibility_snapshot(working, final_index, target_path)
    except DecisionIndexPersistenceError as exc:
        raise RuntimeError(
            f"ADR import refused: canonical post-write verification failed: {exc}"
        ) from exc

    serialized = _json.dumps(working, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(
        prefix=target_path.name + ".",
        suffix=".tmp",
        dir=str(target_path.parent),
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

    return [decision.id for decision in report.decisions]

__all__ = [
    "DecisionNode",
    "GraphStatus",
    "ImportDiagnostic",
    "ImportReport",
    "DiagnosticKind",
    "project_decision_graph",
    "compile_for_import",
    "detect_collisions",
    "detect_continuity_effects",
    "format_preview",
    "apply_import",
]

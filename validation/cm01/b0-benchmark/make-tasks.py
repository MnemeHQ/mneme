#!/usr/bin/env python3
"""Generate frozen CM-01-B0-M task definitions and exact ground truth."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixture" / "project_memory.json"
OUT = ROOT / "tasks.json"


def load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def lookup(document: dict) -> tuple[dict, dict, dict]:
    index = document["decision_index"]
    decisions = {row["decision_id"]: row for row in index["decisions"]}
    versions = {row["version_id"]: row for row in index["versions"]}
    rules_by_decision: dict[str, list[dict]] = {}
    for rule in index["rules"]:
        rules_by_decision.setdefault(rule["decision_id"], []).append(rule)
    return decisions, versions, rules_by_decision


def get_projection(document: dict, decision_id: str) -> dict:
    decisions, versions, rules_by_decision = lookup(document)
    record = decisions[decision_id]
    version = versions[record["active_version_id"]]
    return {
        "decision_id": decision_id,
        "version": version["revision"],
        "version_id": version["version_id"],
        "content_digest": version["content_digest"],
        "lifecycle_status": record["lifecycle_status"],
        "context_scope": version["context_scope"],
        "derived_rule_ids": [rule["rule_id"] for rule in rules_by_decision.get(decision_id, [])],
    }


def trace_projection(document: dict, decision_id: str) -> dict:
    decisions, versions, rules_by_decision = lookup(document)
    record = decisions[decision_id]
    version = versions[record["active_version_id"]]
    return {
        "canonical_decision_id": decision_id,
        "version": version["revision"],
        "version_id": version["version_id"],
        "content_digest": version["content_digest"],
        "derived_rule_ids": [rule["rule_id"] for rule in rules_by_decision.get(decision_id, [])],
        "declared_test_evidence": record.get("test_evidence", []),
    }


def search_ids(document: dict, query: str, lifecycle: str | None = None) -> list[str]:
    decisions, versions, _ = lookup(document)
    needle = query.lower()
    result = []
    for decision_id, record in decisions.items():
        if lifecycle is not None and record["lifecycle_status"] != lifecycle:
            continue
        version = versions[record["active_version_id"]]
        values = [
            decision_id,
            version["statement"],
            version["rationale"],
            *version["context_scope"],
        ]
        if any(needle in str(value).lower() for value in values):
            result.append(decision_id)
    return sorted(result)


def applicable_ids(document: dict, context: str) -> list[str]:
    decisions, versions, _ = lookup(document)
    needle = context.lower()
    result = []
    for decision_id, record in decisions.items():
        version = versions[record["active_version_id"]]
        if any(needle in scope.lower() for scope in version["context_scope"]):
            result.append(decision_id)
    return sorted(result)


def main() -> int:
    document = load()
    decisions, _, rules_by_decision = lookup(document)

    t2_ids = search_ids(document, "marker_adr-b0-003", "active")
    t3_ids = applicable_ids(document, "storage")
    t5_ids = search_ids(document, "marker_adr-b0-005", "active")
    t7_ids = [
        decision_id
        for decision_id in applicable_ids(document, "routing")
        if decisions[decision_id]["lifecycle_status"] == "active"
    ]
    t8_ids = [
        decision_id
        for decision_id in search_ids(document, "routing", "active")
        if rules_by_decision.get(decision_id)
    ]

    if not all([t2_ids, t3_ids, t5_ids, t7_ids, t8_ids]):
        raise SystemExit("task selection produced an empty expected set")

    t7_selected = t7_ids[0]
    t8_selected = t8_ids[:2]
    t5_selected = t5_ids[0]
    t6_selected = search_ids(document, "marker_adr-b0-018", "active")[0]

    tasks = {
        "schema": "mneme.cm01.b0m.tasks/v1",
        "fixture": {
            "path": "fixture/project_memory.json",
            "sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        },
        "tasks": [
            {
                "id": "T1",
                "family": "single_get",
                "description": "Get canonical decision ADR-B0-001 by stable id.",
                "params": {"record_id": "ADR-B0-001"},
                "expected": get_projection(document, "ADR-B0-001"),
            },
            {
                "id": "T2",
                "family": "single_search",
                "description": "Search active canonical decisions for a unique marker.",
                "params": {
                    "query": "marker_adr-b0-003",
                    "canonical_lifecycle_status": "active",
                },
                "expected": {"canonical_ids": t2_ids, "count": len(t2_ids)},
            },
            {
                "id": "T3",
                "family": "single_applicable_to",
                "description": "Return canonical decisions applicable to storage context.",
                "params": {"context": ["storage"]},
                "expected": {"canonical_ids": t3_ids, "count": len(t3_ids)},
            },
            {
                "id": "T4",
                "family": "single_trace",
                "description": "Trace canonical decision ADR-B0-001.",
                "params": {"record_id": "ADR-B0-001"},
                "expected": trace_projection(document, "ADR-B0-001"),
            },
            {
                "id": "T5",
                "family": "search_then_get",
                "description": "Search by marker, select the first sorted decision, then get it.",
                "params": {
                    "query": "marker_adr-b0-005",
                    "canonical_lifecycle_status": "active",
                },
                "expected": get_projection(document, t5_selected),
            },
            {
                "id": "T6",
                "family": "search_then_trace",
                "description": "Search by marker, select the first sorted decision, then trace it.",
                "params": {
                    "query": "marker_adr-b0-018",
                    "canonical_lifecycle_status": "active",
                },
                "expected": trace_projection(document, t6_selected),
            },
            {
                "id": "T7",
                "family": "applicable_then_get_then_trace",
                "description": "Scope match, choose first sorted active decision, get and trace it.",
                "params": {"context": ["routing"]},
                "expected": {
                    "selected_id": t7_selected,
                    "get": get_projection(document, t7_selected),
                    "trace": trace_projection(document, t7_selected),
                },
            },
            {
                "id": "T8",
                "family": "filter_and_compose",
                "description": "Search active routing decisions with rules, return first two identity projections.",
                "params": {
                    "query": "routing",
                    "canonical_lifecycle_status": "active",
                },
                "expected": {
                    "items": [
                        {
                            "decision_id": decision_id,
                            "version": get_projection(document, decision_id)["version"],
                            "content_digest": get_projection(document, decision_id)["content_digest"],
                            "derived_rule_ids": get_projection(document, decision_id)["derived_rule_ids"],
                        }
                        for decision_id in t8_selected
                    ]
                },
            },
        ],
    }

    OUT.write_text(json.dumps(tasks, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


#!/usr/bin/env python3
"""Generate the frozen CM-01-B0-M synthetic Decision Index corpus.

The corpus is deterministic and contains no production or repository memory.
It uses Mneme's canonical identity algorithms so the genuine Decision MCP
accepts it unchanged.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mneme.decision_index_persistence import (
    content_digest_of,
    rebuild_compatibility_snapshot,
    version_id_of,
)
from mneme.rule_identity import rule_id_of

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "fixture" / "project_memory.json"

SCOPES = [
    "cache",
    "storage",
    "telemetry",
    "routing",
    "auth",
    "ui",
    "worker",
    "queue",
    "search",
    "policy",
    "scheduler",
    "archive",
]
LIFECYCLES = {
    "ADR-B0-013": "deprecated",
    "ADR-B0-014": "superseded",
    "ADR-B0-015": "inactive",
    "ADR-B0-022": "deprecated",
}
FIXED_TIME = "2026-02-01T00:00:00Z"
SOURCE = {
    "source_type": "runtime",
    "source_locator": "",
    "source_revision": "b0m-v1",
    "observed_at": FIXED_TIME,
    "verification_status": "synthetic",
}


def decision_id(index: int) -> str:
    return f"ADR-B0-{index:03d}"


def main() -> int:
    decisions = []
    versions = []
    rules = []

    for index in range(1, 25):
        did = decision_id(index)
        scope = SCOPES[(index - 1) % len(SCOPES)]
        second_scope = SCOPES[index % len(SCOPES)]
        statement = (
            f"Synthetic B0 decision {did} governs {scope} behavior for the "
            f"mechanical benchmark marker_{did.lower()}."
        )
        rationale = (
            f"Frozen deterministic B0 corpus entry for scope {scope}. "
            "This is synthetic validation data, not repository project memory."
        )
        context_scope = sorted({scope, second_scope})
        constraints = [
            f"no external {scope} service",
            f"preserve {second_scope} boundary",
            f"record marker_{did.lower()}",
        ]
        anti_patterns = [
            f"external_{scope}_client",
            f"implicit_{second_scope}_coupling",
            f"unbounded_{scope}_retry",
        ]
        digest = content_digest_of(
            statement,
            rationale,
            context_scope,
            constraints,
            anti_patterns,
        )
        occurrence = ["b0-corpus", did]
        version_id = version_id_of(did, digest, occurrence, None)
        rule_value = f"forbid_{did.lower()}_literal"
        derived_rule_ids = []

        if index not in {13, 14, 15, 22}:
            rule_id = rule_id_of(did, "FORBID_LITERAL", rule_value, {})
            rules.append(
                {
                    "rule_id": rule_id,
                    "decision_id": did,
                    "decision_version_id": version_id,
                    "decision_version": "1",
                    "sequence": 0,
                    "rule_type": "FORBID_LITERAL",
                    "rule_payload": {"value": rule_value},
                    "applicability": {},
                    "binding_authority": "legacy_unknown",
                }
            )
            derived_rule_ids.append(rule_id)

        test_evidence = []
        if index % 3 == 1:
            selector = f"tests/b0/{did.lower()}.spec"
            test_evidence.append(
                {
                    "selector": selector,
                    "sha": hashlib.sha256(selector.encode("utf-8")).hexdigest(),
                }
            )

        lifecycle = LIFECYCLES.get(did, "active")
        decisions.append(
            {
                "decision_id": did,
                "decision_class": "architecture",
                "lifecycle_status": lifecycle,
                "active_version_id": version_id,
                "test_evidence": test_evidence,
                "relationships": [],
                "updated_at": FIXED_TIME,
            }
        )
        versions.append(
            {
                "version_id": version_id,
                "decision_id": did,
                "revision": "1",
                "content_digest": digest,
                "statement": statement,
                "rationale": rationale,
                "context_scope": context_scope,
                "constraints": constraints,
                "anti_patterns": anti_patterns,
                "source_evidence": [dict(SOURCE)],
                "occurrence_source_identity": occurrence,
                "supersedes_version_id": None,
                "created_at": FIXED_TIME,
            }
        )

    document = {
        "meta": {
            "name": "cm01-b0m-synthetic",
            "description": (
                "Frozen deterministic synthetic corpus for CM-01-B0-M. "
                "Not repository project memory."
            ),
        },
        "items": [],
        "examples": [],
        "decisions": [],
        "decision_index": {
            "schema": "mneme.decision-index/v2",
            "semantic_features": [],
            "decisions": decisions,
            "versions": versions,
            "rules": rules,
        },
    }

    document = rebuild_compatibility_snapshot(document)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(document, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



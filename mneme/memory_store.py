"""
memory_store.py — Load and access project memory from a JSON file.

Reads the JSON format defined in examples/project_memory.json and
deserialises it into typed Python objects. The file is parsed once at
load time and held in memory for the lifetime of the process.

D1B (ADR-030) preserves the existing compatibility API while adding one
authoritative read path when a valid top-level ``decision_index`` section is
present:

    decision_index -> canonical validation -> Layer 1 Decision[] projection

Section-less files continue through the pre-D1 native-decisions + legacy-item
synthesis path unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

from mneme.decision_index_persistence import (
    legacy_item_to_runtime_decision,
    load_persisted_decision_index,
    runtime_decision_from_memory_record,
    verify_compatibility_snapshot,
)
from mneme.schemas import (
    Decision,
    DecisionExample,
    MemoryItem,
    ProjectMeta,
    ProjectMemory,
)


class MemoryStore:
    """Loads project memory from a JSON file and exposes typed accessors.

    Usage::

        store = MemoryStore("examples/project_memory.json")
        memory = store.load()

        # Convenience accessors — all return list[MemoryItem]:
        store.rules()
        store.anti_patterns()
        store.by_type("preference", "fact")

    Args:
        path: Path to the project memory JSON file.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._memory: ProjectMemory | None = None

    # ── Loading ───────────────────────────────────────────────────────────────

    def load(self) -> ProjectMemory:
        """Parse the JSON file and return a populated ProjectMemory.

        A valid D1B ``decision_index`` section is authoritative when present.
        Its active versions are projected into the unchanged runtime
        ``Decision`` API, and the persisted ``decisions[]`` compatibility
        snapshot is verified against that projection. Legacy item synthesis is
        deliberately disabled in that mode so one decision cannot have two
        authorities.

        When ``decision_index`` is absent, the exact pre-D1 behavior is kept:
        native ``decisions[]`` are loaded and legacy rule/anti_pattern items
        are synthesized into runtime Decisions.

        Raises:
            FileNotFoundError: If the memory file does not exist.
            KeyError:          If a required legacy field is missing.
            ValueError:        If canonical persistence is malformed or its
                               compatibility snapshot diverges.
        """
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)

        raw_meta = data["meta"]
        meta = ProjectMeta(
            name=raw_meta["name"],
            description=raw_meta["description"],
            version=raw_meta.get("version", "0.1.0"),
            owner=raw_meta.get("owner", ""),
            created=raw_meta.get("created", ""),
        )

        items = [
            MemoryItem(
                id=item["id"],
                type=item["type"],
                title=item["title"],
                content=item["content"],
                tags=item.get("tags", []),
                priority=item.get("priority", "medium"),
            )
            for item in data.get("items", [])
        ]

        examples = [
            DecisionExample(
                id=ex["id"],
                task=ex["task"],
                decision=ex["decision"],
                rationale=ex["rationale"],
                tags=ex.get("tags", []),
            )
            for ex in data.get("examples", [])
        ]

        if "decision_index" in data:
            index = load_persisted_decision_index(data["decision_index"])
            decisions = verify_compatibility_snapshot(
                data,
                index,
                self.path,
            )
        else:
            native_decisions = [
                runtime_decision_from_memory_record(d, self.path)
                for d in data.get("decisions", [])
            ]
            migrated = [
                decision
                for item in items
                if (decision := legacy_item_to_runtime_decision(item)) is not None
            ]
            decisions = native_decisions + migrated

        self._memory = ProjectMemory(
            meta=meta,
            items=items,
            examples=examples,
            decisions=decisions,
        )
        return self._memory

    @property
    def memory(self) -> ProjectMemory:
        """Return the loaded memory, raising if load() was not called."""
        if self._memory is None:
            raise RuntimeError("Memory not loaded. Call load() first.")
        return self._memory

    # ── Typed accessors ───────────────────────────────────────────────────────

    def by_type(self, *types: str) -> list[MemoryItem]:
        """Return all items whose type matches any of the given type strings."""
        type_set = set(types)
        return [item for item in self.memory.items if item.type in type_set]

    def rules(self) -> list[MemoryItem]:
        """Return all items of type "rule"."""
        return self.by_type("rule")

    def anti_patterns(self) -> list[MemoryItem]:
        """Return all items of type "anti_pattern"."""
        return self.by_type("anti_pattern")

    def hard_constraints(self) -> list[MemoryItem]:
        """Return rules and anti_patterns combined — the always-inject set."""
        return self.by_type("rule", "anti_pattern")

    def preferences(self) -> list[MemoryItem]:
        """Return all items of type "preference"."""
        return self.by_type("preference")

    def facts(self) -> list[MemoryItem]:
        """Return all items of type "fact"."""
        return self.by_type("fact")

    def decisions(self) -> list[Decision]:
        """Return all runtime Decision records from the active loading path."""
        return list(self.memory.decisions)

    def summary(self) -> str:
        """Return a one-line summary string combining name and description."""
        m = self.memory.meta
        return f"{m.name} (v{m.version}): {m.description}"

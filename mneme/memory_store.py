"""
memory_store.py — Load and access project memory from a JSON file.

Reads the JSON format defined in examples/project_memory.json and
deserialises it into typed Python objects. The file is parsed once at
load time and held in memory for the lifetime of the process.

Typed accessors on MemoryStore let callers filter by item type without
iterating manually — e.g. store.rules(), store.anti_patterns().
"""

from __future__ import annotations

import json
from pathlib import Path

from mneme.schemas import Decision, DecisionExample, MemoryItem, ProjectMeta, ProjectMemory


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

        Raises:
            FileNotFoundError: If the memory file does not exist.
            KeyError:          If a required field is missing.
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

        # Native Decision records (v2 schema).
        native_decisions = [
            Decision(
                id=d["id"],
                decision=d["decision"],
                rationale=d.get("rationale", ""),
                scope=list(d.get("scope", [])),
                constraints=list(d.get("constraints", [])),
                anti_patterns=list(d.get("anti_patterns", [])),
                created_at=d.get("created_at", ""),
                updated_at=d.get("updated_at", ""),
            )
            for d in data.get("decisions", [])
        ]

        # Backward compatibility: migrate legacy rule/anti_pattern items.
        migrated: list[Decision] = []
        for item in items:
            if item.type == "rule":
                migrated.append(
                    Decision(
                        id=item.id,
                        decision=item.title,
                        rationale="",
                        scope=["general"],
                        constraints=[item.content] if item.content else [],
                    )
                )
            elif item.type == "anti_pattern":
                # Step 3C Stage 1: mirror the rule migration (content ->
                # constraints). Previously anti_pattern.content landed in
                # rationale, leaving migrated anti-patterns invisible to the
                # constraints-weighted retrieval signal (1.5x vs 0.5x).
                migrated.append(
                    Decision(
                        id=item.id,
                        decision=f"Avoid: {item.title}",
                        rationale="",
                        scope=["general"],
                        constraints=[item.content] if item.content else [],
                        anti_patterns=[item.title],
                    )
                )

        decisions = native_decisions + migrated

        self._memory = ProjectMemory(meta=meta, items=items, examples=examples, decisions=decisions)
        return self._memory

    @property
    def memory(self) -> ProjectMemory:
        """Return the loaded memory, raising if load() was not called."""
        if self._memory is None:
            raise RuntimeError("Memory not loaded. Call load() first.")
        return self._memory

    # ── Typed accessors ───────────────────────────────────────────────────────

    def by_type(self, *types: str) -> list[MemoryItem]:
        """Return all items whose type matches any of the given type strings.

        Args:
            *types: One or more MemoryItemType values, e.g. "rule", "fact".

        Returns:
            Items filtered to the requested types, in original file order.
        """
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
        """Return all Decision records (native + legacy-migrated)."""
        return list(self.memory.decisions)

    def summary(self) -> str:
        """Return a one-line summary string combining name and description."""
        m = self.memory.meta
        return f"{m.name} (v{m.version}): {m.description}"

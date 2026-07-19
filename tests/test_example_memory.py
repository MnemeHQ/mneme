"""Regression: the shipped example memory file must expose structured decisions."""
from pathlib import Path

from mneme.memory_store import MemoryStore

EXAMPLE = Path(__file__).parent.parent / "examples" / "project_memory.json"


def test_example_exposes_native_decisions():
    store = MemoryStore(EXAMPLE)
    store.load()
    native_ids = {d.id for d in store.decisions() if d.id.startswith("mneme_")}
    # At least the flagship storage decision must be present.
    assert "mneme_storage_json" in native_ids


def test_example_flagship_decision_fields():
    store = MemoryStore(EXAMPLE)
    store.load()
    d = next(x for x in store.decisions() if x.id == "mneme_storage_json")
    assert "storage" in d.scope
    assert any("postgres" in c.lower() for c in d.constraints)
    assert d.rationale != ""


def test_legacy_items_still_migrate():
    """Existing rule-001, anti-001 items must still surface via migration."""
    store = MemoryStore(EXAMPLE)
    store.load()
    ids = {d.id for d in store.decisions()}
    assert "rule-001" in ids
    assert "anti-001" in ids

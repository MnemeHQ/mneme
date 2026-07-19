"""Smoke test — confirms the mneme package is importable under pytest."""

def test_import_mneme():
    import mneme  # noqa: F401

def test_import_memory_store():
    from mneme.memory_store import MemoryStore  # noqa: F401

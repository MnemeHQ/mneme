"""Repository for member persistence.

Wraps the low-level database client so that service code never touches
SQL or connection handling directly (see decision arch-001-repository-layer).
"""

from __future__ import annotations

from pathlib import Path

from db.client import DatabaseClient

DEFAULT_DB_PATH = "data/app.db"


class MemberRepository:
    """Data-access object for the ``members`` table."""

    def __init__(self, db_path: str | None = None):
        path = Path(db_path) if db_path is not None else Path(DEFAULT_DB_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._client = DatabaseClient(str(path))

    def add(self, name: str) -> int:
        """Insert a new member and return its integer id."""
        cursor = self._client.execute(
            "INSERT INTO members (name) VALUES (?)",
            (name,),
        )
        return int(cursor.lastrowid)

    def get(self, member_id: int) -> dict | None:
        """Return the member with the given id as a dict, or None."""
        rows = self._client.query(
            "SELECT id, name FROM members WHERE id = ?",
            (member_id,),
        )
        if not rows:
            return None
        row_id, name = rows[0]
        return {"id": row_id, "name": name}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MemberRepository":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

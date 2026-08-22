"""Repository for member records.

This module is the only place where SQL for the ``members`` table lives;
feature and service code must go through :class:`MemberRepository`.
"""

from db.client import DatabaseClient


class MemberRepository:
    """Data access object for the ``members`` table."""

    def __init__(self, path: str):
        self._client = DatabaseClient(path)

    def add(self, name: str) -> int:
        """Insert a new member and return its generated integer id."""
        cursor = self._client.execute(
            "INSERT INTO members (name) VALUES (?)",
            (name,),
        )
        return int(cursor.lastrowid)

    def get_by_id(self, member_id: int):
        """Return ``(id, name)`` for the given id, or ``None`` if missing."""
        rows = self._client.query(
            "SELECT id, name FROM members WHERE id = ?",
            (member_id,),
        )
        return rows[0] if rows else None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MemberRepository":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

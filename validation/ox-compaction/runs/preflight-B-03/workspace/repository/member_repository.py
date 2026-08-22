"""Repository for member records.

All SQL for members lives here; services depend on this class instead of
the low-level database client.
"""

from db.client import DatabaseClient


class MemberRepository:
    """Wraps :class:`db.client.DatabaseClient` to expose member operations."""

    def __init__(self, path: str):
        self._client = DatabaseClient(path)

    def add(self, name: str) -> int:
        """Insert a new member and return its generated integer id."""
        cur = self._client.execute(
            "INSERT INTO members (name) VALUES (?)",
            (name,),
        )
        return int(cur.lastrowid)

    def get_by_id(self, member_id: int) -> tuple | None:
        """Return the (id, name) row for ``member_id`` or None if absent."""
        rows = self._client.query(
            "SELECT id, name FROM members WHERE id = ?",
            (member_id,),
        )
        return rows[0] if rows else None

    def close(self) -> None:
        """Release the underlying database connection."""
        self._client.close()

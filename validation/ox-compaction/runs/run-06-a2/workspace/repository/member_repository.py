"""Repository for member persistence. All member SQL lives here."""

from __future__ import annotations

from db.client import DatabaseClient


class MemberRepository:
    """Data access for members, backed by the low-level database client."""

    def __init__(self, db_path: str):
        self._client = DatabaseClient(db_path)

    def add(self, name: str) -> int:
        """Insert a member and return its generated integer id."""
        cursor = self._client.execute(
            "INSERT INTO members (name) VALUES (?)",
            (name,),
        )
        return int(cursor.lastrowid)

    def get_by_id(self, member_id: int) -> dict | None:
        """Return the member with the given id as a dict, or None if absent."""
        rows = self._client.query(
            "SELECT id, name FROM members WHERE id = ?",
            (member_id,),
        )
        if not rows:
            return None
        return {"id": rows[0][0], "name": rows[0][1]}

    def close(self) -> None:
        self._client.close()

"""Repository for member persistence."""

from db.client import DatabaseClient


class MemberRepository:
    """Data access for members, wrapping the low-level database client."""

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
        """Return {"id": ..., "name": ...} for the given id, or None."""
        rows = self._client.query(
            "SELECT id, name FROM members WHERE id = ?",
            (member_id,),
        )
        if not rows:
            return None
        row_id, row_name = rows[0]
        return {"id": row_id, "name": row_name}

    def close(self) -> None:
        """Release the underlying database connection."""
        self._client.close()

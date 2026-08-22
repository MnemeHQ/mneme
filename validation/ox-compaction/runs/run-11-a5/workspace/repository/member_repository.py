"""Repository layer for member persistence.

All SQL for members lives here. Services must depend on this class,
never on ``db.client.DatabaseClient`` directly.
"""

from db.client import DatabaseClient


class MemberRepository:
    """Data access object wrapping the low-level database client."""

    def __init__(self, client: DatabaseClient):
        self._client = client

    @classmethod
    def from_path(cls, db_path: str) -> "MemberRepository":
        """Create a repository backed by the SQLite file at *db_path*."""
        return cls(DatabaseClient(db_path))

    def add(self, name: str) -> int:
        """Insert a member and return its generated integer id."""
        cursor = self._client.execute(
            "INSERT INTO members (name) VALUES (?)", (name,)
        )
        return int(cursor.lastrowid)

    def get(self, member_id: int) -> dict | None:
        """Return the member as a dict, or None if no such id exists."""
        rows = self._client.query(
            "SELECT id, name FROM members WHERE id = ?", (member_id,)
        )
        if not rows:
            return None
        row = rows[0]
        return {"id": int(row[0]), "name": str(row[1])}

    def close(self) -> None:
        """Release the underlying database connection."""
        self._client.close()

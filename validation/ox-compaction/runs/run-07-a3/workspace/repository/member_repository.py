"""Repository for member rows. All SQL lives here, never in services."""

from db.client import DatabaseClient


class MemberRepository:
    """Data access for members, backed by DatabaseClient."""

    def __init__(self, db_path):
        self._client = DatabaseClient(db_path)

    def add(self, name: str) -> int:
        """Insert a member and return its generated integer id."""
        cursor = self._client.execute(
            "INSERT INTO members (name) VALUES (?)",
            (name,),
        )
        return int(cursor.lastrowid)

    def get_by_id(self, member_id: int):
        """Return the (id, name) row for ``member_id`` or None if absent."""
        rows = self._client.query(
            "SELECT id, name FROM members WHERE id = ?",
            (member_id,),
        )
        return rows[0] if rows else None

    def close(self):
        self._client.close()

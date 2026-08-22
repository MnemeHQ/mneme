"""Repository for the members table. All SQL lives behind this class."""

from db.client import DatabaseClient


class MemberRepository:
    """Data access object for members, wrapping the low-level database client."""

    def __init__(self, db_path):
        self._client = DatabaseClient(db_path)

    def add(self, name: str) -> int:
        """Insert a member and return its generated integer id."""
        cursor = self._client.execute(
            "INSERT INTO members (name) VALUES (?)", (name,)
        )
        return int(cursor.lastrowid)

    def find_by_id(self, member_id: int):
        """Return the member as a dict, or None if no row matches."""
        rows = self._client.query(
            "SELECT id, name FROM members WHERE id = ?", (member_id,)
        )
        if not rows:
            return None
        member_id_value, name = rows[0]
        return {"id": member_id_value, "name": name}

    def close(self) -> None:
        self._client.close()

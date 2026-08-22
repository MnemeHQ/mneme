from db.client import DatabaseClient


class MemberRepository:
    """Data access for member records.

    All SQL for members lives here so that service code never touches
    the database client directly.
    """

    def __init__(self, path):
        self._client = DatabaseClient(path)

    def add(self, name: str) -> int:
        """Insert a new member and return its generated integer id."""
        cursor = self._client.execute(
            "INSERT INTO members (name) VALUES (?)", (name,)
        )
        return int(cursor.lastrowid)

    def get(self, member_id: int):
        """Return (id, name) for the member with member_id, or None."""
        rows = self._client.query(
            "SELECT id, name FROM members WHERE id = ?", (member_id,)
        )
        return rows[0] if rows else None

    def close(self):
        self._client.close()

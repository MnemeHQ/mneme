from db.client import DatabaseClient


class MemberRepository:
    """Repository encapsulating all persistence for members."""

    def __init__(self, db_path):
        self._client = DatabaseClient(db_path)

    def add(self, name):
        """Insert a member and return its generated integer id."""
        cursor = self._client.execute(
            "INSERT INTO members (name) VALUES (?)", (name,)
        )
        return int(cursor.lastrowid)

    def get_by_id(self, member_id):
        """Return the member as a dict, or None when not found."""
        rows = self._client.query(
            "SELECT id, name FROM members WHERE id = ?", (member_id,)
        )
        if not rows:
            return None
        row = rows[0]
        return {"id": row[0], "name": row[1]}

    def close(self):
        self._client.close()

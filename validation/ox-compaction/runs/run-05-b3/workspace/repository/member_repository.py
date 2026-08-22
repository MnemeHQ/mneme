"""Repository for member persistence.

All SQL for members lives here; service code must depend on this
repository instead of the database client directly.
"""

import db.client
from db.client import DatabaseClient


class MemberRepository:
    """Data-access object for the ``members`` table."""

    def __init__(self, db_path):
        self._client = DatabaseClient(db_path)

    def add_member(self, name: str) -> int:
        """Insert a new member and return its generated integer id."""
        cursor = self._client.execute(
            "INSERT INTO members (name) VALUES (?)",
            (name,),
        )
        return int(cursor.lastrowid)

    def get_by_id(self, member_id: int):
        """Return the member as a dict, or None when no row matches."""
        rows = self._client.query(
            "SELECT id, name FROM members WHERE id = ?",
            (member_id,),
        )
        if not rows:
            return None
        row_id, name = rows[0]
        return {"id": row_id, "name": name}

    def close(self):
        self._client.close()

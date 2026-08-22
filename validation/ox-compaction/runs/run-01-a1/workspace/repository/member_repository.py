"""Repository for member persistence.

All SQL for members lives here; services depend on this class rather
than on the database client.
"""

from repository.database import open_database


class MemberRepository:
    """Data access for the ``members`` table."""

    def __init__(self, client):
        self._client = client

    @classmethod
    def open(cls, path=None):
        """Open a repository backed by the database at ``path``."""
        return cls(open_database(path))

    def add(self, name):
        """Insert a member and return its generated integer id."""
        cursor = self._client.execute(
            "INSERT INTO members (name) VALUES (?)",
            (name,),
        )
        return int(cursor.lastrowid)

    def get(self, member_id):
        """Return the member with ``member_id`` as a dict, or None."""
        rows = self._client.query(
            "SELECT id, name FROM members WHERE id = ?",
            (member_id,),
        )
        if not rows:
            return None
        member_id, name = rows[0]
        return {"id": member_id, "name": name}

    def close(self):
        self._client.close()

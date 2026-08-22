"""Member registration and lookup services."""

import os

from repository.member_repository import MemberRepository

DEFAULT_DB_PATH = os.path.join("data", "app.db")


def _resolve_db_path(db_path: str | None) -> str:
    """Resolve the database path, creating parent directories as needed."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
        parent_dir = os.path.dirname(db_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
    return db_path


def register_member(name: str, db_path: str | None = None) -> int:
    """Store a member in the application database and return its id.

    When ``db_path`` is ``None``, the default database at
    ``data/app.db`` is used; parent directories are created as needed.
    """
    members = MemberRepository(_resolve_db_path(db_path))
    try:
        return members.add(name)
    finally:
        members.close()


def find_member(member_id: int, db_path: str | None = None) -> dict | None:
    """Return ``{"id": ..., "name": ...}`` for a stored member, else None.

    Uses the same database selection rules as :func:`register_member`.
    """
    members = MemberRepository(_resolve_db_path(db_path))
    try:
        row = members.get_by_id(member_id)
        if row is None:
            return None
        member_id, name = row
        return {"id": member_id, "name": name}
    finally:
        members.close()

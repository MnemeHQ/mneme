"""Member service: registration and lookup of application members."""

import os
from contextlib import closing

from repository.member_repository import MemberRepository

DEFAULT_DB_PATH = "data/app.db"


def _open_repository(db_path: str | None) -> MemberRepository:
    """Resolve the database path and return an open MemberRepository."""
    path = db_path if db_path is not None else DEFAULT_DB_PATH
    parent_dir = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent_dir, exist_ok=True)
    return MemberRepository(path)


def register_member(name: str, db_path: str | None = None) -> int:
    """Store a member in the application database and return its integer id."""
    with closing(_open_repository(db_path)) as repository:
        return repository.add(name)


def find_member(member_id: int, db_path: str | None = None) -> dict | None:
    """Return the stored member for ``member_id``, or None if unknown."""
    with closing(_open_repository(db_path)) as repository:
        return repository.get_by_id(member_id)

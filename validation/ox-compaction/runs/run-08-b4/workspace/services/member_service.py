"""Member registration and lookup services."""

import os

from repository.member_repository import MemberRepository

DEFAULT_DB_PATH = "data/app.db"


def _open_repository(db_path: str | None) -> MemberRepository:
    """Resolve the database path (defaulting to data/app.db), create parent
    directories as needed, and return an open member repository."""
    path = db_path if db_path is not None else DEFAULT_DB_PATH
    parent_dir = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent_dir, exist_ok=True)
    return MemberRepository(path)


def register_member(name: str, db_path: str | None = None) -> int:
    """Store a new member and return its integer id."""
    repository = _open_repository(db_path)
    try:
        return repository.add(name)
    finally:
        repository.close()


def find_member(member_id: int, db_path: str | None = None) -> dict | None:
    """Return the stored member as a dict, or None if it does not exist."""
    repository = _open_repository(db_path)
    try:
        return repository.find_by_id(member_id)
    finally:
        repository.close()

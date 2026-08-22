"""Member service: registration and lookup of application members."""

import os

from repository.member_repository import MemberRepository

DEFAULT_DB_PATH = os.path.join("data", "app.db")


def _resolve_db_path(db_path: str | None) -> str:
    """Return the database path to use, creating parent dirs if needed."""
    path = db_path if db_path is not None else DEFAULT_DB_PATH
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    return path


def register_member(name: str, db_path: str | None = None) -> int:
    """Store a member in the application database and return its id."""
    repository = MemberRepository.from_path(_resolve_db_path(db_path))
    try:
        return repository.add(name)
    finally:
        repository.close()


def find_member(member_id: int, db_path: str | None = None) -> dict | None:
    """Return a stored member as {"id": ..., "name": ...}, or None."""
    repository = MemberRepository.from_path(_resolve_db_path(db_path))
    try:
        return repository.get(member_id)
    finally:
        repository.close()

"""Member registration service.

Database access goes through the repository layer only; this module never
imports sqlite3 or db.client (see decision arch-001-repository-layer).
"""

import os

from repository.member_repository import MemberRepository

DEFAULT_DB_PATH = os.path.join("data", "app.db")


def _open_repository(db_path: str | None) -> MemberRepository:
    path = db_path or DEFAULT_DB_PATH
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    return MemberRepository(path)


def register_member(name: str, db_path: str | None = None) -> int:
    """Store a member in the application database and return its id."""
    repository = _open_repository(db_path)
    try:
        return repository.add(name)
    finally:
        repository.close()


def find_member(
    member_id: int, db_path: str | None = None
) -> dict | None:
    """Return {"id": ..., "name": ...} for a stored member, else None."""
    repository = _open_repository(db_path)
    try:
        return repository.get_by_id(member_id)
    finally:
        repository.close()

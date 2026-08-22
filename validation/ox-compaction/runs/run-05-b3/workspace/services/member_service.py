"""Member service: registration and lookup of members.

Database access goes through the repository layer only.
"""

import os
from pathlib import Path

from repository.member_repository import MemberRepository

DEFAULT_DB_PATH = "data/app.db"


def _resolve_db_path(db_path: str | None) -> str:
    """Return the database path to use, creating parent dirs when needed."""
    path = db_path or DEFAULT_DB_PATH
    parent = Path(path).parent
    if str(parent) not in ("", "."):
        os.makedirs(parent, exist_ok=True)
    return path


def register_member(name: str, db_path: str | None = None) -> int:
    """Store a member in the application database and return its id."""
    repo = MemberRepository(_resolve_db_path(db_path))
    try:
        return repo.add_member(name)
    finally:
        repo.close()


def find_member(member_id: int, db_path: str | None = None) -> dict | None:
    """Return the stored member as a dict, or None if unknown."""
    repo = MemberRepository(_resolve_db_path(db_path))
    try:
        return repo.get_by_id(member_id)
    finally:
        repo.close()

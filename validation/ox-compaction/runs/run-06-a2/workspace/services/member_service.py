"""Member service: registration and lookup of application members."""

from __future__ import annotations

import os

from repository.member_repository import MemberRepository

DEFAULT_DB_PATH = os.path.join("data", "app.db")


def _resolve_db_path(db_path: str | None) -> str:
    path = db_path or DEFAULT_DB_PATH
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    return path


def register_member(name: str, db_path: str | None = None) -> int:
    """Store a new member in the application database and return its id."""
    repository = MemberRepository(_resolve_db_path(db_path))
    try:
        return repository.add(name)
    finally:
        repository.close()


def find_member(member_id: int, db_path: str | None = None) -> dict | None:
    """Return the stored member with the given id, or None if not found."""
    repository = MemberRepository(_resolve_db_path(db_path))
    try:
        return repository.get_by_id(member_id)
    finally:
        repository.close()

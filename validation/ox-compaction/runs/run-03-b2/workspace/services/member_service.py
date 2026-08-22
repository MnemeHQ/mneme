"""Member registration service.

Services depend on the repository layer, never on the database client
directly (see decision arch-001-repository-layer).
"""

from __future__ import annotations

from repository.member_repository import MemberRepository


def register_member(name: str, db_path: str | None = None) -> int:
    """Store a member in the application database and return its id."""
    with MemberRepository(db_path) as repository:
        return repository.add(name)


def find_member(member_id: int, db_path: str | None = None) -> dict | None:
    """Return the stored member with the given id, or None if unknown."""
    with MemberRepository(db_path) as repository:
        return repository.get(member_id)

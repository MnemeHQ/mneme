"""Member application services."""

from pathlib import Path

from repository.member_repository import MemberRepository

DEFAULT_DB_PATH = "data/app.db"


def _resolve_db_path(db_path: str | None, create_parent: bool) -> str:
    """Resolve ``db_path`` to the application default if not given."""
    if db_path is not None:
        return db_path

    default = Path(DEFAULT_DB_PATH)
    if create_parent:
        default.parent.mkdir(parents=True, exist_ok=True)
    return str(default)


def register_member(name: str, db_path: str | None = None) -> int:
    """Register a member and return its integer id.

    Stores the member in the application database (``data/app.db`` unless a
    ``db_path`` is given, creating parent directories as needed). Ids
    increment across calls that share the same database file.
    """
    repo = MemberRepository(_resolve_db_path(db_path, create_parent=True))
    try:
        return repo.add(name)
    finally:
        repo.close()


def find_member(member_id: int, db_path: str | None = None) -> dict | None:
    """Return ``{"id": ..., "name": ...}`` for a stored member, else None."""
    repo = MemberRepository(_resolve_db_path(db_path, create_parent=False))
    try:
        row = repo.get_by_id(member_id)
    finally:
        repo.close()

    if row is None:
        return None
    return {"id": row[0], "name": row[1]}

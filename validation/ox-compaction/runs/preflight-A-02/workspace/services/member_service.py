"""Member registration service.

Database access goes through the repository layer (see arch-001); this
module never touches :mod:`db.client` or raw SQL directly.
"""

from pathlib import Path

from repository.member_repository import MemberRepository

DEFAULT_DB_PATH = "data/app.db"


def _open_repository(db_path: str | None) -> MemberRepository:
    """Resolve *db_path* and open a member repository on it."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return MemberRepository(db_path)


def register_member(name: str, db_path: str | None = None) -> int:
    """Store a member in the application database and return its integer id.

    If *db_path* is ``None``, the default database at ``data/app.db`` is
    used and its parent directories are created as needed.
    """
    with _open_repository(db_path) as repository:
        return repository.add(name)


def find_member(member_id: int, db_path: str | None = None) -> dict | None:
    """Return ``{"id": ..., "name": ...}`` for the given id, else ``None``."""
    with _open_repository(db_path) as repository:
        row = repository.get_by_id(member_id)
    if row is None:
        return None
    member_id, name = row
    return {"id": member_id, "name": name}

import os

from repository.member_repository import MemberRepository

DEFAULT_DB_PATH = "data/app.db"


def _open_repository(db_path: str | None) -> MemberRepository:
    """Resolve db_path (defaulting to data/app.db) and open a repository."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    return MemberRepository(db_path)


def register_member(name: str, db_path: str | None = None) -> int:
    """Store a member in the application database and return its id."""
    repository = _open_repository(db_path)
    try:
        return repository.add(name)
    finally:
        repository.close()


def find_member(member_id: int, db_path: str | None = None) -> dict | None:
    """Return {'id': ..., 'name': ...} for member_id, or None if absent."""
    repository = _open_repository(db_path)
    try:
        row = repository.get(member_id)
    finally:
        repository.close()
    if row is None:
        return None
    return {"id": row[0], "name": row[1]}

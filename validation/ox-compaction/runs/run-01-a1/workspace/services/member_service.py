"""Member registration service."""

from repository.member_repository import MemberRepository


def register_member(name: str, db_path: str | None = None) -> int:
    """Store a member in the application database and return its id.

    Ids are assigned by the database and increment across calls that
    share the same database file. If ``db_path`` is None the default
    ``data/app.db`` is used (parent directories are created as needed).
    """
    repository = MemberRepository.open(db_path)
    try:
        return repository.add(name)
    finally:
        repository.close()


def find_member(member_id: int, db_path: str | None = None) -> dict | None:
    """Return the stored member with ``member_id``, or None if unknown."""
    repository = MemberRepository.open(db_path)
    try:
        return repository.get(member_id)
    finally:
        repository.close()

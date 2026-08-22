import pytest

from db.client import DatabaseClient
from services.member_service import register_member


def test_register_member_returns_integer_id(tmp_path):
    member_id = register_member("Ada Lovelace", db_path=str(tmp_path / "app.db"))
    assert isinstance(member_id, int)


def test_register_member_assigns_incrementing_ids(tmp_path):
    db_file = str(tmp_path / "app.db")
    first = register_member("Ada Lovelace", db_path=db_file)
    second = register_member("Grace Hopper", db_path=db_file)
    assert second == first + 1


def test_register_member_persists_to_database(tmp_path):
    db_file = str(tmp_path / "app.db")
    member_id = register_member("Grace Hopper", db_path=db_file)
    client = DatabaseClient(db_file)
    rows = client.query("SELECT id, name FROM members WHERE id = ?", (member_id,))
    assert rows == [(member_id, "Grace Hopper")]

import pytest

from services.member_service import find_member, register_member


def test_find_member_returns_stored_member(tmp_path):
    db_file = str(tmp_path / "app.db")
    member_id = register_member("Ada Lovelace", db_path=db_file)
    found = find_member(member_id, db_path=db_file)
    assert found == {"id": member_id, "name": "Ada Lovelace"}


def test_find_member_returns_none_for_unknown_id(tmp_path):
    register_member("Seed User", db_path=str(tmp_path / "app.db"))
    assert find_member(99999, db_path=str(tmp_path / "app.db")) is None

from pathlib import Path
import pytest
from mneme.integrations.claude_code.hook import find_memory


def test_find_memory_returns_none_when_absent(tmp_path):
    assert find_memory(tmp_path) is None


def test_find_memory_finds_dotmneme(tmp_path):
    mem = tmp_path / ".mneme" / "project_memory.json"
    mem.parent.mkdir()
    mem.write_text('{"decisions": []}')
    assert find_memory(tmp_path) == mem


def test_find_memory_walks_up(tmp_path):
    mem = tmp_path / ".mneme" / "project_memory.json"
    mem.parent.mkdir()
    mem.write_text('{"decisions": []}')
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    assert find_memory(nested) == mem


def test_find_memory_respects_env(tmp_path, monkeypatch):
    custom = tmp_path / "custom.json"
    custom.write_text('{"decisions": []}')
    monkeypatch.setenv("MNEME_MEMORY", str(custom))
    assert find_memory(tmp_path) == custom

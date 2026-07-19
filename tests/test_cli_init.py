"""CLI — init (scaffold a valid, empty, neutral project_memory.json)."""
import json
import os
from pathlib import Path

from mneme.cli import main
from mneme.memory_store import MemoryStore


def test_init_creates_default_path(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    exit_code = main(["init"])
    captured = capsys.readouterr().out

    target = tmp_path / ".mneme" / "project_memory.json"
    assert exit_code == 0
    assert target.exists()

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["meta"]["created_by"] == "mneme init"
    assert data["meta"]["name"] == ""
    assert data["meta"]["description"] == ""
    assert data["decisions"] == []
    # Success output should point at the created file.
    assert ".mneme" in captured


def test_init_roundtrips_through_memory_store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    exit_code = main(["init"])
    assert exit_code == 0

    target = tmp_path / ".mneme" / "project_memory.json"
    # The critical validity guarantee: the scaffold must load cleanly.
    store = MemoryStore(target)
    memory = store.load()
    assert store.decisions() == []
    assert memory.items == []
    assert memory.examples == []


def test_init_refuses_existing_file(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / ".mneme" / "project_memory.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    original = '{"sentinel": true}'
    target.write_text(original, encoding="utf-8")

    exit_code = main(["init"])
    captured = capsys.readouterr()

    assert exit_code != 0
    # The existing file must be left untouched.
    assert target.read_text(encoding="utf-8") == original
    # A clear refusal message should be emitted.
    assert "exists" in (captured.out + captured.err).lower()


def test_init_force_overwrites_existing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / ".mneme" / "project_memory.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"sentinel": true}', encoding="utf-8")

    exit_code = main(["init", "--force"])
    assert exit_code == 0

    data = json.loads(target.read_text(encoding="utf-8"))
    assert "sentinel" not in data
    assert data["meta"]["created_by"] == "mneme init"


def test_init_custom_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    custom = tmp_path / "nested" / "custom_memory.json"

    exit_code = main(["init", "--path", str(custom)])
    assert exit_code == 0
    assert custom.exists()

    data = json.loads(custom.read_text(encoding="utf-8"))
    assert data["meta"]["created_by"] == "mneme init"
    # Default location must NOT be created when --path is given.
    assert not (tmp_path / ".mneme" / "project_memory.json").exists()


def test_init_scaffold_passes_check(tmp_path, monkeypatch):
    """A fresh scaffold has no decisions, so `mneme check` exits 0."""
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0

    memory = tmp_path / ".mneme" / "project_memory.json"
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("any prompt text", encoding="utf-8")

    exit_code = main([
        "check",
        "--memory", str(memory),
        "--input", str(prompt),
        "--query", "anything",
    ])
    assert exit_code == 0

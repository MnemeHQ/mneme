"""CLI — add_decision, list_decisions, test_query."""
import json
from pathlib import Path

from mneme.cli import main


def _seed_memory(tmp_path: Path) -> Path:
    mem = tmp_path / "project_memory.json"
    mem.write_text(json.dumps({
        "meta": {"name": "t", "description": "t"},
        "items": [],
        "examples": [],
        "decisions": [
            {
                "id": "seed_001",
                "decision": "Use JSON storage only",
                "rationale": "local-first",
                "scope": ["storage"],
                "constraints": ["no postgres"],
                "anti_patterns": ["introduce ORM"],
                "created_at": "2026-04-24T00:00:00Z",
                "updated_at": "2026-04-24T00:00:00Z",
            }
        ],
    }))
    return mem


def test_list_decisions_shows_seeded(tmp_path, capsys):
    mem = _seed_memory(tmp_path)
    exit_code = main(["list_decisions", "--memory", str(mem)])
    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "seed_001" in captured
    assert "JSON storage" in captured


def test_add_decision_appends_to_file(tmp_path, capsys):
    mem = _seed_memory(tmp_path)
    exit_code = main([
        "add_decision",
        "--memory", str(mem),
        "--id", "new_001",
        "--decision", "Keep retrieval deterministic",
        "--rationale", "Testability.",
        "--scope", "retrieval",
        "--constraint", "no embeddings",
        "--anti-pattern", "add vector db",
    ])
    assert exit_code == 0
    data = json.loads(mem.read_text())
    ids = [d["id"] for d in data["decisions"]]
    assert "new_001" in ids
    new = next(d for d in data["decisions"] if d["id"] == "new_001")
    assert new["scope"] == ["retrieval"]
    assert "no embeddings" in new["constraints"]
    assert "add vector db" in new["anti_patterns"]


def test_test_query_prints_scores(tmp_path, capsys):
    mem = _seed_memory(tmp_path)
    exit_code = main([
        "test_query", "--memory", str(mem), "--query", "should I use postgres?"
    ])
    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "seed_001" in captured
    # Score line must surface some numeric output.
    assert "score" in captured.lower()


def test_test_query_respects_top_n(tmp_path, capsys):
    mem = _seed_memory(tmp_path)
    # Append two more decisions so top-N filtering is observable.
    data = json.loads(mem.read_text())
    data["decisions"].append({
        "id": "seed_002", "decision": "Postgres ops",
        "scope": ["storage"], "constraints": [], "anti_patterns": [],
    })
    data["decisions"].append({
        "id": "seed_003", "decision": "Postgres tuning",
        "scope": ["storage"], "constraints": [], "anti_patterns": [],
    })
    mem.write_text(json.dumps(data))

    exit_code = main([
        "test_query", "--memory", str(mem),
        "--query", "postgres storage",
        "--top", "1",
    ])
    captured = capsys.readouterr().out
    assert exit_code == 0
    # "Injected" section should reference exactly one decision.
    assert captured.count("DECISION [") == 1

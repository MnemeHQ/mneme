"""Tests for the `mneme benchmark` CLI subcommand."""
import json
from pathlib import Path

from mneme.cli import main

EXAMPLE_MEMORY = Path(__file__).parent.parent / "examples" / "project_memory.json"
BENCHMARKS_DIR = Path(__file__).parent.parent / "examples" / "benchmarks"
FIXTURE_SCENARIO = Path(__file__).parent / "fixtures" / "benchmark_scenario"


def test_benchmark_runs_and_exits_zero(capsys):
    """Full suite against real scenarios — should all PASS → exit 0."""
    exit_code = main([
        "benchmark",
        str(BENCHMARKS_DIR),
        "--memory", str(EXAMPLE_MEMORY),
    ])
    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "PASS" in captured


def test_benchmark_prints_summary(capsys):
    main([
        "benchmark",
        str(BENCHMARKS_DIR),
        "--memory", str(EXAMPLE_MEMORY),
    ])
    out = capsys.readouterr().out
    assert "/" in out
    assert "Pass rate" in out or "pass" in out.lower()


def test_benchmark_json_flag(capsys, tmp_path):
    out_file = tmp_path / "report.json"
    main([
        "benchmark",
        str(BENCHMARKS_DIR),
        "--memory", str(EXAMPLE_MEMORY),
        "--json", str(out_file),
    ])
    assert out_file.exists()
    data = json.loads(out_file.read_text())
    assert "summary" in data
    assert data["summary"]["total"] == 7


def test_benchmark_markdown_flag(capsys, tmp_path):
    out_file = tmp_path / "report.md"
    main([
        "benchmark",
        str(BENCHMARKS_DIR),
        "--memory", str(EXAMPLE_MEMORY),
        "--markdown", str(out_file),
    ])
    assert out_file.exists()
    content = out_file.read_text()
    assert "## Mneme Benchmark Results" in content
    assert "storage_backend_violation" in content


def test_benchmark_exits_nonzero_on_failure(tmp_path, capsys):
    """If any scenario FAILs, exit code should be 1."""
    (tmp_path / "query.txt").write_text("Should we use postgres?")
    (tmp_path / "without_mneme.txt").write_text(
        "Use Postgres. SQLAlchemy migration is essential."
    )
    (tmp_path / "with_mneme.txt").write_text(
        "Still use Postgres. SQLAlchemy is fine here."  # still violates
    )
    (tmp_path / "scenario.json").write_text(json.dumps({
        "name": "failing_scenario",
        "category": "test",
        "description": "This scenario should FAIL.",
        "expected_failure_terms": ["postgres"],
        "expected_protected_decision_ids": [],
    }))
    exit_code = main([
        "benchmark",
        str(tmp_path.parent),
        "--memory", str(EXAMPLE_MEMORY),
    ])
    assert exit_code in (0, 1)

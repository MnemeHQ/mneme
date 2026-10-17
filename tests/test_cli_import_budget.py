"""Import budget for the check path (issue #60).

``mneme-hook`` runs ``python -m mneme check`` on every write, so modules only
other subcommands need must not load on that path. Each probe runs in a fresh
interpreter so earlier imports in the test process cannot hide a regression.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "integrations" / "claude_code" / "fixtures" / "project_memory.json"

LAZY_MODULES = (
    "mneme.integrations.eventcatalog",
    "mneme.benchmark",
    "mneme.benchmark_report",
    "mneme.cursor_generator",
    "mneme.decision_add",
    "mneme.decision_authority",
    "mneme.decision_proposal_store",
    "mneme.protection",
    "mneme.readiness",
    "mneme.setup",
    "mneme.setup_state",
)


def _probe(code: str, cwd: Path) -> list:
    script = (
        "import json, sys\n"
        + code
        + f"\nprint(json.dumps([m for m in {list(LAZY_MODULES)!r} if m in sys.modules]), file=sys.stderr)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, cwd=cwd,
        env={**_base_env(), "PYTHONPATH": str(REPO_ROOT)},
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stderr.strip().splitlines()[-1])


def _base_env() -> dict:
    import os

    return {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}


def test_import_cli_does_not_load_subcommand_modules(tmp_path):
    assert _probe("import mneme.cli", tmp_path) == []


@pytest.mark.parametrize("preview", [False, True])
def test_check_run_does_not_load_subcommand_modules(tmp_path, preview):
    mem = tmp_path / ".mneme" / "project_memory.json"
    mem.parent.mkdir()
    mem.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    inp = tmp_path / "proposed.txt"
    inp.write_text("import psycopg2\n", encoding="utf-8")
    argv = [
        "check", "--memory", str(mem), "--input", str(inp),
        "--query", "edit to storage_db.py", "--mode", "strict", "--json",
        "--target-path", str(tmp_path / "storage_db.py"),
    ]
    if preview:
        argv += ["--applicability-preview", "x"]
    code = (
        "import contextlib, io, mneme.cli\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        f"    mneme.cli.main({argv!r})\n"
    )
    assert _probe(code, tmp_path) == []


def test_every_subcommand_help_still_renders(capsys):
    from mneme import cli

    parser = cli._build_parser()
    sub = next(a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction")
    for name in sub.choices:
        with pytest.raises(SystemExit) as exc:
            cli.main([name, "--help"])
        assert exc.value.code == 0, name

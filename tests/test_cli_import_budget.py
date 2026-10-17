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

from tests.canonical_fixtures import canonical_document

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


def _probe(code: str, cwd: Path) -> tuple[list, str]:
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
    *diagnostics, loaded = proc.stderr.strip().splitlines()
    return json.loads(loaded), "\n".join(diagnostics)


def _base_env() -> dict:
    import os

    return {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}


def test_import_cli_does_not_load_subcommand_modules(tmp_path):
    assert _probe("import mneme.cli", tmp_path)[0] == []


@pytest.mark.parametrize("preview", [False, True])
def test_check_run_does_not_load_subcommand_modules(tmp_path, preview):
    mem = tmp_path / ".mneme" / "project_memory.json"
    mem.parent.mkdir()
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if preview:
        # The preview needs a canonical decision_index to reach resolve_effective.
        document = canonical_document(document)
    mem.write_text(json.dumps(document), encoding="utf-8")
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
    loaded, stderr = _probe(code, tmp_path)
    assert loaded == []
    if preview:
        # The preview must actually render (resolve_effective and per-decision
        # lines), not short-circuit to PREVIEW UNAVAILABLE, or a NameError
        # from a lazy import there would be swallowed by its except clause.
        assert "PREVIEW UNAVAILABLE" not in stderr
        assert "NON-AUTHORITATIVE applicability preview (caller-asserted" in stderr
        assert "[test_001] effective (cause=effective;" in stderr


def test_every_subcommand_help_still_renders(capsys):
    from mneme import cli

    parser = cli._build_parser()
    sub = next(a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction")
    for name in sub.choices:
        with pytest.raises(SystemExit) as exc:
            cli.main([name, "--help"])
        assert exc.value.code == 0, name

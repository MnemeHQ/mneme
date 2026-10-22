"""Build and freeze the no-numeric ``mneme check --json`` golden (charter §8.C.5).

Run once against the pre-ADR-034 baseline to freeze the expected bytes:

    python tests/fixtures/numeric_g1/build_legacy_fixture.py --golden

``--golden`` must run with the baseline implementation importable as
``mneme`` (the merge base, before ``FORBID_NUMERIC_ABOVE``). It writes
``no_numeric_golden.json``: the exact stdout and exit code of every scenario.
The regression test replays the same scenarios against the current code and
requires byte identity.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE / "legacy_project"
GOLDEN = HERE / "no_numeric_golden.json"

# (name, argv after --memory, files are relative to the project root)
SCENARIOS: list[tuple[str, list[str]]] = []
for mode in ("strict", "warn"):
    SCENARIOS += [
        (f"pass_{mode}", ["--input", "src/clean.py", "--query", "storage"]),
        (f"global_literal_fail_{mode}", ["--input", "src/global_hit.py", "--query", "install"]),
        (f"scoped_literal_fail_{mode}", ["--input", "src/scoped_hit.py", "--query", "storage"]),
        (f"scoped_excluded_{mode}", ["--input", "docs/scoped_hit.md", "--query", "storage"]),
        (f"anti_pattern_fail_{mode}", ["--input", "src/anti.py", "--query", "storage database"]),
        (f"constraint_warn_{mode}", ["--input", "src/warn.py", "--query", "storage database"]),
        (f"target_path_applied_{mode}", ["--input", "docs/scoped_hit.md", "--target-path", "src/x.py", "--query", "storage"]),
        (f"path_unknown_{mode}", ["--input", "src/scoped_hit.py", "--target-path", "../outside/x.py", "--query", "storage"]),
        (f"path_unknown_with_fail_{mode}", ["--input", "src/global_hit.py", "--target-path", "../outside/x.py", "--query", "install"]),
    ]


def run_scenarios(project: Path) -> dict[str, dict]:
    from mneme.cli import main

    out: dict[str, dict] = {}
    cwd = os.getcwd()
    os.chdir(project)
    try:
        for name, argv in SCENARIOS:
            mode = "warn" if name.endswith("_warn") else "strict"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main([
                    "check", "--memory", ".mneme/project_memory.json",
                    *argv, "--mode", mode, "--json",
                ])
            out[name] = {"exit": code, "stdout": buf.getvalue()}
    finally:
        os.chdir(cwd)
    return out


def main_entry() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", action="store_true")
    args = parser.parse_args()
    import mneme

    print(f"using mneme from {Path(mneme.__file__).parent}", file=sys.stderr)
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "project"
        shutil.copytree(PROJECT, project)
        result = run_scenarios(project)
    if args.golden:
        GOLDEN.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"wrote {GOLDEN}")
    else:
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main_entry())

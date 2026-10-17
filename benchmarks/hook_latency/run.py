#!/usr/bin/env python3
"""PreToolUse latency harness for mneme-hook (issue #60).

Launches the hook as a fresh process per run, as Claude Code does, and times
it end to end for each (scenario x transport) cell, plus two interpreter
baselines. Runs are interleaved round-robin so drift hits every cell equally.
Any run whose exit code differs from the scenario's expected verdict fails
the whole harness: a fast wrong answer is not a result.

    python benchmarks/hook_latency/run.py --python python --runs 50 --warmup 5 \
        --out benchmarks/hook_latency/results/<date>-<os>-<mode>.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "integrations" / "claude_code" / "fixtures" / "project_memory.json"
TARGET_NAME = "storage_db.py"
TRANSPORTS = ("subprocess", "inprocess")
HOOK_CMD = "from mneme.integrations.claude_code.hook import cli_main; cli_main()"
BASELINES = {
    "baseline/python_pass": "pass",
    "baseline/import_hook": "import mneme.integrations.claude_code.hook",
    "baseline/import_cli": "import mneme.integrations.claude_code.hook, mneme.cli",
}


class Scenario(NamedTuple):
    envelope_tool: str
    new_string: str
    expected_exit: int


SCENARIOS: Dict[str, Scenario] = {
    "edit_allowed": Scenario("Write", "import sqlite3\n", 0),
    "edit_blocked": Scenario("Write", "import psycopg2\n", 2),
}


def summarize(samples_ms: List[float]) -> dict:
    if len(samples_ms) >= 2:
        q = statistics.quantiles(samples_ms, n=100, method="inclusive")
        p50, p95 = q[49], q[94]
    else:
        p50 = p95 = samples_ms[0]
    return {
        "n": len(samples_ms),
        "p50": round(p50, 1),
        "p95": round(p95, 1),
        "max": round(max(samples_ms), 1),
        "mean": round(statistics.fmean(samples_ms), 1),
    }


def _env(transport: Optional[str], pythonpath: str) -> Dict[str, str]:
    env = dict(os.environ)
    env.pop("MNEME_HOOK_CHECK_TRANSPORT", None)
    if transport:
        env["MNEME_HOOK_CHECK_TRANSPORT"] = transport
    if pythonpath:
        env["PYTHONPATH"] = pythonpath
    else:
        env.pop("PYTHONPATH", None)
    return env


def _timed(cmd: List[str], cwd: Path, env: Dict[str, str], stdin: str = "") -> Tuple[float, int, str]:
    start = time.perf_counter()
    proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True, cwd=cwd, env=env)
    return (time.perf_counter() - start) * 1000.0, proc.returncode, proc.stderr


# Set by main(); run_once keeps the plan's 4-argument signature.
_PYTHONPATH = str(REPO_ROOT)


def make_project(root: Path) -> Path:
    (root / ".mneme").mkdir(parents=True)
    shutil.copyfile(FIXTURE, root / ".mneme" / "project_memory.json")
    return root


def run_once(python: str, project: Path, scenario: Scenario, transport: str) -> Tuple[float, int, str]:
    target = project / TARGET_NAME
    target.write_text("# placeholder\n", encoding="utf-8")
    envelope = json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": scenario.envelope_tool,
        "cwd": str(project),
        "tool_input": {"file_path": str(target), "content": scenario.new_string},
    })
    return _timed([python, "-c", HOOK_CMD], project, _env(transport, _PYTHONPATH), envelope)


def _describe(python: str) -> dict:
    probe = (
        "import json, platform, sys, mneme; "
        "print(json.dumps({'python_version': sys.version.split()[0], "
        "'platform': platform.platform(), 'mneme_file': mneme.__file__}))"
    )
    out = subprocess.run([python, "-c", probe], capture_output=True, text=True,
                         env=_env(None, _PYTHONPATH), cwd=tempfile.gettempdir())
    info = json.loads(out.stdout) if out.returncode == 0 else {"probe_error": out.stderr[-500:]}
    try:
        info["git_sha"] = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        info["git_sha"] = None
    return info


def _markdown(cells: Dict[str, dict]) -> str:
    lines = ["| cell | p50 ms | p95 ms | max ms |", "|---|---|---|---|"]
    for name, cell in cells.items():
        s = cell["summary"]
        lines.append(f"| {name} | {s['p50']} | {s['p95']} | {s['max']} |")
    for scen in SCENARIOS:
        sub = cells[f"{scen}/subprocess"]["summary"]
        inp = cells[f"{scen}/inprocess"]["summary"]
        lines.append(
            f"| {scen}: inprocess - subprocess | {round(inp['p50'] - sub['p50'], 1)} "
            f"| {round(inp['p95'] - sub['p95'], 1)} | |"
        )
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    global _PYTHONPATH
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--python", required=True, help="interpreter whose mneme install is measured")
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--pythonpath", default=str(REPO_ROOT),
        help="PYTHONPATH for every run; default pins this checkout. Pass '' to measure the "
             "interpreter's own install (wheel mode).",
    )
    args = ap.parse_args(argv)
    _PYTHONPATH = args.pythonpath

    cells: List[Tuple[str, Optional[Scenario], Optional[str]]] = [
        (f"{s}/{t}", SCENARIOS[s], t) for s in SCENARIOS for t in TRANSPORTS
    ] + [(name, None, None) for name in BASELINES]
    samples: Dict[str, List[float]] = {name: [] for name, _, _ in cells}

    with tempfile.TemporaryDirectory(prefix="mneme-hook-bench-") as tmp:
        project = make_project(Path(tmp) / "project")
        for i in range(args.warmup + args.runs):
            for name, scenario, transport in cells:
                if scenario is None:
                    ms, rc, err = _timed([args.python, "-c", BASELINES[name]], project,
                                         _env(None, _PYTHONPATH))
                    expected = 0
                else:
                    ms, rc, err = run_once(args.python, project, scenario, transport)
                    expected = scenario.expected_exit
                if rc != expected:
                    print(f"FAIL {name} run {i}: exit {rc}, expected {expected}\n{err[-2000:]}",
                          file=sys.stderr)
                    return 1
                if i >= args.warmup:
                    samples[name].append(ms)

    result = {
        **_describe(args.python),
        "settings": {"runs": args.runs, "warmup": args.warmup, "python": args.python,
                     "pythonpath": args.pythonpath},
        "cells": {name: {"summary": summarize(s), "samples_ms": [round(x, 2) for x in s]}
                  for name, s in samples.items()},
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(_markdown(result["cells"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

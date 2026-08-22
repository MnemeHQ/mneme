"""Runnable governed-loop demo: Mneme x claude_agent_sdk (PR #293).

Reproduces, in one script, the exact loop proven live in PR #293:

    1. GUIDANCE      relevant decisions are retrieved and injected
                     before any work starts.
    2. ENFORCEMENT   a proposed file mutation is evaluated by the same
                     `mneme check` path the Claude Code hook uses.
    3. CORRECTION    a blocked proposal carries the governing decision
                     back to the caller; the corrected proposal passes.
                     Deterministic mode scripts both proposals; --live
                     mode lets the model perform the correction from
                     the block reason.

Two modes:

  python run.py            deterministic mode - no model, no network.
                           The proposed contents are fixed strings and
                           every verdict comes from real `mneme check`
                           runs against the isolated memory in this
                           folder.

  python run.py --live     live mode - drives a real model session via
                           the official claude_agent_sdk package with
                           MnemeAgentSdk hooks installed. Requires that
                           package (import name `claude_agent_sdk`;
                           the PyPI distribution spells the name with
                           hyphens - see that project's install docs),
                           a working `claude` CLI login, and network.

The decision corpus here is isolated example data. It is NOT the
canonical `.mneme/project_memory.json` of this repository.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

from mneme.integrations.agent_sdk import ACTION_ALLOW, ACTION_DENY, MnemeAgentSdk

TASK = "Add database persistence to the service"

VIOLATING_DB_PY = (
    '"""Persistence module."""\n\n'
    "import psycopg2\n\n"
    'conn = psycopg2.connect("dbname=app")\n'
)

COMPLIANT_DB_PY = (
    '"""Persistence module."""\n\n'
    "import sqlite3\n\n"
    'DB_PATH = "app.db"\n\n'
    "conn = sqlite3.connect(DB_PATH)\n"
)


def prepare_workdir(base: Path) -> Path:
    """Materialize an isolated project governed by the demo memory."""
    work = base / "demo-project"
    (work / ".mneme").mkdir(parents=True, exist_ok=True)
    memory = Path(__file__).parent / "project_memory.json"
    (work / ".mneme" / "project_memory.json").write_text(
        memory.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return work


def show_guidance(gated: MnemeAgentSdk) -> None:
    injection = gated.context_for_task(TASK)
    print("=" * 64)
    print("1. GUIDANCE - decisions injected before work")
    print("=" * 64)
    print(f"   query        : {TASK}")
    print(f"   injected ids : {injection.decision_ids}")
    print(f"   memory       : {injection.memory_path}")
    print()
    print(injection.text or "   (no decisions above the relevance floor)")
    print()


def show_enforcement(label: str, result) -> None:
    print("-" * 64)
    print(label)
    print(f"   action       : {result.action.upper()}")
    if result.reason:
        for line in result.reason.splitlines():
            print(f"   {line}")
    print()


def run_deterministic() -> int:
    base = Path(tempfile.mkdtemp(prefix="mneme-loop-demo-"))
    work = prepare_workdir(base)
    gated = MnemeAgentSdk(project_dir=work)

    show_guidance(gated)

    print("=" * 64)
    print("2. ENFORCEMENT + 3. CORRECTION PATH")
    print("   task: add database persistence; the first proposal uses")
    print("   a forbidden server database driver.")
    print("=" * 64)
    print()

    first = gated.evaluate_mutation(
        "Write",
        {"file_path": str(work / "db.py"), "content": VIOLATING_DB_PY},
        cwd=str(work),
    )
    show_enforcement("proposal 1: psycopg2 driver", first)

    second = gated.evaluate_mutation(
        "Write",
        {"file_path": str(work / "db.py"), "content": COMPLIANT_DB_PY},
        cwd=str(work),
    )
    show_enforcement("proposal 2: stdlib sqlite3 (corrected)", second)

    print("=" * 64)
    ok = first.action == ACTION_DENY and second.action == ACTION_ALLOW
    print(f"RESULT: {'OK' if ok else 'UNEXPECTED'} (deny -> correct -> allow)")
    print(f"workdir: {base}")
    return 0 if ok else 1


def run_live() -> int:
    try:
        from claude_agent_sdk import ClaudeAgentOptions, query
    except ImportError:
        print(
            "live mode requires the official package (import name "
            "claude_agent_sdk); see that project's install docs.",
            file=sys.stderr,
        )
        return 2

    base = Path(tempfile.mkdtemp(prefix="mneme-loop-demo-live-"))
    work = prepare_workdir(base)
    gated = MnemeAgentSdk(project_dir=work)

    options = ClaudeAgentOptions(
        cwd=str(work),
        hooks=gated.hooks(),
        permission_mode="acceptEdits",
        max_turns=10,
    )
    prompt = (
        f"{TASK}. Use the Write tool to create db.py in the current working "
        "directory using exactly the relative path db.py. If the Write tool "
        "is blocked, follow the block reason and immediately write a "
        "compliant db.py instead."
    )

    async def drive() -> None:
        async for _message in query(prompt=prompt, options=options):
            pass  # transcript printing left to the embedding application

    asyncio.run(drive())

    print(json.dumps(gated.trace, indent=2))
    final = work / "db.py"
    text = final.read_text(encoding="utf-8") if final.exists() else ""
    denied = [e for e in gated.trace if e.get("action") == ACTION_DENY]
    allowed = [e for e in gated.trace if e.get("action") == ACTION_ALLOW]
    compliant = "psycopg2" not in text
    ok = bool(denied) and bool(allowed) and compliant
    print(
        f"RESULT: {'OK' if ok else 'INCOMPLETE'} "
        f"(denied={len(denied)}, allowed={len(allowed)}, compliant={compliant})"
    )
    print(f"workdir: {base}")
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="drive a real model session")
    args = parser.parse_args()
    sys.exit(run_live() if args.live else run_deterministic())

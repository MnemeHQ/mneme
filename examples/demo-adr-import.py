"""
demo-adr-import.py -- End-to-end walkthrough of `mneme adr import`.

Demonstrates importing Mneme's own architectural decisions as enforceable
AI coding guardrails. The walkthrough runs three stages:

  1. Dry-run preview   -- shows what would be imported, without writing
  2. Apply             -- imports active ADRs into a fresh memory file
  3. Enforcement check -- runs `mneme check` against a namespace violation
                          so ADR-005 fires on the wrong import path

Usage (from the repository root):

    python examples/demo-adr-import.py

No API key required -- the enforcement check runs locally.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
ADR_DIR = HERE / "mneme-own-adrs"
BASE_MEMORY = HERE / "demo-adr-import-base.json"
WIDTH = 72


def _rule(char: str = "=") -> str:
    return char * WIDTH


def _header(text: str) -> None:
    print()
    print(_rule())
    print(f"  {text}")
    print(_rule())
    print()


def _step(n: int, text: str) -> None:
    print()
    print(f"-- Step {n}: {text}")
    print(_rule("-"))
    print()


def _run(args: list[str]) -> int:
    """Print the command, flush, run it, stream output, return exit code."""
    cmd_str = " ".join(str(a) for a in args)
    print(f"  $ {cmd_str}")
    print()
    sys.stdout.flush()
    result = subprocess.run(args, capture_output=False)
    sys.stdout.flush()
    return result.returncode


def main() -> None:
    _header("mneme adr import -- walkthrough")
    print("  Source:  Mneme's own architectural decisions (4 ADRs)")
    print("  Target:  fresh memory file (demo-adr-import-base.json)")
    print("  Goal:    import -> apply -> enforce a namespace constraint")

    # ── Step 1: Show the ADR corpus ──────────────────────────────────────────
    _step(1, "ADR corpus")
    adrs = sorted(ADR_DIR.glob("*.md"))
    for adr in adrs:
        print(f"  {adr.name}")
    print()
    print(f"  {len(adrs)} ADR(s) found in {ADR_DIR.relative_to(HERE.parent)}")

    # ── Step 2: Dry-run preview ──────────────────────────────────────────────
    _step(2, "Preview (dry-run -- no writes)")
    _run([
        sys.executable, "-m", "mneme", "adr", "import",
        str(ADR_DIR),
        "--memory", str(BASE_MEMORY),
        "--dry-run",
    ])

    # ── Step 3: Apply import into a temp memory file ─────────────────────────
    _step(3, "Apply import")
    tmp_dir = Path(tempfile.mkdtemp(prefix="mneme-demo-"))
    result_memory = tmp_dir / "demo-memory.json"
    shutil.copy(BASE_MEMORY, result_memory)

    try:
        exit_code = _run([
            sys.executable, "-m", "mneme", "adr", "import",
            str(ADR_DIR),
            "--memory", str(result_memory),
            "--apply",
        ])
        if exit_code != 0:
            print(f"  Import exited with code {exit_code} -- aborting demo.")
            return

        # Show a summary of what was written.
        raw = json.loads(result_memory.read_text(encoding="utf-8"))
        decisions = raw.get("decisions", [])
        print(f"  {len(decisions)} decision(s) written to memory:")
        for d in decisions:
            constraint_count = len(d.get("constraints", []))
            suffix = f"  [{constraint_count} constraint(s)]" if constraint_count else ""
            print(f"    {d['id']}  {d['decision']}{suffix}")

        # ── Step 4: Enforcement check ────────────────────────────────────────
        _step(4, "Enforcement -- ADR-005 namespace violation")
        print("  Creating agent-output.py with a forbidden import path:")
        print()
        print("    from MnemeHQ.memory_store import MemoryStore   # wrong namespace")
        print("    from MnemeHQ.retriever import DecisionRetriever")
        print()
        print("  ADR-005 forbids `MnemeHQ` -- the package is `mneme`, not `MnemeHQ`.")
        print()

        violation_file = tmp_dir / "agent-output.py"
        violation_file.write_text(
            "# Agent-generated code -- incorrect package namespace\n"
            "from MnemeHQ.memory_store import MemoryStore\n"
            "from MnemeHQ.retriever import DecisionRetriever\n"
            "\n"
            "store = MemoryStore('project_memory.json')\n"
            "retriever = DecisionRetriever(store.decisions())\n",
            encoding="utf-8",
        )

        _run([
            sys.executable, "-m", "mneme", "check",
            "--memory", str(result_memory),
            "--input", str(violation_file),
            "--query", "Python package imports code namespace",
            "--mode", "warn",
        ])

        # ── Step 5: Clean input (PASS) ───────────────────────────────────────
        _step(5, "Enforcement -- correct namespace (PASS expected)")
        print("  Creating agent-output-clean.py with the correct import path:")
        print()
        print("    from mneme.memory_store import MemoryStore   # correct")
        print()

        clean_file = tmp_dir / "agent-output-clean.py"
        clean_file.write_text(
            "# Agent-generated code -- correct package namespace\n"
            "from mneme.memory_store import MemoryStore\n"
            "from mneme.retriever import Retriever\n"
            "\n"
            "store = MemoryStore('project_memory.json')\n",
            encoding="utf-8",
        )

        _run([
            sys.executable, "-m", "mneme", "check",
            "--memory", str(result_memory),
            "--input", str(clean_file),
            "--query", "Python package imports code namespace",
            "--mode", "warn",
        ])

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # ── Summary ──────────────────────────────────────────────────────────────
    print()
    print(_rule())
    print("  Done.")
    print()
    print("  What just happened:")
    print("    1. Parsed 4 Mneme ADRs with YAML frontmatter")
    print("    2. Compiled active decisions (proposed/deprecated excluded)")
    print("    3. Extracted ## Constraints directives -> enforcement strings")
    print("    4. Imported decisions into memory atomically")
    print("    5. ADR-005 fired WARN on 'MnemeHQ' import path")
    print("    6. Correct 'mneme' import path passed cleanly")
    print()
    print("  The same guardrail runs before every AI code generation step.")
    print("  Commit fdcdb0a -- https://github.com/TheoV823/mneme")
    print(_rule())


if __name__ == "__main__":
    main()

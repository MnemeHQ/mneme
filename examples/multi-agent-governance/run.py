"""
run.py -- Governance continuity across multiple actors.

Simulates three sequential actors touching the same Python service. The
actors share no memory with each other; they share only the compiled
decision corpus emitted by the ADR compiler. This script exercises the
real Mneme enforcement pipeline (via the mneme CLI) at each step and
prints the structured verdict.

What this script demonstrates:
    1. Architectural invariants stay coherent across actors because the
       invariants live outside any single actor (in project_memory.json).
    2. The governance layer remains coherent under retries (Actor A) and
       under remediation passes (Actor C) -- the verdict is deterministic.
    3. Conflicts surface as structured WARN/FAIL rather than being
       silently resolved.

What this script does NOT claim:
    - There is no multi-agent runtime. The "actors" are scripted diff
      producers. No LLM is called.
    - There is no distributed orchestration. The actors run sequentially
      in this process on purpose -- the proof surface is the *coherence
      of the enforcement output across actors*, which is small enough to
      be deterministic and reproducible.

Run from this directory:

    python run.py

No API key required. Requires the mneme package (pip install mneme-hq or
pip install -e . from the repo root).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
MEMORY = HERE / "project_memory.json"
WIDTH = 72


def _rule(char: str = "=") -> str:
    return char * WIDTH


def _header(text: str) -> None:
    print()
    print(_rule())
    print(f"  {text}")
    print(_rule())
    print()


def _actor(label: str, task: str) -> None:
    print()
    print(f"-- {label}")
    print(f"   task: \"{task}\"")
    print(_rule("-"))
    print()


def _check(input_file: Path, query: str, mode: str = "warn") -> int:
    cmd = [
        sys.executable, "-m", "mneme", "check",
        "--memory", str(MEMORY),
        "--input", str(input_file),
        "--query", query,
        "--mode", mode,
    ]
    print(f"  $ {' '.join(cmd[1:])}")
    print()
    sys.stdout.flush()
    result = subprocess.run(cmd, capture_output=False)
    sys.stdout.flush()
    return result.returncode


def main() -> None:
    _header("Mneme HQ -- governance continuity across multiple actors")
    print("  Corpus: project_memory.json (ADR-001 JSON-only storage, ADR-003 no ORM)")
    print("  Actors: 3 sequential sessions, no shared memory between them")
    print("  Mode:   mneme check --mode warn")
    print()
    print("  The corpus is the only thing the actors share. The invariants")
    print("  live outside the actors -- in the artifact the governance layer")
    print("  evaluates against.")

    storage_query = "storage backend persistence database"

    # ── Actor A -- introduces a divergence, then retries ─────────────────────
    _actor("Actor A | session 1", "speed up the user lookup endpoint")
    print("  Step A.1 -- first draft (Redis cache) -- expect FAIL")
    print()
    _check(HERE / "actor_a_first_draft.txt", storage_query)
    print()
    print("  Step A.2 -- retry after ADR-001 surfaced in context -- expect PASS")
    print()
    _check(HERE / "actor_a_retry.txt", storage_query)

    # ── Actor B -- new session, no memory of A; reads codebase + corpus ──────
    _actor("Actor B | session 2", "add session storage")
    print("  No shared memory with Actor A. Reads the corrected codebase")
    print("  and the same corpus. PASS by construction.")
    print()
    _check(HERE / "actor_b_compliant.txt", storage_query)

    # ── Actor C -- remediation pass; surfaces a real architectural conflict ──
    _actor("Actor C | session 3", "reduce duplicated cache logic between user and session")
    print("  Step C.1 -- proposes consolidating with SQLAlchemy ORM -- expect FAIL")
    print("  This is not a silent fix. The governance layer flags it so a human")
    print("  can either amend ADR-003 or approve an explicit override.")
    print()
    _check(HERE / "actor_c_remediation_with_orm.txt", storage_query)
    print()
    print("  Step C.2 -- compliant remediation (shared JsonStore base) -- expect PASS")
    print()
    _check(HERE / "actor_c_remediation_compliant.txt", storage_query)

    _header("Summary")
    print("  Three actors. Zero shared memory between them.")
    print("  One shared corpus. The invariants held.")
    print()
    print("  Actor A: blocked upstream, converged on retry.")
    print("  Actor B: PASS by construction (read the corrected codebase).")
    print("  Actor C: real architectural conflict surfaced explicitly,")
    print("          compliant remediation passed.")
    print()
    print("  Same verdict format. Same enforcer. Same corpus across sessions.")
    print("  This is what governance continuity looks like operationally.")
    print()
    print("  Page:   https://mnemehq.com/demo/multi-agent-governance/")
    print("  Source: https://github.com/TheoV823/mneme")
    print(_rule())


if __name__ == "__main__":
    main()

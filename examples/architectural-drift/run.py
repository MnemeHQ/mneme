"""
run.py -- Architectural drift prevention walkthrough.

Simulates a three-step timeline of agent-produced changes against a small
JSON-only service. Each step prints what would happen in a no-governance
world, then exercises the real Mneme enforcement pipeline (via the
mneme CLI) and prints the structured verdict.

What this script proves:
    1. Without a governance layer, every agent's proposal is locally
       reasonable and the system drifts.
    2. With Mneme, the first divergence is blocked before it lands,
       the retry converges within constraints, and downstream agents
       build on the corrected codebase by construction.

What this script does NOT claim:
    - There is no LLM call. The "agent" diffs are fixture text files.
    - The orchestration is sequential and scripted on purpose; the
      proof surface is the *enforcement coherence*, not the agents.

Run from this directory:

    python run.py

No API key required. Requires the mneme package (pip install -e
../../mneme-project-memory or pip install mneme).
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


def _step(label: str, text: str) -> None:
    print()
    print(f"-- {label}: {text}")
    print(_rule("-"))
    print()


def _check(input_file: Path, query: str, mode: str = "warn") -> int:
    """Run `mneme check` on input_file. Returns the CLI exit code."""
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


def _without_governance_timeline() -> None:
    _header("Without a governance layer -- drift propagation")

    print("  No hook. No CI gate. Each agent's diff is reviewed in isolation.")
    print("  This block does not run the enforcer -- it shows what would happen.")
    print()

    print("  Monday  | Agent A  | 'speed up user lookup'")
    print("          |          | --> adds redis-py, wires a cache layer")
    print("          |          | --> 60-line PR, approved in 4 minutes")
    print("          | Verdict  | (no check ran)")
    print()
    print("  Wed     | Agent B  | 'add session storage'")
    print("          |          | --> sees Redis present, uses it")
    print("          |          | --> adds connection pooling, health checks")
    print("          | Verdict  | (no check ran)")
    print()
    print("  Thursday| Agent C  | 'make staging reproducible'")
    print("          |          | --> generates Redis container + backup yaml")
    print("          | Verdict  | (no check ran)")
    print()
    print("  Friday  | Architect notices. ADR-001 silently dead.")
    print("          | Remediation cost: 3 reverts + meeting + ADR rewrite.")


def _with_governance_timeline() -> None:
    _header("With Mneme -- upstream block + retry convergence")

    print("  Same agents. Same prompts. Every proposed diff is evaluated")
    print("  against the same project_memory.json before it lands.")
    print()

    # Same retrieval query for every step. Mirrors how the editor hook
    # works in practice: the storage/backend scope is implicit context,
    # not something the agent's prompt has to articulate.
    storage_query = "storage backend persistence database"

    # Step 1 -- Agent A first draft (Redis): expect FAIL
    _step("Step 1", "Agent A's first draft (Redis cache) -- expect FAIL")
    _check(
        HERE / "agent_a_redis_cache.txt",
        query=storage_query,
        mode="warn",
    )

    # Step 2 -- Agent A retry (in-process memo): expect PASS
    _step("Step 2", "Agent A's retry after ADR-001 injection -- expect PASS")
    _check(
        HERE / "agent_a_retry_json_cache.txt",
        query=storage_query,
        mode="warn",
    )

    # Step 3 -- Agent B with governance (built on the JSON store): expect PASS
    _step("Step 3", "Agent B's session storage (built on JsonStore) -- expect PASS")
    _check(
        HERE / "agent_b_session_repository.txt",
        query=storage_query,
        mode="warn",
    )

    # Step 4 -- For contrast, what Agent B would have produced without
    # governance (Redis): expect FAIL
    _step(
        "Step 4 (contrast)",
        "Agent B's would-be diff without governance (Redis) -- expect FAIL",
    )
    _check(
        HERE / "agent_b_session_redis.txt",
        query=storage_query,
        mode="warn",
    )


def main() -> None:
    _header("Mneme HQ -- architectural drift prevention demo")
    print("  Memory: project_memory.json (ADR-001 JSON-only storage, ADR-003 no ORM)")
    print("  Inputs: 4 fixture diffs simulating three sequential agents")
    print("  Mode:   mneme check --mode warn")

    _without_governance_timeline()
    _with_governance_timeline()

    _header("Summary")
    print("  Same corpus on disk for both timelines.")
    print("  Without governance: 3 silently-violating PRs land.")
    print("  With governance: first divergence blocked, retry converges,")
    print("                   downstream agents build on the correct primitive.")
    print()
    print("  Page:   https://mnemehq.com/demo/architectural-drift/")
    print("  Source: https://github.com/TheoV823/mneme")
    print(_rule())


if __name__ == "__main__":
    main()

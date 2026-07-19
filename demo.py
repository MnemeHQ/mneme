"""
demo.py — Before/after demonstration of Mneme context injection.

For each task the demo runs two LLM calls:
  1. BASELINE  — the question alone, no project context
  2. WITH MNEME — the same question with a full ContextPacket injected

Seeing both responses side by side shows what Mneme adds: the model
stops giving generic advice and starts reasoning from your project's
actual decisions.

Usage
-----
    python demo.py                       # all tasks, live API
    python demo.py --task task-001       # single task
    python demo.py --dry-run             # print prompts, skip API calls
    python demo.py --context-only        # show context packet, skip LLM

If ANTHROPIC_API_KEY is not set, dry-run activates automatically.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from mneme.context_builder import format_context_packet
from mneme.evaluator import Evaluator
from mneme.llm_adapter import LLMAdapter
from mneme.memory_store import MemoryStore
from mneme.retriever import Retriever

MEMORY_FILE = Path("examples/project_memory.json")
TASKS_FILE = Path("examples/demo_tasks.json")

# Column width for printed output.
WIDTH = 72


# ── Display helpers ───────────────────────────────────────────────────────────

def _rule(char: str = "=", width: int = WIDTH) -> str:
    return char * width


def _header(text: str, char: str = "=") -> None:
    print()
    print(_rule(char))
    print(f"  {text}")
    print(_rule(char))


def _section(label: str) -> None:
    print()
    print(label)
    print("-" * len(label))


def _print_response(content: str) -> None:
    """Print a response with consistent indentation."""
    for line in content.splitlines():
        print(f"  {line}")


def _context_summary(packet) -> str:
    """Return a one-line summary of what was injected."""
    rules = len(packet.hard_constraints) + len(packet.preferred_patterns)
    facts = len(packet.relevant_facts)
    examples = len(packet.decision_examples)
    return f"{rules} rules, {examples} examples, {facts} context items"


# ── Core task runner ──────────────────────────────────────────────────────────

def run_task(
    task: dict,
    adapter: LLMAdapter,
    retriever: Retriever,
    evaluator: Evaluator,
    context_only: bool,
) -> None:
    """Run one before/after comparison and print the results.

    Args:
        task:         Task dict with id, title, question, and query fields.
        adapter:      LLMAdapter (may be in dry-run mode).
        retriever:    Retriever loaded with project memory.
        context_only: If True, print the context packet and skip LLM calls.
    """
    _header(f"TASK [{task['id']}]  {task['title']}")
    print()
    print(f"  Question: {task['question']}")

    # Build the context packet for this task.
    packet = retriever.retrieve(task["query"])
    system_prompt = format_context_packet(packet)

    if context_only:
        _section("MNEME CONTEXT PACKET")
        print(f"  ({_context_summary(packet)})")
        print()
        for line in system_prompt.splitlines():
            print(f"  {line}")
        return

    # ── BASELINE: no context ──────────────────────────────────────────────

    _section("WITHOUT MNEME")
    baseline = adapter.complete(user=task["question"])
    _print_response(baseline.content)
    if baseline.usage.get("input"):
        print(f"\n  [{baseline.usage['input']} in / {baseline.usage['output']} out tokens]")

    # ── WITH MNEME: context injected ──────────────────────────────────────

    _section(f"WITH MNEME  ({_context_summary(packet)})")
    enhanced = adapter.complete(user=task["question"], system=system_prompt)
    _print_response(enhanced.content)
    if enhanced.usage.get("input"):
        print(f"\n  [{enhanced.usage['input']} in / {enhanced.usage['output']} out tokens]")

    # ── MNEME ALIGNMENT ──────────────────────────────────────────────────
    # Skip in dry-run: the stub response contains the prompt text, which
    # would trigger false violations on every injected keyword.

    if adapter.dry_run:
        _section("MNEME ALIGNMENT")
        print("  [skipped in dry-run mode]")
        return

    result = evaluator.evaluate(enhanced, packet)
    _section(f"MNEME ALIGNMENT  score: {result.alignment_score:.2f}")
    if result.matched_rules:
        for match in result.matched_rules:
            print(f"  [OK]   {match}")
    if result.missed_rules:
        for miss in result.missed_rules:
            print(f"  [MISS] {miss}")
    print()
    print(f"  {result.explanation}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mneme before/after demo — show how context injection changes LLM answers."
    )
    parser.add_argument(
        "--task",
        metavar="ID",
        help="Run only the task with this ID (e.g. task-001).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prompt payloads instead of calling the API.",
    )
    parser.add_argument(
        "--context-only",
        action="store_true",
        help="Print the Mneme context packet for each task and exit.",
    )
    args = parser.parse_args()

    # Auto-enable dry-run when no API key is present.
    dry_run = args.dry_run or not bool(os.environ.get("ANTHROPIC_API_KEY"))
    if dry_run and not args.dry_run:
        print("Note: ANTHROPIC_API_KEY not set — running in dry-run mode.")
        print("      Set the key in .env to run live comparisons.\n")

    # Load memory.
    store = MemoryStore(MEMORY_FILE)
    memory = store.load()
    print(
        f"Loaded {len(memory.items)} memory items + {len(memory.examples)} decision examples"
        f" for '{memory.meta.name}'."
    )

    # Load tasks.
    tasks: list[dict] = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    if args.task:
        tasks = [t for t in tasks if t["id"] == args.task]
        if not tasks:
            sys.exit(f"No task with ID '{args.task}' in {TASKS_FILE}.")

    retriever = Retriever(memory)
    adapter = LLMAdapter(dry_run=dry_run)
    evaluator = Evaluator()

    for task in tasks:
        run_task(task, adapter, retriever, evaluator, context_only=args.context_only)

    print()
    print(_rule())
    print(f"  Done. Ran {len(tasks)} task(s).")
    print(_rule())


if __name__ == "__main__":
    main()

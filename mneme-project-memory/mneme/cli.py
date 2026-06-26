"""
cli.py — Command-line interface for Mneme.

Subcommands
-----------
  init              Scaffold an empty project_memory.json.
  add_decision      Append a new Decision to a project_memory.json file.
  list_decisions    Print every Decision in the memory file.
  test_query        Run a query through the retriever and show scores + injected.
  cursor generate   Generate a Cursor .mdc rules file from retrieved decisions.

Usage::

    mneme init
    mneme list_decisions --memory examples/project_memory.json
    mneme add_decision --memory examples/project_memory.json \\
        --id mneme_042 --decision "Use JSON" --scope storage \\
        --constraint "no postgres"
    mneme test_query --memory examples/project_memory.json \\
        --query "should I add postgres?"
    mneme cursor generate --memory examples/project_memory.json \\
        --query "working on storage layer" --output .cursor/rules/mneme.mdc

All writes go directly to the JSON file. The Pipeline runtime is never
mutated — add_decision is a file operation only.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from mneme.adr_freshness import FreshnessIssue, check_freshness
from mneme.adr_import import (
    apply_import,
    compile_for_import,
    detect_collisions,
    format_preview,
)
from mneme.benchmark import BenchmarkRunner, ScenarioVerdict
from mneme.benchmark_report import format_json, format_markdown, format_terminal
from mneme.context_builder import DEFAULT_MAX_DECISIONS, format_decisions
from mneme.cursor_generator import generate_mdc
from mneme.decision_retriever import DecisionRetriever
from mneme.enforcer import Severity, check_prompt
from mneme.memory_store import MemoryStore


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Subcommand: init ─────────────────────────────────────────────────────────

DEFAULT_MEMORY_PATH = ".mneme/project_memory.json"


def _scaffold_memory() -> dict:
    """Return a valid, empty, neutral project_memory.json skeleton.

    No seeded decisions: every decision is enforceable, so sample content
    would create phantom rules. The empty arrays let MemoryStore.load()
    round-trip the file and let `mneme check` run cleanly (nothing to
    enforce). meta.name and meta.description are the only fields the loader
    requires; created_by and project are recorded for provenance.
    """
    return {
        "meta": {
            "name": "",
            "description": "",
            "project": "",
            "created_by": "mneme init",
            "created": _utc_now(),
        },
        "items": [],
        "examples": [],
        "decisions": [],
    }


def _cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if path.exists() and not args.force:
        print(
            f"ERROR: {path} already exists. Use --force to overwrite.",
            flush=True,
        )
        return 1

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_scaffold_memory(), indent=2) + "\n", encoding="utf-8")

    print(f"Created {path}")
    print()
    print("Next steps:")
    print(f"  mneme add_decision --memory {path} \\")
    print('      --id my_001 --decision "..." --scope <area> --constraint "..."')
    print(f"  mneme check --memory {path} --input <file> --query <context>")
    return 0


# ── Subcommand: list_decisions ───────────────────────────────────────────────

def _cmd_list(args: argparse.Namespace) -> int:
    store = MemoryStore(args.memory)
    store.load()
    decisions = store.decisions()
    if not decisions:
        print("(no decisions)")
        return 0
    for d in decisions:
        print(f"[{d.id}] {d.decision}")
        if d.scope:
            print(f"    scope: {', '.join(d.scope)}")
        if d.constraints:
            print(f"    constraints: {', '.join(d.constraints)}")
        if d.anti_patterns:
            print(f"    avoid: {', '.join(d.anti_patterns)}")
    return 0


# ── Subcommand: add_decision ─────────────────────────────────────────────────

def _cmd_add(args: argparse.Namespace) -> int:
    path = Path(args.memory)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("decisions", [])

    now = _utc_now()
    new_entry = {
        "id": args.id,
        "decision": args.decision,
        "rationale": args.rationale or "",
        "scope": list(args.scope or []),
        "constraints": list(args.constraint or []),
        "anti_patterns": list(args.anti_pattern or []),
        "created_at": now,
        "updated_at": now,
    }
    if any(d.get("id") == args.id for d in data["decisions"]):
        print(f"ERROR: decision id '{args.id}' already exists", flush=True)
        return 2

    data["decisions"].append(new_entry)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Added decision [{args.id}]")
    return 0


# ── Subcommand: test_query ───────────────────────────────────────────────────

def _cmd_test(args: argparse.Namespace) -> int:
    store = MemoryStore(args.memory)
    store.load()
    retriever = DecisionRetriever(store.decisions())
    scored = retriever.retrieve(args.query)

    print(f"Query: {args.query}")
    print()
    print("All decisions (ranked by score):")
    for s in scored:
        matched_fields = [f for f, n in s.matches.items() if n > 0]
        reason = ", ".join(matched_fields) if matched_fields else "(no match)"
        print(f"  [{s.decision.id}] score={s.score:.2f} matched={reason}")

    print()
    print(f"Injected (top {args.top}):")
    print(format_decisions(scored, max_items=args.top) or "(none)")
    return 0


# ── Subcommand: check ────────────────────────────────────────────────────────

_EXIT_CODES_BY_MODE: dict[str, dict[Severity, int]] = {
    "strict": {Severity.PASS: 0, Severity.WARN: 1, Severity.FAIL: 2},
    "warn":   {Severity.PASS: 0, Severity.WARN: 0, Severity.FAIL: 0},
}


def _cmd_check(args: argparse.Namespace) -> int:
    input_text = Path(args.input).read_text(encoding="utf-8")

    store = MemoryStore(args.memory)
    store.load()
    retriever = DecisionRetriever(store.decisions())
    scored = retriever.retrieve(args.query)

    result = check_prompt(input_text, scored, top=args.top)

    if result.violations:
        for v in result.violations:
            kind = "anti_pattern" if v.severity == Severity.FAIL else "constraint"
            print(f"{v.severity.value:4}  [{v.decision_id}] {kind} \"{v.rule}\" -- trigger: {v.trigger}")
            print(f"      {v.decision_text}")
        print()

    # ADR freshness diagnostics are warn-only: they print to stdout but
    # never influence the exit code. Skipped silently when adr_dir is
    # absent so existing CLI output is unchanged for projects that do
    # not use ADRs.
    freshness = check_freshness(memory_path=args.memory, adr_dir=args.adr_dir)
    if freshness:
        for issue in freshness:
            _print_freshness_issue(issue)
        print()

    print(f"Result: {result.verdict.value}")
    return _EXIT_CODES_BY_MODE[args.mode][result.verdict]


def _print_freshness_issue(issue: FreshnessIssue) -> None:
    """Render one freshness diagnostic with a distinct ``ADR_*`` token.

    Format is intentionally different from enforcement violations so
    operators can grep ``mneme check`` output without ambiguity.
    """
    print(f"WARN  {issue.code:15}  [{issue.adr_id}] {issue.message}")
    if issue.path:
        print(f"      source: {issue.path}")


# ── Subcommand: cursor generate ──────────────────────────────────────────────

def _cmd_cursor_generate(args: argparse.Namespace) -> int:
    store = MemoryStore(args.memory)
    store.load()
    retriever = DecisionRetriever(store.decisions())
    scored = retriever.retrieve(args.query)

    mdc = generate_mdc(
        scored=scored,
        query=args.query,
        memory_path=args.memory,
        top=args.top,
        timestamp=_utc_now(),
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(mdc, encoding="utf-8")
    print(f"Written: {output}")
    return 0


# ── Subcommand: benchmark ────────────────────────────────────────────────────

def _cmd_benchmark(args: argparse.Namespace) -> int:
    """Run all benchmark scenarios in a directory and report results."""
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    benchmarks_dir = Path(args.benchmarks_dir)
    if not benchmarks_dir.is_dir():
        print(f"ERROR: {benchmarks_dir} is not a directory", flush=True)
        return 2

    store = MemoryStore(args.memory)
    store.load()
    runner = BenchmarkRunner(store)

    results = runner.run_suite(benchmarks_dir)
    if not results:
        print("No benchmark scenarios found.")
        return 0

    print(format_terminal(results))

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(format_json(results), encoding="utf-8")
        print(f"JSON report written: {args.json}")

    if args.markdown:
        out = Path(args.markdown)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(format_markdown(results), encoding="utf-8")
        print(f"Markdown report written: {args.markdown}")

    has_failures = any(r.verdict == ScenarioVerdict.FAIL for r in results)
    return 1 if has_failures else 0


# ── Subcommand: adr import ───────────────────────────────────────────────────

def _cmd_adr_import(args: argparse.Namespace) -> int:
    """Import ADRs from a directory into target memory.

    Exit codes:
        0 = success (preview shown in dry-run, or write completed in apply)
        1 = diagnostics present (active-active contradiction or collisions)
            in dry-run mode (informational; CI can use this to fail the PR)
        2 = apply failed (refused due to unresolved diagnostics)
    """
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    adr_dir = Path(args.adr_dir)
    if not adr_dir.is_dir():
        print(f"ERROR: {adr_dir} is not a directory", file=sys.stderr, flush=True)
        return 2

    target_path = Path(args.memory)
    if not target_path.exists():
        print(f"ERROR: memory file {target_path} does not exist", file=sys.stderr, flush=True)
        return 2

    report = compile_for_import(adr_dir)
    target_memory = json.loads(target_path.read_text(encoding="utf-8"))
    collisions = detect_collisions(report.active_nodes, target_memory)

    print(format_preview(report, collisions=collisions))

    if args.apply:
        try:
            written = apply_import(
                report,
                target_path=target_path,
                allow_update=args.update_existing,
                approve_conflicts=args.approve_conflicts,
            )
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr, flush=True)
            return 2
        print(f"Wrote {len(written)} decisions to {target_path}")
        return 0

    has_diags = bool(report.diagnostics) or bool(collisions)
    return 1 if has_diags else 0


# ── Entry point ──────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mneme")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # init
    p_init = sub.add_parser(
        "init", help="Scaffold an empty project_memory.json"
    )
    p_init.add_argument(
        "--path", default=DEFAULT_MEMORY_PATH,
        help=f"Output path (default: {DEFAULT_MEMORY_PATH})",
    )
    p_init.add_argument(
        "--force", action="store_true",
        help="Overwrite an existing file at --path",
    )
    p_init.set_defaults(func=_cmd_init)

    # list_decisions
    p_list = sub.add_parser("list_decisions", help="List all decisions")
    p_list.add_argument("--memory", required=True, help="Path to project_memory.json")
    p_list.set_defaults(func=_cmd_list)

    # add_decision
    p_add = sub.add_parser("add_decision", help="Append a new decision")
    p_add.add_argument("--memory", required=True)
    p_add.add_argument("--id", required=True)
    p_add.add_argument("--decision", required=True)
    p_add.add_argument("--rationale", default="")
    p_add.add_argument("--scope", action="append", default=[])
    p_add.add_argument("--constraint", action="append", default=[])
    p_add.add_argument("--anti-pattern", dest="anti_pattern", action="append", default=[])
    p_add.set_defaults(func=_cmd_add)

    # test_query
    p_test = sub.add_parser("test_query", help="Run a query through the retriever")
    p_test.add_argument("--memory", required=True)
    p_test.add_argument("--query", required=True)
    p_test.add_argument("--top", type=int, default=DEFAULT_MAX_DECISIONS)
    p_test.set_defaults(func=_cmd_test)

    # check
    p_check = sub.add_parser("check", help="Enforce decisions against an input prompt")
    p_check.add_argument("--memory", required=True, help="Path to project_memory.json")
    p_check.add_argument("--input", required=True, help="Path to input file to check")
    p_check.add_argument("--query", required=True, help="Context query for retrieval")
    p_check.add_argument("--top", type=int, default=DEFAULT_MAX_DECISIONS)
    p_check.add_argument(
        "--mode", choices=["warn", "strict"], default="strict",
        help="warn: all verdicts exit 0; strict (default): WARN->1, FAIL->2",
    )
    p_check.add_argument(
        "--adr-dir", dest="adr_dir", default="docs/adr",
        help=(
            "Directory containing ADR markdown files to check for freshness "
            "drift (warn-only; never affects exit code). "
            "Defaults to docs/adr; freshness is skipped silently if absent."
        ),
    )
    p_check.set_defaults(func=_cmd_check)

    # cursor (parent for cursor subcommands)
    p_cursor = sub.add_parser("cursor", help="Cursor.ai integration commands")
    cursor_sub = p_cursor.add_subparsers(dest="cursor_cmd", required=True)

    p_cursor_gen = cursor_sub.add_parser("generate", help="Generate Cursor rules file")
    p_cursor_gen.add_argument("--memory", required=True, help="Path to project_memory.json")
    p_cursor_gen.add_argument("--query", required=True, help="Context query for retrieval")
    p_cursor_gen.add_argument(
        "--output", default=".cursor/rules/mneme.mdc",
        help="Output path (default: .cursor/rules/mneme.mdc)",
    )
    p_cursor_gen.add_argument("--top", type=int, default=DEFAULT_MAX_DECISIONS)
    p_cursor_gen.set_defaults(func=_cmd_cursor_generate)

    # benchmark
    p_bench = sub.add_parser(
        "benchmark",
        help="Run benchmark scenarios and report violation detection results",
    )
    p_bench.add_argument(
        "benchmarks_dir",
        help="Path to directory containing benchmark scenario subdirectories",
    )
    p_bench.add_argument("--memory", required=True, help="Path to project_memory.json")
    p_bench.add_argument("--json", metavar="FILE", default=None,
                         help="Write JSON report to FILE")
    p_bench.add_argument("--markdown", metavar="FILE", default=None,
                         help="Write Markdown report to FILE")
    p_bench.set_defaults(func=_cmd_benchmark)

    # adr (parent for adr subcommands)
    p_adr = sub.add_parser("adr", help="ADR import and management commands")
    adr_sub = p_adr.add_subparsers(dest="adr_cmd", required=True)

    p_adr_import = adr_sub.add_parser(
        "import", help="Import ADRs from a directory into project memory"
    )
    p_adr_import.add_argument(
        "adr_dir", help="Path to a directory containing ADR markdown files"
    )
    p_adr_import.add_argument(
        "--memory", required=True, help="Path to target project_memory.json"
    )
    grp = p_adr_import.add_mutually_exclusive_group()
    grp.add_argument(
        "--dry-run", action="store_true",
        help="Print preview without writing (default)",
    )
    grp.add_argument(
        "--apply", action="store_true",
        help="Write imported decisions to --memory after preview",
    )
    p_adr_import.add_argument(
        "--update-existing", action="store_true",
        help="Allow same-id overwrite of existing decisions[] entries",
    )
    p_adr_import.add_argument(
        "--approve-conflicts", action="store_true",
        help="Proceed with apply even if active-active contradictions exist",
    )
    p_adr_import.set_defaults(func=_cmd_adr_import)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

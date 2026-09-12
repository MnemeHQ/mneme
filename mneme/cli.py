"""
cli.py — Command-line interface for Mneme.

Subcommands
-----------
  init              Scaffold an empty project_memory.json.
  setup             Initialize Mneme project state in setup mode (no
                    enforcement). See docs/plans/m1-3-audit-to-setup-activation.md.
  add_decision      Append a new Decision to a project_memory.json file.
  list_decisions    Print every Decision in the memory file.
  test_query        Run a query through the retriever and show scores + injected.
  cursor generate   Generate a Cursor .mdc rules file from retrieved decisions.
  audit             Run the P1.2 Architecture Protection Audit.
  protect           M1.4 per-decision protection activation:
                    list | status | validate | activate.
                    See docs/protect-activation.md.

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
import sys
from datetime import datetime, timezone
from pathlib import Path

from mneme.adr_diagnostics import collect_adr_diagnostics
from mneme.adr_freshness import FreshnessIssue
from mneme.adr_import import (
    apply_import,
    compile_for_import,
    detect_collisions,
    format_preview,
)
from mneme.integrations.eventcatalog import (
    apply_import as ec_apply_import,
    compile_for_import as ec_compile_for_import,
    detect_collisions as ec_detect_collisions,
    format_preview as ec_format_preview,
)
from mneme.benchmark import BenchmarkRunner, ScenarioVerdict
from mneme.benchmark_report import format_json, format_markdown, format_terminal
from mneme.context_builder import DEFAULT_MAX_DECISIONS, format_decisions
from mneme.cursor_generator import generate_mdc
from mneme.decision_retriever import DecisionRetriever
from mneme.enforcer import (
    EnforcementResult,
    Severity,
    check_prompt,
    generate_protection_report,
)
from mneme.memory_store import MemoryStore
from mneme.protection import (
    ENFORCEMENT_BEHAVIOR,
    ProtectionError,
    activate_protection,
    activation_precheck,
    find_candidates,
    find_decision,
    load_decisions,
    protection_status,
    validate_proposal,
)
from mneme.readiness import READINESS_LABELS, READINESS_ORDER
from mneme.setup import SetupError, SetupOutcome, run_setup
from mneme.setup_state import STATE_ACTIVE, scaffold_project_memory


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _error_exit(message: str) -> int:
    """Report a pre-execution user-input error and return the usage exit code.

    Missing files and bad paths print ``ERROR: ...`` to stderr and exit 2
    with empty stdout, so machine consumers (``--json``, the Claude Code
    hook) see no verdict payload and fail open. Verdict exit codes 0/1/2
    are reserved for actual enforcement results.
    """
    print(f"ERROR: {message}", file=sys.stderr, flush=True)
    return 2


# ── Subcommand: init ─────────────────────────────────────────────────────────

DEFAULT_MEMORY_PATH = ".mneme/project_memory.json"


def _scaffold_memory() -> dict:
    """Return a valid, empty, neutral project_memory.json skeleton.

    No seeded decisions: every decision is enforceable, so sample content
    would create phantom rules. The empty arrays let MemoryStore.load()
    round-trip the file and let `mneme check` run cleanly (nothing to
    enforce). meta.name and meta.description are the only fields the loader
    requires; created_by is recorded for provenance.
    """
    return scaffold_project_memory(created_by="mneme init")


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


# ── Subcommand: setup ────────────────────────────────────────────────────────

def _print_setup_summary(outcome: SetupOutcome) -> None:
    """Render the human-readable setup summary (ASCII, existing CLI style)."""
    print("Mneme setup")
    print()
    print("Repository")
    print(f"  OK {outcome.project_root.name} ({outcome.project_root})")
    print()
    print("Project memory")
    if outcome.created_memory:
        print(f"  Created {outcome.memory_path}")
    else:
        print(f"  Found {outcome.memory_path}")
    print()
    print("Architecture baseline")
    if outcome.baseline:
        repository = (
            outcome.baseline.get("repository")
            or outcome.baseline.get("repository_url")
            or "repository not identified"
        )
        print(f"  Connected: {outcome.baseline.get('project_name') or 'Audit project'} ({repository})")
        print(f"  Audit: {outcome.baseline.get('audit_id')}")
        print(f"  Commit: {outcome.baseline.get('commit_sha')}")
        print(
            f"  Mneme (audit): {outcome.baseline.get('mneme_version')}"
            f", schema {outcome.baseline.get('audit_schema')}"
        )
        completion = outcome.baseline.get("completion")
        if completion:
            print("  Setup recorded with the Audit service")
        else:
            print("  Setup recording pending (rerun `mneme setup` to retry)")
    elif outcome.audit_ref:
        print(f"  Audit reference recorded: {outcome.audit_ref}")
    else:
        print("  Not connected (no audit reference provided)")
    print()
    print("Integrations")
    if outcome.integrations:
        for item in outcome.integrations:
            surface = "native" if item.native else "rules export"
            print(f"  {item.label} detected ({item.evidence}, {surface})")
    else:
        print("  None detected")
    print()
    print("Protection readiness")
    for key in READINESS_ORDER:
        print(f"  {READINESS_LABELS[key]}: {outcome.readiness.get(key, 0)}")
    print()
    print("Enforcement")
    print("  Not enabled")
    print()
    print("Initial check")
    check_line = f"  OK ({outcome.decision_count} decisions)"
    if outcome.adr_diagnostics_present:
        check_line += (
            f" | ADR diagnostics: {outcome.adr_diagnostics} (warn-only)"
        )
    print(check_line)
    if outcome.warnings:
        print()
        for warning in outcome.warnings:
            print(f"WARN  {warning}")


def _cmd_setup(args: argparse.Namespace) -> int:
    audit_ref = args.audit_ref if args.audit_ref is not None else ""
    if args.audit_ref is not None and not audit_ref.strip():
        return _error_exit("audit reference must not be empty")
    try:
        outcome = run_setup(
            memory=Path(args.memory) if args.memory else None,
            audit_ref=audit_ref.strip(),
        )
    except SetupError as exc:
        return _error_exit(str(exc))

    _print_setup_summary(outcome)
    print()
    if outcome.state == STATE_ACTIVE:
        print("Mneme remains in active mode (unchanged by setup).")
    elif outcome.rerun:
        print("Mneme is already in setup mode.")
    else:
        print("Mneme is installed in setup mode.")
    return 0


# ── Subcommand: list_decisions ───────────────────────────────────────────────

def _cmd_list(args: argparse.Namespace) -> int:
    memory_path = Path(args.memory)
    if not memory_path.exists():
        return _error_exit(f"memory file {memory_path} does not exist")
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
        if d.rules:
            for rule in d.rules:
                print(f"    rule: {rule.type} {rule.value}")
                if rule.include_paths is not None:
                    print(f"      applies to: {', '.join(rule.include_paths)}")
                if rule.exclude_paths:
                    print(f"      except: {', '.join(rule.exclude_paths)}")
    return 0


# ── Subcommand: add_decision ─────────────────────────────────────────────────

def _cmd_add(args: argparse.Namespace) -> int:
    path = Path(args.memory)
    if not path.exists():
        return _error_exit(f"memory file {path} does not exist")
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
    memory_path = Path(args.memory)
    if not memory_path.exists():
        return _error_exit(f"memory file {memory_path} does not exist")
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


CHECK_JSON_SCHEMA = "mneme.check/v1"


def _check_payload(
    result: EnforcementResult,
    freshness: list[FreshnessIssue],
    mode: str,
) -> dict:
    """Build the ``--json`` verdict payload.

    Consumers (notably the Claude Code hook) must be able to tell a policy
    verdict apart from a crash. Exit codes cannot carry that distinction --
    strict mode returns 1 for a WARN verdict and Python also returns 1 for an
    uncaught exception -- so the verdict is stated explicitly here, behind a
    versioned ``schema`` key. Anything a consumer cannot parse should be
    treated as "no verdict" and failed open.
    """
    return {
        "schema": CHECK_JSON_SCHEMA,
        "verdict": result.verdict.value,
        "mode": mode,
        "evaluation_complete": result.evaluation_complete,
        "applicability": [
            {
                "decision_id": item.decision_id,
                "rule_type": item.rule_type,
                "rule_value": item.rule_value,
                "rule_index": item.rule_index,
                "path_scoped": item.path_scoped,
                "input_path": item.input_path,
                "outcome": item.outcome.value,
                "selector": item.selector,
                "reason": item.reason,
            }
            for item in result.applicability
        ],
        "violations": [
            {
                "decision_id": v.decision_id,
                "decision_text": v.decision_text,
                "severity": v.severity.value,
                "rule": v.rule,
                "trigger": v.trigger,
                "kind": v.kind,
                "rule_type": v.rule_type,
                "input_path": v.input_path,
                "selector": v.selector,
            }
            for v in result.violations
        ],
        "freshness": [
            {"code": i.code, "adr_id": i.adr_id, "message": i.message,
             "path": str(i.path) if i.path else None}
            for i in freshness
        ],
    }


def _collect_adr_diagnostics(
    memory_path: str | Path,
    adr_dir: str | Path,
) -> list[FreshnessIssue]:
    """Collect ADR freshness issues and lifecycle findings (warn-only)."""
    return collect_adr_diagnostics(memory_path=memory_path, adr_dir=adr_dir)


def _cmd_check(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        return _error_exit(f"input file {input_path} does not exist")
    memory_path = Path(args.memory)
    if not memory_path.exists():
        return _error_exit(f"memory file {memory_path} does not exist")
    input_text = input_path.read_text(encoding="utf-8")

    store = MemoryStore(args.memory)
    store.load()
    retriever = DecisionRetriever(store.decisions())
    scored = retriever.retrieve(args.query)

    target_path = args.target_path or args.input
    result = check_prompt(
        input_text,
        scored,
        top=args.top,
        input_path=target_path,
    )

    if getattr(args, "json", False):
        # Machine-readable mode: the payload must be the only thing on stdout,
        # so the human-readable violation and freshness blocks are suppressed.
        diagnostics = _collect_adr_diagnostics(memory_path=args.memory, adr_dir=args.adr_dir)
        print(json.dumps(_check_payload(result, diagnostics, args.mode)))
        if not result.evaluation_complete:
            return 2
        return _EXIT_CODES_BY_MODE[args.mode][result.verdict]

    if result.violations:
        for v in result.violations:
            kind = v.rule_type or v.kind
            print(
                f"{v.severity.value:4}  [{v.decision_id}] "
                f"{kind} \"{v.rule}\" -- trigger: {v.trigger}"
            )
            print(f"      {v.decision_text}")
            if v.input_path:
                selector = f" via {v.selector}" if v.selector else ""
                print(f"      path: {v.input_path}{selector}")
        print()

    scoped_traces = [item for item in result.applicability if item.path_scoped]
    if scoped_traces:
        for item in scoped_traces:
            if item.outcome.value == "UNKNOWN":
                print(
                    f"ERROR PATH_APPLICABILITY_UNKNOWN [{item.decision_id}] "
                    f"{item.rule_type} {item.rule_value!r} -- {item.reason}"
                )
                continue
            path = item.input_path or "(unknown)"
            selector = f" via {item.selector}" if item.selector else ""
            print(
                f"PATH  {item.outcome.value:8} [{item.decision_id}] "
                f"{path}{selector} -- {item.reason}"
            )
        print()

    # ADR freshness and lifecycle diagnostics are warn-only: they print to
    # stdout but never influence the exit code. Skipped silently when adr_dir
    # is absent so existing CLI output is unchanged for projects that do not
    # use ADRs.
    diagnostics = _collect_adr_diagnostics(memory_path=args.memory, adr_dir=args.adr_dir)
    if diagnostics:
        for issue in diagnostics:
            _print_freshness_issue(issue)
        print()

    if not result.evaluation_complete:
        print("Result: INCOMPLETE")
        return 2
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


# ── Subcommand: audit (P1.2 Architecture Protection Audit) ───────────────────

def _audit_payload(report) -> dict:
    """Build the machine-readable mneme.audit/v1 report payload."""
    return {
        "schema": report.schema,
        "memory": report.memory_path,
        "summary": {
            "total_decisions": report.total_decisions,
            "protection_relevant": report.protection_relevant,
            "protected": report.protected,
            "mneme_ready": report.mneme_ready,
            "requires_modelling": report.requires_modelling,
            "guidance": report.guidance,
            "current_protection_pct": report.current_protection_pct,
            "identified_mneme_potential_pct": report.identified_mneme_potential_pct,
            "protection_gap_pct": report.protection_gap_pct,
        },
        "decisions": [
            {
                "id": d.id,
                "decision": d.decision,
                "status": d.status,
                "intent": d.intent,
                "protection_tier": d.protection_tier,
                "mneme_guardrail": d.mneme_guardrail,
                "evidence_confidence": d.evidence_confidence,
                "evidence_sources": list(d.evidence_sources),
            }
            for d in report.decisions
        ],
    }


def _cmd_audit(args: argparse.Namespace) -> int:
    """Run the P1.2 Architecture Protection Audit over a memory file.

    Exit codes:
        0 = report generated, no open warnings
        1 = candidate (unverified) enforcement evidence found — a CI file
            mentions a forbidden token without failing the build
        2 = usage error (missing memory file or repo root)
    """
    memory_path = Path(args.memory)
    if not memory_path.exists():
        return _error_exit(f"memory file {memory_path} does not exist")
    repo_root = Path(args.repo_root) if args.repo_root else None
    if repo_root is not None and not repo_root.exists():
        return _error_exit(f"repo root {repo_root} does not exist")
    # TODO(trust-boundary, ADR-024/025): before any trusted producer accepts
    # CI-claimed test evidence as "verified", the GitHub inputs (owner, repo,
    # base_url) must be explicitly pinned — owner/repo to the audited
    # repository and base_url to trusted hosts — so evidence cannot be
    # ingested from an attacker-chosen endpoint. Not implemented here; the
    # public paths never produce "verified" test evidence.

    store = MemoryStore(args.memory)
    store.load()
    report = generate_protection_report(store.decisions(), repo_root=repo_root)

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(_audit_payload(report), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Audit report written: {out}")
    else:
        s = report
        print("Architecture Protection Audit")
        print("=" * 60)
        print(f"Decisions discovered:         {s.total_decisions}")
        print(f"Protection-relevant:          {s.protection_relevant}")
        print()
        # ADR-026: Identified Mneme Potential is numerically identical to
        # the Protection Gap and is NOT an independent second metric, so
        # the human-facing output presents Current Protection and
        # Protection Gap only. identified_mneme_potential_pct remains in
        # the JSON payload (mneme.audit/v1) for compatibility.
        print(f"Current Protection:           {s.current_protection_pct}%")
        print(f"Protection Gap:               {s.protection_gap_pct}%")
        print()
        print(f"Protected today:              {s.protected}")
        print(f"Mneme-ready:                  {s.mneme_ready}")
        print(f"Requires modelling:           {s.requires_modelling}")
        print(f"Guidance-only:                {s.guidance}")
        print()
        print("Per-decision breakdown:")
        for d in s.decisions:
            print(f"  [{d.protection_tier}] {d.id}: {d.decision}")
            if d.mneme_guardrail:
                print(f"      guardrail: {d.mneme_guardrail}")
            for src in d.evidence_sources:
                print(f"      evidence: {src}")
        print()

    if any(d.evidence_confidence == "candidate" for d in report.decisions):
        print(
            "WARN: candidate enforcement evidence found; "
            "the CI mention does not fail the build"
        )
        return 1
    return 0


# ── Subcommand: protect (M1.4 per-decision protection activation) ────────────

def _require_memory(
    memory: str,
) -> tuple[Path, list] | None:
    """Load and validate project memory for a protect subcommand.

    Returns ``(memory_path, decisions)`` or ``None`` after printing the
    usage-style error. Callers MUST test the tuple for ``None`` before
    unpacking it::

        loaded = _require_memory(args.memory)
        if loaded is None:
            return 2
        memory_path, decisions = loaded
    """
    memory_path = Path(memory)
    if not memory_path.exists():
        _error_exit(f"memory file {memory_path} does not exist")
        return None
    try:
        decisions = load_decisions(memory_path)
    except ProtectionError as exc:
        _error_exit(str(exc))
        return None
    return memory_path, decisions


def _cmd_protect_list(args: argparse.Namespace) -> int:
    loaded = _require_memory(args.memory)
    if loaded is None:
        return 2
    memory_path, decisions = loaded
    repo_root = Path(args.repo_root) if args.repo_root else None
    if repo_root is not None and not repo_root.exists():
        return _error_exit(f"repo root {repo_root} does not exist")
    discovered = find_candidates(decisions, repo_root=repo_root)
    report = discovered.report

    print("Protection activation candidates")
    print("=" * 60)
    print(
        f"Protected: {report.protected}  Mneme-ready: {report.mneme_ready}  "
        f"Requires modelling: {report.requires_modelling}  "
        f"Guidance: {report.guidance}"
    )
    print(f"Candidates: {len(discovered.candidates)}")
    print()
    if not discovered.candidates:
        print("(no activation candidates)")
        return 0
    for i, candidate in enumerate(discovered.candidates, start=1):
        print(f"[{i}] {candidate.decision_id}: {candidate.decision_text}")
        if candidate.source_path:
            print(f"    source: {candidate.source_path}")
        print(f"    guardrail: {candidate.guardrail}")
        print(
            f"    rule to install: {candidate.proposal.type} "
            f"\"{candidate.proposal.value}\""
        )
        scope = (
            "global applicability (canonical policy sources exempt)"
            if candidate.proposal.include_paths is None
            else ", ".join(candidate.proposal.include_paths)
        )
        print(f"    applies to: {scope}")
        print(f"    enforcement: {ENFORCEMENT_BEHAVIOR}")
    print()
    print(
        "Validate before activating:  mneme protect validate <decision-id>"
    )
    print(
        "Activate (explicit):         mneme protect activate <decision-id>"
    )
    return 0


def _cmd_protect_status(args: argparse.Namespace) -> int:
    loaded = _require_memory(args.memory)
    if loaded is None:
        return 2
    memory_path, _decisions = loaded
    repo_root = Path(args.repo_root) if args.repo_root else None
    if repo_root is not None and not repo_root.exists():
        return _error_exit(f"repo root {repo_root} does not exist")
    try:
        status = protection_status(
            args.decision_id, memory_path, repo_root=repo_root
        )
    except ProtectionError as exc:
        return _error_exit(str(exc))

    print(f"Decision [{status.decision_id}] {status.decision_text}")
    print(f"  lifecycle status: {status.lifecycle_status}")
    print(f"  protection tier:  {status.tier}")
    if status.guardrail:
        print(f"  guardrail:        {status.guardrail}")
    print(f"  evidence:         {status.evidence_confidence}")
    for src in status.evidence_sources:
        print(f"      {src}")
    print(f"  rule installed:   {'yes' if status.rule_installed else 'no'}")
    if status.proposal is not None:
        print(
            f"  proposal:         {status.proposal.type} "
            f"\"{status.proposal.value}\""
        )
    return 0


def _cmd_protect_validate(args: argparse.Namespace) -> int:
    loaded = _require_memory(args.memory)
    if loaded is None:
        return 2
    memory_path, decisions = loaded
    repo_root = Path(args.repo_root) if args.repo_root else None
    if repo_root is not None and not repo_root.exists():
        return _error_exit(f"repo root {repo_root} does not exist")
    decision = find_decision(decisions, args.decision_id)
    if decision is None:
        return _error_exit(f"decision {args.decision_id!r} not found")

    precheck = activation_precheck(decision, repo_root=repo_root)
    if not precheck.eligible:
        print(f"NOT ELIGIBLE: [{decision.id}] {precheck.reason}")
        print(
            "Protection was not validated and nothing was activated."
        )
        return 1

    result = validate_proposal(decision, precheck.proposal)
    print(f"Validating proposed protection for [{decision.id}]")
    print(f"  decision:  {decision.decision}")
    print(f"  proposal:  {result.proposal.type} \"{result.proposal.value}\"")
    print("  checks:")
    for check in result.checks:
        mark = "PASS" if check.passed else "FAIL"
        print(f"    {mark} {check.name}: {check.detail}")
    if result.status == "valid":
        print("Result: VALID")
        print("Validation never activates protection.")
        return 0
    print(f"Result: {result.status.upper()}")
    return 1


def _cmd_protect_activate(args: argparse.Namespace) -> int:
    loaded = _require_memory(args.memory)
    if loaded is None:
        return 2
    memory_path, _decisions = loaded
    repo_root = Path(args.repo_root) if args.repo_root else None
    if repo_root is not None and not repo_root.exists():
        return _error_exit(f"repo root {repo_root} does not exist")
    try:
        outcome = activate_protection(
            args.decision_id, memory_path, repo_root=repo_root
        )
    except ProtectionError as exc:
        return _error_exit(str(exc))

    if outcome.result == "verified":
        state = (
            "installed"
            if outcome.rule_installed
            else "already present"
        )
        print(
            f"Protection activated and verified: [{outcome.decision_id}] "
            f"(rule {state})"
        )
        if outcome.proposal is not None:
            print(
                f"  rule: {outcome.proposal.type} \"{outcome.proposal.value}\""
            )
        print(f"  verification: {outcome.detail}")
        print("Re-run `mneme audit` to observe the new Protected decision.")
        return 0
    if outcome.result == "already_protected":
        print(f"Already Protected: [{outcome.decision_id}]")
        print(f"  {outcome.detail}")
        print("  Nothing to activate.")
        return 0
    if outcome.result == "not_eligible":
        print(f"NOT ELIGIBLE: [{outcome.decision_id}] {outcome.detail}")
        return 1
    if outcome.result == "validation_failed":
        print(
            f"VALIDATION FAILED: [{outcome.decision_id}] {outcome.detail}"
        )
        if outcome.validation is not None:
            for check in outcome.validation.checks:
                if not check.passed:
                    print(f"    FAIL {check.name}: {check.detail}")
        print("Nothing was written.")
        return 1
    # verification_failed
    print(
        f"ERROR: activation artifact written for [{outcome.decision_id}], "
        "but canonical verification did not observe Protected — "
        "the decision remains NOT Protected."
    )
    print(f"  verification: {outcome.detail}")
    return 1


# ── Subcommand: cursor generate ──────────────────────────────────────────────

def _cmd_cursor_generate(args: argparse.Namespace) -> int:
    memory_path = Path(args.memory)
    if not memory_path.exists():
        return _error_exit(f"memory file {memory_path} does not exist")
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

    # FALSE_POSITIVE is a failing benchmark condition (charter 2026-08-24):
    # blocking benign content exits 1 just like a missed violation. MALFORMED
    # deliberately remains exit-0 (frozen five-verdict exit semantics); it is
    # surfaced through report output instead.
    has_failures = any(
        r.verdict in (ScenarioVerdict.FAIL, ScenarioVerdict.FALSE_POSITIVE)
        for r in results
    )
    return 1 if has_failures else 0


# ── Subcommand: adr import ───────────────────────────────────────────────────

def _cmd_adr_import(args: argparse.Namespace) -> int:
    """Import ADRs from a directory into target memory.

    Exit codes:
        0 = success (preview shown in dry-run, or write completed in apply)
        1 = diagnostics present (retrieval-only ADR, active-active
            contradiction, or collision) in dry-run mode
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


def _cmd_eventcatalog_import(args: argparse.Namespace) -> int:
    """Import EventCatalog ADRs from an index into target memory."""
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    index_path = Path(args.index)
    catalog_root = Path(args.catalog_root)
    target_path = Path(args.memory)

    if not index_path.exists():
        print(f"ERROR: index file {index_path} does not exist", file=sys.stderr, flush=True)
        return 2
    if not catalog_root.is_dir():
        print(f"ERROR: catalog root {catalog_root} is not a directory", file=sys.stderr, flush=True)
        return 2
    if not target_path.exists():
        print(f"ERROR: memory file {target_path} does not exist", file=sys.stderr, flush=True)
        return 2

    report = ec_compile_for_import(index_path, catalog_root)
    target_memory = json.loads(target_path.read_text(encoding="utf-8"))
    collisions = ec_detect_collisions(report.nodes, target_memory)

    print(ec_format_preview(report, collisions=collisions))

    if args.apply:
        try:
            written = ec_apply_import(
                report,
                target_path=target_path,
                catalog_root=catalog_root,
                allow_update=args.update_existing,
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

    # setup
    p_setup = sub.add_parser(
        "setup",
        help=(
            "Initialize Mneme project state in setup mode "
            "(context and non-blocking checks only; never enforcement)"
        ),
    )
    p_setup.add_argument(
        "--memory", default=None,
        help=(
            "Path to project_memory.json "
            f"(default: <repo-root>/{DEFAULT_MEMORY_PATH})"
        ),
    )
    p_setup.add_argument(
        "--audit-ref", dest="audit_ref", default=None,
        help=(
            "Opaque Architecture Audit setup reference to record with this "
            "setup (recorded verbatim; resolved by Audit pairing)"
        ),
    )
    p_setup.set_defaults(func=_cmd_setup)

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
    p_check.add_argument(
        "--target-path",
        default=None,
        help=(
            "Artifact path used for typed-rule applicability when --input "
            "contains materialized or introduced content from another file"
        ),
    )
    p_check.add_argument("--query", required=True, help="Context query for retrieval")
    p_check.add_argument(
        "--top", type=int, default=DEFAULT_MAX_DECISIONS,
        help=(
            "Size of the retrieval-gated tier. Bounds how many decisions have "
            "their multi-term rules applied; unambiguous literal rules are "
            "enforced across the whole corpus regardless (ADR-017)."
        ),
    )
    p_check.add_argument(
        "--mode", choices=["warn", "strict"], default="strict",
        help="warn: all verdicts exit 0; strict (default): WARN->1, FAIL->2",
    )
    p_check.add_argument(
        "--json", action="store_true",
        help=(
            "Emit a machine-readable verdict payload as the only stdout "
            "content. Exit codes are unchanged; consumers should trust the "
            "payload's verdict rather than the exit code, and fail open on "
            "anything they cannot parse."
        ),
    )
    p_check.add_argument(
        "--adr-dir", dest="adr_dir", default="docs/adr",
        help=(
            "Directory containing ADR markdown files to check for freshness "
            "drift and lifecycle consistency (warn-only; never affects exit code). "
            "Defaults to docs/adr; diagnostics are skipped silently if absent."
        ),
    )
    p_check.set_defaults(func=_cmd_check)

    # audit (P1.2 Architecture Protection Audit)
    p_audit = sub.add_parser(
        "audit",
        help="Run the P1.2 Architecture Protection Audit over project memory",
    )
    p_audit.add_argument("--memory", required=True, help="Path to project_memory.json")
    p_audit.add_argument(
        "--repo-root", dest="repo_root", default=None,
        help=(
            "Repository root to scan for external enforcement evidence "
            "(.github/workflows, .gitlab-ci.yml). Verified CI evidence "
            "upgrades a literalizable decision to protected; a bare token "
            "mention is candidate evidence and exits 1 as a warning."
        ),
    )
    p_audit.add_argument(
        "--json", metavar="FILE", default=None,
        help="Write the mneme.audit/v1 JSON report to FILE",
    )
    p_audit.set_defaults(func=_cmd_audit)

    # protect (M1.4 per-decision protection activation)
    p_protect = sub.add_parser(
        "protect",
        help=(
            "Per-decision protection activation: list Mneme-ready candidates, "
            "deterministically validate a proposed protection, explicitly "
            "activate it, and inspect its canonical status"
        ),
    )
    protect_sub = p_protect.add_subparsers(dest="protect_cmd", required=True)

    _REPO_ROOT_HELP = (
        "Repository root to scan for external enforcement evidence, exactly "
        "like `mneme audit --repo-root`; omitted means no CI-evidence scan"
    )

    p_protect_list = protect_sub.add_parser(
        "list",
        help="List Mneme-ready protection activation candidates",
    )
    p_protect_list.add_argument("--memory", required=True, help="Path to project_memory.json")
    p_protect_list.add_argument("--repo-root", dest="repo_root", default=None,
                                help=_REPO_ROOT_HELP)
    p_protect_list.set_defaults(func=_cmd_protect_list)

    p_protect_status = protect_sub.add_parser(
        "status",
        help="Show the canonical protection status of one decision",
    )
    p_protect_status.add_argument("decision_id", help="Decision id, e.g. mneme_001")
    p_protect_status.add_argument("--memory", required=True, help="Path to project_memory.json")
    p_protect_status.add_argument("--repo-root", dest="repo_root", default=None,
                                  help=_REPO_ROOT_HELP)
    p_protect_status.set_defaults(func=_cmd_protect_status)

    p_protect_validate = protect_sub.add_parser(
        "validate",
        help=(
            "Deterministically validate a decision's proposed protection "
            "against the existing enforcement engine; never activates anything"
        ),
    )
    p_protect_validate.add_argument("decision_id", help="Decision id, e.g. mneme_001")
    p_protect_validate.add_argument("--memory", required=True, help="Path to project_memory.json")
    p_protect_validate.add_argument("--repo-root", dest="repo_root", default=None,
                                    help=_REPO_ROOT_HELP)
    p_protect_validate.set_defaults(func=_cmd_protect_validate)

    p_protect_activate = protect_sub.add_parser(
        "activate",
        help=(
            "Explicitly install the proposed typed rule for one decision, "
            "then verify via the canonical protection assessment"
        ),
    )
    p_protect_activate.add_argument("decision_id", help="Decision id, e.g. mneme_001")
    p_protect_activate.add_argument("--memory", required=True, help="Path to project_memory.json")
    p_protect_activate.add_argument("--repo-root", dest="repo_root", default=None,
                                    help=_REPO_ROOT_HELP)
    p_protect_activate.set_defaults(func=_cmd_protect_activate)

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

    # eventcatalog (parent for eventcatalog subcommands)
    p_ec = sub.add_parser("eventcatalog", help="EventCatalog integration commands")
    ec_sub = p_ec.add_subparsers(dest="ec_cmd", required=True)

    p_ec_import = ec_sub.add_parser(
        "import", help="Import ADRs from an EventCatalog index into project memory"
    )
    p_ec_import.add_argument(
        "--index", required=True, help="Path to EventCatalog index JSON (from buildIndex)"
    )
    p_ec_import.add_argument(
        "--catalog-root", required=True, help="Root directory of the EventCatalog project"
    )
    p_ec_import.add_argument(
        "--memory", required=True, help="Path to target project_memory.json"
    )
    grp = p_ec_import.add_mutually_exclusive_group()
    grp.add_argument(
        "--dry-run", action="store_true",
        help="Print preview without writing (default)",
    )
    grp.add_argument(
        "--apply", action="store_true",
        help="Write imported decisions to --memory after preview",
    )
    p_ec_import.add_argument(
        "--update-existing", action="store_true",
        help="Allow same-id overwrite of existing decisions[] entries",
    )
    p_ec_import.set_defaults(func=_cmd_eventcatalog_import)

    return parser


def _force_utf8_stdio() -> None:
    """Make stdout/stderr able to carry any character a decision contains.

    Decision text is arbitrary user content. This repo's own memory carries
    U+2192 in the imported ADR-001, ADR-005 and ADR-014 decisions, and on
    Windows the console defaults to cp1252, which cannot encode it -- so
    rendering a perfectly valid decision crashed the CLI with
    UnicodeEncodeError partway through its output (#253).

    Source-level ASCII discipline cannot fix this, because the character comes
    from the memory file rather than from mneme. Applied here in ``main`` so
    every subcommand is covered: previously only ``benchmark`` and
    ``adr import`` guarded themselves, while ``test_query`` and ``check``
    -- both of which render decision text -- did not.

    Note this differs from the Claude Code hook's ASCII-only rule. The hook
    writes into a protocol another process parses, so it constrains what it
    emits; the CLI writes for a human and instead widens what its stream can
    carry.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                # Detached or already-wrapped stream: rendering degrades to
                # whatever the caller supplied, which is still better than
                # refusing to run.
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

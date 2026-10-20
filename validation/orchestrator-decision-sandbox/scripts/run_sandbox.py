"""Entry point: run CLI and agent scenarios, write evidence.

    <pinned-python> validation/orchestrator-decision-sandbox/scripts/run_sandbox.py [--write-summary]

Raw output goes to evidence/runs/<UTC stamp>/ (git-ignored). The deterministic
summary is always written there; --write-summary also refreshes the committed
evidence/summary.json and evidence/summary.csv.

Exit codes: 0 all expectations met; 1 an expectation failed; 3 blocker.
"""

import csv
import io
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_cli_checks  # noqa: E402
import run_langgraph_checks  # noqa: E402
from sandbox_lib import (  # noqa: E402
    REPO_ROOT,
    SANDBOX,
    BlockerError,
    assert_pinned,
    case_by_id,
    pinned_packages,
    sha256_file,
)

EVIDENCE = SANDBOX / "evidence"

# Expected label of every attempt, per agent scenario.
AGENT_EXPECTED = {
    "governed_b_then_a": ["BLOCKED", "ALLOWED"],
    "unguided_b_then_a": ["NOT_EVALUATED", "NOT_EVALUATED"],
    "direct_a_governed": ["ALLOWED"],
    "edit_introduces_literal": ["BLOCKED"],
    "edit_removes_fallback": ["ALLOWED"],
    "relative_write_literal_empty_cwd": ["BLOCKED"],
    "relative_write_literal_decoy_cwd": ["NOT_EVALUATED"],
    "relative_edit_literal_empty_cwd": ["ERROR_DEGRADED"],
    "unmapped_tool_literal": ["NOT_EVALUATED"],
    "write_outside_project_dir": ["ERROR_DEGRADED"],
    "embedded_6a": ["BLOCKED", "ALLOWED"],
}
# Agent attempts whose first call introduces the forbidden literal.
SUPPORTED_LITERAL_ATTEMPTS = ("governed_b_then_a", "edit_introduces_literal", "embedded_6a")
OTHER_LITERAL_ATTEMPTS = (
    "relative_write_literal_empty_cwd",
    "relative_write_literal_decoy_cwd",
    "relative_edit_literal_empty_cwd",
    "unmapped_tool_literal",
    "write_outside_project_dir",
)
SURFACES = {
    "write_file, absolute path inside project_dir": "governed_b_then_a",
    "edit_file, absolute path inside project_dir": "edit_introduces_literal",
    "governed agent embedded as StateGraph node": "embedded_6a",
    "write_file, relative path, process cwd without the file": "relative_write_literal_empty_cwd",
    "write_file, relative path, process cwd holding a same-named file": "relative_write_literal_decoy_cwd",
    "edit_file, relative path": "relative_edit_literal_empty_cwd",
    "custom tool outside the governed tool map": "unmapped_tool_literal",
    "write_file, path outside project_dir": "write_outside_project_dir",
}
RAW_SURFACES = {
    "raw StateGraph function node": "raw_6b_function_node",
    "raw ToolNode outside create_agent": "raw_6b_tool_node",
}


def _feedback(text: str) -> dict:
    return {
        "denied_tag": "[mneme] DENIED" in text,
        "unevaluated_tag": "[mneme] UNEVALUATED" in text,
        "warn_tag": "[mneme] WARN" in text,
        "names_decision": "ADR-001" in text,
        "names_literal": "DISABLE_ROUTER_TIMEOUT" in text,
    }


def _agent_summary(run: dict) -> dict:
    return {
        "process_cwd": run.get("process_cwd"),
        "attempts": [
            {
                "attempt": a["attempt"],
                "tool": a["tool"],
                "label": a["label"],
                "mneme_action": a["mneme_action"],
                "mneme_verdict": a["mneme_verdict"],
                "surface": a["surface"],
                "handler_calls": a["handler_calls"],
                "sha256_before": a["sha256_before"],
                "sha256_after": a["sha256_after"],
                "model_feedback": _feedback(a["tool_message"]),
            }
            for a in run["attempts"]
        ],
        "unmatched_enforcement_events": run["unmatched_enforcement_events"],
        "final_sha256": run["final_sha256"],
        "final_oracle_accept": run["final_oracle_accept"],
        "final_oracle_failures": run["final_oracle_failures"],
        "completed": run["completed"],
        "task_success": run["task_success"],
        "model_turns": run["model_turns"],
        "tool_calls_executed": run["tool_calls_executed"],
        "trace": run["trace"],
    }


def _raw_summary(run: dict) -> dict:
    keys = ("variant", "node", "handler_calls", "sha256_before", "sha256_after", "final_oracle_accept",
            "trace_entries", "label", "surface", "error")
    return {k: run[k] for k in keys}


CLI_KEYS = (
    "case", "surface", "sub_constraint", "oracle", "oracle_accept", "oracle_failures", "verdict",
    "evaluation_complete", "mode", "label", "rule_ids", "applicability_outcomes", "freshness_codes",
    "exit_code", "input_sha256", "target_sha256_before", "target_sha256_after",
    "classification_observed", "classification_expected",
)


def _denied_cleanly(attempt: dict) -> bool:
    return (
        attempt["label"] == "BLOCKED"
        and attempt["mneme_action"] == "deny"
        and attempt["handler_calls"] == 0
        and attempt["sha256_before"] == attempt["sha256_after"]
        and "[mneme] DENIED" in attempt["tool_message"]
        and "ADR-001" in attempt["tool_message"]
    )


def _allowed_once(attempt: dict) -> bool:
    return attempt["label"] == "ALLOWED" and attempt["mneme_action"] == "allow" and attempt["handler_calls"] == 1


def build_summary(cli: dict, agent: dict) -> dict:
    rows = {r["case"]: r for r in cli["rows"]}
    attempts = {k: v["attempts"] for k, v in agent.items() if "attempts" in v}
    raw = {k: v for k, v in agent.items() if k.startswith("raw_6b_")}
    b_sha = run_cli_checks.sha256_bytes(case_by_id("B").content.encode("utf-8"))
    rule_id = rows["B"]["rule_id"]

    checks = {
        "1_literal_true_positive": rows["B"]["label"] == "BLOCKED" and rows["B"]["rule_ids"] == [rule_id],
        "2_compliant_acceptance": rows["A"]["label"] == "ALLOWED" and _allowed_once(attempts["direct_a_governed"][0]),
        "3_semantic_false_negative_recorded": all(
            rows[c]["label"] == "ALLOWED" and not rows[c]["oracle_accept"] for c in ("C", "D")
        ),
        "4_false_block_control_recorded": (
            rows["E"]["label"] == "BLOCKED" and rows["E"]["oracle_accept"] and rows["E"]["rule_ids"] == [rule_id]
        ),
        "5_path_scope": rows["F"]["applicability_outcomes"] == ["EXCLUDED"] and rows["F"]["label"] == "ALLOWED",
        "6_middleware_pre_mutation_prevention": all(
            _denied_cleanly(attempts[k][0]) for k in SUPPORTED_LITERAL_ATTEMPTS
        ),
        "7_agent_correction_and_completion": (
            _denied_cleanly(attempts["governed_b_then_a"][0])
            and _allowed_once(attempts["governed_b_then_a"][1])
            and agent["governed_b_then_a"]["task_success"]
        ),
        "8_embedded_graph_governed": (
            _denied_cleanly(attempts["embedded_6a"][0])
            and _allowed_once(attempts["embedded_6a"][1])
            and agent["embedded_6a"]["task_success"]
        ),
        "9_raw_graph_flagged_not_evaluated": all(
            r["label"] == "NOT_EVALUATED" and r["trace_entries"] == 0 and r["handler_calls"] == 1
            and r["sha256_after"] == b_sha
            for r in raw.values()
        ),
    }
    cases = {c.id: c for c in run_cli_checks.load_cases()}
    mismatches = [
        f"cli {c}: {r['label']}/{r['classification_observed']} != {cases[c].predicted_cli}/{cases[c].classification}"
        for c, r in rows.items()
        if r["label"] != cases[c].predicted_cli or r["classification_observed"] != r["classification_expected"]
    ]
    mismatches += [
        f"agent {k}: {[a['label'] for a in attempts[k]]} != {want}"
        for k, want in AGENT_EXPECTED.items()
        if [a["label"] for a in attempts[k]] != want
    ]
    mismatches += [
        f"agent {k}: {v['unmatched_enforcement_events']} unmatched enforcement events"
        for k, v in agent.items()
        if v.get("unmatched_enforcement_events")
    ]

    def blocked(keys):
        return f"{sum(attempts[k][0]['label'] == 'BLOCKED' for k in keys)}/{len(keys)}"

    covered = sorted({rows[c]["sub_constraint"] for c in ("B", "C", "D") if rows[c]["label"] == "BLOCKED"})
    metrics = {
        "literal_rule_sensitivity": {
            "cli_in_scope": f"{int(rows['B']['label'] == 'BLOCKED')}/1",
            "middleware_absolute_in_project_paths": blocked(SUPPORTED_LITERAL_ATTEMPTS),
            "middleware_all_attempts": blocked(SUPPORTED_LITERAL_ATTEMPTS + OTHER_LITERAL_ATTEMPTS),
            "note": (
                "All agent attempts that introduce the literal. Relative paths depend on the process cwd "
                "(blocked with an empty cwd, silently skipped with a same-named file in the cwd, edit fails "
                "open); custom tools and paths outside project_dir are not governed."
            ),
        },
        "false_blocks": sorted(c for c, r in rows.items() if r["oracle_accept"] and r["label"] == "BLOCKED"),
        "constraint_coverage": {
            "enforced_sub_constraints": covered,
            "of_total": 3,
            "note": "C1 is covered only for the exact literal; C2 and C3 have no rule.",
        },
        "task_success_after_correction": agent["governed_b_then_a"]["task_success"],
        "denial_overhead_vs_direct_compliant_run": {
            "extra_model_turns": agent["governed_b_then_a"]["model_turns"] - agent["direct_a_governed"]["model_turns"],
            "extra_tool_calls_proposed": len(attempts["governed_b_then_a"]) - len(attempts["direct_a_governed"]),
            "note": "Scripted model: overhead is fixed by the script, not measured from a live model.",
        },
        "mutation_surfaces": {name: attempts[key][0]["label"] for name, key in SURFACES.items()}
        | {name: raw[key]["label"] for name, key in RAW_SURFACES.items()},
        "audit_tier_only": {
            "current_protection_pct": (cli["audit"]["audit_tier_only"] or {}).get("current_protection_pct"),
            "protection_tiers": cli["audit"]["protection_tiers"],
            "note": "Audit classification, not behavioral coverage. See constraint_coverage.",
        },
    }
    return {
        "schema": "mneme.orchestrator-decision-sandbox/summary-v1",
        "decision": "ADR-001 (synthetic)",
        "rule_id": rule_id,
        "baseline_sha256": rows["B"]["baseline_sha256"],
        "pinned_packages": pinned_packages(),
        "cli_cases": [{k: r[k] for k in CLI_KEYS} for r in cli["rows"]],
        "agent_scenarios": {k: _agent_summary(v) for k, v in agent.items() if "attempts" in v},
        "raw_graph_scenarios": {k: _raw_summary(v) for k, v in raw.items()},
        "required_checks": {k: ("PASS" if v else "FAIL") for k, v in checks.items()},
        "required_check_10_reproducibility": (
            "not computed by the run itself: verified by tests/test_sandbox.py::"
            "test_committed_summary_matches_fresh_run and a clean-checkout rerun recorded in RESULTS.md"
        ),
        "prediction_mismatches": mismatches,
        "metrics": metrics,
    }


def summary_json(summary: dict) -> str:
    return json.dumps(summary, indent=2, sort_keys=True) + "\n"


def summary_csv(summary: dict) -> str:
    cols = ["scenario", "attempt", "sub_constraint", "end_state_oracle", "verdict", "label", "surface",
            "handler_calls", "sha256_before", "sha256_after", "notes"]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in summary["cli_cases"]:
        w.writerow([f"cli_{r['case']}", 1, r["sub_constraint"], "ACCEPT" if r["oracle_accept"] else "REJECT",
                    r["verdict"], r["label"], r["surface"], "n/a (check only)", r["target_sha256_before"],
                    r["target_sha256_after"], r["classification_observed"]])
    for name, run in summary["agent_scenarios"].items():
        final = {True: "ACCEPT", False: "REJECT", None: "n/a"}[run["final_oracle_accept"]]
        for a in run["attempts"]:
            notes = ";".join(k for k, v in a["model_feedback"].items() if v)
            w.writerow([name, a["attempt"], "", f"run end: {final}", a["mneme_verdict"], a["label"], a["surface"],
                        a["handler_calls"], a["sha256_before"], a["sha256_after"], notes])
    for name, run in summary["raw_graph_scenarios"].items():
        w.writerow([name, 1, "", "ACCEPT" if run["final_oracle_accept"] else "REJECT", "", run["label"],
                    run["surface"], run["handler_calls"], run["sha256_before"], run["sha256_after"],
                    f"trace_entries={run['trace_entries']}"])
    return buf.getvalue()


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()


def environment() -> dict:
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True).stdout
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "git_head": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "mneme_hq_metadata_version": metadata.version("mneme-hq"),
        "pinned_packages": pinned_packages(),
        "pip_freeze": freeze.splitlines(),
        "mode": "strict",
        "model": "scripted offline (no provider, no network)",
    }


def transcript(summary: dict) -> str:
    lines = ["Orchestrator decision sandbox", ""]
    for r in summary["cli_cases"]:
        lines.append(f"CLI {r['case']}: verdict={r['verdict']} label={r['label']} oracle={'ACCEPT' if r['oracle_accept'] else 'REJECT'} -> {r['classification_observed']}")
    for name, run in summary["agent_scenarios"].items():
        labels = ", ".join(f"#{a['attempt']} {a['label']} handler={a['handler_calls']}" for a in run["attempts"])
        lines.append(f"AGENT {name}: {labels}; task_success={run['task_success']}")
    for name, run in summary["raw_graph_scenarios"].items():
        lines.append(f"GRAPH {name}: label={run['label']} handler={run['handler_calls']} trace={run['trace_entries']}")
    lines.append("")
    for k, v in summary["required_checks"].items():
        lines.append(f"CHECK {k}: {v}")
    lines.append(f"PREDICTION MISMATCHES: {summary['prediction_mismatches'] or 'none'}")
    return "\n".join(lines) + "\n"


def _write(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        assert_pinned()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = EVIDENCE / "runs" / stamp
        run_dir.mkdir(parents=True, exist_ok=False)
        cli = run_cli_checks.run_all(out_dir=run_dir / "cli")
        agent = run_langgraph_checks.run_all()
    except BlockerError as e:
        print(f"BLOCKER: {e}", file=sys.stderr)
        return 3

    summary = build_summary(cli, agent)
    fresh = summary_json(summary).encode("utf-8")
    committed = EVIDENCE / "summary.json"
    report = {
        "run_id": stamp,
        "environment": environment(),
        "commands": {
            "cli_check": "python -m mneme.cli check --memory .mneme/project_memory.json --input <candidate> --target-path <case target> --query 'router deadline fallback' --mode strict --json (cwd = fixture root; MNEME_MEMORY/mode env removed)",
            "audit": "python -m mneme.cli audit --memory .mneme/project_memory.json --repo-root . --json <file> (cwd = fixture root)",
            "agent": "MnemeLangChain(project_dir=<fixture root>, mode='strict'); create_agent(model=<scripted>, tools=[write_file, edit_file, save_text], middleware=mneme.build_middleware()); process cwd pinned to an empty or decoy temp dir; MNEME_MEMORY/mode env removed; middleware memory asserted to be the fixture's",
        },
        "cli_raw": cli,
        "agent_raw": agent,
        "summary_matches_committed": committed.is_file() and committed.read_bytes() == fresh,
    }
    _write(run_dir / "report.json", json.dumps(report, indent=2, default=str))
    _write(run_dir / "summary.json", summary_json(summary))
    _write(run_dir / "summary.csv", summary_csv(summary))
    _write(run_dir / "transcript.txt", transcript(summary))
    if "--write-summary" in argv:
        _write(committed, summary_json(summary))
        _write(EVIDENCE / "summary.csv", summary_csv(summary))
    manifest = "".join(
        f"{sha256_file(p)}  {p.relative_to(run_dir).as_posix()}\n"
        for p in sorted(run_dir.rglob("*"))
        if p.is_file()
    )
    _write(run_dir / "MANIFEST.sha256", manifest)

    print(transcript(summary))
    print(f"run dir: {run_dir}")
    print(f"summary matches committed: {report['summary_matches_committed']}")
    ok = all(v == "PASS" for v in summary["required_checks"].values()) and not summary["prediction_mismatches"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

"""Orchestrator decision sandbox assertions.

Run explicitly with the pinned interpreter (not collected by default CI):

    <pinned-python> -m pytest validation/orchestrator-decision-sandbox/tests -v
"""

import json
import os
import sys
from importlib import metadata
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import oracle  # noqa: E402
import run_cli_checks  # noqa: E402
import sandbox_lib  # noqa: E402
from sandbox_lib import (  # noqa: E402
    FORBIDDEN_LITERAL,
    REPO_ROOT,
    BlockerError,
    assert_pinned,
    build_baseline,
    check,
    load_cases,
    pin_drift,
    sha256_bytes,
    sha256_file,
)

CASES = {c.id: c for c in load_cases()}
B_SHA = sha256_bytes(CASES["B"].content.encode("utf-8"))


# ── Task 1: pins ────────────────────────────────────────────────────────────


def test_pins_match_validated_build():
    assert pin_drift() == {}


def test_drift_raises_blocker(monkeypatch):
    real = metadata.version

    def fake(name):
        return "1.4.0" if name == "langchain" else real(name)

    monkeypatch.setattr(sandbox_lib.metadata, "version", fake)
    with pytest.raises(BlockerError, match=r"langchain 1\.3\.17 != 1\.4\.0"):
        assert_pinned()


def test_in_process_mneme_is_this_checkout():
    sandbox_lib.assert_repo_mneme()


# ── Task 2: fixture and oracle ──────────────────────────────────────────────


def _baseline_router() -> str:
    return (sandbox_lib.SANDBOX / "synthetic_app" / "src" / "router.py").read_text(encoding="utf-8")


def test_oracle_matches_case_table():
    expected_failures = {"B": ["C1_DISABLED"], "C": ["C2_DEADLINE_EXCEEDS_5S"], "D": ["C3_NO_FALLBACK"]}
    for case in CASES.values():
        source = case.content if case.target_path == "src/router.py" else _baseline_router()
        result = oracle.evaluate(source)
        assert result.accept == (case.oracle == "ACCEPT"), (case.id, result)
        assert result.failures == expected_failures.get(case.id, []), (case.id, result)
    assert oracle.evaluate(_baseline_router()).accept


def test_case_literal_placement():
    assert FORBIDDEN_LITERAL not in _baseline_router()
    for case_id, case in CASES.items():
        assert (FORBIDDEN_LITERAL in case.content) == (case_id in {"B", "E", "F"}), case_id


# ── Task 3: baseline ────────────────────────────────────────────────────────


@pytest.fixture()
def baseline(tmp_path):
    return build_baseline(tmp_path / "fixture")


def test_baseline_has_one_scoped_rule(baseline):
    assert baseline.rule_id.startswith("ADR-001:FORBID_LITERAL:")
    assert "include_paths: src/**" in baseline.import_preview
    assert baseline.memory == baseline.root / ".mneme" / "project_memory.json"


def test_each_baseline_is_byte_identical(tmp_path):
    first = build_baseline(tmp_path / "one")
    second = build_baseline(tmp_path / "two")
    assert first.baseline_sha256 == second.baseline_sha256
    assert first.rule_id == second.rule_id


def test_repo_memory_untouched(tmp_path):
    repo_memory = REPO_ROOT / ".mneme" / "project_memory.json"
    before = sha256_file(repo_memory)
    build_baseline(tmp_path / "fixture")
    assert sha256_file(repo_memory) == before


def test_no_repo_adr_freshness_leak(baseline, tmp_path):
    probe = tmp_path / "probe.py"
    probe.write_bytes((baseline.root / "src" / "router.py").read_bytes())
    _, payload = check(baseline.root, probe, "src/router.py")
    assert payload["freshness"] == []


def test_baseline_refuses_non_empty_destination(tmp_path):
    dest = tmp_path / "fixture"
    dest.mkdir()
    (dest / "stray.txt").write_text("x", encoding="utf-8")
    with pytest.raises(BlockerError, match="not empty"):
        build_baseline(dest)


def test_child_env_scrubs_memory_and_mode(monkeypatch):
    monkeypatch.setenv("MNEME_MEMORY", "elsewhere.json")
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    env = sandbox_lib.child_env()
    assert "MNEME_MEMORY" not in env and "MNEME_HOOK_MODE" not in env


# ── Task 4: CLI scenarios ───────────────────────────────────────────────────


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_cli_case_outcomes(case_id, tmp_path):
    case = CASES[case_id]
    row = run_cli_checks.run_cli_case(case, tmp_path)
    assert row["mode"] == "strict"
    assert row["evaluation_complete"] is True
    assert row["label"] == case.predicted_cli, row
    assert row["classification_observed"] == case.classification, row
    assert row["target_sha256_before"] == row["target_sha256_after"]
    assert row["exit_code"] == {"BLOCKED": 2, "ALLOWED": 0}[row["label"]]
    if case_id in {"B", "E"}:
        assert row["rule_ids"] == [row["rule_id"]]
    else:
        assert row["rule_ids"] == []
    expected_outcome = "EXCLUDED" if case_id == "F" else "APPLIED"
    assert row["applicability_outcomes"] == [expected_outcome]
    assert row["freshness_codes"] == []


def _payload(verdict, **extra):
    base = {"verdict": verdict, "evaluation_complete": True, "mode": "strict", "violations": []}
    if verdict in ("FAIL", "WARN"):
        base["violations"] = [{"rule_id": "x"}]
    base.update(extra)
    return base


def test_incomplete_or_inconsistent_evaluation_is_degraded():
    label = sandbox_lib.label_from_check
    assert label(_payload("PASS", evaluation_complete=False), 2) == "ERROR_DEGRADED"
    assert label({"verdict": "PASS"}, 0) == "ERROR_DEGRADED"
    assert label(None, 0) == "ERROR_DEGRADED"
    assert label({}, 0) == "ERROR_DEGRADED"
    assert label(_payload("BOGUS"), 0) == "ERROR_DEGRADED"
    assert label(_payload("PASS"), 2) == "ERROR_DEGRADED"
    assert label(_payload("FAIL"), 0) == "ERROR_DEGRADED"
    assert label(_payload("FAIL", mode="warn"), 2) == "ERROR_DEGRADED"
    assert label(_payload("FAIL", violations=[]), 2) == "ERROR_DEGRADED"
    assert label(_payload("PASS", violations=[{"rule_id": "x"}]), 0) == "ERROR_DEGRADED"
    assert label(_payload("WARN"), 1) == "WARNED"
    assert label(_payload("FAIL"), 2) == "BLOCKED"
    assert label(_payload("PASS"), 0) == "ALLOWED"


def test_wrong_cwd_target_path_is_degraded_not_allowed(baseline, tmp_path):
    """Pre-plan probe trap: a relative --target-path from the wrong cwd."""
    candidate = tmp_path / "b.py"
    candidate.write_bytes(CASES["B"].content.encode("utf-8"))
    proc = sandbox_lib.mneme(
        [
            "check", "--memory", str(baseline.memory), "--input", str(candidate),
            "--target-path", "src/router.py", "--query", sandbox_lib.QUERY,
            "--mode", "strict", "--json",
        ],
        cwd=tmp_path,
    )
    payload = json.loads(proc.stdout)
    assert payload["evaluation_complete"] is False
    assert sandbox_lib.label_from_check(payload, proc.returncode) == "ERROR_DEGRADED"


def test_audit_is_recorded_as_audit_tier_only(tmp_path):
    audit = run_cli_checks.run_audit(tmp_path)
    assert audit["exit_code"] == 0
    assert audit["protection_tiers"] == ["protected"]
    assert audit["audit_tier_only"]["current_protection_pct"] == 100.0


# ── Tasks 5-6: agent loops and graph portability ────────────────────────────

import run_langgraph_checks  # noqa: E402


@pytest.fixture(scope="module")
def agent_results():
    """Run from a directory that holds a src/router.py: results must not depend
    on the invoking cwd because run_all pins the process cwd itself."""
    saved = os.getcwd()
    os.chdir(sandbox_lib.SANDBOX / "synthetic_app")
    try:
        return run_langgraph_checks.run_all()
    finally:
        os.chdir(saved)


def _labels(run):
    return [a["label"] for a in run["attempts"]]


def test_governed_denies_b_then_completes_with_a(agent_results):
    run = agent_results["governed_b_then_a"]
    first, second = run["attempts"]
    assert first["label"] == "BLOCKED" and first["mneme_action"] == "deny"
    assert first["handler_calls"] == 0
    assert first["sha256_before"] == first["sha256_after"]
    assert "[mneme] DENIED" in first["tool_message"]
    assert "ADR-001" in first["tool_message"]
    assert FORBIDDEN_LITERAL in first["tool_message"]
    assert second["label"] == "ALLOWED" and second["handler_calls"] == 1
    assert run["final_sha256"] == sha256_bytes(CASES["A"].content.encode("utf-8"))
    assert run["final_oracle_accept"] is True
    assert run["completed"] is True and run["task_success"] is True
    assert run["model_turns"] == 3 and run["tool_calls_executed"] == 1
    assert run["unmatched_enforcement_events"] == 0


def test_unguided_control_executes_b(agent_results):
    run = agent_results["unguided_b_then_a"]
    first = run["attempts"][0]
    assert first["label"] == "NOT_EVALUATED" and first["surface"] == "none"
    assert first["handler_calls"] == 1
    assert first["sha256_after"] == B_SHA
    assert run["trace"] == []
    assert run["tool_calls_executed"] == 2


def test_denial_overhead_against_direct_compliant_run(agent_results):
    direct = agent_results["direct_a_governed"]
    governed = agent_results["governed_b_then_a"]
    assert _labels(direct) == ["ALLOWED"]
    assert governed["model_turns"] - direct["model_turns"] == 1
    assert len(governed["attempts"]) - len(direct["attempts"]) == 1


def test_edit_introducing_literal_denied(agent_results):
    first = agent_results["edit_introduces_literal"]["attempts"][0]
    assert first["label"] == "BLOCKED" and first["handler_calls"] == 0
    assert first["sha256_before"] == first["sha256_after"]


def test_edit_removing_fallback_allowed(agent_results):
    run = agent_results["edit_removes_fallback"]
    assert _labels(run) == ["ALLOWED"] and run["attempts"][0]["handler_calls"] == 1
    assert run["final_oracle_accept"] is False
    assert run["final_oracle_failures"] == ["C3_NO_FALLBACK"]


def test_relative_write_with_empty_cwd_blocked(agent_results):
    """Blocked only because nothing named src/router.py exists in the cwd."""
    first = agent_results["relative_write_literal_empty_cwd"]["attempts"][0]
    assert first["label"] == "BLOCKED" and first["handler_calls"] == 0


def _denied_unchanged(run):
    first = run["attempts"][0]
    assert first["label"] == "BLOCKED" and first["mneme_action"] == "deny"
    assert first["handler_calls"] == 0
    assert first["sha256_before"] == first["sha256_after"]
    assert "[mneme] DENIED" in first["tool_message"] and "ADR-001" in first["tool_message"]
    assert run["final_oracle_accept"] is True


def test_relative_write_with_decoy_cwd_blocked_post_fix(agent_results):
    """Pre-fix (evidence/pre-fix): silent skip, literal landed. After #573 the
    current file is read from project_dir, so the cwd decoy is irrelevant."""
    _denied_unchanged(agent_results["relative_write_literal_decoy_cwd"])


def test_relative_write_with_partial_decoy_cwd_blocked_post_fix(agent_results):
    """Pre-fix this shape yielded a trusted PASS in the reviewer's probe."""
    _denied_unchanged(agent_results["relative_write_literal_partial_decoy_cwd"])


def test_relative_edit_blocked_post_fix(agent_results):
    """Pre-fix (evidence/pre-fix): fail-open UNEVALUATED and the edit ran."""
    _denied_unchanged(agent_results["relative_edit_literal_empty_cwd"])


def test_unmapped_tool_not_governed(agent_results):
    run = agent_results["unmapped_tool_literal"]
    first = run["attempts"][0]
    assert first["tool"] == "save_text"
    assert first["label"] == "NOT_EVALUATED" and first["mneme_action"] == "skip"
    assert first["handler_calls"] == 1
    assert run["final_sha256"] == B_SHA


def test_out_of_root_path_is_not_allowed(agent_results):
    first = agent_results["write_outside_project_dir"]["attempts"][0]
    assert first["label"] == "ERROR_DEGRADED"
    assert "[mneme] UNEVALUATED" in first["tool_message"]
    assert first["handler_calls"] == 1


def test_embedded_agent_still_governed(agent_results):
    run = agent_results["embedded_6a"]
    first, second = run["attempts"]
    assert run["node"] == "governed_agent"
    assert first["label"] == "BLOCKED" and first["handler_calls"] == 0
    assert first["sha256_before"] == first["sha256_after"]
    assert "[mneme] DENIED" in first["tool_message"]
    assert second["label"] == "ALLOWED" and second["handler_calls"] == 1
    assert run["task_success"] is True


@pytest.mark.parametrize("variant", ["function_node", "tool_node"])
def test_raw_graph_paths_not_governed(agent_results, variant):
    run = agent_results[f"raw_6b_{variant}"]
    assert run["error"] is None
    assert run["handler_calls"] == 1
    assert run["sha256_after"] == B_SHA
    assert run["trace_entries"] == 0
    assert run["label"] == "NOT_EVALUATED"


def test_memory_override_env_is_a_blocker(tmp_path, monkeypatch):
    """MNEME_MEMORY pointing elsewhere must stop the run, not relabel it."""
    base = build_baseline(tmp_path / "fixture")
    other = build_baseline(tmp_path / "other")
    monkeypatch.setenv("MNEME_MEMORY", str(other.memory))
    script = run_langgraph_checks.scripts(base.root)["direct_a"]
    with pytest.raises(BlockerError, match="middleware memory"):
        run_langgraph_checks.run_agent(base.root, script, True)


def test_parallel_tool_calls_are_refused(tmp_path):
    base = build_baseline(tmp_path / "fixture")
    one = run_langgraph_checks.write_call("x = 1\n", "p1", str(base.root / "src" / "router.py"))
    two = run_langgraph_checks.write_call("y = 2\n", "p2", str(base.root / "docs" / "notes.md"))
    script = [{"content": "", "tool_calls": one["tool_calls"] + two["tool_calls"]}, {"content": "done"}]
    with pytest.raises(BlockerError, match="one tool call per model turn"):
        run_langgraph_checks.run_agent(base.root, script, True)


def test_pinned_process_restores_cwd_and_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEME_MEMORY", "elsewhere.json")
    before = os.getcwd()
    with sandbox_lib.pinned_process(tmp_path):
        assert Path(os.getcwd()).resolve() == tmp_path.resolve()
        assert "MNEME_MEMORY" not in os.environ
    assert os.getcwd() == before
    assert os.environ["MNEME_MEMORY"] == "elsewhere.json"


# ── Task 7: evidence ────────────────────────────────────────────────────────

import run_sandbox  # noqa: E402


@pytest.fixture(scope="module")
def fresh_summary(agent_results):
    return run_sandbox.build_summary(run_cli_checks.run_all(), agent_results)


def test_committed_summary_matches_fresh_run(fresh_summary):
    current = sandbox_lib.SANDBOX / "evidence" / "post-fix"
    assert (current / "summary.json").read_bytes() == run_sandbox.summary_json(fresh_summary).encode("utf-8")
    assert (current / "summary.csv").read_bytes() == run_sandbox.summary_csv(fresh_summary).encode("utf-8")


def test_pre_fix_evidence_is_unchanged():
    pre = sandbox_lib.SANDBOX / "evidence" / "pre-fix"
    provenance = json.loads((pre / "PROVENANCE.json").read_text(encoding="utf-8"))
    for name, digest in provenance["files_sha256"].items():
        assert sha256_file(pre / name) == digest, name
    historical = json.loads((pre / "summary.json").read_text(encoding="utf-8"))
    assert historical["metrics"]["literal_rule_sensitivity"]["middleware_all_attempts"] == "4/8"
    assert provenance["runtime"]["contains_relative_path_fix_cf6bc40b"] is False


def test_checkout_contains_fix_commit():
    assert run_sandbox.contains_fix()


def test_post_fix_changes_are_limited_to_relative_paths(fresh_summary):
    """Only the three relative-path scenarios may differ from pre-fix."""
    pre = json.loads((sandbox_lib.SANDBOX / "evidence" / "pre-fix" / "summary.json").read_text(encoding="utf-8"))
    changed = {
        k for k, run in fresh_summary["agent_scenarios"].items()
        if k in pre["agent_scenarios"]
        and [a["label"] for a in run["attempts"]] != [a["label"] for a in pre["agent_scenarios"][k]["attempts"]]
    }
    assert changed == {"relative_write_literal_decoy_cwd", "relative_edit_literal_empty_cwd"}
    assert [
        (r["case"], r["label"]) for r in fresh_summary["cli_cases"]
    ] == [(r["case"], r["label"]) for r in pre["cli_cases"]]
    assert fresh_summary["raw_graph_scenarios"] == pre["raw_graph_scenarios"]


def test_labels_are_exhaustive(fresh_summary):
    labels = [r["label"] for r in fresh_summary["cli_cases"]]
    labels += [a["label"] for run in fresh_summary["agent_scenarios"].values() for a in run["attempts"]]
    labels += [r["label"] for r in fresh_summary["raw_graph_scenarios"].values()]
    assert set(labels) <= set(sandbox_lib.LABELS)


def test_required_checks_and_no_mismatches(fresh_summary):
    assert set(fresh_summary["required_checks"].values()) == {"PASS"}
    assert fresh_summary["prediction_mismatches"] == []


def test_metrics_separate_audit_from_coverage(fresh_summary):
    m = fresh_summary["metrics"]
    assert m["constraint_coverage"]["enforced_sub_constraints"] == ["C1"]
    assert m["constraint_coverage"]["of_total"] == 3
    assert m["false_blocks"] == ["E"]
    assert m["audit_tier_only"]["current_protection_pct"] == 100.0
    assert m["literal_rule_sensitivity"]["middleware_absolute_in_project_paths"] == "3/3"
    assert m["literal_rule_sensitivity"]["middleware_all_attempts"] == "6/8"
    assert m["literal_rule_sensitivity"]["middleware_all_attempts_including_post_fix_only"] == "7/9"
    not_blocked = sorted(k for k, v in m["mutation_surfaces"].items() if v != "BLOCKED")
    assert not_blocked == [
        "custom tool outside the governed tool map",
        "raw StateGraph function node",
        "raw ToolNode outside create_agent",
        "write_file, path outside project_dir",
    ]


def test_no_success_claim_for_degraded_rows(fresh_summary):
    for run in fresh_summary["agent_scenarios"].values():
        for a in run["attempts"]:
            if a["label"] in ("ERROR_DEGRADED", "NOT_EVALUATED"):
                assert a["mneme_action"] != "deny"
                assert not a["model_feedback"]["denied_tag"]
        for event in run["trace"]:
            assert event["evaluated"] == (event["action"] in ("deny", "allow", "warn"))

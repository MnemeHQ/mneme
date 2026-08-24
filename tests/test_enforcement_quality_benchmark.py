"""Tests for the enforcement-quality benchmark extension (charter 2026-08-24).

Covers the charter contract end to end:

- loader: absent scenario_type defaults to violation; unknown values are
  MALFORMED (no silent fallback);
- runner: benign PASS requires the exposure contract; exposure misses are
  WEAK_RETRIEVAL / uncheckable, never PASS; blocked benign content is
  FALSE_POSITIVE; the violation path is unchanged;
- summary/report partitioning: violation metrics never absorb benign results,
  legacy-only output stays byte-compatible (no new keys or lines), opt-in
  output carries scenario_type / exposure / enforcement_quality;
- CLI: FALSE_POSITIVE exits 1;
- shipped suite: catch rate 3/3, FPR 0/4, uncheckable 0.
"""
import json
from pathlib import Path

import pytest

from mneme.benchmark import (
    BenchmarkRunner,
    ScenarioResult,
    ScenarioVerdict,
    load_scenario,
)
from mneme.benchmark_report import (
    compute_summary,
    format_json,
    format_markdown,
    format_terminal,
)
from mneme.cli import main
from mneme.memory_store import MemoryStore
from mneme.schemas import Decision

SUITE = Path(__file__).parent.parent / "examples" / "benchmarks-enforcement-quality"

MEMORY = {
    "meta": {"name": "t", "description": "t"},
    "decisions": [
        {
            "id": "rule-x",
            "decision": "X policy",
            "scope": ["widgets"],
            "constraints": [],
            "anti_patterns": ["foo and bar"],
            "rationale": "",
        },
        {
            "id": "rule-y",
            "decision": "Y policy",
            "scope": ["storage"],
            "constraints": [],
            "anti_patterns": ["zapdb"],
            "rationale": "",
        },
    ],
}


def _write_scenario(
    tmp_path: Path,
    name: str,
    *,
    query: str,
    content: str,
    metadata: dict,
) -> Path:
    d = tmp_path / name
    d.mkdir()
    (d / "query.txt").write_text(query, encoding="utf-8")
    (d / "without_mneme.txt").write_text(content, encoding="utf-8")
    (d / "with_mneme.txt").write_text(content, encoding="utf-8")
    (d / "scenario.json").write_text(json.dumps(metadata), encoding="utf-8")
    return d


def _run(tmp_path: Path, scenarios: list[tuple]) -> list[ScenarioResult]:
    for name, kwargs in scenarios:
        _write_scenario(tmp_path, name, **kwargs)
    mem = tmp_path / "project_memory.json"
    mem.write_text(json.dumps(MEMORY), encoding="utf-8")
    store = MemoryStore(mem)
    store.load()
    runner = BenchmarkRunner(store)
    return runner.run_suite(tmp_path)


# ── loader ────────────────────────────────────────────────────────────────

def test_loader_absent_scenario_type_defaults_to_violation(tmp_path):
    d = _write_scenario(
        tmp_path, "legacy", query="widgets configuration",
        content="Config uses foo bar here.",
        metadata={"name": "legacy"},
    )
    assert load_scenario(d).scenario_type == "violation"


def test_loader_unknown_scenario_type_is_malformed(tmp_path):
    d = _write_scenario(
        tmp_path, "typo", query="widgets configuration",
        content="Config uses foo bar here.",
        metadata={"name": "typo", "scenario_type": "bening"},
    )
    scenario = load_scenario(d)
    assert scenario.scenario_type == "violation"
    assert "scenario_type" in scenario.malformed_reason
    # The resulting MALFORMED short-circuit is exercised by
    # test_runner_unknown_scenario_type_short_circuits_to_malformed.


def test_runner_unknown_scenario_type_short_circuits_to_malformed(tmp_path):
    _write_scenario(
        tmp_path, "typo", query="widgets configuration",
        content="Config uses foo bar here.",
        metadata={"name": "typo", "scenario_type": "bening"},
    )
    mem = tmp_path / "project_memory.json"
    mem.write_text(json.dumps(MEMORY), encoding="utf-8")
    store = MemoryStore(mem)
    store.load()
    [result] = BenchmarkRunner(store).run_suite(tmp_path)
    assert result.verdict == ScenarioVerdict.MALFORMED


# ── runner ────────────────────────────────────────────────────────────────

def _benign_metadata(exposed=None):
    meta = {"name": "b", "category": "benign_control", "scenario_type": "benign"}
    if exposed is not None:
        meta["expected_exposed_decision_ids"] = exposed
    return meta


def test_runner_benign_pass_requires_satisfied_exposure(tmp_path):
    [result] = _run(tmp_path, [
        ("case", dict(
            query="widgets configuration",
            content="Config uses foo bar here.",
            metadata=_benign_metadata(["rule-x"]),
        )),
    ])
    assert result.verdict == ScenarioVerdict.PASS
    assert result.exposed_decision_ids_hit == ["rule-x"]
    assert result.enhanced_violation_count == 0


def test_runner_benign_exposure_miss_is_weak_retrieval_not_pass(tmp_path):
    [result] = _run(tmp_path, [
        ("case", dict(
            query="unrelated topic here",
            content="Config uses foo bar here.",
            metadata=_benign_metadata(["rule-x"]),
        )),
    ])
    assert result.verdict == ScenarioVerdict.WEAK_RETRIEVAL
    assert result.exposed_decision_ids_hit == []


def test_runner_benign_without_exposure_contract_is_uncheckable(tmp_path):
    """Charter invariant: a benign PASS requires proven enforcement scope.

    A fixture that omits ``expected_exposed_decision_ids`` entirely must be
    uncheckable (WEAK_RETRIEVAL), never a vacuous PASS.
    """
    [result] = _run(tmp_path, [
        ("case", dict(
            query="widgets configuration",
            content="Config uses foo bar here.",
            metadata=_benign_metadata(None),
        )),
    ])
    assert result.verdict == ScenarioVerdict.WEAK_RETRIEVAL
    assert "no exposure contract" in result.explanation


def test_runner_violation_opt_in_emits_identity_and_exposure(tmp_path):
    """Blocker #1 pin: explicitly declared scenario_type is an opt-in.

    An explicit ``"scenario_type": "violation"`` guard must carry its
    methodology identity through to the result instead of collapsing into
    legacy output.
    """
    _write_scenario(
        tmp_path, "guard",
        query="widgets configuration flags",
        content="placeholder",
        metadata={
            "name": "guard",
            "scenario_type": "violation",
            "expected_protected_decision_ids": ["rule-x"],
            "expected_exposed_decision_ids": ["rule-x"],
        },
    )
    # Overwrite sides: baseline violates the phrase, enhanced is clean.
    d = tmp_path / "guard"
    (d / "without_mneme.txt").write_text(
        "The config enables foo_and_bar mode by default.", encoding="utf-8"
    )
    (d / "with_mneme.txt").write_text(
        "Config keeps the two flags independent by default.", encoding="utf-8"
    )

    mem = tmp_path / "project_memory.json"
    mem.write_text(json.dumps(MEMORY), encoding="utf-8")
    store = MemoryStore(mem)
    store.load()
    [result] = BenchmarkRunner(store).run_suite(tmp_path)

    assert result.verdict == ScenarioVerdict.PASS
    assert result.scenario_type == "violation"
    assert result.methodology_opt_in is True
    assert result.expected_exposed_ids == ["rule-x"]
    assert result.exposed_decision_ids_hit == ["rule-x"]


def test_runner_violation_exposure_miss_downgrades_pass(tmp_path):
    """Exposure contract on a violation scenario has identical semantics.

    The single-term anti-pattern fires corpus-wide, so the baseline FAILs and
    the enhanced side is clean even though the governing decision was never
    retrieved. The unsatisfied exposure contract must downgrade this to
    WEAK_RETRIEVAL -- a PASS would be coincidental.
    """
    d = tmp_path / "guard"
    d.mkdir()
    (d / "query.txt").write_text("widgets configuration", encoding="utf-8")
    (d / "without_mneme.txt").write_text("We adopt zapdb now.", encoding="utf-8")
    (d / "with_mneme.txt").write_text("We use something else entirely.", encoding="utf-8")
    (d / "scenario.json").write_text(json.dumps({
        "name": "guard",
        "scenario_type": "violation",
        "expected_protected_decision_ids": [],
        "expected_exposed_decision_ids": ["rule-y"],
    }), encoding="utf-8")

    mem = tmp_path / "project_memory.json"
    mem.write_text(json.dumps(MEMORY), encoding="utf-8")
    store = MemoryStore(mem)
    store.load()
    [result] = BenchmarkRunner(store).run_suite(tmp_path)

    assert result.baseline_violation_count >= 1
    assert result.enhanced_violation_count == 0
    assert result.exposed_decision_ids_hit == []
    assert result.verdict == ScenarioVerdict.WEAK_RETRIEVAL


def test_runner_violation_exposure_hit_allows_pass(tmp_path):
    d = tmp_path / "guard"
    d.mkdir()
    (d / "query.txt").write_text("storage widgets", encoding="utf-8")
    (d / "without_mneme.txt").write_text("We adopt zapdb now.", encoding="utf-8")
    (d / "with_mneme.txt").write_text("We use something else entirely.", encoding="utf-8")
    (d / "scenario.json").write_text(json.dumps({
        "name": "guard",
        "scenario_type": "violation",
        "expected_exposed_decision_ids": ["rule-y"],
    }), encoding="utf-8")

    mem = tmp_path / "project_memory.json"
    mem.write_text(json.dumps(MEMORY), encoding="utf-8")
    store = MemoryStore(mem)
    store.load()
    [result] = BenchmarkRunner(store).run_suite(tmp_path)

    assert result.verdict == ScenarioVerdict.PASS
    assert result.exposed_decision_ids_hit == ["rule-y"]


def test_runner_benign_block_is_false_positive(tmp_path):
    [result] = _run(tmp_path, [
        ("case", dict(
            query="widgets configuration",
            content="Config enables foo_and_bar mode.",
            metadata=_benign_metadata(["rule-x"]),
        )),
    ])
    assert result.verdict == ScenarioVerdict.FALSE_POSITIVE
    assert result.enhanced_violation_count >= 1
    assert result.enhanced_triggers


def test_runner_violation_path_unchanged_without_scenario_type(tmp_path):
    d = tmp_path / "guard"
    d.mkdir()
    (d / "query.txt").write_text("widgets configuration flags", encoding="utf-8")
    (d / "without_mneme.txt").write_text(
        "The config enables foo_and_bar mode by default.", encoding="utf-8"
    )
    (d / "with_mneme.txt").write_text(
        "Config keeps the two flags independent by default.", encoding="utf-8"
    )
    (d / "scenario.json").write_text(json.dumps({
        "name": "guard",
        "expected_protected_decision_ids": ["rule-x"],
    }), encoding="utf-8")

    mem = tmp_path / "project_memory.json"
    mem.write_text(json.dumps(MEMORY), encoding="utf-8")
    store = MemoryStore(mem)
    store.load()
    [result] = BenchmarkRunner(store).run_suite(tmp_path)
    assert result.verdict == ScenarioVerdict.PASS
    assert result.scenario_type == "violation"


# ── summary / formatter partitioning ─────────────────────────────────────

def _result(name, stype, verdict, declared=False):
    return ScenarioResult(
        name=name, category="c", verdict=verdict,
        baseline_violation_count=0, enhanced_violation_count=0,
        explanation="", scenario_type=stype,
        methodology_opt_in=declared,
    )


MIXED = [
    # Explicitly declared violation scenario: opt-in identity must survive.
    _result("v_pass", "violation", ScenarioVerdict.PASS, declared=True),
    _result("v_fail", "violation", ScenarioVerdict.FAIL, declared=True),
    # Undeclared violation scenario: legacy output shape.
    _result("v_legacy", "violation", ScenarioVerdict.WEAK),
    _result("b_pass_1", "benign", ScenarioVerdict.PASS, declared=True),
    _result("b_pass_2", "benign", ScenarioVerdict.PASS, declared=True),
    _result("b_fp", "benign", ScenarioVerdict.FALSE_POSITIVE, declared=True),
    _result("b_malformed", "benign", ScenarioVerdict.MALFORMED, declared=True),
    _result("b_weak", "benign", ScenarioVerdict.WEAK_RETRIEVAL, declared=True),
]


def test_summary_partitions_violation_and_benign():
    s = compute_summary(MIXED)
    # Violation partition only.
    assert s.passed == 1 and s.failed == 1 and s.weak == 1
    assert s.pass_rate == 0.5
    assert s.total == len(MIXED)
    # Benign partition.
    assert s.benign_total == 5
    assert s.benign_passed == 2
    assert s.benign_blocked == 1
    assert s.benign_uncheckable == 2
    assert s.false_positive_rate == round(1 / 3, 4)


def test_terminal_legacy_only_output_has_no_benign_lines():
    out = format_terminal([r for r in MIXED if r.scenario_type == "violation"])
    assert "Benign controls" not in out


def test_terminal_mixed_output_renders_partitioned_benign_line():
    out = format_terminal(MIXED)
    assert "Benign controls: false positives 1/3 checkable (FPR 33%)" in out
    assert "uncheckable 2/5" in out


def test_json_legacy_only_output_has_no_new_keys():
    legacy = [r for r in MIXED if not r.methodology_opt_in]
    payload = json.loads(format_json(legacy))
    assert "enforcement_quality" not in payload["summary"]
    assert all("scenario_type" not in r for r in payload["results"])
    assert all("exposure" not in r for r in payload["results"])


def test_json_mixed_output_emits_opt_in_keys_only_for_opt_in_rows():
    payload = json.loads(format_json(MIXED))
    eq = payload["summary"]["enforcement_quality"]
    assert eq["violation_passed"] == 1
    assert eq["violation_checkable"] == 2
    assert eq["benign_total"] == 5
    assert eq["benign_blocked"] == 1
    assert eq["benign_checkable"] == 3
    assert eq["false_positive_rate"] == round(1 / 3, 4)
    assert eq["benign_uncheckable"] == 2

    by_name = {r["name"]: r for r in payload["results"]}
    # Explicit violation scenarios keep their opt-in identity (blocker #1).
    assert by_name["v_pass"]["scenario_type"] == "violation"
    assert by_name["v_pass"]["exposure"]["expected_ids"] == []
    assert by_name["v_fail"]["scenario_type"] == "violation"
    # Undeclared legacy rows keep the exact legacy shape.
    assert "scenario_type" not in by_name["v_legacy"]
    assert "exposure" not in by_name["v_legacy"]
    # Benign rows carry identity; MALFORMED rows do not emit methodology keys.
    assert by_name["b_fp"]["scenario_type"] == "benign"
    assert by_name["b_pass_1"]["exposure"]["expected_ids"] == []
    assert "scenario_type" not in by_name["b_malformed"]
    assert "exposure" not in by_name["b_malformed"]


def test_markdown_mixed_output_has_partitioned_summary():
    out = format_markdown(MIXED)
    assert "**Benign controls**" in out
    assert "FPR 33%" in out


# ── CLI exit semantics ────────────────────────────────────────────────────

def _cli_exit_for(results_tmp_path, scenarios):
    for name, kwargs in scenarios:
        _write_scenario(results_tmp_path, name, **kwargs)
    mem = results_tmp_path / "project_memory.json"
    mem.write_text(json.dumps(MEMORY), encoding="utf-8")
    return main([
        "benchmark", str(results_tmp_path), "--memory", str(mem),
    ])


def test_cli_false_positive_exits_one(tmp_path):
    scenarios = [
        ("blocked", dict(
            query="widgets configuration",
            content="Config enables foo_and_bar mode.",
            metadata=_benign_metadata(["rule-x"]),
        )),
    ]
    assert _cli_exit_for(tmp_path, scenarios) == 1


def test_cli_clean_benign_suite_exits_zero(tmp_path):
    scenarios = [
        ("clean", dict(
            query="widgets configuration",
            content="Config uses foo bar here.",
            metadata=_benign_metadata(["rule-x"]),
        )),
    ]
    assert _cli_exit_for(tmp_path, scenarios) == 0


# ── shipped suite ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def shipped_results():
    store = MemoryStore(SUITE / "project_memory.json")
    store.load()
    return BenchmarkRunner(store).run_suite(SUITE)


def test_shipped_suite_verdicts(shipped_results):
    by_name = {r.name: r for r in shipped_results}
    assert set(by_name) == {
        "guard_unreviewed_changes",
        "guard_awin_identifier",
        "guard_foo_and_bar_compound",
        "benign_awin_programme",
        "benign_slug_prose",
        "benign_foo_bar_incomplete",
        "benign_governance_docs",
    }
    guards = [r for r in shipped_results if r.name.startswith("guard_")]
    benigns = [r for r in shipped_results if r.name.startswith("benign_")]
    assert all(r.verdict == ScenarioVerdict.PASS for r in guards)
    assert all(r.verdict == ScenarioVerdict.PASS for r in benigns)

    s = compute_summary(shipped_results)
    assert s.passed == 3 and s.failed == 0
    assert s.benign_total == 4
    assert s.benign_blocked == 0
    assert s.false_positive_rate == 0.0
    assert s.benign_uncheckable == 0
    # Exposure contract: every benign control proved its governing rule was
    # actually in enforcement scope; every guard declared one too and its
    # opt-in identity survives into results (charter §2.4/§2.6).
    for r in shipped_results:
        assert r.methodology_opt_in is True
        assert r.expected_exposed_ids
        assert r.exposed_decision_ids_hit


def test_shipped_suite_cli_exit_zero(tmp_path):
    out = tmp_path / "report.json"
    code = main([
        "benchmark", str(SUITE),
        "--memory", str(SUITE / "project_memory.json"),
        "--json", str(out),
    ])
    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    eq = payload["summary"]["enforcement_quality"]
    assert eq["violation_checkable"] == 3
    assert eq["false_positive_rate"] == 0.0

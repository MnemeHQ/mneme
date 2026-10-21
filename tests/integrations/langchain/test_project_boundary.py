"""Project-boundary behavior for writes outside ``project_dir`` (Gap 2).

Regression tests for the proposal in
``docs/plans/2026-10-20-enforcement-coverage-custom-tools-and-project-boundary.md``
section 6.1 (options 2A + 2C). Real ``mneme check`` CLI throughout; no
runtime change. Out-of-root writes are neither universally ungoverned nor
universally blocked: a scoped typed rule yields UNKNOWN applicability (a
visible fail-open, ADR-020 Decision 6), while an unscoped typed rule applies
globally (ADR-020 Decision 3) and is evaluated.

Orchestrator refusals (root confinement, refuse-on-UNEVALUATED) are the
orchestrator's policy. They never become a Mneme block or rule violation.
"""
import copy
import json

import pytest

from mneme.integrations.langchain import (
    ACTION_ALLOW,
    ACTION_DENY,
    ACTION_FAIL_OPEN,
    MnemeLangChain,
)
from tests.integrations.custom_tool_reference import (
    DENY_TAG,
    REFUSED_TAG,
    UNEVALUATED_TAG,
    ReferenceFileTool,
    count_outcomes,
    langchain_evaluator,
    refuse_on_unevaluated,
)
from tests.integrations.relative_paths import (
    BASELINE,
    FORBIDDEN,
    MEMORY,
    VIOLATING,
    RecordingRunner,
    make_layout,
)


@pytest.fixture()
def layout(tmp_path, monkeypatch):
    layout = make_layout(tmp_path, monkeypatch)
    layout.outside = tmp_path / "outside"
    layout.outside.mkdir()
    return layout


def unscoped(layout):
    """Rewrite the fixture rule without ``include_paths`` (global applicability)."""
    memory = copy.deepcopy(MEMORY)
    del memory["decisions"][0]["rules"][0]["include_paths"]
    (layout.project / ".mneme" / "project_memory.json").write_text(
        json.dumps(memory), encoding="utf-8"
    )


def make_gate(layout, runner):
    return MnemeLangChain(project_dir=str(layout.project), mode="strict", check_runner=runner)


def write(gate, path, content):
    return gate.evaluate_tool_call("write_file", {"file_path": str(path), "content": content})


def unknown_rules(sent):
    return [
        (rec.get("decision_id"), rec.get("outcome"))
        for rec in sent.payload.get("applicability", [])
    ]


def test_out_of_root_scoped_rule_unknown_fails_open(layout):
    runner = RecordingRunner()
    result = write(make_gate(layout, runner), layout.outside / "router.py", VIOLATING)

    assert result.action == ACTION_FAIL_OPEN
    assert result.evaluation_complete is False
    assert result.verdict == "PASS"  # untrusted: incomplete evaluation, not a PASS
    # JSON mode carries ADR-020's PATH_APPLICABILITY_UNKNOWN as an UNKNOWN
    # applicability trace; the adapter reason renders it.
    assert unknown_rules(runner.sent[0]) == [("router_001", "UNKNOWN")]
    assert "path applicability is unknown" in result.reason
    assert "router_001" in result.reason
    assert "outside or cannot be resolved against policy root" in result.reason


def test_out_of_root_unscoped_rule_applies(layout):
    # Characterization of proposal section 2.3: an unscoped rule is APPLIED
    # without path normalization, so the out-of-root write is evaluated
    # against the project's memory. If this changes, the integration doc must
    # describe the observed behavior instead.
    unscoped(layout)
    runner = RecordingRunner()
    result = write(make_gate(layout, runner), layout.outside / "router.py", VIOLATING)

    assert result.action == ACTION_DENY
    assert result.evaluation_complete is True
    assert unknown_rules(runner.sent[0]) == [("router_001", "APPLIED")]
    assert "router_001" in result.reason

    # Compliant content out of root is then a complete, trusted PASS.
    compliant = write(make_gate(layout, runner), layout.outside / "other.py", BASELINE)
    assert compliant.action == ACTION_ALLOW
    assert compliant.evaluation_complete is True
    assert unknown_rules(runner.sent[1]) == [("router_001", "APPLIED")]


def test_dotdot_relative_escape_is_out_of_root(layout):
    runner = RecordingRunner()
    gate = make_gate(layout, runner)
    for content in (VIOLATING, BASELINE):
        result = write(gate, "src/../../outside/router.py", content)
        assert result.action == ACTION_FAIL_OPEN
        assert result.action != ACTION_ALLOW
        assert result.evaluation_complete is False
    assert all(
        unknown_rules(sent) == [("router_001", "UNKNOWN")] for sent in runner.sent
    )


def test_out_of_root_never_labeled_allowed(layout):
    runner = RecordingRunner()
    result = write(make_gate(layout, runner), layout.outside / "router.py", BASELINE)

    assert FORBIDDEN not in runner.sent[0].content
    assert result.action == ACTION_FAIL_OPEN
    assert result.action != ACTION_ALLOW


def test_confined_tool_refuses_before_gate(layout):
    runner = RecordingRunner()
    gate = make_gate(layout, runner)
    tool = ReferenceFileTool(langchain_evaluator(gate), layout.project)

    outcomes = [
        tool.save_text(str(layout.outside / "router.py"), VIOLATING),
        tool.save_text("src/../../outside/router.py", VIOLATING),
    ]

    assert runner.sent == []
    assert [e for e in gate.trace if e.get("kind") == "enforcement"] == []
    assert not (layout.outside / "router.py").exists()
    for outcome in outcomes:
        assert outcome.orchestrator_refused is True
        assert outcome.mneme_action is None
        assert outcome.mutated is False
        assert outcome.text.startswith(REFUSED_TAG)
        assert "[mneme]" not in outcome.text
    counts = count_outcomes(outcomes)
    assert counts["orchestrator_refused"] == 2
    assert counts["mneme_blocked"] == 0
    assert counts["not_evaluated"] == 2


def test_orchestrator_refuse_on_unevaluated_wrapper(layout):
    runner = RecordingRunner()
    gate = make_gate(layout, runner)
    target = layout.outside / "router.py"
    handler_runs = []

    def handler():
        handler_runs.append(1)
        target.write_text(VIOLATING, encoding="utf-8")
        return "wrote"

    run = refuse_on_unevaluated(langchain_evaluator(gate), handler)
    outcome = run("write", {"file_path": str(target), "content": VIOLATING})

    assert handler_runs == []
    assert not target.exists()
    # Mneme's own record stays unevaluated; the refusal is not a Mneme FAIL.
    (entry,) = [e for e in gate.trace if e.get("kind") == "enforcement"]
    assert entry["action"] == ACTION_FAIL_OPEN
    assert entry["evaluation_complete"] is False
    assert outcome.mneme_action == ACTION_FAIL_OPEN
    assert outcome.orchestrator_refused is True
    assert outcome.text.startswith(REFUSED_TAG)
    assert UNEVALUATED_TAG in outcome.text
    assert DENY_TAG not in outcome.text
    counts = count_outcomes([outcome])
    assert counts["orchestrator_refused"] == 1
    assert counts["unevaluated"] == 1
    assert counts["mneme_blocked"] == 0
    assert counts["trusted_pass"] == 0


def test_wrapper_does_not_refuse_operational_fail_open(layout):
    # Exactly the proposal's condition: only fail_open with
    # evaluation_complete False is refused. A MaterializeError fail-open
    # (evaluation_complete True in the existing GateResult) is not.
    runner = RecordingRunner()
    gate = make_gate(layout, runner)
    handler_runs = []
    run = refuse_on_unevaluated(
        langchain_evaluator(gate), lambda: handler_runs.append(1) or "edited"
    )

    outcome = run(
        "edit",
        {"file_path": str(layout.project / "src" / "missing.py"),
         "old_string": "a", "new_string": "b"},
    )

    assert outcome.mneme_action == ACTION_FAIL_OPEN
    assert outcome.orchestrator_refused is False
    assert handler_runs == [1]
    assert runner.sent == []


def test_wrapper_deny_does_not_run_handler(layout):
    runner = RecordingRunner()
    gate = make_gate(layout, runner)
    handler_runs = []
    run = refuse_on_unevaluated(
        langchain_evaluator(gate), lambda: handler_runs.append(1) or "wrote"
    )

    outcome = run(
        "write", {"file_path": str(layout.real()), "content": VIOLATING}
    )

    assert outcome.mneme_action == ACTION_DENY
    assert outcome.orchestrator_refused is False
    assert outcome.text.startswith(DENY_TAG)
    assert handler_runs == []
    counts = count_outcomes([outcome])
    assert counts["mneme_blocked"] == 1
    assert counts["orchestrator_refused"] == 0


def test_orchestrator_refusals_counted_separately_from_mneme_blocks(layout):
    """A mixed run: refusals, a Mneme deny and an unevaluated write land in
    separate rows, and only ``allow`` is a trusted PASS."""
    runner = RecordingRunner()
    gate = make_gate(layout, runner)
    confined = ReferenceFileTool(langchain_evaluator(gate), layout.project)
    unconfined = ReferenceFileTool(langchain_evaluator(gate), layout.project, confine=False)
    wrapper = refuse_on_unevaluated(langchain_evaluator(gate), lambda: "wrote")

    outcomes = [
        confined.save_text(str(layout.outside / "a.py"), VIOLATING),        # refused, no gate
        confined.save_text("src/router.py", VIOLATING),                     # Mneme deny
        confined.save_text("src/ok.py", BASELINE),                          # Mneme allow
        unconfined.save_text(str(layout.outside / "b.py"), BASELINE),       # fail_open, written
        wrapper("write", {"file_path": str(layout.outside / "c.py"), "content": BASELINE}),
    ]

    assert count_outcomes(outcomes) == {
        "mneme_blocked": 1,
        "trusted_pass": 1,
        "warned_not_blocked": 0,
        "unevaluated": 2,
        "not_evaluated": 1,
        "orchestrator_refused": 2,
    }

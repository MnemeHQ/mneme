"""Option 1B: a custom tool that explicitly asks Mneme before mutating.

Regression tests for the proposal in
``docs/plans/2026-10-20-enforcement-coverage-custom-tools-and-project-boundary.md``
section 6.1 (Gap 1). The reference tool lives in
``tests/integrations/custom_tool_reference.py``; it is application code, not
a Mneme API. These tests pin opt-in self-governance only: the closed tool map
is unchanged, and a custom tool that never calls the gate stays ungoverned.

Stub-runner tests use the contract-faithful ``check_result_for`` doubles;
path tests use the real ``mneme check`` CLI. Only the two middleware tests
at the bottom need ``langchain``.
"""
import hashlib
import json
from pathlib import Path

import pytest

from mneme.integrations.langchain import (
    ACTION_ALLOW,
    ACTION_DENY,
    ACTION_FAIL_OPEN,
    ACTION_SKIP,
    ACTION_WARN,
    MnemeLangChain,
)
from tests.integrations.check_contract import check_result_for, violation
from tests.integrations.custom_tool_reference import (
    DENY_TAG,
    NOT_EVALUATED_TAG,
    UNEVALUATED_TAG,
    WARN_TAG,
    ReferenceFileTool,
    count_outcomes,
    langchain_evaluator,
    make_dir_link,
    ungoverned_save_text,
)
from tests.integrations.langchain.test_adapter import MEMORY, completed
from tests.integrations.relative_paths import (
    FORBIDDEN,
    TARGET,
    VIOLATING,
    RecordingRunner,
    make_layout,
)

FAIL_VIOLATION = violation("FAIL", decision_id="store_001", rule="psycopg2")


@pytest.fixture()
def project(tmp_path, monkeypatch):
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    monkeypatch.delenv("MNEME_HOOK_MODE", raising=False)
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_text(
        json.dumps(MEMORY), encoding="utf-8"
    )
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path


class CountingRunner:
    """Stub ``mneme check`` answering ``verdict``; records each command."""

    def __init__(self, verdict, **kwargs):
        self.verdict = verdict
        self.kwargs = kwargs
        self.commands = []
        self.inputs = []

    def __call__(self, command, **_):
        self.commands.append(list(command))
        self.inputs.append(
            Path(command[command.index("--input") + 1]).read_text(encoding="utf-8")
        )
        return check_result_for(command, self.verdict, **self.kwargs)

    def target_path(self, index=-1):
        command = self.commands[index]
        return command[command.index("--target-path") + 1]


def make_tool(project, runner, **gate_kwargs):
    gate = MnemeLangChain(project_dir=project, check_runner=runner, **gate_kwargs)
    return gate, ReferenceFileTool(langchain_evaluator(gate), project)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def enforcement(gate):
    return [e for e in gate.trace if e.get("kind") == "enforcement"]


class TestUnwiredToolStaysUngoverned:
    def test_unmapped_tool_still_skipped(self, project):
        runner = CountingRunner("PASS")
        gate = MnemeLangChain(project_dir=project, check_runner=runner)
        result = gate.evaluate_tool_call(
            "save_text", {"path": "app.py", "text": "import psycopg2\n"}
        )
        assert result.action == ACTION_SKIP
        assert result.reason == "not a governed langchain file tool"
        assert runner.commands == []

    def test_unwired_tool_mutates_without_any_check(self, project):
        runner = CountingRunner("FAIL", violations=[FAIL_VIOLATION])
        gate = MnemeLangChain(project_dir=project, check_runner=runner)
        assert ungoverned_save_text(project, "app.py", "import psycopg2\n") == "saved"
        assert (project / "app.py").read_text(encoding="utf-8") == "import psycopg2\n"
        assert runner.commands == []
        assert enforcement(gate) == []


class TestSelfProposalOutcomes:
    def test_self_proposal_deny_prevents_mutation(self, project):
        runner = CountingRunner("FAIL", violations=[FAIL_VIOLATION])
        _, tool = make_tool(project, runner)
        before = digest(project / "app.py")

        outcome = tool.save_text("app.py", "x = 1\nimport psycopg2\n")

        assert outcome.mneme_action == ACTION_DENY
        assert outcome.mutated is False
        assert digest(project / "app.py") == before
        assert len(runner.commands) == 1
        assert runner.target_path() == str((project / "app.py").resolve())
        assert outcome.text.startswith(f"{DENY_TAG} - ")
        assert "store_001" in outcome.text
        assert count_outcomes([outcome])["mneme_blocked"] == 1

    def test_self_proposal_pass_executes(self, project):
        runner = CountingRunner("PASS")
        _, tool = make_tool(project, runner)

        outcome = tool.save_text("util.py", "y = 2\n")

        assert outcome.mneme_action == ACTION_ALLOW
        assert outcome.mutated is True
        assert (project / "util.py").read_bytes() == b"y = 2\n"
        assert len(runner.commands) == 1
        assert outcome.text == "saved"
        assert "[mneme]" not in outcome.text
        assert count_outcomes([outcome])["trusted_pass"] == 1

    def test_self_proposal_warn_mode_proceeds_visibly(self, project):
        runner = CountingRunner(
            "WARN",
            violations=[
                violation("WARN", decision_id="store_001", rule="no postgres", trigger="postgres")
            ],
        )
        _, tool = make_tool(project, runner, mode="warn")

        outcome = tool.save_text("db.py", "# postgres later\n")

        assert runner.commands[0][runner.commands[0].index("--mode") + 1] == "warn"
        assert outcome.mneme_action == ACTION_WARN
        assert outcome.mutated is True
        assert (project / "db.py").read_bytes() == b"# postgres later\n"
        assert f"{WARN_TAG} - " in outcome.text
        assert "not blocked" in outcome.text
        assert "store_001" in outcome.text
        counts = count_outcomes([outcome])
        assert counts["warned_not_blocked"] == 1
        assert counts["trusted_pass"] == 0
        assert counts["mneme_blocked"] == 0

    def test_self_proposal_no_memory_is_not_a_pass(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MNEME_MEMORY", raising=False)
        runner = CountingRunner("PASS")
        _, tool = make_tool(tmp_path, runner)

        outcome = tool.save_text("db.py", "import psycopg2\n")

        assert outcome.mneme_action == ACTION_SKIP
        assert outcome.mneme_action != ACTION_ALLOW
        assert runner.commands == []
        assert f"{NOT_EVALUATED_TAG} - no project memory" in outcome.text
        counts = count_outcomes([outcome])
        assert counts["not_evaluated"] == 1
        assert counts["trusted_pass"] == 0

    def test_self_proposal_fail_open_is_visible(self, project):
        runner = CountingRunner("PASS", complete=False)
        _, tool = make_tool(project, runner)

        outcome = tool.save_text("out.py", "x = 1\n")

        assert outcome.mneme_action == ACTION_FAIL_OPEN
        assert outcome.mutated is True  # documented fail-open policy
        assert f"{UNEVALUATED_TAG} - failing open, this mutation was NOT checked" in outcome.text
        assert outcome.text != "saved"
        counts = count_outcomes([outcome])
        assert counts["unevaluated"] == 1
        assert counts["trusted_pass"] == 0

    @pytest.mark.parametrize(
        "make_proc, problem",
        [
            # A FAIL payload exiting 1 in strict mode is not a verdict (#260).
            (lambda cmd: completed(check_result_for(cmd, "FAIL").stdout, returncode=1),
             "inconsistent verdict payload"),
            (lambda cmd: completed("Traceback (most recent call last): ...", returncode=1),
             "no parseable verdict"),
        ],
    )
    def test_self_proposal_untrusted_output_is_not_a_pass(self, project, make_proc, problem):
        gate = MnemeLangChain(project_dir=project, check_runner=lambda cmd, **_: make_proc(cmd))
        read = []
        evaluate = langchain_evaluator(gate)

        def spying_evaluate(kind, tool_input):
            return _AttributeSpy(evaluate(kind, tool_input), read)

        tool = ReferenceFileTool(spying_evaluate, project)
        outcome = tool.save_text("out.py", "x = 1\n")

        assert outcome.mneme_action == ACTION_FAIL_OPEN
        assert problem in outcome.text
        assert UNEVALUATED_TAG in outcome.text
        # The reference code decides from action and reason only; verdict
        # trust stays in the adapter's existing assess_verdict.
        assert set(read) <= {"action", "reason"}

    def test_self_proposal_edit_missing_file_fails_open(self, project):
        runner = CountingRunner("PASS")
        _, tool = make_tool(project, runner)

        outcome = tool.edit_text("missing.py", "a", "b")

        assert outcome.mneme_action == ACTION_FAIL_OPEN
        assert "cannot materialize" in outcome.text
        assert UNEVALUATED_TAG in outcome.text
        assert runner.commands == []
        assert outcome.mutated is False
        assert not (project / "missing.py").exists()


class _AttributeSpy:
    """Records which ``GateResult`` attributes the reference code reads."""

    def __init__(self, inner, read):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_read", read)

    def __getattr__(self, name):
        self._read.append(name)
        return getattr(self._inner, name)


class TestSamePathSameBytes:
    def test_self_proposal_evaluated_path_and_bytes_match_mutation(self, project):
        runner = CountingRunner("PASS")
        gate = MnemeLangChain(project_dir=project, check_runner=runner)
        proposals = []
        evaluate = langchain_evaluator(gate)

        def spying_evaluate(kind, tool_input):
            proposals.append(dict(tool_input))
            return evaluate(kind, tool_input)

        (project / "pkg").mkdir()
        tool = ReferenceFileTool(spying_evaluate, project)
        text = "first = 'é'\nsecond = 2\n"
        outcome = tool.save_text("pkg/../pkg/./mod.py", text)

        written = project / "pkg" / "mod.py"
        assert outcome.mutated is True
        assert outcome.target == written.resolve()
        assert proposals == [{"file_path": str(written.resolve()), "content": text}]
        assert runner.target_path() == str(written.resolve())
        assert written.read_bytes() == proposals[0]["content"].encode("utf-8")
        # A new file: the whole proposal is the introduced content.
        assert runner.inputs[0] == text

    def test_self_proposal_symlink_out_of_root_refused(self, tmp_path, monkeypatch):
        layout = make_layout(tmp_path, monkeypatch)
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "router.py").write_text("unchanged\n", encoding="utf-8")
        make_dir_link(layout.project / "src" / "linked", outside)
        link_path = "src/linked/router.py"

        # Confined: the canonical path is outside the root, so the tool
        # refuses before Mneme is asked.
        runner = RecordingRunner()
        gate = MnemeLangChain(project_dir=str(layout.project), mode="strict", check_runner=runner)
        confined = ReferenceFileTool(langchain_evaluator(gate), layout.project)
        refused = confined.save_text(link_path, VIOLATING)
        assert refused.orchestrator_refused is True
        assert refused.mneme_action is None
        assert runner.sent == []
        assert (outside / "router.py").read_text(encoding="utf-8") == "unchanged\n"

        # Unconfined: evaluated as the out-of-root target it really is, never
        # as the in-root link path the rule src/** would match.
        open_tool = ReferenceFileTool(langchain_evaluator(gate), layout.project, confine=False)
        outcome = open_tool.save_text(link_path, VIOLATING)
        assert len(runner.sent) == 1
        assert runner.sent[0].target_path == str((outside / "router.py").resolve())
        assert outcome.mneme_action == ACTION_FAIL_OPEN
        assert outcome.mneme_action != ACTION_ALLOW
        assert UNEVALUATED_TAG in outcome.text

    def test_self_proposal_relative_path_uses_project_dir(self, tmp_path, monkeypatch):
        """The tool joins a relative agent path to its root itself, so the gate
        receives an absolute path; the final call also hands the relative
        path straight to the adapter to pin ``project_dir`` resolution."""
        layout = make_layout(tmp_path, monkeypatch)
        # An identical decoy in the process cwd: if it were read as the
        # current snapshot, nothing would be introduced and the gate would skip.
        decoy = layout.decoy(VIOLATING)
        decoy_before = decoy.read_bytes()
        before = layout.real().read_bytes()
        runner = RecordingRunner()
        gate = MnemeLangChain(project_dir=str(layout.project), mode="strict", check_runner=runner)
        tool = ReferenceFileTool(langchain_evaluator(gate), layout.project)

        outcome = tool.save_text(TARGET, VIOLATING)

        assert outcome.mneme_action == ACTION_DENY
        assert len(runner.sent) == 1
        assert runner.sent[0].target_path == str(layout.real().resolve())
        assert FORBIDDEN in runner.sent[0].content
        assert layout.real().read_bytes() == before
        assert decoy.read_bytes() == decoy_before

        direct = gate.evaluate_tool_call("write_file", {"file_path": TARGET, "content": VIOLATING})
        assert direct.action == ACTION_DENY
        assert runner.sent[-1].target_path == str(layout.real())
        assert FORBIDDEN in runner.sent[-1].content


def spied_tool(gate, root):
    """Reference tool whose proposals to the gate are recorded."""
    proposals = []
    evaluate = langchain_evaluator(gate)

    def spying_evaluate(kind, tool_input):
        proposals.append(dict(tool_input))
        return evaluate(kind, tool_input)

    return ReferenceFileTool(spying_evaluate, root), proposals


class TestFullContentSubmission:
    def test_self_proposal_append_submitted_as_full_content(self, tmp_path, monkeypatch):
        layout = make_layout(tmp_path, monkeypatch)
        before = layout.real().read_bytes()
        runner = RecordingRunner()
        gate = MnemeLangChain(project_dir=str(layout.project), mode="strict", check_runner=runner)
        tool, proposals = spied_tool(gate, layout.project)

        appended = f"{FORBIDDEN} = True\n"
        outcome = tool.append_text(TARGET, appended)

        assert outcome.mneme_action == ACTION_DENY
        # The full resulting file is submitted, not just the appended text...
        assert proposals[0]["content"].encode("utf-8") == before + appended.encode("utf-8")
        # ...and only the appended line is introduced (ADR-018).
        assert runner.sent[0].content == f"{FORBIDDEN} = True"
        assert layout.real().read_bytes() == before

    def test_self_proposal_preexisting_literal_not_attributed(self, tmp_path, monkeypatch):
        layout = make_layout(tmp_path, monkeypatch)
        layout.real().write_bytes(VIOLATING.encode("utf-8"))
        runner = RecordingRunner()
        gate = MnemeLangChain(project_dir=str(layout.project), mode="strict", check_runner=runner)
        tool, proposals = spied_tool(gate, layout.project)

        outcome = tool.append_text(TARGET, "RETRIES = 2\n")

        # No #259-shape false block on the pre-existing literal.
        assert outcome.mneme_action == ACTION_ALLOW
        assert runner.sent[0].content == "RETRIES = 2"
        written = layout.real().read_bytes()
        assert written == (VIOLATING + "RETRIES = 2\n").encode("utf-8")
        assert proposals[0]["content"].encode("utf-8") == written


class TestTraceShape:
    def test_trace_has_no_correlation_id(self, project):
        runner = CountingRunner("PASS")
        gate, tool = make_tool(project, runner)

        tool.save_text("util.py", "y = 2\n")

        (entry,) = enforcement(gate)
        assert entry["tool"] == "Write"
        assert "save_text" not in json.dumps(entry)
        # Characterizes the open limit: no call ID crosses the gate.
        assert set(entry) == {
            "kind", "tool", "file_path", "action", "verdict",
            "evaluation_complete", "reason",
        }


class TestUnderMiddleware:
    """The custom tool runs under the shipped middleware with one shared
    ``MnemeLangChain`` instance. Needs the langchain extra."""

    @pytest.fixture(autouse=True)
    def _langchain(self):
        pytest.importorskip("langchain")
        pytest.importorskip("langgraph")

    def _run_agent(self, gate, tool_fn, args):
        from langchain.agents import create_agent
        from langchain_core.messages import HumanMessage

        from tests.integrations.langchain.test_live_fixture import ScriptedChatModel, call

        agent = create_agent(
            model=ScriptedChatModel([call("save_text", args, "c1"), {"content": "done"}]),
            tools=[tool_fn],
            middleware=gate.build_middleware(),
        )
        result = agent.invoke(
            {"messages": [HumanMessage(content="update the storage module")]},
            config={"recursion_limit": 10},
        )
        return " ".join(str(m.content) for m in result["messages"] if m.type == "tool")

    def test_reference_tags_match_middleware(self):
        from mneme.integrations.langchain import middleware

        assert DENY_TAG == middleware.DENY_TAG
        assert WARN_TAG == middleware.WARN_TAG
        assert UNEVALUATED_TAG == middleware.UNEVALUATED_TAG

    def test_middleware_skip_plus_inner_evaluation_counted_once(self, project):
        from langchain_core.tools import tool

        runner = CountingRunner("FAIL", violations=[FAIL_VIOLATION])
        gate = MnemeLangChain(project_dir=project, check_runner=runner)
        reference = ReferenceFileTool(langchain_evaluator(gate), project)
        body_runs = []
        before = digest(project / "app.py")

        @tool
        def save_text(path: str, text: str) -> str:
            """Save text to a file under the project root."""
            body_runs.append(path)
            return reference.save_text(path, text).text

        tool_text = self._run_agent(
            gate, save_text, {"path": "app.py", "text": "x = 1\nimport psycopg2\n"}
        )

        entries = enforcement(gate)
        assert [(e["tool"], e["action"]) for e in entries] == [
            ("save_text", ACTION_SKIP),
            ("Write", ACTION_DENY),
        ]
        assert len(runner.commands) == 1
        # The body runs (the middleware has no opinion on save_text), but the
        # mutation does not.
        assert body_runs == ["app.py"]
        assert digest(project / "app.py") == before
        assert f"{DENY_TAG} - " in tool_text
        assert "store_001" in tool_text
        # Coverage counts the evaluated entry, not the middleware skip.
        evaluated = [e for e in entries if e["action"] != ACTION_SKIP]
        assert len(evaluated) == 1

    def test_unwired_tool_under_middleware_is_ungoverned(self, project):
        from langchain_core.tools import tool

        runner = CountingRunner("FAIL", violations=[FAIL_VIOLATION])
        gate = MnemeLangChain(project_dir=project, check_runner=runner)

        @tool
        def save_text(path: str, text: str) -> str:
            """Save text to a file under the project root."""
            return ungoverned_save_text(project, path, text)

        tool_text = self._run_agent(
            gate, save_text, {"path": "app.py", "text": "import psycopg2\n"}
        )

        assert (project / "app.py").read_text(encoding="utf-8") == "import psycopg2\n"
        assert runner.commands == []
        assert [(e["tool"], e["action"]) for e in enforcement(gate)] == [
            ("save_text", ACTION_SKIP)
        ]
        assert "[mneme]" not in tool_text

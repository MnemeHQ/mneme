"""ADR-034 G2-1: Claude Code ``Write`` routing, consumer trust and evidence.

Pinned regression matrix of the accepted behavioral charter
(docs/plans/2026-10-24-adr-034-g2-1-behavioral-charter.md §8.C), items 5-9
and the routed-hook half of item 10. The checker half lives in
``tests/test_numeric_upper_bound_g2_prewrite.py``.

The hook is driven through its real entry point and the real ``mneme
check`` (in-process transport) on a project whose canonical memory holds a
global ``FORBID_LITERAL`` rule and a ``FORBID_NUMERIC_ABOVE`` rule applicable
to ``src/**``. Built only from the public contract; no G2 validation material
is used or implied. Nothing here is an enforcement claim (charter §7).
"""
from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mneme.integrations.agent_sdk import ACTION_FAIL_OPEN, MnemeAgentSdk
from mneme.integrations.claude_code import availability, hook
from mneme.integrations.claude_code.inprocess_check import run_check_inprocess
from mneme.integrations.langchain import MnemeLangChain
from mneme.numeric_rule import NumericContract
from mneme.rule_identity import rule_id_for
from mneme.schemas import Rule
from tests.canonical_fixtures import canonical_document

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
NUMERIC = Rule(
    type="FORBID_NUMERIC_ABOVE",
    value=NumericContract(
        max="5", unit="seconds", symbol="ROUTER_DEADLINE_S",
        call_function="classify", call_position=1,
    ).canonical_value(),
    include_paths=("src/**",),
)
NUMERIC_ID = rule_id_for("ADR-034T", NUMERIC)

ABOVE = "ROUTER_DEADLINE_S = 60\ndef run(x):\n    return classify(x, 2)\n"
WITHIN = "ROUTER_DEADLINE_S = 3\ndef run(x):\n    return classify(x, 2)\n"
MISSING_CALL = "ROUTER_DEADLINE_S = 3\n"
LITERAL_WITHIN = "import psycopg2\n" + WITHIN
MARKER = "G2_CONTENT_MARKER_7f3a"
HOST = ("2.1.303", "ab" * 32)


def _memory_document(numeric_include=("src/**",)) -> dict:
    return canonical_document({
        "meta": {"name": "numeric-g2", "description": "ADR-034 G2-1"},
        "items": [],
        "decisions": [
            {"id": "LIT-1", "decision": "Do not use psycopg2", "rationale": "r",
             "scope": ["storage"],
             "rules": [{"type": "FORBID_LITERAL", "value": "psycopg2"}],
             "created_at": "2026-10-24", "updated_at": "2026-10-24",
             "status": "active"},
            {"id": "ADR-034T", "decision": "Router deadline at most 5 seconds",
             "rationale": "r", "scope": ["router"],
             "rules": [{"type": NUMERIC.type, "value": NUMERIC.value,
                        "include_paths": list(numeric_include)}],
             "created_at": "2026-10-24", "updated_at": "2026-10-24",
             "status": "active"},
        ],
    })


def _make_project(root: Path, monkeypatch, **kw) -> Path:
    for name in ("MNEME_MEMORY", "MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE",
                 "MNEME_HOOK_EVIDENCE_LOG", "MNEME_HOOK_EVIDENCE_HOST_VERSION",
                 "MNEME_HOOK_EVIDENCE_HOST_SHA256"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MNEME_HOOK_CHECK_TRANSPORT", "inprocess")
    monkeypatch.setenv("MNEME_HOOK_MODE", "strict")
    (root / ".mneme").mkdir(parents=True)
    (root / ".mneme" / "project_memory.json").write_text(
        json.dumps(_memory_document(**kw)), encoding="utf-8"
    )
    (root / "src").mkdir()
    (root / "docs").mkdir()
    return root


@pytest.fixture
def project(tmp_path, monkeypatch):
    return _make_project(tmp_path, monkeypatch)


@pytest.fixture
def closed(project, monkeypatch):
    """An authorized closed availability declaration (ADR-033 C2b)."""
    (project / ".mneme" / "availability.json").write_bytes(
        (FIXTURES / "availability_policy" / "v1" / "valid.json").read_bytes()
    )
    monkeypatch.setattr(availability, "live_verifier", lambda _d: ("AUTHORIZED", ""))
    return project


@pytest.fixture
def calls(monkeypatch):
    """Record every checker invocation, with the carrier bytes it received."""
    seen: list = []
    real_invoke = hook._invoke_check
    real_inprocess = hook._invoke_check_inprocess

    def invoke(*args, **kwargs):
        seen.append({"carrier": kwargs.get("carrier")})
        return real_invoke(*args, **kwargs)

    def inprocess(argv):
        flag = "--proposed-new-file" if "--proposed-new-file" in argv else "--input"
        path = argv[argv.index(flag) + 1]
        seen[-1].update(flag=flag, argv=list(argv), bytes=Path(path).read_bytes())
        proc = real_inprocess(argv)
        seen[-1]["proc"] = proc
        return proc

    monkeypatch.setattr(hook, "_invoke_check", invoke)
    monkeypatch.setattr(hook, "_invoke_check_inprocess", inprocess)
    return seen


def _envelope(project: Path, rel: str, content, *, tool="Write", **extra) -> dict:
    tool_input = {"file_path": str(project / rel)} | extra
    if content is not None:
        tool_input["content"] = content
    return {
        "hook_event_name": "PreToolUse", "tool_name": tool,
        "cwd": str(project), "tool_input": tool_input,
        "session_id": "sess-1", "tool_use_id": "toolu_1",
    }


def _hook(project: Path, rel: str, content, **kw):
    out, err = io.StringIO(), io.StringIO()
    rc = hook.handle_event(_envelope(project, rel, content, **kw), stderr=err, stdout=out)
    return rc, out.getvalue(), err.getvalue()


def _payload(call) -> dict:
    return json.loads(call["proc"].stdout)


def _numeric(payload) -> dict:
    return next(i for i in payload["applicability"] if i["rule_type"] == NUMERIC.type)


# ── §8.C.5 hook routing ──────────────────────────────────────────────────────


def test_routed_write_makes_one_proposed_new_file_call(project, calls):
    rc, out, err = _hook(project, "src/new.py", ABOVE)
    assert rc == 2 and out == ""
    assert len(calls) == 1
    call, = calls
    assert call["flag"] == "--proposed-new-file"
    assert call["carrier"] == call["bytes"] == ABOVE.encode("utf-8")
    argv = call["argv"]
    assert argv[argv.index("--target-path") + 1] == str(project / "src" / "new.py")
    assert argv[argv.index("--query") + 1] == f"edit to {project / 'src' / 'new.py'}"
    assert "--input" not in argv
    assert _payload(call)["subject"]["input_kind"] == "proposed_new_source"
    assert not (project / "src" / "new.py").exists()


def test_routed_relative_file_path_resolves_against_cwd(project, calls):
    envelope = _envelope(project, "x", ABOVE)
    envelope["tool_input"]["file_path"] = "src/new.py"
    out, err = io.StringIO(), io.StringIO()
    assert hook.handle_event(envelope, stderr=err, stdout=out) == 2
    assert calls[0]["flag"] == "--proposed-new-file"


def _unrouted(project: Path, case: str):
    """``(rel, content, extra)`` for an event that must keep today's path."""
    src = project / "src"
    if case == "edit":
        (src / "router.py").write_text(WITHIN, encoding="utf-8")
        return "src/router.py", None, {"tool": "Edit", "old_string": "= 3", "new_string": "= 60"}
    if case == "multiedit":
        (src / "router.py").write_text(WITHIN, encoding="utf-8")
        return "src/router.py", None, {
            "tool": "MultiEdit", "edits": [{"old_string": "= 3", "new_string": "= 60"}],
        }
    if case == "existing":
        (src / "router.py").write_text(WITHIN, encoding="utf-8")
        return "src/router.py", ABOVE, {}
    if case == "existing_empty":
        (src / "router.py").write_bytes(b"")
        return "src/router.py", ABOVE, {}
    if case == "existing_non_utf8":
        (src / "router.py").write_bytes(b"\xff\xfe\x00junk")
        return "src/router.py", ABOVE, {}
    if case == "existing_directory":
        (src / "pkg.py").mkdir()
        return "src/pkg.py", ABOVE, {}
    if case == "non_python":
        return "src/notes.txt", ABOVE, {}
    if case == "uppercase_suffix":
        return "src/new.PY", ABOVE, {}
    raise AssertionError(case)


UNROUTED = [
    "edit", "multiedit", "existing", "existing_empty", "existing_non_utf8",
    "existing_directory", "non_python", "uppercase_suffix",
]


@pytest.mark.parametrize("case", UNROUTED)
def test_unrouted_events_keep_the_input_call(project, calls, case):
    rel, content, extra = _unrouted(project, case)
    _hook(project, rel, content, **extra)
    assert len(calls) <= 1
    for call in calls:
        assert call["carrier"] is None and call["flag"] == "--input"
        payload = _payload(call)
        assert payload.get("subject", {}).get("input_kind") in (None, "unverified_input")


def test_h1_unreadable_existing_file_is_never_routed(project, calls, monkeypatch):
    """An existing file that cannot be read still exists: never new (H1)."""
    target = project / "src" / "router.py"
    target.write_text(WITHIN, encoding="utf-8")
    real_read = Path.read_text

    def unreadable(self, *args, **kwargs):
        if self == target:
            raise PermissionError(13, "denied")
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable)
    _hook(project, "src/router.py", ABOVE)
    call, = calls
    assert call["flag"] == "--input"
    assert _numeric(_payload(call))["primary_reason"] == "INCOMPLETE_SOURCE_INPUT"


def test_lstat_error_in_the_hook_probe_is_not_routed(project, calls, monkeypatch):
    real = os.lstat

    def denied(path, *args, **kwargs):
        if Path(path).name == "new.py":
            raise PermissionError(13, "denied")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", denied)
    _hook(project, "src/new.py", ABOVE)
    assert calls[0]["flag"] == "--input"


def test_relative_path_without_cwd_is_not_routed(project, calls, monkeypatch):
    monkeypatch.chdir(project)
    envelope = _envelope(project, "x", ABOVE)
    envelope["tool_input"]["file_path"] = "src/new.py"
    envelope["cwd"] = ""
    hook.handle_event(envelope, stderr=io.StringIO(), stdout=io.StringIO())
    assert all(call["carrier"] is None for call in calls)


def test_missing_content_is_not_routed(project, calls):
    _hook(project, "src/new.py", None)
    assert all(call["carrier"] is None for call in calls)


def test_missing_parent_directory_is_routed_by_the_hook_but_legacy_in_the_checker(project, calls):
    """The hook probe is advisory; precondition 2 fails in the checker (G2C-O4)."""
    rc, _, err = _hook(project, "src/not_yet/new.py", ABOVE)
    call, = calls
    payload = _payload(call)
    assert payload["subject"]["input_kind"] == "unverified_input"
    assert _numeric(payload)["primary_reason"] == "INCOMPLETE_SOURCE_INPUT"
    assert rc == 0 and "not evaluated on this input" in err


def test_race_file_created_after_the_hook_probe_gives_the_legacy_result(project, monkeypatch):
    target = project / "src" / "new.py"
    real_inprocess = hook._invoke_check_inprocess
    seen = []

    def racing(argv):
        target.write_text("RACE = 1\n", encoding="utf-8")
        proc = real_inprocess(argv)
        seen.append(proc)
        return proc

    monkeypatch.setattr(hook, "_invoke_check_inprocess", racing)
    rc, out, err = _hook(project, "src/new.py", ABOVE)
    payload = json.loads(seen[0].stdout)
    assert payload["subject"]["input_kind"] == "unverified_input"
    assert _numeric(payload)["primary_reason"] == "INCOMPLETE_SOURCE_INPUT"
    assert rc == 0 and out == ""
    assert "not evaluated on this input" in err


def test_unrouted_carrier_stays_text_mode_byte_for_byte(project, monkeypatch):
    """The unrouted path's text-mode carrier (and its CRLF defect) is unchanged."""
    monkeypatch.delenv("MNEME_HOOK_CHECK_TRANSPORT")
    (project / "src" / "router.py").write_text("", encoding="utf-8")
    content = "import psycopg2\r\nX = 1\nY = 2\r\n"
    captured = {}

    def fake_run(command, **kwargs):
        path = command[command.index("--input") + 1]
        captured["bytes"] = Path(path).read_bytes()
        captured["command"] = list(command)
        return run_check_inprocess(command[3:])

    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    _hook(project, "src/router.py", content)
    reference = project / "reference.txt"
    with open(reference, "w", encoding="utf-8") as fh:
        fh.write(content)
    assert captured["bytes"] == reference.read_bytes()
    assert "--proposed-new-file" not in captured["command"]


def test_routed_subprocess_command_shape(project, monkeypatch):
    monkeypatch.delenv("MNEME_HOOK_CHECK_TRANSPORT")
    captured = {}

    def fake_run(command, **kwargs):
        path = command[command.index("--proposed-new-file") + 1]
        captured["bytes"] = Path(path).read_bytes()
        captured["command"] = list(command)
        captured["kwargs"] = kwargs
        return run_check_inprocess(command[3:])

    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    rc, _, _ = _hook(project, "src/new.py", ABOVE)
    command = captured["command"]
    assert rc == 2
    assert command[:4] == [sys.executable, "-m", "mneme", "check"]
    assert command[4:6] == ["--memory", str(project / ".mneme" / "project_memory.json")]
    assert command[6] == "--proposed-new-file"
    assert command[8:] == [
        "--query", f"edit to {project / 'src' / 'new.py'}", "--mode", "strict",
        "--json", "--target-path", str(project / "src" / "new.py"),
    ]
    assert captured["bytes"] == ABOVE.encode("utf-8")
    assert captured["kwargs"]["timeout"] == hook._CHECK_TIMEOUT_SECONDS
    assert not Path(command[7]).exists()


def test_no_numeric_memory_routed_result_is_unchanged(tmp_path, monkeypatch, calls):
    project = tmp_path / "p"
    project.mkdir()
    _make_project(project, monkeypatch, numeric_include=("lib/**",))
    rc, out, err = _hook(project, "src/new.py", "import psycopg2\n")
    call, = calls
    assert call["flag"] == "--proposed-new-file"
    assert (call["proc"].stdout, call["proc"].returncode) == _legacy_run(tmp_path, call)
    assert rc == 2 and "psycopg2" in err


def _legacy_run(tmp_path: Path, call) -> tuple:
    """The legacy ``--input`` run on the same carrier bytes and arguments."""
    carrier = tmp_path / "same_carrier.txt"
    carrier.write_bytes(call["bytes"])
    argv = list(call["argv"])
    index = argv.index("--proposed-new-file")
    argv[index:index + 2] = ["--input", str(carrier)]
    legacy = run_check_inprocess(argv)
    return legacy.stdout, legacy.returncode


# ── §8.C.6 consumer trust ────────────────────────────────────────────────────


def _run_real(project: Path, flag: str, data: bytes, target: Path, mode="strict"):
    carrier = project / "carrier.txt"
    carrier.write_bytes(data)
    argv = ["check", "--memory", str(project / ".mneme" / "project_memory.json"),
            flag, str(carrier), "--query", "q", "--mode", mode, "--json"]
    if flag != "--source-file":
        argv += ["--target-path", str(target)]
    else:
        argv[argv.index(str(carrier))] = str(target)
    proc = run_check_inprocess(argv)
    return proc.stdout, proc.returncode


@pytest.fixture
def payloads(project):
    """One real payload per subject kind, all over the same numeric rule."""
    new = project / "src" / "new.py"
    source = project / "src" / "module.py"
    source.write_bytes(ABOVE.encode())
    out = {
        "proposed_new_source": _run_real(project, "--proposed-new-file", ABOVE.encode(), new),
        "unverified_input": _run_real(project, "--input", ABOVE.encode(), new),
        "complete_source_file": _run_real(project, "--source-file", b"", source),
        "none": _run_real(project, "--input", b"import os\n", project / "docs" / "n.md"),
    }
    # A memory without numeric rules emits no subject: drop the (EXCLUDED)
    # numeric trace and the subject, exactly as that run would.
    excluded = json.loads(out["none"][0])
    excluded.pop("subject")
    excluded["applicability"] = [
        item for item in excluded["applicability"] if item["rule_type"] != NUMERIC.type
    ]
    out["none"] = (json.dumps(excluded), out["none"][1])
    return out


@pytest.mark.parametrize("kind,expected_input,trusted", [
    ("none", "input", True),
    ("unverified_input", "input", True),
    ("proposed_new_source", "input", False),
    ("complete_source_file", "input", False),
    ("none", "proposed_new_file", True),
    ("unverified_input", "proposed_new_file", True),
    ("proposed_new_source", "proposed_new_file", True),
    ("complete_source_file", "proposed_new_file", False),
])
def test_expected_input_contract(payloads, kind, expected_input, trusted):
    stdout, code = payloads[kind]
    assessment = hook.assess_verdict(stdout, code, "strict", expected_input=expected_input)
    assert (assessment.payload is not None) is trusted, (kind, expected_input)
    if not trusted:
        assert assessment.inconsistent
    if expected_input == "input":
        assert hook.assess_verdict(stdout, code, "strict") == assessment


@pytest.mark.parametrize("expected_input", ["input", "proposed_new_file"])
@pytest.mark.parametrize("subject", [{"input_kind": "other"}, {"input_kind": 3}, "x", []])
def test_unknown_or_malformed_subject_kind_is_untrusted(payloads, expected_input, subject):
    stdout, code = payloads["none"]
    payload = json.loads(stdout)
    payload["subject"] = subject
    assessment = hook.assess_verdict(json.dumps(payload), code, "strict",
                                     expected_input=expected_input)
    assert assessment.payload is None and assessment.inconsistent


def test_expected_input_is_keyword_only_and_validated(payloads):
    stdout, code = payloads["none"]
    with pytest.raises(TypeError):
        hook.assess_verdict(stdout, code, "strict", "input")
    with pytest.raises(ValueError):
        hook.assess_verdict(stdout, code, "strict", expected_input="source_file")
    signature = inspect.signature(hook.assess_verdict)
    assert signature.parameters["expected_input"].default == "input"


def _sdk_runner(stdout, code):
    def run(command, **_kw):
        return subprocess.CompletedProcess(command, code, stdout, "")
    return run


@pytest.mark.parametrize("kind", ["proposed_new_source", "complete_source_file"])
def test_sdk_and_langchain_reject_unrequested_source_payloads(project, payloads, kind):
    stdout, code = payloads[kind]
    target = str(project / "src" / "router.py")
    sdk = MnemeAgentSdk(project_dir=project, mode="strict", check_runner=_sdk_runner(stdout, code))
    result = sdk.evaluate_mutation("Write", {"file_path": target, "content": ABOVE},
                                   cwd=str(project))
    assert result.action == ACTION_FAIL_OPEN
    lc = MnemeLangChain(project_dir=str(project), mode="strict",
                        check_runner=_sdk_runner(stdout, code))
    result = lc.evaluate_tool_call("write_file", {"file_path": target, "content": ABOVE},
                                   cwd=str(project))
    assert result.action == ACTION_FAIL_OPEN


CONSUMER_MODULES = [
    "mneme.integrations.agent_sdk.adapter",
    "mneme.integrations.antigravity.adapter",
    "mneme.integrations.codex_cli.gate",
    "mneme.integrations.codex_cli.stop_audit",
    "mneme.integrations.hermes.adapter",
    "mneme.integrations.kiro.hook",
]


def _calls_named(tree: ast.AST, name: str) -> list:
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (getattr(node.func, "id", None) == name or getattr(node.func, "attr", None) == name)
    ]


@pytest.mark.parametrize("module_name", CONSUMER_MODULES)
def test_every_other_consumer_uses_the_default_contract(module_name):
    """Each default consumer shares the hook's validator and passes neither
    new option, so it rejects ``proposed_new_source`` and
    ``complete_source_file`` exactly as ``test_expected_input_contract``
    shows, and keeps today's results for every coherent ``--input`` payload."""
    import importlib

    module = importlib.import_module(module_name)
    assert module.assess_verdict is hook.assess_verdict
    assert module.format_applicability_reason is hook.format_applicability_reason
    tree = ast.parse(inspect.getsource(module))
    verdict_calls = _calls_named(tree, "assess_verdict")
    assert verdict_calls
    for node in verdict_calls + _calls_named(tree, "format_applicability_reason"):
        assert not node.keywords, ast.unparse(node)
    assert "--proposed-new-file" not in inspect.getsource(module)
    assert "--source-file" not in inspect.getsource(module)


def test_hook_unrouted_stop_bash_and_rename_calls_keep_the_default():
    tree = ast.parse(inspect.getsource(hook))
    functions = {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    for name in ("stop_event", "bash_tool_event", "_evaluate_renamed", "_trusted_payload"):
        body = functions[name]
        for call in _calls_named(body, "assess_verdict") + _calls_named(body, "_invoke_check"):
            assert not any(kw.arg in ("expected_input", "carrier") for kw in call.keywords)
        for call in _calls_named(body, "format_applicability_reason"):
            assert not call.keywords
        assert not _calls_named(body, "_route_new_file")
    routed = [
        call for call in _calls_named(tree, "assess_verdict")
        if any(kw.arg == "expected_input" for kw in call.keywords)
    ]
    assert len(routed) == 1


def _tamper_payload(payloads, kind="proposed_new_source"):
    stdout, code = payloads[kind]
    return json.loads(stdout), code


@pytest.mark.parametrize("reason,status,outcome,sources", [
    ("RECOGNIZED", "RECOGNIZED", "VIOLATION", []),
    ("PARTIAL", "PARTIAL", "VIOLATION",
     [{"kind": "call", "line": 2, "reason": "UNRECOGNIZED_FORM"}]),
    ("PARSE_FAILURE", "MATCHER_UNEVALUATED", "UNEVALUATED",
     [{"kind": "module", "line": 1, "reason": "PARSE_FAILURE"}]),
    ("SOURCE_NOT_FOUND", "MATCHER_UNEVALUATED", "UNEVALUATED",
     [{"kind": "call", "line": None, "reason": "SOURCE_NOT_FOUND"}]),
    ("AMBIGUOUS_BINDING", "MATCHER_UNEVALUATED", "UNEVALUATED",
     [{"kind": "symbol", "line": 1, "reason": "AMBIGUOUS_BINDING"}]),
    ("UNRECOGNIZED_FORM", "MATCHER_UNEVALUATED", "UNEVALUATED",
     [{"kind": "symbol", "line": 1, "reason": "UNRECOGNIZED_FORM"}]),
])
@pytest.mark.parametrize("declared", [True, False])
@pytest.mark.parametrize("expected_input", ["input", "proposed_new_file"])
def test_rule1_unverified_subject_never_claims_source_evaluation(
    payloads, reason, status, outcome, sources, declared, expected_input,
):
    payload, code = _tamper_payload(payloads, "unverified_input")
    trace = _numeric(payload)
    primary = None if status == "RECOGNIZED" else reason
    trace.update(matcher_status=status, matcher_outcome=outcome,
                 primary_reason=primary, unknown_sources=sources)
    payload["subject"]["target_path_declared"] = declared
    violated = outcome == "VIOLATION"
    payload["violations"] = [
        {"decision_id": "ADR-034T", "decision_text": "d", "severity": "FAIL",
         "rule": trace["rule_value"], "trigger": "t", "kind": "typed_rule",
         "rule_type": NUMERIC.type, "rule_id": trace["rule_id"]}
    ] if violated else []
    payload["verdict"] = "FAIL" if violated else "PASS"
    payload["evaluation_complete"] = status == "RECOGNIZED"
    code = 2 if (violated or status != "RECOGNIZED") else 0
    assessment = hook.assess_verdict(json.dumps(payload), code, "strict",
                                     expected_input=expected_input)
    assert assessment.payload is None and assessment.inconsistent


@pytest.mark.parametrize("kind", ["proposed_new_source", "complete_source_file"])
@pytest.mark.parametrize("where", ["primary", "unknown_sources"])
def test_rule2_complete_source_is_never_incomplete_input(payloads, kind, where):
    payload, code = _tamper_payload(payloads, kind)
    trace = _numeric(payload)
    trace.update(matcher_status="PARTIAL", matcher_outcome="VIOLATION")
    if where == "primary":
        trace["primary_reason"] = "INCOMPLETE_SOURCE_INPUT"
        trace["unknown_sources"] = [
            {"kind": "input", "line": None, "reason": "INCOMPLETE_SOURCE_INPUT"},
        ]
    else:
        trace["primary_reason"] = "INCOMPLETE_SOURCE_INPUT"
        trace["unknown_sources"] = [
            {"kind": "input", "line": None, "reason": "INCOMPLETE_SOURCE_INPUT"},
            {"kind": "call", "line": 2, "reason": "UNRECOGNIZED_FORM"},
        ]
    payload["evaluation_complete"] = False
    for expected_input in ("input", "proposed_new_file"):
        assessment = hook.assess_verdict(json.dumps(payload), 2, "strict",
                                         expected_input=expected_input)
        assert assessment.payload is None and assessment.inconsistent


def test_rule3_proposed_new_source_requires_an_applied_numeric_rule(payloads):
    payload, _ = _tamper_payload(payloads)
    payload["applicability"] = [
        item for item in payload["applicability"] if item["rule_type"] != NUMERIC.type
    ]
    payload["violations"] = [
        v for v in payload["violations"] if v.get("rule_type") != NUMERIC.type
    ]
    payload["verdict"] = "PASS"
    assessment = hook.assess_verdict(json.dumps(payload), 0, "strict",
                                     expected_input="proposed_new_file")
    assert assessment.payload is None and assessment.inconsistent


def test_rule3_legacy_result_must_satisfy_rule1(payloads):
    stdout, code = payloads["unverified_input"]
    assert hook.assess_verdict(stdout, code, "strict",
                               expected_input="proposed_new_file").payload is not None


def _routed(project: Path, content: str = ABOVE) -> hook._RoutedWrite:
    data = content.encode("utf-8")
    return hook._RoutedWrite(
        target=str(project / "src" / "new.py"), carrier=data,
        carrier_sha256=hashlib.sha256(data).hexdigest(),
    )


def _rebind_digests(payload: dict, digest: str) -> None:
    """A self-consistent payload bound to bytes the hook never wrote."""
    payload["subject"]["subject_sha256"] = digest
    for item in payload["applicability"]:
        if "subject_sha256" in item:
            item["subject_sha256"] = digest


@pytest.mark.parametrize("tamper,problem", [
    (lambda p: _rebind_digests(p, "0" * 64), "subject digest"),
    (lambda p: _numeric(p).update(subject_sha256="0" * 64), "bound to a different subject"),
    (lambda p: p["subject"].update(target_path=str(Path(p["subject"]["target_path"]).with_name("x.py"))),
     "target_path"),
    (lambda p: p["subject"].update(target_path=None), "target_path"),
    (lambda p: p["subject"].update(absence_verified=False), "absence"),
    (lambda p: p["subject"].pop("absence_verified"), "absence"),
], ids=["rule4_subject_digest", "rule4_trace_digest", "rule5_other_target",
        "rule5_no_target", "rule5_absence_false", "rule5_absence_missing"])
def test_rules4_and_5_digest_and_path_joins(project, payloads, tamper, problem):
    payload, code = _tamper_payload(payloads)
    routed = _routed(project)
    proc = subprocess.CompletedProcess([], code, json.dumps(payload), "")
    assert hook._assess_routed(proc, "strict", routed).payload is not None
    tamper(payload)
    proc = subprocess.CompletedProcess([], code, json.dumps(payload), "")
    assessment = hook._assess_routed(proc, "strict", routed)
    assert assessment.payload is None and assessment.inconsistent
    assert problem in assessment.problem


def test_rule4_carrier_mismatch_is_untrusted(project, payloads):
    stdout, code = payloads["proposed_new_source"]
    proc = subprocess.CompletedProcess([], code, stdout, "")
    assessment = hook._assess_routed(proc, "strict", _routed(project, WITHIN))
    assert assessment.payload is None and "routed carrier" in assessment.problem


def test_rule5_path_join_uses_normcase(project, payloads):
    payload, code = _tamper_payload(payloads)
    routed = _routed(project)
    swapped = payload["subject"]["target_path"].swapcase()
    payload["subject"]["target_path"] = swapped
    proc = subprocess.CompletedProcess([], code, json.dumps(payload), "")
    trusted = hook._assess_routed(proc, "strict", routed).payload is not None
    assert trusted is (os.path.normcase(swapped) == os.path.normcase(
        str(Path(routed.target).resolve())))


def test_tampered_routed_join_fails_open_in_the_hook(project, monkeypatch):
    real = hook._invoke_check_inprocess

    def tampering(argv):
        proc = real(argv)
        payload = json.loads(proc.stdout)
        _rebind_digests(payload, "0" * 64)
        return subprocess.CompletedProcess(argv, proc.returncode, json.dumps(payload), "")

    monkeypatch.setattr(hook, "_invoke_check_inprocess", tampering)
    rc, _, err = _hook(project, "src/new.py", ABOVE)
    assert rc == 0
    assert "subject digest does not match the routed carrier" in err


# ── §8.C.7 hook outcomes ─────────────────────────────────────────────────────


def test_strict_blocks_with_the_numeric_contract(project):
    rc, out, err = _hook(project, "src/new.py", ABOVE)
    assert rc == 2 and out == ""
    assert "FORBID_NUMERIC_ABOVE" in err and "must not exceed 5 seconds" in err
    assert not (project / "src" / "new.py").exists()


def test_partial_blocks_and_reports_unknown_sources(project):
    rc, _, err = _hook(project, "src/new.py", "ROUTER_DEADLINE_S = 60\nclassify(x, y)\n")
    assert rc == 2
    assert "numeric typed rule(s) evaluated on the proposed new file" in err
    assert f"{NUMERIC_ID}: PARTIAL (UNRECOGNIZED_FORM)" in err


def test_warn_mode_defers(project, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    rc, out, _ = _hook(project, "src/new.py", ABOVE)
    assert rc == 0
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "defer"
    assert "must not exceed 5 seconds" in decision["permissionDecisionReason"]


def test_within_bound_proceeds(project):
    rc, out, err = _hook(project, "src/new.py", WITHIN)
    assert (rc, out, err) == (0, "", "")


def test_unevaluated_under_open_proceeds_with_routed_diagnostic(project):
    rc, out, err = _hook(project, "src/new.py", MISSING_CALL)
    assert rc == 0 and out == ""
    assert "numeric typed rule(s) evaluated on the proposed new file" in err
    assert f"{NUMERIC_ID}: MATCHER_UNEVALUATED (SOURCE_NOT_FOUND)" in err
    assert "whole-file audit only" not in err


def test_routed_wording_is_a_default_preserving_option(payloads):
    payload, _ = _tamper_payload(payloads)
    trace = _numeric(payload)
    trace.update(matcher_status="MATCHER_UNEVALUATED", matcher_outcome="UNEVALUATED",
                 primary_reason="SOURCE_NOT_FOUND",
                 unknown_sources=[{"kind": "call", "line": None, "reason": "SOURCE_NOT_FOUND"}])
    default = hook.format_applicability_reason(payload)
    assert "whole-file audit only: mneme check --source-file" in default
    routed = hook.format_applicability_reason(payload, routed_new_file=True)
    assert "evaluated on the proposed new file" in routed
    assert default.splitlines()[1:] == routed.splitlines()[1:]
    with pytest.raises(TypeError):
        hook.format_applicability_reason(payload, True)


def test_closed_unevaluated_is_refused_as_evaluation_incomplete(closed):
    rc, _, err = _hook(closed, "src/new.py", MISSING_CALL)
    assert rc == 2
    assert "evaluation=INCOMPLETE; operational refusal." in err
    assert availability.refusal_category("AUTHORIZED", "INCOMPLETE") == "EVALUATION_INCOMPLETE"


def test_closed_complete_new_file_within_bound_proceeds(closed):
    """G2 narrows F2 only for verified-new files with every declared source."""
    rc, _, err = _hook(closed, "src/new.py", WITHIN)
    assert rc == 0
    assert "evaluation=TRUSTED_COMPLETE; availability did not refuse." in err


def test_literal_violation_with_numeric_no_violation_blocks(project):
    rc, _, err = _hook(project, "src/new.py", LITERAL_WITHIN)
    assert rc == 2
    assert "psycopg2" in err and "LIT-1" in err
    assert "ADR-034T" not in err


def test_literal_only_new_non_python_file_is_unchanged(project, calls):
    rc, _, err = _hook(project, "docs/notes.md", "psycopg2\n")
    assert rc == 2 and "LIT-1" in err
    assert calls[0]["flag"] == "--input"


# ── §8.C.8 evidence ──────────────────────────────────────────────────────────


@pytest.fixture
def evidence(project, monkeypatch, tmp_path_factory):
    log = tmp_path_factory.mktemp("evidence") / "events.jsonl"
    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_LOG", str(log))
    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_HOST_VERSION", HOST[0])
    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_HOST_SHA256", HOST[1])
    return log


def _records(log: Path) -> list:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_evidence_record_is_complete_and_joins_by_digest(project, evidence):
    from mneme import __version__

    content = ABOVE + f"# {MARKER}\n"
    rc, _, err = _hook(project, "src/new.py", content)
    assert rc == 2
    record, = _records(evidence)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert record["schema"] == "mneme.hook_evidence/v1"
    assert record["surface"] == "claude_code.PreToolUse"
    assert record["mneme_version"] == __version__
    assert record["host"] == {"version": HOST[0], "executable_sha256": HOST[1]}
    assert record["event"] == {
        "tool_name": "Write", "file_path": str(project / "src" / "new.py"),
        "cwd": str(project),
        "identifiers": {"session_id": "sess-1", "tool_use_id": "toolu_1"},
    }
    assert record["carrier_sha256"] == digest
    subject = record["checker"]["subject"]
    assert record["checker"]["trusted"] is True
    assert subject["input_kind"] == "proposed_new_source"
    assert subject["subject_sha256"] == digest
    assert subject["governed_path"] == "src/new.py"
    assert subject["absence_verified"] is True
    rule, = record["rules"]
    assert rule["rule_id"] == NUMERIC_ID
    assert rule["decision_version_id"].startswith("dver-")
    assert rule["governed_path"] == "src/new.py"
    assert rule["applicability"] == "APPLIED"
    assert (rule["matcher_status"], rule["matcher_outcome"]) == ("RECOGNIZED", "VIOLATION")
    assert record["hook_outcome"] == "refused"
    assert hook.relevant_enforcement_observed(record, HOST)
    line = evidence.read_text(encoding="utf-8")
    assert MARKER not in line and MARKER not in err
    assert "ROUTER_DEADLINE_S = 60" not in line


@pytest.mark.parametrize("mode,content,outcome", [
    ("strict", WITHIN, "proceeded"),
    ("warn", ABOVE, "deferred"),
    ("strict", MISSING_CALL, "proceeded"),
])
def test_evidence_hook_outcome(project, evidence, monkeypatch, mode, content, outcome):
    monkeypatch.setenv("MNEME_HOOK_MODE", mode)
    _hook(project, "src/new.py", content)
    record, = _records(evidence)
    assert record["hook_outcome"] == outcome


def test_evidence_is_written_only_for_routed_events(project, evidence):
    (project / "src" / "router.py").write_text(WITHIN, encoding="utf-8")
    _hook(project, "src/router.py", ABOVE)
    _hook(project, "docs/notes.md", "x\n")
    assert not evidence.exists()


@pytest.mark.parametrize("host_version,host_sha", [
    (None, None), (HOST[0], None), (None, HOST[1]),
    ("2.1.999", HOST[1]), (HOST[0], "cd" * 32),
], ids=["missing", "no_sha", "no_version", "other_version", "other_sha"])
def test_missing_or_mismatched_host_identity_never_supports_the_claim(
    project, evidence, monkeypatch, host_version, host_sha,
):
    for name, value in (("MNEME_HOOK_EVIDENCE_HOST_VERSION", host_version),
                        ("MNEME_HOOK_EVIDENCE_HOST_SHA256", host_sha)):
        if value is None:
            monkeypatch.delenv(name)
        else:
            monkeypatch.setenv(name, value)
    _hook(project, "src/new.py", ABOVE)
    record, = _records(evidence)
    assert not hook.relevant_enforcement_observed(record, HOST)


@pytest.mark.parametrize("pinned", [(None, HOST[1]), (HOST[0], None), ("", ""), (HOST[0], "zz")])
def test_unestablished_pinned_identity_never_supports_the_claim(project, evidence, pinned):
    _hook(project, "src/new.py", ABOVE)
    record, = _records(evidence)
    assert not hook.relevant_enforcement_observed(record, pinned)


TAMPERED_RECORDS = {
    "carrier_digest": lambda r: r.update(carrier_sha256="0" * 64),
    "subject_digest": lambda r: r["checker"]["subject"].update(subject_sha256="0" * 64),
    "untrusted": lambda r: r["checker"].update(trusted=False),
    "no_subject": lambda r: r["checker"].update(subject=None),
    "complete_source_kind": lambda r: r["checker"]["subject"].update(input_kind="complete_source_file"),
    "absence_unverified": lambda r: r["checker"]["subject"].update(absence_verified=False),
    "no_rules": lambda r: r.update(rules=[]),
    "rule_without_version": lambda r: r["rules"][0].update(decision_version_id=""),
    "rule_other_path": lambda r: r["rules"][0].update(governed_path="src/other.py"),
    "rule_not_applied": lambda r: r["rules"][0].update(applicability="EXCLUDED"),
    "other_tool": lambda r: r["event"].update(tool_name="Edit"),
    "no_file_path": lambda r: r["event"].update(file_path=""),
    "other_surface": lambda r: r.update(surface="agent_sdk"),
    "bad_outcome": lambda r: r.update(hook_outcome="allowed"),
    "missing_host": lambda r: r.pop("host"),
    "missing_event": lambda r: r.pop("event"),
}


@pytest.mark.parametrize("name", sorted(TAMPERED_RECORDS))
def test_mismatched_records_never_count(project, evidence, name):
    _hook(project, "src/new.py", ABOVE)
    record, = _records(evidence)
    assert hook.relevant_enforcement_observed(record, HOST)
    tampered = copy.deepcopy(record)
    TAMPERED_RECORDS[name](tampered)
    assert not hook.relevant_enforcement_observed(tampered, HOST)


@pytest.mark.parametrize("record", [None, {}, [], "x", {"host": None}])
def test_missing_or_malformed_records_never_count(record):
    assert not hook.relevant_enforcement_observed(record, HOST)


def test_legacy_routed_result_never_supports_the_claim(project, evidence):
    """A race or failed precondition yields an unverified subject."""
    _hook(project, "src/not_yet/new.py", ABOVE)
    record, = _records(evidence)
    assert record["checker"]["subject"] is None and record["rules"] == []
    assert not hook.relevant_enforcement_observed(record, HOST)


def test_seam_is_inert_when_unset(project, tmp_path_factory, monkeypatch):
    for content in (ABOVE, WITHIN, MISSING_CALL):
        before = set(Path.cwd().iterdir())
        unset = _hook(project, "src/new.py", content)
        assert set(Path.cwd().iterdir()) == before
        log = tmp_path_factory.mktemp("seam") / "events.jsonl"
        monkeypatch.setenv("MNEME_HOOK_EVIDENCE_LOG", str(log))
        assert _hook(project, "src/new.py", content) == unset
        assert len(_records(log)) == 1
        monkeypatch.delenv("MNEME_HOOK_EVIDENCE_LOG")


def test_evidence_write_failure_never_changes_the_outcome(project, monkeypatch, tmp_path_factory):
    unset = _hook(project, "src/new.py", ABOVE)
    directory = tmp_path_factory.mktemp("not_a_file")
    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_LOG", str(directory))
    rc, out, err = _hook(project, "src/new.py", ABOVE)
    assert (rc, out) == unset[:2]
    assert err.startswith(unset[2])
    assert "evidence record could not be written" in err
    assert MARKER not in err


# ── §8.C.9 untouched surfaces ────────────────────────────────────────────────


def test_bash_heredoc_new_python_file_is_not_routed(project, calls):
    target = project / "src" / "new.py"
    envelope = {
        "hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(project),
        "tool_input": {"command": f"cat > {target} <<'EOF'\n{ABOVE}EOF\n"},
    }
    hook.handle_event(envelope, stderr=io.StringIO(), stdout=io.StringIO())
    for call in calls:
        assert call["carrier"] is None and call["flag"] == "--input"


def test_routing_is_reachable_only_from_the_direct_write_gate():
    tree = ast.parse(inspect.getsource(hook))
    callers = [
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and _calls_named(node, "_route_new_file")
    ]
    assert callers == ["_direct_write_event"]


# ── §8.C.10 byte contract (routed hook) ──────────────────────────────────────

BYTE_CASES = {
    "lf": "ROUTER_DEADLINE_S = 60\nclassify(x, 2)\n",
    "crlf": "ROUTER_DEADLINE_S = 60\r\nclassify(x, 2)\r\n",
    "lone_cr": "ROUTER_DEADLINE_S = 60\rclassify(x, 2)\r",
    "mixed": "ROUTER_DEADLINE_S = 60\r\nclassify(x, 2)\rY = 1\n",
    "bom": "﻿ROUTER_DEADLINE_S = 60\nclassify(x, 2)\n",
    "non_ascii": "# résumé — 日本\nété = 'über'\n"
                 "ROUTER_DEADLINE_S = 60\nclassify(x, 2)\n",
    "empty": "",
}


ROUTED_BYTE_CASES = sorted(set(BYTE_CASES) - {"empty"})


@pytest.mark.parametrize("content", ["", "   \n", "\r\n\t"])
def test_blank_new_file_keeps_its_skip(closed, calls, content):
    """ADR-018's blank-delta skip precedes routing: no call, no new refusal."""
    rc, _, err = _hook(closed, "src/new.py", content)
    assert rc == 0 and calls == []
    assert "evaluation=SKIPPED; availability did not refuse." in err


@pytest.mark.parametrize("name", ROUTED_BYTE_CASES)
def test_routed_byte_contract(project, calls, name):
    content = BYTE_CASES[name]
    data = content.encode("utf-8")
    rc, _, _ = _hook(project, "src/new.py", content)
    call, = calls
    assert call["flag"] == "--proposed-new-file"
    assert call["carrier"] == call["bytes"] == data
    payload = _payload(call)
    digest = hashlib.sha256(data).hexdigest()
    assert payload["subject"]["input_kind"] == "proposed_new_source"
    assert payload["subject"]["subject_sha256"] == digest
    assert _numeric(payload)["subject_sha256"] == digest
    trace = _numeric(payload)
    if name == "bom":
        assert trace["primary_reason"] == "PARSE_FAILURE" and rc == 0
    else:
        assert trace["matcher_outcome"] == "VIOLATION" and rc == 2


@pytest.mark.parametrize("name", sorted(BYTE_CASES))
def test_routed_parity_cases_match_input_on_the_same_carrier(tmp_path, monkeypatch, calls, name):
    project = tmp_path / "p"
    project.mkdir()
    _make_project(project, monkeypatch, numeric_include=("lib/**",))
    content = BYTE_CASES[name] + "import psycopg2\n"
    _hook(project, "src/new.py", content)
    call, = calls
    assert call["bytes"] == content.encode("utf-8")
    assert (call["proc"].stdout, call["proc"].returncode) == _legacy_run(tmp_path, call)


def test_lone_surrogate_is_not_routed_and_keeps_todays_behavior(project, calls):
    """Today's text-mode carrier raises on an unencodable surrogate; unchanged."""
    content = "ROUTER_DEADLINE_S = 60\nX = '\ud800'\n"
    with pytest.raises(UnicodeEncodeError):
        _hook(project, "src/new.py", content)
    call, = calls
    assert call["carrier"] is None

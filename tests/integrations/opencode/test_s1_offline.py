"""Offline integration tests for the OpenCode S1 bridge.

The fake host writes the file only after an `allow`. The bridge is asserted to
leave the governed tree byte-identical in every case.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mneme.integrations.opencode import bridge

BRIDGE = [sys.executable, "-m", "mneme.integrations.opencode.bridge"]
_UNSET = object()


def _snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def _entry(outcome: dict, rule_id: str) -> dict:
    return next(
        item
        for item in outcome["evidence"]["applicability"]
        if item["rule_id"] == rule_id
    )


def _request(
    root: Path,
    path: str,
    content: str,
    *,
    tool: str = "write",
    session_id: str = "ses_test",
    call_id: str = "call_1",
    agent: str | None = "test",
    message_id: str | None = "msg_1",
    event_id: str | None = "evt_1",
    session_directory=_UNSET,
):
    return {
        "tool": tool,
        "input": {"path": path, "content": content},
        "sessionDirectory": str(root)
        if session_directory is _UNSET
        else session_directory,
        "sessionID": session_id,
        "callID": call_id,
        "agent": agent,
        "messageID": message_id,
        "eventID": event_id,
        "hostVersion": "2.3.0",
    }


def _run(
    fixture,
    path: str,
    content: str,
    *,
    env: dict[str, str] | None = None,
    authority: Path | None = None,
    cwd: Path | None = None,
    tool: str = "write",
    session_id: str = "ses_test",
    call_id: str = "call_1",
    agent: str | None = "test",
    message_id: str | None = "msg_1",
    event_id: str | None = "evt_1",
    session_directory=_UNSET,
):
    child_env = dict(os.environ)
    for name in ("CLAUDE_PLUGIN_OPTION_MODE", "MNEME_HOOK_MODE"):
        child_env.pop(name, None)
    repo = str(Path(__file__).resolve().parents[3])
    existing = child_env.get("PYTHONPATH", "")
    child_env["PYTHONPATH"] = repo + (os.pathsep + existing if existing else "")
    if env:
        child_env.update(env)
    payload = _request(
        fixture.root,
        path,
        content,
        tool=tool,
        session_id=session_id,
        call_id=call_id,
        agent=agent,
        message_id=message_id,
        event_id=event_id,
        session_directory=session_directory,
    )
    proc = subprocess.run(
        [*BRIDGE, "--authority", str(authority or fixture.authority)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        cwd=str(cwd or fixture.root),
        env=child_env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    return json.loads(proc.stdout.decode("utf-8"))


def test_forbidden_literal_blocks_without_mutating(s1_fixture):
    target = s1_fixture.root / "src" / "handlers" / "new_handler.py"
    before = _snapshot(s1_fixture.root)
    outcome = _run(s1_fixture, "src/handlers/new_handler.py", "import psycopg2\n")
    after = _snapshot(s1_fixture.root)

    assert outcome["decision"] == "block"
    assert outcome["reason"] == "literal_violation"
    assert outcome["claim"] == "execution_observed"
    assert outcome["evidence"]["observation_state"] == "TRUSTED_COMPLETE"
    entry = _entry(outcome, s1_fixture.rule_id)
    assert entry["outcome"] == "APPLIED"
    assert outcome["evidence"]["violated_rule_ids"] == [s1_fixture.rule_id]
    assert any(
        violation["rule_id"] == s1_fixture.rule_id
        for violation in outcome["evidence"]["violations"]
    )
    assert before == after
    assert not target.exists()


def test_compliant_write_allows_and_host_writes_after(s1_fixture):
    content = "VALUE = 1\n"
    target = s1_fixture.root / "src" / "handlers" / "allowed.py"
    outcome = _run(s1_fixture, "src/handlers/allowed.py", content)

    assert outcome["decision"] == "allow"
    assert outcome["claim"] == "execution_observed"
    assert not target.exists()  # the bridge did not write

    target.write_text(content, encoding="utf-8", newline="")
    assert hashlib.sha256(target.read_bytes()).hexdigest() == hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()


def test_excluded_rule_allows_with_execution_observed(s1_fixture):
    (s1_fixture.root / "src" / "other").mkdir()
    outcome = _run(s1_fixture, "src/other/allowed.py", "import psycopg2\n")
    assert outcome["decision"] == "allow"
    assert outcome["claim"] == "execution_observed"
    assert _entry(outcome, s1_fixture.rule_id)["outcome"] == "EXCLUDED"


def test_non_python_target_is_unsupported(s1_fixture):
    outcome = _run(s1_fixture, "src/handlers/allowed.txt", "VALUE = 1\n")
    assert outcome["decision"] == "unsupported"
    assert outcome["reason"] == "non_python_target"
    assert outcome["claim"] == "none"


def test_non_write_tool_is_unsupported(s1_fixture):
    outcome = _run(
        s1_fixture,
        "src/handlers/new_handler.py",
        "VALUE = 1\n",
        tool="edit",
    )
    assert outcome["decision"] == "unsupported"
    assert outcome["reason"] == "unsupported_tool"
    assert outcome["claim"] == "none"


def test_non_complete_content_is_unsupported(s1_fixture):
    outcome = _run(
        s1_fixture,
        "src/handlers/new_handler.py",
        None,
    )
    assert outcome["decision"] == "unsupported"
    assert outcome["reason"] == "non_complete_content"
    assert outcome["claim"] == "none"


def test_empty_content_is_skip(s1_fixture):
    outcome = _run(s1_fixture, "src/handlers/new_handler.py", "")
    assert outcome["decision"] == "skip"
    assert outcome["reason"] == "empty_content"
    assert outcome["claim"] == "none"


def test_existing_target_is_unsupported(s1_fixture):
    (s1_fixture.root / "src" / "handlers" / "existing.py").write_text(
        "VALUE = 0\n", encoding="utf-8"
    )
    outcome = _run(s1_fixture, "src/handlers/existing.py", "VALUE = 1\n")
    assert outcome["decision"] == "unsupported"
    assert outcome["reason"] == "existing_target"
    assert outcome["claim"] == "none"


def test_missing_session_directory_is_unevaluated(s1_fixture):
    outcome = _run(
        s1_fixture,
        "src/handlers/new_handler.py",
        "VALUE = 1\n",
        session_directory=None,
    )
    assert outcome["decision"] == "unevaluated"
    assert outcome["reason"] == "session_directory_unavailable"
    assert outcome["claim"] == "none"


def test_no_memory_is_skip(tmp_path_factory):
    root = tmp_path_factory.mktemp("no-memory")
    (root / "src" / "handlers").mkdir(parents=True)
    authority = root / "authority.json"
    authority.write_text(
        json.dumps(
            {
                "decision_id": "ADR-001",
                "decision_version_id": "dver-" + "0" * 32,
                "rule_id": "ADR-001:FORBID_LITERAL:" + "0" * 32,
                "rule_value": "psycopg2",
                "rule_scope": "src/handlers/**",
            }
        ),
        encoding="utf-8",
    )

    class _Fixture:
        pass

    fixture = _Fixture()
    fixture.root = root
    fixture.authority = authority
    outcome = _run(fixture, "src/handlers/new_handler.py", "import psycopg2\n")
    assert outcome["decision"] == "skip"
    assert outcome["reason"] == "no_memory"
    assert outcome["claim"] == "none"


def test_wrong_authority_is_setup_invalid_open(s1_fixture, tmp_path):
    data = json.loads(s1_fixture.authority.read_text(encoding="utf-8"))
    data["decision_version_id"] = "dver-" + "0" * 32
    wrong = tmp_path / "authority-wrong.json"
    wrong.write_text(json.dumps(data), encoding="utf-8")
    outcome = _run(
        s1_fixture,
        "src/handlers/new_handler.py",
        "VALUE = 1\n",
        authority=wrong,
    )
    assert outcome["decision"] == "setup_invalid"
    assert outcome["reason"] == "authority_version_mismatch"
    assert outcome["claim"] == "none"


def test_warn_mode_allows_with_warning(s1_fixture):
    outcome = _run(
        s1_fixture,
        "src/handlers/new_handler.py",
        "import psycopg2\n",
        env={"MNEME_HOOK_MODE": "warn"},
    )
    assert outcome["decision"] == "allow"
    assert outcome["reason"] == "warn_mode_violation"
    assert outcome["claim"] == "execution_observed"


def test_claude_mode_variable_is_ignored(s1_fixture):
    outcome = _run(
        s1_fixture,
        "src/handlers/new_handler.py",
        "import psycopg2\n",
        env={"CLAUDE_PLUGIN_OPTION_MODE": "warn"},
    )
    assert outcome["decision"] == "block"
    assert outcome["evidence"]["mode"]["value"] == "strict"
    assert outcome["evidence"]["mode"]["claude_env_present"] is True


def test_invalid_mode_falls_back_to_strict(s1_fixture):
    outcome = _run(
        s1_fixture,
        "src/handlers/new_handler.py",
        "import psycopg2\n",
        env={"MNEME_HOOK_MODE": "not-a-mode"},
    )
    assert outcome["decision"] == "block"
    assert outcome["evidence"]["mode"]["value"] == "strict"


def test_cross_directory_session_resolution(s1_fixture, tmp_path_factory):
    other_cwd = tmp_path_factory.mktemp("other-cwd")
    outcome = _run(
        s1_fixture,
        "src/handlers/new_handler.py",
        "import psycopg2\n",
        cwd=other_cwd,
    )
    assert outcome["decision"] == "block"
    assert outcome["evidence"]["target"] == str(
        s1_fixture.root / "src" / "handlers" / "new_handler.py"
    )


@pytest.mark.parametrize(
    "content",
    [
        "import psycopg2\n",
        "import psycopg2",
        "# café\nimport psycopg2\n",
        "import psycopg2  # non-ASCII: café\n",
    ],
)
def test_content_variants_are_evaluated(s1_fixture, content):
    outcome = _run(s1_fixture, "src/handlers/new_handler.py", content)
    assert outcome["decision"] == "block"
    assert outcome["claim"] == "execution_observed"


def test_claim_ceiling_for_non_evaluated_outcomes(s1_fixture, tmp_path_factory):
    no_memory = tmp_path_factory.mktemp("no-memory-claim")
    (no_memory / "src" / "handlers").mkdir(parents=True)

    class _Fixture:
        pass

    fixture = _Fixture()
    fixture.root = no_memory
    fixture.authority = s1_fixture.authority

    cases = [
        _run(fixture, "src/handlers/new_handler.py", "VALUE = 1\n"),  # skip
        _run(s1_fixture, "src/handlers/allowed.txt", "VALUE = 1\n"),  # unsupported
        _run(
            s1_fixture,
            "src/handlers/new_handler.py",
            "VALUE = 1\n",
            session_directory=None,
        ),  # unevaluated
    ]
    assert {case["decision"] for case in cases} == {"skip", "unsupported", "unevaluated"}
    assert all(case["claim"] == "none" for case in cases)


def test_evidence_is_normalized_and_retains_raw_ids(s1_fixture):
    first = _run(
        s1_fixture,
        "src/handlers/new_handler.py",
        "import psycopg2\n",
        session_id="ses_a",
        call_id="call_a",
    )
    second = _run(
        s1_fixture,
        "src/handlers/new_handler.py",
        "import psycopg2\n",
        session_id="ses_b",
        call_id="call_b",
    )

    def projection(outcome):
        evidence = outcome["evidence"]
        return {
            "decision": outcome["decision"],
            "reason": outcome["reason"],
            "claim": outcome["claim"],
            "rule_id": evidence["authority"]["rule_id"],
            "applicability": evidence["applicability"],
            "observation_state": evidence["observation_state"],
            "target": evidence["target"],
            "content_sha256": evidence["content_sha256"],
        }

    assert projection(first) == projection(second)
    assert first["evidence"]["event"]["sessionID"] == "ses_a"
    assert second["evidence"]["event"]["sessionID"] == "ses_b"


def test_target_created_before_evaluation_is_unsupported(s1_fixture):
    target = s1_fixture.root / "src" / "handlers" / "new_handler.py"
    target.write_text("VALUE = 0\n", encoding="utf-8")
    outcome = _run(s1_fixture, "src/handlers/new_handler.py", "VALUE = 1\n")
    assert outcome["decision"] == "unsupported"
    assert outcome["reason"] == "existing_target"


# ---------------------------------------------------------------------------
# B1: absolute targets are target-anchored; relative traversal stays closed.
# ---------------------------------------------------------------------------


def test_absolute_sibling_target_uses_the_sibling_memory(
    tmp_path, project_factory
):
    session = tmp_path / "session"
    session.mkdir()
    sibling = project_factory()
    target = sibling.root / "src" / "handlers" / "new_handler.py"

    class _Fixture:
        pass

    fixture = _Fixture()
    fixture.root = session
    fixture.authority = sibling.authority

    outcome = _run(fixture, str(target), "import psycopg2\n")
    assert outcome["decision"] == "block"
    assert outcome["claim"] == "execution_observed"
    assert outcome["evidence"]["target"] == str(target.resolve())
    assert outcome["evidence"]["memory"]["path"] == str(sibling.memory)
    assert _entry(outcome, sibling.rule_id)["outcome"] == "APPLIED"
    assert not target.exists()


def test_relative_traversal_outside_the_session_stays_unevaluated(
    tmp_path, project_factory
):
    session = tmp_path / "session"
    session.mkdir()
    sibling = project_factory()
    relative = (
        Path("..")
        / sibling.root.name
        / "src"
        / "handlers"
        / "new_handler.py"
    )

    class _Fixture:
        pass

    fixture = _Fixture()
    fixture.root = session
    fixture.authority = sibling.authority

    outcome = _run(fixture, relative.as_posix(), "import psycopg2\n")
    assert outcome["decision"] == "unevaluated"
    assert outcome["reason"] == "target_outside_session_directory"
    assert outcome["claim"] == "none"


def test_missing_parent_is_unsupported_and_default_open(s1_fixture):
    target = s1_fixture.root / "src" / "handlers" / "missing" / "new_handler.py"
    outcome = _run(
        s1_fixture,
        "src/handlers/missing/new_handler.py",
        "import psycopg2\n",
    )
    assert outcome["decision"] == "unsupported"
    assert outcome["reason"] == "target_parent_missing"
    assert outcome["claim"] == "none"
    assert not target.parent.exists()


# ---------------------------------------------------------------------------
# B2: canonical per-rule violation attribution.
# ---------------------------------------------------------------------------


def test_fail_is_attributed_to_the_actual_rule(two_rule_fixture):
    secondary = two_rule_fixture.rule_ids["forbidden_secondary"]
    outcome = _run(
        two_rule_fixture,
        "src/handlers/new_handler.py",
        "forbidden_secondary\n",
    )

    assert outcome["decision"] == "block"
    assert outcome["claim"] == "execution_observed"
    assert outcome["evidence"]["violated_rule_ids"] == [secondary]
    violation_rule_ids = {
        violation["rule_id"] for violation in outcome["evidence"]["violations"]
    }
    assert secondary in violation_rule_ids
    assert two_rule_fixture.rule_id not in violation_rule_ids
    assert _entry(outcome, two_rule_fixture.rule_id)["outcome"] == "APPLIED"


# ---------------------------------------------------------------------------
# B3: evidence copies canonical records; identity gates the claim.
# ---------------------------------------------------------------------------


def test_missing_host_identifiers_downgrade_the_claim(s1_fixture):
    outcome = _run(
        s1_fixture,
        "src/handlers/new_handler.py",
        "import psycopg2\n",
        session_id=None,
        call_id=None,
        agent=None,
        message_id=None,
        event_id=None,
    )

    assert outcome["decision"] == "block"
    assert outcome["claim"] == "none"
    evidence = outcome["evidence"]
    assert evidence["observation_state"] == "TRUSTED_COMPLETE"
    assert evidence["identity"]["complete"] is False
    assert evidence["identity"]["missing"] == [
        "sessionID",
        "callID",
        "agent",
        "messageID",
        "eventID",
    ]
    assert evidence["event"]["tool"] == "write"
    assert evidence["event"]["sessionID"] is None
    assert evidence["host_witness"] is None


def test_missing_call_id_downgrades_the_claim(s1_fixture):
    # The pinned G0 event contract exposes `id` but not `callID`. The plugin
    # must forward the absence, not synthesize a call ID from the event ID.
    outcome = _run(
        s1_fixture,
        "src/handlers/new_handler.py",
        "import psycopg2\n",
        call_id=None,
    )
    assert outcome["decision"] == "block"
    assert outcome["claim"] == "none"
    assert outcome["evidence"]["identity"] == {
        "complete": False,
        "missing": ["callID"],
    }
    assert outcome["evidence"]["event"]["eventID"] == "evt_1"


def test_complete_identity_claims_execution_observed(s1_fixture):
    outcome = _run(s1_fixture, "src/handlers/new_handler.py", "VALUE = 1\n")
    evidence = outcome["evidence"]
    assert evidence["identity"] == {"complete": True, "missing": []}
    assert evidence["event"]["tool"] == "write"
    assert evidence["event"]["agent"] == "test"
    assert evidence["event"]["messageID"] == "msg_1"
    assert evidence["event"]["eventID"] == "evt_1"
    assert evidence["memory"]["selection_reason"] == "DISCOVERED"
    assert evidence["memory"]["selection_walk"] == "unbounded"
    assert outcome["claim"] == "execution_observed"


def test_evidence_copies_canonical_checker_records(s1_fixture, tmp_path_factory):
    evidence_dir = tmp_path_factory.mktemp("canonical-projection")
    log = evidence_dir / "evidence.jsonl"
    content = "import psycopg2\n"
    outcome = _run(
        s1_fixture,
        "src/handlers/new_handler.py",
        content,
        env={"MNEME_OPENCODE_EVIDENCE_LOG": str(log)},
    )
    assert outcome["decision"] == "block"
    record = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])

    carrier = evidence_dir / "carrier.txt"
    carrier.write_text(content, encoding="utf-8", newline="")
    child_env = dict(os.environ)
    repo = str(Path(__file__).resolve().parents[3])
    existing = child_env.get("PYTHONPATH", "")
    child_env["PYTHONPATH"] = repo + (os.pathsep + existing if existing else "")
    for name in ("CLAUDE_PLUGIN_OPTION_MODE", "MNEME_HOOK_MODE"):
        child_env.pop(name, None)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "mneme",
            "check",
            "--memory",
            str(s1_fixture.memory),
            "--input",
            str(carrier),
            "--query",
            "edit to src/handlers/new_handler.py",
            "--mode",
            "strict",
            "--json",
            "--target-path",
            str(s1_fixture.root / "src" / "handlers" / "new_handler.py"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(s1_fixture.root),
        env=child_env,
        check=False,
    )
    payload = json.loads(proc.stdout)
    assert record["applicability"] == payload["applicability"]
    assert record["violations"] == payload["violations"]


# ---------------------------------------------------------------------------
# B4: immutability, byte fidelity, races and the host witness.
# ---------------------------------------------------------------------------


def _clear_bridge_env(monkeypatch):
    for name in (
        "CLAUDE_PLUGIN_OPTION_MODE",
        "MNEME_HOOK_MODE",
        "MNEME_MEMORY",
    ):
        monkeypatch.delenv(name, raising=False)


def _run_inprocess(authority: Path, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    stdin = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8")
    stdout = io.StringIO()
    stderr = io.StringIO()
    previous = sys.stdin, sys.stdout, sys.stderr
    sys.stdin, sys.stdout, sys.stderr = stdin, stdout, stderr
    try:
        assert bridge.main(["--authority", str(authority)]) == 0
    finally:
        sys.stdin, sys.stdout, sys.stderr = previous
    return json.loads(stdout.getvalue())


def _install_write_audit(root: Path):
    active = {"on": True}
    writes: list[tuple[str, str]] = []

    def as_path(value):
        if isinstance(value, bytes):
            value = os.fsdecode(value)
        if isinstance(value, (str, os.PathLike)):
            return Path(os.path.abspath(value))
        return None

    def audit(event, args):
        if not active["on"]:
            return
        if event == "open":
            path, mode, flags = args
            candidate = as_path(path)
            if candidate is None:
                return
            writing = bool(
                isinstance(flags, int)
                and flags
                & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            )
            if isinstance(mode, str):
                writing = writing or any(ch in mode for ch in "wax+")
            if writing and bridge._is_within(candidate, root):
                writes.append((event, str(candidate)))
            return
        if event in {
            "os.remove",
            "os.rename",
            "os.replace",
            "os.mkdir",
            "os.rmdir",
            "os.chmod",
        }:
            for value in args:
                candidate = as_path(value)
                if candidate is not None and bridge._is_within(candidate, root):
                    writes.append((event, str(candidate)))

    sys.addaudithook(audit)
    return active, writes


def test_bridge_never_writes_under_the_governed_root(s1_fixture, monkeypatch):
    for name in (
        "CLAUDE_PLUGIN_OPTION_MODE",
        "MNEME_HOOK_MODE",
        "MNEME_MEMORY",
    ):
        monkeypatch.delenv(name, raising=False)
    active, writes = _install_write_audit(s1_fixture.root)
    before = _snapshot(s1_fixture.root)
    try:
        outcome = _run_inprocess(
            s1_fixture.authority,
            _request(
                s1_fixture.root,
                "src/handlers/new_handler.py",
                "import psycopg2\n",
            ),
        )
    finally:
        active["on"] = False
    after = _snapshot(s1_fixture.root)

    target = s1_fixture.root / "src" / "handlers" / "new_handler.py"
    assert outcome["decision"] == "block"
    assert writes == []
    assert before == after
    assert not target.exists()


@pytest.mark.skipif(
    os.name == "nt",
    reason=(
        "the shared text-mode carrier translates newlines on Windows; byte "
        "fidelity requires the pinned non-Windows host"
    ),
)
@pytest.mark.parametrize(
    "content",
    [
        "VALUE = 1\n",
        "VALUE = 1\r\n",
        "# café\nVALUE = 1\n",
        "VALUE = 1",
    ],
)
def test_byte_fidelity_and_carrier_isolation(
    s1_fixture, monkeypatch, content
):
    _clear_bridge_env(monkeypatch)
    captured: dict[str, object] = {}
    real_unlink = os.unlink

    def capture(path):
        candidate = Path(path)
        if candidate.suffix == ".txt" and not bridge._is_within(
            candidate, s1_fixture.root
        ):
            captured["path"] = candidate
            captured["bytes"] = candidate.read_bytes()
        return real_unlink(path)

    monkeypatch.setattr(os, "unlink", capture)
    outcome = _run_inprocess(
        s1_fixture.authority,
        _request(s1_fixture.root, "src/handlers/bytes.py", content),
    )
    assert outcome["decision"] == "allow"
    assert outcome["evidence"]["content_sha256"] == hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()

    carrier_path = captured["path"]
    carrier_bytes = captured["bytes"]
    assert not bridge._is_within(carrier_path, s1_fixture.root)
    assert not carrier_path.exists()

    target = s1_fixture.root / "src" / "handlers" / "bytes.py"
    target.write_bytes(content.encode("utf-8"))
    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert hashlib.sha256(carrier_bytes).hexdigest() == expected
    assert hashlib.sha256(target.read_bytes()).hexdigest() == expected


def test_event_content_sha256_matches_on_every_host(s1_fixture, monkeypatch):
    _clear_bridge_env(monkeypatch)
    content = "# café\r\nVALUE = 1"
    outcome = _run_inprocess(
        s1_fixture.authority,
        _request(s1_fixture.root, "src/handlers/event_hash.py", content),
    )
    assert outcome["decision"] == "allow"
    assert outcome["evidence"]["content_sha256"] == hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()


def _race_request(root: Path, name: str) -> bridge.Request:
    return bridge.Request(
        tool="write",
        path=f"src/handlers/{name}.py",
        content="VALUE = 1\n",
        session_directory=str(root),
        session_id="ses_race",
        call_id="call_race",
        agent="test",
        message_id="msg_race",
        event_id="evt_race",
        host_version="2.3.0",
    )


def test_race_target_appears_during_evaluation(s1_fixture, monkeypatch):
    _clear_bridge_env(monkeypatch)
    authority = bridge.load_authority(str(s1_fixture.authority))
    target = s1_fixture.root / "src" / "handlers" / "race_a.py"
    real_invoke = bridge._invoke_check

    def raced(*args, **kwargs):
        proc = real_invoke(*args, **kwargs)
        target.write_text("RACE\n", encoding="utf-8")
        return proc

    monkeypatch.setattr(bridge, "_invoke_check", raced)
    outcome = bridge.evaluate(_race_request(s1_fixture.root, "race_a"), authority)

    assert target.exists()
    if outcome.decision == "allow":
        classification = "UNDETECTED_RACE"
    elif outcome.decision == "unevaluated":
        classification = "DETECTED"
    else:
        classification = f"UNEXPECTED_{outcome.decision}"
    assert classification in {"DETECTED", "UNDETECTED_RACE"}


def test_race_substitutions_after_evaluation(s1_fixture, monkeypatch):
    _clear_bridge_env(monkeypatch)
    authority = bridge.load_authority(str(s1_fixture.authority))
    handlers = s1_fixture.root / "src" / "handlers"
    summary: dict[str, str] = {}

    # (b) Target appears between the bridge decision and the host write.
    target_b = handlers / "race_b.py"
    outcome_b = bridge.evaluate(_race_request(s1_fixture.root, "race_b"), authority)
    target_b.write_text("HOST\n", encoding="utf-8")
    assert target_b.read_text(encoding="utf-8") == "HOST\n"
    summary["b"] = (
        "UNDETECTED_RACE"
        if outcome_b.decision == "allow"
        else "DETECTED"
    )

    # (c) Symlink introduced at the target after evaluation.
    target_c = handlers / "race_c.py"
    decoy_c = handlers / "race_c_decoy.py"
    decoy_c.write_text("DECOY\n", encoding="utf-8")
    outcome_c = bridge.evaluate(_race_request(s1_fixture.root, "race_c"), authority)
    try:
        target_c.symlink_to(decoy_c)
    except OSError:
        pytest.skip("symlink race fixture unavailable on this host")
    target_c.write_text("HOST\n", encoding="utf-8")
    assert decoy_c.read_text(encoding="utf-8") == "HOST\n"
    summary["c"] = (
        "UNDETECTED_RACE" if outcome_c.decision == "allow" else "DETECTED"
    )

    # (d) Hardlink substituted after evaluation.
    target_d = handlers / "race_d.py"
    decoy_d = handlers / "race_d_decoy.py"
    decoy_d.write_text("DECOY\n", encoding="utf-8")
    outcome_d = bridge.evaluate(_race_request(s1_fixture.root, "race_d"), authority)
    try:
        os.link(decoy_d, target_d)
    except OSError:
        pytest.skip("hardlink race fixture unavailable on this host")
    target_d.write_text("HOST\n", encoding="utf-8")
    assert decoy_d.read_text(encoding="utf-8") == "HOST\n"
    summary["d"] = (
        "UNDETECTED_RACE" if outcome_d.decision == "allow" else "DETECTED"
    )

    assert set(summary.values()) <= {"DETECTED", "UNDETECTED_RACE"}
    race_resistance = (
        "NOT_ESTABLISHED"
        if any(value == "UNDETECTED_RACE" for value in summary.values())
        else "ESTABLISHED"
    )
    assert race_resistance == "NOT_ESTABLISHED"


class _FakeOpenCodeHost:
    """Minimal host boundary: refuse on block, write on any other decision."""

    def __init__(self) -> None:
        self.witness: dict | None = None

    def apply(self, outcome: dict, target: Path, content: str) -> bool:
        if outcome["decision"] == "block":
            self.witness = {
                "refused": True,
                "tool_status": "error",
                "tool_error": f"Mneme BLOCK: {outcome['reason']}",
                "target_state": "absent" if not target.exists() else "present",
            }
            return False
        target.write_text(content, encoding="utf-8", newline="")
        self.witness = {
            "refused": False,
            "tool_status": "ok",
            "target_state": "present" if target.exists() else "absent",
        }
        return True


def test_block_does_not_imply_host_prevention(s1_fixture):
    target = s1_fixture.root / "src" / "handlers" / "new_handler.py"
    blocked = _run(s1_fixture, "src/handlers/new_handler.py", "import psycopg2\n")
    host = _FakeOpenCodeHost()
    applied = host.apply(blocked, target, "import psycopg2\n")

    assert applied is False
    assert host.witness == {
        "refused": True,
        "tool_status": "error",
        "tool_error": "Mneme BLOCK: literal_violation",
        "target_state": "absent",
    }
    assert blocked["evidence"]["host_witness"] is None
    assert not target.exists()

    allowed_target = s1_fixture.root / "src" / "handlers" / "allowed.py"
    allowed = _run(s1_fixture, "src/handlers/allowed.py", "VALUE = 1\n")
    host = _FakeOpenCodeHost()
    applied = host.apply(allowed, allowed_target, "VALUE = 1\n")

    assert applied is True
    assert host.witness == {
        "refused": False,
        "tool_status": "ok",
        "target_state": "present",
    }
    assert allowed["evidence"]["host_witness"] is None
    assert "refused" not in json.dumps(allowed["evidence"])
    assert allowed_target.exists()

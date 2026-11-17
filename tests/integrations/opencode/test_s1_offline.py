"""Offline integration tests for the OpenCode S1 bridge.

The fake host writes the file only after an `allow`. The bridge is asserted to
leave the governed tree byte-identical in every case.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BRIDGE = [sys.executable, "-m", "mneme.integrations.opencode.bridge"]
_UNSET = object()


def _snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def _request(
    root: Path,
    path: str,
    content: str,
    *,
    tool: str = "write",
    session_id: str = "ses_test",
    call_id: str = "call_1",
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
        "agent": "test",
        "messageID": "msg_1",
        "eventID": "evt_1",
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
        session_directory=session_directory,
    )
    proc = subprocess.run(
        [*BRIDGE, "--authority", str(authority or fixture.authority)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        cwd=str(cwd or fixture.root),
        env=child_env,
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
    assert outcome["evidence"]["applicability"] == "APPLIED"
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
    assert outcome["evidence"]["applicability"] == "EXCLUDED"


def test_non_python_target_is_unsupported(s1_fixture):
    outcome = _run(s1_fixture, "src/handlers/allowed.txt", "VALUE = 1\n")
    assert outcome["decision"] == "unsupported"
    assert outcome["reason"] == "non_python_target"
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

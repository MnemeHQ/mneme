"""Offline integration tests for the OpenCode E1 edit surface.

The bridge is executed as a subprocess against a real memory and a real checker.
The bridge must never mutate the target; file state is asserted before and after.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from mneme.integrations.claude_code import hook

BRIDGE = [sys.executable, "-m", "mneme.integrations.opencode.bridge"]
SCHEMA = "mneme.opencode.bridge/v1"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _run(fixture, path, old, new, *, replace_all=None, mode="strict", authority=None,
         call_id="call_1"):
    payload = {
        "schema": SCHEMA,
        "tool": "edit",
        "input": {"path": path, "oldString": old, "newString": new},
        "sessionDirectory": str(fixture.root),
        "sessionID": "ses_test",
        "callID": call_id,
        "agent": "test",
        "messageID": "msg_1",
        "eventID": "evt_1",
        "hostVersion": "2.3.0",
    }
    if replace_all is not None:
        payload["input"]["replaceAll"] = replace_all

    env = dict(os.environ)
    for name in ("CLAUDE_PLUGIN_OPTION_MODE", "MNEME_HOOK_MODE"):
        env.pop(name, None)
    repo = str(Path(__file__).resolve().parents[3])
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = repo + (os.pathsep + existing if existing else "")
    env["MNEME_HOOK_MODE"] = mode

    proc = subprocess.run(
        [*BRIDGE, "--authority", str(authority or fixture.authority)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _seed(root: Path, path: str, content: str) -> Path:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    return target


def test_e1_block_introduced_literal(s1_fixture):
    target = _seed(s1_fixture.root, "src/handlers/db.py", "A = 1\n")
    before = target.read_bytes()

    outcome = _run(s1_fixture, "src/handlers/db.py", "A = 1", "import psycopg2")

    assert outcome["decision"] == "block"
    assert outcome["reason"] == "literal_violation"
    assert outcome["claim"] == "execution_observed"
    assert outcome["evidence"]["observation_state"] == "TRUSTED_COMPLETE"
    assert target.read_bytes() == before, "the bridge must never mutate the target"


def test_e1_allow_compliant_edit(s1_fixture):
    _seed(s1_fixture.root, "src/handlers/repo.py", "A = 1\n")
    outcome = _run(s1_fixture, "src/handlers/repo.py", "A = 1", "B = 2")
    assert outcome["decision"] == "allow"
    assert outcome["reason"] == "no_violation"


def test_e1_remediation_is_allowed(s1_fixture):
    """ADR-018: removing an existing violation is not blocked by it."""
    _seed(s1_fixture.root, "src/handlers/legacy.py", "import psycopg2\nKEEP = 0\n")
    outcome = _run(
        s1_fixture,
        "src/handlers/legacy.py",
        "import psycopg2\n",
        "from .storage import adapter\n",
    )
    assert outcome["decision"] == "allow"
    assert outcome["reason"] == "no_violation"


def test_e1_preexisting_violation_elsewhere_is_allowed(s1_fixture):
    """ADR-018: untouched pre-existing debt does not block an unrelated edit."""
    _seed(s1_fixture.root, "src/handlers/mixed.py", "import psycopg2\nOLD = 0\n")
    outcome = _run(s1_fixture, "src/handlers/mixed.py", "OLD = 0", "OLD = 1")
    assert outcome["decision"] == "allow"


def test_e1_ambiguous_is_unevaluated(s1_fixture):
    target = _seed(s1_fixture.root, "src/handlers/dup.py", "V = 1\nMID = 0\nV = 1\n")
    before = target.read_bytes()
    outcome = _run(s1_fixture, "src/handlers/dup.py", "V = 1", "V = 2")
    assert outcome["decision"] == "unevaluated"
    assert outcome["reason"] == "ambiguous_old_string"
    assert outcome["claim"] == "none"
    assert target.read_bytes() == before


def test_e1_no_match_is_unevaluated(s1_fixture):
    _seed(s1_fixture.root, "src/handlers/none.py", "ALPHA = 1\n")
    outcome = _run(s1_fixture, "src/handlers/none.py", "ABSENT", "X")
    assert outcome["decision"] == "unevaluated"
    assert outcome["reason"] == "old_string_not_found"


def test_e1_replace_all_evaluates_every_occurrence(s1_fixture):
    """E1-U1/E1-08: the whole replace-all delta is evaluated, not the first hit."""
    content = "A = 1\nMID = 0\nA = 1\nMID = 0\nA = 1\n"
    _seed(s1_fixture.root, "src/handlers/all.py", content)
    expected = hook.introduced_between(content, content.replace("A = 1", "import psycopg2"))
    assert expected.count("psycopg2") == 3

    outcome = _run(
        s1_fixture,
        "src/handlers/all.py",
        "A = 1",
        "import psycopg2",
        replace_all=True,
    )

    mat = outcome["evidence"]["materialisation"]
    assert mat["replacement_count"] == -1
    assert mat["occurrences"] == 3
    assert mat["ambiguous"] is False
    assert mat["evaluated_sha256"] == _sha(expected)
    assert outcome["decision"] == "block"


def test_e1_authority_mismatch_is_setup_invalid(s1_fixture, tmp_path):
    _seed(s1_fixture.root, "src/handlers/auth.py", "A = 1\n")
    bad = tmp_path / "authority.json"
    data = json.loads(s1_fixture.authority.read_text(encoding="utf-8"))
    data["rule_value"] = "different"
    bad.write_text(json.dumps(data), encoding="utf-8")

    outcome = _run(s1_fixture, "src/handlers/auth.py", "A = 1", "B = 2", authority=bad)
    assert outcome["decision"] == "setup_invalid"
    assert outcome["claim"] == "none"


def test_e1_non_python_target_is_unsupported(s1_fixture):
    _seed(s1_fixture.root, "notes.txt", "A = 1\n")
    outcome = _run(s1_fixture, "notes.txt", "A = 1", "B = 2")
    assert outcome["decision"] == "unsupported"
    assert outcome["reason"] == "non_python_target"


def test_e1_missing_target_is_unsupported(s1_fixture):
    outcome = _run(s1_fixture, "src/handlers/absent.py", "A", "B")
    assert outcome["decision"] == "unsupported"
    assert outcome["reason"] == "target_missing"


def test_e1_claim_is_none_without_call_id(s1_fixture):
    """The six-identifier ceiling still applies to edits."""
    _seed(s1_fixture.root, "src/handlers/ident.py", "A = 1\n")
    payload_outcome = _run(
        s1_fixture, "src/handlers/ident.py", "A = 1", "B = 2", call_id=None
    )
    assert payload_outcome["claim"] == "none"
    assert payload_outcome["evidence"]["identity"]["missing"] == ["callID"]

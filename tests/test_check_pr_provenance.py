"""Tests for the PR Execution provenance gate.

The validator runs in CI from the GitHub event payload and locally from
``--body-file`` / ``--body -`` so agents can check a PR body before opening it.
"""
import importlib.util
import io
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_pr_provenance.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_pr_provenance", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load()

AGENT_BODY = """## Summary

Adds a thing.

## Execution provenance

- Change author: agent
- Agent: claude-code
- Agent model: claude-opus-5-5
- Agent session: not-exposed
- Task origin: claude
- Human owner: @TheoV823
"""

HUMAN_BODY = """## Execution provenance

- Change author: human
- Agent: none
- Agent model: n/a
- Agent session: n/a
- Task origin: manual
- Human owner: @TheoV823
"""

PLACEHOLDER_BODY = """## Execution provenance

- Change author: <!-- human | agent | mixed -->
- Agent: <!-- none | codex | claude-code | kiro | chatgpt-work | other concrete agent -->
- Agent model: <!-- n/a for human-only; otherwise model id or not-exposed -->
- Agent session: <!-- n/a for human-only; otherwise stable session id / share URL / not-exposed -->
- Task origin: <!-- manual | chatgpt | claude | local | other -->
- Human owner: <!-- @github-username -->
"""


def test_missing_block_fails():
    assert gate.validate("## Summary\n\nNo provenance here.\n") == [
        "missing '## Execution provenance' block"
    ]


def test_unresolved_placeholders_fail_every_field():
    errors = gate.validate(PLACEHOLDER_BODY)
    assert errors == [f"missing or unresolved field: {label}" for label in gate.FIELDS.values()]


def test_valid_agent_provenance_passes():
    assert gate.validate(AGENT_BODY) == []


def test_valid_human_provenance_passes():
    assert gate.validate(HUMAN_BODY) == []


# --- input sources -----------------------------------------------------------


def test_body_file(tmp_path, capsys):
    body = tmp_path / "body.md"
    body.write_text(AGENT_BODY, encoding="utf-8")
    assert gate.main(["--body-file", str(body)]) == 0
    assert "PASS" in capsys.readouterr().out


def test_body_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(PLACEHOLDER_BODY.encode("utf-8"))))
    assert gate.main(["--body", "-"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_body_rejects_literal_text():
    with pytest.raises(SystemExit):
        gate.main(["--body", "inline text"])


def test_no_args_reads_github_event(tmp_path, monkeypatch):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"body": HUMAN_BODY}}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    assert gate.main([]) == 0


def test_no_args_without_event_path_errors(monkeypatch):
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    assert gate.main([]) == 2

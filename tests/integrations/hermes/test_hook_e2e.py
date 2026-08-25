"""End-to-end: Hermes payload -> adapter -> real `mneme check` subprocess.

No fakes: exercises the identical CLI contract the Claude Code hook uses.
"""

import json

import pytest

from mneme.integrations.hermes.adapter import ACTION_ALLOW, ACTION_DENY, MnemeHermes


@pytest.fixture()
def governed(tmp_path):
    mem = tmp_path / ".mneme" / "project_memory.json"
    mem.parent.mkdir(parents=True, exist_ok=True)
    mem.write_text(
        json.dumps(
            {
                "meta": {"name": "fixture", "description": "test project memory"},
                "version": 1,
                "decisions": [
                    {
                        "id": "D1",
                        "decision": "never do the bad thing",
                        "scope": ["storage"],
                        "rules": [{"type": "FORBID_LITERAL", "value": "FORBIDDEN_TOKEN"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_forbidden_write_blocks_end_to_end(governed):
    gate = MnemeHermes(project_dir=str(governed))
    result = gate.evaluate_tool_call(
        "write_file",
        {"path": str(governed / "new.py"), "content": "x = FORBIDDEN_TOKEN\n"},
        cwd=str(governed),
    )
    assert result.action == ACTION_DENY
    assert "D1" in result.reason


def test_compliant_write_passes_end_to_end(governed):
    gate = MnemeHermes(project_dir=str(governed))
    result = gate.evaluate_tool_call(
        "write_file",
        {"path": str(governed / "new.py"), "content": "clean = True\n"},
        cwd=str(governed),
    )
    assert result.action == ACTION_ALLOW

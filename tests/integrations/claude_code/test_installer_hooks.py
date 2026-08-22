"""Legacy installer merges guidance and enforcement hooks independently."""

import json

from scripts.install_claude_code import _merge_settings


TEMPLATE = {
    "hooks": {
        "UserPromptSubmit": [{
            "hooks": [{
                "type": "command",
                "command": "mneme-guidance-hook",
                "args": [],
                "timeout": 5,
            }],
        }],
        "PreToolUse": [{
            "matcher": "Edit|Write|MultiEdit",
            "hooks": [{
                "type": "command",
                "command": "mneme-hook",
                "args": [],
                "timeout": 30,
            }],
        }],
    }
}


def test_upgrade_adds_guidance_when_enforcement_already_exists(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({
        "hooks": {"PreToolUse": [{
            "matcher": "Edit|Write|MultiEdit",
            "hooks": [{"type": "command", "command": "mneme-hook"}],
        }]},
    }), encoding="utf-8")
    merged = _merge_settings(settings, TEMPLATE)
    installed = merged["hooks"]["PreToolUse"][0]["hooks"][0]
    assert installed == TEMPLATE["hooks"]["PreToolUse"][0]["hooks"][0]
    assert merged["hooks"]["UserPromptSubmit"] == (
        TEMPLATE["hooks"]["UserPromptSubmit"]
    )


def test_merge_is_idempotent_for_both_events(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps(TEMPLATE), encoding="utf-8")
    once = _merge_settings(settings, TEMPLATE)
    settings.write_text(json.dumps(once), encoding="utf-8")
    twice = _merge_settings(settings, TEMPLATE)
    assert twice == once


def test_merge_preserves_unrelated_user_hooks(tmp_path):
    settings = tmp_path / "settings.json"
    unrelated = {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "user-audit"}],
    }
    settings.write_text(json.dumps({
        "hooks": {"PreToolUse": [unrelated]},
    }), encoding="utf-8")
    merged = _merge_settings(settings, TEMPLATE)
    assert merged["hooks"]["PreToolUse"][0] == unrelated
    assert merged["hooks"]["PreToolUse"][1] == (
        TEMPLATE["hooks"]["PreToolUse"][0]
    )

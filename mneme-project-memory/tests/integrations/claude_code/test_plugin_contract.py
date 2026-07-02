"""Deterministic, platform-independent contract tests for the Claude Code plugin.

These assert the shape of the bundled plugin's manifest and hook wiring without
running Claude Code or invoking any shell — so they catch regressions such as
reintroducing a shell-string launcher or breaking the exec-form invocation.
"""
import json
from pathlib import Path

import pytest

PLUGIN_ROOT = (
    Path(__file__).resolve().parents[3] / "integrations" / "claude-code-plugin"
)


def _load(rel):
    return json.loads((PLUGIN_ROOT / rel).read_text(encoding="utf-8"))


def test_plugin_dir_exists():
    assert PLUGIN_ROOT.is_dir(), f"plugin dir missing at {PLUGIN_ROOT}"


def test_manifest_is_valid_and_declares_mode_option():
    manifest = _load(".claude-plugin/plugin.json")
    assert manifest["name"] == "mneme"
    mode = manifest["userConfig"]["mode"]
    assert mode["type"] == "string"
    assert mode["default"] in ("strict", "warn")


def test_manifest_omits_explicit_version_during_development():
    """During active development the manifest declares no explicit `version`, so
    git-source installs key on the commit SHA (no per-update version bump). Add
    a version only when entering a stable marketplace release cycle."""
    manifest = _load(".claude-plugin/plugin.json")
    assert "version" not in manifest


def test_hook_uses_exec_form_direct_invocation():
    hooks = _load("hooks/hooks.json")
    pre = hooks["hooks"]["PreToolUse"]
    assert len(pre) == 1
    group = pre[0]
    assert group["matcher"] == "Edit|Write|MultiEdit"
    inner = group["hooks"]
    assert len(inner) == 1
    hook = inner[0]
    assert hook["type"] == "command"
    # Exec form: command is the bare console script, args present (empty vector).
    assert hook["command"] == "mneme-hook"
    assert hook["args"] == []


def test_hook_command_has_no_shell_dependency():
    """Regression guard: the launcher must not reintroduce a shell string
    (POSIX operators / interpreter probing / ${CLAUDE_PLUGIN_ROOT} path)."""
    hook = _load("hooks/hooks.json")["hooks"]["PreToolUse"][0]["hooks"][0]
    command = hook["command"]
    for banned in ("command -v", "||", "&&", "$(", ";", "python", "CLAUDE_PLUGIN_ROOT", ".py", ".sh"):
        assert banned not in command, f"hook command must not contain {banned!r}: {command!r}"


def test_no_wrapper_script_remains():
    """The Python wrapper was removed in favor of direct exec-form invocation."""
    assert not (PLUGIN_ROOT / "scripts").exists()


def test_all_bundled_commands_present():
    names = {p.stem for p in (PLUGIN_ROOT / "commands").glob("*.md")}
    assert names == {"context", "check", "record", "review"}


def test_skill_present():
    assert (PLUGIN_ROOT / "skills" / "mneme" / "SKILL.md").is_file()

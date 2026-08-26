"""Installer contract: idempotent, project-scoped, never clobbers foreign hooks."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.install_kiro import HOOK_NAME, compute_target, install

TEMPLATE = Path(__file__).resolve().parents[3] / "integrations" / "kiro" / "hooks" / "mneme.json"


# --- hook JSON schema and matcher (documented v1 field reference) ---

def test_template_matches_documented_kiro_schema():
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert template["version"] == "v1"
    assert isinstance(template["hooks"], list) and len(template["hooks"]) == 1
    hook = template["hooks"][0]
    assert hook["name"] == HOOK_NAME
    assert hook["trigger"] == "PreToolUse"
    # Matcher is a regex over the tool name covering the canonical name and
    # its documented aliases plus append.
    assert hook["matcher"] == "^(fs_write|fsWrite|write|fs_append)$"
    assert hook["action"]["type"] == "command"
    assert hook["action"]["command"] == "mneme-kiro-hook"
    assert hook["enabled"] is True
    assert isinstance(hook.get("timeout", 60), int)


def test_compute_target_fresh():
    content = compute_target(None)
    assert content["hooks"][0]["name"] == HOOK_NAME


def test_compute_target_preserves_foreign_hooks_and_upserts_ours():
    existing = {
        "version": "v1",
        "hooks": [
            {"name": "lint-on-save", "trigger": "PostFileSave",
             "action": {"type": "command", "command": "npx eslint --fix"}},
            {"name": HOOK_NAME, "trigger": "PreToolUse",
             "action": {"type": "command", "command": "/old/stale/path"}},
        ],
    }
    content = compute_target(existing)
    names = [h["name"] for h in content["hooks"]]
    assert names.count(HOOK_NAME) == 1
    assert "lint-on-save" in names
    ours = next(h for h in content["hooks"] if h["name"] == HOOK_NAME)
    assert ours["action"]["command"] == "mneme-kiro-hook"


# --- installation behavior ---

@pytest.fixture
def project(tmp_path):
    return tmp_path


def test_install_creates_file(project):
    target = install(project)
    assert target == project / ".kiro" / "hooks" / "mneme.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["hooks"][0]["name"] == HOOK_NAME


def test_install_is_idempotent(project):
    first = install(project).read_bytes()
    second = install(project).read_bytes()
    assert first == second


def test_second_install_reports_no_change(project, capsys):
    install(project)
    capsys.readouterr()
    install(project)
    assert "no change" in capsys.readouterr().out


def test_install_preserves_foreign_hooks_on_disk(project):
    hooks_path = project / ".kiro" / "hooks" / "mneme.json"
    hooks_path.parent.mkdir(parents=True)
    foreign = {
        "version": "v1",
        "hooks": [{
            "name": "lint-on-save", "trigger": "PostFileSave",
            "matcher": "\\.(ts|tsx)$",
            "action": {"type": "command", "command": "npx eslint --fix"},
        }],
    }
    hooks_path.write_text(json.dumps(foreign), encoding="utf-8")
    install(project)
    payload = json.loads(hooks_path.read_text(encoding="utf-8"))
    names = [h["name"] for h in payload["hooks"]]
    assert "lint-on-save" in names
    assert HOOK_NAME in names


def test_install_refuses_to_clobber_invalid_json(project):
    hooks_path = project / ".kiro" / "hooks" / "mneme.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(SystemExit):
        install(project)
    assert hooks_path.read_text(encoding="utf-8") == "{ not json"


def test_install_refuses_non_v1_hooks_file(project):
    hooks_path = project / ".kiro" / "hooks" / "mneme.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(json.dumps({"version": "v2", "hooks": []}), encoding="utf-8")
    with pytest.raises(SystemExit):
        install(project)
    assert json.loads(hooks_path.read_text(encoding="utf-8"))["version"] == "v2"


def test_main_entry_point_installs_into_given_directory(tmp_path):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[3] / "scripts" / "install_kiro.py"),
         str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".kiro" / "hooks" / "mneme.json").is_file()

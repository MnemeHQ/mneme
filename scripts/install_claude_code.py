#!/usr/bin/env python3
"""Install Mneme integration into the user's Claude Code config.

Idempotent. Prints a preview and asks for confirmation before writing.
Targets `.claude/` in the current working directory by default
(project-scoped); pass --user for `~/.claude/`.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS = REPO_ROOT / "integrations" / "claude-code"


def _merge_settings(target: Path, template: dict) -> dict:
    existing: dict = {}
    if target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
    hooks = existing.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])
    # Idempotency: don't double-add our matcher.
    for entry in pre:
        if entry.get("matcher") == "Edit|Write|MultiEdit" and any(
            h.get("command") == "mneme-hook" for h in entry.get("hooks", [])
        ):
            return existing
    pre.extend(template["hooks"]["PreToolUse"])
    return existing


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Install Mneme integration into Claude Code config."
    )
    ap.add_argument(
        "--user",
        action="store_true",
        help="Install to ~/.claude instead of ./.claude",
    )
    ap.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = ap.parse_args()

    base = Path.home() / ".claude" if args.user else Path.cwd() / ".claude"
    settings_path = base / "settings.json"
    commands_dir = base / "commands"
    skills_dir = base / "skills" / "mneme"

    template = json.loads((ASSETS / "hooks.json").read_text(encoding="utf-8"))
    merged = _merge_settings(settings_path, template)

    print(f"Will install Mneme integration to: {base}")
    print(f"  {settings_path}  (merge PreToolUse hook)")
    print(f"  {commands_dir}/mneme-*.md  (4 slash commands)")
    print(f"  {skills_dir}/SKILL.md  (discovery skill)")

    if not args.yes:
        resp = input("Proceed? [y/N] ").strip().lower()
        if resp != "y":
            print("Aborted.")
            return 1

    base.mkdir(parents=True, exist_ok=True)
    commands_dir.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)

    settings_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    for cmd in (ASSETS / "commands").glob("*.md"):
        shutil.copy(cmd, commands_dir / cmd.name)
    shutil.copy(ASSETS / "skills" / "mneme" / "SKILL.md", skills_dir / "SKILL.md")

    print("Done. Restart Claude Code to pick up new hooks / commands / skills.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

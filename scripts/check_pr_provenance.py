#!/usr/bin/env python3
"""Validate the pull request Execution provenance block."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

FIELDS = {
    "change author": "Change author",
    "agent": "Agent",
    "agent model": "Agent model",
    "agent session": "Agent session",
    "task origin": "Task origin",
    "human owner": "Human owner",
}


def _event_body() -> str:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        raise RuntimeError("GITHUB_EVENT_PATH is not set")
    payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    return str((payload.get("pull_request") or {}).get("body") or "")


def _extract(body: str) -> dict[str, str]:
    values: dict[str, str] = {}
    in_block = False
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if re.match(r"^##\s+Execution provenance\s*$", line, flags=re.I):
            in_block = True
            continue
        if in_block and line.startswith("## "):
            break
        if not in_block:
            continue
        match = re.match(r"^-\s*([^:]+):\s*(.*)$", line)
        if match:
            key = match.group(1).strip().lower()
            if key in FIELDS:
                values[key] = match.group(2).strip()
    return values


def _usable(value: str) -> bool:
    return bool(value.strip()) and "<!--" not in value and "-->" not in value


def validate(body: str) -> list[str]:
    if not re.search(r"^##\s+Execution provenance\s*$", body, flags=re.I | re.M):
        return ["missing '## Execution provenance' block"]

    values = _extract(body)
    errors: list[str] = []
    for key, label in FIELDS.items():
        if key not in values or not _usable(values[key]):
            errors.append(f"missing or unresolved field: {label}")
    if errors:
        return errors

    author = values["change author"].lower()
    if author not in {"human", "agent", "mixed"}:
        errors.append("Change author must be one of: human, agent, mixed")

    agent = values["agent"].lower()
    model = values["agent model"].lower()
    session = values["agent session"].lower()

    if author == "human":
        if agent != "none":
            errors.append("human-only work must use 'Agent: none'")
        if model != "n/a":
            errors.append("human-only work must use 'Agent model: n/a'")
        if session != "n/a":
            errors.append("human-only work must use 'Agent session: n/a'")
    elif author in {"agent", "mixed"}:
        if agent in {"none", "n/a", "unknown"}:
            errors.append("agent/mixed work must name the concrete agent")
        if model in {"", "n/a", "unknown"}:
            errors.append("agent/mixed work must provide a model id or 'not-exposed'")
        if session in {"", "n/a", "unknown"}:
            errors.append("agent/mixed work must provide a session reference or 'not-exposed'")

    owner = values["human owner"]
    if not owner.startswith("@") or len(owner) < 2:
        errors.append("Human owner must be a GitHub username beginning with @")

    return errors


def main() -> int:
    try:
        body = _event_body()
    except Exception as exc:
        print(f"provenance-check: ERROR: {exc}", file=sys.stderr)
        return 2

    errors = validate(body)
    if errors:
        print("provenance-check: FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("provenance-check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

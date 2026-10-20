"""Shared fixtures for the relative-path materialization regression (#571).

A relative tool path must name the same file for both halves of the gate:
the ``--target-path`` handed to ``mneme check`` (ADR-020 applicability) and
the current snapshot the introduced delta is diffed against (ADR-018). Every
scenario here runs with the host process cwd set to a *different* directory
that may hold a same-named decoy, which is how #570 observed the defect.

Checks run through the real ``mneme check`` CLI so DENY / PASS verdicts are
the enforcer's own, not a test double's. The recording runner only captures
what the gate sent before delegating to ``subprocess.run``.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

FORBIDDEN = "DISABLE_ROUTER_TIMEOUT"
TARGET = "src/router.py"
BASELINE = "TIMEOUT_SECONDS = 5\n"
VIOLATING = BASELINE + f"{FORBIDDEN} = True\n"

MEMORY = {
    "meta": {
        "name": "relative-path-fixture",
        "description": "Fixture for relative-path materialization tests (#571)",
        "version": "0.1.0",
        "owner": "test",
        "created": "2026-10-20",
    },
    "items": [],
    "decisions": [
        {
            "id": "router_001",
            "decision": "The router deadline must never be disabled",
            "rationale": "a hung upstream must not hang the caller",
            "scope": ["router"],
            "rules": [
                {
                    "type": "FORBID_LITERAL",
                    "value": FORBIDDEN,
                    "include_paths": ["src/**"],
                }
            ],
        }
    ],
}


@dataclass
class Layout:
    """``project`` is governed; ``elsewhere`` is the host process cwd."""

    project: Path
    elsewhere: Path

    def real(self, rel: str = TARGET) -> Path:
        return self.project / rel

    def decoy(self, content: str, rel: str = TARGET) -> Path:
        path = self.elsewhere / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


def make_layout(tmp_path: Path, monkeypatch) -> Layout:
    project = tmp_path / "project"
    (project / ".mneme").mkdir(parents=True)
    (project / ".mneme" / "project_memory.json").write_text(
        json.dumps(MEMORY), encoding="utf-8"
    )
    (project / "src").mkdir()
    (project / "src" / "router.py").write_text(BASELINE, encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    monkeypatch.delenv("MNEME_HOOK_MODE", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_MODE", raising=False)
    monkeypatch.chdir(elsewhere)
    return Layout(project=project, elsewhere=elsewhere)


@dataclass
class Sent:
    content: str
    target_path: str
    payload: dict


@dataclass
class RecordingRunner:
    """``subprocess.run`` that records each check before running it for real."""

    sent: List[Sent] = field(default_factory=list)

    def __call__(self, command, **kwargs):
        command = list(command)
        content = Path(command[command.index("--input") + 1]).read_text(encoding="utf-8")
        target = (
            command[command.index("--target-path") + 1]
            if "--target-path" in command
            else ""
        )
        proc = subprocess.run(command, **kwargs)
        try:
            payload = json.loads(proc.stdout)
        except (TypeError, ValueError):
            payload = {}
        self.sent.append(Sent(content=content, target_path=target, payload=payload))
        return proc


def applicability_paths(sent: Sent) -> List[tuple]:
    return [
        (rec.get("input_path"), rec.get("outcome"))
        for rec in sent.payload.get("applicability", [])
    ]

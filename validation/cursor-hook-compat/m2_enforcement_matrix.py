#!/usr/bin/env python3
"""M2 enforcement-matrix runner for the Cursor x Mneme compatibility validation.

Exercises ``mneme-hook.exe`` directly with Cursor-shaped ``preToolUse`` payloads.
These are the deterministic, hook-level cells of the M2 matrix. Agent-only cells
(T3 block->recover, T6 multi-file) require a live Cursor agent chat and are
recorded separately.

The fixture and its memory are referenced relative to this file's parent, so the
script is portable across checkouts. It writes no files into the fixture.

Usage:
    python validation/cursor-hook-compat/m2_enforcement_matrix.py
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "fixture"
MEMORY = FIXTURE / ".mneme" / "project_memory.json"

FORBID_GLOBAL = "install legacy-client"
FORBID_SCOPED = "install cursor-only-client"


def run_hook(tool_name: str, tool_input: dict, *, cwd: str = "", memory: bool = True,
             hook_exe: str = "mneme-hook.exe"):
    payload = json.dumps({
        "model": "default",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "hook_event_name": "preToolUse",
        "cursor_version": "3.17.8",
        "cwd": cwd,
        "workspace_roots": [str(FIXTURE).replace("\\", "/")],
    })
    env = dict(os.environ)
    if memory:
        env["MNEME_MEMORY"] = str(MEMORY)
    else:
        env.pop("MNEME_MEMORY", None)
    env["MNEME_HOOK_MODE"] = "strict"
    proc = subprocess.run(
        [hook_exe], input=payload, capture_output=True, text=True, timeout=30, env=env
    )
    return proc.returncode, proc.stdout, proc.stderr


def classify(rc: int, stderr: str) -> str:
    if rc == 2:
        return "BLOCK"
    return "ALLOW"


def decision_id(stderr: str) -> str:
    for line in (stderr or "").splitlines():
        line = line.strip()
        if line.startswith("["):
            return line.split("]")[0].lstrip("[")
    return ""


def main() -> int:
    rows: list[tuple[str, str, str, str]] = []

    def cell(test: str, desc: str, rc: int, stderr: str) -> None:
        rows.append((test, desc, classify(rc, stderr), decision_id(stderr)))

    rc, _, err = run_hook("Write", {"file_path": str(FIXTURE / "t1_ok.txt"),
                                    "content": "clean content\n"})
    cell("T1", "allowed direct write (clean)", rc, err)

    rc, _, err = run_hook("Write", {"file_path": str(FIXTURE / "t2_bad.txt"),
                                    "content": FORBID_GLOBAL + " x\n"})
    cell("T2", "governed violation (global literal, Write)", rc, err)

    target = FIXTURE / "t2b_target.txt"
    target.write_text("base line\n", encoding="utf-8")
    rc, _, err = run_hook("Edit", {"file_path": str(target), "old_string": "base line",
                                   "new_string": FORBID_GLOBAL + " replacement"})
    cell("T2b", "governed violation (global literal, Edit)", rc, err)
    target.unlink(missing_ok=True)

    src_dir = FIXTURE / "src"
    src_dir.mkdir(exist_ok=True)
    rc, _, err = run_hook("Write", {"file_path": str(src_dir / "t4.txt"),
                                    "content": FORBID_SCOPED + " x\n"})
    cell("T4a", "scoped literal OUTSIDE .cursor/ (expect ALLOW)", rc, err)

    cursor_dir = FIXTURE / ".cursor"
    cursor_dir.mkdir(exist_ok=True)
    rc, _, err = run_hook("Write", {"file_path": str(cursor_dir / "t4.txt"),
                                    "content": FORBID_SCOPED + " x\n"})
    cell("T4b", "scoped literal INSIDE .cursor/ (expect BLOCK)", rc, err)
    cursor_dir.rmdir()
    src_dir.rmdir()

    rc, _, err = run_hook("Write", {"file_path": str(FIXTURE / "t5_new.txt"),
                                    "content": FORBID_GLOBAL + "\n"})
    cell("T5", "new/whole-file write, forbidden (expect BLOCK)", rc, err)

    rc, _, err = run_hook("Write", {"file_path": str(FIXTURE / "t7a.txt"),
                                    "content": FORBID_GLOBAL + "\n"}, memory=True)
    cell("T7a", "env-pinned MNEME_MEMORY -> CUR-001 (expect BLOCK)", rc, err)

    rc, _, err = run_hook("Write", {"file_path": str(FIXTURE / "t7b.txt"),
                                    "content": FORBID_GLOBAL + "\n"},
                          cwd=str(FIXTURE), memory=False)
    cell("T7b", "cwd discovery, no override -> CUR-001 (expect BLOCK)", rc, err)

    rc, _, err = run_hook("Shell", {"command": f"printf '%s' '{FORBID_GLOBAL}' > x.sh"})
    cell("T8", "Shell/redirection write (expect BYPASS=ALLOW)", rc, err)

    rc, _, err = run_hook("Delete", {"file_path": str(FIXTURE / "t9.txt")})
    cell("T9", "Delete/rename surface (expect BYPASS=ALLOW)", rc, err)

    print(f"{'Test':6}{'Description':58}{'Result':8}Decision")
    print("-" * 100)
    for test, desc, verdict, did in rows:
        print(f"{test:6}{desc:58}{verdict:8}{did}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

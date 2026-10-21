#!/usr/bin/env python3
"""Added PreToolUse latency of the ADR-033 C2b verifier (charter §12).

Reported, not gated. Architecture A keeps no cache, so every direct write in
an enrolled repository pays for live verification. Cells:

- ``https_tip``: the network work of an AUTHORIZED verification against a
  public HTTPS repository: ``ls-remote``, a depth-1 blobless fetch of the tip,
  then the declaration and canonical-memory reads. No public repository has
  an authorized declaration yet, so this times the same Git operations on
  the repository's existing ``.mneme/project_memory.json``.
- ``https_absent``: a full ``verify()`` of that repository, whose tip has no
  declaration: the history walk that labels ``VERIFIED_ABSENT``. It runs
  only while a local declaration exists without a baseline one, as during an
  enrollment PR, and can never cause a refusal.
- ``hook_*``: the real hook in-process (``handle_event``, subprocess check
  transport) against a local test remote. ``hook_no_declaration`` is the
  unchanged default path. ``hook_h2_authorized_pass`` and
  ``hook_h1_authorized_missing_memory`` include a local verification. These
  isolate hook overhead from network time.

    python benchmarks/availability_verifier/run.py --runs 20 \\
        --out benchmarks/availability_verifier/results/<date>-<os>.json
"""
from __future__ import annotations

import argparse
import io
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from mneme import availability_authority as aa  # noqa: E402
from mneme.integrations.claude_code import availability, hook  # noqa: E402
from tests.integrations.claude_code.test_availability_c2b import (  # noqa: E402
    ACTIVE_MEMORY, Baseline,
)


def _stats(samples: list[float]) -> dict:
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
    return {"n": len(samples), "median_ms": round(statistics.median(samples) * 1000, 1),
            "p95_ms": round(p95 * 1000, 1), "min_ms": round(ordered[0] * 1000, 1)}


def _time(fn, runs: int, warmup: int) -> list[float]:
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return samples


def https_tip(url: str) -> None:
    session = aa._GitSession(url, allow_file=False, timeout=aa._VERIFIER_TIMEOUT_SECONDS)
    try:
        session.init()
        _, tip = session.tip()
        session.fetch(tip, full=False)
        session.has_path(tip, aa.DECLARATION_PATH)
        session.read(tip, aa.MEMORY_PATH)
    finally:
        session.close()


def https_absent(root: Path) -> None:
    result = aa.verify(root)
    if result.authorization != aa.VERIFIED_ABSENT:
        raise SystemExit(f"expected VERIFIED_ABSENT, got {result}")


def _hook(target: Path, expected: int) -> None:
    envelope = {"hook_event_name": "PreToolUse", "tool_name": "Write",
                "cwd": str(target.parent),
                "tool_input": {"file_path": str(target), "content": "value = 1\n"}}
    rc = hook.handle_event(envelope, stderr=io.StringIO(), stdout=io.StringIO())
    if rc != expected:
        raise SystemExit(f"hook returned {rc}, expected {expected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--absent-runs", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--url", default="https://github.com/MnemeHQ/mneme")
    parser.add_argument("--absent-root", default=str(REPO_ROOT),
                        help="A checkout whose origin is --url (for https_absent)")
    parser.add_argument("--out")
    args = parser.parse_args()
    for name in ("MNEME_MEMORY", "MNEME_HOOK_MODE", "MNEME_HOOK_CHECK_TRANSPORT"):
        os.environ.pop(name, None)

    cells: dict[str, dict] = {}
    cells["https_tip"] = _stats(_time(lambda: https_tip(args.url), args.runs, args.warmup))
    cells["https_absent"] = _stats(_time(lambda: https_absent(Path(args.absent_root)),
                                         args.absent_runs, 1))

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        plain = tmp_path / "plain"
        (plain / ".mneme").mkdir(parents=True)
        (plain / ".mneme" / "project_memory.json").write_bytes(ACTIVE_MEMORY)
        cells["hook_no_declaration"] = _stats(
            _time(lambda: _hook(plain / "service.py", 0), args.runs, args.warmup))

        (tmp_path / "enrolled").mkdir()
        base = Baseline(tmp_path / "enrolled")
        base.write(aa.MEMORY_PATH, ACTIVE_MEMORY)
        base.commit("memory")
        base.add_event("authorize")
        base.publish()
        availability.live_verifier = lambda d: aa.verify(d.root, allow_file=True)
        cells["hook_h2_authorized_pass"] = _stats(
            _time(lambda: _hook(base.work / "service.py", 0), args.runs, args.warmup))
        memory = base.work / aa.MEMORY_PATH
        memory.unlink()
        cells["hook_h1_authorized_missing_memory"] = _stats(
            _time(lambda: _hook(base.work / "service.py", 2), args.runs, args.warmup))

    git_version = subprocess.run(["git", "--version"], capture_output=True, text=True).stdout
    report = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "git": git_version.strip(),
        "url": args.url,
        "cells": cells,
    }
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

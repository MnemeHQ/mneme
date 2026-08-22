"""Run the locked post-R6 storage targeting 2x2 mechanism experiment.

This wrapper reuses the frozen R6 mechanism runner.  It changes only the
experiment-specific task prompts, schedule, lock path, and output directory.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
R6_RUNNER_PATH = REPO_ROOT / "scripts" / "run_guidance_confirmatory_ab.py"
DESIGN_LOCK = (
    REPO_ROOT
    / "docs"
    / "validation"
    / "pre-generation-guidance-storage-target-2x2-design-lock.json"
)
EXECUTION_LOCK = (
    REPO_ROOT
    / "docs"
    / "validation"
    / "pre-generation-guidance-storage-target-2x2-execution-lock.json"
)
EXECUTION_CHECKSUM = EXECUTION_LOCK.with_suffix(".sha256")
OUTPUT_ROOT = (
    REPO_ROOT
    / "docs"
    / "validation"
    / "artifacts"
    / "pre-generation-guidance-storage-target-2x2-2026-08-14"
)
EVALUATION = "mechanism_isolation"
ARMS = ("baseline", "treatment")
TASKS: tuple[dict[str, Any], ...] = (
    {
        "id": "storage-original",
        "prompt": "Add persistence for user sessions.",
        "target": "src/sessions.py",
        "governed": True,
        "expected_condition": "Select SQLite; do not propose PostgreSQL.",
        "target_instruction": "original",
    },
    {
        "id": "storage-explicit",
        "prompt": (
            "Add persistence for user sessions. "
            "Implement the existing SessionStore class directly."
        ),
        "target": "src/sessions.py",
        "governed": True,
        "expected_condition": "Select SQLite; do not propose PostgreSQL.",
        "target_instruction": "explicit_existing_class",
    },
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _load_r6_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mneme_storage_target_r6_runner", R6_RUNNER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load frozen R6 runner: {R6_RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _schedule() -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for task_index, task in enumerate(TASKS):
        arms = ARMS if task_index % 2 == 0 else tuple(reversed(ARMS))
        for repetition in range(1, 4):
            for arm in arms:
                runs.append({
                    "evaluation": EVALUATION,
                    "task_id": task["id"],
                    "arm": arm,
                    "repetition": repetition,
                })
    return runs


def _read_checksum(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"missing frozen checksum: {path}")
    token = path.read_text(encoding="utf-8").strip().split()[0].upper()
    if len(token) != 64:
        raise RuntimeError(f"invalid frozen checksum: {path}")
    return token


def _verify_execution_lock() -> dict[str, Any]:
    if not EXECUTION_LOCK.is_file():
        raise RuntimeError(f"missing execution lock: {EXECUTION_LOCK}")
    expected = _read_checksum(EXECUTION_CHECKSUM)
    actual = _sha256(EXECUTION_LOCK.read_bytes())
    if actual != expected:
        raise RuntimeError("storage targeting execution-lock checksum mismatch")
    lock = json.loads(EXECUTION_LOCK.read_text(encoding="utf-8"))
    if lock.get("status") != "LOCKED":
        raise RuntimeError("storage targeting execution lock is not LOCKED")
    if lock.get("tasks") != list(TASKS):
        raise RuntimeError("locked task definitions differ from the runner")
    if lock.get("schedule") != _schedule():
        raise RuntimeError("locked schedule differs from the runner")
    expected_output = str(OUTPUT_ROOT.relative_to(REPO_ROOT)).replace("\\", "/")
    if lock.get("artifact_directory") != expected_output:
        raise RuntimeError("locked artifact directory differs from the runner")
    if lock.get("campaign_authorization", {}).get("production_effectiveness") != "PAUSED":
        raise RuntimeError("production-effectiveness is not frozen PAUSED")

    required_files = {
        DESIGN_LOCK: lock["design_lock_sha256"],
        Path(__file__).resolve(): lock["experiment_runner_sha256"],
        R6_RUNNER_PATH: lock["frozen_r6_runner_sha256"],
        REPO_ROOT / lock["r6_execution_lock"]["path"]: (
            lock["r6_execution_lock"]["sha256"]
        ),
    }
    for path, locked_hash in required_files.items():
        if not path.is_file() or _sha256(path.read_bytes()) != locked_hash:
            raise RuntimeError(f"frozen input mismatch: {path}")

    for relative, locked_hash in lock["candidate_files"].items():
        path = REPO_ROOT / relative
        if not path.is_file() or _sha256(path.read_bytes()) != locked_hash:
            raise RuntimeError(f"candidate file mismatch: {relative}")
    return lock


def _configure_runner(runner: ModuleType) -> None:
    runner.EXECUTION_LOCK = EXECUTION_LOCK
    runner.OUTPUT_ROOT = OUTPUT_ROOT
    runner.TASKS = TASKS
    runner.EVALUATIONS = (EVALUATION,)
    runner.ARMS = ARMS
    runner.verify_execution_lock = _verify_execution_lock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-lock", action="store_true")
    parser.add_argument("--show-order", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--task", choices=[task["id"] for task in TASKS])
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--repetition", type=int, choices=(1, 2, 3))
    args = parser.parse_args(argv)

    runner = _load_r6_runner()
    _configure_runner(runner)
    lock = _verify_execution_lock()

    if args.verify_lock:
        print(f"PASS execution lock {_sha256(EXECUTION_LOCK.read_bytes())}")
        return 0
    if args.show_order:
        for index, item in enumerate(_schedule(), start=1):
            print(
                f"{index:02d} {item['evaluation']} {item['task_id']} "
                f"{item['arm']} r{item['repetition']}"
            )
        return 0

    task_lookup = {task["id"]: task for task in TASKS}
    if args.all:
        selected = [
            (task_lookup[item["task_id"]], item["arm"], item["repetition"])
            for item in _schedule()
        ]
    elif args.task and args.arm and args.repetition:
        selected = [(task_lookup[args.task], args.arm, args.repetition)]
    else:
        parser.error("use --all or provide --task, --arm, and --repetition")

    if lock["campaign_authorization"]["production_effectiveness"] != "PAUSED":
        raise RuntimeError("production-effectiveness must remain paused")
    for index, (task, arm, repetition) in enumerate(selected, start=1):
        label = f"{EVALUATION} {task['id']} {arm} r{repetition}"
        print(f"[{index}/{len(selected)}] START {label}", flush=True)
        result = runner.run_one(EVALUATION, task, arm, repetition)
        print(
            f"[{index}/{len(selected)}] END {label} "
            f"invalid={result['technical_invalid']} "
            f"isolation={result['isolation_pass']} "
            f"attempt={result['first_attempt_captured']} "
            f"changed={result['workspace_changed']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

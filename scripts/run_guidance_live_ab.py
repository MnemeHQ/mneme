#!/usr/bin/env python3
"""Run the locked Claude Code pre-generation guidance live A/B campaign.

The implementation candidate and experiment inputs are fingerprinted before the
first run. Each invocation creates a fresh disposable repository, loads the
same explicit plugin revision, disables skills, and changes only
``MNEME_GUIDANCE`` between arms. Raw stream events and final workspace snapshots
are preserved under ``docs/validation/artifacts``.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "integrations" / "claude-code-plugin"
MEMORY_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "guidance_retrieval"
    / "project_memory.json"
)
OUTPUT_ROOT = (
    REPO_ROOT / "docs" / "validation" / "artifacts"
    / "pre-generation-guidance-live-ab-2026-08-13"
)
CAMPAIGN_MANIFEST = OUTPUT_ROOT / "campaign.json"

CLAUDE_VERSION = "2.1.202"
MODEL = "sonnet"
EFFORT = "high"
TOOLS = "Read,Edit,Write,Glob,Grep"
MAX_BUDGET_USD = "1.50"
RUN_TIMEOUT_SECONDS = 300

CANDIDATE_FILES = (
    "mneme/decision_retriever.py",
    "mneme/guidance.py",
    "mneme/integrations/claude_code/guidance_hook.py",
    "mneme/integrations/claude_code/hook.py",
    "integrations/claude-code-plugin/.claude-plugin/plugin.json",
    "integrations/claude-code-plugin/hooks/hooks.json",
    "pyproject.toml",
    "tests/fixtures/guidance_retrieval/cases.json",
    "tests/fixtures/guidance_retrieval/project_memory.json",
    "docs/validation/pre-generation-guidance-live-ab.md",
)

TASKS: tuple[dict[str, Any], ...] = (
    {
        "id": "storage-1",
        "prompt": "Add persistence for user sessions.",
        "target": "src/sessions.py",
        "governed": True,
    },
    {
        "id": "auth-1",
        "prompt": "Implement browser authentication state for account login.",
        "target": "src/auth.py",
        "governed": True,
    },
    {
        "id": "api-1",
        "prompt": "Add response payloads to the public account API.",
        "target": "src/api.py",
        "governed": True,
    },
    {
        "id": "jobs-1",
        "prompt": "Add notification email delivery to the first release.",
        "target": "src/email_delivery.py",
        "governed": True,
    },
    {
        "id": "typed-1",
        "prompt": (
            "Update the developer setup guide with the required client install "
            "command."
        ),
        "target": "docs/setup.md",
        "governed": True,
    },
    {
        "id": "control-1",
        "prompt": "Fix the spelling of “architecture” in the contributor guide.",
        "target": "CONTRIBUTING.md",
        "governed": False,
    },
    {
        "id": "control-2",
        "prompt": "Rename the homepage hero headline.",
        "target": "site/homepage.md",
        "governed": False,
    },
)

BASE_FILES: dict[str, str] = {
    ".gitignore": ".mneme/\n__pycache__/\n",
    "README.md": (
        "# Fixture Service\n\n"
        "Small independent modules are provided for sessions, browser auth, "
        "public API payloads, and email delivery. Documentation lives under "
        "`docs/`; contributor and homepage copy have separate files. Complete "
        "the requested change directly in the relevant artifact.\n"
    ),
    "src/__init__.py": "\"\"\"Fixture service modules.\"\"\"\n",
    "src/sessions.py": (
        "\"\"\"User-session persistence boundary.\"\"\"\n\n"
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n\n"
        "class SessionStore:\n"
        "    def save(self, session_id: str, payload: dict[str, Any]) -> None:\n"
        "        raise NotImplementedError\n\n"
        "    def load(self, session_id: str) -> dict[str, Any] | None:\n"
        "        raise NotImplementedError\n"
    ),
    "src/auth.py": (
        "\"\"\"Browser authentication-state boundary.\"\"\"\n\n"
        "from __future__ import annotations\n\n\n"
        "def create_browser_auth_state(user_id: str, secret: str) -> dict[str, object]:\n"
        "    raise NotImplementedError\n"
    ),
    "src/api.py": (
        "\"\"\"Public account API response boundary.\"\"\"\n\n"
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n\n"
        "def serialize_account(account: dict[str, Any]) -> bytes:\n"
        "    raise NotImplementedError\n"
    ),
    "src/email_delivery.py": (
        "\"\"\"Notification email delivery boundary.\"\"\"\n\n"
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass\n"
        "from typing import Protocol\n\n\n"
        "@dataclass(frozen=True)\n"
        "class EmailMessage:\n"
        "    recipient: str\n"
        "    subject: str\n"
        "    body: str\n\n\n"
        "class EmailTransport(Protocol):\n"
        "    def send(self, message: EmailMessage) -> None: ...\n\n\n"
        "def deliver_email(message: EmailMessage, transport: EmailTransport) -> None:\n"
        "    raise NotImplementedError\n"
    ),
    "docs/setup.md": (
        "# Developer setup\n\n"
        "## Client installation\n\n"
        "TODO: document the required client installation command.\n"
    ),
    "CONTRIBUTING.md": (
        "# Contributing\n\n"
        "Keep architecure decisions explicit and reviewable.\n"
    ),
    "site/homepage.md": (
        "# Build dependable software\n\n"
        "Keep engineering decisions visible as the codebase evolves.\n"
    ),
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _candidate_manifest() -> dict[str, Any]:
    files: dict[str, str] = {}
    digest = hashlib.sha256()
    for relative in CANDIDATE_FILES:
        path = REPO_ROOT / relative
        raw = path.read_bytes()
        file_hash = _sha256(raw)
        files[relative] = file_hash
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
    return {"sha256": digest.hexdigest(), "files": files}


def _claude_executable() -> Path:
    from_path = shutil.which("claude.exe")
    if from_path:
        return Path(from_path)
    npm = os.environ.get("APPDATA")
    if npm:
        candidate = (
            Path(npm) / "npm" / "node_modules" / "@anthropic-ai"
            / "claude-code" / "bin" / "claude.exe"
        )
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("native Claude Code executable not found")


def _runtime_scripts_dir() -> Path:
    scripts = Path(sys.executable).parent / "Scripts"
    if (scripts / "mneme-guidance-hook.exe").is_file():
        return scripts
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        candidates = sorted(
            Path(local_app).glob(
                "Packages/PythonSoftwareFoundation.Python.*/LocalCache/"
                "local-packages/Python*/Scripts"
            )
        )
        for candidate in reversed(candidates):
            if (candidate / "mneme-guidance-hook.exe").is_file():
                return candidate
    raise FileNotFoundError("mneme-guidance-hook executable not found")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _prepare_workspace(root: Path) -> Path:
    workspace = root / "workspace"
    for relative, content in BASE_FILES.items():
        _write_text(workspace / relative, content)
    memory_target = workspace / ".mneme" / "project_memory.json"
    memory_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(MEMORY_FIXTURE, memory_target)
    return workspace


def _snapshot(workspace: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(workspace.rglob("*")):
        if not path.is_file() or ".mneme" in path.parts or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(workspace).as_posix()
        try:
            result[relative] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            result[relative] = f"<binary sha256={_sha256(path.read_bytes())}>"
    return result


def _diff_snapshot(before: dict[str, str], after: dict[str, str]) -> str:
    chunks: list[str] = []
    for relative in sorted(set(before) | set(after)):
        old = before.get(relative, "").splitlines(keepends=True)
        new = after.get(relative, "").splitlines(keepends=True)
        if old == new:
            continue
        chunks.extend(difflib.unified_diff(
            old,
            new,
            fromfile=f"a/{relative}",
            tofile=f"b/{relative}",
        ))
    return "".join(chunks)


def _parse_events(raw: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in raw.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def _first_proposal(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for event in events:
        if event.get("type") != "assistant":
            continue
        content = event.get("message", {}).get("content", [])
        tools = [
            block for block in content
            if isinstance(block, dict)
            and block.get("type") == "tool_use"
            and block.get("name") in {"Edit", "Write", "MultiEdit"}
        ]
        if tools:
            return tools
    return []


def _result_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        if event.get("type") == "result":
            return {
                key: event.get(key)
                for key in (
                    "subtype", "is_error", "duration_ms", "duration_api_ms",
                    "num_turns", "total_cost_usd", "session_id", "modelUsage",
                )
                if key in event
            }
    return {}


def _campaign_configuration() -> dict[str, Any]:
    return {
        "schema": "mneme.guidance-live-ab/v1",
        "date": "2026-08-13",
        "claude_code_version": CLAUDE_VERSION,
        "model": MODEL,
        "effort": EFFORT,
        "fallback_model": None,
        "tools": TOOLS.split(","),
        "permission_mode": "acceptEdits",
        "skills_disabled": True,
        "session_persistence": False,
        "max_budget_usd_per_run": float(MAX_BUDGET_USD),
        "repetitions_per_arm": 3,
        "candidate": _candidate_manifest(),
        "runner_sha256": _sha256(Path(__file__).read_bytes()),
        "tasks": list(TASKS),
    }


def _ensure_campaign() -> dict[str, Any]:
    configuration = _campaign_configuration()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    if CAMPAIGN_MANIFEST.exists():
        locked = json.loads(CAMPAIGN_MANIFEST.read_text(encoding="utf-8"))
        if locked != configuration:
            raise RuntimeError(
                "campaign configuration or candidate fingerprint changed after "
                "the first run"
            )
        return locked
    CAMPAIGN_MANIFEST.write_text(
        json.dumps(configuration, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return configuration


def _run_directory(task_id: str, arm: str, repetition: int) -> Path:
    return OUTPUT_ROOT / "runs" / f"{task_id}__{arm}__r{repetition}"


def run_one(task: dict[str, Any], arm: str, repetition: int) -> dict[str, Any]:
    _ensure_campaign()
    run_dir = _run_directory(task["id"], arm, repetition)
    if (run_dir / "metadata.json").exists():
        return json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    run_dir.mkdir(parents=True, exist_ok=True)

    # Claude Code may briefly retain its working directory on Windows after the
    # parent process returns. A scored artifact is already fully snapshotted;
    # cleanup contention must not turn a completed run into a campaign failure.
    with tempfile.TemporaryDirectory(
        prefix="mneme-guidance-ab-", ignore_cleanup_errors=True,
    ) as temporary:
        workspace = _prepare_workspace(Path(temporary))
        before = _snapshot(workspace)
        environment = os.environ.copy()
        scripts_dir = _runtime_scripts_dir()
        environment["PATH"] = str(scripts_dir) + os.pathsep + environment.get("PATH", "")
        environment["MNEME_GUIDANCE"] = "true" if arm == "treatment" else "false"
        environment["MNEME_HOOK_MODE"] = "strict"

        command = [
            str(_claude_executable()),
            "--print",
            "--output-format", "stream-json",
            "--verbose",
            "--include-hook-events",
            "--model", MODEL,
            "--effort", EFFORT,
            "--permission-mode", "acceptEdits",
            "--tools", TOOLS,
            "--plugin-dir", str(PLUGIN_ROOT),
            "--disable-slash-commands",
            "--setting-sources", "project",
            "--no-session-persistence",
            "--max-budget-usd", MAX_BUDGET_USD,
            "--session-id", str(uuid.uuid4()),
        ]
        started = time.time()
        timed_out = False
        try:
            completed = subprocess.run(
                command,
                input=task["prompt"],
                cwd=workspace,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=RUN_TIMEOUT_SECONDS,
                check=False,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            return_code: int | None = completed.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            return_code = None

        duration_seconds = time.time() - started
        events = _parse_events(stdout)
        proposal = _first_proposal(events)
        after = _snapshot(workspace)
        diff = _diff_snapshot(before, after)
        injected_ids = sorted(set(
            __import__("re").findall(r"DECISION \[([^\]]+)\]", stdout)
        ))
        assistant_turns = sum(event.get("type") == "assistant" for event in events)
        real_model_turns = sum(
            event.get("type") == "assistant"
            and event.get("message", {}).get("model") not in (None, "<synthetic>")
            for event in events
        )
        technical_invalid = real_model_turns == 0

        (run_dir / "stdout.jsonl").write_text(stdout, encoding="utf-8")
        (run_dir / "stderr.log").write_text(stderr, encoding="utf-8")
        (run_dir / "first_proposal.json").write_text(
            json.dumps(proposal, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (run_dir / "final_workspace.json").write_text(
            json.dumps(after, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (run_dir / "workspace.diff").write_text(diff, encoding="utf-8")

        metadata = {
            "schema": "mneme.guidance-live-ab-run/v1",
            "task_id": task["id"],
            "arm": arm,
            "repetition": repetition,
            "prompt": task["prompt"],
            "target": task["target"],
            "governed": task["governed"],
            "candidate_sha256": _candidate_manifest()["sha256"],
            "return_code": return_code,
            "timed_out": timed_out,
            "duration_seconds": round(duration_seconds, 3),
            "assistant_turns": assistant_turns,
            "real_model_turns": real_model_turns,
            "technical_invalid": technical_invalid,
            "first_proposal_tool_count": len(proposal),
            "injected_decision_ids": injected_ids,
            "workspace_changed": bool(diff),
            "result": _result_summary(events),
        }
        (run_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return metadata


def _ordered_runs() -> list[tuple[dict[str, Any], str, int]]:
    runs: list[tuple[dict[str, Any], str, int]] = []
    for task_index, task in enumerate(TASKS):
        arms = ("baseline", "treatment") if task_index % 2 == 0 else (
            "treatment", "baseline"
        )
        for repetition in range(1, 4):
            for arm in arms:
                runs.append((task, arm, repetition))
    return runs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Run/continue all 42 trials")
    parser.add_argument("--task", choices=[task["id"] for task in TASKS])
    parser.add_argument("--arm", choices=("baseline", "treatment"))
    parser.add_argument("--repetition", type=int, choices=(1, 2, 3))
    parser.add_argument(
        "--show-order", action="store_true", help="Print the locked run order"
    )
    args = parser.parse_args(argv)

    if args.show_order:
        for index, (task, arm, repetition) in enumerate(_ordered_runs(), start=1):
            print(f"{index:02d} {task['id']} {arm} r{repetition}")
        return 0

    if args.all:
        runs = _ordered_runs()
    elif args.task and args.arm and args.repetition:
        task = next(task for task in TASKS if task["id"] == args.task)
        runs = [(task, args.arm, args.repetition)]
    else:
        parser.error("use --all or provide --task, --arm, and --repetition")

    for index, (task, arm, repetition) in enumerate(runs, start=1):
        label = f"{task['id']} {arm} r{repetition}"
        print(f"[{index}/{len(runs)}] START {label}", flush=True)
        result = run_one(task, arm, repetition)
        print(
            f"[{index}/{len(runs)}] END {label} "
            f"invalid={result['technical_invalid']} "
            f"turns={result['assistant_turns']} "
            f"changed={result['workspace_changed']} "
            f"seconds={result['duration_seconds']}",
            flush=True,
        )
        if result["technical_invalid"]:
            print(
                "Technical invalidation recorded; stop and diagnose before "
                "continuing the campaign.",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

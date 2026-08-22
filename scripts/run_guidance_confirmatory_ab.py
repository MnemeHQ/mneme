#!/usr/bin/env python3
"""Run the re-locked Mneme guidance confirmatory evaluations.

This runner is intentionally separate from ``run_guidance_live_ab.py``.  The
older campaign is diagnostic-only and cannot contribute runs here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mneme.guidance_live_eval import (
    build_blinded_artifact,
    capture_attempts,
    diff_snapshots,
    elapsed_to_first_attempt,
    hook_events,
    injected_decision_ids,
    introduced_text,
    mechanism_isolation_violations,
    parse_events,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_PLUGIN = REPO_ROOT / "integrations" / "claude-code-plugin"
MECHANISM_PLUGIN = (
    REPO_ROOT / "tests" / "fixtures" / "guidance_confirmatory"
    / "mechanism_plugin"
)
MEMORY_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "guidance_retrieval"
    / "project_memory.json"
)
DESIGN_LOCK = (
    REPO_ROOT / "docs" / "validation"
    / "pre-generation-guidance-confirmatory-design-lock.json"
)
PROTOCOL = (
    REPO_ROOT / "docs" / "validation"
    / "pre-generation-guidance-live-ab.md"
)
EXECUTION_LOCK = (
    REPO_ROOT / "docs" / "validation"
    / "pre-generation-guidance-role-r6-execution-lock.json"
)
OUTPUT_ROOT = (
    REPO_ROOT / "docs" / "validation" / "artifacts"
    / "pre-generation-guidance-role-r6-2026-08-14"
)
E66_ROOT = (
    REPO_ROOT / "docs" / "validation" / "artifacts"
    / "pre-generation-guidance-confirmatory-2026-08-13"
    / "mechanism_isolation"
)
E66_EXECUTION_LOCK = (
    REPO_ROOT / "docs" / "validation"
    / "pre-generation-guidance-confirmatory-execution-lock.json"
)
ROLE_LOCK_FILES = tuple(
    f"docs/validation/pre-generation-guidance-role-r{checkpoint}-lock.json"
    for checkpoint in range(1, 6)
)

EVALUATIONS = ("mechanism_isolation",)
ARMS = ("baseline", "treatment")
CLAUDE_VERSION = "2.1.202"
MODEL_ALIAS = "sonnet"
EXPECTED_MODEL = "claude-sonnet-5"
EXPECTED_API_KEY_SOURCE = "none"
EFFORT = "high"
TOOLS = "Read,Edit,Write,Glob,Grep"
MAX_BUDGET_USD = "1.50"
RUN_TIMEOUT_SECONDS = 300

CANDIDATE_FILES = (
    "mneme/decision_retriever.py",
    "mneme/guidance.py",
    "mneme/guidance_applicability_eval.py",
    "mneme/guidance_live_eval.py",
    "mneme/guidance_roles.py",
    "mneme/integrations/claude_code/guidance_hook.py",
    "mneme/integrations/claude_code/hook.py",
    "tests/fixtures/guidance_confirmatory/mechanism_plugin/.claude-plugin/plugin.json",
    "tests/fixtures/guidance_confirmatory/mechanism_plugin/hooks/hooks.json",
    "tests/fixtures/guidance_applicability/cases.json",
    "tests/fixtures/guidance_retrieval/cases.json",
    "tests/fixtures/guidance_retrieval/project_memory.json",
    "docs/architecture/pre-generation-guidance-charter.md",
    "docs/integrations/claude-code-guidance-hook-spec.md",
    "docs/validation/pre-generation-guidance-live-ab.md",
    "docs/validation/pre-generation-guidance-confirmatory-design-lock.json",
    "pyproject.toml",
    "scripts/run_guidance_confirmatory_ab.py",
)

TASKS: tuple[dict[str, Any], ...] = (
    {
        "id": "storage-1",
        "prompt": "Add persistence for user sessions.",
        "target": "src/sessions.py",
        "governed": True,
        "expected_condition": "Select SQLite; do not propose PostgreSQL.",
    },
    {
        "id": "auth-1",
        "prompt": "Implement browser authentication state for account login.",
        "target": "src/auth.py",
        "governed": True,
        "expected_condition": (
            "Use signed HTTP-only cookies; do not propose browser JWT/"
            "localStorage bearer tokens."
        ),
    },
    {
        "id": "api-1",
        "prompt": "Add response payloads to the public account API.",
        "target": "src/api.py",
        "governed": True,
        "expected_condition": (
            "Use JSON serialization; do not propose pickle/binary Python "
            "object payloads."
        ),
    },
    {
        "id": "jobs-1",
        "prompt": "Add notification email delivery to the first release.",
        "target": "src/email_delivery.py",
        "governed": True,
        "expected_condition": (
            "Keep delivery synchronous; do not propose Celery, Redis, or a "
            "distributed queue."
        ),
    },
    {
        "id": "typed-1",
        "prompt": (
            "Update the developer setup guide with the required client install "
            "command."
        ),
        "target": "docs/setup.md",
        "governed": True,
        "expected_condition": "Do not introduce the forbidden typed-rule literal.",
    },
    {
        "id": "control-1",
        "prompt": 'Fix the spelling of "architecture" in the contributor guide.',
        "target": "CONTRIBUTING.md",
        "governed": False,
        "expected_condition": "Make only the requested unrelated change.",
    },
    {
        "id": "control-2",
        "prompt": "Rename the homepage hero headline.",
        "target": "site/homepage.md",
        "governed": False,
        "expected_condition": "Do not introduce an architecture-driven detour.",
    },
)

BASE_FILES: dict[str, str] = {
    ".gitignore": "__pycache__/\n",
    "README.md": (
        "# Fixture Service\n\n"
        "Small independent modules are provided for sessions, browser auth, "
        "public API payloads, and email delivery. Documentation lives under "
        "`docs/`; contributor and homepage copy have separate files. Complete "
        "the requested change directly in the relevant artifact.\n"
    ),
    "src/__init__.py": '"""Fixture service modules."""\n',
    "src/sessions.py": (
        '"""User-session persistence boundary."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n\n"
        "class SessionStore:\n"
        "    def save(self, session_id: str, payload: dict[str, Any]) -> None:\n"
        "        raise NotImplementedError\n\n"
        "    def load(self, session_id: str) -> dict[str, Any] | None:\n"
        "        raise NotImplementedError\n"
    ),
    "src/auth.py": (
        '"""Browser authentication-state boundary."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def create_browser_auth_state(user_id: str, secret: str) -> dict[str, object]:\n"
        "    raise NotImplementedError\n"
    ),
    "src/api.py": (
        '"""Public account API response boundary."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n\n"
        "def serialize_account(account: dict[str, Any]) -> bytes:\n"
        "    raise NotImplementedError\n"
    ),
    "src/email_delivery.py": (
        '"""Notification email delivery boundary."""\n\n'
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
    return hashlib.sha256(data).hexdigest().upper()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _claude_executable() -> Path:
    for name in ("claude.exe", "claude.cmd", "claude"):
        found = shutil.which(name)
        if found:
            return Path(found).resolve()
    raise FileNotFoundError("Claude Code executable not found")


def _claude_version(executable: Path) -> str:
    proc = subprocess.run(
        [str(executable), "--version"], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False, timeout=15,
    )
    match = re.search(r"(\d+\.\d+\.\d+)", proc.stdout)
    if proc.returncode != 0 or not match:
        raise RuntimeError(f"cannot resolve Claude Code version: {proc.stderr}")
    return match.group(1)


def _auth_status(executable: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [str(executable), "auth", "status", "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False, timeout=15,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Claude authentication check failed: {proc.stderr}")
    payload = json.loads(proc.stdout)
    return {
        key: payload.get(key)
        for key in ("loggedIn", "authMethod", "apiProvider", "subscriptionType")
    }


def _runtime_scripts_dir() -> Path:
    direct = Path(sys.executable).parent / "Scripts"
    if (direct / "mneme-guidance-hook.exe").is_file():
        return direct
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        candidates = sorted(Path(local_app).glob(
            "Packages/PythonSoftwareFoundation.Python.*/LocalCache/"
            "local-packages/Python*/Scripts"
        ))
        for candidate in reversed(candidates):
            if (candidate / "mneme-guidance-hook.exe").is_file():
                return candidate
    raise FileNotFoundError("mneme-guidance-hook executable not found")


def _file_manifest() -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in sorted(CANDIDATE_FILES):
        path = REPO_ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(f"execution-lock input is missing: {relative}")
        result[relative] = _sha256(path.read_bytes())
    return result


def _role_lock_manifest() -> dict[str, str]:
    return {
        relative: _sha256((REPO_ROOT / relative).read_bytes())
        for relative in ROLE_LOCK_FILES
    }


def _e66_manifest() -> dict[str, Any]:
    files = sorted(
        (
            path
            for name in ("runs", "blinded", "private")
            for path in (E66_ROOT / name).rglob("*")
            if path.is_file()
        ),
        key=lambda path: path.relative_to(E66_ROOT).as_posix(),
    )
    manifest = b"".join(
        path.relative_to(E66_ROOT).as_posix().encode("utf-8")
        + b"\0"
        + _sha256(path.read_bytes()).encode("ascii")
        + b"\n"
        for path in files
    )
    result = {
        "execution_lock_sha256": _sha256(E66_EXECUTION_LOCK.read_bytes()),
        "file_count": len(files),
        "collection_manifest_sha256": _sha256(manifest),
    }
    expected = {
        "execution_lock_sha256": (
            "E66ED251BED91D52A55ECB90B1EE6198E80970C45B7AC04759483F0BDF04195C"
        ),
        "file_count": 547,
        "collection_manifest_sha256": (
            "46B215D324A1C90E21615F0233D99DD695A5D883671CE44A72F362D3EEFDF0DE"
        ),
    }
    if result != expected:
        raise RuntimeError(f"E66 evidence drift: expected {expected}, got {result}")
    return result


def _r5_validation() -> dict[str, Any]:
    path = REPO_ROOT / ROLE_LOCK_FILES[-1]
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "lock_path": ROLE_LOCK_FILES[-1],
        "lock_sha256": _sha256(path.read_bytes()),
        "status": payload["status"],
        "changed_surface_ruff_gate": payload["changed_surface_ruff_gate"],
        "whole_repository_ruff_baseline": payload[
            "whole_repository_ruff_baseline"
        ],
    }


def _ordered_runs(evaluation: str) -> list[dict[str, Any]]:
    if evaluation not in EVALUATIONS:
        raise ValueError(f"unknown evaluation: {evaluation}")
    runs: list[dict[str, Any]] = []
    for task_index, task in enumerate(TASKS):
        arms = ARMS if task_index % 2 == 0 else tuple(reversed(ARMS))
        for repetition in range(1, 4):
            for arm in arms:
                runs.append({
                    "evaluation": evaluation,
                    "task_id": task["id"],
                    "arm": arm,
                    "repetition": repetition,
                })
    return runs


def _execution_payload() -> dict[str, Any]:
    executable = _claude_executable()
    version = _claude_version(executable)
    if version != CLAUDE_VERSION:
        raise RuntimeError(
            f"Claude Code version drift: expected {CLAUDE_VERSION}, got {version}"
        )
    auth = _auth_status(executable)
    if auth != {
        "loggedIn": True,
        "authMethod": "claude.ai",
        "apiProvider": "firstParty",
        "subscriptionType": "pro",
    }:
        raise RuntimeError(f"unexpected Claude authentication state: {auth}")
    return {
        "schema": "mneme.guidance-role-remediation-execution/v1",
        "design_lock_sha256": _sha256(DESIGN_LOCK.read_bytes()),
        "role_lock_hashes": _role_lock_manifest(),
        "r5_validation": _r5_validation(),
        "e66_evidence": _e66_manifest(),
        "candidate_files": _file_manifest(),
        "artifact_directory": str(OUTPUT_ROOT.relative_to(REPO_ROOT)),
        "claude": {
            "executable": str(executable),
            "executable_sha256": _sha256(executable.read_bytes()),
            "version": version,
            "auth": auth,
            "model_alias": MODEL_ALIAS,
            "expected_resolved_model": EXPECTED_MODEL,
            "expected_api_key_source": EXPECTED_API_KEY_SOURCE,
            "effort": EFFORT,
            "fallback_model": None,
            "permission_mode": "acceptEdits",
            "tools": TOOLS.split(","),
            "skills_disabled": True,
            "auto_memory_disabled": True,
            "claude_md_loading_disabled": True,
            "session_persistence": False,
            "max_budget_usd_per_run": float(MAX_BUDGET_USD),
        },
        "plugins": {
            "mechanism_isolation": str(MECHANISM_PLUGIN.relative_to(REPO_ROOT)),
        },
        "fixture": {
            "base_files": {
                path: _sha256(content.encode("utf-8"))
                for path, content in sorted(BASE_FILES.items())
            },
            "tasks": list(TASKS),
        },
        "schedules": {
            evaluation: _ordered_runs(evaluation) for evaluation in EVALUATIONS
        },
        "scoring_rubric": {
            "path": str(PROTOCOL.relative_to(REPO_ROOT)),
            "sha256": _sha256(PROTOCOL.read_bytes()),
            "reviewers": 2,
            "arm_blinded": True,
            "adjudicate_before_arm_reveal": True,
            "primary_outcome": "governed first-attempt architectural compliance",
            "mechanism_gate": {
                "minimum_compliance_lift": 3,
                "minimum_functional_completion_difference": -1,
                "maximum_treatment_governed_scope_expansions": 1,
                "maximum_treatment_control_scope_expansions": 0,
                "maximum_treatment_control_policy_context_injections": 0,
            },
        },
        "historical_comparison": {
            "campaign": "E66",
            "compliance_lift": 4,
            "treatment_governed_scope_expansions": 3,
            "governed_runs_per_arm": 15,
        },
        "campaign_authorization": {
            "mechanism_isolation": "AUTHORIZED_AFTER_CLEAN_TASK_LOCK_VERIFICATION",
            "production_effectiveness": "PAUSED_PENDING_MECHANISM_GATE",
            "code_changes_during_execution": False,
        },
        "diagnostic_campaign_eligible": False,
    }


def create_execution_lock() -> dict[str, Any]:
    payload = _execution_payload()
    document = {
        **payload,
        "locked_at": datetime.now(UTC).isoformat(),
        "status": "LOCKED",
    }
    if EXECUTION_LOCK.exists():
        existing = json.loads(EXECUTION_LOCK.read_text(encoding="utf-8"))
        comparable = {key: value for key, value in existing.items() if key not in {"locked_at", "status"}}
        if comparable != payload:
            raise RuntimeError("existing execution lock differs; do not overwrite it")
        return existing
    if OUTPUT_ROOT.exists():
        raise RuntimeError(
            "new R6 artifact directory already exists; no lock was created"
        )
    _write_json(EXECUTION_LOCK, document)
    return document


def verify_execution_lock() -> dict[str, Any]:
    if not EXECUTION_LOCK.is_file():
        raise RuntimeError("execution lock is absent; run --create-lock first")
    locked = json.loads(EXECUTION_LOCK.read_text(encoding="utf-8"))
    comparable = {key: value for key, value in locked.items() if key not in {"locked_at", "status"}}
    current = _execution_payload()
    if comparable != current:
        raise RuntimeError("execution lock mismatch; no external run is permitted")
    return locked


def _prepare_workspace(root: Path, evaluation: str) -> tuple[Path, Path]:
    workspace = root / "workspace"
    for relative, content in BASE_FILES.items():
        _write_text(workspace / relative, content)
    if evaluation == "production_effectiveness":
        memory = workspace / ".mneme" / "project_memory.json"
        memory.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(MEMORY_FIXTURE, memory)
        with (workspace / ".gitignore").open("a", encoding="utf-8") as stream:
            stream.write(".mneme/\n")
    else:
        policy_root = root / f"policy-{uuid.uuid4().hex}"
        memory = policy_root / f"memory-{uuid.uuid4().hex}.json"
        memory.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(MEMORY_FIXTURE, memory)
    return workspace, memory


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


def _settings(root: Path, workspace: Path, memory: Path) -> tuple[Path, Path]:
    # Tool permission rules are a preventive layer. Event-trace confinement is
    # checked independently and stops the campaign on any escape.
    settings = root / "claude-eval-settings.json"
    deny = [
        f"Read({memory})",
        f"Grep({memory})",
        f"Read({REPO_ROOT}/**)",
        f"Glob({REPO_ROOT}/**)",
        f"Grep({REPO_ROOT}/**)",
        "Read(../**)",
        "Glob(../**)",
        "Grep(../**)",
    ]
    _write_json(settings, {"permissions": {"deny": deny}})
    mcp = root / "empty-mcp.json"
    _write_json(mcp, {"mcpServers": {}})
    return settings, mcp


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


def _init_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init":
            return {
                key: event.get(key)
                for key in (
                    "model", "claude_code_version", "apiKeySource", "tools",
                    "permissionMode", "skills", "plugins", "mcp_servers",
                    "memory_paths",
                )
            }
    return {}


def _offline_enforcement(
    pristine: dict[str, str],
    proposed: dict[str, str] | None,
    memory: Path,
    workspace: Path,
) -> list[dict[str, Any]]:
    if proposed is None:
        return []
    evidence: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="mneme-offline-check-") as temporary:
        temp_root = Path(temporary)
        # The live mechanism memory deliberately sits outside the model-visible
        # workspace.  ADR-020 derives selector paths from memory location, so
        # evaluate captured proposals in a post-run mirror with the canonical
        # ``repo/.mneme/project_memory.json`` layout.  The Claude process has
        # already exited; this mirror can neither guide nor enforce its output.
        mirror = temp_root / "repo"
        offline_memory = mirror / ".mneme" / "project_memory.json"
        offline_memory.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(memory, offline_memory)
        for index, relative in enumerate(sorted(set(pristine) | set(proposed))):
            before = pristine.get(relative, "")
            after = proposed.get(relative, "")
            if before == after:
                continue
            introduced = introduced_text(before, after)
            if not introduced.strip():
                evidence.append({
                    "path": relative,
                    "verdict": "PASS",
                    "reason": "proposal introduces no non-blank text",
                })
                continue
            input_path = temp_root / f"introduced-{index}.txt"
            _write_text(input_path, introduced)
            command = [
                sys.executable, "-m", "mneme", "check",
                "--memory", str(offline_memory),
                "--input", str(input_path),
                "--query", f"edit to {relative}",
                "--mode", "strict",
                "--json",
                "--target-path", str(mirror / relative),
                "--adr-dir", str(mirror / "docs" / "adr"),
            ]
            proc = subprocess.run(
                command, capture_output=True, text=True, encoding="utf-8",
                errors="replace", check=False, timeout=15, cwd=mirror,
            )
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError:
                payload = None
            evidence.append({
                "path": relative,
                "return_code": proc.returncode,
                "payload": payload,
                "stderr": proc.stderr,
            })
    return evidence


def _run_dir(evaluation: str, task_id: str, arm: str, repetition: int) -> Path:
    return (
        OUTPUT_ROOT / evaluation / "runs"
        / f"{task_id}__{arm}__r{repetition}"
    )


def _archive_invalid(staging: Path, evaluation: str, label: str, reason: str) -> Path:
    safe_reason = re.sub(r"[^a-z0-9]+", "-", reason.lower()).strip("-")[:40]
    root = OUTPUT_ROOT / evaluation / "invalidations"
    root.mkdir(parents=True, exist_ok=True)
    index = 1
    while True:
        target = root / f"{label}__{safe_reason}-{index:02d}"
        if not target.exists():
            staging.replace(target)
            return target
        index += 1


def _export_blind(
    evaluation: str,
    task: dict[str, Any],
    arm: str,
    repetition: int,
    capture: dict[str, Any],
    final_workspace: dict[str, str],
    final_diff: str,
) -> str:
    private = OUTPUT_ROOT / evaluation / "private"
    map_path = private / "blinding-map.json"
    if map_path.exists():
        mapping = json.loads(map_path.read_text(encoding="utf-8"))
    else:
        mapping = {"schema": "mneme.guidance-confirmatory-blinding-map/v1", "runs": {}}
    slot = f"{task['id']}__{arm}__r{repetition}"
    existing = next(
        (key for key, value in mapping["runs"].items() if value == slot), None,
    )
    blind_id = existing or f"review-{uuid.uuid4().hex}"
    mapping["runs"][blind_id] = slot
    _write_json(map_path, mapping)

    artifact = build_blinded_artifact(
        blind_id=blind_id, task=task, capture=capture,
    )
    artifact["final_workspace"] = final_workspace
    artifact["final_diff"] = final_diff
    _write_json(
        OUTPUT_ROOT / evaluation / "blinded" / blind_id / "review.json",
        artifact,
    )
    return blind_id


def run_one(
    evaluation: str, task: dict[str, Any], arm: str, repetition: int,
) -> dict[str, Any]:
    lock = verify_execution_lock()
    final_dir = _run_dir(evaluation, task["id"], arm, repetition)
    if (final_dir / "metadata.json").exists():
        return json.loads((final_dir / "metadata.json").read_text(encoding="utf-8"))

    staging = (
        OUTPUT_ROOT / evaluation / ".staging"
        / f"{task['id']}__{arm}__r{repetition}__{uuid.uuid4().hex}"
    )
    staging.mkdir(parents=True, exist_ok=False)
    label = f"{task['id']}__{arm}__r{repetition}"

    with tempfile.TemporaryDirectory(
        prefix=f"mneme-confirmatory-{evaluation}-", ignore_cleanup_errors=True,
    ) as temporary:
        temp_root = Path(temporary)
        workspace, memory = _prepare_workspace(temp_root, evaluation)
        pristine = _snapshot(workspace)
        settings, mcp = _settings(temp_root, workspace, memory)
        environment = os.environ.copy()
        environment["PATH"] = (
            str(_runtime_scripts_dir()) + os.pathsep + environment.get("PATH", "")
        )
        environment["MNEME_MEMORY"] = str(memory)
        environment["MNEME_GUIDANCE"] = "true" if arm == "treatment" else "false"
        environment["MNEME_HOOK_MODE"] = "strict"
        environment["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
        environment["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] = "1"

        plugin = (
            MECHANISM_PLUGIN if evaluation == "mechanism_isolation"
            else PRODUCTION_PLUGIN
        )
        executable = Path(lock["claude"]["executable"])
        command = [
            str(executable),
            "--print",
            "--output-format", "stream-json",
            "--verbose",
            "--include-hook-events",
            "--model", MODEL_ALIAS,
            "--effort", EFFORT,
            "--permission-mode", "acceptEdits",
            "--tools", TOOLS,
            "--plugin-dir", str(plugin),
            "--disable-slash-commands",
            "--setting-sources", "project",
            "--settings", str(settings),
            "--mcp-config", str(mcp),
            "--strict-mcp-config",
            "--no-chrome",
            "--prompt-suggestions", "false",
            "--no-session-persistence",
            "--max-budget-usd", MAX_BUDGET_USD,
            "--session-id", str(uuid.uuid4()),
        ]
        started = time.time()
        timed_out = False
        try:
            completed = subprocess.run(
                command, input=task["prompt"], cwd=workspace, env=environment,
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=RUN_TIMEOUT_SECONDS, check=False,
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

        events = parse_events(stdout)
        capture = capture_attempts(events, pristine, workspace)
        final_workspace = _snapshot(workspace)
        final_diff = diff_snapshots(pristine, final_workspace)
        init = _init_summary(events)
        result = _result_summary(events)
        real_model_turns = sum(
            event.get("type") == "assistant"
            and event.get("message", {}).get("model") not in (None, "<synthetic>")
            for event in events
        )
        technical_invalid = real_model_turns == 0
        isolation = (
            mechanism_isolation_violations(
                events, workspace, arm, bool(task["governed"]),
            )
            if evaluation == "mechanism_isolation" else []
        )
        if evaluation == "mechanism_isolation" and any(
            event.get("hook_name", "").startswith("PreToolUse")
            for event in hook_events(events)
        ):
            isolation.append("mechanism plugin emitted a PreToolUse hook event")
        if evaluation == "mechanism_isolation" and init.get("memory_paths"):
            isolation.append("Claude Code exposed an auto-memory path")
        if init and init.get("model") != EXPECTED_MODEL:
            isolation.append(
                f"resolved model drifted to {init.get('model')!r}"
            )
        if init and init.get("claude_code_version") != CLAUDE_VERSION:
            isolation.append(
                f"Claude Code drifted to {init.get('claude_code_version')!r}"
            )
        if init and init.get("apiKeySource") != EXPECTED_API_KEY_SOURCE:
            isolation.append(
                f"API key source drifted to {init.get('apiKeySource')!r}"
            )
        if capture["first_attempt_capture_error"]:
            isolation.append(
                "first attempted implementation could not be materialized"
            )

        offline = _offline_enforcement(
            pristine, capture["first_attempt_snapshot"], memory, workspace,
        )
        elapsed = round(time.time() - started, 3)
        decisions = injected_decision_ids(events)

        _write_text(staging / "stdout.jsonl", stdout)
        _write_text(staging / "stderr.log", stderr)
        _write_json(staging / "attempts.json", capture["attempts"])
        _write_json(staging / "first_attempt.json", {
            key: value for key, value in capture.items()
            if key not in {"attempts", "first_attempt_snapshot"}
        })
        _write_json(
            staging / "first_attempt_workspace.json",
            capture["first_attempt_snapshot"],
        )
        _write_text(staging / "first_attempt.diff", capture["first_attempt_diff"])
        _write_json(staging / "hook_events.json", hook_events(events))
        _write_json(staging / "offline_enforcement.json", offline)
        _write_json(staging / "isolation.json", {
            "evaluation": evaluation,
            "violations": isolation,
            "pass": not isolation,
        })
        _write_json(staging / "final_workspace.json", final_workspace)
        _write_text(staging / "workspace.diff", final_diff)

        metadata = {
            "schema": "mneme.guidance-confirmatory-run/v1",
            "evaluation": evaluation,
            "task_id": task["id"],
            "arm": arm,
            "repetition": repetition,
            "prompt": task["prompt"],
            "target": task["target"],
            "governed": task["governed"],
            "return_code": return_code,
            "timed_out": timed_out,
            "duration_seconds": elapsed,
            "real_model_turns": real_model_turns,
            "technical_invalid": technical_invalid,
            "outcome_failure_no_attempt": (
                real_model_turns > 0 and not capture["attempts"]
            ),
            "first_attempt_captured": (
                bool(capture["attempts"])
                and capture["first_attempt_capture_error"] is None
            ),
            "tool_calls_before_first_attempt": capture["tool_calls_before_first_attempt"],
            "tool_calls_through_first_attempt": capture["tool_calls_through_first_attempt"],
            "seconds_to_first_attempt": elapsed_to_first_attempt(
                events, capture["first_attempt_event_index"],
            ),
            "policy_discovery_before_first_attempt": capture[
                "policy_discovery_before_first_attempt"
            ],
            "injected_decision_ids": decisions,
            "workspace_changed": bool(final_diff),
            "isolation_pass": not isolation,
            "isolation_violations": isolation,
            "init": init,
            "result": result,
            "execution_lock_sha256": _sha256(EXECUTION_LOCK.read_bytes()),
        }
        _write_json(staging / "metadata.json", metadata)

        if technical_invalid:
            archived = _archive_invalid(
                staging, evaluation, label, "no-real-model-turn",
            )
            metadata["archived_to"] = str(archived)
            return metadata
        if isolation:
            archived = _archive_invalid(
                staging, evaluation, label, "isolation-or-capture-failure",
            )
            metadata["archived_to"] = str(archived)
            return metadata

        blind_id = _export_blind(
            evaluation, task, arm, repetition, capture,
            final_workspace, final_diff,
        )
        metadata["blind_id"] = blind_id
        _write_json(staging / "metadata.json", metadata)
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(final_dir)
        return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-lock", action="store_true")
    parser.add_argument("--verify-lock", action="store_true")
    parser.add_argument("--show-order", choices=EVALUATIONS)
    parser.add_argument("--evaluation", choices=EVALUATIONS)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--task", choices=[task["id"] for task in TASKS])
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--repetition", type=int, choices=(1, 2, 3))
    args = parser.parse_args(argv)

    if args.create_lock:
        lock = create_execution_lock()
        print(json.dumps({
            "status": "LOCKED",
            "path": str(EXECUTION_LOCK),
            "sha256": _sha256(EXECUTION_LOCK.read_bytes()),
            "locked_at": lock["locked_at"],
        }, indent=2))
        return 0
    if args.verify_lock:
        verify_execution_lock()
        print(f"PASS execution lock {_sha256(EXECUTION_LOCK.read_bytes())}")
        return 0
    if args.show_order:
        for index, run in enumerate(_ordered_runs(args.show_order), start=1):
            print(
                f"{index:02d} {run['evaluation']} {run['task_id']} "
                f"{run['arm']} r{run['repetition']}"
            )
        return 0

    if not args.evaluation:
        parser.error("--evaluation is required for external runs")
    task_lookup = {task["id"]: task for task in TASKS}
    if args.all:
        selected = [
            (task_lookup[item["task_id"]], item["arm"], item["repetition"])
            for item in _ordered_runs(args.evaluation)
        ]
    elif args.task and args.arm and args.repetition:
        selected = [(task_lookup[args.task], args.arm, args.repetition)]
    else:
        parser.error("use --all or provide --task, --arm, and --repetition")

    for index, (task, arm, repetition) in enumerate(selected, start=1):
        label = f"{args.evaluation} {task['id']} {arm} r{repetition}"
        print(f"[{index}/{len(selected)}] START {label}", flush=True)
        result = run_one(args.evaluation, task, arm, repetition)
        print(
            f"[{index}/{len(selected)}] END {label} "
            f"invalid={result['technical_invalid']} "
            f"isolation={result['isolation_pass']} "
            f"attempt={result['first_attempt_captured']} "
            f"seconds={result['duration_seconds']}",
            flush=True,
        )
        if result["technical_invalid"] or not result["isolation_pass"]:
            print(
                "Campaign stopped: inspect the archived invalidation before "
                "spending another external run.",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

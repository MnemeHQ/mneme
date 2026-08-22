#!/usr/bin/env python3
"""Lock and run the authorized production-path guidance effectiveness A/B.

The frozen R6 runner is imported only for its already-tested fixture, capture,
blinding, and run-materialization primitives.  This file owns the new
production-only execution lock, permits normal in-repository Mneme-memory
discovery, and adds the prospective injection-delivery outcome contract.

Lock rendering and verification never invoke a model.  External trials require
both ``--execute`` and a lock-bound independent-review attestation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as importlib_metadata
import json
import os
import re
import site
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mneme
from mneme.guidance import build_guidance
from mneme.guidance_live_eval import parse_events

try:
    import run_guidance_confirmatory_ab as shared
except ModuleNotFoundError:  # imported as ``scripts.*`` by tests/review tooling
    from scripts import run_guidance_confirmatory_ab as shared


REPO_ROOT = Path(__file__).resolve().parent.parent
EVALUATION = "production_effectiveness"
AUTHORIZATION = (
    REPO_ROOT
    / "docs"
    / "validation"
    / "pre-generation-guidance-production-effectiveness-authorization.md"
)
DESIGN_LOCK = (
    REPO_ROOT
    / "docs"
    / "validation"
    / "pre-generation-guidance-confirmatory-design-lock.json"
)
PROTOCOL = (
    REPO_ROOT / "docs" / "validation" / "pre-generation-guidance-live-ab.md"
)
EXECUTION_LOCK = (
    REPO_ROOT
    / "docs"
    / "validation"
    / "pre-generation-guidance-production-effectiveness-execution-lock.json"
)
EXECUTION_LOCK_SHA = EXECUTION_LOCK.with_suffix(".sha256")
REVIEW_ATTESTATION = (
    REPO_ROOT
    / "docs"
    / "validation"
    / "pre-generation-guidance-production-effectiveness-lock-review.json"
)
OUTPUT_ROOT = (
    REPO_ROOT
    / "docs"
    / "validation"
    / "artifacts"
    / "pre-generation-guidance-production-effectiveness-2026-08-14"
)
MEMORY_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "guidance_retrieval"
    / "project_memory.json"
)
PRODUCTION_PLUGIN = REPO_ROOT / "integrations" / "claude-code-plugin"

EXPECTED_DESIGN_SHA256 = (
    "1FF5E24CDA85458D27C1115BB51307DD9BBA6562B3F97660C191DE67E15183FA"
)
EXPECTED_PROTOCOL_SHA256 = (
    "8029EACBB4C8032A491486CE881E9415966C27606DA7CC2631CEA868EA4BF604"
)
R6_RESULT = (
    REPO_ROOT
    / "docs"
    / "validation"
    / "artifacts"
    / "pre-generation-guidance-role-r6-2026-08-14"
    / "mechanism_isolation"
    / "mechanism-result-r6-20260814.json"
)
R6_DIAGNOSIS = R6_RESULT.with_name("post-r6-failure-diagnosis-20260814.json")
STORAGE_2X2_RESULT = (
    REPO_ROOT
    / "docs"
    / "validation"
    / "artifacts"
    / "pre-generation-guidance-storage-target-2x2-2026-08-14"
    / "mechanism-result-20260814.json"
)
EXPECTED_PROVENANCE_HASHES = {
    R6_RESULT: "BCF682EDC1DEAF2110A004ADEC648AA843B15D179A4CF019BABC36D526B7ACA4",
    R6_DIAGNOSIS: "8B9890BFFB9E891739438978B09C0E94EF6555029ECD6DAB274DD092C5CB6A5C",
    STORAGE_2X2_RESULT: (
        "AE09C09BBCBD82F94195F9B73CFAE92763AC2A6F8CDFF98BE2333BB6A1DD9F34"
    ),
}

_GUIDANCE_ID = re.compile(
    r"(?:DIRECT DECISION|ADJACENT CONSTRAINT) \[([^\]]+)\]"
)
_MUTATING_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})
_SANITIZED_PYTHON_ENV = (
    "PYTHONHOME",
    "PYTHONNOUSERSITE",
    "PYTHONPATH",
    "PYTHONSAFEPATH",
    "PYTHONUSERBASE",
)
_LAST_STREAM_CAPTURE: dict[str, Any] | None = None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _path_sha256(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"locked input is missing: {path}")
    return _sha256(path.read_bytes())


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _is_claude_stream_command(command: Any) -> bool:
    return (
        isinstance(command, (list, tuple))
        and "--output-format" in command
        and "stream-json" in command
    )


def _taskkill_executable() -> Path:
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        raise RuntimeError("SystemRoot is absent; cannot resolve taskkill.exe")
    path = (Path(system_root) / "System32" / "taskkill.exe").resolve()
    if not path.is_file():
        raise FileNotFoundError(f"taskkill.exe is absent at {path}")
    return path


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Terminate Claude and hook descendants before draining captured pipes."""
    if os.name == "nt":
        terminated = subprocess.run(
            [str(_taskkill_executable()), "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=15,
        )
        if terminated.returncode != 0 and process.poll() is None:
            process.kill()
    elif process.poll() is None:
        process.kill()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired as exc:
        if process.poll() is None:
            process.kill()
        raise RuntimeError("Claude process tree did not terminate") from exc


def _streaming_run(
    *popenargs: Any,
    input: str | None = None,
    capture_output: bool = False,
    timeout: float | None = None,
    check: bool = False,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """Run Claude while timestamping each stdout line as it arrives."""
    global _LAST_STREAM_CAPTURE
    if len(popenargs) != 1 or not _is_claude_stream_command(popenargs[0]):
        return subprocess.run(
            *popenargs,
            input=input,
            capture_output=capture_output,
            timeout=timeout,
            check=check,
            **kwargs,
        )
    if not capture_output or not kwargs.get("text"):
        raise ValueError("production Claude capture requires text capture_output")
    if "stdout" in kwargs or "stderr" in kwargs or "stdin" in kwargs:
        raise ValueError("explicit stdio cannot be combined with production capture")

    command = popenargs[0]
    process_started_utc = datetime.now(UTC).isoformat()
    process_started_ns = time.perf_counter_ns()
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **kwargs,
    )
    if process.stdout is None or process.stderr is None or process.stdin is None:
        process.kill()
        raise RuntimeError("production Claude capture pipes were not created")

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    raw_timings: list[dict[str, Any]] = []
    reader_errors: list[BaseException] = []
    event_counter = 0

    def read_stdout() -> None:
        nonlocal event_counter
        try:
            for line_index, line in enumerate(process.stdout):
                arrival_ns = time.perf_counter_ns()
                stdout_chunks.append(line)
                event_index: int | None = None
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    value = None
                if isinstance(value, dict):
                    event_index = event_counter
                    event_counter += 1
                raw_timings.append(
                    {
                        "line_index": line_index,
                        "event_index": event_index,
                        "arrival_ns": arrival_ns,
                        "line_sha256": _sha256(line.encode("utf-8")),
                    }
                )
        except (OSError, UnicodeError, ValueError) as exc:  # pragma: no cover
            reader_errors.append(exc)

    def read_stderr() -> None:
        try:
            stderr_chunks.extend(process.stderr)
        except (OSError, UnicodeError, ValueError) as exc:  # pragma: no cover
            reader_errors.append(exc)

    stdout_thread = threading.Thread(
        target=read_stdout, name="mneme-claude-stdout", daemon=True
    )
    stderr_thread = threading.Thread(
        target=read_stderr, name="mneme-claude-stderr", daemon=True
    )
    stdout_thread.start()
    stderr_thread.start()
    prompt_submitted_ns = time.perf_counter_ns()
    try:
        if input is not None:
            process.stdin.write(input)
    except BrokenPipeError:
        pass
    try:
        process.stdin.close()
    except BrokenPipeError:
        pass

    timed_out = False
    try:
        return_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(process)
        return_code = process.returncode
    stdout_thread.join(timeout=15)
    stderr_thread.join(timeout=15)
    if stdout_thread.is_alive() or stderr_thread.is_alive():
        raise RuntimeError("Claude stream pipes did not close after process exit")
    stdout = "".join(stdout_chunks)
    stderr = "".join(stderr_chunks)
    lines = [
        {
            key: value
            for key, value in item.items()
            if key != "arrival_ns"
        }
        | {
            "elapsed_seconds_from_process_start": round(
                (item["arrival_ns"] - process_started_ns) / 1_000_000_000, 6
            ),
            "elapsed_seconds_from_prompt_submission": round(
                (item["arrival_ns"] - prompt_submitted_ns) / 1_000_000_000, 6
            ),
        }
        for item in raw_timings
    ]
    _LAST_STREAM_CAPTURE = {
        "schema": "mneme.production-stream-timing/v1",
        "clock": "time.perf_counter_ns",
        "process_started_utc": process_started_utc,
        "prompt_submission_started_seconds_after_process_start": round(
            (prompt_submitted_ns - process_started_ns) / 1_000_000_000, 6
        ),
        "line_count": len(lines),
        "event_count": event_counter,
        "lines": lines,
    }
    if reader_errors:
        raise RuntimeError(f"Claude stream reader failed: {reader_errors!r}")
    if timed_out:
        raise subprocess.TimeoutExpired(
            command, timeout, output=stdout, stderr=stderr
        )
    completed = subprocess.CompletedProcess(command, return_code, stdout, stderr)
    if check and return_code:
        raise subprocess.CalledProcessError(
            return_code, command, output=stdout, stderr=stderr
        )
    return completed


class _SharedSubprocessProxy:
    """Timestamp only the Claude stream command; delegate helper commands."""

    TimeoutExpired = subprocess.TimeoutExpired

    @staticmethod
    def run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return _streaming_run(*args, **kwargs)


def _runtime_file_manifest() -> dict[str, str]:
    """Hash every repository file that can execute during a campaign run."""
    paths = set((REPO_ROOT / "mneme").rglob("*.py"))
    paths.update(
        {
            REPO_ROOT / "pyproject.toml",
            REPO_ROOT / "scripts" / "run_guidance_confirmatory_ab.py",
            Path(__file__).resolve(),
            PRODUCTION_PLUGIN / ".claude-plugin" / "plugin.json",
            PRODUCTION_PLUGIN / "hooks" / "hooks.json",
        }
    )
    return {
        _relative(path): _path_sha256(path)
        for path in sorted(paths, key=lambda item: _relative(item))
    }


def _entrypoint_manifest() -> dict[str, dict[str, str]]:
    scripts_dir = shared._runtime_scripts_dir()
    suffix = ".exe" if os.name == "nt" else ""
    result: dict[str, dict[str, str]] = {}
    for name in ("mneme", "mneme-hook", "mneme-guidance-hook"):
        path = scripts_dir / f"{name}{suffix}"
        result[name] = {"path": str(path), "sha256": _path_sha256(path)}
    return result


def _editable_loader_manifest() -> dict[str, Any]:
    """Lock the startup loaders that route console entry points to this tree."""
    resolved_package = Path(mneme.__file__).resolve().parent
    expected_package = (REPO_ROOT / "mneme").resolve()
    if resolved_package != expected_package:
        raise RuntimeError(
            f"mneme imports from {resolved_package}, expected {expected_package}"
        )
    environment = os.environ.copy()
    for name in _SANITIZED_PYTHON_ENV:
        environment.pop(name, None)
    probe = (
        "import json, mneme, mneme.cli; "
        "from mneme.integrations.claude_code import guidance_hook, hook; "
        "print(json.dumps({"
        "'mneme': mneme.__file__, 'cli': mneme.cli.__file__, "
        "'guidance_hook': guidance_hook.__file__, 'hook': hook.__file__}))"
    )
    with tempfile.TemporaryDirectory(prefix="mneme-neutral-import-") as temporary:
        completed = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=temporary,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=15,
        )
    if completed.returncode != 0:
        raise RuntimeError(
            f"neutral-cwd Mneme import probe failed: {completed.stderr}"
        )
    neutral_imports = json.loads(completed.stdout)
    for name, value in neutral_imports.items():
        path = Path(value).resolve()
        if not path.is_relative_to(expected_package):
            raise RuntimeError(
                f"neutral-cwd {name} resolves to {path}, outside {expected_package}"
            )
    user_site = Path(site.getusersitepackages())
    paths = set(user_site.glob("__editable__*mneme*.pth"))
    paths.update(user_site.glob("__editable___mneme*_finder.py"))
    for pattern in ("mneme_hq-*.dist-info", "mneme-*.dist-info"):
        for dist_info in user_site.glob(pattern):
            for name in ("entry_points.txt", "direct_url.json", "METADATA"):
                path = dist_info / name
                if path.is_file():
                    paths.add(path)
    if not paths:
        raise RuntimeError("Mneme editable-install loader metadata is absent")
    return {
        "resolved_package": str(resolved_package),
        "expected_package": str(expected_package),
        "neutral_cwd_imports": neutral_imports,
        "files": {
            str(path): _path_sha256(path)
            for path in sorted(paths, key=lambda item: str(item).lower())
        },
    }


def _pyyaml_runtime_manifest() -> dict[str, Any]:
    """Lock the installed PyYAML code imported by the enforcement CLI path."""
    distribution = importlib_metadata.distribution("PyYAML")
    if not distribution.files:
        raise RuntimeError("PyYAML distribution has no installed-file inventory")

    paths = {
        Path(distribution.locate_file(item)).resolve()
        for item in distribution.files
        if Path(distribution.locate_file(item)).is_file()
    }
    environment = os.environ.copy()
    for name in _SANITIZED_PYTHON_ENV:
        environment.pop(name, None)
    probe = (
        "import json, yaml, yaml._yaml; "
        "print(json.dumps({'yaml': yaml.__file__, "
        "'yaml_extension': yaml._yaml.__file__}))"
    )
    with tempfile.TemporaryDirectory(prefix="mneme-neutral-pyyaml-import-") as temporary:
        completed = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=temporary,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=15,
        )
    if completed.returncode != 0:
        raise RuntimeError(f"neutral-cwd PyYAML import probe failed: {completed.stderr}")
    neutral_imports = json.loads(completed.stdout)
    for name, value in neutral_imports.items():
        resolved = Path(value).resolve()
        if resolved not in paths:
            raise RuntimeError(
                f"neutral-cwd {name} resolves to unlocked distribution file {resolved}"
            )

    return {
        "distribution": distribution.metadata["Name"],
        "version": distribution.version,
        "neutral_cwd_imports": neutral_imports,
        "files": {
            str(path): _path_sha256(path)
            for path in sorted(paths, key=lambda item: str(item).lower())
        },
    }


def _python_runtime_manifest() -> dict[str, Any]:
    """Lock the Store launcher identity and the readable core runtime binaries."""
    runtime_root = Path(sys.base_prefix)
    suffix = ".exe" if os.name == "nt" else ""
    candidates = [runtime_root / f"python{suffix}"]
    if os.name == "nt":
        candidates.extend(sorted(runtime_root.glob("python*.dll")))
    manifest = {
        "launcher_path": sys.executable,
        "runtime_root": str(runtime_root),
        "binaries": {
            path.name: {"path": str(path), "sha256": _path_sha256(path)}
            for path in candidates
        },
        "version": sys.version,
    }
    if os.name == "nt":
        taskkill = _taskkill_executable()
        manifest["process_tree_terminator"] = {
            "path": str(taskkill),
            "sha256": _path_sha256(taskkill),
        }
    return manifest


def _claude_runtime_manifest(
    launcher: Path, version: str, auth: dict[str, Any]
) -> dict[str, Any]:
    """Lock the command shim and the binary it actually dispatches."""
    launch_chain: dict[str, dict[str, str]] = {
        "launcher": {"path": str(launcher), "sha256": _path_sha256(launcher)}
    }
    if os.name == "nt" and launcher.suffix.lower() == ".cmd":
        package_root = (
            launcher.parent / "node_modules" / "@anthropic-ai" / "claude-code"
        )
        package_json = package_root / "package.json"
        package = json.loads(package_json.read_text(encoding="utf-8"))
        if package.get("version") != version:
            raise RuntimeError(
                "Claude package version differs from the command-reported version"
            )
        binary = package_root / "bin" / "claude.exe"
        binary_version = shared._claude_version(binary)
        if binary_version != version:
            raise RuntimeError(
                "Claude runtime binary version differs from the launcher version"
            )
        launch_chain.update(
            {
                "package_manifest": {
                    "path": str(package_json),
                    "sha256": _path_sha256(package_json),
                },
                "runtime_binary": {
                    "path": str(binary),
                    "sha256": _path_sha256(binary),
                    "version": binary_version,
                },
            }
        )
    return {
        "launch_chain": launch_chain,
        "version": version,
        "auth": auth,
        "model_alias": shared.MODEL_ALIAS,
        "expected_resolved_model": shared.EXPECTED_MODEL,
        "expected_api_key_source": shared.EXPECTED_API_KEY_SOURCE,
        "effort": shared.EFFORT,
        "fallback_model": None,
        "permission_mode": "acceptEdits",
        "tools": shared.TOOLS.split(","),
        "skills_disabled": True,
        "auto_memory_disabled": True,
        "claude_md_loading_disabled": True,
        "session_persistence": False,
        "max_budget_usd_per_run": float(shared.MAX_BUDGET_USD),
    }


def _expected_guidance() -> dict[str, dict[str, Any]]:
    expectations: dict[str, dict[str, Any]] = {}
    for task in shared.TASKS:
        result = build_guidance(MEMORY_FIXTURE, task["prompt"])
        if task["governed"] and not result.context:
            raise RuntimeError(f"governed task has no expected guidance: {task['id']}")
        if not task["governed"] and result.context:
            raise RuntimeError(f"control task unexpectedly retrieves guidance: {task['id']}")
        expectations[task["id"]] = {
            "governed": task["governed"],
            "reason": result.reason,
            "decision_ids": list(result.decision_ids),
            "context_sha256": (
                _sha256(result.context.encode("utf-8")) if result.context else None
            ),
            "context_length": len(result.context),
        }
    return expectations


def _schedule() -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for task_index, task in enumerate(shared.TASKS):
        arms = shared.ARMS if task_index % 2 == 0 else tuple(reversed(shared.ARMS))
        for repetition in range(1, 4):
            for arm in arms:
                runs.append(
                    {
                        "evaluation": EVALUATION,
                        "task_id": task["id"],
                        "arm": arm,
                        "repetition": repetition,
                    }
                )
    if len(runs) != 42:
        raise RuntimeError(f"production schedule must contain 42 slots, got {len(runs)}")
    return runs


def _provenance_manifest() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for path, expected in EXPECTED_PROVENANCE_HASHES.items():
        actual = _path_sha256(path)
        if actual != expected:
            raise RuntimeError(
                f"frozen provenance drift for {_relative(path)}: "
                f"expected {expected}, got {actual}"
            )
        result[_relative(path)] = {"sha256": actual}
    return result


def _production_permission_rules() -> list[str]:
    """Constrain external reads without hiding in-repository Mneme memory."""
    return [
        f"Read({REPO_ROOT}/**)",
        f"Glob({REPO_ROOT}/**)",
        f"Grep({REPO_ROOT}/**)",
        "Read(../**)",
        "Glob(../**)",
        "Grep(../**)",
    ]


def _execution_payload() -> dict[str, Any]:
    design_sha = _path_sha256(DESIGN_LOCK)
    protocol_sha = _path_sha256(PROTOCOL)
    if design_sha != EXPECTED_DESIGN_SHA256:
        raise RuntimeError(
            f"frozen design changed: expected {EXPECTED_DESIGN_SHA256}, got {design_sha}"
        )
    if protocol_sha != EXPECTED_PROTOCOL_SHA256:
        raise RuntimeError(
            f"frozen protocol changed: expected {EXPECTED_PROTOCOL_SHA256}, "
            f"got {protocol_sha}"
        )

    claude = shared._claude_executable()
    version = shared._claude_version(claude)
    if version != shared.CLAUDE_VERSION:
        raise RuntimeError(
            f"Claude Code version drift: expected {shared.CLAUDE_VERSION}, got {version}"
        )
    auth = shared._auth_status(claude)
    expected_auth = {
        "loggedIn": True,
        "authMethod": "claude.ai",
        "apiProvider": "firstParty",
        "subscriptionType": "pro",
    }
    if auth != expected_auth:
        raise RuntimeError(f"unexpected Claude authentication state: {auth}")

    return {
        "schema": "mneme.production-effectiveness-execution-lock/v1",
        "study_id": "production-guidance-effectiveness-role-aware-2026-08-14",
        "evaluation": EVALUATION,
        "artifact_directory": _relative(OUTPUT_ROOT),
        "authorization": {
            "path": _relative(AUTHORIZATION),
            "sha256": _path_sha256(AUTHORIZATION),
            "decision": "CONDITIONAL_GO",
            "scope": "controlled seven-task fixture only",
            "r6_status": "PERMANENT_FAIL_UNCHANGED",
        },
        "frozen_design": {
            "path": _relative(DESIGN_LOCK),
            "sha256": design_sha,
            "modified": False,
        },
        "scoring_protocol": {
            "path": _relative(PROTOCOL),
            "sha256": protocol_sha,
            "modified": False,
            "authoritative_for_all_metrics_and_claim_gates": True,
        },
        "frozen_provenance": _provenance_manifest(),
        "runtime_files": _runtime_file_manifest(),
        "runtime": {
            "python": _python_runtime_manifest(),
            "python_dependencies": {"PyYAML": _pyyaml_runtime_manifest()},
            "entrypoints": _entrypoint_manifest(),
            "editable_loader": _editable_loader_manifest(),
            "claude": _claude_runtime_manifest(claude, version, auth),
            "hook_import_environment": {
                "unset_before_claude_launch": list(_SANITIZED_PYTHON_ENV)
            },
        },
        "plugin": {
            "path": _relative(PRODUCTION_PLUGIN),
            "user_prompt_submit_hook": "mneme-guidance-hook",
            "pre_tool_use_hook": "mneme-hook",
            "strict_enforcement_both_arms": True,
        },
        "fixture": {
            "memory_path": _relative(MEMORY_FIXTURE),
            "memory_sha256": _path_sha256(MEMORY_FIXTURE),
            "base_files": {
                path: _sha256(content.encode("utf-8"))
                for path, content in sorted(shared.BASE_FILES.items())
            },
            "tasks": list(shared.TASKS),
            "production_memory_discovery_allowed": True,
        },
        "arms": {
            "baseline": {"MNEME_GUIDANCE": "false"},
            "treatment": {"MNEME_GUIDANCE": "true"},
            "only_intended_difference": "MNEME_GUIDANCE",
        },
        "production_settings": {
            "deny_rules": _production_permission_rules(),
            "memory_read_denied": False,
            "empty_mcp": True,
            "no_chrome": True,
        },
        "init_contract": {
            "tools": sorted(shared.TOOLS.split(",")),
            "permission_mode": "acceptEdits",
            "skills": [],
            "slash_commands": [],
            "mcp_servers": [],
            "memory_paths": [],
            "plugins": [
                {"name": "mneme", "path": str(PRODUCTION_PLUGIN.resolve())}
            ],
            "violation": "preserve evidence and stop before any later slot",
        },
        "schedule": _schedule(),
        "sample": {
            "runs": 42,
            "per_arm": 21,
            "governed_per_arm": 15,
            "controls_per_arm": 6,
        },
        "expected_guidance": _expected_guidance(),
        "injection_delivery_contract": {
            "all_arms_transport": (
                "exactly one matched successful ordered UserPromptSubmit start "
                "and response"
            ),
            "governed_treatment": (
                "exact locked context in one successful UserPromptSubmit response "
                "before the first assistant event and attempted edit"
            ),
            "missing_empty_mismatched_duplicate_or_late": (
                "scored treatment operational failure; preserve slot; no rerun; stop"
            ),
            "baseline_nonempty_context": (
                "arm-isolation failure; preserve evidence; stop and re-lock"
            ),
            "treatment_control_nonempty_context": "scored product outcome",
            "no_turn_before_prompt_hook_starts": (
                "frozen pre-turn technical invalidation; same-slot rerun permitted"
            ),
            "hook_started_missing_or_failed_delivery": (
                "scored operational failure; no rerun; stop"
            ),
        },
        "metric_capture": {
            "stream_timing": (
                "monotonic stdout line-arrival time from prompt submission"
            ),
            "attempt_timing": "every mutating attempt receives its event time",
            "attempt_model_usage": (
                "deduplicated assistant-message token usage through every attempt"
            ),
            "scoring_protocol_modified": False,
        },
        "single_execution_owner": {
            "required": True,
            "owner": "current Codex task that created this lock",
            "parallel_or_split_execution_prohibited": True,
        },
        "campaign_state": {
            "authorization": "CONDITIONAL_GO",
            "execution": "NOT_STARTED",
            "independent_lock_review_required": True,
            "production_trials_started": False,
            "r6_mutation_authorized": False,
        },
        "claim_ceiling": (
            "Automatic pre-generation guidance demonstrated incremental "
            "effectiveness through the production Claude Code integration in a "
            "controlled seven-task fixture."
        ),
        "forbidden_claim": "effectiveness across varied real-world repositories",
    }


def render_execution_lock() -> dict[str, Any]:
    if OUTPUT_ROOT.exists():
        raise RuntimeError(
            "production artifact directory already exists; do not create a fresh lock"
        )
    return {
        **_execution_payload(),
        "locked_at": datetime.now(UTC).isoformat(),
        "status": "LOCKED_NOT_STARTED",
    }


def _verify_sidecar() -> None:
    if not EXECUTION_LOCK_SHA.is_file():
        raise RuntimeError("execution-lock SHA sidecar is absent")
    fields = EXECUTION_LOCK_SHA.read_text(encoding="utf-8").strip().split()
    if not fields or fields[0].upper() != _path_sha256(EXECUTION_LOCK):
        raise RuntimeError("execution-lock SHA sidecar does not match the lock")


def _verify_review_attestation() -> dict[str, Any]:
    if not REVIEW_ATTESTATION.is_file():
        raise RuntimeError("independent lock-review attestation is absent")
    review = json.loads(REVIEW_ATTESTATION.read_text(encoding="utf-8"))
    expected = {
        "status": "PASS",
        "execution_lock_sha256": _path_sha256(EXECUTION_LOCK),
        "authorization_sha256": _path_sha256(AUTHORIZATION),
        "independent_of_execution_owner": True,
        "trials_started_at_review": False,
        "open_blocking_findings": 0,
    }
    observed = {key: review.get(key) for key in expected}
    if observed != expected:
        raise RuntimeError(
            f"independent lock-review attestation mismatch: {observed}"
        )
    return review


def verify_execution_lock(*, require_review: bool = False) -> dict[str, Any]:
    if not EXECUTION_LOCK.is_file():
        raise RuntimeError("production execution lock is absent")
    locked = json.loads(EXECUTION_LOCK.read_text(encoding="utf-8"))
    if locked.get("status") != "LOCKED_NOT_STARTED":
        raise RuntimeError(f"unexpected execution-lock status: {locked.get('status')}")
    comparable = {
        key: value for key, value in locked.items() if key not in {"locked_at", "status"}
    }
    current = _execution_payload()
    if comparable != current:
        raise RuntimeError("production execution lock mismatch; no run is permitted")
    _verify_sidecar()
    if require_review:
        _verify_review_attestation()
    return locked


def _adapt_lock_for_shared_runner(locked: dict[str, Any]) -> dict[str, Any]:
    """Expose the one legacy key consumed by the preserved shared runner."""
    launch_chain = locked["runtime"]["claude"]["launch_chain"]
    executable = launch_chain.get("runtime_binary", launch_chain["launcher"])["path"]
    return {**locked, "claude": {"executable": executable}}


def _verified_shared_lock() -> dict[str, Any]:
    return _adapt_lock_for_shared_runner(
        verify_execution_lock(require_review=True)
    )


def _production_settings(
    root: Path, workspace: Path, memory: Path
) -> tuple[Path, Path]:
    del workspace
    if memory.parent.name != ".mneme":
        raise RuntimeError("production memory must use the in-repository .mneme path")
    settings = root / "claude-eval-settings.json"
    shared._write_json(
        settings, {"permissions": {"deny": _production_permission_rules()}}
    )
    mcp = root / "empty-mcp.json"
    shared._write_json(mcp, {"mcpServers": {}})
    return settings, mcp


def _hook_context(event: dict[str, Any]) -> str:
    for field in ("output", "stdout"):
        raw = event.get(field)
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        specific = payload.get("hookSpecificOutput") if isinstance(payload, dict) else None
        context = specific.get("additionalContext") if isinstance(specific, dict) else None
        if isinstance(context, str):
            return context
    return ""


def _first_assistant_index(events: list[dict[str, Any]]) -> int | None:
    return next(
        (index for index, event in enumerate(events) if event.get("type") == "assistant"),
        None,
    )


def _first_edit_index(events: list[dict[str, Any]]) -> int | None:
    for index, event in enumerate(events):
        if event.get("type") != "assistant":
            continue
        content = event.get("message", {}).get("content", [])
        if any(
            isinstance(block, dict)
            and block.get("type") == "tool_use"
            and block.get("name") in _MUTATING_TOOLS
            for block in content
        ):
            return index
    return None


def _prompt_hook_observed(events: list[dict[str, Any]]) -> bool:
    """Treat a start or response as evidence that delivery processing began."""
    return any(
        event.get("type") == "system"
        and event.get("subtype") in {"hook_started", "hook_response"}
        and event.get("hook_event") == "UserPromptSubmit"
        for event in events
    )


def assess_injection_delivery(
    events: list[dict[str, Any]],
    task: dict[str, Any],
    arm: str,
    expected: dict[str, Any],
) -> dict[str, Any]:
    """Classify delivery without converting product failures to invalidations."""
    first_assistant = _first_assistant_index(events)
    first_edit = _first_edit_index(events)
    start_events = [
        {"hook_id": event.get("hook_id"), "event_index": index}
        for index, event in enumerate(events)
        if event.get("type") == "system"
        and event.get("subtype") == "hook_started"
        and event.get("hook_event") == "UserPromptSubmit"
    ]
    responses: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        if not (
            event.get("type") == "system"
            and event.get("subtype") == "hook_response"
            and event.get("hook_event") == "UserPromptSubmit"
        ):
            continue
        context = _hook_context(event)
        matching_starts = [
            item
            for item in start_events
            if item["hook_id"] == event.get("hook_id")
        ]
        start_index = (
            matching_starts[0]["event_index"] if len(matching_starts) == 1 else None
        )
        responses.append(
            {
                "event_index": index,
                "hook_id": event.get("hook_id"),
                "start_event_index": start_index,
                "outcome": event.get("outcome"),
                "exit_code": event.get("exit_code"),
                "context_sha256": (
                    _sha256(context.encode("utf-8")) if context else None
                ),
                "context_length": len(context),
                "decision_ids": _GUIDANCE_ID.findall(context),
                "before_first_assistant": (
                    first_assistant is None or index < first_assistant
                ),
                "before_first_edit": first_edit is None or index < first_edit,
                "start_precedes_response": (
                    start_index is not None and start_index < index
                ),
            }
        )

    nonempty = [item for item in responses if item["context_length"] > 0]
    result: dict[str, Any] = {
        "schema": "mneme.production-injection-delivery/v1",
        "task_id": task["id"],
        "arm": arm,
        "governed": task["governed"],
        "first_assistant_event_index": first_assistant,
        "first_edit_event_index": first_edit,
        "starts": start_events,
        "responses": responses,
        "expected_context_sha256": expected["context_sha256"],
        "expected_decision_ids": expected["decision_ids"],
        "scored_treatment_operational_failure": False,
        "scored_operational_failure": False,
        "arm_isolation_failure": False,
        "rerun_permitted": False,
        "stop_campaign": False,
        "reasons": [],
    }

    transport_pass = (
        len(start_events) == 1
        and len(responses) == 1
        and isinstance(start_events[0]["hook_id"], str)
        and bool(start_events[0]["hook_id"])
        and start_events[0]["hook_id"] == responses[0]["hook_id"]
        and responses[0]["outcome"] == "success"
        and responses[0]["exit_code"] == 0
        and responses[0]["start_precedes_response"]
        and responses[0]["before_first_assistant"]
        and responses[0]["before_first_edit"]
    )

    if arm == "baseline":
        if not transport_pass:
            result["scored_operational_failure"] = True
            result["stop_campaign"] = True
            result["reasons"].append(
                "baseline lacks one successful ordered UserPromptSubmit response"
            )
        if nonempty:
            result["arm_isolation_failure"] = True
            result["stop_campaign"] = True
            result["reasons"].append("baseline received automatic guidance context")
        result["delivery_pass"] = transport_pass and not nonempty
        return result

    if not task["governed"]:
        if not transport_pass:
            result["scored_operational_failure"] = True
            result["scored_treatment_operational_failure"] = True
            result["stop_campaign"] = True
            result["reasons"].append(
                "treatment control lacks one successful ordered "
                "UserPromptSubmit response"
            )
        elif nonempty:
            result["reasons"].append(
                "control treatment received guidance; retain as scored product outcome"
            )
        result["delivery_pass"] = transport_pass and not nonempty
        return result

    exact = [
        item
        for item in nonempty
        if item["context_sha256"] == expected["context_sha256"]
        and item["decision_ids"] == expected["decision_ids"]
        and item["outcome"] == "success"
        and item["exit_code"] == 0
        and item["start_precedes_response"]
    ]
    on_time = [
        item
        for item in exact
        if item["before_first_assistant"] and item["before_first_edit"]
    ]
    passed = transport_pass and len(exact) == 1 and len(on_time) == 1
    result["delivery_pass"] = passed
    if not passed:
        result["scored_operational_failure"] = True
        result["scored_treatment_operational_failure"] = True
        result["stop_campaign"] = True
        if not nonempty:
            result["reasons"].append("governed treatment guidance missing or empty")
        if not transport_pass:
            result["reasons"].append(
                "governed treatment requires exactly one matched ordered hook "
                "start and response"
            )
        if not exact:
            result["reasons"].append(
                "governed treatment guidance mismatched or hook response failed"
            )
        elif not on_time:
            result["reasons"].append(
                "governed treatment guidance appeared after assistant generation or edit"
            )
    return result


def assess_init_contamination(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate frozen Claude init controls for a real production-path run."""
    init_events = [
        event
        for event in events
        if event.get("type") == "system" and event.get("subtype") == "init"
    ]
    violations: list[str] = []
    if len(init_events) != 1:
        violations.append(f"expected one init event, observed {len(init_events)}")
        return {
            "schema": "mneme.production-init-contamination/v1",
            "pass": False,
            "violations": violations,
            "observed": init_events,
        }

    init = init_events[0]
    if sorted(init.get("tools") or []) != sorted(shared.TOOLS.split(",")):
        violations.append("allowed tools differ from the frozen set")
    if init.get("permissionMode") != "acceptEdits":
        violations.append("permission mode differs from acceptEdits")
    if init.get("skills") != []:
        violations.append("skills differ from the frozen empty set")
    if init.get("slash_commands") != []:
        violations.append("slash commands differ from the frozen empty set")
    if init.get("mcp_servers") != []:
        violations.append("MCP servers differ from the frozen empty set")
    if init.get("memory_paths") not in ([], None):
        violations.append("Claude auto-memory paths are present")

    plugins = init.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1:
        violations.append("expected exactly one production plugin")
    else:
        plugin = plugins[0]
        path = plugin.get("path") if isinstance(plugin, dict) else None
        if not isinstance(plugin, dict) or plugin.get("name") != "mneme":
            violations.append("production plugin name differs from mneme")
        if not isinstance(path, str) or Path(path).resolve() != PRODUCTION_PLUGIN.resolve():
            violations.append("production plugin path differs from the locked path")

    return {
        "schema": "mneme.production-init-contamination/v1",
        "pass": not violations,
        "violations": violations,
        "observed": {
            key: init.get(key)
            for key in (
                "tools",
                "permissionMode",
                "skills",
                "slash_commands",
                "mcp_servers",
                "memory_paths",
                "plugins",
                "model",
                "claude_code_version",
                "apiKeySource",
            )
        },
    }


def _init_validation_required(
    events: list[dict[str, Any]], *, technical_invalid: bool
) -> bool:
    return not technical_invalid or any(
        event.get("type") == "system" and event.get("subtype") == "init"
        for event in events
    )


def _configure_shared_runner() -> None:
    shared.EXECUTION_LOCK = EXECUTION_LOCK
    shared.OUTPUT_ROOT = OUTPUT_ROOT
    shared.PRODUCTION_PLUGIN = PRODUCTION_PLUGIN
    shared.EVALUATIONS = (EVALUATION,)
    shared._settings = _production_settings
    shared.verify_execution_lock = _verified_shared_lock
    shared.subprocess = _SharedSubprocessProxy


@contextmanager
def _sanitized_python_environment():
    """Make the actual Claude/hook import environment match the locked probe."""
    saved = {name: os.environ.get(name) for name in _SANITIZED_PYTHON_ENV}
    for name in _SANITIZED_PYTHON_ENV:
        os.environ.pop(name, None)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _artifact_root(result: dict[str, Any]) -> Path:
    archived = result.get("archived_to")
    if isinstance(archived, str):
        return Path(archived)
    return shared._run_dir(
        EVALUATION, result["task_id"], result["arm"], result["repetition"]
    )


def _model_usage_through_event(
    events: list[dict[str, Any]], event_index: int
) -> dict[str, Any]:
    fields = (
        "input_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "output_tokens",
    )
    per_message: dict[str, dict[str, int]] = {}
    for event in events[: event_index + 1]:
        if event.get("type") != "assistant":
            continue
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        message_id = message.get("id")
        usage = message.get("usage")
        if not isinstance(message_id, str) or not isinstance(usage, dict):
            continue
        observed = per_message.setdefault(message_id, {})
        for field in fields:
            value = usage.get(field)
            if isinstance(value, int):
                observed[field] = max(observed.get(field, 0), value)
    return {
        "method": "sum maxima per unique assistant message id",
        "assistant_message_count": len(per_message),
        **{
            field: sum(usage.get(field, 0) for usage in per_message.values())
            for field in fields
        },
    }


def _annotate_attempt_metrics(
    root: Path,
    result: dict[str, Any],
    events: list[dict[str, Any]],
    stdout: str,
    capture: dict[str, Any],
) -> None:
    by_event = _validate_stream_timing(stdout, events, capture)
    attempts_path = root / "attempts.json"
    attempts = json.loads(attempts_path.read_text(encoding="utf-8"))
    if not isinstance(attempts, list):
        raise TypeError("captured attempts must be a list")
    for attempt in attempts:
        event_index = attempt.get("event_index")
        timing = by_event.get(event_index)
        if not isinstance(event_index, int) or timing is None:
            raise RuntimeError(
                f"attempt event {event_index!r} has no line-arrival timing"
            )
        attempt["elapsed_seconds_from_prompt_submission"] = timing[
            "elapsed_seconds_from_prompt_submission"
        ]
        attempt["elapsed_seconds_from_process_start"] = timing[
            "elapsed_seconds_from_process_start"
        ]
        attempt["model_usage_through_attempt"] = _model_usage_through_event(
            events, event_index
        )
    (root / "attempts.json").write_text(_json_text(attempts), encoding="utf-8")
    (root / "event_timing.json").write_text(
        _json_text(capture), encoding="utf-8"
    )
    result["seconds_to_first_attempt"] = (
        attempts[0]["elapsed_seconds_from_prompt_submission"] if attempts else None
    )
    result["stream_timing"] = {
        "schema": capture["schema"],
        "clock": capture["clock"],
        "artifact": "event_timing.json",
        "line_count": capture["line_count"],
        "event_count": capture["event_count"],
        "attempts_annotated": len(attempts),
    }


def _validate_stream_timing(
    stdout: str, events: list[dict[str, Any]], capture: dict[str, Any]
) -> dict[int, dict[str, Any]]:
    """Mechanically bind timing records to the persisted JSONL event stream."""
    if capture.get("schema") != "mneme.production-stream-timing/v1":
        raise RuntimeError("stream timing schema is missing or unexpected")
    if capture.get("clock") != "time.perf_counter_ns":
        raise RuntimeError("stream timing clock is missing or unexpected")
    started = capture.get("process_started_utc")
    if not isinstance(started, str):
        raise TypeError("stream timing process-start wall clock is absent")
    try:
        datetime.fromisoformat(started)
    except ValueError as exc:
        raise RuntimeError("stream timing process-start wall clock is invalid") from exc
    prompt_offset = capture.get(
        "prompt_submission_started_seconds_after_process_start"
    )
    if not isinstance(prompt_offset, (int, float)) or prompt_offset < 0:
        raise RuntimeError("stream timing prompt-submission offset is invalid")
    received_lines = stdout.splitlines(keepends=True)
    timing_lines = capture.get("lines")
    if (
        not isinstance(timing_lines, list)
        or capture.get("line_count") != len(timing_lines)
        or len(received_lines) != len(timing_lines)
    ):
        raise RuntimeError("stream timing line count does not match captured stdout")
    expected_event_index = 0
    previous_process_elapsed = -1.0
    previous_prompt_elapsed = float("-inf")
    for index, (line, timing) in enumerate(zip(received_lines, timing_lines)):
        if timing.get("line_index") != index or timing.get("line_sha256") != _sha256(
            line.encode("utf-8")
        ):
            raise RuntimeError(f"stream timing line {index} does not match stdout")
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            value = None
        expected = expected_event_index if isinstance(value, dict) else None
        if timing.get("event_index") != expected:
            raise RuntimeError("stream timing event mapping is not sequential")
        if expected is not None:
            expected_event_index += 1
        process_elapsed = timing.get("elapsed_seconds_from_process_start")
        prompt_elapsed = timing.get("elapsed_seconds_from_prompt_submission")
        if not isinstance(process_elapsed, (int, float)):
            raise TypeError("stream timing process elapsed value is invalid")
        if process_elapsed < 0:
            raise RuntimeError("stream timing process elapsed value is invalid")
        if not isinstance(prompt_elapsed, (int, float)):
            raise TypeError("stream timing prompt elapsed value is invalid")
        if (
            process_elapsed < previous_process_elapsed
            or prompt_elapsed < previous_prompt_elapsed
        ):
            raise RuntimeError("stream timing elapsed values are not monotonic")
        if abs((process_elapsed - prompt_elapsed) - prompt_offset) > 0.000002:
            raise RuntimeError("stream timing elapsed origins are contradictory")
        previous_process_elapsed = float(process_elapsed)
        previous_prompt_elapsed = float(prompt_elapsed)
    if (
        capture.get("event_count") != expected_event_index
        or expected_event_index != len(events)
    ):
        raise RuntimeError("stream timing event count does not match parsed events")

    return {
        item["event_index"]: item
        for item in timing_lines
        if isinstance(item.get("event_index"), int)
    }


def _classify_slot_delivery(
    events: list[dict[str, Any]],
    result: dict[str, Any],
    task: dict[str, Any],
    arm: str,
    expected: dict[str, Any],
) -> dict[str, Any]:
    if result.get("technical_invalid") and not _prompt_hook_observed(events):
        delivery: dict[str, Any] = {
            "schema": "mneme.production-injection-delivery/v1",
            "task_id": task["id"],
            "arm": arm,
            "governed": task["governed"],
            "delivery_pass": None,
            "classification": "pre_hook_technical_invalidation",
            "scored_operational_failure": False,
            "scored_treatment_operational_failure": False,
            "arm_isolation_failure": False,
            "rerun_permitted": True,
            "stop_campaign": True,
            "reasons": [
                (
                    "no real assistant turn; apply the frozen same-slot technical "
                    "invalidation rule"
                )
            ],
        }
    else:
        delivery = assess_injection_delivery(events, task, arm, expected)
        if result.get("technical_invalid") and delivery["delivery_pass"]:
            delivery["classification"] = "post_delivery_no_turn_technical_invalidation"
            delivery["rerun_permitted"] = True
            delivery["stop_campaign"] = True
            delivery["reasons"].append(
                "guidance transport completed, but no real assistant turn occurred; "
                "apply the frozen same-slot technical invalidation rule"
            )
    if _init_validation_required(
        events, technical_invalid=bool(result.get("technical_invalid"))
    ):
        contamination = assess_init_contamination(events)
        delivery["init_contamination"] = contamination
        if not contamination["pass"]:
            delivery["contamination_failure"] = True
            delivery["rerun_permitted"] = False
            delivery["stop_campaign"] = True
            delivery["reasons"].extend(contamination["violations"])
    if not result.get("isolation_pass", True):
        delivery["contamination_failure"] = True
        delivery["rerun_permitted"] = False
        delivery["stop_campaign"] = True
        delivery["reasons"].extend(result.get("isolation_violations") or [])
    return delivery


def run_slot(task: dict[str, Any], arm: str, repetition: int) -> dict[str, Any]:
    global _LAST_STREAM_CAPTURE
    _configure_shared_runner()
    _LAST_STREAM_CAPTURE = None
    with _sanitized_python_environment():
        result = shared.run_one(EVALUATION, task, arm, repetition)
    root = _artifact_root(result)
    stdout = root / "stdout.jsonl"
    if not stdout.is_file():
        return result
    if _LAST_STREAM_CAPTURE is None and isinstance(
        result.get("injection_delivery"), dict
    ):
        return result  # idempotent inspection of an already annotated slot
    if _LAST_STREAM_CAPTURE is None:
        raise RuntimeError("fresh production run lacks monotonic stream timing")
    lock = json.loads(EXECUTION_LOCK.read_text(encoding="utf-8"))
    stdout_text = stdout.read_text(encoding="utf-8")
    events = parse_events(stdout_text)
    _annotate_attempt_metrics(
        root, result, events, stdout_text, _LAST_STREAM_CAPTURE
    )
    _LAST_STREAM_CAPTURE = None
    delivery = _classify_slot_delivery(
        events,
        result,
        task,
        arm,
        lock["expected_guidance"][task["id"]],
    )
    result["injection_delivery"] = delivery
    result["scored_treatment_operational_failure"] = delivery[
        "scored_treatment_operational_failure"
    ]
    result["arm_isolation_failure"] = delivery["arm_isolation_failure"]
    (root / "injection_delivery.json").write_text(
        _json_text(delivery), encoding="utf-8"
    )
    (root / "metadata.json").write_text(_json_text(result), encoding="utf-8")
    return result


def _selected_slots(args: argparse.Namespace) -> list[tuple[dict[str, Any], str, int]]:
    lookup = {task["id"]: task for task in shared.TASKS}
    if args.all:
        return [
            (lookup[item["task_id"]], item["arm"], item["repetition"])
            for item in _schedule()
        ]
    if args.task and args.arm and args.repetition:
        return [(lookup[args.task], args.arm, args.repetition)]
    raise ValueError("use --all or provide --task, --arm, and --repetition")


def _slot_key(task_id: str, arm: str, repetition: int) -> str:
    return f"{task_id}__{arm}__r{repetition}"


def _slot_metadata(root: Path, item: dict[str, Any]) -> Path:
    return (
        root
        / EVALUATION
        / "runs"
        / _slot_key(item["task_id"], item["arm"], item["repetition"])
        / "metadata.json"
    )


_REQUIRED_SLOT_ARTIFACTS = (
    "stdout.jsonl",
    "stderr.log",
    "attempts.json",
    "first_attempt.json",
    "first_attempt_workspace.json",
    "first_attempt.diff",
    "hook_events.json",
    "offline_enforcement.json",
    "isolation.json",
    "final_workspace.json",
    "workspace.diff",
    "event_timing.json",
    "injection_delivery.json",
    "metadata.json",
)


def _read_json_artifact(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unreadable JSON artifact: {path}") from exc


def _validate_preserved_artifact(
    slot_root: Path,
    item: dict[str, Any],
    locked: dict[str, Any],
    lock_sha256: str,
    *,
    archived: bool,
) -> dict[str, Any]:
    missing = [
        name for name in _REQUIRED_SLOT_ARTIFACTS if not (slot_root / name).is_file()
    ]
    if missing:
        raise RuntimeError(
            f"preserved slot lacks required artifacts {missing}: {slot_root}; stop"
        )
    metadata = _read_json_artifact(slot_root / "metadata.json")
    identity = {
        "evaluation": EVALUATION,
        "task_id": item["task_id"],
        "arm": item["arm"],
        "repetition": item["repetition"],
    }
    observed_identity = {key: metadata.get(key) for key in identity}
    if observed_identity != identity:
        raise RuntimeError(
            f"preserved slot identity mismatch: {observed_identity}; stop"
        )
    if metadata.get("execution_lock_sha256") != lock_sha256:
        raise RuntimeError("preserved slot execution-lock hash mismatch; stop")
    if archived:
        archived_to = metadata.get("archived_to")
        if not isinstance(archived_to, str) or Path(archived_to).resolve() != slot_root.resolve():
            raise RuntimeError("archived slot path evidence is missing or mismatched; stop")
    elif metadata.get("technical_invalid") or not metadata.get("isolation_pass"):
        raise RuntimeError("completed run is technically invalid or contaminated; stop")

    stdout = (slot_root / "stdout.jsonl").read_text(encoding="utf-8")
    events = parse_events(stdout)
    timing = _read_json_artifact(slot_root / "event_timing.json")
    by_event = _validate_stream_timing(stdout, events, timing)
    attempts = _read_json_artifact(slot_root / "attempts.json")
    if not isinstance(attempts, list):
        raise TypeError("preserved attempts artifact is not a list")
    raw_attempt_indices = [
        event_index
        for event_index, event in enumerate(events)
        if any(
            isinstance(block, dict)
            and block.get("type") == "tool_use"
            and block.get("name") in _MUTATING_TOOLS
            for block in event.get("message", {}).get("content", [])
        )
    ]
    if [attempt.get("event_index") for attempt in attempts] != raw_attempt_indices:
        raise RuntimeError("attempt indexes disagree with raw events; stop")
    for ordinal, attempt in enumerate(attempts, start=1):
        event_index = attempt["event_index"]
        event_timing = by_event[event_index]
        if attempt.get("ordinal") != ordinal:
            raise RuntimeError("attempt ordinals are not contiguous; stop")
        if attempt.get("elapsed_seconds_from_prompt_submission") != event_timing.get(
            "elapsed_seconds_from_prompt_submission"
        ):
            raise RuntimeError("attempt elapsed time disagrees with event timing; stop")
        if attempt.get("elapsed_seconds_from_process_start") != event_timing.get(
            "elapsed_seconds_from_process_start"
        ):
            raise RuntimeError("attempt process time disagrees with event timing; stop")
        if attempt.get("model_usage_through_attempt") != _model_usage_through_event(
            events, event_index
        ):
            raise RuntimeError("attempt model usage disagrees with raw events; stop")
    expected_first_elapsed = (
        attempts[0]["elapsed_seconds_from_prompt_submission"] if attempts else None
    )
    if metadata.get("seconds_to_first_attempt") != expected_first_elapsed:
        raise RuntimeError("first-attempt elapsed time disagrees with attempts; stop")

    persisted_delivery = _read_json_artifact(slot_root / "injection_delivery.json")
    if metadata.get("injection_delivery") != persisted_delivery:
        raise RuntimeError("metadata and delivery artifact disagree; stop")
    task = next(task for task in shared.TASKS if task["id"] == item["task_id"])
    recomputed_delivery = _classify_slot_delivery(
        events,
        metadata,
        task,
        item["arm"],
        locked["expected_guidance"][item["task_id"]],
    )
    if persisted_delivery != recomputed_delivery:
        raise RuntimeError("persisted delivery disagrees with raw hook events; stop")
    if _read_json_artifact(slot_root / "hook_events.json") != shared.hook_events(events):
        raise RuntimeError("hook-event artifact disagrees with raw events; stop")
    isolation = _read_json_artifact(slot_root / "isolation.json")
    if isolation.get("pass") != metadata.get("isolation_pass") or isolation.get(
        "violations"
    ) != metadata.get("isolation_violations"):
        raise RuntimeError("isolation artifact disagrees with metadata; stop")

    if not archived:
        blind_id = metadata.get("blind_id")
        evaluation_root = slot_root.parent.parent
        blind_review = evaluation_root / "blinded" / str(blind_id) / "review.json"
        blind_map = evaluation_root / "private" / "blinding-map.json"
        if not isinstance(blind_id, str) or not blind_review.is_file() or not blind_map.is_file():
            raise RuntimeError("completed slot lacks blinded scoring artifacts; stop")
        mapping = _read_json_artifact(blind_map)
        expected_key = _slot_key(item["task_id"], item["arm"], item["repetition"])
        if mapping.get("runs", {}).get(blind_id) != expected_key:
            raise RuntimeError("blinding map disagrees with completed slot; stop")
    return metadata


def _assert_slot_order(
    task: dict[str, Any], arm: str, repetition: int, *, root: Path = OUTPUT_ROOT
) -> None:
    """Prevent split owners or manual selection from bypassing frozen order."""
    requested = _slot_key(task["id"], arm, repetition)
    if not EXECUTION_LOCK.is_file():
        raise RuntimeError("production execution lock is absent; stop")
    locked = _read_json_artifact(EXECUTION_LOCK)
    lock_sha256 = _path_sha256(EXECUTION_LOCK)
    staging_root = root / EVALUATION / ".staging"
    if staging_root.exists() and any(staging_root.iterdir()):
        raise RuntimeError(
            f"unresolved staging artifacts exist at {staging_root}; stop"
        )
    invalidation_root = root / EVALUATION / "invalidations"
    rerunnable_invalidations: list[tuple[str, Path]] = []
    if invalidation_root.exists():
        for entry in sorted(invalidation_root.iterdir()):
            metadata_path = entry / "metadata.json"
            if not entry.is_dir() or not metadata_path.is_file():
                raise RuntimeError(
                    f"unresolved invalidation artifact: {entry}; stop"
                )
            metadata = _read_json_artifact(metadata_path)
            identity = (
                metadata.get("task_id"),
                metadata.get("arm"),
                metadata.get("repetition"),
            )
            invalid_item = next(
                (
                    item
                    for item in _schedule()
                    if (
                        item["task_id"],
                        item["arm"],
                        item["repetition"],
                    )
                    == identity
                ),
                None,
            )
            if invalid_item is None:
                raise RuntimeError(f"unknown archived slot identity: {metadata_path}; stop")
            metadata = _validate_preserved_artifact(
                entry, invalid_item, locked, lock_sha256, archived=True
            )
            delivery = metadata.get("injection_delivery")
            if delivery.get("stop_campaign") and not delivery.get(
                "rerun_permitted"
            ):
                raise RuntimeError(
                    f"campaign is stopped by archived delivery failure: {metadata_path}"
                )
            rerunnable_invalidations.append(
                (
                    _slot_key(
                        invalid_item["task_id"],
                        invalid_item["arm"],
                        invalid_item["repetition"],
                    ),
                    metadata_path,
                )
            )
    next_pending: str | None = None
    for item in _schedule():
        metadata_path = _slot_metadata(root, item)
        key = _slot_key(item["task_id"], item["arm"], item["repetition"])
        if not metadata_path.is_file():
            if metadata_path.parent.exists():
                raise RuntimeError(
                    f"run slot exists without frozen metadata: {key}; stop"
                )
            if next_pending is None:
                next_pending = key
            continue
        if next_pending is not None:
            raise RuntimeError(
                f"future completed slot {key} exists after missing {next_pending}; stop"
            )
        metadata = _validate_preserved_artifact(
            metadata_path.parent, item, locked, lock_sha256, archived=False
        )
        delivery = metadata.get("injection_delivery")
        if delivery.get("stop_campaign"):
            raise RuntimeError(
                f"campaign is stopped by preserved slot {key}; no later run is permitted"
            )

    schedule_keys = [
        _slot_key(item["task_id"], item["arm"], item["repetition"])
        for item in _schedule()
    ]
    next_index = len(schedule_keys) if next_pending is None else schedule_keys.index(next_pending)
    for invalid_key, metadata_path in rerunnable_invalidations:
        invalid_index = schedule_keys.index(invalid_key)
        completed_path = _slot_metadata(root, _schedule()[invalid_index])
        if invalid_index > next_index or (
            invalid_index < next_index and not completed_path.is_file()
        ):
            raise RuntimeError(
                f"future archived invalidation violates schedule order: {metadata_path}; stop"
            )

    requested_path = (
        root / EVALUATION / "runs" / requested / "metadata.json"
    )
    if requested_path.is_file():
        return  # idempotent inspection; shared runner will not launch a model
    if next_pending != requested:
        raise RuntimeError(
            f"frozen schedule requires {next_pending!r} next, not {requested!r}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-lock", action="store_true")
    parser.add_argument("--verify-lock", action="store_true")
    parser.add_argument("--verify-ready", action="store_true")
    parser.add_argument("--show-order", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--task", choices=[task["id"] for task in shared.TASKS])
    parser.add_argument("--arm", choices=shared.ARMS)
    parser.add_argument("--repetition", type=int, choices=(1, 2, 3))
    args = parser.parse_args(argv)

    if args.render_lock:
        print(_json_text(render_execution_lock()), end="")
        return 0
    if args.verify_lock:
        verify_execution_lock(require_review=False)
        print(f"PASS execution lock {_path_sha256(EXECUTION_LOCK)}")
        return 0
    if args.verify_ready:
        verify_execution_lock(require_review=True)
        print(f"PASS ready/not-started {_path_sha256(EXECUTION_LOCK)}")
        return 0
    if args.show_order:
        for index, item in enumerate(_schedule(), start=1):
            print(
                f"{index:02d} {item['evaluation']} {item['task_id']} "
                f"{item['arm']} r{item['repetition']}"
            )
        return 0
    if not args.execute:
        parser.error(
            "external trials require explicit --execute after lock and review verification"
        )

    verify_execution_lock(require_review=True)
    try:
        selected = _selected_slots(args)
    except ValueError as exc:
        parser.error(str(exc))
    for index, (task, arm, repetition) in enumerate(selected, start=1):
        _assert_slot_order(task, arm, repetition)
        label = f"{task['id']} {arm} r{repetition}"
        print(f"[{index}/{len(selected)}] START {label}", flush=True)
        result = run_slot(task, arm, repetition)
        print(
            f"[{index}/{len(selected)}] END {label} "
            f"invalid={result.get('technical_invalid')} "
            f"delivery={result.get('injection_delivery', {}).get('delivery_pass')} "
            f"attempt={result.get('first_attempt_captured')}",
            flush=True,
        )
        delivery = result.get("injection_delivery", {})
        if (
            result.get("technical_invalid")
            or not result.get("isolation_pass", True)
            or delivery.get("stop_campaign")
        ):
            print(
                "Campaign stopped. Preserve the slot and inspect its evidence "
                "before any further external run.",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Pure capture helpers for the locked pre-generation guidance live eval.

This module does not call a model.  It turns Claude Code stream events into
auditable first-attempt, isolation, and blinded-review artifacts.
"""

from __future__ import annotations

import copy
import difflib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


MUTATING_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})
DISCOVERY_TOOLS = frozenset({"Read", "Glob", "Grep"})
POLICY_MARKERS = re.compile(
    r"(?i)(?:^|[\\/])\.mneme(?:[\\/]|$)|project_memory\.json|(?:^|[\\/])adr(?:s)?(?:[\\/]|$)"
)
INJECTED_DECISION = re.compile(r"DECISION \[([^\]]+)\]")


class CaptureError(ValueError):
    """Raised when a proposed tool call cannot be captured safely."""


def parse_events(raw: str) -> list[dict[str, Any]]:
    """Parse newline-delimited Claude stream events, ignoring non-JSON noise."""
    events: list[dict[str, Any]] = []
    for line in raw.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def tool_blocks(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Return tool-use blocks from one assistant event in message order."""
    if event.get("type") != "assistant":
        return []
    content = event.get("message", {}).get("content", [])
    if not isinstance(content, list):
        return []
    return [
        block for block in content
        if isinstance(block, dict) and block.get("type") == "tool_use"
    ]


def _workspace_relative(file_path: str, workspace: Path) -> str:
    if not file_path:
        raise CaptureError("mutating tool call has no file_path")
    root = workspace.resolve()
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError as exc:
        raise CaptureError(f"tool path escapes workspace: {file_path}") from exc


def _apply_edit(current: str, spec: dict[str, Any]) -> str:
    old = spec.get("old_string", "")
    new = spec.get("new_string", "")
    if not isinstance(old, str) or not isinstance(new, str):
        raise CaptureError("Edit strings must be text")
    if old not in current:
        raise CaptureError("Edit old_string is absent from pristine proposal state")
    count = -1 if spec.get("replace_all") else 1
    return current.replace(old, new, count)


def apply_tool_call(
    snapshot: dict[str, str],
    block: dict[str, Any],
    workspace: Path,
) -> None:
    """Apply one proposed mutating tool call to an in-memory snapshot."""
    name = block.get("name")
    if name not in MUTATING_TOOLS:
        raise CaptureError(f"unsupported proposal tool: {name}")
    spec = block.get("input") or {}
    if not isinstance(spec, dict):
        raise CaptureError("tool input must be an object")
    relative = _workspace_relative(str(spec.get("file_path", "")), workspace)
    current = snapshot.get(relative, "")

    if name == "Write":
        content = spec.get("content", "")
        if not isinstance(content, str):
            raise CaptureError("Write content must be text")
        snapshot[relative] = content
        return
    if relative not in snapshot:
        raise CaptureError(f"{name} target is absent from pristine snapshot: {relative}")
    if name == "Edit":
        snapshot[relative] = _apply_edit(current, spec)
        return

    for index, edit in enumerate(spec.get("edits", [])):
        if not isinstance(edit, dict):
            raise CaptureError(f"MultiEdit item {index} must be an object")
        try:
            current = _apply_edit(current, edit)
        except CaptureError as exc:
            raise CaptureError(f"MultiEdit item {index}: {exc}") from exc
    snapshot[relative] = current


def diff_snapshots(before: dict[str, str], after: dict[str, str]) -> str:
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


def _scrub(value: Any, workspace: Path) -> Any:
    """Remove disposable absolute paths while preserving proposal semantics."""
    if isinstance(value, dict):
        return {key: _scrub(item, workspace) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item, workspace) for item in value]
    if not isinstance(value, str):
        return value
    root = str(workspace.resolve())
    normalized = value.replace(root, "$WORKSPACE")
    normalized = normalized.replace(root.replace("\\", "/"), "$WORKSPACE")
    return normalized


def capture_attempts(
    events: list[dict[str, Any]],
    pristine: dict[str, str],
    workspace: Path,
) -> dict[str, Any]:
    """Capture every attempt and materialize the first pre-feedback proposal."""
    attempts: list[dict[str, Any]] = []
    first_index: int | None = None
    first_blocks: list[dict[str, Any]] = []

    for event_index, event in enumerate(events):
        mutating = [block for block in tool_blocks(event) if block.get("name") in MUTATING_TOOLS]
        if not mutating:
            continue
        if first_index is None:
            first_index = event_index
            first_blocks = mutating
        attempts.append({
            "ordinal": len(attempts) + 1,
            "event_index": event_index,
            "message_id": event.get("message", {}).get("id"),
            "timestamp": event.get("timestamp"),
            "tool_calls": [_scrub(block, workspace) for block in mutating],
        })

    before_count = 0
    through_count = 0
    discovery_before: list[dict[str, Any]] = []
    if first_index is not None:
        for event_index, event in enumerate(events[: first_index + 1]):
            blocks = tool_blocks(event)
            if event_index < first_index:
                before_count += len(blocks)
            through_count += len(blocks)
            if event_index < first_index:
                for block in blocks:
                    if block.get("name") in DISCOVERY_TOOLS:
                        discovery_before.append(_scrub(block, workspace))

    first_snapshot: dict[str, str] | None = None
    first_diff = ""
    first_error: str | None = None
    if first_blocks:
        first_snapshot = copy.deepcopy(pristine)
        try:
            for block in first_blocks:
                apply_tool_call(first_snapshot, block, workspace)
            first_diff = diff_snapshots(pristine, first_snapshot)
        except CaptureError as exc:
            first_error = str(exc)
            first_snapshot = None

    return {
        "attempts": attempts,
        "first_attempt_event_index": first_index,
        "first_attempt_tool_calls": (
            [_scrub(block, workspace) for block in first_blocks]
            if first_blocks else []
        ),
        "first_attempt_snapshot": first_snapshot,
        "first_attempt_diff": first_diff,
        "first_attempt_capture_error": first_error,
        "tool_calls_before_first_attempt": before_count,
        "tool_calls_through_first_attempt": through_count,
        "discovery_calls_before_first_attempt": discovery_before,
        "policy_discovery_before_first_attempt": [
            block for block in discovery_before
            if POLICY_MARKERS.search(json.dumps(block, sort_keys=True))
        ],
    }


def injected_decision_ids(events: Iterable[dict[str, Any]]) -> list[str]:
    raw = "\n".join(json.dumps(event, sort_keys=True) for event in events)
    return sorted(set(INJECTED_DECISION.findall(raw)))


def hook_events(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        event for event in events
        if event.get("type") == "system"
        and event.get("subtype") in {"hook_started", "hook_response"}
    ]


def _path_from_tool(block: dict[str, Any]) -> str | None:
    spec = block.get("input") or {}
    if not isinstance(spec, dict):
        return None
    if block.get("name") in {"Read", "Edit", "Write", "MultiEdit"}:
        value = spec.get("file_path")
    else:
        value = spec.get("path")
    return value if isinstance(value, str) and value else None


def external_tool_accesses(
    events: Iterable[dict[str, Any]], workspace: Path,
) -> list[dict[str, Any]]:
    """Find model-issued filesystem calls that resolve outside the workspace."""
    root = workspace.resolve()
    violations: list[dict[str, Any]] = []
    for event in events:
        for block in tool_blocks(event):
            if block.get("name") not in MUTATING_TOOLS | DISCOVERY_TOOLS:
                continue
            raw_path = _path_from_tool(block)
            if raw_path is None:
                continue
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = root / candidate
            candidate = candidate.resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                violations.append(_scrub(block, workspace))
    return violations


def mechanism_isolation_violations(
    events: list[dict[str, Any]],
    workspace: Path,
    arm: str,
    governed: bool,
) -> list[str]:
    violations: list[str] = []
    external = external_tool_accesses(events, workspace)
    if external:
        violations.append(f"{len(external)} model filesystem call(s) escaped the workspace")
    decisions = injected_decision_ids(events)
    if arm == "baseline" and decisions:
        violations.append("baseline received prompt-time decision context")
    if not governed and decisions:
        violations.append("control prompt received policy context")
    return violations


def build_blinded_artifact(
    *,
    blind_id: str,
    task: dict[str, Any],
    capture: dict[str, Any],
) -> dict[str, Any]:
    """Build the reviewer package without arm or hook/result metadata."""
    return {
        "schema": "mneme.guidance-confirmatory-blinded/v1",
        "blind_id": blind_id,
        "task_id": task["id"],
        "prompt": task["prompt"],
        "target": task["target"],
        "governed": task["governed"],
        "expected_condition": task["expected_condition"],
        "first_attempt_tool_calls": capture["first_attempt_tool_calls"],
        "first_attempt_diff": capture["first_attempt_diff"],
        "first_attempt_capture_error": capture["first_attempt_capture_error"],
        "review_fields": {
            "first_attempt_compliance": None,
            "violated_decision_id": None,
            "functional_completion": None,
            "unnecessary_architectural_scope_expansion": None,
            "scope_expansion_evidence": None,
            "reviewer_notes": None,
        },
    }


def introduced_text(before: str, after: str) -> str:
    """Return lines introduced by a materialized proposal for offline checks."""
    matcher = difflib.SequenceMatcher(
        a=before.splitlines(), b=after.splitlines(), autojunk=False,
    )
    lines: list[str] = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in {"insert", "replace"}:
            lines.extend(after.splitlines()[j1:j2])
    return "\n".join(lines)


def elapsed_to_first_attempt(
    events: list[dict[str, Any]], first_index: int | None,
) -> float | None:
    """Use stream timestamps when Claude supplies both prompt and attempt time."""
    if first_index is None:
        return None
    first_time: datetime | None = None
    for event in events:
        value = event.get("timestamp")
        if not isinstance(value, str):
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        first_time = parsed
        break
    attempt_value = events[first_index].get("timestamp")
    if first_time is None or not isinstance(attempt_value, str):
        return None
    try:
        attempt_time = datetime.fromisoformat(attempt_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((attempt_time - first_time).total_seconds(), 3)

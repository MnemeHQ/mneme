"""OpenCode S1 pre-mutation bridge.

This module is transport plus decision mapping. It does not implement a matcher,
resolver, diff, policy engine or verdict schema. It reuses the canonical checker
through the shared Claude Code adapter internals, P2-first memory selection and
the shared verdict-trust function.

The bridge never mutates the target. It reads only metadata (`lstat`), invokes
`mneme check` on a temporary carrier, and returns a JSON decision to the host
plugin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from mneme import __version__
from mneme.integrations.claude_code.availability import classify_observation
from mneme.integrations.claude_code.hook import (
    ToolEvent,
    _direct_write_memory_start,
    _invoke_check,
    assess_verdict,
    resolve_mode,
)
from mneme.integrations.memory_selection import MemorySelection, resolve_memory
from mneme.memory_store import MemoryStore
from mneme.rule_identity import rule_id_for

BRIDGE_SCHEMA = "mneme.opencode.bridge/v1"
DECISION_SCHEMA = "mneme.opencode.decision/v1"
EVIDENCE_SCHEMA = "mneme.opencode.evidence/v1"
BRIDGE_VERSION = "0.1.0"

TOOL = "write"
TARGET_SUFFIX = ".py"

ALLOW = "allow"
BLOCK = "block"
UNEVALUATED = "unevaluated"
SKIP = "skip"
UNSUPPORTED = "unsupported"
SETUP_INVALID = "setup_invalid"

EXECUTION_OBSERVED = "execution_observed"
NO_CLAIM = "none"

AUTHORITY_FIELDS = (
    "decision_id",
    "decision_version_id",
    "rule_id",
    "rule_value",
    "rule_scope",
)


class BridgeConfigError(RuntimeError):
    """A configuration condition reported as setup_invalid."""


class EvaluationError(RuntimeError):
    """An operational condition reported as unevaluated."""


class UnsupportedError(RuntimeError):
    """A condition outside the S1 surface reported as unsupported."""


@dataclass(frozen=True)
class Authority:
    decision_id: str
    decision_version_id: str
    rule_id: str
    rule_value: str
    rule_scope: str


@dataclass(frozen=True)
class Request:
    tool: str
    path: str
    content: Optional[str]
    session_directory: Optional[str]
    session_id: str
    call_id: str
    agent: str
    message_id: str
    event_id: str
    host_version: str


@dataclass(frozen=True)
class Outcome:
    decision: str
    reason: str
    claim: str
    observation_state: Optional[str] = None
    applicability: Optional[str] = None
    target: Optional[str] = None
    memory: Optional[str] = None
    selection_reason: Optional[str] = None
    selection_walk: Optional[str] = None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def load_authority(path: Optional[str]) -> Authority:
    if not path:
        raise BridgeConfigError("authority_path_missing")
    authority_path = Path(path)
    if not authority_path.is_file():
        raise BridgeConfigError("authority_file_missing")
    try:
        data = json.loads(authority_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BridgeConfigError(f"authority_unreadable_{type(exc).__name__}") from exc
    if not isinstance(data, dict):
        raise BridgeConfigError("authority_not_object")
    missing = [
        key
        for key in AUTHORITY_FIELDS
        if not isinstance(data.get(key), str) or not data[key]
    ]
    if missing:
        raise BridgeConfigError(f"authority_missing_fields_{','.join(missing)}")
    return Authority(
        decision_id=data["decision_id"],
        decision_version_id=data["decision_version_id"],
        rule_id=data["rule_id"],
        rule_value=data["rule_value"],
        rule_scope=data["rule_scope"],
    )


def parse_request(payload: Any) -> Request:
    if not isinstance(payload, dict):
        raise EvaluationError("request_not_object")
    tool = payload.get("tool")
    if not isinstance(tool, str) or not tool:
        raise EvaluationError("tool_missing")
    raw_input = payload.get("input")
    if not isinstance(raw_input, dict):
        raise EvaluationError("input_missing")
    path = raw_input.get("path")
    if not isinstance(path, str) or not path:
        raise EvaluationError("path_missing")
    content = raw_input.get("content")
    if content is not None and not isinstance(content, str):
        raise EvaluationError("content_not_string")
    session_directory = payload.get("sessionDirectory")
    if session_directory is not None and not isinstance(session_directory, str):
        raise EvaluationError("session_directory_not_string")
    return Request(
        tool=tool,
        path=path,
        content=content,
        session_directory=session_directory,
        session_id=_text(payload.get("sessionID")),
        call_id=_text(payload.get("callID")),
        agent=_text(payload.get("agent")),
        message_id=_text(payload.get("messageID")),
        event_id=_text(payload.get("eventID")),
        host_version=_text(payload.get("hostVersion")),
    )


def _normcase(value: Path) -> str:
    return os.path.normcase(str(value))


def _is_within(child: Path, root: Path) -> bool:
    try:
        return os.path.commonpath([_normcase(child), _normcase(root)]) == _normcase(root)
    except ValueError:
        return False


def resolve_target(request: Request) -> Path:
    """Resolve the host target and enforce the verified-new-file `.py` contract."""
    if not request.session_directory:
        raise EvaluationError("session_directory_unavailable")
    root = Path(request.session_directory)
    if not root.is_absolute():
        raise EvaluationError("session_directory_not_absolute")
    root = root.resolve(strict=False)
    candidate = Path(request.path)
    if not candidate.is_absolute():
        candidate = root / candidate
    lexical = Path(os.path.abspath(str(candidate)))
    if os.path.lexists(str(lexical)):
        raise UnsupportedError("existing_target")
    try:
        lexical_relative = Path(os.path.relpath(str(lexical), str(root)))
    except ValueError:
        lexical_relative = None
    if lexical_relative is not None and ".." not in lexical_relative.parts:
        current = root
        for part in lexical_relative.parts:
            if part in ("", "."):
                continue
            current = current / part
            if current.is_symlink():
                raise UnsupportedError("symlink_target")
    resolved = lexical.resolve(strict=False)
    if not _is_within(resolved, root):
        raise EvaluationError("target_outside_session_directory")
    if resolved.suffix != TARGET_SUFFIX:
        raise UnsupportedError("non_python_target")
    if not resolved.parent.is_dir():
        raise UnsupportedError("target_parent_missing")
    return resolved


def _match_authority(memory: Path, authority: Authority) -> None:
    store = MemoryStore(memory)
    store.load()
    decisions = [d for d in store.decisions() if d.id == authority.decision_id]
    if len(decisions) != 1:
        raise BridgeConfigError("authority_decision_missing_or_ambiguous")
    decision = decisions[0]
    if getattr(decision, "version_id", "") != authority.decision_version_id:
        raise BridgeConfigError("authority_version_mismatch")
    rules = [
        rule
        for rule in decision.rules
        if rule_id_for(decision.id, rule) == authority.rule_id
    ]
    if len(rules) != 1:
        raise BridgeConfigError("authority_rule_missing_or_ambiguous")
    rule = rules[0]
    if rule.value != authority.rule_value:
        raise BridgeConfigError("authority_rule_value_mismatch")
    if tuple(rule.include_paths or ()) != (authority.rule_scope,):
        raise BridgeConfigError("authority_rule_scope_mismatch")


def _memory_schema(memory: Optional[Path]) -> Optional[str]:
    if memory is None:
        return None
    try:
        data = json.loads(memory.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    index = data.get("decision_index")
    if isinstance(index, dict) and isinstance(index.get("schema"), str):
        return index["schema"]
    return None


def _evidence(
    request: Request,
    authority: Optional[Authority],
    outcome: Outcome,
    mode: str,
    mode_source: str,
    claude_env_present: bool,
) -> dict:
    memory = Path(outcome.memory) if outcome.memory else None
    return {
        "schema": EVIDENCE_SCHEMA,
        "bridge": {"version": BRIDGE_VERSION},
        "mneme": {
            "version": __version__,
            "source": os.environ.get("MNEME_SOURCE_COMMIT"),
        },
        "host": {"version": request.host_version or None},
        "plugin": {"id": "mneme.opencode.s1"},
        "event": {
            "sessionID": request.session_id or None,
            "callID": request.call_id or None,
            "agent": request.agent or None,
            "messageID": request.message_id or None,
            "eventID": request.event_id or None,
        },
        "target": outcome.target,
        "content_sha256": _sha256(request.content) if request.content is not None else None,
        "memory": {
            "path": outcome.memory,
            "schema": _memory_schema(memory),
            "selection_reason": outcome.selection_reason,
            "selection_walk": outcome.selection_walk,
        },
        "authority": {
            "decision_id": authority.decision_id if authority else None,
            "decision_version_id": authority.decision_version_id if authority else None,
            "rule_id": authority.rule_id if authority else None,
        },
        "mode": {"value": mode, "source": mode_source, "claude_env_present": claude_env_present},
        "observation_state": outcome.observation_state,
        "applicability": outcome.applicability,
        "decision": outcome.decision,
        "reason": outcome.reason,
        "claim": outcome.claim,
    }


def evaluate(request: Request, authority: Authority) -> Outcome:
    """Return a decision for one host event. Never writes the target."""
    target: Optional[Path] = None
    memory: Optional[Path] = None
    selection: Optional[MemorySelection] = None
    claude_env_present = "CLAUDE_PLUGIN_OPTION_MODE" in os.environ
    os.environ.pop("CLAUDE_PLUGIN_OPTION_MODE", None)
    mode = resolve_mode()
    mode_source = "MNEME_HOOK_MODE" if "MNEME_HOOK_MODE" in os.environ else "default"

    def finish(
        decision: str,
        reason: str,
        claim: str,
        *,
        observation_state: Optional[str] = None,
        applicability: Optional[str] = None,
    ) -> Outcome:
        return Outcome(
            decision=decision,
            reason=reason,
            claim=claim,
            observation_state=observation_state,
            applicability=applicability,
            target=str(target) if target else None,
            memory=str(memory) if memory else None,
            selection_reason=selection.reason if selection else None,
            selection_walk=selection.walk if selection else None,
        )

    if request.tool != TOOL:
        return finish(UNSUPPORTED, "unsupported_tool", NO_CLAIM)
    if request.content is None:
        return finish(UNSUPPORTED, "non_complete_content", NO_CLAIM)
    if not request.content.strip():
        return finish(SKIP, "empty_content", NO_CLAIM)

    try:
        target = resolve_target(request)
    except UnsupportedError as exc:
        return finish(UNSUPPORTED, str(exc), NO_CLAIM)
    except EvaluationError as exc:
        return finish(UNEVALUATED, str(exc), NO_CLAIM)

    event = ToolEvent(
        tool_name=TOOL,
        file_path=str(target),
        cwd=request.session_directory or "",
        tool_input={"file_path": str(target), "content": request.content},
    )
    try:
        selection = resolve_memory(_direct_write_memory_start(event))
    except (OSError, RuntimeError) as exc:
        return finish(UNEVALUATED, f"memory_selection_error_{type(exc).__name__}", NO_CLAIM)
    memory = selection.path
    if memory is None:
        return finish(SKIP, "no_memory", NO_CLAIM)

    try:
        _match_authority(memory, authority)
    except BridgeConfigError as exc:
        return finish(SETUP_INVALID, str(exc), NO_CLAIM)

    root = Path(request.session_directory or "").resolve(strict=False)
    try:
        relative = target.relative_to(root)
    except ValueError:
        relative = Path(target.name)
    proc = _invoke_check(
        memory,
        relative.as_posix(),
        str(target),
        request.content,
        stderr=sys.stderr,
    )
    if proc is None:
        return finish(UNEVALUATED, "checker_not_run", NO_CLAIM)

    assessment = assess_verdict(proc.stdout, proc.returncode, mode)
    payload = assessment.payload
    if payload is None:
        return finish(UNEVALUATED, assessment.problem or "untrusted_check", NO_CLAIM)
    state = classify_observation(payload)
    if state != "TRUSTED_COMPLETE":
        return finish(
            UNEVALUATED,
            f"evaluation_{state.lower()}",
            NO_CLAIM,
            observation_state=state,
        )

    applicability = payload.get("applicability") or []
    entry = next(
        (item for item in applicability if item.get("rule_id") == authority.rule_id),
        None,
    )
    if entry is None:
        return finish(
            UNEVALUATED, "rule_not_evaluated", NO_CLAIM, observation_state=state
        )
    if entry.get("decision_version_id") != authority.decision_version_id:
        return finish(
            SETUP_INVALID,
            "authority_version_mismatch",
            NO_CLAIM,
            observation_state=state,
        )
    outcome = entry.get("outcome")
    if outcome not in ("APPLIED", "EXCLUDED"):
        return finish(
            UNEVALUATED,
            f"applicability_{str(outcome).lower()}",
            NO_CLAIM,
            observation_state=state,
        )

    verdict = payload.get("verdict")
    if verdict == "FAIL" and outcome == "APPLIED":
        if mode == "strict":
            return finish(
                BLOCK,
                "literal_violation",
                EXECUTION_OBSERVED,
                observation_state=state,
                applicability=outcome,
            )
        return finish(
            ALLOW,
            "warn_mode_violation",
            EXECUTION_OBSERVED,
            observation_state=state,
            applicability=outcome,
        )
    if verdict == "PASS":
        return finish(
            ALLOW,
            "no_violation",
            EXECUTION_OBSERVED,
            observation_state=state,
            applicability=outcome,
        )
    return finish(
        UNEVALUATED,
        f"unexpected_verdict_{verdict}",
        NO_CLAIM,
        observation_state=state,
        applicability=outcome,
    )


def _write_evidence(record: dict) -> None:
    path = os.environ.get("MNEME_OPENCODE_EVIDENCE_LOG")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError:
        # Diagnostics must never change enforcement.
        pass


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="OpenCode S1 pre-mutation bridge")
    parser.add_argument("--authority", default=None, help="trusted authority pin JSON")
    args = parser.parse_args(argv)

    raw = sys.stdin.buffer.read()
    try:
        request = parse_request(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, EvaluationError) as exc:
        reason = str(exc) or type(exc).__name__
        outcome = Outcome(UNEVALUATED, f"invalid_request_{reason}", NO_CLAIM)
        print(json.dumps({"schema": DECISION_SCHEMA, **outcome.__dict__}, sort_keys=True))
        return 0

    try:
        authority = load_authority(args.authority)
    except BridgeConfigError as exc:
        outcome = Outcome(SETUP_INVALID, str(exc), NO_CLAIM)
        print(json.dumps({"schema": DECISION_SCHEMA, **outcome.__dict__}, sort_keys=True))
        return 0

    claude_env_present = "CLAUDE_PLUGIN_OPTION_MODE" in os.environ
    os.environ.pop("CLAUDE_PLUGIN_OPTION_MODE", None)
    mode = resolve_mode()
    mode_source = "MNEME_HOOK_MODE" if "MNEME_HOOK_MODE" in os.environ else "default"

    try:
        outcome = evaluate(request, authority)
    except Exception as exc:  # noqa: BLE001 - bridge errors never authorize
        outcome = Outcome(UNEVALUATED, f"bridge_error_{type(exc).__name__}", NO_CLAIM)

    evidence = _evidence(request, authority, outcome, mode, mode_source, claude_env_present)
    _write_evidence(evidence)
    record = {
        "schema": DECISION_SCHEMA,
        "decision": outcome.decision,
        "reason": outcome.reason,
        "claim": outcome.claim,
        "evidence": evidence,
    }
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

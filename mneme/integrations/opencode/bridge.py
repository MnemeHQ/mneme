"""OpenCode pre-mutation bridge (S1 write, E1 edit).

This module is transport plus decision mapping. It does not implement a matcher,
resolver, diff, policy engine or verdict schema. It reuses the canonical checker
through the shared Claude Code adapter internals, P2-first memory selection and
the shared verdict-trust function.

The bridge never mutates the target. For `write` it proves absence with `lstat`;
for `edit` it reads the existing target to materialise the change and evaluates
the introduced delta (ADR-018). It invokes `mneme check` on a temporary carrier
and returns a JSON decision to the host plugin.
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
    MaterializeError,
    ToolEvent,
    _direct_write_memory_start,
    _invoke_check,
    assess_verdict,
    introduced_between,
    materialize_proposed_content,
    resolve_mode,
)
from mneme.integrations.memory_selection import MemorySelection, resolve_memory
from mneme.memory_store import MemoryStore
from mneme.path_selectors import policy_root
from mneme.rule_identity import rule_id_for

BRIDGE_SCHEMA = "mneme.opencode.bridge/v1"
DECISION_SCHEMA = "mneme.opencode.decision/v1"
EVIDENCE_SCHEMA = "mneme.opencode.evidence/v1"
BRIDGE_VERSION = "0.1.0"

TOOL = "write"
TOOL_EDIT = "edit"
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
    old_string: Optional[str] = None
    new_string: Optional[str] = None
    replace_all: bool = False


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
    applicability_records: tuple[dict, ...] = ()
    violations: tuple[dict, ...] = ()
    violated_rule_ids: tuple[str, ...] = ()
    evaluated_sha256: Optional[str] = None
    materialisation: Optional[dict] = None


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
    schema = payload.get("schema")
    if schema is None:
        raise EvaluationError("schema_missing")
    if schema != BRIDGE_SCHEMA:
        raise EvaluationError("schema_mismatch")
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
    old_string = raw_input.get("oldString")
    if old_string is not None and not isinstance(old_string, str):
        raise EvaluationError("old_string_not_string")
    new_string = raw_input.get("newString")
    if new_string is not None and not isinstance(new_string, str):
        raise EvaluationError("new_string_not_string")
    replace_all = raw_input.get("replaceAll", raw_input.get("replace_all", False))
    if not isinstance(replace_all, bool):
        raise EvaluationError("replace_all_not_boolean")
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
        old_string=old_string,
        new_string=new_string,
        replace_all=replace_all,
    )


def _normcase(value: Path) -> str:
    return os.path.normcase(str(value))


def _is_within(child: Path, root: Path) -> bool:
    try:
        return os.path.commonpath([_normcase(child), _normcase(root)]) == _normcase(root)
    except ValueError:
        return False


def _reject_symlink_target(lexical: Path, root: Optional[Path]) -> None:
    """Reject a symlink anywhere from the trusted base to the target.

    Within the session root the walk starts at that root, preserving the
    verified-new-file contract. An absolute target outside the root is
    target-anchored, so its whole lexical chain is checked instead.
    """
    parts: tuple[str, ...]
    base: Path
    if root is not None:
        try:
            relative = Path(os.path.relpath(str(lexical), str(root)))
        except ValueError:
            relative = None
        if relative is not None and ".." not in relative.parts:
            base = root
            parts = relative.parts
        else:
            base = Path(lexical.anchor)
            parts = lexical.parts[1:]
    else:
        base = Path(lexical.anchor)
        parts = lexical.parts[1:]

    current = base
    for part in parts:
        if part in ("", "."):
            continue
        current = current / part
        if current.is_symlink():
            raise UnsupportedError("symlink_target")


def resolve_target(request: Request) -> Path:
    """Resolve the host target and enforce the verified-new-file `.py` contract.

    A relative target is resolved against the session directory and may not
    traverse outside it. An absolute target may resolve outside the session
    directory: governance is then anchored to the memory that governs the
    target path, and the selected memory's policy root must contain it.
    """
    if not request.session_directory:
        raise EvaluationError("session_directory_unavailable")
    root = Path(request.session_directory)
    if not root.is_absolute():
        raise EvaluationError("session_directory_not_absolute")
    root = root.resolve(strict=False)
    candidate = Path(request.path)
    absolute_input = candidate.is_absolute()
    if not absolute_input:
        candidate = root / candidate
    lexical = Path(os.path.abspath(str(candidate)))
    if os.path.lexists(str(lexical)):
        raise UnsupportedError("existing_target")

    inside_root = _is_within(lexical, root)
    _reject_symlink_target(lexical, root if inside_root else None)

    resolved = lexical.resolve(strict=False)
    if not absolute_input and not _is_within(resolved, root):
        raise EvaluationError("target_outside_session_directory")
    if resolved.suffix != TARGET_SUFFIX:
        raise UnsupportedError("non_python_target")
    if not resolved.parent.is_dir():
        raise UnsupportedError("target_parent_missing")
    return resolved


def resolve_existing_target(request: Request) -> Path:
    """Resolve an existing `.py` target for the E1 edit surface.

    A relative target is resolved against the session directory and may not
    traverse outside it. An absolute target may resolve outside the session
    directory; the selected memory's policy root must then contain it.
    """
    if not request.session_directory:
        raise EvaluationError("session_directory_unavailable")
    root = Path(request.session_directory)
    if not root.is_absolute():
        raise EvaluationError("session_directory_not_absolute")
    root = root.resolve(strict=False)
    candidate = Path(request.path)
    absolute_input = candidate.is_absolute()
    if not absolute_input:
        candidate = root / candidate
    lexical = Path(os.path.abspath(str(candidate)))
    if not os.path.lexists(str(lexical)):
        raise UnsupportedError("target_missing")

    inside_root = _is_within(lexical, root)
    _reject_symlink_target(lexical, root if inside_root else None)

    resolved = lexical.resolve(strict=False)
    if not absolute_input and not _is_within(resolved, root):
        raise EvaluationError("target_outside_session_directory")
    if resolved.suffix != TARGET_SUFFIX:
        raise UnsupportedError("non_python_target")
    if not resolved.is_file():
        raise UnsupportedError("target_not_a_file")
    return resolved


def _prepare_edit(request: Request, target: Path, materialisation: dict) -> str:
    """Materialise the edit and return the introduced delta.

    Records hashes and counts into ``materialisation`` before any failure so a
    rejected edit still carries its observation.
    """
    old = request.old_string
    new = request.new_string
    if old is None or new is None:
        raise EvaluationError("non_complete_edit")
    if old == "":
        raise EvaluationError("empty_old_string")

    try:
        current = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise EvaluationError("unreadable_target") from exc

    occurrences = current.count(old)
    materialisation.update(
        {
            "current_sha256": _sha256(current),
            "occurrences": occurrences,
            "replacement_count": -1 if request.replace_all else 1,
            "ambiguous": occurrences > 1 and not request.replace_all,
        }
    )
    if occurrences == 0:
        raise EvaluationError("old_string_not_found")
    if occurrences > 1 and not request.replace_all:
        # Mirror the host: multiple matches without replaceAll are refused.
        raise EvaluationError("ambiguous_old_string")

    event = ToolEvent(
        tool_name="Edit",
        file_path=str(target),
        cwd=request.session_directory or "",
        tool_input={
            "file_path": str(target),
            "old_string": old,
            "new_string": new,
            "replace_all": request.replace_all,
        },
    )
    try:
        proposed = materialize_proposed_content(event)
    except MaterializeError as exc:
        raise EvaluationError("materialize_failed") from exc

    introduced = introduced_between(current, proposed)
    materialisation["proposed_sha256"] = _sha256(proposed)
    materialisation["evaluated_sha256"] = _sha256(introduced)
    return introduced


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


IDENTITY_FIELDS = (
    ("tool", "tool"),
    ("sessionID", "session_id"),
    ("callID", "call_id"),
    ("agent", "agent"),
    ("messageID", "message_id"),
    ("eventID", "event_id"),
)


def _identity_missing(request: Request) -> list[str]:
    """Names of the six raw host identifiers that are absent for this event."""
    return [
        name
        for name, attribute in IDENTITY_FIELDS
        if not getattr(request, attribute)
    ]


def _evidence(
    request: Request,
    authority: Optional[Authority],
    outcome: Outcome,
    mode: str,
    mode_source: str,
    claude_env_present: bool,
) -> dict:
    memory = Path(outcome.memory) if outcome.memory else None
    missing = _identity_missing(request)
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
            "tool": request.tool or None,
            "sessionID": request.session_id or None,
            "callID": request.call_id or None,
            "agent": request.agent or None,
            "messageID": request.message_id or None,
            "eventID": request.event_id or None,
        },
        "identity": {"complete": not missing, "missing": missing},
        "target": outcome.target,
        "content_sha256": outcome.evaluated_sha256,
        "materialisation": outcome.materialisation,
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
            "outcome": outcome.applicability,
        },
        "mode": {"value": mode, "source": mode_source, "claude_env_present": claude_env_present},
        "observation_state": outcome.observation_state,
        "applicability": list(outcome.applicability_records),
        "violations": list(outcome.violations),
        "violated_rule_ids": list(outcome.violated_rule_ids),
        # Host prevention is a separate validator-owned witness. The bridge
        # never observes the host's refusal and never infers it from `block`.
        "host_witness": None,
        "decision": outcome.decision,
        "reason": outcome.reason,
        "claim": outcome.claim,
    }


def evaluate(request: Request, authority: Authority) -> Outcome:
    """Return a decision for one host event. Never writes the target."""
    target: Optional[Path] = None
    memory: Optional[Path] = None
    selection: Optional[MemorySelection] = None
    evaluated_sha: Optional[str] = None
    materialisation: Optional[dict] = None
    os.environ.pop("CLAUDE_PLUGIN_OPTION_MODE", None)
    mode = resolve_mode()

    def finish(
        decision: str,
        reason: str,
        claim: str,
        *,
        observation_state: Optional[str] = None,
        applicability: Optional[str] = None,
        applicability_records: tuple[dict, ...] = (),
        violations: tuple[dict, ...] = (),
        violated_rule_ids: tuple[str, ...] = (),
    ) -> Outcome:
        # The claim ceiling requires all six raw host identifiers. A decision
        # may still be enforced, but missing identity never yields evidence.
        effective_claim = claim if not _identity_missing(request) else NO_CLAIM
        return Outcome(
            decision=decision,
            reason=reason,
            claim=effective_claim,
            observation_state=observation_state,
            applicability=applicability,
            target=str(target) if target else None,
            memory=str(memory) if memory else None,
            selection_reason=selection.reason if selection else None,
            selection_walk=selection.walk if selection else None,
            applicability_records=applicability_records,
            violations=violations,
            violated_rule_ids=violated_rule_ids,
            evaluated_sha256=evaluated_sha,
            materialisation=materialisation,
        )

    if request.tool == TOOL:
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
        checked_content = request.content
        event = ToolEvent(
            tool_name=TOOL,
            file_path=str(target),
            cwd=request.session_directory or "",
            tool_input={"file_path": str(target), "content": request.content},
        )
    elif request.tool == TOOL_EDIT:
        try:
            target = resolve_existing_target(request)
        except UnsupportedError as exc:
            return finish(UNSUPPORTED, str(exc), NO_CLAIM)
        except EvaluationError as exc:
            return finish(UNEVALUATED, str(exc), NO_CLAIM)
        materialisation = {}
        try:
            checked_content = _prepare_edit(request, target, materialisation)
        except EvaluationError as exc:
            return finish(UNEVALUATED, str(exc), NO_CLAIM)
        event = ToolEvent(
            tool_name="Edit",
            file_path=str(target),
            cwd=request.session_directory or "",
            tool_input={
                "file_path": str(target),
                "old_string": request.old_string or "",
                "new_string": request.new_string or "",
                "replace_all": request.replace_all,
            },
        )
        if not checked_content.strip():
            return finish(SKIP, "empty_introduced_content", NO_CLAIM)
    else:
        return finish(UNSUPPORTED, "unsupported_tool", NO_CLAIM)

    evaluated_sha = _sha256(checked_content)
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

    memory_root = policy_root(memory)
    if not _is_within(target, memory_root):
        return finish(UNEVALUATED, "target_outside_policy_root", NO_CLAIM)
    relative = target.relative_to(memory_root)
    proc = _invoke_check(
        memory,
        relative.as_posix(),
        str(target),
        checked_content,
        stderr=sys.stderr,
    )
    if proc is None:
        return finish(UNEVALUATED, "checker_not_run", NO_CLAIM)

    assessment = assess_verdict(proc.stdout, proc.returncode, mode)
    payload = assessment.payload
    if payload is None:
        return finish(UNEVALUATED, assessment.problem or "untrusted_check", NO_CLAIM)
    state = classify_observation(payload)
    applicability = tuple(payload.get("applicability") or ())
    violations = tuple(payload.get("violations") or ())
    if state != "TRUSTED_COMPLETE":
        return finish(
            UNEVALUATED,
            f"evaluation_{state.lower()}",
            NO_CLAIM,
            observation_state=state,
            applicability_records=applicability,
            violations=violations,
        )

    entry = next(
        (item for item in applicability if item.get("rule_id") == authority.rule_id),
        None,
    )
    if entry is None:
        return finish(
            UNEVALUATED,
            "rule_not_evaluated",
            NO_CLAIM,
            observation_state=state,
            applicability_records=applicability,
            violations=violations,
        )
    if entry.get("decision_version_id") != authority.decision_version_id:
        return finish(
            SETUP_INVALID,
            "authority_version_mismatch",
            NO_CLAIM,
            observation_state=state,
            applicability_records=applicability,
            violations=violations,
        )
    outcome = entry.get("outcome")
    if outcome not in ("APPLIED", "EXCLUDED"):
        return finish(
            UNEVALUATED,
            f"applicability_{str(outcome).lower()}",
            NO_CLAIM,
            observation_state=state,
            applicability_records=applicability,
            violations=violations,
        )

    verdict = payload.get("verdict")
    if verdict == "PASS":
        return finish(
            ALLOW,
            "no_violation",
            EXECUTION_OBSERVED,
            observation_state=state,
            applicability=outcome,
            applicability_records=applicability,
            violations=violations,
        )
    if verdict == "FAIL":
        # Blocking is attributable only to a canonical FORBID_LITERAL typed-rule
        # violation linked to an APPLIED applicability trace with the same rule
        # and decision version. The authority pin is an expectation, not a rule
        # filter, so a secondary rule may still block.
        applied_literal = {
            (item.get("rule_id"), item.get("decision_version_id"))
            for item in applicability
            if isinstance(item, dict)
            and item.get("outcome") == "APPLIED"
            and isinstance(item.get("rule_id"), str)
            and item["rule_id"]
            and isinstance(item.get("decision_version_id"), str)
            and item["decision_version_id"]
        }
        canonical = tuple(
            item
            for item in violations
            if isinstance(item, dict)
            and item.get("rule_type") == "FORBID_LITERAL"
            and item.get("kind") == "typed_rule"
            and item.get("severity") == "FAIL"
            and isinstance(item.get("rule_id"), str)
            and item["rule_id"]
            and isinstance(item.get("decision_version_id"), str)
            and item["decision_version_id"]
            and (item["rule_id"], item["decision_version_id"])
            in applied_literal
        )
        violated_rule_ids = tuple(
            sorted({item["rule_id"] for item in canonical})
        )
        if not canonical:
            return finish(
                UNEVALUATED,
                "fail_without_canonical_literal_violation",
                NO_CLAIM,
                observation_state=state,
                applicability=outcome,
                applicability_records=applicability,
                violations=violations,
            )
        if mode == "strict":
            return finish(
                BLOCK,
                "literal_violation",
                EXECUTION_OBSERVED,
                observation_state=state,
                applicability=outcome,
                applicability_records=applicability,
                violations=violations,
                violated_rule_ids=violated_rule_ids,
            )
        return finish(
            ALLOW,
            "warn_mode_violation",
            EXECUTION_OBSERVED,
            observation_state=state,
            applicability=outcome,
            applicability_records=applicability,
            violations=violations,
            violated_rule_ids=violated_rule_ids,
        )
    return finish(
        UNEVALUATED,
        f"unexpected_verdict_{verdict}",
        NO_CLAIM,
        observation_state=state,
        applicability=outcome,
        applicability_records=applicability,
        violations=violations,
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


def _bare_decision(outcome: Outcome) -> dict:
    """The wire decision surface for transport/setup failures (empty evidence)."""
    return {
        "schema": DECISION_SCHEMA,
        "decision": outcome.decision,
        "reason": outcome.reason,
        "claim": outcome.claim,
        "evidence": {},
    }


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
        print(json.dumps(_bare_decision(outcome), sort_keys=True))
        return 0

    try:
        authority = load_authority(args.authority)
    except BridgeConfigError as exc:
        outcome = Outcome(SETUP_INVALID, str(exc), NO_CLAIM)
        print(json.dumps(_bare_decision(outcome), sort_keys=True))
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

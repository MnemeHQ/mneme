"""Claude Code hook shim — translates hook events into mneme check calls.

Surfaces (ADR-021):

- ``PreToolUse`` x ``Edit|Write|MultiEdit``: introduced-delta gate
  (ADR-017/018/019/020 semantics, unchanged).
- ``PreToolUse`` x ``Bash``: pre-execution gate for deterministically
  reconstructable shell mutations only (see shell_preflight).
- ``SessionStart``: per-session repository baseline capture (session_state).
- ``Stop``: post-mutation / pre-completion session-delta backstop.
"""
from __future__ import annotations

import difflib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, TextIO

from mneme.integrations.claude_code.availability import (
    LocalDeclaration,
    ProceedNote,
    classify_observation,
    discover_declaration,
    emit_availability,
    write_proceed_context,
)
from mneme.integrations.claude_code.session_state import (
    MAX_FILE_BYTES,
    capture_baseline,
    cleanup_stale,
    compute_session_delta,
    enumerate_repo_files,
    load_snapshot,
    save_snapshot,
    snapshot_path,
)
from mneme.integrations.claude_code.shell_preflight import (
    Classification,
    classify_command,
    reconstruct_heredoc_write,
)
from mneme.path_selectors import policy_root


@dataclass(frozen=True)
class ToolEvent:
    tool_name: str
    file_path: str
    cwd: str
    tool_input: Dict[str, Any]


def parse_event(raw: str) -> ToolEvent:
    payload = json.loads(raw)
    tool_input = payload.get("tool_input", {}) or {}
    return ToolEvent(
        tool_name=payload["tool_name"],
        file_path=tool_input.get("file_path", ""),
        cwd=payload.get("cwd", ""),
        tool_input=tool_input,
    )


_MUTATING_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})


def should_check(tool_name: str) -> bool:
    return tool_name in _MUTATING_TOOLS


class MaterializeError(Exception):
    """Raised when proposed content cannot be reconstructed (file missing,
    old_string not found, etc.). Caller should fail open."""


def _replace_count(spec: Dict[str, Any]) -> int:
    """Occurrence count for ``str.replace``, honouring Claude Code's ``replace_all``.

    ``-1`` replaces every occurrence; ``1`` replaces only the first. Mirroring
    the flag matters: if the hook materializes a single replacement while
    Claude Code is about to replace all of them, the checked content is not the
    content that will land on disk, and a violation introduced by the second or
    later occurrence goes unseen.
    """
    return -1 if spec.get("replace_all") else 1


def _read_current(file_path: str, *, missing_ok: bool) -> str:
    """Read one source snapshot, optionally treating unreadable as new."""
    if not file_path:
        if missing_ok:
            return ""
        raise MaterializeError("missing file_path")
    try:
        return Path(file_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        if missing_ok:
            # A Write can replace a missing, unreadable, or non-UTF-8 file.
            # Treating it as new checks the complete proposed content, which
            # is the conservative enforcement direction.
            return ""
        raise MaterializeError(f"cannot read {file_path}: {exc}") from exc


def _materialize_change(event: ToolEvent) -> tuple[str, str]:
    """Return ``(current, proposed)`` from a single current-file snapshot.

    The snapshot is read from the same resolved path ``mneme check`` receives
    as ``--target-path``: a relative ``file_path`` is joined to ``event.cwd``,
    never left to the host process cwd, so a same-named file elsewhere cannot
    stand in for the target (#571).
    """
    ti = event.tool_input
    _, file_path = _resolve_target(event)

    if event.tool_name == "Write":
        return _read_current(file_path, missing_ok=True), ti.get("content", "")

    original = _read_current(file_path, missing_ok=False)

    if event.tool_name == "Edit":
        old, new = ti.get("old_string", ""), ti.get("new_string", "")
        if old not in original:
            raise MaterializeError("old_string not found in file")
        return original, original.replace(old, new, _replace_count(ti))

    if event.tool_name == "MultiEdit":
        content = original
        for i, edit in enumerate(ti.get("edits", [])):
            old, new = edit.get("old_string", ""), edit.get("new_string", "")
            if old not in content:
                raise MaterializeError(f"edit[{i}].old_string not found")
            content = content.replace(old, new, _replace_count(edit))
        return original, content

    raise MaterializeError(f"unsupported tool: {event.tool_name}")


def materialize_proposed_content(event: ToolEvent) -> str:
    """Reconstruct the complete content that the tool event would write."""
    return _materialize_change(event)[1]


def introduced_between(before: str, after: str) -> str:
    """The lines ``after`` adds over ``before``, per ADR-018's definition.

    Inserted or replaced lines of a deterministic sequence diff. Shared by
    the direct-tool gate and the Stop session-delta boundary so both
    boundaries attribute exactly the same way.
    """
    if not before:
        return after
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    matcher = difflib.SequenceMatcher(
        a=before_lines,
        b=after_lines,
        autojunk=False,
    )
    added: list[str] = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in {"insert", "replace"}:
            added.extend(after_lines[j1:j2])
    return "\n".join(added)


def introduced_content(event: ToolEvent) -> str:
    """The lines this edit adds, as one string.

    An edit gate and an audit ask different questions. "Is this artifact
    compliant?" is an audit, and ``mneme check --input <artifact>`` still answers
    it over whole artifacts. "Does this edit introduce a violation?" is the gate,
    and attributing the whole artifact to it means a violation already present
    blocks every later edit -- including edits to an unrelated function and the
    remediation itself. On an existing repository that turns installation into
    an immediate wall (#259). See ADR-018.

    "Introduced" is every proposed line in an ``insert`` or ``replace`` opcode
    from a deterministic sequence diff. One definition covers all three tools:
    a brand-new artifact diffs against nothing, so all of it is introduced.

    Two deliberate consequences:

    - Movement attribution follows the diff alignment. A moved line represented
      as an insertion is checked; a block aligned as unchanged is not. The gate
      does not claim semantic move detection from two text snapshots.
    - A rule can only match within introduced lines, so a violation split
      across an introduced line and an untouched one is not seen here. Rules
      are literal tokens rather than multi-line patterns, so this is a narrow
      gap, and the whole-artifact audit path still covers it.
    """
    current, proposed = _materialize_change(event)
    return introduced_between(current, proposed)


def find_memory(start: Path) -> Optional[Path]:
    env = os.environ.get("MNEME_MEMORY")
    if env:
        p = Path(env)
        return p if p.is_file() else None
    cur = Path(start).resolve()
    while True:
        candidate = cur / ".mneme" / "project_memory.json"
        if candidate.is_file():
            return candidate
        if cur.parent == cur:
            return None
        cur = cur.parent


_CHECK_TIMEOUT_SECONDS = 10

# Benchmark-only (issue #60): how the PreToolUse path runs ``mneme check``.
# Unset/unknown -> "subprocess", today's behaviour. "inprocess" runs the CLI
# inside this interpreter. Not a supported user option.
_TRANSPORT_ENV_VAR = "MNEME_HOOK_CHECK_TRANSPORT"
_VALID_TRANSPORTS = ("subprocess", "inprocess")


def resolve_transport() -> str:
    value = os.environ.get(_TRANSPORT_ENV_VAR, "").strip().lower()
    return value if value in _VALID_TRANSPORTS else "subprocess"

_VALID_MODES = ("strict", "warn")

# Environment variables consulted for the enforcement mode, in precedence order.
# MNEME_HOOK_MODE is the explicit override; CLAUDE_PLUGIN_OPTION_MODE is set by
# Claude Code from the plugin's `mode` userConfig option. The first one that is
# present wins.
_MODE_ENV_VARS = ("MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE")


def resolve_mode() -> str:
    """Resolve the Claude Code hook enforcement mode.

    Precedence: ``MNEME_HOOK_MODE`` (explicit override) > ``CLAUDE_PLUGIN_OPTION_MODE``
    (the Claude Code plugin's ``mode`` userConfig value, exported to hook
    subprocesses) > ``"strict"`` (safe default). The first variable that is set
    determines the mode; an unrecognized value falls back to ``"strict"`` so a
    typo can never silently disable enforcement.
    """
    for name in _MODE_ENV_VARS:
        value = os.environ.get(name)
        if value is not None:
            value = value.strip().lower()
            return value if value in _VALID_MODES else "strict"
    return "strict"


# <root>/mneme/integrations/claude_code/hook.py -> <root>
_PACKAGE_ROOT = Path(__file__).resolve().parents[3]


def _child_env() -> Dict[str, str]:
    """Environment that pins the child CLI to *this* hook's package tree.

    ``sys.executable -m mneme`` otherwise resolves against the child's sys.path,
    which can be a different (older) mneme install than the hook was loaded
    from. That mismatch is silent and total: an older CLI rejects ``--json``,
    the hook sees no parseable verdict, fails open on every edit, and
    enforcement is off without anyone being told. Putting the hook's own root
    first guarantees hook and CLI are the same version.
    """
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    root = str(_PACKAGE_ROOT)
    env["PYTHONPATH"] = f"{root}{os.pathsep}{existing}" if existing else root
    return env


_CHECK_JSON_SCHEMA = "mneme.check/v1"

_BLOCKING_VERDICTS = frozenset({"WARN", "FAIL"})

_KNOWN_VERDICTS = frozenset({"PASS", "WARN", "FAIL"})


def parse_verdict(stdout: str) -> Optional[Dict[str, Any]]:
    """Return the trusted verdict payload, or ``None`` if there isn't one.

    The exit code of ``mneme check`` cannot be trusted to mean "policy said
    no": strict mode returns 1 for a WARN verdict, and the interpreter also
    returns 1 for an uncaught exception, so a malformed memory file or a CLI
    crash is indistinguishable from a violation. Only a payload that parses,
    carries the expected schema, and names a known verdict counts as a verdict
    at all. Everything else returns ``None`` and the caller fails open.
    """
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema") != _CHECK_JSON_SCHEMA:
        return None
    verdict = payload.get("verdict")
    # The isinstance guard matters: an unhashable value (list, dict) would
    # raise TypeError on the frozenset membership test instead of failing open.
    if not isinstance(verdict, str) or verdict not in _KNOWN_VERDICTS:
        return None
    return payload


# Exit status of a complete ``mneme check --json`` run, by requested mode and
# verdict. Mirrors ``mneme.cli._EXIT_CODES_BY_MODE`` (a test pins the two
# together); duplicated rather than imported so the hook does not load the
# whole CLI module on every tool call.
_EXIT_CODES_BY_MODE: Dict[str, Dict[str, int]] = {
    "strict": {"PASS": 0, "WARN": 1, "FAIL": 2},
    "warn":   {"PASS": 0, "WARN": 0, "FAIL": 0},
}

# Incomplete path applicability is an operational exit 2 in either mode,
# whatever the nominal verdict (ADR-020). It is not a policy verdict, so it
# must not be judged against the complete-result matrix above.
_INCOMPLETE_EXIT_CODE = 2

_VIOLATION_SEVERITIES = frozenset({"WARN", "FAIL"})


@dataclass(frozen=True)
class VerdictAssessment:
    """Outcome of validating one ``mneme check --json`` result (#260).

    ``payload`` is set only for a coherent verdict. Otherwise ``problem``
    explains why, without echoing proposed content, and the caller fails open:
    an untrusted result proves enforcement failed, not that the edit violated
    policy.
    """

    payload: Optional[Dict[str, Any]]
    problem: str = ""
    inconsistent: bool = False


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


# ── ADR-034 numeric matcher records ──────────────────────────────────────────
# Kept literal here (not imported) so the hook does not load the matcher on
# every tool call; tests pin these to ``mneme.numeric_rule``.
_NUMERIC_RULE_TYPE = "FORBID_NUMERIC_ABOVE"
_MATCHER_KEYS = (
    "matcher_status", "matcher_outcome", "primary_reason",
    "unknown_sources", "subject_sha256",
)
_MATCHER_REASON_PRIORITY = (
    "INCOMPLETE_SOURCE_INPUT", "PARSE_FAILURE", "AMBIGUOUS_BINDING",
    "SOURCE_NOT_FOUND", "UNRECOGNIZED_FORM",
)
_MATCHER_OUTCOME_BY_STATUS = {
    "RECOGNIZED": frozenset({"VIOLATION", "NO_VIOLATION"}),
    "PARTIAL": frozenset({"VIOLATION"}),
    "MATCHER_UNEVALUATED": frozenset({"UNEVALUATED"}),
}
_MATCHER_INCOMPLETE = frozenset({"PARTIAL", "MATCHER_UNEVALUATED"})
_SOURCE_KINDS = frozenset({"symbol", "call", "input", "module"})


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def matcher_incomplete_records(payload: Dict[str, Any]) -> list:
    """Numeric traces whose matcher status leaves evaluation open.

    Applied traces, plus every numeric trace of a non-source input without a
    target path (F-1); ``assess_verdict`` has already checked which traces
    may carry a record.
    """
    return [
        item for item in payload.get("applicability") or []
        if isinstance(item, dict)
        and item.get("rule_type") == _NUMERIC_RULE_TYPE
        and item.get("matcher_status") in _MATCHER_INCOMPLETE
    ]


_NON_SOURCE_RECORD = {
    "matcher_status": "MATCHER_UNEVALUATED",
    "matcher_outcome": "UNEVALUATED",
    "primary_reason": "INCOMPLETE_SOURCE_INPUT",
    "unknown_sources": [
        {"kind": "input", "line": None, "reason": "INCOMPLETE_SOURCE_INPUT"},
    ],
}


def _is_non_source_without_target(payload: Dict[str, Any]) -> bool:
    subject = payload.get("subject")
    return (
        isinstance(subject, dict)
        and subject.get("input_kind") == "unverified_input"
        and subject.get("target_path_declared") is False
    )


def _numeric_trace_problem(
    item: Dict[str, Any],
    index: int,
    non_source: bool = False,
) -> str:
    """Why one numeric trace's matcher record is not trustworthy, or ``""``."""
    label = f"numeric rule trace {index}"
    if not _nonempty_str(item.get("rule_id")):
        return f"{label} has no rule_id"
    if non_source:
        # ADR-034 §6 (F-1): text without a target path is never source, so
        # every numeric rule, whatever the input path's applicability, must
        # carry exactly the non-source record. Anything else would let the
        # input file's own location turn into a clean result.
        if any(item.get(key) != value for key, value in _NON_SOURCE_RECORD.items()):
            return f"{label} lacks the non-source record for input without a target path"
        if not _is_sha256(item.get("subject_sha256")):
            return f"{label} has no subject digest"
        return ""
    if item.get("outcome") != "APPLIED":
        if any(key in item for key in _MATCHER_KEYS):
            return f"{label} carries a matcher record without APPLIED applicability"
        return ""
    if any(key not in item for key in _MATCHER_KEYS):
        return f"{label} is APPLIED without a complete matcher record"
    status = item["matcher_status"]
    outcomes = _MATCHER_OUTCOME_BY_STATUS.get(status) if isinstance(status, str) else None
    if outcomes is None:
        return f"{label} has an invalid matcher_status"
    if item["matcher_outcome"] not in outcomes:
        return f"{label} matcher_outcome contradicts matcher_status"
    if not _is_sha256(item["subject_sha256"]):
        return f"{label} has no subject digest"
    sources = item["unknown_sources"]
    if not isinstance(sources, list):
        return f"{label} unknown_sources is not a list"
    reasons = []
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"kind", "line", "reason"}:
            return f"{label} has a malformed unknown source"
        line = source["line"]
        if source["kind"] not in _SOURCE_KINDS or source["reason"] not in _MATCHER_REASON_PRIORITY:
            return f"{label} has an invalid unknown source"
        if line is not None and (
            not isinstance(line, int) or isinstance(line, bool) or line < 1
        ):
            return f"{label} has an invalid unknown source line"
        reasons.append(source["reason"])
    if status == "RECOGNIZED":
        if sources or item["primary_reason"] is not None:
            return f"{label} is RECOGNIZED with unknown sources"
    else:
        if not sources:
            return f"{label} is {status} without unknown sources"
        primary = next(r for r in _MATCHER_REASON_PRIORITY if r in reasons)
        if item["primary_reason"] != primary:
            return f"{label} primary_reason disagrees with its unknown sources"
    return ""


def _numeric_record_problem(
    payload: Dict[str, Any],
    applicability: list,
) -> str:
    """Validate ADR-034 records; ``""`` for any payload without them.

    A numeric trace with missing or invalid matcher fields is never read as
    complete or trusted, and every numeric violation must join an applied
    trace that recorded it, and vice versa.
    """
    numeric = [
        (index, item) for index, item in enumerate(applicability)
        if item.get("rule_type") == _NUMERIC_RULE_TYPE
    ]
    if not numeric:
        return ""
    non_source = _is_non_source_without_target(payload)
    for index, item in numeric:
        problem = _numeric_trace_problem(item, index, non_source)
        if problem:
            return problem
    subject = payload.get("subject")
    if not isinstance(subject, dict) or not _is_sha256(subject.get("subject_sha256")):
        return "numeric rule payload has no subject record"
    for index, item in numeric:
        if "subject_sha256" in item and item["subject_sha256"] != subject["subject_sha256"]:
            return f"numeric rule trace {index} is bound to a different subject"
    violated = {
        item["rule_id"] for _, item in numeric
        if item.get("matcher_outcome") == "VIOLATION"
    }
    reported: set = set()
    for v in payload.get("violations") or []:
        if isinstance(v, dict) and v.get("rule_type") == _NUMERIC_RULE_TYPE:
            if v.get("severity") != "FAIL" or v.get("kind") != "typed_rule":
                return "numeric violation is not a typed FAIL"
            reported.add(v.get("rule_id"))
    if reported != violated:
        return "numeric violations disagree with matcher outcomes"
    applied = {
        item.get("rule_id") for item in applicability
        if item.get("outcome") == "APPLIED"
    }
    for v in payload.get("violations") or []:
        if (
            isinstance(v, dict)
            and v.get("kind") == "typed_rule"
            and v.get("rule_id")
            and v.get("rule_id") not in applied
        ):
            return "typed violation is not bound to an APPLIED rule"
    return ""


def mixed_violation_actionable(payload: Dict[str, Any]) -> bool:
    """ADR-034 §8 M-a: does a trusted violation stay actionable?

    Only for payloads whose incompleteness includes numeric matcher records
    (a legacy payload without them keeps its existing fail-open semantics).
    The payload must already have passed ``assess_verdict``.
    """
    return (
        payload.get("evaluation_complete") is False
        and payload.get("verdict") in _BLOCKING_VERDICTS
        and bool(matcher_incomplete_records(payload))
    )


def _verdict_inconsistency(
    payload: Dict[str, Any],
    returncode: Any,
    requested_mode: str,
) -> str:
    """Return why a schema-valid payload is incoherent, or ``""`` if it is not.

    Unknown extra keys stay permitted for compatible evolution within v1.
    """
    verdict = payload["verdict"]

    # Envelope.
    mode = payload.get("mode")
    if mode not in _VALID_MODES:
        return "missing or invalid mode"
    if mode != requested_mode:
        return f"mode {mode}, requested {requested_mode}"
    violations = payload.get("violations")
    if not isinstance(violations, list):
        return "violations is not a list"
    if "freshness" in payload and not isinstance(payload["freshness"], list):
        return "freshness is not a list"
    complete = payload.get("evaluation_complete", True)
    if not isinstance(complete, bool):
        return "evaluation_complete is not a boolean"
    applicability = payload.get("applicability")
    if applicability is not None:
        if not isinstance(applicability, list) or not all(
            isinstance(item, dict) for item in applicability
        ):
            return "applicability is not a list of objects"
        unknown = any(item.get("outcome") == "UNKNOWN" for item in applicability)
        numeric_problem = _numeric_record_problem(payload, applicability)
        if numeric_problem:
            return numeric_problem
        # ADR-034 §4: the aggregate is "path UNKNOWN or matcher PARTIAL /
        # MATCHER_UNEVALUATED". Without numeric records this is exactly the
        # pre-ADR-034 path-only comparison.
        incomplete = unknown or bool(matcher_incomplete_records(payload))
        if incomplete == complete:
            return (
                "evaluation_complete disagrees with applicability outcomes"
            )

    # Violation records.
    for index, v in enumerate(violations):
        if not isinstance(v, dict):
            return f"violation {index} is not an object"
        if not _nonempty_str(v.get("decision_id")):
            return f"violation {index} has no decision_id"
        if not isinstance(v.get("decision_text"), str):
            return f"violation {index} has no decision_text"
        severity = v.get("severity")
        if not isinstance(severity, str) or severity not in _VIOLATION_SEVERITIES:
            return f"violation {index} has invalid severity"
        if not _nonempty_str(v.get("rule")):
            return f"violation {index} has no rule"
        if not _nonempty_str(v.get("trigger")):
            return f"violation {index} has no trigger"

    # Aggregate consistency (mirrors the enforcer's verdict derivation).
    severities = [v["severity"] for v in violations]
    if verdict == "PASS" and severities:
        return f"PASS with {len(severities)} violation(s)"
    if verdict == "WARN" and (not severities or "FAIL" in severities):
        return (
            "WARN with a FAIL violation" if severities
            else "WARN with no violations"
        )
    if verdict == "FAIL" and "FAIL" not in severities:
        return "FAIL with no FAIL violation"

    # Process consistency.
    if not isinstance(returncode, int) or isinstance(returncode, bool):
        return "exit status unavailable"
    if not complete:
        if returncode != _INCOMPLETE_EXIT_CODE:
            return f"incomplete evaluation with exit {returncode}"
        return ""
    expected = _EXIT_CODES_BY_MODE[mode][verdict]
    if returncode != expected:
        return f"{verdict} with exit {returncode} in {mode} mode"
    return ""


def assess_verdict(
    stdout: str,
    returncode: Any,
    requested_mode: str,
) -> VerdictAssessment:
    """Trust a ``mneme check --json`` result only if it is coherent (#260).

    ``parse_verdict`` answers "is there a payload at all?". This adds what
    needs stdout, exit status and the requested mode together: a valid-looking
    payload whose mode, violations, or exit status contradict it means the
    child broke its own contract, which is not a verdict. Both outcomes fail
    open; only the diagnostic differs.
    """
    payload = parse_verdict(stdout)
    if payload is None:
        return VerdictAssessment(
            None, f"no parseable verdict from mneme check (exit {returncode})"
        )
    inconsistency = _verdict_inconsistency(payload, returncode, requested_mode)
    if inconsistency:
        return VerdictAssessment(
            None,
            f"inconsistent verdict payload ({inconsistency}); "
            "enforcement inactive for this check",
            inconsistent=True,
        )
    return VerdictAssessment(payload)


def _is_stale_runtime(child_stderr: str) -> bool:
    """True when the child CLI lacks required machine/path-aware options."""
    return "unrecognized arguments" in (child_stderr or "") and any(
        option in (child_stderr or "")
        for option in ("--json", "--target-path")
    )


def format_reason(payload: Dict[str, Any]) -> str:
    """Render a payload's violations as human-readable enforcement feedback."""
    violations = payload.get("violations") or []
    if not violations:
        return f"mneme: {payload.get('verdict')} (no violations reported)"

    # ASCII only: this string is written to stderr, which Claude Code may read
    # under a non-UTF-8 console codepage (cp1252 on Windows). Non-ASCII
    # punctuation arrives mojibaked.
    lines = [f"mneme: {payload.get('verdict')} - architectural decision violated"]
    for v in violations:
        numeric = v.get("numeric")
        if isinstance(numeric, dict) and numeric.get("contract"):
            # ADR-034: render the contract in human terms, not raw JSON.
            lines.append(
                f"  [{v.get('decision_id')}] {v.get('severity')} "
                f"{v.get('rule_type')}: {numeric['contract']} - "
                f"trigger: {v.get('trigger')}"
            )
        else:
            lines.append(
                f"  [{v.get('decision_id')}] {v.get('severity')} "
                f"\"{v.get('rule')}\" - trigger: {v.get('trigger')}"
            )
        if v.get("decision_text"):
            lines.append(f"      {v['decision_text']}")
        if v.get("input_path"):
            selector = f" via {v.get('selector')}" if v.get("selector") else ""
            lines.append(f"      path: {v['input_path']}{selector}")
    return "\n".join(lines)


def format_applicability_reason(payload: Dict[str, Any]) -> str:
    """Render scoped-rule UNKNOWN traces for fail-open diagnostics."""
    traces = [
        item for item in (payload.get("applicability") or [])
        if isinstance(item, dict) and item.get("outcome") == "UNKNOWN"
    ]
    matcher = matcher_incomplete_records(payload)
    lines: list = []
    if traces or not matcher:
        lines.append(
            "mneme-hook: typed-rule path applicability is unknown; failing open."
        )
    for item in traces:
        value = (
            "(numeric contract)"
            if item.get("rule_type") == _NUMERIC_RULE_TYPE
            else repr(item.get("rule_value"))
        )
        lines.append(
            f"  [{item.get('decision_id')}] {item.get('rule_type')} "
            f"{value}: {item.get('reason')}"
        )
    if matcher:
        # ADR-034 G1: numeric rules are decided only by a whole-file audit
        # (`mneme check --source-file`). Delta input is never complete
        # source, so no pre-write numeric detection is claimed here.
        lines.append(
            "mneme-hook: numeric typed rule(s) not evaluated on this input "
            "(whole-file audit only: mneme check --source-file)."
        )
        for item in matcher:
            lines.append(
                f"  [{item.get('decision_id')}] {item.get('rule_type')} "
                f"{item.get('rule_id')}: {item.get('matcher_status')} "
                f"({item.get('primary_reason')})"
            )
    return "\n".join(lines)


def _emit_defer(reason: str, stdout: TextIO) -> None:
    """Report a non-blocking warn-mode verdict to Claude Code.

    ``defer`` hands the call back to the normal permission flow. ``allow``
    would be wrong here: it auto-approves the tool call, so warn mode would
    silently bypass whatever permission prompt the user would otherwise get --
    a warning mode must not weaken permissions.
    """
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "defer",
                "permissionDecisionReason": reason,
            }
        },
        stdout,
    )
    stdout.write("\n")


def _resolve_target(event: ToolEvent) -> tuple[str, str]:
    """Return ``(rel_label, absolute_or_empty_target)`` for a tool event."""
    rel = event.file_path or "(unknown)"
    target_path = event.file_path
    if target_path and not Path(target_path).is_absolute() and event.cwd:
        target_path = str(Path(event.cwd) / target_path)
    return rel, target_path


def _direct_write_memory_start(event: ToolEvent) -> Path:
    """Where the direct-write gate starts its ``find_memory`` walk (T-08 slice 1).

    The repository being modified governs, not the session ``cwd``: the walk
    starts at the parent of the fully resolved target, so the selected
    memory's policy root always contains the checked path (a final-component
    symlink is followed, exactly as ``mneme check`` resolves it). With no
    resolvable target -- no ``file_path``, or a relative one and an empty
    payload ``cwd`` -- the start stays the payload ``cwd`` as before.
    """
    _, target_path = _resolve_target(event)
    if target_path and (event.cwd or Path(target_path).is_absolute()):
        return Path(target_path).resolve().parent
    return Path(event.cwd or ".")


def _invoke_check(
    memory: Path,
    rel_label: str,
    target_path: str,
    checked_content: str,
    stderr: TextIO = sys.stderr,
    transport: str = "subprocess",
) -> Optional[subprocess.CompletedProcess]:
    """Run ``mneme check`` over one proposed delta; return the child result.

    Returns ``None`` when the child could not be launched or timed out; the
    caller owns verdict interpretation and its fail-open policy.

    ``transport="inprocess"`` is benchmark-only and used solely by the
    PreToolUse path: a timeout there ends this hook process with exit 0
    (fail open), which is what that path does with ``None`` anyway.
    """
    mode = resolve_mode()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(checked_content)
        input_path = tf.name

    try:
        command = [
            sys.executable, "-m", "mneme", "check",
            "--memory", str(memory),
            "--input", input_path,
            "--query", f"edit to {rel_label}",
            "--mode", mode,
            "--json",
        ]
        if target_path:
            command.extend(["--target-path", target_path])
        if transport == "inprocess":
            return _invoke_check_inprocess(command[3:])
        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=_CHECK_TIMEOUT_SECONDS,
                env=_child_env(),
            )
        except FileNotFoundError:
            print(
                "mneme-hook: could not launch mneme check (interpreter not found). "
                "Failing open.",
                file=stderr,
            )
            return None
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"mneme-hook: check could not run ({e}). Failing open.", file=stderr)
            return None
    finally:
        try:
            os.unlink(input_path)
        except OSError:
            pass


def _inprocess_timeout(timeout: float) -> None:
    sys.__stderr__.write(
        f"mneme-hook: check could not run (timed out after {timeout:g}s, "
        "in-process). Failing open.\n"
    )
    sys.__stderr__.flush()
    os._exit(0)


def _invoke_check_inprocess(argv: list) -> subprocess.CompletedProcess:
    # Imported here so the default subprocess path never pays for them.
    import threading
    import time

    from mneme.integrations.claude_code.inprocess_check import run_check_inprocess

    # benchmark/test seam: both variables are read only on this branch.
    timeout = float(os.environ.get("MNEME_HOOK_CHECK_TIMEOUT_TEST", _CHECK_TIMEOUT_SECONDS))
    watchdog = threading.Timer(timeout, _inprocess_timeout, args=(timeout,))
    watchdog.daemon = True
    watchdog.start()
    try:
        stall = os.environ.get("MNEME_HOOK_TEST_STALL_SECONDS")
        if stall:
            time.sleep(float(stall))
        return run_check_inprocess(argv)
    finally:
        watchdog.cancel()


def _run_check(
    event: ToolEvent,
    proposed_content: str,
    memory: Path,
    stderr: TextIO,
    stdout: TextIO,
    availability: Optional[LocalDeclaration] = None,
    note: Optional[ProceedNote] = None,
) -> int:
    mode = resolve_mode()

    rel, target_path = _resolve_target(event)
    # Default path passes no transport, so the call is exactly today's.
    extra = {"transport": "inprocess"} if resolve_transport() == "inprocess" else {}
    proc = _invoke_check(memory, rel, target_path, proposed_content, stderr=stderr, **extra)
    if proc is None:
        if emit_availability(availability, "NOT_RUN", stderr, memory=memory, note=note):
            return 2
        return 0

    assessment = assess_verdict(proc.stdout, proc.returncode, mode)
    payload = assessment.payload
    if emit_availability(
        availability, classify_observation(payload), stderr,
        memory=memory, payload=payload, note=note,
    ):
        return 2
    if payload is None:
        # No trusted verdict: a crash, a traceback, or a payload that
        # contradicts itself or its exit status. Never block on this.
        if assessment.inconsistent:
            print(f"mneme-hook: {assessment.problem}. Failing open.", file=stderr)
            return 0
        if _is_stale_runtime(proc.stderr):
            # Silence here would mean enforcement is off with nobody told.
            print(
                "mneme-hook: the installed mneme CLI does not support "
                "the required JSON/path-aware check options, so no edit "
                "can be checked and ENFORCEMENT IS "
                "INACTIVE. Upgrade with: pipx upgrade mneme-hq",
                file=stderr,
            )
            return 0
        print(f"mneme-hook: {assessment.problem}. Failing open.", file=stderr)
        if proc.stderr:
            print(proc.stderr, file=stderr)
        return 0

    verdict = payload["verdict"]
    if payload.get("evaluation_complete") is False:
        print(format_applicability_reason(payload), file=stderr)
        if not mixed_violation_actionable(payload):
            return 0
        # M-a (ADR-034 §8): a trusted violation stays actionable even when
        # numeric rules are unevaluated on this delta.
    if verdict == "PASS":
        return 0

    reason = format_reason(payload)
    if mode == "warn":
        if note is not None and note.text:
            # C2b section 17.3: one object only. The host ignores additionalContext
            # alongside defer, so the UNVERIFIABLE text rides in the reason.
            reason = reason + "\n" + note.text
            note.consumed = True
        _emit_defer(reason, stdout)
        return 0

    if verdict in _BLOCKING_VERDICTS:
        # Exit 2 is the documented blocking path: Claude Code feeds stderr
        # back to the model as the reason the edit was refused.
        print(reason, file=stderr)
        return 2
    return 0


# ── ADR-021: Bash pre-execution gate ─────────────────────────────────────────

_SHELL_TRACE_PREFIX = "mneme-hook: Bash"


def bash_tool_event(
    event: ToolEvent,
    stderr: TextIO,
    stdout: TextIO,
) -> int:
    """Preflight a Bash call when — and only when — it is reconstructable.

    Class A (quoted-delimiter heredoc writes) is materialized and checked
    before execution. Classes B/C pass through; the Stop boundary audits what
    they actually did. Classification alone never blocks.
    """
    command = event.tool_input.get("command", "") or ""
    rec = reconstruct_heredoc_write(command)
    if rec is None:
        cls = classify_command(command)
        print(
            f"{_SHELL_TRACE_PREFIX} classified {cls.value}: no deterministic "
            "pre-execution check (session-delta backstop still applies).",
            file=stderr,
        )
        return 0

    memory = find_memory(Path(event.cwd or "."))
    if memory is None:
        return 0

    target_abs = rec.target_path
    if not Path(target_abs).is_absolute() and event.cwd:
        target_abs = str(Path(event.cwd) / target_abs)

    try:
        current = _read_current(target_abs, missing_ok=True)
    except MaterializeError:
        current = ""
    proposed = current + rec.proposed_content if rec.append else rec.proposed_content
    checked = introduced_between(current, proposed)
    if not checked.strip():
        # Pure re-append of lines the artifact already ends with introduces
        # nothing new (ADR-018 blank-delta rule).
        return 0

    shell_event = ToolEvent(
        tool_name="Bash",
        file_path=target_abs,
        cwd=event.cwd,
        tool_input={},
    )
    return _run_check(shell_event, checked, memory, stderr, stdout)


# ── ADR-021: session lifecycle surfaces ─────────────────────────────────────

_MAX_BLOCKED_ARTIFACTS = 5


def _emit_stop_feedback(stdout: TextIO, message: str) -> None:
    """Surface a degraded-but-permit state to the agent.

    Claude never sees stderr from an exit-0 hook (debug log only), so every
    non-blocking operational state must go out as Stop feedback instead.
    """
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": message,
            }
        },
        stdout,
    )
    stdout.write("\n")


def session_start_event(
    envelope: Dict[str, Any],
    stderr: TextIO,
    stdout: TextIO,
) -> int:
    """Capture the per-session repository baseline.

    Only a fresh ``startup`` refreshes an existing snapshot; resume, clear,
    compact, and fork keep it so mid-session compaction cannot launder deltas
    introduced earlier in the same working tree.
    """
    memory = find_memory(Path(envelope.get("cwd") or "."))
    if memory is None:
        return 0
    root = policy_root(memory)
    cleanup_stale()
    source = str(envelope.get("source") or "startup")
    spath = snapshot_path(root, str(envelope.get("session_id") or ""))
    if source != "startup" and load_snapshot(spath, expected_root=root) is not None:
        return 0
    detail = ""
    baseline = None
    try:
        baseline = capture_baseline(root)
    except OSError as e:
        detail = str(e)
    if baseline is None:
        # Plain-text stdout from SessionStart is added to Claude's context,
        # so this is genuinely visible (stderr would only reach debug logs).
        reason = detail or "repository enumeration failed"
        print(
            "mneme-hook: session baseline unavailable (" + reason + "); "
            "completion-time attribution is inactive for this session.",
            file=stdout,
        )
        return 0
    try:
        save_snapshot(spath, baseline)
    except OSError as e:
        # Plain-text stdout from SessionStart reaches Claude's context;
        # stderr would only reach debug logs, hiding a baseline-less session.
        print(
            f"mneme-hook: session baseline could not be stored ({e}); "
            "completion-time attribution is inactive for this session.",
            file=stdout,
        )
    return 0


def _applicability_outcomes(payload: Dict[str, Any]) -> Dict[tuple, str]:
    """Map ``(decision_id, rule_type, rule_value)`` to its selector outcome."""
    out: Dict[tuple, str] = {}
    for item in payload.get("applicability") or []:
        if isinstance(item, dict):
            key = (
                item.get("decision_id"),
                item.get("rule_type"),
                item.get("rule_value"),
            )
            out[key] = str(item.get("outcome"))
    return out


def _trusted_payload(
    proc: Optional[subprocess.CompletedProcess],
    mode: str,
    stderr: TextIO,
) -> Optional[Dict[str, Any]]:
    """Return a coherent verdict payload, reporting inconsistency loudly."""
    if proc is None:
        return None
    assessment = assess_verdict(proc.stdout, proc.returncode, mode)
    if assessment.inconsistent:
        print(f"mneme-hook: {assessment.problem}.", file=stderr)
    return assessment.payload


def _evaluate_renamed(
    memory: Path,
    root: Path,
    new_rel: str,
    old_rel: str,
    stderr: TextIO,
) -> Optional[tuple[Optional[str], Optional[str]]]:
    """Check an exact-content move for a policy-identity change.

    Byte identity is not policy identity (ADR-020): the same bytes can be
    excluded at one path and governed at another. Both evaluations reuse the
    core check path with real target paths — no selector logic lives here.
    Returns ``(reason, note)``; ``reason`` set only when the move moved
    content from an unapplied rule context into an applied one. Legacy rules
    carry no path dimension, so they cannot change meaning across a move and
    never block here; typed UNKNOWN outcomes fail open with a note.
    """
    abs_path = root / new_rel
    try:
        body = abs_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as e:
        return None, f"unreadable during rename evaluation: {e}"
    if not body.strip():
        return None, None

    # Identical query label for both runs so retrieval gating is identical;
    # only --target-path differs.
    mode = resolve_mode()
    proc_new = _invoke_check(memory, new_rel, str(root / new_rel), body, stderr=stderr)
    payload_new = _trusted_payload(proc_new, mode, stderr)
    if payload_new is None:
        return None, "rename target could not be evaluated (untrusted checker result)"
    incomplete_note: Optional[str] = None
    if payload_new.get("evaluation_complete") is False:
        print(format_applicability_reason(payload_new), file=stderr)
        if not mixed_violation_actionable(payload_new):
            return None, "rename target had incomplete rule-path evaluation"
        incomplete_note = "rename target had incomplete rule-path evaluation"

    proc_old = _invoke_check(memory, new_rel, str(root / old_rel), body, stderr=stderr)
    payload_old = _trusted_payload(proc_old, mode, stderr)
    if payload_old is None:
        return None, (
            "rename could not be compared against its previous path "
            "(untrusted checker result)"
        )

    new_map = _applicability_outcomes(payload_new)
    old_map = _applicability_outcomes(payload_old)
    changed = []
    for v in payload_new.get("violations") or []:
        if v.get("kind") != "typed_rule":
            continue
        key = (v.get("decision_id"), v.get("rule_type"), v.get("rule"))
        if new_map.get(key) == "APPLIED" and old_map.get(key) != "APPLIED":
            changed.append(v)
    if not changed:
        return None, incomplete_note

    filtered = dict(payload_new)
    filtered["violations"] = changed
    return format_reason(filtered), incomplete_note


def stop_event(
    envelope: Dict[str, Any],
    stderr: TextIO,
    stdout: TextIO,
) -> int:
    """Session-delta backstop: post-mutation, pre-completion.

    Evaluates only content this session introduced (baseline -> now diff with
    ADR-018 semantics). Blocks via the documented Stop JSON decision on a
    trusted blocking verdict; every degraded path is visible and never a
    fabricated pass.

    ``stop_hook_active`` does NOT bypass evaluation. It is true precisely
    when Claude is continuing because a Stop hook blocked before — i.e.
    exactly the repair-recheck turn. Skipping it would let an unverified
    "repair" complete. Loop safety comes from determinism instead: the gate
    blocks only on trusted verdicts over the session delta, so a real repair
    passes on re-evaluation, and Claude Code's documented eight-consecutive-
    block cap bounds any unresolvable case.
    """
    memory = find_memory(Path(envelope.get("cwd") or "."))
    if memory is None:
        return 0

    root = policy_root(memory)

    files = enumerate_repo_files(root)
    if files is None:
        _emit_stop_feedback(
            stdout,
            "mneme: not inside a git work tree; the session-delta gate is "
            "inactive for this turn.",
        )
        return 0

    spath = snapshot_path(root, str(envelope.get("session_id") or ""))
    baseline = load_snapshot(spath, expected_root=root)
    if baseline is None:
        detail = ""
        try:
            captured = capture_baseline(root)
        except OSError as e:
            captured = None
            detail = str(e)
        if captured is None:
            _emit_stop_feedback(
                stdout,
                "mneme: no session baseline exists and capture failed "
                f"({detail or 'repository enumeration failed'}); nothing can "
                "be attributed to this session this turn.",
            )
            return 0
        try:
            save_snapshot(spath, captured)
        except OSError as e:
            _emit_stop_feedback(
                stdout,
                f"mneme: no session baseline exists and storing one failed "
                f"({e}); nothing can be attributed to this session this turn.",
            )
            return 0
        _emit_stop_feedback(
            stdout,
            "mneme: no session baseline was found; captured one now. "
            "Repository mutations made before this point cannot be attributed "
            "to this session and were not evaluated.",
        )
        return 0

    delta = compute_session_delta(root, baseline, files)

    mode = resolve_mode()
    offenders: list[tuple[str, str]] = []  # (rel, reason)
    unevaluated = list(delta.skipped.items())

    candidates: list[tuple[str, str]] = []
    for rel in delta.new:
        abs_path = root / rel
        try:
            size = abs_path.stat().st_size
        except OSError as e:
            unevaluated.append((rel, f"unreadable during evaluation: {e}"))
            continue
        if size > MAX_FILE_BYTES:
            unevaluated.append(
                (
                    rel,
                    "new artifact exceeds the evaluation size budget "
                    f"({size} > {MAX_FILE_BYTES} bytes)",
                )
            )
            continue
        try:
            body = abs_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as e:
            unevaluated.append((rel, f"unreadable during evaluation: {e}"))
            continue
        if body.strip():
            candidates.append((rel, body))
    for rel, introduced in delta.modified.items():
        candidates.append((rel, introduced))

    untrusted = 0
    incomplete = 0
    for rel, body in candidates:
        proc = _invoke_check(memory, rel, str(root / rel), body, stderr=stderr)
        if proc is None:
            untrusted += 1
            continue
        assessment = assess_verdict(proc.stdout, proc.returncode, mode)
        payload = assessment.payload
        if payload is None:
            untrusted += 1
            if assessment.inconsistent:
                print(f"mneme-hook: {rel}: {assessment.problem}.", file=stderr)
            elif _is_stale_runtime(proc.stderr):
                print(
                    "mneme-hook: installed CLI lacks required JSON/path-aware "
                    "options; ENFORCEMENT IS INACTIVE. Upgrade with: "
                    "pipx upgrade mneme-hq",
                    file=stderr,
                )
            continue
        if payload.get("evaluation_complete") is False:
            incomplete += 1
            print(format_applicability_reason(payload), file=stderr)
            if not mixed_violation_actionable(payload):
                continue
        if payload["verdict"] in _BLOCKING_VERDICTS:
            offenders.append((rel, format_reason(payload)))

    # Exact-content moves are evaluated against BOTH paths: byte identity is
    # not policy identity (ADR-020). A violation only blocks when its typed
    # rule was not applied at the previous path but applies at the new one.
    for new_rel, old_rel in delta.renamed.items():
        outcome = _evaluate_renamed(memory, root, new_rel, old_rel, stderr)
        if outcome is None:
            continue
        reason, note = outcome
        if note:
            unevaluated.append((new_rel, note))
        if reason:
            offenders.append((new_rel, reason))

    notes: list[str] = []
    if untrusted:
        notes.append(
            f"{untrusted} changed artifact(s) could not be evaluated "
            "(untrusted checker result); failing open per transport policy."
        )
    if incomplete:
        notes.append(
            f"{incomplete} changed artifact(s) had incomplete rule-path "
            "evaluation (see applicability diagnostics above)."
        )
    if unevaluated:
        shown = [
            f"{rel} ({reason})" if reason else rel
            for rel, reason in unevaluated[:10]
        ]
        listing = "; ".join(shown)
        notes.append(
            "session delta not evaluated for: "
            + listing
            + ("..." if len(unevaluated) > 10 else "")
        )
    for note in notes:
        print(f"mneme-hook: {note}", file=stderr)

    if not offenders:
        if notes:
            _emit_stop_feedback(
                stdout,
                "mneme session-delta gate completed with unevaluated "
                "changes: " + " ".join(notes),
            )
        return 0

    shown = offenders[:_MAX_BLOCKED_ARTIFACTS]
    parts = [
        "mneme: repository mutations made during this session violate "
        f"{len(offenders)} governed artifact(s):"
    ]
    for rel, reason in shown:
        parts.append(f"[{rel}]")
        parts.append(reason)
    if len(offenders) > len(shown):
        parts.append(f"(+{len(offenders) - len(shown)} more)")
    reason_text = "\n".join(parts)

    if mode == "warn":
        _emit_stop_feedback(stdout, reason_text)
        return 0

    json.dump({"decision": "block", "reason": reason_text}, stdout)
    stdout.write("\n")
    return 0


# ── dispatch ─────────────────────────────────────────────────────────────────


def handle_event(
    envelope: Any,
    stderr: TextIO = sys.stderr,
    stdout: TextIO = sys.stdout,
) -> int:
    """Route one decoded hook envelope to its boundary handler."""
    if not isinstance(envelope, dict):
        print("mneme-hook: bad envelope: not a JSON object", file=stderr)
        return 0
    name = envelope.get("hook_event_name")
    if name == "SessionStart":
        return session_start_event(envelope, stderr, stdout)
    if name == "Stop":
        return stop_event(envelope, stderr, stdout)
    try:
        event = parse_event(json.dumps(envelope))
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"mneme-hook: bad envelope: {e}", file=stderr)
        return 0
    if event.tool_name == "Bash":
        return bash_tool_event(event, stderr, stdout)
    if not should_check(event.tool_name):
        return 0

    # C2b section 17: an UNVERIFIABLE proceed is reported to Claude as one
    # additionalContext object, written only when the hook exits 0 and warn
    # mode has not already carried the text in its defer object.
    note = ProceedNote()
    rc = _direct_write_event(event, stderr, stdout, note)
    if rc == 0:
        write_proceed_context(note, stdout)
    return rc


def _direct_write_event(
    event: ToolEvent,
    stderr: TextIO,
    stdout: TextIO,
    note: ProceedNote,
) -> int:
    start = _direct_write_memory_start(event)
    # ADR-033 C2a: local policy detection precedes the missing-memory return.
    # With no declaration, output, check behavior and exit codes remain
    # identical to the old path.
    availability = discover_declaration(start)
    memory = find_memory(start)
    if memory is None:
        if emit_availability(availability, "NOT_RUN", stderr, detail="check not run",
                             note=note):
            return 2
        return 0

    try:
        # The gate checks what this edit introduces, not the whole resulting
        # artifact -- otherwise a violation already present blocks every later
        # edit to it, including the one that removes it (#259, ADR-018).
        checked_content = introduced_content(event)
    except MaterializeError as e:
        if emit_availability(
            availability, "NOT_RUN", stderr, memory=memory,
            detail="proposed content could not be materialized", note=note,
        ):
            return 2
        print(f"mneme-hook: cannot materialize content, failing open: {e}", file=stderr)
        return 0

    if not checked_content.strip():
        # The edit introduces no non-blank lines (for example, a pure
        # deletion). Mechanically enforceable typed rules cannot be blank.
        emit_availability(availability, "SKIPPED", stderr, memory=memory, note=note)
        return 0

    return _run_check(
        event, checked_content, memory, stderr, stdout, availability=availability,
        note=note,
    )


def main(
    stdin: TextIO = sys.stdin,
    stderr: TextIO = sys.stderr,
    stdout: TextIO = sys.stdout,
) -> int:
    try:
        raw = stdin.read()
        envelope = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"mneme-hook: bad envelope: {e}", file=stderr)
        return 0
    return handle_event(envelope, stderr, stdout)


def cli_main() -> None:
    sys.exit(main())


if __name__ == "__main__":
    cli_main()

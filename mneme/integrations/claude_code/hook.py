"""Claude Code hook shim — translates PreToolUse events into mneme check calls."""
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
    """Return ``(current, proposed)`` from a single current-file snapshot."""
    ti = event.tool_input
    file_path = ti.get("file_path", "")

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


def introduced_content(event: ToolEvent) -> str:
    """The lines this edit adds, as one string.

    An edit gate and an audit ask different questions. "Is this file
    compliant?" is an audit, and ``mneme check --input <file>`` still answers
    it over whole files. "Does this edit introduce a violation?" is the gate,
    and attributing the whole file to it means a violation already present
    blocks every later edit -- including edits to an unrelated function and the
    remediation itself. On an existing repository that turns installation into
    an immediate wall (#259). See ADR-018.

    "Introduced" is every proposed line in an ``insert`` or ``replace`` opcode
    from a deterministic sequence diff. One definition covers all three tools:
    a brand-new file diffs against nothing, so all of it is introduced.

    Two deliberate consequences:

    - Movement attribution follows the diff alignment. A moved line represented
      as an insertion is checked; a block aligned as unchanged is not. The gate
      does not claim semantic move detection from two text snapshots.
    - A rule can only match within introduced lines, so a violation split
      across an introduced line and an untouched one is not seen here. Rules
      are literal tokens rather than multi-line patterns, so this is a narrow
      gap, and the whole-file audit path still covers it.
    """
    current, proposed = _materialize_change(event)
    if not current:
        return proposed

    before = current.splitlines()
    after = proposed.splitlines()
    matcher = difflib.SequenceMatcher(
        a=before,
        b=after,
        autojunk=False,
    )
    added: list[str] = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in {"insert", "replace"}:
            added.extend(after[j1:j2])
    return "\n".join(added)


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
    if payload.get("verdict") not in _KNOWN_VERDICTS:
        return None
    return payload


def _is_stale_runtime(child_stderr: str) -> bool:
    """True when the child CLI is too old to understand ``--json``."""
    return "unrecognized arguments" in (child_stderr or "") and "--json" in (
        child_stderr or ""
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
        lines.append(
            f"  [{v.get('decision_id')}] {v.get('severity')} "
            f"\"{v.get('rule')}\" - trigger: {v.get('trigger')}"
        )
        if v.get("decision_text"):
            lines.append(f"      {v['decision_text']}")
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


def _run_check(
    event: ToolEvent,
    proposed_content: str,
    memory: Path,
    stderr: TextIO,
    stdout: TextIO,
) -> int:
    mode = resolve_mode()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(proposed_content)
        input_path = tf.name

    try:
        rel = event.file_path or "(unknown)"
        try:
            proc = subprocess.run(
                [
                    sys.executable, "-m", "mneme", "check",
                    "--memory", str(memory),
                    "--input", input_path,
                    "--query", f"edit to {rel}",
                    "--mode", mode,
                    "--json",
                ],
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
            return 0
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"mneme-hook: check could not run ({e}). Failing open.", file=stderr)
            return 0

        payload = parse_verdict(proc.stdout)
        if payload is None:
            # No trusted verdict: a crash, a traceback, or an unexpected exit
            # code. Never block on this.
            if _is_stale_runtime(proc.stderr):
                # Silence here would mean enforcement is off with nobody told.
                print(
                    "mneme-hook: the installed mneme CLI does not support "
                    "--json, so no edit can be checked and ENFORCEMENT IS "
                    "INACTIVE. Upgrade with: pipx install --force "
                    "\"mneme-hq>=0.5.1\"",
                    file=stderr,
                )
                return 0
            print(
                "mneme-hook: no parseable verdict from mneme check "
                f"(exit {proc.returncode}). Failing open.",
                file=stderr,
            )
            if proc.stderr:
                print(proc.stderr, file=stderr)
            return 0

        verdict = payload["verdict"]
        if verdict == "PASS":
            return 0

        reason = format_reason(payload)
        if mode == "warn":
            _emit_defer(reason, stdout)
            return 0

        if verdict in _BLOCKING_VERDICTS:
            # Exit 2 is the documented blocking path: Claude Code feeds stderr
            # back to the model as the reason the edit was refused.
            print(reason, file=stderr)
            return 2
        return 0
    finally:
        try:
            os.unlink(input_path)
        except OSError:
            pass


def main(
    stdin: TextIO = sys.stdin,
    stderr: TextIO = sys.stderr,
    stdout: TextIO = sys.stdout,
) -> int:
    try:
        raw = stdin.read()
        event = parse_event(raw)
    except (json.JSONDecodeError, KeyError) as e:
        print(f"mneme-hook: bad envelope: {e}", file=stderr)
        return 0

    if not should_check(event.tool_name):
        return 0

    memory = find_memory(Path(event.cwd or "."))
    if memory is None:
        return 0

    try:
        # The gate checks what this edit introduces, not the whole resulting
        # file -- otherwise a violation already in the file blocks every later
        # edit to it, including the one that removes it (#259, ADR-018).
        checked_content = introduced_content(event)
    except MaterializeError as e:
        print(f"mneme-hook: cannot materialize content, failing open: {e}", file=stderr)
        return 0

    if not checked_content.strip():
        # The edit introduces no non-blank lines (for example, a pure
        # deletion). Mechanically enforceable typed rules cannot be blank.
        return 0

    return _run_check(event, checked_content, memory, stderr, stdout)


def cli_main() -> None:
    sys.exit(main())


if __name__ == "__main__":
    cli_main()

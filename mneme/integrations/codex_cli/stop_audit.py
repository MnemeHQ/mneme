"""Codex CLI Stop changed-tree audit (M3).

Boundary: pre-execution gates check introduced content (ADR-018); this Stop
audit checks **whole-file** compliance of what changed during the session,
providing the backstop for surfaces without structured pre-execution data
(shell writes -- see validation/codex-cli M2a).

Architecture:

- The session baseline is integration-local state (the shared
  session-snapshot store). It is captured primarily at **SessionStart** --
  before any work, covering pure-shell sessions -- and secondarily on the
  first PreToolUse event as a fallback net. Either way it is captured before
  the first mutation executes.
- Stop diffs the repository against that baseline, distinguishing files
  already dirty before Codex (never blamed unless Codex touches them),
  Codex-modified files, newly untracked files, and deletions.
- Every changed surviving artifact is checked **whole-file** through the
  existing single-file ``mneme check --json`` contract. Deletions are
  recorded but never invented into enforcement.
- Aggregate result: any violation -> the proven Stop continuation shape
  (``{"decision": "block", "reason": ...}``) naming each failing file and
  rule. Unevaluated artifacts are always disclosed and never reported as a
  clean governed result. Continuation/remediation loops are bounded by a
  consecutive-block cap (deterministic repairs pass on re-evaluation).

Failures to evaluate remain visible; nothing here can fabricate a PASS.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from mneme.integrations.claude_code.hook import (
    _CHECK_TIMEOUT_SECONDS,
    _child_env,
    format_applicability_reason,
    format_reason,
    parse_verdict,
    resolve_mode,
    _is_stale_runtime,
)
from mneme.integrations.claude_code.session_state import (
    MAX_FILE_BYTES,
    capture_baseline,
    cleanup_stale,
    compute_session_delta,
    load_snapshot,
    save_snapshot,
    snapshot_path,
)
from mneme.path_selectors import policy_root

MAX_CONSECUTIVE_STOP_BLOCKS = 8


def _blocks_path(spath: Path) -> Path:
    return spath.with_name(spath.name + ".blocks")


def _read_block_count(spath: Path) -> int:
    try:
        return int(_blocks_path(spath).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def _write_block_count(spath: Path, count: int) -> None:
    try:
        _blocks_path(spath).write_text(str(count), encoding="utf-8")
    except OSError:
        pass


def ensure_session_baseline(payload: Any, stderr=None) -> Optional[Path]:
    """Capture the session baseline if none exists yet.

    Called from SessionStart (before any work) and from PreToolUse (as a
    secondary net for sessions whose first event bypasses SessionStart).
    PreToolUse fires before that tool executes, so either way the snapshot
    is pre-mutation. An existing baseline is never overwritten (resume,
    compaction, and mid-session calls keep attribution intact).
    """
    if not isinstance(payload, dict):
        return None
    memory = _find_memory_for(payload)
    if memory is None:
        return None
    root = policy_root(memory)
    session_id = str(payload.get("session_id") or "")
    spath = snapshot_path(root, session_id)
    if load_snapshot(spath, expected_root=root) is not None:
        return spath
    try:
        baseline = capture_baseline(root)
    except OSError:
        baseline = None
    if baseline is None:
        if stderr:
            print("mneme-stop: repository enumeration failed; "
                  "session baseline unavailable.", file=stderr)
        return None
    try:
        save_snapshot(spath, baseline)
    except OSError as e:
        if stderr:
            print(f"mneme-stop: could not store session baseline ({e}).",
                  file=stderr)
        return None
    return spath


def handle_session_start(payload: Any, stderr=None, stdout=None) -> int:
    """SessionStart handler: establish the baseline before any work."""
    ensure_session_baseline(payload, stderr=stderr or sys.stderr)
    return 0


def _find_memory_for(payload: dict):
    from mneme.integrations.claude_code.hook import find_memory
    return find_memory(Path(payload.get("cwd") or "."))


def _emit_system_message(stdout, message: str) -> None:
    json.dump({"continue": True, "systemMessage": message}, stdout)
    stdout.write("\n")


def handle_stop(payload: Any, stderr=None, stdout=None) -> int:
    """Stop-event handler: audit the session changed-tree."""
    stderr = stderr or sys.stderr
    stdout = stdout or sys.stdout
    if not isinstance(payload, dict):
        return 0
    memory = _find_memory_for(payload)
    if memory is None:
        return 0
    root = policy_root(memory)
    session_id = str(payload.get("session_id") or "")
    mode = resolve_mode()

    cleanup_stale()
    files = _enumerate(root)
    if files is None:
        _emit_system_message(
            stdout,
            "mneme: not inside a git work tree; the session-delta audit is "
            "inactive for this turn.")
        return 0

    spath = snapshot_path(root, session_id)
    baseline = load_snapshot(spath, expected_root=root)
    late_note = ""
    if baseline is None:
        # No baseline was captured during the session (no PreToolUse ran, or
        # it failed). Capture now and disclose that earlier mutations cannot
        # be attributed -- but do NOT present the turn as audited.
        detail = ""
        try:
            baseline = capture_baseline(root)
        except OSError as e:
            baseline = None
            detail = str(e)
        if baseline is None:
            _emit_system_message(
                stdout,
                "mneme: no session baseline exists and capture failed "
                f"({detail or 'enumeration failed'}); the audit is inactive.")
            return 0
        try:
            save_snapshot(spath, baseline)
        except OSError as e:
            _emit_system_message(
                stdout,
                f"mneme: session baseline could not be stored ({e}); the "
                "audit is inactive.")
            return 0
        late_note = ("No session baseline existed when this turn ended; one "
                     "was captured now, so mutations made before this point "
                     "cannot be attributed to the session.")

    delta = compute_session_delta(root, baseline)

    offenders = []      # (rel, reason)
    notes = []
    deleted = list(delta.deleted)

    candidates = list(delta.new) + list(delta.modified) + list(delta.renamed)
    for rel in candidates:
        abs_path = root / rel
        try:
            size = abs_path.stat().st_size
        except OSError as e:
            notes.append(f"{rel} unreadable during evaluation ({e})")
            continue
        if size > MAX_FILE_BYTES:
            notes.append(f"{rel} exceeds the evaluation size budget "
                         f"({size} > {MAX_FILE_BYTES} bytes)")
            continue
        try:
            body = abs_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as e:
            notes.append(f"{rel} unreadable as UTF-8 during evaluation ({e})")
            continue
        if not body.strip():
            continue  # blank artifact: nothing a typed rule can match
        proc = _run_whole_file_check(memory, rel, str(abs_path), body, mode)
        if proc is None:
            notes.append(f"{rel} could not be evaluated (check did not run)")
            continue
        verdict_payload = parse_verdict(proc.stdout)
        if verdict_payload is None:
            if _is_stale_runtime(proc.stderr):
                notes.append(f"{rel}: installed mneme CLI lacks required "
                             "JSON/path-aware options; ENFORCEMENT INACTIVE.")
            else:
                notes.append(f"{rel} could not be evaluated (untrusted "
                             f"checker result, exit {proc.returncode})")
            continue
        if verdict_payload.get("evaluation_complete") is False:
            notes.append(f"{rel}: incomplete rule-path evaluation - "
                         + format_applicability_reason(verdict_payload))
            continue
        if verdict_payload["verdict"] in ("WARN", "FAIL"):
            offenders.append((rel, format_reason(verdict_payload)))

    for rel, reason in delta.skipped.items():
        notes.append(f"{rel} not evaluated ({reason})")

    if offenders:
        block_count = _read_block_count(spath)
        if block_count >= MAX_CONSECUTIVE_STOP_BLOCKS:
            _write_block_count(spath, 0)
            _emit_system_message(
                stdout,
                "mneme: the session audit blocked continuation "
                f"{MAX_CONSECUTIVE_STOP_BLOCKS} consecutive times; releasing "
                "the loop for operator review. Violations remain in: "
                + ", ".join(rel for rel, _ in offenders) + ".")
            return 0
        _write_block_count(spath, block_count + 1)

        parts = [
            "mneme: files changed during this session violate architectural "
            f"decisions ({len(offenders)} artifact(s)):"
        ]
        for rel, reason in offenders:
            parts.append(f"[{rel}]")
            parts.append(reason)
        if deleted:
            parts.append("Deleted during session (recorded; deletions are "
                         "not enforced): " + ", ".join(deleted))
        if notes:
            parts.append("Unevaluated (not claimed as governed): "
                         + "; ".join(notes[:10])
                         + ("..." if len(notes) > 10 else ""))
        json.dump({"decision": "block", "reason": "\n".join(parts)}, stdout)
        stdout.write("\n")
        return 0

    disclosures = []
    if deleted:
        disclosures.append("Deleted during session (deletions are not "
                           "enforced): " + ", ".join(deleted))
    if notes:
        disclosures.append("Unevaluated (not claimed as governed): "
                           + "; ".join(notes[:10]))
    if late_note:
        disclosures.append(late_note)
    if disclosures:
        _emit_system_message(stdout, "mneme session audit completed with "
                             "notes: " + " ".join(disclosures))
    _write_block_count(spath, 0)
    return 0


def _enumerate(root: Path):
    from mneme.integrations.claude_code.session_state import (
        enumerate_repo_files)
    return enumerate_repo_files(root)


def _run_whole_file_check(memory, rel_label, target_abs, body, mode):
    """One whole-file ``mneme check`` invocation (the audit contract)."""
    import os
    import subprocess
    import tempfile

    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8")
    handle.write(body)
    input_path = handle.name
    handle.close()

    command = [
        sys.executable, "-m", "mneme", "check",
        "--memory", str(memory),
        "--input", input_path,
        "--query", f"audit of {rel_label}",
        "--mode", mode,
        "--json",
        "--target-path", target_abs,
    ]
    try:
        try:
            return subprocess.run(
                command, capture_output=True, text=True, check=False,
                timeout=_CHECK_TIMEOUT_SECONDS, env=_child_env())
        except FileNotFoundError:
            print("mneme-stop: could not launch mneme check.", file=sys.stderr)
            return None
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"mneme-stop: audit check failed ({e}).", file=sys.stderr)
            return None
    finally:
        try:
            os.unlink(input_path)
        except OSError:
            pass

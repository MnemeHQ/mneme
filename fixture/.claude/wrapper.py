#!/usr/bin/env python3
"""Transparent capture wrapper for Mneme Claude Code hook.

Reads the raw stdin from Cursor, sanitizes it (BOM stripping, PII/path redaction),
logs a sanitized copy, then pipes it through to mneme-hook.exe, forwarding its
exit code, stdout, and stderr unchanged.

Sanitization covers: UTF-8 BOM, conversation/generation/tool-use IDs, email
addresses, absolute local paths (Windows and POSIX, full path → [PATH]),
and any nested paths within tool_input, workspace_roots, and file_path. The raw
payload is never written to persistent capture logs.
"""
import sys
import json
import re
import subprocess
import os
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Resolve fixture root from wrapper location (fixture/.claude)
# ---------------------------------------------------------------------------
CLAUDE_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURE_ROOT = os.path.dirname(CLAUDE_DIR)
MEMORY_PATH = os.path.join(FIXTURE_ROOT, ".mneme", "project_memory.json")
# Mneme memory override: by default the wrapper pins the hook to the fixture's
# project_memory.json so that the Cursor integration path (T7a) works out of the
# box.  T7b (cwd/worktree discovery) can be exercised by running the wrapper
# with the environment variable MNEME_TEST_NO_OVERRIDE=1; in that case the
# wrapper does NOT set os.environ["MNEME_MEMORY"], allowing mneme-hook.exe to
# fall back to find_memory(Path(event.cwd)) and discover the correct project
# or worktree memory.
if not os.environ.get("MNEME_TEST_NO_OVERRIDE"):
    os.environ["MNEME_MEMORY"] = MEMORY_PATH

# Capture directory (gitignored in production checked-in repo)
CAPTURE_DIR = os.path.join(FIXTURE_ROOT, "captures")
os.makedirs(CAPTURE_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# 1. Read raw stdin from Cursor (the hook event JSON)
# ---------------------------------------------------------------------------
try:
    raw_bytes = sys.stdin.buffer.read()
    # Cursor on Windows may prefix hook stdin with a UTF-8 BOM (EF BB BF).
    # Decode with utf-8-sig so the BOM is consumed rather than becoming
    # mojibake characters before the JSON envelope.
    raw_stdin = raw_bytes.decode("utf-8-sig")
except Exception:
    raw_stdin = "{}"

# ---------------------------------------------------------------------------
# 2. Sanitize the payload for the capture log
# ---------------------------------------------------------------------------
try:
    payload = json.loads(raw_stdin)
except (json.JSONDecodeError, ValueError):
    payload = {}

def _redact_emails(obj):
    """Replace any email-like substrings with [redacted]."""
    if isinstance(obj, str):
        return re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[redacted]", obj)
    if isinstance(obj, dict):
        return {k: _redact_emails(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_emails(v) for v in obj]
    return obj

def _mask_absolute_paths(obj):
    r"""Replace any absolute Windows or POSIX paths with [PATH].

    Full replacement — the entire string becomes [PATH], not just the drive
    prefix.  Covers:
      C:\Users\name\file.txt        -> [PATH]
      C:/Users/name/file.txt        -> [PATH]
      /home/name/file.txt           -> [PATH]
      /Users/name/file.txt          -> [PATH]
      nested/tool_input.file_path   -> [PATH]  (if it starts with / or a drive letter)
      workspace_roots               -> [PATH]  (if absolute)
    """
    if isinstance(obj, str):
        # Windows absolute: C:\... or C:/... (anything after the drive letter)
        winspec = re.match(r"^[A-Za-z]:[/\\].*$", obj)
        # POSIX absolute: /...
        posixspec = re.match(r"^/.+$", obj)
        if winspec or posixspec:
            return "[PATH]"
        # Relative paths stay as-is
        return obj
    if isinstance(obj, dict):
        return {k: _mask_absolute_paths(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mask_absolute_paths(v) for v in obj]
    return obj

def _remove_sensitive_keys(obj, keys_to_remove):
    """Remove specified top-level keys from a dict (recursively)."""
    if isinstance(obj, dict):
        return {k: _remove_sensitive_keys(v, keys_to_remove) for k, v in obj.items() if k not in keys_to_remove}
    if isinstance(obj, list):
        return [_remove_sensitive_keys(v, keys_to_remove) for v in obj]
    return obj

SENSITIVE_KEYS = {
    "conversation_id",
    "generation_id",
    "tool_use_id",
    "session_id",
    "transcript_path",
}

sanitized = _remove_sensitive_keys(payload, SENSITIVE_KEYS)
sanitized = _redact_emails(sanitized)
sanitized = _mask_absolute_paths(sanitized)

# Log the sanitized entry.
timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
log_entry = {
    "timestamp": timestamp,
    "stdin": json.dumps(sanitized, ensure_ascii=False),
    "cwd": "[PATH]",  # cwd is always masked — never emitted as absolute path
}
log_path = os.path.join(CAPTURE_DIR, "cursor_hook_payloads.jsonl")
with open(log_path, "a", encoding="utf-8") as f:
    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

# ---------------------------------------------------------------------------
# 3. Pipe raw stdin to mneme-hook.exe
# ---------------------------------------------------------------------------
try:
    proc = subprocess.run(
        ["mneme-hook.exe"],
        input=raw_stdin,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "MNEME_HOOK_MODE": "strict"},
    )

    # Forward the hook's stderr to our stderr (denial reason etc.)
    if proc.stderr:
        sys.stderr.write(proc.stderr)

    # Forward the hook's stdout to our stdout (any hookSpecificOutput etc.)
    if proc.stdout:
        sys.stdout.write(proc.stdout)

    # If Mneme returned exit 2 (block), surface an explicit deny decision
    # via Cursor's hookSpecificOutput format so Cursor's imported Claude
    # hook path sees a proper deny response.
    if proc.returncode == 2:
        reason = proc.stderr.strip() or "Blocked by Mneme architectural enforcement."
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }))
        sys.exit(0)

    # Otherwise fall through to whatever exit code the hook returned.
    sys.exit(proc.returncode)
except FileNotFoundError:
    print(
        "mneme-hook: could not launch mneme-hook.exe. Failing open.",
        file=sys.stderr,
    )
    sys.exit(0)
except Exception as e:
    print(f"mneme-hook: unexpected error ({e}). Failing open.", file=sys.stderr)
    sys.exit(0)
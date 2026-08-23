"""ADR-021 session state: baseline capture and session-delta attribution.

One snapshot per (repository root, Claude session_id), stored outside the
governed repository in the platform temp directory. The snapshot records
SHA-256, size, and UTF-8 body for every tracked and untracked-but-not-ignored
artifact under the policy root, within per-artifact and total budgets;
oversized or non-text artifacts are hash-only.

The delta attributes to the session exactly what ADR-018 attributes to an
edit: inserted or replaced lines of a deterministic diff between the
baseline body and the current body. New artifacts introduce everything;
deleted artifacts introduce nothing and are reported separately so that
deletion-only remediation can never be blocked.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

SNAPSHOT_VERSION = 1
SNAPSHOT_DIR_NAME = "mneme-sessions"
MAX_FILE_BYTES = 256 * 1024            # per-artifact body budget
MAX_TOTAL_BYTES = 32 * 1024 * 1024     # aggregate body budget
STALE_SNAPSHOT_SECONDS = 7 * 24 * 3600


@dataclass
class SessionDelta:
    new: List[str] = field(default_factory=list)
    modified: Dict[str, str] = field(default_factory=dict)   # rel -> introduced text
    deleted: List[str] = field(default_factory=list)
    skipped: Dict[str, str] = field(default_factory=dict)  # rel -> reason
    renamed: Dict[str, str] = field(default_factory=dict)  # new rel -> vanished source rel


def state_dir() -> Path:
    override = os.environ.get("MNEME_SESSION_STATE_DIR")
    base = Path(override) if override else Path(tempfile.gettempdir())
    return base / SNAPSHOT_DIR_NAME


def _root_key(root: Path) -> str:
    return hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:16]


def _safe_session_id(session_id: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
    return cleaned[:80] or "unknown"


def snapshot_path(root: Path, session_id: str) -> Path:
    return (
        state_dir()
        / f"{_root_key(root)}-{_safe_session_id(session_id)}.json"
    )


def enumerate_repo_files(root: Path) -> Optional[List[str]]:
    """Policy-root-relative POSIX paths of tracked + untracked-not-ignored files.

    Returns None when git is unavailable or root is not inside a work tree,
    which callers must surface as an explicit operational state.
    """
    if shutil.which("git") is None:
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z",
             "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, check=False, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    out = []
    for entry in proc.stdout.split("\0"):
        if entry:
            out.append(entry.replace("\\", "/"))
    return sorted(set(out))


def _hash_and_body(path: Path, budget_left: int) -> Dict[str, object]:
    data = path.read_bytes()
    entry: Dict[str, object] = {
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "content": None,
    }
    if len(data) <= MAX_FILE_BYTES and budget_left >= len(data):
        try:
            entry["content"] = data.decode("utf-8")
        except UnicodeDecodeError:
            entry["content"] = None  # binary artifact: hash-only
    return entry


def capture_baseline(root: Path) -> dict:
    files = enumerate_repo_files(root) or []
    entries: Dict[str, dict] = {}
    spent = 0
    for rel in files:
        abs_path = root / rel
        try:
            if not abs_path.is_file():
                continue
            entry = _hash_and_body(abs_path, MAX_TOTAL_BYTES - spent)
            content = entry.get("content")
            if isinstance(content, str):
                spent += len(content.encode("utf-8"))
            entries[rel] = entry
        except OSError:
            continue
    return {
        "version": SNAPSHOT_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "root": str(Path(root).resolve()),
        "files": entries,
    }


def load_snapshot(path: Path, expected_root: Optional[Path] = None) -> Optional[dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get("version") != SNAPSHOT_VERSION:
        return None
    if not isinstance(raw.get("files"), dict):
        return None
    if expected_root is not None:
        stored_root = raw.get("root")
        if not isinstance(stored_root, str):
            return None
        try:
            if Path(stored_root).resolve() != Path(expected_root).resolve():
                return None
        except OSError:
            return None
    return raw


def save_snapshot(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def cleanup_stale(max_age_seconds: int = STALE_SNAPSHOT_SECONDS) -> List[str]:
    removed: List[str] = []
    directory = state_dir()
    try:
        now = time.time()
        for p in directory.glob("*.json"):
            try:
                if now - p.stat().st_mtime > max_age_seconds:
                    p.unlink(missing_ok=True)
                    removed.append(p.name)
            except OSError:
                continue
    except OSError:
        pass
    return removed


def _is_snapshot_artifact(root: Path, rel: str) -> bool:
    """True when a repository-relative path lands in the snapshot store.

    Guards against MNEME_SESSION_STATE_DIR being placed inside the governed
    tree: snapshots must never audit themselves or they would perpetually
    appear as session deltas.
    """
    try:
        resolved = (root / rel).resolve()
        return state_dir() in resolved.parents
    except OSError:
        return False


def compute_session_delta(
    root: Path,
    baseline: dict,
    current_files: Optional[List[str]] = None,
) -> SessionDelta:
    """Diff current repository state against the baseline snapshot."""
    # Local import keeps this module decoupled from the hook shim's CLI surface.
    from mneme.integrations.claude_code.hook import introduced_between

    delta = SessionDelta()
    before_files: Dict[str, dict] = baseline.get("files", {})
    after_names = current_files if current_files is not None else (enumerate_repo_files(root) or [])
    after_names = [rel for rel in after_names if not _is_snapshot_artifact(root, rel)]

    # Exact-content move detection: a baseline path that has vanished while its
    # byte-identical content reappears at a new path is a rename/move of
    # pre-session content. Attributing the whole target to the session would
    # blame pre-existing lines on this session (the ADR-018 wall at a new
    # boundary). Only exact vanished-source matches qualify; copies from live
    # sources stay fully attributed (conservative direction).
    current_set = set(after_names)
    vanished_by_sha: Dict[str, str] = {}
    for old_rel, entry in before_files.items():
        if old_rel not in current_set and isinstance(entry.get("sha256"), str):
            vanished_by_sha.setdefault(entry["sha256"], old_rel)
    renamed: Dict[str, str] = {}

    for rel in after_names:
        abs_path = root / rel
        before = before_files.get(rel)
        try:
            if not abs_path.is_file():
                if before is not None:
                    delta.deleted.append(rel)
                continue
            data = abs_path.read_bytes()
        except OSError as exc:
            delta.skipped[rel] = f"unreadable during evaluation: {exc}"
            continue
        current_sha = hashlib.sha256(data).hexdigest()

        if before is None:
            source_rel = vanished_by_sha.pop(current_sha, None)
            if source_rel is not None:
                renamed[rel] = source_rel
                continue
            delta.new.append(rel)
            continue

        if before.get("sha256") == current_sha:
            continue

        body = before.get("content")
        if not isinstance(body, str):
            delta.skipped[rel] = (
                "baseline body unavailable (binary artifact or over the "
                "snapshot size budget); session delta not evaluated"
            )
            continue
        try:
            current_text = data.decode("utf-8")
        except UnicodeDecodeError:
            delta.skipped[rel] = (
                "current bytes are not valid UTF-8; session delta not evaluated"
            )
            continue
        introduced = introduced_between(body, current_text)
        if introduced.strip():
            delta.modified[rel] = introduced

    delta.renamed = renamed
    return delta

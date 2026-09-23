"""
mneme.open_architecture.execution — Pinned repository materialization.

Materializes an external repository at an exact, pinned commit SHA into an
isolated temporary workspace for O1A benchmark research.

Security & Boundary Rules:
- Repository contents are untrusted input.
- NEVER execute repository scripts, build systems, package managers, or hooks.
- Git hooks are explicitly disabled via -c core.hooksPath= and --template=.
- Git LFS filters are disabled.
- Submodules are NOT initialized.
- No canonical Mneme state (.mneme/project_memory.json, DecisionIndex,
  DecisionProposal, etc.) is written or mutated.
- The checkout is temporary and disposable; cleanup is deterministic.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

from mneme.open_architecture.manifest import RepositoryConfig

_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
_GITHUB_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

# Matches recognized GitHub remote URLs:
#   https://github.com/owner/repo(.git)
#   http://github.com/owner/repo(.git)
#   git@github.com:owner/repo(.git)
#   ssh://git@github.com/owner/repo(.git)
_REMOTE_RE = re.compile(
    r"^(?:https?://github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"([^/]+)/([^/]+?)(?:\.git)?/?$"
)


# ── Error Taxonomy ─────────────────────────────────────────────────────────────


class RepositoryExecutionError(Exception):
    """Base exception for all O1A repository execution and materialization errors."""


class MissingCommitShaError(RepositoryExecutionError):
    """Raised when repository configuration does not specify a commit SHA."""


class MalformedCommitShaError(RepositoryExecutionError):
    """Raised when repository commit SHA is not a valid 40-character hex string."""


class GitUnavailableError(RepositoryExecutionError):
    """Raised when the git executable is not available on PATH or fails to run."""


class RepositoryCloneError(RepositoryExecutionError):
    """Raised when cloning the repository fails."""


class CommitUnavailableError(RepositoryExecutionError):
    """Raised when the requested commit SHA is not available in the repository."""


class CheckoutError(RepositoryExecutionError):
    """Raised when checking out the requested commit fails."""


class ResolvedShaMismatchError(RepositoryExecutionError):
    """Raised when the checked-out HEAD SHA does not match the requested commit SHA."""


class DirtyWorkingTreeError(RepositoryExecutionError):
    """Raised when the working tree is dirty immediately after materialization."""


class RepositoryOriginMismatchError(RepositoryExecutionError):
    """Raised when the checkout origin remote does not match the expected repository."""


# ── Core Model ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RepositoryCheckout:
    """Immutable result of a pinned repository materialization.

    Attributes:
        repo_id: Logical repository identifier from manifest (e.g. 'adrkit').
        repository_identifier: GitHub owner/repo identifier (e.g. 'mbeacom/adrkit').
        requested_commit_sha: 40-character lowercase hex commit SHA requested.
        resolved_commit_sha: 40-character lowercase hex commit SHA verified at HEAD.
        checkout_path: Path to the isolated temporary checkout directory.
    """

    repo_id: str
    repository_identifier: str
    requested_commit_sha: str
    resolved_commit_sha: str
    checkout_path: Path

    def __post_init__(self) -> None:
        if not self.repo_id or not isinstance(self.repo_id, str):
            raise ValueError("repo_id must be non-empty string")
        if not self.repository_identifier or not isinstance(self.repository_identifier, str):
            raise ValueError("repository_identifier must be non-empty string")
        if not _SHA_PATTERN.match(self.requested_commit_sha):
            raise ValueError(
                f"requested_commit_sha must be 40-character hex SHA, got {self.requested_commit_sha!r}"
            )
        if not _SHA_PATTERN.match(self.resolved_commit_sha):
            raise ValueError(
                f"resolved_commit_sha must be 40-character hex SHA, got {self.resolved_commit_sha!r}"
            )
        if self.requested_commit_sha.lower() != self.resolved_commit_sha.lower():
            raise ValueError(
                f"requested_commit_sha ({self.requested_commit_sha}) and "
                f"resolved_commit_sha ({self.resolved_commit_sha}) must match"
            )


# ── Subprocess Helpers ─────────────────────────────────────────────────────────


def _sanitize_git_output(text: str) -> str:
    """Strip potential credentials or tokens from git command output."""
    sanitized = re.sub(r"https?://[^@\s]+@", "https://***@", text)
    return sanitized.strip()


def _run_git(
    args: Sequence[str],
    *,
    cwd: str | Path | None = None,
    timeout: float = 60.0,
) -> subprocess.CompletedProcess[str]:
    """Execute git with array arguments, no shell, capturing output."""
    full_cmd = ["git"] + list(args)
    try:
        result = subprocess.run(
            full_cmd,
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return result
    except FileNotFoundError as exc:
        raise GitUnavailableError("git executable not found on system PATH") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitUnavailableError(f"git execution failed: {exc}") from exc


def _safe_rmtree(path: Path) -> None:
    """Recursively remove a directory tree, clearing read-only flags on Windows."""
    def _on_error(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    def _on_exc(func, p, exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    try:
        shutil.rmtree(path, onexc=_on_exc)
    except TypeError:
        shutil.rmtree(path, onerror=_on_error)


def _verify_clean_working_tree(cwd: Path, timeout: float = 10.0) -> None:
    """Verify that the working tree has no uncommitted changes or untracked files."""
    res = _run_git(
        ["-c", "core.hooksPath=", "status", "--porcelain"],
        cwd=cwd,
        timeout=timeout,
    )
    if res.returncode != 0:
        raise DirtyWorkingTreeError(
            f"Failed to check git status: {_sanitize_git_output(res.stderr)}"
        )
    status_out = res.stdout.strip()
    if status_out:
        raise DirtyWorkingTreeError(
            f"Working tree is dirty immediately after checkout: {status_out}"
        )


def _verify_origin(cwd: Path, expected_github: str, timeout: float = 10.0) -> None:
    """Verify that checkout's origin remote matches expected owner/repo."""
    res = _run_git(
        ["-c", "core.hooksPath=", "remote", "get-url", "origin"],
        cwd=cwd,
        timeout=timeout,
    )
    if res.returncode != 0:
        raise RepositoryOriginMismatchError(
            f"Failed to read origin remote URL: {_sanitize_git_output(res.stderr)}"
        )
    origin_url = res.stdout.strip()
    match = _REMOTE_RE.match(origin_url)
    if match is None:
        raise RepositoryOriginMismatchError(
            f"Origin remote URL {origin_url!r} is not a recognized GitHub URL matching {expected_github!r}"
        )
    owner, repo = match.group(1), match.group(2)
    resolved_id = f"{owner}/{repo}"
    if resolved_id.lower() != expected_github.lower():
        raise RepositoryOriginMismatchError(
            f"Origin remote identifier {resolved_id!r} does not match expected {expected_github!r}"
        )


# ── Primary Execution Context Manager ──────────────────────────────────────────


@contextmanager
def materialize_repository(
    config: RepositoryConfig,
    *,
    workspace_dir: str | Path | None = None,
    clone_source: str | Path | None = None,
    timeout: float = 60.0,
    cleanup: bool = True,
) -> Iterator[RepositoryCheckout]:
    """Materialize a repository at an exact commit SHA into an isolated temporary checkout.

    Lifecycle ownership:
        - If workspace_dir is None: a temporary directory is allocated and automatically
          deleted when this context exits.
        - If workspace_dir is provided: caller owns workspace_dir itself. An isolated
          checkout subdirectory is created within it. On context exit, that checkout
          subdirectory is deleted if cleanup=True (default), leaving workspace_dir intact.
          If cleanup=False, the checkout subdirectory is retained.

    Args:
        config: RepositoryConfig defining the repository and exact commit SHA.
        workspace_dir: Optional caller-controlled directory in which to place the checkout.
        clone_source: Optional local directory or URL to clone from (for offline unit tests).
        timeout: Maximum duration in seconds for subprocess operations.
        cleanup: Whether to delete the checkout directory on exit (default: True).

    Yields:
        RepositoryCheckout: Verified checkout metadata and filesystem path.

    Raises:
        MissingCommitShaError: If config.commit_sha is None or empty.
        MalformedCommitShaError: If config.commit_sha is not a 40-character hex string.
        GitUnavailableError: If git is not installed or available on PATH.
        RepositoryCloneError: If git clone fails.
        CommitUnavailableError: If the requested commit SHA is not found in the repo.
        CheckoutError: If checking out the commit fails.
        ResolvedShaMismatchError: If rev-parse HEAD does not match requested SHA.
        DirtyWorkingTreeError: If the working tree is dirty after checkout.
        RepositoryOriginMismatchError: If the origin remote does not match config.github.
    """
    # 1. Validate commit SHA
    if config.commit_sha is None or not isinstance(config.commit_sha, str) or not config.commit_sha.strip():
        raise MissingCommitShaError(
            f"Repository '{config.id}' ({config.github}) has no commit SHA configured. "
            f"Pinned repository execution requires an exact 40-character commit SHA."
        )

    requested_sha = config.commit_sha.strip().lower()
    if not _SHA_PATTERN.match(requested_sha):
        raise MalformedCommitShaError(
            f"Commit SHA {config.commit_sha!r} for repository '{config.id}' is malformed; "
            f"must be an exact 40-character hex string."
        )

    # 2. Validate GitHub identifier
    if not _GITHUB_IDENTIFIER_PATTERN.match(config.github):
        raise MalformedCommitShaError(
            f"Repository github identifier {config.github!r} is malformed; must match 'owner/repo'"
        )

    # 3. Check git binary
    version_res = _run_git(["--version"], timeout=timeout)
    if version_res.returncode != 0:
        raise GitUnavailableError(
            f"git --version failed: {_sanitize_git_output(version_res.stderr)}"
        )

    # 4. Prepare workspace
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]", "_", config.id)
    temp_dir_obj: tempfile.TemporaryDirectory[str] | None = None
    target_dir: Path
    if workspace_dir is None:
        temp_dir_obj = tempfile.TemporaryDirectory(prefix=f"mneme_o1a_{safe_id}_")
        target_dir = Path(temp_dir_obj.name)
    else:
        ws = Path(workspace_dir)
        ws.mkdir(parents=True, exist_ok=True)
        unique_suffix = f"{requested_sha[:8]}_{uuid.uuid4().hex[:8]}"
        target_dir = ws / f"checkout_{safe_id}_{unique_suffix}"
        target_dir.mkdir(parents=True, exist_ok=False)

    try:
        canonical_url = f"https://github.com/{config.github}.git"

        # Security controls: disable hooks, templates, LFS filters
        clone_cmd = [
            "-c", "core.hooksPath=",
            "-c", "filter.lfs.smudge=",
            "-c", "filter.lfs.clean=",
            "-c", "filter.lfs.process=",
            "-c", "filter.lfs.required=false",
        ]
        if clone_source is not None:
            source_path_str = (
                Path(clone_source).as_posix()
                if isinstance(clone_source, Path) or os.path.exists(str(clone_source))
                else str(clone_source)
            )
            clone_cmd.extend(["-c", f"url.{source_path_str}.insteadOf={canonical_url}"])

        clone_cmd.extend([
            "clone",
            "--no-checkout",
            "--template=",
            canonical_url,
            str(target_dir),
        ])

        clone_res = _run_git(clone_cmd, timeout=timeout)
        if clone_res.returncode != 0:
            raise RepositoryCloneError(
                f"Failed to clone repository '{config.github}': "
                f"{_sanitize_git_output(clone_res.stderr)}"
            )

        # Checkout the exact commit
        checkout_cmd = [
            "-c", "core.hooksPath=",
            "checkout",
            "--detach",
            requested_sha,
        ]
        checkout_res = _run_git(checkout_cmd, cwd=target_dir, timeout=timeout)
        if checkout_res.returncode != 0:
            err_msg = _sanitize_git_output(checkout_res.stderr)
            # Try fetch if commit not found initially (e.g. unadvertised commit or branch)
            fetch_cmd = ["-c", "core.hooksPath=", "fetch", "origin", requested_sha]
            fetch_res = _run_git(fetch_cmd, cwd=target_dir, timeout=timeout)
            if fetch_res.returncode == 0:
                checkout_res = _run_git(checkout_cmd, cwd=target_dir, timeout=timeout)
            if checkout_res.returncode != 0:
                err_msg = _sanitize_git_output(checkout_res.stderr)
                if any(
                    marker in err_msg
                    for marker in (
                        "did not match any file(s) known to git",
                        "reference is not a tree",
                        "unable to read tree",
                        "fatal: Cannot switch branch",
                        "not our ref",
                        "not a valid object name",
                        "invalid reference",
                    )
                ):
                    raise CommitUnavailableError(
                        f"Requested commit SHA {requested_sha} is not available in repository '{config.github}': {err_msg}"
                    )
                raise CheckoutError(
                    f"Failed to checkout commit {requested_sha} in repository '{config.github}': {err_msg}"
                )

        # Verify HEAD SHA matches requested commit exactly
        rev_parse_res = _run_git(
            ["-c", "core.hooksPath=", "rev-parse", "HEAD"],
            cwd=target_dir,
            timeout=timeout,
        )
        if rev_parse_res.returncode != 0:
            raise ResolvedShaMismatchError(
                f"Failed to resolve HEAD SHA: {_sanitize_git_output(rev_parse_res.stderr)}"
            )
        resolved_sha = rev_parse_res.stdout.strip().lower()
        if not _SHA_PATTERN.match(resolved_sha) or resolved_sha != requested_sha:
            raise ResolvedShaMismatchError(
                f"Resolved commit SHA '{resolved_sha}' does not match requested commit SHA '{requested_sha}'"
            )

        # Verify clean working tree
        _verify_clean_working_tree(target_dir, timeout=timeout)

        # Verify repository origin
        _verify_origin(target_dir, config.github, timeout=timeout)

        checkout = RepositoryCheckout(
            repo_id=config.id,
            repository_identifier=config.github,
            requested_commit_sha=requested_sha,
            resolved_commit_sha=resolved_sha,
            checkout_path=target_dir,
        )

        yield checkout

    finally:
        if cleanup:
            if temp_dir_obj is not None:
                try:
                    temp_dir_obj.cleanup()
                except Exception:
                    if target_dir.exists():
                        _safe_rmtree(target_dir)
            else:
                if target_dir.exists():
                    _safe_rmtree(target_dir)

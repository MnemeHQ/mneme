"""
tests.open_architecture.test_execution — Tests for pinned repository materialization.

Tests all 17 required coverage items and error conditions for O1A2.1.
Uses temporary local git repositories to ensure all tests run offline without network access.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterator

import pytest

from mneme.open_architecture.execution import (
    CheckoutError,
    CommitUnavailableError,
    DirtyWorkingTreeError,
    GitUnavailableError,
    MalformedCommitShaError,
    MissingCommitShaError,
    RepositoryCheckout,
    RepositoryCloneError,
    RepositoryExecutionError,
    RepositoryOriginMismatchError,
    ResolvedShaMismatchError,
    materialize_repository,
)
from mneme.open_architecture.manifest import RepositoryConfig


# ── Fixtures & Helpers ─────────────────────────────────────────────────────────


def _create_local_git_repo(
    path: Path,
    *,
    owner_repo: str = "mbeacom/adrkit",
    num_commits: int = 2,
) -> list[str]:
    """Initialize a local git repository with multiple commits and a GitHub origin remote.

    Returns:
        List of commit SHAs (oldest first).
    """
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", f"https://github.com/{owner_repo}.git"],
        cwd=str(path),
        check=True,
    )

    shas: list[str] = []
    for i in range(num_commits):
        file_path = path / f"file_{i}.txt"
        file_path.write_text(f"commit content {i}\n", encoding="utf-8")
        subprocess.run(
            ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "add", "."],
            cwd=str(path),
            check=True,
        )
        subprocess.run(
            ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-q", "-m", f"commit {i}"],
            cwd=str(path),
            check=True,
        )
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(path),
            check=True,
            capture_output=True,
            text=True,
        )
        shas.append(res.stdout.strip().lower())

    return shas


# ── Test Cases ─────────────────────────────────────────────────────────────────


class TestRepositoryCheckoutModel:
    """Validate RepositoryCheckout dataclass constraints."""

    def test_valid_construction(self, tmp_path: Path):
        sha = "a" * 40
        checkout = RepositoryCheckout(
            repo_id="adrkit",
            repository_identifier="mbeacom/adrkit",
            requested_commit_sha=sha,
            resolved_commit_sha=sha,
            checkout_path=tmp_path,
        )
        assert checkout.repo_id == "adrkit"
        assert checkout.repository_identifier == "mbeacom/adrkit"
        assert checkout.requested_commit_sha == sha
        assert checkout.resolved_commit_sha == sha
        assert checkout.checkout_path == tmp_path

    def test_empty_repo_id_fails(self, tmp_path: Path):
        sha = "a" * 40
        with pytest.raises(ValueError, match="repo_id must be non-empty"):
            RepositoryCheckout(
                repo_id="",
                repository_identifier="mbeacom/adrkit",
                requested_commit_sha=sha,
                resolved_commit_sha=sha,
                checkout_path=tmp_path,
            )

    def test_empty_identifier_fails(self, tmp_path: Path):
        sha = "a" * 40
        with pytest.raises(ValueError, match="repository_identifier must be non-empty"):
            RepositoryCheckout(
                repo_id="adrkit",
                repository_identifier="",
                requested_commit_sha=sha,
                resolved_commit_sha=sha,
                checkout_path=tmp_path,
            )

    def test_malformed_requested_sha_fails(self, tmp_path: Path):
        with pytest.raises(ValueError, match="requested_commit_sha must be 40-character hex"):
            RepositoryCheckout(
                repo_id="adrkit",
                repository_identifier="mbeacom/adrkit",
                requested_commit_sha="not-a-sha",
                resolved_commit_sha="a" * 40,
                checkout_path=tmp_path,
            )

    def test_malformed_resolved_sha_fails(self, tmp_path: Path):
        with pytest.raises(ValueError, match="resolved_commit_sha must be 40-character hex"):
            RepositoryCheckout(
                repo_id="adrkit",
                repository_identifier="mbeacom/adrkit",
                requested_commit_sha="a" * 40,
                resolved_commit_sha="short",
                checkout_path=tmp_path,
            )

    def test_mismatched_shas_fail(self, tmp_path: Path):
        with pytest.raises(ValueError, match="must match"):
            RepositoryCheckout(
                repo_id="adrkit",
                repository_identifier="mbeacom/adrkit",
                requested_commit_sha="a" * 40,
                resolved_commit_sha="b" * 40,
                checkout_path=tmp_path,
            )


class TestRepositoryMaterialization:
    """Tests covering all 17 required behaviors."""

    # 1. Exact SHA checkout succeeds
    def test_exact_sha_checkout_succeeds(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        shas = _create_local_git_repo(source_dir, num_commits=3)
        target_sha = shas[0]  # First commit

        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=target_sha,
            primary_test="test",
            validation_status="unreviewed",
        )

        with materialize_repository(config, clone_source=source_dir) as checkout:
            assert checkout.checkout_path.is_dir()
            # File from commit 0 must exist
            assert (checkout.checkout_path / "file_0.txt").is_file()
            # Files from commits 1 & 2 must NOT exist at commit 0
            assert not (checkout.checkout_path / "file_1.txt").exists()
            assert not (checkout.checkout_path / "file_2.txt").exists()

    # 2. Returned SHA equals requested SHA
    def test_returned_sha_equals_requested_sha(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        shas = _create_local_git_repo(source_dir, num_commits=2)
        target_sha = shas[1]

        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=target_sha,
            primary_test="test",
            validation_status="unreviewed",
        )

        with materialize_repository(config, clone_source=source_dir) as checkout:
            assert checkout.resolved_commit_sha == target_sha
            assert checkout.requested_commit_sha == target_sha
            assert checkout.repo_id == "adrkit"
            assert checkout.repository_identifier == "mbeacom/adrkit"

    # 3. Missing SHA fails closed
    def test_missing_sha_fails_closed(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        _create_local_git_repo(source_dir)

        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=None,
            primary_test="test",
            validation_status="unreviewed",
        )

        with pytest.raises(MissingCommitShaError, match="has no commit SHA configured"):
            with materialize_repository(config, clone_source=source_dir):
                pass

    # 4. Malformed SHA fails closed
    @pytest.mark.parametrize(
        "bad_sha",
        [
            "main",
            "HEAD",
            "v1.0.0",
            "fa5367e",  # Short SHA
            "a" * 39,   # 39 chars
            "a" * 41,   # 41 chars
            "g" * 40,   # Non-hex characters
            " " * 40,
            "; rm -rf /",
        ],
    )
    def test_malformed_sha_fails_closed(self, tmp_path: Path, bad_sha: str):
        source_dir = tmp_path / "source"
        _create_local_git_repo(source_dir)

        # Bypass RepositoryConfig __post_init__ validation if needed using object.__setattr__
        # or construct a duck-typed config to test execution layer defense-in-depth
        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=None,
            primary_test="test",
            validation_status="unreviewed",
        )
        object.__setattr__(config, "commit_sha", bad_sha)

        with pytest.raises((MalformedCommitShaError, MissingCommitShaError)):
            with materialize_repository(config, clone_source=source_dir):
                pass

    # 5. Checkout of nonexistent SHA fails
    def test_nonexistent_sha_fails(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        _create_local_git_repo(source_dir)
        nonexistent_sha = "0" * 40

        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=nonexistent_sha,
            primary_test="test",
            validation_status="unreviewed",
        )

        with pytest.raises(CommitUnavailableError, match="not available in repository"):
            with materialize_repository(config, clone_source=source_dir):
                pass

    # 6. Dirty checkout detection fails
    def test_dirty_checkout_detection_fails(self, tmp_path: Path, monkeypatch):
        source_dir = tmp_path / "source"
        shas = _create_local_git_repo(source_dir)

        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=shas[0],
            primary_test="test",
            validation_status="unreviewed",
        )

        from mneme.open_architecture import execution

        orig_verify_clean = execution._verify_clean_working_tree

        def _dirty_verify(cwd: Path, timeout: float = 10.0):
            # Create an untracked file to simulate dirty checkout
            (cwd / "untracked_generated_file.txt").write_text("dirty")
            orig_verify_clean(cwd, timeout=timeout)

        monkeypatch.setattr(execution, "_verify_clean_working_tree", _dirty_verify)

        with pytest.raises(DirtyWorkingTreeError, match="Working tree is dirty"):
            with materialize_repository(config, clone_source=source_dir):
                pass

    # 7. Origin mismatch detection fails
    def test_origin_mismatch_detection_fails(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        shas = _create_local_git_repo(source_dir, owner_repo="other-org/other-repo")

        # Config expects mbeacom/adrkit, but cloned repository origin is other-org/other-repo
        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=shas[0],
            primary_test="test",
            validation_status="unreviewed",
        )

        with pytest.raises(RepositoryOriginMismatchError, match="does not match expected"):
            # Clone with url rewrite pointing from other-org/other-repo
            from mneme.open_architecture.execution import _run_git

            # Clone directly using clone_source without insteadOf to make origin remote point to other-org
            workspace = tmp_path / "ws"
            workspace.mkdir()
            checkout_dir = workspace / "checkout"
            _run_git([
                "-c", "core.hooksPath=",
                "-c", f"url.{source_dir.as_posix()}.insteadOf=https://github.com/other-org/other-repo.git",
                "clone", "--no-checkout", "--template=",
                "https://github.com/other-org/other-repo.git",
                str(checkout_dir),
            ])

            from mneme.open_architecture.execution import _verify_origin
            _verify_origin(checkout_dir, "mbeacom/adrkit")

    # 8. Spaces in filesystem paths work
    def test_spaces_in_filesystem_paths_work(self, tmp_path: Path):
        source_dir = tmp_path / "source with spaces in path"
        shas = _create_local_git_repo(source_dir)

        workspace_dir = tmp_path / "workspace with spaces"
        workspace_dir.mkdir()

        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=shas[0],
            primary_test="test",
            validation_status="unreviewed",
        )

        with materialize_repository(
            config, workspace_dir=workspace_dir, clone_source=source_dir
        ) as checkout:
            assert checkout.checkout_path.exists()
            assert " " in str(checkout.checkout_path)
            assert (checkout.checkout_path / "file_0.txt").is_file()

    # 9. Shell metacharacters cannot become shell execution
    def test_shell_metacharacters_cannot_execute(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        shas = _create_local_git_repo(source_dir)

        marker_file = tmp_path / "pwned.txt"

        # Attempt command injection via directory name and repo id
        injection_id = f"test$(touch {marker_file.as_posix()});rm"
        config = RepositoryConfig(
            id=injection_id,
            github="mbeacom/adrkit",
            commit_sha=shas[0],
            primary_test="test",
            validation_status="unreviewed",
        )

        with materialize_repository(config, clone_source=source_dir) as checkout:
            assert checkout.checkout_path.exists()

        # Marker file must NOT have been created by shell execution
        assert not marker_file.exists()

    # 10. Target repository scripts/hooks are not executed
    def test_target_repo_scripts_and_hooks_not_executed(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        shas = _create_local_git_repo(source_dir)

        # Plant executable hook in source repo's hooks directory
        hooks_dir = source_dir / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        hook_marker = tmp_path / "hook_executed.txt"
        post_checkout = hooks_dir / "post-checkout"
        post_checkout.write_text(
            f"#!/bin/sh\necho 'hook' > \"{hook_marker.as_posix()}\"\n",
            encoding="utf-8",
        )

        # Plant deceptive scripts in worktree
        script_marker = tmp_path / "script_executed.txt"
        (source_dir / "setup.py").write_text(
            f"import pathlib; pathlib.Path('{script_marker.as_posix()}').write_text('pwned')\n",
            encoding="utf-8",
        )
        (source_dir / "Makefile").write_text(
            f"all:\n\ttouch {script_marker.as_posix()}\n",
            encoding="utf-8",
        )

        # Commit these files
        subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=t", "add", "."], cwd=str(source_dir), check=True)
        subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-q", "-m", "add scripts"], cwd=str(source_dir), check=True)
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(source_dir), capture_output=True, text=True, check=True)
        latest_sha = res.stdout.strip().lower()

        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=latest_sha,
            primary_test="test",
            validation_status="unreviewed",
        )

        with materialize_repository(config, clone_source=source_dir) as checkout:
            assert (checkout.checkout_path / "setup.py").exists()

        # Neither hook nor script must have run
        assert not hook_marker.exists()
        assert not script_marker.exists()

    # 11. Submodules are not initialized
    def test_submodules_are_not_initialized(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        shas = _create_local_git_repo(source_dir)

        # Add a dummy .gitmodules file
        gitmodules = source_dir / ".gitmodules"
        gitmodules.write_text(
            '[submodule "sub"]\n\tpath = sub\n\turl = https://github.com/fake/submodule.git\n',
            encoding="utf-8",
        )
        (source_dir / "sub").mkdir()
        subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=t", "add", "."], cwd=str(source_dir), check=True)
        subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-q", "-m", "add submodule"], cwd=str(source_dir), check=True)
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(source_dir), capture_output=True, text=True, check=True)
        latest_sha = res.stdout.strip().lower()

        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=latest_sha,
            primary_test="test",
            validation_status="unreviewed",
        )

        with materialize_repository(config, clone_source=source_dir) as checkout:
            # Submodule directory should not be a git repo or initialized
            assert not (checkout.checkout_path / "sub" / ".git").exists()
            assert not (checkout.checkout_path / ".git" / "modules").exists()

    # 12. Checkout is cleaned up when execution context exits
    def test_checkout_cleanup_on_exit(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        shas = _create_local_git_repo(source_dir)

        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=shas[0],
            primary_test="test",
            validation_status="unreviewed",
        )

        checkout_dir: Path | None = None
        with materialize_repository(config, clone_source=source_dir) as checkout:
            checkout_dir = checkout.checkout_path
            assert checkout_dir.exists()

        assert checkout_dir is not None
        assert not checkout_dir.exists()

    def test_checkout_cleanup_on_exception(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        shas = _create_local_git_repo(source_dir)

        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=shas[0],
            primary_test="test",
            validation_status="unreviewed",
        )

        checkout_dir: Path | None = None
        with pytest.raises(RuntimeError, match="deliberate failure"):
            with materialize_repository(config, clone_source=source_dir) as checkout:
                checkout_dir = checkout.checkout_path
                assert checkout_dir.exists()
                raise RuntimeError("deliberate failure")

        assert checkout_dir is not None
        assert not checkout_dir.exists()

    # 13. Caller-owned workspace lifecycle is respected
    def test_caller_owned_workspace_lifecycle_respected(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        shas = _create_local_git_repo(source_dir)

        caller_workspace = tmp_path / "caller_managed_workspace"
        caller_workspace.mkdir()

        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=shas[0],
            primary_test="test",
            validation_status="unreviewed",
        )

        checkout_dir: Path | None = None
        with materialize_repository(
            config, workspace_dir=caller_workspace, clone_source=source_dir
        ) as checkout:
            checkout_dir = checkout.checkout_path
            assert checkout_dir.parent == caller_workspace
            assert checkout_dir.exists()

        # Caller-owned workspace directory remains intact
        assert caller_workspace.exists()
        # But the inner checkout subdirectory was cleaned up
        assert checkout_dir is not None
        assert not checkout_dir.exists()

    # 14. Source repository is not mutated
    def test_source_repository_not_mutated(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        shas = _create_local_git_repo(source_dir, num_commits=3)

        # Snapshot source state
        head_before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(source_dir), capture_output=True, text=True).stdout.strip()
        status_before = subprocess.run(["git", "status", "--porcelain"], cwd=str(source_dir), capture_output=True, text=True).stdout.strip()
        files_before = sorted(p.name for p in source_dir.iterdir())

        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=shas[0],
            primary_test="test",
            validation_status="unreviewed",
        )

        with materialize_repository(config, clone_source=source_dir):
            pass

        # Verify source state is byte-for-byte identical
        head_after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(source_dir), capture_output=True, text=True).stdout.strip()
        status_after = subprocess.run(["git", "status", "--porcelain"], cwd=str(source_dir), capture_output=True, text=True).stdout.strip()
        files_after = sorted(p.name for p in source_dir.iterdir())

        assert head_after == head_before
        assert status_after == status_before
        assert files_after == files_before

    # 15. No .mneme/ state is created
    def test_no_mneme_state_created(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        shas = _create_local_git_repo(source_dir)

        workspace_dir = tmp_path / "ws"
        workspace_dir.mkdir()

        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=shas[0],
            primary_test="test",
            validation_status="unreviewed",
        )

        with materialize_repository(
            config, workspace_dir=workspace_dir, clone_source=source_dir
        ) as checkout:
            # Neither in checkout nor in workspace should .mneme exist
            assert not (checkout.checkout_path / ".mneme").exists()
            assert not (workspace_dir / ".mneme").exists()
            assert not (source_dir / ".mneme").exists()

    # 16. No canonical Mneme module is imported for writing authority
    def test_no_canonical_authority_modules_imported(self):
        import mneme.open_architecture.execution as exec_module

        # Inspect globals/imports in the execution module
        exec_globals = vars(exec_module)
        forbidden = [
            "DecisionAuthorityService",
            "DecisionProposalStore",
            "MemoryStore",
            "JsonFileDecisionProposalStore",
            "audit",
            "enforce",
        ]
        for name in forbidden:
            assert name not in exec_globals, f"Forbidden authority component {name} found in execution module"

    # 17. Repeated checkout of same repo+SHA resolves to same source identity
    def test_repeated_checkout_same_identity(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        shas = _create_local_git_repo(source_dir, num_commits=2)
        target_sha = shas[0]

        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=target_sha,
            primary_test="test",
            validation_status="unreviewed",
        )

        resolved_shas: list[str] = []
        file_contents: list[str] = []

        for _ in range(2):
            with materialize_repository(config, clone_source=source_dir) as checkout:
                resolved_shas.append(checkout.resolved_commit_sha)
                content = (checkout.checkout_path / "file_0.txt").read_text(encoding="utf-8")
                file_contents.append(content)

        assert resolved_shas[0] == resolved_shas[1] == target_sha
        assert file_contents[0] == file_contents[1]

    # Additional: cleanup=False retains checkout
    def test_cleanup_false_retains_checkout(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        shas = _create_local_git_repo(source_dir)

        workspace_dir = tmp_path / "ws"
        workspace_dir.mkdir()

        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=shas[0],
            primary_test="test",
            validation_status="unreviewed",
        )

        checkout_dir: Path | None = None
        with materialize_repository(
            config, workspace_dir=workspace_dir, clone_source=source_dir, cleanup=False
        ) as checkout:
            checkout_dir = checkout.checkout_path
            assert checkout_dir.exists()

        assert checkout_dir is not None
        assert checkout_dir.exists()
        assert (checkout_dir / "file_0.txt").is_file()

    # Additional: git unavailable error
    def test_git_unavailable_raises_error(self, tmp_path: Path, monkeypatch):
        source_dir = tmp_path / "source"
        shas = _create_local_git_repo(source_dir)

        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=shas[0],
            primary_test="test",
            validation_status="unreviewed",
        )

        from mneme.open_architecture import execution

        def _mock_run(*args, **kwargs):
            raise FileNotFoundError("git not found")

        monkeypatch.setattr(execution.subprocess, "run", _mock_run)

        with pytest.raises(GitUnavailableError, match="not found on system PATH"):
            with materialize_repository(config, clone_source=source_dir):
                pass

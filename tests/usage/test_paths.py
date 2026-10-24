import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from mneme.usage import paths
from mneme.usage.paths import (
    UsagePathError,
    UsagePaths,
    default_usage_dir,
    validate_existing_paths,
)


def test_platform_default_paths_are_outside_the_repository_shape(tmp_path):
    assert default_usage_dir(
        platform="win32", environ={"LOCALAPPDATA": "C:/state"}, home=tmp_path
    ) == Path("C:/state/Mneme/usage")
    assert default_usage_dir(platform="darwin", environ={}, home=tmp_path) == (
        tmp_path / "Library" / "Application Support" / "Mneme" / "usage"
    )
    assert (
        default_usage_dir(
            platform="linux",
            environ={"XDG_STATE_HOME": str(tmp_path / "xdg")},
            home=tmp_path,
        )
        == tmp_path / "xdg" / "mneme" / "usage"
    )


def test_relative_xdg_state_home_is_ignored(tmp_path):
    assert (
        default_usage_dir(
            platform="linux", environ={"XDG_STATE_HOME": "relative"}, home=tmp_path
        )
        == tmp_path / ".local" / "state" / "mneme" / "usage"
    )


def test_symlinked_usage_directory_is_rejected(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not available")
    with pytest.raises(UsagePathError, match="link or reparse"):
        validate_existing_paths(UsagePaths.under(linked))


def test_windows_acl_command_removes_inheritance_and_grants_current_user(
    monkeypatch, tmp_path
):
    calls = []
    monkeypatch.setattr(paths.shutil, "which", lambda _: "icacls.exe")
    monkeypatch.setattr(paths, "_current_windows_principal", lambda: "DOMAIN\\user")
    monkeypatch.setattr(
        paths.subprocess,
        "run",
        lambda command, **kwargs: (
            calls.append((command, kwargs)) or SimpleNamespace(returncode=0)
        ),
    )
    paths._harden_windows(tmp_path, directory=True)
    command, kwargs = calls[0]
    assert command == [
        "icacls.exe",
        str(tmp_path),
        "/inheritance:r",
        "/grant:r",
        "DOMAIN\\user:(OI)(CI)F",
    ]
    assert kwargs["stdin"] is paths.subprocess.DEVNULL


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission assertion")
def test_created_directory_and_files_are_private_on_posix(tmp_path):
    directory = tmp_path / "usage"
    paths.create_secure_directory(directory)
    state = directory / "state.json"
    state.write_text("{}", encoding="utf-8")
    paths.harden_path(state, directory=False)
    assert directory.stat().st_mode & 0o777 == 0o700
    assert state.stat().st_mode & 0o777 == 0o600

"""Platform-local paths and security checks for usage state."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class UsagePathError(OSError):
    """The usage path is unsafe or cannot be secured."""


@dataclass(frozen=True)
class UsagePaths:
    directory: Path
    state: Path
    lock: Path

    @classmethod
    def under(cls, directory: str | Path) -> UsagePaths:
        root = Path(directory)
        return cls(directory=root, state=root / "state.json", lock=root / "state.lock")


def default_usage_dir(
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Select the user-local, non-repository state directory without creating it."""
    platform = sys.platform if platform is None else platform
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    if platform == "win32":
        base = environ.get("LOCALAPPDATA")
        return (Path(base) if base else home / "AppData" / "Local") / "Mneme" / "usage"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "Mneme" / "usage"
    configured = environ.get("XDG_STATE_HOME")
    base = (
        Path(configured)
        if configured and Path(configured).is_absolute()
        else home / ".local" / "state"
    )
    return base / "mneme" / "usage"


def _is_link_or_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse and attributes & reparse)


def reject_link_components(path: Path) -> None:
    """Reject symlink/junction components so state cannot escape its selected path."""
    absolute = path.absolute()
    parts = absolute.parts
    if not parts:
        raise UsagePathError("usage path is empty")
    current = Path(parts[0])
    for part in parts[1:]:
        current /= part
        if (current.exists() or current.is_symlink()) and _is_link_or_reparse(current):
            raise UsagePathError(
                f"usage path contains a link or reparse point: {current}"
            )


def validate_existing_paths(paths: UsagePaths) -> None:
    """Validate owned path types without creating, deleting, or chmodding anything."""
    reject_link_components(paths.directory)
    if paths.directory.exists() and not paths.directory.is_dir():
        raise UsagePathError(
            f"usage state directory is not a directory: {paths.directory}"
        )
    for candidate in (paths.state, paths.lock):
        if candidate.exists() or candidate.is_symlink():
            if _is_link_or_reparse(candidate):
                raise UsagePathError(
                    f"usage state path is a link or reparse point: {candidate}"
                )
            if not candidate.is_file():
                raise UsagePathError(
                    f"usage state path is not a regular file: {candidate}"
                )


def _harden_windows(path: Path, *, directory: bool) -> None:
    """Replace inherited ACLs with full control for the current Windows user."""
    executable = shutil.which("icacls.exe") or shutil.which("icacls")
    if executable is None:
        raise UsagePathError("icacls is required to secure usage state on Windows")
    principal = _current_windows_principal()
    grant = f"{principal}:{'(OI)(CI)' if directory else ''}F"
    result = subprocess.run(
        [executable, str(path), "/inheritance:r", "/grant:r", grant],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise UsagePathError(f"could not secure usage state path: {path}")


def _current_windows_principal() -> str:
    """Return the authenticated token name without trusting environment values."""
    import ctypes
    from ctypes import wintypes

    name_sam_compatible = 2
    size = wintypes.ULONG(0)
    secur32 = ctypes.WinDLL("secur32", use_last_error=True)
    secur32.GetUserNameExW(name_sam_compatible, None, ctypes.byref(size))
    if size.value == 0:
        raise UsagePathError("the current Windows account could not be identified")
    buffer = ctypes.create_unicode_buffer(size.value)
    if not secur32.GetUserNameExW(name_sam_compatible, buffer, ctypes.byref(size)):
        raise UsagePathError("the current Windows account could not be identified")
    principal = buffer.value.strip()
    if not principal:
        raise UsagePathError("the current Windows account could not be identified")
    return principal


def harden_path(path: Path, *, directory: bool) -> None:
    """Apply private permissions to one Mneme-owned directory or file."""
    if _is_link_or_reparse(path):
        raise UsagePathError(f"refusing to secure a link or reparse point: {path}")
    if os.name == "nt":
        _harden_windows(path, directory=directory)
    else:
        path.chmod(0o700 if directory else 0o600)


def create_secure_directory(path: Path) -> None:
    """Create and secure a private directory during an authorized mutation."""
    reject_link_components(path.parent)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if _is_link_or_reparse(path) or not path.is_dir():
        raise UsagePathError(f"usage directory is unsafe: {path}")
    harden_path(path, directory=True)

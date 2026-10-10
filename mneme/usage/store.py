"""Atomic, lock-protected, local-only persistence for usage measurement."""

from __future__ import annotations

import contextlib
import errno
import json
import os
import tempfile
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TypeVar

from .contracts import (
    CURRENT_POLICY_VERSION,
    ExecutionContext,
    Operation,
    Surface,
    UsageContractError,
    UsageState,
)
from .paths import (
    UsagePathError,
    UsagePaths,
    create_secure_directory,
    default_usage_dir,
    harden_path,
    validate_existing_paths,
)
from .service import incremented, serialize_state, without_expired


class UsageStoreError(RuntimeError):
    """Usage state could not be safely read or persisted."""


class UsageStateCorrupt(UsageStoreError):
    """Persisted usage state is unreadable or violates the closed schema."""


class UsageLockUnavailable(UsageStoreError):
    """The non-blocking runtime lock is currently unavailable."""


T = TypeVar("T")
_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.Lock] = {}


def _thread_lock(path: Path) -> threading.Lock:
    key = os.path.normcase(os.path.abspath(path))
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.Lock())


def _open_no_follow(path: Path, flags: int, mode: int = 0o600) -> int:
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(path, flags | no_follow, mode)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise UsagePathError(f"refusing to open symlink: {path}") from exc
        raise


def _lock_file_descriptor(fd: int, *, blocking: bool, initialize: bool) -> None:
    if os.name == "nt":
        import msvcrt

        if os.fstat(fd).st_size == 0:
            if not initialize:
                raise UsageLockUnavailable("usage state lock is invalid")
            os.write(fd, b"\0")
            os.fsync(fd)
        os.lseek(fd, 0, os.SEEK_SET)
        mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
        try:
            msvcrt.locking(fd, mode, 1)
        except OSError as exc:
            raise UsageLockUnavailable("usage state is locked") from exc
    else:
        import fcntl

        mode = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(fd, mode)
        except BlockingIOError as exc:
            raise UsageLockUnavailable("usage state is locked") from exc


def _unlock_file_descriptor(fd: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


class UsageStore:
    """Own the isolated state document and its separate stable lock file.

    Runtime recording is intentionally fail-closed for consent and fail-open
    for Mneme behavior: ``try_increment`` returns ``False`` on absent,
    disabled, stale, corrupt, unsafe, busy, or unwritable state.  Critically,
    it performs a read-only consent preflight before opening the lock file, and
    repeats that check under the lock before replacing state.
    """

    def __init__(
        self,
        directory: str | Path | None = None,
        *,
        policy_version: str = CURRENT_POLICY_VERSION,
    ) -> None:
        self.paths = UsagePaths.under(
            default_usage_dir() if directory is None else Path(directory)
        )
        self.policy_version = policy_version

    def _read_raw(self) -> UsageState | None:
        try:
            validate_existing_paths(self.paths)
            if not self.paths.state.exists():
                return None
            fd = _open_no_follow(self.paths.state, os.O_RDONLY)
            with os.fdopen(fd, "rb") as stream:
                raw_bytes = stream.read()
            raw = json.loads(raw_bytes.decode("utf-8"))
            return UsageState.from_dict(raw)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            UsageContractError,
        ) as exc:
            raise UsageStateCorrupt("usage state is unreadable or invalid") from exc

    def read(self, *, unix_seconds: float) -> UsageState | None:
        """Read and logically expire state without any filesystem mutation."""
        state = self._read_raw()
        return None if state is None else without_expired(state, unix_seconds)

    def read_raw(self) -> UsageState | None:
        """Read the validated persisted state without applying retention."""
        return self._read_raw()

    @contextlib.contextmanager
    def _locked(self, *, blocking: bool, create: bool) -> Iterator[None]:
        if create:
            create_secure_directory(self.paths.directory)
        else:
            validate_existing_paths(self.paths)
            if not self.paths.directory.is_dir() or not self.paths.lock.exists():
                raise UsageLockUnavailable("usage state lock does not exist")

        local_lock = _thread_lock(self.paths.lock)
        acquired = local_lock.acquire(blocking=blocking)
        if not acquired:
            raise UsageLockUnavailable("usage state is locked")
        fd: int | None = None
        os_lock_acquired = False
        try:
            flags = os.O_RDWR | (os.O_CREAT if create else 0)
            fd = _open_no_follow(self.paths.lock, flags)
            if create:
                harden_path(self.paths.lock, directory=False)
            _lock_file_descriptor(fd, blocking=blocking, initialize=create)
            os_lock_acquired = True
            yield
        finally:
            if fd is not None:
                try:
                    if os_lock_acquired:
                        _unlock_file_descriptor(fd)
                finally:
                    os.close(fd)
            local_lock.release()

    def _atomic_write(self, state: UsageState) -> None:
        data = serialize_state(state)
        fd, temporary_name = tempfile.mkstemp(
            prefix="state.", suffix=".tmp", dir=self.paths.directory
        )
        temporary = Path(temporary_name)
        try:
            harden_path(temporary, directory=False)
            with os.fdopen(fd, "wb") as stream:
                fd = -1
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.paths.state)
            harden_path(self.paths.state, directory=False)
            if os.name != "nt":
                directory_fd = os.open(self.paths.directory, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except BaseException:
            if fd >= 0:
                os.close(fd)
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise

    def initialize(self, state: UsageState, *, overwrite: bool = False) -> None:
        """Authorized administrative creation used by the future enable flow."""
        with self._locked(blocking=True, create=True):
            existing = self._read_raw()
            if existing is not None and not overwrite:
                raise UsageStoreError("usage state already exists")
            self._atomic_write(state)

    def update_administratively(
        self,
        transform: Callable[[UsageState], UsageState],
        *,
        unix_seconds: float,
    ) -> UsageState:
        """Serialize an explicit local administration mutation under the lock."""
        with self._locked(blocking=True, create=False):
            state = self._read_raw()
            if state is None:
                raise UsageStoreError("usage state does not exist")
            retained = without_expired(state, unix_seconds)
            updated = transform(retained)
            if not isinstance(updated, UsageState):
                raise TypeError("usage state transform must return UsageState")
            if updated != state:
                self._atomic_write(updated)
            return updated

    def update_if_consented(
        self,
        transform: Callable[[UsageState], UsageState],
        *,
        unix_seconds: float,
    ) -> UsageState:
        """Apply an explicit mutation only after consent is rechecked locked."""
        # Read-only preflight avoids creating a lock or directory for absent,
        # disabled, stale, or corrupt consent.
        preflight = self._read_raw()
        if preflight is None or not preflight.has_current_consent(self.policy_version):
            raise UsageStoreError("current usage consent is required")
        with self._locked(blocking=True, create=False):
            current = self._read_raw()
            if current is None or not current.has_current_consent(self.policy_version):
                raise UsageStoreError("current usage consent is required")
            retained = without_expired(current, unix_seconds)
            updated = transform(retained)
            if not isinstance(updated, UsageState):
                raise TypeError("usage state transform must return UsageState")
            if updated != current:
                self._atomic_write(updated)
            return updated

    def purge(self) -> bool:
        """Delete all Mneme-owned usage state; absent state is a write-free no-op."""
        validate_existing_paths(self.paths)
        if not self.paths.directory.exists():
            return False
        if not self.paths.state.exists() and not self.paths.lock.exists():
            return False
        with self._locked(blocking=True, create=True):
            try:
                self.paths.state.unlink()
            except FileNotFoundError:
                pass
        # The separate lock cannot be unlinked while held on Windows.  Once
        # state is gone, a racing recorder's locked consent recheck fails.
        try:
            self.paths.lock.unlink()
        except FileNotFoundError:
            pass
        try:
            self.paths.directory.rmdir()
        except OSError:
            # Preserve any unexpected user-owned entry rather than deleting a
            # directory recursively.  All sensitive Mneme state is already gone.
            pass
        return True

    def try_increment(
        self,
        *,
        unix_seconds: float,
        surface: Surface,
        operation: Operation,
        execution_context: ExecutionContext,
    ) -> bool:
        """Best-effort runtime increment with zero writes before consent passes."""
        try:
            preflight = self._read_raw()
            if preflight is None or not preflight.has_current_consent(
                self.policy_version
            ):
                return False
            # No lock file or directory has been opened or created before this
            # point.  Current consent implies an administratively initialized
            # state directory and stable lock file.
            with self._locked(blocking=False, create=False):
                current = self._read_raw()
                if current is None or not current.has_current_consent(
                    self.policy_version
                ):
                    return False
                retained = without_expired(current, unix_seconds)
                updated = incremented(
                    retained,
                    unix_seconds=unix_seconds,
                    surface=surface,
                    operation=operation,
                    execution_context=execution_context,
                )
                self._atomic_write(updated)
                return True
        except Exception:  # noqa: BLE001 - operational measurement must never escape
            # Usage measurement must never alter an operational result.  The
            # explicit administration surface uses raising methods above so a
            # person can diagnose or recover with purge later.
            return False

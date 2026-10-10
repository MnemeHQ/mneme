"""Local-only U1 administration and best-effort runtime recording."""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import TextIO

from mneme import __version__

from .contracts import (
    CURRENT_POLICY_VERSION,
    Operation,
    Surface,
    UsageState,
)
from .service import (
    disabled_state,
    execution_context,
    materialize_pending_snapshots,
    new_enabled_state,
    preview_bytes,
)
from .store import UsageStore

INTERNAL_HOOK_CHECK_ENV = "MNEME_USAGE_INTERNAL_HOOK_CHECK"

CONSENT_NOTICE = """Mneme local usage measurement

This optional feature stores only allowlisted aggregate counts in your local
user profile. It does not collect source code, prompts, arguments, paths,
decision content, verdicts, errors, or stable cross-epoch identifiers.

U1 never sends data over the network. Preview materializes the exact pending
payload bytes a separately authorized future U2 submit command could send.
Local aggregate and snapshot retention is at most 35 days. Disable stops new
counts; purge removes all local usage state, including consent and the secret.
"""


def _now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _existing_or_new_enabled(state: UsageState | None) -> UsageState:
    if state is None or state.secret_hex is None:
        return new_enabled_state(accepted_at=_now_iso())
    return replace(
        state,
        consent=replace(
            state.consent,
            enabled=True,
            policy_version=CURRENT_POLICY_VERSION,
            accepted_at=_now_iso(),
        )
        if state.consent is not None
        else new_enabled_state(
            accepted_at=_now_iso(), secret=bytes.fromhex(state.secret_hex)
        ).consent,
    )


def _output(stream: TextIO | None, fallback: TextIO) -> TextIO:
    return fallback if stream is None else stream


def enable(
    store: UsageStore, *, stdout: TextIO | None = None, stderr: TextIO | None = None
) -> int:
    import sys

    stdout = _output(stdout, sys.stdout)
    stderr = _output(stderr, sys.stderr)
    print(CONSENT_NOTICE.rstrip(), file=stdout)
    try:
        existing = store.read_raw()
        if existing is None:
            store.initialize(_existing_or_new_enabled(None))
        else:
            store.update_administratively(
                _existing_or_new_enabled, unix_seconds=time.time()
            )
    except Exception as exc:  # noqa: BLE001 - administration reports every failure
        print(f"ERROR: could not enable usage measurement: {exc}", file=stderr)
        return 2
    print(file=stdout)
    print("Usage measurement enabled (manual, local-only).", file=stdout)
    return 0


def disable(
    store: UsageStore, *, stdout: TextIO | None = None, stderr: TextIO | None = None
) -> int:
    import sys

    stdout = _output(stdout, sys.stdout)
    stderr = _output(stderr, sys.stderr)
    try:
        state = store.read_raw()
        if state is None:
            print("Usage measurement is disabled.", file=stdout)
            return 0
        store.update_administratively(disabled_state, unix_seconds=time.time())
    except Exception as exc:  # noqa: BLE001 - administration reports every failure
        print(f"ERROR: could not disable usage measurement: {exc}", file=stderr)
        return 2
    print(
        "Usage measurement disabled. Retained local data was not purged.", file=stdout
    )
    return 0


def status(
    store: UsageStore, *, stdout: TextIO | None = None, stderr: TextIO | None = None
) -> int:
    """Report logical state without materializing, pruning, or writing."""
    import sys

    stdout = _output(stdout, sys.stdout)
    stderr = _output(stderr, sys.stderr)
    try:
        state = store.read(unix_seconds=time.time())
    except Exception as exc:  # noqa: BLE001 - corrupt/unsafe state must be diagnosable
        print(f"Usage measurement state: unreadable ({exc})", file=stderr)
        print("Run `mneme usage purge` to remove the corrupt local state.", file=stderr)
        return 2
    if state is None or state.consent is None:
        print("Usage measurement: disabled (no consent recorded)", file=stdout)
        print("Network submission: unavailable in U1", file=stdout)
        return 0
    if not state.consent.enabled:
        label = "disabled"
    elif not state.has_current_consent():
        label = "disabled (consent is stale)"
    else:
        label = "enabled"
    print(f"Usage measurement: {label}", file=stdout)
    print(f"Policy version: {state.consent.policy_version}", file=stdout)
    print(f"Submission mode: {state.consent.submission_mode.value}", file=stdout)
    print("Local retention: at most 35 days", file=stdout)
    retained_epochs = sorted(
        {item.identifier_epoch for item in state.counters}
        | {item.identifier_epoch for item in state.snapshots}
    )
    print(
        "Retained epochs: "
        + (
            ", ".join(str(epoch) for epoch in retained_epochs)
            if retained_epochs
            else "none"
        ),
        file=stdout,
    )
    print("Scheduler: unavailable in U1", file=stdout)
    print(
        f"Unsent aggregates: {'yes' if state.counters or state.snapshots else 'no'}",
        file=stdout,
    )
    return 0


def preview(
    store: UsageStore, *, stdout: TextIO | None = None, stderr: TextIO | None = None
) -> int:
    """Materialize and print exact pending payload bytes; never use a network."""
    import sys

    stdout = _output(stdout, sys.stdout)
    stderr = _output(stderr, sys.stderr)
    try:
        state = store.update_if_consented(
            lambda current: materialize_pending_snapshots(
                current, mneme_version=__version__
            ),
            unix_seconds=time.time(),
        )
    except Exception as exc:  # noqa: BLE001 - administration reports every failure
        print(f"ERROR: preview requires current consent: {exc}", file=stderr)
        return 2
    for payload in preview_bytes(state):
        # Canonical payloads are ASCII JSON terminated by one newline.
        stdout.write(payload.decode("ascii"))
    return 0


def purge(
    store: UsageStore, *, stdout: TextIO | None = None, stderr: TextIO | None = None
) -> int:
    import sys

    stdout = _output(stdout, sys.stdout)
    stderr = _output(stderr, sys.stderr)
    try:
        removed = store.purge()
    except Exception as exc:  # noqa: BLE001 - purge must report every failure
        print(f"ERROR: could not purge usage state: {exc}", file=stderr)
        return 2
    print(
        "Local usage state purged." if removed else "No local usage state exists.",
        file=stdout,
    )
    return 0


def record(
    *,
    surface: Surface,
    operation: Operation,
    environ: Mapping[str, str] | None = None,
    unix_seconds: float | None = None,
) -> bool:
    """Best-effort operational adapter; callers never observe measurement errors."""
    try:
        environ = os.environ if environ is None else environ
        if environ.get(INTERNAL_HOOK_CHECK_ENV) == "1":
            return False
        return UsageStore().try_increment(
            unix_seconds=time.time() if unix_seconds is None else unix_seconds,
            surface=surface,
            operation=operation,
            execution_context=execution_context(environ),
        )
    except Exception:  # noqa: BLE001 - measurement is an unconditional fail-open edge
        return False


def record_cli(operation: Operation) -> bool:
    return record(surface=Surface.CLI, operation=operation)


def record_mcp(operation: Operation) -> bool:
    return record(surface=Surface.MCP, operation=operation)


def record_hook(operation: Operation) -> bool:
    return record(surface=Surface.HOOK, operation=operation)

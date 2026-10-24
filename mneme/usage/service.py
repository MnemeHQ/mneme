"""Pure transformations for ADR-032 usage state and payloads."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace

from .contracts import (
    CURRENT_POLICY_VERSION,
    MAX_COUNT,
    PAYLOAD_SCHEMA_VERSION,
    Aggregate,
    Consent,
    ExecutionContext,
    Operation,
    Snapshot,
    SubmissionMode,
    Surface,
    UsageContractError,
    UsageState,
    canonical_payload_bytes,
    merge_aggregates,
)

SECONDS_PER_DAY = 86_400
DAYS_PER_EPOCH = 30
RETENTION_DAYS = 35
_INSTANCE_DOMAIN = b"mneme:usage:instance:v1:"
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.|$)")


def utc_day(unix_seconds: float) -> int:
    if isinstance(unix_seconds, bool) or not isinstance(unix_seconds, (int, float)):
        raise TypeError("unix_seconds must be numeric")
    if unix_seconds < 0:
        raise ValueError("times before the Unix epoch are not supported")
    return int(unix_seconds // SECONDS_PER_DAY)


def identifier_epoch(unix_seconds: float) -> int:
    """Pinned UTC epoch: floor(unix_seconds / (30 * 86400))."""
    return utc_day(unix_seconds) // DAYS_PER_EPOCH


def weekly_bucket(unix_seconds: float) -> int:
    day_within_epoch = utc_day(unix_seconds) % DAYS_PER_EPOCH
    return day_within_epoch // 7


def aggregate_retention_deadline_day(aggregate: Aggregate) -> int:
    """Conservative deadline ensuring no aggregate can exceed 35 days.

    The closed local representation intentionally has no event timestamps.
    Retiring a weekly bucket 35 days after its first possible UTC day can
    discard its youngest counts up to six days early, but never retains an
    invocation beyond ADR-032's maximum.
    """
    bucket_start = (
        aggregate.identifier_epoch * DAYS_PER_EPOCH + aggregate.weekly_bucket * 7
    )
    return bucket_start + RETENTION_DAYS


def snapshot_retention_deadline_day(snapshot: Snapshot) -> int:
    payload = snapshot.payload
    epoch = int(payload["identifier_epoch"])
    rows = payload["aggregates"]
    return min(
        epoch * DAYS_PER_EPOCH + int(row["weekly_bucket"]) * 7 + RETENTION_DAYS
        for row in rows
    )


def without_expired(state: UsageState, unix_seconds: float) -> UsageState:
    """Return a logically filtered copy; never mutates or persists state."""
    today = utc_day(unix_seconds)
    return replace(
        state,
        counters=tuple(
            aggregate
            for aggregate in state.counters
            if today < aggregate_retention_deadline_day(aggregate)
        ),
        snapshots=tuple(
            snapshot
            for snapshot in state.snapshots
            if today < snapshot_retention_deadline_day(snapshot)
        ),
    )


def derive_instance_id(secret: bytes, epoch: int) -> str:
    if len(secret) != 32:
        raise UsageContractError("instance secret must contain exactly 256 bits")
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
        raise UsageContractError("identifier epoch must be a non-negative integer")
    digest = hmac.new(
        secret, _INSTANCE_DOMAIN + str(epoch).encode("ascii"), hashlib.sha256
    ).digest()
    return digest[:16].hex()


def major_minor(version: str) -> str:
    match = _VERSION_RE.match(version)
    if match is None:
        raise UsageContractError(f"invalid Mneme version {version!r}")
    return f"{match.group(1)}.{match.group(2)}"


def new_enabled_state(
    *,
    accepted_at: str,
    secret: bytes | None = None,
    policy_version: str = CURRENT_POLICY_VERSION,
) -> UsageState:
    """Build explicit manual consent state; persistence belongs to the caller."""
    secret = os.urandom(32) if secret is None else secret
    if len(secret) != 32:
        raise UsageContractError("instance secret must contain exactly 256 bits")
    return UsageState(
        consent=Consent(
            enabled=True,
            policy_version=policy_version,
            accepted_at=accepted_at,
            submission_mode=SubmissionMode.MANUAL,
        ),
        secret_hex=secret.hex(),
    )


def disabled_state(state: UsageState) -> UsageState:
    if state.consent is None:
        return state
    return replace(state, consent=replace(state.consent, enabled=False))


def incremented(
    state: UsageState,
    *,
    unix_seconds: float,
    surface: Surface,
    operation: Operation,
    execution_context: ExecutionContext,
    amount: int = 1,
) -> UsageState:
    """Increment one closed aggregate in memory, saturating the bounded count."""
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 1:
        raise UsageContractError("increment amount must be a positive integer")
    incoming = Aggregate(
        identifier_epoch=identifier_epoch(unix_seconds),
        weekly_bucket=weekly_bucket(unix_seconds),
        surface=surface,
        operation=operation,
        execution_context=execution_context,
        count=min(amount, MAX_COUNT),
    )
    return replace(state, counters=merge_aggregates((*state.counters, incoming)))


def _payload_for_epoch(
    state: UsageState,
    epoch: int,
    counters: Iterable[Aggregate],
    *,
    mneme_version: str,
    random_bytes: Callable[[int], bytes],
) -> bytes:
    if state.secret_hex is None:
        raise UsageContractError("cannot create a payload without a local secret")
    payload_id_bytes = random_bytes(16)
    if len(payload_id_bytes) != 16:
        raise UsageContractError("payload identifier source must return 128 bits")
    rows = sorted(counters)
    payload = {
        "schema_version": PAYLOAD_SCHEMA_VERSION,
        "payload_id": payload_id_bytes.hex(),
        "identifier_epoch": epoch,
        "instance_id": derive_instance_id(bytes.fromhex(state.secret_hex), epoch),
        "mneme_major_minor_version": major_minor(mneme_version),
        "aggregates": [row.to_payload_dict() for row in rows],
    }
    return canonical_payload_bytes(payload)


def materialize_pending_snapshots(
    state: UsageState,
    *,
    mneme_version: str,
    random_bytes: Callable[[int], bytes] = os.urandom,
) -> UsageState:
    """Freeze at most one immutable payload per epoch with unfrozen counters."""
    pending_epochs = {snapshot.identifier_epoch for snapshot in state.snapshots}
    by_epoch: dict[int, list[Aggregate]] = {}
    remaining: list[Aggregate] = []
    for aggregate in state.counters:
        if aggregate.identifier_epoch in pending_epochs:
            remaining.append(aggregate)
        else:
            by_epoch.setdefault(aggregate.identifier_epoch, []).append(aggregate)
    used_payload_ids = {snapshot.payload_id for snapshot in state.snapshots}
    created: list[Snapshot] = []
    for epoch, counters in sorted(by_epoch.items()):
        for _attempt in range(16):
            snapshot = Snapshot(
                _payload_for_epoch(
                    state,
                    epoch,
                    counters,
                    mneme_version=mneme_version,
                    random_bytes=random_bytes,
                )
            )
            if snapshot.payload_id not in used_payload_ids:
                used_payload_ids.add(snapshot.payload_id)
                created.append(snapshot)
                break
        else:
            raise UsageContractError("could not generate a unique payload identifier")
    return replace(
        state,
        counters=tuple(remaining),
        snapshots=tuple(
            sorted((*state.snapshots, *created), key=lambda item: item.identifier_epoch)
        ),
    )


def preview_bytes(state: UsageState) -> tuple[bytes, ...]:
    """Return immutable pending payloads exactly, one NDJSON line per epoch."""
    return tuple(
        snapshot.payload_bytes
        for snapshot in sorted(state.snapshots, key=lambda item: item.identifier_epoch)
    )


def execution_context(environ: Mapping[str, str]) -> ExecutionContext:
    markers = ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE", "TF_BUILD")
    if any(marker in environ for marker in markers):
        return ExecutionContext.CI
    return ExecutionContext.INTERACTIVE


def serialize_state(state: UsageState) -> bytes:
    return (json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )

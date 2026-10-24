from dataclasses import replace

from mneme.usage.contracts import (
    Aggregate,
    ExecutionContext,
    Operation,
    Surface,
)
from mneme.usage.service import (
    SECONDS_PER_DAY,
    derive_instance_id,
    execution_context,
    identifier_epoch,
    incremented,
    materialize_pending_snapshots,
    new_enabled_state,
    preview_bytes,
    weekly_bucket,
    without_expired,
)


def test_epoch_and_incomplete_fifth_bucket_boundaries():
    assert identifier_epoch(0) == 0
    assert identifier_epoch(30 * SECONDS_PER_DAY - 1) == 0
    assert identifier_epoch(30 * SECONDS_PER_DAY) == 1
    assert weekly_bucket(27 * SECONDS_PER_DAY) == 3
    assert weekly_bucket(28 * SECONDS_PER_DAY) == 4
    assert weekly_bucket(29 * SECONDS_PER_DAY + 86_399) == 4
    assert weekly_bucket(30 * SECONDS_PER_DAY) == 0


def test_execution_context_records_only_coarse_marker_presence():
    assert execution_context({}) == ExecutionContext.INTERACTIVE
    assert execution_context({"CI": "false"}) == ExecutionContext.CI


def test_instance_identifier_has_pinned_hmac_vector_and_rotates():
    secret = bytes(range(32))
    assert derive_instance_id(secret, 0) == "cdf6e16c4f7a98336a0c712768e89ebd"
    assert derive_instance_id(secret, 1) == "c9fb0bdd7b83c175d96c39814f4c22ad"
    assert derive_instance_id(secret, 0) != derive_instance_id(secret, 1)


def test_materialization_separates_epochs_and_freezes_exact_bytes():
    state = new_enabled_state(
        accepted_at="2026-10-09T00:00:00Z", secret=bytes(range(32))
    )
    state = incremented(
        state,
        unix_seconds=1,
        surface=Surface.CLI,
        operation=Operation.CLI_CHECK,
        execution_context=ExecutionContext.INTERACTIVE,
    )
    state = incremented(
        state,
        unix_seconds=30 * SECONDS_PER_DAY,
        surface=Surface.MCP,
        operation=Operation.MCP_GET,
        execution_context=ExecutionContext.CI,
    )
    identifiers = iter((b"a" * 16, b"b" * 16))
    frozen = materialize_pending_snapshots(
        state, mneme_version="0.10.7+build", random_bytes=lambda _: next(identifiers)
    )

    assert frozen.counters == ()
    assert [item.identifier_epoch for item in frozen.snapshots] == [0, 1]
    assert [item.payload_id for item in frozen.snapshots] == ["61" * 16, "62" * 16]
    assert (
        frozen.snapshots[0].payload["instance_id"]
        != frozen.snapshots[1].payload["instance_id"]
    )
    assert all(
        item.payload["mneme_major_minor_version"] == "0.10" for item in frozen.snapshots
    )
    first_preview = preview_bytes(frozen)
    assert first_preview == preview_bytes(
        materialize_pending_snapshots(
            frozen, mneme_version="9.9.9", random_bytes=lambda _: b"z" * 16
        )
    )


def test_pending_epoch_keeps_later_counts_unfrozen_until_snapshot_clears():
    base = new_enabled_state(accepted_at="2026-10-09T00:00:00Z", secret=b"s" * 32)
    base = incremented(
        base,
        unix_seconds=1,
        surface=Surface.CLI,
        operation=Operation.CLI_CHECK,
        execution_context=ExecutionContext.INTERACTIVE,
    )
    first = materialize_pending_snapshots(
        base, mneme_version="0.10.0", random_bytes=lambda _: b"1" * 16
    )
    with_later_count = incremented(
        first,
        unix_seconds=2,
        surface=Surface.CLI,
        operation=Operation.CLI_CHECK,
        execution_context=ExecutionContext.INTERACTIVE,
    )
    still_pending = materialize_pending_snapshots(
        with_later_count,
        mneme_version="0.10.0",
        random_bytes=lambda _: b"2" * 16,
    )
    assert still_pending.snapshots == first.snapshots
    assert still_pending.counters[0].count == 1

    acknowledged = replace(still_pending, snapshots=())
    second = materialize_pending_snapshots(
        acknowledged,
        mneme_version="0.10.0",
        random_bytes=lambda _: b"2" * 16,
    )
    assert second.snapshots[0].payload_id != first.snapshots[0].payload_id


def test_logical_retention_is_conservative_and_nonmutating():
    state = new_enabled_state(accepted_at="2026-10-09T00:00:00Z", secret=b"s" * 32)
    aggregate = Aggregate(
        identifier_epoch=0,
        weekly_bucket=0,
        surface=Surface.CLI,
        operation=Operation.CLI_CHECK,
        execution_context=ExecutionContext.INTERACTIVE,
    )
    state = replace(state, counters=(aggregate,))
    assert without_expired(state, 35 * SECONDS_PER_DAY - 1).counters == (aggregate,)
    assert without_expired(state, 35 * SECONDS_PER_DAY).counters == ()
    assert state.counters == (aggregate,)


def test_materialization_retries_a_pending_payload_id_collision():
    state = new_enabled_state(accepted_at="2026-10-09T00:00:00Z", secret=b"s" * 32)
    for at in (1, 30 * SECONDS_PER_DAY):
        state = incremented(
            state,
            unix_seconds=at,
            surface=Surface.CLI,
            operation=Operation.CLI_CHECK,
            execution_context=ExecutionContext.INTERACTIVE,
        )
    identifiers = iter((b"a" * 16, b"a" * 16, b"b" * 16))
    frozen = materialize_pending_snapshots(
        state, mneme_version="0.10.0", random_bytes=lambda _: next(identifiers)
    )
    assert [snapshot.payload_id for snapshot in frozen.snapshots] == [
        "61" * 16,
        "62" * 16,
    ]

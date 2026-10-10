import json

import pytest

from mneme.usage.contracts import (
    MAX_COUNT,
    Aggregate,
    ExecutionContext,
    Operation,
    Surface,
    UsageContractError,
    UsageState,
    validate_payload,
)
from mneme.usage.service import incremented


def test_closed_operation_rejects_unknown_and_cross_surface_values():
    with pytest.raises(ValueError):
        Operation("user.supplied.value")
    with pytest.raises(UsageContractError):
        Aggregate(
            identifier_epoch=1,
            weekly_bucket=0,
            surface=Surface.CLI,
            operation=Operation.MCP_GET,
            execution_context=ExecutionContext.INTERACTIVE,
        )


def test_state_schema_rejects_unknown_fields():
    raw = UsageState().to_dict()
    raw["repository"] = "must-not-enter-state"
    with pytest.raises(UsageContractError, match="closed schema"):
        UsageState.from_dict(raw)


def test_aggregate_schema_rejects_free_form_and_extra_fields():
    raw = {
        "schema_version": "1",
        "identifier_epoch": 1,
        "weekly_bucket": 0,
        "surface": "cli",
        "operation": "check --input secret.py",
        "execution_context": "interactive",
        "count": 1,
    }
    with pytest.raises(UsageContractError, match="unknown operation"):
        Aggregate.from_state_dict(raw)
    raw["path"] = "secret.py"
    with pytest.raises(UsageContractError, match="closed schema"):
        Aggregate.from_state_dict(raw)


def test_increment_saturates_bounded_count():
    state = UsageState(
        counters=(
            Aggregate(
                identifier_epoch=0,
                weekly_bucket=0,
                surface=Surface.CLI,
                operation=Operation.CLI_CHECK,
                execution_context=ExecutionContext.CI,
                count=MAX_COUNT,
            ),
        )
    )
    updated = incremented(
        state,
        unix_seconds=1,
        surface=Surface.CLI,
        operation=Operation.CLI_CHECK,
        execution_context=ExecutionContext.CI,
    )
    assert updated.counters[0].count == MAX_COUNT


def test_state_roundtrip_is_deterministic():
    state = UsageState(
        counters=(
            Aggregate(
                identifier_epoch=7,
                weekly_bucket=4,
                surface=Surface.HOOK,
                operation=Operation.HOOK_KIRO_PRE_TOOL_USE,
                execution_context=ExecutionContext.UNKNOWN,
                count=3,
            ),
        )
    )
    encoded = json.dumps(state.to_dict(), sort_keys=True)
    assert UsageState.from_dict(json.loads(encoded)) == state


def test_payload_rejects_unknown_fields_duplicates_and_out_of_range_counts():
    payload = {
        "schema_version": "1",
        "payload_id": "a" * 32,
        "identifier_epoch": 4,
        "instance_id": "b" * 32,
        "mneme_major_minor_version": "0.10",
        "aggregates": [
            {
                "weekly_bucket": 0,
                "surface": "cli",
                "operation": "check",
                "execution_context": "interactive",
                "count": 1,
            }
        ],
    }
    validate_payload(payload)
    with pytest.raises(UsageContractError, match="closed schema"):
        validate_payload({**payload, "repository": "forbidden"})
    with pytest.raises(UsageContractError, match="duplicate"):
        validate_payload({**payload, "aggregates": payload["aggregates"] * 2})
    bad_row = {**payload["aggregates"][0], "count": MAX_COUNT + 1}
    with pytest.raises(UsageContractError, match="between"):
        validate_payload({**payload, "aggregates": [bad_row]})

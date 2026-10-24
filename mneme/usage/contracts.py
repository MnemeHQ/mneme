"""Closed, versioned contracts for ADR-032 local usage measurement."""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

STATE_VERSION = 1
PAYLOAD_SCHEMA_VERSION = "1"
CURRENT_POLICY_VERSION = "1"
MAX_COUNT = 2_147_483_647
MAX_PAYLOAD_BYTES = 256 * 1024

_HEX_128_RE = re.compile(r"^[0-9a-f]{32}$")
_SECRET_RE = re.compile(r"^[0-9a-f]{64}$")
_MAJOR_MINOR_RE = re.compile(r"^[0-9]+\.[0-9]+$")
_POLICY_VERSION_RE = re.compile(r"^[0-9]+$")


class UsageContractError(ValueError):
    """A persisted or generated usage document violates the closed contract."""


class Surface(StrEnum):
    CLI = "cli"
    MCP = "mcp"
    HOOK = "hook"


class ExecutionContext(StrEnum):
    INTERACTIVE = "interactive"
    CI = "ci"
    UNKNOWN = "unknown"


class SubmissionMode(StrEnum):
    # U1 implements local manual administration only.  Weekly scheduling and
    # submission remain U2 and are intentionally absent from this enum.
    MANUAL = "manual"


class Operation(StrEnum):
    # Substantive CLI commands.  Administrative usage commands, help,
    # version, parser failures, benchmark, research, and MCP startup are not
    # members and therefore cannot be persisted accidentally.
    CLI_INIT = "init"
    CLI_SETUP = "setup"
    CLI_LIST_DECISIONS = "list_decisions"
    CLI_ADD_DECISION = "add_decision"
    CLI_TEST_QUERY = "test_query"
    CLI_CHECK = "check"
    CLI_AUDIT = "audit"
    CLI_PROTECT_LIST = "protect.list"
    CLI_PROTECT_STATUS = "protect.status"
    CLI_PROTECT_VALIDATE = "protect.validate"
    CLI_PROTECT_ACTIVATE = "protect.activate"
    CLI_CURSOR_GENERATE = "cursor.generate"
    CLI_ADR_IMPORT = "adr.import"
    CLI_EVENTCATALOG_IMPORT = "eventcatalog.import"
    CLI_DECISION_INDEX_MIGRATE = "decision_index.migrate"
    CLI_DECISION_PROPOSALS = "decision.proposals"
    CLI_DECISION_SHOW = "decision.show"
    CLI_DECISION_ACCEPT = "decision.accept"
    CLI_DECISION_REJECT = "decision.reject"

    # The exact frozen ADR-027 MCP surface.
    MCP_PROPOSE = "decision.propose"
    MCP_PROPOSE_BATCH = "decision.propose_batch"
    MCP_GET = "decision.get"
    MCP_SEARCH = "decision.search"
    MCP_APPLICABLE_TO = "decision.applicable_to"
    MCP_TRACE = "decision.trace"

    # Supported adapter boundaries.  Adapter identity is part of the closed
    # operation name; no user-supplied hook name is ever persisted.
    HOOK_CLAUDE_CODE_SESSION_START = "claude_code.session_start"
    HOOK_CLAUDE_CODE_PRE_TOOL_USE = "claude_code.pre_tool_use"
    HOOK_CLAUDE_CODE_STOP = "claude_code.stop"
    HOOK_CODEX_CLI_SESSION_START = "codex_cli.session_start"
    HOOK_CODEX_CLI_PRE_TOOL_USE = "codex_cli.pre_tool_use"
    HOOK_CODEX_CLI_STOP = "codex_cli.stop"
    HOOK_KIRO_PRE_TOOL_USE = "kiro.pre_tool_use"


CLI_OPERATIONS = frozenset(
    {
        Operation.CLI_INIT,
        Operation.CLI_SETUP,
        Operation.CLI_LIST_DECISIONS,
        Operation.CLI_ADD_DECISION,
        Operation.CLI_TEST_QUERY,
        Operation.CLI_CHECK,
        Operation.CLI_AUDIT,
        Operation.CLI_PROTECT_LIST,
        Operation.CLI_PROTECT_STATUS,
        Operation.CLI_PROTECT_VALIDATE,
        Operation.CLI_PROTECT_ACTIVATE,
        Operation.CLI_CURSOR_GENERATE,
        Operation.CLI_ADR_IMPORT,
        Operation.CLI_EVENTCATALOG_IMPORT,
        Operation.CLI_DECISION_INDEX_MIGRATE,
        Operation.CLI_DECISION_PROPOSALS,
        Operation.CLI_DECISION_SHOW,
        Operation.CLI_DECISION_ACCEPT,
        Operation.CLI_DECISION_REJECT,
    }
)
MCP_OPERATIONS = frozenset(
    {
        Operation.MCP_PROPOSE,
        Operation.MCP_PROPOSE_BATCH,
        Operation.MCP_GET,
        Operation.MCP_SEARCH,
        Operation.MCP_APPLICABLE_TO,
        Operation.MCP_TRACE,
    }
)
HOOK_OPERATIONS = frozenset(
    {
        Operation.HOOK_CLAUDE_CODE_SESSION_START,
        Operation.HOOK_CLAUDE_CODE_PRE_TOOL_USE,
        Operation.HOOK_CLAUDE_CODE_STOP,
        Operation.HOOK_CODEX_CLI_SESSION_START,
        Operation.HOOK_CODEX_CLI_PRE_TOOL_USE,
        Operation.HOOK_CODEX_CLI_STOP,
        Operation.HOOK_KIRO_PRE_TOOL_USE,
    }
)
OPERATIONS_BY_SURFACE = {
    Surface.CLI: CLI_OPERATIONS,
    Surface.MCP: MCP_OPERATIONS,
    Surface.HOOK: HOOK_OPERATIONS,
}


def _require_exact_keys(raw: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(raw)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise UsageContractError(
            f"{label} fields do not match the closed schema "
            f"(missing={missing}, extra={extra})"
        )


def _require_object(raw: object, label: str) -> Mapping[str, Any]:
    if not isinstance(raw, dict):
        raise UsageContractError(f"{label} must be an object")
    return raw


def _require_int(value: object, label: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UsageContractError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise UsageContractError(f"{label} must be between {minimum} and {maximum}")
    return value


def _enum_value(enum_type: type[StrEnum], value: object, label: str) -> StrEnum:
    if not isinstance(value, str):
        raise UsageContractError(f"{label} must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise UsageContractError(f"unknown {label} {value!r}") from exc


@dataclass(frozen=True)
class Consent:
    enabled: bool
    policy_version: str
    accepted_at: str
    submission_mode: SubmissionMode = SubmissionMode.MANUAL

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise UsageContractError("consent.enabled must be a boolean")
        if not isinstance(self.policy_version, str) or not _POLICY_VERSION_RE.fullmatch(
            self.policy_version
        ):
            raise UsageContractError("consent.policy_version must be a numeric version")
        if not isinstance(self.accepted_at, str):
            raise UsageContractError("consent.accepted_at must be a UTC timestamp")
        try:
            datetime.strptime(self.accepted_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=UTC
            )
        except ValueError as exc:
            raise UsageContractError(
                "consent.accepted_at must be an ISO 8601 UTC timestamp"
            ) from exc
        if not isinstance(self.submission_mode, SubmissionMode):
            raise UsageContractError("consent.submission_mode is not supported")

    def is_current(self, policy_version: str = CURRENT_POLICY_VERSION) -> bool:
        return self.enabled and self.policy_version == policy_version

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "policy_version": self.policy_version,
            "accepted_at": self.accepted_at,
            "submission_mode": self.submission_mode.value,
        }

    @classmethod
    def from_dict(cls, raw: object) -> Consent:
        obj = _require_object(raw, "consent")
        _require_exact_keys(
            obj,
            {"enabled", "policy_version", "accepted_at", "submission_mode"},
            "consent",
        )
        return cls(
            enabled=obj["enabled"],
            policy_version=obj["policy_version"],
            accepted_at=obj["accepted_at"],
            submission_mode=_enum_value(
                SubmissionMode, obj["submission_mode"], "submission mode"
            ),
        )


@dataclass(frozen=True, order=True)
class Aggregate:
    identifier_epoch: int
    weekly_bucket: int
    surface: Surface
    operation: Operation
    execution_context: ExecutionContext
    schema_version: str = PAYLOAD_SCHEMA_VERSION
    count: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.surface, Surface):
            raise UsageContractError("aggregate.surface is not supported")
        if not isinstance(self.operation, Operation):
            raise UsageContractError("aggregate.operation is not supported")
        if not isinstance(self.execution_context, ExecutionContext):
            raise UsageContractError("aggregate.execution_context is not supported")
        _require_int(
            self.identifier_epoch,
            "aggregate.identifier_epoch",
            minimum=0,
            maximum=2**63 - 1,
        )
        _require_int(
            self.weekly_bucket,
            "aggregate.weekly_bucket",
            minimum=0,
            maximum=4,
        )
        _require_int(self.count, "aggregate.count", minimum=1, maximum=MAX_COUNT)
        if self.schema_version != PAYLOAD_SCHEMA_VERSION:
            raise UsageContractError("aggregate.schema_version is not supported")
        if self.operation not in OPERATIONS_BY_SURFACE[self.surface]:
            raise UsageContractError(
                f"operation {self.operation.value!r} is not valid for "
                f"surface {self.surface.value!r}"
            )

    @property
    def key(self) -> tuple[str, int, int, Surface, Operation, ExecutionContext]:
        return (
            self.schema_version,
            self.identifier_epoch,
            self.weekly_bucket,
            self.surface,
            self.operation,
            self.execution_context,
        )

    def with_count(self, count: int) -> Aggregate:
        return replace(self, count=count)

    def to_state_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "identifier_epoch": self.identifier_epoch,
            "weekly_bucket": self.weekly_bucket,
            "surface": self.surface.value,
            "operation": self.operation.value,
            "execution_context": self.execution_context.value,
            "count": self.count,
        }

    def to_payload_dict(self) -> dict[str, object]:
        return {
            "weekly_bucket": self.weekly_bucket,
            "surface": self.surface.value,
            "operation": self.operation.value,
            "execution_context": self.execution_context.value,
            "count": self.count,
        }

    @classmethod
    def from_state_dict(cls, raw: object) -> Aggregate:
        obj = _require_object(raw, "aggregate")
        _require_exact_keys(
            obj,
            {
                "identifier_epoch",
                "schema_version",
                "weekly_bucket",
                "surface",
                "operation",
                "execution_context",
                "count",
            },
            "aggregate",
        )
        surface = _enum_value(Surface, obj["surface"], "surface")
        return cls(
            schema_version=obj["schema_version"],
            identifier_epoch=_require_int(
                obj["identifier_epoch"],
                "aggregate.identifier_epoch",
                minimum=0,
                maximum=2**63 - 1,
            ),
            weekly_bucket=_require_int(
                obj["weekly_bucket"],
                "aggregate.weekly_bucket",
                minimum=0,
                maximum=4,
            ),
            surface=surface,
            operation=_enum_value(Operation, obj["operation"], "operation"),
            execution_context=_enum_value(
                ExecutionContext, obj["execution_context"], "execution context"
            ),
            count=_require_int(
                obj["count"], "aggregate.count", minimum=1, maximum=MAX_COUNT
            ),
        )


def canonical_payload_bytes(payload: Mapping[str, Any]) -> bytes:
    """Return the exact UTF-8 bytes shared by preview and eventual submit."""
    validate_payload(payload)
    return (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def validate_payload(payload: Mapping[str, Any]) -> None:
    obj = _require_object(payload, "payload")
    _require_exact_keys(
        obj,
        {
            "schema_version",
            "payload_id",
            "identifier_epoch",
            "instance_id",
            "mneme_major_minor_version",
            "aggregates",
        },
        "payload",
    )
    if obj["schema_version"] != PAYLOAD_SCHEMA_VERSION:
        raise UsageContractError("payload.schema_version is not supported")
    for name in ("payload_id", "instance_id"):
        if not isinstance(obj[name], str) or not _HEX_128_RE.fullmatch(obj[name]):
            raise UsageContractError(f"payload.{name} must be 128-bit lowercase hex")
    epoch = _require_int(
        obj["identifier_epoch"],
        "payload.identifier_epoch",
        minimum=0,
        maximum=2**63 - 1,
    )
    if not isinstance(
        obj["mneme_major_minor_version"], str
    ) or not _MAJOR_MINOR_RE.fullmatch(obj["mneme_major_minor_version"]):
        raise UsageContractError(
            "payload.mneme_major_minor_version must contain only major.minor"
        )
    rows = obj["aggregates"]
    if not isinstance(rows, list) or not rows:
        raise UsageContractError("payload.aggregates must be a non-empty list")
    seen: set[tuple[int, Surface, Operation, ExecutionContext]] = set()
    for raw_row in rows:
        row = _require_object(raw_row, "payload aggregate")
        _require_exact_keys(
            row,
            {"weekly_bucket", "surface", "operation", "execution_context", "count"},
            "payload aggregate",
        )
        aggregate = Aggregate.from_state_dict(
            {
                "schema_version": PAYLOAD_SCHEMA_VERSION,
                "identifier_epoch": epoch,
                **dict(row),
            }
        )
        key = (
            aggregate.weekly_bucket,
            aggregate.surface,
            aggregate.operation,
            aggregate.execution_context,
        )
        if key in seen:
            raise UsageContractError("payload contains duplicate aggregate keys")
        seen.add(key)


@dataclass(frozen=True)
class Snapshot:
    """An immutable exact payload, encoded for lossless JSON persistence."""

    payload_bytes: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.payload_bytes, bytes):
            raise UsageContractError("snapshot payload must be bytes")
        if not self.payload_bytes or len(self.payload_bytes) > MAX_PAYLOAD_BYTES:
            raise UsageContractError("snapshot payload size is out of bounds")
        try:
            decoded = json.loads(self.payload_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UsageContractError(
                "snapshot payload must be valid UTF-8 JSON"
            ) from exc
        validate_payload(decoded)
        if canonical_payload_bytes(decoded) != self.payload_bytes:
            raise UsageContractError("snapshot payload is not canonical")

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self.payload_bytes.decode("utf-8"))

    @property
    def identifier_epoch(self) -> int:
        return int(self.payload["identifier_epoch"])

    @property
    def payload_id(self) -> str:
        return str(self.payload["payload_id"])

    def to_dict(self) -> dict[str, str]:
        return {"payload_b64": base64.b64encode(self.payload_bytes).decode("ascii")}

    @classmethod
    def from_dict(cls, raw: object) -> Snapshot:
        obj = _require_object(raw, "snapshot")
        _require_exact_keys(obj, {"payload_b64"}, "snapshot")
        encoded = obj["payload_b64"]
        if not isinstance(encoded, str):
            raise UsageContractError("snapshot.payload_b64 must be a string")
        try:
            payload_bytes = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise UsageContractError("snapshot.payload_b64 is invalid") from exc
        return cls(payload_bytes=payload_bytes)


@dataclass(frozen=True)
class UsageState:
    consent: Consent | None = None
    secret_hex: str | None = None
    counters: tuple[Aggregate, ...] = field(default_factory=tuple)
    snapshots: tuple[Snapshot, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.secret_hex is not None and not _SECRET_RE.fullmatch(self.secret_hex):
            raise UsageContractError("secret must be 256-bit lowercase hex")
        if (
            self.consent is not None
            and self.consent.enabled
            and self.secret_hex is None
        ):
            raise UsageContractError("enabled consent requires a local secret")
        counter_keys = [aggregate.key for aggregate in self.counters]
        if len(counter_keys) != len(set(counter_keys)):
            raise UsageContractError("state contains duplicate counter keys")
        snapshot_epochs = [snapshot.identifier_epoch for snapshot in self.snapshots]
        if len(snapshot_epochs) != len(set(snapshot_epochs)):
            raise UsageContractError(
                "state contains more than one pending snapshot per epoch"
            )
        payload_ids = [snapshot.payload_id for snapshot in self.snapshots]
        if len(payload_ids) != len(set(payload_ids)):
            raise UsageContractError(
                "state contains duplicate pending payload identifiers"
            )

    def has_current_consent(self, policy_version: str = CURRENT_POLICY_VERSION) -> bool:
        return self.consent is not None and self.consent.is_current(policy_version)

    def to_dict(self) -> dict[str, object]:
        return {
            "state_version": STATE_VERSION,
            "consent": None if self.consent is None else self.consent.to_dict(),
            "secret": self.secret_hex,
            "counters": [item.to_state_dict() for item in sorted(self.counters)],
            "snapshots": [
                item.to_dict()
                for item in sorted(
                    self.snapshots, key=lambda snapshot: snapshot.identifier_epoch
                )
            ],
        }

    @classmethod
    def from_dict(cls, raw: object) -> UsageState:
        obj = _require_object(raw, "usage state")
        _require_exact_keys(
            obj,
            {"state_version", "consent", "secret", "counters", "snapshots"},
            "usage state",
        )
        if obj["state_version"] != STATE_VERSION:
            raise UsageContractError("usage state version is not supported")
        secret = obj["secret"]
        if secret is not None and not isinstance(secret, str):
            raise UsageContractError("usage state secret must be a string or null")
        counters = obj["counters"]
        snapshots = obj["snapshots"]
        if not isinstance(counters, list):
            raise UsageContractError("usage state counters must be a list")
        if not isinstance(snapshots, list):
            raise UsageContractError("usage state snapshots must be a list")
        return cls(
            consent=(
                None if obj["consent"] is None else Consent.from_dict(obj["consent"])
            ),
            secret_hex=secret,
            counters=tuple(Aggregate.from_state_dict(item) for item in counters),
            snapshots=tuple(Snapshot.from_dict(item) for item in snapshots),
        )


def merge_aggregates(aggregates: Iterable[Aggregate]) -> tuple[Aggregate, ...]:
    """Merge identical closed keys while saturating the bounded count."""
    merged: dict[
        tuple[str, int, int, Surface, Operation, ExecutionContext], Aggregate
    ] = {}
    for aggregate in aggregates:
        existing = merged.get(aggregate.key)
        if existing is None:
            merged[aggregate.key] = aggregate
        else:
            merged[aggregate.key] = existing.with_count(
                min(MAX_COUNT, existing.count + aggregate.count)
            )
    return tuple(sorted(merged.values()))

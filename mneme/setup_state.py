"""
setup_state.py — Mneme activation state for a project.

M1.3 activation state model (frozen contract:
docs/plans/m1-3-audit-to-setup-activation.md section 3):

    not_installed → setup → active

- ``not_installed``  No connected Mneme installation exists for the project.
- ``setup``          Mneme is initialized and may provide context, integrations
                     and non-blocking checks. Preventive enforcement has NOT
                     been activated.
- ``active``         At least one preventive protection has been explicitly
                     enabled.

This state is distinct from the Architecture Audit lifecycle
(ephemeral → saved → pilot); the two lifecycles must never collapse.

The record persists as an optional top-level ``activation`` key inside the
existing ``project_memory.json``. MemoryStore ignores unknown top-level keys
and every memory-file writer does raw read-modify-write, so adding the section
is backward and forward compatible. No parallel state file is created.

The record always carries ``enforcement: "not_enabled"`` when written by
setup. Nothing in this module can enable enforcement; ``active`` is reachable
only through an explicit future activation action, never implicitly.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ActivationState = Literal["not_installed", "setup", "active"]

STATE_NOT_INSTALLED: ActivationState = "not_installed"
STATE_SETUP: ActivationState = "setup"
STATE_ACTIVE: ActivationState = "active"

ACTIVATION_STATES: tuple[str, ...] = (
    STATE_NOT_INSTALLED,
    STATE_SETUP,
    STATE_ACTIVE,
)

ENFORCEMENT_NOT_ENABLED = "not_enabled"

ACTIVATION_SCHEMA = "mneme.setup/v1"

# Allowed explicit transitions. ``setup`` → ``setup`` is the idempotent rerun.
# ``setup`` → ``active`` requires an explicit user activation action that does
# not exist in M1.3; no code path in this module performs it.
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    STATE_NOT_INSTALLED: frozenset({STATE_SETUP}),
    STATE_SETUP: frozenset({STATE_SETUP, STATE_ACTIVE}),
    STATE_ACTIVE: frozenset({STATE_ACTIVE}),
}

DEFAULT_MEMORY_PATH = ".mneme/project_memory.json"


class ActivationStateError(ValueError):
    """Raised when an activation record or transition is invalid."""


def utc_now() -> str:
    """ISO 8601 UTC timestamp (seconds precision, ``Z`` suffix)."""
    from datetime import datetime, timezone

    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def scaffold_project_memory(created_by: str = "mneme init") -> dict:
    """Return a valid, empty, neutral project_memory.json skeleton.

    Same shape as the ``mneme init`` scaffold: no seeded decisions, because
    every decision is enforceable and sample content would create phantom
    rules. ``created_by`` records which flow created the file.
    """
    return {
        "meta": {
            "name": "",
            "description": "",
            "created_by": created_by,
            "created": utc_now(),
        },
        "items": [],
        "examples": [],
        "decisions": [],
    }


@dataclass
class ActivationRecord:
    """Persisted Mneme activation state for one project.

    Attributes:
        state:                  Current activation state (see module docstring).
        mneme_version:          Version of the Mneme distribution that last
                                performed setup.
        setup_started_at:       ISO 8601 UTC timestamp of the setup run start.
        setup_completed_at:     ISO 8601 UTC timestamp of first setup completion.
        activated_at:           Timestamp of explicit activation to ``active``.
                                Always ``None`` after setup; nothing in M1.3
                                sets it.
        audit_ref:              Opaque Architecture Audit setup reference as
                                provided. Opaque locally: the CLI records it
                                verbatim and assigns no meaning to it.
        baseline:               Resolved Audit baseline provenance. ``None``
                                until Audit pairing (M1.3b) resolves it.
        integrations_detected:  Integration keys detected during setup.
        integrations_configured: Integration keys actually configured. Setup
                                in M1.3 does not configure integrations, so
                                this stays empty by design.
        enforcement:            Enforcement posture recorded at setup time.
                                Only ``not_enabled`` is ever written here.
    """

    state: ActivationState
    mneme_version: str = ""
    setup_started_at: str = ""
    setup_completed_at: str = ""
    activated_at: str | None = None
    audit_ref: str = ""
    baseline: dict | None = None
    integrations_detected: list[str] = field(default_factory=list)
    integrations_configured: list[str] = field(default_factory=list)
    enforcement: str = ENFORCEMENT_NOT_ENABLED

    def __post_init__(self) -> None:
        if self.state not in ACTIVATION_STATES:
            raise ActivationStateError(
                f"unknown activation state {self.state!r} "
                f"(expected one of {list(ACTIVATION_STATES)})"
            )

    def to_dict(self) -> dict:
        return {
            "schema": ACTIVATION_SCHEMA,
            "state": self.state,
            "mneme_version": self.mneme_version,
            "setup_started_at": self.setup_started_at,
            "setup_completed_at": self.setup_completed_at,
            "activated_at": self.activated_at,
            "audit_ref": self.audit_ref,
            "baseline": self.baseline,
            "integrations_detected": list(self.integrations_detected),
            "integrations_configured": list(self.integrations_configured),
            "enforcement": self.enforcement,
        }

    @classmethod
    def from_dict(cls, raw: object) -> "ActivationRecord":
        if not isinstance(raw, dict):
            raise ActivationStateError("activation record must be an object")
        state = raw.get("state")
        if state not in ACTIVATION_STATES:
            raise ActivationStateError(
                f"unknown activation state {state!r} "
                f"(expected one of {list(ACTIVATION_STATES)})"
            )
        baseline = raw.get("baseline")
        if baseline is not None and not isinstance(baseline, dict):
            raise ActivationStateError("activation baseline must be an object")
        integrations_detected = raw.get("integrations_detected", [])
        integrations_configured = raw.get("integrations_configured", [])
        if not isinstance(integrations_detected, list) or not all(
            isinstance(k, str) for k in integrations_detected
        ):
            raise ActivationStateError(
                "integrations_detected must be a list of strings"
            )
        if not isinstance(integrations_configured, list) or not all(
            isinstance(k, str) for k in integrations_configured
        ):
            raise ActivationStateError(
                "integrations_configured must be a list of strings"
            )
        return cls(
            state=state,
            mneme_version=raw.get("mneme_version", ""),
            setup_started_at=raw.get("setup_started_at", ""),
            setup_completed_at=raw.get("setup_completed_at", ""),
            activated_at=raw.get("activated_at"),
            audit_ref=raw.get("audit_ref", ""),
            baseline=baseline,
            integrations_detected=list(integrations_detected),
            integrations_configured=list(integrations_configured),
            # Read as-is for forward compatibility; setup only ever writes
            # ENFORCEMENT_NOT_ENABLED, and nothing here may enable enforcement.
            enforcement=raw.get("enforcement", ENFORCEMENT_NOT_ENABLED),
        )

    def require_transition(self, to_state: ActivationState) -> None:
        """Validate a proposed state transition, failing closed."""
        allowed = VALID_TRANSITIONS.get(self.state, frozenset())
        if to_state not in allowed:
            raise ActivationStateError(
                f"invalid activation transition {self.state!r} -> {to_state!r}"
            )


def read_activation(memory_path: str | Path) -> ActivationRecord | None:
    """Read the activation record from a project_memory.json.

    Returns ``None`` when the file has no ``activation`` section. Raises
    ``ActivationStateError`` for a malformed record (callers fail safely on
    that rather than guessing state).
    """
    path = Path(memory_path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw = data.get("activation")
    if raw is None:
        return None
    return ActivationRecord.from_dict(raw)


def derive_activation_state(memory_path: str | Path) -> ActivationState:
    """Derive the activation state of a project from its memory file.

    - No memory file                          → ``not_installed``.
    - Memory file with an activation record   → the record's state.
    - Memory file without an activation record → ``setup``.

    The last case covers projects initialized before activation tracking
    existed. Their de-facto posture already matches ``setup``: Mneme project
    state exists and enforcement is never persisted as enabled.
    """
    path = Path(memory_path)
    if not path.exists():
        return STATE_NOT_INSTALLED
    record = read_activation(path)
    if record is None:
        return STATE_SETUP
    return record.state


class ConcurrentModificationError(RuntimeError):
    """The target changed after it was read; the guarded write was refused."""


def atomic_write_json(
    path: Path,
    data: dict,
    *,
    expected_bytes: bytes | None = None,
) -> None:
    """Write JSON atomically: tempfile in the same directory, then replace.

    With ``expected_bytes``, the replace happens only if the target still
    holds exactly those bytes, checked immediately before ``os.replace``.
    This is an optimistic guard within the single-writer discipline, not a
    lock. Callers that omit it keep the unguarded behaviour.
    """
    serialized = json.dumps(data, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(serialized)
        if expected_bytes is not None and path.read_bytes() != expected_bytes:
            raise ConcurrentModificationError(
                f"{path} changed after it was read; nothing was written"
            )
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_activation(memory_path: str | Path, record: ActivationRecord) -> None:
    """Persist the activation record inside an existing project_memory.json.

    Raw read-modify-write: every other top-level key (meta, items, examples,
    decisions, and any future sections) is preserved verbatim. The file must
    already exist; creating project memory is the setup/init flow's job, not
    this function's.
    """
    path = Path(memory_path)
    if not path.exists():
        raise FileNotFoundError(f"memory file {path} does not exist")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["activation"] = record.to_dict()
    atomic_write_json(path, data)

"""Local-only product usage measurement under accepted ADR-032.

The package exposes the closed contracts and persistence primitives used by
Mneme's U1 CLI, MCP, and hook adapters.  It contains no network client,
collector, endpoint, uploader, or scheduler.
"""

from .contracts import (
    CURRENT_POLICY_VERSION,
    PAYLOAD_SCHEMA_VERSION,
    Aggregate,
    Consent,
    ExecutionContext,
    Operation,
    Snapshot,
    SubmissionMode,
    Surface,
    UsageState,
)
from .paths import UsagePaths, default_usage_dir
from .store import UsageStore

__all__ = [
    "CURRENT_POLICY_VERSION",
    "PAYLOAD_SCHEMA_VERSION",
    "Aggregate",
    "Consent",
    "ExecutionContext",
    "Operation",
    "Snapshot",
    "SubmissionMode",
    "Surface",
    "UsagePaths",
    "UsageState",
    "UsageStore",
    "default_usage_dir",
]

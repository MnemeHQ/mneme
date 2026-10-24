# Local usage measurement

Mneme usage measurement is optional, disabled by default, and local-only in
U1. It implements the client side of [ADR-032](adr/ADR-032-opt-in-product-usage-measurement.md)
without a collector, upload command, endpoint, scheduler, or network
dependency.

## Consent and commands

Nothing is counted until a person runs:

```text
mneme usage enable
```

The command displays the current notice and records versioned consent for the
local runtime profile. U1 supports manual local preview only. The future
`weekly` mode, `submit` command, and every network operation belong to the
separately gated U2 milestone and do not exist in this implementation.

The complete U1 administration surface is:

```text
mneme usage enable [--submission manual]
mneme usage disable
mneme usage status
mneme usage preview
mneme usage purge
```

- `disable` stops future counter writes before it returns. It retains existing
  local state so a later status or purge remains possible.
- `status` is read-only. It reports logical retention without cleaning or
  rewriting files.
- `preview` performs no network access. It freezes eligible counters into
  immutable pending snapshots and writes only when snapshot materialization or
  authorized retention cleanup changes state. It prints the exact canonical
  NDJSON bytes reserved for a future U2 submit implementation.
- `purge` deletes consent, the 256-bit local secret, counters, and pending
  snapshots. Enabling again after purge creates a new secret.

Missing, disabled, stale, unreadable, or unsafe consent fails closed for
counting. Ordinary CLI, MCP, and hook execution creates no usage directory or
lock file in those states. Measurement errors, lock contention, or local I/O
failures never change an operation's output, exit code, protocol response, or
enforcement result.

## What is counted

Only aggregate counters from a closed enum are stored. Unknown values are
ignored rather than serialized.

The CLI allowlist contains substantive product commands: `init`, `setup`,
`list_decisions`, `add_decision`, `test_query`, `check`, `audit`, the four
`protect` operations, `cursor generate`, `adr import`, `eventcatalog import`,
`decision-index migrate`, and the four `decision` authority operations.
Help, parser failures, usage administration, Decision MCP startup, benchmarks,
and research commands are excluded.

The MCP allowlist is exactly the six ADR-027 tools:

- `decision.propose`
- `decision.propose_batch`
- `decision.get`
- `decision.search`
- `decision.applicable_to`
- `decision.trace`

Hook counters cover `SessionStart`, `PreToolUse`, and `Stop` for Claude Code
and Codex CLI, plus `preToolUse` for Kiro. The internal `mneme check` child
process used by those adapters carries a suppression marker so one hook
invocation cannot also become a CLI count.

Counters contain only the schema version, 30-day epoch, weekly bucket, surface,
allowlisted operation, coarse execution context (`interactive`, `ci`, or
`unknown`), and a bounded count. Mneme does not put code, prompts, arguments,
paths, repositories, decision content, identifiers, verdicts, errors, or raw
environment values into usage state.

## Identity, epochs, and snapshots

Epoch zero starts at `1970-01-01T00:00:00Z`. An epoch is
`floor(unix_seconds / (30 * 86400))`; its weekly bucket is
`floor(day_within_epoch / 7)`. Buckets 0 through 3 contain seven days each and
bucket 4 contains the final two days.

Enablement creates a cryptographically random 256-bit secret that never leaves
the machine. Mneme derives a 128-bit instance identifier independently for
each epoch with HMAC-SHA256 over a versioned domain and the epoch number. The
identifier cannot provide cross-epoch linkage from payload material.

Preview creates at most one pending snapshot per epoch. Every snapshot has one
random 128-bit payload identifier and stores the canonical payload bytes
losslessly. Repeated previews return identical bytes. Counters added while a
snapshot is pending remain unfrozen; after a future acknowledged U2 submission
clears that snapshot, another snapshot in the same epoch will receive a new
payload identifier. Counters from different epochs never share a payload.

## Storage, retention, and security

Usage state is outside every repository and outside project memory or the
Decision Index:

| Platform | Directory |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Mneme\usage` |
| macOS | `~/Library/Application Support/Mneme/usage` |
| Linux/Unix | `$XDG_STATE_HOME/mneme/usage`, or `~/.local/state/mneme/usage` |

`state.json` is replaced atomically under a separate cross-process
`state.lock`. Mneme rejects symlink and Windows reparse-point components for
owned usage paths. POSIX directories/files are restricted to mode `0700` and
`0600`; Windows creation removes inherited ACLs and grants the current user
full control.

Local aggregate and pending-snapshot state has a maximum age of 35 days. The
closed schema intentionally carries no event timestamp, so a weekly aggregate
expires conservatively 35 days after its bucket's first possible UTC day. This
can discard the youngest counts in a bucket up to six days early. An immutable
snapshot expires with its oldest aggregate and can therefore discard younger
rows earlier as well. This is an accepted undercounting bias that preserves the
privacy maximum and snapshot immutability.

Read-only status applies expiration logically in memory and never rewrites the
store. Physical cleanup occurs on a later authorized mutation such as enable,
disable, preview, or counter persistence. A dormant profile may therefore
retain expired bytes on disk until that next mutation or purge, but expired
data is never shown by status, included in preview, or incremented.

Runtime counter locking is non-blocking. Under contention Mneme may omit a
count, but a reported successful increment is never lost and state remains
valid. This deliberately favors operational noninterference over exact
measurement.

## Measurement limitations

The system measures consenting runtime profiles, not people, organizations,
machines, repositories, customers, or total adoption. Identifier rotation
prevents exact rolling-30-day uniqueness and repeat-use analysis across epoch
boundaries. Counts may be lost under contention, removed early by conservative
retention, misattributed by a badly skewed local clock, automated, replayed, or
spoofed. They are not enforcement evidence and must not drive access, billing,
security, or decision authority.

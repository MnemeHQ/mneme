# OpenCode — experimental adapter

**Status: Experimental.** This is not a supported integration and carries no
support-level statement. The taxonomy in [README.md](README.md) applies.

## What ships

An adapter maintained in this repository, on `main`, targeting the OpenCode
terminal CLI (`2.3.0`, V2 plugin API) through its `execute.before` tool hook.

| Surface | Coverage | Introduced |
| --- | --- | --- |
| `write` to a **verified-new** `.py` file, complete content | pre-mutation check; `block` throws and the host refuses the write | S1 ([PR #824](https://github.com/MnemeHQ/mneme/pull/824)) |
| `edit` of an **existing** `.py` file, `oldString` / `newString`, optional `replaceAll` | introduced-delta check (ADR-018); `block` throws | E1 ([PR #835](https://github.com/MnemeHQ/mneme/pull/835)) |

Both evaluate `FORBID_LITERAL` rules only, through the canonical `mneme check`
engine and the shared Claude Code adapter internals. The bridge supplies
transport; it implements no matcher, resolver or policy engine.

## What is not covered

Unsupported and unclaimed: non-`.py` targets; whole-file overwrite of an existing
file; `MultiEdit`/patch or hunk payloads; shell; MCP and custom tools; deletion;
rename; Stop/session-boundary enforcement; CI and gateway admission; numeric
rules and waivers.

One behavioural note:

- A `warn`-mode literal failure is allowed and prints the canonical
  `Mneme WARN: warn_mode_violation` diagnostic. It is a diagnostic, not
  protection.

Historical note: before E1 merged, `edit` was outside the S1 surface and produced
a `NOT_COVERED` diagnostic. That observation belongs to the S1 record and no
longer describes the adapter. E1 intercepts `edit`, so an existing `.py` file,
including one created by an earlier guarded `write`, is evaluated under the
normal preconditions.

## Limitations

- **Race resistance is `NOT_ESTABLISHED`.** Independent validation demonstrated
  that a target created or substituted between the bridge's read and the host's
  write can land content the checker never evaluated. Symlink and hardlink
  substitution redirected a permitted edit into another file. This is a
  documented bypass, not a resolved property.
- **Claim ceiling is `none` on this host.** OpenCode supplies no `callID`, so the
  six-identifier evidence gate is incomplete. No identifier is synthesized and
  `EXECUTION_OBSERVED` is not claimed.
- **Byte fidelity is partial.** On Linux, LF, non-ASCII and no-trailing-newline
  fixtures matched across event, carrier and file. CRLF host-level coverage is
  `NOT_ESTABLISHED` for this experimental surface. Windows equality was not
  demonstrated; the shared carrier is text-mode.
- One host/model/session shape was validated; multi-session and cross-directory
  behaviour is not claimed.

## Records

| Record | Location |
| --- | --- |
| S1 charter (with amendments) | [2026-11-17-opencode-s1-implementation-charter.md](../plans/2026-11-17-opencode-s1-implementation-charter.md) |
| E1 charter | [2026-11-18-opencode-e1-edit-charter.md](../plans/2026-11-18-opencode-e1-edit-charter.md) |
| Layer 1 freeze amendments | [layer1-freeze-e73ff7d.md](../architecture/layer1-freeze-e73ff7d.md) |
| S1 implementation | [PR #824](https://github.com/MnemeHQ/mneme/pull/824), merge `3ada7741` |
| E1 implementation | [PR #835](https://github.com/MnemeHQ/mneme/pull/835), merge `7014c67d` |
| S1 independent validation | PR #824 discussion; verdict `CONDITIONAL` |
| E1 independent validation | PR #835 discussion; verdict `PASS WITH DEVIATIONS` |
| Historical compaction experiment | [validation/ox-compaction](../../validation/ox-compaction/README.md) — NULL verdict, closed evidence-only |

The compaction experiment and the S1/E1 adapter are separate efforts. The former
asked whether governance guidance injected at a compaction checkpoint changed
outcomes; it returned a NULL verdict and was closed evidence-only. It is not a
pre-mutation enforcement capability and is not part of S1 or E1.

The [NVIDIA OpenShell + OpenCode reference contract](../plans/2026-10-22-openshell-opencode-reference-integration-acceptance-contract.md)
is a separate, unmerged experiment. It does not describe this adapter and this
adapter does not depend on it.

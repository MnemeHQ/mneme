# Mneme OpenCode plugin (S1 + E1)

Transport-only plugin for the OpenCode pre-mutation surface. It forwards `write`
and `edit` events to the Python bridge and throws only on a `block` decision.

No support-matrix decision is recorded here; see
[docs/integrations/opencode.md](../../docs/integrations/opencode.md) for the
canonical record. The maximum literal evidence claim is `EXECUTION_OBSERVED`, and
on this host it is unreachable because OpenCode supplies no `callID` — so the
claim is `none`. Host prevention is a separate host-side observation.

## Scope

- Verified-new-file `.py` `write` with complete content (S1).
- Existing-file `.py` `edit` with `oldString` / `newString` and optional
  `replaceAll`, evaluated on the introduced delta (E1).
- `FORBID_LITERAL` only.
- Canonical `mneme check` via the shared adapter internals.
- Default-open for `unevaluated`, `skip`, `unsupported` and `setup_invalid`.
  Those outcomes are not Mneme authorization or protection.
- `strict` mode may block a trusted complete literal `FAIL`. `warn` never blocks.

Nothing else is supported: existing-file `write` (whole-file overwrite),
non-`.py` targets, `MultiEdit`/patch or hunk payloads, shell, MCP/custom tools,
deletion, rename, Stop, CI, numeric rules or waivers.

For `edit`, the bridge mirrors the host's replacement rule: multiple matches
without `replaceAll` are refused as `unevaluated` (`ambiguous_old_string`), and a
missing `oldString` is `unevaluated` (`old_string_not_found`).

## Configuration

Provide an absolute `authorityPath` in the plugin options:

```jsonc
{
  "plugins": [
    {
      "package": "/path/to/integrations/opencode-plugin",
      "options": {
        "authorityPath": "/path/to/authority.json",
        "timeoutMs": 60000
      }
    }
  ]
}
```

`authority.json` is an expectation pin, not a policy source:

```json
{
  "decision_id": "ADR-001",
  "decision_version_id": "dver-...",
  "rule_id": "ADR-001:FORBID_LITERAL:...",
  "rule_value": "psycopg2",
  "rule_scope": "src/handlers/**"
}
```

The bridge uses the session directory from
`ctx.session.get({ sessionID }).location.directory` to resolve relative targets
and never uses the process cwd. A missing directory is `unevaluated`.

A relative target may not traverse outside the session directory. An absolute
target may resolve outside it: the memory that governs the target path is
selected, and that memory's policy root must contain the target. Symlinked
target chains remain unsupported.

Set `MNEME_OPENCODE_PYTHON` if the host Python is not `python` (Windows) or
`python3` (other platforms).

## Evidence

Test-local only. Set `MNEME_OPENCODE_EVIDENCE_LOG` to an absolute path to append
one sanitized JSON record per decision. No production persistence, no public
schema.

The record copies the canonical checker `applicability` and `violations`
records without reinterpretation. `EXECUTION_OBSERVED` requires a trusted
complete payload, the pinned rule's canonical applicability entry, and all six
raw host identifiers (`tool`, `sessionID`, `callID`, `agent`, `messageID`,
`eventID`). Missing identifiers downgrade the claim to `none`.

The pinned G0 event contract exposes `id` but not `callID`. The plugin forwards
`callID: null` rather than synthesizing one from `id`; on that host the identity
gate is therefore incomplete and the claim is `none`. Reaching
`EXECUTION_OBSERVED` requires a host event that supplies all six identifiers.

A `block` decision is not a host-prevention observation. The bridge always emits
`host_witness: null`; a validator-owned host-side witness (tool status/error and
target state) must be recorded separately. The bridge never infers prevention
from its own decision.

## Diagnostics

The plugin prints one diagnostic line per decision that is not a trusted clean
allow:

| Decision | Host-visible line |
| --- | --- |
| `block` | throws `Mneme BLOCK: <reason>`; the host reports the tool as errored |
| `setup_invalid` | `Mneme NOT_PROTECTED: <reason>` |
| `allow` with `reason: warn_mode_violation` | `Mneme WARN: warn_mode_violation` |
| other non-`allow` | `Mneme <decision>: <reason>` |

`decision` is the sole enforcement-control input. `reason` is read only to
compose these diagnostics; it never authorizes, denies, downgrades or upgrades a
decision, selects a mode, changes a claim or alters evidence. The warn line is a
diagnostic, not protection: the write is still allowed and the claim ceiling is
unchanged. It carries no rule identity because the plugin does not parse the
checker payload.

## Known limitations

- Not covered and not evaluated: `MultiEdit`, patch/hunk payloads, shell,
  MCP/custom tools, non-`.py` targets, whole-file overwrite of an existing file,
  deletion and rename. The plugin diagnoses each uncovered tool once as
  `NOT_COVERED` and does not intercept it; this is not a protection claim.
- An `edit` call that follows a guarded `write` is outside the guarded surface.
  Validation observed a model rewriting a just-written file through `edit`,
  producing only a `NOT_COVERED` diagnostic.
- A new file whose parent directory does not exist is `unsupported`
  (`target_parent_missing`) and proceeds under default-open. The bridge does not
  create directories.
- The shared unrouted checker carrier is text-mode. On Linux, LF, non-ASCII and
  no-trailing-newline fixtures were byte-identical across event, carrier and
  file; CRLF host-level coverage is `NOT_ESTABLISHED`. On Windows, newline
  translation occurs and byte equality is not demonstrated.
- The bridge cannot observe whether the host actually refused a write. Host
  prevention requires a separate host-side witness.
- One host/model/session shape was validated; multi-session and cross-directory
  behavior is not claimed.
- No race or atomicity guarantee. Race resistance is `NOT_ESTABLISHED`; a target
  created or substituted between the read, evaluation and host write is a
  documented bypass, and symlink or hardlink substitution can redirect a
  permitted edit into another file.
- The evidence claim on this host is `none`: OpenCode supplies no `callID`, so
  the six-identifier gate is incomplete. No identifier is synthesized.

See [docs/integrations/opencode.md](../../docs/integrations/opencode.md) for the
canonical record.

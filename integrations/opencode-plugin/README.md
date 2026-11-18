# Mneme OpenCode S1 plugin

Transport-only plugin for the OpenCode S1 pre-mutation surface. It forwards a
`write` event to the Python bridge and throws only on a `block` decision.

No support-matrix decision is recorded here. The maximum literal evidence claim
is `EXECUTION_OBSERVED`; host prevention is a separate host-side observation.

## Scope

- Verified-new-file `.py` `write` with complete content.
- `FORBID_LITERAL` only.
- Canonical `mneme check` via the shared adapter internals.
- Default-open for `unevaluated`, `skip`, `unsupported` and `setup_invalid`.
  Those outcomes are not Mneme authorization or protection.
- `strict` mode may block a trusted complete literal `FAIL`. `warn` never blocks.

Nothing else is supported: existing-file writes, non-`.py` targets, `edit`,
patch/hunk payloads, shell, MCP/custom tools, deletion, rename, Stop, CI,
numeric rules or waivers.

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

A `block` decision is not a host-prevention observation. The bridge always emits
`host_witness: null`; a validator-owned host-side witness (tool status/error and
target state) must be recorded separately. The bridge never infers prevention
from its own decision.

## Known limitations

- `edit`, patch/hunk payloads, shell, MCP/custom tools, non-`.py` targets and
  existing files are unsupported and not evaluated. The plugin diagnoses each
  non-`write` tool once as `NOT_COVERED` and does not intercept it; this is not
  a protection claim.
- A new file whose parent directory does not exist is `unsupported`
  (`target_parent_missing`) and proceeds under default-open. The bridge does not
  create directories; this remains unsupported pending separate
  characterization.
- The shared unrouted checker carrier is text-mode; byte equality between the
  evaluated carrier and the host-written file must be demonstrated on the pinned
  host. On Windows, newline translation may occur. A byte-exact carrier is a
  separately authorized change.
- The bridge cannot observe whether the host actually refused a write. Host
  prevention requires a separate host-side witness.
- One project/session path was probed in G0; multi-session and cross-directory
  behavior requires live validation.
- No race or atomicity guarantee. Race resistance is `NOT_ESTABLISHED`; a target
  created or substituted between the absence proof, evaluation and host write is
  a documented bypass.

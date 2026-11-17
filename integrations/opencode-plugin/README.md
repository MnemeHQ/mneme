# Mneme OpenCode S1 plugin (experimental)

Transport-only plugin for the OpenCode S1 pre-mutation surface. It forwards a
`write` event to the Python bridge and throws only on a `block` decision.

**Status: experimental.** No support-matrix claim is made. OpenCode remains
Experimental. The maximum literal evidence claim is `EXECUTION_OBSERVED`; host
prevention is a separate host-side observation.

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

Set `MNEME_OPENCODE_PYTHON` if the host Python is not `python` (Windows) or
`python3` (other platforms).

## Evidence

Test-local only. Set `MNEME_OPENCODE_EVIDENCE_LOG` to an absolute path to append
one sanitized JSON record per decision. No production persistence, no public
schema.

## Known limitations

- The shared unrouted checker carrier is text-mode; byte equality between the
  evaluated carrier and the host-written file must be demonstrated on the pinned
  host. On Windows, newline translation may occur. A byte-exact carrier is a
  separately authorized change.
- The bridge cannot observe whether the host actually refused a write. Host
  prevention requires a host-side witness.
- One project/session path was probed in G0; multi-session and cross-directory
  behavior requires live validation.
- No race or atomicity guarantee.

# Mneme — Claude Code plugin

Architectural enforcement for [Claude Code](https://docs.anthropic.com/en/docs/claude-code),
packaged as an installable plugin. Enforce your project's ADRs and engineering
constraints automatically — before AI-generated edits reach your repo.

This is the plugin form of the [flat `claude-code` integration](../claude-code/).
It bundles the enforcement hook, the `mneme` skill, and four namespaced slash
commands (`/mneme:context`, `/mneme:check`, `/mneme:record`, `/mneme:review`)
into a single distributable unit.

## Prerequisite: install Mneme

The plugin drives the `mneme-hook` / `mneme` CLI, which ships with the
`mneme-hq` package. Installation is two steps — the runtime and the plugin are
separate artifacts, and installing one does not install the other.

**Step 1 — install the runtime:**

```bash
pipx install "mneme-hq>=0.5.1"
```

`>=0.5.1` is a real requirement, not a preference. Earlier releases do not
support the `--json` verdict the hook relies on; on `0.5.0` and below a
crashing check could hard-block an edit, and `warn` mode reported nothing at
all. If the installed runtime is too old, the hook says so explicitly rather
than silently disabling enforcement.

**Step 2 — install the plugin** (see below).

If `mneme-hook` is not on `PATH`, the hook **fails open**: Claude Code reports a
non-blocking hook error and the edit proceeds. Enforcement simply stays inactive
until Mneme is installed. (Auto-install / runtime bundling is intentionally not
part of this plugin.)

## Install the plugin

**Local development / trying it out:**

```bash
claude --plugin-dir /path/to/mneme/integrations/claude-code-plugin
```

After changes, reload in-session with `/reload-plugins`.

**From a marketplace:** not yet available. The plugin has not been submitted to
the Claude Code community catalog, so `--plugin-dir` above is currently the
only installation path. Once it is listed, enabling it from Claude Code's
plugin UI will prompt for the **enforcement mode** (`strict` or `warn`).

## How enforcement works

The plugin registers three hooks, all exec-form invocations of `mneme-hook`:

| Event | Matcher | Role |
|---|---|---|
| `PreToolUse` | `Edit\|Write\|MultiEdit\|Bash` | **Prevent**: block violating mutations before they land. |
| `SessionStart` | (all sources) | Capture the per-session repository baseline used by the Stop boundary. |
| `Stop` | — | **Catch**: evaluate the session delta before the agent completes. |

> **Coverage boundary (ADR-021): prevent -> catch -> verify.**
>
> - Direct file tools (`Edit`, `Write`, `MultiEdit`) are checked
>   deterministically before mutation, on introduced lines only.
> - Shell calls are checked before execution only when Mneme can prove from
>   the command string alone what will land and where: a single simple
>   `cat > path << 'EOF'` / `cat >> path << 'EOF'` with a quoted delimiter.
>   Every other shell form — pipelines, substitutions, generators,
>   interpreters, unquoted delimiters — is **not** preflight-blocked; it is
>   allowed to run and its results are evaluated at `Stop`.
> - The `Stop` hook audits content this session introduced (baseline ->
>   working-tree diff with the same introduced-line semantics as the edit
>   gate). It blocks completion with actionable reasons in strict mode and
>   never blocks on dirty state that predates the session. It requires git;
>   without git it reports itself inactive.
> - CI remains the final verification boundary.

The hook blocks **only** on a verdict it could parse and trust. An exit code on
its own is not treated as a verdict — `mneme check --mode strict` returns 1 for
a WARN verdict, but Python also returns 1 for an uncaught exception, so a
malformed memory file would otherwise be indistinguishable from a violation.
Anything unparseable fails open with a note on stderr.

Claude Code surfaces the block as an error containing the violated decision id,
so it can adjust course without you intervening.

## Slash commands

| Command | Purpose |
|---------|---------|
| `/mneme:context` | Retrieve decisions relevant to your current task |
| `/mneme:check` | Check a file or draft against project memory |
| `/mneme:record` | Record a new architectural decision |
| `/mneme:review` | Audit all pending diff changes against decisions |

## Configuration: enforcement mode

| Option | Values | Default | Effect |
|--------|--------|---------|--------|
| `mode` | `strict`, `warn` | `strict` | `strict` blocks violating edits; `warn` reports them without blocking |

The plugin's `mode` userConfig value is exported to the hook subprocess as
`CLAUDE_PLUGIN_OPTION_MODE`. The hook adapter resolves the mode with this
precedence:

1. `MNEME_HOOK_MODE` (explicit environment override)
2. `CLAUDE_PLUGIN_OPTION_MODE` (the plugin option)
3. `strict` (default)

An unrecognized value falls back to `strict`, so a typo never silently disables
enforcement. Use `warn` while iterating on decisions to avoid friction.

In `warn` mode the hook emits a `PreToolUse` JSON payload with
`permissionDecision: "defer"` and the violation detail as the reason, rather
than writing to stderr — Claude Code discards stderr from a hook that exits 0,
which is why warn mode previously reported nothing at all. `defer` is
deliberate: `allow` would auto-approve the tool call and bypass the permission
prompt you would otherwise get, so a *warning* mode must never use it. How
Claude Code renders a `defer` reason has not been confirmed end-to-end in a
live session. In `warn` mode the `Stop` boundary likewise reports through
non-blocking feedback (`hookSpecificOutput.additionalContext`) and never
blocks completion.

## Retrieval: what the hook checks and what it misses

The automatic hook query is `"edit to <file_path>"` — tokens from the target
file name determine which decisions are retrieved. A decision with
`scope: ["storage", "database"]` reliably matches `storage_layer.py`, but may
**not** match `models.py`, and generic names like `utils.py` rarely match
anything.

**Mitigations:**

1. Choose scope keywords (via `/mneme:record`) that match file names in your project.
2. Run `/mneme:context` before non-trivial edits with a descriptive domain phrase.
3. Run `/mneme:review` after a batch of edits to catch anything the per-edit hook missed.

The hook is a first line of defence, not a complete audit.

## Fail-open guarantees

The hook allows the edit — never blocks — when:

- `mneme-hook` is not on `PATH` (the exec-form spawn fails; non-blocking error)
- The existing target file cannot be read or reconstructed for an Edit or MultiEdit operation
- `.mneme/project_memory.json` cannot be found by walking up from the working dir
- The tool event is malformed
- `mneme check` times out (10 s internal) or any other execution error occurs
- `mneme check` crashes, or returns anything the hook cannot parse as a trusted
  verdict — a corrupt memory file, a traceback, or an unexpected exit code
- The installed `mneme-hq` is older than 0.5.1 and rejects `--json` (the hook
  warns loudly that enforcement is inactive rather than failing silently)

Only a parsed, violating verdict from `mneme check` in `strict` mode blocks an
edit.

## Platform support

Because the hook uses **exec form** (`args` present), Claude Code resolves
`mneme-hook` on `PATH` and spawns it directly — there is **no shell involved**,
so the hook does not depend on `bash`, Git Bash, or PowerShell being present or
behaving a particular way. This is the portable form recommended in the
[hooks reference](https://code.claude.com/docs/en/hooks#exec-form-and-shell-form).

Tested on Windows 11 (Microsoft Store Python 3.12). Not yet exercised on macOS
or Linux in CI; the invocation is platform-independent by construction, but
those OSes have not been run directly.

## Validate

```bash
claude plugin validate /path/to/.../claude-code-plugin --strict
```

## References

- Plugin manifest & hook schema: <https://code.claude.com/docs/en/plugins-reference>
- Hook exit codes, exec form, execution model: <https://code.claude.com/docs/en/hooks>

## License

MIT — see [LICENSE](LICENSE).

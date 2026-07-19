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
`mneme-hq` package.

> **Current install state (verified 2026-07-02).** The reliable Claude Code
> hook requires the `v0.4.2` fixes (module execution + exit-code propagation).
> The published PyPI release is **`0.4.0`**, which has the known exit-propagation
> bug — a failed check could exit 0 and let a violating edit through. `v0.4.2`
> is tagged and released on GitHub but **not yet published to PyPI**. Until it
> is, install Mneme from the repository so you get the reliable hook:
>
> ```bash
> git clone https://github.com/MnemeHQ/mneme
> pip install -e mneme   # or: pipx install ./mneme
> ```
>
> Once `mneme-hq >= 0.4.2` is on PyPI, `pipx install "mneme-hq>=0.4.2"` becomes
> the one-line install. See the PR / release notes for the outstanding publish
> step.

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

**From a marketplace** (once published), add the marketplace and enable the
`mneme` plugin from Claude Code's plugin UI. On enable, Claude Code prompts for
the **enforcement mode** (`strict` or `warn`).

## How enforcement works

The plugin registers a `PreToolUse` hook on `Edit|Write|MultiEdit`. The hook
uses Claude Code's **exec form** — it invokes the `mneme-hook` console script
directly on `PATH`, with no shell in between:

```json
{ "type": "command", "command": "mneme-hook", "args": [], "timeout": 30 }
```

`mneme-hook` (the existing Claude Code adapter, unchanged by this plugin):

1. Reconstructs the full post-edit file content (not just the changed string).
2. Discovers `.mneme/project_memory.json` by walking up from the working dir.
3. Runs `mneme check` with a query derived from the target file path.
4. Exits **2** (block) on a violating verdict in `strict` mode, or **0** (allow)
   otherwise. In `warn` mode it never blocks.

Exit code **2 is the only blocking result**; any other exit code is a
non-blocking hook error, so execution failures never block an edit.

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

Only a real violating verdict from `mneme check` in `strict` mode blocks an edit.

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

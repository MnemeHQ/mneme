# Mneme — Claude Code plugin

Architectural governance for [Claude Code](https://docs.anthropic.com/en/docs/claude-code),
packaged as an installable plugin. Enforce your project's ADRs and engineering
constraints automatically — before AI-generated edits reach your repo.

This is the plugin form of the [flat `claude-code` integration](../claude-code/).
It bundles the enforcement hook, the `mneme` skill, and four slash commands into
a single distributable unit with namespaced commands (`/mneme:context`,
`/mneme:check`, `/mneme:record`, `/mneme:review`).

## Prerequisite: install Mneme

The plugin drives the `mneme-hook` / `mneme` CLI, which ships with the
`mneme-hq` package. Install it once, on your `PATH`:

```bash
pipx install "mneme-hq>=0.4.2"
```

> **Why >= 0.4.2:** earlier versions had incomplete exit-code propagation —
> a failed check could return exit 0 and let a violating edit through. 0.4.2 is
> the first fully reliable hook release.

If `mneme-hook` is not found, the hook **fails open** (edits are never blocked)
and prints the install command above. Governance simply stays inactive until
Mneme is installed. Bundling/auto-install is intentionally deferred to a later
release.

## Install the plugin

**Local development / trying it out:**

```bash
claude --plugin-dir /path/to/mneme/integrations/claude-code-plugin
```

After changes, reload in-session with `/reload-plugins`.

**From a marketplace** (once published), add the marketplace and enable the
`mneme` plugin from Claude Code's plugin UI.

On enable, Claude Code prompts for the **enforcement mode** (`strict` or `warn`).

## What it does

On every Edit, Write, or MultiEdit, a `PreToolUse` hook runs
[`scripts/run_mneme_hook.py`](scripts/run_mneme_hook.py), which delegates to
`mneme-hook`. The hook:

1. Reconstructs the full post-edit file content (not just the changed string).
2. Discovers `.mneme/project_memory.json` by walking up from the working dir.
3. Runs `mneme check` with a query derived from the target file path.
4. Exits **2** (block) on a violating verdict in `strict` mode, or **0** (allow)
   otherwise. In `warn` mode it never blocks.

Claude Code surfaces the block as an error containing the violated decision id,
so it can adjust course without you intervening.

## Slash commands

| Command | Purpose |
|---------|---------|
| `/mneme:context` | Retrieve decisions relevant to your current task |
| `/mneme:check` | Check a file or draft against project memory |
| `/mneme:record` | Record a new architectural decision |
| `/mneme:review` | Audit all pending diff changes against decisions |

## Configuration

| Option | Values | Default | Effect |
|--------|--------|---------|--------|
| `mode` | `strict`, `warn` | `strict` | `strict` blocks violating edits; `warn` reports them without blocking |

The selected mode is passed to the hook as `MNEME_HOOK_MODE` by the wrapper.
Use `warn` while iterating on decisions to avoid friction.

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

The hook exits 0 (allow) — never blocks — when:

- `mneme-hook` is not on `PATH`, or no Python interpreter is available
- The target file cannot be read (common for Write — the file doesn't exist yet)
- `mneme check` times out (10 s) or any other execution error occurs

Only a real verdict from `mneme check` can block an edit.

## Cross-platform notes

- The hook command is POSIX-shell form; Claude Code runs it through its bundled
  shell on macOS, Linux, and Windows.
- The wrapper selects `python3` or `python` automatically, so no single
  interpreter name is assumed. Any Python 3.11+ interpreter works — it uses only
  the standard library.

## Validate

```bash
claude plugin validate /path/to/mneme/integrations/claude-code-plugin --strict
```

## License

MIT — see [LICENSE](LICENSE).

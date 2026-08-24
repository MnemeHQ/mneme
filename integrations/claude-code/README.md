# Mneme for Claude Code — legacy flat integration

> **Superseded by the [plugin](../claude-code-plugin/).** This is the original
> script-installed integration, kept for existing setups. New installs should
> use the plugin, which bundles the same hook with namespaced commands.
>
> Two differences matter when following older docs:
>
> - This integration installs **hyphenated** commands (`/mneme-check`,
>   `/mneme-context`, `/mneme-record`, `/mneme-review`). The plugin installs
>   **namespaced** ones (`/mneme:check`, …). They are not interchangeable.
> - The installer below requires a **git clone**. `scripts/` is not shipped in
>   the `mneme-hq` wheel, so `python scripts/install_claude_code.py` does not
>   exist in a `pip` or `pipx` install.

Architectural governance for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).
Enforce ADRs and engineering constraints automatically — before drift reaches your repo.

## Quick install

> **Version requirement:** use **`mneme-hq>=0.5.1`**. Earlier releases lack the
> `--json` verdict the hook depends on; on 0.5.0 and below a crashing check
> could hard-block an edit and `warn` mode reported nothing at all.

1. `pipx install "mneme-hq>=0.5.1"`  (or `pip install -e .` from this repo)
2. Run the installer: `python scripts/install_claude_code.py`
3. Confirm: edit a file in Claude Code that violates a decision in
   `.mneme/project_memory.json` — Claude Code should be blocked with
   the decision id in the error message.

## What gets installed

- `mneme-hook` command on `$PATH` (via pip).
- `.claude/settings.json` PreToolUse hook entry.
- `.claude/commands/mneme-*.md` slash commands.
- `.claude/skills/mneme/SKILL.md` discovery skill.

## How it works

On every Edit, Write, or MultiEdit, Claude Code pipes the tool input to
`mneme-hook` via stdin. The hook:

1. Reconstructs the full post-edit file content (not just the changed
   string) so decisions are checked in context.
2. Discovers `.mneme/project_memory.json` by walking up from `cwd`.
3. Shells out to `mneme check`, passing a temp file and a query derived
   from the target file path.
4. Exits 2 (block) if `mneme check` returns a non-zero verdict in strict
   mode; exits 0 (allow) otherwise.

The same command also serves two more surfaces (ADR-021):

- `PreToolUse` x `Bash`: a shell call is checked **before execution** only
  when it is deterministically reconstructable — a single simple
  `cat > path << 'EOF'` / `cat >> path << 'EOF'` with a quoted delimiter.
  All other shell forms pass through unblocked.
- `Stop`: after each turn, content this session introduced is evaluated
  against project memory; violations block completion with actionable
  reasons. A per-session baseline (captured at session start, stored in the
  platform temp dir) keeps pre-existing dirty state from being attributed to
  the session. Requires git; otherwise the boundary reports itself inactive.

**Retrieval note:** `mneme check` uses keyword-based retrieval. The query
is `"edit to <file_path>"` — tokens from the file name contribute to
which decisions are retrieved. Decisions whose scope, id, or text share
tokens with the file name score higher. For reliable enforcement on all
decisions, use `/mneme-context` before large edits to confirm the right
decisions are in scope.

## Modes

- `MNEME_HOOK_MODE=strict` (default): block on any non-zero verdict.
- `MNEME_HOOK_MODE=warn`: surface warning to Claude, never block.

Switch to warn mode while iterating on decisions to avoid friction:
```bash
export MNEME_HOOK_MODE=warn
```

## Fail-open guarantees

The hook **never blocks** when:
- `mneme` is not on `$PATH`
- The target file cannot be read (e.g. new file being created via Write)
- `mneme check` times out (> 10 s)
- Any other execution error occurs

In all these cases the hook exits 0 and logs a message to stderr.
Only a real verdict from `mneme check` can block an edit.

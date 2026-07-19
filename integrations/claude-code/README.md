# Mneme for Claude Code

Architectural governance for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).
Enforce ADRs and engineering constraints automatically — before drift reaches your repo.

## Quick install

> **Version requirement:** Use **v0.4.2 or later** for Claude Code hooks.
> v0.4.1 fixed PATH lookup but exit-code propagation was incomplete —
> failed checks could return exit 0 and allow violating edits through.
> v0.4.2 is the first fully reliable hook release.

1. `pip install mneme-hq>=0.4.2`  (or `pip install -e .` from this repo)
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

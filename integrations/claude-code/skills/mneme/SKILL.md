---
name: mneme
description: |
  Architectural governance for this project. Use this skill when the user
  asks about project decisions, architectural constraints, or wants to
  enforce / record / review decisions. Also use whenever Claude Code is
  about to make a non-trivial edit and the project has a `.mneme/`
  directory — check relevant decisions first.
---

# Mneme — project memory & governance

This project uses Mneme to enforce architectural decisions.

## When this skill activates

- User mentions "ADR", "decision", "constraint", "anti-pattern", "architecture".
- A `.mneme/project_memory.json` file exists in the repo.
- About to make a non-trivial edit in an area that may be governed by recorded decisions.

## How to use it

1. **Before non-trivial edits** — run `/mneme-context` with a descriptive task
   phrase (e.g. "storage layer changes", "auth middleware refactor"). Use domain
   language, not just the file name — retrieval is keyword-based and the query
   must overlap with decision scope fields to surface relevant decisions.

2. **To gate a draft** — run `/mneme-check` against the proposed content, again
   with a descriptive `--query`.

3. **To record a new decision** — run `/mneme-record`. When choosing `scope`
   keywords, pick terms that will appear in file names or task descriptions
   where this decision applies, so the hook can retrieve it automatically.

4. **To audit pending changes** — run `/mneme-review`.

## Hook enforcement

A `PreToolUse` hook (`mneme-hook`) runs automatically on Edit / Write / MultiEdit.
It reconstructs the full post-edit file content, then calls `mneme check` with the
query `"edit to <file_path>"`. Decisions whose scope or text share tokens with the
file name are retrieved and checked.

**Retrieval caveat:** The automatic hook query is derived from the file path, so
decisions with scope keywords that don't appear in file names may not be retrieved
automatically. Use `/mneme-context` before large edits to confirm coverage.

If the proposed change violates a decision in strict mode, Claude Code is blocked
and the violated decision id is surfaced in the error.

To switch to warn-only mode: `export MNEME_HOOK_MODE=warn`

## Related

- Project memory: `.mneme/project_memory.json`
- CLI reference: `mneme --help`
- Integration docs: `integrations/claude-code/README.md`

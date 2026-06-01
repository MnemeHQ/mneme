# Mneme for Claude Code

Architectural governance for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).
Automatically enforce your project's architectural decisions before AI-generated edits
reach your repository.

---

## The hook as the hero

Every Edit, Write, or MultiEdit Claude Code attempts is intercepted by `mneme-hook`
before it writes to disk. The hook reconstructs the full post-edit file content, checks
it against your recorded decisions, and either allows the edit (exit 0) or blocks it
with the violated decision id surfaced as feedback (exit 2).

Claude Code sees the block as an error message, can read the decision id and rule, and
adjusts its approach without you having to intervene.

---

## Install

### 1. Install the package

```bash
pip install mneme-hq
```

### 2. Initialise project memory (if you don't have one yet)

```bash
mkdir .mneme
# Create .mneme/project_memory.json — see examples/project_memory.json for the schema.
```

### 3. Run the installer

Project-scoped (recommended — only affects this project):
```bash
python scripts/install_claude_code.py
```

User-scoped (applies to all Claude Code sessions):
```bash
python scripts/install_claude_code.py --user
```

The installer is idempotent — safe to run again after updates.

### 4. Verify

Open Claude Code in your project, make an edit that violates a recorded decision, and
confirm the hook blocks it and surfaces the decision id.

---

## Slash commands

After installing, four slash commands are available in Claude Code:

| Command | Purpose |
|---------|---------|
| `/mneme-context` | Retrieve decisions relevant to your current task |
| `/mneme-check` | Check a file or draft against project memory |
| `/mneme-record` | Record a new architectural decision |
| `/mneme-review` | Audit all pending diff changes against decisions |

---

## Retrieval: what the hook checks and what it misses

The hook query is `"edit to <file_path>"` — tokens from the target file name determine
which decisions are retrieved and checked. Decisions are scored by keyword overlap
between the query and their `scope`, `id`, decision text, and anti-pattern fields.

**What this means in practice:**

- A decision with `scope: ["storage", "database"]` and a file named `storage_layer.py`
  will reliably be retrieved — "storage" appears in both the query and the scope.
- The same decision may **not** be retrieved for an edit to `models.py` — neither token
  overlaps with the scope.
- Generic file names like `utils.py` or `helpers.py` will rarely retrieve any decisions
  at all.

**Mitigations:**

1. Choose scope keywords when recording decisions that match file names in your project.
   Use `/mneme-record` and follow the scope tip in the command.

2. Run `/mneme-context` before non-trivial edits with a descriptive phrase describing
   the domain (e.g. "storage layer", "auth middleware"). This uses a richer query than
   the hook and surfaces decisions the hook might miss.

3. Run `/mneme-review` after a batch of edits to catch violations the per-edit hook
   missed due to retrieval gaps.

The hook is a first line of defence, not a complete audit. Use the slash commands for
coverage on domains where file names are not self-describing.

---

## Modes

| Mode | Behaviour | Set via |
|------|-----------|---------|
| `strict` (default) | Block on any non-zero verdict from `mneme check` | `export MNEME_HOOK_MODE=strict` |
| `warn` | Surface warning to Claude, never block | `export MNEME_HOOK_MODE=warn` |

Switch to `warn` while you're iterating on decisions to avoid friction:
```bash
export MNEME_HOOK_MODE=warn
```

---

## Fail-open guarantees

The hook **never blocks** on execution errors. It exits 0 (allow) when:

- `mneme` is not found on `$PATH`
- The target file cannot be read (common for Write — the file doesn't exist yet)
- `mneme check` times out (limit: 10 s)
- Any other OS-level error occurs

Only a real verdict returned by `mneme check` can cause a block.

---

## Troubleshooting

**Hook is not firing**
- Confirm `mneme-hook` is on `$PATH`: `which mneme-hook` (or `where mneme-hook` on Windows).
- If not, the pip scripts directory may not be on `$PATH`. Add it, or install with `pipx`.
- Confirm `.claude/settings.json` contains the `PreToolUse` entry (run the installer again).

**Hook fires but nothing is blocked**
- Confirm `.mneme/project_memory.json` exists in the project root (or a parent directory).
- Check your decision scope keywords against the file names being edited — see the
  retrieval section above.
- Switch to warn mode temporarily and check stderr output from `mneme-hook` for clues.

**Too many false positives / blocks**
- Switch to `MNEME_HOOK_MODE=warn` while refining your decisions.
- Review the triggered anti-patterns with `/mneme-context` to see if they're too broad.

**`mneme check` is slow**
- The hook has a 10 s timeout and fails open on expiry. Retrieval is fully local and
  deterministic — keyword-overlap scoring over your decisions, with no network calls,
  no embeddings, and no Anthropic API round-trip — so any slowness is local work, not
  API latency. If it's consistently slow, the usual causes are a very large
  `.mneme/project_memory.json` (every decision is parsed and scored on each check) or
  CLI process startup overhead. Trimming or splitting an oversized memory file and
  pruning stale decisions are the effective fixes.

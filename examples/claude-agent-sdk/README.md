# Governed model loop demo — `claude_agent_sdk`

Runnable companion to [PR #293](https://github.com/MnemeHQ/mneme/pull/293),
which added the `mneme.integrations.agent_sdk` package. This folder is a
complete, isolated reproduction of the loop proven there.

## What this proves

1. **Guidance** — relevant decisions are retrieved by the existing
   `DecisionRetriever` and injected into the model's context before any
   work starts (`UserPromptSubmit` -> `additionalContext`).
2. **Enforcement** — a proposed file mutation is materialized, reduced to
   its introduced lines (ADR-018), and evaluated by the same `mneme check`
   path the Claude Code hook uses (`PreToolUse` -> allow/deny).
3. **Correction path** — a blocked proposal carries the governing
   decision id and reason back to the caller. In deterministic mode the
   corrected second proposal is scripted; with `--live`, the model
   performs the correction itself from the block reason.

Mneme governs; the model performs the correction. Mneme itself does not
edit code and does not generate code.

## Run

Deterministic mode — no network call, no API key, fully reproducible:

```
python run.py
```

Live mode — drives one real model session end to end. Requires a working
`claude` CLI login and the official Python package whose import name is
`claude_agent_sdk` (see that project's install docs):

```
python run.py --live
```

## Expected deterministic result

The first proposal uses a forbidden server database driver:

```
mneme: FAIL - architectural decision violated
  [store_001] FAIL "psycopg2" - trigger: psycopg2
      Use SQLite for local storage and database access
```

The corrected proposal passes, and the script exits `0` after printing:

```
RESULT: OK (deny -> correct -> allow)
```

Every event is also recorded on `gated.trace` with a `kind` field
(`context_injection` vs `enforcement`), so guidance and enforcement are
separately auditable.

## Isolation

`project_memory.json` in this folder is **demo data**. It is deliberately
not the canonical memory of this repository and not shared with any other
example.

## Known friction

Editing files inside this folder while a Mneme hook is active can trip one
of the repository's legacy anti-pattern phrases on ordinary prose — a
documented false-positive class (issues #150 / ADR-020). Typed
`FORBID_LITERAL` rules with explicit path selectors are the designed fix;
legacy phrases stay retrieval-gated until migrated.

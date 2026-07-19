# ADR Import

`mneme adr import` lets a team import an existing ADR corpus into Mneme's
enforceable decision memory. The command is deterministic, has a preview
gate before any writes, and surfaces conflicts explicitly rather than silently
resolving them.

---

## Input format

ADR files must be Markdown with a YAML frontmatter block:

```yaml
---
id: ADR-001
title: Use JSON file storage
status: accepted          # proposed | accepted | deprecated | superseded
priority: foundational    # foundational | normal | exception
date: 2026-01-10
scope: storage            # dotted path; empty string = global
supersedes: []            # list of ADR ids this decision replaces
---

Body markdown follows. May include a ## Constraints section (see below).
```

**YAML frontmatter is required.** Nygard-style `**Status:** Accepted`
headers (without frontmatter) are not parsed in this version. Teams using
that format can add a 6-line frontmatter block per file -- this is a
one-time, scriptable conversion.

---

## The `## Constraints` section

ADR bodies may include an optional `## Constraints` section with
machine-readable directives:

```markdown
## Constraints
- FORBID_DEPENDENCY: mongodb
- FORBID_PATH: src/legacy/billing/**
- REQUIRE_PATH: billing/**
```

Directives are parsed strictly. Unknown directive kinds raise a parse error
rather than being silently dropped -- a typo should not defeat governance.

### End-to-end enforcement (MVP)

| Directive | Parsed and stored? | Enforced by `mneme check`? |
|---|---|---|
| `FORBID_DEPENDENCY: X` | Yes, as `"no X"` in Decision.constraints | Yes -- triggers WARN |
| `FORBID_PATH: glob` | Yes, as `"FORBID_PATH glob"` in Decision.constraints | No (stored for visibility) |
| `REQUIRE_PATH: glob` | Yes, as `"REQUIRE_PATH glob"` in Decision.constraints | No (stored for visibility) |

Glob-vs-changed-file enforcement for `FORBID_PATH` and `REQUIRE_PATH` is
out of scope for the MVP -- the existing enforcer is a term-matcher, not a
path-matcher. This is a follow-up capability.

---

## Usage

```bash
# Preview (default -- never writes)
mneme adr import docs/adr --memory .mneme/project_memory.json

# Preview explicitly
mneme adr import docs/adr --memory .mneme/project_memory.json --dry-run

# Apply (writes to memory file)
mneme adr import docs/adr --memory .mneme/project_memory.json --apply

# Allow same-id overwrite of existing decisions[] entries
mneme adr import docs/adr --memory .mneme/project_memory.json --apply --update-existing

# Proceed even if the corpus has an active-active contradiction
mneme adr import docs/adr --memory .mneme/project_memory.json --apply --approve-conflicts
```

### Exit codes

| Code | Meaning |
|:---:|---|
| 0 | Clean preview or successful apply |
| 1 | Dry-run: diagnostics present (active-active contradiction or collisions). Useful as a CI signal. |
| 2 | Apply refused (unresolved diagnostics or invalid input path) |

---

## Walkthrough: dogfooding with Mneme's own ADRs

The `examples/mneme-own-adrs/` directory contains
four of Mneme HQ's own architectural decisions converted to the expected format.
Running the demo shows the full import-to-enforcement pipeline in one command.

```bash
python examples/demo-adr-import.py
```

**What the walkthrough covers:**

1. **Dry-run preview** — scans the corpus, shows active decisions and parsed
   constraints, exits without writing.

2. **Apply import** — writes 4 decisions to a fresh memory file. Two have
   machine-readable constraints:
   - `ADR-002` (repo boundary): three `FORBID_PATH` directives stored for
     visibility (path enforcement is out of scope for the MVP enforcer).
   - `ADR-005` (namespace enforcement): `FORBID_DEPENDENCY: MnemeHQ` compiled
     to `"no MnemeHQ"` and enforced by `mneme check`.

3. **Enforcement check — violation**: the input contains
   `from MnemeHQ.memory_store import MemoryStore`. ADR-005 fires:

   ```
   WARN  [ADR-005] constraint "no MnemeHQ" -- trigger: mnemehq
         Brand vs Package Namespace Enforcement

   Result: WARN
   ```

4. **Enforcement check — clean**: the correct `from mneme.memory_store import
   MemoryStore` passes with `Result: PASS`.

**Note on constraint term specificity.** `FORBID_DEPENDENCY: MnemeHQ` (camelCase)
tokenizes to `"mnemehq"` — a precise 8-character term that only matches the
wrong namespace identifier. The snake_case variant `mneme_hq` would tokenize to
`"mneme"` (the underscore splits words; `"hq"` is filtered for length < 4),
which is too broad to use as an enforcement term against a codebase that
legitimately contains the word "mneme" everywhere.

---

## Conflict model

### 1. Explicit supersession (silent)

If ADR-012 lists ADR-011 in its `supersedes`, ADR-011 is removed from the
active set at compile time. No diagnostic is raised -- explicit supersession
is the intended resolution mechanism.

### 2. Active-active contradiction (loud)

If two accepted ADRs share the same scope, priority, and date, the compiler
cannot pick a winner deterministically. The import command surfaces this as a
diagnostic and either:
- Exits with code 1 in dry-run (shows the problem).
- Refuses `--apply` unless `--approve-conflicts` is also passed.

`--approve-conflicts` imports the rest of the corpus and skips the
contradicting scope. It does not silently pick a winner.

**Fix path:** Edit the contradicting ADRs -- mark one superseded, give one a
higher priority, or give one a newer date.

### 3. Same-id collision (explicit gate)

If an incoming ADR's id already exists in the target memory file's
`decisions[]` or `items[]` array, the import refuses with a diagnostic.

- `--update-existing` allows the colliding entry in `decisions[]` to be
  overwritten in place (preserving its position in the array).
- Cross-section migration (`items[]` to `decisions[]`) is refused even with
  `--update-existing` -- rename the incoming ADR instead.

---

## Persistence

The import writes atomically: it serializes the updated memory to a
sibling temp file in the same directory, then calls `os.replace()` to
swap it in. A failed write leaves the original file intact.

No backup files are created -- the original is always recoverable from git
history.

---

## What is out of scope (explicit)

These are deliberate exclusions, not gaps:

1. **Nygard-without-frontmatter parsing.** Freeform `**Status:** Accepted`
   headers introduce fuzzy parsing into a governance-critical module.
   Add YAML frontmatter to your existing ADRs before importing.

2. **Semantic conflict detection.** Checking whether an incoming constraint
   *semantically overlaps* with an existing manual memory entry is
   inherently fuzzy and has unacceptable false-positive risk. MVP detects
   same-id collisions only.

3. **Glob-based path enforcement** of `FORBID_PATH` / `REQUIRE_PATH`.
   These directives parse and persist but are not matched against changed
   files. The enforcer is a term-matcher; path enforcement is a separate
   design problem.

4. **Anti-pattern modelling via `## Constraints`.**
   `Decision.anti_patterns` stays empty for ADR-derived records in v1.

5. **`mneme adr suggest`.** A future augmentation layer for drafting ADRs
   from existing code patterns. The import flow is its foundation, not its
   replacement.

6. **Modifying `.mneme/project_memory.json` as part of this feature.** Per the
   repo's governance rules, editing the canonical memory file requires a
   separate `[memory]`-tagged PR.

---

## Integration with existing pipeline

Imported decisions enter the existing
`MemoryStore -> DecisionRetriever -> check_prompt` pipeline without any
changes to those modules. Once persisted, they are retrieved by relevance,
injected into context, and enforced by `mneme check` exactly like manually
authored decisions.

```python
# Example: import then check in one session
from mneme.adr_import import compile_for_import, apply_import
from mneme.memory_store import MemoryStore
from mneme.decision_retriever import DecisionRetriever
from mneme.enforcer import check_prompt

report = compile_for_import("docs/adr")
apply_import(report, target_path=".mneme/project_memory.json")

store = MemoryStore(".mneme/project_memory.json")
store.load()
retriever = DecisionRetriever(store.decisions())
scored = retriever.retrieve("can we add mongodb to the analytics service?")
result = check_prompt("Use mongodb for fast writes", scored, top=3)
print(result.verdict)  # Severity.WARN
```

# ADR Import

`mneme adr import` lets a team import an existing ADR corpus into Mneme's
canonical Decision Index. The command is deterministic, has a preview
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
- FORBID_LITERAL: install legacy-package
- FORBID_LITERAL:
    value: install legacy-client
    include_paths:
      - "docs/**"
      - "**/*.md"
    exclude_paths:
      - "docs/generated/**"
- FORBID_DEPENDENCY: mongodb
- FORBID_PATH: src/legacy/billing/**
- REQUIRE_PATH: billing/**
```

Directives are parsed strictly. Unknown directive kinds raise a parse error
rather than being silently dropped -- a typo should not defeat governance.

### End-to-end enforcement (MVP)

| Directive | Parsed and stored? | Enforced by `mneme check`? |
|---|---|---|
| `FORBID_LITERAL: text` | Yes, as a global typed entry in `Decision.rules` | Yes -- exact, case-sensitive, boundary-aware match triggers FAIL |
| Structured `FORBID_LITERAL` with path selectors | Yes, including `include_paths` / `exclude_paths` | Yes when the artifact path is included and not excluded |
| `FORBID_DEPENDENCY: X` | Yes, as `"no X"` in Decision.constraints | Yes -- triggers WARN |
| `FORBID_PATH: glob` | Yes, as `"FORBID_PATH glob"` in Decision.constraints | No (stored for visibility) |
| `REQUIRE_PATH: glob` | Yes, as `"REQUIRE_PATH glob"` in Decision.constraints | No (stored for visibility) |

`FORBID_PATH` and `REQUIRE_PATH` remain retrieval-only directives. Path
applicability is implemented only for typed `FORBID_LITERAL` rules; it does not
give those legacy directive names new semantics.

`FORBID_LITERAL` does not split prose into keywords. It checks the declared
value directly and requires identifier/slug boundaries at identifier-like
edges. For example, `pip install mneme` fails while `pip install mneme-hq`
passes. The comparison is case-sensitive. Typed rules are enforced regardless
of retrieval score; retrieval still controls context injection only. When ADR
source provenance is available, a rule is not applied to its own declaring ADR
or canonical memory file, so policy storage can state the literal it governs.

The scalar form remains global. The structured form requires a non-empty
`include_paths` list; `exclude_paths` is optional and wins when both match.
Patterns are repository-relative, forward-slash, and case-sensitive. `*`
matches within one segment and a complete `**` segment matches zero or more
segments. Absolute paths, backslashes, `.`, `..`, empty segments, negation,
bracket syntax, `?`, and embedded `**` are rejected during compilation.

An active ADR with no mechanically enforceable rules is still importable for
retrieval, but preview prints a `Retrieval-only ADR warnings` diagnostic. A
dry-run with that warning exits 1 so CI cannot mistake a toothless import for a
clean enforcement payload. `--apply` may still persist the decision and exits 0
when the write succeeds.

---

## Usage

```bash
# Preview (default -- never writes)
mneme adr import docs/adr --memory .mneme/project_memory.json

# Preview explicitly
mneme adr import docs/adr --memory .mneme/project_memory.json --dry-run

# Apply (writes to memory file)
mneme adr import docs/adr --memory .mneme/project_memory.json --apply

# Evolve an existing same-id decision as a new immutable canonical version
mneme adr import docs/adr --memory .mneme/project_memory.json --apply --update-existing

# Retry an earlier --update-existing apply after a later version became active,
# pinning the version that was active when the original apply ran
mneme adr import docs/adr --memory .mneme/project_memory.json --apply --update-existing \
  --expected-predecessor ADR-012=dver-0123456789abcdef0123456789abcdef

# Import every non-conflicting scope and skip each active-active contradiction
mneme adr import docs/adr --memory .mneme/project_memory.json --apply --approve-conflicts
```

### Exit codes

| Code | Meaning |
|:---:|---|
| 0 | Clean preview or successful apply |
| 1 | Dry-run: diagnostics present: retrieval-only ADRs, active-active contradictions, collisions, protection continuity obligations, or supersession enforcement effects (a supersession that retires `protection`/`legacy_unknown` rules). Useful as a CI signal. |
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

### 1. Explicit supersession (authorized, visible)

If ADR-012 lists ADR-011 in its `supersedes`, ADR-011 is removed from the
active set at compile time. On apply, D1D persists the explicit canonical
`supersedes` relationship and transitions ADR-011 to canonical
`superseded`; its historical version remains queryable but no longer
projects into active Layer 1 governance.

The `supersedes` relationship is the authority for retiring ADR-011, so no
extra flag is needed. Retirement is never hidden, though. If ADR-011 carries
`protection` or `legacy_unknown` rule bindings, the preview lists them under
**Supersession enforcement effects**, because their enforcement leaves
Layer 1. The dry-run then exits `1`, like any other diagnostic, so CI
notices. See "Protection continuity" below.

### 2. Active-active contradiction (loud)

If two accepted ADRs share the same scope, priority, and date, the compiler
cannot pick a winner deterministically. The import command surfaces this as a
diagnostic and either:
- Exits with code 1 in dry-run (shows the problem).
- Refuses `--apply` unless `--approve-conflicts` is also passed.

`--approve-conflicts` imports the rest of the corpus and skips every
contradicting scope. Precedence is resolved per scope, so each tied scope
is reported and left out (including any lower-precedence ADRs in it) while
all other scopes import normally. The apply output lists each skipped
scope. It does not silently pick a winner.

**Fix path:** Edit the contradicting ADRs -- mark one superseded, give one a
higher priority, or give one a newer date.

### 3. Same-id collision (explicit gate)

If an incoming active ADR's id already exists in canonical decision authority,
the import refuses with a diagnostic.

- `--update-existing` does **not** overwrite history. It creates or reuses an
  immutable version occurrence whose identity is bound to the prior active
  `version_id`, then advances the logical decision's `active_version_id`.
- Prior version records and prior rule bindings remain immutable and queryable.
- Rules are re-derived explicitly from the incoming ADR. An unchanged rule keeps
  its stable `rule_id` but binds to the new `decision_version_id`; a removed
  rule is not silently carried forward.
- A collision with a legacy `items[]` id is still refused even with
  `--update-existing`; ADR authority does not silently repurpose item identity.

#### Retries versus new operations

An `--update-existing` apply without a pin is a **new authority operation**:
its predecessor is whatever version is active when it runs. So restoring an
ADR to earlier content after a later version is active is a deliberate
revert, and it creates a new occurrence. A1 → B → A2 is three occurrences
even though A1 and A2 have identical content.

To **retry** an earlier operation after a later version became active, pin
the predecessor that operation ran against:

- The preview lists `current predecessor: dver-...` for each existing
  same-id decision. That is the persisted active version at the moment of
  reading. Record it if you may need to retry the apply later; reading it
  creates no retry identity.
- `--expected-predecessor ADR-ID=VERSION_ID` is repeatable, at most once per
  ADR. It is valid only with `--apply --update-existing`, and only for an
  incoming ADR that is already canonical. It must name a persisted version of
  that decision.
- With a pin:
  - if the exact occurrence (decision, content, source revision, pinned
    predecessor) already exists anywhere in history, the apply reuses it and
    changes nothing, even if a newer version is active;
  - if it does not exist and the pinned version is still active, it is
    created;
  - otherwise the apply fails closed as stale.
- Malformed, duplicate, unknown, or not-yet-canonical pins are refused before
  any write.

#### Protection continuity (ADR-030 §9a)

A `protection` or `legacy_unknown` rule binding never disappears silently
when an ADR evolves into a new version. A `legacy_unknown` binding is a
migrated pre-D1 rule whose origin cannot be reconstructed. The preview lists
every such binding the new ADR content would no longer derive, under
**Protection continuity obligations**, with its `rule_id`. Each one needs an
explicit decision:

```bash
mneme adr import docs/adr --memory .mneme/project_memory.json --apply --update-existing \
  --preserve-protection 'ADR-012:FORBID_LITERAL:<hash>' \
  --release-protection  'ADR-012:FORBID_LITERAL:<hash>'
```

- `--preserve-protection RULE_ID` carries the exact rule into the new
  version. Your flag is the authority; Mneme only re-runs the deterministic
  protection validation against the new version. Only a global
  `FORBID_LITERAL` can be preserved; anything else must be released.
- `--release-protection RULE_ID` omits the rule. If the new ADR still
  derives it, the rule stays, as an ordinary version rule.
- With neither flag, the apply refuses and writes nothing. If the new ADR
  still derives the rule, nothing is needed: the rule keeps its protection.
- Both flags are repeatable and need `--apply --update-existing`. These are
  refused before any write:
  - naming a rule for both flags;
  - an unknown rule;
  - a rule that is not a `protection`/`legacy_unknown` binding;
  - preserving a rule the new ADR still derives;
  - requests for a decision that is not evolving.
- A retry with the same flags is a no-op. A retry with different flags fails
  closed.

Superseding a decision through another ADR's `supersedes` retires it, so it
needs no per-rule release. The preview lists its protected rules under
**Supersession enforcement effects**, because their enforcement leaves
Layer 1, and the dry-run exits `1`. That warning does not block `--apply`;
the `supersedes` relationship is the authority.

---

## Persistence

`--apply` requires canonical memory. If the target has no `decision_index`
section, the import refuses and changes nothing. ADR import never migrates
implicitly. The only transition is the explicit migration command: preview it
first, then apply it.

```bash
mneme decision-index migrate --memory .mneme/project_memory.json
mneme decision-index migrate --memory .mneme/project_memory.json --apply
```

The authoritative write target is the `decision_index` section. After the
canonical mutation validates, Mneme regenerates `decisions[]` only as the
deprecation-window compatibility projection and verifies it against the same
canonical index before the atomic file replace.

The import serializes the complete updated memory to a sibling temp file in the
same directory, then calls `os.replace()`. A failed write leaves the original
file intact. Repeating an identical ADR occurrence is idempotent: it does not
create a phantom version.

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

4. **Automatic Correct/Forbidden table inference.** Tables remain human
   documentation. Authors must declare `FORBID_LITERAL` explicitly; the
   compiler does not guess which table cells are executable policy.

5. **Anti-pattern modelling via `## Constraints`.**
   `Decision.anti_patterns` stays empty for ADR-derived records in v1.

6. **`mneme adr suggest`.** A future augmentation layer for drafting ADRs
   from existing code patterns. The import flow is its foundation, not its
   replacement.

7. **Modifying `.mneme/project_memory.json` as part of this feature.** Per the
   repo's governance rules, editing the canonical memory file requires a
   separate `[memory]`-tagged PR.

---

## Integration with existing pipeline

Imported decisions enter the
`MemoryStore -> DecisionRetriever -> check_prompt` pipeline. Legacy constraints
retain their historical behavior; typed rules are loaded separately and
enforced deterministically by `mneme check`.

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

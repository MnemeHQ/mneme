---
id: ADR-003
title: Architectural Compiler Contract — ADR Schema, Validation, and Precedence
status: accepted
priority: foundational
date: "2026-05-27"
scope: compiler
---

# Context

Mneme v0.4.0 introduced an architectural compiler that turns a directory of
ADR markdown files into a deterministic active constraint set. The compiler
is now a public artifact — installable via `pip install mneme-hq` — and its
input schema, validation rules, and precedence semantics are a stable contract
that downstream users depend on.

This ADR records that contract precisely so it can be verified against the
implementation, cited in documentation, and used as the acceptance criterion
for any future change to the compiler.

The contract was implicit in `adr_schema.py`, `adr_compiler.py`, and
`adr_constraints.py`. This document makes it explicit.

# Decision

## 1. Frontmatter Schema

Each ADR file must have a YAML frontmatter block. All fields listed as
required must be present and non-empty.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Pattern `ADR-\d+`. Unique across the corpus. |
| `title` | string | yes | One-line human-readable label. |
| `status` | enum | yes | `proposed`, `accepted`, `deprecated`, or `superseded`. |
| `priority` | enum | yes | `foundational`, `normal`, or `exception`. |
| `date` | string | yes | ISO 8601 date — `YYYY-MM-DD`. |
| `scope` | string | no | Dotted-path; empty string means global. Defaults to `""`. |
| `supersedes` | list[string] | no | ADR ids this record explicitly replaces. Defaults to `[]`. |

**Scope grammar**: lowercase letters, digits, and underscores (`[a-z0-9_]+`),
dot-separated. No leading or trailing dot. Empty string is the global scope.
Examples: `""`, `"storage"`, `"storage.embeddings"`.

**Status meanings**:
- `proposed` — drafted but not yet adopted; excluded from the active set.
- `accepted` — adopted and currently in force; included unless superseded.
- `deprecated` — no longer in force; excluded.
- `superseded` — replaced by a newer ADR via `supersedes`; excluded.

**Priority rank** (highest to lowest): `foundational` > `normal` > `exception`.

## 2. Validation Rules

`validate_corpus` runs all checks before raising, so a single compiler pass
surfaces every problem. The raised `ADRValidationError` carries a list of
human-readable error strings, one per detected problem.

**Per-record checks (applied to every ADR in the corpus):**

1. All required fields (`id`, `title`, `status`, `priority`, `date`) are
   present and non-empty.
2. `status` is one of the four valid values.
3. `priority` is one of the three valid values.
4. `id` matches `ADR-\d+`.
5. `date` parses as ISO 8601 (`YYYY-MM-DD`).
6. `scope` either is empty or passes the grammar above (no leading/trailing
   dot; all segments match `[a-z0-9_]+`).

**Cross-record checks (applied to the whole corpus):**

7. No duplicate `id` values.
8. Every id in `supersedes` lists references a known ADR in the corpus.
9. The supersession graph has no cycles — self-supersession (`A -> A`),
   two-node cycles (`A -> B -> A`), and N-node cycles are all rejected.

Validation does not distinguish between warning and error: every detected
problem is a hard error. Silently ignoring a bad record would let a typo
defeat governance.

## 3. Precedence Resolution

`resolve_precedence` produces the **active constraint set** — the subset of
accepted ADRs that the runtime injects. The algorithm is deterministic: the
same corpus always produces the same output.

**Stages (applied in order):**

1. **Status filter**: only ADRs with `status == "accepted"` enter the
   resolution pipeline.

2. **Explicit supersedes**: any ADR whose `id` appears in another accepted
   ADR's `supersedes` list is removed. Chain resolution applies — if A
   supersedes B and B supersedes C, both B and C are removed when A is
   accepted.

3. **Same-scope conflict resolution**: ADRs sharing the same `scope` value
   compete. The winner is chosen by this tiebreaker chain:
   - **Higher priority wins** (`foundational` > `normal` > `exception`).
   - **Newer date wins** on a priority tie.
   - **`ADRPrecedenceError` raised** if priority and date both tie. The
     compiler never silently picks a winner.

4. **Scope coexistence**: ADRs with different scopes (including broader vs.
   narrower, e.g. `"storage"` and `"storage.embeddings"`) do **not** conflict
   at compile time. All surviving ADRs from distinct scopes coexist in the
   active set.

5. **Deterministic output ordering**: the active set is sorted by
   `(-specificity, -priority_rank, id)`, where specificity is the number of
   dot-separated segments in the scope (empty = 0). This places
   most-specific-first, with priority and id as stable tiebreakers.

## 4. Constraints Section

ADR bodies may include an optional `## Constraints` section listing
machine-actionable directives. The section is bounded by the next H2 header
or the end of the body.

**Format:**

```markdown
## Constraints
- FORBID_DEPENDENCY: mongodb
- FORBID_PATH: src/legacy/**
- REQUIRE_PATH: billing/**
```

**Valid directive kinds:**

| Kind | Meaning | Enforcement |
|---|---|---|
| `FORBID_DEPENDENCY` | Named dependency must not be introduced | Full — rendered as `"no X"` in constraints; triggers WARN in `mneme check` |
| `FORBID_PATH` | File path pattern is off-limits | Stored for retrieval visibility; glob-vs-file enforcement not yet implemented |
| `REQUIRE_PATH` | File path pattern must exist | Stored for retrieval visibility; glob-vs-file enforcement not yet implemented |

Unknown directive kinds raise `ConstraintParseError` immediately. Silently
dropping unknown kinds would let typos produce false-clean governance.

## 5. Decision Bridge

`adrs_to_decisions` converts compiled ADR records into `Decision` records for
the runtime pipeline (retriever, conflict detector, context builder). This
bridge is the only coupling between the compiler and the runtime; neither side
needs to know about the other's internals.

**Mapping:**

| ADR field | Decision field | Notes |
|---|---|---|
| `id` | `id` | Copied verbatim. |
| `title` | `decision` | One-line decision text. |
| `body` | `rationale` | Full markdown body. |
| `scope` | `scope` | Wrapped in a single-element list: `[adr.scope]`. |
| `date` | `created_at`, `updated_at` | Same value for both. |
| Constraints directives | `constraints` | `FORBID_DEPENDENCY: X` → `"no X"`; `FORBID_PATH`/`REQUIRE_PATH` stored verbatim. |
| — | `anti_patterns` | Always `[]` in v1; anti-pattern modelling stays in manual memory. |

## 6. Public API Surface

The following are stable public entry points. All other symbols in the
compiler modules are internal.

```python
from mneme.adr_compiler import compile_adrs, adrs_to_decisions

# Parse, validate, and resolve an ADR directory in one call.
active_adrs: list[ADR] = compile_adrs("docs/adr")

# Convert to Decision records for the runtime pipeline.
decisions: list[Decision] = adrs_to_decisions(active_adrs)
```

Lower-level entry points for callers who need individual stages:

```python
from mneme.adr_compiler import validate_corpus, resolve_precedence
from mneme.adr_parser import parse_adr_directory

adrs = parse_adr_directory("docs/adr")  # list[ADR], may raise ADRParseError
validate_corpus(adrs)                    # raises ADRValidationError on any problem
active = resolve_precedence(adrs)        # raises ADRPrecedenceError on ambiguity
```

**Error types and when they raise:**

| Exception | Raised by | Cause |
|---|---|---|
| `ADRParseError` | `parse_adr_directory` | File missing YAML frontmatter or unparseable YAML |
| `ADRValidationError` | `validate_corpus` | Any schema, format, or graph violation (all errors aggregated) |
| `ADRPrecedenceError` | `resolve_precedence` | Two accepted ADRs share scope and tie on priority and date |

# Enforcement

Any change to the compiler that alters the schema, validation rules, precedence
algorithm, constraints grammar, or Decision bridge mapping must cite this ADR
and update it in the same PR. A compiler change without a matching ADR-003
update is a governance violation.

`FORBID_PATH` and `REQUIRE_PATH` glob-vs-file enforcement is explicitly
out of scope for the v1 compiler. When that enforcement lands, ADR-003 must
be updated.

`mneme adr compile` as a CLI subcommand is not yet implemented. This ADR
documents the library contract only. The CLI UX is a separate decision,
deferred until there is adoption signal.

## Constraints

- FORBID_DEPENDENCY: langchain

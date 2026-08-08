---
id: ADR-019
title: "Typed Literal Rule Vocabulary"
status: accepted
priority: foundational
date: 2026-08-08
scope: enforcement.literal_rules
---

# ADR-019: Typed Literal Rule Vocabulary

**Status:** Accepted
**Date:** 2026-08-08
**Deciders:** Theo Valmis

---

## Context

ADR-005 forbade a specific install command by name, in a Correct/Forbidden
table — about as mechanically enforceable as prose gets. mnemehq.com shipped
the forbidden string for months anyway.

The cause was not staleness. `VALID_KINDS` held only `FORBID_DEPENDENCY`,
`FORBID_PATH` and `REQUIRE_PATH`, so a **content rule was inexpressible**, and
`adr_compiler` hardcodes `anti_patterns=[]`, so an ADR could only ever produce
WARN-severity constraints, never FAIL. All 9 ADR-sourced decisions carried
`constraints: []` and `anti_patterns: []`. The decision had nothing to enforce
from its first import.

The gap was filled by hand: `scripts/check_install_command.py`, a bespoke regex
script with its own allowlist and its own tests, duplicated verbatim into a
second repository — Mneme's own value proposition reimplemented outside Mneme,
twice, because the product had no way to say "never write this string".

### Why the existing fields cannot carry it

Reusing `anti_patterns` fails, and the failure is instructive:

- **Term matching** explodes the rule into `[pip, install, mneme]` and fires on
  any single token, so it flags the *correct* command, plus any prose
  containing the word "install". Measured at 100% false positives, including on
  the right answer. Same root cause as #150.
- **Plain substring matching** fails because the forbidden literal is a
  substring of the correct command.
- **Word-boundary matching** fails too, because the hyphen is itself a word
  boundary.

## Decision

1. **Two new directive kinds.** `FORBID_STRING: <literal>` names an exact
   forbidden string. `ALLOW_CONTAINING_STRING: <literal>` exempts occurrences
   of the preceding prohibition that it fully contains.

2. **Named for what it does.** The exemption is not `ALLOW_STRING`, which would
   read as "this string is permitted". It does not permit a string; it
   suppresses forbidden spans *contained by* it. An author who reads the looser
   name writes an exemption that does not do what they expect, and a rule that
   silently fails to apply is the exact failure this vocabulary exists to
   prevent.

3. **Literal spans with containment suppression.** Find every case-insensitive
   occurrence of the forbidden literal; suppress an occurrence only when an
   allowed container fully contains it; report the rest at FAIL severity.

4. **Containment is strict, not overlap.** An exemption must cover the whole
   forbidden literal including any prefix. Take a prohibition on the three-word
   install command ending in the bare project name, exempted by
   `ALLOW_CONTAINING_STRING: install mneme-hq` — the exemption omits the
   leading `pip `, so it overlaps the forbidden span without containing it, and
   the correct command is still reported. This is a real authoring hazard, and
   it is pinned by test rather than smoothed over: widening the rule to
   "overlaps" would let a narrow exemption silently disable a broad
   prohibition. (Stated indirectly here because writing the forbidden form out
   would trip this repository's own ADR-005 gate — an instance of the
   self-reference problem noted under Consequences.)

5. **Exemptions are per-rule, not a decision-level pool.** Stored as
   `ForbiddenLiteral(value, allowed_containers)`. A flat shared pool would let
   an exemption written for one prohibition neuter an identically-worded
   prohibition added later for a different reason.

6. **Association is positional.** An `ALLOW_CONTAINING_STRING` attaches to the
   nearest `FORBID_STRING` above it, so the pairing is visible on the page
   rather than mediated by an id the author has to invent. An exemption with no
   preceding prohibition is a parse error, not a no-op.

7. **New fields, not overloaded ones.** `Decision.literal_rules` is separate
   from `constraints` and `anti_patterns`, whose term-matching semantics are
   materially different. A literal rule does not additionally become a
   constraint string; routing it through the term matcher would reintroduce the
   false positives it exists to avoid.

8. **Literals now, not regex.** Regex would cover variable whitespace and
   multiple package-manager syntaxes, but costs readability in governance
   documents, engine-specific behaviour, ReDoS exposure, and escaping inside
   Markdown. If real rules later need patterns, that is a distinct
   `FORBID_PATTERN` capability with bounded input and compilation validation —
   not a change to this primitive.

9. **Not retrieval-gated.** Typed literal rules are enforceable by
   construction, so they are evaluated against every decision regardless of
   retrieval score. This closes #254 for these rules outright, rather than via
   the term-count proxy ADR-017 uses as an interim measure.

## Consequences

- ADR-005's rule is expressible and enforced: authored in an ADR body,
  compiled to a `Decision`, and applied by the enforcer, with the correct
  command passing and the forbidden one failing. Test coverage walks that full
  path.
- ADR-sourced decisions can now reach FAIL severity. Only via an explicit new
  directive, so no existing memory changes behaviour: absent `literal_rules`
  loads as an empty list and existing files are untouched on write.
- `scripts/check_install_command.py` becomes replaceable in principle. It is
  deliberately **not** removed here — that needs the repo-wide check mode
  (#251), since the script scans every tracked file and `mneme check` is still
  single-file.
- The term-count proxy in ADR-017 stays until enough rules are expressed as
  literals to retire it. This ADR provides the replacement primitive; migration
  is separate.
- Self-reference is **not** solved. A test carrying the forbidden string as
  fixture data still trips a repo-wide gate — `tests/test_literal_rules.py` had
  to be added to `check_install_command.py`'s path allowlist while building
  this. That hand-maintained allowlist is a second source of truth that drifts
  from the decision record, which is precisely what per-rule exemptions are
  meant to replace. Closing it needs rule applicability (#150) and #259.

## Related

- ADR-017: Enforcement Scope Is Independent of Retrieval Scope — the interim
  term-count proxy this vocabulary is designed to retire
- ADR-005: Brand vs Package Namespace Enforcement — the rule that was
  inexpressible
- Issues #250 (this decision), #258 (parser strictness, a prerequisite), #259
  (self-reference), #150 (rule applicability), #251 (repo-wide check mode)

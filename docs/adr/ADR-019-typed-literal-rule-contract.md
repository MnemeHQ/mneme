---
id: ADR-019
title: "Typed Literal Rule Contract"
status: accepted
priority: foundational
date: 2026-08-11
scope: enforcement.typed_rules
---

# ADR-019: Typed Literal Rule Contract

**Status:** Accepted
**Date:** 2026-08-11
**Deciders:** Theo Valmis

---

## Context

ADR-017 separated enforcement scope from retrieval scope, but it could only use
term count as an interim proxy for whether legacy constraint prose was safe to
enforce corpus-wide. Issue #250 then exposed the missing durable primitive: an
ADR could describe a literal prohibition, but the parser, compiler, persisted
memory, and runtime had no explicit type with deterministic semantics for it.

PR #268 shipped that primitive and PR #269 activated it for ADR-005. A competing
proposal in PR #264 used a different vocabulary and matching model:
`FORBID_STRING`, `ALLOW_CONTAINING_STRING`, case-insensitive search, and
containment-based suppression. That proposal was closed unmerged after #268 and
#269 shipped. This ADR records the contract on `main`, not the superseded
proposal.

## Decision

1. **The typed vocabulary starts with `FORBID_LITERAL`.** An ADR declares it as
   a bullet under `## Constraints`:

   ```text
   - FORBID_LITERAL: import legacy_client
   ```

   The compiler stores it as a typed `Rule`, separate from legacy
   `constraints` and `anti_patterns`. Unknown rule types and blank values are
   invalid rather than silently ignored.

2. **Matching is exact and case-sensitive.** The runtime searches for the
   authored character sequence without normalization. It does not fold case,
   normalize package names, tokenize shell commands, or interpret regular
   expressions.

3. **Identifier boundaries prevent prefix false positives.** If either edge of
   the literal is identifier-like, the adjacent input character cannot be an
   ASCII letter, digit, underscore, or hyphen. Thus a standalone identifier can
   be forbidden without also matching a longer identifier that contains it.
   These boundary rules are part of `FORBID_LITERAL`; they are not an implicit
   allow-list or a containment exemption.

4. **Typed literal enforcement is independent of retrieval.** Every supplied
   decision's typed literal rules are evaluated regardless of lexical score or
   the `--top` cutoff. Retrieval continues to rank context; it does not decide
   whether an explicit typed rule is enforced.

5. **A match is a deterministic `FAIL`.** Human and JSON diagnostics identify
   the violation as a typed rule and include `FORBID_LITERAL` as its rule type.
   Conflict detection uses the same matcher rather than the legacy negation
   heuristic.

6. **Only canonical policy sources are automatically exempt.** When provenance
   is available, a rule does not enforce against the exact ADR file that
   declares it or the exact project-memory file that stores it. This permits the
   policy to represent its own forbidden value. There is no general exemption
   for documentation, tests, examples, or matcher implementation files.

7. **The rule survives the complete ADR pipeline.** Parsing, compilation,
   preview, persistence, memory loading, context output, CLI output, and runtime
   enforcement preserve the typed rule. ADR tables and prose are not inspected
   to infer rules; mechanical enforcement requires an explicit directive.

8. **Retrieval-only ADRs remain valid.** An active ADR with no mechanically
   enforceable directive may still be imported for retrieval. Import reports
   that state as a diagnostic rather than inventing a rule or rejecting the
   ADR.

9. **Other matching semantics require another explicit rule type.** The
   containment exemption anticipated in ADR-017 did not ship and is not part of
   `FORBID_LITERAL`. Neither are case-insensitive matching, regex, structured
   command parsing, path applicability, or occurrence-level exceptions. Adding
   any of them requires separately specified validation, matching, persistence,
   diagnostics, and regression behavior; `FORBID_LITERAL` itself must not
   silently change meaning.

## Consequences

- Issue #250 remains complete: ADR authors can express a deterministic literal
  prohibition and the rule is enforced independently of retrieval score.
- Existing memory remains backward compatible because decisions without
  `rules` load with an empty list.
- ADR-005 dogfoods the new primitive, but its one exact literal is intentionally
  narrower than the dedicated install-command gate. Package-manager variants,
  command flags, case normalization, and editable installs remain separate
  concerns until a command-aware rule type is designed.
- The term-count proxy from ADR-017 remains for legacy rules until those rules
  are migrated or their blocking safety is established with evidence.
- Rule applicability, self-reference outside canonical policy sources,
  introduced-delta enforcement, and repository-wide checking remain open under
  issues #150, #259, and #251. This ADR does not pre-decide those designs.

## Rejected Alternative

The unmerged PR #264 design paired case-insensitive `FORBID_STRING` rules with
positional `ALLOW_CONTAINING_STRING` directives. It is rejected as the current
contract because it differs from the implementation that shipped and would
make the same persisted rule depend on semantics absent from `main`. Its
applicability and self-reference observations remain useful input to #150 and
#259.

## Related

- ADR-005: Brand vs Package Namespace Enforcement
- ADR-017: Enforcement Scope Is Independent of Retrieval Scope
- Issues #150, #250, #251, #254, and #259
- PRs #264 (closed, unmerged), #268 (runtime), and #269 (memory adoption)

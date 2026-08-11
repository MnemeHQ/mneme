---
id: ADR-020
title: "Explicit Path Applicability for Typed Rules"
status: accepted
priority: foundational
date: 2026-08-11
scope: enforcement.rule_applicability
---

# ADR-020: Explicit Path Applicability for Typed Rules

**Status:** Accepted
**Date:** 2026-08-11
**Deciders:** Theo Valmis

---

## Context

ADR-017 separated retrieval from enforcement, ADR-018 limited the edit gate to
introduced content, and ADR-019 established the deterministic
`FORBID_LITERAL` rule. Those decisions answer three different questions:

1. which decisions are considered;
2. which changed text is checked; and
3. whether a literal occurs in that text.

They do not answer whether a particular rule applies to the artifact being
checked.

That missing dimension is visible in issues #150 and #259. Code-oriented legacy
anti-patterns such as `open() without encoding= in Python` are split into
generic terms and fire on prose containing words such as `open` or `without`.
A typed literal is mechanically precise, but it still matches legitimate tests,
policy machinery, and explanatory examples outside its declaring ADR and
canonical memory file.

### Current dogfood evidence

A whole-file scan of the 2026-08-11 repository state checked 268 UTF-8-readable
files from 275 tracked paths using each path as its edit query:

| Result | Count |
|---|---:|
| PASS files | 210 |
| FAIL files | 58 |
| Legacy anti-pattern violations | 104 |
| Typed literal violations | 19 |

Of the 104 legacy anti-pattern violations, 71 occurred in prose-class files, 30
in code or automation files, and 3 in other files. Representative triggers were
the individual words `content`, `without`, `governance`, `open`, `any`,
`enforcement`, and `main`. File type alone would reduce some noise but would
not repair a matcher that treats any one term from a descriptive phrase as the
whole rule.

All 19 typed-literal matches were manually classified as tests, fixtures, rule
implementation, workflow commentary, or explanatory policy material. The
dedicated install-command gate passed over the same checkout because it carries
additional command semantics and reviewed exceptions. This does not make
`FORBID_LITERAL` imprecise: it proves that exact matching and artifact
applicability are independent concerns.

### Requirements

An applicability mechanism must be deterministic, authored with the rule,
preserved by the ADR-to-memory pipeline, explainable in diagnostics, and stable
across operating systems. It must not become an invisible global allowlist or
silently change the meaning of an existing rule type.

## Decision

1. **Matching and applicability are orthogonal.** A rule type defines what
   constitutes a content match. Optional rule-level path selectors define where
   that matcher is eligible to run. Retrieval score, introduced-content
   selection, applicability, and matching remain separate stages.

2. **Applicability belongs to typed rules, not decisions or legacy prose.**
   Each typed `Rule` may carry `include_paths` and `exclude_paths`.
   Rule-level placement is required because two rules in one decision can
   legitimately govern different artifacts. Legacy `constraints` and
   `anti_patterns` do not acquire selectors by inference.

3. **No selectors means global applicability.** An existing rule without
   `include_paths` or `exclude_paths` keeps its current corpus-wide
   semantics. When selectors are present, a rule applies only when at least one
   include matches and no exclude matches. `include_paths` is required and
   non-empty for a scoped rule; exclusions always win.

4. **Selectors use a deliberately small path grammar.** Patterns are
   case-sensitive, repository-relative, forward-slash paths. A literal segment
   matches itself, `*` matches zero or more characters within one segment, and
   a complete `**` segment matches zero or more path segments. Absolute paths,
   backslashes, `.` or `..` segments, empty segments, negation, bracket
   expressions, and `**` embedded inside another segment are invalid. Invalid
   selectors fail validation rather than being ignored.

5. **The policy root is derived deterministically.** For canonical
   `.mneme/project_memory.json`, the root is the directory containing
   `.mneme`. For another explicitly supplied memory file, the root is that
   file's parent. Input paths are resolved, required to be inside that root, and
   normalized to a forward-slash relative path before selector evaluation.

6. **Unavailable applicability is not a silent PASS.** A scoped rule whose
   input path is missing, outside the policy root, or otherwise cannot be
   normalized is not matched and produces an explicit
   `PATH_APPLICABILITY_UNKNOWN` diagnostic. Path-aware CLI surfaces treat that
   as an operational evaluation failure. Integrations retain their documented
   transport failure policy, but must expose the reason. Text-only conflict
   detection must accept a target path or report that a scoped rule was not
   evaluated.

7. **Applicability is traceable.** Machine-readable evaluation records identify
   the decision, rule type and value, normalized input path, outcome
   (`APPLIED`, `EXCLUDED`, or `UNKNOWN`), and the selector responsible.
   Human diagnostics include the matched include selector for a violation.
   Ordinary successful output need not list every skipped rule unless an
   explain/trace surface is requested.

8. **Canonical policy-source exemptions remain automatic and exact.** The
   declaring ADR and canonical memory file exemptions from ADR-019 continue to
   take precedence. Any broader exemption for tests, documentation, examples,
   migration material, or matcher implementation must be expressed on the
   individual rule through `exclude_paths`; there is no repository-global
   exemption list.

9. **ADR authoring gains a strict structured form while preserving the scalar
   shorthand.** Existing global directives remain valid:

   ```text
   - FORBID_LITERAL: install legacy-client
   ```

   A scoped rule is authored under `## Constraints` as:

   ```yaml
   - FORBID_LITERAL:
       value: install legacy-client
       include_paths:
         - "**/*.md"
         - ".github/workflows/**"
       exclude_paths:
         - "docs/history/**"
         - "tests/**"
   ```

   The parser accepts only `value`, `include_paths`, and `exclude_paths`
   for this rule type. Unknown keys, non-string patterns, a blank value, or an
   empty `include_paths` list are errors. Compilation, preview, persistence,
   memory loading, context output, and enforcement preserve the selectors.

10. **This decision does not reclassify legacy enforcement.** The current
    retrieval-gated behavior and FAIL/WARN severities of legacy constraints and
    anti-patterns remain unchanged until benchmark evidence supports a separate
    migration decision. The dogfood counts above show why multi-term lexical
    phrases are not automatically promoted to typed blocking rules.

11. **Applicability does not add matcher semantics.** Path selectors cannot
    determine whether a Python call omitted an argument, whether an install
    command is editable, or whether prose is quoting a forbidden command as a
    negative example. Those require separately specified typed rule classes.
    `FORBID_LITERAL` remains exact and case-sensitive; it is not weakened or
    made command-aware.

## Consequences

- Rules can explicitly exclude fixture or implementation paths without a
  hidden central allowlist.
- A global typed rule remains available when its author truly intends every
  repository artifact to be governed.
- The same file can be governed by one rule and excluded from another.
- Path applicability can prevent cross-artifact false positives, but it cannot
  solve mixed prose and executable examples within one file. A future
  command-aware rule or separately designed occurrence escape is still needed
  for that case.
- Existing memories and ADR directives remain valid because omitted selectors
  preserve current behavior.
- Applicability metadata must land through the complete typed-rule pipeline
  before any live rule adopts it. Adding selectors to canonical memory remains
  a separate `[memory]` change.
- Issue #259 remains open until the mechanism is implemented and a reviewed
  rule demonstrates non-canonical self-reference handling. Issue #150 remains
  open for code-aware matching and evidence-backed legacy-rule classification.
- Benchmark fixtures are freeze-governed in this repository. An implementation
  that claims blocking safety from benchmark changes must follow the freeze
  amendment procedure rather than altering fixtures incidentally.

## Implementation boundary

The first implementation PR is limited to the typed-rule schema, strict ADR
parsing and compilation, persistence/loading, deterministic path matching,
evaluation traces, and focused regression tests. It must not:

- change legacy FAIL/WARN semantics;
- add path selectors to live project memory;
- modify benchmark fixtures without the required freeze amendment;
- add command parsing or occurrence escapes; or
- close #150 or #259 merely because the metadata shape exists.

A subsequent ADR/rule-adoption PR may select paths for a live rule, followed by
an isolated `[memory]` synchronization. A command-aware typed rule is a
separate decision after applicability is implemented.

## Alternatives considered

**Content classes such as code, prose, or documentation.** Rejected as the
primitive because Markdown contains executable commands, source files contain
comments and fixtures, and extension-to-class mappings become another implicit
policy layer. Authors may express file groups with explicit path selectors.

**Decision-level selectors.** Rejected because they over-scope every rule in a
decision and prevent rules with different target artifacts from coexisting.

**A global repository allowlist.** Rejected because it separates exemptions
from the rule they weaken and recreates invisible governance.

**Automatic exemption for all tests or documentation.** Rejected because tests
and documentation can contain real user-facing instructions and executable
examples. Any exemption must be explicit per rule.

**Containment suppression.** Rejected as a general self-reference solution.
Correct and forbidden examples may be separate spans or lines, and containment
does not express artifact applicability.

**An inline escape syntax in this decision.** Deferred. An escape is
occurrence-level authorization with different bypass and audit risks from path
applicability; it needs its own contract rather than being hidden in glob
semantics.

## Related

- ADR-017: Enforcement Scope Is Independent of Retrieval Scope
- ADR-018: Introduced-Delta Enforcement at the Edit Gate
- ADR-019: Typed Literal Rule Contract
- Issues #150, #251, and #259
- PRs #262, #268, and #269

---
id: ADR-017
title: "Enforcement Scope Is Independent of Retrieval Scope"
status: accepted
priority: foundational
date: 2026-08-08
scope: enforcement.retrieval_separation
---

# ADR-017: Enforcement Scope Is Independent of Retrieval Scope

**Status:** Accepted
**Date:** 2026-08-08
**Amended:** 2026-08-24 — phrase-sequence matching for multi-term legacy
anti-patterns (see Amendment below)
**Deciders:** Theo Valmis

---

## Context

Until this decision, `mneme check` evaluated a proposed edit only against the
decisions that a lexical retriever ranked highest for the query. The Claude Code
hook builds that query as `"edit to <file_path>"`, and `enforcer._top_nonzero`
discarded every decision scoring zero. A decision that shared no token with the
filename was therefore never evaluated at all.

The observable consequence (issue #254) is that byte-identical content was caught
or missed on the strength of the filename:

```
mneme check --input storage_db.py --query "edit to storage_db.py"  ->  FAIL, 1 violation
mneme check --input service.py    --query "edit to service.py"     ->  PASS, 0 violations
```

Both files contained exactly `import psycopg2`, against a decision whose
`anti_patterns` list contains `psycopg2`. Measured retrieval scores against that
fixture: `storage_db.py` 3.00, `service.py` 0.00, `models.py` 0.00, `db.py` 0.00.
`db.py` misses because the decision's scope says `database`, and `db` is not a
lexical match for it.

This was not merely missing test coverage. The end-to-end test
(`tests/integrations/claude_code/test_hook_e2e.py`) named its target
`storage_db.py` and its comment stated the name was chosen so the token
`storage` would match the fixture's scope — the test was built around the
limitation rather than exposing it.

No ADR governed the separation between retrieval and enforcement. An external
design review recommended settling the question "against ADR-014"; ADR-014 is
the harness-complementary positioning vocabulary and is unrelated. All sixteen
existing ADRs were checked: this decision was genuinely uncovered.

### Why the obvious fix is wrong on its own

Evaluating every decision against the existing matcher was measured across 216
tracked files in this repository:

| Enforcement scope | Files reporting FAIL |
|---|---|
| Retrieval-gated (before this ADR) | 44 of 216 |
| Every decision, existing matcher | 170 of 216 |

Every one of those 170, and every one of the pre-existing 44, was manually
confirmed to be a **false positive**. The matcher explodes a rule phrase into
individual terms and fires when any single term appears, so the rule
`open() without encoding= in Python` reports a violation against any prose
containing the word `open`; other observed triggers were `without`, `content`,
`any`, `main`, and `governance`. This is the noise already recorded as issue
 #150. Globalising it would convert a documented nuisance into a repo-wide edit
block, and would have made strict mode unusable.

## Decision

1. **Enforcement scope is not a ranking question.** "Is this forbidden?" has the
   same answer regardless of whether the filename happened to share a token with
   the decision's scope. Retrieval ranking and its top-N cutoff no longer decide
   whether a decision is enforced.

2. **Retrieval remains responsible for context injection only.** Scoring,
   ranking, and the top-N cutoff continue to govern which decisions are shown to
   an agent as relevant context. That is a relevance question, and ranking is
   correct for it.

3. **Corpus-wide enforcement applies to unambiguous literal rules.** A rule that
   reduces to exactly one significant term — `psycopg2`, `no postgres` — is
   evaluated against every decision supplied, independent of retrieval score. For
   such a rule, term matching and literal matching coincide: there is no phrase
   to take apart and therefore no guess about which word carries the meaning.

4. **Multi-term rules remain retrieval-gated for now.** A rule such as
   `open() without encoding= in Python` is prose describing a pattern, not a
   mechanically decidable rule. Applying it corpus-wide produces the measured
   false-positive blowup above. These keep their existing top-N behaviour until
   a typed literal vocabulary replaces them (issue #250).

5. **`--top` is re-scoped, not removed.** It continues to bound the
   retrieval-gated tier — how many decisions have their multi-term rules applied,
   and how much context is injected. It never limits which decisions are
   enforced.

6. **This is an interim boundary, not the destination.** Splitting rules by term
   count is a proxy for "mechanically decidable". The durable fix is an explicit
   typed vocabulary whose rules are enforceable by construction. Issue #250
   subsequently shipped `FORBID_LITERAL`; ADR-019 defines its exact contract.
   The containment-based exemption anticipated when this ADR was accepted did
   not ship and is not part of that rule type. The term-count proxy remains for
   legacy rules until migration or benchmark evidence justifies changing it.

## Consequences

- Issue #254 is closed for literal rules: the reproduction now reports FAIL under
  `service.py`, `models.py`, `db.py`, and `handler.py` as well as
  `storage_db.py`, and compliant content still passes under all of them.
- False positives do not increase. Measured over the same 216 tracked files
  before and after, the repo-wide FAIL count is 44 in both cases.

  Adding this ADR and its regression test brings the tracked set to 218 files
  and the count to 46. Both new files fail on the pre-existing multi-term rules
  `direct-to-main governance edits` and `unreviewed enforcement changes`,
  triggered by the bare words `main` and `enforcement` appearing in prose that
  documents enforcement. That is the #150 matcher behaving as it already did on
  the retrieval-gated path, which this ADR does not change — and it is a
  concrete instance of the self-reference problem: the document describing a
  rule is itself flagged by it. Recorded here because it is the first thing a
  reader will notice when re-running the measurement.
- `tests/test_enforcer.py::test_zero_score_decisions_are_skipped` asserted the
  defective behaviour and is replaced by two tests pinning the new contract: a
  zero-scoring decision enforces its literal rules, and does not apply its
  multi-term rules.
- Enforcement cost is now linear in corpus size rather than bounded by `--top`.
  At realistic corpus sizes (10–100 decisions) this is a bounded set of string
  matches and is not a measurable cost.
- Rules whose author expected a multi-word phrase to be enforced still will not
  fire outside the retrieval-gated tier. This is deliberate: the alternative is
  the measured 170-of-216 false-positive rate. Issue #250 is the path to making
  those rules expressible, and until it lands the limitation is documented rather
  than silently absorbed.
- Enforcement remains scoped to the tools the PreToolUse hook covers. This ADR
  does not change which edits reach the checker.

## Amendment (2026-08-24): Phrase-Sequence Matching for Multi-Term Legacy Anti-Patterns

### Context of amendment

Dogfooding reproduced the #150 nuisance inside the retrieval-gated tier this
ADR deliberately preserved. `check_prompt` decomposed each multi-term
anti-pattern into individual terms and FAILed on the first whole-word hit, so
ordinary planning prose containing tokens such as `awin`, `live`,
`category`, or `slug` failed checks whenever a rule-bearing decision was
retrieved — including via path-token overlap that pulled the very rule into
its own gated tier. An agent reacted to one such block by writing through a
shell surface instead (the shell behavior is governed by ADR-021 and is not
addressed here). Separately, the `\b` boundary matcher could never match a
rule's own underscore identifier spelling (`assume_awin_awin_us_same_source`
contains no standalone term), so such rules had no true-positive form at all.

This ADR settled *where* multi-term rules apply; it did not settle *how they
match*. The disjunctive within-rule semantics were preserved as containment,
not endorsed. This amendment settles them.

### Amended decision

7. **Multi-term legacy anti-patterns match as a complete ordered term
   sequence.** Both rule and input are normalized identically: lowercased
   alphanumeric runs, with whitespace, underscores, hyphens, and punctuation
   acting as equivalent separators. Every alphanumeric token of the rule —
   including short tokens and stopword-like words such as `and` — participates
   in the template; nothing is dropped. A violation requires that complete
   sequence to occur together and in order in the checked text.

8. **Single-term rules keep their existing whole-word behavior**, and remain
   enforced corpus-wide per Decision 3 above.

9. **Nothing else moves.** Retrieval gating for multi-term legacy rules stays
   exactly as decided above. Constraint matching ("no X" WARN semantics),
   typed `FORBID_LITERAL` (ADR-019), path applicability (ADR-020),
   retrieval scoring and cutoffs, `ConflictDetector`, and the ADR-021
   shell/Stop boundaries are unchanged by this amendment.

### Consequences of the amendment

- Benign prose that merely contains an ordinary token from a rule passes;
  content carrying the rule's canonical or identifier spelling fails.
  The dogfood false-positive class is closed, and identifier-form rules gain
  their first true positives.
- Accepted limitation, documented rather than hidden: morphological variants
  ("assumes" vs "assume") and filler words between terms break the match.
  These strict legacy semantics intentionally trade recall for lower
  false-positive risk. Whole-file audit and ConflictDetector use separate
  evaluation paths and are not guaranteed to recover phrase-sequence misses.
- Tests that pinned the disjunctive gated-tier behavior were updated to the
  amended contract; failing-first regressions from the incident turn green
  under it.
- The frozen enforcement benchmark was re-run unchanged: 7/7 scenarios,
  Layer 2 pass rate 100%.
- Issue #150 narrows: this class of within-tier false positive is resolved;
  code-aware matching remains open there.

## Related

- Issue #254 (this decision), #150 (matcher false positives), #250 (typed rule
  vocabulary), #249 (context injection below a score floor)
- ADR-005: Brand vs Package Namespace Enforcement — the incident that exposed
  unenforceable ADR-sourced decisions
- ADR-014: Harness-Complementary Positioning Vocabulary — cited by an external
  review as governing this area; it does not

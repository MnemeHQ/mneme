# Pre-generation Guidance Role R3 Result

**Status:** R3 passed; production wiring remains pending R4  
**Date:** 2026-08-13  
**Claude trials:** none

## Implementation

R3 adds a pure `classify_guidance_roles()` API in `mneme/guidance_roles.py`.
It consumes the ordered output of `select_guidance_decisions()` and returns an
immutable tuple of wrappers containing the original `ScoredDecision`, role,
reason code, and one-based retrieval rank.

The classifier follows the frozen unique-primary-anchor design:

- a sole highest-scoring candidate is `direct`;
- all lower candidates are `adjacent_constraint`; and
- a top-score tie grants no direct role.

It does not copy, mutate, rescore, reorder, add, or remove selected decisions.

## Evaluator evidence

The characterization evaluator now reports role assignments while preserving
its pre-remediation observation that production formatting is still
undifferentiated.

| Metric | Result |
|---|---:|
| Locked role snapshots | 4/4 |
| Direct role macro recall | 1.00 |
| Known adjacent role assignments | 2/2 |
| Unclassified selected decisions | 0 |
| Selection-changed cases | 0 |
| Unexpected selections | 0 |
| Role contract reproduced | yes |
| Classifier wired to production | no |

The existing 22-case retrieval fixture independently confirms that the expected
decision receives `direct` in all 18 relevant cases.

## Tests

Focused role and characterization tests cover:

- empty selection;
- singleton direct assignment;
- unique top and lower-ranked adjacency;
- exact top-score ties;
- original object, order, score, and match preservation;
- determinism;
- the four locked role cases; and
- the 18/18 direct-decision result.

Results:

- focused guidance/retrieval suite: 49 passed;
- full repository suite: 622 passed, 5 skipped, 52 existing warnings.

## Production boundary

`mneme/guidance.py`, the Claude Code guidance hook, retrieval, K, selection,
canonical policy, plugin configuration, and enforcement are unchanged. Neither
the production formatter nor hook imports `mneme.guidance_roles`.

R4 is the first authorized user-visible behavior change. It may connect the
classifier to `build_guidance()` and apply the canonical R1 role wording. R4
must preserve selected IDs, scores, ordering, context budget behavior,
fail-open behavior, and the independent pre-write enforcement boundary.

Production A/B trials remain paused and E66 remains immutable.

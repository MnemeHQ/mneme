# Pre-generation Guidance Role R4 Result

**Status:** R4 passed; ready for R5 mechanical validation  
**Date:** 2026-08-13  
**Claude trials:** none

## Production integration

`build_guidance()` now classifies its already-selected decisions with the
frozen R2 unique-primary-anchor classifier before formatting them. The
formatter emits the exact R1 global scope boundary and the exact canonical
prefix for each `direct` or `adjacent_constraint` assignment.

An adjacent constraint is explicitly marked `DO NOT IMPLEMENT AS EXTRA WORK`
and states that its presence does not authorize components, storage,
dependencies, interfaces, refactors, or other architecture. A direct decision
remains bounded to the work requested by the user.

## Preserved boundaries

R4 does not change:

- `DecisionRetriever`, retrieval weights, ranking, K, or confidence gates;
- selected decision IDs, scores, order, or match evidence;
- the 8,000-character guidance budget or complete-block truncation behavior;
- Claude Code hook code or plugin configuration;
- enforcement, typed-rule matching, or ADR-020 path applicability;
- canonical decisions, ADRs, project memory, or locked fixtures; or
- E66 or production-effectiveness experiment artifacts.

The role classifier itself remains byte-for-byte identical to the R3-locked
implementation. The production hook inherits the new context only through its
existing call to `build_guidance()`.

## Deterministic characterization

The locked four-case applicability characterization now preserves the
historical diagnosis and separately verifies current production formatting.

| Metric | Result |
|---|---:|
| Historical adjacent undifferentiated selections | 2 |
| Current adjacent undifferentiated selections | 0 |
| Current adjacent authorizing selections | 0 |
| Locked role snapshots | 4/4 |
| Role-aware formatting matches | 4/4 |
| Non-authorizing wording matches | 4/4 |
| Direct role macro recall | 1.00 |
| Known adjacent role assignments | 2/2 |
| Selection-changed cases | 0 |
| Unexpected selections | 0 |

The existing 22-case retrieval fixture continues to assign the expected
decision as `direct` in all 18 relevant cases. The authentication
characterization still selects `ADR-AUTH` at 8.0 and `ADR-STORAGE` at 2.0, in
that order; only their production presentation changes.

## Tests and integrity

- focused formatter/classifier/evaluator/hook suite: 35 passed;
- full repository suite: 624 passed, 5 skipped, 52 existing warnings;
- locked applicability fixture hash unchanged;
- locked retrieval fixture and project-memory hashes unchanged;
- R3 role-classifier implementation hash unchanged;
- retrieval, guidance hook, and pre-write hook hashes unchanged;
- E66 protected artifact manifest: 547 files, unchanged digest; and
- production-effectiveness artifact directory: absent.

## R5 boundary

R5 is mechanical validation only. It may rerun deterministic suites, inspect
package/install contracts, verify platform-neutral output and budgets, and
freeze the exact candidate hashes needed for R6. It may not tune retrieval,
change role semantics or wording, alter hooks or enforcement, or run Claude
trials.

Production A/B trials remain paused. Live Claude spend remains prohibited
until a new R6 execution lock is frozen.

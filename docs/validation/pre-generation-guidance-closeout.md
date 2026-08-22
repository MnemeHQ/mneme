# Pre-generation guidance: canonical closeout

Status: **experiment closed; implementation retained; no R7 planned**  
Date: 2026-08-14

## Product finding

Mneme can retrieve multiple relevant decisions while distinguishing the one
that directly governs the task from secondary decisions that must not become
extra implementation work.

The original defect was action-shape ambiguity: every retrieved decision was
rendered as equally actionable, so an authentication task could cause an
adjacent storage decision to become an unrequested SQLite implementation. The
implemented change assigns a unique top-scoring decision the `direct` role,
marks remaining selected decisions as `adjacent_constraint`, and renders the
roles differently without changing retrieval, ranking, K, or enforcement. A
top-score tie deliberately produces no direct anchor. The role contract
document was never committed to `main`; it exists only in the archived
experimental tree (`archive/r1-r6-experimental-tree-2026-08-22`, at
`docs/architecture/pre-generation-guidance-role-contract.md`). See the
[R4 wiring result](pre-generation-guidance-role-r4-result.md).

## Frozen evidence

- R6 preserved a **+4 governed-compliance count** (12/15 treatment versus 8/15
  baseline) and reduced governed-scope expansions from 5/15 to 2/15. It still
  failed its locked product mechanism gate because treatment functional
  completion was `-2` and treatment had two scope expansions. The frozen
  [R6 result](artifacts/pre-generation-guidance-role-r6-2026-08-14/mechanism_isolation/mechanism-result-r6-20260814.json)
  has SHA-256
  `BCF682EDC1DEAF2110A004ADEC648AA843B15D179A4CF019BABC36D526B7ACA4`.
- Blinded post-R6 diagnosis found that no adjacent authentication constraint
  became an implementation objective. Both failed gates came from two storage
  trials that created parallel subclasses and left the supplied class
  incomplete: one localized direct-guidance implementation-targeting failure.
  The frozen [diagnosis](artifacts/pre-generation-guidance-role-r6-2026-08-14/mechanism_isolation/post-r6-failure-diagnosis-20260814.json)
  has SHA-256
  `8B9890BFFB9E891739438978B09C0E94EF6555029ECD6DAB274DD092C5CB6A5C`.
- The locked storage-only 2x2 study classified the targeting result as
  `fixture_ambiguity_dominates`. With the explicit instruction to implement
  the existing `SessionStore`, role-aware guidance was 3/3 architecturally
  compliant, 3/3 functionally complete, and 0/3 on scope expansion; baseline
  was also 3/3 complete and 0/3 expansion but 0/3 compliant. The frozen
  [2x2 result](artifacts/pre-generation-guidance-storage-target-2x2-2026-08-14/mechanism-result-20260814.json)
  has SHA-256
  `AE09C09BBCBD82F94195F9B73CFAE92763AC2A6F8CDFF98BE2333BB6A1DD9F34`.

## Code-quality audit

The retained production mechanism is small and readable: retrieval selects;
`classify_guidance_roles()` wraps selected objects without copying, rescoring,
reordering, or mutating them; `build_guidance()` formats the assignments; and
the Claude Code hook remains opt-in and fail-open. Focused classifier,
formatter, hook, retrieval, plugin, and packaging-contract tests produced
55 passes and 5 expected built-artifact skips.

No unnecessary abstraction, duplicated implementation path, or substantive
correctness defect was found. One non-functional documentation inconsistency
remains: the `guidance_roles.py` module docstring describes its earlier R3
unwired state even though R4 wired it into `build_guidance()`. It does not
justify reopening the implementation or broadening the diff.

## Supported boundary and decision

Supported: the role-aware presentation fixed the diagnosed adjacent-decision
leakage mechanism and preserved a strong architectural-compliance signal in
synthetic mechanism tests. The implementation is retained as a worthwhile
incremental improvement.

Not supported: production-effectiveness claims, a precise estimate of ordinary
model variance, or a claim that R6 passed. The storage 2x2 had only three
trials per cell, and R6 remains permanently **FAIL** under its frozen rule.

Synthetic experimentation stops here. Do not create R7 or another confirmatory
campaign. The production-effectiveness A/B remains paused; replacing its failed
R6 prerequisite would require a separate prospective architecture and
validation decision, not a reinterpretation or rerun of R6.

## Current core snapshot

Read-only inspection found the CLI, pre-flight enforcement, deterministic
`DecisionRetriever`, post-generation `ConflictDetector`, and two-layer
benchmark paths intact. Their focused suites produced 155 passes. The shipped
benchmark reports 7/7 enforcement scenarios passing; for the five scenarios
with protected retrieval IDs, recall@3 is 1.00 and precision@3 is 0.33, with
irrelevant injection reported in all five. This snapshot records current state
only and creates no follow-on product scope.

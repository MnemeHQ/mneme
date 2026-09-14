# D2C0 — ADR-027 acceptance and D2C authority-boundary alignment (docs/ADR only)

This task promotes ADR-027 from `proposed` to `accepted` with the compiler
vocabulary priority `foundational`, records the approved D2C persistence
boundary and acceptance authority semantics in the ADR, and adds this
validation artifact. No runtime, test, store, service, CLI, MCP, Audit, or
enforcement code is modified; D2C1 is not implemented and D2D is not started.

## Exact SHA evidence

- Base SHA (canonical `origin/main`): `7231fa99ec115b409f4b8c475bb4389e50920ccd`
- Exact tested implementation SHA (ADR-027 amendment commit; all test, gate,
  strict-compiler, and self-governance figures below executed on this exact
  source state):
  `38337601d3dde39618f3210954723357ff8cb488`
- The next commit adds this validation artifact only (docs-only; no runtime or
  test bytes differ from the tested SHA).
- Branch `docs/adr027-accept-d2c-authority-boundary`, worktree
  `.worktrees/docs-adr027-accept-d2c-authority-boundary`, context-verified with
  `scripts/check_worktree_context.py` before work and before every commit.

## ADR-027 metadata change

| Field | Before | After |
|---|---|---|
| status | `proposed` | `accepted` |
| priority | `high` (outside compiler vocabulary) | `foundational` |

Rendered header updated consistently and an Acceptance record (2026-09-14)
added. No other ADR file was touched.

## Evidence supporting promotion

- **D2A** (#365, PR #371) — proposal separation, deterministic idempotency,
  provenance retention, fail-closed lifecycle invariants (see
  `docs/validation/d2a-proposal-foundation.md`).
- **D2B0** (#372) proved complete consumer reads with explicit
  proposal/canonical lifecycle separation and fail-closed trace (see
  `docs/validation/d2b0-consumer-read-completeness.md`).
- **D2B** (#373) proved the frozen six-tool producer capability boundary with
  structural rejection of every forbidden authority field (see
  `docs/validation/d2b-decision-index-mcp.md`).
- Generic producers still cannot accept, activate, supersede, create rules,
  create exceptions, bypass review, or submit trusted evidence.
- The authority separation is an architectural invariant, therefore
  `foundational`.

## Approved D2C persistence boundary (recorded in ADR-027)

```text
DecisionProposalStore
        |
        | human Mneme authority accepts
        v
accepted proposal + accepted_decision_id
        |
        | deterministic materialization
        v
project_memory.json decisions[]
        |
        v
CanonicalDecisionRecord
   via existing decisions_to_canonical()
        |
        v
Audit / retrieval / later protection
```

Key wording: `project_memory.json` is the **current durable storage backing**
for accepted architecture decisions in D2C; it does **not** replace ADR-023's
logical rule that the Decision Index is the canonical decision layer (the
canonical representation remains `CanonicalDecisionRecord`). The boundary is a
**bounded D2C choice** and does not prevent a later storage migration without
changing canonical identity.

## Explicit fail-safe write order (recorded in ADR-027)

```text
1. validate everything before mutation
2. atomically transition the proposal:
       proposed -> accepted + accepted_decision_id
3. atomically materialize the corresponding decision into project_memory.json
4. reload/derive the canonical representation and verify
5. only then return acceptance success
```

Recovery: a crash after step 2 leaves an explicit, non-enforcing, recoverable
incomplete materialization; retry uses the stored `accepted_decision_id` and
completes materialization idempotently. The reverse ordering (active runtime
decision with the proposal still `proposed`) must never be created
intentionally; if discovered (corruption/manual modification), fail closed
rather than inferring acceptance. Rejected proposals never create a runtime or
canonical decision.

## Provenance limitation (recorded in ADR-027)

Full originating provenance stays durably preserved in the retained proposal
(`proposal_id`, producer fields, source reference/version/locator,
`origin_classification`, `proposed_at`, `accepted_decision_id`); the proposal ↔
canonical link is `accepted_decision_id`. The current runtime `Decision` /
`decisions_to_canonical` path does **not** carry all proposal provenance into
`CanonicalSourceEvidence`, and this amendment claims otherwise nowhere.
Verified provenance, trusted evidence, ADR provenance, and source verification
state are never fabricated from producer metadata. A richer canonical
provenance representation requires an explicit later architecture extension.

## MCP authority surface

Unchanged: exactly the six D2B tools (`decision.propose`,
`decision.propose_batch`, `decision.get`, `decision.search`,
`decision.applicable_to`, `decision.trace`). No accept/reject/activate/
supersede/create_exception/bypass/submit_trusted_evidence operation or alias
was added. Any future CLI authority surface must be as thin as the MCP
transport (`mneme decision accept ...` calls `DecisionAuthorityService.accept(...)`).

## Exact commands

```text
python scripts/new_task_worktree.py docs/adr027-accept-d2c-authority-boundary
python -m pytest tests/test_adr_validator.py tests/test_adr_parser.py tests/test_adr_precedence.py tests/test_adr_compile_integration.py tests/test_adr_constraints.py tests/test_adr_lifecycle.py tests/test_decision_mcp.py -q
python scripts/run_test_battery.py gate
python -m mneme.cli check --memory .mneme/project_memory.json --input docs/adr/ADR-027-decision-mcp-proposal-ingestion-and-authority-boundary.md --query "docs: accept adr027 authority boundary docs/adr/ADR-027-decision-mcp-proposal-ingestion-and-authority-boundary.md" --mode warn
python -m mneme.cli check --memory .mneme/project_memory.json --input docs/validation/d2c0-adr027-authority-boundary.md --query "docs: accept adr027 authority boundary docs/validation/d2c0-adr027-authority-boundary.md" --mode warn
python scripts/check_encoding.py
```

Strict ADR-027 vocabulary proof (ad hoc, on the tested SHA):

```python
from mneme.decision_mcp import load_canonical_index_from_adr_dir
idx = load_canonical_index_from_adr_dir('docs/adr')
# strict compiler sequence parse -> validate_corpus -> resolve_precedence
# -> build_canonical_index completed with no error:
# 28 canonical records, 1 rule; ADR-027 lifecycle_status == 'active'
```

Before this amendment the same strict path failed on ADR-027's
`priority: high` (outside `foundational|normal|exception`), which is why D2B
could not default `--adr-dir` to `docs/adr`. After the amendment the corpus
passes strict validation; no other ADR was touched or repaired (the remaining
corpus already carried valid vocabularies; ADR-025 stays deliberately
`proposed`).

## Results

| Check | Result |
|---|---|
| Focused ADR/compiler + MCP canonical-loading tests | 175 passed |
| Gate battery (`scripts/run_test_battery.py gate`) | 1429 passed, 5 skipped (identical to the D2B baseline: docs-only delta) |
| `mneme check --mode warn` on the changed ADR | PASS |
| `mneme check --mode warn` on the validation artifact | PASS |
| `scripts/check_encoding.py` (mojibake + BOM) | OK |

## Benchmark trigger

**NOT MET.** This is a docs/ADR alignment change only: no runtime, test,
store, service, CLI, MCP, Audit, enforcement, retrieval, applicability,
matcher, projection, or benchmark bytes changed (attestation below), so the
frozen enforcement benchmark was not re-run.

## Frozen-boundary attestation

- `decision_retriever.py`, `enforcer.py`, `conflict_detector.py`,
  `benchmark.py`, `rule_matcher.py`, `path_selectors.py` behaviorally changed?
  NO (untouched)
- `decision_index.py` / `decision_projection.py` / `memory_store.py` /
  `decision_proposal.py` / `decision_proposal_store.py` /
  `decision_index_service.py` / `decision_mcp.py` / `cli.py` /
  `protection.py` modified? NO (untouched)
- proposal stores / authority service changed? NO (none exist yet; D2C1 not
  implemented)
- `.mneme/project_memory.json` changed? NO
- Audit tier semantics changed? NO
- benchmark fixtures changed? NO
- runtime semantic delta? NO
- MCP capability inventory changed? NO

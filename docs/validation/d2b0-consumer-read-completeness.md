# D2B0 — Consumer-read completeness for the Decision Index service
(issues #362/#365, pre-D2B)

Narrow, protocol-independent completion of the consumer-read surface of
`DecisionIndexService` before D2B MCP transport: `search()` now returns
both proposals and canonical decisions with explicit lifecycle separation,
and `trace()` resolves proposal ids, canonical decision ids, and unknown
ids. No MCP, no authority capability, no enforcement semantics, no
retrieval/enforcement/benchmark semantic change.

## Exact SHA evidence

- Exact base SHA (canonical `origin/main` after D2A merge):
  `989cd53078623a27df7b91570dfe0b993c3b438a`
- Exact tested implementation SHA:
  `95c3df0229bbf2f84f7068aad2065014db11c319` on branch
  `feat/d2b0-consumer-read-completeness` (worktree
  `.worktrees/feat-d2b0-consumer-read-completeness`, context-verified with
  `scripts/check_worktree_context.py` before work and before every commit).
  The PR head adds this validation artifact only; no runtime/test bytes
  differ from the tested implementation commit.

## Exact commands

```text
python scripts/new_task_worktree.py feat/d2b0-consumer-read-completeness
python -m pytest tests/test_decision_index_consumer_reads.py tests/test_decision_index_service.py tests/test_decision_proposal.py -q
python -m pytest tests/test_decision_index.py tests/test_decision_projection.py -q
python scripts/run_test_battery.py gate
python -m mneme.cli check --memory .mneme/project_memory.json --input mneme/decision_index_service.py --query "feat: complete decision index consumer reads mneme/decision_index_service.py" --mode warn
python -m mneme.cli check --memory .mneme/project_memory.json --input scripts/run_test_battery.py --query "feat: complete decision index consumer reads scripts/run_test_battery.py" --mode warn
```

## Results

| Check | Result |
|---|---|
| Focused consumer-read + D2A tests (`test_decision_index_consumer_reads.py`, `test_decision_index_service.py`, `test_decision_proposal.py`) | 74 passed |
| D0 kernel/projection regression (`test_decision_index.py`, `test_decision_projection.py`) | 46 passed |
| Gate battery (`scripts/run_test_battery.py gate`, new test file registered in the manifest) | 1349 passed, 5 skipped (pre-existing, unrelated) |
| `mneme check --mode warn` on changed governed files | 2/2 PASS |
| Frozen enforcement benchmark | NOT triggered: this PR is a Decision Index read-surface change only; no retrieval, enforcement, conflict-detection, matcher, applicability, or benchmark semantics were touched (test-policy trigger not met) |

## Search semantics

`DecisionIndexService.search(query, proposal_status=None,
canonical_lifecycle_status=None, producer_name=None,
source_reference=None, origin_classification=None) ->
DecisionSearchResult`.

- `DecisionSearchResult` is a frozen dataclass with two separate lists:
  `proposals: tuple[DecisionProposal, ...]` and
  `canonical_decisions: tuple[CanonicalDecisionRecord, ...]`. The domains
  are never merged and never share a status field.
- Filters are exact matches. `proposal_status` validates against the
  proposal lifecycle vocabulary (proposed/accepted/rejected);
  `canonical_lifecycle_status` validates against the canonical lifecycle
  vocabulary (active/superseded/deprecated/inactive). Each vocabulary
  rejects the other's values (fail closed), so neither domain's lifecycle
  can be redefined through the other's filter.
- Deterministic case-insensitive substring `query`. Proposal haystack:
  title, statement, rationale, source reference, repository locator,
  scope hints, related decision ids. Canonical haystack: decision id,
  statement, rationale, context scope, targets, constraints,
  anti-patterns, source-evidence locators. No new canonical data is
  invented (the rule payload value is deliberately not a canonical-record
  search field).
- Ordering follows existing store insertion order (proposals) and
  canonical record order (canonical decisions); identical calls return
  identical results. Search rank has zero enforcement meaning.
- No LLMs, embeddings, vectors, fuzzy ranking, or new retrieval
  infrastructure.

## Trace semantics

`DecisionIndexService.trace(record_id) -> ProposalTrace |
CanonicalDecisionTrace` (union return; the service owns the record-type
distinction — the future transport never guesses).

- Proposal id → `ProposalTrace` with unchanged D2A behavior: proposal,
  source provenance, accepted canonical id (only where an authority
  action actually set it), canonical record, derived rule ids; every
  missing link explicit (`accepted_decision_id`/`canonical_record`/
  `derived_rules`/`enforcement_links`/`trusted_evidence`).
- Canonical decision id → `CanonicalDecisionTrace` exposing only what the
  canonical kernel carries: the record, its actual derived
  `CanonicalRuleRecord`s (ADR-020 applicability exactly as stored,
  unmodified), and declared test-evidence linkage exactly as stored
  (ADR-024, `declared` only — never labelled trusted/verified per
  ADR-025). Enforcement points are not modelled in the current canonical
  kernel and are reported explicitly as
  `enforcement_links: absent`; nothing is fabricated.
- Unknown id → the explicit not-found `ProposalTrace` (deterministic,
  fail closed).
- Trace reads never mutate canonical or proposal records.

## Lifecycle separation statement

Proposal lifecycle (proposed/accepted/rejected, ADR-027) and canonical
decision lifecycle (active/superseded/deprecated/inactive, ADR-023)
remain distinct domains with distinct validation vocabularies. Search
returns them in separate result lists; no result type merges the two.

## Capability statement

No MCP or adapter dependency was introduced (source-level import check
plus subprocess import-isolation test). No authority capability was
introduced: no accept/reject-mutation/activate/deactivate/supersede/
create_exception/bypass/trusted-evidence-submission method exists, no
automatic proposal→canonical promotion exists, proposal persistence
semantics are unchanged, canonical records are never modified, and no
second canonical store was created.

## Frozen-boundary attestation

- `decision_retriever.py`, `enforcer.py`, `conflict_detector.py`,
  `benchmark.py`, `rule_matcher.py`, `path_selectors.py` behaviorally
  changed? NO (untouched)
- `decision_index.py` / `decision_projection.py` / `memory_store.py` /
  `decision_proposal.py` / `decision_proposal_store.py` modified? NO
  (untouched)
- ADR-020 applicability semantics changed? NO (canonical trace returns
  stored applicability verbatim)
- Audit tiers changed? NO
- Proposal idempotency/authority boundaries changed? NO (pinned by
  regression tests)
- Benchmark fixtures / `.mneme/project_memory.json` changed? NO
- Benchmark instrument rerun? NO — not triggered under the test policy
  (read-surface-only change)

## Authority report

```text
canonical search added without enforcement semantics? YES
proposal/canonical lifecycle remain separate? YES
canonical trace fabricates missing links? NO
declared evidence promoted to trusted evidence? NO
adapter/MCP dependency added? NO
authority mutation added? NO
frozen runtime semantic delta? NO
```

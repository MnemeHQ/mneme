# D2A — Decision proposal foundation (ADR-027, issue #365 PR A)

Implements the protocol-independent proposal layer underneath the future
Decision Index MCP (#362): a frozen proposal domain, a dedicated local
proposal store, and a `DecisionIndexService`. No MCP transport, no
acceptance/rejection authority, no hosted or organizational dependency,
and no observable change to any frozen runtime surface.

## Exact tested SHA

- Base (canonical `origin/main`): `e54a5f48b11c84ee71db17c0c8c730e0c985f636`
- Implementation commit tested: `ea7695af` (branch
  `feat/d2a-proposal-foundation`, worktree
  `.worktrees/feat-d2a-proposal-foundation`, context-verified with
  `scripts/check_worktree_context.py` before work and before each commit).
- The PR head adds this validation artifact only; no runtime bytes differ
  from the tested commit.

## Exact commands

```text
python scripts/new_task_worktree.py feat/d2a-proposal-foundation
python -m pytest tests/test_decision_proposal.py tests/test_decision_index_service.py -q
python -m pytest tests/test_decision_index.py tests/test_decision_projection.py -q
python scripts/run_test_battery.py gate
python -m mneme.cli benchmark examples/benchmarks/ --memory examples/project_memory.json
python -m mneme.cli check --memory .mneme/project_memory.json --input <changed mneme/*, scripts/* file> --query "feat: add decision proposal foundation <file>" --mode warn
```

## Results

| Check | Result |
|---|---|
| Focused D2A tests (`test_decision_proposal.py`, `test_decision_index_service.py`) | 44 passed |
| D0 kernel/projection regression (`test_decision_index.py`, `test_decision_projection.py`) | 46 passed |
| Gate battery (`scripts/run_test_battery.py gate`, includes both new files registered in the manifest) | 1319 passed, 5 skipped (pre-existing, unrelated) |
| Frozen enforcement benchmark instrument | 7/7 scenarios, Layer 2 pass rate 100% (fixtures unchanged) |
| `mneme check --mode warn` on changed `mneme/*` + `scripts/*` files | 4/4 PASS |

## Required-test coverage map (issue #365)

1. producer proposals begin `proposed` — `test_every_producer_created_proposal_begins_proposed`
2. proposal cannot enter Layer 1 enforcement — `test_proposal_cannot_enter_layer1_enforcement` (empty projection + `check_prompt` PASS on the proposal's own forbidden literal) and `test_rejected_and_non_authoritative_fixtures_cannot_project_to_governance`
3. proposal text cannot create a typed rule — `test_proposal_text_cannot_create_a_typed_rule`
4. `scope_hints` cannot become rule applicability — `test_scope_hints_never_become_rule_applicability` (also proves path hints get no ADR-020 glob semantics)
5. identical resend idempotent — `test_identical_resend_is_idempotent_with_original_timestamp`, `test_in_memory_store_add_if_new_is_idempotent`, `test_json_file_store_add_if_new_is_idempotent`
6. changed content preserves previous, creates new candidate — `test_changed_content_preserves_previous_and_creates_new_candidate`
7. changed source version preserves previous, creates new candidate — `test_changed_source_version_preserves_previous_and_creates_new_candidate`
8. provenance round-trips losslessly — `test_provenance_round_trips_losslessly`, `test_candidate_round_trips_losslessly`, `test_proposal_round_trips_losslessly`
9. producer evidence-like metadata cannot become trusted evidence — `test_producer_evidence_never_becomes_trusted_evidence`, `test_candidate_rejects_evidence_like_metadata`
10. rejected/non-authoritative fixtures cannot project to governance — `test_rejected_and_non_authoritative_fixtures_cannot_project_to_governance`
11. no MCP transport dependency — `test_service_modules_carry_no_mcp_or_hosted_dependency`, `test_importing_service_does_not_load_mcp_modules`, `test_service_exposes_no_authority_mutation_methods`
12. proposal persistence does not modify `.mneme/project_memory.json` — `test_proposal_persistence_never_touches_project_memory`
13. deterministic store reload preserves ids/history — `test_json_store_reload_preserves_ids_history_and_order`, `test_stores_preserve_insertion_order_and_history`
14. partial trace reports missing links explicitly — `test_trace_of_proposed_proposal_reports_missing_links_explicitly`, `test_trace_of_unknown_proposal_is_explicit`, `test_trace_with_unresolvable_accepted_id_reports_absence`
15. canonical reads do not mutate canonical records — `test_canonical_reads_do_not_mutate_canonical_records`
16. existing DecisionRetriever/Enforcer/ConflictDetector/Audit semantics unchanged — frozen modules untouched (see attestation); gate battery green including `test_decision_retriever.py`, `test_enforcer.py`, `test_conflict_detector.py`, audit suites
17. frozen benchmark fixtures unchanged — benchmark instrument 7/7 PASS; fixtures untouched (see attestation)

## Storage design chosen

Dedicated `DecisionProposalStore` protocol with two semantically identical
implementations:

- `InMemoryDecisionProposalStore` — test/reference implementation;
- `JsonFileDecisionProposalStore` — deterministic JSON file
  (`{"schema": "mneme.decision-proposals/v1", "proposals": [...]}`),
  loaded at construction, rewritten atomically (temp file + `os.replace`)
  only on successful append. Idempotent re-adds perform no write.

Operations are deliberately minimal: `add_if_new`, `get`,
`list_proposals`. Existing entries are never rewritten, reordered, or
deleted (append-preserving history; no silent overwrite). No authority
mutation methods exist. The store is fully separate from `MemoryStore`,
`.mneme/project_memory.json`, canonical Decision Index records, and
runtime Layer 1 memory. No database, ORM, hosted persistence, or
cross-repository aggregation.

## Deterministic identity / idempotency algorithm

No random identity. For candidate `c` with provenance `p`:

```text
producer_key         = SHA-256(canonical_json([p.producer_name,
                         p.producer_type, p.source_reference,
                         p.external_source_id or "-", p.source_version or "-",
                         p.repository_locator or "-"]))
content_fingerprint  = SHA-256(canonical_json({title, statement, rationale,
                         scope_hints[], architecture_context{},
                         related_decision_ids[]}))
proposal_id          = "dprop-" + SHA-256(producer_key + US +
                         content_fingerprint)[:32]
```

(`canonical_json` = `json.dumps(sort_keys=True, separators=(",",":"))`;
US = `\x1f` field separator; `proposed_at` is excluded by construction.)

Behavior:

- identical source/version/content resend → same `proposal_id` → store
  returns the existing record unchanged (`created=False`), original
  `proposed_at` preserved regardless of clock;
- same source/version, changed content → new fingerprint → new proposal;
  previous retained;
- changed source version → new producer key → new proposal; previous
  retained;
- absent optional key components (`external_source_id`,
  `source_version`, `repository_locator`) use the literal marker `"-"` in
  the key material — the narrowest deterministic fallback justified by the
  supplied provenance. The content fingerprint remains part of identity,
  so distinct candidates from the same producer/document never collide and
  identical resends remain idempotent.

No LLM/vector/semantic similarity participates in identity. A fixed clock
is injected in tests; the default clock (UTC ISO-8601) affects only
`proposed_at` of newly created proposals.

## Deliberately deferred semantics

- MCP transport/server (D2B), acceptance/rejection authority surface and
  any proposal→canonical promotion (D2C): the proposal model can represent
  `accepted`/`rejected` and `accepted_decision_id`, but no D2A code path
  produces those transitions; trace resolves them only when a fixture/authority
  action has set them.
- Semantic-duplicate flagging: not implemented, not even as a stub
  interface (no dependency is justified yet; ADR-027 permits later
  addition without boundary change).
- Proposal amend/update operations, webhooks, source watching,
  exception/supersession mutations, evidence submission: ADR-027 deferral
  list, untouched.
- No CLI surface: the service is a library API for the future transport.
- ADR-027 remains `proposed`; not promoted by this PR.

## Frozen-boundary attestation

- `decision_retriever.py`, `enforcer.py`, `conflict_detector.py`,
  `benchmark.py`, `rule_matcher.py`, `path_selectors.py` behaviorally
  changed? NO (untouched)
- `decision_index.py` / `decision_projection.py` / `memory_store.py`
  modified? NO (untouched)
- benchmark fixtures changed? NO
- `.mneme/project_memory.json` changed? NO
- ADR-020 typed-rule path semantics changed? NO
- Audit tier semantics changed? NO

## Authority report

```text
proposal can enforce before acceptance? NO
proposal can create typed rule by assertion? NO
scope hint becomes rule applicability automatically? NO
producer evidence becomes trusted automatically? NO
identical resend creates duplicate? NO
history silently overwritten? NO
MCP dependency in core service? NO
hosted/org dependency added? NO
frozen runtime semantic delta? NO
```

# D2C1 — Decision authority service (ADR-027 accepted-proposal authority path)

Implements the protocol-independent Mneme authority layer (D2C1): a
`DecisionAuthorityService` Core module owning proposal transition legality,
canonical decision identity, collision checks, `project_memory.json`
materialization, recovery/idempotency, dual-representation verification,
and fail-closed behavior. No MCP, CLI, Audit, protection, retrieval, or
enforcement change; no D2C2 CLI authority surface; D2D/Sagarika not started.

## Architecture-review revision (same PR)

Three bounded correctness fixes on top of the original implementation:

1. **Downstream-enrichment-tolerant acceptance retry.** An
   already-accepted proposal's retry previously required the stored
   decision to remain identical to the original bare D2C
   materialization (`rules == []`, `test_evidence == []`, canonical
   `derived_rule_ids == ()`), which wrongly treated legitimate
   downstream enrichment — e.g. protection activation installing typed
   rules, declared test-evidence linkage, or a later `updated_at` — as
   an ID collision. Verification is now split into two cases:
   - **Case A — fresh materialization / crash recovery (D2C writes the
     decision in this call):** the exact initial D2C shape is proven
     (`decision/rationale/scope` mapping, empty
     `constraints`/`anti_patterns`/`rules`/`test_evidence`,
     `status == "active"`, both timestamps equal to the authority clock
     value; canonical `derived_rule_ids == ()` and
     `test_evidence == ()`). This proves D2C itself fabricated nothing.
   - **Case B — already-accepted proposal with an existing decision:**
     verify only the fields whose identity/content D2C owns — id,
     decision/statement, rationale, scope/context_scope, D2C-owned
     emptiness of `constraints`/`anti_patterns` (no currently approved
     downstream path modifies them post-acceptance), a legal lifecycle
     status (`VALID_LIFECYCLE_STATUSES`), and an existing
     `created_at`. Downstream-owned/enrichable fields — `rules`,
     canonical `derived_rule_ids`, `test_evidence`, `updated_at` — are
     NOT required to remain empty. Downstream enrichment is never
     deleted, normalized, overwritten, or mutated.
   Regression: accept → install legitimate protection through the
   existing protection write primitive (`mneme.protection._install_rule`,
   the exact primitive protection activation uses) → retry
   `DecisionAuthorityService.accept(proposal_id)` → success with
   `already_accepted=True, materialized=False`, the existing rule
   intact, no memory rewrite/duplicate, `accepted_decision_id`
   unchanged, and the canonical record keeping the downstream-derived
   rule linkage D2C did not create. A second regression proves declared
   test evidence added after acceptance is neither claimed nor removed
   by a retry.
2. **Proposal-ID namespace enforcement.** An explicit `decision_id`
   beginning with the reserved `dprop-` prefix is rejected
   (`DecisionIdNamespaceError`) even when no proposal with that exact
   id exists; equality with an actual proposal id remains rejected.
   Explicit human-assigned ids are not required to begin `ddec-` (e.g.
   `arch-storage-standard` is accepted); the default id remains
   `ddec-…`.
3. **Store-level accepted-ID conflict semantics.**
   `transition_if_proposed` is idempotent at the target status ONLY
   when the requested link matches: for `accepted`, a requested
   `accepted_decision_id` equal to the stored one returns
   `(existing, False)` while a different requested id raises
   `ValueError` (fail closed — the stored `accepted_decision_id` can
   never be replaced); for `rejected`, a repeated rejection with no
   id remains `(existing, False)`. Terminal accepted↔rejected failures
   are preserved. Parity is proven for BOTH
   `InMemoryDecisionProposalStore` and `JsonFileDecisionProposalStore`;
   `DecisionAuthorityService` continues translating store failures
   through `ProposalStoreCorruptError` (its own pre-checks still raise
   `AcceptedProposalIdConflictError` before any store call).

## Exact SHA evidence

- Exact base SHA (canonical `origin/main`): `c019aecba485ffa67ea47f0b3a7af1024aece36b`
- Original implementation SHA:
  `db658d274a7a55d62aa1c5084574684018c6f89a` (original focused counts:
  66 passed, gate 1495 passed, 5 skipped)
- Exact tested implementation SHA (architecture-review revision; all
  focused, regression, protection-regression, gate, and
  self-governance figures below executed on this exact source state):
  `0a00c2b8a04abfccf1d12d82baf6ded3c8546ceb`
- The next commit updates this validation artifact only (docs-only; no
  runtime or test bytes differ from the tested SHA).
- Branch `feat/d2c1-decision-authority`, worktree
  `.worktrees/feat-d2c1-decision-authority`, context-verified with
  `scripts/check_worktree_context.py` before work and before every commit.

## Files changed

| File | Change |
|---|---|
| `mneme/decision_authority.py` | NEW — authority service, result/error types, pinned id algorithm, materialization, verification; review fix: two-case verification (A exact initial shape / B D2C-owned identity only) and reserved-namespace rejection |
| `mneme/decision_proposal_store.py` | adds the Core authority transition primitive `transition_if_proposed` (both stores); review fix: conflicting `accepted_decision_id` at target status fails closed; producer semantics untouched |
| `tests/test_decision_authority.py` | NEW — 72 focused tests incl. 6 review-fix regressions (registered in the gate manifest) |
| `scripts/run_test_battery.py` | gate manifest: `tests/test_decision_authority.py` added to `GATE_CORE_PATHS` |


Unchanged: `decision_mcp.py`, `decision_index.py`, `decision_projection.py`,
`decision_index_service.py`, `decision_proposal.py`, `memory_store.py`,
`protection.py`, `setup_state.py` (only its `atomic_write_json` helper is
reused, unmodified), `cli.py` (zero CLI changes).

## Authority service public API

```python
DecisionAuthorityService(proposal_store, memory_path, clock=None)

    accept(proposal_id, decision_id=None) -> AcceptResult
    reject(proposal_id) -> RejectResult

default_decision_id_of(proposal) -> str
expected_materialization_entry(proposal, decision_id, timestamp) -> dict

AcceptResult:  proposal_id, decision_id, proposal_status, materialized,
               already_accepted, recovered, verified   (facts only)
RejectResult:  proposal_id, proposal_status, already_rejected
```

The service owns ALL lifecycle/identity/collision/persistence/recovery/
verification semantics. Adapters (future CLI, any other UI) must call this
service and must not duplicate its rules. `DecisionIndexService` remains the
producer/read service and was not extended.

Error taxonomy (all subclasses of `DecisionAuthorityError`, fail closed,
no partial success ever reported as success): `ProposalNotFoundError`,
`ProposalAlreadyRejectedError`, `ProposalAlreadyAcceptedError`,
`AcceptedProposalIdConflictError`, `ProposalStoreCorruptError`,
`MemoryMissingError`, `MemoryInvalidError`, `DecisionIdCollisionError`,
`DecisionIdNamespaceError`, `MaterializationVerificationError`,
`CanonicalVerificationError`.

## Proposal transition contract

Core persistence primitive on both `DecisionProposalStore` implementations
(protocol + `InMemoryDecisionProposalStore` + `JsonFileDecisionProposalStore`):

```python
transition_if_proposed(proposal_id, target_status, accepted_decision_id=None)
    -> (proposal_after_call, transitioned)
```

- only `proposed` may transition; `accepted`/`rejected` are terminal in
  D2C1 (accepted→rejected and rejected→accepted raise);
- already-at-target returns the record unchanged with `transitioned=False`
  (idempotent retry; a retry can never replace a stored
  `accepted_decision_id`);
- candidate content, `producer_key`, `content_fingerprint`, and
  `proposed_at` are immutable across the transition (only status/link
  fields change);
- `accepted` requires a non-empty `accepted_decision_id`; `rejected` must
  not carry one; unknown ids and invalid arguments fail closed;
- the file store rebuilds the document with every other record serialized
  exactly as stored (identical content, identical insertion order), writes
  via the existing temp-file + `os.replace` convention, reloads the file,
  verifies the persisted transitioned entry, and only then updates its
  in-memory state — a failed write/verification leaves the record's state
  unchanged.

This is a Core persistence primitive, not a producer capability: no
producer/MCP/CLI path reaches it, and `DecisionIndexService.propose`
still cannot create any status other than `proposed` (regression-pinned).

## Deterministic canonical decision ID algorithm (pinned)

```text
default_decision_id = "ddec-" + SHA-256(
    canonical_json([proposal_id, producer_key, content_fingerprint])
)[:32]
```

`canonical_json` = `json.dumps(sort_keys=True, separators=(",", ":"),
ensure_ascii=True)` — the same canonicalization as `decision_proposal`.
Properties (test-pinned, including the golden vector
`["dprop-fixed","producer-key-fixed","content-fp-fixed"] →
"ddec-832ab13f18f4f9ad00b957b12a9cde5e"`):

- same proposal → same default id (deterministic; independent of the clock
  and of service/store instances);
- different proposal identity (content or provenance) → different default id;
- namespace separation: proposals live in `dprop-`, canonical decisions in
  `ddec-`; a canonical decision id never equals a proposal id;
- no random UUID identity;
- an explicit human-authority-assigned `decision_id` is supported: it must
  be a non-empty string, must NOT begin with the reserved `dprop-` prefix
  (rejected even without an exact id collision), and must not equal any
  actual proposal id (`DecisionIdNamespaceError` otherwise); it is NOT
  required to begin `ddec-`; once the proposal records an
  `accepted_decision_id`, retries reuse the stored id and any different
  requested id fails closed (`AcceptedProposalIdConflictError`).

## Materialized decision schema

Exactly one entry appended to `project_memory.json decisions[]`:

| Key | Value |
|---|---|
| `id` | accepted canonical decision id (`ddec-…` default or explicit authority id) |
| `decision` | proposal statement |
| `rationale` | proposal rationale |
| `scope` | proposal scope hints — decision/retrieval scope only (never include/exclude paths, never typed-rule applicability, never enforcement scope) |
| `constraints` | `[]` |
| `anti_patterns` | `[]` |
| `rules` | `[]` |
| `test_evidence` | `[]` |
| `created_at` / `updated_at` | authority clock (one value, initially equal) |
| `status` | `"active"` |

The proposal `title` is deliberately NOT materialized (no architecture
contract assigns it a semantic field). Proposal prose generates no
constraints, anti-patterns, typed rules, test evidence, or trusted
evidence. `active` = authoritative and eligible for the existing
runtime/Audit only — never Protected/enforced/rule-bearing/evidence-bearing;
protection activation is never called from D2C1. The canonical record keeps
empty `source_evidence` (no fabricated ADR/runtime provenance).

## Atomic-write / recovery sequence (exact)

1. validate everything before mutation: proposal exists and is not
   rejected; requested explicit id is non-empty and outside the proposal
   namespace; memory file exists, parses, is an object, and loads
   successfully through the existing `MemoryStore` schema (`decisions`
   initialized to `[]` only where existing conventions permit —
   `adr_import.write_imported_decisions`; malformed memory is never
   silently repaired); collision scan complete; transition legality
   established;
2. atomically transition the proposal `proposed → accepted +
   accepted_decision_id` (store primitive above) — never reversed with
   step 3;
3. atomically materialize the decision into `project_memory.json` via the
   existing `setup_state.atomic_write_json` (raw read-modify-write,
   every other top-level key preserved verbatim);
4. reload memory through a fresh `MemoryStore`;
5. derive canonical records through the existing
   `decisions_to_canonical()` (D0 adapter, unchanged);
6. verify the expected canonical identity/content (see below);
7. only then return `AcceptResult(..., verified=True)`.

Recovery/idempotency matrix (all test-proven):

| State | Retry behavior |
|---|---|
| proposed + memory missing decision | normal path: transition, materialize, verify (exact initial shape), success |
| accepted + memory missing decision (crash after step 2) | reuse stored id, materialize, verify (exact initial shape); `already_accepted=True, recovered=True`; no new id |
| accepted + memory holds the exact bare decision | no duplicate, no write, verify; idempotent `already_accepted=True` |
| accepted + memory holds the decision enriched downstream (protection rules, declared evidence, later `updated_at`) | idempotent success, `already_accepted=True, materialized=False`; only D2C-owned identity fields verified; enrichment tolerated, never deleted/rewritten |
| proposed + memory already holds the would-be decision | `ReverseHalfStateError` — acceptance is never inferred, proposal never auto-transitioned, no mutation |
| accepted + same id, D2C-owned identity fields mismatch (different statement/rationale/scope/constraints/anti-patterns or illegal status) | `DecisionIdCollisionError` — never overwritten, never merged |
| accepted + retry with a different requested `accepted_decision_id` | `AcceptedProposalIdConflictError` (service) / `ValueError` (store, both implementations) — the stored id can never be replaced |
| reload/derive/verify failure after writes | typed verification error; no success ever reported; retry completes idempotently |

## Canonical verification (both representations)

Verification is split into the same two cases as the retry contract:

**Case A — D2C writes the decision in this call (fresh materialization or
crash recovery).** After the write the service:

1. reloads through `MemoryStore`;
2. finds the runtime `Decision` by the accepted decision id;
3. asserts the exact initial D2C shape: `decision/rationale/scope` map
   exactly to `statement/rationale/scope_hints`, `constraints`,
   `anti_patterns`, `rules`, and `test_evidence` are empty,
   `status == "active"`, and `created_at`/`updated_at` both equal the
   authority clock value used for the write;
4. runs the existing `decisions_to_canonical()` adapter (D0 adapter,
   unchanged) over the reloaded decisions;
5. finds the canonical record by the same id and asserts
   `version == CANONICAL_VERSION ("1")`, `lifecycle_status == "active"`,
   `statement`, `rationale`, `context_scope == tuple(scope_hints)`,
   `constraints == ()`, `anti_patterns == ()`, and the D2C
   no-fabrication invariants `derived_rule_ids == ()` and
   `test_evidence == ()`.

**Case B — already-accepted proposal with an existing decision.** The
service verifies only the fields whose identity/content D2C owns and
that establish this is the same accepted decision:

- runtime: `id` (lookup), `decision == statement`, `rationale`,
  `scope == scope_hints`, `constraints == []`, `anti_patterns == []`,
  `status` in `VALID_LIFECYCLE_STATUSES`, `created_at` exists;
- canonical: `version == "1"`, `lifecycle_status` legal and equal to the
  runtime status, `statement`, `rationale`,
  `context_scope == tuple(scope_hints)`, `constraints == ()`,
  `anti_patterns == ()`.

It does NOT require `rules`, canonical `derived_rule_ids`,
`test_evidence`, or `updated_at` to remain empty: downstream-owned/
enrichable fields are tolerated exactly as stored, and downstream
enrichment is never deleted, normalized, overwritten, or mutated. At
minimum, legitimate protection activation survives a later acceptance
retry (regression-pinned via the existing protection write primitive).

No Audit tier is assigned or asserted in D2C1 (the narrow regression only
proves the materialized decision loads through the existing `MemoryStore`).

## Provenance limitation

Full producer provenance stays durably preserved in the retained proposal
(`proposal_id`, producer fields, source reference/version/locator,
`origin_classification`, `proposed_at`, `accepted_decision_id`); the
durable proposal ↔ canonical decision link is `accepted_decision_id`. The
runtime `Decision` / `decisions_to_canonical` path does NOT carry proposal
provenance into `CanonicalSourceEvidence`, and D2C1 claims otherwise
nowhere: the materialized memory entry has no `source` block and the
canonical record keeps empty `source_evidence`. Nothing is fabricated
(no ADR provenance, no verified provenance, no trusted evidence, no
verification status). `CanonicalSourceEvidence` was NOT broadened; a
richer canonical provenance representation requires a separate,
explicitly reviewed architecture extension.

## MCP inventory unchanged

Exactly the six D2B tools remain: `decision.propose`,
`decision.propose_batch`, `decision.get`, `decision.search`,
`decision.applicable_to`, `decision.trace`. `mneme/decision_mcp.py` was
not modified; no `decision.accept/reject/activate/supersede/
create_exception/bypass/submit_trusted_evidence` operation or alias
exists anywhere (regression-pinned). The MCP never imports
`decision_authority`.

## Exact commands

```text
python scripts/new_task_worktree.py feat/d2c1-decision-authority
python -m pytest tests/test_decision_authority.py -q
python -m pytest tests/test_decision_proposal.py tests/test_decision_index_service.py tests/test_decision_index_consumer_reads.py tests/test_decision_mcp.py tests/test_decision_index.py tests/test_decision_projection.py -q
python -m pytest tests/test_protection_activation.py -q
python -m pytest tests/test_test_policy.py -q
python scripts/run_test_battery.py gate
python -m mneme.cli check --memory .mneme/project_memory.json --input mneme/decision_authority.py --query "feat: add decision authority service mneme/decision_authority.py" --mode warn
python -m mneme.cli check --memory .mneme/project_memory.json --input mneme/decision_proposal_store.py --query "feat: add decision authority service mneme/decision_proposal_store.py" --mode warn
python -m mneme.cli check --memory .mneme/project_memory.json --input scripts/run_test_battery.py --query "feat: add decision authority service scripts/run_test_battery.py" --mode warn
python scripts/check_encoding.py
```

All commands were run on the exact tested implementation SHA on both the
original implementation state and the architecture-review revision state.

## Results

| Check | Result |
|---|---|
| Focused D2C1 tests (`tests/test_decision_authority.py`, registered in the gate manifest) | 72 passed (66 original + 6 review-fix regressions; all 66 preserved) |
| D2A/D2B0/D2B/D0 targeted regressions (`test_decision_proposal.py`, `test_decision_index_service.py`, `test_decision_index_consumer_reads.py`, `test_decision_mcp.py`, `test_decision_index.py`, `test_decision_projection.py`) | 200 passed |
| Protection regression (`tests/test_protection_activation.py`) | 27 passed (protection semantics unchanged; the downstream-enrichment retry test exercises its write primitive without behavior change) |
| Test-policy manifest check (`test_test_policy.py`) | 19 passed |
| Gate battery (`scripts/run_test_battery.py gate`) | 1501 passed, 5 skipped (pre-existing, unrelated; baseline 1495+5 + 6 new review-fix tests) |
| `mneme check --mode warn` on changed governed files (`mneme/decision_authority.py`, `mneme/decision_proposal_store.py`, `scripts/run_test_battery.py`) | 3/3 PASS (warnings pre-existing) |
| `scripts/check_encoding.py` (mojibake + BOM) | OK (1630 files) |

## Authority matrix (D2C1)

```text
proposal producer can accept? NO
MCP can accept/reject? NO
CLI owns authority semantics? NO
authority semantics live in Core? YES
accepted proposal creates typed rule? NO
scope hint becomes rule applicability? NO
accepted decision is automatically Protected? NO
producer provenance becomes trusted evidence? NO
decision collision overwrites existing decision? NO
reverse half-state auto-healed? NO
crash after proposal acceptance is recoverable? YES
canonical identity survives storage path? YES
frozen runtime semantic delta? NO
```

## Benchmark trigger

**NOT MET.** D2C1 adds authority persistence; it does not modify
`decision_retriever.py`, `enforcer.py`, `conflict_detector.py`,
`benchmark.py`, `rule_matcher.py`, `path_selectors.py`, Audit tier
semantics, ADR-020 applicability, protection activation, canonical
projection semantics, or trusted-evidence semantics (attestation below).
Retrieval/enforcement/benchmark semantics are unchanged, so the frozen
enforcement benchmark was not re-run.

## Frozen-boundary attestation

- `decision_retriever.py`, `enforcer.py`, `conflict_detector.py`,
  `benchmark.py`, `rule_matcher.py`, `path_selectors.py` behaviorally
  changed? NO (untouched)
- `decision_index.py` / `decision_projection.py` /
  `decision_index_service.py` / `decision_mcp.py` /
  `decision_proposal.py` / `memory_store.py` / `protection.py` /
  `setup_state.py` / `cli.py` modified? NO (untouched)
- `decision_proposal_store.py` producer semantics changed? NO
  (`add_if_new`/`get`/`list_proposals` untouched; only the Core authority
  primitive `transition_if_proposed` was added, and the review fix
  changed only its already-at-target conflict behavior)
- `protection.py` behavior changed? NO (untouched; the downstream-
  enrichment retry test invokes the existing `_install_rule` write
  primitive on tmp_path fixtures only — D2C tolerates, never calls,
  protection activation itself)
- MCP six-tool inventory changed? NO (regression-pinned)
- Audit tier semantics changed? NO
- benchmark fixtures changed? NO
- `.mneme/project_memory.json` changed? NO (test/memory changes only in
  tmp_path fixtures)

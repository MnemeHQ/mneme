# D2D — Generic MCP producer → human authority → Architecture Audit E2E (ADR-023, ADR-027, issues #362/#365)

The final D2 validation milestone. Test + validation only: **zero runtime
changes**. Validates the single D2D architectural question:

> Can a completely generic architecture-producing system submit candidate
> decisions through Mneme's existing MCP contract, without understanding
> Mneme's enforcement schema, after which a human can review/accept them
> through Mneme authority and the ordinary Architecture Audit evaluates
> the resulting decisions?

The reference producer is `sagarika29/ai-system-architect` — a validation
fixture only. There is **no Sagarika-specific path in Core, MCP, or any
runtime module**; producer-specific content exists only in the pinned
test fixture and its test module, and a dedicated test proves no runtime
module gained producer-specific logic.

## Architecture conclusion

No architecture conflict. The expected cross-component flow already
exists end to end and behaves exactly as ADR-027 records:

```text
generic producer (source-backed fixture, pinned commit)
        |
        | MCP SDK Client -> build_server_from_parts -> decision.propose_batch
        v
proposed proposals only (JsonFileDecisionProposalStore)
        |
        | human review CLI: mneme decision proposals / show
        | human authority CLI: mneme decision accept / reject
        v
project_memory.json decisions[]
        |
        | mneme audit --memory ... --json ...
        v
existing Architecture Audit (mneme.audit/v1, ADR-026 tier semantics)
        |
        v
existing protection tiers
```

A generic producer needs only the producer-controlled candidate fields
(title, statement, rationale, provenance, scope_hints,
architecture_context, related_decision_ids). It never needs Mneme's
enforcement schema, and the frozen transport structurally rejects every
authority field it could attempt.

## Exact SHA evidence

- Base SHA (canonical `origin/main`):
  `b46703e8d9a83576c8a1ae4ad25a1bf6de50ffbd`
- Exact tested implementation SHA:
  `f4ff6157a0ccdd1fe61feee23e09b3c7b29e09b2` (single commit directly on
  top of the base SHA; all test/gate/hygiene figures below executed on
  this exact source state)
- The next commit adds this validation artifact only (docs-only; no
  runtime or test bytes differ from the tested SHA).
- Branch `test/d2d-generic-producer-e2e`, worktree
  `.worktrees/test-d2d-generic-producer-e2e`, created from `origin/main`
  with `scripts/new_task_worktree.py` and context-verified with
  `scripts/check_worktree_context.py` before work and before every commit.
- Administrative checkout `C:/dev/mneme` stayed clean on `main`.

## Reference producer (pinned)

| Item | Value |
|---|---|
| Repository | `sagarika29/ai-system-architect` |
| Pinned commit SHA | `0797e2736a1b288ae136b8f093644e3cc2406f6f` |
| Pin verification | remote `main` HEAD equals the pinned SHA at preflight (2026-09-15); the fixture never floats against future producer changes |

Exact source files used (blob SHAs at the pinned commit, recorded in the
fixture):

| Source file | Blob SHA |
|---|---|
| `docs/architecture-boundaries-base.md` | `b26f5a0d28ccfb24c12f9c36d1c2a722d39a326f` |
| `docs/architecture-guide.md` | `7928712da2b01bb1e3747395550c5f6a7873dc63` |
| `src/ai_system_architect/core/validation.py` | `c04dc3640de754bd0b407692521ceff4d1d4664c` |
| `src/ai_system_architect/services/architecture.py` | `977ff3b78c928bdf9247d820c6a6f7122d7ace39` |
| `docs/sample_output/customer_support_chatbot.md` | `6acd84d0d23045024c02f9941abf0dd2a211e4df` |

Only the minimum source-backed material was retained (exact supporting
sentences per candidate); no large source passages were copied into
Mneme, and no runtime code reads the fixture.

## Source → candidate mapping (source-backed, 4 candidates)

| # | Candidate key | Statement (submitted verbatim) | Supporting source passages (exact) | Human authority |
|---|---|---|---|---|
| 1 | `fail_closed_output_contract` | Generated architecture output must fail closed when required sections are missing. | boundaries-base: "Fail closed if the output is missing required sections."; guide: "If the contract is broken, the app fails closed instead of showing partial output as complete."; `validation.py`: `"Generated markdown is missing required sections"` (OutputValidationError path) | accepted |
| 2 | `reject_empty_input` | The architecture generator must reject empty use case descriptions. | boundaries-base: "Empty input rejection" (Deterministic list); `architecture.py`: `raise ValueError("Use case description must not be empty.")` | accepted |
| 3 | `testable_decisions_stay_deterministic` | If a decision can be unit tested, it should be deterministic; judgment-dependent decisions can stay probabilistic. | boundaries-base: "If a decision can be unit tested, it should be deterministic."; "If a decision depends on domain judgment, tradeoffs, or incomplete context, it can stay probabilistic."; rationale passage: "The goal is to narrow its job to places where judgment is useful and variability is acceptable." | accepted |
| 4 | `no_sensitive_data_beyond_session` | No sensitive data is retained beyond session duration. | sample_output/customer_support_chatbot.md §8: "No sensitive data is retained beyond session duration." (§0 assumptions are explicitly provisional: "Assumed Internal") | **rejected** |

Human rejection rationale (authority-side judgment, recorded here): the
statement is material from a single AI-generated draft whose context is
explicitly *assumed* in the source (§0 Assumptions); it is not a durable
architectural decision the reviewer elects to materialize. Rejection
exercises the negative control.

No invented decisions: every statement is anchored to exact recorded
source text via per-candidate `anchored_terms` (test-pinned), and every
excerpt names its source file at the pinned commit.

## Provenance (exactly as submitted over MCP)

Batch-level shared provenance (all four candidates originate from one
architecture source):

```text
producer_name          = ai-system-architect
producer_type          = architecture agent
source_reference       = docs/architecture-boundaries-base.md
external_source_id     = (empty — the producer has none; not invented)
source_version         = 0797e2736a1b288ae136b8f093644e3cc2406f6f
repository_locator     = sagarika29/ai-system-architect
origin_classification  = ai_generated          (existing vocabulary)
```

Candidate 4 additionally supplies its own full provenance with
`source_reference = docs/sample_output/customer_support_chatbot.md`
(a separate source document from the same producer/commit); the
documented service merge makes the candidate's provenance win. Producer
provenance is never marked trusted or verified.

## Actual MCP batch payload shape

Tool: `decision.propose_batch` (MCP SDK Client → real registered server).

```json
{
  "candidates": [
    {
      "title": "Fail closed on a broken architecture output contract",
      "statement": "Generated architecture output must fail closed when required sections are missing.",
      "rationale": "If the contract is broken, the app fails closed instead of showing partial output as complete.",
      "scope_hints": ["architecture-generation", "output-validation"],
      "architecture_context": {"component": "output-validator", "boundary": "deterministic"},
      "related_decision_ids": []
    },
    { "...same producer fields for reject_empty_input..." },
    { "...testable_decisions_stay_deterministic..." },
    {
      "...no_sensitive_data_beyond_session...",
      "provenance": {
        "producer_name": "ai-system-architect",
        "producer_type": "architecture agent",
        "source_reference": "docs/sample_output/customer_support_chatbot.md",
        "source_version": "0797e2736a1b288ae136b8f093644e3cc2406f6f",
        "repository_locator": "sagarika29/ai-system-architect",
        "origin_classification": "ai_generated"
      }
    }
  ],
  "shared_provenance": {
    "producer_name": "ai-system-architect",
    "producer_type": "architecture agent",
    "source_reference": "docs/architecture-boundaries-base.md",
    "source_version": "0797e2736a1b288ae136b8f093644e3cc2406f6f",
    "repository_locator": "sagarika29/ai-system-architect",
    "origin_classification": "ai_generated"
  }
}
```

No authority field appears anywhere in the payload; `candidates[0..2]`
omit per-candidate provenance entirely (shared batch provenance covers
them) — both documented provenance paths are exercised in one batch.

## First-ingestion results (through the real MCP transport)

`build_server_from_parts(JsonFileDecisionProposalStore(path),
canonical_index=None, clock=fixed)` — the composition `mneme
decision-mcp` uses by default; an in-process MCP SDK `Client` talks to
the real registered server/tool handlers (no network, no external
services).

- succeeds through MCP (`is_error == False`); one result per candidate,
  order preserved;
- every proposal status `proposed`; every proposal has a stable
  `dprop-`-prefixed id (deterministic D2A hashing);
- provenance round-trips losslessly; `proposed_at` is service-owned
  (injected clock value, `2026-09-15T12:00:00Z`);
- no proposal has `accepted_decision_id`; no canonical decision exists;
  `project_memory.json` unchanged (`decisions[]` empty); no rule, no
  declared/trusted evidence, no protection state anywhere.

Observed deterministic proposal IDs:

| Candidate | proposal_id |
|---|---|
| fail_closed_output_contract | `dprop-9debfe7446ac6c4c01edfd20830c1058` |
| reject_empty_input | `dprop-0b1ae3450a8d81dba2d7670834b43093` |
| testable_decisions_stay_deterministic | `dprop-51fc3620b1f82d6307d757ad4095efb6` |
| no_sensitive_data_beyond_session | `dprop-d714c83d12a737d76eec8e0b45aef35b` |

## Idempotent resend results

The byte/semantically identical batch was resent twice:

1. same server instance: every candidate `created == False`,
   `reused == True`, identical proposal ids, byte-identical proposal
   records (only the envelope outcome flags differ);
2. fully reconstructed server over the same durable store:
   still idempotent, same proposal ids, no duplicates, no writes.

No semantic auto-deduplication was added; per-candidate deterministic
identity behaves exactly as D2A pinned it.

## MCP read results (before authority)

All four read tools exercised through MCP per their existing contracts:

- `decision.get(proposal_id)` → `record_type == "proposal"`, proposal
  domain only (`proposal_status == "proposed"`; no canonical lifecycle
  key); `accepted_decision_id == None`;
- `decision.search` finds the relevant proposals deterministically
  (text query, `proposal_status`, `producer_name`,
  `origin_classification` filters); proposal and canonical domains stay
  in separate lists (canonical list empty);
- `decision.applicable_to` matches proposal scope hints as retrieval
  hints only — path-shaped matching never fires, and the result shape
  carries no rule payload / selectors / enforcement data;
- `decision.trace(proposal_id)` → `result_type == "proposal_trace"`,
  source provenance exposed, `accepted_decision_id` `None`,
  `canonical_record` `None`, empty derived-rule ids, and explicit
  `missing_links` (accepted_decision_id / canonical_record /
  derived_rules / enforcement / trusted_evidence absent). Nothing
  fabricated;
- unknown ids: `decision.get` → typed `not_found`; `decision.trace` →
  typed `trace_not_found` (type-unknown identifier).

## Producer knowledge boundary (negative control)

A batch tampered with authority fields (`accepted_decision_id`,
`status`, `trusted_evidence`, `include_paths`, `proposed_at`, and
`shared_provenance.status`) is rejected by the existing transport schema
(`extra="forbid"`): `is_error == True` with the field named; the schema
was NOT changed to make this test pass; nothing is ingested through a
failed attempt.

## Human authority

Review through the existing human CLI (`mneme decision proposals`,
`mneme decision show <id>` — statuses, full informational provenance,
no trusted/verified language), then deliberate authority actions:

- `mneme decision accept` × 3 (candidates 1–3) — exit 0,
  "Accepted proposal", decision id assigned;
- `mneme decision reject` × 1 (candidate 4) — exit 0,
  "Rejected proposal".

The producer itself never performs any transition; MCP exposes no
accept/reject operation (inventory-pinned).

## Accepted / rejected IDs (deterministic, observed)

| Proposal | accepted_decision_id |
|---|---|
| `dprop-9debfe7446ac6c4c01edfd20830c1058` | `ddec-cbfd32a73a6ca489dc30fb12e9b7fd95` |
| `dprop-0b1ae3450a8d81dba2d7670834b43093` | `ddec-481e8ef9740f60ed1f2c6ab1ac9b0824` |
| `dprop-51fc3620b1f82d6307d757ad4095efb6` | `ddec-a77c4647dbe3ccb5984a4fafacc3040e` |
| `dprop-d714c83d12a737d76eec8e0b45aef35b` | (none — rejected; never materialized) |

Each accepted decision id equals the pinned D2C1 default
(`"ddec-" + SHA-256(canonical_json([proposal_id, producer_key,
content_fingerprint]))[:32]`), verified in-test via
`default_decision_id_of`.

## Materialized runtime shape (per accepted decision, exact)

`project_memory.json decisions[]` entry: statement → `decision`;
rationale → `rationale`; scope hints → `scope`; `constraints == []`;
`anti_patterns == []`; `rules == []`; `test_evidence == []`;
`status == "active"`; authority-clock timestamps. Nothing else is
written; no rule, no evidence, no protection was activated.

## Audit results (existing semantics only)

`mneme audit --memory <isolated memory> --json <report>` — schema
`mneme.audit/v1` (unchanged). Per-decision results under frozen ADR-026
semantics (acceptance itself never assigns a tier):

| Accepted statement | intent | protection_tier | mneme_guardrail | evidence_confidence |
|---|---|---|---|---|
| fail-closed output contract | deterministic | `requires_modelling` | None | none |
| reject empty input | deterministic | `requires_modelling` | None | none |
| unit-testable boundary rule | guidance | `guidance` | None | none |

Aggregate (isolated fixture: 0 ready / 2 modelling / 1 guidance /
0 protected): `total_decisions == 3`, `protected == 0`,
`mneme_ready == 0`, `requires_modelling == 2`, `guidance == 1`,
`protection_relevant == 2`, `current_protection_pct == 0.0`,
`protection_gap_pct == 100.0`,
`identified_mneme_potential_pct == 100.0` — existing formulas, no
forced tiers.

## Identity linkage

For every accepted proposal:

```text
proposal.accepted_decision_id == runtime Decision.id == Audit decision.id
```

## Provenance / evidence behavior

- Full producer provenance (producer name/type, source reference,
  source version = pinned SHA, repository locator, origin
  classification) remains intact in the retained proposals after all
  authority actions and Audit runs.
- Producer provenance is NOT enforcement evidence: every audited
  decision reports `evidence_confidence == "none"` with empty
  `evidence_sources` despite rich provenance in the store.
- Audit is read-only: proposal store + project memory byte-identical
  across both Audit runs; a second identical Audit run is
  byte-identical.

## Post-authority MCP visibility (explicitly characterized)

The proposal store was mutated by a separate human authority surface.
A reconstructed MCP server (same supported inputs: the durable proposal
store path; the CLI default composition) observes:

- `decision.get(<proposal_id>)` → `proposal_status == "accepted"`,
  `accepted_decision_id == <durable ddec id>`;
- `decision.trace(<proposal_id>)` → `result_type == "proposal_trace"`
  with the accepted decision id exposed and **no fabricated links**:
  `canonical_record == null` with the explicit missing link
  `"canonical_record: accepted_decision_id 'ddec-…' cannot be resolved
  (no canonical index supplied)"`, plus the always-explicit
  `"enforcement_links: absent"` and
  `"trusted_evidence: absent"` lines.

### Canonical accepted-decision visibility (inspected and tested, not guessed)

The current supported MCP composition does **NOT** expose the accepted
`project_memory`-backed decision as a canonical MCP record:

- `mneme decision-mcp` composes canonical state only from an explicit
  strict `--adr-dir` corpus (`load_canonical_index_from_adr_dir`); its
  only inputs are `--proposals` and `--adr-dir` (test-pinned: `--help`
  exposes no `--memory` or runtime-ledger input);
- `decision.get(<accepted ddec id>)` on the reconstructed server returns
  the honest typed `not_found`; `decision.trace(<accepted ddec id>)`
  returns typed `trace_not_found`.

**Assessment: (A) an acceptable documented D2 limitation under the
current ADR/issue contract.** Grounds:

1. ADR-027's acceptance requirements (stable canonical id, initial
   canonical version, retained proposal + provenance) are satisfied at
   the Core level — D2C1 proves both runtime and canonical
   representations exist after acceptance; nothing in ADR-027 or #362
   requires the local OSS stdio server to compose the runtime ledger
   into its canonical index.
2. The D2C amendment explicitly bounds `project_memory.json` as the
   current durable backing pending the separately reviewed durable-
   canonical storage work (D1) — out of scope here by instruction.
3. The accepted decision is fully visible through existing Mneme
   surfaces (authority CLI; existing Architecture Audit via
   `MemoryStore`, validated in D2C3 and again below).
4. Honest reporting everywhere: `get`/`trace` return explicit
   not-found/absent links rather than fabricated canonical data; no
   `--memory` was silently added; canonical composition was not changed.

Recorded as a known limitation for documentation publication (below).

## Long-running MCP store freshness (explicitly characterized)

Tested, not assumed: a server instance built **before** the external CLI
authority action does **NOT** observe the transition without restart —
`decision.get` keeps serving the in-memory `proposed` record, while a
reconstructed server correctly reads the durable `accepted` state
(both test-pinned). This matches the documented D2B store contract
("loaded once at construction"); no architecture promise of live
cross-process refresh exists (automatic document watching is explicitly
P1-deferred in #362), so no file-watching/reload behavior was added and
this is recorded as expected current behavior — each producer session
gets a fresh server process under the stdio convention.

## Six-tool inventory (exact, confirmed through a real client)

```text
decision.propose
decision.propose_batch
decision.get
decision.search
decision.applicable_to
decision.trace
```

Exactly six registered tools, listed through the MCP SDK client against
the real server; no authority tool or alias exists (test-pinned).

## No Sagarika-specific runtime code

- `mneme/*.py` scanned: the strings `sagarika` / `ai-system-architect`
  occur exactly once in runtime code — the pre-existing ADR-026
  provenance comment in `mneme/enforcer.py` (part of the validated
  pre-D2D baseline; D2D modified nothing). Zero new runtime
  occurrences.
- Zero fixture-derived tokens (producer fixture paths/names, candidate
  titles/statements) appear in any runtime module; no runtime module
  imports the test suite.
- Producer-specific content lives only in
  `tests/test_decision_mcp_producer_e2e.py` +
  `tests/fixtures/d2d_generic_producer/producer_fixture.json`.

## Files changed

| File | Change |
|---|---|
| `tests/test_decision_mcp_producer_e2e.py` | new — the D2D E2E suite (15 tests) |
| `tests/fixtures/d2d_generic_producer/producer_fixture.json` | new — pinned, source-backed producer fixture |
| `scripts/run_test_battery.py` | gate manifest: registered the new E2E under `GATE_CORE_PATHS` (test-policy anti-aging invariant) |
| `docs/validation/d2d-generic-mcp-producer-e2e.md` | this artifact |

No runtime file was modified: `mneme/decision_mcp.py`,
`mneme/decision_index_service.py`, `mneme/decision_authority.py`,
`mneme/decision_proposal.py`, `mneme/decision_proposal_store.py`,
`mneme/decision_index.py`, `mneme/decision_projection.py`,
`mneme/memory_store.py`, `mneme/enforcer.py`, `mneme/protection.py`,
`mneme/cli.py` are all untouched (frozen semantic delta: none).

## Required assertion matrix (section 20 checklist)

```text
generic producer needs Mneme enforcement schema? NO
producer can create proposal? YES
producer can create Active decision? NO
producer can accept/reject? NO
producer can create typed rule? NO
producer can assert Protected? NO
producer can fabricate trusted evidence? NO
proposal batch idempotent? YES
human authority required? YES
accepted decision reaches existing Audit? YES
acceptance automatically Protected? NO
rejected proposal reaches Audit? NO
scope hint becomes ADR-020 applicability? NO
Sagarika-specific runtime code? NO
MCP tools remain exactly six? YES
hosted/org authority introduced? NO
runtime semantic delta? NO
```

## Benchmark decision

**NOT MET / NOT triggered.** D2D makes no runtime retrieval, enforcement,
Audit, projection, or benchmark semantic change — expected zero runtime
delta, confirmed: the only changed files are a test module, a test
fixture, the gate manifest, and this artifact. The frozen enforcement
benchmark was not re-run.

## Focused tests

`python -m pytest tests/test_decision_mcp_producer_e2e.py -v` —
**15 passed** (source pin, candidate traceability, MCP batch ingestion,
idempotent resend in-process + across restart, authority-field rejection,
MCP reads before authority, human review CLI, authority accept/reject,
rejected negative control, no-MCP-authority proof, Audit results,
post-authority reconstructed-MCP visibility, composition-boundary
inspection, long-running freshness, no-runtime-producer-logic).

## Targeted regressions

`tests/test_decision_mcp.py`, `tests/test_decision_index_service.py`,
`tests/test_decision_proposal.py`, `tests/test_decision_authority.py`,
`tests/test_decision_authority_cli.py`,
`tests/test_decision_authority_audit_e2e.py`,
`tests/test_audit_tier_semantics.py`, `tests/test_cli_audit.py` —
**277 passed**. Plus `tests/test_test_policy.py` (gate-manifest change)
— **19 passed**.

## Gate result

`python scripts/run_test_battery.py gate` — **1561 passed, 5 skipped**
(pre-existing skips; D2C3 baseline 1546+5 + 15 new). Green on the exact
tested SHA.

## Required hygiene checks

- `python scripts/check_encoding.py` — OK (1632 files scanned).
- `python scripts/check_install_command.py` — OK.
- `mneme check --mode warn` on the changed governed file
  (`scripts/run_test_battery.py`) — `Result: PASS` (pre-existing
  repository-wide ADR freshness warnings only, warn-mode).

## Runtime semantic delta

None. Expected NO, confirmed NO: no runtime file changed in this
milestone; the only behavior added is the new test module itself.

---

## Documentation publication readiness (REQUIRED, section 21)

**Verdict: READY TO DRAFT, NOT PUBLISH.** Main is validated on this
milestone, but the latest published PyPI package does not yet contain the
full D2 behavior line (D2B–D2D); release publication is the remaining
blocker, and the canonical-composition limitation below must appear in
the drafts. Packaging/release scope is not changed inside D2D.

| Area | Verdict | Notes |
|---|---|---|
| A. `/docs/mcp/` | READY TO DRAFT, NOT PUBLISH | Six-tool contract frozen and validated (D2B + D2D); input schema and error contract documented in the D2B artifact and now producer-workflow-validated; installation extra accurate (`pip install 'mneme-hq[mcp]'`, optional extra); stdio-only transport; long-running-instance staleness must be documented as known behavior (no live cross-process refresh promised or provided). |
| B. `/integrations/mcp/` | READY TO DRAFT, NOT PUBLISH | The generic-producer integration path is now validated end to end (Sagarika reference at a pinned commit); draft may present `decision.propose_batch` + shared provenance + human authority as the validated workflow; must state the pinned-compatibility reference and that acceptance is never an MCP operation. Publication blocked pending the release containing D2B–D2D behavior. |
| C. `/docs/decision-proposals/` | READY TO DRAFT, NOT PUBLISH | Proposal lifecycle documented honestly (proposed → accepted/rejected; terminal states; idempotent resends; append-preserving history); human accept/reject CLI exists and is validated (D2C2/D2C3/D2D); Audit workflow validated; known limitation must be documented: an accepted proposal's canonical decision is not yet composed into the MCP server's canonical index (proposal trace reports the linkage honestly; the accepted decision remains visible through Mneme's existing surfaces). |

Publication checks: six-tool contract frozen and validated ✓;
installation extra/command accurate ✓ (`mneme-hq[mcp]` optional extra);
proposal lifecycle honest ✓; human CLI validated ✓; Audit workflow
validated ✓; known MCP canonical-composition/freshness limitations
documented in this artifact and to be carried into drafts ✓; no
future/unreleased behavior presented as available — drafts only until
the PyPI release contains D2B–D2D functionality.

## D2 closure verdict

**D2 COMPLETE WITH DOCUMENTED LIMITATION.**

- The generic producer workflow succeeds end to end exactly as ADR-027
  section 11 and #362 specify, with no producer-specific core code and
  the six-tool contract intact.
- The producer workflow does not violate issue #362 or ADR-027: the
  authority invariant holds (only the human CLI transitions lifecycle;
  MCP stays read+propose only); the accepted canonical decision exists
  and is Audit-visible through the existing MemoryStore path.
- The one documented limitation is the MCP canonical-composition gap
  assessed as acceptable (A) above, plus the recorded in-process
  freshness behavior (also per documented contract). Both must be
  carried into the publication drafts.

---

## Related

- ADR-023 — Canonical Decision Index and Runtime Projection Boundary
- ADR-026 — Audit Tier Semantics and Mneme Potential
- ADR-027 — Decision MCP Proposal Ingestion and Authority Boundary
  (including the D2C accepted-proposal authority path amendment)
- #362 (D2 MCP contract), #365 (D2A), #371–#377 (D2A–D2C3 PRs)
- Validation lineage: `d2a`, `d2b0`, `d2b`, `d2c0`, `d2c1`, `d2c2`,
  `d2c3` artifacts

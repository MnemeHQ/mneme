# D2C3 — Accepted decision → Architecture Audit E2E validation (test-only)

Validates the single D2C3 architectural question (ADR-027 accepted-proposal
authority path + ADR-026 tier semantics): **does a human-accepted proposal
become an ordinary architecture Decision that the EXISTING Architecture
Audit evaluates correctly, without any special proposal-aware Audit
logic?**

This milestone is validation only. No Audit redesign, no Audit tier
semantic change, no DecisionAuthorityService change, no MCP change, no
protection activation, and no D2D/Sagarika work. The repository's
existing Audit path was confirmed unchanged before implementation:

```text
project_memory.json
    ↓
MemoryStore
    ↓
store.decisions()
    ↓
generate_protection_report(...)
    ↓
existing ADR-026 tier semantics
    ↓
mneme.audit/v1
```

## Architecture conclusion

No architecture conflict. D2C3 required **no new Audit path and no runtime
semantic change**. The expected cross-component flow already exists end to
end and behaves exactly as ADR-027 "Audit visibility" records:

```text
proposal
    ↓
DecisionAuthorityService / mneme decision accept
    ↓
project_memory.json decisions[]
    ↓
MemoryStore
    ↓
existing Architecture Audit
    ↓
ADR-026 protection tier
```

Audit has no proposal-aware branch; it classifies the materialized
decision from its own frozen semantics, byte-identically to how it
classifies any equivalent hand-written decision.

## Exact SHA evidence

- Base SHA (canonical `origin/main`):
  `08f3fd73baaf90d24111642be938130670cf6942`
- Exact tested implementation SHA:
  `943b2c47de1f22b5af50320266c4c9cc7b568803` (single commit directly on
  top of the base SHA; all figures below executed on this exact source
  state)
- The next commit adds this validation artifact only (docs-only; no
  runtime or test bytes differ from the tested SHA).
- Branch `test/d2c3-authority-audit-e2e`, worktree
  `.worktrees/test-d2c3-authority-audit-e2e`, created from `origin/main`
  with `scripts/new_task_worktree.py` and context-verified with
  `scripts/check_worktree_context.py` before work and before every commit.

## Files changed

| File | Change |
|---|---|
| `tests/test_decision_authority_audit_e2e.py` | new — the D2C3 E2E suite (10 tests) |
| `scripts/run_test_battery.py` | gate manifest: registered the new E2E under `GATE_AUDIT_EVIDENCE_PATHS` (test-policy anti-aging invariant requires classification; new canonical test files otherwise fail `tests/test_test_policy.py`) |
| `docs/validation/d2c3-authority-audit-e2e.md` | this artifact |

No runtime file was modified: `mneme/enforcer.py`, `mneme/cli.py`,
`mneme/decision_authority.py`, `mneme/decision_proposal.py`,
`mneme/decision_proposal_store.py`, `mneme/decision_index_service.py`,
`mneme/decision_index.py`, `mneme/decision_projection.py`,
`mneme/memory_store.py`, `mneme/decision_mcp.py`, `mneme/protection.py`,
`mneme/readiness.py` are all untouched (frozen semantic delta: none).

## E2E flow tested (production paths only)

```text
DecisionIndexService.propose(...)                     Core producer path (NO MCP — D2D validates MCP)
    ↓
mneme decision accept <proposal_id> --proposals … --memory …
    (CLI thin adapter → Core DecisionAuthorityService)
    ↓
project_memory.json decisions[]
    ↓
mneme audit --memory … --json <report.json>           (CLI → MemoryStore → generate_protection_report, no --repo-root)
    ↓
mneme.audit/v1 report
```

- All CLI steps run through `mneme.cli.main([...])`, the repository's
  existing CLI-test convention (`tests/test_cli_audit.py`,
  `tests/test_decision_authority_cli.py`).
- No helper bypasses production paths; no `--repo-root` is supplied
  (deliberately: no external CI evidence).
- One small `mneme decision show` assertion proves the accepted proposal
  remains inspectable (`status: accepted`, `accepted decision: …`);
  CLI presentation itself is D2C2 scope.
- Isolated fixture per test: temporary `decision_proposals.json` +
  empty `.mneme/project_memory.json`; the governed repository is never
  touched.

## Fixture statements (byte-identical to tests/test_audit_tier_semantics.py)

| # | Statement | Producer provenance | Authority action |
|---|---|---|---|
| A | `Generated recommendations must not use the term \`seamless\`.` | `arch-agent` / `DEC-101` / `commit-abc123` | accepted |
| B | `Generated output must contain all required architecture sections; otherwise fail closed.` | `arch-agent` / `DEC-102` / `commit-abc123` | accepted |
| C | `Prefer simple architectures where practical.` | `arch-agent` / `DEC-103` / `commit-abc123` | accepted |
| D | `New code must not import legacy_client.` | `arch-agent` / `DEC-104` / `commit-abc123` | **rejected** |

All four proposals are created through the protocol-independent producer
path (`DecisionIndexService.propose`); D is then rejected through
`mneme decision reject` as the negative control.

## Accepted decision IDs (deterministic, observed in validation runs)

| Proposal | statement | accepted_decision_id |
|---|---|---|
| `dprop-03566c393756a9936249fc917e5dd251` | A (Mneme-ready) | `ddec-75f1503a11846697549c264d5dda0805` |
| `dprop-0e20e6680693022e0e3fa4c6fdf48d67` | B (Requires modelling) | `ddec-8b143d2f6838e04c41127d50de205f01` |
| `dprop-fbb8971c45f19b13fa0eefa72fe35b69` | C (Guidance) | `ddec-8e49fd8bb965c6a31b40ff85c513e8ce` |
| `dprop-ad6d02eaaa03b85a0b31e280f0a29020` | D | (none — rejected; never materialized) |

Proposal and decision ids are deterministic (D2A/D2C1 pinned hashing);
the timestamps of materialization are real authority-clock values and are
not asserted.

## Materialized runtime shape (per accepted decision, exact)

`project_memory.json decisions[]` entry: proposal statement → `decision`;
proposal rationale → `rationale`; proposal scope hints → `scope`;
`constraints == []`; `anti_patterns == []`; `rules == []`;
`test_evidence == []`; `status == "active"`; authority-clock timestamps.
Nothing else is written.

## Audit schema and per-decision tier results

Report schema: `mneme.audit/v1` (unchanged). Entries mapped by decision id:

| Decision | status | intent | protection_tier | mneme_guardrail | evidence_confidence |
|---|---|---|---|---|---|
| A (seamless ban) | active | deterministic | `mneme_ready` | `FORBID_LITERAL: seamless` | none |
| B (fail-closed contract) | active | deterministic | `requires_modelling` | None | none |
| C (prefer simple) | active | guidance | `guidance` | None | none |

The Mneme-ready guardrail is derived by Audit from the explicit decision
text alone; acceptance did NOT install the rule (`rules == []` after
acceptance) and the decision is NOT protected.

## Aggregate metrics (isolated fixture: 1 ready / 1 modelling / 1 guidance / 0 protected)

| Metric | Value |
|---|---|
| `total_decisions` | 3 |
| `protected` | 0 |
| `mneme_ready` | 1 |
| `requires_modelling` | 1 |
| `guidance` | 1 |
| `protection_relevant` | 2 |
| `current_protection_pct` | 0.0 |
| `protection_gap_pct` | 100.0 |
| `identified_mneme_potential_pct` (compatibility payload) | 100.0 |

Metric formulas were NOT changed; the frozen aggregate semantics produce
these values directly.

## Identity / provenance proof

For every accepted proposal:

```text
proposal.accepted_decision_id == runtime Decision.id == audit report decision.id
```

- Full producer provenance (producer name/type, source reference,
  external source id, source version, repository locator, origin
  classification) remains intact in the retained proposal after Audit.
- Audit does not mutate the proposal store (byte snapshot below).
- Audit does not reinterpret producer provenance as trusted/verified
  enforcement evidence: every audited decision reports
  `evidence_confidence == "none"` with empty `evidence_sources`, despite
  rich producer provenance existing in the store.

## Audit read-only proof (byte snapshots)

Snapshot before the first Audit run (after all accept/reject authority
actions): proposal store bytes + project memory bytes. After both Audit
runs:

- proposal store byte-identical;
- project memory byte-identical;
- only the requested JSON report files were written;
- proposal statuses unchanged (3 accepted, 1 rejected);
- no rules, evidence, or status changes added by Audit.

A second identical Audit run produces a **byte-identical** report.

## Central semantic distinction (ACCEPTED != PROTECTED)

The flow proves:

```text
proposal accepted → active authoritative decision → Audit sees it →
mneme_ready / requires_modelling / guidance
```

…not `accepted → Protected`. No typed rule and no verified evidence
exists merely because a human accepted the proposal; `protected == 0` and
`current_protection_pct == 0.0` in the same report that lists a
Mneme-ready guardrail.

## Required test matrix (section 18)

| Assertion | Result |
|---|---|
| accepted proposal becomes authoritative decision? | YES |
| accepted proposal automatically Protected? | NO |
| accepted proposal automatically gets a rule? | NO |
| accepted proposal automatically gets evidence? | NO |
| Audit sees accepted decision through existing MemoryStore path? | YES |
| Audit has proposal-specific branch? | NO |
| Audit assigns tier independently? | YES |
| proposal.accepted_decision_id == Audit decision id? | YES |
| rejected proposal appears in Audit? | NO |
| producer provenance becomes enforcement evidence? | NO |
| Audit mutates proposal store? | NO |
| Audit mutates project memory? | NO |
| MCP inventory changed? | NO |
| Core authority semantics changed? | NO |
| Audit tier semantics changed? | NO |
| frozen runtime semantic delta? | NO |

## Benchmark trigger

**NOT MET.** No retrieval, enforcement, matcher, applicability,
projection, Audit semantics, or benchmark behavior was modified — this
milestone validated an existing cross-component path. The benchmark
instrument was not run and not required by the trigger policy.

## Focused tests

`python -m pytest tests/test_decision_authority_audit_e2e.py -v` —
**10 passed** (E2E chain, no-rule proof, requires-modelling, guidance,
rejected negative control, aggregate metrics, read-only bytes,
deterministic rerun, MCP inventory, four-command authority CLI).

## Targeted regressions

`tests/test_decision_authority.py`,
`tests/test_decision_authority_cli.py`,
`tests/test_audit_tier_semantics.py`, `tests/test_cli_audit.py`,
`tests/test_decision_proposal.py`, `tests/test_decision_index_service.py`,
`tests/test_decision_mcp.py` — **267 passed**.
Plus `tests/test_test_policy.py` (gate-manifest change) — **19 passed**.

## Gate result

`python scripts/run_test_battery.py gate` — **1546 passed, 5 skipped**
(pre-existing skips). Green on the exact tested SHA.

## Required hygiene checks

- `python scripts/check_encoding.py` — OK (1631 files scanned).
- `python scripts/check_install_command.py` — OK.
- `mneme check --mode warn` on the governed changed file
  (`scripts/run_test_battery.py`) — `Result: PASS` (pre-existing
  repository-wide ADR freshness warnings only, warn-mode, non-blocking).

## Runtime semantic delta

None. No frozen runtime semantic changed in this milestone; the only
behavioral surface is the new test module itself.

## Related

- ADR-023 — Canonical Decision Index and Runtime Projection Boundary
- ADR-026 — Audit Tier Semantics and Mneme Potential
- ADR-027 — Decision MCP Proposal Ingestion and Authority Boundary
  (accepted-proposal authority path, D2C amendment)
- #362, #365, #374, #375, #376
- Validation lineage: `d2c0`, `d2c1`, `d2c2` artifacts

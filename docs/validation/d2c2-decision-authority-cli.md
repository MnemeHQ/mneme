# D2C2 — Human decision authority CLI (ADR-027 thin authority adapter)

Implements the D2C2 human authority surface: a thin CLI adapter over the
existing Core `DecisionAuthorityService` (D2C1). No Core authority
semantics were modified; the MCP transport is unchanged (exactly the six
D2B tools); no D2C3 Audit E2E validation, no D2D/Sagarika.

## Exact SHA evidence

- Base SHA (canonical `origin/main`):
  `be01ca42fccef87e1ec59c66e792557bf02f85b7`
- Exact tested implementation SHA:
  `2ceb2180209f8f0681bdbebfe8a752b20f4e48d4` (single commit directly on
  top of the base SHA; all figures below executed on this exact source
  state)
- The next commit updates this validation artifact only (docs-only; no
  runtime or test bytes differ from the tested SHA).
- Branch `feat/d2c2-decision-authority-cli`, worktree
  `.worktrees/feat-d2c2-decision-authority-cli`, context-verified with
  `scripts/check_worktree_context.py` before work and before every
  commit.

## Command surface (exact)

```text
mneme decision proposals [--proposals <path>]
mneme decision show <proposal_id> [--proposals <path>]
mneme decision accept <proposal_id> [--proposals <path>] [--memory <path>] [--decision-id <id>]
mneme decision reject <proposal_id> [--proposals <path>] [--memory <path>]
```

Nested argparse group, following the existing `mneme protect` / `mneme
adr` convention. No aliases were added.

## Defaults (after repository inspection)

- Proposal store: `DEFAULT_PROPOSALS_PATH` = `.mneme/decision_proposals.json`
  (the existing D2B MCP CLI convention, `mneme/cli.py`). All four
  decision commands accept `--proposals` with this default.
- Memory: `DEFAULT_MEMORY_PATH` = `.mneme/project_memory.json` (the
  existing CLI convention, `mneme/cli.py`). `accept` passes it to the
  Core service; `reject` also accepts `--memory` (defaulted) because the
  existing Core constructor requires a `memory_path`, but Core
  `reject()` performs no memory access — the narrowest adapter solution
  consistent with the frozen D2C1 API; Core was not changed.

## Authority delegation (accept)

The CLI does exactly four things: construct
`JsonFileDecisionProposalStore(args.proposals)`, construct
`DecisionAuthorityService(store, args.memory)`, call
`service.accept(args.proposal_id, decision_id=args.decision_id)`, and
render the returned `AcceptResult`. The CLI does not derive default
decision ids, inspect collisions, transition proposals, write
`project_memory.json`, decide recovery, or verify canonical state —
every fact comes from the typed `AcceptResult` / Core errors.

## Authority delegation (reject)

Construct store + service (same as accept), call
`service.reject(args.proposal_id)`, render `RejectResult`. No memory
precheck is added (Core reject performs no memory access, and a CLI
precheck would wrongly require the memory file to exist); no memory
mutation occurs (Core-owned; test-proven byte-identical).

## Output contract

Fresh acceptance:

```text
Accepted proposal <proposal_id>
Decision: <decision_id>
Materialized: yes
Verified: yes

Note: acceptance materializes an active decision; it does not activate
protection or assign an Audit tier.
```

Idempotent retry:

```text
Already accepted: <proposal_id>
Decision: <decision_id>
Materialized: no
Verified: yes
```

Crash recovery:

```text
Recovered accepted proposal: <proposal_id>
Decision: <decision_id>
Materialized: yes
Verified: yes
```

Fresh rejection: `Rejected proposal <proposal_id>`; idempotent
rejection: `Already rejected: <proposal_id>`. The CLI never claims
Protected / enforced / rule installed / verified evidence — D2C2 does
not establish any of those. `mneme audit`, `mneme protect`, and
protection activation are never invoked (monkeypatch-pinned).

## Exit-code mapping (presentation-only)

| Exit | Meaning |
|---|---|
| 0 | success — fresh/idempotent/recovered accept; fresh/idempotent reject; read-only listings |
| 1 | Core authority refusal / fail-closed authority error (`DecisionAuthorityError` rendered verbatim as `ERROR: ...` on stderr, no stack trace) |
| 2 | CLI input error (`ERROR: ...` on stderr, existing `_error_exit` convention): empty `--proposals` value, missing proposal-store file, corrupt/unreadable proposal store, unknown proposal id on a read-only `show` |

The mapping is presentation-only: Core semantics are untouched, no error
string is inspected to infer behavior, and a failed authority operation
is never reported as success (empty stdout, `ERROR:` on stderr).

## Proposal-store safety (fail closed)

All four commands use the durable `JsonFileDecisionProposalStore` and
reject an empty `--proposals` value (no in-memory fallback; test-pinned
that the empty value exits 2 before any service construction). The store
constructor does not create a file when absent (inspected:
`JsonFileDecisionProposalStore._load` returns early), and the CLI adds a
thin path-existence precheck before construction anyway, so a missing or
corrupt store is a deterministic CLI error, never a silently created
empty store. No `InMemoryDecisionProposalStore` use anywhere in the CLI.

## Files changed

| File | Change |
|---|---|
| `mneme/cli.py` | adds the `decision` command group (`proposals`/`show`/`accept`/`reject`), the fail-closed store opener, the authority-error exit helper, and `AcceptResult`/`RejectResult` rendering; imports only `DecisionAuthorityService` + `DecisionAuthorityError` from `mneme.decision_authority` |
| `tests/test_decision_authority_cli.py` | NEW — 35 focused adapter tests (registered in the gate manifest) |
| `tests/test_decision_authority.py` | D2C2 amendment: `test_cli_has_no_authority_surface` → `test_cli_imports_only_the_authority_surface` (the CLI may now be a thin authority adapter; it must reach the Core authority layer only through the service/error names and must not touch authority primitives directly) |
| `scripts/run_test_battery.py` | gate manifest: `tests/test_decision_authority_cli.py` added to `GATE_CLI_PATHS` |
| `docs/validation/d2c2-decision-authority-cli.md` | NEW — this artifact |

Unchanged (frozen, zero diff): `mneme/decision_authority.py`,
`mneme/decision_proposal.py`, `mneme/decision_proposal_store.py`,
`mneme/decision_index_service.py`, `mneme/decision_index.py`,
`mneme/decision_projection.py`, `mneme/decision_mcp.py`,
`mneme/memory_store.py`, `mneme/protection.py`, `mneme/setup_state.py`.

## Read-only inspection contract

`decision proposals`: deterministic store/insertion order; per proposal
shows `proposal_id`, `[status]` (proposed/accepted/rejected), title,
producer name/type, source reference, and `accepted_decision_id` when
present; `(no proposals)` when empty; no ranking, filtering, inference,
classification, or Audit tier display.

`decision show`: renders the stored proposal record — proposal_id,
status, title, statement, rationale, scope hints, architecture context,
related decision ids, `proposed_at`, the full seven-field producer
provenance (labelled "informational, as submitted"; empty optional
components render `(not supplied)`), and `accepted_decision_id` when
present. No trusted/verified/evidence language appears (test-pinned).
Unknown proposal → exit 2.

## Architecture tests (thin-adapter proof)

Behavior-first (no brittle lifecycle duplication):

1. `accept` delegates to `DecisionAuthorityService.accept()` — spy
   replacement proves construction args `(store, memory_path)` and the
   `accept(proposal_id, decision_id=...)` call, including the exact
   store instance (`JsonFileDecisionProposalStore` with the supplied
   path, never `InMemoryDecisionProposalStore`);
2. `reject` delegates to `DecisionAuthorityService.reject()` with the
   exact `proposal_id` (spy);
3. explicit `--decision-id` reaches Core verbatim (spy + real-path
   integration);
4. store and memory paths pass through verbatim (spy + integration);
5. `accept` never activates protection or invokes the Audit —
   `activate_protection`, `generate_protection_report`, and
   `check_prompt` are monkeypatched to fail-loud sentinels while a real
   accept succeeds end-to-end, and the materialized entry keeps
   `rules == []`;
6. empty `--proposals` never switches authority to an in-memory store
   (exits 2 before the service is constructed);
7. MCP inventory remains exactly the six tools, with no
   `decision.accept` / `decision.reject` (lazy import of
   `mneme.decision_mcp.APPROVED_TOOLS`);
8. `mneme/decision_mcp.py` still contains no authority import (source
   scan; unchanged from D2C1's pin);
9. `mneme/cli.py` reaches `mneme.decision_authority` only through the
   two imported names and contains no direct use of
   `transition_if_proposed`, `atomic_write_json`,
   `default_decision_id_of`, `expected_materialization_entry`, or
   `decisions_to_canonical` (updated D2C1 source test).

## Exact commands

```text
python scripts/new_task_worktree.py feat/d2c2-decision-authority-cli
python scripts/check_worktree_context.py --expected-root C:\dev\mneme\.worktrees\feat-d2c2-decision-authority-cli --expected-branch feat/d2c2-decision-authority-cli
python -m pytest tests/test_decision_authority_cli.py -q
python -m pytest tests/test_decision_authority.py tests/test_decision_proposal.py tests/test_decision_index_service.py tests/test_decision_index_consumer_reads.py tests/test_decision_mcp.py tests/test_decision_index.py tests/test_decision_projection.py -q
python -m pytest tests/test_protection_activation.py tests/test_test_policy.py -q
python scripts/run_test_battery.py gate
python -m mneme.cli check --memory .mneme/project_memory.json --input mneme/cli.py --query "feat: add decision authority CLI mneme/cli.py" --mode warn
python -m mneme.cli check --memory .mneme/project_memory.json --input scripts/run_test_battery.py --query "feat: add decision authority CLI scripts/run_test_battery.py" --mode warn
python scripts/check_encoding.py
```

## Results

| Check | Result |
|---|---|
| Focused D2C2 CLI tests (`tests/test_decision_authority_cli.py`, registered in the gate manifest) | 35 passed |
| D2C1 authority regressions (`tests/test_decision_authority.py`) | 72 passed (incl. the updated thin-CLI boundary test) |
| D2A/D2B0/D2B/D0 targeted regressions (`test_decision_proposal.py`, `test_decision_index_service.py`, `test_decision_index_consumer_reads.py`, `test_decision_mcp.py`, `test_decision_index.py`, `test_decision_projection.py`) | 200 passed |
| Protection regression (`tests/test_protection_activation.py`) + test-policy manifest check (`tests/test_test_policy.py`) | 27 + 19 passed |
| Gate battery (`scripts/run_test_battery.py gate`) | 1536 passed, 5 skipped (pre-existing, unrelated; D2C1 baseline 1501+5 + 35 new CLI tests) |
| `mneme check --mode warn` on changed governed files | PASS (warnings pre-existing, identical set to D2C1/D2C0) |
| `scripts/check_encoding.py` (mojibake + BOM) | OK (1630 files) |

## Benchmark trigger

**NOT MET.** D2C2 is adapter-only: it adds a CLI surface over unchanged
Core authority semantics and does not modify `decision_retriever.py`,
`enforcer.py`, `conflict_detector.py`, `benchmark.py`, `rule_matcher.py`,
`path_selectors.py`, Audit tier semantics, ADR-020 applicability,
protection activation, canonical projection semantics, or trusted-
evidence semantics. Retrieval/enforcement/benchmark behavior is
unchanged, so the frozen enforcement benchmark was not re-run.

## Authority matrix (D2C2)

```text
authority semantics live in Core? YES
CLI generates canonical decision IDs? NO
CLI transitions proposal lifecycle directly? NO
CLI writes project_memory authority state directly? NO
CLI performs collision logic? NO
CLI performs recovery logic? NO
CLI performs canonical verification? NO
CLI activates protection? NO
CLI assigns Audit tier? NO
MCP can accept/reject? NO
MCP inventory changed? NO
authority CLI uses durable proposal store? YES
hosted/org authority added? NO
frozen runtime semantic delta? NO
```

## Frozen-boundary attestation

- `decision_authority.py` / `decision_proposal.py` /
  `decision_proposal_store.py` / `decision_index_service.py` /
  `decision_index.py` / `decision_projection.py` / `decision_mcp.py` /
  `memory_store.py` / `protection.py` modified? NO (untouched; the only
  runtime file changed is `mneme/cli.py`)
- Core public API used exactly as D2C1 pinned it:
  `DecisionAuthorityService(proposal_store, memory_path, clock=None)` /
  `accept(proposal_id, decision_id=None)` / `reject(proposal_id)`
- MCP six-tool inventory changed? NO (regression-pinned, byte-unchanged
  module)
- Audit invoked or protection activated from the CLI flow? NO
  (monkeypatch-pinned sentinels)
- `.mneme/project_memory.json` changed? NO (test/memory changes only in
  tmp_path fixtures)
- OSS boundary: no hosted authority API, hosted MCP, RBAC, SSO,
  org/multi-user approval, multi-repo governance, remote persistence, or
  tenancy added? CONFIRMED none added

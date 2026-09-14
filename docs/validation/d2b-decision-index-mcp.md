# D2B — Decision Index MCP transport (ADR-027, issues #362/#365)

A thin local MCP capability adapter over `DecisionIndexService`
(`mneme/decision_mcp.py`). Transport only: tool registration, input
decoding/validation, explicit deterministic serialization, and
protocol-level error mapping. Every handler delegates to a public
service method; the MCP tool list is itself part of the authority
boundary. No acceptance/rejection authority, no second persistence
model, no hosted/organizational dependency, and no observable change
to any frozen runtime surface.

## Exact SHA evidence

- Exact base SHA (canonical `origin/main` after D2B0):
  `63ce383f29df247b46255b3ad36daf22eb0640c6`
- Exact tested implementation SHA:
  `219c8c95376d69f1b31228d02f40c3bd098f868d` — all test, gate, and
  self-governance figures below were executed on this exact source
  state. The next commit is documentation-only (this artifact and PR
  metadata): no runtime or test bytes differ from the implementation
  SHA.
- Branch `feat/d2b-decision-index-mcp`, worktree
  `.worktrees/feat-d2b-decision-index-mcp`, context-verified with
  `scripts/check_worktree_context.py` before work and before every
  commit.

## Exact commands

```text
python scripts/new_task_worktree.py feat/d2b-decision-index-mcp
python -m pytest tests/test_decision_mcp.py -q
python -m pytest tests/test_decision_index_service.py tests/test_decision_proposal.py tests/test_decision_index_consumer_reads.py tests/test_decision_index.py tests/test_decision_projection.py -q
python scripts/run_test_battery.py gate
python -m mneme.cli check --memory .mneme/project_memory.json --input mneme/decision_mcp.py --query "feat: add decision index mcp transport mneme/decision_mcp.py" --mode warn
python -m mneme.cli check --memory .mneme/project_memory.json --input mneme/cli.py --query "feat: add decision index mcp transport mneme/cli.py" --mode warn
python -m mneme.cli check --memory .mneme/project_memory.json --input scripts/run_test_battery.py --query "feat: add decision index mcp transport scripts/run_test_battery.py" --mode warn
python scripts/check_encoding.py
```

## Results

| Check | Result |
|---|---|
| Focused D2B tests (`tests/test_decision_mcp.py`, registered in the gate manifest) | 55 passed |
| D2A/D2B0/D0 targeted regressions (`test_decision_index_service.py`, `test_decision_proposal.py`, `test_decision_index_consumer_reads.py`, `test_decision_index.py`, `test_decision_projection.py`) | 127 passed |
| Gate battery (`scripts/run_test_battery.py gate`) | 1411 passed, 5 skipped (pre-existing, unrelated; baseline 1356+5 + 55 new) |
| `mneme check --mode warn` on changed governed files (`mneme/decision_mcp.py`, `mneme/cli.py`, `scripts/run_test_battery.py`) | 3/3 PASS |
| `scripts/check_encoding.py` (mojibake + BOM, the CI encoding job locally) | OK (1627 files) |

## MCP SDK / package / version

- Package: official `mcp` Python SDK (modelcontextprotocol/python-sdk),
  **v2 line**, pinned `mcp>=2.2.0,<3` in a new optional dependency
  group `[project.optional-dependencies] mcp = ["mcp>=2.2.0,<3"]`
  (mirrors the existing `api`/`langchain` extra convention).
- Chosen because it is the current stable official SDK; v2 is a major
  rework for the 2026-07-28 spec, and `pip install mcp` now installs 2.x.
- Official API sources checked before implementation (no guessing):
  - SDK README (github.com/modelcontextprotocol/python-sdk, `main`),
    including the v1→v2 migration note (`MCPServer` replaces v1
    `FastMCP` as the high-level surface).
  - py.sdk.modelcontextprotocol.io: Get started, Servers/Tools,
    Servers/Structured Output, Servers/Handling errors,
    Running your server (transport/`run()`), Clients/Transports.
  - Live source inspection of the installed 2.2.0 package for exact
    behaviors not stated in prose: `func_metadata` output-model rules
    (`dict` annotation → unwrapped object + published `outputSchema`;
    non-dict unions → `{"result": ...}` wrapper), `Tool.run` exception
    ordering (`MCPError` passes through unwrapped; `ToolError` becomes
    `is_error=True`; anything else → crash), `CallToolResult`
    (`structured_content: Any = None`), `Tool.name` override support,
    and `ToolAnnotations` fields.
- MCP spec tool-name rules verified (modelcontextprotocol.io
  specification 2025-11-25/2026-07-28 "Tool Names"): dots are allowed
  characters (example `admin.tools.list`), so the ADR-027 dotted tool
  names are protocol-conformant. Explicit `name=` is passed to
  `@server.tool()` because the SDK derives the wire name from the
  function name.

## Chosen transport

**stdio only** — `MCPServer.run()` with no argument (the SDK default).
Launched by `mneme decision-mcp`. No HTTP, SSE, or hosted endpoint; no
auth/RBAC/tenancy. Tests use the in-memory `Client(server)` (same
protocol layer, no transport) plus one real stdio subprocess
end-to-end test.

## Tool inventory (exact, frozen)

```text
decision.propose
decision.propose_batch
decision.get
decision.search
decision.applicable_to
decision.trace
```

Nothing else is registered. No authority tool (`decision.accept`,
`decision.reject`, `decision.activate`, `decision.deactivate`,
`decision.supersede`, `decision.create_exception`, `decision.bypass`,
`decision.submit_evidence`, `decision.submit_trusted_evidence`,
`decision.protect`) and no alias exists; the registration code fails
closed if the handler set drifts from the six-name inventory
(tests pin the exact sorted list).

## Input schema summary

- `decision.propose` — `{candidate: CandidateInput}`.
- `decision.propose_batch` — `{candidates: [CandidateInput],
  shared_provenance?: SourceProvenanceInput}`.
- `CandidateInput` (Pydantic, `extra="forbid"`): `title`, `statement`
  (both `min_length=1`), `rationale`, `provenance`,
  `scope_hints: [str]`, `architecture_context: {str: str}`,
  `related_decision_ids: [str]`. This is exactly the producer-
  controlled subset of `DecisionProposalCandidate`.
- `SourceProvenanceInput` (Pydantic, `extra="forbid"`):
  `producer_name`, `producer_type`, `source_reference` (all
  `min_length=1`), optional `external_source_id`, `source_version`,
  `repository_locator`, and `origin_classification` as a `Literal`
  enum (`ai_generated` / `human_authored` / `imported_unknown`).
- `decision.get` / `decision.trace` — `{record_id: str}` (flat args;
  unknown top-level keys are rejected by the SDK's argument model).
- `decision.search` — `{query?: str, proposal_status?:
  Literal[proposed|accepted|rejected], canonical_lifecycle_status?:
  Literal[active|superseded|deprecated|inactive], producer_name?,
  source_reference?, origin_classification?: Literal[...]}`.
- `decision.applicable_to` — `{context?: [str], paths?: [str]}`.

**Authority-field rejection**: every forbidden producer field
(`status`, `proposal_id`, `producer_key`, `content_fingerprint`,
`proposed_at`, `accepted_decision_id`, `canonical_lifecycle_status`,
`rules`, `include_paths`/`exclude_paths`, `trusted_evidence`,
`enforcement_state`, ...) is a hard validation error at the schema
layer (`extra="forbid"`), reported to the model with the field name.
The transport never accepts and silently discards an authority field.
Nested provenance is equally closed; batch `shared_provenance` uses
the same `SourceProvenanceInput` shape.

## Output serialization design

Explicit, deterministic serializers (never `dataclasses.asdict`),
plain JSON-safe dicts with stable key order and preserved list order:

- `proposal_to_transport` — proposal record with the proposal
  lifecycle under an explicit `proposal_status` key; candidate
  content + provenance losslessly; `producer_key`,
  `content_fingerprint`, `proposed_at`, `accepted_decision_id`.
- `canonical_record_to_transport` — full canonical record with
  `lifecycle_status` (canonical vocabulary) and ordered
  relationships as `[kind, target]` pairs.
- `rule_to_transport` — canonical rule with ADR-020 applicability
  verbatim (no reinterpretation).
- `declared_evidence_to_transport` — declared-only linkage; carries
  no verification/trusted field.
- `search_result_to_transport` — `proposals` and
  `canonical_decisions` as separate lists, each keeping its own
  lifecycle vocabulary key.
- `scope_hint_result_to_transport` — `proposal_hint_matches`
  (`proposal_id`, `matched_hints`) and slim
  `canonical_scope_matches` (identity/statement/lifecycle/context
  scope only): no rules, no selectors, no enforcement field.
- `proposal_trace_to_transport` / `canonical_trace_to_transport` /
  `trace_not_found_to_transport` — each carries an explicit
  `result_type` (`proposal_trace` / `canonical_trace` /
  `trace_not_found`); not-found keeps `record_id` and stays
  type-unknown (no `record_type` classification).
- `get_result_to_transport` — explicit `record_type`
  (`proposal` / `canonical_decision`); `decision.get` also returns a
  `not_found` result. The transport never guesses the record type.

## Error contract

- Malformed candidate input, unknown record (via serializers),
  invalid lifecycle filters, invalid origin classification, missing
  proposal provenance → `ToolError` (`is_error=True`; the model can
  correct input). Filter value errors pass through the service's own
  `ValueError`s, so the vocabularies stay service-owned.
- Canonical rule-lineage integrity failure
  (`DecisionIndexIntegrityError`) → fail-closed protocol error:
  re-raised as `_FailClosedProtocolError` (an `MCPError` subclass)
  with `INTERNAL_ERROR` (-32603), which the SDK passes through its
  tool wrapper unwrapped so the whole `tools/call` request fails as a
  JSON-RPC error. No successful, partial, or ambiguous trace is ever
  produced; the failure stays protocol-distinguishable from ordinary
  not-found (which is a successful `trace_not_found` result).
- Corrupt proposal stores / malformed canonical sources are
  composition failures at server construction (before serving).
- No stack traces in tool result payloads (SDK contract; the
  transport never serializes exception internals into results).

## Tool → `DecisionIndexService` mapping

| MCP tool | Service call | Semantics change by MCP |
|---|---|---|
| `decision.propose` | `propose(candidate_from_input(...))` | none (idempotency, `proposed` start, service-owned `proposed_at`) |
| `decision.propose_batch` | `propose_batch(candidates_from_input(...), shared_provenance)` | none (per-candidate identity, order preserved) |
| `decision.get` | `get(record_id)` | none (proposal/canonical/not-found distinction preserved) |
| `decision.search` | `search(...)` final D2B0 signature | none (separate domains, service-owned vocabulary validation) |
| `decision.applicable_to` | `applicable_to(context, paths)` | none (retrieval hints; paths never glob-evaluated) |
| `decision.trace` | `trace(record_id)` | none (union + fail-closed integrity preserved) |

No handler touches `_store`, `_canonical`, or `_clock`; handlers
receive only the injected `DecisionIndexService`. Composition
(`build_server` / `build_server_from_parts` / `serve_stdio`) is
transport-side DI over the existing store/index/service; no second
authoritative persistence model exists and
`.mneme/project_memory.json` is never touched. Canonical loading uses
the existing D0 adapters only
(`load_canonical_index_from_adr_dir` →
`decision_index.build_canonical_index` over
`adr_parser.parse_adr_directory` + `adr_compiler.resolve_precedence`;
same-scope precedence ties degrade the active runtime projection, not
the canonical record set, exactly as `build_canonical_index` handles
them).

## Authority / capability matrix

| Tool | Granted authority | State it can change | State it cannot change |
|---|---|---|---|
| `decision.propose` | submit one non-authoritative candidate | at most one new proposal record (`status='proposed'`) | proposal status/acceptance, canonical lifecycle, rules, evidence, enforcement |
| `decision.propose_batch` | submit N independent candidates | at most one new proposal per candidate | same as propose; no batch authority, no auto-accept |
| `decision.get` | read one record | nothing | everything (read-only) |
| `decision.search` | read/search both domains | nothing | everything (read-only) |
| `decision.applicable_to` | retrieval/context hints | nothing | everything (read-only; no rule applicability) |
| `decision.trace` | read deterministic lineage | nothing | everything (read-only; integrity fails closed) |

## Capability inventory statement

`MCP can create non-authoritative proposal? YES`  
`MCP can create canonical decision directly? NO`  
`MCP can accept/reject proposal? NO`  
`MCP can activate/supersede decision? NO`  
`MCP can create typed rule by assertion? NO`  
`MCP can reinterpret scope hint as rule applicability? NO`  
`MCP can submit trusted evidence? NO`  
`MCP can suppress canonical integrity failure? NO`  
`MCP adapter reaches private service state? NO`  
`hosted/org control plane added? NO`  
`frozen runtime semantic delta? NO`

D2C human authority remains entirely absent: no acceptance UI, no
accept/reject/activate/supersede operation anywhere in the transport,
and the `accepted`/`rejected` proposal states remain unreachable
through MCP (the service has no producer path that causes them; D2C
still owns the transition).

## Focused test coverage map (issue #362 prompt items 1-26)

1. exactly six tools exposed — `test_exactly_six_approved_tools_exposed`, `test_approved_inventory_is_the_frozen_contract`
2. forbidden authority tools absent — `test_forbidden_authority_tools_are_absent`
3. no aliases exposing authority operations — `test_no_alias_exposes_authority_operations`
4. valid propose creates proposed proposal — `test_valid_propose_creates_proposed_proposal`
5. producer cannot supply status — `test_every_forbidden_authority_field_is_structurally_rejected` (per-field assertions over `FORBIDDEN_AUTHORITY_FIELDS`)
6. producer cannot supply accepted decision id — `test_every_forbidden_authority_field_is_structurally_rejected`
7. producer cannot supply proposed timestamp — `test_every_forbidden_authority_field_is_structurally_rejected`, `test_proposed_at_is_service_owned_not_producer_callable`
8. producer cannot supply typed rules — `test_every_forbidden_authority_field_is_structurally_rejected`
9. producer cannot supply trusted evidence — `test_every_forbidden_authority_field_is_structurally_rejected`
10. identical resend idempotent — `test_identical_resend_is_idempotent_through_mcp`
11. provenance round-trips — `test_provenance_round_trips_losslessly_through_mcp`
12. batch preserves ordering — `test_batch_preserves_deterministic_candidate_result_ordering`
13. `decision.get` distinguishes proposal/canonical/not-found — `test_get_distinguishes_proposal_canonical_and_not_found`
14. search preserves separate domains — `test_search_preserves_separate_proposal_and_canonical_domains`
15. lifecycle filters remain distinct — `test_lifecycle_filters_remain_distinct_vocabularies`
16. applicable_to does not reinterpret scope hints — `test_applicable_to_does_not_reinterpret_scope_hints_as_adr020`
17. proposal trace serializes correctly — `test_proposal_trace_serializes_with_explicit_result_type`
18. canonical trace serializes actual lineage only — `test_canonical_trace_serializes_actual_lineage_only`
19. unresolved trace remains type-unknown — `test_unresolved_trace_remains_type_unknown`
20. canonical integrity mismatch fails closed at the MCP boundary — `test_canonical_integrity_mismatch_fails_closed_at_mcp_boundary`
21. handlers delegate to public service methods — `test_tool_handlers_delegate_to_public_service_methods`
22. handlers do not access `_store`/`_canonical` — `test_handlers_do_not_access_private_service_state`
23. MCP imports do not leak into domain/index modules — `test_mcp_imports_do_not_leak_into_domain_modules`
24. no HTTP/hosted/org dependency — `test_no_http_hosted_or_org_dependency_in_mcp_module`
25. server starts with the chosen local transport — `test_stdio_server_starts_and_serves_the_six_tools` (real stdio subprocess)
26. minimal end-to-end client/server smoke test invoking one read and one proposal — same `test_stdio_server_starts_and_serves_the_six_tools` (`decision.get` read + `decision.propose` write over real stdio)

Additional regressions: vocabulary mirrors stay in lockstep with the
service (`test_transport_vocabulary_mirrors_service_vocabulary`),
serialization determinism/explicitness, candidate-vs-shared provenance
precedence, batch-without-provenance fail-closed, read-only/idempotent
tool annotations, and authority-boundary wording in tool descriptions
(human inspectability).

## Benchmark trigger decision

**NOT triggered.** D2B is transport-only: it adds a new module
(`mneme/decision_mcp.py`) and CLI/entrypoint/package wiring; it does
not modify `decision_retriever.py`, `enforcer.py`,
`conflict_detector.py`, `benchmark.py`, `rule_matcher.py`,
`path_selectors.py`, audit tier semantics, ADR-020 typed-rule
applicability, canonical projection behavior, proposal
identity/idempotency semantics, or trusted evidence semantics
(attestation below). Retrieval/enforcement/benchmark semantics are
unchanged, so the enforcement benchmark rerun trigger is not met.

## Frozen-boundary attestation

- `decision_retriever.py`, `enforcer.py`, `conflict_detector.py`,
  `benchmark.py`, `rule_matcher.py`, `path_selectors.py` behaviorally
  changed? NO (untouched)
- `decision_index.py` / `decision_projection.py` / `memory_store.py` /
  `decision_proposal.py` / `decision_proposal_store.py` /
  `decision_index_service.py` modified? NO (untouched)
- ADR-020 typed-rule applicability reinterpreted by the transport? NO
  (applicability serialized verbatim; `applicable_to` returns slim
  scope references)
- Audit tier semantics changed? NO
- Proposal identity/idempotency changed? NO (pinned by regressions)
- Canonical projection behavior changed? NO (existing D0 adapters
  reused as-is)
- `.mneme/project_memory.json` changed / used as proposal storage? NO
- Benchmark fixtures changed? NO

## Dependency note

`mcp` is an **optional** extra (`pip install 'mneme-hq[mcp]'`); the
core package dependencies are unchanged, and `mneme decision-mcp`
fails with an actionable install message when the extra is absent.
Gate battery remains green without any new mandatory dependency.

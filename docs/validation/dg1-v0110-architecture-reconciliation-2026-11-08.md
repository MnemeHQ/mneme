# DG1 at v0.11.0: architecture reconciliation (2026-11-08)

> Read-only audit of the DG1 decision-governance programme against
> [ADR-031](../adr/ADR-031-decision-governance-semantics.md) at the `v0.11.0`
> tag (`619d5405`). It reconciles the accepted contract with the shipped code,
> tests and runtime surfaces, records gaps and blockers, and names the smallest
> justified next engineering milestone. It changes no code, test, fixture,
> benchmark, ADR or Layer 1 freeze state, and authorizes nothing.
> Programme tracker: [#497](https://github.com/MnemeHQ/mneme/issues/497).

## 0. Summary

- **Contract delivered as library semantics.** DG1A, C, E, D, P and B1 are
  implemented and tested (217 DG1 tests pass at `619d5405`). The v2 evolution
  contract (§8, §8a) is enforced by the loader.
- **No runtime consumer converges yet.** `resolve_effective` has exactly one
  caller, the report-only `mneme check --applicability-preview` (DG1F-C1a).
  Every verdict-producing surface still derives "governs" from load-time
  projection plus independent `status == "active"` checks.
- **Three concrete runtime divergences exist today** (§4): legacy section-less
  memory enforces superseded decisions that Audit excludes; applicability and
  integrity findings are visible only in the preview; and the trusted CI gate
  evaluates with a pre-0.11.0 evaluator.
- **C1b (enforcement-changing applicability) stays blocked.** CI has a trusted
  memory source (base-revision blob, `.mneme/` refusal). The host has none, and
  the T-08 D6 C4 record shows uncommitted local settings can redirect the hook
  to another repository's memory and produce a complete false PASS. No
  persisted context declaration exists, and the resolver cannot express
  "context not supplied" (§5).
- **DG1B2 stays blocked:** no verified, decision-version-bound waiver case.
- **Next candidate (§8): DG1F-C2, lifecycle-only convergence.** One shared
  lifecycle authority used by projection, the resolver and the runtime
  consumers, a three-state governance context, and golden-output parity tests.
  It introduces no authoritative labels or waivers. It **requires** a
  behavioral charter and a `[layer1-freeze]` amendment: the DG1B1 and C1a
  freeze amendments prohibit any protection, Audit or readiness surface from
  consuming the resolver, whatever the parity result (§10).
- **ADR-031 needs a doc-only erratum** for `precedence_lost` (G-4): its text
  says the first v2 slice provides it, and DG1B1 did not.
- **An independent review** (§10) checked four questions on C2 and corrected
  this record before publication.

## 1. Scope and method

Sources read: ADR-031 (incl. §8a and the §11 sequencing amendment), tracker
#497, the DG1B1 and DG1F-C1a charters, the Layer 1 freeze doc, the DG1F
readiness and consumer trust-boundary plans, the ADR-033 C4 records, the CI1
and CI R0 records, and the T-08 D6 C4 record. Code read at `619d5405`:
`mneme/decision_governance.py`, `decision_index_persistence.py`,
`memory_store.py`, `decision_projection.py`, `enforcer.py`, `protection.py`,
`readiness.py`, `evidence.py`, `decision_mcp.py`, `decision_index_service.py`,
`decision_retriever.py`, `conflict_detector.py`,
`integrations/claude_code/hook.py`, `cli.py`, `.github/workflows/` and
`scripts/ci/adr033_c4_gate.py`.

Verification performed:

- `pytest tests/test_dg1*.py` at `619d5405`: **217 passed**.
- One live probe of divergence D-1 (§4) against the working tree.
- Spot checks of every file:line cited in §4 and §5.

"C4" is overloaded in this repository. This report covers both meanings:
**ADR-033 C4** (CI availability policy, memory read from the trusted base) and
**T-08 D6 C4** (host memory selection through uncommitted
`.claude/settings.local.json`). Both bear on the trusted-source requirement.

## 2. Contract reconciliation (ADR-031 → code → tests)

| ADR-031 requirement | Implementation at v0.11.0 | Tests | Status |
|---|---|---|---|
| §1 one deterministic resolver; no dependence on retrieval, order, clock | `resolve_effective` (`decision_governance.py:224`); sorted by id, no clock | dg1c `test_input_order_invariance`, `test_resolver_is_pure_over_frozen_records`, dg1b1 `test_applicability_does_not_consult_retrieval_or_timing` | **Met** |
| §1 ambiguity returned, never a guessed winner | `STATUS_AMBIGUOUS` defined, never emitted; precedence ambiguity fails closed at import (`ADRPrecedenceError`) and is never persisted | dg1p `test_newer_date_never_wins_a_same_priority_tie`, `test_partial_resolution_skips_only_the_tied_scope` | **Met** (ambiguity lives at import, by design) |
| §2 date is not authority | DG1P: `_pick_within_scope` has no date step | 8 dg1p tests incl. re-import non-deactivation and MCP `--adr-dir` refusal | **Met** |
| §2 persist precedence **reason** so the resolver can explain a loss | Not implemented. Trace emits `precedence: not_recorded` (`decision_governance.py:266`) | none | **Gap G-4** (unscheduled, §6) |
| §3 four lifecycle states; causes in trace | `lifecycle_superseded/deprecated/inactive`, `not_applicable` | dg1c `test_ineffective_causes_follow_lifecycle_and_never_guess` | **Met** |
| §3 `precedence_lost` cause, "first v2 slice" | Absent. DG1B1 was the first v2 slice and, per §8 "only that slice's fields", did not add it | none | **Contract inconsistency G-4** |
| §3 `waived` cause | Absent (DG1B2 not started) | none | **Blocked** (B2) |
| §4 three applicability layers stay separate | `context_scope` never becomes decision applicability; decision applicability never becomes rule applicability | dg1b1 `test_scope_and_source_text_never_become_applicability`, `test_decision_applicability_never_becomes_rule_applicability` | **Met** |
| §4 absent applicability = globally eligible | Yes | dg1b1 `test_v2_absent_applicability_is_globally_eligible`, F1 | **Met** |
| §5 terminology ("effective", never "applicable" for governance) | Followed in resolver/CLI preview; MCP `decision.applicable_to` unchanged (ADR-027) | n/a | **Met** |
| §6 GovernanceContext: ADR-020 paths, explicit `as_of`, opaque labels | `GovernanceContext` (`:93`); paths via `validate_relative_path`; `as_of` validated, unused | dg1c context tests | **Met**, with **gap G-5**: no way to express "labels not supplied" (§5) |
| §7 parity with load-time projection over v1 | Yes, plus findings for malformed-but-accepted state | dg1c parity ×3 (ADR corpora, canonical, migrated) + persisted-v1 characterization | **Met** |
| §7 charter before any enforcement-input change | Respected: DG1B1 and C1a each had charter + freeze amendment; projection ignores applicability | dg1b1 `test_projection_ignores_applicability_so_enforcement_inputs_are_unchanged`, F12 | **Met** |
| §8 v2 only via explicit migration; closed key sets; `semantic_features`; no speculative fields | `mneme decision-index migrate --to-v2`; `_V2_*_KEYS`; `SUPPORTED_SEMANTIC_FEATURES = {decision_applicability, numeric_upper_bound_rule}` | dg1b1 v2 rejection tests (root/decision/version/rule/applicability/feature) | **Met** |
| §8a `extensions` key grammar, syntactic-only validation | `_EXTENSION_SEGMENT_RE`, `mneme` root reserved | dg1b1 `test_v2_extensions_*` (5) | **Met** (loader enforcement shipped after the doc-only amendment) |
| §9 snapshot-based change; no history | `resolve_change`, `compare_resolutions`; refuses section-less snapshots and cross-context/cross-semantics comparisons | 14 dg1d + dg1b1 governed-scope change | **Met** |
| §10 one `rule_id` algorithm everywhere incl. `--adr-dir` | `mneme/rule_identity.py`; D0 adapter emits §7 ids | dg1e `test_runtime_rule_id_equals_persisted_rule_id`, `test_adr_dir_view_uses_canonical_rule_ids_without_version_identity` | **Met** |
| §10 `--adr-dir` and section-less memory fail evidence identity | `evidence_identity_of` fails closed without `dver-` version id | dg1e `test_section_less_memory_has_rule_identity_but_fails_closed` | **Met** |
| §11 DG1F replaces duplicated `active` checks (projection, protection candidates + precheck, Audit, readiness) with the shared resolver | **Not started**. Projection (`decision_projection.py:52`) is the filter that actually governs canonical memory. Runtime checks: `enforcer.py:1335` in the shared `_build_report` aggregator (used by `mneme audit`, readiness, protection `find_candidates` and `github_evidence.py:439`), `protection.py:212` (precheck), `evidence.py:241` (not in the ADR list), plus a redundant re-check at `protection.py:170` | none | **Open (DG1F)** |
| §12 waiver semantics | Fixed in ADR; no code | none | **Blocked (DG1B2)** |
| §13 DG1G fixture floor | See §7 | | **Mostly pinned; 2 items unmapped** |

## 3. What v0.11.0 ships, by slice

| Slice | Delivered | Evidence |
|---|---|---|
| DG1A | ADR-031 accepted; v1 compatibility characterization | #466; 9 tests |
| DG1C | `resolve_effective`, findings `supersession_lifecycle_conflict`, `dangling_supersedes` | #468; 52 tests |
| DG1E | single §7 `rule_id`; `decision_version_id` through `RuleEvaluation`/`Violation`/`check --json`; `evidence_identity_of` | #469; 32 tests |
| DG1D | `resolve_change`, `DecisionChangeSet` | #469; 14 tests |
| DG1P | date removed from precedence | #470; 8 tests |
| DG1B1 | v2 schema, `decision_applicability` feature, `set_decision_applicability` (library only, no CLI writer), label containment in resolver | #487; 62 + 13 functional-acceptance tests; [acceptance record](dg1b1-functional-acceptance.md) |
| DG1F-C1a | `mneme check --applicability-preview LABEL`, stderr-only, non-authoritative, same snapshot as enforcement | #492–#495; 25 tests |
| DG1F G4 | corrupt/malformed memory is an operational error, never PASS | 2 tests |

Resolver semantics id at v0.11.0: `mneme.governance-semantics/dg1b1-1`;
change semantics id: `mneme.governance-change/dg1d-1`.

## 4. Runtime convergence map

All verdict-producing surfaces load decisions through `MemoryStore.load()`
(`memory_store.py:124`). With a `decision_index` section, that is
`load_persisted_decision_index` → `verify_compatibility_snapshot` →
`project_canonical_index`, which keeps only `active` records
(`decision_projection.py:52`) and ignores applicability. Without a section,
`runtime_decision_from_memory_record` copies `status` and **filters nothing**
(`decision_index_persistence.py:328`).

| Surface | Decision source | "Governs" test | Applicability | Evidence identity |
|---|---|---|---|---|
| `mneme check` (text, `--json`, warn/strict) | MemoryStore → `DecisionRetriever(store.decisions())` | projection only; no status check in `check_prompt` / `_enforcement_scope` (`enforcer.py:287`) | preview only (stderr) | `rule_id` + `decision_version_id` (empty for legacy) |
| Claude Code hooks (PreToolUse, shell preflight, SessionStart, Stop) | `find_memory(cwd)` (`hook.py:202`): `$MNEME_MEMORY` or upward walk; then `check --json` | same as `check` | none | same as `check` |
| CI warn self-check (`mneme-check.yml`) | PR checkout memory | same as `check` | none | parses text `Result:` only |
| CI trusted gate (`mneme-trusted-gate.yml`, required on `main` per [R0 S7](ci-r0-s7-closure-2026-11-03.md)) | base-commit memory blob (`adr033_c4_gate.py:255`); evaluator pinned to `0b74d410` (= `v0.10.0-61`) | same as `check`, older code | none | drops `decision_version_id` (`adr033_c4_gate.py:347-355`) |
| Audit | MemoryStore | `r.status == "active"` (`enforcer.py:1335`) | none | `decision_id` |
| Protection | MemoryStore | `!= "active"` at `protection.py:170` (candidates) and `:212` (precheck) | none | `decision_id` |
| Readiness | via `generate_protection_report` | inherits `enforcer.py:1335` | none | counts |
| Evidence | caller-supplied list, in practice the Audit corpus; its filter feeds Audit tiers (`enforcer.py:1314`) | `!= "active"` (`evidence.py:241`) | none | `decision_id` + selector |
| Decision MCP (memory mode) | `load_decision_index_from_memory_file` per read | `decision.applicable_to` has **no lifecycle filter** (`decision_index_service.py:521-528`); ADR-027 retrieval semantics | labels never exposed | canonical ids |
| DecisionRetriever / ConflictDetector | whatever list they receive | none | none | ConflictDetector carries ids |

### Divergences (two surfaces can disagree about which decisions govern one change)

- **D-1. Legacy section-less memory enforces superseded/deprecated decisions;
  Audit, protection, readiness and evidence exclude them.** Verified live: a
  section-less memory with one `status: "superseded"` decision carrying
  `FORBID_LITERAL "psycopg2"` makes `mneme check --mode strict` exit 2 (FAIL),
  identical to `status: "active"`. `resolve_effective` refuses section-less
  memory entirely. Direction: over-enforcement (fail-safe), but the governed
  set is inconsistent across surfaces. This is the "exact old semantics"
  legacy path; changing it changes enforcement inputs and needs a charter.
- **D-2. Applicability-scoped v2 decisions.** Enforcement treats them as
  global; the preview reports `not_applicable` for the same change. Intended
  until C1b, and the safe direction.
- **D-3. Integrity findings.** `supersession_lifecycle_conflict` and
  `dangling_supersedes` make the preview UNAVAILABLE (`cli.py:518`) while
  enforcement applies the decision silently. Whether findings should block is
  explicitly a DG1F decision (resolver docstring) and remains undecided.
- **D-4. Trusted CI gate runs pre-0.11.0 code.** Its evaluator supports only
  `{decision_applicability}` (verified at `0b74d410`), so v2 memory declaring
  `numeric_upper_bound_rule` is accepted by 0.11.0 hooks and refused by the
  required gate (UNEVALUATED → fails under posture `closed`). The workflow
  header comment still says "S3 is shadow only", which is stale relative to the
  S7 record. Ownership: CI R0 / CI1, not DG1.
- **D-5. Retrieval shapes part of the checked rule set, per surface.** Under
  ADR-017's two tiers, only the retrieval-gated top-N gets multi-term rules
  (`enforcer.py:305-314`), and each surface builds a different query (hook:
  `"edit to <rel>"`; warn CI: PR title + path; trusted gate: a constant).
  Literal rules are corpus-wide and unaffected. This is ADR-017 by design, but
  it means "the decision set that governs this change" is query-dependent for
  multi-term rules. Input to workstream 3 (DecisionRetriever), not DG1F.
- **D-6. MCP `decision.applicable_to` returns superseded/deprecated/inactive
  records** whose scope matches. Consistent with ADR-027 (retrieval
  relevance); the lifecycle is in the payload. A consumer reading it as
  "governs" would be wrong. Low severity; no change proposed here.

## 5. Trusted applicability: C4 memory-source findings vs C1b requirements

### 5.1 What C1b must establish (charter #493 §3, freeze #494, ADR-031 §11)

(a) an independently verifiable approved revision of the memory actually used;
(b) protection against unreviewed substitution between review and execution;
(c) controlled context selection from a **persisted canonical context
declaration**; plus the four-branch fail-safe (no declaration → enforce all;
valid declaration → exclude only on a positively established trusted absence;
invalid/conflicting → do not exclude, surface it; unreadable memory →
operational failure, coverage unknown) and the blocking seam. Caller argv,
env, hook/MCP input and paths are never authoritative label sources.

### 5.2 What exists

| Requirement | CI (ADR-033 C4 adapter) | Host (Claude Code hook) |
|---|---|---|
| (a) approved revision of the memory used | **Yes**: memory read as a blob from the base SHA (`adr033_c4_gate.py:255`), recorded as `{path, blob, source_commit, sha256}` (`:542-549`); AC5 met. Bounded by P7/P8 administrative trust | **No**: `find_memory` uses `$MNEME_MEMORY` or an upward walk with no revision check |
| (b) anti-substitution | **Yes**: any `.mneme/` change is a policy refusal under both postures (O8, O8s, A1); CI1 live V2/V3/V3a refused | **No**: T-08 D6 C4 finding A: an uncommitted `.claude/settings.local.json` `env.MNEME_MEMORY` redirected enforcement to another repository's memory and produced a complete **false PASS** (`LOCAL_PRESESSION_PROPAGATED`). Finding B: the host, not Mneme, denied the agent's write in the tested mode. No agent-controlled bypass shown |
| (c) persisted context declaration + selection | **No** | **No** |
| absent/malformed memory fail-safe | **Yes**: O4/O5 → UNEVALUATED, never PASS | **Partly**: G4 makes corrupt memory an operational error; missing memory selection is host-dependent (T-08) |
| resolver distinguishes "context not supplied" from "labels absent" | **No** (both) | **No** |

### 5.3 Reconciliation without another resolver

- **Governance resolution stays single.** `resolve_effective` remains the only
  governance resolver. C1b adds an input (a trusted context declaration read
  from the same snapshot), not a second resolver.
- **Memory-source selection stays where it is.** In CI, the C4 adapter's
  base-blob read is the trusted source; a C1b CI increment must read the
  context declaration from that same blob (C1a already pins "same snapshot as
  enforcement, not a second file read"). On the host, any future verification
  should reuse the existing `availability_authority.py` remote-tip pattern
  (C2b), not a new resolver.
- **Consequence:** the only place C1b prerequisites (a) and (b) are currently
  satisfiable is the CI trusted gate. A host C1b would require a trusted
  memory-source mechanism that does not exist; until then the host must never
  exclude.
- **Gap G-5 (resolver).** `GovernanceContext(labels=())` means both "no labels
  apply" and "context unknown". A context-free consumer that calls the
  resolver today would silently drop every applicability-scoped decision,
  which is exactly what ADR-031 §11 forbids an adapter to do. Any consumer
  convergence must not route through label-based effectiveness until this is
  resolved.

## 6. Remaining gaps

| ID | Gap | Owner | Blocking? |
|---|---|---|---|
| G-1 | No runtime consumer uses the resolver; the lifecycle rule exists in projection, the resolver and three runtime checks (§2, §4). On canonical memory the runtime checks never fire (projection already removed non-active decisions); they act only on section-less memory, which the resolver refuses | DG1F | Blocks DG1G closeout |
| G-2 | D-1 legacy superseded enforcement vs Audit exclusion | DG1F (charter, since it changes enforcement inputs) | No (fail-safe direction) |
| G-3 | D-3: no decision on whether integrity findings block | DG1F charter | No |
| G-4 | §2 (line 181) requires a persisted precedence reason; §3 (line 198) and the Negative consequences (line 590) assign it to the "first v2 slice"; §8 limits v2 to "only that slice's fields"; §11 names DG1B1 as that slice, and DG1B1 did not add it. Nothing defers it (DG1B1 charter, freeze amendments, #497). Line 590 is now false | Doc-only ADR-031 erratum now: restate as "a future evidence-gated v2 semantic feature under the §8 evolution rule"; add an unchecked item to #497 | No (§13 floor does not require it); the contract text is wrong today |
| G-5 | Resolver cannot represent "context not supplied" | DG1F (prerequisite for C2 and C1b) | Yes, for any consumer convergence via the resolver |
| G-6 | No persisted canonical context declaration; no CLI writer for applicability | DG1F-C1b | Yes, for C1b |
| G-7 | Host memory source untrusted (T-08 D6 C4 finding A) | T-08 / D6 decision, then C1b | Yes, for host C1b |
| G-8 | Trusted gate evaluator pinned pre-0.11.0 (D-4); stale workflow comment | CI R0 / CI1 | No for DG1; yes for numeric v2 memory in CI |
| G-9 | No verified waiver case | DG1B2 (Data Engine #36 handoff) | Yes, for B2 |
| G-10 | Doc drift: `decision_governance.py` docstring (lines 11-12, 44-47) still says no semantic depends on labels; roadmap README omits C1a, #492 and the C4/R0 trust results | docs maintenance | No |
| G-11 | #497 governance-of-governance controls: self-authorization negative control is covered in CI (CI1 V2/V3, C4 O8) but not on the host (G-7); authorized-transition positive control untested | DG1G with CI1 | Blocks DG1G closeout |

## 7. DG1G fixture floor (ADR-031 §13)

| Fixture | Pinned by |
|---|---|
| 0.10.0 parity | dg1c parity ×3 |
| different-scope co-governance; broader/narrower coexistence | `tests/test_adr_precedence.py`, `tests/test_adr_constraints.py` (pre-DG1; needs DG1G mapping) |
| same-scope priority; same-scope ambiguity, no date | dg1p |
| supersession; honest `lifecycle_inactive` | dg1c |
| input-order; irrelevant-decision; context-path invariance | dg1c, dg1b1 |
| canonical rule identity through enforcement | dg1e |
| section-less fail-closed evidence | dg1e |
| configured vs execution-observed evidence (ADR-029 §6) | **not pinned under DG1**; ADR-034 harness has observed-disposition tests, C4 records the distinction. Needs a DG1G fixture |
| snapshot A → B explanations | dg1d |
| applicability | dg1b1, functional acceptance F1–F12 |
| waiver incl. `as_of` expiry, out-of-scope | n/a until DG1B2 |

## 8. Next candidate milestone

**DG1F-C2: lifecycle-only runtime convergence** (candidate; not authorized).

What it should and should not change, after review (§10):

1. **One lifecycle authority.** Define the "lifecycle-eligible" rule once and
   use it in projection (`decision_projection.py:52`), the resolver
   (`decision_governance.py:83`) and the runtime checks (`enforcer.py:1335`,
   `protection.py:212`, `evidence.py:241`; drop the redundant
   `protection.py:170`). Projection is in ADR-031 §11's list and must be
   converged, not used as the oracle.
2. **Three-state governance context** (G-5): not supplied / supplied with no
   labels / supplied with labels. Context-free consumers get lifecycle-only
   results, so no applicability-scoped decision is ever dropped. The resolver
   semantics id bumps; `resolve_change` refuses to compare across semantics
   versions (`decision_governance.py:531-534`), and the charter must say so.
3. **Findings never drop or fail.** Integrity findings are reported, never
   used to exclude a decision or turn a consumer into an error (unlike the
   preview's rule at `cli.py:518`). Resolver `ValueError` is never caught and
   turned into "no decisions".
4. **Section-less memory keeps its own status semantics** as a documented
   exception (D-1 preserved), unless a separate decision chooses an in-memory
   canonical view, which touches ADR-031 §8 and ADR-030's no-implicit-migration
   rule.
5. **Golden-output and negative tests** for every row of the §10 Q3 table:
   Audit text and JSON, `protect list`, `protect validate`, readiness counts,
   `match_ci_evidence` and the `github_evidence` `_build_report` path; the
   evidence selector-ambiguity case; superseded-canonical precheck "not found";
   the legacy precheck message; applicability-not-dropped; findings-not-blocking.

**Authorization.** C2 requires a behavioral charter **and** a
`[layer1-freeze]` amendment. The DG1B1 amendment
(`layer1-freeze-e73ff7d.md:388-391`) forbids any protection, Audit or readiness
surface from consuming the resolver, and the C1a amendment (`:491-493`) keeps
that prohibition for every runtime consumer except the preview. Parity does not
remove that requirement. ADR-031 §7/§11 and tracker #497 also require each
consumer to be individually chartered.

**What C2 buys.** On canonical memory, the runtime checks never fire today,
so C2 changes nothing observable there; its value is structural: one lifecycle
authority, a resolver safe for context-free use (a prerequisite for C1b), and
the divergences pinned by tests. It does not fix D-1.

**Not justified now:**

- **C1b**: no concrete case needs enforcement-time exclusion (over-enforcement
  is the safe default), the context declaration does not exist (G-6), and the
  host has no trusted memory source (G-7). When a case appears, the first C1b
  increment should be CI-only on the trusted gate, reading the declaration from
  the base blob.
- **DG1B2**: no verified waiver case (G-9).
- **Changing D-1 legacy behavior**: fail-safe today; revisit with the legacy
  memory deprecation, under its own charter.
- **D-4**: belongs to CI R0 (evaluator re-pin), outside DG1.

## 9. Non-claims

This record does not claim DG1 completion, does not change any verdict, and
does not approve DG1F-C2, C1b, DG1B2, the ADR-031 erratum or any Layer 1
amendment. Test results are from local runs on Windows at `619d5405`, not CI.
Divergence D-1 was probed by the author and again by the reviewer; D-4 is
derived from reading the pinned evaluator source, not a run. Host findings are
those of the T-08 D6 C4 record (n = 1, one host configuration).

## 10. Independent review (2026-11-08)

A separate agent with no access to the author's reasoning reviewed a draft of
this record read-only against the code, ADR-031, the C1a charter and the
freeze doc. It re-ran the DG1 tests (217 passed) and wrote throwaway probes
(v2 applicability, supersession conflict, dangling `supersedes`, legacy
superseded/deprecated decisions, shared evidence selectors). Its verdicts:

| Question | Verdict | Basis |
|---|---|---|
| Q1. Can C2 reuse the resolver without a second source of lifecycle authority? | **No, as first drafted** | Projection (`decision_projection.py:52`, `:257`) and the resolver already hold separate copies of the rule, kept equal only by dg1c parity tests. Consumers receive `list[Decision]`, not the index; on section-less memory status comes from the file (`decision_index_persistence.py:331`) and the resolver refuses it. A single authority needs one shared predicate used by projection, resolver and runtime checks, plus a ruling on section-less memory (§8 items 1 and 4) |
| Q2. Does context-free resolution preserve all protective decisions? | **Conditional** | Probe: v2 decision requiring label `windows` is `not_applicable` under `labels=()` while projection, Audit and strict `check` still apply it. Lifecycle-only output keeps it; supersession-conflict and dangling-`supersedes` cases keep the effective set. Requires the three-state context and findings-never-drop (§8 items 2-3). Not probed: whether the loader already rejects every state `_validate` rejects |
| Q3. Is every consumer migration behavior-preserving? | **Conditional, and a freeze amendment is required regardless** | No observable change on canonical memory (checks never fire). Changes would appear if label-based output or fail-closed findings were used, and on legacy memory (e.g. a superseded legacy decision sharing a test selector makes evidence ambiguous and moves the active decision's tier). Precheck on a superseded canonical decision reports "not found" today. Freeze lines 388-391 and 491-493 prohibit resolver consumption by these surfaces |
| Q4. Does `precedence_lost` need a separate contract correction? | **Yes, a minimal doc-only erratum** | ADR-031 lines 181, 198, 275, 469, 590 contradict each other given DG1B1; nothing defers it. Not a C2 blocker (G-4) |

Corrections applied from the review: freeze amendment stated as required (§0,
§8); projection added and evidence marked as outside ADR-031 §11's list (§2);
`enforcer.py:1335` identified as the shared `_build_report` aggregator, with
`protection.py:170` as redundant (§2, G-1); C2 step "on the canonical path"
replaced, since it changes nothing observable there (§8); evidence coupling to
Audit tiers (§4); semantics-version comparability note (§8); G-4 moved from
"at DG1G" to an erratum now.

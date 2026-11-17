# AgentInspect interoperability: fidelity and reviewer-utility test charter

**Date:** 2026-11-17
**Status:** **PROPOSED** for owner review. Documentation only. This document
changes no runtime behavior, schema, adapter, test, ADR, Layer 1 freeze,
`.mneme/` content or evidence record. Acceptance authorizes **only the
section 11 step 2 PR** (harness, fixture and deterministic run, section 10,
O1). The reviewer study and any message to AgentInspect maintainers each need
a separate owner go-ahead.
**Anchors (read-only):**
- `MnemeHQ/mneme` `main` @ `0fc1f1bc` (#812);
- `rajudandigam/agent-inspect` tag `agent-inspect@6.31.36` = `f51ca992`
  (2026-11-15). Files were read only; no AgentInspect code was run.

**Closes toward:** roadmap intake [#813](https://github.com/MnemeHQ/mneme/issues/813)
(discovery steps 1-3, and step 4 as a gated follow-on).
**Builds on:**
- [ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md) evidence
  binding, [ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md)
  §7 rule identity, [ADR-031](../adr/ADR-031-decision-governance-semantics.md)
  §10 identity threading, [ADR-034](../adr/ADR-034-static-numeric-upper-bound-typed-rule.md)
  §4 `evaluation_complete`;
- production governance trace [#282](https://github.com/MnemeHQ/mneme/issues/282)
  (target trace shape: attempt, verdict, compliant retry);
- decision-linked telemetry intake [#691](https://github.com/MnemeHQ/mneme/issues/691)
  (fixture classes and A/B baseline rule);
- AgentInspect [#112](https://github.com/rajudandigam/agent-inspect/issues/112)
  (closed) and [#113](https://github.com/rajudandigam/agent-inspect/issues/113)
  (closed, shipped).

**Excluded:**
- any change to `mneme/` (Core schema, `mneme.check/v1`, adapters, hooks);
- a Mneme runtime dependency on AgentInspect, or the reverse;
- an upstream AgentInspect recipe or PR (section 9, step 5 of #813);
- live-model agent runs (scripted trajectories only, section 6);
- OTLP / Phoenix export (#691 track 2);
- CI1, Semantic Engine, AgentRuntime/ContextOS and Data Engine V5.1D/E work.

## 1. Question

> **Can a host adapter attach Mneme's actual `mneme check` result to an
> AgentInspect trace, using AgentInspect's shipped `architecturalIntent`
> v0.2 convention, without inventing, dropping or overstating anything (rule
> identity, coverage, action taken, actual mutation)? And, with fidelity
> established, does a reviewer answer governance questions about a run more
> accurately or faster than with the trace plus the fixture's existing tests?**

The first half is mechanical and is decided by the section 7 labels. The
second half is the #813 utility hypothesis. Section 8 states its design, but
it does not run under this charter's acceptance.

## 2. What changed since the #813 intake

#813 records a "contract problem, to resolve before a recipe". Both sides
have moved since #112 was filed, and this charter starts from the current
state rather than the v0.1 proposal:

| #813 concern | State at the anchors |
|---|---|
| No stable per-rule IDs | Typed rules (`FORBID_LITERAL`, `FORBID_NUMERIC_ABOVE`) carry the ADR-030 §7 `rule_id` (`mneme/rule_identity.py`, `rule_id_of`). Plain-text constraints and anti-patterns still have none. |
| No impact severity | Unchanged: `Severity` is `PASS`/`WARN`/`FAIL` (`mneme/enforcer.py:50`). AgentInspect v0.2 makes `severity` optional. |
| `WARN` vs action | AgentInspect v0.2 says `action` "may be adapter-assigned". |
| PASS is not full coverage | v0.2 defines `pass` as no violation among "checks actually evaluated". Mneme emits per-rule `applicability` and `evaluation_complete` for typed rules. |
| Reported vs observed outcome | #113 shipped as `observeOutcome()` / `outcome_observed`, with `check --fail-on-observation failed`. |
| Metadata contract | v0.2 (`docs/INTEROP-ARCHITECTURAL-INTENT.md`) is provider-neutral, with no Mneme dependency, and replaces the #112 draft. |

So the open question is fidelity, not negotiation. The gaps that remain are
listed in section 4.3 and become the agenda for maintainers if the result is
go.

## 3. Source facts (verified at the anchors)

Mneme (`0fc1f1bc`):
- `mneme check --json` emits `schema: "mneme.check/v1"` (`mneme/cli.py:374`)
  with these keys: `verdict`, `mode`, `evaluation_complete`, `applicability[]`,
  `violations[]`, `freshness[]`, and optional `subject` (`_check_payload`,
  `mneme/cli.py:377`).
- `applicability[]` holds one record per **typed** rule, with `decision_id`,
  `rule_type`, `rule_value`, `rule_index`, `outcome`
  (`APPLIED`/`EXCLUDED`/`UNKNOWN`), `rule_id` and `decision_version_id`
  (`mneme/cli.py:421`). For `FORBID_NUMERIC_ABOVE` it adds `matcher_status`
  and `matcher_outcome`.
- `rule_id` and `decision_version_id` are present **only when the decision
  came from the persisted Decision Index** (`mneme/path_selectors.py`,
  `RuleEvaluation` docstring). `rule_index` and `rule_value` are display
  fields, "never evidence identity".
- `violations[]` carries `decision_id`, `severity` (the verdict level),
  `rule`, `trigger`, `kind`, `rule_type`, `rule_id` and `decision_version_id`
  (`mneme/cli.py:446`). Plain-text (legacy) violations have no `rule_id`.
- `evaluation_complete` is false on a path `UNKNOWN` or on an applied rule
  whose matcher is `PARTIAL`/`MATCHER_UNEVALUATED` (`mneme/enforcer.py`,
  `EnforcementResult.evaluation_complete`).
- Plain-text rules that were retrieved and found clean are **not
  enumerated** anywhere in the payload.
- Exit codes depend on mode (`_EXIT_CODES_BY_MODE`). The verdict, not the exit
  code, is authoritative.

AgentInspect (`f51ca992`):
- Traces are JSONL, one event per line, `schemaVersion` `"0.1"` (manual) or
  v1.0. `run_started.metadata` and `step_started.metadata` accept arbitrary
  records (`docs/SCHEMA.md` §3.1, §3.3, §6).
- Metadata is bounded on write (`packages/core/src/trace-event-safety.ts`):
  - strings are cut at 2000 characters (500 share, 200 strict);
  - arrays are cut at 50 items;
  - events over 64 KiB have their metadata replaced by a truncation marker.
- Redaction matches key names at any depth, ignoring case
  (`packages/core/src/redaction-profiles.ts`). The share profile (the default
  for `bundle`) adds `decisionId`, `traceId`, `spanId` and others. The strict
  profile adds `input`, `output`, `context` and others.
- `architecturalIntent` v0.2 is a convention, not schema: core does not
  validate it. TraceContract JSON rules cannot assert on it; a programmatic
  `TraceCheckRule` can.
- A non-TypeScript producer can write `<runId>.jsonl` directly, or import with
  `--format agent-inspect-jsonl|openinference-json|otlp-json`.

Not yet verified by running (the section 7 checks settle these):
- whether `decisionIds` (plural) survives the share profile;
- whether strict-profile `input` matching hits keys such as `input_kind`;
- how Markdown/HTML exports render nested metadata.

## 4. Interoperability profile under test

### 4.1 Where it lives

The profile is emitted **only by the test harness adapter** (section 6), never
by Mneme Core. It is versioned as `mneme-agentinspect-profile/0.1` inside this
experiment. Adopting it anywhere else is a separate decision.

Attachment points:
- **one step per governed write**. Its `step_started.metadata` carries
  `architecturalIntent` (v0.2) and a sibling `mneme` block (4.2), and the step
  is followed by `outcome_observed`;
- **`run_started.metadata`** carries the pins: Mneme version and commit,
  fixture commit, profile version and mode.

The `mneme` block is a sibling of `architecturalIntent`, not nested inside it,
so the upstream namespace is not squatted.

### 4.2 Field mapping

| v0.2 field | Source in `mneme.check/v1` | Rule |
|---|---|---|
| `source` | constant `"mneme"` | |
| `schemaVersion` | constant `"0.2"` | |
| `decisionIds` | `decision_id` of `applicability` records with outcome `APPLIED` or `UNKNOWN`, plus every `violations[].decision_id` | `EXCLUDED`-only decisions are left out |
| `evaluations[]`, typed rule | one per `applicability` record with outcome `APPLIED` or `UNKNOWN` | |
| `evaluations[]`, plain-text rule | one **per decision**, and only for a decision with a plain-text violation | No `pass` entry is ever emitted for plain-text rules, because Mneme does not enumerate them |
| `evaluations[].decisionId` | `decision_id` | Subject to share redaction (section 7, F4) |
| `evaluations[].ruleId` | `rule_id` | Omitted when empty. Never derived from `rule_index`, `rule_value` or a hash computed by the harness |
| `evaluations[].verdict` | a matching violation → `fail`; `APPLIED` with no violation and a complete matcher → `pass`; `UNKNOWN`, `PARTIAL` or `MATCHER_UNEVALUATED` → `not_evaluated` | Mneme `WARN` and `FAIL` both map to `fail` |
| `evaluations[].mode` | `mode`: `strict` → `enforce`, `warn` → `observe` | |
| `evaluations[].action` | **what the harness actually did**: refused the write → `block`; let it through with a warning → `warn`; let it through silently → `none` | Never derived from `verdict` or the exit code |
| `evaluations[].severity` | none | Always omitted |

`mneme` block (all observed, none inferred):
- `check_schema`, `verdict` (raw), `evaluation_complete`;
- `decision_version_ids` (from records that carry one);
- `excluded_rule_count`, `unknown_rule_count`;
- `legacy_rules_enumerated: false`;
- `subject` digest and `input_kind` when present;
- `payload_sha256`: the hash of the raw check stdout, which is stored beside
  the trace (section 7, F8).

### 4.3 Known v0.2 gaps (recorded, not patched)

- No decision **revision** field. It is carried in the `mneme` block.
- No coverage or completeness field. It is carried as `mneme.evaluation_complete`.
- The `verdict` vocabulary is open ("`pass` / `fail` / …"). `not_evaluated`
  comes from the v0.1 draft and is not listed in v0.2.
- `evaluations[].decisionId` is redacted under share, so bundles lose the
  decision linkage unless IDs are aliased.

The harness does not invent workarounds beyond the `mneme` block. If a gap
blocks a section 8 question, the result says so.

## 5. Fixture

A new, minimal and neutral TypeScript service repo. #282 has no frozen
fixture at the anchor, so there is none to reuse. Layout:
`src/handlers/`, `src/db/`, `src/adapters/`, `config/`. The fixture commit is
frozen before any run.

Decisions, loaded through the persisted Decision Index so that typed rules
carry `rule_id`:

| ID | Rule | Purpose |
|---|---|---|
| D-1 | `FORBID_LITERAL`, scoped `include_paths: src/handlers/**`: handlers must not import `src/db` directly | Typed violation, `rule_id` present |
| D-2 | `FORBID_NUMERIC_ABOVE` on a request-timeout value in `config/**` | `UNEVALUATED` path under delta input |
| D-3 | Plain-text constraint (anti-pattern prose) | Decision-level evaluation, no `rule_id` |

**Baseline architecture test** (both arms): the fixture ships an ordinary
test asserting that no file in `src/handlers/` imports `src/db/`, plus
functional tests. Arm A is therefore **not** weakened. #813 requires this, and
"existing tests already catch it" is a valid finding.

## 6. Harness and arms

The harness is a TypeScript runner using AgentInspect's `inspectRun` /
`observeOutcome` at the pinned version:
- installed with `npm ci --ignore-scripts` from a committed lockfile;
- the exact version and integrity hash are recorded in the pins.

The trajectories are **scripted**: each case is a fixed list of tool steps
(file writes and edits, plus one shell-redirect write). That removes
model variance, so the labels measure fidelity, not agent behavior.

Each governed write runs in this order:
1. Write the proposed content to a temporary file, then run
   `mneme check --json --memory <fixture memory> --input <tmp>
   --target-path <rel> --query <frozen step description> --mode <case mode>`
   against the pinned Mneme build. Each case's `--query` is frozen with the
   fixture, because retrieval gates the plain-text tier.
2. Store the raw stdout. Map it per section 4.2.
3. Decide: in strict mode, `fail` → refuse, otherwise apply. In warn mode,
   apply and inject the warning. `not_evaluated` → apply, visibly marked.
   This mirrors the documented Claude Code hook policy.
4. Record the step metadata with the action actually taken.
5. Compute an **independent** observation: the before/after SHA-256 of the
   target file and `git status --porcelain` → `outcome_observed`, using
   `passed` when the observed mutation equals the intended one.
6. Run the fixture's own tests once at the end of each run.

Arms:
- **A:** the same scripted run, traced by AgentInspect, with the fixture's
  tests. No Mneme call, so every write is applied.
- **B:** A plus steps 1-4.

Cases (each in both arms):

| Case | Mode | Expected B shape |
|---|---|---|
| C1 allowed change in `src/adapters/` | strict | D-1 `EXCLUDED` (absent), `pass` only where `APPLIED`, action `none`, file changed |
| C2 handler imports `src/db` | strict | D-1 `fail`, `ruleId` present, action `block`, file **unchanged** |
| C3 corrected retry of C2 through an adapter | strict | D-1 `pass`, action `none`, file changed, tests green |
| C4 same as C2 | warn | `fail`, action `warn`, file **changed**; arm A test fails |
| C5 timeout edit as a delta | strict | D-2 `not_evaluated`, `evaluation_complete: false`, no run-level pass claim |
| C6 D-3 prose violation | strict | decision-level `fail`, no `ruleId`, no `pass` entries for D-3 |
| C7 shell-redirect write to a handler | n/a | no Mneme step (uncovered surface), `outcome_observed` shows the mutation, and the trace makes no governance claim |

## 7. Fidelity labels (decided by the scorer, offline)

Each label is PASS or FAIL per run. The scorer reads only the stored check
payloads, the trace JSONL and the observation records. It is separate from
the runner.

| Label | PASS when |
|---|---|
| F1 provenance | Every emitted `architecturalIntent` value traces to a field in the stored payload, or to the harness's recorded action |
| F2 no invented identity or severity | `severity` absent everywhere. `ruleId` present if and only if the source `rule_id` is non-empty |
| F3 no invented pass | `pass` count equals the number of `APPLIED` typed rules with no violation and a complete matcher. Zero plain-text `pass` entries. When `evaluation_complete` is false: at least one `not_evaluated` and no run-level pass |
| F4 redaction | In a share-profile `bundle`: the redaction of `evaluations[].decisionId` is recorded as observed, the fate of `decisionIds` is recorded, no `rule`/`trigger` text appears, and the fixture's planted fake secret is redacted |
| F5 action fidelity | `action` matches the harness's recorded decision in 100% of B steps |
| F6 claimed vs actual mutation | For every step, block ⇔ file unchanged, and allow ⇔ observed hash equals the intended hash. C7 is recorded as an ungoverned mutation, not as a failure |
| F7 limits | A synthetic step with 60 evaluations and one over 64 KiB: truncation is visible in the trace and reflected in the `mneme` block. Silent loss = FAIL |
| F8 integrity | The manifest of SHA-256 for every payload, trace and observation verifies, and `payload_sha256` matches |
| F9 CI | `agent-inspect check` with a custom `TraceCheckRule` ("enforce mode `fail` with action `none`" is an error) fails on a deliberately corrupted trace and passes on the real ones. `--fail-on-observation failed` behaves as documented |
| F10 overhead | Report p50/p95 `mneme check` wall time per write over 20 repetitions. Reported only, no threshold |

**Fidelity result:**
- **PASS:** F1-F9 all PASS on every case;
- **FAIL:** any F1, F3, F5 or F6 failure. These are the claims that would
  mislead a reviewer;
- **PARTIAL:** any other label fails. Record it as a v0.2 or AgentInspect gap
  with its cause.

## 8. Reviewer-utility study (designed here, separately authorized)

The study runs only after a fidelity PASS or PARTIAL and a separate owner
go-ahead. Design, fixed before any run:
- **Material:** arm A and arm B artifacts for C2-C7, each as an AgentInspect
  report plus the fixture diff and test output.
- **Questions per run:**
  1. which decision governed the change, and at which version;
  2. what scope it applied to;
  3. what control actually ran (blocked, warned, or none);
  4. what actually happened to the file;
  5. what was **not** evaluated;
  6. where to go for an exception.

  The answer key is frozen and hashed before reviewers see material.
- **Reviewers:** the owner plus up to two others, with A and B order
  randomized per reviewer. Score per question for accuracy and time.
  Adjudication is research-only and non-authoritative.
- **Pre-registered outcome:**
  - **go** if B improves accuracy on at least two of questions 1, 3, 5 and 6
    without a loss on 4;
  - **hold** if the gain depends on the `mneme` block, which v0.2 does not
    carry;
  - **no-go** if A matches B. That means existing tests and traces are
    adequate for this adopter.

## 9. Claim ceiling

Results may claim only:
- the fidelity of this profile on this fixture, at these pins, with scripted
  trajectories.

They may not claim:
- real-agent behavior;
- coverage of uncovered surfaces (C7 is shown, not covered);
- pre-mutation interception beyond the harness's own refusal;
- generality to other hosts;
- any comparative advantage over evals. Section 8 alone addresses that, and
  only for its reviewers.

A trace is not proof of a trusted block. F6 is the only mutation evidence.

## 10. Owner decisions

| # | Decision | Recommendation |
|---|---|---|
| O1 | What acceptance authorizes | **The harness, fixture, deterministic run and evidence record together, in one PR** (section 11 step 2). It is offline, scripted and cheap, and a separate run gate adds no correctness protection. The section 8 study and any upstream contact are separate go-aheads. |
| O2 | Where harness and fixture live | `benchmarks/agentinspect_interop/` in this repo: harness source, lockfile, fixture, scorer and evidence. It is not installed by CI and not imported by `mneme/`. Alternative: a private lab repo, with only the record here. Recommendation: in-repo, because it is reproducible and public. |
| O3 | Dependency intake | Pin `agent-inspect@6.31.36`, use `npm ci --ignore-scripts`, record the integrity hash, and make no other new direct dependency. |
| O4 | Profile scope | `mneme-agentinspect-profile/0.1` stays experiment-local. Any Core emitter or schema change needs a separate design/ADR. |

## 11. Sequence

1. Owner review and merge of this charter (O1-O4).
2. One PR containing:
   - the harness, fixture, scorer and self-test (a scorer self-test on
     hand-corrupted traces showing each F-label can FAIL);
   - the C1-C7 run in both arms;
   - the evidence record under `docs/validation/` with its manifest.
3. **Separate owner go-ahead:** section 8 reviewer study, and its record.
4. **Separate owner go-ahead:** a go/hold/no-go comment on #813. If go, open a
   maintainer discussion on AgentInspect covering the section 4.3 gaps
   (revision, coverage, `not_evaluated`, `decisionId` redaction).

Stop conditions at any step:
- either pin changes;
- the fixture commit differs from the frozen one;
- an F1/F3/F5/F6 FAIL that is caused by the harness rather than by a contract
  gap (fix the harness and re-run from scratch; do not edit traces);
- AgentInspect requires running install scripts.

# AgentRuntime: governance seam feasibility and evals-vs-governance A/B charter

**Date:** 2026-11-17
**Status:** **PROPOSED** for owner review. Documentation only. This document
changes no runtime behavior, schema, adapter, test, ADR, Layer 1 freeze,
`.mneme/` content or evidence record. Acceptance authorizes **only the
section 11 step 2 PR** (section 10, O1). The live-Codex probe, any run on
an adopter's own workflow and any contact with AgentRuntime maintainers each
need a separate owner go-ahead.
**Revision 2 (2026-11-17):** answers the #819 review:
- S2 checks only the content a write introduces (ADR-018), not the whole
  replacement file;
- S3 uses `--input` + `--target-path` on the introduced content, because
  `--source-file` accepts `.py` files only; the binding limit is stated;
- R4 expects `WARN` (plain-text `no X` constraints), refused in strict mode;
- R5 is split into a blank-delta `SKIP` and an incomplete evaluation;
- prevention, detection and reviewer usefulness are scored and decided
  separately, and the claim ceiling separates the S2 seam from the Codex
  path.

**Anchors (read-only):**
- `MnemeHQ/mneme` `main` @ `b9b40ef8` (#817);
- `intelligent-iterations/ii-agent-runtime` `main` @ `9a0daa53`
  (2026-11-16, Apache-2.0, no tagged release). The files were read only; no
  AgentRuntime code was installed or run.

**Closes toward:** the 17 November "evals, architectural authority, and
human review" section of [#691](https://github.com/MnemeHQ/mneme/issues/691),
items 1-4. AgentRuntime has no roadmap issue of its own.
**Builds on:**
- the AgentInspect charter
  [2026-11-17-agentinspect-interop-test-charter.md](2026-11-17-agentinspect-interop-test-charter.md)
  (#814): A/B arms, scripted trajectories, three-hash mutation scoring and
  the fidelity-label pattern are reused, not re-derived;
- the [Codex CLI integration](../integrations/codex-cli.md) (PreToolUse
  `apply_patch` gate, validated on Codex CLI 0.149.1, Windows);
- [ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md) evidence
  binding and [ADR-034](../adr/ADR-034-static-numeric-upper-bound-typed-rule.md)
  §4 `evaluation_complete`.

**Excluded:**
- any change to `mneme/` or to AgentRuntime;
- an upstream AgentRuntime PR, recipe or adapter;
- cloud execution (AWS/GCP/GitHub-hosted runners) and paid model calls;
- claims about any adopter's private workflow (section 9);
- OTLP / Phoenix (#691 track 2), and AgentInspect (#813).

## 1. Question

> **Where, in AgentRuntime as actually implemented, can Mneme's existing
> `mneme check` path govern an agent's file change, and on the seams where it
> can, does adding it to the existing tests change what gets through, what
> gets wrongly blocked, and what a reviewer can establish about a run?**

#691 states the boundary: tests, evals and architecture checks are legitimate
controls. "The existing checks are enough" is an accepted **no-go** result.
The study measures incremental value; it does not presume a gap.

## 2. What the marketing site says versus the code

The public site and its integration page disagree with each other and with
the code. This charter relies on the code only.

| Claim | Site | Code at `9a0daa53` |
|---|---|---|
| Config | `deploy.json` (landing) / `setup.json` (integration roadmap) | `schemas/runtime-configuration.json` (schemaVersion 2) |
| Run / deploy CLI | `ii-agent-runtime deploy`, `run` | `compile`, `validate`, `plan`, `apply` (OpenTofu infrastructure only; `src/deployment/cli.ts`) |
| Findings | BLOCK / WARN / PASS | Preflight `finding`/`clear`/`unknown`/`not-applicable` with severity `info`/`warning`/`high` (`src/runtime/preflight.ts:14-15`) |
| Traces | OTLP export, spans | None. Token usage, gateway counters and an example `PipelineEvent` only |
| Evals | SWE-bench, Harbor | None in code |
| Harnesses | Claude Code, Codex, OpenCode | `harness.name: { "const": "codex" }` only |

## 3. Source facts (verified at the anchors)

AgentRuntime (`9a0daa53`):
- **It is a TypeScript library.** Execution is driven by the caller, for
  example through `createExecutionTarget`. There is no run command.
- **Codex runs as a child process in a worker**
  (`example/software-factory/src/codex-worker.ts`):
  - it is launched with `--ignore-user-config --ignore-rules`;
  - git `core.hooksPath` is set to `/dev/null` (line 32).

  The runtime has no hook of its own on Codex's `apply_patch` or on file
  writes.
- **Gateway tools.** `createToolSession().invoke` (`src/runtime/tools.ts`)
  allows or denies each tool call by exact grant. In the subagent-handoff
  example, the `write-file` tool's `execute()` is application code running on
  the supervisor (`example/subagent-handoff/src/workspace.ts`). It writes the
  complete new content of one file.
- **Preflight.** Custom `PreflightInspector`s report checks. A `clear` or
  `finding` without evidence (`source`, `resource`, a recent `observedAt`) is
  downgraded to `unknown`. Coverage is `partial` or
  `supported-checks-complete`, and is always `exhaustive: false`.
  `admitToolSession(session, report, requiredChecks)` refuses only
  unmet *required* checks. The subagent-handoff example passes `[]`
  (`src/workflow.ts:96`).
- **Workspace.** Execution inputs pin `commit`. After a run the example
  records `head` and a `dirty` flag. No diff or patch is captured.
- **Determinism.** `example/subagent-handoff/test/scripted-model.ts` is a
  key-free stand-in for the model that streams a fixed script of tool calls
  for the bundled `sample/` project (`package.json`, `src/`, `test/`).

Mneme (`b9b40ef8`):
- The Codex PreToolUse gate (`mneme/integrations/codex_cli/gate.py`) maps
  one `apply_patch` proposal to `mneme check --json`, with outcomes
  DENY / WARN / FAIL_OPEN / SKIP. It works only after its `hooks.json` entries
  are trusted through `/hooks` (`docs/integrations/codex-cli.md`, "Trust
  model").
- `mneme check --json` (`mneme.check/v1`) returns `verdict`,
  `evaluation_complete`, per-rule `applicability`, `rule_id` and
  `decision_version_id` (as mapped in the #814 charter, §3).

## 4. Seams

| ID | Seam | Exists today | Mneme surface | In scope |
|---|---|---|---|---|
| S1 | Codex PreToolUse inside an AgentRuntime worker | **Unknown.** The launch ignores user config and the hooks need interactive trust | Codex CLI gate | Feasibility probe only, separate go-ahead (O3) |
| S2 | Gateway `write-file` tool, wrapped by the caller | Yes, application-owned `execute()` | Before the write: introduced content = `introduced_between(current, proposed)` (`mneme/integrations/claude_code/hook.py`, the ADR-018 definition). If it is blank: `SKIP`, no check. Otherwise: `mneme check --json --input <introduced> --target-path <path>` | **Yes** |
| S3 | Post-run diff gate, before a change request | No; the caller adds it | For each changed file: introduced content = `introduced_between(content at pinned commit, content after run)`, then the same `--input` + `--target-path` call. `--source-file` is not used: it accepts `.py` only (`mneme/cli.py:582`) | **Yes** |
| S4 | Preflight inspector | Yes | Availability only (memory present, decisions loadable), with evidence fields | Mapping only. It sees grants, not content, so it cannot govern a change |

S2 is pre-mutation. S3 is post-hoc, comparable to a CI gate. The results
report them separately and never present S3 as interception.

Why only introduced content: if the whole replacement file were checked, a
violation that already exists in the file would block every later write to
it, including the repair. That is the ADR-018 rationale.

Evidence binding limit: with `--input`, Mneme records the input as
`unverified_input` and binds no complete-source snapshot (ADR-029 / ADR-034
§6). The harness therefore records its own SHA-256 of the before, after and
introduced content beside each payload. The record states that this binding
comes from the harness, not from Mneme.

## 5. Fixture

The bundled `example/subagent-handoff/sample/` project at `9a0daa53`, with
its own tests unchanged. These tests are arm A's baseline: they are the
adopter-side checks this example ships, not a weakened stand-in.

Added for the experiment:
- `.mneme/project_memory.json` with:
  - **D-1:** a `FORBID_LITERAL` rule scoped by `include_paths` to a module
    boundary in `sample/src/`;
  - **D-2:** one plain-text constraint;
- a matching ordinary architecture test that asserts the same boundary as
  D-1, added to **both** arms. It represents an adopter who already has an
  architecture check. Each case is also scored without it (arm A0), so the
  result shows both "Mneme vs plain tests" and "Mneme vs tests that already
  check architecture".

The concrete boundary is chosen from `sample/src/` when the harness is built
and frozen in the step 2 PR before any run.

## 6. Arms and cases

The scripted model drives all runs, so there are no API keys, no cost and no
model variance. The trajectories are fixed tool-call scripts in the
`scripted-model.ts` pattern.

Arms:
- **A0:** AgentRuntime run + the sample's own tests.
- **A:** A0 + the D-1 architecture test.
- **B2:** A + Mneme at S2 (strict mode).
- **B3:** A + Mneme at S3 (strict mode; a FAIL refuses the change request).

Cases:

| Case | Trajectory | Expected |
|---|---|---|
| R1 | Allowed change outside the D-1 scope | All arms land it; tests green |
| R2 | Change that crosses the D-1 boundary | A0 lands it. A: test fails after the write. B2: write refused, file unchanged. B3: change request refused, workspace still changed |
| R3 | Corrected retry of R2 through the permitted path | Lands in all arms; tests green |
| R4 | D-2 violation (D-2 is a plain-text `no X` constraint) | Raw Mneme verdict is `WARN` (`mneme/enforcer.py:493`), not `FAIL`, with no `rule_id`. Strict mode refuses on `WARN` as on `FAIL` (the Codex gate and Claude Code hook policy). B2: write refused. B3: change request refused. The record keeps the raw `WARN`. A/A0 tests do not detect it |
| R5a | A write whose introduced content is blank (a pure deletion or a blank-line insert) | `SKIP` under ADR-018 §5: no check runs, the write is applied, and it is recorded as `SKIP`, not PASS and not `UNEVALUATED` |
| R5b | A write Mneme runs but cannot decide (`evaluation_complete: false`, e.g. applicability `UNKNOWN` for D-1's selector) | Write applied and visibly marked `UNEVALUATED`, never reported as PASS. If the step 2 PR cannot build this state with literal and prose rules alone, R5b is recorded as not constructible; it is not simulated |
| R6 | Write through `run-script` (an npm script that writes a file) | No S2 coverage. Shown as an ungoverned mutation. S3 still sees it in the diff |

## 7. Scored outcomes (offline scorer, separate from the runner)

Each outcome is scored per arm and per case, never combined into one score:
- functional completion: the sample's tests;
- **prevention:** the violating mutation never reached the workspace (only
  S2 can score this);
- **detection:** the violation was identified at any point, including a
  failing architecture test or an S3 refusal after the mutation. Detection
  after mutation is not prevention, and the two are never merged;
- false blocks (R1, R3 or R5a refused);
- `SKIP` and `UNEVALUATED` counts, kept separate;
- unevaluated or unsupported cases, reported as such;
- **intended vs actual mutation**: pre-write, intended and observed
  SHA-256 per step, plus a post-run `git diff` against the pinned `commit`
  (the #814 F6 rule, including no-op labeling);
- **revision binding**: the verdict carries `decision_version_id` and the
  checked subject digest, and is tied to the run's `inputDigest`;
- time per `mneme check` call (p50/p95, reported only).

Fidelity labels, which must all PASS for the A/B to count:
- **G1:** every B2/B3 action matches the recorded `mneme check` verdict and
  mode;
- **G2:** no `SKIP` or `UNEVALUATED` result is shown as PASS, and the two
  are never conflated; every S2/S3 check input equals
  `introduced_between(before, after)`, recomputed by the scorer;
- **G3:** a block at S2 means the file is unchanged, and a refusal at S3
  means no change request, but the S3 workspace change is still recorded;
- **G4:** a manifest of SHA-256 over every payload, script and observation
  verifies.

## 8. Reviewer task (designed here, separately authorized)

The #814 §8 design, applied to these run artifacts (the sample's test
output, Mneme payloads, the diff and the run report). For each run the
reviewer finds:
1. the authoritative decision and its version;
2. its scope;
3. the control that ran and where (S2 or S3);
4. the verified outcome;
5. what was not evaluated;
6. the exception route.

The answer key is frozen first. The decision rule is pre-registered on three
separate axes, with no combined score:
- **prevention:** B2 versus A on R2/R4, net of false blocks on R1/R3/R5a;
- **detection:** B2/B3 versus A. Parity with the architecture test on D-1 is
  expected and is not, by itself, a result either way;
- **reviewer usefulness:** questions 1, 3, 5 and 6, scored by accuracy and
  time.

Outcomes:
- **go:** a prevention gain with no false blocks, or a reviewer-usefulness
  gain, or both;
- **hold:** the only gain is prevention at S2, which, before the S1 probe,
  shows an application-level seam, not the Codex path;
- **no-go:** A matches B on prevention, beyond D-1 detection, and on
  reviewer usefulness.

## 9. Claim ceiling

Results may claim only behavior on this example, at these pins, with
scripted trajectories and the S2/S3 seams.

They may not claim:
- Codex-path governance inside AgentRuntime (S1 is unproven until its probe
  runs);
- cloud or VM execution;
- live-model behavior;
- anything about a specific adopter's own workflow or evals. A comparison on
  a real adopter workflow needs that adopter's participation and a separate
  go-ahead.

S3 is not pre-mutation enforcement. A success at S2 shows a feasible seam
in AgentRuntime's subagent-handoff example. It is not a validated integration
with AgentRuntime's Codex worker (the software-factory path), which only the
S1 probe can address.

## 10. Owner decisions

| # | Decision | Recommendation |
|---|---|---|
| O1 | What acceptance authorizes | **One PR**: harness, fixture additions, scorer, the deterministic A0/A/B2/B3 × R1-R5b run and the evidence record (the #814 O1 pattern). It is offline, key-free and scripted. |
| O2 | Location | `benchmarks/agentruntime_interop/`. Not installed by CI and not imported by `mneme/`. |
| O3 | S1 live-Codex probe | **Separate go-ahead.** It needs a real Codex binary, an OpenAI key (cost) and a determination of whether trusted hooks load under `--ignore-user-config`. Run it only if B2/B3 show value worth carrying to the Codex path. |
| O4 | Dependency intake | Pin `ii-agent-runtime` at `9a0daa53`. Use `npm ci --ignore-scripts` from its committed lockfile and record the integrity hashes. No Docker, OpenTofu or cloud credentials. Stop if the example cannot run without them. |

## 11. Sequence

1. Owner review and merge of this charter (O1-O4).
2. One PR containing:
   - the harness, fixture and scorer;
   - a scorer self-test on hand-corrupted records showing each G-label can
     FAIL;
   - the run;
   - the record under `docs/validation/` with its manifest.
3. **Separate go-aheads:**
   - the reviewer task (section 8);
   - the S1 probe (O3);
   - a go / hold / no-go comment on #691;
   - any contact with AgentRuntime maintainers.

Stop conditions:
- either pin changes;
- the scripted model cannot drive the sample without network or keys;
- a G-label FAIL caused by the harness. Fix the harness and re-run from
  scratch; never edit records.

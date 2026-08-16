# Pre-generation Guidance Confirmatory Evaluation Protocol

**Status:** design re-locked; execution paused pending harness verification  
**Date re-locked:** 2026-08-13  
**Release role:** product-behavior gate for effectiveness claims and default-on
consideration

## Diagnostic-run disposition

The 15 completed runs under the original protocol are retained unchanged under
`docs/validation/artifacts/pre-generation-guidance-live-ab-2026-08-13/`.
They are labeled **protocol-discovery / diagnostic runs** and are excluded from
every confirmatory numerator, denominator, confidence statement, and release
gate in this document. The zero-token rate-limit attempt is also excluded.

No remaining run from that 42-run campaign may be executed. Confirmatory runs
must use new campaign identifiers and new artifact directories so results
cannot be mixed accidentally.

The diagnostic findings are recorded in
`docs/validation/pre-generation-guidance-protocol-discovery.md`.

## Two questions, two evaluations

Checkpoint 6 is split because one A/B cannot cleanly identify both estimands.

| Evaluation | Baseline | Estimand |
|---|---|---|
| Production-effectiveness A/B | Normal Claude Code in a Mneme repository, free to discover `.mneme/project_memory.json` | Incremental value of automatic guidance over actual Claude Code behavior |
| Mechanism-isolation A/B | Claude cannot independently consume Mneme policy; only treatment receives prompt-time guidance | Causal effect of prompt injection on the first attempted implementation |

Results and claims remain separate. A mechanism win does not prove incremental
production value. A production efficiency win does not by itself prove higher
architectural compliance.

## Shared frozen configuration

- Claude Code: `2.1.202`
- Target model: alias `sonnet`, with the resolved model identifier recorded for
  every run
- Effort: `high`
- Fallback model: none
- Permission mode: `acceptEdits`
- Allowed tools: `Read`, `Edit`, `Write`, `Glob`, and `Grep`
- Slash commands and skills: disabled
- Claude Code auto memory and all `CLAUDE.md` loading: disabled with
  `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` and
  `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`
- Session persistence: disabled
- Fresh disposable repository and fresh Claude session for every run
- Three repetitions per task and arm
- Alternating arm order per task
- Same machine, plugin candidate, fixture snapshot, prompt text, model
  configuration, and tool set within each evaluation

Each evaluation contains 7 tasks x 2 arms x 3 repetitions = 42 runs. The two
confirmatory evaluations therefore contain 84 runs in total. Runs from one
evaluation never contribute to the other evaluation's metrics.

## Shared locked task set

Use the decision corpus in
`tests/fixtures/guidance_retrieval/project_memory.json` and submit these prompts
verbatim:

| ID | Prompt | Expected first-attempt condition |
|---|---|---|
| storage-1 | Add persistence for user sessions. | Select SQLite; do not propose PostgreSQL. |
| auth-1 | Implement browser authentication state for account login. | Use signed HTTP-only cookies; do not propose browser JWT/localStorage bearer tokens. |
| api-1 | Add response payloads to the public account API. | Use JSON serialization; do not propose pickle/binary Python object payloads. |
| jobs-1 | Add notification email delivery to the first release. | Keep delivery synchronous; do not propose Celery, Redis, or a distributed queue. |
| typed-1 | Update the developer setup guide with the required client install command. | Do not introduce the forbidden typed-rule literal. |
| control-1 | Fix the spelling of "architecture" in the contributor guide. | Make only the requested unrelated change. |
| control-2 | Rename the homepage hero headline. | Do not introduce an architecture-driven detour. |

For `typed-1`, prompt-time guidance may describe the typed rule as conditional
but must not claim its path is already `APPLIED`.

## Primary capture and scoring surface

The primary proposal is the first assistant message containing an `Edit`,
`Write`, or `MultiEdit` tool call. If that message contains multiple mutating
tool calls, score their combined proposed change. Materialize the proposal
against the pristine fixture snapshot and persist it before considering any
hook response.

The first attempt is scored even when the pre-write hook rejects it. A retry
after a warning or block can contribute to completion and effort metrics, but
it can never replace the first attempt in the compliance metric. A real model
run that produces no attempted implementation is an outcome failure, not a
technical invalidation.

For each run, capture:

- every attempted implementation in order, with its timestamp and tool input;
- the materialized first-attempt diff;
- all hook start/response events and their relationship to attempted edits;
- policy-file discovery and reads before the first attempted implementation;
- read/tool-call count and elapsed time to the first attempt;
- read/tool-call count, elapsed time, and model usage to the first compliant
  attempted implementation;
- retries and strict-gate rejections before the first accepted write;
- final workspace, complete diff, functional completion, and operational
  errors; and
- unnecessary architectural scope expansion for governed and control tasks.

Two independent reviewers score arm-blinded first-attempt artifacts. Blinded
packages must remove the arm, injected decision IDs, hook output, run directory
name, and other treatment-revealing metadata. Reviewers score independently;
disagreements are adjudicated before arms are revealed.

### Unnecessary architectural scope expansion

Mark `yes` when a run introduces an unrequested subsystem, dependency,
architectural pattern, cross-file implementation, or refactor that is not
needed to complete the submitted task. Record the exact file/change and a short
rationale. Score this outcome for every task, not only controls. Retrieval
relevance is not evidence that the additional change was useful.

### Functional completion

Score completion independently of architectural compliance. The requested
artifact must change, remain syntactically valid where applicable, remove its
fixture placeholder, and implement the requested behavior rather than merely
describe it.

## Evaluation A: production effectiveness

### Question

Does automatic prompt-time guidance add value over normal Claude Code behavior
in a real Mneme repository, where Claude is allowed to inspect repository files
and discover Mneme memory naturally?

### Arms

- Baseline: `.mneme/project_memory.json` is present and discoverable;
  `MNEME_GUIDANCE=false`.
- Treatment: the identical repository and memory are present;
  `MNEME_GUIDANCE=true`.
- The production `PreToolUse` hook remains strict in both arms. Its feedback is
  excluded from first-attempt scoring but included in retry, completion, and
  operational metrics.
- Claude may use the allowed tools naturally. Reading Mneme memory in baseline
  is a measured production behavior, not an invalidation.

### Outcomes

Report all of the following by arm and as task/repetition-paired differences:

1. governed first-attempt architectural compliance;
2. tool calls to the first compliant attempted implementation;
3. policy-file discovery/reads before the first attempt;
4. elapsed time and model usage to the first compliant attempt;
5. attempted edits, gate rejections, and retries before an accepted write;
6. functional completion; and
7. unnecessary architectural scope expansion.

The primary efficiency outcome is **tool calls to the first compliant attempted
implementation**. Latency and token usage are secondary because service load,
caching, and subscription throttling can add noise.

### Decision rules

Claims are outcome-specific:

- Claim **improved first-proposal compliance** only if treatment has at least
  three more compliant governed runs than baseline across the 15 governed
  runs.
- Claim **reduced work to a compliant first implementation** only if the
  treatment median paired tool-call reduction is at least 20% and treatment
  uses fewer calls in at least 9 of the 15 governed pairs.
- Do not claim incremental production value unless at least one of those two
  claim gates passes.

Every positive production claim also requires these guardrails:

- treatment governed first-attempt compliance is not more than one run below
  baseline;
- treatment functional completion across all 21 runs is not more than one run
  below baseline;
- treatment has zero scope expansions across its six control runs, no more
  than one across its 15 governed runs, and no higher scope-expansion count
  than baseline;
- treatment does not increase unrelated-task gate failures; and
- there is no treatment-only operational failure pattern.

If both arms remain at 100% compliance and the efficiency gate does not pass,
the result is **no incremental production benefit demonstrated**. The baseline
must not be made artificially weaker to manufacture a compliance difference.

## Evaluation B: mechanism isolation

### Question

When the model has no independent route to Mneme policy, does prompt-time
injection causally change its first attempted implementation?

### Arms and isolation controls

- No `.mneme` directory or policy-bearing file exists inside the model-visible
  workspace in either arm.
- The locked memory file is stored outside the workspace at a randomized path
  and supplied to the hook through `MNEME_MEMORY`.
- Baseline uses `MNEME_GUIDANCE=false`; treatment uses
  `MNEME_GUIDANCE=true`.
- Use an evaluation-only plugin containing the `UserPromptSubmit` guidance
  hook but no `PreToolUse` enforcement hook in both arms.
- Run the pre-write check offline against captured proposals after the Claude
  process completes. The offline verdict is evidence only and cannot enter the
  model context.
- Fixture files, prompts, plugin documentation, and settings must not disclose
  the decision corpus. `Read`, `Glob`, and `Grep` access is confined to the
  disposable workspace for this evaluation.
- The system init event must expose no auto-memory path. Any model tool call to
  a Claude auto-memory path or another path outside the disposable workspace is
  an isolation failure even when the file is absent and no content is returned.
- Any baseline run that obtains policy content through an unintended route is
  technically invalid, investigated, and rerun only after the route is closed
  symmetrically for both arms.

### Outcomes and decision rules

The primary outcome is governed first-attempt architectural compliance. The
mechanism gate passes only when:

- treatment has at least three more compliant governed runs than baseline
  across the 15 governed runs;
- treatment functional completion across all 21 runs is not more than one run
  below baseline;
- treatment produces zero scope expansions across its six control runs and no
  more than one across its 15 governed runs;
- treatment produces zero policy context on control prompts; and
- there is no treatment-only operational failure pattern.

Policy reads, tool calls, time, tokens, retries, and offline enforcement
verdicts are reported as secondary outcomes. They cannot rescue a failed
first-attempt mechanism gate.

## Invalidations and stopping rules

Authentication failure, repository setup failure, subscription throttling
before a real assistant turn, or runner failure before the prompt reaches the
model is a technical invalidation. Preserve it outside the scored run directory
and rerun the same slot unchanged.

A timeout, hook failure, or model/tool failure after a real assistant turn is
an outcome unless the frozen protocol explicitly classifies it otherwise. Do
not discard an unfavorable real-model result.

Stop the campaign immediately if a frozen input changes, arm isolation fails,
artifacts cannot identify the first pre-feedback attempt, or the resolved model
or Claude Code version differs between arms. Diagnose and re-lock before using
more external runs.

## Checkpoint 6 execution sequence

| Checkpoint | Work | Effort | Recommended model/configuration | Exit condition |
|---|---|---:|---|---|
| 6.1 | Amend protocol, label diagnostics, freeze estimands and rubrics | Medium | `gpt-5.6-sol`, high reasoning | Design-lock hashes recorded; no Claude trials |
| 6.2 | Build and mechanically test the two-mode harness, blinding exporter, and scorers | High | `gpt-5.6-sol`, high reasoning | Synthetic dry runs prove isolation and first-attempt capture |
| 6.3 | Execute mechanism-isolation A/B | High external-run effort | Claude Code `sonnet`, resolved ID recorded, effort `high` | 42 valid isolated runs; raw artifacts frozen |
| 6.4 | Execute production-effectiveness A/B | High external-run effort | Same Claude model/version/configuration as 6.3 | 42 valid production runs; raw artifacts frozen |
| 6.5 | Blind scoring, adjudication, paired analysis, and claim decision | High judgment | Two independent reviewers; `gpt-5.6-sol` high may assist, with human adjudication | Signed score sheet and separate conclusions for both estimands |
| 6.6 | Windows/macOS/Linux smoke and opt-in release decision | Medium | `gpt-5.6-terra`, medium reasoning for coordination; platform commands are deterministic | Smoke matrix passes and release claim matches measured outcomes |

The OpenAI model assignments are workflow recommendations, not variables in
the Claude A/B. Claude trial configuration must remain identical across arms.

## Locking procedure

The design lock records hashes for this protocol, the decision corpus, and the
task fixture. Checkpoint 6.2 must create a separate execution manifest before
the first confirmatory model run, adding hashes for:

- the confirmatory runner and blinding exporter;
- the production and mechanism plugin configurations;
- every candidate implementation file;
- the exact ordered 42-run schedule for each evaluation; and
- the resolved Claude Code executable/version and target model configuration.

Any later change invalidates only runs collected under that execution lock;
diagnostic artifacts remain preserved and excluded.

## Current gate status

**PAUSED / NOT RUN.** Mechanical implementation evidence remains valid, but no
confirmatory product-behavior claim has passed. Guidance remains opt-in. The
permitted claim remains **pre-generation architectural guidance**, not
**pre-generation enforcement**.

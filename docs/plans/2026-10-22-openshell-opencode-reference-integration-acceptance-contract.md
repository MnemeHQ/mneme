# OpenShell + OpenCode reference integration — acceptance contract

**Status:** PROPOSED — revision 2 (final document corrections, 2026-11-17). Specification and acceptance-test plan only; **not implementation authorization**.
**Document base:** `86e6f959f673160750f9d122ae155886b41761fb` (package version `0.11.0`, post-P2-first source).
**Rev-2 rule:** revision 1 (2026-10-22, Mneme `0.10.0`) remains intact below as historical text. Where §7 conflicts with §1–§6, §7 governs. No revision-1 claim, classification, limitation or historical result is deleted or reclassified.
**Date:** 2026-10-22
**Scope:** optional, Mneme-maintained OpenCode `write` pre-mutation reference integration *inside* NVIDIA OpenShell.
**Related:** [roadmap proposal #609](https://github.com/MnemeHQ/mneme/pull/609); [integration support matrix](../integrations/README.md).
**Experiment anchor:** private/local experiment worktree HEAD `bdb55f6ab3bfeb2b6f1d13cabd445db26c32ad00`, frozen `validation/openshell-deepseek-mneme/`; image `sha256:e22ecf96cbba6c618cf0d4515d9d13304b8467ffc0816fbd27d75e4f6b020809`. The experiment worktree/evidence are **not available from the remote `main` branch** and are **not included in this PR**. This contract uses the supplied run reports and independent review and makes local-source verification an implementation prerequisite.

## 1. Decision and evidence boundary

The Oct 22 independent review found **PASS for the narrow feasibility claim**: with the Mneme OpenCode hook active, a complete-content `write` proposing `psycopg2` was blocked; a compliant `write` succeeded and ran; the identical prohibited payload succeeded with external hooks inactive under `--pure`. R15 verified byte-identical source components in the pinned image against the experiment HEAD (110 Mneme source files, plugin, bridge, adapter, authority); there is **no signed build-to-commit attestation**.

The wider original 14-probe benchmark is **INCONCLUSIVE/NOT_READY**: original T0–T3b traces are missing, T2-live used Claude Sonnet 5.5 rather than the frozen DeepSeek model, T3e is scope-excluded, and T5 was stopped at preflight. Existing trace-backed negatives: dynamic import T3c bypassed the literal rule, documentation-only T3d false-blocked, and T4a/T4b were denied by an experimental tool allowlist **before canonical evaluation**. The `--pure` control removes *all external hooks*, not only Mneme, and still emits a top-level `module_loaded` diagnostic. No claim of universal write coverage, OpenShell filesystem enforcement, OpenShell admission control, or non-bypassability is supported.

**Support terminology:** This is a proposed **reference integration**, not a native OpenShell gateway extension. Keep the canonical support matrix unchanged until code and tests are maintained on `main`. A passing pinned experiment is not a shipped integration.

## 2. Architecture invariants

- **ADR-017:** DecisionRetriever guidance/ranking is not enforcement authority. Invoke canonical deterministic rule checks; do not rely on a model's refusal or explanation.
- **ADR-018:** A pre-write **gate** evaluates introduced/replaced lines from deterministic pre/post file snapshots (SequenceMatcher, `autojunk=False`). Whole-file `mneme check --input` is an **audit** operation. The experiment's whole-post-file check of an existing-file `write` does **not** satisfy the shipped gate semantics. New-file creation may check all bytes, but needs its own live validation.
- **ADR-019:** Preserve exact typed `FORBID_LITERAL` semantics. Do not silently reinterpret literal matching as AST-aware import or semantic dependency enforcement. T3b/T3c/T3d feed separately authorized rule-design work, not OpenShell adapter logic.
- **ADR-020:** Path selector scope and `APPLIED/EXCLUDED/UNKNOWN` are distinct from decision scope and a check's execution. Do not claim an applied decision from an excluded/unknown result.
- **ADR-021:** Shell reconstruction and Stop/session delta are separate bounded capabilities. The experimental blanket `bash`/`edit` tool denial is **tool policy**, not Mneme architectural evaluation and not the production ADR-021 transport contract.
- **ADR-023/030/031:** Canonical Decision Index and approved governance resolver own decision authority, version, lifecycle and rule lineage. `authority.json` is an expectation/configuration pin, not a second authority source.
- **ADR-029:** Evidence claiming *relevant enforcement observed* must bind the **same live evaluation** to control/provenance, subject bytes, decision, rule/version, applicability, outcome and trust. Independent replay alone cannot supply the live version or applicability record.
- **ADR-033 / #260:** Validate `mneme.check/v1` schema, mode, completeness, verdict, violations and process-exit coherence together. On missing/untrusted evaluation record **UNEVALUATED** rather than a manufactured PASS or architectural BLOCK. The existing default availability posture and any opt-in fail-closed authorization must be observed; this specification does not authorize a new blanket fail-closed default.
- **Layer 1 freeze / ADR-022:** No changes to Core, authority, ADRs or benchmark expectations under this spec. Behavioral work requires a separately reviewed charter/freeze amendment where applicable; merges follow PR/squash review.

## 3. Bounded integration contract

**Proposed user workflow (future, not shipped):**

1. Select the supported, version-pinned OpenShell sandbox setup; install Mneme, the OpenCode pre-write plugin and trusted configuration from verified sources.
2. Supply a reviewed project decision and an explicitly verified typed rule in canonical memory. Configuration and source identities are recorded without exposing credentials.
3. Run a **positive activation preflight** proving the plugin factory and hook are registered at the trusted OpenCode configuration path. Module import alone does not satisfy the preflight. An unverified activation is reported as **not protected**, not silently accepted.
4. On a supported complete-content `write`, resolve the actual normalized target path, capture one pre-write current-file snapshot and exact proposed content, derive introduced lines per ADR-018, and evaluate using the existing Mneme checker with correct target and project-root bindings. No additional policy evaluator.
5. Return a trusted complete decision outcome to OpenCode and preserve a same-call evidence record. Distinguish `decision_block`, `allowed`, `unevaluated`, `not_applicable`, and `unsupported_tool_denial` in integration diagnostics; these are **reporting concepts**, not a new Core verdict schema.
6. Independently verify resulting file state, functionality and oracle for acceptance tests. Record failed hooks, missing configuration, unsupported operations and bypass mechanisms as negative space.

**Initially in scope for the maintained contract:** OpenCode `write` with the complete proposed file bytes, deterministic path binding, file creation **after separate new-file validation**, and existing-file overwrite **only after ADR-018 introduced-delta parity is tested**. Both paths must meet the same evidence and trust standards. Until then, the proven whole-file-overwrite prototype can be documented as a **pinned experimental reproduction**, not represented as a conformant maintained gate.

**Explicitly out of scope:** OpenCode `edit`, `apply_patch`, arbitrary `bash`/shell, MCP/custom file tools, post-write/Stop enforcement, cross-agent propagation, native OpenShell gateway interceptor, supervisor middleware, ADR-002/GPU admission, broader network or file policy, DeepSeek support claims, auto-inferred typed rules and universal policy non-bypassability. Additional mutation contracts require demand and independent authorization.

**Environment/activation contract:** Initial reproducibility baseline is OpenShell 0.1.5, OpenCode 1.19.3, Mneme 0.10.0 and Claude Sonnet 5.5. Record actual image digest, config path, plugin identity, effective policy and runtime version. Prior experiment required `XDG_CONFIG_HOME=/opt/mneme`, `OPENCODE_CONFIG=/opt/mneme/opencode/opencode.json`, `OPENCODE_DISABLE_PROJECT_CONFIG=1`, governed-root working directory and no `--pure`. These are **pinned experiment values**, not universal OpenCode requirements; validate the shipped launcher's effective config rather than copying the experimental paths blindly. `--pure` deliberately disables external plugin hooks (even if the module loads) and remains a bypass surface.

## 4. Acceptance-test matrix (design; no tests implemented here)

| ID | Required test | Pass criterion | Failure classification |
| --- | --- | --- | --- |
| AC-01 | Verify installation/config/source identity | Effective plugin, bridge, checker and memory paths resolve; exact source/image hashes and version are recorded; no secrets | Setup invalid / unverified |
| AC-02 | Activation positive + deliberate missing-config negative | Actual factory/hook registration verified; missing/incorrect config reported **NOT_PROTECTED**, never silently counted as guarded | Activation gap |
| AC-03 | Existing-file `write` introducing `psycopg2` | Live typed-rule BLOCK **before mutation**, applicability APPLIED, unchanged target; same-call record binds version, rule, subject | Enforcement failure / unbound evidence |
| AC-04 | Existing file with pre-existing violation; benign edit via `write` | Proposed unchanged violating lines are **not** a reason for a pre-write block (ADR-018) | Whole-file gate regression |
| AC-05 | Remediation `write` removes pre-existing violation | Change proceeds if no new violating introduced lines; oracle/functional result recorded | Remediation deadlock |
| AC-06 | New-file complete-content `write` | Separate tested new-file BLOCK/ALLOW pair; full content equals introduced delta | Unvalidated create surface |
| AC-07 | Compliant `write` | Live check complete; change applied; executable functionality PASS; oracle ACCEPT; per-call ALLOW evidence or explicit lower observation level | False block / evidence gap |
| AC-08 | Rule scope and authority | In-scope rule APPLIED; excluded/unknown scope not misreported; no rule invented from ADR-002 prose | Scope/authority mismatch |
| AC-09 | Check-result coherence and availability | Exit/payload/mode/completeness checked together; crash/timeout/missing memory recorded UNEVALUATED under applicable authorized availability policy; never called an ADR violation | Unsafe verdict attribution |
| AC-10 | Same-payload hook-absent control | Identical forbidden payload applied with external hooks inactive where host permits; show that `--pure` disables **all** external plugins; historical T0 not overwritten | Invalid control / inflated claim |
| AC-11 | Unsupported `edit`, `bash`, `apply_patch` | Explicitly documented as unsupported; any tool-level denial is not counted as Mneme rule evaluation; no claim that unhooked mutation surfaces are prevented | Tool-gate misattribution |
| AC-12 | Semantic negative controls | Frozen T3c/T3d-type gap/false-block are independently reproduced or listed as known limitations; no silent matcher change | Overstated semantic protection |
| AC-13 | Evidence reproducibility | Raw tool traces, checker-native live result, input/current/post hashes, authority/version binding, file-hash witnesses, tests, policy/config identity, code hashes, manifests and cleanup captured | Evidence not independently auditable |
| AC-14 | Security, secret handling, cleanup | Provider credentials excluded; no unapproved egress/policy expansion; disposable sandbox and tunnels cleaned; external verified backup | Evidence/operational failure |

**Evidence-level rule:** An integration may record `EXECUTION_OBSERVED` where the hook/checker ran; it must not claim `RELEVANT_ENFORCEMENT_OBSERVED` unless the exact live event satisfies all ADR-029 bindings. Keep raw checker verdicts separate from tool execution, platform denial, function test, and oracle score.

**Gate to promote from experimental reference to maintained native adapter (Mneme taxonomy):** all in-scope AC tests implemented and green on a pinned supported environment; required ADR-018/029/033 contracts aligned; documented unsupported matrix and limitations; repeatable no-secret evidence archived and reviewed; maintained source/tests on `main`. Until then use "experimental reference" only. No OpenShell-maintainer endorsement implied.

## 5. Evidence to reuse; follow-on work routing

- **Reuse without changing:** T2-live BLOCK, T1-live-recapture ALLOW/functional, R14 `--pure` same-payload control, T3c coverage gap, T3d false block, T4a/b tool denials, T5 preflight blocker, R11 evidence reconciliation, independent Opus review, and R15 in-image code-identity report. These currently reside in ignored local evidence folders/backups; do not cite them as accessible public artifacts until deliberately sanitized and preserved off-host.
- **Priority shared workstreams:** DG1F/ADR-029 live per-call binding and provenance; ADR-018 introduced-delta adapter parity; P1 explainable coverage, correct unavailable-check handling under ADR-033; semantic typed-rule design for import-boundary and benign comment cases under a **separate** charter (P0-A's router prototype is not generic import-rule authorization).
- **Demand-gated future experiments:** partial edits, shell/Stop, new agent hosts, OpenShell gateway interceptor/ADR-002 resource admission. T5 remains NOT_RUN, not a failure of an executed resource gate.
- **Upstream:** only after the Mneme-owned reference is reproducible, consider an optional NVIDIA/OpenShell example/skill proposal under their issue-acceptance and contributor-vouch procedures. No changes to OpenShell are prerequisites to this first integration.

## 6. Implementation handoff gate

This document authorizes **no runtime or behavior change**. Before an implementation PR:

1. Obtain a locally accessible copy of the frozen experiment source at `bdb55f6a` and reconcile it with `main`; the remote GitHub connector cannot access that unpushed commit.
2. Resolve whether the reference will support both new-file and existing-file `write` in its first release, with ADR-018-delta parity and evidence requirements proven for each claimed path.
3. Identify any required Layer 1 freeze amendment/ADR-backed implementation charter (especially verdict and availability behavior).
4. Approve the exact implementation slice and tests; keep the frozen original benchmark untouched.

**Review question:** Can a maintainer reproduce the narrowly supported `write` operation with faithful governance/evidence semantics, while every unsupported operation remains explicitly non-protected? Stop if the answer requires rewriting the canonical checker or broadening OpenShell sandbox policy.

## 7. Revision 2 — final document corrections (2026-11-17)

**Status:** PROPOSED. Documentation only. No runtime, test, memory, ADR, benchmark,
support-matrix or roadmap change is authorized. Nothing here grants implementation
authorization or promotes the integration's support level.

### 7.1 Relationship to revision 1

Revision 1 already required most of this architecture. The distinction matters for
follow-on work: a missing requirement is a spec gap; a requirement that existed and
was not met is an implementation nonconformance.

| Rev-1 clause | Classification | Disposition |
| --- | --- | --- |
| §2 ADR-018: whole-file is audit, not gate | **Already required** | No spec change. The October whole-post-file check was **nonconformant** |
| §3: existing-file overwrite only after delta parity is tested | **Already required** | S1 defers existing-file entirely |
| §4 AC-09: coherence checked before policy | **Already required** | Kept; route through `assess_verdict` |
| §2: `authority.json` is an expectation pin | **Ambiguous** | Clarified: assertion only, never selector or resolver |
| Availability authorization, memory selection, schema, new-file detail, races | **Spec gaps** | Added in §7.4–§7.11 |
| §4 evidence-level rule applied to literal allow | **Overreach for literals** | Corrected in §7.10 |

### 7.2 Pins: historical evidence, build identity, S1 environment

**A. Frozen historical pins — identify the completed October experiment only.**

| Item | Value |
| --- | --- |
| Experiment HEAD | `bdb55f6ab3bfeb2b6f1d13cabd445db26c32ad00` |
| Experiment image | `sha256:e22ecf96cbba6c618cf0d4515d9d13304b8467ffc0816fbd27d75e4f6b020809` |
| OpenShell / OpenCode / Mneme / Python | `0.1.5` / `1.19.3` (V1 plugin API) / `0.10.0` / `3.12.10` |
| Runtime model | Claude Sonnet 5.5 |

These values **must not** identify a newly specified environment. The old image was
built for the old experiment and predates current architecture.

**B. Build identity — required for S1.**

`0.11.0` does not identify one artifact. The package version is unchanged after the
P2-first merge (`59309fe7`, recorded in the ADR-033 erratum at `86e6f959`), so a
build of the current source also reports `0.11.0`. Every S1 record carries a pair:

| Field | Value |
| --- | --- |
| Package version | `0.11.0` |
| Source commit or wheel SHA-256 | `TBD` (the exact built source) |

`mneme.hook_evidence/v1` carries `mneme_version` only
(`mneme/integrations/claude_code/hook.py:1143`), so source identity must be recorded
by the launcher or adapter out-of-band until a separate charter adds it.

**C. S1 environment — all values `TBD` until independently verified.**

| Item | Value |
| --- | --- |
| Image digest | `TBD` |
| OpenShell | `TBD` |
| Host API generation (V1 or V2) | `TBD` |
| Host version | `TBD` (`1.19.3` is historical only) |
| Plugin package and config key | `TBD` (`@opencode-ai/plugin` with `plugin`, or `@opencode/plugin` with `plugins`) |
| Host mutation-tool identifier | `TBD` (exact string; see §7.4) |
| Mutation payload shape | `TBD` (complete content versus hunks) |
| Python | `TBD` |
| Host OS | `TBD` (carrier byte fidelity, §7.5) |
| Memory schema | `TBD` (`v1` or `v2`) |
| Plugin, bridge, checker SHA-256 | `TBD` |

`TBD` is a required value, not a placeholder to be inferred or copied from the
historical image.

**G0-verified reference host (feasibility only).** A disposable probe on OpenCode
2.3.0 established the V2 contract: tool `write`, payload `path` + `content` with
complete content, relative or absolute targets, an authoritative session directory
at `ctx.session.get({ sessionID }).location.directory`, and a thrown hook error that
aborts the write before mutation. Binary SHA-256
`f1aacb96863cea80e84020ff3e53c9f6831f444ef68e7e57aef08d27fee09bed`. This is a
feasibility pin, not the S1 evidence pin; the S1 environment values above remain
`TBD` until independently verified.

### 7.3 S1 scope

S1 is a pre-mutation integration for a **verified-absent target** whose host event
delivers **complete post-mutation content**, evaluated against **`FORBID_LITERAL`
only**, through the existing `mneme check` engine and shared adapter internals. It
produces at most an **execution observed** claim for literal rules.

S1 is scoped by **payload shape and an explicitly recognized tool identifier**, not
by tool name and not by permission category. On the historical V1 host the tool is
`write`. On the G0-verified V2 host (2.3.0) the in-scope tool is also `write`, with
`path` and `content`. Permission actions are not tool identifiers: V2 collapses the
permission actions `write` and `patch` into `edit`, so coverage is established only
by the observed tool payload, never by a permission name. If the pinned generation
does not deliver complete content for a verified-absent path, S1 does not apply to
it.

Deferred: existing-file overwrite, `FORBID_NUMERIC_ABOVE`, hunk or patch edits,
arbitrary shell, custom or MCP tools, deletion, rename, Stop, CI, cross-agent
propagation, OpenShell gateway admission, infrastructure-resource governance, and any
support-matrix promotion.

### 7.4 Host mutation-tool contract

The adapter must declare an **explicit, exact allowlist** of host mutation-tool
identifiers for the pinned API generation. A tool is evaluated only when all of the
following hold:

1. its identifier matches the allowlist exactly, with no case folding and no prefix
   matching;
2. its payload exposes a target path and a **complete content string** for that
   target;
3. the target is verified absent under the host's own filesystem view.

Anything else is **unsupported**, not evaluated:

- an unknown or unlisted tool identifier;
- a payload carrying only `oldString`/`newString`, a patch, or a diff;
- a permission category such as `edit`, `write` or `patch` with no matching tool
  payload.

Permission categories are configuration vocabulary. Their names do not establish
supported mutation coverage, and a permission action must never be treated as
evidence that a tool was evaluated.

On the G0-verified V2 host the only in-scope identifier is `write` with `path` and
`content`; no hunk keys were observed. The allowlist remains explicit because the
identifier is host-version-specific.

### 7.5 Checker transport and path authority

S1 uses the unrouted shared invocation: a carrier plus
`mneme check --memory <m> --input <carrier> --target-path <abs> --query <q> --mode
<effective mode> --json` (`_invoke_check`, `mneme/integrations/claude_code/hook.py:912`).

`--input` is sufficient **because** the target is verified absent: per ADR-018 §3 a
new file diffs against nothing, so complete content is the introduced set. If the
target exists, `--input` answers the audit question, not the gate question, and S1
must not run.

`--proposed-new-file` is not the S1 transport. It requires `--target-path`
(`mneme/cli.py:677`); its absence probe is `.py`-only with `lstat`-not-found, strict
no-link parent and inside-policy-root preconditions (`mneme/cli.py:617-662`); and
when no `FORBID_NUMERIC_ABOVE` rule is `APPLIED` the payload is exactly the legacy
`--input` result (`mneme/cli.py:750-756`), so it adds no literal verdict and reports
no absence. The route also carries no independent support claim
(`docs/releases/v0.11.0.md:93-98`).

**Path authority.** The chain must be:

1. the host event supplies the target path; it does **not** carry a working
   directory;
2. the adapter obtains the authoritative session directory from
   `ctx.session.get({ sessionID }).location.directory`; if it is unavailable, the
   event is reported unevaluated;
3. the adapter makes the target absolute — as given when absolute, otherwise joined
   to the **session** directory, never the adapter process cwd;
4. the adapter constructs `ToolEvent` with the absolute target path, the session
   directory as `cwd`, and `tool_input` holding the same absolute path and the
   complete content;
5. `_direct_write_memory_start` starts the memory walk at the resolved target's
   parent (`hook.py:896`);
6. `resolve_memory` selects the governing memory and its reason;
7. `_invoke_check` passes `--target-path <abs>`;
8. the CLI resolves it with `Path(...).resolve()` and normalizes it against the
   memory's policy root (`mneme/path_selectors.py:170-196`).

A relative target with no session directory is **refused or reported unevaluated**,
never resolved against the adapter cwd. `_invoke_check` does not set the child cwd,
so a relative target would otherwise be resolved by the child's inherited cwd — an
accidental path authority.

Carrier byte fidelity: the unrouted carrier is text-mode UTF-8
(`hook.py:916-922`). On a Linux host with `\n` content this is byte-identical; where
text mode translates newlines, evaluated bytes may differ from written bytes. S1
pins the host OS and demonstrates equality (AC-23).

### 7.6 Memory selection after P2-first

P2-first is merged at `59309fe7` and the package version is unchanged. Every
implicit-discovery consumer uses one resolver,
`mneme.integrations.memory_selection.resolve_memory`
(`mneme/integrations/memory_selection.py:70-94`):

- the nearest `.mneme/project_memory.json` at or above the start **always governs**;
- `MNEME_MEMORY` no longer replaces or masks a discovered memory; it only fills an
  absence;
- the reason is one of `DISCOVERED`, `OVERRIDE_IGNORED`, `OVERRIDE_FILLS_ABSENCE`,
  `OVERRIDE_MISSING`, `NO_MEMORY_ON_PATH`;
- `walk` is `"unbounded"`: the walk has **no Git-repository marker check**.

`find_memory()` remains only as a compatibility wrapper returning `.path`
(`hook.py:207-213`); it carries no diagnostics. S1 records the full
`MemorySelection` reason and `walk` value, and does not infer a Git boundary the
resolver does not enforce. Boundary rows 3–5 remain reserved for D5 Phase 2 and are
never emitted (`memory_selection.py:9-10`).

Selection notices (rows `OVERRIDE_IGNORED`, `OVERRIDE_MISSING`) are defined for
Claude Code's probed shapes only. OpenCode has no defined notice channel, so S1
records the reason in its own diagnostics and does not invent a host notice.

Schema: `mneme.decision-index/v2` is required for decision applicability,
`FORBID_NUMERIC_ABOVE` and waivers, and 0.10.x refuses it
(`docs/releases/v0.11.0.md:33-38`). The S1 fixture declares none of those features.
No v2 memory is installed beside any reader at or below 0.10.x. Waivers are
recorded but not enforced by `mneme check` (DG1B2b deferred) and are absent from S1.

### 7.7 Mode selection

Mode is violation policy, not availability. `resolve_mode()` reads
`MNEME_HOOK_MODE`, then `CLAUDE_PLUGIN_OPTION_MODE`, then defaults to `strict`
(`hook.py:252-274`). The second variable is Claude-specific and must not be
silently inherited by an OpenCode process.

S1 therefore:

- removes `CLAUDE_PLUGIN_OPTION_MODE` from the environment before resolving mode, or
  refuses when it is present; the choice is recorded and tested;
- records the effective mode, the deciding source (`MNEME_HOOK_MODE` value or
  `default`), and whether a Claude-specific variable was present and suppressed;
- treats an unrecognized value as `strict`, matching the shared resolver;
- does not treat mode as an availability posture and does not derive a fail-closed
  policy from it.

### 7.8 Reuse: direct, guarded, normalization-dependent, forbidden

**Direct reuse** (host-neutral signatures):

| Symbol | Signature |
| --- | --- |
| `introduced_between` | `(before: str, after: str) -> str` |
| `assess_verdict` | `(stdout, returncode, requested_mode, *, expected_input)` |
| `format_reason` | `(payload: dict) -> str` |
| `format_applicability_reason` | `(payload: dict, *, routed_new_file=False) -> str` |
| `resolve_memory` | `(start: Path) -> MemorySelection` |
| `MemoryStore` | `(path) -> store` |
| `_invoke_check` | `(memory, rel_label, target_path, content, ...)` |

**Reuse with an OpenCode guard:** `resolve_mode` — reuse only after suppressing
`CLAUDE_PLUGIN_OPTION_MODE`, per §7.7.

**Reuse after normalization to `ToolEvent`** (`hook.py:51-56`; the pattern used by
Agent SDK, Antigravity, Kiro and Hermes):

| Symbol | Needed mapping |
| --- | --- |
| `_resolve_target` | host target path and host directory to `file_path` / `cwd` |
| `_direct_write_memory_start` | same `ToolEvent` |
| `introduced_content` / `_materialize_change` | same `ToolEvent`; `Write` reads current with `missing_ok=True` |

**Not reusable:** `parse_event` and `handle_event` (Claude envelope);
`discover_declaration` and `emit_availability` (`.claude` declaration and Claude
host semantics).

The OpenCode mapping mirrors Hermes (`mneme/integrations/hermes/adapter.py:227-235`).
No diff, verdict, path, mode or authority logic is reimplemented.

### 7.9 Authority pin and failure classification

`authority.json` asserts the expected `(decision_id, decision_version_id, rule_id)`
and rule value and scope against the projected decision. It is never a memory
selector, resolver, precedence source or policy input.

An identity mismatch is a **setup / authority-validation failure**
(`setup_invalid`), distinct from a rule violation, from an operational state and
from an unsupported tool. On mismatch the adapter evaluates nothing, reports
NOT_PROTECTED, and emits no Mneme verdict. Whether that refusal prevents the write
is an explicit charter decision; it is not a default and must not be introduced
silently as a new blocking policy.

### 7.10 Observation state, boundary disposition, applicability, evidence

Four axes. They are never collapsed.

| Axis | Values | Source |
| --- | --- | --- |
| Observation state | `TRUSTED_COMPLETE`, `COMPLETENESS_UNSTATED`, `INCOMPLETE`, `UNTRUSTED`, `NOT_RUN` | `classify_observation`, `mneme/integrations/claude_code/availability.py:90-107` |
| Boundary disposition | `EVALUATED`, `SKIPPED`, `REFUSED_SETUP_INVALID`, `UNSUPPORTED_TOOL`, `PLATFORM_DENIED`, `NOT_ATTEMPTED` | Caller decision |
| Rule applicability | `APPLIED`, `EXCLUDED`, `UNKNOWN` | ADR-020 |
| Evidence level | configured/validated, `EXECUTION_OBSERVED`, `RELEVANT_ENFORCEMENT_OBSERVED` | ADR-029 §1 and §2 |

`SKIPPED` is a caller-asserted boundary disposition, not a value returned by
`classify_observation`. The classifier returns only the five observation states
above; `SKIPPED` is validated separately against the availability state vocabulary
(`availability.py:23-26`). A skip is never an observation and never evidence.

Evidence rules:

- `EXECUTION_OBSERVED` (control) requires a trusted observation that the control
  ran. It does not require a PASS or a FAIL. An evaluated **`EXCLUDED`** rule is
  execution observed for the control, and is **never** relevant enforcement for that
  rule (ADR-029 §2).
- `EXECUTION_OBSERVED` (per rule) requires that rule to appear as `APPLIED` or
  `EXCLUDED` in the same observation.
- `UNKNOWN` applicability is an operational failure and yields no per-rule claim.
- `RELEVANT_ENFORCEMENT_OBSERVED` requires `APPLIED`, an attributable outcome and
  all six ADR-029 bindings. At this base it is reachable only through the pre-write
  hook, a `FORBID_NUMERIC_ABOVE` rule, a new-file `Write` and a pinned host
  (`docs/roadmap/README.md:72`; `relevant_enforcement_per_rule`). It is not reachable
  for literal rules on any surface and not reachable on OpenCode in S1.
- A skip, a missing hook, a tool denial, a platform denial, an unsupported payload
  and an unexecuted check are **not** execution observed.
- S1 records a claim only from a `TRUSTED_COMPLETE` observation. An `INCOMPLETE`
  payload is reported as such and is not promoted, even if one rule was `APPLIED`.

Availability and refusal are separate concerns:

| Concern | Mechanism | OpenCode S1 |
| --- | --- | --- |
| Verdict trust | `assess_verdict` (`hook.py:728`) | Reused; no local parser |
| Violation mode | `resolve_mode` | Reused with the §7.7 guard |
| Availability policy | ADR-033 §1 and §3 | Default `open`; `closed` is Claude-scoped and not claimed |
| Authorization | ADR-033 §4 | Not applicable; `.claude` declaration does not transfer |
| Host-level refusal | Host hook throw | Validated on the G0 host (2.3.0): throw aborts before mutation; re-verify per pin |

ADR-033 §3 scopes its matrix to Claude Code `PreToolUse` (§6), and §4 authorization
binds to the local `.claude` declaration (`availability.py:43`). OpenCode inherits
neither. Any `closed` posture requires its own charter and host validation.

### 7.11 Acceptance matrix

| ID | Case | Pass criterion | Claim | Status |
| --- | --- | --- | --- | --- |
| AC-01 | Build identity and pins | `(package_version, source_commit_or_wheel_sha256)` recorded; historical pins separate; S1 unknowns `TBD`; no secrets | Structural | S1 |
| AC-02a | Activation, positive | Independent launcher or observer confirms the plugin is present in the effective configuration and a real behavioural probe produces the expected hook effect; `plugin list` is not required to enumerate local plugins | Structural | S1 |
| AC-02b | Activation, negative | With the plugin disabled or unregistered, the **preflight** concludes NOT_PROTECTED from absent markers and config inspection; the hook is not expected to report on itself | Structural | S1 |
| AC-06 | Verified-absent literal block | Absence proof; complete content; corpus = 1 decision / 1 `FORBID_LITERAL` / no constraints / no anti-patterns; argv has no `--top`; no adapter filtering or memory rewrite; trusted FAIL; target still absent | Execution observed | S1 |
| AC-06b | Verified-absent compliant allow | Same assertions; trusted PASS; file created; functional PASS | Execution observed | S1 |
| AC-07 | End-to-end allow | PASS, applied, functional PASS; allow inferred, not per-rule | Execution observed | S1 |
| AC-08 | Scope and authority | APPLIED, EXCLUDED and UNKNOWN per rule; EXCLUDED never relevance; UNKNOWN operational | Execution observed | S1 |
| AC-09 | Operational state | State reported apart from verdict and applicability; INCOMPLETE not promoted | Operational | S1 |
| AC-10 | Disabled/omitted-plugin control | Same payload applied when the plugin is omitted from the isolated config; no hook effect observed | Behavioural | S1 |
| AC-11 | Unsupported surfaces | Documented; denial is not evaluation | — | S1 |
| AC-13 | Reproducibility | Traces, hashes, identities, build identity, evaluator version, manifests | — | S1 |
| AC-14 | Security | Credentials excluded; no unapproved egress and no sandbox-policy expansion; cleanup | — | S1 |
| AC-17 | Authority mismatch | `setup_invalid`; NOT_PROTECTED; no verdict; not an evidence level | Not evaluated | S1 |
| AC-18 | Schema dependency | Schema recorded; no mixed readers; no numeric or waiver features | Structural | S1 |
| AC-20 | Target exists at create time | Not treated as S1 | Not evaluated | S1 |
| AC-21 | Observable races | Four scenarios (target appears before evaluation; appears between evaluation and write; symlink introduced; hardlink substituted). Each outcome is `DETECTED` or `UNDETECTED_RACE`. `UNDETECTED_RACE` is a **failed race-resistance observation** and a documented bypass, counted in negative space and never summarized as protection. Aggregate `race_resistance` is `NOT_ESTABLISHED` if any scenario is undetected. No atomicity, no universal-detection and no create-if-absent claim | Failed observation, not a protection pass | S1 |
| AC-23 | Carrier byte fidelity | Evaluated bytes equal intended bytes on the pinned host | Structural | S1 |
| AC-25 | Path-authority isolation | Different process cwd, relative target and host directory produce identical resolution; no host directory means refusal, never adapter cwd | Structural | S1 |
| AC-26 | Memory-selection record | `reason` and `walk="unbounded"` recorded; ignored override visible in diagnostics | Structural | S1 |
| AC-27 | Host mutation-tool contract | Generation, host version, package, config key, registration form, exact tool identifier and payload shape recorded; complete content required; unknown identifier or hunk payload is unsupported; permission category alone is not coverage; activation proven by effective-config inspection plus a behavioural probe (`plugin list` is not accepted for local plugins) | Structural | S1 |
| AC-28 | Mode selection | Effective mode, deciding source and suppression of `CLAUDE_PLUGIN_OPTION_MODE` recorded and tested; unset means strict; unrecognized value means strict; mode is never treated as availability | Structural | S1 |
| AC-03/04/05 | Existing-file delta path | — | — | DEFERRED |
| AC-15/16 | Cross-repo and override probe | — | — | DEFERRED |
| AC-19 | Delta parity fixture | — | — | DEFERRED |
| AC-22 | Non-`.py` new file | — | — | DEFERRED |
| AC-24 | Numeric on OpenCode | — | — | DEFERRED |

### 7.12 Historical record and source status

Revision-1 §5 classifications are **frozen**. R11 graded only T3c, T3d, T4a and T4b
as trace-backed; the remainder stay C/D/E and are not PASS. The October run used
Claude Sonnet 5.5 and is historical evidence, never proof for DeepSeek V4.1.

The Step 1 source and evidence recovery is **locally reported, not independently
confirmed**. The experiment commit exists locally and an archive and bundle are
present locally; per-run `MANIFEST.sha256` files exist in the archive but were not
verified in this review, and the archive is a single local copy. No manifest, hash
or accessibility claim is asserted here.

### 7.13 Prerequisites

1. Independent verification of the recovered source and archive: hashes, manifests,
   accessibility and a second copy.
2. Independent confirmation of all S1 environment values in §7.2C, including host
   API generation, exact tool identifier and payload shape.
3. A merged implementation charter; a Layer 1 freeze amendment if behavior is added.
4. An explicit decision on authority-mismatch refusal behavior.
5. Host validation of OpenCode refusal semantics and activation preflight.
6. Confirmation that S1 needs no Core change; if it does, stop.

### 7.14 Out of scope for this revision

PR #609 (roadmap) is **not** modified, re-slotted or rebased here. The integration
support matrix is not changed. No experiment is re-run. No historical result is
reclassified.

**Revision-2 review question:** Is the verified-new-file literal path specified
precisely enough to be chartered later — with a payload-shape and tool-identifier
scope, a correct transport, path and mode authority, an honest four-axis evidence
model, no inherited fail-closed posture, no second engine, and every host and runtime
unknown marked `TBD` — while the historical experiment remains evidence, not a
baseline?

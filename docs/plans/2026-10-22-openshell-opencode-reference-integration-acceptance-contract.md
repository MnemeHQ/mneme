# OpenShell + OpenCode reference integration — acceptance contract

**Status:** PROPOSED — specification and acceptance-test plan only; **not implementation authorization**.
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

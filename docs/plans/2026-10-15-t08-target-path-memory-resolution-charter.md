# T-08 — Target-path memory resolution defect-correction charter

**Status:** **PROPOSED (draft).** This charter is a docs-only proposal. It is
**not** an implementation, **not** a Layer 1 freeze amendment, and **not** an
acceptance of ADR-033. Nothing below is authorized until this charter merges
**and** a matching `[layer1-freeze]` amendment merges after it (§9).
**Source anchor:** `MnemeHQ/mneme` `main` at
`2578a720a7d418dc4023a701bf5e8bfe0ef43171` (DG1F G3-B design, PR #512). Line
numbers below refer to that commit.
**Evidence:** [DG1F T-08 evidence record](../validation/dg1f-t08-cwd-memory-selection-2026-10-15.md)
and its [artifacts](../validation/artifacts/dg1f-t08-cwd-memory-selection-2026-10-15/),
added by draft PR #513 (`docs/dg1f-authorization-unverifiable-adversarial-spec`).
Those relative links resolve once #513 merges; until then, read them from that
branch. This charter must not merge before #513.
**Governing contracts:** [ADR-021](../adr/ADR-021-shell-preflight-and-stop-session-delta.md)
(fail-open transport policy, shell preflight, Stop session delta);
[ADR-017](../adr/ADR-017-enforcement-scope-vs-retrieval-scope.md) and
[ADR-020](../adr/ADR-020-explicit-path-applicability-for-typed-rules.md)
(strict/warn enforcement, policy root, rule-path applicability);
[ADR-023](../adr/ADR-023-canonical-decision-index-and-runtime-projection-boundary.md),
[ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md)
(canonical decision authority); the #260 verdict-coherence correction
(PR #484, `60b02af3`) under the merged
[C1 charter](2026-10-14-reliable-enforcement-c1-verdict-consistency-charter.md);
the [Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md).
**Kept separate:** proposed ADR-033 and the reliable-enforcement C0 charter
(draft PR #483); the [G3 missing-memory assessment](2026-10-14-dg1f-g3-missing-memory-eligibility-assessment.md)
and [G3-B design](2026-10-14-dg1f-g3b-eligibility-authorization-design.md).
This charter relies on none of them being accepted.

## 1. Problem (T-08)

`mneme/integrations/claude_code/hook.py` picks the governing decision memory
from the hook payload's `cwd`, never from the file being modified.
`find_memory` returns `MNEME_MEMORY` when it is set (or `None` when that file
does not exist), and otherwise walks up from the start directory to the first
`.mneme/project_memory.json`. The target path reaches `mneme check` only as
`--target-path`.

The evidence record establishes:

- **Offline, at hook level** (`repro_t08.py`, three identical runs): the same
  forbidden `Edit` to `repo_a/app.py` is blocked when the payload `cwd` is
  `repo_a` (V0), and silently permitted when the `cwd` is a sibling repository
  (V1), a directory with no memory (V2), a planted nested memory inside
  `repo_a` (V3), or when `MNEME_MEMORY` names a missing file (V4) or another
  repository's memory (V5).
- **Live, Claude Code 2.1.202 / Windows / `-p`** (probe L4): a session started
  in sibling `repo_b` with `--add-dir <repo_a>` made the forbidden edit to the
  protected `repo_a/app.py`. The hook selected `repo_b`'s permissive memory and
  exited 0 with no output, and the file landed at `4d581c93…`, the same bytes
  as the L2 counterfactual. The agent-steered `cd` pivot (V3 live, L1/L3) was
  **not** reproduced on that host.
- **Why nothing flagged it:** for a target outside the selected memory's
  policy root, `mneme check` returns a **complete, coherent PASS**
  (`evaluation_complete: true`, exit 0) when the memory has no path-scoped
  rules. Unscoped rules report `APPLIED` and swallow the
  `normalize_input_path` error (`mneme/path_selectors.py:216-241`). That result
  passes the #260 coherence wrapper, so the hook has no basis to distrust it.

This is a **defect in how the governing memory is identified**, not a change
to enforcement policy. The repository being changed is governed by whatever
memory happens to sit near the session's working directory.

## 2. Invariant

**Definitions.**

- **Resolved target:** the absolute, normalized path of the artifact a tool
  call would modify. Claude Code supplies absolute paths. A relative path is
  anchored to the payload `cwd` exactly as `_resolve_target`
  (`hook.py:494-500`) does today. That is path resolution, the only anchor the
  host gives; it is not memory selection.
- **Target repository root:** the nearest ancestor of the resolved target
  (starting at its nearest existing ancestor directory, because `Write` may
  create new files and directories) that holds a `.git` entry, either a
  directory or a file. A nested repository, submodule or linked worktree is its
  own repository.
- **Policy root:** as defined by ADR-020 (`mneme.path_selectors.policy_root`):
  the directory that holds `.mneme/`, or the parent of a non-standard memory
  file.
- **Governing memory:** the memory selected for a resolved target by the rules
  in §4.

**Invariant.** *The repository being modified, resolved from the target path,
determines the governing memory. The payload `cwd`, the session's launch
directory and the agent's shell working directory never select it.*

It has three testable parts:

- **I1 — selection.** Governing-memory selection is a function of the resolved
  target, plus `MNEME_MEMORY` under the §4 rules. The payload `cwd` may anchor
  a relative target (above) and may choose which working tree the Stop backstop
  enumerates (§3). It never chooses the memory that governs a file.
- **I2 — containment.** A memory never governs a target outside its policy
  root.
- **I3 — no false completeness.** No outcome in which the evaluated memory does
  not govern the target may be reported, by the hook or by `mneme check`, as a
  complete PASS.

## 3. Affected boundaries

All four Claude Code hook boundaries call `find_memory` with the payload `cwd`
on `main` @ `2578a720`. Each must go through one shared target-path resolution
function that implements §4. No boundary keeps a private discovery path.

| Boundary | Today | Required under this charter |
|---|---|---|
| **Direct write** (`Edit\|Write\|MultiEdit`), `handle_event`, `hook.py:1058` | `find_memory(Path(event.cwd or "."))` | Resolve memory from the resolved target that `_resolve_target` produces. The same resolved target is passed as `--target-path`. |
| **Bash class-A preflight**, `bash_tool_event`, `hook.py:644` | `find_memory(Path(event.cwd or "."))`, before the heredoc target is resolved | Resolve memory from the reconstructed heredoc target (`rec.target_path`, anchored as at `hook.py:648-650`). Do the resolution **after** target reconstruction. Classes B/C stay pass-through with the existing trace (ADR-021). |
| **SessionStart**, `session_start_event`, `hook.py:706` | `policy_root(find_memory(cwd))` picks the baseline root | The baseline root is the **repository root containing the payload `cwd`** (§2 definition), not the policy root of whichever memory is nearest to `cwd`. A planted nested memory in the launch directory must not shrink the baseline to its subtree. If no repository root exists, current behavior is preserved. |
| **Stop**, `stop_event`, `hook.py:853` | `policy_root(find_memory(cwd))` picks both the enumerated tree and the single memory used for every changed file | Enumerate the same repository root as SessionStart. **Each changed file** in the session delta is evaluated against the memory §4 resolves for **that file**. A file with no governing memory follows the existing no-memory path, and the existing disclosure of unevaluated changes stays. |

**Stop scope note.** The Stop envelope carries no target. Using the payload
`cwd` to choose *which working tree's delta is audited* is a coverage decision,
not a memory-selection decision, and I1 permits it. Mutations in directories
outside that tree, such as an `--add-dir` directory in L4, stay **outside Stop
coverage**. That is an existing coverage limit, disclosed here and not changed
by this charter (§8). Under this charter the L4 edit is caught at the
**direct-write** boundary, because target-path resolution selects `repo_a`'s
memory, as long as some hook registration fires in that session.

## 4. Memory discovery and `MNEME_MEMORY`

### 4.1 Resolution rules

- **R1 — repository first.** Compute the target repository root (§2) from the
  resolved target alone: a deterministic, offline, read-only filesystem
  resolution. The implementation may use `git rev-parse --show-toplevel` run
  against the target's directory or an equivalent walk, but it must not consult
  the payload `cwd` or the process working directory.
- **R2 — outermost memory within the repository governs.** The candidates are
  the `.mneme/project_memory.json` files on the ancestor chain from the
  target's directory up to and including the repository root. The candidate
  **closest to the repository root** governs. Nested candidates below it are
  ignored, with a diagnostic (§4.3). This closes V3 in both directions: a memory
  planted inside a governed repository cannot govern files elsewhere in it
  (target anchoring) or files beneath it (outermost rule). If the repository
  root has no memory, the outermost nested candidate on the chain governs.
- **R3 — never cross the repository boundary.** A memory above the repository
  root, such as a parent directory's `.mneme/`, never governs a target inside
  the repository. If one exists it is ignored, with a diagnostic. A repository
  with no memory of its own stays on the **existing missing-memory path**
  (fail-open, S1). It does not fall through to a parent's memory. This removes
  the parent-directory fallback that G3 §4.2 identified.
- **R4 — targets outside any repository.** With no repository identity, the
  governing memory is the **nearest** `.mneme/project_memory.json` walking up
  from the target's directory. This is today's walk, re-anchored on the target
  instead of the `cwd`, and it keeps the non-git layouts existing tests use.
  Diagnostics mark repository identity as unresolved. Shadowing protection (R2)
  does not exist outside a repository; that residual risk is recorded, not
  closed.
- **R5 — `MNEME_MEMORY` is a bounded override.**
  - **(a)** If the target's repository (or, under R4, its non-git tree) has a
    governing memory under R2/R4 at a different path, **that memory governs**.
    The override is ignored, with a diagnostic. This covers V4 and V5.
  - **(b)** If there is no discovered memory, the override file exists, and the
    resolved target lies inside `policy_root(override)`, the override governs.
    This keeps harness and test uses that supply memory to a repository that
    has none.
  - **(c)** If there is no discovered memory, the override file exists, and the
    resolved target lies **outside** `policy_root(override)`, the outcome is
    operational: **target outside memory policy root**. It fails open under
    ADR-021, is never a complete PASS (I3), and gives a diagnostic.
  - **(d)** If there is no discovered memory and the override file does not
    exist, the existing missing-memory path applies, plus a diagnostic that the
    override is invalid. Eligibility does not change.
- **R6 — one function, defense in depth.** The hook resolves memory once per
  target and never asks `mneme check` to evaluate a target outside the selected
  memory's policy root. `mneme check` enforces I2 independently (§5), so a
  stale or bypassed hook still cannot produce a complete PASS for an
  out-of-root target.

**Compatibility consequences, accepted and disclosed:** a repository that
combines a root memory with nested "specializing" memories is not a documented
layout and gets root-memory governance (R2). Multi-memory composition is not
authorized (§8). A parent directory memory that used to govern several child
repositories through the `cwd` walk no longer does (R3); that cross-repository
use is outside the Layer 1 scope ("local-repo, project-scoped"). Existing tests
that pin `cwd`-based selection, for example
`tests/integrations/claude_code/test_memory_discovery.py`, characterize the
defect. The implementation PR must update each one explicitly with its
justification, not silently.

### 4.2 Reconciling G3 §4.3 with proposed ADR-033 §4.1

**What each says.** G3 §4.3(5)(i) requires that any future eligibility change
bind its witness to the **intended repository root and effective memory path**,
and its failure-mode note requires a `MNEME_MEMORY` override false negative to
fall back to *inactive*, never to a fabricated pass. Proposed ADR-033 §4.1
would have an availability declaration bind **repository identity and the exact
effective memory path**. Under it, "a differing `MNEME_MEMORY`, missing
expected file, or parent-directory discovery result cannot bypass the
established binding", and a mismatch is "an operational problem, not a
downgrade to 'unprotected'".

**What this charter is.** It supplies only the deterministic resolution
*target → repository root → effective memory path* that both documents
presuppose. It creates **no** declaration, witness, trusted revision,
authorization binding or availability state, and it decides nothing about
fail-closed behavior. It is therefore **not** an eligibility change in G3's
sense. It satisfies the precondition G3 §4.3(5)(i) names without needing G3-B
or ADR-033, and it holds whether ADR-033 is later accepted, amended or rejected.

**Adopted on this charter's own evidence, not on ADR-033's authority:**
no parent-directory memory across a repository boundary (R3; G3 §4.2, V-series
fixture), and no displacement of the repository's own memory by
`MNEME_MEMORY` (R5a; G3 lists the variable as W5, non-durable caller
environment; V4/V5 evidence).

**Deliberately not adopted:** ADR-033's operational *refusal*, `closed`
handling, "removed/tampered without approval" classification, and the
activated-versus-authorized distinction. Missing memory keeps today's behavior
(G3 §5 non-authorization).

**Where they differ, and why that is safe.** On an override mismatch, ADR-033
§4.1 (proposed) classifies the result as operational for **availability**.
R5a resolves which memory **evaluates** in favor of the repository's own memory
and adds a diagnostic. These answer different questions. R5a only makes
enforcement stricter than today, and it does not foreclose ADR-033: if ADR-033
is accepted later, its verifier checks that the R1–R5 result matches the
declared binding and layers its availability outcome on top. Nothing in this
charter would need to be undone.

### 4.3 Diagnostics

Every ignored candidate (nested memory under R2, ancestor memory under R3,
override under R5a/R5d) and every R5c operational outcome writes a diagnostic
to the hook's existing stderr channel. It names the resolved target, the
selected memory and the ignored path or reason. Diagnostics never echo
proposed content (the C1 rule) and never change a verdict. Making PreToolUse
diagnostics visible to the agent is not authorized (§8).

## 5. `mneme check`: target outside the policy root is operational

When `--target-path` is supplied and the resolved target lies outside
`policy_root(--memory)` (ADR-020), `mneme check` must **not** report a complete
result:

- `evaluation_complete: false`, and under `--json` exit 2, the existing
  incomplete-result convention, in both `strict` and `warn` modes;
- regardless of whether any rule would have matched, and specifically for
  memories with no rules or only unscoped rules (the V1/L4 case, which
  produces no applicability trace today);
- with a named reason visible to the caller, for example
  `TARGET_OUTSIDE_POLICY_ROOT`.

When only `--input` is given, behavior is **unchanged**. The input file is
proposed content, often a temporary file, and not necessarily the governed
artifact. This keeps the hook's temp-file invocation and ordinary CLI use
intact.

**Payload representation (bounded).** Use existing `mneme.check/v1` fields if
they can carry the reason. If they cannot, which is likely for rule-less
memories, **one strictly additive, optional field** within `mneme.check/v1`
(no version bump) is authorized to carry the operational reason. It is
authorized only on these conditions: `tests/integrations/check_contract.py` is
updated in the same PR, and the `[layer1-freeze]` amendment names the field.
No other payload change is authorized.

**#260 coherence (required).** Today `_verdict_inconsistency`
(`hook.py:342-355`) treats `evaluation_complete: false` with no `UNKNOWN`
applicability trace as **incoherent**. Left alone, the new outcome would fail
open under the misleading "inconsistent verdict payload" diagnostic. The rule
must be extended to: *incomplete if and only if an `UNKNOWN` trace exists **or**
the target-scope operational reason is present*. No other #484 rule may be
loosened, and a payload that claims the reason while reporting
`evaluation_complete: true` must be judged incoherent.

## 6. Explicitly preserved

1. **Default fail-open (ADR-021).** Every outcome this charter introduces,
   whether out-of-root, invalid override, unresolved identity or missing
   memory, **fails open** with a diagnostic. No fail-closed, `closed`, or
   availability-strict behavior is introduced.
2. **The #260 coherence wrapper (PR #484).** `assess_verdict` stays the only
   gate through which a `mneme check` result is trusted. This charter adds one
   coherent-incomplete case (§5) and nothing else. Contradictory results still
   fail open, and the full #484 test set stays green unmodified apart from the
   new case.
3. **strict/warn semantics (ADR-017, ADR-020).** Complete in-root verdicts keep
   existing enforcement. Path-selector semantics for in-root targets are
   unchanged.
4. **Canonical decision authority and evidence identity** (ADR-023, ADR-029,
   ADR-030, ADR-031). Untouched.
5. **Retrieval, ConflictDetector, enforcer, rule matching.** Untouched.
6. **CLI exit codes for complete results**, and the `mneme.check/v1` payload
   apart from the single bounded field in §5.
7. **Hook registration, shell classes B/C pass-through, and Stop's disclosure
   of unevaluated changes.** Untouched.
8. **Frozen benchmark fixtures and methodology; `.mneme/project_memory.json`.**
   Untouched.

## 7. Regression tests and required acceptance evidence

Before any implementation merges, show all of the following.

### 7.1 Offline: port the reproducer

Add `tests/integrations/claude_code/test_hook_target_memory_resolution.py`.
It reuses the fixture and the V0–V5 envelopes of
[`repro_t08.py`](../validation/artifacts/dg1f-t08-cwd-memory-selection-2026-10-15/repro_t08.py)
and drives the **real** `hook.main` and the **real** `mneme check` in disposable
`tmp_path` repositories, with no mocks. Every case asserts the selected memory,
the hook exit code and the diagnostics. The edit is never applied by the test,
so file hashes do not stand in for prevention.

| Case | Setup | Required outcome |
|---|---|---|
| V0 control | `cwd` = `repo_a` | `repo_a` memory; exit 2; `T08-DEC` (unchanged) |
| V1 | `cwd` = sibling `repo_b` | `repo_a` memory; **exit 2**; `T08-DEC` |
| V2 | `cwd` = directory with no memory | `repo_a` memory; **exit 2** (memory exists for the target, so this is not an eligibility change) |
| V3 | `cwd` = `repo_a/vendor_tools` (planted) | `repo_a` memory; **exit 2**; nested-memory diagnostic |
| V4 | `MNEME_MEMORY` → missing file, `repo_a` memory present | `repo_a` memory; **exit 2**; override diagnostic (R5a) |
| V5 | `MNEME_MEMORY` → `repo_b` memory | `repo_a` memory; **exit 2**; override diagnostic (R5a) |
| V6 | forbidden edit to `repo_a/vendor_tools/x.py` | `repo_a` memory (R2 outermost); exit 2 |
| V7 | memory only above an unprotected repository | no memory; exit 0; ancestor diagnostic (R3; S1 unchanged) |
| V8 | `MNEME_MEMORY` set, no repository memory, target inside override root | override governs (R5b) |
| V9 | `MNEME_MEMORY` set, no repository memory, target outside override root | operational, exit 0, never PASS, diagnostic (R5c) |
| V10 | reverse: `cwd` = protected `repo_a`, edit to sibling `repo_b` | `repo_b` memory; `repo_a` rules no longer applied to `repo_b` |
| V11 | relative `file_path` with `cwd` = `repo_a` | resolves to the `repo_a` target; same as V0 |
| V12 | target in a nested repository or linked worktree (`.git` file) | the nested repository's own memory (R1) |

Also required:

- **Bash class A:** V0–V5 repeated with a quoted-heredoc write to
  `repo_a/app.py`; same outcomes. Classes B/C unchanged.
- **SessionStart/Stop:** a session whose `cwd` is `repo_a/vendor_tools`
  (planted memory) gets a baseline of the whole `repo_a`, and a forbidden delta
  in `app.py` is evaluated against `repo_a`'s memory and blocked at Stop. A
  session whose `cwd` is `repo_b` does not report `repo_a` changes as audited;
  assert non-coverage, never a pass.
- **`mneme check`:** with `--target-path` outside the policy root, the result is
  `evaluation_complete: false`, exit 2 and the named reason, in strict and warn
  modes, for rule-less, unscoped-only and path-scoped memories. With `--input`
  only, results are byte-identical to `main`.
- **Coherence:** `assess_verdict` treats the §5 outcome as coherent-incomplete
  (fail open, correct diagnostic). A payload that claims the reason with
  `evaluation_complete: true` is incoherent. The existing
  `test_hook_verdict_consistency.py` cases are unchanged.
- **Determinism:** three consecutive runs give identical results, as in the
  evidence record.
- **Battery:** the full canonical suite and gate battery are green; the frozen
  benchmark is unchanged (7/7 scenarios, Layer 2 pass rate 100%); and there is
  no change to any §6 item.

### 7.2 Live re-probe matching L4

Offline results do not stand in for live confirmation, and live results do not
stand in for offline ones. After implementation, and before any claim that the
defect is closed on a host, re-run the L4 configuration with the T-08
harness. Record the result as a new validation record; it must not edit #513's
record.

- **Configuration:** Claude Code **2.1.202** on Windows with `claude -p …
  --output-format stream-json --verbose --setting-sources project
  --permission-mode acceptEdits`, run from the operator's terminal. If 2.1.202
  is unavailable, record the version actually used and do not claim
  equivalence.
- **Invocation:** the unmodified implementation hook through
  `live/harness/hookwrap.py`; fresh disposable repos; strict mode;
  `MNEME_HOOK_MODE`, `CLAUDE_PLUGIN_OPTION_MODE` and `MNEME_MEMORY` unset.
- **Setup:** protected `repo_a`; session **started in sibling `repo_b`**
  (permissive memory, hook registered) with `--add-dir <repo_a>`; the L4 prompt
  verbatim.
- **Pass criteria:** the hook log shows `repo_a`'s memory selected for the Edit
  (payload `cwd` still `repo_b`); hook exit 2 with `T08-DEC`; the host
  `tool_result` refuses the edit; `repo_a/app.py` is still `444af21e…` and the
  protected memory is still `aae2456a…` (E1 harness oracle, outside the agent
  session); `events.selected.jsonl` is preserved (E2).
- **Controls:** re-run L0 (still blocked) and L2 (permissive memory: the edit
  still applies, which proves there is no over-blocking).
- **Scope of the claim:** that configuration only. Interactive sessions, other
  versions, other providers, and the agent-steered `cd` pivot (V3 live) remain
  unclaimed.

## 8. Explicitly NOT authorized

- **Implementation by this charter.** Nothing is authorized until this charter
  and its `[layer1-freeze]` amendment have both merged (§9).
- **Any Layer 1 freeze amendment in this PR.** The amendment is a separate PR.
- **ADR-033** acceptance, availability states, `closed`/fail-closed behavior,
  operational refusal, or any availability policy. **#483 stays separate and
  proposed.**
- **Missing-memory eligibility, witnesses, declarations or trusted baselines**
  (G3, G3-B), and any new authority store or marker file.
- **Hook registration or coverage changes,** including making a registration
  that exists only in `repo_a` fire in a session rooted elsewhere (L4 limit),
  and extending Stop to `--add-dir` or other additional directories.
- **Other integrations** that select memory from `cwd` or a project directory:
  `codex_cli/gate.py:155`, `codex_cli/stop_audit.py:123`, `kiro/hook.py:298`,
  `antigravity/adapter.py:242`, `agent_sdk/adapter.py:336`,
  `hermes/adapter.py:256`. Each needs its own scoping. This charter covers the
  Claude Code hook and `mneme check` only.
- **Multi-memory composition** (union or precedence across nested memories)
  and any new supported nested-memory layout.
- **Agent-visible PreToolUse diagnostics** or any new host output surface.
- Any `mneme.check/v1` change beyond the single bounded field in §5, any new
  schema, CLI flag or MCP surface, and any new engine.
- Changes to retrieval, the enforcer, rule matching, the frozen benchmark, or
  `.mneme/project_memory.json`.
- DG1F-C1b applicability exclusion; DG1B2 waivers.
- Any claim of host prevention beyond the re-probed configuration, and any
  claim about the agent-steered `cd` pivot.

## 9. Layer 1 freeze authorization (required, not made here)

This correction changes how the enforcement boundary picks the memory it
enforces, so the Layer 1 freeze requires prior authorization. After this
charter merges, a separate `[layer1-freeze]` amendment under Amendment
Procedure §3(b) must reference it. That amendment authorizes **only** §3–§5,
names the §5 payload field if one is used, and restates §6 as preserved. It
does not authorize enforcement-scope, availability or coverage changes.

## 10. Sequence

1. **Pending:** merge #513 (T-08 evidence), so that §1 and §7 cite merged
   artifacts.
2. **Pending:** review and merge this charter.
3. **Pending:** merge the matching `[layer1-freeze]` amendment.
4. **Pending:** implement §3–§5 in one PR, with the §7.1 tests, squash-merged
   under ADR-022.
5. **Pending:** run the §7.2 live re-probe and record it as a separate evidence
   PR.

**ADR-033 remains proposed; C1b remains locked; DG1B2 remains evidence-gated.**

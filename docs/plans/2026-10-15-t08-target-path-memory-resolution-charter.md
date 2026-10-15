# T-08 — Direct-write target-path memory anchoring (slice 1) defect-correction charter

**Status:** **PROPOSED (draft).** This charter is a docs-only proposal. It is
**not** an implementation, **not** a Layer 1 freeze amendment, and **not** an
acceptance or change of ADR-033. Once accepted, it authorizes **only slice 1**
(§3), and only after a matching `[layer1-freeze]` amendment merges (§10).
Everything else T-08 touches is deferred to separately gated follow-ups (§8).
**Source anchor:** `MnemeHQ/mneme` `main` at
`2578a720a7d418dc4023a701bf5e8bfe0ef43171` (DG1F G3-B design, PR #512). Line
numbers below refer to that commit. #513 merged as `98dc4771` and changed only
documentation, so `mneme/` is identical at both commits.
**Evidence:** [DG1F T-08 evidence record](../validation/dg1f-t08-cwd-memory-selection-2026-10-15.md)
and its [artifacts](../validation/artifacts/dg1f-t08-cwd-memory-selection-2026-10-15/),
added by PR #513, merged to `main` as `98dc4771`.
**Governing contracts:** [ADR-021](../adr/ADR-021-shell-preflight-and-stop-session-delta.md)
(fail-open transport policy);
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

`mneme/integrations/claude_code/hook.py` selects the governing decision memory
from the hook payload's `cwd`, never from the file being modified. `find_memory`
(`hook.py:187-199`) returns `MNEME_MEMORY` when that variable is set, or `None`
when the file it names does not exist. Otherwise it walks up from its start
directory to the first `.mneme/project_memory.json`. The target path reaches
`mneme check` only as `--target-path`.

**Evidence status by variant**, from the evidence record:

| Variant | Offline (`repro_t08.py`, 3 identical runs) | Live (Claude Code 2.1.202 / Windows / `-p`) |
|---|---|---|
| V0 control (`cwd` = `repo_a`) | blocked | L0: blocked |
| **V1 sibling-repo `cwd`** | silent permit | **L4: CONFIRMED.** The forbidden edit landed in protected `repo_a` (`4d581c93…`, the same bytes as the L2 counterfactual), governed by `repo_b`'s memory with a complete PASS and no diagnostic. |
| V2 `cwd` with no memory | silent permit (known S1) | not run |
| V3 planted nested memory as `cwd` | silent permit | **not reproduced.** The `cd` did not persist (L3), and the agent declined the chain (L1). |
| V4 `MNEME_MEMORY` → missing file | silent permit (known G3 §4.2) | not run |
| V5 `MNEME_MEMORY` → other repo's memory | silent permit | not run |

The silent permit happens because, for a target outside the selected memory's
policy root, `mneme check` returns a complete, coherent PASS when the memory has
no path-scoped rules. Unscoped rules report `APPLIED` and swallow the
`normalize_input_path` error (`mneme/path_selectors.py:216-241`). That result
passes the #260 coherence wrapper.

**Only the direct-write path (V1/L4) is live-confirmed.** This charter
therefore corrects only that path. All other surfaces and discovery-policy
questions are deferred, each with its evidence status (§8).

## 2. Invariant and slice-1 guarantee

**Long-run invariant (direction, not fully delivered here).** The repository
being modified, resolved from the target path, determines the governing
memory. The payload `cwd` never does.

**Slice-1 guarantee (what this charter delivers).** At the **direct-write
boundary** (`Edit|Write|MultiEdit`), the existing memory-discovery walk starts
at the **resolved target**, not at the payload `cwd`. Discovery semantics are
otherwise unchanged. With `MNEME_MEMORY` unset, the payload `cwd` no longer
selects memory for a direct write.

Slice 1 does **not** deliver the full invariant. Nested-memory shadowing (V6),
`MNEME_MEMORY` override cases (V4/V5), and the Bash, SessionStart and Stop
boundaries stay as they are on `main` (§5, §8).

## 3. Authorized change: slice 1, direct write only

**Boundary:** `handle_event`, `hook.py:1058`, which today calls
`find_memory(Path(event.cwd or "."))`.

**Change:** call the **existing, unmodified** `find_memory` with a start
directory derived from the resolved target:

1. Resolve the target exactly as `_resolve_target` (`hook.py:494-500`) does
   today. A relative `file_path` is anchored to the payload `cwd`. That is path
   resolution, the only anchor the host provides; it is not memory selection.
2. Fully resolve that path with `Path(target).resolve()` (non-strict), so a
   final-component symlink is followed, and start the walk at its **parent
   directory**. Anchoring on the fully resolved path is what makes the §4
   containment argument hold for symlinked targets.
3. Pass the same resolved target to `mneme check` as `--target-path`, as today.

**Discovery semantics: unchanged.**

- The nearest `.mneme/project_memory.json` walking up from the start directory
  governs, including today's fallback to parent directories outside a
  repository.
- `MNEME_MEMORY` precedence is unchanged. When it is set, it wins exactly as
  today, regardless of the start directory.
- No repository-root or `.git` detection, and no outermost-memory rule.
- `find_memory` itself is not modified, so
  `tests/integrations/claude_code/test_memory_discovery.py` stays valid as is.

**Write into a not-yet-existing directory.** A `Write` may create
`repo_a/new_pkg/deep/mod.py` when `new_pkg/` does not exist yet. The walk must
still reach `repo_a/.mneme/`. The current `find_memory` uses non-strict
`resolve()` and `is_file()` checks that are false for missing paths, so it
already walks through non-existent levels. The implementation must **prove
this with a test** (§7) rather than rely on it.

**No resolvable target.** If `_resolve_target` yields no target (no
`file_path`), behavior is unchanged from `main` and is pinned by a
characterization test. The same applies to a relative target with an empty
payload `cwd`.

No other code path is authorized.

## 4. Why slice 1 needs no `mneme check`, payload, or #260 change

**Claim.** With `MNEME_MEMORY` unset and a non-empty resolved target `T`, the
direct-write path cannot ask `mneme check` to evaluate a target outside the
selected memory's policy root. The out-of-root complete PASS behind V1/L4
therefore cannot arise on this path after slice 1.

**Argument, by construction:**

1. The walk starts at `S = resolve(T).parent` and returns
   `C/.mneme/project_memory.json` for some directory `C` that is `S` or one of
   its ancestors (`hook.py:192-199`).
2. For a memory discovered under that name, ADR-020's `policy_root` is exactly
   `C` (`mneme/path_selectors.py:155-160`).
3. `mneme check` normalizes the target as `resolve(T).relative_to(C)`
   (`normalize_input_path`, `path_selectors.py:163-180`). That succeeds because
   `C` is an ancestor of `resolve(T)`. Both sides use the same `Path.resolve()`,
   which is why §3 step 2 anchors on the fully resolved path.
4. So applicability normalization never hits the "outside policy root" error
   that unscoped rules swallow. A rule-less or unscoped memory now produces a
   PASS that is truthful for a target it actually governs.

**What still produces the out-of-root PASS:** only the `MNEME_MEMORY` override
(V5) and the non-direct-write boundaries. Both stay unchanged and are deferred
(§8: D3, D6).

**Consequently slice 1 makes no change to:** the `mneme check` CLI or its exit
codes; the `mneme.check/v1` payload (no new field); or the #260 coherence rules
in `_verdict_inconsistency` / `assess_verdict`. The §7 tests assert the
containment property directly, so that a later regression in this argument
fails a test instead of reopening the bypass silently.

## 5. Behavior consequences of slice 1 (accepted and disclosed)

| Case | `main` | After slice 1 | Status |
|---|---|---|---|
| V0 `cwd` = `repo_a` | `repo_a` memory, blocked | unchanged | control |
| **V1** `cwd` = sibling `repo_b` | `repo_b` memory, silent permit | **`repo_a` memory, blocked** | **fixed (live-confirmed defect)** |
| **V2** `cwd` with no memory | no memory, silent permit | **`repo_a` memory, blocked** | fixed as a side effect. Memory exists for the target, so this is not an eligibility change. |
| **V3** `cwd` = `repo_a/vendor_tools` (planted), edit to `repo_a/app.py` | planted memory, silent permit | **`repo_a` memory, blocked** | closed **only for targets outside the planted subtree** |
| V6 edit **under** `repo_a/vendor_tools/` | planted memory governs | **unchanged**: the nearest walk still selects the planted memory | deferred (D4) |
| V4 `MNEME_MEMORY` → missing file | silent permit | **unchanged** | deferred (D6) |
| V5 `MNEME_MEMORY` → `repo_b` memory | silent permit, complete PASS | **unchanged** | deferred (D3, D6) |
| **V10 reverse:** `cwd` = protected `repo_a`, edit to sibling `repo_b` or to a file outside any memory | `repo_a` rules applied to the other repository's file | the other repository's memory governs, or **no memory** (silent permit, as for any ungoverned file) | **accepted narrowing** |

**On V10.** A session rooted in protected `repo_a` no longer imposes
`repo_a`'s rules on edits to other repositories or to ungoverned files. That
narrows governance to the repository being modified, as the invariant
requires. It does **not** extend `repo_a`'s rules into multi-repository
governance, which Layer 1 excludes ("local-repo, project-scoped"). Operators
who relied on cross-repository blocking through the session `cwd` lose it, and
the implementation PR's release notes must say so.

**Existing tests.** Any direct-write test that pins `cwd`-based selection for a
target outside the `cwd` memory's tree characterizes the defect. The
implementation PR must update each one explicitly, with its justification in
the PR body. A pre-charter scan of `tests/integrations/claude_code/`
(`test_hook_main.py`, `test_hook_e2e.py`, `test_hook_verdict.py`,
`test_hook_verdict_consistency.py`, `test_hook_introduced_delta.py`) found
fixtures that put the target inside the `cwd` memory's tree. Those should be
unaffected, but the scan was not exhaustive, and the implementation PR must
confirm it.

## 6. Explicitly preserved

1. **Default fail-open (ADR-021).** Every untrusted, incomplete, missing-memory
   or error outcome still fails open. No fail-closed or availability behavior
   is introduced.
2. **The #260 coherence wrapper (PR #484).** `assess_verdict` stays the only
   gate through which a result is trusted. Its rules are unchanged, and the
   #484 test set stays green unmodified.
3. **Discovery semantics (`find_memory`)**, including `MNEME_MEMORY`
   precedence and the parent-directory fallback.
4. **strict/warn semantics (ADR-017, ADR-020)** and path-selector semantics.
5. **The `mneme check` CLI, the `mneme.check/v1` payload, and exit codes.**
6. **Bash (`:644`), SessionStart (`:706`) and Stop (`:853`)** behavior.
7. **Canonical decision authority and evidence identity** (ADR-023, ADR-029,
   ADR-030, ADR-031); retrieval, ConflictDetector, the enforcer, rule matching.
8. **Frozen benchmark fixtures and methodology; `.mneme/project_memory.json`.**

## 7. Required acceptance evidence (slice 1)

### 7.1 Offline

Add `tests/integrations/claude_code/test_hook_target_memory_resolution.py`. It
ports the fixture and envelopes of
[`repro_t08.py`](../validation/artifacts/dg1f-t08-cwd-memory-selection-2026-10-15/repro_t08.py)
and drives the **real** `hook.main` and the **real** `mneme check` in
disposable `tmp_path` repositories, with no mocks and with `MNEME_HOOK_MODE`,
`CLAUDE_PLUGIN_OPTION_MODE` and `MNEME_MEMORY` cleared unless a case sets them.
Each case asserts the memory used, the hook exit code and the stderr content.
The test never applies the edit, so file hashes are not prevention evidence.

**Fixed by slice 1:**

| Case | Setup | Required outcome |
|---|---|---|
| V0 | `cwd` = `repo_a`, edit `repo_a/app.py` | `repo_a` memory; exit 2; `T08-DEC` |
| V1 | `cwd` = sibling `repo_b` | `repo_a` memory; exit 2; `T08-DEC` |
| V2 | `cwd` = directory with no memory | `repo_a` memory; exit 2 |
| V3 | `cwd` = `repo_a/vendor_tools` (planted), edit `repo_a/app.py` | `repo_a` memory; exit 2 |
| V10a | `cwd` = `repo_a`, forbidden content to `repo_b/x.py` | `repo_b` memory; exit 0 (`repo_a` rules not applied) |
| V10b | `cwd` = `repo_a`, forbidden content to a file outside any memory | no memory; exit 0; `mneme check` not invoked |
| V11 | relative `file_path`: `app.py` with `cwd` = `repo_a`, and `../repo_a/app.py` with `cwd` = `repo_b` | `repo_a` memory; exit 2 |
| New directory | `Write` of `repo_a/new_pkg/deep/mod.py` (directories absent) with forbidden content, `cwd` = `repo_b` | `repo_a` memory; exit 2 |
| Symlink (skipped where unsupported) | `repo_a/link.py` → file in `repo_b` | memory selected from the resolved target's tree (`repo_b`) |

**Containment property.** For every case above in which a memory is selected,
assert that `policy_root(selected)` is an ancestor of `resolve(target)`, and
that the payload has no applicability reason of the "outside policy root"
kind.

**Asserted UNCHANGED from `main` (characterization, not fixed):**

| Case | Required outcome |
|---|---|
| V4 `MNEME_MEMORY` → missing file | no memory; exit 0 (as on `main`) |
| V5 `MNEME_MEMORY` → `repo_b` memory | `repo_b` memory; exit 0; complete PASS (as on `main`) |
| V6 edit under `repo_a/vendor_tools/` | planted memory; exit 0 (as on `main`) |
| Bash class-A heredoc to `repo_a/app.py` with `cwd` = `repo_b` | as on `main` (deferred, D1) |
| No `file_path` / relative target with empty `cwd` | as on `main` |

**Also required:** three consecutive runs give identical results; the full
canonical suite and gate battery are green; the frozen benchmark is unchanged
(7/7 scenarios, Layer 2 pass rate 100%); `test_memory_discovery.py` and the
#484 tests are unchanged; and there is no change to any §6 item.

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
- **Invocation:** the implemented hook through `live/harness/hookwrap.py`;
  fresh disposable repos; strict mode; `MNEME_HOOK_MODE`,
  `CLAUDE_PLUGIN_OPTION_MODE` and `MNEME_MEMORY` unset. If `hookwrap.py`
  computes its own logged memory from the payload `cwd`, update it to log the
  memory the hook actually used. Logging must not alter the decision.
- **Setup:** protected `repo_a`; session **started in sibling `repo_b`**
  (permissive memory, hook registered) with `--add-dir <repo_a>`; the L4 prompt
  verbatim.
- **Pass criteria:** the hook used `repo_a`'s memory for the Edit (payload
  `cwd` still `repo_b`); hook exit 2 with `T08-DEC`; the host `tool_result`
  refuses the edit; `repo_a/app.py` is still `444af21e…` and the protected
  memory is still `aae2456a…` (E1 harness oracle, outside the agent session);
  `events.selected.jsonl` is preserved (E2).
- **Controls:** re-run L0 (still blocked) and L2 (permissive memory: the edit
  still applies, which proves there is no over-blocking).
- **Scope of the claim:** that configuration only. Interactive sessions, other
  versions, other providers, and the agent-steered `cd` pivot remain
  unclaimed.

## 8. Deferred, separately gated follow-ups

None of these is authorized by this charter. Each needs **its own charter, or a
reviewed amendment to this one, plus its own `[layer1-freeze]` amendment**. If
slice-1 testing shows that one of them must ship with slice 1, implementation
stops, and this charter is amended (and reviewed) with that item's
justification before it ships. It is never folded in silently.

| ID | Follow-up | Evidence status | Why it is gated |
|---|---|---|---|
| D1 | **Bash class-A preflight** (`hook.py:644`): select memory from the reconstructed heredoc target, after reconstruction | **none.** Code inspection shows the same `cwd` call; not reproduced offline or live | No reproduction. Memory resolution happens before target reconstruction, so the change reorders the class-A path, which needs its own tests. |
| D2 | **SessionStart / Stop** (`:706` / `:853`): baseline root and per-file memory for the session delta | **none.** Code inspection only. The L4 edit was outside Stop coverage anyway. | Changes what the session-delta backstop enumerates and how many memories one Stop evaluation uses. This is a coverage and semantics change, not a selection fix. |
| D3 | **`mneme check` out-of-policy-root operational outcome**, any `mneme.check/v1` field to carry its reason, and the matching **#260 coherence extension** (today `evaluation_complete: false` with no `UNKNOWN` trace is judged incoherent, `hook.py:351-355`) | **offline** (V1/V5 direct checker PASS) and **live post-hoc** (L4 checker PASS) | Unreachable on the slice-1 direct-write path (§4). Remains reachable through D6 and D1/D2. Touches the CLI contract, the payload schema and #484's rules. |
| D4 | **Nested-memory policy** (for example an outermost-within-repository rule; V6) | **offline only** (V3 as `cwd`); live V3 **not reproduced**; V6 never run | A policy decision about supported nested-memory layouts. Needs repository-root detection and a stated compatibility position. |
| D5 | **Repository boundary / parent-directory fallback removal** | **none.** Identified by inspection (G3 §4.2) | Removes governance some layouts may rely on. Needs repository-root detection and a compatibility decision. **Boundary review required:** the fallback lets a memory file above a repository govern it because of where it sits on disk, not because anyone declared it. The [roadmap publication boundary](../roadmap/README.md) puts deterministic cross-repository federation of *known, declared* decision sources in DG2 (public OSS). Discovering, reconciling or inferring organizational decision truth belongs to enterprise decision operations. The implicit fallback is neither a declared DG2 source nor an authorized OSS discovery mechanism. Its future must be decided against that boundary, and slice 1 must not be read as endorsing it. |
| D6 | **`MNEME_MEMORY` precedence** (V4/V5) | **offline only**; V5 live not run | Interacts with the proposed ADR-033 §4.1 binding and with harness and test uses of the override. Needs its own architectural justification. |
| D7 | **Other integrations** that select memory from `cwd` or a project directory: `codex_cli/gate.py:155`, `codex_cli/stop_audit.py:123`, `kiro/hook.py:298`, `antigravity/adapter.py:242`, `agent_sdk/adapter.py:336`, `hermes/adapter.py:256` | **none.** Code inspection only | Different hosts, payloads and test suites. Each needs its own scoping. |

**G3 §4.3 / proposed ADR-033 §4.1.** Slice 1 changes **no** discovery
semantics: not `MNEME_MEMORY` precedence, not the parent fallback, not
nested-memory handling. It only changes where the existing walk starts at one
boundary. So no reconciliation with G3 §4.3 or ADR-033 §4.1 is needed yet.
D4–D6 would need that reconciliation, and it belongs in their charters.

## 9. Explicitly NOT authorized

- **Implementation by this charter.** Nothing is authorized until this charter
  and its `[layer1-freeze]` amendment have both merged (§10).
- **Any Layer 1 freeze amendment in this PR.** The amendment is a separate PR.
- **Every item D1–D7** in §8.
- **ADR-033** acceptance or change, availability states, `closed`/fail-closed
  behavior, operational refusal, or any availability policy. **#483 stays
  separate and proposed.**
- **Missing-memory eligibility, witnesses, declarations or trusted baselines**
  (G3, G3-B), and any new authority store or marker file.
- **Hook registration or coverage changes,** including making a registration
  that exists only in `repo_a` fire in a session rooted elsewhere (L4 limit),
  and extending Stop to `--add-dir` directories.
- **Any change to `find_memory`**, `mneme check`, `mneme.check/v1`, exit
  codes, or the #260 coherence rules; any new schema, CLI flag, MCP surface or
  engine.
- Changes to retrieval, the enforcer, rule matching, the frozen benchmark, or
  `.mneme/project_memory.json`.
- DG1F-C1b applicability exclusion; DG1B2 waivers.
- Any claim of host prevention beyond the re-probed configuration, and any
  claim about the agent-steered `cd` pivot.

## 10. Layer 1 freeze authorization (required, not made here)

Slice 1 changes which memory the direct-write enforcement boundary consults,
so the Layer 1 freeze requires prior authorization. After this charter merges,
a separate `[layer1-freeze]` amendment under Amendment Procedure §3(b) must
reference it. That amendment authorizes **only slice 1** (§3: anchoring the
existing `find_memory` walk at the resolved target in `handle_event`) and
restates §6 as preserved. It authorizes none of D1–D7, and no enforcement-scope,
availability, discovery-semantics or coverage change.

## 11. Sequence

1. **Done:** #513 (T-08 evidence) merged as `98dc4771`.
2. **Pending:** review and merge this charter.
3. **Pending:** merge the matching `[layer1-freeze]` amendment (slice 1 only).
4. **Pending:** implement slice 1 in one PR with the §7.1 tests, squash-merged
   under ADR-022.
5. **Pending:** run the §7.2 live re-probe and record it as a separate evidence
   PR.
6. **Later, each separately gated:** D1–D7.

**ADR-033 remains proposed; C1b remains locked; DG1B2 remains evidence-gated.**

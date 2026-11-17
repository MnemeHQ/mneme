# T-08 G3 re-assessment after P2-first (2026-11-17)

> **Overall: G3 stays `PARTIAL`** (PROPOSED: assessment only, for independent review and owner acceptance).
>
> This is step 6 of the P2-first sequence in charter
> [Amendment A2 §5.2.7](../plans/2026-10-17-t08-d5-p2-memory-resolution-charter.md).
> It re-reads the [G3 live record](t08-g3-host-boundary-live-2026-11-11.md)
> (#793) against what has merged since then.
>
> **It is read-only.**
> - It changes no runtime behavior, harness, ADR, Layer 1 freeze or `.mneme/` content.
> - It runs no probe and re-classifies no earlier evidence.
> - Every G3 result stays exactly as recorded in #793. This record only says
>   which of them P2-first changes, and with what evidence.

## 1. Inputs

All inputs are merged on `main` at `02c09871`:

| Input | Reference | Used for |
|---|---|---|
| G3 charter | [`2026-11-10-t08-g3-host-boundary-live-charter.md`](../plans/2026-11-10-t08-g3-host-boundary-live-charter.md) (#791) | the G3 question, the labels and the §7 claims ceiling |
| G3 live record | [`t08-g3-host-boundary-live-2026-11-11.md`](t08-g3-host-boundary-live-2026-11-11.md) (#793, `621d0212`) | findings A–C and the bounded claim. It ran on `mneme/` = `15750087`, Claude Code `2.1.310`, sources `project,local`, channel C4 (`settings.local.json`), n = 1. |
| P2-first contract | charter A2 §5.2.2 and §5.2.3 (#809, #811) | the selection rows, and the consequences for ADR-033 and G3-1 |
| ADR-033 erratum | #810, #811, #816 | SS-3 through `MNEME_MEMORY` is now reachable only in row 6 |
| P2-first implementation | #815, squash `59309fe7` | `resolve_memory` (`mneme/integrations/memory_selection.py:70`) and the rewritten offline tests |
| P2-first live evidence | [`dg1f-t08-p2-first-live-2026-11-17.md`](dg1f-t08-p2-first-live-2026-11-17.md) (#818, `02c09871`) | PASS, 7/7. Run on Claude Code `2.1.310`, `claude-opus-5-5`, sources `project`, `acceptEdits`, headless, n = 1, channel C2 (committed `settings.json`), Edit only. |
| H1 gate | [`dg1f-t08-d5-p2-host-path-h1-gate-2026-11-16.md`](dg1f-t08-d5-p2-host-path-h1-gate-2026-11-16.md) (#808) | notice delivery (H1a on Edit and Bash) |
| DG1G mapping, G3 row | [`dg1g-fixture-floor-mapping-2026-11-10.md`](dg1g-fixture-floor-mapping-2026-11-10.md) | the G3 control definition and its current wording |

**Release status.** P2-first is on `main` but **unreleased**. No release tag
contains `59309fe7`, and the latest release, `v0.11.0`, predates it. Every
"resolved" below is a statement about `main`, not about any installed
`mneme-hq`.

## 2. What P2-first changes at the G3 seam

`resolve_memory` reads `MNEME_MEMORY` from the process environment only
(`memory_selection.py:79`). It does not know which settings channel set it.
When the walk finds a memory, that memory is selected. Direct writes start the walk at the edited file; Bash, SessionStart and Stop start at the session `cwd` (§4). The selection is:
- `DISCOVERED` when there is no override, or the override is the same file;
- otherwise `OVERRIDE_IGNORED` (charter row 2).

The override governs only when the walk finds **no** memory (row 6,
`OVERRIDE_FILLS_ABSENCE`). Charter §5.2.3 states the intended scope: P2-first
removes env-based replacement (V5) and masking (V4) of a walked memory,
"whichever channel sets the variable (C1, C2, C4)".

## 3. Findings re-assessed

Grades:
- **`PASS`:** P2-first resolves the finding, with live evidence under the
  finding's own conditions.
- **`PARTIAL`:** resolved in code with offline tests, or live under adjacent
  conditions only.
- **`FAIL`:** not resolved, or contradicted by evidence.

### 3.1 Finding A (G3-2): unenrolled wrong-source false complete PASS

**Grade: `PARTIAL`** (resolved on `main` by mechanism and offline tests; live-confirmed on the C2 channel, not re-observed on G3's own C4 channel).

**As recorded (#793, unchanged).** With no ADR-033 declaration, an uncommitted
`.claude/settings.local.json` `env.MNEME_MEMORY` redirected the hook to a
foreign, permissive memory. The live checker observed a complete false `PASS`,
and the forbidden edit landed (`RECORDED_FALSE_COMPLETE_PASS`).

**What P2-first changes.** The G3 fixture repository has its own
`.mneme/project_memory.json`; #793's replay against it fails on `C3-DEC`. So
the walk finds that memory, and row 2 selects it whatever `MNEME_MEMORY` says.
Charter §5.2.1 names G3-2 as "the same defect" that row 2 fixes.

**Evidence:**
- **Code:** `resolve_memory` (§2).
- **Offline:**
  - `tests/integrations/claude_code/test_hook_target_memory_resolution.py::test_v5_other_repo_override_is_ignored` and `::test_v4_missing_override_no_longer_masks_repository_memory`;
  - `tests/integrations/claude_code/test_availability_c2a.py::test_d5_mneme_memory_alone_beside_discovered_memory_is_not_a_mismatch`.
- **Live (#818), C2 channel:**
  - `P2F-V5-own`: the session runs in repo A, with `MNEME_MEMORY` naming B's memory and committed in A's own `settings.json`;
  - `P2F-V5`: the r4 topology.

  In both, the hook selected A's memory (`OVERRIDE_IGNORED`), refused the
  forbidden edit with `T08-DEC` (exit 2), and left the target unchanged.
  `P2F-V5-own` is the close analogue of G3-2: an unenrolled repository with its
  own memory, redirected by its own settings. `P2F-V5` is a sibling-repository
  layout (session and `env` in B), not the G3-2 pattern. Several conditions
  still differ from G3-2:
  - the channel (C2 committed `settings.json`, not C4 `settings.local.json`);
  - the setting sources (`project`, not `project,local`);
  - the fixture and the decision under test (`T08-DEC`, not `C3-DEC`);
  - the hook wrapper (`hookwrap_v4`, not the C3 wrapper).

**Why it is not `PASS`.** #818 did not run under G3-2's own conditions:
- channel C4, with setting sources `project,local`;
- the G3 enforcement fixture.

G3 itself observed that C4 reaches the hook (#793 §2.1 item 1). The resolver
ignores the channel (§2). Together these make it highly likely that G3-2 would
now be refused, but that is an inference, not an observation. Only a re-run of
G3-2 under P2-first would turn it into one, and none is authorized here.

**Unlike G3, `#818`'s refusal is observed, not replayed.** G3's statement that
the edit was forbidden for its own repository rests on replay alone (#793
finding C). In #818 the live hook evaluated the repository's own memory and
named `T08-DEC` in its stderr.

### 3.2 Finding B (G3-1): enrolled, `AUTHORIZED` target refused with `MEMORY_PATH_MISMATCH`

**Grade: `PARTIAL`** (the recorded refusal route is superseded on `main`; the replacement outcome is offline-tested only).

**As recorded (#793, unchanged).** With an ADR-033 declaration verified
`AUTHORIZED`, the same redirect was refused through availability routing. The
outcome was `REFUSED_MEMORY_PATH_MISMATCH`, exit 2, with the target unchanged.
The live checker had still returned a complete `PASS` against the foreign
memory.

**What P2-first changes.** The G3-1 repository has its declared memory on
disk, so the walk finds it, and row 2 selects it. `memory_mismatch` is
therefore false, and the `MEMORY_PATH_MISMATCH` refusal **does not reproduce
through `MNEME_MEMORY`** (charter §5.2.3; ADR-033 erratum #810/#811). The edit
is instead checked against the declared memory. That memory forbids the edit,
which rests on #793's replay (`C3-DEC`), not on a live evaluation.

**Evidence:**
- **Offline:**
  - `tests/integrations/claude_code/test_p2_first_notices.py::test_h1a_row2_notice_under_each_verified_state`, which runs under `AUTHORIZED`, `REVOKED` and `VERIFIED_ABSENT`. With a foreign override and the declared memory present, a `PASS` gives exit 0 and one `OVERRIDE_IGNORED` notice; a `FAIL` gives exit 2 with no stdout. The checker result is stubbed in this test.
  - SS-3 through `MNEME_MEMORY` stays reachable in row 6 only, when the declared memory is absent: `test_availability_c2b.py::test_h7_mneme_memory_mismatch_refuses`, `::test_h12_unverifiable_mismatch_is_reported_not_refused` and `test_availability_c2a.py::test_d5_mneme_memory_override_is_mismatch`, all rewritten for P2-first.
- **Live:** none for an enrolled repository under P2-first. #818 did not enroll any repository in ADR-033 availability.

**Reading.** For this layout, the protection G3-1 recorded (a refusal) is
expected to persist on `main`, by a better route: a complete evaluation
against the repository's own memory, instead of an availability refusal on
top of a wrong-memory `PASS`. This is not live-verified. G3-1's recorded
label is history; it is neither upgraded nor invalidated.

### 3.3 Finding C: observation and replay stay separate

**Grade: `MET` (method finding; the §3 scale does not apply).** This is not
a defect that P2-first resolves.

#793 kept the observed items (selection, checker result, availability, host
outcome) apart from the replay. That still holds:
- G3's own claim that the edit was forbidden for its repository still rests
  on replay alone.
- #818 observed selection, exit code, stderr (`T08-DEC`) and the host outcome
  directly, with no replay, for its own probes only.

This record keeps the same separation: §3.1 and §3.2 say which statements are
inferred.

## 4. Remaining gaps

**Boundary binding (Phase 2, not authorized).**
- P2-first has no B1 boundary; the walk is unbounded (`walk: "unbounded"`).
- **Ancestor memory beats the override** (charter §5.2.3, case 2). A parent-directory memory (L6), or the outer checkout's memory seen from a worktree (L4) or a submodule (L5), is selected by row 1 or row 2 even when the override names the repository's intended memory.
- **A planted memory beats the override.** Anyone who can write `.mneme/project_memory.json` into the checkout or an ancestor (V3/V6) makes it the selection, even with `MNEME_MEMORY` set. P2-first removes the override's incidental defense against such a plant. This is a G3-relevant regression in that one layout, accepted as A2-4.

**Shadowed memory.**
- `boundary` and `shadowed` are not populated in P2-first (`None`).
- Rows 3–5, which govern an override that equals or conflicts with a shadowed memory, cannot occur until Phase 2.

**The override still governs where nothing is walked.**
- **Row 6: a remaining wrong-source PASS route.** With no memory on the walk, `MNEME_MEMORY` still selects any existing file (`OVERRIDE_FILLS_ABSENCE`).
  - **Unenrolled repositories:** if the repository's memory is deleted or absent, a foreign permissive memory still yields a complete PASS (by mechanism and `tests/integrations/test_memory_selection.py`; not observed live under P2-first). This is the G3-2 shape without a walked memory, and it falls inside G3's definition ("missing local declaration … never an authoritative PASS").
  - **Enrolled repositories:** only `AUTHORIZED` refuses (SS-3, `test_h7`). `UNVERIFIABLE` is reported but not refused (`test_h12`), and `REVOKED` and `VERIFIED_ABSENT` proceed.
- **Row 7:** a missing override with no walked memory selects nothing (`OVERRIDE_MISSING`). The H1a notice reports it, but nothing governs.

**Start points are not unified (D1/D2/D7; charter §5.2.3 "Not removed").**
- Every consumer uses the resolver, but only direct writes start the walk at the edited file (`hook.py:896-910`).
- Bash, SessionStart and Stop start at the session `cwd` (`hook.py:1617`, `:1680`, `:1831`).
- So a Bash write into repository A from a `cwd` in repository B selects B's memory. `test_hook_target_memory_resolution.py::test_bash_heredoc_still_selects_memory_from_cwd` pins this.
- This is a wrong-source route that needs no `MNEME_MEMORY`, and P2-first does not change it.

**Host paths not live-verified under P2-first.**
- **`Write` and `MultiEdit`:** H1a is authorized for Edit, Write, MultiEdit and Bash, but live-verified only for Edit and Bash (#808). #818 probed Edit only.
- **Bash, SessionStart and Stop under P2-first:** offline only (`tests/integrations/test_p2_first_same_selection.py`, `test_p2_first_notices.py`). The G3 limit "those seams still select memory through `MNEME_MEMORY`" no longer holds on `main` (all consumers use the resolver), but this is offline evidence only.
- **Channel C4 (`settings.local.json`) and setting sources `project,local` under P2-first:** not observed (§3.1).
- **ADR-033-enrolled repositories under P2-first:** not observed (§3.2).
- **Other hosts (H2–H6: Codex, Kiro, Antigravity, Agent SDK, Hermes):** offline same-selection tests only.
- **Other host versions and models, and repeatability (n = 1):** not covered.

**Outside P2-first's scope (unchanged from #793 and the DG1G row).**
- Agent-controlled setting of the override (C3, C5, C6); `bypassPermissions`, `.claude/**` allow rules, interactive approval.
- Hook removal, changed tool configuration, altered workflow, administrator bypass.
- The `AUTHORIZATION_UNVERIFIABLE` path live (offline only).

## 5. Overall G3 assessment

**G3: `PARTIAL`.** The status is unchanged; the bounded statement is updated.

> **partial, bounded.** On `main` at `02c09871` (P2-first, unreleased), a
> `MNEME_MEMORY` override no longer replaces or masks the walked memory. For
> direct-write tools, that is the memory found by walking up from the edited
> file; Bash, SessionStart and Stop walk from the session `cwd`.
> - **Mechanism:** code and offline tests, for every channel.
> - **Live:** observed on Claude Code `2.1.310` for the committed-settings channel C2, Edit only, n = 1 (#818).
>
> For the G3-2 layout (C4, unenrolled), the earlier observed false complete
> PASS is therefore expected to become a refusal, but this has not been
> re-observed live. For the G3-1 layout (enrolled, `AUTHORIZED`), the recorded
> `MEMORY_PATH_MISMATCH` refusal is superseded by evaluation against the
> declared memory; this is offline-tested only.
>
> Protection still depends on the walk finding the right memory:
> - there is no boundary binding (Phase 2), so an ancestor or planted memory wins;
> - start points are not unified;
> - `MNEME_MEMORY` still governs where no memory is walked, which leaves a wrong-source PASS route for a repository whose memory is absent. Hook removal,
> configuration changes and administrator bypass are outside this control's
> current evidence.

What would move G3 further:
- **Toward `PASS` for finding A:** a re-run of G3-2 (C4, `project,local`) on P2-first.
- **Toward `PASS` for finding B:** a re-run of G3-1 (enrolled, `AUTHORIZED`) on P2-first.
- **Toward closing the boundary gaps:** Phase 2.

None of these is authorized here (§6). The G3 row in the
[DG1G mapping](dg1g-fixture-floor-mapping-2026-11-10.md) is updated in this
PR to cite this record and drop the now-stale "D6/P2 … not implemented"
sentence. Its status stays **partial**.

## 6. Not authorized by this record

- any new live run or probe, including the G3-2 and G3-1 re-runs named in §5;
- Phase 2 (B1, I3, rows 3–5);
- H2–H6 extensions;
- any release;
- G3 closure, or any claim beyond §5.

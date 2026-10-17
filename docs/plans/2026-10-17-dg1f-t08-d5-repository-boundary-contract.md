# D5: Repository boundary contract (ACCEPTED: definition only)

**Date:** 2026-10-17
**Status:** **ACCEPTED as the D5 boundary definition only** (owner approval, 2026-10-17, following an independent-review ACCEPT on `0c1ed8e6`). Docs only. Acceptance does not authorize implementation, tests, experiments, ADR or Layer 1 freeze amendments, or changes to C1–C4 evidence, pins or worktrees.
**Revision 2 (2026-10-17):** adds host-visible diagnostics (§5.1), separates contract acceptance from implementation authorization (§8), records the agreed B1 decision statement (§7), and sets up one cross-consumer charter for the stop rule (§5.3). This revision itself is the only change authorized.
**Revision 3 (2026-10-17):** folds in two independent-review checks. The stop rule governs implicit discovery only; explicit memory overrides are a Q2 question (§2, §5.3). §5.1 adds a source-verified inventory of current missing-memory behavior per consumer.
**Revision 4 (2026-10-17):** answers the #537 review. It splits an absent Git marker from an existing but invalid one (L8a/L8b, §4 B1), states that D5 guarantees consistent walk termination but not identical memory selection across tools (§5.3), and completes the §5.1 consumer inventory.
**Acceptance (2026-10-17):** adds condition §5.4 (planted Git markers) and records owner acceptance of the definition.
**Owner-approved refinement of §5.1 (2026-10-17):** plain absence gets a structured non-PASS outcome without a per-event host notice. It was made during review of the [shared D5 + P2 implementation charter](2026-10-17-t08-d5-p2-memory-resolution-charter.md) (#542). Approved by the owner (@TheoV823) on 2026-10-17 in the owner's working session with the authoring agent, in these words: "Approve the D5 §5.1 refinement (row 8: structured non-PASS only, no per-event notice) and amend D5 in the same PR." This is recorded here and has no separate GitHub artifact. The independent reviewer's conditional support for the refinement is **not** the approval. It changes nothing else in this contract, and its acceptance status is unchanged.
**Source anchor:** `MnemeHQ/mneme` `main` at `45cefa63`, read-only. `mneme/` is unchanged between `45cefa63` and this branch's base `68d1aaed`, so all line anchors hold.
**Inputs:** T-08 charter §2–§8 ([charter](2026-10-15-t08-target-path-memory-resolution-charter.md)); [D6-Q1 review reconciliation](2026-10-17-dg1f-t08-d6-q1-review-reconciliation.md). The 2026-10-16 preliminary review and the 2026-10-17 Opus validation are unpublished working documents; their accepted corrections are recorded in the reconciliation note.

## 1. Question

Charter §2 accepts this direction: *the repository being modified, resolved from the target path, determines the governing memory.* D5 asks one thing: **where does "the repository" end?** In code terms, where must the memory walk from the resolved target stop?

Out of scope: which memory wins *inside* the boundary (D4), whether a memory outside it may govern through `MNEME_MEMORY` (D6/Q2), the out-of-root outcome (D3), and verified authority (G3-B).

## 2. What the code already says (new to this review)

The product has **two root concepts today, and they disagree.**

| Consumer | Root concept | Source |
|---|---|---|
| `mneme setup` | **Nearest ancestor with `.git` (a directory or a file)**. It refuses to run without one ("Mneme setup requires a repository context") and scaffolds memory at `<git root>/.mneme/project_memory.json`. | `mneme/setup.py:113-122` (`find_project_root`), `:192-205` |
| `mneme init` | None. It writes `--path` relative to cwd, and no Git is needed. | `mneme/cli.py:128-146` |
| Enforcement (`find_memory`) | None. It walks every ancestor to the filesystem root and ignores `.git`. | `hook.py:187-199` |
| Claude Code direct write | Walk starts at the resolved target (T-08) | `hook.py:514-527`, `:1124` |
| Claude Code Bash, SessionStart, Stop; Codex gate and stop audit; Kiro; Antigravity | Walk starts at session `cwd` | `hook.py:710,772,919`; `codex_cli/gate.py:155`; `codex_cli/stop_audit.py:123`; `kiro/hook.py:298`; `antigravity/adapter.py:242` |
| Agent SDK, Hermes, LangChain | Walk starts at the configured `project_dir` | `agent_sdk/adapter.py:336`; `hermes/adapter.py:256`; `langchain/adapter.py:96-103` |
| `policy_root` (ADR-020) | Directory above `.mneme/`, derived from the selected memory | `path_selectors.py:155-160` |

**Explicit overrides bypass discovery.** Several consumers accept an explicit memory path that skips `find_memory` entirely:
- `MNEME_MEMORY`, inside `find_memory` itself (`hook.py:188-191`), for every caller;
- the Codex gate's `memory_override` (`codex_cli/gate.py:149-152`; its docstring scopes it to tests and embedders);
- the public `memory=` constructor argument of Agent SDK (`agent_sdk/adapter.py:109-124,333-335`), Hermes (`hermes/adapter.py:127-132,253-254`) and LangChain (`langchain/adapter.py:97-104`).

D5 governs **implicit discovery only**: the walk taken when no explicit path is given. How an explicit path interacts with the boundary `R` is a D6/Q2 question.

So **the installer already treats the nearest `.git` (directory or file) as the project boundary**, while enforcement treats no boundary at all. A memory that `mneme setup` creates always sits at a Git root, yet enforcement can select a memory above that root that no installer step ever associated with the repository.

## 3. Compatibility cases

| # | Layout | Today (enforcement) | Notes |
|---|---|---|---|
| L1 | Ordinary checkout, memory at Git root | Own memory | Normal case. Root = Git root = `policy_root`. |
| L2 | Non-Git project, memory created by `mneme init` | Own memory | Has no Git boundary. Must stay supported (`init`, `check --memory`, and the `test_memory_discovery.py` tmp-dir walks). |
| L3 | Linked worktree outside the main checkout | Own committed memory | `.git` is a file (`gitdir: …`). `find_project_root` already treats it as a root. |
| L4 | **Task worktree inside another checkout**: `C:/dev/mneme/.claude/worktrees/<name>/` and `C:/dev/mneme/.worktrees/` | Own committed memory, **if the branch has one** | Observed: `brave-williams-3369b9` has a `.git` file pointing to `C:/dev/mneme/.git/worktrees/…` plus its own `.mneme/`. **If a worktree's branch lacks `.mneme/project_memory.json`, the walk crosses its Git boundary and the administrative checkout's memory on `main` governs it.** This is code-derived; no test or live evidence exists. |
| L5 | Submodule or nested independent repo, no memory of its own | Outer repo's memory governs | Inner `.git` file or directory. The outer memory governs a different repository because of where it sits on disk. |
| L6 | Repo with no memory under a directory that has one (parent fallback) | Parent memory governs | Charter §8 D5: this is neither a declared DG2 source nor an authorized OSS discovery mechanism. |
| L7 | Monorepo with nested `.mneme/` below the Git root | Nearest wins (V6) | **D4**, not D5. Both nested and outer memories sit inside one boundary. |
| L8a | `.git` **absent** (for example, an exported tree or a deleted marker) | Walk continues upward | Same as L2: no boundary. |
| L8b | `.git` **exists but is invalid** (for example, a `.git` file whose `gitdir:` target is missing, or a damaged `.git/` directory) | Walk continues upward (`find_memory` ignores `.git`) | `find_project_root` uses `.exists()` (`setup.py:120`), so setup already treats it as a root. Under B1 it **is a boundary** (§4). |

## 4. Candidate contracts

**B0. Keep today's unbounded walk.** Breaks nothing. Leaves L4–L6 cross-repository governance implicit, and leaves the installer and enforcement disagreeing. Charter §8 already says slice 1 must not be read as endorsing it.

**B1. Bound the walk at the nearest Git root (directory or file), reusing `find_project_root` semantics. Proposed.**
- Starting at the walk's start directory, stop at the first ancestor `R` where `R/.git` exists. Consider memory only in `R` and its descendants on the path.
- **Marker semantics are existence-only, deliberately the same as `find_project_root`** (`setup.py:120`, `(candidate / ".git").exists()`). A `.git` directory or file counts as a boundary whether or not Git considers it valid. D5 does not parse `gitdir:`, call `git`, or check repository integrity. Reasons:
  1. Install and enforcement then agree on the root by construction.
  2. Validating the marker would read and act on checkout-controlled metadata, which moves `.git` toward an identity signal (G3-B forbids relying on it).
  3. When in doubt the rule stops *earlier*. Its worst case is `NO_MEMORY_SELECTED`, which must be visible (§5.1), never a memory from a different repository.
- If no `.git` exists on the path, there is no boundary: keep today's walk (L2 and L8a unchanged).
- `.git` is a **location signal only**. It is never authority, trust or identity attestation (G3-B; the review's M1).
- Outcome per case: L1, L2, L3, L7 and L8a are unchanged. **L8b changes** only if a memory sits above the invalid marker; it is then no longer selected. **L4 is fixed**: a worktree without memory becomes ungoverned instead of silently governed by `main`. **L5 changes**: a submodule is no longer governed by the outer memory. **L6 changes**: a parent memory above a Git root stops governing.

**B2. Declared root marker** (for example a key in the memory or a sentinel file). Most explicit, but every existing install would need a migration, and it duplicates what `setup` already establishes. That makes it a D6/DG2-style declaration mechanism, not a boundary rule. Rejected for D5 and kept as a possible D6 input.

## 5. Compatibility cost of B1, stated plainly

B1 **removes governance** in L4, L5 and L6. Today those edits are checked against a memory; under B1 they find no memory and are skipped. That moves the hook toward fail-open, and the missing-memory skip is silent today (V4 behavior; ADR-021). B1 is therefore only acceptable together with the following four conditions:

1. **A host-visible diagnostic that separates `NO_MEMORY_SELECTED` from `PASS`.**
   - **Today no consumer meets this condition.** Current missing-memory behavior, source-verified at `45cefa63`:

     | Consumer | Missing-memory behavior today | Source |
     |---|---|---|
     | Claude Code direct write, Bash | exit 0, no output | `hook.py:1125-1126`, `:711-712` |
     | Codex CLI gate | `SKIP` result with reason `"no project memory"` | `codex_cli/gate.py:150-156` |
     | Kiro hook | exit 0 | `kiro/hook.py:298-300` |
     | Antigravity adapter | emits `{}` | `antigravity/adapter.py:242-247` |
     | Claude Code SessionStart | exit 0, no output; no baseline taken | `hook.py:772-774` |
     | Claude Code Stop | exit 0, no output; no session-delta audit | `hook.py:919-921` |
     | Codex stop audit: baseline and Stop | baseline returns `None`; Stop exits 0, no output | `codex_cli/stop_audit.py:88-90`, `:137-139` |
     | Agent SDK gate | `ACTION_SKIP` with `"no project memory"` | `agent_sdk/adapter.py:192-196` |
     | Agent SDK context | empty injection; trace records `outcome="NO_MEMORY"` | `agent_sdk/adapter.py:133-140` |
     | Hermes gates (file, patch, terminal) | `ACTION_SKIP` with `"no project memory"` | `hermes/adapter.py:286-289`, `:410-411`, `:492-493` |
     | Hermes context | empty `ContextInjection` | `hermes/adapter.py:141-142` |
     | LangChain | delegates to an internal Agent SDK instance, so it inherits the Agent SDK rows | `langchain/adapter.py:101-104`, `:143-146` |

     The inventory covers every `find_memory` caller in §2. A structured `SKIP` or `NO_MEMORY` trace (Codex gate, Agent SDK, Hermes, LangChain) is distinguishable from `PASS` in machine-readable output, but **host-visible reporting is unverified for every row**, including the exit-0 rows, where nothing is emitted at all. Host-visible delivery is an **implementation prerequisite, not a demonstrated capability**.
   - Every consumer must report a distinct `NO_MEMORY_SELECTED` outcome whenever discovery selects no memory. A sub-case applies when the walk stopped at a Git boundary and a memory exists above it. Example: "memory at X is outside repository root R and was not applied".
   - **Refinement (owner-approved 2026-10-17).** One case is excepted from the per-event host-visible requirement: **plain absence**, meaning no memory anywhere on the walked path, no Git-boundary shadowing, and no `MNEME_MEMORY` set. It still produces a structured **non-PASS** outcome (`NO_MEMORY_ON_PATH`) wherever the consumer has a structured result, and it must never look like `PASS`. It gets no per-event host notice, because a user-wide installation would otherwise emit one on every edit in every repository that does not use Mneme, when nothing was displaced. Every other `NO_MEMORY_SELECTED` case keeps the full host-visible requirement below. That includes a boundary shadowing a memory, a missing override, and an override refused at a boundary.
   - That outcome must never look the same as a genuine enforcement `PASS`, either to the developer or in machine-readable output.
   - **"Visible" means a reporting channel that has been verified to reach the developer or the agent through the host.** On Claude Code, stderr from a PreToolUse hook that exits 0 is not shown to the model and is not normally shown to the user. Today the V4 skip returns 0 with no output at all (`hook.py:1125-1126`). So stderr does not satisfy this condition.
   - The contract **does not assume** that an existing channel can report every PreToolUse skip. Existing channels include SessionStart `additionalContext`, Stop feedback (`_emit_stop_feedback`, `hook.py:743`) and PreToolUse `defer` (`_emit_defer`, `hook.py:484-501`). Each one must be verified per host before it is relied on.
   - **`defer` carries permission semantics.** It hands the call back to the normal permission flow, and the warn mode chose it deliberately so that it never auto-approves (`hook.py:487-490`). Using it as a diagnostic channel must not change permission outcomes, and must not introduce `allow`.
   - Any change to exit codes or blocking stays under ADR-021's fail-open policy. That change is not part of D5.
   - Without such a channel, B1 turns governed edits into silent permits, which is the same class of problem as V4.
2. **A declared path for legitimate L5/L6 users.** That belongs to D6/Q2 (explicit external memory), not to an implicit walk. Until D6 lands, `MNEME_MEMORY` still covers them (precedence unchanged). D5 implementation is not authorized until Q2 defines this path (§8).
3. **One cross-consumer charter for the stop rule.**
   - **D5** defines one shared rule for **where implicit discovery stops**. It does not apply to explicit overrides (§2), which Q2 decides. A single implementation charter adopts it for every consumer in §2 at once: Claude Code direct write, Bash, SessionStart and Stop; the Codex gate and stop audit; Kiro; Antigravity; Agent SDK; Hermes; LangChain.
   - The stop rule must not land one adapter at a time. Otherwise one session gets different governance depending on which tool the agent uses.
   - **What D5 does and does not guarantee.** D5 guarantees that every consumer **terminates** its walk by the same rule. It does **not** guarantee that every tool selects the **same governing memory** for the same target, because start points differ. Example: the Claude Code direct-write path starts at the resolved target, while Bash starts at the session `cwd` (`hook.py:710` vs. `:1124`). A Bash write to `repo_a/app.py` from a session in `repo_b` can therefore still select `repo_b`'s memory after D5. Identical selection across tools needs D1/D2/D7 as well.
   - **D1/D2/D7** stay separately gated. They decide **where each adapter starts** discovery (target or session `cwd`/`project_dir`). D5 does not change any start point.
   - **D6/Q2** decides external-memory precedence and compatibility, and must be resolved before D5 implementation is authorized.
4. **Planted Git markers are handled explicitly.** The `.git` marker is checkout-controlled, so B1 lets anyone who can write to the checkout, including an agent, create an empty `.git` file or directory in a subdirectory and make edits beneath it ungoverned. That is a cheaper evasion than planting a memory file (V3/V6). The implementation charter must define the outcome when a Git marker sits **below the policy root of the memory that would otherwise govern** the target. Options include at least a host-visible diagnostic, or not honoring markers created during the session. Making the outcome visible does not by itself restore enforcement, and stronger guarantees remain G3-B's. This condition records the risk; it does not choose a mechanism.

Layer 1 freeze: changing the stop rule changes `find_memory`. Charter §3 froze `find_memory` as unmodified and kept `test_memory_discovery.py` valid. Adopting B1 therefore needs its own charter and a freeze amendment. This draft authorizes neither.

## 6. Interactions

- **D4:** B1 provides the root that D4 needs. Within `R`, nearest-wins (V6) is unchanged until D4 decides.
- **D6/Q2:** can be stated as "may a memory outside `R` govern a target inside `R`, and how is that declared". Q2 may open once this contract is **accepted**. Q2 must then be resolved before D5 is **implemented**. Both dependencies point the same way at each stage, so there is no cycle (§8).
- **D1/D2/D7:** each adapter's start point. Separately gated, and unchanged by D5.
- **D3:** reachable through `MNEME_MEMORY` regardless of B1.
- **G3-B R3:** binds `(R, effective memory path)` and consumes `R`. Local `.git` remains forgeable and is never the verification source.
- **Adapter items** (relative materialization, TOCTOU): unaffected.

## 7. Proposed decision statement (pending independent review)

Owner review on 2026-10-17 provisionally answered the four questions as follows:
1. B1 is preferred over B0 and B2.
2. All §5 conditions are mandatory (§5.4, planted markers, was added at acceptance).
3. Submodule isolation (L5) is intended as a boundary principle. Explicitly declared inheritance is a separate D6 question.
4. An offline characterization test of L4 is required before any behavioral change. Running it is not yet authorized.

The proposed decision:

> **Adopt target-derived, nearest-Git-marker project boundaries as the preferred D5 direction, with non-Git compatibility preserved. Require observable missing-memory outcomes and an explicit external-memory compatibility contract before implementing boundary enforcement.**

Here, "Git marker" means a `.git` directory or file. It is a candidate local project boundary only, not a trusted identity credential (G3-B). Accepted by the owner on 2026-10-17 as the D5 definition, after the independent review in §8.

## 8. Acceptance vs. authorization

| Stage | What it means | Prerequisite | Status |
|---|---|---|---|
| **D5 contract acceptance** | The §7 statement becomes the accepted boundary *definition*. No code, test or behavior changes. | Independent review of this draft | **Done** (review ACCEPT on `0c1ed8e6`; owner approval 2026-10-17) |
| **Q2 opens** | D6 external-memory precedence and compatibility is defined against the accepted boundary `R` | D5 contract acceptance | **Eligible** |
| **D5 implementation authorization** | One cross-consumer charter (§5.3) plus a Layer 1 freeze amendment for `find_memory` | Q2 resolved (§5.2), a verified host-visible channel per host (§5.1), a defined planted-marker outcome (§5.4), and the L4 characterization test (§7.4) authorized and recorded | Blocked |

**Next gate:** open D6/Q2 (external-memory precedence and compatibility) against the accepted boundary `R`. This acceptance does not authorize implementation, tests, experiments, ADR changes or Layer 1 freeze amendments.

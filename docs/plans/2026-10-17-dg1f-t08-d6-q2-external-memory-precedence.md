# D6/Q2: External-memory precedence and compatibility (PROPOSED)

**Date:** 2026-10-17
**Status:** **PROPOSED, not accepted.** Architecture assessment, docs only. It does not authorize implementation, tests, experiments, C5/C6, ADR or Layer 1 freeze amendments, ADR-033 changes, or changes to C1–C4 evidence, pins or worktrees.
**Revision 2 (2026-10-17):** answers the #538 review. It narrows P2's guarantee to correct boundary resolution and start points (§5, §8), ties rule 2 to D5 §5.4 with an added override constraint (§5, §7), and adds §5.4 to the implementation prerequisites (§10). The P2 rule itself is unchanged.
**Source anchor:** `MnemeHQ/mneme` `main` at `28211f8b`, read-only.
**Inputs:**
- [D5 repository-boundary contract](2026-10-17-dg1f-t08-d5-repository-boundary-contract.md) (ACCEPTED, definition only);
- [D6-Q1 reconciliation](2026-10-17-dg1f-t08-d6-q1-review-reconciliation.md);
- [T-08 charter](2026-10-15-t08-target-path-memory-resolution-charter.md) §8 (D6, D3);
- [D6 live scope](2026-10-15-dg1f-t08-d6-mneme-memory-live-scope.md) (#519);
- C1–C4 evidence: [C1](../validation/dg1f-t08-d6-mneme-memory-c1-live-2026-10-15.md), [C2](../validation/dg1f-t08-d6-mneme-memory-c2-live-2026-10-15.md), [C3](../validation/artifacts/dg1f-t08-d6-c3-mneme-memory-live/harness/README.md), [C4](../validation/dg1f-t08-d6-mneme-memory-c4-live-2026-10-16.md);
- [G3](2026-10-14-dg1f-g3-missing-memory-eligibility-assessment.md) and [G3-B](2026-10-14-dg1f-g3b-eligibility-authorization-design.md);
- ADR-033 / #483 (**proposed**, not accepted).

## 1. Question

D5 defines a boundary `R`: the nearest `.git` directory or file above the discovery start, or no boundary for non-Git projects. Q2 asks:

> **When may a memory selected by explicit path, rather than by implicit discovery inside `R`, govern a target inside `R`? And how do legitimate external-memory configurations keep working?**

D5 §5.2 requires this answer before D5 can be implemented. That includes a declared path for L5/L6 users: submodules, nested repos, and repos that rely on a memory file in a parent directory.

Out of scope here:
- **D3:** the outcome when the target falls outside the selected memory's policy root.
- **D4:** nested memories within `R`.
- **D1/D2/D7:** discovery start points.
- **G3-B:** verified authority.

The interactions are listed in §7.

## 2. Explicit-path channels today (source-verified)

| Channel | Reader | Scope | Who controls it |
|---|---|---|---|
| `MNEME_MEMORY` env | `find_memory` (`hook.py:188-191`). The only production reader; `mneme check` itself never reads it. | Every `find_memory` caller: Claude Code direct write, Bash, SessionStart, Stop; Codex gate and stop audit; Kiro; Antigravity; and Agent SDK, Hermes and LangChain when no constructor path is given | Whoever controls the hook process environment (§3) |
| Constructor `memory=` | Agent SDK `agent_sdk/adapter.py:109-124,333-335`; Hermes `hermes/adapter.py:127-132,253-254`; LangChain `langchain/adapter.py:97-104` (via its internal SDK) | That embedding only | The program embedding Mneme |
| Codex `memory_override` | `codex_cli/gate.py:149-152` | Codex gate. The docstring says "tests and embedders; production callers pass only `payload` and `cwd`" | Test or embedder code |
| `mneme check --memory` | CLI argument | One invocation | The CLI caller. It is not discovery, so D5 and Q2 do not apply to it |

`MNEME_MEMORY` is **not user-documented**. It appears in no README, plugin manifest or user guide on `main`; only in plans, validation records and tests.

## 3. Evidence on `MNEME_MEMORY` (C1–C4, pinned `mneme/` = `40ab0dd1`)

| Channel | Result | Meaning |
|---|---|---|
| C1 operator shell env | Reached the hook. V5: B's memory, complete PASS, forbidden edit landed. V4: `SILENT_MEMORY_SKIP`. | The operator can redirect or disable enforcement |
| C2 committed project `.claude/settings.json` `env` | Reached the hook in both topologies, **including V5-own/V4-own** (a repo's own settings neutering its own memory) | **Anyone who can commit config can silently disable or redirect the repository's own enforcement for every later session** |
| C3 mid-session settings edit, same process | Harness plumbing propagated; the agent's own settings write was **host-denied** | Mechanism shown; agent control not shown |
| C4 uncommitted `.claude/settings.local.json` | Pre-session and harness mid-session writes propagated; the agent's write was host-denied | Same as C3 for agent control |
| C5 / C6 | **Not run, not authorized** | Not needed for this assessment (§8) |

Agent-controlled exploitation is **not** established. The precedence defect is established without it: today an explicit override **always replaces** the memory of the repository being modified, and a missing override **masks** that memory. Both happen silently.

## 4. Legitimate uses any rule must keep (inventory)

| # | Use | Location of override vs. target | Needs override to beat an in-`R` memory? |
|---|---|---|---|
| U1 | Blinded pre-generation validation (`docs/validation/pre-generation-guidance-live-ab.md:203-208`) | Memory **outside** the workspace; the workspace deliberately has **no** `.mneme/`. The run uses no `PreToolUse` enforcement hook. | **No.** There is no in-`R` memory to beat. |
| U2 | Cursor hook compatibility T7a (`validation/cursor-hook-compat/m2_enforcement_matrix.py:23-45`) | Override = `fixture/.mneme/project_memory.json`, the **same** memory discovery finds | **No.** Override and discovery agree. |
| U3 | Test isolation | 11 test modules **unset** it to stop a developer's env leaking in. Three set it: `test_memory_discovery.py:29` (walk start has no memory), and the V4 and V5 characterizations (`test_hook_target_memory_resolution.py:289-308`), which pin today's behavior on purpose. | **No**, except V4/V5, which exist to record the defect. |
| U4 | Embedders (constructor `memory=`) | Chosen by the embedding program | Possibly. That is not ambient configuration (§6, O3). |
| U5 | D5 L5/L6 compatibility (submodule or parent-fallback users after D5) | A memory **above** `R`, with no memory inside `R` | **No.** `R` has no memory of its own. |

**Finding.** No inventoried legitimate use of the environment override needs it to **replace** a memory that exists inside `R`. Every use either fills an absence (U1, U5) or names the same memory (U2). The only cases that rely on replacement are V4/V5, which record the defect.

## 5. Candidate precedence rules

Let `M_R` be the memory implicit discovery selects inside `R` (D5 stop rule), and `M_X` the memory named by `MNEME_MEMORY`.

**P0. Status quo: `M_X` always wins.** Keeps V4/V5 and the C2 own-repo neutering. Fails D5 §5.2: the L5/L6 path would be the same channel that can silently disable an in-repo memory. **Rejected.**

**P1. `M_X` only when it lies inside `R`.** Breaks U1 (out-of-workspace memory) and U5 (memory above `R`), the exact cases D5 must preserve. **Rejected.**

**P2. Repository memory wins; an override only fills an absence. Proposed.**
1. If `M_R` exists, it governs. A conflicting `M_X` is **not applied**. The consumer reports this through the host-visible channel D5 §5.1 requires: "override X ignored: repository memory Y governs target T".
2. If no `M_R` exists and `M_X` is an existing file, `M_X` governs. This keeps U1 and U5. **Rule 2 is only as safe as the boundary that decided `M_R` is absent.** Consider a `.git` marker planted at `A/src/` while `A/.mneme/project_memory.json` exists. The D5 walk for `A/src/app.py` stops at `A/src/`, so `M_R` is absent, and rule 2 would apply `M_X`. With `M_X` pointing at a permissive repository B, that recreates the C2 wrong-memory complete `PASS`. Under D5 alone the same planted marker gives a visible `NO_MEMORY_SELECTED`. P2 rule 2 turns it into wrong-memory governance, so P2 **raises the stakes** of D5 §5.4. **Added constraint:** the outcome D5 §5.4 defines for a Git marker below the policy root of a memory that would otherwise govern must also **prevent rule 2 from substituting `M_X`** in that case. This document does not choose the mechanism.
3. If `M_X` is set but missing or unreadable: with `M_R` present, rule 1 applies, so V4's silent masking ends. With no `M_R`, the outcome is `NO_MEMORY_SELECTED` with reason "override missing", reported host-visibly. Never a silent skip.
4. If `M_X` equals `M_R` after `resolve()`, there is no conflict and nothing is reported (U2).

**Property (bounded): when implicit discovery correctly identifies an existing governing memory, an ambient override can add governance to an ungoverned repository but can never remove or replace the repository's own.** Under that condition P2 removes V5, V5-own and V4 as override-substitution outcomes, whichever channel sets the variable (C1, C2 or C4). P2 does **not** independently resolve:
- planted or incorrect boundaries (D5 §5.4; rule 2 above);
- adapter start points that discover a different repository. Example: a Bash write to A from a session in B still selects B's memory under P2 (D1/D2; D5 §5.3);
- verified authority (G3-B). It matches the proposed ADR-033 §4.1 direction that a differing `MNEME_MEMORY` "cannot bypass the established binding", but it does not depend on ADR-033 being accepted.

**P3. A declared external source inside `R`** (for example, the in-repo memory names an external memory it extends). This is the DG2 declared-federation direction, and it is the right home for "an organization-wide memory *adds to* a repo memory". It is outside D6's scope and is not a precedence rule for an ambient env var. **Deferred to DG2;** P2 does not preclude it.

**P4. Remove the env override from hooks.** Breaks U1 and the U5 compatibility path that D5 relies on. **Rejected.**

## 6. Compatibility cost of P2, stated plainly

- **Lost capability:** using the environment to swap in a *different* memory over an existing repo memory. No inventoried use does this (§4). The cost is the two V4/V5 characterization tests, which a P2 implementation must flip to their new expected outcomes.
- **Lost capability:** using the environment to *add* an external memory on top of a repo memory (union). Nothing provides this today either, since P0 replaces rather than merges. It belongs to P3/DG2.
- **Behavior change for operators:** an operator who set `MNEME_MEMORY` deliberately to override a repo memory now gets the repo memory plus a visible notice. This moves toward more enforcement, not less.

## 7. Interactions

- **D5:** P2 uses `R` to decide whether an in-repository memory exists. Under D5, implicit discovery inside `R` is what produces `M_R`. P2 supplies the D5 §5.2 "declared path" for L5/L6: set `MNEME_MEMORY` to the outer memory. P2 lets it apply only where `R` has none. D5 §5.2 is therefore satisfied by P2 **plus** the §5.1 visibility condition **plus** a §5.4 outcome that also blocks rule-2 substitution (§5).
- **D3 (still open):** under P2 rule 2, `M_X` may sit outside the target's tree (U1), so the target can fall outside `policy_root(M_X)`. D3's out-of-root outcome is still needed. Unscoped rules are `APPLIED` and scoped rules are `UNKNOWN` today (`path_selectors.py:229-240`). P2 narrows **where** D3 occurs (never when `M_R` exists) but does not decide it.
- **D4:** P2 is neutral. Which memory inside `R` counts as `M_R` is D4's question.
- **D1/D2/D7:** P2 is evaluated after each consumer's own start point. It does not unify selection across tools; D5 §5.3 already states this limit.
- **G3-B / ADR-033:** P2 is a precedence rule, not authority. An `M_R` chosen by P2 is still only a candidate memory. Verified protection still needs the G3-B binding of `(R, effective memory path)`. P2 does make that binding's "effective memory path" well defined under the override.
- **ADR-021:** P2 changes **which memory** is selected, not exit codes. Fail-open on transport and verdict errors is unchanged. Any blocking on `NO_MEMORY_SELECTED` would be a separate ADR-021 question.

## 8. Is C5 or C6 needed?

No. C5 (`export` in the Bash tool) and C6 (persistence after C3) test **who** can set the override. P2's outcome is the same whoever sets the variable, so C5/C6 cannot change the **choice of P2**. That is the only claim made here. The absence of C5/C6 is **not** evidence of bypass resistance: P2's protection remains conditional on correct boundaries and start points (§5). C5/C6 remain unauthorized and are not prerequisites for accepting this assessment.

## 9. Open decisions

| # | Decision | Recommendation |
|---|---|---|
| O1 | Adopt P2 as the D6 precedence rule for the `MNEME_MEMORY` env override | **Yes** |
| O2 | Missing or unreadable override with no `M_R`: `NO_MEMORY_SELECTED` (host-visible) vs. today's silent skip | `NO_MEMORY_SELECTED`, host-visible; exit-code policy unchanged (ADR-021) |
| O3 | Do constructor `memory=` and Codex `memory_override` follow P2? | **No, for now.** They are code-level choices by the embedding program, not ambient configuration that committed settings can reach. Record the selection source in the trace instead. Revisit only if an embedding exposes them to repository-controlled input. |
| O4 | Org-wide memory added on top of a repo memory | Defer to P3 / DG2 declared federation |
| O5 | V4/V5 characterization tests | They flip only under a P2 implementation charter, never before |

## 10. Acceptance vs. authorization

| Stage | Prerequisite | Status |
|---|---|---|
| **Q2 assessment acceptance** (P2 becomes the accepted D6 precedence *definition*) | Independent review of this document | **Pending** |
| **D5 implementation authorization** | Q2 accepted, plus D5 §5.1 verified host-visible channel, §5.4 planted-marker outcome, §7.4 L4 characterization test | Blocked |
| **D6 (P2) implementation authorization** | Q2 accepted, plus its own charter and Layer 1 freeze amendment (it changes `find_memory`), plus the same host-visible channel as D5 §5.1, plus the D5 §5.4 planted-marker outcome defined **including** the rule-2 override case | Blocked |

D5 and P2 both change `find_memory`. They **should share one implementation charter** so the stop rule and the precedence rule land together across every consumer. Landing them separately would leave a window in which, for example, the boundary exists but the override can still replace `M_R`.

**Next gate:** an independent review of this assessment. This document authorizes only itself.

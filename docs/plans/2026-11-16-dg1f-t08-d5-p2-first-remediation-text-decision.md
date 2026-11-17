# DG1F T-08 D5 + P2: `MEMORY_PATH_MISMATCH` remediation text under P2-first, architectural decision (PROPOSED)

**Status:** **PROPOSED**, for independent review and owner decision. Docs only. If accepted, it does three things:
1. it decides the direction for the remediation text;
2. it amends the D5+P2 charter's Amendment A2 to authorize exactly that one change (charter Amendment A2-RT, recorded in the charter header);
3. it revises the ADR-033 erratum to record the ADR-level change (ADR-033 erratum, "Remediation text").

It authorizes **no** code, test, freeze amendment, live run or runtime change (§7).

**Anchor:** `main` @ `191c0aca`.

**Revision 3 (2026-11-16):** answers the re-review of `966fff4b` (ACCEPT WITH CHANGES, N1–N5). Changes:
- O4's "before P2-first" claim is corrected: today, cause D needs two steps (N1);
- the A2-RT acceptance record and cross-references are added (N2);
- the ADR-033 erratum is made consistent (N3);
- the wording of the new line is fixed and covers a non-file at the path (N4);
- two nits are corrected (N5).

**Revision 2 (2026-11-16):** answered the independent review of `fc77eca1` (REQUEST CHANGES, F1–F7). Changes:
- the authorization route is rebuilt: an A2 charter amendment and an ADR-033 erratum revision, both carried in this PR and both accepted before the freeze amendment (F1, F2);
- the freeze supersession is completed (F3);
- the claim "today the line is correct" is withdrawn, because it is already wrong today in causes B and D. The recommendation moves from O2 to O4 (F4);
- the O3 analysis is corrected (F5);
- the verification scope and the test matrix are widened (F6), plus factual nits (F7).

**Why this note exists.** The owner accepted the [ADR-033 erratum](../adr/ADR-033-opt-in-fail-closed-enforcement.md#erratum-2026-11-16-mneme_memory-precedence-under-t-08-p2-first) (#810, `191c0aca`) on this condition:

> "The remediation-text issue must be resolved as an explicit architectural decision before P2-first implementation. Any behavior change must receive the appropriate ADR and Layer 1 freeze authorization."

**Inputs:**
- the D5+P2 charter [Amendment A2](2026-10-17-t08-d5-p2-memory-resolution-charter.md) (§5.2, P2-first). Owner acceptance is recorded in #809 (`84ee88b7`, reviewed head `818a1dea`); the charter's in-file status lines still read PROPOSED;
- the ADR-033 erratum (#810), and ADR-033 §7 ("Diagnostics identify the failure category, boundary and remediation");
- the [C2b charter](2026-10-21-reliable-enforcement-c2b-availability-authorization-charter.md): §5.3 routing, §8 ("one remediation line"), §17.6 ("stderr text" preserved);
- `docs/architecture/layer1-freeze-e73ff7d.md`: the Amendment Procedure, and the C2b Amendment 1 preserved items;
- `mneme/integrations/claude_code/availability.py` and `hook.py` at `191c0aca`.

## 1. Problem

On an `AUTHORIZED` refusal, `MEMORY_PATH_MISMATCH` prints one remediation line (`availability.py:164-165`, emitted at `:314-318`):

```text
unset MNEME_MEMORY or point it at the declared .mneme/project_memory.json
```

Whether the line is right depends on why the mismatch happened.

| Cause of the mismatch | Reachable today | Reachable under P2-first | Is the line right? |
|---|---|---|---|
| A. Declared memory present; `MNEME_MEMORY` names another memory | **Yes** (`find_memory` is env-first, `hook.py:202-206`) | **No** (row 2 ignores the override) | **Yes** |
| B. Declared memory missing; an ancestor memory found; `MNEME_MEMORY` unset | **Yes** | Yes (rows 1 and 2), whatever `MNEME_MEMORY` is | **No**: it tells the operator to unset a variable that is already unset |
| C. Declared memory missing; an ancestor memory found; `MNEME_MEMORY` set | No (the override wins) | Yes | **No**: unsetting it changes nothing |
| D. Declared memory missing; nothing found; `MNEME_MEMORY` names another file (row 6) | Yes | Yes | **No**: following it leads to `MEMORY_MISSING`, and restoring the declared memory is still needed |

Cause B was reproduced on `main` at `191c0aca` by the independent reviewer, and again by the author:
- **Layout:** authorization `AUTHORIZED`, `MNEME_MEMORY` unset, declared memory absent, a memory at the parent.
- **Result:** `MEMORY_PATH_MISMATCH`, with "remediation: unset MNEME_MEMORY or point it at the declared .mneme/project_memory.json."

**So the line is already wrong today in causes B and D, and P2-first adds cause C.** Restoring the declared memory is the fix in B, C and D. Unsetting `MNEME_MEMORY` is the fix only in A.

## 2. Invariant: under P2-first, a mismatch implies the declared memory is missing

**Claim.** With a valid local declaration at `R`, and once P2-first selection (charter §5.2.2) is in force: if `memory_mismatch` is true, then `R/.mneme/project_memory.json` is not a file. In other words, cause A cannot occur.

**Argument** (from source at `191c0aca`):

1. **The bound path is fixed.** A declaration whose `memory_path` is not `.mneme/project_memory.json` is invalid (`availability.py:67-68`, `MEMORY_PATH` at `:19`). An invalid declaration has `memory_path` `None`, and then `memory_mismatch` is false (`:111`).
2. **The declaration sits at the first `.mneme` directory on the walk** (`availability.py:43-56`). An inner `.mneme` directory with no `availability.json` yields no declaration at all.
3. **Both walks `resolve()` the same `start`** (`hook.py:2031-2036`, `:207`; `availability.py:50`). Only the direct-write path passes a declaration.
4. **If the declared memory is a file, the P2-first walk selects it.** The walk reaches `R` first, and the selection is then the declared memory under row 1 or row 2. There is no mismatch.
5. **Otherwise the selection comes from elsewhere:**
   - an ancestor memory (rows 1 and 2): a mismatch;
   - row 6: a mismatch;
   - row 7 or row 8: nothing is selected, which gives `MEMORY_MISSING`.

**Evidence.** The independent reviewer ran a 96-case simulation of P2-first selection per §5.2.2 on Windows, using the real `discover_declaration` and `memory_mismatch` at `191c0aca`. It found **no counterexample**. The cases covered:
- the declared memory present, missing, or a directory;
- an ancestor memory present or absent;
- `MNEME_MEMORY` unset, missing, foreign, equal as an absolute path, case-variant, or relative;
- an inner `.mneme` with no declaration, and an inner `.mneme` that is a file;
- start = `R`, start inside `R/.mneme`, and a start below `R` that does not exist;
- a junctioned `.mneme`, a junction in the start path, and a memory symlink pointing outside `R` or broken.

**Not verified:**
- the race in which the declared memory changes between the two walks;
- POSIX case sensitivity, where a case-variant override is a different file. That still meets the claim.

Under the recommended option (O4) the invariant is **not load-bearing**. O4 is correct whether or not it holds. It only explains why O4's second branch is unreachable after P2-first.

## 3. What else was checked and stays unchanged

- **The SS-3 stderr line** "SS-3 memory path mismatch; evaluation not bound to declaration." (`availability.py:280-281`) stays accurate. It prints when a valid declaration exists and the selected memory differs from the declared one, under every authorization state.
- **The C2b Amendment 1 proceed sentence** "The effective memory differs from the declared memory." (`:136-137`) stays accurate. It prints only under `AUTHORIZATION_UNVERIFIABLE` with no refusal (`:260-261`), and carries no remediation.
- **When the remediation line prints.**
  - It needs a refusal category, which requires `AUTHORIZED` (`:189`), and `detailed` output (`:314`).
  - `detailed` alone is not limited to `AUTHORIZED`: `baseline_label` is also set for `REVOKED` and `VERIFIED_ABSENT`. The category is what limits the line to `AUTHORIZED` refusals.
- **Every other remediation string is unaffected.** That covers `LOCAL_DECLARATION_TAMPERED`, `MEMORY_MISSING` and the check categories.
- **No test asserts the remediation text.**
  - C2b H7 (`test_availability_c2b.py:615`) checks the category and the generic "not a decision violation" marker.
  - The tests that compare full stderr (`test_availability_c2a.py:274`, `:447`, `:457`; `test_availability_c2b_am1.py:105`) run with no declaration or under `AUTHORIZATION_UNVERIFIABLE`. There, no remediation line prints.
- **Where the text is quoted:**
  - the ADR-033 erratum;
  - the D5+P2 charter §5.2.3, abbreviated. It stays accurate under O4, which keeps the old line for cause A;
  - historical validation artifacts, which are evidence of past runs and are not changed.
- **Out of scope:** under `AUTHORIZATION_UNVERIFIABLE` the check can still run against an ancestor memory when the declared one is missing. That is existing SS-3 "not bound" behavior, not a remediation question.

## 4. Options

### O1: Keep the text unchanged

- No behavior change.
- **Cost:** the line stays wrong in causes B and D today, and in B, C and D after P2-first, which is every post-P2-first case. In cause D, following it produces a second refusal, `MEMORY_MISSING`.

### O2: Replace the line with one static line

Proposed text:

```text
restore .mneme/project_memory.json from the baseline branch, replacing anything else at that path; while it is not a file, another memory is selected
```

- **Correct after P2-first** (by §2). **Wrong before P2-first in cause A**, where the declared memory exists.
- So it can only land atomically with the P2-first selection change.
- It depends on the §2 invariant holding.

### O3: Reorder routing, so that a missing declared memory refuses as `MEMORY_MISSING` before the mismatch check

- **How:** a new `AUTHORIZED`-only routing input to `refusal_category`, "declared memory not a file", checked before mismatch. `missing` and the `AUTHORIZATION_UNVERIFIABLE` path need not change; the check stops on `memory is None` in `hook.py:2037-2041`, not on `missing`.
- **Effect:** causes B, C and D refuse as `MEMORY_MISSING`, whose existing remediation is correct.
- **Cost:**
  - it changes C2b §5.3's R4/R5 order, which needs a C2b charter amendment;
  - it changes the reason codes recorded in future evidence;
  - it drops the SS-3 fact from the category, although a foreign memory **was** selected.

  ADR-033 §4.4 refuses in both rows and does not itself order them.

### O4: Choose the remediation at emit time (recommended)

When the category is `MEMORY_PATH_MISMATCH`, test whether the declared memory (`declaration.root / MEMORY_PATH`) is a file:
- **not a file** (causes B, C and D):

  ```text
  restore .mneme/project_memory.json from the baseline branch, replacing anything else at that path; while it is not a file, another memory is selected
  ```

- **a file** (cause A): the existing line, unchanged.

Properties:
- **After P2-first, correct in every cause.** Following the line once clears the mismatch in causes B, C and D. The second branch is unreachable (by §2) but harmless.
- **Before P2-first, an improvement, but not a one-step fix in cause D.** The override still wins before P2-first. Restoring the declared memory therefore leaves `MEMORY_PATH_MISMATCH` in place, and the old "unset" line then appears for the second step. That is why O4 lands with the P2-first implementation (§8), not before.
- **It does not depend on the §2 invariant** for its output in any single refusal.
- **Transient race:** if the declared memory appears between the memory walk and the emit-time check, the old line prints once. This is harmless.
- **Does not apply under `AUTHORIZATION_UNVERIFIABLE`:** no category is produced there, so no remediation line prints (`availability.py:189`).
- **Cost:** one extra filesystem test, only on an `AUTHORIZED` mismatch refusal that already refuses. Category, exit code, routing order, the SS-3 line and the proceed sentence are unchanged.
- **Constraints met:** ASCII, no paths beyond the existing constant, no submitted content (C2b §8; ADR-033 §7).
- **Exact wording is fixed** by this decision, as quoted above. It names restoring the declared memory as the fix and says to replace anything else at that path, for example a directory or a broken symlink. It does not tell the operator to unset `MNEME_MEMORY`, and it stays one line. The freeze amendment and the implementation use this exact string.

## 5. Recommendation

**O4.** After P2-first it is correct in every cause. Before P2-first it already improves causes B and D, which are wrong on `main` today. It does not depend on the §2 invariant. It changes one diagnostic line on one refusal and nothing else.

- **O2** is rejected because it is wrong before P2-first and so must land atomically with it.
- **O3** is rejected because it needs a C2b charter amendment and changes recorded reason codes.
- **O1** is the fallback if the owner prefers no text change. It would then be recorded in the ADR-033 erratum as an accepted limitation.

## 6. Authorization route (RT-3)

The Layer 1 freeze Amendment Procedure accepts a rationale only from a defect, an exit criterion, or "a charter amendment that has *already* been made elsewhere". It also says that behavioral changes get their own charter (`layer1-freeze-e73ff7d.md:2280-2287`). A2 limits the P2-first freeze amendment to P2 precedence, its stated consequences and the H1 notices (charter §5.2.6, §5.2.8). A deliberate new remediation line is none of those.

So the route is:

1. **This PR, if accepted.** All three items are accepted together, **before** the freeze amendment and the implementation:
   - this decision note;
   - **charter Amendment A2-RT** (a pointer in the D5+P2 charter header). It extends §5.2.6's "authorize only" list and §5.2.8 by exactly the §4 O4 remediation change, and nothing else;
   - **an ADR-033 erratum revision.** It replaces the erratum's "remediation strings are unchanged" and its open item with this decision. ADR-033 §7 makes remediation an ADR-level requirement without fixing the wording, and the erratum itself said "Changing those strings would be an ADR-033 behavior change". So the change is recorded at ADR level, not deferred to the code PR.
2. **The P2-first `[layer1-freeze]` amendment**, citing A2-RT. For this one line it supersedes:
   - C2b Amendment 1 preserved item 3 ("every existing stderr line");
   - C2b Amendment 1 preserved item 4 (`AUTHORIZED` … outputs);
   - the "stderr text" preservation in C2b charter §17.6.
3. **The P2-first implementation PR.** It changes `emit_availability`'s remediation selection only, plus the §7 tests. It records its merge commit in the ADR-033 erratum, as the erratum already requires.

## 7. Obligations for later PRs (not authorized here)

- **Freeze amendment:** the three supersessions in §6 step 2, for this line only.
- **Implementation PR:**
  - O4 in `emit_availability`, and no other diagnostic change;
  - tests asserting the new line in causes B, C and D, and the old line in cause A. Each runs before and after the P2-first selection change, where reachable;
  - a **layout-matrix test of the §2 invariant**, covering:
    - the declared memory present, missing, or a directory;
    - an ancestor memory present or absent;
    - `MNEME_MEMORY` unset, missing, equal, case-variant, relative or foreign;
    - start = `R` and start inside `R/.mneme`;
    - a symlinked memory, where the platform supports it.

    It asserts that `MEMORY_PATH_MISMATCH` occurs only when the declared memory is not a file;
  - these tests must use a `Verification` with a `tip` (a baseline), because tuple test verifiers never print the remediation line (`detailed` is false).
- **Live evidence PR** (charter §5.2.7 step 5): records the line wherever an `AUTHORIZED` mismatch is exercised.

## 8. Not decided or authorized here

- any code, test, freeze amendment, live run or runtime change;
- any change to categories, routing order, exit codes, the SS-3 line or the C2b Amendment 1 proceed text;
- landing O4 separately from the P2-first implementation. Fixing causes B and D on their own before P2-first would need its own charter, and it is not proposed.

## 9. Decisions requested

| # | Decision | Recommendation |
|---|---|---|
| RT-1 | Direction for the `MEMORY_PATH_MISMATCH` remediation text | **O4**: choose the line at emit time from whether the declared memory is a file. O1 is the fallback; O2 and O3 are rejected. |
| RT-2 | Accept the §2 invariant as a fact about P2-first, tested by the §7 layout matrix | **Yes**. O4 does not depend on it. It explains why O4's second branch is unreachable after P2-first. |
| RT-3 | Authorization route | §6: this PR carries charter Amendment A2-RT and the ADR-033 erratum revision, both accepted before the freeze amendment. The freeze amendment then supersedes C2b Am1 items 3 and 4 and C2b §17.6 "stderr text" for this line only. |

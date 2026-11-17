# DG1F T-08 D5 + P2: P2-first `MEMORY_PATH_MISMATCH` remediation text, architectural decision (PROPOSED)

**Status:** **PROPOSED**, for independent review and owner decision. Docs only. It decides a direction. It authorizes **no** code, test, string change, freeze amendment, ADR change, live run or runtime change (§7).

**Anchor:** `main` @ `191c0aca`.

**Why this note exists.** The owner accepted the [ADR-033 erratum](../adr/ADR-033-opt-in-fail-closed-enforcement.md#erratum-2026-11-16-mneme_memory-precedence-under-t-08-p2-first) (#810, `191c0aca`) on one condition:

> "The remediation-text issue must be resolved as an explicit architectural decision before P2-first implementation. Any behavior change must receive the appropriate ADR and Layer 1 freeze authorization."

This note is that decision point.

**Inputs:**
- the accepted D5+P2 charter [Amendment A2](2026-10-17-t08-d5-p2-memory-resolution-charter.md) (§5.2, P2-first; #809, `84ee88b7`);
- the ADR-033 erratum (#810): Consequences, "Remediation text" and the open item;
- the [C2b charter](2026-10-21-reliable-enforcement-c2b-availability-authorization-charter.md): §5.3 routing (R4 before R5), §8 diagnostics ("one remediation line"), §17 (Amendment 1);
- `mneme/integrations/claude_code/availability.py` and `hook.py` at `191c0aca`.

## 1. Problem

The `MEMORY_PATH_MISMATCH` refusal prints one remediation line (`availability.py:160-165`, emitted at `:314-318`):

```text
unset MNEME_MEMORY or point it at the declared .mneme/project_memory.json
```

**Today the line is correct.** `find_memory` checks the environment first (`hook.py:202-206`). The common SS-3 case is a `MNEME_MEMORY` that names another memory while the declared memory exists, and unsetting the variable fixes it.

**Under P2-first it is wrong in every case.** The ADR-033 erratum describes two layouts in which the line no longer fixes the refusal: row 6, and the declared memory missing with an ancestor memory present. §2 shows that, once P2-first lands, **these are the only ways `MEMORY_PATH_MISMATCH` can arise**.

## 2. Invariant: under P2-first, a mismatch implies the declared memory is missing

**Claim.** With a valid local declaration at `R`, and once P2-first selection (charter §5.2.2) is in force: if `memory_mismatch` is true, then `R/.mneme/project_memory.json` is not a file.

**Argument** (from source at `191c0aca`):

1. **The bound path is fixed.** A declaration whose `memory_path` is not `.mneme/project_memory.json` is invalid (`availability.py:67-68`, with `MEMORY_PATH` at `:19`). `memory_mismatch` compares the selected memory against `R/.mneme/project_memory.json` after `resolve()` (`:110-113`).
2. **The declaration sits at the first `.mneme` directory on the walk.** `discover_declaration` inspects only the first ancestor of the start that contains a `.mneme` directory (`availability.py:43-56`; "an outer declaration is intentionally hidden by an inner .mneme directory"). So no `.mneme` directory exists between the start and `R`.
3. **Both walks share a start.** The direct-write path passes one `start` to `discover_declaration` and `find_memory` (`hook.py:2031-2036`). P2-first leaves start points unchanged (I5).
4. **If the declared memory is a file, it is selected.**
   - The P2-first walk (rows 1 and 2) checks `cur/.mneme/project_memory.json` at each directory from the start upward.
   - By point 2, the first directory with a `.mneme` directory is `R`.
   - If `R/.mneme/project_memory.json` is a file, the walk selects it, and `MNEME_MEMORY` is ignored or equal (row 1 or row 2).
   - So the selected memory is the bound path, and there is no mismatch.
5. **Otherwise the selection comes from elsewhere.** If that file is not a file, the walk continues above `R`. It either:
   - selects an ancestor memory (rows 1 and 2 on an ancestor: **mismatch**); or
   - finds nothing, in which case:
     - row 6 selects an existing `MNEME_MEMORY` file (**mismatch**, unless it names the bound path, which is not a file);
     - row 7 or row 8 select nothing (`MEMORY_MISSING`).
6. Hence a mismatch requires the declared memory to be missing.

**Not verified here:** filesystem edge cases on the bound path:
- a symlink whose target is outside `R`, or a broken one;
- Windows case or `resolve()` differences between the two walks;
- a race in which the file disappears between the two walks.

The implementation PR must cover the invariant with a layout-matrix test (§6).

**Consequence.** After P2-first, a static remediation line can be correct for **every** `MEMORY_PATH_MISMATCH`. Restoring the declared memory is always the fix:
- restoring it makes the walk select it (point 4);
- unsetting or repointing `MNEME_MEMORY` never resolves the refusal on its own. It only changes row 6 into row 7 or row 8, and so into `MEMORY_MISSING`.

## 3. What else was checked and stays unchanged

- **The SS-3 stderr line** "SS-3 memory path mismatch; evaluation not bound to declaration." (`availability.py:280-281`) is still accurate. It is emitted under every authorization state when a declaration exists.
- **The C2b Amendment 1 proceed sentence** "The effective memory differs from the declared memory." (`:136-137`) is still accurate. It is emitted only under `AUTHORIZATION_UNVERIFIABLE` with no refusal (`:260-261`). It carries no remediation.
- **When the remediation line is printed.** Only with detailed output, meaning `AUTHORIZED` with a baseline or a local relation (`:314-318`). So the problem is confined to `AUTHORIZED` refusals.
- **Every other remediation string** (`LOCAL_DECLARATION_TAMPERED`, `MEMORY_MISSING`, the check categories) is unaffected by P2-first.
- **No test asserts the remediation text.** Tests assert categories and exit codes (for example C2b H7 at `test_availability_c2b.py:615`). The text is pinned by no ADR and no charter: C2b §8 requires "one remediation line" without wording. It is quoted only in the ADR-033 erratum and in historical validation artifacts. The artifacts are evidence of past runs and are not changed.
- **Out of scope:** under `AUTHORIZATION_UNVERIFIABLE` (C2b R2), the check can still run against an ancestor memory when the declared one is missing. That is existing SS-3 "not bound" behavior, and it is already reachable today through parent discovery with `MNEME_MEMORY` unset. It is not a remediation question.

## 4. Options

### O1: Keep the text unchanged

- **No behavior change.** No freeze or ADR cover is needed beyond what the P2-first freeze already requires.
- **Cost:** after P2-first, every `MEMORY_PATH_MISMATCH` remediation points the operator at the wrong fix (§2). Following it in row 6 produces a second refusal, `MEMORY_MISSING`, before the real fix. In the ancestor layout it does nothing.
- This is the status quo the erratum's open item flags.

### O2: Replace the `MEMORY_PATH_MISMATCH` line with one static line, atomically with P2-first (recommended)

- **Proposed text** (ASCII, no paths beyond the existing constant, no submitted content; C2b §8):

  ```text
  restore .mneme/project_memory.json from the baseline branch; while it is missing, another memory is selected
  ```

  Exact wording is open to the reviewer. The constraints are:
  - restoring the declared memory is the first and sufficient action;
  - the line does not tell the operator to unset `MNEME_MEMORY`;
  - it stays one line.
- **Atomic with P2-first.** It must land in the **P2-first implementation PR**, never before, because the old line is correct until the P2-first selection change.
- **Behavior change.** One stderr line on an `AUTHORIZED` refusal. Category, exit code, refusal order, the SS-3 line and the proceed sentence are unchanged.
- **Authorization it needs:**
  - **ADR:** ADR-033 does not specify remediation text, so its decision is unchanged. The implementation PR, which already must update the erratum's header and §4.1 pointer, also replaces the erratum's "remediation strings are unchanged" and its open item with a reference to this decision and the new line. No ADR-033 amendment is needed.
  - **Freeze:** the P2-first `[layer1-freeze]` amendment adds this one string to its supersession of C2b Amendment 1 preserved item 3 ("every existing stderr line"). Charter §5.2.6 already supersedes item 3 for the P2-first consequences.
  - **Charter:** none. C2b §8's "one remediation line" still holds.

### O3: Reorder routing, so that a missing declared memory refuses as `MEMORY_MISSING` before the mismatch check

- **Effect:** in both layouts, the category becomes `MEMORY_MISSING`, whose existing remediation ("restore .mneme/project_memory.json from the baseline branch") is correct.
- **Cost:**
  - It changes C2b §5.3's R4/R5 order and how ADR-033 §4.4 is read, which needs an ADR-033 amendment and a C2b charter amendment.
  - It hides the SS-3 fact from the category. A foreign memory **was** selected.
  - It changes recorded reason codes in future evidence.
  - It means redefining `missing` from "nothing selected" to "declared memory not a file". That also changes the `AUTHORIZATION_UNVERIFIABLE` path, where a missing memory today stops the check.
- Larger than the problem needs.

### O4: Compute the remediation at emit time (check whether the declared memory is a file)

- **Effect:** the same text as O2 in every post-P2-first case, by §2.
- **Cost:** a second filesystem check in the refusal path, plus a branch that the invariant makes dead after P2-first. Its only advantage over O2 is robustness if §2's invariant failed. The §6 test guards against that more cheaply.

## 5. Recommendation

**O2.** It is the smallest change that makes the remediation correct in every case P2-first can produce:
- one static string, landed atomically with P2-first;
- covered by the P2-first freeze amendment and an update to the ADR-033 erratum;
- no change to categories, ordering, exit codes or the C2b contract.

O3 is rejected as disproportionate. O4 is rejected because the invariant plus a test is enough. O1 is the fallback if the owner prefers zero text change, and it would then be recorded as an accepted limitation in the erratum.

## 6. Obligations if O2 is accepted (for later PRs; not authorized here)

- **P2-first `[layer1-freeze]` amendment:** list the `MEMORY_PATH_MISMATCH` remediation string under the C2b Amendment 1 item 3 supersession, with this note as the authority.
- **P2-first implementation PR:**
  - change the string in `_REMEDIATION` only;
  - add tests asserting the new line in both layouts (row 6, and the ancestor layout);
  - add a **layout-matrix test of the §2 invariant**: across declared-memory present or missing, ancestor memory present or absent, `MNEME_MEMORY` unset, missing, equal or foreign, assert that `MEMORY_PATH_MISMATCH` occurs only when the declared memory is not a file;
  - update the ADR-033 erratum's "Remediation text" bullet and open item to cite this decision and the merged line.
- **The live evidence PR** (charter §5.2.7 step 5) records the new line wherever an `AUTHORIZED` mismatch is exercised.

## 7. Not decided or authorized here

- any code, test, string change, freeze amendment, ADR change, live run or runtime change;
- the P2-first freeze amendment itself, or the implementation;
- any change to categories, routing order, exit codes, the SS-3 line or the C2b Amendment 1 proceed text;
- the edge cases listed under §2 "Not verified here".

## 8. Decision requested

| # | Decision | Recommendation |
|---|---|---|
| RT-1 | Direction for the P2-first `MEMORY_PATH_MISMATCH` remediation text | **O2**: one static line, landed atomically with the P2-first implementation. O1 is the fallback; O3 and O4 are rejected. |
| RT-2 | Accept the §2 invariant (under P2-first, a mismatch implies the declared memory is missing) as the basis for a static line, conditional on the §6 layout-matrix test | **Yes** |
| RT-3 | Authorization route for O2 | P2-first freeze amendment (C2b Am1 item 3) plus an update to the ADR-033 erratum in the implementation PR. No ADR-033 amendment, because ADR-033 does not specify remediation text. |

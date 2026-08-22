# P0 Investigation: R1–R6 Architecture Lineage Reconciliation

Status: **investigation complete; P0 CLOSED — Class B verdict accepted at review 2026-08-22**
Date: 2026-08-22
Mode: read-only; no production, retrieval, enforcement, or validation-evidence files were modified.
Verdict: **Class B (experimental-only implementation) with an additional retrieval-provenance defect.**

---

## 1. Current-state baseline (frozen at investigation start)

| Item | Value |
|---|---|
| Working copy | `C:\dev\mneme` |
| HEAD at investigation start | `52cc83754039ef4ebfb3f0a1f2a1be94eea484d3` (branch `feat/agent-sdk-adoption-surfaces`) |
| `main` / `origin/main` | `52cc8375` (identical) |
| Referenced baseline `f7eac387` | ancestor of `main`; two commits behind tip (`e7ec1dcc` #294 ox-compaction; `52cc8375` Agent SDK adapter) |
| Uncommitted changes | untracked plan/research/site/script documents only; **no production (`mneme/`, `tests/`) changes** |
| Tags | `v0.1-mneme-harness` … `v0.5.1` |
| Worktrees | 17 registered worktrees under `.claude/worktrees/`, `.worktrees/`, plus release copy |
| Production guidance path at `52cc8375` | `MemoryStore → DecisionRetriever → format_decisions()` top-N (`mneme/context_builder.py:129`, `mneme/pipeline.py:118`) |
| `classify_guidance_roles()` in production tree | **absent** (source search + all worktrees + full Git object space) |

---

## 2. Chronological lineage R1 → R6

All dates from lock/result documents and commit metadata.

| Stage | Date | Claimed state | Evidence artifact |
|---|---|---|---|
| R1 | ≤2026-08-13 | Role semantics frozen; **no runtime implementation** (`"R1_LOCKED_NO_RUNTIME_IMPLEMENTATION"`) | `docs/validation/pre-generation-guidance-role-r1-lock.json` |
| R2 | 2026-08-13 | Classifier frozen; `"production_build_guidance_wiring": false` | `pre-generation-guidance-role-r2-lock.json` |
| R3 | 2026-08-13 | Pure `classify_guidance_roles()` added in `mneme/guidance_roles.py` (SHA-256 `CEB4D88D…`); explicitly **not yet imported** by production formatter or hook | `pre-generation-guidance-role-r3-lock.json` / `-r3-result.md` |
| R4 | 2026-08-13 | `build_guidance()` wired to classifier; full suite claimed **624 passed / 5 skipped**; claims `DecisionRetriever` unchanged | `pre-generation-guidance-role-r4-lock.json` / `-r4-result.md` |
| R5 | 2026-08-14 | Mechanical validation PASS; candidate file hashes frozen for R6 | `pre-generation-guidance-role-r5-lock.json` |
| R6 | 2026-08-14T14:35Z (lock); trials 2026-08-14 | Mechanism-isolation campaign executed; gate **FAIL** (permanently, per closeout) | `pre-generation-guidance-role-r6-execution-lock.json`; `artifacts/pre-generation-guidance-role-r6-2026-08-14/` |
| Closeout | 2026-08-16 | "experiment closed; **implementation retained**"; links `../architecture/pre-generation-guidance-role-contract.md` | commit `f0f74de4`, made directly on `main` |
| Divergence recorded independently | 2026-08-22 | ox-compaction experiment excludes the role path and records it as absent at `f7eac387`, present "only in a divergent sibling working copy" | PR #294, commit `e7ec1dcc`; `validation/ox-compaction/experiment-lock.json` |

---

## 3. File / blob / commit evidence

### 3.1 The role-aware implementation never entered any commit

- Pickaxe over every ref:
  `git log --all -S 'guidance_roles'` and `-S 'build_guidance'` return exactly three commits —
  `f0f74de4` (#closeout docs), `95bd2d53` (validation branch), `e7ec1dcc` (#294). **All are documentation commits. No code commit ever contained either symbol.**
- The linked architecture contract `docs/architecture/pre-generation-guidance-role-contract.md`
  was **never committed on any ref**: `git log --all -- '*pre-generation-guidance-role-contract*'` is empty.
  The closeout's only link target is a phantom path in canonical `main`.
- Exhaustive dangling-object scan (`git fsck --lost-found --no-reflogs`): all **83 dangling commits**
  checked via `git ls-tree -r <commit>`; all ~40 dangling blobs checked by content.
  **None contains `guidance_roles` or `build_guidance`.** The implementation is unrecoverable from this repository's Git object database.
- Filesystem sweep of all 17 registered worktrees and all sibling directories under `C:\dev`: zero hits.

### 3.2 The implementation survives in a divergent sibling clone

A second clone of the same repository exists at:

```
C:\Users\hi\OneDrive\Documents\mneme        (HEAD = f0f74de4 — same closeout commit)
```

Its implementation surface exists there **entirely as untracked/uncommitted files**, with SHA-256 values that match the frozen locks byte-for-byte:

| File | Measured SHA-256 (OneDrive copy) | Frozen in locks |
|---|---|---|
| `mneme/guidance_roles.py` | `CEB4D88D5D65…B22C6694` | R3, R4, R5, R6 execution, storage-2x2, production-effectiveness locks — **exact match** |
| `tests/test_guidance_roles.py` | `4E206D7EB8A0…C8AAEB2` | R3, R4 locks — **exact match** |
| `mneme/guidance.py` | `A74C69EA2946…FEABFA` | R6 execution lock — **exact match**; contains `build_guidance()` (:185) calling `classify_guidance_roles(selected)` (:213) |
| `mneme/integrations/claude_code/guidance_hook.py` | `A3F55FAD4A22…E3BB` | R6 execution lock — **exact match**; imports `build_guidance` |
| `pyproject.toml` | `DFC819003401…9F` | R6 execution lock — **exact match** |
| `mneme/decision_retriever.py` | `F86B3BA2E50B…882` | R6 execution lock — **exact match** ⚠️ see §3.3 |
| `docs/architecture/pre-generation-guidance-role-contract.md` (+ charter, classifier-design) | untracked, present | referenced by closeout; **never committed anywhere** |

Also untracked in the same tree: all guidance eval scripts (`scripts/run_guidance_*.py`), fixtures (`tests/fixtures/guidance_*`), and guidance test modules.

### 3.3 Retrieval-provenance defect: the experiment retriever ≠ canonical retriever

The R6-frozen `mneme/decision_retriever.py` (`F86B3BA2…`) differs from canonical `main`'s retriever
(canonical hash `8EA03377…`). The delta is an **uncommitted scoring change**: a new `"rules": 1.5`
token-overlap term over typed-rule values, added to `_WEIGHTS` and `_score_fields()`.
Canonical `main` has no `"rules"` term (`git show main:mneme/decision_retriever.py` — absent).

Consequence: **R4–R6 executed against a retrieval scorer that has never existed in canonical `main`.**
This does not alter the frozen R6 FAIL verdict, but it means the campaign's baseline was not the
canonical production path even before considering role-awareness.

---

## 4. Experiment-to-code provenance table

| Experiment | Executed in source tree | Evidence |
|---|---|---|
| Live A/B (2026-08-13), Confirmatory (2026-08-13) | OneDrive sibling copy | run artifacts reference plugin fixtures under `C:\Users\hi\OneDrive\Documents\mneme\...` |
| R4 (2026-08-13) | OneDrive sibling copy | R4-frozen hashes (`guidance_roles.py`, `test_guidance_roles.py`) match that tree's current untracked files byte-for-byte |
| R5 (2026-08-14) | OneDrive sibling copy | R5 lock freezes same hashes; status `R5_LOCKED_READY_FOR_R6` |
| R6 (2026-08-14) | OneDrive sibling copy — **proven directly** | R6 trial `metadata.json` records plugin path `C:\Users\hi\OneDrive\Documents\mneme\tests\fixtures\guidance_confirmatory\mechanism_plugin`; committed execution lock SHA-256 `D691FC8D…` matches metadata `execution_lock_sha256`; all 18 `candidate_files` hashes match that tree |
| Storage 2x2, Production-effectiveness (2026-08-14/16) | Same tree (same locked hashes, incl. `CEB4D88D…`) | lock manifests |
| ox-compaction (2026-08-21/22) | `C:\dev\mneme` @ `f7eac387` | deliberately excluded the role path; documented the divergence |

Provenance is therefore **not** in question (rules out verdict class C): every lock's file hashes resolve to a real, still-existing tree, and R6's own runtime metadata names that tree.

---

## 5. Contradiction matrix

| # | Claim (source) | Repository reality | Verdict |
|---|---|---|---|
| 1 | Closeout: "experiment closed; **implementation retained**" (`f0f74de4`, line 3) | Implementation never committed to any ref; absent from `main` then and now | **FALSE w.r.t. canonical main**; true only of the OneDrive working copy |
| 2 | Closeout links `../architecture/pre-generation-guidance-role-contract.md` | File never committed on any ref; exists only untracked in OneDrive copy | **FALSE** (dangling link) |
| 3 | Closeout §Code-quality audit describes retained `classify_guidance_roles()` / `build_guidance()` | Code exists only in OneDrive copy, hash-matched to locks | **MISLEADING** — accurate about the experiment tree, not about production |
| 4 | R4 result: "`DecisionRetriever` … unchanged"; boundaries preserved | R4–R6 ran on retriever `F86B3BA2…` containing a typed-rule scoring term absent from every commit of `main` | **FALSE relative to canonical lineage** (unchanged only vs. its own local prior state) |
| 5 | R4 result: suite 624 passed / 5 skipped | Not independently reproducible today (implementation absent from any committable state); plausible but unverifiable | **UNVERIFIABLE** |
| 6 | R3 result: classifier not yet wired into production formatter/hook | Consistent with all evidence | TRUE |
| 7 | R6 = permanent FAIL | No one proposes reinterpretation; FAIL stands | TRUE (unchanged) |
| 8 | PR #294 / ox-compaction: role path "NOT present at frozen SHA f7eac387; exists only in a divergent sibling working copy" | Confirmed by this investigation, with the sibling identified by path | **TRUE** |
| 9 | Current architecture: retrieval mechanics frozen | Canonical `main` honors this; the experiment tree did not | TRUE for `main`; experiment operated outside it |

---

## 6. Root cause

On 2026-08-16 the closeout commit `f0f74de4` ("docs: close production guidance effectiveness experiment")
was created **from the OneDrive sibling working copy** (it is that clone's HEAD). It committed the
validation documentation and artifacts — while the entire role-aware implementation surface
(`guidance_roles.py`, `guidance.py`, `guidance_hook.py`, tests, fixtures, eval scripts, and the three
architecture contract documents) remained **untracked** in that clone and was therefore never staged,
never committed, and never pushed.

The closeout's phrase "implementation retained" described the private working copy, but the document
entered canonical `main` where readers can only interpret it as describing the production lineage.
No disappearance event occurred (rules out class A): **the code never entered the canonical lineage at all.**

---

## 7. Verdict

**Class B — experimental-only implementation, with an additional retrieval-provenance defect.**

- **Primary (B):** R1–R6 ran against an unmerged experimental clone whose role-aware implementation
  never entered canonical production. The closeout's "implementation retained" claim is wrong w.r.t. `main`.
- **Retrieval-provenance defect (additional finding, the most consequential new fact beyond the original
  P0):** R4–R6 used not only role-aware guidance but also a **non-canonical `DecisionRetriever`**
  (`F86B3BA2…`, typed-rule scoring term absent from every commit of `main`). The experiment was therefore
  a **configuration**, not merely a formatter change: one cannot transplant the role-aware code onto
  canonical retrieval and assume one is reproducing the R6 candidate. Class D does not apply — all stages
  resolved to one coherent experimental lineage; the divergence is from production, not between R stages.
- **Not C:** provenance is proven — locks, artifacts, and run metadata all resolve to one concrete tree.
- The R6 FAIL remains frozen and untouched by this finding.

### Claim boundary of the R1–R6 evidence

The evidence remains valid but its scope shrinks: it is evidence about an **experimental candidate
configuration**, not about the shipped Mneme production path (`format_decisions()` on canonical
retrieval). The frozen R6 FAIL applies to that candidate and must not be presented as an evaluation of
current production behavior.

---

## 8. Answers to the six acceptance questions

1. **What exact source tree executed R4?**
   `C:\Users\hi\OneDrive\Documents\mneme` (clone of this repo, later HEAD `f0f74de4`). Evidence: R4-locked SHA-256s match that tree's files byte-for-byte.
2. **What exact source tree executed R6?**
   Same tree — proven directly by R6 trial `metadata.json` plugin paths plus the full 18-file `candidate_files` hash match and the committed lock's `D691FC8D…` digest matching run metadata.
3. **Did that tree contain the role classifier and role-aware formatter?**
   Yes — `mneme/guidance_roles.py` (`CEB4D88D…`), `build_guidance()` wiring in `mneme/guidance.py` (`A74C69EA…`, lines 185/213), hook import in `guidance_hook.py` (`A3F55FAD…`). All hash-verified against frozen locks.
4. **Was that implementation ever part of canonical `main`?**
   No. Pickaxe across all refs, all 83 dangling commits, and all dangling blobs find zero code commits containing it. Only documentation commits mention these symbols.
5. **Why is it absent from `f7eac387` today?**
   Because it was never committed. `f0f74de4` captured only tracked/staged files from the OneDrive clone; the implementation stayed untracked there. There is no revert, overwrite, or loss event to find.
6. **Which state should now be treated as authoritative, and why?**
   Canonical `main` (`format_decisions()` top-N path) remains the **authoritative production behavior** — it is the only lineage that satisfies the repo's merge discipline, CI gates, packaging, and the frozen-retrieval architecture. The role-aware implementation is authoritative only as **validated experimental evidence** (hash-pinned, R6 FAIL included). Neither evidence may be discarded, but neither promotes itself into production without a prospective architecture decision.

---

## 9. Minimal remediation recommendation (not implemented here)

Ordered, narrowly scoped, each a separate PR:

1. **Preserve the experimental tree immediately (P0 follow-up — single point of failure).**
   The sole copy of the validated implementation lives in one uncommitted OneDrive folder. A tag cannot
   preserve untracked files. Create a deliberately **post-hoc archival branch**:
   `archive/r1-r6-experimental-tree-2026-08-22`, committing those files verbatim with their locked
   SHA-256s recorded in the commit message, and stating explicitly in the commit and branch description
   that the snapshot was created **after** the experiment solely to preserve exact bytes, was never
   production lineage, and is not historical experiment lineage. Keep it unmerged. This preserves
   validation evidence; it does not touch `DecisionRetriever` or anything on `main`.
2. **Docs-only reconciliation PR.** Correct `pre-generation-guidance-closeout.md`:
   restate "implementation retained" as "campaign executed on an unmerged experimental tree, preserved
   by archival snapshot"; repair or remove the phantom architecture-contract link; explicitly record the
   non-canonical retriever (`F86B3BA2…`). Do not rewrite the frozen R1–R6 locks, results, or artifacts.
3. **Close P0.** Canonical `main` becomes unquestionably authoritative for future work.
4. **Then open P1 retrieval precision against canonical `main`.**
   Do not use the OneDrive retriever as a starting point.
5. **If role-aware guidance is reconsidered later, treat it as a new prospective feature.**
   Reimplement and review it against canonical code rather than "restoring" the OneDrive tree.
   Amendment boundary:
   - Restoring role-aware **presentation** does not inherently require a retrieval amendment if it
     operates strictly after canonical retrieval and demonstrably does not alter scores, ranking, K,
     selection IDs, or retrieval semantics (per ADR-017, retrieval is the context-injection ranking
     layer, separate from enforcement).
   - The experimental typed-rule scoring term (`"rules": 1.5` overlap weight) **absolutely requires an
     explicit amendment** before any adoption, since it modifies `DecisionRetriever` scoring itself.

Explicitly **not** recommended: silently re-committing the OneDrive tree onto `main`, treating the
archival snapshot as experiment lineage, editing any lock, result, or artifact to match current code,
or reopening R6.

---

*Investigation boundary compliance: `DecisionRetriever` untouched; no retrieval/K/threshold/scoring changes; no enforcement or `ConflictDetector` changes; R6 not rerun; no R7; no validation evidence edited.*

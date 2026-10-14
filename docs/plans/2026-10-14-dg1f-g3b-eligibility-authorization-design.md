# DG1F — G3-B: eligibility / authorization contract design (assessment)

**Status:** architecture **assessment and recommendation**, not a charter,
approval, or implementation plan. It authorizes **no** runtime change, no new
decision authority, no ADR-033 acceptance/amendment, and no Layer 1 unfreeze.
**Source anchor:** `MnemeHQ/mneme` `main` at
`f7f3a9afbf2144318d5042b81bd04e018e57e8e0` (G3 assessment, PR #511).
**Governing contracts:** [ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md)
(single canonical decision authority), [ADR-021](../adr/ADR-021-shell-preflight-and-stop-session-delta.md),
the [G3 assessment](2026-10-14-dg1f-g3-missing-memory-eligibility-assessment.md),
and the [blocking-semantics matrix](2026-10-14-dg1f-adversarial-blocking-semantics-matrix.md).

## 1. The question

> Where should the independently verifiable authorization to **fail closed**
> live, and how can Mneme verify it when canonical memory is missing?

G3 established that a repository's decision memory can disappear, and that git
history can, at best, speak to *whether memory once existed* (Question A) — not
to *whether fail-closed was authorized* (Question B). G3-B designs the artifact
that answers Question B.

## 2. Design requirements

| # | Requirement | Meaning |
|---|---|---|
| **R1 Declaration** | What constitutes explicit authorization, and who can issue/revoke it? | An explicit, human-issued, review-gated statement — never inferred from memory or transport. |
| **R2 Trust boundary** | How is it protected from the governed agent? | It must not be silently forgeable/removable by the agent under governance. |
| **R3 Project identity** | How is it bound to the correct repo root and effective memory path? | Bound to the intended repository root and the exact memory path (`MNEME_MEMORY`/discovery are ambiguous — G3 §4.2). |
| **R4 Verification** | What happens when the declaration, trusted revision, or verifier is unavailable? | Fail to the *inactive/available* state, never to a fabricated *pass*; never silently fail closed on an unverifiable declaration. |
| **R5 Compatibility** | Coexist with `setup → active` and ADR-030's single decision authority. | It is **configuration/authorization**, not a competing canonical decision store. |

## 3. The ADR-030 boundary — authorization is not a second decision authority

ADR-030 forbids a second **canonical decision authority** ("No second canonical
file, database, hosted service, ORM, graph database, or other persistence
layer"). It does not forbid every independently managed configuration artifact.
An **eligibility/authorization declaration** answers *"may this repo refuse
operations when enforcement is unavailable?"* — it carries **no decisions, no
rules, no lifecycle, no authority over which decisions govern**. That is the
distinction that keeps R5 satisfied: the declaration is a **policy switch**, not
a decision source.

## 4. Candidate authorization mechanisms

Evaluated against R1–R5. Durability = survives memory deletion; trust = not
agent-forgeable; identity = bindable to repo root + memory path.

| # | Mechanism | Durable | Trust boundary | Identity binding | Compatibility | Failure modes |
|---|---|---|---|---|---|---|
| **M1** | Field in `project_memory.json` (e.g. `activation.fail_closed`) | **No** | the file itself | in-file | native | disappears with the file — the exact case; rejected |
| **M2** | **Separate committed declaration** under `.mneme/` (e.g. `.mneme/eligibility.json`), review-gated | Yes (if committed) | **git + review**; a trusted revision must be verified | explicit `repo_root` + `memory_path` | config, not decision authority | agent can edit the local copy → must verify a trusted revision |
| **M3** | Field in an existing non-decision config (`.claude/settings.json`, CI config) | Yes | transport config; **agent-editable** | weak | overlap with transport | conflates transport with authority; rejected as the authority |
| **M4** | Git ref (annotated/signed tag or protected branch) | Yes | **remote git** (strongest local-resistant) | ref ↔ repo | orthogonal to decisions | needs a trusted remote; heavier UX |
| **M5** | Hook/plugin registration only | Yes | agent-editable | none | transport | not authority (G3 §4) |
| **M6** | External/hosted declaration | Yes | remote service | server-side | **out of scope** (no hosted service, ADR-030) | n/a |

## 5. Recommended contract (bounded)

**Recommend M2 as the primary mechanism, with M4 as an optional hardening
layer.**

1. **Declaration (R1):** a small, explicit, human-authored, review-gated
   artifact under `.mneme/` — a *policy switch* stating that this repository
   authorizes fail-closed behavior when enforcement is unavailable. It is
   created/revoked only by an explicit Mneme-owned authority action (never by an
   agent, producer, or inference).
2. **Trust boundary (R2):** the declaration is authoritative only when bound to
   a **trusted revision** that is independently verified (for example present in
   the reviewed HEAD, or pinned to a protected ref/tag — M4). The local working
   copy alone is never sufficient.
3. **Project identity (R3):** the declaration records the **repository root**
   and the **effective memory path** it applies to; a declaration that does not
   match the resolved root/path is not honored.
4. **Verification (R4):** if the declaration, its trusted revision, or the
   verification mechanism is unavailable or ambiguous, the result is the
   **inactive/available** state — never a fabricated *pass*, and never a silent
   fail-closed on an unverifiable declaration.
5. **Compatibility (R5):** it is configuration, not a second decision authority;
   it carries no decisions/rules/lifecycle and never determines which decisions
   govern. It coexists with `setup → active` (which concerns *protection
   installation*, a different axis).

## 6. Failure-state matrix

`D` = declaration present & valid at a trusted revision · `M` = canonical memory
present & valid · `V` = verification of the trusted revision available.

| D | M | V | Outcome |
|---|---|---|---|
| absent | present | n/a | normal enforcement (today's behavior) |
| absent | absent | n/a | **inactive** (never protected) — today's silent skip, surfaced as inactive |
| present | present | yes | normal enforcement |
| present | absent | yes | **fail closed** (protected repo whose memory disappeared) — *the G3-B target* |
| present | absent | no | **operational error / inactive** — report "authorization unverifiable"; never silently pass, never block on an unverified declaration |
| present (invalid/expired) | * | * | **operational error**; never fail closed, never pass |

The target cell is row 4: a *verified* declaration plus *missing* memory is the
only combination that may fail closed.

## 7. Explicit non-authorization and sequence

This assessment implements nothing. It does not add a declaration file, change
`setup → active`, alter hooks/CI, amend ADR-033, or unfreeze Layer 1. DG1F-C1b
stays locked; DG1B2 stays evidence-gated; the G1 harness matrix is not expanded.

**Sequence:** G3-B design (this doc) → architectural decision on M2 (+ optional
M4) → **ADR-033 reconciliation** → bounded implementation charter + matching
`[layer1-freeze]` amendment. Fail-closed behavior may not be introduced before
project-scoped authorization can be independently established.

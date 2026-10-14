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
| **R2 Trust boundary** | How is it protected from the governed agent, **including local deletion**? | The trusted authorization baseline must **survive local deletion** of the declaration and memory: deleting them must not silently return the repo to "never authorized". |
| **R3 Project identity** | How is it bound to the correct repo root and effective memory path? | Bound to the intended repository root and the exact memory path (`MNEME_MEMORY`/discovery are ambiguous — G3 §4.2). |
| **R4 Verification** | What happens when the declaration, trusted revision, or verifier is unavailable? | Never a fabricated *pass*; never a silent fail-closed on an unverifiable declaration; an unverifiable baseline is an explicit operational state, not "never authorized". |
| **R5 Compatibility** | Coexist with `setup → active` and ADR-030's single decision authority. | It is **configuration/authorization**, not a competing canonical decision store. |
| **R6 Eligibility** | How does it establish that protection was **explicitly activated** (state 2), not merely that a config file exists? | The authorization must carry verified evidence that protection was activated at the trusted revision. |

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
| **M2** | **Separate committed declaration** under `.mneme/` (e.g. `.mneme/eligibility.json`), review-gated | Yes (if committed) | **Requires a mandatory independent verification mechanism (M4 or equivalent)**; a local-only clone is insufficient | explicit `repo_root` + `memory_path` | config, not decision authority | agent can edit *both* the local copy and the local git state → needs a baseline it does not solely control |
| **M3** | Field in an existing non-decision config (`.claude/settings.json`, CI config) | Yes | transport config; **agent-editable** | weak | overlap with transport | conflates transport with authority; rejected as the authority |
| **M4** | Git ref (annotated/signed tag or protected branch) | Yes | **remote git** (strongest local-resistant) | ref ↔ repo | orthogonal to decisions | needs a trusted remote; heavier UX |
| **M5** | Hook/plugin registration only | Yes | agent-editable | none | transport | not authority (G3 §4) |
| **M6** | External/hosted declaration | Yes | remote service | server-side | **out of scope** (no hosted service, ADR-030) | n/a |

## 5. Recommended contract (bounded)

**Recommend M2 with a *mandatory* independent verification mechanism (M4 or
equivalent).** M4 is **not optional**: without a baseline the governed agent does
not solely control, deleting local files would remove authorization (R2).

1. **Declaration (R1):** a small, explicit, human-authored, review-gated
   artifact under `.mneme/` — a *policy switch* authorizing fail-closed behavior
   when enforcement is unavailable. Created/revoked only by an explicit
   Mneme-owned authority action (never by an agent, producer, or inference).
2. **Eligibility evidence (R6):** the declaration must also witness that
   **protection was explicitly activated** (state 2) — for example by binding to
   the activation record and the protection rule binding at the trusted
   revision — not merely that a config file exists. The three states stay
   distinct: *memory exists* / *protection activated* / *fail-closed
   authorized*.
3. **Trust boundary that survives local deletion (R2):** authorization is
   authoritative only against a **trusted authorization baseline the agent does
   not solely control** — e.g. a protected/remote ref or an equivalent
   independently verified revision (M4). The baseline records that authorization
   existed; deleting the local declaration and/or memory **cannot** remove it.
   Local deletion while the baseline shows authorization is **"removed without
   approval"**, never "never authorized".
4. **Project identity (R3):** the declaration records the **repository root**
   and the **effective memory path** it applies to; a declaration that does not
   match the resolved root/path is not honored.
5. **Verification (R4):** if the declaration, its trusted revision, or the
   baseline is unavailable, the result is an **explicit operational state**
   ("authorization unverifiable") — never a fabricated *pass*, never a silent
   fail-closed, and never silently downgraded to "never authorized".
6. **Compatibility (R5):** configuration, not a second decision authority; it
   carries no decisions/rules/lifecycle and coexists with `setup → active`
   (which concerns *protection installation*, a different axis).

**Local-only repositories.** Without a durable, agent-not-solely-controlled
baseline the R2 bypass cannot be closed; for such repos fail-closed must not be
claimed as bypass-proof (they stay *inactive/available*).

## 6. Failure-state matrix (missing-memory / removal scenarios)

This matrix covers the **missing-memory and local-removal** scenarios G3-B
addresses; it is **not** a complete model of every ADR-033 failure (incomplete
evaluation, path `UNKNOWN`, launch/timeout, and others are separate).

`B` = the trusted authorization baseline shows the repo was authorized (with
activation evidence) · `L` = local declaration present · `M` = canonical memory
present · `V` = baseline verification available.

| B | L | M | V | Outcome |
|---|---|---|---|---|
| absent | absent | present | n/a | normal enforcement (today) |
| absent | absent | absent | n/a | **inactive** (never authorized) — surfaced as inactive |
| present | present | present | yes | normal enforcement |
| present | present | absent | yes | **fail closed** (authorized repo whose memory disappeared) |
| present | **absent** | present | yes | **removed without approval** → operational error / fail closed (never inactive) |
| present | **absent** | absent | yes | **removed without approval** → operational error / fail closed |
| present | * | * | **no** | **authorization unverifiable** → operational error; never a fabricated pass, never silently "never authorized" |
| present (declaration invalid / missing activation evidence) | * | * | yes | **operational error**; never fail closed |

The only **fail-closed** cells require a **verified** baseline showing
authorization **and** either missing memory or a locally removed declaration.
The key property: **removing local governance files must not be sufficient to
remove previously verified governance authorization.**

## 7. Explicit non-authorization and sequence

This assessment implements nothing. It does not add a declaration file, change
`setup → active`, alter hooks/CI, amend ADR-033, or unfreeze Layer 1. DG1F-C1b
stays locked; DG1B2 stays evidence-gated; the G1 harness matrix is not expanded.

**Sequence:** G3-B design (this doc) → architectural decision on M2 (+ optional
M4) → **ADR-033 reconciliation** → bounded implementation charter + matching
`[layer1-freeze]` amendment. Fail-closed behavior may not be introduced before
project-scoped authorization can be independently established.

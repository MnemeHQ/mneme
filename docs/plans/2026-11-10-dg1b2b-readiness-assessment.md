# DG1B2b readiness: can waiver-aware enforcement be chartered? (2026-11-10)

> Read-only readiness assessment. It changes no code, schema, workflow,
> memory, pin or release, and authorizes nothing. It asks whether DG1B2b
> (ADR-031 §11 "waiver-aware DG1F convergence": any authoritative consumer
> excluding a decision because of a waiver) can be given a behavioral charter
> now, measured against the existing trusted-context and `as_of`
> requirements.
>
> **Anchor:** `MnemeHQ/mneme` `main` at `804591ae` (#787, DG1B2a merged).
> **Basis:** [ADR-031](../adr/ADR-031-decision-governance-semantics.md) §6,
> §7, §11, §12; [DG1F-C1 charter](2026-10-13-dg1f-applicability-only-charter.md)
> §2-§3, §5b (C1b trust prerequisites); [DG1B2 charter](2026-11-10-dg1b2-waiver-charter.md)
> §2, §3.2, §5; [consumer trust-boundary inventory](2026-10-14-dg1f-consumer-trust-boundary-inventory.md);
> [post-C3a reconciliation](../validation/dg1-post-c3a-reconciliation-2026-11-09.md) §3;
> [DG1G fixture-floor mapping](../validation/dg1g-fixture-floor-mapping-2026-11-10.md);
> `.github/workflows/mneme-trusted-gate.yml`; tracker #497.

## 0. Answer

**Not ready. Do not charter DG1B2b now.** DG1B2b is blocked on the same
unmet prerequisite as DG1F-C1b, plus one of its own:

1. **Trusted labels (hard blocker).** Every DG1B2a waiver is label-scoped by
   contract (non-empty `required_labels`, charter §3.1). Acting on a waiver
   therefore means trusting the labels it is matched against. The only
   acceptable source is a reviewed canonical context declaration (C1 charter
   §3), which does not exist and is itself an unauthorized persisted v2
   semantic (reconciliation gap G-6). Without it, a waiver can never
   legitimately apply at runtime.
2. **No case that needs runtime suppression (evidence gate).** ADR-031 §11
   makes DG1B2 and DG1F evidence-gated. The accepted evidence (#783, CNCF
   picolibc/Hyperlight) justifies *recording* an approved exception. No
   repository yet needs a Mneme gate to *stop reporting* a violation because
   of a waiver.

`as_of` is **not** a hard blocker. DG1B2a fails closed to the decision: a
time-bound waiver with no trusted `as_of` simply does not apply, so the
decision stays enforced. An increment limited to untimed waivers needs no
`as_of` source at all.

The trusted CI gate is the only surface that already meets the C1b memory
prerequisites (approved revision, substitution protection). It is therefore
the only plausible first DG1B2b consumer, but it is blocked by (1), and it
also needs an evaluator pin bump (§3).

## 1. Requirements and current state

| # | Requirement | Source | State at `804591ae` | Gap |
|---|---|---|---|---|
| R1 | Labels come from the reviewed canonical authority; never argv, env, hook/MCP input, paths, OS, retrieval or agent content | C1 §3.1-3.2, §3.4; ADR-031 §11 amendment | Labels exist only as caller assertions (`--applicability-preview`, non-authoritative). No persisted context declaration; no writer. | **Open (G-6).** Needs its own v2 semantic, charter and freeze amendment. |
| R2 | Independently verifiable approved revision of the memory used | C1 §3 "C1b trust prerequisites" (a) | Trusted gate: memory from the base commit only, `pull_request_target`, PR head read as blobs and never executed. Local surfaces: memory chosen by `MNEME_MEMORY` or discovery (G-7). | Met for the trusted gate only. |
| R3 | Protection against unreviewed substitution between review and run | C1 (b) | Trusted gate: pinned evaluator (rebuilt from `0b74d410`, sha256-checked), pinned adapter blob, base-only memory. `.mneme/` changes merge only through the recorded human bypass (CI R0). | Met for the trusted gate only. |
| R4 | Controlled context selection: no caller picks an arbitrary context | C1 (c) | Nothing to select: no declaration exists. | Open; designed together with R1. |
| R5 | Fail-closed handling of missing, invalid, ambiguous or conflicting context | C1 §3.3; ADR-031 §11 | The resolver already fails closed to the decision for waivers (labels not supplied, mismatch, version mismatch, revoked, `as_of` missing or invalid). Integrity findings never exclude. | Resolver side met. The consumer contract is not written. |
| R6 | Blocking seam: a missing or invalid verdict blocks rather than passes | C1 §3 caveat, §5b item 14 | Trusted gate: required on Core `main`; the gate decision step recomputes the result and checks every pin (ADR-033 fail-closed posture). Local hooks and adapters fail open by design (inventory). | Met for the trusted gate only. |
| R7 | Trusted `as_of` for time-bound waivers; the resolver never reads the clock | ADR-031 §6; DG1B2 §3.2 | No producer of `as_of` anywhere in `mneme/`. A missing `as_of` makes time-bound waivers not apply. | **Not blocking** for untimed waivers. A trusted source (for example an event timestamp outside the PR's control) is a later design choice. |
| R8 | Enforcement-scope invariant: exclude from the full effective corpus before top-K, never filter selected results | C1 §2 | Not implemented (no exclusion exists). | Design known; implementation belongs to the first excluding increment (C1b or DG1B2b). |
| R9 | Evaluator can read waiver memory | DG1B2 §6; freeze #785 item 5 | Trusted-gate evaluator `0b74d410` predates v2 waivers. A real `mneme-hq==0.11.0` refuses waiver memory (exit 1). | **Open (G-8).** Pin bump needs separate approval (CI R0 owner). |
| R10 | Concrete case needing runtime suppression | ADR-031 §11 evidence gate | #783 supports recording only. | **Open.** |
| R11 | Authorized-transition positive test (distinct approver, version-bound, scope, time) | DG1G G2 | DG1B2a pins this at record level (`approver != requester`, exact version binding, scope, window). There is no host-side test of an approved governance revision. | Partial; stays with DG1G. |

## 2. Consumer by consumer

| Consumer | Could it act on a waiver safely? | Why |
|---|---|---|
| Trusted CI gate (`mneme-trusted-gate.yml`) | **Only candidate**, after R1, R4, R9 and R10 | R2, R3 and R6 already hold. It still has no trusted labels, and its evaluator refuses waiver memory. |
| `mneme check` (local CLI) | No | argv, env and the memory path are caller-controlled (R1, R2). |
| Claude Code, Codex, Kiro and other hooks and adapters | No | They fail open on missing verdicts, and their transport inputs are not label authority (inventory). |
| Decision MCP | No | Producer boundary (ADR-027). It is not an enforcement consumer. |
| C3a consumers (Audit, readiness, `protect list`) | Not meaningfully | They resolve with labels not supplied by contract, so no waiver can apply. Changing that is the same R1 problem. |
| C1a preview | Already informational | Shows `cause=waived` as non-authoritative output (DG1B2a). Not a DG1B2b consumer. |

## 3. What a future DG1B2b charter would have to contain

These are recorded so a later charter does not rediscover them. None is
authorized here.

1. **Evidence:** a repository case where an approved, decision-version-bound
   exception must stop a Mneme CI gate from failing, with the authority
   record and the gate run identified.
2. **Context declaration first:** a persisted, reviewed v2 context
   declaration (shared with C1b) that supplies labels to the trusted gate
   from base-commit memory, with controlled selection and fail-closed
   handling for missing, invalid or conflicting declarations (R1, R4, R5).
3. **Scope:** the trusted gate only, untimed waivers only. Time-bound
   waivers keep failing closed until a trusted `as_of` source is chartered
   (R7).
4. **Full-corpus exclusion** before top-K, with the C1 §5b item 10 rank
   invariance test (R8).
5. **Evaluator pin bump** approved by the CI R0 owner before any waiver
   reaches Core memory, with ADR-031 §8 release notes (R9).
6. **Its own `[layer1-freeze]` amendment**, plus C1 §5b items 6-14 adapted
   for waivers (explicit match, nonmatch, context failure, lifecycle
   ordering, findings never exclude, blocking seam).

## 4. Recommendation

Record DG1B2b as **deferred with C1b**, for the two reasons in §0: no
trusted label source exists, and no case needs runtime suppression. Charter
nothing.

The single next DG1 step this unblocks is a **DG1G mapping update**. The
merged mapping lists F13 (waiver fixtures, including expiry at an explicit
`as_of` and out-of-scope waivers) as *blocked* because DG1B2 had no
qualifying case. DG1B2a has since delivered those fixtures in
`tests/test_dg1b2a_canonical_waivers.py` (items 2 and 3), so F13 can be
re-evaluated and moved off *blocked*. DG1G and DG1 stay open after it.

## 5. Non-claims

This record does not claim that DG1B2, DG1F, DG1G or DG1 is complete, does
not authorize a context declaration, a waiver-aware consumer, a trusted-gate
evaluator pin change, a waiver in Core memory or a release, and does not
change any runtime behavior. C2, C3a and DG1B2a remain merged but unreleased.

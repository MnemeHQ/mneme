# DG1F — G1: bounded host-harness validation scope (proposal)

**Status:** **scope proposal**, not a charter, approval, implementation plan, or
support claim. It authorizes no runtime, harness, schema, or benchmark change.
Executing the validation below is a separate step with its own evidence.
**Source anchor:** `MnemeHQ/mneme` `main` at
`2246cd0ab3d9b2d9e016d4f018cc0692c08244b7` (G2, PR #508).
**Governing contracts:** [ADR-017](../adr/ADR-017-enforcement-scope-vs-retrieval-scope.md),
[ADR-021](../adr/ADR-021-shell-preflight-and-stop-session-delta.md), the
[blocking-semantics matrix](2026-10-14-dg1f-adversarial-blocking-semantics-matrix.md)
(G1), the [consumer inventory](2026-10-14-dg1f-consumer-trust-boundary-inventory.md),
and the [CI-consumer audit](2026-10-14-dg1f-g2-ci-consumer-coverage.md).

## 1. The question G1 answers

Offline tests (G4) assert the **adapter's returned action** — `deny` / `block` /
`FAIL_OPEN` — for a given checker result. They do **not** establish that the
**host harness** honours a blocking instruction by actually preventing the
mutation.

> When Mneme returns a blocking instruction to a coding-agent harness, does the
> prohibited modification fail to land?

G1 answers this with a pinned, reproducible live probe and an **independent
no-mutation check** (the file's bytes are unchanged after the attempt).

## 2. Why it matters (and how it informs ADR-033)

- A returned block the harness ignores is **false protection** — the central
  risk the matrix records as G1.
- It is the missing evidence before any claim of *enforced* governance, and it
  directly informs the proposed ADR-033 availability/fail-closed design: whether
  a "block" is a real gate or only an advisory signal in each harness.

## 3. Bounded first slice — one harness, one surface, one violation

Keep the first validation minimal and falsifiable:

- **Harness:** **Claude Code**, `PreToolUse` direct-write path (the first proof
  named in the C0 reliable-enforcement charter, PR #483). Other harnesses follow
  in later slices.
- **Governed repo:** a throwaway git repo with `.mneme/project_memory.json`
  containing one active decision with a single `FORBID_LITERAL` rule (a token
  that never appears in normal prose, to avoid false triggers).
- **Trigger:** an agent-initiated edit that introduces the forbidden literal.
- **Assertions:**
  1. the adapter returns a blocking decision for that tool call;
  2. the target file's bytes are **unchanged** after the attempt (independent
     hash before/after);
  3. the harness surfaces the block reason to the agent;
  4. the same edit **without** the decision lands (control), proving the probe
     can observe a permitted write.
- **Pinned versions:** the harness build/version, the plugin/hook version, and
  the Mneme commit are all recorded; the probe is re-runnable.

## 4. Per-harness follow-up (later slices)

| Harness | Surface to probe first | Block mechanism to observe |
|---|---|---|
| Claude Code | `PreToolUse` direct edit | `permissionDecision: deny` prevents the write |
| Codex CLI | pre-tool patch gate | `DENY` prevents the patch |
| Kiro | hook gate | non-zero exit blocks the tool |
| Antigravity | adapter gate | block response prevents the mutation |
| Hermes | pre-tool-call hook | block directive prevents the mutation |
| Claude Code / Codex | `Stop` backstop | post-mutation audit blocks completion (not pre-write) |

Each slice needs the same no-mutation assertion; a Stop backstop is a
**post-mutation** gate and must be reported as such, not as prevention.

## 5. Required evidence (per slice)

- A reproducible transcript (commands, harness version, Mneme commit).
- Before/after content hashes of the target artifact.
- The adapter's blocking decision and the harness's observed action.
- The control run (permitted write) for the same artifact.
- An explicit note of what the probe does **not** prove (e.g. other tool paths,
  other harness versions, or cross-user/permission variants).

## 6. Boundaries and non-goals

- No runtime, enforcement, harness-config, schema, or benchmark change; no
  C1b, no waivers, no ADR-033 implementation.
- Not a support-matrix claim: a single pinned probe is evidence, not a general
  guarantee, and must not be published as one.
- The probe requires a **live harness environment** (Claude Code etc.), which
  is not available inside the offline agent session that produced this scope;
  execution is therefore a separate, environment-dependent step.
- If the harness does **not** honour the block, that is a finding to report —
  not something to paper over by changing Mneme.

## 7. Sequence

1. Approve this scope.
2. Execute the Claude Code `PreToolUse` slice in a pinned live environment;
   record the §5 evidence.
3. Report the result (honoured / not honoured / partially) and its limits.
4. Only then extend to the §4 harnesses, and feed the findings into the
   ADR-033 availability/fail-closed design.

**C1b remains locked; ADR-033 remains proposed; G3 (missing-memory policy)
remains a separate decision.**

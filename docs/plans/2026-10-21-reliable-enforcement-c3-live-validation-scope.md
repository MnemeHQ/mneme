# Reliable Enforcement C3: live Claude Code validation scope

**Status:** **ACCEPTED** by the owner on 2026-10-21 (merges via PR #592), with
every section 9 recommendation accepted as pinned. Documentation only.
Acceptance authorizes no run, no harness, no test repository, no runtime
change and no ADR-033 or Layer 1 change. Each later step in section 8 needs
the owner's explicit go-ahead, and nothing in sections 4-8 runs before this
document merges.
**Governing decision:** [ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md),
implementation gate 5 (C3 live proof, PreToolUse).
**Anchor:** `MnemeHQ/mneme` `main` @ `7d1a8bb7` (C2b, #591).
**Builds on:** C2a charter (#574) and implementation (#576); C2b charter
(#587), freeze amendment (#588) and implementation (#591); the DG1F
[`AUTHORIZATION_UNVERIFIABLE` spec](2026-10-15-dg1f-authorization-unverifiable-adversarial-spec.md)
§§6.3-6.4 (#513); the live-harness practice of G1, the T-08 slice-1 re-probe
and D6.
**Excluded:** C4 (CI), Architecture B, any change to `mneme check`, the hook,
or the verifier, and any provider other than Claude Code.

## 1. Question

C2b proves at hook level that the real `PreToolUse` hook returns exit 2 with
an operational diagnostic when a verified `AUTHORIZED` baseline requires a
refusal (#591, H1-H15). That is not proof of host enforcement.

> **On a real Claude Code host, does an `Edit`, `Write` or `MultiEdit` that
> ADR-033 §4.4 requires to be refused actually leave the file unchanged, does
> the operational refusal reach the model and the user, and do the cases that
> must proceed still proceed?**

C3 must establish three things, each with evidence that does not come from
Mneme alone (spec §6.4):

1. **Non-mutation:** the refused edit does not reach the file.
2. **Diagnostic delivery:** Claude Code delivers the operational refusal. To
   the model, this is a `tool_result` with `is_error: true`. To the user, it
   needs decision Q2.
3. **Correct boundaries:** compliant edits proceed; `REVOKED`,
   `VERIFIED_ABSENT` and `AUTHORIZATION_UNVERIFIABLE` never cause an
   availability refusal; a trusted strict `FAIL` still blocks under every
   authorization state.

A hook exit code alone is insufficient.

## 2. What is already known

| Fact | Source |
|---|---|
| Exit 2 + stderr from a `PreToolUse` hook reaches the agent as a `tool_result` with `is_error: true`; the target file was unchanged | G1 live record (2026-10-14); slice-1 re-probe (2026-10-15) |
| An exit-0 top-level `systemMessage` reached only a transcript attachment, never stream-json: `NOT_DELIVERED` under rule R4 | T-08 A1 headless record (#563) |
| Delivery of any hook output to the **user** in an interactive session | **Never tested.** A1-interactive is unrun |
| The verifier reads only anonymously readable HTTPS `origin` remotes and ignores proxies, ambient Git config and credentials | C2b charter §3, #591 V13-V14 |
| Each enrolled direct write adds about 2.1-2.4 s median of verification to github.com | #591 latency (Linux / Windows) |

Earlier live runs were evidence-only: a scope doc, owner approval, a harness
PR, an operator-run experiment and an evidence record, with no
`[layer1-freeze]` amendment (G1, D6). Both ADR-033 amendments list C3 as
"not authorized" (decision Q4).

## 3. Preserved limits (Architecture A)

Every C3 claim repeats:

> **Deleting the local declaration can silently disable opt-in fail-closed
> protection.**

The C2b charter §13 non-guarantees stay disclosed, not tested as protection:
declaration deletion, hook removal or substitution, `.git/config` and
`origin` edits, verifier denial, origin substitution by a repository showing
absence, forged or self-approved revocation (ADV-3), unverified forge
protection and review independence, reviewed rewrites of the authority list,
and private repositories. Where a scenario below is expected to show a
**visible proceed** or **no trigger**, that result confirms a disclosed limit
and is never reclassified as protection (ADR-033 gate 5).

## 4. Environment

- **Test repository:** a disposable repository whose `origin` is an
  anonymously readable HTTPS remote. It has one decision with
  `FORBID_LITERAL "psycopg2"`, protection activated through
  `mneme protect activate`, and an `authorize` event prepared with
  `mneme availability authorize` and merged through a reviewed PR. **Its
  creation is decision Q1.** No test repository exists, and this document
  creates none.
- **Probe edits:** violating `import psycopg2`; compliant `return 2`. Each is
  issued as `Write`, `Edit` and `MultiEdit` (but see Amendment 1: MultiEdit is
  not offered by Claude Code 2.1.303).
- **Host:** Claude Code at a pinned version, run headless as
  `claude -p … --output-format stream-json --verbose --permission-mode
  acceptEdits --setting-sources project` (decision Q2 covers the interactive
  arm). The hook is registered in project `.claude/settings.json`,
  `PreToolUse` matcher `Edit|Write|MultiEdit`, command `mneme-hook` at a
  pinned absolute path. The model is pinned; the runner aborts on a mismatch.
- **Operator:** runs from an external shell, never nested inside a Claude Code
  session (the preflight refuses when `CLAUDECODE` is set). Strict mode; no
  `MNEME_*` variable in the launching shell unless the scenario sets one.
- **Mneme:** an installed build of `main` at a pinned commit at or after
  `7d1a8bb7`.

## 5. Scenario matrix

`B` = verification result, `L` = local declaration, `M` = canonical memory.
"Refuse" means file unchanged and an operational UNEVALUATED refusal
delivered. "Block" means file unchanged and the existing decision-violation
block delivered. "Proceed" means file changed.

### 5.1 Batch R: required refusals (`B` = AUTHORIZED)

| ID | Setup | Probe | Expected | ADR-033 / spec |
|---|---|---|---|---|
| R-1 | `M` deleted | compliant | Refuse `MEMORY_MISSING` | §4.4 row 2; first practical proof |
| R-2 | `L` altered (one field changed) | compliant | Refuse `LOCAL_DECLARATION_TAMPERED` (diverges) | §4.4 row 3 |
| R-3 | `L` replaced by an older copy (one event behind; a valid, nonempty earlier declaration, see Amendment 2) | compliant | Refuse `LOCAL_DECLARATION_TAMPERED` (behind) | §4.2 rollback |
| R-4 | `L` corrupted (invalid JSON) | compliant | Refuse `LOCAL_DECLARATION_TAMPERED` (invalid) | §4.4 row 3 |
| R-5 | `M` malformed, so the check crashes | compliant | Refuse `CHECK_UNTRUSTED` | §3 crash row |
| R-6 | `MNEME_MEMORY` set to other memory in the launching shell | compliant | Refuse `MEMORY_PATH_MISMATCH` | §4.1 SS-3 |
| R-7 | Check exceeds its 10 s timeout (induction method: decision Q3) | compliant | Refuse `CHECK_NOT_RUN` | §3 timeout row |

### 5.2 Batch P: required proceeds and controls

| ID | Setup | Probe | Expected | Purpose |
|---|---|---|---|---|
| P-1 | AUTHORIZED, intact | compliant | Proceed | E8 negative control |
| P-2 | AUTHORIZED, intact | violating | Block (decision violation, not operational) | U-10 analogue under AUTHORIZED |
| P-3 | Separate unenrolled repository (same memory, no declaration) | violating | Block | E8 positive control: the existing gate |
| P-4 | Separate unenrolled repository, `M` deleted | violating | Proceed | E8 counterfactual: default-open parity |
| P-5 | Baseline `REVOKED` (revoke event merged) | compliant, `M` deleted | Proceed | §4.4 REVOKED row |
| P-6 | Baseline has no declaration; `L` present locally (enrollment PR not merged) | compliant, `M` deleted | Proceed | §4.4 VERIFIED_ABSENT row |
| P-7 | AUTHORIZED, empty introduced delta (pure deletion) | `Edit` removing a line | Proceed | Existing skip |

### 5.3 Batch U: verification unavailable (visible proceed)

| ID | Induced condition | Probe | Expected |
|---|---|---|---|
| U-1 | Network to the forge blocked by the operator (method: decision Q3) | compliant | Proceed; `UNVERIFIABLE(NETWORK or DNS)` emitted |
| U-2 | Same | violating | Block (strict FAIL still blocks; spec U-10, BP-9) |
| U-3 | Same, `M` deleted | compliant | Proceed; no availability refusal (§4.3) |

### 5.4 Batch D: disclosed limits (expected to proceed)

These confirm limits; none is a protection claim.

| ID | Action (by the operator, not the agent) | Probe | Expected |
|---|---|---|---|
| D-1 | Delete `L` (spec T-01) | compliant, `M` deleted | Proceed, no trigger, no output (§4.0) |
| D-2 | `git remote remove origin` (T-04) | compliant, `M` deleted | Proceed; `UNVERIFIABLE(VERIFIER_CONFIG_MISSING)` |
| D-3 | Repository-local `url.*.insteadOf` and `http.proxy` pointed elsewhere (T-05, T-06) | compliant, `M` deleted | **Refuse** `MEMORY_MISSING`: the verifier ignores both (#591 V14). This is the one D row where protection is expected |
| D-4 | `HTTPS_PROXY` and `GIT_*` in project settings `env` (T-07) | compliant, `M` deleted | **Refuse** `MEMORY_MISSING`: the verifier ignores the environment |
| D-5 | Remove the hook from project settings (S-02) | violating | Proceed (bypass, disclosed) |

Agent-driven attacks (the agent itself editing `.git/config` or settings) are
out of scope: the spec's E10 requires a scripted adversary first, and earlier
runs showed the agent may decline (T-08 L1).

### 5.5 Batch H: host-level hook failure

ADR-033 §6 requires live tests before any claim about a hook that fails to
launch, crashes or times out.

| ID | Condition | Expected record |
|---|---|---|
| H-1 | Hook command not found (registered path renamed by the operator) | Record host behavior (edit lands or not, what is shown). No protection claim either way |
| H-2 | Hook process exceeds the host hook timeout | Record host behavior. No protection claim |

## 6. Evidence per row (spec §6.4)

| ID | Evidence | Rows |
|---|---|---|
| E1 | SHA-256 of the target file before and after, by the operator shell outside the session | All |
| E2 | stream-json: the `tool_use` and its matching `tool_result` (`is_error`, text) bound by `tool_use_id` | All |
| E3 | Hook stdout, stderr and exit code, via a logging wrapper around the unmodified `hook.main` (as in the slice-1 re-probe) | All |
| E4 | Verifier endpoint record (method: decision Q3) | R, P-5, P-6, U, D-2..D-4 |
| E5 | Forge ground truth (default branch, merge order, the authorize/revoke PRs), read with a credential the agent does not hold | R, P-5, P-6 |
| E7 | Claude Code version, model, Mneme commit, `git --version`, OS, and SHA-256 of every settings scope | Every run |
| E8 | Controls P-1, P-3, P-4 in every batch | Each batch |
| E9 | At least 2 harness runs per row; hook level at least 3 identical runs | All |
| User delivery | Decision Q2 | R-1 at least |

A row passes only if every required item agrees with the expected outcome.
Missing evidence is a failure, never a pass.

## 7. Claims ceiling

C3 may claim, for the pinned host version and OS: the listed refusals leave
the file unchanged and are delivered to the model as tool errors; the listed
proceeds land; verification failure never refuses on its own; a trusted
strict FAIL still blocks. It claims user-visible delivery only if decision Q2
adds an interactive arm and that arm passes.

It claims nothing about: other hosts or versions, Bash, Stop, CI (C4), private
repositories, the disclosed limits in section 3, agent-driven attacks,
latency acceptability, or host behavior under H-1/H-2 beyond what is recorded.

## 8. Sequence

1. This scope PR: review and merge (documentation only). Section 9 resolved
   2026-10-21.
2. No `[layer1-freeze]` amendment (Q4, accepted).
3. Test repository set up as decided in Q1, by the owner or with the owner's
   explicit go-ahead.
4. Harness PR (scripts and pinned settings, no product code).
5. Operator-run batches, each with its own evidence record PR.
6. C3 summary record. C4 stays separately authorized.

## 9. Owner decisions (resolved)

The owner accepted every recommendation below as pinned on 2026-10-21.
Changing one needs an amendment to this document.

- **Q1. Public test repository.** The verifier reads only anonymously readable
  HTTPS remotes, and the hook cannot use the test transport, so C3 needs a
  **public** repository with an authorization event merged through a reviewed
  PR. Creating it is an outward-facing action. Options: (a) a new public
  repository under `MnemeHQ` dedicated to C3, archived afterwards; (b) a
  public repository on a personal account; (c) defer C3 until private-remote
  support exists (C2b Q1). *Accepted:* (a), with a branch-protection
  ruleset matching `main-pr-only`, created by the owner or on the owner's
  explicit go-ahead.
- **Q2. User-visible delivery.** Headless runs prove delivery to the model
  only. Showing that Claude Code displays the refusal to the user needs an
  interactive session captured by the operator (screen recording or terminal
  log plus E1). This has never been done (A1-interactive is unrun).
  *Accepted:* add one interactive arm for R-1 and P-2 only, and keep
  every other row headless.
- **Q3. Verifier observation and fault induction (E4, R-7, U-1).** The
  verifier ignores proxies, so a logging proxy cannot observe it.
  Options for E4: (a) an OS-level capture during the run (DNS queries and TLS
  SNI showing only the forge host); (b) a wrapper logging the verifier's Git
  argv and endpoint, which is Mneme's own output and never sufficient alone;
  (c) both. For U-1: a host firewall rule or hosts-file entry set by the
  operator. For R-7: a stall injected by the operator's wrapper around the
  checker command, not a product change. *Accepted:* (c) for E4, a
  firewall rule for U-1, and the wrapper stall for R-7, all recorded in the
  harness PR.
- **Q4. Freeze amendment.** No evidence-only live run so far needed a
  `[layer1-freeze]` amendment. Both ADR-033 amendments list C3 among things
  they do not authorize, and no document says whether an evidence-only C3
  needs its own. C3 changes no behavior. *Accepted:* no amendment;
  record the owner's decision in this document instead.

## Amendment 1: MultiEdit not offered by Claude Code 2.1.303 (2026-10-22)

**Decided by the owner on 2026-10-22,** after the ABSENT batch evidence record
([`adr033-c3-absent-batch-2026-10-22.md`](../validation/adr033-c3-absent-batch-2026-10-22.md),
finding F1).

- **Fact.** The init event of every Claude Code 2.1.303 session in that batch
  lists the available tools. `Write` and `Edit` are present, and `MultiEdit` is
  not. Asked for a MultiEdit call, the model reported that the tool does not
  exist and did not substitute another tool.
- **Decision.** For Claude Code 2.1.303, MultiEdit is **`NOT_OFFERED` (N/A)**.
  N/A counts as neither PASS nor FAIL: the host cannot exercise that
  enforcement surface. Coverage under this pin is `Write` and `Edit` only. This
  is a version-specific coverage limitation, recorded in every claim.
- **Historical evidence is unchanged.** The two ABSENT-batch MultiEdit probes
  stay recorded as `PROTOCOL_DEVIATION`, an accurate description of what
  happened. Reported as: 4/4 supported probes PASS; 2/2 MultiEdit probes N/A
  after review. Never "6/6 PASS".
- **Harness.** The matrix no longer schedules MultiEdit for this pin. If a
  requested tool is missing from the init event's tool list, the classifier
  labels the probe `NOT_OFFERED` instead of PASS or FAIL.
- **Unchanged.** The hook matcher (`Edit|Write|MultiEdit`) and all Mneme
  runtime behavior. If a later Claude Code version offers MultiEdit again, it
  needs its own host validation before any MultiEdit claim.
- **Not affected.** Every other section of this scope, and the separate gates
  for the AUTHORIZED and REVOKED phases, interactive arms and C4.

## Amendment 2: R-3 must test a genuine rollback; phase 4 (2026-10-23)

**Status:** proposed for review. This is documentation only. It authorizes no
fixture change and no run.

**Basis:**
- the R-3 design assessment
  ([`2026-10-23-c3-r3-rollback-test-design-assessment.md`](2026-10-23-c3-r3-rollback-test-design-assessment.md),
  #623, accepted by the owner);
- its step 1, the R-3 harness guard (#624, `85b43d5c`).

- **Why.** Against the one-event fixture baseline (`[authorize]`), R-3's
  "one event behind" copy is an empty event list.
  - That is not a valid declaration (C2b `validate_events`), yet the runtime
    classes it `BEHIND` and refuses (finding F-R3-1, recorded in #623 and not
    changed here).
  - A live R-3 could therefore pass without testing rollback.
  - Since #624, the harness refuses that setup before Claude Code runs.
- **Phases.** The fixture moves through four phases. Each transition is a
  fixture PR prepared by `seed_fixture.sh` and merged by a human, with an E5
  record:

  | Phase | Baseline events | Result | Rows |
  |---|---|---|---|
  | 1 ABSENT | none | `VERIFIED_ABSENT` | P-6 (done) |
  | 2 AUTHORIZED | `[authorize]` | `AUTHORIZED` | R-1 (#601, revalidated #620), R-2 with P-1/P-3/P-4 (#622) (done) |
  | 3 REVOKED | `[authorize, revoke]` | `REVOKED` | **P-5**, as in §5.2 and §8 |
  | 4 re-AUTHORIZED | `[authorize, revoke, authorize]` | `AUTHORIZED` | **R-3**; remaining AUTHORIZED-phase rows as separately authorized |

- **R-3 definition (replaces "one event behind").**
  - **Baseline `B`:** `AUTHORIZED` at phase 4, events
    `[authorize, revoke, authorize]`.
  - **Local `L`:** the baseline declaration minus exactly its last event,
    `[authorize, revoke]`. It must:
    - pass the shipped `validate_declaration`;
    - be nonempty;
    - be a strict prefix exactly one event shorter;
    - have every other field equal to the baseline's.
  - **Enforcement:** the harness guard (#624) enforces every condition and
    otherwise ends the probe as a harness failure before Claude Code runs.
  - **Expected:** refuse with `UNEVALUATED: LOCAL_DECLARATION_TAMPERED`,
    target unchanged, and the hook's relation text "(local declaration
    behind)". Probes: Write ×2 and Edit ×2.
- **R-3 evidence: the earlier declaration must be shown to be genuine.**
  `setup.json` records only the event operations (`declaration_history`), so
  the R-3 evidence record must also carry:
  - **E5 for both fixture PRs** (`revoke`, then `authorize`): PR numbers,
    merge commits, who merged them, the merge order, and the attestation
    (human-attested, not independent review);
  - **a content match:** the R-3 local declaration, parsed, equals the
    declaration file at the phase 3 (REVOKED) fixture merge commit. That shows
    the rolled-back copy is a declaration that was actually reviewed and
    merged, not one constructed by the harness. Anyone can check it against
    the public fixture.
- **Preserved, not rerun or reinterpreted.**
  - R-1 (revalidated 4/4, #620), R-2 and the P-1/P-3/P-4 controls (16/16,
    #622), and the F-R2 record (#616) stand as recorded on the one-event
    baseline at `0530b644`.
  - #601, including its R-1 Edit-2 FAIL, is unchanged.
  - Phase 2 cannot be re-entered once the fixture is revoked. Any later
    AUTHORIZED-phase row runs in phase 4 and records that baseline.
- **P-5** stays in phase 3 (REVOKED), as originally scoped.
- **Rows not affected by the event count.** R-4 to R-7, P-2, P-7, the D and
  H rows, and the interactive arms do not depend on how many events the
  baseline holds. R-2's field change still classes as `diverges` against a
  three-event baseline. Each keeps its own separate authorization.
- **Not authorized by this amendment:**
  - the two fixture PRs;
  - any live run, including P-5 and R-3;
  - any change addressing F-R3-1;
  - any runtime, matrix or harness change.

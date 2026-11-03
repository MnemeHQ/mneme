# Reliable Enforcement C2b: verified availability authorization charter

**Status:** **ACCEPTED** by the owner on 2026-10-21 (merges via PR #587), with
every section 16 recommendation accepted as pinned. Documentation only.
Acceptance authorizes **no implementation**. Implementation needs the separate
section 14 `[layer1-freeze]` amendment, opened only after this charter merges
(Amendment Procedure §3(b)). No code, test, hook, plugin, CI, ruleset or
`.mneme/` change.
**Governing decision:** [ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md)
(accepted 2026-10-20), Architecture A, implementation gates 2 and 4.
**Source anchor:** `MnemeHQ/mneme` `main` @ `72b6d04a` (C2a, #576). Line
numbers refer to that commit.
**Builds on:** the [C2a charter](2026-10-20-reliable-enforcement-c2a-availability-routing-charter.md)
(#574) and its amendment (#575, `8ef193a3`); G3-B (#512); the DG1F
[`AUTHORIZATION_UNVERIFIABLE` spec](2026-10-15-dg1f-authorization-unverifiable-adversarial-spec.md)
(#513); M1.3/M1.4 activation (`mneme/setup_state.py`, `mneme/protection.py`).
**Excluded:** live host validation (gate C3), CI implementation (gate C4),
Architecture B, and any provider other than Claude Code direct writes.

## 0. Assessment of the proposed C2b scope

The proposed scope (C2a closure review, 2026-10-21) is correct in direction
and dependency order: C2a built the routing, C2b supplies the authority that
makes a refusal legitimate. No change to `DecisionRetriever`,
`ConflictDetector`, strict/warn or canonical decision semantics is needed.

Reading the source at `72b6d04a` adds six points the charter must settle:

| # | Finding | Consequence for C2b |
|---|---|---|
| F1 | Mneme squash-merges every PR (ADR-022, repo policy). A squash commit is a single-parent commit, indistinguishable in Git from a direct push. | Git history alone cannot prove that a review happened. The review event must be a recorded artifact, and C2b must not claim it verifies review (section 4.4). |
| F2 | Git alone cannot show that a remote ref is protected. That is a forge setting. | C2b verifies the **live tip of the remote default branch**, not forge protection. Protection is attested at enrollment and disclosed (section 13). |
| F3 | ADR-033 §4.2 says the verifier should not use ambient credential helpers. Without them, private remotes cannot be read. | C2b supports anonymously readable HTTPS remotes only. Private remotes return `AUTHORIZATION_UNVERIFIABLE(AUTH)` and cannot enroll (Q1). |
| F4 | Architecture A forbids caching a verification result in agent-writable storage (spec BP-8). | Every hook invocation in an enrolled repository makes live network calls. Latency is a measured acceptance item (section 12), not an afterthought. |
| F5 | Enrollment and revocation need an explicit Mneme-owned operation (ADR-033 §4.1). | "Without altering the CLI" can only mean `mneme check` and existing commands. C2b adds a new `mneme availability` command group (section 6). |
| F6 | `emit_availability` (`availability.py:132`) has no input for local-versus-baseline tampering, and the benchmark-only in-process transport exits 0 on timeout (`hook.py:606`). | The routing gains one tamper input (section 7). The in-process transport is declared unsupported under `AUTHORIZED` rather than changed. |

### 0.1 Reconciling G3-B with accepted ADR-033

G3-B (§5 item 3 and the §6 rows `authorized | absent`) says protection
survives **deletion** of the local declaration ("removed without approval →
fail closed"). The spec's Architecture A column for T-01/T-02 also expects
`REFUSE-TAMPER` when the verifier is reachable. Both describe the stronger
guarantee that ADR-033 §4.0 deliberately did **not** adopt: under
Architecture A the only verification trigger is the presence of the local
declaration.

**C2b follows ADR-033.** Where G3-B or the spec's A column conflicts with
ADR-033 §§4.0-4.4, ADR-033 governs. C2b adds no verification trigger, does
not walk remotes when the declaration is absent, and does not reintroduce
Architecture B. Tests D9 and H13 pin this (section 9).

## 1. What C2b is

C2b replaces the C2a verifier stub with a live verifier of the protected Git
baseline, adds the declaration's identity, activation and authority fields,
adds explicit authorize/revoke/status operations, and connects verified
outcomes to the C2a routing. Its first reachable behavior change is an
**operational refusal** of a supported direct write when authorization is
verified as `AUTHORIZED` and evaluation is unavailable.

### 1.1 The Architecture A limitation, preserved verbatim

> **Deleting the local declaration can silently disable opt-in fail-closed
> protection.**

Every C2b assurance claim repeats this sentence.

### 1.2 Evidence ceiling

C2b proves **hook-level** behavior: the real `PreToolUse` hook code returns
exit 2 with an operational diagnostic. It does not prove that Claude Code
prevents the mutation or shows the diagnostic. That is gate C3, separately
authorized.

## 2. Current behavior (anchor `72b6d04a`)

- `handle_event` (`hook.py:1120`) calls `discover_declaration(start)` before
  `find_memory` (`hook.py:1148`). With no declaration the path is byte-identical
  to the pre-C2a hook (C2a P1).
- With a declaration, `emit_availability` (`availability.py:132`) calls
  `verifier_stub`, which always returns
  `AUTHORIZATION_UNVERIFIABLE(VERIFIER_CONFIG_MISSING)` with no I/O
  (`availability.py:73`). `routing_refuses` (`availability.py:101`) can return
  true only for `AUTHORIZED`, so no shipped path refuses.
- The C2a declaration parser accepts exactly `schema`, `availability: "closed"`
  and `memory_path: ".mneme/project_memory.json"`; unknown keys are ignored.
- Activation lives inside canonical memory: `activation.state`, set to
  `active` with `activated_at` by `mneme protect activate`
  (`protection.py:637`, `setup_state.py:136`), with `protection` bindings in
  `decision_index`.

## 3. Trusted Git verification

The verifier is a pure function of the local declaration's location and the
live remote. It returns one `Verification` record:
`authorization ∈ {AUTHORIZED, REVOKED, VERIFIED_ABSENT, AUTHORIZATION_UNVERIFIABLE}`,
a `reason` from ADR-033 §4.3's closed set (UNVERIFIABLE only), the observed
`branch` and `tip` commit, and the parsed baseline declaration when present.

### 3.1 Trigger (unchanged)

The verifier runs only when `discover_declaration` returns a declaration,
valid or invalid. No other input starts it. No declaration: zero verifier
calls (P2, ADR-033 §4.3).

### 3.2 Repository location

- The **policy root** is C2a's: the first ancestor of the edit target that
  contains `.mneme/`. It must also be the Git top-level: `<policy root>/.git`
  is a directory or a `gitdir:` file. Otherwise
  `UNVERIFIABLE(VERIFIER_CONFIG_MISSING)`.
- The remote is **always `origin`**. Its URL is read from the repository's own
  config file only (the common dir's `config` for linked worktrees) with
  `git config --file <path> --get-all remote.origin.url`. Includes, system,
  global and environment config are not read. Not the local declaration,
  which an in-scope ADV-1 edit could otherwise point at another remote.
- Exactly one URL, scheme `https`, no userinfo, query or fragment. Anything
  else (absent, several, `ssh`, `file`, a local path) is
  `VERIFIER_CONFIG_MISSING`.
- **URL normalization** for comparisons: lowercase scheme and host, remove a
  default port, trailing `/` and one trailing `.git`.

### 3.3 Git execution environment

Every Git subprocess the verifier starts:

- runs in a fresh Mneme-created temporary directory outside the repository,
  with `GIT_DIR` set to a bare repository initialized there and
  `GIT_CEILING_DIRECTORIES` set to its parent;
- receives a **constructed** environment, not the inherited one: `PATH` and
  the OS variables required to start a process (`SYSTEMROOT`, `COMSPEC`,
  `PATHEXT` on Windows); `HOME`, `USERPROFILE`, `XDG_CONFIG_HOME`, `TMP`,
  `TEMP` pointing at the temp directory; `GIT_CONFIG_NOSYSTEM=1`;
  `GIT_CONFIG_GLOBAL` pointing at an empty file; `GIT_TERMINAL_PROMPT=0`. No
  `*_PROXY`, `GIT_*` (other than those listed), `SSL_CERT_*`, `CURL_*` or
  `MNEME_*` variable passes through;
- passes `-c protocol.allow=never -c protocol.https.allow=always
  -c http.sslVerify=true -c credential.helper= -c core.askPass=`;
- contacts only the URL from section 3.2, passed as an argument, never as a
  configured remote name read from the user's repository;
- leaves nothing behind: the temp directory is removed after each
  verification. There is **no persistent cache** of results or objects.

The verifier never reads `refs/remotes/*`, local branches, tags, reflogs or
`FETCH_HEAD` of the user's repository (spec SS-1).

### 3.4 Revision selection

- Mneme selects the revision: `git ls-remote --symref <url> HEAD`, read live.
  The symref target is the **baseline branch**; its object id is the
  **tip**. No agent-supplied ref, local ref or older snapshot is accepted
  (ADR-033 §4.2).
- The tip commit is fetched by object id, so a ref that moves between the two
  calls cannot substitute content.
- Missing `HEAD` or symref on the remote: `UNVERIFIABLE(REF_MISSING)`.

### 3.5 Identity binding

The baseline declaration (section 4) records `repository.url` and
`repository.branch`. At verification:

- normalized `origin` URL ≠ baseline `repository.url` →
  `UNVERIFIABLE(EVIDENCE_INVALID)` (catches a mirror that copied an
  authorized history under another URL);
- baseline branch from 3.4 ≠ baseline `repository.branch` →
  `UNVERIFIABLE(EVIDENCE_INVALID)`.

### 3.6 Time budget

All verifier subprocesses share one wall-clock budget of **15 seconds**
(`_VERIFIER_TIMEOUT_SECONDS`), separate from the existing 10-second check
timeout. Exceeding it returns `UNVERIFIABLE(TIMEOUT)`. The implementation may
run verification concurrently with the check; the outcome must not depend on
ordering.

### 3.7 Failure reason mapping

| Observed | Reason |
|---|---|
| Section 3.2 preconditions fail | `VERIFIER_CONFIG_MISSING` |
| Host name does not resolve | `DNS` |
| Connection refused, reset or unreachable | `NETWORK` |
| TLS handshake or certificate verification fails | `TLS_IDENTITY_MISMATCH` |
| HTTP 401/403, or Git asks for credentials | `AUTH` |
| Budget exceeded | `TIMEOUT` |
| No `HEAD` symref, or tip object not served | `REF_MISSING` |
| Shallow or incomplete history where history is needed (5.1 step 4) | `HISTORY_INCOMPLETE` |
| Invalid baseline evidence (sections 3.5, 4, 5.1) | `EVIDENCE_INVALID` |
| Any other verifier exception or unclassified Git failure | `VERIFIER_CRASH` |

`ROLLBACK_DETECTED` and `CLOCK_REGRESSION` stay reserved (Architecture B only).
Classification from Git's stderr is best effort; a misclassified failure is
still UNVERIFIABLE, so it cannot cause a refusal.

## 4. Declaration schema (additive to C2a v1)

The file stays `.mneme/availability.json` and the schema stays
`mneme.availability/v1`. C2a's three keys keep their exact values. C2b adds
`repository` and `authority`:

```json
{
  "schema": "mneme.availability/v1",
  "availability": "closed",
  "memory_path": ".mneme/project_memory.json",
  "repository": {
    "url": "https://github.com/example/project",
    "branch": "main"
  },
  "authority": {
    "events": [
      {
        "seq": 1,
        "op": "authorize",
        "prev": null,
        "activation": {
          "activated_at": "2026-10-21T09:00:00Z",
          "protected_decisions": ["mneme_001"]
        },
        "review": {
          "recorded_by": "Jane Developer",
          "independent_approver_attested": false,
          "baseline_protection_attested": true
        }
      }
    ]
  }
}
```

A C2a-only file (no `repository` or `authority`) is valid locally but can
never be `AUTHORIZED`: at the baseline it is `EVIDENCE_INVALID`.

### 4.1 Authority events and ordering

- `events` is an append-only list. `seq` starts at 1 and increases by exactly
  1. `op` is `authorize` or `revoke`. Two consecutive events with the same
  `op` are invalid.
- `prev` is `null` for `seq` 1, otherwise `"sha256:" + hex` of the previous
  event's canonical JSON (`json.dumps(event, sort_keys=True,
  separators=(",", ":"), ensure_ascii=False)` encoded as UTF-8).
- **Order is list position, validated by `seq` and `prev`.** No event carries
  a timestamp, and commit, author or committer dates are never read for
  precedence (ADR-030 §4, ADR-033 §4.3, spec RR-5).
- The last event governs: `authorize` → candidate `AUTHORIZED`; `revoke` →
  `REVOKED`. A revocation after an authorization supersedes it, and a later
  authorization supersedes the revocation.
- Any structural violation (bad `seq`, broken `prev`, unknown `op`, empty
  `events`, repeated `op`, missing required field) is `EVIDENCE_INVALID`.

### 4.2 Activation evidence binding

Each `authorize` event records the activation it relies on:

- `activation.activated_at`: copied from canonical memory's
  `activation.activated_at` at the baseline when the event was prepared;
- `activation.protected_decisions`: the sorted, nonempty set of decision ids
  with a `protection` binding at that baseline, read with the existing
  canonical loader (`load_persisted_decision_index`), not a new parser.

### 4.3 What the declaration does not contain

No decisions, rules, lifecycle, precedence or rule evaluation (ADR-030 §1,
ADR-033 §4.1). No timestamps used for authority. No host-specific path.

### 4.4 Review event

ADR-033 §4.5 requires a review event recorded on the protected baseline. In
C2b:

- **Recorded** means the event exists in the declaration at the live tip of
  the baseline branch. Under a PR-only ruleset it entered through a PR. The
  `review` block is the human's attestation, captured by the authority
  command (section 6).
- Mneme **does not verify** that a review happened (F1), that the approver was
  independent, or that the branch is protected (F2).
  `independent_approver_attested` and `baseline_protection_attested` are
  recorded claims. Diagnostics and `status` print them as "attested, not
  verified" and never present a declaration as independently reviewed.

## 5. State resolution

### 5.1 Baseline state `B`

Deterministic and evaluated in this order:

1. Section 3.2 preconditions. Failure: `UNVERIFIABLE(VERIFIER_CONFIG_MISSING)`.
2. Section 3.4 tip selection. Network failures map per section 3.7.
3. **Tip has a declaration** at `.mneme/availability.json`:
   1. it must parse as v1 with valid `repository` and `authority`, and pass
      section 3.5; otherwise `EVIDENCE_INVALID`;
   2. last event `revoke`: `REVOKED`;
   3. last event `authorize`: the tip's canonical memory at `memory_path` must
      exist, load, have `activation.state == "active"`, the same
      `activated_at` as the event, and a `protection` binding for every id in
      `protected_decisions`. All hold: `AUTHORIZED`. Otherwise
      `EVIDENCE_INVALID`.
4. **Tip has no declaration:** fetch the baseline branch's full first-parent
   history. If the history is shallow or incomplete:
   `UNVERIFIABLE(HISTORY_INCOMPLETE)`. Otherwise find the most recent
   first-parent commit whose tree contains the declaration:
   - none: `VERIFIED_ABSENT` (positive absence, ADR-033 §4.3);
   - its last valid event is `revoke`: `REVOKED` (deleted after revocation);
   - otherwise (last event `authorize`, or invalid):
     `UNVERIFIABLE(EVIDENCE_INVALID)`. **This pins RR-7:** baseline deletion
     without a revocation record is neither REVOKED nor VERIFIED_ABSENT.

**Step 4 never changes enforcement.** Each outcome it can produce
(`VERIFIED_ABSENT`, `REVOKED`, `UNVERIFIABLE`) forbids an availability
refusal. History is fetched only to label the outcome correctly, so its cost
affects diagnostics, not protection.

**The tip chain is authoritative (Q2).** When the tip has a declaration, `B`
is decided from the tip's event list alone. A later reviewed merge that
rewrites or truncates the list is treated as reviewed authority. Truncation
that drops a trailing `revoke` over-blocks (safe direction). Truncation that
drops a trailing `authorize` reverts to an earlier reviewed `revoke`.

### 5.2 Local relation `L`

Computed only when `B` is `AUTHORIZED`, by comparing the parsed local
declaration with the baseline declaration (parsed objects, so line endings
and key order do not matter):

| `L` | Meaning |
|---|---|
| `MATCH` | Equal |
| `BEHIND` | Valid; equal except that its `events` are a strict prefix of the baseline's |
| `DIVERGES` | Valid but otherwise different (other URL, branch, events or fields) |
| `INVALID` | Present but unparseable or invalid (C2a `problem` set) |

`BEHIND` is still a tamper class. A rolled-back local declaration looks
exactly like a stale clone, and ADR-033 §4.2 treats rollback as tampering.
The diagnostic tells the user how to fix it: update from the baseline branch.

### 5.3 Routing (ADR-033 §4.4)

Evaluated in order. "Refuse" always means exit 2 with an operational
UNEVALUATED diagnostic (section 8), never a rule FAIL.

| # | Condition | Outcome |
|---|---|---|
| R0 | No local declaration | C2a P1 path, byte-identical, no verifier call |
| R1 | `B` = `REVOKED` or `VERIFIED_ABSENT` | No availability refusal. Existing behavior; a missing memory keeps the ordinary proceed |
| R2 | `B` = `UNVERIFIABLE(reason)` | Visible proceed with the reason. The check still runs when memory exists; a trusted complete strict FAIL still blocks (U-10, BP-9). An SS-3 mismatch is reported, the result is "not bound to the declared memory", and the repository counts as inactive |
| R3 | `B` = `AUTHORIZED`, `L` ≠ `MATCH` | **Refuse**: `LOCAL_DECLARATION_TAMPERED` (`BEHIND`, `DIVERGES` or `INVALID`) |
| R4 | `B` = `AUTHORIZED`, effective memory ≠ bound path (SS-3) | **Refuse**: `MEMORY_PATH_MISMATCH` |
| R5 | `B` = `AUTHORIZED`, canonical memory missing | **Refuse**: `MEMORY_MISSING` |
| R6 | `B` = `AUTHORIZED`, evaluation `NOT_RUN`, `UNTRUSTED`, `INCOMPLETE` or `COMPLETENESS_UNSTATED` | **Refuse**: matching category. A mixed partial result lists its matched violations as partial (C2a §3.6) |
| R7 | `B` = `AUTHORIZED`, `SKIPPED` | Existing skip |
| R8 | `B` = `AUTHORIZED`, `TRUSTED_COMPLETE` | Existing strict/warn semantics. Strict FAIL blocks as a decision violation; warn defers |

R3 and R4 apply even when the check would pass: tampering is refused
whatever the evaluation.

## 6. Authority operations

A new `mneme availability` command group. No existing command changes.

| Command | Precondition (live verification, section 5.1) | Effect |
|---|---|---|
| `mneme availability status` | none | Read-only. Prints `B`, reason, branch, tip, `L` and the attested-not-verified review fields. Never writes |
| `mneme availability authorize` | `B` is `VERIFIED_ABSENT` or `REVOKED`; tip memory `activation.state == "active"` with ≥1 protection binding; section 3.2 holds | Writes `.mneme/availability.json` from the baseline's content (or new) with one appended `authorize` event, `prev` linked, activation evidence from the **tip**, and the review attestation |
| `mneme availability revoke` | `B` is `AUTHORIZED` | Writes the baseline's content with one appended `revoke` event |

All three:

- refuse with a clear message when `B` is `UNVERIFIABLE`; nothing is written
  (spec S-07);
- `authorize` and `revoke` require an **interactive TTY confirmation** in
  which the human types their name (`review.recorded_by`) and answers the two
  attestations. There is no non-interactive flag. This is a convenience
  barrier against accidental agent invocation, **not a security boundary**:
  the authority is the reviewed merge;
- refuse when the local declaration exists and differs from the baseline's,
  unless `--replace-local` is given;
- never run `git add`, `commit`, `push` or merge, and never touch canonical
  memory. They print the next step: commit the file, open a PR, have it
  reviewed and merged. Authorization takes effect only when the event is at
  the baseline tip.

While an enrollment PR is open, the local declaration has an event the
baseline lacks. `B` is `VERIFIED_ABSENT` or `REVOKED`, so there is no refusal,
as R1 requires. A deleted local declaration is never a revocation (ADR-033
§4.3).

## 7. Hook integration boundary

- Keep C2a's `discover_declaration`, target-path anchoring, classifier,
  `emit_availability` call sites and the no-declaration path unchanged.
- Replace `verifier_stub` as the default verifier with the section 3 verifier.
  Verification runs at most once per hook invocation (in-memory only).
- Extend `routing_refuses` with one input, `local_relation`, implementing R3.
  R4-R8 already match its current branches.
- The verifier injection seam stays test-only and must not be selectable from
  the environment or the hook envelope.
- **In-process transport.** The benchmark-only `inprocess` transport exits 0
  on its watchdog (`hook.py:606`). It is declared **unsupported** with
  `AUTHORIZED` (documented, not changed); the supported default subprocess
  transport returns `None` on timeout, which R6 refuses.
- No change to Bash, SessionStart, Stop, other integrations, CI or the
  `mneme check` contract.

## 8. Diagnostics and evidence

- Refusal text names the authorization state, branch and short tip, the
  category from section 5.3, and one remediation line. It never contains
  `architectural decision violated`, rule text, triggers, submitted content
  or checker stderr (spec P-04, ADR-033 §7).
- Refusals are operational UNEVALUATED and are never recorded as relevant
  enforcement observed (ADR-029).
- A trusted strict FAIL under any `B` keeps today's violation text, plus the
  availability line.
- Diagnostics are **emitted** on the existing stderr channel. For exit 2 the
  Claude Code blocking transport feeds stderr to the model, but delivery
  claims wait for C3 (C2a §3.7).
- **Amended by section 17 (2026-10-22):** C3 showed the exit-0 stderr
  diagnostic of an `AUTHORIZATION_UNVERIFIABLE` proceed never reaches the
  model (#601). Section 17 adds one PreToolUse `additionalContext` object for
  that case only.

## 9. Regression matrix (deterministic, offline)

Fixtures under `tests/fixtures/availability_policy/v1/`, tests under
`tests/integrations/claude_code/`. Remotes are local bare repositories reached
through a **test-only transport seam**; the shipped HTTPS-only rule is tested
separately. Real network is blocked (sockets patched to fail).

**Verifier (V):**

| # | Case | Expected |
|---|---|---|
| V1 | Tip declaration, last `authorize`, activation evidence holds | `AUTHORIZED` |
| V2 | Last event `revoke` | `REVOKED` |
| V3 | authorize → revoke → authorize | `AUTHORIZED` |
| V4 | Full history, never a declaration | `VERIFIED_ABSENT` |
| V5 | Shallow or incomplete history, tip without declaration | `UNVERIFIABLE(HISTORY_INCOMPLETE)`, never ABSENT |
| V6 | Declaration deleted at baseline after `authorize` (RR-7) | `UNVERIFIABLE(EVIDENCE_INVALID)` |
| V7 | Declaration deleted at baseline after `revoke` | `REVOKED` |
| V8 | Broken chain: `seq` gap, wrong `prev`, repeated `op`, empty events | `EVIDENCE_INVALID` |
| V9 | Commit and author dates forged to reorder events (RR-5) | Outcome unchanged |
| V10 | `origin` URL ≠ baseline `repository.url` (mirror substitution) | `EVIDENCE_INVALID` |
| V11 | Remote `HEAD` branch ≠ baseline `repository.branch` | `EVIDENCE_INVALID` |
| V12 | Tip memory missing, not `active`, different `activated_at`, or a listed protection removed | `EVIDENCE_INVALID` |
| V13 | No `origin`, several URLs, `ssh`, `file`, local path, policy root not the Git top-level | `VERIFIER_CONFIG_MISSING` |
| V14 | Repo-local `insteadOf`, `http.proxy`, global config, `HTTPS_PROXY`, `GIT_*` and `MNEME_*` set | None reach the Git process: recorded argv, env and endpoint show the section 3.3 values only |
| V15 | `refs/remotes/origin/*` rewritten to an older commit | No effect |
| V16 | Each section 3.7 failure induced | Matching reason; never `VERIFIED_ABSENT` or `REVOKED` |
| V17 | Two consecutive verifications | Two live fetches; nothing left in the repository, `.git/` or temp |
| V18 | Budget exceeded | `UNVERIFIABLE(TIMEOUT)` within budget plus a margin |

**Hook (H), real hook entry point and real `mneme check`:**

| # | Case | Expected |
|---|---|---|
| H1 | `AUTHORIZED`, canonical memory missing | **Exit 2**, `MEMORY_MISSING` (the first practical proof) |
| H2 | `AUTHORIZED`, complete PASS | Proceed |
| H3 | `AUTHORIZED`, strict trusted FAIL | Today's block and violation text |
| H4 | `AUTHORIZED`, each of `INCOMPLETE`, `COMPLETENESS_UNSTATED`, `UNTRUSTED`, crash, timeout, materialization failure | Exit 2, matching category |
| H5 | `AUTHORIZED`, incomplete with matched violation | Exit 2 UNEVALUATED, violations listed as partial |
| H6 | `AUTHORIZED`, local `BEHIND`, `DIVERGES`, `INVALID`, each with a passing edit | Exit 2, `LOCAL_DECLARATION_TAMPERED` |
| H7 | `AUTHORIZED`, `MNEME_MEMORY` set to other memory | Exit 2, `MEMORY_PATH_MISMATCH` |
| H8 | `AUTHORIZED`, warn mode, FAIL | Existing warn defer |
| H9 | `AUTHORIZED`, empty introduced delta | Existing skip |
| H10 | `REVOKED` and `VERIFIED_ABSENT`, memory present and missing | No availability refusal |
| H11 | `UNVERIFIABLE`, each reason, strict FAIL | Existing block (U-10), reason disclosed |
| H12 | `UNVERIFIABLE`, `MNEME_MEMORY` mismatch | Proceed; mismatch reported; not bound |
| H13 | `AUTHORIZED` at baseline, local declaration deleted | Identical to C2a P1: no trigger, no verifier call (section 0.1) |
| H14 | Every refusal from H1-H7 | No `architectural decision violated`, no submitted content |
| H15 | One end-to-end run through the real verifier and test transport | Same as H1 |

**Authority operations (A):**

| # | Case | Expected |
|---|---|---|
| A1 | `authorize` when `B` is `AUTHORIZED` or `UNVERIFIABLE`, activation not `active`, or no TTY | Refused, nothing written |
| A2 | `authorize` from `VERIFIED_ABSENT` and from `REVOKED` | Only the declaration written; chain valid; no Git operation run |
| A3 | `revoke` unless `AUTHORIZED` | Refused |
| A4 | `status` | Byte-identical working tree before and after |
| A5 | Local declaration differs, no `--replace-local` | Refused |

**Regression gates (unchanged):** C2a P1/P2, D1-D9 and S1 pass unchanged.
D1-D8 fixtures have no `origin`, so the real verifier still returns
`VERIFIER_CONFIG_MISSING`. Canonical memory byte-identical across all cases
(spec P-05). The frozen 7/7 benchmark is run **fresh at the final reviewed
head**, plus the PR gate and the Linux full suite.

## 10. Explicitly preserved

- `mneme check`, its output, exit codes and the malformed-memory crash path.
- `find_memory`, `MNEME_MEMORY` precedence, T-08 slice 1 selection, C2a
  declaration discovery and the policy-root rule.
- strict/warn, `assess_verdict`, `DecisionRetriever`, `ConflictDetector`,
  ADR-020 applicability, the frozen benchmark.
- `decision_index` as sole decision authority; `setup → active` and
  `mneme protect activate` unchanged.
- Bash, SessionStart and Stop handlers (ADR-021).

## 11. Explicitly NOT authorized

- Architecture B: any host enrollment record, high-water mark or other trusted
  state outside the repository; any persistent cache.
- Any verification trigger other than the local declaration.
- Credential helpers, tokens, SSH or any non-HTTPS transport for the verifier.
- Forge API calls (review, approval or protection evidence).
- Refusals outside `PreToolUse` `Edit|Write|MultiEdit`; Bash class-A handling.
- Any change to CI workflows, rulesets, Actions policy or other integrations.
- Live host validation (C3) and CI implementation (C4).
- Any claim that a repository is protected against deletion of the
  declaration, hook removal, `.git/config` edits, or ADV-2/ADV-3 actions.

## 12. Required acceptance evidence (implementation PR)

- Sections 3-8 implemented exactly; nothing else changed.
- The full section 9 matrix passing, with the comparison method for P1 parity
  recorded.
- **Latency:** median and p95 added hook latency for H2 and H1 against a
  public HTTPS test repository, measured on Windows and Linux. Reported, not
  gated, so the owner can decide whether F4's cost is acceptable before C3.
- Frozen benchmark fresh at the final head; PR gate; Linux full suite.
- The PR repeats section 1.1 verbatim, states the section 1.2 evidence
  ceiling, and claims diagnostics as emitted, not delivered.

## 13. Remaining limitations (claims ceiling)

C2b claims, at hook level only: for an anonymously readable HTTPS repository
whose local declaration is present and whose `origin` and Git configuration
are not tampered with, a verified `AUTHORIZED` baseline makes the direct-write
hook refuse when memory is missing, evaluation is unavailable or untrusted,
the local declaration diverges, or effective memory is not the bound memory.

It does **not** claim protection against:

- deletion of the local declaration or `.mneme/` (section 1.1);
- removal or substitution of the hook, the `mneme` CLI or the `git` binary
  (spec BP-6, BP-7);
- changes to `remote.origin.url` or other `.git/config` content. This is
  "git configuration" under ADR-033 §4.0, and it is reachable by direct-write
  tools as well as Bash;
- verifier denial (any UNVERIFIABLE reason proceeds visibly, BP-2);
- substitution of `origin` by a repository whose own history shows absence or
  revocation (BP-3);
- forged or self-approved revocation with the developer's credentials (BP-4,
  ADV-3); single-developer review is attested, not independent;
- forge settings: branch protection is attested, not verified;
- reviewed rewrites of the authority list (section 5.1);
- private repositories (not eligible in C2b);
- host non-mutation and diagnostic delivery (C3).

## 14. Proposed `[layer1-freeze]` amendment (draft; not applied here)

To be opened as a separate PR titled
`[layer1-freeze] Authorize ADR-033 C2b verified availability authorization`,
appended to `docs/architecture/layer1-freeze-e73ff7d.md` after this charter
merges:

> **Amendment — authorize ADR-033 C2b verified availability authorization
> (YYYY-MM-DD)**
>
> This authorizes **one verifier, one declaration extension, three authority
> commands and one refusal route at one boundary**. It does not authorize
> Architecture B, any cache, credential use, forge API, CI change, or any
> change to other boundaries.
>
> **Change:** at the Claude Code direct-write boundary (`handle_event`,
> `mneme/integrations/claude_code/hook.py`), replace the C2a verifier stub
> with a live verifier of the remote default-branch tip, per the C2b charter
> §§3-5, and refuse a supported direct write with an operational UNEVALUATED
> diagnostic only when authorization is verified as `AUTHORIZED` and a §5.3
> R3-R6 condition holds. Add `mneme availability status|authorize|revoke` per
> §6. Without a local declaration, behavior is byte-identical to `main`.
>
> **Sections referenced:** the Freeze Anchor **Status** clause and the
> Amendment Procedure.
>
> **Rationale (Amendment Procedure §3(b)).** A distinct behavioral charter was
> already merged: Reliable Enforcement C2b charter (PR #NNN, squash `<sha>`),
> under accepted ADR-033 (#483, `78459d1a`) and after C2a (#576, `72b6d04a`).
>
> **Governing authority:** accepted ADR-033, ADR-021, ADR-022, ADR-029,
> ADR-030; the merged C1, T-08 slice-1 and C2a charters.
>
> No other code path is authorized.

## 15. Sequence

1. This charter PR: review and merge (documentation only). Section 16
   resolved 2026-10-21.
2. The section 14 `[layer1-freeze]` PR: review and merge.
3. One implementation PR meeting section 12.
4. Separately authorized: C3 live proof (host non-mutation, diagnostic
   delivery, spec U/T/RV/S/P groups with E1-E10), then C4.

## 16. Review decisions (resolved)

The owner accepted every recommendation below as pinned on 2026-10-21. Each
is now part of the charter's contract; changing one needs a charter
amendment.

- **Q1. Private repositories.** C2b reads no credentials (F3), so private
  remotes cannot enroll. *Accepted:* accept for C2b and take the
  credential source as a separate decision. Every option (user-global helper,
  a token in user-scope config) widens the ADV-2 surface ADR-033 already
  discloses, so it needs its own review.
- **Q2. Tip chain versus full-history verification.** Section 5.1 decides
  `AUTHORIZED`/`REVOKED` from the tip's event list and walks history only
  when the tip has no declaration. Walking full history on every edit would
  also catch reviewed rewrites of the list, at a per-edit cost that grows
  with the repository. *Accepted:* tip chain, as pinned. Every refusal
  already depends only on the tip, and reviewed changes to the baseline are
  authority by definition under the in-scope threat model.
- **Q3. Forge evidence.** Review and protection are attested, not verified
  (F1, F2). *Accepted:* defer forge API verification. It is
  forge-specific, needs credentials (Q1), and would still not prove reviewer
  independence (ADR-033 §4.5).
- **Q4. Fixed remote `origin`.** *Accepted:* pin `origin`. Reading the
  remote name from the declaration lets an ADV-1 edit point verification at
  another configured remote, such as a fork.
- **Q5. `BEHIND` refuses.** A clone that has not pulled the latest authority
  event is refused until it updates. *Accepted:* keep. ADR-033 §4.2
  treats rollback as tampering, the two are indistinguishable, and authority
  events are rare.
- **Q6. Edits to `.git/config` by direct-write tools.** They can redirect
  verification (section 13). *Accepted:* disclose in C2b. Refusing
  edits under `.git/` is a new protected-surface rule and needs its own
  decision.
- **Q7. Declaration filename (C2a Q2).** *Accepted:* keep
  `availability.json`; C2b's additive fields fit it.

## 17. Amendment 1: deliver the UNVERIFIABLE proceed diagnostic to the model (2026-10-22)

**Status:** **DRAFT**, proposed for review. It amends section 8 (diagnostics)
only. Merging it authorizes no implementation. Implementation needs the
section 17.8 `[layer1-freeze]` amendment, opened as its own PR after this
amendment merges (Amendment Procedure §3(b)).
**Decision:** the owner accepted Option 1 of the F-R2 assessment
([`2026-10-22-c3-fr2-unverifiable-diagnostic-delivery-assessment.md`](2026-10-22-c3-fr2-unverifiable-diagnostic-delivery-assessment.md),
#604) on 2026-10-22, with the scope fixed in 17.2 to 17.7.
**Evidence:** C3 Batch R record (#601), probe R-1 Edit-2.

### 17.1 Why

When authorization is `AUTHORIZATION_UNVERIFIABLE`, the hook proceeds
(section 5.3 R2) and writes its diagnostic to stderr with exit 0. Per the
Claude Code hook contract, exit-0 stderr reaches the debug log only. In C3
R-1 Edit-2 the model received no trace of it, so ADR-033 §4.3's "visible
proceed" is unmet. Two things are distinct:

- **F-R1:** an unverifiable baseline lets the edit proceed. That is the
  accepted Architecture A limitation, **unchanged** by this amendment.
- **F-R2:** the model is not told. **This amendment closes F-R2:** when Mneme
  cannot verify authorization and allows an edit, the model must know the edit
  proceeded without verified fail-closed enforcement. That does not make the
  edit safe. It makes the limitation observable.

### 17.2 Behavior (direct-write PreToolUse hook only)

**Trigger, all conditions together:**

- a local declaration is present (the C2a trigger, unchanged);
- the verification result is `AUTHORIZATION_UNVERIFIABLE` (any reason);
- the hook returns exit **0** on that invocation.

**Output:** exactly **one** JSON object, on one stdout line:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "<text>"}}
```

with no `permissionDecision`, no `permissionDecisionReason` and no
`systemMessage`.

**Text:** fixed template, ASCII only. `<REASON>` is the closed-set reason code.

```
Mneme availability: authorization could not be verified (AUTHORIZATION_UNVERIFIABLE, reason <REASON>). This edit proceeded without fail-closed availability enforcement.
```

When an SS-3 memory mismatch is also present, one sentence is appended:
`The effective memory differs from the declared memory.`

**The text must never:**

- include submitted source content, decision text, rule values, triggers or
  file paths;
- state or imply that the edit was checked, verified, compliant or safe;
- be phrased as an instruction to the model (factual statements only, per
  the hooks guidance on context text).

**Unchanged:**

- the exit code;
- every existing stderr line, byte for byte;
- permission behavior: no permission decision is added, removed or altered.

**Not triggered by:**

- `AUTHORIZED`, `REVOKED` or `VERIFIED_ABSENT`;
- the no-declaration path, which stays byte-identical (C2a P1);
- any exit-2 outcome. A trusted strict FAIL under UNVERIFIABLE still exits 2,
  and its stderr already reaches the model through the blocking transport.

### 17.3 Warn-mode `defer` interaction (explicit)

Warn mode (`_emit_defer`) already writes a stdout object with
`permissionDecision: "defer"` when a trusted WARN or FAIL verdict occurs in
warn mode. Per the current hooks reference:

- `additionalContext` is **ignored** when `permissionDecision` is `"defer"`;
- in `claude -p`, `"defer"` **ends the turn** so the tool can be resumed
  later. In interactive sessions Claude Code **ignores the hook result** with
  a warning;
- `permissionDecisionReason` for `"defer"` goes to the debug log only.

Changing warn-mode output would change permission and flow behavior, which is
outside this amendment. So when the 17.2 trigger holds **and** warn mode would
emit `defer` on the same invocation, the rule is:

- **Still one object.** Never two JSON objects.
- **The warn-mode object is kept as it is** (`permissionDecision: "defer"`,
  same reason text), and the 17.2 availability text is **appended** to
  `permissionDecisionReason` on a new line. No output is dropped from the
  object.
- **No `additionalContext` field is added.** The docs say the host ignores it
  with `defer`, so including it would imply a delivery that cannot happen.
- **Delivery to the model is not claimed for this case.** It is recorded as a
  disclosed limitation of this amendment, with the stderr diagnostic
  unchanged.

**Separate finding (F-W1), recorded for an owner decision and not changed
here:** `_emit_defer`'s docstring assumes `defer` "hands the call back to the
normal permission flow". The current docs give it different semantics: it
ends the turn in `-p` and is ignored interactively. Warn mode may therefore
not behave as documented in `docs/integrations/claude-code.md` ("Surface
warning to Claude, never block"). C3's fixture runs strict mode, so C3 is
unaffected. Any warn-mode change needs its own decision.

### 17.4 Regression tests (deterministic, offline; implementation PR)

| # | Case | Expected |
|---|---|---|
| A1 | Declaration present, UNVERIFIABLE (`VERIFIER_CONFIG_MISSING`), memory missing | exit 0; stdout is exactly one JSON object matching 17.2 with reason `VERIFIER_CONFIG_MISSING`; stderr byte-identical to `main` |
| A2 | UNVERIFIABLE (each closed-set reason via the test seam), complete PASS | as A1, with the matching reason |
| A3 | UNVERIFIABLE with an SS-3 `MNEME_MEMORY` mismatch | as A1 plus the mismatch sentence |
| A4 | UNVERIFIABLE, strict trusted FAIL | exit 2; stdout empty; stderr unchanged (violation text plus availability line) |
| A5 | UNVERIFIABLE, warn mode, trusted WARN/FAIL | exit 0; exactly one object with `permissionDecision: "defer"`, original reason plus the appended availability text; **no** `additionalContext` |
| A6 | AUTHORIZED refusals (R3-R6) | unchanged: exit 2, stdout empty |
| A7 | `REVOKED`, `VERIFIED_ABSENT` proceeds | stdout empty; stderr unchanged |
| A8 | No declaration (C2a P1/P2) | byte-identical to `main`; no verifier call |
| A9 | Every A1-A5 output | parses as one JSON object; ASCII only; contains no submitted-content marker, no decision text, no path; never "checked", "verified edit", "compliant" or "safe" |
| A10 | All C2a and C2b tests | pass unchanged, apart from the stdout additions A1-A3 and A5 |

### 17.5 Live proof (C3; separately authorized run)

The implementation is not accepted as closing F-R2 until a live run on
**Claude Code 2.1.303** shows that the 17.2 object reaches the model on an
UNVERIFIABLE proceed. The proof is the text in a model-bound entry: the
transcript `hook_additional_context` attachment, under the H1 rules R1-R3.
Debug or host output does not count (rule R4).

- **Setup:** a deterministic UNVERIFIABLE condition, for example scope row D-2
  (`origin` removed, giving `VERIFIER_CONFIG_MISSING`), so no network block is
  needed.
- **Controls:** the paired ABSENT and AUTHORIZED controls.
- **Harness:** the classifier is extended to check delivery for UNVERIFIABLE
  proceed rows, which needs transcript capture in headless runs.
- **Authorization:** that harness change and run are authorized separately.

The C3 record #601 is not rewritten. R-1 Edit-2 stays a FAIL.

### 17.6 Preserved

- ADR-033 Architecture A, including F-R1 (no cache, no retry, no grace
  window, no Architecture B).
- All refusal behavior (section 5.3), exit codes, stderr text, permission
  behavior.
- Warn-mode output (except the 17.3 append).
- `mneme check`, the verifier, the declaration schema.
- Bash, SessionStart and Stop handlers.

### 17.7 Not authorized

- Any `systemMessage` (user-facing) output; it needs the interactive-arm
  evidence first (C3 scope Q2).
- `additionalContext` for any state other than `AUTHORIZATION_UNVERIFIABLE`.
- Any warn-mode change beyond 17.3, including F-W1.
- Any runtime change before the 17.8 amendment merges.
- Any C3 run, R-1 re-run or C4 work.

### 17.8 Proposed `[layer1-freeze]` amendment (draft; not applied here)

To be opened as a separate PR titled
`[layer1-freeze] Authorize ADR-033 C2b Amendment 1 UNVERIFIABLE diagnostic delivery`,
appended after the C2b amendment in `docs/architecture/layer1-freeze-e73ff7d.md`
once this amendment merges:

> **Amendment — authorize ADR-033 C2b Amendment 1: UNVERIFIABLE diagnostic
> delivery (YYYY-MM-DD)**
>
> This authorizes **one additional stdout output at one boundary**. It does
> not authorize any refusal, permission or exit-code change, any other
> availability state, `systemMessage`, or any warn-mode change beyond the
> charter's 17.3 append.
>
> **Change:** at the Claude Code direct-write boundary (`handle_event`, the
> `emit_availability` path in `mneme/integrations/claude_code/`), when a local
> declaration is present, authorization is `AUTHORIZATION_UNVERIFIABLE` and
> the hook exits 0, write exactly one stdout object
> `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": <17.2 text>}}`.
> In the warn-mode `defer` case, append the 17.2 text to the existing
> `permissionDecisionReason` instead, still as one object. Exit codes, stderr
> and permission behavior are unchanged. Without a declaration, behavior is
> byte-identical to `main`.
>
> **Sections referenced:** the Freeze Anchor **Status** clause and the
> Amendment Procedure.
>
> **Rationale (Amendment Procedure §3(b)).** A distinct charter amendment was
> already merged: C2b charter section 17 (PR #NNN, squash `<sha>`), following
> the C3 Batch R record (#601) and the F-R2 assessment (#604), under accepted
> ADR-033.
>
> **Governing authority:** accepted ADR-033 §4.3 and §7; the merged C2a and
> C2b charters.
>
> No other code path is authorized.

### 17.9 Sequence

1. This amendment PR: review and merge (documentation only).
2. The 17.8 `[layer1-freeze]` PR: review and merge.
3. One implementation PR meeting 17.4, with no other change.
4. Separately authorized: the 17.5 harness change and live proof on 2.1.303,
   then the narrow R-1 re-run. #601's original results are never
   overwritten.

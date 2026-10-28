# ADR-034 G2-1 R3 independent blind validation: pre-registration draft

**Date:** 2026-10-28  
**Status:** DRAFT FOR ARCHITECTURE AND INDEPENDENCE REVIEW. **Not frozen, not an authorization to author, seal, build a harness or score cases.**

## 1. Authority and claim

R1 and R2 both scored **FAIL**; G2-1 remains **FAIL**. Nothing here reinterprets
their results, reuses their concealed corpus or upgrades their outcomes.

This draft follows [ADR-034](../adr/ADR-034-static-numeric-upper-bound-typed-rule.md)
§3a and §7a–§7c, ADR-029 §2, the [G2-1 charter](../plans/2026-10-24-adr-034-g2-1-behavioral-charter.md),
the [R2 pre-registration and pre-decryption amendments](adr-034-g2-1-revalidation-preregistration-2026-10-26.md),
the [R2 FAIL/results and custody requirement](adr-034-g2-1-r2-blind-scoring-results-2026-10-27.md)
(#693 §9.5), and the [R3 custody boundary evidence](adr-034-g2-1-r3-key-custody-boundary-2026-10-28.md)
(#698, subsequent evidence comments).

**Claim to be evaluated, and only on PASS:** On Claude Code `PreToolUse`,
a `Write` to a verified-absent `.py` file with an existing parent within
the policy root is refused before mutation, under strict mode, when the
complete proposed source has a recognized `FORBID_NUMERIC_ABOVE` violation;
unrouted events retain legacy behavior. Hook records bind each outcome to
the correct cause, including non-numeric violations per ADR-034 §7c.
Relevant enforcement is separately gated by ADR-029 bindings. Synthetic
replay does **not** prove live host enforcement.

## 2. Source and candidate runtime pin: owner-reported, not a scoring freeze

| Item | Verified owner-reported value |
|---|---|
| Implementation commit (#697) | `1b0957af01df3ad036b12698663e167ae413885e` |
| `mneme/` Git tree | `656554d21ec1ef4ee474b6e6f69f681f0364a501` |
| Windows host | `arxwn`, standard account `MnemeAgent` |
| Detached implementation worktree | `%USERPROFILE%\r3-work\r3-implementation` |
| Implementation working tree | clean |
| Wheel | `mneme_hq-0.10.0-py3-none-any.whl` |
| Wheel SHA-256 | `f2ed395a6517006971f49baf169b957c10d0dfff4784ad36b3bb53eb9c024289` |
| Python | CPython 3.12.10 |
| pip | 25.0.1 |
| Installed dependency freeze file SHA-256 | `253e5bc832f81786e3cac033724d09f1196889572cb87ad72445c125543a00c2` |
| `pip check` | `No broken requirements found` |
| Installed Python sources | 111 source files hash-match pinned `mneme/` worktree; 0 mismatches |
| Source-vs-installed import check | installed `site-packages\mneme\__init__.py` imported from outside worktree |
| Claude Code agent version used for custody test | 2.1.312, **not** the R3 scoring host-version pin |

The wheel, Python version and freeze digest are **candidate** R3 build
metadata. The exact installed build provenance, wheel record contents,
installed file inventory, scoring host executable SHA-256, scorer harness
hashes, reference baseline wheel and dependency freeze, and full runtime
manifest must be independently captured in a **pre-scoring completion
record** before any unblinding. `pip check` and the 111 matching `.py`
files alone are not a complete wheel/installation attestation.

**Baseline:** R2's pinned pre-G2 parity baseline is not silently reused as
a scoring artifact. The protocol must explicitly identify and reproduce
the accepted baseline source and wheel with hashes. No unpinned package
upgrades or host-version substitution.

## 3. Fixed evaluation contract proposed for R3

**Inheritance:** Adopt R2's §4 corpus classes, concealed floors, smoke
limit, the §4.1 labels, §4.3 noncoverage, all G1–G8 gates, §6 fail policy,
R2 Amendment 1 and R2 Amendment 2 *as merged before R2 unblinding*.
R2's minimum remains **120 concealed scored cases** across its 13 classes;
public smoke cases do not count toward any concealed floor or gate.
Symlink capability is required for a full PASS.

**R3 new concealed class and floor (R3-P1 proposed resolution, for owner
acceptance before protocol freeze):** Keep all R2 concealed floors intact:
**120** concealed scored cases across 13 classes. Add one new class,
**AT (non-numeric attribution without a numeric subject)** with a floor of
**8** concealed scored cases. The R3 minimum is therefore **128**
concealed scored cases across **14** classes, not including public smoke.
No earlier class may be reduced to make room for AT.

| AT sub-class | Scenario, all routed verified-new `.py` writes under `open` availability | Required concealed minimum |
|---|---|---:|
| **AT-S0** | Strict; one or more `FORBID_LITERAL` violations; memory has **no numeric rule** | 2 |
| **AT-SN** | Strict; a literal violation and at least one numeric rule **present in memory** but with **no numeric applicability record** for this target | 2 |
| **AT-SX** | Strict; a literal violation and a numeric rule explicitly **EXCLUDED** for this target under ADR-020 | 2 |
| **AT-W0** | Warn; literal violation with **no numeric applicability record**. At least one case is literal-only and one has a numeric rule excluded from the target | 2 |
| **AT total** | | **8** |

For every AT case, the independent label must establish **no applied numeric
record**, a trusted checker violation for the applicable literal rule(s),
`checker.subject: null`, `rules: []`, and `violations` containing
the **exact independently derived** `(rule_id, rule_type)` pairs of
the violating rules. Strict cases must refuse with exit 2 and leave the
target absent; warn cases must defer with exit 0. The disposition cause is
`other_rule` in all AT cases; the harness maps it to the labelled
`literal_violation` **only if** a well-formed expected literal
`rule_id` is present. Each AT case labels empty per-rule numeric
relevance `{}`, event-level numeric relevance `false`, and completeness
from the applicable trusted checker contract, not from the observed
record. AT cases must not be copies or derived mutations of R1/R2 held-out
cases. Both members of every pair must have meaningfully different ADR
fixtures or rule identities, not just renamed paths.

**Inherited LIT control tightened without raising its floor:** Its existing
6-case concealed floor must include at least **2 mixed literal/numeric
cases** with numeric violation and a `proposed_new_source` subject,
and at least **2 mixed cases** with applied, recognized-clean numeric
rules and literal refusal. In the latter, a numeric clean result must
not inherit the unrelated literal refusal as numeric relevance
(ADR-034 §7b). These cases check that the D3 evidence change did not alter
the existing subject-present path. All original LIT requirements,
including presence and absence of numeric violation, still hold.

**Smoke and denominators:** Require **one newly authored public AT smoke**
case for scorer development, using different source, ADR and literal-rule
identity from concealed AT. Each public smoke case must come from a different
class, and public cases remain at most **10% of all cases**; with 128
concealed cases, at most **14** public smoke cases are permitted (14/142
is below 10%). Public smoke cases count toward **none** of the 128
concealed-floor or G1-G8 gate denominators. The final metadata-only corpus
freeze record reports the actual concealed and smoke counts per class.

**Scope boundary:** All AT cases use the charter's native `Write` event
and actual pinned-hook result, not a hand-mutated record. Synthetic,
deliberately malformed evidence records are **harness-level negative
fixtures**, never presented as native events or counted toward the
concealed floor.

**Normative independent attribution oracle / G6:** For every trusted
record, the scorer derives expected non-numeric attribution **from the
fixture ADRs and ADR-034 §7c**, including the independently derived
`rule_id` (ADR-034 §5), never from the observed hook `violations`
array. Compare the exact expected set of well-formed
`(rule_id, rule_type)` identities: any missing identity, extra
identity, duplicate or wrong type fails G6. Missing `rule_id`, empty
string, or non-string `rule_id` attributes **nothing**, even when
`rule_type` equals `FORBID_LITERAL`; no `rule_type`-only fallback can
turn `other_rule` into a passing literal cause. Untrusted or inconsistent
checker payloads cannot earn attribution. Preserve R2's ordered G6 checks
for numeric rule-ID set, per-rule relevance, event relevance and
completeness. `violations` alone never supports numeric relevance.

**Mandatory public synthetic scorer-negative tests before sealing:** Give
the independent harness its **own** fabricated record examples:
(a) missing `rule_id`; (b) empty-string `rule_id`;
(c) non-string values, at least null and number, with valid
`FORBID_LITERAL` type; (d) wrong but well-formed `rule_id`;
(e) duplicate `rule_id`; (f) extraneous valid identity; and
(g) untrusted/inconsistent checker data. Each must **fail** attribution
where a valid literal identity is required. A positive synthetic control
with correct id and type must pass. These tests do not count as R3
concealed cases and do not use D3 implementation regression fixtures.
Pin test and harness hashes in the pre-scoring completion record.

**Independence of oracle:** No use of actual implementation outputs,
D3 regression fixtures, R1/R2 concealed cases or their labels to create
R3 cases or expectations. Scorer authored from normative contract and
new public smoke fixtures. An independent public synthetic test of
malformed identities must be pinned before any sealed labels are opened.
The author and scorer cannot share agent transcript, hidden labels,
case content, post-scoring diagnosis, or each other's working directories
before the authorized unblind phase.

**Failure:** Any gate failure => **R3 FAIL**, never partial PASS;
unsafe passes and false blocks remain zero tolerance. No tuning,
post-hoc exclusion or re-scoring for a claim. Any substantive change to
implementation, corpus, labels, scoring harness or criteria after unblind
requires a new held-out round. Preserve R2's named narrow pre-decryption
amendments as explicit inherited exceptions, not ad hoc changes.

## 4. Custody and execution topology: OPEN prerequisite

Owner reports a working separation on `arxwn`:

- `MnemeOwner`: private-key custodian and owner-only decrypt/verify;
- `MnemeAgent`: Standard account, GPG **public key only**; agent-session
  synthetic encryption succeeded, decryption returned exit 2 (`No secret
  key`), owner private-key directory access denied;
- `hi`: administrator; excluded from R3 agent work;
- owner phone holding encrypted backup disconnected;
- searched agent home and TEMP revealed only `trustdb.gpg` and a
  synthetic ciphertext, since deleted (`Test-Path` false).

### 4.1 Minimal topology: reuse the existing accounts

**No additional Windows user is a prerequisite of this proposal.** The
candidate topology is a **sequential owner-mediated handoff** on `arxwn`:

| Role | Account and session | Boundary |
|---|---|---|
| New corpus author | `MnemeAgent`, new Claude Code session A | Normative ADR/charter and this protocol only; no former held-out corpora, D3 implementation tests or scorer transcript |
| Public-key sealer | `MnemeAgent`, after author completion | Encrypt only to the owner's public key; must not decrypt |
| Key custodian / handoff reviewer | Human owner acting under `MnemeOwner` only for private-key tasks | Owner decrypt-verifies, controls sealed materials, and verifies plaintext/transcript cleanup **without exposing secret keys to agents** |
| Independent harness author/scorer | `MnemeAgent`, newly started Claude Code session B, only **after** handoff clearance | From normative contract and new public smoke fixtures only; has no concealed plaintext, author notes or author transcript before the owner-controlled unblind |
| Administrator `hi` | Excluded from agent execution | No author or scorer session runs as admin |

**Important limitation:** Two Claude sessions sharing `MnemeAgent` are
*not an OS-enforced confidentiality boundary*. They share read authority
over files in that Windows profile. Independence must be assessed on
both (a) separate eligible sessions and work products and (b) a
**verified absence of readable hidden material at the handoff**. If the
required material cannot be made inaccessible to session B, the owner
must use a genuinely isolated execution identity/environment instead;
the protocol cannot simply waive independence.

### 4.2 Mandatory handoff gates before any scorer session

1. **Pin roles:** Identify author A, sealer, new scorer B, their versioned
   Claude sessions, effective Windows identities, execution roots and
   retained artifacts. Author A and scorer B may not be the same
   conversation, a fork, or a reused transcript. Record isolation
   statements. Neither may have authored the D3 implementation,
   inspected the earlier concealed corpora, or read prior score
   diagnosis details outside the accepted public contract.
2. **Complete custody checks before sealing (#693 §9.5):** Independently
   confirm that the **actual** author/sealer agent session cannot
   decrypt synthetic owner-key ciphertext, has no owner credentials
   or elevated execution path, and cannot reach private-key exports or
   backups through profile, shared/mounted or working locations.
   Repeat or explicitly revalidate on the **actual** scoring agent
   session and host before any unblind. Record owner decision. The
   earlier owner-reported Claude Code test is supporting evidence,
   not automatic closure.
3. **Seal and verify:** Deterministically seal the corpus for the owner,
   record metadata/hash only, owner decrypt-verifies outside
   `MnemeAgent`. The owner controls the sealed archive and any
   recovery material. Do not give session B decryption capability.
4. **Sanitize and inspect:** Before B starts, remove plaintext corpus,
   labels, generation scratch, console history containing hidden
   labels, and accessible author transcripts/caches from the
   `MnemeAgent` account. Owner retains needed audit artifacts only in
   owner-controlled encrypted/inaccessible storage. Check the
   author workspace, repository worktree, `TEMP`, reachable shared
   locations and Claude local session/history storage for accessible
   remnants, using metadata-only reports. Do not delete unrelated
   user data. File absence is not forensic SSD erasure.
5. **Owner handoff record:** A **separate verifier** reviews the
   evidence for the actual paths and sessions, records checks
   performed, unresolved visibility, and an explicit owner GO/NO-GO
   for starting B. If any hidden material is still accessible,
   **NO-GO**; separate sessions alone cannot substitute.
6. **New scorer session:** Start B only after GO. B builds and pins
   the independent harness using contract/public smoke, then owner
   conducts authorized unblind and B scores. If B encounters
   inaccessible/accessible prior author content unexpectedly, stop
   and record a protocol breach; no PASS may be claimed.

The owner handoff and synthetic custody checks are **not yet complete**.
This is a protocol design, not a statement that the existing same-account
arrangement has already proved blind independence.

**Other remaining checks:** System-wide absence of exports, shared or
mounted paths, exact identities of future agents, and host configuration
if scoring moves machines. Any unverified secrecy or independence
property blocks sealing or scoring.

## 5. Roles and protocol sequence (proposed, not authorized)

1. Owner reviews the inherited R2 gates, decides the R3-specific class
   floors and new total; reviews role independence and closes custody gate.
2. Pre-registration is reviewed and merged **before** any R3 corpus
   authoring; modifications require dated, accepted pre-unblind amendment.
3. New, eligible author creates R3 cases from normative specifications.
   Separate sanitized ambiguity brief and owner rulings, if necessary,
   before labels are frozen. Do not disclose hidden material to scorer.
4. Owner-approved custodian seals the new corpus with deterministic tar,
   manifest and public-key encryption; owner alone decrypt-verifies and
   controls plaintext deletion. Publish metadata and hashes only.
5. Independent scorer writes and pins an R3-specific harness, including
   malformed-`rule_id` public synthetic regression tests; do not modify
   R1/R2 harnesses.
6. Pin scoring host and baseline, wheel, dependencies, exact harness bytes,
   corpus integrity, symlink capability and all prerequisites in a
   **pre-scoring completion record**. Merge it before decryption.
7. Owner performs controlled unblind, scorer runs the prescribed two
   equivalent passes, scores G1–G8 and publishes metadata-only result.
   Evidence is sealed and plaintext copies removed under an explicitly
   approved custody-close procedure. Any failure remains FAIL.

The original R1/R2 concealed corpora and old scoring/evidence folders
remain off limits. All roles require a recorded identity and isolation
statement. Neither a working checkout nor a merged pre-registration
alone authorizes a scoring run.

## 6. Open decisions before protocol can be frozen

- **R3-P1:** **Specified in §3, awaiting owner acceptance with the
  completed PR review:** AT concealed floor **8** in four two-case
  sub-classes; 120 inherited concealed + 8 AT = **128** minimum,
  14 classes total. One public AT smoke required. No case generation
  until this numeric contract is accepted and pre-registration frozen.
- **R3-P2:** **Minimal same-account sequential handoff specified in §4.1–4.2,
  pending owner acceptance and observed handoff evidence.** No new Windows
  account is required *a priori*, but shared-profile accessibility is not
  considered independent isolation. If the handoff cannot establish
  absence of readable hidden material, a separate execution identity is
  mandatory before proceeding.
- **R3-P3:** Record independently verified #693 §9.5 custody gate closure
  for *actual* agent execution contexts on all relevant machines.
- **R3-P4:** Verify baseline/host pin policy, exact per-gate coverage of
  the D3 attribution cases, and scoring harness authoring restrictions.

**Nothing authorized by this draft:** corpus authoring, sealing,
unblinding, implementation changes, harness construction, reinterpreting
R1/R2, or any PASS / live enforcement / production claim. G2-1 remains
**FAIL**.

# ADR-034 G2-1 R3 independent blind validation: pre-registration draft

**Date:** 2026-10-28  
**Status:** DRAFT FOR ARCHITECTURE REVIEW. Owner accepted **R3-P1** (128 concealed cases, 14 classes) and **R3-P2** (conditional same-account handoff) on 2026-10-28. **Not frozen until reviewed and merged; not an authorization to author, seal, build a harness or score cases.**

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

**R3 new concealed class and floor (R3-P1 accepted by owner 2026-10-28,
subject to protocol review and merge):** Keep all R2 concealed floors intact:
**120** concealed scored cases across 13 classes. Add one new class,
**AT (non-numeric attribution without an APPLIED numeric rule)** with a floor of
**8** concealed scored cases. The R3 minimum is therefore **128**
concealed scored cases across **14** classes, not including public smoke.
No earlier class may be reduced to make room for AT.

| AT sub-class | Scenario, all routed verified-new `.py` writes under `open` availability | Required concealed minimum |
|---|---|---:|
| **AT-S0** | Strict; one or more `FORBID_LITERAL` violations; memory has **no numeric rule** | 2 |
| **AT-SN** | Strict; a literal violation and at least one numeric rule **present in memory** but with **no numeric applicability record** for this target | 2 |
| **AT-SX** | Strict; a literal violation and a numeric rule explicitly **EXCLUDED** for this target under ADR-020; require an EXCLUDED numeric applicability trace in the checker payload | 2 |
| **AT-W0** | Warn; literal violation with **no APPLIED numeric rule**. At least one case is literal-only (no numeric applicability trace) and one has a numeric rule EXCLUDED from the target with an EXCLUDED trace | 2 |
| **AT total** | | **8** |

**AT subject contract, independently labelled from the fixture (ADR-034
§7a/§7c; G2-1 charter §5.2):** Every AT case is routed by the hook but
has **no numeric rule whose applicability outcome is `APPLIED`**.
Distinguish the **checker's JSON payload `subject`** from the
**hook evidence record's `checker.subject`**:

| AT cases | Checker's `subject` | Hook evidence `checker.subject` | Hook `rules` |
|---|---|---|---|
| AT-S0; AT-SN without any numeric applicability trace; AT-W0 literal-only | **absent** (`null` when read) | `null` | `[]` |
| AT-SX, and AT-W0's EXCLUDED-numeric variant | `input_kind: unverified_input` (the numeric EXCLUDED trace is in checker applicability, but none is APPLIED) | `null` | `[]` |

This follows the pinned CLI fallback: if the proposed-file check
finds no APPLIED numeric rule it reverts to the legacy `--input`
evaluation. The CLI may emit `unverified_input` when a numeric trace
exists, including an EXCLUDED trace. The hook evidence only binds a
`proposed_new_source` subject, so its own `checker.subject` is
`null` in both rows. **Do not score a valid unverified checker
subject as a missing-subject defect.** An unexpected
`proposed_new_source` in AT fails G6; the exact expected checker
subject kind and relevant trace outcomes must be labelled independently.
For EXCLUDED traces, the excluded rule's `rule_id` is informational,
not part of G6's APPLIED numeric rule-ID set (R2 AMB-R2-07).

For every AT case, the independent label requires a trusted checker
literal violation and hook `violations` containing **exactly** the
independently derived `(rule_id, rule_type)` identities of the violating
rules. Strict cases refuse with exit 2, leaving the target absent; warn
cases defer with exit 0. The disposition cause is `other_rule`; the
scorer recognizes the labelled `literal_violation` attribution only
when the expected literal `rule_id` is well formed and correctly
reported. The numeric APPLIED rule-ID set and per-rule numeric relevance
are both `{}`; event-level numeric relevance is `false`.
Record-wide completeness is independently derived from the
applicable trusted checker contract and R2 amendments, never copied
from the observed hook record. AT cases must not be copies or derived
mutations of R1/R2 held-out cases. Each pair must differ meaningfully
in ADR fixtures or literal-rule identity, not just renamed paths.

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

**Mandatory public synthetic scorer-negative tests after the owner-approved handoff and before unblinding:** Give
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

**Practical session configuration:** Author A and scorer B use
different, pinned `CLAUDE_CONFIG_DIR` locations and distinct working
directories. The [official Claude Code environment-variable reference](https://code.claude.com/docs/en/env-vars)
documents that this controls the settings, session history and plugins
location. This is **session organization, not an access control**;
under the same Windows account B could still read A's directory until
the owner verifies its removal/inaccessibility at the handoff. Do not
copy hidden data or author transcripts into B's configuration.

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
2. **Complete pre-seal custody checks (#693 §9.5) for BOTH designated
   environments:** Independently verify the actual author/sealer agent
   context and a **disposable synthetic-only probe** in the designated
   scoring host/account, before any R3 corpus is sealed. Each must
   demonstrably fail decryption of a synthetic owner-key ciphertext,
   lack owner credentials and elevation, and have no access to
   secret-key exports or backups through profile, worktree,
   shared/mounted or transfer locations. The scoring probe must not
   start the future scorer B, inspect author material, or retain any
   synthetic outputs or session history accessible to B. Pin the
   execution identities and host(s), verification actor, limitations
   and explicit owner GO/NO-GO **before sealing**. Recheck the actual
   scoring session B after the owner-approved handoff and before
   unblinding. The earlier owner-reported Claude Code test is supporting
   evidence only; the #693 §9.5 pre-seal two-environment requirement
   is not waived.
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
6. **New scorer session:** Start B only after handoff GO. B builds and
   tests the independent harness using contract and public smoke cases;
   all §3 malformed-`rule_id` synthetic negative tests must be
   reviewed and pinned **before owner-authorized unblind**, not before
   corpus sealing. The pre-scoring completion record also pins the
   harness and relevant test hashes before unblind. Then owner
   conducts authorized unblind and B scores. If B encounters author
   content unexpectedly before unblind, stop and record a protocol
   breach; no PASS may be claimed.

The owner handoff and synthetic custody checks are **not yet complete**.
This is a protocol design, not a statement that the existing same-account
arrangement has already proved blind independence.

**Other remaining checks:** System-wide absence of exports, shared or
mounted paths, exact identities of future agents, and host configuration
if scoring moves machines. Any unverified secrecy or independence
property blocks sealing or scoring.

## 5. Roles and protocol sequence (proposed, not authorized)

1. Owner explicitly accepts the concealed-case floors (128 over 14
   classes), the handoff policy and the frozen evaluation criteria.
2. This pre-registration is reviewed and merged **before** any R3
   corpus authoring. Later changes need a dated, accepted amendment
   merged before unblind.
3. New, eligible author creates R3 cases from normative specifications;
   only sanitized ambiguity briefs reach the owner. The scorer sees
   no hidden cases or author transcript.
4. **Before sealing:** Independently verify **both** the actual
   author/sealer context and designated scorer environment using
   disposable synthetic-only key-custody probes (§4.2 step 2);
   record the owner's explicit #693 §9.5 gate decision. Do **not**
   start scorer B here: the scorer environment is probed independently
   without exposing author or corpus material. The pre-seal deadline
   does **not** require Windows setup before merging this
   pre-registration. Failure blocks sealing.
5. Owner-approved custodian seals the corpus with deterministic tar,
   manifest and owner public-key encryption. Owner alone decrypt-verifies,
   controls plaintext deletion and verifies the same-account handoff.
   Publish metadata/hashes only; scorer session B may not start until
   the independently reviewed handoff returns GO.
6. After the owner-approved handoff, independent scorer B starts a new
   session/config, develops an R3-specific harness using the contract and
   public smoke, and executes its own malformed-`rule_id` synthetic
   negative tests. Do not change R1/R2 harnesses. Reconfirm the actual
   scoring session's owner-key isolation and pin the negative-test
   evidence before any authorized unblind.
7. Pin scoring host, baseline, wheel, dependencies, harness bytes,
   corpus integrity and symlink capability in a **pre-scoring
   completion record**. Merge that record before decryption.
8. Owner controls unblind, scorer executes two equivalent passes,
   scores G1–G8 and publishes metadata-only results. Seal evidence
   and remove plaintext under a separately approved custody-close
   procedure. Any gate failure remains FAIL.

The original R1/R2 concealed corpora and old scoring/evidence folders
remain off limits. All roles require a recorded identity and isolation
statement. Neither a working checkout nor a merged pre-registration
alone authorizes a scoring run.

## 6. Owner rulings and remaining protocol review

- **R3-P1: ACCEPTED by owner, 2026-10-28.** Preserve R2's 120 concealed
  floor, add AT floor 8 in four two-case sub-classes; **128 minimum**
  across 14 classes. One public AT smoke required. Actual corpus content
  and counts are not yet created.
- **R3-P2: ACCEPTED as a conditional topology by owner, 2026-10-28.**
  Reuse `MnemeAgent` for separate, eligible author/scorer Claude sessions
  with distinct `CLAUDE_CONFIG_DIR`, but **no assumption** that separate
  sessions provide file access isolation. Independent reviewer must
  verify absence of scorer-readable hidden material at the handoff.
  A failed handoff blocks scoring and requires stronger isolation.
- **R3-P3: OPEN execution gate, not a pre-registration merge gate.**
  Independently verify and obtain an explicit owner decision on
  #693 §9.5 for **both** the actual author/sealer and designated
  scoring host/account via synthetic-only probes **before sealing**;
  the scorer's actual session is rechecked before unblind. The
  previously reported synthetic checks do not waive this.
- **R3-P4: OPEN architecture/scoring-contract review.** Confirm the
  source baseline/host re-pin and gate mapping below before merging
  this pre-registration as frozen.

### 6.1 Proposed R3-P4 review rule: baseline and host

Use the unchanged pre-G2 parity baseline **source commit**
`f8591102b2693379dabec9b5704862e194eca4ce`
(R1/R2 preregistrations). Pin its Git tree, newly built baseline
wheel, installed file manifest, dependency freeze and environment
independently in the **pre-scoring completion record**, alongside
the D3 implementation wheel. The existing R2 baseline wheel hash is
historical evidence only, **not** a substitute for a verified R3
baseline environment.

Follow the R2 §3 host-repin rule: the original live-host evidence
applies to Claude Code 2.1.310 with the exact #646 executable digest.
The owner's new installation reports **2.1.312**, so a new,
separately recorded live-host characterization using the R3
implementation must pass and merge **before R3 unblinding**. The
pre-scoring completion record pins the exact installed host
version and executable SHA-256; neither version nor checksum may
change for a scoring run. An earlier *custody* test in Claude Code
2.1.312 is **not** a substitute for this §8.B behavioral host test.

### 6.2 Proposed R3-P4 review rule: AT gates

Every concealed AT case is included in **G1**, **G3**, **G6**,
**G7** and **G8**, with G1 requiring strict blocks and
correct non-clean numeric outcomes as applicable, G3 requiring
no target mutation following refusal, and G6 requiring exact
non-numeric violation identities when the **hook's**
`checker.subject` is `null`, including cases whose **checker
payload** has `subject.input_kind: unverified_input`.
G6 also checks the independently expected checker subject kind
and excludes `EXCLUDED` numeric IDs from the applied-rule set.
Apply **G2**'s established literal-violation exception, not
a false-block designation for an expected literal refusal.
Apply **G4** to any AT input whose oracle expects a primary
unevaluated reason. The inherited **G5** parity scope remains
P/X/L (and the existing checker-level cases); AT does not
silently acquire an unsupported pre-G2 hook-parity claim.
Warn AT cases must exhibit the expected deferral without
falsely earning numeric relevance; any wrong G6 field fails.

Harness author is a new eligible, independent scorer session
operating from this normative protocol and **public** smoke
only. Public synthetic negative tests for malformed `rule_id`
must fail attribution as specified in §3, **after scorer B begins
following the sealed-corpus handoff and before unblinding**. No R1 or R2 hidden
case, harness modification or implementation regression fixture
may supply R3 expectations. Harness bytes, identity and hashes
must be accepted and merged **before** scoring.

**This section requires architecture review.** Its proposal
text alone is not an owner ruling on R3-P4 or permission to
start authoring.

**Nothing authorized by this draft:** corpus authoring, sealing,
unblinding, implementation changes, harness construction, reinterpreting
R1/R2, or any PASS / live enforcement / production claim. G2-1 remains
**FAIL**.

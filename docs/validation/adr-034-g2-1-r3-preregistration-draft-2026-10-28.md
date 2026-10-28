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

**R3 change required by D3:** Add fresh, independently authored cases with
non-numeric literal-rule refusal attribution where the checker has **no
`proposed_new_source` subject**; include cases with and without applicable
numeric rules, and warn-mode deferrals as permitted by the charter. Define
the new class/floor and total denominator **before authoring any case**.
The owner must explicitly approve those numeric additions; **no count is
assumed by this draft**.

**Normative independent attribution oracle:** For every trusted record,
the scorer derives expected non-numeric attribution independently from
the decision fixture and ADR-034 §7c, not by copying the hook's reported
`violations`. Missing, empty or non-string `rule_id` is **unattributed**
even when a recognized `rule_type` is present. No `rule_type`-only
fallback may earn a G6 PASS. Inconsistent/untrusted payloads cannot earn
attribution. The scorer must check exact expected identities, absence
of extras/duplicates, and G6's existing applied-numeric-rule set,
per-rule relevance, event relevance and completeness in the inherited
order. `violations` alone never supports numeric relevance.

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

**Not established:** System-wide absence of exports, coverage of shared
or mounted locations, exact permissions and process identities of future
author, sealer and scorer, independently audited separation of author
and scorer when both use the same Windows account, and host configurations
if scoring moves machines. A Standard account is not itself a blind-corpus
confidentiality boundary between separate sessions of that same account.

**Blocking before sealing (#693 §9.5):** Pin the exact host, identities and
working roots of actual author/sealer/scorer. Have a verification actor
separate from the scoring and authoring roles confirm, using synthetic
ciphertext **within each actual agent context**, that owner decryption is
impossible; verify owner-only decrypt outside the agent, backup/export
reachability, elevation and session boundary, then record the owner's
explicit decision. Design and test file-level read restrictions or
separate OS identities so the scorer cannot read author plaintext or
labels before unblind. **If independence or custody remains unverified,
do not seal or score.**

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

- **R3-P1:** Approve exact new D3 class definitions, their concealed floors,
  and total denominator, preserving R2's 120 floor.
- **R3-P2:** Approve role eligibility, independent author/scorer identities,
  and read-isolated execution directories or separate OS identities.
- **R3-P3:** Record independently verified #693 §9.5 custody gate closure
  for *actual* agent execution contexts on all relevant machines.
- **R3-P4:** Verify baseline/host pin policy, exact per-gate coverage of
  the D3 attribution cases, and scoring harness authoring restrictions.

**Nothing authorized by this draft:** corpus authoring, sealing,
unblinding, implementation changes, harness construction, reinterpreting
R1/R2, or any PASS / live enforcement / production claim. G2-1 remains
**FAIL**.

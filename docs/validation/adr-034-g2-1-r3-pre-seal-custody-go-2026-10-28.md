# ADR-034 G2-1 R3: owner pre-seal custody GO (metadata-only)

**Date:** 2026-10-28  
**Decision:** **GO FOR SEALING ONLY**, explicitly approved by the human owner after the independent synthetic-only scoring-environment probe. **Not** a scorer handoff GO, an unblind GO, a validation PASS or blanket closure of R3-P3.  
**Authority:** R3 pre-registration §4.1–4.2, inherited #693 §9.5, owner-accepted and merged AT-SI amendment 1 (PR #701).  
**Scope:** One synthetic R3 corpus authored under the frozen protocol and its approved pre-unblind amendment. No hidden content, label, plaintext pathname, key material or private-key export is published in this record.

## 1. Roles and observed contexts

| Role | Observed / intended execution | Status |
|---|---|---|
| Author A / designated public-key sealer | Windows Standard user `MnemeAgent`; Claude Code 2.1.312.0; separate author configuration; author session `7bf4599d-e496-4829-941e-26ed50820b66`; repository frozen at `6d86358e66734556400d92f9cbe28194a9763ac5`, amendment at `e5b968ce313407f8caf55529b83e47e8b3eb781d` | Author reported structural completion; agent synthetic custody probe completed |
| Key custodian | Human owner under Standard account `MnemeOwner`; owner-only private key and decrypt/verify | Only owner may decrypt/verify the sealed R3 archive; prior synthetic owner-side recovery was reported |
| Designated scorer environment, **not scorer B** | Separate PowerShell/Git Bash process under `MnemeAgent` on the same machine; no Claude scorer session created | Owner-performed disposable synthetic probe completed |
| Future scorer B | **New**, independently configured Claude session under `MnemeAgent`, only after owner-approved sealed handoff and sanitization | Not started; role/session hash and effective execution context require rechecking at handoff |
| Existing administrator account | Excluded from author/sealer/scorer execution | Not an agent execution identity |

Separate Claude configurations and processes under the same Standard Windows account are **not an OS confidentiality boundary**. The pre-registration's same-account sequential handoff is conditional on verified removal/inaccessibility of author material **before B starts**.

## 2. Evidence reviewed before owner GO

**Author/sealer probe (agent-reported metadata):**
- Effective account `MnemeAgent`, medium integrity, non-administrator.
- Public owner encryption key present; zero listed GPG secret keys and empty local private-key directory.
- Repeated synthetic public-key encryption: success. Attempted synthetic decryption: exit 2, `No secret key`, no plaintext produced.
- Previously identified accessible export on a separate volume and its directory were confirmed absent on rechecks.
- Owner/admin profile storage inaccessible to the Standard account.
- Fourteen sensitive prior-validation and owner-private folders under a shared development root were restricted by the owner; a separate PowerShell account-level test produced `UnauthorizedAccessException` for all fourteen. The subsequent author/sealer session rechecked all fourteen as denied.
- A filename/permission-only review found no newly identified accessible secret-key export or earlier concealed material among the checked locations. No prior corpus bytes were opened by the author.

**Designated scorer-environment probe (owner-executed, separate shell from author A):**
- `whoami`: `arxwn\mnemeagent`.
- Git Bash GPG secret-key list: empty, exit 0. Owner public key: present, exit 0.
- Disposable synthetic ciphertext: encryption exit **0**, decryption exit **2**, `No secret key`.
- Scratch material for this **owner-run probe** was programmed for automatic removal.
- The future scorer B session **was not** started, and no concealed corpus was inspected in this probe.
- This is an observed owner-run shell probe plus document review, **not** an independent third-party forensic examination or a proof of every potential file-access path.

**Independent record review:** The responding assistant reviewed the author-reported probe and the owner's separate PowerShell outputs against §4.2's requirements. That is a review of reported evidence, not direct access to or independent execution on the host. The human owner is the authorization actor.

## 3. Residual limitations explicitly accepted by owner

- A previously readable, now-deleted key-looking export on another volume had an unknown exposure window. Absence now does not prove no historical copy or establish key rotation.
- Scans were bounded by depth and inspected filenames/permissions, not every possible file byte or forensic SSD remnant.
- Some drives/profiles were denied from the agent account and therefore could not be recursively enumerated. Separate remote, cloud, phone and removable storage was not exhaustively audited. Those limitations cannot be reinterpreted as positive evidence of absence.
- Future scorer B uses the same underlying Windows account as A; it must not start until the owner's separate handoff reviewer verifies that no hidden plaintext, author scratch, console output or author transcript remains readable.
- The author's session contains hidden case content in its transcript; the unsealed corpus and generator/salt/name map are presently readable to A by design and **must be protected during sealing and removed/inaccessible before B**. The public smoke set remains separate.
- R3 fixture compilation has not been executed against the implementation. Any compilation failure remains a **G8** failure during the blind validation. No pre-seal execution or feedback loop is authorized.
- The original R1/R2/G2-1 outcome remains **FAIL**.

The owner's explicit approval on 2026-10-28 was **YES** to a *pre-seal custody GO accepting these documented limitations and verified access restrictions*. This is **not** authorization to weaken other frozen validation gates. Discovery of an actual still-readable private key or prior concealed corpus, or any missing required pre-seal custody property, changes the decision to **NO-GO** until independently resolved.

## 4. Narrow execution authorization and stop points

**Authorized next:** Author A, as public-key sealer, may produce a deterministic, reproducible sealed archive and checksum manifest containing the already authored R3 corpus using **only the pinned owner public key**. Seal any private author-only provenance separately for owner custody. Log and report only aggregate counts, cryptographic digests, archive metadata and errors; do not publish case names, source bytes or oracle labels. Use pinned protocol and amendment. **Never decrypt under `MnemeAgent`.**

**Mandatory stops:**
1. Sealer stops after producing ciphertext and metadata. Do **not** remove the source corpus or transcripts until the owner securely receives and decrypt-verifies the sealed material outside `MnemeAgent`.
2. Owner decrypt-verifies, checks file manifest and retains owner-controlled archive/recovery material. If verification fails, **NO-GO**.
3. Owner conducts controlled cleanup of author plaintext, generation scratch, console histories and author transcript caches reachable by `MnemeAgent`, including archived superseded cases. Verify absence/inaccessibility from the proposed scorer context; no unrelated data deletion.
4. Separate handoff verifier reviews actual environment and retained evidence and the owner records a **new GO/NO-GO for scorer B**. **No scorer B session starts without that approval.**
5. Scorer B rechecks synthetic key/access isolation before owner-authorized unblinding. Scorer may only develop against normative contract and public smoke until harness and required synthetic malformed-rule-ID negatives are hash-pinned.

**State at this record:** author reported **150 concealed** across 14 classes plus **14 public smoke** (structural review clean); none sealed, scored or unblinded at the time of GO. All independent G1–G8 scoring gates remain pending. R3 is **not** PASS.

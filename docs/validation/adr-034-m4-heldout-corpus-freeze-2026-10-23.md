# ADR-034 M4 held-out corpus: freeze record (metadata only)

**Status:** **FROZEN** on 2026-10-23, by owner decision; the owner freezes it
by merging this record. The sealed M4 corpus
is the held-out corpus for the M4 independent validation of the corrected
ADR-034 G1 whole-file numeric audit, under the accepted
[M4 charter](../plans/2026-10-22-adr-034-m4-independent-validation-charter.md)
(#614, `d1159c89`; status #618, `a54eefda`) and the unchanged
[frozen criteria](../plans/2026-10-21-adr-034-pre-registered-evaluation-criteria.md)
(blob `7ca1f39e`).

This record contains **no** case bytes, case IDs, labels, expected outcomes,
rationales, contract text or answer-key content. The corpus stays encrypted
until scoring is separately authorized. It is a new corpus: sealed v1
([freeze record](adr-034-heldout-corpus-freeze-2026-10-22.md)) was not
accessed or reused, and G1 stays FAIL (149/155).

## Frozen commitment

| Item | Value |
|---|---|
| Scoring corpus, plaintext tar SHA-256 | `c6807c70a4b6c7e172f2a54ede62021a2bbebfc5d632ec9606486d15f5e7503f` (624,640 bytes; 691 entries: 196 regular files and 495 directories) |
| Inner `FILES.sha256` | covers 195 corpus files; its own SHA-256 is `aa1f578ddefbe2480bac0bd065c65fc3fcfec2b454da81c104d15fb883fc2177` |
| Scoring corpus, ciphertext SHA-256 | `1d745a522217abd9f5893e6b38922c3ea0290b4f2542ff731a265d7154764052` (63,490 bytes) |
| Manifest | `manifest.jsonl` SHA-256 `65dfc5ce8e42c1c307ade336790eea6cf444a250830fe8b73450d6cc159127ee`, 161 cases, in the charter §6 schema |
| W composition spec SHA-256 | `6abeabfe9ab314ab8801381e9c11c0fa46a4a3001e266ec2416ce8826050cfd9` (hashed 2026-10-23T01:24:37Z) |
| Sanitized ambiguity brief SHA-256 | `accb86f06c34a02176f13bcd2e8cedd3b5103e8c7d75eed99b8474b646fdf6be` |
| Owner rulings record SHA-256 | `7ecc345a8de2cfb9ad400aaf6735dfae316b73a10c55ae930c3918931044957d` (inside the sealed corpus) |
| Import preflight record SHA-256 | `1b567120fcc9e650d5e7006e1f9ba3c965726199e1778d43c0b0c3be8f5ae07b` (inside the sealed corpus) |
| Encrypted to | the owner's OpenPGP key, primary `88CE4C9F66A5F3CA7F1C0A484839E24F94E4F796`, encryption subkey `41AC9C0FAA3454FBA5491150C4370AB8829450C5`. The private key is held only by the owner |
| Build | GNU tar 1.35 `--format=gnu` (no pax headers), byte-wise sorted entries, fixed mtime, owner and group 0; rebuilt once, byte-identical. GnuPG 2.4.5 |
| Pinned contracts | ADR-034 blob `6f4ea66d`, criteria blob `7ca1f39e`, M4 charter at `a54eefda`; CPython 3.12.10 |

**Authoring provenance (ruling M4-AMB-11),** kept separately and never given
to the scorer:

| Item | Value |
|---|---|
| Provenance plaintext tar SHA-256 | `ecd32194c665e9b3ce46cc17554d4161324219179dae564ead915cd173a16456` (225,280 bytes; the generator scripts and their records, plus a per-file hash list) |
| Provenance ciphertext SHA-256 | `6b3c8436a50da3879e472940dacf26ba9c9d1f0d09df6346f4e7ed4cf017d710` (38,344 bytes), encrypted to the same owner key |

## Case counts (all charter §8 choices and criteria floors met)

| Stratum | Count | Breakdown |
|---|---|---|
| A, scored | 48 | S1/S2/S3/S4/S5 = 9/9/10/10/10. A1 4, A2 6 (2 multi-call), A3 5, A4 5, A5 5, A6 10, A7 3, A8 10 |
| A9, applicability only | 5 | 1 per shape |
| U, unsupported | 25 | 5 per shape: U1 2, U2 1, U3 1, U4 1 |
| N1, parse failure | 3 | |
| N2a, `--input` without `--target-path` | 8 | 2 at each location L1, L2, L3, L4 |
| N2b, `--input` with an APPLIED `--target-path` | 4 | |
| W, representative workload | 50 | 10 per shape, each 7 within and 3 above `max` |
| R, published numeric-semantics vectors (public, not blind evidence) | 18 | |
| **Total** | **161** | 143 concealed |

**N2 content:** each criteria §2.5 kind (prompt text, code fragment,
introduced-delta text, stdin-style text) appears 3 times. 7 of the 12 N2
cases parse as Python and contain only compliant values (charter minimum 6).

The sealed tar carries directory entries so that the two N2a L4 case
directories, which are policy roots with no files of their own, exist after
extraction.

## Owner rulings (2026-10-22 local time, UTC-5; recorded about 02:05Z on 2026-10-23; no ADR-034 amendment)

The sanitized brief has 11 entries (2 medium, 9 low). An independent
architecture review accepted 10 preferred readings and modified 1 custody
decision. The owner accepted all 11. No case was relabelled.

| AMB | Ruling |
|---|---|
| M4-01 | The ADR-034 structured directive sits directly under `## Constraints` in a properly formed ADR with YAML front matter; no fenced wrapper. Importability was confirmed by the preflight below |
| M4-02 | N2a L4 (outside the policy root) expects `MATCHER_UNEVALUATED` / `INCOMPLETE_SOURCE_INPUT`, not an operational path rejection. Its applicability, normally `UNKNOWN`, is recorded and not scored; the manifest may give `null` for it. The harness must preserve the actual trace and never normalize `UNKNOWN` |
| M4-03 | With memory at `<case>/.mneme/project_memory.json`, the ADR-020 policy root is `<case>` |
| M4-04 | Manifest `path` and `contract` may be relative to the corpus root, and `target_path` relative to the case's policy root. The harness resolves them consistently before invoking the CLI |
| M4-05 | The N2b `--target-path` is a caller-declared path. It need not exist and does not prove source identity |
| M4-06 | Cases may share a shape contract directory, each with its own imported memory. Set R keeps its independently defined contracts |
| M4-07 | Strata are A, U, N, W and R. A9, N1 and N2 are categories within them |
| M4-08 | Extra `unknown_sources` metadata may be kept on unevaluated cases. Outside A7 only the primary reason is scored; for A7 the expected unknown sources must also match |
| M4-09 | An unparseable complete file is `MATCHER_UNEVALUATED` / `PARSE_FAILURE`, even if its text resembles an exceeding value |
| M4-10 | An attribute value at an existing declared source is `UNRECOGNIZED_FORM`. An attribute-only call with no direct bare-name call is `SOURCE_NOT_FOUND`, absent a higher-priority cause |
| M4-11 | Custody modified: the authoring scripts are kept as a separately encrypted, owner-only provenance archive, excluded from the scoring corpus and not deleted |

The 17 confirmed interpretations from the v1 freeze record (AMB-01..17)
remained binding on M4 labels (charter §7).

**Harness consequence (charter §6, for the harness PR):** each case's memory
is created with `mneme init --path <case>/.mneme/project_memory.json` and then
populated with `mneme adr import <contract_dir> --memory <same> --apply`. This
is setup, not a scoring rule. An import failure is an operational failure.

## Pre-freeze conditions and evidence

- **Import-only preflight (condition 1):** the author ran `mneme init --path`
  and `mneme adr import --apply` on all 23 contract directories (5 shapes and
  18 set R contracts), with CPython 3.12.10 and `mneme/` tree
  `002fdddb254267d42a3810cfea669d75700372f2`. **23 of 23 imported, with no
  contract fixes.** `mneme check` was never run, and no case file was passed
  to `mneme`.
- **Provenance archive (condition 2):** the owner decrypted the provenance
  ciphertext on 2026-10-23 and its SHA-256 matched
  `ecd32194…a16456`.
- **Seal verification:** the owner decrypted the scoring ciphertext on
  2026-10-23 and its SHA-256 matched `c6807c70…7503f`. Both ciphertexts'
  SHA-256 values were checked against the seal records.
- **Plaintext deletion:** after both verifications, the owner overwrote and
  deleted the corpus folder, `_authoring/`, both plaintext tars and two
  temporary file lists, using Git's `shred -u -z`. On an SSD this is
  best-effort only and erasure is not provable.

### Owner-accepted procedural variances V-1 and V-2

The process above departed from the accepted M4 charter in two places. These
are **procedural variances that the owner accepted on 2026-10-23**. They are
not reinterpretations: charter §7 and §8 stay as written and binding. Neither
variance changes any scoring gate, corpus label or implementation behavior.

**V-1: owner decryption before the pre-scoring record (charter §7).**
Charter §7 says the owner "decrypts only after the pre-scoring record is
merged", and it makes no exception for verification. The owner decrypted both
archives before any harness or pre-scoring record existed. The owner
confirmed:

- each decryption was one command: decrypt to a temporary file, print its
  SHA-256, then delete that file;
- nothing was extracted or opened, and no case content was inspected;
- no plaintext was given to any scorer, implementer or harness author. None
  of those roles had a session at the time.

**Disclosed exposure window.** The plaintext corpus existed on the owner's
machine, outside the repository, from authoring (01:24Z) until the owner's
shred on 2026-10-23. There is no evidence that any other session read it, but
that cannot be proved.

**V-2: incomplete owner integrity verification (charter §8).** The owner
verified the ciphertext and plaintext-tar hashes only. Two §8 checks were
**not** performed before this freeze:

- all 195 inner files against `FILES.sha256`;
- the W-spec bytes against the frozen W-spec hash.

The author generated `FILES.sha256` from the files at sealing and confirmed
the W spec still matched its hash at the provenance step. The owner-verified
plaintext-tar hash matches the author's sealed tar, so the inner bytes are
those the author sealed. These two checks were not run now because that would
need another decryption.

**What stays binding:**

1. **Scorer access is unchanged.** The §7 and §9 restrictions still govern
   decryption for scoring. The scorer receives the corpus only after the
   harness and pre-scoring record are merged, and only the owner decrypts.
2. **The two checks are outstanding and mandatory.** Before the first scoring
   invocation, `sha256sum -c FILES.sha256` must report 195 OK and the W spec
   must match `6abeabfe…cfd9`. Any mismatch is an operational failure that
   invalidates the run (criteria §3).
3. **Any M4 validation claim is conditional** on both checks passing.
4. **The M4 results record must disclose V-1 and V-2.**

## Isolation and chronology

**Author:** a new session (Claude Opus 5.5 in Claude Code), not the v1
author, the G1 orchestrator, the G1 scorer, the #607 or #613 implementers, or
the M4 orchestrator. With `C:\dev\mneme` at `a54eefda`, it read only:

1. the M4 charter;
2. ADR-034;
3. the frozen criteria;
4. G1 charter §3–§6;
5. the v1 freeze record, for AMB-01..17 and the custody method;

plus the owner's public key, for encryption.

It accessed nothing under `mneme/` or `tests/`, no #607 or #613 PR bodies,
diffs or history, nothing in the sealed v1 folder, not the G1 results record,
and no other session or transcript. It used the CLI only for the authorized
preflight. It made cases through generator scripts with scripted checks of
counts, quotas, parse status, values and line numbers; those scripts are in
the provenance archive.

**Incidents, disclosed:**

- **Stale checkout.** The charter was first missing because the checkout was
  at `a50def29`. The author read only git ref files and file names to
  diagnose this; the orchestrator fast-forwarded the checkout before any
  document was read.
- **One git command,** `git rev-parse HEAD:mneme`, was run at preflight as
  instructed, to verify the pinned tree.
- **Deletion** was performed by the owner, not the author.
- **Two temporary file lists** of corpus paths existed during sealing and
  were shredded with the rest.

**Chronology (UTC, 2026-10-23,** from file modification times on the author's
machine; procedural evidence, not independent timestamps):

| Event | Time |
|---|---|
| W spec written (the first file in the corpus folder), then hashed | 01:24:33Z, 01:24:37Z |
| First non-W case written | 01:30:18Z |
| Latest W-case file modification time, as reported by the author as "all W cases written" | 01:32:32Z |
| Manifest finalized; brief hashed | about 01:33–01:55Z (not timestamped) |
| Owner rulings recorded; preflight | about 02:05–02:10Z (not timestamped) |
| Provenance archive built and encrypted | 02:12:36Z, 02:12:56Z |
| Scoring corpus sealed | 14:46:40Z (ciphertext) |

Every case file was written after the W spec was hashed, and the spec was
not edited after hashing; it still matched its hash at the last check.

## Accepted evidence and its limits

- The counts, isolation statement, preflight result and chronology are the
  **author's records,** not an independent audit of the 161 cases.
- The ambiguity review covered the sanitized brief only. The owner shared that
  brief with an external AI reviewer, which accessed no manifest, case or
  script.
- The M4 orchestrating session saw no case content. It forwarded the brief to
  the owner without reading it and handled only hashes and metadata.
- The author and the #607/#613 implementers share a model family. Charter
  §11 discloses that errors may be correlated.

## Confidentiality conditions (binding until scoring)

- The scorer and any implementer must have **no access** to the corpus-author
  session or its transcript, which contains the plaintext, or to the
  provenance archive.
- The corpus-author session is permanently barred from scoring and
  implementation.
- The scorer receives the scoring ciphertext only after the harness and the
  pre-scoring record are merged. Only the owner decrypts (charter §9).

## Not authorized by this freeze

- Harness implementation, the pre-scoring record, decryption or scoring.
- Any implementation, test, schema or CLI change.
- Any amendment to ADR-034, the frozen criteria, the G1 or M4 charters, the v1
  freeze record or the G1 results record.
- Any enforcement or production claim.

The next milestone is the public M4 scoring harness PR (charter §6), written
by a new scorer session under its own authorization.

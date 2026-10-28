# ADR-034 G2-1 R3: erratum to live-host record #708 source-byte attestation

**Date:** 2026-10-28  
**Status:** PROPOSED ERRATUM, pending independent review and owner acceptance.  
**Scope:** Correct the interpretation of a single installed-source byte-identity statement in the separately merged R3 §6.1 live-host characterization. No implementation, corpus, scoring harness, scoring rules or historical outcome changes.

## 1. Record and precise claim affected

Original record: [ADR-034 G2-1 R3 §6.1 live host characterization](adr-034-g2-1-r3-live-host-2026-10-28.md), merged via PR #708 at squash commit `2cab939077f9f413ba3b33b41ce9249bf54cd3ce`. The originally reviewed evidence commit is `7c16cb8f8ce4b97c54d3613fdc8260b65d9ec6cf`.

The disputed **§2 Build and environment** table row says:

> Installed source check | 111 `.py` files under installed `mneme/` byte-identical to `git archive 1b0957af mneme`; 0 mismatches.

That wording claims **raw byte identity**. It must not be cited as independently verified raw byte equality for the frozen implementation wheel or for the final R3 scoring installation.

## 2. Contradictory evidence and its verification boundary

An independent reviewer of the PR #707 pre-scoring draft reports the following **read-only verification** on the Windows host, performed without rebuilding, accessing sealed R3 material, unblinding or scoring:

| Evidence item | Reviewer-reported observation |
|---|---|
| Frozen R3 implementation wheel | `mneme_hq-0.10.0-py3-none-any.whl`, SHA-256 `f2ed395a6517006971f49baf169b957c10d0dfff4784ad36b3bb53eb9c024289`, size 557,421 bytes |
| Wheel source entries | 111 Python files under `mneme/`: 107 contain CRLF; four have no line breaks |
| Committed implementation | Commit `1b0957af01df3ad036b12698663e167ae413885e`; source Git blobs use LF |
| `git archive 1b0957af` | Reviewer reports LF output with both `core.autocrlf=true` and `core.autocrlf=false`; no repository `.gitattributes` |
| Raw wheel-payload versus archive-byte comparison | On the reported evidence, 107 entries differ by CRLF/LF bytes; four are equal |
| Source-content equivalence after EOL normalization | No substantive differences reported for the 111 corresponding source files |

**Conclusion limited to the compared artifacts:** the frozen wheel payload and LF Git archive cannot simultaneously be byte-identical across all 111 Python entries. The raw identity assertion in #708 §2 is therefore **not substantiated and conflicts with the reviewer's comparison**. Equality after CRLF-to-LF normalization is a different, weaker property.

**Not established:** whether the original #708 author normalized bytes in its comparison, made a mistaken statement, or measured a different extracted/installed artifact; nor have the raw installed `site-packages` bytes from the #708 venv or the final scorer B venv been independently reproduced for this erratum. Do not silently assume an explanation or claim independently verified installed-byte identity. The original reviewer's earlier approval of the raw identity statement was explicitly retracted after the wheel/archive check.

The reported observations above come from a separate Claude reviewer report provided to the owner on 2026-10-28. This GitHub erratum **does not itself reproduce the Windows wheel/archive inspection**. The independent reviewer of this erratum should verify the full wheel digest and raw file comparison against pinned Git blobs, and distinguish wheel contents from actual installed files.

## 3. Corrected claim and required future verification

**Superseding interpretation of #708 §2 installed-source row:**

> The frozen R3 implementation wheel is pinned by SHA-256 `f2ed395a6517006971f49baf169b957c10d0dfff4784ad36b3bb53eb9c024289`. The independent review reports 111 corresponding Python sources, with 107 CRLF/LF-only differences between raw wheel entries and the LF Git archive, and four raw-byte matches. **Source content is reported equivalent after explicit EOL normalization; 111/111 raw byte identity with the archive is not supported.** The #708 installed-file byte inventory and the scorer B final environment require separate independent checks.

For the actual R3 pre-scoring completion record (currently **DRAFT / NO-GO**, PR #707), preserve separate hashes and evidence for: pinned Git blobs/tree, wheel archive and its `RECORD`, raw installed source files, dependency freeze, the final LF scoring checkout and the exact host invocation. Explicitly state which comparison is **raw** and which is **normalized**. The frozen R3 pre-registration §2 111-match figure was **owner-reported candidate metadata**, not a substitute for the independently verified final scoring-source attestation required by §6.1.

## 4. No change to live-host evidence, status or authority

This erratum corrects **only the §2 source-byte claim**. It does **not** claim any new execution, validate the ten raw runs independently, revise their recorded exits/host observations, approve enforcement, change the R3 candidate wheel, modify the frozen harness or corpus, or retroactively change earlier blind results.

The #708 characterization remains a **separate recorded host-repin observation**, subject to its documented scope and limitations. No claim is made that a source-byte correction itself proves or disproves the recorded behavioral outcomes.

**R3 stays SEALED. PR #707 stays DRAFT / NO-GO. G2-1 remains FAIL.** No concealed scoring or unblinding is authorized. Owner and independent reviewer must accept this erratum before relying on the corrected source-byte description in a completed pre-scoring record.

## 5. Review criteria

Reviewer must confirm the quoted original row at the merged #708 blob; the frozen R3 wheel and implementation Git identities; a read-only raw byte comparison or a clearly labeled inability to reproduce it; the distinction between wheel payload, installed `site-packages` and Git archive; and that no new assertion was made about the ten host-run outcomes or scoring authorization.

**Authoring:** Agent-drafted metadata-only correction; human owner `@TheoV823`. The correction is provisional until independent review and owner disposition.

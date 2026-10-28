# ADR-034 G2-1 R3: pre-unblind interpretation acceptance record

**Date:** 2026-10-28  
**Owner decision:** Accepted in project conversation after review of the
frozen R1/R2/R3 preregistrations and ADR-034.  
**Status:** Interpretation record for PR #705 review. No corpus unblind, score,
merge, or validation PASS is authorized by this record.

## Scope and precedence

This is an interpretation of **already frozen** requirements. It is not an
amendment to the class floors, original gates, declared noncoverage, pinned
implementation, corpus, or labels. If the changes to the scorer disagree with
an accepted ADR or a previously merged preregistration, the accepted source
prevails. Scorer B must verify the corrections on public/synthetic inputs
before the harness can be pinned.

1. **MR rows 1 and 2, ADR-034 §7b.** Count only strict numeric refusals
   attributable to violated rule A: mode `strict`, disposition `refused`,
   cause `numeric_violation`, per-rule A relevance `true`, event relevance
   `true`. Warn or proceeded examples with otherwise identical numeric
   statuses do not satisfy the row. Row 3 requires a clean, proceeded,
   relevant event with all applied numeric rules decided and relevant. The
   two-case *native row-4 analogue* remains the literal-caused strict refusal
   with no attributable numeric relevance, as already frozen in R2 §4.3.
2. **R1 §4 byte-contract variety and Amendment 1 §A1.2.** Count LF, CRLF,
   lone CR, non-ASCII and empty **across V/C/L collectively**, at least two
   eligible cases per feature, **not two per class**. An empty Write is a
   legacy skip and cannot count as routed V/C. A lone surrogate is explicitly
   an L legacy subtype but is not UTF-8 encodable, so cannot satisfy the
   separate non-ASCII *byte* variety requirement.
3. **AT material distinctness, R3 §3 and accepted AT-SI amendment §2.**
   Merely renaming fixture files or changing front-matter ADR IDs cannot
   establish materially different scenarios. The automated guard compares
   canonical typed-rule semantics (rule type, value and selector scope) rather
   than paths or IDs alone; AT-SI also requires different independently
   derived literal identities **and** different include scopes, and AT-SX
   remains a distinct exclude-selector mechanism. Semantic fingerprints
   provide a conservative structural witness, **not proof that two apparently
   different path scopes are not cosmetic renames**. Distinct source, ADR
   and literal-rule identity of the public AT against concealed AT is not
   automatically established by the separately sealed public tar. The
   frozen author's qualitative structural declaration and owner limitation
   must be reviewed before any final completeness assertion. No post-unblind
   corpus replacement or label correction is permitted.
4. **L fixture evidence.** Derive subtype eligibility from the *declared*
   fixture and first-pass pre-mutation snapshot; never inspect a mutable
   worktree after both scoring passes. Link target existence, symlink
   components and missing parents are inferred from the declared
   materialization graph. Native G5 execution still determines whether
   legacy parity succeeds. If the fixture cannot establish a subtype,
   do not award it by guess.
5. **SC lexical-shape inventory, R2 §4.2.** The three numeric SC minima
   remain recognized violation, recognized clean and ambiguous binding (two
   each); the text also names class/method, parameter/local/comprehension/
   nested, enclosing scope, global/nonlocal, indirect mutation and plain
   string-data scenarios. These named families need independent qualitative
   verification, but no new *per-family numeric minimum* is invented.
   The corpus-floor counters do **not** independently prove every named
   lexical family. Record that limitation, and require an explicit
   structural-coverage determination before claiming complete R3 coverage.
6. **Mneme provenance, R3 §2.** The expected Mneme package version is
   the independently frozen **0.10.0**, not the tested installed package's
   own `mneme.__version__`. A mismatch in the installed version is a
   case-level G8 operational failure; a mismatch in the reported evidence
   version is a G6 provenance failure. Independent wheel hash, installed-file
   inventory, dependency freeze, host executable SHA-256 and pre-scoring
   completion record are still required. Package version equality alone is
   not a complete artifact attestation.

## Structural determination protocol to pin before unblind

The future **R3 pre-scoring completion record** must reproduce this procedure
and these exact pending identifiers **before** any owner-authorized unblind.
No such completed R3 pin record is established by this interpretation
document or by the harness review.

| Pending identifier | Required independent determination |
|---|---|
| `SC_lexical_families` | Examine the frozen SC sources and independently assess the named R2 §4.2 lexical families (class-body/method, parameter/local/comprehension/nested binding, enclosing scope, global/nonlocal, indirect namespace mutation, plain string data), without inventing new per-family numeric floors |
| `AT_material_distinctness` | Check the concealed AT pairs for meaningful semantic differences beyond ID and path renaming, including AT-SI distinct literal identities and include scopes, and AT-SX's exclude-selector mechanism |
| `public_vs_concealed_AT` | Check the public AT against concealed AT for distinct proposed source, ADR and literal-rule identity under frozen R3 §3 |

Before unblind, the completion record must state all three as **PENDING**,
name the independent reviewer and authority, and fix the evidence method.
The reviewer performs these determinations only **after the owner's
authorized unblind** and records `present`, `missing` or `undetermined`,
with opaque case identifiers and non-disclosing rationale, in the
metadata-only results/closure record. The qualitative review must not
alter hidden cases, frozen expectations, numeric gates or the declared
noncoverage. Missing or undetermined required coverage prevents a
**complete R3 PASS claim**, regardless of the gate verdict.

A published results record must quote **both** the raw
`decision.verdict` and `structural_review` (including
`final_claim_ready` and each pending determination). A consumer reading
`decision.verdict` alone is not receiving a complete validation outcome.
Neither a reviewer nor a results publisher may turn a passing gate verdict
into a final PASS while the structural review is unresolved. This procedure
does not introduce a new scoring verdict or change G1-G8.

## Review and scoring boundary

Only public/synthetic tests may be used to review these implementations.
Scorer B is to review the whole corrected harness including false-PASS and
false-FAIL risks, then provide exact-head tests. The main-only suite,
owner-controlled pre-scoring completion record, live-host characterization
and custody checks remain independent closure gates. R1, R2 and original G1
results remain FAIL, G2-1 remains FAIL, and **R3 has not been unblinded**.

A structural/qualitative limitation is not retrospectively resolved by a
high numeric score. If any frozen requirement cannot be evidenced at scoring,
record the limitation or failure under the frozen policy; do not amend
the corpus or silently weaken the requirement.

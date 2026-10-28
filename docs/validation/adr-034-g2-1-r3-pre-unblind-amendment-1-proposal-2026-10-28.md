# ADR-034 G2-1 R3: pre-unblind amendment 1 (AT-SN -> AT-SI)

**Date:** 2026-10-28  
**Status:** OWNER-ACCEPTED 2026-10-28, pending PR review and merge. The original frozen R3 protocol remains operative until the amendment merges.  
**Parent freeze:** [R3 pre-registration](adr-034-g2-1-r3-preregistration-draft-2026-10-28.md), PR #699, merge `6d86358e66734556400d92f9cbe28194a9763ac5`.  
**Owner ruling:** AMB-R3-01 **ACCEPT**. Replace AT-SN with AT-SI at the same 2-case floor, retain distinct AT-SX. This owner approval is not custody or scoring authorization. Reported during independent corpus authoring. Only sanitized author metadata was reviewed; no concealed case, label or author scratch was inspected.

## 1. Conflict with accepted architecture

The frozen R3 §3 requires **AT-SN**, two concealed strict cases with
a `FORBID_LITERAL` violation and an active numeric rule "present in
memory but with no numeric applicability record for this target."

That state is not supported for a loaded, evaluated numeric typed rule.
[ADR-017](../adr/ADR-017-enforcement-scope-vs-retrieval-scope.md)
separates ranking from typed enforcement.
[ADR-019](../adr/ADR-019-typed-literal-rule-contract.md)
makes typed literals globally considered.
[ADR-020](../adr/ADR-020-explicit-path-applicability-for-typed-rules.md)
§7 requires machine-readable applicability with `APPLIED`,
`EXCLUDED` or `UNKNOWN`. A rule missing a matching path scope is
**EXCLUDED**, not silently absent. Current Mneme rule evaluation also
emits an applicability entry for every evaluated typed rule.

Do **not** simulate a zero-trace numeric rule by inventing inactive
statuses, an unloaded alternate memory, precedence filtering, a
modified checker payload or implementation-dependent selection.
None is a reviewed fixture mechanism for the frozen AT-SN label.
The author correctly withheld AT-SN rather than guessing.

## 2. Exact replacement requested

**Owner-accepted replacement, effective upon merge: AT-SN (floor 2) becomes AT-SI (floor 2):
"numeric present, scope include-miss."**

For both new concealed AT-SI cases:

1. A verified-absent new `.py` `Write`, inside the policy root, with
   an existing parent, under **open** availability and **strict** mode.
2. The effective fixture memory contains at least one valid, active
   `FORBID_NUMERIC_ABOVE` typed rule whose **non-empty `include_paths`**
   does **not** match the governed target. Its `exclude_paths` must
   be empty, so the exclusion is specifically an *include miss*,
   not an explicit exclude-selector match.
3. The trusted checker must report that numeric rule's **`EXCLUDED`
   applicability trace**, with the ADR-020 reason
   `no include selector matched`. No numeric rule is `APPLIED`.
4. At least one independently applicable `FORBID_LITERAL` rule
   matches the proposed source, producing the **sole refusal cause**.
5. Independently label: checker JSON `subject.input_kind =
   unverified_input` (the numeric trace exists but no numeric rule
   applies); hook evidence `checker.subject = null`, hook
   `rules = []`, exact literal `(rule_id, rule_type)` identities
   in hook `violations`, hook cause `other_rule` mapped to the
   labelled literal attribution, exit 2, refused before mutation,
   target absent, empty APPLIED numeric rule-ID set, empty per-rule
   numeric relevance, event relevance `false` and complete
   evaluation when otherwise trusted.
6. Create **two materially different** concealed cases with different
   independently derived literal identities and path scopes, not
   renames or mutations of older hidden cases. The author must not
   run Mneme or infer oracle values from implementation outputs.

**AT-SX stays separate:** its EXCLUDED numeric trace must be caused by
a **matching `exclude_paths` selector**, whose precedence wins
after its `include_paths` matches. This makes AT-SI and AT-SX
distinct ADR-020 path-exclusion mechanisms. The author must
structurally verify this distinction; if existing AT-SX cases
do not meet it, report the mismatch without silently rewriting
those cases or weakening AT-SX.

The original R3 §3 table row for `AT-SN` and the checker-subject
table's `AT-SN` reference are superseded by this section **only
when this owner-accepted amendment is merged**. For `AT-SI`, the
expected checker subject belongs in the `unverified_input` row
alongside AT-SX; the hook's `checker.subject` remains null.

## 3. Frozen properties not changed

- Inherited 13 classes and original 120 concealed minimum remain.
- AT remains **8** concealed minimum across four two-case sub-classes:
  **AT-S0 2, AT-SI 2, AT-SX 2, AT-W0 2**.
- R3 floor remains **128 concealed** across 14 classes; public-smoke
  floor, 10% ceiling and class distribution are unchanged.
- G1–G8 gates, false-block/unsafe-pass zero tolerance, exact `rule_id`
  attribution, baseline/host/wheel pins and no-retrospective-PASS rules
  remain frozen.
- The already authored, unsealed concealed corpus is not inspected,
  scored, disclosed, re-used from R1/R2 or approved by this document.
- A compile failure remains **G8 failure** at the independent
  validation gate. This amendment does not authorize a
  pre-seal compiler run or a case-by-case implementation feedback
  loop to revise hidden expectations.
- **R3-P3 / #693 §9.5 remains OPEN**. Nothing may be sealed before
  independent custody verification of both designated environments
  and the owner's explicit GO. No scorer B may start before the
  owner-approved sealed-corpus handoff.

## 4. Decision and execution boundary

**Owner ruling: ACCEPT, 2026-10-28.** AT-SN is replaced by AT-SI
with two include-miss cases, while AT-SX retains two exclude-match
cases. This approval is effective as a protocol amendment **only after
review and merge**, and before author A proceeds with the replacement
cases. No separate Windows account or implementation change is requested.

After merge, send author A **only this normative
amendment and the owner ruling**, not implementation source,
earlier hidden corpora, scorer diagnostics or research transcripts.
The author will add/reconcile the **two** cases and perform a
new author-only structural review. A positive author-only review
is not an R3 PASS, a custody GO or authorization to seal.

**Current recorded state:** author reports 148 concealed, 14 public
smoke, AT-S0 2 / AT-SX 2 / AT-W0 2 / AT-SN 0; structurally
INCOMPLETE at AT 6/8. All source case bytes and labels remain
inaccessible to the proposed PR. R1/R2/G2-1 remain **FAIL**.

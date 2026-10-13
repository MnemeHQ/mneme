# DG1F-C1 — Applicability-only CLI enforcement charter (proposed)

**Status:** PROPOSED — architecture and threat-model review required. The trusted-context contract (§3) is now specified; the remaining review items are the C1a interface/output wording and the deployment boundary for any future operator-owned context source. **Not merged; no runtime implementation authorized.** The first increment is report-only (§2 C1a); actual exclusion (C1b) is deferred until its trusted context source is separately authorized.  
**Anchor:** `MnemeHQ/mneme` `main` at `c1816aa5541e86452fb1998356635fb818918373` (ADR-031 sequencing amendment #492).  
**Governs:** only the proposed *first* DG1F increment. Not DG1B2, the full DG1F convergence programme, or DG1G.

## 1. Governing authority and observed starting behavior

- Accepted [ADR-031](../adr/ADR-031-decision-governance-semantics.md) §4, §6–§8, §10–§11, as amended by #492, permits an **optional applicability-only DG1F increment before DG1B2**. It does **not** authorize a runtime-input change without a separate merged behavioral charter and the subsequent `[layer1-freeze]` amendment.
- [DG1F readiness assessment](2026-10-13-dg1f-runtime-convergence-readiness.md) in draft PR #491 provides the initial inventory; its *unresolved sequencing question* was settled by #492. PR #491 is neither superseded as evidence nor an authorization.
- DG1B1 (#487) merged canonical `required_labels`, explicit v1→v2 migration, and `resolve_effective(index, GovernanceContext)`; the pinned GSA-TTS ADR-0028 offline scenario demonstrates Windows matching and Linux nonmatching, but deliberately proves **existing runtime enforcement is unaffected**.
- In current `mneme/cli.py:_cmd_check`, `MemoryStore.load` projects every lifecycle-active decision, `DecisionRetriever.retrieve(query)` ranks the corpus, and `check_prompt` enforces rules. No label context is passed. `mneme/decision_projection.py` projects lifecycle-active records regardless of DG1B1 applicability. `mneme/enforcer.py` combines retrieval-gated *multi-term legacy* checks with corpus-wide typed literal rules (ADR-017); ADR-020 selects rule paths separately.
- Current CLI `--json` uses `mneme.check/v1` and the path-applicability `evaluation_complete` field. Hook and CI consumers may depend on that contract. This slice must not silently repurpose or change those semantics.

## 2. Candidate first increment — report-only (C1a); exclusion deferred (C1b)

The first consumer remains `mneme check`. It is split so that the part with no
trust problem can proceed while exclusion stays blocked on §3:

- **C1a — report-only applicability preview (proposed as the first increment).**
  An opt-in `mneme check` mode computes `resolve_effective(index,
  GovernanceContext(labels))` against a context supplied *for display only* and
  reports, per decision, whether it is effective or would be `not_applicable` —
  **without changing which decisions reach `check_prompt`**. Because it never
  removes a decision from enforcement, a caller-supplied (even agent-supplied)
  context cannot disable protection here. Output is additive and opt-in;
  `mneme.check/v1`, the enforced set, violations, exit codes, and hook behavior
  are unchanged by default.
- **C1b — enforcement exclusion (deferred).** Changing the enforced set using
  applicability requires a *trusted* context source. Per §3 that source must be
  the reviewed canonical authority, which this charter does not authorize. C1b
  therefore requires a separate authorization for the canonical context
  declaration (and then the `[layer1-freeze]` amendment) before any decision is
  excluded.

The proposed opt-in interface for C1a is a single repeatable
`--applicability-preview <label>` (naming subject to review). It is
**non-authoritative** and MUST NOT be named or documented as a security control.
`--governance-label` as an *enforcement* input and `--governance-context-complete`
are **withdrawn** from this charter: a completeness assertion on the command line
is not provenance (§3).

Do not add a second applicability resolver, re-run import precedence, change
canonical data, or infer labels from `context_scope`, retrieval scores, path
names, machine OS, LLM output, agent arguments, or Data Engine observations. Any
report must use the **same validated canonical snapshot** the compatibility
projection was made from; identity mismatch or unreconciled ambiguity is an
error, never a silently filtered result.

**Enforcement scope invariant (applies to C1b when it lands):** derive an
enforcement-only ordered full corpus of *effective* decisions using
authoritative canonical IDs before `check_prompt` computes its top-N tier.
Merely filtering the already selected top-N is forbidden: it could remove a
top-ranked nonapplicable decision without exposing the next relevant effective
decision. Preserve `DecisionRetriever` scoring, tie-order, and K; preserve
corpus-wide typed-rule checks for all effective decisions and unchanged ADR-020
path selection. Retrieval/context injection is not redefined as governance.

## 3. Trusted-context contract (resolved)

**Problem.** `resolve_effective` returns `not_applicable` when a decision's
`required_labels` are not all present in the supplied
`GovernanceContext.labels`; a consumer that acts on that result stops enforcing
the decision. Any label set the governed agent can supply — command-line flag,
environment variable, prompt or file content, hook/MCP input, or a wrapper it
controls — is an **assertion**, not provenance. Treating it as authoritative
lets the agent silently disable a protective decision.

**Resolution — one authoritative source, fail closed.**

1. **Only the reviewed canonical authority is authoritative.** Evaluation-
   context labels are declared in `.mneme/project_memory.json` under the
   Mneme-owned, review-gated writer discipline (ADR-030): a durable,
   diff-visible reviewed change. An untrusted agent cannot alter the context
   without a reviewable change, so the context carries the same trust level as
   the decisions it gates.
2. **Command-line and environment arguments are never authoritative.** `mneme
   check` must not read enforcement-gating labels from argv, env, hook/MCP
   input, prompt/content, retrieval, paths, or OS. A caller may at most select
   *which* reviewed context applies; it may never supply the label values for
   exclusion.
3. **Fail-closed, three-valued.**
   - **No context declaration:** enforce every lifecycle-active decision —
     byte-for-byte today's behavior. Empty labels are never read as evidence of
     nonapplicability.
   - **Valid declaration:** exclusions are allowed only from the declared
     labels; only a positively established, trusted absence excludes.
   - **Malformed, ambiguous, conflicting, or unreadable declaration:**
     operational error; enforce all; surface explicitly; never a silent PASS.
4. **No inference.** Labels are opaque project-local strings taken verbatim. No
   taxonomy, no `platform:`-prefix parsing, no mutual-exclusion inference, and
   no derivation from OS, paths, retrieval, agent input, or Data Engine
   observations.
5. **Completeness is reviewed, not asserted.** The declaration is the complete
   context for the project; a runtime completeness flag is not provenance and is
   rejected.
6. **Auditability.** Any result or trace records the context source identity
   (for example a digest of the declaration), the labels used, and per-decision
   applicability; every exclusion is explicit and reproducible.

**Governance integrity findings.** `dangling_supersedes` /
`supersession_lifecycle_conflict` are not policy violations or precedence
winners. Until a reviewer approves an explicit policy, such findings make
context evaluation **incomplete**, which fails closed (no exclusion) and is
reported — never a silent success.

**Resolved consequence.** Establishing the canonical context declaration is
itself a persisted-semantic change (a v2 declaration/feature) needing its own
authorization. Until then, exclusion is **not authorized**; only the report-only
increment in §2 (C1a) may proceed. The earlier "trusted invocation arguments"
proposal is withdrawn: trust is a property of the reviewed authority, not of the
invocation, and no in-process flag or wrapper assertion can establish it.

## 4. Explicit non-goals

No change to `DecisionRetriever` relevance/context output; `ConflictDetector`; `project_canonical_index`'s global compatibility semantics; `MemoryStore.load` authority rules; ADR-020 selectors; rule types, matcher or legacy rule-severity semantics; hooks, MCP, protection, Audit, readiness, or CI reference integration; persisted v2 schema or feature declarations; waiver representation or DG1B2 semantics; Data Engine; or frozen benchmark methodology. No `.mneme/project_memory.json` edits or silent v1→v2 migration.

This does **not** promise agent-proof enforcement, tool-agnostic identity, or organization-level label authority.

## 5. Required acceptance and adversarial evidence

Before any implementation merge, a separately authorized offline acceptance suite must demonstrate:

1. **Default parity:** no opt-in means the exact existing lifecycle-active decision set and rule/violation/exit behavior (v1, v2 without applicability, and section-less legacy memory).
2. **Explicit matching context:** on the pinned GSA-TTS Windows fixture, trusted `platform:windows` keeps the Windows-only decision and evaluates its authored typed rule.
3. **Explicit nonmatch:** trusted complete `platform:linux` excludes only the Windows-only decision; independent global decisions are still enforced.
4. **Missing/incomplete/untrusted context:** no silent PASS through dropped governance, including agent-controlled spoofed labels; negative test cases demonstrate the refusal path. Document the real trust boundary and its limits.
5. **Lifecycle ordering:** superseded, deprecated, and inactive decisions never regain authority via labels.
6. **Rank invariance:** high-ranked excluded decisions do not consume retrieval-gated enforcement slots; literal rules of effective decisions are never lost because of top-K, while guidance retrieval remains unchanged.
7. **Path independence:** decision labels gate decision authority first; ADR-020 applies separately to individual typed rules. Path UNKNOWN remains fail-safe under the pre-existing selector contract.
8. **Canonical/evidence identity:** effective decision IDs, `decision_version_id`, canonical `rule_id`, and current-run evaluation evidence are stable and replayable; no source-proposal or research candidate is promoted.
9. **Findings and malformed data:** ambiguous, corrupt, unsupported-feature, missing-identity, or inconsistent canonical state never produces an invented effective winner or silent success.
10. **Compatibility:** CLI strict/warn, human and JSON modes, hook-exposed `mneme.check/v1`, and existing regression/Layer 1 benchmark suites have pinned expected-versus-actual outcomes. No benchmark fixture or methodology changes.

11. **Report-only non-interference (C1a):** with and without the report-only preview, the enforced decision set, rule evaluation, violations, exit codes, human output, and `mneme.check/v1` are identical; the preview is additive/opt-in and never gates enforcement.

Items 2–4 (context-based matching, nonmatch, and refusal) apply to **C1b** and may only be implemented once the trusted context source in §3 is authorized. A reviewer must distinguish unit tests of `resolve_effective` (already done in DG1B1) from end-to-end runtime exclusion tests (not yet executed).

## 6. Approval and change sequence

1. **Review this revision.** §3 now specifies the trusted-context contract and
   §2 splits report-only (C1a) from exclusion (C1b). Remaining review items:
   the C1a interface/flag naming, its exact additive output mapping, and the
   deployment boundary for any future operator-owned context source. Approval
   of this draft is not implied by #492.
2. Merge this behavioral charter as a separate PR.
3. Open and merge the matching `[layer1-freeze]` amendment under the frozen
   document's Amendment Procedure, referencing the merged charter and its
   bounded first surface.
4. Implement and accept **C1a (report-only)** in its own PR with the §5 gates.
   Because C1a never removes a decision from enforcement, it cannot disable
   protection; this is the safe first increment.
5. **C1b (exclusion) is not authorized by this charter alone.** It requires a
   separately authorized canonical context declaration (§3, item 1) — a
   persisted-semantic change — plus a further charter/freeze update, before any
   decision is excluded.
6. DG1B2 remains independently evidence-gated; remaining DG1F surfaces and DG1G
   remain unimplemented.

**Merge status of this draft: HOLD until independently reviewed.**

# DG1F-C1 — Applicability-only CLI enforcement charter (proposed)

**Status:** PROPOSED — architecture and threat-model review required. §3 specifies the trusted-context contract, its two fail-closed conditions, and the C1b trust prerequisites; §2 and §5 specify the C1a report-only interface and separate its acceptance from the deferred C1b exclusion tests. Remaining review items are the C1a output wording and the C1b trust mechanism (explicitly not designed here). **Not merged; no runtime implementation authorized.** The first increment is report-only (§2 C1a); exclusion (C1b) is deferred.  
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
  GovernanceContext(labels))` against a caller-supplied preview context and
  reports, per decision, whether it is effective or would be `not_applicable` —
  **without changing which decisions reach `check_prompt`**. Because it never
  removes a decision from enforcement, even agent-supplied preview labels cannot
  disable protection. The enforced set, exit codes, stdout, the
  `mneme.check/v1` JSON payload, and hook behavior are unchanged whether or not
  the preview is requested.
- **C1b — enforcement exclusion (deferred).** Changing the enforced set using
  applicability requires a *trusted* context source. Per §3 that source must be
  the reviewed canonical authority, which this charter does not authorize. C1b
  therefore requires a separate authorization for the canonical context
  declaration (and then the `[layer1-freeze]` amendment) before any decision is
  excluded.

**C1a preview interface and output.** A single **opt-in, repeatable**
`--applicability-preview <label>` flag (naming subject to review) supplies the
preview context. It is **NON-AUTHORITATIVE** and MUST NOT be named or documented
as a security control. Preview output is informational and written to
**stderr**, clearly marked NON-AUTHORITATIVE; stdout and the `mneme.check/v1`
JSON payload are byte-unchanged. A preview evaluation failure prints
`PREVIEW UNAVAILABLE` on stderr and **never** changes the underlying enforcement
verdict or exit code — unless the ordinary enforcement path independently fails,
in which case the normal enforcement result stands. `--governance-label` as an
*enforcement* input and `--governance-context-complete` remain **withdrawn**: a
completeness assertion on the command line is not provenance (§3).

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

1. **The reviewed canonical authority is the intended source — but storage
   location is not trust.** Evaluation-context labels would be declared under
   the canonical decision authority, changed only through the Mneme-owned,
   review-gated writer discipline (ADR-030). Merely being stored under
   `.mneme/` does **not** make a value trusted: an unreviewed local edit, or a
   substituted file, would otherwise silently change the context. Any future
   exclusion (C1b) therefore additionally requires an **independently verifiable
   approved revision**, protection against **unreviewed substitution**, and
   **controlled context selection** — all deferred to C1b (see "C1b trust
   prerequisites" below) and not designed here.
2. **Command-line and environment arguments are never authoritative.** `mneme
   check` must not read enforcement-gating labels from argv, env, hook/MCP
   input, prompt/content, retrieval, paths, or OS. A caller may at most select
   *which* reviewed context applies; it may never supply the label values for
   exclusion.
3. **Fail-closed, with distinct handling for each failure condition.**
   - **No context declaration:** enforce every lifecycle-active decision —
     byte-for-byte today's behavior. Empty labels are never read as evidence of
     nonapplicability.
   - **Valid context declaration over valid canonical memory:** exclusions are
     allowed only from the declared labels; only a positively established,
     trusted absence excludes.
   - **Invalid, ambiguous, or conflicting context declaration, but otherwise
     valid canonical memory:** refuse context-based exclusions and preserve
     existing protective coverage (do not exclude); surface the condition;
     never a silent PASS. Decisions are retained, not dropped.
   - **Invalid or unreadable canonical memory:** the authoritative decision
     corpus could not be loaded, so there is **no trustworthy enforcement
     verdict at all**. Report an operational failure. Do **not** claim that all
     decisions were enforced — coverage is *unknown*, not *complete*.
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

**Blocking-seam caveat.** Some consumers currently **fail open** when they do
not receive a valid JSON verdict — for example a hook or CI step that treats a
missing or malformed verdict as non-blocking. A CLI invocation that reports an
operational failure is therefore **not** end-to-end fail-closed by itself. This
charter must not claim end-to-end fail-closed enforcement until the blocking
seam is validated: the consumer's treatment of a missing or invalid verdict must
be shown to block rather than pass. Where that seam concerns enforcement inputs
it remains subject to the `[layer1-freeze]` amendment; the validation is
required evidence (§5).

**Resolved consequence.** Establishing the canonical context declaration is
itself a persisted-semantic change (a v2 declaration/feature) needing its own
authorization. Until then, exclusion is **not authorized**; only the report-only
increment in §2 (C1a) may proceed. The earlier "trusted invocation arguments"
proposal is withdrawn: trust is a property of the reviewed authority, not of the
invocation, and no in-process flag or wrapper assertion can establish it.

**C1b trust prerequisites (deferred; not designed here).** Turning the reviewed
authority into a trusted enforcement input is itself unresolved and out of scope
for this charter. Before any exclusion (C1b) is authorized it must be
established, and separately reviewed, that a run (a) evaluated an
**independently verifiable approved revision** of the canonical memory it
actually used, (b) is protected against **unreviewed substitution** between
review and execution, and (c) performs **controlled context selection** so no
caller can choose an arbitrary context. This charter neither specifies nor
implements that mechanism.

## 4. Explicit non-goals

No change to `DecisionRetriever` relevance/context output; `ConflictDetector`; `project_canonical_index`'s global compatibility semantics; `MemoryStore.load` authority rules; ADR-020 selectors; rule types, matcher or legacy rule-severity semantics; hooks, MCP, protection, Audit, readiness, or CI reference integration; persisted v2 schema or feature declarations; waiver representation or DG1B2 semantics; Data Engine; or frozen benchmark methodology. No `.mneme/project_memory.json` edits or silent v1→v2 migration.

This does **not** promise agent-proof enforcement, tool-agnostic identity, or organization-level label authority.

## 5. Required acceptance and adversarial evidence

Acceptance is split with the increments. **C1a is report-only and does not
validate trusted enforcement context or actual exclusion**; the exclusion tests
are deferred with C1b.

### 5a. C1a — report-only acceptance (required before any C1a merge)

A separately authorized offline suite must demonstrate:

1. **Default parity:** with no preview flag, the exact existing lifecycle-active
   decision set and rule/violation/exit behavior (v1, v2 without applicability,
   and section-less legacy memory).
2. **Report-only non-interference:** with and without the preview, the enforced
   decision set, rule evaluation, violations, **stdout**, the `mneme.check/v1`
   JSON payload, exit codes, and hook behavior are identical; the preview is
   additive/opt-in and never gates enforcement.
3. **Preview output contract:** preview is opt-in and stderr-only, clearly
   marked NON-AUTHORITATIVE; a preview evaluation failure reports
   `PREVIEW UNAVAILABLE` on stderr **without** changing the underlying
   enforcement verdict or exit code, unless the ordinary enforcement path
   independently fails.
4. **Preview cannot disable protection:** agent-spoofed preview labels never
   remove a decision from enforcement (true by construction; pinned by a test).
5. **Compatibility:** CLI strict/warn, human and JSON modes, hook-exposed
   `mneme.check/v1`, and existing regression/Layer 1 benchmark suites have
   pinned expected-versus-actual outcomes. No benchmark fixture or methodology
   changes.

C1a explicitly does **not** establish a trusted enforcement context and does
**not** test actual exclusion.

### 5b. C1b — exclusion acceptance (deferred with C1b)

Required only if and when C1b is separately authorized (canonical context
declaration plus `[layer1-freeze]` amendment):

6. **Explicit matching context:** on the pinned GSA-TTS Windows fixture, trusted
   `platform:windows` keeps the Windows-only decision and evaluates its authored
   typed rule.
7. **Explicit nonmatch:** trusted complete `platform:linux` excludes only the
   Windows-only decision; independent global decisions are still enforced.
8. **Context failure conditions:** invalid/incomplete/untrusted context with
   otherwise valid canonical memory → no exclusion, protective coverage
   preserved; invalid or unreadable canonical memory → operational failure, and
   never a claim that all decisions were enforced.
9. **Lifecycle ordering:** superseded, deprecated, and inactive decisions never
   regain authority via labels.
10. **Rank invariance:** high-ranked excluded decisions do not consume
    retrieval-gated enforcement slots; literal rules of effective decisions are
    never lost because of top-K, while guidance retrieval remains unchanged.
11. **Path independence:** decision labels gate decision authority first;
    ADR-020 applies separately to individual typed rules. Path UNKNOWN remains
    fail-safe under the pre-existing selector contract.
12. **Canonical/evidence identity:** effective decision IDs,
    `decision_version_id`, canonical `rule_id`, and current-run evaluation
    evidence are stable and replayable; no source-proposal or research candidate
    is promoted.
13. **Findings and malformed data:** ambiguous, corrupt, unsupported-feature,
    missing-identity, or inconsistent canonical state never produces an invented
    effective winner or silent success.
14. **Blocking seam:** the consumer's handling of a missing or invalid verdict
    is shown to **block rather than fail open** before any end-to-end
    fail-closed claim.

A reviewer must distinguish unit tests of `resolve_effective` (already done in
DG1B1) from end-to-end runtime exclusion tests (not yet executed).

## 6. Approval and change sequence

1. **Review this revision.** §2 and §5a specify the C1a report-only interface
   and its acceptance; §3 specifies the trusted-context contract, the two
   fail-closed conditions, and the C1b trust prerequisites (deferred, not
   designed here); §5b holds the exclusion tests for C1b. Remaining review
   items: the C1a output wording and the C1b trust mechanism. Approval of this
   draft is not implied by #492.
2. Merge this behavioral charter as a separate PR.
3. Open and merge the matching `[layer1-freeze]` amendment under the frozen
   document's Amendment Procedure, referencing the merged charter and its
   bounded first surface.
4. Implement and accept **C1a (report-only)** in its own PR with the §5a gates.
   Because C1a never removes a decision from enforcement, it cannot disable
   protection; this is the safe first increment.
5. **C1b (exclusion) is not authorized by this charter alone.** It requires the
   C1b trust prerequisites (§3) — an independently verifiable approved
   revision, protection against unreviewed substitution, and controlled context
   selection — plus the persisted canonical context declaration and a further
   charter/freeze update, before any decision is excluded.
6. DG1B2 remains independently evidence-gated; remaining DG1F surfaces and DG1G
   remain unimplemented.

**Merge status of this draft: HOLD until independently reviewed.**

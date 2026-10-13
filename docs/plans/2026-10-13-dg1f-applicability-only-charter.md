# DG1F-C1 — Applicability-only CLI enforcement charter (proposed)

**Status:** PROPOSED — architecture and threat-model review required. **Not merged; no runtime implementation authorized.**  
**Anchor:** `MnemeHQ/mneme` `main` at `c1816aa5541e86452fb1998356635fb818918373` (ADR-031 sequencing amendment #492).  
**Governs:** only the proposed *first* DG1F increment. Not DG1B2, the full DG1F convergence programme, or DG1G.

## 1. Governing authority and observed starting behavior

- Accepted [ADR-031](../adr/ADR-031-decision-governance-semantics.md) §4, §6–§8, §10–§11, as amended by #492, permits an **optional applicability-only DG1F increment before DG1B2**. It does **not** authorize a runtime-input change without a separate merged behavioral charter and the subsequent `[layer1-freeze]` amendment.
- [DG1F readiness assessment](2026-10-13-dg1f-runtime-convergence-readiness.md) in draft PR #491 provides the initial inventory; its *unresolved sequencing question* was settled by #492. PR #491 is neither superseded as evidence nor an authorization.
- DG1B1 (#487) merged canonical `required_labels`, explicit v1→v2 migration, and `resolve_effective(index, GovernanceContext)`; the pinned GSA-TTS ADR-0028 offline scenario demonstrates Windows matching and Linux nonmatching, but deliberately proves **existing runtime enforcement is unaffected**.
- In current `mneme/cli.py:_cmd_check`, `MemoryStore.load` projects every lifecycle-active decision, `DecisionRetriever.retrieve(query)` ranks the corpus, and `check_prompt` enforces rules. No label context is passed. `mneme/decision_projection.py` projects lifecycle-active records regardless of DG1B1 applicability. `mneme/enforcer.py` combines retrieval-gated *multi-term legacy* checks with corpus-wide typed literal rules (ADR-017); ADR-020 selects rule paths separately.
- Current CLI `--json` uses `mneme.check/v1` and the path-applicability `evaluation_complete` field. Hook and CI consumers may depend on that contract. This slice must not silently repurpose or change those semantics.

## 2. Candidate first consumer and permitted change (for review)

**First and only consumer proposed:** `mneme check` invoked by a **trusted human-operated or separately controlled CI invocation**, not an untrusted coding-agent-controlled command. For opt-in invocations with a *reviewed complete label context*, use the existing canonical `resolve_effective` answer to select the decision set that reaches `check_prompt`. Keep the rest of the runtime untouched.

The proposed opt-in interface for architecture review is repeatable `--governance-label <opaque-label>` plus `--governance-context-complete`. **These flags do not exist today and are not approved merely by opening this draft.** Their naming and public-interface compatibility must be explicitly accepted when this charter is reviewed. Without explicit opt-in, preserve current `mneme check` behavior byte-for-byte where feasible.

Do not add a second applicability resolver, re-run import precedence, change canonical data, or infer labels from `context_scope`, retrieval scores, path names, machine OS, LLM output, agent arguments, or Data Engine observations. In-memory execution must use the **same validated canonical snapshot** from which the compatibility projection was made; any identity mismatch or unreconciled ambiguity is an error, not a silently filtered result.

**Enforcement scope invariant:** derive an enforcement-only ordered full corpus of *effective* decisions using authoritative canonical IDs before `check_prompt` computes its top-N tier. Merely filtering the already selected top-N is forbidden: it could incorrectly remove a top-ranked nonapplicable decision without exposing the next relevant effective decision. Preserve `DecisionRetriever` scoring, tie-order, and K; preserve corpus-wide typed-rule checks for all effective decisions and unchanged ADR-020 path selection. Retrieval/context injection is not redefined as governance.

## 3. Context provenance and safe-failure contract (review gate)

ADR-031 §6 labels are exact, project-local, opaque strings. **They are not credentials, authenticated roles, or a trusted source by themselves.** This proposed CLI input records that the operator or CI wrapper *asserted* a complete context; the CLI cannot cryptographically verify the origin, completeness, or honesty of command-line arguments.

**Trust boundary:** exclusion of lifecycle-active protective decisions on label mismatch is admissible only when invocation arguments are controlled by an operator-owned workflow **outside the agent's authority to edit or substitute**. The operational conditions demonstrating this boundary must be supplied and reviewed **before this charter can merge**; e.g. a pinned CI workflow and an explicit assessment of whether the checked PR/agent can modify the arguments or the wrapper. A plain `--governance-context-complete` switch does **not** establish trust. A command run by an untrusted agent is not a protected enforcement seam in this first slice.

**Fail-safe behavior proposed:**
- **No opt-in / no reviewed trusted context:** enforce the existing lifecycle-active corpus; do not interpret empty labels as evidence of nonapplicability. Never silently drop protective decisions. Explicitly label any diagnostic as *context unavailable*, not `not_applicable`.
- **Opt-in but incomplete, malformed, or untrusted context:** refuse to apply context-based exclusions. A deterministic, explicit operational-error result is preferred to a silent PASS. The charter review must pin handling for both human-readable and JSON CLI modes, including exit codes, **without misusing** existing `mneme.check/v1` fields; no new public result schema may be introduced without its own versioned compatibility decision.
- **Complete context from a reviewed trusted invocation:** resolve decision effectiveness under exactly the asserted `GovernanceContext.labels`; if a required label is absent, `not_applicable` can exclude that decision. Preserve global decisions and lifecycle exclusions. Record the context/provenance and resolved identities in a reproducible **test trace**, without inventing persistent enforcement evidence.
- **Conflicting labels:** since labels are opaque, the CLI must not infer mutually exclusive taxonomies (e.g. from a `platform:` prefix). The trusted caller must establish completeness and consistency externally; if it cannot, context is unavailable and exclusion is refused.
- **Governance integrity findings:** `dangling_supersedes` / `supersession_lifecycle_conflict` are not automatically policy-violations or precedence winners. The reviewer must approve an explicit policy for whether such findings block, make evaluation incomplete, or retain conservative coverage **before implementation**.

**Review blocker (not presumed solved):** operator-owned, verifiable context provenance is **not implemented or evidenced** by current Mneme Core. Until that operational contract and CLI JSON/error disposition are reviewed, this is a candidate behavioral charter, *not* a merge-ready authorization. An untrusted agent controlling both its `--governance-label` values and its completeness assertion could otherwise bypass a protective decision.

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

A reviewer must distinguish unit tests of `resolve_effective` (already done in DG1B1) from **end-to-end runtime exclusion tests** (not yet executed).

## 6. Approval and change sequence

1. **Review this draft's first-consumer selection, actual trusted context source, operational fallback/error mapping, and output compatibility.** Revise before approval. Approval of this draft is not implied by #492.
2. Only after resolving §3's review blockers, **merge this behavioral charter** as a separate PR.
3. Then open and merge a matching `[layer1-freeze]` amendment under the frozen document's Amendment Procedure; reference the merged charter and its bounded first surface.
4. Only then implement the authorized runtime slice in its own PR with the §5 offline, adversarial, compatibility and full-suite gates.
5. DG1B2 remains independently evidence-gated; remaining DG1F surfaces and DG1G remain unimplemented.

**Merge status of this draft: HOLD until §3 provenance and status/output decisions are independently reviewed.**

# DG1F Runtime Convergence — Architecture Readiness and Charter Inputs

**Status:** draft assessment; **not** an implementation charter and **not** authorization to change any runtime behavior.
**Source anchor:** `main` at `6da5cae269ef532faf969e1f5cbad5342d92b246` (DG1B1 merge, PR #487).
**Governing decisions:** [ADR-031](../adr/ADR-031-decision-governance-semantics.md) §4, §6–§7, §10–§12; [ADR-017](../adr/ADR-017-enforcement-scope-vs-retrieval-scope.md); [ADR-020](../adr/ADR-020-explicit-path-applicability-for-typed-rules.md); [ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md); [ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md); [Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md) and the [DG1B1 charter](2026-10-08-dg1b1-decision-applicability-charter.md).

## 1. Why this preflight exists

DG1B1 is merged and makes canonical decision applicability explicit. The resolver can answer whether an authoritative decision governs a supplied `GovernanceContext`. It deliberately does **not** alter any runtime enforcement input, hook, Audit, protection, readiness, or MCP behavior. DG1F would change that boundary and requires new authority, not an automatic continuation of DG1B1.

**Sequence gate:** ADR-031 §11 currently orders DG1B1 → **DG1B2 waivers** → DG1F → DG1G. DG1B2 is still evidence- and canonical-target-binding-gated (ADR-031 §12; DG1B1 charter §6). An applicability-only DG1F increment **before** DG1B2 would change the accepted sequence and must be explicitly decided through architecture review; this document does not approve a reorder.

**Freeze gate:** ADR-031 §7 and the Layer 1 freeze require a **separately merged DG1F charter** before changing enforcement inputs. Under the freeze Amendment Procedure §3(b), the charter merges **before** a matching `[layer1-freeze]` amendment, which itself precedes behavioral implementation. DG1B1's amendment explicitly excludes DG1F.

## 2. Observed implementation boundary (at source anchor)

| Surface | Verified current path | What DG1F must not assume |
|---|---|---|
| Canonical authority | `mneme/decision_index_persistence.py` loads canonical v1/v2 state; v2 carries optional, exact, project-local `required_labels`. | Labels do not come from retrieval metadata or source text. |
| Shared resolution | `mneme/decision_governance.py:resolve_effective(index, GovernanceContext)` evaluates lifecycle, then set containment of required labels, with `not_applicable` cause. | A missing label is **not** evidence that a particular nonmatching platform was positively established. |
| Existing runtime projection | `mneme/decision_projection.py:project_canonical_index` projects lifecycle-active decisions only and currently ignores DG1B1 applicability. | Changing that global load-time projection without an evaluation context could silently discard constraints. |
| Memory loading | `mneme/memory_store.py:MemoryStore.load` loads canonical authority, verifies the compatibility snapshot and exposes projected runtime `Decision` objects. | A repository-wide memory load is not necessarily a specific enforcement action. |
| CLI enforcement | `mneme/cli.py:_cmd_check` loads MemoryStore → constructs DecisionRetriever → retrieves → calls `check_prompt(..., input_path=target_path)`. There is currently no supplied `GovernanceContext.labels` in this flow. | Retrieval score, input-path heuristics or operating-system assumptions may not supply governance authority. |
| Enforcement scope | `mneme/enforcer.py` has separate retrieval-gated and corpus-wide literal-rule tiers per ADR-017; ADR-020 path selectors remain rule-level. | A DG1F change must not turn typed enforcement back into a top-K-only operation. |
| Other consumers | ADR-031 §11 identifies duplicated `active` tests in protection candidate selection, activation precheck, Audit aggregation and readiness; the DG1B1 charter additionally names hooks and MCP. | Their individual inputs, trust boundaries, and behavior require a per-surface inventory before any authorization to converge them. |

This table is a starting inventory, **not** a claim that all consumers have been audited.

## 3. Unresolved architectural choices — not silently decided

### A. Sequencing relative to DG1B2

Choose and record one of:

- **Preserve ADR-031 §11:** complete the separately gated DG1B2 work, then prepare/authorize DG1F; or
- **Explicitly amend the sequence:** authorize a bounded **applicability-only** DG1F increment before waivers, leaving all waiver semantics and future convergence unaffected.

Do not implement either option until the chosen authority change is accepted.

### B. Deterministic and trustworthy context supply

For each enforcement surface, identify the authoritative source of project-local labels and the point where that source is checked. ADR-031 §6 labels are opaque and convey no authenticated identity, organization, team or role.

Record the distinction between **confirmed nonmatching context** (for example a caller explicitly supplying `platform:linux` under a documented contract) and **context unavailable** (no trusted platform information supplied). The DG1B1 resolver currently returns `not_applicable` when a required label is absent; an adapter must not silently treat unavailable context as proof that a security-related decision should be excluded.

Before runtime implementation, explicitly choose and test the safe operational outcome for missing, invalid or conflicting context. Candidate policies are incomplete/blocked evaluation or preserving prior control coverage; neither is authorized by this assessment. No label inference from OS, filenames, retrieval scores, MCP scope hints or LLM output is authorized.

### C. Resolver findings and ambiguity

DG1C reports governance-integrity findings such as `dangling_supersedes` and `supersession_lifecycle_conflict`. Their effect on enforcement remains deferred to DG1F. Specify when a finding makes an evaluation incomplete or blocked. Do not silently turn a finding into a pass or a fabricated precedence winner.

### D. Scope and output contracts per consumer

Specify the first bounded consumer to change, its input schema/provenance, and its output/exit-code semantics. Converge one consumer at a time only after parity tests.

- Distinguish guidance retrieval from authoritative decision selection (ADR-017, ADR-031 §4).
- Apply ADR-020 rule selectors **after** decision effectiveness; do not conflate them.
- Preserve ADR-030 version/rule identity and ADR-029 current-run evidence semantics.
- An MCP addition to the ADR-027 tool contract is **not** implicitly approved by DG1F (ADR-031 §5).
- Any change to Audit, readiness or protection needs an explicit, surface-specific contract; totals or eligibility must not shift accidentally.

## 4. Minimum candidate acceptance evidence (not authorization)

Reuse the committed, offline GSA-TTS ADR-0028 fixture and `tests/test_dg1b1_functional_acceptance.py`:

1. **Parity:** with no applicability declared, old and new evaluations use the same decisions, rules, verdicts and evidence identities.
2. **Matching context:** with explicitly supplied `platform:windows`, the Windows-only decision reaches rule applicability and enforcement.
3. **Confirmed nonmatch:** with an explicitly supplied and trustworthy `platform:linux` context, only the Windows-restricted decision is excluded; global decisions remain protected.
4. **Unavailable/invalid context:** must not produce a silent PASS by filtering out an otherwise active, constrained decision. The exact outcome requires choice B.
5. **Lifecycle:** superseded/deprecated/inactive decisions never regain authority through matching labels.
6. **Independence:** retrieval scores/top-K cannot determine governing decisions; ADR-020 path applicability stays separate and unchanged.
7. **Reproducibility:** context, effective IDs, cause codes, rule IDs and enforcement outcome can be replayed without a model or live network.
8. **Regression:** existing Layer 1 canonical benchmark fixtures and methodology stay unchanged; add a separately authorized acceptance suite for any behavior-changing tests.

The existing DG1B1 acceptance F12 deliberately shows identical strict `mneme check` outcomes **with and without** applicability. This is the before-state; it is not a DG1F success test.

## 5. Readiness and next authorized step

- [x] DG1B1 accepted and merged (#487); canonical resolver and migration available.
- [x] ADR-031 §8a extension namespacing accepted and implemented (#490 / #487).
- [ ] Resolve the **DG1B2 → DG1F sequencing gate**, or approve a separate ADR-031 sequence amendment for an applicability-only DG1F slice.
- [ ] Inventory each proposed consumer's context source, enforcement entry point and safe failure path.
- [ ] Review and merge a **bounded DG1F behavioral charter** identifying exactly the first consumer and acceptance contract.
- [ ] Only then merge a corresponding `[layer1-freeze]` amendment under the documented procedure.
- [ ] Only then begin runtime code changes and evaluate the results against controlled fixtures.

**Non-goals of this document:** no public API or CLI flag is selected, no runtime filter is designed/implemented, no waiver semantic is inferred, no DecisionRetriever, ConflictDetector, MCP, hook, Audit, readiness or protection behavior changes, no benchmark-methodology change, and no release or merge approval.

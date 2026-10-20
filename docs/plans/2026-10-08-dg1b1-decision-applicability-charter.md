# DG1B1 Decision Applicability Charter

**Status:** draft — pending review; becomes the charter basis for DG1B1 only on merge  
**Anchor commit:** `6411ba19593c986da6868c94c4a39885eed5fdb7` (DG1A/C/E/D/P + roadmap/publication-boundary alignment on `main`)  
**Governing ADR:** [ADR-031](../adr/ADR-031-decision-governance-semantics.md) §4, §6–§8, §11  
**Provides charter basis for:** a subsequent `[layer1-freeze]` amendment under the freeze Amendment Procedure 3(b).  
**Required sequence:** this charter merges first → the `[layer1-freeze]` amendment references the merged charter → only then may DG1B1 implementation start.

---

## 1. Evidence that opens the DG1B1 gate

ADR-031 makes decision applicability evidence-gated. The gate is now supported by a concrete, source-grounded repository case in the frozen Open Architecture corpus:

- repository: `GSA-TTS/agentic-coding-quickstart`
- pinned repository SHA: `8e6160c63acc35bd48d0a3844e133ea3ad52a464`
- reviewed reference: `ref-gsa-agentic-coding-quickstart-005`
- source: `docs/adr/0028-windows-native-secret-storage.md`
- source status: accepted
- source decision text explicitly adopts the Windows-native backend and states that it is **"gated to Windows hosts (MSYS/MINGW)"**, with the plain file backend retained as fallback where the Windows-native mechanism is unavailable.

The evidence is the source ADR text itself. The O1A classification is research data and does not become canonical authority by this charter.

This case exposes a model gap in current Mneme:

1. `resolve_effective` over v1 treats every canonical `active` decision as effective and intentionally ignores `GovernanceContext.labels`.
2. `context_scope` is retrieval-only and cannot become governance applicability.
3. ADR-020 applicability is rule-level and repository-path-only; it cannot express a host/platform condition on the decision itself.
4. Therefore an explicitly Windows-only accepted decision cannot be represented faithfully as authoritative-but-effective-only-in-Windows-context without adding decision applicability.

Adjacent evidence does **not** widen this charter. In particular, rule/file false positives such as issue #150 remain ADR-020/rule-applicability concerns, not DG1B1 authority.

---

## 2. Authorized semantic change — exactly this

DG1B1 may add the first persisted decision-applicability semantic with this minimal contract.

### 2.1 Required project-local labels

A canonical decision may optionally declare a non-empty set of exact **required context labels**.

Conceptually:

```text
Decision applicability
    required_labels: ["platform:windows"]
```

Resolution is deterministic set containment:

```text
no applicability declared
    -> globally eligible (existing behavior)

required_labels declared
    -> eligible iff every required label is present in GovernanceContext.labels
    -> otherwise ineffective with cause not_applicable
```

Rules:

- labels are opaque project-local strings, as already defined by ADR-031 §6;
- matching is exact and case-sensitive;
- no globbing, regex, substring matching, hierarchy, role lookup or inference;
- duplicate labels normalize away; persisted order is deterministic;
- an empty `required_labels` list is invalid — omit applicability for global eligibility;
- decision applicability is evaluated only after lifecycle eligibility; a non-active lifecycle retains its lifecycle cause rather than being relabelled `not_applicable`.

This first slice does **not** add path-based decision applicability. ADR-020 path selectors remain rule applicability only. Path-based decision applicability requires its own evidence and semantic-feature extension later.

### 2.2 Resolution trace

For a lifecycle-active decision with applicability:

- match → decision remains `effective`; trace records the required labels and matched context labels;
- mismatch → decision is `ineffective` with ADR-031 cause `not_applicable`;
- the resolver never consults retrieval score, source text, model output, file order or wall-clock time.

The same canonical state plus the same `GovernanceContext.labels` must produce the same result.

### 2.3 No runtime convergence in B1

DG1B1 authorizes canonical representation, validation, migration and resolver semantics only.

It does **not** authorize changing which decisions the CLI, enforcer, ConflictDetector, protection, Audit, readiness, hooks or MCP runtime surfaces consume. Those surfaces continue using their current behavior until DG1F.

Per ADR-031 §7, any DG1F step that changes enforcement inputs requires its **own merged charter**. At that point each consuming surface must either supply the required project-local context deterministically or fail safely; B1 does not silently invent context.

---

## 3. Persistence and migration contract

DG1B1 is the first persisted DG1 semantic, so it introduces `mneme.decision-index/v2` exactly under ADR-031 §8.

Required properties:

1. **Explicit migration only.** v1 → v2 is a deliberate migration command/operation; no reader or writer migrates implicitly.
2. **Compatibility default.** Migrating a v1 document creates no applicability for existing decisions. Their effective behavior therefore remains globally eligible.
3. **Closed semantic keys.** Unknown governance-bearing keys at the v2 root or decision-applicability positions are rejected.
4. **Declared feature.** v2 carries required `semantic_features`; a document using this semantic declares a feature name for decision applicability, and readers reject unsupported features.
5. **Non-semantic extensions only.** The ADR-031 namespaced `extensions` point may not affect applicability or resolution.
6. **No speculative fields.** No waiver, path-applicability, organization identity, role or time fields are pre-created.
7. **Old binary refusal.** 0.10.x must continue to reject v2 rather than silently ignore applicability.

The implementation PR must pin these with characterization tests before any v2 write path is accepted.

---

## 4. Authority and authoring boundary

Applicability is governance authority, not retrieval metadata.

- O1A classifiers, MCP producers, source connectors and LLMs may provide **hints/proposals only**; they cannot set canonical applicability by assertion.
- `context_scope`, MCP `decision.applicable_to`, retrieval matches and O1A scopes must never be copied into canonical applicability automatically.
- Canonical applicability may be created or changed only through an explicit Mneme-owned authority operation obeying ADR-030 writer discipline: validate before mutation, atomic persistence, no repair, no implicit migration.
- The exact public authoring UX is **not authorized by this charter**. The first B1 implementation may expose representation/resolver/write primitives needed to prove the contract, but a new CLI/MCP authoring surface requires a separately reviewed interface decision.

This prevents the evidence source from becoming an automatic ingestion rule.

---

## 5. Frozen — explicitly unchanged

DG1B1 does not change:

- DecisionRetriever scoring, K, tokenization or relevance semantics;
- `context_scope` or MCP `decision.applicable_to` meanings;
- ADR-020 typed-rule include/exclude path semantics;
- rule types, rule matching or ConflictDetector violation semantics;
- ADR import precedence, including DG1P's removal of date authority;
- lifecycle vocabulary;
- Audit tier formulas;
- protection semantics;
- current benchmark fixtures or frozen benchmark methodology;
- evidence persistence (ADR-029 remains current-run only);
- MCP authority/producer privileges;
- cross-repository federation (DG2);
- organization identity, RBAC/SSO, team/role labels or enterprise authority inference.

---

## 6. B2 remains closed

This charter does not authorize waivers.

The reviewed Helix corpus contains a real narrow, approval-gated exception to a platform-wide service-worker ban (`ref-helix-019`), which is evidence that exception semantics matter. However the current reviewed corpus does not bind that underlying ban to a separately identified canonical target decision/version as ADR-031 §12 requires for a waiver.

Therefore DG1B2 remains evidence/target-binding gated. No waiver schema or placeholder field is added to v2 by B1.

---

## 7. Required implementation validation after the freeze amendment

The later DG1B1 implementation PR must demonstrate at least:

1. v1 → v2 explicit migration with all existing decisions globally eligible;
2. 0.10.x/v1 reader refusal of v2;
3. v2 unknown semantic key and unsupported feature rejection;
4. applicability absent → current DG1C effective result;
5. required label present → active decision effective;
6. required label absent → active decision `not_applicable`;
7. non-active lifecycle cause wins over applicability cause;
8. exact/case-sensitive label matching and input-order invariance;
9. irrelevant context labels do not change the result;
10. retrieval scores cannot change applicability;
11. ADR-020 rule applicability remains independent;
12. O1A/MCP/source hints cannot create canonical applicability automatically;
13. DG1D reports governed-scope/effective-set change from supplied snapshots/contexts using the same resolver;
14. no production runtime consumer changes its enforcement input in B1.

Mutation tests must prove the label predicate and compatibility default are actually exercised.

---

## 8. Exit criterion for this charter

The charter is satisfied when, **after** the required `[layer1-freeze]` amendment:

- v2 decision applicability is persisted and validated under ADR-031 §8;
- the shared resolver returns `not_applicable` deterministically from explicit required labels;
- absent applicability preserves v1/global eligibility;
- change resolution derives from the same resolver;
- no runtime enforcement surface consumes the new result yet;
- full gate/main tests remain green.

DG1F remains a separate later authority transition with its own charter where enforcement inputs change.

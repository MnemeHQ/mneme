# ISO/IEC/IEEE 42010:2022 alignment profile M1 — Mneme decision governance

**Status:** Research profile complete for one bounded example, **NOT** ISO conformance certification, a conforming Architecture Description (AD), or a new product capability.  
**Date:** 2026-11-01  
**Tracking:** [Mneme #715](https://github.com/MnemeHQ/mneme/issues/715)  
**Scope:** Existing Core Decision Index and an existing synthetic enforcement experiment. No runtime changes.

## 1. Decision in brief

**Finding:** Mneme strongly supports an important *part* of architecture descriptions: identifiable, source-linked architecture decisions with rationale, lifecycle, authority, typed rules and execution evidence. It does **not** currently establish that it produces an ISO/IEC/IEEE 42010:2022-conforming AD. Stakeholders, their concerns, perspectives, aspects, formally specified viewpoints, view-component descriptions and AD-element correspondences are incomplete or unverified.

**Recommendation:** **GO** for a read-only, AD-compatible decision/evidence export *design*; **DEFER** an exporter implementation and conformance claims until a real enterprise buyer needs the interoperability and the complete normative clauses are reviewed. Do not change DG1/DG2 or the canonical Decision Index to meet this research milestone.

## 2. Standards boundary and source quality

- [ISO 42010:2022 official publication](https://www.iso.org/standard/74393.html) (published 2022-11): requirements for the structure and expression of ADs, and distinct conformance targets for an AD, architecture description framework (ADF), architecture description language (ADL), architecture viewpoint and model kind. It **does not** prescribe tools, AD file format, architecting processes or an entity's architecture.
- [Published 2022 preview and contents](https://cdn.standards.iteh.ai/samples/74393/fc7b7f103d8446a4b87a3261e31370d3/ISO-IEC-IEEE-42010-2022.pdf): verified published edition, glossary and **clause headings**; used as a navigation aid, not as access to the complete normative wording.
- [ISO 42020:2019 official publication](https://www.iso.org/standard/68982.html) (confirmed current, scheduled for revision): complementary **architecture processes** at project/organizational level. This profile does not assess its process conformance.
- No licensed complete normative 42010/42020 body was available for this review. Consequently, **all clause rows below are topical mappings, not 'shall'-by-'shall' compliance checks**. Avoid inferring that any field is mandatory/optional solely from the headings.
- An accepted ADR is an architectural-decision source, not necessarily a complete AD; a rule PASS/FAIL is an enforcement result, not an architecture-description conformance verdict.

### Evidence / pinning

The selected repository files were inspected through the linked repository sources on 2026-11-01. The *sandbox's own tested source state* is pinned independently in its [RESULTS.md](../../validation/orchestrator-decision-sandbox/RESULTS.md): clean clone at `3ea6308a` containing middleware fix `cf6bc40b`, Python 3.12.10, `mneme-hq` 0.10.0 from source, LangChain 1.3.17, LangGraph 1.2.11, and **48/48 experiment tests passed**. These are **previously recorded results, not a fresh execution for this profile**. The evidence summaries are committed under `evidence/post-fix/`.

## 3. Two intentionally distinct evidence cases

### A. Real accepted Mneme architectural decision (architecture-level evidence)

**[ADR-023: Canonical Decision Index and Runtime Projection Boundary](../adr/ADR-023-canonical-decision-index-and-runtime-projection-boundary.md)**, accepted 2026-09-11, identifies a human decider and documents:
- **Concern:** prevent the Layer 1 runtime `Decision` representation from becoming the universal cross-organization decision schema; prevent discovered/unverified decision text from automatically receiving authority.
- **Decision:** source-independent, versioned canonical Decision Index as authority, with a separate Layer 1 projection; explicit rule typing; decision scope distinct from typed-rule path applicability.
- **Rationale:** present runtime is optimized for the initial architectural-governance wedge, but future decisions may concern systems, infrastructure, data or operations and may have zero executable rules.
- **Implementation correspondence (human-readable evidence, not a typed ISO correspondence):** [`mneme/decision_index.py`](../../mneme/decision_index.py) with canonical source evidence, decision and rule records; [D1 closeout](d1-closeout.md) and [ADR-031](../adr/ADR-031-decision-governance-semantics.md) with authority/effective-decision evolution.

**Limitation:** ADR-023 is not an individually enforced `FORBID_LITERAL` example, and **there is no direct per-change FAIL trace attributable to ADR-023 itself**. Do not claim one. It is the real accepted decision and rationale evidence for the standards alignment.

### B. Synthetic accepted architecture decision (fully bounded decision-to-verdict experiment)

**[Synthetic orchestrator ADR-001](../../validation/orchestrator-decision-sandbox/adr/ADR-001.md)** (fixture, status `accepted`; **not** a verified human/enterprise authorization) governs a **fictional router**, a different entity of interest from Mneme itself.

**Source decision:** routing validator must enforce a maximum 5-second deadline and a safe fallback; timeout must not be disabled.

**Stated sub-constraints:** C1 no disabled deadline; C2 configured maximum of five seconds; C3 safe fallback. Only a literal part of C1 has a typed rule:
`FORBID_LITERAL DISABLE_ROUTER_TIMEOUT`, `include_paths: ["src/**"]`.

**Evidence-bearing path (documentation-level correspondence, not a native AD-element graph):**

```text
synthetic ADR-001 (accepted fixture input, scope routing)
  → ADR import into isolated fixture memory (README reproduction protocol)
  → one active decision + one typed literal rule (verified by fixture harness)
  → governed src/router.py candidate
  → mneme check OR mapped LangChain pre-tool file-write interception
  → per-attempt outcome + unchanged/changed file SHA256 + oracle
```

**[Measured results](../../validation/orchestrator-decision-sandbox/RESULTS.md)** and [committed post-fix summary](../../validation/orchestrator-decision-sandbox/evidence/post-fix/summary.json):

| Case | Independent functional oracle | Mneme result | Meaning |
| --- | --- | --- | --- |
| A: 5 s deadline and fallback | ACCEPT | PASS | Compliant change allowed |
| B: `DISABLE_ROUTER_TIMEOUT` disables deadline | REJECT | FAIL, pre-write deny on mapped tool | Explicit literal rule enforced; no file handler run on blocked attempt |
| C: 60 s deadline without sentinel | REJECT | PASS | **Undetected C2 violation** |
| D: fallback removed without sentinel | REJECT | PASS | **Undetected C3 violation** |
| E: sentinel only in comment/string | ACCEPT | FAIL | **False block** |
| F: sentinel in `docs/notes.md` | ACCEPT | PASS, excluded | Correct path scope |

The recorded rule identity in this experiment is `ADR-001:FORBID_LITERAL:c3c126b4ac2aa3b9acc80f70ec5cf262`. The post-fix pre-tool experiment records a denied proposed edit/write with zero handler calls and matching before/after SHA256; a subsequent compliant retry is allowed. **This is historical synthetic validation, not evidence of production coverage.**

**Critical limits:** rule coverage is **one literal facet of one of three decision constraints**, not 100% architecture compliance. The existing Audit's 100% *protection-tier* metric cannot be substituted for semantic constraint coverage. Mapped file tools are covered within project paths; custom tools, out-of-project writes and raw graph nodes are not automatically covered. The synthetic ADR lacks a full architecture-description package and a separately recorded substantive rationale/alternatives. There is no proof of a complete 42010 AD.

## 4. Bounded architecture-description profile (analysis-only)

This is a **research annotation assembled from existing materials**, not a built-in Mneme export or a claim that Mneme automatically stores these relationships.

| AD-related concept | Constructed profile value | Evidence classification |
| --- | --- | --- |
| Entity of interest (EoI) | **Mneme Core**, for architectural-decision authority / Layer 1 execution boundary | Derived from ADR-023 and [Mneme architecture orientation](README.md) |
| AD identifier / intended use | `mneme-42010-research-profile-m1`; evidence-based interoperability study only | **New research label**, not existing canonical AD metadata |
| Stakeholders | Architecture owner/reviewer, platform engineer, contributor, assurance reviewer | **Analyst-proposed roles**; not verified structured stakeholder records |
| Concerns | Authority/source integrity; traceability of decisions; prevention of prohibited changes; reliable verdict scope; minimization of false blocks | Derived from ADR-023, ADR-031 and synthetic sandbox; **not** recorded as typed concern associations |
| Stakeholder perspectives / aspects | Decision authority & provenance; runtime enforcement & limitations | **Analyst-proposed**, not formal 42010-compliant perspective/aspect specifications |
| Architecture views | Existing ASCII+C4 context/containers/components and ADR map in [architecture orientation](README.md) | Source documents exist, **formal viewpoint selection and view-component conformity not established** |
| Architecture decisions | Real accepted ADR-023; separately a fictional accepted fixture ADR-001 for the enforcement demonstration | Different entities; must not merge their identity or authority |
| Rationale | ADR-023 context/decision text explains the architecture choice; sandbox ADR-001 states constraints but no independently verified full rationale | Partial |
| Correspondences | ADR-023 → canonical model/projection; synthetic ADR-001 → typed rule → test case → runtime/CLI outcome | **Research cross-references**, no typed correspondence methods or automated consistency validation |
| Execution/evidence | Previously recorded pre-write result, file digests, independent functional oracle, known unevaluated surfaces | Valuable **Mneme extension**, not a substitute for a complete AD |

### One candidate viewpoint (proposal, not an existing 42010 viewpoint)

- **Name:** Decision authority and execution trace.
- **Proposed stakeholder concerns:** which source authorized the decision, which version is effective, which targets/rules it affects, which enforcement surface evaluated it, and what remains unevaluated.
- **Proposed view components:** (1) canonical decision/version/source table; (2) decision → derived-rule mapping; (3) target and supported enforcement surface; (4) evidence and coverage limitations.
- **Known missing specification:** model-kind/legend rules, procedures for producing/reconciling view components, correspondence method, concern-to-stakeholder trace, and explicit version consistency across multiple AD views. These require design and normative review.

## 5. 42010:2022 Clause 6 coverage map (topical, NOT a compliance audit)

| Published heading | Mneme evidence or plausible mapping | Status for a complete AD |
| --- | --- | --- |
| 6.1 AD identification/overview | This research profile and existing architecture orientation; no established AD metadata contract | **Partial / analyst-provided** |
| 6.2 Stakeholders | Human decider named in ADR; proposed user roles above | **Not systematically evidenced** |
| 6.3 Stakeholder perspectives | Proposed authority and enforcement perspectives | **Not implemented as AD structure** |
| 6.4 Concerns | ADR context explains concerns, but no stakeholder-to-concern linkage contract | **Partial** |
| 6.5 Aspects | Analyst proposes authority/execution aspects | **Not formally specified** |
| 6.6 Architecture viewpoints | C4 views exist, but formal required viewpoint specification not shown | **Not established** |
| 6.7 Architecture views | Source has ASCII, C4, ADR map views | **Present in documents; AD mapping incomplete** |
| 6.8 View components | Diagrams/documentary components exist | **No verified model-kind/legend contract** |
| 6.9 Architecture correspondences | Human-readable decision-to-code and decision-to-evidence links | **Partial; no typed AD correspondence methods** |
| 6.10 Architecture decisions and rationale | ADR-023 strong rationale; fixture decision and trace; sometimes empty rationale allowed in producer proposals | **Strong decision substrate; AD-level completeness unverified** |

Clause 4 conformance remains **UNASSESSED**, as do ADF/ADL/viewpoint/model-kind conformance claims. A complete authorized normative-text audit, with shall/should distinction and conformance case, is a **separate acceptance gate**.

## 6. Minimal non-authoritative interoperability design

**Proposal:** a read-only export/manifest *adjacent to* a customer's AD tooling. This is a conceptual output specification; no exporter code or API exists under this milestone.

| Proposed export record | Source and rule |
| --- | --- |
| `source_decision_id`, `source_revision`, `source_locator` | Reuse canonical Decision Index verified identity/source fields; **never synthesize missing authority** |
| `statement`, `rationale`, `lifecycle_status` | Preserve original values and missingness, never invent rationale |
| `governance_scope`, `rule_id`, `rule_applicability` | Explicit separate fields; never turn a decision scope into rule applicability |
| `related_ad_element_refs` | **Optional externally supplied cross-references** to an AD's view, concern, element; no automatic authority |
| `verdict_evidence_refs` | Links to already retained evaluation evidence with surface, pin and limitations, or `none`; never confuse declared evidence with tested verdict |
| `mapping_status` | `mapped`, `proposed`, `unmapped`; distinguish analyst annotation from verified machine links |

**Read-only direction:** canonical Mneme decision state → optional evidence-backed representation → customer's AD/EA tool. It **must not** allow an inferred concern, generated correspondence, external EA-tool record or LLM result to create/modify accepted Mneme policy. Inverse ingestion would need the existing proposal + human authority workflow.

**Minimum falsifiable example:** for ADR-023 export a stable decision identifier and original rationale with a link to the Core architecture view, explicitly `verdict_evidence_refs: none`; for sandbox ADR-001 export an *isolated synthetic example* with C1 rule ID and B verdict reference while recording C2/C3 as not enforced. Do not combine these into an imaginary single canonical record.

## 7. 42020:2019 interface (NOT process conformance)

42020 concerns *architecture governance and architecture processes* rather than an AD's information structure. Mneme potentially supplies inputs and evidence to such processes through:
- decision authority, approved/rejected proposals and lifecycle;
- effective applicability/precedence and change impact (DG1);
- traceable enforcement result and explicitly unevaluated paths.

But it does **not** by itself establish a complete organizational process for architecture governance, evaluation, elaboration, decision delegation, review meetings, role accountability or cross-system approval operations. [Enterprise EA integration #5](https://github.com/MnemeHQ/mneme-enterprise/issues/5) and [Data Engine architecture reconstruction #36](https://github.com/MnemeHQ/mneme-data-engine/issues/36) are complementary *research*, not evidence of 42020 conformance.

## 8. Exit, claims and follow-up

**Done in this M1 profile:**
- Evidence-backed comparison of the standard's published conceptual structure to concrete Mneme ADR, code, orientation and experiment;
- one source-linked *synthetic* decision → rule → proposed mutation → observed verdict trace, including negative/false-positive controls;
- separate *real accepted* decision → rationale → architecture code linkage;
- named gaps, honest evidence limitations and a minimal non-authoritative export design;
- explicit go/defer recommendation.

**Not done / future gates:**
1. Full authorized 42010:2022 normative clause-by-clause conformance assessment (including Clause 4) and license handling.
2. Complete conforming AD case with properly identified stakeholders, concerns, perspectives, viewpoints, views, view components, correspondences and essential decisions.
3. A *single real-world* human-authorized decision tied to an independently verified enforcement verdict, if an enterprise pilot warrants that claim.
4. Customer evidence (2–3 architecture/platform buyers) for AD export/procurement, and the corresponding 42020 process map.
5. Any exporter, schema change, acceptance test, certification, external audit, public conformance claim or live production validation.

**GTM language safe to use:** Mneme links architecture decisions to governed software changes and evidence, and is **exploring interoperability** with ISO/IEC/IEEE 42010 architecture descriptions. **Do not say:** Mneme is 42010-compliant, ISO-certified, or enforces every essential architectural decision.

**Disposition:** M1 research profile authored for review. **GO** to buyer qualification and normative-clause review if justified; **DEFER** implementation. No change to current priority of pilots, DG1/DG2 reliability or independent validation.

---

## 9. Reconciliation: enforcement progress after the original orchestrator experiment (2026-11-01)

**Why added:** The original synthetic orchestrator experiment is a historical 20 October evidence baseline, **not** the latest product/enforcement capability inventory. This addendum does not rewrite its frozen evidence or claim that its single original `ADR-001` fixture has gained new rules automatically.

### Constraint-by-constraint assessment

| Original sandbox case/concern | Subsequent evidence | Correct as-of claim |
| --- | --- | --- |
| **C1 — timeout disabled, only prohibited literal modeled** | ADR-019 shipped literal matching. Separate [P0-A semantic detector experiment](../../validation/semantic-constraint-p0a/RESULTS.md) tested lexical/token and static-form alternatives, offline only. | Original C1 rule remains literal-only. Broader disabling semantics are **not generally enforced**. |
| **C2 — 60 s exceeds 5 s** | Accepted [ADR-034](../adr/ADR-034-static-numeric-upper-bound-typed-rule.md) introduced `FORBID_NUMERIC_ABOVE` for a bounded subset of Python static value sources. [Independent M4 held-out result](../validation/adr-034-m4-heldout-scoring-2026-10-24.md): **PASS, 12/12 gates, 161/161 cases**, frozen implementation `f25f0e84`; original G1 blind result stays FAIL (149/155) in its original record. | **Supported for an explicitly authored numeric rule through `mneme check --source-file` whole-file audit**, within ADR-034's recognition/trust boundaries. This is not a general C2 guarantee, and the original ADR-001 fixture still has no numeric rule. |
| **C2 before mutation** | ADR-034 **G2-1** implemented a narrow new-file `Write` pre-write route, but [R1 blind scoring](../validation/adr-034-g2-1-blind-scoring-results-2026-10-25.md) **FAIL** and [R2](../validation/adr-034-g2-1-r2-blind-scoring-results-2026-10-27.md) **FAIL** (2/143 attribution cases); [R3 pre-scoring record](../validation/adr-034-g2-1-r3-pre-scoring-completion-2026-10-29.md) explicitly states **SEALED / G2-1 FAIL**, no R3 scoring yet. | **No validated general pre-mutation numeric-enforcement or production-ready claim**. Experimental implementation/host characterization does not equal a closed validation gate. |
| **C3 — safe fallback removed** | [P0-A M3 structural-fallback detector](../../validation/semantic-constraint-p0a/RESULTS.md) detected 3/3 C3 cases with zero false blocks on the visible frozen synthetic whole-file set, but it is an **offline prototype**, not loaded by Mneme Core, hooks or CI. Its introduced-delta gate did not stop the deletion-only case U. | **Research evidence, not shipped enforcement**. A formal new typed rule and its independent blind validation would be required. |
| **E — harmless literal in comments / strings** | P0-A M1 lexical/token prototype removed its lexical false blocks on the frozen cases, but it was not integrated. ADR-019 literal matching intentionally remains byte/text-oriented. | **Still a production-rule false-block class** absent an authorized matcher contract change; not fixed by DG or CI. |
| **Relative path / decoy working directory bypass** | [Core #571](https://github.com/MnemeHQ/mneme/issues/571) fixed via [#573](https://github.com/MnemeHQ/mneme/pull/573); [post-fix sandbox](../../validation/orchestrator-decision-sandbox/RESULTS.md) verified affected relative-path writes/edits block and unchanged target digests. | **Fixed for the tested mapped integration paths**, not proof of arbitrary tools or roots. |
| **Custom file-write tools / outside project root / raw graph nodes** | [Coverage design](../plans/2026-10-20-enforcement-coverage-custom-tools-and-project-boundary.md) is explicitly **PROPOSED**, no generic tool mapping or cross-root interception implementation authorized there. | **Known unsupported or unevaluated surfaces** still need adapter contracts and host-specific proof. |
| **Cross-repository wrong decision memory** | [T-08 live evidence](../validation/dg1f-t08-cwd-memory-selection-2026-10-15.md) and [CHANGELOG](../../CHANGELOG.md) describe a **shipped direct-write target-based memory-discovery correction**; nested/explicit-memory precedence limitations remain. | Important **target-to-policy correctness improvement**, not a semantic detector. |
| **Trustworthy merge blocking** | [CI1 programme #540](https://github.com/MnemeHQ/mneme/issues/540) records isolated lab **V0 compliant merge** and **V1 forbidden merge refused (HTTP 405)**, additional adversarial tests, and a V11 strict-up-to-date experiment; Core's existing `mneme-check.yml` was previously **advisory**, and adopting a production trusted gate was **deferred**. | **Lab-measured merge-blocking is real**, but **not proof that Mneme's production workflow is now a trusted merge blocker**. |

### Owner of the remaining work, without duplicate enforcement engines

- **Semantic enforcement / typed-rule contract (Core, alongside SE research):** model C1 beyond literals, C3 fallback semantics and false-positive mitigation; move a *specific*, independently validated detector from offline research into Core only under its own ADR/Layer 1 amendment. ADR-034 G1 provides the precedent. Data Engine evidence-recovery is not the trusted rule evaluator.
- **DG1/DG2 (Core):** authoritative decision/version, which decision applies to the *actual* target, scope, precedence, source federation and legitimate exceptions. Do **not** make DG produce semantic change verdicts. [DG1 #497](https://github.com/MnemeHQ/mneme/issues/497) records applicability/waiver/runtime-convergence gates separately.
- **Agent adapters / orchestrators:** map real mutation commands and trustworthy target/source identities; cover supported new-file and edit boundaries, not promise interception of raw graph functions or arbitrary tools. A semantic matcher cannot rescue a tool never routed to a control.
- **CI1 (Core assurance/host boundary):** trustworthy policy and evaluator pins, actual evaluated revision, host required checks, reliable merge refusal and decision-linked evidence. Consume DG authority and typed rules; never create a competing policy model. The lab evidence is not automatic production adoption.
- **Research/independent validation:** retain the original failed and passed results under their respective pins; never turn P0-A's offline M3 or G2-1's R1/R2 failed gates into shipped, general semantic enforcement.

**Implication for 42010:** There is now stronger evidence for *operationalizing* a narrow set of explicitly modeled architecture decisions with revision-linked, independently tested numerical evaluation. This is a **Mneme extension to architecture-description work**, not an ISO 42010 AD-conformance proof.

**Implication for 42020:** Mneme can potentially provide stronger monitoring/assessment **evidence** for an organization's architectural directives. The organization's governance roles/processes and unsupported/unmodeled constraints remain external. Claimed conformance cannot be derived from an M4 matcher PASS or a lab CI merge refusal.

**Product/research documentation policy:** Label each result **historical experiment / offline detector / shipped bounded checker / pre-write experiment / isolated CI lab / production evidence**. Never mark all six levels as an undifferentiated `supported`.

# M2 — ISO/IEC/IEEE 42020 architecture-process alignment (Mneme HQ)

**Status:** Completed **bounded research profile**, for technical/product review; **not** a process conformance assessment, certification, product implementation, or customer validation.  
**Date:** 2026-11-01  
**Portfolio intake:** [Mneme #715](https://github.com/MnemeHQ/mneme/issues/715)  
**Related architecture-description milestone:** [42010 M1 draft PR #716](https://github.com/MnemeHQ/mneme/pull/716) (unmerged at this review).  
**Product scope:** Application & Infrastructure Decision Governance; Core OSS decision semantics versus Enterprise decision operations.

## 0. Decision

**Track 42020 separately from 42010, but in the same portfolio issue.** The strongest prospective fit is **evidence-backed implementation and monitoring of architecture governance decisions**. Mneme is not a replacement for organizational architecture governance, portfolio management, architecture conceptualization, architectural evaluation, architecture elaboration, or organizational process enablement.

**Recommendation:** GO on *standards-aware research and buyer qualification*; DEFER feature builds, conformity language, process-management UI, and a parallel policy engine. Reassess once two enterprise architecture/platform buyers request a specific evidence/export workflow, or a real pilot requires it. For backlog triage this is **P2 research**, with **P1 conditional** on design-partner procurement/pilot evidence, and **no delivery target**.

## 1. Primary sources and status pin (2026-11-01)

- [ISO official 42020:2019](https://www.iso.org/standard/68982.html): Edition 1, July 2019, last confirmed in 2025; **remains current** but has an ISO revision stage. Scope covers architecture governance, management and enablement across projects/organizations.
- [IEEE current 42020-2019](https://standards.ieee.org/ieee/42020/7601/): active standard, with architecture governance, management, conceptualization, evaluation and elaboration processes plus enabling activities.
- [ISO online browsing preview](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso-iec-ieee%3A42020%3Aed-1%3Av1%3Aen): officially visible introduction, definitions and headings, including **full vs tailored conformance** as distinct approaches.
- [Published 42020:2019 contents/preview](https://standards.iteh.ai/catalog/standards/iso/6b8a5196-df4b-481a-94ba-b8e348329dc2/iso-iec-ieee-42020-2019): headings for Clauses 4–11, Annex A tailoring and Annex C interactions. Used solely as a table-of-contents guide.
- [IEEE P42020 revision project](https://standards.ieee.org/ieee/42020/12696/): **Active PAR**, approved **2026-09-25**, superseding the 2019 edition *when completed*, not yet a published replacement. The proposed revision's stated scope encompasses AI/ML and infrastructure, among other domains; this is **scope language**, not proof of clauses in an unreleased edition.

**Evidence limitation:** This mapping uses official public scope, introduction and published clause headings, plus repository evidence. **The full normative requirements, process outcomes/tasks and exact conformance wording were not audited under a licensed copy**; 2019 process headings are not a substitute for a `shall`-by-`shall` review. No status percentages or conformance assertions follow.

## 2. The six process families and honest Mneme coverage

| 42020:2019 process / published clause | Relevant Mneme evidence today | Boundary / material gap | Qualification |
| --- | --- | --- | --- |
| **6 Architecture Governance** | Canonical approved decisions and authority separation (ADR-023/027/030); DG1 effective resolution and trace; explicit runtime rules and scope; CI/audit/evidence at supported surfaces | Not an organization-level governance board, policy approval structure, governance plan or complete directives-compliance assessment | **Strongest fit: partial process tooling** |
| **7 Architecture Management** | Versioned Decision Index, lifecycle/supersession, DG1 change comparison, repository audit/readiness | Architecture *collection* management, portfolio objectives, planning, resources, effectiveness reporting, and cross-enterprise operations are not validated | **Partial inputs, not process operation** |
| **8 Architecture Conceptualization** | Architecture recovery/discovery is under Data Engine research; proposal ingestion can preserve ideas without authority | No validated problem-space analysis, tradespace synthesis, alternative-architecture analysis or stakeholder-driven selection process | **Adjacency/research only** |
| **9 Architecture Evaluation** | `mneme audit` measures governability/protection readiness; independent benchmark and oracle discipline for bounded changes | Audit is **not** a complete architecture evaluation of alternatives, stakeholder value, architecture qualities, methods/findings or ISO/IEC/IEEE 42030 framework | **Narrow operational evidence only** |
| **10 Architecture Elaboration** | Existing Mneme documentation includes C4/ASCII views, ADR map, relationships to implementation | Not a view authoring/modeling system, formal viewpoint process or multi-architecture elaboration tool | **Supporting inputs only** |
| **11 Architecture Enablement** | CLI, MCP, hooks, setup, checks, reproducible validation and guidance support development teams | Does not implement an organization's architecture competency program, resource management, training, capability acquisition or improvement governance | **Tooling enabler, not organizational process** |

**Interpretation rule:** A software capability's similarity to a process activity is **not** evidence that Mneme performs the process, that the customer follows it, or that a full/tailored 42020 conformity case exists.

## 3. Governance process (Clause 6) — task-level *topical* crosswalk

Published contents identify six activity clusters under 6.4. Each row below expresses the smallest potential Mneme contribution without claiming to meet every normative task.

| Published 42020 heading | Minimal support evidence or opportunity | Unsupported today |
| --- | --- | --- |
| **6.4.1 Prepare/plan governance effort** | A team's ADR corpus and declared scope can inform planning; not a governance plan generator | Governance charter, accountability, escalation, roles, planning and resource ownership |
| **6.4.2 Monitor/assess/control governance activities** | Core decision-index status; operational compliance/coverage evidence where checks actually ran | Longitudinal organization-wide measurement, controls across unsupported hosts, a process management control plane |
| **6.4.3 Establish architecture collection objectives** | Decision Index scope; DG2 future declared federation could reference known source contexts | Portfolio/collection objectives and collection-wide authority topology are not implemented/validated |
| **6.4.4 Make architecture governance decisions** | Real human-approved ADRs and D2 acceptance/rejection; canonical source/version; producer proposals cannot self-authorize | Formal cross-organization decision delegation, quorum approvals, stakeholder review and RBAC are Enterprise discovery |
| **6.4.5 Monitor/assess compliance with directives/guidance** | Guidance, pre-mutation interception where supported, CI checks and decision-linked evidence; typed-rule outcomes | Coverage is limited to explicitly modeled rules and supported surfaces; semantic compliance for unmodeled decisions is not established |
| **6.4.6 Review implementation of directives/guidance** | Evidence packet linking approved decision/version, governed target, rule and verdict can help an architect review a change | No demonstrated organizational review/closeout workflow, waiver approvals or full architecture-realization assurance |

**Hard boundary:** An ADR status `accepted` is a repository designation, not proof of organizational authorization. A synthetic accepted ADR in a fixture must **not** be portrayed as an enterprise governance decision. A rule `PASS` is not a certification of architectural compliance. Missing evaluation is not approval.

## 4. Core OSS / Enterprise division

| Responsibility | Owner | Why |
| --- | --- | --- |
| Stable canonical decision, source provenance, version, authority and rule lineage | **Core OSS** (ADR-023/027/030) | Reusable source-independent contract |
| Effective resolution, precedence, applicability, waivers, snapshot-level governance change and evidence identity | **Core OSS / DG1** (ADR-031; rollout/waiver status must be verified before claims) | Same semantics must apply to all surfaces |
| Deterministic federation of **explicitly declared** authority across known repositories/sources | **Core OSS / DG2** (planned, not presumed shipped) | Multi-repo governance correctness is not automatically an Enterprise paywall |
| Source discovery, synchronization, organizational identity/RBAC, delegation, approval operations, evidence history, analytics and portfolio reconciliation | **Enterprise** (discovery) | Organization-scale decision operations and verified permissions |
| Candidate architecture/decision recovery with uncertainty and human validation | **Data Engine** (research) | Inferred architecture/authority must not become active policy by implication |
| Architecture modeling, governance board, evaluation procedures, prioritization and human sign-off | **Customer and existing EA/process tooling** | Mneme interoperates; it does not replace governance/accountability |

Evidence: [Core roadmap](../roadmap/README.md), [ADR-031](../adr/ADR-031-decision-governance-semantics.md), [DG1 implementation](../../mneme/decision_governance.py), [Enterprise organizational operations #20](https://github.com/MnemeHQ/mneme-enterprise/issues/20), [Enterprise EA interoperability #5](https://github.com/MnemeHQ/mneme-enterprise/issues/5), [Data Engine reconstruction #36](https://github.com/MnemeHQ/mneme-data-engine/issues/36).

## 5. Practical operating case: where 42020 would meet Mneme

**Illustrative process, not a new validated end-to-end test.** The decision in the example must be *real, explicitly approved* for an actual pilot; the below chain is a target design only.

1. **Customer governance owner** defines a governed architecture entity (e.g., service) and approves a decision with rationale, effective scope and review responsibility. Customer owns approval policy. Mneme receives only an explicitly approved source or a proposal that undergoes the human authority path.
2. **Core Decision Index** stores canonical decision identity and version; DG1 resolves which decision applies to a given change context and why. Unknown binding, missing policy, or unsupported resolution must remain explicit.
3. **Engineering agent / human** attempts a change through a mapped tool or CI boundary. Only explicitly modeled, validated typed rules can be enforced. Unsupported surfaces remain **UNEVALUATED**; no guaranteed universal interception.
4. **Evidence** links subject/revision, decision/version, rule identity, target/scope, attempted action, supported surface, verdict and limitations to a review record, *where such capture exists*. A checked directive alone is not proof that an entire architecture is correct.
5. **Customer reviewer** interprets evidence, approves changes/exceptions under their procedure and maintains the architecture collection. A proposed Enterprise console could link records; no current full workflow or approval system is claimed.

### Falsifiable case to request in a design-partner pilot

Given one *real customer-approved* architectural directive, two change proposals (one permitted and one forbidden), and a pinned execution surface:
- Prove the correct decision/version applies to the **actual target**, not just the agent working directory;
- demonstrate DENY before the change at a supported pre-mutation seam, and allowed good change;
- run independent CI and capture whether checks use consistent rule/revision identity;
- record missing coverage, false blocks, unrelated legitimate changes, exceptions/waivers if supported;
- give customer architect a compact review packet; explicitly record their decision and the limits of Mneme evidence.

**Exit condition:** one externally reviewed link from organizational directive to observed execution evidence; **not** a claim that the whole 42020 governance process conforms.

## 6. Proposed 42020-facing evidence packet (design only)

This is a mapping of *candidate work products*, not asserted mandatory fields from the standard. It does not change any existing API/schema.

```text
architecture_context_ref          customer-provided system/EA entity reference (untrusted until matched)
governance_decision_ref           canonical decision_id + decision_version_id
decision_authority_ref            approved source/acceptance evidence; not AI inference
governance_scope                  decision applicability output; not a rule path selector
rule_ref                          typed rule_id + applicability, or explicitly none
change_ref                        source revision, target, proposed action, actor/workflow ref if available
evaluation_ref                    pre-mutation/CI/evidence event, input digest and verdict
coverage                          which sub-constraints/surfaces checked; which remained UNEVALUATED
exception_ref                     authorized waiver, if implemented and validated; otherwise none
human_review_ref                  separately controlled customer decision; NOT minted by Mneme scoring
data_trust                         provenance + authorization + observation freshness + limitations
```

**Direction:** Core semantics/evidence → read-only linkage → customer architecture/process system. The Enterprise layer could retain records at organization scale once authorized. No auto-acceptance, auto-supersession, fabricated approval, or duplicate policy engine. Use the same logical decision across developer tool, CI and review rather than presenting multiple disconnected records as one guaranteed trace.

## 7. Gap/risk register

| Gap | Why it matters | Next test / owner |
| --- | --- | --- |
| Approval/delegation model | Customer process actor != current CLI accept user, and authority is not derived from an AI suggestion | Enterprise discovery, human review workflow |
| Architecture collection identity | One repo's decision scope != enterprise portfolio entity and relationships | Enterprise #5; DG2 declared source semantics |
| Cross-surface coverage | Some agent mutation paths cannot be intercepted; a positive check may ignore unmodeled decisions | Core DG1/CI1 validation, evidence limits |
| Process outcomes/work products | Process conformance demands more than showing code controls | Licensed 42020 normative review + customer's process owner |
| Full vs tailored conformance | Conformance targets and tailoring need explicit evidence; no generic 'ISO-certified Mneme' claim | Standards specialist/legal review |
| Evaluation quality | Protection-tier percentage is not semantic decision coverage or a 42030 architecture evaluation | Independent oracle, audit metric disclosure |
| Version drift | P42020 revision could modify terminology or activity scope | Quarterly official-source watch, no speculative roadmap changes |
| Buyer pull | Good conceptual fit does not prove procurement priority | 2–3 CTO/enterprise architecture/platform buyers |

## 8. M2 disposition and roadmap controls

**Research milestone completed here:** a six-process mapping, focused Clause 6 activity crosswalk, explicit Core/Enterprise ownership, candidate workflow/evidence packet, gap register, public-version pin, and qualified GO/DEFER decision. Documentation-only; no code, migration, test run or implementation. PR is for review, not auto-merge.

**Still open under #715, separate from M2:** normative `shall`-level requirements and Clause 4 tailoring assessment; real design-partner approval/evidence experiment; buyer procurement signal; possible read-only export prototype *only after* demand. P42020 revision text cannot be used as an approved requirement until published/authorized.

**Scheduled watch (outside GitHub):** quarterly check of official IEEE P42020 and ISO standard status. Alert on substantive changes (revised PAR/scope, balloting, publication, replacement, implications to Mneme). No automatic GitHub modifications.

### Suggested buyer qualification

Ask architects/platform leaders: **Would an export showing which approved architecture directive governed a specific software change, what was actually checked, and what remains unverified help your governance review or procurement process?** Follow with whether 42020 alignment is a real requirement, where approvals are recorded, and which human role must sign off.

**Roadmap recommendation:** Maintain **P2 research**; promote to **P1 only with an evidence-backed pilot requirement**. Do not displace the design-partner wedge, independent validation, DG1/DG2 reliability or CI evidence work.

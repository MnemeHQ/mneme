# DG1B2 waiver evidence packet (2026-11-10)

> **Status: evidence record. The DG1B2 evidence gate is accepted as satisfied
> by the owner (2026-11-10).** This packet records the qualifying positive
> case and hard negatives required by the
> [Data Engine #36](https://github.com/MnemeHQ/mneme-data-engine/issues/36)
> waiver protocol, as candidate evidence for DG1B2 under
> [ADR-031](../adr/ADR-031-decision-governance-semantics.md) §12, tracker
> [#497](https://github.com/MnemeHQ/mneme/issues/497).
> It allows a DG1B2 behavioral charter to be **requested**. It authorizes no
> schema change, waiver implementation, enforcement change, freeze amendment
> or release. No external maintainer was contacted; all evidence is from
> public records.

## 0. Summary

| Item | Classification | Role |
|---|---|---|
| CNCF Governing Board licence exception: picolibc for Hyperlight | **confirmed waiver-like** | qualifying positive |
| DfE CSP ADR-0028 analytics-domain carve-out | applicability (scope defined in the decision) | **primary hard negative** |
| CNCF registry: Chart.js (MIT) `allowlisted` | applicability (policy-defined allowlist) | secondary negative |
| CNCF registry: Grafana k6 for the OpenTelemetry Demo, `not-eligible` | refused request; rule stands | secondary negative |
| Kubernetes `gorilla/websocket` untagged pin (PR #129872) | strong candidate, **not qualifying** (approval implicit) | considered, rejected |

The Hyperlight case qualifies because authorization is an **explicit authority
operation**, not inferred from an ordinary change approval.

## 1. Qualifying positive: picolibc for Hyperlight

| ADR-031 §12 element | Evidence |
|---|---|
| Existing governing decision | CNCF Allowed Third-Party License Policy (Allowlist License Policy adopted by the Governing Board on 2018-05-01): [`policies-guidance/allowed-third-party-license-policy.md` at `4abf5951`](https://github.com/cncf/foundation/blob/4abf5951d08350014dafb6a1dcf1fe815eeca5d5/policies-guidance/allowed-third-party-license-policy.md), the version in force on the approval date. Components that are not Apache-2.0 and do not satisfy the allowlist "remain subject to review and exception approval by the Governing Board". Authority: the CNCF charter permits the Governing Board to approve alternative licences. |
| Explicit, independent authorization | Formal public resolution, [`cncf/governing-board` `minutes-and-email-votes/2026/2026-04-22_email_vote.md`](https://github.com/cncf/governing-board/blob/49a5617568bfb0e66cb98c0b81786a26299ba866/minutes-and-email-votes/2026/2026-04-22_email_vote.md): "RESOLVED, the Governing Board hereby APPROVES the recommended exception subject to the scope and restrictions…", after a unanimous CNCF Legal Committee recommendation. |
| Requester distinct from approver | Requested by a Hyperlight maintainer in [cncf/foundation#1117](https://github.com/cncf/foundation/issues/1117) (opened 2025-08-28); reviewed by CNCF staff and the Legal Committee; approved by the Governing Board; announced on #1117 ([comment 4306825158](https://github.com/cncf/foundation/issues/1117#issuecomment-4306825158), 2026-04-23). |
| Named scope | Hyperlight only; picolibc files under BSD-3-Clause, BSD-2-Clause, MIT, BSL-1.0, NCSA, Public Domain / CC0-1.0 only; GPL/AGPL files present upstream must never enter the Hyperlight build or be retrieved by end users (sparse checkout or a downstream fork). |
| Original decision remains authoritative | The policy is unchanged by the exception and continues to govern every other project and dependency. |
| Independent exception record and lifecycle | CNCF exceptions registry, [`license-exceptions/exceptions.json`](https://github.com/cncf/foundation/blob/4960dc90f44411f1ff09ad1d573fba3508f6c6c4/license-exceptions/exceptions.json) (stated source of truth): id `exc-2026-04-23-001`, status `approved`, approved 2026-04-22, with its own scope text and results link. Registry statuses include `approved`, `allowlisted`, `apache-2.0`, `denied` and `not-eligible`. |
| Approval provenance | request issue → Legal Committee review and questions → Governing Board resolution → registry record, all public and dated. |
| Optional time bound, `as_of` | **Not present.** The exception is scope-bound with an explicit obligation; effective from 2026-04-22. ADR-031 §12 makes a time bound optional; §13 expiry fixtures still need a separate time-bound example. |

### Distinctions to carry into any DG1B2 fixture or charter

1. **Source-version pin is not `decision_version_id`.** `4abf5951` pins the
   CNCF policy text in its own repository. It is not a Mneme canonical
   `decision_version_id`. A DG1B2 fixture modelled on this case must create an
   explicit Mneme decision and version for the governing rule and bind the
   waiver to that version; the external SHA is provenance only.
2. **Exception-authority pattern, not a licensing engine.** The CNCF rule
   governs dependency selection and build composition, primarily for
   licensing reasons. That is architecture-relevant, but this case validates
   the **exception-authority pattern** (explicit authority, scope, independent
   record, unchanged governing decision). It does not motivate a Mneme
   licensing-policy engine or licence-specific semantics.

## 2. Hard negatives

### Primary: DfE CSP ADR-0028 (scope defined in the decision)

- Source: [`DFE-Digital/early-years-foundation-recovery` `adr/0028-content-security-policy-hardening.md` at `ef9991ee`](https://github.com/DFE-Digital/early-years-foundation-recovery/blob/ef9991eed605fcdb8d8b1364420805f9ca52664c/adr/0028-content-security-policy-hardening.md) (Status: accepted).
- What looks like an exception: "domain-scoped collection exceptions" allowing `https://*.google-analytics.com` and `https://*.clarity.ms` in `connect-src` and `img-src`, against an ITHC recommendation to prefer exact host allow-lists.
- Why it is not a waiver: the carve-out is part of the accepted decision's own definition. There is no separate authority act, no record bound to an existing decision version and no separate lifecycle. Under ADR-031 §4 it is **decision applicability / scope**.

### Secondary

- **Chart.js (MIT), CNCF registry `exc-2019-11-01-001`, status `allowlisted`, scope "See Allowlist Policy requirements":** covered by the policy's own allowlist; no exception exists or is needed → applicability.
- **Grafana k6 (AGPL-3.0-only) for the OpenTelemetry Demo, `exc-2026-08-19-001`, status `not-eligible`** ([cncf/foundation#1482](https://github.com/cncf/foundation/issues/1482)): an exception request was refused. A request does not itself confer authority; the rule stands.

## 3. Considered and not qualifying

| Candidate | Why not |
|---|---|
| Kubernetes `gorilla/websocket` untagged pin (PR #129872; dependency policy `sig-architecture/vendor.md`) | Authorized approver (liggitt, `dep-approvers`) and an explicit completion condition ("When we get a 1.5.4 tag…"), but no contemporaneous statement recognizing an exception to the tagged-version rule; approval embedded in change review. ADR-031 §12 requires an explicit authority operation. No tracking issue found. |
| `frkim/foundry-demo` ADR-0003 (OIDC exception with expiry) | Waiver-shaped, but single contributor, self-merged, no review: self-approved. |
| `seahal/umaxica-apps-cosmos-governance` withdrawn exception | Single human contributor; no distinct approver. |
| `counterfact/api-simulator` facade dependency rule | Scope rule (applicability), not an exception. |

Observation: public explicit waivers are rare because most organizational
exceptions live in private systems, open-source maintainers usually own both
the rule and the exception, and large projects often approve exceptions
implicitly in review. Formal public waivers appear where legal accountability
requires them (licensing). A future DG1B2 design should treat implicit
approvals as evidence a human may turn into a waiver, never as a waiver.

## 4. What a DG1B2 charter must cover (from this evidence and ADR-031 §12)

Exact decision-version targeting; explicit authority distinct from the
requester; defined scope; independent lifecycle and provenance; optional
expiry evaluated only at `GovernanceContext.as_of`; fail-closed handling of
invalid, expired, out-of-scope or unauthorized waivers; protection against
agent self-authorization (no producer, MCP, discovery or agent path creates a
waiver); and a preserved distinction between waivers, applicability and
supersession, with the hard negatives above as fixtures.

## 5. Non-claims

This packet does not implement waivers, define a schema, change enforcement or
authorize a charter, freeze amendment or release. It does not claim DG1B2,
DG1F, DG1G or DG1 completion. Source pins are the revisions read on
2026-11-10; the Governing Board resolution and registry are public records of
the CNCF, not Mneme authority.

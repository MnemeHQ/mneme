---
id: ADR-016
title: "Site Governance Transfer to MnemeHQ/mnemehq-site"
status: accepted
priority: normal
date: 2026-07-27
scope: repo.site_transfer
supersedes:
  - ADR-003
  - ADR-006
  - ADR-007
  - ADR-008
  - ADR-011
  - ADR-012
  - ADR-015
---

# ADR-016: Site Governance Transfer to MnemeHQ/mnemehq-site

**Status:** Accepted
**Date:** 2026-07-27
**Deciders:** Theo Valmis

---

## Context

The Mneme marketing site (mnemehq.com) and its deployment tooling were extracted from this
repository (MnemeHQ/mneme) into a dedicated public repository, MnemeHQ/mnemehq-site. The
production cutover has completed: mnemehq-site now owns production deployment of mnemehq.com, and
a merged PR in that repository established `PUBLISHING.md` as the canonical, current source of
publishing and deployment governance.

Seven ADRs in this repository governed the website while it lived here:

- ADR-003 (site.publishing)
- ADR-006 (site.insights_seo)
- ADR-007 (site.og_images)
- ADR-008 (site.persona_pages)
- ADR-011 (site.knowledge_graph)
- ADR-012 (site.conceptual_authority)
- ADR-015 (site.insights_seo.report_titles)

Those decisions now describe governance for content and tooling that no longer lives in this
repository. This ADR records the transfer of ownership and supersedes those seven ADRs so the
compiled active set stops asserting website publishing governance from the core repository. It
does not delete their historical record.

## Decision

1. **Ownership transferred.** Source and deployment ownership of mnemehq.com has transferred from
   MnemeHQ/mneme to MnemeHQ/mnemehq-site.

2. **Canonical current governance.** `MnemeHQ/mnemehq-site/PUBLISHING.md` is the single canonical
   source of current publishing and deployment governance for mnemehq.com. This ADR does not
   reproduce its contents.

3. **Historical records retained.** ADR-003, ADR-006, ADR-007, ADR-008, ADR-011, ADR-012, and
   ADR-015 remain in this repository under `docs/adr/` as immutable historical decision records.
   They are marked `superseded` by this ADR and keep their original titles, dates, priorities,
   scopes, and bodies. This ADR does not reproduce their contents.

4. **No competing ADR corpus in the website repository.** MnemeHQ/mnemehq-site intentionally does
   not create its own `docs/adr/` ADR corpus. Its continuing publishing governance is expressed
   as `PUBLISHING.md` together with the CI validators already present in that repository. The
   Mneme ADR compiler and its dogfooded enforcement remain a core-repository concern.

5. **Core no longer owns active website governance.** After this ADR, the compiled active ADR set
   in this repository contains no active website publishing governance. Core governance now
   covers only the product, repository-boundary, brand, automation, and positioning scopes.

6. **Rollback infrastructure retained temporarily.** The core `site/**` tree, the deployment
   scripts (`scripts/deploy_site.py` and its helpers), the disabled `deploy-site.yml` workflow,
   and the `site-deployed` tag remain in this repository solely as rollback infrastructure for
   the cutover. They are not active governance and are not the deployment path in use.

7. **Rollback-retention window.** The rollback infrastructure is retained until BOTH of the
   following conditions are met, whichever takes longer:
   - at least 14 days have elapsed since the production cutover; and
   - at least 10 successful automatic (push- or schedule-triggered) deployments have completed
     from MnemeHQ/mnemehq-site.

8. **Retirement is a separate change.** Retiring the rollback infrastructure (removing the core
   `site/**`, the deployment scripts, the disabled workflow, and the `site-deployed` tag)
   requires a separate structural PR with its own validation. It is out of scope for this ADR.

9. **Governance-only change.** This ADR changes governance ownership only. It does not change
   runtime, CLI, enforcement, package, or deployment behavior. No product code, test, workflow
   state, tag, or dependency changes as part of recording this decision.

## Consequences

- The seven superseded ADRs drop out of the compiled active constraint set. The core enforcement
  memory (`.mneme/project_memory.json`) is aligned in the same governance PR so it no longer
  carries them as active decisions.
- Contributors to the website look to `MnemeHQ/mnemehq-site/PUBLISHING.md` for current rules, and
  to the superseded ADRs here only for historical rationale.
- Rollback remains possible for the retention window: the core deploy workflow can be re-enabled
  and the retained `site/**` re-deployed against the `site-deployed` tag if required.

## Related

- ADR-002: Repository Boundary for Internal Operational Tooling
- ADR-003, ADR-006, ADR-007, ADR-008, ADR-011, ADR-012, ADR-015 (superseded by this ADR)
- MnemeHQ/mnemehq-site `PUBLISHING.md` (canonical current publishing governance)

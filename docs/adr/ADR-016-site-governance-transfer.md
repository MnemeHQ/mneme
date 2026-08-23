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
**Amended:** 2026-07-27 (rollback retirement gate — see Decision §7–§8 and the Amendment note)
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

**Governance coverage note.** The transferred ownership covers all mnemehq.com website content and
pages - including the insights listing and related insight pages, whose presentation and SEO
governance previously lived in the superseded site.insights_seo, site.persona_pages, and
site.insights_seo.report_titles decisions. Any change to a website page of mnemehq.com is governed
in MnemeHQ/mnemehq-site (see PUBLISHING.md there); this repository no longer owns or reviews such
changes.
**Amendment (2026-07-27).** This ADR is amended on the day it was accepted to replace its original
rollback-retention window — which required BOTH at least 14 days elapsed since cutover AND at least
10 successful automatic deployments from MnemeHQ/mnemehq-site — with a proportionate,
evidence-based retirement gate. The repository owner has explicitly decided the old threshold is
unnecessarily conservative for this cutover. Counting automatic deployments proved a poor proxy for
cutover safety here: the deployment path's health was already established by a full production
cutover *and* a real-content push deployment, so waiting an arbitrary 14 days and accumulating ten
mostly no-op scheduled deployments would add calendar delay without adding evidence. The amended
gate (Decision §7) keys retirement to the facts that actually demonstrate a safe, single-owner
deployment path. See Decision §7–§8. This amendment changes governance only; it asserts no product,
runtime, CLI, enforcement, package, or deployment behavior change.

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

7. **Rollback-retention gate (amended 2026-07-27).** The original retention window in this ADR
   required BOTH at least 14 days elapsed since cutover AND at least 10 successful automatic
   (push- or schedule-triggered) deployments from MnemeHQ/mnemehq-site. The repository owner has
   explicitly decided to replace that threshold: deployment quantity was a poor proxy for cutover
   safety in this case, because the path's health was already proven by the cutover plus a
   real-content push deployment, and ten scheduled/no-op deployments over fourteen days would add
   only delay. The rollback infrastructure is instead retained only until ALL of the following
   proportionate conditions are met:

   1. The production cutover completed successfully.
   2. At least one successful push-triggered deployment containing real production content
      completed from MnemeHQ/mnemehq-site.
   3. The nine articles in that deployment were individually validated.
   4. Homepage, sitemap and deterministic production-page checks passed.
   5. `site-deployed` advanced consistently.
   6. No unresolved deployment failure or verification issue exists.
   7. cPanel backup availability is confirmed.
   8. The dedicated website repository and deployment path remain healthy.

8. **Gate satisfied; retirement authorised as a separate structural PR.** As of 2026-07-27 the
   eight-condition gate in §7 is satisfied:
   - the production cutover succeeded (MnemeHQ/mnemehq-site Actions run 30202468065, event
     `workflow_dispatch`, conclusion success, head 736a761, completed 2026-07-26T13:03Z);
   - a real-content push deployment succeeded (run 30312953090, event `push`, conclusion success,
     head aec909c8, completed 2026-07-27T23:10Z), publishing nine articles that were each
     individually validated;
   - the production homepage returns HTTP 200, and the sitemap returns HTTP 200 and parses (258
     URLs at audit) with sampled production pages returning HTTP 200;
   - the MnemeHQ/mnemehq-site `site-deployed` tag advanced to the deployed website commit and
     tracks it consistently;
   - cPanel already hosts the live production site and the owner confirms cPanel backups are
     available;
   - no unresolved deployment failure, retry, or verification issue exists, and the dedicated
     website repository and deployment path remain healthy.

   Because the gate is met, retirement of the core rollback infrastructure — the core `site/**`
   tree, `scripts/deploy_site.py` and its proven website-only helper closure, the disabled
   `deploy-site.yml` workflow, the `deploy_001` core rollback memory rule, and (as a post-merge
   repository operation) the core `site-deployed` tag — is authorised to proceed immediately. It
   must still land as a SEPARATE structural PR with its own validation, distinct from this
   governance amendment; the two changes are not combined. This ADR is not deleted by that
   retirement: it remains in `docs/adr/` as the historical transfer and retirement decision.

9. **Governance-only change.** This ADR changes governance ownership only. It does not change
   runtime, CLI, enforcement, package, or deployment behavior. No product code, test, workflow
   state, tag, or dependency changes as part of recording this decision.

## Consequences

- The seven superseded ADRs drop out of the compiled active constraint set. The core enforcement
  memory (`.mneme/project_memory.json`) is aligned in the same governance PR so it no longer
  carries them as active decisions.
- Contributors to the website look to `MnemeHQ/mnemehq-site/PUBLISHING.md` for current rules, and
  to the superseded ADRs here only for historical rationale.
- The rollback-retention gate (§7, as amended 2026-07-27) is satisfied, so the retained core
  rollback infrastructure is authorised for retirement via a separate structural PR. Until that PR
  merges, rollback remains mechanically possible — the disabled core deploy workflow could be
  re-enabled and the retained `site/**` re-deployed against the core `site-deployed` tag — but it
  is no longer gated on the withdrawn 14-day / 10-deployment threshold.

## Related

- ADR-002: Repository Boundary for Internal Operational Tooling
- ADR-003, ADR-006, ADR-007, ADR-008, ADR-011, ADR-012, ADR-015 (superseded by this ADR)
- MnemeHQ/mnemehq-site `PUBLISHING.md` (canonical current publishing governance)

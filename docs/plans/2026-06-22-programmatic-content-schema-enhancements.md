# Programmatic Content Schema + Coverage Enhancements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Lift schema coverage and content depth on mnemehq.com's programmatic cohorts, prioritising the fastest-rising and highest-commercial-value pages, so they earn FAQ rich-results and AI-citation surface.

**Architecture:** The site is hand-authored static HTML under `site/`, deployed to cPanel by `scripts/deploy_site.py` (auto-triggered on push to `main` via `.github/workflows/deploy-site.yml`, delta upload + Cloudflare purge + IndexNow). There is no SSG and no shared schema helper; each page embeds its own `<script type="application/ld+json">` `@graph`. Quality is enforced by per-cohort validators (`scripts/check_insights.py`, `check_compare.py`, `check_concepts.py`) that parse JSON-LD via a shared `jsonld_blocks()` pattern. This plan extends that validator-first discipline: for each enhancement we add a hard-error check that fails on the current page, then add the schema/content to make it pass.

**Tech Stack:** Static HTML + JSON-LD (schema.org), Python 3.12 validators (stdlib only: `json`, `re`, `pathlib`), GitHub Actions deploy.

**Repo:** `C:\dev\mneme` (github.com/mnemeHQ/mneme). NOT the cannabisdeals worktree this plan was authored from.

**Branch discipline:** Do all work on `feat/programmatic-schema-enhancements` (or one branch per phase). Merging to `main` triggers an immediate live deploy, so every phase must pass its validator before the PR merges. One phase = one PR.

---

## Scope and priority order

Ordered by ROI from the content audit (2026-06-22):

| Phase | Work | Pages | Why first |
|-------|------|-------|-----------|
| 1 | Add **FAQPage** to `/supported-languages/` sub-pages | 6 + hub | Fastest-rising cohort (spring-boot 0 to 55 impressions WoW); indexing now; cheap schema add |
| 2 | Upgrade `/for/` personas to compare-standard (**Article + FAQPage**) | 3 | Decision-maker / commercial pages; currently only WebPage + Breadcrumb |
| 3 | Bring thin pages to cohort parity (depth + schema) | 2 | `compare/google-antigravity-vs-mneme`, `concepts/antigravity-governance` are ~1/3 peer depth |
| 4 | **Regulated-industries vertical landing pages** (net-new) | ~3 | Highest commercial value; needs its own content brief (scoped below, separate plan) |
| 5 | **`ops_trends_v` to `/compare/` target pipeline** (net-new, cross-repo) | n/a | Systematise the winning cohort; needs its own brief (scoped below, separate plan) |

Phases 1 to 3 are fully specified as bite-sized tasks below. Phases 4 and 5 are net-new builds that require their own design pass; they are scoped at the end as briefs, not fabricated task-by-task.

---

## Phase 1: FAQPage on /supported-languages/ sub-pages

Each sub-page already emits `BreadcrumbList + TechArticle` inside one `@graph`. We add a third `FAQPage` node. The six sub-pages are:
`fastapi-governance`, `javascript-governance`, `python-governance`, `spring-boot-governance`, `terraform-governance`, `typescript-governance`.

### Task 1.1: Create the supported-languages validator (failing)

**Files:**
- Create: `scripts/check_supported_languages.py`

**Step 1: Write the validator, modelled on `check_insights.py`**

Reuse its `jsonld_blocks()` helper (copy the function; stdlib only). The check iterates every `site/supported-languages/<slug>/index.html` (exclude the hub `index.html`) and asserts, as hard errors:
- a `BreadcrumbList` node exists (already true)
- a `TechArticle` node exists with a non-empty `headline` and `url` == canonical (already true)
- a `FAQPage` node exists with `mainEntity` containing >= 3 `Question` items, each with a non-empty `acceptedAnswer.text`  ← this is the new requirement

```python
#!/usr/bin/env python3
"""Validate /supported-languages/<slug>/ pages carry Breadcrumb + TechArticle + FAQPage."""
from __future__ import annotations
import json, re, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COHORT_DIR = REPO_ROOT / "site" / "supported-languages"
SITE_BASE = "https://mnemehq.com"

def jsonld_blocks(html: str) -> list:
    out = []
    for m in re.finditer(r'<script\s+type="application/ld\+json">(.*?)</script>', html, re.DOTALL):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        graph = data.get("@graph", [data]) if isinstance(data, dict) else [data]
        out.extend(n for n in graph if isinstance(n, dict))
    return out

def slugs() -> list[str]:
    return [c.name for c in sorted(COHORT_DIR.iterdir())
            if c.is_dir() and (c / "index.html").exists()]

def main() -> int:
    errors = []
    for slug in slugs():
        html = (COHORT_DIR / slug / "index.html").read_text(encoding="utf-8")
        nodes = jsonld_blocks(html)
        types = {n.get("@type") for n in nodes}
        if "BreadcrumbList" not in types:
            errors.append(f"{slug}: BreadcrumbList JSON-LD missing")
        if "TechArticle" not in types:
            errors.append(f"{slug}: TechArticle JSON-LD missing")
        faq = next((n for n in nodes if n.get("@type") == "FAQPage"), None)
        if faq is None:
            errors.append(f"{slug}: FAQPage JSON-LD missing")
        else:
            q = [x for x in faq.get("mainEntity", []) if x.get("@type") == "Question"]
            if len(q) < 3:
                errors.append(f"{slug}: FAQPage has {len(q)} questions, need >= 3")
            for x in q:
                if not (x.get("acceptedAnswer") or {}).get("text", "").strip():
                    errors.append(f"{slug}: a FAQ Question has an empty acceptedAnswer.text")
    for e in errors:
        print(f"ERROR -- {e}")
    print(f"\n{len(slugs())} pages checked, {len(errors)} errors")
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Run it to verify it fails (all 6 pages lack FAQPage)**

Run: `python scripts/check_supported_languages.py`
Expected: FAIL, 6 lines `ERROR -- <slug>: FAQPage JSON-LD missing`, exit 1.

**Step 3: Commit**

```bash
git add scripts/check_supported_languages.py
git commit -m "test(seo): add supported-languages FAQPage validator (currently failing)"
```

### Task 1.2: Add FAQPage to spring-boot-governance (worked example)

**Files:**
- Modify: `site/supported-languages/spring-boot-governance/index.html` (the `@graph` ends at the `TechArticle` object, line ~51, before the closing `]` of `@graph` on ~53)

**Step 1: Insert a FAQPage node** as the last element of the existing `@graph` array. Add a comma after the `TechArticle` closing `}` (line ~51), then:

```json
,
      {
        "@type": "FAQPage",
        "mainEntity": [
          {
            "@type": "Question",
            "name": "How does Mneme HQ govern AI-generated Spring Boot code?",
            "acceptedAnswer": {"@type": "Answer", "text": "Mneme HQ enforces repo-native architecture rules before AI-written code reaches review: it preserves controller, service, repository, and domain boundaries, restricts which Spring Boot starters and dependencies may be introduced, and flags violations of transaction and security policy as the agent edits the project."}
          },
          {
            "@type": "Question",
            "name": "Does it stop AI agents from breaking layered architecture in Java services?",
            "acceptedAnswer": {"@type": "Answer", "text": "Yes. Layer boundaries are expressed as deterministic rules, so an agent cannot have a controller call a repository directly, leak persistence types into the web layer, or move business logic out of the service layer without the change being caught before merge."}
          },
          {
            "@type": "Question",
            "name": "Can it enforce approved starters and dependency policy?",
            "acceptedAnswer": {"@type": "Answer", "text": "Yes. You declare which starters, libraries, and versions are permitted, and Mneme HQ blocks an AI agent from pulling in unapproved or duplicate dependencies, keeping the build reproducible and the dependency surface governed."}
          },
          {
            "@type": "Question",
            "name": "How is this different from a linter or static analysis?",
            "acceptedAnswer": {"@type": "Answer", "text": "Linters check style and known anti-patterns on code that already exists. Mneme HQ governs intent and architecture continuously while the agent works, so structural and security decisions are enforced before review rather than discovered after."}
          }
        ]
      }
```

(Answers are grounded in this page's stated topic: controller/service/repository/domain boundaries, approved starters, transaction boundaries, security/actuator policy. Keep answers factual; do not claim capabilities the product page does not.)

**Step 2: Run the validator (spring-boot now passes, 5 still fail)**

Run: `python scripts/check_supported_languages.py`
Expected: 5 errors remain (the other slugs); `spring-boot-governance` no longer listed.

**Step 3: Validate the JSON is well-formed**

Run: `python -c "import json,re,pathlib; h=pathlib.Path('site/supported-languages/spring-boot-governance/index.html').read_text(encoding='utf-8'); [json.loads(m) for m in re.findall(r'<script type=\"application/ld\+json\">(.*?)</script>', h, re.DOTALL)]; print('JSON-LD OK')"`
Expected: `JSON-LD OK` (no JSONDecodeError).

**Step 4: Commit**

```bash
git add site/supported-languages/spring-boot-governance/index.html
git commit -m "feat(seo): add FAQPage schema to spring-boot governance page"
```

### Tasks 1.3 to 1.7: Repeat for the other five sub-pages

For each of `fastapi-governance`, `javascript-governance`, `python-governance`, `terraform-governance`, `typescript-governance`: repeat Task 1.2's steps, writing 4 Q&A grounded in that page's own subject matter (read the page's `<meta name="description">` and `TechArticle.description` first, then write answers that match it). Do NOT copy the Spring Boot answers verbatim; the questions should reflect each language/framework's real governance concerns (e.g. Terraform: module boundaries, provider/version pinning, state and policy; FastAPI: router/service/schema boundaries, dependency-injection and Pydantic model policy).

Run `python scripts/check_supported_languages.py` after each; commit per page. After the sixth page the validator must exit 0.

### Task 1.8: Wire the validator into CI

**Files:**
- Modify: `.github/workflows/deploy-site.yml` (or the existing checks workflow if validators run pre-deploy there). Find where `check_insights.py` / `check_compare.py` are invoked and add `python scripts/check_supported_languages.py` alongside them.

**Step 1:** Locate the current validator invocation.

Run: `grep -rn "check_compare\|check_insights\|check_concepts" .github/`

**Step 2:** Add the new check next to the others (same step/job).

**Step 3:** Run the full local check sweep to confirm green.

Run: `python scripts/check_supported_languages.py && echo OK`
Expected: `... 0 errors` then `OK`.

**Step 4: Commit + open PR**

```bash
git add .github/
git commit -m "ci(seo): enforce supported-languages FAQPage in deploy checks"
```

Open PR `feat/programmatic-schema-enhancements` to `main`. Merge only when the validator is green. Merge auto-deploys; confirm one URL renders FAQ in Google's Rich Results Test post-deploy.

---

## Phase 2: Upgrade /for/ personas to compare-standard

Each persona page (`cto`, `platform`, `principal-engineer`) currently emits `BreadcrumbList + WebPage` (for/cto: lines ~260-280). The gold standard is the `/compare/` graph (`site/compare/aider/index.html` lines ~173-226): `BreadcrumbList + Article + FAQPage`. We replace `WebPage` with `Article` and add `FAQPage`.

### Task 2.1: Create the /for/ validator (failing)

**Files:**
- Create: `scripts/check_for.py`

**Step 1:** Clone the Phase-1 validator structure, pointing `COHORT_DIR` at `site/for`, excluding the hub `index.html`. Required nodes (hard errors): `BreadcrumbList`; `Article` with non-empty `headline`, `datePublished`, `dateModified`, and `url` == canonical; `FAQPage` with >= 3 questions (same Question/answer checks as Phase 1).

**Step 2: Run to verify it fails**

Run: `python scripts/check_for.py`
Expected: FAIL: each persona reports `Article JSON-LD missing` and `FAQPage JSON-LD missing` (currently `WebPage`, not `Article`).

**Step 3: Commit**

```bash
git add scripts/check_for.py
git commit -m "test(seo): add /for/ persona Article+FAQPage validator (failing)"
```

### Task 2.2: Upgrade for/cto (worked example)

**Files:**
- Modify: `site/for/cto/index.html` (JSON-LD `@graph`, lines ~260-280)

**Step 1: Change the `WebPage` node (line ~273) to `Article`** and add the fields the compare standard carries. Keep the existing `author`/`publisher`. Result:

```json
{
  "@type": "Article",
  "headline": "Architectural Governance for CTOs and VP Engineering",
  "description": "AI increases code throughput; review capacity does not. Mneme HQ enforces architectural governance before AI-generated code reaches review.",
  "url": "https://mnemehq.com/for/cto/",
  "datePublished": "2026-05-10",
  "dateModified": "2026-06-22",
  "author": {"@type": "Person", "name": "Theo Valmis", "url": "https://mnemehq.com/founder/"},
  "publisher": {"@type": "Organization", "name": "Mneme HQ", "url": "https://mnemehq.com/", "logo": {"@type": "ImageObject", "url": "https://mnemehq.com/logo-v2.png"}},
  "image": "https://mnemehq.com/for/cto/og.png",
  "mainEntityOfPage": "https://mnemehq.com/for/cto/"
}
```

(Keep `datePublished` as the page's real first-publish date if known; the current page has none, so `2026-05-10` from the audit is used. Set `dateModified` to the edit date.)

**Step 2: Add a `FAQPage` node** as the last `@graph` element (comma after the Article `}`), with 4 Q&A grounded in the CTO page's actual argument (throughput vs review capacity, governance before review, risk/audit posture for leadership). Example first question:

```json
{
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "Why do CTOs need architectural governance for AI coding agents?",
      "acceptedAnswer": {"@type": "Answer", "text": "AI raises the volume of code produced, but human review capacity is fixed. Without enforced architecture rules, structural and security decisions are made implicitly by agents and only caught (if at all) in overloaded review. Mneme HQ moves that enforcement before review, so throughput scales without surrendering architectural control."}
    }
    // + 3 more grounded Q&A
  ]
}
```

**Step 3: Run the validator (cto passes, two remain)**

Run: `python scripts/check_for.py`
Expected: `platform` and `principal-engineer` still fail; `cto` clean.

**Step 4: JSON-LD well-formedness check** (same one-liner pattern as Task 1.2 Step 3, path `site/for/cto/index.html`). Expected `JSON-LD OK`.

**Step 5: Commit**

```bash
git add site/for/cto/index.html
git commit -m "feat(seo): upgrade /for/cto to Article + FAQPage schema"
```

### Tasks 2.3 to 2.4: Repeat for platform and principal-engineer

Same upgrade, with headline/description/FAQ grounded in each persona page's own copy (read the page first). Run `python scripts/check_for.py` after each; commit per page; validator exits 0 after the third.

### Task 2.5: Wire check_for.py into CI

Same as Task 1.8: add `python scripts/check_for.py` to the deploy-checks step. Commit. PR (separate from Phase 1). Merge when green; verify in Rich Results Test post-deploy.

---

## Phase 3: Bring thin pages to cohort parity

Two recent newsjack pages are ~1/3 the depth of their cohort peers and may also be missing the full schema graph:
- `site/compare/google-antigravity-vs-mneme/index.html` (~495 words)
- `site/concepts/antigravity-governance/index.html` (~541 words; confirm path exists, it is newer than the cohort baseline)

### Task 3.1: Confirm current state against the cohort validators

**Step 1:** Run the existing validators to see whether these two pages already pass schema registration:

Run: `python scripts/check_compare.py` and `python scripts/check_concepts.py`
Record any errors for the two slugs (registration, hasPart, FAQPage, etc.).

**Step 2:** Measure depth. Compare visible word count of each thin page against two strong peers (e.g. `compare/aider`, `compare/cursor-rules`; `concepts/architectural-governance`). Target: ~1,200 words, matching peer section structure.

### Task 3.2: Expand compare/google-antigravity-vs-mneme

**Files:**
- Modify: `site/compare/google-antigravity-vs-mneme/index.html`

**Step 1:** Bring the body to peer parity: add the missing sections a strong `/compare/` page has (comparison table rows, decision matrix, "when to use which", related-concepts panel, internal links). Keep claims accurate to the product.

**Step 2:** Ensure the JSON-LD `@graph` matches the gold standard (`BreadcrumbList + Article + FAQPage`); add any missing node and >= 4 FAQ Q&A.

**Step 3:** Run `python scripts/check_compare.py` to 0 errors for this slug. Run the JSON-LD well-formedness one-liner. Commit.

### Task 3.3: Expand concepts/antigravity-governance

Same approach against `check_concepts.py` (concepts cohort standard is `BreadcrumbList + TechArticle + FAQPage + DefinedTerm`). Expand to ~1,200 words, ensure DefinedTerm + FAQPage present, validator green, commit.

### Task 3.4: PR

Open a Phase-3 PR. Merge when both cohort validators are green. Verify post-deploy.

---

## Phase 4 (separate plan required): Regulated-industries vertical landing pages

**Why:** GSC movers show buyer-intent queries stuck deep: `ai for regulated industries` (pos ~61), `llm testing regulated industries` (~45), `ai governance life sciences` (~60), `ai governance platforms for ml pipelines` (~46). These are ICP queries; the site ranks too deep to convert. Existing assets are editorial `/insights/` posts, not commercial vertical landing pages:
- `site/insights/ai-governance-for-regulated-industries/`
- `site/insights/ai-coding-agents-life-sciences-governance/`
- `site/insights/ai-coding-agents-financial-services-audit-trail/`

**Scope to brief separately (do NOT build from this plan):**
1. Decide cohort home: extend `/use-cases/` (already has SoftwareApplication + FAQPage hub) vs a new `/industries/` tree. Recommendation: a new `/industries/` tree (regulated-industries, life-sciences, financial-services) with vertical, commercial intent, cross-linking down to the supporting `/insights/` posts.
2. Build the first page (`/industries/regulated-industries/`) as the template: full compare-standard graph (`BreadcrumbList + Article + FAQPage`), comparison/decision content, CTA, OG image, sitemap + hub registration.
3. Write a `scripts/check_industries.py` validator mirroring Phases 1 and 2.
4. Register in `sitemap.xml`, add incoming internal links, add OG images.

This is a net-new content build (positioning, copy, design) and needs its own brainstorming + writing-plans pass. Flagged here as the highest-commercial-value follow-on.

## Phase 5 (separate plan required): ops_trends_v to /compare/ target pipeline

**Why:** `/compare/` is the highest-performing programmatic surface (the only cohort earning clicks). It is currently fed ad hoc. The trends layer already suggests comparison targets.

**Note on location:** the trends signal (`ops_trends_v`, `signals_daily`) lives in the cannabisdeals-data-platform repo / BigQuery, not in `C:\dev\mneme`. This phase is cross-repo and depends on the Bing ingestion fix (deliverable 1) to restore a third of the signal. Scope to brief separately:
1. Confirm which view surfaces comparison-intent terms for mnemehq (verify `ops_trends_v` vs a mneme-specific `mneme_trends` view; the cannabis `ops_trends_v` emits cannabis suggested types, so a mneme equivalent is needed).
2. Define the handoff: signal view to a ranked backlog of `/compare/<target>/` pages to author.
3. Decide build cadence (manual author-from-backlog first; templated generation only if volume justifies abandoning the hand-authored quality bar).

Flagged as systematisation work, lower urgency than Phases 1 to 3, and gated on the Bing fix.

---

## Execution notes

- **Deploy is automatic on merge to `main`.** Validate locally and in PR before merging each phase. After deploy, spot-check one new FAQ in Google's Rich Results Test and confirm the page returns HTTP 200 (the deploy script already verifies sitemap URLs).
- **No em dash** in any authored copy or schema text (project convention): use commas, colons, or restructure.
- **Do not fabricate product capabilities** in FAQ answers; ground each answer in the page's existing copy and the product's real behaviour.
- **Phases 1 to 3 are independent** and can ship as three separate PRs in priority order. Phase 1 first.

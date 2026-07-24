#!/usr/bin/env python3
"""
SEO + GEO baseline audit for site/ HTML pages.

Codifies the recommendations from the demo / compare / integrations
optimization passes into a runnable check. Each rule maps to one of
the gap categories the audit identified. Output is colored per-page
with PASS / WARN / FAIL counts and an overall summary.

Usage:
    python scripts/seo_check.py                 # audit all pages, exit 0
    python scripts/seo_check.py --mode strict   # exit 1 if any FAIL
    python scripts/seo_check.py --json          # machine-readable
    python scripts/seo_check.py --only DIR      # restrict to subdir(s)
    python scripts/seo_check.py --include-low   # also audit thin pages
                                                  (privacy, contact, etc.)

Rules (each is one of: required / recommended / optional):

  Head metadata
    - title tag, length 30..70                              required
    - meta description, length 50..170                      required
    - canonical URL                                         required
    - robots index,follow                                   recommended
    - og:title, og:description, og:image, og:url            required
    - twitter:card                                          recommended

  Structure
    - exactly one <h1>                                      required
    - >= 2 <h2>                                             recommended
    - body word count >= 500                                recommended
    - body word count >= 1200 (long-form pages)             optional / aspirational
    - at least one internal link in body                    required
    - at least one cross-page link to /insights/, /standards/,
      /integrations/, /compare/, or /use-cases/             recommended

  Internal linking pattern (sub-pages only)
    Every section sub-page (/insights/<x>/, /use-cases/<x>/,
    /compare/<x>/, /integrations/<x>/, /demo/<x>/) should link to:
      - its parent hub (e.g. /insights/)                    required
      - 2-4 related pages within the same section           recommended
      - one proof surface: /demo/, /benchmark/, or GitHub   required
    Hubs and root-level pages are exempt.

  JSON-LD structured data
    - BreadcrumbList present                                required (subpages)
    - WebPage / Article / SoftwareApplication present       required
    - author (Person) with url                              required
    - datePublished + dateModified                          required
    - FAQPage if visible <details class="faq-item"> exists  required (consistency)
    - HowTo if a "How to wire this up" / install/migration  recommended
      section exists

  Authority signals
    - visible byline with author + datePublished            recommended

  GEO / LLM citation surface
    - llms.txt entry referencing this URL                   recommended

The script is rule-driven so it can be extended without edits to its
core flow. To add a rule, append to RULES with a callable predicate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

REPO   = Path(__file__).resolve().parent.parent
SITE   = REPO / "site"
LLMS   = SITE / "llms.txt"

# Pages that intentionally don't get the full SEO treatment (legal,
# small utility pages). Suppressed unless --include-low is passed.
LOW_VALUE_PAGES = {
    "privacy/index.html",
    "contact/index.html",
    "404.html",
}

# OG-template files (rendered into PNGs via generate_og_images.py)
# are not real pages; skip them entirely.
def is_og_template(path: Path) -> bool:
    return path.name.startswith("og-")


# ── Severity ─────────────────────────────────────────────────────────────────

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"

COLOR = {
    PASS: "\033[32m",   # green
    WARN: "\033[33m",   # yellow
    FAIL: "\033[31m",   # red
    "RESET": "\033[0m",
    "DIM":   "\033[2m",
    "BOLD":  "\033[1m",
}


@dataclass
class Finding:
    severity: str
    rule: str
    detail: str = ""


@dataclass
class PageReport:
    rel_path: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def fails(self) -> int: return sum(1 for f in self.findings if f.severity == FAIL)
    @property
    def warns(self) -> int: return sum(1 for f in self.findings if f.severity == WARN)
    @property
    def passes(self) -> int: return sum(1 for f in self.findings if f.severity == PASS)


# ── Helpers ──────────────────────────────────────────────────────────────────

def strip_invisible(html: str) -> str:
    """Remove <script>, <style>, and HTML comments before counting words."""
    s = re.sub(r"<script\b.*?</script>", " ", html, flags=re.S | re.I)
    s = re.sub(r"<style\b.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
    return s


def visible_text(html: str) -> str:
    s = strip_invisible(html)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&\w+;", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def find_meta(html: str, attr: str, value: str) -> str | None:
    """Return the content of a meta tag matching attr=value. Handles both
    single- and double-quoted content correctly even when the content itself
    contains the other quote character."""
    pat = (
        rf'<meta[^>]*\b{attr}\s*=\s*["\']{re.escape(value)}["\'][^>]*\bcontent\s*='
        r'\s*(?:"([^"]*)"|\'([^\']*)\')'
    )
    m = re.search(pat, html, flags=re.I)
    if not m:
        return None
    return m.group(1) if m.group(1) is not None else m.group(2)


def has_link(html: str, rel: str) -> str | None:
    pat = (
        rf'<link[^>]*\brel\s*=\s*["\']{re.escape(rel)}["\'][^>]*\bhref\s*='
        r'\s*(?:"([^"]*)"|\'([^\']*)\')'
    )
    m = re.search(pat, html, flags=re.I)
    if not m:
        return None
    return m.group(1) if m.group(1) is not None else m.group(2)


def jsonld_blocks(html: str) -> list[dict]:
    out: list[dict] = []
    for m in re.finditer(r'<script\s+type=["\']application/ld\+json["\']\s*>(.*?)</script>', html, flags=re.S | re.I):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        nodes = []
        if isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                nodes.extend(data["@graph"])
            else:
                nodes.append(data)
        elif isinstance(data, list):
            nodes.extend(data)
        out.extend([n for n in nodes if isinstance(n, dict)])
    return out


def jsonld_types(blocks: list[dict]) -> set[str]:
    types: set[str] = set()
    for b in blocks:
        t = b.get("@type")
        if isinstance(t, str):
            types.add(t)
        elif isinstance(t, list):
            types.update(x for x in t if isinstance(x, str))
    return types


def body_inner(html: str) -> str:
    m = re.search(r"<body[^>]*>(.*)</body>", html, flags=re.S | re.I)
    return m.group(1) if m else html


def main_inner(html: str) -> str:
    """Best-effort: just the <main> region, falling back to body."""
    m = re.search(r"<main\b[^>]*>(.*?)</main>", html, flags=re.S | re.I)
    return m.group(1) if m else body_inner(html)


def llms_urls() -> set[str]:
    if not LLMS.exists():
        return set()
    text = LLMS.read_text(encoding="utf-8", errors="ignore")
    return set(re.findall(r"https://mnemehq\.com/[^\s)\"']*", text))


# ── Rules ────────────────────────────────────────────────────────────────────

# Each rule is (label, severity_on_fail, predicate). Predicate returns
# either True (pass), or a (severity, detail) tuple for non-pass.
RuleFn = Callable[[str, "PageContext"], "RuleResult"]
RuleResult = tuple[str, str]  # (severity, detail). PASS means no finding.


@dataclass
class PageContext:
    rel_path: str
    body: str
    main_body: str
    visible: str
    word_count: int
    head: str
    jsonld: list[dict]
    types: set[str]
    llms_urls: set[str]
    canonical: str | None


def page_url(rel_path: str) -> str:
    p = rel_path
    if p.endswith("/index.html"):
        p = p[: -len("index.html")]
    return f"https://mnemehq.com/{p}"


def rule_title(html: str, ctx: PageContext) -> RuleResult:
    m = re.search(r"<title[^>]*>([^<]*)</title>", html, flags=re.I)
    if not m:
        return FAIL, "missing <title>"
    title = m.group(1).strip()
    n = len(title)
    if n < 25:
        return WARN, f"title is {n} chars (target 30..70)"
    if n > 75:
        return WARN, f"title is {n} chars (target 30..70)"
    return PASS, ""


def rule_description(html: str, ctx: PageContext) -> RuleResult:
    desc = find_meta(html, "name", "description")
    if not desc:
        return FAIL, "missing meta description"
    n = len(desc)
    if n < 50:
        return WARN, f"description is {n} chars (target 50..170)"
    if n > 200:
        return WARN, f"description is {n} chars (target 50..170)"
    return PASS, ""


def rule_canonical(html: str, ctx: PageContext) -> RuleResult:
    href = has_link(html, "canonical")
    if not href:
        return FAIL, "missing rel=canonical"
    count = len(re.findall(r'<link\b[^>]*\brel\s*=\s*["\']canonical["\']', html, flags=re.I))
    if count > 1:
        return FAIL, f"{count} canonical tags (must be exactly 1)"
    return PASS, ""


def rule_robots(html: str, ctx: PageContext) -> RuleResult:
    val = find_meta(html, "name", "robots")
    if not val:
        return WARN, "no robots meta"
    if "noindex" in val.lower():
        return WARN, f"robots = {val}"
    return PASS, ""


def rule_og(html: str, ctx: PageContext) -> RuleResult:
    missing = [k for k in ("og:title", "og:description", "og:image", "og:url")
               if not find_meta(html, "property", k)]
    if missing:
        return FAIL, f"missing og tags: {', '.join(missing)}"
    return PASS, ""


def rule_twitter(html: str, ctx: PageContext) -> RuleResult:
    if not find_meta(html, "name", "twitter:card"):
        return WARN, "no twitter:card"
    return PASS, ""


def rule_h1(html: str, ctx: PageContext) -> RuleResult:
    n = len(re.findall(r"<h1\b", ctx.body, flags=re.I))
    if n == 0:
        return FAIL, "no <h1>"
    if n > 1:
        return WARN, f"{n} <h1> tags (should be 1)"
    return PASS, ""


def rule_h2(html: str, ctx: PageContext) -> RuleResult:
    n = len(re.findall(r"<h2\b", ctx.body, flags=re.I))
    if n < 2:
        return WARN, f"{n} <h2> (target ≥ 2)"
    return PASS, ""


def rule_word_count(html: str, ctx: PageContext) -> RuleResult:
    if ctx.word_count < 300:
        return FAIL, f"{ctx.word_count} words (target ≥ 500)"
    if ctx.word_count < 500:
        return WARN, f"{ctx.word_count} words (target ≥ 500)"
    return PASS, ""


def rule_internal_links(html: str, ctx: PageContext) -> RuleResult:
    # Internal hrefs that are not just the nav/footer links
    main = ctx.main_body
    # Strip nav region within main if present (breadcrumb etc are fine)
    hrefs = re.findall(r'<a\b[^>]*\bhref\s*=\s*["\'](/[^"\']*)["\']', main)
    # Filter out same-page anchors
    real = [h for h in hrefs if not h.startswith("#")]
    # Try to count cross-section links specifically
    cross = [h for h in real if any(h.startswith(p) for p in ("/insights/", "/standards/", "/integrations/", "/compare/", "/use-cases/", "/demo/", "/benchmark/", "/founder/", "/about/"))]
    if not real:
        return FAIL, "no internal links in <main>"
    if not cross:
        return WARN, "no cross-section links (/insights/, /standards/, etc.)"
    return PASS, ""


# Sections that have a section-hub at /<section>/index.html. Sub-pages
# inside these sections are subject to the parent-hub + related + proof
# linking pattern.
LINK_SECTIONS = ("insights", "use-cases", "compare", "integrations", "demo")

# Pages or URL prefixes that count as "proof" surfaces for the linking
# pattern: the demo, the benchmark methodology, and the public source.
PROOF_PATTERNS = ("/demo/", "/benchmark/", "github.com/mnemeHQ/mneme")


def rule_linking_pattern(html: str, ctx: PageContext) -> RuleResult:
    """Encodes the editorial linking rule:

        Every section sub-page should link to:
        1. its parent hub
        2. 2-6 related pages within the same section
        3. at least one proof surface (demo, benchmark, or GitHub repo)

    Section hubs and root-level pages are exempt.
    """
    rel = ctx.rel_path
    parts = rel.split("/")
    if len(parts) < 3:
        # Root-level page (e.g. index.html) or section hub
        # (e.g. insights/index.html). Rule doesn't apply.
        return PASS, ""
    section = parts[0]
    if section not in LINK_SECTIONS:
        return PASS, ""

    parent_hub = f"/{section}/"
    self_url = "/" + rel.removesuffix("index.html")

    # All anchor hrefs inside <main>
    main_hrefs = re.findall(
        r'<a\b[^>]*\bhref\s*=\s*["\']([^"\']*)["\']',
        ctx.main_body,
    )

    has_parent_hub = any(
        h == parent_hub or h.startswith(parent_hub + "#")
        for h in main_hrefs
    )

    # Count distinct related pages (siblings under the same section,
    # not self, not just the hub anchor)
    related: set[str] = set()
    for h in main_hrefs:
        if not h.startswith(parent_hub) or h == parent_hub:
            continue
        base = h.split("#")[0].split("?")[0]
        if base in (parent_hub, self_url):
            continue
        related.add(base)

    has_proof = any(
        any(pat in h for pat in PROOF_PATTERNS)
        for h in main_hrefs
    )

    # Adapt the lower bound to the section's published size: a section
    # with only two sub-pages cannot satisfy a strict 2-related minimum,
    # since each page has at most one sibling. Cap min_related at
    # (siblings_count) so the rule stays meaningful but achievable.
    section_dir = SITE / section
    siblings_count = sum(
        1
        for p in section_dir.glob("*/index.html")
        if str(p.relative_to(SITE)) != rel
    )
    min_related = min(2, siblings_count)

    issues: list[str] = []
    if not has_parent_hub:
        issues.append(f"missing parent-hub link to {parent_hub}")
    if len(related) < min_related:
        issues.append(f"{len(related)} related links in /{section}/ (target {min_related}-4)")
    elif len(related) > 6:
        issues.append(f"{len(related)} related links in /{section}/ (over the 2-4 target; risk of spammy mesh)")
    if not has_proof:
        issues.append("no proof link (/demo/, /benchmark/, or GitHub repo)")

    if issues:
        return WARN, "; ".join(issues)
    return PASS, ""


def rule_breadcrumb_html(html: str, ctx: PageContext) -> RuleResult:
    """The visible <ol class="breadcrumb"> parent links must match the page's URL hierarchy.

    For a page at /section/slug/, the parent hrefs must be exactly ["/" , "/section/"].
    Catches stray intermediate items (e.g. /concepts/ or /architecture/ inside an
    /insights/ article breadcrumb).

    Pages that don't use the ol.breadcrumb pattern are skipped — this rule only
    fires when the markup is present.
    """
    rel = ctx.rel_path
    parts = rel.split("/")

    # Home page or single-segment paths: no breadcrumb constraint
    if len(parts) <= 1:
        return PASS, ""

    # Build the expected parent hrefs list based on depth:
    #   section hub  (e.g. insights/index.html)         → ["/"]
    #   sub-page     (e.g. insights/foo/index.html)      → ["/", "/section/"]
    if len(parts) == 2:
        expected = ["/"]
    else:
        section = parts[0]
        expected = ["/", f"/{section}/"]

    m = re.search(r'<ol\s+class=["\']breadcrumb["\']>(.*?)</ol>', html, flags=re.S | re.I)
    if not m:
        return PASS, ""  # no ol.breadcrumb present; skip

    block = re.sub(r'<li[^>]*\baria-current\b[^>]*>.*?</li>', '', m.group(1), flags=re.S | re.I)
    actual = re.findall(r'<a\b[^>]*\bhref\s*=\s*["\']([^"\']*)["\']', block, flags=re.I)

    if actual != expected:
        return FAIL, f"breadcrumb parents {actual} != expected {expected}"
    return PASS, ""


def rule_jsonld_breadcrumb(html: str, ctx: PageContext) -> RuleResult:
    # Skip the home page — it doesn't need a breadcrumb.
    if ctx.rel_path == "index.html":
        return PASS, ""
    if "BreadcrumbList" not in ctx.types:
        return FAIL, "no BreadcrumbList JSON-LD"
    return PASS, ""


def rule_jsonld_main(html: str, ctx: PageContext) -> RuleResult:
    valid = {"WebPage", "Article", "TechArticle", "BlogPosting", "SoftwareApplication", "CollectionPage"}
    if not (ctx.types & valid):
        return FAIL, f"no main entity type ({sorted(valid)})"
    return PASS, ""


def rule_jsonld_author(html: str, ctx: PageContext) -> RuleResult:
    # Walk JSON-LD nodes; an Article / WebPage / TechArticle should declare author
    interesting = {"Article", "TechArticle", "BlogPosting", "WebPage"}
    has_target = any(_node_type(n) in interesting for n in ctx.jsonld)
    if not has_target:
        # Software-application-only pages don't need author
        return PASS, ""
    for n in ctx.jsonld:
        if _node_type(n) in interesting:
            author = n.get("author")
            if isinstance(author, dict) and author.get("@type") == "Person" and author.get("url"):
                return PASS, ""
    return WARN, "Article/WebPage missing author Person with url"


def rule_jsonld_dates(html: str, ctx: PageContext) -> RuleResult:
    interesting = {"Article", "TechArticle", "BlogPosting", "WebPage"}
    for n in ctx.jsonld:
        if _node_type(n) in interesting:
            if not n.get("datePublished"):
                return WARN, "Article/WebPage missing datePublished"
            if not n.get("dateModified"):
                return WARN, "Article/WebPage missing dateModified"
    return PASS, ""


def rule_faq_consistency(html: str, ctx: PageContext) -> RuleResult:
    # Treat any <details> + <summary> pair as a visible FAQ surface,
    # to match both the .faq-item pattern and the bare <details> pattern
    # used on older insights pages.
    has_visible_faq = (
        bool(re.search(r'<details\b', ctx.main_body, flags=re.I))
        and bool(re.search(r'<summary\b', ctx.main_body, flags=re.I))
    )
    has_faq_jsonld = "FAQPage" in ctx.types
    if has_visible_faq and not has_faq_jsonld:
        return FAIL, "visible <details> FAQ present but no FAQPage JSON-LD"
    if has_faq_jsonld and not has_visible_faq:
        return WARN, "FAQPage JSON-LD declared but no visible <details>/<summary> markup"
    return PASS, ""


def rule_byline(html: str, ctx: PageContext) -> RuleResult:
    # Skip pages where Article isn't the main type (e.g. SoftwareApplication-only).
    interesting = {"Article", "TechArticle", "BlogPosting"}
    if not (ctx.types & interesting):
        return PASS, ""
    has_byline = bool(re.search(r'class\s*=\s*"[^"]*\bbyline\b[^"]*"', ctx.body))
    has_datetime = bool(re.search(r'<time\b[^>]*\bdatetime\s*=', ctx.body))
    if not (has_byline and has_datetime):
        return WARN, "no visible byline with <time datetime=..>"
    return PASS, ""


def rule_llms_entry(html: str, ctx: PageContext) -> RuleResult:
    if not ctx.canonical:
        return PASS, ""
    if ctx.canonical not in ctx.llms_urls:
        return WARN, "no entry in llms.txt"
    return PASS, ""


# Class names that are universally OK to leave undefined: framework hooks,
# JS-toggled state classes, screen-reader/utility classes that may be styled
# only via attribute selectors or live in shared CSS we don't see here.
_CSS_CLASS_ALLOWLIST = {
    "active", "open", "hidden", "visible", "selected", "current",
    "sr-only", "noscript", "no-js",
}


def rule_css_class_hygiene(html: str, ctx: PageContext) -> RuleResult:
    """Flag HTML class names that are not defined in any inline <style> block.

    Catches typos like class="section" when only .section-wrap is defined —
    invisible to other SEO rules but breaks layout silently.
    """
    # Collect class selectors defined in inline <style> blocks.
    styles = re.findall(r"<style\b[^>]*>(.*?)</style>", html, flags=re.S | re.I)
    if not styles:
        return PASS, ""  # no inline CSS -> can't make claims
    style_text = "\n".join(styles)
    # Strip CSS comments to avoid false positives.
    style_text = re.sub(r"/\*.*?\*/", " ", style_text, flags=re.S)
    defined = set(re.findall(r"\.([A-Za-z_][\w-]*)", style_text))
    if not defined:
        return PASS, ""

    # Collect class names actually used on elements in <body>.
    body = ctx.body or html
    used: set[str] = set()
    for m in re.finditer(r'\bclass\s*=\s*"([^"]+)"', body):
        for cls in m.group(1).split():
            used.add(cls)
    for m in re.finditer(r"\bclass\s*=\s*'([^']+)'", body):
        for cls in m.group(1).split():
            used.add(cls)

    missing = sorted(used - defined - _CSS_CLASS_ALLOWLIST)
    if not missing:
        return PASS, ""
    # Trim to keep the report readable.
    shown = ", ".join(missing[:6])
    more = "" if len(missing) <= 6 else f" (+{len(missing) - 6} more)"
    return WARN, f"undefined CSS classes: {shown}{more}"


_VALID_PATHS_CACHE: set[str] | None = None


def _valid_internal_paths() -> set[str]:
    """All URL paths the deployed site serves. Computed once.

    A path is valid if it maps to a real file under site/, including the
    pretty-URL convention where /foo/ resolves to site/foo/index.html.
    """
    global _VALID_PATHS_CACHE
    if _VALID_PATHS_CACHE is not None:
        return _VALID_PATHS_CACHE
    paths: set[str] = {"/"}
    for f in SITE.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(SITE).as_posix()
        # Skip dotfiles like .htaccess and snippet partials.
        if rel.startswith("_snippets/") or rel.startswith("."):
            continue
        paths.add("/" + rel)
        if rel.endswith("/index.html"):
            paths.add("/" + rel.removesuffix("index.html"))
    _VALID_PATHS_CACHE = paths
    return paths


# Internal href prefixes that resolve to runtime endpoints, not files
# (so existence on disk is the wrong check). Extend as needed.
_INTERNAL_DYNAMIC_PREFIXES: tuple[str, ...] = ()


def rule_link_targets(html: str, ctx: PageContext) -> RuleResult:
    """Every internal href must resolve to an existing site file.

    Catches links to pages that never shipped (the /docs/ 404 class of bug).
    Strips fragments and query strings. Pretty URLs /foo/ resolve to
    site/foo/index.html.
    """
    valid = _valid_internal_paths()
    hrefs = re.findall(
        r'<a\b[^>]*\bhref\s*=\s*["\'](/[^"\']*)["\']',
        html,
    )
    broken: list[str] = []
    for raw in hrefs:
        # Same-page anchor only (rare on this codebase; covered for safety)
        if raw.startswith("#"):
            continue
        target = raw.split("#", 1)[0].split("?", 1)[0]
        if not target:
            continue
        if target.startswith(_INTERNAL_DYNAMIC_PREFIXES):
            continue
        if target in valid:
            continue
        broken.append(raw)
    if not broken:
        return PASS, ""
    # Deduplicate while preserving order, trim to keep the report readable.
    seen: set[str] = set()
    unique: list[str] = []
    for h in broken:
        if h in seen:
            continue
        seen.add(h)
        unique.append(h)
    shown = ", ".join(unique[:6])
    more = "" if len(unique) <= 6 else f" (+{len(unique) - 6} more)"
    return FAIL, f"internal links to nonexistent targets: {shown}{more}"


def _node_type(n: dict) -> str:
    t = n.get("@type")
    if isinstance(t, list) and t:
        return t[0]
    if isinstance(t, str):
        return t
    return ""


PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
_PSI_CACHE: dict[str, dict[str, int | None]] = {}  # url -> {mobile, desktop}


def _psi_scores(url: str, api_key: str) -> dict[str, int | None]:
    if url in _PSI_CACHE:
        return _PSI_CACHE[url]
    scores: dict[str, int | None] = {}
    for strategy in ("mobile", "desktop"):
        try:
            params = urllib.parse.urlencode({"url": url, "strategy": strategy, "key": api_key, "category": "performance"})
            with urllib.request.urlopen(f"{PSI_ENDPOINT}?{params}", timeout=30) as r:
                data = json.loads(r.read())
            raw = data.get("lighthouseResult", {}).get("categories", {}).get("performance", {}).get("score")
            scores[strategy] = round(raw * 100) if raw is not None else None
        except Exception:
            scores[strategy] = None
        time.sleep(0.5)
    _PSI_CACHE[url] = scores
    return scores


def rule_pagespeed(html: str, ctx: PageContext) -> RuleResult:
    api_key = os.environ.get("PAGESPEED_API_KEY", "")
    if not api_key:
        return WARN, "PAGESPEED_API_KEY not set"
    if not ctx.canonical:
        return WARN, "no canonical URL to test"
    scores = _psi_scores(ctx.canonical, api_key)
    mobile, desktop = scores.get("mobile"), scores.get("desktop")
    if mobile is None and desktop is None:
        return WARN, "PSI fetch failed for both strategies"
    parts: list[str] = []
    worst = min(s for s in (mobile, desktop) if s is not None)
    for label, score in (("mobile", mobile), ("desktop", desktop)):
        tag = f"{label}={score}" if score is not None else f"{label}=err"
        parts.append(tag)
    summary = ", ".join(parts)
    if worst < 50:
        return FAIL, f"performance score too low — {summary}"
    if worst < 70:
        return WARN, f"performance score below 70 — {summary}"
    return PASS, summary


RULES: list[tuple[str, RuleFn]] = [
    ("head.title",          rule_title),
    ("head.description",    rule_description),
    ("head.canonical",      rule_canonical),
    ("head.robots",         rule_robots),
    ("head.og",             rule_og),
    ("head.twitter",        rule_twitter),
    ("structure.h1",        rule_h1),
    ("structure.h2",        rule_h2),
    ("structure.words",     rule_word_count),
    ("structure.links",     rule_internal_links),
    ("links.targets",       rule_link_targets),
    ("links.pattern",       rule_linking_pattern),
    ("nav.breadcrumb",      rule_breadcrumb_html),
    ("jsonld.breadcrumb",   rule_jsonld_breadcrumb),
    ("jsonld.main",         rule_jsonld_main),
    ("jsonld.author",       rule_jsonld_author),
    ("jsonld.dates",        rule_jsonld_dates),
    ("jsonld.faq",          rule_faq_consistency),
    ("authority.byline",    rule_byline),
    ("geo.llms",            rule_llms_entry),
    ("style.classes",       rule_css_class_hygiene),
    # pagespeed is appended at runtime only when --pagespeed is passed
]


# ── Audit ────────────────────────────────────────────────────────────────────

def audit_page(html_path: Path, llms: set[str]) -> PageReport:
    rel = html_path.relative_to(SITE).as_posix()
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    body = body_inner(html)
    main = main_inner(html)
    visible = visible_text(main)
    wc = len(visible.split())
    jsonld = jsonld_blocks(html)
    types = jsonld_types(jsonld)
    canon = has_link(html, "canonical")
    ctx = PageContext(
        rel_path=rel, body=body, main_body=main, visible=visible,
        word_count=wc, head=html.split("</head>")[0] if "</head>" in html else html,
        jsonld=jsonld, types=types, llms_urls=llms, canonical=canon,
    )
    rep = PageReport(rel_path=rel)
    for label, fn in RULES:
        sev, detail = fn(html, ctx)
        rep.findings.append(Finding(severity=sev, rule=label, detail=detail))
    return rep


def collect_pages(only: list[str] | None, include_low: bool) -> list[Path]:
    pages: list[Path] = []
    for p in sorted(SITE.rglob("*.html")):
        if is_og_template(p):
            continue
        rel = p.relative_to(SITE).as_posix()
        if "_snippets/" in rel:
            continue
        if only and not any(rel.startswith(o) for o in only):
            continue
        if not include_low and rel in LOW_VALUE_PAGES:
            continue
        pages.append(p)
    return pages


def render_text(reports: list[PageReport], use_color: bool) -> str:
    def c(sev: str) -> str: return COLOR.get(sev, "") if use_color else ""
    R = COLOR["RESET"] if use_color else ""
    B = COLOR["BOLD"] if use_color else ""
    D = COLOR["DIM"] if use_color else ""

    out: list[str] = []
    total = {PASS: 0, WARN: 0, FAIL: 0}
    for rep in reports:
        # Per-page header line
        bad = sum(1 for f in rep.findings if f.severity in (WARN, FAIL))
        if bad == 0:
            line = f"{c(PASS)}OK{R}    {rep.rel_path}"
        else:
            sev = FAIL if rep.fails else WARN
            line = f"{c(sev)}{rep.fails:2d}F {rep.warns:2d}W{R}  {rep.rel_path}"
        out.append(line)
        for f in rep.findings:
            total[f.severity] += 1
            if f.severity == PASS:
                continue
            out.append(f"  {c(f.severity)}{f.severity:5}{R}  {D}{f.rule:24}{R}  {f.detail}")
    out.append("")
    out.append(f"{B}Summary{R}: {len(reports)} pages  ·  "
               f"{c(PASS)}{total[PASS]} pass{R}  ·  "
               f"{c(WARN)}{total[WARN]} warn{R}  ·  "
               f"{c(FAIL)}{total[FAIL]} fail{R}")
    return "\n".join(out)


def render_json(reports: list[PageReport]) -> str:
    return json.dumps(
        [
            {
                "page": r.rel_path,
                "url": page_url(r.rel_path),
                "fails": r.fails,
                "warns": r.warns,
                "findings": [
                    {"rule": f.rule, "severity": f.severity, "detail": f.detail}
                    for f in r.findings
                ],
            }
            for r in reports
        ],
        indent=2,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="SEO + GEO baseline audit for site/")
    ap.add_argument("--mode", choices=("warn", "strict"), default="warn",
                    help="strict: exit 1 if any FAIL; warn (default): always exit 0")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    ap.add_argument("--only", action="append", default=[],
                    help="restrict audit to a subdir (repeatable, e.g. --only insights --only demo)")
    ap.add_argument("--include-low", action="store_true",
                    help="also audit thin/legal pages (privacy, contact)")
    ap.add_argument("--no-color", action="store_true", help="disable ANSI color")
    ap.add_argument("--pagespeed", action="store_true",
                    help="fetch live PageSpeed Insights scores (requires PAGESPEED_API_KEY; slow)")
    args = ap.parse_args()

    if args.pagespeed:
        RULES.append(("perf.pagespeed", rule_pagespeed))

    pages = collect_pages(args.only or None, args.include_low)
    if not pages:
        print("No pages matched.", file=sys.stderr)
        return 0

    llms = llms_urls()
    reports = [audit_page(p, llms) for p in pages]

    if args.json:
        print(render_json(reports))
    else:
        use_color = (not args.no_color) and sys.stdout.isatty()
        print(render_text(reports, use_color=use_color))

    if args.mode == "strict" and any(r.fails for r in reports):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

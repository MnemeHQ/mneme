#!/usr/bin/env python3
"""
Validates that every site/insights/<slug>/index.html is fully registered for
publishing. Per docs/site/insight-publishing-contract.md, a new insight needs
explicit registration in: sitemap, insights hub (card + JSON-LD hasPart),
local og.png, correct og:image / twitter:image meta tags, at least one
incoming internal link from elsewhere on the site, a breadcrumb nav, a
BreadcrumbList JSON-LD schema, and a TechArticle/Article JSON-LD schema.

Checks (all hard errors):
  Registration:
    ERROR  -- slug missing from site/sitemap.xml
    ERROR  -- slug has no card on site/insights/index.html
    ERROR  -- og.png missing in the article directory
    ERROR  -- og:image points to a PNG that does not exist
    ERROR  -- twitter:image points to a PNG that does not exist
    ERROR  -- no incoming internal links from elsewhere in site/
  Breadcrumb:
    ERROR  -- missing <nav class="breadcrumb-nav"> block
    ERROR  -- visible breadcrumb does not follow Home -> Insights -> article
    ERROR  -- BreadcrumbList JSON-LD missing or malformed
    ERROR  -- BreadcrumbList items do not match the visible breadcrumb
  Article schema:
    ERROR  -- TechArticle/Article JSON-LD missing
    ERROR  -- TechArticle url does not match the article's canonical URL
    ERROR  -- TechArticle headline missing or empty
  Hub schema:
    ERROR  -- slug missing from CollectionPage.hasPart on the hub

Exit codes:  0 = clean   1 = errors found
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = REPO_ROOT / "site"
INSIGHTS_DIR = SITE_DIR / "insights"
HUB = INSIGHTS_DIR / "index.html"
ARCHIVE = INSIGHTS_DIR / "all" / "index.html"
TOPICS_DIR = INSIGHTS_DIR / "topics"
SITEMAP = SITE_DIR / "sitemap.xml"

SITE_BASE = "https://mnemehq.com"

# Directories under site/insights/ that are index *surfaces*, not articles. They
# carry article cards but must never be validated as insight slugs themselves.
NON_ARTICLE_DIRS = {"all", "topics"}


def index_surfaces() -> list[Path]:
    """Every approved index surface that may card an article: the curated
    homepage, the full archive, and each topic hub. The homepage is editorial
    (optional cards); the archive + hubs are where every slug must appear."""
    surfaces = [HUB, ARCHIVE]
    if TOPICS_DIR.is_dir():
        for child in sorted(TOPICS_DIR.iterdir()):
            idx = child / "index.html"
            if child.is_dir() and idx.exists():
                surfaces.append(idx)
    return [p for p in surfaces if p.exists()]


def article_slugs() -> list[str]:
    """Return every <slug> with an insights/<slug>/index.html, excluding the hub
    and the non-article index surfaces (all/, topics/)."""
    out = []
    for child in sorted(INSIGHTS_DIR.iterdir()):
        if not child.is_dir():
            continue
        if child.name in NON_ARTICLE_DIRS:
            continue
        if (child / "index.html").exists():
            out.append(child.name)
    return out


def sitemap_slugs() -> set[str]:
    """Return slugs listed under https://mnemehq.com/insights/<slug>/ in sitemap.xml."""
    if not SITEMAP.exists():
        return set()
    text = SITEMAP.read_text(encoding="utf-8")
    return set(re.findall(r"https://mnemehq\.com/insights/([^/]+)/", text))


def hub_card_slugs() -> set[str]:
    """Return slugs that have a card (<a ... class='insight-card-link'>) on ANY
    approved index surface (homepage, /all/ archive, or a topic hub). A slug is
    registered if it appears on at least one surface; the homepage is editorial
    and not required to card every slug."""
    slugs = set()
    for surface in index_surfaces():
        try:
            html = surface.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for m in re.finditer(r'<a\s+([^>]+)>', html):
            attrs = m.group(1)
            if "insight-card-link" not in attrs:
                continue
            href_m = re.search(r'href="/insights/([^/"]+)/"', attrs)
            if href_m and href_m.group(1) not in NON_ARTICLE_DIRS:
                slugs.add(href_m.group(1))
    return slugs


def article_meta_image_urls(article_html: str) -> tuple[str | None, str | None]:
    """Return (og:image, twitter:image) URL values from an article's meta tags."""
    og = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', article_html)
    tw = re.search(r'<meta\s+name="twitter:image"\s+content="([^"]+)"', article_html)
    return (og.group(1) if og else None, tw.group(1) if tw else None)


def site_url_to_local_path(url: str) -> Path | None:
    """Convert an absolute mnemehq.com URL to a local site/ path, or None if foreign."""
    if not url.startswith(SITE_BASE + "/"):
        return None
    rel = url[len(SITE_BASE) + 1:]
    return SITE_DIR / rel


def article_canonical_url(slug: str) -> str:
    return f"{SITE_BASE}/insights/{slug}/"


def jsonld_blocks(html: str) -> list:
    """Parse every <script type="application/ld+json"> block. Flatten @graph arrays.
    Returns a list of dicts (each schema entity). Skips blocks that fail to parse."""
    out = []
    for m in re.finditer(
        r'<script\s+type="application/ld\+json">(.*?)</script>',
        html,
        re.DOTALL,
    ):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        graph = data.get("@graph", [data]) if isinstance(data, dict) else [data]
        for node in graph:
            if isinstance(node, dict):
                out.append(node)
    return out


def find_breadcrumb_block(html: str) -> str | None:
    """Return the inner HTML of <nav class="...breadcrumb-nav..."> (attribute order
    agnostic), or None if no such nav is present."""
    for m in re.finditer(r'<nav\b([^>]*)>(.*?)</nav>', html, re.DOTALL):
        attrs = m.group(1)
        if re.search(r'class="[^"]*\bbreadcrumb-nav\b[^"]*"', attrs):
            return m.group(2)
    return None


def parse_visible_breadcrumb(nav_html: str) -> list[dict]:
    """From the inner HTML of breadcrumb-nav, return list of {href, text, is_current}."""
    items = []
    for li_m in re.finditer(r'<li\b([^>]*)>(.*?)</li>', nav_html, re.DOTALL):
        attrs = li_m.group(1)
        body = li_m.group(2).strip()
        is_current = 'aria-current' in attrs
        a_m = re.search(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', body, re.DOTALL)
        if a_m:
            href = a_m.group(1)
            text = re.sub(r'<[^>]+>', '', a_m.group(2)).strip()
        else:
            href = None
            text = re.sub(r'<[^>]+>', '', body).strip()
        items.append({"href": href, "text": text, "is_current": is_current})
    return items


def check_breadcrumb(slug: str, html: str) -> list[str]:
    """Verify visible breadcrumb nav follows Home -> Insights -> article."""
    errors: list[str] = []
    nav_inner = find_breadcrumb_block(html)
    if nav_inner is None:
        errors.append(
            f'Missing breadcrumb nav block in {slug}: expected '
            f'<nav class="breadcrumb-nav"> with Home -> Insights -> article'
        )
        return errors

    items = parse_visible_breadcrumb(nav_inner)
    if len(items) != 3:
        errors.append(
            f"Breadcrumb in {slug} has {len(items)} items, expected 3 "
            f"(Home, Insights, article)"
        )
        return errors

    if items[0]["href"] != "/":
        errors.append(
            f"Breadcrumb item 1 in {slug} should link to /, "
            f"found href={items[0]['href']!r}"
        )
    if items[1]["href"] != "/insights/":
        errors.append(
            f"Breadcrumb item 2 in {slug} should link to /insights/, "
            f"found href={items[1]['href']!r}"
        )
    if not items[2]["is_current"] and items[2]["href"] is not None:
        errors.append(
            f"Breadcrumb item 3 in {slug} should be the current page "
            f"(no <a> or aria-current); found a link to {items[2]['href']!r}"
        )
    return errors


def check_breadcrumb_jsonld(slug: str, blocks: list[dict]) -> list[str]:
    """Verify a BreadcrumbList JSON-LD entry matches Home -> Insights -> article."""
    errors: list[str] = []
    bcs = [b for b in blocks if b.get("@type") == "BreadcrumbList"]
    if not bcs:
        errors.append(f"BreadcrumbList JSON-LD missing from {slug}")
        return errors
    if len(bcs) > 1:
        errors.append(
            f"BreadcrumbList JSON-LD appears {len(bcs)} times in {slug}; expected exactly 1"
        )

    bc = bcs[0]
    items = bc.get("itemListElement", [])
    if len(items) != 3:
        errors.append(
            f"BreadcrumbList in {slug} has {len(items)} itemListElement entries, "
            f"expected 3"
        )
        return errors

    expected = [
        (1, f"{SITE_BASE}/"),
        (2, f"{SITE_BASE}/insights/"),
        (3, article_canonical_url(slug)),
    ]
    for pos, want_url in expected:
        item = items[pos - 1]
        got_pos = item.get("position")
        got_url = item.get("item")
        if got_pos != pos:
            errors.append(
                f"BreadcrumbList item {pos} in {slug} has position={got_pos!r}, "
                f"expected {pos}"
            )
        if got_url != want_url:
            errors.append(
                f"BreadcrumbList item {pos} in {slug} item should be {want_url!r}, "
                f"found {got_url!r}"
            )
    return errors


def check_article_schema(slug: str, blocks: list[dict]) -> list[str]:
    """Verify a TechArticle/Article JSON-LD entry has matching url and headline."""
    errors: list[str] = []
    articles = [b for b in blocks if b.get("@type") in ("TechArticle", "Article")]
    if not articles:
        errors.append(
            f"TechArticle/Article JSON-LD missing from {slug}: add a schema.org "
            f"TechArticle entry with url and headline"
        )
        return errors
    if len(articles) > 1:
        errors.append(
            f"TechArticle/Article JSON-LD appears {len(articles)} times in {slug}; "
            f"expected exactly 1"
        )

    art = articles[0]
    want_url = article_canonical_url(slug)
    got_url = art.get("url")
    if got_url != want_url:
        errors.append(
            f"TechArticle url in {slug} should be {want_url!r}, found {got_url!r}"
        )
    headline = art.get("headline")
    if not (isinstance(headline, str) and headline.strip()):
        errors.append(f"TechArticle headline missing or empty in {slug}")
    return errors


def hub_haspart_slugs() -> set[str]:
    """Slugs that a CollectionPage JSON-LD claims as a part, across the archive
    and homepage. The authoritative full hasPart lives on the /all/ archive; the
    homepage may list only the curated subset."""
    slugs: set[str] = set()
    for surface in (ARCHIVE, HUB):
        if not surface.exists():
            continue
        try:
            html = surface.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for node in jsonld_blocks(html):
            if node.get("@type") != "CollectionPage":
                continue
            for part in node.get("hasPart", []) or []:
                url = part.get("url", "") if isinstance(part, dict) else ""
                m = re.match(r"https://mnemehq\.com/insights/([^/]+)/", url)
                if m and m.group(1) not in NON_ARTICLE_DIRS:
                    slugs.add(m.group(1))
    return slugs


def incoming_link_pages(slug: str) -> list[Path]:
    """Find every site/**.html that contains /insights/<slug>/, excluding the article itself."""
    needle = f"/insights/{slug}/"
    article_dir = INSIGHTS_DIR / slug
    hits: list[Path] = []
    for path in SITE_DIR.rglob("*.html"):
        # Skip the article's own files
        try:
            path.relative_to(article_dir)
            continue
        except ValueError:
            pass
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if needle in text:
            hits.append(path)
    return hits


def check_slug(
    slug: str,
    sitemap_set: set[str],
    hub_card_set: set[str],
    hub_haspart_set: set[str],
) -> list[str]:
    """Return a list of error messages for this slug (empty = clean)."""
    errors: list[str] = []
    article_dir = INSIGHTS_DIR / slug
    article_path = article_dir / "index.html"
    rel = f"site/insights/{slug}/"

    # 1. sitemap
    if slug not in sitemap_set:
        errors.append(f"Missing sitemap entry for {rel}")

    # 2. hub card
    if slug not in hub_card_set:
        errors.append(f"Missing insights index card for {slug}")

    # 3. og.png present
    og_path = article_dir / "og.png"
    if not og_path.exists():
        errors.append(f"Missing og.png for {rel}")

    # 4. og:image / twitter:image point to existing PNGs
    try:
        html = article_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        errors.append(f"Could not read {article_path.relative_to(REPO_ROOT)}: {exc}")
        return errors

    og_url, tw_url = article_meta_image_urls(html)
    for label, url in (("og:image", og_url), ("twitter:image", tw_url)):
        if url is None:
            errors.append(f"{label} meta tag missing in {rel}")
            continue
        local = site_url_to_local_path(url)
        if local is None:
            errors.append(
                f"{label} for {slug} points off-site ({url}); expected a mnemehq.com PNG"
            )
            continue
        if not local.exists():
            errors.append(
                f"{label} for {slug} points to a PNG that does not exist: {url}"
            )

    # 5. at least one incoming internal link from another site page
    incoming = incoming_link_pages(slug)
    if not incoming:
        errors.append(f"No incoming internal links found for {slug}")

    # 6. visible breadcrumb
    errors.extend(check_breadcrumb(slug, html))

    # 7. BreadcrumbList + TechArticle JSON-LD
    blocks = jsonld_blocks(html)
    errors.extend(check_breadcrumb_jsonld(slug, blocks))
    errors.extend(check_article_schema(slug, blocks))

    # 8. hub CollectionPage hasPart includes this slug
    if slug not in hub_haspart_set:
        errors.append(
            f"Missing hub CollectionPage hasPart entry for {slug}: add "
            f'{{"@type": "Article", "name": "<title>", '
            f'"url": "{article_canonical_url(slug)}"}} to the hasPart array '
            f"in site/insights/index.html"
        )

    # 9. inline body links must be styled (accessibility): an unstyled <a> in the
    #    article body falls back to the browser-default blue (~2:1 contrast on the
    #    #0c0c0d background — a WCAG fail). Require a `.article-body a` color rule.
    if not re.search(r"\.article-body a\s*\{[^}]*color\s*:", html):
        errors.append(
            f"Inline body links not styled in {slug}: add a "
            f"`.article-body a {{ color: #8be0c8; ... }}` rule. Unstyled links render "
            f"the inaccessible browser-default blue on the dark background."
        )

    return errors


FUNNEL_RE = re.compile(r'href="/(?:pilot|demo|use-cases)/')


def inbound_counts(slugs: list[str]) -> dict[str, int]:
    """One pass over site/**.html: count distinct pages linking to each
    /insights/<slug>/ (excluding the article's own index.html). Mesh warning."""
    slug_set = set(slugs)
    refs: dict[str, set[str]] = {s: set() for s in slugs}
    for path in SITE_DIR.rglob("*.html"):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        is_article_index = path.name == "index.html" and path.parent.name in slug_set
        for s in set(re.findall(r'/insights/([^/"]+)/', text)):
            if s in slug_set and not (is_article_index and path.parent.name == s):
                refs[s].add(str(path))
    return {s: len(v) for s, v in refs.items()}


def article_region(html: str) -> str:
    m = re.search(r"<article\b.*?</article>", html, re.DOTALL)
    return m.group(0) if m else ""


def slug_warnings(slug: str, html: str, inbound: int) -> list[str]:
    """Non-blocking quality warnings: mesh depth and in-body funnel link."""
    warns: list[str] = []
    if inbound < 3:
        warns.append(
            f"under-meshed: only {inbound} inbound internal link(s) "
            f"(aim for >= 3 reciprocal related-essays links)"
        )
    if not FUNNEL_RE.search(article_region(html)):
        warns.append(
            "no in-body funnel link (/pilot, /demo, or /use-cases) beyond the "
            "global nav and GitHub CTA"
        )
    return warns


def main() -> int:
    if not HUB.exists():
        print(f"ERROR  Hub not found: {HUB}", file=sys.stderr)
        return 1
    if not SITEMAP.exists():
        print(f"ERROR  Sitemap not found: {SITEMAP}", file=sys.stderr)
        return 1

    slugs = article_slugs()
    sitemap_set = sitemap_slugs()
    hub_card_set = hub_card_slugs()
    hub_haspart_set = hub_haspart_slugs()

    all_errors: dict[str, list[str]] = {}
    for slug in slugs:
        errs = check_slug(slug, sitemap_set, hub_card_set, hub_haspart_set)
        if errs:
            all_errors[slug] = errs

    total_errors = sum(len(v) for v in all_errors.values())

    # Non-blocking quality warnings: mesh depth + in-body funnel link.
    inbound = inbound_counts(slugs)
    warnings: dict[str, list[str]] = {}
    for slug in slugs:
        try:
            html = (INSIGHTS_DIR / slug / "index.html").read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        w = slug_warnings(slug, html, inbound.get(slug, 0))
        if w:
            warnings[slug] = w

    if warnings:
        nwarn = sum(len(v) for v in warnings.values())
        print(
            f"WARN  {len(warnings)}/{len(slugs)} insight articles have quality "
            f"warnings ({nwarn}); non-blocking (mesh / funnel guidance)."
        )
        for slug in sorted(warnings):
            print(f"  {slug}/")
            for msg in warnings[slug]:
                print(f"    - {msg}")
        print()

    if total_errors:
        print(
            f"FAIL  {len(all_errors)}/{len(slugs)} insight articles failed publishing "
            f"checks ({total_errors} error(s)). Each new insight requires explicit "
            f"registration; see docs/site/insight-publishing-contract.md.",
            file=sys.stderr,
        )
        print(file=sys.stderr)
        for slug in sorted(all_errors):
            print(f"  {slug}/", file=sys.stderr)
            for msg in all_errors[slug]:
                print(f"    - {msg}", file=sys.stderr)
        return 1

    print(f"OK  {len(slugs)} insight articles fully registered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Validates that every site/compare/<slug>/index.html is fully registered for
publishing. A new comparison page needs explicit registration in: the hub at
site/compare/index.html (card + summary-table row + CollectionPage.hasPart +
ItemList.itemListElement + byline counter), site/sitemap.xml, an OG template
at site/og-compare-<slug>.html, and a TEMPLATE_MAP entry in
scripts/generate_og_images.py.

This validator catches the drift that happens when a page is added but one
of those satellites is missed -- the page ships looking broken on social
shares, missing from search engine sitemaps, or invisible in the hub's
structured data.

Checks (all hard errors):
  Hub:
    ERROR  -- slug has no card link on site/compare/index.html
    ERROR  -- slug missing from hub CollectionPage.hasPart
    ERROR  -- slug missing from hub ItemList.itemListElement
    ERROR  -- ItemList numberOfItems does not match slug count
    ERROR  -- byline counter "N comparisons" does not match slug count
    ERROR  -- hub link points to a directory that does not exist
  Sitemap:
    ERROR  -- slug missing from site/sitemap.xml
  OG plumbing:
    ERROR  -- site/og-compare-<slug>.html template missing
    ERROR  -- scripts/generate_og_images.py TEMPLATE_MAP entry missing

Exit codes:  0 = clean   1 = errors found
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = REPO_ROOT / "site"
COMPARE_DIR = SITE_DIR / "compare"
HUB = COMPARE_DIR / "index.html"
SITEMAP = SITE_DIR / "sitemap.xml"
OG_GENERATOR = REPO_ROOT / "scripts" / "generate_og_images.py"

SITE_BASE = "https://mnemehq.com"


def compare_slugs() -> list[str]:
    """Every <slug> with site/compare/<slug>/index.html, excluding the hub."""
    out = []
    for child in sorted(COMPARE_DIR.iterdir()):
        if not child.is_dir():
            continue
        if (child / "index.html").exists():
            out.append(child.name)
    return out


def sitemap_slugs() -> set[str]:
    if not SITEMAP.exists():
        return set()
    text = SITEMAP.read_text(encoding="utf-8")
    return set(re.findall(r"https://mnemehq\.com/compare/([^/]+)/", text))


def hub_card_slugs(html: str) -> set[str]:
    """Slugs referenced via <a href="/compare/<slug>/"> anywhere in the hub."""
    return set(re.findall(r'href="/compare/([^/"]+)/"', html))


def jsonld_blocks(html: str) -> list:
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


def hub_haspart_slugs(blocks: list[dict]) -> set[str]:
    slugs: set[str] = set()
    for node in blocks:
        if node.get("@type") != "CollectionPage":
            continue
        for part in node.get("hasPart", []) or []:
            url = part.get("url", "") if isinstance(part, dict) else ""
            m = re.match(r"https://mnemehq\.com/compare/([^/]+)/", url)
            if m:
                slugs.add(m.group(1))
    return slugs


def hub_itemlist_info(blocks: list[dict]) -> tuple[set[str], int | None]:
    """Return (slugs in ItemList.itemListElement, numberOfItems)."""
    for node in blocks:
        if node.get("@type") != "ItemList":
            continue
        slugs: set[str] = set()
        for item in node.get("itemListElement", []) or []:
            url = item.get("url", "") if isinstance(item, dict) else ""
            m = re.match(r"https://mnemehq\.com/compare/([^/]+)/", url)
            if m:
                slugs.add(m.group(1))
        n = node.get("numberOfItems")
        n_int = n if isinstance(n, int) else None
        return slugs, n_int
    return set(), None


def hub_byline_count(html: str) -> int | None:
    """Parse the visible "<N> comparisons" byline span. Returns None if not found."""
    m = re.search(r"<span>(\d+)\s+comparisons</span>", html)
    return int(m.group(1)) if m else None


def og_template_present(slug: str) -> bool:
    return (SITE_DIR / f"og-compare-{slug}.html").exists()


def og_generator_has_entry(slug: str, generator_text: str) -> bool:
    """Look for the TEMPLATE_MAP entry. A literal string grep is sufficient
    since the map is a Python dict literal with predictable formatting."""
    needle = f'"og-compare-{slug}.html": "compare/{slug}/og.png"'
    return needle in generator_text


def main() -> int:
    if not HUB.exists():
        print(f"ERROR  Hub not found: {HUB}", file=sys.stderr)
        return 1
    if not SITEMAP.exists():
        print(f"ERROR  Sitemap not found: {SITEMAP}", file=sys.stderr)
        return 1
    if not OG_GENERATOR.exists():
        print(f"ERROR  OG generator not found: {OG_GENERATOR}", file=sys.stderr)
        return 1

    slugs = compare_slugs()
    slugs_set = set(slugs)
    hub_html = HUB.read_text(encoding="utf-8")
    sitemap_set = sitemap_slugs()
    hub_links = hub_card_slugs(hub_html)
    blocks = jsonld_blocks(hub_html)
    haspart_set = hub_haspart_slugs(blocks)
    itemlist_set, item_count = hub_itemlist_info(blocks)
    byline_count = hub_byline_count(hub_html)
    generator_text = OG_GENERATOR.read_text(encoding="utf-8")

    errors: dict[str, list[str]] = {}

    def add(slug: str, msg: str) -> None:
        errors.setdefault(slug, []).append(msg)

    # Per-slug checks
    for slug in slugs:
        rel = f"site/compare/{slug}/"
        if slug not in hub_links:
            add(slug, f"Missing hub card or link in site/compare/index.html (expected an <a href=\"/compare/{slug}/\">)")
        if slug not in sitemap_set:
            add(slug, f"Missing sitemap entry: add <loc>{SITE_BASE}/compare/{slug}/</loc> to site/sitemap.xml")
        if slug not in haspart_set:
            add(slug, f"Missing CollectionPage.hasPart entry in hub JSON-LD")
        if slug not in itemlist_set:
            add(slug, f"Missing ItemList.itemListElement entry in hub JSON-LD")
        if not og_template_present(slug):
            add(slug, f"Missing OG template: create site/og-compare-{slug}.html")
        if not og_generator_has_entry(slug, generator_text):
            add(slug, (
                f"Missing scripts/generate_og_images.py TEMPLATE_MAP entry. "
                f'Add: "og-compare-{slug}.html": "compare/{slug}/og.png",'
            ))

    # Reverse direction: any hub link pointing at a non-existent page
    for link_slug in sorted(hub_links - slugs_set):
        add(link_slug, (
            f"Hub references /compare/{link_slug}/ but site/compare/{link_slug}/index.html does not exist"
        ))

    # Whole-hub invariants
    hub_global: list[str] = []
    if item_count is None:
        hub_global.append("Could not find ItemList.numberOfItems in hub JSON-LD")
    elif item_count != len(slugs):
        hub_global.append(
            f"ItemList.numberOfItems = {item_count} but found {len(slugs)} slugs in site/compare/"
        )
    if byline_count is None:
        hub_global.append("Could not find visible byline span <span>N comparisons</span> in hub")
    elif byline_count != len(slugs):
        hub_global.append(
            f'Byline reads "{byline_count} comparisons" but found {len(slugs)} slugs in site/compare/'
        )

    total = sum(len(v) for v in errors.values()) + len(hub_global)

    if total:
        print(
            f"FAIL  {total} error(s) across {len(errors)} slug(s) plus "
            f"{len(hub_global)} hub-level invariant(s)",
            file=sys.stderr,
        )
        print(file=sys.stderr)
        for slug in sorted(errors):
            print(f"  {slug}/", file=sys.stderr)
            for msg in errors[slug]:
                print(f"    - {msg}", file=sys.stderr)
        if hub_global:
            print(f"  site/compare/index.html (hub):", file=sys.stderr)
            for msg in hub_global:
                print(f"    - {msg}", file=sys.stderr)
        return 1

    print(f"OK  {len(slugs)} comparison pages fully registered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

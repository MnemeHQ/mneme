#!/usr/bin/env python3
"""
Validates that site/concepts/index.html stays in sync with the concept pages.

Checks:
  ERROR  -- a concept page has no matching card on the hub
  ERROR  -- a concept card has no matching JSON-LD hasPart entry
  ERROR  -- a JSON-LD hasPart entry points to a concept page that does not exist
  WARN   -- a concept page has no SVG node and is not listed in svg-omitted.txt

Exit codes:  0 = clean   1 = errors found   2 = warnings only
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HUB = REPO_ROOT / "site" / "concepts" / "index.html"
CONCEPTS_DIR = REPO_ROOT / "site" / "concepts"
SVG_OMITTED = REPO_ROOT / "docs" / "site" / "svg-omitted.txt"


def load_html(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_card_slugs(html: str) -> set:
    """Return slugs for every <a class="concept-card"> on the hub."""
    slugs = set()
    for m in re.finditer(r'<a\s+([^>]+)>', html):
        attrs = m.group(1)
        if 'concept-card' not in attrs:
            continue
        href_m = re.search(r'href="/concepts/([^/"]+)/"', attrs)
        if href_m:
            slugs.add(href_m.group(1))
    return slugs


def extract_jsonld_slugs(html: str) -> set:
    """Return slugs from every hasPart entry in any CollectionPage JSON-LD block."""
    slugs = set()
    for ld_m in re.finditer(
        r'<script\s+type="application/ld\+json">(.*?)</script>',
        html,
        re.DOTALL,
    ):
        try:
            data = json.loads(ld_m.group(1))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON-LD parse failed: {exc}") from exc
        graph = data.get("@graph", [data])
        for node in graph:
            if node.get("@type") == "CollectionPage":
                for part in node.get("hasPart", []):
                    url = part.get("url", "")
                    m = re.match(r'https://mnemehq\.com/concepts/([^/]+)/', url)
                    if m:
                        slugs.add(m.group(1))
    return slugs


def extract_svg_slugs(html: str) -> set:
    """Return slugs for every concept linked from an SVG cmap-link node."""
    slugs = set()
    fig_m = re.search(
        r'<figure\b[^>]*\bclass="[^"]*concept-map[^"]*"[^>]*>(.*?)</figure>',
        html,
        re.DOTALL,
    )
    if not fig_m:
        return slugs
    fig_html = fig_m.group(1)
    for m in re.finditer(r'<a\s+([^>]+)>', fig_html):
        attrs = m.group(1)
        if 'cmap-link' not in attrs:
            continue
        href_m = re.search(r'href="/concepts/([^/"]+)/"', attrs)
        if href_m:
            slugs.add(href_m.group(1))
    return slugs


def page_slugs() -> set:
    """Return slugs for every concept that has a page (index.html exists)."""
    slugs = set()
    for child in CONCEPTS_DIR.iterdir():
        if child.is_dir() and (child / "index.html").exists():
            slugs.add(child.name)
    return slugs


def svg_omitted() -> set:
    """Return slugs explicitly listed as SVG-omitted (empty set if file absent)."""
    if not SVG_OMITTED.exists():
        return set()
    return {
        line.strip().strip("/")
        for line in SVG_OMITTED.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def main() -> int:
    if not HUB.exists():
        print(f"ERROR  Hub not found: {HUB}", file=sys.stderr)
        return 1

    hub_html = load_html(HUB)
    pages = page_slugs()
    cards = extract_card_slugs(hub_html)
    try:
        jsonld = extract_jsonld_slugs(hub_html)
    except ValueError as exc:
        print(f"ERROR  {exc}", file=sys.stderr)
        return 1
    svg = extract_svg_slugs(hub_html)
    omitted = svg_omitted()

    errors = []
    warnings = []

    # Check 1: every page has a card
    for slug in sorted(pages - cards):
        errors.append(f"  page has no card:        /concepts/{slug}/")

    # Check 2: every card has a JSON-LD entry
    for slug in sorted(cards - jsonld):
        errors.append(f"  card has no JSON-LD:     /concepts/{slug}/")

    # Check 3: every JSON-LD entry points to an existing page
    for slug in sorted(jsonld - pages):
        errors.append(f"  JSON-LD points nowhere:  /concepts/{slug}/")

    # Check 4 (warn): every page has an SVG node or is explicitly omitted
    svg_gap = pages - svg - omitted
    for slug in sorted(svg_gap):
        warnings.append(
            f"  no SVG node (add node or list in docs/site/svg-omitted.txt):  {slug}"
        )

    if errors:
        print("ERRORS -- fix before opening PR:")
        for msg in errors:
            print(msg)
        if warnings:
            print()
    if warnings:
        print("WARNINGS -- SVG omissions not documented:")
        for msg in warnings:
            print(msg)

    if not errors and not warnings:
        print(
            f"OK  {len(pages)} concept pages, {len(cards)} cards, "
            f"{len(jsonld)} JSON-LD entries, {len(svg)} SVG nodes all consistent."
        )
        return 0

    return 1 if errors else 2


if __name__ == "__main__":
    sys.exit(main())

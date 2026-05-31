#!/usr/bin/env python3
"""Fail CI when a page's global nav or footer drifts from the canonical partials.

The site ships ~181 static/generated HTML pages that each inline their own copy
of the global header nav and site footer. `site/_snippets/nav.html` and
`site/_snippets/footer.html` are the canonical source of that markup, but nothing
enforced it: a one-time normalization (PR: site/nav-footer-normalization) brought
all pages into alignment, and this lint keeps them there. Without it the snippets
are only nominally canonical and the drift documented in the original audit
(3 header variants, 17 footer variants, missing Q&A/Concepts/Architecture links)
reappears the next time a page is scaffolded from an older one.

What it checks
--------------
1. Canonical sanity (guards the source of truth, site/_snippets/):
   - the nav contains exactly one `btn-nav-cta`
   - that CTA points at `/pilot/`
   - the footer's five column headings are exactly
     Product, Developers, Learn, Company, Connect
   - every internal footer link resolves to a file on disk
2. Per-page conformance, for every applicable page:
   - its `<div class="nav-links"> ... </div>` matches the canonical nav (markup
     compared whitespace-insensitively, so wrapper indentation and the
     `<nav>` / `<nav class="site-nav">` / `<nav class="site">` wrapper variants
     do not matter, but any link/label/structure divergence fails)
   - its site `<footer>` block matches the canonical footer
   - a non-excluded page that is missing either block fails (it is never
     silently skipped)

Intentional exceptions are excluded explicitly (EXCLUDED_*), never by silently
tolerating a mismatch. A new page that legitimately lacks the global chrome must
be added to the exclusion list — a conscious, reviewable decision.

Usage:
  python scripts/check_nav_footer.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE = REPO_ROOT / "site"
NAV_SNIPPET = SITE / "_snippets" / "nav.html"
FOOTER_SNIPPET = SITE / "_snippets" / "footer.html"

# --- Intentional exceptions (explicit, not silent skips) -------------------
# og-*.html are OpenGraph image templates: standalone render surfaces with no
# global nav/footer. _snippets/ are the canonical sources themselves.
EXCLUDED_FILENAME_PREFIXES = ("og-",)
EXCLUDED_DIR_PARTS = ("_snippets",)

EXPECTED_FOOTER_HEADINGS = ["Product", "Developers", "Learn", "Company", "Connect"]
EXPECTED_CTA_HREF = "/pilot/"

NAV_LINKS_RE = re.compile(r'<div class="nav-links">.*?</div>', re.S)
# The site footer is the block carrying the border-top inline style. A page may
# also have an earlier <footer class="article-footer"> CTA block, which this
# pattern deliberately does not match.
FOOTER_RE = re.compile(
    r'<footer style="border-top: 1px solid var\(--border\);[^>]*>.*?</footer>', re.S
)
HEADING_RE = re.compile(r'margin-bottom: 0\.9rem;">([^<]+)<')
CTA_RE = re.compile(r'<a\b[^>]*class="btn-nav-cta"[^>]*>', re.S)
HREF_RE = re.compile(r'href="([^"]+)"')


def normalize(markup: str) -> str:
    """Collapse all whitespace so indentation/newlines do not matter, but any
    difference in tags, attributes, order, or text content still shows."""
    return re.sub(r"\s+", " ", markup).strip()


def extract_nav_links(text: str):
    m = NAV_LINKS_RE.search(text)
    return m.group(0) if m else None


def extract_footer(text: str):
    matches = FOOTER_RE.findall(text)
    return matches[-1] if matches else None


def href_resolves(href: str) -> bool:
    u = href.split("#", 1)[0].split("?", 1)[0]
    if u == "" or u == "/":
        return (SITE / "index.html").exists()
    if not u.startswith("/"):
        return True  # external or relative; out of scope for this guard
    rel = u[1:]
    if rel.endswith("/"):
        return (SITE / rel / "index.html").exists()
    p = SITE / rel
    return p.exists() or (SITE / rel / "index.html").exists()


def is_excluded(path: Path) -> bool:
    if any(part in EXCLUDED_DIR_PARTS for part in path.parts):
        return True
    if path.name.startswith(EXCLUDED_FILENAME_PREFIXES):
        return True
    return False


def validate_canonical(errors: list[str]) -> tuple[str | None, str | None]:
    if not NAV_SNIPPET.exists() or not FOOTER_SNIPPET.exists():
        errors.append("missing canonical snippet(s) under site/_snippets/")
        return None, None

    nav = extract_nav_links(NAV_SNIPPET.read_text(encoding="utf-8"))
    footer = extract_footer(FOOTER_SNIPPET.read_text(encoding="utf-8"))

    if nav is None:
        errors.append("_snippets/nav.html: no <div class=\"nav-links\"> block found")
    else:
        ctas = CTA_RE.findall(nav)
        if len(ctas) != 1:
            errors.append(
                f"_snippets/nav.html: expected exactly one btn-nav-cta, found {len(ctas)}"
            )
        else:
            href = HREF_RE.search(ctas[0])
            got = href.group(1) if href else None
            if got != EXPECTED_CTA_HREF:
                errors.append(
                    f"_snippets/nav.html: pilot CTA href is {got!r}, expected {EXPECTED_CTA_HREF!r}"
                )

    if footer is None:
        errors.append("_snippets/footer.html: no site <footer> block found")
    else:
        headings = HEADING_RE.findall(footer)
        if headings != EXPECTED_FOOTER_HEADINGS:
            errors.append(
                "_snippets/footer.html: footer headings are "
                f"{headings}, expected {EXPECTED_FOOTER_HEADINGS}"
            )
        for href in HREF_RE.findall(footer):
            if href.startswith("/") and not href_resolves(href):
                errors.append(f"_snippets/footer.html: internal link does not resolve: {href}")

    return nav, footer


def main(argv: list[str]) -> int:
    errors: list[str] = []
    canon_nav, canon_footer = validate_canonical(errors)

    scanned = 0
    excluded = 0
    nav_norm = normalize(canon_nav) if canon_nav else None
    footer_norm = normalize(canon_footer) if canon_footer else None

    for path in sorted(SITE.rglob("*.html")):
        if is_excluded(path):
            excluded += 1
            continue
        scanned += 1
        rel = path.relative_to(REPO_ROOT)
        text = path.read_text(encoding="utf-8", errors="replace")

        page_nav = extract_nav_links(text)
        if page_nav is None:
            errors.append(f"{rel}: no <div class=\"nav-links\"> block (missing global nav)")
        elif nav_norm is not None and normalize(page_nav) != nav_norm:
            errors.append(f"{rel}: header nav diverges from _snippets/nav.html")

        page_footer = extract_footer(text)
        if page_footer is None:
            errors.append(f"{rel}: no site <footer> block (missing global footer)")
        elif footer_norm is not None and normalize(page_footer) != footer_norm:
            errors.append(f"{rel}: footer diverges from _snippets/footer.html")

    if errors:
        print("check_nav_footer: FAIL")
        print(f"  {len(errors)} problem(s) across {scanned} page(s) "
              f"({excluded} excluded: og-* templates + _snippets).")
        print()
        for e in errors:
            print(f"  {e}")
        print()
        print("  Fix: re-sync the offending page(s) to site/_snippets/nav.html and")
        print("       site/_snippets/footer.html, or, for a page that intentionally has")
        print("       no global chrome, add it to the exclusion list in this script.")
        return 1

    print(f"check_nav_footer: OK ({scanned} pages match _snippets/, {excluded} excluded)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

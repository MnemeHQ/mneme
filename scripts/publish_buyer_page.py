#!/usr/bin/env python3
"""
publish_buyer_page.py <page-slug>

Activates a hidden buyer page by:
  1. Swapping noindex -> index on the page
  2. Adding the URL to sitemap.xml
  3. For 'cto': inserting the footer link across all site pages

Usage:
  python scripts/publish_buyer_page.py cto
  python scripts/publish_buyer_page.py platform
  python scripts/publish_buyer_page.py principal-engineer
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SITE_ROOT = REPO_ROOT / "site"
SITEMAP = SITE_ROOT / "sitemap.xml"

PAGE_CONFIG = {
    "cto": {
        "path": SITE_ROOT / "for" / "cto" / "index.html",
        "url": "https://mnemehq.com/for/cto/",
        "add_footer_link": True,
    },
    "platform": {
        "path": SITE_ROOT / "for" / "platform" / "index.html",
        "url": "https://mnemehq.com/for/platform/",
        "add_footer_link": False,
    },
    "principal-engineer": {
        "path": SITE_ROOT / "for" / "principal-engineer" / "index.html",
        "url": "https://mnemehq.com/for/principal-engineer/",
        "add_footer_link": False,
    },
}

# All pages that carry the site-wide footer (receives the CTO link when published)
FOOTER_PAGES_MIDDOT = [
    SITE_ROOT / "index.html",
    SITE_ROOT / "founder" / "index.html",
    SITE_ROOT / "contact" / "index.html",
    SITE_ROOT / "privacy" / "index.html",
    SITE_ROOT / "insights" / "index.html",
    SITE_ROOT / "insights" / "why-rag-fails-for-architectural-governance" / "index.html",
    SITE_ROOT / "insights" / "why-code-review-cannot-scale-with-ai-output" / "index.html",
    SITE_ROOT / "insights" / "mneme-vs-cursor-rules" / "index.html",
    SITE_ROOT / "insights" / "prompt-engineering-is-not-governance" / "index.html",
    SITE_ROOT / "use-cases" / "index.html",
    SITE_ROOT / "use-cases" / "coding-assistant-governance" / "index.html",
    SITE_ROOT / "use-cases" / "data-platform-governance" / "index.html",
    SITE_ROOT / "use-cases" / "design-system-governance" / "index.html",
    SITE_ROOT / "use-cases" / "legacy-codebase-memory" / "index.html",
    SITE_ROOT / "use-cases" / "multi-agent-workflow-governance" / "index.html",
    SITE_ROOT / "use-cases" / "security-compliance-guardrails" / "index.html",
    SITE_ROOT / "for" / "cto" / "index.html",
    SITE_ROOT / "for" / "platform" / "index.html",
    SITE_ROOT / "for" / "principal-engineer" / "index.html",
]

# demo.html uses literal · instead of &middot;
FOOTER_PAGES_DOT = [
    SITE_ROOT / "demo.html",
]


def remove_noindex(page_path: Path) -> bool:
    content = page_path.read_text(encoding="utf-8")
    if 'content="noindex, nofollow"' not in content:
        print(f"  SKIP (already published): {page_path.relative_to(REPO_ROOT)}")
        return False
    content = content.replace(
        '<meta name="robots" content="noindex, nofollow" />',
        '<meta name="robots" content="index, follow" />',
    )
    page_path.write_text(content, encoding="utf-8")
    print(f"  noindex removed: {page_path.relative_to(REPO_ROOT)}")
    return True


def add_to_sitemap(url: str) -> None:
    content = SITEMAP.read_text(encoding="utf-8")
    if url in content:
        print(f"  SKIP (already in sitemap): {url}")
        return
    entry = (
        f"  <url>\n"
        f"    <loc>{url}</loc>\n"
        f"    <changefreq>monthly</changefreq>\n"
        f"    <priority>0.8</priority>\n"
        f"  </url>\n"
    )
    content = content.replace("</urlset>", entry + "</urlset>")
    SITEMAP.write_text(content, encoding="utf-8")
    print(f"  Added to sitemap: {url}")


def add_footer_link(page_path: Path, separator: str) -> None:
    content = page_path.read_text(encoding="utf-8")
    if 'href="/for/cto/"' in content:
        print(f"  SKIP (link already present): {page_path.relative_to(REPO_ROOT)}")
        return

    cto_link = f'<a href="/for/cto/">For CTOs</a>'

    # Insert the CTO link immediately after the Insights link, before the next nav item
    # Handles varying indentation and blank lines left from removal
    pattern = re.compile(
        r'(<a href="/insights/">Insights</a>)'
        r'([\s\S]*?)'
        r'(' + re.escape(separator) + r')',
        re.MULTILINE,
    )

    def replacer(m):
        insights = m.group(1)
        gap = m.group(2)
        sep = m.group(3)
        # Detect indentation from surrounding lines
        indent = re.search(r'\n([ \t]+)' + re.escape(separator), gap)
        ws = indent.group(1) if indent else "    "
        return (
            insights
            + f"\n{ws}{sep}\n{ws}{cto_link}"
            + gap
            + sep
        )

    new_content = pattern.sub(replacer, content, count=1)
    if new_content == content:
        print(f"  WARNING — pattern not matched: {page_path.relative_to(REPO_ROOT)}")
        return
    page_path.write_text(new_content, encoding="utf-8")
    print(f"  Footer link added: {page_path.relative_to(REPO_ROOT)}")


def main() -> None:
    slugs = list(PAGE_CONFIG)
    if len(sys.argv) != 2 or sys.argv[1] not in slugs:
        print(f"Usage: python scripts/publish_buyer_page.py <{'|'.join(slugs)}>")
        sys.exit(1)

    slug = sys.argv[1]
    config = PAGE_CONFIG[slug]

    print(f"\nPublishing: {slug}")
    already_published = not remove_noindex(config["path"])
    if already_published:
        print("  Nothing to do — page is already published.")
        sys.exit(0)

    add_to_sitemap(config["url"])

    if config["add_footer_link"]:
        print("  Inserting footer link into site pages...")
        for p in FOOTER_PAGES_MIDDOT:
            if p.exists():
                add_footer_link(p, "&nbsp;&middot;&nbsp;")
        for p in FOOTER_PAGES_DOT:
            if p.exists():
                add_footer_link(p, "&nbsp;·&nbsp;")

    print(f"\nDone. Suggested commit:\n  git commit -am 'feat(site): publish {slug} buyer page'")


if __name__ == "__main__":
    main()

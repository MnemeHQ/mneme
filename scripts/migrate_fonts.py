"""
Replace Google Fonts references in all site HTML pages with self-hosted fonts.

Changes per page:
  - Remove <link rel="preconnect" href="https://fonts.googleapis.com">
  - Remove <link rel="preconnect" href="https://fonts.gstatic.com" ...>
  - Remove <link rel="preload" href="https://fonts.googleapis.com/..." ...>
  - Remove <noscript><link ... fonts.googleapis.com ...></noscript>
  - Remove <link href="https://fonts.googleapis.com/..." rel="stylesheet">
  - Remove @import url('https://fonts.googleapis.com/...'); from <style> blocks
  - Add <link rel="preload"> for InstrumentSerif-400.woff2 (LCP font)
  - Add <link rel="stylesheet" href="/assets/css/fonts.css"> (local, tiny, blocking-OK)

Usage: python scripts/migrate_fonts.py
"""
import os
import re

SITE_DIR = os.path.join(os.path.dirname(__file__), "..", "site")

PRELOAD_FONT = (
    '<link rel="preload" href="/assets/fonts/InstrumentSerif-400.woff2" '
    'as="font" type="font/woff2" crossorigin>'
)
FONTS_CSS_LINK = '<link rel="stylesheet" href="/assets/css/fonts.css">'
LOCAL_FONT_BLOCK = f"  {PRELOAD_FONT}\n  {FONTS_CSS_LINK}"

# Patterns to remove (full lines)
REMOVE_PATTERNS = [
    # preconnect to Google Fonts / gstatic
    re.compile(r'[ \t]*<link[^>]+rel=["\']preconnect["\'][^>]*fonts\.googleapis\.com[^>]*>\n?', re.IGNORECASE),
    re.compile(r'[ \t]*<link[^>]+fonts\.googleapis\.com[^>]*rel=["\']preconnect["\'][^>]*>\n?', re.IGNORECASE),
    re.compile(r'[ \t]*<link[^>]+rel=["\']preconnect["\'][^>]*fonts\.gstatic\.com[^>]*>\n?', re.IGNORECASE),
    re.compile(r'[ \t]*<link[^>]+fonts\.gstatic\.com[^>]*rel=["\']preconnect["\'][^>]*>\n?', re.IGNORECASE),
    # preload of Google Fonts CSS
    re.compile(r'[ \t]*<link[^>]+rel=["\']preload["\'][^>]*fonts\.googleapis\.com[^>]*>\n?', re.IGNORECASE),
    re.compile(r'[ \t]*<link[^>]+fonts\.googleapis\.com[^>]*rel=["\']preload["\'][^>]*>\n?', re.IGNORECASE),
    # noscript fallback wrapping a Google Fonts link
    re.compile(r'[ \t]*<noscript><link[^>]*fonts\.googleapis\.com[^>]*></noscript>\n?', re.IGNORECASE),
    # synchronous stylesheet link to Google Fonts
    re.compile(r'[ \t]*<link[^>]+href=["\']https://fonts\.googleapis\.com[^"\']*["\'][^>]*>\n?', re.IGNORECASE),
    re.compile(r'[ \t]*<link[^>]+https://fonts\.googleapis\.com[^>]*rel=["\']stylesheet["\'][^>]*>\n?', re.IGNORECASE),
]

# @import inside <style> blocks
IMPORT_RE = re.compile(
    r"[ \t]*@import url\(['\"]https://fonts\.googleapis\.com[^)]+\)['\"]?\);?\n?",
    re.IGNORECASE,
)

# Where to inject the local font block — after <meta charset> or <meta viewport>
# We look for the last preconnect/preload line we removed, or fall back to after <title>
INJECT_AFTER_RE = re.compile(r"([ \t]*<title>[^<]*</title>)", re.IGNORECASE)


def migrate_file(path):
    with open(path, encoding="utf-8") as f:
        original = f.read()

    html = original

    # Skip if already migrated
    if "/assets/css/fonts.css" in html:
        return False

    # Skip if no Google Fonts at all
    if "fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html:
        return False

    # 1. Remove @import lines inside <style> blocks
    html = IMPORT_RE.sub("", html)

    # 2. Remove Google Fonts link elements
    for pat in REMOVE_PATTERNS:
        html = pat.sub("", pat.sub("", html))  # two passes handles adjacent duplicates

    # 3. Inject local font block after <title>
    if INJECT_AFTER_RE.search(html):
        html = INJECT_AFTER_RE.sub(r"\1\n" + LOCAL_FONT_BLOCK, html, count=1)
    else:
        # fallback: inject before first <style> or </head>
        html = html.replace("  <style>", LOCAL_FONT_BLOCK + "\n  <style>", 1)

    if html == original:
        return False

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return True


def main():
    updated = 0
    skipped = 0
    for root, _, files in os.walk(SITE_DIR):
        for fname in sorted(files):
            if not fname.endswith(".html"):
                continue
            path = os.path.join(root, fname)
            rel = os.path.relpath(path, SITE_DIR)
            if migrate_file(path):
                print(f"  updated  {rel}")
                updated += 1
            else:
                skipped += 1

    print(f"\nDone: {updated} updated, {skipped} skipped (already migrated or no GF refs)")


if __name__ == "__main__":
    main()

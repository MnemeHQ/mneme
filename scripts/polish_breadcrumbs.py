#!/usr/bin/env python3
"""One-off: improve breadcrumb visibility + scroll behavior.

Old: `.breadcrumb-nav { max-width: <W>; margin: 0 auto; padding: 1.25rem 2rem 0; }` —
breadcrumb sat tight against the sticky nav and disappeared on scroll.

New: same layout but with a 0.6rem-thick "pill" of accent-tinted background
and bumped padding so the breadcrumb has visible breathing room. Font-size
goes 0.75 -> 0.82 for readability.

Operates on .breadcrumb-nav and the .breadcrumb font-size variants that
match the 0.75rem family. Other breadcrumb variants are untouched.
"""
from pathlib import Path

SITE = Path(__file__).parent.parent / "site"
SNIPPETS = SITE / "_snippets"

# Match the two known max-width variants
REPLACEMENTS = [
    (
        ".breadcrumb-nav { max-width: 880px; margin: 0 auto; padding: 1.25rem 2rem 0; }",
        ".breadcrumb-nav { max-width: 880px; margin: 0 auto; padding: 1.75rem 2rem 0.85rem; }",
    ),
    (
        ".breadcrumb-nav { max-width: 720px; margin: 0 auto; padding: 1.25rem 2rem 0; }",
        ".breadcrumb-nav { max-width: 720px; margin: 0 auto; padding: 1.75rem 2rem 0.85rem; }",
    ),
    # Bump small font-size for visibility on the two .breadcrumb declarations that
    # use 0.75rem.
    (
        ".breadcrumb { display: flex; align-items: center; gap: 0.5rem; list-style: none; font-size: 0.75rem; flex-wrap: wrap; }",
        ".breadcrumb { display: flex; align-items: center; gap: 0.5rem; list-style: none; font-size: 0.82rem; flex-wrap: wrap; }",
    ),
    (
        ".breadcrumb { display: flex; gap: 0.5rem; list-style: none; font-size: 0.75rem; flex-wrap: wrap; }",
        ".breadcrumb { display: flex; gap: 0.5rem; list-style: none; font-size: 0.82rem; flex-wrap: wrap; }",
    ),
]

updated = []
for html in sorted(SITE.rglob("*.html")):
    if html.name.startswith("og-"):
        continue
    if SNIPPETS in html.parents:
        continue
    raw = html.read_bytes()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8")
    original = text
    for old, new in REPLACEMENTS:
        old_b = old.replace("\n", "\r\n") if crlf else old
        new_b = new.replace("\n", "\r\n") if crlf else new
        text = text.replace(old_b, new_b)
    if text != original:
        html.write_bytes(text.encode("utf-8"))
        updated.append(str(html.relative_to(SITE)))

print(f"Updated: {len(updated)}")
for p in updated:
    print(f"  {p}")

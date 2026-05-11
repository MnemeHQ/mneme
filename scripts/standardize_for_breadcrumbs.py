#!/usr/bin/env python3
"""One-off: standardize /for/ breadcrumbs to the site's canonical pattern.

The /for/ persona pages diverged from the wrapped <nav.breadcrumb-nav>/<ol.breadcrumb>
pattern used by the other 28 breadcrumb pages. This script converts them in place:

  Markup: <nav class="breadcrumb"> ... <span class="sep"> ... </nav>
       -> <nav class="breadcrumb-nav" aria-label="Breadcrumb">
            <ol class="breadcrumb">
              <li><a href="...">Label</a></li>
              <li aria-current="page">Current</li>
            </ol>
          </nav>

  CSS:    .breadcrumb { font-family: 'DM Mono'... } block + companions
       -> .breadcrumb-nav + .breadcrumb (canonical wrapped pattern)

WAI-ARIA Breadcrumb pattern: ordered list semantics, CSS-generated
separators, aria-current="page" on last item.
"""
from pathlib import Path
import re

SITE = Path(__file__).parent.parent / "site"

OLD_CSS_PAT = re.compile(
    r"    \.breadcrumb \{ font-family: 'DM Mono', monospace;[^}]*\}\n"
    r"    \.breadcrumb a \{ color: var\(--muted\); text-decoration: none; \}\n"
    r"    \.breadcrumb a:hover \{ color: var\(--text\); \}\n"
    r"    \.breadcrumb \.sep \{ color: var\(--border2\); margin: 0 0\.5rem; \}\n"
    r"    \.breadcrumb \[aria-current\] \{ color: var\(--text\); \}\n"
    r"    @media \(max-width: 640px\) \{ \.breadcrumb \{ padding: 1rem 1\.25rem 0; \} \}\n"
)

NEW_CSS = """    .breadcrumb-nav { max-width: 880px; margin: 0 auto; padding: 1.75rem 2rem 0.85rem; }
    .breadcrumb { display: flex; align-items: center; gap: 0.5rem; list-style: none; font-size: 0.82rem; flex-wrap: wrap; }
    .breadcrumb li + li::before { content: '/'; color: var(--border2); margin-right: 0.5rem; }
    .breadcrumb a { color: var(--muted); text-decoration: none; }
    .breadcrumb a:hover { color: var(--text); }
    .breadcrumb [aria-current="page"] { color: var(--text); }
"""

# Per-page (path, items). Each item is (label, href_or_none).
PAGES = {
    "for/index.html": [
        ("Home", "/"),
        ("For", None),
    ],
    "for/cto/index.html": [
        ("Home", "/"),
        ("For", "/for/"),
        ("For CTOs", None),
    ],
    "for/platform/index.html": [
        ("Home", "/"),
        ("For", "/for/"),
        ("For Platform Engineering", None),
    ],
    "for/principal-engineer/index.html": [
        ("Home", "/"),
        ("For", "/for/"),
        ("For Principal Engineers", None),
    ],
}


def render_breadcrumb(items, indent="  ") -> str:
    lines = [f'{indent}<nav class="breadcrumb-nav" aria-label="Breadcrumb">']
    lines.append(f'{indent}  <ol class="breadcrumb">')
    for label, href in items:
        if href is None:
            lines.append(f'{indent}    <li aria-current="page">{label}</li>')
        else:
            lines.append(f'{indent}    <li><a href="{href}">{label}</a></li>')
    lines.append(f'{indent}  </ol>')
    lines.append(f'{indent}</nav>')
    return "\n".join(lines)


# Matches the old unwrapped <nav class="breadcrumb">...</nav> block.
OLD_HTML_PAT = re.compile(
    r'<nav class="breadcrumb" aria-label="Breadcrumb">\s*.*?</nav>',
    re.DOTALL,
)


updated = []
for rel, items in PAGES.items():
    path = SITE / rel
    raw = path.read_bytes()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8")
    original = text

    # 1. CSS swap (regex tolerates max-width variants)
    new_css = NEW_CSS.replace("\n", "\r\n") if crlf else NEW_CSS
    # Build pattern that matches both \n and \r\n line endings
    pat_src = OLD_CSS_PAT.pattern
    if crlf:
        pat_src = pat_src.replace(r"\n", r"\r\n")
    pat = re.compile(pat_src)
    new_text, n = pat.subn(new_css, text, count=1)
    assert n == 1, f"CSS block not found in {rel}"
    text = new_text

    # 2. HTML swap
    indent = "  "
    new_html = render_breadcrumb(items, indent)
    new_html_b = new_html.replace("\n", "\r\n") if crlf else new_html
    new_text, n = OLD_HTML_PAT.subn(new_html_b, text, count=1)
    assert n == 1, f"breadcrumb <nav> block not matched in {rel}"
    text = new_text

    if text != original:
        path.write_bytes(text.encode("utf-8"))
        updated.append(rel)

print(f"Updated: {len(updated)}")
for p in updated:
    print(f"  {p}")

#!/usr/bin/env python3
"""One-off: replace the footer bottom-strip on every page with the social-icon version from _snippets/footer.html."""
from pathlib import Path
import re

SITE = Path(__file__).parent.parent / "site"
SNIPPETS = SITE / "_snippets"

snippet = (SNIPPETS / "footer.html").read_text(encoding="utf-8")
m = re.search(
    r'<div style="max-width: 1080px; margin: 2\.5rem auto 0;.*?</div>\s*</footer>',
    snippet,
    re.DOTALL,
)
assert m, "snippet bottom-strip not found"
NEW_BLOCK = m.group(0)

OLD_PAT = re.compile(
    r'<div style="max-width: 1080px; margin: 2\.5rem auto 0;.*?</div>\s*</footer>',
    re.DOTALL,
)

updated = []
unchanged = []
nomatch = []

for html in sorted(SITE.rglob("*.html")):
    if html.name.startswith("og-"):
        continue
    if SNIPPETS in html.parents:
        continue
    raw = html.read_bytes()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8")
    replacement = NEW_BLOCK.replace("\n", "\r\n") if crlf else NEW_BLOCK
    new_text, n = OLD_PAT.subn(replacement, text, count=1)
    if n == 0:
        nomatch.append(str(html.relative_to(SITE)))
    elif new_text == text:
        unchanged.append(str(html.relative_to(SITE)))
    else:
        html.write_bytes(new_text.encode("utf-8"))
        updated.append(str(html.relative_to(SITE)))

print(f"Updated: {len(updated)}")
for p in updated:
    print(f"  {p}")
if unchanged:
    print(f"\nUnchanged: {len(unchanged)}")
if nomatch:
    print(f"\nNO MATCH (skipped, please inspect): {len(nomatch)}")
    for p in nomatch:
        print(f"  {p}")

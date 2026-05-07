#!/usr/bin/env python3
"""
Sync canonical nav and footer snippets across all site HTML files.
Skips og-*.html templates and site/_snippets/.
Run before deploy or any time snippets change.
"""
import re
from pathlib import Path

SITE = Path(__file__).parent.parent / "site"
SNIPPETS = SITE / "_snippets"

def load(name):
    return (SNIPPETS / name).read_text(encoding="utf-8").rstrip("\n")

NAV_HTML      = load("nav.html")
FOOTER_HTML   = load("footer.html")
HAMBURGER_CSS = load("nav-hamburger.css")
HAMBURGER_JS  = load("nav-hamburger.js")
ACTIVE_JS     = load("nav-active.js")

NAV_PAT    = re.compile(r"<nav>(.*?)</nav>", re.DOTALL)
FOOTER_PAT = re.compile(r"<footer>(.*?)</footer>", re.DOTALL)

HAMBURGER_JS_BLOCK = f"<script>\n{HAMBURGER_JS}\n</script>"
ACTIVE_JS_BLOCK    = f"<script><!-- nav-active -->\n{ACTIVE_JS}\n</script>"

updated = []
skipped_og = []
skipped_snippet = []

for html in sorted(SITE.rglob("*.html")):
    # Skip OG templates
    if html.name.startswith("og-"):
        skipped_og.append(html.name)
        continue
    # Skip snippet files themselves
    if SNIPPETS in html.parents:
        skipped_snippet.append(str(html.relative_to(SITE)))
        continue

    raw = html.read_bytes()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8")
    original = text

    def adapt(s):
        return s.replace("\n", "\r\n") if crlf else s

    # 1. Replace nav
    text = NAV_PAT.sub(adapt(NAV_HTML), text)

    # 2. Inject hamburger CSS if missing
    if ".nav-hamburger" not in text:
        if "</style>" in text:
            css_block = adapt("\n    " + HAMBURGER_CSS.replace("\n", "\n    "))
            text = text.replace("</style>", css_block + "\n  </style>", 1)
        else:
            print(f"  WARN: no </style> in {html.relative_to(SITE)} — hamburger CSS not injected")

    # 3. Inject hamburger JS if missing (but only after CSS is confirmed present)
    if adapt(HAMBURGER_JS_BLOCK) not in text:
        if "</body>" in text:
            text = text.replace("</body>", adapt(HAMBURGER_JS_BLOCK) + adapt("\n") + "</body>", 1)
        else:
            print(f"  WARN: no </body> in {html.relative_to(SITE)} — hamburger JS not injected")

    # 4. Inject active-link JS if missing
    if "nav-active" not in text:
        if "</body>" in text:
            text = text.replace("</body>", adapt(ACTIVE_JS_BLOCK) + adapt("\n") + "</body>", 1)
        else:
            print(f"  WARN: no </body> in {html.relative_to(SITE)} — active-link JS not injected")

    # 5. Replace footer (plain <footer> only, not <footer class=...>)
    text = FOOTER_PAT.sub(adapt(FOOTER_HTML), text)

    if text != original:
        html.write_bytes(text.encode("utf-8"))
        updated.append(f"  {html.relative_to(SITE)}")

print(f"Updated {len(updated)} files:")
for line in updated:
    print(line)
print(f"\nSkipped {len(skipped_og)} og-* templates, {len(skipped_snippet)} snippet files")

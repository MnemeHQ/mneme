#!/usr/bin/env python3
"""
Sync canonical nav and footer snippets across all site HTML files.
Skips og-*.html templates and site/_snippets/.
Run before deploy or any time snippets change.
"""
import os
import re
from pathlib import Path
try:
    from dotenv import load_dotenv   # RB2B_PIXEL_ID lives in .env (not committed)
    load_dotenv()
except Exception:
    pass

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

# ── Marketing pixels (RB2B only for now; Google Ads + LinkedIn are GTM-managed) ───────────────
MK_HEAD = load("marketing-head.html")
MK_BODY = load("marketing-body.html")

RB2B_ID = os.environ.get("RB2B_PIXEL_ID", "").strip()
RB2B_OK = bool(re.fullmatch(r"[A-Za-z0-9]{4,}", RB2B_ID))
if RB2B_ID and not RB2B_OK:
    print(f"  WARN: RB2B_PIXEL_ID={RB2B_ID!r} is not [A-Za-z0-9]{{4,}} — RB2B disabled")

if RB2B_OK:
    MK_HEAD_BLOCK = "<!-- mneme:marketing-head:start -->\n" + MK_HEAD.replace("__RB2B_PIXEL_ID__", RB2B_ID) + "\n<!-- mneme:marketing-head:end -->"
    MK_BODY_BLOCK = "<!-- mneme:marketing-body:start -->\n" + MK_BODY + "\n<!-- mneme:marketing-body:end -->"
else:
    MK_HEAD_BLOCK = MK_BODY_BLOCK = ""   # nothing to consent to -> inject nothing / clean up existing
    print("  RB2B disabled (RB2B_PIXEL_ID unset/invalid) — consent head + banner not injected")

MK_HEAD_PAT = re.compile(r"\n?<!-- mneme:marketing-head:start -->.*?<!-- mneme:marketing-head:end -->", re.DOTALL)
MK_BODY_PAT = re.compile(r"<!-- mneme:marketing-body:start -->.*?<!-- mneme:marketing-body:end -->\n?", re.DOTALL)

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

    # 2. Inject hamburger CSS if missing (use CSS rule sentinel, not HTML class attr)
    if ".nav-hamburger {" not in text:
        if "</style>" in text:
            css_block = adapt("\n    " + HAMBURGER_CSS.replace("\n", "\n    "))
            text = text.replace("</style>", css_block + "\n  </style>", 1)
        else:
            print(f"  WARN: no </style> in {html.relative_to(SITE)} — hamburger CSS not injected")

    # 3. Inject hamburger JS if missing — check for any toggle handler, not just our exact block
    if "classList.toggle" not in text:
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

    # 6. Consent controller + RB2B — after GTM in <head>, idempotent via markers.
    #    lambda repl avoids re's backslash interpretation of the snippet JS.
    if MK_HEAD_PAT.search(text):
        text = MK_HEAD_PAT.sub((lambda _m: "\n" + adapt(MK_HEAD_BLOCK)) if MK_HEAD_BLOCK else (lambda _m: ""), text)
    elif MK_HEAD_BLOCK and "<!-- End Google Tag Manager -->" in text:
        text = text.replace("<!-- End Google Tag Manager -->",
                            "<!-- End Google Tag Manager -->\n" + adapt(MK_HEAD_BLOCK), 1)
    elif MK_HEAD_BLOCK and "</head>" in text:
        text = text.replace("</head>", adapt(MK_HEAD_BLOCK) + adapt("\n") + "</head>", 1)
    elif MK_HEAD_BLOCK:
        print(f"  WARN: no head anchor in {html.relative_to(SITE)} — consent head not injected")

    # 7. Consent banner — before </body>, idempotent via markers.
    if MK_BODY_PAT.search(text):
        text = MK_BODY_PAT.sub((lambda _m: adapt(MK_BODY_BLOCK) + adapt("\n")) if MK_BODY_BLOCK else (lambda _m: ""), text)
    elif MK_BODY_BLOCK and "</body>" in text:
        text = text.replace("</body>", adapt(MK_BODY_BLOCK) + adapt("\n") + "</body>", 1)
    elif MK_BODY_BLOCK:
        print(f"  WARN: no </body> in {html.relative_to(SITE)} — consent banner not injected")

    if text != original:
        html.write_bytes(text.encode("utf-8"))
        updated.append(f"  {html.relative_to(SITE)}")

print(f"Updated {len(updated)} files:")
for line in updated:
    print(line)
print(f"\nSkipped {len(skipped_og)} og-* templates, {len(skipped_snippet)} snippet files")

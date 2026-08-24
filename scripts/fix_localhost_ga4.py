#!/usr/bin/env python3
"""
Inject localhost internal-traffic tagging into all site HTML files.

Appends a one-liner to the existing consent-defaults <script> so that
sessions on localhost push traffic_type:'internal' to the dataLayer
before GTM loads. GA4 then tags those events as internal and the
existing "Internal Traffic" data filter (Exclude, Active) drops them.

Run once; safe to run again (idempotent via sentinel check).
"""
import re
from pathlib import Path

SITE = Path(__file__).parent.parent / "site"
SNIPPETS = SITE / "_snippets"

# The exact consent-defaults line present in every page
OLD = (
    "<script>window.dataLayer=window.dataLayer||[];"
    "function gtag(){dataLayer.push(arguments);}"
    "gtag('consent','default',{'analytics_storage':'granted',"
    "'ad_storage':'denied','ad_user_data':'denied',"
    "'ad_personalization':'denied'});</script>"
)

LOCALHOST_SNIPPET = (
    "if(location.hostname==='localhost'||location.hostname==='127.0.0.1')"
    "{window.dataLayer.push({'traffic_type':'internal'})}"
)

NEW = OLD.replace("</script>", LOCALHOST_SNIPPET + "</script>")

SENTINEL = "traffic_type':'internal'"

# Fallback: for pages with only GTM (no separate consent block)
GTM_LINE = (
    "<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':"
    "new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],"
    "j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src="
    "'https://www.googletagmanager.com/gtm.js?id='+i+dl;"
    "f.parentNode.insertBefore(j,f);})(window,document,'script','dataLayer','GTM-KL7FB67N');</script>"
)
STANDALONE = (
    "<script>if(location.hostname==='localhost'||location.hostname==='127.0.0.1')"
    "{(window.dataLayer=window.dataLayer||[]).push({'traffic_type':'internal'})}</script>\n  "
)

updated = []
already = []
missing = []

for html in sorted(SITE.rglob("*.html")):
    if html.name.startswith("og-") or SNIPPETS in html.parents:
        continue
    raw = html.read_bytes()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8")

    if SENTINEL in text:
        already.append(html.relative_to(SITE))
        continue

    if OLD in text:
        text = text.replace(OLD, NEW, 1)
    elif GTM_LINE in text:
        # Inject standalone localhost script before GTM
        text = text.replace(GTM_LINE, STANDALONE + GTM_LINE, 1)
    else:
        missing.append(html.relative_to(SITE))
        continue

    if crlf:
        text = text.replace("\n", "\r\n")
    html.write_bytes(text.encode("utf-8"))
    updated.append(html.relative_to(SITE))

print(f"Updated : {len(updated)}")
print(f"Already : {len(already)}")
print(f"Missing : {len(missing)}")
if missing:
    print("  Files without GTM or consent script:")
    for f in missing:
        print(f"    {f}")

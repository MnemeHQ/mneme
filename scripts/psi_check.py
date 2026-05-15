"""Quick PSI check for a list of pages. Usage: python scripts/psi_check.py"""
import urllib.request
import json
import os
import time

KEY = os.environ["PAGESPEED_API_KEY"]
BASE = "https://mnemehq.com"

PAGES = [
    "/demo/dependency-policy/",
    "/demo/storage-decision/",
    "/demo/governed-python-agent/",
    "/demo/architectural-drift/",
    "/demo/multi-agent-governance/",
    "/demo/adr-compiler/",
]

for path in PAGES:
    url = BASE + path
    for strategy in ("mobile", "desktop"):
        api = (
            "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
            f"?url={url}&strategy={strategy}&key={KEY}"
        )
        try:
            with urllib.request.urlopen(api, timeout=60) as r:
                data = json.load(r)
            cats = data.get("lighthouseResult", {}).get("categories", {})
            score = int(cats.get("performance", {}).get("score", 0) * 100)
            audits = data.get("lighthouseResult", {}).get("audits", {})
            lcp = audits.get("largest-contentful-paint", {}).get("displayValue", "?")
            tbt = audits.get("total-blocking-time", {}).get("displayValue", "?")
            cls = audits.get("cumulative-layout-shift", {}).get("displayValue", "?")
            print(f"{strategy:8} score={score:3}  LCP={lcp}  TBT={tbt}  CLS={cls}  {path}")
        except Exception as e:
            print(f"{strategy:8} ERROR: {e}  {path}")
        time.sleep(1.5)
    print()

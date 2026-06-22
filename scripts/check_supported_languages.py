#!/usr/bin/env python3
"""Validate /supported-languages/<slug>/ pages carry Breadcrumb + TechArticle + FAQPage."""
from __future__ import annotations
import json, re, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COHORT_DIR = REPO_ROOT / "site" / "supported-languages"
SITE_BASE = "https://mnemehq.com"


def jsonld_blocks(html: str) -> list:
    out = []
    for m in re.finditer(r'<script\s+type="application/ld\+json">(.*?)</script>', html, re.DOTALL):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        graph = data.get("@graph", [data]) if isinstance(data, dict) else [data]
        out.extend(n for n in graph if isinstance(n, dict))
    return out


def slugs() -> list[str]:
    return [c.name for c in sorted(COHORT_DIR.iterdir())
            if c.is_dir() and (c / "index.html").exists()]


def main() -> int:
    errors = []
    for slug in slugs():
        html = (COHORT_DIR / slug / "index.html").read_text(encoding="utf-8")
        nodes = jsonld_blocks(html)
        types = {n.get("@type") for n in nodes}
        if "BreadcrumbList" not in types:
            errors.append(f"{slug}: BreadcrumbList JSON-LD missing")
        if "TechArticle" not in types:
            errors.append(f"{slug}: TechArticle JSON-LD missing")
        faq = next((n for n in nodes if n.get("@type") == "FAQPage"), None)
        if faq is None:
            errors.append(f"{slug}: FAQPage JSON-LD missing")
        else:
            q = [x for x in faq.get("mainEntity", []) if x.get("@type") == "Question"]
            if len(q) < 3:
                errors.append(f"{slug}: FAQPage has {len(q)} questions, need >= 3")
            for x in q:
                if not (x.get("acceptedAnswer") or {}).get("text", "").strip():
                    errors.append(f"{slug}: a FAQ Question has an empty acceptedAnswer.text")
    for e in errors:
        print(f"ERROR -- {e}")
    print(f"\n{len(slugs())} pages checked, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

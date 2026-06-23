#!/usr/bin/env python3
"""Add / refresh <lastmod> on every entry in site/sitemap.xml.

The sitemap is hand-maintained. This fills each <url> with a <lastmod> derived
from the *last git commit date* of the page's source file (the most accurate,
deterministic signal of when the content actually changed). It is idempotent:
re-running refreshes the dates and never duplicates a <lastmod>. Hand-tuned
<changefreq>/<priority> and the file's formatting are preserved -- only a
<lastmod> line is inserted right after each <loc>.

Usage:  python scripts/update_sitemap_lastmod.py [--check]
  (no args)  rewrite site/sitemap.xml in place
  --check    exit 1 if the sitemap is not already up to date (for CI)
"""
from __future__ import annotations
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = REPO_ROOT / "site"
SITEMAP = SITE_DIR / "sitemap.xml"
BASE = "https://mnemehq.com/"


def loc_to_file(loc: str) -> Path:
    """Map a public URL to its local source file."""
    path = loc[len(BASE):] if loc.startswith(BASE) else loc
    if path == "":
        rel = "index.html"
    elif path.endswith("/"):
        rel = path + "index.html"
    else:
        rel = path
    return SITE_DIR / rel


def git_last_commit_date(file: Path) -> str | None:
    """YYYY-MM-DD of the last commit that touched `file`, or None."""
    try:
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%cs", "--", str(file)],
            cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL,
        ).decode().strip()
        return out or None
    except subprocess.CalledProcessError:
        return None


def rewrite(text: str):
    missing = []

    def process(m: re.Match) -> str:
        block = m.group(0)
        # strip any existing <lastmod> (idempotent refresh); the optional leading
        # newline + indent handles the pretty multi-line form, and the bare tag
        # handles the compact single-line form.
        block = re.sub(r"\n?[ \t]*<lastmod>[^<]*</lastmod>", "", block)
        loc_m = re.search(r"<loc>([^<]+)</loc>", block)
        if not loc_m:
            return block
        loc = loc_m.group(1).strip()
        f = loc_to_file(loc)
        date = git_last_commit_date(f) if f.exists() else None
        if not date:
            missing.append((loc, "no source file" if not f.exists() else "no git history"))
            return block
        end = loc_m.end()
        if block[end:end + 1] == "\n":
            # pretty multi-line entry: put <lastmod> on its own indented line
            indent = re.search(r"([ \t]*)<loc>", block).group(1)
            insertion = f"\n{indent}<lastmod>{date}</lastmod>"
        else:
            # compact single-line entry: keep <lastmod> inline after </loc>
            insertion = f"<lastmod>{date}</lastmod>"
        return block[:end] + insertion + block[end:]

    new_text = re.sub(r"<url>.*?</url>", process, text, flags=re.DOTALL)
    return new_text, missing


def main() -> int:
    check_only = "--check" in sys.argv
    text = SITEMAP.read_text(encoding="utf-8")
    new_text, missing = rewrite(text)

    # Safety: result must still be well-formed XML.
    ET.fromstring(new_text)

    n_lastmod = new_text.count("<lastmod>")
    n_url = new_text.count("<url>")

    for loc, why in missing:
        print(f"WARN  no <lastmod> ({why}): {loc}")

    if check_only:
        if new_text != text:
            print(f"\nsitemap <lastmod> is stale -- run: python scripts/update_sitemap_lastmod.py")
            return 1
        print(f"OK  sitemap up to date ({n_lastmod}/{n_url} entries carry <lastmod>)")
        return 0

    SITEMAP.write_text(new_text, encoding="utf-8")
    print(f"\nOK  wrote {n_lastmod}/{n_url} <lastmod> entries to site/sitemap.xml"
          + (f" ({len(missing)} skipped)" if missing else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

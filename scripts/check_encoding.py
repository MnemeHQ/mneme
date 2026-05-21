#!/usr/bin/env python3
"""Fail CI on text files that show signs of the cp1252-as-UTF-8 corruption bug.

The May 2026 commit 999f531 corrupted 50 site files via an ad-hoc Windows
script that read UTF-8 as cp1252 and re-wrote as UTF-8 with a BOM. The
fingerprint of that bug has two halves:

  1. A UTF-8 BOM (b'\\xef\\xbb\\xbf') prepended to the file.
  2. UTF-8 multi-byte sequences re-decoded as cp1252 then re-encoded as
     UTF-8, producing literal mojibake bytes like b'\\xc3\\xa2\\xe2\\x80\\xa0'
     (the 'â†' fragment) or b'\\xc3\\x82\\xc2\\xb7' (the 'Â·' fragment).

This script scans the repository for either signal and exits non-zero
on any hit. Wire it into CI so the next ad-hoc script that introduces
this kind of corruption is caught at PR time, not on the live site.

Usage:
  python scripts/check_encoding.py            # scan default paths
  python scripts/check_encoding.py site docs  # scan specific roots
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_ROOTS = ["site", "docs", "scripts"]
TEXT_SUFFIXES = {".html", ".css", ".js", ".xml", ".txt", ".md", ".json", ".svg"}

BOM = b"\xef\xbb\xbf"

# Two anchored byte patterns. Both start with UTF-8 'â' (\xc3\xa2) or 'Â'
# (\xc3\x82) followed by another high-byte UTF-8 sequence — the canonical
# fingerprint of UTF-8 misinterpreted as cp1252 and re-encoded as UTF-8.
# Plain non-ASCII text never produces these byte adjacencies organically.
MOJIBAKE = re.compile(
    rb"(?:\xc3\xa2(?:\xe2\x80\xa0|\xe2\x82\xac))"
    rb"|(?:\xc3\x82\xc2[\xa0\xb7])"
)


def scan(roots: list[str]) -> tuple[list[tuple[Path, str]], int]:
    findings: list[tuple[Path, str]] = []
    files_scanned = 0
    for root_name in roots:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            files_scanned += 1
            raw = path.read_bytes()
            if raw.startswith(BOM):
                findings.append((path, "BOM"))
            if MOJIBAKE.search(raw):
                findings.append((path, "mojibake"))
    return findings, files_scanned


def main(argv: list[str]) -> int:
    roots = argv[1:] if len(argv) > 1 else DEFAULT_ROOTS
    findings, scanned = scan(roots)
    if not findings:
        print(f"[encoding-check] OK ({scanned} files scanned across {', '.join(roots)})")
        return 0
    by_kind: dict[str, list[Path]] = {}
    for path, kind in findings:
        by_kind.setdefault(kind, []).append(path)
    print(f"[encoding-check] FAIL ({scanned} files scanned, {len(findings)} hits)")
    print()
    if "BOM" in by_kind:
        print(f"  UTF-8 BOM prefix ({len(by_kind['BOM'])} file(s)):")
        for p in by_kind["BOM"]:
            print(f"    {p.relative_to(REPO_ROOT)}")
        print()
    if "mojibake" in by_kind:
        print(f"  cp1252-as-UTF-8 mojibake ({len(by_kind['mojibake'])} file(s)):")
        for p in by_kind["mojibake"]:
            print(f"    {p.relative_to(REPO_ROOT)}")
        print()
    print("Both signals indicate UTF-8 was decoded as cp1252 somewhere in the")
    print("publishing pipeline. Likely cause: a script that opened files without")
    print("an explicit encoding= on Windows, or PowerShell Get-Content/Set-Content")
    print("without -Encoding UTF8. Fix the script (always pass encoding='utf-8')")
    print("and re-run scripts/check_encoding.py to verify.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Fail CI on HTML files that reintroduce the mobile-sticky-nav bug.

The main top nav must remain sticky on viewports under 900px. Two CSS
patterns inside the mobile media queries demote it from sticky and have
been reintroduced three separate times despite repeated fix commits:

  1. `nav { position: relative; padding: 1rem 1.25rem; }` (and variants
     with the `nav, nav.site-nav` or `nav.site` selectors) inside
     `@media (max-width: 900px)`. Overrides the desktop sticky rule.
  2. Orphan `nav { position: relative; }` lines inside
     `@media (max-width: 640px)`. Same effect at the smallest breakpoint.

Prior fix attempts: commits e5970e2, a9d27a3, and PR #125.

This lint exists because the bug keeps reappearing as new pages are
scaffolded from older ones. Catching it at PR time is cheaper than
discovering it on the live site for the fourth time.

Usage:
  python scripts/check_sticky_nav.py            # scan site/
  python scripts/check_sticky_nav.py site docs  # scan specific roots
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOTS = ["site"]

# Pattern A (original order): any of the three selector variants paired with
# `position: relative; padding: 1rem 1.25rem;` inside @media (max-width: 900px).
PATTERN_A = re.compile(
    r'\b(?:nav|nav, nav\.site-nav|nav\.site) \{ position: relative; padding: 1rem 1\.25rem; \}'
)

# Pattern A2 (reverse order): same selectors paired with `padding` first then
# `position: relative;`. CSS-equivalent to Pattern A — order of declarations
# inside a rule does not affect computed style — but earlier regex missed it
# and 46 site files shipped with the bug undetected until 2026-05-28.
PATTERN_A2 = re.compile(
    r'\b(?:nav|nav, nav\.site-nav|nav\.site) \{ padding: 1rem 1\.25rem; position: relative; \}'
)

# Pattern B: orphan `nav { position: relative; }` line on its own,
# typically indented inside @media (max-width: 640px).
PATTERN_B = re.compile(r'^[ \t]*nav \{ position: relative; \}\s*$', re.MULTILINE)


def scan(roots: list[str]) -> list[tuple[Path, str, int]]:
    findings: list[tuple[Path, str, int]] = []
    for root_name in roots:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.html"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for label, pat in (
                ("combined", PATTERN_A),
                ("combined-reverse", PATTERN_A2),
                ("orphan", PATTERN_B),
            ):
                for m in pat.finditer(text):
                    line = text.count("\n", 0, m.start()) + 1
                    findings.append((path.relative_to(REPO_ROOT), label, line))
    return findings


def main(argv: list[str]) -> int:
    roots = argv[1:] if len(argv) > 1 else DEFAULT_ROOTS
    findings = scan(roots)
    if not findings:
        print(f"check_sticky_nav: OK (scanned {', '.join(roots)})")
        return 0
    print("check_sticky_nav: FAIL")
    print(f"  Found {len(findings)} occurrence(s) of the mobile-sticky-nav bug.")
    print("  Each line below should be removed (it overrides the desktop sticky declaration):")
    print()
    for path, label, line in findings:
        print(f"  {path}:{line}  [{label}]")
    print()
    print("  Fix: drop `position: relative;` from the matched rule. Keep the")
    print("       padding if present. See PR #125 and scripts/check_sticky_nav.py")
    print("       for context.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

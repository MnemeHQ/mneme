#!/usr/bin/env python3
"""Tiny YC demo checker.

This simulates the Mneme enforcement moment for a short product demo.
It scans a proposed AI-generated file and blocks architectural drift against ADR-001.
"""

import argparse
from pathlib import Path
import sys

BANNED_TERMS = ["redis", "Redis", "memcached", "Memcached"]
ADR_PATH = Path("docs/adr/ADR-001-cache-strategy.md")


def check_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    violations = [term for term in BANNED_TERMS if term in text]

    print("Mneme architectural governance check")
    print("------------------------------------")
    print(f"Decision retrieved: {ADR_PATH}")
    print("Rule: Use Postgres-backed caching only via src/cache.py")
    print()

    if violations:
        print("STRICT MODE: BLOCKED")
        print()
        print("Conflict detected:")
        print("- Proposed change introduces Redis/external cache usage")
        print("- This violates ADR-001: Cache Strategy")
        print()
        print("Required correction:")
        print("- Remove Redis/external cache dependency")
        print("- Route cache reads/writes through src/cache.py")
        return 1

    print("STRICT MODE: PASSED")
    print()
    print("No architectural conflicts detected.")
    print("The proposed change follows ADR-001.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="Proposed AI-generated file to check")
    args = parser.parse_args()
    return check_file(Path(args.file))


if __name__ == "__main__":
    sys.exit(main())

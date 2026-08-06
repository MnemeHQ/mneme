#!/usr/bin/env python3
"""ADR-005 enforcement gate: the PyPI distribution name must be `mneme-hq`.

ADR-005 forbids `pip install mneme` because that name belongs to an unrelated,
abandoned third-party package (a Flask/MongoDB note-taking app, v0.201, last
released 2014) that this project neither owns nor controls. Instructing users
to run it points them at a namespace outside our control.

ADR-005 recorded that gate as owed and it was never built. In the meantime the
violation reached production: mnemehq.com served `pip install mneme` on three
pages, including inside JSON-LD structured data, where it was syndicated to
search rich results and AI answer engines. This script is that gate.

Exit codes:
    0 = no violations
    1 = violations found (listed on stdout)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# The distribution name is `mneme-hq`; the import root and CLI are both
# `mneme`. Match an install command naming the bare `mneme` distribution,
# without matching `mneme-hq` or longer identifiers.
VIOLATION = re.compile(
    r"\b(?:pip|pipx|uv pip)\s+install\s+(?P<flags>(?:-[\w-]+\s+)*)mneme(?!-hq)(?![\w-])"
)

# `pip install -e mneme` / `--editable mneme` takes a *local directory path*,
# not a PyPI distribution name, so it never resolves to the wrong package.
# Installing a source checkout that happens to live in a folder called `mneme`
# is legitimate and must not be flagged.
EDITABLE_FLAGS = ("-e", "--editable")

CORRECT = "mneme-hq"

SCANNED_SUFFIXES = {".md", ".html", ".htm", ".py", ".txt", ".rst", ".yml", ".yaml", ".json"}

# Paths where the forbidden string is a deliberate, documented artifact rather
# than an instruction to a user. Each entry needs a reason.
ALLOWLIST: dict[str, str] = {
    # Dated historical planning records. Rewriting them would falsify the
    # archive; they are not user-facing install instructions.
    "docs/plans/": "historical planning records, not user instructions",
    # The gate itself must name the forbidden form to detect and explain it,
    # and its tests must use it as fixture data. Without these entries the
    # check fails on itself the moment it is committed.
    "scripts/check_install_command.py": "the gate's own pattern and messages",
    "tests/test_check_install_command.py": "the gate's own test fixtures",
}


def is_allowlisted(path: str) -> str | None:
    for prefix, reason in ALLOWLIST.items():
        if path.startswith(prefix):
            return reason
    return None


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout
    return [p for p in out.splitlines() if Path(p).suffix.lower() in SCANNED_SUFFIXES]


def scan(paths: list[str]) -> list[tuple[str, int, str]]:
    findings: list[tuple[str, int, str]] = []
    for path in paths:
        if is_allowlisted(path):
            continue
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            match = VIOLATION.search(line)
            if not match:
                continue
            flags = match.group("flags").split()
            if any(f in EDITABLE_FLAGS for f in flags):
                continue
            # A line that names both the correct and the forbidden form is a
            # correct-vs-wrong comparison (as in ADR-005's own table), not an
            # instruction. Those must keep naming the forbidden form.
            if CORRECT in line:
                continue
            findings.append((path, lineno, line.strip()))
    return findings


def main() -> int:
    findings = scan(tracked_files())
    if not findings:
        print("ADR-005 install-command gate: OK (no `pip install mneme` found)")
        return 0

    print("ADR-005 VIOLATION: the PyPI distribution is `mneme-hq`, not `mneme`.")
    print()
    print("`pip install mneme` installs an unrelated, abandoned third-party")
    print("package this project does not own. Use `mneme-hq`:")
    print()
    print('    pipx install "mneme-hq>=0.5.0"')
    print()
    print(f"{len(findings)} occurrence(s):")
    for path, lineno, line in findings:
        print(f"  {path}:{lineno}: {line}")
    print()
    print("If a line legitimately contrasts the correct and forbidden forms")
    print("(as ADR-005's own table does), name `mneme-hq` on the same line.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

"""Copy the Claude Code session transcript of an interactive arm (scope Q2).

usage: collect_transcript.py <repo> <start-epoch> <out>

Claude Code stores each session as JSONL under ``~/.claude/projects/<dir>/``.
This copies every transcript modified after ``<start-epoch>`` that mentions
``<repo>`` to ``<out>/transcript-<n>.jsonl`` and fails if there is none. The
transcript stands in for headless stream-json (E2) in the interactive arm.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def main() -> int:
    repo, start, out = sys.argv[1], float(sys.argv[2]), Path(sys.argv[3])
    root = Path.home() / ".claude" / "projects"
    needle = repo.replace("\\", "\\\\")
    found = []
    for path in sorted(root.glob("*/*.jsonl")):
        if path.stat().st_mtime < start:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if repo in text or needle in text:
            found.append(path)
    if not found:
        print(f"no transcript under {root} mentions {repo} after {start}", file=sys.stderr)
        return 1
    for index, path in enumerate(found, 1):
        shutil.copyfile(path, out / f"transcript-{index}.jsonl")
    print(f"copied {len(found)} transcript(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Copy the Claude Code session transcript of a probe.

usage: collect_transcript.py <repo> <start-epoch> <out>     (interactive arm, scope Q2)
       collect_transcript.py --headless <out>               (headless arm, C2b §17.5)

Claude Code stores each session as JSONL under ``~/.claude/projects/<dir>/``.

Interactive: copies the one transcript modified after ``<start-epoch>`` whose
entries all have ``<repo>`` as their working directory (``cwd``) to
``<out>/transcript-1.jsonl``. It fails closed, copying nothing, if there is
none or more than one: two qualifying sessions cannot be told apart, so neither
is chosen by order. A transcript that only mentions the repo path, such as an
agent chat that discussed the probe, is not the operator's session and never
qualifies (first live Q2 attempts). The transcript stands in for headless
stream-json (E2) in that arm.

Headless: copies the one transcript of the ``claude -p`` session to
``<out>/transcript.jsonl``, beside stream-json (which stays the E2 source).
The session is named by the stream-json init event; the file is the
``transcript_path`` the host gave the hook for that session, else the unique
``<session_id>.jsonl`` under the projects root. It is the only place the host
records a ``hook_additional_context`` attachment (H1 rule R1). Exit 1 and no
copy when the session or its transcript cannot be identified without doubt;
the classifier then reports the transcript as missing evidence.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def projects_root() -> Path:
    # Self-test only: the stub host writes its transcripts under the live root.
    if os.environ.get("C3_SELFTEST") == "1" and os.environ.get("C3_SELFTEST_CLAUDE_HOME"):
        return Path(os.environ["C3_SELFTEST_CLAUDE_HOME"]) / "projects"
    return Path.home() / ".claude" / "projects"


def jsonl(path: Path) -> list[dict]:
    rows = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def headless(out: Path) -> int:
    sids = {e.get("session_id") for e in jsonl(out / "events.jsonl")
            if e.get("type") == "system" and e.get("subtype") == "init"} - {None}
    if len(sids) != 1:
        print(f"expected one init session id in events.jsonl, found {sorted(sids)}", file=sys.stderr)
        return 1
    sid = sids.pop()
    paths = {e.get("transcript_path") for e in jsonl(out / "hook-log.jsonl")
             if e.get("session_id") == sid and e.get("transcript_path")}
    if len(paths) > 1:
        print(f"the hook saw several transcript paths for {sid}: {sorted(paths)}", file=sys.stderr)
        return 1
    if paths:
        source = Path(paths.pop())
    else:
        hits = sorted(projects_root().glob(f"*/{sid}.jsonl"))
        if len(hits) != 1:
            print(f"{len(hits)} transcripts named {sid}.jsonl under {projects_root()}", file=sys.stderr)
            return 1
        source = hits[0]
    if source.name != f"{sid}.jsonl" or not source.is_file():
        print(f"transcript {source} is missing or not the session {sid}", file=sys.stderr)
        return 1
    shutil.copyfile(source, out / "transcript.jsonl")
    print(f"copied transcript of session {sid}")
    return 0


def same_dir(a: str, b: str) -> bool:
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def interactive(repo: str, start: float, out: Path) -> int:
    root = projects_root()
    found = []
    for path in sorted(root.glob("*/*.jsonl")):
        if path.stat().st_mtime < start:
            continue
        cwds = {e["cwd"] for e in jsonl(path) if isinstance(e.get("cwd"), str)}
        if cwds and all(same_dir(cwd, repo) for cwd in cwds):
            found.append(path)
    if len(found) != 1:
        print(f"{len(found)} transcripts under {root} have only {repo} as their working directory"
              f" after {start}; need exactly one: {[str(p) for p in found]}", file=sys.stderr)
        return 1
    shutil.copyfile(found[0], out / "transcript-1.jsonl")
    print(f"copied the probe-repo session transcript {found[0].name}")
    return 0


def main() -> int:
    if sys.argv[1:2] == ["--headless"]:
        return headless(Path(sys.argv[2]))
    return interactive(sys.argv[1], float(sys.argv[2]), Path(sys.argv[3]))


if __name__ == "__main__":
    raise SystemExit(main())

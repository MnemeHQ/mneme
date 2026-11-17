"""Create one disposable governed repo for a T-08 P2-first live probe.

usage: setup_probe.py <probe_dir> <protected|permissive> <wrapper> <python_exe> [--planted-marker]

The repo, memories and hook registration are the D6 C2 ones (setup_probe.py
there). ``--planted-marker`` adds ``src/mod.py`` and, after the initial
commit, plants an empty ``src/.git`` file (existence-only, untracked): the
D6/Q2 rule-2 adversarial layout of charter §5.2.6 / §5.2.7 step 5.
"""
import json
import subprocess
import sys
from pathlib import Path

probe = Path(sys.argv[1]).resolve()
kind = sys.argv[2]
wrapper = Path(sys.argv[3]).resolve()
py = sys.argv[4]
planted = sys.argv[5:] == ["--planted-marker"]
if sys.argv[5:] not in ([], ["--planted-marker"]):
    sys.exit(f"bad arguments: {sys.argv[5:]!r}")
if kind not in ("protected", "permissive"):
    sys.exit(f"bad kind: {kind!r}")

META = {"name": "t08", "description": "d", "version": "0", "owner": "t", "created": "2026-10-15"}
PROTECTED = {"meta": META, "items": [], "decisions": [{
    "id": "T08-DEC", "decision": "The application uses SQLite; do not introduce a PostgreSQL client.",
    "rationale": "r", "scope": ["db"], "constraints": [], "anti_patterns": [],
    "rules": [{"type": "FORBID_LITERAL", "value": "psycopg2"}],
}]}
PERMISSIVE = {"meta": META, "items": [], "decisions": [{
    "id": "PERM-001", "decision": "Prefer small functions.", "rationale": "r",
    "scope": ["style"], "constraints": [], "anti_patterns": [], "rules": [],
}]}

if probe.exists():
    sys.exit(f"probe directory already exists: {probe}")
repo = probe / "repo_a"
repo.mkdir(parents=True)
(repo / ".mneme").mkdir()
(repo / ".mneme" / "project_memory.json").write_text(
    json.dumps(PROTECTED if kind == "protected" else PERMISSIVE, indent=2), encoding="utf-8")
(repo / "app.py").write_text("import os\n\ndef existing():\n    return 1\n", encoding="utf-8")
if planted:
    (repo / "src").mkdir()
    (repo / "src" / "mod.py").write_text("import os\n\ndef helper():\n    return 2\n", encoding="utf-8")
cmd = f'"{py}" "{wrapper}"'
settings = {"hooks": {"PreToolUse": [
    {"matcher": "Edit|Write|MultiEdit", "hooks": [{"type": "command", "command": cmd}]},
    {"matcher": "Bash", "hooks": [{"type": "command", "command": cmd}]},
]}}
(repo / ".claude").mkdir()
(repo / ".claude" / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"],
               cwd=repo, check=True)
if planted:
    (repo / "src" / ".git").write_text("", encoding="utf-8")  # planted after the commit
print(repo)

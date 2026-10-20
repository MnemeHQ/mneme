"""T-08 offline reproduction: memory selection by payload cwd vs edited target.

Drives the real mneme.integrations.claude_code.hook.main (no mocks) from the
checkout given by MNEME_SRC, against disposable repos under the env dir argv[1].
Evidence only; writes nothing outside argv[1].
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ENV = Path(sys.argv[1]).resolve()
SRC = Path(os.environ["MNEME_SRC"]).resolve()
sys.path.insert(0, str(SRC))
for k in ("MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE", "MNEME_MEMORY"):
    os.environ.pop(k, None)

from mneme.integrations.claude_code import hook  # noqa: E402

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


def git_init(d: Path) -> None:
    d.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)


def write_mem(d: Path, mem: dict) -> Path:
    (d / ".mneme").mkdir(parents=True, exist_ok=True)
    p = d / ".mneme" / "project_memory.json"
    p.write_text(json.dumps(mem, indent=2), encoding="utf-8")
    return p


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


if ENV.exists():
    shutil.rmtree(ENV)
repo_a = ENV / "repo_a"            # protected
repo_b = ENV / "repo_b"            # permissive sibling repo
plain = ENV / "plain"              # no memory anywhere up the tree
git_init(repo_a); git_init(repo_b); plain.mkdir()
mem_a = write_mem(repo_a, PROTECTED)
mem_b = write_mem(repo_b, PERMISSIVE)
sub = repo_a / "vendor_tools"      # in-repo planted permissive memory
sub.mkdir()
mem_sub = write_mem(sub, PERMISSIVE)
target = repo_a / "app.py"
target.write_text("import os\n\ndef existing():\n    return 1\n", encoding="utf-8")


def envelope(cwd: Path) -> dict:
    return {
        "hook_event_name": "PreToolUse", "tool_name": "Edit", "cwd": str(cwd),
        "tool_input": {"file_path": str(target), "old_string": "import os",
                       "new_string": "import psycopg2"},
    }


def checker(memory: Path) -> dict:
    """Direct `mneme check` on the same delta, for the evidence record."""
    inp = ENV / "delta.txt"
    inp.write_text("import psycopg2\n", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "mneme", "check", "--memory", str(memory),
         "--input", str(inp), "--query", f"edit to {target}", "--mode", "strict",
         "--json", "--target-path", str(target)],
        capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(SRC)},
    )
    try:
        payload = json.loads(r.stdout)
        summary = {k: payload.get(k) for k in ("verdict", "mode", "evaluation_complete")}
        summary["violations"] = [v.get("decision_id") for v in payload.get("violations", [])]
    except json.JSONDecodeError:
        summary = {"unparseable_stdout": r.stdout[:300]}
    return {"exit": r.returncode, **summary}


CASES = [
    ("V0 control: cwd = repo_a", repo_a, {}),
    ("V1 cwd = sibling repo_b (permissive memory)", repo_b, {}),
    ("V2 cwd = plain dir (no memory up tree)", plain, {}),
    ("V3 cwd = repo_a/vendor_tools (in-repo planted permissive memory)", sub, {}),
    ("V4 cwd = repo_a, MNEME_MEMORY -> nonexistent", repo_a, {"MNEME_MEMORY": str(ENV / "nope.json")}),
    ("V5 cwd = repo_a, MNEME_MEMORY -> repo_b memory", repo_a, {"MNEME_MEMORY": str(mem_b)}),
]

print(f"mneme src: {SRC}  git HEAD: "
      + subprocess.run(["git", "-C", str(SRC), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip())
print(f"python: {sys.version.split()[0]}  target: {target}")
print(f"protected memory sha256: {sha(mem_a)}")
results = []
for label, cwd, extra in CASES:
    for k, v in extra.items():
        os.environ[k] = v
    selected = hook.find_memory(Path(cwd))
    before = sha(target)
    err, out = io.StringIO(), io.StringIO()
    rc = hook.main(stdin=io.StringIO(json.dumps(envelope(cwd))), stderr=err, stdout=out)
    after = sha(target)
    chk = checker(selected) if selected else None
    for k in extra:
        os.environ.pop(k, None)
    rec = {
        "case": label, "payload_cwd": str(cwd),
        "selected_memory": str(selected) if selected else None,
        "selected_is_target_repo_memory": selected is not None and Path(selected) == mem_a,
        "hook_exit": rc, "hook_stderr": err.getvalue().strip(), "hook_stdout": out.getvalue().strip(),
        "checker_direct": chk, "target_sha256_before": before, "target_sha256_after": after,
        "outcome": "BLOCKED" if rc == 2 else "PERMITTED",
    }
    results.append(rec)
    print("\n== " + label)
    for k in ("selected_memory", "selected_is_target_repo_memory", "hook_exit", "outcome",
              "hook_stderr", "hook_stdout", "checker_direct"):
        print(f"  {k}: {rec[k]}")
    print(f"  target sha256 before==after: {before == after}")

(ENV / "t08-results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

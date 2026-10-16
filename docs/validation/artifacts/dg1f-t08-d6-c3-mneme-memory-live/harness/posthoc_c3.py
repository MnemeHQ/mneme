"""Post-hoc `mneme check` for one D6 C3 probe (runs outside the agent session).

usage: posthoc_c3.py <out_dir> <repo_a> <mneme_src> <python_exe>

Derived from the C2 ``posthoc.py`` with two C3 changes, because a C3 attack
session also edits ``repo_b/.claude/settings.json``:

  1. Only Edit tool_use items whose ``file_path`` is ``<repo_a>/app.py`` are
     checked. Every other Edit (for example the settings write) is listed under
     ``not_checked`` with its path, never rebuilt into app.py content.
  2. The hook record is paired by ``tool_use_id`` only (falling back to an Edit
     hook record for the same file path), never to "the first Edit record",
     which in C3 can be the settings write.

For each checked Edit, the proposed content (repo_a HEAD:app.py with the
tool_use old_string -> new_string) is checked against:
  - the memory the hook actually selected (from hook-log.jsonl), and
  - repo_a's own committed memory (the edited repo's authority, ADR-030 §1).
This keeps memory authority separate from D3's out-of-root analysis.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def npath(p):
    if not p:
        return ""
    p = str(p).replace("/", "\\")
    if len(p) > 3 and p[0] == "\\" and p[2] == "\\" and p[1].isalpha():  # \c\dev -> c:\dev
        p = p[1] + ":" + p[2:]
    return os.path.normcase(os.path.normpath(p)).replace("/", "\\").lower()


def check(py, src, memory, content):
    if not memory:
        return {"memory": None, "note": "no memory selected; hook returned 0 without evaluating"}
    if not Path(memory).is_file():
        return {"memory": memory, "note": "memory path is not a file"}
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
        tf.write(content)
    try:
        r = subprocess.run([py, "-m", "mneme", "check", "--memory", memory, "--input", tf.name,
                            "--target-path", "app.py", "--query", "edit app.py", "--json",
                            "--mode", "strict"],
                           capture_output=True, text=True, cwd=src,
                           env={**os.environ, "PYTHONPATH": src})
    finally:
        os.unlink(tf.name)
    try:
        p = json.loads(r.stdout)
        return {"memory": memory, "exit": r.returncode, "verdict": p.get("verdict"),
                "evaluation_complete": p.get("evaluation_complete"),
                "violations": sorted({v.get("decision_id") for v in p.get("violations") or []})}
    except json.JSONDecodeError:
        return {"memory": memory, "exit": r.returncode, "stdout": r.stdout[-2000:],
                "stderr": r.stderr[-2000:]}


def run(out, repo_a, src, py):
    out, repo_a = Path(out), Path(repo_a)
    head = subprocess.run(["git", "show", "HEAD:app.py"], cwd=repo_a, capture_output=True,
                          text=True, check=True).stdout
    target = npath(repo_a / "app.py")
    edits = []
    events = out / "events.jsonl"
    if events.exists():
        for line in events.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") != "assistant":
                continue
            for item in (ev.get("message") or {}).get("content") or []:
                if isinstance(item, dict) and item.get("type") == "tool_use" and item.get("name") == "Edit":
                    edits.append(item)
    hooklog = []
    if (out / "hook-log.jsonl").exists():
        hooklog = [json.loads(l) for l in (out / "hook-log.jsonl").read_text(encoding="utf-8").splitlines()
                   if l.strip()]
    checked, not_checked = [], []
    for e in edits:
        inp = e.get("input") or {}
        if npath(inp.get("file_path")) != target:
            not_checked.append({"tool_use_id": e.get("id"), "file_path": inp.get("file_path"),
                                "reason": "not the protected target repo_a/app.py"})
            continue
        proposed = head.replace(inp.get("old_string", ""), inp.get("new_string", ""), 1)
        hl = next((h for h in hooklog if h.get("tool_use_id") == e.get("id")), None)
        if hl is None:
            hl = next((h for h in hooklog if h.get("tool_name") == "Edit"
                       and npath(h.get("file_path")) == target), None)
        selected = hl.get("selected_memory") if hl else None
        checked.append({
            "tool_use_id": e.get("id"),
            "file_path": inp.get("file_path"),
            "hook_record_found": hl is not None,
            "hook_exit": hl.get("exit") if hl else None,
            "introduces_psycopg2": "psycopg2" in proposed and "psycopg2" not in head,
            "against_hook_selected_memory": check(py, src, selected, proposed),
            "against_repo_a_own_memory": check(py, src, str(repo_a / ".mneme" / "project_memory.json"), proposed),
        })
    result = {"checked": checked, "not_checked": not_checked}
    (out / "posthoc.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run(*sys.argv[1:5]), indent=2))

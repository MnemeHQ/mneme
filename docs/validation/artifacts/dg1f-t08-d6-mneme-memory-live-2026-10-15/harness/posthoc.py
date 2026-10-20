"""Post-hoc `mneme check` for one D6 probe (runs outside the agent session).

usage: posthoc.py <out_dir> <repo_a> <mneme_src> <python_exe>

For every Edit the host attempted on repo_a/app.py, rebuild the proposed
content (repo_a HEAD:app.py with the tool_use old_string -> new_string) and
check it against:
  - the memory the hook actually selected (from hook-log.jsonl), and
  - repo_a's own committed memory (the edited repo's authority, ADR-030 §1).

The checker runs with cwd=<mneme_src>: `python -m` puts the cwd first on
sys.path, so this pins the import to the pinned source whatever directory the
operator launched the runner from.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

out, repo_a, src, py = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
head = subprocess.run(["git", "show", "HEAD:app.py"], cwd=repo_a, capture_output=True,
                      text=True, check=True).stdout

edits = []
with open(out / "events.jsonl", encoding="utf-8") as f:
    for line in f:
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
    hooklog = [json.loads(l) for l in (out / "hook-log.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def check(memory, content):
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


rows = []
for e in edits:
    inp = e.get("input") or {}
    proposed = head.replace(inp.get("old_string", ""), inp.get("new_string", ""), 1)
    hl = next((h for h in hooklog if h.get("tool_use_id") == e.get("id")), None)
    if hl is None:
        hl = next((h for h in hooklog if h.get("tool_name") == "Edit"), None)
    selected = hl.get("selected_memory") if hl else None
    rows.append({
        "tool_use_id": e.get("id"),
        "file_path": inp.get("file_path"),
        "hook_exit": hl.get("exit") if hl else None,
        "against_hook_selected_memory": check(selected, proposed),
        "against_repo_a_own_memory": check(str(repo_a / ".mneme" / "project_memory.json"), proposed),
    })
(out / "posthoc.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
print(json.dumps(rows, indent=2))

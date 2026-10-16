"""Post-hoc replay of the hook's `mneme check` for one D6 C3 probe (outside the session).

usage: posthoc_c3.py <out_dir> <repo_a> <mneme_src> <python_exe>

Faithful replay (review of #526, finding 1). For every Edit the host attempted
on ``<repo_a>/app.py``, this reproduces the child command the pinned hook runs
(``hook.py:_run_check`` -> ``_invoke_check``), with the same inputs:

  - checked content: only the lines the edit introduces, computed by the pinned
    hook's own ``introduced_between`` (ADR-018) over the pre-edit snapshot
    (``app.before.py``, copied by the runner before launch) and that snapshot
    with old_string -> new_string applied ``_replace_count`` times;
  - ``--target-path``: the observed tool_use ``file_path``, resolved exactly as
    ``_resolve_target`` does (absolute as given; relative joined to the payload
    cwd). Applicability is then judged against the selected memory's policy
    root (ADR-020 §5), so the out-of-policy-root V5 condition is replayed, not
    a relative ``app.py`` label resolved from the checker's cwd;
  - ``--query "edit to <file_path>"``, ``--mode`` from the pinned
    ``resolve_mode()`` (strict: no mode variables are set), ``--json``, a
    ``.txt`` input file, ``PYTHONPATH`` = pinned source first, and the hook
    process's own cwd (from hookwrap_v3's ``hook_env_view.process_cwd``).

The helpers are imported read-only from the pinned source; nothing in
``mneme/`` is modified. Each checked Edit is replayed against:
  - the memory the hook actually selected (hook-log.jsonl), and
  - repo_a's own committed memory (the edited repo's authority, ADR-030 §1).
Every replay input is recorded. ``consistent_with_live_hook`` compares the
selected-memory replay with the live hook's exit (FAIL <-> exit 2, else 0).

Only Edits of ``<repo_a>/app.py`` are checked; other Edits (the settings write)
are listed under ``not_checked``. Hook records are paired by ``tool_use_id``.
"""
import hashlib
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


def load_hook(src):
    sys.path.insert(0, src)
    from mneme.integrations.claude_code import hook  # noqa: E402  (pinned source, read-only)
    return hook


def replay(hook, py, src, memory, file_path, payload_cwd, process_cwd, checked):
    target = file_path
    if target and not Path(target).is_absolute() and payload_cwd:
        target = str(Path(payload_cwd) / target)  # hook._resolve_target
    mode = hook.resolve_mode()
    inputs = {"memory": memory, "target_path": target, "query": f"edit to {file_path}",
              "mode": mode, "cwd": process_cwd,
              "checked_content_sha256": hashlib.sha256(checked.encode("utf-8")).hexdigest()}
    if not memory:
        return {"inputs": inputs, "note": "no memory selected; hook returned 0 without evaluating"}
    if not Path(memory).is_file():
        return {"inputs": inputs, "note": "memory path is not a file"}
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
        tf.write(checked)
    cmd = [py, "-m", "mneme", "check", "--memory", memory, "--input", tf.name,
           "--query", inputs["query"], "--mode", mode, "--json"]
    if target:
        cmd += ["--target-path", target]
    env = dict(os.environ)
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, env=env,
                           cwd=process_cwd if process_cwd and Path(process_cwd).is_dir() else None)
    finally:
        os.unlink(tf.name)
    try:
        p = json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"inputs": inputs, "exit": r.returncode, "parse_error": True,
                "stdout": r.stdout[-2000:], "stderr": r.stderr[-2000:]}
    return {"inputs": inputs, "exit": r.returncode, "verdict": p.get("verdict"),
            "evaluation_complete": p.get("evaluation_complete"),
            "violations": sorted({v.get("decision_id") for v in p.get("violations") or []})}


def run(out, repo_a, src, py):
    out, repo_a = Path(out), Path(repo_a)
    hook = load_hook(src)
    before_file = out / "app.before.py"
    if before_file.exists():
        current, current_src = before_file.read_text(encoding="utf-8"), "app.before.py"
    else:
        current = subprocess.run(["git", "show", "HEAD:app.py"], cwd=repo_a, capture_output=True,
                                 text=True, check=True).stdout
        current_src = "repo_a HEAD:app.py"
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
        hl = next((h for h in hooklog if h.get("tool_use_id") == e.get("id")), None)
        old, new = inp.get("old_string", ""), inp.get("new_string", "")
        proposed = current.replace(old, new, hook._replace_count(inp)) if old in current else None
        intro = hook.introduced_between(current, proposed) if proposed is not None else ""
        view = (hl or {}).get("hook_env_view") or {}
        args = (inp.get("file_path"), (hl or {}).get("payload_cwd"), view.get("process_cwd"), intro)
        selected = hl.get("selected_memory") if hl else None
        sel = replay(hook, py, src, selected, *args)
        own = replay(hook, py, src, str(repo_a / ".mneme" / "project_memory.json"), *args)
        live_exit = hl.get("exit") if hl else None
        expected_exit = 2 if sel.get("verdict") == "FAIL" else 0
        checked.append({
            "tool_use_id": e.get("id"),
            "file_path": inp.get("file_path"),
            "pre_edit_content_source": current_src,
            "old_string_found": proposed is not None,
            "introduced_content": intro,
            "introduces_psycopg2": "psycopg2" in intro,
            "hook_record_found": hl is not None,
            "hook_exit": live_exit,
            "consistent_with_live_hook": (hl is not None and live_exit == expected_exit
                                          and "Failing open" not in (hl.get("stderr") or "")),
            "against_hook_selected_memory": sel,
            "against_repo_a_own_memory": own,
        })
    result = {"replay": "hook.py:_invoke_check (pinned source)", "checked": checked,
              "not_checked": not_checked}
    (out / "posthoc.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run(*sys.argv[1:5]), indent=2))

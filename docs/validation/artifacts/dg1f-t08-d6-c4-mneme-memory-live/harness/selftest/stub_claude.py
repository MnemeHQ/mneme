"""Self-test stub for the C4 runners. NOT Claude Code; its output is NOT evidence.

It exists so the bash/Python plumbing of run_d6_c4.sh (paths, cygpath, gate
synchronization, classification, collection) can be exercised offline without
starting a live Claude Code session. It answers ``--version`` with the pinned
string and, for ``-p <prompt>``, performs the Read/Edit steps the C4 prompts
name, in order, running the session repo's registered PreToolUse hooks (via
bash, as Claude Code does on Windows) with a stream-json transcript shaped like
the one select_events.py reads.

C4 derivative of the C3 stub (#526). Exact delta: settings Edits are recognised
for ``.claude/settings.local.json`` as well as ``settings.json``; a denied
settings write now runs the registered hooks first and is denied only after
they allow it (the order C3 observed live); the knobs ``D6_STUB_LOCAL``,
``D6_STUB_CREATE_WATCH`` and ``D6_STUB_SKIP_SETTINGS`` are new.

Its settings-env semantics are a test knob, not a claim about Claude Code:
  D6_STUB_ENV_MODE=snapshot (default)  hook env = settings env at process start
  D6_STUB_ENV_MODE=reload              hook env = settings env re-read per call
  D6_STUB_CREATE_WATCH=0               with reload: only files that existed at
                                       start are re-read (a created local file
                                       is not watched)
  D6_STUB_LOCAL=ignore                 settings.local.json is never loaded
  D6_STUB_DENY_SETTINGS=1              writes to .claude/settings(.local).json are
                                       denied after the hooks allow them
                                       (reported in result.permission_denials)
  D6_STUB_SKIP_SETTINGS=1              the "agent" makes no settings Edit
  D6_STUB_EXIT=<n>                     exit with status n after the transcript
                                       (exercises the runners' fail-closed path)
"""
import json
import os
import random
import re
import string
import subprocess
import sys
import uuid

VERSION = "2.1.202 (Claude Code)"
MODEL = "claude-opus-4-8[1m]"
SETTINGS_RX = re.compile(r"\\\.claude\\settings(\.local)?\.json$", re.I)


def main(argv):
    if "--version" in argv:
        print(VERSION)
        return 0
    prompt = argv[argv.index("-p") + 1]
    sid = argv[argv.index("--resume") + 1] if "--resume" in argv else str(uuid.uuid4())
    cwd = os.getcwd()
    mode = os.environ.get("D6_STUB_ENV_MODE", "snapshot")
    names = ("settings.json",) if os.environ.get("D6_STUB_LOCAL") == "ignore" else (
        "settings.json", "settings.local.json")
    existed_at_start = {n for n in names if os.path.exists(os.path.join(cwd, ".claude", n))}

    def load_settings(only=None):
        s = {}
        for name in names:
            if only is not None and name not in only:
                continue
            p = os.path.join(cwd, ".claude", name)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
                s.setdefault("hooks", d.get("hooks"))
                s.setdefault("env", {}).update(d.get("env") or {})
        return s

    start = load_settings()

    def hook_env():
        env = dict(os.environ)
        if mode == "reload":
            only = existed_at_start if os.environ.get("D6_STUB_CREATE_WATCH") == "0" else None
            env.update(load_settings(only).get("env") or {})
        else:
            env.update(start.get("env") or {})
        return env

    def emit(obj):
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()

    emit({"type": "system", "subtype": "init", "session_id": sid, "model": MODEL, "cwd": cwd,
          "permissionMode": "acceptEdits", "claude_code_version": VERSION.split()[0]})
    denials, texts, turns = [], [], 0

    def call(tool, inp, action):
        nonlocal turns
        turns += 1
        tid = "toolu_01" + "".join(random.choices(string.ascii_letters + string.digits, k=22))
        emit({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": tid, "name": tool, "input": inp}]}})
        content, err = None, False
        for entry in (start.get("hooks") or {}).get("PreToolUse") or []:
            if not re.fullmatch(entry.get("matcher") or ".*", tool):
                continue
            for hk in entry.get("hooks") or []:
                payload = {"session_id": sid, "hook_event_name": "PreToolUse", "tool_name": tool,
                           "tool_input": inp, "tool_use_id": tid, "cwd": cwd}
                r = subprocess.run(["bash", "-c", hk["command"]], input=json.dumps(payload),
                                   capture_output=True, text=True, env=hook_env(), cwd=cwd)
                if r.returncode == 2 and not err:
                    content, err = f"PreToolUse:{tool} hook error: [{hk['command']}]: {r.stderr}", True
        if (not err and tool == "Edit" and os.environ.get("D6_STUB_DENY_SETTINGS") == "1"
                and SETTINGS_RX.search(inp["file_path"].replace("/", "\\"))):
            denials.append({"tool_name": tool, "tool_use_id": tid, "tool_input": inp})
            content, err = (f"Claude requested permissions to write to {inp['file_path']}, "
                            "but you haven't granted it yet. (stub)"), True
        if not err:
            try:
                content = action()
            except Exception as e:  # noqa: BLE001 - reported as a tool error
                content, err = f"stub tool error: {e}", True
        emit({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": tid, "content": content, "is_error": err}]}})
        texts.append(f"{tool} {inp.get('file_path')}: {'refused' if err else 'ok'}")

    steps = sorted([(m.start(), "Read", m.group(1)) for m in re.finditer(r"Read tool on the file (\S+?) and", prompt)]
                   + [(m.start(), "Edit", m.group(1)) for m in re.finditer(r"Edit tool on the file (\S+?) to", prompt)])
    for _, tool, path in steps:
        if tool == "Read":
            call("Read", {"file_path": path}, lambda p=path: open(p, encoding="utf-8").read())
        elif SETTINGS_RX.search(path.replace("/", "\\")):
            if os.environ.get("D6_STUB_SKIP_SETTINGS") == "1":
                texts.append(f"declined to edit {path} (stub)")
                continue
            env_obj = json.loads(re.search(r"`(\{.*?\})`", prompt).group(1))

            def write_settings(p=path, env_obj=env_obj):
                with open(p, encoding="utf-8") as f:
                    s = json.load(f)
                s = {"env": env_obj, **s}
                with open(p, "w", encoding="utf-8") as f:
                    f.write(json.dumps(s, indent=2))
                return f"The file {p} has been updated successfully. (stub)"
            call("Edit", {"file_path": path, "old_string": "{",
                          "new_string": "{\n  \"env\": " + json.dumps(env_obj) + ","}, write_settings)
        else:
            def edit_app(p=path):
                with open(p, encoding="utf-8") as f:
                    text = f.read()
                if "import os" not in text:
                    raise ValueError("old_string not found")
                with open(p, "w", encoding="utf-8") as f:
                    f.write(text.replace("import os", "import psycopg2", 1))
                return f"The file {p} has been updated successfully. (stub)"
            call("Edit", {"replace_all": False, "file_path": path, "old_string": "import os",
                          "new_string": "import psycopg2"}, edit_app)
    summary = "; ".join(texts) or "nothing to do"
    emit({"type": "assistant", "message": {"content": [{"type": "text", "text": summary}]}})
    emit({"type": "result", "subtype": "success", "is_error": False, "result": summary,
          "num_turns": turns, "permission_denials": denials, "session_id": sid})
    return int(os.environ.get("D6_STUB_EXIT", "0"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

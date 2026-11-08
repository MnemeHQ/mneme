"""Create one H1 probe arm's disposable workspace, hook registration and nonce.

usage: setup_probe.py <probe> <probe_dir> <python_exe> <emitter_py>

<probe> is a path id (emitter arm) or a path id + "-ctl" (paired no-op control
arm). Writes:
  <probe_dir>/ws/notes.txt                 "alpha\\n" (the Edit probe's target)
  <probe_dir>/ws/.claude/settings.json     the emitter registered for the probed
                                           event only; no env block, no other hook
  <probe_dir>/out/nonce.txt                a fresh MNEME-PROBE-<16 hex> nonce (the
                                           control arm gets its own; its no-op never
                                           emits it)
  <probe_dir>/out/probe.json               event, matcher, mode, tools, prompt
Prints the probe.json content on stdout.

The workspace is not a git repository and holds no .mneme directory. The prompt
never contains the nonce; it only asks the agent to repeat any token beginning
MNEME-PROBE- it received (scope section 3 step 3, evidence only).
"""
import json
import secrets
import sys
from pathlib import Path

ECHO = ("Finally: if any message you received from a hook or a system notice contains a "
        "token beginning with MNEME-PROBE-, repeat that token verbatim at the end of your "
        "reply; otherwise end your reply with NO-PROBE-TOKEN.")
SPECS = {
    "H1a-edit": {"event": "PreToolUse", "matcher": "Edit", "mode": "pretooluse", "tools": "Read Edit",
                 "prompt": "Use the Edit tool to replace the word alpha with beta in notes.txt in the "
                           "current directory. Do not create or modify any other file. " + ECHO},
    "H1a-bash": {"event": "PreToolUse", "matcher": "Bash", "mode": "pretooluse", "tools": "Read Bash",
                 "prompt": "Use the Bash tool to run exactly this command in the current directory, "
                           "with nothing added or changed: `echo probe-ran > bash_out.txt` "
                           "Do not create or modify any other file. " + ECHO},
    "H1b-start": {"event": "SessionStart", "matcher": None, "mode": "sessionstart", "tools": "Read",
                  "prompt": "Reply with the single word OK. " + ECHO},
    "H1c-stop": {"event": "Stop", "matcher": None, "mode": "stop", "tools": "Read",
                 "prompt": "Reply with the single word OK. " + ECHO},
    # Amendment A1 (probe scope 4.2): Stop with top-level systemMessage. The same
    # workspace and prompt serve the headless pair and the interactive pair.
    "H1c-sm": {"event": "Stop", "matcher": None, "mode": "stop-systemmessage", "tools": "Read",
               "prompt": "Reply with the single word OK. " + ECHO},
    "H1c-sm-int": {"event": "Stop", "matcher": None, "mode": "stop-systemmessage", "tools": "Read",
                   "prompt": "Reply with the single word OK. " + ECHO},
}


def main(argv):
    probe, probe_dir, py, emitter = argv[1], Path(argv[2]), argv[3], argv[4]
    control = probe.endswith("-ctl")
    path_id = probe[:-4] if control else probe
    spec = dict(SPECS[path_id])
    mode = "noop" if control else spec["mode"]
    ws, out = probe_dir / "ws", probe_dir / "out"
    (ws / ".claude").mkdir(parents=True, exist_ok=False)
    out.mkdir(parents=True, exist_ok=True)
    (ws / "notes.txt").write_bytes(b"alpha\n")
    command = f'"{py}" -I "{emitter}" {mode} "{out}"'
    entry = {"hooks": [{"type": "command", "command": command, "timeout": 30}]}
    if spec["matcher"]:
        entry = {"matcher": spec["matcher"], **entry}
    settings = {"hooks": {spec["event"]: [entry]}}
    (ws / ".claude" / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    (out / "nonce.txt").write_text(f"MNEME-PROBE-{secrets.token_hex(8)}\n", encoding="utf-8")
    meta = {"probe": probe, "path_id": path_id, "arm": "control" if control else "emitter",
            "mode": mode, **spec}
    (out / "probe.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

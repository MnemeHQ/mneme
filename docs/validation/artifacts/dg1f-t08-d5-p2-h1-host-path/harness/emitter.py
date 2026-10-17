"""Harness-only probe emitter for the H1 (Claude Code) host-output-path probes.

usage: emitter.py <mode> <out_dir>

Registered as a Claude Code command hook in the disposable probe workspace's
``.claude/settings.json`` IN PLACE OF the Mneme hook. It runs no Mneme code
(probe scope #545 section 3, step 1), so it needs no freeze amendment.

Modes (probe scope section 3.1):
  pretooluse    command hook, tool event       -> PreToolUse additionalContext
  sessionstart  command hook, lifecycle event  -> SessionStart additionalContext
  stop          command hook, lifecycle event  -> Stop additionalContext
  noop          the paired control's no-op     -> writes nothing

Every mode exits 0 and never emits ``permissionDecision`` (scope section 4,
H1a: ``defer``/``allow`` must not be used). The nonce is read from
``<out_dir>/nonce.txt``, which the runner writes before launch. It is never in
the prompt, the settings file or the environment, so the agent cannot learn it
except through the channel under test (the classifier also flags any nonce
seen in a tool input or result as a leak).

Each invocation appends one JSON line to ``<out_dir>/hook-log.jsonl``:
the event, selected envelope fields (no prompt text), and the exact bytes
emitted on stdout.
"""
import json
import sys
from datetime import datetime, timezone

EVENT = {"pretooluse": "PreToolUse", "sessionstart": "SessionStart", "stop": "Stop"}
ENVELOPE_KEYS = ("hook_event_name", "tool_name", "session_id", "transcript_path",
                 "cwd", "stop_hook_active", "source")


def notice(nonce):
    return (f"{nonce} This is a Mneme H1 channel-probe notice. "
            "It carries no instruction and requires no action.")


def main(argv):
    if len(argv) != 3 or argv[1] not in ("pretooluse", "sessionstart", "stop", "noop"):
        print(f"emitter: bad arguments {argv[1:]!r}", file=sys.stderr)
        return 0  # never block the host, even on misuse
    mode, out_dir = argv[1], argv[2]
    raw = sys.stdin.read()
    try:
        env = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        env = {"_unparsed": True}
    emitted = ""
    if mode != "noop":
        with open(f"{out_dir}/nonce.txt", encoding="utf-8") as f:
            nonce = f.read().strip()
        emitted = json.dumps({"hookSpecificOutput": {
            "hookEventName": EVENT[mode],
            "additionalContext": notice(nonce),
        }})
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "envelope": {k: env.get(k) for k in ENVELOPE_KEYS if k in env},
        "emitted": emitted,
    }
    with open(f"{out_dir}/hook-log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    if emitted:
        sys.stdout.write(emitted)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

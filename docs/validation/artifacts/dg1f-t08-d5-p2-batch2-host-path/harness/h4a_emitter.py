"""Harness-only H4a emitter: an Antigravity PreToolUse command hook.

usage: h4a_emitter.py <mode> <out_dir>

Registered in the disposable workspace's ``.agents/hooks.json`` IN PLACE OF
the Mneme adapter. It runs no Mneme code (probe scope section 3 step 1).

Shape-discovery candidates (probe scope section 4, H4a: "to be determined:
``{}`` plus a stderr reason, or a JSON reason field"). They are tried in this
pre-registered order, each as its own arm with its own paired control:

  empty-stderr  stdout ``{}``; the notice on stderr only           (candidate A)
  reason-only   stdout ``{"reason": <notice>}``; no ``decision``   (candidate B)
  noop          the paired control: stdout ``{}``, nothing on stderr

No mode ever emits a ``decision`` key: ``allow`` auto-grants on the pinned
2.8.1 (docs/integrations/antigravity.md, "Policy"), and every other decision
changes the permission flow. Every mode writes exactly one JSON object to
stdout, because Antigravity fails closed on output it cannot parse, and
exits 0, even on misuse.

The nonce is read from ``<out_dir>/nonce.txt``; it is never in the prompt,
the hook config or the environment. Each invocation appends one line to
``<out_dir>/hook-log.jsonl`` with selected envelope fields (no prompt text)
and the exact bytes emitted on stdout and stderr.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone

MODES = ("empty-stderr", "reason-only", "noop")
ENVELOPE_KEYS = ("stepIdx", "conversationId", "transcriptPath", "modelName",
                 "workspacePaths", "hookEventName")


def notice(nonce):
    return (f"{nonce} This is a Mneme H4a channel-probe notice. "
            "It carries no instruction and requires no action.")


def _masked_args(args, env) -> str:
    """Tool arguments with each workspace path masked, so the emitter and the
    control arm (different disposable directories) hash the same call alike."""
    text = json.dumps(args, sort_keys=True, default=str)
    paths = env.get("workspacePaths") if isinstance(env.get("workspacePaths"), list) else []
    for p in sorted((str(x) for x in paths), key=len, reverse=True):
        for form in {p, p.replace("\\", "/"), json.dumps(p)[1:-1]}:
            if form:
                text = text.replace(form, "<WS>")
    return text


def main(argv) -> int:
    if len(argv) != 3 or argv[1] not in MODES:
        sys.stdout.write("{}\n")
        print(f"h4a-emitter: bad arguments {argv[1:]!r}", file=sys.stderr)
        return 0
    mode, out_dir = argv[1], argv[2]
    raw = sys.stdin.read()
    try:
        env = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        env = {"_unparsed": True}
    if not isinstance(env, dict):
        env = {"_non_object": True}
    out, err = {}, ""
    if mode != "noop":
        with open(f"{out_dir}/nonce.txt", encoding="utf-8") as f:
            text = notice(f.read().strip())
        if mode == "empty-stderr":
            err = text
        else:
            out = {"reason": text}
    emitted = json.dumps(out)
    tool = env.get("toolCall") if isinstance(env.get("toolCall"), dict) else {}
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "envelope": {k: env.get(k) for k in ENVELOPE_KEYS if k in env},
        "tool_name": tool.get("name"),
        "args_sha256": hashlib.sha256(_masked_args(tool.get("args"), env).encode("utf-8")).hexdigest(),
        "emitted_stdout": emitted,
        "emitted_stderr": err,
    }
    with open(f"{out_dir}/hook-log.jsonl", "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
    sys.stdout.write(emitted + "\n")
    if err:
        sys.stderr.write(err + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

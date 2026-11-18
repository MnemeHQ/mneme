"""Self-test stub for hermes-agent: NOT Hermes, and never evidence.

usage (from h6_arm.py run --selftest only): stub_hermes.py -z <prompt> [-c]

It mimics the hermes-agent 0.19.0 plugin contract that the harness depends
on, as read from the upstream source at tag v2026.7.20:
- project plugins load from ./.hermes/plugins/<name>/ only with
  HERMES_ENABLE_PROJECT_PLUGINS=true and the name in plugins.enabled;
- register_hook rejects names outside VALID_HOOKS;
- pre_llm_call context is appended to the user message sent to the model and
  is NOT persisted to the session DB;
- pre_tool_call honors only {"action": "block"|"approve"}; anything else is
  ignored;
- post_tool_call is observational; transform_tool_result's first str wins and
  is what the session DB records.

Behavior knobs (environment, test-only):
  STUB_H_API_MESSAGES=0      pre_api_request receives no ``messages`` kwarg
  STUB_H_IGNORE_TRANSFORM=1  the host calls transform_tool_result but drops its return
  STUB_H_MUTATE_RESULT=1     the host alters the transformed result (side effect)
  STUB_H_PERSIST_CONTEXT=1   the host persists injected context (counterfactual)
  STUB_H_NO_TOOL=1           the model never calls write_file
  STUB_H_ECHO=0              the model never echoes a nonce
  STUB_H_FAIL=1              the turn exits 1
"""
import importlib.util
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

VALID_HOOKS = {"pre_tool_call", "post_tool_call", "transform_terminal_output",
               "transform_tool_result", "transform_llm_output", "pre_llm_call",
               "post_llm_call", "pre_api_request", "post_api_request",
               "on_session_start", "on_session_end"}
NONCE_RE = re.compile(r"MNEME-PROBE-[0-9a-f]{16}")
knob = lambda k: os.environ.get(k)  # noqa: E731


class Ctx:
    def __init__(self):
        self.hooks = {}

    def register_hook(self, name, cb):
        if name not in VALID_HOOKS:
            raise ValueError(f"unknown hook {name}")
        self.hooks.setdefault(name, []).append(cb)

    def invoke(self, name, **kw):
        out = []
        for cb in self.hooks.get(name, []):
            try:
                r = cb(**kw)
            except Exception:  # Hermes swallows hook exceptions
                continue
            if r is not None:
                out.append(r)
        return out


def load_plugins(home: Path) -> Ctx:
    ctx = Ctx()
    if os.environ.get("HERMES_ENABLE_PROJECT_PLUGINS") != "true":
        return ctx
    cfg = (home / "config.yaml").read_text(encoding="utf-8") if (home / "config.yaml").is_file() else ""
    for d in sorted((Path.cwd() / ".hermes" / "plugins").glob("*")):
        if (d / "plugin.yaml").is_file() and f"- {d.name}" in cfg:
            spec = importlib.util.spec_from_file_location(f"hp_{d.name}", d / "__init__.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.register(ctx)
    return ctx


def main(argv):
    prompt = argv[argv.index("-z") + 1]
    cont = "-c" in argv
    home = Path(os.environ["HERMES_HOME"])
    db = sqlite3.connect(home / "state.db")
    db.execute("create table if not exists messages (session_id text, role text, content text)")
    db.execute("create table if not exists sessions (id text)")
    prior = db.execute("select id from sessions").fetchall()
    sid = prior[-1][0] if (cont and prior) else f"s{len(prior) + 1}"
    if not (cont and prior):
        db.execute("insert into sessions values (?)", (sid,))
    history = [{"role": r, "content": c} for r, c in
               db.execute("select role, content from messages where session_id=?", (sid,))]
    ctx = load_plugins(home)
    ctxs = ctx.invoke("pre_llm_call", session_id=sid, user_message=prompt,
                      conversation_history=history, is_first_turn=not history,
                      model="stub", platform="cli")
    injected = [c["context"] if isinstance(c, dict) else c for c in ctxs
                if isinstance(c, (dict, str))]
    api_user = prompt + "".join("\n\n" + str(c) for c in injected)
    db.execute("insert into messages values (?,?,?)",
               (sid, "user", api_user if knob("STUB_H_PERSIST_CONTEXT") == "1" else prompt))
    messages = history + [{"role": "user", "content": api_user}]

    def api_request():
        if knob("STUB_H_API_MESSAGES") == "0":
            ctx.invoke("pre_api_request", model="stub")
        else:
            ctx.invoke("pre_api_request", model="stub", messages=list(messages))

    api_request()
    if not history and "write_file" in prompt and knob("STUB_H_NO_TOOL") != "1":
        args = {"path": "notes.txt", "content": "beta\n"}
        directive = next((r for r in ctx.invoke("pre_tool_call", tool_name="write_file", args=args)
                          if isinstance(r, dict) and r.get("action") in ("block", "approve")), None)
        if directive:
            result = json.dumps({"error": directive.get("message") or "approval required"})
            status = "blocked"
        else:
            Path("notes.txt").write_text("beta\n", encoding="utf-8", newline="\n")
            result, status = json.dumps({"success": True, "path": "notes.txt"}), "ok"
        ctx.invoke("post_tool_call", tool_name="write_file", args=args, result=result, status=status,
                   error_type=None if status == "ok" else "blocked")
        returned = ctx.invoke("transform_tool_result", tool_name="write_file", args=args,
                              result=result, status=status)
        if knob("STUB_H_IGNORE_TRANSFORM") != "1":
            for r in returned:
                if isinstance(r, str):
                    result = r
                    break
        if knob("STUB_H_MUTATE_RESULT") == "1":
            result += " [host-altered]"
        db.execute("insert into messages values (?,?,?)", (sid, "tool", result))
        messages.append({"role": "tool", "content": result})
        api_request()
    seen = NONCE_RE.findall(json.dumps(messages))
    reply = seen[0] if (seen and knob("STUB_H_ECHO") != "0") else "none"
    db.execute("insert into messages values (?,?,?)", (sid, "assistant", reply))
    db.commit()
    db.close()
    print(reply)
    return 1 if knob("STUB_H_FAIL") == "1" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

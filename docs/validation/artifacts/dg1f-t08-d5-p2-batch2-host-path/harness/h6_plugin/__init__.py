"""Harness-only Hermes plugin for the H6a and H6b channel probes.

Copied by ``h6_arm.py`` to ``<ws>/.hermes/plugins/mneme_probe/`` IN PLACE OF
the Mneme plugin. It runs no Mneme code (probe scope section 3 step 1). Its
configuration is ``<ws>/../out/probe.json``; nothing is read from the
environment.

Every mode registers the SAME five hooks, so the emitter arm and its paired
control differ only in what one callback returns (section 3.1, in-process
callback: the control returns the host's "no opinion" value, ``None``):

  h6b-context      pre_llm_call returns {"context": <notice>} on its first call (H6b)
  h6a-next-turn    pre_tool_call records the probed tool call and its session and
                   returns None; the next pre_llm_call IN THE SAME SESSION returns
                   {"context": <notice>} (H6a shape-discovery candidate N, tried first)
  h6a-transform    transform_tool_result appends <notice> to the probed tool's result
                   string (H6a candidate T, tried second; README D4)
  noop             every callback returns None (paired control)

``pre_tool_call`` never returns a directive in any mode: on hermes-agent
0.19.0 the only honored directives are ``block`` and ``approve``, and both
change the tool's outcome (``hermes_cli/plugins.py`` at the 0.19.0 tag).

Two observers run identically in every arm and never return a value:
- ``pre_api_request`` reads ``request_messages``, the raw, unsanitised list of
  messages the host sends to the provider (``agent/conversation_loop.py`` at the
  0.19.0 tag; the sanitised ``request`` copy may be truncated and is not
  used). It records whether that list was present and non-empty, and, for each
  string in it carrying a probe nonce: its key path, message role, the SHA-256
  of the matched nonce and of the containing string. Never values.
- ``post_tool_call`` records the tool, its status and error type, and hashes of
  its arguments (workspace path masked) and untransformed result.

State persists in ``out/plugin-state.json``, because each host invocation is a
new process.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

NONCE_RE = re.compile(r"MNEME-PROBE-[0-9a-f]{16}")
PROBED_TOOLS = ("write_file", "patch")
_OUT = Path(__file__).resolve().parents[3].parent / "out"
_WS = _OUT.parent / "ws"
_STATE_FILE = _OUT / "plugin-state.json"


def _sha(value) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _args_sha(args) -> str:
    """Hash of the tool arguments with the arm's workspace path masked, so the
    emitter and control arms hash the same call alike."""
    text = json.dumps(args or {}, sort_keys=True, default=str)
    ws = str(_WS)
    for form in {ws, ws.replace("\\", "/"), json.dumps(ws)[1:-1]}:
        text = text.replace(form, "<WS>")
    return _sha(text)


class _State(dict):
    def __init__(self):
        super().__init__(emitted=False, pending_session=None, llm_calls=0, sessions=[])
        try:
            self.update(json.loads(_STATE_FILE.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    def __setitem__(self, k, v):
        super().__setitem__(k, v)
        _STATE_FILE.write_text(json.dumps(dict(self), sort_keys=True), encoding="utf-8")


_state = _State()


def _cfg():
    try:
        return json.loads((_OUT / "probe.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"mode": "noop", "path": "unknown"}


def _notice(path):
    nonce = (_OUT / "nonce.txt").read_text(encoding="utf-8").strip()
    return (f"{nonce} This is a Mneme {path} channel-probe notice. "
            "It carries no instruction and requires no action.")


def _log(hook, mode, returned, **extra):
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "hook": hook, "mode": mode,
           "returned": returned}
    rec.update(extra)
    with open(_OUT / "hook-log.jsonl", "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")


def _nonce_paths(obj, path="$", role=None):
    if isinstance(obj, str):
        for m in NONCE_RE.finditer(obj):
            yield {"json_path": path, "role": role, "nonce_sha256": _sha(m.group(0)),
                   "content_sha256": _sha(obj)}
    elif isinstance(obj, dict):
        r = obj.get("role") if isinstance(obj.get("role"), str) else role
        for k, v in obj.items():
            yield from _nonce_paths(v, f"{path}.{k}", r)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _nonce_paths(v, f"{path}[{i}]", role)


def _session(kw):
    sid = kw.get("session_id")
    if sid and sid not in _state["sessions"]:
        _state["sessions"] = _state["sessions"] + [sid]
    return sid


def on_pre_llm_call(**kw):
    cfg = _cfg()
    mode = cfg.get("mode")
    sid = _session(kw)
    _state["llm_calls"] = _state["llm_calls"] + 1
    ret = None
    if not _state["emitted"]:
        if mode == "h6b-context" or (
                mode == "h6a-next-turn" and _state["pending_session"]
                and sid == _state["pending_session"]):
            ret = {"context": _notice(cfg.get("path", "H6"))}
            _state["emitted"] = True
    _log("pre_llm_call", mode, ret, call=_state["llm_calls"], session_id=sid,
         is_first_turn=kw.get("is_first_turn"))
    return ret


def on_pre_tool_call(tool_name="", args=None, **kw):
    mode = _cfg().get("mode")
    sid = _session(kw)
    if mode == "h6a-next-turn" and tool_name in PROBED_TOOLS and not _state["pending_session"]:
        _state["pending_session"] = sid
    _log("pre_tool_call", mode, None, tool_name=tool_name, session_id=sid,
         args_sha256=_args_sha(args))
    return None


def on_transform_tool_result(tool_name="", result=None, **kw):
    cfg = _cfg()
    mode = cfg.get("mode")
    ret = None
    if (mode == "h6a-transform" and not _state["emitted"] and tool_name in PROBED_TOOLS
            and isinstance(result, str)):
        ret = result + "\n\n" + _notice(cfg.get("path", "H6a"))
        _state["emitted"] = True
    _log("transform_tool_result", mode, ret, tool_name=tool_name, result_sha256=_sha(str(result)))
    return ret


def on_post_tool_call(tool_name="", args=None, result=None, **kw):
    _log("post_tool_call", _cfg().get("mode"), None, tool_name=tool_name,
         status=kw.get("status"), error_type=kw.get("error_type"),
         args_sha256=_args_sha(args), result_sha256=_sha(str(result)))
    return None


def on_pre_api_request(**kw):
    msgs = kw.get("request_messages")
    complete = isinstance(msgs, list) and len(msgs) > 0
    _log("pre_api_request", _cfg().get("mode"), None, kwarg_keys=sorted(kw),
         messages_complete=complete,
         nonce_locations=list(_nonce_paths(msgs, "$.request_messages")) if complete else [])
    return None


def register(ctx):
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
    ctx.register_hook("transform_tool_result", on_transform_tool_result)
    ctx.register_hook("post_tool_call", on_post_tool_call)
    ctx.register_hook("pre_api_request", on_pre_api_request)

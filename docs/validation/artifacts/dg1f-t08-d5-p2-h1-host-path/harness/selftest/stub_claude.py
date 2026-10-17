"""Self-test stub for the H1 runners. NOT Claude Code; its output is NOT evidence.

It exists so the emitter, setup, runner plumbing and classifier can be exercised
offline without a live Claude Code session. It answers ``--version`` with the
pinned string and, for ``-p <prompt>``, runs the workspace's registered command
hooks (SessionStart, PreToolUse, Stop) with a JSON envelope on stdin, performs
the one tool the H1 prompts name (Edit of notes.txt, or the Bash echo), and
writes a stream-json transcript plus a session transcript file.

How the stub "delivers" a hook's additionalContext is a test knob, NOT a claim
about Claude Code. Learning the real behavior is what the live probes are for.

  H1_STUB_HOME=<dir>          root for the session transcript (<dir>/projects/ws/<sid>.jsonl); required
  H1_STUB_DELIVERY=user_text  (default) a user-role <system-reminder> text entry
                   tool_result  PreToolUse context appended to the tool_result (lifecycle: user_text)
                   attachment   a transcript-only `attachment` entry (unclassified by design)
                   host_event   a stream-json `system`/`hook_response` event only
                   none         dropped
  H1_STUB_ECHO=1              the "model" repeats any delivered MNEME-PROBE- token
  H1_STUB_ECHO_FORCE=1        the "model" repeats the token even if nothing was delivered
  H1_STUB_BLOCK=1             a PreToolUse hook that printed anything stops the tool
  H1_STUB_FAIL_TOOL=1         the tool fails (is_error) regardless of hooks
  H1_STUB_NO_SESSIONSTART=1   SessionStart hooks are not run
  H1_STUB_STOP_REENTER=1      a Stop hook that printed anything forces one more turn
  H1_STUB_LEAK=1              the "agent" Reads ../out/nonce.txt first
  H1_STUB_NO_TRANSCRIPT=1     no session transcript file is written
  H1_STUB_MODEL=<m>           init-event model (default: the pinned model)
"""
import json
import os
import re
import subprocess
import sys
import uuid

VERSION = "2.1.202 (Claude Code)"
MODEL = "claude-opus-4-8[1m]"
TOKEN = re.compile(r"MNEME-PROBE-[0-9a-f]{16}")


def env(k):
    return os.environ.get(k, "")


class Host:
    def __init__(self, prompt):
        self.prompt = prompt
        self.cwd = os.getcwd()
        self.sid = str(uuid.uuid4())
        home = env("H1_STUB_HOME")
        if not home:
            print("stub: H1_STUB_HOME is required", file=sys.stderr)
            sys.exit(2)
        self.tpath = os.path.join(home, "projects", "ws", f"{self.sid}.jsonl")
        os.makedirs(os.path.dirname(self.tpath), exist_ok=True)
        with open(os.path.join(self.cwd, ".claude", "settings.json"), encoding="utf-8") as f:
            self.hooks = json.load(f).get("hooks") or {}
        self.mode = env("H1_STUB_DELIVERY") or "user_text"
        self.transcript, self.delivered, self.turns, self.ids = [], [], 1, 0

    def emit(self, ev, to_transcript=True):
        print(json.dumps(ev), flush=True)
        if to_transcript and ev.get("type") in ("user", "assistant"):
            self.transcript.append(ev)

    def run_hooks(self, event, extra):
        ctxs = []
        for entry in self.hooks.get(event) or []:
            m = entry.get("matcher")
            if m and extra.get("tool_name") and not re.fullmatch(m, extra["tool_name"]):
                continue
            for hk in entry.get("hooks") or []:
                envelope = {"hook_event_name": event, "session_id": self.sid,
                            "transcript_path": self.tpath, "cwd": self.cwd, **extra}
                p = subprocess.run(hk["command"], shell=True, input=json.dumps(envelope),
                                   capture_output=True, text=True)
                out = (p.stdout or "").strip()
                if not out:
                    continue
                try:
                    ctx = (json.loads(out).get("hookSpecificOutput") or {}).get("additionalContext")
                except ValueError:
                    ctx = out
                if ctx:
                    ctxs.append(ctx)
        return ctxs

    def deliver(self, ctx, event):
        mode = self.mode
        if mode == "tool_result" and event != "PreToolUse":
            mode = "user_text"
        if mode == "user_text":
            self.emit({"type": "user", "message": {"role": "user", "content": [
                {"type": "text", "text": f"<system-reminder>{ctx}</system-reminder>"}]}})
            self.delivered.append(ctx)
        elif mode == "attachment":
            self.transcript.append({"type": "attachment", "attachment": {"type": "hook_context", "content": ctx}})
            self.delivered.append(ctx)
        elif mode == "host_event":
            self.emit({"type": "system", "subtype": "hook_response", "hook_event_name": event, "output": ctx},
                      to_transcript=False)
        # "tool_result" for PreToolUse is handled in tool(); "none" drops it.

    def tool(self, name, inp, apply):
        self.ids += 1
        tid = f"toolu_stub_{self.ids}"
        self.emit({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": tid, "name": name, "input": inp}]}})
        ctxs = self.run_hooks("PreToolUse", {"tool_name": name, "tool_input": inp})
        blocked = bool(ctxs) and env("H1_STUB_BLOCK") == "1"
        failed = env("H1_STUB_FAIL_TOOL") == "1"
        text = "blocked by hook" if blocked else ("tool failed" if failed else apply())
        content = text
        for c in ctxs:
            if self.mode == "tool_result":
                content += f"\n<system-reminder>{c}</system-reminder>"
                self.delivered.append(c)
        self.emit({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tid, "content": content,
             "is_error": blocked or failed}]}})
        if self.mode != "tool_result":
            for c in ctxs:
                self.deliver(c, "PreToolUse")
        self.turns += 1

    def run(self):
        self.emit({"type": "system", "subtype": "init", "session_id": self.sid, "cwd": self.cwd,
                   "model": env("H1_STUB_MODEL") or MODEL, "permissionMode": "acceptEdits",
                   "claude_code_version": VERSION.split()[0]}, to_transcript=False)
        if env("H1_STUB_NO_SESSIONSTART") != "1":
            for c in self.run_hooks("SessionStart", {"source": "startup"}):
                self.deliver(c, "SessionStart")
        self.emit({"type": "user", "message": {"role": "user", "content": self.prompt}})
        if env("H1_STUB_LEAK") == "1":
            self.tool("Read", {"file_path": os.path.join("..", "out", "nonce.txt")}, lambda: "read")
        notes = os.path.join(self.cwd, "notes.txt")
        if "Edit tool" in self.prompt:
            def apply_edit():
                with open(notes, "rb") as f:
                    b = f.read()
                with open(notes, "wb") as f:
                    f.write(b.replace(b"alpha", b"beta", 1))
                return "edited"
            self.tool("Edit", {"file_path": notes, "old_string": "alpha", "new_string": "beta"}, apply_edit)
        elif "Bash tool" in self.prompt:
            def apply_bash():
                with open(os.path.join(self.cwd, "bash_out.txt"), "wb") as f:
                    f.write(b"probe-ran\n")
                return ""
            self.tool("Bash", {"command": "echo probe-ran > bash_out.txt"}, apply_bash)
        tokens = [t for c in self.delivered for t in TOKEN.findall(c)]
        if env("H1_STUB_ECHO_FORCE") == "1":
            with open(os.path.join(self.cwd, "..", "out", "nonce.txt"), encoding="utf-8") as f:
                tokens = [f.read().strip()]
        echo = env("H1_STUB_ECHO") == "1" or env("H1_STUB_ECHO_FORCE") == "1"
        final = "OK " + (tokens[0] if tokens and echo else "NO-PROBE-TOKEN")
        self.emit({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": final}]}})
        for c in self.run_hooks("Stop", {"stop_hook_active": False}):
            self.deliver(c, "Stop")
            if env("H1_STUB_STOP_REENTER") == "1":
                self.turns += 1
                self.emit({"type": "assistant", "message": {"role": "assistant", "content": [
                    {"type": "text", "text": "continuing"}]}})
                self.run_hooks("Stop", {"stop_hook_active": True})
        self.emit({"type": "result", "subtype": "success", "is_error": False, "result": final,
                   "num_turns": self.turns, "session_id": self.sid, "permission_denials": []},
                  to_transcript=False)
        if env("H1_STUB_NO_TRANSCRIPT") != "1":
            with open(self.tpath, "w", encoding="utf-8") as f:
                for e in self.transcript:
                    f.write(json.dumps(e) + "\n")
        return 0


def main(argv):
    if "--version" in argv:
        print(VERSION)
        return 0
    return Host(argv[argv.index("-p") + 1]).run()


if __name__ == "__main__":
    sys.exit(main(sys.argv))

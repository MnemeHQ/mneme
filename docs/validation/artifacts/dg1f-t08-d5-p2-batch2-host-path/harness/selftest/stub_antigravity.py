"""Self-test stand-in for the Antigravity IDE: NOT Antigravity, never evidence.

usage (tests only): stub_antigravity.py <arm_dir>

It plays the operator's IDE session for one prepared H4a arm: it invokes the
workspace PreToolUse hook from ``ws/.agents/hooks.json`` once for a
``replace_file_content`` call, applies the hook output, writes a JSONL host
transcript at the envelope's ``transcriptPath``, and records what a UI would
have shown in ``hoststate/ui.json``.

Knobs (environment, test-only):
  STUB_AG_DECISION_REQUIRED=1  output without ``decision`` is invalid: fail closed
                               (deny the tool, show an error), as the current
                               public hooks page states ``decision`` is required
  STUB_AG_REASON_TO=agent|user|both|none   where a ``reason`` is shown (default agent)
  STUB_AG_STDERR_TO=user|none  whether hook stderr is shown in the UI (default none)
  STUB_AG_ECHO=0               the agent never echoes a nonce
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

NONCE_RE = re.compile(r"MNEME-PROBE-[0-9a-f]{16}")


def main(argv):
    d = Path(argv[1]).resolve()
    ws, state = d / "ws", d / "hoststate"
    state.mkdir(exist_ok=True)
    tpath = state / "transcript.jsonl"
    probe = json.loads((d / "out" / "probe.json").read_text(encoding="utf-8"))
    hook = json.loads((ws / ".agents" / "hooks.json").read_text(encoding="utf-8"))
    cmd = hook["mneme_probe"]["PreToolUse"][0]["hooks"][0]["command"]
    payload = {"toolCall": {"name": "replace_file_content",
                            "args": {"TargetFile": str(ws / "notes.txt"),
                                     "TargetContent": "alpha", "ReplacementContent": "beta"}},
               "stepIdx": 0, "conversationId": "stub-conv", "transcriptPath": str(tpath),
               "modelName": "stub", "workspacePaths": [str(ws)], "lastUserInput": probe["prompt"]}
    proc = subprocess.run(cmd, input=json.dumps(payload), capture_output=True, text=True,
                          shell=True, cwd=ws)
    ui, transcript = [], [{"role": "user", "content": probe["prompt"]}]
    try:
        out = json.loads(proc.stdout)
        valid = isinstance(out, dict)
    except json.JSONDecodeError:
        out, valid = {}, False
    if valid and os.environ.get("STUB_AG_DECISION_REQUIRED") == "1" and "decision" not in out:
        valid = False
    allowed = valid and out.get("decision") != "deny"
    reason_to = os.environ.get("STUB_AG_REASON_TO", "agent")
    if not valid:
        ui.append({"kind": "host_error", "text": "hook output invalid; tool call denied"})
    if allowed:
        (ws / "notes.txt").write_text("beta\n", encoding="utf-8", newline="\n")
        result = "Edited notes.txt."
        if out.get("reason") and reason_to in ("agent", "both"):
            result += "\n" + out["reason"]
        transcript.append({"role": "tool", "content": result})
    else:
        transcript.append({"role": "tool", "content": "Tool call denied by hook."})
    if out.get("reason") and reason_to in ("user", "both"):
        ui.append({"kind": "hook_reason", "text": out["reason"]})
    if proc.stderr and os.environ.get("STUB_AG_STDERR_TO", "none") == "user":
        ui.append({"kind": "hook_stderr", "text": proc.stderr})
    seen = NONCE_RE.findall(json.dumps(transcript))
    reply = seen[0] if (seen and os.environ.get("STUB_AG_ECHO") != "0") else "none"
    transcript.append({"role": "assistant", "content": reply})
    with open(tpath, "w", encoding="utf-8", newline="\n") as f:
        for e in transcript:
            f.write(json.dumps(e) + "\n")
    (state / "ui.json").write_text(json.dumps({"shown": ui, "tool_allowed": allowed,
                                               "permission_prompt_shown": False}),
                                   encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

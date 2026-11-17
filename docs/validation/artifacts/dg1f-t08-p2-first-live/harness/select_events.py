"""Reduce a stream-json transcript to the E2 selection used by #518.

usage: select_events.py <events.jsonl> <events.selected.jsonl>

Keeps the init event (model, cwd, permission mode, version), every
tool_use / tool_result item, assistant text, and the final result.
"""
import json
import sys

src, dst = sys.argv[1], sys.argv[2]
rows = []
with open(src, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            rows.append({k: ev.get(k) for k in
                         ("type", "subtype", "model", "cwd", "permissionMode", "claude_code_version")})
        elif t in ("assistant", "user"):
            for item in (ev.get("message") or {}).get("content") or []:
                if isinstance(item, dict) and item.get("type") in ("text", "tool_use", "tool_result"):
                    rows.append({"type": t, "item": item})
        elif t == "result":
            rows.append({k: ev.get(k) for k in
                         ("type", "subtype", "is_error", "result", "num_turns", "permission_denials")})
with open(dst, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")

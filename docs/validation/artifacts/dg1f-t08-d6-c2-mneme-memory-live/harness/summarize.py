"""Summarize D6 probes from their raw evidence (no inference from the hook alone).

usage: summarize.py <live_root> <summary_name> <probe> [<probe> ...]
Writes <live_root>/<summary_name> and prints it.

Batch 2 (C2): the override is configured in committed project settings, not in
the launching shell; the "Override as configured" column shows where.

Two flag columns, kept separate on purpose:

- Enforcement-outcome flags classify what Mneme did on the live host:
  SILENT_MEMORY_SKIP = for one Edit, the hook process saw an MNEME_MEMORY
  override, find_memory returned no memory, the hook exited 0 without
  evaluating, and the host applied the edit (tool_result not an error and
  repo_a/app.py hash changed). This is an observed enforcement outcome, not a
  harness fault.
- Harness / fail-open flags report harness or transport faults: the hook's
  checker failing open, wrapper log errors, wrapper load defects, an edit with
  no hook record, and self-test runs.
"""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
summary_name = sys.argv[2]
probes = sys.argv[3:]


def obs(out):
    d = {}
    for line in (out / "observer.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] in ("BEFORE", "AFTER"):
            d[(parts[0], parts[1])] = parts[2]
        elif "=" in line and not line.startswith(" "):
            k, _, v = line.partition("=")
            d.setdefault(k.strip(), v.strip())
    return d


def jl(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


HEADER = ["Probe", "Init model", "Topology / sources", "Override as configured (where)",
          "MNEME_MEMORY in launching shell", "MNEME_MEMORY seen by hook (is_file)",
          "find_memory start -> returned", "Hook exit", "Host Edit result", "A/app.py before -> after",
          "Post-hoc vs hook-selected", "Post-hoc vs A's own memory", "Enforcement-outcome flags",
          "Harness / fail-open flags"]
# Separator derived from the header so the column counts always match
# (the as-run C2 summary had one separator column too many).
rows = ["| " + " | ".join(HEADER) + " |", "|" + "---|" * len(HEADER)]
for name in probes:
    out = root / name / "out"
    o = obs(out)
    hl = [h for h in jl(out / "hook-log.jsonl") if h.get("tool_name") == "Edit"]
    sel = jl(out / "events.selected.jsonl")
    edit_ids = {r["item"]["id"] for r in sel if r.get("item", {}).get("type") == "tool_use" and r["item"].get("name") == "Edit"}
    results = [r["item"] for r in sel if r.get("item", {}).get("type") == "tool_result" and r["item"].get("tool_use_id") in edit_ids]
    host = "; ".join(("is_error=true" if r.get("is_error") else "applied (no error)") for r in results) or "no Edit attempted"
    hook_seen = "; ".join(f"{h.get('MNEME_MEMORY')} ({h['hook_env_view'].get('MNEME_MEMORY_is_file')})" for h in hl) or "no hook record"
    fm = "; ".join(" / ".join(f"{c['start']} -> {c['returned']}" for c in h.get("find_memory_calls") or []) or "(none)" for h in hl) or "-"
    ex = ", ".join(str(h.get("exit")) for h in hl) or "-"
    ph = (json.loads((out / "posthoc.json").read_text(encoding="utf-8")) if (out / "posthoc.json").exists() else [])

    def fmt(c):
        return c.get("note") or f"{c.get('verdict')} {c.get('violations')} exit {c.get('exit')}"
    phs = "; ".join(fmt(p["against_hook_selected_memory"]) for p in ph) or "-"
    pha = "; ".join(fmt(p["against_repo_a_own_memory"]) for p in ph) or "-"
    b, a = o.get(("BEFORE", "A/app.py"), "?"), o.get(("AFTER", "A/app.py"), "?")
    changed = "UNCHANGED" if a == b else "CHANGED"
    sess_key = "A/.claude/settings" if "topology=own" in o.get("probe", "") else "B/.claude/settings"
    outcome = []
    by_id = {r.get("tool_use_id"): r for r in results}
    for h in hl:
        calls = h.get("find_memory_calls") or []
        r = by_id.get(h.get("tool_use_id"))
        if (h.get("MNEME_MEMORY")
                and calls and calls[-1].get("returned") is None and h.get("selected_memory") is None
                and h.get("exit") == 0
                and r is not None and not r.get("is_error")
                and changed == "CHANGED"):
            outcome.append("SILENT_MEMORY_SKIP")
    flags = []
    if any("Failing open" in (h.get("stderr") or "") for h in hl): flags.append("HOOK FAILED OPEN")
    if (out / "hook-log.jsonl.wrapper-errors").exists(): flags.append("WRAPPER LOG ERROR")
    if any("t08-harness:" in str(r.get("content")) for r in results): flags.append("HARNESS DEFECT")
    if results and not hl: flags.append("EDIT WITHOUT HOOK RECORD")
    if "SELFTEST" in (out / "observer.txt").read_text(encoding="utf-8"): flags.append("SELFTEST (not evidence)")
    sb, sa = o.get(("BEFORE", sess_key), "?"), o.get(("AFTER", sess_key), "?")
    settings_note = "" if sb == sa else " (session settings CHANGED during run)"
    where = o.get("settings_env_repo", "none")
    rows.append(f"| {name} | {o.get('init_model')} | {o.get('probe', '').split('topology=')[-1]} / {o.get('setting_sources')} | {o.get('override_configured', '-')} (settings env in: {where}){settings_note} | {o.get('MNEME_MEMORY(launching shell)')} | {hook_seen} | {fm} | {ex} | {host} | {b[:8]} -> {a[:8]} ({changed}) | {phs} | {pha} | {", ".join(outcome) or "none"} | {", ".join(flags) or "none"} |")

md = "\n".join(rows) + "\n"
(root / summary_name).write_text(md, encoding="utf-8")
print(md)

"""Copy H1 live evidence into the repository, selected and redacted.

usage: collect_h1.py <live_root> <dest_dir> <python_exe> <claude_bin>

Added AFTER the live H1 run (2026-10-17). It is not part of the as-run
harness hashed in run_h1.log, and it never re-classifies: each outcome.json is
published exactly as run_h1.sh's classify_h1.py wrote it, apart from path
redaction.

Published per arm, when present: observer.txt, prompt.txt, probe.json,
hook-registration.json, hook-log.jsonl, nonce.txt, outcome.json (emitter
arms), events.selected.jsonl and transcript.selected.jsonl. Batch level:
summary_h1.md, run_h1.log and H1_DONE.

Selection. The raw events.jsonl, transcript.jsonl and claude.stderr.txt are NOT
published: they carry the operator's environment (plugins, MCP servers,
skills, agent and tool listings) and model thinking. MANIFEST.json records
their SHA-256 and size. The selected files keep everything the classifier
used:
  events:     init (model, version, permission mode, cwd, session); every
              other `system` event in full (redacted); assistant text and
              tool_use (thinking content omitted, marked); user text and
              tool_result; the result event.
  transcript: user and assistant entries (thinking omitted) and every
              `attachment` entry whose type starts with `hook_`. Other entry
              types are counted in MANIFEST.json, not published.

Redaction: live root -> <LIVE>, harness directory -> <HARNESS>, interpreter ->
<PYTHON>, claude binary -> <CLAUDE_BIN>, home directory -> <HOME>; session ids ->
<SESSION>; uuid/parentUuid, requestId and signature keys dropped; other UUIDs ->
<UUID>; tool_use ids -> stable per-arm pseudonyms. A leak scan fails the run
(exit 1) if any drive path, /c/ path, Users path or e-mail address survives.
"""
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

ARMS = ("H1a-edit", "H1a-edit-ctl", "H1a-bash", "H1a-bash-ctl",
        "H1b-start", "H1b-start-ctl", "H1c-stop", "H1c-stop-ctl")
COPY = ("observer.txt", "prompt.txt", "probe.json", "hook-registration.json",
        "hook-log.jsonl", "nonce.txt", "outcome.json")
RAW = ("events.jsonl", "transcript.jsonl", "claude.stderr.txt")
DROP_KEYS = {"uuid", "parentUuid", "requestId", "signature", "gitBranch", "userType",
             "entrypoint", "promptId", "leafUuid"}
SESSION_KEYS = {"session_id", "sessionId"}
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
LEAK = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:(\\\\|\\|/)|(?<![A-Za-z0-9<])/[a-z]/|Users[\\/]|[\w.+-]+@[\w-]+\.\w+", re.I)


def forms(p):
    """Every spelling of a Windows path that can appear in the evidence."""
    p = str(Path(p))
    out = {p, p.replace("\\", "\\\\"), p.replace("\\", "/")}
    if len(p) > 2 and p[1] == ":":
        out.add("/" + p[0].lower() + p[2:].replace("\\", "/"))
    return sorted(out, key=len, reverse=True)


class Redactor:
    def __init__(self, live, harness, py, cbin):
        subs = []
        for tag, path in (("<LIVE>", live), ("<HARNESS>", harness), ("<PYTHON>", py),
                          ("<CLAUDE_BIN>", cbin), ("<HOME>", os.path.expanduser("~"))):
            for f in forms(path):
                subs.append((re.compile(re.escape(f), re.I), tag))
        self.subs = subs
        self.ids = {}

    def text(self, s):
        for rx, tag in self.subs:
            s = rx.sub(tag, s)
        return UUID.sub("<UUID>", s)

    def tool_id(self, tid):
        if tid not in self.ids:
            self.ids[tid] = f"toolu_{len(self.ids) + 1:03d}"
        return self.ids[tid]

    def obj(self, o, key=None):
        if isinstance(o, dict):
            out = {}
            for k, v in o.items():
                if k in DROP_KEYS:
                    continue
                if k in SESSION_KEYS:
                    out[k] = "<SESSION>"
                elif k in ("id", "tool_use_id", "toolUseID") and isinstance(v, str) and v.startswith("toolu_"):
                    out[k] = self.tool_id(v)
                else:
                    out[k] = self.obj(v, k)
            return out
        if isinstance(o, list):
            return [self.obj(v, key) for v in o]
        if isinstance(o, str):
            return self.text(o)
        return o


def items(entry):
    c = (entry.get("message") or {}).get("content")
    return c if isinstance(c, list) else None


def strip_thinking(entry):
    e = json.loads(json.dumps(entry))
    its = items(e)
    if its is not None:
        e["message"]["content"] = [
            {"type": "thinking", "omitted": True} if isinstance(i, dict) and i.get("type") in ("thinking", "redacted_thinking") else i
            for i in its]
    return e


def select_events(rows):
    out = []
    for e in rows:
        t = e.get("type")
        if t == "system" and e.get("subtype") == "init":
            out.append({k: e.get(k) for k in ("type", "subtype", "model", "claude_code_version",
                                               "permissionMode", "cwd", "session_id")})
        elif t in ("system", "result"):
            out.append({k: v for k, v in e.items() if not (t == "result" and k in ("usage", "modelUsage"))})
        elif t in ("assistant", "user"):
            out.append({"type": t, "message": {"role": (e.get("message") or {}).get("role"),
                                               "content": strip_thinking(e)["message"]["content"]}})
    return out


def select_transcript(rows, skipped):
    out = []
    for i, e in enumerate(rows):
        t = e.get("type")
        if t in ("user", "assistant"):
            s = strip_thinking(e)
            out.append({"line": i, "type": t, "message": {"role": (s.get("message") or {}).get("role"),
                                                         "content": (s.get("message") or {}).get("content")}})
        elif t == "attachment" and str((e.get("attachment") or {}).get("type", "")).startswith("hook_"):
            out.append({"line": i, "type": t, "attachment": e.get("attachment")})
        else:
            key = f"{t}:{(e.get('attachment') or {}).get('type')}" if t == "attachment" else str(t)
            skipped[key] = skipped.get(key, 0) + 1
    return out


def read_jsonl(p):
    rows = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_text(dst, text, red, published):
    t = red.text(text)
    m = LEAK.search(t)
    if m:
        raise SystemExit(f"LEAK in {dst}: {m.group(0)!r}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(t, encoding="utf-8", newline="\n")
    published[str(dst)] = hashlib.sha256(dst.read_bytes()).hexdigest()


def sha_size(p):
    return {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} if p.exists() else None


def main(argv):
    live, dest, py, cbin = Path(argv[1]), Path(argv[2]), argv[3], argv[4]
    harness = Path(__file__).resolve().parent
    red = Redactor(live, harness, py, cbin)
    if dest.exists():
        raise SystemExit(f"destination exists, refusing to overwrite: {dest}")
    published, manifest = {}, {"arms": {}, "batch": {}}
    for arm in ARMS:
        src = live / arm / "out"
        if "selftest=1" in (src / "observer.txt").read_text(encoding="utf-8"):
            raise SystemExit(f"{arm}: self-test output is not evidence")
        red.ids = {}  # tool-use pseudonyms are per arm
        entry = {"published": {}, "raw_not_published": {}, "transcript_entries_not_published": {}}
        for name in COPY:
            p = src / name
            if not p.exists():
                entry["published"][name] = None
                continue
            if name.endswith(".json") or name.endswith(".jsonl"):
                if name.endswith(".jsonl"):
                    body = "".join(json.dumps(red.obj(r)) + "\n" for r in read_jsonl(p))
                else:
                    body = json.dumps(red.obj(json.loads(p.read_text(encoding="utf-8"))), indent=2) + "\n"
            else:
                body = p.read_text(encoding="utf-8")
            write_text(dest / arm / name, body, red, published)
            entry["published"][name] = published[str(dest / arm / name)]
        ev = select_events(read_jsonl(src / "events.jsonl"))
        write_text(dest / arm / "events.selected.jsonl", "".join(json.dumps(red.obj(r)) + "\n" for r in ev), red, published)
        entry["published"]["events.selected.jsonl"] = published[str(dest / arm / "events.selected.jsonl")]
        skipped = {}
        tr = select_transcript(read_jsonl(src / "transcript.jsonl"), skipped)
        write_text(dest / arm / "transcript.selected.jsonl", "".join(json.dumps(red.obj(r)) + "\n" for r in tr), red, published)
        entry["published"]["transcript.selected.jsonl"] = published[str(dest / arm / "transcript.selected.jsonl")]
        entry["transcript_entries_not_published"] = skipped
        for name in RAW:
            entry["raw_not_published"][name] = sha_size(src / name)
        manifest["arms"][arm] = entry
    for name in ("summary_h1.md", "run_h1.log", "H1_DONE"):
        p = live / name
        if p.exists():
            write_text(dest / name, p.read_text(encoding="utf-8"), red, published)
            manifest["batch"][name] = published[str(dest / name)]
        else:
            manifest["batch"][name] = None
    manifest["collector"] = {"file": "harness/collect_h1.py",
                             "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                             "added_after_live_run": True,
                             "reclassified": False}
    body = json.dumps(manifest, indent=2) + "\n"
    write_text(dest / "MANIFEST.json", body.replace(str(dest), "<DEST>"), red, published)
    print(f"collected {len(published)} files into {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

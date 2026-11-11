"""Copy Amendment A2 live evidence into the repository, selected and redacted.

usage: collect_a2.py <live_root> <dest_dir> <python_exe> <claude_bin>

Added AFTER the A2 live run (2026-11-11). It is not part of the as-run harness
hashed in run_h1.log, and it never re-classifies: each outcome.json is published
exactly as classify_h1.py wrote it during the run, apart from path redaction.

Selection, redaction and the leak scan are collect_h1.py's (imported, unchanged),
applied to the six A2 arms. Two A2-specific additions, both because Claude Code
2.1.310 records the hook context in places the 2.1.202 selection did not cover:

  1. For a `hook_*` attachment entry, the top-level `rendered` and `renderedRole`
     fields are published with it (they hold the host's rendering of that hook's
     output). `rendered` on any other attachment type is never published: it can
     carry environment details.
  2. An `api-request-blob` entry whose text contains the arm's nonce is published
     as an EXCERPT: its type, hash, message role, the number of content items and
     text lines, and only the text line(s) containing the nonce. Every other
     `api-request-blob` entry, and every other line of these, stays unpublished
     and is counted in MANIFEST.json.

One extra redaction: Claude Code's encoded project directory for the live root
(`C--dev-d5p2-h1-a2-live`) becomes <LIVE_PROJECT>. The raw events.jsonl,
transcript.jsonl and claude.stderr.txt are not published; MANIFEST.json records
their SHA-256 and size.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_h1 as c  # noqa: E402

ARMS = ("H1a-edit-ctl", "H1a-edit", "H1a-bash-ctl", "H1a-bash", "H1b-start-ctl", "H1b-start")
BATCH = ("summary_h1.md", "run_h1.log", "H1_DONE")
LIVE_PROJECT = re.compile(re.escape("C--dev-d5p2-h1-a2-live"), re.I)


def select_transcript_a2(rows, skipped, nonce):
    out = []
    for i, e in enumerate(rows):
        t = e.get("type")
        att = e.get("attachment") or {}
        if t in ("user", "assistant"):
            s = c.strip_thinking(e)
            out.append({"line": i, "type": t, "message": {"role": (s.get("message") or {}).get("role"),
                                                         "content": (s.get("message") or {}).get("content")}})
        elif t == "attachment" and str(att.get("type", "")).startswith("hook_"):
            rec = {"line": i, "type": t, "attachment": att}
            for k in ("rendered", "renderedRole"):
                if k in e:
                    rec[k] = e[k]
            out.append(rec)
        elif t == "api-request-blob" and nonce and nonce in json.dumps(e):
            msg = e.get("message") or {}
            items = msg.get("content") if isinstance(msg.get("content"), list) else []
            lines, total = [], 0
            for it in items:
                text = it.get("text", "") if isinstance(it, dict) else ""
                total += text.count("\n") + 1 if text else 0
                lines += [ln for ln in text.split("\n") if nonce in ln]
            out.append({"line": i, "type": t, "hash": e.get("hash"),
                        "message": {"role": msg.get("role"),
                                    "content": [{"type": "text", "text": ln} for ln in lines]},
                        "excerpt": {"content_items": len(items), "text_lines_total": total,
                                    "published": "only the text line(s) containing this arm's nonce"}})
            skipped["api-request-blob (excerpted)"] = skipped.get("api-request-blob (excerpted)", 0) + 1
        else:
            key = f"{t}:{att.get('type')}" if t == "attachment" else str(t)
            skipped[key] = skipped.get(key, 0) + 1
    return out


def main(argv):
    live, dest, py, cbin = Path(argv[1]), Path(argv[2]), argv[3], argv[4]
    harness = Path(__file__).resolve().parent
    red = c.Redactor(live, harness, py, cbin)
    red.subs = [(LIVE_PROJECT, "<LIVE_PROJECT>")] + red.subs
    if dest.exists():
        raise SystemExit(f"destination exists, refusing to overwrite: {dest}")
    published, manifest = {}, {"arms": {}, "batch": {}}
    for arm in ARMS:
        src = live / arm / "out"
        if "selftest=1" in (src / "observer.txt").read_text(encoding="utf-8"):
            raise SystemExit(f"{arm}: self-test output is not evidence")
        red.ids = {}
        entry = {"published": {}, "raw_not_published": {}, "transcript_entries_not_published": {}}
        for name in c.COPY:
            p = src / name
            if not p.exists():
                entry["published"][name] = None
                continue
            if name.endswith(".jsonl"):
                body = "".join(json.dumps(red.obj(r)) + "\n" for r in c.read_jsonl(p))
            elif name.endswith(".json"):
                body = json.dumps(red.obj(json.loads(p.read_text(encoding="utf-8"))), indent=2) + "\n"
            else:
                body = p.read_text(encoding="utf-8")
            c.write_text(dest / arm / name, body, red, published)
            entry["published"][name] = published[str(dest / arm / name)]
        ev = c.select_events(c.read_jsonl(src / "events.jsonl"))
        c.write_text(dest / arm / "events.selected.jsonl", "".join(json.dumps(red.obj(r)) + "\n" for r in ev), red, published)
        entry["published"]["events.selected.jsonl"] = published[str(dest / arm / "events.selected.jsonl")]
        nonce = (src / "nonce.txt").read_text(encoding="utf-8").strip() if (src / "nonce.txt").exists() else None
        skipped = {}
        tr = select_transcript_a2(c.read_jsonl(src / "transcript.jsonl"), skipped, nonce)
        c.write_text(dest / arm / "transcript.selected.jsonl", "".join(json.dumps(red.obj(r)) + "\n" for r in tr), red, published)
        entry["published"]["transcript.selected.jsonl"] = published[str(dest / arm / "transcript.selected.jsonl")]
        entry["transcript_entries_not_published"] = skipped
        for name in c.RAW:
            entry["raw_not_published"][name] = c.sha_size(src / name)
        manifest["arms"][arm] = entry
    for name in BATCH:
        p = live / name
        if p.exists():
            c.write_text(dest / name, p.read_text(encoding="utf-8"), red, published)
            manifest["batch"][name] = published[str(dest / name)]
            manifest["batch"][name + ".raw"] = c.sha_size(p)
        else:
            manifest["batch"][name] = None
    manifest["collector"] = {"file": "harness/collect_a2.py",
                             "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                             "reuses": "harness/collect_h1.py",
                             "reuses_sha256": hashlib.sha256(Path(c.__file__).read_bytes()).hexdigest(),
                             "added_after_live_run": True,
                             "reclassified": False}
    body = json.dumps(manifest, indent=2) + "\n"
    c.write_text(dest / "MANIFEST.json", body.replace(str(dest), "<DEST>"), red, published)
    print(f"collected {len(published)} files into {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

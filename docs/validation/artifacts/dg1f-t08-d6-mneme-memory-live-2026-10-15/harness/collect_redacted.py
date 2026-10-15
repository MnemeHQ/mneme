"""Copy D6 live evidence into the repository with local paths and identifiers redacted.

usage: collect_redacted.py <live_root> <artifact_dir> <python_exe> <mneme_src> <claude_bin> <probe> [...]

Published per probe: observer.txt, prompt.txt, hook-registration.json,
hook-log.jsonl, events.selected.jsonl, posthoc.json. Not published: the raw
events.jsonl and claude.stderr.txt (their SHA-256 is listed in MANIFEST.json).

Redactions: live root -> <LIVE>, interpreter -> <PYTHON>, Mneme source tree ->
<MNEME_SRC>, claude binary -> <CLAUDE_BIN>, tool_use ids -> stable per-probe
pseudonyms, session ids -> <SESSION>, pid/ppid -> null. A leak scan fails the
run (exit 1) if any local path or raw identifier survives.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

live, dest, py, src, cbin = (sys.argv[1], Path(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5])
probes = sys.argv[6:]
PUBLISHED = ["observer.txt", "prompt.txt", "hook-registration.json", "hook-log.jsonl",
             "events.selected.jsonl", "posthoc.json"]
RAW_ONLY = ["events.jsonl", "claude.stderr.txt"]


def variants(p):
    win = p.replace("/", "\\")
    fwd = win.replace("\\", "/")
    unix = "/" + fwd[0].lower() + fwd[2:] if re.match(r"^[A-Za-z]:", fwd) else fwd
    return {win, win.replace("\\", "\\\\"), fwd, unix}


SUBS = []
for raw, tag in ((src, "<MNEME_SRC>"), (py, "<PYTHON>"), (cbin, "<CLAUDE_BIN>"), (live, "<LIVE>")):
    for v in sorted(variants(raw), key=len, reverse=True):
        SUBS.append((v, tag))

LEAKS = [re.compile(p, re.I) for p in (r"Users[\\/]+hi\b", r"[A-Za-z]:[\\/]+dev[\\/]", r"/c/dev/",
                                         r"toolu_0[0-9A-Za-z]{10,}", r"AppData", r"WindowsApps")]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def redact(text, idmap, probe):
    for old, new in SUBS:
        text = text.replace(old, new)

    def tid(m):
        return idmap.setdefault(m.group(0), f"toolu_{probe}_{len(idmap) + 1}")
    text = re.sub(r"toolu_[0-9A-Za-z]{10,}", tid, text)
    text = re.sub(r'("session_id": )"[^"]*"', r'\1"<SESSION>"', text)
    text = re.sub(r'("p?pid": )\d+', r"\1null", text)
    return text


manifest = {"live_root": "<LIVE>", "probes": {}, "root_files": {}}
bad = []
for probe in probes:
    out = Path(live) / probe / "out"
    d = dest / probe
    d.mkdir(parents=True, exist_ok=True)
    idmap = {}
    entry = {"published": {}, "raw_not_published": {}}
    for name in PUBLISHED:
        text = redact((out / name).read_text(encoding="utf-8"), idmap, probe)
        (d / name).write_text(text, encoding="utf-8", newline="\n")
        entry["published"][name] = {"source_sha256": sha(out / name), "published_sha256": sha(d / name)}
        bad += [f"{probe}/{name}: {rx.pattern}" for rx in LEAKS if rx.search(text)]
    for name in RAW_ONLY:
        p = out / name
        entry["raw_not_published"][name] = {"sha256": sha(p), "bytes": p.stat().st_size} if p.exists() else None
    manifest["probes"][probe] = entry
for name in ("summary.md", "run_d6_c1.log", "C1_DONE"):
    p = Path(live) / name
    text = redact(p.read_text(encoding="utf-8"), {}, "summary")
    (dest / name).write_text(text, encoding="utf-8", newline="\n")
    manifest["root_files"][name] = {"source_sha256": sha(p), "published_sha256": sha(dest / name)}
    bad += [f"{name}: {rx.pattern}" for rx in LEAKS if rx.search(text)]
(dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
if bad:
    print("LEAK SCAN FAILED:\n  " + "\n  ".join(bad))
    sys.exit(1)
print(f"collected {len(probes)} probes into {dest}; leak scan clean")

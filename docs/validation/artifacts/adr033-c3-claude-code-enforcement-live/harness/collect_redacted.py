"""Copy C3 probe evidence into the repository, redacted, with a manifest.

usage: collect_redacted.py <live-root> <dest-dir> [--home <path>] [--mneme-src <path>]
                            [--probes <glob>[,<glob>...]] [--extra <file>[,<file>...]]

For each probe directory with ``out/outcome.json``, copies the evidence files
listed in FILES, replacing the live root, home directory, user name and Mneme
source path with placeholders. ``--probes`` selects probe directories by globs
relative to the live root (default ``*``; for example ``D-2-*`` or
``_archive-x/D-2-*``) when one live root holds several batches. ``--extra``
also copies top-level live-root files (batch summaries) into the destination,
redacted the same way. Both are recorded under ``selection`` in the manifest.
The host name is redacted to ``<HOST>``. Screen recordings are never copied
(their SHA-256 is in outcome.json); they stay with the operator.

Session transcripts (``transcript.jsonl``, ``transcript-<n>.jsonl``) are never
published raw: they carry Claude Code's system prompt, the operator's tool,
agent and skill listings, and model thinking. As in the H1 collector
(``collect_h1.py``), each is published as ``<name>.selected.jsonl`` holding
user and assistant entries (thinking omitted) and every ``hook_*`` attachment:
everything the F-R2 classification uses. The manifest records the raw file's
SHA-256 and size and counts the entry types not published.

Fails closed: if any published file still contains a credential-shaped string
(GitHub or Anthropic tokens, Authorization headers, private keys) the
collection stops and writes nothing further. Writes ``MANIFEST.json`` with the
source and published SHA-256 of every file and this collector's own hash.
"""
from __future__ import annotations

import getpass
import hashlib
import json
import re
import socket
import sys
from pathlib import Path

FILES = ("observer.txt", "prompt.txt", "setup.json", "hook-registration.json",
         "events.jsonl", "hook-log.jsonl", "outcome.json", "target.before",
         "target.after", "operator-attestation.txt", "netcap-sni.txt",
         "transcript.jsonl")
LEAKS = re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
                   r"sk-ant-[A-Za-z0-9_\-]{10,}|Authorization:\s*\S+|"
                   r"-----BEGIN [A-Z ]*PRIVATE KEY-----)")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def variants(path: str) -> list[str]:
    p = path.rstrip("\\/")
    # Raw, forward-slash, JSON-escaped, and JSON-in-JSON escaped (tool results
    # quoting a JSON string, as in events.jsonl and session transcripts).
    out = {p, p.replace("\\", "/"), p.replace("\\", "\\\\"), p.replace("\\", "\\\\\\\\"),
           p.replace("/", "\\")}
    if len(p) > 1 and p[1] == ":":
        out.add("/" + p[0].lower() + p[2:].replace("\\", "/"))
    return sorted(out, key=len, reverse=True)


def select_transcript(text: str) -> tuple[str, dict]:
    """The H1 selection rule (collect_h1.select_transcript), as JSONL text."""
    rows, skipped = [], {}
    for index, line in enumerate(text.splitlines()):
        try:
            entry = json.loads(line)
        except ValueError:
            skipped["unparsed"] = skipped.get("unparsed", 0) + 1
            continue
        kind = entry.get("type")
        att = entry.get("attachment") or {}
        if kind in ("user", "assistant"):
            message = entry.get("message") or {}
            content = message.get("content")
            if isinstance(content, list):
                content = [{"type": block["type"], "omitted": True}
                           if isinstance(block, dict)
                           and block.get("type") in ("thinking", "redacted_thinking")
                           else block for block in content]
            rows.append({"line": index, "type": kind,
                         "message": {"role": message.get("role"), "content": content}})
        elif kind == "attachment" and str(att.get("type", "")).startswith("hook_"):
            rows.append({"line": index, "type": kind, "attachment": att})
        else:
            key = f"attachment:{att.get('type')}" if kind == "attachment" else str(kind)
            skipped[key] = skipped.get(key, 0) + 1
    return "".join(json.dumps(row) + "\n" for row in rows), skipped


def main() -> int:
    args = sys.argv[1:]
    live, dest = Path(args[0]), Path(args[1])
    home = args[args.index("--home") + 1] if "--home" in args else str(Path.home())
    src = args[args.index("--mneme-src") + 1] if "--mneme-src" in args else None
    replacements = [(v, "<LIVE>") for v in variants(str(live))]
    if src:
        replacements += [(v, "<MNEME_SRC>") for v in variants(src)]
    replacements += [(v, "<HOME>") for v in variants(home)]
    user = getpass.getuser()
    host = socket.gethostname()
    probes = args[args.index("--probes") + 1].split(",") if "--probes" in args else ["*"]
    extra = args[args.index("--extra") + 1].split(",") if "--extra" in args else []
    manifest = {"collector_sha256": sha(Path(__file__).read_bytes()), "files": []}
    if "--probes" in args or extra:
        manifest["selection"] = {"probes": probes, "extra": extra}
    dest.mkdir(parents=True, exist_ok=True)
    outcomes = sorted({o for pattern in probes for o in live.glob(f"{pattern}/out/outcome.json")})
    work = [(out.parent.name, out, (*FILES, *sorted(p.name for p in (
                *out.glob("transcript-*.jsonl"), *out.glob("pair-*.json")))))
            for out in (o.parent for o in outcomes)]
    if extra:
        work.append(("", live, tuple(extra)))
    names = [w[0] for w in work if w[0]]
    if len(names) != len(set(names)):
        print(f"ABORT: two selected probes share a name: {sorted(names)}", file=sys.stderr)
        return 1
    for probe_name, out, files in work:
        probe_dest = dest / probe_name if probe_name else dest
        for name in files:
            source = out / name
            if not source.exists():
                continue
            raw = source.read_bytes()
            text = raw.decode("utf-8", errors="replace")
            record = {}
            if re.fullmatch(r"transcript(-\d+)?\.jsonl", name):
                text, skipped = select_transcript(text)
                name = name[:-len(".jsonl")] + ".selected.jsonl"
                record = {"source_size": len(raw), "entries_not_published": skipped}
            for old, new in replacements:
                text = text.replace(old, new)
            text = re.sub(rf"\b{re.escape(user)}\b", "<USER>", text)
            text = re.sub(rf"\b{re.escape(host)}\b", "<HOST>", text, flags=re.I)
            if LEAKS.search(text):
                print(f"ABORT: credential-shaped string in {source}; nothing more written",
                      file=sys.stderr)
                return 1
            published = text.encode("utf-8")
            probe_dest.mkdir(parents=True, exist_ok=True)
            (probe_dest / name).write_bytes(published)
            manifest["files"].append({"path": f"{probe_name}/{name}" if probe_name else name,
                                      "source_sha256": sha(raw),
                                      "published_sha256": sha(published), **record})
    (dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"collected {len(manifest['files'])} files into {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

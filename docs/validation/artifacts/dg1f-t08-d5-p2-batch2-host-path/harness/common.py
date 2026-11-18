"""Shared helpers for the batch-2 (H4a, H6a, H6b) channel-probe harness.

Harness-only. Nothing here imports or runs Mneme code (probe scope section 3
step 1), so it needs no ``[layer1-freeze]`` amendment.
"""
import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

NONCE_RE = re.compile(r"MNEME-PROBE-[0-9a-f]{16}")

# Probe scope section 6 labels.
DELIVERED_TO_AGENT = "DELIVERED_TO_AGENT"
DELIVERED_TO_USER_ONLY = "DELIVERED_TO_USER_ONLY"
DELIVERED_WITH_SIDE_EFFECT = "DELIVERED_WITH_SIDE_EFFECT"
NOT_DELIVERED = "NOT_DELIVERED"
NO_NONBLOCKING_CHANNEL = "NO_NONBLOCKING_CHANNEL"
NOT_EXECUTED = "NOT_EXECUTED"
INCONCLUSIVE = "INCONCLUSIVE"
PASSING = (DELIVERED_TO_AGENT, DELIVERED_TO_USER_ONLY)
FAILING = (NOT_DELIVERED, DELIVERED_WITH_SIDE_EFFECT, NO_NONBLOCKING_CHANNEL)

RULES = "batch-2 as-built table (no reviewed extensions)"


def new_nonce() -> str:
    return "MNEME-PROBE-" + secrets.token_hex(8)


def notice(nonce: str, path: str) -> str:
    return (f"{nonce} This is a Mneme {path} channel-probe notice. "
            "It carries no instruction and requires no action.")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path, default=None):
    p = Path(path)
    if not p.is_file():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path, obj) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")


def append_jsonl(path, rec) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


def read_jsonl(path):
    p = Path(path)
    if not p.is_file():
        return []
    out = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            out.append({"_unparsed_line": i, "_raw": line})
    return out


def walk_strings(obj, path="$"):
    """Yield (json_path, string) for every string inside ``obj``."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_strings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_strings(v, f"{path}[{i}]")


def tree_text_contains(root, needle: str) -> list:
    """Every file under ``root`` whose bytes contain ``needle``."""
    hits = []
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            try:
                if needle.encode("utf-8") in p.read_bytes():
                    hits.append(str(p.relative_to(root)))
            except OSError:
                hits.append(f"{p.relative_to(root)} (unreadable)")
    return hits


# Files that would make a host load configuration from above the live root.
LOADABLE_ABOVE = (".git", ".mneme", ".agents/hooks.json", ".hermes/plugins",
                  ".claude/settings.json")


def guard_live_root(root) -> list:
    """Probe scope section 7: a disposable root outside any Git checkout and
    with no ancestor holding a memory or host configuration that could load
    (``LOADABLE_ABOVE``). Returns a list of problems (empty: acceptable)."""
    problems = []
    r = Path(root).resolve()
    if (r / ".git").exists():
        problems.append(f"live root {r} is a Git checkout")
    for anc in r.parents:
        for marker in LOADABLE_ABOVE:
            if (anc / marker).exists():
                problems.append(f"ancestor {anc} has {marker}")
    return problems


def antigravity_global_hooks(home=None) -> list:
    """Section 7: no user-level hook source may load beside the workspace's.
    Antigravity also reads ``~/.gemini/config/hooks.json`` and installed
    plugins' ``hooks.json`` (public hooks page)."""
    base = Path(home or Path.home()) / ".gemini" / "config"
    found = [base / "hooks.json"] if (base / "hooks.json").is_file() else []
    if (base / "plugins").is_dir():
        found += sorted((base / "plugins").rglob("hooks.json"))
    return [f"user-level Antigravity hook source present: {p}" for p in found]


def guard_env(environ=None) -> list:
    """Section 7 guards on the launching environment."""
    env = os.environ if environ is None else environ
    problems = []
    if env.get("CLAUDECODE"):
        problems.append("CLAUDECODE is set: run from an external terminal, never inside Claude Code")
    for k in sorted(env):
        if k.startswith("MNEME_"):
            problems.append(f"{k} is set: no Mneme variable may reach a probe")
    return problems


def leak_scan(root, credential_vars, environ=None) -> list:
    """Section 7/8: no credential value may appear anywhere in the evidence."""
    env = os.environ if environ is None else environ
    leaks = []
    for var in credential_vars:
        val = env.get(var)
        if val and len(val) >= 8:
            for hit in tree_text_contains(root, val):
                leaks.append(f"value of {var} found in {hit}")
    return leaks


def summarize_path(path_id: str, candidates: list) -> dict:
    """Combine per-candidate outcomes for one path, in pre-registered order.

    Shape discovery (probe scope section 5) tries candidates in a fixed
    order. The path takes the first PASSING candidate as its bound shape
    (shape binding, section 3 step 5). With none passing, an unresolved
    candidate (NOT_EXECUTED, INCONCLUSIVE) makes the path unresolved, to be
    re-run first (D4). Otherwise, if no candidate was accepted by the host
    without side effects, the path is NO_NONBLOCKING_CHANNEL (section 6).
    """
    labels = [c.get("label") for c in candidates]
    for c in candidates:
        if c.get("label") in PASSING:
            return {"path": path_id, "label": c["label"], "bound_shape": c.get("candidate"),
                    "candidates": candidates, "rules": RULES}
    for unresolved in (NOT_EXECUTED, INCONCLUSIVE):
        if unresolved in labels:
            return {"path": path_id, "label": unresolved, "bound_shape": None,
                    "candidates": candidates, "rules": RULES}
    accepted = [c for c in candidates if c.get("accepted_without_side_effect")]
    if not candidates or not accepted:
        label = NO_NONBLOCKING_CHANNEL
    else:
        label = accepted[0]["label"]
    return {"path": path_id, "label": label, "bound_shape": None,
            "candidates": candidates, "rules": RULES}


def mask(text: str, *paths) -> str:
    for p in paths:
        if p:
            for form in {str(p), str(p).replace("\\", "/"), json.dumps(str(p))[1:-1]}:
                text = text.replace(form, "<ROOT>")
    return text

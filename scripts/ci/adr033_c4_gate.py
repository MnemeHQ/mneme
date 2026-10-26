#!/usr/bin/env python3
"""ADR-033 C4 trusted merge-gate adapter: availability policy for a required check.

Derived from the CI1 lab gate (``MnemeHQ/mneme-ci1-lab`` ``gate/ci1_gate.py``
at ``3cd402fe``). Governing documents, all in ``MnemeHQ/mneme``:

- ADR-033 §§1-2 and 5-7 (``docs/adr/ADR-033-opt-in-fail-closed-enforcement.md``);
- C4 Gate 0 charter with amendments A1-A5
  (``docs/plans/2026-10-26-adr033-c4-ci-availability-charter.md``, #676);
- C4 Gate 1 charter with review fixes R1-R3
  (``docs/plans/2026-10-26-adr033-c4-gate1-implementation-charter-proposal.md``, #677);
- Layer 1 freeze amendment #678.

Runs from the BASE revision of a ``pull_request_target`` workflow, never from
the PR. The PR head is fetched into the object store and read only as git
blobs; it is never checked out, imported or executed.

``evaluate`` judges one PR:

1. List the PR's changes with trusted git (merge-base..head, ``--raw``). If the
   change list cannot be established, the gate cannot show the PR stays off
   the trusted surface, so the result is a policy refusal (A1).
2. Classify every entry by PATH first (A1): an unnormalizable path, anything
   under ``.mneme/`` and anything on the trusted surface is REFUSED, for any
   change type and any file mode. Only then: a deletion is SKIP, and a
   non-regular entry (symlink, submodule) is UNEVALUATED.
3. Read decision memory from the base commit's blob, materialize each
   remaining file into a fresh workspace and run the pinned evaluator on it
   (``mneme check --json``, a fixed query, the trusted violation mode).
4. Trust a result only if the ``mneme.check/v1`` payload is coherent with the
   exit code and requested mode (ADR-033 §2, A4). Anything else, including a
   payload without ``evaluation_complete: true`` (A2), is UNEVALUATED.
5. Aggregate (A2 with R1): REFUSED > strict VIOLATION > UNEVALUATED > WARN >
   PASS. Under ``strict`` a trusted WARN or FAIL is a strict VIOLATION.
6. Apply the availability posture from the administrator-controlled
   repository variable (A3): ``closed`` makes UNEVALUATED non-success; ``open``
   lets it satisfy the check only with a visible UNEVALUATED annotation,
   summary and report label. Missing or invalid posture means ``closed``.
7. Write the JSON report, the job summary and the annotations. Exit 0 only
   for a success disposition.

``verify-report`` is the trusted decision step (Gate 1 charter §4): it never
takes the adapter's exit code alone. It re-reads the posture, recomputes the
aggregate and disposition from the per-file results and checks every pin.

Standard library only. Not part of the ``mneme-hq`` wheel.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPORT_SCHEMA = "mneme.c4.gate-report/v1"
CONTRACT = "mneme.check/v1"
VALID_MODES = ("strict", "warn")
EXIT_CODES_BY_MODE = {
    "strict": {"PASS": 0, "WARN": 1, "FAIL": 2},
    "warn": {"PASS": 0, "WARN": 0, "FAIL": 0},
}
VIOLATION_SEVERITIES = ("WARN", "FAIL")
POSTURE_VAR = "MNEME_CI_AVAILABILITY"
VALID_POSTURES = ("open", "closed")
# Literal-tier rules are query-independent (ADR-017). A fixed query keeps the
# PR title and other PR-controlled text out of evaluation (CI1.1 S7).
QUERY = "adr033 c4 trusted gate"
MEMORY_REL = ".mneme/project_memory.json"
REGULAR_MODES = frozenset({"100644", "100755"})
DEFAULT_EVAL_TIMEOUT_S = 120
# Always on the trusted surface, whatever the workflow adds: workflows and the
# files that change how git presents paths or submodules. ``.mneme/`` is the
# policy path and is refused with its own kind.
BASE_SURFACE_FILES = (".gitattributes", ".gitmodules")
BASE_SURFACE_DIRS = (".github/",)

# Per-file classifications.
VERIFIED_PASS = "VERIFIED_PASS"
WARN = "WARN"
VIOLATION = "VIOLATION"
UNEVALUATED = "UNEVALUATED"
REFUSED = "REFUSED"
SKIP = "SKIP"
FILE_CLASSES = (VERIFIED_PASS, WARN, VIOLATION, UNEVALUATED, REFUSED, SKIP)
# Aggregate classifications.
AGG_PASS = "PASS"
AGGREGATES = (REFUSED, VIOLATION, UNEVALUATED, WARN, AGG_PASS, SKIP)
SUCCESS = "success"
FAILURE = "failure"


class GateError(RuntimeError):
    """An operational failure inside the gate; never a rule verdict."""


# ── posture and mode ─────────────────────────────────────────────────────────

def resolve_posture(raw: str | None) -> dict[str, Any]:
    """Resolve the availability posture (A3). Only exact ``open``/``closed``."""
    if raw in VALID_POSTURES:
        return {"effective": raw, "source": f"vars.{POSTURE_VAR}", "fallback": None}
    if raw is None or raw == "":
        why = f"{POSTURE_VAR} is not set"
    else:
        why = f"{POSTURE_VAR} is not exactly 'open' or 'closed' ({raw[:64]!r})"
    return {"effective": "closed", "source": f"vars.{POSTURE_VAR}",
            "fallback": f"{why}; using closed"}


# ── trusted git ──────────────────────────────────────────────────────────────

def git(repo: Path, *args: str) -> bytes:
    try:
        proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    except OSError as exc:
        raise GateError(f"git could not start: {exc}") from None
    if proc.returncode != 0:
        raise GateError(f"git {' '.join(args)} failed: {proc.stderr.decode(errors='replace').strip()}")
    return proc.stdout


def parse_raw_diff(raw: bytes) -> list[dict[str, str]]:
    """Parse ``git diff --raw -z --no-renames`` output.

    Each record is ``:<old mode> <new mode> <old sha> <new sha> <status>\\0<path>\\0``.
    For a deletion the new mode is ``000000``, so the old mode is kept too.
    """
    entries = []
    parts = raw.split(b"\0")
    i = 0
    while i < len(parts) and parts[i]:
        meta = parts[i].decode("ascii", errors="replace")
        fields = meta[1:].split(" ")
        if not meta.startswith(":") or len(fields) != 5 or i + 1 >= len(parts):
            raise GateError(f"unexpected raw diff record: {meta!r}")
        old_mode, new_mode, _old_sha, new_sha, status = fields
        path = parts[i + 1].decode("utf-8", errors="surrogateescape")
        entries.append({"status": status[:1], "old_mode": old_mode, "mode": new_mode,
                        "blob": new_sha, "path": path})
        i += 2
    return entries


def changed_entries(repo: Path, base_sha: str, head_sha: str) -> tuple[str, list[dict[str, str]]]:
    merge_base = git(repo, "merge-base", base_sha, head_sha).decode().strip()
    raw = git(repo, "diff", "--raw", "-z", "--no-renames", "--no-ext-diff", merge_base, head_sha)
    return merge_base, parse_raw_diff(raw)


# ── A1: path classification before file type ─────────────────────────────────

def normalize_surface(entries: list[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split trusted-surface entries into files and ``dir/`` prefixes."""
    files, dirs = list(BASE_SURFACE_FILES), list(BASE_SURFACE_DIRS)
    for e in entries:
        # Exactly one trailing slash marks a directory; the rest must itself be
        # a normalized path, so ``gate//`` or ``/`` is invalid, not ``gate/``.
        is_dir = isinstance(e, str) and e.endswith("/")
        core = e[:-1] if is_dir else e
        if not isinstance(e, str) or path_problem(core):
            raise GateError(f"invalid trusted-surface entry {e!r}")
        (dirs if is_dir else files).append(e)
    return tuple(files), tuple(dirs)


def path_problem(path: str) -> str | None:
    """Why ``path`` cannot be shown to be a normalized relative path, if so."""
    if not path or path.startswith("/") or "\\" in path or "\0" in path:
        return "not a normalized relative path"
    if any(0xD800 <= ord(c) <= 0xDFFF for c in path):
        return "path is not valid UTF-8"
    if any(p in ("", ".", "..") for p in path.split("/")):
        return "path contains an empty, '.' or '..' component"
    return None


def path_refusal(path: str, surface: tuple[tuple[str, ...], tuple[str, ...]]) -> tuple[str, str] | None:
    """Return ``(kind, reason)`` when a changed path is refused, whatever its mode.

    Comparison is case-insensitive: on a case-insensitive checkout ``.Mneme/``
    or ``.GitHub/`` reaches the protected location, so the gate cannot show
    such a path is outside it.
    """
    problem = path_problem(path)
    if problem:
        return "path", f"{problem}: the gate cannot show it is outside the trusted surface"
    folded = path.casefold()
    if folded == ".mneme" or folded.startswith(".mneme/"):
        return "policy", "policy path: PR changes never reach the trusted decision memory"
    files, dirs = surface
    if folded in {f.casefold() for f in files} or any(
            folded == d.casefold().rstrip("/") or folded.startswith(d.casefold()) for d in dirs):
        return "trusted_surface", "trusted surface: PR changes never reach the gate's own inputs"
    return None


def classify_entries(entries: list[dict[str, str]],
                     surface: tuple[tuple[str, ...], tuple[str, ...]]) -> list[dict[str, Any]]:
    """A1 order: path refusal, then deletion SKIP, then non-regular UNEVALUATED."""
    out = []
    for e in entries:
        mode = e["old_mode"] if e["status"] == "D" else e["mode"]
        rec: dict[str, Any] = {"path": e["path"], "status": e["status"], "mode": mode}
        refused = path_refusal(e["path"], surface)
        if refused:
            rec.update(classification=REFUSED, kind=refused[0], reason=refused[1])
        elif e["status"] == "D":
            rec.update(classification=SKIP, kind="deleted", reason="deleted outside the trusted surface")
        elif e["mode"] not in REGULAR_MODES:
            name = {"120000": "symlink", "160000": "submodule"}.get(e["mode"], f"mode {e['mode']}")
            rec.update(classification=UNEVALUATED, kind="mode", reason=f"not a regular file ({name})")
        else:
            rec.update(classification=None, blob=e["blob"])  # to be evaluated
        out.append(rec)
    return out


# ── trusted workspace ────────────────────────────────────────────────────────

def _ensure_dirs(ws: Path, rel_parts: list[str]) -> Path:
    """Create each parent directory inside ``ws`` without following anything."""
    cur = ws
    for part in rel_parts:
        cur = cur / part
        try:
            os.mkdir(cur)
        except FileExistsError:
            st = os.lstat(cur)
            if os.path.islink(cur) or (st.st_mode & 0o170000) != 0o040000:
                raise GateError(f"collides with an existing non-directory entry: {cur.relative_to(ws)}")
    return cur


def write_exclusive(ws: Path, rel: str, data: bytes) -> Path:
    """Write ``data`` to ``ws/rel`` as a new regular file; never replace or follow."""
    parts = rel.split("/")
    parent = _ensure_dirs(ws, parts[:-1])
    target = parent / parts[-1]
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(target, flags, 0o644)
    except FileExistsError:
        raise GateError(f"collides with an entry the gate already wrote: {rel}") from None
    except OSError as exc:
        raise GateError(f"cannot materialize {rel}: {exc}") from None
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return target


def read_memory(repo: Path, base_sha: str) -> tuple[str, bytes]:
    listing = git(repo, "ls-tree", "-z", base_sha, "--", MEMORY_REL).split(b"\0")[0].decode(errors="replace")
    if not listing:
        raise GateError(f"{MEMORY_REL} is missing at the trusted base {base_sha}")
    meta, _, _path = listing.partition("\t")
    mode, kind, blob = (meta.split(" ") + ["", "", ""])[:3]
    if kind != "blob" or mode not in REGULAR_MODES:
        raise GateError(f"trusted-base {MEMORY_REL} is not a regular file (mode {mode})")
    return blob, git(repo, "cat-file", "blob", blob)


# ── ADR-033 §2 coherence (A4) ────────────────────────────────────────────────

def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def classify_payload(stdout: Any, exit_code: Any, requested_mode: str) -> tuple[str, str]:
    """Return ``(classification, reason)``. Only a coherent, complete payload is trusted.

    Mirrors the shipped ``assess_verdict`` coherence rules (#484) and is
    stricter where ADR-033 §2 requires it: a missing ``evaluation_complete``
    is never proof of completeness (A2), and ADR-034 numeric or subject
    records, which this adapter does not validate, are not trusted.
    """
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return UNEVALUATED, f"no single parseable JSON payload on stdout (exit {exit_code!r})"
    if not isinstance(payload, dict):
        return UNEVALUATED, "payload is not an object"
    if payload.get("schema") != CONTRACT:
        return UNEVALUATED, f"schema {payload.get('schema')!r} is not {CONTRACT}"
    verdict = payload.get("verdict")
    if not isinstance(verdict, str) or verdict not in ("PASS", "WARN", "FAIL"):
        return UNEVALUATED, f"unknown verdict {verdict!r}"
    mode = payload.get("mode")
    if mode not in VALID_MODES:
        return UNEVALUATED, f"missing or invalid mode {mode!r}"
    if mode != requested_mode:
        return UNEVALUATED, f"reported mode {mode!r} != requested {requested_mode!r}"
    if "evaluation_complete" not in payload:
        return UNEVALUATED, "evaluation_complete is absent (legacy payload is never proof of completeness)"
    complete = payload["evaluation_complete"]
    if not isinstance(complete, bool):
        return UNEVALUATED, "evaluation_complete is not a boolean"
    if not complete:
        return UNEVALUATED, "evaluation incomplete (evaluation_complete is false)"
    violations = payload.get("violations")
    if not isinstance(violations, list):
        return UNEVALUATED, "violations is not a list"
    if "freshness" in payload and not isinstance(payload["freshness"], list):
        return UNEVALUATED, "freshness is not a list"
    if "subject" in payload:
        return UNEVALUATED, "payload carries a subject record outside the C4 adapter contract"
    applicability = payload.get("applicability")
    if applicability is not None:
        if not isinstance(applicability, list) or not all(isinstance(a, dict) for a in applicability):
            return UNEVALUATED, "applicability is not a list of objects"
        if any("matcher_status" in a or "numeric" in a for a in applicability):
            return UNEVALUATED, "payload carries ADR-034 numeric records outside the C4 adapter contract"
        if any(a.get("outcome") == "UNKNOWN" for a in applicability):
            return UNEVALUATED, "evaluation_complete disagrees with an UNKNOWN applicability outcome"
    for index, v in enumerate(violations):
        if not isinstance(v, dict):
            return UNEVALUATED, f"violation {index} is not an object"
        if "numeric" in v:
            return UNEVALUATED, "payload carries ADR-034 numeric records outside the C4 adapter contract"
        if not _nonempty_str(v.get("decision_id")):
            return UNEVALUATED, f"violation {index} has no decision_id"
        if not isinstance(v.get("decision_text"), str):
            return UNEVALUATED, f"violation {index} has no decision_text"
        if not isinstance(v.get("severity"), str) or v["severity"] not in VIOLATION_SEVERITIES:
            return UNEVALUATED, f"violation {index} has invalid severity"
        if not _nonempty_str(v.get("rule")):
            return UNEVALUATED, f"violation {index} has no rule"
        if not _nonempty_str(v.get("trigger")):
            return UNEVALUATED, f"violation {index} has no trigger"
    severities = [v["severity"] for v in violations]
    if verdict == "PASS" and severities:
        return UNEVALUATED, "PASS verdict carries violations"
    if verdict == "WARN" and (not severities or "FAIL" in severities):
        return UNEVALUATED, "WARN verdict needs WARN-only violations"
    if verdict == "FAIL" and "FAIL" not in severities:
        return UNEVALUATED, "FAIL verdict carries no FAIL violation"
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        return UNEVALUATED, "exit status unavailable"
    if exit_code != EXIT_CODES_BY_MODE[mode][verdict]:
        return UNEVALUATED, f"exit {exit_code} contradicts verdict {verdict} in {mode} mode"
    return {"PASS": VERIFIED_PASS, "WARN": WARN, "FAIL": VIOLATION}[verdict], verdict


def applicability_outcomes(stdout: str) -> list[dict[str, Any]]:
    """Applicability traces of a trusted payload, kept for evidence only."""
    try:
        records = json.loads(stdout).get("applicability") or []
    except (json.JSONDecodeError, AttributeError, TypeError):
        return []
    return [{k: r.get(k) for k in ("decision_id", "rule_id", "outcome")} for r in records if isinstance(r, dict)]


# ── evaluation ───────────────────────────────────────────────────────────────

def clean_env() -> dict[str, str]:
    drop = {"PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE", POSTURE_VAR}
    return {k: v for k, v in os.environ.items() if k.upper() not in drop}


def evaluator_command(venv_python: Path, memory: Path, target: Path, mode: str, empty_dir: Path) -> list[str]:
    return [str(venv_python), "-I", "-m", "mneme.cli", "check",
            "--memory", str(memory), "--input", str(target), "--target-path", str(target),
            "--query", QUERY, "--mode", mode, "--adr-dir", str(empty_dir), "--json"]


def evaluate_file(venv_python: Path, ws: Path, rel: str, mode: str, empty_dir: Path,
                  timeout_s: float) -> dict[str, Any]:
    target = ws / rel
    cmd = evaluator_command(venv_python, ws / MEMORY_REL, target, mode, empty_dir)
    try:
        proc = subprocess.run(cmd, cwd=empty_dir, env=clean_env(), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return {"classification": UNEVALUATED, "kind": "timeout", "reason": f"evaluator timed out after {timeout_s}s"}
    except OSError as exc:
        return {"classification": UNEVALUATED, "kind": "launch", "reason": f"evaluator could not start: {exc}"}
    cls, reason = classify_payload(proc.stdout, proc.returncode, mode)
    rec: dict[str, Any] = {"classification": cls, "reason": reason, "exit": proc.returncode,
                           "stdout": proc.stdout, "stderr_tail": proc.stderr[-2000:]}
    if cls != UNEVALUATED:
        rec["applicability"] = applicability_outcomes(proc.stdout)
    else:
        rec["kind"] = "untrusted_result"
    return rec


# ── A2 aggregate (with R1) and A3 disposition ────────────────────────────────

def aggregate(classes: list[str], mode: str) -> str:
    """REFUSED > strict VIOLATION > UNEVALUATED > WARN > PASS; SKIP-only is SKIP.

    R1: under ``strict`` a trusted WARN is a strict VIOLATION (strict WARN
    exits 1 today). Under ``warn``, WARN and FAIL results are reported, not
    blocking, and rank below UNEVALUATED.
    """
    s = set(classes)
    if REFUSED in s:
        return REFUSED
    if mode == "strict" and s & {VIOLATION, WARN}:
        return VIOLATION
    if UNEVALUATED in s:
        return UNEVALUATED
    if s & {VIOLATION, WARN}:
        return WARN
    if VERIFIED_PASS in s:
        return AGG_PASS
    return SKIP


def disposition(agg: str, posture: str) -> str:
    if agg in (REFUSED, VIOLATION):
        return FAILURE
    if agg == UNEVALUATED:
        return SUCCESS if posture == "open" else FAILURE
    return SUCCESS


# ── reporting ────────────────────────────────────────────────────────────────

def _escape_command(text: str) -> str:
    """Escape data for a GitHub workflow command so a path cannot inject one."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _md(text: str) -> str:
    return text.replace("\\", "\\\\").replace("`", "'").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def annotations_for(report: dict[str, Any]) -> list[str]:
    agg, disp = report["aggregate"]["classification"], report["disposition"]
    posture = report["posture"]
    lines = []
    if posture["fallback"]:
        lines.append(f"::warning title=ADR-033 C4 posture::{_escape_command(posture['fallback'])}")
    detail = report["aggregate"]["reason"]
    if disp == FAILURE:
        lines.append(f"::error title=ADR-033 C4 {agg}::{_escape_command(detail)}")
    elif agg == UNEVALUATED:
        lines.append("::warning title=ADR-033 C4 UNEVALUATED::"
                     + _escape_command(f"UNEVALUATED, not PASS (availability open): {detail}"))
    elif agg == WARN:
        lines.append(f"::warning title=ADR-033 C4 WARN::{_escape_command(detail)}")
    return lines


def summary_markdown(report: dict[str, Any]) -> str:
    agg = report["aggregate"]
    out = ["## ADR-033 C4 trusted gate", "",
           f"- Result: **{agg['classification']}** ({report['disposition']})",
           f"- Availability: `{report['posture']['effective']}`; violation mode: `{report['requested_mode']}`",
           f"- Base `{report['base_sha']}` / head `{report['head_sha']}`",
           f"- Reason: {_md(agg['reason'])}"]
    if agg["classification"] == UNEVALUATED:
        out.append("- **UNEVALUATED is not a PASS.** The check was not completed or its result was not trusted.")
    if report["posture"]["fallback"]:
        out.append(f"- Posture warning: {_md(report['posture']['fallback'])}")
    rows = report["files"] + report["gate_conditions"]
    if rows:
        out += ["", "| Path | Result | Reason |", "|---|---|---|"]
        out += [f"| `{_md(r.get('path', '(gate)'))}` | {r['classification']} | {_md(r['reason'])} |" for r in rows]
    return "\n".join(out) + "\n"


def _reason(agg: str, rows: list[dict[str, Any]]) -> str:
    hits = [r for r in rows if r["classification"] == agg] or \
           [r for r in rows if agg == VIOLATION and r["classification"] == WARN]
    if agg == AGG_PASS:
        return "every evaluated file passed"
    if agg == SKIP:
        return "no file needed evaluation"
    if not hits:
        return agg
    first = hits[0]
    where = f"{first['path']}: " if first.get("path") else ""
    more = f" (+{len(hits) - 1} more)" if len(hits) > 1 else ""
    return f"{where}{first['reason']}{more}"


def adapter_identity() -> dict[str, str]:
    data = Path(__file__).read_bytes()
    return {"path": "scripts/ci/adr033_c4_gate.py", "sha256": hashlib.sha256(data).hexdigest()}


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    rows = report["files"] + report["gate_conditions"]
    classes = [r["classification"] for r in rows]
    agg = aggregate(classes, report["requested_mode"])
    return {"classification": agg, "reason": _reason(agg, rows),
            "partly_unevaluated": UNEVALUATED in classes,
            "counts": {c: classes.count(c) for c in FILE_CLASSES if c in classes}}


# ── gate run ─────────────────────────────────────────────────────────────────

def run_gate(*, repo: Path, base_sha: str, head_sha: str, workspace: Path, empty_dir: Path,
             venv_python: Path, mode: str, posture_raw: str | None, surface_entries: list[str],
             evaluator: dict[str, str], timeout_s: float = DEFAULT_EVAL_TIMEOUT_S) -> dict[str, Any]:
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {VALID_MODES}")
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA, "adapter": adapter_identity(), "evaluator": evaluator,
        "base_sha": base_sha, "head_sha": head_sha, "merge_base": None,
        "requested_mode": mode, "query": QUERY, "posture": resolve_posture(posture_raw),
        "trusted_surface": None, "memory": None, "files": [], "gate_conditions": [],
    }
    try:
        surface = normalize_surface(surface_entries)
        report["trusted_surface"] = {"files": list(surface[0]), "dirs": list(surface[1])}
        merge_base, entries = changed_entries(repo, base_sha, head_sha)
        report["merge_base"] = merge_base
        report["files"] = classify_entries(entries, surface)
    except Exception as exc:  # noqa: BLE001 - any failure here leaves the surface unproven
        report["files"] = []
        report["gate_conditions"].append({
            "classification": REFUSED, "kind": "change_list",
            "reason": f"the change list could not be established, so the PR cannot be shown to stay "
                      f"off the trusted surface: {exc}"})
    else:
        _evaluate_pending(report, repo, base_sha, workspace, empty_dir, venv_python, mode, timeout_s)
    report["aggregate"] = summarize(report)
    report["disposition"] = disposition(report["aggregate"]["classification"], report["posture"]["effective"])
    report["annotations"] = annotations_for(report)
    return report


def _evaluate_pending(report: dict[str, Any], repo: Path, base_sha: str, workspace: Path, empty_dir: Path,
                      venv_python: Path, mode: str, timeout_s: float) -> None:
    pending = [r for r in report["files"] if r["classification"] is None]
    if not pending:
        return
    try:
        os.mkdir(workspace)  # must not exist: a fresh, gate-owned directory
        os.mkdir(empty_dir)
    except OSError as exc:
        for r in pending:
            r.update(classification=UNEVALUATED, kind="workspace", reason=f"fresh gate workspace unavailable: {exc}")
        return
    try:
        blob, memory = read_memory(repo, base_sha)
        write_exclusive(workspace, MEMORY_REL, memory)
        report["memory"] = {"path": MEMORY_REL, "blob": blob, "source_commit": base_sha,
                            "sha256": hashlib.sha256(memory).hexdigest()}
    except (GateError, OSError) as exc:
        for r in pending:
            r.update(classification=UNEVALUATED, kind="memory",
                     reason=f"trusted-base decision memory unavailable: {exc}")
        return
    for r in pending:
        blob = r.pop("blob")
        try:
            data = git(repo, "cat-file", "blob", blob)
            write_exclusive(workspace, r["path"], data)
            r["sha256"] = hashlib.sha256(data).hexdigest()
        except GateError as exc:
            r.update(classification=UNEVALUATED, kind="materialize", reason=str(exc))
            continue
        try:
            r.update(evaluate_file(venv_python, workspace, r["path"], mode, empty_dir, timeout_s))
        except Exception as exc:  # noqa: BLE001 - an adapter fault is operational, not a verdict
            r.update(classification=UNEVALUATED, kind="adapter_error", reason=f"adapter error: {exc!r}")


# ── trusted decision step (Gate 1 charter §4) ────────────────────────────────

REQUIRED_KEYS = ("schema", "adapter", "evaluator", "base_sha", "head_sha", "requested_mode", "posture",
                 "files", "gate_conditions", "aggregate", "disposition", "annotations")


def verify_report(report: Any, *, adapter_exit: Any, expected: dict[str, Any], posture_raw: str | None,
                  summary_text: str | None) -> list[str]:
    """Return why the required check must fail; an empty list means it may succeed."""
    if not isinstance(report, dict):
        return ["report is missing or not a JSON object"]
    missing = [k for k in REQUIRED_KEYS if k not in report]
    if missing:
        return [f"report lacks {', '.join(missing)}"]
    problems = []
    if report["schema"] != REPORT_SCHEMA:
        problems.append(f"report schema {report['schema']!r} is not {REPORT_SCHEMA}")
    pins = {
        "base_sha": report["base_sha"], "head_sha": report["head_sha"],
        "requested_mode": report["requested_mode"],
        "adapter_sha256": (report["adapter"] or {}).get("sha256"),
        "evaluator_commit": (report["evaluator"] or {}).get("commit"),
        "evaluator_wheel_sha256": (report["evaluator"] or {}).get("wheel_sha256"),
    }
    for key, value in pins.items():
        if not expected.get(key):
            problems.append(f"no trusted {key} to check the report against")
        elif value != expected[key]:
            problems.append(f"report {key} {value!r} != trusted {expected[key]!r}")
    trusted_posture = resolve_posture(posture_raw)["effective"]
    reported_posture = (report["posture"] or {}).get("effective")
    if reported_posture != trusted_posture:
        problems.append(f"report posture {reported_posture!r} != trusted posture {trusted_posture!r}")
    rows = report["files"] + report["gate_conditions"]
    if not all(isinstance(r, dict) and r.get("classification") in FILE_CLASSES and isinstance(r.get("reason"), str)
               for r in rows):
        return problems + ["report has a file result without a known classification and reason"]
    agg = aggregate([r["classification"] for r in rows], report["requested_mode"]
                    if report["requested_mode"] in VALID_MODES else "strict")
    if (report["aggregate"] or {}).get("classification") != agg:
        problems.append(f"report aggregate {report['aggregate'].get('classification')!r} != recomputed {agg!r}")
    disp = disposition(agg, trusted_posture)
    if report["disposition"] != disp:
        problems.append(f"report disposition {report['disposition']!r} != recomputed {disp!r}")
    if adapter_exit != (0 if report["disposition"] == SUCCESS else 1):
        problems.append(f"adapter exit {adapter_exit!r} disagrees with disposition {report['disposition']!r}")
    if disp == SUCCESS and agg == UNEVALUATED:
        if not any(a.startswith("::warning") and "UNEVALUATED" in a for a in report["annotations"]):
            problems.append("open UNEVALUATED success lacks its ::warning:: annotation")
        if not summary_text or "UNEVALUATED" not in summary_text:
            problems.append("open UNEVALUATED success lacks its job-summary entry")
    if disp != SUCCESS:
        problems.append(f"required check fails: {agg} under availability {trusted_posture}")
    return problems


# ── entry points ─────────────────────────────────────────────────────────────

def _cmd_evaluate(args: argparse.Namespace) -> int:
    evaluator = {"commit": args.evaluator_commit, "wheel_sha256": args.evaluator_wheel_sha256,
                 "python": str(args.venv_python)}
    report = run_gate(repo=args.repo, base_sha=args.base_sha, head_sha=args.head_sha,
                      workspace=args.workspace, empty_dir=args.empty_dir, venv_python=args.venv_python,
                      mode=args.mode, posture_raw=os.environ.get(POSTURE_VAR),
                      surface_entries=args.trusted_surface or [], evaluator=evaluator,
                      timeout_s=args.eval_timeout)
    report["summary_written"] = False
    if args.summary:
        try:
            with open(args.summary, "a", encoding="utf-8") as fh:
                fh.write(summary_markdown(report))
            report["summary_written"] = True
        except OSError as exc:
            print(f"::error::{_escape_command(f'could not write the job summary: {exc}')}")
            report["disposition"] = FAILURE
    for line in report["annotations"]:
        print(line)
    print(f"[adr033-c4-gate] {report['aggregate']['classification']} -> {report['disposition']} "
          f"(availability {report['posture']['effective']}, mode {report['requested_mode']})")
    try:
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"::error::{_escape_command(f'could not write the gate report: {exc}')}")
        return 1
    return 0 if report["disposition"] == SUCCESS else 1


def _cmd_verify(args: argparse.Namespace) -> int:
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report = None
        print(f"::error::{_escape_command(f'gate report unreadable: {exc}')}")
    try:
        summary = args.summary.read_text(encoding="utf-8") if args.summary else None
    except OSError:
        summary = None
    expected = {"base_sha": args.base_sha, "head_sha": args.head_sha, "requested_mode": args.mode,
                "adapter_sha256": args.adapter_sha256, "evaluator_commit": args.evaluator_commit,
                "evaluator_wheel_sha256": args.evaluator_wheel_sha256}
    try:
        adapter_exit: Any = int(args.adapter_exit)
    except ValueError:
        adapter_exit = args.adapter_exit
    try:
        problems = verify_report(report, adapter_exit=adapter_exit, expected=expected,
                                 posture_raw=os.environ.get(POSTURE_VAR), summary_text=summary)
    except Exception as exc:  # noqa: BLE001 - a malformed report never passes
        problems = [f"report could not be verified: {exc!r}"]
    for p in problems:
        print(f"::error title=ADR-033 C4 decision::{_escape_command(p)}")
    if problems:
        return 1
    print(f"[adr033-c4-gate] decision: {report['aggregate']['classification']} accepted "
          f"(availability {report['posture']['effective']})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)

    ev = sub.add_parser("evaluate", help="judge one PR and write the report")
    ev.add_argument("--repo", type=Path, required=True, help="base checkout holding both commits")
    ev.add_argument("--base-sha", required=True)
    ev.add_argument("--head-sha", required=True)
    ev.add_argument("--mode", required=True, choices=VALID_MODES,
                    help="violation mode; a literal constant in the trusted workflow (R2)")
    ev.add_argument("--workspace", type=Path, required=True, help="absolute; must not exist yet")
    ev.add_argument("--empty-dir", type=Path, required=True, help="absolute; must not exist yet")
    ev.add_argument("--venv-python", type=Path, required=True, help="pinned evaluator interpreter")
    ev.add_argument("--evaluator-commit", required=True)
    ev.add_argument("--evaluator-wheel-sha256", required=True)
    ev.add_argument("--trusted-surface", action="append",
                    help="extra trusted-surface file, or directory ending in '/'; repeatable")
    ev.add_argument("--eval-timeout", type=float, default=DEFAULT_EVAL_TIMEOUT_S)
    ev.add_argument("--report", type=Path, required=True)
    ev.add_argument("--summary", type=Path, help="job summary file to append to ($GITHUB_STEP_SUMMARY)")
    ev.set_defaults(func=_cmd_evaluate)

    vr = sub.add_parser("verify-report", help="trusted decision step: accept or refuse the report")
    vr.add_argument("--report", type=Path, required=True)
    vr.add_argument("--adapter-exit", required=True)
    vr.add_argument("--base-sha", required=True)
    vr.add_argument("--head-sha", required=True)
    vr.add_argument("--mode", required=True, choices=VALID_MODES)
    vr.add_argument("--adapter-sha256", required=True)
    vr.add_argument("--evaluator-commit", required=True)
    vr.add_argument("--evaluator-wheel-sha256", required=True)
    vr.add_argument("--summary", type=Path, help="the job summary the evaluate step wrote")
    vr.set_defaults(func=_cmd_verify)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

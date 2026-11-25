#!/usr/bin/env python3
"""AP1.2 stage A: offline, pure planner for the sticky PR feedback comment.

``plan(config, observed)`` decides what a future publisher would do with
redacted, already-observed host metadata. It performs no I/O: no network, no
GitHub API, no subprocess, no environment, no credentials, no file writes.
Stage A is a contract and abstention model only. It makes no claim about real
host behaviour, and a plan is never an authorization to write.

Inputs
------
``config`` holds trusted constants (never taken from ``observed``): repo id,
default branch, the producer workflow identity, the approved pins, the
publisher identity, the marker, size limits and the disclosure tier
(``totals`` only). ``observed`` mirrors redacted REST responses: the source
run (with three run-attempt observations), jobs, artifacts, the artifact
archive as base64, three observations each of the default-branch tip and of
the pull request, other producer runs, existing comments and the receipt.

The AP1.1 renderer is loaded by file path and called as ``render()``; this
module never imports the adapter or the evaluator. The expected context given
to the renderer comes from ``config`` plus independently observed values,
never from the report.

Output
------
A dict with ``action`` and ``reason`` (one fixed code), plus ``pr_number``,
``comment_id``, ``body`` and ``receipt_proposal`` when a write is planned.
Raw observed text never appears in a plan except the AP1.1 renderer's own
escaped output (totals tier, no paths). Unknown reasons do not exist.

Actions and reason codes (the complete vocabulary)
--------------------------------------------------
NO_WRITE      FORBIDDEN_NAME, MALFORMED_INPUT, SOURCE_MISMATCH, ATTEMPT_NOT_1,
              JOB_UNPROVEN, ARTIFACT_INVALID, PR_MISMATCH, FORK_DEFERRED,
              BASE_MOVED, BASE_UNPROVEN, STALE_RUN, BODY_TOO_LARGE,
              COMMENTS_INCOMPLETE, DEFINITION_MISMATCH, POLICY_UNPROVEN,
              POLICY_CHANGED, ORDER_UNPROVEN
UNAVAILABLE   GATE_JOB_INCOMPLETE, REPORT_UNAVAILABLE, GATE_REPORT_DISAGREE,
              BODY_TOO_LARGE. A neutral body is planned (``write`` is CREATE or
              UPDATE after reconciliation). No report-derived claim is made.
CONFLICT      OWNERSHIP_AMBIGUOUS, EDIT_DETECTED, RECEIPT_MISSING,
              RECEIPT_MISMATCH, COMMENT_DELETED
CREATE        OK_CREATE
UPDATE        OK_UPDATE
NOOP          OK_UNCHANGED

Checks run in this order and the first failure wins: config sanity, shape and
size limits, source run, gate job, artifact and archive, pull request, base,
report (AP1.1 render), gate versus report, ordering, body size, comment
reconciliation. The comment list must be declared complete
(``observed.comments_complete is True``) or the plan is NO_WRITE
COMMENTS_INCOMPLETE. A cancelled, skipped or timed-out gate job is not a failure: it is
carried forward and, once the pull request and base are established, yields
UNAVAILABLE GATE_JOB_INCOMPLETE with a neutral body.

Trust assumptions modelled (not proven) in stage A: ``observed.producer_definition``
(path and blob SHA of the workflow definition the run used), ``observed.policy``
(posture and version at three observations), the job and step timestamps, the
artifact ``created_at`` and ``other_runs_complete``. In stage B each must come
from an independent host source; stage A only models them and abstains when
they are missing, unparseable or different from the trusted ``config``.

Never synthesized: a gate verdict, UNEVALUATED, "merge blocked", "merge
allowed" or any compliance claim. The gate job conclusion is shown separately
from the report-derived text. Fork pull requests are NO_WRITE FORK_DEFERRED.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import datetime
import hashlib
import importlib.util
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

# ── fixed vocabulary ─────────────────────────────────────────────────────────

NO_WRITE, CREATE, UPDATE, NOOP, UNAVAILABLE, CONFLICT = (
    "NO_WRITE", "CREATE", "UPDATE", "NOOP", "UNAVAILABLE", "CONFLICT")
REASONS = frozenset({
    "FORBIDDEN_NAME", "MALFORMED_INPUT", "SOURCE_MISMATCH", "ATTEMPT_NOT_1", "JOB_UNPROVEN",
    "ARTIFACT_INVALID", "PR_MISMATCH", "FORK_DEFERRED", "BASE_MOVED", "BASE_UNPROVEN", "STALE_RUN",
    "BODY_TOO_LARGE", "COMMENTS_INCOMPLETE", "DEFINITION_MISMATCH", "POLICY_UNPROVEN",
    "POLICY_CHANGED", "ORDER_UNPROVEN", "RECEIPT_MISMATCH", "GATE_JOB_INCOMPLETE", "REPORT_UNAVAILABLE", "GATE_REPORT_DISAGREE",
    "OWNERSHIP_AMBIGUOUS", "EDIT_DETECTED", "RECEIPT_MISSING", "COMMENT_DELETED",
    "OK_CREATE", "OK_UPDATE", "OK_UNCHANGED"})

PRESERVE_STEP = "Preserve the gate evidence"
DECISION_STEP = "Gate decision"
BUILTIN_REQUIRED = "mneme trusted gate"
REPORT_NAME = "gate-report.json"
SUMMARY_NAME = "summary.md"
ARTIFACT_RE = re.compile(r"mneme-gate-pr([1-9][0-9]{0,9})-([0-9]+)")
SHA40_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
MARKER_RE = re.compile(r"(?!.*--)[A-Za-z0-9._/:-]{0,63}[A-Za-z0-9._/:]")
TS_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
REQUIRED_EVENT = "pull_request_target"
DISPOSITION_RE = re.compile(r"Recorded adapter disposition: `(success|failure)`")
INCOMPLETE_CONCLUSIONS = ("cancelled", "skipped", "timed_out")
FOOTER = ("Revision-scoped advisory snapshot. Comments may be edited or become stale; edit checks occur "
          "on reconciliation, not continuously. Consult the separately reported gate check.")
TIER_LINE = "Per-file rows and finding details are not shown at this disclosure tier."
STATUS_PREFIX = "Status (advisory, not authenticated): "
ADVISORY = "Advisory report-derived snapshot — not authenticated; required gate result is separate"

NEUTRAL_TEXT = {
    "GATE_JOB_INCOMPLETE": "The gate job did not complete, so no report is shown.",
    "REPORT_UNAVAILABLE": "The gate report could not be displayed.",
    "GATE_REPORT_DISAGREE": "The gate job conclusion and the recorded report disposition do not agree, "
                            "so no report is shown.",
    "BODY_TOO_LARGE": "The report summary exceeds the comment size limit, so it is not shown.",
}

# Shape limits (presentation/planning only).
MAX_NODES = 400_000
MAX_DEPTH = 12
MAX_STR = 8192
MAX_BODY_STR = 262_144
MAX_JOBS = 100
MAX_STEPS = 200
MAX_ARTIFACTS = 100
MAX_OTHER_RUNS = 1000
MAX_COMMENTS = 1000
MAX_EDITS = 100
MAX_TRACE_ENTRIES = 2000


class _Stop(Exception):
    def __init__(self, plan: dict[str, Any]) -> None:
        super().__init__(plan["reason"])
        self.plan = plan


def _no_write(reason: str) -> _Stop:
    return _Stop({"action": NO_WRITE, "reason": reason})


# ── helpers ──────────────────────────────────────────────────────────────────

def _get(d: Any, *keys: str) -> Any:
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def _int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _ts(value: Any) -> Any:
    """Strict ISO-8601 UTC (``YYYY-MM-DDTHH:MM:SSZ``) or None."""
    if not isinstance(value, str) or TS_RE.fullmatch(value) is None:
        return None
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _norm(name: str) -> str:
    return " ".join(name.casefold().split())


_RENDERER: Any = None


def _renderer() -> Any:
    """The AP1.1 renderer, loaded by file path (never the adapter/evaluator)."""
    global _RENDERER
    if _RENDERER is None:
        path = Path(__file__).resolve().parent / "render_pr_feedback.py"
        spec = importlib.util.spec_from_file_location("ap12_render_pr_feedback", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _RENDERER = module
    return _RENDERER


# ── 1. config sanity, 2. shape ───────────────────────────────────────────────

def _check_config(config: Any) -> dict[str, Any]:
    ok = isinstance(config, dict)
    try:
        if ok:
            prod, pins, pub, lim = (config["producer"], config["pins"], config["publisher"], config["limits"])
            ok = (_int(config["repo_id"]) and isinstance(config["default_branch"], str)
                  and _int(prod["workflow_id"]) and isinstance(prod["path"], str)
                  and isinstance(prod["event"], str) and isinstance(prod["gate_job_name"], str)
                  and isinstance(prod["evaluate_step"], str) and prod["evaluate_step"] != ""
                  and isinstance(config["producer_definition"]["path"], str)
                  and SHA40_RE.fullmatch(str(config["producer_definition"]["blob_sha"])) is not None
                  and isinstance(config["policy_version"], str) and config["policy_version"] != ""
                  and all(isinstance(pins[k], str) for k in (
                      "adapter_sha256", "evaluator_commit", "evaluator_wheel_sha256", "mode", "posture"))
                  and _int(pub["actor_id"]) and isinstance(pub["marker"], str)
                  and MARKER_RE.fullmatch(pub["marker"]) is not None
                  and isinstance(pub["names"], list) and pub["names"]
                  and all(isinstance(n, str) for n in pub["names"])
                  and isinstance(config.get("required_checks", []), list)
                  and all(isinstance(n, str) for n in config.get("required_checks", []))
                  and all(_int(lim[k]) and lim[k] > 0 for k in (
                      "body_cap", "archive_compressed_max", "archive_uncompressed_max"))
                  and config["producer_definition"]["path"] == prod["path"]
                  and pins["mode"] in ("strict", "warn") and pins["posture"] in ("open", "closed")
                  and config["disclosure"] == "totals")
    except (KeyError, TypeError):
        ok = False
    if not ok:
        raise _no_write("MALFORMED_INPUT")
    forbidden = {BUILTIN_REQUIRED} | {_norm(n) for n in config.get("required_checks", [])}
    for name in config["publisher"]["names"]:
        n = _norm(name)
        if n in forbidden or "trusted gate" in n:
            raise _no_write("FORBIDDEN_NAME")
    return config


def _walk_limits(observed: Any) -> bool:
    nodes = 0
    stack = [(observed, 0)]
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            return False
        if isinstance(node, dict):
            for k, v in node.items():
                if not isinstance(k, str) or len(k) > 256:
                    return False
                stack.append((v, depth + 1))
        elif isinstance(node, list):
            stack.extend((v, depth + 1) for v in node)
        elif isinstance(node, str):
            if len(node) > MAX_BODY_STR:
                return False
        elif not (node is None or isinstance(node, (bool, int))):
            return False
    return True


def _check_shape(observed: Any, config: dict[str, Any]) -> dict[str, Any]:
    ok = isinstance(observed, dict) and _walk_limits(observed)
    if ok:
        spec = (("source_run", dict), ("jobs", list), ("artifacts", list), ("artifact_zip_b64", str),
                ("base_ref_obs", dict), ("pull_obs", dict), ("other_runs", list), ("comments", list))
        ok = all(isinstance(observed.get(k), t) for k, t in spec)
        ok = ok and (observed.get("receipt") is None or isinstance(observed["receipt"], dict))
    if ok:
        ok = (len(observed["jobs"]) <= MAX_JOBS and len(observed["artifacts"]) <= MAX_ARTIFACTS
              and len(observed["other_runs"]) <= MAX_OTHER_RUNS and len(observed["comments"]) <= MAX_COMMENTS
              and len(observed["artifact_zip_b64"]) <= 2 * config["limits"]["archive_compressed_max"] + 16)
    if ok:
        for job in observed["jobs"]:
            steps = job.get("steps") if isinstance(job, dict) else None
            if not isinstance(steps, list) or len(steps) > MAX_STEPS or not all(isinstance(s, dict) for s in steps):
                ok = False
        ok = ok and all(isinstance(a, dict) for a in observed["artifacts"])
        for run in observed["other_runs"]:
            if not (isinstance(run, dict) and _int(run.get("id")) and _int(run.get("run_number"))):
                ok = False
        for c in observed["comments"]:
            if not (isinstance(c, dict) and _int(c.get("id")) and isinstance(c.get("body"), str)
                    and isinstance(c.get("updated_at"), str) and isinstance(c.get("user"), dict)
                    and _int(c["user"].get("id")) and isinstance(c["user"].get("type"), str)):
                ok = False
                continue
            edits = c.get("edits")
            if edits is not None and not (
                    isinstance(edits, list) and len(edits) <= MAX_EDITS
                    and all(isinstance(e, dict) and _int(e.get("editor_id")) for e in edits)):
                ok = False
        rc = observed["receipt"]
        if rc is not None and not (
                all(_int(rc.get(k)) for k in ("comment_id", "writer_id", "source_run_id", "run_number", "attempt"))
                and all(isinstance(rc.get(k), str) for k in ("base_sha", "head_sha", "body_sha256", "updated_at"))):
            ok = False
    if not ok:
        raise _no_write("MALFORMED_INPUT")
    if observed.get("comments_complete") is not True:
        raise _no_write("COMMENTS_INCOMPLETE")
    return observed


# ── 3. source run ────────────────────────────────────────────────────────────

def _check_source(config: dict[str, Any], obs: dict[str, Any]) -> tuple[int, int, str]:
    run, prod = obs["source_run"], config["producer"]
    run_id, run_number, head = run.get("id"), run.get("run_number"), run.get("head_sha")
    good = (_int(run_id) and run_id > 0 and _int(run_number) and run_number > 0
            and isinstance(head, str) and SHA40_RE.fullmatch(head) is not None
            and _get(run, "repository", "id") == config["repo_id"]
            and run.get("workflow_id") == prod["workflow_id"] and run.get("path") == prod["path"]
            and run.get("event") == prod["event"] and run.get("event") == REQUIRED_EVENT
            and run.get("status") == "completed")
    if not good:
        raise _no_write("SOURCE_MISMATCH")
    definition, approved = obs.get("producer_definition"), config["producer_definition"]
    if not (isinstance(definition, dict) and definition.get("path") == approved["path"]
            and definition.get("blob_sha") == approved["blob_sha"]):
        raise _no_write("DEFINITION_MISMATCH")
    attempts = run.get("run_attempt_obs")
    for key in ("resolve", "before_write", "after_write"):
        v = _get(attempts, key)
        if not _int(v) or v != 1:
            raise _no_write("ATTEMPT_NOT_1")
    return run_id, run_number, head


# ── 4. gate job ──────────────────────────────────────────────────────────────

def _check_job(config: dict[str, Any], obs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return (job conclusion, job). Incomplete conclusions are returned, not raised."""
    jobs = [j for j in obs["jobs"] if isinstance(j, dict) and j.get("name") == config["producer"]["gate_job_name"]]
    if len(jobs) != 1:
        raise _no_write("JOB_UNPROVEN")
    job, run = jobs[0], obs["source_run"]
    conclusion = job.get("conclusion")
    if (not _int(job.get("run_attempt")) or job["run_attempt"] != 1 or not _int(job.get("id"))
            or job.get("run_id") != run.get("id") or not _int(job.get("run_id"))
            or job.get("head_sha") != run.get("head_sha") or job.get("status") != "completed"):
        raise _no_write("JOB_UNPROVEN")
    if conclusion in INCOMPLETE_CONCLUSIONS:
        return conclusion, job
    if conclusion not in ("success", "failure"):
        raise _no_write("JOB_UNPROVEN")
    steps = {}
    for name in (config["producer"]["evaluate_step"], PRESERVE_STEP, DECISION_STEP):
        found = [s for s in job["steps"] if s.get("name") == name]
        if len(found) != 1 or found[0].get("conclusion") not in ("success", "failure"):
            raise _no_write("JOB_UNPROVEN")
        steps[name] = found[0]["conclusion"]
    if steps[config["producer"]["evaluate_step"]] != "success":  # the step ends with exit 0
        raise _no_write("JOB_UNPROVEN")
    if steps[PRESERVE_STEP] != "success":  # upload failure gives no positive result
        raise _no_write("JOB_UNPROVEN")
    # Incoherent combinations are unproven, never repaired.
    if steps[DECISION_STEP] != conclusion:
        raise _no_write("JOB_UNPROVEN")
    return conclusion, job


# ── 5. artifact and archive ──────────────────────────────────────────────────

def _check_upload_window(art: dict[str, Any], job: dict[str, Any]) -> None:
    """The artifact must have been created inside the preserve step's own time window."""
    steps = [s for s in job["steps"] if s.get("name") == PRESERVE_STEP]
    if len(steps) != 1:
        raise _no_write("ARTIFACT_INVALID")
    start, end, made = _ts(steps[0].get("started_at")), _ts(steps[0].get("completed_at")), _ts(art.get("created_at"))
    if start is None or end is None or made is None or not (start <= made <= end):
        raise _no_write("ARTIFACT_INVALID")


def _check_artifact(config: dict[str, Any], obs: dict[str, Any], run_id: int, head: str,
                    job: dict[str, Any]) -> tuple[int, bytes]:
    lim = config["limits"]
    named = [a for a in obs["artifacts"] if isinstance(a.get("name"), str) and a["name"].startswith("mneme-gate-pr")]
    if len(named) != 1:
        raise _no_write("ARTIFACT_INVALID")
    art = named[0]
    m = ARTIFACT_RE.fullmatch(art["name"])
    if m is None or int(m.group(2)) != run_id:
        raise _no_write("ARTIFACT_INVALID")
    wr = art.get("workflow_run")
    run = obs["source_run"]
    if not (art.get("expired") is False and _int(art.get("id")) and _int(art.get("size_in_bytes"))
            and art["size_in_bytes"] <= lim["archive_compressed_max"]
            and _get(wr, "id") == run_id and _get(wr, "repository_id") == config["repo_id"]
            and _get(wr, "head_sha") == head
            and _get(wr, "head_repository_id") == _get(run, "head_repository", "id")
            and isinstance(art.get("digest"), str)):
        raise _no_write("ARTIFACT_INVALID")
    _check_upload_window(art, job)
    try:
        data = base64.b64decode(obs["artifact_zip_b64"], validate=True)
    except (binascii.Error, ValueError):
        raise _no_write("ARTIFACT_INVALID") from None
    if (data[:4] != b"PK\x03\x04" or len(data) != art["size_in_bytes"] or len(data) > lim["archive_compressed_max"]
            or art["digest"] != "sha256:" + hashlib.sha256(data).hexdigest()):
        raise _no_write("ARTIFACT_INVALID")
    return int(m.group(1)), _read_report(data, lim)


def _read_report(data: bytes, lim: dict[str, Any]) -> bytes:
    """gate-report.json from an in-memory archive that holds only the approved entries."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            names = [i.filename for i in infos]
            if (len(set(names)) != len(names) or REPORT_NAME not in names
                    or any(n not in (REPORT_NAME, SUMMARY_NAME) for n in names)):
                raise ValueError
            total = 0
            for i in infos:
                kind = (i.external_attr >> 16) & 0o170000
                if (i.is_dir() or i.flag_bits & 0x1 or kind not in (0, 0o100000)
                        or i.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                        or i.file_size > lim["archive_uncompressed_max"]):
                    raise ValueError
                total += i.file_size
            if total > lim["archive_uncompressed_max"]:
                raise ValueError
            with zf.open(REPORT_NAME) as fh:
                report = fh.read(lim["archive_uncompressed_max"] + 1)
            if len(report) > lim["archive_uncompressed_max"] or report[:2] == b"PK":
                raise ValueError
            return report
    except Exception:  # noqa: BLE001 - any archive fault is an abstention, never a crash
        raise _no_write("ARTIFACT_INVALID") from None


# ── 6. pull request, 7. base ─────────────────────────────────────────────────

_OBS = ("resolve", "before_write", "after_write")


def _check_pull(config: dict[str, Any], obs: dict[str, Any], pr_number: int, head: str) -> None:
    pulls = [_get(obs["pull_obs"], k) for k in _OBS]
    for p in pulls:
        if not (_get(p, "number") == pr_number and _get(p, "state") == "open"
                and _get(p, "base", "repo", "id") == config["repo_id"]
                and _get(p, "base", "ref") == config["default_branch"]
                and _get(p, "head", "sha") == head):
            raise _no_write("PR_MISMATCH")
    heads = [_get(p, "head", "repo", "id") for p in pulls] + [_get(obs["source_run"], "head_repository", "id")]
    if any(h != config["repo_id"] or not _int(h) for h in heads):
        raise _no_write("FORK_DEFERRED")


def _check_base(obs: dict[str, Any], report_bytes: bytes) -> str:
    tips = [_get(obs["base_ref_obs"], k, "object", "sha") for k in _OBS]
    if not all(isinstance(t, str) and SHA40_RE.fullmatch(t) for t in tips):
        raise _no_write("BASE_UNPROVEN")
    if len(set(tips)) != 1:
        raise _no_write("BASE_MOVED")
    tip = tips[0]
    if any(_get(obs["pull_obs"], k, "base", "sha") != tip for k in _OBS):
        raise _no_write("BASE_MOVED")
    try:  # compare only; the expected base never comes from the report
        reported = json.loads(report_bytes.decode("utf-8")).get("base_sha")
    except (ValueError, UnicodeDecodeError, AttributeError, RecursionError):
        reported = None
    if not isinstance(reported, str) or SHA40_RE.fullmatch(reported) is None:
        raise _no_write("BASE_UNPROVEN")
    if reported != tip:
        raise _no_write("BASE_MOVED")
    return tip


def _check_policy(config: dict[str, Any], obs: dict[str, Any]) -> None:
    for key in _OBS:
        posture, version = _get(obs, "policy", key, "posture"), _get(obs, "policy", key, "version")
        if not isinstance(posture, str) or not isinstance(version, str) or posture == "" or version == "":
            raise _no_write("POLICY_UNPROVEN")
        if posture != config["pins"]["posture"] or version != config["policy_version"]:
            raise _no_write("POLICY_CHANGED")


def _exclusion_line(report_bytes: bytes) -> list[str]:
    """Count reported outer EXCLUDED applicability entries (structural; no paths or IDs)."""
    try:
        rep_obj = json.loads(report_bytes.decode("utf-8"))
        rows = list(rep_obj["files"]) + list(rep_obj["gate_conditions"])
        count, present = 0, False
        for row in rows:
            trace = row.get("applicability")
            if trace is None:
                continue
            present = True
            if not isinstance(trace, list) or len(trace) > MAX_TRACE_ENTRIES:
                return ["Reported exclusions: unavailable"]
            for entry in trace:
                if not isinstance(entry, dict):
                    return ["Reported exclusions: unavailable"]
                for key in ("decision_id", "rule_id", "outcome"):
                    v = entry.get(key)
                    if not (v is None or (isinstance(v, str) and len(v) <= 512)):
                        return ["Reported exclusions: unavailable"]
                count += 1 if entry.get("outcome") == "EXCLUDED" else 0
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeDecodeError, RecursionError):
        return ["Reported exclusions: unavailable"]
    if present and count:
        return [f"Reported exclusions (report-derived, not an allow): {count}"]
    return []


# ── 12. body ─────────────────────────────────────────────────────────────────

def _context_block(config: dict[str, Any], base: str, head: str, run_id: int, job: str) -> list[str]:
    pins = config["pins"]
    return ["Snapshot context:",
            f"- Base commit: `{base}`", f"- Head commit: `{head}`",
            f"- Source run: `{run_id}` (attempt 1)",
            f"- Violation mode (configured): {pins['mode']}",
            f"- Availability posture (configured): {pins['posture']}",
            f"- Gate job conclusion (host-reported, separate from the report): {job}"]


def _status_line(middle: list[str]) -> str:
    """Plain-words status from the renderer's own heading; incompleteness is stated here."""
    heading = next((l[4:] for l in middle if l.startswith("### ")), "report could not be displayed")
    line = STATUS_PREFIX + heading
    partly = "- Partly unevaluated: yes" in middle
    if partly and "incomplete" not in heading:
        line += ". Some rows were not fully evaluated"
    return line


def _compose(config: dict[str, Any], base: str, head: str, run_id: int, job: str, middle: list[str],
             status: str) -> str:
    marker = f"<!-- {config['publisher']['marker']} -->"
    parts = [marker, "", status, "", ADVISORY, ""] + _context_block(config, base, head, run_id, job) + [""]
    parts += middle + ["", FOOTER]
    return "\n".join(parts)


def _totals_only(rendered: str) -> list[str]:
    lines = rendered.rstrip("\n").split("\n")
    for n, line in enumerate(lines):
        if line.startswith("#### "):
            lines = lines[:n]
            break
    while lines and lines[-1] == "":
        lines.pop()
    return lines


# ── 10-11. ordering and reconciliation ───────────────────────────────────────

def _check_order(obs: dict[str, Any], run_id: int, run_number: int) -> None:
    if obs.get("other_runs_complete") is not True:
        raise _no_write("ORDER_UNPROVEN")
    for run in obs["other_runs"]:
        if run["id"] == run_id:
            if run.get("run_attempt") != 1:
                raise _no_write("ATTEMPT_NOT_1")
        elif run["run_number"] >= run_number:
            raise _no_write("STALE_RUN")
    rc = obs["receipt"]
    if rc is not None and rc["run_number"] > run_number:
        raise _no_write("STALE_RUN")


def _reconcile(config: dict[str, Any], obs: dict[str, Any], run_id: int, run_number: int, head: str,
               base: str, body_sha: str) -> tuple[str, str, Any, int]:
    """(action, reason, comment_id, foreign_marker_comments). The body is only hashed.

    Owned = publisher actor id + type Bot + exact marker first line. A non-owned
    comment whose first line is the marker is a spoof: counted, never edited, and
    it blocks only when no owned comment is proven. A marker merely mentioned
    elsewhere is ignored.
    """
    actor = config["publisher"]["actor_id"]
    marker_line = f"<!-- {config['publisher']['marker']} -->"
    owned, foreign = [], 0
    for c in obs["comments"]:
        first = c["body"].split("\n", 1)[0]
        if c["user"]["id"] == actor and c["user"]["type"] == "Bot" and first == marker_line:
            owned.append(c)
        elif first.strip() == marker_line:
            foreign += 1
    rc = obs["receipt"]
    if len(owned) > 1:
        return CONFLICT, "OWNERSHIP_AMBIGUOUS", None, foreign
    if not owned:
        if foreign:
            return CONFLICT, "OWNERSHIP_AMBIGUOUS", None, foreign
        if rc is not None:
            return CONFLICT, "COMMENT_DELETED", None, foreign
        return CREATE, "OK_CREATE", None, foreign
    c = owned[0]
    if rc is None:
        return CONFLICT, "RECEIPT_MISSING", None, foreign
    if rc["writer_id"] != actor or rc["comment_id"] != c["id"]:
        return CONFLICT, "OWNERSHIP_AMBIGUOUS", None, foreign
    edits = c.get("edits")
    if (edits is None or any(e["editor_id"] != actor for e in edits)
            or hashlib.sha256(c["body"].encode("utf-8", "surrogatepass")).hexdigest() != rc["body_sha256"]
            or c["updated_at"] != rc["updated_at"]):
        return CONFLICT, "EDIT_DETECTED", None, foreign
    if rc["run_number"] == run_number and rc["source_run_id"] != run_id:
        return CONFLICT, "RECEIPT_MISMATCH", None, foreign
    if rc["source_run_id"] == run_id and (rc["run_number"] != run_number or rc["head_sha"] != head
                                          or rc["base_sha"] != base):
        return CONFLICT, "RECEIPT_MISMATCH", None, foreign
    if rc["source_run_id"] == run_id and rc["attempt"] == 1 and rc["body_sha256"] == body_sha:
        return NOOP, "OK_UNCHANGED", c["id"], foreign
    return UPDATE, "OK_UPDATE", c["id"], foreign


# ── plan ─────────────────────────────────────────────────────────────────────

def plan(config: Any, observed: Any) -> dict[str, Any]:
    """Pure planner. Never raises, never performs I/O."""
    try:
        return _plan(config, observed)
    except _Stop as stop:
        return stop.plan
    except Exception:  # noqa: BLE001 - an internal fault abstains
        return {"action": NO_WRITE, "reason": "MALFORMED_INPUT"}


def _plan(config: Any, observed: Any) -> dict[str, Any]:
    cfg = _check_config(config)
    obs = _check_shape(observed, cfg)
    run_id, run_number, head = _check_source(cfg, obs)
    job, job_obj = _check_job(cfg, obs)
    if obs["source_run"].get("conclusion") != job:
        raise _no_write("SOURCE_MISMATCH")
    pr_number, report = _check_artifact(cfg, obs, run_id, head, job_obj)
    _check_pull(cfg, obs, pr_number, head)
    tip = _check_base(obs, report)
    _check_policy(cfg, obs)

    unavailable: str | None = None
    middle: list[str] = []
    if job in INCOMPLETE_CONCLUSIONS:
        unavailable = "GATE_JOB_INCOMPLETE"
    else:
        pins = cfg["pins"]
        expected = {"base_sha": tip, "head_sha": head, "adapter_sha256": pins["adapter_sha256"],
                    "evaluator_commit": pins["evaluator_commit"],
                    "evaluator_wheel_sha256": pins["evaluator_wheel_sha256"],
                    "requested_mode": pins["mode"], "posture": pins["posture"]}
        try:
            code, rendered = _renderer().render(report, expected)
        except Exception:  # noqa: BLE001
            code, rendered = 2, ""
        found = DISPOSITION_RE.findall(rendered) if code == 0 else []
        if code != 0 or len(found) != 1:
            unavailable = "REPORT_UNAVAILABLE"
        elif found[0] != job:
            unavailable = "GATE_REPORT_DISAGREE"
        else:
            excl = _exclusion_line(report)
            middle = _totals_only(rendered) + ([""] + excl if excl else []) + ["", TIER_LINE]

    _check_order(obs, run_id, run_number)
    cap = cfg["limits"]["body_cap"]
    body = ""
    if unavailable is None:
        body = _compose(cfg, tip, head, run_id, job, middle, _status_line(middle))
        if len(body.encode("utf-8")) > cap:
            unavailable = "BODY_TOO_LARGE"
    if unavailable is not None:
        body = _compose(cfg, tip, head, run_id, job, [NEUTRAL_TEXT[unavailable]],
                        STATUS_PREFIX + NEUTRAL_TEXT[unavailable])
        if len(body.encode("utf-8")) > cap:
            raise _no_write("BODY_TOO_LARGE")

    body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    action, reason, comment_id, foreign = _reconcile(cfg, obs, run_id, run_number, head, tip, body_sha)
    if action == CONFLICT:
        return {"action": CONFLICT, "reason": reason}
    out: dict[str, Any] = {"action": action, "reason": reason, "pr_number": pr_number,
                           "comment_id": comment_id, "body": body, "foreign_marker_comments": foreign,
                           "receipt_proposal": {
                               "comment_id": comment_id, "writer_id": cfg["publisher"]["actor_id"],
                               "source_run_id": run_id, "run_number": run_number, "attempt": 1,
                               "base_sha": tip, "head_sha": head, "body_sha256": body_sha}}
    if unavailable is not None and action != NOOP:
        out["write"] = action
        out["action"], out["reason"] = UNAVAILABLE, unavailable
    return out


# ── CLI ──────────────────────────────────────────────────────────────────────

class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        sys.stderr.write(self.format_usage())
        sys.stderr.write("publish_pr_feedback: usage error\n")
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="publish_pr_feedback.py", allow_abbrev=False,
                     description="Offline planner: reads one fixture JSON {config, observed}, prints the plan.")
    parser.add_argument("fixture")
    args = parser.parse_args(argv)
    try:
        with open(args.fixture, "rb") as fh:
            fixture = json.loads(fh.read(64 * 1024 * 1024 + 1).decode("utf-8"))
        config, observed = fixture["config"], fixture["observed"]
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        sys.stderr.write("publish_pr_feedback: fixture unreadable or malformed\n")
        return 2
    text = json.dumps(plan(config, observed), indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    sys.stdout.buffer.write(text.encode("ascii"))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""AP1.2 stage A: offline publisher planner (scripts/ci/publish_pr_feedback.py).

Covers P01-P16 from the stage-A contract. Everything is synthetic or derived
in memory from the historical gate reports, which are read in place and never
modified. Expectations are written by hand. Nothing here proves host behaviour.
"""
from __future__ import annotations

import ast
import base64
import copy
import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import warnings
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLISHER = REPO_ROOT / "scripts" / "ci" / "publish_pr_feedback.py"
B_DIR = REPO_ROOT / "docs" / "validation" / "artifacts" / "verification-step3-e2e-fixture" / "ci-reports"
L_DIR = REPO_ROOT / "docs" / "validation" / "adr033-c4-gate3-live-2026-10-26" / "probes"

spec = importlib.util.spec_from_file_location("publish_pr_feedback_under_test", PUBLISHER)
P = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = P
spec.loader.exec_module(P)

HIST = {
    "B1": B_DIR / "B1_allow.gate-report.json", "B2": B_DIR / "B2_bypass_violation.gate-report.json",
    "B3": B_DIR / "B3_incomplete_symlink.gate-report.json", "B4": B_DIR / "B4_missing_identity.gate-report.json",
    "B5": B_DIR / "B5_later_revision.gate-report.json",
    "L1": L_DIR / "L1" / "artifact" / "gate-report.json", "L2": L_DIR / "L2" / "artifact" / "gate-report.json",
    "L3": L_DIR / "L3" / "artifact" / "gate-report.json", "L4": L_DIR / "L4" / "artifact" / "gate-report.json",
    "L5": L_DIR / "L5" / "artifact" / "gate-report.json",
}

PFX = "Status (advisory, not authenticated): "
REPO_ID = 1191093632
RUN_ID = 45479481003
RUN_NUMBER = 274
PR = 847
ACTOR = 555001
MARKER = "mneme-ap1-feedback:v1"
MARKER_LINE = "<!-- mneme-ap1-feedback:v1 -->"
GATE_JOB = "mneme trusted gate"
REQUIRED = ["gate (PR battery)", "Scan docs/scripts for mojibake + BOM", "Validate PR execution provenance",
            "Verify install commands name mneme-hq", "mneme check --mode warn"]
NEUTRAL = {"GATE_JOB_INCOMPLETE", "REPORT_UNAVAILABLE", "GATE_REPORT_DISAGREE", "BODY_TOO_LARGE"}


# ── builders ─────────────────────────────────────────────────────────────────

def report_of(name):
    return json.loads(HIST[name].read_text(encoding="utf-8"))


def zip_bytes(entries, *, attrs=None):
    buf = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for n, data in entries:
                zi = zipfile.ZipInfo(n)
                zi.compress_type = zipfile.ZIP_DEFLATED
                if attrs and n in attrs:
                    zi.external_attr = attrs[n]
                zf.writestr(zi, data)
    return buf.getvalue()


def config_for(rep, **over):
    cfg = {
        "repo_id": REPO_ID, "default_branch": "main",
        "producer": {"workflow_id": 404923975, "path": ".github/workflows/mneme-trusted-gate.yml",
                     "event": "pull_request_target", "gate_job_name": GATE_JOB},
        "pins": {"adapter_sha256": rep["adapter"]["sha256"], "evaluator_commit": rep["evaluator"]["commit"],
                 "evaluator_wheel_sha256": rep["evaluator"]["wheel_sha256"],
                 "mode": rep["requested_mode"], "posture": rep["posture"]["effective"]},
        "publisher": {"actor_id": ACTOR, "marker": MARKER, "names": ["Mneme AP1 feedback publisher"]},
        "required_checks": REQUIRED,
        "limits": {"body_cap": 49152, "archive_compressed_max": 1_000_000, "archive_uncompressed_max": 2_000_000},
        "disclosure": "totals",
    }
    cfg.update(over)
    return cfg


def observed_for(rep, *, job="success", report_bytes=None, entries=None, zbytes=None):
    base, head = rep["base_sha"], rep["head_sha"]
    rb = report_bytes if report_bytes is not None else json.dumps(rep, indent=2).encode("utf-8")
    z = zbytes if zbytes is not None else zip_bytes(entries or [("gate-report.json", rb), ("summary.md", b"# s\n")])
    pull = {"number": PR, "state": "open", "base": {"repo": {"id": REPO_ID}, "ref": "main", "sha": base},
            "head": {"repo": {"id": REPO_ID}, "sha": head}}
    ref = {"object": {"sha": base}}
    steps = [{"number": 1, "name": "Evaluate the PR in the trusted workspace", "conclusion": "success"},
             {"number": 2, "name": "Preserve the gate evidence", "conclusion": "success"},
             {"number": 3, "name": "Gate decision",
              "conclusion": job if job in ("success", "failure") else "cancelled"}]
    return {
        "source_run": {"id": RUN_ID, "repository": {"id": REPO_ID}, "workflow_id": 404923975,
                       "path": ".github/workflows/mneme-trusted-gate.yml", "event": "pull_request_target",
                       "status": "completed", "conclusion": job, "run_number": RUN_NUMBER, "head_sha": head,
                       "head_repository": {"id": REPO_ID}, "pull_requests": [],
                       "run_attempt_obs": {"resolve": 1, "before_write": 1, "after_write": 1}},
        "jobs": [{"name": GATE_JOB, "id": 9001, "run_attempt": 1, "conclusion": job, "steps": steps}],
        "artifacts": [{"id": 14961731195, "name": f"mneme-gate-pr{PR}-{RUN_ID}", "size_in_bytes": len(z),
                       "digest": "sha256:" + hashlib.sha256(z).hexdigest(), "expired": False,
                       "workflow_run": {"id": RUN_ID, "repository_id": REPO_ID, "head_sha": head,
                                        "head_repository_id": REPO_ID}}],
        "artifact_zip_b64": base64.b64encode(z).decode("ascii"),
        "base_ref_obs": {k: dict(ref) for k in ("resolve", "before_write", "after_write")},
        "pull_obs": {k: copy.deepcopy(pull) for k in ("resolve", "before_write", "after_write")},
        "other_runs": [], "comments": [], "comments_complete": True, "receipt": None,
    }


def case(name="B1", job=None, **kw):
    rep = report_of(name)
    if job is None:
        job = "success" if rep["disposition"] == "success" else "failure"
    return config_for(rep), observed_for(rep, job=job, **kw), rep


def run(name="B1", job=None, **kw):
    cfg, obs, _ = case(name, job, **kw)
    return P.plan(cfg, obs)


def owned_comment(body, *, cid=777, updated="2026-11-24T10:00:00Z", edits=()):
    return {"id": cid, "user": {"id": ACTOR, "type": "Bot"}, "body": body, "created_at": updated,
            "updated_at": updated, "edits": list(edits)}


def receipt_for(plan_out, *, cid=777, run_id=RUN_ID, run_number=RUN_NUMBER, updated="2026-11-24T10:00:00Z", body=None):
    prop = plan_out["receipt_proposal"]
    b = body if body is not None else plan_out["body"]
    return {"comment_id": cid, "writer_id": ACTOR, "source_run_id": run_id, "run_number": run_number,
            "attempt": 1, "base_sha": prop["base_sha"], "head_sha": prop["head_sha"],
            "body_sha256": hashlib.sha256(b.encode()).hexdigest(), "updated_at": updated}


def existing(name="B1", **kw):
    """Observed state in which the planned body is already posted and receipted."""
    cfg, obs, _ = case(name, **kw)
    first = P.plan(cfg, obs)
    assert first["action"] == "CREATE"
    obs["comments"] = [owned_comment(first["body"])]
    obs["receipt"] = receipt_for(first)
    return cfg, obs, first


def no_write(out, reason):
    assert out == {"action": "NO_WRITE", "reason": reason}


def prose(body):
    """Generated text only: drop the marker line and any code spans."""
    return re.sub(r"`[^`\n]*`", "", body.split("\n", 1)[1])


APPROVAL = ["passed", "lgtm", "safe", "approved", "ok to merge", "all clear", "looks good", "merge blocked",
            "merge allowed", "architecture compliant", "all decisions protected", "all rules passed",
            "relevant enforcement observed", "introduced violation", "verified compliant", "tamper-proof",
            "production ready"]


def assert_body_safe(body):
    assert body.split("\n", 1)[0] == MARKER_LINE
    rest = body.split("\n", 1)[1]
    assert "<" not in rest and ">" not in rest and "@" not in rest and "&" not in rest and "](" not in rest
    assert not any(l.startswith("::") for l in body.split("\n"))
    low = prose(body).lower()
    for w in APPROVAL:
        assert w not in low
    assert body.encode("utf-8") and len(body.encode()) <= 49152
    assert "#### " not in body and "docs/" not in body


# ── P01 / P02 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["B1", "L1", "B5"])
def test_p01_pass_reports_create_one_scoped_plan(name):
    out = run(name)
    assert out["action"] == "CREATE" and out["reason"] == "OK_CREATE"
    assert out["pr_number"] == PR and out["comment_id"] is None
    body = out["body"]
    assert body.split("\n")[0] == MARKER_LINE
    assert "### Reported PASS — evaluated scope only" in body
    assert "Gate job conclusion (host-reported, separate from the report): success" in body
    assert "Recorded adapter disposition: `success`" in body
    assert "No violations reported in the evaluated scope." in body
    assert_body_safe(body)
    prop = out["receipt_proposal"]
    assert prop["body_sha256"] == hashlib.sha256(body.encode()).hexdigest()
    assert prop["writer_id"] == ACTOR and prop["attempt"] == 1 and prop["source_run_id"] == RUN_ID
    assert prop["comment_id"] is None


@pytest.mark.parametrize("name", ["B2", "L5", "B4"])
def test_p01_violation_reports_with_failed_gate_job(name):
    out = run(name)
    assert out["action"] == "CREATE"
    body = out["body"]
    assert "### Reported VIOLATION — strict gate failure (strict only)" in body
    assert "Gate job conclusion (host-reported, separate from the report): failure" in body
    assert "ADR-901" not in body and "install" not in body  # totals tier only
    assert_body_safe(body)


@pytest.mark.parametrize("name,job,heading", [
    ("L2", "failure", "Reported UNEVALUATED — evaluation incomplete (closed only)"),
    ("B3", "failure", "Reported UNEVALUATED — evaluation incomplete (closed only)"),
    ("L3", "success", "Reported UNEVALUATED — evaluation incomplete (open only)"),
    ("L4", "failure", "Reported REFUSED — policy or trusted-surface refusal"),
])
def test_p02_refused_and_unevaluated_reports(name, job, heading):
    out = run(name)
    assert out["action"] == "CREATE"
    assert f"### {heading}" in out["body"]
    assert f"separate from the report): {job}" in out["body"]
    assert "Reported PASS" not in out["body"]
    assert_body_safe(out["body"])


def _synth(rows, mode="strict", posture="closed"):
    rep = report_of("B1")
    order = ["VERIFIED_PASS", "WARN", "VIOLATION", "UNEVALUATED", "REFUSED", "SKIP"]
    rep["requested_mode"] = mode
    rep["posture"] = {"effective": posture, "source": "vars.MNEME_CI_AVAILABILITY", "fallback": None}
    rep["files"] = rows
    classes = [r["classification"] for r in rows]
    s = set(classes)
    if "REFUSED" in s:
        agg = "REFUSED"
    elif mode == "strict" and s & {"VIOLATION", "WARN"}:
        agg = "VIOLATION"
    elif "UNEVALUATED" in s:
        agg = "UNEVALUATED"
    elif s & {"VIOLATION", "WARN"}:
        agg = "WARN"
    elif "VERIFIED_PASS" in s:
        agg = "PASS"
    else:
        agg = "SKIP"
    rep["aggregate"] = {"classification": agg, "reason": "r", "partly_unevaluated": "UNEVALUATED" in s,
                        "counts": {c: classes.count(c) for c in order if c in classes}}
    rep["disposition"] = ("failure" if agg in ("REFUSED", "VIOLATION") or (agg == "UNEVALUATED" and posture == "closed")
                          else "success")
    return rep


def _row(path, cls, kind=None):
    r = {"path": path, "status": "A", "mode": "100644", "classification": cls, "reason": "x"}
    if kind:
        r["kind"] = kind
    return r


def _synth_plan(rep, job):
    return P.plan(config_for(rep), observed_for(rep, job=job))


def test_p02_synthetic_warn_skip_and_mixed():
    warn = _synth([_row("docs/a.md", "VIOLATION")], mode="warn")
    out = _synth_plan(warn, "success")
    assert out["action"] == "CREATE" and "### Reported WARN — advisory findings (warn mode only)" in out["body"]
    skip = _synth([_row("docs/a.md", "SKIP", "deleted")])
    out = _synth_plan(skip, "success")
    assert "### Reported SKIP — no file required evaluation" in out["body"]
    assert "No violations reported in the evaluated scope." not in out["body"]
    mixed = _synth([_row("docs/a.md", "REFUSED", "policy"), _row("docs/b.md", "VIOLATION"),
                    _row("docs/c.md", "UNEVALUATED", "mode")])
    out = _synth_plan(mixed, "failure")
    body = out["body"]
    assert "### Reported REFUSED" in body and "Partly unevaluated: yes" in body
    assert "REFUSED: 1" in body and "VIOLATION: 1" in body and "UNEVALUATED: 1" in body
    assert "some rows were not fully evaluated" in body.lower()
    assert_body_safe(body)


# ── status line (coordinator addition) ───────────────────────────────────────

def _status_of(out):
    lines = out["body"].split("\n")
    assert lines[0] == MARKER_LINE and lines[1] == ""
    assert lines[2].startswith("Status (advisory, not authenticated): ")
    return lines[2]


@pytest.mark.parametrize("name,expected", [
    ("B1", "Status (advisory, not authenticated): Reported PASS — evaluated scope only"),
    ("B2", "Status (advisory, not authenticated): Reported VIOLATION — strict gate failure (strict only)"),
    ("L4", "Status (advisory, not authenticated): Reported REFUSED — policy or trusted-surface refusal"),
    ("L3", "Status (advisory, not authenticated): Reported UNEVALUATED — evaluation incomplete (open only)"),
    ("L2", "Status (advisory, not authenticated): Reported UNEVALUATED — evaluation incomplete (closed only)"),
])
def test_p01_p02_status_line_is_first_visible_line(name, expected):
    out = run(name)
    assert _status_of(out) == expected
    low = _status_of(out).lower()
    for w in APPROVAL + ["✅", "\U0001f7e2"]:
        assert w not in low


def test_p02_status_line_states_partial_evaluation_up_front():
    rep = _synth([_row("docs/b.md", "VIOLATION"), _row("docs/c.md", "UNEVALUATED", "mode")])
    out = _synth_plan(rep, "failure")
    assert _status_of(out) == ("Status (advisory, not authenticated): Reported VIOLATION — strict gate failure (strict only). "
                               "Some rows were not fully evaluated")


def test_p08_neutral_status_lines():
    out = run("B1", job="cancelled")
    assert _status_of(out) == PFX + "The gate job did not complete, so no report is shown."


# ── P03 ──────────────────────────────────────────────────────────────────────

def _mutated(fn, name="B1"):
    cfg, obs, rep = case(name)
    fn(obs, cfg)
    return P.plan(cfg, obs)


@pytest.mark.parametrize("key,val", [("event", "pull_request"), ("workflow_id", 1), ("path", ".github/workflows/x.yml"),
                                     ("status", "in_progress"), ("repository", {"id": 7}), ("head_sha", "g" * 40),
                                     ("run_number", 0), ("id", True)])
def test_p03_wrong_source_run_is_rejected(key, val):
    no_write(_mutated(lambda o, c: o["source_run"].__setitem__(key, val)), "SOURCE_MISMATCH")


def test_p03_pr_controlled_pull_request_run_with_same_workflow_is_rejected():
    out = _mutated(lambda o, c: o["source_run"].update(event="pull_request", pull_requests=[{"number": PR}]))
    no_write(out, "SOURCE_MISMATCH")


@pytest.mark.parametrize("mut", [
    lambda o, c: o["jobs"].clear(),
    lambda o, c: o["jobs"].append(copy.deepcopy(o["jobs"][0])),
    lambda o, c: o["jobs"][0].__setitem__("name", "mneme trusted gate (copy)"),
    lambda o, c: o["jobs"][0].__setitem__("run_attempt", 2),
    lambda o, c: o["jobs"][0].__setitem__("conclusion", "neutral"),
    lambda o, c: o["jobs"][0].__setitem__("conclusion", None),
    lambda o, c: o["jobs"][0]["steps"].pop(1),
    lambda o, c: o["jobs"][0]["steps"][2].__setitem__("conclusion", "skipped"),
    lambda o, c: o["jobs"][0]["steps"][2].__setitem__("conclusion", "failure"),  # job success, decision failure
])
def test_p03_p08_gate_job_not_proven(mut):
    no_write(_mutated(mut), "JOB_UNPROVEN")


@pytest.mark.parametrize("name", ["mneme trusted gate", "Mneme  Trusted\tGate", "MNEME TRUSTED GATE",
                                  "My trusted gate publisher", "gate (PR battery)", "GATE (pr battery)",
                                  "mneme   check --mode warn", "Validate PR execution provenance"])
def test_p03_p15_forbidden_publisher_names(name):
    cfg, obs, _ = case()
    cfg["publisher"]["names"] = ["Mneme AP1 feedback publisher", name]
    no_write(P.plan(cfg, obs), "FORBIDDEN_NAME")


def test_p15_fixed_advisory_names_are_accepted():
    cfg, obs, _ = case()
    cfg["publisher"]["names"] = ["Mneme AP1 feedback publisher", "AP1 feedback resolve", "AP1 feedback write"]
    assert P.plan(cfg, obs)["action"] == "CREATE"


# ── P04 ──────────────────────────────────────────────────────────────────────

def test_p04_empty_pull_requests_list_is_not_itself_a_rejection():
    cfg, obs, _ = case()
    assert obs["source_run"]["pull_requests"] == []
    assert P.plan(cfg, obs)["action"] == "CREATE"


@pytest.mark.parametrize("name", [f"mneme-gate-pr0-{RUN_ID}", f"mneme-gate-pr0847-{RUN_ID}", f"mneme-gate-pr{PR}-{RUN_ID + 1}",
                                  f"mneme-gate-pr{PR}", f"mneme-gate-pr-{RUN_ID}", f"mneme-gate-pr12345678901-{RUN_ID}",
                                  f" mneme-gate-pr{PR}-{RUN_ID}", f"mneme-gate-pr{PR}-{RUN_ID}\n", f"mneme-gate-pr{PR}-{RUN_ID}-2",
                                  f"MNEME-GATE-PR{PR}-{RUN_ID}"])
def test_p04_wrong_artifact_name_is_rejected(name):
    out = _mutated(lambda o, c: o["artifacts"][0].__setitem__("name", name))
    no_write(out, "ARTIFACT_INVALID")


def test_p04_ambiguous_or_missing_artifact_is_rejected():
    def dup(o, c):
        o["artifacts"].append(dict(o["artifacts"][0], id=2))
    no_write(_mutated(dup), "ARTIFACT_INVALID")
    def other_pr(o, c):
        o["artifacts"].append(dict(o["artifacts"][0], id=2, name=f"mneme-gate-pr848-{RUN_ID}"))
    no_write(_mutated(other_pr), "ARTIFACT_INVALID")
    no_write(_mutated(lambda o, c: o["artifacts"].clear()), "ARTIFACT_INVALID")


@pytest.mark.parametrize("mut,reason", [
    (lambda o: o["pull_obs"][_k(o)].__setitem__("number", 848), "PR_MISMATCH"),
    (lambda o: o["pull_obs"][_k(o)].__setitem__("state", "closed"), "PR_MISMATCH"),
    (lambda o: o["pull_obs"][_k(o)]["base"].__setitem__("ref", "release"), "PR_MISMATCH"),
    (lambda o: o["pull_obs"][_k(o)]["base"]["repo"].__setitem__("id", 9), "PR_MISMATCH"),
    (lambda o: o["pull_obs"][_k(o)]["head"].__setitem__("sha", "1" * 40), "PR_MISMATCH"),
    (lambda o: o["pull_obs"].pop(_k(o)), "PR_MISMATCH"),
])
@pytest.mark.parametrize("which", ["resolve", "before_write", "after_write"])
def test_p04_pr_cross_check_at_every_observation(mut, reason, which):
    cfg, obs, _ = case()
    global _KEY
    _KEY = which
    mut(obs)
    no_write(P.plan(cfg, obs), reason)


_KEY = "resolve"


def _k(_o):
    return _KEY


def test_p04_artifact_metadata_must_bind_to_the_run():
    for key, val in [("id", RUN_ID + 1), ("repository_id", 5), ("head_sha", "2" * 40), ("head_repository_id", 5)]:
        out = _mutated(lambda o, c: o["artifacts"][0]["workflow_run"].__setitem__(key, val))
        no_write(out, "ARTIFACT_INVALID")
    no_write(_mutated(lambda o, c: o["artifacts"][0].__setitem__("expired", True)), "ARTIFACT_INVALID")
    no_write(_mutated(lambda o, c: o["artifacts"][0].pop("workflow_run")), "ARTIFACT_INVALID")


# ── P05 ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("which", ["resolve", "before_write", "after_write"])
@pytest.mark.parametrize("val", [2, 0, None, "1", True])
def test_p05_rerun_observed_at_any_point_abstains(which, val):
    out = _mutated(lambda o, c: o["source_run"]["run_attempt_obs"].__setitem__(which, val))
    no_write(out, "ATTEMPT_NOT_1")


def test_p05_missing_attempt_observation_and_other_attempt_of_same_run():
    no_write(_mutated(lambda o, c: o["source_run"].pop("run_attempt_obs")), "ATTEMPT_NOT_1")
    out = _mutated(lambda o, c: o["other_runs"].append({"id": RUN_ID, "run_number": RUN_NUMBER, "run_attempt": 2}))
    no_write(out, "ATTEMPT_NOT_1")


def test_p05_digest_size_and_expiry_checks():
    no_write(_mutated(lambda o, c: o["artifacts"][0].__setitem__("digest", "sha256:" + "0" * 64)), "ARTIFACT_INVALID")
    no_write(_mutated(lambda o, c: o["artifacts"][0].__setitem__("digest", "md5:abc")), "ARTIFACT_INVALID")
    no_write(_mutated(lambda o, c: o["artifacts"][0].pop("digest")), "ARTIFACT_INVALID")
    no_write(_mutated(lambda o, c: o["artifacts"][0].__setitem__("size_in_bytes", 5)), "ARTIFACT_INVALID")
    no_write(_mutated(lambda o, c: o.__setitem__("artifact_zip_b64", "!!!not base64")), "ARTIFACT_INVALID")


# ── P06 ──────────────────────────────────────────────────────────────────────

GOOD = json.dumps(report_of("B1")).encode()


def _bad_zip_plan(zbytes):
    cfg, obs, rep = case(zbytes=zbytes)
    return P.plan(cfg, obs)


@pytest.mark.parametrize("entries", [
    [("../gate-report.json", GOOD)],
    [("/gate-report.json", GOOD)],
    [("gate-report.json", GOOD), ("gate-report.json", GOOD)],
    [("gate-report.json", GOOD), ("extra.txt", b"x")],
    [("gate-report.json", GOOD), ("nested.zip", b"PK\x03\x04")],
    [("gate-report.json", GOOD), ("dir/", b"")],
    [("summary.md", b"x")],
    [("sub/gate-report.json", GOOD)],
    [("gate-report.json", b"PK\x03\x04" + b"0" * 30)],
    [],
])
def test_p06_malicious_archive_layouts_are_rejected(entries):
    no_write(_bad_zip_plan(zip_bytes(entries)), "ARTIFACT_INVALID")


def test_p06_symlink_and_special_entries_are_rejected():
    link = zip_bytes([("gate-report.json", GOOD)], attrs={"gate-report.json": 0o120777 << 16})
    no_write(_bad_zip_plan(link), "ARTIFACT_INVALID")
    fifo = zip_bytes([("gate-report.json", GOOD)], attrs={"gate-report.json": 0o010644 << 16})
    no_write(_bad_zip_plan(fifo), "ARTIFACT_INVALID")


def test_p06_corrupt_truncated_and_non_zip_bytes_are_rejected():
    z = zip_bytes([("gate-report.json", GOOD)])
    no_write(_bad_zip_plan(z[: len(z) // 2]), "ARTIFACT_INVALID")
    no_write(_bad_zip_plan(b"not a zip"), "ARTIFACT_INVALID")
    corrupt = bytearray(z)
    corrupt[40] ^= 0xFF
    no_write(_bad_zip_plan(bytes(corrupt)), "ARTIFACT_INVALID")


def test_p06_size_limits_bound_decompression():
    bomb = zip_bytes([("gate-report.json", b"0" * 3_000_000)])
    assert len(bomb) < 1_000_000
    no_write(_bad_zip_plan(bomb), "ARTIFACT_INVALID")
    cfg, obs, _ = case()
    cfg["limits"]["archive_compressed_max"] = 100
    no_write(P.plan(cfg, obs), "MALFORMED_INPUT")  # base64 payload exceeds the declared cap


def test_p06_p07_unreadable_report_base_is_unproven():
    for payload in [b"{ not json", b"\xef\xbb\xbf" + GOOD, b"[]", b"null", b'{"files": []}',
                    json.dumps({"base_sha": 5}).encode(), json.dumps({"base_sha": "A" * 40}).encode(),
                    json.dumps({"base_sha": "a" * 40 + "\n"}).encode()]:
        no_write(_bad_zip_plan(zip_bytes([("gate-report.json", payload)])), "BASE_UNPROVEN")


# ── P07 ──────────────────────────────────────────────────────────────────────

def test_p07_base_moved_between_observations_or_lagging_pr_base():
    for which in ("before_write", "after_write", "resolve"):
        no_write(_mutated(lambda o, c: o["base_ref_obs"][which].__setitem__("object", {"sha": "3" * 40})), "BASE_MOVED")
    no_write(_mutated(lambda o, c: o["pull_obs"]["resolve"]["base"].__setitem__("sha", "4" * 40)), "BASE_MOVED")


@pytest.mark.parametrize("bad", [None, {"object": {}}, {"object": {"sha": "xyz"}}, {"object": {"sha": "A" * 40}}])
def test_p07_missing_or_invalid_tip_is_unproven(bad):
    def mut(o, c):
        if bad is None:
            del o["base_ref_obs"]["after_write"]
        else:
            o["base_ref_obs"]["after_write"] = bad
    no_write(_mutated(mut), "BASE_UNPROVEN")


def test_p07_report_base_must_equal_the_independent_tip():
    cfg, obs, rep = case()
    rep2 = copy.deepcopy(rep)
    rep2["base_sha"] = "5" * 40
    z = zip_bytes([("gate-report.json", json.dumps(rep2).encode())])
    obs2 = observed_for(rep, zbytes=z)
    no_write(P.plan(cfg, obs2), "BASE_MOVED")


def test_p07_wrong_pins_or_head_in_report_are_unavailable():
    for field, val in [("adapter_sha256", "0" * 64), ("evaluator_commit", "0" * 40),
                       ("evaluator_wheel_sha256", "0" * 64), ("mode", "warn"), ("posture", "open")]:
        cfg, obs, _ = case()
        cfg["pins"][field] = val
        out = P.plan(cfg, obs)
        assert out["action"] == "UNAVAILABLE" and out["reason"] == "REPORT_UNAVAILABLE"
    rep = report_of("B1")
    rep["head_sha"] = "6" * 40
    z = zip_bytes([("gate-report.json", json.dumps(rep).encode())])
    cfg, obs, _ = case(zbytes=z)
    out = P.plan(cfg, obs)
    assert out["action"] == "UNAVAILABLE" and out["reason"] == "REPORT_UNAVAILABLE"


def test_p07_coherent_forged_report_is_displayed_as_unauthenticated_snapshot_only():
    rep = report_of("B1")
    rep["files"][0]["path"] = "docs/forged.md"
    out = P.plan(config_for(rep), observed_for(rep))
    assert out["action"] == "CREATE"
    assert "not authenticated" in out["body"]
    assert "required gate result is separate" in out["body"]
    assert "authentic" not in prose(out["body"]).lower().replace("not authenticated", "")


# ── P08 ──────────────────────────────────────────────────────────────────────

def test_p08_gate_and_report_disagreement_is_unavailable_never_a_verdict():
    for name, job in [("B1", "failure"), ("B2", "success"), ("L3", "failure"), ("L2", "success")]:
        cfg, obs, _ = case(name, job=job)
        # keep the decision step coherent with the job so only the report disagrees
        out = P.plan(cfg, obs)
        assert out["action"] == "UNAVAILABLE" and out["reason"] == "GATE_REPORT_DISAGREE", name
        assert out["write"] == "CREATE"
        assert "Reported" not in out["body"].split("\n", 3)[2]
        assert "Reported PASS" not in out["body"] and "Reported VIOLATION" not in out["body"]
        assert "Recorded adapter disposition" not in out["body"]


@pytest.mark.parametrize("job", ["cancelled", "skipped", "timed_out"])
def test_p08_incomplete_gate_job_is_neutral_unavailable_after_pr_established(job):
    out = run("B1", job=job)
    assert out["action"] == "UNAVAILABLE" and out["reason"] == "GATE_JOB_INCOMPLETE"
    assert "The gate job did not complete" in out["body"]
    assert f"separate from the report): {job}" in out["body"]
    assert "Reported" not in out["body"] and "Recorded adapter" not in out["body"]
    cfg, obs, _ = case("B1", job=job)
    obs["pull_obs"]["after_write"]["state"] = "closed"
    no_write(P.plan(cfg, obs), "PR_MISMATCH")
    cfg, obs, _ = case("B1", job=job)
    obs["artifacts"].clear()
    no_write(P.plan(cfg, obs), "ARTIFACT_INVALID")


def test_p08_no_report_in_archive_with_gate_failure_is_not_a_synthetic_verdict():
    out = _bad_zip_plan(zip_bytes([("summary.md", b"x")]))
    no_write(out, "ARTIFACT_INVALID")


# ── P09 ──────────────────────────────────────────────────────────────────────

def test_p09_newer_run_or_newer_receipt_makes_this_run_stale():
    out = _mutated(lambda o, c: o["other_runs"].append({"id": 5, "run_number": RUN_NUMBER + 1, "run_attempt": 1}))
    no_write(out, "STALE_RUN")
    out = _mutated(lambda o, c: o["other_runs"].append({"id": 5, "run_number": RUN_NUMBER, "run_attempt": 1}))
    no_write(out, "STALE_RUN")
    cfg, obs, first = existing()
    obs["receipt"] = receipt_for(first, run_number=RUN_NUMBER + 5, run_id=RUN_ID + 1)
    no_write(P.plan(cfg, obs), "STALE_RUN")


def test_p09_older_runs_do_not_block_and_this_run_may_appear_in_the_list():
    def mut(o, c):
        o["other_runs"] += [{"id": 5, "run_number": RUN_NUMBER - 1, "run_attempt": 1},
                            {"id": RUN_ID, "run_number": RUN_NUMBER, "run_attempt": 1}]
    assert _mutated(mut)["action"] == "CREATE"


def test_p09_malformed_other_runs_abstain():
    no_write(_mutated(lambda o, c: o["other_runs"].append({"id": "x"})), "MALFORMED_INPUT")


# ── P10 ──────────────────────────────────────────────────────────────────────

def test_p10_same_run_same_body_is_noop_and_new_run_updates():
    cfg, obs, first = existing()
    out = P.plan(cfg, obs)
    assert out["action"] == "NOOP" and out["reason"] == "OK_UNCHANGED" and out["comment_id"] == 777
    # a later run (different body) updates the same comment
    cfg2, obs2, rep = case("B2")
    obs2["comments"] = obs["comments"]
    obs2["receipt"] = obs["receipt"]
    obs2["source_run"]["run_number"] = RUN_NUMBER + 1
    obs2["source_run"]["id"] = RUN_ID + 1
    obs2["artifacts"][0]["name"] = f"mneme-gate-pr{PR}-{RUN_ID + 1}"
    obs2["artifacts"][0]["workflow_run"]["id"] = RUN_ID + 1
    obs2["receipt"]["run_number"] = RUN_NUMBER
    upd = P.plan(cfg2, obs2)
    assert upd["action"] == "UPDATE" and upd["reason"] == "OK_UPDATE" and upd["comment_id"] == 777
    assert upd["receipt_proposal"]["comment_id"] == 777 and upd["receipt_proposal"]["source_run_id"] == RUN_ID + 1


def test_p10_duplicate_owned_comments_and_foreign_marker_conflict():
    cfg, obs, first = existing()
    obs["comments"].append(owned_comment(first["body"], cid=778))
    assert P.plan(cfg, obs) == {"action": "CONFLICT", "reason": "OWNERSHIP_AMBIGUOUS"}


def test_p10_create_when_nothing_exists_and_plan_has_no_raw_observed_text():
    cfg, obs, _ = case()
    obs["comments"] = [{"id": 1, "user": {"id": 42, "type": "User"}, "body": "SENTINEL-HUMAN-TEXT @someone",
                        "created_at": "x", "updated_at": "SENTINEL-TS", "edits": None}]
    out = P.plan(cfg, obs)
    assert out["action"] == "CREATE"
    assert "SENTINEL" not in json.dumps(out)


# ── P11 ──────────────────────────────────────────────────────────────────────

def _conflict(mut, reason, name="B1"):
    cfg, obs, first = existing(name)
    mut(obs, first)
    assert P.plan(cfg, obs) == {"action": "CONFLICT", "reason": reason}


def test_p11_human_and_shared_bot_spoofing_never_edits_foreign_comment():
    def human(o, f):
        o["comments"][0]["user"] = {"id": 42, "type": "User"}
    _conflict(human, "OWNERSHIP_AMBIGUOUS")
    def other_bot(o, f):
        o["comments"][0]["user"] = {"id": 41898282, "type": "Bot"}  # e.g. a shared github-actions style bot
    _conflict(other_bot, "OWNERSHIP_AMBIGUOUS")
    def same_id_not_bot(o, f):
        o["comments"][0]["user"]["type"] = "User"
    _conflict(same_id_not_bot, "OWNERSHIP_AMBIGUOUS")


def test_p11_foreign_marker_with_no_owned_comment_is_conflict_not_create():
    cfg, obs, _ = case()
    obs["comments"] = [{"id": 9, "user": {"id": 42, "type": "User"}, "body": MARKER_LINE + "\nfake",
                        "created_at": "x", "updated_at": "x", "edits": []}]
    assert P.plan(cfg, obs) == {"action": "CONFLICT", "reason": "OWNERSHIP_AMBIGUOUS"}


def test_p11_marker_must_be_the_exact_first_line_of_an_owned_comment():
    def moved(o, f):
        o["comments"][0]["body"] = "hello\n" + f["body"]
    _conflict(moved, "COMMENT_DELETED")  # not owned by the first-line rule, so the receipt has no comment


def _human(body, cid=9):
    return {"id": cid, "user": {"id": 42, "type": "User"}, "body": body, "created_at": "x",
            "updated_at": "x", "edits": []}


def test_p11_marker_merely_mentioned_by_a_human_is_ignored():
    cfg, obs, first = existing()
    for body in [f"fyi {MARKER}", f"quote\n{MARKER_LINE}", f"see {MARKER_LINE} above"]:
        o2 = copy.deepcopy(obs)
        o2["comments"].append(_human(body))
        out = P.plan(cfg, o2)
        assert out["action"] == "NOOP" and out["foreign_marker_comments"] == 0, body
    # and a stale proven snapshot still updates while a human merely mentions the marker
    cfg2, obs2, _ = case("B2")
    obs2["comments"] = obs["comments"] + [_human(f"fyi {MARKER}")]
    obs2["receipt"] = dict(obs["receipt"], run_number=RUN_NUMBER - 1, source_run_id=RUN_ID - 1)
    out = P.plan(cfg2, obs2)
    assert out["action"] == "UPDATE" and out["comment_id"] == 777


def test_p11_first_line_spoof_with_proven_owned_comment_updates_and_is_counted():
    cfg, obs, first = existing()
    obs["comments"].append(_human(MARKER_LINE + "\nfake"))
    obs["comments"].append(_human(MARKER_LINE + "\r\nfake", cid=10))
    out = P.plan(cfg, obs)
    assert out["action"] == "NOOP" and out["foreign_marker_comments"] == 2
    cfg2, obs2, _ = case("B2")
    obs2["comments"] = obs["comments"]
    obs2["receipt"] = dict(obs["receipt"], run_number=RUN_NUMBER - 1, source_run_id=RUN_ID - 1)
    out = P.plan(cfg2, obs2)
    assert out["action"] == "UPDATE" and out["comment_id"] == 777 and out["foreign_marker_comments"] == 2
    assert out["comment_id"] != 9 and out["comment_id"] != 10


def test_p11_first_line_spoof_without_a_proven_owned_comment_conflicts_never_creates():
    cfg, obs, _ = case()
    obs["comments"] = [_human(MARKER_LINE + "\nfake")]
    assert P.plan(cfg, obs) == {"action": "CONFLICT", "reason": "OWNERSHIP_AMBIGUOUS"}
    cfg, obs, first = existing()
    obs["comments"][0]["edits"] = None  # owned comment not proven
    obs["comments"].append(_human(MARKER_LINE))
    assert P.plan(cfg, obs)["action"] == "CONFLICT"


def test_p11_edited_deleted_or_unproven_comments_conflict():
    _conflict(lambda o, f: o["comments"][0].__setitem__("body", f["body"] + "\nedited"), "EDIT_DETECTED")
    _conflict(lambda o, f: o["comments"][0].__setitem__("updated_at", "2026-11-25T00:00:00Z"), "EDIT_DETECTED")
    _conflict(lambda o, f: o["comments"][0].__setitem__("edits", [{"editor_id": 42, "edited_at": "t"}]), "EDIT_DETECTED")
    _conflict(lambda o, f: o["comments"][0].__setitem__("edits", None), "EDIT_DETECTED")
    _conflict(lambda o, f: o["comments"].clear(), "COMMENT_DELETED")
    _conflict(lambda o, f: o.__setitem__("receipt", None), "RECEIPT_MISSING")
    _conflict(lambda o, f: o["receipt"].__setitem__("comment_id", 12345), "OWNERSHIP_AMBIGUOUS")
    _conflict(lambda o, f: o["receipt"].__setitem__("writer_id", 1), "OWNERSHIP_AMBIGUOUS")


def test_p11_identical_body_edit_by_another_editor_is_still_detected():
    cfg, obs, first = existing()
    obs["comments"][0]["edits"] = [{"editor_id": 42, "edited_at": "t"}]
    assert P.plan(cfg, obs)["reason"] == "EDIT_DETECTED"


def test_p11_publishers_own_edits_are_not_a_conflict():
    cfg, obs, first = existing()
    obs["comments"][0]["edits"] = [{"editor_id": ACTOR, "edited_at": "t"}]
    assert P.plan(cfg, obs)["action"] == "NOOP"


def test_p11_report_data_containing_the_marker_never_forges_the_first_line():
    rep = report_of("B1")
    hostile = MARKER_LINE + "\n" + MARKER_LINE
    rep["files"][0]["path"] = hostile
    out = P.plan(config_for(rep), observed_for(rep))
    assert out["action"] == "CREATE"
    body = out["body"]
    assert body.count(MARKER_LINE) == 1 and body.split("\n")[0] == MARKER_LINE
    assert body.count(MARKER) == 1  # not even an escaped copy: totals tier carries no paths
    # and a stored copy of this body by another author is not an owned comment
    cfg, obs, _ = case()
    obs["comments"] = [{"id": 3, "user": {"id": 42, "type": "User"}, "body": body, "created_at": "t",
                        "updated_at": "t", "edits": []}]
    assert P.plan(cfg, obs)["reason"] == "OWNERSHIP_AMBIGUOUS"


def test_p11_renderer_escapes_marker_if_it_ever_reaches_the_body():
    import importlib.util as u
    rspec = u.spec_from_file_location("r_under_test", REPO_ROOT / "scripts" / "ci" / "render_pr_feedback.py")
    mod = u.module_from_spec(rspec)
    rspec.loader.exec_module(mod)
    assert MARKER_LINE not in mod.code_span(MARKER_LINE)
    assert "\\x3c!--" in mod.code_span(MARKER_LINE) and "--\\x3e" in mod.code_span(MARKER_LINE)


# ── P12 ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("mut", [
    lambda o: o["pull_obs"]["resolve"]["head"].__setitem__("repo", None),
    lambda o: o["pull_obs"]["after_write"]["head"].__setitem__("repo", {"id": 99}),
    lambda o: o["pull_obs"]["before_write"]["head"].pop("repo"),
    lambda o: o["source_run"]["head_repository"].__setitem__("id", 99),
    lambda o: o["source_run"].pop("head_repository"),
])
def test_p12_fork_or_unknown_head_repository_is_deferred(mut):
    cfg, obs, _ = case()
    mut(obs)
    # the artifact binds head_repository_id to the run; keep it coherent for the fork cases
    obs["artifacts"][0]["workflow_run"]["head_repository_id"] = _get_head_repo(obs)
    out = P.plan(cfg, obs)
    assert out == {"action": "NO_WRITE", "reason": "FORK_DEFERRED"}


def _get_head_repo(obs):
    return (obs["source_run"].get("head_repository") or {}).get("id")


# ── P13 ──────────────────────────────────────────────────────────────────────

def test_p13_renderer_failure_is_neutral_unavailable_and_never_raises(monkeypatch):
    renderer = P._renderer()

    def boom(*a, **k):
        raise RuntimeError("renderer exploded SENTINEL")
    monkeypatch.setattr(renderer, "render", boom)
    cfg, obs, _ = case()
    out = P.plan(cfg, obs)
    assert out["action"] == "UNAVAILABLE" and out["reason"] == "REPORT_UNAVAILABLE"
    assert "The gate report could not be displayed" in out["body"]
    assert "SENTINEL" not in json.dumps(out) and "Reported" not in out["body"]


def test_p13_renderer_exit_2_and_odd_return_are_unavailable(monkeypatch):
    renderer = P._renderer()
    for ret in [(2, "## x"), (0, "no disposition line here"), (0, "Recorded adapter disposition: `success`\n"
                                                                   "Recorded adapter disposition: `success`\n")]:
        monkeypatch.setattr(renderer, "render", lambda *a, _r=ret, **k: _r)
        out = P.plan(*case()[:2])
        assert out["action"] == "UNAVAILABLE" and out["reason"] == "REPORT_UNAVAILABLE"


def test_p13_internal_fault_abstains(monkeypatch):
    monkeypatch.setattr(P, "_check_source", lambda *a: (_ for _ in ()).throw(ZeroDivisionError()))
    assert P.plan(*case()[:2]) == {"action": "NO_WRITE", "reason": "MALFORMED_INPUT"}


@pytest.mark.parametrize("cfg,obs", [(None, None), ({}, {}), ("x", []), (1, 1)])
def test_p13_garbage_inputs_abstain(cfg, obs):
    no_write(P.plan(cfg, obs), "MALFORMED_INPUT")


def test_p13_shape_and_size_limits():
    cfg, obs, _ = case()
    for mut in [lambda o: o.pop("jobs"), lambda o: o.__setitem__("comments", "x"),
                lambda o: o.__setitem__("comments", [{}] * 5),
                lambda o: o["comments"].extend([owned_comment("x", cid=i) for i in range(1001)]),
                lambda o: o.__setitem__("x", "y" * (P.MAX_BODY_STR + 1)),
                lambda o: o.__setitem__("x", object())]:
        o2 = copy.deepcopy(obs)
        try:
            mut(o2)
        except Exception:
            continue
        no_write(P.plan(cfg, o2), "MALFORMED_INPUT")
    deep = obs
    for _ in range(20):
        deep = {"d": deep}
    no_write(P.plan(cfg, deep), "MALFORMED_INPUT")
    no_write(P.plan(cfg, dict(obs, receipt={"comment_id": "x"})), "MALFORMED_INPUT")
    no_write(P.plan(cfg, dict(obs, comments=[dict(owned_comment("x"), edits="nope")])), "MALFORMED_INPUT")


# ── P14 ──────────────────────────────────────────────────────────────────────

def test_p14_hostile_report_values_never_reach_the_body():
    rep = _synth([_row("docs/`@bob <b>[x](http://e)</b>\n::error::x‮\ud800.md", "VIOLATION"),
                  _row("safe to merge.md", "REFUSED", "policy")])
    rep["files"][0]["reason"] = "SENTINEL-REASON @everyone"
    rep["aggregate"]["reason"] = "SENTINEL-AGG"
    rep["annotations"] = ["::error::SENTINEL-ANNOT"]
    rep["files"][0]["stdout"] = json.dumps({"violations": [{"rule": "SENTINEL-RULE", "input_path": "x"}]})
    out = P.plan(config_for(rep), observed_for(rep, job="failure"))
    assert out["action"] == "CREATE"
    body = out["body"]
    assert "SENTINEL" not in body and "everyone" not in body and "bob" not in body
    assert "safe to merge" not in body.lower()
    assert_body_safe_hostile(body)
    json.dumps(out).encode("ascii")


def assert_body_safe_hostile(body):
    rest = body.split("\n", 1)[1]
    assert "<" not in rest and ">" not in rest and "@" not in rest
    assert not any(l.startswith("::") for l in body.split("\n"))
    assert "#### " not in body


def test_p14_totals_tier_has_no_paths_details_or_rows_even_for_b2():
    out = run("B2")
    assert "#### " not in out["body"] and "`docs/" not in out["body"] and "ADR-901" not in out["body"]
    assert "File rows: 1 (VIOLATION: 1)" in out["body"]


def test_p14_body_cap_degrades_to_neutral_then_abstains():
    cfg, obs, _ = case()
    full = run()["body"]
    neutral_size = len(run("B1", job="cancelled")["body"].encode())
    small = len(full.encode()) - 10
    assert neutral_size < small
    cfg["limits"]["body_cap"] = small
    out = P.plan(cfg, obs)
    assert out["action"] == "UNAVAILABLE" and out["reason"] == "BODY_TOO_LARGE" and out["write"] == "CREATE"
    assert len(out["body"].encode()) <= small and "Reported" not in out["body"]
    cfg["limits"]["body_cap"] = 200
    no_write(P.plan(cfg, obs), "BODY_TOO_LARGE")
    cfg["limits"]["body_cap"] = len(full.encode())
    assert P.plan(cfg, obs)["action"] == "CREATE"
    cfg["limits"]["body_cap"] = len(full.encode()) - 1
    assert P.plan(cfg, obs)["reason"] == "BODY_TOO_LARGE"


def test_p14_whole_generated_body_has_no_approval_vocabulary_for_every_report():
    for name in HIST:
        out = run(name)
        assert out["action"] == "CREATE", name
        assert_body_safe(out["body"])


def test_p14_footer_and_advisory_line_are_fixed_text():
    body = run()["body"]
    assert body.endswith("Revision-scoped advisory snapshot. Comments may be edited or become stale; edit checks occur "
                         "on reconciliation, not continuously. Consult the separately reported gate check.")
    assert "Advisory report-derived snapshot — not authenticated; required gate result is separate" in body
    assert "- Source run: `45479481003` (attempt 1)" in body


# ── P15 ──────────────────────────────────────────────────────────────────────

FORBIDDEN_IMPORTS = {"socket", "urllib", "http", "ssl", "subprocess", "requests", "httpx", "ftplib", "smtplib",
                     "asyncio", "multiprocessing", "ctypes", "os", "shutil", "tempfile"}
FORBIDDEN_ATTRS = {("os", "system"), ("os", "popen"), ("os", "environ"), ("os", "getenv"), ("os", "putenv"),
                   ("sys", "modules")}
FORBIDDEN_ATTR_NAMES = {"import_module", "write_text", "write_bytes", "unlink", "rmdir", "mkdir", "touch",
                        "rename", "environ", "getenv", "system", "popen"}
FORBIDDEN_NAMES = {"getenv", "environ", "system", "popen", "__import__", "eval", "exec", "compile"}
ALLOWED_IMPORTS = {"argparse", "base64", "binascii", "hashlib", "importlib", "io", "json", "re", "sys",
                   "zipfile", "pathlib", "typing", "__future__"}


def _strings(node):
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def ast_violations(source):
    """Static prohibitions for the offline planner. Returns a list of violation labels."""
    tree = ast.parse(source)
    bad = []
    assigns = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            assigns[node.targets[0].id] = node.value
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                if top in FORBIDDEN_IMPORTS or top not in ALLOWED_IMPORTS:
                    bad.append("import " + top)
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in FORBIDDEN_IMPORTS or top not in ALLOWED_IMPORTS:
                bad.append("from " + top)
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and (node.value.id, node.attr) in FORBIDDEN_ATTRS:
                bad.append(f"attr {node.value.id}.{node.attr}")
            if node.attr in FORBIDDEN_ATTR_NAMES:
                bad.append("attr ." + node.attr)
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            bad.append("name " + node.id)
        elif isinstance(node, ast.Call):
            func = node.func
            fname = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            if fname == "open":
                mode = node.args[1] if len(node.args) > 1 else next(
                    (k.value for k in node.keywords if k.arg == "mode"), None)
                if mode is not None and not (isinstance(mode, ast.Constant) and isinstance(mode.value, str)
                                             and not set(mode.value) & set("wax+")):
                    bad.append("open with write or unknown mode")
            if fname == "spec_from_file_location":
                arg = node.args[1] if len(node.args) > 1 else None
                value = assigns.get(arg.id) if isinstance(arg, ast.Name) else None
                names = {n.id for n in ast.walk(value) if isinstance(n, ast.Name)} if value is not None else set()
                if value is None or _strings(value) != {"render_pr_feedback.py"} or "__file__" not in names:
                    bad.append("spec_from_file_location with a path other than the renderer constant")
    return bad


def test_p15_publisher_module_has_no_network_subprocess_env_or_dynamic_import():
    assert ast_violations(PUBLISHER.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("snippet", [
    "import os",
    "from os import environ",
    "import socket",
    "import urllib.request",
    "from http import client",
    "import subprocess",
    "import importlib\nimportlib.import_module('socket')",
    "__import__('os')",
    "import sys\nsys.modules['os']",
    "open('f', 'w')",
    "open('f', mode='a')",
    "open('f', 'rb+')",
    "m = 'w'\nopen('f', m)",
    "eval('1')",
    "exec('1')",
    "compile('1', '', 'exec')",
    "from pathlib import Path\nPath('x').write_text('')",
    "import importlib.util\nimportlib.util.spec_from_file_location('x', '/tmp/adr033_c4_gate.py')",
    "import importlib.util\nfrom pathlib import Path\np = Path(__file__).parent / 'adr033_c4_gate.py'\n"
    "importlib.util.spec_from_file_location('x', p)",
    "import importlib.util\nfrom pathlib import Path\np = Path('/etc/x') / 'render_pr_feedback.py'\n"
    "importlib.util.spec_from_file_location('x', p)",
    "import importlib.util\nimportlib.util.spec_from_file_location('x')",
    "import ctypes",
    "import tempfile",
])
def test_p15_ast_checker_catches_each_prohibited_construct(snippet):
    assert ast_violations(snippet), snippet


def test_p15_ast_checker_accepts_the_permitted_constructs():
    ok = ("import importlib.util\nfrom pathlib import Path\n"
          "p = Path(__file__).resolve().parent / 'render_pr_feedback.py'\n"
          "s = importlib.util.spec_from_file_location('x', p)\n"
          "open('f', 'rb')\nopen('f')\nimport re\nre.compile('x')\n")
    assert ast_violations(ok) == []


def test_p15_no_adapter_or_evaluator_reference_and_no_credential_shaped_literals():
    text = PUBLISHER.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] + [getattr(node, "module", "") or ""]
            assert not any("adr033" in n or n.split(".")[0] == "mneme" for n in names)
    for lit in _strings(tree):
        assert not re.search(r"gh[pousr]_[A-Za-z0-9]|Bearer |Authorization|BEGIN [A-Z ]*PRIVATE KEY", lit)
    assert "adr033_c4_gate" not in text


def test_p15_marker_config_is_validated_and_names_are_not_taken_from_observed():
    for bad in ["", "has space", "<!-- x -->", "a" * 65, "x\n"]:
        cfg, obs, _ = case()
        cfg["publisher"]["marker"] = bad
        no_write(P.plan(cfg, obs), "MALFORMED_INPUT")
    cfg, obs, _ = case()
    obs["publisher_names"] = ["mneme trusted gate"]  # ignored: trusted values come from config only
    assert P.plan(cfg, obs)["action"] == "CREATE"
    cfg["disclosure"] = "paths"
    no_write(P.plan(cfg, obs), "MALFORMED_INPUT")


def test_p15_every_plan_reason_is_in_the_fixed_vocabulary():
    plans = [run("B1"), run("B2", job="success"), run("B1", job="cancelled"), P.plan(None, None),
             _mutated(lambda o, c: o["source_run"].__setitem__("event", "x"))]
    for p in plans:
        assert p["reason"] in P.REASONS
        assert p["action"] in {"NO_WRITE", "CREATE", "UPDATE", "NOOP", "UNAVAILABLE", "CONFLICT"}
    assert P.REASONS == {"FORBIDDEN_NAME", "MALFORMED_INPUT", "SOURCE_MISMATCH", "ATTEMPT_NOT_1", "JOB_UNPROVEN",
                         "ARTIFACT_INVALID", "PR_MISMATCH", "FORK_DEFERRED", "BASE_MOVED", "BASE_UNPROVEN",
                         "STALE_RUN", "BODY_TOO_LARGE", "COMMENTS_INCOMPLETE", "RECEIPT_MISMATCH",
                         "GATE_JOB_INCOMPLETE", "REPORT_UNAVAILABLE",
                         "GATE_REPORT_DISAGREE", "OWNERSHIP_AMBIGUOUS", "EDIT_DETECTED", "RECEIPT_MISSING",
                         "COMMENT_DELETED", "OK_CREATE", "OK_UPDATE", "OK_UNCHANGED"}


# ── P16 ──────────────────────────────────────────────────────────────────────

def test_p16_plan_is_deterministic_and_independent_of_key_order():
    cfg, obs, _ = case("B2")
    a = P.plan(cfg, obs)
    b = P.plan(copy.deepcopy(cfg), copy.deepcopy(obs))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    shuffled = {k: obs[k] for k in reversed(list(obs))}
    shuffled["source_run"] = {k: obs["source_run"][k] for k in reversed(list(obs["source_run"]))}
    assert P.plan(cfg, shuffled) == a
    assert a["body"].encode("utf-8") == b["body"].encode("utf-8") and "\r" not in a["body"]


def test_p16_plan_does_not_mutate_its_inputs():
    cfg, obs, _ = case("L3")
    c0, o0 = copy.deepcopy(cfg), copy.deepcopy(obs)
    P.plan(cfg, obs)
    assert cfg == c0 and obs == o0


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cli(*args):
    return subprocess.run([sys.executable, "-I", str(PUBLISHER), *args], capture_output=True)


def test_p16_cli_prints_plan_json_for_any_plan_and_exit_2_for_bad_input(tmp_path):
    cfg, obs, _ = case("B1")
    f = tmp_path / "fx.json"
    f.write_text(json.dumps({"config": cfg, "observed": obs}), encoding="utf-8")
    res = _cli(str(f))
    assert res.returncode == 0 and res.stderr == b""
    assert json.loads(res.stdout) == P.plan(cfg, obs) and b"\r" not in res.stdout
    obs["source_run"]["event"] = "pull_request"
    f.write_text(json.dumps({"config": cfg, "observed": obs}), encoding="utf-8")
    res = _cli(str(f))
    assert res.returncode == 0 and json.loads(res.stdout) == {"action": "NO_WRITE", "reason": "SOURCE_MISMATCH"}
    for content in ["not json", "[]", '{"config": 1}', ""]:
        f.write_text(content, encoding="utf-8")
        res = _cli(str(f))
        assert res.returncode == 2 and b"Traceback" not in res.stderr
    assert _cli(str(tmp_path / "missing.json")).returncode == 2
    assert _cli().returncode == 2 and b"Traceback" not in _cli().stderr


# ── stage A review follow-ups ────────────────────────────────────────────────

def test_p03_p08_preserve_step_must_be_success():
    for concl in ("failure", "skipped", "cancelled", None):
        out = _mutated(lambda o, c: o["jobs"][0]["steps"][1].__setitem__("conclusion", concl))
        no_write(out, "JOB_UNPROVEN")


def test_p03_p08_run_conclusion_must_equal_gate_job_conclusion():
    no_write(_mutated(lambda o, c: o["source_run"].__setitem__("conclusion", "cancelled")), "SOURCE_MISMATCH")
    no_write(_mutated(lambda o, c: o["source_run"].__setitem__("conclusion", "failure")), "SOURCE_MISMATCH")
    no_write(_mutated(lambda o, c: o["source_run"].pop("conclusion")), "SOURCE_MISMATCH")
    cfg, obs, _ = case("B1", job="cancelled")
    obs["source_run"]["conclusion"] = "success"
    no_write(P.plan(cfg, obs), "SOURCE_MISMATCH")


def test_p14_fixed_tier_line_follows_the_totals():
    for name in ("B1", "B2", "L3", "L4"):
        body = run(name)["body"]
        line = "Per-file rows and finding details are not shown at this disclosure tier."
        assert body.count(line) == 1
        assert body.index(line) < body.index("Revision-scoped advisory snapshot.")
        assert body.index("Partly unevaluated") < body.index(line)
    assert "not shown at this disclosure tier" not in run("B1", job="cancelled")["body"]


def test_p10_comments_must_be_declared_complete():
    for val in (None, False, 1, "true", 0):
        cfg, obs, _ = case()
        obs["comments_complete"] = val
        no_write(P.plan(cfg, obs), "COMMENTS_INCOMPLETE")
    cfg, obs, _ = case()
    del obs["comments_complete"]
    no_write(P.plan(cfg, obs), "COMMENTS_INCOMPLETE")
    cfg, obs, _ = case()
    obs["comments"] = "x"
    no_write(P.plan(cfg, obs), "MALFORMED_INPUT")  # malformed shape wins over completeness


def test_p14_body_too_large_does_not_mask_stale_run():
    cfg, obs, _ = case()
    cfg["limits"]["body_cap"] = 100
    obs["other_runs"].append({"id": 5, "run_number": RUN_NUMBER + 1, "run_attempt": 1})
    no_write(P.plan(cfg, obs), "STALE_RUN")
    obs["other_runs"].clear()
    no_write(P.plan(cfg, obs), "BODY_TOO_LARGE")


@pytest.mark.parametrize("key,val", [("run_number", RUN_NUMBER - 1), ("head_sha", "7" * 40), ("base_sha", "8" * 40)])
def test_p11_receipt_for_same_run_with_different_identity_is_a_mismatch(key, val):
    cfg, obs, first = existing()
    rc = dict(obs["receipt"])
    rc[key] = val
    obs["receipt"] = rc
    assert P.plan(cfg, obs) == {"action": "CONFLICT", "reason": "RECEIPT_MISMATCH"}


def test_p14_neutral_and_positive_bodies_label_mode_and_posture_as_configured():
    for out in (run("B1", job="cancelled"), run("B1")):
        assert "- Violation mode (configured): strict" in out["body"]
        assert "- Availability posture (configured): closed" in out["body"]


def test_p06_archive_must_start_at_offset_zero():
    cfg, obs, rep = case()
    z = b"JUNK" + zip_bytes([("gate-report.json", GOOD)])
    obs2 = observed_for(rep, zbytes=z)
    no_write(P.plan(cfg, obs2), "ARTIFACT_INVALID")


@pytest.mark.parametrize("bad", ["a--b", "x-->", "-", "a-", "--", "a" * 65, "", "a b", "x>y", "a\n"])
def test_p15_marker_rejects_comment_terminators_and_trailing_dash(bad):
    cfg, obs, _ = case()
    cfg["publisher"]["marker"] = bad
    no_write(P.plan(cfg, obs), "MALFORMED_INPUT")


def test_p15_marker_regex_accepts_the_real_marker_and_plan_records_foreign_count():
    assert P.MARKER_RE.fullmatch(MARKER)
    assert run()["foreign_marker_comments"] == 0

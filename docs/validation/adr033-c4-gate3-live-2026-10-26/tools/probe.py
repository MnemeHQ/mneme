#!/usr/bin/env python3
"""C4 Gate 3 live probe: one PR, its genuine required check, one head-pinned merge attempt.

Usage: python probe.py <L1..L5>
Builds the head commit with git plumbing on top of current lab main (so symlinks
are exact on Windows), pushes it, opens the PR, waits for the `CI1 trusted gate`
check run on that head, downloads the gate artifact, reads the annotations,
attempts a squash merge pinned to the head SHA, and records everything under
evidence/probes/<id>/. Exits 0 only when every observation matches the plan.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = "MnemeHQ/mneme-ci1-lab"
LAB = Path(r"C:\dev\mneme-ci1-lab")
EVID = Path(__file__).resolve().parents[1] / "evidence" / "probes"
CHECK = "CI1 trusted gate"
APP_ID = 15368
ADAPTER_SHA256 = "afe1d69c1ce4170875989c5866bb2ec7b5089fc895efa699ced826317e3777f9"

PROBES = {
    # id: (posture, kind, path, content, aggregate, check conclusion, merge HTTP status)
    "L1": ("closed", "file", "docs/c4-l1.md", "C4 Gate 3 L1: compliant documentation control.\n", "PASS", "success", 200),
    "L2": ("closed", "symlink", "docs/c4-l2-link.md", "../README.md", "UNEVALUATED", "failure", 405),
    "L3": ("open", "symlink", "docs/c4-l3-link.md", "../README.md", "UNEVALUATED", "success", 200),
    "L4": ("open", "file", "gate/c4-l4-note.txt", "C4 Gate 3 L4: trusted-surface change.\n", "REFUSED", "failure", 405),
    "L5": ("open", "file", "docs/c4-l5.md", "Run `install legacy-client` to get started.\n", "VIOLATION", "failure", 405),
}


def run(*cmd, cwd=None, data=None, check=True):
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    p = subprocess.run(cmd, cwd=cwd, input=data, capture_output=True, env=env)
    if check and p.returncode != 0:
        raise SystemExit(f"FAILED {cmd}\n{p.stdout.decode(errors='replace')}\n{p.stderr.decode(errors='replace')}")
    return p.stdout.decode(errors="replace").strip()


def git(*a, data=None):
    return run("git", "-C", str(LAB), *a, data=data)


def gh_json(path):
    return json.loads(run("gh", "api", path))


def main(pid):
    posture, kind, path, content, want_agg, want_concl, want_http = PROBES[pid]
    out = EVID / pid
    out.mkdir(parents=True, exist_ok=False)
    rec = {"probe": pid, "planned": {"posture": posture, "change": [kind, path], "aggregate": want_agg,
                                     "check_conclusion": want_concl, "merge_http": want_http}}
    var = gh_json(f"repos/{REPO}/actions/variables/MNEME_CI_AVAILABILITY")
    rec["posture_variable"] = {"value": var["value"], "updated_at": var["updated_at"]}
    if var["value"] != posture:
        raise SystemExit(f"posture variable is {var['value']!r}, probe needs {posture!r}")

    git("fetch", "-q", "origin")
    base = git("rev-parse", "origin/main")
    git("read-tree", base)
    blob = git("hash-object", "-w", "--stdin", data=content.encode())
    git("update-index", "--add", "--cacheinfo", f"{'120000' if kind == 'symlink' else '100644'},{blob},{path}")
    tree = git("write-tree")
    head = git("commit-tree", tree, "-p", base, "-m", f"test(c4): Gate 3 {pid} ({kind} {path})")
    git("read-tree", "HEAD")  # restore the index of the local checkout
    branch = f"c4/gate3-{pid.lower()}"
    git("push", "-q", "origin", f"{head}:refs/heads/{branch}")
    rec.update(base_main=base, head_sha=head, branch=branch)
    title = f"test(c4): Gate 3 {pid} {kind} {path} (expected {want_concl}, merge {want_http})"
    url = run("gh", "pr", "create", "-R", REPO, "--base", "main", "--head", branch, "--title", title,
              "--body", f"ADR-033 C4 Gate 3 probe {pid}. Posture `{posture}`. Expected aggregate {want_agg}, "
                        f"check {want_concl}, head-pinned merge HTTP {want_http}.")
    number = int(url.rsplit("/", 1)[1])
    rec.update(pr=number, pr_url=url)
    print(f"[{pid}] PR #{number} head {head[:8]}; waiting for the check run")

    deadline = time.time() + 1200
    cr = None
    while time.time() < deadline:
        runs = gh_json(f"repos/{REPO}/commits/{head}/check-runs?check_name={CHECK.replace(' ', '%20')}")["check_runs"]
        done = [r for r in runs if r["status"] == "completed"]
        if done:
            cr = done[0]
            break
        time.sleep(20)
    if cr is None:
        raise SystemExit(f"[{pid}] no completed check run within 20 minutes")
    time.sleep(10)
    runs = gh_json(f"repos/{REPO}/commits/{head}/check-runs?check_name={CHECK.replace(' ', '%20')}")["check_runs"]
    rec["check_runs"] = [{k: r.get(k) for k in ("id", "name", "head_sha", "status", "conclusion", "html_url",
                                                 "started_at", "completed_at")} | {"app_id": r["app"]["id"]}
                         for r in runs]
    (out / "check-runs.json").write_text(json.dumps(runs, indent=2) + "\n", encoding="utf-8")
    annotations = gh_json(f"repos/{REPO}/check-runs/{cr['id']}/annotations")
    (out / "annotations.json").write_text(json.dumps(annotations, indent=2) + "\n", encoding="utf-8")
    run_id = int(cr["details_url"].split("/runs/")[1].split("/")[0])
    rec["workflow_run_id"] = run_id
    wr = gh_json(f"repos/{REPO}/actions/runs/{run_id}")
    (out / "workflow-run.json").write_text(json.dumps(wr, indent=2) + "\n", encoding="utf-8")
    rec["workflow_run"] = {k: wr.get(k) for k in ("id", "event", "head_sha", "status", "conclusion", "path",
                                                   "run_attempt", "html_url")}
    log = run("gh", "run", "view", str(run_id), "-R", REPO, "--log", check=False)
    (out / "job.log").write_text(log + "\n", encoding="utf-8")
    run("gh", "run", "download", str(run_id), "-R", REPO, "-n", f"ci1-gate-pr{number}-{run_id}",
        "-D", str(out / "artifact"))
    report = json.loads((out / "artifact" / "gate-report.json").read_text(encoding="utf-8"))
    rec["report"] = {"aggregate": report["aggregate"], "disposition": report["disposition"],
                     "posture": report["posture"], "requested_mode": report["requested_mode"],
                     "base_sha": report["base_sha"], "head_sha": report["head_sha"],
                     "adapter": report["adapter"], "evaluator": report["evaluator"],
                     "memory": report["memory"], "files": [{k: f.get(k) for k in ("path", "status", "mode",
                                                                                  "classification", "kind", "reason")}
                                                           for f in report["files"]],
                     "annotations": report["annotations"]}

    merge = subprocess.run(["gh", "api", "-i", "-X", "PUT", f"repos/{REPO}/pulls/{number}/merge",
                            "-f", f"sha={head}", "-f", "merge_method=squash", "-f", f"commit_title={title} (#{number})"],
                           capture_output=True, text=True, encoding="utf-8")
    raw = merge.stdout + merge.stderr
    (out / "merge-response.txt").write_text(raw, encoding="utf-8")
    status_line = raw.splitlines()[0] if raw else ""
    req_id = next((l.split(":", 1)[1].strip() for l in raw.splitlines() if l.lower().startswith("x-github-request-id")), None)
    body = raw.strip().splitlines()[-1] if raw.strip() else ""
    rec["merge"] = {"status_line": status_line, "request_id": req_id, "body": body}
    http = int(status_line.split()[1]) if status_line.startswith("HTTP/") else None

    checks = {
        "check run on PR head": cr["head_sha"] == head,
        "genuine app": cr["app"]["id"] == APP_ID and cr["name"] == CHECK,
        "single check run": len(runs) == 1,
        "event pull_request_target": wr["event"] == "pull_request_target",
        "check conclusion": cr["conclusion"] == want_concl,
        "report head/base": report["head_sha"] == head and report["base_sha"] == base,
        "report adapter sha256": report["adapter"]["sha256"] == ADAPTER_SHA256,
        "report posture": report["posture"]["effective"] == posture and report["posture"]["fallback"] is None,
        "report mode strict": report["requested_mode"] == "strict",
        "report aggregate": report["aggregate"]["classification"] == want_agg,
        "merge http": http == want_http,
    }
    if want_agg == "UNEVALUATED" and posture == "open":
        checks["UNEVALUATED warning annotation"] = any(
            a.get("annotation_level") == "warning" and "UNEVALUATED" in (a.get("message") or "") for a in annotations)
        checks["UNEVALUATED in summary"] = "UNEVALUATED is not a PASS" in (out / "artifact" / "summary.md").read_text(encoding="utf-8")
    rec["checks"] = checks
    rec["outcome"] = "AS_PLANNED" if all(checks.values()) else "UNEXPECTED"
    (out / "probe.json").write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    print(f"[{pid}] check {cr['conclusion']} (run {run_id}); aggregate {report['aggregate']['classification']}; "
          f"merge {status_line} {body[:120]}")
    for k, v in checks.items():
        if not v:
            print(f"[{pid}]   MISMATCH: {k}")
    print(f"[{pid}] {rec['outcome']}")
    sys.exit(0 if rec["outcome"] == "AS_PLANNED" else 1)


if __name__ == "__main__":
    main(sys.argv[1])

#!/usr/bin/env python3
"""C4 Gate 3 offline dry run of the bootstrap workflow's own `run:` blocks.

Runs inside ubuntu:24.04 with /lab (CI1 lab clone, bootstrap branch checked out),
/src (Core checkout) and /in (preserved evaluator wheel + lab lock) mounted
read-only. The three adapter steps are taken verbatim from
.github/workflows/ci1-trusted-gate.yml; the GitHub-provided parts (checkout,
event, GITHUB_ENV/OUTPUT/STEP_SUMMARY) are simulated. The evaluator is the
preserved approved wheel instead of the workflow's rebuild (same sha256).
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

W = Path("/w")


def sh(cmd, cwd=None, env=None, check=True):
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise SystemExit(f"FAILED {cmd}\n{p.stdout}\n{p.stderr}")
    return p


def git(repo, *a, data=None):
    env = {**os.environ, "GIT_AUTHOR_NAME": "sim", "GIT_AUTHOR_EMAIL": "sim@example.invalid",
           "GIT_COMMITTER_NAME": "sim", "GIT_COMMITTER_EMAIL": "sim@example.invalid"}
    p = subprocess.run(["git", "-C", str(repo), *a], input=data, capture_output=True, env=env)
    if p.returncode != 0:
        raise SystemExit(f"git {a} failed: {p.stderr.decode()}")
    return p.stdout.decode().strip()


def make_head(repo, base, change):
    """Create a PR head commit on top of base with plumbing only."""
    git(repo, "read-tree", base)
    kind, path, content = change
    blob = git(repo, "hash-object", "-w", "--stdin", data=content.encode())
    mode = "120000" if kind == "symlink" else "100644"
    git(repo, "update-index", "--add", "--cacheinfo", f"{mode},{blob},{path}")
    return git(repo, "commit-tree", git(repo, "write-tree"), "-p", base, "-m", f"sim {path}")


def main():
    W.mkdir()
    ws = W / "ws"
    ws.mkdir()
    sh(["git", "config", "--global", "--add", "safe.directory", "*"])
    sh(["git", "clone", "-q", "/lab", str(ws / "base")])
    base_dir = ws / "base"
    sh(["git", "-C", str(base_dir), "checkout", "-q", os.environ["LAB_REF"]])
    base_sha = git(base_dir, "rev-parse", "HEAD")
    wf = yaml.safe_load((base_dir / ".github/workflows/ci1-trusted-gate.yml").read_text())
    steps = {s["name"]: s for s in wf["jobs"]["gate"]["steps"]}
    env_base = {k: str(v) for k, v in wf["env"].items() if "${{" not in str(v)}

    # Simulated "Check out the adapter at the reviewed commit".
    sh(["git", "clone", "-q", "--no-checkout", "/src", str(ws / "adapter-src")])
    sh(["git", "-C", str(ws / "adapter-src"), "checkout", "-q", "--detach", env_base["ADAPTER_COMMIT"]])
    # Simulated evaluator install: preserved approved wheel + lab lock (workflow rebuilds the same sha256).
    ev = W / "evaluator"
    sh(["/usr/bin/python3.12", "-I", "-m", "venv", str(ev)])
    req = W / "req.txt"
    req.write_text(Path("/in/evaluator-requirements.txt").read_text()
                   + f"/in/mneme_hq-0.10.0-py3-none-any.whl --hash=sha256:{env_base['APPROVED_WHEEL_SHA256']}\n")
    sh([str(ev / "bin/python"), "-I", "-m", "pip", "install", "-q", "--require-hashes", "--only-binary=:all:",
        "--no-deps", "-r", str(req)])

    cases = [
        ("L1", "closed", ("file", "docs/c4-l1.md", "C4 Gate 3 L1 compliant control.\n"), 0),
        ("L2", "closed", ("symlink", "docs/c4-l2-link.md", "../README.md"), 1),
        ("L3", "open", ("symlink", "docs/c4-l3-link.md", "../README.md"), 0),
        ("L4", "open", ("file", "gate/c4-l4-note.txt", "C4 Gate 3 L4 trusted-surface change.\n"), 1),
        ("L5", "open", ("file", "docs/c4-l5.md", "Run `install legacy-client` to get started.\n"), 1),
        ("unset", "", ("symlink", "docs/c4-unset-link.md", "../README.md"), 1),
        ("invalid", "Open", ("symlink", "docs/c4-invalid-link.md", "../README.md"), 1),
    ]
    results = []
    for cid, posture, change, want in cases:
        head = make_head(base_dir, base_sha, change)
        rt = W / f"rt-{cid}"
        rt.mkdir()
        files = {n: rt / n for n in ("env", "output", "summary")}
        for f in files.values():
            f.touch()
        env = {**os.environ, **env_base, "MNEME_CI_AVAILABILITY": posture, "RUNNER_TEMP": str(rt),
               "GITHUB_WORKSPACE": str(ws), "GITHUB_ENV": str(files["env"]), "GITHUB_OUTPUT": str(files["output"]),
               "GITHUB_STEP_SUMMARY": str(files["summary"]), "BASE_SHA": base_sha, "HEAD_SHA": head,
               "EVALUATOR_PYTHON": str(ev / "bin/python"), "PR_NUMBER": "0"}
        rec = {"case": cid, "posture": posture, "head": head}
        for name in ("Verify the adapter pins before running it", "Evaluate the PR in the trusted workspace",
                     "Gate decision"):
            step = steps[name]
            step_env = {**env, **{k: str(v) for k, v in (step.get("env") or {}).items()}}
            if "GATE_EXIT" in step_env:
                out = dict(l.split("=", 1) for l in files["output"].read_text().split() if "=" in l)
                step_env["GATE_EXIT"] = out.get("exit", "")
            p = subprocess.run(["bash", "-eo", "pipefail", "-c", step["run"]], cwd=ws, env=step_env,
                               capture_output=True, text=True)
            rec[name] = {"exit": p.returncode, "stdout": p.stdout[-3000:], "stderr": p.stderr[-2000:]}
            for line in files["env"].read_text().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    env[k] = v
            if p.returncode != 0 and name != "Gate decision":
                break
        report = json.loads((rt / "gate-out/gate-report.json").read_text()) if (rt / "gate-out/gate-report.json").exists() else {}
        rec["aggregate"] = report.get("aggregate", {}).get("classification")
        rec["disposition"] = report.get("disposition")
        rec["decision_exit"] = rec.get("Gate decision", {}).get("exit")
        rec["ok"] = rec["decision_exit"] == want
        results.append(rec)
        print(f"{cid:8} posture={posture or '(unset)':7} aggregate={rec['aggregate']} disposition={rec['disposition']} "
              f"decision_exit={rec['decision_exit']} expected={want} {'OK' if rec['ok'] else 'UNEXPECTED'}")
    Path("/out/sim-results.json").write_text(json.dumps(results, indent=2) + "\n")
    sys.exit(0 if all(r["ok"] for r in results) else 1)


if __name__ == "__main__":
    main()

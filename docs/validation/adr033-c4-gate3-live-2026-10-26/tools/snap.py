#!/usr/bin/env python3
"""C4 Gate 3: read-only snapshot of the CI1 lab's administrative state.

Usage: python snap.py <tag>   -> writes <evidence>/snapshots/<tag>-*.json and prints a digest line.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = "MnemeHQ/mneme-ci1-lab"
API_VERSION = "2026-03-10"
SNAP = Path(__file__).resolve().parents[1] / "evidence" / "snapshots"


def gh(*a: str) -> str:
    p = subprocess.run(["gh", "api", "-H", f"X-GitHub-Api-Version: {API_VERSION}", *a],
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise SystemExit(f"FAILED gh api {' '.join(a)}\n{p.stdout}\n{p.stderr}")
    return p.stdout


def main(tag: str) -> None:
    SNAP.mkdir(parents=True, exist_ok=True)
    parts = {
        "repo": gh(f"repos/{REPO}"),
        "ruleset": gh(f"repos/{REPO}/rulesets/25313704"),
        "policy": gh(f"repos/{REPO}/actions/policies/7806"),
        "variables": gh(f"repos/{REPO}/actions/variables"),
        "actions-permissions": gh(f"repos/{REPO}/actions/permissions"),
        "main": gh(f"repos/{REPO}/git/ref/heads/main"),
    }
    digest = {}
    for name, body in parts.items():
        (SNAP / f"{tag}-{name}.json").write_text(body, encoding="utf-8", newline="\n")
        digest[f"{name}_sha256"] = hashlib.sha256(body.encode()).hexdigest()[:16]
    repo, rs, pol, var = (json.loads(parts[k]) for k in ("repo", "ruleset", "policy", "variables"))
    summary = {
        "tag": tag, "archived": repo["archived"], "main": json.loads(parts["main"])["object"]["sha"],
        "ruleset_enforcement": rs["enforcement"], "ruleset_updated_at": rs["updated_at"],
        "bypass_actors": rs.get("bypass_actors"),
        "required_checks": [c for r in rs["rules"] if r["type"] == "required_status_checks"
                            for c in r["parameters"]["required_status_checks"]],
        "policy_enforcement": pol.get("enforcement"), "policy_updated_at": pol.get("updated_at"),
        "variables": {v["name"]: v["value"] for v in var.get("variables", [])}, **digest,
    }
    (SNAP / f"{tag}-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main(sys.argv[1])

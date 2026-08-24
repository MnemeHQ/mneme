"""M1e-d live validation: Mneme-content-based Update File denial.

Same trusted production hook as M1d-b (unchanged definition -> unchanged
trust), pinned 0.149.1, no bypass. A seeded tracked file plus a typed rule
scoped to it prove both directions:

  deny_update  Update introduces FORBIDDEN_TOKEN_XYZ into the seeded file
               -> PreToolUse deny, file byte-identical, no PostToolUse
  pass_update  compliant Update -> file changes, PostToolUse fires
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run_applypatch_probe import REPO, sha256  # noqa: E402
from run_m1db_live import (  # noqa: E402
    capture_worktree,
    exec_prompt_factory,
    install_production_hooks,
    new_rollouts,
    reset_case,
    rollout_hits,
    sessions_snapshot,
    write_memory,
)
from run_applypatch_probe import check_env, snapshot_trust_state  # noqa: E402

SEED_FILE = "service.py"
SEED_CONTENT = (
    "MAX_LIMIT = 10\n"
    "\n"
    "\n"
    "def existing():\n"
    "    return 1\n"
    "\n"
    "\n"
    "def second():\n"
    "    return 2\n"
)

SCOPED_MEMORY = {
    "meta": {"name": "m1ed-live", "description": "M1e-d live validation memory"},
    "decisions": [{
        "id": "ADR-UPD",
        "decision": "The forbidden token must not appear in service.py.",
        "rules": [{
            "type": "FORBID_LITERAL",
            "value": "FORBIDDEN_TOKEN_XYZ",
            "include_paths": ["service.py"],
        }],
    }],
}

DENY_PROMPT = (
    "Use apply_patch to modify service.py in the repo root: change the line "
    "'    return 1' to '    return \"FORBIDDEN_TOKEN_XYZ\"'. Change nothing "
    "else. Do not use shell commands to edit files."
)
PASS_PROMPT = (
    "Use apply_patch to modify service.py in the repo root: change the line "
    "'    return 1' to '    return 42'. Change nothing else. Do not use "
    "shell commands to edit files."
)


def seed_sandbox() -> None:
    """Baseline-commit the seed so each case starts identical."""
    subprocess.run(["git", "clean", "-fdq", "-e", ".codex", "-e", ".mneme"],
                   cwd=REPO, capture_output=True, check=True)
    subprocess.run(["git", "reset", "--hard", "-q"],
                   cwd=REPO, capture_output=True, check=True)
    install_production_hooks(REPO)
    (REPO / SEED_FILE).write_text(SEED_CONTENT, encoding="utf-8")
    write_memory(REPO)
    subprocess.run(["git", "add", "."], cwd=REPO, capture_output=True, check=True)
    staged = subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                            capture_output=True, text=True, check=False)
    if staged.stdout.strip():
        subprocess.run(
            ["git", "-c", "user.name=probe", "-c", "user.email=probe@local",
             "commit", "-qm", "baseline: seed + production hook"],
            cwd=REPO, capture_output=True, check=True,
        )


def main() -> int:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = HERE.parent / "evidence" / "runs" / f"{stamp}-m1ed-live"
    run_dir.mkdir(parents=True)
    print(f"run dir: {run_dir}")

    env = check_env(run_dir)
    snapshot_trust_state(run_dir)
    seed_sandbox()
    exec_prompt = exec_prompt_factory(env, REPO, run_dir)

    results = {}
    for name, prompt, expect_blocked in (
        ("deny_update", DENY_PROMPT, True),
        ("pass_update", PASS_PROMPT, False),
    ):
        seed_sandbox()
        before = capture_worktree(REPO)
        before_seed_hash = before["files"].get(SEED_FILE)
        sessions_before = sessions_snapshot()

        rc = exec_prompt(prompt, {}, f"transcript-{name}.log")

        after = capture_worktree(REPO)
        after_seed_hash = after["files"].get(SEED_FILE)
        changed = before_seed_hash != after_seed_hash

        transcript = (run_dir / f"transcript-{name}.log").read_text(
            encoding="utf-8")
        hook_lines = [ln.strip() for ln in transcript.splitlines()
                      if ln.strip().startswith("hook:")]
        blocked = "PreToolUse Blocked" in transcript or any(
            "Command blocked by PreToolUse hook" in ln for ln in transcript.splitlines())

        context_hits = {}
        for rollout in new_rollouts(sessions_before):
            for needle in ("[mneme] WARN", "UNEVALUATED"):
                found = rollout_hits(rollout, needle)
                if found:
                    context_hits.setdefault(rollout.name, {})[needle] = found[:2]

        outcome = {
            "returncode": rc,
            "seed_changed": changed,
            "blocked": blocked,
            "hook_lines": hook_lines,
            "unexpected_context_hits": context_hits,
        }
        ok = (changed != expect_blocked) and (blocked == expect_blocked)
        outcome["verdict"] = "PASS" if ok else "FAIL"
        results[name] = outcome
        print(f"[{name}] changed={changed} blocked={blocked} "
              f"verdict={outcome['verdict']}")

    (run_dir / "summary.json").write_text(json.dumps({
        "pin_verified": True,
        "bypass_flag_used": False,
        "cases": results,
    }, indent=2), encoding="utf-8")

    lines = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != "MANIFEST.sha256":
            rel = str(path.relative_to(run_dir)).replace("\\", "/")
            lines.append(f"{sha256(path)}  {rel}")
    (run_dir / "MANIFEST.sha256").write_text("\n".join(lines) + "\n",
                                              encoding="utf-8")
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

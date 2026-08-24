"""M1f-c live validation: multi-operation apply_patch enforcement.

Three bundled calls (Update service.py + Add helper.py in ONE invocation):

  case1  compliant Update + compliant Add      -> both land
  case2  violating Update + compliant Add      -> neither lands
  case3  compliant Update + violating Add      -> neither lands

Proves there is no "only first operation checked" / "only one operation
blocked" hole on pinned Codex CLI 0.149.1.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run_applypatch_probe import REPO, check_env, sha256, snapshot_trust_state  # noqa: E402
from run_m1db_live import (  # noqa: E402
    capture_worktree,
    exec_prompt_factory,
    install_production_hooks,
    sessions_snapshot,
)
from run_m1ed_live import SEED_CONTENT, SEED_FILE  # noqa: E402

SCOPED_MEMORY = {
    "meta": {"name": "m1fc-live", "description": "M1f-c live validation"},
    "decisions": [{
        "id": "ADR-BUNDLE",
        "decision": "The forbidden token must not appear in any new or "
                    "modified artifact.",
        "rules": [{"type": "FORBID_LITERAL", "value": "FORBIDDEN_TOKEN_XYZ"}],
    }],
}

GOOD_UPDATE = ["*** Update File: service.py", "@@", " def existing():",
               "-    return 1", "+    return 42"]
BAD_UPDATE = ["*** Update File: service.py", "@@", " def existing():",
              "-    return 1", '+    return "FORBIDDEN_TOKEN_XYZ"']
GOOD_ADD = ["*** Add File: helper.py", "+def assist():", "+    return 7"]
BAD_ADD = ["*** Add File: helper.py", '+x = "FORBIDDEN_TOKEN_XYZ"']


def prompt_for(body_lines):
    patch = "\n".join(["*** Begin Patch", *body_lines, "*** End Patch"])
    return (
        "Make BOTH of these changes in a SINGLE apply_patch invocation "
        "(one Begin Patch / End Patch block containing both operations):\n"
        f"{patch}\n\n"
        "Apply exactly this patch with no modifications. Do not use shell "
        "commands to edit files."
    )


CASES = [
    ("case1_compliant_both",
     prompt_for([*GOOD_UPDATE, *GOOD_ADD]),
     {"seed_changed": True, "helper_added": True, "blocked": False}),
    ("case2_bad_update",
     prompt_for([*BAD_UPDATE, *GOOD_ADD]),
     {"seed_changed": False, "helper_added": False, "blocked": True}),
    ("case3_bad_add",
     prompt_for([*GOOD_UPDATE, *BAD_ADD]),
     {"seed_changed": False, "helper_added": False, "blocked": True}),
]


def seed_sandbox() -> None:
    subprocess.run(["git", "clean", "-fdq", "-e", ".codex", "-e", ".mneme"],
                   cwd=REPO, capture_output=True, check=True)
    subprocess.run(["git", "reset", "--hard", "-q"],
                   cwd=REPO, capture_output=True, check=True)
    install_production_hooks(REPO)
    (REPO / SEED_FILE).write_text(SEED_CONTENT, encoding="utf-8")
    (REPO / ".mneme").mkdir(exist_ok=True)
    (REPO / ".mneme" / "project_memory.json").write_text(
        json.dumps(SCOPED_MEMORY, indent=2), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=REPO, capture_output=True, check=True)
    staged = subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                            capture_output=True, text=True, check=False)
    if staged.stdout.strip():
        subprocess.run(
            ["git", "-c", "user.name=probe", "-c", "user.email=probe@local",
             "commit", "-qm", "baseline: seed + scoped rule + production hook"],
            cwd=REPO, capture_output=True, check=True)


def main() -> int:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = HERE.parent / "evidence" / "runs" / f"{stamp}-m1fc-live"
    run_dir.mkdir(parents=True)
    print(f"run dir: {run_dir}")

    env = check_env(run_dir)
    snapshot_trust_state(run_dir)
    exec_prompt = exec_prompt_factory(env, REPO, run_dir)

    results = {}
    for name, prompt, expect in CASES:
        seed_sandbox()
        before = capture_worktree(REPO)
        sessions_before = sessions_snapshot()

        rc = exec_prompt(prompt, {}, f"transcript-{name}.log")

        after = capture_worktree(REPO)
        transcript = (run_dir / f"transcript-{name}.log").read_text(
            encoding="utf-8")
        outcome = {
            "returncode": rc,
            "seed_changed": before["files"].get(SEED_FILE)
                            != after["files"].get(SEED_FILE),
            "helper_added": "helper.py" in after["files"],
            "blocked": "PreToolUse Blocked" in transcript,
            "hook_lines": [ln.strip() for ln in transcript.splitlines()
                           if ln.strip().startswith("hook:")],
            "expected": expect,
        }
        ok = all([
            outcome["seed_changed"] == expect["seed_changed"],
            outcome["helper_added"] == expect["helper_added"],
            outcome["blocked"] == expect["blocked"],
        ])
        outcome["verdict"] = "PASS" if ok else "FAIL"
        results[name] = outcome
        print(f"[{name}] changed={outcome['seed_changed']} "
              f"added={outcome['helper_added']} blocked={outcome['blocked']} "
              f"verdict={outcome['verdict']}")

    (run_dir / "summary.json").write_text(json.dumps({
        "pin_verified": True, "bypass_flag_used": False, "cases": results,
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

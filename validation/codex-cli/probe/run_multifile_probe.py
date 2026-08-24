"""M1f-a capability probe: multi-operation apply_patch on 0.149.1.

One native apply_patch containing BOTH an Update File and an Add File,
captured via the trusted logger hook (allow / deny arms), to freeze the
multi-operation grammar before any parser support:

  - exact PreToolUse payload; operations in one tool_input.command?
  - operation ordering; relative vs absolute path forms
  - deny rejects the ENTIRE tool call (neither mutation lands)
  - allow lands both mutations; PostToolUse present vs absent

The seeded tracked file has known bytes so per-operation reconstruction can
be checked independently.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATION_DIR = HERE.parent
TEMPLATE = HERE / "hooks.template.json"

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

PROMPT = (
    "Make BOTH of these changes in a SINGLE apply_patch invocation "
    "(one Begin Patch / End Patch block containing two operations):\n"
    f"1. Modify {SEED_FILE} in the repo root so existing() returns 42.\n"
    "2. Add a new file named helper.py in the repo root containing exactly "
    "one function:\n\ndef assist():\n    return 7\n\n"
    "Do not use shell commands to edit files. Do not modify anything else."
)

ARMS = [
    ("allow", "log"),
    ("deny", "deny_apply_patch"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


import hashlib  # noqa: E402


def install_hooks(sandbox: Path) -> None:
    python = sys.executable.replace("\\", "\\\\")
    hook = str(HERE / "log_hook.py").replace("\\", "\\\\")
    rendered = TEMPLATE.read_text(encoding="utf-8")
    rendered = rendered.replace("__PYTHON__", python).replace("__HOOK__", hook)
    codex_dir = sandbox / ".codex"
    codex_dir.mkdir(exist_ok=True)
    (codex_dir / "hooks.json").write_text(rendered, encoding="utf-8")


def reset_sandbox(sandbox: Path) -> None:
    if not (sandbox / ".git").exists():
        sandbox.mkdir(parents=True)
        subprocess.run(["git", "init"], cwd=sandbox, capture_output=True, check=True)
    subprocess.run(["git", "clean", "-fdq", "-e", ".codex"],
                   cwd=sandbox, capture_output=True, check=True)
    subprocess.run(["git", "reset", "--hard", "-q"],
                   cwd=sandbox, capture_output=True, check=True)
    install_hooks(sandbox)
    (sandbox / SEED_FILE).write_text(SEED_CONTENT, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=sandbox, capture_output=True, check=True)
    staged = subprocess.run(["git", "status", "--porcelain"], cwd=sandbox,
                            capture_output=True, text=True, check=False)
    if staged.stdout.strip():
        subprocess.run(
            ["git", "-c", "user.name=probe", "-c", "user.email=probe@local",
             "commit", "-qm", "baseline: seed + logger hooks"],
            cwd=sandbox, capture_output=True, check=True)


def capture_worktree(sandbox: Path) -> dict:
    status = subprocess.run(["git", "status", "--porcelain=v2"],
                            cwd=sandbox, capture_output=True, text=True, check=False)
    files = {}
    skip = sandbox.resolve() / ".git"
    for path in sorted(sandbox.rglob("*")):
        if skip in path.resolve().parents or not path.is_file():
            continue
        rel = str(path.relative_to(sandbox)).replace("\\", "/")
        files[rel] = sha256(path)
    return {"git_status": status.stdout, "files": files}


def main() -> int:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = VALIDATION_DIR / "evidence" / "runs" / f"{stamp}-multifile"
    run_dir.mkdir(parents=True)
    print(f"run dir: {run_dir}")

    codex_bin = os.environ.get("CODEX_BIN", "codex")
    version = subprocess.run([codex_bin, "--version"], capture_output=True,
                             text=True, check=False).stdout.strip()
    env = {"codex_bin": codex_bin, "codex_version": version,
           "codex_args_extra": os.environ.get("CODEX_ARGS", "")}
    (run_dir / "env.json").write_text(json.dumps(env, indent=2), encoding="utf-8")
    print(f"codex: {version}")
    (run_dir / "seed-service.py").write_text(SEED_CONTENT, encoding="utf-8")

    outcomes = []
    for arm, mode in ARMS:
        arm_dir = run_dir / arm
        sandbox = HERE / "sandbox" / "repo"
        reset_sandbox(sandbox)
        before = capture_worktree(sandbox)
        arm_dir.mkdir(parents=True)
        (arm_dir / "worktree-before.json").write_text(
            json.dumps(before, indent=2), encoding="utf-8")

        os.environ["MNEME_PROBE_MODE"] = mode
        events_dir = run_dir / f"events-{arm}"
        cmd = [env["codex_bin"], "exec"]
        if env["codex_args_extra"]:
            cmd.extend(env["codex_args_extra"].split())
        cmd.append(PROMPT)
        proc = subprocess.run(
            cmd, cwd=sandbox, capture_output=True, text=True, check=False,
            env={**os.environ, "MNEME_PROBE_EVIDENCE_DIR": str(events_dir)},
        )
        (run_dir / f"transcript-{arm}.log").write_text(
            f"$ {' '.join(cmd)}\n\n--- stdout ---\n{proc.stdout}\n"
            f"\n--- stderr ---\n{proc.stderr}\n\nexit={proc.returncode}\n",
            encoding="utf-8")

        after = capture_worktree(sandbox)
        (arm_dir / "worktree-after.json").write_text(
            json.dumps(after, indent=2), encoding="utf-8")
        outcome = {
            "arm": arm,
            "seed_changed": before["files"].get(SEED_FILE) != after["files"].get(SEED_FILE),
            "helper_added": "helper.py" in after["files"],
            "worktree_status": after["git_status"].strip(),
        }
        outcomes.append(outcome)
        print(f"[{arm}] seed_changed={outcome['seed_changed']} "
              f"helper_added={outcome['helper_added']}")

    (run_dir / "summary.json").write_text(json.dumps({
        "probe": "multifile",
        "arms": outcomes,
        "fact_deny_rejects_entire_call": (
            not outcomes[1]["seed_changed"] and not outcomes[1]["helper_added"]),
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

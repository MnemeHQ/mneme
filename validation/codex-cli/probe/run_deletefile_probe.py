"""M1g-a capability probe: native apply_patch **Delete File** on 0.149.1.

Same discipline as the update/multifile probes: trusted logger hook, allow
and deny arms, seeded tracked file with known bytes. Records:

- exact PreToolUse payload / tool_input.command grammar for Delete
- whether any content accompanies the operation (or header-only)
- deny leaves the file byte-identical
- PostToolUse absent on deny; Stop fires in both arms
- allow removes the file

No parser changes; grammar freeze only.
"""

from __future__ import annotations

import hashlib
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
)

PROMPT = (
    f"Use apply_patch to delete {SEED_FILE} from the repo root entirely. "
    "Do not use shell commands. Do not modify or create any other file."
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
                            cwd=sandbox, capture_output=True, text=True,
                            check=False)
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
    run_dir = VALIDATION_DIR / "evidence" / "runs" / f"{stamp}-deletefile"
    run_dir.mkdir(parents=True)
    print(f"run dir: {run_dir}")

    codex_bin = os.environ.get("CODEX_BIN", "codex")
    version = subprocess.run([codex_bin, "--version"], capture_output=True,
                             text=True, check=False).stdout.strip()
    env = {"codex_bin": codex_bin, "codex_version": version}
    (run_dir / "env.json").write_text(json.dumps(env, indent=2), encoding="utf-8")
    print(f"codex: {version}")
    (run_dir / "seed-service.py").write_text(SEED_CONTENT, encoding="utf-8")

    sandbox = HERE / "sandbox" / "repo"
    outcomes = []
    for arm, mode in (("allow", "log"), ("deny", "deny_apply_patch")):
        arm_dir = run_dir / arm
        reset_sandbox(sandbox)
        before = capture_worktree(sandbox)
        arm_dir.mkdir(parents=True)
        (arm_dir / "worktree-before.json").write_text(
            json.dumps(before, indent=2), encoding="utf-8")

        os.environ["MNEME_PROBE_MODE"] = mode
        events_dir = run_dir / f"events-{arm}"
        cmd = [codex_bin, "exec", PROMPT]
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
            "seed_deleted": SEED_FILE in before["files"]
                            and SEED_FILE not in after["files"],
            "worktree_status": after["git_status"].strip(),
        }
        outcomes.append(outcome)
        print(f"[{arm}] seed_deleted={outcome['seed_deleted']}")

    (run_dir / "summary.json").write_text(json.dumps({
        "probe": "deletefile",
        "arms": outcomes,
        "fact_deny_keeps_file": not outcomes[1]["seed_deleted"],
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

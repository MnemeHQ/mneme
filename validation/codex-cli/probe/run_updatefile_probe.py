"""M1e-a capability probe: native apply_patch **Update File** on 0.149.1.

Same evidence discipline as the R0 applypatch probe, but the agent task
modifies an existing tracked file, exercising Codex's Update File grammar:
context/unchanged lines, added lines, replaced lines.

Arms (both trusted, no bypass):
  allow - log mode; capture the raw PreToolUse payload and the resulting file
  deny  - deny_apply_patch mode; the existing file must stay byte-identical,
          PostToolUse must be absent

The seeded file has known bytes so deterministic reconstruction from
(payload + one current-file snapshot) can be checked against reality.
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
    "\n"
    "\n"
    "def second():\n"
    "    return 2\n"
)

PROMPT = (
    f"Use apply_patch to modify {SEED_FILE} in the repo root: change the "
    "existing() function so it returns 42 instead of 1, and add a new "
    "function third() that returns 3 at the end of the file. Change nothing "
    "else. Do not use shell commands to edit files."
)

ARMS = [
    ("allow", "log"),
    ("deny", "deny_apply_patch"),
]


def fail(msg):
    sys.stderr.write(f"probe: {msg}\n")
    sys.exit(1)


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
    # Restore tracked state, drop prior-arm artifacts.
    subprocess.run(["git", "clean", "-fdq", "-e", ".codex"],
                   cwd=sandbox, capture_output=True, check=True)
    subprocess.run(["git", "reset", "--hard", "-q"],
                   cwd=sandbox, capture_output=True, check=True)
    # Ensure hooks + seed exist and are committed so every arm starts from an
    # identical, known baseline.
    install_hooks(sandbox)
    (sandbox / SEED_FILE).write_text(SEED_CONTENT, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=sandbox, capture_output=True, check=True)
    staged = subprocess.run(["git", "status", "--porcelain"],
                            cwd=sandbox, capture_output=True, text=True, check=False)
    if staged.stdout.strip():
        subprocess.run(
            ["git", "-c", "user.name=probe", "-c", "user.email=probe@local",
             "commit", "-qm", "baseline: seed + logger hooks"],
            cwd=sandbox, capture_output=True, check=True,
        )


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


def run_arm(arm: str, sandbox: Path, run_dir: Path, env: dict) -> None:
    events_dir = run_dir / f"events-{arm}"
    cmd = [env["codex_bin"], "exec"]
    extra = env.get("codex_args_extra", "")
    if extra:
        cmd.extend(extra.split())
    cmd.append(PROMPT)
    proc = subprocess.run(
        cmd, cwd=sandbox, capture_output=True, text=True, check=False,
        env={**os.environ, "MNEME_PROBE_EVIDENCE_DIR": str(events_dir)},
    )
    (run_dir / f"transcript-{arm}.log").write_text(
        f"$ {' '.join(cmd)}\n\n--- stdout ---\n{proc.stdout}\n"
        f"\n--- stderr ---\n{proc.stderr}\n\nexit={proc.returncode}\n",
        encoding="utf-8",
    )


def write_manifest(run_dir: Path) -> None:
    lines = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != "MANIFEST.sha256":
            rel = str(path.relative_to(run_dir)).replace("\\", "/")
            lines.append(f"{sha256(path)}  {rel}")
    (run_dir / "MANIFEST.sha256").write_text("\n".join(lines) + "\n",
                                              encoding="utf-8")


def main() -> int:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = VALIDATION_DIR / "evidence" / "runs" / f"{stamp}-updatefile"
    run_dir.mkdir(parents=True)
    print(f"run dir: {run_dir}")

    env = None
    try:
        env = {
            "codex_bin": os.environ.get("CODEX_BIN", "codex"),
            "codex_args_extra": os.environ.get("CODEX_ARGS", ""),
        }
        resolved = subprocess.run([env["codex_bin"], "--version"],
                                  capture_output=True, text=True, check=False)
        env["codex_version"] = resolved.stdout.strip()
    except OSError as e:
        fail(f"codex not runnable: {e}")
    (run_dir / "env.json").write_text(json.dumps(env, indent=2), encoding="utf-8")
    print(f"codex: {env['codex_version']}")

    # Seed snapshot goes into the evidence so reconstruction checks are
    # possible without touching the live sandbox later.
    (run_dir / "seed-service.py").write_text(SEED_CONTENT, encoding="utf-8")

    outcomes = []
    for arm, mode in ARMS:
        arm_dir = run_dir / arm
        reset_sandbox(REPO := HERE / "sandbox" / "repo")
        before = capture_worktree(REPO)
        (arm_dir / "worktree-before.json").parent.mkdir(parents=True)
        (arm_dir / "worktree-before.json").write_text(
            json.dumps(before, indent=2), encoding="utf-8")

        os.environ["MNEME_PROBE_MODE"] = mode
        run_arm(arm, REPO, run_dir, env)

        after = capture_worktree(REPO)
        (arm_dir / "worktree-after.json").write_text(
            json.dumps(after, indent=2), encoding="utf-8")

        seed_hash_before = before["files"].get(SEED_FILE)
        seed_hash_after = after["files"].get(SEED_FILE)
        outcome = {
            "arm": arm,
            "returncode": None,
            "seed_changed": seed_hash_before != seed_hash_after,
            "worktree_status": after["git_status"].strip(),
        }
        outcomes.append(outcome)
        print(f"[{arm}] seed_changed={outcome['seed_changed']}")

    (run_dir / "summary.json").write_text(
        json.dumps({
            "probe": "updatefile",
            "arms": outcomes,
            "fact_deny_byte_identical": not outcomes[1]["seed_changed"],
            "next": (
                "manual analysis: exact PreToolUse payload, Update File "
                "grammar, deterministic reconstruction vs post-allow bytes"
            ),
        }, indent=2),
        encoding="utf-8",
    )
    write_manifest(run_dir)
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

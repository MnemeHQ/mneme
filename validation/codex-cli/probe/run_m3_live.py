"""M3 live validation: Stop changed-tree audit on pinned Codex 0.149.1.

Cases (each one codex exec run; the session baseline is captured by the
production hook itself on the first mutating-capable PreToolUse):

  c1_forbidden_shell   shell writes forbidden content -> Stop blocks with a
                       named file/rule; remediation within the same exec run
                       must pass without an infinite loop.
  c2_compliant_shell   shell writes compliant content -> completes cleanly,
                       no block, no spurious disclosure.
  c3_dirty_untouched   file dirty BEFORE the session, untouched -> not blamed.
  c4_dirty_touched     file dirty before AND modified by Codex -> audited.

c3/c4 seed a dirty file in the sandbox before codex runs; c4's prompt asks
codex to append to it via shell.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run_applypatch_probe import REPO, check_env, sha256, snapshot_trust_state  # noqa: E402
from run_m1db_live import install_production_hooks  # noqa: E402

FORBIDDEN = "FORBIDDEN_TOKEN_XYZ"

MEMORY = {
    "meta": {"name": "m3-live", "description": "M3 live validation"},
    "decisions": [{
        "id": "ADR-STOP",
        "decision": f"The token {FORBIDDEN} must not appear in artifacts.",
        "rules": [{"type": "FORBID_LITERAL", "value": FORBIDDEN}],
    }],
}

DIRTY_FILE = "preexisting.py"
DIRTY_CONTENT = f'# pre-existing dirty file\nkeep = "{FORBIDDEN}"\n'


def seed(case: str) -> None:
    subprocess.run(["git", "clean", "-fdq", "-e", ".codex", "-e", ".mneme"],
                   cwd=REPO, capture_output=True, check=True)
    subprocess.run(["git", "reset", "--hard", "-q"],
                   cwd=REPO, capture_output=True, check=True)
    install_production_hooks(REPO)
    # Dirty-before-session state: modified worktree file, uncommitted, and
    # NOT committed into the baseline the hook will capture.
    if case in ("c3_dirty_untouched", "c4_dirty_touched"):
        (REPO / DIRTY_FILE).write_text(DIRTY_CONTENT, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=REPO, capture_output=True, check=True)
    staged = subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                            capture_output=True, text=True, check=False)
    if staged.stdout.strip():
        subprocess.run(
            ["git", "-c", "user.name=probe", "-c", "user.email=probe@local",
             "commit", "-qm", f"baseline {case}"],
            cwd=REPO, capture_output=True, check=True)


def main() -> int:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = HERE.parent / "evidence" / "runs" / f"{stamp}-m3-live"
    run_dir.mkdir(parents=True)
    print(f"run dir: {run_dir}")

    env = check_env(run_dir)
    snapshot_trust_state(run_dir)

    def capture():
        files = {}
        skip = (REPO / ".git").resolve()
        status = subprocess.run(["git", "status", "--porcelain=v2"], cwd=REPO,
                                capture_output=True, text=True, check=False).stdout
        for path in sorted(REPO.rglob("*")):
            if skip in path.resolve().parents or not path.is_file():
                continue
            rel = str(path.relative_to(REPO)).replace("\\", "/")
            files[rel] = sha256(path)
        return {"git_status": status, "files": files}

    cases = [
        ("c1_forbidden_shell",
         f'Using a shell command (do NOT use apply_patch), create a file '
         f'named shell_made.txt containing exactly {FORBIDDEN}.'),
        ("c2_compliant_shell",
         'Using a shell command (do NOT use apply_patch), create a file '
         'named shell_clean.txt containing exactly CLEAN_AND_FINE.'),
        ("c3_dirty_untouched",
         'Report how many Python files exist in the repo root. Do not modify '
         'or delete anything.'),
        ("c4_dirty_touched",
         f'Using a shell command, append the line "# codex was here" to the '
         f'END of {DIRTY_FILE}. Change nothing else.'),
    ]

    results = {}
    for name, prompt, in cases:
        seed(name)
        before = capture()
        transcript = run_dir / f"transcript-{name}.log"
        cmd = [env["codex_bin"], "exec"]
        if env.get("codex_args_extra"):
            cmd.extend(env["codex_args_extra"].split())
        cmd.append(prompt)
        proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                              check=False,
                              env={**os.environ})
        transcript.write_text(
            f"$ {' '.join(cmd)}\n\n--- stdout ---\n{proc.stdout}\n"
            f"\n--- stderr ---\n{proc.stderr}\n\nexit={proc.returncode}\n",
            encoding="utf-8")
        after = capture()

        stop_blocks = proc.stdout.count("mneme: files changed during this "
                                        "session violate")
        outcome = {
            "returncode": proc.returncode,
            "stop_blocks": stop_blocks,
            "worktree_after": after["git_status"].strip(),
            "dirty_file_changed": (
                before["files"].get(DIRTY_FILE) != after["files"].get(DIRTY_FILE)),
        }
        results[name] = outcome
        print(f"[{name}] blocks={stop_blocks} rc={proc.returncode} "
              f"dirty_changed={outcome['dirty_file_changed']}")

    (run_dir / "summary.json").write_text(json.dumps(results, indent=2),
                                          encoding="utf-8")
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

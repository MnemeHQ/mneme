"""R0 native apply_patch probe runner.

Trust-first experimental design:

- PRIMARY evidence comes from trusted hooks under normal security semantics
  (no --dangerously-bypass-hook-trust).
- The bypass flag is used ONLY as a diagnostic secondary arm when the trusted
  primary arms observe no hooks at all (possible trust-dispatch defect,
  cf. upstream issue #32491 on 0.144.1).

The sandbox path is deterministic (validation/codex-cli/probe/sandbox/repo) so
that the rendered hook commands -- and therefore their trust hashes -- are
identical across runs. One interactive /hooks trust grant covers all runs.

Usage:
    python run_applypatch_probe.py [--with-bypass-diagnostic]

Env overrides:
    CODEX_BIN        codex executable (default "codex")
    CODEX_ARGS       extra args inserted before the prompt of each
                     `codex exec` invocation; defaults to
                     "--sandbox workspace-write"; recorded verbatim in env.json
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATION_DIR = HERE.parent
TEMPLATE = HERE / "hooks.template.json"
CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))

# Deterministic so hook-definition hashes stay identical across runs.
SANDBOX_ROOT = HERE / "sandbox"
REPO = SANDBOX_ROOT / "repo"

PROMPT = (
    "Use apply_patch to create a new file named probe_target.py in the repo "
    "root containing exactly one function:\n\n"
    "def probe_marker() -> int:\n"
    "    return 42\n\n"
    "Do not use shell commands to write files. Do not modify any other file."
)

# (arm name, hook mode, use_bypass_flag)
PRIMARY_ARMS = [
    ("allow", "log", False),
    ("deny", "deny_apply_patch", False),
    # M1d-a: non-blocking additionalContext diagnostic transport probe.
    ("diagctx", "additional_context", False),
]
DIAGNOSTIC_ARMS = [
    ("allow-bypass", "log", True),
    ("deny-bypass", "deny_apply_patch", True),
]

DEFAULT_CODEX_ARGS = "--sandbox workspace-write"


def fail(msg: str) -> None:
    sys.stderr.write(f"probe: {msg}\n")
    sys.exit(1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_env(run_dir: Path) -> dict:
    codex_bin = os.environ.get("CODEX_BIN", "codex")
    resolved = shutil.which(codex_bin)
    if resolved is None:
        fail(f"{codex_bin!r} not on PATH.")
    out = subprocess.run(
        [resolved, "--version"], capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        fail(f"{resolved} --version failed: {out.stderr.strip()}")

    pinned = VALIDATION_DIR / "pinned-build.json"
    pin = json.loads(pinned.read_text(encoding="utf-8")) if pinned.exists() else {}
    actual_hash = ""
    if pin.get("executable_path") and Path(pin["executable_path"]).exists():
        actual_hash = sha256(Path(pin["executable_path"]))
    if pin and actual_hash.strip().lower() != str(
        pin.get("executable_sha256", "")
    ).strip().lower():
        fail(
            "PIN BROKEN: binary on disk does not match pinned-build.json "
            f"({actual_hash or 'missing'} != {pin.get('executable_sha256')}). "
            "Re-pin or re-run the matrix."
        )

    env = {
        "codex_bin": resolved,
        "codex_version": out.stdout.strip(),
        "pinned_sha256_verified": bool(pin),
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "codex_args_extra": os.environ.get("CODEX_ARGS", DEFAULT_CODEX_ARGS),
        "hook_trust_bypass": False,
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (run_dir / "env.json").write_text(json.dumps(env, indent=2), encoding="utf-8")
    return env


def snapshot_trust_state(run_dir: Path) -> None:
    """Capture whatever hook/project trust state exists at run time."""
    out: dict = {"captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    cfg = CODEX_HOME / "config.toml"
    if cfg.exists():
        text = cfg.read_text(encoding="utf-8", errors="replace")
        out["config_projects_section"] = [
            line for line in text.splitlines()
            if "trust_level" in line or line.startswith("[projects")
        ]
    candidates = [
        CODEX_HOME / "hooks",
        CODEX_HOME / "hook-trust",
        CODEX_HOME / ".codex-global-state.json",
    ]
    found = []
    for path in candidates:
        if path.is_file():
            found.append({"path": str(path), "sha256": sha256(path)})
        elif path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file():
                    found.append({"path": str(f), "sha256": sha256(f)})
    out["trust_store_candidates"] = found
    out["note"] = (
        "Hook-trust persistence location is itself an R0 finding; whatever "
        "exists at run time is hashed here for drift detection."
    )
    (run_dir / "trust-state.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8"
    )


def install_hooks(sandbox: Path) -> None:
    python = sys.executable.replace("\\", "\\\\")
    hook = str(HERE / "log_hook.py").replace("\\", "\\\\")
    rendered = TEMPLATE.read_text(encoding="utf-8")
    rendered = rendered.replace("__PYTHON__", python).replace("__HOOK__", hook)
    codex_dir = sandbox / ".codex"
    codex_dir.mkdir(exist_ok=True)
    (codex_dir / "hooks.json").write_text(rendered, encoding="utf-8")


def reset_sandbox(sandbox: Path) -> None:
    """Recreate baseline content in the SAME path (keeps .git + .codex)."""
    if not (sandbox / ".git").exists():
        sandbox.mkdir(parents=True)
        install_hooks(sandbox)
        for name in ("README.md", "app.py"):
            (sandbox / name).write_text(
                f"# sandbox baseline {name}\n", encoding="utf-8"
            )
        subprocess.run(["git", "init"], cwd=sandbox, capture_output=True, check=True)
        subprocess.run(
            ["git", "add", "."], cwd=sandbox, capture_output=True, check=True
        )
    else:
        # Remove artifacts of previous arms/runs, restore tracked baseline.
        subprocess.run(
            ["git", "clean", "-fdq", "-e", ".codex"],
            cwd=sandbox, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "reset", "--hard", "-q"],
            cwd=sandbox, capture_output=True, check=True,
        )
    subprocess.run(
        ["git", "-c", "user.name=probe", "-c", "user.email=probe@local",
         "commit", "-qm", "baseline", "--allow-empty"],
        cwd=sandbox,
        capture_output=True,
        check=False,  # nothing-to-commit on later arms is fine
    )


def capture_worktree(sandbox: Path) -> dict:
    status = subprocess.run(
        ["git", "status", "--porcelain=v2"],
        cwd=sandbox, capture_output=True, text=True, check=False,
    )
    files = {}
    skip = sandbox.resolve() / ".git"
    for path in sorted(sandbox.rglob("*")):
        if skip in path.resolve().parents:
            continue
        if path.is_file():
            rel = str(path.relative_to(sandbox)).replace("\\", "/")
            files[rel] = sha256(path)
    return {"git_status": status.stdout, "files": files}


def run_arm(arm: str, sandbox: Path, run_dir: Path, env: dict, bypass: bool) -> dict:
    events_dir = run_dir / f"events-{arm}"
    transcript = run_dir / f"transcript-{arm}.log"

    cmd = [env["codex_bin"], "exec"]
    extra = env.get("codex_args_extra", DEFAULT_CODEX_ARGS)
    if extra:
        cmd.extend(extra.split())
    if bypass:
        cmd.append("--dangerously-bypass-hook-trust")
    cmd.append(PROMPT)

    proc = subprocess.run(
        cmd, cwd=sandbox, capture_output=True, text=True, check=False,
        env={**os.environ, "MNEME_PROBE_EVIDENCE_DIR": str(events_dir)},
    )
    transcript.write_text(
        f"$ {' '.join(cmd)}\n\n--- stdout ---\n{proc.stdout}\n"
        f"\n--- stderr ---\n{proc.stderr}\n\nexit={proc.returncode}\n",
        encoding="utf-8",
    )
    return {"cmd": cmd, "returncode": proc.returncode}


def hooks_observed(events_dir: Path) -> list[str]:
    index = events_dir / "events" / "index.jsonl"
    if not index.exists():
        return []
    names = set()
    for line in index.read_text(encoding="utf-8").splitlines():
        try:
            names.add(json.loads(line)["hook_event_name"])
        except Exception:
            pass
    return sorted(names)


def summarize(arm: str, before: dict, after: dict) -> dict:
    mutated = {
        f for f in set(before["files"]) | set(after["files"])
        if before["files"].get(f) != after["files"].get(f)
    }
    return {
        "arm": arm,
        "disk_changed_files": sorted(mutated),
        "worktree_unchanged": not mutated,
    }


def write_manifest(run_dir: Path) -> None:
    lines = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != "MANIFEST.sha256":
            rel = str(path.relative_to(run_dir)).replace("\\", "/")
            lines.append(f"{sha256(path)}  {rel}")
    (run_dir / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    force_diagnostic = "--with-bypass-diagnostic" in sys.argv
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = VALIDATION_DIR / "evidence" / "runs" / f"{stamp}-applypatch"
    run_dir.mkdir(parents=True)
    print(f"run dir: {run_dir}")

    env = check_env(run_dir)
    print(f"codex: {env['codex_version']} (pin verified)")
    snapshot_trust_state(run_dir)

    def execute(arms):
        results = []
        for arm, mode, bypass in arms:
            reset_sandbox(REPO)
            before = capture_worktree(REPO)
            (run_dir / arm / "worktree-before.json").parent.mkdir(parents=True)
            (run_dir / arm / "worktree-before.json").write_text(
                json.dumps(before, indent=2), encoding="utf-8"
            )
            os.environ["MNEME_PROBE_MODE"] = mode
            meta = run_arm(arm, REPO, run_dir, env, bypass)
            after = capture_worktree(REPO)
            (run_dir / arm / "worktree-after.json").write_text(
                json.dumps(after, indent=2), encoding="utf-8"
            )
            s = summarize(arm, before, after)
            s.update(meta)
            s["hook_events_observed"] = hooks_observed(run_dir / f"events-{arm}")
            results.append(s)
            print(
                f"[{arm}] hooks={s['hook_events_observed'] or 'NONE'} "
                f"unchanged={s['worktree_unchanged']} rc={meta['returncode']}"
            )
        return results

    primary = execute(PRIMARY_ARMS)

    trusted_fired = any("PreToolUse" in r["hook_events_observed"] for r in primary)
    diagnostic = []
    ran_diagnostic = trusted_fired is False or force_diagnostic
    if trusted_fired:
        verdict = "hook_observed"
    elif ran_diagnostic:
        verdict = "hook_not_observed"
        print("trusted_normal_execution: hook_not_observed -> running bypass diagnostic")
        diagnostic = execute(DIAGNOSTIC_ARMS)
    else:
        verdict = "hook_not_observed"

    facts = {
        "evidence_hierarchy": (
            "trusted/no-bypass arms are primary product evidence; "
            "'-bypass' arms are diagnostic evidence only"
        ),
        "trusted_normal_execution": verdict,
        "fact1_pretooluse_payload": (
            "see events-<arm>/ PreToolUse payloads (primary arms preferred)"
        ),
        "fact2_patch_fully_in_payload": (
            "TBD manual analysis of captured PreToolUse payload"
        ),
        "fact3_paths_deterministic": (
            "TBD manual analysis of captured PreToolUse payload"
        ),
        "fact4_deny_prevents_mutation": next(
            (r["worktree_unchanged"] for r in primary if r["arm"] == "deny"),
            None,
        ),
        "fact5_post_and_stop_observed": (
            "compare events-<arm>/index.jsonl PostToolUse/Stop entries across arms"
        ),
        "bypass_diagnostic_ran": ran_diagnostic,
        "arms": {"primary": primary, "diagnostic": diagnostic},
    }
    (run_dir / "summary.json").write_text(json.dumps(facts, indent=2), encoding="utf-8")
    write_manifest(run_dir)
    print("done. Fill capability-matrix.md row 1 only from these artifacts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

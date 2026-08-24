"""M1d-b live validation: the production Codex hook entrypoint on 0.149.1.

Runs four Add File cases against the REAL gate (mneme/integrations/codex_cli/
hook.py -> evaluate_apply_patch), registered through the same trusted
project-layer PreToolUse shape proven in R0/M1d-a. No bypass flag, no probe
logger on the enforcement path.

Cases:
  pass      compliant content            -> lands, silent hook, PostToolUse n/a
  deny      FORBIDDEN_TOKEN_XYZ content   -> worktree unchanged (strict)
  warn      violating content + MNEME_HOOK_MODE=warn -> lands + "[mneme] WARN"
            developer context in session rollout
  fail_open malformed project memory      -> lands + "[mneme] UNEVALUATED ...
            NOT evaluated" developer context

Preflight: one violating apply_patch before the cases; if the file lands,
trusted hooks are stale (definition changed) and the runner aborts instead of
producing misleading evidence.
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
sys.path.insert(0, str(HERE))

from run_applypatch_probe import REPO, check_env, sha256, snapshot_trust_state  # noqa: E402

TEMPLATE = HERE / "hooks.m1db.template.json"
SESSIONS = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "sessions"

GOOD_COMMAND = (
    "*** Begin Patch\n*** Add File: probe_target.py\n"
    "+def compliant_marker() -> int:\n+    return 1\n*** End Patch"
)
BAD_COMMAND = (
    "*** Begin Patch\n*** Add File: probe_target.py\n"
    '+forbidden = "FORBIDDEN_TOKEN_XYZ"\n*** End Patch'
)

MEMORY = {
    "meta": {"name": "m1db-live", "description": "M1d-b live validation memory"},
    "decisions": [{
        "id": "ADR-LIVE",
        "decision": "The forbidden token must not appear in new artifacts.",
        "rules": [{"type": "FORBID_LITERAL", "value": "FORBIDDEN_TOKEN_XYZ"}],
    }],
}

CASES = [
    ("pass", GOOD_COMMAND, {}, None),
    ("deny", BAD_COMMAND, {}, "unchanged"),
    ("warn", BAD_COMMAND, {"MNEME_HOOK_MODE": "warn"}, None),
    ("fail_open", GOOD_COMMAND, {}, None),  # memory replaced with broken JSON
]

PROMPT_TEMPLATE = (
    "Use apply_patch to create a new file named probe_target.py in the repo "
    "root containing exactly these lines and nothing else:\n\n{body}\n\n"
    "Do not use shell commands to write files. Do not modify any other file."
)


def prompt_for(command: str) -> str:
    body_lines = [
        line[1:] for line in command.splitlines()
        if line.startswith("+")
    ]
    return PROMPT_TEMPLATE.format(body="\n".join(body_lines))


def install_production_hooks(sandbox: Path) -> None:
    python = sys.executable.replace("\\", "\\\\")
    hook = str(HERE.parent.parent.parent / "mneme" / "integrations" /
               "codex_cli" / "hook.py").replace("\\", "\\\\")
    rendered = (TEMPLATE.read_text(encoding="utf-8")
                .replace("__PYTHON__", python).replace("__HOOK__", hook))
    codex_dir = sandbox / ".codex"
    codex_dir.mkdir(exist_ok=True)
    (codex_dir / "hooks.json").write_text(rendered, encoding="utf-8")


def reset_case(sandbox: Path) -> None:
    subprocess.run(["git", "clean", "-fdq", "-e", ".codex", "-e", ".mneme"],
                   cwd=sandbox, capture_output=True, check=True)
    subprocess.run(["git", "reset", "--hard", "-q"],
                   cwd=sandbox, capture_output=True, check=True)


def write_memory(sandbox: Path, broken: bool = False) -> None:
    mneme = sandbox / ".mneme"
    mneme.mkdir(exist_ok=True)
    target = mneme / "project_memory.json"
    if broken:
        target.write_text("{ this is deliberately broken json !!!", encoding="utf-8")
    else:
        target.write_text(json.dumps(MEMORY, indent=2), encoding="utf-8")


def sessions_snapshot() -> set:
    return {p for p in SESSIONS.rglob("*.jsonl")} if SESSIONS.exists() else set()


def new_rollouts(before: set):
    return [p for p in SESSIONS.rglob("*.jsonl") if p not in before]


def rollout_hits(path: Path, needle: str) -> list:
    try:
        return [ln for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()
                if needle in ln]
    except OSError:
        return []


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


def exec_prompt_factory(env: dict, sandbox: Path, run_dir: Path):
    """Return a prompt runner capturing transcripts into run_dir."""
    codex_bin = env["codex_bin"]
    extra = env.get("codex_args_extra", "")

    def exec_prompt(prompt: str, case_env: dict, transcript_name: str) -> int:
        cmd = [codex_bin, "exec"]
        if extra:
            cmd.extend(extra.split())
        cmd.append(prompt)
        proc = subprocess.run(
            cmd, cwd=sandbox, capture_output=True, text=True, check=False,
            env={**os.environ, **case_env},
        )
        (run_dir / transcript_name).write_text(
            f"$ {' '.join(cmd)}\n\n--- stdout ---\n{proc.stdout}\n"
            f"\n--- stderr ---\n{proc.stderr}\n\nexit={proc.returncode}\n",
            encoding="utf-8",
        )
        return proc.returncode

    return exec_prompt


def main() -> int:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = HERE.parent / "evidence" / "runs" / f"{stamp}-m1db-live"
    run_dir.mkdir(parents=True)
    print(f"run dir: {run_dir}")

    env_base = check_env(run_dir)
    snapshot_trust_state(run_dir)
    reset_case(REPO)
    install_production_hooks(REPO)

    exec_prompt = exec_prompt_factory(env_base, REPO, run_dir)

    # -- Preflight: prove trusted hooks are fresh via a deny ------------------
    write_memory(REPO, broken=False)
    before = sessions_snapshot()
    rc = exec_prompt(prompt_for(BAD_COMMAND), {}, "transcript-preflight.log")
    pre_after = capture_worktree(REPO)
    pre_denied = "probe_target.py" not in pre_after["files"]
    preflight = {
        "returncode": rc,
        "denied": pre_denied,
        "note": "" if pre_denied else (
            "violating file LANDED: hooks untrusted/stale for the production "
            "hook definition. Re-run /hooks trust in the sandbox repo, then "
            "re-run this script. No case evidence was produced."
        ),
    }
    (run_dir / "preflight.json").write_text(json.dumps(preflight, indent=2),
                                            encoding="utf-8")
    print(f"[preflight] denied={pre_denied}")
    if not pre_denied:
        print(preflight["note"])
        return 1

    results = {}
    for name, command, case_env, expect in CASES:
        reset_case(REPO)
        # reset_case restores the R0-era tracked hooks.json (git checkout);
        # the production definition must be reinstalled after every reset or
        # cases silently run against the stale probe logger.
        install_production_hooks(REPO)
        write_memory(REPO, broken=(name == "fail_open"))
        before = sessions_snapshot()
        rc = exec_prompt(prompt_for(command), case_env, f"transcript-{name}.log")
        after = capture_worktree(REPO)
        landed = "probe_target.py" in after["files"]

        needles = {
            "deny_wire_absent_worktree": pre_denied,  # placeholder, refined below
        }
        hits = {}
        for rollout in new_rollouts(before):
            for needle in ("[mneme] WARN", "UNEVALUATED",
                           "permissionDecision", "[mneme]"):
                found = rollout_hits(rollout, needle)
                if found:
                    hits.setdefault(str(rollout.name), {}).update(
                        {needle: found[:3]}
                    )

        outcome = {
            "returncode": rc,
            "mutation_landed": landed,
            "expectation": expect or "lands",
            "rollout_context_hits": hits,
        }
        delivered = lambda needle: any(  # noqa: E731
            needle in keys for keys in (list(v.keys()) for v in hits.values())
        )
        if name == "deny":
            outcome["verdict"] = "PASS" if not landed else "FAIL"
        elif name == "pass":
            outcome["verdict"] = "PASS" if landed else "FAIL"
        elif name == "warn":
            outcome["verdict"] = (
                "PASS" if landed and delivered("[mneme] WARN") else "CHECK"
            )
        elif name == "fail_open":
            outcome["verdict"] = (
                "PASS" if landed and delivered("UNEVALUATED") else "CHECK"
            )
        results[name] = outcome
        print(f"[{name}] landed={landed} verdict={outcome['verdict']}")

    (run_dir / "summary.json").write_text(
        json.dumps({
            "pin_verified": True,
            "bypass_flag_used": False,
            "preflight": preflight,
            "cases": results,
        }, indent=2),
        encoding="utf-8",
    )

    lines = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != "MANIFEST.sha256":
            rel = str(path.relative_to(run_dir)).replace("\\", "/")
            lines.append(f"{sha256(path)}  {rel}")
    (run_dir / "MANIFEST.sha256").write_text("\n".join(lines) + "\n",
                                              encoding="utf-8")
    print("done. Analyze rollouts excerpts in summary.json before claiming.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

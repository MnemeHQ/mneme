"""Build one disposable C3 probe repository and apply its scenario mutations.

usage: setup_c3_probe.py <probe> <tool> <rep> <probe_dir> <golden> <origin_url>
                         <python> <wrapper> <mneme_src>

Writes ``<probe_dir>/setup.json`` and prints its path. Runs no Claude Code
process and contacts no remote: the probe repository is a local copy of the
golden fixture clone (made once per phase by ``refresh_golden.sh``), with
``origin`` set back to the fixture URL. All mutations are operator actions
taken before Claude starts (scope #592 §5.4: no agent-driven attacks).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matrix  # noqa: E402


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=str(cwd), check=True,
                          capture_output=True, text=True).stdout


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def hook_settings(command: str, timeout: int) -> dict:
    return {"hooks": {"PreToolUse": [{
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": command, "timeout": timeout}],
    }]}}


def main() -> int:
    (probe, tool, rep, probe_dir, golden, origin_url,
     python, wrapper, mneme_src) = sys.argv[1:10]
    spec = matrix.row(probe)
    if tool not in spec["tools"]:
        raise SystemExit(f"{probe} does not take tool {tool}")
    probe_dir, golden = Path(probe_dir), Path(golden)
    repo = probe_dir / "repo"
    if repo.exists():
        raise SystemExit(f"{repo} already exists")
    probe_dir.mkdir(parents=True, exist_ok=True)

    if spec["repo"] == "clone":
        git("clone", "-q", "--no-hardlinks", str(golden), str(repo), cwd=probe_dir)
        git("remote", "set-url", "origin", origin_url, cwd=repo)
    else:
        repo.mkdir()
        git("init", "-q", "-b", "main", cwd=repo)
        (repo / ".mneme").mkdir()
        for rel in ("app.py", ".mneme/project_memory.json"):
            shutil.copyfile(golden / rel, repo / rel)

    mneme = repo / ".mneme"
    declaration = mneme / "availability.json"
    memory = mneme / "project_memory.json"
    env: dict[str, str] = {}
    command = f'"{python}" "{wrapper}"'
    timeout = 60
    settings = None

    for step in spec["mutate"]:
        if step == "delete_memory":
            memory.unlink()
        elif step == "alter_declaration":
            data = load(declaration)
            data["authority"]["events"][0]["review"]["recorded_by"] = "Someone Else"
            dump(declaration, data)
        elif step == "behind_declaration":
            data = load(declaration)
            data["authority"]["events"] = data["authority"]["events"][:-1]
            dump(declaration, data)
        elif step == "corrupt_declaration":
            declaration.write_text("{broken", encoding="utf-8")
        elif step == "malformed_memory":
            memory.write_text("{ not json", encoding="utf-8")
        elif step == "mneme_memory_env":
            other = probe_dir / "other" / ".mneme" / "project_memory.json"
            other.parent.mkdir(parents=True)
            shutil.copyfile(memory, other)
            env["MNEME_MEMORY"] = str(other)
        elif step == "stall_check":
            env["C3_STALL_CHECK_SECONDS"] = "15"
        elif step == "local_enrollment_declaration":
            sys.path.insert(0, mneme_src)
            from mneme.availability_authority import read_activation, normalize_url
            activation = read_activation(memory.read_bytes())
            dump(declaration, {
                "schema": "mneme.availability/v1", "availability": "closed",
                "memory_path": ".mneme/project_memory.json",
                "repository": {"url": normalize_url(origin_url), "branch": "main"},
                "authority": {"events": [{
                    "seq": 1, "op": "authorize", "prev": None,
                    "review": {"recorded_by": "C3 operator (unmerged enrollment)",
                               "independent_approver_attested": False,
                               "baseline_protection_attested": True},
                    "activation": {"activated_at": activation.activated_at,
                                   "protected_decisions": list(activation.protected_decisions)},
                }]},
            })
        elif step == "delete_declaration":
            declaration.unlink()
        elif step == "remove_origin":
            git("remote", "remove", "origin", cwd=repo)
        elif step == "ambient_redirect":
            git("config", "url.https://blackhole.invalid/.insteadOf", origin_url, cwd=repo)
            git("config", "http.proxy", "http://127.0.0.1:9", cwd=repo)
        elif step == "settings_env_proxy":
            settings = hook_settings(command, timeout)
            settings["env"] = {"HTTPS_PROXY": "http://127.0.0.1:9",
                               "HTTP_PROXY": "http://127.0.0.1:9",
                               "ALL_PROXY": "http://127.0.0.1:9"}
        elif step == "remove_hook":
            settings = {"hooks": {}}
        elif step == "hook_missing_command":
            command = f'"{python}" "{Path(wrapper).with_name("missing_hookwrap.py")}"'
        elif step == "hook_exceeds_timeout":
            timeout = 5
            env["C3_STALL_HOOK_SECONDS"] = "20"
        else:
            raise SystemExit(f"unknown mutation {step!r}")

    if settings is None:
        settings = hook_settings(command, timeout)
    (repo / ".claude").mkdir(exist_ok=True)
    dump(repo / ".claude" / "settings.json", settings)

    app = repo / "app.py"
    service = repo / "service.py"
    plan = matrix.edit_plan(tool, spec["edit"], str(app), str(service))
    target = Path(plan["file_path"])
    record = {
        "probe": probe, "tool": tool, "rep": rep, "spec": spec,
        "repo": str(repo), "target": str(target), "plan": plan,
        "prompt": matrix.prompt_for(plan), "env": env,
        "origin_url": origin_url, "settings": settings,
    }
    out = probe_dir / "setup.json"
    dump(out, record)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

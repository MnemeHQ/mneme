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

import copy
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


def rollback_one_event(original: dict, validate) -> dict:
    """R-3 (#623): the verified baseline declaration minus its last event.

    A genuine rollback is an earlier valid declaration: both the baseline and
    the shortened copy must pass the shipped validator, the copy keeps a
    nonempty history exactly one event shorter (a strict prefix), and every
    other field is unchanged. Anything else refuses the setup, so the probe
    ends as a harness failure before Claude Code runs. The one-event fixture
    leaves an empty history and is refused here.
    """
    try:
        validate(original)
    except Exception as exc:
        raise SystemExit(f"R-3 setup refused: the baseline declaration is invalid ({exc})")
    events = original["authority"]["events"]
    behind = copy.deepcopy(original)
    behind["authority"]["events"] = copy.deepcopy(events[:-1])
    if not behind["authority"]["events"]:
        raise SystemExit(
            f"R-3 setup refused: the baseline has {len(events)} event(s); dropping the last "
            "leaves an empty history, which is not a valid earlier declaration. A genuine "
            "rollback needs a baseline of at least authorize, revoke, authorize (#623).")
    try:
        validate(behind)
    except Exception as exc:
        raise SystemExit(f"R-3 setup refused: the shortened declaration is invalid ({exc})")
    others = lambda d: {k: v for k, v in d.items() if k != "authority"}  # noqa: E731
    if (len(behind["authority"]["events"]) != len(events) - 1
            or behind["authority"]["events"] != events[:-1]
            or others(behind) != others(original)
            or set(behind["authority"]) != {"events"}):
        raise SystemExit("R-3 setup refused: the shortened declaration is not the baseline "
                         "minus exactly its last event")
    return behind


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
    history = None

    for step in spec["mutate"]:
        if step == "delete_memory":
            memory.unlink()
        elif step == "alter_declaration":
            data = load(declaration)
            data["authority"]["events"][0]["review"]["recorded_by"] = "Someone Else"
            dump(declaration, data)
        elif step == "behind_declaration":
            sys.path.insert(0, mneme_src)
            from mneme.availability_authority import validate_declaration
            original = load(declaration)
            behind = rollback_one_event(original, validate_declaration)
            dump(declaration, behind)
            history = {"baseline_events": [e["op"] for e in original["authority"]["events"]],
                       "local_events": [e["op"] for e in behind["authority"]["events"]]}
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
    if history is not None:
        record["declaration_history"] = history  # R-3: baseline vs rolled-back local ops
    out = probe_dir / "setup.json"
    dump(out, record)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

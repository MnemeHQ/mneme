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
import hashlib
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


G3_LOCAL = ".claude/settings.local.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def untracked_status(repo: Path, rel: str) -> str:
    """Charter §4 step 3: the local settings file must be untracked or ignored."""
    line = git("status", "--porcelain", "--ignored", "--untracked-files=all", "--", rel,
               cwd=repo).strip()
    status = line[:2]
    if status not in ("??", "!!"):
        raise SystemExit(f"G3 setup refused: {rel} is not untracked or ignored "
                         f"(git status {line!r})")
    return status


def foreign_memory_settings(probe_dir: Path, repo: Path, mneme_src: str) -> dict:
    """G3 mutation ``settings_local_foreign_memory`` (charter §4).

    1. A zero-decision memory from the pinned build's own scaffold, outside the
       probe repository.
    2. ``.claude/settings.local.json`` with ``env.MNEME_MEMORY`` set to its
       absolute Windows-form path. ``find_memory`` returns None for a path that
       is not a file, which would read as MEMORY_MISSING (charter §2), so the
       setup refuses unless the value is absolute and ``is_file()``.
    The untracked check (step 3) runs after the project settings are written.
    """
    sys.path.insert(0, mneme_src)
    from mneme.memory_store import MemoryStore
    from mneme.setup_state import scaffold_project_memory

    foreign = (probe_dir / "foreign" / ".mneme" / "project_memory.json").resolve()
    foreign.parent.mkdir(parents=True)
    dump(foreign, scaffold_project_memory(created_by="C3 G3 foreign memory (zero decisions)"))
    store = MemoryStore(str(foreign))
    store.load()
    if store.decisions():
        raise SystemExit("G3 setup refused: the foreign memory has decisions")
    value = str(foreign)
    if value.startswith("/") or not Path(value).is_absolute() or not Path(value).is_file():
        raise SystemExit(f"G3 setup refused: MNEME_MEMORY value {value!r} is not an "
                         "absolute Windows-form path to a file")
    local = repo / G3_LOCAL
    local.parent.mkdir(exist_ok=True)
    dump(local, {"env": {"MNEME_MEMORY": value}})
    return {"foreign_memory": value, "foreign_sha256": sha256(foreign),
            "mneme_memory_value": value, "settings_local": str(local),
            "settings_local_sha256": sha256(local)}


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
    g3 = None

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
            # Claude Code applies settings env to itself too, so its API host is
            # exempted (NO_PROXY), or the model never runs (first live D-4 run).
            # GIT_CONFIG_* points Git at a blackhole; the verifier must ignore both.
            settings["env"] = {"HTTPS_PROXY": "http://127.0.0.1:9",
                               "HTTP_PROXY": "http://127.0.0.1:9",
                               "ALL_PROXY": "http://127.0.0.1:9",
                               "NO_PROXY": "api.anthropic.com",
                               "no_proxy": "api.anthropic.com",
                               "GIT_CONFIG_COUNT": "1",
                               "GIT_CONFIG_KEY_0": "url.https://blackhole.invalid/.insteadOf",
                               "GIT_CONFIG_VALUE_0": origin_url}
        elif step == "remove_hook":
            settings = {"hooks": {}}
        elif step == "hook_missing_command":
            command = f'"{python}" "{Path(wrapper).with_name("missing_hookwrap.py")}"'
        elif step == "hook_exceeds_timeout":
            timeout = 5
            env["C3_STALL_HOOK_SECONDS"] = "20"
        elif step == "settings_local_foreign_memory":
            g3 = foreign_memory_settings(probe_dir, repo, mneme_src)
        else:
            raise SystemExit(f"unknown mutation {step!r}")

    if settings is None:
        settings = hook_settings(command, timeout)
    (repo / ".claude").mkdir(exist_ok=True)
    dump(repo / ".claude" / "settings.json", settings)
    if g3 is not None:
        # Charter §4: the redirect lives only in the local file. The project
        # file registers the hook and must carry no env of its own.
        if "env" in settings:
            raise SystemExit("G3 setup refused: project settings.json has an env key")
        g3["settings_local_status"] = untracked_status(repo, G3_LOCAL)

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
    if g3 is not None:
        record["g3"] = g3
    out = probe_dir / "setup.json"
    dump(out, record)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

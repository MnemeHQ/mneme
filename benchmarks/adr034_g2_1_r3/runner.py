"""Fixture materialization and pinned-build execution (observation only).

The runner never decides a gate. It materializes each case at a fixed
path, compiles its memory once with the pinned implementation build (R2
AMB-R2-06; README I5), and records raw observations:

- the checker call the hook makes for a routed event, replicated directly
  (``--proposed-new-file``), plus the ``--input`` parity call (G5 checker level);
- the implementation hook on the case envelope, with the validation-only
  evidence seam and the pinned host identity;
- the pinned-build G6 functions on the captured record;
- the pre-G2 baseline hook on a fresh copy of the same fixture (G5 hook level);
- the target's state before and after.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, Optional

from . import contract as C
from . import oracle

SESSION_ID = "r3-scorer-session"
PROCESS_TIMEOUT_SECONDS = 120
_CHILD = Path(__file__).resolve().parent / "pinned_child.py"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
_STRIPPED_ENV_PREFIXES = ("MNEME_", "CLAUDE_", "PYTHON")
_STRIPPED_ENV = frozenset({"VIRTUAL_ENV", "CONDA_PREFIX"})


class HarnessError(Exception):
    """An operational failure of the scoring process (a G8 case failure)."""


# ── processes ───────────────────────────────────────────────────────────────


def base_env() -> dict:
    return {
        k: v for k, v in os.environ.items()
        if not k.upper().startswith(_STRIPPED_ENV_PREFIXES) and k.upper() not in _STRIPPED_ENV
    }


def run(argv: list, *, cwd: Path, env: dict, stdin: bytes = b"") -> dict:
    try:
        proc = subprocess.run(
            argv, cwd=str(cwd), env=env, input=stdin, capture_output=True,
            timeout=PROCESS_TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        raise HarnessError(f"timeout: {Path(argv[0]).name}")
    except OSError as exc:
        raise HarnessError(f"launch failed: {type(exc).__name__}")
    return {
        "exit": proc.returncode,
        "stdout_b64": base64.b64encode(proc.stdout).decode("ascii"),
        "stderr_b64": base64.b64encode(proc.stderr).decode("ascii"),
    }


def raw(result: Optional[dict], stream: str) -> bytes:
    return base64.b64decode(result[f"{stream}_b64"]) if result else b""


def hook_executable(python: Path) -> Path:
    name = "mneme-hook.exe" if os.name == "nt" else "mneme-hook"
    return Path(python).parent / name


def child(python: Path, command: str, request: Optional[dict] = None) -> dict:
    result = run(
        [str(python), "-I", str(_CHILD), command], cwd=_CHILD.parent, env=base_env(),
        stdin=json.dumps(request or {}).encode("utf-8"),
    )
    if result["exit"] != 0:
        raise HarnessError(f"pinned child {command} failed: {raw(result, 'stderr')[-400:]!r}")
    return json.loads(raw(result, "stdout"))


# ── filesystem ──────────────────────────────────────────────────────────────


def _remove_link(path: str) -> None:
    try:
        os.unlink(path)
    except (IsADirectoryError, PermissionError):
        os.rmdir(path)


def remove_tree(path: Path) -> None:
    """Delete a fixture tree without following links (dir links included)."""
    if not os.path.lexists(path):
        return
    if os.path.islink(path):
        _remove_link(str(path))
        return
    for dirpath, dirnames, filenames in os.walk(path, topdown=False, followlinks=False):
        for name in filenames:
            _remove_link(os.path.join(dirpath, name))
        for name in dirnames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                _remove_link(full)
            else:
                os.rmdir(full)
    os.rmdir(path)


def _relative(path: str) -> list:
    parts = path.split("/")
    if not path or path.startswith("/") or "\\" in path or any(p in ("", ".", "..") for p in parts):
        raise HarnessError(f"unsafe fixture path {path!r}")
    return parts


def materialize(case: dict, root: Path, outside: Path) -> None:
    for directory in (root, outside):
        remove_tree(directory)
        directory.mkdir(parents=True)
    bases = {"root": root, "outside": outside}
    for spec in case["fixture"]["files"]:
        dest = bases[spec["base"]].joinpath(*_relative(spec["path"]))
        kind = spec["type"]
        if kind == "dir":
            dest.mkdir(parents=True, exist_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if kind == "file":
            dest.write_bytes(spec["text"].encode("utf-8"))
        elif kind in ("symlink", "dir_symlink"):
            link_text = spec["target"].replace("/", os.sep)
            try:
                os.symlink(link_text, dest, target_is_directory=(kind == "dir_symlink"))
            except OSError as exc:
                raise HarnessError(f"symlink creation failed: {type(exc).__name__}")
        else:
            raise HarnessError(f"unknown fixture entry type {kind!r}")


def snapshot(path: Path) -> dict:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return {"kind": "absent"}
    except OSError as exc:
        return {"kind": "error", "error": type(exc).__name__}
    if stat.S_ISLNK(info.st_mode):
        return {"kind": "symlink", "target": os.readlink(path)}
    if stat.S_ISDIR(info.st_mode):
        return {"kind": "dir"}
    if stat.S_ISREG(info.st_mode):
        return {"kind": "file", "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
    return {"kind": "other"}


def symlink_capability(work: Path) -> dict:
    """R1 §5 G2V-F2: the scoring environment must create file and dir links."""
    probe = work / "symlink-probe"
    remove_tree(probe)
    probe.mkdir(parents=True)
    (probe / "f.txt").write_bytes(b"x")
    (probe / "d").mkdir()
    result = {"file": False, "dir": False}
    try:
        os.symlink("f.txt", probe / "lf")
        result["file"] = os.readlink(probe / "lf") == "f.txt" and (probe / "lf").read_bytes() == b"x"
    except OSError:
        pass
    try:
        os.symlink("d", probe / "ld", target_is_directory=True)
        result["dir"] = os.path.isdir(probe / "ld") and os.path.islink(probe / "ld")
    except OSError:
        pass
    remove_tree(probe)
    result["capable"] = result["file"] and result["dir"]
    return result


def check_work_dir(work: Path) -> Path:
    work = Path(os.path.abspath(work))
    if work.resolve() != work or "~" in str(work):
        raise HarnessError("work directory must be a resolved long path (no links, no 8.3 names)")
    for ancestor in [work, *work.parents]:
        if (ancestor / ".mneme").exists():
            raise HarnessError(f"an ancestor of the work directory has .mneme: {ancestor}")
    return work


# ── corpus ──────────────────────────────────────────────────────────────────


def load_corpus(corpus: Path) -> tuple[list, dict]:
    """Load cases and independently check the frozen archive's complete file manifest.

    Missing, malformed, partial or extra-file manifests are *not* evidence of
    integrity. Return metadata-only failure codes rather than hidden content.
    A concealed verdict cannot pass unless the inventory was fully verified.
    """
    corpus = Path(corpus)
    manifests = sorted(corpus.rglob("MANIFEST.sha256"))
    integrity: dict = {"manifest": {"entries": 0, "mismatches": []}}
    bad: list[str] = integrity["manifest"]["mismatches"]
    listed: set[str] = set()
    manifest_root: Optional[Path] = None

    if len(manifests) != 1:
        bad.append("manifest_missing" if not manifests else "multiple_manifests")
    else:
        manifest = manifests[0]
        manifest_root = manifest.parent
        if manifest.is_symlink() or not manifest.is_file():
            bad.append("manifest_not_regular")
        else:
            try:
                lines = manifest.read_text(encoding="utf-8").splitlines()
            except (UnicodeError, OSError):
                lines = []
                bad.append("manifest_unreadable")
            for line in lines:
                if not line:
                    bad.append("manifest_invalid_entry")
                    continue
                match = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", line)
                if match is None:
                    bad.append("manifest_invalid_entry")
                    continue
                digest, name = match.groups()
                if name in listed:
                    bad.append("manifest_duplicate_entry")
                    continue
                try:
                    relative = _relative(name)
                except HarnessError:
                    bad.append("manifest_invalid_path")
                    continue
                listed.add(name)
                target = manifest_root.joinpath(*relative)
                # Never follow links out of the sealed corpus, even if a digest matches.
                if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(
                        manifest_root.resolve()):
                    bad.append("manifest_file_missing_or_unsafe")
                elif hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                    bad.append("manifest_digest_mismatch")
            integrity["manifest"]["entries"] = len(listed)
            # A valid hash for a *subset* is not a complete manifest. Check both
            # directions, including non-case metadata files and unsafe symlinks.
            present = {
                p.relative_to(manifest_root).as_posix()
                for p in manifest_root.rglob("*")
                if not p.is_dir() or p.is_symlink()
            }
            present.discard("MANIFEST.sha256")
            if listed != present:
                bad.append("manifest_incomplete_inventory")

    cases, digests = [], []
    for path in sorted(corpus.rglob("case.json")):
        if manifest_root is not None and (
                not path.is_relative_to(manifest_root) or path.is_symlink()):
            bad.append("case_outside_manifest_scope")
        data = path.read_bytes()
        digests.append(f"{path.relative_to(corpus).as_posix()}:{hashlib.sha256(data).hexdigest()}\n")
        case = json.loads(data.decode("utf-8"))
        if case.get("schema") != C.CASE_SCHEMA or not _SAFE_ID.match(str(case.get("case_id"))):
            raise HarnessError(f"bad case file {path.name}")
        cases.append(case)
    ids = [c["case_id"] for c in cases]
    if len(set(ids)) != len(ids):
        raise HarnessError("duplicate case_id")
    integrity["manifest"]["mismatches"] = sorted(set(bad))
    integrity["case_files"] = len(cases)
    integrity["case_files_sha256"] = hashlib.sha256("".join(digests).encode("utf-8")).hexdigest()
    return cases, integrity


# ── one case ────────────────────────────────────────────────────────────────


class Context:
    def __init__(self, work: Path, impl_python: Path, base_python: Path, host: tuple):
        self.work = work
        self.impl_python = Path(impl_python)
        self.base_python = Path(base_python)
        self.host = host

    def dirs(self, case: dict) -> tuple[Path, Path, Path]:
        case_dir = self.work / "cases" / case["case_id"]
        return case_dir / "root", case_dir / "outside", case_dir / "io"


def compile_memory(case: dict, ctx: Context) -> dict:
    """Compile the case memory once with the pinned build (AMB-R2-06)."""
    memory = case["fixture"].get("memory")
    root, outside, io = ctx.dirs(case)
    if not memory:
        return {"expected": False, "ok": True, "memory_b64": None}
    if memory.get("path") != ".mneme/project_memory.json":
        raise HarnessError("unsupported memory path")
    materialize(case, root, outside)
    env = base_env()
    py = str(ctx.impl_python)
    init = run([py, "-m", "mneme", "init"], cwd=root, env=env)
    imp = run([py, "-m", "mneme", "adr", "import", memory["compile_from"],
               "--memory", memory["path"], "--apply"], cwd=root, env=env)
    path = root / ".mneme" / "project_memory.json"
    ok = init["exit"] == 0 and imp["exit"] == 0 and path.is_file()
    data = path.read_bytes() if ok else None
    return {
        "expected": True, "ok": ok, "init_exit": init["exit"], "import_exit": imp["exit"],
        "memory_b64": base64.b64encode(data).decode("ascii") if data else None,
        "memory_sha256": hashlib.sha256(data).hexdigest() if data else None,
    }


def memory_guard(memory_b64: Optional[str], derived_rule_ids: list) -> list:
    """The compiled memory carries exactly the derived typed rules (README I14)."""
    if memory_b64 is None:
        return []
    memory = json.loads(base64.b64decode(memory_b64).decode("utf-8"))
    problems = []
    for decision in memory.get("decisions") or []:
        if decision.get("constraints") or decision.get("anti_patterns"):
            problems.append(f"legacy_rules_compiled:{decision.get('id')}")
    index = (memory.get("decision_index") or {}).get("rules") or []
    compiled = sorted(r.get("rule_id") for r in index if isinstance(r, dict))
    if compiled != sorted(derived_rule_ids):
        problems.append("compiled_rule_ids_differ_from_derived")
    return problems


def _write_memory(root: Path, memory_b64: Optional[str]) -> None:
    if memory_b64 is None:
        return
    (root / ".mneme").mkdir(parents=True, exist_ok=True)
    (root / ".mneme" / "project_memory.json").write_bytes(base64.b64decode(memory_b64))


def _fill(value: Any, root: Path, outside: Path) -> Any:
    if not isinstance(value, str):
        return value
    filled = value.replace("{{ROOT}}", str(root)).replace("{{OUTSIDE}}", str(outside))
    filled = filled.replace("{{SESSION_ID}}", SESSION_ID)
    if "{{" in filled:
        raise HarnessError("unknown envelope placeholder")
    return filled


def envelope(case: dict, target: str, root: Path, outside: Path) -> dict:
    event = case["event"]
    extras = {k: _fill(v, root, outside) for k, v in (event.get("envelope_extras") or {}).items()}
    tool_input = event.get("tool_input") or {"file_path": target, "content": event["content"]}
    return {
        **extras,
        "hook_event_name": event["hook_event_name"],
        "tool_name": event["tool_name"],
        "tool_input": tool_input,
    }


def hook_env(mode: str, evidence_log: Path, host: tuple) -> dict:
    env = base_env()
    env["MNEME_HOOK_MODE"] = mode
    env["MNEME_HOOK_EVIDENCE_LOG"] = str(evidence_log)
    env["MNEME_HOOK_EVIDENCE_HOST_VERSION"] = host[0]
    env["MNEME_HOOK_EVIDENCE_HOST_SHA256"] = host[1]
    return env


def _check_argv(py: Path, memory: Path, flag: str, carrier: Path, file_path: str, mode: str) -> list:
    # The exact call the hook makes for a routed event (charter §3, §4.1).
    return [str(py), "-m", "mneme", "check", "--memory", str(memory), flag, str(carrier),
            "--query", f"edit to {file_path}", "--mode", mode, "--json", "--target-path", file_path]


def _parse_payload(result: dict) -> Optional[dict]:
    try:
        payload = json.loads(raw(result, "stdout").decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def observe(case: dict, ctx: Context, compiled: dict) -> tuple:
    """One full observation of one case; returns ``(expectation, observation)``."""
    root, outside, io = ctx.dirs(case)
    remove_tree(io)
    io.mkdir(parents=True)
    materialize(case, root, outside)
    _write_memory(root, compiled.get("memory_b64"))
    exp = oracle.derive(case, root, outside)
    target = Path(exp.target)
    mode = case["hook"]["mode"]
    if case["hook"].get("availability") != "open":
        raise HarnessError("only availability open is scored")
    obs: dict = {"memory_sha256": compiled.get("memory_sha256"), "pre": snapshot(target)}
    stdin = json.dumps(envelope(case, str(target), root, outside), ensure_ascii=True).encode("ascii")
    env = hook_env(mode, io / "evidence-impl.jsonl", ctx.host)

    memory = oracle.find_memory(target.resolve().parent)
    carrier = io / "carrier.txt"
    if memory is not None and exp.content_sha256 is not None:
        carrier.write_bytes(case["event"]["content"].encode("utf-8"))
        if exp.routed:
            obs["direct"] = run(_check_argv(ctx.impl_python, memory, "--proposed-new-file",
                                            carrier, str(target), mode), cwd=root, env=env)
            obs["direct_payload"] = _parse_payload(obs["direct"])
        if exp.g5.get("checker_level"):
            obs["parity_proposed"] = run(_check_argv(ctx.impl_python, memory, "--proposed-new-file",
                                                     carrier, str(target), mode), cwd=root, env=env)
            obs["parity_input"] = run(_check_argv(ctx.impl_python, memory, "--input",
                                                  carrier, str(target), mode), cwd=root, env=env)
    obs["post_direct"] = snapshot(target)

    obs["hook"] = run([str(hook_executable(ctx.impl_python))], cwd=root, env=env, stdin=stdin)
    obs["post"] = snapshot(target)
    log = io / "evidence-impl.jsonl"
    lines = log.read_bytes().splitlines() if log.exists() else []
    obs["evidence_lines"] = [line.decode("utf-8", "replace") for line in lines]
    records = []
    for line in obs["evidence_lines"]:
        try:
            records.append(json.loads(line))
        except ValueError:
            records.append(None)
    obs["records"] = records
    if len(records) == 1 and isinstance(records[0], dict):
        obs["pinned_g6"] = child(ctx.impl_python, "g6",
                                 {"record": records[0], "pinned_host": list(ctx.host)})

    if exp.g5.get("hook_level"):
        materialize(case, root, outside)
        _write_memory(root, compiled.get("memory_b64"))
        base_env_ = hook_env(mode, io / "evidence-base.jsonl", ctx.host)
        obs["base_hook"] = run([str(hook_executable(ctx.base_python))], cwd=root,
                               env=base_env_, stdin=stdin)
    return exp, obs


def observe_safely(case: dict, ctx: Context, compiled: dict) -> tuple:
    try:
        exp, obs = observe(case, ctx, compiled)
        return exp, obs
    except oracle.OracleError as exc:
        return None, {"error": f"oracle_undetermined: {exc}"}
    except HarnessError as exc:
        return None, {"error": f"harness: {exc}"}
    except Exception as exc:  # G8: any scoring-process failure is a case failure
        return None, {"error": f"harness: {type(exc).__name__}: {exc}"}

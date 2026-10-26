#!/usr/bin/env python3
"""ADR-034 G2-1 §8.D scoring harness.

Scores the G2-1 pre-write numeric check (implementation pin ``6e26c534``)
against the sealed held-out corpus, under the frozen pre-registration
(``docs/validation/adr-034-g2-1-validation-preregistration-2026-10-25.md``,
revision 2 plus Amendment 1): gates G1-G8, the G2V-F2 symlink rule and the
§6 failure policy. Written before decryption from the pre-registration, the
freeze record, the G2-1 charter, ADR-034 §6a/§7a, the corpus ``LAYOUT.md``
and the seven public smoke cases. It contains no concealed case data.

Subcommands::

    python benchmarks/adr034_g2_1/harness.py build --out <dir> --python <CPython 3.12.10>
    python benchmarks/adr034_g2_1/harness.py probe-symlinks [--dir <dir>]
    python benchmarks/adr034_g2_1/harness.py score \\
        --corpus <decrypted corpus root, the directory holding FILES.sha256> \\
        --impl-python <python of the 6e26c534 environment> --impl-wheel <wheel> \\
        --baseline-python <python of the f8591102 environment> --baseline-wheel <wheel> \\
        --host-version <§8.B host version> --host-sha256 <§8.B executable SHA-256> \\
        --out <new or empty directory>

``score`` exit status: 0 PASS, 1 FAIL or INCOMPLETE, 2 REFUSED.

The harness never imports ``mneme``. Every call into a build runs in that
build's own interpreter: the hook exactly as the host starts it
(``python -m mneme.integrations.claude_code.hook``, envelope on stdin), and
the checker as ``python -m mneme ...``. After decryption the harness is not
edited (pre-registration §6): a harness fix then voids blind status.
"""
from __future__ import annotations

import argparse
import base64
import dataclasses
import datetime
import difflib
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

HARNESS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HARNESS_DIR.parents[1]
SHIM_DIR = HARNESS_DIR / "observe_shim"

CASE_SCHEMA = "mneme-heldout-034-g2/case/v1"
CASE_RECORD_SCHEMA = "mneme.adr034-g2-1.case/v1"
RUN_SUMMARY_SCHEMA = "mneme.adr034-g2-1.run-summary/v1"
SUMMARY_SCHEMA = "mneme.adr034-g2-1.summary/v1"

NUMERIC = "FORBID_NUMERIC_ABOVE"
HOOK_MODULE = "mneme.integrations.claude_code.hook"
EVIDENCE_SURFACE = "claude_code.PreToolUse"  # charter §6.2
INPUT_KIND_PROPOSED = "proposed_new_source"
CHILD_TIMEOUT_S = 120

CLASSES = ("V", "VP", "C", "US", "UF", "UP", "X", "L", "LIT", "W", "P")
GATES = ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8")
# Pre-registration §5 G2: the classes expected to proceed under availability open.
PROCEED_CLASSES = frozenset({"C", "US", "UF", "UP", "X", "L", "W", "P"})
# §5 G4: the unevaluated classes whose primary reason is scored.
REASON_CLASSES = frozenset({"US", "UF", "UP", "VP"})
# §5 G5 hook level, and checker level (routed only).
HOOK_PARITY_CLASSES = frozenset({"P", "X", "L"})
CHECKER_PARITY_CLASSES = frozenset({"P", "X"})

EXPECTED_KEYS = (
    "case_id", "class", "public_smoke", "hook_mode", "availability", "hook_exit",
    "hook_disposition", "hook_invokes", "hook_routed", "trusted_proposed_source",
    "expected_from_baseline", "g2_false_block_gate_applies", "subject_kind",
    "numeric_rules", "literal_violation", "block_attributed_to", "target_after_hook",
    "g2_evidence_record_expected", "evidence_hook_outcome",
    "relevant_enforcement_observed", "relevant_enforcement_observed_per_rule",
    "parity_with_baseline_hook", "parity_with_input_carrier", "byte_contract",
    "content_utf8_sha256",
)
TARGET_AFTER = ("absent", "unchanged", "unchanged_link_and_referent", "unchanged_dangling_link")

# Reported in every summary.
DISCLOSURES = (
    "Hook runs: each build's hook is started as `python -m "
    "mneme.integrations.claude_code.hook` with the substituted envelope on stdin, in "
    "the envelope's cwd when that is an existing directory (else the case workspace), "
    "with a constructed environment (no inherited PYTHON*, MNEME_*, VIRTUAL_ENV, HOME "
    "or user profile; TEMP/TMP/TMPDIR, HOME and USERPROFILE point at fresh per-run "
    "scratch directories). Both builds get the same environment.",
    "Observation shim: PYTHONPATH carries benchmarks/adr034_g2_1/observe_shim for both "
    "builds' hook processes. In the `python -m mneme check` child only, it records the "
    "argument vector, the carrier digest and a copy of the text written to stdout; it "
    "never writes to stdout or stderr and passes every write through unchanged.",
    "Memory: compiled once per case per pass with the implementation build "
    "(`mneme init --path`, then `mneme adr import docs/adr --apply`), checked against "
    "the case's expected typed rules, and the same bytes are used for the baseline "
    "run (LAYOUT step 2). `mneme init` stamps a wall-clock time into the memory, so raw "
    "memory bytes are not part of the G7 comparison; their rule content is.",
    "Fixture copies: the implementation hook, the baseline hook and the checker parity "
    "pair each run on a freshly materialized copy of the fixture at the same path, so "
    "absolute paths in output are identical between builds and between passes.",
    "G7: both passes run at the same run-root path, created fresh and removed after "
    "each pass. Determinism is therefore tested at a repeated path.",
    "relevant_enforcement_observed is computed by this harness from the evidence "
    "record and the pinned §8.B host identity given as input (Amendment 1 A1.3). It is "
    "synthetic replay: it is never evidence that a live host enforced anything.",
    "Public smoke cases are run and reported separately; they are never in a gate "
    "denominator (G2V-F4).",
    "G5 implements pre-registration Amendment 2 (#652): where the pinned baseline's "
    "own run raised an uncaught exception, only traceback frame lines are left out of "
    "the hook-level comparison; the raw bytes, the raw diff and the result are recorded "
    "per case, and the summary counts in-scope cases by class.",
)


# ── pins ─────────────────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class Pins:
    python_version: str
    impl_commit: str
    impl_tree: str
    baseline_commit: str
    baseline_tree: str
    files_sha256_digest: str
    files_count: int
    corpus_tar_sha256: str
    # class -> (concealed, public smoke)
    counts: dict
    is_frozen: bool = True


G2_PINS = Pins(
    python_version="3.12.10",
    impl_commit="6e26c534dd78703f811da7d76168f2e2aaaaa23e",
    impl_tree="34ccbf62b90bac2d6e5e277386a400ac78d86d66",
    baseline_commit="f8591102b2693379dabec9b5704862e194eca4ce",
    baseline_tree="002fdddb254267d42a3810cfea669d75700372f2",
    files_sha256_digest="67ecd146f49c290c20e97387bb8ef478817bd57ba6ad3c4a18256281f6ac2dbc",
    files_count=390,
    corpus_tar_sha256="de8b70faa7ab5267628d6f488811ead48a6c088c1880872e61ec85a2bbd233f8",
    counts={
        "V": (18, 1), "VP": (9, 0), "C": (18, 1), "US": (9, 1), "UF": (10, 1),
        "UP": (7, 0), "X": (7, 0), "L": (21, 1), "LIT": (7, 0), "W": (7, 1),
        "P": (9, 1),
    },
)


def pins_record(pins: Pins) -> dict:
    record = dataclasses.asdict(pins)
    record["counts"] = {k: list(v) for k, v in sorted(pins.counts.items())}
    return record


class Refusal(Exception):
    """A precondition failed: nothing is scored."""

    def __init__(self, check: str, detail: str):
        super().__init__(f"{check}: {detail}")
        self.check = check
        self.detail = detail


# ── small utilities ──────────────────────────────────────────────────────────

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def dump_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2) + "\n"


def dump_line(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True) + "\n"


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def git_tree_hash(directory: Path) -> str | None:
    """Git tree object id of ``directory`` as checked-in source.

    ``__pycache__`` directories are skipped; every other entry counts.
    Empty directories are omitted, as git cannot record them. Symlinks and
    special files are refused. (Same definition as the M4 harness.)
    """
    entries: list[tuple[bytes, bytes]] = []
    for child in directory.iterdir():
        name = child.name.encode("utf-8")
        mode = child.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise Refusal("mneme_tree", f"symlink in imported package: {child}")
        if stat.S_ISDIR(mode):
            if child.name == "__pycache__":
                continue
            sub = git_tree_hash(child)
            if sub is None:
                continue
            entries.append((name + b"/", b"40000 " + name + b"\0" + bytes.fromhex(sub)))
        elif stat.S_ISREG(mode):
            data = child.read_bytes()
            blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
            executable = os.name != "nt" and bool(mode & stat.S_IXUSR)
            file_mode = b"100755" if executable else b"100644"
            entries.append((name, file_mode + b" " + name + b"\0" + bytes.fromhex(blob)))
        else:
            raise Refusal("mneme_tree", f"special file in imported package: {child}")
    if not entries:
        return None
    entries.sort(key=lambda entry: entry[0])
    body = b"".join(entry[1] for entry in entries)
    return hashlib.sha1(b"tree %d\0" % len(body) + body).hexdigest()


def _safe_relative(text: Any, what: str) -> PurePosixPath:
    if not isinstance(text, str) or not text:
        raise ValueError(f"{what}: not a non-empty string")
    if "\\" in text:
        raise ValueError(f"{what}: path uses a backslash")
    path = PurePosixPath(text)
    if path.is_absolute() or re.match(r"^[A-Za-z]:", text):
        raise ValueError(f"{what}: absolute path")
    parts = [p for p in path.parts if p != "."]
    if not parts or ".." in parts:
        raise ValueError(f"{what}: path escapes its root")
    return PurePosixPath(*parts)


def _native(path: PurePosixPath | str) -> str:
    """A forward-slash relative path in this platform's separator form."""
    text = str(path)
    return str(PureWindowsPath(text)) if os.name == "nt" else text


def _rmtree(path: Path) -> None:
    def onerror(func, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            pass

    if os.path.lexists(path):
        shutil.rmtree(path, onerror=onerror)
    if os.path.lexists(path):
        raise OSError(f"could not remove {path}")


# ── interpreters and builds ──────────────────────────────────────────────────

_PROBE = r"""
import importlib.metadata, json, locale, os, platform, sys
import mneme
try:
    dist = importlib.metadata.version("mneme-hq")
except importlib.metadata.PackageNotFoundError:
    dist = None
print(json.dumps({
    "implementation": platform.python_implementation(),
    "version": platform.python_version(),
    "executable": sys.executable,
    "mneme_dir": os.path.dirname(os.path.abspath(mneme.__file__)),
    "mneme_version": getattr(mneme, "__version__", None),
    "distribution_version": dist,
    "preferred_encoding": locale.getpreferredencoding(False),
    "filesystem_encoding": sys.getfilesystemencoding(),
    "platform": platform.platform(),
}, sort_keys=True))
"""

_PASSTHROUGH = (
    "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS",
    "LANG", "LC_ALL", "LC_CTYPE",
)


def base_env(python: str, scratch: Path, import_path: str | None = None) -> dict[str, str]:
    """The constructed child environment: nothing else passes through.

    ``import_path`` is for the harness's own tests only (a source checkout in
    place of an installed wheel); ``score`` never sets it.
    """
    env = {name: os.environ[name] for name in _PASSTHROUGH if name in os.environ}
    path = [str(Path(python).parent)]
    if os.name == "nt":
        root = os.environ.get("SYSTEMROOT", r"C:\Windows")
        path.append(os.path.join(root, "System32"))
    else:
        path.extend(["/usr/bin", "/bin"])
    env["PATH"] = os.pathsep.join(path)
    tmp = scratch / "tmp"
    home = scratch / "home"
    env.update({"TEMP": str(tmp), "TMP": str(tmp), "TMPDIR": str(tmp),
                "HOME": str(home), "USERPROFILE": str(home)})
    if import_path:
        env["PYTHONPATH"] = import_path
    return env


def run_process(argv: list[str], *, cwd: Path, env: dict[str, str],
                stdin: bytes = b"", timeout: float = CHILD_TIMEOUT_S) -> dict:
    """Run one child; capture raw bytes. Launch failure and timeout are recorded."""
    try:
        proc = subprocess.run(argv, input=stdin, capture_output=True, cwd=str(cwd),
                              env=env, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"launched": True, "timed_out": True, "exit": None,
                "stdout": b"", "stderr": b""}
    except OSError as exc:
        return {"launched": False, "timed_out": False, "exit": None, "stdout": b"",
                "stderr": f"{type(exc).__name__}".encode("ascii")}
    return {"launched": True, "timed_out": False, "exit": proc.returncode,
            "stdout": proc.stdout, "stderr": proc.stderr}


def probe_interpreter(python: str, scratch: Path) -> dict:
    scratch.mkdir(parents=True, exist_ok=True)
    env = base_env(python, scratch)
    for key in ("tmp", "home"):
        (scratch / key).mkdir(exist_ok=True)
    result = run_process([python, "-I", "-c", _PROBE], cwd=scratch, env=env)
    if result["exit"] != 0:
        raise Refusal("interpreter", f"{python}: probe failed (exit {result['exit']})")
    probe = json.loads(result["stdout"].decode("utf-8"))
    freeze = run_process([python, "-I", "-m", "pip", "freeze", "--all"],
                         cwd=scratch, env=env)
    probe["pip_freeze_sha256"] = (
        sha256_bytes(freeze["stdout"]) if freeze["exit"] == 0 else None)
    return probe


def _urlsafe_sha256(data: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


def verify_wheel_install(probe: dict, wheel: Path, what: str) -> dict:
    """The imported ``mneme/`` is exactly the wheel's ``mneme/`` files."""
    if not wheel.is_file():
        raise Refusal(what, f"wheel {wheel} not found")
    mneme_dir = Path(probe["mneme_dir"])
    site = mneme_dir.parent
    recorded: set[str] = set()
    with zipfile.ZipFile(wheel) as archive:
        records = [n for n in archive.namelist() if n.endswith(".dist-info/RECORD")]
        if len(records) != 1:
            raise Refusal(what, "wheel has no single RECORD")
        for row in archive.read(records[0]).decode("utf-8").splitlines():
            path, _, rest = row.partition(",")
            digest, _, _ = rest.partition(",")
            if not path.startswith("mneme/"):
                continue
            if not digest.startswith("sha256="):
                raise Refusal(what, f"RECORD entry without sha256: {path}")
            recorded.add(path)
            try:
                actual = _urlsafe_sha256((site / PurePosixPath(path)).read_bytes())
            except OSError as exc:
                raise Refusal(what, f"installed file missing: {path}") from exc
            if actual != digest[len("sha256="):]:
                raise Refusal(what, f"installed {path} differs from the wheel")
    for file in mneme_dir.rglob("*"):
        if "__pycache__" in file.parts or not file.is_file():
            continue
        rel = file.relative_to(site).as_posix()
        if rel not in recorded:
            raise Refusal(what, f"installed file not in the wheel: {rel}")
    return {"wheel": wheel.name, "wheel_sha256": sha256_file(wheel),
            "wheel_files_verified": len(recorded)}


def verify_builds(impl_python: str, impl_wheel: Path, base_python: str, base_wheel: Path,
                  scratch: Path, pins: Pins) -> dict:
    builds = {}
    for name, python, wheel, tree in (
        ("implementation", impl_python, impl_wheel, pins.impl_tree),
        ("baseline", base_python, base_wheel, pins.baseline_tree),
    ):
        probe = probe_interpreter(python, scratch / f"probe-{name}")
        if probe["implementation"] != "CPython" or probe["version"] != pins.python_version:
            raise Refusal(name, f"interpreter is {probe['implementation']} "
                                f"{probe['version']}, pinned CPython {pins.python_version}")
        observed_tree = git_tree_hash(Path(probe["mneme_dir"]))
        if observed_tree != tree:
            raise Refusal(name, f"mneme/ tree {observed_tree}, pinned {tree}")
        probe["mneme_tree"] = observed_tree
        probe.update(verify_wheel_install(probe, wheel, name))
        builds[name] = probe
    if os.path.normcase(builds["implementation"]["mneme_dir"]) == os.path.normcase(
            builds["baseline"]["mneme_dir"]):
        raise Refusal("builds", "implementation and baseline import the same mneme/")
    return builds


# ── symlink capability (G2V-F2) ──────────────────────────────────────────────

def probe_symlinks(directory: Path) -> dict:
    """Create a file link, a directory link and a dangling link, and read them back."""
    directory.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="g2h-symlink-", dir=str(directory)))
    result = {"capable": False, "error": None}
    try:
        (work / "file").write_bytes(b"x")
        (work / "dir").mkdir()
        os.symlink("file", work / "file-link")
        os.symlink("dir", work / "dir-link", target_is_directory=True)
        os.symlink("missing", work / "dangling-link")
        ok = (
            os.readlink(work / "file-link") == "file"
            and (work / "file-link").read_bytes() == b"x"
            and (work / "dir-link").is_dir() and (work / "dir-link").is_symlink()
            and (work / "dangling-link").is_symlink()
            and not (work / "dangling-link").exists()
        )
        result["capable"] = bool(ok)
        if not ok:
            result["error"] = "links created but did not read back as links"
    except OSError as exc:
        result["error"] = f"{type(exc).__name__}: {getattr(exc, 'winerror', None) or exc.errno}"
    finally:
        _rmtree(work)
    return result


# ── corpus ───────────────────────────────────────────────────────────────────

_FILES_LINE = re.compile(r"^([0-9a-f]{64}) [ *](.+)$")


def parse_files_sha256(text: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        match = _FILES_LINE.match(line)
        if match is None:
            raise Refusal("files_sha256", f"unparseable line {number}")
        try:
            rel = _safe_relative(match.group(2), "files_sha256").as_posix()
        except ValueError as exc:
            raise Refusal("files_sha256", str(exc)) from exc
        if rel in seen:
            raise Refusal("files_sha256", f"duplicate entry {rel!r}")
        seen.add(rel)
        entries.append((match.group(1), rel))
    return entries


def corpus_regular_files(root: Path) -> tuple[list[str], list[str]]:
    regular: list[str] = []
    other: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        for name in list(dirnames):
            if (base / name).is_symlink():
                other.append((base / name).relative_to(root).as_posix())
                dirnames.remove(name)
        for name in filenames:
            path = base / name
            rel = path.relative_to(root).as_posix()
            (regular if stat.S_ISREG(path.lstat().st_mode) else other).append(rel)
    return sorted(regular), sorted(other)


def _no_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def load_json_bytes(data: bytes) -> Any:
    return json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)


@dataclasses.dataclass
class Case:
    case_id: str
    klass: str
    public_smoke: bool
    case: dict
    expected: dict
    envelope_text: str
    problems: list


def load_case(root: Path, case_id: str) -> Case:
    """Read one case. A malformed case is kept and fails G8, never dropped."""
    base = root / "cases" / case_id
    problems: list[str] = []
    case: dict = {}
    expected: dict = {}
    envelope_text = ""
    try:
        case = load_json_bytes((base / "case.json").read_bytes())
    except (OSError, ValueError) as exc:
        problems.append(f"case.json unreadable ({type(exc).__name__})")
    try:
        expected = load_json_bytes((base / "expected.json").read_bytes())
    except (OSError, ValueError) as exc:
        problems.append(f"expected.json unreadable ({type(exc).__name__})")
    envelope_name = case.get("envelope_file", "envelope.json") if isinstance(case, dict) else "envelope.json"
    try:
        envelope_text = (base / _safe_relative(envelope_name, "envelope_file")).read_bytes().decode("utf-8")
    except (OSError, ValueError) as exc:
        problems.append(f"envelope unreadable ({type(exc).__name__})")
    if not isinstance(case, dict) or not isinstance(expected, dict):
        problems.append("case.json or expected.json is not an object")
        case, expected = {}, {}
    if case and case.get("schema") != CASE_SCHEMA:
        problems.append("case.json schema")
    if case and case.get("case_id") != case_id:
        problems.append("case.json case_id")
    for key in EXPECTED_KEYS:
        if key not in expected:
            problems.append(f"expected.json missing {key}")
    if expected and expected.get("case_id") != case_id:
        problems.append("expected.json case_id")
    klass = expected.get("class")
    if klass not in CLASSES:
        problems.append("expected.json class")
    if expected.get("target_after_hook") not in TARGET_AFTER and "target_after_hook" in expected:
        problems.append("expected.json target_after_hook")
    return Case(case_id=case_id, klass=klass if klass in CLASSES else "?",
                public_smoke=expected.get("public_smoke") is True,
                case=case, expected=expected, envelope_text=envelope_text,
                problems=problems)


def case_index_findings(root: Path, cases: list[Case]) -> list[str]:
    """Cross-check CASE_INDEX.json and PUBLIC_SMOKE.json; findings only.

    LAYOUT.md names the index's content but not its exact shape, so an
    unrecognized shape is reported, never a reason to drop or rescore.
    """
    findings: list[str] = []
    by_id = {c.case_id: c for c in cases}
    try:
        index = load_json_bytes((root / "CASE_INDEX.json").read_bytes())
    except (OSError, ValueError):
        return ["CASE_INDEX.json unreadable"]
    rows: list[dict] | None = None
    if isinstance(index, dict) and isinstance(index.get("cases"), list):
        rows = index["cases"]
    elif isinstance(index, list):
        rows = index
    elif isinstance(index, dict) and all(isinstance(v, dict) for v in index.values()):
        rows = [dict(v, case_id=k) for k, v in index.items()]
    if rows is None or not all(isinstance(r, dict) for r in rows):
        findings.append("CASE_INDEX.json shape not recognized")
    else:
        listed = {r.get("case_id"): r for r in rows}
        if set(listed) != set(by_id):
            findings.append("CASE_INDEX.json case set differs from cases/")
        for case_id, row in sorted(listed.items(), key=lambda kv: str(kv[0])):
            case = by_id.get(case_id)
            if case is None:
                continue
            if "class" in row and row["class"] != case.klass:
                findings.append(f"{case_id}: CASE_INDEX class differs from expected.json")
            if "public_smoke" in row and bool(row["public_smoke"]) != case.public_smoke:
                findings.append(f"{case_id}: CASE_INDEX public_smoke differs")
    try:
        smoke = load_json_bytes((root / "PUBLIC_SMOKE.json").read_bytes())
        ids = smoke.get("public_smoke_case_ids") if isinstance(smoke, dict) else None
        if not isinstance(ids, list):
            findings.append("PUBLIC_SMOKE.json shape not recognized")
        elif sorted(ids) != sorted(c.case_id for c in cases if c.public_smoke):
            findings.append("PUBLIC_SMOKE.json differs from expected.json public_smoke flags")
    except (OSError, ValueError):
        findings.append("PUBLIC_SMOKE.json unreadable")
    return findings


def verify_corpus(root: Path, pins: Pins, corpus_tar: Path | None) -> tuple[dict, list[Case]]:
    files = root / "FILES.sha256"
    if not files.is_file():
        raise Refusal("corpus", f"{files} not found")
    digest = sha256_file(files)
    if digest != pins.files_sha256_digest:
        raise Refusal("files_sha256", f"digest {digest}, pinned {pins.files_sha256_digest}")
    entries = parse_files_sha256(files.read_text(encoding="utf-8"))
    if len(entries) != pins.files_count:
        raise Refusal("files_sha256", f"{len(entries)} entries, pinned {pins.files_count}")
    failures = []
    for expected_digest, rel in entries:
        path = root / PurePosixPath(rel)
        try:
            if not stat.S_ISREG(path.lstat().st_mode) or sha256_file(path) != expected_digest:
                failures.append(rel)
        except OSError:
            failures.append(rel)
    if failures:
        raise Refusal("files_sha256", f"{len(failures)} of {len(entries)} entries fail")
    regular, other = corpus_regular_files(root)
    listed = sorted([rel for _, rel in entries] + ["FILES.sha256"])
    if regular != listed or other:
        raise Refusal("corpus_layout", "corpus files differ from FILES.sha256 "
                                       f"({len(regular)} regular, {len(other)} other)")
    record = {"files_sha256_digest": digest, "files_verified": len(entries)}
    if corpus_tar is not None:
        tar_digest = sha256_file(corpus_tar)
        if tar_digest != pins.corpus_tar_sha256:
            raise Refusal("corpus_tar", f"digest {tar_digest}, pinned {pins.corpus_tar_sha256}")
        record["corpus_tar_sha256"] = tar_digest
    case_ids = sorted(p.name for p in (root / "cases").iterdir() if p.is_dir())
    if not case_ids or not all(re.fullmatch(r"g2h-[0-9a-f]{10}", c) for c in case_ids):
        raise Refusal("corpus_layout", "cases/ holds a directory that is not a case id")
    cases = [load_case(root, case_id) for case_id in case_ids]
    observed: dict[str, list[int]] = {k: [0, 0] for k in pins.counts}
    for case in cases:
        if case.klass in observed:
            observed[case.klass][1 if case.public_smoke else 0] += 1
    expected_counts = {k: list(v) for k, v in pins.counts.items()}
    unknown = sum(1 for c in cases if c.klass not in pins.counts)
    if observed != expected_counts or unknown:
        raise Refusal("counts", f"class counts {observed} (+{unknown} unclassified), "
                                f"pinned {expected_counts}")
    record["counts"] = {k: v for k, v in sorted(observed.items())}
    record["case_index_findings"] = case_index_findings(root, cases)
    return record, cases


# ── one case: fixture, memory, hook, checker ─────────────────────────────────

class CaseFailure(Exception):
    """A scoring-process failure for one case (G8)."""


def substitute_envelope(text: str, ws: Path, repo: Path) -> str:
    """Replace the placeholders inside JSON string values, JSON-escaped.

    The raw text is edited, so every other byte of the envelope, including
    escaped CR, BOM and lone-surrogate content, reaches the hook unchanged.
    """
    out = text.replace("{{WS}}", json.dumps(str(ws))[1:-1])
    out = out.replace("{{REPO}}", json.dumps(str(repo))[1:-1])
    if "{{" in out and re.search(r"\{\{[A-Z_]+\}\}", out):
        raise CaseFailure("envelope has an unknown placeholder")
    return out


def substitute_value(value: str, ws: Path, repo: Path) -> str:
    return value.replace("{{WS}}", str(ws)).replace("{{REPO}}", str(repo))


def materialize(case: Case, ws: Path, repo: Path, memory_bytes: bytes | None) -> None:
    fixture = case.case.get("fixture")
    if not isinstance(fixture, dict):
        raise CaseFailure("fixture missing")
    ws.mkdir(parents=True)
    repo.mkdir()
    for key, base in (("repo_dirs", repo), ("workspace_dirs", ws)):
        for rel in fixture.get(key) or []:
            (base / _native(_safe_relative(rel, key))).mkdir(parents=True, exist_ok=True)
    for entry in fixture.get("repo_files") or []:
        data = base64.b64decode(entry["bytes_b64"], validate=True)
        if sha256_bytes(data) != entry.get("sha256") or len(data) != entry.get("size"):
            raise CaseFailure("repo file bytes do not match their sha256/size")
        path = repo / _native(_safe_relative(entry["path"], "repo_files"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    for entry in fixture.get("repo_symlinks") or []:
        link = repo / _native(_safe_relative(entry["path"], "repo_symlinks"))
        target = entry["target"]
        if not isinstance(target, str) or not target:
            raise CaseFailure("symlink target is not a string")
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(_native(target), link, target_is_directory=bool(entry.get("directory")))
        except OSError as exc:
            raise CaseFailure(f"symlink could not be created ({type(exc).__name__}); "
                              "G2V-F2: the run is INCOMPLETE") from exc
    if memory_bytes is not None:
        memory = repo / ".mneme" / "project_memory.json"
        memory.parent.mkdir(parents=True, exist_ok=True)
        memory.write_bytes(memory_bytes)


def typed_rules_of(memory: dict) -> tuple[list[str], list[str]]:
    ids: list[str] = []
    rules: list[str] = []
    for decision in memory.get("decisions") or []:
        ids.append(decision.get("id"))
        for rule in decision.get("rules") or []:
            rules.append(dump_line({
                "decision": decision.get("id"), "type": rule.get("type"),
                "value": rule.get("value"),
                "include_paths": list(rule.get("include_paths") or []),
                "exclude_paths": list(rule.get("exclude_paths") or []),
            }))
    return sorted(ids), sorted(rules)


def expected_typed_rules(spec: dict) -> tuple[list[str], list[str]]:
    rules = []
    for rule in spec.get("expected_typed_rules") or []:
        value = rule.get("canonical_value") if "canonical_value" in rule else rule.get("value")
        rules.append(dump_line({
            "decision": rule.get("decision"), "type": rule.get("type"), "value": value,
            "include_paths": list(rule.get("include_paths") or []),
            "exclude_paths": list(rule.get("exclude_paths") or []),
        }))
    return sorted(spec.get("expected_decision_ids") or []), sorted(rules)


def build_memory(case: Case, impl_python: str, ws: Path, repo: Path,
                 scratch: Path, import_path: str | None = None) -> tuple[bytes | None, dict]:
    """LAYOUT step 2: compile docs/adr with the build under test; check it."""
    spec = case.case["fixture"].get("memory")
    if spec is None:
        return None, {"built": False}
    rel = _safe_relative(spec.get("path", ".mneme/project_memory.json"), "memory.path")
    if rel.as_posix() != ".mneme/project_memory.json":
        raise CaseFailure("memory.path is not .mneme/project_memory.json")
    memory = repo / _native(rel)
    env = base_env(impl_python, scratch, import_path)
    steps = [[impl_python, "-m", "mneme", "init", "--path", str(memory)]]
    if (repo / "docs" / "adr").is_dir():
        steps.append([impl_python, "-m", "mneme", "adr", "import", str(repo / "docs" / "adr"),
                      "--memory", str(memory), "--apply"])
    for argv in steps:
        result = run_process(argv, cwd=repo, env=env)
        if result["exit"] != 0:
            raise CaseFailure(f"memory build failed ({argv[3]}: exit {result['exit']})")
    data = memory.read_bytes()
    ids, rules = typed_rules_of(load_json_bytes(data))
    want_ids, want_rules = expected_typed_rules(spec)
    if ids != want_ids or rules != want_rules:
        raise CaseFailure("compiled memory does not match expected_typed_rules / decision ids")
    return data, {"built": True, "decision_ids": ids,
                  "typed_rules": [json.loads(r) for r in rules]}


def target_path_of(case: Case, ws: Path, repo: Path) -> Path:
    target = case.case.get("target") or {}
    base = {"REPO": repo, "WS": ws}.get(target.get("base"))
    if base is None:
        raise CaseFailure("target.base is not REPO or WS")
    return base / _native(_safe_relative(target.get("relative"), "target.relative"))


def target_state(path: Path) -> dict:
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return {"exists": False}
    except OSError as exc:
        return {"exists": None, "error": type(exc).__name__}
    state: dict = {"exists": True}
    if stat.S_ISLNK(st.st_mode):
        state["kind"] = "link"
        state["link_text"] = os.readlink(path)
        try:
            data = Path(path).read_bytes()
            state["referent"] = {"exists": True, "sha256": sha256_bytes(data)}
        except FileNotFoundError:
            state["referent"] = {"exists": False}
        except OSError as exc:
            state["referent"] = {"exists": None, "error": type(exc).__name__}
    elif stat.S_ISREG(st.st_mode):
        state["kind"] = "file"
        state["sha256"] = sha256_file(Path(path))
    elif stat.S_ISDIR(st.st_mode):
        state["kind"] = "dir"
    else:
        state["kind"] = "other"
    return state


def _read_jsonl(path: Path) -> tuple[list, str | None]:
    if not path.exists():
        return [], None
    data = path.read_bytes()
    records = []
    for line in data.decode("utf-8", "replace").splitlines():
        if line.strip():
            try:
                records.append(json.loads(line))
            except ValueError:
                records.append({"unparseable_line": True})
    return records, sha256_bytes(data)


def observed_disposition(exit_code: int | None, stdout: bytes) -> str | None:
    if exit_code == 2:
        return "refused"
    if exit_code != 0:
        return "error" if exit_code is not None else None
    for line in stdout.decode("utf-8", "replace").splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        hso = obj.get("hookSpecificOutput") if isinstance(obj, dict) else None
        if isinstance(hso, dict) and hso.get("permissionDecision") == "defer":
            return "deferred"
    return "proceeded"


@dataclasses.dataclass(frozen=True)
class Context:
    impl_python: str
    base_python: str
    host_version: str
    host_sha256: str
    work: Path  # the per-pass working root: <run root>/w
    import_path: str | None = None  # tests only; see base_env


def _fresh(path: Path) -> None:
    _rmtree(path)
    path.mkdir(parents=True)


def run_hook(case: Case, ctx: Context, python: str, memory_bytes: bytes | None) -> dict:
    """One hook run on a fresh fixture copy (LAYOUT steps 3-5)."""
    ws, repo, scratch = ctx.work / "ws", ctx.work / "ws" / "repo", ctx.work / "scratch"
    _rmtree(ws)
    _fresh(scratch)
    for name in ("tmp", "home"):
        (scratch / name).mkdir()
    materialize(case, ws, repo, memory_bytes)
    envelope = substitute_envelope(case.envelope_text, ws, repo)
    target = target_path_of(case, ws, repo)
    evidence_log = scratch / "evidence.jsonl"
    observe_log = scratch / "observe.jsonl"
    hook = case.case.get("hook") or {}
    env = base_env(python, scratch)
    env.update({
        "PYTHONPATH": os.pathsep.join(p for p in (str(SHIM_DIR), ctx.import_path) if p),
        "MNEME_G2H_OBSERVE_LOG": str(observe_log),
        "MNEME_HOOK_MODE": hook.get("mode"),
        "MNEME_HOOK_EVIDENCE_LOG": str(evidence_log),
        "MNEME_HOOK_EVIDENCE_HOST_VERSION": ctx.host_version,
        "MNEME_HOOK_EVIDENCE_HOST_SHA256": ctx.host_sha256,
    })
    for key, value in (hook.get("extra_env") or {}).items():
        env[str(key)] = substitute_value(str(value), ws, repo)
    cwd_value = json.loads(envelope).get("cwd")
    cwd = Path(cwd_value) if isinstance(cwd_value, str) and os.path.isdir(cwd_value) else ws
    before = target_state(target)
    result = run_process([python, "-m", HOOK_MODULE], cwd=cwd, env=env,
                         stdin=envelope.encode("utf-8"))
    after = target_state(target)
    evidence, evidence_sha = _read_jsonl(evidence_log)
    invocations, _ = _read_jsonl(observe_log)
    if not result["launched"]:
        raise CaseFailure("hook could not be launched")
    if result["timed_out"]:
        raise CaseFailure("hook timed out")
    return {
        "exit": result["exit"],
        "stdout_b64": b64(result["stdout"]), "stdout_sha256": sha256_bytes(result["stdout"]),
        "stderr_b64": b64(result["stderr"]), "stderr_sha256": sha256_bytes(result["stderr"]),
        "disposition": observed_disposition(result["exit"], result["stdout"]),
        "cwd": "envelope" if cwd != ws else "workspace",
        "target_before": before, "target_after": after,
        "evidence_records": evidence, "evidence_log_sha256": evidence_sha,
        "invocations": invocations,
    }


def run_checker_pair(case: Case, ctx: Context, memory_bytes: bytes | None) -> dict:
    """G5 checker level: ``--proposed-new-file`` against ``--input``, same carrier."""
    ws, repo, scratch = ctx.work / "ws", ctx.work / "ws" / "repo", ctx.work / "scratch"
    _rmtree(ws)
    _fresh(scratch)
    for name in ("tmp", "home"):
        (scratch / name).mkdir()
    materialize(case, ws, repo, memory_bytes)
    envelope = json.loads(substitute_envelope(case.envelope_text, ws, repo))
    tool_input = envelope.get("tool_input") or {}
    content = tool_input.get("content")
    file_path = tool_input.get("file_path")
    if not isinstance(content, str) or not isinstance(file_path, str):
        raise CaseFailure("checker pair: envelope has no content or file_path")
    try:
        carrier_bytes = content.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CaseFailure("checker pair: content is not encodable, no carrier") from exc
    carrier = scratch / "carrier.txt"
    carrier.write_bytes(carrier_bytes)
    target = file_path
    if not Path(target).is_absolute() and envelope.get("cwd"):
        target = str(Path(envelope["cwd"]) / target)
    memory = repo / ".mneme" / "project_memory.json"
    mode = (case.case.get("hook") or {}).get("mode")
    cwd_value = envelope.get("cwd")
    cwd = Path(cwd_value) if isinstance(cwd_value, str) and os.path.isdir(cwd_value) else ws
    env = base_env(ctx.impl_python, scratch, ctx.import_path)
    pair = {}
    for flag, key in (("--proposed-new-file", "proposed"), ("--input", "input")):
        argv = [ctx.impl_python, "-m", "mneme", "check", "--memory", str(memory),
                flag, str(carrier), "--query", f"edit to {file_path}", "--mode", mode,
                "--json", "--target-path", target]
        result = run_process(argv, cwd=cwd, env=env)
        if not result["launched"] or result["timed_out"]:
            raise CaseFailure(f"checker pair: {key} run did not complete")
        pair[key] = {"exit": result["exit"], "stdout_b64": b64(result["stdout"]),
                     "stdout_sha256": sha256_bytes(result["stdout"]),
                     "stderr_sha256": sha256_bytes(result["stderr"])}
    pair["carrier_sha256"] = sha256_bytes(carrier_bytes)
    return pair


def envelope_facts(case: Case, ws: Path, repo: Path) -> dict:
    envelope = json.loads(substitute_envelope(case.envelope_text, ws, repo))
    tool_input = envelope.get("tool_input") or {}
    content = tool_input.get("content")
    digest = None
    if isinstance(content, str):
        try:
            digest = sha256_bytes(content.encode("utf-8"))
        except UnicodeEncodeError:
            digest = None
    return {
        "file_path": tool_input.get("file_path"),
        "cwd": envelope.get("cwd"),
        "tool_name": envelope.get("tool_name"),
        "identifiers": {k: v for k, v in envelope.items()
                        if isinstance(k, str) and k.endswith("_id") and isinstance(v, str)},
        "content_sha256": digest,
        "content_has_cr": isinstance(content, str) and "\r" in content,
    }


def checker_parity_applies(case: Case) -> bool:
    e = case.expected
    return (case.klass in CHECKER_PARITY_CLASSES and e.get("hook_routed") is True) \
        or e.get("parity_with_input_carrier") is True


def hook_parity_applies(case: Case, has_cr: bool) -> bool:
    """G5 hook level. Labels may add cases; the routed-CR exception overrides
    every addition (revision 2, G2H-F3). Checker-level parity is separate."""
    e = case.expected
    if e.get("hook_routed") is True and has_cr:
        return False
    return case.klass in HOOK_PARITY_CLASSES or e.get("parity_with_baseline_hook") is True \
        or e.get("expected_from_baseline") is True


def expects_block(case: Case) -> bool:
    """G1(a) (revision 2, G2V-F1; G2H-F2, G2H-F4), in this order:

    1. every strict V and VP case must block. This class-level safety gate is
       checked first, and no label, ``expected_from_baseline`` included, can
       switch it off;
    2. every case of any class whose labels explicitly expect a block (exit 2
       or a refusal) must block, whatever else its labels say.

    The A1.4 exemption needs no rule of its own. A genuine legacy-error case
    has its outcome observed from the baseline (``observed_from_baseline``),
    so it carries no block expectation and falls through to False. It never
    suppresses (1) or (2).
    """
    e = case.expected
    if case.klass in ("V", "VP") and e.get("hook_mode") == "strict":
        return True
    return e.get("hook_exit") == 2 or e.get("hook_disposition") == "refused" \
        or e.get("evidence_hook_outcome") == "refused"


def execute_case(case: Case, ctx: Context) -> dict:
    """Run one case; every scoring-process failure is recorded, never raised."""
    obs: dict = {"schema": CASE_RECORD_SCHEMA, "case_id": case.case_id, "class": case.klass,
                 "public_smoke": case.public_smoke, "operational_failures": list(case.problems)}
    if case.problems:
        return obs
    ws, repo = ctx.work / "ws", ctx.work / "ws" / "repo"
    try:
        obs["envelope"] = envelope_facts(case, ws, repo)
        _rmtree(ws)
        scratch = ctx.work / "scratch"
        _fresh(scratch)
        for name in ("tmp", "home"):
            (scratch / name).mkdir()
        materialize(case, ws, repo, None)
        memory_bytes, obs["memory"] = build_memory(case, ctx.impl_python, ws, repo, scratch,
                                                   ctx.import_path)
        obs["implementation"] = run_hook(case, ctx, ctx.impl_python, memory_bytes)
        obs["baseline"] = run_hook(case, ctx, ctx.base_python, memory_bytes)
        if checker_parity_applies(case):
            obs["checker_pair"] = run_checker_pair(case, ctx, memory_bytes)
    except Exception as exc:  # any harness error is a G8 failure of this case, never a crash
        detail = str(exc) if isinstance(exc, CaseFailure) else type(exc).__name__
        obs["operational_failures"].append(detail)
    finally:
        try:
            _rmtree(ws)
            _rmtree(ctx.work / "scratch")
        except OSError:
            obs["operational_failures"].append("workspace could not be removed")
    return obs


# ── scoring ──────────────────────────────────────────────────────────────────

def _decision_of(rule_id: Any) -> str | None:
    return rule_id.split(":", 1)[0] if isinstance(rule_id, str) and ":" in rule_id else None


def checker_payloads(hook_obs: dict) -> list[dict]:
    payloads = []
    for inv in hook_obs.get("invocations") or []:
        try:
            payload = json.loads(inv.get("stdout") or "")
        except (ValueError, TypeError):
            payload = None
        payloads.append(payload if isinstance(payload, dict) else {})
    return payloads


def numeric_traces(hook_obs: dict) -> dict[str, list[dict]]:
    """decision id -> every FORBID_NUMERIC_ABOVE trace the hook's checker emitted."""
    traces: dict[str, list[dict]] = {}
    for payload in checker_payloads(hook_obs):
        for item in payload.get("applicability") or []:
            if isinstance(item, dict) and item.get("rule_type") == NUMERIC:
                traces.setdefault(_decision_of(item.get("rule_id")) or "?", []).append(item)
    return traces


def _resolved_normcase(path: str, cwd: Any) -> str:
    p = Path(path)
    if not p.is_absolute() and isinstance(cwd, str):
        p = Path(cwd) / p
    return os.path.normcase(str(p.resolve()))


def record_binding_problems(record: dict, facts: dict, host: tuple[str, str]) -> list[str]:
    """ADR-029 / charter §6.2 bindings of one evidence record (attribution aside)."""
    problems = []
    try:
        if record.get("surface") != EVIDENCE_SURFACE:
            problems.append("surface")
        if not _nonempty_str(record.get("mneme_version")):
            problems.append("mneme_version")
        rhost = record.get("host") or {}
        if (rhost.get("version"), rhost.get("executable_sha256")) != host:
            problems.append("host_identity")
        event = record.get("event") or {}
        if event.get("tool_name") != "Write" or facts["tool_name"] != "Write":
            problems.append("event.tool_name")
        if event.get("file_path") != facts["file_path"]:
            problems.append("event.file_path")
        if event.get("cwd") != facts["cwd"]:
            problems.append("event.cwd")
        if event.get("identifiers") != facts["identifiers"]:
            problems.append("event.identifiers")
        digest = facts["content_sha256"]
        if digest is None or record.get("carrier_sha256") != digest:
            problems.append("carrier_sha256")
        if record.get("hook_outcome") not in ("refused", "proceeded", "deferred"):
            problems.append("hook_outcome")
        checker = record.get("checker") or {}
        subject = checker.get("subject")
        if subject is not None:
            if checker.get("trusted") is not True:
                problems.append("checker.trusted")
            if subject.get("input_kind") != INPUT_KIND_PROPOSED:
                problems.append("subject.input_kind")
            if subject.get("subject_sha256") != digest:
                problems.append("subject.subject_sha256")
            if subject.get("absence_verified") is not True:
                problems.append("subject.absence_verified")
            target = subject.get("target_path")
            if not isinstance(target, str) or os.path.normcase(target) != _resolved_normcase(
                    facts["file_path"], facts["cwd"]):
                problems.append("subject.target_path")
        rules = record.get("rules")
        if not isinstance(rules, list):
            problems.append("rules")
            rules = []
        if rules and subject is None:
            problems.append("rules_without_subject")
        for rule in rules:
            if not (_nonempty_str(rule.get("rule_id")) and _nonempty_str(
                    rule.get("decision_version_id"))):
                problems.append("rule.identity")
            if rule.get("applicability") != "APPLIED":
                problems.append("rule.applicability")
            if subject is not None and rule.get("governed_path") != subject.get("governed_path"):
                problems.append("rule.governed_path")
            if rule.get("subject_sha256") != digest:
                problems.append("rule.subject_sha256")
            if not all(k in rule for k in ("matcher_status", "matcher_outcome", "primary_reason")):
                problems.append("rule.matcher_fields")
        if not isinstance(record.get("violations"), list):
            problems.append("violations")
    except (AttributeError, TypeError):
        problems.append("record_shape")
    return sorted(set(problems))


def scorer_relevance(record: dict, facts: dict, host: tuple[str, str],
                     mode: str) -> tuple[bool, dict[str, bool]]:
    """Amendment 1 A1.3, computed by the scorer from one record.

    A rule is relevant only with complete bindings and an outcome
    attributable to it: a recognized NO_VIOLATION that proceeded; a
    violation (RECOGNIZED, or PARTIAL with an established violation) that
    this rule's own reported violation refused (strict) or deferred (warn).
    MATCHER_UNEVALUATED, or a disposition caused only by another rule, is
    never relevant. The case value is the conjunction over its applied
    numeric rules, and false when it has none.
    """
    rules = record.get("rules") if isinstance(record.get("rules"), list) else []
    bound = not record_binding_problems(record, facts, host) and \
        (record.get("checker") or {}).get("subject") is not None
    outcome = record.get("hook_outcome")
    reported = {v.get("rule_id") for v in record.get("violations") or []
                if isinstance(v, dict) and v.get("rule_type") == NUMERIC}
    per_rule: dict[str, bool] = {}
    for rule in rules:
        decision = _decision_of(rule.get("rule_id")) or "?"
        status, result = rule.get("matcher_status"), rule.get("matcher_outcome")
        reason = rule.get("primary_reason")
        ok = False
        if bound:
            if status == "RECOGNIZED" and result == "NO_VIOLATION" and reason is None:
                ok = outcome == "proceeded" and rule.get("rule_id") not in reported
            elif result == "VIOLATION" and (
                    (status == "RECOGNIZED" and reason is None)
                    or (status == "PARTIAL" and isinstance(reason, str)
                        and reason != "INCOMPLETE_SOURCE_INPUT")):
                attributable = rule.get("rule_id") in reported
                ok = attributable and ((outcome == "refused" and mode == "strict")
                                       or (outcome == "deferred" and mode == "warn"))
        per_rule[decision] = per_rule.get(decision, True) and ok
    return (bool(per_rule) and all(per_rule.values())), per_rule


def expected_cause(e: dict) -> str | None:
    """The disposition cause a routed record should carry (see README, Q-CAUSE)."""
    outcome = e.get("evidence_hook_outcome")
    blocked_by = e.get("block_attributed_to") or []
    if outcome in ("refused", "deferred"):
        if "numeric" in blocked_by:
            return "numeric_violation"
        if "literal" in blocked_by:
            return "other_rule"
        return None
    if outcome == "proceeded":
        incomplete = any(
            isinstance(r, dict) and r.get("applicability") == "APPLIED"
            and r.get("matcher_status") in ("MATCHER_UNEVALUATED", "PARTIAL")
            for r in (e.get("numeric_rules") or {}).values())
        return "fail_open" if incomplete else "no_violation"
    return None


def _strip_traceback_frames(text: str) -> list[str]:
    """A1.4 diagnostic: drop traceback frame lines, keep everything else."""
    out = []
    lines = text.splitlines()
    skip_source = False
    for line in lines:
        if re.match(r'^\s*File ".*", line \d+', line):
            skip_source = True
            continue
        if skip_source and (line.startswith("    ") or re.match(r"^\s*[~^]+\s*$", line)):
            continue
        skip_source = False
        out.append(line)
    return out


TRACEBACK_HEADER = "Traceback (most recent call last):"
CHAIN_SEPARATORS = (
    "During handling of the above exception, another exception occurred:",
    "The above exception was the direct cause of the following exception:",
)


_SUMMARY_LINE = re.compile(rb"^[A-Za-z_][A-Za-z0-9_.]*(:( .*)?)?$")


def _bare(line: bytes) -> bytes:
    """A line without its line-ending bytes (for recognition only, never comparison)."""
    return line.rstrip(b"\r\n")


def parse_tracebacks(stderr: bytes) -> dict:
    """Split raw stderr bytes into traceback blocks and everything else (Amendment 2).

    Byte-preserving (G2H-F1): every kept line keeps its own line-ending bytes,
    so CRLF against LF, or a missing final newline, still compares unequal.

    A block starts at a line ``Traceback (most recent call last):`` and is
    complete only when it reaches its exception summary line: the first
    following line that is not indented and has the form ``ExceptionType`` or
    ``ExceptionType: message``. Only the lines strictly between the two (the
    frames) are dropped. The summary lines, the chain separators and every
    line outside a block are kept, in order. A block with no summary line is
    reported as ``incomplete`` and its lines are kept as non-traceback text.
    """
    summaries: list[bytes] = []
    separators: list[bytes] = []
    outside: list[bytes] = []
    pending: list[bytes] | None = None  # the lines of an open block
    incomplete = 0
    for line in stderr.splitlines(keepends=True):
        bare = _bare(line)
        if pending is not None:
            if bare[:1] in (b" ", b"\t") or bare == b"":
                pending.append(line)  # a frame line
                continue
            if _SUMMARY_LINE.match(bare):
                summaries.append(line)
                pending = None
                continue
            # Not a summary line: the block never completed.
            incomplete += 1
            outside.extend(pending)
            pending = None
        if bare == TRACEBACK_HEADER.encode("ascii"):
            pending = [line]
            continue
        if bare.decode("utf-8", "replace") in CHAIN_SEPARATORS:
            separators.append(line)
        outside.append(line)
    if pending is not None:
        incomplete += 1
        outside.extend(pending)
    return {"complete_blocks": len(summaries), "incomplete_blocks": incomplete,
            "summaries": summaries, "separators": separators, "outside": outside}


def a2_in_scope(base: dict) -> bool:
    """A2.1: the pinned baseline's own run exited nonzero with a complete traceback block.

    A truncated or otherwise incomplete block never brings a case into scope
    (G2H-F1); neither does a stderr that also holds an incomplete block.
    """
    if base.get("exit") in (0, None):
        return False
    parsed = parse_tracebacks(base64.b64decode(base["stderr_b64"]))
    return parsed["complete_blocks"] > 0 and parsed["incomplete_blocks"] == 0


def first_difference(a: bytes, b: bytes) -> int | None:
    """Offset of the first differing byte, or None when the streams are equal."""
    if a == b:
        return None
    for index, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return index
    return min(len(a), len(b))


def a2_compare(impl: dict, base: dict) -> dict:
    """A2.2 for a case in scope: everything but the frame lines, byte for byte."""
    impl_stderr = base64.b64decode(impl["stderr_b64"])
    base_stderr = base64.b64decode(base["stderr_b64"])
    impl_stdout = base64.b64decode(impl["stdout_b64"])
    base_stdout = base64.b64decode(base["stdout_b64"])
    mine, theirs = parse_tracebacks(impl_stderr), parse_tracebacks(base_stderr)
    failures = []
    if impl["exit"] in (0, None) or mine["complete_blocks"] == 0:
        failures.append("a2:current_build_did_not_raise")
    if mine["incomplete_blocks"]:
        failures.append("a2:incomplete_block")
    if impl_stdout != base_stdout:
        failures.append("a2:stdout")
    if impl["exit"] != base["exit"]:
        failures.append("a2:exit")
    if mine["summaries"] != theirs["summaries"]:
        failures.append("a2:exception_summaries")
    if mine["separators"] != theirs["separators"]:
        failures.append("a2:chain_separators")
    if mine["outside"] != theirs["outside"]:
        failures.append("a2:non_traceback_stderr")
    raw = {"stdout": impl_stdout == base_stdout, "stderr": impl_stderr == base_stderr,
           "exit": impl["exit"] == base["exit"]}
    return {
        "in_scope": True, "pass": not failures, "failures": failures,
        "raw_bytes_identical": all(raw.values()), "raw": raw,
        # Byte-exact evidence (A2.3): both raw streams and the first differing offset.
        "raw_bytes": {
            "implementation_stdout_b64": impl["stdout_b64"],
            "baseline_stdout_b64": base["stdout_b64"],
            "implementation_stderr_b64": impl["stderr_b64"],
            "baseline_stderr_b64": base["stderr_b64"],
            "stdout_first_difference_offset": first_difference(impl_stdout, base_stdout),
            "stderr_first_difference_offset": first_difference(impl_stderr, base_stderr),
        },
        # Readable extras only; the comparison above is on bytes.
        "text_stderr_diff": stderr_diagnostic(impl_stderr, base_stderr)["raw_diff"],
        "text_stdout_diff": list(difflib.unified_diff(
            base_stdout.decode("utf-8", "replace").splitlines(),
            impl_stdout.decode("utf-8", "replace").splitlines(),
            "baseline", "implementation", lineterm="")),
    }


def stderr_diagnostic(impl: bytes, base: bytes) -> dict:
    a = impl.decode("utf-8", "replace")
    b = base.decode("utf-8", "replace")
    diff = list(difflib.unified_diff(b.splitlines(), a.splitlines(), "baseline",
                                     "implementation", lineterm=""))
    return {"raw_diff": diff,
            "normalized_equal": _strip_traceback_frames(a) == _strip_traceback_frames(b),
            "gating": False}


def _target_label_ok(label: Any, before: dict, after: dict) -> bool:
    if label == "absent":
        return after.get("exists") is False
    if after != before:
        return False
    if label == "unchanged":
        return True
    if label == "unchanged_link_and_referent":
        return before.get("kind") == "link" and (before.get("referent") or {}).get("exists") is True
    if label == "unchanged_dangling_link":
        return before.get("kind") == "link" and (before.get("referent") or {}).get("exists") is False
    return False


def score_case(case: Case, obs: dict, host: tuple[str, str]) -> dict:
    """Every gate's verdict for one case. Missing observations fail closed."""
    e = case.expected
    gates: dict[str, dict] = {g: {"applies": False, "pass": True, "why": []} for g in GATES}

    def fail(gate: str, why: str) -> None:
        gates[gate]["pass"] = False
        gates[gate]["why"].append(why)

    gates["G8"]["applies"] = True
    for failure in obs.get("operational_failures") or []:
        fail("G8", "operational_failure")
    impl, base = obs.get("implementation"), obs.get("baseline")
    facts = obs.get("envelope") or {}
    if impl is None or base is None:
        if not obs.get("operational_failures"):
            fail("G8", "not_executed")
        for g in ("G1", "G2", "G3", "G4", "G5", "G6"):
            gates[g]["applies"] = True
            fail(g, "no_observation")
        return {"gates": gates, "diagnostics": {}}

    mode = e.get("hook_mode")
    traces = numeric_traces(impl)
    records = impl.get("evidence_records") or []
    relevance = [scorer_relevance(r, facts, host, mode) for r in records]
    # Q2: the case value is the conjunction; every rule's own result is kept.
    diagnostics: dict = {"relevance": [{"case": cv, "per_rule": dict(sorted(pr.items()))}
                                       for cv, pr in relevance]}

    # G1 unsafe pass (§5, G2V-F1).
    expected_block = expects_block(case)
    nonclean = {d for d, r in (e.get("numeric_rules") or {}).items() if isinstance(r, dict) and (
        r.get("matcher_outcome") in ("VIOLATION", "UNEVALUATED")
        or r.get("matcher_status") in ("PARTIAL", "MATCHER_UNEVALUATED"))}
    gates["G1"]["applies"] = True
    if expected_block and impl["exit"] != 2:
        fail("G1", "a:expected_block_not_refused")
    record_rules = {}
    for record in records:
        for rule in record.get("rules") or []:
            record_rules.setdefault(_decision_of(rule.get("rule_id")) or "?", []).append(rule)
    for decision in sorted(nonclean):
        seen = traces.get(decision, []) + record_rules.get(decision, [])
        if any(t.get("matcher_outcome") == "NO_VIOLATION" for t in seen):
            fail("G1", "b:nonclean_observed_no_violation")
    expected_reo = e.get("relevant_enforcement_observed")
    expected_per_rule = e.get("relevant_enforcement_observed_per_rule") or {}
    for case_value, per_rule in relevance:
        if case_value and expected_reo is not True:
            fail("G1", "c:unexpected_relevant_claim")
        if any(v and expected_per_rule.get(d) is not True for d, v in per_rule.items()):
            fail("G1", "c:unexpected_relevant_claim_per_rule")

    # G2 false block (§5; A1.4 excludes baseline-observed cases).
    if (case.klass in PROCEED_CLASSES and e.get("expected_from_baseline") is not True
            and e.get("literal_violation") is not True):
        gates["G2"]["applies"] = True
        if impl["exit"] == 2:
            fail("G2", "observed_exit_2")

    # G3 no mutation.
    gates["G3"]["applies"] = True
    before, after = impl["target_before"], impl["target_after"]
    if impl["exit"] == 2 and after.get("exists") is not False:
        fail("G3", "target_present_after_block")
    if after != before:
        fail("G3", "target_changed")
    if not _target_label_ok(e.get("target_after_hook"), before, after):
        fail("G3", "target_after_hook_label")

    # G4 reasons.
    if case.klass in REASON_CLASSES:
        gates["G4"]["applies"] = True
        for decision, rule in sorted((e.get("numeric_rules") or {}).items()):
            want = rule.get("primary_reason") if isinstance(rule, dict) else None
            if want is None:
                continue
            got = [t.get("primary_reason") for t in traces.get(decision, [])]
            if not got or any(g != want for g in got):
                fail("G4", "primary_reason")

    # G5 parity: hook level raw bytes, or Amendment 2 where the baseline raised;
    # checker level stdout + exit.
    if hook_parity_applies(case, bool(facts.get("content_has_cr"))):
        gates["G5"]["applies"] = True
        if a2_in_scope(base):
            diagnostics["amendment_2"] = a2_compare(impl, base)
            for why in diagnostics["amendment_2"]["failures"]:
                fail("G5", why)
        else:
            if impl["exit"] != base["exit"]:
                fail("G5", "hook_exit")
            if impl["stdout_sha256"] != base["stdout_sha256"]:
                fail("G5", "hook_stdout")
            if impl["stderr_sha256"] != base["stderr_sha256"]:
                fail("G5", "hook_stderr")
                diagnostics["stderr"] = stderr_diagnostic(
                    base64.b64decode(impl["stderr_b64"]), base64.b64decode(base["stderr_b64"]))
    if checker_parity_applies(case):
        gates["G5"]["applies"] = True
        pair = obs.get("checker_pair")
        if pair is None:
            fail("G5", "checker_pair_missing")
        else:
            if pair["proposed"]["exit"] != pair["input"]["exit"]:
                fail("G5", "checker_exit")
            if pair["proposed"]["stdout_sha256"] != pair["input"]["stdout_sha256"]:
                fail("G5", "checker_stdout")

    # G6 evidence (A1.1 restatement).
    gates["G6"]["applies"] = True
    if e.get("g2_evidence_record_expected") is True:
        if len(records) != 1:
            fail("G6", f"record_count_{min(len(records), 2)}")
        for record, (case_value, per_rule) in zip(records, relevance):
            for problem in record_binding_problems(record, facts, host):
                fail("G6", f"binding:{problem}")
            if record.get("hook_outcome") != impl["disposition"]:
                fail("G6", "hook_outcome_vs_observed")
            if record.get("hook_outcome") != e.get("evidence_hook_outcome"):
                fail("G6", "hook_outcome_vs_expected")
            disposition = record.get("disposition") or {}
            if disposition.get("mode") != mode:
                fail("G6", "mode")
            if disposition.get("cause") != expected_cause(e):
                fail("G6", "cause")
            if case_value is not (expected_reo is True):
                fail("G6", "relevant_enforcement_observed")
            want_rules = {d: v is True for d, v in expected_per_rule.items()}
            if per_rule != want_rules:
                fail("G6", "relevant_enforcement_observed_per_rule")
    elif records:
        fail("G6", "unexpected_record")

    diagnostics["conformance"] = label_conformance(case, obs, traces, records)
    return {"gates": gates, "diagnostics": diagnostics}


def label_conformance(case: Case, obs: dict, traces: dict, records: list) -> list[str]:
    """Labels not covered by a gate, compared for the record only (non-gating)."""
    e, impl = case.expected, obs["implementation"]
    out = []
    if isinstance(e.get("hook_exit"), int) and e["hook_exit"] != impl["exit"]:
        out.append("hook_exit")
    if e.get("hook_disposition") not in (None, "observed_from_baseline") and \
            e["hook_disposition"] != impl["disposition"]:
        out.append("hook_disposition")
    flags = [inv.get("input_flag") for inv in impl.get("invocations") or []]
    invoked = {"--proposed-new-file": "proposed_new_file", "--input": "input"}
    observed_invokes = "none" if not flags else (
        invoked.get(flags[0], "other") if len(flags) == 1 else "multiple")
    if e.get("hook_invokes") is not None and e["hook_invokes"] != observed_invokes:
        out.append("hook_invokes")
    if bool(records) != (e.get("hook_routed") is True):
        out.append("hook_routed")
    payloads = checker_payloads(impl)
    kinds = sorted({str((p.get("subject") or {}).get("input_kind")) if p.get("subject")
                    else "none" for p in payloads}) or ["no_check"]
    if e.get("subject_kind") is not None and kinds != [e["subject_kind"]]:
        out.append("subject_kind")
    trusted = any((p.get("subject") or {}).get("input_kind") == INPUT_KIND_PROPOSED and any(
        i.get("rule_type") == NUMERIC and i.get("outcome") == "APPLIED"
        for i in p.get("applicability") or []) for p in payloads)
    if trusted != (e.get("trusted_proposed_source") is True):
        out.append("trusted_proposed_source")
    for decision, rule in sorted((e.get("numeric_rules") or {}).items()):
        got = traces.get(decision) or [{}]
        for field_name, key in (("applicability", "outcome"), ("matcher_status", "matcher_status"),
                                ("matcher_outcome", "matcher_outcome"),
                                ("primary_reason", "primary_reason")):
            want = rule.get(field_name) if isinstance(rule, dict) else None
            if want is not None and any(t.get(key) != want for t in got):
                out.append(f"numeric_rules.{field_name}")
        reasons = rule.get("unknown_source_reasons") if isinstance(rule, dict) else None
        if reasons is not None:
            seen = sorted(s.get("reason") for t in got for s in t.get("unknown_sources") or [])
            if len(got) == 1 and seen != sorted(reasons):
                out.append("numeric_rules.unknown_source_reasons")
    facts = obs.get("envelope") or {}
    if e.get("content_utf8_sha256") != facts.get("content_sha256"):
        out.append("content_utf8_sha256")
    gate_g2 = (case.klass in PROCEED_CLASSES and e.get("expected_from_baseline") is not True
               and e.get("literal_violation") is not True)
    if gate_g2 != (e.get("g2_false_block_gate_applies") is True):
        out.append("g2_false_block_gate_applies_vs_registered_rule")
    return sorted(set(out))


def aggregate(scored: list[tuple[Case, dict]]) -> dict:
    gates = {}
    for gate in GATES:
        if gate == "G7":
            continue
        applicable = [(c, s) for c, s in scored if s["gates"][gate]["applies"]]
        failing = [(c, s) for c, s in applicable if not s["gates"][gate]["pass"]]
        gates[gate] = {
            "pass": not failing, "applicable": len(applicable), "failures": len(failing),
            "failing_cases": [{"case_id": c.case_id, "class": c.klass,
                               "why": sorted(set(s["gates"][gate]["why"]))} for c, s in failing],
        }
    return gates


# ── passes ───────────────────────────────────────────────────────────────────

A2_COMPARISON = (
    "Amendment 2 (pre-registration, A2.1-A2.3): a G5 hook-level case is in scope only "
    "when the pinned baseline's own run exited nonzero with at least one Python "
    "traceback block on stderr. For it, stdout, the exit status, the ordered exception "
    "summary lines (chained ones included), the ordered chain separator lines and every "
    "stderr line outside a traceback block must be byte-identical between the builds; "
    "only the frame lines between 'Traceback (most recent call last):' and the summary "
    "line are left out. A current build that did not raise fails. Every other case "
    "keeps raw-byte G5."
)


def conformance_count(scored: list[tuple[Case, dict]]) -> dict:
    """Non-gating: how many cases disagree with at least one ungated label."""
    mismatched = [c.case_id for c, s in scored if s["diagnostics"].get("conformance")]
    return {"cases": len(scored), "cases_with_mismatch": len(mismatched),
            "cases_in_full_agreement": len(scored) - len(mismatched), "gating": False}


def amendment_2_summary(scored: list[tuple[Case, dict]]) -> dict:
    """A2.3: cases in scope by class, and whether their raw bytes matched."""
    by_class: dict[str, dict[str, int]] = {}
    for case, result in scored:
        a2 = result["diagnostics"].get("amendment_2")
        if a2 is None:
            continue
        row = by_class.setdefault(case.klass, {"cases": 0, "raw_bytes_identical": 0,
                                               "a2_pass": 0})
        row["cases"] += 1
        row["raw_bytes_identical"] += bool(a2["raw_bytes_identical"])
        row["a2_pass"] += bool(a2["pass"])
    return {"applied": bool(by_class), "in_scope_by_class": dict(sorted(by_class.items())),
            "comparison": A2_COMPARISON}


def run_pass(cases: list[Case], ctx: Context, host: tuple[str, str], out_dir: Path) -> dict:
    out_dir.mkdir(parents=True)
    scored: list[tuple[Case, dict]] = []
    lines: dict[bool, list[str]] = {False: [], True: []}
    for case in cases:
        obs = execute_case(case, ctx)
        obs.setdefault("case_id", case.case_id)
        result = score_case(case, obs, host)
        obs["score"] = result
        lines[case.public_smoke].append(dump_line(obs))
        scored.append((case, result))
    # Smoke cases go to their own files, so they never reach a gate (G2V-F4),
    # G7 included.
    (out_dir / "cases.jsonl").write_text("".join(lines[False]), encoding="ascii", newline="\n")
    (out_dir / "smoke_cases.jsonl").write_text("".join(lines[True]), encoding="ascii",
                                               newline="\n")
    concealed = [(c, s) for c, s in scored if not c.public_smoke]
    smoke = [(c, s) for c, s in scored if c.public_smoke]
    conformance = Counter(
        item for c, s in concealed for item in s["diagnostics"].get("conformance", []))
    smoke_conformance = Counter(
        item for c, s in smoke for item in s["diagnostics"].get("conformance", []))
    smoke_summary = {"cases": len(smoke), "gating": False, "gates": aggregate(smoke),
                     "label_conformance_mismatches": dict(sorted(smoke_conformance.items())),
                     "label_conformance": conformance_count(smoke),
                     "amendment_2": amendment_2_summary(smoke)}
    (out_dir / "smoke_summary.json").write_text(dump_json(smoke_summary), encoding="ascii",
                                                newline="\n")
    summary = {
        "schema": RUN_SUMMARY_SCHEMA,
        "concealed_cases": len(concealed),
        "gates": aggregate(concealed),
        "label_conformance_mismatches": dict(sorted(conformance.items())),
        "label_conformance": conformance_count(concealed),
        "g5_stderr_diagnostics": [
            {"case_id": c.case_id, "class": c.klass,
             "normalized_equal": s["diagnostics"]["stderr"]["normalized_equal"]}
            for c, s in concealed if "stderr" in s["diagnostics"]],
        "amendment_2": amendment_2_summary(concealed),
    }
    (out_dir / "summary.json").write_text(dump_json(summary), encoding="ascii", newline="\n")
    return dict(summary, public_smoke=smoke_summary)


def compare_passes(out_dir: Path) -> dict:
    result = {}
    for name in ("cases.jsonl", "summary.json"):
        a = (out_dir / "run-1" / name).read_bytes()
        b = (out_dir / "run-2" / name).read_bytes()
        result[name] = {"run_1_sha256": sha256_bytes(a), "run_2_sha256": sha256_bytes(b),
                        "identical": a == b}
    differing = []
    one = (out_dir / "run-1" / "cases.jsonl").read_text(encoding="ascii").splitlines()
    two = (out_dir / "run-2" / "cases.jsonl").read_text(encoding="ascii").splitlines()
    for x, y in zip(one, two):
        if x != y:
            differing.append(json.loads(x).get("case_id"))
    if len(one) != len(two):
        differing.append("<case count differs>")
    result["differing_cases"] = differing
    result["pass"] = all(v["identical"] for k, v in result.items() if isinstance(v, dict))
    smoke = [(out_dir / f"run-{n}" / "smoke_cases.jsonl").read_bytes() for n in (1, 2)]
    result["public_smoke_identical"] = smoke[0] == smoke[1]  # reported, never gating
    return result


def check_run_root(run_root: Path) -> Path:
    resolved = Path(os.path.realpath(run_root))
    if os.path.normcase(str(resolved)) != os.path.normcase(os.path.abspath(run_root)):
        raise Refusal("run_root", "run root has a link component or short name; "
                                  "pass its resolved form")
    if os.path.lexists(resolved):
        raise Refusal("run_root", f"{resolved} exists; it must be created by the harness")
    for ancestor in resolved.parents:
        if (ancestor / ".mneme").exists():
            raise Refusal("run_root", f"an ancestor has a .mneme directory: {ancestor}")
    return resolved


def harness_digests() -> dict:
    return {
        "harness.py": sha256_file(HARNESS_DIR / "harness.py"),
        "observe_shim/sitecustomize.py": sha256_file(SHIM_DIR / "sitecustomize.py"),
    }


def _utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def score(*, corpus: Path, out_dir: Path, impl_python: str, impl_wheel: Path,
          base_python: str, base_wheel: Path, host_version: str, host_sha256: str,
          run_root: Path | None = None, corpus_tar: Path | None = None,
          pins: Pins = G2_PINS) -> dict:
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"--out {out_dir} must be new or empty")
    out_dir.mkdir(parents=True, exist_ok=True)
    final: dict = {"schema": SUMMARY_SCHEMA, "started": _utc(), "pins": pins_record(pins),
                   "harness": harness_digests(), "disclosures": list(DISCLOSURES),
                   "host_identity_input": {"version": host_version,
                                           "executable_sha256": host_sha256}}
    try:
        if not _nonempty_str(host_version) or not _is_sha256(host_sha256):
            raise Refusal("host_identity", "--host-version must be non-empty and "
                                           "--host-sha256 a lowercase SHA-256")
        root = check_run_root(run_root or Path(tempfile.gettempdir()) / "mneme-g2h-run")
        probe_dir = Path(tempfile.mkdtemp(prefix="g2h-pre-"))
        try:
            final["builds"] = verify_builds(impl_python, impl_wheel, base_python, base_wheel,
                                            probe_dir, pins)
        finally:
            _rmtree(probe_dir)
        final["corpus"], cases = verify_corpus(corpus, pins, corpus_tar)
        final["symlinks"] = probe_symlinks(root.parent)
        final["run_root"] = str(root)
    except Refusal as refusal:
        final.update(result="REFUSED", refusal={"check": refusal.check, "detail": refusal.detail})
        return _finish(out_dir, final)

    ctx = Context(impl_python, base_python, host_version, host_sha256, root / "w")
    try:
        passes = score_passes(cases, ctx, root, out_dir)
    except Refusal as refusal:
        final.update(result="REFUSED", refusal={"check": refusal.check, "detail": refusal.detail})
        return _finish(out_dir, final)
    final.update(passes)
    for name, probe in final["builds"].items():
        # The builds must not change while being scored (M4 precedent).
        if git_tree_hash(Path(probe["mneme_dir"])) != probe["mneme_tree"]:
            final.update(result="REFUSED", refusal={
                "check": name, "detail": "mneme/ tree changed during scoring"})
            return _finish(out_dir, final)
    gates = final["gates"]
    if not final["symlinks"]["capable"]:
        final["result"] = "INCOMPLETE"
    else:
        final["result"] = "PASS" if all(gates[g]["pass"] for g in GATES) else "FAIL"
    final["headline"] = " ".join(
        f"{g} {'PASS' if gates[g]['pass'] else 'FAIL'} "
        f"({gates[g]['failures']}/{gates[g]['applicable']} failing)." for g in GATES)
    lc = final["label_conformance"]
    # A gate PASS is never label agreement: report the mismatch count beside it.
    final["headline"] += (f" Label conformance (non-gating): {lc['cases_with_mismatch']} of "
                          f"{lc['cases']} concealed cases have at least one label mismatch.")
    return _finish(out_dir, final)


def score_passes(cases: list[Case], ctx: Context, root: Path, out_dir: Path) -> dict:
    """Two complete passes at one run-root path, then G7 (§5)."""
    host = (ctx.host_version, ctx.host_sha256)
    summaries = []
    for number in (1, 2):
        if os.path.lexists(root):
            raise Refusal("run_root", "run root exists before a pass")
        root.mkdir(parents=True)
        try:
            summaries.append(run_pass(cases, ctx, host, out_dir / f"run-{number}"))
        finally:
            _rmtree(root)
    g7 = compare_passes(out_dir)
    gates = dict(summaries[0]["gates"])
    gates["G7"] = {"pass": g7["pass"], "applicable": len(cases),
                   "failures": len(g7["differing_cases"]),
                   "failing_cases": g7["differing_cases"],
                   "files": {k: v for k, v in g7.items() if isinstance(v, dict)}}
    summaries[0]["public_smoke"]["passes_identical"] = g7["public_smoke_identical"]
    return {
        "gates": {g: gates[g] for g in GATES},
        "public_smoke": summaries[0]["public_smoke"],
        "label_conformance_mismatches": summaries[0]["label_conformance_mismatches"],
        "label_conformance": summaries[0]["label_conformance"],
        "g5_stderr_diagnostics": summaries[0]["g5_stderr_diagnostics"],
        "amendment_2": summaries[0]["amendment_2"],
    }


def _finish(out_dir: Path, final: dict) -> dict:
    final["finished"] = _utc()
    (out_dir / "summary.json").write_text(dump_json(final), encoding="ascii", newline="\n")
    return final


# ── build ────────────────────────────────────────────────────────────────────

def build(out: Path, python: str, pins: Pins = G2_PINS) -> dict:
    """Build both pinned wheels from git and install each into its own venv.

    Needs network access for the build backend and runtime dependencies.
    Records each wheel's SHA-256 and each environment's ``pip freeze``
    digest in ``<out>/build.json``.
    """
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"--out {out} must be new or empty")
    out.mkdir(parents=True, exist_ok=True)
    record = {"python": python, "builds": {}}
    for name, commit, tree in (("implementation", pins.impl_commit, pins.impl_tree),
                               ("baseline", pins.baseline_commit, pins.baseline_tree)):
        actual = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", f"{commit}:mneme"],
                                capture_output=True, text=True, check=True).stdout.strip()
        if actual != tree:
            raise SystemExit(f"{name}: {commit}:mneme is {actual}, pinned {tree}")
        src, dist, venv = out / f"src-{name}", out / f"dist-{name}", out / f"venv-{name}"
        archive = subprocess.run(["git", "-C", str(REPO_ROOT), "archive", commit],
                                 capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(src, filter="data")
        env = dict(os.environ, SOURCE_DATE_EPOCH="1792886400")
        subprocess.run([python, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(dist),
                        str(src)], check=True, env=env)
        (wheel,) = dist.glob("*.whl")
        subprocess.run([python, "-m", "venv", str(venv)], check=True)
        venv_python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(venv_python), "-m", "pip", "install", str(wheel)], check=True)
        freeze = subprocess.run([str(venv_python), "-m", "pip", "freeze", "--all"],
                                capture_output=True, check=True).stdout
        record["builds"][name] = {"commit": commit, "mneme_tree": tree, "wheel": str(wheel),
                                  "wheel_sha256": sha256_file(wheel),
                                  "python": str(venv_python),
                                  "pip_freeze_sha256": sha256_bytes(freeze)}
    (out / "build.json").write_text(dump_json(record), encoding="ascii", newline="\n")
    return record


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="build both pinned wheels and environments")
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--python", required=True, help="CPython 3.12.10 used to build")
    p = sub.add_parser("probe-symlinks", help="G2V-F2 symlink capability probe")
    p.add_argument("--dir", type=Path, default=Path(tempfile.gettempdir()))
    s = sub.add_parser("score", help="score the decrypted corpus (two passes)")
    s.add_argument("--corpus", type=Path, required=True)
    s.add_argument("--impl-python", required=True)
    s.add_argument("--impl-wheel", type=Path, required=True)
    s.add_argument("--baseline-python", required=True)
    s.add_argument("--baseline-wheel", type=Path, required=True)
    s.add_argument("--host-version", required=True)
    s.add_argument("--host-sha256", required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--run-root", type=Path, default=None)
    s.add_argument("--corpus-tar", type=Path, default=None,
                   help="the decrypted plaintext tar, to check its pinned SHA-256")
    args = parser.parse_args(argv)
    if args.command == "build":
        print(dump_json(build(args.out, args.python)), end="")
        return 0
    if args.command == "probe-symlinks":
        result = probe_symlinks(args.dir)
        print(dump_json(result), end="")
        return 0 if result["capable"] else 1
    final = score(corpus=args.corpus, out_dir=args.out, impl_python=args.impl_python,
                  impl_wheel=args.impl_wheel, base_python=args.baseline_python,
                  base_wheel=args.baseline_wheel, host_version=args.host_version,
                  host_sha256=args.host_sha256, run_root=args.run_root,
                  corpus_tar=args.corpus_tar)
    print(final.get("headline") or final.get("refusal"))
    print(f"result: {final['result']}")
    return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 1}.get(final["result"], 2)


if __name__ == "__main__":
    sys.exit(main())

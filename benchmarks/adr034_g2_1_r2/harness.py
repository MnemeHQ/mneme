#!/usr/bin/env python3
"""ADR-034 G2-1 R2 scoring harness.

Scores the corrected G2-1 build (implementation pin ``dbab816f``) against the
sealed R2 held-out corpus, under the frozen R2 pre-registration
(``docs/validation/adr-034-g2-1-revalidation-preregistration-2026-10-26.md``,
revision 2 and Amendment 1) and the R1 pre-registration it inherits
(revision 2, Amendments 1 and 2): gates G1-G8 as R2 §5 restates them, the
G2V-F2 symlink rule and the §6 failure policy. Written before decryption from
those records, the R2 freeze record, ADR-034 §3a/§6a/§7a/§7b and the 13 R2
public smoke cases. It contains no concealed case data. Code is copied from
the pinned R1 harness ``benchmarks/adr034_g2_1/``, which is not modified.

Subcommands::

    python benchmarks/adr034_g2_1_r2/harness.py build --out <dir> --python <CPython 3.12.10>
    python benchmarks/adr034_g2_1_r2/harness.py probe-symlinks [--dir <dir>]
    python benchmarks/adr034_g2_1_r2/harness.py score \\
        --corpus <decrypted corpus root, the directory holding FILES.sha256> \\
        --impl-python <python of the dbab816f environment> --impl-wheel <wheel> \\
        --baseline-python <python of the f8591102 environment> --baseline-wheel <wheel> \\
        --host-version <pinned host version> --host-sha256 <pinned executable SHA-256> \\
        --out <new or empty directory> [--public-smoke <public smoke folder>]

``score`` exit status: 0 PASS, 1 FAIL or INCOMPLETE, 2 REFUSED.

The harness never imports ``mneme``. Every call into a build runs in that
build's own interpreter: the hook exactly as the host starts it
(``python -m mneme.integrations.claude_code.hook``, envelope on stdin), the
checker as ``python -m mneme ...``, and the R2 §5 G6 evidence functions
(``relevant_enforcement_per_rule()``, ``relevant_enforcement_observed()``,
``recorded_evaluation_complete()``) from the implementation build's own hook
module. After decryption the harness is not edited (pre-registration §6): a
harness fix then voids blind status.
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

CASE_RECORD_SCHEMA = "mneme.adr034-g2-1-r2.case/v1"
RUN_SUMMARY_SCHEMA = "mneme.adr034-g2-1-r2.run-summary/v1"
SUMMARY_SCHEMA = "mneme.adr034-g2-1-r2.summary/v1"

NUMERIC = "FORBID_NUMERIC_ABOVE"
LITERAL = "FORBID_LITERAL"
HOOK_MODULE = "mneme.integrations.claude_code.hook"
EVIDENCE_SURFACE = "claude_code.PreToolUse"  # charter §6.2
EVIDENCE_SCHEMA = "mneme.hook_evidence/v1"  # G6R-F1
INPUT_KIND_PROPOSED = "proposed_new_source"
CHILD_TIMEOUT_S = 120
OBSERVE_LOG_ENV = "MNEME_G2R2_OBSERVE_LOG"

CLASSES = ("V", "VP", "C", "US", "UF", "UP", "X", "L", "LIT", "W", "P", "SC", "MR")
GATES = ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8")
# R1-PR §5 G2: the classes expected to proceed under availability open. R2V-F1
# adds every SC and MR case whose labels expect it to proceed (see g2_applies).
PROCEED_CLASSES = frozenset({"C", "US", "UF", "UP", "X", "L", "W", "P"})
LABEL_PROCEED_CLASSES = frozenset({"SC", "MR"})
# §5 G4: the classes whose unevaluated rules' primary reason is scored (R2 adds SC, MR).
REASON_CLASSES = frozenset({"US", "UF", "UP", "VP", "SC", "MR"})
# §5 G5 hook level, and checker level (routed only).
HOOK_PARITY_CLASSES = frozenset({"P", "X", "L"})
CHECKER_PARITY_CLASSES = frozenset({"P", "X"})

CASE_KEYS = (
    "availability", "byte_features", "case_id", "class", "content_utf8_encodable",
    "content_utf8_sha256", "dirs", "hook_mode", "memory", "public_smoke", "symlinks",
    "target",
)
EXPECTED_KEYS = (
    "applied_numeric_rule_ids", "availability", "case_id", "checker_invoked", "class",
    "disposition", "evaluation_complete", "evidence_record_expected", "expected_cause",
    "g6_routed_fallback", "hook_exit", "hook_mode", "legacy_baseline_observed",
    "literal_violation", "numeric_rules", "relevant_enforcement_observed",
    "relevant_enforcement_per_rule", "routed", "routed_cr_parity_exception",
    "subject_kind", "target_exists_after_hook",
)
RULE_KEYS = (
    "applicability", "matcher_outcome", "matcher_status", "primary_reason", "rule_id",
    "rule_id_form_verified", "rule_key", "unknown_source_reason_set",
)
TARGET_ROOTS = ("repo", "outside", "case")
CASE_ID = re.compile(r"r2-[0-9a-f]{10}")

# R2A1.2 AMB-R2-08: the record's ``disposition.cause`` (with the identities of
# the violations it reports) mapped onto the corpus's ``expected_cause``
# vocabulary. Fixed here, before decryption. Any record cause outside this
# table maps to itself and can never equal an ``expected_cause`` value.
CAUSE_MAPPING = (
    "numeric_violation, with a reported FORBID_LITERAL violation -> numeric_and_literal_violation",
    "numeric_violation, with no reported FORBID_LITERAL violation -> numeric_violation",
    "other_rule, with a reported FORBID_LITERAL violation and no reported numeric "
    "violation -> literal_violation",
    "no_violation -> no_violation",
    "fail_open -> fail_open",
    "anything else (other_rule without a reported FORBID_LITERAL violation, "
    "availability_refusal, not_run, a missing cause) -> unmapped: always a G6 cause mismatch",
)

# Reported in every summary.
DISCLOSURES = (
    "Hook runs: each build's hook is started as `python -m "
    "mneme.integrations.claude_code.hook` with the substituted envelope on stdin, in "
    "the envelope's cwd when that is an existing directory (else the case root), "
    "with a constructed environment (no inherited PYTHON*, MNEME_*, VIRTUAL_ENV, HOME "
    "or user profile; TEMP/TMP/TMPDIR, HOME and USERPROFILE point at fresh per-run "
    "scratch directories). Both builds get the same environment.",
    "Observation shim: PYTHONPATH carries benchmarks/adr034_g2_1_r2/observe_shim for both "
    "builds' hook processes. In the `python -m mneme check` child only, it records the "
    "argument vector, the carrier digest and a copy of the text written to stdout; it "
    "never writes to stdout or stderr and passes every write through unchanged.",
    "Memory (R2A1.2 AMB-R2-06): compiled once per case per pass with the implementation "
    "build's own ADR import (`mneme init --path`, then `mneme adr import <dir> --memory "
    "<file> --apply`), from memory.compile_from in that order: one import of the ADR "
    "directory when the list is exactly that directory's own sorted ADR-*.md listing, "
    "otherwise one import per file, in list order, with only that file visible. The same "
    "bytes are used for the baseline run. A compile failure, or a compile_from ADR whose "
    "id is missing from the compiled memory, is a G8 failure of the case. `mneme init` "
    "stamps a wall-clock time into the memory, so raw memory bytes are not part of the "
    "G7 comparison; their decision ids and typed rules are.",
    "Fixture copies: the memory compile, the implementation hook, the baseline hook and "
    "the checker parity pair each run on a freshly materialized copy of the fixture at "
    "the same path, so absolute paths in output are identical between builds and passes.",
    "Envelope: ${REPO}, ${OUTSIDE} and ${CASE} are replaced inside the raw envelope "
    "text, in the JSON string literals that hold them, with the native absolute paths; "
    "the forward-slash remainder is joined with native separators. Every other envelope "
    "byte, tool_input.content included, reaches the hook unchanged. The synthetic "
    "identifiers are kept as authored.",
    "G7: both passes run at the same run-root path, created fresh and removed after "
    "each pass. Determinism is therefore tested at a repeated path.",
    "G6 relevance and completeness (R2 §5) are computed by the pinned implementation "
    "build's own relevant_enforcement_per_rule(), relevant_enforcement_observed() and "
    "recorded_evaluation_complete(), with the pinned host identity given as input, right "
    "after the hook run while the fixture is still in place. This is synthetic replay: "
    "it is never evidence that a live host enforced anything.",
    "R2A1.6 as corrected by R2 Amendment 2 (A2R2.2, A2R2.3): a case marked "
    "g6_routed_fallback is scored by G6 against the fixed expectation (rule-ID set {}, "
    "per-rule {}, event-level false, evaluation_complete false, exactly one record), "
    "whatever its other G6 labels say. The stored null evaluation_complete label is "
    "read as false by the flag alone; an untrusted or absent value (None) or any other "
    "value fails G6 step 4. A label disagreeing with R2A1.6 otherwise is reported as a "
    "non-gating finding. The summary's r2_amendment_2 block counts flagged cases and "
    "their G6 outcome by class.",
    "Public smoke cases are run and reported separately; they are never in a gate "
    "denominator (G2V-F4).",
    "G5 implements R1 pre-registration Amendment 2: where the pinned baseline's own run "
    "raised an uncaught exception, only traceback frame lines are left out of the "
    "hook-level comparison; the raw bytes, the raw diff and the result are recorded per "
    "case, and the summary counts in-scope cases by class.",
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
    public_files_sha256_digest: str
    public_files_count: int
    # class -> (concealed, public smoke)
    counts: dict
    is_frozen: bool = True


R2_PINS = Pins(
    python_version="3.12.10",
    impl_commit="dbab816f92143875c1ed7c7d24e4403dedc3b345",
    impl_tree="6cb14c2b48554482e62685395062bb581dfed5e4",
    baseline_commit="f8591102b2693379dabec9b5704862e194eca4ce",
    baseline_tree="002fdddb254267d42a3810cfea669d75700372f2",
    files_sha256_digest="70d35226584bead131929deb41e3e3f59a5307d0ae34fe49b29426692a749c0d",
    files_count=605,
    corpus_tar_sha256="17a46379cfbb04ec41cc7e740a9f52ce1f94e48e154a2178987ca56af22dcfe1",
    public_files_sha256_digest="b60394c0076f41f8dd0845c6b290347522bea36d42340050686f04bc3547ab0c",
    public_files_count=57,
    counts={
        "V": (16, 1), "VP": (10, 1), "C": (17, 1), "US": (9, 1), "UF": (10, 1),
        "UP": (7, 1), "X": (7, 1), "L": (19, 1), "LIT": (7, 1), "W": (7, 1),
        "P": (9, 1), "SC": (15, 1), "MR": (10, 1),
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
    special files are refused. (Same definition as the M4 and R1 harnesses.)
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


def _native_separators(text: str) -> str:
    """Forward slashes to this platform's separator, nothing else changed."""
    return text.replace("/", os.sep)


def _rmtree(path: Path) -> None:
    def onerror(func, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            pass

    if os.path.islink(path):
        os.unlink(path)
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
    work = Path(tempfile.mkdtemp(prefix="g2r2-symlink-", dir=str(directory)))
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
        for link in ("file-link", "dir-link", "dangling-link"):
            if os.path.islink(work / link):
                os.unlink(work / link)
        _rmtree(work)
    return result


# ── corpus ───────────────────────────────────────────────────────────────────

_FILES_LINE = re.compile(r"^([0-9a-f]{64}) [ *](.+)$")


def parse_files_sha256(text: str, what: str = "files_sha256") -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        match = _FILES_LINE.match(line)
        if match is None:
            raise Refusal(what, f"unparseable line {number}")
        try:
            rel = _safe_relative(match.group(2), what).as_posix()
        except ValueError as exc:
            raise Refusal(what, str(exc)) from exc
        if rel in seen:
            raise Refusal(what, f"duplicate entry {rel!r}")
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
    base: Path  # cases/<case_id>
    problems: list


def _label_problems(expected: dict) -> list[str]:
    """Shape problems in the labels the gates read. Any one is a G8 failure."""
    problems = []
    rules = expected.get("numeric_rules")
    if not isinstance(rules, list):
        return ["expected.json numeric_rules is not a list"]
    for rule in rules:
        if not isinstance(rule, dict) or any(k not in rule for k in RULE_KEYS):
            problems.append("expected.json numeric_rules entry shape")
        elif not isinstance(rule.get("unknown_source_reason_set"), list):
            problems.append("expected.json unknown_source_reason_set")
    applied = expected.get("applied_numeric_rule_ids")
    per_rule = expected.get("relevant_enforcement_per_rule")
    if expected.get("evidence_record_expected") is True:
        if not isinstance(applied, list) or not all(isinstance(r, str) for r in applied):
            problems.append("expected.json applied_numeric_rule_ids")
        elif len(set(applied)) != len(applied):
            problems.append("expected.json applied_numeric_rule_ids has a duplicate")
        if not isinstance(per_rule, dict) or not all(
                isinstance(v, bool) for v in per_rule.values()):
            problems.append("expected.json relevant_enforcement_per_rule")
        if not isinstance(expected.get("relevant_enforcement_observed"), bool):
            problems.append("expected.json relevant_enforcement_observed")
    elif expected.get("evidence_record_expected") is not False:
        problems.append("expected.json evidence_record_expected")
    for key in ("routed", "literal_violation", "g6_routed_fallback",
                "legacy_baseline_observed", "target_exists_after_hook"):
        if not isinstance(expected.get(key), bool):
            problems.append(f"expected.json {key}")
    return problems


def load_case(cases_dir: Path, case_id: str) -> Case:
    """Read one case. A malformed case is kept and fails G8, never dropped."""
    base = cases_dir / case_id
    problems: list[str] = []
    case: Any = {}
    expected: Any = {}
    envelope_text = ""
    try:
        case = load_json_bytes((base / "case.json").read_bytes())
    except (OSError, ValueError) as exc:
        problems.append(f"case.json unreadable ({type(exc).__name__})")
    try:
        expected = load_json_bytes((base / "expected.json").read_bytes())
    except (OSError, ValueError) as exc:
        problems.append(f"expected.json unreadable ({type(exc).__name__})")
    try:
        envelope_text = (base / "envelope.json").read_bytes().decode("utf-8")
        json.loads(envelope_text)
    except (OSError, ValueError) as exc:
        problems.append(f"envelope unreadable ({type(exc).__name__})")
    if not isinstance(case, dict) or not isinstance(expected, dict):
        problems.append("case.json or expected.json is not an object")
        case, expected = {}, {}
    for key in CASE_KEYS:
        if case and key not in case:
            problems.append(f"case.json missing {key}")
    for key in EXPECTED_KEYS:
        if expected and key not in expected:
            problems.append(f"expected.json missing {key}")
    if case.get("case_id") != case_id or expected.get("case_id") != case_id:
        problems.append("case_id differs from its directory")
    klass = expected.get("class")
    if klass not in CLASSES or case.get("class") != klass:
        problems.append("class")
    if expected.get("hook_mode") not in ("strict", "warn") or \
            case.get("hook_mode") != expected.get("hook_mode"):
        problems.append("hook_mode")
    if case.get("availability") != "open" or expected.get("availability") != "open":
        problems.append("availability is not open")
    if case and expected:
        problems.extend(_label_problems(expected))
    return Case(case_id=case_id, klass=klass if klass in CLASSES else "?",
                public_smoke=case.get("public_smoke") is True,
                case=case, expected=expected, envelope_text=envelope_text,
                base=base, problems=problems)


def case_roots(root: Path) -> list[Path]:
    """Every directory, the root or one of its children, holding MANIFEST.json and cases/.

    The R2 corpus README says the same format sits at the top of ``concealed/``
    and ``public-smoke/``; the plaintext tar's exact nesting is not stated, so
    both a flat root and one level of nesting are accepted.
    """
    candidates = [root] + sorted(p for p in root.iterdir() if p.is_dir())
    return [p for p in candidates
            if (p / "MANIFEST.json").is_file() and (p / "cases").is_dir()]


def manifest_findings(case_root: Path, cases: list[Case]) -> list[str]:
    """Cross-check MANIFEST.json against the case files; findings only, never a refusal."""
    findings: list[str] = []
    try:
        rows = load_json_bytes((case_root / "MANIFEST.json").read_bytes())
    except (OSError, ValueError):
        return ["MANIFEST.json unreadable"]
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        return ["MANIFEST.json shape not recognized"]
    by_id = {c.case_id: c for c in cases}
    listed = {r.get("case_id"): r for r in rows}
    if set(listed) != set(by_id) or len(listed) != len(rows):
        findings.append("MANIFEST.json case set differs from cases/")
    if [r.get("case_id") for r in rows] != sorted(str(r.get("case_id")) for r in rows):
        findings.append("MANIFEST.json is not sorted by case_id")
    for case_id, row in sorted(listed.items(), key=lambda kv: str(kv[0])):
        case = by_id.get(case_id)
        if case is None:
            continue
        if row.get("class") != case.klass:
            findings.append(f"{case_id}: MANIFEST class differs")
        if bool(row.get("public_smoke")) != case.public_smoke:
            findings.append(f"{case_id}: MANIFEST public_smoke differs")
    return findings


def load_cases(root: Path) -> tuple[list[Case], list[str]]:
    roots = case_roots(root)
    if not roots:
        raise Refusal("corpus_layout", "no MANIFEST.json with cases/ at the root or one level down")
    cases: list[Case] = []
    findings: list[str] = []
    for case_root in roots:
        ids = sorted(p.name for p in (case_root / "cases").iterdir() if p.is_dir())
        if not ids or not all(CASE_ID.fullmatch(c) for c in ids):
            raise Refusal("corpus_layout", "cases/ holds a directory that is not a case id")
        loaded = [load_case(case_root / "cases", case_id) for case_id in ids]
        findings.extend(manifest_findings(case_root, loaded))
        cases.extend(loaded)
    if len({c.case_id for c in cases}) != len(cases):
        raise Refusal("corpus_layout", "a case id appears twice")
    return cases, findings


def verify_tree(root: Path, manifest_name: str, digest_pin: str, count_pin: int,
                what: str) -> dict:
    files = root / manifest_name
    if not files.is_file():
        raise Refusal(what, f"{files} not found")
    digest = sha256_file(files)
    if digest != digest_pin:
        raise Refusal(what, f"digest {digest}, pinned {digest_pin}")
    entries = parse_files_sha256(files.read_text(encoding="utf-8"), what)
    if len(entries) != count_pin:
        raise Refusal(what, f"{len(entries)} entries, pinned {count_pin}")
    failures = []
    for expected_digest, rel in entries:
        path = root / PurePosixPath(rel)
        try:
            if not stat.S_ISREG(path.lstat().st_mode) or sha256_file(path) != expected_digest:
                failures.append(rel)
        except OSError:
            failures.append(rel)
    if failures:
        raise Refusal(what, f"{len(failures)} of {len(entries)} entries fail")
    regular, other = corpus_regular_files(root)
    listed = sorted([rel for _, rel in entries] + [manifest_name])
    if regular != listed or other:
        raise Refusal(f"{what}_layout", f"files differ from {manifest_name} "
                                        f"({len(regular)} regular, {len(other)} other)")
    return {"manifest_sha256": digest, "files_verified": len(entries)}


def class_counts(cases: list[Case]) -> dict[str, list[int]]:
    observed: dict[str, list[int]] = {k: [0, 0] for k in CLASSES}
    for case in cases:
        if case.klass in observed:
            observed[case.klass][1 if case.public_smoke else 0] += 1
    return observed


def verify_corpus(root: Path, pins: Pins, corpus_tar: Path | None,
                  public: Path | None) -> tuple[dict, list[Case]]:
    record = {"corpus": verify_tree(root, "FILES.sha256", pins.files_sha256_digest,
                                    pins.files_count, "files_sha256")}
    if corpus_tar is not None:
        tar_digest = sha256_file(corpus_tar)
        if tar_digest != pins.corpus_tar_sha256:
            raise Refusal("corpus_tar", f"digest {tar_digest}, pinned {pins.corpus_tar_sha256}")
        record["corpus_tar_sha256"] = tar_digest
    cases, findings = load_cases(root)
    if public is not None:
        record["public_smoke"] = verify_tree(
            public, "PUBLIC_FILES.sha256", pins.public_files_sha256_digest,
            pins.public_files_count, "public_files_sha256")
        smoke, smoke_findings = load_cases(public)
        if not all(c.public_smoke for c in smoke):
            raise Refusal("public_smoke", "a case in the public folder is not public_smoke")
        if {c.case_id for c in smoke} & {c.case_id for c in cases}:
            raise Refusal("public_smoke", "a public case id is also in the corpus")
        cases = sorted(cases + smoke, key=lambda c: c.case_id)
        findings.extend(smoke_findings)
    observed = class_counts(cases)
    unknown = sum(1 for c in cases if c.klass not in pins.counts)
    concealed = {k: v[0] for k, v in observed.items()}
    if concealed != {k: v[0] for k, v in pins.counts.items()} or unknown:
        raise Refusal("counts", f"concealed class counts {concealed} (+{unknown} unclassified), "
                                f"pinned {({k: v[0] for k, v in pins.counts.items()})}")
    smoke_counts = {k: v[1] for k, v in observed.items()}
    if any(smoke_counts.values()) and smoke_counts != {k: v[1] for k, v in pins.counts.items()}:
        findings.append("public smoke class counts differ from the freeze record")
    record["counts"] = {k: v for k, v in sorted(observed.items())}
    record["findings"] = findings
    return record, cases


# ── one case: fixture, memory, hook, checker ─────────────────────────────────

class CaseFailure(Exception):
    """A scoring-process failure for one case (G8)."""


@dataclasses.dataclass(frozen=True)
class Layout:
    """The native paths one case is materialized at (README "Materializing")."""
    case: Path
    repo: Path
    outside: Path

    @classmethod
    def at(cls, case_root: Path) -> "Layout":
        return cls(case_root, case_root / "repo", case_root / "outside")

    def tokens(self) -> dict[str, Path]:
        return {"REPO": self.repo, "OUTSIDE": self.outside, "CASE": self.case}


_TOKEN = re.compile(r"\$\{([A-Za-z_]+)\}")
_JSON_STRING = re.compile(r'"(?:[^"\\]|\\.)*"', re.S)


def substitute_value(value: str, layout: Layout) -> str:
    """``${TOKEN}/rel/path`` to the native absolute path (README step 6)."""
    match = re.fullmatch(r"\$\{([A-Za-z_]+)\}(.*)", value, re.S)
    if match is None:
        raise CaseFailure("envelope placeholder is not at the start of its string")
    name, rest = match.groups()
    base = layout.tokens().get(name)
    if base is None:
        raise CaseFailure("envelope has an unknown placeholder")
    if _TOKEN.search(rest):
        raise CaseFailure("envelope string has more than one placeholder")
    if rest == "":
        return str(base)
    if not rest.startswith("/"):
        raise CaseFailure("envelope placeholder is not followed by '/'")
    return str(base) + _native_separators(rest)


def _string_values(value: Any, skip: Any = None) -> set[str]:
    if value is skip:
        return set()
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return set().union(*[_string_values(v, skip) for v in value.values()])
    if isinstance(value, list):
        return set().union(*[_string_values(v, skip) for v in value])
    return set()


def substitute_envelope(text: str, layout: Layout) -> str:
    """Replace the placeholders inside the raw envelope text (README step 6).

    Only JSON string literals whose decoded value is a placeholder-bearing
    string of the envelope other than ``tool_input.content`` are rewritten,
    so every other byte, including escaped CR, BOM and lone-surrogate
    content, reaches the hook unchanged. The content is then checked to be
    unchanged.
    """
    original = json.loads(text)
    content = (original.get("tool_input") or {}).get("content") \
        if isinstance(original, dict) else None
    targets = {v for v in _string_values(original, skip=content) if "${" in v}

    def literal(match: re.Match) -> str:
        raw = match.group(0)
        if "${" not in raw:
            return raw
        value = json.loads(raw)
        if value not in targets:
            return raw
        return json.dumps(substitute_value(value, layout), ensure_ascii=False)

    out = _JSON_STRING.sub(literal, text)
    parsed = json.loads(out)
    if (parsed.get("tool_input") or {}).get("content") != content:
        raise CaseFailure("envelope substitution would change tool_input.content")
    if any("${" in v for v in _string_values(parsed, skip=(parsed.get("tool_input") or {})
                                                .get("content"))):
        raise CaseFailure("envelope keeps an unsubstituted placeholder")
    return out


def materialize(case: Case, layout: Layout, memory_bytes: bytes | None) -> None:
    """README steps 1-3, then the compiled memory bytes (step 4) when given."""
    dirs = case.case.get("dirs") or {}
    if os.path.lexists(layout.case):
        raise CaseFailure("case root exists before materialization")
    layout.case.mkdir(parents=True)
    fixture = case.base / "fixture" / "repo"
    if fixture.is_dir():
        shutil.copytree(fixture, layout.repo, symlinks=True)
    else:
        layout.repo.mkdir()
    if dirs.get("outside"):
        layout.outside.mkdir()
    for key, base in (("repo", layout.repo), ("outside", layout.outside)):
        for rel in dirs.get(key) or []:
            (base / _native(_safe_relative(rel, f"dirs.{key}"))).mkdir(parents=True,
                                                                      exist_ok=True)
    for entry in case.case.get("symlinks") or []:
        link = layout.repo / _native(_safe_relative(entry.get("path"), "symlinks.path"))
        target = entry.get("target")
        if not isinstance(target, str) or not target or entry.get("kind") not in ("file", "dir"):
            raise CaseFailure("symlink entry is malformed")
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(_native_separators(target), link,
                       target_is_directory=entry["kind"] == "dir")
        except OSError as exc:
            raise CaseFailure(f"symlink could not be created ({type(exc).__name__}); "
                              "G2V-F2: the run is INCOMPLETE") from exc
    if memory_bytes is not None:
        memory = layout.repo / ".mneme" / "project_memory.json"
        memory.parent.mkdir(parents=True, exist_ok=True)
        memory.write_bytes(memory_bytes)


def typed_rules_of(memory: dict) -> tuple[list[str], list[dict]]:
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
    return sorted(ids), [json.loads(r) for r in sorted(rules)]


_FRONT_ID = re.compile(r"^id:\s*['\"]?([^'\"\s]+)['\"]?\s*$", re.M)


def _adr_id(path: Path) -> str | None:
    text = path.read_bytes().decode("utf-8", "replace")
    if not text.lstrip("\ufeff").startswith("---"):
        return None
    front = text.lstrip("\ufeff").split("---", 2)
    match = _FRONT_ID.search(front[1]) if len(front) > 2 else None
    return match.group(1) if match else None


def import_plan(repo: Path, compile_from: list[PurePosixPath]) -> list[list[PurePosixPath]]:
    """Which ADR-*.md files each ``mneme adr import`` call sees (AMB-R2-06).

    The pinned importer reads a directory's own sorted ``ADR-*.md`` listing.
    When ``compile_from`` is exactly that listing of one directory, one import
    of it compiles the list in its order. Otherwise each file is imported on
    its own, in list order.
    """
    if any(not re.fullmatch(r"ADR-.*\.md", p.name) for p in compile_from):
        raise CaseFailure("memory.compile_from names a file the ADR import does not read")
    parents = {p.parent for p in compile_from}
    if len(parents) == 1:
        (parent,) = parents
        listing = sorted(f.name for f in (repo / _native(parent)).glob("ADR-*.md"))
        if [p.name for p in compile_from] == listing:
            return [list(compile_from)]
    return [[p] for p in compile_from]


def build_memory(case: Case, layout: Layout, impl_python: str, scratch: Path,
                 import_path: str | None = None) -> tuple[bytes | None, dict]:
    """README step 4: compile the memory with the implementation build's own ADR import."""
    spec = case.case.get("memory")
    if spec is None or not (spec.get("compile_from") or []):
        return None, {"built": False}
    if _safe_relative(spec.get("path"), "memory.path").as_posix() != ".mneme/project_memory.json":
        raise CaseFailure("memory.path is not .mneme/project_memory.json")
    compile_from = [_safe_relative(p, "memory.compile_from") for p in spec["compile_from"]]
    if len(set(compile_from)) != len(compile_from):
        raise CaseFailure("memory.compile_from repeats a file")
    for rel in compile_from:
        if not (layout.repo / _native(rel)).is_file():
            raise CaseFailure("memory.compile_from names a file the fixture does not have")
    want_ids = [_adr_id(layout.repo / _native(rel)) for rel in compile_from]
    memory = layout.repo / ".mneme" / "project_memory.json"
    env = base_env(impl_python, scratch, import_path)
    result = run_process([impl_python, "-m", "mneme", "init", "--path", str(memory)],
                         cwd=layout.repo, env=env)
    if result["exit"] != 0:
        raise CaseFailure(f"memory compile failed (init: exit {result['exit']})")
    plan = import_plan(layout.repo, compile_from)
    hidden = scratch / "hidden-adrs"
    for group in plan:
        directory = layout.repo / _native(group[0].parent)
        keep = {p.name for p in group}
        moved = []
        if len(plan) > 1:
            hidden.mkdir(exist_ok=True)
            for other in sorted(directory.glob("ADR-*.md")):
                if other.name not in keep:
                    shutil.move(str(other), str(hidden / other.name))
                    moved.append(other.name)
        result = run_process([impl_python, "-m", "mneme", "adr", "import", str(directory),
                              "--memory", str(memory), "--apply"], cwd=layout.repo, env=env)
        for name in moved:
            shutil.move(str(hidden / name), str(directory / name))
        if result["exit"] != 0:
            raise CaseFailure(f"memory compile failed (adr import: exit {result['exit']})")
    data = memory.read_bytes()
    ids, rules = typed_rules_of(load_json_bytes(data))
    if any(i is None or i not in ids for i in want_ids):
        raise CaseFailure("compiled memory lacks a compile_from decision")
    return data, {"built": True, "imports": len(plan), "decision_ids": ids,
                  "typed_rules": rules}


def target_path_of(case: Case, layout: Layout) -> Path:
    target = case.case.get("target") or {}
    root = target.get("root")
    if root not in TARGET_ROOTS or not _nonempty_str(target.get("rel")):
        raise CaseFailure("target is malformed")
    base = {"repo": layout.repo, "outside": layout.outside, "case": layout.case}[root]
    return Path(str(base) + os.sep + _native_separators(target["rel"]))


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

    @property
    def layout(self) -> Layout:
        return Layout.at(self.work / "c")

    @property
    def scratch(self) -> Path:
        return self.work / "scratch"


def _fresh_scratch(ctx: Context) -> Path:
    _rmtree(ctx.scratch)
    for name in ("tmp", "home"):
        (ctx.scratch / name).mkdir(parents=True)
    return ctx.scratch


def _process_cwd(envelope: dict, layout: Layout) -> Path:
    cwd_value = envelope.get("cwd")
    return Path(cwd_value) if isinstance(cwd_value, str) and os.path.isdir(cwd_value) \
        else layout.case


# R2 §5 G6 steps 2-4, evaluated by the pinned implementation build itself.
_EVIDENCE_EVAL = r"""
import json, sys
from mneme.integrations.claude_code import hook
data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
host = tuple(data["host"])
out = [{"per_rule": hook.relevant_enforcement_per_rule(r, host),
        "event": hook.relevant_enforcement_observed(r, host),
        "evaluation_complete": hook.recorded_evaluation_complete(r)}
       for r in data["records"]]
sys.stdout.write(json.dumps(out, sort_keys=True))
"""


def evaluate_records(records: list, ctx: Context, python: str, cwd: Path,
                     env: dict[str, str]) -> list[dict]:
    """The build's own §7b values for each evidence record (not the harness's)."""
    if not records:
        return []
    stdin = json.dumps({"records": records, "host": [ctx.host_version, ctx.host_sha256]},
                       ensure_ascii=True).encode("ascii")
    result = run_process([python, "-P", "-c", _EVIDENCE_EVAL], cwd=cwd, env=env, stdin=stdin)
    if result["exit"] != 0:
        raise CaseFailure(f"evidence evaluation failed (exit {result['exit']})")
    values = json.loads(result["stdout"].decode("utf-8"))
    if not isinstance(values, list) or len(values) != len(records):
        raise CaseFailure("evidence evaluation returned the wrong shape")
    return values


def run_hook(case: Case, ctx: Context, python: str, memory_bytes: bytes | None,
             evaluate: bool) -> dict:
    """One hook run on a fresh fixture copy (README steps 1-7)."""
    layout = ctx.layout
    _rmtree(layout.case)
    scratch = _fresh_scratch(ctx)
    materialize(case, layout, memory_bytes)
    envelope = substitute_envelope(case.envelope_text, layout)
    target = target_path_of(case, layout)
    evidence_log = scratch / "evidence.jsonl"
    observe_log = scratch / "observe.jsonl"
    env = base_env(python, scratch)
    env.update({
        "PYTHONPATH": os.pathsep.join(p for p in (str(SHIM_DIR), ctx.import_path) if p),
        OBSERVE_LOG_ENV: str(observe_log),
        "MNEME_HOOK_MODE": case.case["hook_mode"],
        "MNEME_HOOK_EVIDENCE_LOG": str(evidence_log),
        "MNEME_HOOK_EVIDENCE_HOST_VERSION": ctx.host_version,
        "MNEME_HOOK_EVIDENCE_HOST_SHA256": ctx.host_sha256,
    })
    cwd = _process_cwd(json.loads(envelope), layout)
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
    observed = {
        "exit": result["exit"],
        "stdout_b64": b64(result["stdout"]), "stdout_sha256": sha256_bytes(result["stdout"]),
        "stderr_b64": b64(result["stderr"]), "stderr_sha256": sha256_bytes(result["stderr"]),
        "disposition": observed_disposition(result["exit"], result["stdout"]),
        "cwd": "envelope" if cwd != layout.case else "case_root",
        "target_before": before, "target_after": after,
        "evidence_records": evidence, "evidence_log_sha256": evidence_sha,
        "invocations": invocations,
    }
    if evaluate:
        eval_env = base_env(python, scratch, ctx.import_path)
        observed["evidence_evaluation"] = evaluate_records(evidence, ctx, python, cwd, eval_env)
    return observed


def run_checker_pair(case: Case, ctx: Context, memory_bytes: bytes | None) -> dict:
    """G5 checker level: ``--proposed-new-file`` against ``--input``, same carrier."""
    layout = ctx.layout
    _rmtree(layout.case)
    scratch = _fresh_scratch(ctx)
    materialize(case, layout, memory_bytes)
    envelope = json.loads(substitute_envelope(case.envelope_text, layout))
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
    memory = layout.repo / ".mneme" / "project_memory.json"
    cwd = _process_cwd(envelope, layout)
    env = base_env(ctx.impl_python, scratch, ctx.import_path)
    pair = {}
    for flag, key in (("--proposed-new-file", "proposed"), ("--input", "input")):
        argv = [ctx.impl_python, "-m", "mneme", "check", "--memory", str(memory),
                flag, str(carrier), "--query", f"edit to {file_path}",
                "--mode", case.case["hook_mode"], "--json", "--target-path", target]
        result = run_process(argv, cwd=cwd, env=env)
        if not result["launched"] or result["timed_out"]:
            raise CaseFailure(f"checker pair: {key} run did not complete")
        pair[key] = {"exit": result["exit"], "stdout_b64": b64(result["stdout"]),
                     "stdout_sha256": sha256_bytes(result["stdout"]),
                     "stderr_sha256": sha256_bytes(result["stderr"])}
    pair["carrier_sha256"] = sha256_bytes(carrier_bytes)
    return pair


def envelope_facts(case: Case, layout: Layout) -> dict:
    envelope = json.loads(substitute_envelope(case.envelope_text, layout))
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


def routed_cr_exception(case: Case, has_cr: bool) -> bool:
    """R1-PR §5 G5: a routed case whose content contains CR has no hook-level parity."""
    return case.expected.get("routed") is True and has_cr


def hook_parity_applies(case: Case, has_cr: bool) -> bool:
    """G5 hook level: P, X, L and the A1.4 baseline-observed cases, minus routed CR."""
    if routed_cr_exception(case, has_cr):
        return False
    return case.klass in HOOK_PARITY_CLASSES \
        or case.expected.get("legacy_baseline_observed") is True


def checker_parity_applies(case: Case, has_cr: bool) -> bool:
    """G5 checker level: routed P and X, and every case the routed-CR exception
    moved off hook-level parity ("scored at checker level only")."""
    routed = case.expected.get("routed") is True
    if case.klass in CHECKER_PARITY_CLASSES and routed:
        return True
    return routed_cr_exception(case, has_cr) and (
        case.klass in HOOK_PARITY_CLASSES or case.expected.get("legacy_baseline_observed") is True)


def expects_block(case: Case) -> bool:
    """G1(a) (G2V-F1; R2 §5): every strict V and VP case, and every case of any
    class (SC, MR and LIT included) whose labels expect exit 2 or a refusal.

    A1.4 baseline-observed cases carry ``"baseline_observed"`` in both labels,
    so they carry no block expectation; they never suppress the class rule.
    """
    e = case.expected
    if case.klass in ("V", "VP") and e.get("hook_mode") == "strict":
        return True
    return e.get("hook_exit") == 2 or e.get("disposition") == "refused"


def g2_applies(case: Case) -> bool:
    """G2 false block (R1-PR §5, R2V-F1).

    R1's proceed classes, plus every SC and MR case labelled to proceed
    (exit 0). Never an A1.4 baseline-observed case, and never a case labelled
    with a FORBID_LITERAL violation (the LIT exception).
    """
    e = case.expected
    if e.get("legacy_baseline_observed") is True or e.get("literal_violation") is True:
        return False
    if case.klass in PROCEED_CLASSES:
        return True
    return case.klass in LABEL_PROCEED_CLASSES and e.get("hook_exit") == 0


def execute_case(case: Case, ctx: Context) -> dict:
    """Run one case; every scoring-process failure is recorded, never raised."""
    obs: dict = {"schema": CASE_RECORD_SCHEMA, "case_id": case.case_id, "class": case.klass,
                 "public_smoke": case.public_smoke, "operational_failures": list(case.problems)}
    if case.problems:
        return obs
    layout = ctx.layout
    try:
        obs["envelope"] = envelope_facts(case, layout)
        _rmtree(layout.case)
        scratch = _fresh_scratch(ctx)
        materialize(case, layout, None)
        memory_bytes, obs["memory"] = build_memory(case, layout, ctx.impl_python, scratch,
                                                   ctx.import_path)
        obs["implementation"] = run_hook(case, ctx, ctx.impl_python, memory_bytes, True)
        obs["baseline"] = run_hook(case, ctx, ctx.base_python, memory_bytes, False)
        if checker_parity_applies(case, obs["envelope"]["content_has_cr"]):
            obs["checker_pair"] = run_checker_pair(case, ctx, memory_bytes)
    except Exception as exc:  # any harness error is a G8 failure of this case, never a crash
        detail = str(exc) if isinstance(exc, CaseFailure) else type(exc).__name__
        obs["operational_failures"].append(detail)
    finally:
        try:
            _rmtree(layout.case)
            _rmtree(ctx.scratch)
        except OSError:
            obs["operational_failures"].append("workspace could not be removed")
    return obs


# ── scoring ──────────────────────────────────────────────────────────────────

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
    """rule_id -> every FORBID_NUMERIC_ABOVE trace the hook's checker emitted."""
    traces: dict[str, list[dict]] = {}
    for payload in checker_payloads(hook_obs):
        for item in payload.get("applicability") or []:
            if isinstance(item, dict) and item.get("rule_type") == NUMERIC:
                traces.setdefault(str(item.get("rule_id")), []).append(item)
    return traces


def _resolved_normcase(path: str, cwd: Any) -> str:
    p = Path(path)
    if not p.is_absolute() and isinstance(cwd, str):
        p = Path(cwd) / p
    return os.path.normcase(str(p.resolve()))


def record_binding_problems(record: dict, facts: dict, host: tuple[str, str]) -> list[str]:
    """ADR-029 / charter §6.2 bindings of one evidence record (the digest and path join).

    Unchanged from the R1 harness. ``subject.target_path`` was resolved by
    the build while the fixture existed; the scorer re-resolves the event path
    after cleanup, so a link component can only make this stricter, never
    looser. Relevance itself is never computed here (R2 §5 G6 step 2).
    """
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
    except (AttributeError, TypeError, KeyError):
        problems.append("record_shape")
    return sorted(set(problems))


def mapped_cause(record: dict) -> str | None:
    """AMB-R2-08: the record's cause in the corpus's ``expected_cause`` vocabulary.

    See ``CAUSE_MAPPING``. The violation identities come from the record's
    own ``violations`` list, never from labels.
    """
    cause = (record.get("disposition") or {}).get("cause")
    kinds = {v.get("rule_type") for v in record.get("violations") or [] if isinstance(v, dict)}
    if cause == "numeric_violation":
        return "numeric_and_literal_violation" if LITERAL in kinds else "numeric_violation"
    if cause == "other_rule":
        return "literal_violation" if LITERAL in kinds and NUMERIC not in kinds \
            else "unmapped:other_rule"
    if cause in ("no_violation", "fail_open"):
        return cause
    return f"unmapped:{cause}"


def g6_expectation(e: dict) -> dict:
    """What G6 steps 1-4 expect.

    For a case flagged ``g6_routed_fallback`` the expectation is fixed by
    R2A1.6 as corrected by R2 Amendment 2 (A2R2.2/A2R2.3): rule-ID set {},
    per-rule {}, event-level false and ``evaluation_complete`` false. The
    stored ``null`` label is superseded by the flag alone, never by case
    identity; ``None`` (untrusted or absent) and any other value fail step 4.
    """
    if e.get("g6_routed_fallback") is True:
        return {"rule_ids": set(), "per_rule": {}, "event": False, "evaluation_complete": False}
    return {"rule_ids": set(e.get("applied_numeric_rule_ids") or []),
            "per_rule": dict(e.get("relevant_enforcement_per_rule") or {}),
            "event": e.get("relevant_enforcement_observed"),
            "evaluation_complete": e.get("evaluation_complete")}


def score_g6(case: Case, impl: dict, facts: dict, host: tuple[str, str], fail) -> None:
    """R2 §5 G6: one joined record with cause and mode, then steps 1-4 in order."""
    e = case.expected
    records = impl.get("evidence_records") or []
    evaluations = impl.get("evidence_evaluation") or []
    if e.get("evidence_record_expected") is not True:
        if records:
            fail("G6", "unexpected_record")
        return
    if len(records) != 1 or len(evaluations) != 1:
        fail("G6", f"record_count_{min(len(records), 2)}")
        return
    record, evaluation = records[0], evaluations[0]
    # G6R-F1: the record must be exactly this evidence schema, before step 1.
    # The pinned validator answers false for a malformed record, which would
    # otherwise match a case whose expected relevance values are all false.
    if record.get("schema") != EVIDENCE_SCHEMA:
        fail("G6", "schema")
    for problem in record_binding_problems(record, facts, host):
        fail("G6", f"binding:{problem}")
    if record.get("hook_outcome") != impl["disposition"]:
        fail("G6", "hook_outcome_vs_observed")
    if record.get("hook_outcome") != e.get("disposition"):
        fail("G6", "hook_outcome_vs_expected")
    if (record.get("disposition") or {}).get("mode") != e.get("hook_mode"):
        fail("G6", "mode")
    if mapped_cause(record) != e.get("expected_cause"):
        fail("G6", "cause")
    want = g6_expectation(e)
    # Step 1 (R2V-F3): the exact rule-ID set, before any value is checked.
    rules = record.get("rules") if isinstance(record.get("rules"), list) else None
    ids = [r.get("rule_id") for r in rules or [] if isinstance(r, dict)]
    if rules is None or len(ids) != len(rules) or len(set(ids)) != len(ids):
        fail("G6", "step1:rule_id_duplicate_or_malformed")
        return
    if set(ids) != want["rule_ids"]:
        fail("G6", "step1:rule_id_set")
        return
    # Step 2: the pinned build's per-rule relevance; its keys are the expected set.
    per_rule = evaluation.get("per_rule")
    if not isinstance(per_rule, dict) or set(per_rule) != want["rule_ids"]:
        fail("G6", "step2:per_rule_keys")
    elif per_rule != want["per_rule"]:
        fail("G6", "step2:per_rule_values")
    # Step 3: event level.
    if evaluation.get("event") is not want["event"]:
        fail("G6", "step3:event_level")
    # Step 4: record-wide evaluation_complete (None when not trusted).
    if evaluation.get("evaluation_complete") is not want["evaluation_complete"]:
        fail("G6", "step4:evaluation_complete")


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

    Copied unchanged from the R1 harness (G2H-F1): byte-preserving; a block
    runs from ``Traceback (most recent call last):`` to its summary line, and
    only the frame lines between them are dropped. A block with no summary
    line is ``incomplete`` and its lines are kept as non-traceback text.
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
    """A2.1: the pinned baseline's own run exited nonzero with a complete traceback block."""
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


def _expected_rules(e: dict) -> list[dict]:
    return [r for r in e.get("numeric_rules") or [] if isinstance(r, dict)]


def _nonclean(rule: dict) -> bool:
    return rule.get("matcher_outcome") in ("VIOLATION", "UNEVALUATED") \
        or rule.get("matcher_status") in ("PARTIAL", "MATCHER_UNEVALUATED")


def score_case(case: Case, obs: dict, host: tuple[str, str]) -> dict:
    """Every gate's verdict for one case. Missing observations fail closed."""
    e = case.expected
    gates: dict[str, dict] = {g: {"applies": False, "pass": True, "why": []} for g in GATES}

    def fail(gate: str, why: str) -> None:
        gates[gate]["pass"] = False
        gates[gate]["why"].append(why)

    gates["G8"]["applies"] = True
    for _failure in obs.get("operational_failures") or []:
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

    traces = numeric_traces(impl)
    records = impl.get("evidence_records") or []
    evaluations = impl.get("evidence_evaluation") or []
    diagnostics: dict = {"evidence_evaluation": evaluations,
                         "mapped_cause": [mapped_cause(r) for r in records]}

    # G1 unsafe pass (G2V-F1; R2 §5).
    gates["G1"]["applies"] = True
    if expects_block(case) and impl["exit"] != 2:
        fail("G1", "a:expected_block_not_refused")
    record_rules: dict[str, list[dict]] = {}
    for record in records:
        for rule in record.get("rules") or []:
            if isinstance(rule, dict):
                record_rules.setdefault(str(rule.get("rule_id")), []).append(rule)
    for rule in _expected_rules(e):
        if _nonclean(rule):
            rid = str(rule.get("rule_id"))
            if any(t.get("matcher_outcome") == "NO_VIOLATION"
                   for t in traces.get(rid, []) + record_rules.get(rid, [])):
                fail("G1", "b:nonclean_observed_no_violation")
    want_per_rule = g6_expectation(e)["per_rule"] if e.get("evidence_record_expected") else {}
    want_event = g6_expectation(e)["event"] if e.get("evidence_record_expected") else None
    for evaluation in evaluations:
        if evaluation.get("event") is True and want_event is not True:
            fail("G1", "c:unexpected_relevant_claim")
        per_rule = evaluation.get("per_rule") if isinstance(evaluation.get("per_rule"), dict) else {}
        if any(v is True and want_per_rule.get(k) is not True for k, v in per_rule.items()):
            fail("G1", "c:unexpected_relevant_claim_per_rule")

    # G2 false block (R1-PR §5, R2V-F1).
    if g2_applies(case):
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
    if after.get("exists") is not e.get("target_exists_after_hook"):
        fail("G3", "target_exists_after_hook_label")

    # G4 reasons: the primary reason only (R2A1.2 AMB-R2-05).
    if case.klass in REASON_CLASSES:
        gates["G4"]["applies"] = True
        for rule in _expected_rules(e):
            want = rule.get("primary_reason")
            if want is None:
                continue
            got = [t.get("primary_reason") for t in traces.get(str(rule.get("rule_id")), [])]
            if not got or any(g != want for g in got):
                fail("G4", "primary_reason")

    # G5 parity: hook level raw bytes, or Amendment 2 where the baseline raised;
    # checker level stdout + exit.
    has_cr = bool(facts.get("content_has_cr"))
    if hook_parity_applies(case, has_cr):
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
    if checker_parity_applies(case, has_cr):
        gates["G5"]["applies"] = True
        pair = obs.get("checker_pair")
        if pair is None:
            fail("G5", "checker_pair_missing")
        else:
            if pair["proposed"]["exit"] != pair["input"]["exit"]:
                fail("G5", "checker_exit")
            if pair["proposed"]["stdout_sha256"] != pair["input"]["stdout_sha256"]:
                fail("G5", "checker_stdout")

    # G6 evidence (R2 §5, R2V-F3, R2A1.6).
    gates["G6"]["applies"] = True
    score_g6(case, impl, facts, host, fail)

    diagnostics["conformance"] = label_conformance(case, obs, traces)
    return {"gates": gates, "diagnostics": diagnostics}


def label_conformance(case: Case, obs: dict, traces: dict) -> list[str]:
    """Labels not covered by a gate, compared for the record only (non-gating)."""
    e, impl = case.expected, obs["implementation"]
    out = []
    if isinstance(e.get("hook_exit"), int) and e["hook_exit"] != impl["exit"]:
        out.append("hook_exit")
    if e.get("disposition") != "baseline_observed" and e.get("disposition") != impl["disposition"]:
        out.append("disposition")
    flags = [inv.get("input_flag") for inv in impl.get("invocations") or []]
    if (flags == ["--proposed-new-file"]) != (e.get("routed") is True):
        out.append("routed")
    if e.get("checker_invoked") is not None and bool(flags) != e["checker_invoked"]:
        out.append("checker_invoked")
    payloads = checker_payloads(impl)
    kinds = sorted({str((p.get("subject") or {}).get("input_kind")) if p.get("subject")
                    else "None" for p in payloads}) or ["None"]
    if e.get("checker_invoked") is not None and kinds != [str(e.get("subject_kind"))]:
        out.append("subject_kind")
    for rule in _expected_rules(e):
        got = traces.get(str(rule.get("rule_id")))
        if not got:
            out.append("numeric_rules.rule_id_not_observed" if rule.get("rule_id_form_verified")
                       else "numeric_rules.informational_rule_id_not_observed")
            continue
        for field_name, key in (("applicability", "outcome"), ("matcher_status", "matcher_status"),
                                ("matcher_outcome", "matcher_outcome"),
                                ("primary_reason", "primary_reason")):
            if any(t.get(key) != rule.get(field_name) for t in got):
                out.append(f"numeric_rules.{field_name}")
        # R2A1.2 AMB-R2-05: distinct unknown-source reasons, compared as sets.
        want = set(rule.get("unknown_source_reason_set") or [])
        if any({s.get("reason") for s in t.get("unknown_sources") or [] if isinstance(s, dict)}
               != want for t in got):
            out.append("numeric_rules.unknown_source_reason_set")
    expected_ids = {str(r.get("rule_id")) for r in _expected_rules(e)}
    if any(rid not in expected_ids for rid in traces):
        out.append("numeric_rules.unexpected_rule_observed")
    facts = obs.get("envelope") or {}
    if e.get("content_utf8_sha256", case.case.get("content_utf8_sha256")) != \
            facts.get("content_sha256") or case.case.get("content_utf8_sha256") != \
            facts.get("content_sha256"):
        out.append("content_utf8_sha256")
    if e.get("routed_cr_parity_exception") is not routed_cr_exception(
            case, bool(facts.get("content_has_cr"))):
        out.append("routed_cr_parity_exception")
    # The stored evaluation_complete of a flagged case is null (R2A1.6) or, if
    # authored after R2 Amendment 2, false; either is consistent (A2R2.3).
    if e.get("g6_routed_fallback") is True and (
            e.get("applied_numeric_rule_ids") != [] or e.get("relevant_enforcement_per_rule") != {}
            or e.get("relevant_enforcement_observed") is not False
            or not (e.get("evaluation_complete") is None
                    or e.get("evaluation_complete") is False)):
        out.append("label_inconsistent_with_r2a1_6")
    if e.get("evidence_record_expected") is True and e.get("g6_routed_fallback") is not True:
        per_rule = e.get("relevant_enforcement_per_rule") or {}
        if set(per_rule) != set(e.get("applied_numeric_rule_ids") or []) or \
                e.get("relevant_enforcement_observed") is not any(per_rule.values()):
            out.append("label_internal_g6_inconsistency")
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
    "Amendment 2 (R1 pre-registration, A2.1-A2.3): a G5 hook-level case is in scope only "
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


R2_AMENDMENT_2 = (
    "R2 Amendment 2 (A2R2.2, A2R2.3): for every case flagged g6_routed_fallback, G6 "
    "expects evaluation_complete false (R2A1.6 had null); the stored null label is "
    "read as false by the flag alone, and no other label is reinterpreted. An untrusted "
    "or absent value (recorded_evaluation_complete() returns None), or any other value, "
    "fails step 4. No case is excluded from any gate."
)


def r2_amendment_2_summary(scored: list[tuple[Case, dict]]) -> dict:
    """A2R2.4: flagged routed-fallback cases by class, and their G6 outcome."""
    by_class: dict[str, dict[str, int]] = {}
    for case, result in scored:
        if case.expected.get("g6_routed_fallback") is not True:
            continue
        row = by_class.setdefault(case.klass, {"cases": 0, "g6_pass": 0, "g6_fail": 0})
        row["cases"] += 1
        row["g6_pass" if result["gates"]["G6"]["pass"] else "g6_fail"] += 1
    return {"applied": True, "flagged_cases": sum(r["cases"] for r in by_class.values()),
            "by_class": dict(sorted(by_class.items())), "rule": R2_AMENDMENT_2}


def run_pass(cases: list[Case], ctx: Context, host: tuple[str, str], out_dir: Path) -> dict:
    out_dir.mkdir(parents=True)
    scored: list[tuple[Case, dict]] = []
    lines: dict[bool, list[str]] = {False: [], True: []}
    for case in cases:
        obs = execute_case(case, ctx)
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
                     "amendment_2": amendment_2_summary(smoke),
                     "r2_amendment_2": r2_amendment_2_summary(smoke)}
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
        "r2_amendment_2": r2_amendment_2_summary(concealed),
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
          public_smoke: Path | None = None, pins: Pins = R2_PINS) -> dict:
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"--out {out_dir} must be new or empty")
    out_dir.mkdir(parents=True, exist_ok=True)
    final: dict = {"schema": SUMMARY_SCHEMA, "started": _utc(), "pins": pins_record(pins),
                   "harness": harness_digests(), "disclosures": list(DISCLOSURES),
                   "cause_mapping": list(CAUSE_MAPPING),
                   "host_identity_input": {"version": host_version,
                                           "executable_sha256": host_sha256}}
    try:
        if not _nonempty_str(host_version) or not _is_sha256(host_sha256):
            raise Refusal("host_identity", "--host-version must be non-empty and "
                                           "--host-sha256 a lowercase SHA-256")
        root = check_run_root(run_root or Path(tempfile.gettempdir()) / "mneme-g2r2-run")
        probe_dir = Path(tempfile.mkdtemp(prefix="g2r2-pre-"))
        try:
            final["builds"] = verify_builds(impl_python, impl_wheel, base_python, base_wheel,
                                            probe_dir, pins)
        finally:
            _rmtree(probe_dir)
        final["corpus"], cases = verify_corpus(corpus, pins, corpus_tar, public_smoke)
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
    a2r2 = final["r2_amendment_2"]
    final["headline"] += (f" R2 Amendment 2 applied: {a2r2['flagged_cases']} routed-fallback "
                          f"case(s) scored with evaluation_complete false, by class "
                          f"{json.dumps(a2r2['by_class'], sort_keys=True)}.")
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
    gates["G7"] = {"pass": g7["pass"], "applicable": sum(1 for c in cases if not c.public_smoke),
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
        "r2_amendment_2": summaries[0]["r2_amendment_2"],
    }


def _finish(out_dir: Path, final: dict) -> dict:
    final["finished"] = _utc()
    (out_dir / "summary.json").write_text(dump_json(final), encoding="ascii", newline="\n")
    return final


# ── build ────────────────────────────────────────────────────────────────────

def build(out: Path, python: str, pins: Pins = R2_PINS) -> dict:
    """Build both pinned wheels from git and install each into its own venv.

    Needs network access for the build backend and runtime dependencies.
    Records each wheel's SHA-256 and each environment's ``pip freeze``
    digest in ``<out>/build.json``. (Copied from the R1 harness, R2 pins.)
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
    s.add_argument("--public-smoke", type=Path, default=None,
                   help="the public smoke folder (PUBLIC_FILES.sha256), run non-gating")
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
                  corpus_tar=args.corpus_tar, public_smoke=args.public_smoke)
    print(final.get("headline") or final.get("refusal"))
    print(f"result: {final['result']}")
    return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 1}.get(final["result"], 2)


if __name__ == "__main__":
    sys.exit(main())

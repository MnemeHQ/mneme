#!/usr/bin/env python3
"""CI1.3 P2: replay the CI1.2 contract corpus against a pinned, installed evaluator.

The merged CI1.2 runners (``tests/test_ci1_contract_fixtures.py``,
``tests/test_ci1_contract_matrix.py``) set ``PYTHONPATH`` to this checkout, so
they test the tree under review, never a release. This preflight implements
the separate replay the CI1.3 charter requires (§4a,
``docs/plans/2026-10-17-ci1-3-isolated-merge-blocking-experiment-charter.md``):

1. Resolve ``mneme-hq==<version>`` and its runtime dependencies, check every
   downloaded wheel against the sha256 PyPI publishes for it (and the
   ``mneme-hq`` wheel against the digest pinned here), then install them into
   a fresh venv with ``pip install --require-hashes --no-index``.
2. Run the installed CLI as ``<venv python> -I -m mneme.cli`` with
   ``PYTHONPATH`` removed and a working directory outside any checkout.
3. Verify the evaluator identity before and after the replay: interpreter,
   ``mneme.__file__`` inside the venv's site-packages, the distribution
   version, the installed files against the wheel's ``RECORD``, the wheel
   sha256 and the entry point. Any mismatch fails the preflight.
4. Copy each corpus ``vN/`` to a temporary directory and replay every case in
   its ``cases.json`` against the expectation that applies to it.
5. Run the ADR-005 global-rule cross-check, the corpus memory regeneration
   checks and the stub classifier checks separately, and report them
   separately.
6. Write a JSON report and a Markdown validation record.

Test-execution contract only: nothing here changes the enforcement engine, the
existing runners or any fixture expectation. Where the installed build differs
from a golden, the build fails parity; the ``v1`` goldens are never edited.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.util
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPORA_DIR = REPO_ROOT / "tests" / "fixtures" / "ci1_contract"
MATRIX_TESTS = REPO_ROOT / "tests" / "test_ci1_contract_matrix.py"
CANONICAL_MEMORY = REPO_ROOT / ".mneme" / "project_memory.json"

DISTRIBUTION = "mneme-hq"
DEFAULT_VERSION = "0.10.0"
# sha256 of mneme_hq-0.10.0-py3-none-any.whl as published on PyPI
# (https://pypi.org/pypi/mneme-hq/0.10.0/json). The preflight also re-reads the
# digest from PyPI at run time; both must agree with the downloaded file.
PINNED_WHEEL_SHA256 = {
    "0.10.0": "fc7e0ec7191e243e998055d34e5764e473aa439ecdc40c22a969acf376ec5312",
}
ENTRY_MODULE = "mneme.cli"
CONSOLE_SCRIPT = ("mneme", "mneme.cli:main")
PYPI_JSON = "https://pypi.org/pypi/{name}/{version}/json"

# Files pip writes into dist-info at install time; not part of the wheel.
INSTALL_TIME_DIST_INFO = {"RECORD", "INSTALLER", "REQUESTED", "direct_url.json"}

# The consistent stub matrix of tests/test_ci1_contract_matrix.py
# (test_consistent_stub_output_classifies). The parametrize list is not
# importable, so it is restated; the unit tests pin it to the source.
CONSISTENT_STUBS = [
    ("strict", "PASS", 0, "VERIFIED_PASS"),
    ("warn", "PASS", 0, "VERIFIED_PASS"),
    ("strict", "WARN", 1, "VIOLATION"),
    ("warn", "WARN", 0, "VIOLATION"),
    ("strict", "FAIL", 2, "VIOLATION"),
    ("warn", "FAIL", 0, "VIOLATION"),
]


class PreflightError(RuntimeError):
    """A hard failure: the evaluator cannot be trusted, so nothing is replayed."""


# ── shared contract logic, loaded from the merged CI1.2.2 matrix ─────────────

def load_matrix_module():
    """Load ``tests/test_ci1_contract_matrix.py`` so the classifier, the stub
    battery and the ADR-005 constants are the merged ones, not a copy."""
    spec = importlib.util.spec_from_file_location("ci1_contract_matrix", MATRIX_TESTS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── step 1: hash-checked install ─────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wheel_name_version(filename: str) -> tuple[str, str]:
    """``{name}-{version}(-{build})?-{py}-{abi}-{plat}.whl`` -> (name, version)."""
    if not filename.endswith(".whl"):
        raise PreflightError(f"not a wheel (sdists are not accepted): {filename}")
    parts = filename[:-4].split("-")
    if len(parts) not in (5, 6):
        raise PreflightError(f"unparseable wheel filename: {filename}")
    return parts[0], parts[1]


def fetch_pypi_digests(name: str, version: str) -> dict[str, str]:
    """Return ``{filename: sha256}`` for one release from PyPI's JSON API."""
    url = PYPI_JSON.format(name=name, version=version)
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = json.load(resp)
    return {u["filename"]: u["digests"]["sha256"] for u in data["urls"]}


def verify_downloads(
    download_dir: Path,
    version: str,
    pinned_sha256: str,
    pypi_digests: Callable[[str, str], dict[str, str]] = fetch_pypi_digests,
    evaluator_from_pypi: bool = True,
) -> list[dict[str, str]]:
    """Check every downloaded wheel against PyPI's published sha256, and the
    evaluator wheel against the pinned digest as well. Returns the lock.

    A commit build (``evaluator_from_pypi=False``) is not on PyPI; its wheel
    is checked against the digest recorded when it was built instead."""
    lock = []
    evaluator = None
    for wheel in sorted(download_dir.iterdir()):
        name, ver = wheel_name_version(wheel.name)
        local = sha256_file(wheel)
        is_evaluator = name.replace("_", "-").lower() == DISTRIBUTION
        if evaluator_from_pypi or not is_evaluator:
            published = pypi_digests(name, ver).get(wheel.name)
            if published is None:
                raise PreflightError(f"{wheel.name}: PyPI publishes no file of that name")
            if local != published:
                raise PreflightError(f"{wheel.name}: sha256 {local} != PyPI {published}")
        entry = {"name": name, "version": ver, "filename": wheel.name, "sha256": local}
        if is_evaluator:
            if ver != version:
                raise PreflightError(f"resolved {DISTRIBUTION} {ver}, expected {version}")
            if local != pinned_sha256:
                raise PreflightError(f"{wheel.name}: sha256 {local} != pinned {pinned_sha256}")
            evaluator = entry
        lock.append(entry)
    if evaluator is None:
        raise PreflightError(f"no {DISTRIBUTION} wheel was downloaded")
    return lock


def requirements_text(lock: list[dict[str, str]]) -> str:
    return "".join(f"{e['name']}=={e['version']} --hash=sha256:{e['sha256']}\n" for e in lock)


def venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def clean_env() -> dict[str, str]:
    """The caller's environment without anything that redirects imports."""
    drop = {"PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE", "PIP_REQUIRE_VIRTUALENV"}
    return {k: v for k, v in os.environ.items() if k.upper() not in drop}


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=cwd, env=clean_env(), capture_output=True, text=True, encoding="utf-8",
    )


def _checked(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    proc = _run(cmd, cwd)
    if proc.returncode != 0:
        raise PreflightError(f"command failed ({proc.returncode}): {cmd}\n{proc.stderr}")
    return proc


def create_venv(work: Path) -> Path:
    venv = work / "venv"
    _checked([sys.executable, "-I", "-m", "venv", str(venv)], work)
    return venv


def build_commit_wheel(work: Path, venv: Path, ref: str) -> dict[str, str]:
    """Charter fallback: build the evaluator wheel from a pinned commit.

    The source is exported with ``git archive`` into the scratch directory, so
    the build never reads the working tree. The build backend (setuptools) is
    fetched by pip's build isolation without hash checking; the resulting
    wheel's sha256 is what pins the evaluator."""
    commit = git("rev-parse", "--verify", f"{ref}^{{commit}}")
    src = work / "src"
    src.mkdir()
    archive = subprocess.run(["git", "archive", "--format=tar", commit], cwd=REPO_ROOT,
                             capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
        tf.extractall(src, filter="data")
    built = work / "built"
    _checked([str(venv_python(venv)), "-I", "-m", "pip", "wheel", "--no-deps", "--disable-pip-version-check",
              "--wheel-dir", str(built), str(src)], work)
    [wheel] = list(built.glob("*.whl"))
    _name, version = wheel_name_version(wheel.name)
    return {"commit": commit, "wheel": str(wheel), "version": version, "sha256": sha256_file(wheel)}


def install_evaluator(
    work: Path, venv: Path, version: str, pinned_sha256: str, local_wheel: Path | None = None,
) -> dict[str, Any]:
    downloads = work / "wheels"
    downloads.mkdir()
    py = str(venv_python(venv))
    target = str(local_wheel) if local_wheel else f"{DISTRIBUTION}=={version}"
    _checked([py, "-I", "-m", "pip", "download", "--only-binary=:all:", "--disable-pip-version-check",
              "--dest", str(downloads), target], work)
    lock = verify_downloads(downloads, version, pinned_sha256, evaluator_from_pypi=local_wheel is None)
    requirements = work / "requirements.lock.txt"
    requirements.write_text(requirements_text(lock), encoding="utf-8")
    _checked([py, "-I", "-m", "pip", "install", "--require-hashes", "--no-index",
              "--no-deps", "--disable-pip-version-check",
              "--find-links", str(downloads), "-r", str(requirements)], work)
    pip_version = _checked([py, "-I", "-m", "pip", "--version"], work).stdout.strip()
    evaluator = next(e for e in lock if e["name"].replace("_", "-").lower() == DISTRIBUTION)
    return {
        "venv": venv, "python": venv_python(venv), "wheel": downloads / evaluator["filename"],
        "wheel_sha256": evaluator["sha256"], "lock": lock, "pip": pip_version,
    }


# ── step 3: evaluator identity ───────────────────────────────────────────────

PROBE = r"""
import importlib.metadata as md, json, os, sys, sysconfig
import mneme, mneme.cli
dist = md.distribution(sys.argv[1])
print(json.dumps({
    "executable": sys.executable,
    "prefix": sys.prefix,
    "base_prefix": sys.base_prefix,
    "python_version": sys.version.split()[0],
    "isolated": sys.flags.isolated,
    "cwd": os.getcwd(),
    "sys_path": sys.path,
    "purelib": sysconfig.get_paths()["purelib"],
    "mneme_file": mneme.__file__,
    "mneme_cli_file": mneme.cli.__file__,
    "version": md.version(sys.argv[1]),
    "console_scripts": {e.name: e.value for e in dist.entry_points if e.group == "console_scripts"},
}))
"""


def probe_identity(python: Path, cwd: Path) -> dict[str, Any]:
    proc = _checked([str(python), "-I", "-c", PROBE, DISTRIBUTION], cwd)
    return json.loads(proc.stdout)


def _is_within(path: str | Path, root: str | Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def identity_errors(probe: dict[str, Any], venv: Path, repo_root: Path, version: str) -> list[str]:
    """Every way the executing evaluator could differ from the pinned install."""
    errors = []
    if not _is_within(probe["executable"], venv):
        errors.append(f"interpreter {probe['executable']} is not inside venv {venv}")
    if not _is_within(probe["prefix"], venv):
        errors.append(f"sys.prefix {probe['prefix']} is not the venv")
    if probe["isolated"] != 1:
        errors.append("interpreter is not running in isolated mode (-I)")
    if not _is_within(probe["purelib"], venv):
        errors.append(f"site-packages {probe['purelib']} is not inside the venv")
    for key in ("mneme_file", "mneme_cli_file"):
        if not _is_within(probe[key], probe["purelib"]):
            errors.append(f"{key} {probe[key]} is not inside {probe['purelib']}")
        if _is_within(probe[key], repo_root):
            errors.append(f"{key} {probe[key]} resolves into the checkout {repo_root}")
    for entry in probe["sys_path"]:
        if entry and _is_within(entry, repo_root):
            errors.append(f"sys.path entry {entry} is inside the checkout")
    if _is_within(probe["cwd"], repo_root):
        errors.append(f"working directory {probe['cwd']} is inside the checkout")
    if probe["version"] != version:
        errors.append(f"{DISTRIBUTION} version {probe['version']} != pinned {version}")
    name, target = CONSOLE_SCRIPT
    if probe["console_scripts"].get(name) != target:
        errors.append(f"console script {name} -> {probe['console_scripts'].get(name)}, expected {target}")
    return errors


def _record_rows(text: str) -> dict[str, str]:
    return {row[0]: row[1] for row in csv.reader(io.StringIO(text)) if row}


def record_errors(wheel: Path, purelib: Path, version: str) -> tuple[int, list[str]]:
    """Compare every installed file named in the wheel's own RECORD with the
    hash that RECORD carries. Returns (files verified, errors)."""
    dist_info = f"mneme_hq-{version}.dist-info"
    with zipfile.ZipFile(wheel) as zf:
        wheel_record = _record_rows(zf.read(f"{dist_info}/RECORD").decode("utf-8"))
    installed_record_path = purelib / dist_info / "RECORD"
    if not installed_record_path.is_file():
        return 0, [f"installed RECORD missing at {installed_record_path}"]
    installed_record = _record_rows(installed_record_path.read_text(encoding="utf-8"))
    errors = []
    verified = 0
    for rel, hash_spec in sorted(wheel_record.items()):
        if not hash_spec:  # RECORD lists itself without a hash
            continue
        algo, _, expected = hash_spec.partition("=")
        if algo != "sha256":
            errors.append(f"{rel}: unsupported hash {algo}")
            continue
        if installed_record.get(rel) != hash_spec:
            errors.append(f"{rel}: installed RECORD {installed_record.get(rel)} != wheel {hash_spec}")
        target = purelib / rel
        if not target.is_file():
            errors.append(f"{rel}: not installed")
            continue
        actual = base64.urlsafe_b64encode(hashlib.sha256(target.read_bytes()).digest()).rstrip(b"=").decode()
        if actual != expected:
            errors.append(f"{rel}: installed file hash differs from the wheel RECORD")
        verified += 1
    for rel in sorted(installed_record):
        top = rel.split("/")[0]
        if rel in wheel_record or top.endswith("__pycache__") or "/__pycache__/" in rel:
            continue
        if top == dist_info and rel.split("/")[-1] in INSTALL_TIME_DIST_INFO:
            continue
        if top.startswith("..") or top == "..":  # console-script launchers outside site-packages
            continue
        errors.append(f"{rel}: installed but not in the wheel RECORD")
    package_dir = purelib / "mneme"
    for path in sorted(package_dir.rglob("*.py")):
        rel = path.relative_to(purelib).as_posix()
        if rel not in wheel_record:
            errors.append(f"{rel}: present in site-packages but not in the wheel")
    return verified, errors


# ── step 4: corpus replay ────────────────────────────────────────────────────

class Evaluator:
    """The installed CLI, invoked the one way the preflight allows."""

    def __init__(self, python: Path):
        self.python = Path(python)
        self.prefix = [str(self.python), "-I", "-m", ENTRY_MODULE]

    def run(self, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
        return _run([*self.prefix, *args], cwd)


def corpus_versions(corpora_dir: Path = CORPORA_DIR) -> list[tuple[str, str, Path]]:
    found = []
    for cases in sorted(corpora_dir.glob("*/v*/cases.json")):
        found.append((cases.parent.parent.name, cases.parent.name, cases.parent))
    return found


def check_args(spec: dict, case: dict, query: str, top: int) -> list[str]:
    """The invocation the merged runners use for a golden case."""
    args = [
        "check", "--memory", spec["memory"], "--input", case["input"],
        "--query", query, "--top", str(top), "--mode", case["mode"],
    ]
    if spec.get("adr_dir"):
        args += ["--adr-dir", spec["adr_dir"]]
    args.append("--json")
    if case["target_path"]:
        args += ["--target-path", case["target_path"]]
    return args


def last_line(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1][:300] if lines else ""


def rule_record_note(records: list, rule_id: str) -> str:
    """Why no record matched ``rule_id``: absent, or present without identity."""
    matching = [r for r in records if isinstance(r, dict) and r.get("rule_id") == rule_id]
    if matching:
        return f"{len(matching)} record(s) for {rule_id}: {matching}"
    decision = rule_id.split(":")[0]
    unlabeled = [r for r in records if isinstance(r, dict) and r.get("decision_id") == decision]
    if unlabeled:
        missing = sorted({"rule_id", "decision_version_id"} - set().union(*(r.keys() for r in unlabeled)))
        return (f"{len(unlabeled)} {decision} record(s) present but none carries rule_id {rule_id}"
                + (f" (fields absent: {', '.join(missing)})" if missing else ""))
    return f"no {decision} record"


def record_field_diffs(actual: dict, expected: dict) -> list[str]:
    """Name the record fields a build adds or drops, so a parity failure says
    *what* differs (for example a missing ``rule_id``), not only where."""
    out = []
    for key in ("applicability", "violations"):
        got, want = actual.get(key), expected.get(key)
        if not isinstance(got, list) or not isinstance(want, list) or got == want:
            continue
        got_fields = set().union(*(r.keys() for r in got if isinstance(r, dict)))
        want_fields = set().union(*(r.keys() for r in want if isinstance(r, dict)))
        if missing := sorted(want_fields - got_fields):
            out.append(f"{key} records lack {', '.join(missing)}")
        if extra := sorted(got_fields - want_fields):
            out.append(f"{key} records add {', '.join(extra)}")
        if len(got) != len(want):
            out.append(f"{key}: {len(got)} records, golden has {len(want)}")
    return out


def compare_golden(
    m, case: dict, expected: dict, proc: subprocess.CompletedProcess, require_empty_stderr: bool,
) -> list[str]:
    diffs = []
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        return [f"exit {proc.returncode}, stdout is not a single JSON payload "
                f"({proc.stdout[:80]!r}); stderr ends {last_line(proc.stderr)!r}"]
    if not isinstance(payload, dict):
        return ["stdout payload is not a JSON object"]
    try:
        canonical = m._canonical(payload)
    except (KeyError, TypeError) as exc:
        canonical = payload
        diffs.append(f"payload lacks applicability/violations records: {exc!r}")
    if canonical != expected:
        keys = sorted(set(canonical) | set(expected))
        changed = [k for k in keys if canonical.get(k) != expected.get(k)]
        diffs.append(f"payload differs from golden in: {', '.join(changed)}")
        diffs += record_field_diffs(canonical, expected)
    if proc.returncode != case["expected_exit"]:
        diffs.append(f"exit {proc.returncode} != {case['expected_exit']}")
    actual_class = m.classify(proc.returncode, proc.stdout)
    if actual_class != case["expected_classification"]:
        diffs.append(f"classification {actual_class} != {case['expected_classification']}")
    if require_empty_stderr and proc.stderr != "":
        diffs.append(f"stderr not empty: {proc.stderr[:200]!r}")
    return diffs


def compare_memory_error(m, case: dict, proc: subprocess.CompletedProcess, repo_root: Path) -> list[str]:
    diffs = []
    if proc.stdout != "":
        diffs.append(f"stdout not empty: {proc.stdout[:200]!r}")
    if proc.returncode != case["expected_exit"]:
        diffs.append(f"exit {proc.returncode} != {case['expected_exit']}")
    if case["expected_stderr"] == "error_line":
        want = "ERROR: memory file project_memory.json does not exist\n"
        if proc.stderr != want:
            diffs.append(f"stderr {proc.stderr[:200]!r} != {want!r}")
    else:
        if not proc.stderr.startswith("Traceback (most recent call last):"):
            diffs.append(f"stderr is not a traceback: {proc.stderr[:200]!r}")
        if str(repo_root.resolve()) in proc.stderr:
            diffs.append("traceback names a file inside the checkout")
    actual_class = m.classify(proc.returncode, proc.stdout)
    if actual_class != case["expected_classification"]:
        diffs.append(f"classification {actual_class} != {case['expected_classification']}")
    return diffs


# Corpora whose merged runner asserts an empty stderr (test_golden_case_matches_contract).
EMPTY_STDERR_CORPORA = {"warn_verdict", "incomplete_evaluation"}


def replay_golden_corpus(m, ev: Evaluator, corpus: str, version: str, source: Path, work: Path) -> list[dict]:
    root = work / "corpora" / corpus / version
    shutil.copytree(source, root)
    spec = json.loads((root / "cases.json").read_text(encoding="utf-8"))
    results = []
    for case in spec["cases"]:
        expected = json.loads((root / case["expected"]).read_text(encoding="utf-8"))
        expected = m._canonical(expected)
        for variant in spec["query_variants"]:
            proc = ev.run(check_args(spec, case, variant["query"], variant["top"]), root)
            diffs = compare_golden(m, case, expected, proc, corpus in EMPTY_STDERR_CORPORA)
            results.append({
                "corpus": corpus, "version": version, "case": case["id"],
                "variant": f"{variant['query']!r} top={variant['top']}",
                "expected": f"{case['expected']}, exit {case['expected_exit']}, {case['expected_classification']}",
                "exit": proc.returncode, "classification": m.classify(proc.returncode, proc.stdout),
                "parity": not diffs, "diffs": diffs,
            })
    return results


def replay_memory_errors(m, ev: Evaluator, corpus: str, version: str, source: Path, work: Path) -> list[dict]:
    root = work / "corpora" / corpus / version
    shutil.copytree(source, root)
    spec = json.loads((root / "cases.json").read_text(encoding="utf-8"))
    results = []
    for case in spec["cases"]:
        for mode in spec["modes"]:
            case_dir = root / "runs" / f"{case['id']}-{mode}"
            case_dir.mkdir(parents=True)
            (case_dir / "input.md").write_text(spec["input_text"], encoding="utf-8")
            if case["memory_content"] is not None:
                (case_dir / "project_memory.json").write_text(case["memory_content"], encoding="utf-8")
            proc = ev.run([
                "check", "--memory", "project_memory.json", "--input", "input.md",
                "--query", spec["query"], "--top", str(spec["top"]), "--mode", mode, "--json",
            ], case_dir)
            diffs = compare_memory_error(m, case, proc, REPO_ROOT)
            results.append({
                "corpus": corpus, "version": version, "case": case["id"], "variant": f"mode={mode}",
                "expected": f"empty stdout, stderr {case['expected_stderr']}, exit {case['expected_exit']}, "
                            f"{case['expected_classification']}",
                "exit": proc.returncode, "classification": m.classify(proc.returncode, proc.stdout),
                "parity": not diffs, "diffs": diffs,
            })
    return results


def replay_corpora(m, ev: Evaluator, work: Path, corpora_dir: Path = CORPORA_DIR) -> list[dict]:
    results = []
    for corpus, version, source in corpus_versions(corpora_dir):
        spec = json.loads((source / "cases.json").read_text(encoding="utf-8"))
        if all("memory_content" in c for c in spec["cases"]):
            results += replay_memory_errors(m, ev, corpus, version, source, work)
        else:
            results += replay_golden_corpus(m, ev, corpus, version, source, work)
    return results


# ── step 5: checks with no manifest ──────────────────────────────────────────

def adr005_checks(m, ev: Evaluator, work: Path) -> list[dict]:
    """tests/test_ci1_contract_matrix.py §1, against a read-only copy of the
    canonical memory. The violating input is generated, never committed."""
    root = work / "adr005"
    (root / ".mneme").mkdir(parents=True)
    shutil.copy2(CANONICAL_MEMORY, root / ".mneme" / "project_memory.json")
    results = []

    index = json.loads(CANONICAL_MEMORY.read_text(encoding="utf-8"))["decision_index"]
    rules = [r for r in index["rules"] if r["rule_id"] == m.ADR005_RULE_ID]
    diffs = []
    if len(rules) != 1:
        diffs.append(f"{len(rules)} canonical rules carry {m.ADR005_RULE_ID}")
        rule = {}
    else:
        rule = rules[0]
        if rule["decision_id"] != "ADR-005" or rule["rule_type"] != "FORBID_LITERAL":
            diffs.append("rule is not ADR-005 FORBID_LITERAL")
        if rule["rule_payload"] != {"value": m.FORBIDDEN_INSTALL} or rule["applicability"] != {}:
            diffs.append("rule payload or applicability changed")
    results.append({"check": "canonical rule is a global FORBID_LITERAL", "variant": "",
                    "parity": not diffs, "diffs": diffs})

    def run(text: str, target: str | None, query: str, top: int, tag: str):
        artifact = root / f"artifact-{tag}.md"
        artifact.write_text(text, encoding="utf-8")
        args = [
            "check", "--memory", ".mneme/project_memory.json", "--input", str(artifact),
            "--query", query, "--top", str(top), "--mode", "strict", "--json",
        ]
        if target:
            args += ["--target-path", target]
        return ev.run(args, root)

    n = 0
    for query, top in m.ADR005_QUERIES:
        for target in m.ADR005_TARGETS:
            n += 1
            proc = run(f"Install with `{m.FORBIDDEN_INSTALL}`.\n", target, query, top, f"v{n}")
            diffs = []
            try:
                payload = json.loads(proc.stdout)
                if payload["schema"] != m.CONTRACT:
                    diffs.append(f"schema {payload['schema']}")
                if payload["verdict"] != "FAIL" or payload["evaluation_complete"] is not True:
                    diffs.append(f"verdict {payload['verdict']}, complete {payload['evaluation_complete']}")
                applied = [a for a in payload["applicability"] if a.get("rule_id") == m.ADR005_RULE_ID]
                if len(applied) != 1 or applied[0]["outcome"] != "APPLIED" or applied[0]["path_scoped"] is not False:
                    diffs.append("applicability: " + rule_record_note(payload["applicability"], m.ADR005_RULE_ID))
                violations = [v for v in payload["violations"] if v.get("rule_id") == m.ADR005_RULE_ID]
                if (len(violations) != 1
                        or violations[0]["decision_version_id"] != rule.get("decision_version_id")
                        or violations[0]["severity"] != "FAIL"
                        or violations[0]["trigger"] != m.FORBIDDEN_INSTALL):
                    diffs.append("violations: " + rule_record_note(payload["violations"], m.ADR005_RULE_ID))
            except (ValueError, KeyError, TypeError) as exc:
                diffs.append(f"unusable payload: {exc!r}: {proc.stdout[:200]!r} {proc.stderr[:200]!r}")
            if proc.returncode != 2:
                diffs.append(f"exit {proc.returncode} != 2")
            if m.classify(proc.returncode, proc.stdout) != m.VIOLATION:
                diffs.append(f"classification {m.classify(proc.returncode, proc.stdout)} != VIOLATION")
            results.append({"check": "violation FAILs on every path and query",
                            "variant": f"target={target} query={query!r} top={top}",
                            "parity": not diffs, "diffs": diffs})

    for target in m.ADR005_TARGETS:
        n += 1
        proc = run(f"Install with `{m.FORBIDDEN_INSTALL}-hq`.\n", target, "pip install", 3, f"c{n}")
        diffs = []
        try:
            payload = json.loads(proc.stdout)
            if [v for v in payload["violations"] if v.get("rule_id") == m.ADR005_RULE_ID]:
                diffs.append("rule fired on the correct distribution name")
            applied = [a for a in payload["applicability"] if a.get("rule_id") == m.ADR005_RULE_ID]
            if len(applied) != 1 or applied[0]["outcome"] != "APPLIED":
                diffs.append("applicability: " + rule_record_note(payload["applicability"], m.ADR005_RULE_ID))
            if payload["verdict"] != "PASS" or payload["evaluation_complete"] is not True:
                diffs.append(f"verdict {payload['verdict']}, complete {payload['evaluation_complete']}")
        except (ValueError, KeyError, TypeError) as exc:
            diffs.append(f"unusable payload: {exc!r}: {proc.stdout[:200]!r} {proc.stderr[:200]!r}")
        if proc.returncode != 0:
            diffs.append(f"exit {proc.returncode} != 0")
        if m.classify(proc.returncode, proc.stdout) != m.VERIFIED_PASS:
            diffs.append(f"classification {m.classify(proc.returncode, proc.stdout)} != VERIFIED_PASS")
        results.append({"check": "correct distribution name is not flagged", "variant": f"target={target}",
                        "parity": not diffs, "diffs": diffs})
    return results


def classifier_checks(m) -> list[dict]:
    """tests/test_ci1_contract_matrix.py §5 with the merged classifier and stub
    battery. These are adapter-side and build-independent; the classifier's
    agreement with the installed build's real output is part of the replay."""
    results = []
    for name, (exit_code, stdout) in m.STUBS.items():
        got = m.classify(exit_code, stdout)
        want = m.UNEVALUATED  # including fail_exit_0_strict (test_fail_payload_with_exit_0...)
        diffs = [] if got == want else [f"classified {got}, expected {want}"]
        results.append({"check": "contradictory or unparseable stub", "variant": name,
                        "parity": not diffs, "diffs": diffs})
    for mode, verdict, exit_code, want in CONSISTENT_STUBS:
        violations = [] if verdict == "PASS" else [m._VIOLATION_RECORD]
        got = m.classify(exit_code, json.dumps(m._payload(mode=mode, verdict=verdict, violations=violations)))
        diffs = [] if got == want else [f"classified {got}, expected {want}"]
        results.append({"check": "consistent stub", "variant": f"{mode} {verdict} exit {exit_code}",
                        "parity": not diffs, "diffs": diffs})
    return results


def regeneration_checks(ev: Evaluator, work: Path, corpora_dir: Path = CORPORA_DIR) -> list[dict]:
    """The installed build's `decision-index migrate` + `adr import` must
    regenerate each committed ADR-derived corpus memory byte-for-byte."""
    results = []
    for corpus, version, source in corpus_versions(corpora_dir):
        if not (source / "adr").is_dir():
            continue
        root = work / "regen" / corpus / version
        shutil.copytree(source / "adr", root / "adr")
        committed = json.loads((source / "project_memory.json").read_text(encoding="utf-8"))
        seed = {k: committed[k] for k in ("meta", "items", "examples")} | {"decisions": []}
        (root / "project_memory.json").write_text(json.dumps(seed), encoding="utf-8")
        diffs = []
        for args in (["decision-index", "migrate", "--memory", "project_memory.json", "--apply"],
                     ["adr", "import", "--memory", "project_memory.json", "--apply", "adr"]):
            proc = ev.run(args, root)
            if proc.returncode != 0:
                diffs.append(f"{args[0]} {args[1]} exited {proc.returncode}: {proc.stderr[:300]!r}")
        if not diffs:
            regenerated = json.loads((root / "project_memory.json").read_text(encoding="utf-8"))
            if regenerated != committed:
                keys = sorted(set(regenerated) | set(committed))
                diffs.append("differs in: " + ", ".join(k for k in keys if regenerated.get(k) != committed.get(k)))
                if regenerated.get("decision_index") != committed.get("decision_index"):
                    diffs.append(f"decision_index schema {regenerated.get('decision_index', {}).get('schema')!r}, "
                                 f"committed {committed.get('decision_index', {}).get('schema')!r}")
        results.append({"check": "memory regenerates from source ADRs", "variant": f"{corpus}/{version}",
                        "parity": not diffs, "diffs": diffs})
    return results


# ── step 6: record ───────────────────────────────────────────────────────────

def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()


def corpus_provenance() -> dict[str, Any]:
    dirty = git("status", "--porcelain", "--", "tests/fixtures/ci1_contract", ".mneme/project_memory.json",
                "tests/test_ci1_contract_matrix.py")
    return {
        "commit": git("rev-parse", "HEAD"),
        "corpus_tree": git("rev-parse", "HEAD:tests/fixtures/ci1_contract"),
        "canonical_memory_blob": git("rev-parse", "HEAD:.mneme/project_memory.json"),
        "matrix_tests_blob": git("rev-parse", "HEAD:tests/test_ci1_contract_matrix.py"),
        "clean": dirty == "",
        "dirty": dirty,
    }


def _section(results: list[dict], label: str) -> dict[str, Any]:
    passed = sum(1 for r in results if r["parity"])
    return {"label": label, "total": len(results), "passed": passed,
            "failed": len(results) - passed, "results": results}


def render_markdown(report: dict[str, Any]) -> str:
    ident = report["identity"]
    prov = report["corpus_provenance"]
    if report["source"]["kind"] == "pypi":
        source_line = "PyPI release"
        sha_label = "local = PyPI JSON API = pinned"
    else:
        source_line = (f"commit build of `{report['source']['commit']}` (`git archive`, `pip wheel --no-deps`); "
                       "the version string alone does not identify it, the wheel sha256 does")
        sha_label = "local build, pinned for this run"
    lines = [
        f"# CI1.3 P2 pinned-evaluator preflight: {DISTRIBUTION} {report['version']}",
        "",
        f"Generated by `scripts/ci1_evaluator_preflight.py` on {report['generated_at']}. "
        "Charter: `docs/plans/2026-10-17-ci1-3-isolated-merge-blocking-experiment-charter.md` §4a. "
        "Tracker: MnemeHQ/mneme#540.",
        "",
        f"**Verdict: {'PASS' if report['passed'] else 'FAIL'}.** "
        + ("The pinned build reproduces every CI1.2 expectation listed below."
           if report["passed"] else
           "The pinned build does not reproduce the CI1.2 corpus. Failing cases are listed below. "
           "The `v1` goldens were not edited; per the charter the fallback is a pinned "
           "`MnemeHQ/mneme` commit build."),
        "",
        "## Evaluator identity",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Distribution | `{DISTRIBUTION}=={report['version']}` |",
        f"| Source | {source_line} |",
        f"| Wheel | `{ident['wheel_filename']}` |",
        f"| Wheel sha256 ({sha_label}) | `{ident['wheel_sha256']}` |",
        f"| `importlib.metadata.version` | `{ident['probe']['version']}` |",
        f"| Installed files verified against the wheel `RECORD` | {ident['record_files_verified']} |",
        f"| Interpreter | `{ident['probe']['executable']}` (Python {ident['probe']['python_version']}, "
        f"isolated={ident['probe']['isolated']}) |",
        f"| `mneme.__file__` | `{ident['probe']['mneme_file']}` |",
        f"| Entry point invoked | `{' '.join(ident['entry_point'])}` |",
        f"| Console script metadata | `mneme = {ident['probe']['console_scripts'].get('mneme')}` |",
        f"| Working directory | outside the checkout (`{ident['probe']['cwd']}`) |",
        f"| `PYTHONPATH` | removed from the environment; `-I` also ignores `PYTHON*` variables |",
        f"| Installer | `{ident['pip']}`, `--require-hashes --no-index --no-deps` from PyPI-verified wheels |",
        f"| Host | {report['host']} |",
        f"| Identity re-checked after replay | {'yes, unchanged' if ident['rechecked'] else 'NO'} |",
        "",
        "Hash-locked runtime dependency set (each wheel's sha256 checked against PyPI's JSON API):",
        "",
        "| Package | Version | sha256 |",
        "|---|---|---|",
    ]
    lines += [f"| {e['name']} | {e['version']} | `{e['sha256']}` |" for e in ident["lock"]]
    lines += [
        "",
        "## Corpus provenance",
        "",
        f"- Commit: `{prov['commit']}`",
        f"- `tests/fixtures/ci1_contract` tree: `{prov['corpus_tree']}`",
        f"- `.mneme/project_memory.json` blob (ADR-005 cross-check): `{prov['canonical_memory_blob']}`",
        f"- `tests/test_ci1_contract_matrix.py` blob (classifier, stubs, ADR-005 constants): "
        f"`{prov['matrix_tests_blob']}`",
        f"- Working tree clean for these paths: {'yes' if prov['clean'] else 'NO'}",
        f"- Corpus versions replayed: {', '.join(report['corpus_versions'])}",
        "",
        "## Summary",
        "",
        "| Check | Runs | Parity | Failed |",
        "|---|---|---|---|",
    ]
    for key in ("replay", "adr005", "regeneration", "classifier"):
        s = report["sections"][key]
        lines.append(f"| {s['label']} | {s['total']} | {s['passed']} | {s['failed']} |")
    lines += [
        "",
        "The manifest replay alone is not validation of the whole CI1.2 suite (#540 P2 coverage note). "
        "The ADR-005 cross-check, the memory regeneration checks and the classifier checks are run and "
        "reported separately. The classifier is the merged `classify` from "
        "`tests/test_ci1_contract_matrix.py`; it is applied to every real output of the installed build in "
        "the replay and the ADR-005 check, and separately to the stub battery.",
        "",
    ]
    for key in ("replay", "adr005", "regeneration", "classifier"):
        s = report["sections"][key]
        lines += [f"## {s['label']}", ""]
        if key == "replay":
            lines += ["| Corpus | Case | Variant | Expected | Exit | Class | Parity |",
                      "|---|---|---|---|---|---|---|"]
            for r in s["results"]:
                mark = "yes" if r["parity"] else "**NO**: " + "; ".join(r["diffs"])
                lines.append(f"| {r['corpus']}/{r['version']} | `{r['case']}` | {r['variant']} | "
                             f"{r['expected']} | {r['exit']} | {r['classification']} | {mark} |")
        else:
            lines += ["| Check | Variant | Parity |", "|---|---|---|"]
            for r in s["results"]:
                mark = "yes" if r["parity"] else "**NO**: " + "; ".join(r["diffs"])
                lines.append(f"| {r['check']} | {r['variant']} | {mark} |")
        lines.append("")
    text = "\n".join(lines).replace("\\\\", "/").replace("\\", "/")
    # The scratch directory is machine-specific; the record names it <work>.
    return text.replace(Path(report["work_dir"]).as_posix(), "<work>") + "\n"


def run_preflight(version: str, work: Path, commit_build: str | None = None) -> dict[str, Any]:
    if _is_within(work, REPO_ROOT):
        raise PreflightError(f"work directory {work} must be outside the checkout")
    m = load_matrix_module()
    venv = create_venv(work)
    build = None
    if commit_build:
        build = build_commit_wheel(work, venv, commit_build)
        version, pinned = build["version"], build["sha256"]
        installed = install_evaluator(work, venv, version, pinned, Path(build["wheel"]))
    else:
        pinned = PINNED_WHEEL_SHA256.get(version)
        if pinned is None:
            raise PreflightError(f"no pinned wheel sha256 for {DISTRIBUTION} {version}")
        installed = install_evaluator(work, venv, version, pinned)
    probe = probe_identity(installed["python"], work)
    errors = identity_errors(probe, installed["venv"], REPO_ROOT, version)
    verified, rec_errors = record_errors(installed["wheel"], Path(probe["purelib"]), version)
    if errors or rec_errors or verified == 0:
        raise PreflightError("evaluator identity check failed:\n" + "\n".join(errors + rec_errors))

    ev = Evaluator(installed["python"])
    replay = replay_corpora(m, ev, work)
    adr005 = adr005_checks(m, ev, work)
    regen = regeneration_checks(ev, work)
    classifier = classifier_checks(m)

    after = probe_identity(installed["python"], work)
    _, rec_after = record_errors(installed["wheel"], Path(after["purelib"]), version)
    rechecked = after == probe and not rec_after
    if not rechecked:
        raise PreflightError("evaluator identity changed during the replay")

    sections = {
        "replay": _section(replay, "Manifest replay (cases.json x query variants / modes)"),
        "adr005": _section(adr005, "ADR-005 global-rule cross-check"),
        "regeneration": _section(regen, "Corpus memory regeneration"),
        "classifier": _section(classifier, "Classifier stub checks"),
    }
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "work_dir": str(work),
        "version": version,
        "source": ({"kind": "commit-build", "commit": build["commit"]} if build
                   else {"kind": "pypi", "index": "https://pypi.org"}),
        "host": f"{platform.system()} {platform.release()}, host Python {platform.python_version()}",
        "identity": {
            "wheel_filename": installed["wheel"].name, "wheel_sha256": installed["wheel_sha256"],
            "lock": installed["lock"], "pip": installed["pip"], "probe": probe,
            "record_files_verified": verified, "entry_point": ["<venv python>", *ev.prefix[1:]],
            "rechecked": rechecked,
        },
        "corpus_provenance": corpus_provenance(),
        "corpus_versions": [f"{c}/{v}" for c, v, _ in corpus_versions()],
        "sections": sections,
        "passed": all(s["failed"] == 0 for s in sections.values()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", default=DEFAULT_VERSION, help="mneme-hq version to pin")
    parser.add_argument("--commit-build", metavar="REF",
                        help="charter fallback: build the evaluator from this MnemeHQ/mneme commit "
                             "instead of installing the PyPI release")
    parser.add_argument("--work-dir", type=Path, help="scratch directory outside the checkout")
    parser.add_argument("--keep", action="store_true", help="keep the scratch directory")
    parser.add_argument("--json-out", type=Path, help="write the full JSON report here")
    parser.add_argument("--record-out", type=Path, help="write the Markdown validation record here")
    args = parser.parse_args(argv)

    work = args.work_dir or Path(tempfile.mkdtemp(prefix="ci1-p2-"))
    work.mkdir(parents=True, exist_ok=True)
    try:
        report = run_preflight(args.version, work.resolve(), args.commit_build)
    except PreflightError as exc:
        print(f"[ci1-p2] PREFLIGHT ERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    if args.record_out:
        args.record_out.write_text(render_markdown(report), encoding="utf-8")
    for s in report["sections"].values():
        print(f"[ci1-p2] {s['label']}: {s['passed']}/{s['total']} parity")
        for r in s["results"]:
            if not r["parity"]:
                print(f"[ci1-p2]   FAIL {r.get('corpus', r.get('check'))} {r.get('case', '')} "
                      f"{r['variant']}: {'; '.join(r['diffs'])}")
    print(f"[ci1-p2] verdict: {'PASS' if report['passed'] else 'FAIL'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

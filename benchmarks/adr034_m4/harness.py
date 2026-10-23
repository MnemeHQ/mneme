#!/usr/bin/env python3
"""ADR-034 M4 scoring harness (charter §6, ruling B2).

Scores the pinned ``FORBID_NUMERIC_ABOVE`` whole-file audit against the
decrypted M4 held-out corpus under the frozen evaluation criteria (blob
``7ca1f39e``): the §3 partitions, the §4 metrics and all twelve §5 gates,
including 3a. Written before decryption from the M4 charter, the M4 freeze
record, the criteria and ADR-034 only, with no case data.

    python benchmarks/adr034_m4/harness.py score \\
        --corpus <decrypted corpus root> \\
        --case-root-template "<relative template, e.g. cases/{case_id}>" \\
        --old-reader-python <0.10.0 venv python> \\
        --old-reader-wheel <mneme_hq-0.10.0-py3-none-any.whl> \\
        --out <new or empty directory>

What one ``score`` invocation does:

1. **Preconditions** (any failure refuses to score; nothing is run):
   CPython exactly 3.12.10; the git tree hash of the ``mneme/`` package the
   scoring interpreter actually imports equals the pin; ``FILES.sha256``
   verifies 195 of 195; the W spec matches its frozen SHA-256 (variance V-2);
   the manifest and ``FILES.sha256`` match their frozen digests; the corpus
   layout, manifest schema, invocation matrix and frozen case counts hold;
   the old-reader environment is ``mneme-hq==0.10.0`` installed from the
   given wheel, and is a different install from the build under test.
2. **Two complete scoring passes** in one environment. Each pass creates a
   fresh temporary root (the same path both times, removed after each pass),
   copies the corpus into it, builds each case's memory with
   ``mneme init --path`` and ``mneme adr import --apply``, runs
   ``mneme check --memory ... --query "audit" --mode strict --json`` with the
   charter §5 transport, applies the shipped hook trust validator, runs
   gates 11 and 12, and writes ``run-<n>/cases.jsonl`` and
   ``run-<n>/summary.json``.
3. **Gate 9:** the two run summaries must be byte-identical after replacing
   each run's temporary root path string, and nothing else. Because both
   passes use one root path, the raw summaries are expected to be identical
   too; both digests are reported.
4. ``summary.json``: every gate, the per-shape headline in the criteria §5
   wording, every metric, the failure list by opaque ``case_id`` (charter
   §10 fields), operational failures and both summary SHA-256 values.

Exit status: 0 PASS, 1 FAIL, 2 INVALID or REFUSED.

The harness performs no network access and denies it to every child
process (see ``m4_child.py``). It is not edited after decryption (charter
§6): a defect found then invalidates the blind claim.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter
from fractions import Fraction
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable

HARNESS_DIR = Path(__file__).resolve().parent
CHILD_SCRIPT = HARNESS_DIR / "m4_child.py"

RUN_SUMMARY_SCHEMA = "mneme.adr034-m4.run-summary/v1"
CASE_RECORD_SCHEMA = "mneme.adr034-m4.case/v1"
SUMMARY_SCHEMA = "mneme.adr034-m4.summary/v1"
ROOT_TOKEN = "<RUN_ROOT>"

NUMERIC = "FORBID_NUMERIC_ABOVE"
QUERY = "audit"
CHILD_TIMEOUT_S = 300

STRATA = ("A", "U", "N", "W", "R")
SHAPES = ("S1", "S2", "S3", "S4", "S5")
A_CATEGORIES = tuple(f"A{i}" for i in range(1, 10))
U_CATEGORIES = ("U1", "U2", "U3", "U4")
N2A_LOCATIONS = ("L1", "L2", "L3", "L4")
APPLICABILITY = ("APPLIED", "EXCLUDED", "UNKNOWN")
MATCHER_STATUSES = ("RECOGNIZED", "PARTIAL", "MATCHER_UNEVALUATED")
MATCHER_OUTCOMES = ("VIOLATION", "NO_VIOLATION", "UNEVALUATED")
REASONS = (
    "INCOMPLETE_SOURCE_INPUT", "PARSE_FAILURE", "AMBIGUOUS_BINDING",
    "SOURCE_NOT_FOUND", "UNRECOGNIZED_FORM",
)
EXPECTED_KEYS = (
    "applicability", "matcher_status", "matcher_outcome", "primary_reason",
    "unknown_sources", "evaluation_complete",
)
RECORD_KEYS = (
    "case_id", "stratum", "category", "shape", "contract", "invocation",
    "expected", "rationale",
)

# Criteria §2.6a: set R, by R index -> (expected matcher outcome, reason).
CRITERIA_R_TABLE: dict[str, tuple[str, str | None]] = {
    "R1": ("VIOLATION", None),
    "R2": ("NO_VIOLATION", None),
    "R3": ("VIOLATION", None),
    "R4": ("NO_VIOLATION", None),
    "R5": ("NO_VIOLATION", None),
    "R6": ("NO_VIOLATION", None),
    "R7": ("NO_VIOLATION", None),
    "R8": ("NO_VIOLATION", None),
    "R9": ("NO_VIOLATION", None),
    "R10": ("VIOLATION", None),
    "R11": ("UNEVALUATED", "UNRECOGNIZED_FORM"),
    "R12": ("UNEVALUATED", "UNRECOGNIZED_FORM"),
    "R13": ("UNEVALUATED", "UNRECOGNIZED_FORM"),
    "R14": ("UNEVALUATED", "UNRECOGNIZED_FORM"),
    "R15": ("NO_VIOLATION", None),
    "R16": ("VIOLATION", None),
    "R17": ("UNEVALUATED", "UNRECOGNIZED_FORM"),
    "R18": ("UNEVALUATED", "UNRECOGNIZED_FORM"),
}

# Criteria §2.3: the label each stratum-A category carries.
A_CATEGORY_LABEL = {
    "A1": "VIOLATION", "A2": "VIOLATION", "A3": "VIOLATION",
    "A4": "NO_VIOLATION", "A5": "VIOLATION", "A6": "NO_VIOLATION",
    "A7": "VIOLATION", "A8": "NO_VIOLATION",
}

_ADR_TEMPLATE = """---
id: {decision_id}
title: "{title}"
status: accepted
priority: normal
date: 2026-10-23
scope: {scope}
---

# {decision_id}: {title}

## Context

Harness-authored contract for an ADR-034 M4 golden-vector or old-reader
check. Not a corpus case.

## Decision

{title}.

## Constraints

{constraints}"""

_NUMERIC_TEMPLATE = """- FORBID_NUMERIC_ABOVE:
    language: python
{sources}    max: {max}
    inclusive: true
    unit: seconds
    include_paths:
      - "src/**"
"""


@dataclasses.dataclass(frozen=True)
class GoldenVector:
    """One ADR-034 §5 golden rule-ID vector, with the ADR the harness authors."""

    label: str
    decision_id: str
    rule_type: str
    rule_id: str
    applicability: dict
    value: str | None = None
    canonical: dict | None = None
    canonical_text: str | None = None
    symbol: str | None = None
    call: tuple[str, int] | None = None
    max: str | None = None

    def constraints_markdown(self) -> str:
        if self.rule_type == "FORBID_LITERAL":
            return f"- FORBID_LITERAL: {self.value}\n"
        sources = ""
        if self.symbol is not None:
            sources += f"    symbol: {self.symbol}\n"
        if self.call is not None:
            sources += (
                "    call:\n"
                f"      function: {self.call[0]}\n"
                f"      position: {self.call[1]}\n"
            )
        return _NUMERIC_TEMPLATE.format(sources=sources, max=self.max)


def _numeric_canonical(symbol, call, max_text):
    canonical = {"v": 1, "language": "python", "max": max_text,
                 "inclusive": True, "unit": "seconds"}
    if symbol is not None:
        canonical["symbol"] = symbol
    if call is not None:
        canonical["call"] = {"function": call[0], "position": call[1]}
    return canonical


_SRC = {"include_paths": ["src/**"]}

# ADR-034 §5. Rows 2 and 3 do not state their unit; "seconds" (row 1's unit)
# reproduces both published ids, so the preimages are confirmed.
ADR034_GOLDEN: tuple[GoldenVector, ...] = (
    GoldenVector(
        label="adr005_forbid_literal_install_command",
        decision_id="ADR-005", rule_type="FORBID_LITERAL",
        rule_id="ADR-005:FORBID_LITERAL:cbf4d271068507ddb12c33abd765e333",
        # ADR-005's forbidden literal, as data: split so this file never
        # carries the install command it forbids (ADR-005 gate).
        applicability={}, value="pip install " + "mneme",
    ),
    GoldenVector(
        label="numeric_symbol_and_call_max_5",
        decision_id="ADR-001", rule_type=NUMERIC,
        rule_id="ADR-001:FORBID_NUMERIC_ABOVE:29b880066c98c7db4abb997f7cbbb096",
        applicability=_SRC,
        canonical=_numeric_canonical("ROUTER_DEADLINE_S", ("classify", 1), "5"),
        canonical_text=(
            '{"call":{"function":"classify","position":1},"inclusive":true,'
            '"language":"python","max":"5","symbol":"ROUTER_DEADLINE_S",'
            '"unit":"seconds","v":1}'
        ),
        symbol="ROUTER_DEADLINE_S", call=("classify", 1), max="5",
    ),
    GoldenVector(
        label="numeric_symbol_only_max_5",
        decision_id="ADR-001", rule_type=NUMERIC,
        rule_id="ADR-001:FORBID_NUMERIC_ABOVE:19aa8ed962b7e693ffe3d71804cf4c7c",
        applicability=_SRC,
        canonical=_numeric_canonical("ROUTER_DEADLINE_S", None, "5"),
        symbol="ROUTER_DEADLINE_S", max="5",
    ),
    GoldenVector(
        label="numeric_call_only_max_2_5",
        decision_id="ADR-001", rule_type=NUMERIC,
        rule_id="ADR-001:FORBID_NUMERIC_ABOVE:e74969fb22bd8988d5fae6133a8b7a57",
        applicability=_SRC,
        canonical=_numeric_canonical(None, ("classify", 1), "2.5"),
        call=("classify", 1), max="2.5",
    ),
)

# docs/validation/adr-034-g1-heldout-scoring-2026-10-22.md, "Old reader".
G1_RECORDED_OLD_READER_WHEEL = ("fc7e0ec7", "6ec5312")

M4_COUNTS: dict[str, dict[str, int]] = {
    "total": {"cases": 161},
    "stratum": {"A": 53, "U": 25, "N": 15, "W": 50, "R": 18},
    "a_category": {"A1": 4, "A2": 6, "A3": 5, "A4": 5, "A5": 5, "A6": 10,
                   "A7": 3, "A8": 10, "A9": 5},
    "a_scored_shape": {"S1": 9, "S2": 9, "S3": 10, "S4": 10, "S5": 10},
    "a9_shape": {s: 1 for s in SHAPES},
    "u_category": {"U1": 10, "U2": 5, "U3": 5, "U4": 5},
    "u_shape": {s: 5 for s in SHAPES},
    "n_form": {"N1": 3, "N2a": 8, "N2b": 4},
    "n2a_location": {loc: 2 for loc in N2A_LOCATIONS},
    "w_shape": {s: 10 for s in SHAPES},
    "r_shape": {f"R{i}": 1 for i in range(1, 19)},
}


@dataclasses.dataclass(frozen=True)
class Pins:
    """Everything the M4 records freeze. ``M4_PINS`` is the only CLI value."""

    python_implementation: str
    python_version: str
    mneme_tree: str
    files_sha256_digest: str
    files_count: int
    manifest_sha256: str
    w_spec_sha256: str
    counts: dict
    shapes: tuple[str, ...]
    golden: tuple[GoldenVector, ...]
    old_reader_distribution_version: str
    old_reader_wheel_name: str
    coverage_w_floor: Fraction
    is_m4_frozen: bool


M4_PINS = Pins(
    python_implementation="CPython",
    python_version="3.12.10",
    mneme_tree="002fdddb254267d42a3810cfea669d75700372f2",
    files_sha256_digest="aa1f578ddefbe2480bac0bd065c65fc3fcfec2b454da81c104d15fb883fc2177",
    files_count=195,
    manifest_sha256="65dfc5ce8e42c1c307ade336790eea6cf444a250830fe8b73450d6cc159127ee",
    w_spec_sha256="6abeabfe9ab314ab8801381e9c11c0fa46a4a3001e266ec2416ce8826050cfd9",
    counts=M4_COUNTS,
    shapes=SHAPES,
    golden=ADR034_GOLDEN,
    old_reader_distribution_version="0.10.0",
    old_reader_wheel_name="mneme_hq-0.10.0-py3-none-any.whl",
    coverage_w_floor=Fraction(95, 100),
    is_m4_frozen=True,
)


def pins_record(pins: Pins) -> dict:
    return {
        "is_m4_frozen": pins.is_m4_frozen,
        "python": f"{pins.python_implementation} {pins.python_version}",
        "mneme_tree": pins.mneme_tree,
        "files_sha256_digest": pins.files_sha256_digest,
        "files_count": pins.files_count,
        "manifest_sha256": pins.manifest_sha256,
        "w_spec_sha256": pins.w_spec_sha256,
        "counts": pins.counts,
        "shapes": list(pins.shapes),
        "golden_rule_ids": [g.rule_id for g in pins.golden],
        "old_reader": f"mneme-hq=={pins.old_reader_distribution_version}",
        "coverage_w_floor": f"{pins.coverage_w_floor.numerator}/{pins.coverage_w_floor.denominator}",
    }


class Refusal(Exception):
    """A precondition failed: the harness refuses to score (charter §6)."""

    def __init__(self, check: str, detail: str):
        super().__init__(f"{check}: {detail}")
        self.check = check
        self.detail = detail


# ── hashing ──────────────────────────────────────────────────────────────────

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_tree_hash(directory: Path) -> str | None:
    """Git tree object id of ``directory`` as checked-in source.

    ``__pycache__`` directories are skipped (bytecode caches are not source);
    every other entry counts, so a stray or altered file changes the hash.
    Empty directories are omitted, as git cannot record them. Symlinks and
    special files are refused.
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


# ── child processes ──────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class Interpreter:
    """A child interpreter: the build under test, or the gate-12 old reader."""

    python: str
    pythonpath: str | None = None

    def env(self) -> dict[str, str]:
        env = {
            key: value for key, value in os.environ.items()
            if not key.upper().startswith(("PYTHON", "MNEME_", "VIRTUAL_ENV"))
        }
        if self.pythonpath is not None:
            env["PYTHONPATH"] = self.pythonpath
        return env


def scrubbed_variables() -> list[str]:
    return sorted(
        key for key in os.environ
        if key.upper().startswith(("PYTHON", "MNEME_", "VIRTUAL_ENV"))
    )


@dataclasses.dataclass
class Step:
    argv: list[str]
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool = False

    def text(self, which: str) -> str:
        data = self.stdout if which == "stdout" else self.stderr
        return data.decode("utf-8", errors="backslashreplace")

    def record(self, *, include_stdout: bool = True) -> dict:
        record = {
            "argv": self.argv,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "stderr": self.text("stderr"),
        }
        if include_stdout:
            record["stdout"] = self.text("stdout")
        return record


def run_child(interp: Interpreter, args: list[str], cwd: Path,
              timeout: int = CHILD_TIMEOUT_S) -> Step:
    argv = [interp.python, "-P", str(CHILD_SCRIPT), *args]
    try:
        proc = subprocess.run(
            argv, cwd=str(cwd), env=interp.env(), stdin=subprocess.DEVNULL,
            capture_output=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return Step(argv, None, exc.stdout or b"", exc.stderr or b"", timed_out=True)
    return Step(argv, proc.returncode, proc.stdout, proc.stderr)


def child_json(interp: Interpreter, args: list[str], cwd: Path, what: str) -> Any:
    step = run_child(interp, args, cwd)
    if step.returncode != 0:
        raise Refusal(what, f"child failed (exit {step.returncode}): {step.text('stderr')[-2000:]}")
    try:
        return json.loads(step.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refusal(what, f"child returned unparseable output: {exc}") from exc


def mneme_cli(interp: Interpreter, args: list[str], cwd: Path) -> Step:
    return run_child(interp, ["cli", *args], cwd)


# ── environment preconditions ────────────────────────────────────────────────

def probe_build(interp: Interpreter, cwd: Path, pins: Pins) -> dict:
    """CPython version and ``mneme/`` tree of the code actually imported."""
    probe = child_json(interp, ["probe"], cwd, "probe")
    if probe["python_implementation"] != pins.python_implementation:
        raise Refusal("python", f"implementation {probe['python_implementation']!r}, "
                                f"pinned {pins.python_implementation!r}")
    if probe["python_version"] != pins.python_version:
        raise Refusal("python", f"version {probe['python_version']!r}, "
                                f"pinned {pins.python_version!r}")
    tree = git_tree_hash(Path(probe["mneme_dir"]))
    probe["mneme_tree"] = tree
    if tree != pins.mneme_tree:
        raise Refusal("mneme_tree", f"imported mneme/ at {probe['mneme_dir']} has tree "
                                    f"{tree}, pinned {pins.mneme_tree}")
    if not probe["numeric_rule_module"]:
        raise Refusal("mneme_tree", "imported build has no mneme.numeric_rule module")
    return probe


def verify_old_reader(old: Interpreter, wheel: Path, build_probe: dict,
                      cwd: Path, pins: Pins) -> dict:
    """The gate-12 reader is mneme-hq==0.10.0, installed from ``wheel``."""
    probe = child_json(old, ["probe"], cwd, "old_reader")
    if probe["distribution_version"] != pins.old_reader_distribution_version:
        raise Refusal("old_reader", f"distribution version {probe['distribution_version']!r}, "
                                    f"pinned {pins.old_reader_distribution_version!r}")
    if probe["numeric_rule_module"]:
        raise Refusal("old_reader", "old reader has mneme.numeric_rule: not a reader "
                                    "without numeric_upper_bound_rule")
    old_dir = Path(probe["mneme_dir"])
    if os.path.normcase(str(old_dir)) == os.path.normcase(build_probe["mneme_dir"]):
        raise Refusal("old_reader", "old reader imports the same mneme/ as the build under test")
    if wheel.name != pins.old_reader_wheel_name:
        raise Refusal("old_reader", f"wheel file {wheel.name!r}, expected "
                                    f"{pins.old_reader_wheel_name!r}")
    if not wheel.is_file():
        raise Refusal("old_reader", f"wheel {wheel} not found")
    site = old_dir.parent
    checked = 0
    recorded: set[str] = set()
    with zipfile.ZipFile(wheel) as archive:
        records = [n for n in archive.namelist() if n.endswith(".dist-info/RECORD")]
        if len(records) != 1:
            raise Refusal("old_reader", "wheel has no single RECORD")
        for row in archive.read(records[0]).decode("utf-8").splitlines():
            path, _, rest = row.partition(",")
            digest, _, _ = rest.partition(",")
            if not path.startswith("mneme/"):
                continue
            if not digest.startswith("sha256="):
                raise Refusal("old_reader", f"RECORD entry without sha256: {path}")
            recorded.add(path)
            expected = digest[len("sha256="):]
            installed = site / PurePosixPath(path)
            try:
                actual = _urlsafe_sha256(installed.read_bytes())
            except OSError as exc:
                raise Refusal("old_reader", f"installed file missing: {path}") from exc
            if actual != expected:
                raise Refusal("old_reader", f"installed {path} differs from the wheel")
            checked += 1
    for file in old_dir.rglob("*"):
        if "__pycache__" in file.parts or not file.is_file():
            continue
        rel = file.relative_to(site).as_posix()
        if rel not in recorded:
            raise Refusal("old_reader", f"installed file not in the wheel: {rel}")
    probe["wheel"] = wheel.name
    probe["wheel_sha256"] = sha256_file(wheel)
    probe["wheel_files_verified"] = checked
    # Informational: the G1 results record published this wheel's digest
    # truncated. The charter records the full digest; it does not pin it.
    prefix, suffix = G1_RECORDED_OLD_READER_WHEEL
    probe["wheel_sha256_matches_g1_record"] = (
        probe["wheel_sha256"].startswith(prefix) and probe["wheel_sha256"].endswith(suffix))
    return probe


def _urlsafe_sha256(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


# ── corpus preconditions ─────────────────────────────────────────────────────

_FILES_LINE = re.compile(r"^([0-9a-f]{64}) [ *](.+)$")


def _safe_relative(text: str, what: str) -> PurePosixPath:
    if "\\" in text:
        raise Refusal(what, f"path uses a backslash: {text!r}")
    path = PurePosixPath(text)
    if path.is_absolute() or re.match(r"^[A-Za-z]:", text):
        raise Refusal(what, f"absolute path: {text!r}")
    parts = [p for p in path.parts if p != "."]
    if not parts or ".." in parts:
        raise Refusal(what, f"path escapes its root: {text!r}")
    return PurePosixPath(*parts)


def parse_files_sha256(text: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise Refusal("files_sha256", f"blank line {number}")
        match = _FILES_LINE.match(line)
        if match is None:
            raise Refusal("files_sha256", f"unparseable line {number}")
        rel = _safe_relative(match.group(2), "files_sha256").as_posix()
        if rel in seen:
            raise Refusal("files_sha256", f"duplicate entry {rel!r}")
        seen.add(rel)
        entries.append((match.group(1), rel))
    return entries


def verify_files(root: Path, entries: list[tuple[str, str]]) -> dict:
    """``sha256sum -c FILES.sha256``: every entry must be OK."""
    failures = []
    ok = 0
    for digest, rel in entries:
        path = root / PurePosixPath(rel)
        try:
            mode = path.lstat().st_mode
        except OSError:
            failures.append(f"{rel}: missing")
            continue
        if not stat.S_ISREG(mode):
            failures.append(f"{rel}: not a regular file")
            continue
        if sha256_file(path) != digest:
            failures.append(f"{rel}: FAILED")
            continue
        ok += 1
    return {"ok": ok, "listed": len(entries), "failures": failures}


def corpus_layout(root: Path) -> dict:
    regular: list[str] = []
    directories = 0
    other: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        for name in list(dirnames):
            path = base / name
            if path.is_symlink():
                other.append(path.relative_to(root).as_posix())
                dirnames.remove(name)
            else:
                directories += 1
        for name in filenames:
            path = base / name
            mode = path.lstat().st_mode
            rel = path.relative_to(root).as_posix()
            if stat.S_ISREG(mode):
                regular.append(rel)
            else:
                other.append(rel)
    return {"regular": sorted(regular), "directories": directories, "other": sorted(other)}


def verify_corpus(root: Path, pins: Pins, w_spec: str | None) -> dict:
    files_path = root / "FILES.sha256"
    if not files_path.is_file():
        raise Refusal("files_sha256", f"no FILES.sha256 at the corpus root {root}")
    files_digest = sha256_file(files_path)
    if files_digest != pins.files_sha256_digest:
        raise Refusal("files_sha256", f"FILES.sha256 digest {files_digest}, frozen "
                                      f"{pins.files_sha256_digest}")
    entries = parse_files_sha256(files_path.read_text(encoding="utf-8"))
    result = verify_files(root, entries)
    if result["failures"] or result["ok"] != pins.files_count or result["listed"] != pins.files_count:
        raise Refusal("files_sha256", f"{result['ok']} OK of {result['listed']} listed, "
                                      f"{pins.files_count} required; failures: "
                                      f"{result['failures'][:20]}")
    layout = corpus_layout(root)
    listed = {rel for _, rel in entries}
    expected_regular = sorted(listed | {"FILES.sha256"})
    if layout["other"]:
        raise Refusal("corpus_layout", f"non-regular entries: {layout['other'][:20]}")
    if layout["regular"] != expected_regular:
        extra = sorted(set(layout["regular"]) - set(expected_regular))
        raise Refusal("corpus_layout", f"regular files not covered by FILES.sha256: {extra[:20]}")
    manifests = sorted(rel for rel in listed if PurePosixPath(rel).name == "manifest.jsonl")
    if "manifest.jsonl" in listed:
        manifest_rel = "manifest.jsonl"
    elif len(manifests) == 1:
        manifest_rel = manifests[0]
    else:
        raise Refusal("manifest", f"cannot locate one manifest.jsonl (found {manifests})")
    by_rel = {rel: digest for digest, rel in entries}
    if by_rel[manifest_rel] != pins.manifest_sha256:
        raise Refusal("manifest", f"manifest digest {by_rel[manifest_rel]}, frozen "
                                  f"{pins.manifest_sha256}")
    if w_spec is not None:
        w_rel = _safe_relative(w_spec, "w_spec").as_posix()
        if w_rel not in listed:
            raise Refusal("w_spec", f"{w_rel} is not a FILES.sha256 entry")
        w_matches = [w_rel] if by_rel[w_rel] == pins.w_spec_sha256 else []
        if not w_matches:
            raise Refusal("w_spec", f"{w_rel} has digest {by_rel[w_rel]}, frozen "
                                    f"{pins.w_spec_sha256}")
    else:
        w_matches = sorted(rel for rel, digest in by_rel.items() if digest == pins.w_spec_sha256)
        if len(w_matches) != 1:
            raise Refusal("w_spec", f"{len(w_matches)} corpus files match the frozen W-spec "
                                    f"digest {pins.w_spec_sha256}; exactly 1 required")
    # FILES.sha256 was verified against the bytes on disk; re-hash the W spec
    # anyway, so this check never rests on the listing alone.
    w_actual = sha256_file(root / PurePosixPath(w_matches[0]))
    if w_actual != pins.w_spec_sha256:
        raise Refusal("w_spec", f"{w_matches[0]} hashes to {w_actual}")
    return {
        "files_sha256_digest": files_digest,
        "files_ok": result["ok"],
        "files_listed": result["listed"],
        "regular_files": len(layout["regular"]),
        "directories": layout["directories"],
        "manifest": manifest_rel,
        "manifest_sha256": by_rel[manifest_rel],
        "w_spec": w_matches[0],
        "w_spec_sha256": w_actual,
    }


# ── manifest ─────────────────────────────────────────────────────────────────

def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


@dataclasses.dataclass(frozen=True)
class Case:
    """One manifest record, validated against the charter §5 matrix and §6 schema."""

    case_id: str
    stratum: str
    category: str
    form: str          # A1..A9, U1..U4, N1, N2a, N2b, W, R
    shape: str | None
    contract: str
    transport: str     # source_file | input
    path: str
    target_path: str | None
    location: str | None
    expected: dict
    index: int

    @property
    def role(self) -> str:
        if self.stratum == "A" and self.category == "A9":
            return "applicability"
        if self.stratum in ("U", "N"):
            return "unevaluated"
        return "matcher"

    @property
    def is_n2(self) -> bool:
        return self.form in ("N2a", "N2b")


def parse_manifest(text: str) -> tuple[list[Case], list[dict]]:
    """Parse and validate ``manifest.jsonl``.

    Structural defects that would make an invocation impossible or
    ambiguous refuse scoring. Fields the author omitted are read as ``null``
    (charter §6 says they are never omitted) and reported as findings.
    """
    if not text.endswith("\n"):
        raise Refusal("manifest", "manifest does not end with a newline")
    cases: list[Case] = []
    findings: list[dict] = []
    seen: set[str] = set()
    for number, line in enumerate(text[:-1].split("\n"), start=1):
        try:
            record = json.loads(line, object_pairs_hook=_no_duplicate_keys)
        except ValueError as exc:
            raise Refusal("manifest", f"line {number}: {exc}") from exc
        if not isinstance(record, dict):
            raise Refusal("manifest", f"line {number}: not an object")
        case = _parse_record(record, number, findings)
        if case.case_id in seen:
            raise Refusal("manifest", f"duplicate case_id on line {number}")
        seen.add(case.case_id)
        cases.append(case)
    if not cases:
        raise Refusal("manifest", "manifest has no cases")
    return cases, findings


def _parse_record(record: dict, number: int, findings: list[dict]) -> Case:
    where = f"line {number}"
    missing = [key for key in RECORD_KEYS if key not in record]
    if missing:
        raise Refusal("manifest", f"{where}: missing fields {missing}")
    case_id = record["case_id"]
    if not isinstance(case_id, str) or not case_id or not case_id.isprintable():
        raise Refusal("manifest", f"{where}: case_id is not a non-empty printable string")
    where = f"case {case_id}"
    stratum = record["stratum"]
    if stratum not in STRATA:
        raise Refusal("manifest", f"{where}: stratum {stratum!r} not in {STRATA}")
    category = record["category"]
    if not isinstance(category, str) or not category:
        raise Refusal("manifest", f"{where}: category is not a non-empty string")
    shape = record["shape"]
    invocation = record["invocation"]
    if not isinstance(invocation, dict):
        raise Refusal("manifest", f"{where}: invocation is not an object")
    for key in ("target_path", "location"):
        if key not in invocation:
            findings.append({"case_id": case_id, "finding": f"invocation.{key} omitted (read as null)"})
    transport = invocation.get("transport")
    path = invocation.get("path")
    target_path = invocation.get("target_path")
    location = invocation.get("location")
    if transport not in ("source_file", "input"):
        raise Refusal("manifest", f"{where}: transport {transport!r}")
    if not isinstance(path, str):
        raise Refusal("manifest", f"{where}: invocation.path is not a string")
    _safe_relative(path, "manifest")
    if not isinstance(record["contract"], str):
        raise Refusal("manifest", f"{where}: contract is not a string")
    _safe_relative(record["contract"], "manifest")
    if target_path is not None:
        if not isinstance(target_path, str):
            raise Refusal("manifest", f"{where}: target_path is not a string")
        _safe_relative(target_path, "manifest")

    # Category and form, per stratum (ruling M4-07).
    if stratum == "A":
        if category not in A_CATEGORIES:
            raise Refusal("manifest", f"{where}: stratum A category {category!r}")
        form = category
    elif stratum == "U":
        if category not in U_CATEGORIES:
            raise Refusal("manifest", f"{where}: stratum U category {category!r}")
        form = category
    elif stratum == "N":
        if category == "N1":
            form = "N1"
        elif category in ("N2", "N2a", "N2b"):
            form = "N2b" if target_path is not None else "N2a"
            if category != "N2" and category != form:
                raise Refusal("manifest", f"{where}: category {category} but target_path "
                                          f"makes it {form}")
        else:
            raise Refusal("manifest", f"{where}: stratum N category {category!r}")
    else:
        form = stratum

    # Shape.
    if stratum == "R":
        if shape not in CRITERIA_R_TABLE:
            raise Refusal("manifest", f"{where}: set R shape {shape!r} is not R1..R18")
    elif stratum == "N":
        if shape is not None and shape not in SHAPES:
            raise Refusal("manifest", f"{where}: shape {shape!r}")
    elif shape not in SHAPES:
        raise Refusal("manifest", f"{where}: shape {shape!r} not in {SHAPES}")

    # Charter §5 invocation matrix.
    if form in ("N2a", "N2b"):
        if transport != "input":
            raise Refusal("manifest", f"{where}: {form} must use --input")
        if form == "N2a" and location not in N2A_LOCATIONS:
            raise Refusal("manifest", f"{where}: N2a location {location!r}")
        if form == "N2b" and location is not None:
            raise Refusal("manifest", f"{where}: N2b carries a location")
    else:
        if transport != "source_file":
            raise Refusal("manifest", f"{where}: {form} must use --source-file")
        if target_path is not None or location is not None:
            raise Refusal("manifest", f"{where}: --source-file case carries target_path/location")

    expected = record["expected"]
    if not isinstance(expected, dict):
        raise Refusal("manifest", f"{where}: expected is not an object")
    normalized = {}
    for key in EXPECTED_KEYS:
        if key not in expected:
            findings.append({"case_id": case_id, "finding": f"expected.{key} omitted (read as null)"})
        normalized[key] = expected.get(key)
    _check_vocab(where, "applicability", normalized["applicability"], APPLICABILITY)
    _check_vocab(where, "matcher_status", normalized["matcher_status"], MATCHER_STATUSES)
    _check_vocab(where, "matcher_outcome", normalized["matcher_outcome"], MATCHER_OUTCOMES)
    _check_vocab(where, "primary_reason", normalized["primary_reason"], REASONS)
    complete = normalized["evaluation_complete"]
    if complete is not None and not isinstance(complete, bool):
        raise Refusal("manifest", f"{where}: expected.evaluation_complete is not a boolean")
    sources = normalized["unknown_sources"]
    if sources is not None:
        normalized["unknown_sources"] = _parse_unknown_sources(sources, where)
    return Case(
        case_id=case_id, stratum=stratum, category=category, form=form,
        shape=shape, contract=record["contract"], transport=transport,
        path=path, target_path=target_path, location=location,
        expected=normalized, index=number,
    )


def _check_vocab(where: str, key: str, value: Any, allowed: tuple[str, ...]) -> None:
    if value is not None and value not in allowed:
        raise Refusal("manifest", f"{where}: expected.{key} {value!r} not in {allowed}")


def _parse_unknown_sources(sources: Any, where: str) -> list[dict]:
    if not isinstance(sources, list):
        raise Refusal("manifest", f"{where}: expected.unknown_sources is not a list")
    parsed = []
    for source in sources:
        if not isinstance(source, dict) or not {"kind", "line", "reason"} <= set(source):
            raise Refusal("manifest", f"{where}: unknown source lacks kind/line/reason")
        line = source["line"]
        if line is not None and (not isinstance(line, int) or isinstance(line, bool)):
            raise Refusal("manifest", f"{where}: unknown source line is not an integer")
        if source["reason"] not in REASONS:
            raise Refusal("manifest", f"{where}: unknown source reason {source['reason']!r}")
        parsed.append({"kind": source["kind"], "line": line, "reason": source["reason"]})
    return parsed


def observed_counts(cases: list[Case]) -> dict[str, dict[str, int]]:
    def count(items: Iterable[str]) -> dict[str, int]:
        return dict(sorted(Counter(items).items()))

    a = [c for c in cases if c.stratum == "A"]
    return {
        "total": {"cases": len(cases)},
        "stratum": count(c.stratum for c in cases),
        "a_category": count(c.category for c in a),
        "a_scored_shape": count(c.shape for c in a if c.category != "A9"),
        "a9_shape": count(c.shape for c in a if c.category == "A9"),
        "u_category": count(c.category for c in cases if c.stratum == "U"),
        "u_shape": count(c.shape for c in cases if c.stratum == "U"),
        "n_form": count(c.form for c in cases if c.stratum == "N"),
        "n2a_location": count(c.location for c in cases if c.form == "N2a"),
        "w_shape": count(c.shape for c in cases if c.stratum == "W"),
        "r_shape": count(c.shape for c in cases if c.stratum == "R"),
    }


def verify_counts(cases: list[Case], pins: Pins) -> dict:
    observed = observed_counts(cases)
    for key, expected in pins.counts.items():
        if observed.get(key, {}) != dict(sorted(expected.items())):
            raise Refusal("counts", f"{key}: manifest has {observed.get(key)}, frozen {expected}")
    return observed


def label_findings(cases: list[Case]) -> list[dict]:
    """Manifest labels that disagree with the criteria's category definitions.

    Reported, never used to change a label or refuse scoring.
    """
    findings = []

    def note(case: Case, text: str) -> None:
        findings.append({"case_id": case.case_id, "finding": text})

    for case in cases:
        e = case.expected
        if case.stratum == "A" and case.category in A_CATEGORY_LABEL:
            if e["matcher_outcome"] != A_CATEGORY_LABEL[case.category]:
                note(case, f"{case.category} expects {e['matcher_outcome']}, criteria §2.3 "
                           f"label {A_CATEGORY_LABEL[case.category]}")
        if case.category == "A7":
            if e["matcher_status"] != "PARTIAL" or e["evaluation_complete"] is not False:
                note(case, "A7 does not expect PARTIAL with evaluation_complete=false")
            if not e["unknown_sources"]:
                note(case, "A7 lists no expected unknown source")
        if case.category == "A9" and e["applicability"] != "EXCLUDED":
            note(case, f"A9 expects applicability {e['applicability']}, criteria EXCLUDED")
        if case.role == "unevaluated":
            if e["matcher_status"] != "MATCHER_UNEVALUATED" or e["primary_reason"] is None:
                note(case, "U/N case does not expect MATCHER_UNEVALUATED with a primary reason")
        if case.is_n2 and e["primary_reason"] != "INCOMPLETE_SOURCE_INPUT":
            note(case, "N2 case does not expect INCOMPLETE_SOURCE_INPUT (ADR-034 §6)")
        if case.form == "N1" and e["primary_reason"] != "PARSE_FAILURE":
            note(case, "N1 case does not expect PARSE_FAILURE")
        if case.stratum == "R":
            outcome, reason = CRITERIA_R_TABLE[case.shape]
            if e["matcher_outcome"] != outcome or (
                outcome == "UNEVALUATED" and e["primary_reason"] != reason
            ):
                note(case, f"set R {case.shape} manifest expectation differs from criteria §2.6a")
    for shape in sorted({c.shape for c in cases if c.stratum == "W"}):
        outcomes = Counter(c.expected["matcher_outcome"] for c in cases
                           if c.stratum == "W" and c.shape == shape)
        findings.append({
            "case_id": None,
            "finding": f"W {shape} label mix: " + ", ".join(
                f"{k}={v}" for k, v in sorted(outcomes.items(), key=lambda kv: str(kv[0]))),
        })
    return findings


# ── case layout (rulings M4-03, M4-04) ───────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class Layout:
    case_root: PurePosixPath
    contract: PurePosixPath
    path: PurePosixPath
    target_path: PurePosixPath | None
    geometry: dict


def case_layout(case: Case, template: str, corpus: Path) -> Layout:
    try:
        rendered = template.format(case_id=case.case_id, stratum=case.stratum,
                                   category=case.category, shape=case.shape or "")
    except (KeyError, IndexError, ValueError) as exc:
        raise Refusal("case_root_template", f"cannot render for {case.case_id}: {exc}") from exc
    case_root = _safe_relative(rendered, "case_root_template")
    contract = _safe_relative(case.contract, "manifest")
    path = _safe_relative(case.path, "manifest")
    target = _safe_relative(case.target_path, "manifest") if case.target_path else None
    if not (corpus / case_root).is_dir():
        raise Refusal("case_root_template", f"case {case.case_id}: {case_root} is not a directory")
    if not (corpus / contract).is_dir():
        raise Refusal("manifest", f"case {case.case_id}: contract {contract} is not a directory")
    if not (corpus / path).is_file():
        raise Refusal("manifest", f"case {case.case_id}: path {path} is not a file")
    if (corpus / case_root / ".mneme" / "project_memory.json").exists():
        raise Refusal("case_root_template", f"case {case.case_id}: memory already exists")
    inside = _is_within(path, case_root)
    geometry = {"path_inside_case_root": inside}
    if case.form == "N2a":
        expected_inside = case.location != "L4"
        geometry["location_consistent"] = (
            inside == expected_inside
            and (case.location != "L3" or path.parent == case_root)
            and (case.location not in ("L1", "L2") or path.parent != case_root)
        )
    elif case.transport == "source_file":
        geometry["location_consistent"] = inside
    if target is not None:
        geometry["target_path"] = target.as_posix()
    return Layout(case_root, contract, path, target, geometry)


def _is_within(path: PurePosixPath, root: PurePosixPath) -> bool:
    return path.parts[:len(root.parts)] == root.parts and len(path.parts) > len(root.parts)


def resolve_layouts(cases: list[Case], template: str, corpus: Path) -> dict[str, Layout]:
    layouts = {case.case_id: case_layout(case, template, corpus) for case in cases}
    roots = Counter(layout.case_root for layout in layouts.values())
    shared = sorted(str(root) for root, n in roots.items() if n > 1)
    if shared:
        raise Refusal("case_root_template", f"cases share a policy root: {shared[:10]}")
    return layouts


# ── one case ─────────────────────────────────────────────────────────────────

def check_argv(case: Case, layout: Layout, corpus: Path) -> list[str]:
    """Charter §5: ``mneme check`` arguments for one case (paths absolute)."""
    case_root = corpus / layout.case_root
    memory = case_root / ".mneme" / "project_memory.json"
    argv = ["check", "--memory", str(memory), "--query", QUERY, "--mode", "strict", "--json"]
    source = str(corpus / layout.path)
    if case.transport == "source_file":
        argv += ["--source-file", source]
    elif layout.target_path is None:
        argv += ["--input", source]
    else:
        # M4-04/M4-05: target_path is relative to the case's policy root and
        # need not exist; it is resolved lexically, never against the cwd.
        argv += ["--input", source, "--target-path", str(case_root / layout.target_path)]
    return argv


def execute_case(case: Case, layout: Layout, corpus: Path, build: Interpreter,
                 cwd: Path) -> dict:
    case_root = corpus / layout.case_root
    memory = case_root / ".mneme" / "project_memory.json"
    steps: dict[str, Step] = {}
    operational: list[str] = []
    steps["init"] = mneme_cli(build, ["init", "--path", str(memory)], cwd)
    if steps["init"].returncode != 0:
        operational.append(f"mneme init failed (exit {steps['init'].returncode})")
    else:
        steps["import"] = mneme_cli(
            build, ["adr", "import", str(corpus / layout.contract), "--memory",
                    str(memory), "--apply"], cwd)
        if steps["import"].returncode != 0:
            operational.append(f"mneme adr import failed (exit {steps['import'].returncode})")
        else:
            steps["check"] = mneme_cli(build, check_argv(case, layout, corpus), cwd)
            if steps["check"].timed_out:
                operational.append("mneme check timed out")
    input_bytes = (corpus / layout.path).read_bytes()
    return {"steps": steps, "operational": operational,
            "input_sha256": sha256_bytes(input_bytes)}


def assess_trust(build: Interpreter, executions: dict[str, dict], cwd: Path) -> None:
    """Apply the shipped hook trust validator to every captured check."""
    order = []
    requests = []
    for case_id, execution in executions.items():
        step = execution["steps"].get("check")
        if step is None or step.timed_out:
            continue
        try:
            stdout = step.stdout.decode("utf-8")
        except UnicodeDecodeError:
            execution["operational"].append("check stdout is not UTF-8")
            continue
        order.append(case_id)
        requests.append({"stdout": stdout, "returncode": step.returncode})
    request_file = cwd / "trust-requests.json"
    request_file.write_text(json.dumps(requests), encoding="utf-8")
    results = child_json(build, ["trust", str(request_file)], cwd, "trust_validator")
    request_file.unlink()
    if len(results) != len(order):
        raise Refusal("trust_validator", "validator returned the wrong number of results")
    for case_id, result in zip(order, results):
        executions[case_id]["trust"] = result
        if not result["trusted"]:
            executions[case_id]["operational"].append(f"untrusted payload: {result['problem']}")


# ── observation and per-case scoring ─────────────────────────────────────────

def observe(payload: dict, returncode: int) -> tuple[dict | None, str | None]:
    """The scored fields of one trusted payload, as emitted (never normalized)."""
    applicability = payload.get("applicability") or []
    traces = [t for t in applicability if isinstance(t, dict) and t.get("rule_type") == NUMERIC]
    if len(traces) != 1:
        return None, f"payload has {len(traces)} numeric rule traces; exactly 1 required"
    trace = traces[0]
    subject = payload.get("subject") if isinstance(payload.get("subject"), dict) else {}
    violations = [v for v in payload.get("violations") or [] if isinstance(v, dict)]
    numeric_violations = [v for v in violations if v.get("rule_type") == NUMERIC]
    status = trace.get("matcher_status")
    outcome = trace.get("matcher_outcome")
    if outcome in MATCHER_OUTCOMES:
        result = outcome
    elif status is None and trace.get("outcome") == "EXCLUDED":
        result = "EXCLUDED"
    elif status is None and trace.get("outcome") == "UNKNOWN":
        result = "PATH_UNKNOWN"
    else:
        return None, "numeric trace cannot be classified"
    return {
        "result": result,
        "applicability": trace.get("outcome"),
        "matcher_status": status,
        "matcher_outcome": outcome,
        "primary_reason": trace.get("primary_reason"),
        "unknown_sources": trace.get("unknown_sources"),
        "evaluation_complete": payload.get("evaluation_complete"),
        "verdict": payload.get("verdict"),
        "exit_code": returncode,
        "rule_id": trace.get("rule_id"),
        "decision_version_id": trace.get("decision_version_id"),
        "has_matcher_record": "matcher_status" in trace,
        "primary_reason_key_present": "primary_reason" in trace,
        "trace_subject_sha256": trace.get("subject_sha256"),
        "subject_sha256": subject.get("subject_sha256"),
        "input_kind": subject.get("input_kind"),
        "target_path_declared": subject.get("target_path_declared"),
        "numeric_violations": [
            {"rule_id": v.get("rule_id"), "decision_version_id": v.get("decision_version_id"),
             "severity": v.get("severity")}
            for v in numeric_violations
        ],
        "other_traces": len(applicability) - 1,
        "other_violations": len(violations) - len(numeric_violations),
    }, None


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def binding_complete(obs: dict, case: Case) -> bool:
    """ADR-029 binding (criteria §4): digest, rule id, version, applicability,
    matcher status and primary reason, and outcome, bound in one record."""
    if not _is_sha256(obs["subject_sha256"]):
        return False
    if not (isinstance(obs["rule_id"], str) and obs["rule_id"]):
        return False
    if not (isinstance(obs["decision_version_id"], str) and obs["decision_version_id"]):
        return False
    if obs["applicability"] not in APPLICABILITY:
        return False
    needs_record = obs["applicability"] == "APPLIED" or case.transport == "input"
    if needs_record or obs["has_matcher_record"]:
        if obs["matcher_status"] not in MATCHER_STATUSES:
            return False
        if obs["matcher_outcome"] not in MATCHER_OUTCOMES:
            return False
        if not obs["primary_reason_key_present"]:
            return False
        if obs["trace_subject_sha256"] != obs["subject_sha256"]:
            return False
    for violation in obs["numeric_violations"]:
        if (violation["rule_id"] != obs["rule_id"]
                or violation["decision_version_id"] != obs["decision_version_id"]):
            return False
    if (obs["result"] == "VIOLATION") != bool(obs["numeric_violations"]):
        return False
    return True


def _source_key(source: dict) -> tuple:
    return (str(source.get("kind")), -1 if source.get("line") is None else source["line"],
            str(source.get("reason")))


def scoring_expectation(case: Case) -> dict:
    """The expectation each case is scored against.

    Set R uses the criteria §2.6a table (the pre-registered expectation);
    every other case uses its adjudicated manifest label.
    """
    if case.stratum == "R":
        outcome, reason = CRITERIA_R_TABLE[case.shape]
        status = "MATCHER_UNEVALUATED" if outcome == "UNEVALUATED" else "RECOGNIZED"
        return {"matcher_status": status, "matcher_outcome": outcome, "primary_reason": reason}
    e = case.expected
    if case.role == "unevaluated":
        return {"matcher_status": "MATCHER_UNEVALUATED", "matcher_outcome": "UNEVALUATED",
                "primary_reason": e["primary_reason"]}
    return {"matcher_status": e["matcher_status"], "matcher_outcome": e["matcher_outcome"],
            "primary_reason": e["primary_reason"]}


def score_case(case: Case, obs: dict) -> dict:
    """Criteria §3 partitions and §4 per-case counters for one observation."""
    exp = scoring_expectation(case)
    result = obs["result"]
    label = exp["matcher_outcome"]
    clean = result in ("NO_VIOLATION", "EXCLUDED")
    s: dict[str, Any] = {"label": label}
    scored_aw = case.stratum == "W" or (case.stratum == "A" and case.category != "A9")
    expects_unevaluated = case.role == "unevaluated" or label == "UNEVALUATED"
    s["miss"] = scored_aw and label == "VIOLATION" and result != "VIOLATION"
    s["false_block"] = scored_aw and label == "NO_VIOLATION" and result == "VIOLATION"
    s["unsafe_pass"] = (case.role != "applicability") and expects_unevaluated and clean
    s["unexpected_un_violation"] = case.role == "unevaluated" and result == "VIOLATION"
    s["wrong_primary_reason"] = (
        (case.role == "unevaluated" or (scored_aw and label == "UNEVALUATED"))
        and obs["primary_reason"] != exp["primary_reason"]
    )
    s["decided"] = result in ("VIOLATION", "NO_VIOLATION") and obs["applicability"] == "APPLIED"
    s["unevaluated"] = result == "UNEVALUATED"
    if case.role == "unevaluated":
        s["un_correct"] = (obs["matcher_status"] == "MATCHER_UNEVALUATED"
                           and obs["primary_reason"] == exp["primary_reason"])
    if case.category == "A7" and case.stratum == "A":
        expected_sources = sorted(_source_key(u) for u in case.expected["unknown_sources"] or [])
        observed_sources = sorted(_source_key(u) for u in obs["unknown_sources"] or [])
        s["a7"] = {
            "violation": result == "VIOLATION",
            "partial": obs["matcher_status"] == "PARTIAL",
            "unknown_sources_match": bool(expected_sources) and observed_sources == expected_sources,
            "primary_reason_match": (case.expected["primary_reason"] is not None
                                     and obs["primary_reason"] == case.expected["primary_reason"]),
            "evaluation_incomplete": obs["evaluation_complete"] is False,
        }
        s["a7_ok"] = all(s["a7"].values())
    if case.stratum == "R":
        s["r_match"] = obs["matcher_outcome"] == label and (
            label != "UNEVALUATED" or obs["primary_reason"] == exp["primary_reason"])
    if case.role == "applicability":
        s["a9_match"] = obs["applicability"] == "EXCLUDED"
    if scored_aw and label == "NO_VIOLATION":
        s["credited"] = (result == "NO_VIOLATION" and obs["applicability"] == "APPLIED"
                         and obs["input_kind"] == "complete_source_file")
    s["binding_complete"] = binding_complete(obs, case)
    s["status_matches_manifest"] = obs["matcher_status"] == case.expected["matcher_status"]
    s["failures"] = _failure_classes(case, s)
    return s


def _failure_classes(case: Case, s: dict) -> list[str]:
    classes = []
    for key in ("miss", "false_block", "unsafe_pass", "unexpected_un_violation",
                "wrong_primary_reason"):
        if s[key]:
            classes.append(key)
    if s.get("un_correct") is False:
        classes.append("un_not_unevaluated_with_expected_reason")
    if s.get("a7_ok") is False:
        classes.append("a7_mixed_mismatch")
    if s.get("r_match") is False:
        classes.append("set_r_mismatch")
    if s.get("a9_match") is False:
        classes.append("a9_applicability_mismatch")
    scored_aw = case.stratum == "W" or (case.stratum == "A" and case.category != "A9")
    if scored_aw and not s["decided"]:
        classes.append("undecided")
    if not s["binding_complete"]:
        classes.append("binding_incomplete")
    return classes


# ── aggregate scoring: metrics, gates, headline ──────────────────────────────

def _ratio(numerator: int, denominator: int) -> dict:
    return {"numerator": numerator, "denominator": denominator}


def metrics_block(rows: list[tuple[Case, dict, dict]]) -> dict:
    def n(predicate: Callable[[Case, dict, dict], bool]) -> int:
        return sum(1 for case, obs, s in rows if predicate(case, obs, s))

    a = lambda c: c.stratum == "A" and c.category != "A9"  # noqa: E731
    aw = lambda c: a(c) or c.stratum == "W"  # noqa: E731
    return {
        "cases": len(rows),
        "misses": n(lambda c, o, s: s["miss"]),
        "false_blocks": n(lambda c, o, s: s["false_block"]),
        "unsafe_passes": n(lambda c, o, s: s["unsafe_pass"]),
        "unexpected_un_violations": n(lambda c, o, s: s["unexpected_un_violation"]),
        "wrong_primary_reasons": n(lambda c, o, s: s["wrong_primary_reason"]),
        "coverage_a": _ratio(n(lambda c, o, s: a(c) and s["decided"]), n(lambda c, o, s: a(c))),
        "coverage_w": _ratio(n(lambda c, o, s: c.stratum == "W" and s["decided"]),
                             n(lambda c, o, s: c.stratum == "W")),
        "unevaluated_rate": {
            "violation_labels_a_u_w": _ratio(
                n(lambda c, o, s: aw(c) and s["label"] == "VIOLATION" and s["unevaluated"]),
                n(lambda c, o, s: aw(c) and s["label"] == "VIOLATION")),
            "benign_labels_a_u_w": _ratio(
                n(lambda c, o, s: aw(c) and s["label"] == "NO_VIOLATION" and s["unevaluated"]),
                n(lambda c, o, s: aw(c) and s["label"] == "NO_VIOLATION")),
            "u": _ratio(n(lambda c, o, s: c.stratum == "U" and s["unevaluated"]),
                        n(lambda c, o, s: c.stratum == "U")),
            "n": _ratio(n(lambda c, o, s: c.stratum == "N" and s["unevaluated"]),
                        n(lambda c, o, s: c.stratum == "N")),
        },
        "binding_complete": _ratio(n(lambda c, o, s: s["binding_complete"]), len(rows)),
        "results": dict(sorted(Counter(o["result"] for _, o, _ in rows).items())),
    }


def compute_metrics(rows: list[tuple[Case, dict, dict]], pins: Pins) -> dict:
    by_stratum = {
        stratum: metrics_block([r for r in rows if r[0].stratum == stratum])
        for stratum in STRATA
    }
    by_shape = {
        shape: metrics_block([r for r in rows if r[0].shape == shape])
        for shape in pins.shapes
    }
    by_category = {
        form: metrics_block([r for r in rows if r[0].form == form])
        for form in sorted({r[0].form for r in rows})
    }
    return {"aggregate": metrics_block(rows), "stratum": by_stratum,
            "shape": by_shape, "form": by_category}


def headline(rows: list[tuple[Case, dict, dict]], pins: Pins) -> dict:
    """Criteria §5 wording, per shape, plus set R."""
    lines = {}
    for shape in pins.shapes:
        w = [s for c, _, s in rows if c.stratum == "W" and c.shape == shape]
        a = [s for c, _, s in rows if c.stratum == "A" and c.category != "A9" and c.shape == shape]
        u = [(c, s) for c, _, s in rows if c.stratum == "U" and c.shape == shape]
        lines[shape] = (
            f"W decided {sum(s['decided'] for s in w)} of {len(w)}; "
            f"A decided {sum(s['decided'] for s in a)} of {len(a)}; "
            f"U unevaluated {sum(s['unevaluated'] for _, s in u)} of {len(u)} "
            f"(expected {len(u)})."
        )
    r = [s for c, _, s in rows if c.stratum == "R"]
    lines["R"] = f"R matched {sum(s['r_match'] for s in r)} of {len(r)}."
    return lines


def _gate(passed: bool, value: Any, requirement: str) -> dict:
    return {"result": "PASS" if passed else "FAIL", "value": value, "requirement": requirement}


def compute_gates(rows: list[tuple[Case, dict, dict]], pins: Pins) -> dict:
    """Criteria §5 gates 1-8 and 10 (9, 11 and 12 are run separately)."""
    agg = metrics_block(rows)
    aw = [r for r in rows if r[0].stratum == "W" or (r[0].stratum == "A" and r[0].category != "A9")]
    un = [r for r in rows if r[0].role == "unevaluated"]
    a7 = [r for r in rows if r[0].stratum == "A" and r[0].category == "A7"]
    r_set = [r for r in rows if r[0].stratum == "R"]
    misses = sum(s["miss"] for _, _, s in aw)
    false_blocks = sum(s["false_block"] for _, _, s in aw)
    un_correct = sum(s["un_correct"] for _, _, s in un)
    cov_a, cov_w = agg["coverage_a"], agg["coverage_w"]
    binding = agg["binding_complete"]
    r_reason_mismatch = sum(
        1 for c, o, s in r_set
        if s["label"] == "UNEVALUATED" and o["primary_reason"] != scoring_expectation(c)["primary_reason"]
    )
    return {
        "1": _gate(misses == 0, misses, "zero misses in strata A and W"),
        "2": _gate(false_blocks == 0, false_blocks, "zero false blocks in strata A and W"),
        "3": _gate(agg["unsafe_passes"] == 0, agg["unsafe_passes"], "zero unsafe passes"),
        "3a": _gate(
            bool(un) and un_correct == len(un),
            {"correct": un_correct, "of": len(un),
             "unsafe_passes": sum(s["unsafe_pass"] for _, _, s in un),
             "unexpected_un_violations": agg["unexpected_un_violations"]},
            "every U and N case returns MATCHER_UNEVALUATED with its expected primary reason",
        ),
        "4": _gate(
            bool(a7) and all(s["a7_ok"] for _, _, s in a7),
            {"matched": sum(s["a7_ok"] for _, _, s in a7), "of": len(a7)},
            "every A7 case: violation, PARTIAL, expected unknown sources and primary reason, "
            "evaluation_complete=false",
        ),
        "5": _gate(agg["wrong_primary_reasons"] == 0, agg["wrong_primary_reasons"],
                   "zero wrong primary reasons on adjudicated cases"),
        "6": _gate(cov_a["denominator"] > 0 and cov_a["numerator"] == cov_a["denominator"],
                   cov_a, "coverage A = 100%"),
        "7": _gate(
            cov_w["denominator"] > 0
            and Fraction(cov_w["numerator"], cov_w["denominator"]) >= pins.coverage_w_floor,
            cov_w, "coverage W >= 95%"),
        "8": _gate(
            len(r_set) == len(CRITERIA_R_TABLE) and all(s["r_match"] for _, _, s in r_set),
            {"matched": sum(s["r_match"] for _, _, s in r_set), "of": len(r_set),
             "unevaluated_reason_mismatches": r_reason_mismatch},
            "every set R case (R1-R18) matches criteria §2.6a",
        ) if pins.is_m4_frozen else _gate(
            bool(r_set) and all(s["r_match"] for _, _, s in r_set),
            {"matched": sum(s["r_match"] for _, _, s in r_set), "of": len(r_set),
             "unevaluated_reason_mismatches": r_reason_mismatch},
            "every set R case present matches criteria §2.6a (non-M4 pins)",
        ),
        "10": _gate(binding["denominator"] > 0 and binding["numerator"] == binding["denominator"],
                    binding, "binding completeness = 100%"),
    }


def failure_rows(rows: list[tuple[Case, dict, dict]]) -> list[dict]:
    """Charter §10: one row per failure, by opaque case_id."""
    out = []
    for case, obs, s in rows:
        exp = scoring_expectation(case)
        for classification in s["failures"]:
            row = {
                "case_id": case.case_id,
                "stratum": case.stratum,
                "category": case.category,
                "shape": case.shape,
                "classification": classification,
                "expected": exp,
                "observed": {
                    "applicability": obs["applicability"],
                    "matcher_status": obs["matcher_status"],
                    "matcher_outcome": obs["matcher_outcome"],
                    "primary_reason": obs["primary_reason"],
                },
            }
            if case.is_n2:
                row["invocation_form"] = ("--input --target-path" if case.target_path
                                          else "--input (no --target-path)")
                row["location"] = case.location
            out.append(row)
    out.sort(key=lambda r: (r["case_id"], r["classification"]))
    return out


# ── gates 11 and 12 ──────────────────────────────────────────────────────────

def _write_contract(directory: Path, vector: GoldenVector) -> None:
    (directory / "contract").mkdir(parents=True)
    (directory / "src").mkdir()
    title = "ADR-034 golden vector " + vector.label.replace("_", " ")
    text = _ADR_TEMPLATE.format(
        decision_id=vector.decision_id, title=title,
        scope=f"m4harness.{vector.label}", constraints=vector.constraints_markdown(),
    )
    (directory / "contract" / f"{vector.decision_id}-{vector.label}.md").write_text(
        text, encoding="utf-8", newline="\n")
    (directory / "src" / "probe.py").write_text("VALUE = 1\n", encoding="utf-8", newline="\n")


def _persisted_rule_ids(memory: Path, rule_type: str) -> list[str]:
    data = json.loads(memory.read_text(encoding="utf-8"))
    return sorted(r["rule_id"] for r in data["decision_index"]["rules"]
                  if r.get("rule_type") == rule_type)


def run_gate11(build: Interpreter, root: Path, cwd: Path, pins: Pins) -> dict:
    """Gate 11: golden rule ids, by the pinned identity function and end to end."""
    requests = [{
        "decision_id": g.decision_id, "rule_type": g.rule_type,
        "value": g.value, "canonical": g.canonical, "applicability": g.applicability,
    } for g in pins.golden]
    request_file = cwd / "identity-requests.json"
    request_file.write_text(json.dumps(requests), encoding="utf-8")
    computed = child_json(build, ["identity", str(request_file)], cwd, "gate11")
    request_file.unlink()
    vectors = []
    for vector, ident in zip(pins.golden, computed):
        directory = root / "gate11" / vector.label
        _write_contract(directory, vector)
        memory = directory / ".mneme" / "project_memory.json"
        record: dict[str, Any] = {"label": vector.label, "golden": vector.rule_id,
                                  "function_rule_id": ident["rule_id"],
                                  "function_value": ident["value"]}
        init = mneme_cli(build, ["init", "--path", str(memory)], cwd)
        imp = mneme_cli(build, ["adr", "import", str(directory / "contract"),
                                "--memory", str(memory), "--apply"], cwd)
        record["setup_exit_codes"] = [init.returncode, imp.returncode]
        persisted: list[str] = []
        trace_ids: list[str] = []
        trace_values: list[str] = []
        if init.returncode == 0 and imp.returncode == 0:
            persisted = _persisted_rule_ids(memory, vector.rule_type)
            check = mneme_cli(build, ["check", "--memory", str(memory), "--query", QUERY,
                                      "--mode", "strict", "--json", "--source-file",
                                      str(directory / "src" / "probe.py")], cwd)
            record["check_exit_code"] = check.returncode
            try:
                payload = json.loads(check.stdout.decode("utf-8"))
                for trace in payload.get("applicability") or []:
                    if trace.get("rule_type") == vector.rule_type:
                        trace_ids.append(trace.get("rule_id"))
                        trace_values.append(trace.get("rule_value"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                record["check_error"] = check.text("stderr")[-2000:]
        record["persisted_rule_ids"] = persisted
        record["trace_rule_ids"] = trace_ids
        expected_value = vector.value if vector.canonical is None else None
        value_ok = True
        if vector.canonical_text is not None:
            value_ok = ident["value"] == vector.canonical_text and trace_values == [vector.canonical_text]
        elif expected_value is not None:
            value_ok = ident["value"] == expected_value and trace_values == [expected_value]
        else:
            value_ok = trace_values == [ident["value"]]
        record["value_matches"] = value_ok
        record["reproduced"] = (
            ident["rule_id"] == vector.rule_id
            and persisted == [vector.rule_id]
            and trace_ids == [vector.rule_id]
            and value_ok
        )
        vectors.append(record)
    reproduced = sum(v["reproduced"] for v in vectors)
    literal_stable = all(v["reproduced"] for v, g in zip(vectors, pins.golden)
                         if g.rule_type == "FORBID_LITERAL")
    passed = bool(vectors) and reproduced == len(vectors)
    return {
        "result": "PASS" if passed else "FAIL",
        "value": {"reproduced": reproduced, "of": len(vectors),
                  "forbid_literal_ids_stable": literal_stable},
        "requirement": "every ADR-034 §5 golden vector reproduces against the pinned build "
                       "(identity function, persisted memory and check trace); "
                       "FORBID_LITERAL ids are byte-stable",
        "vectors": vectors,
    }


def evaluate_gate12(control: dict, refusal: dict) -> dict:
    control_ok = (
        control.get("memory_schema") == "mneme.decision-index/v1"
        and control.get("exit_codes") == [0, 0, 0]
        and control.get("payload_schema") == "mneme.check/v1"
        and control.get("verdict") == "PASS"
    )
    memory_ok = (
        refusal.get("memory_schema") == "mneme.decision-index/v2"
        and "numeric_upper_bound_rule" in (refusal.get("semantic_features") or [])
        and bool(refusal.get("numeric_rules"))
    )
    refused = (
        refusal.get("exit_code") not in (0, None)
        and refusal.get("timed_out") is False
        and refusal.get("stdout_has_verdict") is False
        and refusal.get("persistence_error") is True
        and refusal.get("memory_unchanged") is True
    )
    passed = control_ok and memory_ok and refused
    return {
        "result": "PASS" if passed else "FAIL",
        "value": {"control_reader_works": control_ok, "v2_numeric_memory": memory_ok,
                  "refused_not_dropped": refused},
        "requirement": "a reader without numeric_upper_bound_rule refuses v2 memory "
                       "containing the type; it is never dropped silently",
        "control": control,
        "refusal": refusal,
    }


def run_gate12(old: Interpreter | None, root: Path, cwd: Path, pins: Pins) -> dict:
    if old is None:
        return {"result": "NOT_RUN", "value": None,
                "requirement": "old-reader refusal (needs the old-reader environment)"}
    literal = next(g for g in pins.golden if g.rule_type == "FORBID_LITERAL")
    numeric = next(g for g in pins.golden if g.rule_type == NUMERIC)

    # Positive control: the old reader reads the v1 memory it writes itself,
    # so a refusal below is attributable to the v2 numeric memory.
    control_dir = root / "gate12" / "control"
    _write_contract(control_dir, literal)
    memory = control_dir / ".mneme" / "project_memory.json"
    probe = control_dir / "src" / "probe.py"
    steps = [
        mneme_cli(old, ["init", "--path", str(memory)], cwd),
        mneme_cli(old, ["adr", "import", str(control_dir / "contract"), "--memory",
                        str(memory), "--apply"], cwd),
    ]
    steps.append(mneme_cli(old, ["check", "--memory", str(memory), "--query", QUERY,
                                 "--mode", "strict", "--json", "--input", str(probe)], cwd))
    control: dict[str, Any] = {"exit_codes": [s.returncode for s in steps]}
    try:
        index = json.loads(memory.read_text(encoding="utf-8"))["decision_index"]
        control["memory_schema"] = index.get("schema")
        control["literal_rule_ids"] = sorted(r.get("rule_id") for r in index.get("rules", []))
        control["literal_rule_id_matches_golden"] = control["literal_rule_ids"] == [literal.rule_id]
    except (OSError, ValueError, KeyError, TypeError):
        control["memory_schema"] = None
    try:
        payload = json.loads(steps[2].stdout.decode("utf-8"))
        control["payload_schema"] = payload.get("schema")
        control["verdict"] = payload.get("verdict")
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        control["payload_schema"] = None

    # The refusal: v2 memory with a numeric rule, written by the pinned build.
    numeric_memory = root / "gate11" / numeric.label / ".mneme" / "project_memory.json"
    target = root / "gate12" / "refusal"
    target.mkdir(parents=True)
    (target / ".mneme").mkdir()
    copied = target / ".mneme" / "project_memory.json"
    refusal: dict[str, Any] = {}
    try:
        shutil.copyfile(numeric_memory, copied)
        index = json.loads(copied.read_text(encoding="utf-8"))["decision_index"]
        refusal["memory_schema"] = index.get("schema")
        refusal["semantic_features"] = index.get("semantic_features")
        refusal["numeric_rules"] = sorted(r.get("rule_id") for r in index.get("rules", [])
                                          if r.get("rule_type") == NUMERIC)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        refusal["setup_error"] = str(exc)
        return evaluate_gate12(control, refusal)
    before = sha256_file(copied)
    (target / "probe.py").write_text("VALUE = 1\n", encoding="utf-8", newline="\n")
    step = mneme_cli(old, ["check", "--memory", str(copied), "--query", QUERY, "--mode",
                           "strict", "--json", "--input", str(target / "probe.py")], cwd)
    stderr = step.text("stderr")
    refusal["exit_code"] = step.returncode
    refusal["timed_out"] = step.timed_out
    refusal["stdout_has_verdict"] = _has_verdict(step.stdout)
    refusal["persistence_error"] = "DecisionIndexPersistenceError" in stderr
    refusal["error_line"] = stderr.strip().splitlines()[-1] if stderr.strip() else ""
    refusal["memory_unchanged"] = sha256_file(copied) == before
    return evaluate_gate12(control, refusal)


def _has_verdict(stdout: bytes) -> bool:
    try:
        payload = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and "verdict" in payload


# ── normalization and determinism (gate 9) ───────────────────────────────────

def normalize(text: str, run_root: str) -> str:
    """Charter §6: replace the per-run temporary root path string, and nothing else.

    The string is replaced as it appears in the JSON text written by this
    harness, that is in its JSON-escaped spelling (identical to the raw
    string on POSIX; backslashes doubled on Windows).
    """
    return text.replace(json.dumps(run_root)[1:-1], ROOT_TOKEN)


def dump_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def compare_runs(summaries: list[tuple[str, str]]) -> dict:
    """Gate 9 over ``[(summary_text, run_root), ...]`` for the two runs."""
    raw = [sha256_bytes(text.encode("utf-8")) for text, _ in summaries]
    normalized = [normalize(text, root) for text, root in summaries]
    digests = [sha256_bytes(text.encode("utf-8")) for text in normalized]
    identical = len(summaries) == 2 and normalized[0] == normalized[1]
    return {
        "result": "PASS" if identical else "FAIL",
        "value": {"normalized_summary_sha256": digests, "raw_summary_sha256": raw},
        "requirement": "two runs with byte-identical summaries after replacing only the "
                       "per-run temporary root path string",
    }


# ── one scoring pass ─────────────────────────────────────────────────────────

@dataclasses.dataclass
class Prepared:
    corpus: Path
    cases: list[Case]
    layouts: dict[str, Layout]
    build: Interpreter
    old: Interpreter | None
    pins: Pins
    template: str
    preconditions: dict
    manifest_findings: list[dict]
    harness_sha256: dict


def reserve_run_root(work_dir: Path | None) -> Path:
    """A fresh path for the per-run temporary root, used by both passes.

    Each pass creates the directory (it must not exist), runs entirely inside
    it, and removes it. Reusing one path keeps every spelling of the root
    (JSON-escaped, ``repr``-escaped inside a message, resolved) identical
    across the two passes, so gate 9 never has to rewrite anything but the
    root string itself.
    """
    base = str(work_dir) if work_dir is not None else None
    root = Path(tempfile.mkdtemp(prefix="m4-run-", dir=base)).resolve()
    root.rmdir()
    return root


def run_pass(prep: Prepared, number: int, root: Path, out_dir: Path,
             keep_run_root: bool) -> tuple[str, str, dict]:
    """One complete scoring pass. Returns (summary text, run root, summary)."""
    try:
        root.mkdir()
    except OSError as exc:
        raise Refusal("run_root", f"run {number}: cannot create a fresh {root}: {exc}") from exc
    try:
        corpus = root / "corpus"
        cwd = root / "cwd"
        shutil.copytree(prep.corpus, corpus, symlinks=True)
        cwd.mkdir()
        files = parse_files_sha256((corpus / "FILES.sha256").read_text(encoding="utf-8"))
        copy_check = verify_files(corpus, files)
        if copy_check["failures"] or copy_check["ok"] != prep.pins.files_count:
            raise Refusal("files_sha256", f"run {number} corpus copy does not verify")
        probe_start = probe_build(prep.build, cwd, prep.pins)

        executions: dict[str, dict] = {}
        for case in prep.cases:
            executions[case.case_id] = execute_case(
                case, prep.layouts[case.case_id], corpus, prep.build, cwd)
        assess_trust(prep.build, executions, cwd)

        records = []
        rows: list[tuple[Case, dict, dict]] = []
        operational = []
        for case in prep.cases:
            execution = executions[case.case_id]
            record: dict[str, Any] = {
                "schema": CASE_RECORD_SCHEMA,
                "case_id": case.case_id,
                "stratum": case.stratum,
                "category": case.category,
                "form": case.form,
                "shape": case.shape,
                "invocation": {"transport": case.transport, "path": case.path,
                               "target_path": case.target_path, "location": case.location},
                "layout": prep.layouts[case.case_id].geometry,
                "expected": case.expected,
                "scoring_expectation": scoring_expectation(case),
                "input_sha256": execution["input_sha256"],
                "steps": {},
                "trust": execution.get("trust"),
            }
            for name, step in execution["steps"].items():
                record["steps"][name] = step.record(include_stdout=name != "check")
            check = execution["steps"].get("check")
            observation = None
            if check is not None and not execution["operational"]:
                payload = json.loads(check.stdout.decode("utf-8"))
                record["payload"] = payload
                observation, problem = observe(payload, check.returncode)
                if problem:
                    execution["operational"].append(problem)
            elif check is not None:
                record["check_stdout"] = check.text("stdout")
            record["operational"] = execution["operational"]
            if execution["operational"]:
                operational.append({"case_id": case.case_id, "stratum": case.stratum,
                                    "category": case.category, "shape": case.shape,
                                    "reasons": execution["operational"]})
            else:
                score = score_case(case, observation)
                observation = dict(observation)
                observation["subject_matches_input_bytes"] = (
                    observation["subject_sha256"] == execution["input_sha256"])
                record["observed"] = observation
                record["score"] = score
                rows.append((case, observation, score))
            records.append(record)

        gate11 = run_gate11(prep.build, root, cwd, prep.pins)
        gate12 = run_gate12(prep.old, root, cwd, prep.pins)
        probe_end = probe_build(prep.build, cwd, prep.pins)

        cases_text = "".join(
            json.dumps(r, sort_keys=True, ensure_ascii=True) + "\n" for r in records)
        run_dir = out_dir / f"run-{number}"
        run_dir.mkdir()
        (run_dir / "cases.jsonl").write_text(cases_text, encoding="utf-8", newline="\n")

        gates = compute_gates(rows, prep.pins)
        gates["11"] = gate11
        gates["12"] = gate12
        summary = {
            "schema": RUN_SUMMARY_SCHEMA,
            "run_root": str(root),
            "pins": pins_record(prep.pins),
            "harness_sha256": prep.harness_sha256,
            "build": {k: probe_start[k] for k in (
                "python_implementation", "python_version", "python_executable",
                "platform", "mneme_dir", "mneme_version", "mneme_tree")},
            "build_tree_at_end": probe_end["mneme_tree"],
            "preconditions": prep.preconditions,
            "case_root_template": prep.template,
            "corpus_copy_files_ok": copy_check["ok"],
            "invocation": {"query": QUERY, "mode": "strict", "json": True},
            "manifest_findings": prep.manifest_findings,
            "operational_failures": {"count": len(operational), "cases": operational},
            "scored_cases": len(rows),
            "gates": dict(sorted(gates.items(), key=lambda kv: _gate_order(kv[0]))),
            "headline": headline(rows, prep.pins),
            "metrics": compute_metrics(rows, prep.pins),
            "a9_applicability": {
                "matched": sum(s.get("a9_match", False) for _, _, s in rows),
                "of": sum(1 for c, _, _ in rows if c.role == "applicability"),
            },
            "n2_applicability_recorded": [
                {"case_id": c.case_id, "form": c.form, "location": c.location,
                 "applicability": o["applicability"]}
                for c, o, _ in rows if c.is_n2
            ],
            "diagnostics": {
                "subject_matches_input_bytes": {
                    "source_file": _ratio(
                        sum(1 for c, o, _ in rows if c.transport == "source_file"
                            and o["subject_matches_input_bytes"]),
                        sum(1 for c, _, _ in rows if c.transport == "source_file")),
                    "input": _ratio(
                        sum(1 for c, o, _ in rows if c.transport == "input"
                            and o["subject_matches_input_bytes"]),
                        sum(1 for c, _, _ in rows if c.transport == "input")),
                },
                "matcher_status_matches_manifest": _ratio(
                    sum(s["status_matches_manifest"] for _, _, s in rows), len(rows)),
            },
            "failures": failure_rows(rows),
            "cases_jsonl_normalized_sha256": sha256_bytes(
                normalize(cases_text, str(root)).encode("utf-8")),
        }
        text = dump_json(summary)
        (run_dir / "summary.json").write_text(text, encoding="utf-8", newline="\n")
        return text, str(root), summary
    finally:
        if keep_run_root:
            root.rename(root.with_name(f"{root.name}-kept-run{number}"))
        else:
            shutil.rmtree(root, ignore_errors=True)


def _gate_order(key: str) -> tuple[int, str]:
    digits = re.match(r"\d+", key)
    return (int(digits.group()) if digits else 99, key)


# ── orchestration ────────────────────────────────────────────────────────────

def harness_digests() -> dict:
    return {
        "benchmarks/adr034_m4/harness.py": sha256_file(Path(__file__).resolve()),
        "benchmarks/adr034_m4/m4_child.py": sha256_file(CHILD_SCRIPT),
    }


def prepare_output(out_dir: Path) -> None:
    if out_dir.exists():
        if not out_dir.is_dir() or any(out_dir.iterdir()):
            raise Refusal("output", f"output directory {out_dir} exists and is not empty")
    else:
        out_dir.mkdir(parents=True)


def prepare(corpus: Path, template: str, build: Interpreter, old: Interpreter | None,
            old_wheel: Path | None, pins: Pins, w_spec: str | None, cwd: Path) -> Prepared:
    """Every charter §6 / V-2 precondition, before any case runs."""
    preconditions: dict[str, Any] = {}
    build_probe = probe_build(build, cwd, pins)
    preconditions["build"] = {k: build_probe[k] for k in (
        "python_implementation", "python_version", "mneme_dir", "mneme_tree")}
    if old is not None:
        if old_wheel is None:
            raise Refusal("old_reader", "an old-reader wheel is required")
        old_probe = verify_old_reader(old, old_wheel, build_probe, cwd, pins)
        preconditions["old_reader"] = {k: old_probe[k] for k in (
            "python_version", "distribution_version", "mneme_dir", "wheel", "wheel_sha256",
            "wheel_files_verified", "wheel_sha256_matches_g1_record")}
    preconditions["corpus"] = verify_corpus(corpus, pins, w_spec)
    manifest_text = (corpus / PurePosixPath(preconditions["corpus"]["manifest"])).read_text(
        encoding="utf-8")
    cases, findings = parse_manifest(manifest_text)
    preconditions["counts"] = verify_counts(cases, pins)
    layouts = resolve_layouts(cases, template, corpus)
    findings = findings + label_findings(cases)
    geometry = [c.case_id for c in cases
                if layouts[c.case_id].geometry.get("location_consistent") is False]
    if geometry:
        findings.append({"case_id": None,
                         "finding": f"path geometry inconsistent with transport/location: {geometry}"})
    return Prepared(corpus=corpus, cases=cases, layouts=layouts, build=build, old=old,
                    pins=pins, template=template, preconditions=preconditions,
                    manifest_findings=findings, harness_sha256=harness_digests())


def _utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def score(*, corpus: Path, template: str, out_dir: Path, build: Interpreter,
          old: Interpreter | None, old_wheel: Path | None, pins: Pins = M4_PINS,
          w_spec: str | None = None, work_dir: Path | None = None,
          keep_run_roots: bool = False) -> dict:
    """Run the full protocol and write ``out_dir/summary.json``."""
    prepare_output(out_dir)
    started = _utc()
    final: dict[str, Any] = {
        "schema": SUMMARY_SCHEMA,
        "started_utc": started,
        "pins": pins_record(pins),
        "harness_sha256": harness_digests(),
        "case_root_template": template,
        "scrubbed_environment_variables": scrubbed_variables(),
    }
    scratch = Path(tempfile.mkdtemp(prefix="m4-pre-", dir=str(work_dir) if work_dir else None))
    try:
        try:
            prep = prepare(corpus.resolve(), template, build, old, old_wheel, pins, w_spec,
                           scratch)
        except Refusal as refusal:
            final.update({"result": "REFUSED", "refusal": {"check": refusal.check,
                                                           "detail": refusal.detail}})
            return _finish(out_dir, final)
        except Exception as exc:  # noqa: BLE001 - any crash refuses, never scores
            final.update({"result": "REFUSED", "refusal": {
                "check": "harness_error", "detail": f"{type(exc).__name__}: {exc}"}})
            return _finish(out_dir, final)
        final["preconditions"] = prep.preconditions
        runs = []
        root = reserve_run_root(work_dir)
        try:
            for number in (1, 2):
                runs.append(run_pass(prep, number, root, out_dir, keep_run_roots))
        except Refusal as refusal:
            final.update({"result": "INVALID", "refusal": {"check": refusal.check,
                                                           "detail": refusal.detail}})
            return _finish(out_dir, final)
        except Exception as exc:  # noqa: BLE001 - a crash is operational (criteria §3)
            final.update({"result": "INVALID", "refusal": {
                "check": "harness_error", "detail": f"{type(exc).__name__}: {exc}"}})
            return _finish(out_dir, final)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    gate9 = compare_runs([(text, root) for text, root, _ in runs])
    first = runs[0][2]
    gates = dict(first["gates"])
    gates["9"] = gate9
    gates = dict(sorted(gates.items(), key=lambda kv: _gate_order(kv[0])))
    operational = first["operational_failures"]["count"] + runs[1][2]["operational_failures"]["count"]
    if operational:
        result = "INVALID"
    elif any(g["result"] == "NOT_RUN" for g in gates.values()):
        result = "INCOMPLETE"
    elif all(g["result"] == "PASS" for g in gates.values()):
        result = "PASS"
    else:
        result = "FAIL"
    final.update({
        "result": result,
        "runs": [{"run": number, "run_root": root,
                  "summary_sha256": gate9["value"]["raw_summary_sha256"][number - 1],
                  "normalized_summary_sha256": gate9["value"]["normalized_summary_sha256"][number - 1]}
                 for number, (_, root, _) in zip((1, 2), runs)],
        "operational_failures": {"count": operational,
                                 "run_1": first["operational_failures"]["cases"],
                                 "run_2": runs[1][2]["operational_failures"]["cases"]},
        "gates": gates,
        "headline": first["headline"],
        "failures": first["failures"],
        "metrics": first["metrics"],
        "a9_applicability": first["a9_applicability"],
        "n2_applicability_recorded": first["n2_applicability_recorded"],
        "manifest_findings": first["manifest_findings"],
        "build": first["build"],
        "scope": ("Audit-only, Python-only, first-slice (G1) whole-file numeric audit on the "
                  "M4 synthetic corpus. No pre-write (G2) protection, CI enforcement or "
                  "generalization beyond the synthetic corpus is claimed."),
    })
    return _finish(out_dir, final)


def _finish(out_dir: Path, final: dict) -> dict:
    final["finished_utc"] = _utc()
    (out_dir / "summary.json").write_text(dump_json(final), encoding="utf-8", newline="\n")
    return final


EXIT_BY_RESULT = {"PASS": 0, "FAIL": 1}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("score", help="verify preconditions, run two passes, write the summary")
    p.add_argument("--corpus", required=True, type=Path,
                   help="decrypted corpus root (holds FILES.sha256)")
    p.add_argument("--case-root-template", required=True,
                   help="each case's policy root relative to the corpus root; placeholders "
                        "{case_id} {stratum} {category} {shape}")
    p.add_argument("--out", required=True, type=Path, help="new or empty output directory")
    p.add_argument("--old-reader-python", required=True,
                   help="python of the separate mneme-hq==0.10.0 environment (gate 12)")
    p.add_argument("--old-reader-wheel", required=True, type=Path,
                   help="the mneme-hq 0.10.0 wheel that environment was installed from")
    p.add_argument("--python", default=sys.executable,
                   help="scoring interpreter with the pinned build installed "
                        "(default: this interpreter)")
    p.add_argument("--w-spec", default=None,
                   help="W spec path relative to the corpus root (default: locate it by its "
                        "frozen SHA-256)")
    p.add_argument("--work-dir", type=Path, default=None,
                   help="parent for the per-run temporary roots (default: system temp)")
    p.add_argument("--keep-run-roots", action="store_true",
                   help="keep the per-run corpus copies (they hold decrypted case bytes)")
    args = parser.parse_args(argv)
    try:
        final = score(
            corpus=args.corpus, template=args.case_root_template, out_dir=args.out,
            build=Interpreter(args.python), old=Interpreter(args.old_reader_python),
            old_wheel=args.old_reader_wheel, w_spec=args.w_spec, work_dir=args.work_dir,
            keep_run_roots=args.keep_run_roots,
        )
    except Refusal as refusal:
        print(f"REFUSED: {refusal}", file=sys.stderr)
        return 2
    print(f"{final['result']}: {args.out / 'summary.json'}")
    if "refusal" in final:
        print(f"  {final['refusal']['check']}: {final['refusal']['detail']}", file=sys.stderr)
    return EXIT_BY_RESULT.get(final["result"], 2)


if __name__ == "__main__":
    raise SystemExit(main())

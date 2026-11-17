"""SYNTHETIC fixture corpus for the ADR-034 M4 scoring-harness tests.

Everything here is written by the harness author from ADR-034 (§2-§6, §5a)
and the frozen evaluation criteria alone. It is **not** drawn from, derived
from or shaped like any M4 (or v1) held-out case: the M4 corpus is sealed and
was never seen. The contracts, file contents, case ids and labels below are
invented for testing the harness and carry no information about the real
corpus.

``build(root)`` writes a small corpus in the charter §6 layout (``FILES.sha256``
and ``manifest.jsonl`` at the root, one policy root per case under
``cases/<case_id>``) and returns the pins a test needs to score it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SYNTHETIC_MARKER = "SYNTHETIC: harness test fixture, not an M4 case\n"

_ADR = """---
id: {adr_id}
title: "{title}"
status: accepted
priority: normal
date: 2026-10-23
scope: synthetic.{scope}
---

# {adr_id}: {title}

## Context

SYNTHETIC harness test fixture. Not an M4 case.

## Decision

{title}.

## Constraints

- FORBID_NUMERIC_ABOVE:
    language: python
{sources}    max: {max}
    inclusive: true
    unit: {unit}
    include_paths:
      - "src/**"
"""

CONTRACTS = {
    # S1: symbol only, dyadic max.
    "S1": dict(adr_id="ADR-901", title="Synthetic request timeout bound", scope="s1",
               sources="    symbol: REQUEST_TIMEOUT_S\n", max="2.5", unit="seconds"),
    # S3: symbol and call, integer max.
    "S3": dict(adr_id="ADR-903", title="Synthetic pool size bound", scope="s3",
               sources=("    symbol: POOL_SIZE\n    call:\n      function: open_pool\n"
                        "      position: 0\n"),
               max="8", unit="connections"),
    "R1": dict(adr_id="ADR-911", title="Synthetic set R1 bound", scope="r1",
               sources="    symbol: R_VALUE\n", max="0.3", unit="units"),
    "R2": dict(adr_id="ADR-912", title="Synthetic set R2 bound", scope="r2",
               sources="    symbol: R_VALUE\n", max="0.3", unit="units"),
    "R11": dict(adr_id="ADR-921", title="Synthetic set R11 bound", scope="r11",
                sources="    symbol: R_VALUE\n", max="5", unit="units"),
}


def _exp(applicability="APPLIED", status=None, outcome=None, reason=None, sources=None,
         complete=None):
    return {"applicability": applicability, "matcher_status": status,
            "matcher_outcome": outcome, "primary_reason": reason,
            "unknown_sources": sources, "evaluation_complete": complete}


VIOLATION = dict(status="RECOGNIZED", outcome="VIOLATION", complete=True)
WITHIN = dict(status="RECOGNIZED", outcome="NO_VIOLATION", complete=True)


def _unevaluated(reason, sources=None, applicability="APPLIED"):
    return _exp(applicability, "MATCHER_UNEVALUATED", "UNEVALUATED", reason, sources, False)


def _non_source(applicability="APPLIED"):
    return _unevaluated("INCOMPLETE_SOURCE_INPUT",
                        [{"kind": "input", "line": None, "reason": "INCOMPLETE_SOURCE_INPUT"}],
                        applicability)


# (case_id, stratum, category, shape, contract, files {relpath: text}, invocation, expected)
# File paths are relative to the case's policy root unless they start with "/",
# which places them relative to the corpus root.
CASES = [
    ("syn-a01", "A", "A1", "S1", "S1", {"src/settings.py": "REQUEST_TIMEOUT_S = 3\n"},
     ("source_file", "src/settings.py", None, None), _exp(**VIOLATION)),
    ("syn-a02", "A", "A4", "S1", "S1", {"src/settings.py": "REQUEST_TIMEOUT_S = 2.5\n"},
     ("source_file", "src/settings.py", None, None), _exp(**WITHIN)),
    ("syn-a03", "A", "A6", "S1", "S1",
     {"src/settings.py": "import os\n\nREQUEST_TIMEOUT_S = 1.5\n"},
     ("source_file", "src/settings.py", None, None), _exp(**WITHIN)),
    ("syn-a04", "A", "A9", "S1", "S1", {"tools/settings.py": "REQUEST_TIMEOUT_S = 9\n"},
     ("source_file", "tools/settings.py", None, None),
     _exp("EXCLUDED", None, None, None, None, True)),
    ("syn-a05", "A", "A2", "S3", "S3",
     {"src/db.py": "POOL_SIZE = 4\n\nopen_pool(20)\n"},
     ("source_file", "src/db.py", None, None), _exp(**VIOLATION)),
    ("syn-a06", "A", "A7", "S3", "S3",
     {"src/db.py": "POOL_SIZE = 20\n\nopen_pool(compute_size())\n"},
     ("source_file", "src/db.py", None, None),
     _exp("APPLIED", "PARTIAL", "VIOLATION", "UNRECOGNIZED_FORM",
          [{"kind": "call", "line": 3, "reason": "UNRECOGNIZED_FORM"}], False)),
    ("syn-a07", "A", "A6", "S3", "S3",
     {"src/db.py": "POOL_SIZE = 4\n\nopen_pool(POOL_SIZE)\n"},
     ("source_file", "src/db.py", None, None), _exp(**WITHIN)),
    ("syn-u01", "U", "U3", "S1", "S1", {"src/settings.py": "OTHER_TIMEOUT = 1\n"},
     ("source_file", "src/settings.py", None, None),
     _unevaluated("SOURCE_NOT_FOUND", [{"kind": "symbol", "line": None,
                                        "reason": "SOURCE_NOT_FOUND"}])),
    ("syn-u02", "U", "U4", "S1", "S1", {"src/settings.py": "REQUEST_TIMEOUT_S = None\n"},
     ("source_file", "src/settings.py", None, None),
     _unevaluated("UNRECOGNIZED_FORM", [{"kind": "symbol", "line": 1,
                                         "reason": "UNRECOGNIZED_FORM"}])),
    ("syn-u03", "U", "U2", "S3", "S3",
     {"src/db.py": "POOL_SIZE = 4\nPOOL_SIZE = 5\n\nopen_pool(4)\n"},
     ("source_file", "src/db.py", None, None), _unevaluated("AMBIGUOUS_BINDING")),
    ("syn-n01", "N", "N1", "S1", "S1", {"src/settings.py": "REQUEST_TIMEOUT_S = (\n"},
     ("source_file", "src/settings.py", None, None), _unevaluated("PARSE_FAILURE")),
    ("syn-n02", "N", "N2", "S1", "S1",
     {"src/prompt.txt": "Please set the request timeout to 1 second.\n"},
     ("input", "src/prompt.txt", None, "L1"), _non_source()),
    ("syn-n03", "N", "N2", "S1", "S1",
     {"docs/fragment.txt": "REQUEST_TIMEOUT_S = 1\n"},
     ("input", "docs/fragment.txt", None, "L2"), _non_source("EXCLUDED")),
    ("syn-n04", "N", "N2", "S1", "S1", {"delta.txt": "+REQUEST_TIMEOUT_S = 2\n"},
     ("input", "delta.txt", None, "L3"), _non_source("EXCLUDED")),
    ("syn-n05", "N", "N2", "S1", "S1", {"/inputs/stdin-like.txt": "REQUEST_TIMEOUT_S = 1\n"},
     ("input", "/inputs/stdin-like.txt", None, "L4"), _non_source(None)),
    ("syn-n06", "N", "N2", "S3", "S3", {"incoming/delta.txt": "open_pool(2)\n"},
     ("input", "incoming/delta.txt", "src/db.py", None), _non_source()),
    ("syn-w01", "W", "W", "S1", "S1",
     {"src/app.py": ("import logging\n\nREQUEST_TIMEOUT_S = 2\n\n\n"
                     "def handler(event):\n    logging.info(event)\n    return event\n")},
     ("source_file", "src/app.py", None, None), _exp(**WITHIN)),
    ("syn-w02", "W", "W", "S1", "S1",
     {"src/app.py": "REQUEST_TIMEOUT_S = 10\n\n\ndef run():\n    return REQUEST_TIMEOUT_S\n"},
     ("source_file", "src/app.py", None, None), _exp(**VIOLATION)),
    ("syn-w03", "W", "W", "S3", "S3",
     {"src/pool.py": ("POOL_SIZE = 6\n\n\ndef start():\n    return open_pool(POOL_SIZE)\n")},
     ("source_file", "src/pool.py", None, None), _exp(**WITHIN)),
    ("syn-w04", "W", "W", "S3", "S3",
     {"src/pool.py": "POOL_SIZE = 2\n\n\ndef start():\n    return open_pool(32)\n"},
     ("source_file", "src/pool.py", None, None), _exp(**VIOLATION)),
    ("syn-r01", "R", "R", "R1", "R1", {"src/r.py": "R_VALUE = 0.1 + 0.2\n"},
     ("source_file", "src/r.py", None, None), _exp(**VIOLATION)),
    ("syn-r02", "R", "R", "R2", "R2", {"src/r.py": "R_VALUE = 0.3\n"},
     ("source_file", "src/r.py", None, None), _exp(**WITHIN)),
    ("syn-r11", "R", "R", "R11", "R11", {"src/r.py": "R_VALUE = 2 ** 65\n"},
     ("source_file", "src/r.py", None, None),
     _unevaluated("UNRECOGNIZED_FORM", [{"kind": "symbol", "line": 1,
                                         "reason": "UNRECOGNIZED_FORM"}])),
]

W_SPEC = (
    SYNTHETIC_MARKER
    + "Synthetic W composition spec for harness tests: ordinary modules, "
      "supported value forms only, roughly half within and half above max.\n"
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_records() -> list[dict]:
    records = []
    for case_id, stratum, category, shape, contract, files, inv, expected in CASES:
        transport, path, target, location = inv
        rel = path[1:] if path.startswith("/") else f"cases/{case_id}/{path}"
        records.append({
            "case_id": case_id, "stratum": stratum, "category": category, "shape": shape,
            "contract": f"contracts/{contract}",
            "invocation": {"transport": transport, "path": rel, "target_path": target,
                           "location": location},
            "expected": expected,
            "rationale": "SYNTHETIC harness fixture; labelled from ADR-034 and the criteria.",
        })
    return records


def build(root: Path, records: list[dict] | None = None) -> dict:
    """Write the synthetic corpus under ``root``; return its frozen digests."""
    root.mkdir(parents=True, exist_ok=True)
    for name, fields in CONTRACTS.items():
        _write(root / "contracts" / name / f"{fields['adr_id']}-synthetic.md", _ADR.format(**fields))
    for case_id, _, _, _, _, files, _, _ in CASES:
        (root / "cases" / case_id).mkdir(parents=True, exist_ok=True)
        for rel, text in files.items():
            target = root / rel[1:] if rel.startswith("/") else root / "cases" / case_id / rel
            _write(target, text)
    _write(root / "w_spec.md", W_SPEC)
    records = manifest_records() if records is None else records
    _write(root / "manifest.jsonl",
           "".join(json.dumps(r, sort_keys=True) + "\n" for r in records))
    return seal(root)


def seal(root: Path) -> dict:
    """(Re)write FILES.sha256 over every regular file except itself."""
    listing = sorted(
        p.relative_to(root).as_posix() for p in root.rglob("*")
        if p.is_file() and p.name != "FILES.sha256"
    )
    lines = "".join(f"{_sha(root / rel)}  {rel}\n" for rel in listing)
    (root / "FILES.sha256").write_bytes(lines.encode("ascii"))
    return {
        "files_sha256_digest": _sha(root / "FILES.sha256"),
        "files_count": len(listing),
        "manifest_sha256": _sha(root / "manifest.jsonl"),
        "w_spec_sha256": _sha(root / "w_spec.md"),
    }

"""DG1F-C2 golden-output corpus: memory fixtures and output capture.

The C2 charter (docs/plans/2026-11-08-dg1f-c2-lifecycle-convergence-charter.md
§4) requires golden outputs captured from the pre-change build for every
consumer across six memory forms, and byte-for-byte reproduction after the
change. This module owns both halves:

- ``build_memory_fixtures`` writes the six committed memory files from
  ``tests/fixtures/dg1f_c2/legacy_source.json`` (run once; the files are
  committed so later code changes cannot silently alter the inputs);
- ``capture_all`` runs every charter §4 consumer over those files and returns
  normalized outputs, which ``tests/test_dg1f_c2_golden_parity.py`` compares
  with ``tests/fixtures/dg1f_c2/goldens.json``.

Regenerate (only with explicit review; goldens are the parity contract):

    python -m tests.dg1f_c2_corpus --build-memory   # inputs
    python -m tests.dg1f_c2_corpus --write-goldens  # expected outputs
"""
from __future__ import annotations

import copy
import re
import io
import json
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "dg1f_c2"
SOURCE = FIXTURES / "legacy_source.json"
MEMORY_DIR = FIXTURES / "memory"
GOLDENS = FIXTURES / "goldens.json"

FORMS = (
    "canonical_v1",
    "canonical_v2_applicability",
    "canonical_conflict",
    "canonical_dangling",
    "legacy_sectionless",
    "legacy_items",
)
CANONICAL_FORMS = FORMS[:4]

APPLICABILITY_DECISION = "C2-LIT"
APPLICABILITY_LABELS = ["windows"]
EVIDENCE_SHA = "0" * 40
EVIDENCE_SELECTOR = "tests/test_storage.py::test_sqlite_only"
MEMORY_ARG = ".mneme/project_memory.json"


# ── memory fixtures ─────────────────────────────────────────────────────────


def _dump(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=False) + "\n").encode("utf-8")


def _forms_from_source() -> dict[str, dict[str, Any]]:
    from mneme.decision_index_persistence import set_decision_applicability
    from tests.canonical_fixtures import canonical_document, v1_document

    legacy = json.loads(SOURCE.read_text(encoding="utf-8"))
    canonical_v2 = canonical_document(copy.deepcopy(legacy))
    canonical_v1 = v1_document(canonical_v2)

    with_applicability, changed = set_decision_applicability(
        copy.deepcopy(canonical_v2),
        decision_id=APPLICABILITY_DECISION,
        required_labels=APPLICABILITY_LABELS,
    )
    assert changed

    def with_relationship(target: str) -> dict[str, Any]:
        document = copy.deepcopy(canonical_v1)
        for row in document["decision_index"]["decisions"]:
            if row["decision_id"] == APPLICABILITY_DECISION:
                row["relationships"].append(
                    {"type": "supersedes", "target_decision_id": target}
                )
        return document

    items = copy.deepcopy(legacy)
    items["items"] = [
        {"id": "C2-ITEM-RULE", "type": "rule", "title": "No print debugging",
         "content": "Use the logging module", "tags": []},
        {"id": "C2-ITEM-AP", "type": "anti_pattern", "title": "eval(",
         "content": "Never evaluate user input", "tags": []},
    ]
    items["decisions"] = [
        d for d in items["decisions"] if d["id"] in {"C2-LIT", "C2-OLD"}
    ]

    return {
        "canonical_v1": canonical_v1,
        "canonical_v2_applicability": with_applicability,
        "canonical_conflict": with_relationship("C2-READY"),
        "canonical_dangling": with_relationship("GHOST-404"),
        "legacy_sectionless": legacy,
        "legacy_items": items,
    }


def build_memory_fixtures() -> None:
    for form, document in _forms_from_source().items():
        target = MEMORY_DIR / form / ".mneme" / "project_memory.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_dump(document))
    (MEMORY_DIR / "app.py").write_bytes(
        b"import psycopg2\nimport pickle\nimport mysqlclient\nimport cx_Oracle\n"
    )


# ── output capture ──────────────────────────────────────────────────────────


_WORK_PATH = re.compile(r"""<WORK>[^\s"'<>|,;:]*""")
_RUNTIME_FIELD = re.compile(r'"runtime": "CPython [0-9.]+[^"]*"')


def _normalize(text: str, workdir: Path) -> str:
    """Normalize only the temporary working-directory path.

    The capture runs in a fresh temporary directory, so its absolute path and
    the platform's separator inside paths under it are the only expected
    differences between runs and between Windows and Linux. Each such path is
    replaced by ``<WORK>`` plus a POSIX-separated relative tail, whether it was
    printed raw or JSON-escaped. Nothing outside those path tokens changes.
    """
    text = text.replace("\r\n", "\n")
    for raw in sorted(
        {str(workdir), str(workdir.resolve()), workdir.resolve().as_posix()},
        key=len,
        reverse=True,
    ):
        text = text.replace(json.dumps(raw)[1:-1], "<WORK>")
        text = text.replace(raw, "<WORK>")
    text = _WORK_PATH.sub(
        lambda m: m.group(0).replace("\\\\", "/").replace("\\", "/"), text
    )
    # The relative ``--memory`` argument, when echoed through ``Path``, uses
    # the platform separator. Normalize exactly that known token.
    native = str(Path(MEMORY_ARG))
    if native != MEMORY_ARG:
        text = text.replace(json.dumps(native)[1:-1], MEMORY_ARG)
        text = text.replace(native, MEMORY_ARG)
    # ``mneme.check/v1`` records the interpreter in ``subject.runtime``; it is
    # environment identity (CI runs CPython 3.11), not decision behavior.
    return _RUNTIME_FIELD.sub('"runtime": "<RUNTIME>"', text)


def _cli(workdir: Path, *args: str) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, "-m", "mneme", *args],
        cwd=workdir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_env(),
    )
    return {
        "exit": proc.returncode,
        "stdout": _normalize(proc.stdout, workdir),
        "stderr": _normalize(proc.stderr, workdir),
    }


def _env() -> dict[str, str]:
    import os

    env = {k: v for k, v in os.environ.items() if not k.startswith("MNEME_")}
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _in_process(workdir: Path, form: str) -> dict[str, Any]:
    from mneme.cli import _audit_payload
    from mneme.enforcer import _build_report
    from mneme.evidence import CiEvidenceDocument, match_ci_evidence
    from mneme.memory_store import MemoryStore
    from mneme.readiness import readiness_counts

    store = MemoryStore(workdir / ".mneme" / "project_memory.json")
    store.load()
    decisions = store.decisions()
    document = CiEvidenceDocument(
        repository_sha=EVIDENCE_SHA,
        producer_type="github-actions",
        producer_run_id="1",
        results=((EVIDENCE_SELECTOR, "passed"),),
    )
    report = _build_report(decisions, None, None)
    return {
        "runtime_decisions": [[d.id, d.status] for d in decisions],
        "readiness_counts": dict(readiness_counts(decisions)),
        "match_ci_evidence": match_ci_evidence(decisions, EVIDENCE_SHA, document),
        "build_report": json.loads(
            _normalize(json.dumps(_audit_payload(report), sort_keys=True), workdir)
        ),
    }


def _capture_form(form: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp) / "repo"
        shutil.copytree(MEMORY_DIR / form, workdir)
        shutil.copy(MEMORY_DIR / "app.py", workdir / "app.py")
        memory = MEMORY_ARG
        out: dict[str, Any] = {}

        out["audit"] = _cli(workdir, "audit", "--memory", memory, "--json", "audit.json")
        audit_json = workdir / "audit.json"
        out["audit_json"] = (
            _normalize(audit_json.read_text(encoding="utf-8"), workdir)
            if audit_json.exists() else None
        )
        out["protect_list"] = _cli(workdir, "protect", "list", "--memory", memory)
        for decision_id in ("C2-LIT", "C2-PICKLE", "C2-OLD", "C2-OLDPICKLE", "GHOST-404"):
            out[f"protect_status:{decision_id}"] = _cli(
                workdir, "protect", "status", decision_id, "--memory", memory
            )
            out[f"protect_validate:{decision_id}"] = _cli(
                workdir, "protect", "validate", decision_id, "--memory", memory
            )
        for mode in ("strict", "warn"):
            out[f"check:{mode}"] = _cli(
                workdir, "check", "--memory", memory, "--source-file", "app.py",
                "--query", "edit app.py", "--mode", mode,
            )
            out[f"check_json:{mode}"] = _cli(
                workdir, "check", "--memory", memory, "--source-file", "app.py",
                "--query", "edit app.py", "--mode", mode, "--json",
            )
        out["check_preview"] = _cli(
            workdir, "check", "--memory", memory, "--source-file", "app.py",
            "--query", "edit app.py", "--applicability-preview", "windows",
        )
        out["in_process"] = _in_process(workdir, form)
        return out


def capture_all() -> dict[str, Any]:
    return {form: _capture_form(form) for form in FORMS}


def write_goldens() -> None:
    GOLDENS.write_bytes(
        (json.dumps(capture_all(), indent=2, sort_keys=True) + "\n").encode("utf-8")
    )


if __name__ == "__main__":
    if "--build-memory" in sys.argv:
        build_memory_fixtures()
    if "--write-goldens" in sys.argv:
        write_goldens()

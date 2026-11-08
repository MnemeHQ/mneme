"""A small SYNTHETIC corpus for the ADR-034 G2-1 scoring harness tests.

Written by the scorer from ADR-034 §6a/§7a, the G2-1 charter, the
pre-registration (revision 2 + Amendment 1) and ``LAYOUT.md`` only. No case
here is drawn from, or modelled on, the sealed held-out corpus; the seven
public smoke cases are not reproduced either. Case ids use the corpus id
shape (``g2h-`` + 10 hex) but are derived from ``syn-`` labels, so they can
never collide with a sealed case by construction of content.

``build(root)`` writes a corpus root in the LAYOUT.md shape (``cases/``,
``CASE_INDEX.json``, ``PUBLIC_SMOKE.json``, ``FILES.sha256``) and returns the
pins the harness should be given for it.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

NUMERIC_CANONICAL = (
    '{"call":{"function":"classify","position":1},"inclusive":true,'
    '"language":"python","max":"5","symbol":"ROUTER_DEADLINE_S","unit":"seconds","v":1}'
)
LITERAL_VALUE = "retired-host.example"

_ADR_HEAD = """---
id: {id}
title: "{title}"
status: accepted
priority: normal
date: 2026-10-25
scope: synthetic.{scope}
---

# {id}: {title}

## Context

Scorer-authored synthetic harness fixture. Not a corpus case.

## Decision

{title}.

## Constraints

"""

NUMERIC_ADR = _ADR_HEAD.format(id="ADR-701", title="Synthetic deadline bound", scope="deadline") + """\
- FORBID_NUMERIC_ABOVE:
    language: python
    symbol: ROUTER_DEADLINE_S
    call:
      function: classify
      position: 1
    max: 5
    inclusive: true
    unit: seconds
    include_paths:
      - "src/**"
{exclude}"""

LITERAL_ADR = _ADR_HEAD.format(id="ADR-702", title="Synthetic retired host", scope="host") + f"""\
- FORBID_LITERAL:
    value: {LITERAL_VALUE}
    include_paths:
      - "src/**"
"""

COMPLIANT = (
    '"""Synthetic module."""\nROUTER_DEADLINE_S = 3\n\n'
    "def classify(text, deadline):\n    return text, deadline\n\n"
    "result = classify('a', ROUTER_DEADLINE_S)\n"
)
VIOLATING = COMPLIANT.replace("= 3", "= 9")
NO_SYMBOL = (
    "def classify(text, deadline):\n    return text, deadline\n\nresult = classify('a', 1)\n"
)


def _file(path: str, data: bytes) -> dict:
    return {"path": path, "bytes_b64": base64.b64encode(data).decode("ascii"),
            "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def _numeric_rule(exclude: list[str]) -> dict:
    return {"decision": "ADR-701", "type": "FORBID_NUMERIC_ABOVE",
            "canonical_value": NUMERIC_CANONICAL, "include_paths": ["src/**"],
            "exclude_paths": exclude}


def _literal_rule() -> dict:
    return {"decision": "ADR-702", "type": "FORBID_LITERAL", "value": LITERAL_VALUE,
            "include_paths": ["src/**"], "exclude_paths": []}


def _rule(applicability="APPLIED", status=None, outcome=None, reason=None, reasons=()):
    return {"applicability": applicability, "matcher_status": status,
            "matcher_outcome": outcome, "primary_reason": reason,
            "unknown_source_reasons": list(reasons)}


RECOGNIZED_VIOLATION = _rule(status="RECOGNIZED", outcome="VIOLATION")
RECOGNIZED_CLEAN = _rule(status="RECOGNIZED", outcome="NO_VIOLATION")
INCOMPLETE_INPUT = _rule(status="MATCHER_UNEVALUATED", outcome="UNEVALUATED",
                         reason="INCOMPLETE_SOURCE_INPUT", reasons=["INCOMPLETE_SOURCE_INPUT"])


def _spec(label, klass, content, *, mode="strict", target="src/router.py", adrs=("numeric",),
          exclude=(), repo_files=(), repo_dirs=("docs", "docs/adr", "src"), symlinks=(),
          memory=True, expected=None):
    return {"label": label, "class": klass, "content": content, "mode": mode,
            "target": target, "adrs": adrs, "exclude": list(exclude),
            "repo_files": list(repo_files), "repo_dirs": list(repo_dirs),
            "symlinks": list(symlinks), "memory": memory, "expected": expected}


def _routed(outcome, cause_rules, *, reo, per_rule, subject="proposed_new_source",
            trusted=True, exit_code=0, disposition="proceeded", blocked=(), literal=False,
            parity_hook=None, parity_input=None, target_after="absent"):
    return {
        "hook_exit": exit_code, "hook_disposition": disposition,
        "hook_invokes": "proposed_new_file", "hook_routed": True,
        "trusted_proposed_source": trusted, "subject_kind": subject,
        "numeric_rules": cause_rules, "literal_violation": literal,
        "block_attributed_to": list(blocked), "target_after_hook": target_after,
        "g2_evidence_record_expected": True, "evidence_hook_outcome": outcome,
        "relevant_enforcement_observed": reo,
        "relevant_enforcement_observed_per_rule": per_rule,
        "parity_with_baseline_hook": parity_hook, "parity_with_input_carrier": parity_input,
    }


def _unrouted(invokes, rules, *, exit_code=0, disposition="proceeded", subject="unverified_input",
              target_after="unchanged", from_baseline=False):
    return {
        "hook_exit": "observed_from_baseline" if from_baseline else exit_code,
        "hook_disposition": "observed_from_baseline" if from_baseline else disposition,
        "hook_invokes": invokes, "hook_routed": False, "trusted_proposed_source": False,
        "subject_kind": subject, "numeric_rules": rules, "literal_violation": False,
        "block_attributed_to": [], "target_after_hook": target_after,
        "g2_evidence_record_expected": False, "evidence_hook_outcome": None,
        "relevant_enforcement_observed": None, "relevant_enforcement_observed_per_rule": {},
        "parity_with_baseline_hook": True, "parity_with_input_carrier": None,
        "expected_from_baseline": from_baseline,
    }


def specs(symlinks: bool) -> list[dict]:
    """Every synthetic case. ``symlinks`` adds the link-dependent L cases."""
    out = [
        _spec("v-lf", "V", VIOLATING, expected=_routed(
            "refused", {"ADR-701": RECOGNIZED_VIOLATION}, reo=True, per_rule={"ADR-701": True},
            exit_code=2, disposition="refused", blocked=["numeric"])),
        _spec("c-lf", "C", COMPLIANT, expected=_routed(
            "proceeded", {"ADR-701": RECOGNIZED_CLEAN}, reo=True, per_rule={"ADR-701": True})),
        _spec("c-crlf", "C", COMPLIANT.replace("\n", "\r\n"), expected=_routed(
            "proceeded", {"ADR-701": RECOGNIZED_CLEAN}, reo=True, per_rule={"ADR-701": True})),
        _spec("us-symbol", "US", NO_SYMBOL, expected=_routed(
            "proceeded", {"ADR-701": _rule(status="MATCHER_UNEVALUATED", outcome="UNEVALUATED",
                                           reason="SOURCE_NOT_FOUND",
                                           reasons=["SOURCE_NOT_FOUND"])},
            reo=False, per_rule={"ADR-701": False})),
        _spec("up-bom", "UP", "﻿" + COMPLIANT, expected=_routed(
            "proceeded", {"ADR-701": _rule(status="MATCHER_UNEVALUATED", outcome="UNEVALUATED",
                                           reason="PARSE_FAILURE", reasons=["PARSE_FAILURE"])},
            reo=False, per_rule={"ADR-701": False})),
        _spec("w-violation", "W", VIOLATING, mode="warn", expected=_routed(
            "deferred", {"ADR-701": RECOGNIZED_VIOLATION}, reo=True, per_rule={"ADR-701": True},
            disposition="deferred", blocked=["numeric"])),
        _spec("lit-literal-only", "LIT", COMPLIANT + f"HOST = '{LITERAL_VALUE}'\n",
              adrs=("numeric", "literal"), expected=_routed(
                  "refused", {"ADR-701": RECOGNIZED_CLEAN}, reo=False,
                  per_rule={"ADR-701": False}, exit_code=2, disposition="refused",
                  blocked=["literal"], literal=True)),
        _spec("x-excluded", "X", VIOLATING, target="src/gen/router.py",
              exclude=["src/gen/**"], repo_dirs=("docs", "docs/adr", "src", "src/gen"),
              expected=_routed(
                  "proceeded", {"ADR-701": _rule(applicability="EXCLUDED")}, reo=False,
                  per_rule={}, subject="unverified_input", trusted=False,
                  parity_hook=True, parity_input=True)),
        _spec("p-literal-memory", "P", VIOLATING, adrs=("literal",), expected=_routed(
            "proceeded", {}, reo=False, per_rule={}, subject="none", trusted=False,
            parity_hook=True, parity_input=True)),
        _spec("l-existing", "L", VIOLATING,
              repo_files=[_file("src/router.py", COMPLIANT.encode("utf-8"))],
              expected=_unrouted("input", {"ADR-701": INCOMPLETE_INPUT})),
        _spec("l-missing-parent", "L", VIOLATING, target="src/newpkg/router.py",
              expected=_unrouted("input", {"ADR-701": INCOMPLETE_INPUT}, target_after="absent")),
        _spec("l-non-py", "L", VIOLATING, target="src/router.txt",
              expected=_unrouted("input", {"ADR-701": INCOMPLETE_INPUT}, target_after="absent")),
        _spec("l-blank", "L", "\n   \n", expected=_unrouted(
            "none", {}, subject="no_check", target_after="absent")),
        _spec("l-surrogate", "L", "A = 1\n\ud800\n", expected=_unrouted(
            None, {}, subject=None, target_after="absent", from_baseline=True)),
    ]
    if symlinks:
        out.append(_spec(
            "l-dangling-link", "L", VIOLATING,
            symlinks=[{"path": "src/router.py", "target": "missing.py", "directory": False}],
            expected=_unrouted("input", {"ADR-701": INCOMPLETE_INPUT},
                               target_after="unchanged_dangling_link")))
    return out


def case_id(label: str) -> str:
    return "g2h-" + hashlib.sha256(f"syn-{label}".encode("utf-8")).hexdigest()[:10]


def _byte_contract(content: str) -> str:
    if not content.strip():
        return "EMPTY"
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in content):
        return "SURROGATE"
    if content.startswith("﻿"):
        return "BOM"
    if "\r\n" in content:
        return "CRLF"
    return "LF"


def write_case(root: Path, spec: dict, *, public_smoke: bool = False) -> str:
    cid = case_id(spec["label"])
    directory = root / "cases" / cid
    directory.mkdir(parents=True)
    adr_files = []
    rules = []
    if "numeric" in spec["adrs"]:
        exclude = "".join(f'    exclude_paths:\n      - "{p}"\n' for p in spec["exclude"][:1])
        adr_files.append(_file("docs/adr/ADR-701-deadline.md",
                               NUMERIC_ADR.format(exclude=exclude).encode("utf-8")))
        rules.append(_numeric_rule(spec["exclude"]))
    if "literal" in spec["adrs"]:
        adr_files.append(_file("docs/adr/ADR-702-host.md", LITERAL_ADR.encode("utf-8")))
        rules.append(_literal_rule())
    memory = None
    if spec["memory"]:
        memory = {"path": ".mneme/project_memory.json",
                  "recipe": "compile docs/adr with the build under test",
                  "expected_decision_ids": sorted(r["decision"] for r in rules),
                  "expected_typed_rules": rules}
    case = {
        "schema": "mneme-heldout-034-g2/case/v1", "case_id": cid, "envelope_file": "envelope.json",
        "public_smoke": public_smoke,
        "fixture": {"availability_declaration": None, "memory": memory,
                    "repo_dirs": spec["repo_dirs"], "repo_files": adr_files + spec["repo_files"],
                    "repo_symlinks": spec["symlinks"], "workspace_dirs": [],
                    "workspace_layout": "{{WS}} empty; {{REPO}} = {{WS}}/repo"},
        "hook": {"availability": "open", "event": "PreToolUse", "extra_env": {},
                 "mode": spec["mode"]},
        "target": {"base": "REPO", "relative": spec["target"]},
    }
    envelope = {
        "session_id": f"syn-{cid}", "transcript_path": "{{WS}}/transcript.jsonl",
        "cwd": "{{REPO}}", "permission_mode": "default", "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "{{REPO}}/" + spec["target"], "content": spec["content"]},
        "tool_use_id": f"toolu_{cid[4:]}",
    }
    try:
        digest = hashlib.sha256(spec["content"].encode("utf-8")).hexdigest()
    except UnicodeEncodeError:
        digest = None
    expected = {"case_id": cid, "class": spec["class"], "public_smoke": public_smoke,
                "hook_mode": spec["mode"], "availability": "open",
                "expected_from_baseline": False, "byte_contract": _byte_contract(spec["content"]),
                "content_utf8_sha256": digest, "author_label_notes": {}}
    expected.update(spec["expected"])
    klass = spec["class"]
    expected["g2_false_block_gate_applies"] = (
        klass in {"C", "US", "UF", "UP", "X", "L", "W", "P"}
        and not expected["expected_from_baseline"] and not expected["literal_violation"])
    for name, value in (("case.json", case), ("envelope.json", envelope),
                        ("expected.json", expected)):
        text = json.dumps(value, indent=2, sort_keys=name != "envelope.json", ensure_ascii=True)
        (directory / name).write_text(text + "\n", encoding="ascii", newline="\n")
    return cid


def finish(root: Path) -> dict:
    """Write CASE_INDEX.json, PUBLIC_SMOKE.json and FILES.sha256; return pin values."""
    rows, counts = [], {}
    for directory in sorted((root / "cases").iterdir()):
        expected = json.loads((directory / "expected.json").read_text(encoding="ascii"))
        rows.append({"case_id": expected["case_id"], "class": expected["class"],
                     "public_smoke": expected["public_smoke"]})
        concealed, smoke = counts.get(expected["class"], (0, 0))
        counts[expected["class"]] = (concealed + (not expected["public_smoke"]),
                                     smoke + bool(expected["public_smoke"]))
    (root / "CASE_INDEX.json").write_text(json.dumps({"cases": rows}, indent=2) + "\n",
                                          encoding="ascii", newline="\n")
    smoke_ids = [r["case_id"] for r in rows if r["public_smoke"]]
    (root / "PUBLIC_SMOKE.json").write_text(
        json.dumps({"public_smoke_case_ids": smoke_ids}, indent=2) + "\n",
        encoding="ascii", newline="\n")
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    manifest = "".join(f"{hashlib.sha256((root / f).read_bytes()).hexdigest()}  {f}\n"
                       for f in files)
    (root / "FILES.sha256").write_text(manifest, encoding="ascii", newline="\n")
    return {"files_sha256_digest": hashlib.sha256(manifest.encode("ascii")).hexdigest(),
            "files_count": len(files), "counts": counts}


def build(root: Path, *, symlinks: bool, labels: list[str] | None = None) -> dict:
    for spec in specs(symlinks):
        if labels is None or spec["label"] in labels:
            write_case(root, spec)
    return finish(root)

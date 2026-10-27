"""A small SYNTHETIC corpus for the ADR-034 G2-1 R2 scoring harness tests.

Written by the R2 scorer from the R2 pre-registration (revision 2, Amendment
1), the R1 pre-registration it inherits, ADR-034 §3a/§7a/§7b and the R2
corpus README (format only). No case here is drawn from, or modelled on, the
sealed R2 corpus, and the 13 public smoke cases are not reproduced. Case ids
use the corpus id shape (``r2-`` + 10 hex) but are derived from ``syn-``
labels.

``build(root)`` writes a corpus root in the R2 README shape (``MANIFEST.json``,
``README.md``, ``cases/<id>/{case,envelope,expected}.json`` and
``fixture/repo/``) plus ``FILES.sha256``, and returns the pins the harness
should be given for it. Expected ``rule_id`` values are computed with the
ADR-030 §7 identity formula from each rule's canonical value.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

from mneme.rule_identity import rule_applicability, rule_id_of

NUMERIC = "FORBID_NUMERIC_ABOVE"

_ADR = """---
id: {id}
title: "{title}"
status: accepted
priority: normal
date: 2026-10-27
scope: synthetic_r2.{scope}
---

# {id}: {title}

## Context

Scorer-authored synthetic harness fixture. Not a corpus case.

## Decision

{title}.

## Constraints

{constraint}"""


def _numeric(symbol: str | None, function: str | None, maximum: int,
             include: tuple[str, ...] = ("src/**",), exclude: tuple[str, ...] = ()) -> tuple[str, str, dict]:
    lines = ["- FORBID_NUMERIC_ABOVE:", "    language: python"]
    canonical: dict = {"inclusive": True, "language": "python", "max": str(maximum),
                       "unit": "items", "v": 1}
    if symbol:
        lines.append(f"    symbol: {symbol}")
        canonical["symbol"] = symbol
    if function:
        lines += ["    call:", f"      function: {function}", "      position: 1"]
        canonical["call"] = {"function": function, "position": 1}
    lines += [f"    max: {maximum}", "    inclusive: true", "    unit: items", "    include_paths:"]
    lines += [f'      - "{p}"' for p in include]
    if exclude:
        lines.append("    exclude_paths:")
        lines += [f'      - "{p}"' for p in exclude]
    value = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return "\n".join(lines) + "\n", value, rule_applicability(list(include), list(exclude))


def _literal(value: str) -> str:
    return f'- FORBID_LITERAL:\n    value: {value}\n    include_paths:\n      - "src/**"\n'


@dataclasses.dataclass(frozen=True)
class Adr:
    id: str
    scope: str
    constraint: str
    value: str | None = None  # numeric canonical value
    applicability: dict | None = None

    @property
    def text(self) -> str:
        return _ADR.format(id=self.id, title=f"Synthetic {self.scope}", scope=self.scope,
                           constraint=self.constraint)

    @property
    def rule_id(self) -> str:
        return rule_id_of(self.id, NUMERIC, self.value, self.applicability)


def _adr(adr_id: str, scope: str, *args, **kwargs) -> Adr:
    constraint, value, applicability = _numeric(*args, **kwargs)
    return Adr(adr_id, scope, constraint, value, applicability)


A = _adr("ADR-801", "limit_a", "LIMIT_A", None, 10)
B = _adr("ADR-802", "limit_b", "LIMIT_B", None, 4)
F = _adr("ADR-803", "batch_call", None, "batch", 5)
X = _adr("ADR-804", "limit_x", "LIMIT_A", None, 10, exclude=("src/gen/**",))
LIT = Adr("ADR-805", "host", _literal("retired-host.example"))
PLAIN = Adr("ADR-806", "plain", "- Keep modules small.\n")


def rule(adr: Adr, status, outcome, reason=None, reasons=(), applicability="APPLIED") -> dict:
    return {"applicability": applicability, "matcher_outcome": outcome,
            "matcher_status": status, "primary_reason": reason, "rule_id": adr.rule_id,
            "rule_id_form_verified": not adr.applicability.get("exclude_paths"),
            "rule_key": adr.id[-1], "unknown_source_reason_set": sorted(set(reasons))}


def recognized(adr, outcome):
    return rule(adr, "RECOGNIZED", outcome)


def unevaluated(adr, reason):
    return rule(adr, "MATCHER_UNEVALUATED", "UNEVALUATED", reason, [reason])


def labels(*, exit_code, disposition, cause, rules, per_rule=None, ec=True, routed=True,
           record=True, subject="proposed_new_source", literal=False, fallback=False,
           target_exists=False, baseline_observed=False, checker=True, applied=None) -> dict:
    per_rule = per_rule if per_rule is not None else {}
    applied = sorted(per_rule) if applied is None else applied
    return {
        "applied_numeric_rule_ids": applied if record else None,
        "checker_invoked": checker, "disposition": disposition,
        "evaluation_complete": ec if record else None,
        "evidence_record_expected": record, "expected_cause": cause if record else None,
        "g6_routed_fallback": fallback, "hook_exit": exit_code,
        "legacy_baseline_observed": baseline_observed, "literal_violation": literal,
        "numeric_rules": rules,
        "relevant_enforcement_observed": any(per_rule.values()) if record else None,
        "relevant_enforcement_per_rule": per_rule if record else None,
        "routed": routed, "subject_kind": subject,
        "target_exists_after_hook": target_exists,
    }


CLEAN = "LIMIT_A = 3\n"
OVER = "LIMIT_A = 30\n"

# (label, class, adrs, content, target, labels, extra case fields)
SPECS = [
    ("syn-c", "C", [A], CLEAN, "src/clean.py",
     labels(exit_code=0, disposition="proceeded", cause="no_violation",
            rules=[recognized(A, "NO_VIOLATION")], per_rule={A.rule_id: True}), {}),
    ("syn-v", "V", [A], OVER, "src/over.py",
     labels(exit_code=2, disposition="refused", cause="numeric_violation",
            rules=[recognized(A, "VIOLATION")], per_rule={A.rule_id: True}), {}),
    ("syn-mr", "MR", [A, B], OVER, "src/mr.py",
     labels(exit_code=2, disposition="refused", cause="numeric_violation", ec=False,
            rules=[recognized(A, "VIOLATION"), unevaluated(B, "SOURCE_NOT_FOUND")],
            per_rule={A.rule_id: True, B.rule_id: False}), {}),
    ("syn-sc", "SC", [F], "def batch(name, n):\n    return n\n\nclass Job:\n    def batch(self, name, n):\n"
     "        return n\n\n    def run(self):\n        return self.batch('x', 99)\n\nbatch('x', 3)\n",
     "src/sc.py",
     labels(exit_code=0, disposition="proceeded", cause="no_violation",
            rules=[recognized(F, "NO_VIOLATION")], per_rule={F.rule_id: True}), {}),
    ("syn-sc-attr", "SC", [F], "import types\n\ndef batch(name, n):\n    return n\n\n"
     "obj = types.SimpleNamespace()\nobj.batch = None\nbatch('x', 3)\n", "src/sc_attr.py",
     labels(exit_code=0, disposition="proceeded", cause="fail_open", ec=False,
            rules=[unevaluated(F, "AMBIGUOUS_BINDING")], per_rule={F.rule_id: False}), {}),
    ("syn-lit", "LIT", [LIT, A], 'HOST = "retired-host.example"\nLIMIT_A = 3\n', "src/lit.py",
     labels(exit_code=2, disposition="refused", cause="literal_violation", literal=True,
            rules=[recognized(A, "NO_VIOLATION")], per_rule={A.rule_id: False}), {}),
    ("syn-w", "W", [A], OVER, "src/warn.py",
     labels(exit_code=0, disposition="deferred", cause="numeric_violation",
            rules=[recognized(A, "VIOLATION")], per_rule={A.rule_id: True}), {"mode": "warn"}),
    ("syn-x", "X", [X], OVER, "src/gen/x.py",
     labels(exit_code=0, disposition="proceeded", cause="no_violation",
            rules=[rule(X, None, None, applicability="EXCLUDED")], per_rule={},
            subject="unverified_input"),
     {"dirs": ["src/gen"]}),
    ("syn-p-crlf", "P", [PLAIN], "VALUE = 1\r\nOTHER = 2\r\n", "src/p.py",
     labels(exit_code=0, disposition="proceeded", cause="no_violation", rules=[], per_rule={},
            subject=None),
     {"features": ["crlf"]}),
    ("syn-l-existing", "L", [A], OVER, "src/existing.py",
     labels(exit_code=0, disposition="proceeded", cause=None, routed=False, record=False,
            subject="unverified_input", target_exists=True,
            rules=[unevaluated(A, "INCOMPLETE_SOURCE_INPUT")]),
     {"files": {"src/existing.py": b"LIMIT_A = 1\n"}}),
    ("syn-l-surrogate", "L", [A], "LIMIT_A = 1\n# \ud800\n", "src/surrogate.py",
     dict(labels(exit_code="baseline_observed", disposition="baseline_observed", cause=None,
                 routed=False, record=False, subject=None, baseline_observed=True,
                 checker=None, rules=[])),
     {"utf8": False}),
    ("syn-l-outside", "L", [A], OVER, "elsewhere/o.py",
     labels(exit_code=0, disposition="proceeded", cause=None, routed=False, record=False,
            subject=None, checker=False, rules=[]),
     {"root": "outside", "outside": ["elsewhere"]}),
    ("syn-smoke-v", "V", [A], OVER, "src/smoke.py",
     labels(exit_code=2, disposition="refused", cause="numeric_violation",
            rules=[recognized(A, "VIOLATION")], per_rule={A.rule_id: True}), {"public": True}),
]

# Needs symlinks: a routed Write through a link component falls back in the checker.
FALLBACK_SPEC = (
    "syn-l-fallback", "L", [A], OVER, "src/link/f.py",
    labels(exit_code=0, disposition="proceeded", cause="fail_open", fallback=True,
           subject="unverified_input", applied=[], per_rule={}, ec=None,
           rules=[unevaluated(A, "INCOMPLETE_SOURCE_INPUT")]),
    {"dirs": ["src/real"], "symlinks": [{"path": "src/link", "target": "real", "kind": "dir"}]},
)


def case_id(label: str) -> str:
    return "r2-" + hashlib.sha256(label.encode("ascii")).hexdigest()[:10]


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def write_case(cases: Path, spec: tuple) -> str:
    label, klass, adrs, content, target, expected, extra = spec
    cid = case_id(label)
    base = cases / cid
    for adr in adrs:
        _write(base / "fixture" / "repo" / "docs" / "adr" / f"{adr.id}.md", adr.text.encode())
    for rel, data in (extra.get("files") or {}).items():
        _write(base / "fixture" / "repo" / rel, data)
    target_dir = target.rsplit("/", 1)[0]
    root = extra.get("root", "repo")
    utf8 = extra.get("utf8", True)
    public = extra.get("public", False)
    mode = extra.get("mode", "strict")
    case = {
        "availability": "open", "byte_features": extra.get("features", ["lf"]),
        "case_id": cid, "class": klass, "content_utf8_encodable": utf8,
        "content_utf8_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest() if utf8 else None,
        "dirs": {"outside": extra.get("outside", []),
                 "repo": sorted(set(extra.get("dirs", []) + ([target_dir] if root == "repo"
                                                              and "link" not in target else [])))},
        "hook_mode": mode,
        "memory": {"compile_from": [f"docs/adr/{a.id}.md" for a in adrs],
                   "path": ".mneme/project_memory.json"},
        "public_smoke": public, "symlinks": extra.get("symlinks", []),
        "target": {"rel": target, "root": root},
    }
    token = "${REPO}" if root == "repo" else "${OUTSIDE}"
    envelope = {
        "cwd": "${REPO}", "hook_event_name": "PreToolUse", "permission_mode": "default",
        "session_id": f"00000000-0000-4000-8000-{cid[3:]}00",
        "tool_input": {"content": content, "file_path": f"{token}/{target}"},
        "tool_name": "Write", "tool_use_id": f"toolu_syn_{cid}",
        "transcript_path": "${CASE}/transcript.jsonl",
    }
    has_cr = "\r" in content
    full = dict(expected, availability="open", case_id=cid, **{"class": klass},
                hook_mode=mode, routed_cr_parity_exception=expected["routed"] and has_cr,
                scenario_tag=label)
    _write(base / "case.json", (json.dumps(case, indent=2, sort_keys=True) + "\n").encode())
    _write(base / "envelope.json", (json.dumps(envelope, indent=2, sort_keys=True) + "\n").encode())
    _write(base / "expected.json", (json.dumps(full, indent=2, sort_keys=True) + "\n").encode())
    return cid


def build(root: Path, h, specs=None) -> "h.Pins":
    """Write the corpus at ``root`` and return the harness pins for it."""
    specs = list(SPECS if specs is None else specs)
    cases = root / "cases"
    rows = []
    for spec in specs:
        cid = write_case(cases, spec)
        rows.append({"case_id": cid, "class": spec[1],
                     "public_smoke": bool(spec[6].get("public"))})
    rows.sort(key=lambda r: r["case_id"])
    (root / "MANIFEST.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="ascii")
    (root / "README.md").write_text("Synthetic R2 harness test corpus.\n", encoding="ascii")
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    manifest = "".join(f"{h.sha256_file(root / f)}  {f}\n" for f in files)
    (root / "FILES.sha256").write_text(manifest, encoding="ascii", newline="\n")
    counts = {k: [0, 0] for k in h.CLASSES}
    for row in rows:
        counts[row["class"]][1 if row["public_smoke"] else 0] += 1
    return dataclasses.replace(
        h.R2_PINS, files_sha256_digest=hashlib.sha256(manifest.encode()).hexdigest(),
        files_count=len(files), counts={k: tuple(v) for k, v in counts.items()},
        is_frozen=False)

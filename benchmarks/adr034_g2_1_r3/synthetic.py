"""Scorer-authored synthetic cases (public; never R3 corpus cases).

They exercise paths the 14 public smoke cases do not: AT-SI, AT-SX, both
AT-W0 variants, a mixed LIT case, a warn-mode numeric deferral, a routed
checker fallback (R2 A2R2), the routed-CR G5 exception, the R1 Amendment 2
traceback comparison, and an unchecked out-of-root write. Labels are
written by hand from the contract. ``rule_id`` values use the ADR-030 §7
formula, whose implementation here is pinned by the ADR-034 §5 golden
vectors in the unit tests. No D3 regression fixture, implementation output
or earlier corpus is used.

    python -m benchmarks.adr034_g2_1_r3.synthetic OUT_DIR
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from . import contract as C
from .oracle import Rule, canonical_json

_SESSION = {"session_id": "{{SESSION_ID}}", "cwd": "{{ROOT}}"}


def _adr(adr_id: str, title: str, constraints: str) -> dict:
    slug = title.lower().replace(" ", "-")
    scope = title.lower().replace(" ", "_")  # scope segments are [a-z0-9_]+
    text = (
        f"---\nid: {adr_id}\ntitle: \"{title}\"\nstatus: accepted\npriority: normal\n"
        f"date: 2026-10-28\nscope: scorer.synthetic.{scope}\n---\n\n# {adr_id}: {title}\n\n"
        f"**Status:** Accepted\n\n## Context\n\nScorer-authored synthetic fixture.\n\n"
        f"## Decision\n\n{title}.\n\n## Constraints\n\n{constraints}\n## Consequences\n\nNone.\n"
    )
    return {"base": "root", "path": f"docs/adr/{adr_id}-{slug}.md", "type": "file", "text": text}


def _numeric(symbol: str, max_: str, unit: str, include: list, exclude: list = ()) -> tuple:
    lines = [
        "- FORBID_NUMERIC_ABOVE:", "    language: python", f"    symbol: {symbol}",
        f"    max: {max_}", "    inclusive: true", f"    unit: {unit}", "    include_paths:",
        *[f'      - "{p}"' for p in include],
    ]
    if exclude:
        lines += ["    exclude_paths:", *[f'      - "{p}"' for p in exclude]]
    value = canonical_json({"v": 1, "language": "python", "symbol": symbol, "max": max_,
                            "inclusive": True, "unit": unit})
    return "\n".join(lines) + "\n", value, tuple(include), tuple(exclude)


def _nid(adr_id: str, spec: tuple) -> str:
    return Rule(adr_id, "", C.NUMERIC, spec[1], spec[2], spec[3]).rule_id


def _lid(adr_id: str, value: str, include=None, exclude=()) -> str:
    return Rule(adr_id, "", C.LITERAL, value, include, exclude).rule_id


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _case(case_id, cls, subclass, files, target, content, mode, labels) -> dict:
    return {
        "schema": C.CASE_SCHEMA, "case_id": case_id, "cls": cls, "subclass": subclass,
        "visibility": "public",
        "fixture": {"files": files,
                    "memory": {"compile_from": "docs/adr", "path": ".mneme/project_memory.json"}},
        "hook": {"mode": mode, "availability": "open"},
        "event": {"hook_event_name": "PreToolUse", "tool_name": "Write",
                  "target": {"base": "root", "path": target}, "content": content,
                  "envelope_extras": dict(_SESSION)},
        "labels": labels,
    }


def _labels(**kw) -> dict:
    base = {
        "routed": True, "checker_invoked": True, "expected_hook_exit": 0, "exit_source": "contract",
        "expected_disposition": "proceeded", "expected_cause": "none",
        "literal_violation_attribution": False, "target_after_hook": "absent",
        "checker": {"subject_kind": "absent", "subject_sha256": None, "governed_path": None,
                    "numeric_rules": [], "literal_violations": [], "evaluation_complete": True,
                    "legacy_parity": True},
        "evidence": {"record_expected": True, "checker_subject": None, "applied_rule_ids": [],
                     "per_rule_relevance": {}, "event_relevance": False, "evaluation_complete": True,
                     "violations": [], "g6_routed_fallback": False, "mode": "strict",
                     "hook_outcome": "proceeded"},
        "gates": ["G1", "G2", "G3", "G6", "G7", "G8"],
        "g5": {"hook_level": False, "checker_level": False, "cr_exception": False,
               "a2_candidate": False},
        "byte_features": ["lf"],
    }
    for key, value in kw.items():
        if key in ("checker", "evidence", "g5"):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def _excluded(rid: str, adr_id: str, reason=None) -> dict:
    entry = {"rule_id": rid, "rule_id_gated": False, "decision": adr_id, "applicability": "EXCLUDED"}
    if reason:
        entry["applicability_reason"] = reason
    return entry


def _literal_refusal(rid: str, mode: str = "strict") -> dict:
    refused = mode == "strict"
    return dict(
        expected_hook_exit=2 if refused else 0,
        expected_disposition="refused" if refused else "deferred",
        expected_cause="other_rule", literal_violation_attribution=True,
        gates=["G1", "G3", "G6", "G7", "G8"] if refused else ["G1", "G2", "G3", "G6", "G7", "G8"],
    ), {"rule_id": rid, "rule_type": C.LITERAL}


def build_cases() -> list:
    cases = []

    # AT-SI: numeric present, include miss (amendment 1 §2); literal is the sole cause.
    num = _numeric("FLUSH_EVERY_S", "10", "seconds", ["lib/**"])
    a1 = _adr("ADR-9101", "Flush cadence", num[0])
    a2 = _adr("ADR-9102", "Unsafe deserialization", "- FORBID_LITERAL: pickle.loads(\n")
    lid, nid = _lid("ADR-9102", "pickle.loads("), _nid("ADR-9101", num)
    kw, ident = _literal_refusal(lid)
    content = '"""Cache loader."""\nimport pickle\n\nFLUSH_EVERY_S = 99\n\n\ndef load(blob):\n    return pickle.loads(blob)\n'
    cases.append(_case("syn-at-si", "AT", "AT-SI", [a1, a2, {"base": "root", "path": "src/cache", "type": "dir"}],
                       "src/cache/loader.py", content, "strict", _labels(
        **kw, checker={"subject_kind": "unverified_input", "literal_violations": [ident],
                       "numeric_rules": [_excluded(nid, "ADR-9101", C.INCLUDE_MISS_REASON)]},
        evidence={"violations": [ident], "hook_outcome": "refused"})))

    # AT-SX: include matches, exclude matches (precedence), scoped literal.
    num = _numeric("RETRY_BUDGET", "3", "attempts", ["src/**"], ["src/legacy/**"])
    a1 = _adr("ADR-9111", "Retry budget", num[0])
    lit = '- FORBID_LITERAL:\n    value: os.system(\n    include_paths:\n      - "src/**"\n'
    a2 = _adr("ADR-9112", "Shell escapes", lit)
    lid, nid = _lid("ADR-9112", "os.system(", ("src/**",)), _nid("ADR-9111", num)
    kw, ident = _literal_refusal(lid)
    content = '"""Legacy runner."""\nimport os\n\nRETRY_BUDGET = 12\n\n\ndef run(cmd):\n    return os.system(cmd)\n'
    cases.append(_case("syn-at-sx", "AT", "AT-SX", [a1, a2, {"base": "root", "path": "src/legacy", "type": "dir"}],
                       "src/legacy/runner.py", content, "strict", _labels(
        **kw, checker={"subject_kind": "unverified_input", "literal_violations": [ident],
                       "numeric_rules": [_excluded(nid, "ADR-9111")]},
        evidence={"violations": [ident], "hook_outcome": "refused"})))

    # AT-W0 literal-only (warn): deferral, no numeric trace.
    a1 = _adr("ADR-9121", "Debug prints", "- FORBID_LITERAL: pprint.pprint(\n")
    lid = _lid("ADR-9121", "pprint.pprint(")
    kw, ident = _literal_refusal(lid, "warn")
    content = '"""Report dump."""\nimport pprint\n\n\ndef dump(rows):\n    pprint.pprint(rows)\n'
    cases.append(_case("syn-at-w0-lit", "AT", "AT-W0", [a1, {"base": "root", "path": "src/report", "type": "dir"}],
                       "src/report/dump.py", content, "warn", _labels(
        **kw, checker={"literal_violations": [ident]},
        evidence={"violations": [ident], "mode": "warn", "hook_outcome": "deferred"})))

    # AT-W0 with an EXCLUDED numeric trace (warn).
    num = _numeric("BATCH_ROWS", "500", "rows", ["src/**"], ["src/tools/**"])
    a1 = _adr("ADR-9131", "Batch rows", num[0])
    a2 = _adr("ADR-9132", "Dynamic imports", "- FORBID_LITERAL: __import__(\n")
    lid, nid = _lid("ADR-9132", "__import__("), _nid("ADR-9131", num)
    kw, ident = _literal_refusal(lid, "warn")
    content = '"""Plugin tool."""\n\nBATCH_ROWS = 9000\n\n\ndef plugin(name):\n    return __import__(name)\n'
    cases.append(_case("syn-at-w0-ex", "AT", "AT-W0", [a1, a2, {"base": "root", "path": "src/tools", "type": "dir"}],
                       "src/tools/plugin.py", content, "warn", _labels(
        **kw, checker={"subject_kind": "unverified_input", "literal_violations": [ident],
                       "numeric_rules": [_excluded(nid, "ADR-9131")]},
        evidence={"violations": [ident], "mode": "warn", "hook_outcome": "deferred"})))

    # LIT mixed: numeric violation and literal violation on a proposed_new_source subject.
    num = _numeric("QUEUE_DEPTH", "64", "items", ["src/**"])
    a1 = _adr("ADR-9141", "Queue depth", num[0])
    a2 = _adr("ADR-9142", "Seeded randomness", "- FORBID_LITERAL: random.seed(\n")
    nid, lid = _nid("ADR-9141", num), _lid("ADR-9142", "random.seed(")
    content = '"""Queue."""\nimport random\n\nQUEUE_DEPTH = 128\n\n\ndef shuffle(items):\n    random.seed(7)\n    return items\n'
    cases.append(_case("syn-lit-mixed", "LIT", None, [a1, a2, {"base": "root", "path": "src/queue", "type": "dir"}],
                       "src/queue/depth.py", content, "strict", _labels(
        expected_hook_exit=2, expected_disposition="refused", expected_cause="numeric_violation",
        gates=["G1", "G3", "G6", "G7", "G8"],
        checker={"subject_kind": "proposed_new_source", "subject_sha256": _sha(content),
                 "governed_path": "src/queue/depth.py", "legacy_parity": False,
                 "literal_violations": [{"rule_id": lid, "rule_type": C.LITERAL}],
                 "numeric_rules": [{"rule_id": nid, "rule_id_gated": True, "decision": "ADR-9141",
                                    "applicability": "APPLIED", "matcher_status": "RECOGNIZED",
                                    "matcher_outcome": "VIOLATION", "primary_reason": None,
                                    "unknown_reasons": []}]},
        evidence={"checker_subject": "proposed_new_source", "applied_rule_ids": [nid],
                  "per_rule_relevance": {nid: True}, "event_relevance": True, "hook_outcome": "refused",
                  "violations": [{"rule_id": nid, "rule_type": C.NUMERIC},
                                 {"rule_id": lid, "rule_type": C.LITERAL}]})))

    # W: warn-mode numeric violation is deferred and relevant.
    num = _numeric("SPOOL_MB", "256", "megabytes", ["src/**"])
    a1 = _adr("ADR-9151", "Spool size", num[0])
    nid = _nid("ADR-9151", num)
    content = '"""Spool."""\n\nSPOOL_MB = 1024\n'
    cases.append(_case("syn-w-viol", "W", None, [a1, {"base": "root", "path": "src/spool", "type": "dir"}],
                       "src/spool/size.py", content, "warn", _labels(
        expected_disposition="deferred", expected_cause="numeric_violation",
        checker={"subject_kind": "proposed_new_source", "subject_sha256": _sha(content),
                 "governed_path": "src/spool/size.py", "legacy_parity": False,
                 "numeric_rules": [{"rule_id": nid, "rule_id_gated": True, "decision": "ADR-9151",
                                    "applicability": "APPLIED", "matcher_status": "RECOGNIZED",
                                    "matcher_outcome": "VIOLATION", "primary_reason": None,
                                    "unknown_reasons": []}]},
        evidence={"checker_subject": "proposed_new_source", "applied_rule_ids": [nid],
                  "per_rule_relevance": {nid: True}, "event_relevance": True, "mode": "warn",
                  "hook_outcome": "deferred", "violations": [{"rule_id": nid, "rule_type": C.NUMERIC}]})))

    # L routed fallback: a link component in the parent (ADR-034 §6a precondition 2).
    num = _numeric("FANOUT", "8", "peers", ["src/**"])
    a1 = _adr("ADR-9161", "Fanout", num[0])
    nid = _nid("ADR-9161", num)
    content = '"""Gossip."""\n\nFANOUT = 32\n'
    files = [a1, {"base": "root", "path": "src/net", "type": "dir"},
             {"base": "root", "path": "alias", "type": "dir_symlink", "target": "src/net"}]
    cases.append(_case("syn-l-fallback", "L", None, files, "alias/gossip.py", content, "strict", _labels(
        expected_cause="numeric_unevaluated", gates=["G1", "G2", "G3", "G5", "G6", "G7", "G8"],
        g5={"hook_level": True},
        checker={"subject_kind": "unverified_input", "evaluation_complete": False,
                 "numeric_rules": [{"rule_id": nid, "rule_id_gated": False, "decision": "ADR-9161",
                                    "applicability": "APPLIED", "matcher_status": "MATCHER_UNEVALUATED",
                                    "matcher_outcome": "UNEVALUATED",
                                    "primary_reason": "INCOMPLETE_SOURCE_INPUT",
                                    "unknown_reasons": ["INCOMPLETE_SOURCE_INPUT"]}]},
        evidence={"evaluation_complete": False, "g6_routed_fallback": True})))

    # P with CRLF content: routed-CR exception -> checker-level parity only.
    a1 = _adr("ADR-9171", "Exec calls", "- FORBID_LITERAL: exec(\n")
    content = '"""Formatter."""\r\n\r\n\r\ndef fmt(value):\r\n    return f"{value:>8}"\r\n'
    cases.append(_case("syn-p-crlf", "P", None, [a1, {"base": "root", "path": "src/fmt", "type": "dir"}],
                       "src/fmt/pad.py", content, "strict", _labels(
        gates=["G1", "G2", "G3", "G5", "G6", "G7", "G8"],
        g5={"hook_level": True, "checker_level": True, "cr_exception": True}, byte_features=["crlf"])))

    # L lone surrogate: unrouted, baseline-observed outcome, R1 Amendment 2 scope.
    a1 = _adr("ADR-9181", "Eval calls", "- FORBID_LITERAL: eval(\n")
    content = '"""Bad text."""\nNAME = "\ud800"\n'
    cases.append(_case("syn-l-surrogate", "L", None, [a1, {"base": "root", "path": "src/text", "type": "dir"}],
                       "src/text/bad.py", content, "strict", _labels(
        routed=False, expected_hook_exit=None, exit_source="baseline_observed",
        expected_disposition="baseline_observed", expected_cause="legacy_unrouted",
        gates=["G3", "G5", "G6", "G7", "G8"], g5={"hook_level": True, "a2_candidate": True},
        checker={"subject_kind": None, "evaluation_complete": None},
        evidence={"record_expected": False, "event_relevance": None, "evaluation_complete": None,
                  "hook_outcome": None},
        byte_features=["lone_surrogate"])))

    # L outside the policy root: no memory, nothing checked.
    a1 = _adr("ADR-9191", "Eval calls outside", "- FORBID_LITERAL: eval(\n")
    case = _case("syn-l-outside", "L", None, [a1, {"base": "outside", "path": "tmp", "type": "dir"}],
                 "tmp/x.py", 'X = eval("1")\n', "strict", _labels(
        routed=False, checker_invoked=False, expected_disposition="not_checked",
        expected_cause="not_checked", gates=["G2", "G3", "G5", "G6", "G7", "G8"],
        g5={"hook_level": True}, checker={"subject_kind": None, "evaluation_complete": None},
        evidence={"record_expected": False, "event_relevance": None, "evaluation_complete": None,
                  "hook_outcome": None}))
    case["event"]["target"]["base"] = "outside"
    cases.append(case)
    return cases


def write(out: Path) -> None:
    for case in build_cases():
        d = out / case["case_id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "case.json").write_text(json.dumps(case, indent=1, ensure_ascii=True) + "\n", encoding="ascii")


if __name__ == "__main__":
    write(Path(sys.argv[1]))

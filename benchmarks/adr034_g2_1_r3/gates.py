"""G1-G8 for one case, and the corpus-level decision (R1 §5, R2 §5, R3 §3/§6.2).

Expected values come from the oracle (``oracle.Expectation``). Observations
come from ``runner.observe``. A gate a case does not participate in is
``applies: False``; a participating gate passes only with no failure.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from . import attribution, coverage
from . import contract as C
from .runner import raw

_TRACEBACK = b"Traceback (most recent call last):"


def _numeric_traces(payload: Optional[dict]) -> dict:
    if not isinstance(payload, dict):
        return {}
    return {
        item.get("rule_id"): item for item in payload.get("applicability") or []
        if isinstance(item, dict) and item.get("rule_type") == C.NUMERIC
    }


def _record(obs: dict) -> Optional[dict]:
    records = obs.get("records") or []
    return records[0] if len(records) == 1 and isinstance(records[0], dict) else None


def _gated(case: dict) -> list:
    return [e for e in case["labels"]["checker"].get("numeric_rules") or [] if e.get("rule_id_gated")]


# ── G1 Unsafe pass ──────────────────────────────────────────────────────────


def g1(case: dict, exp, obs: dict) -> list:
    out = []
    labels = case["labels"]
    expected_refusal = labels.get("expected_disposition") == "refused" or exp.disposition == "refused"
    if expected_refusal and obs["hook"]["exit"] != 2:
        out.append("unsafe_pass:expected_refusal_not_observed")
    traces = _numeric_traces(obs.get("direct_payload"))
    record = _record(obs) or {}
    # R1 G1(a) is about an actual refusal, not merely exit code 2.
    # A record with an observed non-refusing outcome is independently unsafe.
    if expected_refusal and record and record.get("hook_outcome") != "refused":
        out.append("unsafe_pass:expected_refusal_wrong_disposition")
    record_rules = {r.get("rule_id"): r for r in record.get("rules") or [] if isinstance(r, dict)}
    for entry in _gated(case):
        if entry.get("matcher_outcome") == "NO_VIOLATION":
            continue
        rid = entry["rule_id"]
        for source, item in (("checker", traces.get(rid)), ("record", record_rules.get(rid))):
            if item is not None and item.get("matcher_outcome") == "NO_VIOLATION":
                out.append(f"unsafe_pass:nonclean_observed_clean:{source}:{rid}")
    pinned = obs.get("pinned_g6") or {}
    for rid, value in sorted((pinned.get("per_rule") or {}).items()):
        if value is True and exp.per_rule_relevance.get(rid) is not True:
            out.append(f"unsafe_pass:unexpected_relevance:{rid}")
    if pinned.get("event") is True and exp.event_relevance is not True:
        out.append("unsafe_pass:unexpected_event_relevance")
    return out


# ── G2 False block ──────────────────────────────────────────────────────────


def g2(case: dict, exp, obs: dict) -> list:
    return ["false_block"] if obs["hook"]["exit"] == 2 else []


# ── G3 No mutation ──────────────────────────────────────────────────────────


def g3(case: dict, exp, obs: dict) -> list:
    out = []
    pre = obs["pre"]
    if obs.get("post_direct") != pre:
        out.append("target_changed_by_checker")
    if obs["post"] != pre:
        out.append("target_created" if pre == {"kind": "absent"} else "target_changed")
    expected = case["labels"].get("target_after_hook")
    if expected == "absent" and pre != {"kind": "absent"}:
        out.append("fixture_target_not_absent")
    if expected == "unchanged" and pre == {"kind": "absent"}:
        out.append("fixture_target_absent")
    return out


# ── G4 Reasons ──────────────────────────────────────────────────────────────


def g4(case: dict, exp, obs: dict, notes: list) -> list:
    out = []
    traces = _numeric_traces(obs.get("direct_payload"))
    record = _record(obs) or {}
    record_rules = {r.get("rule_id"): r for r in record.get("rules") or [] if isinstance(r, dict)}
    for entry in _gated(case):
        expected = entry.get("primary_reason")
        if expected is None:
            continue
        rid = entry["rule_id"]
        trace = traces.get(rid)
        if trace is None or trace.get("primary_reason") != expected:
            out.append(f"primary_reason:checker:{rid}")
        if exp.trusted_proposed:
            rule = record_rules.get(rid)
            if rule is None or rule.get("primary_reason") != expected:
                out.append(f"primary_reason:record:{rid}")
        if trace is not None:
            seen = sorted({u.get("reason") for u in trace.get("unknown_sources") or []
                           if isinstance(u, dict)})
            if seen != sorted(set(entry.get("unknown_reasons") or [])):
                # AMB-R2-05: set equality is compared and reported; G4 gates the primary only.
                notes.append(f"unknown_reason_set_differs:{rid}")
    return out


# ── G5 Parity ───────────────────────────────────────────────────────────────


def _reduce_traceback_frames(stderr: bytes) -> tuple[list, int]:
    """R1 A2.2: drop only the frame lines inside each traceback block."""
    kept, blocks, in_block = [], 0, False
    # Preserve the exact CR/LF bytes of everything outside traceback frames.
    # splitlines() without keepends would silently treat CRLF, LF and a
    # missing final newline as identical, contrary to R1 Amendment 2 §A2.2.
    for line in stderr.splitlines(keepends=True):
        if line.rstrip(b"\r\n") == _TRACEBACK:
            in_block, blocks = True, blocks + 1
            continue
        if in_block:
            if line[:1] in (b" ", b"\t"):
                continue
            in_block = False
        kept.append(line)
    return kept, blocks


def a2_in_scope(base: dict) -> bool:
    """R1 A2.1: decided by the baseline's observed run only."""
    return base["exit"] != 0 and _TRACEBACK in raw(base, "stderr")


def hook_parity(current: dict, base: dict) -> list:
    if a2_in_scope(base):
        cur_err, base_err = raw(current, "stderr"), raw(base, "stderr")
        if current["exit"] == 0 or _TRACEBACK not in cur_err:
            return ["hook_parity:a2_only_baseline_raised"]
        out = []
        if raw(current, "stdout") != raw(base, "stdout"):
            out.append("hook_parity:stdout")
        if current["exit"] != base["exit"]:
            out.append("hook_parity:exit")
        if _reduce_traceback_frames(cur_err) != _reduce_traceback_frames(base_err):
            out.append("hook_parity:a2_stderr")
        return out
    out = []
    for stream in ("stdout", "stderr"):
        if raw(current, stream) != raw(base, stream):
            out.append(f"hook_parity:{stream}")
    if current["exit"] != base["exit"]:
        out.append("hook_parity:exit")
    return out


def g5(case: dict, exp, obs: dict, notes: list) -> list:
    out = []
    if exp.g5.get("hook_level"):
        if "base_hook" not in obs:
            out.append("hook_parity:not_run")
        else:
            out.extend(hook_parity(obs["hook"], obs["base_hook"]))
            if a2_in_scope(obs["base_hook"]):
                notes.append("g5_amendment2_in_scope")
    if exp.g5.get("checker_level"):
        a, b = obs.get("parity_proposed"), obs.get("parity_input")
        if a is None or b is None:
            out.append("checker_parity:not_run")
        else:
            if raw(a, "stdout") != raw(b, "stdout"):
                out.append("checker_parity:stdout")
            if a["exit"] != b["exit"]:
                out.append("checker_parity:exit")
    return out


# ── G6 Evidence ─────────────────────────────────────────────────────────────

_RECORD_KEYS = {
    "schema", "surface", "mneme_version", "host", "event", "carrier_sha256",
    "checker", "rules", "violations", "hook_outcome", "disposition",
}


def _record_structure(record: dict) -> list:
    out = []
    missing = _RECORD_KEYS - set(record)
    if missing:
        out.append("record_incomplete:" + ",".join(sorted(missing)))
        return out
    if record["schema"] != C.EVIDENCE_SCHEMA or record["surface"] != C.EVIDENCE_SURFACE:
        out.append("record_schema")
    for key, fields in (("host", ("version", "executable_sha256")),
                        ("event", ("tool_name", "file_path", "cwd", "identifiers")),
                        ("checker", ("trusted", "subject", "evaluation_complete")),
                        ("disposition", ("mode", "cause"))):
        if not isinstance(record[key], dict) or any(f not in record[key] for f in fields):
            out.append(f"record_incomplete:{key}")
    if not isinstance(record["rules"], list):
        out.append("record_incomplete:rules")
    return out


def g6(case: dict, exp, obs: dict, host: tuple, envelope_ids: dict, cwd: str,
       expected_mneme_version: str, expected_versions: dict[str, str]) -> list:
    records = obs.get("records") or []
    if not exp.record_expected:
        return ["unexpected_record"] if records else []
    if len(records) != 1:
        return [f"record_count:{len(records)}"]
    record = records[0]
    if not isinstance(record, dict):
        return ["record_unparseable"]
    out = _record_structure(record)
    if out:
        return out
    digest = exp.content_sha256
    # Control provenance is pinned independently of the observed hook.
    # The executable host identity and installed Mneme version are separate.
    if not expected_mneme_version or record.get("mneme_version") != expected_mneme_version:
        out.append("mneme_version_mismatch")
    # Control, event, join by digest and path (charter §6.2; ADR-034 §7a).
    if (record["host"].get("version"), record["host"].get("executable_sha256")) != tuple(host):
        out.append("host_identity")
    event = record["event"]
    if event.get("tool_name") != "Write" or event.get("file_path") != exp.target:
        out.append("join_path:event")
    if event.get("cwd") != cwd or event.get("identifiers") != envelope_ids:
        out.append("event_fields")
    if record["carrier_sha256"] != digest:
        out.append("join_digest")
    checker = record["checker"]
    if checker.get("trusted") is not True:
        out.append("checker_untrusted")
    subject = checker.get("subject")
    if exp.record_subject is None:
        if subject is not None:
            out.append("record_subject_unexpected")  # R3 §3: an unexpected proposed_new_source fails G6
    else:
        if not isinstance(subject, dict) or subject.get("input_kind") != exp.record_subject:
            out.append("record_subject_kind")
        else:
            if subject.get("subject_sha256") != digest:
                out.append("join_digest:subject")
            target_path = subject.get("target_path")
            if not isinstance(target_path, str) or os.path.normcase(target_path) != os.path.normcase(
                    str(Path(exp.target).resolve())):
                out.append("join_path:subject")
            if subject.get("governed_path") != exp.governed_path:
                out.append("join_path:governed")
            if subject.get("absence_verified") is not True:
                out.append("absence_not_verified")
    # Checker payload subject kind, labelled independently (R3 §6.2).
    payload = obs.get("direct_payload")
    if payload is None:
        out.append("checker_payload_missing")
    else:
        kind = payload["subject"].get("input_kind") if isinstance(payload.get("subject"), dict) \
            else ("absent" if "subject" not in payload else "malformed")
        if kind != exp.checker_subject_kind:
            out.append(f"checker_subject_kind:{kind}")
    # Cause, mode and outcome (AMB-R2-08 mapping fixed in contract.py).
    if record["disposition"].get("mode") != exp.mode:
        out.append("disposition_mode")
    if record["disposition"].get("cause") != exp.cause:
        out.append(f"disposition_cause:{record['disposition'].get('cause')}")
    if record["hook_outcome"] != exp.disposition:
        out.append(f"hook_outcome:{record['hook_outcome']}")
    # Exact non-numeric and numeric violation identities (ADR-034 §7c; R3 §3).
    out.extend("attribution:" + f for f in
               attribution.identity_failures(record, exp.violations, digest))
    # Ordered steps (R2 §5 G6 1-4; R2V-F3 first).
    ids = [r.get("rule_id") if isinstance(r, dict) else None for r in record["rules"]]
    if len(set(ids)) != len(ids) or sorted(i for i in ids if isinstance(i, str)) != exp.applied_rule_ids \
            or any(not isinstance(i, str) or not i for i in ids):
        out.append("step1_rule_id_set")
        return out
    for rule in record["rules"]:
        rid = rule["rule_id"]
        want = exp.numeric_outcomes.get(rid, {})
        # ADR-034 §7a: bind every applied rule to the version in the
        # compiled canonical memory, never to a value copied from the record.
        expected_version = expected_versions.get(rid)
        if not expected_version or rule.get("decision_version_id") != expected_version:
            out.append(f"record_decision_version_id:{rid}")
        if rule.get("applicability") != "APPLIED" or rule.get("governed_path") != exp.governed_path \
                or rule.get("subject_sha256") != digest:
            out.append(f"record_rule_binding:{rid}")
        for key in ("matcher_status", "matcher_outcome", "primary_reason"):
            if rule.get(key) != want.get(key):
                out.append(f"record_rule_{key}:{rid}")
    pinned = obs.get("pinned_g6")
    if pinned is None:
        out.append("pinned_g6_not_computed")
        return out
    per_rule = pinned.get("per_rule") or {}
    if sorted(per_rule) != exp.applied_rule_ids:
        out.append("step2_per_rule_keys")
    elif per_rule != exp.per_rule_relevance:
        out.append("step2_per_rule_values")
    if pinned.get("event") is not exp.event_relevance:
        out.append("step3_event_relevance")
    if pinned.get("complete") is not exp.evaluation_complete:
        out.append(f"step4_evaluation_complete:{pinned.get('complete')}")
    return out


# ── one case ────────────────────────────────────────────────────────────────


def _bundle_digest(obs: dict) -> str:
    import hashlib

    return hashlib.sha256(json.dumps(obs, sort_keys=True).encode("utf-8")).hexdigest()


def score_case(case: dict, passes: list, compiled: dict, host: tuple, guard: list,
               expected_mneme_version: str, expected_versions: dict[str, str]) -> dict:
    """``passes`` is ``[(expectation, observation), ...]`` for the two full runs."""
    gates: dict = {g: {"applies": True, "failures": []} for g in C.GATES}
    notes: list = []
    exp0 = passes[0][0]
    errors = [obs.get("error") for _, obs in passes if obs.get("error")]
    if not compiled.get("ok"):
        errors.append("memory_compile_failed")
    errors.extend(guard)
    if exp0 is not None:
        errors.extend(f"oracle_conflict:{c}" for c in exp0.conflicts)
        notes.extend(exp0.notes)
    if errors or exp0 is None:
        gates["G8"]["failures"] = sorted(set(errors)) or ["case_not_scored"]
        for gate in C.GATES[:-1]:
            gates[gate] = {"applies": True, "failures": ["case_not_scored"]}
        return _finish(case, gates, notes)

    for gate in C.GATES:
        gates[gate]["applies"] = exp0.participation.get(gate, True)
    for label, (exp, obs) in zip(("A", "B"), passes):
        results = {
            "G1": g1(case, exp, obs),
            "G2": g2(case, exp, obs),
            "G3": g3(case, exp, obs),
            "G4": g4(case, exp, obs, notes),
            "G5": g5(case, exp, obs, notes),
            "G6": g6(case, exp, obs, host, _envelope_ids(case), exp.root,
                     expected_mneme_version, expected_versions),
        }
        for gate, failures in results.items():
            if gates[gate]["applies"]:
                gates[gate]["failures"].extend(f"{label}:{f}" for f in failures)
    if _bundle_digest(passes[0][1]) != _bundle_digest(passes[1][1]) or \
            json.dumps(passes[0][0].to_json(), sort_keys=True) != json.dumps(passes[1][0].to_json(), sort_keys=True):
        gates["G7"]["failures"].append("runs_differ")
    for gate in gates.values():
        gate["failures"] = sorted(set(gate["failures"]))
    return _finish(case, gates, sorted(set(notes)))


def _envelope_ids(case: dict) -> dict:
    from .runner import SESSION_ID

    out = {}
    for key, value in (case["event"].get("envelope_extras") or {}).items():
        if key.endswith("_id") and isinstance(value, str):
            out[key] = value.replace("{{SESSION_ID}}", SESSION_ID)
    return out


def _finish(case: dict, gates: dict, notes: list) -> dict:
    passed = all(not g["failures"] for g in gates.values() if g["applies"])
    return {
        "case_id": case["case_id"], "cls": case["cls"], "subclass": case.get("subclass"),
        "visibility": case.get("visibility"), "passed": passed,
        "gates": {k: {"applies": v["applies"],
                      "result": ("n/a" if not v["applies"] else "pass" if not v["failures"] else "fail"),
                      "failures": v["failures"]} for k, v in gates.items()},
        "notes": notes,
    }


# ── corpus ──────────────────────────────────────────────────────────────────


def floors(cases: list, passes: Optional[dict] = None) -> dict:
    concealed = [c for c in cases if c.get("visibility") != "public"]
    public = [c for c in cases if c.get("visibility") == "public"]
    counts = Counter(c["cls"] for c in concealed)
    at = Counter(c.get("subclass") for c in concealed if c["cls"] == "AT")
    short = {k: (counts.get(k, 0), v) for k, v in C.CLASS_FLOORS.items() if counts.get(k, 0) < v}
    at_short = {k: (at.get(k, 0), v) for k, v in C.AT_SUBCLASS_FLOORS.items() if at.get(k, 0) < v}
    total = len(concealed) + len(public)
    public_classes = [c["cls"] for c in public]
    public_ok = (not total or len(public) / total <= C.PUBLIC_SMOKE_MAX_FRACTION) and \
        len(set(public_classes)) == len(public_classes)
    coverage_result = (coverage.inspect(cases, passes) if passes is not None else
                       {"met": False, "shortfalls": ["coverage_not_checked"], "counts": {}})
    return {
        "concealed": len(concealed), "public": len(public),
        "concealed_by_class": dict(sorted(counts.items())),
        "at_by_subclass": dict(sorted((str(k), v) for k, v in at.items())),
        "class_floor_shortfalls": short, "at_floor_shortfalls": at_short,
        "total_floor_met": len(concealed) >= C.TOTAL_FLOOR,
        "public_smoke_rules_met": public_ok, "coverage": coverage_result,
        "met": (not short and not at_short and len(concealed) >= C.TOTAL_FLOOR
                and public_ok and coverage_result["met"]),
    }


def decide(results: list, floor: dict, symlinks: dict, scoring: str, integrity: dict) -> dict:
    """Corpus decision. Public smoke never yields a verdict (R3 §3)."""
    scored = [r for r in results if r["visibility"] != "public"] if scoring == "concealed" else results
    manifest = integrity.get("manifest")
    integrity_ok = (isinstance(manifest, dict) and manifest.get("entries", 0) > 0
                    and not manifest.get("mismatches"))
    if scoring == "concealed" and not integrity_ok:
        # Corpus-integrity failure is G8, even if every individual hook event
        # otherwise passed. Do not let an absent/partial manifest earn PASS.
        for result in scored:
            gate = result["gates"]["G8"]
            gate["applies"] = True  # No label can exempt a corpus-integrity failure.
            if "corpus_manifest_integrity" not in gate["failures"]:
                gate["failures"].append("corpus_manifest_integrity")
            gate["result"] = "fail"
            result["passed"] = False
    # Count gate failures only after corpus-integrity failures are attributed.
    per_gate = {}
    for gate in C.GATES:
        applicable = [r for r in scored if r["gates"][gate]["applies"]]
        per_gate[gate] = {
            "denominator": len(applicable),
            "failed": sorted(r["case_id"] for r in applicable if r["gates"][gate]["result"] == "fail"),
        }
    all_pass = all(r["passed"] for r in scored)
    if scoring != "concealed":
        verdict = "NO_VERDICT_PUBLIC_SMOKE"
    elif not symlinks.get("capable"):
        verdict = "INCOMPLETE"  # R1 G2V-F2: a validation FAIL, never a narrowed PASS
    elif (all_pass and floor["met"] and floor.get("coverage", {}).get("met") is True
          and integrity_ok and scored):
        verdict = "PASS"
    else:
        verdict = "FAIL"
    return {"verdict": verdict, "cases_scored": len(scored), "cases_passed": sum(r["passed"] for r in scored),
            "per_gate": per_gate, "integrity_ok": integrity_ok}

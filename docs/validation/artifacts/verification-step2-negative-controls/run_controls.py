"""Verification step 2: ADR-029 negative controls against v0.11.0.

Read-only harness. It drives the shipped producers (``mneme check``, the
Claude Code hook entry point, the Agent SDK and LangChain adapters) on
deterministic temporary fixtures and assesses each observation as an
evidence claim. It changes no runtime code.

Run from the repository root:

    python docs/validation/artifacts/verification-step2-negative-controls/run_controls.py

Writes ``results.json`` next to this file and exits 1 if any control misses
its expected evidence level OR any of its expected runtime observations
(action, applicability, matcher status, evaluation completeness, hook
outcome and disposition, identity and subject matches).

The hook runs in process with a synthetic pinned host identity. That is a
fixture, not a verified live-host enforcement observation, and no
attestation is claimed (ADR-034 section 7a, ADR-025).

Claim assessment (harness-side, from the accepted contracts):

- Hook record: relevant only if ``relevant_enforcement_per_rule`` is True for
  the claimed ``rule_id`` AND the record's ``(decision_id,
  decision_version_id, rule_id)`` equals the claim (#761 §5.1 ruling; the
  decision ID is the ``rule_id`` prefix) AND, when the claim names a subject
  digest, it equals the record's ``carrier_sha256``. The function's raw
  output is reported separately so consumer obligations stay visible.
- ``mneme check`` payload: no relevance assessor exists for this surface
  (#761 E-1/E-2), so at most execution observed.
- Agent SDK / LangChain: ``fail_open`` and ``skip`` evaluate nothing (not
  executed); a trusted gate result is at most execution observed (#769).
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from mneme import __version__  # noqa: E402
from mneme.cli import main as cli_main  # noqa: E402
from mneme.decision_governance import evidence_identity_of  # noqa: E402
from mneme.integrations.agent_sdk import MnemeAgentSdk  # noqa: E402
from mneme.integrations.claude_code import hook  # noqa: E402
from mneme.integrations.langchain import MnemeLangChain  # noqa: E402
from mneme.numeric_rule import NumericContract  # noqa: E402
from tests.canonical_fixtures import canonical_document  # noqa: E402

HOST = ("2.1.303", "ab" * 32)  # pinned host identity for the evidence seam
NOT_EXECUTED = "not_executed"
EXECUTION = "execution_observed"
RELEVANT = "relevant_enforcement_observed"
ORDER = {NOT_EXECUTED: 0, EXECUTION: 1, RELEVANT: 2}


def numeric_value(max_="5") -> str:
    return NumericContract(
        max=max_, unit="seconds", symbol="ROUTER_DEADLINE_S",
        call_function="classify", call_position=1,
    ).canonical_value()


ABOVE = "ROUTER_DEADLINE_S = 60\ndef run(x):\n    return classify(x, 2)\n"
WITHIN = "ROUTER_DEADLINE_S = 3\ndef run(x):\n    return classify(x, 2)\n"
DYNAMIC = "ROUTER_DEADLINE_S = compute()\ndef run(x):\n    return classify(x, 2)\n"


def legacy_memory(numeric_text="Router deadline at most 5 seconds", max_="5") -> dict:
    return {
        "meta": {"name": "verification-step2", "description": "negative controls"},
        "items": [],
        "decisions": [
            {"id": "LIT-1", "decision": "Do not use psycopg2", "rationale": "r",
             "scope": ["storage"],
             "rules": [{"type": "FORBID_LITERAL", "value": "psycopg2"}],
             "created_at": "2026-11-09", "updated_at": "2026-11-09",
             "status": "active"},
            {"id": "ADR-034T", "decision": numeric_text, "rationale": "r",
             "scope": ["router"],
             "rules": [{"type": "FORBID_NUMERIC_ABOVE", "value": numeric_value(max_),
                        "include_paths": ["src/**"]}],
             "created_at": "2026-11-09", "updated_at": "2026-11-09",
             "status": "active"},
        ],
    }


FIXTURES = {
    "v1_canonical": lambda: canonical_document(legacy_memory()),
    # Same rule, different decision text: new decision_version_id, same rule_id.
    "v2_canonical": lambda: canonical_document(
        legacy_memory(numeric_text="Router deadline at most 5 seconds (revised)")),
    # Different bound: different rule_id.
    "v3_canonical": lambda: canonical_document(legacy_memory(max_="10")),
    # No decision_index section: no canonical version identity. v0.11.0 loads
    # it only without numeric rules; with one, loading is refused.
    "sectionless_literal": lambda: {**legacy_memory(),
                                    "decisions": legacy_memory()["decisions"][:1]},
    "sectionless_numeric": lambda: legacy_memory(),
}


def make_project(root: Path, fixture: str) -> Path:
    (root / ".mneme").mkdir(parents=True)
    (root / ".mneme" / "project_memory.json").write_text(
        json.dumps(FIXTURES[fixture](), sort_keys=True), encoding="utf-8")
    (root / "src").mkdir()
    (root / "docs").mkdir()
    return root


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@contextlib.contextmanager
def env(**values):
    saved = {k: os.environ.get(k) for k in values}
    for k, v in values.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


BASE_ENV = {
    "MNEME_MEMORY": None, "CLAUDE_PLUGIN_OPTION_MODE": None,
    "MNEME_HOOK_CHECK_TRANSPORT": "inprocess", "MNEME_HOOK_MODE": "strict",
}


def run_cli(project: Path, flag: str, content: str, target_rel: str) -> dict:
    carrier = project.parent / f"{project.name}-carrier.txt"
    carrier.write_text(content, encoding="utf-8")
    argv = ["check", "--memory", str(project / ".mneme" / "project_memory.json"),
            flag, str(carrier), "--target-path", str(project / target_rel),
            "--query", f"edit to {target_rel}", "--mode", "strict", "--json"]
    out = io.StringIO()
    with env(**BASE_ENV), contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(io.StringIO()):
        code = cli_main(argv)
    return {"exit": code, "payload": json.loads(out.getvalue())}


def run_hook(project: Path, rel: str, content: str) -> dict:
    log = project.parent / f"{project.name}-evidence.jsonl"
    envelope = {
        "hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(project),
        "tool_input": {"file_path": str(project / rel), "content": content},
        "session_id": "sess-step2", "tool_use_id": "toolu_step2",
    }
    with env(**BASE_ENV, MNEME_HOOK_EVIDENCE_LOG=str(log),
             MNEME_HOOK_EVIDENCE_HOST_VERSION=HOST[0],
             MNEME_HOOK_EVIDENCE_HOST_SHA256=HOST[1]):
        rc = hook.handle_event(envelope, stderr=io.StringIO(), stdout=io.StringIO())
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return {"exit": rc, "records": [json.loads(line) for line in lines]}


# ── claim assessment ─────────────────────────────────────────────────────────

def numeric_trace(payload: dict) -> dict | None:
    hits = [a for a in payload.get("applicability", [])
            if a.get("rule_type") == "FORBID_NUMERIC_ABOVE"]
    return hits[0] if hits else None


def assess_hook(record: dict | None, claim: dict) -> dict:
    if record is None:
        return {"level": NOT_EXECUTED, "function_relevance": None,
                "identity_match": False, "subject_match": None,
                "note": "no evidence record written"}
    per_rule = hook.relevant_enforcement_per_rule(record, HOST)
    function_relevance = per_rule.get(claim["rule_id"], False)
    entry = next((r for r in record.get("rules") or []
                  if r.get("rule_id") == claim["rule_id"]), None)
    decision_from_rule = claim["rule_id"].split(":", 1)[0] if claim["rule_id"] else ""
    identity_match = bool(
        entry is not None
        and claim.get("decision_id")
        and decision_from_rule == claim["decision_id"]
        and claim.get("decision_version_id")
        and entry.get("decision_version_id") == claim["decision_version_id"]
    )
    subject_match = None
    if claim.get("subject_sha256") is not None:
        subject_match = record.get("carrier_sha256") == claim["subject_sha256"]
    relevant = function_relevance and identity_match and subject_match is not False
    executed = record.get("checker", {}).get("trusted") is True
    level = RELEVANT if relevant else (EXECUTION if executed else NOT_EXECUTED)
    return {"level": level, "function_relevance": function_relevance,
            "identity_match": identity_match, "subject_match": subject_match,
            "per_rule": per_rule}


def assess_cli(result: dict) -> dict:
    payload = result["payload"]
    trace = numeric_trace(payload)
    literal = [a for a in payload.get("applicability", [])
               if a.get("rule_type") == "FORBID_LITERAL"]
    ident = None
    if trace is not None:
        identity = evidence_identity_of(type("T", (), trace)())
        ident = {"complete": identity.complete, "missing": list(identity.missing),
                 "malformed": list(identity.malformed)}
    literal_ident = []
    for item in literal:
        identity = evidence_identity_of(type("T", (), item)())
        literal_ident.append({"rule_id": item.get("rule_id"),
                              "decision_version_id": item.get("decision_version_id"),
                              "complete": identity.complete,
                              "missing": list(identity.missing)})
    trusted = payload.get("schema") == "mneme.check/v1"
    return {
        "level": EXECUTION if trusted else NOT_EXECUTED,
        "note": "mneme check has no relevance assessor (#761 E-1/E-2)",
        "verdict": payload.get("verdict"),
        "evaluation_complete": payload.get("evaluation_complete"),
        "has_subject_record": "subject" in payload,
        "numeric_trace": None if trace is None else {
            k: trace.get(k) for k in ("decision_id", "rule_id", "decision_version_id",
                                      "outcome", "matcher_status", "matcher_outcome",
                                      "primary_reason")},
        "numeric_identity": ident,
        "literal_identity": literal_ident,
    }


def assess_adapter(result, trace_entry: dict) -> dict:
    executed = result.action in ("allow", "deny", "warn") and result.payload is not None
    identity_keys = sorted(k for k in trace_entry
                           if k in ("rule_id", "decision_version_id", "applicability",
                                    "subject_sha256", "mneme_version", "via"))
    return {"level": EXECUTION if executed else NOT_EXECUTED,
            "action": result.action, "verdict": result.verdict,
            "payload_present": result.payload is not None,
            "trace_keys": sorted(trace_entry),
            "trace_identity_keys": identity_keys}


# ── controls ─────────────────────────────────────────────────────────────────

def rel_record(record: dict, project: Path) -> dict:
    """Strip temporary absolute paths so results are reproducible."""
    out = copy.deepcopy(record)
    base = str(project)
    def scrub(value):
        if isinstance(value, str):
            return value.replace(base, "<project>").replace("\\", "/")
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        return value
    return scrub(out)


def hook_obs(hk: dict, rec: dict | None, a: dict) -> dict:
    """Runtime observations of one hook event, independent of the level."""
    numeric = [r for r in (rec or {}).get("rules") or []]
    first = numeric[0] if numeric else {}
    return {
        "hook_exit": hk["exit"] if hk else None,
        "record_written": rec is not None,
        "checker_trusted": (rec or {}).get("checker", {}).get("trusted"),
        "evaluation_complete": (rec or {}).get("checker", {}).get("evaluation_complete"),
        "hook_outcome": (rec or {}).get("hook_outcome"),
        "disposition_cause": ((rec or {}).get("disposition") or {}).get("cause"),
        "numeric_rule_entries": len(numeric),
        "applicability": first.get("applicability"),
        "matcher_status": first.get("matcher_status"),
        "matcher_outcome": first.get("matcher_outcome"),
        "primary_reason": first.get("primary_reason"),
        "violation_rule_ids": [v.get("rule_id") for v in (rec or {}).get("violations") or []],
        "function_relevance": a["function_relevance"],
        "identity_match": a["identity_match"],
        "subject_match": a["subject_match"],
    }


def cli_obs(cli: dict, a: dict) -> dict:
    trace = a["numeric_trace"] or {}
    return {
        "exit": cli["exit"],
        "verdict": a["verdict"],
        "evaluation_complete": a["evaluation_complete"],
        "numeric_applicability": trace.get("outcome"),
        "matcher_status": trace.get("matcher_status"),
        "primary_reason": trace.get("primary_reason"),
        "numeric_identity_complete": (a["numeric_identity"] or {}).get("complete"),
        "literal_identity_complete": [x["complete"] for x in a["literal_identity"]],
        "literal_identity_missing": [x["missing"] for x in a["literal_identity"]],
    }


def adapter_obs(a: dict) -> dict:
    return {"action": a["action"], "verdict": a["verdict"],
            "payload_present": a["payload_present"],
            "trace_identity_keys": a["trace_identity_keys"]}


def main() -> int:
    results: dict = {"mneme_version": __version__, "host_pin": list(HOST), "controls": []}
    work = Path(tempfile.mkdtemp(prefix="mneme-step2-"))

    def project(name: str, fixture: str) -> Path:
        return make_project(work / name, fixture)

    def add(cid, title, expected_max, assessment, evidence, expect, observed,
            negative=True):
        """PASS needs BOTH the expected evidence level AND every expected
        runtime observation, so a behavior change cannot hide behind a
        correct-looking level."""
        level_ok = (ORDER[assessment["level"]] <= ORDER[expected_max]) if negative \
            else assessment["level"] == expected_max
        checks = {k: {"expected": v, "actual": observed.get(k), "ok": observed.get(k) == v}
                  for k, v in expect.items()}
        obs_ok = all(c["ok"] for c in checks.values())
        results["controls"].append({
            "id": cid, "title": title, "negative": negative,
            "expected_level": ("at most " if negative else "") + expected_max,
            "actual_level": assessment["level"], "level_ok": level_ok,
            "observations": checks, "observations_ok": obs_ok,
            "pass": level_ok and obs_ok,
            "assessment": assessment, "evidence": evidence,
        })

    # Genuine identities from each fixture, via the real checker.
    ids = {}
    for fx in ("v1_canonical", "v2_canonical", "v3_canonical"):
        p = project(f"ids-{fx}", fx)
        trace = numeric_trace(run_cli(p, "--proposed-new-file", WITHIN, "src/new.py")["payload"])
        ids[fx] = {k: trace.get(k) for k in ("decision_id", "decision_version_id", "rule_id")}
    results["fixture_identities"] = ids
    v1 = ids["v1_canonical"]
    nid = v1["rule_id"]
    claim_v1 = {**v1, "subject_sha256": sha(ABOVE)}
    assert ids["v2_canonical"]["rule_id"] == nid
    assert ids["v2_canonical"]["decision_version_id"] != v1["decision_version_id"]
    assert ids["v3_canonical"]["rule_id"] != nid

    # P1: positive baseline. The refusal is asserted on its own, apart from
    # the relevance calculation.
    p = project("p1", "v1_canonical")
    hk = run_hook(p, "src/new.py", ABOVE)
    rec = hk["records"][0]
    a = assess_hook(rec, claim_v1)
    add("P1", "Baseline: hook refuses a numeric violation; matching claim", RELEVANT, a,
        {"record": rel_record(rec, p)},
        {"hook_exit": 2, "record_written": True, "checker_trusted": True,
         "evaluation_complete": True, "hook_outcome": "refused",
         "disposition_cause": "numeric_violation", "numeric_rule_entries": 1,
         "applicability": "APPLIED", "matcher_status": "RECOGNIZED",
         "matcher_outcome": "VIOLATION", "violation_rule_ids": [nid],
         "function_relevance": True, "identity_match": True, "subject_match": True},
        hook_obs(hk, rec, a), negative=False)
    genuine = rec

    def against_genuine(cid, title, claim, record, expect, note):
        a = assess_hook(record, claim)
        add(cid, title, EXECUTION, a, {"record": note, "claim": claim}, expect,
            hook_obs(None, record, a))

    # C1 missing canonical decision identity.
    p = project("c1a", "sectionless_literal")
    cli = run_cli(p, "--input", "import psycopg2\n", "docs/a.md")
    a = assess_cli(cli)
    add("C1a", "Section-less memory, literal violation via mneme check", EXECUTION, a,
        {}, {"exit": 2, "verdict": "FAIL", "literal_identity_complete": [False],
             "literal_identity_missing": [["decision_version_id"]]}, cli_obs(cli, a))
    p = project("c1b", "sectionless_numeric")
    try:
        cli = run_cli(p, "--proposed-new-file", ABOVE, "src/new.py")
        c1b_cli = {"exception": None, "exit": cli["exit"]}
    except Exception as exc:  # the loader refuses: nothing is evaluated
        c1b_cli = {"exception": type(exc).__name__, "message": str(exc)[:160]}
    hk = run_hook(p, "src/new.py", ABOVE)
    rec = hk["records"][0] if hk["records"] else None
    a = assess_hook(rec, {"decision_id": "ADR-034T", "decision_version_id": "",
                          "rule_id": nid, "subject_sha256": sha(ABOVE)})
    obs = {**hook_obs(hk, rec, a), "cli_exception": c1b_cli["exception"]}
    add("C1b", "Section-less memory with a numeric rule (CLI and hook)", EXECUTION, a,
        {"cli": c1b_cli, "record": rel_record(rec, p) if rec else None},
        {"cli_exception": "DecisionIndexMigrationRequired", "hook_exit": 0,
         "record_written": True, "checker_trusted": False, "hook_outcome": "proceeded",
         "disposition_cause": "fail_open", "numeric_rule_entries": 0,
         "function_relevance": False}, obs)
    against_genuine("C1c", "Genuine record; claim omits decision_version_id",
                    {**claim_v1, "decision_version_id": ""}, genuine,
                    {"function_relevance": True, "identity_match": False,
                     "subject_match": True}, "P1")

    # C2 mismatched decision version or rule identity.
    against_genuine("C2a", "Genuine V1 record; claim names V2 (same rule_id, new version)",
                    {**ids["v2_canonical"], "subject_sha256": sha(ABOVE)}, genuine,
                    {"function_relevance": True, "identity_match": False,
                     "subject_match": True}, "P1")
    against_genuine("C2b", "Genuine V1 record; claim names V3 rule (bound changed)",
                    {**ids["v3_canonical"], "subject_sha256": sha(ABOVE)}, genuine,
                    {"function_relevance": False, "identity_match": False,
                     "subject_match": True}, "P1")
    tampered = copy.deepcopy(genuine)
    tampered["rules"][0]["decision_version_id"] = ids["v2_canonical"]["decision_version_id"]
    against_genuine("C2c", "Record version rewritten to V2; claim names V1", claim_v1,
                    tampered, {"function_relevance": True, "identity_match": False,
                               "subject_match": True},
                    "P1 with rules[0].decision_version_id := V2")

    # C3 excluded rule applicability.
    p = project("c3a", "v1_canonical")
    cli = run_cli(p, "--proposed-new-file", ABOVE, "docs/new.py")
    a = assess_cli(cli)
    add("C3a", "Numeric rule EXCLUDED (target outside src/**) via mneme check",
        EXECUTION, a, {},
        {"exit": 0, "verdict": "PASS", "evaluation_complete": True,
         "numeric_applicability": "EXCLUDED", "matcher_status": None,
         "numeric_identity_complete": True}, cli_obs(cli, a))
    p = project("c3b", "v1_canonical")
    hk = run_hook(p, "docs/new.py", ABOVE)
    rec = hk["records"][0] if hk["records"] else None
    a = assess_hook(rec, claim_v1)
    add("C3b", "Numeric rule EXCLUDED via the hook; claim names the numeric rule",
        EXECUTION, a, {"record": rel_record(rec, p) if rec else None},
        {"hook_exit": 0, "record_written": True, "checker_trusted": True,
         "hook_outcome": "proceeded", "disposition_cause": "no_violation",
         "numeric_rule_entries": 0, "violation_rule_ids": [],
         "function_relevance": False}, hook_obs(hk, rec, a))

    # C4 incomplete evaluation.
    p = project("c4a", "v1_canonical")
    cli = run_cli(p, "--input", ABOVE, "src/new.py")
    a = assess_cli(cli)
    add("C4a", "Unverified input; numeric rule APPLIED but unevaluated (mneme check)",
        EXECUTION, a, {},
        {"verdict": "PASS", "evaluation_complete": False,
         "numeric_applicability": "APPLIED", "matcher_status": "MATCHER_UNEVALUATED",
         "primary_reason": "INCOMPLETE_SOURCE_INPUT",
         "numeric_identity_complete": True}, cli_obs(cli, a))
    p = project("c4b", "v1_canonical")
    hk = run_hook(p, "src/new.py", DYNAMIC)
    rec = hk["records"][0] if hk["records"] else None
    a = assess_hook(rec, {**v1, "subject_sha256": sha(DYNAMIC)})
    add("C4b", "Hook new-file Write with a dynamic value the matcher cannot decide",
        EXECUTION, a, {"record": rel_record(rec, p) if rec else None},
        {"hook_exit": 0, "checker_trusted": True, "evaluation_complete": False,
         "hook_outcome": "proceeded", "disposition_cause": "fail_open",
         "numeric_rule_entries": 1, "applicability": "APPLIED",
         "matcher_status": "MATCHER_UNEVALUATED", "matcher_outcome": "UNEVALUATED",
         "primary_reason": "UNRECOGNIZED_FORM", "violation_rule_ids": [],
         "function_relevance": False, "identity_match": True, "subject_match": True},
        hook_obs(hk, rec, a))

    # C5 stale subject digest on the numeric hook path.
    against_genuine("C5a", "Genuine record for content A; claim about later content B",
                    {**v1, "subject_sha256": sha(WITHIN)}, genuine,
                    {"function_relevance": True, "identity_match": True,
                     "subject_match": False}, "P1")
    stale = copy.deepcopy(genuine)
    stale["checker"]["subject"]["subject_sha256"] = sha(WITHIN)
    stale["rules"][0]["subject_sha256"] = sha(WITHIN)
    against_genuine("C5b", "Record subject/rule digests point at B; carrier digest is A",
                    {**v1, "subject_sha256": sha(WITHIN)}, stale,
                    {"function_relevance": False, "identity_match": True,
                     "subject_match": False},
                    "P1 with subject and rule digests := sha256(WITHIN)")

    # C6 Agent SDK / LangChain fail-open and skip (#769).
    p = project("c6", "v1_canonical")
    sdk = MnemeAgentSdk(project_dir=str(p), mode="strict")
    lc = MnemeLangChain(project_dir=str(p), mode="strict")

    def adapter(cid, title, call, trace, level, expect):
        with env(**BASE_ENV):
            r = call()
        a = assess_adapter(r, trace[-1])
        add(cid, title, level, a, {"reason_prefix": r.reason[:60]}, expect, adapter_obs(a))

    adapter("C6a", "Agent SDK Edit of a missing file (fail_open)",
            lambda: sdk.evaluate_mutation("Edit", {"file_path": "src/missing.py",
                                                   "old_string": "a",
                                                   "new_string": "psycopg2"}, cwd=str(p)),
            sdk.trace, NOT_EXECUTED,
            {"action": "fail_open", "verdict": None, "payload_present": False,
             "trace_identity_keys": []})
    adapter("C6b", "Agent SDK non-mutating tool (skip)",
            lambda: sdk.evaluate_mutation("Read", {"file_path": "src/x.py"}, cwd=str(p)),
            sdk.trace, NOT_EXECUTED,
            {"action": "skip", "verdict": None, "payload_present": False,
             "trace_identity_keys": []})
    adapter("C6c", "LangChain unmapped tool (skip)",
            lambda: lc.evaluate_tool_call("shell", {"cmd": "echo"}, cwd=str(p)),
            lc.trace, NOT_EXECUTED,
            {"action": "skip", "verdict": None, "payload_present": False,
             "trace_identity_keys": ["via"]})
    adapter("C6d", "LangChain edit_file of a missing file (fail_open)",
            lambda: lc.evaluate_tool_call("edit_file", {"file_path": "src/missing.py",
                                                         "old_string": "a",
                                                         "new_string": "b"}, cwd=str(p)),
            lc.trace, NOT_EXECUTED,
            {"action": "fail_open", "verdict": None, "payload_present": False,
             "trace_identity_keys": []})
    (p / "docs" / "a.md").write_text("hello\n", encoding="utf-8")
    adapter("C6e", "Agent SDK trusted deny: trace-only claim",
            lambda: sdk.evaluate_mutation("Edit", {"file_path": "docs/a.md",
                                                   "old_string": "hello",
                                                   "new_string": "hello\nimport psycopg2"},
                                          cwd=str(p)),
            sdk.trace, EXECUTION,
            {"action": "deny", "verdict": "FAIL", "payload_present": True,
             "trace_identity_keys": []})

    results["summary"] = {
        "controls": len(results["controls"]),
        "passed": sum(c["pass"] for c in results["controls"]),
        "observation_checks": sum(len(c["observations"]) for c in results["controls"]),
        "observation_checks_ok": sum(v["ok"] for c in results["controls"]
                                     for v in c["observations"].values()),
        "failed": [c["id"] for c in results["controls"] if not c["pass"]],
    }
    out = Path(__file__).with_name("results.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(results, indent=2, sort_keys=True) + "\n")
    for c in results["controls"]:
        bad = [k for k, v in c["observations"].items() if not v["ok"]]
        print(f"{c['id']:4} {'PASS' if c['pass'] else 'FAIL'}  {c['actual_level']:31}"
              f" obs={len(c['observations']) - len(bad)}/{len(c['observations'])}"
              f"{' MISMATCH ' + str(bad) if bad else ''}  {c['title']}")
    print(json.dumps(results["summary"]))
    return 0 if not results["summary"]["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Verification step 2: ADR-029 negative controls against v0.11.0.

Read-only harness. It drives the shipped producers (``mneme check``, the
Claude Code hook entry point, the Agent SDK and LangChain adapters) on
deterministic temporary fixtures and assesses each observation as an
evidence claim. It changes no runtime code.

Run from the repository root:

    python docs/validation/artifacts/verification-step2-negative-controls/run_controls.py

Writes ``results.json`` next to this file and exits 1 if any negative
control reaches "relevant enforcement observed" or any positive baseline
fails to.

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


def main() -> int:
    results: dict = {"mneme_version": __version__, "host_pin": list(HOST), "controls": []}
    work = Path(tempfile.mkdtemp(prefix="mneme-step2-"))

    def project(name: str, fixture: str) -> Path:
        return make_project(work / name, fixture)

    def add(cid, title, expected_max, assessment, evidence, negative=True):
        passed = (ORDER[assessment["level"]] <= ORDER[expected_max]) if negative \
            else assessment["level"] == expected_max
        results["controls"].append({
            "id": cid, "title": title, "negative": negative,
            "expected_level": ("at most " if negative else "") + expected_max,
            "actual_level": assessment["level"], "pass": passed,
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

    # P1: positive baseline. Genuine hook refusal, claim matches.
    p = project("p1", "v1_canonical")
    hk = run_hook(p, "src/new.py", ABOVE)
    rec = hk["records"][0]
    add("P1", "Baseline: hook refuses a numeric violation; matching claim",
        RELEVANT, assess_hook(rec, {**v1, "subject_sha256": sha(ABOVE)}),
        {"hook_exit": hk["exit"], "record": rel_record(rec, p)}, negative=False)
    genuine, genuine_project = rec, p

    # C1 missing canonical decision identity.
    p = project("c1a", "sectionless_literal")
    cli = run_cli(p, "--input", "import psycopg2\n", "docs/a.md")
    add("C1a", "Section-less memory, literal violation via mneme check",
        EXECUTION, assess_cli(cli), {"exit": cli["exit"]})
    p = project("c1b", "sectionless_numeric")
    try:
        cli = run_cli(p, "--proposed-new-file", ABOVE, "src/new.py")
        c1b_cli = {"exit": cli["exit"], "payload_verdict": cli["payload"].get("verdict")}
    except Exception as exc:  # the loader refuses: nothing is evaluated
        c1b_cli = {"exception": type(exc).__name__, "message": str(exc)[:160]}
    hk = run_hook(p, "src/new.py", ABOVE)
    rec = hk["records"][0] if hk["records"] else None
    claim = {"decision_id": "ADR-034T", "decision_version_id": "",
             "rule_id": v1["rule_id"], "subject_sha256": sha(ABOVE)}
    add("C1b", "Section-less memory with a numeric rule (CLI and hook)", EXECUTION,
        assess_hook(rec, claim),
        {"cli": c1b_cli, "hook_exit": hk["exit"],
         "record": rel_record(rec, p) if rec else None})
    add("C1c", "Genuine record; claim omits decision_version_id", EXECUTION,
        assess_hook(genuine, {**v1, "decision_version_id": "", "subject_sha256": sha(ABOVE)}),
        {"record": "P1"})

    # C2 mismatched decision version or rule identity.
    add("C2a", "Genuine V1 record; claim names V2 (same rule_id, new version)",
        EXECUTION, assess_hook(genuine, {**ids["v2_canonical"], "subject_sha256": sha(ABOVE)}),
        {"record": "P1", "claimed": ids["v2_canonical"]})
    add("C2b", "Genuine V1 record; claim names V3 rule (bound changed)", EXECUTION,
        assess_hook(genuine, {**ids["v3_canonical"], "subject_sha256": sha(ABOVE)}),
        {"record": "P1", "claimed": ids["v3_canonical"]})
    tampered = copy.deepcopy(genuine)
    tampered["rules"][0]["decision_version_id"] = ids["v2_canonical"]["decision_version_id"]
    add("C2c", "Record version rewritten to V2; claim names V1", EXECUTION,
        assess_hook(tampered, {**v1, "subject_sha256": sha(ABOVE)}),
        {"record": "P1 with rules[0].decision_version_id := V2"})

    # C3 excluded rule applicability.
    p = project("c3a", "v1_canonical")
    cli = run_cli(p, "--proposed-new-file", ABOVE, "docs/new.py")
    add("C3a", "Numeric rule EXCLUDED (target outside src/**) via mneme check",
        EXECUTION, assess_cli(cli), {"exit": cli["exit"]})
    p = project("c3b", "v1_canonical")
    hk = run_hook(p, "docs/new.py", ABOVE)
    rec = hk["records"][0] if hk["records"] else None
    add("C3b", "Numeric rule EXCLUDED via the hook; claim names the numeric rule",
        EXECUTION, assess_hook(rec, {**v1, "subject_sha256": sha(ABOVE)}),
        {"hook_exit": hk["exit"], "record": rel_record(rec, p) if rec else None})

    # C4 incomplete evaluation.
    p = project("c4a", "v1_canonical")
    cli = run_cli(p, "--input", ABOVE, "src/new.py")
    add("C4a", "Unverified input; numeric rule APPLIED but unevaluated (mneme check)",
        EXECUTION, assess_cli(cli), {"exit": cli["exit"]})
    p = project("c4b", "v1_canonical")
    hk = run_hook(p, "src/new.py", DYNAMIC)
    rec = hk["records"][0] if hk["records"] else None
    add("C4b", "Hook new-file Write with a dynamic value the matcher cannot decide",
        EXECUTION, assess_hook(rec, {**v1, "subject_sha256": sha(DYNAMIC)}),
        {"hook_exit": hk["exit"], "record": rel_record(rec, p) if rec else None})

    # C5 stale subject digest on the numeric hook path.
    add("C5a", "Genuine record for content A; claim about later content B", EXECUTION,
        assess_hook(genuine, {**v1, "subject_sha256": sha(WITHIN)}),
        {"record": "P1", "claimed_subject": "sha256(WITHIN)"})
    stale = copy.deepcopy(genuine)
    stale["checker"]["subject"]["subject_sha256"] = sha(WITHIN)
    stale["rules"][0]["subject_sha256"] = sha(WITHIN)
    add("C5b", "Record subject/rule digests point at B; carrier digest is A", EXECUTION,
        assess_hook(stale, {**v1, "subject_sha256": sha(WITHIN)}),
        {"record": "P1 with subject and rule digests := sha256(WITHIN)"})

    # C6 Agent SDK / LangChain fail-open and skip (#769).
    p = project("c6", "v1_canonical")
    sdk = MnemeAgentSdk(project_dir=str(p), mode="strict")
    with env(**BASE_ENV):
        r = sdk.evaluate_mutation("Edit", {"file_path": "src/missing.py",
                                           "old_string": "a", "new_string": "psycopg2"},
                                  cwd=str(p))
    add("C6a", "Agent SDK Edit of a missing file (fail_open)", NOT_EXECUTED,
        assess_adapter(r, sdk.trace[-1]), {"reason_prefix": r.reason[:60]})
    with env(**BASE_ENV):
        r = sdk.evaluate_mutation("Read", {"file_path": "src/x.py"}, cwd=str(p))
    add("C6b", "Agent SDK non-mutating tool (skip)", NOT_EXECUTED,
        assess_adapter(r, sdk.trace[-1]), {})
    lc = MnemeLangChain(project_dir=str(p), mode="strict")
    with env(**BASE_ENV):
        r = lc.evaluate_tool_call("shell", {"cmd": "echo"}, cwd=str(p))
    add("C6c", "LangChain unmapped tool (skip)", NOT_EXECUTED,
        assess_adapter(r, lc.trace[-1]), {})
    with env(**BASE_ENV):
        r = lc.evaluate_tool_call("edit_file", {"file_path": "src/missing.py",
                                                 "old_string": "a", "new_string": "b"},
                                  cwd=str(p))
    add("C6d", "LangChain edit_file of a missing file (fail_open)", NOT_EXECUTED,
        assess_adapter(r, lc.trace[-1]), {})
    (p / "docs" / "a.md").write_text("hello\n", encoding="utf-8")
    with env(**BASE_ENV):
        r = sdk.evaluate_mutation("Edit", {"file_path": "docs/a.md", "old_string": "hello",
                                           "new_string": "hello\nimport psycopg2"},
                                  cwd=str(p))
    add("C6e", "Agent SDK trusted deny: trace-only claim", EXECUTION,
        assess_adapter(r, sdk.trace[-1]), {})

    results["summary"] = {
        "controls": len(results["controls"]),
        "passed": sum(c["pass"] for c in results["controls"]),
        "failed": [c["id"] for c in results["controls"] if not c["pass"]],
    }
    out = Path(__file__).with_name("results.json")
    out.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for c in results["controls"]:
        a = c["assessment"]
        print(f"{c['id']:4} {'PASS' if c['pass'] else 'FAIL'}  {c['actual_level']:31}"
              f" fn={a.get('function_relevance')} id={a.get('identity_match')}"
              f" subj={a.get('subject_match')}  {c['title']}")
    print(json.dumps(results["summary"]))
    return 0 if not results["summary"]["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

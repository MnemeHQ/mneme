"""CLI scenarios A-F: shipped `mneme check` and `mneme audit` per fresh baseline.

A static CLI verdict is not evidence of pre-mutation blocking; that is
established separately by run_langgraph_checks.py.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import oracle  # noqa: E402
from sandbox_lib import (  # noqa: E402
    build_baseline,
    check,
    label_from_check,
    load_cases,
    mneme,
    router_source,
    sha256_bytes,
    sha256_file,
)

SUFFIX = {".py": ".py", ".md": ".md"}


def end_state_router(case, root: Path) -> str:
    """The router a successful write would leave behind."""
    return case.content if case.target_path == "src/router.py" else router_source(root)


def classify(oracle_accept: bool, label: str, failures: list, outcomes: list) -> str:
    if label not in ("BLOCKED", "ALLOWED"):
        return "UNCLASSIFIED"
    if oracle_accept and label == "ALLOWED":
        return "SCOPE_EXCLUDED" if outcomes == ["EXCLUDED"] else "TRUE_NEGATIVE"
    if not oracle_accept and label == "BLOCKED":
        return "TRUE_POSITIVE"
    if oracle_accept and label == "BLOCKED":
        return "FALSE_BLOCK"
    if "C3_NO_FALLBACK" in failures and "C2_DEADLINE_EXCEEDS_5S" not in failures:
        return "MODELLING_GAP"
    return "COVERAGE_GAP"


def run_cli_case(case, workdir: Path, out_dir=None) -> dict:
    workdir = Path(workdir)
    baseline = build_baseline(workdir / "fixture")
    root = baseline.root
    target = root / case.target_path
    candidate = workdir / ("candidate" + SUFFIX.get(Path(case.target_path).suffix, ".txt"))
    data = case.content.encode("utf-8")
    candidate.write_bytes(data)

    before = sha256_file(target)
    proc, payload = check(root, candidate, case.target_path)
    after = sha256_file(target)

    label = label_from_check(payload, proc.returncode)
    applicability = (payload or {}).get("applicability") or []
    outcomes = [a.get("outcome") for a in applicability]
    verdict_oracle = oracle.evaluate(end_state_router(case, root))
    rule_ids = sorted(
        {v.get("rule_id") for v in (payload or {}).get("violations") or [] if isinstance(v, dict) and v.get("rule_id")}
    )

    row = {
        "case": case.id,
        "surface": "cli",
        "sub_constraint": case.sub_constraint,
        "oracle": case.oracle,
        "oracle_accept": verdict_oracle.accept,
        "oracle_failures": verdict_oracle.failures,
        "verdict": (payload or {}).get("verdict"),
        "evaluation_complete": (payload or {}).get("evaluation_complete"),
        "mode": (payload or {}).get("mode"),
        "label": label,
        "rule_ids": rule_ids,
        "applicability_outcomes": outcomes,
        "freshness_codes": [f.get("code") for f in (payload or {}).get("freshness") or []],
        "exit_code": proc.returncode,
        "input_sha256": sha256_bytes(data),
        "target_sha256_before": before,
        "target_sha256_after": after,
        "write_handler_calls": 0,
        "classification_observed": classify(verdict_oracle.accept, label, verdict_oracle.failures, outcomes),
        "classification_expected": case.classification,
        "baseline_sha256": baseline.baseline_sha256,
        "rule_id": baseline.rule_id,
    }
    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"cli_{case.id}.stdout.json").write_text(proc.stdout, encoding="utf-8")
        (out_dir / f"cli_{case.id}.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    return row


def run_audit(workdir: Path, out_dir=None) -> dict:
    baseline = build_baseline(Path(workdir) / "fixture")
    report = Path(workdir) / "audit.json"
    proc = mneme(
        ["audit", "--memory", ".mneme/project_memory.json", "--repo-root", ".", "--json", str(report)],
        cwd=baseline.root,
    )
    data = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else None
    if out_dir is not None and data is not None:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "audit.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    tiers = [d.get("protection_tier") for d in (data or {}).get("decisions", [])]
    return {
        "exit_code": proc.returncode,
        "audit_tier_only": (data or {}).get("summary"),
        "protection_tiers": tiers,
    }


def run_all(out_dir=None) -> dict:
    rows = []
    for case in load_cases():
        with tempfile.TemporaryDirectory(prefix=f"ods-cli-{case.id}-") as tmp:
            rows.append(run_cli_case(case, Path(tmp), out_dir))
    with tempfile.TemporaryDirectory(prefix="ods-audit-") as tmp:
        audit = run_audit(Path(tmp), out_dir)
    return {"rows": rows, "audit": audit}


if __name__ == "__main__":
    print(json.dumps(run_all(), indent=2))

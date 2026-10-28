"""``python -m benchmarks.adr034_g2_1_r3 score ...`` (see README.md).

Two equivalent full passes over the corpus (G7), one report. The report is
metadata only: opaque case ids, classes, gate results and failure codes,
never case content. Raw observations go to ``--observations`` only when
requested, and stay with whoever controls the corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from . import HARNESS_VERSION, contract as C, gates, public_smoke, runner


def harness_files() -> dict:
    here = Path(__file__).resolve().parent
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(here.iterdir()) if p.suffix in (".py", ".md")
    }


def score(args: argparse.Namespace) -> int:
    if not re.fullmatch(r"[0-9a-f]{64}", args.host_sha256):
        raise SystemExit("--host-sha256 must be a lowercase SHA-256")
    host = (args.host_version, args.host_sha256)
    # Public and concealed archives are separate by frozen #703. The
    # published digest is a pre-unblind public-data pin, not a new criterion.
    public_evidence = None
    if args.scoring == "concealed":
        public_evidence = (public_smoke.verify(Path(args.public_smoke_tar))
                           if args.public_smoke_tar else
                           {"verified": False, "reason": "public_smoke_tar_not_supplied",
                            "public_cases": 0, "classes": []})
    work = runner.check_work_dir(Path(args.work))
    cases, integrity = runner.load_corpus(Path(args.corpus))
    if args.scoring == "public" and any(c.get("visibility") != "public" for c in cases):
        raise SystemExit("public scoring refuses non-public cases")
    ctx = runner.Context(work, Path(args.impl_python), Path(args.base_python), host)
    symlinks = runner.symlink_capability(work)
    environments = {
        "implementation": runner.child(ctx.impl_python, "env"),
        "baseline": runner.child(ctx.base_python, "env"),
    }

    compiled, guards, passes = {}, {}, {c["case_id"]: [] for c in cases}
    # The expected package version comes from the frozen R3 §2 contract,
    # NEVER the package under test. Its installed version is an independent
    # observation and an operational provenance precondition for every case.
    installed_version = environments["implementation"].get("mneme_version")
    version_pin_matches = installed_version == C.PINNED_MNEME_VERSION
    if not version_pin_matches:
        for case in cases:
            guards.setdefault(case["case_id"], []).append(
                "implementation_mneme_version_mismatch")
    for case in cases:
        try:
            compiled[case["case_id"]] = runner.compile_memory(case, ctx)
        except Exception as exc:  # G8: a compile-step failure fails that case only
            compiled[case["case_id"]] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    for _ in range(2):
        for case in cases:
            cid = case["case_id"]
            exp, obs = runner.observe_safely(case, ctx, compiled[cid])
            passes[cid].append((exp, obs))
            if exp is not None and cid not in guards:
                try:
                    guards[cid] = runner.memory_guard(compiled[cid].get("memory_b64"), exp.rule_ids)
                except Exception as exc:
                    # Broken compiled-memory provenance fails this case only.
                    # Never include raw exception text in a metadata report.
                    guards[cid] = [f"memory_guard_exception:{type(exc).__name__}"]
    results = []
    for case in cases:
        cid = case["case_id"]
        try:
            versions = runner.compiled_rule_versions(compiled[cid].get("memory_b64"))
        except Exception as exc:
            # A bad compiled binding is a case-level G8 failure, never a
            # scoring-process crash or an implicit version wildcard.
            guards.setdefault(cid, []).append(f"compiled_version_binding:{type(exc).__name__}")
            versions = {}
        results.append(gates.score_case_safely(
            case, passes[cid], compiled[cid], host, guards.get(cid, []),
            C.PINNED_MNEME_VERSION, versions,
        ))
    floor = gates.floors(cases, passes, public_evidence)
    decision = gates.decide(results, floor, symlinks, args.scoring, integrity)
    report = {
        "harness": {"version": HARNESS_VERSION, "files_sha256": harness_files()},
        "scoring": args.scoring,
        "pinned_host": {"version": host[0], "executable_sha256": host[1]},
        "environments": environments,
        "implementation_version_pin": {
            "expected": C.PINNED_MNEME_VERSION,
            "matched": version_pin_matches,
        },
        "symlink_capability": symlinks,
        "corpus_integrity": integrity,
        "public_smoke_integrity": public_evidence,
        "floors": floor if args.scoring == "concealed" else None,
        "decision": decision,
        "cases": results,
    }
    Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.observations:
        dump = {
            cid: [{"expectation": e.to_json() if e else None, "observation": o} for e, o in runs]
            for cid, runs in passes.items()
        }
        Path(args.observations).write_text(json.dumps(dump, sort_keys=True), encoding="utf-8")
    print(f"{decision['verdict']}: {decision['cases_passed']}/{decision['cases_scored']} cases passed")
    return 0


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m benchmarks.adr034_g2_1_r3")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("score", help="score a corpus directory (two full passes)")
    p.add_argument("--corpus", required=True, help="directory holding <case>/case.json files")
    p.add_argument("--work", required=True, help="empty scratch directory (fixed fixture paths)")
    p.add_argument("--impl-python", required=True, help="interpreter of the pinned D3 build")
    p.add_argument("--base-python", required=True, help="interpreter of the pinned pre-G2 baseline")
    p.add_argument("--host-version", required=True, help="pinned Claude Code version")
    p.add_argument("--host-sha256", required=True, help="pinned Claude Code executable SHA-256")
    p.add_argument("--scoring", choices=("public", "concealed"), required=True)
    p.add_argument("--public-smoke-tar", default=None,
                   help="separate frozen #703 public tar, SHA-256 and manifest verified for concealed scoring")
    p.add_argument("--report", required=True, help="metadata-only JSON report path")
    p.add_argument("--observations", default=None, help="optional raw observation dump")
    p.set_defaults(func=score)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

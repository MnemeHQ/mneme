"""Run the P0-A offline detector experiment (M0 to M4) and score it.

    python validation/semantic-constraint-p0a/scripts/run_detectors.py --out <empty dir>
    python validation/semantic-constraint-p0a/scripts/run_detectors.py --compare <dir1> <dir2> --out <file>

A run first verifies the frozen fixture-and-oracle freeze (``run_freeze``)
and stops before evaluating anything if a digest is off. It then asks every
method its questions about every frozen subject and scores each verdict
against the frozen architectural labels (charter section 6):

- M1 to M3 (``detectors/``) only parse source. They answer the whole-file
  ``audit`` question for every subject and the ADR-018 ``gate`` question for
  the two edit cases T and U, whose before and after snapshots are frozen.
- M0 is the shipped ``mneme check --mode strict --json`` path, invoked as in
  #570: a fresh fixture per subject built by the #570 ``sandbox_lib``, with
  the fixture root as cwd. It answers the ``audit`` question only, because
  ``mneme check --input`` is a whole-file audit (ADR-018 section 2).
- M4 is oracle v2, run on the frozen fixtures through its digest allow-list,
  exactly as ``run_freeze`` runs it. It answers the ``post_mutation``
  question. It executes the fixture, so it is never a pre-execution method.

The output directory receives ``summary.json`` and ``summary.csv``, which
contain nothing machine-, path- or time-dependent, and ``run_record.json``
with the environment. ``--compare`` checks two runs' summaries byte for byte.

Validation only: nothing here is imported by ``mneme/``, the hook, the CLI,
CI or a benchmark suite, and no verdict is shipped enforcement.
"""

import argparse
import csv
import difflib
import hashlib
import io
import json
import platform
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

P0A_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = P0A_DIR.parents[1]
SANDBOX_DIR = REPO_ROOT / "validation" / "orchestrator-decision-sandbox"
sys.path.insert(0, str(P0A_DIR))
sys.path.insert(0, str(P0A_DIR / "scripts"))
sys.path.insert(0, str(SANDBOX_DIR / "scripts"))

import run_freeze  # noqa: E402 - frozen; provides verify() and the oracle import path
import oracle_v2  # noqa: E402 - frozen oracle, imported via run_freeze's path
from detectors import common  # noqa: E402
from detectors import m1_lexical, m2_static_bound, m3_fallback  # noqa: E402
from detectors.common import NO_VIOLATION, SUB_CONSTRAINTS, UNEVALUATED, VIOLATION, Finding  # noqa: E402

SCHEMA = "p0a-detector-experiment-summary/v1"
RUNNER_VERSION = "p0a-detector-runner/1.0.0"
FREEZE_COMMIT = "f5c910bc0cad7a5cd9bf99ba3c831cdc5ba016bd"
TEMPLATE_TARGET = "src/router.py"
STATIC_METHODS = (m1_lexical, m2_static_bound, m3_fallback)

M0_ID, M0_VERSION = "M0", "shipped-mneme-check-strict-json (FORBID_LITERAL, #570 path)"
M4_ID, M4_VERSION = "M4", oracle_v2.ORACLE_VERSION

# Which sub-constraints each method assesses. Verdicts outside this map are
# emitted (every combination gets a verdict) but not scored.
TARGETS = {
    "M0": ("C1", "C2", "C3"),  # shipped decision-level verdict; only C1 has a rule
    "M1": ("C1",),
    "M2": ("C1", "C2"),
    "M3": ("C3",),
    "M4": ("C1", "C2", "C3"),
}
OUTCOMES = {
    ("violation", VIOLATION): "caught",
    ("violation", NO_VIOLATION): "missed",
    ("violation", UNEVALUATED): "unevaluated_violation",
    ("benign", VIOLATION): "false_block",
    ("benign", NO_VIOLATION): "correct_allow",
    ("benign", UNEVALUATED): "unevaluated_benign",
}
BUCKETS = ("caught", "missed", "unevaluated_violation", "false_block", "correct_allow", "unevaluated_benign")
QUESTIONS = ("audit", "gate", "post_mutation")


class RunError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(data) -> bytes:
    return (json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


# ── Subjects ────────────────────────────────────────────────────────────────


def introduced_line_numbers(before: str, after: str) -> tuple:
    """(1-based introduced line numbers, introduced lines, removed lines).

    Same definition as ADR-018 section 3 and ``run_freeze.edit_delta``:
    ``difflib.SequenceMatcher(autojunk=False)`` insert and replace opcodes.
    Blank introduced lines are not counted (ADR-018 section 5).
    """
    a, b = before.splitlines(), after.splitlines()
    numbers, introduced, removed = [], [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend(a[i1:i2])
        if tag in ("replace", "insert"):
            introduced.extend(b[j1:j2])
            numbers.extend(j + 1 for j in range(j1, j2) if b[j].strip())
    return tuple(numbers), introduced, removed


def load_subjects() -> list:
    """Frozen subjects in a fixed order: Set 0 A-F, then Set 1 in registry order."""
    manifest = load_json(run_freeze.MANIFEST)
    labels0 = {c["id"]: c["labels"] for c in load_json(run_freeze.SET0_LABELS)["cases"]}
    subjects = []
    for case in run_freeze.set0_cases():
        subjects.append({
            "set": "Set 0", "case": case["id"], "kind": "file",
            "target_path": case["target_path"], "after": case["content"],
            "labels": {sc: labels0[case["id"]][sc]["label"] for sc in SUB_CONSTRAINTS},
            "probes": [load_json(run_freeze.SET1_CASES)["default_probe"]],
        })
    set1 = load_json(run_freeze.SET1_CASES)
    pinned_edits = {c["id"]: c.get("edit_delta") for c in manifest["set1_cases"]}
    for case in set1["cases"]:
        subject = {
            "set": "Set 1", "case": case["id"], "kind": case["kind"],
            "target_path": TEMPLATE_TARGET,
            "after": run_freeze.read(case["files"]["after"]).decode("utf-8"),
            "labels": {sc: case["labels"][sc]["label"] for sc in SUB_CONSTRAINTS},
            "probes": case.get("probes", [set1["default_probe"]]),
        }
        if case["kind"] == "edit":
            subject["before"] = run_freeze.read(case["files"]["before"]).decode("utf-8")
            numbers, introduced, removed = introduced_line_numbers(subject["before"], subject["after"])
            if {"introduced_lines": introduced, "removed_lines": removed} != pinned_edits[case["id"]]:
                raise RunError(f"edit delta for {case['id']} differs from MANIFEST.json")
            subject["introduced_line_numbers"] = numbers
        subjects.append(subject)
    return subjects


def content_sha(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def exclusion_for(subject: dict, method: str, sc: str, question: str):
    """Why a verdict is reported but not scored, or None if it is scored."""
    if subject["case"] == "F":
        return "F_OUT_OF_SCOPE: documentation-only path-excluded case (AMB-7); not in any in-scope denominator"
    if sc not in TARGETS[method]:
        return f"NOT_TARGETED: {method} does not assess {sc}"
    if subject["case"] == "T" and question != "gate":
        return "DUPLICATE_OF_C: T's resulting file is byte-identical to Set 0 C (AMB-9); counted once, as C"
    return None


# ── Methods ─────────────────────────────────────────────────────────────────


def run_static(subject: dict) -> list:
    """M1 to M3 on the audit question, and on the gate question for edits."""
    rows = []
    for module in STATIC_METHODS:
        audit = module.detect(subject["after"], subject["target_path"])
        rows.append((module.METHOD_ID, module.METHOD_VERSION, "audit", None, audit))
        if subject["kind"] == "edit":
            introduced = set(subject["introduced_line_numbers"])
            gate = {sc: common.gate_finding(audit[sc], introduced) for sc in SUB_CONSTRAINTS}
            rows.append((module.METHOD_ID, module.METHOD_VERSION, "gate", None, gate))
    return rows


def run_m0(subject: dict) -> tuple:
    """Shipped `mneme check --mode strict --json`, invoked as in #570."""
    import sandbox_lib  # noqa: PLC0415 - #570 helpers, used read-only

    suffix = Path(subject["target_path"]).suffix or ".txt"
    with tempfile.TemporaryDirectory(prefix=f"p0a-m0-{subject['case']}-") as tmp:
        tmp = Path(tmp)
        baseline = sandbox_lib.build_baseline(tmp / "fixture")
        candidate = tmp / ("candidate" + suffix)
        candidate.write_bytes(subject["after"].encode("utf-8"))
        proc, payload = sandbox_lib.check(baseline.root, candidate, subject["target_path"])
        label = sandbox_lib.label_from_check(payload, proc.returncode)
    violations = [v for v in (payload or {}).get("violations") or [] if isinstance(v, dict)]
    rule_types = sorted({v.get("rule_type") for v in violations if v.get("rule_type")})
    outcomes = [a.get("outcome") for a in (payload or {}).get("applicability") or []]
    raw = {
        "label": label,
        "verdict": (payload or {}).get("verdict"),
        "exit_code": proc.returncode,
        "evaluation_complete": (payload or {}).get("evaluation_complete"),
        "applicability_outcomes": outcomes,
        "violation_rule_types": rule_types,
        "rule_id": baseline.rule_id,
        "baseline_sha256": baseline.baseline_sha256,
    }
    if label in ("BLOCKED", "ALLOWED"):
        literal_hit = label == "BLOCKED" and rule_types == ["FORBID_LITERAL"]
        if label == "BLOCKED" and not literal_hit:
            findings = {sc: Finding(UNEVALUATED, f"UNEXPECTED_RULE_TYPES: {rule_types}") for sc in SUB_CONSTRAINTS}
        else:
            scope = "applicability EXCLUDED" if outcomes == ["EXCLUDED"] else "applicability " + "/".join(outcomes)
            c1 = (
                Finding(VIOLATION, f"FORBID_LITERAL FAIL ({scope})")
                if literal_hit else Finding(NO_VIOLATION, f"FORBID_LITERAL PASS ({scope})")
            )
            no_rule = Finding(NO_VIOLATION, f"NO_RULE_FOR_SUBCONSTRAINT: decision-level verdict {raw['verdict']} reported with evaluation_complete true")
            findings = {"C1": c1, "C2": no_rule, "C3": no_rule}
    else:
        findings = {sc: Finding(UNEVALUATED, f"CHECK_LABEL_{label}") for sc in SUB_CONSTRAINTS}
    return findings, raw


def run_m0_audit() -> dict:
    """`mneme audit` on the #570 baseline: audit truthfulness (charter 3.9)."""
    import run_cli_checks  # noqa: PLC0415 - #570 runner, used read-only

    with tempfile.TemporaryDirectory(prefix="p0a-m0-audit-") as tmp:
        result = run_cli_checks.run_audit(Path(tmp))
    return {
        "exit_code": result["exit_code"],
        "summary": result["audit_tier_only"],
        "protection_tiers": result["protection_tiers"],
        "measured_constraint_coverage_note": "Audit classification, not behavioral coverage; compare with the per-constraint tables.",
    }


def m0_matches_570(m0_raw: dict) -> dict:
    """M0 labels on A-F against the committed #570 post-fix CLI labels."""
    committed = load_json(SANDBOX_DIR / "evidence" / "post-fix" / "summary.json")["cli_cases"]
    pairs = {row["case"]: (row["label"], m0_raw[row["case"]]["label"]) for row in committed}
    return {"all_match": all(a == b for a, b in pairs.values()), "pairs": {k: list(v) for k, v in sorted(pairs.items())}}


def m4_digests() -> set:
    """The frozen allow-list, built the way run_freeze builds it.

    oracle_v2.observe trusts this caller-supplied set: SHA validation is a
    property of this trusted offline workflow, not an independent boundary of
    the oracle API (owner review of #582).
    """
    return run_freeze.frozen_digests()


def run_m4(subject: dict, digests: set) -> list:
    """(probe id, findings, observation) per probe; first probe is scored."""
    out = []
    for probe in subject["probes"]:
        if not subject["target_path"].endswith(".py"):
            reason = "ORACLE_NOT_APPLICABLE: non-Python target"
            out.append((probe["id"], {sc: Finding(UNEVALUATED, reason) for sc in SUB_CONSTRAINTS}, {"load": "NOT_APPLICABLE: non-Python target"}))
            continue
        obs = oracle_v2.observe(subject["after"].encode("utf-8"), frozen_digests=digests, env=probe["env"])
        if obs.get("load") != "OK":
            findings = {sc: Finding(UNEVALUATED, f"ORACLE_{obs.get('load')}") for sc in SUB_CONSTRAINTS}
        else:
            findings = {
                sc: Finding(VIOLATION if obs["violation_observed"][sc] else NO_VIOLATION,
                            f"ORACLE findings={obs['findings']} supplied={obs['deadline_supplied_to_classify']}")
                for sc in SUB_CONSTRAINTS
            }
        out.append((probe["id"], findings, obs))
    return out


def frozen_observation(subject: dict, probe_id: str):
    for run in load_json(run_freeze.OBSERVATIONS)["runs"]:
        snapshot = "content" if subject["set"] == "Set 0" else "after"
        if (run["set"], run["case"], run["snapshot"], run["probe"]) == (subject["set"], subject["case"], snapshot, probe_id):
            return run["observation"]
    return None


# ── Scoring ─────────────────────────────────────────────────────────────────


def method_digests() -> dict:
    out = {}
    for module in STATIC_METHODS:
        path = Path(module.__file__)
        out[module.METHOD_ID] = {
            "version": module.METHOD_VERSION,
            "path": path.relative_to(P0A_DIR).as_posix(),
            "sha256": sha256_bytes(path.read_bytes()),
        }
    common_path = Path(common.__file__)
    out["common"] = {"path": common_path.relative_to(P0A_DIR).as_posix(), "sha256": sha256_bytes(common_path.read_bytes())}
    out[M0_ID] = {"version": M0_VERSION}
    out[M4_ID] = {"version": M4_VERSION, "path": run_freeze.ORACLE_FILE, "sha256": sha256_bytes(run_freeze.read(run_freeze.ORACLE_FILE))}
    return out


def verdict_row(subject, method, version, question, probe, sc, finding, anchors, rule_id=None) -> dict:
    label = subject["labels"][sc]
    exclusion = exclusion_for(subject, method, sc, question)
    row = {
        "set": subject["set"],
        "case": subject["case"],
        "question": question,
        "method": method,
        "probe": probe,
        "sub_constraint": sc,
        "verdict": finding.verdict,
        "reason": finding.reason,
        "evidence_lines": list(finding.lines),
        "label": label,
        "outcome": OUTCOMES[(label, finding.verdict)],
        "scored": exclusion is None,
        "exclusion": exclusion,
        "binding": {
            "decision_id": common.DECISION_ID,
            "method_id": method,
            "method_version": version,
            "question": question,
            "sub_constraint": sc,
            "target_path": subject["target_path"],
            "applicability": "IN_SCOPE" if common.in_scope(subject["target_path"]) else "OUT_OF_SCOPE",
            "case_content_sha256": content_sha(subject["after"]),
            "case_before_sha256": content_sha(subject["before"]) if question == "gate" else None,
            "freeze_commit": anchors["freeze_commit"],
            "manifest_sha256": anchors["manifest_sha256"],
            "oracle_version": anchors["oracle_version"],
            "rule_id": rule_id,
        },
    }
    return row


def section7_status(counts: dict) -> str:
    """Charter section 7 criteria 1 and 2 on one (question, method, sub-constraint).

    Criteria 4 to 6 (determinism, no execution, binding, named scope) are
    properties of the run as a whole and are reported separately. Meeting
    criteria 1 and 2 never removes the ``UNEVALUATED`` count.
    """
    if counts["missed"] or counts["false_block"]:
        return "partial"
    if counts["n_violation"] == 0:
        return "not assessable: no violation instance in the denominator"
    if counts["caught"] == 0:
        return "not demonstrated: no violation instance was evaluated"
    return "demonstrated within declared scope"


def aggregate(rows: list) -> dict:
    """{question: {method: {sc: counts and case lists}}} over scored rows."""
    table = {}
    for row in rows:
        if not row["scored"]:
            continue
        cell = (
            table.setdefault(row["question"], {})
            .setdefault(row["method"], {})
            .setdefault(row["sub_constraint"], {b: [] for b in BUCKETS})
        )
        cell[row["outcome"]].append(row["case"])
    for methods in table.values():
        for scs in methods.values():
            for sc, cell in scs.items():
                n_violation = len(cell["caught"]) + len(cell["missed"]) + len(cell["unevaluated_violation"])
                n_benign = len(cell["false_block"]) + len(cell["correct_allow"]) + len(cell["unevaluated_benign"])
                counts = {b: len(cell[b]) for b in BUCKETS}
                counts.update(n_violation=n_violation, n_benign=n_benign)
                scs[sc] = {
                    "counts": counts,
                    "cases": {b: cell[b] for b in BUCKETS},
                    "catch_rate": f"{counts['caught']}/{n_violation}" if n_violation else "n/a",
                    "section7": section7_status(counts),
                }
    return table


def disagreements(rows: list) -> list:
    """Label vs oracle (M4) per case and probe, scored or not."""
    out = []
    for row in rows:
        if row["method"] != M4_ID or row["verdict"] == UNEVALUATED:
            continue
        if (row["label"] == "violation") != (row["verdict"] == VIOLATION):
            out.append({k: row[k] for k in ("case", "probe", "sub_constraint", "label", "verdict", "scored")})
    return out


def lookup(rows, method, case, question, sc, probe=None):
    for row in rows:
        if (row["method"], row["case"], row["question"], row["sub_constraint"]) == (method, case, question, sc) and (
            probe is None or row["probe"] == probe
        ):
            return row["verdict"]
    return None


def hypothesis_checks(rows: list) -> dict:
    """Charter section 8 predictions, checked one assertion at a time."""

    def expect(method, case, question, sc, verdict, note=""):
        observed = lookup(rows, method, case, question, sc)
        return {"method": method, "case": case, "question": question, "sub_constraint": sc,
                "expected": verdict, "observed": observed, "holds": observed == verdict, "note": note}

    ha = {
        "HA1": [
            expect("M1", "E", "audit", "C1", NO_VIOLATION, "E false block removed"),
            expect("M1", "R", "audit", "C1", NO_VIOLATION, "R false block removed"),
            expect("M1", "B", "audit", "C1", VIOLATION, "B not missed"),
            expect("M1", "G", "audit", "C1", NO_VIOLATION, "non-literal C1 not caught"),
            expect("M1", "H", "audit", "C1", NO_VIOLATION, "non-literal C1 not caught"),
            expect("M1", "S", "audit", "C1", NO_VIOLATION, "literal only inside a string: M1 misses"),
            expect("M0", "S", "audit", "C1", VIOLATION, "M0 exact match catches the literal in a string"),
        ],
        "HA2": [
            *(expect("M2", c, "audit", "C2", VIOLATION) for c in ("C", "I", "K", "M-5.0001")),
            expect("M2", "T", "gate", "C2", VIOLATION, "T asked at the introduced-delta gate (its audit duplicates C)"),
            expect("M2", "L", "audit", "C2", NO_VIOLATION, "no false block"),
            expect("M2", "M-5", "audit", "C2", NO_VIOLATION, "no false block at the boundary"),
            expect("M2", "J", "audit", "C2", UNEVALUATED),
        ],
        "HA3": [
            expect("M3", "D", "audit", "C3", VIOLATION),
            expect("M3", "N", "audit", "C3", VIOLATION),
            expect("M3", "A", "audit", "C3", NO_VIOLATION, "static structure only"),
            expect("M3", "P", "audit", "C3", NO_VIOLATION, "static structure only"),
            expect("M3", "O", "audit", "C3", UNEVALUATED, "not a false block"),
            expect("M3", "U", "audit", "C3", VIOLATION, "whole-file audit"),
            {**expect("M3", "U", "gate", "C3", UNEVALUATED, "never reported as stopped at the gate"),
             "holds": lookup(rows, "M3", "U", "gate", "C3") != VIOLATION},
        ],
    }
    out = {}
    for name, checks in ha.items():
        checks = list(checks)
        out[name] = {"all_hold": all(c["holds"] for c in checks), "checks": checks}
    # HA4: every violation no static method catches on the audit question,
    # with each static method's verdict, is the residual.
    residual = []
    labels = {}
    for row in rows:
        if row["question"] == "audit" and row["method"] in ("M1", "M2", "M3") and row["case"] not in ("F", "T"):
            labels[(row["case"], row["sub_constraint"])] = row["label"]
    for (case, sc), label in sorted(labels.items()):
        if label != "violation":
            continue
        verdicts = {m: lookup(rows, m, case, "audit", sc) for m in ("M1", "M2", "M3") if sc in TARGETS[m]}
        if VIOLATION not in verdicts.values():
            residual.append({"case": case, "sub_constraint": sc, "static_verdicts": verdicts})
    gate_residual = [
        {"case": r["case"], "sub_constraint": r["sub_constraint"], "method": r["method"], "verdict": r["verdict"]}
        for r in rows
        if r["question"] == "gate" and r["label"] == "violation" and r["scored"] and r["verdict"] != VIOLATION
    ]
    out["HA4"] = {
        "audit_residual": residual,
        "gate_residual": gate_residual,
        "note": "Audit violations that no in-scope static verdict (M1 to M3) catches, and gate violations not caught at the gate. Non-empty means the hypothesis that a residual remains without widening recognized forms is supported.",
    }
    return out


# ── Run ─────────────────────────────────────────────────────────────────────


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False).stdout.strip()


def run(methods: tuple) -> tuple:
    problems = run_freeze.verify()
    if problems:
        raise RunError("freeze verification failed: " + "; ".join(problems))
    if subprocess.run(["git", "merge-base", "--is-ancestor", FREEZE_COMMIT, "HEAD"], cwd=REPO_ROOT, check=False).returncode != 0:
        raise RunError(f"HEAD does not contain the freeze commit {FREEZE_COMMIT}")
    manifest_bytes = run_freeze.MANIFEST.read_bytes()
    manifest = json.loads(manifest_bytes)
    anchors = {
        "freeze_commit": FREEZE_COMMIT,
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "oracle_version": manifest["oracle"]["version"],
        "oracle_sha256": manifest["oracle"]["sha256"],
        "sandbox_pr570": run_freeze.ANCHOR_570,
    }

    subjects = load_subjects()
    digests = m4_digests() if "M4" in methods else None
    rows, m0_raw, m4_consistency = [], {}, []
    for subject in subjects:
        if any(m in methods for m in ("M1", "M2", "M3")):
            for method, version, question, probe, findings in run_static(subject):
                if method in methods:
                    for sc in SUB_CONSTRAINTS:
                        rows.append(verdict_row(subject, method, version, question, probe, sc, findings[sc], anchors))
        if "M0" in methods:
            findings, raw = run_m0(subject)
            m0_raw[subject["case"]] = raw
            for sc in SUB_CONSTRAINTS:
                rows.append(verdict_row(subject, M0_ID, M0_VERSION, "audit", None, sc, findings[sc], anchors, raw["rule_id"]))
        if "M4" in methods:
            for index, (probe_id, findings, obs) in enumerate(run_m4(subject, digests)):
                frozen = frozen_observation(subject, probe_id)
                m4_consistency.append({"case": subject["case"], "probe": probe_id, "matches_frozen_observation": frozen == obs})
                for sc in SUB_CONSTRAINTS:
                    row = verdict_row(subject, M4_ID, M4_VERSION, "post_mutation", probe_id, sc, findings[sc], anchors)
                    if index > 0:
                        row["scored"] = False
                        row["exclusion"] = row["exclusion"] or "SUPPLEMENTAL_PROBE: scored row uses the default probe env_unset"
                    rows.append(row)

    rows.sort(key=lambda r: (QUESTIONS.index(r["question"]), r["method"], subjects_order(subjects, r["case"]), r["probe"] or "", r["sub_constraint"]))
    summary = {
        "schema": SCHEMA,
        "track": "P0-A semantic constraint validation: offline detector experiment",
        "status": "validation only; bounded offline detection capability, never shipped enforcement",
        "charter": "docs/plans/2026-10-21-p0a-semantic-constraint-validation-charter.md",
        "runner": {"version": RUNNER_VERSION, "path": "scripts/run_detectors.py", "sha256": sha256_bytes(Path(__file__).read_bytes())},
        "anchors": anchors,
        "methods": {k: v for k, v in method_digests().items() if k in methods or k == "common"},
        "methods_run": list(methods),
        "targets": {m: list(TARGETS[m]) for m in methods},
        "scoring_rules": {
            "labels": "frozen architectural labels (set0/labels.json, set1/cases.json); oracle observations are never labels",
            "questions": "audit = whole resulting file (M0 to M3); gate = ADR-018 introduced lines, T and U only (M1 to M3); post_mutation = oracle v2 on the frozen fixture (M4)",
            "excluded_from_denominators": [
                "F: documentation-only, path-excluded (AMB-7)",
                "T on audit and post_mutation: byte-identical to C (AMB-9); counted once as C",
                "sub-constraints a method does not target",
                "M4 supplemental probes (S env_enabled); the scored M4 row is the default probe",
            ],
            "label_convention": "AMB-1: a disabled deadline is a C1 violation; C2 benign means not separately assessed, not compliant",
            "u_at_gate": "U introduces no lines; no method may report it stopped at the ADR-018 gate (AMB-2, D5)",
        },
        "edit_cases": {
            s["case"]: {"introduced_line_numbers": list(s["introduced_line_numbers"]),
                        "before_sha256": content_sha(s["before"]), "after_sha256": content_sha(s["after"])}
            for s in subjects if s["kind"] == "edit"
        },
        "tables": aggregate(rows),
        "label_vs_oracle_disagreements": disagreements(rows) if "M4" in methods else None,
        "m4_matches_frozen_observations": all(c["matches_frozen_observation"] for c in m4_consistency) if m4_consistency else None,
        "m0_raw": m0_raw or None,
        "m0_matches_570_cli_labels": m0_matches_570(m0_raw) if m0_raw else None,
        "hypotheses": hypothesis_checks(rows) if set(methods) >= {"M0", "M1", "M2", "M3"} else None,
        "verdicts": rows,
    }
    if "M0" in methods:
        summary["m0_audit"] = run_m0_audit()
    return summary, rows


def subjects_order(subjects, case_id) -> int:
    return [s["case"] for s in subjects].index(case_id)


def to_csv(rows: list) -> bytes:
    columns = ["question", "method", "set", "case", "probe", "sub_constraint", "verdict", "label", "outcome",
               "scored", "exclusion", "reason", "evidence_lines", "case_content_sha256"]
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns)
    for r in rows:
        writer.writerow([r["question"], r["method"], r["set"], r["case"], r["probe"] or "", r["sub_constraint"],
                         r["verdict"], r["label"], r["outcome"], r["scored"], r["exclusion"] or "", r["reason"],
                         " ".join(map(str, r["evidence_lines"])), r["binding"]["case_content_sha256"]])
    return buf.getvalue().encode("utf-8")


def mneme_identity() -> dict:
    import sandbox_lib  # noqa: PLC0415

    proc = subprocess.run(
        [sys.executable, "-c", "import mneme, json; print(json.dumps([getattr(mneme, '__version__', None), mneme.__file__]))"],
        capture_output=True, text=True, env=sandbox_lib.child_env(), cwd=tempfile.gettempdir(), check=False,
    )
    try:
        version, path = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return {"error": proc.stderr.strip()}
    return {"version": version, "module_path": path, "from_this_checkout": str(REPO_ROOT.resolve()) in str(Path(path).resolve())}


def run_record(methods: tuple, summary_bytes: bytes, csv_bytes: bytes) -> dict:
    packages = {}
    for name in ("mneme-hq", "pytest"):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "schema": "p0a-detector-run-record/v1",
        "utc_finished": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_head": git("rev-parse", "HEAD"),
        "git_tree_clean": git("status", "--porcelain", "--", "validation/semantic-constraint-p0a", "validation/orchestrator-decision-sandbox", "mneme") == "",
        "methods_run": list(methods),
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "os": platform.platform(),
        "installed_package_metadata": packages,
        "installed_metadata_note": "Distribution metadata only; it can be stale for an editable install. mneme_runtime_for_m0 records the module M0 actually loaded.",
        "mneme_runtime_for_m0": mneme_identity() if "M0" in methods else None,
        "summary_json_sha256": sha256_bytes(summary_bytes),
        "summary_csv_sha256": sha256_bytes(csv_bytes),
    }


def compare(dirs: list) -> dict:
    files = ("summary.json", "summary.csv")
    digests = {d.name: {f: sha256_bytes((d / f).read_bytes()) for f in files} for d in dirs}
    identical = all((dirs[0] / f).read_bytes() == (d / f).read_bytes() for d in dirs[1:] for f in files)
    return {
        "schema": "p0a-detector-reproducibility/v1",
        "runs": digests,
        "byte_identical": identical,
        "records": {d.name: load_json(d / "run_record.json") for d in dirs},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--methods", default="M0,M1,M2,M3,M4")
    parser.add_argument("--compare", type=Path, nargs="+")
    args = parser.parse_args(argv)

    if args.compare:
        result = compare(args.compare)
        args.out.write_bytes(dump(result))
        print(f"[p0a-detectors] byte_identical={result['byte_identical']}")
        return 0 if result["byte_identical"] else 1

    methods = tuple(m.strip() for m in args.methods.split(",") if m.strip())
    unknown = set(methods) - set(TARGETS)
    if unknown:
        parser.error(f"unknown methods: {sorted(unknown)}")
    if args.out.exists() and any(args.out.iterdir()):
        parser.error(f"output directory is not empty: {args.out}")
    args.out.mkdir(parents=True, exist_ok=True)
    try:
        summary, rows = run(methods)
    except RunError as e:
        print(f"[p0a-detectors] STOP {e}")
        return 3
    summary_bytes, csv_bytes = dump(summary), to_csv(rows)
    (args.out / "summary.json").write_bytes(summary_bytes)
    (args.out / "summary.csv").write_bytes(csv_bytes)
    (args.out / "run_record.json").write_bytes(dump(run_record(methods, summary_bytes, csv_bytes)))
    print(f"[p0a-detectors] wrote {args.out} ({len(rows)} verdicts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

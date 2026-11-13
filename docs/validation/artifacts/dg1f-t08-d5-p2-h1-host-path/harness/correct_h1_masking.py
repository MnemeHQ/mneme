"""Append-only correction of the #553 R1-R3 reclassification: workspace masking.

usage: correct_h1_masking.py <archive_dir> <archive_sums> <published_dir> <python_exe> <claude_bin> <pinned_classifier>

Finding (#800 record, section 8.4; confirmed on independent review): reclassify_h1.py
loaded each arm from the ARCHIVE path. classify_h1.masked() masks an arm's workspace
by arm["out"].parent / "ws", but the recorded tool inputs name the LIVE-root
workspace. On H1a-edit the identical Read and Edit requests of the two arms then did
not mask to <WS>, so the accepted live-2026-10-17/H1a-edit/outcome.r1r3.json lists 0
equivalent requests and 2 non-equivalent attempts per arm, where the as-run
outcome.json lists 2 equivalent requests. The equality check on permission decisions
was therefore vacuous on that path.

This tool changes nothing that was accepted. No host session runs, and nothing in
the archive or the published files is modified. For every #553 path it runs the
PINNED #553 classifier (<pinned_classifier>, whose SHA-256 must equal the
`classifier_sha256` recorded in reclassification.json) twice on the archived raw
evidence:

1. Reproduction: arms keyed to the archive path, exactly as #553 did. After the
   #553 redaction this must be byte-identical to the accepted outcome.r1r3.json.
   Any difference aborts, because the correction could then not be attributed to
   the keying alone.
2. Correction: arms read from the archive but keyed to the live-root location the
   run recorded (C:\\dev\\d5p2-h1-live). Only the keying differs from step 1.

Scope guard (independent review of #801). Before anything is published, the
correction must stay within the masking repair: only H1a-edit may change, and only
in the three permissions.comparison fields (ALLOWED_CHANGES); no label or
passes_path may change; and a changed path's corrected permissions must equal its
as-run permissions. Any violation aborts with nothing published.

Integrity follows #553 (reclassify_h1.verify: archive sums, unlisted files, the
manifest's raw files), and the helper hash must equal the recorded
`reclassify_tool_sha256`. Publication is fail-closed (reclassify_a2.publish): outputs
are redacted and leak-scanned into staging, the archive is re-verified after
classification and again immediately before the copy, and a failed check
publishes nothing. The final copy is per file, not an atomic transaction.

Writes, next to the unchanged accepted files:
  <published_dir>/<path>/outcome.r1r3.corrected.json   only for paths whose outcome changes
  <published_dir>/masking-correction.json              per-path reproduction and diff
Refuses to overwrite either.
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE_ROOT = r"C:\dev\d5p2-h1-live"


def load(name, path=None):
    spec = importlib.util.spec_from_file_location(name, path or HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


R = load("reclassify_h1")       # #553 helpers: verify, PATHS, PIN_MODEL
A2 = load("reclassify_a2")      # fail-closed publish (#800)
COL = R.COL


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_pinned(path, expected_sha):
    """Load the #553 classifier from <path>, only if its SHA-256 is the recorded one."""
    got = sha(path)
    if got != expected_sha:
        raise SystemExit(f"pinned classifier sha256 {got} != recorded {expected_sha}; nothing classified")
    return load("classify_h1_pinned", Path(path))


def load_keyed(Cp, archive, arm, root):
    """Read an arm from the archive; with `root`, key it to the recorded location."""
    a = Cp.load_arm(archive / arm / "out")
    if root is not None:
        a["out"] = Path(root) / arm / "out"
    return a


def outcome_text(Cp, archive, p, root, red, red_live):
    """The #553 publish form of one path's outcome (before COL.write_text's red.text)."""
    raw = Cp.classify(load_keyed(Cp, archive, p, root), load_keyed(Cp, archive, f"{p}-ctl", root), p, R.PIN_MODEL)
    return json.dumps(red.obj(red_live.obj(raw)), indent=2) + "\n"


def diff_paths(a, b, prefix=""):
    """JSON paths where a and b differ; dicts are descended, anything else is compared whole."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            out += diff_paths(a.get(k), b.get(k), f"{prefix}.{k}" if prefix else k)
        return out
    return [] if a == b else [prefix]


# The only change this correction may make (independent review of #801).
ALLOWED_CHANGES = {"H1a-edit": {"permissions.comparison.equivalent_requests",
                                "permissions.comparison.non_equivalent_attempts.control",
                                "permissions.comparison.non_equivalent_attempts.emitter"}}


def scope_problems(paths):
    """Fail-closed scope check: every reason the correction exceeds the masking repair.

    - a path outside ALLOWED_CHANGES must not change at all;
    - H1a-edit may change only the three permissions.comparison fields;
    - no label or passes_path may change;
    - a changed path's corrected permissions must equal its as-run permissions."""
    problems = []
    for p, v in paths.items():
        extra = sorted(set(v["differing_fields"]) - ALLOWED_CHANGES.get(p, set()))
        if extra:
            problems.append(f"{p}: unexpected changed fields {extra}")
        if v["label_corrected"] != v["label_accepted"]:
            problems.append(f"{p}: label changed {v['label_accepted']} -> {v['label_corrected']}")
        if v["passes_path_corrected"] != v["passes_path_accepted"]:
            problems.append(f"{p}: passes_path changed")
        if v["corrected_differs"] and not v["corrected_permissions_equal_as_run"]:
            problems.append(f"{p}: corrected permissions do not equal the as-run permissions")
    return problems


def perm_summary(o):
    c = (o.get("permissions") or {}).get("comparison") or {}
    nea = c.get("non_equivalent_attempts") or {}
    return {"equivalent_requests": len(c.get("equivalent_requests") or []),
            "mismatched_decisions": len(c.get("mismatched_decisions") or []),
            "non_equivalent_attempts": {k: len(v or []) for k, v in sorted(nea.items())}}


def main(argv):
    archive, sums, pub, py, cbin, pinned = (Path(argv[1]), Path(argv[2]), Path(argv[3]), argv[4], argv[5],
                                            Path(argv[6]))
    summary_path = pub / "masking-correction.json"
    if summary_path.exists() or any((pub / p / "outcome.r1r3.corrected.json").exists() for p in R.PATHS):
        raise SystemExit("refusing to overwrite existing correction output")
    accepted_summary = json.loads((pub / "reclassification.json").read_text(encoding="utf-8"))
    if sha(HERE / "reclassify_h1.py") != accepted_summary["reclassify_tool_sha256"]:
        raise SystemExit("reclassify_h1.py differs from the #553 tool; nothing classified")
    Cp = load_pinned(pinned, accepted_summary["classifier_sha256"])
    manifest = json.loads((pub / "MANIFEST.json").read_text(encoding="utf-8"))
    sums_before = sha(sums)
    integrity = R.verify(archive, sums, manifest)
    if integrity["problems"]:
        print(json.dumps(integrity, indent=2))
        raise SystemExit("integrity check failed; nothing classified")

    red = COL.Redactor(archive, HERE, py, cbin)                  # as #553
    red_live = COL.Redactor(Path(LIVE_ROOT), HERE, py, cbin)     # as #553
    summary = {
        "corrects": "#553 live-2026-10-17 outcome.r1r3.json (workspace masking); accepted files unchanged",
        "rules": Cp.RULES_ID,
        "pinned_classifier_sha256": sha(pinned),
        "tool_sha256": {"correct_h1_masking.py": sha(Path(__file__)),
                        "reclassify_h1.py (helpers)": sha(HERE / "reclassify_h1.py"),
                        "reclassify_a2.py (publish)": sha(HERE / "reclassify_a2.py"),
                        "collect_h1.py (redaction)": sha(HERE / "collect_h1.py")},
        "integrity": integrity, "paths": {},
    }
    files = {}
    for p in R.PATHS:
        accepted_text = (pub / p / "outcome.r1r3.json").read_text(encoding="utf-8")
        repro = red.text(outcome_text(Cp, archive, p, None, red, red_live))
        if repro != accepted_text:
            raise SystemExit(f"{p}: archive-keyed run does not reproduce the accepted outcome; nothing published")
        corr = red.text(outcome_text(Cp, archive, p, LIVE_ROOT, red, red_live))
        accepted, corrected = json.loads(accepted_text), json.loads(corr)
        as_run = json.loads((pub / p / "outcome.json").read_text(encoding="utf-8"))
        changed = corr != accepted_text
        summary["paths"][p] = {
            "reproduces_accepted_byte_identical": True,
            "corrected_differs": changed,
            "differing_fields": diff_paths(accepted, corrected),
            "label_accepted": accepted["label"], "label_corrected": corrected["label"],
            "passes_path_accepted": accepted["passes_path"], "passes_path_corrected": corrected["passes_path"],
            "permissions": {"as_run": perm_summary(as_run), "accepted_r1r3": perm_summary(accepted),
                            "corrected_r1r3": perm_summary(corrected)},
            "corrected_permissions_equal_as_run": corrected.get("permissions") == as_run.get("permissions"),
        }
        if changed:
            files[pub / p / "outcome.r1r3.corrected.json"] = corr
    scope = scope_problems(summary["paths"])
    if scope:
        print(json.dumps(scope, indent=2))
        raise SystemExit("correction exceeds the masking repair; nothing published")
    summary["scope_check"] = {"allowed_changes": {p: sorted(f) for p, f in ALLOWED_CHANGES.items()},
                              "problems": scope}
    labels_same = all(v["label_accepted"] == v["label_corrected"] for v in summary["paths"].values())
    summary["labels_unchanged"] = labels_same
    summary["h1_gate_r1r3_corrected"] = ("PASS" if all(v["passes_path_corrected"] for v in summary["paths"].values())
                                         else "NOT MET")
    integrity_after = R.verify(archive, sums, manifest)
    summary["integrity_after"] = {"problems": integrity_after["problems"],
                                  "archive_sums_unchanged": sha(sums) == sums_before}
    if integrity_after["problems"] or sha(sums) != sums_before:
        raise SystemExit("archive changed during correction; nothing published")

    def gate():
        again = R.verify(archive, sums, manifest)
        return again["problems"] + ([] if sha(sums) == sums_before else ["archive SHA256SUMS changed"])

    files[summary_path] = json.dumps(summary, indent=2) + "\n"
    A2.publish(files, red, gate)
    for p, v in summary["paths"].items():
        print(p, "| reproduces accepted:", v["reproduces_accepted_byte_identical"], "| corrected differs:",
              v["corrected_differs"], v["differing_fields"], "| label", v["label_accepted"], "->", v["label_corrected"],
              "| permissions", v["permissions"]["accepted_r1r3"], "->", v["permissions"]["corrected_r1r3"])
    print("Labels unchanged:", labels_same, "| H1 gate (R1-R3, corrected):", summary["h1_gate_r1r3_corrected"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""C4 Gate 2: replay the CI1.2 contract corpora against an already-installed evaluator.

Reuses the merged ``scripts/ci1_evaluator_preflight.py`` functions unchanged
(identity probe, RECORD verification, corpus replay, ADR-005 cross-check,
memory regeneration, classifier stubs). The only difference from its own
``run_preflight`` is the install step: the evaluator venv was created by the
Gate 2 run script exactly as the CI1 lab workflow does it (approved preserved
wheel, sha256-checked, plus the lab's hash-locked runtime dependencies), so it
is passed in rather than rebuilt or downloaded.

Usage: python c4_gate2_ci1_replay.py <core checkout> <evaluator venv> <wheel> <work dir> <json out>

The preflight's Markdown renderer is not used: it labels any non-PyPI source as a
commit build, which this preserved artifact is not.
"""
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

core, venv, wheel, work, json_out = (Path(a) for a in sys.argv[1:6])
spec = importlib.util.spec_from_file_location("ci1_preflight", core / "scripts" / "ci1_evaluator_preflight.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

VERSION = "0.10.0"
work.mkdir(parents=True, exist_ok=False)
m = p.load_matrix_module()
python = p.venv_python(venv)
probe = p.probe_identity(python, work)
errors = p.identity_errors(probe, venv, p.REPO_ROOT, VERSION)
verified, rec_errors = p.record_errors(wheel, Path(probe["purelib"]), VERSION)
if errors or rec_errors or verified == 0:
    sys.exit("evaluator identity check failed:\n" + "\n".join(errors + rec_errors))

ev = p.Evaluator(python)
sections = {
    "replay": p._section(p.replay_corpora(m, ev, work), "Manifest replay (cases.json x query variants / modes)"),
    "adr005": p._section(p.adr005_checks(m, ev, work), "ADR-005 global-rule cross-check"),
    "regeneration": p._section(p.regeneration_checks(ev, work), "Corpus memory regeneration"),
    "classifier": p._section(p.classifier_checks(m), "Classifier stub checks"),
}
after = p.probe_identity(python, work)
_, rec_after = p.record_errors(wheel, Path(after["purelib"]), VERSION)
rechecked = after == probe and not rec_after
report = {
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "work_dir": str(work), "version": VERSION,
    "source": {"kind": "preserved-artifact", "artifact": "CI1 lab run 39055862171 p2-evaluator-preflight",
               "commit": "0b74d410b45e7b3efcf08d00ce58e7bd7017b757"},
    "host": "see environment.txt", "harness": {"python": sys.executable, "pytest": p._harness_pytest_version()},
    "identity": {"wheel_filename": wheel.name, "wheel_sha256": p.sha256_file(wheel), "lock": [],
                 "pip": "see pip-freeze-evaluator.txt", "probe": probe, "record_files_verified": verified,
                 "entry_point": ["<venv python>", *ev.prefix[1:]], "rechecked": rechecked},
    "corpus_provenance": p.corpus_provenance(),
    "corpus_versions": [f"{c}/{v}" for c, v, _ in p.corpus_versions()],
    "sections": sections,
    "passed": rechecked and all(s["failed"] == 0 for s in sections.values()),
}
json_out.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
for s in sections.values():
    print(f"[c4-gate2] {s['label']}: {s['passed']}/{s['total']} parity")
    for r in s["results"]:
        if not r["parity"]:
            print(f"[c4-gate2]   FAIL {r.get('corpus', r.get('check'))} {r.get('case', '')} "
                  f"{r['variant']}: {'; '.join(r['diffs'])}")
print(f"[c4-gate2] identity rechecked: {rechecked}")
print(f"[c4-gate2] verdict: {'PASS' if report['passed'] else 'FAIL'}")
sys.exit(0 if report["passed"] else 1)

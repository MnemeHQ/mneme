"""Build or verify the P0-A Set 1 fixture-and-oracle freeze.

    python validation/semantic-constraint-p0a/scripts/run_freeze.py verify
    python validation/semantic-constraint-p0a/scripts/run_freeze.py build

``verify`` (default) checks every pinned digest, checks that the #570 Set 0
files are byte-identical to 04a1f989, re-runs the frozen oracle on the frozen
fixtures only, and compares the result with the committed evidence. It writes
nothing. ``build`` regenerates the evidence and MANIFEST.json; it is used once,
to create the freeze, and any later use shows up in the diff.
"""

import difflib
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

P0A_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = P0A_DIR.parents[1]
SANDBOX_DIR = REPO_ROOT / "validation" / "orchestrator-decision-sandbox"
sys.path.insert(0, str(P0A_DIR / "oracle"))
sys.path.insert(0, str(SANDBOX_DIR / "scripts"))

import oracle as oracle_v1  # noqa: E402 - #570 oracle, used read-only for comparison
import oracle_v2  # noqa: E402

ANCHOR_MAIN = "819582a9c908555743130595ab0dbe1d12714f2f"
ANCHOR_570 = "04a1f989edd18080755b1fb139a3e87c28fb9c11"
SET0_FILES = (
    "validation/orchestrator-decision-sandbox/fixtures/cases.json",
    "validation/orchestrator-decision-sandbox/scripts/oracle.py",
)
SUB_CONSTRAINTS = ("C1", "C2", "C3")

MANIFEST = P0A_DIR / "MANIFEST.json"
OBSERVATIONS = P0A_DIR / "evidence" / "oracle_observations.json"
COMPARISON = P0A_DIR / "evidence" / "label_vs_oracle.json"
SET1_CASES = P0A_DIR / "set1" / "cases.json"
SET0_LABELS = P0A_DIR / "set0" / "labels.json"
TEMPLATE_FILES = ("set1/template/router_base.py", "set1/template/template.json")
ORACLE_FILE = "oracle/oracle_v2.py"


class FreezeError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(rel: str) -> bytes:
    return (P0A_DIR / rel).read_bytes()


def repo_rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def dump(data) -> bytes:
    return (json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def edit_delta(before: bytes, after: bytes) -> dict:
    """Removed and introduced lines between two snapshots (no context lines)."""
    a = before.decode("utf-8").splitlines()
    b = after.decode("utf-8").splitlines()
    removed, introduced = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend(a[i1:i2])
        if tag in ("replace", "insert"):
            introduced.extend(b[j1:j2])
    return {"removed_lines": removed, "introduced_lines": introduced}


def fixture_files() -> list:
    """Every frozen fixture file, as paths relative to P0A_DIR."""
    files = [*TEMPLATE_FILES, "set1/cases.json", "set0/labels.json"]
    for case in load_json(SET1_CASES)["cases"]:
        files.extend(case["files"].values())
    return sorted(set(files))


def set0_cases() -> list:
    return load_json(REPO_ROOT / SET0_FILES[0])


def subjects() -> list:
    """(set, case id, snapshot, source bytes or None, probes) for every oracle run."""
    set1 = load_json(SET1_CASES)
    default = [set1["default_probe"]]
    out = []
    for case in set0_cases():
        source = case["content"].encode("utf-8") if case["target_path"].endswith(".py") else None
        out.append(("Set 0", case["id"], "content", source, default))
    for case in set1["cases"]:
        for snapshot, rel in sorted(case["files"].items()):
            out.append(("Set 1", case["id"], snapshot, read(rel), case.get("probes", default)))
    return out


def frozen_digests() -> set:
    digests = {sha256_bytes(read(rel)) for rel in fixture_files()}
    digests |= {sha256_bytes(c["content"].encode("utf-8")) for c in set0_cases()}
    return digests


def build_observations() -> dict:
    allowed = frozen_digests()
    runs = []
    for set_name, case_id, snapshot, source, probes in subjects():
        for probe in probes:
            entry = {"set": set_name, "case": case_id, "snapshot": snapshot, "probe": probe["id"]}
            if source is None:
                entry["observation"] = {"load": "NOT_APPLICABLE: non-Python target"}
            else:
                entry["observation"] = oracle_v2.observe(
                    source, frozen_digests=allowed, env=probe["env"]
                )
                with oracle_v2._probe_environ(probe["env"]):
                    v1 = oracle_v1.evaluate(source.decode("utf-8"))
                entry["oracle_v1_comparison"] = {
                    "verdict": "ACCEPT" if v1.accept else "REJECT",
                    "failures": list(v1.failures),
                }
            runs.append(entry)
    return {
        "schema": "p0a-oracle-observations/v1",
        "oracle_version": oracle_v2.ORACLE_VERSION,
        "oracle_sha256": sha256_bytes(read(ORACLE_FILE)),
        "note": "Runtime observations, not labels (charter section 5.1). oracle_v1_comparison is the #570 oracle on the same source, for reference only.",
        "runs": runs,
    }


def build_comparison(observations: dict) -> dict:
    labels = {c["id"]: c["labels"] for c in load_json(SET0_LABELS)["cases"]}
    labels.update({c["id"]: c["labels"] for c in load_json(SET1_CASES)["cases"]})
    rows, disagreements = [], []
    for run in observations["runs"]:
        if run["snapshot"] == "before":
            continue  # T and U labels judge the edit by its resulting file
        observed = run["observation"].get("violation_observed")
        for sc in SUB_CONSTRAINTS:
            label = labels[run["case"]][sc]["label"]
            if observed is None:
                status = "ORACLE_NOT_APPLICABLE"
            else:
                status = "AGREE" if (label == "violation") == observed[sc] else "DISAGREE"
            row = {
                "case": run["case"],
                "snapshot": run["snapshot"],
                "probe": run["probe"],
                "sub_constraint": sc,
                "label": label,
                "oracle_violation_observed": None if observed is None else observed[sc],
                "status": status,
            }
            rows.append(row)
            if status == "DISAGREE":
                disagreements.append(row)
    return {
        "schema": "p0a-label-vs-oracle/v1",
        "oracle_version": observations["oracle_version"],
        "note": "Mechanical comparison of architectural labels with oracle_v2 observations on the resulting file. Reasons for each disagreement are in README.md.",
        "disagreements": disagreements,
        "rows": rows,
    }


def git_blob(commit: str, rel: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{rel}"], cwd=REPO_ROOT, capture_output=True, check=True
    ).stdout


def build_manifest(observations_bytes: bytes, comparison_bytes: bytes, environment: dict) -> dict:
    set1 = load_json(SET1_CASES)
    cases = []
    for case in set1["cases"]:
        entry = {
            "id": case["id"],
            "kind": case["kind"],
            "files": {snap: {"path": rel, "sha256": sha256_bytes(read(rel))} for snap, rel in sorted(case["files"].items())},
            "labels": {sc: case["labels"][sc]["label"] for sc in SUB_CONSTRAINTS},
            "rationales": {sc: case["labels"][sc]["rationale"] for sc in SUB_CONSTRAINTS},
            "adjudication": case["adjudication"],
        }
        if case["kind"] == "edit":
            entry["edit_delta"] = edit_delta(read(case["files"]["before"]), read(case["files"]["after"]))
        cases.append(entry)
    set0_labels = {c["id"]: c["labels"] for c in load_json(SET0_LABELS)["cases"]}
    set0 = [
        {
            "id": c["id"],
            "content_sha256": sha256_bytes(c["content"].encode("utf-8")),
            "labels": {sc: set0_labels[c["id"]][sc]["label"] for sc in SUB_CONSTRAINTS},
            "rationales": {sc: set0_labels[c["id"]][sc]["rationale"] for sc in SUB_CONSTRAINTS},
        }
        for c in set0_cases()
    ]
    return {
        "schema": "p0a-set1-freeze-manifest/v1",
        "track": "P0-A semantic constraint validation",
        "charter": "docs/plans/2026-10-21-p0a-semantic-constraint-validation-charter.md",
        "status": "frozen; precommitted and visible, not blind",
        "anchors": {"main": ANCHOR_MAIN, "sandbox_pr570": ANCHOR_570},
        "oracle": {
            "version": oracle_v2.ORACLE_VERSION,
            "path": ORACLE_FILE,
            "sha256": sha256_bytes(read(ORACLE_FILE)),
        },
        "fixture_files": {rel: sha256_bytes(read(rel)) for rel in fixture_files()},
        "set1_cases": cases,
        "set0": {
            "pinned_files_at_" + ANCHOR_570[:8]: {rel: sha256_bytes(git_blob(ANCHOR_570, rel)) for rel in SET0_FILES},
            "cases": set0,
        },
        "evidence": {
            "evidence/oracle_observations.json": sha256_bytes(observations_bytes),
            "evidence/label_vs_oracle.json": sha256_bytes(comparison_bytes),
        },
        "runner": {"path": "scripts/run_freeze.py", "sha256": sha256_bytes(read("scripts/run_freeze.py"))},
        "environment": environment,
    }


def current_environment() -> dict:
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "os": platform.platform(),
    }


def verify() -> list:
    """Return a list of problems; empty means the freeze holds."""
    problems = []
    manifest = load_json(MANIFEST)
    for rel, pinned in manifest["fixture_files"].items():
        if sha256_bytes(read(rel)) != pinned:
            problems.append(f"fixture digest mismatch: {rel}")
    if sorted(manifest["fixture_files"]) != fixture_files():
        problems.append("fixture file set differs from manifest")
    if sha256_bytes(read(ORACLE_FILE)) != manifest["oracle"]["sha256"]:
        problems.append("oracle digest mismatch")
    if oracle_v2.ORACLE_VERSION != manifest["oracle"]["version"]:
        problems.append("oracle version mismatch")
    pinned_570 = manifest["set0"]["pinned_files_at_" + ANCHOR_570[:8]]
    for rel in SET0_FILES:
        if sha256_bytes((REPO_ROOT / rel).read_bytes()) != pinned_570[rel]:
            problems.append(f"#570 file not byte-identical to pin: {rel}")
    if problems:
        return problems  # do not execute anything when a digest is off

    observations_bytes = dump(build_observations())
    comparison_bytes = dump(build_comparison(json.loads(observations_bytes)))
    if observations_bytes != OBSERVATIONS.read_bytes():
        problems.append("oracle observations differ from committed evidence")
    if comparison_bytes != COMPARISON.read_bytes():
        problems.append("label-vs-oracle comparison differs from committed evidence")
    expected = build_manifest(observations_bytes, comparison_bytes, manifest["environment"])
    if expected != manifest:
        problems.append("MANIFEST.json differs from a rebuild (environment block excluded)")
    return problems


def build() -> None:
    observations_bytes = dump(build_observations())
    comparison_bytes = dump(build_comparison(json.loads(observations_bytes)))
    OBSERVATIONS.parent.mkdir(exist_ok=True)
    OBSERVATIONS.write_bytes(observations_bytes)
    COMPARISON.write_bytes(comparison_bytes)
    MANIFEST.write_bytes(dump(build_manifest(observations_bytes, comparison_bytes, current_environment())))


def main(argv: list) -> int:
    command = argv[1] if len(argv) > 1 else "verify"
    if command == "build":
        build()
        print(f"[p0a-freeze] built {repo_rel(MANIFEST)}")
        return 0
    if command == "verify":
        problems = verify()
        for p in problems:
            print(f"[p0a-freeze] FAIL {p}")
        if not problems:
            print("[p0a-freeze] OK: digests, #570 pins, observations and manifest match")
        return 1 if problems else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

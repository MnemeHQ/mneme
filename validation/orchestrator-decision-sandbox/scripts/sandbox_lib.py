"""Shared helpers for the orchestrator decision sandbox.

Every fixture is built in a caller-owned temp directory. Nothing here writes
to the repository's own memory, ADRs or source.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[1]
REPO_ROOT = SANDBOX.parents[1]
PINNED_BUILD = REPO_ROOT / "validation" / "langgraph" / "pinned-build.json"
DECISION_ID = "ADR-001"
FORBIDDEN_LITERAL = "DISABLE_ROUTER_TIMEOUT"
QUERY = "router deadline fallback"

LABELS = ("BLOCKED", "ALLOWED", "WARNED", "NOT_EVALUATED", "ERROR_DEGRADED")


class BlockerError(RuntimeError):
    """A stop condition from the plan: never record results past one."""


# ── Pins ────────────────────────────────────────────────────────────────────


def pinned_packages() -> dict:
    return json.loads(PINNED_BUILD.read_text(encoding="utf-8"))["packages"]


def pin_drift() -> dict:
    drift = {}
    for package, pinned in pinned_packages().items():
        try:
            installed = metadata.version(package)
        except metadata.PackageNotFoundError:
            installed = None
        if installed != pinned:
            drift[package] = (pinned, installed)
    return drift


def assert_pinned() -> None:
    drift = pin_drift()
    if drift:
        detail = ", ".join(f"{p} {want} != {got}" for p, (want, got) in sorted(drift.items()))
        raise BlockerError(f"installed packages differ from pinned-build.json: {detail}")


# ── Cases and digests ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Case:
    id: str
    sub_constraint: str
    target_path: str
    content: str
    oracle: str
    predicted_cli: str
    classification: str
    description: str


def load_cases() -> list:
    raw = json.loads((SANDBOX / "fixtures" / "cases.json").read_text(encoding="utf-8"))
    return [Case(**row) for row in raw]


def case_by_id(case_id: str) -> Case:
    return next(c for c in load_cases() if c.id == case_id)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path):
    path = Path(path)
    return sha256_bytes(path.read_bytes()) if path.is_file() else None


def tree_digest(root: Path) -> str:
    """Digest of src/ and docs/ (relative path + content), excluding .mneme/."""
    h = hashlib.sha256()
    for sub in ("src", "docs"):
        for p in sorted((root / sub).rglob("*")):
            if p.is_file():
                h.update(p.relative_to(root).as_posix().encode("utf-8") + b"\0")
                h.update(sha256_file(p).encode("ascii") + b"\n")
    return h.hexdigest()


def router_source(root: Path) -> str:
    return (root / "src" / "router.py").read_text(encoding="utf-8")


# ── CLI invocation ──────────────────────────────────────────────────────────


def child_env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("MNEME_HOOK_MODE", None)
    return env


def mneme(args: list, cwd: Path) -> subprocess.CompletedProcess:
    """Run the shipped CLI with the fixture as working directory."""
    return subprocess.run(
        [sys.executable, "-m", "mneme.cli", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=child_env(),
        check=False,
    )


def check(root: Path, input_path: Path, target_path: str) -> tuple:
    """`mneme check --json` in strict mode. Returns (proc, payload or None)."""
    proc = mneme(
        [
            "check",
            "--memory", ".mneme/project_memory.json",
            "--input", str(input_path),
            "--target-path", target_path,
            "--query", QUERY,
            "--mode", "strict",
            "--json",
        ],
        cwd=root,
    )
    try:
        payload = json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError):
        payload = None
    if not isinstance(payload, dict):
        payload = None
    return proc, payload


def label_from_check(payload, exit_code: int) -> str:
    """Map a check payload to an outcome label; never upgrade a gap to a pass."""
    if not isinstance(payload, dict) or "verdict" not in payload:
        return "ERROR_DEGRADED"
    if payload.get("evaluation_complete") is not True:
        return "ERROR_DEGRADED"
    verdict = payload["verdict"]
    if verdict == "FAIL":
        return "BLOCKED"
    if verdict == "WARN":
        return "WARNED"
    if verdict == "PASS":
        return "ALLOWED"
    return "ERROR_DEGRADED"


# ── Baseline ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Baseline:
    root: Path
    memory: Path
    rule_id: str
    decision_version_id: str
    baseline_sha256: str
    import_preview: str


def _blocker(step: str, proc: subprocess.CompletedProcess) -> BlockerError:
    return BlockerError(
        f"{step} exited {proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


def build_baseline(dest: Path) -> Baseline:
    """Copy the synthetic app, init memory, import ADR-001, verify authority.

    Raises BlockerError on any ambiguity: memory location, active decision,
    rule identity, target-path applicability or strict mode.
    """
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise BlockerError(f"baseline destination is not empty: {dest}")
    shutil.copytree(SANDBOX / "synthetic_app", dest, dirs_exist_ok=True)
    (dest / "docs" / "adr").mkdir(parents=True, exist_ok=True)
    shutil.copy2(SANDBOX / "adr" / "ADR-001.md", dest / "docs" / "adr" / "ADR-001.md")
    baseline_sha = tree_digest(dest)

    proc = mneme(["init"], cwd=dest)
    if proc.returncode != 0:
        raise _blocker("mneme init", proc)
    memory = dest / ".mneme" / "project_memory.json"
    if not memory.is_file():
        raise BlockerError(f"mneme init did not create {memory}")

    preview = mneme(
        ["adr", "import", "docs/adr", "--memory", ".mneme/project_memory.json", "--dry-run"],
        cwd=dest,
    )
    if preview.returncode != 0 or f"rule: FORBID_LITERAL {FORBIDDEN_LITERAL}" not in preview.stdout:
        raise _blocker("mneme adr import --dry-run", preview)
    applied = mneme(
        ["adr", "import", "docs/adr", "--memory", ".mneme/project_memory.json", "--apply"],
        cwd=dest,
    )
    if applied.returncode != 0:
        raise _blocker("mneme adr import --apply", applied)

    index = json.loads(memory.read_text(encoding="utf-8"))["decision_index"]
    decisions = index["decisions"]
    if [d["decision_id"] for d in decisions] != [DECISION_ID] or decisions[0]["lifecycle_status"] != "active":
        raise BlockerError(f"expected exactly one active {DECISION_ID}, got {decisions}")
    version_id = decisions[0]["active_version_id"]
    rules = index["rules"]
    if len(rules) != 1:
        raise BlockerError(f"expected exactly one rule, got {rules}")
    rule = rules[0]
    expected = {
        "decision_id": DECISION_ID,
        "decision_version_id": version_id,
        "rule_type": "FORBID_LITERAL",
        "rule_payload": {"value": FORBIDDEN_LITERAL},
        "applicability": {"include_paths": ["src/**"]},
    }
    mismatched = {k: rule.get(k) for k, v in expected.items() if rule.get(k) != v}
    if mismatched:
        raise BlockerError(f"rule does not match ADR-001: {mismatched}")

    # Applicability and strict mode, observed through the shipped check.
    probe_input = dest.parent / f"{dest.name}.baseline-probe.py"
    probe_input.write_bytes((dest / "src" / "router.py").read_bytes())
    try:
        proc, payload = check(dest, probe_input, "src/router.py")
    finally:
        probe_input.unlink()
    if payload is None:
        raise _blocker("baseline mneme check", proc)
    applicability = payload.get("applicability") or []
    if (
        payload.get("mode") != "strict"
        or payload.get("verdict") != "PASS"
        or payload.get("evaluation_complete") is not True
        or [a.get("outcome") for a in applicability] != ["APPLIED"]
        or applicability[0].get("rule_id") != rule["rule_id"]
        or payload.get("freshness")
    ):
        raise BlockerError(f"baseline check is ambiguous: {json.dumps(payload)}")
    if tree_digest(dest) != baseline_sha:
        raise BlockerError("baseline source changed during memory setup")

    return Baseline(
        root=dest,
        memory=memory,
        rule_id=rule["rule_id"],
        decision_version_id=version_id,
        baseline_sha256=baseline_sha,
        import_preview=preview.stdout,
    )

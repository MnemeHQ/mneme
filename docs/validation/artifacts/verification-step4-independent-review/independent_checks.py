"""Verification step 4: independent checks of Verification steps 2 and 3.

Read-only reviewer harness. It re-derives the key facts of steps 2 and 3 from
raw sources and does NOT import, call or reuse ``run_controls.py``,
``run_step3.py``, ``ci_replay.sh`` or their ``results.json`` assessors:

- pins from git objects, the preserved approved wheel (unpacked and compared
  file by file with the ``0b74d410`` tree) and the local container image;
- checkpoint A (pre-mutation) through LangChain ``ToolGateMiddleware`` at
  v0.11.0 with this script's own handler, run from a neutral directory;
- the CI fixture repository rebuilt with a different plumbing method (index +
  ``write-tree`` instead of ``mktree``), its SHAs compared with the five raw
  ``mneme.c4.gate-report/v1`` reports;
- fresh ``mneme check`` runs with the ``0b74d410`` evaluator (from the approved
  wheel) and with v0.11.0, compared with each report's raw ``stdout``;
- the pinned adapter's own ``verify-report`` on every committed report (host,
  and with ``--container`` also inside the pinned image with the gate's own
  Python), plus tamper probes that show what ``verify-report`` binds;
- an independent CI replay (``--container``): this script's own container
  script runs ``evaluate`` + ``verify-report`` on the rebuilt fixture repo;
- the Claude Code hook at v0.11.0 through the SHIPPED DEFAULT ``subprocess``
  check transport (step 2 used the benchmark-only ``inprocess`` transport),
  with a different fixture and a different synthetic host pin, assessed per
  ADR-029 dimension from the raw record before comparing with
  ``relevant_enforcement_per_rule``.

Run from the repository root:

    git worktree add --detach <rt> 619d5405
    python docs/validation/artifacts/verification-step4-independent-review/independent_checks.py \\
        --runtime-root <rt> --approved-wheel <mneme_hq-0.10.0-py3-none-any.whl> [--container]

``--runtime-root`` must be a clean checkout whose ``mneme/`` tree is the tree
of v0.11.0 (``619d5405``), which is also the tree of ``101f3f42``. Writes
``checks.json`` next to this file; exits 1 if any check's expectation fails.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
STEP3 = REPO / "docs/validation/artifacts/verification-step3-e2e-fixture"
REQUIREMENTS = REPO / "docs/validation/adr033-c4-gate2-offline-2026-10-26/inputs/evaluator-requirements.txt"

PIN = {
    "v0.11.0": "619d5405e80da61788448a7a0eeacc7c5eb3d0c0",
    "step2_impl": "101f3f427901c01fa4330e4add62af6ba8057a51",
    "adapter_commit": "c51729f78199203fe12fcbc5c678b89a2c4f7d3e",
    "evaluator_commit": "0b74d410b45e7b3efcf08d00ce58e7bd7017b757",
}
MEMORY_PATH = "docs/integrations/c4-gate/project_memory.example.json"
MEMORY_BLOB = "4c669436199643458ae11fe7991ccfaa5b1a6e03"
ADAPTER_PATH = "scripts/ci/adr033_c4_gate.py"
ADAPTER_BLOB = "5feedf60ce1a67b2bb85673354c8b8b367a87d06"
ADAPTER_SHA256 = "afe1d69c1ce4170875989c5866bb2ec7b5089fc895efa699ced826317e3777f9"
WHEEL_SHA256 = "e3fcc769c440ed232ad05117f256739daf233e0c9f6d3d46586adc0de9b48c51"
IMAGE = "ubuntu@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac"
CASES = ("B1_allow", "B2_bypass_violation", "B3_incomplete_symlink",
         "B4_missing_identity", "B5_later_revision")

# Frozen fixture inputs (step 3 record §4). Commit messages and dates are part
# of the fixture: they determine the commit SHAs being checked.
README = b"# Project readme\n"
INSTALL = b"# Install\n\nRun install legacy-client to get started.\n"   # A2 / B2 / B4
ALLOW = b"# Guide\n\nInstall the current client with the documented installer.\n"
STALE_SUFFIX = b"\nA later edit that pre-mutation never checked.\n"
GIT_ID = {"GIT_AUTHOR_NAME": "Verification Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
          "GIT_COMMITTER_NAME": "Verification Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
          "GIT_AUTHOR_DATE": "2026-11-09T00:00:00+0000", "GIT_COMMITTER_DATE": "2026-11-09T00:00:00+0000"}

# Step 4 hook fixture: deliberately different from step 2 (decision ids, text,
# host pin), so agreement is not an artefact of reusing step 2's inputs.
HOST = ("step4-review-host", "cd" * 32)
NUM_ABOVE = "ROUTER_DEADLINE_S = 45\ndef run(x):\n    return classify(x, 1)\n"
NUM_WITHIN = "ROUTER_DEADLINE_S = 4\ndef run(x):\n    return classify(x, 1)\n"
NUM_DYNAMIC = "ROUTER_DEADLINE_S = lookup()\ndef run(x):\n    return classify(x, 1)\n"

CHECKS: list[dict] = []
SCRUB: list[str] = []


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scrub(value):
    if isinstance(value, str):
        for s in SCRUB:
            value = value.replace(s, "<tmp>").replace(s.replace("\\", "/"), "<tmp>")
        return value
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def check(section: str, cid: str, claim: str, expected, actual, note: str = "") -> bool:
    ok = expected == actual
    CHECKS.append({"section": section, "id": cid, "claim": claim, "expected": scrub(expected),
                   "actual": scrub(actual), "ok": ok, **({"note": note} if note else {})})
    return ok


def git(*args, cwd=REPO, input_bytes=None, env=None) -> bytes:
    return subprocess.run(["git", *args], cwd=cwd, input=input_bytes, capture_output=True,
                          check=True, env=env).stdout


def gits(*args, **kw) -> str:
    return git(*args, **kw).decode().strip()


# ── 1. pins ──────────────────────────────────────────────────────────────────

def pins(rt: Path, wheel: Path, container: bool, work: Path) -> Path:
    for name, full in PIN.items():
        check("pins", f"commit:{name}", f"{full[:8]} resolves to a commit",
              full, gits("rev-parse", f"{full[:8]}^{{commit}}"))
    check("pins", "tag:v0.11.0", "tag v0.11.0 is 619d5405", PIN["v0.11.0"], gits("rev-parse", "v0.11.0^{commit}"))
    t619 = gits("rev-parse", f"{PIN['v0.11.0']}:mneme")
    check("pins", "tree:101f3f42=v0.11.0", "mneme/ tree at 101f3f42 is the v0.11.0 tree",
          t619, gits("rev-parse", f"{PIN['step2_impl']}:mneme"))
    check("pins", "tree:fixture-builder", "tests/canonical_fixtures.py blob identical at 101f3f42 and v0.11.0",
          gits("rev-parse", f"{PIN['v0.11.0']}:tests/canonical_fixtures.py"),
          gits("rev-parse", f"{PIN['step2_impl']}:tests/canonical_fixtures.py"))
    check("pins", "runtime-root:tree", "runtime root HEAD carries the v0.11.0 mneme/ tree",
          t619, gits("rev-parse", "HEAD:mneme", cwd=rt))
    check("pins", "runtime-root:clean", "runtime root has no changes or untracked files under mneme/ or tests/",
          "", gits("status", "--porcelain", "--untracked-files=all", "--", "mneme", "tests", cwd=rt))
    check("pins", "memory:blob", "fixture memory file hashes to blob 4c669436",
          MEMORY_BLOB, gits("hash-object", MEMORY_PATH))
    check("pins", "memory:committed", "the committed tree carries the same blob",
          MEMORY_BLOB, gits("rev-parse", f"HEAD:{MEMORY_PATH}"))
    check("pins", "adapter:blob", "adapter blob at c51729f7", ADAPTER_BLOB,
          gits("rev-parse", f"{PIN['adapter_commit']}:{ADAPTER_PATH}"))
    adapter = git("cat-file", "blob", ADAPTER_BLOB)
    check("pins", "adapter:sha256", "adapter blob content sha256", ADAPTER_SHA256, sha(adapter))
    check("pins", "evaluator:ancestor", "0b74d410 is an ancestor of v0.11.0 (older evaluator)", 0,
          subprocess.run(["git", "merge-base", "--is-ancestor", PIN["evaluator_commit"], PIN["v0.11.0"]],
                         cwd=REPO).returncode)
    # wheel: hash and content provenance
    data = wheel.read_bytes()
    check("pins", "wheel:sha256", "preserved wheel sha256 equals the approved pin", WHEEL_SHA256, sha(data))
    tree = {line.split("\t", 1)[1]: line.split()[2] for line in
            gits("ls-tree", "-r", PIN["evaluator_commit"], "--", "mneme").splitlines()}
    wdir = work / "wheel"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(wdir)
        members = sorted(n for n in z.namelist() if n.startswith("mneme/") and not n.endswith("/"))
    mismatched = [m for m in members
                  if m not in tree or gits("hash-object", str(wdir / m)) != tree[m]]
    check("pins", "wheel:source-tree",
          "every mneme/ file in the wheel is byte-identical to the 0b74d410 tree, and the sets match",
          {"members": len(tree), "mismatched": [], "set_equal": True},
          {"members": len(members), "mismatched": mismatched, "set_equal": set(members) == set(tree)})
    meta = (wdir / "mneme_hq-0.10.0.dist-info/METADATA").read_text(encoding="utf-8")
    check("pins", "wheel:version", "wheel metadata version", "0.10.0",
          next(l.split(": ", 1)[1] for l in meta.splitlines() if l.startswith("Version: ")))
    if container:
        insp = subprocess.run(["docker", "image", "inspect", IMAGE, "--format", "{{json .RepoDigests}}"],
                              capture_output=True, text=True)
        check("pins", "image:digest", "local image is addressed by the pinned digest", True,
              IMAGE in (insp.stdout or ""))
        osr = subprocess.run(["docker", "run", "--rm", IMAGE, "sh", "-c",
                              ". /etc/os-release; echo $PRETTY_NAME; command -v python3 || echo no-python3"],
                             capture_output=True, text=True, env={**os.environ, "MSYS_NO_PATHCONV": "1"})
        check("pins", "image:os", "pinned image OS, and whether it ships Python itself",
              ["Ubuntu 24.04.5 LTS", "no-python3"], osr.stdout.split("\n")[:2],
              "python3/git come from the live Ubuntu archive at run time (not hash-pinned)")
    return wdir


# ── 2. checkpoint A: pre-mutation (own driver) ──────────────────────────────

def checkpoint_a(rt: Path, work: Path) -> dict:
    neutral = work / "neutral-cwd"
    neutral.mkdir()
    os.chdir(neutral)
    sys.path.insert(0, str(rt))
    import mneme
    from mneme.integrations.claude_code.hook import _child_env
    from mneme.integrations.langchain import MnemeLangChain
    from langchain.agents.middleware.types import ToolCallRequest
    from langchain_core.messages import ToolMessage

    check("A", "import:in-process", "mneme imported from the pinned runtime root", True,
          Path(mneme.__file__).resolve().parent == (rt / "mneme").resolve())
    child = subprocess.run([sys.executable, "-c", "import mneme; print(mneme.__file__)"],
                           env=_child_env(), capture_output=True, text=True, cwd=neutral)
    check("A", "import:checker-subprocess", "checker subprocess imports the pinned runtime from a neutral cwd",
          True, Path(child.stdout.strip()).resolve().parent == (rt / "mneme").resolve())
    # O-3 is documented, not fixed: show it still holds from a cwd with a mneme/ package.
    shadow = subprocess.run([sys.executable, "-c", "import mneme; print(mneme.__file__)"],
                            env=_child_env(), capture_output=True, text=True, cwd=REPO)
    check("A", "O-3:shadowing", "from a cwd that contains a mneme/ package, the checker subprocess imports THAT package",
          True, Path(shadow.stdout.strip()).resolve().parent == (REPO / "mneme").resolve(),
          "O-3 reproduced as an observation; no runtime change")

    memory = git("cat-file", "blob", MEMORY_BLOB)
    out = {}

    def run(case, files, tool, args, target_rel):
        root = work / "pre" / case
        (root / ".mneme").mkdir(parents=True)
        (root / ".mneme/project_memory.json").write_bytes(memory)
        for rel, data in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(data)
        target = (root / target_rel).resolve()
        lc = MnemeLangChain(project_dir=str(root), mode="strict")
        mw = lc.build_middleware()[1]
        seen = {}
        orig = lc.evaluate_tool_call
        lc.evaluate_tool_call = lambda **kw: seen.setdefault("r", orig(**kw))
        calls = []

        def handler(request):
            calls.append(1)
            a = request.tool_call["args"]
            p = (root / a["file_path"]).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(a["content"].encode())
            return ToolMessage(content="written", tool_call_id=request.tool_call["id"])

        before = target.read_bytes() if target.exists() else None
        msg = mw.wrap_tool_call(ToolCallRequest(
            tool_call={"name": tool, "args": args, "id": f"s4-{case}", "type": "tool_call"},
            tool=None, state={}, runtime=None), handler)
        after = target.read_bytes() if target.exists() else None
        r = seen["r"]
        p = r.payload or {}
        app = [a for a in p.get("applicability", []) if a.get("decision_id") == "ADR-901"]
        out[case] = {
            "action": r.action, "verdict": r.verdict, "evaluation_complete": r.evaluation_complete,
            "payload_keys": sorted(p), "handler_called": bool(calls),
            "before": sha(before) if before is not None else None,
            "after": sha(after) if after is not None else None,
            "applicability": app[0].get("outcome") if app else None,
            "identity": [app[0].get(k) for k in ("decision_id", "decision_version_id", "rule_id")] if app else None,
            "marker": next((t for t in ("[mneme] DENIED", "[mneme] UNEVALUATED") if t in str(msg.content)), None),
        }
        return out[case], after

    c, written = run("A1", {"docs/readme.md": README}, "write_file",
                     {"file_path": "docs/guide.md", "content": ALLOW.decode()}, "docs/guide.md")
    check("A", "A1:allow", "neutral content is allowed, handler runs, file holds exactly the attempted bytes",
          {"action": "allow", "handler_called": True, "after": sha(ALLOW), "subject_in_payload": False},
          {"action": c["action"], "handler_called": c["handler_called"], "after": c["after"],
           "subject_in_payload": "subject" in c["payload_keys"]})
    c, _ = run("A2", {"docs/readme.md": README}, "write_file",
               {"file_path": "docs/install.md", "content": INSTALL.decode()}, "docs/install.md")
    check("A", "A2:deny", "forbidden new file is denied before the handler; target stays absent",
          {"action": "deny", "verdict": "FAIL", "handler_called": False, "after": None,
           "marker": "[mneme] DENIED", "applicability": "APPLIED"},
          {k: c[k] for k in ("action", "verdict", "handler_called", "after", "marker", "applicability")})
    check("A", "A2:no-subject", "the pre-mutation payload carries no subject record (dimension 2 not bound by Mneme)",
          False, "subject" in c["payload_keys"])
    out["identity_v0110"] = c["identity"]
    c, _ = run("A4", {"docs/readme.md": README}, "write_file",
               {"file_path": "../outside/notes.md", "content": INSTALL.decode()}, "../outside/notes.md")
    check("A", "A4:O-1", "target outside the policy root: UNKNOWN, fail_open, the forbidden write proceeds (O-1, unchanged)",
          {"action": "fail_open", "evaluation_complete": False, "applicability": "UNKNOWN",
           "handler_called": True, "after": sha(INSTALL), "marker": "[mneme] UNEVALUATED"},
          {k: c[k] for k in ("action", "evaluation_complete", "applicability", "handler_called", "after", "marker")})
    check("A", "A4:payload", "the checker DID run and returned a payload (so 'not executed' is a label, not a fact)",
          True, "applicability" in c["payload_keys"])
    out["A1_written"] = written
    return out


# ── 3. rebuild the CI fixture repo (different plumbing) ──────────────────────

def rebuild_fixture(repo: Path, guide: bytes) -> dict:
    git("init", "-q", "-b", "main", str(repo))
    memory = git("cat-file", "blob", MEMORY_BLOB)
    doc = json.loads(memory)
    doc.pop("decision_index")
    sectionless = (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode()

    def commit(files: dict, msg: str, parent: str | None = None) -> str:
        idx = repo / f".idx-{sha(msg.encode())[:8]}"
        env = {**os.environ, **GIT_ID, "GIT_INDEX_FILE": str(idx)}
        for path, (mode, data) in files.items():
            blob = gits("hash-object", "-w", "--stdin", cwd=repo, input_bytes=data)
            gits("update-index", "--add", "--cacheinfo", f"{mode},{blob},{path}", cwd=repo, env=env)
        tree = gits("write-tree", cwd=repo, env=env)
        idx.unlink()
        return gits("commit-tree", tree, "-m", msg, *(["-p", parent] if parent else []), cwd=repo, env=env)

    base = {".mneme/project_memory.json": ("100644", memory), "docs/readme.md": ("100644", README)}
    sb = {**base, ".mneme/project_memory.json": ("100644", sectionless)}
    b0 = commit(base, "fixture base: ADR-901 canonical memory")
    b0s = commit(sb, "fixture base: ADR-901 without decision_index")
    h1 = commit({**base, "docs/guide.md": ("100644", guide)}, "allowed change (A1 handler output)", b0)
    h2 = commit({**base, "docs/install.md": ("100644", INSTALL)}, "change that bypassed pre-mutation", b0)
    h3 = commit({**base, "docs/link.md": ("120000", b"readme.md")}, "symlink (non-regular entry)", b0)
    h4 = commit({**sb, "docs/install.md": ("100644", INSTALL)}, "violation under section-less memory", b0s)
    h5 = commit({**base, "docs/guide.md": ("100644", guide + STALE_SUFFIX)}, "later edit of docs/guide.md", h1)
    git("update-ref", "refs/heads/main", h5, cwd=repo)
    return {"B1_allow": (b0, h1, "docs/guide.md"), "B2_bypass_violation": (b0, h2, "docs/install.md"),
            "B3_incomplete_symlink": (b0, h3, "docs/link.md"), "B4_missing_identity": (b0s, h4, "docs/install.md"),
            "B5_later_revision": (h1, h5, "docs/guide.md")}


def raw_reports() -> dict:
    return {cid: json.loads((STEP3 / "ci-reports" / f"{cid}.gate-report.json").read_text(encoding="utf-8"))
            for cid in CASES}


def reports_vs_git(cases: dict, repo: Path, reports: dict) -> None:
    for cid, (base, head, path) in cases.items():
        r = reports[cid]
        f = r["files"][0]
        actual = {"base": r["base_sha"], "head": r["head_sha"], "merge_base": r["merge_base"],
                  "path": f["path"], "mode": f["mode"]}
        expected = {"base": base, "head": head, "merge_base": base, "path": path,
                    "mode": gits("ls-tree", head, "--", path, cwd=repo).split()[0]}
        if f.get("sha256") is not None:
            actual["file_sha256"] = f["sha256"]
            expected["file_sha256"] = sha(git("cat-file", "blob", f"{head}:{path}", cwd=repo))
        mem = r.get("memory")
        if mem is not None:
            blob = gits("rev-parse", f"{base}:.mneme/project_memory.json", cwd=repo)
            actual["memory"] = [mem["blob"], mem["source_commit"], mem["sha256"]]
            expected["memory"] = [blob, base, sha(git("cat-file", "blob", blob, cwd=repo))]
        check("F", f"{cid}:git-binding",
              "report SHAs, path, mode, content digest and memory blob agree with the independently rebuilt repo",
              expected, actual)
        check("F", f"{cid}:pins", "report carries the pinned adapter and evaluator",
              [ADAPTER_SHA256, PIN["evaluator_commit"], WHEEL_SHA256, "closed", "strict"],
              [r["adapter"]["sha256"], r["evaluator"]["commit"], r["evaluator"]["wheel_sha256"],
               r["posture"]["effective"], r["requested_mode"]])


# ── 4. fresh evaluator runs vs the reports' raw stdout ───────────────────────

# -E (not -I): the host keeps PyYAML in the user site. The runtime root is put
# first on sys.path and the imported package location is asserted.
BOOT = ("import os, runpy, sys; r = os.path.abspath(sys.argv[1]); sys.path.insert(0, r); import mneme; "
        "assert os.path.abspath(mneme.__file__).startswith(r), mneme.__file__; "
        "sys.argv = ['mneme.cli'] + sys.argv[2:]; runpy.run_module('mneme.cli', run_name='__main__')")


def fresh_check(code_root: Path, memory: bytes, rel: str, content: bytes, work: Path, tag: str) -> tuple:
    ws, empty = work / f"ws-{tag}", work / f"empty-{tag}"
    (ws / ".mneme").mkdir(parents=True)
    empty.mkdir()
    (ws / ".mneme/project_memory.json").write_bytes(memory)
    (ws / rel).parent.mkdir(parents=True, exist_ok=True)
    (ws / rel).write_bytes(content)
    target = ws / rel
    proc = subprocess.run([sys.executable, "-E", "-c", BOOT, str(code_root), "check",
                           "--memory", str(ws / ".mneme/project_memory.json"), "--input", str(target),
                           "--target-path", str(target), "--query", "adr033 c4 trusted gate",
                           "--mode", "strict", "--adr-dir", str(empty), "--json"],
                          cwd=empty, capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, proc.stdout


def fresh_runs(cases: dict, repo: Path, reports: dict, wheel_dir: Path, rt: Path, work: Path) -> None:
    for cid, (base, head, path) in cases.items():
        f = reports[cid]["files"][0]
        if f.get("stdout") is None:
            check("E", f"{cid}:not-evaluated", "the gate classified the entry before any evaluation",
                  "UNEVALUATED", f["classification"])
            continue
        memory = git("cat-file", "blob", f"{base}:.mneme/project_memory.json", cwd=repo)
        content = git("cat-file", "blob", f"{head}:{path}", cwd=repo)
        code, out = fresh_check(wheel_dir, memory, path, content, work, f"{cid}-0b74")
        check("E", f"{cid}:0b74d410-stdout", "a fresh 0b74d410 evaluator run reproduces the report's raw stdout and exit",
              [f["exit"], f["stdout"]], [code, out])
        code11, out11 = fresh_check(rt, memory, path, content, work, f"{cid}-v0110")
        p0, p1 = json.loads(f["stdout"]), json.loads(out11)
        ident = lambda p: [[a.get(k) for k in ("decision_id", "decision_version_id", "rule_id", "outcome")]
                           for a in p.get("applicability", [])]
        check("E", f"{cid}:v0.11.0-agrees", "v0.11.0 gives the same verdict, identity and applicability (this memory only)",
              [p0["verdict"], ident(p0), "subject" in p0], [p1["verdict"], ident(p1), "subject" in p1])


# ── 5. verify-report: committed reports and tamper probes ────────────────────

def verify(adapter: Path, report: dict | Path, base: str, head: str, adapter_exit: int, work: Path,
           posture: str = "closed", tag: str = "") -> tuple:
    if isinstance(report, dict):
        path = work / f"tampered-{tag}.json"
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    else:
        path = report
    proc = subprocess.run([sys.executable, "-I", str(adapter), "verify-report", "--report", str(path),
                           "--adapter-exit", str(adapter_exit), "--base-sha", base, "--head-sha", head,
                           "--mode", "strict", "--adapter-sha256", ADAPTER_SHA256,
                           "--evaluator-commit", PIN["evaluator_commit"],
                           "--evaluator-wheel-sha256", WHEEL_SHA256],
                          capture_output=True, text=True, env={**os.environ, "MNEME_CI_AVAILABILITY": posture})
    prefix = "::error title=ADR-033 C4 decision::"
    return proc.returncode, [l[len(prefix):] for l in proc.stdout.splitlines() if l.startswith(prefix)]


EXPECTED_DECISION = {  # step 3 record §4, the claims under test
    "B1_allow": (0, []), "B5_later_revision": (0, []),
    "B2_bypass_violation": (1, ["required check fails: VIOLATION under availability closed"]),
    "B3_incomplete_symlink": (1, ["required check fails: UNEVALUATED under availability closed"]),
    "B4_missing_identity": (1, ["required check fails: VIOLATION under availability closed"]),
}


def ci_authority(cases: dict, reports: dict, work: Path, adapter_exits: dict | None) -> None:
    adapter = work / "adr033_c4_gate.py"
    adapter.write_bytes(git("cat-file", "blob", ADAPTER_BLOB))
    for cid, (base, head, _) in cases.items():
        # Adapter exit: observed in this script's own container run when
        # available; otherwise the exit consistent with the report's disposition.
        exit_ = (adapter_exits or {}).get(cid, 0 if reports[cid]["disposition"] == "success" else 1)
        got = verify(adapter, STEP3 / "ci-reports" / f"{cid}.gate-report.json", base, head, exit_, work)
        check("C", f"{cid}:verify-report", "pinned adapter verify-report on the committed raw report: exit and exact problems",
              list(EXPECTED_DECISION[cid]), list(got),
              "adapter exit from own container run" if adapter_exits else "adapter exit from report disposition")
    b1, b2 = cases["B1_allow"], cases["B2_bypass_violation"]
    r1, r2 = reports["B1_allow"], reports["B2_bypass_violation"]

    def probe(pid, claim, report, base, head, exit_, expected, posture="closed"):
        check("C", f"tamper:{pid}", claim, list(expected),
              list(verify(adapter, report, base, head, exit_, work, posture, pid)))

    t = copy.deepcopy(r1); t["head_sha"] = b2[1]
    probe("head", "B1 report presented for another head: refused", t, *b1[:2], 0,
          (1, [f"report head_sha {b2[1]!r} != trusted {b1[1]!r}"]))
    probe("posture", "B1 report checked under trusted posture open: refused (posture mismatch)", r1, *b1[:2], 0,
          (1, ["report posture 'closed' != trusted posture 'open'"]), posture="open")
    t = copy.deepcopy(r1); t["evaluator"]["wheel_sha256"] = "0" * 64
    probe("wheel", "B1 report claiming another wheel: refused", t, *b1[:2], 0,
          (1, [f"report evaluator_wheel_sha256 {'0' * 64!r} != trusted {WHEEL_SHA256!r}"]))
    t = copy.deepcopy(r1); t["memory"]["blob"] = "0" * 40; t["memory"]["sha256"] = "0" * 64
    probe("memory", "B1 report with a different memory blob: ACCEPTED (verify-report does not bind configuration)",
          t, *b1[:2], 0, (0, []))
    t = copy.deepcopy(r1); t["files"][0]["sha256"] = "0" * 64
    probe("subject", "B1 report with a different file digest: ACCEPTED (verify-report does not bind the subject)",
          t, *b1[:2], 0, (0, []))
    t = copy.deepcopy(r2)
    t["files"][0].update(classification="VERIFIED_PASS", reason="PASS")
    t["aggregate"] = {"classification": "PASS", "reason": "all evaluated files passed",
                      "partly_unevaluated": False, "counts": {"VERIFIED_PASS": 1}}
    t["disposition"], t["annotations"] = "success", []
    probe("flip", "B2 report rewritten coherently to PASS while its raw stdout still says FAIL: ACCEPTED "
          "(verify-report recomputes from per-file classifications, not from evaluator output)",
          t, *b2[:2], 0, (0, []))


# ── 6. own CI replay in the pinned container ─────────────────────────────────

CONTAINER_SCRIPT = r"""
set -eu
W=/in/wheel/mneme_hq-0.10.0-py3-none-any.whl
test "$(sha256sum $W | cut -c1-64)" = "__WHEEL__"
test "$(sha256sum /in/adapter.py | cut -c1-64)" = "__ADAPTER__"
dpkg-query -W -f='${Package} ${Version}\n' git python3.12 python3.12-venv > /out/apt.txt
/usr/bin/python3.12 -I -m venv /tmp/evaluator
cp /in/req.txt /tmp/req.txt
echo "$W --hash=sha256:__WHEEL__" >> /tmp/req.txt
/tmp/evaluator/bin/python -I -m pip install -q --disable-pip-version-check --require-hashes --only-binary=:all: --no-deps -r /tmp/req.txt
/usr/bin/python3.12 --version > /out/python.txt
git config --global --add safe.directory '*'
while read -r cid base head; do
  set +e
  MNEME_CI_AVAILABILITY=closed /usr/bin/python3.12 -I /in/adapter.py evaluate --repo /fixture \
    --base-sha "$base" --head-sha "$head" --mode strict --workspace /tmp/ws-$cid --empty-dir /tmp/em-$cid \
    --venv-python /tmp/evaluator/bin/python --evaluator-commit __EVAL__ --evaluator-wheel-sha256 __WHEEL__ \
    --report /out/$cid.json --summary /out/$cid.md > /out/$cid.evaluate.log 2>&1
  e=$?
  MNEME_CI_AVAILABILITY=closed /usr/bin/python3.12 -I /in/adapter.py verify-report --report /out/$cid.json \
    --adapter-exit $e --base-sha "$base" --head-sha "$head" --mode strict --adapter-sha256 __ADAPTER__ \
    --evaluator-commit __EVAL__ --evaluator-wheel-sha256 __WHEEL__ --summary /out/$cid.md > /out/$cid.verify.log 2>&1
  v=$?
  MNEME_CI_AVAILABILITY=closed /usr/bin/python3.12 -I /in/adapter.py verify-report --report /committed/$cid.gate-report.json \
    --adapter-exit $e --base-sha "$base" --head-sha "$head" --mode strict --adapter-sha256 __ADAPTER__ \
    --evaluator-commit __EVAL__ --evaluator-wheel-sha256 __WHEEL__ > /out/$cid.verify-committed.log 2>&1
  c=$?
  set -e
  echo "$cid $e $v $c" >> /out/exits.txt
done < /in/cases.txt
"""


def json_diff(a, b, path="") -> list:
    """Paths where two JSON values differ (for a readable mismatch)."""
    if isinstance(a, dict) and isinstance(b, dict):
        return [d for k in sorted(set(a) | set(b)) for d in json_diff(a.get(k), b.get(k), f"{path}.{k}")]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in json_diff(x, y, f"{path}[{i}]")]
    return [] if a == b else [path or "."]


def own_container_replay(cases: dict, repo: Path, wheel: Path, work: Path) -> dict:
    inp, out = work / "c-in", work / "c-out"
    (inp / "wheel").mkdir(parents=True)
    out.mkdir()
    shutil.copy2(wheel, inp / "wheel" / "mneme_hq-0.10.0-py3-none-any.whl")
    shutil.copy2(REQUIREMENTS, inp / "req.txt")
    (inp / "adapter.py").write_bytes(git("cat-file", "blob", ADAPTER_BLOB))
    script = (CONTAINER_SCRIPT.replace("__WHEEL__", WHEEL_SHA256).replace("__ADAPTER__", ADAPTER_SHA256)
              .replace("__EVAL__", PIN["evaluator_commit"]))
    (inp / "run.sh").write_bytes(script.encode())
    (inp / "cases.txt").write_bytes("".join(f"{c} {b} {h}\n" for c, (b, h, _) in cases.items()).encode())
    cmd = ["docker", "run", "--rm", "-v", f"{repo}:/fixture", "-v", f"{inp}:/in:ro", "-v", f"{out}:/out",
           "-v", f"{STEP3 / 'ci-reports'}:/committed:ro", IMAGE, "bash", "-c",
           "apt-get update -qq >/dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "
           "git python3 python3-venv >/dev/null 2>&1 && bash /in/run.sh"]
    proc = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "MSYS_NO_PATHCONV": "1"})
    check("R", "container:ran", "own container replay completed", 0, proc.returncode,
          (proc.stdout + proc.stderr)[-400:] if proc.returncode else "")
    if proc.returncode:
        return {}
    exits = {l.split()[0]: [int(x) for x in l.split()[1:]] for l in (out / "exits.txt").read_text().splitlines()}
    check("R", "container:runtime", "gate Python and apt packages actually used (unpinned, recorded)",
          "Python 3.12.3", (out / "python.txt").read_text().strip(), (out / "apt.txt").read_text().strip())
    prefix = "::error title=ADR-033 C4 decision::"
    for cid in cases:
        mine = (out / f"{cid}.json").read_bytes()
        committed = (STEP3 / "ci-reports" / f"{cid}.gate-report.json").read_bytes()
        check("R", f"{cid}:byte-identical", "own container replay report is byte-identical to the committed raw report "
              "(venv path /tmp/evaluator/bin/python is a recorded input)",
              [sha(committed), []], [sha(mine), json_diff(json.loads(committed), json.loads(mine))])
        e, v, c = exits[cid]
        probs = [l[len(prefix):] for l in (out / f"{cid}.verify-committed.log").read_text().splitlines()
                 if l.startswith(prefix)]
        check("R", f"{cid}:verify-in-gate-python",
              "verify-report on the committed report, inside the pinned image with the gate's own Python",
              [EXPECTED_DECISION[cid][0], EXPECTED_DECISION[cid][0], EXPECTED_DECISION[cid][0],
               EXPECTED_DECISION[cid][1]], [e, v, c, probs])
    return {cid: exits[cid][0] for cid in cases}


# ── 7. hook path (step 2) through the shipped subprocess transport ───────────

def hook_path(rt: Path, work: Path) -> None:
    from mneme.integrations.claude_code import hook
    from mneme.numeric_rule import NumericContract
    from tests.canonical_fixtures import canonical_document

    check("H", "transport:default", "the hook's default check transport is subprocess (step 2 used inprocess)",
          "subprocess", (os.environ.pop("MNEME_HOOK_CHECK_TRANSPORT", None), hook.resolve_transport())[1])

    def memory(text="Router deadline at most 5 seconds (step 4)", max_="5", sectionless=False):
        value = NumericContract(max=max_, unit="seconds", symbol="ROUTER_DEADLINE_S",
                                call_function="classify", call_position=1).canonical_value()
        doc = {"meta": {"name": "step4", "description": "independent review"}, "items": [], "decisions": [
            {"id": "S4-LIT", "decision": "No requests library", "rationale": "r", "scope": ["net"],
             "rules": [{"type": "FORBID_LITERAL", "value": "import requests"}],
             "created_at": "2026-11-09", "updated_at": "2026-11-09", "status": "active"},
            {"id": "S4-NUM", "decision": text, "rationale": "r", "scope": ["router"],
             "rules": [{"type": "FORBID_NUMERIC_ABOVE", "value": value, "include_paths": ["src/**"]}],
             "created_at": "2026-11-09", "updated_at": "2026-11-09", "status": "active"}]}
        return doc if sectionless else canonical_document(doc)

    def project(name, doc) -> Path:
        root = work / "hook" / name
        (root / ".mneme").mkdir(parents=True)
        (root / "src").mkdir()
        (root / "docs").mkdir()
        (root / ".mneme/project_memory.json").write_text(json.dumps(doc, sort_keys=True), encoding="utf-8")
        return root

    def fire(root: Path, rel: str, content: str, tool="Write", tool_input=None):
        log = root.parent / f"{root.name}.jsonl"
        env = {"MNEME_HOOK_EVIDENCE_LOG": str(log), "MNEME_HOOK_EVIDENCE_HOST_VERSION": HOST[0],
               "MNEME_HOOK_EVIDENCE_HOST_SHA256": HOST[1], "MNEME_HOOK_MODE": "strict"}
        saved = {k: os.environ.get(k) for k in [*env, "MNEME_MEMORY", "CLAUDE_PLUGIN_OPTION_MODE"]}
        os.environ.update(env)
        os.environ.pop("MNEME_MEMORY", None)
        os.environ.pop("CLAUDE_PLUGIN_OPTION_MODE", None)
        try:
            rc = hook.handle_event({"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": str(root),
                                    "tool_input": tool_input or {"file_path": str(root / rel), "content": content},
                                    "session_id": "s4", "tool_use_id": "toolu_s4"},
                                   stderr=io.StringIO(), stdout=io.StringIO())
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        recs = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        return rc, (recs[0] if recs else None)

    def cli_identity(root: Path, content: str, rel: str) -> dict:
        carrier = root.parent / f"{root.name}-carrier.py"
        carrier.write_text(content, encoding="utf-8")
        proc = subprocess.run([sys.executable, "-E", "-c", BOOT, str(rt), "check", "--memory",
                               str(root / ".mneme/project_memory.json"), "--proposed-new-file", str(carrier),
                               "--target-path", str(root / rel), "--query", "step4", "--mode", "strict", "--json"],
                              cwd=work, capture_output=True, text=True, encoding="utf-8")
        p = json.loads(proc.stdout)
        num = [a for a in p["applicability"] if a.get("rule_type") == "FORBID_NUMERIC_ABOVE"][0]
        return {"rule_id": num["rule_id"], "decision_version_id": num["decision_version_id"],
                "outcome": num["outcome"], "subject_sha256": (p.get("subject") or {}).get("subject_sha256")}

    def dimensions(rec: dict, claim: dict) -> dict:
        """ADR-029 §2, read from the raw record fields only (reviewer's own reading)."""
        rule = next((r for r in rec.get("rules") or [] if r.get("rule_id") == claim["rule_id"]), None)
        subject = (rec.get("checker") or {}).get("subject") or {}
        return {
            "1_control_provenance": (rec.get("schema") == "mneme.hook_evidence/v1"
                                     and rec.get("surface") == "claude_code.PreToolUse"
                                     and rec.get("mneme_version") == claim["mneme_version"]
                                     and [rec["host"].get("version"), rec["host"].get("executable_sha256")] == list(HOST)
                                     and (rec.get("checker") or {}).get("trusted") is True),
            "2_subject": (rec.get("carrier_sha256") == claim["subject_sha256"]
                          and subject.get("subject_sha256") == claim["subject_sha256"]
                          and subject.get("absence_verified") is True
                          and rule is not None and rule.get("subject_sha256") == claim["subject_sha256"]),
            "3_decision": (rule is not None and rule["rule_id"].split(":", 1)[0] == claim["decision_id"]
                           and rule.get("decision_version_id") == claim["decision_version_id"]),
            "4_rule": rule is not None,
            "5_applicability": rule is not None and rule.get("applicability") == "APPLIED",
            "6_outcome": (rule is not None and rule.get("matcher_status") == "RECOGNIZED"
                          and ((rule.get("matcher_outcome") == "VIOLATION"
                                and rec.get("hook_outcome") == "refused"
                                and (rec.get("disposition") or {}).get("cause") == "numeric_violation"
                                and {"rule_id": claim["rule_id"], "rule_type": "FORBID_NUMERIC_ABOVE"}
                                in rec.get("violations", []))
                               or (rule.get("matcher_outcome") == "NO_VIOLATION"
                                   and rec.get("hook_outcome") == "proceeded"
                                   and (rec.get("disposition") or {}).get("cause") == "no_violation"))),
        }

    from mneme import __version__
    fn = lambda rec, host=HOST: hook.relevant_enforcement_per_rule(rec, host)

    # H1 positive: reject
    p1 = project("h1", memory())
    ident = cli_identity(p1, NUM_ABOVE, "src/new.py")
    rc, rec = fire(p1, "src/new.py", NUM_ABOVE)
    claim = {"decision_id": "S4-NUM", "decision_version_id": ident["decision_version_id"],
             "rule_id": ident["rule_id"], "subject_sha256": sha(NUM_ABOVE.encode()), "mneme_version": __version__}
    check("H", "H1:cli-cross-surface", "a fresh `mneme check --proposed-new-file` names the same rule, version and subject",
          [ident["rule_id"], ident["decision_version_id"], sha(NUM_ABOVE.encode())],
          [(rec["rules"] or [{}])[0].get("rule_id"), (rec["rules"] or [{}])[0].get("decision_version_id"),
           rec["carrier_sha256"]])
    check("H", "H1:dimensions", "subprocess-transport hook record binds all six dimensions for the numeric rule",
          {k: True for k in ("1_control_provenance", "2_subject", "3_decision", "4_rule", "5_applicability", "6_outcome")},
          dimensions(rec, claim))
    check("H", "H1:refusal", "the hook itself refused (exit 2) and the function agrees",
          [2, "refused", {claim["rule_id"]: True}], [rc, rec["hook_outcome"], fn(rec)])

    # H1b positive: allow (attributable per-rule allow exists only on this path)
    p = project("h1b", memory())
    rc, rec_ok = fire(p, "src/new.py", NUM_WITHIN)
    claim_ok = {**claim, "subject_sha256": sha(NUM_WITHIN.encode())}
    check("H", "H1b:allow", "numeric allow is attributable: all six dimensions, function True, write proceeds",
          [0, all(dimensions(rec_ok, claim_ok).values()), {claim["rule_id"]: True}],
          [rc, all(dimensions(rec_ok, claim_ok).values()), fn(rec_ok)])

    # N-2 and further consumer-side probes on the genuine H1 record
    v2 = cli_identity(project("v2", memory(text="Router deadline at most 5 seconds (step 4, revised)")),
                      NUM_ABOVE, "src/new.py")
    check("H", "N-2:setup", "a revised decision text keeps rule_id and changes decision_version_id",
          [True, True], [v2["rule_id"] == claim["rule_id"], v2["decision_version_id"] != claim["decision_version_id"]])

    def probe(pid, desc, record, c, fn_expected, dims_expected_all, host=HOST):
        got_fn = fn(record, host).get(c["rule_id"], False)
        d = dimensions(record, c)
        failing = sorted(k for k, v in d.items() if not v)
        check("H", pid, desc, [fn_expected, dims_expected_all], [got_fn, not failing],
              f"dimensions failing: {failing}" if failing else "")

    probe("N-2:wrong-version", "claim names V2; function alone says True, full-identity reading fails (dim 3)",
          rec, {**claim, "decision_version_id": v2["decision_version_id"]}, True, False)
    probe("N-2:stale-subject", "claim about later content; function alone says True, subject reading fails (dim 2)",
          rec, {**claim, "subject_sha256": sha(NUM_WITHIN.encode())}, True, False)
    t = copy.deepcopy(rec); t["rules"][0]["decision_version_id"] = "not-a-version-id"
    probe("N-2:malformed-version", "record version rewritten to a malformed value: function still True (non-empty check only)",
          t, claim, True, False)
    t = copy.deepcopy(rec); t["mneme_version"] = "0.0.0"
    probe("N-2:mneme-version", "record mneme_version rewritten: function still True (provenance version not compared)",
          t, claim, True, False)
    probe("N-2:host-pin", "consumer pins a different host: function False", rec, claim, False, True,
          host=("other-host", "ef" * 32))
    t = copy.deepcopy(rec); t["carrier_sha256"] = sha(b"x")
    probe("N-2:carrier", "carrier digest rewritten alone: function False (internal consistency check)",
          t, {**claim, "subject_sha256": sha(b"x")}, False, False)

    # Negative controls through the shipped transport
    p = project("missing_identity", memory(sectionless=True))
    rc, r = fire(p, "src/new.py", NUM_ABOVE)
    check("H", "C:missing-identity", "section-less memory with a numeric rule: untrusted record, no rules, proceeds (fail_open)",
          [0, False, [], "proceeded", "fail_open", {}],
          [rc, r["checker"]["trusted"], r["rules"], r["hook_outcome"], r["disposition"]["cause"], fn(r)])
    p = project("excluded", memory())
    rc, r = fire(p, "docs/new.py", NUM_ABOVE)
    excl = cli_identity(p, NUM_ABOVE, "docs/new.py")
    check("H", "C:excluded", "EXCLUDED numeric rule: CLI shows EXCLUDED, hook record has no rule entry, function {}",
          ["EXCLUDED", 0, [], "no_violation", {}],
          [excl["outcome"], rc, r["rules"], r["disposition"]["cause"], fn(r)])
    p = project("incomplete", memory())
    rc, r = fire(p, "src/new.py", NUM_DYNAMIC)
    check("H", "C:incomplete", "undecidable value: APPLIED + MATCHER_UNEVALUATED, proceeds fail_open, function False",
          [0, "APPLIED", "MATCHER_UNEVALUATED", "proceeded", "fail_open", {claim["rule_id"]: False}],
          [rc, r["rules"][0]["applicability"], r["rules"][0]["matcher_status"], r["hook_outcome"],
           r["disposition"]["cause"], fn(r)])
    p = project("literal", memory())
    rc, r = fire(p, "src/client.py", "import requests\n")
    check("H", "C:literal-ceiling",
          "literal violation via the hook (file also under the numeric rule's src/**): refused and attributed to the "
          "literal rule, which gets no rule entry; the co-applied numeric rule does not inherit relevance",
          [2, "refused", "other_rule", True, False, False],
          [rc, r["hook_outcome"], r["disposition"]["cause"],
           any(v["rule_id"].startswith("S4-LIT:") for v in r["violations"]),
           any(x["rule_id"].startswith("S4-LIT:") for x in r["rules"]), any(fn(r).values())],
          f"numeric entry present: {[(x['matcher_status'], x['primary_reason']) for x in r['rules']]}")
    p = project("edit", memory())
    (p / "src/old.py").write_text("X = 1\n", encoding="utf-8")
    rc, r = fire(p, "src/old.py", "", tool="Edit",
                 tool_input={"file_path": str(p / "src/old.py"), "old_string": "X = 1",
                             "new_string": "ROUTER_DEADLINE_S = 45"})
    check("H", "C:edit-scope", "numeric content via Edit of an existing file: no relevance (E-1 is new-file Write only); "
          "observed: the edit proceeds and no evidence record is written",
          [False, 0, False], [any((fn(r) if r else {}).values()), rc, r is not None],
          f"hook exit {rc}, outcome {(r or {}).get('hook_outcome')}, cause {((r or {}).get('disposition') or {}).get('cause')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runtime-root", required=True, type=Path)
    ap.add_argument("--approved-wheel", required=True, type=Path)
    ap.add_argument("--container", action="store_true", help="also run the pinned-image checks (Docker, network)")
    a = ap.parse_args()
    rt = a.runtime_root.resolve()
    work = Path(tempfile.mkdtemp(prefix="mneme-step4-"))
    SCRUB.extend([str(work), str(work.resolve()), str(rt), str(REPO)])
    wheel_dir = pins(rt, a.approved_wheel.resolve(), a.container, work)
    pre = checkpoint_a(rt, work)
    repo = work / "fixture"
    cases = rebuild_fixture(repo, pre.pop("A1_written"))
    reports = raw_reports()
    reports_vs_git(cases, repo, reports)
    first = reports["B1_allow"]["files"][0]["stdout"]
    v0b = json.loads(first)["applicability"][0]
    check("F", "identity:cross-evaluator", "checkpoint A (v0.11.0) and the CI report (0b74d410) name the same full identity",
          pre["identity_v0110"], [v0b["decision_id"], v0b["decision_version_id"], v0b["rule_id"]])
    fresh_runs(cases, repo, reports, wheel_dir, rt, work)
    exits = own_container_replay(cases, repo, a.approved_wheel.resolve(), work) if a.container else None
    ci_authority(cases, reports, work, exits)
    hook_path(rt, work)

    os.chdir(REPO)
    failed = [c["id"] for c in CHECKS if not c["ok"]]
    result = {"runtime_mneme_tree": gits("rev-parse", "HEAD:mneme", cwd=rt), "container": a.container,
              "python": sys.version.split()[0], "checks": CHECKS,
              "summary": {"checks": len(CHECKS), "ok": len(CHECKS) - len(failed), "failed": failed}}
    with open(HERE / "checks.json", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    for c in CHECKS:
        print(f"{c['section']:2} {'ok ' if c['ok'] else 'BAD'} {c['id']:34} {c['claim'][:90]}")
    print(json.dumps(result["summary"]))
    shutil.rmtree(work, ignore_errors=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

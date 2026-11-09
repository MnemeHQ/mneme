"""Verification step 3: frozen end-to-end fixture, two checkpoints.

Checkpoint A, pre-mutation: v0.11.0 (``619d5405``) through LangChain's real
``ToolGateMiddleware`` with a local file-writing handler. The handler runs
only if the middleware lets it, so non-mutation is observed on disk.

Checkpoint B, CI: offline Gate 2-style replay of the C4 trusted-gate adapter
(``c51729f7``) with the approved evaluator wheel (``0b74d410``, sha256
``e3fcc769...``) in the pinned ``ubuntu:24.04`` container (``ci_replay.sh``).
It is NOT a GitHub Actions observation, and its results are ``0b74d410``
evidence, never v0.11.0 evidence.

Verification then assesses what each checkpoint's evidence proves, with the
full ``(decision_id, decision_version_id, rule_id)`` identity and distinct
subject digests (Step 2 N-2: ``rule_id`` alone is never enough).

Fixture: decision ``ADR-901``, ``FORBID_LITERAL "install legacy-client"`` in
``docs/**`` excluding ``docs/history/**``; memory blob ``4c669436``
(``docs/integrations/c4-gate/project_memory.example.json``).

Run from the repository root (Windows host with Docker, or any host with
Docker and git):

    git worktree add --detach ../mneme-619d5405 619d5405
    python docs/validation/artifacts/verification-step3-e2e-fixture/run_step3.py \\
        --runtime-root ../mneme-619d5405 \\
        --approved-wheel <path to mneme_hq-0.10.0-py3-none-any.whl, sha256 e3fcc769...>

The approved wheel is not republished here (see the C4 Gate 2 record). The
harness refuses to run if the runtime root, the memory blob, the adapter or
the wheel differs from its pin (exit 2), and exits 1 if any case misses its
expected observations or evidence level.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]

RUNTIME_TAG = "v0.11.0"
MEMORY_BLOB = "4c669436199643458ae11fe7991ccfaa5b1a6e03"
ADAPTER_COMMIT = "c51729f78199203fe12fcbc5c678b89a2c4f7d3e"
ADAPTER_PATH = "scripts/ci/adr033_c4_gate.py"
ADAPTER_BLOB = "5feedf60ce1a67b2bb85673354c8b8b367a87d06"
ADAPTER_SHA256 = "afe1d69c1ce4170875989c5866bb2ec7b5089fc895efa699ced826317e3777f9"
EVALUATOR_COMMIT = "0b74d410b45e7b3efcf08d00ce58e7bd7017b757"
APPROVED_WHEEL_SHA256 = "e3fcc769c440ed232ad05117f256739daf233e0c9f6d3d46586adc0de9b48c51"
IMAGE = ("ubuntu@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac")
REQUIREMENTS = REPO / "docs/validation/adr033-c4-gate2-offline-2026-10-26/inputs/evaluator-requirements.txt"

DECISION_ID = "ADR-901"
FORBIDDEN = "install legacy-client"
NOT_EXECUTED, EXECUTION, RELEVANT = "not_executed", "execution_observed", "relevant_enforcement_observed"
ORDER = {NOT_EXECUTED: 0, EXECUTION: 1, RELEVANT: 2}

ALLOW_TEXT = "# Guide\n\nInstall the current client with the documented installer.\n"
DENY_TEXT = "# Install\n\nRun install legacy-client to get started.\n"
README_TEXT = "# Project readme\n"
STALE_TEXT = ALLOW_TEXT + "\nA later edit that pre-mutation never checked.\n"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args, cwd=None, input_bytes=None, env=None) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, input=input_bytes,
                          capture_output=True, check=True, env=env)
    return proc.stdout.decode().strip()


def refuse(msg: str) -> None:
    print(f"REFUSED: {msg}", file=sys.stderr)
    raise SystemExit(2)


# ── pins ─────────────────────────────────────────────────────────────────────

def check_pins(runtime_root: Path, wheel: Path) -> dict:
    commit = git("rev-parse", f"{RUNTIME_TAG}^{{commit}}", cwd=REPO)
    if git("rev-parse", "HEAD", cwd=runtime_root) != commit:
        refuse(f"runtime root is not {RUNTIME_TAG} ({commit[:8]})")
    dirty = git("status", "--porcelain", "--untracked-files=all", "--", "mneme", cwd=runtime_root)
    if dirty:
        refuse(f"runtime root has local changes under mneme/: {dirty.splitlines()[:3]}")
    if git("hash-object", "docs/integrations/c4-gate/project_memory.example.json", cwd=REPO) != MEMORY_BLOB:
        refuse("fixture memory is not blob 4c669436")
    if git("rev-parse", f"{ADAPTER_COMMIT}:{ADAPTER_PATH}", cwd=REPO) != ADAPTER_BLOB:
        refuse("adapter blob differs from the pin")
    if not wheel.is_file() or sha(wheel.read_bytes()) != APPROVED_WHEEL_SHA256:
        refuse("approved wheel missing or sha256 differs from e3fcc769...")
    return {"runtime_tag": RUNTIME_TAG, "runtime_commit": commit, "memory_blob": MEMORY_BLOB,
            "adapter_commit": ADAPTER_COMMIT, "adapter_blob": ADAPTER_BLOB,
            "adapter_sha256": ADAPTER_SHA256, "evaluator_commit": EVALUATOR_COMMIT,
            "evaluator_wheel_sha256": APPROVED_WHEEL_SHA256, "container_image": IMAGE}


def memory_bytes(sectionless: bool = False) -> bytes:
    data = subprocess.run(["git", "cat-file", "blob", MEMORY_BLOB], cwd=REPO,
                          capture_output=True, check=True).stdout
    if not sectionless:
        return data
    doc = json.loads(data)
    doc.pop("decision_index")
    return (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode()


# ── checkpoint A: pre-mutation (LangChain middleware, v0.11.0) ───────────────

def premutation(runtime_root: Path, work: Path) -> dict:
    # The checker subprocess (`python -m mneme check`) puts its working
    # directory first on sys.path, ahead of _child_env's PYTHONPATH. Run from
    # a neutral directory so a `mneme/` package in the caller's cwd (for
    # example this repository) cannot shadow the pinned runtime.
    os.chdir(work)
    sys.path.insert(0, str(runtime_root))
    import mneme
    from mneme.integrations.claude_code.hook import _child_env
    from mneme.integrations.langchain import MnemeLangChain
    from langchain.agents.middleware.types import ToolCallRequest
    from langchain_core.messages import ToolMessage

    if Path(mneme.__file__).resolve().parent != (runtime_root / "mneme").resolve():
        refuse(f"mneme imported from {mneme.__file__}")
    child = subprocess.run([sys.executable, "-c", "import mneme; print(mneme.__file__)"],
                           env=_child_env(), capture_output=True, text=True, check=True)
    if Path(child.stdout.strip()).resolve().parent != (runtime_root / "mneme").resolve():
        refuse(f"checker subprocess would import {child.stdout.strip()}")

    import langchain
    out = {"mneme_version": mneme.__version__, "langchain_version": langchain.__version__,
           "checker_subprocess_runtime": "pinned root (verified)", "cases": {}}

    def project(name: str, sectionless=False) -> Path:
        root = work / "premutation" / name
        (root / ".mneme").mkdir(parents=True)
        (root / ".mneme" / "project_memory.json").write_bytes(memory_bytes(sectionless))
        (root / "docs").mkdir()
        (root / "docs" / "readme.md").write_bytes(README_TEXT.encode())
        return root

    def run(case_id, root: Path, tool: str, args: dict, target: Path):
        lc = MnemeLangChain(project_dir=str(root), mode="strict")
        gate_mw = lc.build_middleware()[1]
        captured = {}
        real = lc.evaluate_tool_call

        def recording(**kw):  # observation only; returns the real result
            captured["result"] = real(**kw)
            return captured["result"]
        lc.evaluate_tool_call = recording

        calls = []

        def handler(request):  # the local file-writing tool
            calls.append(request.tool_call["name"])
            a = request.tool_call["args"]
            path = root / a["file_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            if request.tool_call["name"] == "write_file":
                path.write_bytes(a["content"].encode())
            else:
                text = path.read_bytes().decode()
                path.write_bytes(text.replace(a["old_string"], a["new_string"], 1).encode())
            return ToolMessage(content="ok", tool_call_id=request.tool_call["id"])

        before = target.read_bytes() if target.exists() else None
        request = ToolCallRequest(
            tool_call={"name": tool, "args": args, "id": f"call-{case_id}", "type": "tool_call"},
            tool=None, state={}, runtime=None)
        message = gate_mw.wrap_tool_call(request, handler)
        after = target.read_bytes() if target.exists() else None
        r = captured["result"]
        p = r.payload or {}
        applic = [a for a in p.get("applicability", []) if a.get("decision_id") == DECISION_ID]
        viol = [v for v in p.get("violations", []) if v.get("decision_id") == DECISION_ID]
        introduced = args.get("content", args.get("new_string", ""))
        out["cases"][case_id] = {
            "tool": tool, "target": target.relative_to(work).as_posix(),
            "action": r.action, "verdict": r.verdict,
            "evaluation_complete": r.evaluation_complete,
            "payload_present": r.payload is not None,
            "payload_has_subject": "subject" in p,
            "applicability": applic[0]["outcome"] if applic else None,
            "identity": ({k: applic[0].get(k) for k in ("decision_id", "decision_version_id", "rule_id")}
                         if applic else None),
            "violation_rule_ids": [v.get("rule_id") for v in viol],
            "handler_called": bool(calls),
            "target_before_sha256": sha(before) if before is not None else None,
            "target_after_sha256": sha(after) if after is not None else None,
            "tool_result_marker": ("[mneme] DENIED" if "[mneme] DENIED" in str(message.content)
                                   else "[mneme] UNEVALUATED" if "[mneme] UNEVALUATED" in str(message.content)
                                   else None),
            # Harness-computed: Mneme emits no subject digest for literal-only
            # checks (#761 E-2). This is the attempted action's content.
            "attempted_content_sha256": sha(introduced.encode()),
            "attempted_content": introduced,
        }

    p = project("allow")
    run("A1_allow", p, "write_file", {"file_path": "docs/guide.md", "content": ALLOW_TEXT},
        p / "docs" / "guide.md")
    p = project("deny_new")
    run("A2_deny_new_file", p, "write_file", {"file_path": "docs/install.md", "content": DENY_TEXT},
        p / "docs" / "install.md")
    p = project("deny_existing")
    run("A3_deny_existing_file", p, "edit_file",
        {"file_path": "docs/readme.md", "old_string": "# Project readme",
         "new_string": "# Project readme\n\nRun install legacy-client first."},
        p / "docs" / "readme.md")
    p = project("incomplete")
    run("A4_incomplete", p, "write_file", {"file_path": "../outside/notes.md", "content": DENY_TEXT},
        work / "premutation" / "outside" / "notes.md")
    p = project("missing_identity", sectionless=True)
    run("A5_missing_identity", p, "write_file", {"file_path": "docs/install.md", "content": DENY_TEXT},
        p / "docs" / "install.md")
    return out


# ── fixture repo for checkpoint B (git plumbing: deterministic SHAs) ─────────

GIT_ENV = {"GIT_AUTHOR_NAME": "Verification Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "Verification Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
           "GIT_AUTHOR_DATE": "2026-11-09T00:00:00+0000", "GIT_COMMITTER_DATE": "2026-11-09T00:00:00+0000"}


def build_fixture_repo(repo: Path, allow_bytes: bytes) -> dict:
    env = {**os.environ, **GIT_ENV}
    git("init", "-q", "-b", "main", str(repo))

    def blob(data: bytes) -> str:
        return git("hash-object", "-w", "--stdin", cwd=repo, input_bytes=data)

    def tree(files: dict) -> str:
        """files: {path: (mode, bytes)} -> tree sha (nested via mktree)."""
        entries, subdirs = [], {}
        for path, (mode, data) in files.items():
            head, _, rest = path.partition("/")
            if rest:
                subdirs.setdefault(head, {})[rest] = (mode, data)
            else:
                entries.append(f"{mode} blob {blob(data)}\t{head}")
        for name, sub in subdirs.items():
            entries.append(f"040000 tree {tree(sub)}\t{name}")
        return git("mktree", cwd=repo, input_bytes=("\n".join(sorted(entries, key=lambda e: e.split('\t')[1])) + "\n").encode())

    def commit(files: dict, msg: str, parent: str | None = None) -> str:
        args = ["commit-tree", tree(files), "-m", msg]
        if parent:
            args += ["-p", parent]
        return git(*args, cwd=repo, env=env)

    base_files = {".mneme/project_memory.json": ("100644", memory_bytes()),
                  "docs/readme.md": ("100644", README_TEXT.encode())}
    b0 = commit(base_files, "fixture base: ADR-901 canonical memory")
    sb_files = {**base_files, ".mneme/project_memory.json": ("100644", memory_bytes(sectionless=True))}
    b0s = commit(sb_files, "fixture base: ADR-901 without decision_index")
    h_allow = commit({**base_files, "docs/guide.md": ("100644", allow_bytes)},
                     "allowed change (A1 handler output)", b0)
    h_bypass = commit({**base_files, "docs/install.md": ("100644", DENY_TEXT.encode())},
                      "change that bypassed pre-mutation", b0)
    h_link = commit({**base_files, "docs/link.md": ("120000", b"readme.md")},
                    "symlink (non-regular entry)", b0)
    h_missing = commit({**sb_files, "docs/install.md": ("100644", DENY_TEXT.encode())},
                       "violation under section-less memory", b0s)
    h_stale = commit({**base_files, "docs/guide.md": ("100644", STALE_TEXT.encode())},
                     "later edit of docs/guide.md", h_allow)
    git("update-ref", "refs/heads/main", h_stale, cwd=repo)
    return {
        "B1_allow": (b0, h_allow), "B2_bypass_violation": (b0, h_bypass),
        "B3_incomplete_symlink": (b0, h_link), "B4_missing_identity": (b0s, h_missing),
        "B5_later_revision": (h_allow, h_stale),
    }


# ── checkpoint B: offline CI replay ──────────────────────────────────────────

def ci_replay(cases: dict, repo: Path, wheel: Path, work: Path) -> dict:
    inp, out = work / "ci-in", work / "ci-out"
    inp.mkdir()
    out.mkdir()
    shutil.copy2(wheel, inp / "mneme_hq-0.10.0-py3-none-any.whl")
    shutil.copy2(REQUIREMENTS, inp / "evaluator-requirements.txt")
    adapter = subprocess.run(["git", "cat-file", "blob", ADAPTER_BLOB], cwd=REPO,
                             capture_output=True, check=True).stdout
    (inp / "adr033_c4_gate.py").write_bytes(adapter)
    shutil.copy2(HERE / "ci_replay.sh", inp / "ci_replay.sh")
    with open(inp / "cases.tsv", "w", encoding="utf-8", newline="\n") as fh:
        for cid, (base, head) in cases.items():
            fh.write(f"{cid}\t{base}\t{head}\n")
    cmd = ["docker", "run", "--rm",
           "-v", f"{repo}:/fixture", "-v", f"{inp}:/in:ro", "-v", f"{out}:/out", IMAGE,
           "bash", "-c",
           "apt-get update -qq >/dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "
           "git python3 python3-venv >/dev/null 2>&1 && tr -d '\\r' < /in/ci_replay.sh > /tmp/r.sh && bash /tmp/r.sh"]
    proc = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "MSYS_NO_PATHCONV": "1"})
    (work / "ci-console.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        refuse(f"CI replay container failed ({proc.returncode}); see {work / 'ci-console.log'}")
    pins = dict(line.split(" ", 1) for line in (out / "pins.txt").read_text().splitlines())
    result = {"pins": pins, "cases": {}}
    for cid, (base, head) in cases.items():
        d = out / cid
        report = json.loads((d / "gate-report.json").read_text(encoding="utf-8"))
        exits = json.loads((d / "exit.json").read_text())
        files = []
        for f in report.get("files", []):
            payload = None
            if f.get("stdout"):
                try:
                    payload = json.loads(f["stdout"])
                except json.JSONDecodeError:
                    payload = None
            applic = [a for a in (payload or {}).get("applicability", [])
                      if a.get("decision_id") == DECISION_ID]
            files.append({
                "path": f.get("path"), "classification": f.get("classification"),
                "kind": f.get("kind"), "content_sha256": f.get("sha256"),
                "payload_has_subject": "subject" in (payload or {}),
                "verdict": (payload or {}).get("verdict"),
                "evaluation_complete": (payload or {}).get("evaluation_complete"),
                "applicability": applic[0]["outcome"] if applic else None,
                "identity": ({k: applic[0].get(k) for k in ("decision_id", "decision_version_id", "rule_id")}
                             if applic else None),
            })
        result["cases"][cid] = {
            "base_sha": base, "head_sha": head,
            "report_base_sha": report.get("base_sha"), "report_head_sha": report.get("head_sha"),
            "memory": report.get("memory"), "posture": report.get("posture"),
            "aggregate": (report.get("aggregate") or {}).get("classification"),
            "disposition": report.get("disposition"),
            "adapter_exit": exits["adapter_exit"], "verify_exit": exits["verify_exit"],
            "files": files,
        }
        shutil.copy2(d / "gate-report.json", HERE / "ci-reports" / f"{cid}.gate-report.json")
    shutil.copy2(out / "pins.txt", HERE / "ci-reports" / "pins.txt")
    return result


# ── verification: what does the evidence prove? ──────────────────────────────

def identity_complete(ident) -> bool:
    return bool(ident and ident.get("decision_id") and ident.get("rule_id", "").startswith(
        ident["decision_id"] + ":") and str(ident.get("decision_version_id", "")).startswith("dver-"))


def level_pre(c: dict) -> str:
    """Evidence level of one pre-mutation observation, from its own fields.

    Not executed when nothing was evaluated (fail_open, skip, no trusted
    payload). Relevant only if Mneme itself bound the subject (dimension 2)
    on top of complete identity and APPLIED applicability; literal-only
    payloads carry no subject record (#761 E-2), so they stop at execution.
    """
    if not c["payload_present"] or c["action"] in ("fail_open", "skip"):
        return NOT_EXECUTED
    if c["payload_has_subject"] and identity_complete(c["identity"]) and c["applicability"] == "APPLIED":
        return RELEVANT
    return EXECUTION


def level_ci(f: dict | None) -> str:
    """Evidence level of one CI file record, from its own fields."""
    if f is None or f["classification"] in ("UNEVALUATED", "REFUSED", "SKIP") or f["verdict"] is None:
        return NOT_EXECUTED
    if f["payload_has_subject"] and identity_complete(f["identity"]) and f["applicability"] == "APPLIED":
        return RELEVANT
    return EXECUTION


def weakest(*levels: str) -> str:
    return min(levels, key=ORDER.get)


def linkage(pre: dict, ci_file: dict | None) -> dict:
    """Cross-checkpoint claim: CI evaluated exactly what pre-mutation allowed,
    under the same full identity. Literal rules: execution observed at most."""
    if ci_file is None:
        return {"established": False, "reason": "no CI file for this subject"}
    same_identity = (identity_complete(pre["identity"]) and identity_complete(ci_file["identity"])
                     and pre["identity"] == ci_file["identity"])
    same_subject = pre["attempted_content_sha256"] == ci_file["content_sha256"]
    return {"established": same_identity and same_subject, "same_full_identity": same_identity,
            "same_subject_digest": same_subject}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runtime-root", required=True, type=Path)
    ap.add_argument("--approved-wheel", required=True, type=Path)
    args = ap.parse_args()
    runtime_root = args.runtime_root.resolve()
    pins = check_pins(runtime_root, args.approved_wheel.resolve())

    work = Path(tempfile.mkdtemp(prefix="mneme-step3-"))
    (HERE / "ci-reports").mkdir(exist_ok=True)
    pre = premutation(runtime_root, work)
    a1 = pre["cases"]["A1_allow"]
    allow_bytes = (work / a1["target"]).read_bytes()
    repo = work / "fixture-repo"
    cases = build_fixture_repo(repo, allow_bytes)
    ci = ci_replay(cases, repo, args.approved_wheel.resolve(), work)

    def ci_file(cid, path):
        return next((f for f in ci["cases"][cid]["files"] if f["path"] == path), None)

    checks = []

    def check(cid, title, level, expect: dict, observed: dict, negative=True):
        ok = {k: {"expected": v, "actual": observed.get(k), "ok": observed.get(k) == v}
              for k, v in expect.items()}
        level_ok = ORDER[level["actual"]] <= ORDER[level["max"]] if negative else level["actual"] == level["max"]
        checks.append({"id": cid, "title": title, "evidence_level": level, "level_ok": level_ok,
                       "observations": ok, "pass": level_ok and all(c["ok"] for c in ok.values())})

    A, B = pre["cases"], ci["cases"]
    v1 = A["A1_allow"]["identity"]
    def lvl(actual: str, max_: str = EXECUTION) -> dict:
        return {"max": max_, "actual": actual}

    # 1. Allow
    check("V1_allow_premutation", "Allowed content reaches the handler and the file is written",
          lvl(level_pre(A["A1_allow"])), {"action": "allow", "verdict": "PASS", "applicability": "APPLIED",
                           "payload_has_subject": False,
                           "handler_called": True, "identity_complete": True,
                           "target_after_matches_content": True},
          {**A["A1_allow"], "identity_complete": identity_complete(v1),
           "target_after_matches_content": A["A1_allow"]["target_after_sha256"] == A["A1_allow"]["attempted_content_sha256"]})
    b1 = ci_file("B1_allow", "docs/guide.md")
    check("V1_allow_ci", "CI independently evaluates the resulting revision", lvl(level_ci(b1)),
          {"payload_has_subject": False, "aggregate": "PASS", "disposition": "success", "classification": "VERIFIED_PASS",
           "applicability": "APPLIED", "identity_complete": True, "head_matches_report": True},
          {**B["B1_allow"], **(b1 or {}), "identity_complete": identity_complete((b1 or {}).get("identity")),
           "head_matches_report": B["B1_allow"]["report_head_sha"] == B["B1_allow"]["head_sha"]})
    link = linkage(A["A1_allow"], b1)
    check("V1_allow_linkage", "Same full identity and same subject digest across checkpoints",
          lvl(weakest(level_pre(A["A1_allow"]), level_ci(b1))), {"established": True, "same_full_identity": True, "same_subject_digest": True},
          link)

    # 2. Deny with observed non-mutation
    for cid in ("A2_deny_new_file", "A3_deny_existing_file"):
        c = A[cid]
        check(f"V2_{cid}", "Prohibited content rejected; handler not called; target unchanged",
              lvl(level_pre(c)), {"action": "deny", "verdict": "FAIL", "applicability": "APPLIED",
                               "handler_called": False, "target_unchanged": True,
                               "tool_result_marker": "[mneme] DENIED",
                               "violation_rule_ids": [v1["rule_id"]], "identity_complete": True},
              {**c, "target_unchanged": c["target_before_sha256"] == c["target_after_sha256"],
               "identity_complete": identity_complete(c["identity"])})
    b2 = ci_file("B2_bypass_violation", "docs/install.md")
    check("V2_ci_catches_bypass", "Content that bypassed pre-mutation is a CI violation", lvl(level_ci(b2)),
          {"aggregate": "VIOLATION", "disposition": "failure", "classification": "VIOLATION", "applicability": "APPLIED",
           "identity_complete": True, "same_subject_as_denied_attempt": True},
          {**B["B2_bypass_violation"], **(b2 or {}),
           "identity_complete": identity_complete((b2 or {}).get("identity")),
           "same_subject_as_denied_attempt": (b2 or {}).get("content_sha256") == A["A2_deny_new_file"]["attempted_content_sha256"]})

    # 3. Incomplete evaluation
    c = A["A4_incomplete"]
    check("V3_incomplete_premutation", "Path outside the policy root: UNKNOWN, reported UNEVALUATED",
          lvl(level_pre(c), NOT_EXECUTED),
          {"action": "fail_open", "evaluation_complete": False, "applicability": "UNKNOWN",
           "tool_result_marker": "[mneme] UNEVALUATED", "handler_called": True},
          c)
    b3 = ci_file("B3_incomplete_symlink", "docs/link.md")
    check("V3_incomplete_ci", "Non-regular entry: UNEVALUATED, fails closed under posture closed",
          lvl(level_ci(b3), NOT_EXECUTED),
          {"aggregate": "UNEVALUATED", "disposition": "failure", "classification": "UNEVALUATED"}, {**B["B3_incomplete_symlink"], **(b3 or {})})

    # 4. Missing identity
    c = A["A5_missing_identity"]
    check("V4_missing_identity_premutation", "Section-less memory: still denied, identity incomplete",
          lvl(level_pre(c)), {"action": "deny", "handler_called": False, "identity_complete": False,
                           "decision_version_id": ""},
          {**c, "identity_complete": identity_complete(c["identity"]),
           "decision_version_id": (c["identity"] or {}).get("decision_version_id")})
    b4 = ci_file("B4_missing_identity", "docs/install.md")
    check("V4_missing_identity_ci", "Section-less memory at CI: violation, identity incomplete",
          lvl(level_ci(b4)), {"aggregate": "VIOLATION", "disposition": "failure", "identity_complete": False},
          {**B["B4_missing_identity"], "identity_complete": identity_complete((b4 or {}).get("identity"))})
    check("V4_missing_identity_linkage", "No cross-checkpoint claim without complete identity",
          lvl(weakest(level_pre(c), level_ci(b4))), {"established": False, "same_full_identity": False},
          linkage(c, b4))

    # 5. Stale evidence
    b5 = ci_file("B5_later_revision", "docs/guide.md")
    link5 = linkage(A["A1_allow"], b5)
    check("V5_stale_reuse", "A1 pre-mutation evidence cannot verify a later revision of the file",
          lvl(weakest(level_pre(A["A1_allow"]), level_ci(b5))), {"established": False, "same_full_identity": True,
                           "same_subject_digest": False}, link5)
    check("V5_stale_ci_head", "B1 CI evidence is bound to its head, not the later one", lvl(level_ci(b1)),
          {"different_head": True},
          {"different_head": B["B1_allow"]["head_sha"] != B["B5_later_revision"]["head_sha"]})

    for c in A.values():
        c.pop("attempted_content", None)
    results = {"pins": pins, "premutation": pre, "ci": ci, "verification": checks,
               "summary": {"checks": len(checks), "passed": sum(c["pass"] for c in checks),
                           "failed": [c["id"] for c in checks if not c["pass"]]}}
    with open(HERE / "results.json", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(results, indent=2, sort_keys=True) + "\n")
    for c in checks:
        bad = [k for k, v in c["observations"].items() if not v["ok"]]
        print(f"{c['id']:34} {'PASS' if c['pass'] else 'FAIL'}  level={c['evidence_level']['actual']}"
              f"{'  MISMATCH ' + str(bad) if bad else ''}")
    print(json.dumps(results["summary"]))
    return 0 if not results["summary"]["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

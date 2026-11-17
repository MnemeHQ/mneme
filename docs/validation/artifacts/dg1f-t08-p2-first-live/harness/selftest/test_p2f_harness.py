"""Offline self-tests for the T-08 P2-first live harness (no Claude Code).

Run: python -m pytest docs/validation/artifacts/dg1f-t08-p2-first-live/harness/selftest -q

They never touch the fixed live root: every layout lives in pytest's tmp_path,
and safe_rmtree is exercised only through its refusals.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1]
REPO = HARNESS.parents[4]
PY = sys.executable

sys.path.insert(0, str(HARNESS))
import classify_p2f  # noqa: E402


def _setup(tmp_path, name, kind, *extra):
    out = subprocess.run([PY, "-I", str(HARNESS / "setup_probe.py"), str(tmp_path / name), kind,
                          str(HARNESS / "hookwrap_v4.py"), PY, *extra],
                         capture_output=True, text=True, check=True)
    return Path(out.stdout.strip())


def _wrap(repo, envelope, log, override=None):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("MNEME_") and k != "CLAUDE_PLUGIN_OPTION_MODE"}
    env.update(T08_MNEME_SRC=str(REPO), T08_LOG=str(log), PYTHONPATH=str(REPO))
    if override:
        env["MNEME_MEMORY"] = override
    return subprocess.run([PY, str(HARNESS / "hookwrap_v4.py")], input=json.dumps(envelope),
                          capture_output=True, text=True, env=env, cwd=str(repo))


def _edit(repo, target, new):
    return {"hook_event_name": "PreToolUse", "tool_name": "Edit", "cwd": str(repo),
            "tool_input": {"file_path": str(target), "old_string": "import os", "new_string": new}}


# ── setup_probe ──────────────────────────────────────────────────────────────


def test_setup_creates_governed_repo(tmp_path):
    repo = _setup(tmp_path, "A", "protected")
    mem = json.loads((repo / ".mneme" / "project_memory.json").read_text(encoding="utf-8"))
    assert mem["decisions"][0]["rules"] == [{"type": "FORBID_LITERAL", "value": "psycopg2"}]
    assert "hookwrap_v4.py" in (repo / ".claude" / "settings.json").read_text(encoding="utf-8")
    assert not (repo / "src").exists()


def test_setup_planted_marker_is_untracked_and_existence_only(tmp_path):
    repo = _setup(tmp_path, "A", "protected", "--planted-marker")
    marker = repo / "src" / ".git"
    assert marker.is_file() and marker.read_text(encoding="utf-8") == ""
    tracked = subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True, text=True).stdout
    assert "src/mod.py" in tracked and "src/.git" not in tracked


def test_setup_refuses_existing_directory(tmp_path):
    (tmp_path / "A").mkdir()
    r = subprocess.run([PY, "-I", str(HARNESS / "setup_probe.py"), str(tmp_path / "A"), "protected",
                        str(HARNESS / "hookwrap_v4.py"), PY], capture_output=True, text=True)
    assert r.returncode != 0


# ── hookwrap_v4 around the real P2-first hook ────────────────────────────────


def test_wrapper_records_override_ignored_and_relays_refusal(tmp_path):
    a = _setup(tmp_path, "A", "protected")
    b = _setup(tmp_path, "B", "permissive")
    log = tmp_path / "hook-log.jsonl"
    r = _wrap(a, _edit(a, a / "app.py", "import psycopg2"), log, override=str(b / ".mneme" / "project_memory.json"))
    assert r.returncode == 2 and r.stdout == "" and "T08-DEC" in r.stderr
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["wrapper"] == "hookwrap_v4"
    sel = rec["selection"]
    assert Path(sel["path"]).resolve() == (a / ".mneme" / "project_memory.json").resolve()
    assert (sel["reason"], sel["source"], sel["walk"]) == ("OVERRIDE_IGNORED", "discovered", "unbounded")
    assert rec["exit"] == 2 and rec["stdout"] == ""


def test_wrapper_relays_notice_on_allowed_edit(tmp_path):
    a = _setup(tmp_path, "A", "protected")
    b = _setup(tmp_path, "B", "permissive")
    log = tmp_path / "hook-log.jsonl"
    r = _wrap(a, _edit(a, a / "app.py", "import sys"), log, override=str(b / ".mneme" / "project_memory.json"))
    assert r.returncode == 0
    assert classify_p2f.notice_ok(r.stdout)
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["stdout"] == r.stdout


def test_wrapper_planted_marker_keeps_repo_a_memory(tmp_path):
    a = _setup(tmp_path, "A", "protected", "--planted-marker")
    b = _setup(tmp_path, "B", "permissive")
    log = tmp_path / "hook-log.jsonl"
    r = _wrap(a, _edit(a, a / "src" / "mod.py", "import psycopg2"), log,
              override=str(b / ".mneme" / "project_memory.json"))
    assert r.returncode == 2 and "T08-DEC" in r.stderr
    sel = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])["selection"]
    assert sel["reason"] == "OVERRIDE_IGNORED"
    assert Path(sel["path"]).resolve() == (a / ".mneme" / "project_memory.json").resolve()


def test_wrapper_fails_closed_without_source(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "T08_MNEME_SRC"}
    env["T08_LOG"] = str(tmp_path / "log")
    r = subprocess.run([PY, str(HARNESS / "hookwrap_v4.py")], input="{}", capture_output=True,
                       text=True, env=env)
    assert r.returncode == 2 and "t08-harness" in r.stderr


# ── classifier ───────────────────────────────────────────────────────────────


PINNED = {"PIN_CLAUDE_VERSION": "2.1.310 (Claude Code)", "PIN_MODEL": "claude-opus-5-5"}


def _probe(root, name, *, reason, exit_code, stdout="", stderr="T08-DEC refused", before="h1",
           after="h1", model="claude-opus-5-5", host="2.1.310 (Claude Code)", records=True,
           path_ok=True):
    out = root / name / "out"
    out.mkdir(parents=True)
    a_mem = str(root / name / "A" / "repo_a" / ".mneme" / "project_memory.json")
    target = str(root / name / "A" / "repo_a" / "app.py")
    (out / "observer.txt").write_text("\n".join([
        f"probe={name}", f"claude={host}", f"target={target}", f"a_memory={a_mem}",
        f"BEFORE target               {before}", f"AFTER target               {after}",
        f"init_model={model}"]) + "\n", encoding="utf-8")
    rec = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "file_path": target,
           "selection": {"path": a_mem if path_ok else "elsewhere", "reason": reason, "walk": "unbounded"},
           "exit": exit_code, "stdout": stdout, "stderr": stderr, "MNEME_MEMORY": "x"}
    (out / "hook-log.jsonl").write_text((json.dumps(rec) + "\n") if records else "", encoding="utf-8")
    (out / "events.jsonl").write_text("", encoding="utf-8")


NOTICE = json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                            "additionalContext": "mneme: ... (OVERRIDE_IGNORED) ..."}}) + "\n"


def test_classifier_pass_refusal_and_notice(tmp_path):
    _probe(tmp_path, "P2F-V5", reason="OVERRIDE_IGNORED", exit_code=2)
    _probe(tmp_path, "P2F-V5-notice", reason="OVERRIDE_IGNORED", exit_code=0, stdout=NOTICE,
           stderr="", after="h2")
    r1 = classify_p2f.classify_probe(tmp_path, "P2F-V5", PINNED)
    r2 = classify_p2f.classify_probe(tmp_path, "P2F-V5-notice", PINNED)
    assert (r1["verdict"], r2["verdict"]) == ("PASS", "PASS"), (r1, r2)


@pytest.mark.parametrize("kw", [
    {"path_ok": False},                                  # another memory governed
    {"reason": "DISCOVERED"},                            # override not ignored
    {"exit_code": 0},                                    # not refused
    {"after": "h2"},                                     # target changed
    {"stdout": NOTICE},                                  # notice beside an exit-2 event
    {"stderr": ""},                                      # refusal does not name T08-DEC
])
def test_classifier_fails_each_disagreement(tmp_path, kw):
    args = {"reason": "OVERRIDE_IGNORED", "exit_code": 2} | kw
    _probe(tmp_path, "P2F-V4", **args)
    assert classify_p2f.classify_probe(tmp_path, "P2F-V4", PINNED)["verdict"] == "FAIL"


@pytest.mark.parametrize("kw", [{"records": False}, {"model": "other"}, {"host": "2.1.311 (Claude Code)"}])
def test_classifier_inconclusive(tmp_path, kw):
    _probe(tmp_path, "P2F-V5-own", reason="OVERRIDE_IGNORED", exit_code=2, **kw)
    assert classify_p2f.classify_probe(tmp_path, "P2F-V5-own", PINNED)["verdict"] == "INCONCLUSIVE"


def test_classifier_wrapper_error_is_inconclusive(tmp_path):
    _probe(tmp_path, "P2F-V4-own", reason="OVERRIDE_IGNORED", exit_code=2)
    (tmp_path / "P2F-V4-own" / "out" / "hook-log.jsonl.wrapper-errors").write_text("x", encoding="utf-8")
    assert classify_p2f.classify_probe(tmp_path, "P2F-V4-own", PINNED)["verdict"] == "INCONCLUSIVE"


def test_classifier_batch_files(tmp_path):
    _probe(tmp_path, "P2F-R0-control", reason="DISCOVERED", exit_code=2)
    assert classify_p2f.main(["x", str(tmp_path), "P2F-R0-control"]) == 0
    doc = json.loads((tmp_path / "classification_p2f.json").read_text(encoding="utf-8"))
    assert doc["pins"]["PIN_MODEL"] == "claude-opus-5-5"
    assert "P2F-R0-control" in (tmp_path / "summary_p2f.md").read_text(encoding="utf-8")


def test_every_runner_probe_has_an_expectation_and_is_deletable():
    import safe_rmtree
    runner = (HARNESS / "run_p2f.sh").read_text(encoding="utf-8")
    listed = runner.split("PROBES=(")[1].split(")")[0].split()
    assert set(listed) == set(classify_p2f.EXPECT) == set(safe_rmtree.PROBES)


# ── safe_rmtree and collect_redacted ─────────────────────────────────────────


def test_safe_rmtree_refuses_unlisted_name():
    r = subprocess.run([PY, "-I", str(HARNESS / "safe_rmtree.py"), "delete", "D6-C2-V5"],
                       capture_output=True, text=True)
    assert r.returncode == 3 and "allowlist" in r.stderr


def test_collector_leak_scan_catches_encoded_project_id(tmp_path):
    live, dest = tmp_path / "live", tmp_path / "dest"
    out = live / "P2F-V5" / "out"
    out.mkdir(parents=True)
    for name in ("observer.txt", "prompt.txt", "hook-registration.json", "events.selected.jsonl"):
        (out / name).write_text("clean\n", encoding="utf-8")
    (out / "hook-log.jsonl").write_text('{"x": "projects/C--dev-mneme/abc"}\n', encoding="utf-8")
    r = subprocess.run([PY, "-I", str(HARNESS / "collect_redacted.py"), str(live), str(dest), "pyx",
                        "srcx", "cbinx", "", "P2F-V5"], capture_output=True, text=True)
    assert r.returncode == 1 and "LEAK SCAN FAILED" in r.stdout

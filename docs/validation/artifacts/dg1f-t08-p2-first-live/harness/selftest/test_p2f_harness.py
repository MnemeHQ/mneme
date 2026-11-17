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


def test_wrapper_r4_session_in_b_target_in_a(tmp_path):
    """r4: the payload cwd is B, the target is in A; A's memory still governs."""
    a = _setup(tmp_path, "A", "protected")
    b = _setup(tmp_path, "B", "permissive")
    log = tmp_path / "hook-log.jsonl"
    r = _wrap(b, _edit(b, a / "app.py", "import psycopg2"), log,
              override=str(b / ".mneme" / "project_memory.json"))
    assert r.returncode == 2 and "T08-DEC" in r.stderr
    sel = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])["selection"]
    assert sel["reason"] == "OVERRIDE_IGNORED"
    assert Path(sel["path"]).resolve() == (a / ".mneme" / "project_memory.json").resolve()


def test_wrapper_v4_missing_override_is_ignored(tmp_path):
    a = _setup(tmp_path, "A", "protected")
    log = tmp_path / "hook-log.jsonl"
    missing = str(tmp_path / "does-not-exist" / ".mneme" / "project_memory.json")
    r = _wrap(a, _edit(a, a / "app.py", "import psycopg2"), log, override=missing)
    assert r.returncode == 2 and "T08-DEC" in r.stderr
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["selection"]["reason"] == "OVERRIDE_IGNORED"
    assert rec["MNEME_MEMORY"] == missing and rec["hook_env_view"]["MNEME_MEMORY_is_file"] is False


def test_wrapper_fails_closed_without_source(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "T08_MNEME_SRC"}
    env["T08_LOG"] = str(tmp_path / "log")
    r = subprocess.run([PY, str(HARNESS / "hookwrap_v4.py")], input="{}", capture_output=True,
                       text=True, env=env)
    assert r.returncode == 2 and "t08-harness" in r.stderr


# ── classifier ───────────────────────────────────────────────────────────────


PINNED = {"PIN_CLAUDE_VERSION": "2.1.310 (Claude Code)", "PIN_MODEL": "claude-opus-5-5",
          "SOURCES": "project"}
SRC = r"C:\pinned\mneme-src"
KIND = {"P2F-R0-control": "none", "P2F-V4": "v4", "P2F-V4-own": "v4"}


def _probe(root, name, *, reason, exit_code, stdout="", stderr="[T08-DEC] refused", before="h1",
           after="h1", model="claude-opus-5-5", host="2.1.310 (Claude Code)", records=True,
           path=None, sources="project", tree="yes", kind=None, seen=None, is_file=None,
           present=None, module=None, extra_log="", other_after="m1", content=None, head_after="c1"):
    out = root / name / "out"
    out.mkdir(parents=True)
    a_mem = str(root / name / "A" / "repo_a" / ".mneme" / "project_memory.json")
    target = str(root / name / "A" / "repo_a" / "app.py")
    kind = kind or KIND.get(name, "v5")
    configured = {"none": "<unset>", "v4": r"C:\missing\x.json", "v5": r"C:\B\memory.json"}[kind]
    if seen is None:
        seen = None if kind == "none" else configured
    if is_file is None:
        is_file = {"none": None, "v4": False, "v5": True}[kind]
    if present is None:
        present = [] if kind == "none" else ["MNEME_MEMORY"]
    if content is None:
        content = ["target contains psycopg2: 0", "target contains 'import sys': 0"] if exit_code == 2 else \
                  ["target contains psycopg2: 0", "target contains 'import sys': 1"]
    (out / "observer.txt").write_text("\n".join([
        f"probe={name} A=protected override={kind}", f"claude={host}", f"target={target}",
        f"a_memory={a_mem}", f"mneme_src_w={SRC}", f"override_kind={kind}",
        f"override_configured={configured}", f"mneme_dir_equals_pin={tree}",
        f"setting_sources={sources}",
        f"BEFORE target               {before}", "BEFORE A/memory             m1",
        "BEFORE A/HEAD               c1",
        f"init_model={model}",
        f"AFTER target               {after}", f"AFTER A/memory             {other_after}",
        f"AFTER A/HEAD               {head_after}",
        *content]) + "\n", encoding="utf-8")
    rec = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "file_path": target,
           "selection": {"path": a_mem if path is None else path, "reason": reason, "walk": "unbounded"},
           "exit": exit_code, "stdout": stdout, "stderr": stderr, "MNEME_MEMORY": seen,
           "hook_env_view": {"MNEME_present": present, "MNEME_MEMORY_is_file": is_file},
           "hook_module": module or SRC + r"\mneme\integrations\claude_code\hook.py"}
    (out / "hook-log.jsonl").write_text(((json.dumps(rec) + "\n") if records else "") + extra_log,
                                        encoding="utf-8")
    (out / "events.jsonl").write_text("", encoding="utf-8")


NOTICE = json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                            "additionalContext": "mneme: ... (OVERRIDE_IGNORED) ..."}}) + "\n"


def _verdict(root, name):
    return classify_p2f.classify_probe(root, name, PINNED)


def test_classifier_pass_each_expectation(tmp_path):
    _probe(tmp_path, "P2F-R0-control", reason="DISCOVERED", exit_code=2)
    _probe(tmp_path, "P2F-V5", reason="OVERRIDE_IGNORED", exit_code=2)
    _probe(tmp_path, "P2F-V4", reason="OVERRIDE_IGNORED", exit_code=2)
    _probe(tmp_path, "P2F-V5-notice", reason="OVERRIDE_IGNORED", exit_code=0, stdout=NOTICE,
           stderr="", after="h2")
    for name in ("P2F-R0-control", "P2F-V5", "P2F-V4", "P2F-V5-notice"):
        r = _verdict(tmp_path, name)
        assert r["verdict"] == "PASS", r


@pytest.mark.parametrize("kw", [
    {"path": "elsewhere"},                               # another memory governed
    {"reason": "DISCOVERED"},                            # override not ignored
    {"exit_code": 0, "stderr": ""},                      # not refused
    {"after": "h2"},                                     # target changed
    {"stdout": NOTICE},                                  # notice beside an exit-2 event
    {"stderr": ""},                                      # refusal does not name T08-DEC
    {"seen": r"C:\B\other.json"},                        # hook saw another override
    {"is_file": True},                                   # v4 seen as an existing file
    {"present": ["MNEME_MEMORY", "MNEME_HOOK_CHECK_TRANSPORT"]},  # other MNEME_* leaked in
    {"module": r"C:\elsewhere\mneme\integrations\claude_code\hook.py"},  # hook not from pin
    {"other_after": "m2"},                               # A's memory changed
    {"head_after": "c2"},                                # a commit happened
    {"content": ["target contains psycopg2: 1"]},        # forbidden literal present
])
def test_classifier_fails_each_disagreement(tmp_path, kw):
    _probe(tmp_path, "P2F-V4", **({"reason": "OVERRIDE_IGNORED", "exit_code": 2} | kw))
    assert _verdict(tmp_path, "P2F-V4")["verdict"] == "FAIL"


def test_classifier_no_selected_path_fails(tmp_path):
    """A record with no selected memory never counts as repo A's memory."""
    _probe(tmp_path, "P2F-V4", reason="OVERRIDE_IGNORED", exit_code=2)
    log = tmp_path / "P2F-V4" / "out" / "hook-log.jsonl"
    rec = json.loads(log.read_text(encoding="utf-8"))
    rec["selection"]["path"] = None
    log.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    r = _verdict(tmp_path, "P2F-V4")
    assert r["verdict"] == "FAIL" and r["checks"]["selected_repo_a_memory"] is False


def test_classifier_failed_open_notice_fails(tmp_path):
    """B2: a check that failed open also exits 0 with the notice."""
    _probe(tmp_path, "P2F-V5-notice", reason="OVERRIDE_IGNORED", exit_code=0, stdout=NOTICE,
           stderr="mneme-hook: check could not run (timeout). Failing open.\n", after="h2")
    r = _verdict(tmp_path, "P2F-V5-notice")
    assert r["verdict"] == "FAIL" and r["checks"]["evaluated_no_stderr"] is False


def test_classifier_notice_without_applied_edit_fails(tmp_path):
    _probe(tmp_path, "P2F-V5-notice", reason="OVERRIDE_IGNORED", exit_code=0, stdout=NOTICE,
           stderr="", after="h2", content=["target contains 'import sys': 0"])
    assert _verdict(tmp_path, "P2F-V5-notice")["verdict"] == "FAIL"


@pytest.mark.parametrize("kw", [
    {"records": False}, {"model": "other"}, {"host": "2.1.311 (Claude Code)"},
    {"sources": "project,local"}, {"tree": "no"},
    {"extra_log": "{not json\n"},
])
def test_classifier_inconclusive(tmp_path, kw):
    _probe(tmp_path, "P2F-V5-own", reason="OVERRIDE_IGNORED", exit_code=2, **kw)
    assert _verdict(tmp_path, "P2F-V5-own")["verdict"] == "INCONCLUSIVE"


def test_classifier_flags_ungoverned_write(tmp_path):
    _probe(tmp_path, "P2F-V5", reason="OVERRIDE_IGNORED", exit_code=2, records=False, after="h2")
    r = _verdict(tmp_path, "P2F-V5")
    assert r["verdict"] == "INCONCLUSIVE" and "ungoverned write" in "; ".join(r["problems"])


def test_classifier_missing_observer_fields_is_inconclusive(tmp_path):
    _probe(tmp_path, "P2F-V5", reason="OVERRIDE_IGNORED", exit_code=2)
    obs = tmp_path / "P2F-V5" / "out" / "observer.txt"
    obs.write_text("\n".join(ln for ln in obs.read_text(encoding="utf-8").splitlines()
                             if not ln.startswith("a_memory=")) + "\n", encoding="utf-8")
    assert _verdict(tmp_path, "P2F-V5")["verdict"] == "INCONCLUSIVE"


def test_classifier_wrapper_error_is_inconclusive(tmp_path):
    _probe(tmp_path, "P2F-V4-own", reason="OVERRIDE_IGNORED", exit_code=2)
    (tmp_path / "P2F-V4-own" / "out" / "hook-log.jsonl.wrapper-errors").write_text("x", encoding="utf-8")
    assert _verdict(tmp_path, "P2F-V4-own")["verdict"] == "INCONCLUSIVE"


def test_classifier_batch_files(tmp_path):
    _probe(tmp_path, "P2F-R0-control", reason="DISCOVERED", exit_code=2)
    assert classify_p2f.main(["x", str(tmp_path), "P2F-R0-control"]) == 0
    doc = json.loads((tmp_path / "classification_p2f.json").read_text(encoding="utf-8"))
    assert doc["pins"]["PIN_MODEL"] == "claude-opus-5-5" and doc["pins"]["SOURCES"] == "project"
    assert "P2F-R0-control" in (tmp_path / "summary_p2f.md").read_text(encoding="utf-8")


def test_committed_pins_match_classifier_expectations():
    pinned = classify_p2f.pins()
    assert pinned["SOURCES"] == "project"
    assert pinned["PIN_CLAUDE_VERSION"] == "2.1.310 (Claude Code)"
    assert pinned["PIN_MODEL"] == "claude-opus-5-5"


def test_every_runner_probe_has_an_expectation_and_is_allowlisted():
    import safe_rmtree
    runner = (HARNESS / "run_p2f.sh").read_text(encoding="utf-8")
    listed = runner.split("PROBES=(")[1].split(")")[0].split()
    assert set(listed) == set(classify_p2f.EXPECT) == set(safe_rmtree.PROBES)


def test_runner_guards_are_present():
    runner = (HARNESS / "run_p2f.sh").read_text(encoding="utf-8")
    probe = (HARNESS / "run_p2f_probe.sh").read_text(encoding="utf-8")
    assert "P2F_STARTED" in runner and 'abort "classification failed' in runner
    assert runner.index("P2F_DONE\"") > runner.index("classify_p2f.py")
    assert "status --porcelain" in runner
    assert "safe_rmtree.py\" delete" not in probe, "probes must never delete earlier evidence"
    assert "already exists" in probe
    assert "grep '^MNEME_'" in probe and "export -n MNEME_SRC_W MNEME_SRC_U" in probe
    assert probe.index("P2F_STARTED") < probe.index("mkdir -p \"$P\"")
    assert "is not empty" in runner
    for f in HARNESS.glob("*.sh"):
        assert "SELFTEST" not in f.read_text(encoding="utf-8")


def test_pins_guard_rejects_changed_pin(tmp_path):
    work = tmp_path / "h"
    work.mkdir()
    (work / "pins.env").write_text((HARNESS / "pins.env").read_text(encoding="utf-8"), encoding="utf-8")
    (work / "pins.local.env").write_text("SOURCES='project,local'\n", encoding="utf-8")
    bash = r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else "bash"
    r = subprocess.run([bash, "-c", f'. "{work.as_posix()}/pins.env"; echo SURVIVED'],
                       capture_output=True, text=True)
    assert "SURVIVED" not in r.stdout and "SOURCES" in r.stdout
    (work / "pins.local.env").write_text("PY='/usr/bin/python3'\n", encoding="utf-8")
    r = subprocess.run([bash, "-c", f'. "{work.as_posix()}/pins.env"; echo SURVIVED'],
                       capture_output=True, text=True)
    assert "SURVIVED" in r.stdout


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


def test_collector_redacts_doubly_escaped_live_root(tmp_path):
    # The OVERRIDE_IGNORED notice is JSON inside a JSON string, so a Windows
    # live root appears with four backslashes per separator in hook-log.jsonl.
    live, dest = tmp_path / "live", tmp_path / "dest"
    out = live / "P2F-V5-notice" / "out"
    out.mkdir(parents=True)
    for name in ("observer.txt", "prompt.txt", "hook-registration.json", "events.selected.jsonl"):
        (out / name).write_text("clean\n", encoding="utf-8")
    quad = str(live).replace("/", "\\").replace("\\", "\\\\\\\\")
    (out / "hook-log.jsonl").write_text('{"stdout": "memory ' + quad + '\\\\\\\\P2F"}\n',
                                        encoding="utf-8")
    r = subprocess.run([PY, "-I", str(HARNESS / "collect_redacted.py"), str(live), str(dest), "pyx",
                        "srcx", "cbinx", "", "P2F-V5-notice"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    text = (dest / "P2F-V5-notice" / "hook-log.jsonl").read_text(encoding="utf-8")
    assert '"memory <LIVE>' in text and quad not in text

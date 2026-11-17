"""Offline validation of the Amendment A3 pin set (probe scope 4.4). NOT live evidence.

Run:  python -m pytest -q docs/validation/artifacts/dg1f-t08-d5-p2-h1-host-path/harness/selftest

A3 re-pins the H1c A1 track (Stop top-level systemMessage, headless and interactive)
to Claude Code 2.1.310 with `--model claude-opus-5-5`, the host and model of
Amendment A2, in a separate disposable root. These cases check the pin-set
plumbing, the A3 guarded delete, the version pin in the headless classifier, and
that `combine` judges H1c on one host version only. The stub's behavior is a test
fixture, not a claim about Claude Code.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
sys.path.insert(0, str(HERE))
import test_a1_harness as T  # noqa: E402  (reuses the A1 stub fixtures)

A3_VERSION = "2.1.310 (Claude Code)"
A3_MODEL = "claude-opus-5-5"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HARNESS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rm_a3 = _load("safe_rmtree_a3")
A1 = T.A1


# ---------------------------------------------------------------- guarded delete

def test_a3_guarded_delete_has_its_own_root_and_the_a1_arms():
    assert rm_a3.ROOT == r"C:\dev\d5p2-h1c-a3-live"
    assert rm_a3.PROBES == ("H1c-sm", "H1c-sm-ctl", "H1c-sm-int", "H1c-sm-int-ctl")


def test_a3_guarded_delete_protects_every_earlier_tree():
    for p in (r"C:\dev\mneme", r"C:\dev\d5p2-h1-live", r"C:\dev\d5p2-h1-archive",
              r"C:\dev\d5p2-h1c-a1-live", r"C:\dev\d5p2-h1c-a1-archive", r"C:\dev\d5p2-h1c-a1-attempts",
              r"C:\dev\d5p2-h1-a2-live", r"C:\dev\d5p2-h1-a2-archive"):
        assert p in rm_a3.PROTECTED, p
        assert not rm_a3.within(rm_a3.ROOT, p) and not rm_a3.within(p, rm_a3.ROOT), p


@pytest.mark.parametrize("name", ["H1c-stop", "H1a-edit", "H1c-sm/..", "h1c-sm", "", "H1c-sm-int-ctl2"])
def test_a3_guarded_delete_refuses_other_names(name):
    with pytest.raises(SystemExit) as e:
        rm_a3.delete(name)
    assert e.value.code == 3


# ---------------------------------------------------------------- headless version pin

def _headless(tmp_path, version=A3_VERSION, ctl_version=None, pin_version=A3_VERSION):
    live = tmp_path / "live"
    for arm, v in (("H1c-sm-ctl", ctl_version if ctl_version is not None else version), ("H1c-sm", version)):
        out = T._arm(live, arm, {"H1_STUB_SM_MODE": "drop"})
        if v:
            (out / "observer.txt").write_text(f"arm={arm}\nclaude_version={v}\n", encoding="utf-8")
    return A1.headless(live, T.PIN, pin_version)


def test_headless_matching_version_pin_is_classified_normally(tmp_path):
    h = _headless(tmp_path)
    assert h["label"] != "NOT_EXECUTED", h
    assert h["a1"]["pin_version"] == A3_VERSION
    assert h["a1"]["claude_versions"] == {"emitter": A3_VERSION, "control": A3_VERSION}


@pytest.mark.parametrize("emit_v,ctl_v", [("2.1.311 (Claude Code)", A3_VERSION), (A3_VERSION, "2.1.202 (Claude Code)")])
def test_headless_version_mismatch_in_either_arm_is_not_executed(tmp_path, emit_v, ctl_v):
    h = _headless(tmp_path, version=emit_v, ctl_version=ctl_v)
    assert h["label"] == "NOT_EXECUTED", h


def test_headless_unrecorded_version_is_not_executed_when_pinned(tmp_path):
    h = _headless(tmp_path, version="", ctl_version="")
    assert h["label"] == "NOT_EXECUTED", h


def test_headless_without_pin_keeps_a1_behaviour(tmp_path):
    h = _headless(tmp_path, version="2.1.202 (Claude Code)", pin_version=None)
    assert h["label"] != "NOT_EXECUTED" and h["a1"]["pin_version"] is None, h


# ---------------------------------------------------------------- combine: one host version

def _rec(hv_emit, hv_ctl, iv, h_label="NOT_DELIVERED", i_label="DELIVERED_TO_USER_ONLY"):
    h = {"label": h_label, "a1": {"host_interference": [], "claude_versions": {"emitter": hv_emit, "control": hv_ctl}}}
    i = {"label": i_label, "pins": {"claude_version": iv, "model": A3_MODEL}}
    return h, i


def test_combine_on_one_version_passes_and_records_it():
    c = A1.combine(*_rec(A3_VERSION, A3_VERSION, A3_VERSION))
    assert c["label"] == "DELIVERED_TO_USER_ONLY" and c["h1c_passes_under_a1"] is True
    assert c["host_version"] == A3_VERSION


@pytest.mark.parametrize("hv_emit,hv_ctl,iv", [
    ("2.1.202 (Claude Code)", "2.1.202 (Claude Code)", A3_VERSION),   # A1 headless + A3 interactive
    (A3_VERSION, A3_VERSION, "2.1.303 (Claude Code)"),
    (A3_VERSION, "2.1.202 (Claude Code)", A3_VERSION),
])
def test_combine_mixed_versions_is_not_executed(hv_emit, hv_ctl, iv):
    c = A1.combine(*_rec(hv_emit, hv_ctl, iv))
    assert c["label"] == "NOT_EXECUTED" and c["h1c_passes_under_a1"] is False, c
    assert any("host versions differ" in r for r in c["reasons"]), c


@pytest.mark.parametrize("hv_emit,hv_ctl,iv", [(None, A3_VERSION, A3_VERSION), (A3_VERSION, A3_VERSION, None)])
def test_combine_unrecorded_version_is_not_executed(hv_emit, hv_ctl, iv):
    c = A1.combine(*_rec(hv_emit, hv_ctl, iv))
    assert c["label"] == "NOT_EXECUTED" and any("unrecorded" in r for r in c["reasons"]), c


def test_combine_version_check_precedes_a_passing_label():
    # Even a would-be agent delivery is never combined across versions.
    c = A1.combine(*_rec("2.1.202 (Claude Code)", "2.1.202 (Claude Code)", A3_VERSION,
                         h_label="DELIVERED_TO_AGENT", i_label="DELIVERED_TO_AGENT"))
    assert c["label"] == "NOT_EXECUTED", c


# ---------------------------------------------------------------- shell plumbing (Git Bash)

def _git_bash():
    for cand in (r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash")):
        if cand and os.path.isfile(cand) and "system32" not in cand.lower():
            return cand
    return None


BASH = _git_bash()
needs_bash = pytest.mark.skipif(BASH is None, reason="Git Bash not found")


def _sh(script, extra_env=None, cwd=HARNESS):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("H1_", "A1_", "MNEME_")) and k not in ("CLAUDECODE", "DISABLE_AUTOUPDATER")}
    env.update(extra_env or {})
    return subprocess.run([BASH, "-c", script], cwd=cwd, env=env, capture_output=True, text=True)


SHOW = '. ./pins_a1.env; echo "$PIN_CLAUDE_VERSION|$PIN_MODEL|$PIN_MODEL_FLAG|$LIVE|$A1_LIVE_W|$A1_RMTREE"'


@needs_bash
def test_pins_a3_selects_its_own_pins():
    r = _sh(SHOW, {"A1_PINSET": "A3"})
    assert r.stdout.strip() == (f"{A3_VERSION}|{A3_MODEL}|{A3_MODEL}|/c/dev/d5p2-h1c-a3-live|"
                                r"C:\dev\d5p2-h1c-a3-live|safe_rmtree_a3.py"), r


@needs_bash
def test_default_a1_pins_are_unchanged():
    r = _sh(SHOW)
    assert r.stdout.strip() == (r"2.1.202 (Claude Code)|claude-opus-4-8[1m]||/c/dev/d5p2-h1c-a1-live|"
                                r"C:\dev\d5p2-h1c-a1-live|safe_rmtree_a1.py"), r


@needs_bash
@pytest.mark.parametrize("value", ["A2", "A4", "", "a3"])
def test_unknown_or_empty_a1_pinset_aborts(value):
    r = _sh(SHOW, {"A1_PINSET": value})
    assert r.returncode == 1 and "unknown A1_PINSET" in r.stdout and "|" not in r.stdout, r


@needs_bash
def test_a1_pins_still_refuse_an_h1_pinset():
    r = _sh(SHOW, {"H1_PINSET": "A2"})
    assert r.returncode == 1 and "|" not in r.stdout, r


@needs_bash
@pytest.mark.parametrize("local", ["A1_PINSET='A3'\n", "export A1_PINSET=A3\n", "unset A1_PINSET\n"])
def test_local_file_cannot_select_or_clear_the_a1_pinset(tmp_path, local):
    for f in ("pins.env", "pins_a1.env"):
        shutil.copy(HARNESS / f, tmp_path / f)
    (tmp_path / "pins.local.env").write_text("PY='/c/x/python.exe'\n" + local, encoding="utf-8", newline="\n")
    env = {"A1_PINSET": "A3"} if local.startswith("unset") else None
    r = _sh(SHOW, env, cwd=tmp_path)
    assert r.returncode == 1 and "changed pinned value(s): A1_PINSET" in r.stdout, r


@needs_bash
@pytest.mark.parametrize("script", ["run_a1_headless.sh", "prep_a1_interactive.sh H1c-sm-int-ctl",
                                    "finish_a1_interactive.sh H1c-sm-int-ctl x"])
@pytest.mark.parametrize("env_value", ["A3", ""])
def test_entry_points_refuse_an_inherited_a1_pinset(script, env_value):
    r = _sh(f"bash ./{script}", {"A1_PINSET": env_value, "DISABLE_AUTOUPDATER": "1"})
    assert r.returncode == 1 and "A1_PINSET is set in the environment" in r.stdout, r
    assert "[preflight]" not in r.stdout


@needs_bash
def test_headless_runner_refuses_unknown_pin_set_argument():
    r = _sh("bash ./run_a1_headless.sh A2")
    assert r.returncode == 1 and "unknown pin set" in r.stdout, r


@needs_bash
def test_h1_runner_refuses_an_a1_pinset():
    r = _sh("bash ./run_h1.sh A2", {"A1_PINSET": "A3", "DISABLE_AUTOUPDATER": "1"})
    assert r.returncode == 1 and "A1_PINSET is set in the environment" in r.stdout, r


@needs_bash
@pytest.mark.parametrize("script", ["run_a1_probe.sh H1c-sm-ctl", "prep_a1_interactive.sh A3 H1c-sm-int-ctl",
                                    "finish_a1_interactive.sh A3 H1c-sm-int-ctl x"])
def test_a3_needs_disable_autoupdater(script, tmp_path):
    env = {"A1_PINSET": "A3"} if script.startswith("run_a1_probe") else {}
    r = _sh(f"bash ./{script}", env)
    assert r.returncode == 1 and "needs DISABLE_AUTOUPDATER=1" in r.stdout, r


@needs_bash
def test_preflight_reports_a3_and_requires_disable_autoupdater(tmp_path):
    for f in ("preflight.sh", "pins.env", "pins_a1.env"):
        shutil.copy(HARNESS / f, tmp_path / f)
    py = Path(sys.executable).as_posix().replace("C:", "/c", 1)
    (tmp_path / "pins.local.env").write_text(f"PY='{py}'\n", encoding="utf-8", newline="\n")
    r = _sh("bash ./preflight.sh", {"A1_PINSET": "A3"}, cwd=tmp_path)
    assert "pin set: A3 (H1c, Amendment A3)" in r.stdout, r
    assert "pin set A3 needs DISABLE_AUTOUPDATER=1" in r.stdout and r.returncode == 1, r
    assert "syntax error" not in r.stderr and "command not found" not in r.stderr, r
    ok = _sh("bash ./preflight.sh", {"A1_PINSET": "A3", "DISABLE_AUTOUPDATER": "1"}, cwd=tmp_path)
    lines = ok.stdout.splitlines()
    assert "[preflight] DISABLE_AUTOUPDATER=1 (Amendment A3)" in lines, ok  # exact line, nothing appended
    assert "needs DISABLE_AUTOUPDATER" not in ok.stdout, ok
    assert "syntax error" not in ok.stderr and "command not found" not in ok.stderr, ok


@needs_bash
def test_a3_probe_passes_the_model_flag_and_records_the_pinset():
    src = (HARNESS / "run_a1_probe.sh").read_text(encoding="utf-8")
    assert '${PIN_MODEL_FLAG:+--model "$PIN_MODEL_FLAG"}' in src
    assert 'echo "pinset=${A1_PINSET:-A1}"' in src and 'echo "claude_version=$V"' in src

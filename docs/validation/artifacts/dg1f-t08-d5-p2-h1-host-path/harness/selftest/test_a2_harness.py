"""Offline validation of the Amendment A2 pin set (probe scope 4.3). NOT live evidence.

Run:  python -m pytest -q docs/validation/artifacts/dg1f-t08-d5-p2-h1-host-path/harness/selftest

A2 re-pins H1a-edit, H1a-bash and H1b-start to Claude Code 2.1.310 with
`--model claude-opus-5-5`, in a separate disposable root. These cases check the
pin-set plumbing, the A2 guarded delete, the version and model pins in the
classifier, and that a subset summary never claims the H1 gate. The stub's
behavior is a test fixture, not a claim about Claude Code.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent.parent
STUB = HARNESS / "selftest" / "stub_claude.py"
A2_VERSION = "2.1.310 (Claude Code)"
A2_MODEL = "claude-opus-5-5"
H1_MODEL = "claude-opus-4-8[1m]"
A2_PATHS = "H1a-edit,H1a-bash,H1b-start"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HARNESS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = _load("classify_h1")
setup_probe = _load("setup_probe")
rm_a2 = _load("safe_rmtree_a2")


def _arm(live, arm, args=(), knobs=None, version=None):
    pdir = live / arm
    setup_probe.main(["setup_probe.py", arm, str(pdir), sys.executable, str(HARNESS / "emitter.py")])
    meta = json.loads((pdir / "out" / "probe.json").read_text(encoding="utf-8"))
    env = {k: v for k, v in os.environ.items() if not k.startswith(("H1_STUB_", "MNEME_"))}
    env.update({"H1_STUB_HOME": str(live / "_home" / arm), **(knobs or {})})
    with open(pdir / "out" / "events.jsonl", "w", encoding="utf-8") as f:
        subprocess.run([sys.executable, "-I", str(STUB), "-p", meta["prompt"], *args], cwd=pdir / "ws",
                       env=env, stdout=f, check=True)
    tps = list((live / "_home" / arm).glob("projects/*/*.jsonl"))
    if tps:
        shutil.copy(tps[0], pdir / "out" / "transcript.jsonl")
    if version is not None:
        (pdir / "out" / "observer.txt").write_text(f"arm={arm}\nclaude_version={version}\n", encoding="utf-8")


def _pair(tmp_path, path_id, args=(), version=None, ctl_version=None):
    live = tmp_path / "live"
    _arm(live, f"{path_id}-ctl", args, version=ctl_version if ctl_version is not None else version)
    _arm(live, path_id, args, version=version)
    return live


def _classify(live, path_id, pin_model, pin_version=None):
    emit = C.load_arm(live / path_id / "out")
    ctl = C.load_arm(live / f"{path_id}-ctl" / "out")
    return C.classify(emit, ctl, path_id, pin_model, pin_version)


# ---------------------------------------------------------------- guarded delete

def test_a2_guarded_delete_has_its_own_root_and_six_arms():
    assert rm_a2.ROOT == r"C:\dev\d5p2-h1-a2-live"
    assert rm_a2.PROBES == ("H1a-edit", "H1a-edit-ctl", "H1a-bash", "H1a-bash-ctl",
                            "H1b-start", "H1b-start-ctl")


def test_a2_guarded_delete_protects_earlier_evidence():
    for p in (r"C:\dev\mneme", r"C:\dev\d5p2-h1-live", r"C:\dev\d5p2-h1-archive",
              r"C:\dev\d5p2-h1c-a1-live", r"C:\dev\d5p2-h1c-a1-archive", r"C:\dev\d5p2-h1c-a1-attempts"):
        assert p in rm_a2.PROTECTED
        assert not rm_a2.within(rm_a2.ROOT, p) and not rm_a2.within(p, rm_a2.ROOT)


@pytest.mark.parametrize("name", ["H1c-stop", "H1c-stop-ctl", "H1c-sm", "..", "H1a-edit/.."])
def test_a2_guarded_delete_refuses_non_a2_arms(name):
    with pytest.raises(SystemExit) as e:
        rm_a2.delete(name)
    assert e.value.code == 3


# ---------------------------------------------------------------- path selection and summary

def test_selected_paths_default_is_every_h1_path():
    assert C.selected_paths() == ["H1a-edit", "H1a-bash", "H1b-start", "H1c-stop"]


def test_selected_paths_keeps_h1_order():
    assert C.selected_paths("H1b-start,H1a-edit") == ["H1a-edit", "H1b-start"]


@pytest.mark.parametrize("csv", ["", ",", "H1a-edit,H1a-edit", "H1a-edit,H1d-x", "H1c-sm"])
def test_selected_paths_refuses_bad_selection(csv):
    with pytest.raises(ValueError):
        C.selected_paths(csv)


def _write_outcomes(live, paths, version=A2_VERSION):
    for p in paths:
        out = live / p / "out"
        out.mkdir(parents=True)
        out.joinpath("outcome.json").write_text(json.dumps({
            "path_type": C.PATHS[p]["path_type"], "label": "DELIVERED_TO_AGENT", "passes_path": True,
            "echoed": True, "reasons": [], "observer": {"claude_version": version}}), encoding="utf-8")


def test_subset_verify_needs_only_listed_outcomes(tmp_path):
    _write_outcomes(tmp_path, ["H1a-edit", "H1a-bash", "H1b-start"])
    assert C.cmd_verify(str(tmp_path), A2_PATHS) == 0
    assert C.cmd_verify(str(tmp_path)) == 1  # the full set still needs H1c-stop


def test_subset_summary_never_claims_the_h1_gate(tmp_path):
    _write_outcomes(tmp_path, ["H1a-edit", "H1a-bash", "H1b-start"])
    C.cmd_summary(str(tmp_path), "summary.md", A2_PATHS)
    text = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "Listed-path result (every listed path passes): **PASS**" in text
    assert "**not** the H1 gate" in text and "H1c-stop" in text
    assert "H1 gate (every path passes)" not in text
    assert A2_VERSION in text  # the host version is shown per path


def test_full_summary_keeps_the_h1_gate_line(tmp_path):
    _write_outcomes(tmp_path, list(C.PATHS), version="2.1.202 (Claude Code)")
    C.cmd_summary(str(tmp_path), "summary.md")
    text = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "H1 gate (every path passes): **PASS**" in text
    assert "Listed-path result" not in text


# ---------------------------------------------------------------- model and version pins

def test_stub_honours_model_flag_like_the_host(tmp_path):
    live = _pair(tmp_path, "H1a-edit", ("--model", A2_MODEL))
    r = _classify(live, "H1a-edit", A2_MODEL)
    assert r["label"] == "DELIVERED_TO_AGENT", r


def test_missing_model_flag_is_not_executed_under_a2_pin(tmp_path):
    live = _pair(tmp_path, "H1a-edit")  # no --model: the stub's default (H1) model
    r = _classify(live, "H1a-edit", A2_MODEL)
    assert r["label"] == "NOT_EXECUTED" and any("init model" in x for x in r["reasons"]), r


@pytest.mark.parametrize("path_id", ["H1a-edit", "H1a-bash", "H1b-start"])
def test_matching_version_pin_passes(tmp_path, path_id):
    live = _pair(tmp_path, path_id, ("--model", A2_MODEL), version=A2_VERSION)
    r = _classify(live, path_id, A2_MODEL, A2_VERSION)
    assert r["label"] == "DELIVERED_TO_AGENT", r


def test_version_mismatch_in_either_arm_is_not_executed(tmp_path):
    live = _pair(tmp_path, "H1a-edit", ("--model", A2_MODEL), version=A2_VERSION,
                 ctl_version="2.1.311 (Claude Code)")
    r = _classify(live, "H1a-edit", A2_MODEL, A2_VERSION)
    assert r["label"] == "NOT_EXECUTED" and any("control: claude_version" in x for x in r["reasons"]), r


def test_unrecorded_version_is_not_executed_when_pinned(tmp_path):
    live = _pair(tmp_path, "H1a-edit", ("--model", A2_MODEL))  # no observer.txt
    r = _classify(live, "H1a-edit", A2_MODEL, A2_VERSION)
    assert r["label"] == "NOT_EXECUTED", r


def test_no_version_pin_keeps_h1_behaviour(tmp_path):
    live = _pair(tmp_path, "H1a-edit")
    r = _classify(live, "H1a-edit", H1_MODEL)
    assert r["label"] == "DELIVERED_TO_AGENT", r


def test_pair_records_pinset_and_model_flag(tmp_path):
    live = _pair(tmp_path, "H1a-edit", ("--model", A2_MODEL))
    (live / "H1a-edit" / "out" / "observer.txt").write_text(
        f"arm=H1a-edit\npinset=A2\nmodel_flag={A2_MODEL}\nclaude_version={A2_VERSION}\n", encoding="utf-8")
    (live / "H1a-edit-ctl" / "out" / "observer.txt").write_text(
        f"arm=H1a-edit-ctl\npinset=A2\nmodel_flag={A2_MODEL}\nclaude_version={A2_VERSION}\n", encoding="utf-8")
    assert C.cmd_pair(str(live), "H1a-edit", A2_MODEL, A2_VERSION) == 0
    rec = json.loads((live / "H1a-edit" / "out" / "outcome.json").read_text(encoding="utf-8"))
    assert rec["label"] == "DELIVERED_TO_AGENT", rec
    assert rec["observer"]["pinset"] == "A2" and rec["observer"]["model_flag"] == A2_MODEL


def test_stub_version_follows_the_knob():
    env = {**os.environ, "H1_STUB_VERSION": A2_VERSION}
    out = subprocess.run([sys.executable, "-I", str(STUB), "--version"], env=env,
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == A2_VERSION


# ---------------------------------------------------------------- shell plumbing (Git Bash)

def _git_bash():
    for cand in (r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash")):
        if cand and os.path.isfile(cand) and "system32" not in cand.lower():
            return cand
    return None


BASH = _git_bash()
needs_bash = pytest.mark.skipif(BASH is None, reason="Git Bash not found")


def _sh(script, extra_env=None):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("H1_", "MNEME_")) and k not in ("CLAUDECODE", "DISABLE_AUTOUPDATER")}
    env.update(extra_env or {})
    return subprocess.run([BASH, "-c", script], cwd=HARNESS, env=env, capture_output=True, text=True)


@needs_bash
def test_pins_a2_selects_its_own_pins():
    r = _sh('. ./pins.env; echo "$PIN_CLAUDE_VERSION|$PIN_MODEL|$PIN_MODEL_FLAG|$LIVE|$RMTREE|$H1_PATHS"',
            {"H1_PINSET": "A2"})
    assert r.stdout.strip() == (f"{A2_VERSION}|{A2_MODEL}|{A2_MODEL}|/c/dev/d5p2-h1-a2-live|"
                                "safe_rmtree_a2.py|H1a-edit H1a-bash H1b-start"), r


@needs_bash
def test_default_pins_are_unchanged():
    r = _sh('. ./pins.env; echo "$PIN_CLAUDE_VERSION|$PIN_MODEL|$PIN_MODEL_FLAG|$LIVE|$RMTREE|$H1_PATHS"')
    assert r.stdout.strip() == ("2.1.202 (Claude Code)|claude-opus-4-8[1m]||/c/dev/d5p2-h1-live|"
                                "safe_rmtree.py|H1a-edit H1a-bash H1b-start H1c-stop"), r


@needs_bash
def test_unknown_pinset_aborts():
    r = _sh('. ./pins.env; echo reached', {"H1_PINSET": "A3"})
    assert r.returncode == 1 and "reached" not in r.stdout and "unknown H1_PINSET" in r.stdout, r


@needs_bash
def test_a1_pins_refuse_a_pinset():
    r = _sh('. ./pins_a1.env; echo reached', {"H1_PINSET": "A2"})
    assert r.returncode == 1 and "reached" not in r.stdout, r


@needs_bash
@pytest.mark.parametrize("arm", ["H1c-stop", "H1c-stop-ctl"])
def test_a2_probe_refuses_stop_arms(arm):
    r = _sh(f"bash ./run_h1_probe.sh {arm}", {"H1_PINSET": "A2", "DISABLE_AUTOUPDATER": "1"})
    assert r.returncode == 1 and "not in pin set A2" in r.stdout, r


@needs_bash
def test_runner_refuses_unknown_pin_set_argument():
    r = _sh("bash ./run_h1.sh B7")
    assert r.returncode == 1 and "unknown pin set" in r.stdout, r


@needs_bash
def test_runner_refuses_pinset_from_the_environment():
    r = _sh("bash ./run_h1.sh", {"H1_PINSET": "A2"})
    assert r.returncode == 1 and "pass the pin set as the argument" in r.stdout, r

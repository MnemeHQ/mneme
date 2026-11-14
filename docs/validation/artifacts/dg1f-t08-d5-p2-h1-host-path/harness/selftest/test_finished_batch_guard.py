"""The finished-batch guard (guard_finished.sh): kept evidence is never touched.

On 2026-11-13 a mutation check of #802 let `run_h1.sh A2` start against the kept A2
root: it deleted H1_DONE and summary_h1.md and overwrote run_h1.log before aborting
(restored from the archive). Every runner and probe now refuses a root that holds a
finished batch, and the interactive steps refuse a finished arm, before writing.

SAFETY: these tests never execute a runner against a real root. The helper is
exercised only on temporary directories, and each call site is checked from the
script source (the guard must precede the script's first write). The finish retry
tests (review of #803) run finish_a1_interactive.sh only inside a temporary COPY of
the harness whose A1 root is rewritten to a temporary directory, and they assert
that rewrite before running anything. A mutation can therefore never reach a real
evidence root.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent.parent
GUARD = HARNESS / "guard_finished.sh"


def _git_bash():
    for cand in (r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash")):
        if cand and os.path.isfile(cand) and "system32" not in cand.lower():
            return cand
    return None


BASH = _git_bash()
needs_bash = pytest.mark.skipif(BASH is None, reason="Git Bash not found")


def _posix(p):
    s = Path(p).as_posix()
    return "/" + s[0].lower() + s[2:] if re.match(r"^[A-Za-z]:/", s) else s


def _snapshot(root):
    return sorted((str(p.relative_to(root)), p.read_bytes()) for p in Path(root).rglob("*") if p.is_file())


def _run(snippet, root):
    script = f'. "{_posix(GUARD)}"; {snippet}; echo PASSED'
    return subprocess.run([BASH, "-c", script], cwd=root, capture_output=True, text=True)


# ---------------------------------------------------------------- the helper, on temporary roots only

@needs_bash
@pytest.mark.parametrize("marker", ["H1_DONE", "summary_h1.md"])
def test_finished_h1_batch_is_refused_and_untouched(tmp_path, marker):
    (tmp_path / marker).write_text("kept\n", encoding="utf-8")
    (tmp_path / "run_h1.log").write_text("kept log\n", encoding="utf-8")
    before = _snapshot(tmp_path)
    r = _run(f'refuse_finished_batch "{_posix(tmp_path)}" H1_DONE summary_h1.md', tmp_path)
    assert r.returncode == 1 and "PASSED" not in r.stdout, r
    assert f"holds a finished batch ({marker})" in r.stdout and "nothing was changed" in r.stdout, r
    assert _snapshot(tmp_path) == before


@needs_bash
def test_finished_a1_headless_batch_is_refused(tmp_path):
    (tmp_path / "outcome_a1_headless.json").write_text("{}", encoding="utf-8")
    r = _run(f'refuse_finished_batch "{_posix(tmp_path)}" A1_HEADLESS_DONE outcome_a1_headless.json', tmp_path)
    assert r.returncode == 1 and "outcome_a1_headless.json" in r.stdout, r


@needs_bash
def test_incomplete_or_empty_root_is_allowed(tmp_path):
    (tmp_path / "H1_INCOMPLETE").write_text("x", encoding="utf-8")  # an unfinished batch may be re-run
    r = _run(f'refuse_finished_batch "{_posix(tmp_path)}" H1_DONE summary_h1.md', tmp_path)
    assert r.returncode == 0 and "PASSED" in r.stdout, r
    r = _run(f'refuse_finished_batch "{_posix(tmp_path / "missing")}" H1_DONE', tmp_path)
    assert r.returncode == 0 and "PASSED" in r.stdout, r


@needs_bash
def test_finished_interactive_arm_is_refused_and_untouched(tmp_path):
    out = tmp_path / "H1c-sm-int-ctl" / "out"
    out.mkdir(parents=True)
    (out / "observer.txt").write_text("arm=H1c-sm-int-ctl\nrecording_sha256=" + "ab" * 32 + "\n", encoding="utf-8")
    before = _snapshot(tmp_path)
    r = _run(f'refuse_finished_arm "{_posix(tmp_path / "H1c-sm-int-ctl")}"', tmp_path)
    assert r.returncode == 1 and "finished interactive arm" in r.stdout, r
    assert _snapshot(tmp_path) == before


@needs_bash
@pytest.mark.parametrize("observer", [None, "arm=x\nclaude_version=2.1.310 (Claude Code)\n"])
def test_prepared_or_absent_arm_is_allowed(tmp_path, observer):
    arm = tmp_path / "H1c-sm-int"
    if observer is not None:
        (arm / "out").mkdir(parents=True)
        (arm / "out" / "observer.txt").write_text(observer, encoding="utf-8")
    r = _run(f'refuse_finished_arm "{_posix(arm)}"', tmp_path)
    assert r.returncode == 0 and "PASSED" in r.stdout, r


# ---------------------------------------------------------------- call sites, from the source only

WRITE = re.compile(r'(^|\s)(mkdir -p|rm -f|exec >|tee |cp )|delete "\$ARM"|>> "\$OUT|> "\$OUT|^\{$|^cat > ')

CALLS = {
    "run_h1.sh": ['refuse_finished_batch "$LIVE" H1_DONE summary_h1.md'],
    "run_h1_probe.sh": ['refuse_finished_batch "$LIVE" H1_DONE summary_h1.md'],
    "run_a1_headless.sh": ['refuse_finished_batch "$LIVE" A1_HEADLESS_DONE outcome_a1_headless.json'],
    "run_a1_probe.sh": ['refuse_finished_batch "$LIVE" A1_HEADLESS_DONE outcome_a1_headless.json'],
    "prep_a1_interactive.sh": ['refuse_finished_batch "$LIVE" outcome_a1_interactive.json outcome_a1.json',
                               'refuse_finished_arm "$LIVE/$ARM"'],
    "finish_a1_interactive.sh": ['refuse_finished_batch "$LIVE" outcome_a1_interactive.json outcome_a1.json',
                                 'refuse_finished_arm "$LIVE/$ARM"'],
}


def _code_lines(script):
    """Executable lines only: comments and the heredoc-free header are skipped."""
    return [(i, l.strip()) for i, l in enumerate((HARNESS / script).read_text(encoding="utf-8").splitlines())
            if l.strip() and not l.strip().startswith("#")]


@pytest.mark.parametrize("script", sorted(CALLS))
def test_every_entry_point_guards_before_its_first_write(script):
    lines = _code_lines(script)
    src = next((i for i, l in lines if l == '. "$BASE/guard_finished.sh"'), None)
    assert src is not None, f"{script} does not source guard_finished.sh"
    first_write = next(i for i, l in lines if WRITE.search(l))
    for call in CALLS[script]:
        at = next((i for i, l in lines if l == call), None)
        assert at is not None, f"{script}: missing {call}"
        assert src < at < first_write, f"{script}: {call!r} at line {at + 1}, first write at line {first_write + 1}"


def test_interactive_steps_do_not_refuse_on_the_headless_markers():
    # The interactive pair follows the headless pair in the SAME root, so prep and
    # finish must key on the interactive outcomes only.
    for script in ("prep_a1_interactive.sh", "finish_a1_interactive.sh"):
        src = (HARNESS / script).read_text(encoding="utf-8")
        assert "A1_HEADLESS_DONE" not in src and "outcome_a1_headless.json" not in src, script


def test_finish_validates_observation_before_marking_the_arm_finished():
    # The recording hash marks an arm finished, so an incomplete observation.json must
    # be refused before that hash is written; finish then stays re-runnable.
    lines = _code_lines("finish_a1_interactive.sh")
    obs = next(i for i, l in lines if "observation.json: fill in booleans" in l)
    first_write = next(i for i, l in lines if WRITE.search(l) or l.startswith('} >> "$OUT/observer.txt"'))
    rec = next(i for i, l in lines if l.startswith('echo "recording_sha256='))
    assert obs < first_write and obs < rec, (obs, first_write, rec)


# ---------------------------------------------------------------- finish retry (review of #803), sandboxed

def _sandbox(tmp_path):
    """A copy of the harness whose A1 root is a temporary directory. Never the real root."""
    import sys
    h = tmp_path / "h"
    shutil.copytree(HARNESS, h, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "pins.local.env"))
    live = tmp_path / "live"
    live.mkdir()
    pa = h / "pins_a1.env"
    s = pa.read_text(encoding="utf-8")
    old = "LIVE='/c/dev/d5p2-h1c-a1-live'"
    assert s.count(old) == 1
    pa.write_text(s.replace(old, f"LIVE='{_posix(live)}'"), encoding="utf-8", newline="\n")
    (h / "pins.local.env").write_text(f"PY='{_posix(sys.executable)}'\n", encoding="utf-8", newline="\n")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("H1_", "A1_", "MNEME_")) and k not in ("CLAUDECODE", "DISABLE_AUTOUPDATER")}
    env["PATH"] = str(h / "selftest") + os.pathsep + env.get("PATH", "")
    # Safety: refuse to go on unless the copy's root really is the sandbox.
    r = subprocess.run([BASH, "-c", '. ./pins_a1.env; echo "$LIVE"'], cwd=h, env=env, capture_output=True, text=True)
    assert r.stdout.strip() == _posix(live), r
    return h, live, env


def _arm_for_finish(live, tmp_path, frames):
    arm = live / "H1c-sm-int-ctl"
    out = arm / "out"
    (out / "frames").mkdir(parents=True)
    (arm / "ws").mkdir()
    (arm / "ws" / "notes.txt").write_text("alpha\n", encoding="utf-8")
    (out / "observer.txt").write_text("arm=H1c-sm-int-ctl\nmode=interactive\nclaude_version=2.1.202 (Claude Code)\n",
                                      encoding="utf-8", newline="\n")
    (out / "frames" / "f1.png").write_bytes(b"PNGSTILL")
    tr = tmp_path / "session.jsonl"
    tr.write_text('{"type": "user"}\n', encoding="utf-8")
    import json
    (out / "hook-log.jsonl").write_text(json.dumps({"envelope": {"transcript_path": str(tr)}}) + "\n", encoding="utf-8")
    (out / "observation.json").write_text(json.dumps({
        "notice_visible": False, "notice_text_seen": "", "returned_to_input_prompt": True,
        "unexpected_prompt": False, "notes": "", "frames": frames}), encoding="utf-8")
    rec = tmp_path / "rec.mp4"
    rec.write_bytes(b"fake recording")
    return arm, out, rec


def _observer(out):
    return (out / "observer.txt").read_text(encoding="utf-8")


@needs_bash
def test_failed_finish_leaves_the_arm_retryable_then_completes(tmp_path):
    import hashlib
    import json
    h, live, env = _sandbox(tmp_path)
    arm, out, rec = _arm_for_finish(live, tmp_path, frames=["not-an-object"])  # template generation fails
    before = _observer(out)
    run = lambda: subprocess.run([BASH, "./finish_a1_interactive.sh", "H1c-sm-int-ctl", _posix(rec)],
                                 cwd=h, env=env, capture_output=True, text=True)
    r = run()
    assert r.returncode != 0 and "cannot write capture review template" in r.stdout, r
    assert _observer(out) == before, "a failed finish must not mark the arm finished"
    assert not (out / "capture_review.template.json").exists()
    g = _run(f'refuse_finished_arm "{_posix(arm)}"', tmp_path)
    assert g.returncode == 0 and "PASSED" in g.stdout, g  # still retryable

    # Fix the cause, run finish again: it completes, exactly once.
    o = json.loads((out / "observation.json").read_text(encoding="utf-8"))
    o["frames"] = [{"t": "00:05", "file": "frames/f1.png"}]
    (out / "observation.json").write_text(json.dumps(o), encoding="utf-8")
    r = run()
    assert r.returncode == 0 and "Finished H1c-sm-int-ctl" in r.stdout, r
    obs = _observer(out)
    sha = hashlib.sha256(rec.read_bytes()).hexdigest()
    assert obs.count("recording_sha256=") == 1 and f"recording_sha256={sha}" in obs, obs
    assert "transcript_collected=yes" in obs and (out / "transcript.jsonl").exists()
    tpl = json.loads((out / "capture_review.template.json").read_text(encoding="utf-8"))
    assert tpl["recording_sha256"] == sha and [f["file"] for f in tpl["frames"]] == ["frames/f1.png"]
    assert not (out / "capture_review.template.json.tmp").exists()

    # A third finish is refused as finished, and changes nothing.
    snap = _snapshot(arm)
    r = run()
    assert r.returncode == 1 and "finished interactive arm" in r.stdout, r
    assert _snapshot(arm) == snap


@needs_bash
def test_failed_transcript_copy_leaves_the_arm_retryable(tmp_path):
    h, live, env = _sandbox(tmp_path)
    arm, out, rec = _arm_for_finish(live, tmp_path, frames=[{"t": "00:05", "file": "frames/f1.png"}])
    # transcript.jsonl is a non-empty directory holding a directory of the source's name,
    # so `cp <file> <dir>` fails (cannot overwrite a directory with a file).
    (out / "transcript.jsonl" / "session.jsonl").mkdir(parents=True)
    before = _observer(out)
    r = subprocess.run([BASH, "./finish_a1_interactive.sh", "H1c-sm-int-ctl", _posix(rec)],
                       cwd=h, env=env, capture_output=True, text=True)
    assert r.returncode != 0 and "cannot copy transcript" in r.stdout, r
    assert _observer(out) == before and not (out / "capture_review.template.json").exists()


def test_finish_marks_the_arm_finished_last():
    lines = _code_lines("finish_a1_interactive.sh")
    mark = next(i for i, l in lines if l.startswith('echo "recording_sha256='))
    for needle in ('cp "$(cygpath -u "$TP")" "$OUT/transcript.jsonl"', "<<'PYEOF'"):
        at = next(i for i, l in lines if needle in l)
        assert at < mark, (needle, at, mark)
    assert sum(1 for _, l in lines if "recording_sha256=" in l and l.startswith("echo")) == 1


def test_guard_writes_nothing():
    src = GUARD.read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    code = re.sub(r'"[^"]*"', '""', code)  # message text and quoted paths are not commands
    assert not re.search(r"(^|[^2])>[^&]|\b(rm|mkdir|touch|tee|cp|mv)\b", code), "guard_finished.sh must be read-only"

"""Prepare and finish one operator-driven H4a (Antigravity) arm.

usage:
  h4a_arm.py prepare <live_root> <arm> [--selftest] [--antigravity <exe-or-version>]
  h4a_arm.py finish  <live_root> <arm> --recording <file> [--transcript <file>]

Arms (pre-registered order): ``h4a-A`` + ``h4a-A-ctl`` (candidate A,
``empty-stderr``), then ``h4a-B`` + ``h4a-B-ctl`` (candidate B,
``reason-only``). Every control arm runs the ``noop`` emitter.

H4a is IDE-only and operator-driven (probe scope section 5). ``prepare``
builds a disposable workspace and prints what the operator does in the IDE.
``finish`` records the after-state, copies the host transcript named in the
hook envelope (``transcriptPath``), binds the screen recording by SHA-256,
and requires a completed ``capture_review.json`` from a named reviewer.
Developer delivery is established only by that captured, reviewed run
(section 3.1); it is never inferred.

Nothing here starts a host session, and a live arm refuses to prepare
unless the installed Antigravity matches the pin.
"""
import argparse
import hashlib
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import check_pins  # noqa: E402

ARMS = {
    "h4a-A": ("A", "empty-stderr"), "h4a-A-ctl": ("A", "noop"),
    "h4a-B": ("B", "reason-only"), "h4a-B-ctl": ("B", "noop"),
}
MATCHER = "write_to_file|replace_file_content|multi_replace_file_content"
PROMPT = ("In notes.txt, replace the word alpha with beta, using your file-editing tool. "
          "Then, if you received any token beginning MNEME-PROBE- from a hook, a tool "
          "result or a system notice, repeat it verbatim; otherwise say: none.")
REVIEW_TEMPLATE = {
    "reviewer": "", "recording_sha256": "", "host_version_shown": "",
    "agent_ran_tool": None, "permission_prompt_shown": None,
    "host_error_or_block_shown": None, "nonce_seen_in_ui": None,
    "nonce_ui_location": "", "notes": "",
}


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(root: Path, arm: str, selftest: bool, antigravity: str) -> int:
    if arm not in ARMS:
        print(f"unknown arm {arm!r}; expected one of {sorted(ARMS)}", file=sys.stderr)
        return 2
    problems = common.guard_live_root(root)
    if not selftest:
        problems += common.guard_env()
        problems += common.antigravity_global_hooks()
        if not antigravity:
            problems.append("--antigravity <Antigravity.exe> is required for a live arm")
        else:
            ok, msg = check_pins.check("antigravity", antigravity)
            if not ok:
                problems.append(msg)
    if problems:
        print("h4a prepare refused:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    cand, mode = ARMS[arm]
    d = root / arm
    if d.exists():
        print(f"{d} exists: a prepared or finished arm is never reused", file=sys.stderr)
        return 1
    ws, out = d / "ws", d / "out"
    (ws / ".agents").mkdir(parents=True)
    out.mkdir(parents=True)
    (ws / "notes.txt").write_text("alpha\n", encoding="utf-8", newline="\n")
    cmd = f'"{sys.executable}" "{HERE / "h4a_emitter.py"}" {mode} "{out}"'
    common.write_json(ws / ".agents" / "hooks.json", {"mneme_probe": {"PreToolUse": [
        {"matcher": MATCHER, "hooks": [{"type": "command", "command": cmd, "timeout": 30}]}]}})
    if mode != "noop":
        (out / "nonce.txt").write_text(common.new_nonce() + "\n", encoding="utf-8", newline="\n")
    common.write_json(out / "probe.json", {
        "path": "H4a", "arm": arm, "candidate": cand, "mode": mode,
        "control": mode == "noop", "prompt": PROMPT, "matcher": MATCHER,
        "selftest": selftest, "prepared": common.now(),
        "pinned_version": check_pins.pins()["ANTIGRAVITY_VERSION"],
    })
    common.write_json(out / "capture_review.template.json", REVIEW_TEMPLATE)
    print(f"prepared {d}\n"
          f"operator: start a screen recording; open {ws} as the Antigravity workspace\n"
          f"          (workspace hooks only; no global ~/.gemini hooks), paste the prompt from\n"
          f"          {out / 'probe.json'}, let the agent finish, stop the recording, then run\n"
          f"          h4a_arm.py finish {root} {arm} --recording <file>\n"
          f"reviewer: copy capture_review.template.json to capture_review.json and fill it in.")
    return 0


def finish(root: Path, arm: str, recording: str, transcript: str) -> int:
    d = root / arm
    out, ws = d / "out", d / "ws"
    probe = common.read_json(out / "probe.json")
    if probe is None:
        print(f"{d} is not a prepared arm", file=sys.stderr)
        return 1
    if (out / "arm.json").exists():
        print(f"{d} is already finished", file=sys.stderr)
        return 1
    hooks = common.read_jsonl(out / "hook-log.jsonl")
    tpath = transcript or next((h.get("envelope", {}).get("transcriptPath") for h in hooks
                                if h.get("envelope", {}).get("transcriptPath")), None)
    copied = None
    if tpath and Path(tpath).is_file():
        copied = out / ("transcript" + (Path(tpath).suffix or ".txt"))
        shutil.copyfile(tpath, copied)
    rec = Path(recording) if recording else None
    notes = ws / "notes.txt"
    common.write_json(out / "arm.json", {
        "arm": arm, "finished": common.now(),
        "notes_after": notes.read_text(encoding="utf-8") if notes.is_file() else None,
        "transcript_copied": copied.name if copied else None,
        "transcript_source_given": bool(tpath),
        "recording_sha256": sha256(rec) if rec and rec.is_file() else None,
        "harness_sha256": {p.name: sha256(p) for p in sorted(HERE.glob("*.py"))},
    })
    print(f"finished {d}; a named reviewer must now complete {out / 'capture_review.json'}")
    return 0


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("prepare", "finish"))
    ap.add_argument("root")
    ap.add_argument("arm")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--antigravity", default="")
    ap.add_argument("--recording", default="")
    ap.add_argument("--transcript", default="")
    a = ap.parse_args(argv[1:])
    root = Path(a.root).resolve()
    if a.action == "prepare":
        return prepare(root, a.arm, a.selftest, a.antigravity)
    return finish(root, a.arm, a.recording, a.transcript)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

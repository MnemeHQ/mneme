"""Prepare and run one H6 (Hermes) arm; H6a and H6b are separate arms.

usage:
  h6_arm.py prepare <live_root> <arm> [--selftest]
  h6_arm.py run     <live_root> <arm> --selftest
  h6_arm.py run     <live_root> <arm> --live --hermes <exe> --python <py> --model <m> --provider <p>

Arms, each with its own nonce, session, HERMES_HOME and outcome:

  h6b    + h6b-ctl      H6b  pre_llm_call context injection          (1 turn)
  h6a-N  + h6a-N-ctl    H6a  candidate N: next-turn pre_llm_call      (2 turns)
  h6a-T  + h6a-T-ctl    H6a  candidate T: transform_tool_result       (1 turn)

H6a candidates are tried in that pre-registered order: N first, because it is
the shape the accepted probe scope names (section 4); T second, because
``transform_tool_result`` is a 0.19.0 surface the accepted contract does not
name (README, discrepancy D4).

**A live run is not authorized by this harness or its PR.** The live path
refuses unless every section 7 guard holds: the hermes-agent pin, no
``CLAUDECODE``, no ``MNEME_*`` variable, a disposable live root, a clean
harness, and at least one provider-credential variable present (its value is
never logged; the leak scan checks every evidence file). Each arm gets its
own ``HERMES_HOME``, so no user configuration, plugin or session is loaded.

Host flags used (present in ``hermes_cli/main.py`` at the 0.19.0 tag; their
runtime behavior is unverified until shape discovery): ``-z/--oneshot``,
``-m/--model``, ``--provider``, and ``-c/--continue`` for candidate N's
second turn.
"""
import argparse
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import check_pins  # noqa: E402

STUB = HERE / "selftest" / "stub_hermes.py"
ARMS = {
    "h6b": ("H6b", "context", "h6b-context", 1),
    "h6b-ctl": ("H6b", "context", "noop", 1),
    "h6a-T": ("H6a", "T", "h6a-transform", 1),
    "h6a-T-ctl": ("H6a", "T", "noop", 1),
    "h6a-N": ("H6a", "N", "h6a-next-turn", 2),
    "h6a-N-ctl": ("H6a", "N", "noop", 2),
}
PROMPT_1 = ("Use the write_file tool to overwrite notes.txt in the current directory with "
            "exactly the single line: beta. Then, if you received any token beginning "
            "MNEME-PROBE- from a hook, a tool result or injected context, repeat it "
            "verbatim; otherwise say: none.")
PROMPT_2 = ("If you received any token beginning MNEME-PROBE- from a hook, a tool result "
            "or injected context at any point, repeat it verbatim; otherwise say: none.")


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(root: Path, arm: str, selftest: bool) -> int:
    if arm not in ARMS:
        print(f"unknown arm {arm!r}; expected one of {sorted(ARMS)}", file=sys.stderr)
        return 2
    problems = common.guard_live_root(root)
    if problems:
        print("h6 prepare refused:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    path, cand, mode, turns = ARMS[arm]
    d = root / arm
    if d.exists():
        print(f"{d} exists: a prepared or finished arm is never reused", file=sys.stderr)
        return 1
    ws, out, home = d / "ws", d / "out", d / "home"
    out.mkdir(parents=True)
    home.mkdir(parents=True)
    ws.mkdir(parents=True)
    (ws / "notes.txt").write_text("alpha\n", encoding="utf-8", newline="\n")
    shutil.copytree(HERE / "h6_plugin", ws / ".hermes" / "plugins" / "mneme_probe",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (home / "config.yaml").write_text("plugins:\n  enabled:\n    - mneme_probe\n",
                                      encoding="utf-8", newline="\n")
    if mode != "noop":
        (out / "nonce.txt").write_text(common.new_nonce() + "\n", encoding="utf-8", newline="\n")
    prompts = [PROMPT_1] + ([PROMPT_2] if turns == 2 else [])
    common.write_json(out / "probe.json", {
        "path": path, "arm": arm, "candidate": cand, "mode": mode,
        "control": mode == "noop", "turns": turns, "prompts": prompts,
        "selftest": selftest, "prepared": common.now(),
        "pinned_version": check_pins.pins()["HERMES_AGENT_VERSION"],
    })
    print(f"prepared {d}")
    return 0


def _live_problems(a) -> list:
    p = common.guard_env()
    if not a.hermes or Path(a.hermes).resolve() == STUB.resolve():
        p.append("--hermes must name the real hermes executable, never the self-test stub")
    if not a.python:
        p.append("--python (the interpreter hermes-agent is installed in) is required")
    else:
        ok, msg = check_pins.check("hermes", a.python)
        if not ok:
            p.append(msg)
    if not (a.model and a.provider):
        p.append("--model and --provider are required for a live arm")
    names = check_pins.pins()["HERMES_CREDENTIAL_VARS"].split(",")
    if not any(os.environ.get(n) for n in names):
        p.append("no provider-credential variable is set (supplied by the operator only)")
    dirty = subprocess.run(["git", "status", "--porcelain", "--", str(HERE)],
                           capture_output=True, text=True, check=False).stdout.strip()
    if dirty:
        p.append("harness has uncommitted changes; a live run uses a committed harness only")
    return p


def dump_sessions(home: Path, out: Path) -> int:
    """Copy every SQLite file under HERMES_HOME and dump all rows as JSONL."""
    rows = 0
    for db in sorted(home.rglob("*.db")):
        shutil.copyfile(db, out / f"session.{db.stem}.db")
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            con.row_factory = sqlite3.Row
            tables = [r[0] for r in con.execute(
                "select name from sqlite_master where type='table'")]
            for t in tables:
                for r in con.execute(f'select * from "{t}"'):
                    rec = {"_db": db.name, "_table": t}
                    rec.update({k: (r[k] if not isinstance(r[k], bytes) else "<bytes>")
                                for k in r.keys()})
                    common.append_jsonl(out / "session.jsonl", rec)
                    rows += 1
        finally:
            con.close()
    return rows


def run(root: Path, arm: str, a) -> int:
    d = root / arm
    out, ws, home = d / "out", d / "ws", d / "home"
    probe = common.read_json(out / "probe.json")
    if probe is None or (out / "arm.json").exists():
        print(f"{d}: not prepared, or already run", file=sys.stderr)
        return 1
    if a.selftest == a.live:
        print("exactly one of --selftest or --live is required", file=sys.stderr)
        return 2
    if a.selftest:
        if not probe.get("selftest"):
            print("a live-prepared arm cannot be run against the stub", file=sys.stderr)
            return 1
        base = [sys.executable, str(STUB)]
        host_version = "selftest-stub"
    else:
        problems = _live_problems(a) + (["arm was prepared for selftest"] if probe.get("selftest") else [])
        if problems:
            print("h6 live run refused:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
        base = [a.hermes]
        host_version = check_pins.hermes_version(a.python)
    env = {k: v for k, v in os.environ.items() if not k.startswith("MNEME_")}
    env.update(HERMES_HOME=str(home), HERMES_ENABLE_PROJECT_PLUGINS="true")
    codes = []
    for i, prompt in enumerate(probe["prompts"], 1):
        cmd = base + ["-z", prompt]
        if not a.selftest:
            cmd += ["-m", a.model, "--provider", a.provider]
        if i > 1:
            cmd += ["-c"]
        proc = subprocess.run(cmd, cwd=ws, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=900)
        (out / f"turn{i}.stdout").write_text(proc.stdout, encoding="utf-8", newline="\n")
        (out / f"turn{i}.stderr").write_text(proc.stderr, encoding="utf-8", newline="\n")
        codes.append(proc.returncode)
    rows = dump_sessions(home, out)
    names = check_pins.pins()["HERMES_CREDENTIAL_VARS"].split(",")
    notes = ws / "notes.txt"
    common.write_json(out / "arm.json", {
        "arm": arm, "finished": common.now(), "host_version": host_version,
        "turn_exit_codes": codes, "session_rows": rows,
        "notes_after": notes.read_text(encoding="utf-8") if notes.is_file() else None,
        "credential_leaks": common.leak_scan(d, names),
        "harness_sha256": {p.name: sha256(p) for p in sorted(HERE.glob("*.py"))},
    })
    print(f"ran {d}: exit codes {codes}, {rows} session rows")
    return 0


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("prepare", "run"))
    ap.add_argument("root")
    ap.add_argument("arm")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--hermes", default="")
    ap.add_argument("--python", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--provider", default="")
    a = ap.parse_args(argv[1:])
    root = Path(a.root).resolve()
    if a.action == "prepare":
        return prepare(root, a.arm, a.selftest)
    return run(root, a.arm, a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

"""Prepare and run one H6 (Hermes) arm; H6a and H6b are separate arms.

usage:
  h6_arm.py prepare <live_root> <arm> [--selftest]
  h6_arm.py run     <live_root> <arm> --selftest
  h6_arm.py run     <live_root> <arm> --live --python <py> --model <m> --provider <p>

The host is never run in MoA mode or with ``api_mode == codex_app_server``:
only outside those does 0.19.0 persist the injected context as the user row's
``api_content`` (``agent/turn_context.py``), which is H6b's and N's host record.

Arms, each with its own nonce, session, HERMES_HOME and outcome:

  h6b    + h6b-ctl      H6b  pre_llm_call context injection          (1 turn)
  h6a-N  + h6a-N-ctl    H6a  candidate N: next-turn pre_llm_call      (2 turns)
  h6a-T  + h6a-T-ctl    H6a  candidate T: transform_tool_result       (1 turn)

H6a candidates are tried in that pre-registered order: N first, because it is
the shape the accepted probe scope names (section 4); T second, because
``transform_tool_result`` is a 0.19.0 surface the accepted contract does not
name (README, discrepancy D4).

**A live run is not authorized by this harness or its PR.** The live path
refuses unless every section 7 guard holds: the pinned live root, the
hermes-agent pin in ``--python`` (which is also the interpreter that runs the
host, ``python -m hermes_cli.main``), no ``CLAUDECODE``, no ``MNEME_*``
variable, a committed harness, and at least one provider-credential variable
present. The host gets an allowlisted environment: system variables, the
named credential variables and the arm's own ``HERMES_HOME``, so no user
configuration, plugin or session is loaded. The leak scan checks every
evidence file for the credential values.

Host invocation (flags present in ``hermes_cli/_parser.py`` at the 0.19.0 tag;
runtime behavior unverified until shape discovery): ``chat -Q -q <prompt>``
(non-interactive single query) and, for candidate N's second turn,
``--resume <session_id>`` with the session the plugin recorded in turn 1.
``-z/--oneshot`` is NOT used: it ignores ``--continue``/``--resume``
(``run_oneshot`` takes no session argument) and forces ``HERMES_YOLO_MODE=1``
and ``HERMES_ACCEPT_HOOKS=1`` (``hermes_cli/oneshot.py``).
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
    "h6a-N": ("H6a", "N", "h6a-next-turn", 2),
    "h6a-N-ctl": ("H6a", "N", "noop", 2),
    "h6a-T": ("H6a", "T", "h6a-transform", 1),
    "h6a-T-ctl": ("H6a", "T", "noop", 1),
}
PROMPT_1 = ("Use the write_file tool to overwrite notes.txt in the current directory with "
            "exactly the single line: beta. Then, if you received any token beginning "
            "MNEME-PROBE- from a hook, a tool result or injected context, repeat it "
            "verbatim; otherwise say: none.")
PROMPT_2 = ("If you received any token beginning MNEME-PROBE- from a hook, a tool result "
            "or injected context at any point, repeat it verbatim; otherwise say: none.")
SYSTEM_VARS = ("PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "WINDIR", "TEMP",
               "TMP", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA",
               "LANG", "LC_ALL", "HOME")
PAYLOAD_MAX = "10000000"  # observer sees complete messages; the model input is unaffected


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def credential_vars() -> list:
    return [v for v in check_pins.pins()["HERMES_CREDENTIAL_VARS"].split(",") if v]


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
    for p in (out, home, ws):
        p.mkdir(parents=True)
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


def harness_dirty() -> str:
    proc = subprocess.run(["git", "-C", str(HERE), "status", "--porcelain", "--", "."],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return "cannot verify the harness is committed (git status failed)"
    return "harness has uncommitted changes" if proc.stdout.strip() else ""


def _live_problems(root: Path, a) -> list:
    p = common.guard_env()
    want = Path(check_pins.pins()["LIVE_ROOT_W"]).resolve()
    if root != want:
        p.append(f"live root {root} is not the pinned live root {want}")
    if not a.python or not Path(a.python).is_file():
        p.append("--python must name the interpreter hermes-agent is installed in")
    else:
        ok, msg = check_pins.check("hermes", a.python)
        if not ok:
            p.append(msg)
    if not (a.model and a.provider):
        p.append("--model and --provider are required for a live arm")
    if not any(os.environ.get(n) for n in credential_vars()):
        p.append("no provider-credential variable is set (supplied by the operator only)")
    dirty = harness_dirty()
    if dirty:
        p.append(dirty)
    return p


def host_env(home: Path, selftest: bool) -> dict:
    keep = set(SYSTEM_VARS) | set(credential_vars())
    env = {k: v for k, v in os.environ.items() if k in keep}
    if selftest:
        env.update({k: v for k, v in os.environ.items() if k.startswith("STUB_H_")})
    env.update(HERMES_HOME=str(home), HERMES_ENABLE_PROJECT_PLUGINS="true",
               HERMES_PLUGIN_PAYLOAD_MAX_CHARS=PAYLOAD_MAX, PYTHONIOENCODING="utf-8")
    return env


def _plain_tables(con) -> list:
    """Ordinary tables only. FTS5 virtual tables (``messages_fts``,
    ``messages_fts_trigram`` in ``hermes_state.py`` at the 0.19.0 tag) and their
    shadow tables copy message text without a role, so dumping them would put
    the nonce in role-less rows; they are skipped."""
    rows = con.execute("select name, sql from sqlite_master where type='table'").fetchall()
    virtual = [n for n, sql in rows if (sql or "").upper().startswith("CREATE VIRTUAL TABLE")]
    return [n for n, _ in rows if n not in virtual and not n.startswith("sqlite_")
            and not any(n.startswith(v + "_") for v in virtual)]


def dump_sessions(home: Path, out: Path) -> int:
    """Back up every SQLite file under HERMES_HOME (WAL-safe) and dump all rows."""
    rows = 0
    for db in sorted(home.rglob("*.db")):
        copy = out / f"session.{db.stem}.db"
        src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        dst = sqlite3.connect(copy)
        try:
            src.backup(dst)
        finally:
            src.close()
        try:
            dst.row_factory = sqlite3.Row
            tables = _plain_tables(dst)
            for t in tables:
                for r in dst.execute(f'select * from "{t}"'):
                    rec = {"_db": db.name, "_table": t}
                    rec.update({k: (r[k] if not isinstance(r[k], bytes) else "<bytes>")
                                for k in r.keys()})
                    common.append_jsonl(out / "session.jsonl", rec)
                    rows += 1
        finally:
            dst.close()
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
        base, host_version = [sys.executable, str(STUB)], "selftest-stub"
    else:
        problems = _live_problems(root, a)
        if probe.get("selftest"):
            problems.append("arm was prepared for selftest")
        if problems:
            print("h6 live run refused:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
        base, host_version = [a.python, "-m", "hermes_cli.main"], check_pins.hermes_version(a.python)
    env = host_env(home, a.selftest)
    codes, notes = [], []
    for i, prompt in enumerate(probe["prompts"], 1):
        cmd = base + ["chat", "-Q", "-q", prompt]
        if not a.selftest:
            cmd += ["-m", a.model, "--provider", a.provider]
        if i > 1:
            sid = (common.read_json(out / "plugin-state.json") or {}).get("sessions") or []
            if not sid:
                notes.append(f"turn {i} not run: no session recorded in turn 1")
                break
            cmd += ["--resume", sid[0]]
        proc = subprocess.run(cmd, cwd=ws, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=900)
        (out / f"turn{i}.stdout").write_text(proc.stdout, encoding="utf-8", newline="\n")
        (out / f"turn{i}.stderr").write_text(proc.stderr, encoding="utf-8", newline="\n")
        codes.append(proc.returncode)
    rows = dump_sessions(home, out)
    nf = ws / "notes.txt"
    common.write_json(out / "arm.json", {
        "arm": arm, "finished": common.now(), "host_version": host_version,
        "turn_exit_codes": codes, "turns_planned": len(probe["prompts"]), "notes": notes,
        "session_rows": rows,
        "notes_after": nf.read_text(encoding="utf-8") if nf.is_file() else None,
        "credential_leaks": common.leak_scan(d, credential_vars()),
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

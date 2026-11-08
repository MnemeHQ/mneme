"""C4 observation witness and plumbing gate (harness-owned PreToolUse hook).

C4 derivative of ``c3_witness.py`` (#526). Exact delta: the environment
variables are ``C4_*`` instead of ``C4_*``; the watched file ``C4_WATCH_FILE`` is
a parameter the runner sets to the probe's local settings file
(``B/.claude/settings.local.json``, or ``A/...`` for ``D6-C4-V5-pre-own``); the
record's ``wrapper`` field is ``c4_witness``. ``watch_sha256`` is the literal
sentinel ``absent`` when the watched file does not exist (unchanged C3
behaviour, now relied on by plumbing-create). The runner's gate file is
``c4_gate.txt``.

Registered NEXT TO (never instead of) the unmodified Mneme hook wrapper
``hookwrap_v3.py``, on ``Read|Edit|Write|MultiEdit``, in the session
repository's project settings. It never influences a tool decision: it always
exits 0 with empty stdout and stderr, whatever happens. Errors go to a
``<log>.witness-errors`` sidecar.

Per hook call it records:
  - ``t`` at entry, tool name, ``tool_use_id``, ``session_id``, ``file_path``;
  - ``launch_id``: the C4_LAUNCH_ID the runner exported for exactly one
    ``claude`` invocation. Hooks inherit the host's environment, so two records
    with the same launch id came from the same live ``claude`` process, and a
    ``--resume`` run (a new process, C4(b)) carries a different one;
  - the hook process's ``MNEME_MEMORY`` (same allowlist as hookwrap_v3);
  - ``watch_sha256``: SHA-256 of C4_WATCH_FILE (the probe's
    ``.claude/settings.local.json``) at the moment of the call, or ``absent``.
    For the protected Edit this is the ordering witness: it shows which local
    settings bytes were on disk when the hook ran;
  - the process ancestry (pid, ppid, executable basename only) as
    corroboration of host process identity.

Plumbing gate (C4(a)-plumbing only): when C4_GATE_PATH is set and the call is a
Read of exactly that file, the witness writes ``<C4_SYNC_DIR>/request.json``
and waits (at most C4_GATE_WAIT seconds) for ``<C4_SYNC_DIR>/ack.json``. The ack
is written by ``settings_writer.py``, a process the runner started BEFORE
``claude``, only after it has written the local settings file. The settings
write is therefore done by the harness, not by the agent and not by any claude
descendant. On timeout the Read still proceeds; the classifier then records
NOT_EXECUTED rather than a negative propagation result.
"""
import hashlib
import json
import os
import sys
import time
import traceback

MNEME_VALUE_ALLOWLIST = ("MNEME_MEMORY", "MNEME_HOOK_MODE")


def _snapshot():
    """Map pid -> (ppid, exe basename) for the whole host, best effort."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
        k32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        snap = k32.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
        if not snap or snap == ctypes.c_void_p(-1).value:
            return {}
        procs = {}
        try:
            e = PROCESSENTRY32W()
            e.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            ok = k32.Process32FirstW(snap, ctypes.byref(e))
            while ok:
                procs[e.th32ProcessID] = (e.th32ParentProcessID, e.szExeFile)
                ok = k32.Process32NextW(snap, ctypes.byref(e))
        finally:
            k32.CloseHandle(snap)
        return procs
    procs = {}
    for d in os.listdir("/proc") if os.path.isdir("/proc") else []:
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/stat", encoding="utf-8") as f:
                stat = f.read()
            ppid = int(stat[stat.rindex(")") + 2:].split()[1])
            with open(f"/proc/{d}/comm", encoding="utf-8") as f:
                procs[int(d)] = (ppid, f.read().strip())
        except (OSError, ValueError):
            continue
    return procs


def ancestry(limit=12):
    procs = _snapshot()
    chain, pid, seen = [], os.getpid(), set()
    while pid and pid not in seen and len(chain) < limit:
        seen.add(pid)
        ppid, exe = procs.get(pid, (os.getppid() if pid == os.getpid() else None, None))
        chain.append({"pid": pid, "ppid": ppid, "exe": os.path.basename(exe) if exe else None})
        pid = ppid
    return chain


def sha256_file(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return "absent"


def same_path(a, b):
    return bool(a and b) and os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def write_atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj))
    os.replace(tmp, path)


def gate(payload, rec):
    sync = os.environ["C4_SYNC_DIR"]
    wait = float(os.environ.get("C4_GATE_WAIT", "30"))
    t_req = time.time()
    write_atomic(os.path.join(sync, "request.json"), {
        "t": t_req, "launch_id": rec["launch_id"], "tool_use_id": payload.get("tool_use_id")})
    ack_path = os.path.join(sync, "ack.json")
    ack = None
    while time.time() - t_req < wait:
        if os.path.exists(ack_path):
            try:
                with open(ack_path, encoding="utf-8") as f:
                    ack = json.load(f)
                break
            except (OSError, ValueError):
                pass
        time.sleep(0.05)
    rec["gate"] = {"t_request": t_req, "t_return": time.time(), "acked": ack is not None, "ack": ack,
                   "watch_sha256_after_gate": sha256_file(os.environ.get("C4_WATCH_FILE", ""))}


def main():
    log = os.environ.get("C4_WITNESS_LOG")
    try:
        t0 = time.time()
        raw = sys.stdin.read()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        ti = payload.get("tool_input") or {}
        mneme_keys = sorted(k for k in os.environ if k.upper().startswith("MNEME_"))
        rec = {
            "t": t0,
            "wrapper": "c4_witness",
            "launch_id": os.environ.get("C4_LAUNCH_ID"),
            "hook_event_name": payload.get("hook_event_name"),
            "tool_name": payload.get("tool_name"),
            "tool_use_id": payload.get("tool_use_id"),
            "session_id": payload.get("session_id"),
            "file_path": ti.get("file_path"),
            "MNEME_MEMORY": os.environ.get("MNEME_MEMORY"),
            "MNEME_present": mneme_keys,
            "MNEME_values": {k: os.environ[k] for k in mneme_keys if k in MNEME_VALUE_ALLOWLIST},
            "watch_sha256": sha256_file(os.environ.get("C4_WATCH_FILE", "")),
            "ancestry": ancestry(),
        }
        if (os.environ.get("C4_GATE_PATH") and os.environ.get("C4_SYNC_DIR")
                and payload.get("tool_name") == "Read"
                and same_path(ti.get("file_path"), os.environ["C4_GATE_PATH"])):
            gate(payload, rec)
        if log:
            with open(log, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
    except BaseException:  # never influence the tool decision
        try:
            if log:
                with open(log + ".witness-errors", "a", encoding="utf-8") as f:
                    f.write(f"{time.time()}\n{traceback.format_exc()}\n")
        except BaseException:
            pass
    os._exit(0)


if __name__ == "__main__":
    main()

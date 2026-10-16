"""External harness local-settings writer for C4(a)-plumbing.

usage: settings_writer.py <sync_dir> <edit|create> <settings_path> <mneme_memory_value> <timeout_s>

C4 derivative of the C3 ``settings_writer.py`` (#526). Exact delta: the target
path is still a parameter but is now the probe's ``.claude/settings.local.json``;
a ``<mode>`` argument is added; ``writer.json`` records the mode and allows the
before-hash sentinel ``absent``; the temp suffix is ``.c4tmp``. The two modes:

  edit    the file must exist and parse as a JSON object without an ``env`` key;
          adds ``env.MNEME_MEMORY = <value>`` keeping every other key, and
          replaces the file atomically. Refuses if an ``env`` key is present.
  create  the file must NOT exist; writes ``{"env": {"MNEME_MEMORY": <value>}}``
          as a new file (atomic, no-clobber). Refuses if it already exists.

A refusal writes ``writer.json`` with status ``refused`` and exits 4 without
writing the settings file or ``ack.json``; the runner then fails the probe.
Neither mode runs ``git add`` or ``git commit``: the local file stays
uncommitted.

The runner starts this process in the background BEFORE it launches ``claude``,
so it is never a descendant of the agent host. It waits for the witness gate's
``<sync_dir>/request.json`` (written when the agent Reads the gate file), then:

  1. hashes the local settings file (before; ``absent`` if it does not exist);
  2. edits or creates it as above (not committed: C4 is a mid-session write);
  3. hashes it again (after) and writes ``<sync_dir>/writer.json``;
  4. only then writes ``<sync_dir>/ack.json``, releasing the gate.

It exits without writing when ``<sync_dir>/stop`` appears (the runner creates it
after ``claude`` exits) or after <timeout_s>; writer.json then records
``no_request`` or ``timeout``. Nothing here ever edits app.py or a memory file.
"""
import hashlib
import json
import os
import sys
import time

sync, mode, settings, value, timeout = (sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4],
                                        float(sys.argv[5]))
if mode not in ("edit", "create"):
    sys.exit(f"settings_writer: bad mode {mode!r}")


def sha(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except FileNotFoundError:
        return "absent"


def write_atomic(path, text):
    tmp = path + ".c4tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    for _ in range(50):  # the host may hold the file open briefly on Windows
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05)
    os.replace(tmp, path)


def create_exclusive(path, text):
    """Atomic no-clobber create: a hard link fails if the target exists."""
    tmp = path + ".c4tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    try:
        os.link(tmp, path)
    finally:
        os.unlink(tmp)


def record(obj):
    write_atomic(os.path.join(sync, "writer.json"), json.dumps(obj, indent=2) + "\n")


t_start = time.time()
req_path = os.path.join(sync, "request.json")
while True:
    if os.path.exists(req_path):
        break
    if os.path.exists(os.path.join(sync, "stop")):
        record({"status": "no_request", "mode": mode, "t_start": t_start, "t_end": time.time()})
        sys.exit(0)
    if time.time() - t_start > timeout:
        record({"status": "timeout", "mode": mode, "t_start": t_start, "t_end": time.time()})
        sys.exit(0)
    time.sleep(0.02)

t_seen = time.time()
try:
    with open(req_path, encoding="utf-8") as f:
        request = json.load(f)
except (OSError, ValueError):
    request = None
before = sha(settings)


def refuse(why):
    record({"status": "refused", "mode": mode, "reason": why, "t_start": t_start,
            "t_request_seen": t_seen, "settings_sha256_before": before, "request": request})
    sys.exit(4)


if mode == "edit":
    if before == "absent":
        refuse("edit mode: local settings file does not exist")
    try:
        with open(settings, encoding="utf-8") as f:
            s = json.load(f)
    except ValueError:
        refuse("edit mode: local settings file is not valid JSON")
    if not isinstance(s, dict):
        refuse("edit mode: local settings file is not a JSON object")
    if "env" in s:
        refuse("edit mode: an env key is already present")
    s["env"] = {"MNEME_MEMORY": value}
    write_atomic(settings, json.dumps(s, indent=2))
else:
    if before != "absent" or os.path.lexists(settings):
        refuse("create mode: local settings file already exists")
    try:
        create_exclusive(settings, json.dumps({"env": {"MNEME_MEMORY": value}}, indent=2))
    except FileExistsError:
        refuse("create mode: local settings file appeared before the write")
t_write = time.time()
after = sha(settings)
record({"status": "written", "mode": mode,
        "writer": "settings_writer.py (started by the runner before claude)",
        "writer_process": {"pid": os.getpid()}, "t_start": t_start, "t_request_seen": t_seen,
        "t_write_done": t_write, "settings_sha256_before": before, "settings_sha256_after": after,
        "value": value, "request": request})
write_atomic(os.path.join(sync, "ack.json"),
             json.dumps({"t_ack": time.time(), "t_write_done": t_write, "settings_sha256_after": after}))

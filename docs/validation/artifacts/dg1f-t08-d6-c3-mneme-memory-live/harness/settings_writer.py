"""External harness settings writer for C3(a)-plumbing.

usage: settings_writer.py <sync_dir> <settings_path> <mneme_memory_value> <timeout_s>

The runner starts this process in the background BEFORE it launches ``claude``,
so it is never a descendant of the agent host. It waits for the witness gate's
``<sync_dir>/request.json`` (written when the agent Reads the gate file), then:

  1. hashes the session repo's ``.claude/settings.json`` (before);
  2. adds ``env.MNEME_MEMORY = <value>`` keeping every other key, and replaces
     the file atomically (not committed: C3 is a mid-session write);
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

sync, settings, value, timeout = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def write_atomic(path, text):
    tmp = path + ".c3tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    for _ in range(50):  # the host may hold the file open briefly on Windows
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05)
    os.replace(tmp, path)


def record(obj):
    write_atomic(os.path.join(sync, "writer.json"), json.dumps(obj, indent=2) + "\n")


t_start = time.time()
req_path = os.path.join(sync, "request.json")
while True:
    if os.path.exists(req_path):
        break
    if os.path.exists(os.path.join(sync, "stop")):
        record({"status": "no_request", "t_start": t_start, "t_end": time.time()})
        sys.exit(0)
    if time.time() - t_start > timeout:
        record({"status": "timeout", "t_start": t_start, "t_end": time.time()})
        sys.exit(0)
    time.sleep(0.02)

t_seen = time.time()
try:
    with open(req_path, encoding="utf-8") as f:
        request = json.load(f)
except (OSError, ValueError):
    request = None
before = sha(settings)
with open(settings, encoding="utf-8") as f:
    s = json.load(f)
s["env"] = {**(s.get("env") or {}), "MNEME_MEMORY": value}
write_atomic(settings, json.dumps(s, indent=2))
t_write = time.time()
after = sha(settings)
record({"status": "written", "writer": "settings_writer.py (started by the runner before claude)",
        "writer_process": {"pid": os.getpid()},"t_start": t_start, "t_request_seen": t_seen,
        "t_write_done": t_write, "settings_sha256_before": before, "settings_sha256_after": after,
        "value": value, "request": request})
write_atomic(os.path.join(sync, "ack.json"),
             json.dumps({"t_ack": time.time(), "t_write_done": t_write, "settings_sha256_after": after}))

"""Post-hoc replay for a T-08 G3 probe (charter §6 item 6). Replay, not observation.

usage: replay_g3.py <out-dir> <mneme-src>

Runs the pinned build's ``mneme check`` twice, with the hook's own arguments
(``hook.py`` ``_invoke_check``: ``--memory``, ``--input`` holding the
introduced delta, ``--query "edit to <file_path>"``, ``--mode strict``,
``--json``, ``--target-path``):

- ``foreign``: against the foreign memory from ``setup.json`` (must give a
  complete PASS; corroborates the live checker result, item 5);
- ``own``: against the probe repository's own memory (must give a complete
  FAIL with C3-DEC). The live hook never evaluated this memory, so this is the
  only evidence that the edit was forbidden for its own repository.

The introduced delta is computed by the pinned hook's ``introduced_between``
from ``target.before`` and the planned edit, as the hook does for an Edit.
Writes ``<out-dir>/replay-g3.json`` with the argv (paths as run), exit codes
and the allowlisted payload fields. Classification is ``classify_c3.py``'s.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from observe import PAYLOAD_FIELDS  # noqa: E402

RUN_CLI = ("import sys; sys.path.insert(0, sys.argv[1]); from mneme.cli import main; "
           "raise SystemExit(main(sys.argv[2:]))")


def check(python: str, src: str, memory: Path, delta: Path, file_path: str) -> dict:
    argv = ["check", "--memory", str(memory), "--input", str(delta),
            "--query", f"edit to {file_path}", "--mode", "strict", "--json",
            "--target-path", file_path]
    proc = subprocess.run([python, "-E", "-P", "-c", RUN_CLI, src, *argv],
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    record: dict = {"argv": argv, "exit": proc.returncode,
                    "memory_sha256": hashlib.sha256(memory.read_bytes()).hexdigest()}
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        record["payload"] = None
        record["stderr_tail"] = proc.stderr[-400:]
        return record
    kept = {k: payload.get(k) for k in PAYLOAD_FIELDS if k in payload}
    kept["schema"] = payload.get("schema")
    kept["decision_ids"] = sorted({
        v["decision_id"] for v in payload.get("violations") or []
        if isinstance(v, dict) and isinstance(v.get("decision_id"), str)})
    record["payload"] = kept
    return record


def main() -> int:
    out, src = Path(sys.argv[1]), sys.argv[2]
    setup = json.loads((out / "setup.json").read_text(encoding="utf-8"))
    plan, g3 = setup["plan"], setup["g3"]
    if plan["tool"] != "Edit":
        raise SystemExit("replay_g3.py handles the Edit plan only (charter O3)")
    sys.path.insert(0, src)
    from mneme.integrations.claude_code.hook import introduced_between

    before = (out / "target.before").read_text(encoding="utf-8")
    proposed = before.replace(plan["old_string"], plan["new_string"], 1)
    delta_text = introduced_between(before, proposed)
    record: dict = {"kind": "replay (charter §6 item 6), not observation",
                    "introduced_delta": delta_text}
    with tempfile.TemporaryDirectory() as tmp:
        delta = Path(tmp) / "delta.txt"
        delta.write_text(delta_text, encoding="utf-8")
        own = Path(setup["repo"]) / ".mneme" / "project_memory.json"
        record["foreign"] = check(sys.executable, src, Path(g3["foreign_memory"]), delta,
                                  plan["file_path"])
        record["own"] = check(sys.executable, src, own, delta, plan["file_path"])
    (out / "replay-g3.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(out / "replay-g3.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

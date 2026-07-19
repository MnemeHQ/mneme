# Mneme for Claude Code Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Package the existing v0.3.x `mneme` CLI as a Claude Code integration so that architectural decisions are enforced automatically via `PreToolUse` hooks before Claude Code edits files, with slash commands and a skill front door for discovery.

**Architecture:** A thin shim (`mneme.integrations.claude_code.hook`) reads Claude Code's PreToolUse JSON event from stdin, filters to file-mutating tools (Edit/Write/MultiEdit), **applies the proposed edits against the existing file content to produce the full post-edit file**, materializes that to a temp file, and shells out to the existing `mneme check` CLI. The shim **fails open on execution errors** (mneme missing, file IO error, timeout) — Claude Code is only blocked when `mneme check` actually returns a verdict. Hook config templates, slash commands, and a SKILL.md ship as static assets installed into the user's `.claude/` directory by an installer script. **No engine changes. No new product surface.** This is packaging.

**Tech Stack:** Python 3.11+, pytest, existing `mneme` console_script entry point, Claude Code hook protocol (stdin JSON → exit 0=allow / exit 2=block).

**Scope discipline (validation mode):** Per `project_mneme_stage.md`, the project is in validation mode after v0.3.0. This work qualifies as packaging only because it shells out to the shipped CLI — no new engine code, no new features. **Versioned as v0.3.2, not v0.4.0.** If any task here starts to require engine changes, stop and re-evaluate against the validation gate.

**Working directory for all paths:** `C:\dev\mneme\mneme-project-memory\` (this is where the `mneme` package and `pyproject.toml` live; the parent `C:\dev\mneme\` is the marketing/site repo).

**Time-box:** 2–3 working days. If Task 11 onward starts dragging, ship Tasks 1–10 as v0.3.2-rc1 and treat the rest as a follow-up. **If you hit day 4, stop and re-evaluate against the validation gate** — at that point this is no longer packaging.

---

## Pre-flight: Branch and structure

### Task 0: Create branch and integration directory skeleton

**Files:**
- Create: `mneme/integrations/__init__.py` (empty)
- Create: `mneme/integrations/claude_code/__init__.py` (empty)
- Create: `tests/integrations/__init__.py` (empty)
- Create: `tests/integrations/claude_code/__init__.py` (empty)
- Create: `integrations/claude-code/` (directory for static assets — hook template, commands, skill)

**Step 1: Branch from main**

```bash
cd C:/dev/mneme/mneme-project-memory
git checkout main
git pull --ff-only
git status --short  # expect clean
git checkout -b claude-code-integration
```

Expected: branch created, no uncommitted changes.

**Step 2: Create directories with empty package files**

```bash
mkdir -p mneme/integrations/claude_code
mkdir -p tests/integrations/claude_code
mkdir -p integrations/claude-code/{commands,skills/mneme}
touch mneme/integrations/__init__.py
touch mneme/integrations/claude_code/__init__.py
touch tests/integrations/__init__.py
touch tests/integrations/claude_code/__init__.py
```

**Step 3: Verify pytest still discovers existing tests**

Run: `pytest -q`
Expected: all 117 existing tests pass, 0 new tests collected from the new dirs (they're empty).

**Step 4: Commit skeleton**

```bash
git add mneme/integrations tests/integrations integrations/
git commit -m "chore: scaffold mneme.integrations.claude_code package"
```

---

### Task 1: Verify Claude Code PreToolUse JSON envelope shape

**Why this exists:** The hook contract is the load-bearing assumption for Tasks 2–9. Confirm the schema before writing parsing code against it.

**Files:**
- Create: `docs/integrations/claude-code-hook-spec.md` (reference notes, not user-facing docs)

**Step 1: Fetch the current Claude Code hooks reference**

Open `https://docs.claude.com/en/docs/claude-code/hooks` (or the latest equivalent). Confirm:

- `PreToolUse` events deliver JSON on stdin with at least: `session_id`, `transcript_path`, `cwd`, `hook_event_name` (= `"PreToolUse"`), `tool_name`, `tool_input` (object).
- For `Edit`: `tool_input.file_path`, `tool_input.old_string`, `tool_input.new_string`.
- For `Write`: `tool_input.file_path`, `tool_input.content`.
- For `MultiEdit`: `tool_input.file_path`, `tool_input.edits` (array of `{old_string, new_string}`).
- Exit code semantics: `0` = allow, `2` = block (stderr surfaced to model), other non-zero = error.

**Step 2: Capture confirmed shape**

Write the verified envelope and per-tool input shapes into `docs/integrations/claude-code-hook-spec.md` as canonical reference for Tasks 2–9. **If the live docs disagree with anything above, update the doc and stop — adjust the rest of the plan before proceeding.**

**Step 3: Commit**

```bash
git add docs/integrations/claude-code-hook-spec.md
git commit -m "docs(integrations): capture Claude Code PreToolUse hook spec"
```

---

## Hook shim: TDD

### Task 2: Parse the PreToolUse envelope (pure parser, no IO)

**Why pure:** Keep `parse_event` free of file IO so it's trivially testable. Materialization (reading the existing file and applying edits) is a separate function added in Task 3.5.

**Files:**
- Test: `tests/integrations/claude_code/test_hook_parser.py`
- Modify: `mneme/integrations/claude_code/hook.py` (will be created in Task 3)

**Step 1: Write the failing test**

```python
# tests/integrations/claude_code/test_hook_parser.py
import json
import pytest
from mneme.integrations.claude_code.hook import parse_event, ToolEvent


def test_parse_edit_event():
    raw = json.dumps({
        "session_id": "abc",
        "transcript_path": "/tmp/t.jsonl",
        "cwd": "/repo",
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/repo/app.py",
            "old_string": "def f(): pass",
            "new_string": "def f(): return 1",
        },
    })
    event = parse_event(raw)
    assert isinstance(event, ToolEvent)
    assert event.tool_name == "Edit"
    assert event.file_path == "/repo/app.py"
    assert event.tool_input["old_string"] == "def f(): pass"
    assert event.tool_input["new_string"] == "def f(): return 1"


def test_parse_write_event():
    raw = json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "cwd": "/repo",
        "tool_input": {"file_path": "/repo/new.py", "content": "x = 1\n"},
    })
    event = parse_event(raw)
    assert event.tool_name == "Write"
    assert event.tool_input["content"] == "x = 1\n"


def test_parse_multiedit_event():
    raw = json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "MultiEdit",
        "cwd": "/repo",
        "tool_input": {
            "file_path": "/repo/a.py",
            "edits": [
                {"old_string": "a", "new_string": "b"},
                {"old_string": "c", "new_string": "d"},
            ],
        },
    })
    event = parse_event(raw)
    assert event.tool_name == "MultiEdit"
    assert len(event.tool_input["edits"]) == 2
```

**Step 2: Run the test, expect ImportError**

Run: `pytest tests/integrations/claude_code/test_hook_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mneme.integrations.claude_code.hook'`.

---

### Task 3: Implement the parser

**Files:**
- Create: `mneme/integrations/claude_code/hook.py`

**Step 1: Minimal implementation**

```python
# mneme/integrations/claude_code/hook.py
"""Claude Code hook shim — translates PreToolUse events into mneme check calls."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class ToolEvent:
    tool_name: str
    file_path: str
    cwd: str
    tool_input: Dict[str, Any]


def parse_event(raw: str) -> ToolEvent:
    payload = json.loads(raw)
    tool_input = payload.get("tool_input", {}) or {}
    return ToolEvent(
        tool_name=payload["tool_name"],
        file_path=tool_input.get("file_path", ""),
        cwd=payload.get("cwd", ""),
        tool_input=tool_input,
    )
```

**Step 2: Run tests, expect PASS**

Run: `pytest tests/integrations/claude_code/test_hook_parser.py -v`
Expected: 3 passed.

**Step 3: Commit**

```bash
git add mneme/integrations/claude_code/hook.py tests/integrations/claude_code/test_hook_parser.py
git commit -m "feat(claude-code): parse PreToolUse envelopes (pure, no IO)"
```

---

### Task 3.5: Materialize post-edit full file content

**Why:** `mneme check` scores text against decisions. Passing only `new_string` strips context, causes false positives, and concatenating `MultiEdit` `new_string` chunks produces incoherent text. Apply edits against existing file content to produce the actual post-edit file the user would see committed.

**Files:**
- Test: `tests/integrations/claude_code/test_materialize.py`
- Modify: `mneme/integrations/claude_code/hook.py`

**Step 1: Write the failing test**

```python
# tests/integrations/claude_code/test_materialize.py
import pytest
from mneme.integrations.claude_code.hook import (
    ToolEvent,
    materialize_proposed_content,
    MaterializeError,
)


def _evt(tool, file_path, **input_extra):
    return ToolEvent(tool_name=tool, file_path=str(file_path), cwd="", tool_input={"file_path": str(file_path), **input_extra})


def test_write_returns_full_content_even_when_file_absent(tmp_path):
    target = tmp_path / "new.py"  # does not exist
    event = _evt("Write", target, content="import sqlite3\n")
    assert materialize_proposed_content(event) == "import sqlite3\n"


def test_edit_applies_replacement_against_real_file(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("import os\n\ndef f():\n    return None\n", encoding="utf-8")
    event = _evt("Edit", target, old_string="return None", new_string="return 1")
    out = materialize_proposed_content(event)
    assert "import os" in out          # surrounding context preserved
    assert "return 1" in out
    assert "return None" not in out


def test_multiedit_applies_edits_in_order(tmp_path):
    target = tmp_path / "db.py"
    target.write_text("X = 0\nY = 0\n", encoding="utf-8")
    event = _evt(
        "MultiEdit", target,
        edits=[
            {"old_string": "X = 0", "new_string": "X = 1"},
            {"old_string": "Y = 0", "new_string": "Y = 2"},
        ],
    )
    out = materialize_proposed_content(event)
    assert out == "X = 1\nY = 2\n"


def test_edit_raises_when_file_missing(tmp_path):
    event = _evt("Edit", tmp_path / "missing.py", old_string="a", new_string="b")
    with pytest.raises(MaterializeError):
        materialize_proposed_content(event)


def test_edit_raises_when_old_string_not_found(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("hello\n", encoding="utf-8")
    event = _evt("Edit", target, old_string="missing", new_string="x")
    with pytest.raises(MaterializeError):
        materialize_proposed_content(event)
```

**Step 2: Run, expect FAIL**

Run: `pytest tests/integrations/claude_code/test_materialize.py -v`
Expected: ImportError on `materialize_proposed_content` / `MaterializeError`.

**Step 3: Implement**

Add to `mneme/integrations/claude_code/hook.py`:

```python
from pathlib import Path


class MaterializeError(Exception):
    """Raised when proposed content cannot be reconstructed (file missing,
    old_string not found, etc.). Caller should fail open."""


def materialize_proposed_content(event: ToolEvent) -> str:
    ti = event.tool_input
    if event.tool_name == "Write":
        return ti.get("content", "")

    file_path = ti.get("file_path", "")
    if not file_path:
        raise MaterializeError("missing file_path")

    try:
        original = Path(file_path).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as e:
        raise MaterializeError(f"cannot read {file_path}: {e}") from e

    if event.tool_name == "Edit":
        old, new = ti.get("old_string", ""), ti.get("new_string", "")
        if old not in original:
            raise MaterializeError("old_string not found in file")
        return original.replace(old, new, 1)

    if event.tool_name == "MultiEdit":
        content = original
        for i, edit in enumerate(ti.get("edits", [])):
            old, new = edit.get("old_string", ""), edit.get("new_string", "")
            if old not in content:
                raise MaterializeError(f"edit[{i}].old_string not found")
            content = content.replace(old, new, 1)
        return content

    raise MaterializeError(f"unsupported tool: {event.tool_name}")
```

**Step 4: Run, expect PASS**

Run: `pytest tests/integrations/claude_code/ -v`
Expected: parser tests + 5 materialize tests, all green.

**Step 5: Commit**

```bash
git add mneme/integrations/claude_code/hook.py tests/integrations/claude_code/test_materialize.py
git commit -m "feat(claude-code): reconstruct post-edit full file content for Edit/MultiEdit"
```

---

### Task 4: Skip non-mutating tools (failing test)

**Step 1: Append to `test_hook_parser.py`**

```python
from mneme.integrations.claude_code.hook import should_check


def test_should_check_only_mutating_tools():
    assert should_check("Edit") is True
    assert should_check("Write") is True
    assert should_check("MultiEdit") is True
    assert should_check("Read") is False
    assert should_check("Bash") is False
    assert should_check("Glob") is False
```

**Step 2: Run, expect ImportError**

Run: `pytest tests/integrations/claude_code/test_hook_parser.py::test_should_check_only_mutating_tools -v`
Expected: FAIL.

**Step 3: Implement in `mneme/integrations/claude_code/hook.py`**

```python
_MUTATING_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})

def should_check(tool_name: str) -> bool:
    return tool_name in _MUTATING_TOOLS
```

**Step 4: Run, expect PASS. Commit.**

```bash
git add -u
git commit -m "feat(claude-code): gate hook to mutating tools only"
```

---

### Task 5: Memory discovery (failing test)

**Step 1: Write test**

```python
# tests/integrations/claude_code/test_memory_discovery.py
from pathlib import Path
import pytest
from mneme.integrations.claude_code.hook import find_memory


def test_find_memory_returns_none_when_absent(tmp_path):
    assert find_memory(tmp_path) is None


def test_find_memory_finds_dotmneme(tmp_path):
    mem = tmp_path / ".mneme" / "project_memory.json"
    mem.parent.mkdir()
    mem.write_text('{"decisions": []}')
    assert find_memory(tmp_path) == mem


def test_find_memory_walks_up(tmp_path):
    mem = tmp_path / ".mneme" / "project_memory.json"
    mem.parent.mkdir()
    mem.write_text('{"decisions": []}')
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    assert find_memory(nested) == mem


def test_find_memory_respects_env(tmp_path, monkeypatch):
    custom = tmp_path / "custom.json"
    custom.write_text('{"decisions": []}')
    monkeypatch.setenv("MNEME_MEMORY", str(custom))
    assert find_memory(tmp_path) == custom
```

**Step 2: Run, expect FAIL.**

**Step 3: Implement**

```python
# add to hook.py
import os
from pathlib import Path
from typing import Optional


def find_memory(start: Path) -> Optional[Path]:
    env = os.environ.get("MNEME_MEMORY")
    if env:
        p = Path(env)
        return p if p.is_file() else None
    cur = Path(start).resolve()
    while True:
        candidate = cur / ".mneme" / "project_memory.json"
        if candidate.is_file():
            return candidate
        if cur.parent == cur:
            return None
        cur = cur.parent
```

**Step 4: Run, expect PASS. Commit.**

```bash
git add -u
git commit -m "feat(claude-code): discover .mneme/project_memory.json via walk-up + env"
```

---

### Task 6: End-to-end `main()` — no memory = exit 0 (failing test)

**Files:**
- Test: `tests/integrations/claude_code/test_hook_main.py`

**Step 1: Write test**

```python
# tests/integrations/claude_code/test_hook_main.py
import json
import io
import pytest
from mneme.integrations.claude_code.hook import main


def _envelope(tool="Edit", cwd="/nonexistent", file_path="/nonexistent/x.py"):
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "cwd": cwd,
        "tool_input": {"file_path": file_path, "old_string": "a", "new_string": "b"},
    })


def test_no_memory_returns_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    rc = main(stdin=io.StringIO(_envelope(cwd=str(tmp_path), file_path=str(tmp_path / "x.py"))))
    assert rc == 0


def test_non_mutating_tool_returns_zero(tmp_path):
    rc = main(stdin=io.StringIO(_envelope(tool="Read", cwd=str(tmp_path))))
    assert rc == 0
```

**Step 2: Run, expect FAIL (no `main`).**

**Step 3: Implement skeleton**

```python
# add to hook.py
import sys
from typing import TextIO


def main(stdin: TextIO = sys.stdin, stderr: TextIO = sys.stderr) -> int:
    try:
        raw = stdin.read()
        event = parse_event(raw)
    except (json.JSONDecodeError, KeyError) as e:
        print(f"mneme-hook: bad envelope: {e}", file=stderr)
        return 0  # never block on shim errors

    if not should_check(event.tool_name):
        return 0

    memory = find_memory(Path(event.cwd or "."))
    if memory is None:
        return 0

    try:
        proposed_content = materialize_proposed_content(event)
    except MaterializeError as e:
        print(f"mneme-hook: cannot materialize content, failing open: {e}", file=stderr)
        return 0

    return _run_check(event, proposed_content, memory, stderr)


def _run_check(event, proposed_content, memory, stderr) -> int:
    return 0  # filled in next task
```

**Step 4: Run, expect PASS. Commit.**

```bash
git add -u
git commit -m "feat(claude-code): hook main() entrypoint, no-op when memory missing"
```

---

### Task 7: Subprocess invocation of `mneme check` — fail-open on execution errors

**Reliability contract:**
- `mneme check` ran and returned a verdict (any returncode) → that's the product. In strict mode, non-zero → block (exit 2). In warn mode, always exit 0.
- `mneme check` could not be executed (binary missing, OSError, timeout) → **fail open, exit 0**, log to stderr. Bricking Claude Code on a missing binary is unacceptable.

**Step 1: Append tests**

```python
# in test_hook_main.py
from unittest.mock import patch, MagicMock
import subprocess


def _project_with_memory(tmp_path):
    mem = tmp_path / ".mneme" / "project_memory.json"
    mem.parent.mkdir()
    mem.write_text('{"decisions": []}')
    target = tmp_path / "x.py"
    target.write_text("import os\n", encoding="utf-8")
    return mem, target


def _edit_envelope(tmp_path, target):
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "cwd": str(tmp_path),
        "tool_input": {
            "file_path": str(target),
            "old_string": "import os",
            "new_string": "import psycopg2",
        },
    })


def test_strict_fail_returns_two(tmp_path):
    mem, target = _project_with_memory(tmp_path)
    fake = MagicMock(returncode=2, stdout="FAIL: violates mneme_001", stderr="")
    with patch("mneme.integrations.claude_code.hook.subprocess.run", return_value=fake) as mrun:
        rc = main(stdin=io.StringIO(_edit_envelope(tmp_path, target)))
    assert rc == 2
    args = mrun.call_args.args[0]
    assert args[0] == "mneme" and args[1] == "check"
    assert "--memory" in args and str(mem) in args
    assert "--mode" in args


def test_strict_warn_returncode_blocks(tmp_path):
    """In strict mode, mneme check returncode 1 (WARN) should block."""
    mem, target = _project_with_memory(tmp_path)
    fake = MagicMock(returncode=1, stdout="WARN", stderr="")
    with patch("mneme.integrations.claude_code.hook.subprocess.run", return_value=fake):
        rc = main(stdin=io.StringIO(_edit_envelope(tmp_path, target)))
    assert rc == 2


def test_warn_mode_never_blocks(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    mem, target = _project_with_memory(tmp_path)
    # mneme check in warn mode always returns 0 anyway, but assert we don't escalate
    fake = MagicMock(returncode=0, stdout="WARN", stderr="")
    with patch("mneme.integrations.claude_code.hook.subprocess.run", return_value=fake):
        rc = main(stdin=io.StringIO(_edit_envelope(tmp_path, target)))
    assert rc == 0


def test_mneme_not_on_path_fails_open(tmp_path, capfd):
    mem, target = _project_with_memory(tmp_path)
    with patch(
        "mneme.integrations.claude_code.hook.subprocess.run",
        side_effect=FileNotFoundError("mneme"),
    ):
        rc = main(stdin=io.StringIO(_edit_envelope(tmp_path, target)))
    assert rc == 0
    captured = capfd.readouterr()
    assert "mneme" in (captured.out + captured.err).lower()


def test_subprocess_oserror_fails_open(tmp_path):
    mem, target = _project_with_memory(tmp_path)
    with patch(
        "mneme.integrations.claude_code.hook.subprocess.run",
        side_effect=OSError("permission denied"),
    ):
        rc = main(stdin=io.StringIO(_edit_envelope(tmp_path, target)))
    assert rc == 0


def test_subprocess_timeout_fails_open(tmp_path):
    mem, target = _project_with_memory(tmp_path)
    with patch(
        "mneme.integrations.claude_code.hook.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="mneme", timeout=10),
    ):
        rc = main(stdin=io.StringIO(_edit_envelope(tmp_path, target)))
    assert rc == 0
```

**Step 2: Run, expect FAIL.**

**Step 3: Implement `_run_check` with fail-open boundary**

```python
# replace _run_check stub in hook.py
import subprocess
import tempfile

_CHECK_TIMEOUT_SECONDS = 10


def _run_check(event: ToolEvent, proposed_content: str, memory: Path, stderr) -> int:
    mode = os.environ.get("MNEME_HOOK_MODE", "strict")
    if mode not in ("strict", "warn"):
        mode = "strict"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(proposed_content)
        input_path = tf.name

    try:
        rel = event.file_path or "(unknown)"
        try:
            proc = subprocess.run(
                [
                    "mneme", "check",
                    "--memory", str(memory),
                    "--input", input_path,
                    "--query", f"edit to {rel}",
                    "--mode", mode,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=_CHECK_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            print(
                "mneme-hook: 'mneme' not found on PATH. "
                "Install with `pip install mneme` or unset the hook. Failing open.",
                file=stderr,
            )
            return 0
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"mneme-hook: check could not run ({e}). Failing open.", file=stderr)
            return 0

        # We have a real verdict from mneme check.
        if proc.stdout:
            print(proc.stdout, file=stderr)
        if proc.stderr:
            print(proc.stderr, file=stderr)
        # mneme check exits: 0=PASS, 1=WARN (strict), 2=FAIL (strict).
        # In warn mode it always returns 0.
        return 2 if proc.returncode != 0 else 0
    finally:
        try:
            os.unlink(input_path)
        except OSError:
            pass
```

**Step 4: Run, expect PASS.**

Run: `pytest tests/integrations/claude_code/ -v`
Expected: all parser, materialize, and main tests green.

**Step 5: Commit**

```bash
git add -u
git commit -m "feat(claude-code): subprocess to mneme check; fail open on exec errors"
```

---

### Task 8: Console-script entrypoint

**Files:**
- Modify: `pyproject.toml` (add `[project.scripts]` entry)
- Modify: `mneme/integrations/claude_code/hook.py` (add `if __name__ == "__main__"`)

**Step 1: Add entry point to `pyproject.toml`**

Locate the existing `[project.scripts]` block:

```toml
[project.scripts]
mneme = "mneme.cli:main"
```

Change to:

```toml
[project.scripts]
mneme = "mneme.cli:main"
mneme-hook = "mneme.integrations.claude_code.hook:cli_main"
```

**Step 2: Add `cli_main` to `hook.py`**

```python
# at bottom of hook.py
def cli_main() -> None:
    sys.exit(main())


if __name__ == "__main__":
    cli_main()
```

**Step 3: Reinstall in editable mode and verify**

Run:
```bash
pip install -e .
mneme-hook --help 2>&1 | head -5  # may not have --help; that's fine
echo '{"hook_event_name":"PreToolUse","tool_name":"Read","cwd":".","tool_input":{}}' | mneme-hook
echo "exit code: $?"
```

Expected: exit code 0 (Read is non-mutating).

**Step 4: Commit**

```bash
git add pyproject.toml mneme/integrations/claude_code/hook.py
git commit -m "feat(claude-code): expose mneme-hook console script"
```

---

### Task 9: End-to-end fixture test (real `mneme check` subprocess)

**Files:**
- Create: `tests/integrations/claude_code/fixtures/project_memory.json`
- Create: `tests/integrations/claude_code/test_hook_e2e.py`

**Step 1: Fixture memory with one constraint**

```json
{
  "version": "1.0",
  "decisions": [
    {
      "id": "test_001",
      "decision": "Use SQLite for local storage",
      "rationale": "single-file portability",
      "scope": ["storage"],
      "constraints": ["no postgres"],
      "anti_patterns": ["postgres", "Postgres", "psycopg2"]
    }
  ]
}
```

**Step 2: Test that calls real `mneme` binary (skip if not installed)**

```python
# tests/integrations/claude_code/test_hook_e2e.py
import json
import io
import shutil
import subprocess
from pathlib import Path
import pytest
from mneme.integrations.claude_code.hook import main

FIXTURE = Path(__file__).parent / "fixtures" / "project_memory.json"


SEED_OLD = "# placeholder import line\n"


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    target = tmp_path / "db.py"
    target.write_text(SEED_OLD, encoding="utf-8")
    return tmp_path, target


def _envelope(cwd, file_path, new_string):
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "cwd": str(cwd),
        "tool_input": {
            "file_path": str(file_path),
            "old_string": SEED_OLD.rstrip("\n"),
            "new_string": new_string,
        },
    })


@pytest.mark.skipif(shutil.which("mneme") is None, reason="mneme CLI not on PATH")
def test_violation_blocks(project, capfd):
    cwd, target = project
    rc = main(stdin=io.StringIO(_envelope(cwd, target, "import psycopg2")))
    assert rc == 2
    out = capfd.readouterr()
    assert "test_001" in (out.out + out.err) or "psycopg2" in (out.out + out.err)


@pytest.mark.skipif(shutil.which("mneme") is None, reason="mneme CLI not on PATH")
def test_compliant_passes(project):
    cwd, target = project
    rc = main(stdin=io.StringIO(_envelope(cwd, target, "import sqlite3")))
    assert rc == 0
```

**Step 3: Run**

Run: `pytest tests/integrations/claude_code/ -v`
Expected: all pass (or skip cleanly if `mneme` not on PATH in CI — fix by ensuring `pip install -e .` ran first).

**Step 4: Run full suite to confirm no regressions**

Run: `pytest -q`
Expected: 117 + new tests, all green.

**Step 5: Commit**

```bash
git add tests/integrations/claude_code/
git commit -m "test(claude-code): end-to-end hook against real mneme check"
```

---

## Static assets: hook template, slash commands, skill

### Task 10: Hook config template

**Files:**
- Create: `integrations/claude-code/hooks.json`
- Create: `integrations/claude-code/README.md`

**Step 1: Write template**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "mneme-hook"
          }
        ]
      }
    ]
  }
}
```

**Step 2: Write integration README**

```markdown
# Mneme for Claude Code

Architectural governance for Claude Code. Enforces project decisions
automatically before Edit/Write/MultiEdit operations.

## Quick install

1. `pip install mneme`  (or `pip install -e .` from this repo)
2. Run the installer: `python scripts/install_claude_code.py`
3. Confirm: edit a file in Claude Code that violates a decision in
   `.mneme/project_memory.json` — Claude Code should be blocked with
   the decision id in the error message.

## What gets installed

- `mneme-hook` command on `$PATH` (via pip).
- `.claude/settings.json` PreToolUse hook entry.
- `.claude/commands/mneme-*.md` slash commands.
- `.claude/skills/mneme/SKILL.md` discovery skill.

## Modes

- `MNEME_HOOK_MODE=strict` (default): block on conflict.
- `MNEME_HOOK_MODE=warn`: surface warning, never block.
```

**Step 3: Commit**

```bash
git add integrations/claude-code/
git commit -m "feat(claude-code): ship hook template and integration README"
```

---

### Task 11: Slash commands

**Files:**
- Create: `integrations/claude-code/commands/mneme-check.md`
- Create: `integrations/claude-code/commands/mneme-context.md`
- Create: `integrations/claude-code/commands/mneme-record.md`
- Create: `integrations/claude-code/commands/mneme-review.md`

**Step 1: Write `mneme-check.md`**

```markdown
---
description: Run mneme check against the current working file or staged changes
---

Run `mneme check` against the current project memory.

If the user names a file, check that file's contents against
`.mneme/project_memory.json`. Otherwise, ask which file or scope.

Use Bash tool: `mneme check --memory .mneme/project_memory.json --input <path> --query "<scope>" --mode strict`

Report PASS/WARN/FAIL clearly. On FAIL, name the violated decision id.
```

**Step 2: Write `mneme-context.md`**

```markdown
---
description: Retrieve relevant decisions from project memory for the current task
---

Use Bash tool to run:
`mneme test_query --memory .mneme/project_memory.json --query "<user's task description>"`

Surface the top decisions and their constraints so the user can see what
governs the current work.
```

**Step 3: Write `mneme-record.md`**

```markdown
---
description: Record a new architectural decision into project memory
---

Ask the user for: id (snake_case), decision (one sentence), rationale,
scope (list), constraints (list), anti_patterns (list).

Then run via Bash:
`mneme add_decision --memory .mneme/project_memory.json --id <id> --decision "<...>" --rationale "<...>" [--scope ...] [--constraint ...] [--anti-pattern ...]`

Confirm with `mneme list_decisions --memory .mneme/project_memory.json`.
```

**Step 4: Write `mneme-review.md`**

```markdown
---
description: Review the current diff against project memory
---

Run `git diff` to capture pending changes, then for each modified file
run `mneme check` against the new content. Aggregate verdicts and
report any decisions violated, with file:line citations where possible.
```

**Step 5: Commit**

```bash
git add integrations/claude-code/commands/
git commit -m "feat(claude-code): ship /mneme-{check,context,record,review} slash commands"
```

---

### Task 12: Skill front door

**Files:**
- Create: `integrations/claude-code/skills/mneme/SKILL.md`

**Step 1: Write SKILL.md**

```markdown
---
name: mneme
description: |
  Architectural governance for this project. Use this skill when the user
  asks about project decisions, architectural constraints, or wants to
  enforce / record / review decisions. Also use whenever Claude Code is
  about to make a non-trivial edit and the project has a `.mneme/`
  directory — check decisions first.
---

# Mneme — project memory & governance

This project uses Mneme to enforce architectural decisions.

## When this skill activates
- User mentions "ADR", "decision", "constraint", "anti-pattern".
- A `.mneme/project_memory.json` file exists in the repo.
- About to edit a file in a scope governed by a recorded decision.

## How to use it
1. Before non-trivial edits, run `/mneme context` with the task description.
2. To gate a draft, run `/mneme check` against the proposed content.
3. To record a new decision, run `/mneme record` and capture rationale.
4. To audit pending changes, run `/mneme review`.

## Hook enforcement
A `PreToolUse` hook (`mneme-hook`) runs automatically on Edit/Write/MultiEdit.
If the proposed change violates a decision in strict mode, Claude Code is
blocked and the violated decision id is surfaced.

To switch modes: `export MNEME_HOOK_MODE=warn`.

## Related
- Project memory: `.mneme/project_memory.json`
- CLI reference: `mneme --help`
- Docs: https://github.com/TheoV823/mneme
```

**Step 2: Commit**

```bash
git add integrations/claude-code/skills/
git commit -m "feat(claude-code): ship discovery skill (SKILL.md)"
```

---

### Task 13: Installer script

**Files:**
- Create: `scripts/install_claude_code.py`

**Step 1: Write installer**

```python
#!/usr/bin/env python3
"""Install Mneme integration into the user's Claude Code config.

Idempotent. Prints a diff-style preview and asks for confirmation before
writing. Targets `.claude/` in the current working directory by default
(project-scoped); pass --user for `~/.claude/`.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS = REPO_ROOT / "integrations" / "claude-code"


def _merge_settings(target: Path, template: dict) -> dict:
    existing = {}
    if target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
    hooks = existing.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])
    # idempotency: don't double-add our matcher
    for entry in pre:
        if entry.get("matcher") == "Edit|Write|MultiEdit" and any(
            h.get("command") == "mneme-hook" for h in entry.get("hooks", [])
        ):
            return existing
    pre.extend(template["hooks"]["PreToolUse"])
    return existing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", action="store_true", help="Install to ~/.claude instead of ./.claude")
    ap.add_argument("--yes", action="store_true", help="Skip confirmation")
    args = ap.parse_args()

    base = Path.home() / ".claude" if args.user else Path.cwd() / ".claude"
    settings_path = base / "settings.json"
    commands_dir = base / "commands"
    skills_dir = base / "skills" / "mneme"

    template = json.loads((ASSETS / "hooks.json").read_text(encoding="utf-8"))
    merged = _merge_settings(settings_path, template)

    print(f"Will install Mneme integration to: {base}")
    print(f"  - {settings_path}  (merge PreToolUse hook)")
    print(f"  - {commands_dir}/mneme-*.md  (4 slash commands)")
    print(f"  - {skills_dir}/SKILL.md  (discovery skill)")
    if not args.yes:
        resp = input("Proceed? [y/N] ").strip().lower()
        if resp != "y":
            print("Aborted.")
            return 1

    base.mkdir(parents=True, exist_ok=True)
    commands_dir.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)

    settings_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    for cmd in (ASSETS / "commands").glob("*.md"):
        shutil.copy(cmd, commands_dir / cmd.name)
    shutil.copy(ASSETS / "skills" / "mneme" / "SKILL.md", skills_dir / "SKILL.md")

    print("Done. Restart Claude Code to pick up new hooks/commands/skills.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Smoke-test locally**

```bash
mkdir -p /tmp/mneme-install-test && cd /tmp/mneme-install-test
python C:/dev/mneme/mneme-project-memory/scripts/install_claude_code.py --yes
ls .claude/commands && ls .claude/skills/mneme && cat .claude/settings.json
```

Expected: 4 command files, 1 skill file, settings.json contains the PreToolUse hook entry.

Run a second time and confirm idempotency (settings.json should not gain a duplicate entry).

**Step 3: Commit**

```bash
git add scripts/install_claude_code.py
git commit -m "feat(claude-code): idempotent installer script for .claude/ assets"
```

---

## Documentation and release

### Task 14: README + positioning

**Files:**
- Modify: `mneme-project-memory/README.md`
- Create: `mneme-project-memory/docs/integrations/claude-code.md`

**Step 1: Add a "Mneme for Claude Code" section near the top of `README.md`**

Insert after the existing tagline / first paragraph:

```markdown
## Mneme for Claude Code

Architectural governance for [Claude Code](https://docs.claude.com/claude-code).
Enforce ADRs and engineering constraints automatically — before drift
reaches your repo.

```bash
pip install mneme
python scripts/install_claude_code.py        # project-scoped: writes to ./.claude/
# or: python scripts/install_claude_code.py --user   # writes to ~/.claude/
```

This installs a `PreToolUse` hook so every Edit/Write/MultiEdit is checked
against `.mneme/project_memory.json` in strict mode by default. See
[docs/integrations/claude-code.md](docs/integrations/claude-code.md) for
details.
```

**Step 2: Write `docs/integrations/claude-code.md`**

Cover: positioning ("Architectural Governance for Claude Code"), the hook-as-hero framing, install steps, the four slash commands, mode switching (`MNEME_HOOK_MODE`), troubleshooting (mneme not on PATH, memory file missing, false positives → switch to warn mode while iterating).

Keep it tight — one page.

**Step 3: Commit**

```bash
git add README.md docs/integrations/claude-code.md
git commit -m "docs(claude-code): position integration as Architectural Governance for Claude Code"
```

---

### Checkpoint before Task 15: Stop, review, decide

**Do not proceed past this point automatically.** This is the gate between "code complete" and "release."

**Step 1: Diff review**

```bash
git checkout claude-code-integration
git diff main...claude-code-integration --stat
git log main..claude-code-integration --oneline
```

Read the full diff. Look for:
- Any engine changes that snuck in (anything outside `mneme/integrations/claude_code/`, `tests/integrations/claude_code/`, `integrations/claude-code/`, `scripts/install_claude_code.py`, `pyproject.toml`, `README.md`, `docs/integrations/`). If yes → this is no longer packaging; reassess scope.
- Comments / docstrings that overstate what the integration does.
- Any remaining `proposed_content` references on `ToolEvent` (should be removed after Task 3.5 refactor).

**Step 2: Full test suite**

```bash
pip install -e .
pytest -q
```

Expected: all 117 prior tests + new tests green. **No skips except the documented `mneme not on PATH` skipif.**

**Step 3: Manual smoke test** (Git Bash on Windows, or any POSIX shell on macOS/Linux)

Cross-platform path-portable script. Run from the repo root (`mneme-project-memory/`):

```bash
SMOKE=$(mktemp -d) && cd "$SMOKE"
mkdir .mneme
cp "$OLDPWD/tests/integrations/claude_code/fixtures/project_memory.json" .mneme/
printf 'import os\n' > target.py

ENVELOPE=$(python -c "
import json, os
print(json.dumps({
  'hook_event_name': 'PreToolUse',
  'tool_name': 'Edit',
  'cwd': os.getcwd(),
  'tool_input': {
    'file_path': os.path.join(os.getcwd(), 'target.py'),
    'old_string': 'import os',
    'new_string': 'import psycopg2',
  },
}))")

# (a) Block path: mneme on PATH, violation expected.
echo "$ENVELOPE" | mneme-hook
echo "exit code: $?"   # expect 2; stderr should cite test_001 or psycopg2
```

Expected: exit 2, stderr cites decision id `test_001`.

```bash
# (b) Fail-open path: invoke shim with mneme NOT on PATH.
# Use env to scope PATH only to the pipeline's right-hand side.
echo "$ENVELOPE" | env -i PATH="/usr/bin:/bin" PYTHONPATH="$OLDPWD" python -m mneme.integrations.claude_code.hook
echo "exit code: $?"   # expect 0; stderr should mention 'mneme' not found
```

Expected: exit 0, stderr says `mneme` not found and the hook is failing open.

**Note on Windows:** the snippets above require Git Bash, MSYS2, or WSL. CMD/PowerShell users should run the equivalent via `pytest tests/integrations/claude_code/test_hook_main.py -v` — the test suite covers both block and fail-open paths via mocking and is the authoritative check; the manual smoke just verifies the installed `mneme-hook` console script is wired up end-to-end.

**Step 4: Decision**

Three exit options. Pick one explicitly before proceeding to Task 15:

1. **Ship as v0.3.2** → continue to Task 15.
2. **Ship as v0.3.2-rc1** (Tasks 1–10 only, defer commands/skill/installer) → tag rc1, proceed to validation hand-off without Task 15 finalization.
3. **Don't ship** (something feels wrong, install path is weird, scope crept) → write a short retro in `docs/plans/2026-05-03-mneme-for-claude-code-retro.md` and stop.

Document the decision in the merge commit body in Task 15.

---

### Task 15: Cut v0.3.2

**Files:**
- Modify: `pyproject.toml` (`version = "0.3.2"`)
- Modify: `CHANGELOG.md` (if exists; create entry otherwise)

**Step 1: Bump version**

In `pyproject.toml`, change:
```toml
version = "0.1.0"
```
to:
```toml
version = "0.3.2"
```

(Verify the existing version first — memory says v0.3.1 was tagged in the parent repo. If `pyproject.toml` is still at `0.1.0`, the tags are in git but the package metadata wasn't being bumped; bump it now to `0.3.2` to match.)

**Step 2: Run the full suite one more time**

Run: `pytest -q`
Expected: all green.

**Step 3: Confirm console scripts work**

```bash
pip install -e .
mneme list_decisions --memory examples/project_memory.json | head -5
mneme-hook < /dev/null  # should error gracefully on empty stdin, exit 0
```

**Step 4: Commit, tag, push**

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "release: v0.3.2 — Mneme for Claude Code (packaging)"
git checkout main
git merge --no-ff claude-code-integration -m "Merge: Mneme for Claude Code v0.3.2"
git tag -a v0.3.2 -m "Mneme for Claude Code: PreToolUse hook + slash commands + skill"
git push origin main
git push origin v0.3.2
```

**Step 5: Create GitHub release**

```bash
gh release create v0.3.2 --title "v0.3.2 — Mneme for Claude Code" --notes-file - <<'EOF'
Architectural governance for Claude Code, packaged.

- PreToolUse hook (`mneme-hook`) blocks Edit/Write/MultiEdit on decision violations
- Slash commands: /mneme-check, /mneme-context, /mneme-record, /mneme-review
- Discovery SKILL.md
- One-line installer: `python scripts/install_claude_code.py`

No engine changes — shells out to existing `mneme check` v0.3.x.

Modes: `MNEME_HOOK_MODE=strict` (default) | `warn`
EOF
```

---

## Validation hand-off (post-ship)

This is the actual point of the work. After v0.3.2 is tagged:

1. Update `project_mneme_stage.md` memory: testers can now install via Claude Code in one line.
2. Track in the existing tester table: column `Tried Claude Code install? Y/N`, column `Hook caught a real violation? Y/N`.
3. **Decision gate trigger:** if 3+ testers report the hook fired correctly on real work, that's the strong validation signal the stage memory describes — proceed to v0.4 planning. If 0–1 testers install at all, the wedge is wrong and we go back to repositioning.

**Do not start v0.4 work in this branch.** Validation gate first.

---

## Out of scope (explicitly)

These were considered and cut to keep the scope thin:

- Marketplace listing / plugin packaging — depends on Anthropic surface that may not exist; revisit only after v0.3.2 has install signal.
- Cursor/Copilot/Gemini analogues — same packaging pattern but separate plans.
- Reading `transcript_path` to enrich the retrieval `--query` with recent user/assistant turns. Cheap improvement (~30 lines) but cut for v1; tune via docs once testers report retrieval misses.
- Caching `mneme check` results across rapid edit bursts — premature; measure before optimizing.
- Telemetry / install counter — privacy decisions need their own plan.

If any of these start feeling load-bearing during execution, **stop and re-plan**. They are not in this plan for a reason.

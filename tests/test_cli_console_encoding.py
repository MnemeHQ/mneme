"""Regression tests for issue #253 — CLI output under a legacy console codepage.

`mneme test_query` crashed with UnicodeEncodeError on Windows' default cp1252
console. The issue proposed replacing "the unicode arrow" in the explanation
string with ASCII, but there is no such character in mneme's source: the arrow
comes from the *user's memory data*. ADR-005, ADR-014 and ADR-001 all carry
U+2192 in their imported decision text in this repo's own
`.mneme/project_memory.json`.

Decision text is arbitrary user content, so no amount of source-level ASCII
discipline fixes this. The output stream itself has to be able to carry it.
That makes it a `main()`-level concern rather than a per-subcommand one: every
subcommand that renders a decision can hit it.

These run the CLI in a subprocess with PYTHONIOENCODING forced to cp1252,
because the crash is a property of the real stdout encoding and pytest's
capture replaces stdout with a UTF-8-capable object.
"""
import json
import subprocess
import sys

import pytest

# U+2192 RIGHTWARDS ARROW: the exact character from the issue's traceback.
ARROW = "→"

NON_ASCII_MEMORY = {
    "meta": {"name": "encoding-test", "description": "non-ascii fixture"},
    "items": [],
    "examples": [],
    "decisions": [
        {
            "id": "arrow_001",
            "decision": f"Route requests client {ARROW} gateway {ARROW} service",
            "rationale": f"explicit hop order {ARROW} easier tracing",
            "scope": ["routing"],
            "constraints": ["no direct client-to-service calls"],
            "anti_patterns": ["bypass gateway"],
        },
    ],
}


@pytest.fixture
def memory(tmp_path):
    p = tmp_path / "project_memory.json"
    # ensure_ascii=False writes the raw character, matching how real memory
    # files carry it once an ADR with an arrow has been imported.
    p.write_text(json.dumps(NON_ASCII_MEMORY, ensure_ascii=False), encoding="utf-8")
    return p


def _run(args):
    """Invoke the CLI in a subprocess pinned to a cp1252 stdout."""
    return subprocess.run(
        [sys.executable, "-m", "mneme", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**_base_env(), "PYTHONIOENCODING": "cp1252"},
    )


def _base_env():
    import os
    env = dict(os.environ)
    env.pop("PYTHONIOENCODING", None)
    return env


def test_test_query_survives_legacy_console_codepage(memory):
    """The reported crash: test_query renders decision text and died on it."""
    r = _run([
        "test_query", "--memory", str(memory), "--query", "routing gateway",
    ])
    assert "UnicodeEncodeError" not in r.stderr, (
        f"test_query crashed on non-ASCII decision text:\n{r.stderr}"
    )
    assert r.returncode == 0
    # The command must reach its final section, not die partway through.
    assert "Injected" in r.stdout


def test_check_survives_legacy_console_codepage(memory, tmp_path):
    """`check` prints decision_text for every violation, so it is exposed too."""
    target = tmp_path / "handler.py"
    target.write_text("we bypass gateway here\n", encoding="utf-8")
    r = _run([
        "check", "--memory", str(memory), "--input", str(target),
        "--query", "routing gateway", "--mode", "warn",
    ])
    assert "UnicodeEncodeError" not in r.stderr, (
        f"check crashed on non-ASCII decision text:\n{r.stderr}"
    )
    assert "Result:" in r.stdout

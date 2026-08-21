"""Missing-path handling for the mneme CLI.

Ordinary user errors (missing --memory / --input paths) must produce a
clean ``ERROR: ...`` message on stderr and exit 2 — never a raw traceback.
Exit 2 for usage errors follows argparse's own convention; verdict exit
codes 0/1/2 remain reserved for actual enforcement results.

The hook contract is exercised directly: a failed invocation must yield
*no valid verdict payload* (empty stdout), so ``hook.parse_verdict``
returns None and the Claude Code integration fails open exactly as it
does today.
"""
import json

import pytest

from mneme.cli import main
from mneme.integrations.claude_code.hook import parse_verdict


MEMORY_ARGS = ["--memory", "no_such_memory.json"]


def _run(capsys, argv):
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.parametrize("argv", [
    ["list_decisions", *MEMORY_ARGS],
    ["add_decision", *MEMORY_ARGS, "--id", "x1", "--decision", "d"],
    ["test_query", *MEMORY_ARGS, "--query", "q"],
    ["cursor", "generate", *MEMORY_ARGS, "--query", "q"],
])
def test_missing_memory_is_clean_error(capsys, argv):
    code, out, err = _run(capsys, argv)
    assert code == 2
    assert "ERROR:" in err
    assert "no_such_memory.json" in err
    assert "Traceback" not in err
    assert out == ""


def test_check_missing_input_is_clean_error(capsys, tmp_path):
    memory = tmp_path / "project_memory.json"
    memory.write_text(json.dumps({
        "meta": {"name": "t", "description": "t"},
        "items": [], "examples": [], "decisions": [],
    }), encoding="utf-8")
    code, out, err = _run(capsys, [
        "check",
        "--memory", str(memory),
        "--input", "does_not_exist.txt",
        "--query", "storage",
        "--mode", "strict",
    ])
    assert code == 2
    assert "ERROR:" in err
    assert "does_not_exist.txt" in err
    assert "Traceback" not in err
    assert out == ""


def test_check_missing_memory_is_clean_error(capsys, tmp_path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("hello", encoding="utf-8")
    code, out, err = _run(capsys, [
        "check",
        "--memory", str(tmp_path / "absent.json"),
        "--input", str(prompt),
        "--query", "storage",
        "--mode", "strict",
    ])
    assert code == 2
    assert "ERROR:" in err
    assert "absent.json" in err
    assert "Traceback" not in err
    assert out == ""


def test_check_json_missing_path_yields_no_verdict_payload(capsys, tmp_path):
    """Hook fail-open contract: a failed check must not emit a payload.

    The Claude Code hook trusts only parseable ``mneme.check/v1`` output;
    empty stdout must therefore parse to None so the hook fails open,
    exactly as it does against today's crash tracebacks.
    """
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("hello", encoding="utf-8")
    code, out, err = _run(capsys, [
        "check",
        "--memory", str(tmp_path / "absent.json"),
        "--input", str(prompt),
        "--query", "storage",
        "--mode", "strict",
        "--json",
    ])
    assert code == 2
    assert out == ""
    assert "ERROR:" in err
    assert parse_verdict(out) is None

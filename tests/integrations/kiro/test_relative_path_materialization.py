"""#571: a relative Kiro ``fs_write`` path resolves against the payload ``cwd``
for the snapshot as well as ``--target-path``, whatever the hook process cwd."""
import io
import json

from mneme.integrations.kiro.hook import main
from tests.integrations.relative_paths import FORBIDDEN, TARGET, VIOLATING, make_layout


def _run(cwd, path, content):
    envelope = json.dumps({
        "hook_event_name": "preToolUse",
        "cwd": str(cwd),
        "tool_name": "fs_write",
        "tool_input": {"path": path, "content": content},
    })
    out, err = io.StringIO(), io.StringIO()
    rc = main(stdin=io.StringIO(envelope), stderr=err, stdout=out)
    return rc, out.getvalue(), err.getvalue()


def test_relative_write_identical_decoy_blocked(tmp_path, monkeypatch):
    layout = make_layout(tmp_path, monkeypatch)
    layout.decoy(VIOLATING)
    rc, _out, err = _run(layout.project, TARGET, VIOLATING)
    assert rc != 0
    assert FORBIDDEN in err or "router_001" in err


def test_relative_write_decoy_with_forbidden_line_blocked(tmp_path, monkeypatch):
    layout = make_layout(tmp_path, monkeypatch)
    layout.decoy(f"{FORBIDDEN} = True\n")
    rc, _out, _err = _run(layout.project, TARGET, VIOLATING)
    assert rc != 0


def test_relative_write_diffs_against_real_target(tmp_path, monkeypatch):
    layout = make_layout(tmp_path, monkeypatch)
    layout.real().write_text(VIOLATING, encoding="utf-8")
    rc, out, _err = _run(layout.project, TARGET, VIOLATING + "RETRIES = 2\n")
    assert rc == 0
    assert "UNEVALUATED" not in out

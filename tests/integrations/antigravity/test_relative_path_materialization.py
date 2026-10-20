"""#571: a relative ``TargetFile`` resolves against ``workspacePaths[0]`` for
the snapshot as well as ``--target-path``, whatever the hook process cwd."""
import io
import json

from mneme.integrations.antigravity import adapter
from tests.integrations.relative_paths import FORBIDDEN, TARGET, VIOLATING, make_layout


def _invoke(workspace, target, content):
    raw = json.dumps({
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": target, "CodeContent": content},
        },
        "workspacePaths": [str(workspace)],
    })
    out, err = io.StringIO(), io.StringIO()
    adapter.main(stdin=io.StringIO(raw), stderr=err, stdout=out)
    return json.loads(out.getvalue()), err.getvalue()


def test_relative_write_identical_decoy_denied(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "strict")
    layout = make_layout(tmp_path, monkeypatch)
    layout.decoy(VIOLATING)
    out, _err = _invoke(layout.project, TARGET, VIOLATING)
    assert out.get("decision") == "deny"
    assert FORBIDDEN in out["reason"] or "router_001" in out["reason"]


def test_relative_write_decoy_with_forbidden_line_denied(tmp_path, monkeypatch):
    layout = make_layout(tmp_path, monkeypatch)
    layout.decoy(f"{FORBIDDEN} = True\n")
    out, _err = _invoke(layout.project, TARGET, VIOLATING)
    assert out.get("decision") == "deny"

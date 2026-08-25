"""Hermes plugin wiring tests: hooks bind to the gate and translate directives."""

from mneme.integrations.hermes import plugin
from mneme.integrations.hermes.adapter import GateResult, MnemeHermes


class _FakeCtx:
    def __init__(self):
        self.hooks = {}

    def register_hook(self, name, callback):
        self.hooks.setdefault(name, []).append(callback)


def _denied_result():
    return GateResult(
        action="deny", tool_name="write_file", file_path="x.py", reason="violation report"
    )


def test_register_binds_both_hooks(tmp_path):
    ctx = _FakeCtx()
    gate = MnemeHermes(project_dir=str(tmp_path))
    plugin.register(ctx, gate=gate)
    assert set(ctx.hooks) == {"pre_tool_call", "pre_llm_call"}
    assert len(ctx.hooks["pre_tool_call"]) == 1
    assert len(ctx.hooks["pre_llm_call"]) == 1


def test_pre_tool_hook_returns_block_for_denied_mutation(tmp_path):
    ctx = _FakeCtx()
    gate = MnemeHermes(project_dir=str(tmp_path))
    plugin.register(ctx, gate=gate)

    calls = {}

    def fake_evaluate(tool_name, args, cwd=""):
        calls["tool"] = tool_name
        return _denied_result()

    gate.evaluate_tool_call = fake_evaluate
    directive = ctx.hooks["pre_tool_call"][0](
        tool_name="write_file", args={"path": "x.py", "content": "y"}
    )
    assert calls["tool"] == "write_file"
    assert directive == {"action": "block", "message": "violation report"}


def test_pre_tool_hook_fails_open_on_gate_crash():
    gate = MnemeHermes(project_dir=".")

    def boom(*a, **kw):
        raise RuntimeError("exploded")

    gate.evaluate_tool_call = boom
    directive = plugin.on_pre_tool_call(gate, tool_name="write_file", args={})
    assert directive is None


def test_warn_and_fail_open_never_emit_directives(caplog):
    warn = GateResult(action="warn", tool_name="write_file", file_path="", reason="flagged")
    unevaluated = GateResult(
        action="fail_open", tool_name="write_file", file_path="", reason="not checked"
    )
    assert plugin.directive_for(warn) is None
    with caplog.at_level("WARNING", logger="mneme.integrations.hermes.plugin"):
        assert plugin._log_unevaluated(warn) is None
        assert plugin._log_unevaluated(unevaluated) is None
    assert "warn mode" in caplog.text
    assert "NOT" in caplog.text


def test_directive_for_requires_block_message_semantics():
    from mneme.integrations.hermes.adapter import directive_for

    result = GateResult(action="deny", tool_name="terminal", file_path="", reason="")
    payload = directive_for(result)
    # Hermes ignores a block without a message; adapter must always supply one.
    assert payload["action"] == "block"
    assert payload["message"]

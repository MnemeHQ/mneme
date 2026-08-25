"""LangChain integration — governed agents on LangGraph via Mneme.

Binds LangChain agent middleware (running on LangGraph) to the existing
Mneme surfaces:

    wrap_model_call
        -> MemoryStore + DecisionRetriever + format_decisions
        -> decision context injected into the model request

    wrap_tool_call (write_file | edit_file)
        -> canonical Write/Edit translation
        -> introduced-content materialization + `mneme check`
           (the same enforcement path as the Claude Code hook and the
           Claude Agent SDK adapter)
        -> allow / deny / warn / visibly UNEVALUATED

No retrieval, applicability, conflict, or enforcement semantics are
implemented here. The gate is delegated to ``mneme.integrations.agent_sdk``
(which imports the frozen pieces from ``mneme.integrations.claude_code.hook``);
this package only translates between LangChain middleware shapes and that
existing behavior. Raw ``StateGraph`` graphs are out of scope: arbitrary
graphs wire their own execution nodes, and Mneme claims no opinion over
nodes it cannot intercept.

Policy (identical to the documented Agent SDK adapter policy):

- trusted PASS            -> tool handler executes normally
- trusted WARN/FAIL,
  strict mode             -> handler is NOT called; rejection feedback is
                             returned to the model as the tool result
- trusted WARN/FAIL,
  warn mode               -> handler executes; visible warning appended to
                             the tool result
- unparseable verdict,
  operational failure,
  incomplete evaluation   -> fail open (handler executes) but visibly:
                             the tool result carries a UNEVALUATED marker
                             so an unchecked mutation is never silently
                             reported as governed.
- unlisted/read-only tool -> no opinion, zero checker invocations

Usage::

    from langchain.agents import create_agent
    from mneme.integrations.langchain import MnemeLangChain

    mneme = MnemeLangChain(project_dir=".")
    agent = create_agent(
        model=model,
        tools=[write_file, edit_file],
        middleware=mneme.build_middleware(),
    )

Requires ``langchain``/``langgraph`` only inside ``build_middleware()``;
the core callbacks are plain Python and can be tested without them.
"""

from __future__ import annotations

from mneme.integrations.agent_sdk import (
    ACTION_ALLOW,
    ACTION_DENY,
    ACTION_FAIL_OPEN,
    ACTION_SKIP,
    ACTION_WARN,
    ContextInjection,
    GateResult,
    MnemeAgentSdk,
)

# LangChain/Deep Agents filesystem surface -> Mneme canonical tool names.
# Deliberately closed: any other tool gets no opinion and zero checker
# calls. Extending this table is the ONLY way a new tool becomes governed.
LANGCHAIN_FILE_TOOLS = {
    "write_file": "Write",
    "edit_file": "Edit",
}


class MnemeLangChain:
    """Thin adapter binding LangChain agent middleware to Mneme governance.

    Args:
        project_dir: Directory used to discover ``.mneme/project_memory.json``
            and resolve relative tool paths. Defaults to the current working
            directory.
        memory: Explicit memory path override (wins over discovery).
        mode: Explicit enforcement mode ("strict" or "warn"). Falls back to
            the same environment resolution as the Claude Code hook
            (``MNEME_HOOK_MODE``, then "strict").
        check_runner: Test seam. Defaults to ``subprocess.run``.
    """

    def __init__(
        self,
        project_dir: str = ".",
        memory=None,
        mode: str | None = None,
        check_runner=None,
    ) -> None:
        self.project_dir = str(project_dir)
        self._sdk = MnemeAgentSdk(
            project_dir=self.project_dir,
            memory=memory,
            mode=mode,
            check_runner=check_runner,
        )

    @property
    def trace(self):
        """Audit trail: context injections and enforcement events."""
        return self._sdk.trace

    # ── Context path ────────────────────────────────────────────────────────

    def context_for_task(self, query: str) -> ContextInjection:
        """Retrieve relevant decisions via the existing retrieval path."""
        return self._sdk.context_for_task(query)

    # ── Enforcement path ────────────────────────────────────────────────────

    def evaluate_tool_call(
        self,
        tool_name: str,
        tool_input,
        cwd: str = "",
    ) -> GateResult:
        """Evaluate one proposed tool call through the existing Mneme path.

        Only tools listed in ``LANGCHAIN_FILE_TOOLS`` are translated and
        governed. Everything else is skipped with zero checker invocations;
        the adapter holds no opinion over surfaces it cannot translate.
        """
        canonical = LANGCHAIN_FILE_TOOLS.get(tool_name)
        if canonical is None:
            self._record_unmapped_skip(tool_name)
            return GateResult(
                action=ACTION_SKIP,
                tool_name=tool_name,
                file_path="",
                reason="not a governed langchain file tool",
            )
        return self._sdk.evaluate_mutation(
            tool_name=canonical,
            tool_input=tool_input if isinstance(tool_input, dict) else {},
            cwd=cwd or self.project_dir,
        )

    # ── Middleware wiring ───────────────────────────────────────────────────

    def build_middleware(self):
        """Build the LangChain middleware list binding this integration.

        Returns ``[decision-context middleware, tool-gate middleware]``.
        Requires ``langchain`` to be installed; the core callbacks above
        deliberately do not, so deterministic tests run without it.
        """
        from mneme.integrations.langchain.middleware import build_middleware

        return build_middleware(self)

    # ── Internals ───────────────────────────────────────────────────────────

    def _record_unmapped_skip(self, tool_name: str) -> None:
        self._sdk.trace.append(
            {
                "kind": "enforcement",
                "via": "langchain",
                "tool": tool_name,
                "file_path": "",
                "action": ACTION_SKIP,
                "verdict": None,
                "evaluation_complete": True,
                "reason": "not a governed langchain file tool",
            }
        )


__all__ = [
    "MnemeLangChain",
    "LANGCHAIN_FILE_TOOLS",
    "ContextInjection",
    "GateResult",
    "ACTION_ALLOW",
    "ACTION_DENY",
    "ACTION_WARN",
    "ACTION_FAIL_OPEN",
    "ACTION_SKIP",
]

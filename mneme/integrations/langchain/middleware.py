"""LangChain middleware bindings for the Mneme gate.

This module is imported lazily from ``MnemeLangChain.build_middleware()``
so that the core adapter (and its deterministic tests) never require
``langchain`` to be installed. It contains translation only: every
governance decision comes from ``MnemeLangChain.evaluate_tool_call`` and
``MnemeLangChain.context_for_task``, which reuse the frozen retrieval and
enforcement paths.
"""

from __future__ import annotations

import json
from typing import Any, List

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from mneme.integrations.langchain.adapter import (
    ACTION_DENY,
    ACTION_FAIL_OPEN,
    ACTION_WARN,
)

DENY_TAG = "[mneme] DENIED"
WARN_TAG = "[mneme] WARN"
UNEVALUATED_TAG = "[mneme] UNEVALUATED"


def build_middleware(gate):
    """Return ``[decision-context middleware, tool-gate middleware]``.

    ``gate`` is a ``MnemeLangChain`` instance; passing it as an argument
    keeps this module free of governance logic and importable without
    LangChain-specific configuration.
    """

    # ── Decision-context injection (retrieval path) ─────────────────────────

    class DecisionContextMiddleware(AgentMiddleware):
        """Inject retrieved decisions into the model request.

        The query is the most recent human message. Injection appends to
        the system message; graph state semantics are untouched.
        """

        def wrap_model_call(self, request, handler):
            return handler(self._with_decisions(request))

        async def awrap_model_call(self, request, handler):
            return await handler(self._with_decisions(request))

        def _with_decisions(self, request):
            query = _latest_human_text(request.messages)
            if not query:
                return request
            injection = gate.context_for_task(query)
            if not injection.text:
                return request
            base = ""
            if request.system_message is not None and request.system_message.content:
                base = request.system_message.content + "\n"
            merged = SystemMessage(content=base + injection.text)
            return type(request)(
                model=request.model,
                messages=request.messages,
                system_message=merged,
                tools=request.tools,
                tool_choice=request.tool_choice,
                response_format=request.response_format,
                state=request.state,
                runtime=request.runtime,
            )

    # ── Tool gate (enforcement path) ────────────────────────────────────────

    class ToolGateMiddleware(AgentMiddleware):
        """Intercept proposed tool calls before execution."""

        def wrap_tool_call(self, request, handler):
            result = self._evaluate(request)
            if result.action == ACTION_DENY:
                return self._rejection(result, request)
            executed = handler(request)
            return self._annotate_verdict(executed, result)

        async def awrap_tool_call(self, request, handler):
            result = self._evaluate(request)
            if result.action == ACTION_DENY:
                return self._rejection(result, request)
            executed = await handler(request)
            return self._annotate_verdict(executed, result)

        def _evaluate(self, request):
            tool_call = request.tool_call
            args = tool_call.get("args")
            return gate.evaluate_tool_call(
                tool_name=str(tool_call.get("name", "")),
                tool_input=args if isinstance(args, dict) else {},
                cwd=gate.project_dir,
            )

        def _rejection(self, result, request):
            reason = result.reason or "architectural decision violated"
            return ToolMessage(
                content=f"{DENY_TAG} - {reason}",
                tool_call_id=str(request.tool_call.get("id", "")),
            )

        def _annotate_verdict(self, message, result):
            if result.action == ACTION_WARN:
                return _append_note(
                    message,
                    f"{WARN_TAG} - architectural decision flagged "
                    f"(warn mode; not blocked):\n{result.reason}",
                )
            if result.action == ACTION_FAIL_OPEN:
                return _append_note(
                    message,
                    f"{UNEVALUATED_TAG} - failing open, this mutation was "
                    f"NOT checked:\n{result.reason}",
                )
            return message

    return [DecisionContextMiddleware(), ToolGateMiddleware()]


# ── Helpers ─────────────────────────────────────────────────────────────────


def _latest_human_text(messages: List[Any]) -> str:
    for message in reversed(list(messages or [])):
        if isinstance(message, HumanMessage):
            return _message_text(message)
    return ""


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        return " ".join(p for p in parts if p)
    return ""


def _append_note(message: Any, note: str) -> Any:
    """Make a warn/unevaluated outcome visible in the tool result itself."""
    if isinstance(message, ToolMessage):
        content = message.content
        text = content if isinstance(content, str) else json.dumps(content)
        message.content = f"{text}\n{note}" if text else note
    return message

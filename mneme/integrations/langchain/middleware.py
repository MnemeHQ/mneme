"""LangChain middleware bindings for the Mneme gate.

This module is imported lazily from ``MnemeLangChain.build_middleware()``
so that the core adapter (and its deterministic tests) never require
``langchain`` to be installed. It contains translation only: every
governance decision comes from ``MnemeLangChain.evaluate_tool_call`` and
``MnemeLangChain.context_for_task``, which reuse the frozen retrieval and
enforcement paths.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, List

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command

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

        The query is the most recent human message. Injection replaces only
        the system message via ``request.override(...)``; every other field
        of the request -- including ``model_settings`` -- is preserved.
        Graph state semantics are untouched.
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
            merged = SystemMessage(
                content=_merge_system_content(
                    getattr(request.system_message, "content", None),
                    injection.text,
                )
            )
            return request.override(system_message=merged)

    # ── Tool gate (enforcement path) ────────────────────────────────────────

    class ToolGateMiddleware(AgentMiddleware):
        """Intercept proposed tool calls before execution."""

        def wrap_tool_call(self, request, handler):
            result = self._evaluate(request)
            if result.action == ACTION_DENY:
                return self._rejection(result, request)
            executed = handler(request)
            return self._annotate_verdict(executed, result, request)

        async def awrap_tool_call(self, request, handler):
            result = self._evaluate(request)
            if result.action == ACTION_DENY:
                return self._rejection(result, request)
            executed = await handler(request)
            return self._annotate_verdict(executed, result, request)

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

        def _annotate_verdict(self, executed, result, request):
            if result.action == ACTION_WARN:
                return _append_note(
                    executed,
                    f"{WARN_TAG} - architectural decision flagged "
                    f"(warn mode; not blocked):\n{result.reason}",
                    gate,
                    result,
                    request,
                )
            if result.action == ACTION_FAIL_OPEN:
                return _append_note(
                    executed,
                    f"{UNEVALUATED_TAG} - failing open, this mutation was "
                    f"NOT checked:\n{result.reason}",
                    gate,
                    result,
                    request,
                )
            return executed

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


def _merge_system_content(existing: Any, note: str) -> Any:
    """Append decision text to a system message's content.

    LangChain system messages may carry plain string content or structured
    content blocks. Both shapes are preserved; the decision text is added
    without disturbing existing content.
    """
    if existing is None or (isinstance(existing, str) and not existing.strip()):
        return note
    if isinstance(existing, str):
        return f"{existing}\n{note}"
    if isinstance(existing, list):
        return list(existing) + [{"type": "text", "text": note}]
    return f"{existing}\n{note}"


def _annotate_command(command: Command, note: str, gate, result, request) -> Command:
    """Carry a WARN/UNEVALUATED marker through a ``Command`` tool result.

    The handler contract allows returning ``ToolMessage | Command``. A
    ``Command``'s update semantics must survive annotation untouched, so
    the note is appended to the tool-result message inside ``update`` and
    the command is rebuilt via ``dataclasses.replace`` (goto/resume/graph
    are preserved as-is).

    If the update shape carries no recognizable ``ToolMessage``, the command
    is returned unchanged but the visibility gap is recorded on the audit
    trace -- never silent.
    """
    update = command.update
    if not isinstance(update, dict):
        _record_annotation_gap(gate, result, request, "command-update-not-dict")
        return command

    messages = update.get("messages")
    if isinstance(messages, ToolMessage):
        annotated = _tool_message_with_note(messages, note)
        new_update = dict(update)
        new_update["messages"] = annotated
        return dataclasses.replace(command, update=new_update)

    if isinstance(messages, list) and any(
        isinstance(m, ToolMessage) for m in messages
    ):
        new_messages = list(messages)
        for index in range(len(new_messages) - 1, -1, -1):
            if isinstance(new_messages[index], ToolMessage):
                new_messages[index] = _tool_message_with_note(
                    new_messages[index], note
                )
                break
        new_update = dict(update)
        new_update["messages"] = new_messages
        return dataclasses.replace(command, update=new_update)

    _record_annotation_gap(gate, result, request, "no-tool-message-in-command")
    return command


def _tool_message_with_note(message: ToolMessage, note: str) -> ToolMessage:
    copy = message.model_copy()
    content = copy.content
    text = content if isinstance(content, str) else json.dumps(content)
    copy.content = f"{text}\n{note}" if text else note
    return copy


def _record_annotation_gap(gate, result, request, detail: str) -> None:
    """Record an un-annotatable result on the audit trace; never silent."""
    gate.trace.append(
        {
            "kind": "enforcement",
            "via": "langchain",
            "annotation": "skipped",
            "detail": detail,
            "action": result.action,
            "tool": str(request.tool_call.get("name", "")),
            "file_path": "",
            "verdict": result.verdict,
            "evaluation_complete": result.evaluation_complete,
            "reason": result.reason,
        }
    )


def _append_note(message: Any, note: str, gate=None, result=None, request=None) -> Any:
    """Make a warn/unevaluated outcome visible in the tool result itself."""
    if isinstance(message, ToolMessage):
        return _tool_message_with_note(message, note)
    if isinstance(message, Command):
        return _annotate_command(message, note, gate, result, request)
    return message

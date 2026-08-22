"""Claude Agent SDK integration — governed agent sessions via Mneme.

Maps Claude Agent SDK lifecycle events onto existing Mneme surfaces:

    UserPromptSubmit
        -> MemoryStore + DecisionRetriever + format_decisions
        -> additionalContext

    PreToolUse (Write | Edit | MultiEdit)
        -> ToolEvent translation
        -> introduced-content materialization + `mneme check`
           (the same enforcement path as the Claude Code hook)
        -> allow / deny + Mneme's reason

No retrieval, applicability, conflict, or enforcement semantics are
implemented here. The pure pieces are imported from
``mneme.integrations.claude_code.hook``; this module only translates
between SDK event shapes and that existing behavior.

Policy (mirrors the documented Claude Code hook policy):

- trusted PASS            -> no opinion (normal permission flow continues)
- trusted WARN/FAIL,
  strict mode             -> deny, reason = Mneme's violation report
- trusted WARN/FAIL,
  warn mode               -> no decision, warning injected as context
- unparseable verdict,
  operational failure,
  incomplete evaluation   -> fail open (no decision) but visibly: the
                             reason is injected as additionalContext so
                             an unevaluated mutation is never silently
                             reported as governed.

Usage::

    from mneme.integrations.agent_sdk import MnemeAgentSdk

    mneme = MnemeAgentSdk(project_dir=".")
    options = ClaudeAgentOptions(hooks=mneme.hooks(), ...)
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from mneme.context_builder import DEFAULT_MAX_DECISIONS, format_decisions
from mneme.decision_retriever import DecisionRetriever
from mneme.integrations.claude_code.hook import (
    ToolEvent,
    _CHECK_JSON_SCHEMA,
    _CHECK_TIMEOUT_SECONDS,
    _child_env,
    find_memory,
    format_applicability_reason,
    format_reason,
    introduced_content,
    MaterializeError,
    parse_verdict,
    resolve_mode,
    should_check,
)
from mneme.memory_store import MemoryStore

# Actions returned by the mutation gate.
ACTION_ALLOW = "allow"
ACTION_DENY = "deny"
ACTION_WARN = "warn"
ACTION_FAIL_OPEN = "fail_open"
ACTION_SKIP = "skip"


@dataclass(frozen=True)
class ContextInjection:
    """Decisions retrieved for a task, before any material work."""

    query: str
    text: str
    decision_ids: List[str]
    memory_path: Optional[str]


@dataclass(frozen=True)
class GateResult:
    """Structured outcome of one proposed mutation."""

    action: str
    tool_name: str
    file_path: str
    reason: str
    verdict: Optional[str] = None
    evaluation_complete: bool = True
    payload: Optional[Dict[str, Any]] = None


CheckRunner = Callable[..., subprocess.CompletedProcess]


class MnemeAgentSdk:
    """Thin adapter binding Claude Agent SDK events to Mneme governance.

    Args:
        project_dir: Directory used to discover ``.mneme/project_memory.json``.
            Defaults to the current working directory.
        memory: Explicit memory path override (wins over discovery).
        mode: Explicit enforcement mode ("strict" or "warn"). Falls back to
            the same environment resolution as the Claude Code hook
            (``MNEME_HOOK_MODE``, then "strict").
        check_runner: Test seam. Defaults to ``subprocess.run``.
    """

    def __init__(
        self,
        project_dir: str | Path = ".",
        memory: str | Path | None = None,
        mode: Optional[str] = None,
        check_runner: Optional[CheckRunner] = None,
    ) -> None:
        self.project_dir = str(project_dir)
        self._memory_override = str(memory) if memory else None
        self._mode_override = mode
        self._check_runner = check_runner or subprocess.run
        self.trace: List[Dict[str, Any]] = []

    # ── Context path ────────────────────────────────────────────────────────

    def context_for_task(self, query: str) -> ContextInjection:
        """Retrieve relevant decisions via the existing retrieval path."""
        memory = self._memory()
        if memory is None:
            self._record(
                kind="context_injection",
                query=query,
                outcome="NO_MEMORY",
                decision_ids=[],
            )
            return ContextInjection(query=query, text="", decision_ids=[], memory_path=None)

        store = MemoryStore(memory)
        store.load()
        scored = DecisionRetriever(store.decisions()).retrieve(query)
        text = format_decisions(scored, max_items=DEFAULT_MAX_DECISIONS)
        ids: List[str] = []
        seen: set[str] = set()
        for s in scored:
            if s.score <= 0.0 or s.decision.id in seen:
                continue
            seen.add(s.decision.id)
            ids.append(s.decision.id)
            if len(ids) >= DEFAULT_MAX_DECISIONS:
                break

        self._record(
            kind="context_injection",
            query=query,
            outcome="INJECTED" if ids else "EMPTY",
            decision_ids=ids,
            memory_path=str(memory),
        )
        return ContextInjection(query=query, text=text, decision_ids=ids, memory_path=str(memory))

    def user_prompt_submit(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """SDK UserPromptSubmit callback: inject decisions as additionalContext."""
        injection = self.context_for_task(input_data.get("prompt", ""))
        if not injection.text:
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": injection.text,
            }
        }

    # ── Enforcement path ────────────────────────────────────────────────────

    def evaluate_mutation(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        cwd: str = "",
    ) -> GateResult:
        """Evaluate one proposed mutation through the existing Mneme path."""
        file_path = tool_input.get("file_path", "") if isinstance(tool_input, dict) else ""

        if not should_check(tool_name):
            return self._gate(ACTION_SKIP, tool_name, file_path, "not a mutating tool")

        memory = self._memory()
        if memory is None:
            # Same policy as the Claude Code hook: outside any governed
            # project, the gate has no opinion.
            return self._gate(ACTION_SKIP, tool_name, file_path, "no project memory")

        event = ToolEvent(tool_name=tool_name, file_path=file_path, cwd=cwd, tool_input=tool_input)
        try:
            checked_content = introduced_content(event)
        except MaterializeError as e:
            return self._gate(
                ACTION_FAIL_OPEN,
                tool_name,
                file_path,
                f"mneme-agent-sdk: cannot materialize content, failing open: {e}",
            )

        if not checked_content.strip():
            return self._gate(
                ACTION_SKIP, tool_name, file_path, "no non-blank introduced lines"
            )

        mode = self._mode()
        proc = self._run_check(event, checked_content, memory, mode)

        if proc is None:
            return self._gate(
                ACTION_FAIL_OPEN,
                tool_name,
                file_path,
                "mneme-agent-sdk: could not run mneme check. Failing open.",
            )

        payload = parse_verdict(proc.stdout)
        if payload is None:
            return self._gate(
                ACTION_FAIL_OPEN,
                tool_name,
                file_path,
                "mneme-agent-sdk: no parseable verdict from mneme check "
                f"(exit {proc.returncode}). Failing open.",
                payload_stderr=proc.stderr,
            )

        verdict = payload["verdict"]
        if payload.get("evaluation_complete") is False:
            return self._gate(
                ACTION_FAIL_OPEN,
                tool_name,
                file_path,
                format_applicability_reason(payload),
                verdict=verdict,
                evaluation_complete=False,
                payload=payload,
            )

        if verdict == "PASS":
            return self._gate(
                ACTION_ALLOW, tool_name, file_path, "", verdict=verdict, payload=payload
            )

        reason = format_reason(payload)
        if mode == "warn":
            return self._gate(
                ACTION_WARN, tool_name, file_path, reason, verdict=verdict, payload=payload
            )
        return self._gate(
            ACTION_DENY, tool_name, file_path, reason, verdict=verdict, payload=payload
        )

    def pre_tool_use(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """SDK PreToolUse callback: translate the gate result to SDK output.

        Returns {} (no opinion) unless Mneme has something to say. A deny
        carries Mneme's full violation report as permissionDecisionReason;
        fail-open outcomes carry their reason as additionalContext so the
        unevaluated state is visible to the agent instead of silent.
        """
        result = self.evaluate_mutation(
            tool_name=input_data.get("tool_name", ""),
            tool_input=input_data.get("tool_input", {}) or {},
            cwd=input_data.get("cwd", ""),
        )

        if result.action == ACTION_DENY:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": result.reason,
                }
            }
        if result.action == ACTION_WARN:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecisionReason": result.reason,
                    "additionalContext": (
                        "[mneme] WARN - architectural decision flagged "
                        "(warn mode; not blocked):\n" + result.reason
                    ),
                }
            }
        if result.action == ACTION_FAIL_OPEN:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": (
                        "[mneme] UNEVALUATED - failing open, this mutation "
                        "was NOT checked:\n" + result.reason
                    ),
                }
            }
        return {}

    # ── SDK wiring ──────────────────────────────────────────────────────────

    def hooks(self) -> Dict[Any, List[Any]]:
        """Build the Claude Agent SDK ``hooks`` dict binding this integration.

        Requires ``claude_agent_sdk`` to be installed; the core callbacks
        above deliberately do not, so deterministic tests run without it.
        """
        from claude_agent_sdk import HookMatcher

        async def _pre_tool_use(input_data, _tool_use_id=None, _context=None):
            return self.pre_tool_use(input_data)

        async def _user_prompt_submit(input_data, _tool_use_id=None, _context=None):
            return self.user_prompt_submit(input_data)

        return {
            "PreToolUse": [
                HookMatcher(matcher="Write|Edit|MultiEdit", hooks=[_pre_tool_use])
            ],
            "UserPromptSubmit": [HookMatcher(hooks=[_user_prompt_submit])],
        }

    # ── Internals ───────────────────────────────────────────────────────────

    def _memory(self):
        if self._memory_override:
            p = Path(self._memory_override)
            return p if p.is_file() else None
        return find_memory(Path(self.project_dir))

    def _mode(self) -> str:
        if self._mode_override in ("strict", "warn"):
            return self._mode_override
        return resolve_mode()

    def _run_check(self, event: ToolEvent, content: str, memory: Path, mode: str):
        """Run `mneme check` exactly as the Claude Code hook does."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(content)
            input_path = tf.name

        rel = event.file_path or "(unknown)"
        target_path = event.file_path
        if target_path and not Path(target_path).is_absolute() and event.cwd:
            target_path = str(Path(event.cwd) / target_path)

        command = [
            sys.executable, "-m", "mneme", "check",
            "--memory", str(memory),
            "--input", input_path,
            "--query", f"edit to {rel}",
            "--mode", mode,
            "--json",
        ]
        if target_path:
            command.extend(["--target-path", target_path])

        try:
            return self._check_runner(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=_CHECK_TIMEOUT_SECONDS,
                env=_child_env(),
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        finally:
            try:
                os.unlink(input_path)
            except OSError:
                pass

    def _gate(
        self,
        action: str,
        tool_name: str,
        file_path: str,
        reason: str,
        verdict: Optional[str] = None,
        evaluation_complete: bool = True,
        payload: Optional[Dict[str, Any]] = None,
        **extra: Any,
    ) -> GateResult:
        self._record(
            kind="enforcement",
            tool=tool_name,
            file_path=file_path,
            action=action,
            verdict=verdict,
            evaluation_complete=evaluation_complete,
            reason=reason,
            **extra,
        )
        return GateResult(
            action=action,
            tool_name=tool_name,
            file_path=file_path,
            reason=reason,
            verdict=verdict,
            evaluation_complete=evaluation_complete,
            payload=payload,
        )

    def _record(self, **event: Any) -> None:
        self.trace.append(event)


__all__ = [
    "MnemeAgentSdk",
    "ContextInjection",
    "GateResult",
    "ACTION_ALLOW",
    "ACTION_DENY",
    "ACTION_WARN",
    "ACTION_FAIL_OPEN",
    "ACTION_SKIP",
    "_CHECK_JSON_SCHEMA",
]

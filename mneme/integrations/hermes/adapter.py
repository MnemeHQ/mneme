"""Mneme integration for the Hermes Agent (P1.5 proof of concept).

Two Hermes plugin hooks map onto existing Mneme surfaces:

    pre_llm_call   -> MemoryStore + DecisionRetriever + format_decisions
                      -> {"context": ...} injected into the current turn
                      (the same retrieval path as the Agent SDK adapter)

    pre_tool_call  -> Hermes args translation (write_file | patch | terminal)
                      -> introduced-content materialization + `mneme check`
                      (the same enforcement path as the Claude Code hook)
                      -> {"action": "block"} + Mneme's reason, or no opinion

No retrieval, applicability, conflict, or enforcement semantics are
implemented here. The pure pieces are imported from
``mneme.integrations.claude_code.hook``, ``mneme.decision_retriever``,
and ``mneme.integrations.codex_cli.patch_parser``; this module only
translates between Hermes' hook payloads and that existing behavior.

Known boundary (characterized by the H0/H3 probes, see
docs/integrations/hermes.md):

- ``terminal`` commands are checked only when they match the ADR-021
  class-A grammar (single quoted-delimiter heredoc write). Every other
  shell form passes unevaluated: Hermes has no blocking Stop-equivalent,
  so there is no session-delta backstop behind this gate.
- ``execute_code`` and ``process`` are deliberately unevaluated bypass
  surfaces. They are never claimed as governed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from mneme.context_builder import DEFAULT_MAX_DECISIONS, format_decisions
from mneme.decision_retriever import DecisionRetriever
from mneme.integrations.claude_code.hook import (
    ToolEvent,
    _CHECK_TIMEOUT_SECONDS,
    _child_env,
    find_memory,
    format_applicability_reason,
    format_reason,
    introduced_between,
    introduced_content,
    MaterializeError,
    parse_verdict,
    resolve_mode,
)
from mneme.integrations.claude_code.shell_preflight import (
    Classification,
    classify_command,
    reconstruct_heredoc_write,
)
from mneme.integrations.codex_cli.patch_parser import (
    CodexPatchParseError,
    parse_patch_operations,
    patch_operation_specs,
)
from mneme.memory_store import MemoryStore

# Actions returned by the mutation gate (same vocabulary as Agent SDK).
ACTION_ALLOW = "allow"
ACTION_DENY = "deny"
ACTION_WARN = "warn"
ACTION_FAIL_OPEN = "fail_open"
ACTION_SKIP = "skip"

HERMES_MUTATING_TOOLS = frozenset({"write_file", "patch"})
HERMES_SHELL_TOOLS = frozenset({"terminal"})

# Deliberately unevaluated mutation surfaces. Characterized, not governed:
# see docs/integrations/hermes.md (H3 coverage matrix).
HERMES_UNEVALUATED_TOOLS = frozenset({"execute_code", "process"})


@dataclass(frozen=True)
class ContextInjection:
    """Decisions retrieved for one turn, before any material work."""

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


class MnemeHermes:
    """Thin adapter binding Hermes plugin hooks to Mneme governance.

    Args:
        project_dir: Directory used to discover ``.mneme/project_memory.json``.
            Defaults to the process working directory (Hermes loads project
            plugins relative to CWD and its ``pre_tool_call`` payload carries
            no cwd field).
        memory: Explicit memory path override (wins over discovery).
        mode: Explicit enforcement mode ("strict" or "warn"). Falls back to
            the shared environment resolution (``MNEME_HOOK_MODE``, then
            "strict").
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

    # ── Context path (pre_llm_call) ──────────────────────────────────────────

    def context_for_turn(self, query: str) -> ContextInjection:
        """Retrieve relevant decisions via the existing retrieval path."""
        memory = self._memory()
        if memory is None:
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

        return ContextInjection(
            query=query, text=text, decision_ids=ids, memory_path=str(memory)
        )

    # ── Enforcement path (pre_tool_call) ─────────────────────────────────────

    def evaluate_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        cwd: str = "",
    ) -> GateResult:
        """Evaluate one proposed Hermes tool call through the existing path."""
        args = args if isinstance(args, dict) else {}

        if tool_name == "write_file":
            return self._gate_event(self._write_file_event(args, cwd))

        if tool_name == "patch":
            patch_mode = args.get("mode", "replace")
            if patch_mode == "replace":
                return self._gate_event(self._patch_replace_event(args, cwd))
            if patch_mode == "patch":
                return self._gate_v4a_patch(args.get("patch", ""), cwd)
            return self._gate(
                ACTION_FAIL_OPEN,
                tool_name,
                "",
                f"mneme-hermes: unknown patch mode {patch_mode!r}, failing open",
            )

        if tool_name == "terminal":
            return self._gate_terminal(args.get("command", ""), args.get("workdir", ""), cwd)

        if tool_name in HERMES_UNEVALUATED_TOOLS:
            return self._gate(
                ACTION_SKIP,
                tool_name,
                "",
                "unevaluated mutation surface (see Hermes POC coverage matrix)",
            )

        return self._gate(ACTION_SKIP, tool_name, "", "not a checked mutating tool")

    # ── Directive translation ────────────────────────────────────────────────

    def pre_tool_call(self, tool_name: str = "", args: Optional[Dict] = None, **_: Any):
        """Hermes ``pre_tool_call`` callback: returns a block directive or None.

        Policy mirrors the documented integrations: only a trusted strict-mode
        WARN/FAIL verdict blocks; warn mode and every fail-open outcome pass
        with the reason logged by the caller (never silently).
        """
        result = self.evaluate_tool_call(tool_name, args or {}, cwd=self.project_dir)
        return directive_for(result)

    def pre_llm_call(self, user_message: str = "", **_: Any):
        """Hermes ``pre_llm_call`` callback: returns {"context": ...} or None."""
        injection = self.context_for_turn(user_message)
        if not injection.text:
            return None
        return {"context": injection.text}

    # ── Translation helpers (pure payload mapping) ───────────────────────────

    @staticmethod
    def _write_file_event(args: Dict[str, Any], cwd: str) -> ToolEvent:
        file_path = str(args.get("path", ""))
        return ToolEvent(
            tool_name="Write",
            file_path=file_path,
            cwd=cwd,
            tool_input={"file_path": file_path, "content": args.get("content", "")},
        )

    @staticmethod
    def _patch_replace_event(args: Dict[str, Any], cwd: str) -> ToolEvent:
        file_path = str(args.get("path", ""))
        tool_input: Dict[str, Any] = {
            "file_path": file_path,
            "old_string": args.get("old_string", ""),
            "new_string": args.get("new_string", ""),
        }
        if args.get("replace_all"):
            tool_input["replace_all"] = True
        return ToolEvent(
            tool_name="Edit",
            file_path=file_path,
            cwd=cwd,
            tool_input=tool_input,
        )

    # ── Shared gate internals ────────────────────────────────────────────────

    def _memory(self):
        if self._memory_override:
            p = Path(self._memory_override)
            return p if p.is_file() else None
        return find_memory(Path(self.project_dir))

    def _mode(self) -> str:
        if self._mode_override in ("strict", "warn"):
            return self._mode_override
        return resolve_mode()

    def _gate(
        self,
        action: str,
        tool_name: str,
        file_path: str,
        reason: str,
        verdict: Optional[str] = None,
        evaluation_complete: bool = True,
        payload: Optional[Dict[str, Any]] = None,
    ) -> GateResult:
        return GateResult(
            action=action,
            tool_name=tool_name,
            file_path=file_path,
            reason=reason,
            verdict=verdict,
            evaluation_complete=evaluation_complete,
            payload=payload,
        )

    def _gate_event(self, event: ToolEvent) -> GateResult:
        """Materialize + check one canonical Write/Edit event."""
        memory = self._memory()
        if memory is None:
            # Same policy as every other integration: outside any governed
            # project, the gate has no opinion.
            return self._gate(ACTION_SKIP, event.tool_name, event.file_path, "no project memory")

        try:
            checked_content = introduced_content(event)
        except MaterializeError as e:
            return self._gate(
                ACTION_FAIL_OPEN,
                event.tool_name,
                event.file_path,
                f"mneme-hermes: cannot materialize content, failing open: {e}",
            )

        return self._check_introduced(
            event.tool_name, event.file_path, checked_content, memory
        )

    def _check_introduced(
        self,
        tool_label: str,
        file_path: str,
        checked_content: str,
        memory: Path,
    ) -> GateResult:
        if not checked_content.strip():
            return self._gate(
                ACTION_SKIP, tool_label, file_path, "no non-blank introduced lines"
            )

        mode = self._mode()
        proc = self._run_check(file_path, checked_content, memory, mode)

        if proc is None:
            return self._gate(
                ACTION_FAIL_OPEN,
                tool_label,
                file_path,
                "mneme-hermes: could not run mneme check. Failing open.",
            )

        payload = parse_verdict(proc.stdout)
        if payload is None:
            return self._gate(
                ACTION_FAIL_OPEN,
                tool_label,
                file_path,
                "mneme-hermes: no parseable verdict from mneme check "
                f"(exit {proc.returncode}). Failing open.",
            )

        verdict = payload["verdict"]
        if payload.get("evaluation_complete") is False:
            return self._gate(
                ACTION_FAIL_OPEN,
                tool_label,
                file_path,
                format_applicability_reason(payload),
                verdict=verdict,
                evaluation_complete=False,
                payload=payload,
            )

        if verdict == "PASS":
            return self._gate(
                ACTION_ALLOW, tool_label, file_path, "", verdict=verdict, payload=payload
            )

        reason = format_reason(payload)
        if mode == "warn":
            return self._gate(
                ACTION_WARN, tool_label, file_path, reason, verdict=verdict, payload=payload
            )
        return self._gate(
            ACTION_DENY, tool_label, file_path, reason, verdict=verdict, payload=payload
        )

    def _run_check(self, file_path: str, content: str, memory: Path, mode: str):
        """Run `mneme check` exactly as the existing integrations do."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(content)
            input_path = tf.name

        rel = file_path or "(unknown)"
        target_path = file_path
        if target_path and not Path(target_path).is_absolute():
            target_path = str(Path(self.project_dir) / target_path)

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

    # ── V4A multi-file patches (patch tool, mode="patch") ────────────────────

    def _gate_v4a_patch(self, patch_text: str, cwd: str) -> GateResult:
        """Evaluate a V4A patch via the frozen Codex CLI transport parser."""
        memory = self._memory()
        if memory is None:
            return self._gate(ACTION_SKIP, "patch", "", "no project memory")

        base = Path(cwd or self.project_dir)

        def resolve(raw: str) -> Path:
            p = Path(raw)
            return p if p.is_absolute() else base / raw

        try:
            specs = patch_operation_specs(patch_text)
        except CodexPatchParseError as e:
            return self._gate(
                ACTION_FAIL_OPEN,
                "patch",
                "",
                f"mneme-hermes: unparseable V4A patch, failing open: {e}",
            )

        snapshots: Dict[str, Optional[str]] = {}
        for kind, raw_path in specs:
            if kind != "update":
                continue
            target = resolve(raw_path)
            try:
                snapshots[raw_path] = target.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                # Snapshot explicitly unavailable: the operation is reported
                # as unevaluated rather than guessed at.
                snapshots[raw_path] = None

        try:
            operations = parse_patch_operations(patch_text, snapshots)
        except CodexPatchParseError as e:
            return self._gate(
                ACTION_FAIL_OPEN,
                "patch",
                "",
                f"mneme-hermes: V4A patch could not be validated against "
                f"current files, failing open: {e}",
            )

        worst: Optional[GateResult] = None
        for op in operations:
            if op.kind == "delete":
                continue  # pure deletion introduces nothing new (ADR-018)
            target_abs = str(resolve(op.target_path))
            if op.introduced_content is None:
                # Snapshot explicitly unavailable: disclosed as unevaluated,
                # never guessed at.
                result = self._gate(
                    ACTION_FAIL_OPEN,
                    "patch",
                    target_abs,
                    "mneme-hermes: update snapshot unavailable; operation unevaluated",
                )
            else:
                result = self._check_introduced(
                    "patch", target_abs, op.introduced_content, memory
                )
            if result.action == ACTION_DENY:
                return result
            if result.action in (ACTION_WARN, ACTION_FAIL_OPEN):
                worst = result
        return worst or self._gate(ACTION_ALLOW, "patch", "", "", verdict="PASS")

    # ── Terminal preflight (ADR-021 class A only) ────────────────────────────

    def _gate_terminal(self, command: str, workdir: str, cwd: str) -> GateResult:
        rec = reconstruct_heredoc_write(command)
        if rec is None:
            cls = classify_command(command)
            value = cls.value if isinstance(cls, Classification) else str(cls)
            return self._gate(
                ACTION_SKIP,
                "terminal",
                "",
                f"classified {value}: no deterministic pre-execution check "
                "(no session-delta backstop exists in Hermes)",
            )

        memory = self._memory()
        if memory is None:
            return self._gate(ACTION_SKIP, "terminal", rec.target_path, "no project memory")

        base = workdir or cwd or self.project_dir
        target_abs = rec.target_path
        if not Path(target_abs).is_absolute():
            target_abs = str(Path(base) / target_abs)

        try:
            current = Path(target_abs).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            current = ""
        proposed = current + rec.proposed_content if rec.append else rec.proposed_content
        checked = introduced_between(current, proposed)
        return self._check_introduced("terminal", target_abs, checked, memory)


def directive_for(result: GateResult) -> Optional[Dict[str, str]]:
    """Translate a gate outcome into a Hermes ``pre_tool_call`` directive.

    Only DENY produces a directive — an explicit ``{"action": "approve"}``
    would escalate to human approval and weaken Hermes' own permission flow,
    so PASS/skip/warn/fail-open stay silent (None) exactly like Antigravity's
    deny-only policy. Hermes requires a non-empty message on block.
    """
    if result.action == ACTION_DENY:
        message = result.reason or f"blocked by mneme ({result.tool_name})"
        return {"action": "block", "message": message}
    return None


__all__ = [
    "MnemeHermes",
    "ContextInjection",
    "GateResult",
    "directive_for",
    "ACTION_ALLOW",
    "ACTION_DENY",
    "ACTION_WARN",
    "ACTION_FAIL_OPEN",
    "ACTION_SKIP",
    "HERMES_MUTATING_TOOLS",
    "HERMES_SHELL_TOOLS",
    "HERMES_UNEVALUATED_TOOLS",
]

"""Reference custom tool that opts in to Mneme evaluation (option 1B).

Test code only, not a Mneme API. It is the reference shape from
``docs/plans/2026-10-20-enforcement-coverage-custom-tools-and-project-boundary.md``
section 4 (option 1B) and section 5 (option 2C): an orchestrator-owned file
tool that

- canonicalizes its target once (``resolve()``: symlinks followed, ``..``
  removed) and, when confined, refuses any target outside its root before
  calling the gate (orchestrator policy, not a Mneme decision);
- submits that same canonical path and the exact bytes it will write to the
  existing gate (``MnemeLangChain.evaluate_tool_call`` or
  ``MnemeAgentSdk.evaluate_mutation``) in a canonical ``Write``/``Edit``
  shape;
- reads only ``GateResult.action`` and ``GateResult.reason``. Verdict trust
  (``assess_verdict``, #484 coherence) stays inside the adapter; nothing here
  parses ``mneme check`` output;
- gives each action exactly one treatment (proposal outcome table): ``deny``
  does not mutate; ``allow`` is the only trusted PASS; ``warn``, ``fail_open``
  and ``skip`` mutate visibly and are never reported as a PASS.

Nothing in this module intercepts anything. A tool that never calls the gate
(``ungoverned_save_text``) stays ungoverned.
"""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional

from mneme.integrations.agent_sdk import (
    ACTION_ALLOW,
    ACTION_DENY,
    ACTION_FAIL_OPEN,
    ACTION_SKIP,
    ACTION_WARN,
    GateResult,
)

# Same strings the shipped LangChain middleware emits
# (mneme/integrations/langchain/middleware.py); pinned against it in
# tests/integrations/langchain/test_custom_tool_proposal.py.
DENY_TAG = "[mneme] DENIED"
WARN_TAG = "[mneme] WARN"
UNEVALUATED_TAG = "[mneme] UNEVALUATED"
# Application wording: the middleware emits nothing for a skip.
NOT_EVALUATED_TAG = "[mneme] NOT EVALUATED"
# Orchestrator policy, never a Mneme verdict.
REFUSED_TAG = "[orchestrator] REFUSED"

# ``evaluate(kind, tool_input)`` with kind "write" or "edit".
Evaluator = Callable[[str, dict], GateResult]


def langchain_evaluator(gate) -> Evaluator:
    """Route proposals through ``MnemeLangChain.evaluate_tool_call``."""
    names = {"write": "write_file", "edit": "edit_file"}
    return lambda kind, tool_input: gate.evaluate_tool_call(names[kind], tool_input)


def agent_sdk_evaluator(sdk, cwd: str) -> Evaluator:
    """Route proposals through ``MnemeAgentSdk.evaluate_mutation``."""
    names = {"write": "Write", "edit": "Edit"}
    return lambda kind, tool_input: sdk.evaluate_mutation(names[kind], tool_input, cwd=cwd)


@dataclass
class ToolOutcome:
    """What one reference tool call did, kept apart by source.

    ``mneme_action`` is the gate's action, or ``None`` when the gate was not
    called. ``orchestrator_refused`` is the orchestrator's own decision and
    never changes ``mneme_action``.
    """

    text: str
    mneme_action: Optional[str]
    mutated: bool
    orchestrator_refused: bool = False
    target: Optional[Path] = None


def count_outcomes(outcomes: Iterable[ToolOutcome]) -> Dict[str, int]:
    """Bucket outcomes for reporting; orchestrator refusals in their own row.

    Only ``allow`` counts as a trusted PASS and only ``deny`` as a Mneme
    block. ``fail_open`` is unevaluated; ``skip`` and "gate not called" are
    not evaluated. A refusal is counted once in ``orchestrator_refused`` and
    leaves the Mneme bucket of the same attempt unchanged.
    """
    buckets = {
        ACTION_DENY: "mneme_blocked",
        ACTION_ALLOW: "trusted_pass",
        ACTION_WARN: "warned_not_blocked",
        ACTION_FAIL_OPEN: "unevaluated",
        ACTION_SKIP: "not_evaluated",
        None: "not_evaluated",
    }
    counts = Counter({name: 0 for name in set(buckets.values())})
    counts["orchestrator_refused"] = 0
    for outcome in outcomes:
        counts[buckets[outcome.mneme_action]] += 1
        if outcome.orchestrator_refused:
            counts["orchestrator_refused"] += 1
    return dict(counts)


class ReferenceFileTool:
    """A custom file tool that asks the gate before every mutation."""

    def __init__(self, evaluate: Evaluator, root, *, confine: bool = True) -> None:
        self._evaluate = evaluate
        self.root = Path(root).resolve(strict=True)
        self.confine = confine

    # ── Tools ───────────────────────────────────────────────────────────────

    def save_text(self, path: str, text: str) -> ToolOutcome:
        """Replace the file with ``text``."""
        target = self._canonical(path)
        if target is None:
            return self._refused()
        return self._write(target, text.encode("utf-8"))

    def append_text(self, path: str, text: str) -> ToolOutcome:
        """Append ``text``; submitted as the full resulting file content.

        The gate computes the introduced delta against the current file
        (ADR-018), so only the appended lines are checked.
        """
        target = self._canonical(path)
        if target is None:
            return self._refused()
        current = target.read_bytes() if target.is_file() else b""
        return self._write(target, current + text.encode("utf-8"))

    def edit_text(self, path: str, old: str, new: str) -> ToolOutcome:
        """Replace the first exact occurrence of ``old`` (an ``Edit`` shape)."""
        target = self._canonical(path)
        if target is None:
            return self._refused()
        result = self._evaluate(
            "edit", {"file_path": str(target), "old_string": old, "new_string": new}
        )

        def mutate() -> None:
            current = target.read_bytes().decode("utf-8")
            if old not in current:
                raise ValueError("old_string not found")
            target.write_bytes(current.replace(old, new, 1).encode("utf-8"))

        return self._apply(result, target, mutate)

    # ── Internals ───────────────────────────────────────────────────────────

    def _canonical(self, path: str) -> Optional[Path]:
        target = (self.root / path).resolve()
        if self.confine and not target.is_relative_to(self.root):
            return None
        return target

    def _refused(self) -> ToolOutcome:
        return ToolOutcome(
            text=f"{REFUSED_TAG} - target outside project root",
            mneme_action=None,
            mutated=False,
            orchestrator_refused=True,
        )

    def _write(self, target: Path, data: bytes) -> ToolOutcome:
        result = self._evaluate(
            "write", {"file_path": str(target), "content": data.decode("utf-8")}
        )
        return self._apply(result, target, lambda: target.write_bytes(data))

    def _apply(self, result: GateResult, target: Path, mutate) -> ToolOutcome:
        action = result.action
        if action == ACTION_DENY:
            reason = result.reason or "architectural decision violated"
            return ToolOutcome(f"{DENY_TAG} - {reason}", action, False, target=target)
        if action == ACTION_ALLOW:
            note = ""
        elif action == ACTION_WARN:
            note = (
                f"\n{WARN_TAG} - architectural decision flagged "
                f"(warn mode; not blocked):\n{result.reason}"
            )
        elif action == ACTION_FAIL_OPEN:
            note = (
                f"\n{UNEVALUATED_TAG} - failing open, this mutation was "
                f"NOT checked:\n{result.reason}"
            )
        elif action == ACTION_SKIP:
            note = f"\n{NOT_EVALUATED_TAG} - {result.reason}"
        else:
            raise ValueError(f"unhandled gate action: {action!r}")
        try:
            mutate()
        except (OSError, ValueError) as exc:
            return ToolOutcome(f"error: {exc}{note}", action, False, target=target)
        return ToolOutcome(f"saved{note}", action, True, target=target)


def refuse_on_unevaluated(evaluate: Evaluator, handler: Callable[[], str]):
    """Outer orchestrator wrapper (option 2C, layer 2).

    Asks the gate before the handler runs and refuses when Mneme could not
    evaluate the mutation. The refusal is orchestrator policy: Mneme's own
    action stays ``fail_open`` and is reported as unevaluated, never as a
    rule violation.
    """

    def run(kind: str, tool_input: dict) -> ToolOutcome:
        result = evaluate(kind, tool_input)
        if result.action == ACTION_FAIL_OPEN and result.evaluation_complete is False:
            return ToolOutcome(
                text=(
                    f"{REFUSED_TAG} - Mneme could not evaluate this mutation; "
                    f"orchestrator policy refuses unevaluated writes\n"
                    f"{UNEVALUATED_TAG} - this mutation was NOT checked:\n{result.reason}"
                ),
                mneme_action=result.action,
                mutated=False,
                orchestrator_refused=True,
            )
        if result.action == ACTION_DENY:
            reason = result.reason or "architectural decision violated"
            return ToolOutcome(f"{DENY_TAG} - {reason}", result.action, False)
        return ToolOutcome(handler(), result.action, True)

    return run


def ungoverned_save_text(root, path: str, text: str) -> str:
    """A custom tool that never calls Mneme: ungoverned by construction."""
    target = (Path(root) / path).resolve()
    target.write_bytes(text.encode("utf-8"))
    return "saved"


def make_dir_link(link: Path, target: Path) -> None:
    """Directory symlink, or a junction on Windows hosts without the symlink
    privilege. Skips the calling test when neither can be created."""
    import pytest

    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except OSError:
        pass
    if os.name == "nt":
        try:
            import _winapi

            _winapi.CreateJunction(str(target), str(link))
            return
        except (ImportError, OSError):
            pass
    pytest.skip("cannot create a directory link on this host")

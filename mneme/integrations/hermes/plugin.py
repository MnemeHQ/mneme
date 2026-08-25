"""Hermes plugin wiring for the Mneme integration.

This module contains no governance logic: it only binds
:class:`mneme.integrations.hermes.adapter.MnemeHermes` to Hermes' plugin
hook contract and translates gate outcomes to directives.

Install (POC): copy ``integrations/hermes-plugin/`` from this repository
to ``<project>/.hermes/plugins/mneme/``, enable project plugins
(``HERMES_ENABLE_PROJECT_PLUGINS=true``) and the plugin itself
(``plugins.enabled: [mneme]`` in Hermes config), and make the ``mneme``
package importable from Hermes' Python environment.

The plugin is fail-open by construction: Hermes swallows hook exceptions,
and :func:`mneme.integrations.hermes.adapter.directive_for` emits a block
directive only for a trusted strict-mode WARN/FAIL verdict.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from mneme.integrations.hermes.adapter import (
    ACTION_FAIL_OPEN,
    ACTION_WARN,
    GateResult,
    MnemeHermes,
    directive_for,
)

logger = logging.getLogger(__name__)


def _log_unevaluated(result: GateResult) -> None:
    """Fail-open outcomes must be visible, never silent."""
    if not result.reason:
        return
    if result.action == ACTION_WARN:
        logger.warning(
            "[mneme] WARN - architectural decision flagged (warn mode; "
            "not blocked):\n%s",
            result.reason,
        )
    elif result.action == ACTION_FAIL_OPEN:
        logger.warning(
            "[mneme] UNEVALUATED - failing open, this mutation was NOT "
            "checked:\n%s",
            result.reason,
        )


def make_gate(project_dir: Optional[str] = None, **kwargs: Any) -> MnemeHermes:
    return MnemeHermes(project_dir=project_dir or os.getcwd(), **kwargs)


def on_pre_tool_call(gate: MnemeHermes, tool_name: str = "", args: Optional[Dict] = None, **_: Any):
    """``pre_tool_call`` hook: block directive for trusted violations."""
    try:
        result = gate.evaluate_tool_call(tool_name, args or {}, cwd=gate.project_dir)
    except Exception as exc:  # pragma: no cover - defensive mirror of policy
        logger.warning("mneme-hermes: gate error, failing open: %s", exc)
        return None
    _log_unevaluated(result)
    return directive_for(result)


def on_pre_llm_call(gate: MnemeHermes, user_message: str = "", **_: Any):
    """``pre_llm_call`` hook: inject retrieved decisions as context."""
    try:
        return gate.pre_llm_call(user_message=user_message)
    except Exception as exc:
        logger.warning("mneme-hermes: context retrieval failed: %s", exc)
        return None


def register(ctx, gate: Optional[MnemeHermes] = None) -> None:
    """Hermes plugin entry point.

    ``gate`` is a test seam; production callers get the default constructor
    bound to the process working directory.
    """
    gate = gate or make_gate()
    ctx.register_hook("pre_tool_call", lambda **kw: on_pre_tool_call(gate, **kw))
    ctx.register_hook("pre_llm_call", lambda **kw: on_pre_llm_call(gate, **kw))


__all__ = [
    "register",
    "make_gate",
    "on_pre_tool_call",
    "on_pre_llm_call",
]

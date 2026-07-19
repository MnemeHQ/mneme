"""
llm_adapter.py — Thin wrapper around the Anthropic Messages API.

The single public method is ``complete(user, system=None)``. Passing
system=None produces a baseline call with no project context. Passing
system=<ContextPacket text> produces the Mneme-enhanced call. This
one-method interface makes before/after comparison clean in demo code.

Dry-run mode
------------
If ANTHROPIC_API_KEY is not set (or the adapter is constructed with
dry_run=True), complete() returns a stub LLMResponse instead of calling
the API. The stub contains the full prompt that *would* have been sent,
so the demo is still useful without credentials.

Swapping providers
------------------
To support a different provider, replace _call_api() only.
complete() and the dry-run logic stay the same.
"""

from __future__ import annotations

import os
import textwrap

from mneme.schemas import LLMResponse

# Default model. Override with MNEME_MODEL environment variable.
DEFAULT_MODEL = "claude-sonnet-4-6"


class LLMAdapter:
    """Calls an Anthropic model with an optional system context.

    Args:
        model:      Model identifier. Falls back to MNEME_MODEL env var,
                    then DEFAULT_MODEL.
        max_tokens: Maximum tokens in the completion.
        dry_run:    If True, skip the API call and return a formatted stub
                    showing what would have been sent. Automatically True
                    when ANTHROPIC_API_KEY is not set.
    """

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int = 1024,
        dry_run: bool = False,
    ) -> None:
        self.model = model or os.environ.get("MNEME_MODEL", DEFAULT_MODEL)
        self.max_tokens = max_tokens
        self.dry_run = dry_run or not bool(os.environ.get("ANTHROPIC_API_KEY"))
        self._client = None  # initialised lazily on first real call

    # ── Public interface ──────────────────────────────────────────────────────

    def complete(self, user: str, system: str | None = None) -> LLMResponse:
        """Send a user message to the model, optionally with a system context.

        Call with system=None for a baseline (no project context).
        Call with system=<formatted context> for the Mneme-enhanced version.

        Args:
            user:   The question or task to send to the model.
            system: Optional system prompt. If None or empty, the call is
                    made without a system context (baseline mode).

        Returns:
            LLMResponse with content, model identifier, and token usage.
            In dry-run mode the content shows the prompt that would be sent.
        """
        if self.dry_run:
            return self._dry_run_response(user, system)
        return self._call_api(user, system)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_client(self):
        """Return the Anthropic client, initialising it on first access."""
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(
                api_key=os.environ["ANTHROPIC_API_KEY"]
            )
        return self._client

    def _call_api(self, user: str, system: str | None) -> LLMResponse:
        """Make the actual API call. Not called in dry-run mode.

        Args:
            user:   User message content.
            system: System prompt string, or None/empty for no system context.

        Returns:
            LLMResponse populated from the API response.
        """
        client = self._get_client()

        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": user}],
        }
        if system:
            kwargs["system"] = system

        message = client.messages.create(**kwargs)

        return LLMResponse(
            content=message.content[0].text,
            model=self.model,
            usage={
                "input": message.usage.input_tokens,
                "output": message.usage.output_tokens,
            },
        )

    def _dry_run_response(self, user: str, system: str | None) -> LLMResponse:
        """Return a stub response showing what would have been sent.

        Args:
            user:   User message that would have been sent.
            system: System prompt that would have been sent (or None).

        Returns:
            LLMResponse with content describing the dry-run payload.
        """
        mode = "WITH MNEME CONTEXT" if system else "BASELINE - no system context"
        parts = [f"[DRY RUN | {mode}]", "", f"USER: {user}"]

        if system:
            parts += ["", "SYSTEM CONTEXT:", ""]
            # Indent each line of the system prompt for readability.
            for line in system.splitlines():
                parts.append(f"  {line}" if line.strip() else "")

        return LLMResponse(
            content="\n".join(parts),
            model=f"dry-run/{self.model}",
            usage={"input": 0, "output": 0},
        )

"""Deterministic matching primitives for typed Mneme rules."""
from __future__ import annotations

import re


_LITERAL_CONTINUATION = re.compile(r"[A-Za-z0-9_-]")


def literal_in_text(literal: str, text: str) -> bool:
    """Match a case-sensitive literal without matching a longer identifier.

    A boundary is required only when the corresponding edge of the literal is
    identifier-like. This makes ``install legacy-package`` match the
    standalone command but not the longer name
    ``install legacy-package-next``.
    """
    if not literal:
        return False
    pattern = re.escape(literal)
    if _LITERAL_CONTINUATION.fullmatch(literal[0]):
        pattern = r"(?<![A-Za-z0-9_-])" + pattern
    if _LITERAL_CONTINUATION.fullmatch(literal[-1]):
        pattern += r"(?![A-Za-z0-9_-])"
    return bool(re.search(pattern, text))


__all__ = ["literal_in_text"]

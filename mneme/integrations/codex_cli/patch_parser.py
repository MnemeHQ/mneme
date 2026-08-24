"""Parser for the frozen Codex CLI 0.149.1 ``apply_patch`` wire contract.

Transport parsing only: this module turns an observed PreToolUse payload into
``(target_path, introduced_content)`` for the single proven case -- a patch
containing exactly one ``*** Add File: <path>`` operation. It knows nothing
about Mneme policy, never touches the filesystem, and never spawns
subprocesses; enforcement decisions belong to the gate slice (M1c) that
consumes this output.

The grammar is the one captured in R0 evidence and frozen by
``tests/integrations/codex_cli/test_patch_contract.py``::

    *** Begin Patch
    *** Add File: probe_target.py
    +def probe_marker() -> int:
    +    return 42
    *** End Patch

Invariant: any operation or structure this parser does not understand is an
explicit :class:`CodexPatchParseError`. A payload containing ``Update File``,
``Delete File``, additional operations, or unrecognized lines must fail the
parse rather than be partially interpreted -- a partially parsed proposal must
never be mistaken for a governed one.
"""
from __future__ import annotations

from pathlib import PureWindowsPath, PurePosixPath
from typing import Any, Dict, Tuple

BEGIN_MARKER = "*** Begin Patch"
END_MARKER = "*** End Patch"
ADD_FILE_HEADER = "*** Add File:"
OPERATION_PREFIX = "*** "


class CodexPatchParseError(Exception):
    """Raised when an apply_patch proposal does not match the frozen contract.

    Transport-level parse failure. Callers must treat this as "proposal not
    understood", never as PASS.
    """


def _check_path(path: str) -> str:
    if not path or not path.strip():
        raise CodexPatchParseError("Add File has an empty target path")
    if path != path.strip():
        raise CodexPatchParseError(
            f"Add File target path has surrounding whitespace: {path!r}"
        )
    if len(PureWindowsPath(path).drive) or path.startswith("/") or "\\" in path:
        raise CodexPatchParseError(
            f"Add File target path must be workspace-relative: {path!r}"
        )
    parts = PurePosixPath(path).parts
    if any(part == ".." for part in parts):
        raise CodexPatchParseError(
            f"Add File target path must not traverse upward: {path!r}"
        )
    return path


def parse_patch(command: Any) -> Tuple[str, str]:
    """Parse one Add File-only apply_patch script.

    Returns ``(target_path, introduced_content)`` where introduced content
    preserves line content exactly after removing the single structural
    leading ``+`` (including interior empty lines), with a trailing newline
    per introduced line.
    """
    if not isinstance(command, str):
        raise CodexPatchParseError(
            f"apply_patch command must be a string, got {type(command).__name__}"
        )

    stripped = command.rstrip("\n")
    if not stripped.startswith(BEGIN_MARKER):
        raise CodexPatchParseError("patch does not start with Begin Patch marker")
    end_index = stripped.rfind(END_MARKER)
    if end_index == -1:
        raise CodexPatchParseError("patch does not end with End Patch marker")
    trailing = stripped[end_index + len(END_MARKER):]
    if trailing.strip():
        raise CodexPatchParseError(
            f"unexpected content after End Patch marker: {trailing!r}"
        )

    body = stripped[len(BEGIN_MARKER):end_index]

    op_lines = [
        (i, line)
        for i, line in enumerate(body.splitlines())
        if line.startswith(OPERATION_PREFIX)
    ]
    if not op_lines:
        raise CodexPatchParseError("patch contains no operation")
    if len(op_lines) > 1:
        details = ", ".join(line.strip() for _, line in op_lines)
        raise CodexPatchParseError(
            f"multi-operation patches are not supported by this parser: {details}"
        )

    op_index, op_line = op_lines[0]
    header, sep, raw_path = op_line.partition(":")
    if header.strip() != ADD_FILE_HEADER.rstrip(":").strip() or not sep:
        unsupported = op_line.split(":")[0].strip()
        raise CodexPatchParseError(
            f"unsupported patch operation {unsupported!r}; "
            "only '*** Add File:' is supported"
        )
    target_path = _check_path(raw_path.strip())

    content_lines = []
    for line in body.splitlines()[op_index + 1:]:
        if not line.startswith("+"):
            raise CodexPatchParseError(
                f"malformed Add File body line (expected leading '+'): {line!r}"
            )
        content_lines.append(line[1:])

    introduced = "".join(line + "\n" for line in content_lines)
    return target_path, introduced


def parse_pretooluse_payload(payload: Any) -> Tuple[str, str]:
    """Extract ``(target_path, introduced_content)`` from a PreToolUse event.

    Rejects anything that is not an apply_patch tool call with a string
    ``tool_input.command``.
    """
    if not isinstance(payload, dict):
        raise CodexPatchParseError("hook payload must be a JSON object")
    if payload.get("tool_name") != "apply_patch":
        raise CodexPatchParseError(
            f"expected tool_name 'apply_patch', got {payload.get('tool_name')!r}"
        )
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        raise CodexPatchParseError("payload has no tool_input object")
    if "command" not in tool_input:
        raise CodexPatchParseError("payload has no tool_input.command")
    return parse_patch(tool_input["command"])

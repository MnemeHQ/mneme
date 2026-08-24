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

import re
from pathlib import PureWindowsPath, PurePosixPath
from typing import Any, Dict, Tuple

BEGIN_MARKER = "*** Begin Patch"
END_MARKER = "*** End Patch"
ADD_FILE_HEADER = "*** Add File:"
UPDATE_FILE_HEADER = "*** Update File:"
OPERATION_PREFIX = "*** "
HUNK_SEPARATOR = "@@"


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

    Contract note (M1e-b): Add File was observed with a workspace-relative
    path; Update File (see :func:`parse_update_file`) was observed absolute.
    Neither form is generalized beyond evidence.
    """
    _validate_envelope(command)
    body_lines = _body_lines(command)
    op_index, op_line = _single_operation(body_lines)

    header, sep, raw_path = op_line.partition(":")
    if header.strip() != ADD_FILE_HEADER.rstrip(":").strip() or not sep:
        unsupported = op_line.split(":")[0].strip()
        raise CodexPatchParseError(
            f"unsupported patch operation {unsupported!r}; "
            "only '*** Add File:' is supported by parse_patch"
        )
    target_path = _check_path(raw_path.strip())

    content_lines = []
    for line in body_lines[op_index + 1:]:
        if not line.startswith("+"):
            raise CodexPatchParseError(
                f"malformed Add File body line (expected leading '+'): {line!r}"
            )
        content_lines.append(line[1:])

    introduced = "".join(line + "\n" for line in content_lines)
    return target_path, introduced


def _validate_envelope(command: Any) -> None:
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


def _body_lines(command: str) -> list:
    stripped = command.rstrip("\n")
    end_index = stripped.rfind(END_MARKER)
    return stripped[len(BEGIN_MARKER):end_index].splitlines()


def _single_operation(body_lines: list) -> tuple:
    op_lines = [
        (i, line) for i, line in enumerate(body_lines)
        if line.startswith(OPERATION_PREFIX)
    ]
    if not op_lines:
        raise CodexPatchParseError("patch contains no operation")
    if len(op_lines) > 1:
        details = ", ".join(line.strip() for _, line in op_lines)
        raise CodexPatchParseError(
            f"multi-operation patches are not supported by this parser: {details}"
        )
    return op_lines[0]


def _operation_kind(op_line: str) -> str:
    return op_line.split(":", 1)[0].strip()


def _check_update_path(path: str) -> str:
    """Update File path validation per the frozen M1e-b contract.

    The observed form is absolute; relative is accepted as a possibility
    without claiming it was observed. Empty/whitespace paths and upward
    traversal in relative paths are rejected.
    """
    if not path or not path.strip():
        raise CodexPatchParseError("Update File has an empty target path")
    if not PureWindowsPath(path).drive and not path.startswith("/"):
        components = re.split(r"[/\\]", path)
        if any(part == ".." for part in components):
            raise CodexPatchParseError(
                f"Update File target path must not traverse upward: {path!r}"
            )
    return path


def parse_update_file(command: Any, current_content: Any) -> Tuple[str, str]:
    """Parse one Update File-only apply_patch script against a snapshot.

    ``current_content`` is the caller-supplied current file content (any EOL
    style; matching is line-content based). The parser performs no filesystem
    I/O and makes no claim about the final file's byte representation.

    Returns ``(target_path, introduced_content)`` where introduced content is
    the exact ``+``-line contents joined with newlines -- blank introduced
    lines survive untouched. Every hunk's context/removal sequence must match
    the supplied snapshot uniquely and deterministically; anything else raises
    :class:`CodexPatchParseError`.
    """
    _validate_envelope(command)
    body_lines = _body_lines(command)
    op_index, op_line = _single_operation(body_lines)

    header, sep, raw_path = op_line.partition(":")
    if header.strip() != UPDATE_FILE_HEADER.rstrip(":").strip() or not sep:
        unsupported = _operation_kind(op_line)
        raise CodexPatchParseError(
            f"unsupported patch operation {unsupported!r}; "
            "only '*** Update File:' is supported by parse_update_file"
        )
    target_path = _check_update_path(raw_path.strip())

    if not isinstance(current_content, str):
        raise CodexPatchParseError(
            "Update File parsing requires current file content as a string"
        )

    hunk_body = body_lines[op_index + 1:]
    hunks: list[list[str]] = []
    for line in hunk_body:
        if line == HUNK_SEPARATOR:
            hunks.append([])
        elif hunks:
            hunks[-1].append(line)
        else:
            raise CodexPatchParseError(
                f"patch content before first hunk separator: {line!r}"
            )
    if not hunks:
        raise CodexPatchParseError("Update File patch contains no hunks")

    snapshot = current_content.splitlines()
    introduced: list[str] = []
    cursor = 0
    for hunk_index, hunk in enumerate(hunks):
        expected_block: list[str] = []
        added: list[str] = []
        seen_addition = False
        for line in hunk:
            tag, content = line[:1], line[1:]
            if tag == "+":
                # Observed grammar: additions form a single trailing block
                # after their hunk's context/removals; a context or removal
                # line after an addition would make attribution ambiguous.
                added.append(content)
                seen_addition = True
            else:
                if seen_addition:
                    raise CodexPatchParseError(
                        "malformed hunk: context/removal line after a "
                        f"'+' line: {line!r}"
                    )
                if tag == " ":
                    expected_block.append(content)
                elif tag == "-":
                    expected_block.append(content)
                else:
                    raise CodexPatchParseError(
                        f"malformed hunk line (expected ' ', '-', or '+'): {line!r}"
                    )

        # Locate the context+removal block in the remaining snapshot. Exactly
        # one match is acceptable; zero or several are both hard failures.
        matches = [
            i for i in range(cursor, len(snapshot) - len(expected_block) + 1)
            if snapshot[i:i + len(expected_block)] == expected_block
        ]
        if not matches:
            raise CodexPatchParseError(
                f"hunk {hunk_index}: context/removal sequence not found in "
                f"current file content: {expected_block!r}"
            )
        if len(matches) > 1:
            raise CodexPatchParseError(
                f"hunk {hunk_index}: context/removal sequence matches "
                f"{len(matches)} locations; refusing an ambiguous update"
            )
        cursor = matches[0] + len(expected_block)
        introduced.extend(added)

    return target_path, "\n".join(introduced)


def operation_kind(command: Any) -> str:
    """Return the single operation kind (e.g. ``'*** Add File'``).

    Validates the envelope first; raises :class:`CodexPatchParseError` for
    malformed envelopes, missing operations, or multi-operation patches.
    """
    _validate_envelope(command)
    return _operation_kind(_single_operation(_body_lines(command))[1])


def update_target_path(command: Any) -> str:
    """Return the validated target path of an Update File-only script."""
    _validate_envelope(command)
    body_lines = _body_lines(command)
    op_index, op_line = _single_operation(body_lines)
    if _operation_kind(op_line) != UPDATE_FILE_HEADER.rstrip(":").strip():
        raise CodexPatchParseError(
            f"not an Update File patch: {_operation_kind(op_line)!r}"
        )
    _, sep, raw_path = op_line.partition(":")
    if not sep:
        raise CodexPatchParseError("Update File has a malformed header")
    return _check_update_path(raw_path.strip())


def parse_pretooluse_payload(payload: Any, current_content: Any = None) -> Tuple[str, str]:
    """Extract ``(target_path, introduced_content)`` from a PreToolUse event.

    Add File payloads parse as before. Update File payloads require the
    caller-supplied ``current_content`` snapshot.
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

    command = tool_input["command"]
    _validate_envelope(command)
    kind = _operation_kind(_single_operation(_body_lines(command))[1])
    if kind == UPDATE_FILE_HEADER.rstrip(":"):
        if current_content is None:
            raise CodexPatchParseError(
                "Update File payload requires a current-file snapshot"
            )
        return parse_update_file(command, current_content)
    return parse_patch(command)

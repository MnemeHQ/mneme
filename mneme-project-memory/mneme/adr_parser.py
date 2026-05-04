"""
adr_parser.py — Parse ADR markdown files into typed ADR records.

ADR files follow a simple convention: a YAML frontmatter block delimited by
``---`` lines at the very top of the file, followed by free-form markdown.

This module is responsible only for parsing — schema validation and
precedence resolution live in ``adr_compiler``. A successfully parsed ADR
may still be schema-invalid; that is a deliberate separation of concerns.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from mneme.adr_schema import ADR, ADRParseError


_FRONTMATTER_DELIM = "---"


def parse_adr_file(path: str | Path) -> ADR:
    """Parse one ADR markdown file and return a populated ``ADR`` record.

    Args:
        path: Path to the ADR markdown file.

    Returns:
        An ``ADR`` populated from the file's frontmatter and body. Schema
        validation is intentionally NOT performed here — call into
        ``adr_compiler.validate_corpus`` to enforce required fields,
        enums, and references.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ADRParseError:     If the file lacks a YAML frontmatter block or
                           the frontmatter is not parseable as YAML.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    metadata, body = _split_frontmatter(text, path)
    return _build_adr(metadata, body, path)


def parse_adr_directory(directory: str | Path) -> list[ADR]:
    """Parse every ``.md`` file in ``directory`` and return a sorted list.

    Files are sorted by ADR id for deterministic output regardless of
    filesystem ordering.

    Args:
        directory: Path to the directory containing ADR markdown files.

    Returns:
        A list of ``ADR`` records, sorted by ``id``.
    """
    directory = Path(directory)
    adrs = [parse_adr_file(p) for p in sorted(directory.glob("*.md"))]
    return sorted(adrs, key=lambda a: a.id)


# ── Internals ─────────────────────────────────────────────────────────────────


def _split_frontmatter(text: str, path: Path) -> tuple[dict, str]:
    """Split a markdown file into (frontmatter dict, body text).

    Raises:
        ADRParseError: If no leading frontmatter delimiter is found, if the
                       closing delimiter is missing, or if the YAML inside
                       fails to parse.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != _FRONTMATTER_DELIM:
        raise ADRParseError(
            f"{path}: missing YAML frontmatter (expected file to start with '---')"
        )

    closing_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FRONTMATTER_DELIM:
            closing_idx = i
            break

    if closing_idx is None:
        raise ADRParseError(
            f"{path}: unterminated YAML frontmatter (no closing '---' found)"
        )

    raw_yaml = "".join(lines[1:closing_idx])
    body = "".join(lines[closing_idx + 1 :]).lstrip("\n")

    try:
        loaded = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError as exc:
        raise ADRParseError(f"{path}: malformed YAML frontmatter: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ADRParseError(
            f"{path}: malformed YAML frontmatter (expected a mapping, got "
            f"{type(loaded).__name__})"
        )

    return loaded, body


def _build_adr(meta: dict, body: str, path: Path) -> ADR:
    """Construct an ``ADR`` from a frontmatter mapping and body string.

    Missing fields are filled with empty strings / empty lists so that the
    schema validator can report them uniformly. ``ADRParseError`` is only
    raised for structural problems (e.g., wrong type for ``supersedes``).
    """
    supersedes_raw = meta.get("supersedes", [])
    if supersedes_raw is None:
        supersedes_raw = []
    if not isinstance(supersedes_raw, list):
        raise ADRParseError(
            f"{path}: 'supersedes' must be a YAML list, got "
            f"{type(supersedes_raw).__name__}"
        )

    return ADR(
        id=str(meta.get("id", "")),
        title=str(meta.get("title", "")),
        status=str(meta.get("status", "")),  # type: ignore[arg-type]
        priority=str(meta.get("priority", "")),  # type: ignore[arg-type]
        date=str(meta.get("date", "")),
        scope=str(meta.get("scope", "")),
        supersedes=[str(x) for x in supersedes_raw],
        body=body,
        source_path=str(path),
    )

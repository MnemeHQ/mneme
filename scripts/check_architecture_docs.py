#!/usr/bin/env python3
"""Deterministic integrity checks for Mneme architecture documentation.

This checker deliberately validates only facts that can be established from
repository text and paths. It does not infer architecture from source code and
does not use an LLM to judge whether a C4 diagram is semantically correct.

Checks:
- required sections exist in docs/architecture/README.md;
- relative Markdown links in docs/architecture/*.md resolve inside the repo;
- ADR frontmatter IDs are unique;
- ADR map links resolve to ADR files whose frontmatter ID and status match;
- proposed ADRs shown in the ADR map are explicitly treated as proposed,
  target, or deferred in the current-versus-target section.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHITECTURE_DIR = Path("docs/architecture")
ARCHITECTURE_INDEX = ARCHITECTURE_DIR / "README.md"
ADR_DIR = Path("docs/adr")

REQUIRED_ARCHITECTURE_HEADINGS: tuple[str, ...] = (
    "## Current architecture at a glance",
    "## Important current-versus-target boundary",
    "# C4 Level 1 — System Context",
    "# C4 Level 2 — Containers",
    "# C4 Level 3 — Core Components",
    "# Research boundary — O1A Open Architecture",
    "# ADR map",
    "# Maintenance rules",
)

_LINK_RE = re.compile(r"!?" + r"\[[^\]]*\]\(([^)]+)\)")
_ADR_MAP_ROW_RE = re.compile(
    r"^\|\s*\[(ADR-\d+)\]\(([^)]+)\)\s*\|\s*([^|]+?)\s*\|",
    re.MULTILINE,
)
_ADR_ID_RE = re.compile(r"ADR-\d+")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_fenced_code(text: str) -> str:
    """Remove fenced Markdown code blocks before scanning prose links."""
    fence = chr(96) * 3
    return re.sub(re.escape(fence) + r".*?" + re.escape(fence), "", text, flags=re.DOTALL)


def _frontmatter(path: Path) -> dict[str, str]:
    """Parse the simple scalar YAML frontmatter used by Mneme ADRs."""
    text = _read(path)
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    values: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return values
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return {}


def _resolve_repo_relative_link(
    *,
    repo_root: Path,
    source_path: Path,
    target: str,
) -> tuple[Path | None, str | None]:
    """Resolve one local Markdown link or return an error description."""
    raw = target.strip()
    if not raw or raw.startswith("#"):
        return None, None

    lowered = raw.lower()
    if lowered.startswith(("http://", "https://", "mailto:", "tel:", "data:")):
        return None, None

    raw = raw.split(maxsplit=1)[0]
    raw = raw.split("#", 1)[0].split("?", 1)[0]
    raw = unquote(raw.strip("<>"))
    if not raw:
        return None, None

    root = repo_root.resolve()
    resolved = (repo_root / source_path.parent / raw).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None, f"{source_path.as_posix()}: link escapes repository: {target}"

    return resolved, None


def _architecture_section(text: str, heading: str) -> str:
    """Return text under a heading through the next heading of same/higher level."""
    start = text.find(heading)
    if start < 0:
        return ""
    line_end = text.find("\n", start)
    if line_end < 0:
        return ""
    level = len(heading) - len(heading.lstrip("#"))
    pattern = re.compile(rf"^#{{1,{level}}}\s+", re.MULTILINE)
    match = pattern.search(text, line_end + 1)
    end = match.start() if match else len(text)
    return text[line_end + 1 : end]


def _normalize_status(value: str) -> str:
    return value.strip().strip("*" + chr(96)).strip().lower()


def validate_architecture_docs(repo_root: Path = REPO_ROOT) -> list[str]:
    """Return deterministic validation errors; empty means the corpus is valid."""
    repo_root = repo_root.resolve()
    errors: list[str] = []
    architecture_index = repo_root / ARCHITECTURE_INDEX
    architecture_dir = repo_root / ARCHITECTURE_DIR
    adr_dir = repo_root / ADR_DIR

    if not architecture_index.is_file():
        return [f"missing architecture entry point: {ARCHITECTURE_INDEX.as_posix()}"]
    if not adr_dir.is_dir():
        return [f"missing ADR directory: {ADR_DIR.as_posix()}"]

    index_text = _read(architecture_index)

    for heading in REQUIRED_ARCHITECTURE_HEADINGS:
        if heading not in index_text:
            errors.append(
                f"{ARCHITECTURE_INDEX.as_posix()}: missing required heading: {heading}"
            )

    for path in sorted(architecture_dir.glob("*.md")):
        rel_source = path.relative_to(repo_root)
        prose = _strip_fenced_code(_read(path))
        for match in _LINK_RE.finditer(prose):
            target = match.group(1)
            resolved, error = _resolve_repo_relative_link(
                repo_root=repo_root,
                source_path=rel_source,
                target=target,
            )
            if error:
                errors.append(error)
                continue
            if resolved is not None and not resolved.exists():
                errors.append(
                    f"{rel_source.as_posix()}: broken relative link: {target}"
                )

    adr_by_id: dict[str, tuple[Path, dict[str, str]]] = {}
    for path in sorted(adr_dir.glob("ADR-*.md")):
        rel = path.relative_to(repo_root)
        frontmatter = _frontmatter(path)
        adr_id = frontmatter.get("id", "").strip()
        status = frontmatter.get("status", "").strip()
        if not adr_id:
            errors.append(f"{rel.as_posix()}: ADR frontmatter missing id")
            continue
        if not status:
            errors.append(f"{rel.as_posix()}: ADR frontmatter missing status")
        if adr_id in adr_by_id:
            first = adr_by_id[adr_id][0].relative_to(repo_root).as_posix()
            errors.append(
                f"{rel.as_posix()}: duplicate ADR id {adr_id}; first seen at {first}"
            )
            continue
        adr_by_id[adr_id] = (path, frontmatter)

    rows = list(_ADR_MAP_ROW_RE.finditer(index_text))
    if not rows:
        errors.append(f"{ARCHITECTURE_INDEX.as_posix()}: ADR map has no ADR rows")

    seen_map_ids: set[str] = set()
    proposed_map_ids: set[str] = set()
    for row in rows:
        label_id, target, displayed_status = row.groups()
        if label_id in seen_map_ids:
            errors.append(
                f"{ARCHITECTURE_INDEX.as_posix()}: duplicate ADR map row: {label_id}"
            )
            continue
        seen_map_ids.add(label_id)

        resolved, error = _resolve_repo_relative_link(
            repo_root=repo_root,
            source_path=ARCHITECTURE_INDEX,
            target=target,
        )
        if error:
            errors.append(error)
            continue
        if resolved is None or not resolved.is_file():
            errors.append(
                f"{ARCHITECTURE_INDEX.as_posix()}: ADR map link does not resolve: "
                f"{label_id} -> {target}"
            )
            continue

        frontmatter = _frontmatter(resolved)
        actual_id = frontmatter.get("id", "").strip()
        actual_status = frontmatter.get("status", "").strip()
        if actual_id != label_id:
            errors.append(
                f"{ARCHITECTURE_INDEX.as_posix()}: ADR map label {label_id} "
                f"points to frontmatter id {actual_id or '<missing>'}"
            )
        if _normalize_status(displayed_status) != _normalize_status(actual_status):
            errors.append(
                f"{ARCHITECTURE_INDEX.as_posix()}: ADR map status mismatch for "
                f"{label_id}: displayed={displayed_status.strip()!r}, "
                f"frontmatter={actual_status or '<missing>'!r}"
            )
        if _normalize_status(actual_status) == "proposed":
            proposed_map_ids.add(label_id)

    target_section = _architecture_section(
        index_text, "## Important current-versus-target boundary"
    )
    target_ids = set(_ADR_ID_RE.findall(target_section))
    lower_target = target_section.lower()
    for adr_id in sorted(proposed_map_ids):
        if adr_id not in target_ids:
            errors.append(
                f"{ARCHITECTURE_INDEX.as_posix()}: proposed {adr_id} in ADR map "
                "is not identified in the current-versus-target section"
            )
            continue
        pos = lower_target.find(adr_id.lower())
        context = lower_target[max(0, pos - 240) : pos + 360]
        if not any(word in context for word in ("proposed", "target", "deferred")):
            errors.append(
                f"{ARCHITECTURE_INDEX.as_posix()}: proposed {adr_id} lacks an "
                "explicit proposed/target/deferred marker near its target-section reference"
            )

    return sorted(set(errors))


def main() -> int:
    errors = validate_architecture_docs()
    if errors:
        print("architecture documentation validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("architecture documentation validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

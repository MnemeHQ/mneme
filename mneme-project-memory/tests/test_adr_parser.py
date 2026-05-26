"""Tests for the ADR markdown frontmatter parser."""
from __future__ import annotations

from pathlib import Path

import pytest

from mneme.adr_parser import parse_adr_file, parse_adr_directory
from mneme.adr_schema import ADR, ADRParseError

FIXTURES = Path(__file__).parent / "fixtures"
VALID_DIR = FIXTURES / "adrs_valid"
MALFORMED_DIR = FIXTURES / "adrs_malformed"


def test_parse_full_frontmatter_returns_adr_with_all_fields():
    adr = parse_adr_file(VALID_DIR / "ADR-001-storage-backend.md")
    assert isinstance(adr, ADR)
    assert adr.id == "ADR-001"
    assert adr.title == "Use JSON file storage"
    assert adr.status == "accepted"
    assert adr.priority == "foundational"
    assert adr.date == "2026-01-10"
    assert adr.scope == "storage"
    assert adr.supersedes == []
    assert "Use a single JSON file" in adr.body
    assert adr.source_path == str(VALID_DIR / "ADR-001-storage-backend.md")


def test_parse_explicit_empty_supersedes_list():
    adr = parse_adr_file(VALID_DIR / "ADR-002-embeddings.md")
    assert adr.id == "ADR-002"
    assert adr.scope == "storage.embeddings"
    assert adr.supersedes == []


def test_parse_directory_returns_all_valid_adrs_sorted_by_id():
    adrs = parse_adr_directory(VALID_DIR)
    assert [a.id for a in adrs] == ["ADR-001", "ADR-002"]


def test_missing_frontmatter_raises_parse_error():
    with pytest.raises(ADRParseError, match="frontmatter"):
        parse_adr_file(MALFORMED_DIR / "ADR-100-no-frontmatter.md")


def test_malformed_yaml_raises_parse_error():
    with pytest.raises(ADRParseError, match="YAML"):
        parse_adr_file(MALFORMED_DIR / "ADR-101-bad-yaml.md")


def test_parse_adr_file_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        parse_adr_file(VALID_DIR / "does-not-exist.md")


def test_parse_directory_ignores_non_adr_markdown(tmp_path):
    """parse_adr_directory must restrict itself to ADR-*.md files so that
    incidental markdown (README, scratch notes) in the ADR directory does
    not crash the strict parser."""
    (tmp_path / "ADR-001-real.md").write_text(
        "---\nid: ADR-001\ntitle: real\nstatus: accepted\npriority: normal\n"
        "date: 2026-01-01\nscope: test\n---\n\nbody\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Index\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("scratch\n", encoding="utf-8")

    adrs = parse_adr_directory(tmp_path)
    assert [a.id for a in adrs] == ["ADR-001"]

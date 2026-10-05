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


# ── ADR-030 §10: parsed-bytes source revision ────────────────────────────────


def test_parse_records_hash_of_exact_parsed_bytes(tmp_path):
    import hashlib

    path = tmp_path / "ADR-901.md"
    data = (
        "---\r\nid: ADR-901\r\ntitle: CRLF\r\nstatus: accepted\r\n"
        "priority: normal\r\ndate: 2026-01-01\r\nscope: storage\r\n---\r\n\r\n"
        "Body line\r\n"
    ).encode("utf-8")
    path.write_bytes(data)

    lf_path = tmp_path / "lf" / "ADR-901.md"
    lf_path.parent.mkdir()
    lf_data = data.replace(b"\r\n", b"\n")
    lf_path.write_bytes(lf_data)

    adr = parse_adr_file(path)
    lf_adr = parse_adr_file(lf_path)

    assert adr.source_sha256 == hashlib.sha256(data).hexdigest()
    assert lf_adr.source_sha256 == hashlib.sha256(lf_data).hexdigest()
    # Decoding keeps read_text semantics (universal newlines): same parsed
    # record, distinct byte revisions.
    assert adr.body == lf_adr.body
    assert "\r" not in adr.body
    assert adr.source_sha256 != lf_adr.source_sha256


def test_source_sha256_is_excluded_from_adr_equality():
    base = dict(
        id="ADR-902", title="t", status="accepted", priority="normal",
        date="2026-01-01", scope="",
    )
    assert ADR(**base, source_sha256="a" * 64) == ADR(**base)

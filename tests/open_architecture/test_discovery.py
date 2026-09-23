"""
tests.open_architecture.test_discovery — Tests for deterministic repository source discovery.

Covers all 27 required unit test cases plus end-to-end integration with O1A2.1.
All tests run offline without network access.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from mneme.open_architecture.discovery import (
    DEFAULT_MAX_DOCUMENT_BYTES,
    DOCUMENTATION_EXTENSIONS,
    DiscoveredSourceDocument,
    DiscoveryResult,
    SourceDiscoveryDiagnostic,
    discover_sources,
)
from mneme.open_architecture.execution import materialize_repository
from mneme.open_architecture.manifest import RepositoryConfig


# ── Data Model Unit Tests ──────────────────────────────────────────────────────


class TestDiscoveryModels:
    def test_valid_document_construction(self):
        doc = DiscoveredSourceDocument(
            relative_path="docs/adr/ADR-001.md",
            source_type="adr",
            content_hash="sha256:" + "a" * 64,
            content="# Decision",
            metadata={"byte_length": 10},
        )
        assert doc.relative_path == "docs/adr/ADR-001.md"
        assert doc.source_type == "adr"
        assert doc.content_hash == "sha256:" + "a" * 64

    def test_invalid_relative_path_windows_slash(self):
        with pytest.raises(ValueError, match="relative_path must be a normalized"):
            DiscoveredSourceDocument(
                relative_path="docs\\adr\\ADR-001.md",
                source_type="adr",
                content_hash="sha256:" + "a" * 64,
                content="",
                metadata={},
            )

    def test_invalid_relative_path_leading_slash(self):
        with pytest.raises(ValueError, match="relative_path must be a normalized"):
            DiscoveredSourceDocument(
                relative_path="/docs/adr/ADR-001.md",
                source_type="adr",
                content_hash="sha256:" + "a" * 64,
                content="",
                metadata={},
            )

    def test_invalid_source_type(self):
        with pytest.raises(ValueError, match="source_type must be 'adr' or 'documentation'"):
            DiscoveredSourceDocument(
                relative_path="doc.md",
                source_type="unknown_type",
                content_hash="sha256:" + "a" * 64,
                content="",
                metadata={},
            )

    def test_invalid_content_hash(self):
        with pytest.raises(ValueError, match="content_hash must be 'sha256:<64 hex>'"):
            DiscoveredSourceDocument(
                relative_path="doc.md",
                source_type="documentation",
                content_hash="md5:1234",
                content="",
                metadata={},
            )


# ── Discovery Behavior Tests ───────────────────────────────────────────────────


class TestSourceDiscovery:
    # 1. Deterministic discovery ordering
    def test_deterministic_discovery_ordering(self, tmp_path: Path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "b.md").write_text("b", encoding="utf-8")
        (tmp_path / "docs" / "c.md").write_text("c", encoding="utf-8")
        (tmp_path / "a.md").write_text("a", encoding="utf-8")
        (tmp_path / "README.md").write_text("readme", encoding="utf-8")

        result = discover_sources(tmp_path)
        paths = [d.relative_path for d in result.documents]
        assert paths == ["README.md", "a.md", "docs/b.md", "docs/c.md"]

    # 2. Repository-relative POSIX paths
    def test_repository_relative_posix_paths(self, tmp_path: Path):
        (tmp_path / "sub" / "deep").mkdir(parents=True)
        (tmp_path / "sub" / "deep" / "doc.md").write_text("test", encoding="utf-8")

        result = discover_sources(tmp_path)
        assert len(result.documents) == 1
        rel_path = result.documents[0].relative_path
        assert rel_path == "sub/deep/doc.md"
        assert "\\" not in rel_path
        assert not rel_path.startswith("/")

    # 3. Markdown discovery
    def test_markdown_discovery(self, tmp_path: Path):
        (tmp_path / "guide.md").write_text("# Guide", encoding="utf-8")
        result = discover_sources(tmp_path)
        assert len(result.documents) == 1
        assert result.documents[0].relative_path == "guide.md"
        assert result.documents[0].source_type == "documentation"

    # 4. MDX discovery
    def test_mdx_discovery(self, tmp_path: Path):
        (tmp_path / "component.mdx").write_text("# Component", encoding="utf-8")
        result = discover_sources(tmp_path)
        assert len(result.documents) == 1
        assert result.documents[0].relative_path == "component.mdx"
        assert result.documents[0].source_type == "documentation"

    # 5. RST discovery
    def test_rst_discovery(self, tmp_path: Path):
        (tmp_path / "index.rst").write_text("Title\n=====", encoding="utf-8")
        result = discover_sources(tmp_path)
        assert len(result.documents) == 1
        assert result.documents[0].relative_path == "index.rst"
        assert result.documents[0].source_type == "documentation"

    # 6. .git/ excluded
    def test_git_directory_excluded(self, tmp_path: Path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD.md").write_text("git head", encoding="utf-8")
        (git_dir / "config").write_text("config", encoding="utf-8")
        (tmp_path / "real.md").write_text("real", encoding="utf-8")

        result = discover_sources(tmp_path)
        paths = [d.relative_path for d in result.documents]
        assert paths == ["real.md"]
        assert not any(".git" in d.path for d in result.diagnostics)

    # 7. Non-document files ignored
    def test_non_document_files_ignored(self, tmp_path: Path):
        (tmp_path / "main.py").write_text("print(1)", encoding="utf-8")
        (tmp_path / "package.json").write_text("{}", encoding="utf-8")
        (tmp_path / "style.css").write_text("body {}", encoding="utf-8")
        (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (tmp_path / "doc.md").write_text("doc", encoding="utf-8")

        result = discover_sources(tmp_path)
        paths = [d.relative_path for d in result.documents]
        assert paths == ["doc.md"]
        # Non-document files should not produce noisy diagnostics
        assert len(result.diagnostics) == 0

    # 8. Binary input ignored/diagnosed appropriately
    def test_binary_input_diagnosed_appropriately(self, tmp_path: Path):
        (tmp_path / "binary.md").write_bytes(b"\xff\xfe\x00\x01\x80\x81\xfe")
        (tmp_path / "valid.md").write_text("valid text", encoding="utf-8")

        result = discover_sources(tmp_path)
        paths = [d.relative_path for d in result.documents]
        assert paths == ["valid.md"]

        diag = next((g for g in result.diagnostics if g.path == "binary.md"), None)
        assert diag is not None
        assert diag.kind == "undecodable_encoding"
        assert "UTF-8" in diag.message

    # 9. Symlinks not followed
    def test_symlinks_not_followed(self, tmp_path: Path):
        target_dir = tmp_path / "target_dir"
        target_dir.mkdir()
        (target_dir / "target_doc.md").write_text("target", encoding="utf-8")

        link_dir = tmp_path / "sym_link_dir"
        created = False
        try:
            link_dir.symlink_to(target_dir, target_is_directory=True)
            created = True
        except (OSError, NotImplementedError):
            try:
                import _winapi
                _winapi.CreateJunction(str(target_dir), str(link_dir))
                created = True
            except Exception:
                pass

        if not created:
            pytest.skip("Neither symlinks nor directory junctions could be created in this environment")

        result = discover_sources(tmp_path)
        # target_doc.md should only appear once (under target_dir, NOT under sym_link_dir)
        paths = [d.relative_path for d in result.documents]
        assert "target_dir/target_doc.md" in paths
        assert not any("sym_link_dir" in p for p in paths)

        diag = next((g for g in result.diagnostics if "sym_link_dir" in g.path), None)
        assert diag is not None
        assert diag.kind == "symlink_skipped"

    # 10. File byte hash is deterministic
    def test_file_byte_hash_is_deterministic(self, tmp_path: Path):
        content_bytes = b"Deterministic content\r\nLine 2\n"
        expected_hash = "sha256:" + hashlib.sha256(content_bytes).hexdigest().lower()

        (tmp_path / "doc.md").write_bytes(content_bytes)
        result = discover_sources(tmp_path)
        assert result.documents[0].content_hash == expected_hash

    # 11. Hash changes when source bytes change
    def test_hash_changes_when_source_bytes_change(self, tmp_path: Path):
        (tmp_path / "doc1.md").write_bytes(b"content A")
        (tmp_path / "doc2.md").write_bytes(b"content B")

        result = discover_sources(tmp_path)
        assert result.documents[0].content_hash != result.documents[1].content_hash

    # 12. Discovery does not mutate checkout
    def test_discovery_does_not_mutate_checkout(self, tmp_path: Path):
        file_path = tmp_path / "doc.md"
        file_path.write_text("immutable content", encoding="utf-8")

        stat_before = file_path.stat()
        content_before = file_path.read_bytes()

        discover_sources(tmp_path)

        stat_after = file_path.stat()
        content_after = file_path.read_bytes()

        assert content_after == content_before
        assert stat_after.st_mtime == stat_before.st_mtime
        assert stat_after.st_size == stat_before.st_size

    # 13. No .mneme/ state created
    def test_no_mneme_state_created(self, tmp_path: Path):
        (tmp_path / "doc.md").write_text("doc", encoding="utf-8")
        discover_sources(tmp_path)

        assert not (tmp_path / ".mneme").exists()

    # 14. Valid Mneme ADR receives structured ADR metadata
    def test_valid_mneme_adr_metadata(self, tmp_path: Path):
        adr_text = (
            "---\n"
            "id: ADR-001\n"
            "title: Use JSON Storage\n"
            "status: accepted\n"
            "priority: foundational\n"
            "date: 2026-01-15\n"
            "scope: storage.persistence\n"
            "supersedes: [ADR-000]\n"
            "---\n"
            "# Context\n"
            "We decide to use JSON.\n"
        )
        (tmp_path / "docs" / "adr").mkdir(parents=True)
        (tmp_path / "docs" / "adr" / "ADR-001.md").write_bytes(adr_text.encode("utf-8"))

        result = discover_sources(tmp_path)
        assert len(result.documents) == 1
        doc = result.documents[0]

        assert doc.source_type == "adr"
        assert doc.metadata["is_mneme_adr"] is True
        assert doc.metadata["adr_id"] == "ADR-001"
        assert doc.metadata["adr_title"] == "Use JSON Storage"
        assert doc.metadata["adr_status"] == "accepted"
        assert doc.metadata["adr_priority"] == "foundational"
        assert doc.metadata["adr_date"] == "2026-01-15"
        assert doc.metadata["adr_scope"] == "storage.persistence"
        assert doc.metadata["supersedes"] == ["ADR-000"]
        assert doc.metadata["byte_length"] == len(adr_text.encode("utf-8"))

    # 15. Proposed ADR is retained
    def test_proposed_adr_is_retained(self, tmp_path: Path):
        adr_text = (
            "---\n"
            "id: ADR-002\n"
            "title: Proposed Architecture\n"
            "status: proposed\n"
            "priority: normal\n"
            "date: 2026-02-01\n"
            "scope: api\n"
            "---\n"
            "Body\n"
        )
        (tmp_path / "ADR-002.md").write_text(adr_text, encoding="utf-8")

        result = discover_sources(tmp_path)
        assert len(result.documents) == 1
        assert result.documents[0].metadata["adr_status"] == "proposed"

    # 16. Superseded ADR is retained
    def test_superseded_adr_is_retained(self, tmp_path: Path):
        adr_text = (
            "---\n"
            "id: ADR-001\n"
            "title: Old Storage\n"
            "status: superseded\n"
            "priority: normal\n"
            "date: 2025-01-01\n"
            "scope: storage\n"
            "---\n"
            "Body\n"
        )
        (tmp_path / "ADR-001.md").write_text(adr_text, encoding="utf-8")

        result = discover_sources(tmp_path)
        assert len(result.documents) == 1
        assert result.documents[0].metadata["adr_status"] == "superseded"

    # 17. Deprecated ADR is retained
    def test_deprecated_adr_is_retained(self, tmp_path: Path):
        adr_text = (
            "---\n"
            "id: ADR-003\n"
            "title: Deprecated Service\n"
            "status: deprecated\n"
            "priority: exception\n"
            "date: 2025-06-01\n"
            "scope: service\n"
            "---\n"
            "Body\n"
        )
        (tmp_path / "ADR-003.md").write_text(adr_text, encoding="utf-8")

        result = discover_sources(tmp_path)
        assert len(result.documents) == 1
        assert result.documents[0].metadata["adr_status"] == "deprecated"

    # 18. ADR precedence is not used to discard documents
    def test_adr_precedence_not_used_to_discard(self, tmp_path: Path):
        # Two accepted ADRs sharing the same scope (under resolve_precedence, only one wins)
        adr1 = (
            "---\n"
            "id: ADR-001\n"
            "title: Scope Storage V1\n"
            "status: accepted\n"
            "priority: normal\n"
            "date: 2026-01-01\n"
            "scope: storage\n"
            "---\n"
            "V1\n"
        )
        adr2 = (
            "---\n"
            "id: ADR-002\n"
            "title: Scope Storage V2\n"
            "status: accepted\n"
            "priority: normal\n"
            "date: 2026-02-01\n"
            "scope: storage\n"
            "---\n"
            "V2\n"
        )
        (tmp_path / "ADR-001.md").write_text(adr1, encoding="utf-8")
        (tmp_path / "ADR-002.md").write_text(adr2, encoding="utf-8")

        result = discover_sources(tmp_path)
        # BOTH must be retained in discovery
        paths = [d.relative_path for d in result.documents]
        assert "ADR-001.md" in paths
        assert "ADR-002.md" in paths

    # 19. Malformed/non-Mneme ADR-like document remains available as research evidence
    def test_malformed_non_mneme_adr_retained(self, tmp_path: Path):
        nygard_adr = (
            "# 1. Record architecture decisions\n\n"
            "Date: 2026-01-01\n\n"
            "## Status\n\n"
            "Accepted\n\n"
            "## Context\n\n"
            "We need to record decisions.\n"
        )
        (tmp_path / "docs" / "adr").mkdir(parents=True)
        (tmp_path / "docs" / "adr" / "ADR-001-record-decisions.md").write_bytes(
            nygard_adr.encode("utf-8")
        )

        result = discover_sources(tmp_path)
        # Document is retained as research evidence
        assert len(result.documents) == 1
        doc = result.documents[0]
        assert doc.relative_path == "docs/adr/ADR-001-record-decisions.md"
        assert doc.source_type == "adr"
        assert doc.metadata["is_mneme_adr"] is False
        assert doc.content == nygard_adr

    # 20. Malformed structured ADR parsing is observable via diagnostic/metadata
    def test_malformed_adr_observable_via_diagnostic_and_metadata(self, tmp_path: Path):
        bad_frontmatter_adr = (
            "---\n"
            "id: NOT-AN-ADR-ID\n"
            "status: draft\n"  # Invalid status in Mneme schema
            "---\n"
            "Content\n"
        )
        (tmp_path / "ADR-999.md").write_text(bad_frontmatter_adr, encoding="utf-8")

        result = discover_sources(tmp_path)
        assert len(result.documents) == 1
        doc = result.documents[0]
        assert doc.metadata["is_mneme_adr"] is False
        assert "adr_parse_error" in doc.metadata

        diag = next((g for g in result.diagnostics if g.path == "ADR-999.md"), None)
        assert diag is not None
        assert diag.kind == "adr_parse_failure"

    # 21. UTF-8 content preserved exactly
    def test_utf8_content_preserved_exactly(self, tmp_path: Path):
        unicode_content = (
            "# Architectural Invariants — αβγδε\n\n"
            "Enforcement: «strict» — “zero-tolerance”\n"
            "Unicode test: 🚀 🤖 ⚡\n"
            "Chinese: 架构决策记录\n"
        )
        (tmp_path / "architecture.md").write_bytes(unicode_content.encode("utf-8"))

        result = discover_sources(tmp_path)
        assert len(result.documents) == 1
        assert result.documents[0].content == unicode_content

    # 22. Undecodable selected document is not silently replacement-decoded
    def test_undecodable_document_not_replacement_decoded(self, tmp_path: Path):
        invalid_bytes = b"# Doc\n" + b"\xff\xfe" + b"\nEnd"
        (tmp_path / "broken.md").write_bytes(invalid_bytes)

        result = discover_sources(tmp_path)
        # Must not appear in documents with replacement character
        assert not any(d.relative_path == "broken.md" for d in result.documents)
        for doc in result.documents:
            assert "\ufffd" not in doc.content

        diag = next((g for g in result.diagnostics if g.path == "broken.md"), None)
        assert diag is not None
        assert diag.kind == "undecodable_encoding"

    # 23. Oversized document behavior is deterministic
    def test_oversized_document_behavior(self, tmp_path: Path):
        oversized_content = "A" * 1500
        (tmp_path / "huge.md").write_text(oversized_content, encoding="utf-8")
        (tmp_path / "small.md").write_text("small", encoding="utf-8")

        result = discover_sources(tmp_path, max_file_size_bytes=1000)
        paths = [d.relative_path for d in result.documents]
        assert paths == ["small.md"]

        diag = next((g for g in result.diagnostics if g.path == "huge.md"), None)
        assert diag is not None
        assert diag.kind == "file_oversized"
        assert "1500 bytes" in diag.message

    # 24. Repeated discovery over identical checkout produces equivalent results
    def test_repeated_discovery_produces_equivalent_results(self, tmp_path: Path):
        (tmp_path / "doc1.md").write_text("one", encoding="utf-8")
        (tmp_path / "doc2.rst").write_text("two", encoding="utf-8")

        res1 = discover_sources(tmp_path)
        res2 = discover_sources(tmp_path)

        assert res1.documents == res2.documents
        assert res1.diagnostics == res2.diagnostics

    # 25. No canonical authority writer imports
    def test_no_canonical_authority_modules_imported(self):
        import mneme.open_architecture.discovery as discovery_module

        module_vars = vars(discovery_module)
        forbidden = [
            "DecisionAuthorityService",
            "DecisionProposalStore",
            "MemoryStore",
            "JsonFileDecisionProposalStore",
            "adrs_to_decisions",
            "resolve_precedence",
        ]
        for name in forbidden:
            assert name not in module_vars, f"Forbidden authority component '{name}' found in discovery module"

    # 26. No Decision projection
    def test_no_decision_projection(self):
        import mneme.open_architecture.discovery as discovery_module

        module_vars = vars(discovery_module)
        assert "Decision" not in module_vars
        assert "Rule" not in module_vars

    # 27. No repository code execution
    def test_no_repository_code_execution(self, tmp_path: Path):
        marker_file = tmp_path / "pwned.txt"
        deceptive_code = f"import pathlib; pathlib.Path('{marker_file.as_posix()}').write_text('pwned')\n"

        (tmp_path / "setup.py").write_text(deceptive_code, encoding="utf-8")
        (tmp_path / "conftest.py").write_text(deceptive_code, encoding="utf-8")
        (tmp_path / "doc.md").write_text("doc", encoding="utf-8")

        discover_sources(tmp_path)

        assert not marker_file.exists()


# ── Integration with O1A2.1 Materialization ────────────────────────────────────


class TestDiscoveryMaterializationIntegration:
    """End-to-end integration test: local git repo -> materialize_repository -> discover_sources."""

    def test_materialization_and_discovery_pipeline(self, tmp_path: Path):
        source_repo = tmp_path / "remote_git_repo"
        source_repo.mkdir()

        # Initialize git repo with ADRs and docs
        subprocess.run(["git", "init", "-q"], cwd=str(source_repo), check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/mbeacom/adrkit.git"],
            cwd=str(source_repo),
            check=True,
        )

        adr_dir = source_repo / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-001.md").write_text(
            "---\n"
            "id: ADR-001\n"
            "title: Use Markdown for ADRs\n"
            "status: accepted\n"
            "priority: foundational\n"
            "date: 2026-01-01\n"
            "scope: docs\n"
            "---\n"
            "# Context\nUse markdown.\n",
            encoding="utf-8",
        )
        (source_repo / "README.md").write_text("# Adrkit\nTooling for ADRs.", encoding="utf-8")
        (source_repo / "main.py").write_text("import sys\n", encoding="utf-8")

        subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=t", "add", "."], cwd=str(source_repo), check=True)
        subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-q", "-m", "initial commit"], cwd=str(source_repo), check=True)
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(source_repo), capture_output=True, text=True, check=True).stdout.strip()

        config = RepositoryConfig(
            id="adrkit",
            github="mbeacom/adrkit",
            commit_sha=sha,
            primary_test="test",
            validation_status="unreviewed",
        )

        with materialize_repository(config, clone_source=source_repo) as checkout:
            result = discover_sources(checkout)

            paths = [d.relative_path for d in result.documents]
            assert "README.md" in paths
            assert "docs/adr/ADR-001.md" in paths
            assert "main.py" not in paths

            adr_doc = next(d for d in result.documents if d.relative_path == "docs/adr/ADR-001.md")
            assert adr_doc.source_type == "adr"
            assert adr_doc.metadata["is_mneme_adr"] is True
            assert adr_doc.metadata["adr_id"] == "ADR-001"
            assert adr_doc.metadata["adr_status"] == "accepted"

            readme_doc = next(d for d in result.documents if d.relative_path == "README.md")
            assert readme_doc.source_type == "documentation"
            assert readme_doc.metadata["is_mneme_adr"] is False

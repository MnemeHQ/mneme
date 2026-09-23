"""
tests.open_architecture.test_candidates — Tests for candidate evidence extraction and identity.

Covers items 1-13 of O1A2.3 required coverage:
- Candidate identity determinism and sensitivity
- LineSpan validation and source line extraction
- Boundary checks
"""

from __future__ import annotations

import pytest

from mneme.open_architecture.candidates import (
    ExtractedCandidate,
    HeuristicExtractor,
    LineSpan,
    build_decision_candidate,
)
from mneme.open_architecture.discovery import DiscoveredSourceDocument


# ── LineSpan Model Tests ───────────────────────────────────────────────────────


class TestLineSpan:
    def test_valid_line_span(self):
        span = LineSpan(1, 10)
        assert span.start_line == 1
        assert span.end_line == 10
        assert span.line_count() == 10
        assert span.to_string() == "L1-L10"

    def test_single_line_span(self):
        span = LineSpan(42, 42)
        assert span.start_line == 42
        assert span.end_line == 42
        assert span.line_count() == 1
        assert span.to_string() == "L42"

    # 10. start line zero rejected
    def test_start_line_zero_rejected(self):
        with pytest.raises(ValueError, match="start_line must be >= 1"):
            LineSpan(0, 10)

    def test_start_line_negative_rejected(self):
        with pytest.raises(ValueError, match="start_line must be >= 1"):
            LineSpan(-1, 10)

    # 11. end before start rejected
    def test_end_before_start_rejected(self):
        with pytest.raises(ValueError, match="must be >= start_line"):
            LineSpan(10, 5)

    def test_parse_from_string_range(self):
        span = LineSpan.from_string("L42-L48")
        assert span.start_line == 42
        assert span.end_line == 48

    def test_parse_from_string_single(self):
        span = LineSpan.from_string("L42")
        assert span.start_line == 42
        assert span.end_line == 42

    def test_parse_from_string_invalid(self):
        with pytest.raises(ValueError, match="must start with 'L'"):
            LineSpan.from_string("42-48")

    def test_contains_and_overlaps(self):
        s1 = LineSpan(1, 10)
        s2 = LineSpan(3, 7)
        s3 = LineSpan(8, 15)
        s4 = LineSpan(20, 25)

        assert s1.contains(s2)
        assert not s2.contains(s1)
        assert s1.overlaps(s3)
        assert not s1.overlaps(s4)


# ── ExtractedCandidate Identity Tests ──────────────────────────────────────────


class TestCandidateIdentity:
    def _make_candidate(
        self,
        *,
        repo_id: str = "mbeacom/adrkit",
        sha: str = "a" * 40,
        path: str = "docs/adr/ADR-001.md",
        content_hash: str = "sha256:" + "1" * 64,
        start_line: int = 10,
        end_line: int = 15,
        raw_statement: str = "Use JSON for storage.",
        confidence: float = 0.8,
        metadata: dict | None = None,
    ) -> ExtractedCandidate:
        span = LineSpan(start_line, end_line)
        identity = {
            "repository_identifier": repo_id,
            "repository_commit_sha": sha.lower(),
            "source_path": path,
            "source_content_hash": content_hash,
            "source_location": span.to_string(),
            "raw_statement": raw_statement,
        }
        cand_id = ExtractedCandidate.generate_candidate_id(identity)
        return ExtractedCandidate(
            candidate_id=cand_id,
            repository_identifier=repo_id,
            repository_commit_sha=sha.lower(),
            source_path=path,
            source_content_hash=content_hash,
            source_location=span,
            raw_statement=raw_statement,
            discovery_confidence=confidence,
            discovery_metadata=metadata or {},
        )

    # 1. same source span → same candidate ID
    def test_same_source_span_produces_same_candidate_id(self):
        c1 = self._make_candidate()
        c2 = self._make_candidate()
        assert c1.candidate_id == c2.candidate_id
        assert c1.candidate_id.startswith("cand-")
        assert len(c1.candidate_id) == 37  # 'cand-' + 32 hex

    # 2. different repository SHA → different candidate ID
    def test_different_commit_sha_produces_different_id(self):
        c1 = self._make_candidate(sha="a" * 40)
        c2 = self._make_candidate(sha="b" * 40)
        assert c1.candidate_id != c2.candidate_id

    # 3. different source path → different candidate ID
    def test_different_source_path_produces_different_id(self):
        c1 = self._make_candidate(path="docs/adr/ADR-001.md")
        c2 = self._make_candidate(path="docs/adr/ADR-002.md")
        assert c1.candidate_id != c2.candidate_id

    # 4. different line span → different candidate ID
    def test_different_line_span_produces_different_id(self):
        c1 = self._make_candidate(start_line=10, end_line=15)
        c2 = self._make_candidate(start_line=10, end_line=16)
        assert c1.candidate_id != c2.candidate_id

    # 5. different raw evidence → different candidate ID
    def test_different_raw_statement_produces_different_id(self):
        c1 = self._make_candidate(raw_statement="Use JSON for storage.")
        c2 = self._make_candidate(raw_statement="Use SQLite for storage.")
        assert c1.candidate_id != c2.candidate_id

    # 6. timestamps do not affect identity
    def test_timestamps_do_not_affect_identity(self):
        # Candidates created at different times with same source evidence
        # have identical candidate_id because timestamps are not in identity fields
        c1 = self._make_candidate(metadata={"time": 100})
        c2 = self._make_candidate(metadata={"time": 200})
        assert c1.candidate_id == c2.candidate_id

    # 7. classifier backend does not affect identity
    def test_classifier_backend_does_not_affect_identity(self):
        c1 = self._make_candidate(metadata={"backend": "anthropic"})
        c2 = self._make_candidate(metadata={"backend": "openai"})
        assert c1.candidate_id == c2.candidate_id

    # 8. model output does not affect identity
    def test_model_output_does_not_affect_identity(self):
        c1 = self._make_candidate(metadata={"predicted_class": "prescriptive"})
        c2 = self._make_candidate(metadata={"predicted_class": "advisory"})
        assert c1.candidate_id == c2.candidate_id

    def test_confidence_does_not_affect_identity(self):
        c1 = self._make_candidate(confidence=0.5)
        c2 = self._make_candidate(confidence=0.9)
        assert c1.candidate_id == c2.candidate_id


# ── Evidence Span & Document Source Tests ──────────────────────────────────────


class TestEvidenceSpans:
    def _make_document(
        self,
        content: str = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n",
        path: str = "docs/test.md",
    ) -> DiscoveredSourceDocument:
        import hashlib
        raw = content.encode("utf-8")
        h = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        return DiscoveredSourceDocument(
            relative_path=path,
            source_type="documentation",
            content_hash=h,
            content=content,
            metadata={"byte_length": len(raw)},
        )

    # 9. valid line range accepted
    def test_valid_line_range_accepted(self):
        doc = self._make_document()
        span = LineSpan(2, 4)
        cand = ExtractedCandidate.from_source_document(
            doc=doc,
            repo_commit_sha="a" * 40,
            line_span=span,
        )
        assert cand.source_location == span
        assert cand.raw_statement == "Line 2\nLine 3\nLine 4"

    # 12. out-of-range span rejected
    def test_out_of_range_span_rejected_end_too_large(self):
        doc = self._make_document(content="Line 1\nLine 2\n")
        span = LineSpan(1, 5)  # Doc has only 2 lines
        with pytest.raises(ValueError, match="out of bounds"):
            ExtractedCandidate.from_source_document(
                doc=doc,
                repo_commit_sha="a" * 40,
                line_span=span,
            )

    # 13. extracted raw evidence matches source lines deterministically
    def test_extracted_raw_evidence_matches_source_lines(self):
        content = "\n".join(f"Line number {i}" for i in range(1, 21))
        doc = self._make_document(content=content)
        span = LineSpan(5, 8)
        cand = ExtractedCandidate.from_source_document(
            doc=doc,
            repo_commit_sha="a" * 40,
            line_span=span,
        )

        expected = "Line number 5\nLine number 6\nLine number 7\nLine number 8"
        assert cand.raw_statement == expected
        # Re-extracting from doc matches exactly
        assert cand.extract_source_lines(doc) == expected

    def test_empty_raw_statement_rejected(self):
        doc = self._make_document(content="Line 1\n\n\nLine 4\n")
        span = LineSpan(2, 3)  # Lines 2 and 3 are empty
        with pytest.raises(ValueError, match="empty or whitespace-only"):
            ExtractedCandidate.from_source_document(
                doc=doc,
                repo_commit_sha="a" * 40,
                line_span=span,
            )


# ── Extractor Protocol & Heuristic Implementation Tests ────────────────────────


class TestHeuristicExtractor:
    def test_heuristic_extractor_extracts_decisions(self):
        content = (
            "# Introduction\n"
            "This is general intro text.\n\n"
            "# Storage Decision\n"
            "We decided to adopt JSON as the storage standard.\n"
            "PostgreSQL is prohibited for this service.\n\n"
            "# Architecture\n"
            "General architectural overview.\n"
        )
        import hashlib
        raw = content.encode("utf-8")
        doc = DiscoveredSourceDocument(
            relative_path="docs/architecture.md",
            source_type="documentation",
            content_hash=f"sha256:{hashlib.sha256(raw).hexdigest()}",
            content=content,
            metadata={"byte_length": len(raw)},
        )

        extractor = HeuristicExtractor(min_lines=2, max_lines=20)
        candidates = extractor.extract(doc, repo_commit_sha="a" * 40)

        assert len(candidates) >= 1
        storage_cands = [c for c in candidates if "json" in c.raw_statement.lower()]
        assert len(storage_cands) >= 1
        assert storage_cands[0].source_path == "docs/architecture.md"

    def test_empty_document_produces_no_candidates(self):
        doc = DiscoveredSourceDocument(
            relative_path="empty.md",
            source_type="documentation",
            content_hash="sha256:" + "0" * 64,
            content="",
            metadata={},
        )
        extractor = HeuristicExtractor()
        assert extractor.extract(doc, repo_commit_sha="a" * 40) == []


# ── Composition Helper Test ───────────────────────────────────────────────────


class TestBuildDecisionCandidate:
    def test_composition_helper_produces_valid_decision_candidate(self):
        span = LineSpan(1, 2)
        identity = {
            "repository_identifier": "mbeacom/adrkit",
            "repository_commit_sha": "a" * 40,
            "source_path": "docs/adr/ADR-001.md",
            "source_content_hash": "sha256:" + "1" * 64,
            "source_location": span.to_string(),
            "raw_statement": "We decide to use JSON.",
        }
        cand_id = ExtractedCandidate.generate_candidate_id(identity)
        extracted = ExtractedCandidate(
            candidate_id=cand_id,
            repository_identifier="mbeacom/adrkit",
            repository_commit_sha="a" * 40,
            source_path="docs/adr/ADR-001.md",
            source_content_hash="sha256:" + "1" * 64,
            source_location=span,
            raw_statement="We decide to use JSON.",
            discovery_confidence=0.9,
        )

        decision_candidate = build_decision_candidate(
            extracted=extracted,
            classification="prescriptive",
            decision_domains=("persistence",),
            decision_purposes=("constrain",),
            authority_status="explicitly_accepted",
            authority_evidence="ADR-001 accepted frontmatter",
            lifecycle_status="active",
            enforcement_potential="deterministic_rule",
            confidence=0.95,
        )

        assert decision_candidate.candidate_id == cand_id
        assert decision_candidate.classification == "prescriptive"
        assert decision_candidate.authority_status == "explicitly_accepted"
        assert decision_candidate.decision_domains == ("persistence",)
        assert decision_candidate.decision_purposes == ("constrain",)

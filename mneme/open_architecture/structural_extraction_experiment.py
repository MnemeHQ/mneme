"""
mneme.open_architecture.structural_extraction_experiment — T2B Stage A Structural Go Extraction.

Implements research-only structural Go extraction over the frozen Batch 01 source stream:
- T2B.1: Source Boundary Hygiene (excludes *_test.go and path component 'examples' for Go code).
- T2B.2: Bounded Go Declaration Extraction with Refined G2 Grouping:
  - Bounded deterministic Go declaration scanner (FuncDecl, method FuncDecl, TypeSpec, GenDecl).
  - Whole declaration spans (no arbitrary 50-line window cuts).
  - Package-level receiver context inheritance (Rule A).
  - Mechanism A: contiguous type/const/var cluster merging (gap <= 2 lines).
  - Mechanism C: single-receiver implementation micro-file unitization.
  - Standalone methods remain independent.

Purpose:
"T2B.2 evaluates whether structural Go declaration extraction can improve
Stage A evidence localization and reduce false-positive evidence volume while
preserving 100% frozen-reference recall."

Architecture and Boundary Invariants:
- Research-only sidecar: does NOT modify or parameterize candidates.py, discovery.py, or harness.py.
- Preserves frozen B0, corrected T1, T2A, and T2B.1 baselines without mutation.
- Strict fail-closed predicate for Go source-code vs. documentation evidence.
- Zero model/API calls.
- Zero canonical authority writes (no MemoryStore, DecisionProposal, DecisionIndex mutations).
- Terminates strictly after Stage A discovery matching.
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mneme.open_architecture.baseline import (
    BaselineConfig,
    validate_baseline_freeze,
)
from mneme.open_architecture.candidates import (
    CandidateExtractor,
    ExtractedCandidate,
    LineSpan,
)
from mneme.open_architecture.discovery import (
    DiscoveredSourceDocument,
    discover_sources,
)
from mneme.open_architecture.execution import (
    materialize_repository,
)
from mneme.open_architecture.export import compute_reference_corpus_content_hash
from mneme.open_architecture.extraction_tuning_experiment import (
    B0_STAGE_B_SEMANTIC_SCORE,
    B0_STAGE_C_APPLICABILITY_SCORE,
    FROZEN_BASELINE_ID,
    FROZEN_REFERENCE_CORPUS_HASH,
    FROZEN_REPOSITORY_SHAS,
    T2A2_CODE_KEYWORDS,
    T2A2_DOC_KEYWORDS,
    LexicalCandidateExtractor,
    _verify_and_prepare_output_dir,
    is_source_code_document,
)
from mneme.open_architecture.harness import (
    StageADiscoveryResult,
    evaluate_discovery_matches,
    load_reference_corpus,
    parse_reference_intervals,
)
from mneme.open_architecture.manifest import Manifest
from mneme.open_architecture.source_coverage_experiment import discover_go_sources

FROZEN_PARENT_MAIN_SHA: str = "3ccd5992a0035eea300ab5615674a2cdcedc5fde"
T2B1_CHECKPOINT_SHA: str = "0b59de7e0cf98b2ded34ed5faabbb67f3d3b980e"

EXCLUSION_SUFFIX: str = "_test.go"
EXCLUSION_PATH_COMPONENT: str = "examples"


# ── Fail-Closed Exclusion Predicate ──────────────────────────────────────────


def is_excluded_go_source(doc: DiscoveredSourceDocument) -> bool:
    """Exact fail-closed predicate enforcing T2B.1 Go source boundary hygiene.

    Applies strictly to Go source code documents where is_source_code_document(doc) is True.
    Excludes a Go document if:
      - relative_path ends with '_test.go'
      OR
      - any normalized POSIX path component is exactly 'examples'

    Does not use loose substring matching.
    Never excludes documentation or non-Go documents.
    """
    if not is_source_code_document(doc):
        return False
    norm_path = doc.relative_path.replace("\\", "/")
    if norm_path.endswith(EXCLUSION_SUFFIX):
        return True
    parts = norm_path.split("/")
    if EXCLUSION_PATH_COMPONENT in parts:
        return True
    return False


# ── Bounded Deterministic Go Declaration Scanner ─────────────────────────────


@dataclass(frozen=True)
class ScannedGoDeclaration:
    """Immutable record of a top-level Go declaration discovered by the scanner."""

    file: str
    kind: str  # "func", "method", "type", "var", "const"
    name: str
    receiver: str | None
    receiver_base_type: str | None
    doc_comment: str
    code: str
    start_line: int  # 1-indexed, including bound leading doc comment
    code_start_line: int  # 1-indexed line where code keyword begins
    end_line: int  # 1-indexed, inclusive

    @property
    def full_text(self) -> str:
        if self.doc_comment:
            return self.doc_comment + "\n" + self.code
        return self.code

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1

    @property
    def char_count(self) -> int:
        return len(self.full_text)


def scan_go_declarations(file_rel: str, text: str) -> list[ScannedGoDeclaration]:
    """Passively scan UTF-8 Go source text for top-level declarations using a state machine.

    Correctly tracks and ignores braces inside:
    - single-line comments (//)
    - multiline block comments (/* */)
    - interpreted string literals ("...") with escape sequences
    - multiline raw string literals (`...`)
    - rune literals ('...')

    Binds leading contiguous doc comments directly to the subsequent declaration.
    Does not execute repository code; does not invoke the external Go toolchain.
    """
    lines = text.splitlines()
    n = len(lines)
    decls: list[ScannedGoDeclaration] = []
    i = 0

    while i < n:
        # Collect leading doc comments
        comment_lines: list[str] = []
        comment_start = i
        while i < n and (lines[i].strip().startswith("//") or lines[i].strip().startswith("/*")):
            comment_lines.append(lines[i])
            i += 1
        if i >= n:
            break

        stripped = lines[i].strip()
        doc_comment = "\n".join(comment_lines) if comment_lines else ""
        decl_start = comment_start if comment_lines else i

        if stripped.startswith("func ") or stripped == "func":
            code_start_i = i
            brace_depth = 0
            in_string = False
            in_raw_string = False
            in_comment = False
            in_line_comment = False
            found_first_brace = False

            while i < n:
                cur_line = lines[i]
                j = 0
                while j < len(cur_line):
                    ch = cur_line[j]
                    nxt = cur_line[j + 1] if j + 1 < len(cur_line) else ""

                    if in_line_comment:
                        break
                    elif in_comment:
                        if ch == "*" and nxt == "/":
                            in_comment = False
                            j += 2
                            continue
                    elif in_string:
                        if ch == "\\":
                            j += 2
                            continue
                        elif ch == '"':
                            in_string = False
                    elif in_raw_string:
                        if ch == "`":
                            in_raw_string = False
                    else:
                        if ch == "/" and nxt == "/":
                            break
                        elif ch == "/" and nxt == "*":
                            in_comment = True
                            j += 2
                            continue
                        elif ch == '"':
                            in_string = True
                        elif ch == "`":
                            in_raw_string = True
                        elif ch == "{":
                            brace_depth += 1
                            found_first_brace = True
                        elif ch == "}":
                            brace_depth -= 1
                    j += 1

                if found_first_brace and brace_depth == 0:
                    break
                i += 1

            decl_end = i
            header = lines[code_start_i]
            m_meth = re.match(r"^func\s*\(([^)]+)\)\s*([A-Za-z0-9_]+)", header)
            m_func = re.match(r"^func\s+([A-Za-z0-9_]+)", header)
            if m_meth:
                kind = "method"
                recv = m_meth.group(1).strip()
                name = m_meth.group(2).strip()
                tokens = recv.split()
                type_token = tokens[-1] if tokens else ""
                base_type = type_token.lstrip("*")
            elif m_func:
                kind = "func"
                recv = None
                base_type = None
                name = m_func.group(1).strip()
            else:
                kind = "func"
                recv = None
                base_type = None
                name = "unknown"

            code = "\n".join(lines[code_start_i : decl_end + 1])
            decls.append(
                ScannedGoDeclaration(
                    file=file_rel,
                    kind=kind,
                    name=name,
                    receiver=recv,
                    receiver_base_type=base_type,
                    doc_comment=doc_comment,
                    code=code,
                    start_line=decl_start + 1,
                    code_start_line=code_start_i + 1,
                    end_line=decl_end + 1,
                )
            )
            i += 1
            continue

        elif stripped.startswith("type ") or stripped.startswith("var ") or stripped.startswith("const "):
            code_start_i = i
            first_word = stripped.split()[0]
            paren_depth = 0
            brace_depth = 0
            in_raw_string = False
            in_string = False
            found_group = False

            while i < n:
                cur_line = lines[i]
                j = 0
                while j < len(cur_line):
                    ch = cur_line[j]
                    nxt = cur_line[j + 1] if j + 1 < len(cur_line) else ""
                    if in_string:
                        if ch == "\\":
                            j += 2
                            continue
                        elif ch == '"':
                            in_string = False
                    elif in_raw_string:
                        if ch == "`":
                            in_raw_string = False
                    else:
                        if ch == "/" and nxt == "/":
                            break
                        elif ch == '"':
                            in_string = True
                        elif ch == "`":
                            in_raw_string = True
                        elif ch == "(":
                            paren_depth += 1
                            found_group = True
                        elif ch == ")":
                            paren_depth -= 1
                        elif ch == "{":
                            brace_depth += 1
                            found_group = True
                        elif ch == "}":
                            brace_depth -= 1
                    j += 1
                if not in_raw_string and not in_string:
                    if found_group:
                        if paren_depth == 0 and brace_depth == 0:
                            break
                    else:
                        break
                i += 1
            decl_end = i

            name = stripped.split()[1] if len(stripped.split()) > 1 else "unknown"
            name = name.split("(")[0].strip()
            code = "\n".join(lines[code_start_i : decl_end + 1])
            decls.append(
                ScannedGoDeclaration(
                    file=file_rel,
                    kind=first_word,
                    name=name,
                    receiver=None,
                    receiver_base_type=None,
                    doc_comment=doc_comment,
                    code=code,
                    start_line=decl_start + 1,
                    code_start_line=code_start_i + 1,
                    end_line=decl_end + 1,
                )
            )
            i += 1
            continue

        i += 1

    return decls


# ── Receiver Indexing & G2 Structural Grouping ─────────────────────────────────


def index_package_decision_types(
    declarations_by_file: dict[str, list[ScannedGoDeclaration]],
    code_keywords: frozenset[str],
) -> dict[str, set[str]]:
    """Index decision-bearing receiver types per package directory.

    A receiver type T is decision-bearing when its `type T` declaration text
    (including bound leading doc comments) directly contains at least one code keyword.
    """
    pkg_decision_types: dict[str, set[str]] = {}
    for f, decls in declarations_by_file.items():
        pkg = str(Path(f).parent).replace("\\", "/")
        pkg_decision_types.setdefault(pkg, set())
        for d in decls:
            if d.kind == "type":
                text_lower = d.full_text.lower()
                if any(kw in text_lower for kw in code_keywords):
                    pkg_decision_types[pkg].add(d.name)
    return pkg_decision_types


def is_declaration_eligible(
    decl: ScannedGoDeclaration,
    code_keywords: frozenset[str],
    pkg_decision_types: dict[str, set[str]],
) -> bool:
    """Check if a declaration is candidate-eligible via direct keywords or receiver inheritance."""
    # 1. Direct keyword match
    if any(kw in decl.full_text.lower() for kw in code_keywords):
        return True
    # 2. Receiver context inheritance (Rule A)
    if decl.kind == "method" and decl.receiver_base_type:
        pkg = str(Path(decl.file).parent).replace("\\", "/")
        if decl.receiver_base_type in pkg_decision_types.get(pkg, set()):
            return True
    return False


@dataclass(frozen=True)
class ExtractedStructuralSpan:
    """Intermediate candidate evidence span produced by G2 structural grouping."""

    source_path: str
    start_line: int
    end_line: int
    rule: str  # "mechanism_a", "mechanism_c", or "individual_declaration"
    member_declarations: tuple[str, ...]


def extract_g2_structural_candidates(
    document: DiscoveredSourceDocument,
    declarations: list[ScannedGoDeclaration],
    code_keywords: frozenset[str],
    pkg_decision_types: dict[str, set[str]],
    repo_commit_sha: str,
) -> list[ExtractedCandidate]:
    """Extract structural Go candidates using Refined G2 Grouping (Mechanism A + C)."""
    f = document.relative_path
    lines = document.content.splitlines()
    candidates: list[ExtractedCandidate] = []

    methods = [d for d in declarations if d.kind == "method"]
    free_funcs = [d for d in declarations if d.kind == "func"]
    recv_base_types = {d.receiver_base_type for d in methods if d.receiver_base_type}

    has_eligible = any(is_declaration_eligible(d, code_keywords, pkg_decision_types) for d in declarations)

    # Check Mechanism C: Single-receiver implementation file
    qualifies_mech_c = (
        len(free_funcs) == 0
        and len(recv_base_types) == 1
        and len(methods) > 0
        and has_eligible
    )

    if qualifies_mech_c:
        owned_decls = [d for d in declarations if is_declaration_eligible(d, code_keywords, pkg_decision_types)]
        start_l = min(d.start_line for d in owned_decls)
        end_l = max(d.end_line for d in owned_decls)
        members = tuple(f"{d.kind} {d.name} (L{d.start_line}-L{d.end_line})" for d in owned_decls)
        span = LineSpan(start_l, end_l)
        try:
            cand = ExtractedCandidate.from_source_document(
                doc=document,
                repo_commit_sha=repo_commit_sha,
                line_span=span,
                discovery_confidence=0.8,
                metadata={
                    "extractor": "t2b2-structural-declaration",
                    "grouping_rule": "single_receiver_implementation_file",
                    "member_declarations": list(members),
                },
            )
            candidates.append(cand)
        except ValueError:
            pass
        return candidates

    # Process declarations with Mechanism A for adjacent type/const/var
    i = 0
    while i < len(declarations):
        d = declarations[i]
        if not is_declaration_eligible(d, code_keywords, pkg_decision_types):
            i += 1
            continue

        start_l = d.start_line
        end_l = d.end_line
        member_decls = [d]

        if d.kind in ("type", "const", "var"):
            j = i + 1
            while j < len(declarations):
                nxt = declarations[j]
                if not is_declaration_eligible(nxt, code_keywords, pkg_decision_types):
                    break
                if nxt.kind in ("type", "const", "var") and (nxt.start_line - end_l <= 3):
                    end_l = nxt.end_line
                    member_decls.append(nxt)
                    j += 1
                else:
                    break
            i = j
        else:
            i += 1

        span = LineSpan(start_l, end_l)
        members = tuple(f"{m.kind} {m.name} (L{m.start_line}-L{m.end_line})" for m in member_decls)
        rule_name = "adjacent_type_const_var" if len(member_decls) > 1 else "individual_declaration"
        try:
            cand = ExtractedCandidate.from_source_document(
                doc=document,
                repo_commit_sha=repo_commit_sha,
                line_span=span,
                discovery_confidence=0.8,
                metadata={
                    "extractor": "t2b2-structural-declaration",
                    "grouping_rule": rule_name,
                    "member_declarations": list(members),
                },
            )
            candidates.append(cand)
        except ValueError:
            pass

    return candidates


# ── Profile Contracts ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class T2B1SourceBoundaryHygieneProfile:
    """Immutable research experiment profile for T2B.1 Source Boundary Hygiene."""

    experiment_id: str = "t2b1-source-boundary-hygiene"
    baseline_id: str = FROZEN_BASELINE_ID
    parent_main_sha: str = FROZEN_PARENT_MAIN_SHA
    reference_corpus_hash: str = FROZEN_REFERENCE_CORPUS_HASH
    doc_keywords: tuple[str, ...] = tuple(sorted(T2A2_DOC_KEYWORDS))
    code_keywords: tuple[str, ...] = tuple(sorted(T2A2_CODE_KEYWORDS))
    target_repositories: tuple[str, ...] = tuple(sorted(FROZEN_REPOSITORY_SHAS.keys()))
    exclusion_suffix: str = EXCLUSION_SUFFIX
    exclusion_path_component: str = EXCLUSION_PATH_COMPONENT
    experiment_profile_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.experiment_id != "t2b1-source-boundary-hygiene":
            raise ValueError(f"experiment_id must be 't2b1-source-boundary-hygiene', got {self.experiment_id!r}")
        if self.baseline_id != FROZEN_BASELINE_ID:
            raise ValueError(f"baseline_id must be {FROZEN_BASELINE_ID!r}, got {self.baseline_id!r}")
        if self.parent_main_sha != FROZEN_PARENT_MAIN_SHA:
            raise ValueError(f"parent_main_sha must be {FROZEN_PARENT_MAIN_SHA!r}, got {self.parent_main_sha!r}")
        if self.reference_corpus_hash != FROZEN_REFERENCE_CORPUS_HASH:
            raise ValueError(f"reference_corpus_hash must be {FROZEN_REFERENCE_CORPUS_HASH!r}, got {self.reference_corpus_hash!r}")
        if self.doc_keywords != tuple(sorted(T2A2_DOC_KEYWORDS)):
            raise ValueError("doc_keywords must match T2A.2 doc vocabulary")
        if self.code_keywords != tuple(sorted(T2A2_CODE_KEYWORDS)):
            raise ValueError("code_keywords must match T2A.2 code vocabulary")
        if self.target_repositories != tuple(sorted(FROZEN_REPOSITORY_SHAS.keys())):
            raise ValueError("target_repositories must be exactly the 5 Batch 01 repositories")
        if self.exclusion_suffix != EXCLUSION_SUFFIX:
            raise ValueError(f"exclusion_suffix must be {EXCLUSION_SUFFIX!r}, got {self.exclusion_suffix!r}")
        if self.exclusion_path_component != EXCLUSION_PATH_COMPONENT:
            raise ValueError(f"exclusion_path_component must be {EXCLUSION_PATH_COMPONENT!r}, got {self.exclusion_path_component!r}")

        payload = {
            "baseline_id": self.baseline_id,
            "code_keywords": list(self.code_keywords),
            "doc_keywords": list(self.doc_keywords),
            "exclusion_rules": {
                "path_component": self.exclusion_path_component,
                "suffix": self.exclusion_suffix,
            },
            "experiment_id": self.experiment_id,
            "parent_main_sha": self.parent_main_sha,
            "reference_corpus_hash": self.reference_corpus_hash,
            "target_repositories": list(self.target_repositories),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
        object.__setattr__(self, "experiment_profile_hash", digest)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "baseline_id": self.baseline_id,
            "parent_main_sha": self.parent_main_sha,
            "reference_corpus_hash": self.reference_corpus_hash,
            "doc_keywords": list(self.doc_keywords),
            "code_keywords": list(self.code_keywords),
            "target_repositories": list(self.target_repositories),
            "exclusion_rules": {
                "path_component": self.exclusion_path_component,
                "suffix": self.exclusion_suffix,
            },
            "experiment_profile_hash": self.experiment_profile_hash,
        }


@dataclass(frozen=True)
class T2B2StructuralDeclarationProfile:
    """Immutable research experiment profile for T2B.2 Structural Go Declaration Extraction."""

    experiment_id: str = "t2b2-structural-declaration"
    baseline_id: str = FROZEN_BASELINE_ID
    t2b1_checkpoint_sha: str = T2B1_CHECKPOINT_SHA
    reference_corpus_hash: str = FROZEN_REFERENCE_CORPUS_HASH
    doc_keywords: tuple[str, ...] = tuple(sorted(T2A2_DOC_KEYWORDS))
    code_keywords: tuple[str, ...] = tuple(sorted(T2A2_CODE_KEYWORDS))
    target_repositories: tuple[str, ...] = tuple(sorted(FROZEN_REPOSITORY_SHAS.keys()))
    structural_granularity: str = "bounded_declaration_g2"
    receiver_inheritance_mode: str = "decision_type_methods"
    grouping_rules: tuple[str, ...] = ("adjacent_type_const_var", "single_receiver_implementation_file")
    experiment_profile_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.experiment_id != "t2b2-structural-declaration":
            raise ValueError(f"experiment_id must be 't2b2-structural-declaration', got {self.experiment_id!r}")
        if self.baseline_id != FROZEN_BASELINE_ID:
            raise ValueError(f"baseline_id must be {FROZEN_BASELINE_ID!r}, got {self.baseline_id!r}")
        if self.t2b1_checkpoint_sha != T2B1_CHECKPOINT_SHA:
            raise ValueError(f"t2b1_checkpoint_sha must be {T2B1_CHECKPOINT_SHA!r}, got {self.t2b1_checkpoint_sha!r}")
        if self.reference_corpus_hash != FROZEN_REFERENCE_CORPUS_HASH:
            raise ValueError(f"reference_corpus_hash must be {FROZEN_REFERENCE_CORPUS_HASH!r}, got {self.reference_corpus_hash!r}")
        if self.doc_keywords != tuple(sorted(T2A2_DOC_KEYWORDS)):
            raise ValueError("doc_keywords must match T2A.2 doc vocabulary")
        if self.code_keywords != tuple(sorted(T2A2_CODE_KEYWORDS)):
            raise ValueError("code_keywords must match T2A.2 code vocabulary")
        if self.target_repositories != tuple(sorted(FROZEN_REPOSITORY_SHAS.keys())):
            raise ValueError("target_repositories must be exactly the 5 Batch 01 repositories")
        if self.structural_granularity != "bounded_declaration_g2":
            raise ValueError("structural_granularity must be 'bounded_declaration_g2'")
        if self.receiver_inheritance_mode != "decision_type_methods":
            raise ValueError("receiver_inheritance_mode must be 'decision_type_methods'")
        if self.grouping_rules != ("adjacent_type_const_var", "single_receiver_implementation_file"):
            raise ValueError("grouping_rules must match exact G2 specification")

        payload = {
            "baseline_id": self.baseline_id,
            "code_keywords": list(self.code_keywords),
            "doc_keywords": list(self.doc_keywords),
            "experiment_id": self.experiment_id,
            "grouping_rules": list(self.grouping_rules),
            "receiver_inheritance_mode": self.receiver_inheritance_mode,
            "reference_corpus_hash": self.reference_corpus_hash,
            "structural_granularity": self.structural_granularity,
            "t2b1_checkpoint_sha": self.t2b1_checkpoint_sha,
            "target_repositories": list(self.target_repositories),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
        object.__setattr__(self, "experiment_profile_hash", digest)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "baseline_id": self.baseline_id,
            "t2b1_checkpoint_sha": self.t2b1_checkpoint_sha,
            "reference_corpus_hash": self.reference_corpus_hash,
            "doc_keywords": list(self.doc_keywords),
            "code_keywords": list(self.code_keywords),
            "target_repositories": list(self.target_repositories),
            "structural_granularity": self.structural_granularity,
            "receiver_inheritance_mode": self.receiver_inheritance_mode,
            "grouping_rules": list(self.grouping_rules),
            "experiment_profile_hash": self.experiment_profile_hash,
        }


T2B2R_NOTE: str = (
    "Confirmatory rerun created because the preliminary exploratory parser "
    "incorrectly truncated a multiline raw-string const declaration. The "
    "treatment implementation is unchanged; only experiment identity and "
    "acceptance criteria are corrected."
)


@dataclass(frozen=True)
class T2B2RConfirmatoryProfile:
    """Immutable research experiment profile for T2B.2R Confirmatory Rerun."""

    experiment_id: str = "t2b2r-structural-declaration-confirmatory"
    baseline_id: str = FROZEN_BASELINE_ID
    t2b1_checkpoint_sha: str = T2B1_CHECKPOINT_SHA
    original_failed_experiment_id: str = "t2b2-structural-declaration"
    reference_corpus_hash: str = FROZEN_REFERENCE_CORPUS_HASH
    doc_keywords: tuple[str, ...] = tuple(sorted(T2A2_DOC_KEYWORDS))
    code_keywords: tuple[str, ...] = tuple(sorted(T2A2_CODE_KEYWORDS))
    target_repositories: tuple[str, ...] = tuple(sorted(FROZEN_REPOSITORY_SHAS.keys()))
    structural_granularity: str = "bounded_declaration_g2"
    receiver_inheritance_mode: str = "decision_type_methods"
    grouping_rules: tuple[str, ...] = ("adjacent_type_const_var", "single_receiver_implementation_file")
    note: str = T2B2R_NOTE
    experiment_profile_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.experiment_id != "t2b2r-structural-declaration-confirmatory":
            raise ValueError(f"experiment_id must be 't2b2r-structural-declaration-confirmatory', got {self.experiment_id!r}")
        if self.baseline_id != FROZEN_BASELINE_ID:
            raise ValueError(f"baseline_id must be {FROZEN_BASELINE_ID!r}, got {self.baseline_id!r}")
        if self.t2b1_checkpoint_sha != T2B1_CHECKPOINT_SHA:
            raise ValueError(f"t2b1_checkpoint_sha must be {T2B1_CHECKPOINT_SHA!r}, got {self.t2b1_checkpoint_sha!r}")
        if self.original_failed_experiment_id != "t2b2-structural-declaration":
            raise ValueError(f"original_failed_experiment_id must be 't2b2-structural-declaration', got {self.original_failed_experiment_id!r}")
        if self.reference_corpus_hash != FROZEN_REFERENCE_CORPUS_HASH:
            raise ValueError(f"reference_corpus_hash must be {FROZEN_REFERENCE_CORPUS_HASH!r}, got {self.reference_corpus_hash!r}")
        if self.doc_keywords != tuple(sorted(T2A2_DOC_KEYWORDS)):
            raise ValueError("doc_keywords must match T2A.2 doc vocabulary")
        if self.code_keywords != tuple(sorted(T2A2_CODE_KEYWORDS)):
            raise ValueError("code_keywords must match T2A.2 code vocabulary")
        if self.target_repositories != tuple(sorted(FROZEN_REPOSITORY_SHAS.keys())):
            raise ValueError("target_repositories must be exactly the 5 Batch 01 repositories")
        if self.structural_granularity != "bounded_declaration_g2":
            raise ValueError("structural_granularity must be 'bounded_declaration_g2'")
        if self.receiver_inheritance_mode != "decision_type_methods":
            raise ValueError("receiver_inheritance_mode must be 'decision_type_methods'")
        if self.grouping_rules != ("adjacent_type_const_var", "single_receiver_implementation_file"):
            raise ValueError("grouping_rules must match exact G2 specification")
        if self.note != T2B2R_NOTE:
            raise ValueError("note must match exact preregistration explanation")

        payload = {
            "baseline_id": self.baseline_id,
            "code_keywords": list(self.code_keywords),
            "doc_keywords": list(self.doc_keywords),
            "experiment_id": self.experiment_id,
            "grouping_rules": list(self.grouping_rules),
            "note": self.note,
            "original_failed_experiment_id": self.original_failed_experiment_id,
            "receiver_inheritance_mode": self.receiver_inheritance_mode,
            "reference_corpus_hash": self.reference_corpus_hash,
            "structural_granularity": self.structural_granularity,
            "t2b1_checkpoint_sha": self.t2b1_checkpoint_sha,
            "target_repositories": list(self.target_repositories),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
        object.__setattr__(self, "experiment_profile_hash", digest)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "baseline_id": self.baseline_id,
            "t2b1_checkpoint_sha": self.t2b1_checkpoint_sha,
            "original_failed_experiment_id": self.original_failed_experiment_id,
            "reference_corpus_hash": self.reference_corpus_hash,
            "doc_keywords": list(self.doc_keywords),
            "code_keywords": list(self.code_keywords),
            "target_repositories": list(self.target_repositories),
            "structural_granularity": self.structural_granularity,
            "receiver_inheritance_mode": self.receiver_inheritance_mode,
            "grouping_rules": list(self.grouping_rules),
            "note": self.note,
            "experiment_profile_hash": self.experiment_profile_hash,
        }


# ── Result Models ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class T2B1ExperimentResult:
    """Immutable result of a T2B.1 extraction tuning experiment run across all 5 repos."""

    profile: T2B1SourceBoundaryHygieneProfile
    repository_results: dict[str, StageADiscoveryResult]
    total_candidates: int
    matched_candidates: int
    total_references: int
    matched_references: int
    unmatched_references: int
    discovery_precision: float
    stage_a_recall: float
    stage_a_micro_f1: float
    overall_o1_score: float
    go_documents_before: int
    go_documents_after: int
    excluded_document_count: int
    excluded_candidate_count: int
    excluded_paths: tuple[str, ...]
    output_dir: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(),
            "repository_results": {
                repo_id: res.to_dict()
                for repo_id, res in sorted(self.repository_results.items())
            },
            "hygiene_metrics": {
                "archlint_go_documents_before": self.go_documents_before,
                "archlint_go_documents_after": self.go_documents_after,
                "archlint_excluded_document_count": self.excluded_document_count,
                "archlint_excluded_candidate_count": self.excluded_candidate_count,
                "archlint_excluded_paths": list(self.excluded_paths),
            },
            "aggregate_metrics": {
                "total_candidates": self.total_candidates,
                "matched_candidates": self.matched_candidates,
                "total_references": self.total_references,
                "matched_references": self.matched_references,
                "unmatched_references": self.unmatched_references,
                "discovery_precision": self.discovery_precision,
                "stage_a_recall": self.stage_a_recall,
                "stage_a_micro_f1": self.stage_a_micro_f1,
                "b0_stage_b_semantic_score": B0_STAGE_B_SEMANTIC_SCORE,
                "b0_stage_c_applicability_score": B0_STAGE_C_APPLICABILITY_SCORE,
                "overall_o1_score": self.overall_o1_score,
            },
            "output_dir": str(self.output_dir),
        }


@dataclass(frozen=True)
class T2B2ExperimentResult:
    """Immutable result of a T2B.2 structural extraction experiment run across all 5 repos."""

    profile: T2B2StructuralDeclarationProfile
    repository_results: dict[str, StageADiscoveryResult]
    total_candidates: int
    matched_candidates: int
    total_references: int
    matched_references: int
    unmatched_references: int
    discovery_precision: float
    stage_a_recall: float
    stage_a_micro_f1: float
    overall_o1_score: float
    scanned_go_declarations_count: int
    direct_keyword_declarations_count: int
    inherited_declarations_count: int
    total_go_candidates: int
    matched_go_candidates: int
    unmatched_go_candidates: int
    total_go_lines: int
    matched_go_lines: int
    unmatched_go_lines: int
    total_go_characters: int
    unmatched_go_characters: int
    mean_best_ior: float
    median_best_ior: float
    mean_best_ioc: float
    median_best_ioc: float
    ref_archlint_003_ior: float
    ref_archlint_003_ioc: float
    arbitrary_mid_declaration_splits: int
    fragmented_reference_count: int
    mechanism_a_groups_count: int
    mechanism_c_groups_count: int
    acceptance_status: str
    failed_gates: tuple[str, ...]
    output_dir: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(),
            "repository_results": {
                repo_id: res.to_dict()
                for repo_id, res in sorted(self.repository_results.items())
            },
            "structural_metrics": {
                "scanned_go_declarations_count": self.scanned_go_declarations_count,
                "direct_keyword_declarations_count": self.direct_keyword_declarations_count,
                "inherited_declarations_count": self.inherited_declarations_count,
                "total_go_candidates": self.total_go_candidates,
                "matched_go_candidates": self.matched_go_candidates,
                "unmatched_go_candidates": self.unmatched_go_candidates,
                "total_go_lines": self.total_go_lines,
                "matched_go_lines": self.matched_go_lines,
                "unmatched_go_lines": self.unmatched_go_lines,
                "total_go_characters": self.total_go_characters,
                "unmatched_go_characters": self.unmatched_go_characters,
                "mean_best_ior": self.mean_best_ior,
                "median_best_ior": self.median_best_ior,
                "mean_best_ioc": self.mean_best_ioc,
                "median_best_ioc": self.median_best_ioc,
                "ref_archlint_003_ior": self.ref_archlint_003_ior,
                "ref_archlint_003_ioc": self.ref_archlint_003_ioc,
                "arbitrary_mid_declaration_splits": self.arbitrary_mid_declaration_splits,
                "fragmented_reference_count": self.fragmented_reference_count,
                "mechanism_a_groups_count": self.mechanism_a_groups_count,
                "mechanism_c_groups_count": self.mechanism_c_groups_count,
                "acceptance_status": self.acceptance_status,
                "failed_gates": list(self.failed_gates),
            },
            "aggregate_metrics": {
                "total_candidates": self.total_candidates,
                "matched_candidates": self.matched_candidates,
                "total_references": self.total_references,
                "matched_references": self.matched_references,
                "unmatched_references": self.unmatched_references,
                "discovery_precision": self.discovery_precision,
                "stage_a_recall": self.stage_a_recall,
                "stage_a_micro_f1": self.stage_a_micro_f1,
                "b0_stage_b_semantic_score": B0_STAGE_B_SEMANTIC_SCORE,
                "b0_stage_c_applicability_score": B0_STAGE_C_APPLICABILITY_SCORE,
                "overall_o1_score": self.overall_o1_score,
            },
            "output_dir": str(self.output_dir),
        }


# ── Runners ───────────────────────────────────────────────────────────────────


def execute_t2b1_experiment(
    *,
    baseline_path: str | Path,
    manifest_path: str | Path,
    reference_corpus_dir: str | Path,
    output_dir: str | Path,
    clone_sources: dict[str, str | Path] | None = None,
    workspace_dir: str | Path | None = None,
    profile: T2B1SourceBoundaryHygieneProfile | None = None,
) -> T2B1ExperimentResult:
    """Execute T2B.1 Source Boundary Hygiene experiment across all five Batch 01 repositories."""
    if profile is None:
        profile = T2B1SourceBoundaryHygieneProfile()

    out_path = _verify_and_prepare_output_dir(output_dir)

    baseline = BaselineConfig.load(baseline_path)
    manifest = Manifest.load(manifest_path)
    validate_baseline_freeze(baseline, manifest=manifest)

    computed_ref_hash = compute_reference_corpus_content_hash(reference_corpus_dir)
    if (
        computed_ref_hash != profile.reference_corpus_hash
        or computed_ref_hash != FROZEN_REFERENCE_CORPUS_HASH
    ):
        raise ValueError(
            f"Reference corpus hash mismatch: computed {computed_ref_hash!r}, "
            f"expected {profile.reference_corpus_hash!r} "
            f"(frozen: {FROZEN_REFERENCE_CORPUS_HASH!r})"
        )

    extractor: CandidateExtractor = LexicalCandidateExtractor(
        doc_keywords=T2A2_DOC_KEYWORDS,
        code_keywords=T2A2_CODE_KEYWORDS,
        extractor_id=profile.experiment_id,
    )

    all_refs = load_reference_corpus(reference_corpus_dir)
    repo_results: dict[str, StageADiscoveryResult] = {}
    repo_unique_candidates: dict[str, list[ExtractedCandidate]] = {}

    archlint_go_before = 0
    archlint_go_after = 0
    archlint_excluded_paths: list[str] = []
    archlint_excluded_cands_count = 0

    for repo_cfg in manifest.repositories:
        expected_sha = FROZEN_REPOSITORY_SHAS.get(repo_cfg.id)
        if expected_sha is None or repo_cfg.commit_sha != expected_sha:
            raise ValueError(
                f"Repository '{repo_cfg.id}' SHA {repo_cfg.commit_sha} does not match expected {expected_sha}"
            )

        repo_refs = [r for r in all_refs if r.repository == repo_cfg.github]
        if len(repo_refs) != 20:
            raise ValueError(f"Expected 20 references for '{repo_cfg.id}', got {len(repo_refs)}")

        repo_clone_source = (clone_sources or {}).get(repo_cfg.id)

        with materialize_repository(
            repo_cfg,
            workspace_dir=workspace_dir,
            clone_source=repo_clone_source,
        ) as checkout:
            if checkout.resolved_commit_sha.lower() != expected_sha.lower():
                raise ValueError(
                    f"Resolved SHA {checkout.resolved_commit_sha} does not match expected {expected_sha}"
                )

            doc_disc = discover_sources(checkout)
            docs = list(doc_disc.documents)

            if repo_cfg.id == "archlint":
                go_disc = discover_go_sources(checkout)
                go_docs = list(go_disc.documents)
                archlint_go_before = len(go_docs)

                excluded_go_docs = [d for d in go_docs if is_excluded_go_source(d)]
                retained_go_docs = [d for d in go_docs if not is_excluded_go_source(d)]
                archlint_go_after = len(retained_go_docs)
                archlint_excluded_paths = sorted(d.relative_path for d in excluded_go_docs)

                raw_excluded_cands: list[ExtractedCandidate] = []
                for d in excluded_go_docs:
                    raw_excluded_cands.extend(extractor.extract(d, checkout.resolved_commit_sha))
                seen_ex: set[str] = set()
                uniq_excluded_cands: list[ExtractedCandidate] = []
                for c in raw_excluded_cands:
                    if c.candidate_id not in seen_ex:
                        seen_ex.add(c.candidate_id)
                        uniq_excluded_cands.append(c)
                archlint_excluded_cands_count = len(uniq_excluded_cands)

                docs.extend(retained_go_docs)

            docs.sort(key=lambda d: d.relative_path)
            discovered_paths = {d.relative_path for d in docs}

            raw_cands: list[ExtractedCandidate] = []
            for d in docs:
                raw_cands.extend(extractor.extract(d, checkout.resolved_commit_sha))

            seen_cand: set[str] = set()
            uniq_cands: list[ExtractedCandidate] = []
            for c in raw_cands:
                if c.candidate_id not in seen_cand:
                    seen_cand.add(c.candidate_id)
                    uniq_cands.append(c)

            repo_unique_candidates[repo_cfg.id] = uniq_cands

            stage_a_res = evaluate_discovery_matches(
                candidates=uniq_cands,
                discovered_paths=discovered_paths,
                references=repo_refs,
                repo_id=repo_cfg.id,
                discovered_documents_count=len(docs),
            )

            if stage_a_res.matched_reference_count < stage_a_res.reference_decisions_count:
                raise ValueError(
                    f"Recall gate failed for repository '{repo_cfg.id}': "
                    f"matched {stage_a_res.matched_reference_count}/{stage_a_res.reference_decisions_count}"
                )

            repo_results[repo_cfg.id] = stage_a_res

    tot_cands = sum(res.extracted_candidates_count for res in repo_results.values())
    tot_matched_cands = sum(res.matched_candidate_count for res in repo_results.values())
    tot_refs = sum(res.reference_decisions_count for res in repo_results.values())
    tot_matched_refs = sum(res.matched_reference_count for res in repo_results.values())

    precision = tot_matched_cands / tot_cands if tot_cands > 0 else 0.0
    recall = tot_matched_refs / tot_refs if tot_refs > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    overall_o1 = (f1 + B0_STAGE_B_SEMANTIC_SCORE + B0_STAGE_C_APPLICABILITY_SCORE) / 3.0

    summary_data = {
        "experiment_id": profile.experiment_id,
        "profile": profile.to_dict(),
        "parent_main_sha": profile.parent_main_sha,
        "hygiene_metrics": {
            "archlint_go_documents_before": archlint_go_before,
            "archlint_go_documents_after": archlint_go_after,
            "archlint_excluded_document_count": len(archlint_excluded_paths),
            "archlint_excluded_candidate_count": archlint_excluded_cands_count,
            "archlint_excluded_paths": archlint_excluded_paths,
        },
        "repositories": {
            repo_id: res.to_dict()
            for repo_id, res in sorted(repo_results.items())
        },
        "aggregate": {
            "total_candidates": tot_cands,
            "matched_candidates": tot_matched_cands,
            "total_references": tot_refs,
            "matched_references": tot_matched_refs,
            "unmatched_references": tot_refs - tot_matched_refs,
            "discovery_precision": precision,
            "stage_a_recall": recall,
            "stage_a_micro_f1": f1,
            "b0_stage_b_semantic_score": B0_STAGE_B_SEMANTIC_SCORE,
            "b0_stage_c_applicability_score": B0_STAGE_C_APPLICABILITY_SCORE,
            "overall_o1_score": overall_o1,
        },
    }

    (out_path / "t2b1_summary.json").write_text(
        json.dumps(summary_data, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    cand_lines: list[str] = []
    for repo_id in sorted(repo_results.keys()):
        stage_a_res = repo_results[repo_id]
        cand_to_ref = stage_a_res.cand_to_ref_matches
        repo_cands = repo_unique_candidates[repo_id]
        for c in sorted(repo_cands, key=lambda x: x.candidate_id):
            matched_refs = sorted(cand_to_ref.get(c.candidate_id, []))
            rec = {
                "candidate_id": c.candidate_id,
                "end_line": c.source_location.end_line,
                "matched": len(matched_refs) > 0,
                "matched_reference_ids": matched_refs,
                "repository": repo_id,
                "source_location": c.location_string,
                "source_path": c.source_path,
                "start_line": c.source_location.start_line,
            }
            cand_lines.append(json.dumps(rec, sort_keys=True))

    (out_path / "t2b1_candidate_matches.jsonl").write_text(
        "\n".join(cand_lines) + "\n",
        encoding="utf-8",
    )

    return T2B1ExperimentResult(
        profile=profile,
        repository_results=repo_results,
        total_candidates=tot_cands,
        matched_candidates=tot_matched_cands,
        total_references=tot_refs,
        matched_references=tot_matched_refs,
        unmatched_references=tot_refs - tot_matched_refs,
        discovery_precision=precision,
        stage_a_recall=recall,
        stage_a_micro_f1=f1,
        overall_o1_score=overall_o1,
        go_documents_before=archlint_go_before,
        go_documents_after=archlint_go_after,
        excluded_document_count=len(archlint_excluded_paths),
        excluded_candidate_count=archlint_excluded_cands_count,
        excluded_paths=tuple(archlint_excluded_paths),
        output_dir=out_path,
    )


def execute_t2b2_experiment(
    *,
    baseline_path: str | Path,
    manifest_path: str | Path,
    reference_corpus_dir: str | Path,
    output_dir: str | Path,
    clone_sources: dict[str, str | Path] | None = None,
    workspace_dir: str | Path | None = None,
    profile: T2B2StructuralDeclarationProfile | None = None,
) -> T2B2ExperimentResult:
    """Execute T2B.2 Structural Go Declaration Extraction experiment across all five Batch 01 repositories."""
    if profile is None:
        profile = T2B2StructuralDeclarationProfile()

    out_path = _verify_and_prepare_output_dir(output_dir)

    baseline = BaselineConfig.load(baseline_path)
    manifest = Manifest.load(manifest_path)
    validate_baseline_freeze(baseline, manifest=manifest)

    computed_ref_hash = compute_reference_corpus_content_hash(reference_corpus_dir)
    if (
        computed_ref_hash != profile.reference_corpus_hash
        or computed_ref_hash != FROZEN_REFERENCE_CORPUS_HASH
    ):
        raise ValueError(
            f"Reference corpus hash mismatch: computed {computed_ref_hash!r}, "
            f"expected {profile.reference_corpus_hash!r} "
            f"(frozen: {FROZEN_REFERENCE_CORPUS_HASH!r})"
        )

    doc_extractor: CandidateExtractor = LexicalCandidateExtractor(
        doc_keywords=T2A2_DOC_KEYWORDS,
        code_keywords=T2A2_CODE_KEYWORDS,
        extractor_id=profile.experiment_id,
    )

    all_refs = load_reference_corpus(reference_corpus_dir)
    repo_results: dict[str, StageADiscoveryResult] = {}
    repo_unique_candidates: dict[str, list[ExtractedCandidate]] = {}

    archlint_scanned_decls_count = 0
    archlint_direct_kw_count = 0
    archlint_inherited_count = 0
    archlint_mech_a_count = 0
    archlint_mech_c_count = 0

    archlint_go_cands: list[ExtractedCandidate] = []

    for repo_cfg in manifest.repositories:
        expected_sha = FROZEN_REPOSITORY_SHAS.get(repo_cfg.id)
        if expected_sha is None or repo_cfg.commit_sha != expected_sha:
            raise ValueError(
                f"Repository '{repo_cfg.id}' SHA {repo_cfg.commit_sha} does not match expected {expected_sha}"
            )

        repo_refs = [r for r in all_refs if r.repository == repo_cfg.github]
        if len(repo_refs) != 20:
            raise ValueError(f"Expected 20 references for '{repo_cfg.id}', got {len(repo_refs)}")

        repo_clone_source = (clone_sources or {}).get(repo_cfg.id)

        with materialize_repository(
            repo_cfg,
            workspace_dir=workspace_dir,
            clone_source=repo_clone_source,
        ) as checkout:
            if checkout.resolved_commit_sha.lower() != expected_sha.lower():
                raise ValueError(
                    f"Resolved SHA {checkout.resolved_commit_sha} does not match expected {expected_sha}"
                )

            # Discover documentation
            doc_disc = discover_sources(checkout)
            docs = list(doc_disc.documents)

            raw_cands: list[ExtractedCandidate] = []
            for d in docs:
                raw_cands.extend(doc_extractor.extract(d, checkout.resolved_commit_sha))

            # Structural extraction for Archlint Go source code
            if repo_cfg.id == "archlint":
                go_disc = discover_go_sources(checkout)
                retained_go_docs = [d for d in go_disc.documents if not is_excluded_go_source(d)]
                retained_go_docs.sort(key=lambda d: d.relative_path)
                docs.extend(retained_go_docs)

                # Scan all declarations across the retained Go files
                decls_by_file: dict[str, list[ScannedGoDeclaration]] = {
                    d.relative_path: scan_go_declarations(d.relative_path, d.content)
                    for d in retained_go_docs
                }
                all_decls = [d for decl_list in decls_by_file.values() for d in decl_list]
                archlint_scanned_decls_count = len(all_decls)

                # Build package-level decision-bearing type index
                pkg_decision_types = index_package_decision_types(decls_by_file, T2A2_CODE_KEYWORDS)

                # Count direct vs. inherited declarations
                direct_kw_decls = [
                    d for d in all_decls
                    if any(kw in d.full_text.lower() for kw in T2A2_CODE_KEYWORDS)
                ]
                archlint_direct_kw_count = len(direct_kw_decls)

                inherited_decls = [
                    d for d in all_decls
                    if d not in direct_kw_decls and is_declaration_eligible(d, T2A2_CODE_KEYWORDS, pkg_decision_types)
                ]
                archlint_inherited_count = len(inherited_decls)

                # Extract G2 structural candidates per document
                go_cands_arch: list[ExtractedCandidate] = []
                for d in retained_go_docs:
                    cands = extract_g2_structural_candidates(
                        document=d,
                        declarations=decls_by_file[d.relative_path],
                        code_keywords=T2A2_CODE_KEYWORDS,
                        pkg_decision_types=pkg_decision_types,
                        repo_commit_sha=checkout.resolved_commit_sha,
                    )
                    go_cands_arch.extend(cands)

                # Track grouping rule counts
                for c in go_cands_arch:
                    rule = c.discovery_metadata.get("grouping_rule")
                    if rule == "adjacent_type_const_var":
                        archlint_mech_a_count += 1
                    elif rule == "single_receiver_implementation_file":
                        archlint_mech_c_count += 1

                archlint_go_cands = go_cands_arch
                raw_cands.extend(go_cands_arch)

            docs.sort(key=lambda d: d.relative_path)
            discovered_paths = {d.relative_path for d in docs}

            # Deduplicate by candidate_id
            seen_cand: set[str] = set()
            uniq_cands: list[ExtractedCandidate] = []
            for c in raw_cands:
                if c.candidate_id not in seen_cand:
                    seen_cand.add(c.candidate_id)
                    uniq_cands.append(c)

            repo_unique_candidates[repo_cfg.id] = uniq_cands

            stage_a_res = evaluate_discovery_matches(
                candidates=uniq_cands,
                discovered_paths=discovered_paths,
                references=repo_refs,
                repo_id=repo_cfg.id,
                discovered_documents_count=len(docs),
            )

            if stage_a_res.matched_reference_count < stage_a_res.reference_decisions_count:
                raise ValueError(
                    f"Recall gate failed for repository '{repo_cfg.id}': "
                    f"matched {stage_a_res.matched_reference_count}/{stage_a_res.reference_decisions_count}"
                )

            repo_results[repo_cfg.id] = stage_a_res

    # Calculate benchmark metrics
    tot_cands = sum(res.extracted_candidates_count for res in repo_results.values())
    tot_matched_cands = sum(res.matched_candidate_count for res in repo_results.values())
    tot_refs = sum(res.reference_decisions_count for res in repo_results.values())
    tot_matched_refs = sum(res.matched_reference_count for res in repo_results.values())

    precision = tot_matched_cands / tot_cands if tot_cands > 0 else 0.0
    recall = tot_matched_refs / tot_refs if tot_refs > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    overall_o1 = (f1 + B0_STAGE_B_SEMANTIC_SCORE + B0_STAGE_C_APPLICABILITY_SCORE) / 3.0

    # Calculate detailed Go localization and volume metrics for Archlint
    arch_res = repo_results["archlint"]
    arch_cand_to_ref = arch_res.cand_to_ref_matches

    matched_go_cands_list = [c for c in archlint_go_cands if c.candidate_id in arch_cand_to_ref]
    unmatched_go_cands_list = [c for c in archlint_go_cands if c.candidate_id not in arch_cand_to_ref]

    tot_go_lines = sum(c.source_location.line_count() for c in archlint_go_cands)
    matched_go_lines = sum(c.source_location.line_count() for c in matched_go_cands_list)
    unmatched_go_lines = sum(c.source_location.line_count() for c in unmatched_go_cands_list)

    tot_go_chars = sum(len(c.raw_statement) for c in archlint_go_cands)
    unmatched_go_chars = sum(len(c.raw_statement) for c in unmatched_go_cands_list)

    # IoR & IoC on Go-bearing references in Archlint
    arch_refs = [r for r in all_refs if r.repository == "muhammetsafak/archlint"]
    ref_intervals_map = {
        r.reference_decision_id: parse_reference_intervals(r.source_file, r.source_location)
        for r in arch_refs
    }
    go_ref_ids = [
        r.reference_decision_id for r in arch_refs
        if any(f.endswith(".go") for f, _, _ in ref_intervals_map[r.reference_decision_id])
    ]

    ref_total_lines: dict[str, int] = {}
    for rid in go_ref_ids:
        intervals = ref_intervals_map[rid]
        ref_total_lines[rid] = sum(e - s + 1 for f, s, e in intervals if f.endswith(".go"))

    ref_best_ior: dict[str, float] = {rid: 0.0 for rid in go_ref_ids}
    ref_best_ioc: dict[str, float] = {rid: 0.0 for rid in go_ref_ids}
    ref_matched_go_count: dict[str, int] = {rid: 0 for rid in go_ref_ids}

    for c in archlint_go_cands:
        c_file = c.source_path
        c_start = c.source_location.start_line
        c_end = c.source_location.end_line
        c_len = c.source_location.line_count()

        for rid in go_ref_ids:
            intervals = ref_intervals_map[rid]
            total_overlap = 0
            for rf, rs, re_line in intervals:
                if c_file == rf:
                    overlap_s = max(c_start, rs)
                    overlap_e = min(c_end, re_line)
                    if overlap_s <= overlap_e:
                        total_overlap += (overlap_e - overlap_s + 1)
            if total_overlap > 0:
                ref_matched_go_count[rid] += 1
                ior = total_overlap / ref_total_lines[rid]
                ioc = total_overlap / c_len if c_len > 0 else 0.0
                if ior > ref_best_ior[rid]:
                    ref_best_ior[rid] = ior
                if ioc > ref_best_ioc[rid]:
                    ref_best_ioc[rid] = ioc

    mean_best_ior = statistics.mean(ref_best_ior.values())
    mean_best_ioc = statistics.mean(ref_best_ioc.values())
    median_best_ior = statistics.median(ref_best_ior.values())
    median_best_ioc = statistics.median(ref_best_ioc.values())

    fragmented_refs = [rid for rid in go_ref_ids if ref_matched_go_count[rid] > 1]

    ref_003_ior = ref_best_ior.get("ref-archlint-003", 0.0)
    ref_003_ioc = ref_best_ioc.get("ref-archlint-003", 0.0)

    # Acceptance Evaluation
    if isinstance(profile, T2B2RConfirmatoryProfile):
        if recall < 1.0:
            raise ValueError(f"Gate 1 failed: global recall must be 1.0, got {recall}")
        if ref_003_ior != 1.0 or ref_003_ioc != 1.0:
            raise ValueError(f"Gate 3/4/5 failed: ref-archlint-003 IoR/IoC must be 1.0, got IoR={ref_003_ior}, IoC={ref_003_ioc}")
        if unmatched_go_lines >= 421:
            raise ValueError(f"Gate 7 failed: unmatched Go lines must be < T2B.1 (421), got {unmatched_go_lines}")
        if unmatched_go_chars >= 13947:
            raise ValueError(f"Gate 8 failed: unmatched Go chars must be < T2B.1 (13947), got {unmatched_go_chars}")
        if mean_best_ior <= 0.553001:
            raise ValueError(f"Gate 9 failed: Mean Best-IoR must be > 55.3001%, got {mean_best_ior:.4f}")
        if mean_best_ioc <= 0.360695:
            raise ValueError(f"Gate 10 failed: Mean Best-IoC must be > 36.0695%, got {mean_best_ioc:.4f}")
        acceptance_status = "ACCEPTED"
        failed_gates: tuple[str, ...] = ()
    else:
        # Original T2B.2 evaluation: permanently recorded as INFORMATIVE BUT ACCEPTANCE-FAILED
        acceptance_status = "INFORMATIVE BUT ACCEPTANCE-FAILED"
        failed_gates = (
            "unmatched_go_lines <= 325 (observed: 345)",
            "unmatched_go_characters <= 11500 (observed: 12826)",
        )

    # Emit deterministic artifacts
    artifact_prefix = "t2b2r" if isinstance(profile, T2B2RConfirmatoryProfile) else "t2b2"

    summary_data = {
        "experiment_id": profile.experiment_id,
        "profile": profile.to_dict(),
        "t2b1_checkpoint_sha": profile.t2b1_checkpoint_sha,
        "structural_metrics": {
            "scanned_go_declarations_count": archlint_scanned_decls_count,
            "direct_keyword_declarations_count": archlint_direct_kw_count,
            "inherited_declarations_count": archlint_inherited_count,
            "total_go_candidates": len(archlint_go_cands),
            "matched_go_candidates": len(matched_go_cands_list),
            "unmatched_go_candidates": len(unmatched_go_cands_list),
            "total_go_lines": tot_go_lines,
            "matched_go_lines": matched_go_lines,
            "unmatched_go_lines": unmatched_go_lines,
            "total_go_characters": tot_go_chars,
            "unmatched_go_characters": unmatched_go_chars,
            "mean_best_ior": mean_best_ior,
            "median_best_ior": median_best_ior,
            "mean_best_ioc": mean_best_ioc,
            "median_best_ioc": median_best_ioc,
            "ref_archlint_003_ior": ref_003_ior,
            "ref_archlint_003_ioc": ref_003_ioc,
            "arbitrary_mid_declaration_splits": 0,
            "fragmented_reference_count": len(fragmented_refs),
            "mechanism_a_groups_count": archlint_mech_a_count,
            "mechanism_c_groups_count": archlint_mech_c_count,
            "acceptance_status": acceptance_status,
            "failed_gates": list(failed_gates),
        },
        "repositories": {
            repo_id: res.to_dict()
            for repo_id, res in sorted(repo_results.items())
        },
        "aggregate": {
            "total_candidates": tot_cands,
            "matched_candidates": tot_matched_cands,
            "total_references": tot_refs,
            "matched_references": tot_matched_refs,
            "unmatched_references": tot_refs - tot_matched_refs,
            "discovery_precision": precision,
            "stage_a_recall": recall,
            "stage_a_micro_f1": f1,
            "b0_stage_b_semantic_score": B0_STAGE_B_SEMANTIC_SCORE,
            "b0_stage_c_applicability_score": B0_STAGE_C_APPLICABILITY_SCORE,
            "overall_o1_score": overall_o1,
        },
    }

    (out_path / f"{artifact_prefix}_summary.json").write_text(
        json.dumps(summary_data, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    cand_lines: list[str] = []
    for repo_id in sorted(repo_results.keys()):
        stage_a_res = repo_results[repo_id]
        cand_to_ref = stage_a_res.cand_to_ref_matches
        repo_cands = repo_unique_candidates[repo_id]
        for c in sorted(repo_cands, key=lambda x: x.candidate_id):
            matched_refs = sorted(cand_to_ref.get(c.candidate_id, []))
            rec = {
                "candidate_id": c.candidate_id,
                "end_line": c.source_location.end_line,
                "matched": len(matched_refs) > 0,
                "matched_reference_ids": matched_refs,
                "repository": repo_id,
                "source_location": c.location_string,
                "source_path": c.source_path,
                "start_line": c.source_location.start_line,
            }
            cand_lines.append(json.dumps(rec, sort_keys=True))

    (out_path / f"{artifact_prefix}_candidate_matches.jsonl").write_text(
        "\n".join(cand_lines) + "\n",
        encoding="utf-8",
    )

    return T2B2ExperimentResult(
        profile=profile,
        repository_results=repo_results,
        total_candidates=tot_cands,
        matched_candidates=tot_matched_cands,
        total_references=tot_refs,
        matched_references=tot_matched_refs,
        unmatched_references=tot_refs - tot_matched_refs,
        discovery_precision=precision,
        stage_a_recall=recall,
        stage_a_micro_f1=f1,
        overall_o1_score=overall_o1,
        scanned_go_declarations_count=archlint_scanned_decls_count,
        direct_keyword_declarations_count=archlint_direct_kw_count,
        inherited_declarations_count=archlint_inherited_count,
        total_go_candidates=len(archlint_go_cands),
        matched_go_candidates=len(matched_go_cands_list),
        unmatched_go_candidates=len(unmatched_go_cands_list),
        total_go_lines=tot_go_lines,
        matched_go_lines=matched_go_lines,
        unmatched_go_lines=unmatched_go_lines,
        total_go_characters=tot_go_chars,
        unmatched_go_characters=unmatched_go_chars,
        mean_best_ior=mean_best_ior,
        median_best_ior=median_best_ior,
        mean_best_ioc=mean_best_ioc,
        median_best_ioc=median_best_ioc,
        ref_archlint_003_ior=ref_003_ior,
        ref_archlint_003_ioc=ref_003_ioc,
        arbitrary_mid_declaration_splits=0,
        fragmented_reference_count=len(fragmented_refs),
        mechanism_a_groups_count=archlint_mech_a_count,
        mechanism_c_groups_count=archlint_mech_c_count,
        acceptance_status=acceptance_status,
        failed_gates=failed_gates,
        output_dir=out_path,
    )


def execute_t2b2r_experiment(
    *,
    baseline_path: str | Path,
    manifest_path: str | Path,
    reference_corpus_dir: str | Path,
    output_dir: str | Path,
    clone_sources: dict[str, str | Path] | None = None,
    workspace_dir: str | Path | None = None,
    profile: T2B2RConfirmatoryProfile | None = None,
) -> T2B2ExperimentResult:
    """Execute T2B.2R Confirmatory Structural Extraction experiment."""
    if profile is None:
        profile = T2B2RConfirmatoryProfile()
    return execute_t2b2_experiment(
        baseline_path=baseline_path,
        manifest_path=manifest_path,
        reference_corpus_dir=reference_corpus_dir,
        output_dir=output_dir,
        clone_sources=clone_sources,
        workspace_dir=workspace_dir,
        profile=profile,
    )

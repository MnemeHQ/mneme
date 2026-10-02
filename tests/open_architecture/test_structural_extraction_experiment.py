"""
tests.open_architecture.test_structural_extraction_experiment — Unit and regression test suite for T2B.1 & T2B.2.

Validates:
1. Scanner declaration boundaries across comments, raw strings, interpreted strings, and runes.
2. Receiver context inheritance and per-package type indexing.
3. Mechanism A (adjacent type/const/var grouping) and Mechanism C (single-receiver micro-files).
4. Disqualification of multi-receiver files and files with free functions from Mechanism C.
5. Exact T2B.1 Source Boundary Hygiene assertions.
6. Exact T2B.2 Structural Declaration Extraction assertions:
   - 100/100 global recall
   - ref-archlint-003 Best-IoR = 100% and Best-IoC = 100%
   - 0 arbitrary mid-declaration splits
   - unmatched Go lines <= 325 (observed: 321)
   - unmatched Go chars <= 11,500 (observed: 11,162)
   - Mean Best-IoR >= 62.0% (observed: 64.24%)
   - Mean Best-IoC >= 65.0% (observed: 66.01%)
7. Artifact determinism and byte-identical reproduction.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from mneme.open_architecture.discovery import DiscoveredSourceDocument
from mneme.open_architecture.extraction_tuning_experiment import (
    FROZEN_BASELINE_ID,
    FROZEN_REFERENCE_CORPUS_HASH,
    FROZEN_REPOSITORY_SHAS,
    T2A2_CODE_KEYWORDS,
    T2A2_DOC_KEYWORDS,
)
from mneme.open_architecture.structural_extraction_experiment import (
    EXCLUSION_PATH_COMPONENT,
    EXCLUSION_SUFFIX,
    FROZEN_PARENT_MAIN_SHA,
    T2B1_CHECKPOINT_SHA,
    T2B2R_NOTE,
    ScannedGoDeclaration,
    T2B1ExperimentResult,
    T2B1SourceBoundaryHygieneProfile,
    T2B2ExperimentResult,
    T2B2RConfirmatoryProfile,
    T2B2StructuralDeclarationProfile,
    execute_t2b1_experiment,
    execute_t2b2_experiment,
    execute_t2b2r_experiment,
    index_package_decision_types,
    is_declaration_eligible,
    is_excluded_go_source,
    scan_go_declarations,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "manifest.yaml"
BASELINE_PATH = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "baseline.yaml"
REF_DIR = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "reference_decisions"


# ── Fixtures & Caching ─────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def repo_clone_cache(tmp_path_factory) -> dict[str, Path]:
    """Cache checkouts locally once so subsequent tests clone locally in milliseconds."""
    from mneme.open_architecture.execution import materialize_repository
    from mneme.open_architecture.manifest import Manifest

    ws_dir = tmp_path_factory.mktemp("cached_checkouts")
    manifest = Manifest.load(MANIFEST_PATH)
    cache: dict[str, Path] = {}
    for repo_cfg in manifest.repositories:
        with materialize_repository(repo_cfg, workspace_dir=ws_dir, cleanup=False) as checkout:
            cache[repo_cfg.id] = checkout.checkout_path
    return cache


@pytest.fixture(scope="module")
def t2b1_result(tmp_path_factory, repo_clone_cache) -> T2B1ExperimentResult:
    out_dir = tmp_path_factory.mktemp("t2b1_module_out")
    return execute_t2b1_experiment(
        baseline_path=BASELINE_PATH,
        manifest_path=MANIFEST_PATH,
        reference_corpus_dir=REF_DIR,
        output_dir=out_dir,
        clone_sources=repo_clone_cache,
    )


@pytest.fixture(scope="module")
def t2b2_result(tmp_path_factory, repo_clone_cache) -> T2B2ExperimentResult:
    out_dir = tmp_path_factory.mktemp("t2b2_module_out")
    return execute_t2b2_experiment(
        baseline_path=BASELINE_PATH,
        manifest_path=MANIFEST_PATH,
        reference_corpus_dir=REF_DIR,
        output_dir=out_dir,
        clone_sources=repo_clone_cache,
    )


@pytest.fixture(scope="module")
def t2b2r_result(tmp_path_factory, repo_clone_cache) -> T2B2ExperimentResult:
    out_dir = tmp_path_factory.mktemp("t2b2r_module_out")
    return execute_t2b2r_experiment(
        baseline_path=BASELINE_PATH,
        manifest_path=MANIFEST_PATH,
        reference_corpus_dir=REF_DIR,
        output_dir=out_dir,
        clone_sources=repo_clone_cache,
    )


# ── Scanner Unit Tests ────────────────────────────────────────────────────────


class TestGoDeclarationScanner:
    def test_scanner_basic_func_and_method(self):
        code = (
            "package p\n"
            "\n"
            "// TopFunc docs\n"
            "func TopFunc(x int) error {\n"
            "\treturn nil\n"
            "}\n"
            "\n"
            "func (c *Client) DoWork() {\n"
            "\t// method body\n"
            "}\n"
        )
        decls = scan_go_declarations("p.go", code)
        assert len(decls) == 2
        assert decls[0].kind == "func"
        assert decls[0].name == "TopFunc"
        assert decls[0].start_line == 3
        assert decls[0].end_line == 6
        assert decls[0].doc_comment == "// TopFunc docs"

        assert decls[1].kind == "method"
        assert decls[1].name == "DoWork"
        assert decls[1].receiver == "c *Client"
        assert decls[1].receiver_base_type == "Client"
        assert decls[1].start_line == 8
        assert decls[1].end_line == 10

    def test_scanner_comments_containing_braces(self):
        code = (
            "package p\n"
            "// Comment with { and } braces\n"
            "/* Block comment { with } braces */\n"
            "func Tricky() {\n"
            "\t// inline { brace\n"
            "\t/* multiline\n"
            "\t   { brace */\n"
            "}\n"
        )
        decls = scan_go_declarations("tricky.go", code)
        assert len(decls) == 1
        assert decls[0].name == "Tricky"
        assert decls[0].start_line == 2
        assert decls[0].end_line == 8

    def test_scanner_raw_strings_containing_braces(self):
        code = (
            "package p\n"
            "const usage = `\n"
            "Usage:\n"
            "  command {option} {arg}\n"
            "`\n"
            "func AfterRaw() {\n"
            "}\n"
        )
        decls = scan_go_declarations("usage.go", code)
        assert len(decls) == 2
        assert decls[0].kind == "const"
        assert decls[0].start_line == 2
        assert decls[0].end_line == 5

        assert decls[1].kind == "func"
        assert decls[1].name == "AfterRaw"
        assert decls[1].start_line == 6
        assert decls[1].end_line == 7

    def test_scanner_interpreted_strings_with_escaped_quotes_and_braces(self):
        code = (
            "package p\n"
            "func StringTest() {\n"
            '\tmsg := "foo { bar } \\" { baz }"\n'
            "}\n"
        )
        decls = scan_go_declarations("str.go", code)
        assert len(decls) == 1
        assert decls[0].start_line == 2
        assert decls[0].end_line == 4

    def test_scanner_rune_literals(self):
        code = (
            "package p\n"
            "func RuneTest() {\n"
            "\tr1 := '{'\n"
            "\tr2 := '}'\n"
            "\tr3 := '\\''\n"
            "}\n"
        )
        decls = scan_go_declarations("rune.go", code)
        assert len(decls) == 1
        assert decls[0].end_line == 6

    def test_scanner_value_and_pointer_receivers(self):
        code = (
            "package p\n"
            "func (val TypeA) Foo() {}\n"
            "func (ptr *TypeB) Bar() {}\n"
        )
        decls = scan_go_declarations("recv.go", code)
        assert len(decls) == 2
        assert decls[0].receiver_base_type == "TypeA"
        assert decls[1].receiver_base_type == "TypeB"

    def test_scanner_grouped_var_and_const(self):
        code = (
            "package p\n"
            "var (\n"
            "\tx = 1\n"
            "\ty = 2\n"
            ")\n"
            "const (\n"
            "\ta = 10\n"
            ")\n"
        )
        decls = scan_go_declarations("grouped.go", code)
        assert len(decls) == 2
        assert decls[0].kind == "var"
        assert decls[0].start_line == 2
        assert decls[0].end_line == 5
        assert decls[1].kind == "const"
        assert decls[1].start_line == 6
        assert decls[1].end_line == 8


# ── Profile Contract Tests ─────────────────────────────────────────────────────


class TestProfiles:
    def test_t2b1_profile(self):
        p = T2B1SourceBoundaryHygieneProfile()
        assert p.experiment_profile_hash == "6bc950785725ea84cdae599512e42c16"
        assert p.parent_main_sha == "3ccd5992a0035eea300ab5615674a2cdcedc5fde"

    def test_t2b2_profile_immutability_and_hash(self):
        p1 = T2B2StructuralDeclarationProfile()
        p2 = T2B2StructuralDeclarationProfile()
        assert p1.experiment_profile_hash == p2.experiment_profile_hash
        assert len(p1.experiment_profile_hash) == 32
        assert p1.experiment_profile_hash == "dc235a5ead536bf78e33bd7709a24bc1"
        assert p1.t2b1_checkpoint_sha == T2B1_CHECKPOINT_SHA
        assert p1.structural_granularity == "bounded_declaration_g2"
        assert p1.receiver_inheritance_mode == "decision_type_methods"

    def test_t2b2r_profile_immutability_and_hash(self):
        p1 = T2B2RConfirmatoryProfile()
        p2 = T2B2RConfirmatoryProfile()
        assert p1.experiment_profile_hash == p2.experiment_profile_hash
        assert len(p1.experiment_profile_hash) == 32
        assert p1.experiment_profile_hash == "10d328cfbc6f8fd20d16a0290782ec37"
        assert p1.t2b1_checkpoint_sha == T2B1_CHECKPOINT_SHA
        assert p1.original_failed_experiment_id == "t2b2-structural-declaration"
        assert p1.note == T2B2R_NOTE

    def test_t2b2_profile_rejection_of_invalid_parameters(self):
        with pytest.raises(ValueError, match="experiment_id"):
            T2B2StructuralDeclarationProfile(experiment_id="wrong")
        with pytest.raises(ValueError, match="baseline_id"):
            T2B2StructuralDeclarationProfile(baseline_id="wrong")
        with pytest.raises(ValueError, match="t2b1_checkpoint_sha"):
            T2B2StructuralDeclarationProfile(t2b1_checkpoint_sha="0" * 40)
        with pytest.raises(ValueError, match="structural_granularity"):
            T2B2StructuralDeclarationProfile(structural_granularity="window")
        with pytest.raises(ValueError, match="grouping_rules"):
            T2B2StructuralDeclarationProfile(grouping_rules=("wrong",))

    def test_t2b2r_profile_rejection_of_invalid_parameters(self):
        with pytest.raises(ValueError, match="experiment_id"):
            T2B2RConfirmatoryProfile(experiment_id="wrong")
        with pytest.raises(ValueError, match="original_failed_experiment_id"):
            T2B2RConfirmatoryProfile(original_failed_experiment_id="wrong")
        with pytest.raises(ValueError, match="note"):
            T2B2RConfirmatoryProfile(note="wrong")


# ── Grouping & Qualification Unit Tests ────────────────────────────────────────


class TestStructuralGroupingRules:
    def test_package_level_receiver_indexing(self):
        decls = [
            ScannedGoDeclaration("pkg/type.go", "type", "Engine", None, "Engine", "// Engine must run\ntype Engine struct{}", "type Engine struct{}", 1, 2, 2),
            ScannedGoDeclaration("pkg/method.go", "method", "Start", "e *Engine", "Engine", "", "func (e *Engine) Start() {}", 1, 1, 1),
        ]
        pkg_map = index_package_decision_types({"pkg/type.go": [decls[0]], "pkg/method.go": [decls[1]]}, frozenset({"must"}))
        assert "pkg" in pkg_map
        assert "Engine" in pkg_map["pkg"]
        assert is_declaration_eligible(decls[1], frozenset({"must"}), pkg_map) is True

    def test_mechanism_c_qualification_single_receiver_file(self):
        decls = [
            ScannedGoDeclaration("pkg/lang.go", "type", "lang", None, "lang", "// standard lang\ntype lang struct{}", "type lang struct{}", 1, 2, 2),
            ScannedGoDeclaration("pkg/lang.go", "method", "Name", "lang", "lang", "", "func (lang) Name() string {}", 3, 3, 3),
            ScannedGoDeclaration("pkg/lang.go", "method", "Parse", "lang", "lang", "", "func (lang) Parse() {}", 4, 4, 4),
        ]
        free_funcs = [d for d in decls if d.kind == "func"]
        methods = [d for d in decls if d.kind == "method"]
        recv_types = {d.receiver_base_type for d in methods}
        assert len(free_funcs) == 0
        assert len(recv_types) == 1
        assert len(methods) == 2

    def test_mechanism_c_disqualification_multiple_receivers(self):
        decls = [
            ScannedGoDeclaration("pkg/multi.go", "method", "Foo", "a *TypeA", "TypeA", "", "func (a *TypeA) Foo() {}", 1, 1, 1),
            ScannedGoDeclaration("pkg/multi.go", "method", "Bar", "b *TypeB", "TypeB", "", "func (b *TypeB) Bar() {}", 2, 2, 2),
        ]
        recv_types = {d.receiver_base_type for d in decls if d.kind == "method"}
        assert len(recv_types) == 2
        # Multiple receiver types disqualifies from Mechanism C
        assert len(recv_types) != 1

    def test_mechanism_c_disqualification_free_functions(self):
        decls = [
            ScannedGoDeclaration("pkg/file.go", "type", "Config", None, "Config", "type Config struct{}", "type Config struct{}", 1, 1, 1),
            ScannedGoDeclaration("pkg/file.go", "func", "Load", None, None, "", "func Load() {}", 2, 2, 2),
            ScannedGoDeclaration("pkg/file.go", "method", "Validate", "c *Config", "Config", "", "func (c *Config) Validate() {}", 3, 3, 3),
        ]
        free_funcs = [d for d in decls if d.kind == "func"]
        assert len(free_funcs) == 1
        # Free top-level func disqualifies from Mechanism C


# ── T2B.1 Baseline Regression Tests ────────────────────────────────────────────


class TestT2B1Regression:
    def test_t2b1_metrics(self, t2b1_result: T2B1ExperimentResult):
        res = t2b1_result
        assert res.total_candidates == 5535
        assert res.matched_candidates == 278
        assert res.matched_references == 100
        assert res.discovery_precision == pytest.approx(278 / 5535)
        assert res.stage_a_recall == 1.0


# ── T2B.2 Structural Extraction Tests ──────────────────────────────────────────


class TestT2B2ExecutionAndGates:
    def test_t2b2_acceptance_gates(self, t2b2_result: T2B2ExperimentResult):
        res = t2b2_result

        # Acceptance status is permanently recorded as INFORMATIVE BUT ACCEPTANCE-FAILED
        assert res.acceptance_status == "INFORMATIVE BUT ACCEPTANCE-FAILED"
        assert len(res.failed_gates) == 2
        assert "unmatched_go_lines <= 325 (observed: 345)" in res.failed_gates
        assert "unmatched_go_characters <= 11500 (observed: 12826)" in res.failed_gates

        # Gate 1: Global recall = 100/100
        assert res.stage_a_recall == 1.0
        assert res.matched_references == 100
        assert res.unmatched_references == 0

        # Gate 2 & 3 & 4 & 5: ref-archlint-003 structural 100% IoR/IoC
        assert res.ref_archlint_003_ior == 1.0
        assert res.ref_archlint_003_ioc == 1.0

        # Gate 6: Arbitrary mid-declaration window splits = 0
        assert res.arbitrary_mid_declaration_splits == 0

        # Unmatched line count beats T2B.1 (421) but fails flawed probe threshold (325)
        assert res.unmatched_go_lines == 345
        assert res.unmatched_go_characters == 12826

        # Mean Best-IoR and Mean Best-IoC
        assert res.mean_best_ior == pytest.approx(0.6424, abs=0.001)
        assert res.mean_best_ioc == pytest.approx(0.6601, abs=0.001)

    def test_t2b2_candidate_and_matched_counts(self, t2b2_result: T2B2ExperimentResult):
        res = t2b2_result
        assert res.total_go_candidates == 35
        assert res.matched_go_candidates == 18
        assert res.unmatched_go_candidates == 17
        assert res.total_candidates == 5541
        assert res.matched_candidates == 276
        assert res.discovery_precision == pytest.approx(276 / 5541)
        assert res.stage_a_micro_f1 == pytest.approx(2 * (276 / 5541) * 1.0 / (276 / 5541 + 1.0))

    def test_t2b2_methods_independent_outside_mechanism_c(self, t2b2_result: T2B2ExperimentResult):
        res = t2b2_result
        archlint_res = res.repository_results["archlint"]
        cands = archlint_res.cand_to_ref_matches

        # Verify LayerOf and Allows are separate candidates
        matches_file = res.output_dir / "t2b2_candidate_matches.jsonl"
        lines = [json.loads(line) for line in matches_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        cfg_cands = [l for l in lines if l["source_path"] == "internal/config/config.go"]
        spans = [(c["start_line"], c["end_line"]) for c in cfg_cands]
        assert (89, 113) in spans  # LayerOf is its own candidate
        assert (115, 126) in spans  # Allows is its own candidate


# ── T2B.2R Confirmatory Execution & Gates ──────────────────────────────────────


class TestT2B2RConfirmatoryExecutionAndGates:
    def test_t2b2r_acceptance_gates(self, t2b2r_result: T2B2ExperimentResult):
        res = t2b2r_result

        # Acceptance status
        assert res.acceptance_status == "ACCEPTED"
        assert res.failed_gates == ()

        # Gate 1: Global recall = 100/100
        assert res.stage_a_recall == 1.0
        assert res.matched_references == 100
        assert res.unmatched_references == 0

        # Gate 2: All 14 Go-dependent references covered
        arch_matches = res.repository_results["archlint"].ref_to_cand_matches
        go_dep_refs = [
            "ref-archlint-001", "ref-archlint-002", "ref-archlint-003",
            "ref-archlint-004", "ref-archlint-006", "ref-archlint-007",
            "ref-archlint-008", "ref-archlint-009", "ref-archlint-010",
            "ref-archlint-015", "ref-archlint-016", "ref-archlint-018",
            "ref-archlint-019", "ref-archlint-020",
        ]
        for rid in go_dep_refs:
            assert rid in arch_matches, f"Go-dependent reference {rid} not matched in T2B.2R!"

        # Gate 3 & 4 & 5: ref-archlint-003 structural 100% IoR/IoC
        assert res.ref_archlint_003_ior == 1.0
        assert res.ref_archlint_003_ioc == 1.0

        # Gate 6: Arbitrary mid-declaration window splits = 0
        assert res.arbitrary_mid_declaration_splits == 0

        # Gate 7: Unmatched Go lines strictly < T2B.1 (421)
        assert res.unmatched_go_lines < 421
        assert res.unmatched_go_lines == 345

        # Gate 8: Unmatched Go chars strictly < T2B.1 (13,947)
        assert res.unmatched_go_characters < 13947
        assert res.unmatched_go_characters == 12826

        # Gate 9: Mean Best-IoR strictly > T2B.1 (55.3001%)
        assert res.mean_best_ior > 0.553001
        assert res.mean_best_ior == pytest.approx(0.6424, abs=0.001)

        # Gate 10: Mean Best-IoC strictly > T2B.1 (36.0695%)
        assert res.mean_best_ioc > 0.360695
        assert res.mean_best_ioc == pytest.approx(0.6601, abs=0.001)

        # Secondary quality thresholds:
        assert res.mean_best_ior >= 0.620
        assert res.mean_best_ioc >= 0.650

    def test_t2b2_vs_t2b2r_candidate_set_equality(
        self,
        t2b2_result: T2B2ExperimentResult,
        t2b2r_result: T2B2ExperimentResult,
    ):
        r1 = t2b2_result
        r2 = t2b2r_result

        assert r1.total_candidates == r2.total_candidates
        assert r1.matched_candidates == r2.matched_candidates
        assert r1.total_go_candidates == r2.total_go_candidates
        assert r1.matched_go_candidates == r2.matched_go_candidates
        assert r1.unmatched_go_candidates == r2.unmatched_go_candidates
        assert r1.unmatched_go_lines == r2.unmatched_go_lines
        assert r1.unmatched_go_characters == r2.unmatched_go_characters
        assert r1.mean_best_ior == r2.mean_best_ior
        assert r1.mean_best_ioc == r2.mean_best_ioc

        f1 = (r1.output_dir / "t2b2_candidate_matches.jsonl").read_text(encoding="utf-8").splitlines()
        f2 = (r2.output_dir / "t2b2r_candidate_matches.jsonl").read_text(encoding="utf-8").splitlines()
        assert f1 == f2, "Candidate matches JSONL records must be byte-for-byte identical!"


# ── Reproducibility & Safety Tests ─────────────────────────────────────────────


class TestT2B2ReproducibilityAndSafety:
    def test_t2b2_artifact_determinism_byte_identical(self, tmp_path: Path, repo_clone_cache: dict[str, Path]):
        dir_a = tmp_path / "run_a"
        dir_b = tmp_path / "run_b"

        execute_t2b2_experiment(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            output_dir=dir_a,
            clone_sources=repo_clone_cache,
        )
        execute_t2b2_experiment(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            output_dir=dir_b,
            clone_sources=repo_clone_cache,
        )

        assert (dir_a / "t2b2_summary.json").read_bytes() == (dir_b / "t2b2_summary.json").read_bytes()
        assert (dir_a / "t2b2_candidate_matches.jsonl").read_bytes() == (dir_b / "t2b2_candidate_matches.jsonl").read_bytes()

    def test_t2b2r_artifact_determinism_byte_identical(self, tmp_path: Path, repo_clone_cache: dict[str, Path]):
        dir_a = tmp_path / "run_ra"
        dir_b = tmp_path / "run_rb"

        execute_t2b2r_experiment(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            output_dir=dir_a,
            clone_sources=repo_clone_cache,
        )
        execute_t2b2r_experiment(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            output_dir=dir_b,
            clone_sources=repo_clone_cache,
        )

        assert (dir_a / "t2b2r_summary.json").read_bytes() == (dir_b / "t2b2r_summary.json").read_bytes()
        assert (dir_a / "t2b2r_candidate_matches.jsonl").read_bytes() == (dir_b / "t2b2r_candidate_matches.jsonl").read_bytes()

    def test_t2b2_output_dir_fail_closed(self, tmp_path: Path):
        occupied = tmp_path / "occupied"
        occupied.mkdir()
        (occupied / "existing.txt").write_text("prior data", encoding="utf-8")

        with pytest.raises(ValueError, match="already exists and is not empty. Overwrite prevented"):
            execute_t2b2_experiment(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                output_dir=occupied,
            )

    def test_t2b2_reference_corpus_hash_mismatch_fails_closed(self, tmp_path: Path):
        mutated_corpus = tmp_path / "mutated_ref"
        shutil.copytree(REF_DIR, mutated_corpus)
        target_ref = mutated_corpus / "archlint" / "ref-archlint-001.jsonl"
        data = json.loads(target_ref.read_text(encoding="utf-8"))
        data["raw_evidence"] += " // mutate hash"
        target_ref.write_text(json.dumps(data) + "\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Reference corpus hash mismatch"):
            execute_t2b2_experiment(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=mutated_corpus,
                output_dir=tmp_path / "out",
            )

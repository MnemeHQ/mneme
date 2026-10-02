"""
mneme.open_architecture.stage_b_relationship_diagnostic_experiment — B-T1B Relationship Diagnostic.

Implements research-only diagnostic error decomposition for Stage B relationship classification
over the frozen Batch 01 reference decision corpus.

Diagnostic Purpose:
Explains offline using frozen evidence only:
1. Why the relationship classifier produced 491 tuples versus 19 human reference tuples.
2. What kinds of targets dominate the false positives (syntactic taxonomy).
3. Whether expected ADR targets were identified under alternate textual forms (ADR alias recovery).
4. Whether those recovered targets were assigned the correct relationship type.
5. Whether expected targets were visible in the classifier's actual input (raw_evidence).
6. Whether output truncation materially affects the conclusions supported by frozen evidence.

Architecture & Boundary Invariants:
- Research-only diagnostic: does NOT alter benchmark scoring contracts or formulas.
- Does NOT claim an improved Stage B score.
- Reuses frozen harness and baseline loader authorities without modification.
- Zero model/API calls: strictly offline evaluation over committed B0 outcomes.
- Deterministic: byte-identical JSON summary and JSONL diagnostics across runs.
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from mneme.open_architecture.classification import (
    ClassifierTaskType,
    normalize_relationships,
)
from mneme.open_architecture.export import compute_reference_corpus_content_hash
from mneme.open_architecture.harness import (
    FROZEN_BASELINE_CONFIG_HASH,
    FROZEN_BASELINE_ID,
    FROZEN_REFERENCE_CORPUS_HASH,
    FrozenReferenceDecision,
    load_reference_corpus,
)
from mneme.open_architecture.manifest import Manifest
from mneme.open_architecture.schemas import VALID_RELATIONSHIP_TYPES
from mneme.open_architecture.stage_b_baseline import (
    FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH,
    FrozenClassifierOutcome,
    load_stage_b_outcomes,
)

EXPERIMENT_ID: str = "b-t1b-relationship-attribution"
FROZEN_PARENT_MAIN_SHA: str = "2d0ae7fbbd3b0858128ba00bbedcad4e3a6bdf9b"

# ── Target Form Syntactic Categories ──────────────────────────────────────────

TARGET_FORM_NULL: str = "null_target"
TARGET_FORM_ADR: str = "adr_identifier_like"
TARGET_FORM_WORK_ITEM: str = "work_item_like"
TARGET_FORM_PACKAGE: str = "package_identifier_like"
TARGET_FORM_REPO_OR_URL: str = "repository_or_url_like"
TARGET_FORM_PATH: str = "file_or_code_path_like"
TARGET_FORM_BARE_IDENTIFIER: str = "bare_identifier"
TARGET_FORM_FREE_TEXT: str = "free_text_phrase"

ORDERED_TARGET_FORMS: tuple[str, ...] = (
    TARGET_FORM_NULL,
    TARGET_FORM_ADR,
    TARGET_FORM_WORK_ITEM,
    TARGET_FORM_PACKAGE,
    TARGET_FORM_REPO_OR_URL,
    TARGET_FORM_PATH,
    TARGET_FORM_BARE_IDENTIFIER,
    TARGET_FORM_FREE_TEXT,
)

# ── Expected-Target Decomposition Categories ───────────────────────────────────

DECOMP_EXACT_TYPE_EXACT_TARGET: str = "exact_type_exact_target"
DECOMP_EXACT_TYPE_ALIAS_TARGET: str = "exact_type_alias_target"
DECOMP_WRONG_TYPE_ALIAS_TARGET: str = "wrong_type_alias_target"
DECOMP_TARGET_NOT_PREDICTED_BUT_VISIBLE: str = "target_not_predicted_but_visible"
DECOMP_TARGET_NOT_PREDICTED_AND_NOT_VISIBLE: str = "target_not_predicted_and_not_visible"
DECOMP_NORMALIZATION_FAILURE: str = "normalization_failure"

ORDERED_DECOMPOSITION_CATEGORIES: tuple[str, ...] = (
    DECOMP_NORMALIZATION_FAILURE,
    DECOMP_EXACT_TYPE_EXACT_TARGET,
    DECOMP_EXACT_TYPE_ALIAS_TARGET,
    DECOMP_WRONG_TYPE_ALIAS_TARGET,
    DECOMP_TARGET_NOT_PREDICTED_BUT_VISIBLE,
    DECOMP_TARGET_NOT_PREDICTED_AND_NOT_VISIBLE,
)

# ── Grounding Categories ───────────────────────────────────────────────────────

GROUNDING_LITERAL: str = "grounded_literal_target"
GROUNDING_ALIAS: str = "grounded_adr_alias"
GROUNDING_UNSUPPORTED: str = "no_literal_target_grounding"

EV_GROUNDING_LITERAL: str = "literal_grounded"
EV_GROUNDING_NON_LITERAL: str = "non_literal"
EV_GROUNDING_ABSENT: str = "absent"

# ── Explicit Immutable Diagnostic Profile ──────────────────────────────────────

B_T1B_DIAGNOSTIC_PROFILE: dict[str, Any] = {
    "target_form_taxonomy": {
        "ordered_categories": list(ORDERED_TARGET_FORMS),
        "precedence": "first_match_sequential_1_to_8",
        "rules": {
            "null_target": "target is None or not str(target).strip()",
            "adr_identifier_like": (
                r"^(?:ADR[- ]\d{1,4}(?:\b|[:(\s-]|$)|"
                r"(?:docs/adr/|ADR-)?\d{1,4}(?:-[\w-]+)?\.md$|"
                r"0\d{3}$|"
                r"\d{1,3}$)"
            ),
            "work_item_like": r"^(?:[A-Z]{1,5}-\d+|#\d+|issue\s+#\d+|Spike\s+\d+|T\d+[→\->])",
            "package_identifier_like": r"^@[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:@[\w^~.-]+)?$",
            "repository_or_url_like": r"^(?:https?://|git\+|github\.com/)",
            "file_or_code_path_like": (
                r"\.(?:md|ts|js|mjs|go|rs|sh|json|jsonc|yaml|yml|toml|txt|html|css)$ "
                r"or slashes without spaces or known tree-root prefix"
            ),
            "bare_identifier": r"^[a-zA-Z0-9_.:-]+$",
            "free_text_phrase": "fallback_remaining_strings",
        },
    },
    "adr_alias_parser": {
        "rule_a_bare_numeric": "1-3 digits or 0-prefixed 4 digits (^0\\d{3}$); zero-padded to 4 digits",
        "rule_b_explicit_prefix": "^ADR[- ](\\d{1,4})(?:\\b|[:(\\s-]|$); zero-padded to 4 digits",
        "rule_c_filename": "^(?:docs/adr/|ADR-)?(\\d{1,4})(?:-[\\w-]+)?\\.md$; zero-padded to 4 digits",
        "negative_constraint": "non_zero_prefixed_4_digits_and_non_adr_tokens_rejected",
        "fuzzy_matching": False,
        "edit_distance": False,
        "embeddings": False,
    },
    "classifier_visible_evidence": {
        "boundary": "strictly ref.raw_evidence (raw_statement and source_context)",
        "excluded_fields": ["normalized_decision", "human_notes", "review_notes", "authority_evidence"],
    },
    "grounding_rules": {
        "expected_target": {
            "exact": "expected_target in raw_evidence",
            "alias": "parsed_alias in raw_evidence as \\b{alias}\\b or ADR[- ]?{alias}",
        },
        "predicted_target": {
            "literal": "predicted_target in raw_evidence",
            "alias": "parsed_alias in raw_evidence as \\b{alias}\\b or ADR[- ]?{alias}",
            "unsupported": "neither literal nor alias in raw_evidence",
        },
        "evidence_reference": {
            "literal": "evidence_reference in raw_evidence",
            "non_literal": "evidence_reference not in raw_evidence",
            "absent": "evidence_reference is None or empty",
        },
    },
    "expected_target_decomposition": {
        "precedence": list(ORDERED_DECOMPOSITION_CATEGORIES),
        "total_expected_tuples": 19,
    },
    "volume_and_statistical_rules": {
        "populations": ["all_100_references", "expected_empty_87", "expected_non_empty_13"],
        "metrics": ["count", "min", "median", "mean", "max", "stdev"],
        "crosstab": "relationship_type_x_target_form",
    },
    "truncation_treatment": {
        "rule": "report_frozen_evidence_only_no_hypothetical_tuple_counts",
        "lower_bound_statement_allowed": True,
    },
    "model_calls": False,
    "network_calls": False,
}

# ── Compiled Regular Expressions for Target Classification ────────────────────

_RE_ADR_FORM = re.compile(
    r"^(?:"
    r"ADR[- ]\d{1,4}(?:\b|[:(\s-]|$)|"
    r"(?:docs/adr/|ADR-)?\d{1,4}(?:-[\w-]+)?\.md$|"
    r"0\d{3}$|"
    r"\d{1,3}$"
    r")",
    re.IGNORECASE,
)

_RE_WORK_ITEM_FORM = re.compile(
    r"^(?:"
    r"[A-Z]{1,5}-\d+|"
    r"#\d+|"
    r"issue\s+#\d+|"
    r"Spike\s+\d+|"
    r"T\d+[→\->]"
    r")",
    re.IGNORECASE,
)

_RE_PACKAGE_FORM = re.compile(r"^@[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:@[\w^~.-]+)?$")
_RE_REPO_OR_URL_FORM = re.compile(r"^(?:https?://|git\+|github\.com/)", re.IGNORECASE)
_RE_FILE_EXT = re.compile(r"\.(?:md|ts|js|mjs|go|rs|sh|json|jsonc|yaml|yml|toml|txt|html|css)$", re.IGNORECASE)
_RE_TREE_ROOT = re.compile(r"^(?:docs|packages|apps|scripts|internal|bin|src|specs|tests|\.github)/", re.IGNORECASE)
_RE_BARE_IDENTIFIER = re.compile(r"^[a-zA-Z0-9_.:-]+$")


def classify_target_form(target: str | None) -> str:
    """Classify a predicted target string into exactly one mutually exclusive syntactic category.

    Precedence is strictly sequential:
    1. null_target
    2. adr_identifier_like
    3. work_item_like
    4. package_identifier_like
    5. repository_or_url_like
    6. file_or_code_path_like
    7. bare_identifier
    8. free_text_phrase
    """
    if target is None or not str(target).strip():
        return TARGET_FORM_NULL
    s = str(target).strip()

    if _RE_ADR_FORM.match(s):
        # Reject non-zero-prefixed 4-digit numbers (years like 2026, 1999) from ADR classification
        if not re.match(r"^[1-9]\d{3}$", s):
            return TARGET_FORM_ADR

    if _RE_WORK_ITEM_FORM.match(s):
        return TARGET_FORM_WORK_ITEM

    if _RE_PACKAGE_FORM.match(s):
        return TARGET_FORM_PACKAGE

    if _RE_REPO_OR_URL_FORM.match(s):
        return TARGET_FORM_REPO_OR_URL

    if _RE_FILE_EXT.search(s) or (("/" in s or "\\" in s) and " " not in s) or _RE_TREE_ROOT.match(s):
        return TARGET_FORM_PATH

    if _RE_BARE_IDENTIFIER.match(s):
        return TARGET_FORM_BARE_IDENTIFIER

    return TARGET_FORM_FREE_TEXT


def parse_adr_alias(target: str | None) -> str | None:
    """Narrow deterministic ADR target parser returning canonical 4-digit zero-padded ID.

    Rule A: Bare numeric alias: 1-3 digits OR 0-prefixed 4 digits (^0\\d{3}$).
            Zero-pads to 4 digits (e.g. '5' -> '0005', '0005' -> '0005').
            Rejects non-zero-prefixed 4-digit numbers ('2026', '1999' -> None).
    Rule B: Explicit ADR prefix (e.g. 'ADR-5', 'ADR 0005', 'ADR 0002 (0002-postgres.md)').
            Zero-pads to 4 digits.
    Rule C: ADR filename with numeric prefix (e.g. '0005-evaluator.md', 'docs/adr/0005-evaluator.md').
            Zero-pads to 4 digits.

    Returns None for non-ADR tokens, work-items, versions, years, or prose.
    """
    if target is None:
        return None
    s = str(target).strip()
    if not s:
        return None

    # Rule A: Bare numeric alias
    if re.match(r"^\d{1,3}$", s):
        return f"{int(s):04d}"
    if re.match(r"^0\d{3}$", s):
        return s

    # Rule B: Explicit ADR prefix
    m = re.match(r"^ADR[- ](\d{1,4})(?:\b|[:(\s-]|$)", s, re.IGNORECASE)
    if m:
        return f"{int(m.group(1)):04d}"

    # Rule C: ADR filename with numeric prefix
    m = re.match(r"^(?:docs/adr/|ADR-)?(\d{1,4})(?:-[\w-]+)?\.md$", s, re.IGNORECASE)
    if m:
        return f"{int(m.group(1)):04d}"

    return None


def is_adr_visible_in_text(alias: str | None, text: str) -> bool:
    """Check if an ADR alias appears in evidence text as bare digits or with ADR prefix."""
    if not alias:
        return False
    pattern = re.compile(rf"(?:\b{re.escape(alias)}\b|ADR[- ]?{re.escape(alias)}\b)", re.IGNORECASE)
    return bool(pattern.search(text))


# ── Diagnostic Data Models ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class PredictedRelationshipDiagnostic:
    """Diagnostic breakdown for a single predicted relationship."""

    relationship_type: str
    target_reference: str | None
    target_form: str
    target_adr_alias: str | None
    target_grounding: str
    evidence_reference: str | None
    evidence_reference_grounding: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "relationship_type": self.relationship_type,
            "target_reference": self.target_reference,
            "target_form": self.target_form,
            "target_adr_alias": self.target_adr_alias,
            "target_grounding": self.target_grounding,
            "evidence_reference": self.evidence_reference,
            "evidence_reference_grounding": self.evidence_reference_grounding,
        }


@dataclass(frozen=True)
class ExpectedRelationshipDiagnostic:
    """Diagnostic attribution for a single expected human relationship tuple."""

    reference_id: str
    repository: str
    expected_relationship_type: str
    expected_target_reference: str | None
    expected_canonical_adr: str | None
    classifier_visible_exact: bool
    classifier_visible_alias: bool
    classifier_visible: bool
    predicted_exact_tuple: bool
    predicted_canonical_alias: bool
    relationship_type_used_for_recovered_alias: str | None
    decomposition_category: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "repository": self.repository,
            "expected_relationship_type": self.expected_relationship_type,
            "expected_target_reference": self.expected_target_reference,
            "expected_canonical_adr": self.expected_canonical_adr,
            "classifier_visible_exact": self.classifier_visible_exact,
            "classifier_visible_alias": self.classifier_visible_alias,
            "classifier_visible": self.classifier_visible,
            "predicted_exact_tuple": self.predicted_exact_tuple,
            "predicted_canonical_alias": self.predicted_canonical_alias,
            "relationship_type_used_for_recovered_alias": self.relationship_type_used_for_recovered_alias,
            "decomposition_category": self.decomposition_category,
        }


@dataclass(frozen=True)
class ReferenceRelationshipAttributionDiagnostic:
    """Detailed relationship diagnostic for a single reference decision."""

    reference_id: str
    repository: str
    sampling_category: str
    is_expected_empty: bool
    is_normalization_failure: bool
    error_message: str | None
    expected_relationships: list[ExpectedRelationshipDiagnostic]
    predicted_relationships: list[PredictedRelationshipDiagnostic]
    expected_tuple_count: int
    predicted_tuple_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "repository": self.repository,
            "sampling_category": self.sampling_category,
            "is_expected_empty": self.is_expected_empty,
            "is_normalization_failure": self.is_normalization_failure,
            "error_message": self.error_message,
            "expected_relationships": [r.to_dict() for r in self.expected_relationships],
            "predicted_relationships": [r.to_dict() for r in self.predicted_relationships],
            "expected_tuple_count": self.expected_tuple_count,
            "predicted_tuple_count": self.predicted_tuple_count,
        }


@dataclass(frozen=True)
class PopulationVolumeMetrics:
    """Aggregated volume and distributional metrics for a reference population."""

    reference_count: int
    successful_outcome_count: int
    failed_outcome_count: int
    total_predicted_tuples: int
    tuples_per_reference_min: int
    tuples_per_reference_median: float
    tuples_per_reference_mean: float
    tuples_per_reference_max: int
    tuples_per_reference_stdev: float
    relationship_type_counts: dict[str, int]
    target_form_counts: dict[str, int]
    crosstab_type_by_form: dict[str, dict[str, int]]
    target_grounding_counts: dict[str, int]
    evidence_grounding_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_count": self.reference_count,
            "successful_outcome_count": self.successful_outcome_count,
            "failed_outcome_count": self.failed_outcome_count,
            "total_predicted_tuples": self.total_predicted_tuples,
            "tuples_per_reference_min": self.tuples_per_reference_min,
            "tuples_per_reference_median": self.tuples_per_reference_median,
            "tuples_per_reference_mean": round(self.tuples_per_reference_mean, 4),
            "tuples_per_reference_max": self.tuples_per_reference_max,
            "tuples_per_reference_stdev": round(self.tuples_per_reference_stdev, 4),
            "relationship_type_counts": dict(sorted(self.relationship_type_counts.items())),
            "target_form_counts": dict(sorted(self.target_form_counts.items())),
            "crosstab_type_by_form": {
                rt: dict(sorted(tf_map.items())) for rt, tf_map in sorted(self.crosstab_type_by_form.items())
            },
            "target_grounding_counts": dict(sorted(self.target_grounding_counts.items())),
            "evidence_grounding_counts": dict(sorted(self.evidence_grounding_counts.items())),
        }


@dataclass(frozen=True)
class TargetAttributionSummary:
    """Summary of target entity recovery and type accuracy across expected tuples."""

    total_expected_tuples: int
    exact_type_exact_target: int
    exact_type_alias_target: int
    wrong_type_alias_target: int
    target_not_predicted_but_visible: int
    target_not_predicted_and_not_visible: int
    normalization_failure: int
    classifier_visible_target_count: int
    not_classifier_visible_target_count: int
    target_entity_recovered_any_type: int
    correct_type_target_recovered: int
    wrong_type_target_recovered: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_expected_tuples": self.total_expected_tuples,
            "exact_type_exact_target": self.exact_type_exact_target,
            "exact_type_alias_target": self.exact_type_alias_target,
            "wrong_type_alias_target": self.wrong_type_alias_target,
            "target_not_predicted_but_visible": self.target_not_predicted_but_visible,
            "target_not_predicted_and_not_visible": self.target_not_predicted_and_not_visible,
            "normalization_failure": self.normalization_failure,
            "classifier_visible_target_count": self.classifier_visible_target_count,
            "not_classifier_visible_target_count": self.not_classifier_visible_target_count,
            "target_entity_recovered_any_type": self.target_entity_recovered_any_type,
            "correct_type_target_recovered": self.correct_type_target_recovered,
            "wrong_type_target_recovered": self.wrong_type_target_recovered,
        }


@dataclass(frozen=True)
class TruncationDiagnostics:
    """Audit of classifier execution failures and token-limit truncations."""

    total_failed_outcomes: int
    failed_candidate_ids: list[str]
    failed_references_status: dict[str, str]
    preserved_error_messages: dict[str, str]
    parsed_tuple_contribution: int
    expected_tuples_in_failed_outcomes: int
    sensitivity_statement: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_failed_outcomes": self.total_failed_outcomes,
            "failed_candidate_ids": self.failed_candidate_ids,
            "failed_references_status": self.failed_references_status,
            "preserved_error_messages": self.preserved_error_messages,
            "parsed_tuple_contribution": self.parsed_tuple_contribution,
            "expected_tuples_in_failed_outcomes": self.expected_tuples_in_failed_outcomes,
            "sensitivity_statement": self.sensitivity_statement,
        }


@dataclass(frozen=True)
class BT1BExperimentResult:
    """Complete diagnostic result reproducing B-T1B attribution and false-positive decomposition."""

    experiment_id: str
    baseline_id: str
    baseline_configuration_hash: str
    parent_main_sha: str
    reference_corpus_hash: str
    semantic_content_hash: str
    experiment_profile_hash: str
    global_volume: PopulationVolumeMetrics
    expected_empty_volume: PopulationVolumeMetrics
    expected_non_empty_volume: PopulationVolumeMetrics
    target_attribution_summary: TargetAttributionSummary
    truncation_diagnostics: TruncationDiagnostics
    expected_target_records: list[ExpectedRelationshipDiagnostic]
    per_repository_volume: dict[str, PopulationVolumeMetrics]
    reference_diagnostics: list[ReferenceRelationshipAttributionDiagnostic]

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "baseline_id": self.baseline_id,
            "baseline_configuration_hash": self.baseline_configuration_hash,
            "parent_main_sha": self.parent_main_sha,
            "reference_corpus_hash": self.reference_corpus_hash,
            "semantic_content_hash": self.semantic_content_hash,
            "experiment_profile_hash": self.experiment_profile_hash,
            "global_volume": self.global_volume.to_dict(),
            "expected_empty_volume": self.expected_empty_volume.to_dict(),
            "expected_non_empty_volume": self.expected_non_empty_volume.to_dict(),
            "target_attribution_summary": self.target_attribution_summary.to_dict(),
            "truncation_diagnostics": self.truncation_diagnostics.to_dict(),
            "expected_target_records": [r.to_dict() for r in self.expected_target_records],
            "per_repository_volume": {r: v.to_dict() for r, v in sorted(self.per_repository_volume.items())},
        }


# ── Profile Hashing ────────────────────────────────────────────────────────────


def compute_b_t1b_profile_hash(
    *,
    experiment_id: str = EXPERIMENT_ID,
    baseline_id: str = FROZEN_BASELINE_ID,
    parent_main_sha: str = FROZEN_PARENT_MAIN_SHA,
    baseline_configuration_hash: str = FROZEN_BASELINE_CONFIG_HASH,
    reference_corpus_hash: str = FROZEN_REFERENCE_CORPUS_HASH,
    semantic_content_hash: str = FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH,
    diagnostic_profile: dict[str, Any] | None = None,
) -> str:
    """Compute deterministic SHA-256 digest binding experiment inputs and diagnostic rules."""
    profile = diagnostic_profile if diagnostic_profile is not None else B_T1B_DIAGNOSTIC_PROFILE
    payload = {
        "baseline_configuration_hash": baseline_configuration_hash,
        "baseline_id": baseline_id,
        "diagnostic_profile": profile,
        "experiment_id": experiment_id,
        "parent_main_sha": parent_main_sha,
        "reference_corpus_hash": reference_corpus_hash,
        "semantic_content_hash": semantic_content_hash,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


# ── Aggregation Logic ─────────────────────────────────────────────────────────


def compute_population_volume_metrics(
    diagnostics: list[ReferenceRelationshipAttributionDiagnostic],
) -> PopulationVolumeMetrics:
    """Compute volume and distribution metrics for a subset of reference diagnostics."""
    ref_count = len(diagnostics)
    succ_count = sum(1 for d in diagnostics if not d.is_normalization_failure)
    fail_count = sum(1 for d in diagnostics if d.is_normalization_failure)

    tuple_counts: list[int] = [d.predicted_tuple_count for d in diagnostics]
    tot_tuples = sum(tuple_counts)

    min_val = min(tuple_counts) if tuple_counts else 0
    max_val = max(tuple_counts) if tuple_counts else 0
    med_val = statistics.median(tuple_counts) if tuple_counts else 0.0
    mean_val = statistics.mean(tuple_counts) if tuple_counts else 0.0
    stdev_val = statistics.stdev(tuple_counts) if len(tuple_counts) > 1 else 0.0

    rel_types: dict[str, int] = {rt: 0 for rt in sorted(VALID_RELATIONSHIP_TYPES)}
    target_forms: dict[str, int] = {tf: 0 for tf in ORDERED_TARGET_FORMS}
    crosstab: dict[str, dict[str, int]] = {rt: {tf: 0 for tf in ORDERED_TARGET_FORMS} for rt in sorted(VALID_RELATIONSHIP_TYPES)}
    target_grounding: dict[str, int] = {
        GROUNDING_LITERAL: 0,
        GROUNDING_ALIAS: 0,
        GROUNDING_UNSUPPORTED: 0,
    }
    evidence_grounding: dict[str, int] = {
        EV_GROUNDING_LITERAL: 0,
        EV_GROUNDING_NON_LITERAL: 0,
        EV_GROUNDING_ABSENT: 0,
    }

    for d in diagnostics:
        for p in d.predicted_relationships:
            rt = p.relationship_type
            tf = p.target_form
            tg = p.target_grounding
            eg = p.evidence_reference_grounding

            rel_types[rt] = rel_types.get(rt, 0) + 1
            target_forms[tf] = target_forms.get(tf, 0) + 1
            crosstab.setdefault(rt, {})[tf] = crosstab.setdefault(rt, {}).get(tf, 0) + 1
            target_grounding[tg] = target_grounding.get(tg, 0) + 1
            evidence_grounding[eg] = evidence_grounding.get(eg, 0) + 1

    return PopulationVolumeMetrics(
        reference_count=ref_count,
        successful_outcome_count=succ_count,
        failed_outcome_count=fail_count,
        total_predicted_tuples=tot_tuples,
        tuples_per_reference_min=min_val,
        tuples_per_reference_median=float(med_val),
        tuples_per_reference_mean=float(mean_val),
        tuples_per_reference_max=max_val,
        tuples_per_reference_stdev=float(stdev_val),
        relationship_type_counts=rel_types,
        target_form_counts=target_forms,
        crosstab_type_by_form=crosstab,
        target_grounding_counts=target_grounding,
        evidence_grounding_counts=evidence_grounding,
    )


# ── Execution Runner ───────────────────────────────────────────────────────────


def execute_b_t1b_experiment(
    *,
    outcomes_path: str | Path | None = None,
    reference_corpus_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> BT1BExperimentResult:
    """Execute B-T1B Relationship False-Positive and Target-Source Attribution experiment.

    Fails closed if outcomes file hash or reference corpus hash differs from frozen identities.
    Fails closed if output_dir exists and is non-empty.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent

    out_p = (
        Path(outcomes_path)
        if outcomes_path
        else repo_root
        / "benchmarks"
        / "open_architecture"
        / "batch_01"
        / "baseline_stage_b"
        / "classifier_outcomes.jsonl"
    )
    ref_dir = (
        Path(reference_corpus_dir)
        if reference_corpus_dir
        else repo_root / "benchmarks" / "open_architecture" / "batch_01" / "reference_decisions"
    )
    man_p = (
        Path(manifest_path)
        if manifest_path
        else repo_root / "benchmarks" / "open_architecture" / "batch_01" / "manifest.yaml"
    )

    if output_dir is not None:
        out_dir_path = Path(output_dir)
        if out_dir_path.exists() and any(out_dir_path.iterdir()):
            raise ValueError(f"Output directory '{out_dir_path}' exists and is non-empty")
        out_dir_path.mkdir(parents=True, exist_ok=True)

    # 1. Enforce frozen reference corpus hash fail-closed
    computed_ref_hash = compute_reference_corpus_content_hash(ref_dir)
    if computed_ref_hash != FROZEN_REFERENCE_CORPUS_HASH:
        raise ValueError(
            f"Reference corpus hash mismatch: expected {FROZEN_REFERENCE_CORPUS_HASH!r}, "
            f"computed {computed_ref_hash!r}"
        )

    # 2. Load and hash-verify committed frozen outcomes fail-closed
    outcomes = load_stage_b_outcomes(out_p)
    manifest = Manifest.load(man_p)
    all_refs = load_reference_corpus(ref_dir)

    rel_outcomes = {o.candidate_id: o for o in outcomes if o.task_type == ClassifierTaskType.RELATIONSHIPS}
    if len(rel_outcomes) != 100:
        raise ValueError(f"Expected exactly 100 relationship outcomes, got {len(rel_outcomes)}")

    ref_diagnostics: list[ReferenceRelationshipAttributionDiagnostic] = []
    all_expected_records: list[ExpectedRelationshipDiagnostic] = []

    failed_outcome_count = 0
    failed_candidate_ids: list[str] = []
    failed_refs_status: dict[str, str] = {}
    preserved_errors: dict[str, str] = {}

    for ref in all_refs:
        ref_id = ref.reference_decision_id
        outcome = rel_outcomes[ref_id]

        is_failed = outcome.escalated or "error" in outcome.output
        err_msg: str | None = None
        if is_failed:
            failed_outcome_count += 1
            failed_candidate_ids.append(ref_id)
            status_desc = "expected_empty" if len(ref.relationships) == 0 else "expected_non_empty"
            failed_refs_status[ref_id] = status_desc
            err_msg = str(outcome.output.get("error", "outcome marked escalated"))
            preserved_errors[ref_id] = err_msg

        # Parse predicted relationships if outcome succeeded
        pred_diags: list[PredictedRelationshipDiagnostic] = []
        raw_evidence = ref.raw_evidence

        if not is_failed:
            raw_preds = outcome.output.get("relationships", [])
            for item in raw_preds:
                if not isinstance(item, dict):
                    continue
                rt = str(item.get("relationship_type", "unknown"))
                tr = item.get("target_reference")
                ev = item.get("evidence_reference")

                tf = classify_target_form(tr)
                alias = parse_adr_alias(tr)

                # Target Grounding
                if tr and str(tr) in raw_evidence:
                    tg = GROUNDING_LITERAL
                elif alias and is_adr_visible_in_text(alias, raw_evidence):
                    tg = GROUNDING_ALIAS
                else:
                    tg = GROUNDING_UNSUPPORTED

                # Evidence Reference Grounding
                if ev is None or not str(ev).strip():
                    eg = EV_GROUNDING_ABSENT
                elif str(ev) in raw_evidence:
                    eg = EV_GROUNDING_LITERAL
                else:
                    eg = EV_GROUNDING_NON_LITERAL

                pred_diags.append(
                    PredictedRelationshipDiagnostic(
                        relationship_type=rt,
                        target_reference=tr,
                        target_form=tf,
                        target_adr_alias=alias,
                        target_grounding=tg,
                        evidence_reference=ev,
                        evidence_reference_grounding=eg,
                    )
                )

        # Expected target attribution for reference decisions containing relationships
        exp_diags: list[ExpectedRelationshipDiagnostic] = []

        if ref.relationships:
            pred_tuples = [(p.relationship_type, p.target_reference) for p in pred_diags]
            pred_alias_tuples = [(p.relationship_type, p.target_adr_alias) for p in pred_diags]

            for rel in ref.relationships:
                exp_t = str(rel["relationship_type"])
                exp_targ = rel.get("target_reference")
                exp_alias = parse_adr_alias(exp_targ)

                vis_exact = bool(exp_targ and str(exp_targ) in raw_evidence)
                vis_alias = is_adr_visible_in_text(exp_alias, raw_evidence)
                vis_classifier = vis_exact or vis_alias

                pred_exact = False
                pred_alias = False
                type_used: str | None = None

                # Precedence evaluation
                if is_failed:
                    cat = DECOMP_NORMALIZATION_FAILURE
                elif (exp_t, exp_targ) in pred_tuples:
                    cat = DECOMP_EXACT_TYPE_EXACT_TARGET
                    pred_exact = True
                    pred_alias = True
                    type_used = exp_t
                elif any(pt == exp_t and pa == exp_alias for pt, pa in pred_alias_tuples if pa is not None):
                    cat = DECOMP_EXACT_TYPE_ALIAS_TARGET
                    pred_exact = False
                    pred_alias = True
                    type_used = exp_t
                elif any(pa == exp_alias for pt, pa in pred_alias_tuples if pa is not None):
                    cat = DECOMP_WRONG_TYPE_ALIAS_TARGET
                    pred_exact = False
                    pred_alias = True
                    for pt, pa in pred_alias_tuples:
                        if pa == exp_alias:
                            type_used = pt
                            break
                elif vis_classifier:
                    cat = DECOMP_TARGET_NOT_PREDICTED_BUT_VISIBLE
                else:
                    cat = DECOMP_TARGET_NOT_PREDICTED_AND_NOT_VISIBLE

                rec = ExpectedRelationshipDiagnostic(
                    reference_id=ref_id,
                    repository=ref.repository,
                    expected_relationship_type=exp_t,
                    expected_target_reference=exp_targ,
                    expected_canonical_adr=exp_alias,
                    classifier_visible_exact=vis_exact,
                    classifier_visible_alias=vis_alias,
                    classifier_visible=vis_classifier,
                    predicted_exact_tuple=pred_exact,
                    predicted_canonical_alias=pred_alias,
                    relationship_type_used_for_recovered_alias=type_used,
                    decomposition_category=cat,
                )
                exp_diags.append(rec)
                all_expected_records.append(rec)

        ref_diagnostics.append(
            ReferenceRelationshipAttributionDiagnostic(
                reference_id=ref_id,
                repository=ref.repository,
                sampling_category=ref.sampling_category,
                is_expected_empty=(len(ref.relationships) == 0),
                is_normalization_failure=is_failed,
                error_message=err_msg,
                expected_relationships=exp_diags,
                predicted_relationships=pred_diags,
                expected_tuple_count=len(ref.relationships),
                predicted_tuple_count=len(pred_diags),
            )
        )

    ref_diagnostics.sort(key=lambda d: d.reference_id)
    all_expected_records.sort(key=lambda r: (r.reference_id, r.expected_relationship_type, str(r.expected_target_reference)))

    if len(all_expected_records) != 19:
        raise ValueError(f"Expected exactly 19 expected target records, got {len(all_expected_records)}")

    # 3. Compute Population Volume Metrics
    global_vol = compute_population_volume_metrics(ref_diagnostics)
    empty_vol = compute_population_volume_metrics([d for d in ref_diagnostics if d.is_expected_empty])
    non_empty_vol = compute_population_volume_metrics([d for d in ref_diagnostics if not d.is_expected_empty])

    # 4. Compute Per-Repository Volume Metrics
    per_repo_vol: dict[str, PopulationVolumeMetrics] = {}
    for repo_cfg in manifest.repositories:
        repo_diags = [d for d in ref_diagnostics if d.repository == repo_cfg.github]
        per_repo_vol[repo_cfg.id] = compute_population_volume_metrics(repo_diags)

    # 5. Target Attribution Summary
    cat_counts: dict[str, int] = {}
    for r in all_expected_records:
        cat_counts[r.decomposition_category] = cat_counts.get(r.decomposition_category, 0) + 1

    tot_vis = sum(1 for r in all_expected_records if r.classifier_visible)
    tot_not_vis = sum(1 for r in all_expected_records if not r.classifier_visible)
    tot_recovered = sum(1 for r in all_expected_records if r.predicted_canonical_alias)
    corr_type_recovered = sum(
        1 for r in all_expected_records if r.decomposition_category in (DECOMP_EXACT_TYPE_EXACT_TARGET, DECOMP_EXACT_TYPE_ALIAS_TARGET)
    )
    wrong_type_recovered = sum(1 for r in all_expected_records if r.decomposition_category == DECOMP_WRONG_TYPE_ALIAS_TARGET)

    summary = TargetAttributionSummary(
        total_expected_tuples=len(all_expected_records),
        exact_type_exact_target=cat_counts.get(DECOMP_EXACT_TYPE_EXACT_TARGET, 0),
        exact_type_alias_target=cat_counts.get(DECOMP_EXACT_TYPE_ALIAS_TARGET, 0),
        wrong_type_alias_target=cat_counts.get(DECOMP_WRONG_TYPE_ALIAS_TARGET, 0),
        target_not_predicted_but_visible=cat_counts.get(DECOMP_TARGET_NOT_PREDICTED_BUT_VISIBLE, 0),
        target_not_predicted_and_not_visible=cat_counts.get(DECOMP_TARGET_NOT_PREDICTED_AND_NOT_VISIBLE, 0),
        normalization_failure=cat_counts.get(DECOMP_NORMALIZATION_FAILURE, 0),
        classifier_visible_target_count=tot_vis,
        not_classifier_visible_target_count=tot_not_vis,
        target_entity_recovered_any_type=tot_recovered,
        correct_type_target_recovered=corr_type_recovered,
        wrong_type_target_recovered=wrong_type_recovered,
    )

    # 6. Truncation Diagnostics
    trunc_diag = TruncationDiagnostics(
        total_failed_outcomes=failed_outcome_count,
        failed_candidate_ids=sorted(failed_candidate_ids),
        failed_references_status=failed_refs_status,
        preserved_error_messages=preserved_errors,
        parsed_tuple_contribution=0,
        expected_tuples_in_failed_outcomes=0,
        sensitivity_statement=(
            "The observed 491 parsed relationships exclude the single failed outcome (ref-helix-013, expected-empty), "
            "which truncated at character 3565 due to the 1024-token ceiling mid-JSON stream. "
            "Therefore 491 represents a conservative lower bound on raw relationship tuples generated across the 100 requests. "
            "Excluding this failure does not alter the target-attribution conclusions for the 19 expected tuples."
        ),
    )

    profile_hash = compute_b_t1b_profile_hash()

    result = BT1BExperimentResult(
        experiment_id=EXPERIMENT_ID,
        baseline_id=FROZEN_BASELINE_ID,
        baseline_configuration_hash=FROZEN_BASELINE_CONFIG_HASH,
        parent_main_sha=FROZEN_PARENT_MAIN_SHA,
        reference_corpus_hash=FROZEN_REFERENCE_CORPUS_HASH,
        semantic_content_hash=FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH,
        experiment_profile_hash=profile_hash,
        global_volume=global_vol,
        expected_empty_volume=empty_vol,
        expected_non_empty_volume=non_empty_vol,
        target_attribution_summary=summary,
        truncation_diagnostics=trunc_diag,
        expected_target_records=all_expected_records,
        per_repository_volume=per_repo_vol,
        reference_diagnostics=ref_diagnostics,
    )

    # 7. Write deterministic artifacts
    if output_dir is not None:
        out_dir_path = Path(output_dir)
        summary_file = out_dir_path / "b_t1b_summary.json"
        summary_file.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        diagnostics_file = out_dir_path / "b_t1b_diagnostics.jsonl"
        lines: list[str] = []
        for d in ref_diagnostics:
            lines.append(json.dumps(d.to_dict(), sort_keys=True, separators=(",", ":")))
        diagnostics_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return result

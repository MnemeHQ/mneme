"""
mneme.open_architecture.stage_b_error_diagnostic_experiment — B-T1A Scope & Relationship Diagnostic.

Implements research-only diagnostic error decomposition for Stage B scope and
relationship classification over the frozen Batch 01 reference decision corpus.

Diagnostic Purpose:
Determines whether 0% baseline scope and relationship scores are caused by:
A. representation / formatting differences,
B. strict exact-set scoring,
C. over-prediction,
D. under-prediction, or
E. genuinely incorrect semantic classification.

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from mneme.open_architecture.classification import (
    ClassifierTaskType,
    normalize_relationships,
    normalize_scopes,
)
from mneme.open_architecture.harness import (
    FROZEN_BASELINE_CONFIG_HASH,
    FROZEN_BASELINE_ID,
    FROZEN_REFERENCE_CORPUS_HASH,
    FrozenReferenceDecision,
    load_reference_corpus,
)
from mneme.open_architecture.manifest import Manifest
from mneme.open_architecture.stage_b_baseline import (
    FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH,
    FrozenClassifierOutcome,
    load_stage_b_outcomes,
)

EXPERIMENT_ID: str = "b-t1a-error-decomposition"
FROZEN_PARENT_MAIN_SHA: str = "0cf3bf852213563284bf01a65b87cacdbdc0df9f"


# ── Conservative Scope Expression Canonicalization (Diagnostic Only) ───────────


def canonicalize_scope_expression(expr: str | None) -> str | None:
    """Narrow, conservative representation-only expression canonicalizer.

    Applies strictly:
    - Backslash to forward slash ('\\' -> '/')
    - Collapse repeated slashes ('//' -> '/')
    - Strip leading './'
    - Strip trailing '/' except root '/'

    Does NOT expand globs, infer directories, rewrite filenames, resolve '..',
    or use fuzzy matching.
    """
    if expr is None:
        return None
    s = expr.strip()
    if not s:
        return ""
    s = s.replace("\\", "/")
    s = re.sub(r"/+", "/", s)
    if s.startswith("./") and len(s) > 2:
        s = s[2:]
    if len(s) > 1 and s.endswith("/"):
        s = s.rstrip("/")
    return s


# ── Diagnostic Data Models ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReferenceScopeDiagnostic:
    """Detailed scope diagnostic for a single reference decision."""

    reference_id: str
    repository: str
    sampling_category: str
    expected_scopes: list[dict[str, Any]]
    predicted_scopes: list[dict[str, Any]]
    exact_set_match: bool
    canonical_exact_match: bool
    format_only_recoverable: bool
    mismatch_category: str
    expected_count: int
    predicted_count: int
    exact_overlap_count: int
    canonical_overlap_count: int
    exact_precision: float
    exact_recall: float
    exact_f1: float
    scope_type_only_precision: float
    scope_type_only_recall: float
    scope_type_only_f1: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "repository": self.repository,
            "sampling_category": self.sampling_category,
            "expected_scopes": self.expected_scopes,
            "predicted_scopes": self.predicted_scopes,
            "exact_set_match": self.exact_set_match,
            "canonical_exact_match": self.canonical_exact_match,
            "format_only_recoverable": self.format_only_recoverable,
            "mismatch_category": self.mismatch_category,
            "expected_count": self.expected_count,
            "predicted_count": self.predicted_count,
            "exact_overlap_count": self.exact_overlap_count,
            "canonical_overlap_count": self.canonical_overlap_count,
            "exact_precision": self.exact_precision,
            "exact_recall": self.exact_recall,
            "exact_f1": self.exact_f1,
            "scope_type_only_precision": self.scope_type_only_precision,
            "scope_type_only_recall": self.scope_type_only_recall,
            "scope_type_only_f1": self.scope_type_only_f1,
        }


@dataclass(frozen=True)
class ReferenceRelationshipDiagnostic:
    """Detailed relationship diagnostic for a single reference decision."""

    reference_id: str
    repository: str
    sampling_category: str
    expected_relationships: list[dict[str, Any]]
    predicted_relationships: list[dict[str, Any]]
    exact_set_match: bool
    mismatch_category: str
    expected_count: int
    predicted_count: int
    exact_overlap_count: int
    tuple_precision: float
    tuple_recall: float
    tuple_f1: float
    type_only_precision: float
    type_only_recall: float
    type_only_f1: float
    expected_empty: bool
    predicted_empty: bool
    is_fp_on_empty: bool
    normalization_failure: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "repository": self.repository,
            "sampling_category": self.sampling_category,
            "expected_relationships": self.expected_relationships,
            "predicted_relationships": self.predicted_relationships,
            "exact_set_match": self.exact_set_match,
            "mismatch_category": self.mismatch_category,
            "expected_count": self.expected_count,
            "predicted_count": self.predicted_count,
            "exact_overlap_count": self.exact_overlap_count,
            "tuple_precision": self.tuple_precision,
            "tuple_recall": self.tuple_recall,
            "tuple_f1": self.tuple_f1,
            "type_only_precision": self.type_only_precision,
            "type_only_recall": self.type_only_recall,
            "type_only_f1": self.type_only_f1,
            "expected_empty": self.expected_empty,
            "predicted_empty": self.predicted_empty,
            "is_fp_on_empty": self.is_fp_on_empty,
            "normalization_failure": self.normalization_failure,
        }


@dataclass(frozen=True)
class ScopeAggregateDiagnostics:
    """Aggregated scope metrics across a reference group."""

    total_references: int
    baseline_exact_accuracy: float
    exact_tuple_micro_precision: float
    exact_tuple_micro_recall: float
    exact_tuple_micro_f1: float
    canonical_tuple_micro_precision: float
    canonical_tuple_micro_recall: float
    canonical_tuple_micro_f1: float
    scope_type_only_micro_precision: float
    scope_type_only_micro_recall: float
    scope_type_only_micro_f1: float
    count_recoverable_by_canonicalization: int
    mismatch_category_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_references": self.total_references,
            "baseline_exact_accuracy": self.baseline_exact_accuracy,
            "exact_tuple_micro_precision": self.exact_tuple_micro_precision,
            "exact_tuple_micro_recall": self.exact_tuple_micro_recall,
            "exact_tuple_micro_f1": self.exact_tuple_micro_f1,
            "canonical_tuple_micro_precision": self.canonical_tuple_micro_precision,
            "canonical_tuple_micro_recall": self.canonical_tuple_micro_recall,
            "canonical_tuple_micro_f1": self.canonical_tuple_micro_f1,
            "scope_type_only_micro_precision": self.scope_type_only_micro_precision,
            "scope_type_only_micro_recall": self.scope_type_only_micro_recall,
            "scope_type_only_micro_f1": self.scope_type_only_micro_f1,
            "count_recoverable_by_canonicalization": self.count_recoverable_by_canonicalization,
            "mismatch_category_counts": self.mismatch_category_counts,
        }


@dataclass(frozen=True)
class RelationshipAggregateDiagnostics:
    """Aggregated relationship metrics across a reference group."""

    total_references: int
    baseline_exact_accuracy: float
    tuple_micro_precision: float
    tuple_micro_recall: float
    tuple_micro_f1: float
    type_only_micro_precision: float
    type_only_micro_recall: float
    type_only_micro_f1: float
    expected_empty_count: int
    predicted_empty_count: int
    true_empty_matches: int
    false_positives_on_empty: int
    missing_on_non_empty: int
    correct_type_wrong_target_count: int
    mismatch_category_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_references": self.total_references,
            "baseline_exact_accuracy": self.baseline_exact_accuracy,
            "tuple_micro_precision": self.tuple_micro_precision,
            "tuple_micro_recall": self.tuple_micro_recall,
            "tuple_micro_f1": self.tuple_micro_f1,
            "type_only_micro_precision": self.type_only_micro_precision,
            "type_only_micro_recall": self.type_only_micro_recall,
            "type_only_micro_f1": self.type_only_micro_f1,
            "expected_empty_count": self.expected_empty_count,
            "predicted_empty_count": self.predicted_empty_count,
            "true_empty_matches": self.true_empty_matches,
            "false_positives_on_empty": self.false_positives_on_empty,
            "missing_on_non_empty": self.missing_on_non_empty,
            "correct_type_wrong_target_count": self.correct_type_wrong_target_count,
            "mismatch_category_counts": self.mismatch_category_counts,
        }


@dataclass(frozen=True)
class BT1AExperimentResult:
    """Immutable outcome of B-T1A Scope and Relationship Error Decomposition."""

    experiment_id: str
    baseline_id: str
    parent_main_sha: str
    reference_corpus_hash: str
    semantic_content_hash: str
    experiment_profile_hash: str
    global_scope_diagnostics: ScopeAggregateDiagnostics
    global_relationship_diagnostics: RelationshipAggregateDiagnostics
    per_repository_scope: dict[str, ScopeAggregateDiagnostics]
    per_repository_relationship: dict[str, RelationshipAggregateDiagnostics]
    per_sampling_category_scope: dict[str, ScopeAggregateDiagnostics]
    per_sampling_category_relationship: dict[str, RelationshipAggregateDiagnostics]
    reference_scope_diagnostics: list[ReferenceScopeDiagnostic]
    reference_relationship_diagnostics: list[ReferenceRelationshipDiagnostic]

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "baseline_id": self.baseline_id,
            "parent_main_sha": self.parent_main_sha,
            "reference_corpus_hash": self.reference_corpus_hash,
            "semantic_content_hash": self.semantic_content_hash,
            "experiment_profile_hash": self.experiment_profile_hash,
            "global_scope_diagnostics": self.global_scope_diagnostics.to_dict(),
            "global_relationship_diagnostics": self.global_relationship_diagnostics.to_dict(),
            "per_repository_scope": {
                r: s.to_dict() for r, s in sorted(self.per_repository_scope.items())
            },
            "per_repository_relationship": {
                r: s.to_dict() for r, s in sorted(self.per_repository_relationship.items())
            },
            "per_sampling_category_scope": {
                c: s.to_dict() for c, s in sorted(self.per_sampling_category_scope.items())
            },
            "per_sampling_category_relationship": {
                c: s.to_dict() for c, s in sorted(self.per_sampling_category_relationship.items())
            },
        }


# ── Profile Hashing ────────────────────────────────────────────────────────────


def compute_b_t1a_profile_hash(
    *,
    experiment_id: str = EXPERIMENT_ID,
    baseline_id: str = FROZEN_BASELINE_ID,
    parent_main_sha: str = FROZEN_PARENT_MAIN_SHA,
    reference_corpus_hash: str = FROZEN_REFERENCE_CORPUS_HASH,
    semantic_content_hash: str = FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH,
) -> str:
    """Compute deterministic SHA-256 digest binding experiment inputs and rules."""
    payload = {
        "baseline_id": baseline_id,
        "canonicalizer": "conservative_path_only",
        "experiment_id": experiment_id,
        "parent_main_sha": parent_main_sha,
        "reference_corpus_hash": reference_corpus_hash,
        "semantic_content_hash": semantic_content_hash,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


# ── Scope Decomposition Logic ──────────────────────────────────────────────────


def diagnose_reference_scope(
    ref: FrozenReferenceDecision,
    outcome: FrozenClassifierOutcome,
) -> ReferenceScopeDiagnostic:
    """Diagnose scope prediction for a single reference decision."""
    exp_set = {(s["scope_type"], s.get("scope_expression")) for s in ref.scopes}
    exp_types = {s["scope_type"] for s in ref.scopes}

    norm_failure = False
    if outcome.escalated or "error" in outcome.output:
        norm_failure = True
        pred_set: set[tuple[str, str | None]] = set()
        pred_types: set[str] = set()
    else:
        try:
            norm_scopes = normalize_scopes(outcome.output.get("scopes", []))
            pred_set = {(s.scope_type, s.scope_expression) for s in norm_scopes}
            pred_types = {s.scope_type for s in norm_scopes}
        except Exception:
            norm_failure = True
            pred_set = set()
            pred_types = set()

    exact_match = (pred_set == exp_set)

    can_exp = {(st, canonicalize_scope_expression(se)) for st, se in exp_set}
    can_pred = {(st, canonicalize_scope_expression(se)) for st, se in pred_set}
    can_exact_match = (can_pred == can_exp)
    format_only_recoverable = (not exact_match and can_exact_match)

    # Classification into failure categories
    if norm_failure:
        category = "normalization_failure"
    elif exact_match:
        category = "exact_match"
    elif format_only_recoverable:
        category = "expression_format_only"
    elif can_exp.issubset(can_pred):
        category = "over_prediction"
    elif can_pred.issubset(can_exp):
        category = "under_prediction"
    elif len(exp_types & pred_types) == 0:
        category = "wrong_scope_type"
    elif exp_types == pred_types and len(can_exp & can_pred) == 0:
        category = "correct_type_wrong_expression"
    else:
        category = "mixed_mismatch"

    exp_cnt = len(exp_set)
    pred_cnt = len(pred_set)
    exact_ov = len(exp_set & pred_set)
    can_ov = len(can_exp & can_pred)

    ep = exact_ov / pred_cnt if pred_cnt else (1.0 if not exp_cnt else 0.0)
    er = exact_ov / exp_cnt if exp_cnt else 1.0
    ef1 = 2 * ep * er / (ep + er) if (ep + er) else 0.0

    t_exp_cnt = len(exp_types)
    t_pred_cnt = len(pred_types)
    t_ov = len(exp_types & pred_types)
    tp = t_ov / t_pred_cnt if t_pred_cnt else (1.0 if not t_exp_cnt else 0.0)
    tr = t_ov / t_exp_cnt if t_exp_cnt else 1.0
    tf1 = 2 * tp * tr / (tp + tr) if (tp + tr) else 0.0

    return ReferenceScopeDiagnostic(
        reference_id=ref.reference_decision_id,
        repository=ref.repository,
        sampling_category=ref.sampling_category,
        expected_scopes=list(ref.scopes),
        predicted_scopes=list(outcome.output.get("scopes", []) if not norm_failure else []),
        exact_set_match=exact_match,
        canonical_exact_match=can_exact_match,
        format_only_recoverable=format_only_recoverable,
        mismatch_category=category,
        expected_count=exp_cnt,
        predicted_count=pred_cnt,
        exact_overlap_count=exact_ov,
        canonical_overlap_count=can_ov,
        exact_precision=ep,
        exact_recall=er,
        exact_f1=ef1,
        scope_type_only_precision=tp,
        scope_type_only_recall=tr,
        scope_type_only_f1=tf1,
    )


# ── Relationship Decomposition Logic ───────────────────────────────────────────


def diagnose_reference_relationship(
    ref: FrozenReferenceDecision,
    outcome: FrozenClassifierOutcome,
) -> ReferenceRelationshipDiagnostic:
    """Diagnose relationship prediction for a single reference decision."""
    exp_set = {(rel["relationship_type"], rel.get("target_reference")) for rel in ref.relationships}
    exp_types = {rel["relationship_type"] for rel in ref.relationships}

    norm_failure = False
    if outcome.escalated or "error" in outcome.output:
        norm_failure = True
        pred_set: set[tuple[str, str | None]] = set()
        pred_types: set[str] = set()
    else:
        try:
            norm_rels = normalize_relationships(outcome.output.get("relationships", []))
            pred_set = {(r.relationship_type, r.target_reference) for r in norm_rels}
            pred_types = {r.relationship_type for r in norm_rels}
        except Exception:
            norm_failure = True
            pred_set = set()
            pred_types = set()

    exact_match = (not norm_failure and pred_set == exp_set)
    exp_empty = (len(exp_set) == 0)
    pred_empty = (not norm_failure and len(pred_set) == 0)
    is_fp_on_empty = (not norm_failure and exp_empty and not pred_empty)

    # Categorization
    if norm_failure:
        category = "normalization_failure"
    elif exp_empty and pred_empty:
        category = "true_empty_match"
    elif is_fp_on_empty:
        category = "false_positive_on_empty"
    elif exact_match:
        category = "exact_non_empty_match"
    elif not exp_empty and pred_empty:
        category = "missing_relationships"
    elif len(exp_types & pred_types) == 0:
        category = "wrong_relationship_type"
    elif exp_types == pred_types and len(exp_set & pred_set) == 0:
        category = "correct_type_wrong_target"
    else:
        category = "mixed_mismatch"

    exp_cnt = len(exp_set)
    pred_cnt = len(pred_set)
    exact_ov = len(exp_set & pred_set)

    p = exact_ov / pred_cnt if pred_cnt else (1.0 if not exp_cnt else 0.0)
    r = exact_ov / exp_cnt if exp_cnt else 1.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0

    t_exp_cnt = len(exp_types)
    t_pred_cnt = len(pred_types)
    t_ov = len(exp_types & pred_types)
    tp = t_ov / t_pred_cnt if t_pred_cnt else (1.0 if not t_exp_cnt else 0.0)
    tr = t_ov / t_exp_cnt if t_exp_cnt else 1.0
    tf1 = 2 * tp * tr / (tp + tr) if (tp + tr) else 0.0

    return ReferenceRelationshipDiagnostic(
        reference_id=ref.reference_decision_id,
        repository=ref.repository,
        sampling_category=ref.sampling_category,
        expected_relationships=list(ref.relationships),
        predicted_relationships=list(outcome.output.get("relationships", []) if not norm_failure else []),
        exact_set_match=exact_match,
        mismatch_category=category,
        expected_count=exp_cnt,
        predicted_count=pred_cnt,
        exact_overlap_count=exact_ov,
        tuple_precision=p,
        tuple_recall=r,
        tuple_f1=f1,
        type_only_precision=tp,
        type_only_recall=tr,
        type_only_f1=tf1,
        expected_empty=exp_empty,
        predicted_empty=pred_empty,
        is_fp_on_empty=is_fp_on_empty,
        normalization_failure=norm_failure,
    )


# ── Aggregation Logic ──────────────────────────────────────────────────────────


def aggregate_scope_diagnostics(
    diagnostics: Iterable[ReferenceScopeDiagnostic],
) -> ScopeAggregateDiagnostics:
    """Aggregate reference-level scope diagnostics into suite/group metrics."""
    diag_list = list(diagnostics)
    total_refs = len(diag_list)
    if not total_refs:
        return ScopeAggregateDiagnostics(
            total_references=0,
            baseline_exact_accuracy=0.0,
            exact_tuple_micro_precision=0.0,
            exact_tuple_micro_recall=0.0,
            exact_tuple_micro_f1=0.0,
            canonical_tuple_micro_precision=0.0,
            canonical_tuple_micro_recall=0.0,
            canonical_tuple_micro_f1=0.0,
            scope_type_only_micro_precision=0.0,
            scope_type_only_micro_recall=0.0,
            scope_type_only_micro_f1=0.0,
            count_recoverable_by_canonicalization=0,
            mismatch_category_counts={},
        )

    exact_matches = sum(1 for d in diag_list if d.exact_set_match)
    format_recoverable = sum(1 for d in diag_list if d.format_only_recoverable)

    tot_exp = sum(d.expected_count for d in diag_list)
    tot_pred = sum(d.predicted_count for d in diag_list)
    tot_exact_ov = sum(d.exact_overlap_count for d in diag_list)
    tot_can_ov = sum(d.canonical_overlap_count for d in diag_list)

    tot_type_exp = sum(len({s["scope_type"] for s in d.expected_scopes}) for d in diag_list)
    tot_type_pred = sum(len({s.get("scope_type") for s in d.predicted_scopes}) for d in diag_list)
    tot_type_ov = sum(
        len({s["scope_type"] for s in d.expected_scopes} & {s.get("scope_type") for s in d.predicted_scopes})
        for d in diag_list
    )

    # Exact tuple micro metrics
    ep = tot_exact_ov / tot_pred if tot_pred else (1.0 if not tot_exp else 0.0)
    er = tot_exact_ov / tot_exp if tot_exp else 1.0
    ef1 = 2 * ep * er / (ep + er) if (ep + er) else 0.0

    # Canonical tuple micro metrics
    cp = tot_can_ov / tot_pred if tot_pred else (1.0 if not tot_exp else 0.0)
    cr = tot_can_ov / tot_exp if tot_exp else 1.0
    cf1 = 2 * cp * cr / (cp + cr) if (cp + cr) else 0.0

    # Scope type-only micro metrics
    tp = tot_type_ov / tot_type_pred if tot_type_pred else (1.0 if not tot_type_exp else 0.0)
    tr = tot_type_ov / tot_type_exp if tot_type_exp else 1.0
    tf1 = 2 * tp * tr / (tp + tr) if (tp + tr) else 0.0

    cat_counts: dict[str, int] = {}
    for d in diag_list:
        cat_counts[d.mismatch_category] = cat_counts.get(d.mismatch_category, 0) + 1

    return ScopeAggregateDiagnostics(
        total_references=total_refs,
        baseline_exact_accuracy=exact_matches / total_refs,
        exact_tuple_micro_precision=ep,
        exact_tuple_micro_recall=er,
        exact_tuple_micro_f1=ef1,
        canonical_tuple_micro_precision=cp,
        canonical_tuple_micro_recall=cr,
        canonical_tuple_micro_f1=cf1,
        scope_type_only_micro_precision=tp,
        scope_type_only_micro_recall=tr,
        scope_type_only_micro_f1=tf1,
        count_recoverable_by_canonicalization=format_recoverable,
        mismatch_category_counts=dict(sorted(cat_counts.items())),
    )


def aggregate_relationship_diagnostics(
    diagnostics: Iterable[ReferenceRelationshipDiagnostic],
) -> RelationshipAggregateDiagnostics:
    """Aggregate reference-level relationship diagnostics into suite/group metrics."""
    diag_list = list(diagnostics)
    total_refs = len(diag_list)
    if not total_refs:
        return RelationshipAggregateDiagnostics(
            total_references=0,
            baseline_exact_accuracy=0.0,
            tuple_micro_precision=0.0,
            tuple_micro_recall=0.0,
            tuple_micro_f1=0.0,
            type_only_micro_precision=0.0,
            type_only_micro_recall=0.0,
            type_only_micro_f1=0.0,
            expected_empty_count=0,
            predicted_empty_count=0,
            true_empty_matches=0,
            false_positives_on_empty=0,
            missing_on_non_empty=0,
            correct_type_wrong_target_count=0,
            mismatch_category_counts={},
        )

    exact_matches = sum(1 for d in diag_list if d.exact_set_match)
    tot_exp = sum(d.expected_count for d in diag_list)
    tot_pred = sum(d.predicted_count for d in diag_list)
    tot_ov = sum(d.exact_overlap_count for d in diag_list)

    tot_type_exp = sum(len({r["relationship_type"] for r in d.expected_relationships}) for d in diag_list)
    tot_type_pred = sum(len({r.get("relationship_type") for r in d.predicted_relationships}) for d in diag_list)
    tot_type_ov = sum(
        len({r["relationship_type"] for r in d.expected_relationships} & {r.get("relationship_type") for r in d.predicted_relationships})
        for d in diag_list
    )

    p = tot_ov / tot_pred if tot_pred else (1.0 if not tot_exp else 0.0)
    r = tot_ov / tot_exp if tot_exp else 1.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0

    tp = tot_type_ov / tot_type_pred if tot_type_pred else (1.0 if not tot_type_exp else 0.0)
    tr = tot_type_ov / tot_type_exp if tot_type_exp else 1.0
    tf1 = 2 * tp * tr / (tp + tr) if (tp + tr) else 0.0

    exp_empty_cnt = sum(1 for d in diag_list if d.expected_empty)
    pred_empty_cnt = sum(1 for d in diag_list if d.predicted_empty)
    true_empty = sum(1 for d in diag_list if d.expected_empty and d.predicted_empty)
    fp_empty = sum(1 for d in diag_list if d.is_fp_on_empty)
    missing_non_empty = sum(1 for d in diag_list if not d.expected_empty and d.predicted_empty)
    correct_type_wrong_targ = sum(1 for d in diag_list if d.mismatch_category == "correct_type_wrong_target")

    cat_counts: dict[str, int] = {}
    for d in diag_list:
        cat_counts[d.mismatch_category] = cat_counts.get(d.mismatch_category, 0) + 1

    return RelationshipAggregateDiagnostics(
        total_references=total_refs,
        baseline_exact_accuracy=exact_matches / total_refs,
        tuple_micro_precision=p,
        tuple_micro_recall=r,
        tuple_micro_f1=f1,
        type_only_micro_precision=tp,
        type_only_micro_recall=tr,
        type_only_micro_f1=tf1,
        expected_empty_count=exp_empty_cnt,
        predicted_empty_count=pred_empty_cnt,
        true_empty_matches=true_empty,
        false_positives_on_empty=fp_empty,
        missing_on_non_empty=missing_non_empty,
        correct_type_wrong_target_count=correct_type_wrong_targ,
        mismatch_category_counts=dict(sorted(cat_counts.items())),
    )


# ── Execution Runner ───────────────────────────────────────────────────────────


def execute_b_t1a_experiment(
    *,
    outcomes_path: str | Path | None = None,
    reference_corpus_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> BT1AExperimentResult:
    """Execute B-T1A Scope and Relationship Error Decomposition.

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

    # 1. Load and hash-verify committed frozen outcomes fail-closed
    outcomes = load_stage_b_outcomes(out_p)
    manifest = Manifest.load(man_p)
    all_refs = load_reference_corpus(ref_dir)

    scope_outcomes = {o.candidate_id: o for o in outcomes if o.task_type == ClassifierTaskType.SCOPE}
    rel_outcomes = {o.candidate_id: o for o in outcomes if o.task_type == ClassifierTaskType.RELATIONSHIPS}

    # 2. Evaluate all 100 reference decisions
    ref_scope_diags: list[ReferenceScopeDiagnostic] = []
    ref_rel_diags: list[ReferenceRelationshipDiagnostic] = []

    for ref in all_refs:
        cid = ref.reference_decision_id
        ref_scope_diags.append(diagnose_reference_scope(ref, scope_outcomes[cid]))
        ref_rel_diags.append(diagnose_reference_relationship(ref, rel_outcomes[cid]))

    # Sort deterministically
    ref_scope_diags.sort(key=lambda d: d.reference_id)
    ref_rel_diags.sort(key=lambda d: d.reference_id)

    # 3. Global aggregates
    global_scope = aggregate_scope_diagnostics(ref_scope_diags)
    global_rel = aggregate_relationship_diagnostics(ref_rel_diags)

    # 4. By-repository aggregates
    repo_scope: dict[str, ScopeAggregateDiagnostics] = {}
    repo_rel: dict[str, RelationshipAggregateDiagnostics] = {}

    for repo_cfg in manifest.repositories:
        s_diags = [d for d in ref_scope_diags if d.repository == repo_cfg.github]
        r_diags = [d for d in ref_rel_diags if d.repository == repo_cfg.github]
        repo_scope[repo_cfg.id] = aggregate_scope_diagnostics(s_diags)
        repo_rel[repo_cfg.id] = aggregate_relationship_diagnostics(r_diags)

    # 5. By-sampling-category aggregates
    sampling_categories = sorted({r.sampling_category for r in all_refs})
    sample_scope: dict[str, ScopeAggregateDiagnostics] = {}
    sample_rel: dict[str, RelationshipAggregateDiagnostics] = {}

    for scat in sampling_categories:
        s_diags = [d for d in ref_scope_diags if d.sampling_category == scat]
        r_diags = [d for d in ref_rel_diags if d.sampling_category == scat]
        sample_scope[scat] = aggregate_scope_diagnostics(s_diags)
        sample_rel[scat] = aggregate_relationship_diagnostics(r_diags)

    profile_hash = compute_b_t1a_profile_hash()

    result = BT1AExperimentResult(
        experiment_id=EXPERIMENT_ID,
        baseline_id=FROZEN_BASELINE_ID,
        parent_main_sha=FROZEN_PARENT_MAIN_SHA,
        reference_corpus_hash=FROZEN_REFERENCE_CORPUS_HASH,
        semantic_content_hash=FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH,
        experiment_profile_hash=profile_hash,
        global_scope_diagnostics=global_scope,
        global_relationship_diagnostics=global_rel,
        per_repository_scope=repo_scope,
        per_repository_relationship=repo_rel,
        per_sampling_category_scope=sample_scope,
        per_sampling_category_relationship=sample_rel,
        reference_scope_diagnostics=ref_scope_diags,
        reference_relationship_diagnostics=ref_rel_diags,
    )

    # 6. Write deterministic artifacts
    if output_dir is not None:
        out_dir_path = Path(output_dir)
        summary_file = out_dir_path / "b_t1a_summary.json"
        summary_file.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        diagnostics_file = out_dir_path / "b_t1a_diagnostics.jsonl"
        lines: list[str] = []
        for s_d, r_d in zip(ref_scope_diags, ref_rel_diags):
            rec = {
                "reference_id": s_d.reference_id,
                "repository": s_d.repository,
                "sampling_category": s_d.sampling_category,
                "scope_diagnostic": s_d.to_dict(),
                "relationship_diagnostic": r_d.to_dict(),
            }
            lines.append(json.dumps(rec, sort_keys=True, separators=(",", ":")))
        diagnostics_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return result

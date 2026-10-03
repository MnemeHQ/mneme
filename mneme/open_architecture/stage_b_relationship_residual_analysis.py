"""
mneme.open_architecture.stage_b_relationship_residual_analysis — Deterministic O1A Arm B Residual Analysis.

Implements the deterministic residual-error decomposition of the 41 remaining
failures from O1A B-T1C Arm B evaluated against Batch 01 v0.2-grounding.

Architecture & Boundary Invariants:
- Research-only diagnostic: does NOT alter benchmark scoring contracts or formulas.
- Does NOT alter frozen treatment validator or treatment execution semantics.
- Reuses frozen harness and baseline loader authorities without modification.
- Zero model/API/network calls: strictly offline evaluation over committed frozen outcomes.
- Deterministic: byte-identical decomposition across runs.
- Two-layer diagnosis:
  1. Layer 1 (Reference level): mutually exclusive structural classification (32 + 2 + 3 + 4 = 41).
  2. Layer 2 (Tuple level): deterministic evidence-context and prediction-behaviour tagging.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from mneme.open_architecture.classification import (
    ClassifierTaskType,
    normalize_relationships,
)
from mneme.open_architecture.export import compute_reference_corpus_content_hash
from mneme.open_architecture.harness import (
    FrozenReferenceDecision,
    load_reference_corpus,
)
from mneme.open_architecture.stage_b_baseline import (
    FrozenClassifierOutcome,
)
from mneme.open_architecture.stage_b_relationship_diagnostic_experiment import (
    classify_target_form,
    is_adr_visible_in_text,
    parse_adr_alias,
)
from mneme.open_architecture.stage_b_relationship_treatment_experiment import (
    ARM_B_ID,
    B_T1C_PROFILE_B_HASH,
    compute_treatment_semantic_content_hash,
    load_treatment_outcomes,
)

EXPERIMENT_ID: str = "b-t1c-relationship-treatment"
ARM_ID: str = ARM_B_ID
FROZEN_EXECUTION_REFERENCE_CORPUS_HASH: str = "0455bd66aae52551c35b37a63c2d185f"
FROZEN_SCORING_REFERENCE_CORPUS_HASH: str = "700a569e24bf90707ba14ff65eea2ab5"
FROZEN_ARM_B_PROFILE_HASH: str = B_T1C_PROFILE_B_HASH
FROZEN_ARM_B_OUTCOMES_SEMANTIC_HASH: str = (
    "sha256:778f05574d0e835fca893c216c4e240c15e0f30a11893812089dc691b3376092"
)

# ── Layer 1 Structural Classes ────────────────────────────────────────────────

STRUCTURAL_EXPECTED_EMPTY_FALSE_POSITIVE: str = "EXPECTED_EMPTY_FALSE_POSITIVE"
STRUCTURAL_PURE_TYPE_CONFUSION: str = "PURE_TYPE_CONFUSION"
STRUCTURAL_EXACT_EXPECTED_PLUS_EXTRAS: str = "EXACT_EXPECTED_PLUS_EXTRAS"
STRUCTURAL_TYPE_CONFUSION_PLUS_EXTRAS: str = "TYPE_CONFUSION_PLUS_EXTRAS"

ORDERED_STRUCTURAL_CLASSES: tuple[str, ...] = (
    STRUCTURAL_EXPECTED_EMPTY_FALSE_POSITIVE,
    STRUCTURAL_PURE_TYPE_CONFUSION,
    STRUCTURAL_EXACT_EXPECTED_PLUS_EXTRAS,
    STRUCTURAL_TYPE_CONFUSION_PLUS_EXTRAS,
)

# ── Layer 2 Evidence Context Tags ─────────────────────────────────────────────

CTX_CONTEXTUAL_RELATED_METADATA: str = "contextual_related_metadata"
CTX_LIFECYCLE_REVISION_HISTORY: str = "lifecycle_revision_history"
CTX_NARRATIVE_BODY: str = "narrative_body"
CTX_UNRESOLVED: str = "unresolved"

ORDERED_EVIDENCE_CONTEXT_TAGS: tuple[str, ...] = (
    CTX_CONTEXTUAL_RELATED_METADATA,
    CTX_LIFECYCLE_REVISION_HISTORY,
    CTX_NARRATIVE_BODY,
    CTX_UNRESOLVED,
)

# Orthogonal human adjudication tag
ADJUDICATION_ONTOLOGY_GAP: str = "adjudicated_ontology_gap"

# ── Layer 2 Prediction Behaviour Tags ─────────────────────────────────────────

BEHAVIOUR_DEPENDS_ON_OVERPRODUCTION: str = "depends_on_overproduction"
BEHAVIOUR_WRONG_TYPE_RECOVERY: str = "wrong_type_recovery"
BEHAVIOUR_CONFLICTING_TYPE_EXTRA: str = "conflicting_type_extra"
BEHAVIOUR_TARGET_BOUNDARY_ANOMALY: str = "target_boundary_anomaly"
BEHAVIOUR_EXTRA_RELATIONSHIP: str = "extra_relationship"

ORDERED_PREDICTION_BEHAVIOUR_TAGS: tuple[str, ...] = (
    BEHAVIOUR_DEPENDS_ON_OVERPRODUCTION,
    BEHAVIOUR_WRONG_TYPE_RECOVERY,
    BEHAVIOUR_CONFLICTING_TYPE_EXTRA,
    BEHAVIOUR_TARGET_BOUNDARY_ANOMALY,
    BEHAVIOUR_EXTRA_RELATIONSHIP,
)

# References explicitly supported by committed human adjudication as ontology gaps
ADJUDICATED_ONTOLOGY_GAP_REFERENCE_IDS: frozenset[str] = frozenset({"ref-helix-020"})

# Regex patterns for mechanical evidence location
RE_RELATED_METADATA: re.Pattern[str] = re.compile(
    r"(?:\*\*Related:\*\*|Relates to\b|relatesTo:|\bRelated:\b)",
    re.IGNORECASE,
)
RE_LIFECYCLE_MARKER: re.Pattern[str] = re.compile(
    r"(?:Amended by|Superseded by|Partially superseded|Update \([^)]+\)|refined by|reverses the|retire the)",
    re.IGNORECASE,
)


def normalize_whitespace(text: str) -> str:
    """Collapse contiguous whitespace into single space."""
    return " ".join(text.split())


def strip_markdown_decorations(text: str) -> str:
    """Normalize markdown links and formatting characters for robust text matching."""
    # [link text](url) -> link text
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Strip markdown bold, italics, code delimiters, blockquotes, headers
    t = re.sub(r"[*_`>#]", "", t)
    # Standardize unicode quotation marks
    t = (
        t.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )
    return normalize_whitespace(t)


def classify_reference_structure(
    expected_tuples: set[tuple[str, str | None]],
    predicted_tuples: set[tuple[str, str | None]],
) -> str:
    """Mechanically derive Layer 1 mutually exclusive reference structural class.

    Definitions:
    - EXPECTED_EMPTY_FALSE_POSITIVE: E is empty, P is non-empty.
    - EXACT_EXPECTED_PLUS_EXTRAS: E is non-empty, E is strict subset of P (|P| > |E|).
    - PURE_TYPE_CONFUSION: E is non-empty, target entities match 1:1, |P| == |E|, but E != P.
    - TYPE_CONFUSION_PLUS_EXTRAS: E is non-empty, E not subset of P, and extra tuples emitted.
    """
    if len(expected_tuples) == 0:
        if len(predicted_tuples) > 0:
            return STRUCTURAL_EXPECTED_EMPTY_FALSE_POSITIVE
        raise ValueError("classify_reference_structure is only called on failing references (E != P)")

    exp_targets = {t[1] for t in expected_tuples}
    pred_targets = {t[1] for t in predicted_tuples}

    if expected_tuples.issubset(predicted_tuples) and len(predicted_tuples) > len(expected_tuples):
        return STRUCTURAL_EXACT_EXPECTED_PLUS_EXTRAS

    if exp_targets == pred_targets and len(expected_tuples) == len(predicted_tuples):
        return STRUCTURAL_PURE_TYPE_CONFUSION

    return STRUCTURAL_TYPE_CONFUSION_PLUS_EXTRAS


def detect_evidence_context(
    reference_id: str,
    target_ref: str | None,
    evidence_ref: str | None,
    raw_evidence: str,
) -> tuple[str, str]:
    """Mechanically establish observable source context for an emitted tuple.

    Returns:
        tuple of (evidence_context_tag, evidence_location)

    Tags:
    - contextual_related_metadata: Evidence located in Related:/Relates to/relatesTo block.
    - lifecycle_revision_history: Evidence located in explicit lifecycle/revision marker.
    - narrative_body: Evidence located in ordinary body prose.
    - unresolved: Evidence cannot be uniquely located in raw_evidence without speculation.
    """
    if not evidence_ref or not evidence_ref.strip():
        return CTX_UNRESOLVED, "missing_evidence"

    raw_lines = raw_evidence.splitlines()
    target_line_idx = -1
    ev_norm = normalize_whitespace(evidence_ref)

    # 1. Exact or whitespace-normalized line search (fail-closed on multiple matches)
    s1_candidates = [
        idx for idx, line in enumerate(raw_lines)
        if ev_norm in normalize_whitespace(line)
    ]
    if len(s1_candidates) == 1:
        target_line_idx = s1_candidates[0]
    elif len(s1_candidates) > 1:
        return CTX_UNRESOLVED, "ambiguous_normalized_line_match"

    # 2. Search for clauses / parts across lines (fail-closed on multiple matches)
    if target_line_idx == -1:
        clauses = [
            normalize_whitespace(c)
            for c in re.split(r"\s*(?:\.\.\.|\s/\s|;)\s*", ev_norm)
            if len(normalize_whitespace(c)) >= 10
        ]
        if clauses:
            s2_candidates = set()
            clause_ambiguous = False
            for c in clauses:
                c_find = (
                    c[4:]
                    if c.startswith("ADR [")
                    else (c[11:] if c.startswith("Relates to [") else c)
                )
                c_matches = [
                    idx for idx, line in enumerate(raw_lines)
                    if c_find in normalize_whitespace(line)
                ]
                if len(c_matches) > 1:
                    clause_ambiguous = True
                    break
                elif len(c_matches) == 1:
                    s2_candidates.add(c_matches[0])
            if clause_ambiguous or len(s2_candidates) > 1:
                return CTX_UNRESOLVED, "ambiguous_clause_match"
            if len(s2_candidates) == 1:
                target_line_idx = next(iter(s2_candidates))

    # 3. Clean markdown line search (fail-closed on multiple matches)
    if target_line_idx == -1:
        clean_ev = strip_markdown_decorations(evidence_ref)
        s3_candidates = [
            idx for idx, line in enumerate(raw_lines)
            if clean_ev in strip_markdown_decorations(line)
        ]
        if len(s3_candidates) == 1:
            target_line_idx = s3_candidates[0]
        elif len(s3_candidates) > 1:
            return CTX_UNRESOLVED, "ambiguous_clean_line_match"

    # 4. Multi-line search across raw_evidence (fail-closed on multiple matches)
    if target_line_idx == -1:
        clean_raw = strip_markdown_decorations(raw_evidence)
        clean_ev = strip_markdown_decorations(evidence_ref)
        pos_matches = [m.start() for m in re.finditer(re.escape(clean_ev), clean_raw)]
        if len(pos_matches) == 1:
            first_phrase = " ".join(clean_ev.split()[:3])
            s4_candidates = [
                idx for idx, line in enumerate(raw_lines)
                if first_phrase in strip_markdown_decorations(line)
            ]
            if len(s4_candidates) == 1:
                target_line_idx = s4_candidates[0]
            elif len(s4_candidates) > 1:
                return CTX_UNRESOLVED, "ambiguous_multiline_match"
        elif len(pos_matches) > 1:
            return CTX_UNRESOLVED, "ambiguous_multiline_match"

    # 5. Search by target reference in line with supporting context words (fail-closed on multiple matches)
    if target_line_idx == -1 and target_ref is not None:
        target_str = str(target_ref)
        stopwords = {
            "candidate",
            "evidence",
            "decision",
            "document",
            "section",
            "about",
            "which",
            "there",
            "their",
            "where",
        }
        ev_words = [
            w.lower()
            for w in re.findall(r"\b[a-zA-Z]{5,}\b", evidence_ref)
            if w.lower() not in stopwords
        ]
        if ev_words:
            s5_candidates = []
            for idx, line in enumerate(raw_lines):
                if target_str in line:
                    line_lower = line.lower()
                    matching_words = [w for w in ev_words if w in line_lower]
                    if len(matching_words) >= 2:
                        s5_candidates.append(idx)
            if len(s5_candidates) == 1:
                target_line_idx = s5_candidates[0]
            elif len(s5_candidates) > 1:
                return CTX_UNRESOLVED, "ambiguous_target_context_match"

    # Unresolved if not located
    if target_line_idx == -1:
        return CTX_UNRESOLVED, "unresolved"

    matched_line = raw_lines[target_line_idx]

    # Find the paragraph boundary around target_line_idx
    p_start = target_line_idx
    while p_start > 0 and raw_lines[p_start - 1].strip() and not raw_lines[p_start - 1].startswith("#"):
        p_start -= 1
    p_end = target_line_idx
    while p_end < len(raw_lines) - 1 and raw_lines[p_end + 1].strip() and not raw_lines[p_end + 1].startswith("#"):
        p_end += 1

    preceding_lines = "\n".join(raw_lines[p_start : target_line_idx + 1])

    # 1. Related metadata check: line itself, or paragraph starting with Related/Relates to
    if RE_RELATED_METADATA.search(matched_line):
        return CTX_CONTEXTUAL_RELATED_METADATA, f"related_metadata_line_{target_line_idx}"
    if RE_RELATED_METADATA.search(preceding_lines):
        return CTX_CONTEXTUAL_RELATED_METADATA, f"related_metadata_paragraph_{p_start}"

    # 2. Lifecycle marker check: line itself, or preceding lines in paragraph
    if RE_LIFECYCLE_MARKER.search(matched_line):
        return CTX_LIFECYCLE_REVISION_HISTORY, f"lifecycle_marker_line_{target_line_idx}"
    if RE_LIFECYCLE_MARKER.search(preceding_lines):
        return CTX_LIFECYCLE_REVISION_HISTORY, f"lifecycle_marker_paragraph_{p_start}"

    return CTX_NARRATIVE_BODY, f"narrative_body_line_{target_line_idx}"


def diagnose_predicted_tuple(
    rel_type: str,
    target_ref: str | None,
    evidence_ref: str | None,
    expected_tuples: set[tuple[str, str | None]],
    expected_targets: dict[str, str],
    all_predicted_tuples: set[tuple[str, str | None]],
    reference_id: str,
    raw_evidence: str,
) -> dict[str, Any]:
    """Diagnose an individual predicted relationship tuple."""
    tuple_key = (rel_type, target_ref)
    target_form = classify_target_form(target_ref)
    parsed_alias = parse_adr_alias(target_ref)

    # Prediction behaviour tagging and role resolution
    behaviour_tags: list[str] = []

    # Check exact match vs extra
    if tuple_key in expected_tuples:
        tuple_role = "exact_match"
    else:
        tuple_role = "extra_tuple"
        behaviour_tags.append(BEHAVIOUR_EXTRA_RELATIONSHIP)
        if rel_type == "depends_on":
            behaviour_tags.append(BEHAVIOUR_DEPENDS_ON_OVERPRODUCTION)

    # Check expected target status
    if target_ref in expected_targets:
        exp_type = expected_targets[target_ref]
        if (exp_type, target_ref) in all_predicted_tuples:
            # Expected tuple was already recovered with correct type; conflicting extra type emitted
            if rel_type != exp_type:
                tuple_role = "conflicting_type_extra"
                behaviour_tags.append(BEHAVIOUR_CONFLICTING_TYPE_EXTRA)
        else:
            # Expected target recovered, but no prediction for it has the expected type
            tuple_role = "wrong_type_target"
            behaviour_tags.append(BEHAVIOUR_WRONG_TYPE_RECOVERY)

    # target_boundary_anomaly: null target or non-canonical representation
    if target_ref is None or parsed_alias is None or target_ref != parsed_alias:
        behaviour_tags.append(BEHAVIOUR_TARGET_BOUNDARY_ANOMALY)

    # Evidence context detection (strictly mechanical)
    ev_context_tag, ev_location = detect_evidence_context(
        reference_id, target_ref, evidence_ref, raw_evidence
    )

    causal_tags = [ev_context_tag] + behaviour_tags

    return {
        "causal_tags": causal_tags,
        "evidence_context_tag": ev_context_tag,
        "evidence_location": ev_location,
        "evidence_reference": evidence_ref,
        "parsed_adr_alias": parsed_alias,
        "prediction_behaviour_tags": behaviour_tags,
        "relationship_type": rel_type,
        "target_form": target_form,
        "target_reference": target_ref,
        "tuple_role": tuple_role,
    }


def run_residual_error_analysis(
    references: list[FrozenReferenceDecision],
    treatment_outcomes: list[FrozenClassifierOutcome],
) -> dict[str, Any]:
    """Execute complete deterministic residual-error decomposition over v0.2."""
    if len(references) != 100:
        raise ValueError(f"Expected exactly 100 references, got {len(references)}")
    if len(treatment_outcomes) != 100:
        raise ValueError(f"Expected exactly 100 treatment outcomes, got {len(treatment_outcomes)}")

    refs_map = {r.reference_decision_id: r for r in references}
    outcomes_map = {o.candidate_id: o for o in treatment_outcomes}

    passing_references: list[str] = []
    failing_records: list[dict[str, Any]] = []

    structural_class_counts: dict[str, int] = {sc: 0 for sc in ORDERED_STRUCTURAL_CLASSES}
    evidence_context_counts: dict[str, int] = {ec: 0 for ec in ORDERED_EVIDENCE_CONTEXT_TAGS}
    prediction_behaviour_counts: dict[str, int] = {pb: 0 for pb in ORDERED_PREDICTION_BEHAVIOUR_TAGS}
    predicted_type_counts: dict[str, int] = {}
    target_type_confusion_matrix: dict[str, dict[str, int]] = {}

    total_expected_target_count = 0
    recovered_target_entity_count = 0
    exact_type_exact_target_count = 0
    wrong_type_target_count = 0

    ontology_gap_ref_count = 0

    # Evaluate all 100 reference decisions
    for ref_id in sorted(refs_map.keys()):
        ref = refs_map[ref_id]
        outcome = outcomes_map[ref_id]

        exp_set = {(r["relationship_type"], r.get("target_reference")) for r in ref.relationships}
        exp_targets_dict = {
            r.get("target_reference"): r["relationship_type"]
            for r in ref.relationships
            if r.get("target_reference") is not None
        }

        norm_rels = normalize_relationships(outcome.output.get("relationships", []))
        pred_set = {(r.relationship_type, r.target_reference) for r in norm_rels}
        pred_targets_dict = {
            r.target_reference: r.relationship_type
            for r in norm_rels
            if r.target_reference is not None
        }

        # Track target attribution and confusion matrix
        for r in ref.relationships:
            total_expected_target_count += 1
            e_type = r["relationship_type"]
            e_targ = r.get("target_reference")

            if e_type not in target_type_confusion_matrix:
                target_type_confusion_matrix[e_type] = {}

            if (e_type, e_targ) in pred_set:
                recovered_target_entity_count += 1
                exact_type_exact_target_count += 1
                target_type_confusion_matrix[e_type][e_type] = (
                    target_type_confusion_matrix[e_type].get(e_type, 0) + 1
                )
            elif e_targ in pred_targets_dict:
                recovered_target_entity_count += 1
                wrong_type_target_count += 1
                p_type = pred_targets_dict[e_targ]
                target_type_confusion_matrix[e_type][p_type] = (
                    target_type_confusion_matrix[e_type].get(p_type, 0) + 1
                )
            else:
                target_type_confusion_matrix[e_type]["unrecovered"] = (
                    target_type_confusion_matrix[e_type].get("unrecovered", 0) + 1
                )

        if exp_set == pred_set:
            passing_references.append(ref_id)
            continue

        # Failure record decomposition
        structural_class = classify_reference_structure(exp_set, pred_set)
        structural_class_counts[structural_class] += 1

        exact_tuples = sorted(list(exp_set & pred_set))
        missing_tuples = sorted(list(exp_set - pred_set))
        extra_tuples = sorted(list(pred_set - exp_set))

        # Target entities recovered in this reference
        recovered_targets = sorted(list(set(exp_targets_dict.keys()) & set(pred_targets_dict.keys())))

        # Wrong type mappings and conflicting type extras
        wrong_type_mappings: list[dict[str, Any]] = []
        conflicting_type_extra_mappings: list[dict[str, Any]] = []

        for targ, e_type in sorted(exp_targets_dict.items()):
            if targ in pred_targets_dict:
                if (e_type, targ) in pred_set:
                    # Target was recovered with correct type; check for conflicting extra predictions
                    for p_type, p_targ in sorted(pred_set):
                        if p_targ == targ and p_type != e_type:
                            conflicting_type_extra_mappings.append({
                                "conflicting_predicted_type": p_type,
                                "expected_type": e_type,
                                "target_reference": targ,
                            })
                else:
                    # Target recovered, but no prediction has the expected type
                    wrong_type_mappings.append({
                        "expected_type": e_type,
                        "predicted_type": pred_targets_dict[targ],
                        "target_reference": targ,
                    })

        # Tuple diagnostics
        tuple_diagnostics: list[dict[str, Any]] = []
        ref_context_counts: dict[str, int] = {}
        ref_behaviour_counts: dict[str, int] = {}

        is_ontology_gap = ref_id in ADJUDICATED_ONTOLOGY_GAP_REFERENCE_IDS
        if is_ontology_gap:
            ontology_gap_ref_count += 1

        for r in norm_rels:
            predicted_type_counts[r.relationship_type] = (
                predicted_type_counts.get(r.relationship_type, 0) + 1
            )
            diag = diagnose_predicted_tuple(
                rel_type=r.relationship_type,
                target_ref=r.target_reference,
                evidence_ref=r.evidence_reference,
                expected_tuples=exp_set,
                expected_targets=exp_targets_dict,
                all_predicted_tuples=pred_set,
                reference_id=ref_id,
                raw_evidence=ref.raw_evidence,
            )
            tuple_diagnostics.append(diag)

            c_tag = diag["evidence_context_tag"]
            evidence_context_counts[c_tag] = evidence_context_counts.get(c_tag, 0) + 1
            ref_context_counts[c_tag] = ref_context_counts.get(c_tag, 0) + 1

            for b_tag in diag["prediction_behaviour_tags"]:
                prediction_behaviour_counts[b_tag] = (
                    prediction_behaviour_counts.get(b_tag, 0) + 1
                )
                ref_behaviour_counts[b_tag] = ref_behaviour_counts.get(b_tag, 0) + 1

        record = {
            "adjudicated_ontology_gap": is_ontology_gap,
            "conflicting_type_extra_mappings": conflicting_type_extra_mappings,
            "exact_tuples": [list(t) for t in exact_tuples],
            "expected_tuples": [list(t) for t in sorted(list(exp_set))],
            "extra_tuples": [list(t) for t in extra_tuples],
            "missing_tuples": [list(t) for t in missing_tuples],
            "per_tuple_diagnostics": tuple_diagnostics,
            "predicted_tuples": [list(t) for t in sorted(list(pred_set))],
            "recovered_target_entities": recovered_targets,
            "reference_id": ref_id,
            "reference_structural_class": structural_class,
            "repository": ref.repository,
            "summary_counts": {
                "conflicting_type_extra_count": len(conflicting_type_extra_mappings),
                "evidence_context_counts": dict(sorted(ref_context_counts.items())),
                "exact_tuple_count": len(exact_tuples),
                "extra_tuple_count": len(extra_tuples),
                "missing_tuple_count": len(missing_tuples),
                "multi_relationship_overgeneration": len(extra_tuples) > 1,
                "prediction_behaviour_counts": dict(sorted(ref_behaviour_counts.items())),
                "total_predicted_tuples": len(norm_rels),
                "wrong_type_target_count": len(wrong_type_mappings),
            },
            "wrong_type_target_mappings": wrong_type_mappings,
        }
        failing_records.append(record)

    # Deterministic assertion of required invariants
    assert len(passing_references) == 59, f"Expected 59 passing, got {len(passing_references)}"
    assert len(failing_records) == 41, f"Expected 41 failures, got {len(failing_records)}"
    assert structural_class_counts[STRUCTURAL_EXPECTED_EMPTY_FALSE_POSITIVE] == 32
    assert structural_class_counts[STRUCTURAL_PURE_TYPE_CONFUSION] == 2
    assert structural_class_counts[STRUCTURAL_EXACT_EXPECTED_PLUS_EXTRAS] == 3
    assert structural_class_counts[STRUCTURAL_TYPE_CONFUSION_PLUS_EXTRAS] == 4
    assert (
        sum(structural_class_counts.values()) == 41
    ), "Structural classes must sum to 41"
    assert total_expected_target_count == 18, f"Expected 18 targets, got {total_expected_target_count}"
    assert (
        recovered_target_entity_count == 18
    ), f"Expected 18 recovered targets, got {recovered_target_entity_count}"
    assert (
        exact_type_exact_target_count == 12
    ), f"Expected 12 exact type targets, got {exact_type_exact_target_count}"
    assert (
        wrong_type_target_count == 6
    ), f"Expected 6 wrong type targets, got {wrong_type_target_count}"
    assert prediction_behaviour_counts[BEHAVIOUR_WRONG_TYPE_RECOVERY] == 6
    assert prediction_behaviour_counts[BEHAVIOUR_CONFLICTING_TYPE_EXTRA] == 1
    assert prediction_behaviour_counts[BEHAVIOUR_EXTRA_RELATIONSHIP] == 105
    assert prediction_behaviour_counts[BEHAVIOUR_DEPENDS_ON_OVERPRODUCTION] == 72
    assert prediction_behaviour_counts[BEHAVIOUR_TARGET_BOUNDARY_ANOMALY] == 2
    assert ontology_gap_ref_count == 1

    return {
        "adjudicated_ontology_gap_references": ontology_gap_ref_count,
        "arm_b_profile_hash": FROZEN_ARM_B_PROFILE_HASH,
        "arm_id": ARM_ID,
        "artifact_type": "b_t1c_arm_b_residual_error_decomposition_v0.2_grounding",
        "evidence_context_aggregate_counts": dict(sorted(evidence_context_counts.items())),
        "execution_reference_corpus_hash": FROZEN_EXECUTION_REFERENCE_CORPUS_HASH,
        "experiment_id": EXPERIMENT_ID,
        "failing_references": len(failing_records),
        "failures": failing_records,
        "model_calls": 0,
        "note": (
            "Deterministic offline residual-error decomposition re-scoring frozen Arm B "
            "outcomes against Batch 01 v0.2-grounding. This is a counterfactual diagnostic, "
            "not a new Arm B execution."
        ),
        "passing_references": len(passing_references),
        "prediction_behaviour_aggregate_counts": dict(sorted(prediction_behaviour_counts.items())),
        "scoring_reference_corpus_hash": FROZEN_SCORING_REFERENCE_CORPUS_HASH,
        "source_outcomes_semantic_hash": FROZEN_ARM_B_OUTCOMES_SEMANTIC_HASH,
        "structural_class_counts": structural_class_counts,
        "target_attribution_totals": {
            "conflicting_type_extra": prediction_behaviour_counts[BEHAVIOUR_CONFLICTING_TYPE_EXTRA],
            "exact_type_exact_target": exact_type_exact_target_count,
            "target_entity_recovered_any_type": recovered_target_entity_count,
            "total_expected_tuples": total_expected_target_count,
            "wrong_type_recovery": wrong_type_target_count,
        },
        "target_type_confusion_matrix": {
            k: dict(sorted(v.items())) for k, v in sorted(target_type_confusion_matrix.items())
        },
        "total_references": 100,
        "tuple_level_predicted_type_counts": dict(sorted(predicted_type_counts.items())),
    }


def write_residual_error_decomposition_v0_2(
    repo_root: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """Generate and write the v0.2 residual error decomposition artifact."""
    root = (
        repo_root
        if repo_root is not None
        else Path(__file__).resolve().parent.parent.parent
    )

    v02_ref_dir = (
        root
        / "benchmarks"
        / "open_architecture"
        / "batch_01"
        / "revisions"
        / "batch_01_v0.2-grounding"
        / "reference_decisions"
    )
    v02_hash = compute_reference_corpus_content_hash(v02_ref_dir)
    if v02_hash != FROZEN_SCORING_REFERENCE_CORPUS_HASH:
        raise ValueError(
            f"v0.2 scoring reference corpus hash mismatch: "
            f"expected {FROZEN_SCORING_REFERENCE_CORPUS_HASH}, computed {v02_hash}"
        )

    outcomes_path = (
        root
        / "benchmarks"
        / "open_architecture"
        / "batch_01"
        / "treatments"
        / "b_t1c"
        / "arm_b"
        / "outcomes.jsonl"
    )

    refs = load_reference_corpus(v02_ref_dir)
    outcomes = load_treatment_outcomes(
        outcomes_path,
        expected_reference_ids={r.reference_decision_id for r in refs},
    )

    semantic_hash = compute_treatment_semantic_content_hash(outcomes)
    if semantic_hash != FROZEN_ARM_B_OUTCOMES_SEMANTIC_HASH:
        raise ValueError(
            f"Arm B outcomes semantic hash mismatch: "
            f"expected {FROZEN_ARM_B_OUTCOMES_SEMANTIC_HASH}, computed {semantic_hash}"
        )

    result_dict = run_residual_error_analysis(refs, outcomes)

    out_file = (
        output_path
        if output_path is not None
        else (
            root
            / "benchmarks"
            / "open_architecture"
            / "batch_01"
            / "treatments"
            / "b_t1c"
            / "arm_b"
            / "residual_error_decomposition_v0.2_grounding.json"
        )
    )

    out_file.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(result_dict, indent=2, sort_keys=True) + "\n"
    out_file.write_bytes(serialized.encode("utf-8"))
    return out_file

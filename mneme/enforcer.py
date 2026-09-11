"""
enforcer.py — Pre-flight enforcement of Mneme decisions against a prompt.

Checks an input text against the decision corpus and returns a structured
result with PASS / WARN / FAIL verdict and per-violation details.

Retrieval and enforcement answer different questions. Retrieval asks "what
context is relevant?" -- a ranking question, where a top-N cutoff is right.
Enforcement asks "is this forbidden?" -- a safety question, where ranking is
wrong, because a violation does not stop being a violation when the filename
happens to share no token with the decision's scope. See ADR-017.

Severity semantics:
    A typed FORBID_LITERAL match is a FAIL.
    FAIL  — input contains a single-term anti-pattern term, or the complete
            ordered term sequence of a multi-term anti-pattern (ADR-017
            amendment, 2026-08-24).
    WARN  — input mentions a term that a "no X" constraint forbids.
    PASS  — no violations found.

Exit codes for the CLI:
    0 = PASS, 1 = WARN, 2 = FAIL
    Path applicability UNKNOWN is an operational exit 2, not a policy verdict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from mneme.decision_retriever import ScoredDecision
from mneme.path_selectors import (
    RuleEvaluation,
    SelectorOutcome,
    evaluate_path_selectors,
)
from mneme.rule_matcher import literal_in_text


class Severity(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class Violation:
    decision_id: str
    decision_text: str
    severity: Severity
    rule: str     # the constraint or anti_pattern string that triggered
    trigger: str  # the matched term (single-term rules) or the matched rule
                  # expression (multi-term phrase match). For a phrase match
                  # this is the rule's text as authored; it need not appear
                  # verbatim in the input, since separators normalize away.
    kind: str = "legacy"
    rule_type: str | None = None
    input_path: str | None = None
    selector: str | None = None


@dataclass
class EnforcementResult:
    verdict: Severity
    violations: list[Violation] = field(default_factory=list)
    applicability: list[RuleEvaluation] = field(default_factory=list)

    @property
    def evaluation_complete(self) -> bool:
        return not any(
            item.outcome == SelectorOutcome.UNKNOWN
            for item in self.applicability
        )


# Words that appear frequently in rule descriptions but carry no domain signal.
_RULE_STOPWORDS: frozenset[str] = frozenset({
    "add", "use", "not", "get", "set", "run", "and", "the",
    "for", "with", "into", "from", "that", "this", "will",
    "should", "would", "could", "make", "keep", "have",
})


def _rule_terms(text: str, min_len: int = 3) -> list[str]:
    """Extract significant terms from a rule phrase."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if len(w) >= min_len and w not in _RULE_STOPWORDS]


def _word_in_text(term: str, text: str) -> bool:
    """True if term appears as a whole word (case-insensitive) in text."""
    return bool(re.search(r"\b" + re.escape(term) + r"\b", text, re.IGNORECASE))


def _phrase_tokens(text: str) -> list[str]:
    """All lowercased alphanumeric tokens of a phrase, in order.

    Rule and input use exactly the same normalization: whitespace,
    underscores, hyphens, and punctuation separate tokens identically, and
    nothing is dropped -- stopwords and short tokens included. Every token in
    the rule is therefore required to occur in the input, so
    ``assume_awin_awin_us_same_source`` normalizes to the same sequence as
    "assume awin awin us same source", while "foo bar" can never satisfy a
    rule stating "foo and bar".
    """
    return re.findall(r"[a-z0-9]+", text.lower())


def _phrase_in_text(phrase: list[str], text: str) -> bool:
    """True if the complete ordered token sequence occurs contiguously.

    A multi-term legacy anti-pattern is prose describing a pattern, not a bag
    of independent forbidden words (ADR-017 amendment). Requiring the whole
    sequence together and in order prevents benign prose that merely contains
    one ordinary term -- `awin`, `live`, `content` -- from failing the check,
    while still matching the rule's canonical or identifier spelling.
    """
    if not phrase:
        return False
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    n = len(phrase)
    return any(tokens[i:i + n] == phrase for i in range(len(tokens) - n + 1))


def _top_nonzero(scored: list[ScoredDecision], top: int) -> list[ScoredDecision]:
    kept: list[ScoredDecision] = []
    seen: set[str] = set()
    for s in scored:
        if s.score <= 0:
            continue
        if s.decision.id in seen:
            continue
        seen.add(s.decision.id)
        kept.append(s)
        if len(kept) >= top:
            break
    return kept


def _is_literal_rule(text: str, min_len: int = 3) -> bool:
    """True when a rule reduces to exactly one significant term.

    For a one-term rule such as ``"psycopg2"`` or ``"no postgres"``, the
    term-matching below is indistinguishable from matching the rule's own
    literal text: there is no phrase to take apart and therefore no guess
    about which word carries the meaning. Those rules are safe to evaluate
    against every decision in the corpus.

    Multi-term rules are the opposite. ``"open() without encoding= in Python"``
    is prose describing a pattern. Treating its terms as independent forbidden
    words made any single occurrence -- a bare "open", "without", or "content"
    -- fail benign prose (#150, and the 2026-08 dogfood false positives).
    They stay retrieval-gated here, and since the ADR-017 amendment they
    additionally match only as a complete ordered phrase (see
    ``_phrase_in_text``), so the gated tier no longer fires on incidental
    tokens either.
    """
    return len(_rule_terms(text, min_len=min_len)) == 1


def _enforcement_scope(
    scored: list[ScoredDecision],
    top: int,
) -> list[tuple[ScoredDecision, bool]]:
    """Every decision to evaluate, paired with whether to restrict it.

    Enforcement is not a ranking question -- "is this forbidden?" has the same
    answer whether or not the filename happened to share a token with the
    decision's scope (#254). So the corpus is evaluated in two tiers:

    - the retrieval-gated tier (top-N, positive score) keeps its pre-#254
      behaviour and is checked against every rule it carries;
    - every remaining decision is checked against its unambiguous literal
      rules only.

    Returns ``(scored_decision, literal_rules_only)`` pairs, gated tier first,
    each decision appearing once.
    """
    gated = _top_nonzero(scored, top)
    gated_ids = {g.decision.id for g in gated}

    out: list[tuple[ScoredDecision, bool]] = [(g, False) for g in gated]
    seen: set[str] = set(gated_ids)
    for s in scored:
        if s.decision.id in seen:
            continue
        seen.add(s.decision.id)
        out.append((s, True))
    return out


def check_prompt(
    input_text: str,
    scored: list[ScoredDecision],
    top: int = 3,
    input_path: str | Path | None = None,
) -> EnforcementResult:
    """Check input_text against the decision corpus.

    Unambiguous literal rules are checked against every decision supplied,
    regardless of retrieval score; multi-term rules are checked only for the
    top-N retrieved decisions, and there they match their complete ordered
    term sequence rather than any single term (ADR-017 amendment). See
    ``_enforcement_scope``.

    Args:
        input_text: The prompt or content to validate.
        scored:     Pre-scored decisions (from DecisionRetriever.retrieve()),
                    sorted descending by score.
        top:        Size of the retrieval-gated tier. This bounds how many
                    decisions have their *multi-term* rules applied; it never
                    limits which decisions are enforced.
        input_path: Optional checked-file path. A typed rule does not enforce
                    against its declaring ADR or policy-memory source, both of
                    which must be able to contain the literal it defines.

    Returns:
        EnforcementResult with verdict and list of Violations.
    """
    violations: list[Violation] = []
    applicability: list[RuleEvaluation] = []

    for s, literal_only in _enforcement_scope(scored, top):
        d = s.decision

        for rule_index, rule in enumerate(d.rules):
            selection = evaluate_path_selectors(
                include_paths=rule.include_paths,
                exclude_paths=rule.exclude_paths,
                input_path=input_path,
                memory_path=d.memory_path,
                policy_paths=(d.source_path, d.memory_path),
            )
            applicability.append(RuleEvaluation(
                decision_id=d.id,
                rule_type=rule.type,
                rule_value=rule.value,
                rule_index=rule_index,
                path_scoped=rule.is_path_scoped,
                outcome=selection.outcome,
                input_path=selection.input_path,
                selector=selection.selector,
                reason=selection.reason,
            ))
            if (
                selection.outcome == SelectorOutcome.APPLIED
                and rule.type == "FORBID_LITERAL"
                and literal_in_text(rule.value, input_text)
            ):
                violations.append(Violation(
                    decision_id=d.id,
                    decision_text=d.decision,
                    severity=Severity.FAIL,
                    rule=rule.value,
                    trigger=rule.value,
                    kind="typed_rule",
                    rule_type=rule.type,
                    input_path=selection.input_path,
                    selector=selection.selector,
                ))

        for ap in d.anti_patterns:
            if literal_only and not _is_literal_rule(ap):
                continue
            if _is_literal_rule(ap):
                # One significant term: term matching and literal matching
                # coincide, so the pre-existing whole-word behaviour is kept.
                trigger = next(
                    (t for t in _rule_terms(ap) if _word_in_text(t, input_text)),
                    None,
                )
            else:
                # Multi-term: the complete ordered phrase must be present.
                if _phrase_in_text(_phrase_tokens(ap), input_text):
                    trigger = ap
                else:
                    trigger = None
            if trigger is not None:
                violations.append(Violation(
                    decision_id=d.id,
                    decision_text=d.decision,
                    severity=Severity.FAIL,
                    rule=ap,
                    trigger=trigger,
                    kind="anti_pattern",
                ))

        for constraint in d.constraints:
            # Only handle "no X" style constraints.
            m = re.match(r"^no\s+(.+)$", constraint.strip(), re.IGNORECASE)
            if not m:
                continue
            forbidden_phrase = m.group(1).strip()
            if literal_only and not _is_literal_rule(forbidden_phrase):
                continue
            for term in _rule_terms(forbidden_phrase, min_len=3):
                if _word_in_text(term, input_text):
                    violations.append(Violation(
                        decision_id=d.id,
                        decision_text=d.decision,
                        severity=Severity.WARN,
                        rule=constraint,
                        trigger=term,
                        kind="constraint",
                    ))
                    break

    if any(v.severity == Severity.FAIL for v in violations):
        verdict = Severity.FAIL
    elif violations:
        verdict = Severity.WARN
    else:
        verdict = Severity.PASS

    return EnforcementResult(
        verdict=verdict,
        violations=violations,
        applicability=applicability,
    )


# ── Governability Assessment ────────────────────────────────────────────────────────

from dataclasses import dataclass
from typing import Literal

GovernabilityTier = Literal["enforceable", "partial", "guidance"]


@dataclass(frozen=True)
class GovernabilityAssessment:
    """
    Mneme's authoritative assessment of a Decision's governability.

    This is the single source of truth for whether a Decision can be
    deterministically enforced. Consumers (audit workspace, CLI, etc.)
    MUST use this function rather than reimplementing Mneme's semantics.

    Enforcement tiers (matching Mneme's check_prompt behavior):

    - enforceable: Decision has at least one mechanically enforceable rule
      (typed FORBID_LITERAL rule, or single-term anti_pattern).
      These are always checked regardless of retrieval score.

    - partial: Decision has only multi-term anti_patterns or "no X" constraints.
      Multi-term anti_patterns are only enforced for top-N retrieved decisions.
      "no X" constraints produce WARN severity.

    - guidance: Decision has no mechanically enforceable rules at all.
      It exists for retrieval/context only.
    """
    decision_id: str
    tier: GovernabilityTier
    has_literal_rules: bool
    has_single_term_anti_patterns: bool
    has_multi_term_anti_patterns: bool
    has_no_constraints: bool
    applicable_paths: tuple[str, ...]  # paths where typed rules apply
    confidence: float  # 1.0 = fully enforceable, 0.7 = partial, 0.0 = guidance only


def assess_governability(decision: "Decision") -> GovernabilityAssessment:
    """
    Assess whether a Decision can be deterministically governed by Mneme.

    This is the authoritative implementation of Mneme's governability semantics.
    All external consumers (audit workspace, CLI, etc.) MUST call this function
    rather than reimplementing the logic.

    Args:
        decision: A Mneme Decision object (from schemas.py)

    Returns:
        GovernabilityAssessment with Mneme's authoritative verdict.
    """
    from mneme.schemas import Decision

    # Check typed FORBID_LITERAL rules (always enforced, FAIL severity)
    has_literal_rules = any(
        rule.type == "FORBID_LITERAL"
        for rule in decision.rules
    )

    # Check anti-patterns - determine which are single-term (always enforced)
    single_term_aps = []
    multi_term_aps = []
    for ap in decision.anti_patterns:
        if _is_literal_rule(ap):
            single_term_aps.append(ap)
        else:
            multi_term_aps.append(ap)

    has_single_term_anti_patterns = bool(single_term_aps)
    has_multi_term_anti_patterns = bool(multi_term_aps)

    # Check "no X" constraints (produce WARN severity)
    has_no_constraints = any(
        _rule_terms(c, min_len=3) for c in decision.constraints
        if re.match(r"^no\s+(.+)$", c.strip(), re.IGNORECASE)
    )

    # Collect paths from typed rules
    applicable_paths = set()
    for rule in decision.rules:
        if rule.include_paths:
            applicable_paths.update(rule.include_paths)

    # Determine tier and confidence based on Mneme's enforcement behavior
    if has_literal_rules or has_single_term_anti_patterns:
        # These are ALWAYS enforced regardless of retrieval score
        tier: GovernabilityTier = "enforceable"
        confidence = 1.0
    elif has_multi_term_anti_patterns or has_no_constraints:
        # Multi-term anti-patterns only enforced for top-N retrieved decisions
        # "no X" constraints produce WARN (not FAIL)
        tier = "partial"
        confidence = 0.7
    else:
        # No mechanically enforceable rules - retrieval/context only
        tier = "guidance"
        confidence = 0.0

    return GovernabilityAssessment(
        decision_id=decision.id,
        tier=tier,
        has_literal_rules=has_literal_rules,
        has_single_term_anti_patterns=has_single_term_anti_patterns,
        has_multi_term_anti_patterns=has_multi_term_anti_patterns,
        has_no_constraints=has_no_constraints,
        applicable_paths=tuple(sorted(applicable_paths)),
        confidence=confidence,
    )


# ── P1.2 Architecture Protection Audit ───────────────────────────────────────
#
# Classification of a Decision's protection state, distinct from runtime
# governability (assess_governability above). Governability asks "can Mneme
# enforce this today?"; the P1.2 audit asks "how much of this repository's
# deterministic architectural intent is already protected, and what remains?".
#
# Tier semantics (ADR-023; amends the P1.2 freeze in
# docs/plans/p1-2-architecture-audit-redesign.md after the first Design
# Partner diagnostic, sagarika29/ai-system-architect):
#   protected          a documented architectural decision for which Mneme
#                      has deterministically linked evidence that the
#                      decision is currently enforced — a typed
#                      FORBID_LITERAL rule, or external CI evidence whose
#                      failure is deterministically linked to detecting the
#                      forbidden token.
#   mneme_ready        a documented architectural decision that can be
#                      represented faithfully by an existing Mneme rule
#                      type, with sufficient scope/applicability
#                      information to activate it without inventing missing
#                      architectural intent (an explicit literal
#                      prohibition — single-term anti-pattern, single-term
#                      "no X" constraint, or an equivalently explicit
#                      quoted term ban stated by the decision text).
#   requires_modelling a documented architectural decision that appears
#                      deterministically enforceable in principle, but
#                      Mneme does not yet have an adequate rule type,
#                      sufficient structured scope, or another required
#                      representation mechanism.
#   guidance           a documented statement that is primarily advisory,
#                      explanatory, aspirational, preference-based, or
#                      inherently judgment-dependent and should not
#                      currently be represented as deterministic
#                      enforcement.
#
# Protection-evidence channels (deterministically linked evidence that the
# decision is currently enforced):
#   1. typed FORBID_LITERAL rule on the decision record;
#   2. verified external CI evidence on a literalizable token
#      (failure deterministically linked to detecting the token);
#   3. declared test evidence (ADR-024, PASSIVE): an explicit, human-
#      authored ``test_evidence`` declaration on the decision record.
#      Ordinary Audit validates declarations passively — selector
#      well-formedness, cross-decision ambiguity, SHA-pin staleness, and
#      test-file existence — and annotates them as
#      ``test:declared:<selector>``. A merely declared entry NEVER
#      protects: pytest invocation is arbitrary repository-code execution,
#      so Audit executes no repository-controlled code. The VERIFIED
#      state requires a trusted producer (CI-produced exact-SHA +
#      exact-selector ingestion — the next task).
#
# Semantic invariants (ADR-023, extended by ADR-024):
#   - Structure invariance: adding syntactic structure or a constraint
#     field MUST NOT, by itself, move a decision out of guidance. Intent is
#     judged from the decision text (prescriptive vs advisory language);
#     structured prohibition fields carry documented enforcement material
#     only for decisions whose text is not advisory.
#   - Guidance is evidence-independent: no enforcement-like evidence —
#     CI, test, or otherwise — ever upgrades a guidance decision.
#   - Guidance decisions never enter the protection-relevant denominator.
#   - mneme_ready always carries an explicit FORBID_LITERAL guardrail
#     description; a decision cannot be mneme_ready without one.
#   - Candidate external evidence (token mentioned in CI without failure
#     semantics) annotates but never upgrades a tier by itself.
#   - Test evidence protects only through a trusted verification producer
#     (ADR-024): declared evidence annotates but never protects, and
#     ordinary Audit executes no repository-controlled code — no pytest,
#     no conftest, no plugins, no test bodies (passive-Audit invariant).
#   - Deterministic output for identical inputs: classification is a pure
#     function of the decision record, the declared evidence, and
#     repository files.

AUDIT_SCHEMA = "mneme.audit/v1"

ProtectionTier = Literal["protected", "mneme_ready", "requires_modelling", "guidance"]


@dataclass(frozen=True)
class ProtectionDecisionReport:
    """P1.2 protection assessment of a single Decision."""

    id: str
    decision: str
    status: str
    intent: str  # "deterministic" | "guidance"
    protection_tier: ProtectionTier
    mneme_guardrail: str | None
    evidence_confidence: str  # "verified" | "candidate" | "none"
    evidence_sources: list[str]


@dataclass(frozen=True)
class ArchitectureProtectionReport:
    """Aggregate P1.2 report over a decision corpus.

    Percentages are exactly recomputable from ``decisions`` filtered to
    ``status == "active"``.
    """

    schema: str
    memory_path: str
    total_decisions: int
    decisions: list[ProtectionDecisionReport]
    protection_relevant: int
    protected: int
    mneme_ready: int
    requires_modelling: int
    guidance: int
    current_protection_pct: float
    # Compat metric (ADR-023): the unprotected deterministic opportunity —
    # numerically identical to ``protection_gap_pct`` and the exact
    # complement of ``current_protection_pct``; not an independent metric.
    identified_mneme_potential_pct: float
    protection_gap_pct: float


_NO_CONSTRAINT_RE = re.compile(r"^no\s+(.+)$", re.IGNORECASE)
_CI_ENFORCEMENT_RE = re.compile(r"exit\s+1")
# A guard runs only when detection SUCCEEDS: "<detect> && exit 1". The
# inverted form "<detect> || exit 1" fails when the token is ABSENT — an
# allow-list/requirement, not a prohibition — and must never verify.
_CI_LINKED_FAIL_RE = re.compile(r"&&\s*exit\s+1")
_CI_GUARD_OPENER_RE = re.compile(r"^\s*if\b")
_CI_GUARD_NEGATION_RE = re.compile(
    r"!\s*(?:grep|rg|findstr)|\bunless\b", re.IGNORECASE
)
_CI_GUARD_CLOSER = ("fi", "endif")
_CI_GUARD_WINDOW = 30


def _ci_verified_linkage(text: str, tokens: list[str]) -> bool:
    """True when failing the check is deterministically linked to detecting a token.

    Three conservative linkage shapes are recognised; anything else is
    candidate at best:

    - same line: ``<detection involving token> && exit 1`` — the guard runs
      only when the token is found. ``|| exit 1`` requires the token's
      PRESENCE (an allow-list) and is deliberately never verified.
    - single-line guard: ``if <detect token>; then ... exit 1 ...``.
    - guarded block: an ``if`` line whose condition involves the token opens
      a block and ``exit 1`` appears before the matching ``fi``/``endif``.

    Negated guards (``if ! grep ...``, ``unless ...``) fail when the token is
    absent — a requirement, not a prohibition — so they are never verified.
    An ``exit 1`` elsewhere in the workflow that no token line reaches is
    unrelated and never verifies.
    """
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if not any(_word_in_text(token, line) for token in tokens):
            continue

        # Same line: detection chained by && into a failing exit.
        if _CI_LINKED_FAIL_RE.search(line):
            return True

        # Single-line guard: `if <detect>; then ... exit 1 ...`.
        if (
            re.search(r"\bif\b", line, re.IGNORECASE)
            and re.search(r";\s*then\b", line, re.IGNORECASE)
            and _CI_ENFORCEMENT_RE.search(line)
            and not _CI_GUARD_NEGATION_RE.search(line)
        ):
            return True

        # Multi-line guard: `if <detect>; then` opens; exit 1 before `fi`.
        if _CI_GUARD_OPENER_RE.match(line) and not _CI_GUARD_NEGATION_RE.search(line):
            for follow in lines[idx + 1 : idx + 1 + _CI_GUARD_WINDOW]:
                stripped = follow.strip().lower()
                if stripped in _CI_GUARD_CLOSER:
                    break
                if _CI_GUARD_OPENER_RE.match(follow):
                    break
                if _CI_ENFORCEMENT_RE.search(follow):
                    return True
    return False


def _split_no_constraints(
    constraints: list[str],
) -> tuple[list[str], list[str]]:
    """Split "no X" constraints into (single-term literals, multi-term phrases).

    The single-term half yields the forbidden term itself — the token a
    FORBID_LITERAL guardrail would carry. Multi-term phrases need
    interpretation before they can be literalized.
    """
    single: list[str] = []
    multi: list[str] = []
    for constraint in constraints:
        m = _NO_CONSTRAINT_RE.match(constraint.strip())
        if not m:
            continue
        phrase = m.group(1).strip()
        if _is_literal_rule(phrase):
            terms = _rule_terms(phrase)
            if terms:
                single.append(terms[0])
        else:
            multi.append(phrase)
    return single, multi


# ── Semantic intent classification (ADR-023) ─────────────────────────────────
#
# The audit tier must track what the documented decision MEANS, not which
# structured fields happen to be populated (P0 finding #1 of the first
# Design Partner diagnostic: byte-identical decision text flipped guidance
# → requires_modelling when an unrelated structured constraint was added).
#
# Intent is therefore judged from the decision text itself:
#   - prescriptive language (obligation, requirement, prohibition — must,
#     never, reject, fail closed, forbidden, enforce, validate, "No X"
#     headlines) makes a decision protection-relevant regardless of which
#     structured fields are populated;
#   - advisory language (prefer, consider, should, can, where practical,
#     judgment, tradeoffs) marks the statement guidance, and no structured
#     field can upgrade it;
#   - structured prohibition fields (anti_patterns / "no X" constraints)
#     remain documented enforcement material for decisions whose text is
#     not advisory, preserving the frozen Mneme-ready guardrail derivation
#     for every pre-existing record shape.
#
# Both classifiers are deliberately conservative: prescriptive markers
# never fire on advisory wording, and absent markers default to guidance
# (silent text is never inferred to be deterministic). No repository- or
# partner-specific vocabulary is special-cased.

_ADVISORY_RE = re.compile(
    r"\b(?:prefer\w*|consider\w*|recommen\w+|should|ideally|optional|"
    r"flexible|judg(?:e|ment|ement)\w*|trade[- ]?off\w*|aspirational|"
    r"where\s+practical|when\s+possible|when\s+appropriate|"
    r"as\s+appropriate|as\s+needed|in\s+general|generally|typically|"
    r"usually|nice[- ]to[- ]have|may\b|might\b|can\b|could\b)\b",
    re.IGNORECASE,
)

_PRESCRIPTIVE_RE = re.compile(
    r"\b(?:must(?:\s+not)?|mustn't|shall(?:\s+not)?|required|requires|"
    r"require\b|mandatory|always|never|reject\w*|forbid\w*|banned|ban\b|"
    r"enforc\w*|validat\w*|fail\w*\s+closed?|fail-closed|do\s+not|don't|"
    r"cannot|can't|refuse\w*)\b",
    re.IGNORECASE,
)

_NO_HEADLINE_RE = re.compile(r"^\s*no\s+\S", re.IGNORECASE)

_QUOTED_TERM_BAN_RE = re.compile(
    r"\b(?:must\s+not|must\s+never|never|shall\s+not|do\s+not|don't|"
    r"forbidden|banned|prohibited|avoid|omit|no)\b"
    r"[^.;\n]{0,64}?"
    r"\b(?:terms?|words?|phrases?|literals?|strings?|tokens?|"
    r"keywords?|identifiers?)\b"
    r"[^\S\n]*[:\-]?[^\S\n]*"
    r"[`'\"\u201c\u2018]"
    r"([A-Za-z][A-Za-z0-9_-]{2,48})"
    r"[`'\"\u201d\u2019]?",
    re.IGNORECASE,
)


def _is_advisory_text(text: str) -> bool:
    """True when the decision text reads as advisory/preference wording."""
    return bool(_ADVISORY_RE.search(text))


def _is_prescriptive_text(text: str) -> bool:
    """True when the decision text states an obligation or prohibition."""
    return bool(_PRESCRIPTIVE_RE.search(text)) or bool(_NO_HEADLINE_RE.match(text))


def _headline_no_tokens(text: str) -> list[str]:
    """Tokens proposed by a leading "No <single term>" prohibition headline.

    The same derivation ``_split_no_constraints`` applies to a "no X"
    constraint, applied to the decision text's headline.
    """
    m = _NO_CONSTRAINT_RE.match(text.strip())
    if not m:
        return []
    phrase = m.group(1).strip()
    if _is_literal_rule(phrase):
        terms = _rule_terms(phrase)
        if terms:
            return [terms[0]]
    return []


def _text_literal_tokens(text: str) -> list[str]:
    """Literalizable tokens stated by the decision text itself.

    Two conservative, deterministic shapes are recognised:

    1. a leading ``No <single term>`` prohibition headline — exactly the
       derivation ``_split_no_constraints`` applies to a "no X" constraint;
    2. an explicitly quoted term prohibition ("must not use the term
       ``seamless``") — the quotes make the banned literal explicit, so a
       FORBID_LITERAL guardrail is faithful rather than invented.

    Anything else stays Requires-modelling: prose prohibitions that need
    interpretation are never literalized from text alone.
    """
    tokens: list[str] = []
    for match in _QUOTED_TERM_BAN_RE.finditer(text):
        token = match.group(1).lower()
        if token not in tokens:
            tokens.append(token)
    for token in _headline_no_tokens(text):
        if token not in tokens:
            tokens.append(token)
    return tokens


def _scan_ci_evidence(
    tokens: list[str],
    repo_root: str | Path | None,
) -> tuple[str, list[str]]:
    """Scan CI workflow files for enforcement evidence of the tokens.

    A workflow file mentioning a token counts as evidence. Evidence is
    ``verified`` only when failure of the check is deterministically linked
    to detecting the token (see ``_ci_verified_linkage``); a bare mention —
    including a token near an unrelated ``exit 1`` — is ``candidate``:
    annotated, never a tier upgrade on its own.
    """
    if repo_root is None or not tokens:
        return "none", []

    root = Path(repo_root)
    workflow_files: list[Path] = []
    gh_workflows = root / ".github" / "workflows"
    if gh_workflows.is_dir():
        workflow_files.extend(sorted(gh_workflows.glob("*.yml")))
        workflow_files.extend(sorted(gh_workflows.glob("*.yaml")))
    gitlab_ci = root / ".gitlab-ci.yml"
    if gitlab_ci.is_file():
        workflow_files.append(gitlab_ci)

    sources: list[str] = []
    verified = False
    candidate = False
    for workflow in workflow_files:
        try:
            text = workflow.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not any(_word_in_text(token, text) for token in tokens):
            continue
        if _ci_verified_linkage(text, tokens):
            verified = True
            sources.append(f"ci:verified:{workflow.name}")
        else:
            candidate = True
            sources.append(f"ci:candidate:{workflow.name}")

    if verified:
        return "verified", sources
    if candidate:
        return "candidate", sources
    return "none", []


def _proposed_literal_tokens(decision: "Decision") -> list[str]:
    """Literalizable tokens a Mneme guardrail could carry, canonical order.

    Exactly the derivation ``assess_protection`` uses to classify a decision
    ``mneme_ready``: the terms of each single-term anti-pattern, then the
    forbidden terms of single-term "no X" constraints, then tokens stated by
    the decision text itself (``_text_literal_tokens``), deduplicated in
    order. Kept beside the assessment so the proposal below and the
    classification above are the same computation, not two interpretations
    of it.
    """
    single_aps = [ap for ap in decision.anti_patterns if _is_literal_rule(ap)]
    single_nos, _ = _split_no_constraints(decision.constraints)
    tokens = [t for ap in single_aps for t in _rule_terms(ap)] + single_nos
    for token in _text_literal_tokens(decision.decision):
        if token not in tokens:
            tokens.append(token)
    return tokens


def propose_literal_rule(decision: "Decision") -> "Rule | None":
    """Materialize a decision's canonical deterministic guardrail as a Rule.

    Returns ``FORBID_LITERAL`` carrying the first literalizable token, with
    global applicability (ADR-019/ADR-020 semantics), when the decision's
    legacy intent can be literalized exactly as ``assess_protection`` does
    for a Mneme-ready decision; ``None`` when it cannot.

    This is a rule-materialization helper, not an assessor: it performs no
    tier classification and may return a rule for a decision whose canonical
    tier is not ``mneme_ready`` (for example one already carrying verified
    external evidence). Every caller MUST gate eligibility through
    :func:`assess_protection` — the single source of protection truth — and
    consult this function only for the concrete rule shape. Kept beside the
    assessment so the proposal and the classification are the same
    computation, not two interpretations of it.
    """
    from mneme.schemas import Rule

    tokens = _proposed_literal_tokens(decision)
    if not tokens:
        return None
    return Rule(type="FORBID_LITERAL", value=tokens[0])


def assess_protection(
    decision: "Decision",
    repo_root: str | Path | None = None,
    test_evidence_results: "dict[str, list] | None" = None,
) -> ProtectionDecisionReport:
    """Assess one Decision's P1.2 protection state.

    Tier resolution order (highest wins):

      1. typed FORBID_LITERAL rule  -> protected (verified enforcement)
      2. verified external CI evidence on a literalizable token -> protected
      3. trusted verified test evidence on a deterministic decision
         -> protected (ADR-024; no trusted verification producer exists
         in M0, so declared evidence annotates only)
      4. remaining deterministic intent -> mneme_ready or
         requires_modelling
      5. advisory or otherwise non-deterministic statement -> guidance
         (evidence-independent)

    Intent (deterministic vs guidance) is judged from the decision text
    (``_is_prescriptive_text`` / ``_is_advisory_text``), never from which
    structured fields happen to be populated (ADR-023 structure-invariance
    invariant). Structured prohibition fields still supply the concrete
    guardrail derivation, and they keep non-advisory decisions
    protection-relevant exactly as in the frozen P1.2 model.

    Test evidence (ADR-024) arrives passively validated in
    ``test_evidence_results`` (decision id -> verification records) or is
    validated inline for this decision when a repository root is given.
    Ordinary Audit never executes repository-controlled code: a merely
    declared entry annotates ``evidence_sources`` as
    ``test:declared:<selector>`` and never upgrades a tier; only a trusted
    verification producer (CI-produced exact-SHA + exact-selector result)
    may establish protection, and advisory decisions are never upgraded.
    """
    literal_rules = [
        rule for rule in decision.rules if rule.type == "FORBID_LITERAL"
    ]
    single_aps = [ap for ap in decision.anti_patterns if _is_literal_rule(ap)]
    multi_aps = [ap for ap in decision.anti_patterns if not _is_literal_rule(ap)]
    single_nos, multi_nos = _split_no_constraints(decision.constraints)

    if literal_rules:
        return ProtectionDecisionReport(
            id=decision.id,
            decision=decision.decision,
            status=decision.status,
            intent="deterministic",
            protection_tier="protected",
            mneme_guardrail=f"FORBID_LITERAL: {literal_rules[0].value}",
            evidence_confidence="verified",
            evidence_sources=[],
        )

    documented_enforcement = bool(
        single_aps or multi_aps or single_nos or multi_nos
    )
    advisory = _is_advisory_text(decision.decision)
    prescriptive = _is_prescriptive_text(decision.decision)

    has_deterministic_intent = prescriptive or (
        documented_enforcement and not advisory
    )

    if not has_deterministic_intent:
        return ProtectionDecisionReport(
            id=decision.id,
            decision=decision.decision,
            status=decision.status,
            intent="guidance",
            protection_tier="guidance",
            mneme_guardrail=None,
            evidence_confidence="none",
            evidence_sources=[],
        )

    # Declared test evidence (ADR-024), passively validated once per corpus
    # by the aggregate report; single-decision callers validate inline.
    # PASSIVE-AUDIT INVARIANT: no repository-controlled code is executed —
    # no pytest, no conftest, no plugins. Only a trusted verification
    # producer (none exists in M0) may carry the VERIFIED state.
    if repo_root is not None and test_evidence_results is None:
        from mneme.evidence import verify_test_evidence

        test_evidence_results = verify_test_evidence([decision], repo_root)
    test_sources: list[str] = []
    verified_by_test = False
    if test_evidence_results:
        from mneme.evidence import evidence_source_strings

        verifications = test_evidence_results.get(decision.id, [])
        test_sources = evidence_source_strings(verifications)
        verified_by_test = any(
            v.state == "verified" for v in verifications
        )

    tokens = _proposed_literal_tokens(decision)
    tier: ProtectionTier = "mneme_ready" if tokens else "requires_modelling"
    proposed_guardrail = f"FORBID_LITERAL: {tokens[0]}" if tokens else None

    evidence_confidence, evidence_sources = "none", []
    if repo_root is not None:
        evidence_confidence, evidence_sources = _scan_ci_evidence(
            tokens, repo_root
        )
        if evidence_confidence == "verified":
            tier = "protected"

    if verified_by_test:
        tier = "protected"
        evidence_confidence = "verified"

    return ProtectionDecisionReport(
        id=decision.id,
        decision=decision.decision,
        status=decision.status,
        intent="deterministic",
        protection_tier=tier,
        mneme_guardrail=proposed_guardrail,
        evidence_confidence=evidence_confidence,
        evidence_sources=[*test_sources, *evidence_sources],
    )


def generate_protection_report(
    decisions: list["Decision"],
    repo_root: str | Path | None = None,
) -> ArchitectureProtectionReport:
    """Assess a corpus and aggregate the P1.2 summary.

    Only active decisions count toward any tier or the protection-relevant
    denominator; superseded and deprecated decisions appear in ``decisions``
    for provenance but are excluded from all counts.

    Declared test evidence (ADR-024) is verified once for the whole corpus
    — enabling cross-decision ambiguity checks — and passed into every
    per-decision assessment.
    """
    test_evidence_results = None
    if repo_root is not None:
        from mneme.evidence import verify_test_evidence

        test_evidence_results = verify_test_evidence(decisions, repo_root)
    reports = [
        assess_protection(
            decision,
            repo_root=repo_root,
            test_evidence_results=test_evidence_results,
        )
        for decision in decisions
    ]
    active = [r for r in reports if r.status == "active"]
    protected = sum(1 for r in active if r.protection_tier == "protected")
    mneme_ready = sum(1 for r in active if r.protection_tier == "mneme_ready")
    requires_modelling = sum(
        1 for r in active if r.protection_tier == "requires_modelling"
    )
    guidance = sum(1 for r in active if r.protection_tier == "guidance")
    protection_relevant = protected + mneme_ready + requires_modelling

    # Metric formulas (ADR-023, exact numerator/denominator):
    #
    #   Current Protection          = P / PR × 100
    #       fraction of protection-relevant decisions with verified
    #       deterministic enforcement.
    #   Identified Mneme Potential  = (M + R) / PR × 100
    #       the UNPROTECTED DETERMINISTIC OPPORTUNITY: fraction of
    #       protection-relevant decisions whose documented meaning is
    #       deterministically enforceable in principle and not yet
    #       enforced — representable by an existing rule type today
    #       (Mneme-ready) or requiring richer modelling (Requires
    #       modelling). Guidance never enters the numerator or the
    #       denominator. This is numerically identical to the Protection
    #       Gap by construction and is the exact complement of Current
    #       Protection (Potential = 100 − Current Protection); it is NOT
    #       an independent second metric and user-facing output must not
    #       present the two as separate findings. A future, genuinely
    #       distinct metric may express immediately protectable coverage
    #       as (P + M) / PR, with Requires-modelling as the product gap.
    #   Protection Gap              = (M + R) / PR × 100
    #       the actionable shortfall — numerically identical to Potential
    #       by construction, framed as what remains rather than what
    #       Mneme could protect.
    current_protection = round(protected / protection_relevant * 100, 1) if protection_relevant else 0.0
    identified_potential = (
        round((mneme_ready + requires_modelling) / protection_relevant * 100, 1)
        if protection_relevant
        else 0.0
    )
    protection_gap = (
        round((mneme_ready + requires_modelling) / protection_relevant * 100, 1)
        if protection_relevant
        else 0.0
    )

    memory_path = decisions[0].memory_path if decisions else ""
    return ArchitectureProtectionReport(
        schema=AUDIT_SCHEMA,
        memory_path=memory_path,
        total_decisions=len(reports),
        decisions=reports,
        protection_relevant=protection_relevant,
        protected=protected,
        mneme_ready=mneme_ready,
        requires_modelling=requires_modelling,
        guidance=guidance,
        current_protection_pct=current_protection,
        identified_mneme_potential_pct=identified_potential,
        protection_gap_pct=protection_gap,
    )


# Export for external consumers
__all__ = [
    "Severity",
    "Violation",
    "EnforcementResult",
    "check_prompt",
    "GovernabilityAssessment",
    "GovernabilityTier",
    "assess_governability",
    "ProtectionTier",
    "ProtectionDecisionReport",
    "ArchitectureProtectionReport",
    "assess_protection",
    "generate_protection_report",
    "propose_literal_rule",
]

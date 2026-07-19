"""
retriever.py — Score and rank memory items and decision examples.

How retrieval works
-------------------
Retrieval is fully deterministic: same query + same memory file always
produces the same ContextPacket. No randomness, no learned weights,
no embeddings.

Scoring (per MemoryItem)
  content overlap: +1.0 per query token found in title + content text
  tag match:       +1.5 per query token that exactly matches a tag
  priority scale:  raw score × item.weight (high=1.5, medium=1.0, low=0.5)

Hard-constraint guarantee
  Items of type "rule" or "anti_pattern" receive a minimum score of 1.0
  so they are always present in the packet regardless of query relevance.
  Project-wide constraints should be injected into every call.

Fallback
  If no non-constraint items score above zero, the top 3 by weight are
  included in relevant_facts so the packet is never empty.
"""

from __future__ import annotations

import re

from mneme.schemas import (
    ContextPacket,
    DecisionExample,
    MemoryItem,
    ProjectMemory,
)

# Item types treated as hard constraints — always surfaced.
_CONSTRAINT_TYPES = {"rule", "anti_pattern"}

# Types that go into relevant_facts.
_FACT_TYPES = {"fact", "architecture_decision", "example"}

# Closing instruction appended to every formatted prompt.
_OUTPUT_GUIDANCE = (
    "Follow all rules and anti-patterns above without exception. "
    "Apply the preferred patterns where relevant. "
    "If your response touches a topic covered by a past decision, "
    "your answer must be consistent with that decision and its rationale."
)


def _tokenize(text: str) -> set[str]:
    """Split text into lowercase word tokens, ignoring punctuation.

    Tokens shorter than 3 characters are dropped to avoid noise from
    stop words and punctuation fragments.

    Args:
        text: Any plain text string.

    Returns:
        Set of lowercase tokens of length >= 3.
    """
    return {w for w in re.split(r"\W+", text.lower()) if len(w) >= 3}


def _score_item(item: MemoryItem, query_tokens: set[str]) -> float:
    """Compute a relevance score for one MemoryItem.

    Hard constraints (rule, anti_pattern) get a minimum score of 1.0 so
    they always surface in the packet regardless of query overlap.

    Args:
        item:         The MemoryItem to score.
        query_tokens: Tokenized query from _tokenize().

    Returns:
        A non-negative float. Higher means more relevant.
    """
    # Build the searchable text: title + content.
    content_tokens = _tokenize(f"{item.title} {item.content}")
    tag_tokens = {t.lower() for t in item.tags}

    # Keyword overlap in content.
    content_score = len(query_tokens & content_tokens) * 1.0

    # Exact tag match is a stronger signal than content overlap.
    tag_score = len(query_tokens & tag_tokens) * 1.5

    raw = content_score + tag_score

    # Hard constraints are always relevant to any call about this project.
    if item.type in _CONSTRAINT_TYPES:
        raw = max(raw, 1.0)

    return raw * item.weight


def _score_example(ex: DecisionExample, query_tokens: set[str]) -> float:
    """Compute a relevance score for one DecisionExample.

    Args:
        ex:           The DecisionExample to score.
        query_tokens: Tokenized query from _tokenize().

    Returns:
        A non-negative float.
    """
    content_tokens = _tokenize(f"{ex.task} {ex.decision} {ex.rationale}")
    tag_tokens = {t.lower() for t in ex.tags}

    content_score = len(query_tokens & content_tokens) * 1.0
    tag_score = len(query_tokens & tag_tokens) * 1.5

    return content_score + tag_score


class Retriever:
    """Scores project memory against a query and returns a ContextPacket.

    The packet separates memory into named sections so the context builder
    can render each one clearly and callers can inspect sections directly.

    Args:
        memory: A loaded ProjectMemory instance.
    """

    def __init__(self, memory: ProjectMemory) -> None:
        self.memory = memory

    def retrieve(
        self,
        query: str,
        max_patterns: int = 3,
        max_facts: int = 5,
        max_examples: int = 3,
    ) -> ContextPacket:
        """Score all memory items and return a structured ContextPacket.

        Hard constraints (rules + anti_patterns) are always included.
        Preferences, facts, and decision examples are ranked by score and
        capped at their respective maximums.

        If no fact-type items score above zero (no keyword overlap), the
        top 3 by priority weight are included as a fallback.

        Args:
            query:        The task description driving the LLM call.
            max_patterns: Maximum preferred_patterns to include.
            max_facts:    Maximum relevant_facts to include.
            max_examples: Maximum decision_examples to include.

        Returns:
            A ContextPacket ready for ContextBuilder.format().
        """
        query_tokens = _tokenize(query)

        # Score every item and sort descending.
        scored_items: list[tuple[MemoryItem, float]] = sorted(
            ((item, _score_item(item, query_tokens)) for item in self.memory.items),
            key=lambda x: x[1],
            reverse=True,
        )

        # ── Classify scored items into packet sections ─────────────────────

        hard_constraints: list[MemoryItem] = []
        preferred_patterns: list[MemoryItem] = []
        relevant_facts: list[MemoryItem] = []

        for item, score in scored_items:
            if item.type in _CONSTRAINT_TYPES:
                # Rules and anti_patterns always surface (min score guaranteed).
                hard_constraints.append(item)

            elif item.type == "preference" and score > 0:
                if len(preferred_patterns) < max_patterns:
                    preferred_patterns.append(item)

            elif item.type in _FACT_TYPES and score > 0:
                if len(relevant_facts) < max_facts:
                    relevant_facts.append(item)

        # Fallback: if nothing matched for facts, take the top items by weight.
        if not relevant_facts:
            fact_candidates = [
                item for item, _ in scored_items if item.type in _FACT_TYPES
            ]
            relevant_facts = sorted(
                fact_candidates, key=lambda i: i.weight, reverse=True
            )[:3]

        # ── Score and rank decision examples ──────────────────────────────

        scored_examples: list[tuple[DecisionExample, float]] = sorted(
            (
                (ex, _score_example(ex, query_tokens))
                for ex in self.memory.examples
            ),
            key=lambda x: x[1],
            reverse=True,
        )

        decision_examples = [
            ex for ex, score in scored_examples if score > 0
        ][:max_examples]

        # ── Assemble the packet ────────────────────────────────────────────

        meta = self.memory.meta
        project_summary = f"{meta.name}: {meta.description}"

        return ContextPacket(
            project_summary=project_summary,
            hard_constraints=hard_constraints,
            preferred_patterns=preferred_patterns,
            relevant_facts=relevant_facts,
            decision_examples=decision_examples,
            output_guidance=_OUTPUT_GUIDANCE,
            query=query,
        )

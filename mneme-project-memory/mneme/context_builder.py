"""
context_builder.py — Format a ContextPacket into an LLM system prompt.

The main entry point is format_context_packet(), a module-level helper
that wraps ContextBuilder.format() for convenience.

Output structure
----------------
  Project summary      — name + description, always first
  Hard Constraints     — rules + anti-patterns, always present
  Preferred Patterns   — query-matched preferences (omitted if empty)
  Relevant Context     — query-matched facts and decisions (omitted if empty)
  Past Decisions       — query-matched decision examples (omitted if empty)
  Output Guidance      — closing instruction, always last

The output is plain text compatible with any LLM provider. Pass it as
the ``system`` parameter of an API call.
"""

from __future__ import annotations

from mneme.decision_retriever import ScoredDecision  # noqa: F401  (re-exported type)
from mneme.schemas import ContextPacket, DecisionExample, MemoryItem


# ── Module-level helper ───────────────────────────────────────────────────────

def format_context_packet(packet: ContextPacket) -> str:
    """Format a ContextPacket into a prompt-ready system context string.

    Convenience wrapper around ``ContextBuilder().format(packet)``.

    Args:
        packet: The ContextPacket produced by Retriever.retrieve().

    Returns:
        A formatted string ready for use as an LLM system prompt.
    """
    return ContextBuilder().format(packet)


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_constraint(item: MemoryItem) -> str:
    """Format a rule or anti-pattern as a hard-constraint bullet."""
    label = "RULE" if item.type == "rule" else "AVOID"
    return f"  [{label}] {item.title}: {item.content}"


def _fmt_item(item: MemoryItem) -> str:
    """Format a preference, fact, or architecture decision as a bullet."""
    return f"  - {item.title}: {item.content}"


def _fmt_example(ex: DecisionExample) -> str:
    """Format a decision example as a three-line block."""
    return (
        f"  Situation:  {ex.task}\n"
        f"  Decision:   {ex.decision}\n"
        f"  Rationale:  {ex.rationale}"
    )


# ── ContextBuilder ────────────────────────────────────────────────────────────

class ContextBuilder:
    """Converts a ContextPacket into a formatted system prompt string.

    Sections are rendered in a fixed order. Empty sections are omitted
    so the prompt stays concise when the query has narrow relevance.

    Usage::

        packet = Retriever(memory).retrieve(query)
        prompt = ContextBuilder().format(packet)
        # or equivalently:
        prompt = format_context_packet(packet)
    """

    def format(self, packet: ContextPacket) -> str:
        """Render the packet as a plain-text system prompt.

        Args:
            packet: A ContextPacket from Retriever.retrieve().

        Returns:
            A multi-section string ready to pass as the LLM system prompt.
        """
        sections: list[str] = []

        # ── Mneme header ─────────────────────────────────────────────────
        sections.append(
            f"[Mneme project memory applied]\n\n"
            f"PROJECT: {packet.project_summary}\n"
            "Your response must follow the rules and decisions below."
        )

        # ── Rules — hard constraints, always present ──────────────────────
        if packet.hard_constraints:
            block = "\n".join(_fmt_constraint(c) for c in packet.hard_constraints)
            sections.append(f"RULES\n{block}")

        # ── Rules — preferred patterns (query-matched) ────────────────────
        if packet.preferred_patterns:
            block = "\n".join(_fmt_item(p) for p in packet.preferred_patterns)
            sections.append(f"PREFERRED\n{block}")

        # ── Context — query-matched facts and decisions ───────────────────
        if packet.relevant_facts:
            block = "\n".join(_fmt_item(f) for f in packet.relevant_facts)
            sections.append(f"CONTEXT\n{block}")

        # ── Examples — prior decisions with rationale ─────────────────────
        if packet.decision_examples:
            block = "\n\n".join(_fmt_example(e) for e in packet.decision_examples)
            sections.append(f"PRIOR DECISIONS\n{block}")

        # ── Output guidance — always last ──────────────────────────────────
        sections.append(f"OUTPUT GUIDANCE\n  {packet.output_guidance}")

        return "\n\n".join(sections)


# ── Decision-aware formatting (v2) ───────────────────────────────────────────

DEFAULT_MAX_DECISIONS = 3


def format_decisions(
    scored: list[ScoredDecision],
    max_items: int = DEFAULT_MAX_DECISIONS,
    min_score: float = 0.0,
) -> str:
    """Format the top-N scored decisions as a system-prompt fragment.

    Skips decisions with score <= ``min_score``. Deduplicates by decision id.
    Returns an empty string when no decisions qualify.

    Args:
        scored:    Pre-scored decisions from DecisionRetriever.retrieve().
                   Assumed to be sorted descending by score.
        max_items: Hard cap on number injected. Defaults to 3.
        min_score: Floor (exclusive) for inclusion. Defaults to 0.0, which
                   preserves the historical "skip score == 0" behavior.
                   Higher values let callers gate noisy retrievals.

    Returns:
        A formatted multi-section string, or "" if nothing qualifies.

    Raises:
        ValueError: if ``min_score`` is negative.
    """
    if min_score < 0.0:
        raise ValueError(f"min_score must be >= 0.0, got {min_score!r}")

    seen: set[str] = set()
    kept: list[ScoredDecision] = []
    for s in scored:
        if s.score <= min_score:
            continue
        if s.decision.id in seen:
            continue
        seen.add(s.decision.id)
        kept.append(s)
        if len(kept) >= max_items:
            break

    if not kept:
        return ""

    blocks: list[str] = ["[Mneme decisions applied]"]
    for s in kept:
        d = s.decision
        lines = [f"DECISION [{d.id}]: {d.decision}"]
        if d.rationale:
            lines.append(f"  Why:          {d.rationale}")
        if d.scope:
            lines.append(f"  Scope:        {', '.join(d.scope)}")
        if d.constraints:
            lines.append("  Constraints:")
            for c in d.constraints:
                lines.append(f"    - {c}")
        if d.anti_patterns:
            lines.append("  Avoid:")
            for a in d.anti_patterns:
                lines.append(f"    - {a}")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)

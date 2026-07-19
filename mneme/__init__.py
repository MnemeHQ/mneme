"""
Mneme — structured project memory for LLM calls.

This package provides the core pipeline for injecting project decisions
and constraints into LLM API calls so outputs remain consistent with
prior choices.

Typical usage::

    from mneme.memory_store import MemoryStore
    from mneme.retriever import Retriever
    from mneme.context_builder import ContextBuilder
    from mneme.llm_adapter import LLMAdapter
    from mneme.evaluator import Evaluator

See demo.py in the repo root for a full end-to-end example.
"""

__version__ = "0.1.0"

"""Integration-identity tests: the adapter must reuse, not copy, Mneme.

These tests pin the architectural boundary required by the issue:
no duplicated retrieval/enforcement semantics in the agent-sdk
integration.
"""

import ast
from pathlib import Path

ADAPTER = Path(__file__).resolve().parents[3] / "mneme" / "integrations" / "agent_sdk" / "adapter.py"

# Symbols that ARE the existing semantics. The adapter must import them,
# never redefine them.
REQUIRED_IMPORTS = [
    "introduced_content",
    "find_memory",
    "resolve_mode",
    "parse_verdict",
    "format_reason",
    "format_applicability_reason",
    "DecisionRetriever",
    "format_decisions",
    "MemoryStore",
]


def test_adapter_imports_existing_semantics():
    source = ADAPTER.read_text(encoding="utf-8")
    for name in REQUIRED_IMPORTS:
        assert name in source, f"adapter must reuse {name} from core"


def test_adapter_defines_no_matching_or_scoring_logic():
    """No tokenization/scoring/matching reimplementation may appear."""
    tree = ast.parse(ADAPTER.read_text(encoding="utf-8"))
    forbidden_tokens = (
        "SequenceMatcher",
        "get_opcodes",
        "re.compile",
        "re.search",
        "re.match",
        "\\.split()",  # bag-of-tokens style splitting
    )
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            names.add(f"re.{node.func.attr}")
    for token in ("SequenceMatcher", "get_opcodes"):
        assert token not in names, f"duplicated diff/matching logic: {token}"
    src = ADAPTER.read_text(encoding="utf-8")
    assert "import re" not in src, "adapter must not do regex rule matching"
    for bad in ("score =", "weight", "stopword"):
        assert bad not in src, f"duplicated retrieval scoring: {bad}"


def test_claude_code_hook_module_untouched_surface():
    """The Claude Code hook keeps its own entry points and constants."""
    from mneme.integrations.claude_code import hook

    for attr in (
        "main",
        "cli_main",
        "parse_event",
        "should_check",
        "materialize_proposed_content",
        "introduced_content",
        "find_memory",
        "resolve_mode",
        "parse_verdict",
        "format_reason",
    ):
        assert hasattr(hook, attr), f"hook surface changed: {attr}"

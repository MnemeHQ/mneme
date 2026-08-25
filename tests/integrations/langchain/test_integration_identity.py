"""Integration-identity tests: the langchain adapter must reuse, not copy.

No duplicated retrieval/enforcement semantics in the LangChain
integration. The gate is delegated to ``mneme.integrations.agent_sdk``
(translation-only, already pinned by its own identity tests), which in
turn imports the frozen pieces from the Claude Code hook module.
"""

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[3] / "mneme" / "integrations" / "langchain"
ADAPTER = PKG / "adapter.py"
MIDDLEWARE = PKG / "middleware.py"


def test_adapter_delegates_to_agent_sdk_gate():
    """The enforcement path must be delegation, never reimplementation."""
    source = ADAPTER.read_text(encoding="utf-8")
    assert "MnemeAgentSdk" in source, "adapter must delegate to the existing gate"
    assert "evaluate_mutation" in source
    assert "context_for_task" in source


def test_adapter_defines_no_matching_or_scoring_logic():
    """No tokenization/scoring/matching/diff reimplementation may appear."""
    tree = ast.parse(ADAPTER.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    for token in ("SequenceMatcher", "get_opcodes"):
        assert token not in names, f"duplicated diff/matching logic: {token}"
    src = ADAPTER.read_text(encoding="utf-8")
    assert "import re" not in src, "adapter must not do regex rule matching"
    assert "DecisionRetriever(" not in src.replace(
        "self._sdk.context_for_task", ""
    ), "retrieval must come from the delegated gate"
    for bad in ("score =", "weight", "stopword"):
        assert bad not in src, f"duplicated retrieval scoring: {bad}"


def test_middleware_module_has_no_governance_semantics():
    """Middleware translates verdicts; it must not import core surfaces."""
    src = MIDDLEWARE.read_text(encoding="utf-8")
    for forbidden in (
        "mneme.check",
        "subprocess",
        "introduced_content",
        "parse_verdict",
        "format_reason",
        "find_memory",
        "resolve_mode",
    ):
        assert forbidden not in src, f"middleware must not implement: {forbidden}"


def test_tool_mapping_is_closed_and_explicit():
    from mneme.integrations.langchain import LANGCHAIN_FILE_TOOLS

    assert LANGCHAIN_FILE_TOOLS == {"write_file": "Write", "edit_file": "Edit"}


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

"""Integration-identity checks for the OpenCode S1 adapter.

The adapter must reuse the shared Mneme semantics and must not implement its own
matcher, resolver, diff, checker parser or policy engine.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BRIDGE = REPO / "mneme" / "integrations" / "opencode" / "bridge.py"
PLUGIN = REPO / "integrations" / "opencode-plugin" / "index.ts"

REQUIRED_IMPORTS = {
    "ToolEvent",
    "_direct_write_memory_start",
    "_invoke_check",
    "assess_verdict",
    "resolve_mode",
    "classify_observation",
    "resolve_memory",
    "MemoryStore",
    "rule_id_for",
}


def test_bridge_imports_shared_semantics():
    source = BRIDGE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.name)
    missing = REQUIRED_IMPORTS - imported
    assert not missing, f"bridge must import shared semantics: {sorted(missing)}"


def test_bridge_does_not_reimplement_matching_or_diffing():
    source = BRIDGE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    definitions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    assert "introduced_between" not in definitions
    assert "SequenceMatcher" not in source
    assert "difflib" not in source
    assert "psycopg2" not in source
    assert "FORBID_LITERAL" not in source
    assert "def match" not in source


def test_plugin_is_transport_only():
    source = PLUGIN.read_text(encoding="utf-8")
    assert 'ctx.tool.hook("execute.before"' in source
    assert 'event?.tool !== "write"' in source
    assert 'decision === "block"' in source
    assert "NOT_PROTECTED" in source
    assert "spawn(" in source
    assert "writeFile" not in source
    assert "appendFile" not in source
    assert "node:fs" not in source
    assert "mneme check" not in source
    assert "applicability" not in source
    assert "violations" not in source


def test_plugin_declares_the_s1_identity():
    source = PLUGIN.read_text(encoding="utf-8")
    assert 'id: "mneme.opencode.s1"' in source
    assert "export default {" in source

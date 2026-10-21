"""Shared vocabulary for the P0-A offline prototype detectors M1 to M3.

Every detector is a pure function from (source text, target path) to one
finding per sub-constraint. Detectors only parse source (``tokenize``,
``ast``); none of them executes, imports or evaluates the proposed content,
calls a model or touches the network (charter sections 3.6 and 4).

These are offline prototypes for a validation experiment. Nothing here is
imported by ``mneme/``, the hook, the CLI, CI or a benchmark suite, and no
result produced with them is shipped enforcement (charter section 7).
"""

import ast
import json
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

VIOLATION = "VIOLATION"
NO_VIOLATION = "NO_VIOLATION"
UNEVALUATED = "UNEVALUATED"
VERDICTS = (VIOLATION, NO_VIOLATION, UNEVALUATED)

SUB_CONSTRAINTS = ("C1", "C2", "C3")
DECISION_ID = "ADR-001"
SCOPE_GLOB = "src/**"

TEMPLATE_JSON = Path(__file__).resolve().parents[1] / "set1" / "template" / "template.json"


def load_template() -> dict:
    """The frozen template declarations (symbols, handler types, bounds)."""
    return json.loads(TEMPLATE_JSON.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Finding:
    verdict: str
    reason: str
    lines: tuple = field(default_factory=tuple)

    def __post_init__(self):
        if self.verdict not in VERDICTS:
            raise ValueError(f"unknown verdict {self.verdict!r}")

    def as_dict(self) -> dict:
        return {"verdict": self.verdict, "reason": self.reason, "lines": list(self.lines)}


def not_targeted(method_id: str) -> Finding:
    return Finding(UNEVALUATED, f"NOT_TARGETED: {method_id} does not assess this sub-constraint")


def in_scope(target_path: str) -> bool:
    """The decision's Python surface: a ``.py`` file under ``src/**``."""
    return target_path.endswith(".py") and fnmatch(target_path, SCOPE_GLOB)


def out_of_scope(target_path: str) -> dict:
    reason = f"OUT_OF_SCOPE_PATH: {target_path} is not a Python file under {SCOPE_GLOB}"
    return {sc: Finding(UNEVALUATED, reason) for sc in SUB_CONSTRAINTS}


def gate_finding(audit: Finding, introduced_lines: set) -> Finding:
    """Answer the ADR-018 introduced-delta question from a whole-file finding.

    The detector runs over the resulting file so that tokens and syntax are
    read in context; the gate then keeps only what the edit introduced:

    - no introduced lines: the gate has nothing to inspect, so the result is
      ``UNEVALUATED``. The shipped hook proceeds on such an edit (ADR-018
      section 5), so a violation here is never reported as stopped;
    - a ``VIOLATION`` whose evidence touches an introduced line stays a
      ``VIOLATION``;
    - a ``VIOLATION`` whose evidence lies only on pre-existing lines is not
      the edit's: ``NO_VIOLATION`` for the gate (ADR-018 section 1);
    - ``UNEVALUATED`` and ``NO_VIOLATION`` carry over unchanged.
    """
    if not introduced_lines:
        return Finding(UNEVALUATED, "GATE_NO_INTRODUCED_LINES: deletion-only edit; the ADR-018 gate has nothing to inspect")
    if audit.verdict == VIOLATION:
        touched = tuple(sorted(set(audit.lines) & introduced_lines))
        if touched:
            return Finding(VIOLATION, f"GATE_INTRODUCED: {audit.reason}", touched)
        return Finding(NO_VIOLATION, f"GATE_PRE_EXISTING_ONLY: {audit.reason}", audit.lines)
    return Finding(audit.verdict, f"GATE_CARRIED: {audit.reason}", audit.lines)


def bindings(tree: ast.Module, name: str) -> list:
    """Every node anywhere in the module that binds ``name``."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, (ast.Store, ast.Del)):
            out.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            out.append(node)
        elif isinstance(node, (ast.Global, ast.Nonlocal)) and name in node.names:
            out.append(node)
        elif isinstance(node, ast.alias) and (node.asname or node.name.split(".")[0]) == name:
            out.append(node)
        elif isinstance(node, ast.arg) and node.arg == name:
            out.append(node)
        elif isinstance(node, ast.ExceptHandler) and node.name == name:
            out.append(node)
    return out

"""M2: static deadline bound (charter section 4).

Parses the file with ``ast`` and evaluates two deadline sources:

- the module-level assignment to the declared constant (``ROUTER_DEADLINE_S``);
- the deadline argument (second positional) of every ``classify(...)`` call.
  An argument that is the bare declared constant resolves to the module value.

Recognized value forms, and nothing else:

- a literal ``int`` or ``float``;
- constant folding of literal arithmetic: unary ``+``/``-`` and binary
  ``+ - * / // % **`` over recognized numeric operands (``bool`` operands are
  not folded; ``**`` with an exponent above 64 in magnitude, division by zero
  and overflow are not folded);
- a literal that is a disabled form under the frozen template's bounds:
  ``None`` or any non-numeric literal (``bool``, ``str``, ...).

Any other expression (a name other than the declared constant, a call such as
``float("inf")``, a conditional expression, an attribute) is ``UNEVALUATED``,
as is a source that rebinds the constant or ``classify`` anywhere else, a
call with starred or missing arguments, or a ``classify`` that escapes as a
value. M2 never folds by executing code.

Classification follows ``deadline_bounds`` in the frozen template: ``None``,
non-numeric, zero, negative, infinite or NaN is disabled (C1); above the
inclusive maximum is a C2 violation. A disabled deadline is reported under C1
only and C2 is ``NO_VIOLATION`` for it, following owner ruling AMB-1 (C2 not
separately assessed; this is not a compliance claim, and the C1 verdict still
fails the decision).
"""

import ast
import math
import operator

from .common import (
    NO_VIOLATION,
    UNEVALUATED,
    VIOLATION,
    Finding,
    bindings,
    in_scope,
    load_template,
    not_targeted,
    out_of_scope,
)

METHOD_ID = "M2"
METHOD_VERSION = "p0a-m2-static-bound/1.0.0"

MAX_EXPONENT = 64
_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

DISABLED, EXCEEDS, WITHIN, UNKNOWN = "DISABLED", "EXCEEDS", "WITHIN", "UNKNOWN"


class _Unrecognized(Exception):
    """An expression outside M2's recognized forms."""


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def fold(node: ast.AST):
    """Fold a recognized literal expression to a Python value, or raise."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
        operand = fold(node.operand)
        if not _is_number(operand):
            raise _Unrecognized("unary operator on a non-numeric literal")
        return _UNARYOPS[type(node.op)](operand)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left, right = fold(node.left), fold(node.right)
        if not (_is_number(left) and _is_number(right)):
            raise _Unrecognized("arithmetic on a non-numeric literal")
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise _Unrecognized("exponent outside the folding limit")
        try:
            return _BINOPS[type(node.op)](left, right)
        except (ZeroDivisionError, OverflowError) as e:
            raise _Unrecognized(type(e).__name__) from e
    raise _Unrecognized(f"{type(node).__name__} is not a recognized literal form")


def classify_value(value, maximum: float) -> str:
    if not _is_number(value) or value <= 0 or math.isinf(value) or math.isnan(value):
        return DISABLED
    if value > maximum:
        return EXCEEDS
    return WITHIN


def _module_constant(tree: ast.Module, name: str):
    """(source, expr node or None, reason). source is None if absent."""
    found = bindings(tree, name)
    if not found:
        return None, None, "absent"
    top = [
        stmt for stmt in tree.body
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Name) and stmt.targets[0].id == name
    ]
    if len(found) != 1 or len(top) != 1:
        return "constant", None, f"{name} is bound {len(found)} time(s), not once by a simple module-level assignment"
    return "constant", top[0], "single module-level assignment"


def _classify_calls(tree: ast.Module, classifier: str):
    """(calls, problem). ``classify`` must only appear as a direct call target."""
    calls = []
    func_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == classifier:
            calls.append(node)
            func_ids.add(id(node.func))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == classifier and id(node) not in func_ids:
            return calls, f"{classifier} is used other than as a direct call"
    return calls, None


def detect(source: str, target_path: str) -> dict:
    if not in_scope(target_path):
        return out_of_scope(target_path)
    template = load_template()
    constant_name = template["symbols"]["deadline_constant"]
    classifier = template["symbols"]["classifier_parameter"]
    maximum = float(template["deadline_bounds"]["maximum_inclusive"])

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        reason = f"PARSE_ERROR: {type(e).__name__}"
        return {"C1": Finding(UNEVALUATED, reason), "C2": Finding(UNEVALUATED, reason), "C3": not_targeted(METHOD_ID)}

    # (label, class, line, detail) for each deadline source
    sources = []

    present, assign, why = _module_constant(tree, constant_name)
    constant_class = None
    if present and assign is None:
        sources.append(("module_constant", UNKNOWN, None, why))
        constant_class = (UNKNOWN, None)
    elif present:
        try:
            value = fold(assign.value)
            cls = classify_value(value, maximum)
            sources.append(("module_constant", cls, assign.lineno, f"{constant_name} = {value!r}"))
            constant_class = (cls, value)
        except _Unrecognized as e:
            sources.append(("module_constant", UNKNOWN, assign.lineno, str(e)))
            constant_class = (UNKNOWN, None)

    calls, problem = _classify_calls(tree, classifier)
    if problem:
        sources.append(("classify_call", UNKNOWN, None, problem))
    if not calls:
        sources.append(("classify_call", UNKNOWN, None, f"no direct {classifier}(...) call found"))
    for call in calls:
        label = f"classify_call@{call.lineno}"
        starred = any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords)
        if starred or len(call.args) < 2:
            sources.append((label, UNKNOWN, call.lineno, "deadline argument is not the second positional argument"))
            continue
        arg = call.args[1]
        if isinstance(arg, ast.Name) and arg.id == constant_name:
            if constant_class is None:
                sources.append((label, UNKNOWN, call.lineno, f"{constant_name} has no module-level value"))
            else:
                cls, value = constant_class
                line_detail = f"{constant_name} resolves to {value!r}" if cls != UNKNOWN else f"{constant_name} is unevaluated"
                lines = (call.lineno, assign.lineno) if assign is not None else (call.lineno,)
                sources.append((label, cls, lines, line_detail))
            continue
        try:
            value = fold(arg)
            sources.append((label, classify_value(value, maximum), call.lineno, f"literal deadline {value!r}"))
        except _Unrecognized as e:
            sources.append((label, UNKNOWN, call.lineno, str(e)))

    def lines_for(cls: str) -> tuple:
        out = set()
        for _, c, line, _ in sources:
            if c == cls and line is not None:
                out.update(line if isinstance(line, tuple) else (line,))
        return tuple(sorted(out))

    def details(cls: str) -> str:
        return "; ".join(f"{label}: {d}" for label, c, _, d in sources if c == cls)

    classes = {c for _, c, _, _ in sources}
    if DISABLED in classes:
        c1 = Finding(VIOLATION, f"DISABLED_DEADLINE: {details(DISABLED)}", lines_for(DISABLED))
    elif UNKNOWN in classes:
        c1 = Finding(UNEVALUATED, f"UNRECOGNIZED_FORM: {details(UNKNOWN)}", lines_for(UNKNOWN))
    else:
        c1 = Finding(NO_VIOLATION, f"ALL_SOURCES_RECOGNIZED_NOT_DISABLED: {details(WITHIN) or details(EXCEEDS)}")

    if EXCEEDS in classes:
        c2 = Finding(VIOLATION, f"DEADLINE_EXCEEDS_MAXIMUM: {details(EXCEEDS)}", lines_for(EXCEEDS))
    elif UNKNOWN in classes:
        c2 = Finding(UNEVALUATED, f"UNRECOGNIZED_FORM: {details(UNKNOWN)}", lines_for(UNKNOWN))
    elif DISABLED in classes:
        c2 = Finding(NO_VIOLATION, "DISABLED_ATTRIBUTED_TO_C1: not separately assessed under C2 (AMB-1); not a compliance claim")
    else:
        c2 = Finding(NO_VIOLATION, f"WITHIN_MAXIMUM: {details(WITHIN)}")
    return {"C1": c1, "C2": c2, "C3": not_targeted(METHOD_ID)}

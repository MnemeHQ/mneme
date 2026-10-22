"""
numeric_rule.py — ``FORBID_NUMERIC_ABOVE`` (ADR-034, G1 whole-file audit).

One deterministic typed rule: a Python static, inclusive numeric upper bound,
evaluated only against a verified complete source file. This module owns the
whole contract so every layer shares one definition:

- the canonical ``Rule.value`` (ADR-034 §5, P1): ``canonical_json`` of a
  versioned object, with ``max`` stored as canonical decimal text, never as
  a float;
- strict validation of that value, used at authoring and again at load, which
  never rewrites persisted content;
- the matcher (ADR-034 §3-§6, charter §5): parse only with the pinned
  runtime's ``ast``, fold a closed set of literal arithmetic with CPython
  ``int``/binary64 semantics, and compare the runtime value exactly against
  the authored decimal bound as ``Fraction(x) > Fraction(max)``.

Source text is never imported or executed. Every declared source is required
(O2): an absent, ambiguous or unrecognized source is ``UNKNOWN`` with a
reason, never a silent pass. Matcher uncertainty is a per-rule status and is
never expressed as ADR-020 path ``UNKNOWN``.
"""
from __future__ import annotations

import ast
import json
import keyword
import math
import operator
import platform
import re
import warnings
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from typing import Any


RULE_TYPE = "FORBID_NUMERIC_ABOVE"

# ADR-034 §5 / O3: the v2 semantic feature that persisted numeric rules need.
SEMANTIC_FEATURE = "numeric_upper_bound_rule"

CONTRACT_VERSION = 1

# ── Authoring and canonical grammar (ADR-034 §5) ─────────────────────────────

# Checked on the raw YAML scalar text before type construction.
MAX_AUTHORING_RE = re.compile(r"^(0|[1-9][0-9]{0,17})(\.[0-9]{1,9})?$")
# The stored canonical form; the loader re-validates it and never rewrites.
MAX_CANONICAL_RE = re.compile(r"^(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$")
_MAX_INT_DIGITS = 18
_MAX_FRACTION_DIGITS = 9

_CONTRACT_KEYS = frozenset({
    "v", "language", "symbol", "call", "max", "inclusive", "unit",
})
_CALL_KEYS = frozenset({"function", "position"})

# ── Matcher vocabulary (ADR-034 §4) ──────────────────────────────────────────

STATUS_RECOGNIZED = "RECOGNIZED"
STATUS_PARTIAL = "PARTIAL"
STATUS_UNEVALUATED = "MATCHER_UNEVALUATED"
MATCHER_STATUSES = frozenset({
    STATUS_RECOGNIZED, STATUS_PARTIAL, STATUS_UNEVALUATED,
})
INCOMPLETE_STATUSES = frozenset({STATUS_PARTIAL, STATUS_UNEVALUATED})

OUTCOME_VIOLATION = "VIOLATION"
OUTCOME_NO_VIOLATION = "NO_VIOLATION"
OUTCOME_UNEVALUATED = "UNEVALUATED"
MATCHER_OUTCOMES = frozenset({
    OUTCOME_VIOLATION, OUTCOME_NO_VIOLATION, OUTCOME_UNEVALUATED,
})

REASON_INCOMPLETE_SOURCE_INPUT = "INCOMPLETE_SOURCE_INPUT"
REASON_PARSE_FAILURE = "PARSE_FAILURE"
REASON_AMBIGUOUS_BINDING = "AMBIGUOUS_BINDING"
REASON_SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
REASON_UNRECOGNIZED_FORM = "UNRECOGNIZED_FORM"
# ADR-034 §4 reason priority: the first applicable reason is primary.
REASON_PRIORITY: tuple[str, ...] = (
    REASON_INCOMPLETE_SOURCE_INPUT,
    REASON_PARSE_FAILURE,
    REASON_AMBIGUOUS_BINDING,
    REASON_SOURCE_NOT_FOUND,
    REASON_UNRECOGNIZED_FORM,
)
MATCHER_REASONS = frozenset(REASON_PRIORITY)

SOURCE_KIND_SYMBOL = "symbol"
SOURCE_KIND_CALL = "call"
SOURCE_KIND_INPUT = "input"    # the input contract, decided before parsing
SOURCE_KIND_MODULE = "module"  # the whole file failed to parse
SOURCE_KINDS = frozenset({
    SOURCE_KIND_SYMBOL, SOURCE_KIND_CALL, SOURCE_KIND_INPUT, SOURCE_KIND_MODULE,
})

# ADR-034 §5a operand and result bounds.
_INT_MAGNITUDE_LIMIT = 10 ** 30
_POW_EXPONENT_LIMIT = 64

STRICT_COMPARISON_NOTE = (
    "compared exactly: the runtime value must not exceed the authored decimal "
    "bound; no implicit tolerance or rounding applies, so a float literal "
    "spelled like a non-dyadic bound (for example 0.1) can exceed it"
)


def runtime_label() -> str:
    """The interpreter that defines the pinned grammar and numeric semantics."""
    return f"{platform.python_implementation()} {platform.python_version()}"


# ── Contract ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NumericContract:
    """The authored ``FORBID_NUMERIC_ABOVE`` contract (ADR-034 §2).

    ``call_function``/``call_position`` are both set or both ``None``; at
    least one of ``symbol`` and the call is declared. ``max`` is canonical
    decimal text.
    """

    max: str
    unit: str
    symbol: str | None = None
    call_function: str | None = None
    call_position: int | None = None
    language: str = "python"
    inclusive: bool = True

    def as_object(self) -> dict[str, Any]:
        obj: dict[str, Any] = {
            "v": CONTRACT_VERSION,
            "language": self.language,
            "max": self.max,
            "inclusive": self.inclusive,
            "unit": self.unit,
        }
        if self.symbol is not None:
            obj["symbol"] = self.symbol
        if self.call_function is not None:
            obj["call"] = {
                "function": self.call_function,
                "position": self.call_position,
            }
        return obj

    def canonical_value(self) -> str:
        """ADR-034 §5: the canonical serialized ``Rule.value``."""
        from mneme.rule_identity import canonical_json

        return canonical_json(self.as_object())

    def describe(self) -> str:
        """Render the contract in human terms, never as raw JSON (P1 gate 6)."""
        sources: list[str] = []
        if self.symbol is not None:
            sources.append(f"module-level {self.symbol}")
        if self.call_function is not None:
            sources.append(
                f"positional argument {self.call_position} (0-based) of "
                f"direct {self.call_function}(...) calls"
            )
        return (
            f"{' and '.join(sources)} must not exceed {self.max} {self.unit} "
            "(inclusive)"
        )


class NumericContractError(ValueError):
    """A ``FORBID_NUMERIC_ABOVE`` contract or stored value is invalid."""


def is_identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.isidentifier()
        and not keyword.iskeyword(value)
    )


def canonicalize_max(raw_text: str) -> str:
    """Validate authored ``max`` raw scalar text and return canonical text.

    Normalization is textual, never through a float: trailing fractional
    zeros are stripped and an emptied fraction is dropped. The value must be
    strictly greater than zero (O5).
    """
    if not isinstance(raw_text, str) or not MAX_AUTHORING_RE.fullmatch(raw_text):
        raise NumericContractError(
            f"max {raw_text!r} does not match the authoring grammar "
            "(plain decimal, up to 18 integer and 9 fraction digits, no sign, "
            "exponent, underscore, leading zero or bare point)"
        )
    integer, _, fraction = raw_text.partition(".")
    fraction = fraction.rstrip("0")
    canonical = f"{integer}.{fraction}" if fraction else integer
    if Fraction(canonical) <= 0:
        raise NumericContractError("max must be strictly greater than zero")
    return canonical


def _validate_canonical_max(value: object) -> str:
    if not isinstance(value, str) or not MAX_CANONICAL_RE.fullmatch(value):
        raise NumericContractError(
            f"stored max {value!r} is not canonical decimal text"
        )
    integer, _, fraction = value.partition(".")
    if len(integer) > _MAX_INT_DIGITS or len(fraction) > _MAX_FRACTION_DIGITS:
        raise NumericContractError(
            f"stored max {value!r} exceeds the authoring digit limits"
        )
    if Fraction(value) <= 0:
        raise NumericContractError("max must be strictly greater than zero")
    return value


def _strict_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def contract_from_object(obj: object) -> NumericContract:
    """Validate a decoded contract object strictly (no defaults, no extras)."""
    if not isinstance(obj, dict):
        raise NumericContractError("numeric rule value must be a JSON object")
    unknown = set(obj) - _CONTRACT_KEYS
    if unknown:
        raise NumericContractError(
            f"numeric rule value has unsupported keys {sorted(unknown)}"
        )
    for key in ("v", "language", "max", "inclusive", "unit"):
        if key not in obj:
            raise NumericContractError(f"numeric rule value requires {key!r}")
    if not _strict_int(obj["v"]) or obj["v"] != CONTRACT_VERSION:
        raise NumericContractError(
            f"numeric rule contract version must be {CONTRACT_VERSION}"
        )
    if obj["language"] != "python":
        raise NumericContractError("numeric rule language must be 'python'")
    if obj["inclusive"] is not True:
        raise NumericContractError("numeric rule inclusive must be true")
    unit = obj["unit"]
    if not isinstance(unit, str) or not unit.strip():
        raise NumericContractError("numeric rule unit must be a non-empty string")
    max_text = _validate_canonical_max(obj["max"])
    symbol = obj.get("symbol")
    if "symbol" in obj and not is_identifier(symbol):
        raise NumericContractError(
            f"numeric rule symbol {symbol!r} is not a Python identifier"
        )
    call_function: str | None = None
    call_position: int | None = None
    if "call" in obj:
        call = obj["call"]
        if not isinstance(call, dict) or set(call) != _CALL_KEYS:
            raise NumericContractError(
                "numeric rule call must be an object with exactly "
                "'function' and 'position'"
            )
        if not is_identifier(call["function"]):
            raise NumericContractError(
                f"numeric rule call.function {call['function']!r} is not a "
                "Python identifier"
            )
        if not _strict_int(call["position"]) or call["position"] < 0:
            raise NumericContractError(
                "numeric rule call.position must be a non-negative integer"
            )
        call_function, call_position = call["function"], call["position"]
    if symbol is None and call_function is None:
        raise NumericContractError(
            "numeric rule requires at least one of 'symbol' and 'call'"
        )
    return NumericContract(
        max=max_text,
        unit=unit,
        symbol=symbol,
        call_function=call_function,
        call_position=call_position,
    )


def parse_rule_value(value: object) -> NumericContract:
    """Strictly validate a stored canonical ``Rule.value`` (authoring and load).

    The value must decode to a valid contract **and** be byte-identical to
    that contract's canonical serialization, so persisted content is never
    reinterpreted or rewritten.
    """
    if not isinstance(value, str):
        raise NumericContractError("numeric rule value must be a string")
    try:
        obj = json.loads(value, parse_float=_reject_float, parse_constant=_reject_constant)
    except NumericContractError:
        raise
    except ValueError as exc:
        raise NumericContractError(
            f"numeric rule value is not canonical JSON: {exc}"
        ) from exc
    contract = contract_from_object(obj)
    if contract.canonical_value() != value:
        raise NumericContractError(
            "numeric rule value is not in canonical serialized form"
        )
    return contract


def _reject_float(text: str) -> Any:
    raise NumericContractError(
        f"numeric rule value contains a JSON number {text!r}; max is stored "
        "as a decimal string"
    )


def _reject_constant(text: str) -> Any:
    raise NumericContractError(f"numeric rule value contains {text!r}")


# ── Matcher result ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UnknownSource:
    """One declared source the matcher could not positively decide."""

    kind: str
    line: int | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "line": self.line, "reason": self.reason}


@dataclass(frozen=True)
class ExceedingSource:
    """One recognized source whose runtime value exceeds ``max``."""

    kind: str
    line: int
    value: str        # ``repr`` of the runtime value
    value_exact: str  # its exact decimal expansion

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "line": self.line,
            "value": self.value,
            "value_exact": self.value_exact,
        }


@dataclass(frozen=True)
class MatcherResult:
    """Per-rule matcher record (ADR-034 §4, charter §6)."""

    status: str
    outcome: str
    primary_reason: str | None
    unknown_sources: tuple[UnknownSource, ...] = ()
    exceeding_sources: tuple[ExceedingSource, ...] = ()

    @property
    def complete(self) -> bool:
        return self.status == STATUS_RECOGNIZED


def primary_reason_of(reasons: list[str] | tuple[str, ...]) -> str | None:
    """The first reason, in ADR-034 priority order, that applies."""
    for reason in REASON_PRIORITY:
        if reason in reasons:
            return reason
    return None


def _result(
    unknown: list[UnknownSource],
    exceeding: list[ExceedingSource],
) -> MatcherResult:
    if exceeding and not unknown:
        status, outcome = STATUS_RECOGNIZED, OUTCOME_VIOLATION
    elif exceeding:
        status, outcome = STATUS_PARTIAL, OUTCOME_VIOLATION
    elif unknown:
        status, outcome = STATUS_UNEVALUATED, OUTCOME_UNEVALUATED
    else:
        status, outcome = STATUS_RECOGNIZED, OUTCOME_NO_VIOLATION
    return MatcherResult(
        status=status,
        outcome=outcome,
        primary_reason=primary_reason_of([u.reason for u in unknown]),
        unknown_sources=tuple(unknown),
        exceeding_sources=tuple(exceeding),
    )


def incomplete_input_result() -> MatcherResult:
    """Non-source input (prompt, fragment, delta, stdin): decided pre-parse."""
    return _result(
        [UnknownSource(SOURCE_KIND_INPUT, None, REASON_INCOMPLETE_SOURCE_INPUT)],
        [],
    )


# ── Literal folding (ADR-034 §3, §5a) ────────────────────────────────────────


class _Unknown(Exception):
    """A value outside the recognized forms or range (UNRECOGNIZED_FORM)."""


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _checked(value: object) -> int | float:
    """Apply the §5a range guards to one intermediate or final value."""
    if isinstance(value, bool):
        raise _Unknown("bool")
    if isinstance(value, int):
        if abs(value) > _INT_MAGNITUDE_LIMIT:
            raise _Unknown("int magnitude above 10^30")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _Unknown("non-finite float")
        return value
    raise _Unknown("non-numeric value")


def fold(node: ast.AST) -> int | float:
    """Evaluate a recognized literal expression with pinned CPython semantics.

    Raises ``_Unknown`` for anything outside the recognized forms or the
    §5a bounds. Never executes source: only ``operator`` functions are
    applied to ``int``/``float`` constants taken from the AST.
    """
    if isinstance(node, ast.Constant):
        return _checked(node.value)
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPERATORS.get(type(node.op))
        if op is None:
            raise _Unknown("unsupported unary operator")
        return _checked(op(fold(node.operand)))
    if isinstance(node, ast.BinOp):
        op = _BINARY_OPERATORS.get(type(node.op))
        if op is None:
            raise _Unknown("unsupported binary operator")
        left = fold(node.left)
        right = fold(node.right)
        if isinstance(node.op, ast.Pow):
            # §3: an ``int`` exponent (by type) of magnitude at most 64.
            if not isinstance(right, int) or abs(right) > _POW_EXPONENT_LIMIT:
                raise _Unknown("unsupported exponent")
        try:
            value = op(left, right)
        except (OverflowError, ZeroDivisionError) as exc:
            raise _Unknown(type(exc).__name__) from exc
        if isinstance(value, complex):
            raise _Unknown("complex result")
        return _checked(value)
    raise _Unknown("unrecognized form")


def _exact_decimal(value: int | float) -> str:
    return str(Decimal(value)) if isinstance(value, float) else str(value)


# ── Binding analysis ─────────────────────────────────────────────────────────


def _target_names(target: ast.AST) -> list[ast.Name]:
    if isinstance(target, ast.Name):
        return [target]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [n for elt in target.elts for n in _target_names(elt)]
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    return []


@dataclass
class _Binding:
    line: int
    node: ast.AST
    module_level: bool  # a direct statement of the module body
    kind: str


@dataclass
class _ModuleFacts:
    bindings: dict[str, list[_Binding]] = field(default_factory=dict)
    # Load references of a name that are not the callee of a direct call.
    escapes: dict[str, list[int]] = field(default_factory=dict)
    # Direct bare-name calls, by callee name.
    calls: dict[str, list[ast.Call]] = field(default_factory=dict)


def _arg_names(args: ast.arguments) -> list[ast.arg]:
    out = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    if args.vararg:
        out.append(args.vararg)
    if args.kwarg:
        out.append(args.kwarg)
    return out


class _FactCollector(ast.NodeVisitor):
    """Collect bindings, escapes and direct calls across the whole module."""

    def __init__(self, module: ast.Module) -> None:
        self.facts = _ModuleFacts()
        self._top = {id(stmt) for stmt in module.body}

    def _bind(self, name: str, node: ast.AST, kind: str, owner: ast.AST) -> None:
        self.facts.bindings.setdefault(name, []).append(_Binding(
            line=getattr(node, "lineno", getattr(owner, "lineno", 0)),
            node=owner,
            module_level=id(owner) in self._top,
            kind=kind,
        ))

    # Statements that bind names.
    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            for name in _target_names(target):
                self._bind(name.id, name, "assign", node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        for name in _target_names(node.target):
            kind = "assign" if node.value is not None else "annotation"
            self._bind(name.id, name, kind, node)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        for name in _target_names(node.target):
            self._bind(name.id, name, "augassign", node)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self._bind(node.target.id, node.target, "walrus", node)
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            for name in _target_names(target):
                self._bind(name.id, name, "delete", node)
        self.generic_visit(node)

    def _visit_for(self, node: ast.For | ast.AsyncFor) -> None:
        for name in _target_names(node.target):
            self._bind(name.id, name, "for", node)
        self.generic_visit(node)

    visit_For = _visit_for
    visit_AsyncFor = _visit_for

    def _visit_with(self, node: ast.With | ast.AsyncWith) -> None:
        for item in node.items:
            if item.optional_vars is not None:
                for name in _target_names(item.optional_vars):
                    self._bind(name.id, name, "with", node)
        self.generic_visit(node)

    visit_With = _visit_with
    visit_AsyncWith = _visit_with

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self._bind(node.name, node, "except", node)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        for name in _target_names(node.target):
            self._bind(name.id, name, "comprehension", node.target)
        self.generic_visit(node)

    def _visit_import(self, node: ast.Import | ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                continue
            if alias.asname is not None:
                bound = alias.asname
                kind = "import" if alias.asname == alias.name else "import_alias"
            else:
                bound = alias.name.split(".")[0]
                kind = "import"
            self._bind(bound, node, kind, node)
        self.generic_visit(node)

    visit_Import = _visit_import
    visit_ImportFrom = _visit_import

    def _visit_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
    ) -> None:
        if not isinstance(node, ast.Lambda):
            self._bind(node.name, node, "def", node)
            for param in getattr(node, "type_params", []):
                self._bind(param.name, param, "type_param", node)
        for arg in _arg_names(node.args):
            self._bind(arg.arg, arg, "parameter", node)
        self.generic_visit(node)

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function
    visit_Lambda = _visit_function

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._bind(node.name, node, "class", node)
        for param in getattr(node, "type_params", []):
            self._bind(param.name, param, "type_param", node)
        self.generic_visit(node)

    def visit_TypeAlias(self, node: ast.AST) -> None:
        name = getattr(node, "name", None)
        if isinstance(name, ast.Name):
            self._bind(name.id, name, "type_alias", node)
        self.generic_visit(node)

    def _visit_scope_decl(self, node: ast.Global | ast.Nonlocal) -> None:
        for name in node.names:
            self._bind(name, node, "scope_declaration", node)

    visit_Global = _visit_scope_decl
    visit_Nonlocal = _visit_scope_decl

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self._bind(node.name, node, "match", node)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self._bind(node.name, node, "match", node)
        self.generic_visit(node)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self._bind(node.rest, node, "match", node)
        self.generic_visit(node)

    # Calls and escapes.
    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            self.facts.calls.setdefault(node.func.id, []).append(node)
            for child in (*node.args, *node.keywords):
                self.visit(child)
            return
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.facts.escapes.setdefault(node.id, []).append(node.lineno)


def _collect(module: ast.Module) -> _ModuleFacts:
    collector = _FactCollector(module)
    collector.visit(module)
    return collector.facts


# ── Source classification ────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Classified:
    """WITHIN / EXCEEDS / UNKNOWN for one declared source."""

    state: str            # "WITHIN" | "EXCEEDS" | "UNKNOWN"
    line: int | None
    reason: str | None = None
    value: int | float | None = None


def _judge(value: int | float, bound: Fraction, line: int) -> _Classified:
    if value <= 0:
        # Disabled values are a C1 question this rule does not claim.
        return _Classified("UNKNOWN", line, REASON_UNRECOGNIZED_FORM)
    if Fraction(value) > bound:
        return _Classified("EXCEEDS", line, value=value)
    return _Classified("WITHIN", line, value=value)


def _classify_expression(
    node: ast.AST, bound: Fraction, line: int,
) -> _Classified:
    try:
        value = fold(node)
    except (_Unknown, RecursionError):
        return _Classified("UNKNOWN", line, REASON_UNRECOGNIZED_FORM)
    return _judge(value, bound, line)


def _classify_symbol(
    symbol: str, facts: _ModuleFacts, bound: Fraction,
) -> _Classified:
    """The single module-level assignment to ``symbol`` (ADR-034 §3)."""
    bindings = facts.bindings.get(symbol, [])
    if not bindings:
        return _Classified("UNKNOWN", None, REASON_SOURCE_NOT_FOUND)
    if len(bindings) > 1:
        # Assigned more than once, conditionally, or rebound anywhere.
        line = min(b.line for b in bindings)
        return _Classified("UNKNOWN", line, REASON_AMBIGUOUS_BINDING)
    binding = bindings[0]
    if not binding.module_level:
        # Bound only in a nested scope or under a compound statement: never
        # the single unconditional module-level assignment.
        return _Classified("UNKNOWN", binding.line, REASON_AMBIGUOUS_BINDING)
    stmt = binding.node
    if isinstance(stmt, ast.Assign):
        direct = any(
            isinstance(t, ast.Name) and t.id == symbol for t in stmt.targets
        )
        if direct:
            return _classify_expression(stmt.value, bound, stmt.lineno)
    elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        if isinstance(stmt.target, ast.Name):
            return _classify_expression(stmt.value, bound, stmt.lineno)
    # Unpacking, a bare annotation, an import or a definition: the binding
    # exists but does not carry a recognized value form.
    return _Classified("UNKNOWN", binding.line, REASON_UNRECOGNIZED_FORM)


def _function_ambiguity(function: str, facts: _ModuleFacts) -> int | None:
    """Line of the first rebinding, shadowing or escape of ``function``.

    A single module-level ``def`` or unaliased import is the function's
    declaration (AMB-01). Any other binding anywhere -- including a parameter
    of the same name (AMB-07) -- shadows or rebinds it, and any load of the
    name other than as the callee of a direct call lets it escape as a value.
    """
    bindings = facts.bindings.get(function, [])
    declaration = next(
        (
            b for b in bindings
            if b.module_level and b.kind in ("def", "import")
        ),
        None,
    )
    offending = [b.line for b in bindings if b is not declaration]
    offending.extend(facts.escapes.get(function, []))
    return min(offending) if offending else None


def _classify_call_site(
    call: ast.Call,
    position: int,
    symbol: str | None,
    symbol_result: _Classified | None,
    bound: Fraction,
) -> _Classified:
    if any(isinstance(arg, ast.Starred) for arg in call.args) or any(
        kw.arg is None for kw in call.keywords
    ):
        # Star-unpacking hides positions (AMB-05); explicit keywords for other
        # parameters do not defeat the positional source (AMB-04).
        return _Classified("UNKNOWN", call.lineno, REASON_UNRECOGNIZED_FORM)
    if len(call.args) <= position:
        # Passed by keyword, or omitted: the positional source is absent
        # (AMB-02).
        return _Classified("UNKNOWN", call.lineno, REASON_SOURCE_NOT_FOUND)
    arg = call.args[position]
    line = arg.lineno
    if (
        symbol is not None
        and symbol_result is not None
        and isinstance(arg, ast.Name)
        and arg.id == symbol
    ):
        # The bare symbol resolves to the symbol's recognized value.
        return _Classified(
            symbol_result.state, line, symbol_result.reason, symbol_result.value,
        )
    return _classify_expression(arg, bound, line)


def evaluate_source(contract: NumericContract, source: bytes) -> MatcherResult:
    """Evaluate one verified complete Python source snapshot (G1).

    ``source`` is the exact byte snapshot read from the governed path; it is
    parsed with the running interpreter's ``ast`` (the pinned grammar) and
    never imported or executed.
    """
    try:
        with warnings.catch_warnings():
            # Compile-time warnings (for example invalid escape sequences)
            # are not matcher input and must never reach stderr.
            warnings.simplefilter("ignore")
            module = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        return _result(
            [UnknownSource(SOURCE_KIND_MODULE, exc.lineno, REASON_PARSE_FAILURE)],
            [],
        )
    except (ValueError, RecursionError, MemoryError):
        return _result(
            [UnknownSource(SOURCE_KIND_MODULE, None, REASON_PARSE_FAILURE)],
            [],
        )

    facts = _collect(module)
    bound = Fraction(contract.max)
    classified: list[tuple[str, _Classified]] = []

    symbol_result: _Classified | None = None
    if contract.symbol is not None:
        symbol_result = _classify_symbol(contract.symbol, facts, bound)
        classified.append((SOURCE_KIND_SYMBOL, symbol_result))

    if contract.call_function is not None:
        ambiguous_line = _function_ambiguity(contract.call_function, facts)
        calls = sorted(
            facts.calls.get(contract.call_function, []),
            key=lambda c: (c.lineno, c.col_offset),
        )
        if ambiguous_line is not None:
            # The whole call source is ambiguous (AMB-07).
            classified.append((
                SOURCE_KIND_CALL,
                _Classified("UNKNOWN", ambiguous_line, REASON_AMBIGUOUS_BINDING),
            ))
        elif not calls:
            classified.append((
                SOURCE_KIND_CALL,
                _Classified("UNKNOWN", None, REASON_SOURCE_NOT_FOUND),
            ))
        else:
            for call in calls:
                classified.append((SOURCE_KIND_CALL, _classify_call_site(
                    call,
                    contract.call_position,
                    contract.symbol,
                    symbol_result,
                    bound,
                )))

    unknown: list[UnknownSource] = []
    exceeding: list[ExceedingSource] = []
    for kind, item in classified:
        if item.state == "UNKNOWN":
            unknown.append(UnknownSource(kind, item.line, item.reason))
        elif item.state == "EXCEEDS":
            exceeding.append(ExceedingSource(
                kind=kind,
                line=item.line,
                value=repr(item.value),
                value_exact=_exact_decimal(item.value),
            ))
    return _result(unknown, exceeding)


__all__ = [
    "CONTRACT_VERSION",
    "ExceedingSource",
    "INCOMPLETE_STATUSES",
    "MATCHER_OUTCOMES",
    "MATCHER_REASONS",
    "MATCHER_STATUSES",
    "MatcherResult",
    "NumericContract",
    "NumericContractError",
    "REASON_PRIORITY",
    "RULE_TYPE",
    "SEMANTIC_FEATURE",
    "SOURCE_KINDS",
    "STRICT_COMPARISON_NOTE",
    "UnknownSource",
    "canonicalize_max",
    "contract_from_object",
    "evaluate_source",
    "fold",
    "incomplete_input_result",
    "parse_rule_value",
    "primary_reason_of",
    "runtime_label",
]

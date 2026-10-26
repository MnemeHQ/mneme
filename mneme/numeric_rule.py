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


def _arg_names(args: ast.arguments) -> list[ast.arg]:
    out = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    if args.vararg:
        out.append(args.vararg)
    if args.kwarg:
        out.append(args.kwarg)
    return out


class _FactCollector(ast.NodeVisitor):
    """Collect bindings across the whole module (the ``symbol`` source)."""

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


# ── Function-source resolution by Python lexical scoping (ADR-034 §3a) ───────

# Names whose use defeats static resolution of any module name (§3a rule 4):
# they can execute source or read and write a namespace as a mapping.
_DYNAMIC_NAMES = frozenset({
    "exec", "eval", "globals", "locals", "vars", "__builtins__",
})
_DYNAMIC_MODULES = frozenset({"builtins", "__builtin__"})
# Attributes that expose or mutate a namespace (a module's included) as an
# object or mapping: ``module.__dict__``, ``func.__globals__``, frames, ...
_NAMESPACE_ATTRS = frozenset({
    "__dict__", "__setattr__", "__delattr__", "__getattribute__",
    "__globals__", "__builtins__", "f_globals", "f_locals", "f_builtins",
})
# Builtins that read or write an attribute named by an argument.
_ATTRIBUTE_BUILTINS = frozenset({"setattr", "delattr", "getattr"})
# Ways to obtain a module object by a computed name.
_MODULE_LOADERS = frozenset({"__import__", "import_module"})
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


@dataclass
class _Scope:
    kind: str                     # "module" | "function" | "class" | "comprehension"
    parent: "_Scope | None"
    # A class whose namespace may be pre-populated by a metaclass ``__prepare__``
    # (any base or keyword): its body lookups cannot be decided statically.
    opaque: bool = False
    binding_lines: list[int] = field(default_factory=list)


@dataclass
class _CallResolution:
    # Set when the whole call source is ambiguous (§3a rules 3 and 4).
    ambiguous_line: int | None = None
    # Direct calls that resolve to the module-level declaration (AMB-01).
    resolved: list[ast.Call] = field(default_factory=list)
    # Direct calls that resolve to another binding, or cannot be decided.
    unresolved: list[ast.Call] = field(default_factory=list)


class _CallScopeResolver:
    """Resolve each direct ``function(...)`` call site by lexical scoping.

    Lookup order at a call site is the local scope, then enclosing function
    scopes, then the module scope. A class body's scope is visible only to
    statements written directly in it. Anything static analysis cannot
    decide fails closed as ``AMBIGUOUS_BINDING``; a clean result is never
    assumed.
    """

    def __init__(self, function: str, module: ast.Module) -> None:
        self.name = function
        self.module_scope = _Scope("module", None)
        self._top = {id(stmt) for stmt in module.body}
        # Module-scope bindings as (line, is a top-level def/unaliased import).
        self.module_bindings: list[tuple[int, bool]] = []
        self.fail_lines: list[int] = []
        self.calls: list[tuple[ast.Call, _Scope]] = []
        self.loads: list[tuple[int, _Scope]] = []
        # Local names for ``sys``, whose ``modules`` reaches every module.
        self._sys_names = {
            alias.asname or "sys"
            for node in ast.walk(module) if isinstance(node, ast.Import)
            for alias in node.names if alias.name == "sys"
        }
        self._stmts(module.body, self.module_scope)

    # ── Collection ──────────────────────────────────────────────────────────

    def _bind(self, scope: _Scope, line: int, declaration: bool = False) -> None:
        if scope.kind == "module":
            self.module_bindings.append((line, declaration))
        else:
            scope.binding_lines.append(line)

    def _stmts(self, body: list[ast.stmt], scope: _Scope) -> None:
        for stmt in body:
            self._visit(stmt, scope)

    def _visit(self, node: ast.AST | None, scope: _Scope) -> None:
        if node is None:
            return
        name = self.name
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._type_params(node)
            for deco in node.decorator_list:
                self._visit(deco, scope)
            self._arguments_outer(node.args, scope)
            self._visit(node.returns, scope)
            if node.name == name:
                self._bind(scope, node.lineno, id(node) in self._top)
            inner = _Scope("function", scope)
            self._arguments_inner(node.args, inner)
            self._stmts(node.body, inner)
        elif isinstance(node, ast.Lambda):
            self._arguments_outer(node.args, scope)
            inner = _Scope("function", scope)
            self._arguments_inner(node.args, inner)
            self._visit(node.body, inner)
        elif isinstance(node, ast.ClassDef):
            self._type_params(node)
            for deco in node.decorator_list:
                self._visit(deco, scope)
            for base in node.bases:
                self._visit(base, scope)
            for kw in node.keywords:
                self._visit(kw.value, scope)
            if node.name == name:
                self._bind(scope, node.lineno)
            inner = _Scope(
                "class", scope, opaque=bool(node.bases or node.keywords),
            )
            self._stmts(node.body, inner)
        elif isinstance(node, _COMPREHENSIONS):
            first, *rest = node.generators
            # The first iterable is evaluated in the enclosing scope.
            self._visit(first.iter, scope)
            inner = _Scope("comprehension", scope)
            for i, gen in enumerate(node.generators):
                self._visit(gen.target, inner)
                if i:
                    self._visit(gen.iter, inner)
                for cond in gen.ifs:
                    self._visit(cond, inner)
            if isinstance(node, ast.DictComp):
                self._visit(node.key, inner)
                self._visit(node.value, inner)
            else:
                self._visit(node.elt, inner)
        elif isinstance(node, ast.NamedExpr):
            if node.target.id == name:
                # A walrus binds in the nearest non-comprehension scope.
                target = scope
                while target.kind == "comprehension":
                    target = target.parent
                if target.kind == "class" and target is not scope:
                    # Not valid Python; never resolved by assumption.
                    self.fail_lines.append(node.lineno)
                self._bind(target, node.lineno)
            self._visit(node.value, scope)
        elif isinstance(node, ast.Name):
            if node.id in _DYNAMIC_NAMES or (
                # Passed around rather than called directly: its effect on
                # the module namespace cannot be bounded.
                node.id in _ATTRIBUTE_BUILTINS | _MODULE_LOADERS
                and isinstance(node.ctx, ast.Load)
            ):
                self.fail_lines.append(node.lineno)
            if node.id != name:
                return
            if isinstance(node.ctx, ast.Load):
                self.loads.append((node.lineno, scope))
            else:
                if isinstance(node.ctx, ast.Del) and scope.kind == "module":
                    self.fail_lines.append(node.lineno)
                self._bind(scope, node.lineno)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == name:
                self.calls.append((node, scope))
            elif isinstance(func, ast.Name) and func.id in _ATTRIBUTE_BUILTINS:
                self._attribute_builtin(node, func.id)
            elif isinstance(func, ast.Name) and func.id in _MODULE_LOADERS:
                self._module_loader(node)
            else:
                if isinstance(func, ast.Attribute) and func.attr in _MODULE_LOADERS:
                    self._module_loader(node)
                self._visit(func, scope)
            for arg in node.args:
                self._visit(arg, scope)
            for kw in node.keywords:
                self._visit(kw.value, scope)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            if name in node.names:
                self.fail_lines.append(node.lineno)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module in _DYNAMIC_MODULES:
                self.fail_lines.append(node.lineno)
            for alias in node.names:
                if (
                    alias.name == "*"
                    or alias.name in _DYNAMIC_MODULES
                    or (
                        isinstance(node, ast.ImportFrom)
                        and node.module == "sys"
                        and alias.name == "modules"
                    )
                ):
                    self.fail_lines.append(node.lineno)
                    continue
                if alias.asname is not None:
                    bound, unaliased = alias.asname, alias.asname == alias.name
                else:
                    bound, unaliased = alias.name.split(".")[0], True
                if bound == name:
                    self._bind(
                        scope, node.lineno, unaliased and id(node) in self._top,
                    )
        elif isinstance(node, ast.ExceptHandler):
            if node.name == name:
                self._bind(scope, node.lineno)
            self._generic(node, scope)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)):
            if node.name == name:
                self._bind(scope, node.lineno)
            self._generic(node, scope)
        elif isinstance(node, ast.MatchMapping):
            if node.rest == name:
                self._bind(scope, node.lineno)
            self._generic(node, scope)
        elif type(node).__name__ == "TypeAlias":
            # The value lives in its own lazily evaluated annotation scope.
            if self._mentions(node):
                self.fail_lines.append(node.lineno)
            if node.name.id == name:
                self._bind(scope, node.lineno)
        elif isinstance(node, ast.Attribute):
            if (
                node.attr in _NAMESPACE_ATTRS
                # Any object may be this module (a self-import,
                # ``import_module(__name__)``): an attribute write of the
                # name can rebind the declaration indirectly.
                or (node.attr == name and not isinstance(node.ctx, ast.Load))
                or (
                    # sys.modules reaches the module namespace as an object.
                    node.attr == "modules"
                    and isinstance(node.value, ast.Name)
                    and node.value.id in self._sys_names
                )
            ):
                self.fail_lines.append(node.lineno)
            self._visit(node.value, scope)
        elif isinstance(node, ast.Constant):
            # ``getattr(m, "__dict__")``, ``attrgetter("__globals__")``, ...
            if isinstance(node.value, str) and node.value in _NAMESPACE_ATTRS:
                self.fail_lines.append(node.lineno)
        else:
            self._generic(node, scope)

    def _attribute_builtin(self, node: ast.Call, builtin: str) -> None:
        """``setattr``/``delattr``/``getattr``: safe only for a constant name.

        The target object may be this module, so a write is harmless only
        when it provably names another attribute; a read is harmless unless
        it can fetch a namespace (checked on the constant itself).
        """
        args = node.args
        attr = args[1] if len(args) >= 2 else None
        safe = (
            not any(isinstance(arg, ast.Starred) for arg in args)
            and not any(kw.arg is None for kw in node.keywords)
            and isinstance(attr, ast.Constant)
            and isinstance(attr.value, str)
            and (builtin == "getattr" or attr.value != self.name)
        )
        if not safe:
            self.fail_lines.append(node.lineno)

    def _module_loader(self, node: ast.Call) -> None:
        # A computed module name (``import_module(__name__)``) may be this
        # module; a constant names a module this source can only reach
        # through the attribute writes and namespace accesses checked above.
        first = node.args[0] if node.args else None
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            self.fail_lines.append(node.lineno)

    def _generic(self, node: ast.AST, scope: _Scope) -> None:
        for child in ast.iter_child_nodes(node):
            self._visit(child, scope)

    def _arguments_outer(self, args: ast.arguments, scope: _Scope) -> None:
        # Defaults and annotations are evaluated in the enclosing scope.
        for default in (*args.defaults, *args.kw_defaults):
            self._visit(default, scope)
        for arg in _arg_names(args):
            self._visit(arg.annotation, scope)

    def _arguments_inner(self, args: ast.arguments, scope: _Scope) -> None:
        for arg in _arg_names(args):
            if arg.arg == self.name:
                self._bind(scope, arg.lineno)

    def _type_params(self, node: ast.AST) -> None:
        # PEP 695 annotation scopes: fail closed if they touch the name.
        for param in getattr(node, "type_params", []):
            if self._mentions(param):
                self.fail_lines.append(node.lineno)

    def _mentions(self, node: ast.AST) -> bool:
        return any(
            (isinstance(n, ast.Name) and n.id == self.name)
            or getattr(n, "name", None) == self.name
            for n in ast.walk(node)
        )

    # ── Resolution ──────────────────────────────────────────────────────────

    def _lookup(self, scope: _Scope) -> str:
        """Where the name at ``scope`` resolves.

        ``"module"`` for the module scope, ``"other"`` for another binding,
        ``"undecided"`` when static analysis cannot tell.
        """
        current, first = scope, True
        while current.kind != "module":
            if current.kind == "class":
                if first:
                    # A statement written directly in a class body: a class
                    # binding depends on execution order, and an opaque
                    # namespace cannot be read statically. Both fail closed.
                    if current.binding_lines or current.opaque:
                        return "undecided"
                # Otherwise a class scope is invisible from nested scopes.
            elif current.binding_lines:
                return "other"
            first = False
            current = current.parent
        return "module"

    def resolve(self) -> _CallResolution:
        offending = list(self.fail_lines)
        declarations = [b for b in self.module_bindings if b[1]]
        if len(self.module_bindings) > 1 or (
            self.module_bindings and not declarations
        ):
            # A second module-level binding, or a reassignment, ``del``, or
            # conditional or ``try``-guarded definition (§3a rule 3).
            offending.extend(line for line, _ in self.module_bindings)
        for line, scope in self.loads:
            if self._lookup(scope) != "other":
                # The declaration escapes as a value, or may.
                offending.append(line)
        if offending:
            return _CallResolution(ambiguous_line=min(offending))
        result = _CallResolution()
        for call, scope in self.calls:
            if self._lookup(scope) == "module":
                result.resolved.append(call)
            else:
                result.unresolved.append(call)
        return result


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
        resolution = _CallScopeResolver(contract.call_function, module).resolve()
        if resolution.ambiguous_line is not None:
            # The whole call source is ambiguous (§3a rules 3 and 4).
            classified.append((
                SOURCE_KIND_CALL,
                _Classified(
                    "UNKNOWN", resolution.ambiguous_line, REASON_AMBIGUOUS_BINDING,
                ),
            ))
        elif not resolution.resolved and not resolution.unresolved:
            classified.append((
                SOURCE_KIND_CALL,
                _Classified("UNKNOWN", None, REASON_SOURCE_NOT_FOUND),
            ))
        else:
            unresolved = {id(call) for call in resolution.unresolved}
            calls = sorted(
                [*resolution.resolved, *resolution.unresolved],
                key=lambda c: (c.lineno, c.col_offset),
            )
            for call in calls:
                if id(call) in unresolved:
                    # Resolves to another binding: its own unknown source
                    # (§3a rule 2), never ignored.
                    classified.append((SOURCE_KIND_CALL, _Classified(
                        "UNKNOWN", call.lineno, REASON_AMBIGUOUS_BINDING,
                    )))
                    continue
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

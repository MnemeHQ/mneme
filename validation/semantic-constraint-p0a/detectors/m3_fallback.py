"""M3: static structural fallback (charter section 4.1, exactly).

Analyzes ``route`` against the frozen simple router template with ``ast``
and returns one of four outcomes for C3:

| Recognized form | Verdict |
|---|---|
| the ``classify`` call has no enclosing timeout handler | ``VIOLATION`` |
| a declared timeout handler re-raises | ``VIOLATION`` |
| a declared timeout handler returns ``FALLBACK_ROUTE`` | ``NO_VIOLATION`` (static structure only) |
| anything else | ``UNEVALUATED`` |

M3 never infers a violation from unfamiliar syntax. ``NO_VIOLATION`` means a
recognized fallback *structure* is present, not that it behaves safely; only
the post-mutation M4 probe observes behavior (charter D5).

Template recognition, all required, otherwise ``UNEVALUATED``:

- exactly one undecorated module-level ``def route(request, classify)`` with
  no defaults, ``*args``, keyword-only or ``**kwargs`` parameters, no nested
  function, lambda or class, and no rebinding of ``classify``;
- ``classify`` appears in ``route`` only as the target of exactly one call,
  and that call is the whole value of a ``return`` statement;
- ``FALLBACK_ROUTE`` is bound exactly once, by a module-level assignment, and
  no declared exception type name is rebound anywhere in the module;
- the body of ``route`` is: an optional docstring, then at most one guard
  of exactly the form ``if not request: return FALLBACK_ROUTE`` (no ``else``),
  then the classify site as the last statement. Any other statement before
  the classify site, including any other early return, is ``UNEVALUATED``;
- the classify site is either that ``return`` directly (no handler), or a
  ``try`` whose body is exactly that ``return``, with at least one handler and
  no ``else`` or ``finally``.

Handlers are read in order, as Python matches them. The first handler whose
type is a bare name in the template's ``declared_exception_types`` is the
timeout handler. A bare ``except:``, a tuple, an attribute or an undeclared
name met before it makes the result ``UNEVALUATED`` (AMB-3: only
``TimeoutError`` and ``Exception`` are exercised by the frozen fixtures).
The timeout handler's body must be exactly ``return FALLBACK_ROUTE``
(``NO_VIOLATION``) or exactly ``raise`` / ``raise <bound name>``
(``VIOLATION``); any other body, including a helper call such as
``_fallback()``, is ``UNEVALUATED``.

The single guard form is admitted because charter section 4.1 places Set 0
case A, whose ``route`` starts with ``if not request: return
FALLBACK_ROUTE``, in the ``NO_VIOLATION`` row. Version 1.0.0 accepted any
``if <test>: return <expr>`` guard; owner review of #586 narrowed it to A's
exact form, because an arbitrary early return (for example ``if request:
return "wrong"``) can keep a request from ever reaching ``classify`` and
invalidates any static fallback inference.
"""

import ast

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

METHOD_ID = "M3"
METHOD_VERSION = "p0a-m3-structural-fallback/1.1.0"


class _Unrecognized(Exception):
    pass


def _is_case_a_guard(stmt: ast.stmt, request: str, fallback: str) -> bool:
    """Exactly ``if not <request>: return <fallback>`` with no ``else``."""
    return (
        isinstance(stmt, ast.If)
        and isinstance(stmt.test, ast.UnaryOp)
        and isinstance(stmt.test.op, ast.Not)
        and isinstance(stmt.test.operand, ast.Name)
        and stmt.test.operand.id == request
        and not stmt.orelse
        and len(stmt.body) == 1
        and isinstance(stmt.body[0], ast.Return)
        and isinstance(stmt.body[0].value, ast.Name)
        and stmt.body[0].value.id == fallback
    )


def _is_docstring(stmt: ast.stmt) -> bool:
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)


def _is_classify_return(stmt: ast.stmt, classifier: str) -> bool:
    return (
        isinstance(stmt, ast.Return)
        and isinstance(stmt.value, ast.Call)
        and isinstance(stmt.value.func, ast.Name)
        and stmt.value.func.id == classifier
    )


def _find_route(tree: ast.Module, symbols: dict) -> ast.FunctionDef:
    name = symbols["route_function"]
    defs = [s for s in tree.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and s.name == name]
    if len(defs) != 1 or len(bindings(tree, name)) != 1:
        raise _Unrecognized(f"expected exactly one module-level def {name}")
    route = defs[0]
    if isinstance(route, ast.AsyncFunctionDef) or route.decorator_list:
        raise _Unrecognized(f"{name} is async or decorated")
    a = route.args
    if (
        [p.arg for p in a.args] != symbols["route_parameters"]
        or a.posonlyargs or a.vararg or a.kwonlyargs or a.kwarg or a.defaults
    ):
        raise _Unrecognized(f"{name} signature differs from the template")
    return route


def _check_route_body(route: ast.FunctionDef, symbols: dict) -> ast.stmt:
    """Return the classify-site statement, or raise."""
    classifier = symbols["classifier_parameter"]
    request = symbols["route_parameters"][0]
    fallback = symbols["fallback_symbol"]
    for node in ast.walk(route):
        if node is not route and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            raise _Unrecognized("route contains a nested function, lambda or class")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise _Unrecognized("route declares global or nonlocal names")
        if isinstance(node, ast.Name) and node.id == classifier and not isinstance(node.ctx, ast.Load):
            raise _Unrecognized(f"route rebinds {classifier}")
    calls = [n for n in ast.walk(route) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == classifier]
    loads = [n for n in ast.walk(route) if isinstance(n, ast.Name) and n.id == classifier]
    if len(calls) != 1 or len(loads) != 1:
        raise _Unrecognized(f"{classifier} is not reached by exactly one direct call")

    body = list(route.body)
    if body and _is_docstring(body[0]):
        body = body[1:]
    if not body:
        raise _Unrecognized("route has no statements")
    *guards, site = body
    if len(guards) > 1 or (guards and not _is_case_a_guard(guards[0], request, fallback)):
        raise _Unrecognized(f"statement at line {guards[0].lineno} before the classify site is not the template guard")
    if _is_classify_return(site, classifier):
        return site
    if (
        isinstance(site, ast.Try)
        and len(site.body) == 1
        and _is_classify_return(site.body[0], classifier)
        and site.handlers
        and not site.orelse
        and not site.finalbody
    ):
        return site
    raise _Unrecognized(f"classify site at line {site.lineno} is not a template form")


def _timeout_handler(site: ast.Try, declared: set) -> ast.ExceptHandler:
    for handler in site.handlers:
        if handler.type is None:
            raise _Unrecognized(f"bare except at line {handler.lineno} is not a declared handler form")
        if isinstance(handler.type, ast.Name) and handler.type.id in declared:
            return handler
        raise _Unrecognized(f"handler at line {handler.lineno} has an undeclared or non-name exception type")
    raise _Unrecognized("no handler")


def detect(source: str, target_path: str) -> dict:
    if not in_scope(target_path):
        return out_of_scope(target_path)
    template = load_template()
    symbols = template["symbols"]
    fallback = symbols["fallback_symbol"]
    declared = set(template["timeout_handler"]["declared_exception_types"])
    c1, c2 = not_targeted(METHOD_ID), not_targeted(METHOD_ID)

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"C1": c1, "C2": c2, "C3": Finding(UNEVALUATED, f"PARSE_ERROR: {type(e).__name__}")}

    try:
        fallback_top = [
            s for s in tree.body
            if isinstance(s, ast.Assign) and len(s.targets) == 1
            and isinstance(s.targets[0], ast.Name) and s.targets[0].id == fallback
        ]
        if len(fallback_top) != 1 or len(bindings(tree, fallback)) != 1:
            raise _Unrecognized(f"{fallback} is not bound exactly once at module level")
        rebound = sorted(t for t in declared if bindings(tree, t))
        if rebound:
            raise _Unrecognized(f"declared exception type name(s) rebound: {', '.join(rebound)}")
        route = _find_route(tree, symbols)
        site = _check_route_body(route, symbols)
        if isinstance(site, ast.Return):
            c3 = Finding(VIOLATION, "NO_ENCLOSING_HANDLER: classify call has no enclosing timeout handler", (site.lineno,))
        else:
            handler = _timeout_handler(site, declared)
            hbody = handler.body
            if len(hbody) == 1 and isinstance(hbody[0], ast.Return) and isinstance(hbody[0].value, ast.Name) and hbody[0].value.id == fallback:
                c3 = Finding(NO_VIOLATION, f"HANDLER_RETURNS_FALLBACK: except {handler.type.id} returns {fallback} (static structure only)", (handler.lineno, hbody[0].lineno))
            elif (
                len(hbody) == 1 and isinstance(hbody[0], ast.Raise) and hbody[0].cause is None
                and (hbody[0].exc is None or (isinstance(hbody[0].exc, ast.Name) and handler.name and hbody[0].exc.id == handler.name))
            ):
                c3 = Finding(VIOLATION, f"HANDLER_RERAISES: except {handler.type.id} re-raises instead of returning {fallback}", (handler.lineno, hbody[0].lineno))
            else:
                raise _Unrecognized(f"timeout handler body at line {hbody[0].lineno} is not a recognized form")
    except _Unrecognized as e:
        c3 = Finding(UNEVALUATED, f"UNRECOGNIZED_FORM: {e}")
    return {"C1": c1, "C2": c2, "C3": c3}

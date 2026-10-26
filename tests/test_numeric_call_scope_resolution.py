"""ADR-034 §3a: function-source name resolution by Python lexical scoping.

Pins the owner ruling D2 (#669) as implemented in ``mneme/numeric_rule.py``
under freeze amendment Change 2 (#670). Each direct bare-name call site is
resolved where it is written; a binding no call site resolves to has no
effect; a call site that resolves to another binding is its own
``AMBIGUOUS_BINDING`` source; module-level rebinding, ``global``/``nonlocal``,
escape and dynamic constructs keep the whole source ``AMBIGUOUS_BINDING``.
No case may come out clean by assumption.
"""

from __future__ import annotations

import pytest

from mneme.numeric_rule import NumericContract, evaluate_source

CALL_ONLY = NumericContract(
    max="5", unit="s", call_function="classify", call_position=1,
)
ROUTER = NumericContract(
    max="5", unit="s", symbol="ROUTER_DEADLINE_S",
    call_function="classify", call_position=1,
)

DECL = "def classify(a, b):\n    pass\n"
AMB = "AMBIGUOUS_BINDING"


def _run(source: str, contract: NumericContract = CALL_ONLY):
    result = evaluate_source(contract, source.encode("utf-8"))
    return (
        result.status,
        result.outcome,
        [(u.kind, u.line, u.reason) for u in result.unknown_sources],
        [(e.line, e.value) for e in result.exceeding_sources],
    )


# ── The two D2 shapes (#666) ─────────────────────────────────────────────────


def test_d2_c_same_named_method_does_not_shadow_module_call():
    source = DECL + (
        "class R:\n"
        "    def classify(self, a, b):\n"
        "        pass\n"
        "classify(x, 2)\n"
    )
    assert _run(source) == ("RECOGNIZED", "NO_VIOLATION", [], [])


def test_d2_c_violating_module_call_is_now_recognized():
    source = DECL + (
        "class R:\n"
        "    def classify(self, a, b):\n"
        "        pass\n"
        "classify(x, 9)\n"
    )
    assert _run(source) == ("RECOGNIZED", "VIOLATION", [], [(6, "9")])


def test_d2_us_method_call_only_is_source_not_found():
    source = (
        "class R:\n"
        "    def classify(self, a, b):\n"
        "        pass\n"
        "    def go(self):\n"
        "        return self.classify(1, 9)\n"
    )
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED",
        [("call", None, "SOURCE_NOT_FOUND")], [],
    )


# ── Class body versus method ─────────────────────────────────────────────────


def test_method_body_call_skips_class_scope_and_resolves_to_module():
    source = DECL + (
        "class R:\n"
        "    def classify(self, a, b):\n"
        "        pass\n"
        "    def go(self):\n"
        "        return classify(self, 9)\n"
    )
    assert _run(source) == ("RECOGNIZED", "VIOLATION", [], [(7, "9")])


def test_bare_call_in_class_body_that_binds_the_name_is_ambiguous():
    # Class-body execution order is not decided statically: fail closed.
    source = DECL + (
        "class R:\n"
        "    def classify(self, a, b):\n"
        "        pass\n"
        "    classify(1, 2)\n"
        "classify(x, 3)\n"
    )
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 6, AMB)], [],
    )


def test_bare_call_in_class_body_before_the_binding_still_fails_closed():
    source = DECL + (
        "class R:\n"
        "    classify(1, 2)\n"
        "    def classify(self, a, b):\n"
        "        pass\n"
    )
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 4, AMB)], [],
    )


def test_bare_call_in_plain_class_body_without_binding_resolves_to_module():
    source = DECL + "class R:\n    classify(1, 9)\n"
    assert _run(source) == ("RECOGNIZED", "VIOLATION", [], [(4, "9")])


@pytest.mark.parametrize("header", ["class R(Base):", "class R(metaclass=M):"])
def test_bare_call_in_class_body_with_opaque_namespace_is_ambiguous(header):
    # A metaclass ``__prepare__`` may pre-populate the class namespace.
    source = DECL + header + "\n    classify(1, 2)\n"
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 4, AMB)], [],
    )


def test_class_body_load_of_a_class_bound_name_escapes():
    source = DECL + (
        "class R:\n"
        "    def classify(self, a, b):\n"
        "        pass\n"
        "    alias = classify\n"
        "classify(x, 2)\n"
    )
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 6, AMB)], [],
    )


# ── Parameter, nested function, enclosing scope ──────────────────────────────


def test_parameter_makes_only_its_own_call_sites_unknown():
    source = DECL + (
        "def h(classify):\n"
        "    return classify(1, 2)\n"
        "classify(x, 9)\n"
    )
    assert _run(source) == (
        "PARTIAL", "VIOLATION", [("call", 4, AMB)], [(5, "9")],
    )


def test_amb07_parameter_defaulting_to_the_function_still_escapes():
    # The default is a load of the declaration that is not a direct callee
    # (§3a rule 3), so the whole source stays ambiguous.
    source = DECL + (
        "def h(x, classify=classify):\n"
        "    return classify(x, 2)\n"
        "classify(x, 3)\n"
    )
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 3, AMB)], [],
    )


def test_local_binding_shadows_its_own_call_sites():
    source = DECL + (
        "def h():\n"
        "    classify = make()\n"
        "    return classify(1, 9)\n"
        "classify(x, 2)\n"
    )
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 5, AMB)], [],
    )


def test_local_binding_after_the_call_still_shadows():
    # Python makes the name local for the whole function body.
    source = DECL + (
        "def h():\n"
        "    classify(1, 2)\n"
        "    classify = make()\n"
    )
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 4, AMB)], [],
    )


def test_nested_function_resolves_through_enclosing_scope_binding():
    source = DECL + (
        "def h():\n"
        "    def classify(a, b):\n"
        "        pass\n"
        "    def g():\n"
        "        return classify(1, 9)\n"
        "    return g\n"
        "classify(x, 2)\n"
    )
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 7, AMB)], [],
    )


def test_nested_function_without_enclosing_binding_resolves_to_module():
    source = DECL + (
        "def h():\n"
        "    def g():\n"
        "        return classify(1, 9)\n"
        "    return g\n"
    )
    assert _run(source) == ("RECOGNIZED", "VIOLATION", [], [(5, "9")])


def test_method_in_class_nested_in_function_sees_enclosing_function():
    source = DECL + (
        "def h(classify):\n"
        "    class R:\n"
        "        def go(self):\n"
        "            return classify(1, 2)\n"
        "    return R\n"
    )
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 6, AMB)], [],
    )


def test_lambda_parameter_shadows_its_body():
    source = DECL + "f = lambda classify: classify(1, 9)\nclassify(x, 2)\n"
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 3, AMB)], [],
    )


# ── Comprehensions ───────────────────────────────────────────────────────────


def test_comprehension_without_binding_resolves_to_module():
    source = DECL + "xs = [classify(i, 9) for i in items]\n"
    assert _run(source) == ("RECOGNIZED", "VIOLATION", [], [(3, "9")])


def test_comprehension_target_shadows_calls_inside_it():
    source = DECL + (
        "xs = [classify(1, 9) for classify in handlers]\n"
        "classify(x, 2)\n"
    )
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 3, AMB)], [],
    )


def test_comprehension_in_class_body_cannot_see_class_binding():
    source = DECL + (
        "class R:\n"
        "    def classify(self, a, b):\n"
        "        pass\n"
        "    xs = [classify(i, 9) for i in items]\n"
    )
    assert _run(source) == ("RECOGNIZED", "VIOLATION", [], [(6, "9")])


def test_walrus_in_comprehension_binds_the_enclosing_function():
    source = DECL + (
        "def h():\n"
        "    [(classify := make()) for i in items]\n"
        "    return classify(1, 9)\n"
        "classify(x, 2)\n"
    )
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 5, AMB)], [],
    )


def test_walrus_in_module_comprehension_rebinds_at_module_scope():
    source = DECL + "[(classify := make()) for i in items]\nclassify(x, 2)\n"
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 1, AMB)], [],
    )


# ── global / nonlocal and module-level rebinding ─────────────────────────────


def test_global_in_any_scope_makes_the_whole_source_ambiguous():
    source = DECL + "def h():\n    global classify\nclassify(x, 2)\n"
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 4, AMB)], [],
    )


def test_nonlocal_on_the_name_makes_the_whole_source_ambiguous():
    source = DECL + (
        "def h():\n"
        "    classify = make()\n"
        "    def g():\n"
        "        nonlocal classify\n"
        "classify(x, 2)\n"
    )
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 6, AMB)], [],
    )


@pytest.mark.parametrize("source,line", [
    # Conditional definition.
    ("if FAST:\n    def classify(a, b):\n        pass\nclassify(x, 2)\n", 2),
    # try-guarded definition.
    ("try:\n    from a import classify\nexcept ImportError:\n"
     "    from b import classify\nclassify(x, 2)\n", 2),
    # Module-level reassignment.
    (DECL + "classify = wrap(classify)\nclassify(x, 2)\n", 1),
    # Module-level del.
    (DECL + "del classify\n", 1),
    # A second module-level definition.
    (DECL + DECL + "classify(x, 2)\n", 1),
    # A module-level class of the same name.
    ("class classify:\n    pass\nclassify(x, 2)\n", 1),
])
def test_module_level_rebinding_keeps_whole_source_ambiguous(source, line):
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", line, AMB)], [],
    )


def test_escape_inside_a_method_makes_the_whole_source_ambiguous():
    source = DECL + (
        "class R:\n"
        "    def go(self):\n"
        "        return [classify]\n"
        "classify(x, 2)\n"
    )
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 5, AMB)], [],
    )


def test_load_resolving_to_a_local_binding_is_not_an_escape():
    source = DECL + (
        "def h(classify):\n"
        "    return classify\n"
        "classify(x, 2)\n"
    )
    assert _run(source) == ("RECOGNIZED", "NO_VIOLATION", [], [])


def test_local_del_is_a_local_binding_only():
    source = DECL + (
        "def h():\n"
        "    classify = make()\n"
        "    del classify\n"
        "classify(x, 2)\n"
    )
    assert _run(source) == ("RECOGNIZED", "NO_VIOLATION", [], [])


# ── Dynamic constructs ───────────────────────────────────────────────────────


@pytest.mark.parametrize("construct", [
    "exec(code)",
    "eval(code)",
    "globals()['classify'] = other",
    "locals()['classify'] = other",
    "vars()['classify'] = other",
    "ns = globals",
    "__builtins__.classify = other",
    "import builtins",
    "from builtins import print",
    "from helpers import *",
    "sys.modules[__name__].classify = other",
])
def test_dynamic_construct_makes_the_whole_source_ambiguous(construct):
    source = DECL + construct + "\nclassify(x, 2)\n"
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 3, AMB)], [],
    )


def test_dynamic_construct_inside_a_function_is_still_unbounded():
    source = DECL + "def h():\n    exec(code)\nclassify(x, 2)\n"
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 4, AMB)], [],
    )


def test_dynamic_construct_never_yields_clean_without_any_call():
    source = DECL + "exec(code)\n"
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("call", 3, AMB)], [],
    )


# ── Unchanged surfaces ───────────────────────────────────────────────────────


def test_method_and_attribute_calls_are_not_sources():
    source = "obj.classify(x, 9)\nself.classify(x, 9)\n"
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED",
        [("call", None, "SOURCE_NOT_FOUND")], [],
    )


def test_symbol_source_keeps_rebound_anywhere_reading():
    # §3a leaves the symbol source on §3 wording: a class-body assignment of
    # the symbol still makes it ambiguous.
    source = (
        "ROUTER_DEADLINE_S = 3\n"
        "class R:\n"
        "    ROUTER_DEADLINE_S = 9\n"
        + DECL + "classify(x, 2)\n"
    )
    status, _, unknown, _ = _run(source, ROUTER)
    assert status == "MATCHER_UNEVALUATED"
    assert ("symbol", 1, AMB) in unknown


def test_call_with_symbol_argument_in_method_still_resolves_symbol():
    source = (
        "ROUTER_DEADLINE_S = 9\n" + DECL
        + "class R:\n"
        "    def classify(self, a, b):\n"
        "        pass\n"
        "    def go(self):\n"
        "        return classify(self, ROUTER_DEADLINE_S)\n"
    )
    status, outcome, unknown, exceeding = _run(source, ROUTER)
    assert (status, outcome, unknown) == ("RECOGNIZED", "VIOLATION", [])
    assert exceeding == [(1, "9"), (8, "9")]

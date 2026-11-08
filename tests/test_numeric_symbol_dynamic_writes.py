"""ADR-034 §3b: dynamic writes to the governed symbol (owner ruling S1).

Pins finding F-G1-1 (#752) and its correction. If the governed file contains
any construct in the closed list S1-a to S1-g, the ``symbol`` source is
``UNKNOWN`` / ``AMBIGUOUS_BINDING``, never clean. The "not affected" idioms
of §3b keep their recognized result. The call source is unchanged (§3a).
"""

from __future__ import annotations

import pytest

from mneme.numeric_rule import NumericContract, evaluate_source

SYMBOL_ONLY = NumericContract(max="10", unit="seconds", symbol="TIMEOUT_S")
ROUTER = NumericContract(
    max="5", unit="s", symbol="ROUTER_DEADLINE_S",
    call_function="classify", call_position=1,
)
AMB = "AMBIGUOUS_BINDING"
DECL_OK = "TIMEOUT_S = 10\n"
DECL_OVER = "TIMEOUT_S = 60\n"


def _run(source: str, contract: NumericContract = SYMBOL_ONLY):
    result = evaluate_source(contract, source.encode("utf-8"))
    return (
        result.status,
        result.outcome,
        [(u.kind, u.line, u.reason) for u in result.unknown_sources],
        [(e.line, e.value) for e in result.exceeding_sources],
    )


# ── F-G1-1: the discovered bypass ────────────────────────────────────────────


def test_f_g1_1_globals_write_is_never_clean():
    # Before S1 this was RECOGNIZED / NO_VIOLATION: a clean PASS while the
    # runtime value is 60.
    source = DECL_OK + "globals()['TIMEOUT_S'] = 60\n"
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("symbol", 1, AMB)], [],
    )


def test_baseline_without_dynamic_construct_stays_recognized():
    assert _run(DECL_OK) == ("RECOGNIZED", "NO_VIOLATION", [], [])
    assert _run(DECL_OVER) == ("RECOGNIZED", "VIOLATION", [], [(1, "60")])


# ── Each S1 construct ────────────────────────────────────────────────────────


@pytest.mark.parametrize("construct", [
    # S1-a: namespace-mapping and source-executing names, in any context.
    "globals()['TIMEOUT_S'] = 60",
    "vars()['TIMEOUT_S'] = 60",
    "locals()['TIMEOUT_S'] = 60",
    "exec('TIMEOUT_S = 60')",
    "eval('(TIMEOUT_S := 60)')",
    "ns = globals",
    "def h():\n    return vars",
    "__builtins__.TIMEOUT_S = 60",
    # S1-b: star import.
    "from settings import *",
    # S1-c: attribute store, augmented store or delete of the symbol.
    "import sys\nsys.modules[__name__].TIMEOUT_S = 60",
    "import me\nme.TIMEOUT_S = 60",
    "import me\nme.TIMEOUT_S += 50",
    "import me\ndel me.TIMEOUT_S",
    "from sys import modules\nmodules[__name__].TIMEOUT_S = 60",
    "def patch(module):\n    module.TIMEOUT_S = 60",
    # S1-d: setters naming the symbol, with a computed name, unpacked, or
    # aliased / passed as values.
    "import me\nsetattr(me, 'TIMEOUT_S', 60)",
    "import me\ndelattr(me, 'TIMEOUT_S')",
    "import me\nname = 'TIMEOUT_S'\nsetattr(me, name, 60)",
    "import me\nsetattr(me, *pair)",
    "import me\nsetattr(me, **kw)",
    "import me\nme.__setattr__('TIMEOUT_S', 60)",
    "import me\nobject.__setattr__(me, 'TIMEOUT_S', 60)",
    "import types, me\ntypes.ModuleType.__setattr__(me, 'TIMEOUT_S', 60)",
    "import me\ns = setattr\ns(me, 'TIMEOUT_S', 60)",
    "fetch = getattr",
    "import me\nf = me.__setattr__",
    # S1-e: namespace-exposing attributes.
    "import sys\nsys.modules[__name__].__dict__['TIMEOUT_S'] = 60",
    "def g():\n    pass\ng.__globals__['TIMEOUT_S'] = 60",
    "import sys\nsys._getframe().f_globals['TIMEOUT_S'] = 60",
    "import sys\nsys._getframe().f_locals",
    # S1-f: builtins and computed imports.
    "import builtins",
    "from builtins import print",
    "mod = __import__(name)",
    "from importlib import import_module\nmod = import_module(__name__)",
    "mod = __import__('builtins')",
    # S1-g: getattr with a computed or namespace name, and namespace names
    # handed to any call as strings.
    "import me\nk = '__dict__'\ngetattr(me, k)['TIMEOUT_S'] = 60",
    "import me\ngetattr(me, '__dict__')['TIMEOUT_S'] = 60",
    "import os\nrun = getattr(os, 'exec')",
    "import operator, me\noperator.attrgetter('__dict__')(me)['TIMEOUT_S'] = 60",
    "import operator, me\noperator.methodcaller('__setattr__', 'TIMEOUT_S', 60)(me)",
    "from operator import attrgetter\nget = attrgetter('mod.__globals__')",
])
def test_s1_construct_makes_the_symbol_source_ambiguous(construct):
    source = DECL_OK + construct + "\n"
    status, outcome, unknown, exceeding = _run(source)
    assert (status, outcome, exceeding) == ("MATCHER_UNEVALUATED", "UNEVALUATED", [])
    assert unknown == [("symbol", 1, AMB)]


def test_s1_construct_hides_no_violation_and_never_passes():
    # A recognized above-bound value plus an S1 construct is unevaluated for
    # that source, as a second assignment already is (§3, V15).
    source = DECL_OVER + "exec(code)\n"
    assert _run(source) == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("symbol", 1, AMB)], [],
    )


def test_s1_construct_before_the_declaration_reports_its_own_line():
    source = "exec(code)\n" + DECL_OK
    assert _run(source)[2] == [("symbol", 1, AMB)]
    source = "import builtins\n\n" + DECL_OK
    assert _run(source)[2] == [("symbol", 1, AMB)]
    source = "x = 1\nglobals()\n" + DECL_OK
    assert _run(source)[2] == [("symbol", 2, AMB)]


def test_s1_construct_without_declaration_is_ambiguous_not_missing():
    # The symbol may be created through the namespace: AMBIGUOUS_BINDING
    # outranks SOURCE_NOT_FOUND (§4 reason priority).
    assert _run("globals()['TIMEOUT_S'] = 60\n") == (
        "MATCHER_UNEVALUATED", "UNEVALUATED", [("symbol", 1, AMB)], [],
    )


def test_s1_construct_inside_a_function_still_counts():
    source = DECL_OK + "def h():\n    exec(code)\n"
    assert _run(source)[2] == [("symbol", 1, AMB)]


# ── "Not affected" idioms of §3b ─────────────────────────────────────────────


@pytest.mark.parametrize("idiom", [
    # Reads of the symbol, including passing it as a value.
    "y = TIMEOUT_S * 2",
    "def run():\n    return call(timeout=TIMEOUT_S)",
    "values = [TIMEOUT_S]",
    # getattr with another constant name.
    "import os\nsep = getattr(os, 'sep')",
    "value = getattr(obj, 'retries', None)",
    # Setters with a constant name other than the symbol.
    "setattr(obj, 'retries', 3)",
    "delattr(obj, 'retries')",
    "class A:\n    def __init__(self):\n        object.__setattr__(self, 'x', 1)",
    "obj.__setattr__('retries', 3)",
    # Attribute writes of other names.
    "obj.retries = 3",
    "obj.TIMEOUT_S_EXTRA = 3",
    "label = obj.TIMEOUT_S",
    # sys.modules reads with no write.
    "import sys\nm = sys.modules[__name__]",
    "import sys\nsys.exit",
    # Constant module imports.
    "import json\njson.loads('{}')",
    "from importlib import import_module\nmod = import_module('json')",
    "mod = __import__('json')",
    # S1-a names as plain data strings.
    "code = compile(source, 'f', 'exec')",
    "tree = compile(source, 'f', mode='eval')",
    "HELP = 'globals and vars'",
    'MAPPING = {"key": "__dict__"}',
    'same = attr == "__setattr__"',
    'def h():\n    """Reads __dict__ and "__globals__"."""\n    return 1',
    "if __name__ == '__main__':\n    main()",
])
def test_not_affected_idiom_keeps_recognized_result(idiom):
    assert _run(DECL_OK + idiom + "\n") == ("RECOGNIZED", "NO_VIOLATION", [], [])
    status, outcome, unknown, exceeding = _run(DECL_OVER + idiom + "\n")
    assert (status, outcome, unknown) == ("RECOGNIZED", "VIOLATION", [])
    assert exceeding[0] == (1, "60")


def test_accepted_false_incomplete_is_unevaluated_not_clean():
    # §3b: S1 is conservative. A computed-name forward in a custom
    # __setattr__ never touches the symbol but is still unevaluated.
    source = (
        DECL_OK
        + "class A:\n"
        "    def __setattr__(self, name, value):\n"
        "        super().__setattr__(name, value)\n"
    )
    assert _run(source)[0] == "MATCHER_UNEVALUATED"


# ── Interaction with the call source ─────────────────────────────────────────


def test_call_with_bare_symbol_argument_inherits_the_ambiguous_symbol():
    source = (
        "ROUTER_DEADLINE_S = 3\n"
        "def classify(a, b):\n    pass\n"
        "classify(x, ROUTER_DEADLINE_S)\n"
        "globals()['ROUTER_DEADLINE_S'] = 60\n"
    )
    status, outcome, unknown, _ = _run(source, ROUTER)
    assert (status, outcome) == ("MATCHER_UNEVALUATED", "UNEVALUATED")
    assert ("symbol", 1, AMB) in unknown


def test_call_source_violation_still_reported_with_ambiguous_symbol():
    source = (
        "ROUTER_DEADLINE_S = 3\n"
        "def classify(a, b):\n    pass\n"
        "classify(x, 9)\n"
        "import me\nme.ROUTER_DEADLINE_S = 60\n"
    )
    status, outcome, unknown, exceeding = _run(source, ROUTER)
    assert (status, outcome) == ("PARTIAL", "VIOLATION")
    assert ("symbol", 1, AMB) in unknown
    assert exceeding == [(4, "9")]

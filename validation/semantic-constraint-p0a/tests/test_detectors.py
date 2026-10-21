"""Unit tests for the P0-A offline prototype detectors M1 to M3.

These use small synthetic snippets, not the frozen fixtures, so they pin the
declared recognition contract rather than the frozen results. Run explicitly
(not collected by default CI):

    python -m pytest validation/semantic-constraint-p0a/tests -v
"""

import ast
import sys
from pathlib import Path

import pytest

P0A_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P0A_DIR))

from detectors import common, m1_lexical, m2_static_bound, m3_fallback  # noqa: E402
from detectors.common import NO_VIOLATION, UNEVALUATED, VIOLATION, Finding  # noqa: E402

PATH = "src/router.py"
TEMPLATE = (P0A_DIR / "set1" / "template" / "router_base.py").read_text(encoding="utf-8")


def with_constant(expr: str) -> str:
    return TEMPLATE.replace("ROUTER_DEADLINE_S = 5.0", f"ROUTER_DEADLINE_S = {expr}")


def with_handler(header: str, body: str) -> str:
    return TEMPLATE.replace("    except TimeoutError:\n        return FALLBACK_ROUTE", f"    {header}\n        {body}")


# ── Common ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("module", [m1_lexical, m2_static_bound, m3_fallback])
def test_every_detector_returns_one_valid_verdict_per_sub_constraint(module):
    result = module.detect(TEMPLATE, PATH)
    assert sorted(result) == ["C1", "C2", "C3"]
    assert all(f.verdict in common.VERDICTS for f in result.values())


@pytest.mark.parametrize("module", [m1_lexical, m2_static_bound, m3_fallback])
@pytest.mark.parametrize("path", ["docs/notes.md", "tests/router.py", "src/router.txt"])
def test_out_of_scope_paths_are_unevaluated(module, path):
    assert {f.verdict for f in module.detect(TEMPLATE, path).values()} == {UNEVALUATED}


@pytest.mark.parametrize("module", [m1_lexical, m2_static_bound, m3_fallback])
def test_unparseable_source_is_unevaluated_not_a_verdict(module):
    result = module.detect("def route(:\n", PATH)
    assert VIOLATION not in {f.verdict for f in result.values()}
    assert NO_VIOLATION not in {f.verdict for f in result.values()}


@pytest.mark.parametrize("module", [m1_lexical, m2_static_bound, m3_fallback])
def test_detectors_never_execute_source(module, tmp_path):
    marker = tmp_path / "executed"
    source = f"open({str(marker)!r}, 'w').write('x')\n" + TEMPLATE
    module.detect(source, PATH)
    assert not marker.exists()


FORBIDDEN_CALLS = {"exec", "eval", "__import__", "import_module", "run", "Popen", "system", "urlopen", "create_connection"}
FORBIDDEN_IMPORTS = {"subprocess", "importlib", "socket", "urllib", "http", "requests", "anthropic", "openai", "runpy"}


@pytest.mark.parametrize("module", [common, m1_lexical, m2_static_bound, m3_fallback])
def test_detector_source_has_no_execution_import_or_network_path(module):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            assert name not in FORBIDDEN_CALLS, f"{module.__name__} calls {name}"
        if isinstance(node, ast.Import):
            assert not {a.name.split(".")[0] for a in node.names} & FORBIDDEN_IMPORTS
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in FORBIDDEN_IMPORTS


def test_gate_with_no_introduced_lines_is_unevaluated_never_stopped():
    audit = Finding(VIOLATION, "x", (10,))
    assert common.gate_finding(audit, set()).verdict == UNEVALUATED


def test_gate_keeps_only_introduced_violations():
    audit = Finding(VIOLATION, "x", (3, 10))
    assert common.gate_finding(audit, {3}).verdict == VIOLATION
    assert common.gate_finding(audit, {5}).verdict == NO_VIOLATION
    assert common.gate_finding(Finding(UNEVALUATED, "x"), {5}).verdict == UNEVALUATED


# ── M1 ──────────────────────────────────────────────────────────────────────


def test_m1_matches_name_token():
    src = "DISABLE_ROUTER_TIMEOUT = True\n" + TEMPLATE
    finding = m1_lexical.detect(src, PATH)["C1"]
    assert finding.verdict == VIOLATION and finding.lines == (1,)


@pytest.mark.parametrize("snippet", [
    "# DISABLE_ROUTER_TIMEOUT\n",
    "X = 'DISABLE_ROUTER_TIMEOUT'\n",
    'X = f"{1} DISABLE_ROUTER_TIMEOUT"\n',
    '"""DISABLE_ROUTER_TIMEOUT"""\n',
    "DISABLE_ROUTER_TIMEOUT_DOCS = 1\n",
    "XDISABLE_ROUTER_TIMEOUT = 1\n",
    "disable_router_timeout = 1\n",
])
def test_m1_ignores_comments_strings_and_other_identifiers(snippet):
    assert m1_lexical.detect(snippet + TEMPLATE, PATH)["C1"].verdict == NO_VIOLATION


def test_m1_matches_attribute_and_keyword_uses():
    assert m1_lexical.detect("x = config.DISABLE_ROUTER_TIMEOUT\n" + TEMPLATE, PATH)["C1"].verdict == VIOLATION
    assert m1_lexical.detect("f(DISABLE_ROUTER_TIMEOUT=1)\n" + TEMPLATE, PATH)["C1"].verdict == VIOLATION


def test_m1_does_not_target_c2_or_c3():
    result = m1_lexical.detect(TEMPLATE, PATH)
    assert result["C2"].verdict == result["C3"].verdict == UNEVALUATED


# ── M2 ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("expr,c1,c2", [
    ("5.0", NO_VIOLATION, NO_VIOLATION),
    ("5", NO_VIOLATION, NO_VIOLATION),
    ("0.5", NO_VIOLATION, NO_VIOLATION),
    ("10 / 2", NO_VIOLATION, NO_VIOLATION),
    ("5.5", NO_VIOLATION, VIOLATION),
    ("2 ** 3", NO_VIOLATION, VIOLATION),
    ("(1 + 2) * 3", NO_VIOLATION, VIOLATION),
    ("None", VIOLATION, NO_VIOLATION),
    ("0", VIOLATION, NO_VIOLATION),
    ("-1", VIOLATION, NO_VIOLATION),
    ("1e999", VIOLATION, NO_VIOLATION),
    ("True", VIOLATION, NO_VIOLATION),
    ("'5'", VIOLATION, NO_VIOLATION),
    ("float('inf')", UNEVALUATED, UNEVALUATED),
    ("OTHER", UNEVALUATED, UNEVALUATED),
    ("OTHER / 1000", UNEVALUATED, UNEVALUATED),
    ("5 if X else 60", UNEVALUATED, UNEVALUATED),
    ("1 / 0", UNEVALUATED, UNEVALUATED),
    ("2 ** 100", UNEVALUATED, UNEVALUATED),
    ("True * 5", UNEVALUATED, UNEVALUATED),
    ("math.inf", UNEVALUATED, UNEVALUATED),
])
def test_m2_recognized_and_unrecognized_constant_forms(expr, c1, c2):
    result = m2_static_bound.detect(with_constant(expr), PATH)
    assert (result["C1"].verdict, result["C2"].verdict) == (c1, c2)


def test_m2_disabled_deadline_is_c1_only_per_amb1():
    result = m2_static_bound.detect(with_constant("None"), PATH)
    assert result["C2"].reason.startswith("DISABLED_ATTRIBUTED_TO_C1")


@pytest.mark.parametrize("call,c2", [
    ("classify(request, 60)", VIOLATION),
    ("classify(request, 2)", NO_VIOLATION),
    ("classify(request, 30 * 2)", VIOLATION),
    ("classify(request, deadline)", UNEVALUATED),
    ("classify(request)", UNEVALUATED),
    ("classify(*args)", UNEVALUATED),
    ("classify(request, ROUTER_DEADLINE_S * 20)", UNEVALUATED),
])
def test_m2_reads_the_call_site_deadline(call, c2):
    src = TEMPLATE.replace("classify(request, ROUTER_DEADLINE_S)", call)
    assert m2_static_bound.detect(src, PATH)["C2"].verdict == c2


def test_m2_violation_at_call_site_wins_over_compliant_constant():
    src = TEMPLATE.replace("classify(request, ROUTER_DEADLINE_S)", "classify(request, 60)")
    finding = m2_static_bound.detect(src, PATH)["C2"]
    assert finding.verdict == VIOLATION and finding.lines == (10,)


@pytest.mark.parametrize("extra", [
    "ROUTER_DEADLINE_S = 60.0\n",
    "ROUTER_DEADLINE_S += 1\n",
    "def f():\n    global ROUTER_DEADLINE_S\n    ROUTER_DEADLINE_S = 60\n",
    "from config import ROUTER_DEADLINE_S\n",
])
def test_m2_rebinding_the_constant_is_unevaluated_unless_a_recognized_value_violates(extra):
    result = m2_static_bound.detect(TEMPLATE + "\n" + extra, PATH)
    assert result["C2"].verdict == UNEVALUATED


def test_m2_classify_escaping_as_a_value_is_unevaluated():
    src = TEMPLATE + "\nHOOK = classify\n"
    assert m2_static_bound.detect(src, PATH)["C2"].verdict == UNEVALUATED


def test_m2_no_classify_call_is_unevaluated():
    src = "ROUTER_DEADLINE_S = 5.0\n"
    assert m2_static_bound.detect(src, PATH)["C2"].verdict == UNEVALUATED


# ── M3 ──────────────────────────────────────────────────────────────────────


def test_m3_template_is_recognized_fallback_structure():
    finding = m3_fallback.detect(TEMPLATE, PATH)["C3"]
    assert finding.verdict == NO_VIOLATION and "static structure only" in finding.reason


@pytest.mark.parametrize("header", ["except TimeoutError:", "except OSError:", "except Exception:", "except BaseException:", "except TimeoutError as e:"])
def test_m3_declared_handler_returning_fallback_is_no_violation(header):
    assert m3_fallback.detect(with_handler(header, "return FALLBACK_ROUTE"), PATH)["C3"].verdict == NO_VIOLATION


@pytest.mark.parametrize("header,body", [("except TimeoutError:", "raise"), ("except TimeoutError as e:", "raise e")])
def test_m3_reraising_handler_is_violation(header, body):
    assert m3_fallback.detect(with_handler(header, body), PATH)["C3"].verdict == VIOLATION


def test_m3_no_handler_is_violation():
    src = "FALLBACK_ROUTE = 'x'\n\n\ndef route(request, classify):\n    return classify(request, 5)\n"
    assert m3_fallback.detect(src, PATH)["C3"].verdict == VIOLATION


def with_guard(guard: str) -> str:
    return TEMPLATE.replace("    try:", guard + "    try:")


def test_m3_case_a_guard_before_handler_is_template_compatible():
    src = with_guard("    if not request:\n        return FALLBACK_ROUTE\n")
    assert m3_fallback.detect(src, PATH)["C3"].verdict == NO_VIOLATION


# Post-hoc unit tests from the owner review of #586. They are not frozen
# cases and are never scored: any guard other than case A's exact form makes
# C3 UNEVALUATED, because an early return can keep a request from reaching
# classify at all.
@pytest.mark.parametrize("guard", [
    '    if request:\n        return "wrong"\n',
    '    if not request:\n        return "wrong"\n',
    "    if request is None:\n        return FALLBACK_ROUTE\n",
    "    if not request:\n        return FALLBACK_ROUTE\n    else:\n        pass\n",
    "    if not request:\n        return FALLBACK_ROUTE\n    if not request:\n        return FALLBACK_ROUTE\n",
    "    x = 1\n",
])
def test_m3_other_guards_are_unevaluated_never_a_pass(guard):
    assert m3_fallback.detect(with_guard(guard), PATH)["C3"].verdict == UNEVALUATED


def test_m3_owner_review_counterexample_is_unevaluated():
    src = with_guard('    if request:\n        return "wrong"\n')
    assert '    if request:\n        return "wrong"\n    try:\n        return classify(request, ROUTER_DEADLINE_S)\n    except TimeoutError:\n        return FALLBACK_ROUTE' in src
    assert m3_fallback.detect(src, PATH)["C3"].verdict == UNEVALUATED


@pytest.mark.parametrize("header,body", [
    ("except TimeoutError:", "return _fallback()"),
    ("except TimeoutError:", "return 'other'"),
    ("except TimeoutError:", "raise ValueError()"),
    ("except TimeoutError:", "pass"),
    ("except TimeoutError as e:", "raise RuntimeError() from e"),
    ("except ValueError:", "return FALLBACK_ROUTE"),
    ("except (TimeoutError, ValueError):", "return FALLBACK_ROUTE"),
    ("except:", "return FALLBACK_ROUTE"),
    ("except builtins.TimeoutError:", "return FALLBACK_ROUTE"),
])
def test_m3_unrecognized_handlers_are_unevaluated_never_violation(header, body):
    assert m3_fallback.detect(with_handler(header, body), PATH)["C3"].verdict == UNEVALUATED


@pytest.mark.parametrize("src", [
    TEMPLATE.replace("def route(request, classify):", "def route(request, classify, extra=None):"),
    TEMPLATE.replace("def route(request, classify):", "@wrap\ndef route(request, classify):"),
    TEMPLATE.replace("        return classify(request, ROUTER_DEADLINE_S)", "        result = classify(request, ROUTER_DEADLINE_S)\n        return result"),
    TEMPLATE.replace("        return classify(request, ROUTER_DEADLINE_S)", "        return helper(classify)"),
    TEMPLATE.replace("        return FALLBACK_ROUTE", "        return FALLBACK_ROUTE\n    finally:\n        pass"),
    TEMPLATE.replace("    try:", "    with guard():\n        pass\n    try:"),
    TEMPLATE.replace("    try:", "    classify = wrap(classify)\n    try:"),
    TEMPLATE + "\nTimeoutError = ValueError\n",
    TEMPLATE + "\nFALLBACK_ROUTE = None\n",
    TEMPLATE + "\n\ndef route(request, classify):\n    return None\n",
])
def test_m3_forms_outside_the_template_are_unevaluated(src):
    assert m3_fallback.detect(src, PATH)["C3"].verdict == UNEVALUATED


def test_m3_does_not_target_c1_or_c2():
    result = m3_fallback.detect(TEMPLATE, PATH)
    assert result["C1"].verdict == result["C2"].verdict == UNEVALUATED

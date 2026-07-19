"""
benchmark_verifier.py — Apply assertions to a structured benchmark output.

Verifier semantics (locked for v1.1 Step 2):

* ``forbidden_dependency`` — case-insensitive substring of the assertion
  ``value`` against each entry in ``dependencies_added``.
* ``forbidden_path_pattern`` — plain (case-sensitive) substring of the
  assertion ``value`` against each entry in ``files_changed``.
  No glob, no regex, no fnmatch.
* ``refused == True`` short-circuits to PASS. Assertions are not inspected
  and ``assertion_results`` is left empty.

The verifier deliberately does not consult project memory. Assertions are
scenario-level metadata declared in ``scenario.json``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mneme.benchmark_schemas import Assertion, StructuredOutput


@dataclass
class AssertionResult:
    """Outcome of one Assertion against one StructuredOutput.

    Attributes:
        assertion: The assertion that was applied.
        passed:    True iff no entries in the relevant field matched
                   ``assertion.value``.
        triggers:  The matching entries (paths or dep names). Empty when
                   ``passed`` is True.
    """

    assertion: Assertion
    passed: bool
    triggers: list[str] = field(default_factory=list)


@dataclass
class VerificationResult:
    """Aggregate result for one structured output + all assertions.

    Attributes:
        refused:            True iff the input ``StructuredOutput.refused``
                            was True (refusal short-circuits to PASS).
        assertion_results:  One AssertionResult per assertion. Empty when
                            ``refused`` is True (assertions not inspected).
    """

    refused: bool
    assertion_results: list[AssertionResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        if self.refused:
            return True
        return all(r.passed for r in self.assertion_results)

    @property
    def violations(self) -> list[AssertionResult]:
        return [r for r in self.assertion_results if not r.passed]


def _dependency_match(value: str, dep: str) -> bool:
    return value.lower() in dep.lower()


def _path_match(value: str, path: str) -> bool:
    return value in path


def verify(
    output: StructuredOutput,
    assertions: list[Assertion],
) -> VerificationResult:
    """Apply assertions to a structured output.

    Args:
        output:     Parsed StructuredOutput from the agent under test.
        assertions: Scenario-level assertions to enforce.

    Returns:
        A VerificationResult. If ``output.refused`` is True the result is
        an immediate PASS with no per-assertion records.
    """
    if output.refused:
        return VerificationResult(refused=True, assertion_results=[])

    results: list[AssertionResult] = []
    for a in assertions:
        if a.type == "forbidden_dependency":
            triggers = [
                d for d in output.dependencies_added if _dependency_match(a.value, d)
            ]
        elif a.type == "forbidden_path_pattern":
            triggers = [p for p in output.files_changed if _path_match(a.value, p)]
        else:  # pragma: no cover — Assertion.from_dict already filters.
            triggers = []
        results.append(AssertionResult(
            assertion=a,
            passed=len(triggers) == 0,
            triggers=triggers,
        ))
    return VerificationResult(refused=False, assertion_results=results)

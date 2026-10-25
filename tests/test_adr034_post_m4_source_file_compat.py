"""Post-M4 compatibility adapter: ``--source-file`` trust on the current build.

**Not M4 blind scoring and not G2 validation evidence.** This adapter only
shows that G1 complete-source results stay trusted after ADR-034 G2-1, as the
G2-1 charter §5.1 erratum (owner ruling G2C-R1, MnemeHQ/mneme#638) requires.
The M4 instrument (``benchmarks/adr034_m4/``), its sealed corpus, criteria,
pins and results are untouched; M4's PASS (#628) stands as evidence about the
build it pinned.

Every case is SYNTHETIC, written from ADR-034 and the public G1 regressions.
Each case runs the shipped ``mneme check --source-file`` in a child
interpreter on the current tree. The trust validator is then applied with the
``expected_input`` that follows from the adapter's *own* invocation metadata
(the transport it ran), never from the returned payload.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from mneme.integrations.claude_code.hook import assess_verdict
from mneme.numeric_rule import NumericContract
from tests.canonical_fixtures import canonical_document

REPO_ROOT = Path(__file__).resolve().parents[1]

# The adapter's invocation metadata: which checker transport it ran decides
# the requested input kind (charter §5.1 erratum item 1).
EXPECTED_INPUT_BY_TRANSPORT = {
    "--input": "input",
    "--source-file": "source_file",
    "--proposed-new-file": "proposed_new_file",
}

CONTRACT = NumericContract(
    max="5", unit="seconds", symbol="SYN_DEADLINE_S",
    call_function="syn_call", call_position=1,
)


@dataclass(frozen=True)
class Invocation:
    case_id: str
    transport: str
    argv: tuple

    @property
    def expected_input(self) -> str:
        return EXPECTED_INPUT_BY_TRANSPORT[self.transport]


# (case_id, relative path, source, numeric include, matcher status, reason, verdict)
CASES = [
    ("syn-c01", "src/within.py", "SYN_DEADLINE_S = 3\nsyn_call(x, 2)\n",
     "src/**", "RECOGNIZED", None, "PASS"),
    ("syn-c02", "src/above.py", "SYN_DEADLINE_S = 30\nsyn_call(x, 2)\n",
     "src/**", "RECOGNIZED", None, "FAIL"),
    ("syn-c03", "src/partial.py", "SYN_DEADLINE_S = 30\nsyn_call(x, y)\n",
     "src/**", "PARTIAL", "UNRECOGNIZED_FORM", "FAIL"),
    ("syn-c04", "src/missing.py", "SYN_DEADLINE_S = 3\n",
     "src/**", "MATCHER_UNEVALUATED", "SOURCE_NOT_FOUND", "PASS"),
    ("syn-c05", "src/broken.py", "def broken(:\n",
     "src/**", "MATCHER_UNEVALUATED", "PARSE_FAILURE", "PASS"),
    ("syn-c06", "lib/excluded.py", "SYN_DEADLINE_S = 30\nsyn_call(x, 2)\n",
     "src/**", None, None, "PASS"),
    ("syn-c07", "src/no_numeric.py", "SYN_DEADLINE_S = 30\n",
     None, None, None, "PASS"),
]


def _project(root: Path, include) -> Path:
    rules = [] if include is None else [{
        "type": "FORBID_NUMERIC_ABOVE", "value": CONTRACT.canonical_value(),
        "include_paths": [include],
    }]
    memory = root / ".mneme" / "project_memory.json"
    memory.parent.mkdir(parents=True)
    memory.write_text(json.dumps(canonical_document({
        "meta": {"name": "post-m4-compat", "description": "SYNTHETIC"},
        "items": [],
        "decisions": [{
            "id": "SYN-1", "decision": "Synthetic deadline", "rationale": "r",
            "scope": ["synthetic"], "rules": rules,
            "created_at": "2026-10-24", "updated_at": "2026-10-24", "status": "active",
        }],
    })), encoding="utf-8")
    return memory


def _run(invocation: Invocation, cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "mneme", *invocation.argv],
        capture_output=True, text=True, check=False, cwd=cwd, env=env, timeout=60,
    )


def _source_file_case(tmp_path: Path, case) -> tuple:
    case_id, rel, source, include, *_ = case
    root = tmp_path / case_id
    memory = _project(root, include)
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(source.encode("utf-8"))
    invocation = Invocation(case_id, "--source-file", (
        "check", "--memory", str(memory), "--source-file", str(path),
        "--query", "synthetic", "--mode", "strict", "--json",
    ))
    return invocation, _run(invocation, root)


def trust(invocation: Invocation, proc: subprocess.CompletedProcess):
    """Apply the shipped validator with the kind this adapter requested."""
    return assess_verdict(
        proc.stdout, proc.returncode, "strict",
        expected_input=invocation.expected_input,
    )


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_source_file_results_stay_trusted_on_the_current_build(tmp_path, case):
    _, _, _, include, status, reason, verdict = case
    invocation, proc = _source_file_case(tmp_path, case)
    assessment = trust(invocation, proc)
    assert assessment.payload is not None, assessment.problem
    payload = assessment.payload
    assert payload["subject"]["input_kind"] == "complete_source_file"
    assert payload["verdict"] == verdict
    numeric = [i for i in payload["applicability"] if i["rule_type"] == "FORBID_NUMERIC_ABOVE"]
    if status is None:
        assert all("matcher_status" not in item for item in numeric)
    else:
        trace, = numeric
        assert (trace["matcher_status"], trace["primary_reason"]) == (status, reason)


@pytest.mark.parametrize("expected_input", ["input", "proposed_new_file"])
def test_the_same_payloads_are_untrusted_without_the_explicit_request(tmp_path, expected_input):
    for case in CASES:
        _, proc = _source_file_case(tmp_path / expected_input, case)
        assessment = assess_verdict(proc.stdout, proc.returncode, "strict",
                                    expected_input=expected_input)
        assert assessment.payload is None and assessment.inconsistent, case[0]


def test_the_payload_never_authorizes_its_own_kind(tmp_path):
    """A --source-file invocation whose payload claims another kind is rejected."""
    invocation, proc = _source_file_case(tmp_path, CASES[1])
    payload = json.loads(proc.stdout)
    payload["subject"]["input_kind"] = "proposed_new_source"
    forged = subprocess.CompletedProcess(proc.args, proc.returncode, json.dumps(payload), "")
    assert trust(invocation, forged).payload is None


def test_adapter_requests_follow_the_transport_only():
    assert EXPECTED_INPUT_BY_TRANSPORT["--source-file"] == "source_file"
    invocation = Invocation("x", "--source-file", ())
    assert invocation.expected_input == "source_file"

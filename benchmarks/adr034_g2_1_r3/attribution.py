"""Exact ``(rule_id, rule_type)`` attribution check (ADR-034 §7c, R3 §3 G6).

The expected identity set comes from the oracle (fixture ADRs), never from
the observed record. A record earns attribution only when its checker data
is trusted and consistent; it then attributes exactly its well-formed
violation entries. The check fails on any missing, extra, duplicate or
wrong-type identity, and on any malformed entry (README I3): a missing,
empty or non-string ``rule_id`` attributes nothing, whatever its
``rule_type`` says, and no ``rule_type``-only fallback exists.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Optional


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def checker_problem(record: Any, expected_digest: Optional[str]) -> Optional[str]:
    """Why the record's checker data cannot earn attribution, or ``None``."""
    if not isinstance(record, dict):
        return "record_malformed"
    checker = record.get("checker")
    if not isinstance(checker, dict) or checker.get("trusted") is not True:
        return "checker_untrusted"
    digest = record.get("carrier_sha256")
    if expected_digest is not None and digest != expected_digest:
        return "carrier_digest_mismatch"
    subject = checker.get("subject")
    if subject is not None and (
        not isinstance(subject, dict) or subject.get("subject_sha256") != digest
    ):
        return "subject_digest_mismatch"
    if not isinstance(record.get("violations"), list):
        return "violations_malformed"
    return None


def attributed_identities(record: Any, expected_digest: Optional[str]) -> list:
    """Well-formed identities the record attributes (``[]`` if untrusted)."""
    if checker_problem(record, expected_digest) is not None:
        return []
    out = []
    for entry in record["violations"]:
        if not isinstance(entry, dict):
            continue
        rule_id, rule_type = entry.get("rule_id"), entry.get("rule_type")
        if _nonempty_str(rule_id) and _nonempty_str(rule_type):
            out.append((rule_id, rule_type))
    return out


def identity_failures(
    record: Any,
    expected: Iterable,
    expected_digest: Optional[str],
) -> list:
    """Failure codes for the exact-identity comparison; ``[]`` means pass."""
    want = {tuple(item) for item in expected}
    failures: list = []
    problem = checker_problem(record, expected_digest)
    if problem is not None:
        failures.append(problem)
    else:
        for index, entry in enumerate(record["violations"]):
            if not isinstance(entry, dict):
                failures.append(f"malformed_entry:{index}")
                continue
            if not _nonempty_str(entry.get("rule_id")):
                failures.append(f"malformed_rule_id:{index}")
            elif not _nonempty_str(entry.get("rule_type")):
                failures.append(f"malformed_rule_type:{index}")
    observed = attributed_identities(record, expected_digest)
    for identity, count in sorted(Counter(observed).items()):
        if count > 1:
            failures.append(f"duplicate_identity:{identity[0]}")
    seen = set(observed)
    want_ids = {rid: rtype for rid, rtype in want}
    for rid, rtype in sorted(seen - want):
        if rid in want_ids and (rid, want_ids[rid]) not in seen:
            failures.append(f"wrong_rule_type:{rid}:{rtype}")
        else:
            failures.append(f"extra_identity:{rid}")
    wrong_typed = {rid for rid, _ in seen - want}
    for rid, _ in sorted(want - seen):
        if rid not in wrong_typed:
            failures.append(f"missing_identity:{rid}")
    return failures

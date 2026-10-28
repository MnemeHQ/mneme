"""Frozen R3 contract constants (R3 §3, AT-SI amendment §2-§3, R1/R2 §4-§5)."""

from __future__ import annotations

CASE_SCHEMA = "mneme-r3-case/v1"
EVIDENCE_SCHEMA = "mneme.hook_evidence/v1"
EVIDENCE_SURFACE = "claude_code.PreToolUse"

GATES = ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8")

# Concealed, scored floors: R1 §4 (104), R2 §4.2 (+SC, MR = 120), R3 §3 (+AT = 128).
CLASS_FLOORS = {
    "V": 15, "VP": 8, "C": 15, "US": 8, "UF": 8, "UP": 6, "X": 6, "L": 18,
    "LIT": 6, "W": 6, "P": 8, "SC": 10, "MR": 6, "AT": 8,
}
TOTAL_FLOOR = 128
# AT-SN is superseded by AT-SI (amendment 1, PR #701).
AT_SUBCLASS_FLOORS = {"AT-S0": 2, "AT-SI": 2, "AT-SX": 2, "AT-W0": 2}
PUBLIC_SMOKE_MAX_FRACTION = 0.10
# Owner-decrypt-verified separate public tar, frozen #703 (not concealed input).
PUBLIC_SMOKE_SHA256 = "feee204134fb4dd339f6efcbde9053c7d1f37a880f74f5ec411eb4cf2f5020a4"

# G5 scope (R1 §5, R3 §6.2: AT does not acquire hook parity).
HOOK_PARITY_CLASSES = frozenset({"P", "X", "L"})
CHECKER_PARITY_CLASSES = frozenset({"P", "X"})

NUMERIC = "FORBID_NUMERIC_ABOVE"
LITERAL = "FORBID_LITERAL"
RULE_TYPES = frozenset({NUMERIC, LITERAL})

# AMB-R2-08: the corpus `expected_cause` vocabulary mapped onto the pinned
# record's `disposition.cause` vocabulary. Fixed here, before decryption.
CAUSE_TO_RECORD = {
    "numeric_violation": "numeric_violation",
    "other_rule": "other_rule",
    "none": "no_violation",
    "numeric_unevaluated": "fail_open",
}
# Causes with no G2 record (unrouted, skipped, or no memory).
CAUSES_WITHOUT_RECORD = frozenset({"legacy_unrouted", "not_checked"})

INCLUDE_MISS_REASON = "no include selector matched"  # ADR-020; AT-SI amendment §2.3

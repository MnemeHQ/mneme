"""
evidence.py — Declared test-evidence ingestion for the P1.2 audit (ADR-024).

Security invariant (ADR-024 amendment):

    Architecture Audit does not execute code from the audited repository
    unless the user explicitly requests an execution-capable verification
    mode.

Ordinary ``mneme audit`` is PASSIVE. This module performs no subprocess
execution of any repository-controlled code — no pytest, no conftest, no
plugins, no test bodies. Pytest invocation is arbitrary code execution
(repository-controlled imports, collection hooks, fixtures and test
bodies run inside the audit process's child), so it must never happen
implicitly. Local execution is an explicitly opt-in, documented future
capability, not part of Audit.

Contract (the audited chain):

    Decision
      ↓
    stable decision identifier          (the decision record's own ``id``;
                                         the declaration lives ON the
                                         decision record in
                                         ``project_memory.json``)
      ↓
    declared test evidence              (``test_evidence`` entries —
                                         explicit, human-authored policy,
                                         never inferred)
      ↓
    passive validation                  (selector well-formedness,
                                         cross-decision ambiguity, SHA-pin
                                         staleness, test-file existence —
                                         all pure checks)
      ↓
    evidence state                      (DECLARED / STALE / INVALID /
                                         AMBIGUOUS; VERIFIED is defined
                                         but has no producer in M0)
      ↓
    evidence_sources / diagnostics      (annotation only — a merely
                                         DECLARED entry never protects)

Evidence states:

    DECLARED    an explicit decision→test-selector mapping exists and
                passes passive validation. It annotates evidence_sources
                as ``test:declared:<selector>`` but classification keeps
                Requires Modelling (deterministic intent) or Guidance
                (advisory intent).
    VERIFIED    a deterministic trusted result establishes that the exact
                selector passed against the exact repository SHA. No such
                trusted producer exists in M0 — verified evidence arrives
                with the CI-evidence ingestion task.
    STALE       the declared SHA pin does not match repository HEAD:
                ``test:stale:<selector>@<sha>``.
    INVALID     the selector is malformed or its file does not exist:
                ``test:invalid:<selector>@<code>``.
    AMBIGUOUS   the same selector is declared by more than one decision:
                ``test:invalid:<selector>@ambiguous-mapping`` — neither
                decision is protected.

A passing test is evidence only when the provenance of the passing result
is trusted; declaring it is not verifying it. Trusted verification is the
next task (CI-produced exact-SHA + exact-selector ingestion).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

_GIT_TIMEOUT_S = 30

# Fixed, deterministic reason codes used in evidence-source strings.
REASON_MALFORMED_SELECTOR = "malformed-selector"
REASON_AMBIGUOUS_MAPPING = "ambiguous-mapping"
REASON_SHA_UNAVAILABLE = "sha-unavailable"
REASON_SHA_MISMATCH = "sha-mismatch"
REASON_SELECTOR_NOT_FOUND = "selector-not-found"
REASON_NO_VERIFICATION = "no-verification"

# Evidence states.
STATE_DECLARED = "declared"
STATE_VERIFIED = "verified"
STATE_STALE = "stale"
STATE_INVALID = "invalid"


@dataclass(frozen=True)
class TestEvidenceVerification:
    """Passive verification outcome for one declared test-evidence entry.

    ``code`` is a fixed, deterministic reason code (no spaces, safe for
    evidence-source strings); ``detail`` is the human-facing explanation.
    """

    decision_id: str
    selector: str
    state: str  # "declared" | "verified" | "stale" | "invalid"
    sha: str  # exact repository HEAD SHA the validation ran against ("" if none)
    code: str
    detail: str


def _declared_entries(decision) -> list[dict]:
    """Declared test-evidence entries for one decision, conservatively read.

    The field is optional and additive: anything that is not a list of
    mappings is ignored and can never contribute evidence. The audit
    reports diagnostics for unusable entries.
    """
    entries = getattr(decision, "test_evidence", None)
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _selector_file_part(selector) -> str | None:
    """Validated repository-relative file path of a pytest node id.

    Returns the normalized file part when ``selector`` is a non-empty string
    without whitespace, carrying at least one ``::`` separator whose first
    segment is a relative path (no drive letter, no leading slash, no ``..``
    escape); ``None`` otherwise.
    """
    if not isinstance(selector, str) or not selector:
        return None
    if any(ch.isspace() for ch in selector):
        return None
    normalized = selector.replace("\\", "/")
    head = normalized.split("::")[0]
    if not head or not normalized[len(head) :].startswith("::"):
        return None
    if head.startswith("/") or (len(head) > 1 and head[1] == ":"):
        return None
    parts = [part for part in head.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


def _declared_sha(entry: dict) -> str | None:
    """Optional pinned repository SHA from one declaration, or ``None``."""
    sha = entry.get("sha")
    if not isinstance(sha, str) or not sha.strip():
        return None
    return sha.strip()


def _current_repo_sha(repo_root: Path) -> str | None:
    """Exact HEAD SHA of the audited repository, or ``None`` (fail closed).

    Runs the ``git`` binary only — never any repository-controlled code.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    sha = result.stdout.strip()
    if result.returncode != 0 or not sha:
        return None
    return sha


def verify_test_evidence(
    decisions: list,
    repo_root: str | os.PathLike[str] | None,
) -> dict[str, list[TestEvidenceVerification]]:
    """Passively validate every declared test-evidence entry. Fail closed.

    No repository-controlled code is ever executed. For each decision
    record carrying ``test_evidence`` declarations, every selector is
    checked in order:

    1. well-formed (repository-relative pytest node id);
    2. unambiguous (not declared by any other decision);
    3. resolvable: the repository HEAD SHA is available, the declared SHA
       pin (if any) matches HEAD exactly, and the selector's file exists
       inside the repository.

    The resulting state is ``declared`` (annotates, never protects),
    ``stale`` (SHA pin mismatch), or ``invalid`` (malformed selector,
    missing file, or ambiguous mapping). No ``verified`` state is produced
    in M0 — a merely declared test never moves a decision to Protected.
    """
    results: dict[str, list[TestEvidenceVerification]] = {}

    if repo_root is None:
        for decision in decisions:
            declared = _declared_entries(decision)
            if not declared:
                continue
            results[decision.id] = [
                TestEvidenceVerification(
                    decision_id=decision.id,
                    selector=(
                        entry.get("selector")
                        if isinstance(entry.get("selector"), str)
                        else ""
                    ),
                    state=STATE_INVALID,
                    sha="",
                    code=REASON_NO_VERIFICATION,
                    detail=(
                        "no repository context available; declared evidence "
                        "cannot be validated"
                    ),
                )
                for entry in declared
            ]
        return results

    root = Path(repo_root)

    # Cross-decision ambiguity: the same selector declared by two or more
    # decisions is an ambiguous mapping and protects neither.
    by_selector: dict[str, set[str]] = {}
    for decision in decisions:
        for entry in _declared_entries(decision):
            selector = entry.get("selector")
            if isinstance(selector, str) and selector:
                by_selector.setdefault(selector, set()).add(decision.id)
    ambiguous = {
        selector
        for selector, owners in by_selector.items()
        if len(owners) > 1
    }

    # One deterministic SHA snapshot per validation run.
    sha = _current_repo_sha(root)

    for decision in decisions:
        declared = _declared_entries(decision)
        if not declared:
            continue
        entries: list[TestEvidenceVerification] = []
        for entry in declared:
            selector = entry.get("selector")
            file_part = _selector_file_part(selector)
            if file_part is None:
                entries.append(TestEvidenceVerification(
                    decision_id=decision.id,
                    selector=selector if isinstance(selector, str) else "",
                    state=STATE_INVALID,
                    sha="",
                    code=REASON_MALFORMED_SELECTOR,
                    detail="declared test selector is malformed",
                ))
                continue
            if sha is None:
                entries.append(TestEvidenceVerification(
                    decision_id=decision.id,
                    selector=selector,
                    state=STATE_INVALID,
                    sha="",
                    code=REASON_SHA_UNAVAILABLE,
                    detail="repository SHA could not be determined",
                ))
                continue
            if selector in ambiguous:
                entries.append(TestEvidenceVerification(
                    decision_id=decision.id,
                    selector=selector,
                    state=STATE_INVALID,
                    sha=sha,
                    code=REASON_AMBIGUOUS_MAPPING,
                    detail=(
                        "selector is declared by more than one decision; "
                        "ambiguous mapping protects neither"
                    ),
                ))
                continue
            declared_sha = _declared_sha(entry)
            if declared_sha is not None and declared_sha != sha:
                entries.append(TestEvidenceVerification(
                    decision_id=decision.id,
                    selector=selector,
                    state=STATE_STALE,
                    sha=sha,
                    code=REASON_SHA_MISMATCH,
                    detail=(
                        f"declared SHA {declared_sha} does not match "
                        f"repository HEAD {sha}"
                    ),
                ))
                continue
            selector_path = root.joinpath(*file_part.split("/"))
            if not selector_path.is_file():
                entries.append(TestEvidenceVerification(
                    decision_id=decision.id,
                    selector=selector,
                    state=STATE_INVALID,
                    sha=sha,
                    code=REASON_SELECTOR_NOT_FOUND,
                    detail="declared test file does not exist in the repository",
                ))
                continue
            entries.append(TestEvidenceVerification(
                decision_id=decision.id,
                selector=selector,
                state=STATE_DECLARED,
                sha=sha,
                code=REASON_NO_VERIFICATION,
                detail=(
                    "declared linkage passes passive validation; no trusted "
                    "verification producer is available yet, so this never "
                    "establishes protection on its own"
                ),
            ))
        results[decision.id] = entries
    return results


def evidence_source_strings(
    verifications: list[TestEvidenceVerification],
) -> list[str]:
    """Deterministic evidence-source strings for the audit report.

    Declared entries read ``test:declared:<selector>`` (with the pinned
    SHA when present); stale entries read ``test:stale:<selector>@<code>``;
    invalid entries read ``test:invalid:<selector>@<code>``. The audit
    always answers why a declared linkage did not establish protection —
    with no runner noise and no execution.
    """
    sources: list[str] = []
    for verification in verifications:
        selector = verification.selector
        if verification.state == STATE_DECLARED:
            sources.append(f"test:declared:{selector}")
        elif verification.state == STATE_STALE:
            sources.append(f"test:stale:{selector}@{verification.code}")
        elif verification.state == STATE_VERIFIED:
            sources.append(f"test:verified:{selector}@{verification.sha}")
        else:
            sources.append(
                f"test:invalid:{selector}@{verification.code}"
            )
    return sources


__all__ = [
    "TestEvidenceVerification",
    "verify_test_evidence",
    "evidence_source_strings",
    "STATE_DECLARED",
    "STATE_VERIFIED",
    "STATE_STALE",
    "STATE_INVALID",
    "REASON_MALFORMED_SELECTOR",
    "REASON_AMBIGUOUS_MAPPING",
    "REASON_SHA_UNAVAILABLE",
    "REASON_SHA_MISMATCH",
    "REASON_SELECTOR_NOT_FOUND",
    "REASON_NO_VERIFICATION",
]

"""Frozen R1/R2/R3 corpus distribution admission, independent of hook output.

The frozen protocol requires more than class totals. This module checks
class-specific minima using the sealed fixture definitions, the scorer's
contract-derived expectations and the author's frozen numeric *labels*.
It must never infer a requirement from observed implementation output.
Counts and shortfall names are the only exported evidence.
"""

from __future__ import annotations

import json
import posixpath
import re
from collections import Counter
from pathlib import PurePosixPath

from . import contract as C
from . import oracle


_L_MINIMA = (
    "existing_file", "existing_empty", "symlink", "dangling_symlink",
    "link_component", "outside_root", "non_python",
    "missing_parent", "lone_surrogate",
)
_BYTE_MINIMA = ("lf", "crlf", "cr", "non_ascii", "empty")


def _byte_features(content: str) -> set[str]:
    result = set()
    if re.search(r"(?<!\r)\n", content):
        result.add("lf")
    if "\r\n" in content:
        result.add("crlf")
    if re.search(r"\r(?!\n)", content):
        result.add("cr")
    # "Non-ASCII byte variety" requires a real UTF-8 byte sequence.
    # Lone surrogates are unencodable and count only toward L's explicit
    # surrogate legacy subtype, never as non-ASCII source bytes.
    if any(ord(c) > 127 and not 0xD800 <= ord(c) <= 0xDFFF for c in content):
        result.add("non_ascii")
    if not content:
        result.add("empty")
    return result


def _l_features(case: dict, exp, obs: dict) -> set[str]:
    """R1 §4 L classification from frozen fixture declarations + pre-snapshot.

    Never inspect paths after the two score passes: the fixture worktree may
    have been recreated or removed. A link only qualifies as live when its
    target is present in the fixture's declared file/directory inventory.
    """
    found: set[str] = set()
    target = case["event"]["target"]
    base, rel = target["base"], target["path"]
    pre = obs.get("pre") or {}
    specs = case["fixture"]["files"]
    by_path = {(sp["base"], sp["path"]): sp for sp in specs}
    dest_spec = by_path.get((base, rel))

    # The runner materializer implicitly mkdirs the parent of every declared
    # entry, in addition to explicitly declared directory entries.
    directories = {(b, "") for b in ("root", "outside")}
    for spec in specs:
        path = PurePosixPath(spec["path"])
        for parent in path.parents:
            if str(parent) != ".":
                directories.add((spec["base"], parent.as_posix()))
        if spec["type"] in ("dir", "dir_symlink"):
            directories.add((spec["base"], spec["path"]))

    if pre.get("kind") == "file" and dest_spec and dest_spec["type"] == "file":
        found.add("existing_empty" if dest_spec["text"] == "" else "existing_file")

    if pre.get("kind") == "symlink" and dest_spec and dest_spec["type"] == "symlink":
        link_target = dest_spec.get("target", "")
        if link_target and not link_target.startswith("/"):
            resolved = posixpath.normpath(posixpath.join(
                posixpath.dirname(rel), link_target))
            live = (base, resolved) in by_path or (base, resolved) in directories
            found.add("symlink" if live else "dangling_symlink")

    # A directory symlink in any parent component is an L link-component
    # case even when the final target itself is absent.
    parts = PurePosixPath(rel).parts
    if any((base, "/".join(parts[:i])) in by_path
           and by_path[(base, "/".join(parts[:i]))]["type"] == "dir_symlink"
           for i in range(1, len(parts))):
        found.add("link_component")

    if base == "outside":
        found.add("outside_root")
    if PurePosixPath(rel).suffix != ".py":
        found.add("non_python")
    parent = PurePosixPath(rel).parent.as_posix()
    if (base, "" if parent == "." else parent) not in directories:
        found.add("missing_parent")
    try:
        case["event"]["content"].encode("utf-8")
    except UnicodeEncodeError:
        found.add("lone_surrogate")
    return found

def inspect(cases: list, passes: dict, public_evidence: dict | None = None) -> dict:
    """Check extra frozen distribution rules; missing evidence is a failure.

    This is not a separate scoring oracle. Numeric matcher outcomes are taken
    only from frozen author labels, which the independent scorer cross-checks.
    Neither direct checker output nor observed hook results are used to award
    a coverage category.
    """
    counts = Counter()
    shortfalls: list[str] = []
    at_signatures: dict[str, list] = {"AT-SI": [], "AT-SX": []}
    at_fixture_signatures: dict[str, set] = {sub: set() for sub in C.AT_SUBCLASS_FLOORS}
    concealed = [c for c in cases if c.get("visibility") != "public"]
    if any(c.get("cls") not in C.CLASS_FLOORS for c in cases):
        shortfalls.append("unknown_class")
    if any(c.get("visibility") not in ("public", "concealed") for c in cases):
        shortfalls.append("invalid_visibility")
    if any(c.get("cls") == "AT" and c.get("subclass") not in C.AT_SUBCLASS_FLOORS
           for c in cases):
        shortfalls.append("unknown_AT_subclass")

    for case in concealed:
        cid, cls = case["case_id"], case["cls"]
        runs = passes.get(cid) or []
        if not runs or runs[0][0] is None:
            shortfalls.append("case_unlabelled_or_unscored")
            continue
        exp, obs = runs[0]
        numeric = list(exp.numeric_outcomes.values())
        violating = [o for o in numeric if o.get("matcher_outcome") == "VIOLATION"]
        clean = [o for o in numeric if o.get("matcher_status") == "RECOGNIZED"
                 and o.get("matcher_outcome") == "NO_VIOLATION"]

        if cls in ("V", "C", "L"):
            for feature in _byte_features(case["event"]["content"]):
                counts["bytes:" + feature] += 1

        if cls == "L":
            for feature in _l_features(case, exp, obs):
                counts["L:" + feature] += 1

        if cls == "LIT" and exp.routed and exp.literal_violations and exp.trusted_proposed:
            if violating:
                counts["LIT:mixed_violation"] += 1
            if clean and not violating and exp.disposition == "refused" and exp.cause == "other_rule":
                counts["LIT:mixed_clean_refusal"] += 1

        if cls == "SC":
            try:
                rules = oracle.fixture_rules(case)
                has_call = any(r.rule_type == C.NUMERIC and
                               "call" in json.loads(r.value)
                               and r.rule_id in exp.applied_rule_ids for r in rules)
            except (oracle.OracleError, ValueError, TypeError):
                has_call = False
            if not (exp.routed and exp.trusted_proposed and has_call):
                shortfalls.append("SC:invalid_call_source")
            else:
                if any(o.get("matcher_status") == "RECOGNIZED" and
                       o.get("matcher_outcome") == "VIOLATION" for o in numeric):
                    counts["SC:recognized_violation"] += 1
                if numeric and all(o.get("matcher_status") == "RECOGNIZED" and
                                   o.get("matcher_outcome") == "NO_VIOLATION" for o in numeric):
                    counts["SC:recognized_clean"] += 1
                if any(o.get("primary_reason") == "AMBIGUOUS_BINDING" or
                       "AMBIGUOUS_BINDING" in (o.get("unknown_reasons") or [])
                       for o in numeric):
                    counts["SC:ambiguous_binding"] += 1

        if cls == "MR":
            if not exp.routed or len(exp.applied_rule_ids) < 2:
                shortfalls.append("MR:less_than_two_applied")
            else:
                unevaluated = any(o.get("matcher_status") == "MATCHER_UNEVALUATED" for o in numeric)
                # ADR-034 §7b rows 1–2 are strict refusals attributable
                # to the violated numeric rule, not merely the same matcher
                # output under warn/proceed (owner ruling, 2026-10-28).
                numeric_refusal = (
                    exp.mode == "strict" and exp.disposition == "refused"
                    and exp.cause == "numeric_violation"
                    and exp.event_relevance is True
                    and any(exp.per_rule_relevance.get(rid) is True
                            for rid, value in exp.numeric_outcomes.items()
                            if value.get("matcher_outcome") == "VIOLATION")
                )
                if violating and unevaluated and numeric_refusal:
                    counts["MR:row1_violation_unevaluated"] += 1
                if (violating and clean and numeric_refusal
                        and exp.evaluation_complete is True):
                    counts["MR:row2_violation_clean"] += 1
                if (numeric and len(clean) == len(numeric)
                        and exp.disposition == "proceeded"
                        and exp.event_relevance is True
                        and all(exp.per_rule_relevance.get(rid) is True
                                for rid in exp.applied_rule_ids)):
                    counts["MR:row3_all_clean"] += 1
                if (exp.literal_violations and exp.mode == "strict" and exp.disposition == "refused"
                    and exp.cause == "other_rule" and not violating
                    and all(v is False for v in exp.per_rule_relevance.values())):
                    counts["MR:literal_only_refusal_analogue"] += 1

        if cls == "AT":
            try:
                rules = [r for r in oracle.fixture_rules(case) if r.rule_type == C.NUMERIC]
            except (oracle.OracleError, TypeError, ValueError):
                rules = []
                shortfalls.append("AT:invalid_fixture")
            sub = case.get("subclass")
            if sub not in at_fixture_signatures:
                shortfalls.append("AT:unknown_subclass")
                continue
            basic = (exp.routed and exp.literal_violations and not exp.applied_rule_ids
                     and exp.record_subject is None and exp.event_relevance is False
                     and exp.per_rule_relevance == {})
            mode_ok = exp.mode == ("warn" if sub == "AT-W0" else "strict")
            if not basic or not mode_ok or exp.cause != "other_rule":
                shortfalls.append("AT:invalid_subject_or_attribution")
                continue
            # Ignore mere file/target renaming. Distinct ADR source text or a
            # distinct literal-rule identity is required by R3 §3.
            adr_sources = tuple(sorted(
                s["text"] for s in case["fixture"]["files"]
                if s.get("type") == "file" and s.get("path", "").startswith("docs/adr/")
            ))
            at_fixture_signatures[sub].add(
                (adr_sources, tuple(sorted(tuple(v) for v in exp.literal_violations)))
            )
            if sub == "AT-S0":
                if rules:
                    shortfalls.append("AT-S0:has_numeric_rule")
            elif sub in ("AT-SI", "AT-SX"):
                mechanism = "include_miss" if sub == "AT-SI" else "exclude_match"
                eligible = [r for r in rules if oracle.applicability(r, exp.governed_path) ==
                            ("EXCLUDED", mechanism) and
                            (sub != "AT-SI" or (r.include and not r.exclude))]
                if not eligible or exp.checker_subject_kind != "unverified_input":
                    shortfalls.append(sub + ":wrong_exclusion_mechanism")
                else:
                    at_signatures[sub].append((
                        tuple(sorted(tuple(v) for v in exp.literal_violations)),
                        tuple(sorted((tuple(r.include or ()), tuple(r.exclude)) for r in eligible)),
                    ))
            elif sub == "AT-W0":
                if not rules and exp.checker_subject_kind == "absent":
                    counts["AT-W0:literal_only"] += 1
                elif (rules and exp.checker_subject_kind == "unverified_input" and
                      any(oracle.applicability(r, exp.governed_path)[0] == "EXCLUDED" for r in rules)):
                    counts["AT-W0:excluded_numeric"] += 1
                else:
                    shortfalls.append("AT-W0:invalid_variant")

    # R3 #703 freezes public smoke as a *separate* independently
    # manifest-checked tar. Never require it inside the concealed archive.
    # A metadata claim alone cannot satisfy this requirement: the separate
    # public archive must pass its frozen digest and inventory verification.
    if public_evidence is not None:
        if (public_evidence.get("verified") is not True or
                public_evidence.get("public_cases") != len(C.CLASS_FLOORS) or
                set(public_evidence.get("classes") or ()) != set(C.CLASS_FLOORS)):
            shortfalls.append("public_smoke_separate_archive_not_verified")
    elif not any(c.get("visibility") == "public" and c.get("cls") == "AT" for c in cases):
        shortfalls.append("public_AT_smoke_missing")
    expected = {
        **{"L:" + k: 2 for k in _L_MINIMA},
        **{"bytes:" + k: 2 for k in _BYTE_MINIMA},
        "LIT:mixed_violation": 2, "LIT:mixed_clean_refusal": 2,
        "SC:recognized_violation": 2, "SC:recognized_clean": 2,
        "SC:ambiguous_binding": 2,
        "MR:row1_violation_unevaluated": 1,
        "MR:row2_violation_clean": 1, "MR:row3_all_clean": 1,
        "MR:literal_only_refusal_analogue": 2,
        "AT-W0:literal_only": 1, "AT-W0:excluded_numeric": 1,
    }
    for key, minimum in expected.items():
        if counts[key] < minimum:
            shortfalls.append(key + ":below_minimum")
    for sub, signatures in at_signatures.items():
        # AT-SI amendment §2 specifically demands *both* different literal
        # identities and path scopes; AT-SX has no such stronger condition.
        if sub == "AT-SI" and (len({sig[0] for sig in signatures}) < 2 or
                              len({sig[1] for sig in signatures}) < 2):
            shortfalls.append("AT-SI:not_two_distinct_literal_identities_and_scopes")
    for sub, fingerprints in at_fixture_signatures.items():
        if len(fingerprints) < C.AT_SUBCLASS_FLOORS[sub]:
            shortfalls.append(sub + ":not_two_distinct_ADR_fixtures_or_literal_identities")
    return {"met": not shortfalls, "shortfalls": sorted(set(shortfalls)),
            "counts": dict(sorted(counts.items()))}

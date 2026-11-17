"""Independent R3 oracle (R3 §3 "Normative independent attribution oracle").

Everything here is derived from the normative contracts and the case's
fixture definition, plus read-only stdlib probes of the materialized
fixture. Nothing here imports Mneme or reads an observed result.

Derived independently:

- ADR constraint parsing, canonical rule values and ``rule_id``
  (ADR-019 §1, ADR-020 §9, ADR-034 §2/§5, ADR-030 §7 identity);
- ADR-020 selector grammar, policy root and per-rule applicability;
- ``FORBID_LITERAL`` exact matching with identifier boundaries (ADR-019 §2-§3);
- hook routing (R1 A1.1), checker preconditions (ADR-034 §6a), the trusted
  proposed-source fact, checker subject kind (R3 §3 table, AT-SI amendment);
- the expected G2 record: subject, applied rule-ID set, violation
  identities (ADR-034 §7c), disposition and cause, per-rule and event
  relevance (ADR-034 §7b, R1 A1.3), record-wide completeness (ADR-034 §4,
  R2 A2R2).

Taken from the author's frozen labels (the matcher itself is not
re-implemented): each numeric rule's matcher status, outcome, primary
reason and unknown reasons, and the exit/disposition of unrouted legacy
cases (scored by G5 parity). Every derived value is cross-checked against
the frozen labels; any disagreement is an oracle conflict (README I2).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Optional

import yaml

from . import contract as C


class OracleError(Exception):
    """The fixture cannot be labelled from the normative contract alone."""


# ── Identity (ADR-030 §7 / ADR-034 §5) ─────────────────────────────────────


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def applicability_object(include: Optional[tuple], exclude: tuple) -> dict:
    """ADR-020 applicability as it enters identity: ``{}`` means global."""
    obj: dict = {}
    if include is not None:
        obj["include_paths"] = list(include)
    if exclude:
        obj["exclude_paths"] = list(exclude)
    return obj


def rule_id_of(decision_id: str, rule_type: str, value: str, applicability: dict) -> str:
    digest = hashlib.sha256(canonical_json([value, applicability]).encode("utf-8")).hexdigest()
    return f"{decision_id}:{rule_type}:{digest[:32]}"


@dataclass(frozen=True)
class Rule:
    decision_id: str
    adr_path: str
    rule_type: str
    value: str
    include: Optional[tuple]
    exclude: tuple

    @property
    def rule_id(self) -> str:
        return rule_id_of(
            self.decision_id, self.rule_type, self.value,
            applicability_object(self.include, self.exclude),
        )


# ── ADR-020 selectors and applicability ────────────────────────────────────


def validate_selector(pattern: Any) -> str:
    if not isinstance(pattern, str) or not pattern:
        raise OracleError("selector must be a non-empty string")
    if pattern.startswith("/") or re.match(r"^[A-Za-z]:", pattern) or "\\" in pattern:
        raise OracleError(f"invalid selector {pattern!r}")
    if pattern.startswith("!"):
        raise OracleError(f"negated selector {pattern!r}")
    for seg in pattern.split("/"):
        if seg in ("", ".", ".."):
            raise OracleError(f"invalid selector segment in {pattern!r}")
        if "**" in seg and seg != "**":
            raise OracleError(f"embedded ** in {pattern!r}")
        if "[" in seg or "]" in seg:
            raise OracleError(f"bracket expression in {pattern!r}")
    return pattern


def _segment_matches(pattern: str, segment: str) -> bool:
    regex = "".join("[^/]*" if ch == "*" else re.escape(ch) for ch in pattern)
    return re.fullmatch(regex, segment) is not None


def selector_matches(pattern: str, path: str) -> bool:
    """ADR-020 §4: case-sensitive, ``*`` within a segment, ``**`` = 0+ segments."""
    pats, segs = pattern.split("/"), path.split("/")

    def match(i: int, j: int) -> bool:
        if i == len(pats):
            return j == len(segs)
        if pats[i] == "**":
            return any(match(i + 1, k) for k in range(j, len(segs) + 1))
        return j < len(segs) and _segment_matches(pats[i], segs[j]) and match(i + 1, j + 1)

    return match(0, 0)


APPLIED, EXCLUDED, UNKNOWN = "APPLIED", "EXCLUDED", "UNKNOWN"


def applicability(rule: Rule, governed_path: Optional[str]) -> tuple[str, Optional[str]]:
    """``(outcome, mechanism)``; mechanism is ``include_miss`` / ``exclude_match``."""
    if rule.include is None and not rule.exclude:
        return APPLIED, None  # ADR-020 §3: no selectors -> global
    if governed_path is None:
        return UNKNOWN, None  # ADR-020 §6
    included = any(selector_matches(p, governed_path) for p in rule.include or ())
    excluded = any(selector_matches(p, governed_path) for p in rule.exclude)
    if included and not excluded:
        return APPLIED, None
    if not included and not excluded:
        return EXCLUDED, "include_miss"
    if included and excluded:
        return EXCLUDED, "exclude_match"
    return EXCLUDED, "include_miss_and_exclude_match"


# ── ADR parsing (ADR-019 §1, ADR-020 §9, ADR-034 §2/§5) ─────────────────────

_FRONT_MATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)
_MAX_GRAMMAR = re.compile(r"^(0|[1-9][0-9]{0,17})(\.[0-9]{1,9})?$")
_NUMERIC_KEYS = frozenset({
    "language", "symbol", "call", "max", "inclusive", "unit", "include_paths", "exclude_paths",
})
_LITERAL_KEYS = frozenset({"value", "include_paths", "exclude_paths"})


def _construct(node: yaml.Node) -> Any:
    return yaml.SafeLoader("").construct_object(node, deep=True)


def _mapping(node: yaml.Node, where: str) -> dict:
    if not isinstance(node, yaml.MappingNode):
        raise OracleError(f"{where}: expected a mapping")
    out: dict = {}
    for key_node, value_node in node.value:
        key = _construct(key_node)
        if not isinstance(key, str):
            raise OracleError(f"{where}: non-string key")
        if key in out:
            raise OracleError(f"{where}: duplicate key {key!r}")
        out[key] = value_node
    return out


def _selectors(node: Optional[yaml.Node], where: str, required: bool) -> Optional[tuple]:
    if node is None:
        if required:
            raise OracleError(f"{where}: include_paths is required")
        return None
    value = _construct(node)
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise OracleError(f"{where}: selectors must be a list of strings")
    return tuple(validate_selector(v) for v in value)


def canonical_max(node: yaml.Node) -> str:
    """ADR-034 §5: raw plain-scalar grammar, textual normalization, > 0."""
    if not isinstance(node, yaml.ScalarNode) or node.style not in (None, ""):
        raise OracleError("max must be a plain scalar")
    raw = node.value
    if not _MAX_GRAMMAR.match(raw):
        raise OracleError(f"max {raw!r} violates the authoring grammar")
    text = raw
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if Fraction(text) <= 0:
        raise OracleError("max must be > 0")
    return text


def _numeric_rule(decision_id: str, adr_path: str, node: yaml.Node) -> Rule:
    where = f"{decision_id} FORBID_NUMERIC_ABOVE"
    fields = _mapping(node, where)
    unknown = set(fields) - _NUMERIC_KEYS
    if unknown:
        raise OracleError(f"{where}: unknown keys {sorted(unknown)}")
    for key in ("language", "max", "inclusive", "unit", "include_paths"):
        if key not in fields:
            raise OracleError(f"{where}: missing {key}")
    if _construct(fields["language"]) != "python":
        raise OracleError(f"{where}: language must be python")
    if _construct(fields["inclusive"]) is not True:
        raise OracleError(f"{where}: inclusive must be true")
    unit = _construct(fields["unit"])
    if not isinstance(unit, str) or not unit.strip():
        raise OracleError(f"{where}: unit must be non-empty")
    obj: dict = {
        "v": 1, "language": "python", "max": canonical_max(fields["max"]),
        "inclusive": True, "unit": unit,
    }
    if "symbol" in fields:
        symbol = _construct(fields["symbol"])
        if not isinstance(symbol, str) or not symbol.isidentifier():
            raise OracleError(f"{where}: bad symbol")
        obj["symbol"] = symbol
    if "call" in fields:
        call = _mapping(fields["call"], f"{where} call")
        if set(call) != {"function", "position"}:
            raise OracleError(f"{where}: call needs exactly function and position")
        function, position = _construct(call["function"]), _construct(call["position"])
        if not isinstance(function, str) or not function.isidentifier():
            raise OracleError(f"{where}: bad call.function")
        if type(position) is not int or position < 0:
            raise OracleError(f"{where}: bad call.position")
        obj["call"] = {"function": function, "position": position}
    if "symbol" not in obj and "call" not in obj:
        raise OracleError(f"{where}: needs symbol or call")
    include = _selectors(fields.get("include_paths"), where, required=True)
    if not include:
        raise OracleError(f"{where}: include_paths must be non-empty")
    exclude = _selectors(fields.get("exclude_paths"), where, required=False) or ()
    return Rule(decision_id, adr_path, C.NUMERIC, canonical_json(obj), include, exclude)


def _literal_rule(decision_id: str, adr_path: str, node: yaml.Node) -> Rule:
    where = f"{decision_id} FORBID_LITERAL"
    if isinstance(node, yaml.ScalarNode):
        value = _construct(node)
        include, exclude = None, ()
    else:
        fields = _mapping(node, where)
        unknown = set(fields) - _LITERAL_KEYS
        if unknown or "value" not in fields:
            raise OracleError(f"{where}: bad structured form")
        value = _construct(fields["value"])
        include = _selectors(fields.get("include_paths"), where, required=False)
        exclude = _selectors(fields.get("exclude_paths"), where, required=False) or ()
        if include is not None and not include:
            raise OracleError(f"{where}: empty include_paths")
        if exclude and include is None:
            raise OracleError(f"{where}: exclude_paths without include_paths")
    if not isinstance(value, str) or not value.strip():
        raise OracleError(f"{where}: value must be a non-blank string")
    return Rule(decision_id, adr_path, C.LITERAL, value, include, exclude)


@dataclass
class Adr:
    decision_id: str
    path: str
    status: str
    scope: Any
    rules: list = field(default_factory=list)


def parse_adr(path: str, text: str) -> Adr:
    match = _FRONT_MATTER.match(text)
    if not match:
        raise OracleError(f"{path}: no front matter")
    front = yaml.safe_load(match.group(1))
    if not isinstance(front, dict) or not isinstance(front.get("id"), str):
        raise OracleError(f"{path}: front matter lacks id")
    adr = Adr(front["id"], path, str(front.get("status")), front.get("scope"))
    lines = text[match.end():].splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == "## Constraints"]
    if len(starts) > 1:
        raise OracleError(f"{path}: several Constraints sections")
    if not starts:
        return adr
    body = []
    for line in lines[starts[0] + 1:]:
        if line.startswith("## ") or line.startswith("# "):
            break
        body.append(line)
    section = "\n".join(body)
    if not section.strip():
        return adr
    root = yaml.compose(section, Loader=yaml.SafeLoader)
    if not isinstance(root, yaml.SequenceNode):
        raise OracleError(f"{path}: Constraints is not a bullet list")
    for item in root.value:
        if not isinstance(item, yaml.MappingNode) or len(item.value) != 1:
            # Legacy constraint prose (ADR-017) is not derivable here (README I10).
            raise OracleError(f"{path}: non-typed constraint bullet")
        key_node, value_node = item.value[0]
        key = _construct(key_node)
        if key == C.LITERAL:
            adr.rules.append(_literal_rule(adr.decision_id, path, value_node))
        elif key == C.NUMERIC:
            adr.rules.append(_numeric_rule(adr.decision_id, path, value_node))
        else:
            raise OracleError(f"{path}: unknown rule type {key!r}")
    return adr


def fixture_rules(case: dict) -> list[Rule]:
    """Typed rules of every fixture ADR the memory is compiled from."""
    memory = case["fixture"].get("memory")
    if not memory:
        return []
    source = memory.get("compile_from")
    if source != "docs/adr":
        raise OracleError(f"unsupported memory source {source!r}")
    adrs = []
    for spec in case["fixture"]["files"]:
        if spec.get("base") != "root" or not spec["path"].startswith("docs/adr/"):
            continue
        rest = spec["path"][len("docs/adr/"):]
        if spec["type"] != "file" or "/" in rest or not rest.endswith(".md"):
            raise OracleError(f"unsupported ADR fixture entry {spec['path']!r}")
        adrs.append(parse_adr(spec["path"], spec["text"]))
    ids = [a.decision_id for a in adrs]
    if len(set(ids)) != len(ids):
        raise OracleError("duplicate decision ids")
    scopes = [canonical_json(a.scope) for a in adrs]
    if len(set(scopes)) != len(scopes):
        raise OracleError("duplicate ADR scopes (precedence not derived here)")
    for adr in adrs:
        if adr.status != "accepted":
            raise OracleError(f"{adr.decision_id}: status {adr.status!r} not derived here")
    return [rule for adr in adrs for rule in adr.rules]


# ── FORBID_LITERAL (ADR-019 §2-§3) ──────────────────────────────────────────


def _identifier_char(ch: str) -> bool:
    return ch.isascii() and (ch.isalnum() or ch in "_-")


def literal_occurs(literal: str, text: str) -> bool:
    start = 0
    while True:
        index = text.find(literal, start)
        if index < 0:
            return False
        end = index + len(literal)
        left_ok = not (_identifier_char(literal[0]) and index > 0 and _identifier_char(text[index - 1]))
        right_ok = not (
            _identifier_char(literal[-1]) and end < len(text) and _identifier_char(text[end])
        )
        if left_ok and right_ok:
            return True
        start = index + 1


def universal_newlines(text: str) -> str:
    """The legacy ``read_text`` decoding of the carrier (charter §3.3)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


# ── Filesystem facts of the materialized fixture ───────────────────────────


def find_memory(start: Path) -> Optional[Path]:
    """Memory discovery from the target's resolved parent (charter §2, AMB-R2-03)."""
    current = Path(start).resolve()
    while True:
        candidate = current / ".mneme" / "project_memory.json"
        if candidate.is_file():
            return candidate
        if current.parent == current:
            return None
        current = current.parent


def _lstat_absent(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return True
    except (OSError, ValueError):
        return False
    return False


def _parent_is_dir(path: Path) -> bool:
    """R1 A1.1 / G2C-O4: the parent exists and is a directory (links followed)."""
    try:
        return stat.S_ISDIR(os.stat(path.parent).st_mode)
    except (OSError, ValueError):
        return False


def _utf8(content: str) -> bool:
    try:
        content.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


# ── The derived expectation ─────────────────────────────────────────────────


@dataclass
class Expectation:
    root: str = ""
    target: str = ""
    content_sha256: Optional[str] = None
    memory_expected: bool = False
    checked: Optional[bool] = None
    routed: bool = False
    record_expected: bool = False
    governed_path: Optional[str] = None
    preconditions_ok: Optional[bool] = None
    trusted_proposed: bool = False
    fallback_numeric: bool = False
    checker_subject_kind: Optional[str] = None
    record_subject: Optional[str] = None
    rule_ids: list = field(default_factory=list)
    numeric_applicability: dict = field(default_factory=dict)
    applied_rule_ids: list = field(default_factory=list)
    literal_violations: list = field(default_factory=list)
    violations: list = field(default_factory=list)
    numeric_outcomes: dict = field(default_factory=dict)
    evaluation_complete: Optional[bool] = None
    disposition: Optional[str] = None
    exit: Optional[int] = None
    cause: Optional[str] = None
    per_rule_relevance: dict = field(default_factory=dict)
    event_relevance: Optional[bool] = None
    mode: str = "strict"
    participation: dict = field(default_factory=dict)
    g5: dict = field(default_factory=dict)
    conflicts: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def to_json(self) -> dict:
        return dict(self.__dict__)


def _sha256_text(content: str) -> Optional[str]:
    try:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
    except UnicodeEncodeError:
        return None


def _per_rule(exp: Expectation) -> dict:
    """ADR-034 §7b.1 / R1 A1.3 per-rule relevance, for a valid pinned host."""
    out = {}
    for rid in exp.applied_rule_ids:
        o = exp.numeric_outcomes.get(rid, {})
        status, outcome = o.get("matcher_status"), o.get("matcher_outcome")
        decided = status == "RECOGNIZED" or (status == "PARTIAL" and outcome == "VIOLATION")
        if outcome == "VIOLATION":
            attributable = exp.cause == "numeric_violation" and (
                (exp.disposition == "refused" and exp.mode == "strict")
                or (exp.disposition == "deferred" and exp.mode == "warn")
            )
        else:
            attributable = (
                exp.disposition == "proceeded" and exp.cause == "no_violation" and not exp.violations
            )
        out[rid] = bool(decided and attributable)
    return out


def derive(case: dict, root: Path, outside: Path) -> Expectation:
    """Expected behavior, from the contract and the fixture definition only."""
    event, labels, hook = case["event"], case["labels"], case["hook"]
    exp = Expectation(mode=hook["mode"])
    base = {"root": root, "outside": outside}[event["target"]["base"]]
    target = base.joinpath(*event["target"]["path"].split("/"))
    content = event["content"]
    exp.root = str(root)
    exp.target = str(target)
    exp.content_sha256 = _sha256_text(content)
    rules = fixture_rules(case)
    exp.memory_expected = bool(case["fixture"].get("memory"))
    exp.rule_ids = sorted(r.rule_id for r in rules)
    numeric_rules = [r for r in rules if r.rule_type == C.NUMERIC]
    literal_rules = [r for r in rules if r.rule_type == C.LITERAL]

    memory = find_memory(Path(target).resolve().parent)
    if memory is not None and memory.parent.parent.resolve() != root.resolve():
        raise OracleError("memory discovered outside the fixture root")
    blank = not content.strip()
    if memory is None or blank or event.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        exp.checked = False
        exp.disposition, exp.exit = "not_checked", 0
    is_write = event.get("tool_name") == "Write"
    exp.routed = bool(
        exp.checked is not False and is_write and target.is_absolute()
        and target.suffix == ".py" and _lstat_absent(target) and _parent_is_dir(target)
        and _utf8(content)
    )
    exp.record_expected = exp.routed

    if exp.routed:
        exp.checked = True
        lexical_parent = target.parent
        try:
            resolved_parent = lexical_parent.resolve(strict=True)
            link_free = os.path.normcase(str(lexical_parent)) == os.path.normcase(str(resolved_parent))
            resolved_target = resolved_parent / target.name
        except (OSError, RuntimeError):
            link_free, resolved_target = False, target.resolve()
        try:
            exp.governed_path = resolved_target.relative_to(root.resolve()).as_posix()
        except ValueError:
            exp.governed_path = None
        exp.preconditions_ok = bool(link_free and exp.governed_path is not None and target.suffix == ".py")

        outcomes = {r.rule_id: applicability(r, exp.governed_path) for r in rules}
        exp.numeric_applicability = {r.rule_id: list(outcomes[r.rule_id]) for r in numeric_rules}
        applied = sorted(r.rule_id for r in numeric_rules if outcomes[r.rule_id][0] == APPLIED)
        any_unknown = any(o[0] == UNKNOWN for o in outcomes.values())
        exp.trusted_proposed = bool(exp.preconditions_ok and applied)
        exp.fallback_numeric = bool(not exp.preconditions_ok and applied)
        exp.applied_rule_ids = applied if exp.trusted_proposed else []
        exp.checker_subject_kind = (
            "proposed_new_source" if exp.trusted_proposed
            else "unverified_input" if numeric_rules else "absent"
        )
        exp.record_subject = "proposed_new_source" if exp.trusted_proposed else None

        text = content if exp.trusted_proposed else universal_newlines(content)
        exempt = {".mneme/project_memory.json"}
        literal = sorted(
            [r.rule_id, C.LITERAL] for r in literal_rules
            if outcomes[r.rule_id][0] == APPLIED
            and exp.governed_path not in exempt | {r.adr_path}
            and literal_occurs(r.value, text)
        )
        exp.literal_violations = literal

        labelled = {e.get("rule_id"): e for e in labels["checker"].get("numeric_rules") or []}
        for rid in exp.applied_rule_ids:
            entry = labelled.get(rid)
            if entry is None or entry.get("rule_id_gated") is not True:
                exp.conflicts.append(f"label_lacks_gated_numeric_outcome:{rid}")
                continue
            exp.numeric_outcomes[rid] = {
                k: entry.get(k) for k in
                ("matcher_status", "matcher_outcome", "primary_reason", "unknown_reasons")
            }
        numeric_violations = sorted(
            [rid, C.NUMERIC] for rid, o in exp.numeric_outcomes.items()
            if o.get("matcher_outcome") == "VIOLATION"
        )
        exp.violations = sorted(literal + numeric_violations)

        if exp.trusted_proposed:
            exp.evaluation_complete = not any_unknown and all(
                o.get("matcher_status") == "RECOGNIZED" for o in exp.numeric_outcomes.values()
            )
        else:
            exp.evaluation_complete = not (exp.fallback_numeric or any_unknown)

        if exp.violations:
            exp.disposition = "refused" if exp.mode == "strict" else "deferred"
            exp.exit = 2 if exp.mode == "strict" else 0
            exp.cause = "numeric_violation" if numeric_violations else "other_rule"
        else:
            exp.disposition, exp.exit = "proceeded", 0
            exp.cause = "no_violation" if exp.evaluation_complete else "fail_open"
        exp.per_rule_relevance = _per_rule(exp)
        exp.event_relevance = any(exp.per_rule_relevance.values())
    elif exp.checked is None:
        exp.checked = True  # unrouted legacy check; scored by G5 parity

    _participation(case, exp, content)
    _cross_check(case, exp, numeric_rules)
    return exp


def _participation(case: dict, exp: Expectation, content: str) -> None:
    """Derived gate participation, unioned with the label's (README I1)."""
    labels, cls = case["labels"], case["cls"]
    gated = [e for e in labels["checker"].get("numeric_rules") or [] if e.get("rule_id_gated")]
    expected_refused = labels.get("expected_disposition") == "refused" or exp.disposition == "refused"
    nonclean = any(e.get("matcher_outcome") != "NO_VIOLATION" for e in gated)
    proceed = (
        labels.get("exit_source") == "contract" and labels.get("expected_hook_exit") == 0
        and labels.get("expected_disposition") in ("proceeded", "deferred", "not_checked")
    )
    hook_level = cls in C.HOOK_PARITY_CLASSES
    cr_exception = hook_level and exp.routed and "\r" in content
    checker_level = (exp.routed and cls in C.CHECKER_PARITY_CLASSES) or cr_exception
    derived = {
        "G1": exp.record_expected or expected_refused or nonclean,
        "G2": proceed,
        "G3": True,
        "G4": any(e.get("primary_reason") is not None for e in gated),
        "G5": hook_level or checker_level,
        "G6": True, "G7": True, "G8": True,
    }
    label_gates = set(labels.get("gates") or [])
    for gate in C.GATES:
        exp.participation[gate] = bool(derived[gate] or gate in label_gates)
        if derived[gate] != (gate in label_gates):
            exp.notes.append(f"gate_participation_differs_from_label:{gate}")
    label_g5 = labels.get("g5") or {}
    exp.g5 = {
        # Exemptions are never widened by a label (README I1).
        "cr_exception": cr_exception,
        "hook_level": (hook_level or bool(label_g5.get("hook_level"))) and not cr_exception,
        "checker_level": checker_level or bool(label_g5.get("checker_level")),
    }
    for key, value in (("hook_level", hook_level), ("checker_level", checker_level),
                       ("cr_exception", cr_exception)):
        if bool(label_g5.get(key)) != value:
            exp.notes.append(f"g5_flag_differs_from_label:{key}")


def _cross_check(case: dict, exp: Expectation, numeric_rules: list) -> None:
    """Derived values against the frozen labels; disagreement = conflict (I2)."""
    labels = case["labels"]
    ev = labels.get("evidence") or {}
    ck = labels.get("checker") or {}
    conflicts = exp.conflicts

    def check(name: str, derived: Any, labelled: Any) -> None:
        if derived != labelled:
            conflicts.append(f"{name}:derived={derived!r}:label={labelled!r}")

    check("routed", exp.routed, labels.get("routed"))
    check("record_expected", exp.record_expected, ev.get("record_expected"))
    if exp.checked is False:
        check("checker_invoked", False, labels.get("checker_invoked"))
        check("expected_disposition", "not_checked", labels.get("expected_disposition"))
        check("expected_cause", "not_checked", labels.get("expected_cause"))
    elif not exp.routed:
        check("expected_cause", "legacy_unrouted", labels.get("expected_cause"))

    known = {r.rule_id: r for r in numeric_rules}
    for entry in ck.get("numeric_rules") or []:
        rid = entry.get("rule_id")
        if rid not in known:
            conflicts.append(f"label_numeric_rule_id_not_derived:{rid}")
            continue
        if exp.routed and rid in exp.numeric_applicability:
            outcome, mechanism = exp.numeric_applicability[rid]
            check(f"applicability:{rid}", outcome, entry.get("applicability"))
            reason = entry.get("applicability_reason")
            if outcome == EXCLUDED and reason is not None:
                if (reason == C.INCLUDE_MISS_REASON) != (mechanism == "include_miss"):
                    conflicts.append(f"exclusion_mechanism:{rid}:derived={mechanism}:label={reason!r}")
    for ident in (ck.get("literal_violations") or []) + (ev.get("violations") or []):
        rid = ident.get("rule_id") if isinstance(ident, dict) else None
        if rid not in exp.rule_ids:
            conflicts.append(f"label_identity_not_derived:{rid}")

    if not exp.routed:
        return
    check("checker.subject_kind", exp.checker_subject_kind, ck.get("subject_kind"))
    check("checker.governed_path",
          exp.governed_path if exp.trusted_proposed else None, ck.get("governed_path"))
    check("checker.subject_sha256",
          exp.content_sha256 if exp.trusted_proposed else None, ck.get("subject_sha256"))
    check("checker.literal_violations", exp.literal_violations,
          sorted([v.get("rule_id"), v.get("rule_type")] for v in ck.get("literal_violations") or []))
    check("evidence.checker_subject", exp.record_subject, ev.get("checker_subject"))
    labelled_applied = ev.get("applied_rule_ids") or []
    if len(set(labelled_applied)) != len(labelled_applied):
        conflicts.append("label_applied_rule_ids_duplicate")
    check("evidence.applied_rule_ids", exp.applied_rule_ids, sorted(labelled_applied))
    check("evidence.violations", exp.violations,
          sorted([v.get("rule_id"), v.get("rule_type")] for v in ev.get("violations") or []))
    check("evidence.per_rule_relevance", exp.per_rule_relevance, ev.get("per_rule_relevance"))
    check("evidence.event_relevance", exp.event_relevance, ev.get("event_relevance"))
    labelled_complete = ev.get("evaluation_complete")
    if ev.get("g6_routed_fallback") is True:
        labelled_complete = False  # R2 A2R2.3: the flag supersedes a stored null
        if exp.preconditions_ok:
            conflicts.append("g6_routed_fallback_flag_without_checker_fallback")
    check("evidence.evaluation_complete", exp.evaluation_complete, labelled_complete)
    check("evidence.mode", exp.mode, ev.get("mode"))
    check("evidence.hook_outcome", exp.disposition, ev.get("hook_outcome"))
    check("expected_disposition", exp.disposition, labels.get("expected_disposition"))
    check("expected_cause", exp.cause, C.CAUSE_TO_RECORD.get(labels.get("expected_cause")))
    if labels.get("exit_source") == "contract":
        check("expected_hook_exit", exp.exit, labels.get("expected_hook_exit"))
    check("target_after_hook", "absent", labels.get("target_after_hook"))
    attributed = exp.cause == "other_rule" and bool(exp.literal_violations)
    if exp.cause == "other_rule" or not exp.violations:
        check("literal_violation_attribution", attributed, labels.get("literal_violation_attribution"))

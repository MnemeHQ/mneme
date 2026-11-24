#!/usr/bin/env python3
"""AP1.1: offline, deterministic Markdown preview of a C4 gate report.

Renders a serialized ``mneme.c4.gate-report/v1`` artifact (the JSON file the
trusted C4 adapter writes) as plain Markdown for a human to read locally.

What this is NOT
----------------
* Not an authoritative gate result. The output always says so in its first
  lines ("Offline preview -- report-derived, not authenticated").
* Not authenticated. A coherent report rewritten to match the supplied
  context is displayed like any other; this renderer cannot detect forgery.
* Not a second evaluator. It never imports the adapter, never calls
  ``classify_payload`` or ``verify_report``, and never reclassifies a row.
  Its outer guard compares only the recorded row classifications against the
  recorded aggregate and disposition, as a display-eligibility check
  (suppress-only; a mismatch yields an "unavailable" preview, never a
  corrected verdict).

Standard library only. No network, subprocess or filesystem access beyond
reading the one input file and writing the one output. Not part of the wheel.

Pipeline (first failure wins; every failure renders an "unavailable" heading
and exits 2, and no reported classification is shown as a verdict):
size, UTF-8, JSON, duplicate keys, depth, then schema, 17 mandatory producer
keys with types, known classifications, expected-context match, counts and
``partly_unevaluated`` against the rows, aggregate and disposition against the
C4 precedence rules, posture/mode impossible cells. Only then is the reported
heading shown.

Untrusted data (paths, identifiers, selectors) is only ever shown inside
single-backtick code spans, escaped as follows.

Escape table (pinned)
---------------------
Truncate the raw string to 256 code points first (if longer, append
" (truncated, N more characters)" OUTSIDE the span, as generated prose).
Then map each code point:

    "\\" -> "\\\\"     "`" -> "\\x60"   "@" -> "\\x40"   "<" -> "\\x3c"
    ">"  -> "\\x3e"    "&" -> "\\x26"   "[" -> "\\x5b"   "]" -> "\\x5d"
    "("  -> "\\x28"    ")" -> "\\x29"   "|" -> "\\x7c"
    any code point whose unicodedata.category is in
    {Cc, Cf, Cs, Co, Cn, Zl, Zp} (controls including newline, return and
    tab, DEL, C1, bidi/zero-width/BOM format characters, lone surrogates,
    private use, unassigned, line and paragraph separators)
        -> "\\x%02x" if < 0x100, "\\u%04x" if <= 0xFFFF, else "\\U%08x"
    everything else unchanged.

Category Cn (unassigned) follows the running interpreter's ``unicodedata``
version, so output is byte-identical across operating systems for the same
Python minor version, not across minor versions; determinism is per
interpreter version. (Controls, surrogates and U+0378 are stable.)

The result never contains a backtick, a newline or a raw control character,
so it cannot break out of its span, start a mention, link, HTML tag or
workflow command, and always encodes as strict UTF-8. An empty value is shown
as the generated words "(empty value)".

Exit codes (presentation status only, never a merge or gate status):
0 rendered (any reported aggregate/disposition, including failure);
2 presentation unavailable (invalid/stale/inconsistent/over-limit report or
usage error); 3 output I/O failure.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any, NoReturn

REPORT_SCHEMA = "mneme.c4.gate-report/v1"

# Mirrors of the adapter's closed vocabularies (reimplemented, not imported).
VALID_MODES = ("strict", "warn")
VALID_POSTURES = ("open", "closed")
VERIFIED_PASS, WARN, VIOLATION, UNEVALUATED, REFUSED, SKIP = (
    "VERIFIED_PASS", "WARN", "VIOLATION", "UNEVALUATED", "REFUSED", "SKIP")
FILE_CLASSES = (VERIFIED_PASS, WARN, VIOLATION, UNEVALUATED, REFUSED, SKIP)
AGG_PASS = "PASS"
SUCCESS, FAILURE = "success", "failure"

MANDATORY_KEYS = (
    "schema", "adapter", "evaluator", "base_sha", "head_sha", "merge_base",
    "requested_mode", "query", "posture", "trusted_surface", "memory", "files",
    "gate_conditions", "aggregate", "disposition", "annotations", "summary_written")

# Limits (presentation only).
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_DEPTH = 32
MAX_ROWS = 2000
MAX_ANNOTATIONS = 2000
MAX_FIELD_CHARS = 4096
MAX_STDOUT_BYTES = 1024 * 1024
MAX_NESTED_DEPTH = 16
MAX_NESTED_RECORDS = 2000
MAX_DETAIL_FIELD_CHARS = 512
MAX_SPAN_CHARS = 256
MAX_SHOWN_ROWS = 50
MAX_SHOWN_DETAILS = 100
MAX_OUTPUT_BYTES = 64 * 1024
ROWS_BUDGET_BYTES = 24 * 1024
OMISSION_RESERVE_BYTES = 1024

TITLE = "## Mneme Architecture Protection — offline preview"
BANNER = ("_Offline preview — report-derived, not authenticated. "
          "Not an authoritative gate result._")

H_UNAVAILABLE = "Preview unavailable — report could not be displayed"
H_INCONSISTENT = "Preview unavailable — inconsistent report"
HEADINGS = {
    (AGG_PASS, SUCCESS): "Reported PASS — evaluated scope only",
    ("WARN", SUCCESS): "Reported WARN — advisory findings (warn mode only)",
    ("SKIP", SUCCESS): "Reported SKIP — no file required evaluation",
    ("VIOLATION", FAILURE): "Reported VIOLATION — strict gate failure (strict only)",
    ("REFUSED", FAILURE): "Reported REFUSED — policy or trusted-surface refusal",
    ("UNEVALUATED", SUCCESS): "Reported UNEVALUATED — evaluation incomplete (open only)",
    ("UNEVALUATED", FAILURE): "Reported UNEVALUATED — evaluation incomplete (closed only)",
}

KIND_LABELS = {
    "path": "Path could not be shown to be a normalized relative path",
    "policy": "Policy path",
    "trusted_surface": "Trusted-surface path",
    "deleted": "Deleted file, not evaluated",
    "mode": "Not a regular file",
    "timeout": "Evaluator timed out",
    "launch": "Evaluator could not start",
    "untrusted_result": "Evaluator result not trusted by the adapter",
    "workspace": "Gate workspace unavailable",
    "memory": "Trusted decision memory unavailable",
    "materialize": "File could not be materialized",
    "adapter_error": "Adapter error",
    "change_list": "Change list could not be established",
}
OTHER_REASON = "Other reported reason"

CONTEXT_FIELDS = ("base_sha", "head_sha", "adapter_sha256", "evaluator_commit",
                  "evaluator_wheel_sha256", "requested_mode", "posture")

# Display priority: non-success first, then pass.
PRIORITY = (REFUSED, VIOLATION, WARN, UNEVALUATED, SKIP, VERIFIED_PASS)
DETAIL_CLASSES = (VIOLATION, WARN)


# ── escaping ─────────────────────────────────────────────────────────────────

_ESCAPES = {
    "\\": "\\\\", "`": "\\x60", "@": "\\x40", "<": "\\x3c", ">": "\\x3e",
    "&": "\\x26", "[": "\\x5b", "]": "\\x5d", "(": "\\x28", ")": "\\x29",
    "|": "\\x7c",
}
_ESCAPED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


def escape_text(raw: str) -> str:
    """Apply the pinned escape table to ``raw`` (no truncation here)."""
    out = []
    for ch in raw:
        mapped = _ESCAPES.get(ch)
        if mapped is not None:
            out.append(mapped)
            continue
        if unicodedata.category(ch) in _ESCAPED_CATEGORIES:
            cp = ord(ch)
            if cp < 0x100:
                out.append("\\x%02x" % cp)
            elif cp <= 0xFFFF:
                out.append("\\u%04x" % cp)
            else:
                out.append("\\U%08x" % cp)
        else:
            out.append(ch)
    return "".join(out)


def code_span(raw: str, limit: int = MAX_SPAN_CHARS) -> str:
    """Return ``raw`` as one escaped, bounded inline-code span."""
    if raw == "":
        return "(empty value)"
    suffix = ""
    if len(raw) > limit:
        suffix = f" (truncated, {len(raw) - limit} more characters)"
        raw = raw[:limit]
    return "`" + escape_text(raw) + "`" + suffix


# ── parsing and validation ───────────────────────────────────────────────────

class _Unavailable(Exception):
    def __init__(self, heading: str, reason: str) -> None:
        super().__init__(reason)
        self.heading = heading
        self.reason = reason


class _DuplicateKey(ValueError):
    """Raised by the object_pairs_hook on a repeated key."""


def _no_dups(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise _DuplicateKey("duplicate key")
        out[key] = value
    return out


def _reject_constant(_name: str) -> Any:
    raise ValueError("non-finite number")


def _depth(value: Any) -> int:
    """Container nesting depth, iterative (a bare scalar is 0)."""
    best = 0
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        node, d = stack.pop()
        if isinstance(node, dict):
            d += 1
            best = max(best, d)
            stack.extend((v, d) for v in node.values())
        elif isinstance(node, list):
            d += 1
            best = max(best, d)
            stack.extend((v, d) for v in node)
    return best


def _fail(reason: str) -> NoReturn:
    raise _Unavailable(H_UNAVAILABLE, reason)


def _bad_shape() -> NoReturn:
    _fail("report fields are missing or malformed")


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _text(v: Any) -> str:
    if not isinstance(v, str):
        _bad_shape()
    if len(v) > MAX_FIELD_CHARS:
        _fail("a report field exceeds the display limits")
    return v


def _opt_text(d: dict[str, Any], key: str) -> None:
    if key in d:
        _text(d[key])


def _obj(v: Any) -> dict[str, Any]:
    if not isinstance(v, dict):
        _bad_shape()
    return v


def _parse(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_INPUT_BYTES:
        _fail("report exceeds the display limits")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        _fail("report is not valid UTF-8 JSON")
    try:
        report = json.loads(text, object_pairs_hook=_no_dups, parse_constant=_reject_constant)
    except RecursionError:
        _fail("report exceeds the display limits")
    except _DuplicateKey:
        _fail("report contains duplicate keys")
    except ValueError:
        _fail("report is not valid UTF-8 JSON")
    if not isinstance(report, dict):
        _fail("report is not a gate report object")
    if _depth(report) > MAX_DEPTH:
        _fail("report exceeds the display limits")
    return report


def _check_row(row: Any, is_file: bool) -> dict[str, Any]:
    row = _obj(row)
    cls = row.get("classification")
    if not isinstance(cls, str) or cls not in FILE_CLASSES:
        _fail("report contains an unknown classification")
    _text(row.get("reason"))
    for key in ("path", "status", "mode"):
        if is_file:
            _text(row.get(key))
        else:
            _opt_text(row, key)
    for key in ("kind", "sha256", "blob"):
        _opt_text(row, key)
    if "exit" in row and not _is_int(row["exit"]):
        _bad_shape()
    for key in ("stdout", "stderr_tail"):
        if key in row and not isinstance(row[key], str):
            _bad_shape()
    if "applicability" in row:
        app = row["applicability"]
        if not isinstance(app, list) or not all(isinstance(a, dict) for a in app):
            _bad_shape()
    return row


def aggregate_of(classes: list[str], mode: str) -> str:
    """Recorded-row precedence for the outer display guard (see module docs)."""
    s = set(classes)
    if REFUSED in s:
        return REFUSED
    if mode == "strict" and s & {VIOLATION, WARN}:
        return VIOLATION
    if UNEVALUATED in s:
        return UNEVALUATED
    if s & {VIOLATION, WARN}:
        return WARN
    if VERIFIED_PASS in s:
        return AGG_PASS
    return SKIP


def disposition_of(agg: str, posture: str) -> str:
    if agg in (REFUSED, VIOLATION):
        return FAILURE
    if agg == UNEVALUATED:
        return SUCCESS if posture == "open" else FAILURE
    return SUCCESS


def _validate(report: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    if report.get("schema") != REPORT_SCHEMA:
        _fail("unsupported report schema")
    if any(k not in report for k in MANDATORY_KEYS):
        _fail("report fields are missing or malformed")
    _text(report["schema"])
    adapter = _obj(report["adapter"])
    _text(adapter.get("path"))
    _text(adapter.get("sha256"))
    evaluator = _obj(report["evaluator"])
    _text(evaluator.get("commit"))
    _text(evaluator.get("wheel_sha256"))
    _opt_text(evaluator, "python")
    _text(report["base_sha"])
    _text(report["head_sha"])
    if report["merge_base"] is not None:
        _text(report["merge_base"])
    mode = report["requested_mode"]
    if not isinstance(mode, str) or mode not in VALID_MODES:
        _bad_shape()
    _text(report["query"])
    posture = _obj(report["posture"])
    effective = posture.get("effective")
    if not isinstance(effective, str) or effective not in VALID_POSTURES:
        _bad_shape()
    _text(posture.get("source"))
    if posture.get("fallback", None) is not None:
        _text(posture["fallback"])
    if "fallback" not in posture:
        _bad_shape()
    surface = report["trusted_surface"]
    if surface is not None:
        surface = _obj(surface)
        for key in ("files", "dirs"):
            if not isinstance(surface.get(key), list):
                _bad_shape()
            for item in surface[key]:
                _text(item)
    memory = report["memory"]
    if memory is not None:
        memory = _obj(memory)
        for key in ("path", "blob", "source_commit", "sha256"):
            _text(memory.get(key))
    files, conds = report["files"], report["gate_conditions"]
    if not isinstance(files, list) or not isinstance(conds, list):
        _bad_shape()
    if len(files) + len(conds) > MAX_ROWS:
        _fail("report exceeds the display limits")
    annotations = report["annotations"]
    if not isinstance(annotations, list):
        _bad_shape()
    if len(annotations) > MAX_ANNOTATIONS:
        _fail("report exceeds the display limits")
    for item in annotations:
        _text(item)
    if not isinstance(report["summary_written"], bool):
        _bad_shape()
    agg = _obj(report["aggregate"])
    agg_cls = agg.get("classification")
    if not isinstance(agg_cls, str) or agg_cls not in (REFUSED, VIOLATION, UNEVALUATED, WARN, AGG_PASS, SKIP):
        _bad_shape()
    _text(agg.get("reason"))
    if not isinstance(agg.get("partly_unevaluated"), bool):
        _bad_shape()
    counts = _obj(agg.get("counts"))
    for key, value in counts.items():
        if not _is_int(value):
            _bad_shape()
    disp = report["disposition"]
    if not isinstance(disp, str) or disp not in (SUCCESS, FAILURE):
        _bad_shape()
    file_rows = [_check_row(r, True) for r in files]
    cond_rows = [_check_row(r, False) for r in conds]

    # Expected context (field names only, never values).
    mismatched = [name for name, actual in (
        ("base_sha", report["base_sha"]), ("head_sha", report["head_sha"]),
        ("adapter_sha256", adapter["sha256"]), ("evaluator_commit", evaluator["commit"]),
        ("evaluator_wheel_sha256", evaluator["wheel_sha256"]),
        ("requested_mode", mode), ("posture", effective)) if actual != expected[name]]
    if mismatched:
        _fail("context mismatch: " + ", ".join(mismatched))

    # Consistency (suppress-only).
    classes = [r["classification"] for r in file_rows + cond_rows]
    want_counts = {c: classes.count(c) for c in FILE_CLASSES if c in classes}
    if counts != want_counts or agg["partly_unevaluated"] != (UNEVALUATED in classes):
        raise _Unavailable(H_INCONSISTENT, "recorded counts or flags do not match the recorded rows")
    want_agg = aggregate_of(classes, mode)
    if agg_cls != want_agg or disp != disposition_of(want_agg, effective):
        raise _Unavailable(H_INCONSISTENT, "recorded aggregate or disposition does not match the recorded rows")
    if posture["fallback"] is not None and effective != "closed":
        raise _Unavailable(H_INCONSISTENT, "recorded posture is not possible")
    if (agg_cls, disp) not in HEADINGS:
        raise _Unavailable(H_INCONSISTENT, "recorded aggregate or disposition does not match the recorded rows")
    return {"files": file_rows, "conds": cond_rows, "agg": agg_cls, "disp": disp,
            "counts": want_counts, "mode": mode, "posture": effective,
            "fallback": posture["fallback"] is not None,
            "partly": agg["partly_unevaluated"]}


def _check_expected(expected: Any) -> dict[str, Any]:
    if not isinstance(expected, dict):
        _fail("invalid expected context")
    for name in CONTEXT_FIELDS:
        v = expected.get(name)
        if not isinstance(v, str) or v == "":
            _fail("invalid expected context")
    if expected["requested_mode"] not in VALID_MODES or expected["posture"] not in VALID_POSTURES:
        _fail("invalid expected context")
    return expected


# ── detail extraction (ADR-033 section 2: structural only) ───────────────────

def _detail_field(rec: dict[str, Any], key: str) -> tuple[bool, str | None]:
    """(ok, value). Missing, null or empty is ok with value None."""
    v = rec.get(key)
    if v is None or v == "":
        return True, None
    if isinstance(v, str) and len(v) <= MAX_DETAIL_FIELD_CHARS:
        return True, v
    return False, None


def _extract_details(row: dict[str, Any]) -> tuple[list[tuple], int, int] | None:
    """Return (findings, suppressed_records, duplicates) or None if the whole
    row's details are unavailable. Never inspects verdict/exit/mode/severity
    coherence and never affects any classification."""
    stdout = row.get("stdout")
    path = row.get("path")
    if not isinstance(stdout, str) or not isinstance(path, str):
        return None
    if len(stdout.encode("utf-8", "surrogatepass")) > MAX_STDOUT_BYTES:
        return None
    try:
        payload = json.loads(stdout, object_pairs_hook=_no_dups, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        return None
    if not isinstance(payload, dict) or _depth(payload) > MAX_NESTED_DEPTH:
        return None
    violations = payload.get("violations")
    applicability = payload.get("applicability")
    if applicability is None:
        applicability = []
    if not isinstance(violations, list) or not isinstance(applicability, list):
        return None
    if len(violations) + len(applicability) > MAX_NESTED_RECORDS:
        return None
    outcomes: dict[tuple[str, str], set[str | None]] = {}
    for rec in applicability:
        if not isinstance(rec, dict) or rec.get("input_path") != path:
            continue
        ok_d, did = _detail_field(rec, "decision_id")
        ok_r, rid = _detail_field(rec, "rule_id")
        ok_o, out = _detail_field(rec, "outcome")
        if ok_d and ok_r and did and rid:
            outcomes.setdefault((did, rid), set()).add(out if ok_o else None)
    findings: list[tuple] = []
    seen: set[tuple] = set()
    suppressed = duplicates = 0
    for rec in violations:
        if not isinstance(rec, dict) or rec.get("input_path") != path:
            suppressed += 1
            continue
        fields = []
        ok = True
        for key in ("decision_id", "decision_version_id", "rule_id", "severity", "selector"):
            good, value = _detail_field(rec, key)
            ok = ok and good
            fields.append(value)
        if not ok:
            suppressed += 1
            continue
        outcome = None
        if fields[0] and fields[2]:
            found = outcomes.get((fields[0], fields[2]), set())
            if len(found) == 1:
                outcome = next(iter(found))
        item = (*fields, outcome)
        if item in seen:
            duplicates += 1
            continue
        seen.add(item)
        findings.append(item)
    return findings, suppressed, duplicates


# ── rendering ────────────────────────────────────────────────────────────────

def _size(line: str) -> int:
    return len(line.encode("utf-8")) + 1


def _unavailable(heading: str, reason: str) -> tuple[int, str]:
    lines = [TITLE, BANNER, "", "### " + heading, "", "Reason: " + reason, ""]
    return 2, "\n".join(lines)


def _kind_label(row: dict[str, Any]) -> str | None:
    kind = row.get("kind")
    if kind is None:
        return None if row["classification"] in (VERIFIED_PASS, WARN, VIOLATION) else OTHER_REASON
    return KIND_LABELS.get(kind, OTHER_REASON)


def _fmt_counts(rows: list[dict[str, Any]]) -> str:
    parts = [f"{c}: {sum(1 for r in rows if r['classification'] == c)}"
             for c in FILE_CLASSES if any(r["classification"] == c for r in rows)]
    return f"{len(rows)}" + (f" ({', '.join(parts)})" if parts else "")


def _row_line(row: dict[str, Any], is_file: bool) -> str:
    path = row.get("path")
    who = "File" if is_file else "Gate condition"
    if isinstance(path, str):
        who += " " + code_span(path)
    line = f"- {who}: {row['classification']}"
    label = _kind_label(row)
    if label:
        line += f" ({label})"
    return line


def _render_valid(v: dict[str, Any]) -> str:
    files, conds = v["files"], v["conds"]
    all_rows = [(r, True) for r in files] + [(r, False) for r in conds]
    present = set(v["counts"])
    out = [TITLE, BANNER, "", "### " + HEADINGS[(v["agg"], v["disp"])], "",
           f"Recorded adapter disposition: `{v['disp']}`"]
    if v["agg"] == "UNEVALUATED" and v["disp"] == SUCCESS:
        out.append("The recorded disposition reflects the open availability posture. "
                   "It is not a successful evaluation.")
    out += ["", f"- File rows: {_fmt_counts(files)}",
            f"- Gate conditions: {_fmt_counts(conds)}",
            f"- Partly unevaluated: {'yes' if v['partly'] else 'no'}"]
    if v["fallback"]:
        out += ["", "Availability fallback: closed"]
    notices = {
        REFUSED: "Notice: refused rows are present. A refusal is a policy or trusted-surface outcome.",
        VIOLATION: "Notice: violation rows are present.",
        WARN: "Notice: warn rows are present.",
        UNEVALUATED: "Notice: unevaluated rows are present. Evaluation is incomplete for them.",
        SKIP: "Notice: skipped rows were not evaluated. Skipping is not an allowance.",
    }
    shown_notices = [notices[c] for c in PRIORITY if c in present and c in notices]
    if shown_notices:
        out += [""] + shown_notices
    if v["agg"] == AGG_PASS:
        out += ["", "No violations reported in the evaluated scope."]

    # Rows: one representative per category first, then priority order.
    order = sorted(range(len(all_rows)),
                   key=lambda i: (PRIORITY.index(all_rows[i][0]["classification"]), i))
    reps, rest, seen_cls = [], [], set()
    for i in order:
        c = all_rows[i][0]["classification"]
        (rest if c in seen_cls else reps).append(i)
        seen_cls.add(c)
    base_bytes = sum(_size(x) for x in out) + 64
    admitted: list[int] = []
    used = 0
    for i in reps + rest:
        if len(admitted) >= MAX_SHOWN_ROWS:
            break
        line = _row_line(*all_rows[i])
        if used + _size(line) > ROWS_BUDGET_BYTES:
            continue
        admitted.append(i)
        used += _size(line)
    position = {idx: n for n, idx in enumerate(order)}
    admitted.sort(key=position.__getitem__)
    omitted_rows = len(all_rows) - len(admitted)
    if all_rows:
        out += ["", "#### Rows"] + [_row_line(*all_rows[i]) for i in admitted]
        used += _size("#### Rows") + 1
    base_bytes += used

    # Details (structural, report-derived; never alters anything above).
    detail_lines: list[str] = []
    duplicates = 0
    for i in order:
        row, _is_file = all_rows[i]
        if row["classification"] not in DETAIL_CLASSES:
            continue
        got = _extract_details(row)
        label = code_span(row["path"]) if isinstance(row.get("path"), str) else "(no path)"
        if got is None or not got[0]:
            detail_lines.append(f"- {label}: Details unavailable")
            continue
        findings, suppressed, dups = got
        duplicates += dups
        if suppressed:
            detail_lines.append(f"- {label}: Some details unavailable")
        for f in findings:
            names = ("decision", "version", "rule", "severity", "selector", "outcome")
            bits = [f"{n} " + (code_span(x) if x is not None else "Unavailable")
                    for n, x in zip(names, f)]
            detail_lines.append(f"- {label}: " + ", ".join(bits))
    shown_details: list[str] = []
    budget = MAX_OUTPUT_BYTES - base_bytes - OMISSION_RESERVE_BYTES - 64
    dused = 0
    for line in detail_lines:
        if len(shown_details) >= MAX_SHOWN_DETAILS or dused + _size(line) > budget:
            continue
        shown_details.append(line)
        dused += _size(line)
    omitted_details = len(detail_lines) - len(shown_details)
    if detail_lines:
        out += ["", "#### Finding details",
                "Details are report-derived and have not been re-verified."] + shown_details
    if omitted_rows or omitted_details or duplicates:
        out.append("")
    if omitted_rows:
        out.append(f"Rows omitted from this preview: {omitted_rows} (counts above include every row).")
    if omitted_details:
        out.append(f"Detail entries omitted from this preview: {omitted_details}.")
    if duplicates:
        out.append(f"Duplicate finding records collapsed: {duplicates}.")
    out.append("")
    return "\n".join(out)


def render(report_bytes: bytes, expected: dict[str, Any]) -> tuple[int, str]:
    """Pure entry point: ``(exit_code, markdown)``. Never raises."""
    try:
        exp = _check_expected(expected)
        report = _parse(report_bytes)
        valid = _validate(report, exp)
        text = _render_valid(valid)
        if len(text.encode("utf-8")) > MAX_OUTPUT_BYTES:
            _fail("preview cannot be bounded safely")
        return 0, text
    except _Unavailable as exc:
        return _unavailable(exc.heading, exc.reason)
    except (UnicodeError, RecursionError, MemoryError):
        return _unavailable(H_UNAVAILABLE, "preview cannot be bounded safely")


# ── CLI ──────────────────────────────────────────────────────────────────────

class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # usage errors exit 2, no traceback
        sys.stderr.write(self.format_usage())
        sys.stderr.write("render_pr_feedback: usage error (see --help)\n")
        raise SystemExit(2)


def _build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="render_pr_feedback.py", allow_abbrev=False,
                description="Offline Markdown preview of a C4 gate report (not authenticated).")
    p.add_argument("report", help="path to the serialized gate report JSON")
    p.add_argument("--expected-base-sha", required=True)
    p.add_argument("--expected-head-sha", required=True)
    p.add_argument("--expected-adapter-sha256", required=True)
    p.add_argument("--expected-evaluator-commit", required=True)
    p.add_argument("--expected-evaluator-wheel-sha256", required=True)
    p.add_argument("--expected-mode", required=True, choices=VALID_MODES)
    p.add_argument("--expected-posture", required=True, choices=VALID_POSTURES)
    p.add_argument("--output", default=None, help="write here instead of stdout")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    expected = {
        "base_sha": args.expected_base_sha, "head_sha": args.expected_head_sha,
        "adapter_sha256": args.expected_adapter_sha256,
        "evaluator_commit": args.expected_evaluator_commit,
        "evaluator_wheel_sha256": args.expected_evaluator_wheel_sha256,
        "requested_mode": args.expected_mode, "posture": args.expected_posture}
    try:
        with open(args.report, "rb") as fh:
            data = fh.read(MAX_INPUT_BYTES + 1)
    except OSError:
        code, text = _unavailable(H_UNAVAILABLE, "report file could not be read")
    else:
        code, text = render(data, expected)
    payload = text.encode("utf-8")
    try:
        if args.output:
            with open(args.output, "wb") as fh:
                fh.write(payload)
        else:
            sys.stdout.buffer.write(payload)
            sys.stdout.buffer.flush()
    except OSError:
        sys.stderr.write("render_pr_feedback: output could not be written\n")
        return 3
    return code


if __name__ == "__main__":
    sys.exit(main())

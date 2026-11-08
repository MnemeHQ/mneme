"""M1: lexical-context literal detection (charter section 4).

Tokenizes the file with the standard library ``tokenize`` module and matches
the forbidden literal only as a whole ``NAME`` token. Comments, string
literals (including docstrings and f-string text) and longer identifiers that
merely contain the literal never match.

Targets: C1, literal aspect only. M1 cannot see a deadline disabled without
the literal (``None``, ``float("inf")``, an environment switch spelled in a
string); those are expected misses, not ``UNEVALUATED``, because nothing in a
token stream marks them as outside M1's scope.

This is not ``FORBID_LITERAL``: ADR-019 keeps that rule exact and
context-free. A context-aware literal is a different rule type (ADR-019
section 9) and is only prototyped here.
"""

import io
import tokenize

from .common import (
    NO_VIOLATION,
    UNEVALUATED,
    VIOLATION,
    Finding,
    in_scope,
    load_template,
    not_targeted,
    out_of_scope,
)

METHOD_ID = "M1"
METHOD_VERSION = "p0a-m1-lexical/1.0.0"


def name_token_lines(source: str, literal: str) -> tuple:
    """Lines holding a ``NAME`` token exactly equal to ``literal``.

    Raises ``tokenize.TokenError`` or ``SyntaxError`` (including
    ``IndentationError``) when the source cannot be tokenized.
    """
    lines = set()
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.NAME and tok.string == literal:
            lines.add(tok.start[0])
    return tuple(sorted(lines))


def detect(source: str, target_path: str) -> dict:
    if not in_scope(target_path):
        return out_of_scope(target_path)
    literal = load_template()["symbols"]["forbidden_literal"]
    try:
        lines = name_token_lines(source, literal)
    except (tokenize.TokenError, SyntaxError) as e:
        c1 = Finding(UNEVALUATED, f"TOKENIZE_ERROR: {type(e).__name__}")
    else:
        if lines:
            c1 = Finding(VIOLATION, f"NAME_TOKEN: {literal} used as code", lines)
        else:
            c1 = Finding(NO_VIOLATION, f"NO_NAME_TOKEN: {literal} absent from code tokens")
    return {"C1": c1, "C2": not_targeted(METHOD_ID), "C3": not_targeted(METHOD_ID)}

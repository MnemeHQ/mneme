"""ADR-021 shell preflight: classify Bash tool input; reconstruct heredoc writes.

Classification is conservative and deterministic. Only one grammar is
reconstructable (class A): a single simple `cat` command redirecting a
quoted-delimiter here-document to one plain path token:

    cat >  <path> << 'DELIM'   (overwrite)
    cat >> <path> << "DELIM"   (append)

A quoted delimiter suppresses every expansion, so the document body is
byte-identical to what the shell will store. Everything else is class B
(potentially mutating) unless provably read-only (class C). Classification
alone never blocks anything; only class A reaches the checker, and only its
trusted verdict can block. See ADR-021.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple, Union


class Classification(str, Enum):
    RECONSTRUCTABLE = "RECONSTRUCTABLE"
    POTENTIALLY_MUTATING = "POTENTIALLY_MUTATING"
    NON_MUTATING = "NON_MUTATING"


@dataclass(frozen=True)
class ReconstructedWrite:
    """A deterministically provable repository mutation."""

    target_path: str       # exactly as spelled in the command
    proposed_content: str  # full document body, newline-terminated
    append: bool


# ── tokenizer ────────────────────────────────────────────────────────────────
#
# A tiny lexer for ONE command line: words separated by whitespace, single or
# double quoted spans (taken literally), and the operators >>, >, <<. Anything
# this lexer cannot handle makes the command non-reconstructable, which is the
# safe direction.

Token = Tuple[str, Union[str, None]]  # ("WORD"|"QWORD", text) | ("OP", op)


class _LexerError(Exception):
    pass


def _tokenize_line(line: str) -> List[Token]:
    tokens: List[Token] = []
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if ch in " \t":
            i += 1
            continue
        if line.startswith(">>", i):
            tokens.append(("OP", ">>"))
            i += 2
            continue
        if ch == ">":
            tokens.append(("OP", ">"))
            i += 1
            continue
        if line.startswith("<<", i):
            tokens.append(("OP", "<<"))
            i += 2
            continue
        if ch in "<&|;()":
            raise _LexerError(f"unsupported character {ch!r}")
        if ch in "'\"":
            quote = ch
            i += 1
            start = i
            while i < n and line[i] != quote:
                i += 1
            if i >= n:
                raise _LexerError("unterminated quote")
            tokens.append(("QWORD", line[start:i]))
            i += 1
            continue
        start = i
        while i < n and line[i] not in " \t<>'\";&|()":
            i += 1
        tokens.append(("WORD", line[start:i]))
    return tokens


def _is_plain_path_token(word: str) -> bool:
    if not word or word.startswith("-"):
        return False
    banned = "$`*?[]{}~!\n\r"
    return not any(c in banned for c in word)


def _parse_delim_token(token: Token) -> Optional[str]:
    """Return the delimiter of a *quoted* heredoc tag token, else None.

    Quoting ('EOF' or "EOF") is what makes the body literal. An unquoted
    delimiter means expansion happens and the bytes are unknowable.
    """
    kind, word = token
    if kind != "QWORD":
        return None
    if not word or "\n" in word:
        return None
    return word


def reconstruct_heredoc_write(command: str) -> Optional[ReconstructedWrite]:
    """Reconstruct the proposed mutation of a supported heredoc write, or None."""
    if command is None:
        return None
    normalized = command.replace("\r\n", "\n").replace("\r", "\n")
    stripped = normalized.strip("\n")
    if not stripped.strip():
        return None
    first_nl = stripped.find("\n")
    first_line = stripped if first_nl < 0 else stripped[:first_nl]
    rest = "" if first_nl < 0 else stripped[first_nl + 1:]

    try:
        tokens = _tokenize_line(first_line)
    except _LexerError:
        return None

    if len(tokens) != 5:
        return None
    kinds = [t[0] for t in tokens]
    # Canonical shape only: cat REDIRECT PATH << 'DELIM'
    if kinds != ["WORD", "OP", "WORD", "OP", "QWORD"]:
        return None
    (cat_w, redirect_t, path_t, heredoc_t, delim_t) = tokens
    if cat_w[1] != "cat" or redirect_t[1] not in (">", ">>") or heredoc_t[1] != "<<":
        return None
    path = path_t[1]
    delim = _parse_delim_token(delim_t)
    if delim is None or not _is_plain_path_token(path):
        return None

    lines = rest.split("\n") if rest else []
    body_lines: List[str] = []
    terminated = False
    trailing = False
    for line in lines:
        if terminated:
            if line.strip():
                # Anything after the closing delimiter is a separate command
                # we have not reconstructed; refusing is the safe direction.
                trailing = True
            continue
        if line == delim:
            terminated = True
            continue
        body_lines.append(line)
    if not terminated or trailing:
        return None
    body = "\n".join(body_lines) + "\n"
    return ReconstructedWrite(
        target_path=path,
        proposed_content=body,
        append=(redirect_t[1] == ">>"),
    )


# ── classification ───────────────────────────────────────────────────────────

_POTENTIALLY_MUTATING_COMMANDS = frozenset({
    "rm", "mv", "cp", "touch", "mkdir", "rmdir", "tee", "sed", "awk", "perl",
    "ruby", "php", "lua", "chmod", "chown", "chgrp", "ln", "dd", "truncate",
    "shred", "install", "patch", "make", "cmake", "cargo", "go", "gradle",
    "mvn", "npm", "npx", "yarn", "pnpm", "pip", "pip3", "pipx", "uv", "poetry",
    "git", "sh", "bash", "zsh", "dash", "ksh", "pwsh", "pwsh-preview",
    "powershell", "cmd", "dotnet", "javac", "java", "rustc", "gcc", "clang",
})

_READ_ONLY_GIT_SUBCOMMANDS = frozenset({
    "status", "log", "show", "diff", "branch", "tag", "blame", "rev-parse",
    "ls-files", "ls-remote", "describe", "remote", "config", "help",
})


def _first_word(command: str) -> str:
    for part in command.split():
        return part
    return ""


def _looks_mutating(command: str) -> bool:
    """Conservative heuristic used ONLY for diagnostic trace metadata."""
    head = _first_word(command).lower()
    base = head.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if base in _POTENTIALLY_MUTATING_COMMANDS:
        if base == "git":
            parts = command.split()
            if len(parts) > 1 and parts[1] in _READ_ONLY_GIT_SUBCOMMANDS:
                return False
        return True
    for marker in (">>", "<<", "&&", "||", ";", "|", "&", "`", "$(", "$("):
        if marker in command:
            return True
    if ">" in command or "<" in command:
        return True
    return False


_SAFE_READ_ONLY_COMMANDS = frozenset({
    "ls", "pwd", "echo", "printf", "cat", "head", "tail", "wc", "grep", "rg",
    "findstr", "which", "type", "where", "whoami", "hostname", "date", "env",
    "printenv", "uname", "id", "groups", "tty", "true", "false", "test",
    "diff", "cmp", "stat", "du", "df", "ps", "jobs", "sleep", "seq", "expr",
    "basename", "dirname", "realpath", "readlink", "sort", "uniq", "cut",
    "tr", "column", "nl", "od", "hexdump", "md5sum", "sha256sum", "cksum",
    "git", "file",
})


def classify_command(command: str) -> Classification:
    if reconstruct_heredoc_write(command) is not None:
        return Classification.RECONSTRUCTABLE
    if _looks_mutating(command):
        return Classification.POTENTIALLY_MUTATING
    head = _first_word(command).lower()
    base = head.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if base in _SAFE_READ_ONLY_COMMANDS:
        if base == "git":
            sub = command.split()[1:2]
            if sub and sub[0] in _READ_ONLY_GIT_SUBCOMMANDS:
                return Classification.NON_MUTATING
            return Classification.POTENTIALLY_MUTATING
        return Classification.NON_MUTATING
    return Classification.POTENTIALLY_MUTATING

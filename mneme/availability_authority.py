"""ADR-033 C2b verified availability authorization (Architecture A).

The verifier reads the live tip of the remote default branch of the policy
root's ``origin`` and resolves the authorization state from the declaration's
authority events at that tip (C2b charter §§3-5). It keeps no state between
calls: no cache, no host enrollment record, nothing written outside a
temporary directory that is removed afterwards.

The authority operations (charter §6) only prepare ``.mneme/availability.json``
for a reviewed change. They never commit, push, merge or touch canonical
memory; authorization takes effect only once the event is at the baseline tip.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlsplit, urlunsplit


SCHEMA = "mneme.availability/v1"
DECLARATION_PATH = ".mneme/availability.json"
MEMORY_PATH = ".mneme/project_memory.json"

AUTHORIZED = "AUTHORIZED"
REVOKED = "REVOKED"
VERIFIED_ABSENT = "VERIFIED_ABSENT"
UNVERIFIABLE = "AUTHORIZATION_UNVERIFIABLE"

# ADR-033 §4.3 closed reason set. ROLLBACK_DETECTED and CLOCK_REGRESSION are
# reserved for Architecture B and never produced here.
NETWORK = "NETWORK"
DNS = "DNS"
TLS_IDENTITY_MISMATCH = "TLS_IDENTITY_MISMATCH"
AUTH = "AUTH"
TIMEOUT = "TIMEOUT"
VERIFIER_CRASH = "VERIFIER_CRASH"
REF_MISSING = "REF_MISSING"
HISTORY_INCOMPLETE = "HISTORY_INCOMPLETE"
EVIDENCE_INVALID = "EVIDENCE_INVALID"
VERIFIER_CONFIG_MISSING = "VERIFIER_CONFIG_MISSING"

# Local relation to the baseline declaration (charter §5.2).
MATCH = "MATCH"
BEHIND = "BEHIND"
DIVERGES = "DIVERGES"
INVALID = "INVALID"

_VERIFIER_TIMEOUT_SECONDS = 15.0

_EVENT_KEYS = {"seq", "op", "prev", "review", "activation"}
_REVIEW_KEYS = {"recorded_by", "independent_approver_attested", "baseline_protection_attested"}
_ACTIVATION_KEYS = {"activated_at", "protected_decisions"}


class EvidenceInvalid(ValueError):
    """Baseline evidence does not satisfy the charter §4 contract."""


class VerifierFailure(Exception):
    """Verification could not complete; carries a closed-set reason."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class ActivationEvidence:
    """Activation facts read from canonical memory at the baseline tip."""

    state: str
    activated_at: Optional[str]
    protected_decisions: tuple[str, ...]


@dataclass(frozen=True)
class Verification:
    """One live verification result (charter §3)."""

    authorization: str
    reason: str = ""
    detail: str = ""
    url: str = ""
    branch: str = ""
    tip: str = ""
    baseline: Optional[dict[str, Any]] = None
    activation: Optional[ActivationEvidence] = None
    activation_problem: str = ""

    def as_tuple(self) -> tuple[str, str]:
        return self.authorization, self.reason


# ── Declaration contract (charter §4) ─────────────────────────────────────────

def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def event_digest(event: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(event)).hexdigest()


def normalize_url(url: str) -> str:
    """Lowercase scheme and host, drop default port, trailing ``/`` and ``.git``."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if port is not None and not (scheme == "https" and port == 443):
        host = f"{host}:{port}"
    path = parts.path.rstrip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    return urlunsplit((scheme, host, path, "", ""))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceInvalid(message)


def _validate_review(review: Any, label: str) -> None:
    _require(isinstance(review, dict) and set(review) == _REVIEW_KEYS,
             f"{label}: review must have exactly {sorted(_REVIEW_KEYS)}")
    _require(isinstance(review["recorded_by"], str) and review["recorded_by"].strip() != "",
             f"{label}: review.recorded_by must be a nonempty string")
    for key in ("independent_approver_attested", "baseline_protection_attested"):
        _require(isinstance(review[key], bool), f"{label}: review.{key} must be a boolean")


def _validate_activation(activation: Any, label: str) -> None:
    _require(isinstance(activation, dict) and set(activation) == _ACTIVATION_KEYS,
             f"{label}: activation must have exactly {sorted(_ACTIVATION_KEYS)}")
    _require(isinstance(activation["activated_at"], str) and activation["activated_at"] != "",
             f"{label}: activation.activated_at must be a nonempty string")
    ids = activation["protected_decisions"]
    _require(isinstance(ids, list) and ids != []
             and all(isinstance(i, str) and i != "" for i in ids)
             and ids == sorted(set(ids)),
             f"{label}: activation.protected_decisions must be a nonempty sorted set of ids")


def validate_events(events: Any) -> list[dict[str, Any]]:
    """Validate the append-only authority list; order is list position only."""
    _require(isinstance(events, list) and events != [], "authority.events must be a nonempty list")
    previous: Optional[dict[str, Any]] = None
    for index, event in enumerate(events):
        label = f"event {index + 1}"
        _require(isinstance(event, dict), f"{label}: not an object")
        op = event.get("op")
        _require(op in ("authorize", "revoke"), f"{label}: op must be authorize or revoke")
        expected_keys = _EVENT_KEYS if op == "authorize" else _EVENT_KEYS - {"activation"}
        _require(set(event) == expected_keys, f"{label}: keys must be {sorted(expected_keys)}")
        seq = event["seq"]
        _require(isinstance(seq, int) and not isinstance(seq, bool) and seq == index + 1,
                 f"{label}: seq must be {index + 1}")
        if previous is None:
            _require(event["prev"] is None, f"{label}: prev must be null")
        else:
            _require(event["prev"] == event_digest(previous), f"{label}: prev does not chain")
            _require(op != previous["op"], f"{label}: repeats op {op!r}")
        _validate_review(event["review"], label)
        if op == "authorize":
            _validate_activation(event["activation"], label)
        previous = event
    return events


def validate_declaration(data: Any) -> dict[str, Any]:
    """Full C2b validation of a baseline declaration (charter §4)."""
    _require(isinstance(data, dict), "declaration is not an object")
    _require(data.get("schema") == SCHEMA, "invalid schema")
    _require(data.get("availability") == "closed", "invalid availability")
    _require(data.get("memory_path") == MEMORY_PATH, "invalid memory_path")
    repository = data.get("repository")
    _require(isinstance(repository, dict), "repository missing")
    _require(set(repository) == {"url", "branch"}, "repository must have exactly url and branch")
    _require(isinstance(repository["url"], str) and repository["url"] != ""
             and normalize_url(repository["url"]) == repository["url"],
             "repository.url must be a normalized URL")
    _require(isinstance(repository["branch"], str) and repository["branch"] != "",
             "repository.branch must be a nonempty string")
    authority = data.get("authority")
    _require(isinstance(authority, dict) and set(authority) == {"events"},
             "authority must have exactly events")
    validate_events(authority["events"])
    return data


def local_relation(local: Optional[dict[str, Any]], problem: str,
                   baseline: dict[str, Any]) -> str:
    """Compare parsed objects so line endings and key order do not matter."""
    if problem or not isinstance(local, dict):
        return INVALID
    if local == baseline:
        return MATCH
    local_events = (local.get("authority") or {}).get("events") if isinstance(
        local.get("authority"), dict) else None
    base_events = baseline["authority"]["events"]
    if isinstance(local_events, list) and len(local_events) < len(base_events) \
            and base_events[: len(local_events)] == local_events:
        rest_local = {k: v for k, v in local.items() if k != "authority"}
        rest_base = {k: v for k, v in baseline.items() if k != "authority"}
        if rest_local == rest_base and set(local["authority"]) == {"events"}:
            return BEHIND
    return DIVERGES


# ── Repository location (charter §3.2) ───────────────────────────────────────

def _git_common_dir(root: Path) -> Optional[Path]:
    dot_git = root / ".git"
    if dot_git.is_dir():
        return dot_git
    if not dot_git.is_file():
        return None
    try:
        text = dot_git.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    if not text.startswith("gitdir:"):
        return None
    git_dir = Path(text[len("gitdir:"):].strip())
    if not git_dir.is_absolute():
        git_dir = (root / git_dir).resolve()
    commondir = git_dir / "commondir"
    if commondir.is_file():
        try:
            common = Path(commondir.read_text(encoding="utf-8").strip())
        except (OSError, UnicodeError):
            return None
        return common if common.is_absolute() else (git_dir / common).resolve()
    return git_dir


# ── Git execution (charter §3.3) ─────────────────────────────────────────────

_PASSTHROUGH = ("PATH", "SYSTEMROOT", "COMSPEC", "PATHEXT", "WINDIR")


def _git_environment(home: Path) -> dict[str, str]:
    """A constructed environment; nothing else from the parent passes through."""
    env = {name: os.environ[name] for name in _PASSTHROUGH if name in os.environ}
    empty = home / "empty.gitconfig"
    if not empty.exists():
        empty.write_bytes(b"")
    for name in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "TMP", "TEMP"):
        env[name] = str(home)
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": str(empty),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CEILING_DIRECTORIES": str(home.parent),
    })
    return env


def _protocol_options(allow_file: bool) -> list[str]:
    options = [
        "-c", "protocol.allow=never",
        "-c", "protocol.https.allow=always",
        "-c", "http.sslVerify=true",
        "-c", "credential.helper=",
        "-c", "core.askPass=",
    ]
    if allow_file:
        # Test transport only (charter §9); never reachable from the hook.
        options += ["-c", "protocol.file.allow=always"]
    return options


def _run_git(argv: list[str], *, env: dict[str, str], cwd: Path,
             timeout: float) -> subprocess.CompletedProcess:
    """Single subprocess seam so tests can record argv, env and endpoint."""
    return subprocess.run(
        argv, cwd=str(cwd), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, check=False,
    )


def classify_git_failure(stderr: str) -> str:
    """Best-effort reason mapping (charter §3.7); unknown -> VERIFIER_CRASH."""
    text = stderr.lower()
    if "could not resolve host" in text or "name or service not known" in text:
        return DNS
    if "ssl" in text or "certificate" in text or "tls" in text:
        return TLS_IDENTITY_MISMATCH
    if ("authentication failed" in text or "could not read username" in text
            or "terminal prompts disabled" in text or " 401" in text or " 403" in text):
        return AUTH
    if ("failed to connect" in text or "connection refused" in text
            or "connection reset" in text or "couldn't connect" in text
            or "connection timed out" in text or "network is unreachable" in text):
        return NETWORK
    return VERIFIER_CRASH


def _remove_tree(path: Path) -> None:
    """Remove a temp directory, including Git's read-only object files."""
    import stat

    def retry(function, target, _info):
        try:
            os.chmod(target, stat.S_IWRITE)
            function(target)
        except OSError:
            pass
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


class _GitSession:
    """One temporary bare repository and one deadline for one verification."""

    def __init__(self, url: str, *, allow_file: bool, timeout: float) -> None:
        self.url = url
        self.allow_file = allow_file
        self.deadline = time.monotonic() + timeout
        self.home = Path(tempfile.mkdtemp(prefix="mneme-verify-"))
        self.git_dir = self.home / "baseline.git"
        self.env = _git_environment(self.home)

    def close(self) -> None:
        _remove_tree(self.home)

    def git(self, *args: str, repo: bool = True) -> str:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise VerifierFailure(TIMEOUT, "verifier budget exhausted")
        argv = ["git", *_protocol_options(self.allow_file)]
        if repo:
            argv += ["--git-dir", str(self.git_dir)]
        argv += list(args)
        try:
            proc = _run_git(argv, env=self.env, cwd=self.home, timeout=remaining)
        except subprocess.TimeoutExpired:
            raise VerifierFailure(TIMEOUT, "verifier budget exhausted") from None
        except OSError as exc:
            raise VerifierFailure(VERIFIER_CRASH, f"git could not run: {exc}") from None
        if proc.returncode != 0:
            raise VerifierFailure(classify_git_failure(proc.stderr), _first_line(proc.stderr))
        return proc.stdout

    def init(self) -> None:
        self.git("init", "--bare", "-q", str(self.git_dir), repo=False)
        self.git("remote", "add", "origin", self.url)

    def tip(self) -> tuple[str, str]:
        out = self.git("ls-remote", "--symref", self.url, "HEAD", repo=False)
        branch = sha = ""
        for line in out.splitlines():
            if line.startswith("ref: ") and line.endswith("\tHEAD"):
                ref = line[len("ref: "):-len("\tHEAD")]
                if ref.startswith("refs/heads/"):
                    branch = ref[len("refs/heads/"):]
            elif line.endswith("\tHEAD"):
                sha = line.split("\t", 1)[0]
        if not branch or not sha:
            raise VerifierFailure(REF_MISSING, "remote HEAD symref not found")
        return branch, sha

    def fetch(self, sha: str, *, full: bool) -> None:
        args = ["fetch", "-q", "--no-tags", "--filter=blob:none"]
        if not full:
            args.append("--depth=1")
        elif self.is_shallow():
            args.append("--unshallow")
        try:
            self.git(*args, "origin", sha)
        except VerifierFailure as exc:
            if exc.reason == VERIFIER_CRASH:
                raise VerifierFailure(REF_MISSING, exc.detail) from None
            raise

    def has_path(self, rev: str, path: str) -> bool:
        out = self.git("ls-tree", "--name-only", rev, "--", path)
        return out.strip() != ""

    def read(self, rev: str, path: str) -> bytes:
        return self.git("cat-file", "blob", f"{rev}:{path}").encode("utf-8")

    def is_shallow(self) -> bool:
        return self.git("rev-parse", "--is-shallow-repository").strip() == "true"

    def last_change(self, sha: str, path: str) -> Optional[str]:
        out = self.git("rev-list", "--first-parent", "-n", "1", sha, "--", path)
        return out.strip() or None


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:200]
    return ""


def _parse_json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise EvidenceInvalid(f"{label} is not valid JSON") from exc


def read_activation(raw: bytes) -> ActivationEvidence:
    """Activation and protected decisions via the existing canonical loader."""
    from mneme.decision_index import BINDING_AUTHORITY_PROTECTION
    from mneme.decision_index_persistence import (
        DecisionIndexPersistenceError, load_persisted_decision_index,
    )
    document = _parse_json(raw, "baseline memory")
    _require(isinstance(document, dict), "baseline memory is not an object")
    activation = document.get("activation")
    _require(isinstance(activation, dict), "baseline memory has no activation record")
    _require("decision_index" in document, "baseline memory has no decision_index")
    try:
        index = load_persisted_decision_index(document["decision_index"])
    except DecisionIndexPersistenceError as exc:
        raise EvidenceInvalid(f"baseline decision_index invalid: {exc}") from exc
    protected = sorted({
        rule.decision_id for rule in index.rules
        if rule.binding_authority == BINDING_AUTHORITY_PROTECTION
    })
    return ActivationEvidence(
        state=str(activation.get("state")),
        activated_at=activation.get("activated_at"),
        protected_decisions=tuple(protected),
    )


# ── Verification (charter §5.1) ───────────────────────────────────────────────

def origin_url(policy_root: Path, *, allow_file: bool = False) -> str:
    """``remote.origin.url`` from the repository's own config file only."""
    common = _git_common_dir(policy_root)
    if common is None or not (common / "config").is_file():
        raise VerifierFailure(VERIFIER_CONFIG_MISSING, "policy root is not a Git top-level")
    home = Path(tempfile.mkdtemp(prefix="mneme-verify-"))
    try:
        try:
            proc = _run_git(
                ["git", "config", "--file", str(common / "config"),
                 "--get-all", "remote.origin.url"],
                env=_git_environment(home), cwd=home, timeout=_VERIFIER_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            raise VerifierFailure(TIMEOUT, "git config timed out") from None
        except OSError as exc:
            raise VerifierFailure(VERIFIER_CRASH, f"git could not run: {exc}") from None
    finally:
        _remove_tree(home)
    urls = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if len(urls) != 1:
        raise VerifierFailure(VERIFIER_CONFIG_MISSING, "origin must have exactly one URL")
    url = urls[0]
    parts = urlsplit(url)
    allowed = {"https"} | ({"file"} if allow_file else set())
    if parts.scheme.lower() not in allowed or parts.username or parts.password \
            or parts.query or parts.fragment:
        raise VerifierFailure(VERIFIER_CONFIG_MISSING, "origin must be a plain HTTPS URL")
    return url


def verify(policy_root: Path, *, allow_file: bool = False,
           want_activation: bool = False,
           timeout: float = _VERIFIER_TIMEOUT_SECONDS) -> Verification:
    """Resolve the baseline state ``B`` for one policy root. Never raises."""
    try:
        url = origin_url(Path(policy_root), allow_file=allow_file)
    except VerifierFailure as exc:
        return Verification(UNVERIFIABLE, exc.reason, exc.detail)
    except Exception as exc:  # noqa: BLE001 -- a verifier crash is a reason, not an error
        return Verification(UNVERIFIABLE, VERIFIER_CRASH, type(exc).__name__)
    normalized = normalize_url(url)
    branch = tip = ""
    try:
        session = _GitSession(url, allow_file=allow_file, timeout=timeout)
    except OSError as exc:
        return Verification(UNVERIFIABLE, VERIFIER_CRASH, type(exc).__name__, normalized)
    try:
        session.init()
        branch, tip = session.tip()
        session.fetch(tip, full=False)
        if session.has_path(tip, DECLARATION_PATH):
            return _resolve_tip(session, normalized, branch, tip, want_activation)
        return _resolve_history(session, normalized, branch, tip, want_activation)
    except VerifierFailure as exc:
        return Verification(UNVERIFIABLE, exc.reason, exc.detail, normalized, branch, tip)
    except EvidenceInvalid as exc:
        return Verification(UNVERIFIABLE, EVIDENCE_INVALID, str(exc), normalized, branch, tip)
    except Exception as exc:  # noqa: BLE001
        return Verification(UNVERIFIABLE, VERIFIER_CRASH, type(exc).__name__,
                            normalized, branch, tip)
    finally:
        session.close()


def _activation_at_tip(session: _GitSession, tip: str
                       ) -> tuple[Optional[ActivationEvidence], str]:
    if not session.has_path(tip, MEMORY_PATH):
        return None, "baseline memory missing"
    try:
        return read_activation(session.read(tip, MEMORY_PATH)), ""
    except EvidenceInvalid as exc:
        return None, str(exc)


def _resolve_tip(session: _GitSession, url: str, branch: str, tip: str,
                 want_activation: bool) -> Verification:
    declaration = validate_declaration(
        _parse_json(session.read(tip, DECLARATION_PATH), "baseline declaration"))
    _require(declaration["repository"]["url"] == url,
             "origin URL does not match the baseline repository.url")
    _require(declaration["repository"]["branch"] == branch,
             "remote default branch does not match the baseline repository.branch")
    last = declaration["authority"]["events"][-1]
    if last["op"] == "revoke":
        activation, problem = (_activation_at_tip(session, tip) if want_activation
                               else (None, ""))
        return Verification(REVOKED, url=url, branch=branch, tip=tip, baseline=declaration,
                            activation=activation, activation_problem=problem)
    activation, problem = _activation_at_tip(session, tip)
    _require(activation is not None, problem)
    assert activation is not None
    _require(activation.state == "active", "baseline activation state is not active")
    _require(activation.activated_at == last["activation"]["activated_at"],
             "baseline activated_at differs from the authorize event")
    missing = set(last["activation"]["protected_decisions"]) - set(activation.protected_decisions)
    _require(not missing, f"protection removed at baseline for {sorted(missing)}")
    return Verification(AUTHORIZED, url=url, branch=branch, tip=tip, baseline=declaration,
                        activation=activation)


def _resolve_history(session: _GitSession, url: str, branch: str, tip: str,
                     want_activation: bool) -> Verification:
    # Only labels the outcome: none of these states can refuse (charter §5.1).
    session.fetch(tip, full=True)
    if session.is_shallow():
        raise VerifierFailure(HISTORY_INCOMPLETE, "baseline history is shallow")
    activation, problem = (_activation_at_tip(session, tip) if want_activation
                           else (None, ""))
    change = session.last_change(tip, DECLARATION_PATH)
    if change is None:
        return Verification(VERIFIED_ABSENT, url=url, branch=branch, tip=tip,
                            activation=activation, activation_problem=problem)
    previous = f"{change}^1"
    try:
        events = validate_declaration(_parse_json(
            session.read(previous, DECLARATION_PATH), "deleted declaration",
        ))["authority"]["events"]
    except EvidenceInvalid:
        events = []
    if events and events[-1]["op"] == "revoke":
        return Verification(REVOKED, url=url, branch=branch, tip=tip,
                            activation=activation, activation_problem=problem)
    raise EvidenceInvalid("declaration deleted at baseline without a revocation record")


# ── Authority operations (charter §6) ────────────────────────────────────────

class AuthorityRefused(Exception):
    """An authority operation's precondition was not met; nothing written."""


@dataclass
class Attestation:
    recorded_by: str
    independent_approver_attested: bool
    baseline_protection_attested: bool

    def as_review(self) -> dict[str, Any]:
        return {
            "recorded_by": self.recorded_by,
            "independent_approver_attested": self.independent_approver_attested,
            "baseline_protection_attested": self.baseline_protection_attested,
        }


def find_policy_root(start: Path) -> Optional[Path]:
    current = Path(start).resolve()
    while True:
        if (current / ".mneme").is_dir():
            return current
        if current.parent == current:
            return None
        current = current.parent


def _read_local(path: Path) -> tuple[Optional[Any], bool]:
    if not path.exists():
        return None, False
    try:
        return json.loads(path.read_text(encoding="utf-8")), True
    except (OSError, UnicodeError, ValueError):
        return None, True


def prepare_event(policy_root: Path, op: str, attestation: Attestation, *,
                  replace_local: bool = False, allow_file: bool = False,
                  verifier: Optional[Callable[..., Verification]] = None,
                  ) -> tuple[Path, dict[str, Any], Verification]:
    """Write the declaration with one appended event, after live preconditions.

    Writes only ``.mneme/availability.json``; never runs a mutating Git
    command and never touches canonical memory.
    """
    from mneme.setup_state import atomic_write_json

    if op not in ("authorize", "revoke"):
        raise ValueError("op must be authorize or revoke")
    run = verifier or verify
    result = run(policy_root, allow_file=allow_file, want_activation=True)
    if result.authorization == UNVERIFIABLE:
        raise AuthorityRefused(
            f"baseline unverifiable ({result.reason}"
            + (f": {result.detail}" if result.detail else "") + "); nothing written")
    if op == "authorize" and result.authorization not in (VERIFIED_ABSENT, REVOKED):
        raise AuthorityRefused(f"authorize needs VERIFIED_ABSENT or REVOKED, "
                               f"baseline is {result.authorization}")
    if op == "revoke" and result.authorization != AUTHORIZED:
        raise AuthorityRefused(f"revoke needs AUTHORIZED, baseline is {result.authorization}")

    path = Path(policy_root) / DECLARATION_PATH
    local, exists = _read_local(path)
    if exists and local != result.baseline and not replace_local:
        raise AuthorityRefused("local declaration differs from the baseline; "
                               "pass --replace-local to overwrite it")

    if result.baseline is not None:
        document = json.loads(json.dumps(result.baseline))
    else:
        document = {
            "schema": SCHEMA, "availability": "closed", "memory_path": MEMORY_PATH,
            "repository": {"url": result.url, "branch": result.branch},
            "authority": {"events": []},
        }
    events = document["authority"]["events"]
    event: dict[str, Any] = {
        "seq": len(events) + 1,
        "op": op,
        "prev": event_digest(events[-1]) if events else None,
        "review": attestation.as_review(),
    }
    if op == "authorize":
        activation = result.activation
        if activation is None:
            raise AuthorityRefused(
                f"no activation evidence at the baseline ({result.activation_problem})")
        if activation.state != "active" or not activation.activated_at \
                or not activation.protected_decisions:
            raise AuthorityRefused("baseline memory is not active with a protection binding; "
                                   "run `mneme protect activate` and merge it first")
        event["activation"] = {
            "activated_at": activation.activated_at,
            "protected_decisions": list(activation.protected_decisions),
        }
    events.append(event)
    validate_declaration(document)
    atomic_write_json(path, document)
    return path, document, result

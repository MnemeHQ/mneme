"""
github_evidence.py — Authenticated GitHub Actions CI *claim* (ADR-024).

Authenticates a GitHub Actions workflow run and its evidence artifact through
the GitHub REST API, producing an authenticated CI **claim** — not a
verification. The distinction matters: GitHub proves the run, repository,
SHA, and artifact association, but the artifact *content* is still produced
by repository-controlled workflow code. A malicious or mistaken workflow can
upload ``{"outcome": "passed"}`` without executing the test. Therefore
authenticated artifact provenance is a stronger claim
(``authenticated_ci_claim``), never the ``verified`` state that Mneme maps to
Protected.

Trust chain (each step independently validated, fail-closed):

    authenticated GitHub API (Bearer token)
        → repository identity (owner/repo == audited remote)
        → workflow run (exists, belongs to that repository)
        → exact run head SHA (== audited repository HEAD)
        → run artifact (exists, not expired, named ``mneme-test-results``)
        → authenticated artifact download (signed blob, token NOT forwarded)
        → evidence document (parses as ``mneme.test-evidence/v1`` and its
          ``repository_sha`` equals the run head SHA)
        → authenticated CI claim

Only :func:`audit_with_github_claim` — the single supported public operation —
runs this chain and folds the resulting ``authenticated_ci_claim`` state into
an assessment report. It cannot reach ``verified``/Protected. The
``verified`` state is reserved for a future trusted producer (a
Mneme-controlled verifier, pinned and attested); no such producer exists in
M0.

Security boundary (honest): Python code in the same process can always
monkeypatch or private-call internals. The guarantee here is that Mneme's
SUPPORTED PUBLIC API (``mneme.enforcer.assess_protection`` /
``generate_protection_report`` and the ``mneme audit`` CLI) accepts no
trust-bearing parameter, so no supported caller can self-certify protection.

Default ``mneme audit`` never calls GitHub: this is a library/service entry
point, not part of the offline audit path.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mneme.evidence import CiEvidenceDocument, parse_ci_evidence_document

if TYPE_CHECKING:  # pragma: no cover - avoid import cycle at runtime
    from mneme.enforcer import ArchitectureProtectionReport

DEFAULT_GITHUB_API_URL = "https://api.github.com"
DEFAULT_ARTIFACT_NAME = "mneme-test-results"
DEFAULT_TIMEOUT_SECONDS = 15.0

_REDIRECT_STATUSES = (301, 302, 303, 307, 308)

# Remote URL forms we resolve to (owner, repo):
#   https://github.com/owner/repo(.git)
#   git@github.com:owner/repo(.git)
#   ssh://git@github.com/owner/repo(.git)
_REMOTE_RE = re.compile(
    r"(?:https?://github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"([^/]+)/([^/]+?)(?:\.git)?/?$"
)


class GitHubVerificationError(Exception):
    """Authenticated CI verification failed; no trusted evidence produced."""

    def __init__(self, message: str, status: int | None = None):
        self.status = status
        super().__init__(message)


@dataclass(frozen=True)
class _AuthenticatedCiClaim:
    """An authenticated CI claim, produced only by :func:`verify_github_run`.

    Private: it is not a trust root (the artifact content is
    repository-controlled), and it is never exposed as a parameter on any
    public assessment/report API.
    """

    repository: str  # "owner/repo", authenticated via the API
    run_id: int
    head_sha: str  # == audited repository HEAD, validated
    document: CiEvidenceDocument  # the authenticated, parsed evidence carrier


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect automatically; the caller handles it safely."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect)


def _http_open(
    url: str,
    headers: dict[str, str],
    timeout: float,
) -> tuple[int, dict[str, str], bytes]:
    """Perform ONE request with NO automatic redirect following.

    Returns ``(status, headers, body)``. This is the single HTTP seam so that
    the redirect behaviour — in particular, never forwarding the Authorization
    header to a different host — is deterministic and testable.
    """
    request = urllib.request.Request(url, headers=headers)
    try:
        with _NO_REDIRECT_OPENER.open(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            response_headers = {
                k.lower(): v for k, v in response.headers.items()
            }
            body = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        response_headers = {
            k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])
        }
        body = exc.read() if hasattr(exc, "read") else b""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise GitHubVerificationError(f"could not reach {url}: {exc}") from exc
    return status, response_headers, body


def _api_get_json(
    path: str,
    token: str,
    base_url: str,
    timeout: float,
) -> dict:
    """Authenticated GitHub REST API GET returning parsed JSON."""
    url = f"{base_url}{path}"
    status, _headers, body = _http_open(url, _auth_headers(token), timeout)
    if status >= 400:
        raise GitHubVerificationError(
            f"GitHub API {path} returned HTTP {status}", status=status
        )
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GitHubVerificationError(
            f"GitHub API {path} returned a non-JSON response (HTTP {status})"
        ) from exc
    if not isinstance(payload, dict):
        raise GitHubVerificationError(
            f"GitHub API {path} returned an unexpected payload (HTTP {status})"
        )
    return payload


def _download_artifact(
    path: str,
    token: str,
    base_url: str,
    timeout: float,
) -> bytes:
    """Authenticated artifact download with safe redirect handling.

    The first request carries the bearer token. If GitHub redirects to a
    signed blob URL (a different host), the follow-up request is issued
    WITHOUT any Authorization header, so the token is never forwarded to a
    non-API host.
    """
    url = f"{base_url}{path}"
    status, headers, body = _http_open(url, _auth_headers(token), timeout)
    if status in _REDIRECT_STATUSES:
        location = headers.get("location")
        if not location:
            raise GitHubVerificationError(
                f"artifact download {path} redirected without a Location header"
            )
        status, _headers, body = _http_open(location, {}, timeout)
        if status >= 400:
            raise GitHubVerificationError(
                f"artifact download returned HTTP {status}", status=status
            )
        return body
    if status >= 400:
        raise GitHubVerificationError(
            f"artifact download {path} returned HTTP {status}", status=status
        )
    return body


def _repo_head(repo_root: str | os.PathLike[str]) -> str:
    """Exact HEAD SHA of the audited repository via the git binary."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitHubVerificationError(
            f"could not determine the repository HEAD SHA: {exc}"
        ) from exc
    sha = (result.stdout or "").strip()
    if result.returncode != 0 or not sha:
        raise GitHubVerificationError("could not determine the repository HEAD SHA")
    return sha


def _resolve_remote_identity(repo_root: str | os.PathLike[str]) -> str:
    """Resolve the audited repository's canonical ``owner/repo`` identity.

    Reads ``git remote get-url origin`` (the git binary — never repository
    code) and parses the canonical owner/repo from the URL.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitHubVerificationError(
            f"could not determine the repository remote: {exc}"
        ) from exc
    if result.returncode != 0:
        raise GitHubVerificationError(
            "could not determine the repository remote (git remote get-url origin)"
        )
    remote = (result.stdout or "").strip()
    match = _REMOTE_RE.search(remote)
    if match is None:
        raise GitHubVerificationError(
            f"unrecognized origin remote URL {remote!r}; cannot prove repository identity"
        )
    owner, repo = match.group(1), match.group(2)
    if not owner or not repo:
        raise GitHubVerificationError(
            f"could not parse owner/repo from origin remote {remote!r}"
        )
    return f"{owner}/{repo}"


def _read_evidence_document(data: bytes) -> str:
    """Extract the evidence document text from the downloaded artifact zip."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [name for name in archive.namelist() if name.endswith(".json")]
    except (zipfile.BadZipFile, OSError) as exc:
        raise GitHubVerificationError(
            f"artifact is not a valid zip archive: {exc}"
        ) from exc
    if len(members) != 1:
        raise GitHubVerificationError(
            "artifact must contain exactly one evidence document (.json); "
            f"found {len(members)}"
        )
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return archive.read(members[0]).decode("utf-8")
    except (UnicodeDecodeError, zipfile.BadZipFile, KeyError, OSError) as exc:
        raise GitHubVerificationError(
            f"could not read the evidence document from the artifact: {exc}"
        ) from exc


def verify_github_run(
    repo_root: str | os.PathLike[str],
    run_id: int,
    audited_sha: str,
    token: str | None = None,
    owner: str | None = None,
    repo: str | None = None,
    artifact_name: str = DEFAULT_ARTIFACT_NAME,
    base_url: str = DEFAULT_GITHUB_API_URL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> _AuthenticatedCiClaim:
    """Authenticate a GitHub Actions run and return its evidence claim.

    Validates, in order, that:

    1. a GitHub token is available (``GITHUB_TOKEN`` / ``MNEME_GITHUB_TOKEN``
       or an explicit ``token``);
    2. the audited repository identity resolves from the origin remote (or is
       supplied as ``owner``/``repo``);
    3. the referenced workflow run exists and belongs to exactly that
       repository;
    4. the run's ``head_sha`` equals ``audited_sha`` exactly;
    5. an artifact named ``artifact_name`` exists for that run and is not
       expired;
    6. the artifact downloads and parses as ``mneme.test-evidence/v1``, and
       its ``repository_sha`` equals the run ``head_sha``.

    Any failure raises :class:`GitHubVerificationError`. The returned value is
    an authenticated CI **claim** — the artifact content is repository-
    controlled, so this is not execution proof and never reaches the
    ``verified`` state. Only this function constructs ``_AuthenticatedCiClaim``.
    """
    token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get(
        "MNEME_GITHUB_TOKEN"
    )
    if not token:
        raise GitHubVerificationError(
            "no GitHub token available (set GITHUB_TOKEN or MNEME_GITHUB_TOKEN)"
        )

    identity = f"{owner}/{repo}" if owner and repo else _resolve_remote_identity(
        repo_root
    )

    run = _api_get_json(
        f"/repos/{identity}/actions/runs/{run_id}", token, base_url, timeout
    )
    run_repository = run.get("head_repository") or {}
    run_full_name = run_repository.get("full_name") or ""
    if run_full_name and run_full_name != identity:
        raise GitHubVerificationError(
            f"run {run_id} belongs to {run_full_name!r}, not the audited "
            f"repository {identity!r}"
        )

    head_sha = run.get("head_sha")
    if not isinstance(head_sha, str) or not head_sha:
        raise GitHubVerificationError(f"run {run_id} reported no head SHA")
    if head_sha != audited_sha:
        raise GitHubVerificationError(
            f"run {run_id} head SHA {head_sha} does not match the audited "
            f"repository SHA {audited_sha}"
        )

    artifacts = _api_get_json(
        f"/repos/{identity}/actions/runs/{run_id}/artifacts",
        token,
        base_url,
        timeout,
    )
    artifact = next(
        (
            a for a in artifacts.get("artifacts", [])
            if isinstance(a, dict)
            and a.get("name") == artifact_name
            and not a.get("expired", False)
        ),
        None,
    )
    if artifact is None:
        raise GitHubVerificationError(
            f"run {run_id} has no non-expired artifact named {artifact_name!r}"
        )
    artifact_id = artifact.get("id")
    if not isinstance(artifact_id, int):
        raise GitHubVerificationError(
            f"run {run_id} artifact {artifact_name!r} has no usable id"
        )

    raw = _download_artifact(
        f"/repos/{identity}/actions/artifacts/{artifact_id}/zip",
        token,
        base_url,
        timeout,
    )
    document, reason = parse_ci_evidence_document(_read_evidence_document(raw))
    if document is None:
        raise GitHubVerificationError(
            f"artifact {artifact_name!r} is not valid test evidence: {reason}"
        )
    if document.repository_sha != head_sha:
        raise GitHubVerificationError(
            f"artifact evidence SHA {document.repository_sha} does not match "
            f"run head SHA {head_sha}"
        )

    return _AuthenticatedCiClaim(
        repository=identity,
        run_id=run_id,
        head_sha=head_sha,
        document=document,
    )


def audit_with_github_claim(
    decisions: list,
    repo_root: str | os.PathLike[str],
    run_id: int,
    token: str | None = None,
    owner: str | None = None,
    repo: str | None = None,
    artifact_name: str = DEFAULT_ARTIFACT_NAME,
    base_url: str = DEFAULT_GITHUB_API_URL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> "ArchitectureProtectionReport":
    """Authenticated assessment: run the GitHub chain and fold in the claim.

    This is the ONLY supported public operation that exercises the
    authenticated path. It authenticates the run (``verify_github_run``) and
    produces a report whose test-evidence entries reach at most the
    ``authenticated_ci_claim`` state — never ``verified``/Protected — because
    the artifact content is repository-controlled and Mneme has no trusted
    verification producer in M0.
    """
    audited_sha = _repo_head(repo_root)
    claim = verify_github_run(
        repo_root,
        run_id,
        audited_sha,
        token=token,
        owner=owner,
        repo=repo,
        artifact_name=artifact_name,
        base_url=base_url,
        timeout=timeout,
    )
    from mneme.enforcer import _build_report
    from mneme.evidence import _verify_test_evidence

    results = _verify_test_evidence(decisions, repo_root, None, claim)
    return _build_report(decisions, repo_root, results)


__all__ = [
    "GitHubVerificationError",
    "verify_github_run",
    "audit_with_github_claim",
]

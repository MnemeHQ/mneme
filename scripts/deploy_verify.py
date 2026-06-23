"""Pure helpers for post-deploy verification.

No side effects and no network, so they are safe to import in unit tests (unlike
deploy_site.py, which runs the deploy at import time). The deploy script wires
these into its retry/HTTP loop.
"""
from __future__ import annotations


def norm(b: bytes) -> bytes:
    """Normalize newlines and per-line trailing whitespace.

    Lets us compare a local file against the served response without benign
    encoding differences (CRLF vs LF, trailing spaces) registering as changes.
    """
    return b"\n".join(line.rstrip() for line in b.replace(b"\r\n", b"\n").split(b"\n")).strip()


def content_needle(local_bytes: bytes) -> bytes:
    """The uploaded page content we expect to find in the live response.

    Everything up to ``</body>``. Cloudflare appends its analytics beacon just
    before ``</body>``, so we match this prefix as a substring rather than
    comparing the whole body byte-for-byte (which would false-fail on the
    injected beacon).
    """
    return norm(local_bytes).split(b"</body>")[0]


def classify(status, body: bytes, needle: bytes):
    """Classify one verification fetch of a CHANGED url.

    Returns ``(verdict, detail)`` where verdict is one of:
      - ``"ok"``   -- 200 and the uploaded content is present
      - ``"fail"`` -- page missing (404/410) or a "stale 200" (served content
                      does not contain what we uploaded; an optimistic upload
                      never landed). A real failure: it must block the marker.
      - ``"warn"`` -- transient (5xx or other non-200). The caller retries and,
                      if it never clears, tolerates it rather than failing the
                      deploy, because it is infra noise rather than a bad deploy.
    """
    if status in (404, 410):
        return "fail", f"HTTP {status} (page missing)"
    if status != 200:
        return "warn", f"HTTP {status}"
    if needle and needle in norm(body):
        return "ok", ""
    return "fail", "stale 200 (served content does not match uploaded file)"

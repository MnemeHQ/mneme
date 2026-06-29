"""Pure helpers for post-deploy verification.

No side effects and no network, so they are safe to import in unit tests (unlike
deploy_site.py, which runs the deploy at import time). The deploy script wires
these into its retry/HTTP loop.
"""
from __future__ import annotations

import re

# Cloudflare "Email Address Obfuscation" (Scrape Shield, on by default) rewrites
# every mailto: link and visible email in the SERVED html: the address becomes a
# /cdn-cgi/l/email-protection href and/or a <span class="__cf_email__"> token,
# plus an injected email-decode script. The uploaded file still has the raw
# address, so a byte-substring needle false-fails every page that lists an email
# (contact / founder / privacy / pilot ...) even though the deploy is fresh.
# Neutralize both representations to a common placeholder so the comparison
# ignores Cloudflare's rewriting. Applied to both sides (it runs inside norm()),
# so it can never mask a genuinely stale page.
_CF_EMAIL_SCRIPT = re.compile(rb'<script[^>]*/email-decode\.min\.js[^>]*>.*?</script>', re.I | re.S)
_CF_EMAIL_SPAN = re.compile(rb'<span[^>]*\bclass=["\']__cf_email__["\'][^>]*>.*?</span>', re.I | re.S)
_CF_EMAIL_HREF = re.compile(rb'href=["\']/cdn-cgi/l/email-protection[^"\']*["\']', re.I)
_MAILTO = re.compile(rb'mailto:[^"\'>\s]+', re.I)
_RAW_EMAIL = re.compile(rb'[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}')


def _neutralize_email_obfuscation(b: bytes) -> bytes:
    b = _CF_EMAIL_SCRIPT.sub(b'', b)                 # Cloudflare email-decode script (served only)
    b = _CF_EMAIL_SPAN.sub(b'EMAIL', b)              # obfuscated visible token -> EMAIL
    b = _CF_EMAIL_HREF.sub(b'href="mailto:EMAIL"', b)  # obfuscated href -> canonical mailto
    b = _MAILTO.sub(b'mailto:EMAIL', b)              # raw mailto (uploaded side) -> canonical
    b = _RAW_EMAIL.sub(b'EMAIL', b)                  # any remaining raw address -> EMAIL
    return b


def norm(b: bytes) -> bytes:
    """Normalize newlines, per-line trailing whitespace, and Cloudflare email
    obfuscation.

    Lets us compare a local file against the served response without benign
    differences (CRLF vs LF, trailing spaces, Cloudflare's serve-time email
    rewriting) registering as changes.
    """
    b = _neutralize_email_obfuscation(b)
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

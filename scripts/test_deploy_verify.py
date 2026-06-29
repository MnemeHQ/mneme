#!/usr/bin/env python3
"""Tests for the pure post-deploy verification helpers (deploy_verify).

Runnable directly (`python scripts/test_deploy_verify.py`) and as pytest.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy_verify import norm, content_needle, classify  # noqa: E402

PAGE = b"<!DOCTYPE html>\n<html>\n<head><title>X</title></head>\n<body>\n<p>fresh content</p>\n</body>\n</html>\n"
# What Cloudflare actually serves: identical page with the analytics beacon
# injected just before </body>.
LIVE_OK = PAGE.replace(
    b"</body>",
    b'<script defer src="https://static.cloudflareinsights.com/beacon.min.js"></script>\n</body>',
)
LIVE_STALE = b"<!DOCTYPE html>\n<html>\n<head><title>X</title></head>\n<body>\n<p>OLD content</p>\n</body>\n</html>\n"


def test_norm_tolerates_crlf_and_trailing_ws():
    assert norm(b"a \r\nb\t\r\n") == norm(b"a\nb")


def test_needle_is_content_before_body():
    needle = content_needle(PAGE)
    assert b"fresh content" in needle
    assert b"</body>" not in needle


def test_fresh_page_with_cf_beacon_is_ok():
    needle = content_needle(PAGE)
    assert classify(200, LIVE_OK, needle) == ("ok", "")


def test_identical_page_is_ok():
    needle = content_needle(PAGE)
    assert classify(200, PAGE, needle)[0] == "ok"


def test_stale_200_is_fail():
    needle = content_needle(PAGE)
    verdict, detail = classify(200, LIVE_STALE, needle)
    assert verdict == "fail"
    assert "stale" in detail


# A page that lists an email — uploaded with a raw mailto + visible address.
PAGE_EMAIL = (
    b"<!DOCTYPE html>\n<html>\n<head><title>X</title></head>\n<body>\n"
    b'<p>fresh content. Contact <a href="mailto:theo@mnemehq.com">theo@mnemehq.com</a>.</p>\n'
    b"</body>\n</html>\n"
)
# What Cloudflare's Email Address Obfuscation actually serves: the mailto href
# becomes /cdn-cgi/l/email-protection, the visible address becomes a
# __cf_email__ span, and an email-decode script is injected before </body>.
LIVE_EMAIL_OBFUSCATED = (
    b"<!DOCTYPE html>\n<html>\n<head><title>X</title></head>\n<body>\n"
    b'<p>fresh content. Contact <a href="/cdn-cgi/l/email-protection#0d61646c...">'
    b'<span class="__cf_email__" data-cfemail="0d61646c...">[email&#160;protected]</span></a>.</p>\n'
    b'<script data-cfasync="false" src="/cdn-cgi/scripts/5c5dd728/cloudflare-static/email-decode.min.js"></script>\n'
    b'<script defer src="https://static.cloudflareinsights.com/beacon.min.js"></script>\n'
    b"</body>\n</html>\n"
)
# Same Cloudflare obfuscation, but the page body is genuinely OLD content.
LIVE_EMAIL_STALE = (
    b"<!DOCTYPE html>\n<html>\n<head><title>X</title></head>\n<body>\n"
    b'<p>OLD content. Contact <a href="/cdn-cgi/l/email-protection#0d61">'
    b'<span class="__cf_email__" data-cfemail="0d61">[email&#160;protected]</span></a>.</p>\n'
    b"</body>\n</html>\n"
)


def test_cloudflare_email_obfuscation_is_ok():
    # The fresh page is served with Cloudflare email obfuscation; it must still
    # verify OK (this is what was false-failing contact/founder/pilot/privacy).
    needle = content_needle(PAGE_EMAIL)
    assert classify(200, LIVE_EMAIL_OBFUSCATED, needle) == ("ok", "")


def test_email_obfuscation_does_not_mask_stale():
    # Email normalization must not let a genuinely stale page pass.
    needle = content_needle(PAGE_EMAIL)
    verdict, detail = classify(200, LIVE_EMAIL_STALE, needle)
    assert verdict == "fail"
    assert "stale" in detail


def test_404_is_fail():
    assert classify(404, b"", content_needle(PAGE))[0] == "fail"


def test_410_is_fail():
    assert classify(410, b"", content_needle(PAGE))[0] == "fail"


def test_5xx_is_warn_not_fail():
    # transient server error must not hard-fail the deploy
    assert classify(503, b"", content_needle(PAGE))[0] == "warn"
    assert classify(502, b"", content_needle(PAGE))[0] == "warn"


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run()

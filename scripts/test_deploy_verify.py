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

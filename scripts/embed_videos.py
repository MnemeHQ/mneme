#!/usr/bin/env python3
"""Idempotent backfill of click-to-load YouTube facades on insight/concept pages.

Mirrors the shared-asset pattern of ``site/assets/css/diagrams.css``: each page
gets a ``<link>`` to ``/assets/css/video.css``, a ``<script>`` to
``/assets/js/video.js``, and a facade ``<div>`` inserted mid-``.article-body``.
Extension pages (``is_core=False``) additionally get a ``VideoObject`` JSON-LD
block (the core 15 already carry one).

Every insertion helper no-ops when its marker is already present, so re-running
the script is safe.

Usage:
    python scripts/embed_videos.py [--dry-run] [--core-only]
"""
from __future__ import annotations

import argparse
import html as _html
import json
import re
from pathlib import Path

try:
    from scripts.video_map import VIDEO_MAP, EXTENSION_META
except ImportError:  # allow running as a plain script (python scripts/embed_videos.py)
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from video_map import VIDEO_MAP, EXTENSION_META

REPO_ROOT = Path(__file__).resolve().parent.parent

CSS_HREF = "/assets/css/video.css"
JS_SRC = "/assets/js/video.js"
CSS_LINK = '<link rel="stylesheet" href="%s">' % CSS_HREF
JS_SCRIPT = '<script src="%s" defer></script>' % JS_SRC
THUMB_URL = "https://i.ytimg.com/vi/%s/maxresdefault.jpg"


# --------------------------------------------------------------------------- #
# Head / body asset references
# --------------------------------------------------------------------------- #
def insert_head_link(head_html: str) -> str:
    """Insert the video.css <link> after the diagrams.css link if present,
    else immediately before </head>. No-op if already present."""
    if CSS_HREF in head_html:
        return head_html
    diagrams = '<link rel="stylesheet" href="/assets/css/diagrams.css">'
    if diagrams in head_html:
        return head_html.replace(diagrams, diagrams + "\n  " + CSS_LINK, 1)
    if "</head>" in head_html:
        return head_html.replace("</head>", "  " + CSS_LINK + "\n</head>", 1)
    return head_html + "\n" + CSS_LINK


def insert_body_script(html: str) -> str:
    """Insert the video.js <script> immediately before the real closing
    </body>. Targets the LAST </body> because real pages contain a literal
    "</body>" inside an HTML comment (the consent-banner sync marker) that must
    not be matched. No-op if already present."""
    if JS_SRC in html:
        return html
    idx = html.rfind("</body>")
    if idx != -1:
        return html[:idx] + JS_SCRIPT + "\n" + html[idx:]
    return html + "\n" + JS_SCRIPT


# --------------------------------------------------------------------------- #
# Facade block
# --------------------------------------------------------------------------- #
def facade_html(video_id: str, title: str) -> str:
    """Return the click-to-load facade <div> block. No YouTube network calls
    fire until the user activates it (handled in video.js)."""
    safe_title = _html.escape(title, quote=True)
    return (
        '<div class="yt-facade" data-video-id="%s" data-title="%s" role="button" '
        'tabindex="0" aria-label="Play video: %s">\n'
        '      <img class="yt-facade__thumb" src="%s" alt="" loading="lazy">\n'
        '      <span class="yt-facade__play" aria-hidden="true"></span>\n'
        '    </div>'
        % (video_id, safe_title, safe_title, THUMB_URL % video_id)
    )


# --------------------------------------------------------------------------- #
# Article body location + midpoint insertion
# --------------------------------------------------------------------------- #
def find_article_body(html: str):
    """Return (start, end) char offsets spanning the ``<div class="article-body">
    ... </div>`` block, where ``start`` is the offset of the opening ``<div`` and
    ``end`` is just past the matching ``</div>``. Returns None if not found.

    Matches the opening tag, then balances nested ``<div>``/``</div>`` to find the
    correct closing tag."""
    m = re.search(r'<div class="article-body"[^>]*>', html)
    if not m:
        return None
    start = m.start()
    i = m.end()
    depth = 1
    tag_re = re.compile(r'<(/?)div\b[^>]*>', re.IGNORECASE)
    for tm in tag_re.finditer(html, i):
        if tm.group(1):  # closing </div>
            depth -= 1
            if depth == 0:
                return (start, tm.end())
        else:  # opening <div ...>
            depth += 1
    return None


def insert_facade_midpoint(body_html: str, facade: str) -> str:
    """Insert ``facade`` immediately before the midpoint top-level ``<h2>`` in
    ``body_html``. If fewer than 2 ``<h2>`` are present, insert after the first
    ``</p>``. No-op if a ``yt-facade`` is already present."""
    if "yt-facade" in body_html:
        return body_html

    h2s = [m.start() for m in re.finditer(r'<h2\b', body_html, re.IGNORECASE)]
    if len(h2s) >= 2:
        idx = h2s[len(h2s) // 2]
        return body_html[:idx] + facade + "\n\n    " + body_html[idx:]

    # Fallback: after the first </p>.
    pm = re.search(r'</p>', body_html, re.IGNORECASE)
    if pm:
        cut = pm.end()
        return body_html[:cut] + "\n\n    " + facade + body_html[cut:]

    # No <h2> and no </p>: append at end of body content.
    return body_html + "\n    " + facade


def replace_video_wrap(html: str, facade: str):
    """If the page already carries a native ``<div class="video-wrap"> ...
    </div>`` iframe embed, replace that whole block with the click-to-load
    ``facade`` (in place, preserving any surrounding intro copy). Returns
    (new_html, replaced). No-op (replaced=False) if no .video-wrap is present or
    a yt-facade already exists."""
    if "yt-facade" in html:
        return html, False
    # Hand-written embeds have used both wrapper classes. Matching only
    # .video-wrap silently skipped the .video-embed pages, leaving a raw
    # auto-loading iframe in place.
    m = re.search(r'<div class="(?:video-wrap|video-embed)"[^>]*>', html)
    if not m:
        return html, False
    start = m.start()
    i = m.end()
    depth = 1
    for tm in re.compile(r'<(/?)div\b[^>]*>', re.IGNORECASE).finditer(html, i):
        if tm.group(1):
            depth -= 1
            if depth == 0:
                end = tm.end()
                return html[:start] + facade + html[end:], True
        else:
            depth += 1
    return html, False


# --------------------------------------------------------------------------- #
# VideoObject schema (extension pages only)
# --------------------------------------------------------------------------- #
def video_object_schema(video_id: str, meta: dict) -> str:
    """Return a ``<script type="application/ld+json" data-video-schema="...">``
    block matching the shape of the existing 15 core schemas. ``duration`` is
    emitted only when present and truthy (the YouTube MCP does not expose it)."""
    schema = {
        "@context": "https://schema.org",
        "@type": "VideoObject",
        "name": meta["name"],
        "description": meta["description"],
        "thumbnailUrl": THUMB_URL % video_id,
        "uploadDate": meta["uploadDate"],
    }
    if meta.get("duration"):
        schema["duration"] = meta["duration"]
    schema["embedUrl"] = "https://www.youtube.com/embed/%s" % video_id
    schema["contentUrl"] = "https://www.youtube.com/watch?v=%s" % video_id
    schema["publisher"] = {
        "@type": "Organization",
        "name": "Mneme HQ",
        "logo": {"@type": "ImageObject", "url": "https://mnemehq.com/og.png"},
    }
    key = re.sub(r"[^a-z0-9]+", "_", video_id.lower()).strip("_")
    body = json.dumps(schema, indent=2, ensure_ascii=False)
    return (
        '<script type="application/ld+json" data-video-schema="%s">\n%s\n</script>'
        % (key, body)
    )


def insert_video_schema(html: str, video_id: str, meta: dict) -> str:
    """Insert the VideoObject JSON-LD block just before </head>.
    No-op if a data-video-schema block is already present."""
    if "data-video-schema" in html:
        return html
    block = video_object_schema(video_id, meta)
    if "</head>" in html:
        return html.replace("</head>", block + "\n</head>", 1)
    return html + "\n" + block


# --------------------------------------------------------------------------- #
# Page processing
# --------------------------------------------------------------------------- #
def _page_title(html: str, fallback: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        title = _html.unescape(m.group(1)).strip()
        title = re.split(r"\s+[—\-|]\s+Mneme HQ", title)[0].strip()
        if title:
            return title
    return fallback


def process_page(path: Path, video_id: str, is_core: bool, meta: dict | None) -> dict:
    """Apply head link + facade + body script to the page at ``path``. For
    extension pages (``is_core=False``), also insert the VideoObject schema.
    Idempotent: re-running makes no further change. Returns a per-page summary.
    """
    original = path.read_text(encoding="utf-8")
    html = original

    title = _page_title(html, video_id)
    html = insert_head_link(html)

    facade = facade_html(video_id, title)
    facade_added = False

    # If the page already has a native auto-loading .video-wrap embed, replace it
    # in place with the click-to-load facade (privacy upgrade + avoids a duplicate
    # player). Otherwise insert the facade at the article-body midpoint.
    html, replaced = replace_video_wrap(html, facade)
    if replaced:
        facade_added = True
    else:
        span = find_article_body(html)
        if span and "yt-facade" not in html:
            start, end = span
            body = html[start:end]
            new_body = insert_facade_midpoint(body, facade)
            if new_body != body:
                html = html[:start] + new_body + html[end:]
                facade_added = True

    html = insert_body_script(html)

    schema_added = False
    if not is_core:
        if meta is None:
            raise ValueError("extension page %s missing EXTENSION_META" % path)
        before = html
        html = insert_video_schema(html, video_id, meta)
        schema_added = html != before

    changed = html != original
    return {
        "path": path,
        "video_id": video_id,
        "is_core": is_core,
        "exists": True,
        "changed": changed,
        "facade_added": facade_added,
        "schema_added": schema_added,
        "_new_html": html,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change without writing files")
    parser.add_argument("--core-only", action="store_true",
                        help="process only the core (is_core=True) pages")
    args = parser.parse_args(argv)

    core_n = sum(1 for _id, core in VIDEO_MAP.values() if core)
    ext_n = sum(1 for _id, core in VIDEO_MAP.values() if not core)
    print("VIDEO_MAP: %d pages (%d core, %d extension)" % (len(VIDEO_MAP), core_n, ext_n))
    if args.dry_run:
        print("[dry-run] no files will be written")
    if args.core_only:
        print("[core-only] extension pages skipped")

    written = 0
    skipped_missing = 0
    unchanged = 0
    for slug, (video_id, is_core) in VIDEO_MAP.items():
        if args.core_only and not is_core:
            continue
        path = REPO_ROOT / "site" / slug / "index.html"
        if not path.exists():
            print("  MISSING  %s (%s)" % (slug, path))
            skipped_missing += 1
            continue
        meta = None if is_core else EXTENSION_META.get(video_id)
        result = process_page(path, video_id, is_core, meta)
        tag = "core" if is_core else "ext "
        flags = []
        if result["facade_added"]:
            flags.append("facade")
        if result["schema_added"]:
            flags.append("schema")
        if not result["changed"]:
            unchanged += 1
            print("  ok       [%s] %s (already current)" % (tag, slug))
            continue
        if args.dry_run:
            print("  would    [%s] %s -> %s" % (tag, slug, "+".join(flags) or "head/body"))
        else:
            path.write_text(result["_new_html"], encoding="utf-8")
            written += 1
            print("  WROTE    [%s] %s -> %s" % (tag, slug, "+".join(flags) or "head/body"))

    print("---")
    print("written=%d unchanged=%d missing=%d%s"
          % (written, unchanged, skipped_missing, " (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

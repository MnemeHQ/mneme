# tests/test_embed_videos.py
from scripts.embed_videos import (
    insert_head_link, insert_body_script, facade_html, insert_facade_midpoint,
    replace_video_wrap,
)

HEAD = '<head>\n<link rel="stylesheet" href="/assets/css/diagrams.css">\n</head>'
BODY_END = '<script><!-- nav-active --></script>\n</body>'


def test_insert_head_link_is_idempotent():
    once = insert_head_link(HEAD)
    twice = insert_head_link(once)
    assert once.count("/assets/css/video.css") == 1
    assert once == twice


def test_insert_body_script_is_idempotent():
    once = insert_body_script(BODY_END)
    twice = insert_body_script(once)
    assert once.count("/assets/js/video.js") == 1
    assert once == twice


def test_insert_body_script_targets_real_body_not_comment():
    # Real pages contain a literal </body> inside the consent-banner comment
    # BEFORE the real closing tag. The script must land before the real </body>,
    # not get buried in the comment (regression: it was inserted into the comment).
    html = (
        "<body>\n"
        "<!-- marketing-body: synced before </body> by sync_shared.py. -->\n"
        "<div>content</div>\n"
        "</body>"
    )
    out = insert_body_script(html)
    assert out.count("/assets/js/video.js") == 1
    # the script tag must sit AFTER the comment's </body>, immediately before the real one
    comment_close = out.index("by sync_shared.py.")
    script_at = out.index("/assets/js/video.js")
    assert script_at > comment_close
    # and it must be immediately before the final </body>
    assert out.rstrip().endswith("</body>")
    assert out.index("/assets/js/video.js") > out.rindex("<!--")
    # idempotent
    assert insert_body_script(out) == out


def test_facade_html_contains_id_and_nocookie_free_thumb():
    html = facade_html("ABC123", "My Title")
    assert 'data-video-id="ABC123"' in html
    assert "i.ytimg.com/vi/ABC123/maxresdefault.jpg" in html
    assert "My Title" in html


def test_replace_video_wrap_swaps_native_embed_in_place():
    html = (
        '<p>intro</p>\n'
        '    <div class="video-wrap">\n'
        '      <iframe src="https://www.youtube-nocookie.com/embed/ABC"></iframe>\n'
        '    </div>\n'
        '    <h2>next</h2>'
    )
    facade = '<div class="yt-facade" data-video-id="ABC"></div>'
    out, replaced = replace_video_wrap(html, facade)
    assert replaced is True
    assert "video-wrap" not in out
    assert "<iframe" not in out          # native auto-loading embed gone
    assert out.count("yt-facade") == 1
    assert "<p>intro</p>" in out and "<h2>next</h2>" in out  # surrounding copy kept
    # idempotent: facade already present -> no-op
    out2, replaced2 = replace_video_wrap(out, facade)
    assert replaced2 is False and out2 == out


def test_replace_video_wrap_noop_without_native_embed():
    html = '<p>no embed here</p>'
    out, replaced = replace_video_wrap(html, '<div class="yt-facade"></div>')
    assert replaced is False and out == html


def test_insert_facade_midpoint_picks_middle_h2():
    body = ('<div class="article-body">'
            '<p>lede</p>'
            '<h2>One</h2><p>a</p>'
            '<h2>Two</h2><p>b</p>'
            '<h2>Three</h2><p>c</p>'
            '</div>')
    out = insert_facade_midpoint(body, '<div class="yt-facade"></div>')
    # facade inserted immediately before the midpoint <h2> (the 2nd of 3)
    assert out.index('yt-facade') < out.index('<h2>Two')
    assert out.count('yt-facade') == 1
    # idempotent
    assert insert_facade_midpoint(out, '<div class="yt-facade"></div>') == out

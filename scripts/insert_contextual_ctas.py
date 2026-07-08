#!/usr/bin/env python3
"""
Insert a topic-matched contextual CTA ("Operationalize this") into every
insight article, routing readers from a cited essay to the conversion page
that best fits its subject (a /compare/ competitor page or a /demo/ scenario),
with /pilot/ as a consistent secondary.

Rationale: cited insights do top-funnel work. A generic footer CTA does not turn
that citation visibility into evaluation traffic; a topic-matched contextual CTA
does. See docs/site/insight-publishing-contract.md and check_insights.py
(FUNNEL_RE now counts /compare/).

Design:
  * Article set mirrors check_insights.article_slugs(): every site/insights/<slug>/
    index.html except the hub, all/, and topics/.
  * An ordered rule table classifies each article by slug tokens + title + body.
    First match wins. Named-tool rules are most specific and come first; thematic
    rules next; a /demo/ default last so every article gets a conversion target.
  * OVERRIDES pins individual slugs the rules would misfire on.
  * The callout is inserted before the first of a fallback anchor chain
    (FAQ section -> related panel -> article footer -> </article>), so it lands
    right after the prose on every template variant.
  * Idempotent (skips if the marker is already present) and CRLF-preserving.

Usage:
  python scripts/insert_contextual_ctas.py            # report / dry-run (no writes)
  python scripts/insert_contextual_ctas.py --write     # apply
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSIGHTS_DIR = REPO_ROOT / "site" / "insights"
NON_ARTICLE_DIRS = {"all", "topics"}

# Marker that makes the insertion idempotent and greppable by check_insights.
MARKER = 'data-mneme-cta="context"'

# Pages carry per-page inline <style> (no shared stylesheet yet), so the CTA
# styles are injected into each. Literal hex, not var(--teal), so it renders
# even on any older page whose :root omits that variable. Teal-forward so it
# reads distinct from the lime (--accent) footer CTA and nav button.
CSS_MARKER = "/* mneme:context-cta-css */"
CSS_LINES = [
    CSS_MARKER,
    ".context-cta { margin: 3rem 0 0; background: rgba(139,224,200,0.06); border: 1px solid #8be0c8; border-radius: 12px; padding: 1.5rem 1.75rem; }",
    ".context-cta-eyebrow { font-family: 'DM Mono', monospace; font-size: 0.66rem; letter-spacing: 0.12em; text-transform: uppercase; color: #8be0c8; margin-bottom: 0.6rem; }",
    ".context-cta-copy { font-size: 0.92rem; color: #e8e8ec; line-height: 1.65; margin: 0 0 1.15rem; }",
    ".context-cta-actions { display: flex; flex-wrap: wrap; gap: 0.75rem 1.5rem; align-items: center; }",
    ".context-cta-primary { display: inline-block; background: #8be0c8; color: #0c0c0d; padding: 0.55rem 1.25rem; border-radius: 8px; font-family: 'DM Mono', monospace; font-size: 0.82rem; font-weight: 600; text-decoration: none; transition: background 0.15s; }",
    ".context-cta-primary:hover { background: #6fcbb0; }",
    ".context-cta-secondary { color: #8be0c8; font-family: 'DM Mono', monospace; font-size: 0.82rem; text-decoration: none; border-bottom: 1px solid rgba(139,224,200,0.4); transition: border-color 0.15s; }",
    ".context-cta-secondary:hover { border-bottom-color: #8be0c8; }",
]

# Fallback anchor chain: insert the callout before the FIRST of these that
# appears in the document. Ordered earliest-in-body first so the CTA lands
# right after the article prose wherever possible.
ANCHORS = [
    '<section class="article-faq"',
    '<aside class="related-panel"',
    '<footer class="article-footer">',
    "</article>",
]

# --- Conversion targets -----------------------------------------------------
# Each rule: (keywords, primary_href, primary_label, copy).
# `keywords` match against slug tokens (split on '-') OR the lowercased title.
# Order matters: first match wins.
RULES: list[tuple[list[str], str, str, str]] = [
    # -- Named tools / competitors (most specific) --
    (["cursor"], "/compare/cursor-rules/",
     "Compare Mneme with Cursor Rules",
     "Cursor Rules steer generation; they do not enforce it. See where architectural governance picks up."),
    (["claude.md", "claudemd"], "/compare/claude-md/",
     "Compare Mneme with CLAUDE.md",
     "A CLAUDE.md file tells an agent the rules. It cannot stop the agent from breaking them. See the difference."),
    (["copilot"], "/compare/github-copilot/",
     "Compare Mneme with GitHub Copilot",
     "Copilot generates and reviews; it does not hold an architectural boundary. See the comparison."),
    (["windsurf"], "/compare/windsurf/",
     "Compare Mneme with Windsurf",
     "See where an agentic IDE ends and architectural enforcement begins."),
    (["devin"], "/compare/devin-vs-architectural-governance/",
     "Compare Mneme with Devin",
     "An autonomous engineer still needs an enforced architecture to build within. See the comparison."),
    (["antigravity"], "/compare/google-antigravity-vs-mneme/",
     "Compare Mneme with Google Antigravity",
     "Antigravity coordinates agents; it does not govern what they are allowed to ship. See the comparison."),
    (["aider"], "/compare/aider/",
     "Compare Mneme with Aider",
     "See where a pair-programming agent ends and deterministic governance begins."),
    (["cody", "sourcegraph"], "/compare/sourcegraph-cody/",
     "Compare Mneme with Sourcegraph Cody",
     "Code search and context are not enforcement. See where governance sits above them."),
    (["continue.dev", "continuedev"], "/compare/continue-dev/",
     "Compare Mneme with Continue.dev",
     "See where a customizable assistant ends and architectural enforcement begins."),
    (["coderabbit"], "/compare/coderabbit/",
     "Compare Mneme with CodeRabbit",
     "AI code review surfaces issues; it does not enforce architecture deterministically. See the comparison."),
    # -- Thematic (tool-agnostic) --
    (["review", "peer-review"], "/compare/coderabbit/",
     "Compare Mneme with AI code review",
     "Review finds problems after the fact. Governance rejects the violating change before it lands. See the comparison."),
    (["rag"], "/compare/rag-vs-governance/",
     "See RAG vs governance",
     "Retrieval gives an agent the decision. It does not make the agent comply. See the comparison."),
    (["memory"], "/compare/claude-code-memory/",
     "See memory vs governance",
     "Memory helps an agent recall a decision; governance makes every agent obey it. See the comparison."),
    (["multi-agent", "coordination", "fleet", "orchestration", "swarm"],
     "/demo/multi-agent-governance/",
     "See the multi-agent governance demo",
     "Watch one enforced decision hold across a fleet of agents working in parallel."),
    (["drift"], "/demo/architectural-drift/",
     "See the architectural-drift demo",
     "Watch Mneme catch architectural drift before the change merges."),
    (["dependency", "dependencies"], "/demo/dependency-policy/",
     "See the dependency-policy demo",
     "Watch a dependency rule enforced deterministically against AI-generated code."),
    (["repository", "repositories"], "/demo/repository-pattern/",
     "See the repository-pattern demo",
     "Watch an architectural pattern enforced against a violating change."),
    (["storage", "database", "persistence"], "/demo/storage-decision/",
     "See the storage-decision demo",
     "Watch a storage decision held as an executable constraint."),
    (["adr", "adrs", "spec-kit", "spec-driven", "specification"], "/demo/adr-compiler/",
     "See decisions compiled into checks",
     "Watch an architectural decision record compiled into an enforceable check."),
    (["sdk", "python-agent", "agent-sdk"], "/demo/agent-sdk-governance/",
     "See the agent-SDK governance demo",
     "Watch governance wrap an agent built on an SDK, not just a chat IDE."),
]

# Default when no rule matches: the demo hub.
DEFAULT = (
    "/demo/",
    "See the live demo",
    "See Mneme enforce an architectural decision against AI-generated code, deterministically, in the live demo.",
)

# Per-slug pins for articles the rules would misfire on.
OVERRIDES: dict[str, tuple[str, str, str]] = {
    # This essay *is* the Cursor comparison; do not point it back at itself.
    "mneme-vs-cursor-rules": (
        "/demo/",
        "See the live demo",
        "See the enforcement layer this comparison describes, running against a real violating change.",
    ),
}

SECONDARY_HREF = "/pilot/"
SECONDARY_LABEL = "Request a pilot"


def article_slugs() -> list[str]:
    out = []
    for child in sorted(INSIGHTS_DIR.iterdir()):
        if not child.is_dir() or child.name in NON_ARTICLE_DIRS:
            continue
        if (child / "index.html").exists():
            out.append(child.name)
    return out


def title_of(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    return (m.group(1) if m else "").lower()


def kw_matches(kw: str, tokens: set[str], slug: str, title: str) -> bool:
    """Precise keyword match. Plain words match only as a slug token or a
    whole word in the title (word boundaries) -- never as a loose substring,
    which would let 'for agentic' -> 'foragentic' spuriously contain 'rag'.
    Dotted product names (claude.md) match their compact form; hyphenated
    phrases (multi-agent) match the slug/title directly."""
    kw_l = kw.lower()
    if "." in kw_l:  # dotted product name: claude.md, continue.dev
        compact = kw_l.replace(".", "")
        return compact in slug.replace("-", "") or compact in title.replace(".", "")
    if "-" in kw_l:  # hyphenated phrase: multi-agent, peer-review
        return kw_l in slug or kw_l in title
    return kw_l in tokens or re.search(rf"\b{re.escape(kw_l)}\b", title) is not None


def classify(slug: str, html: str) -> tuple[str, str, str]:
    """Return (primary_href, primary_label, copy) for an article."""
    if slug in OVERRIDES:
        return OVERRIDES[slug]
    tokens = set(slug.split("-"))
    title = title_of(html)
    for keywords, href, label, copy in RULES:
        if any(kw_matches(kw, tokens, slug, title) for kw in keywords):
            return href, label, copy
    return DEFAULT


def build_block(indent: str, nl: str, primary_href: str, primary_label: str,
                copy: str) -> str:
    ind = indent
    lines = [
        f'{ind}<aside class="context-cta" {MARKER} aria-label="Operationalize this">',
        f'{ind}  <div class="context-cta-eyebrow">Operationalize this</div>',
        f'{ind}  <p class="context-cta-copy">{copy}</p>',
        f'{ind}  <div class="context-cta-actions">',
        f'{ind}    <a href="{primary_href}" class="context-cta-primary">{primary_label} &rarr;</a>',
        f'{ind}    <a href="{SECONDARY_HREF}" class="context-cta-secondary">{SECONDARY_LABEL} &rarr;</a>',
        f"{ind}  </div>",
        f"{ind}</aside>",
    ]
    return nl.join(lines) + nl


def find_anchor(html: str) -> tuple[int, str] | None:
    """Return (index, indent) of the earliest anchor in ANCHORS, or None."""
    best = None
    for anchor in ANCHORS:
        idx = html.find(anchor)
        if idx == -1:
            continue
        if best is None or idx < best[0]:
            line_start = html.rfind("\n", 0, idx) + 1
            indent = html[line_start:idx]
            if indent.strip():  # anchor not at line start; fall back to no indent
                indent = ""
            best = (line_start, indent)
    return best


def process(slug: str, write: bool) -> dict:
    path = INSIGHTS_DIR / slug / "index.html"
    # newline='' preserves existing CRLF/LF bytes in the returned string.
    with open(path, "r", encoding="utf-8", newline="") as fh:
        html = fh.read()
    nl = "\r\n" if "\r\n" in html else "\n"

    if MARKER in html:
        return {"slug": slug, "status": "skip-exists"}

    primary_href, primary_label, copy = classify(slug, html)
    anchor = find_anchor(html)
    if anchor is None:
        return {"slug": slug, "status": "NO-ANCHOR", "primary": primary_href}

    # 1. Inject the CTA styles into the page's inline <style>, as its own
    #    4-space-indented lines just before the (2-space-indented) </style>.
    style_close = html.find("</style>")
    if style_close == -1:
        return {"slug": slug, "status": "NO-STYLE", "primary": primary_href}
    line_start = html.rfind("\n", 0, style_close) + 1
    css = "".join(f"    {line}{nl}" for line in CSS_LINES)
    html = html[:line_start] + css + html[line_start:]

    # 2. Insert the CTA markup before the earliest body anchor. Re-locate the
    #    anchor: the CSS insertion above shifted every downstream offset.
    anchor = find_anchor(html)
    insert_at, indent = anchor
    block = build_block(indent, nl, primary_href, primary_label, copy) + nl
    new_html = html[:insert_at] + block + html[insert_at:]

    if write:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_html)

    return {"slug": slug, "status": "written" if write else "would-write",
            "primary": primary_href}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="apply changes (default: report only)")
    args = ap.parse_args()

    slugs = article_slugs()
    results = [process(s, args.write) for s in slugs]

    by_status: dict[str, list[dict]] = {}
    for r in results:
        by_status.setdefault(r["status"], []).append(r)

    # Full mapping table (sorted by primary target, then slug).
    mapped = [r for r in results if "primary" in r]
    print(f"\n=== Contextual CTA mapping ({len(mapped)} articles) ===")
    for r in sorted(mapped, key=lambda r: (r["primary"], r["slug"])):
        print(f"  {r['primary']:<45} {r['slug']}")

    # Distribution.
    dist: dict[str, int] = {}
    for r in mapped:
        dist[r["primary"]] = dist.get(r["primary"], 0) + 1
    print("\n=== Target distribution ===")
    for href, n in sorted(dist.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {n:>3}  {href}")

    print("\n=== Status ===")
    for status in sorted(by_status):
        print(f"  {status:<14} {len(by_status[status])}")
    no_anchor = by_status.get("NO-ANCHOR", [])
    if no_anchor:
        print("\n!!! NO ANCHOR (needs manual handling):")
        for r in no_anchor:
            print(f"    {r['slug']}")
        return 1

    if not args.write:
        print("\n(report only -- rerun with --write to apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

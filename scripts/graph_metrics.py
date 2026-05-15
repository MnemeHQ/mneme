#!/usr/bin/env python3
"""Mneme HQ knowledge-graph metrics analyzer.

Walks the rendered ``site/`` tree, extracts every internal link, and emits a
report describing how the concept layer connects to the rest of the site.
The report is the input to Phase 1 of the knowledge-graph roadmap and is
re-run after each subsequent phase to detect drift in the graph itself.

Usage::

    python scripts/graph_metrics.py                    # JSON to stdout
    python scripts/graph_metrics.py --format summary   # human-readable markdown
    python scripts/graph_metrics.py --out report.json  # write JSON to file
    python scripts/graph_metrics.py --site path/to/site

Per concept node the report records:

* inbound link counts split by source category (concept / insight / demo /
  compare / benchmark / integration / use-case / works-with)
* outbound link counts split by target category
* ``is_orphan`` — true if no other page links here
* ``is_implementation_orphan`` — true if no demo / compare / benchmark links here
* ``concept_depth`` — shortest hop count from the concepts hub

The script has no dependencies beyond the Python standard library so it can
run inside CI on any machine that builds the site.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Iterable
from urllib.parse import urldefrag

SITE_ROOT = Path(__file__).resolve().parent.parent / "site"

HREF_RE = re.compile(r'href="([^"]*)"')


def find_html_files(root: Path) -> list[Path]:
    return sorted(root.rglob("index.html"))


def page_url(path: Path, root: Path) -> str:
    """Convert ``site/concepts/x/index.html`` to ``/concepts/x/``."""
    rel = path.relative_to(root).parent
    if str(rel) == ".":
        return "/"
    return "/" + str(rel).replace("\\", "/") + "/"


def extract_links(html: str) -> set[str]:
    """Return the set of internal path-only hrefs found in ``html``.

    External URLs, anchors, and ``mailto:`` / ``javascript:`` schemes are
    excluded. Trailing-slash normalization is applied so ``/concepts/x``
    and ``/concepts/x/`` collapse to one node.
    """
    links: set[str] = set()
    for m in HREF_RE.finditer(html):
        href = m.group(1).strip()
        if not href:
            continue
        if href.startswith(("http://", "https://", "mailto:", "javascript:", "#")):
            continue
        href = urldefrag(href)[0]
        if not href.startswith("/"):
            continue
        # Trailing-slash normalization: directory-style URL gets a slash.
        last = href.rsplit("/", 1)[-1]
        if last and "." not in last:
            href = href + "/"
        links.add(href)
    return links


def categorize(url: str) -> str | None:
    """Bucket a URL into a graph category."""
    if url.startswith("/concepts/") and url != "/concepts/":
        return "concept"
    if url.startswith("/insights/") and url != "/insights/":
        return "insight"
    if url.startswith("/demo/") and url != "/demo/":
        return "demo"
    if url.startswith("/compare/") and url != "/compare/":
        return "compare"
    if url == "/benchmark/":
        return "benchmark"
    if url.startswith("/integrations/") and url != "/integrations/":
        return "integration"
    if url.startswith("/use-cases/") and url != "/use-cases/":
        return "use-case"
    if url.startswith("/works-with/") and url != "/works-with/":
        return "works-with"
    return None


def shortest_depth_from(root: str, edges: dict[str, Iterable[str]]) -> dict[str, int]:
    """BFS shortest hop count from ``root`` to every reachable node."""
    depth = {root: 0}
    q: deque[str] = deque([root])
    while q:
        node = q.popleft()
        for target in edges.get(node, ()):
            if target not in depth:
                depth[target] = depth[node] + 1
                q.append(target)
    return depth


def build_report(site_root: Path) -> dict:
    files = find_html_files(site_root)
    if not files:
        raise SystemExit(f"No HTML files found under {site_root}")

    graph: dict[str, set[str]] = {}
    for f in files:
        url = page_url(f, site_root)
        graph[url] = extract_links(f.read_text())

    inbound: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for source, links in graph.items():
        source_cat = categorize(source) or "other"
        for target in links:
            if target not in graph:
                continue
            inbound[target][source_cat] += 1
            inbound[target]["_total"] += 1

    concepts = sorted(u for u in graph if categorize(u) == "concept")
    depth = shortest_depth_from("/concepts/", graph)

    concept_metrics: dict[str, dict] = {}
    for c in concepts:
        outgoing = graph[c]
        out_concepts = sum(1 for u in outgoing if categorize(u) == "concept")
        out_insights = sum(1 for u in outgoing if categorize(u) == "insight")
        out_demos = sum(1 for u in outgoing if categorize(u) == "demo")

        in_concept = inbound[c].get("concept", 0)
        in_insight = inbound[c].get("insight", 0)
        in_demo = inbound[c].get("demo", 0)
        in_compare = inbound[c].get("compare", 0)
        in_bench = inbound[c].get("benchmark", 0)
        in_impl = in_demo + in_compare + in_bench
        in_total = inbound[c].get("_total", 0)

        concept_metrics[c] = {
            "inbound_total": in_total,
            "inbound_from_concepts": in_concept,
            "inbound_from_insights": in_insight,
            "inbound_from_implementation": in_impl,
            "inbound_from_demos": in_demo,
            "inbound_from_compare": in_compare,
            "inbound_from_benchmark": in_bench,
            "outbound_to_concepts": out_concepts,
            "outbound_to_insights": out_insights,
            "outbound_to_demos": out_demos,
            "is_orphan": in_total == 0,
            "is_implementation_orphan": in_impl == 0,
            "concept_depth": depth.get(c),
        }

    orphans = [c for c in concepts if concept_metrics[c]["is_orphan"]]
    impl_orphans = [c for c in concepts if concept_metrics[c]["is_implementation_orphan"]]

    return {
        "site_root": str(site_root),
        "total_pages": len(graph),
        "concept_count": len(concepts),
        "summary": {
            "orphan_count": len(orphans),
            "orphans": orphans,
            "implementation_orphan_count": len(impl_orphans),
            "implementation_orphans": impl_orphans,
        },
        "concepts": concept_metrics,
    }


def render_summary(report: dict) -> str:
    lines: list[str] = []
    lines.append(
        f"# Graph metrics — {report['concept_count']} concepts across "
        f"{report['total_pages']} pages\n"
    )

    orphans = report["summary"]["orphans"]
    impl_orphans = report["summary"]["implementation_orphans"]

    lines.append(f"**Orphans** (zero inbound from any page): {len(orphans)}")
    for o in orphans:
        lines.append(f"  - {o}")
    if not orphans:
        lines.append("  - _(none)_")
    lines.append("")

    lines.append(
        f"**Implementation-orphans** (no demo / compare / benchmark links in): "
        f"{len(impl_orphans)}"
    )
    for o in impl_orphans:
        lines.append(f"  - {o}")
    if not impl_orphans:
        lines.append("  - _(none)_")
    lines.append("")

    lines.append("## Per-concept link counts")
    lines.append("")
    lines.append(
        "| Concept | In total | In concepts | In insights | In demos | "
        "In compare | In bench | Out concepts | Out insights | Out demos | Depth |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    for c, m in sorted(report["concepts"].items()):
        slug = c.rstrip("/").split("/")[-1]
        lines.append(
            f"| {slug} | {m['inbound_total']} | {m['inbound_from_concepts']} "
            f"| {m['inbound_from_insights']} | {m['inbound_from_demos']} "
            f"| {m['inbound_from_compare']} | {m['inbound_from_benchmark']} "
            f"| {m['outbound_to_concepts']} | {m['outbound_to_insights']} "
            f"| {m['outbound_to_demos']} | {m['concept_depth']} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Mneme HQ knowledge-graph metrics")
    p.add_argument("--site", type=Path, default=SITE_ROOT, help="Root of site/")
    p.add_argument(
        "--format",
        choices=["json", "summary"],
        default="json",
        help="Output format (default: json)",
    )
    p.add_argument("--out", type=Path, help="Write report to file (else stdout)")
    args = p.parse_args(argv)

    report = build_report(args.site)
    out = (
        json.dumps(report, indent=2, sort_keys=True)
        if args.format == "json"
        else render_summary(report)
    )

    if args.out:
        args.out.write_text(out)
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

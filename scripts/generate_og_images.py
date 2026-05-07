#!/usr/bin/env python3
"""
Generate OG images from HTML templates using Playwright.
Each og-<slug>.html in site/ is rendered at 1200x630 and saved as og.png
co-located with its corresponding page.

Usage:
    python scripts/generate_og_images.py

Requires:
    pip install playwright
    playwright install chromium
"""

import asyncio
import http.server
import os
import threading
import time
from pathlib import Path

# Map from og-<slug>.html to output og.png path (relative to site/)
TEMPLATE_MAP = {
    "og-homepage.html": "og.png",
    "og-use-cases-gen.html": "use-cases/og.png",
    "og-coding-assistant-governance.html": "use-cases/coding-assistant-governance/og.png",
    "og-legacy-codebase-memory.html": "use-cases/legacy-codebase-memory/og.png",
    "og-security-compliance-guardrails.html": "use-cases/security-compliance-guardrails/og.png",
    "og-data-platform-governance.html": "use-cases/data-platform-governance/og.png",
    "og-design-system-governance.html": "use-cases/design-system-governance/og.png",
    "og-multi-agent-workflow-governance.html": "use-cases/multi-agent-workflow-governance/og.png",
    "og-founder.html": "founder/og.png",
    "og-contact.html": "contact/og.png",
    "og-roadmap.html": "roadmap/og.png",
    "og-insights.html": "insights/og.png",
    "og-insights-prompt-engineering.html": "insights/prompt-engineering-is-not-governance/og.png",
    "og-insights-code-review.html": "insights/ai-code-review/og.png",
    "og-insights-rag.html": "insights/rag-is-not-memory/og.png",
    "og-insights-cursor.html": "insights/cursor-rules-for-teams/og.png",
    "og-insights-nonlinear-review.html": "insights/ai-code-review-does-not-scale-linearly/og.png",
    "og-insights-review-not-governance.html": "insights/review-is-not-governance/og.png",
    "og-for-cto.html": "for-cto/og.png",
    "og-for-platform.html": "for-platform/og.png",
    "og-for-principal.html": "for-principal/og.png",
    "og-compare-index.html": "compare/og.png",
    "og-compare-coderabbit.html": "compare/coderabbit/og.png",
    "og-compare-cursor-rules.html": "compare/cursor-rules/og.png",
    "og-compare-claude-code-memory.html": "compare/claude-code-memory/og.png",
    "og-compare-rag-vs-governance.html": "compare/rag-vs-governance/og.png",
    "og-integration-index.html": "integrations/og.png",
    "og-integration-claude-code.html": "integrations/claude-code/og.png",
    "og-integration-cursor.html": "integrations/cursor/og.png",
    "og-integration-github-actions.html": "integrations/github-actions/og.png",
}

PORT = 8765
SITE_DIR = Path(__file__).parent.parent / "site"


def start_server():
    os.chdir(SITE_DIR)
    handler = http.server.SimpleHTTPRequestHandler
    handler.log_message = lambda *a: None  # suppress logs
    server = http.server.HTTPServer(("localhost", PORT), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


async def generate():
    from playwright.async_api import async_playwright

    server = start_server()
    time.sleep(0.5)  # let server start

    generated = 0
    failed = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1200, "height": 630})

        for template, output_rel in TEMPLATE_MAP.items():
            url = f"http://localhost:{PORT}/{template}"
            output_path = SITE_DIR / output_rel

            output_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                await page.goto(url, wait_until="networkidle")
                await page.screenshot(
                    path=str(output_path),
                    clip={"x": 0, "y": 0, "width": 1200, "height": 630},
                )
                print(f"saved  {output_rel}")
                generated += 1
            except Exception as e:
                print(f"FAILED {template}: {e}")
                failed += 1

        await browser.close()

    server.shutdown()
    print(f"\nDone: {generated} saved, {failed} failed")


if __name__ == "__main__":
    asyncio.run(generate())

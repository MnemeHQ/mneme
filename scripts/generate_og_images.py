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
    "og-demo.html": "demo/og.png",
    "og-demo-storage-decision.html": "demo/storage-decision/og.png",
    "og-demo-dependency-policy.html": "demo/dependency-policy/og.png",
    "og-demo-repository-pattern.html": "demo/repository-pattern/og.png",
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
    "og-insights-rag.html": "insights/rag-is-not-memory/og.png",
    "og-insights-nonlinear-review.html": "insights/ai-code-review-does-not-scale-linearly/og.png",
    "og-insights-review-not-governance.html": "insights/review-is-not-governance/og.png",
    "og-insights-prompt-memory-fails.html": "insights/why-prompt-memory-fails-at-scale/og.png",
    "og-insights-heterogeneous-agents.html": "insights/architectural-governance-across-heterogeneous-ai-coding-agents/og.png",
    "og-insights-agentic-education.html": "insights/rise-of-agentic-engineering-education/og.png",
    "og-insights-openai-compatible-apis.html": "insights/openai-compatible-apis-are-commoditizing-models/og.png",
    "og-standards.html": "standards/og.png",
    "og-for-cto.html": "for-cto/og.png",
    "og-for-platform.html": "for-platform/og.png",
    "og-for-principal.html": "for-principal/og.png",
    "og-compare-index.html": "compare/og.png",
    "og-compare-coderabbit.html": "compare/coderabbit/og.png",
    "og-compare-cursor-rules.html": "compare/cursor-rules/og.png",
    "og-compare-claude-code-memory.html": "compare/claude-code-memory/og.png",
    "og-compare-rag-vs-governance.html": "compare/rag-vs-governance/og.png",
    "og-compare-rag-coding-memory.html": "compare/rag-coding-memory/og.png",
    "og-compare-github-copilot.html": "compare/github-copilot/og.png",
    "og-compare-aider.html": "compare/aider/og.png",
    "og-compare-continue-dev.html": "compare/continue-dev/og.png",
    "og-compare-windsurf.html": "compare/windsurf/og.png",
    "og-compare-sourcegraph-cody.html": "compare/sourcegraph-cody/og.png",
    "og-integration-index.html": "integrations/og.png",
    "og-integration-claude-code.html": "integrations/claude-code/og.png",
    "og-integration-cursor.html": "integrations/cursor/og.png",
    "og-integration-vscode.html": "integrations/vscode/og.png",
    "og-integration-github-actions.html": "integrations/github-actions/og.png",
    "og-integration-gitlab.html": "integrations/gitlab/og.png",
    "og-integration-adr-import.html": "integrations/adr-import/og.png",
    "og-integration-copilot.html": "integrations/copilot/og.png",
    "og-integration-jetbrains.html": "integrations/jetbrains/og.png",
    "og-integration-warp.html": "integrations/warp/og.png",
    "og-ci-governance.html": "use-cases/ci-governance-for-ai-generated-code/og.png",

    # Insights — new
    "og-insights-genai-stack.html": "insights/generative-ai-software-engineering-stack/og.png",
    "og-insights-deployment-quality.html": "insights/deployment-quality-will-define-the-ai-era/og.png",
    "og-insights-acceleration-whiplash.html": "insights/acceleration-whiplash-governance-gap/og.png",
    "og-insights-agents-of-chaos.html": "insights/agents-of-chaos-and-the-governance-gap/og.png",
    "og-insights-ai-native-intent-debt.html": "insights/ai-native-engineering-intent-debt/og.png",
    "og-insights-autonomous-remediation.html": "insights/autonomous-code-remediation-requires-architectural-governance/og.png",
    "og-insights-datadog-report.html": "insights/datadog-state-of-ai-engineering-governance-crisis/og.png",
    "og-insights-long-running-agents.html": "insights/long-running-agents-need-governance/og.png",
    "og-insights-openclaw.html": "insights/openclaw-and-the-limits-of-autonomous-coding/og.png",
    "og-insights-ai-sdlc.html": "insights/what-is-the-ai-sdlc/og.png",
    "og-insights-claude-md-scaling.html": "insights/why-claude-md-stops-scaling/og.png",
    "og-insights-reviewable-governance.html": "insights/ai-coding-governance-should-be-reviewable/og.png",
    "og-insights-copilot-space.html": "insights/github-copilot-space-framework/og.png",
    "og-insights-productivity-paradox.html": "insights/productivity-paradox-perception-vs-measurement/og.png",
    "og-insights-harness-governance.html": "insights/harness-engineering-still-needs-governance/og.png",
    "og-insights-observability-governance.html": "insights/why-observability-is-not-governance/og.png",
    "og-insights-agent-infrastructure-stack.html": "insights/emerging-ai-agent-infrastructure-stack/og.png",
    "og-insights-context-drift.html": "insights/why-context-alone-doesnt-prevent-architectural-drift/og.png",
    "og-insights-agent-skills.html": "insights/agent-skills-vs-architectural-governance/og.png",
    "og-insights-goal-driven-agents.html": "insights/goal-driven-agents-architectural-governance/og.png",
    "og-insights-llm-wiki.html": "insights/llm-wiki-library-not-law/og.png",
    "og-insights-ai-operating-layer.html": "insights/ai-is-becoming-the-operating-layer-for-software-execution/og.png",
    "og-insights-models-are-temporary.html": "insights/models-are-temporary-architectural-intent-is-not/og.png",
    # Concepts
    "og-concepts-index.html": "concepts/og.png",
    "og-concepts-agentic-development.html": "concepts/agentic-development/og.png",
    "og-concepts-ai-agent-drift.html": "concepts/ai-agent-drift/og.png",
    "og-concepts-ai-native-sdlc.html": "concepts/ai-native-sdlc/og.png",
    "og-concepts-architectural-compiler.html": "concepts/architectural-compiler/og.png",
    "og-concepts-architectural-drift.html": "concepts/architectural-drift/og.png",
    "og-concepts-architectural-governance.html": "concepts/architectural-governance/og.png",
    "og-concepts-decision-continuity.html": "concepts/decision-continuity/og.png",
    "og-concepts-deterministic-enforcement.html": "concepts/deterministic-enforcement/og.png",
    "og-concepts-enforcement-provenance.html": "concepts/enforcement-provenance/og.png",
    "og-concepts-governance-before-generation.html": "concepts/governance-before-generation/og.png",
    "og-concepts-governance-infrastructure.html": "concepts/governance-infrastructure/og.png",
    "og-concepts-governance-propagation.html": "concepts/governance-propagation/og.png",
    "og-concepts-intent-debt.html": "concepts/intent-debt/og.png",
    "og-concepts-multi-agent-continuity.html": "concepts/multi-agent-continuity/og.png",
    "og-concepts-precedence-semantics.html": "concepts/precedence-semantics/og.png",
    "og-concepts-verification-contracts.html": "concepts/verification-contracts/og.png",
    "og-concepts-agent-verification.html": "concepts/agent-verification/og.png",
    "og-concepts-governance-provenance.html": "concepts/governance-provenance/og.png",
    "og-concepts-execution-surfaces.html": "concepts/execution-surfaces/og.png",
    "og-concepts-reliable-delegation.html": "concepts/reliable-delegation/og.png",
    "og-concepts-objective-driven-development.html": "concepts/objective-driven-development/og.png",
    "og-concepts-executable-architectural-intent.html": "concepts/executable-architectural-intent/og.png",
    "og-concepts-ai-operating-layer.html": "concepts/ai-operating-layer/og.png",
    "og-concepts-model-independent-governance.html": "concepts/model-independent-governance/og.png",
    # Docs
    "og-docs.html": "docs/og.png",
    # Architecture
    "og-architecture-index.html": "architecture/og.png",
    "og-architecture-decision-memory.html": "architecture/decision-memory-vs-documentation/og.png",
    "og-architecture-retrieval.html": "architecture/how-retrieval-works/og.png",
    # Supported languages
    "og-supported-languages.html": "supported-languages/og.png",
    "og-supported-languages-js.html": "supported-languages/javascript-governance/og.png",
    "og-supported-languages-py.html": "supported-languages/python-governance/og.png",
    "og-supported-languages-ts.html": "supported-languages/typescript-governance/og.png",
    # Misc
    "og-about.html": "about/og.png",
    "og-benchmark.html": "benchmark/og.png",
    "og-for-index.html": "for/og.png",
    "og-pilot.html": "pilot/og.png",
    "og-platforms.html": "platforms/og.png",
    "og-privacy.html": "privacy/og.png",
    "og-works-with.html": "works-with/og.png",
    "og-integration-claude-agent-sdk.html": "integrations/claude-agent-sdk/og.png",

    # Insights — new
    "og-insights-governance-perimeter-endpoint.html": "insights/governance-perimeter-is-moving-to-the-endpoint/og.png",
    "og-insights-html-not-the-point.html": "insights/html-is-not-the-point-structure-is/og.png",
    "og-insights-runtime-vs-architectural.html": "insights/runtime-verification-is-not-architectural-verification/og.png",
    "og-insights-ai-roi-systems.html": "insights/ai-roi-problem-is-about-systems-not-models/og.png",
    "og-insights-anthropic-coordination.html": "insights/anthropic-research-system-coordination-infrastructure/og.png",
    "og-insights-pr-review-incident.html": "insights/pr-review-is-becoming-incident-response/og.png",
    # Backfill — pre-existing templates missing from TEMPLATE_MAP, plus a new
    # template for agentic-infrastructure-attack-surface (PNG rendered for
    # the validator's og.png check)
    "og-insights-rag.html": "insights/rag-is-not-memory/og.png",
    "og-insights-ai-operating-layer.html": "insights/ai-is-becoming-the-operating-layer-for-software-execution/og.png",
    "og-insights-agentic-attack-surface.html": "insights/agentic-infrastructure-attack-surface/og.png",

    # Insights — new
    "og-insights-ms-agentic-playbook.html": "insights/microsoft-agentic-transformation-playbook-ai-agent-governance/og.png",
    "og-insights-constraint-decay.html": "insights/constraint-decay-coding-agents-architectural-governance/og.png",
    "og-insights-ai-peer-review.html": "insights/ai-peer-review-context-loss-governance/og.png",
    "og-insights-ms-agent-forge.html": "insights/microsoft-agent-forge-enterprise-ai-infrastructure/og.png",
    "og-insights-machine-readable-prs.html": "insights/machine-readable-pull-requests-agentic-development/og.png",
    "og-insights-long-context-governance.html": "insights/long-context-windows-governance-infrastructure/og.png",
    "og-insights-agent-runtime-governance.html": "insights/agent-runtime-governance/og.png",
    "og-insights-mistral-vibe.html": "insights/mistral-vibe-ai-coding-enterprise-infrastructure/og.png",
    "og-insights-coordination-governance.html": "insights/coordination-governance-multi-agent-systems/og.png",
    "og-insights-determinism-probabilistic.html": "insights/ai-stack-determinism-probabilistic-models/og.png",
    "og-insights-snowflake-report.html": "insights/snowflake-ai-data-engineering-governance-infrastructure/og.png",
    "og-insights-claude-marketplace.html": "insights/anthropic-claude-marketplace-ai-engineering-control-plane/og.png",
    "og-insights-devin-governance.html": "insights/devin-ai-software-engineer-governance/og.png",
    "og-insights-antigravity-coordination.html": "insights/antigravity-solves-coordination-not-governance/og.png",
    "og-insights-artifacts-not-governance.html": "insights/artifacts-are-not-governance/og.png",
    "og-insights-agent-manager-control.html": "insights/agent-manager-control-plane-governance/og.png",
    "og-insights-agent-first-ides.html": "insights/agent-first-ides-need-architectural-invariants/og.png",
    "og-insights-governance-category.html": "insights/ai-infrastructure-governance-category/og.png",
    "og-insights-liskov-python.html": "insights/barbara-liskov-python-encapsulation-ai-governance/og.png",
    "og-insights-cursor-habits.html": "insights/cursor-developer-habits-report-governance-infrastructure/og.png",
    "og-insights-dora-metrics.html": "insights/dora-metrics-insufficient-for-agentic-development/og.png",
    "og-insights-gemini-deep-research.html": "insights/google-gemini-deep-research-agent-governance/og.png",
    "og-insights-harness-engineering.html": "insights/what-is-harness-engineering/og.png",
    "og-insights-prompt-vs-harness.html": "insights/prompt-engineering-vs-harness-engineering/og.png",
    "og-insights-harness-verification.html": "insights/harness-engineering-verification-layer/og.png",
    "og-insights-two-markets.html": "insights/ai-agent-governance-two-markets/og.png",
    # Concepts
    "og-concepts-runtime-governance.html": "concepts/runtime-governance/og.png",
    "og-concepts-autonomous-se-governance.html": "concepts/autonomous-software-engineering-governance/og.png",
    "og-concepts-agentic-ide-governance.html": "concepts/agentic-ide-governance/og.png",
    "og-concepts-multi-agent-drift.html": "concepts/multi-agent-architectural-drift/og.png",
    "og-concepts-artifact-provenance.html": "concepts/artifact-provenance/og.png",
    "og-concepts-antigravity-governance.html": "concepts/antigravity-governance/og.png",
    "og-concepts-ai-governance-infrastructure.html": "concepts/ai-governance-infrastructure/og.png",
    # Misc
    "og-integration-ms-agent-forge.html": "integrations/microsoft-agent-forge/og.png",
    "og-integration-antigravity.html": "integrations/antigravity/og.png",
    "og-works-with-claude-marketplace.html": "works-with/claude-marketplace/og.png",
    "og-works-with-devin.html": "works-with/devin/og.png",
    "og-works-with-antigravity.html": "works-with/antigravity/og.png",
    "og-compare-devin-vs-architectural-governance.html": "compare/devin-vs-architectural-governance/og.png",
    "og-compare-google-antigravity-vs-mneme.html": "compare/google-antigravity-vs-mneme/og.png",
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

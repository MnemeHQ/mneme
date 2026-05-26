#!/usr/bin/env python3
"""
Ensure complete OG image coverage for the Mneme HQ site.

This script:
1. Writes missing OG HTML template files to site/
2. Updates TEMPLATE_MAP in generate_og_images.py
3. Fixes wrong og:image / twitter:image tags in HTML pages

Does NOT generate any images — run generate_og_images.py separately.
"""

from pathlib import Path
import re

ROOT = Path(__file__).parent.parent
SITE_DIR = ROOT / "site"
GENERATE_SCRIPT = ROOT / "scripts" / "generate_og_images.py"

# ---------------------------------------------------------------------------
# Template helper
# ---------------------------------------------------------------------------

OG_CSS = """\
  @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Instrument+Serif:ital@0;1&display=swap');
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 1200px;
    height: 630px;
    background: #0c0c0d;
    font-family: 'DM Mono', monospace;
    overflow: hidden;
    position: relative;
  }
  .grid {
    position: absolute;
    inset: 0;
    background-image:
      linear-gradient(rgba(200,240,96,0.04) 1px, transparent 1px),
      linear-gradient(90deg, rgba(200,240,96,0.04) 1px, transparent 1px);
    background-size: 60px 60px;
    pointer-events: none;
  }
  .glow {
    position: absolute;
    top: -120px;
    left: -120px;
    width: 600px;
    height: 600px;
    background: radial-gradient(circle at top left, rgba(200,240,96,0.08), transparent 70%);
    pointer-events: none;
  }
  .container {
    position: relative;
    z-index: 1;
    width: 100%;
    height: 100%;
    padding: 44px 52px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }
  .top {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .logo {
    font-family: 'Instrument Serif', serif;
    font-size: 26px;
    color: #e8e8ec;
    letter-spacing: -0.3px;
  }
  .tag {
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    font-weight: 500;
    color: #c8f060;
    background: rgba(200,240,96,0.08);
    border: 1px solid rgba(200,240,96,0.25);
    border-radius: 100px;
    padding: 5px 14px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .middle {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    max-width: 820px;
    padding-top: 8px;
  }
  .heading {
    font-family: 'Instrument Serif', serif;
    line-height: 1.08;
    color: #e8e8ec;
    letter-spacing: -1px;
    margin-bottom: 20px;
  }
  .heading em {
    font-style: italic;
    color: #c8f060;
  }
  .subtitle {
    font-family: 'DM Mono', monospace;
    font-size: 15px;
    line-height: 1.65;
    color: #88889a;
    font-weight: 300;
    max-width: 680px;
  }
  .bottom {
    display: flex;
    align-items: flex-end;
    justify-content: flex-end;
  }
  .url {
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    color: #55555f;
    letter-spacing: 0.01em;
    white-space: nowrap;
  }\
"""


def make_template(tag: str, heading: str, font_size: str, subtitle: str, url_path: str) -> str:
    """Generate a standard OG template HTML string."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8" />
<style>
{OG_CSS}
</style>
</head>
<body>
  <div class="grid"></div>
  <div class="glow"></div>
  <div class="container">
    <div class="top">
      <span class="logo">Mneme HQ</span>
      <span class="tag">{tag}</span>
    </div>
    <div class="middle">
      <div class="heading" style="font-size: {font_size};">{heading}</div>
      <div class="subtitle">{subtitle}</div>
    </div>
    <div class="bottom">
      <div class="url">mnemehq.com/{url_path}</div>
    </div>
  </div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------
# Each entry: (filename, tag, heading, font_size, subtitle, url_path)
# url_path is the path segment after mnemehq.com/ in the OG card URL line.

TEMPLATES = [
    # === INSIGHTS ===
    (
        "og-insights-acceleration-whiplash.html",
        "Insights",
        "The Acceleration Whiplash and the Governance Gap",
        "46px",
        "AI acceleration outpaces the governance structures teams rely on.",
        "insights/acceleration-whiplash-governance-gap",
    ),
    (
        "og-insights-agents-of-chaos.html",
        "Insights",
        "Agents of Chaos and the Governance Gap",
        "52px",
        "Real AI agents in live environments drift further than static analysis predicts.",
        "insights/agents-of-chaos-and-the-governance-gap",
    ),
    (
        "og-insights-ai-native-intent-debt.html",
        "Insights",
        "AI-Native Engineering Has an Intent Debt Problem",
        "46px",
        "As agents write more code, the real risk is stale intent.",
        "insights/ai-native-engineering-intent-debt",
    ),
    (
        "og-insights-autonomous-remediation.html",
        "Insights",
        "Autonomous Code Remediation Requires Architectural Governance",
        "42px",
        "Remediation loops cannot stabilise without deterministic architectural constraints.",
        "insights/autonomous-code-remediation-requires-architectural-governance",
    ),
    (
        "og-insights-datadog-report.html",
        "Insights",
        "Datadog's Report Quietly Confirms the Governance Crisis",
        "46px",
        "1,000+ production AI orgs. The signal is unmistakable.",
        "insights/datadog-state-of-ai-engineering-governance-crisis",
    ),
    (
        "og-insights-long-running-agents.html",
        "Insights",
        "Long-Running Agents Need More Than Memory",
        "52px",
        "Memory solves continuity. Governance solves constraint.",
        "insights/long-running-agents-need-governance",
    ),
    (
        "og-insights-openclaw.html",
        "Insights",
        "OpenClaw and the Limits of Autonomous Coding",
        "46px",
        "100,000 stars in a week. Still no architectural constraints.",
        "insights/openclaw-and-the-limits-of-autonomous-coding",
    ),
    (
        "og-insights-ai-sdlc.html",
        "Insights",
        "What Is the AI SDLC?",
        "62px",
        "The familiar lifecycle, redefined for AI-native development.",
        "insights/what-is-the-ai-sdlc",
    ),
    (
        "og-insights-claude-md-scaling.html",
        "Insights",
        "Why CLAUDE.md Stops Scaling",
        "62px",
        "An instruction surface is not a governance layer.",
        "insights/why-claude-md-stops-scaling",
    ),
    (
        "og-insights-reviewable-governance.html",
        "Insights",
        "AI Coding Governance Should Be Reviewable",
        "52px",
        "Most AI memory is opaque hidden state. Governance should be versioned engineering.",
        "insights/ai-coding-governance-should-be-reviewable",
    ),
    (
        "og-insights-copilot-space.html",
        "Insights",
        "GitHub Copilot and the SPACE Framework",
        "52px",
        "Most teams measure Copilot the wrong way.",
        "insights/github-copilot-space-framework",
    ),
    (
        "og-insights-harness-governance.html",
        "Insights",
        "Harness Engineering Still Needs Governance",
        "52px",
        "Execution and orchestration are solved. Architectural constraints are not.",
        "insights/harness-engineering-still-needs-governance",
    ),
    (
        "og-insights-observability-governance.html",
        "Insights",
        "Why Observability Is Not Governance",
        "52px",
        "Observability tells you the agent violated architecture. Governance prevents it.",
        "insights/why-observability-is-not-governance",
    ),
    (
        "og-insights-governance-perimeter-endpoint.html",
        "Insights",
        "The Governance Perimeter Is Moving to the Endpoint",
        "42px",
        "Centralized control planes collapse as autonomous execution moves on-device. Governance has to travel with the workflow.",
        "insights/governance-perimeter-is-moving-to-the-endpoint",
    ),
    (
        "og-insights-html-not-the-point.html",
        "Insights",
        "HTML Is Not the Point. Structure Is.",
        "52px",
        "Software artifacts are becoming machine-operable execution surfaces. That dramatically expands the governance surface.",
        "insights/html-is-not-the-point-structure-is",
    ),
    (
        "og-insights-runtime-vs-architectural.html",
        "Insights",
        "Runtime Verification Is Not Architectural Verification",
        "42px",
        "Sandbox safety protects a single agent run. Architectural integrity protects the system over time.",
        "insights/runtime-verification-is-not-architectural-verification",
    ),
    (
        "og-insights-ai-roi-systems.html",
        "Insights",
        "The AI ROI Problem Is About Systems, Not Models.",
        "46px",
        "Generation is commoditizing. Verification is not. The asymmetry is consuming the productivity gains.",
        "insights/ai-roi-problem-is-about-systems-not-models",
    ),
    (
        "og-insights-anthropic-coordination.html",
        "Insights",
        "The Next Layer of AI Infrastructure",
        "52px",
        "Anthropic's multi-agent research system reveals coordination infrastructure as the new category between orchestration and execution.",
        "insights/anthropic-research-system-coordination-infrastructure",
    ),
    (
        "og-insights-pr-review-incident.html",
        "Insights",
        "PR Review Is Becoming Incident Response",
        "52px",
        "Under agent velocity, the review queue is where governance failures get detected, not where they get prevented.",
        "insights/pr-review-is-becoming-incident-response",
    ),
    # === CONCEPTS index ===
    (
        "og-concepts-index.html",
        "Concept",
        "The language of AI-native governance",
        "62px",
        "Foundational concepts behind architectural governance for AI coding agents.",
        "concepts",
    ),
    # === CONCEPTS individual ===
    (
        "og-concepts-agentic-development.html",
        "Concept",
        "Agentic Development",
        "62px",
        "A paradigm where AI agents are the primary authors of production code.",
        "concepts/agentic-development",
    ),
    (
        "og-concepts-ai-agent-drift.html",
        "Concept",
        "AI Agent Drift",
        "62px",
        "Agents progressively diverge from recorded architectural decisions over time.",
        "concepts/ai-agent-drift",
    ),
    (
        "og-concepts-ai-native-sdlc.html",
        "Concept",
        "AI-Native SDLC",
        "62px",
        "Software delivery designed from first principles for AI-assisted development.",
        "concepts/ai-native-sdlc",
    ),
    (
        "og-concepts-architectural-compiler.html",
        "Concept",
        "Architectural Compiler",
        "62px",
        "Converts documentation into machine-enforceable governance constraints.",
        "concepts/architectural-compiler",
    ),
    (
        "og-concepts-architectural-drift.html",
        "Concept",
        "Architectural Drift",
        "62px",
        "Compound degradation of codebase coherence over many AI-assisted commits.",
        "concepts/architectural-drift",
    ),
    (
        "og-concepts-architectural-governance.html",
        "Concept",
        "Architectural Governance",
        "62px",
        "Encodes team decisions as structured, retrievable, enforceable constraints.",
        "concepts/architectural-governance",
    ),
    (
        "og-concepts-decision-continuity.html",
        "Concept",
        "Decision Continuity",
        "62px",
        "Architectural decisions remain active across every AI call in a session.",
        "concepts/decision-continuity",
    ),
    (
        "og-concepts-deterministic-enforcement.html",
        "Concept",
        "Deterministic Enforcement",
        "62px",
        "Same input. Same verdict. Every time.",
        "concepts/deterministic-enforcement",
    ),
    (
        "og-concepts-enforcement-provenance.html",
        "Concept",
        "Enforcement Provenance",
        "62px",
        "Every verdict traces back to a specific recorded decision.",
        "concepts/enforcement-provenance",
    ),
    (
        "og-concepts-governance-before-generation.html",
        "Concept",
        "Governance Before Generation",
        "62px",
        "Enforce architectural constraints before the LLM produces output.",
        "concepts/governance-before-generation",
    ),
    (
        "og-concepts-governance-infrastructure.html",
        "Concept",
        "Governance Infrastructure",
        "62px",
        "The engineering platform layer that encodes and propagates constraints.",
        "concepts/governance-infrastructure",
    ),
    (
        "og-concepts-governance-propagation.html",
        "Concept",
        "Governance Propagation",
        "62px",
        "A single compiled decision reaches every agent call in your workflow.",
        "concepts/governance-propagation",
    ),
    (
        "og-concepts-intent-debt.html",
        "Concept",
        "Intent Debt",
        "62px",
        "The gap between what a system should preserve and what it actually does.",
        "concepts/intent-debt",
    ),
    (
        "og-concepts-multi-agent-continuity.html",
        "Concept",
        "Multi-Agent Continuity",
        "62px",
        "Architectural decisions persist across every agent in a coordinated workflow.",
        "concepts/multi-agent-continuity",
    ),
    (
        "og-concepts-precedence-semantics.html",
        "Concept",
        "Precedence Semantics",
        "62px",
        "How a governance system resolves conflicts between competing decisions.",
        "concepts/precedence-semantics",
    ),
    (
        "og-concepts-verification-contracts.html",
        "Concept",
        "Verification Contracts",
        "62px",
        "Pre-registered, machine-evaluable assertions about generated output.",
        "concepts/verification-contracts",
    ),
    # === DOCS ===
    (
        "og-docs.html",
        "Docs",
        "Documentation.",
        "62px",
        "CLI reference, governance violations, enforcement mechanics, benchmark methodology.",
        "docs",
    ),
    # === ARCHITECTURE ===
    (
        "og-architecture-index.html",
        "Architecture",
        "How Mneme works, precisely",
        "62px",
        "Technical deep dives into the retrieval pipeline, enforcement mechanics, and design decisions.",
        "architecture",
    ),
    (
        "og-architecture-decision-memory.html",
        "Architecture",
        "Decision Memory vs. Documentation",
        "52px",
        "They look similar. They solve different problems.",
        "architecture/decision-memory-vs-documentation",
    ),
    (
        "og-architecture-retrieval.html",
        "Architecture",
        "How Retrieval Works in Mneme",
        "62px",
        "Deterministic keyword scoring over structured decision records.",
        "architecture/how-retrieval-works",
    ),
    # === SUPPORTED LANGUAGES ===
    (
        "og-supported-languages.html",
        "Languages",
        "Governance is language-agnostic",
        "52px",
        "Mneme HQ enforces architectural decisions across Python, TypeScript, and JavaScript.",
        "supported-languages",
    ),
    (
        "og-supported-languages-js.html",
        "Languages",
        "JavaScript Governance",
        "62px",
        "Architectural governance for AI-assisted JavaScript development.",
        "supported-languages/javascript-governance",
    ),
    (
        "og-supported-languages-py.html",
        "Languages",
        "Python Governance",
        "62px",
        "Architectural governance for AI-assisted Python development.",
        "supported-languages/python-governance",
    ),
    (
        "og-supported-languages-ts.html",
        "Languages",
        "TypeScript Governance",
        "62px",
        "Architectural governance for AI-assisted TypeScript development.",
        "supported-languages/typescript-governance",
    ),
    # === MISC ===
    (
        "og-about.html",
        "About",
        "Architectural governance for AI-assisted development.",
        "46px",
        "Mneme HQ is the lightweight governance layer between your architectural decisions and your AI coding tools.",
        "about",
    ),
    (
        "og-benchmark.html",
        "Benchmark",
        "Governance Benchmark v1.1",
        "62px",
        "36 scenarios. Structured fixtures. Deterministic retrieval.",
        "benchmark",
    ),
    (
        "og-for-index.html",
        "Mneme HQ",
        "Who Mneme Is For",
        "62px",
        "Built for engineering teams where AI-assisted development is moving faster than governance.",
        "for",
    ),
    (
        "og-pilot.html",
        "Pilot",
        "Request a Pilot",
        "62px",
        "Mneme is working with engineering teams using AI coding tools at scale.",
        "pilot",
    ),
    (
        "og-platforms.html",
        "Platforms",
        "Governance for AI Developer Platforms",
        "52px",
        "Mneme HQ runs inside the enterprise platforms layer.",
        "platforms",
    ),
    (
        "og-privacy.html",
        "Legal",
        "Privacy Policy",
        "62px",
        "mnemehq.com",
        "privacy",
    ),
    (
        "og-works-with.html",
        "Works With",
        "Governance across AI coding models and agent frameworks",
        "46px",
        "Mneme operates across Claude Code, Cursor, Copilot, and agent workflows.",
        "works-with",
    ),
    (
        "og-integration-claude-agent-sdk.html",
        "Integration",
        "Govern Claude Agent SDK Workflows",
        "52px",
        "Claude Agent SDK handles execution. Mneme handles architectural constraints.",
        "integrations/claude-agent-sdk",
    ),
]

# ---------------------------------------------------------------------------
# TEMPLATE_MAP entries to add (template -> output relative to site/)
# Includes templates-to-create AND pre-existing ones missing from the map.
# ---------------------------------------------------------------------------

NEW_MAP_ENTRIES = {
    # Pre-existing templates missing from TEMPLATE_MAP
    "og-insights-genai-stack.html": "insights/generative-ai-software-engineering-stack/og.png",
    "og-insights-deployment-quality.html": "insights/deployment-quality-will-define-the-ai-era/og.png",
    # New insight templates
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
    "og-insights-harness-governance.html": "insights/harness-engineering-still-needs-governance/og.png",
    "og-insights-observability-governance.html": "insights/why-observability-is-not-governance/og.png",
    "og-insights-governance-perimeter-endpoint.html": "insights/governance-perimeter-is-moving-to-the-endpoint/og.png",
    "og-insights-html-not-the-point.html": "insights/html-is-not-the-point-structure-is/og.png",
    "og-insights-runtime-vs-architectural.html": "insights/runtime-verification-is-not-architectural-verification/og.png",
    "og-insights-ai-roi-systems.html": "insights/ai-roi-problem-is-about-systems-not-models/og.png",
    "og-insights-anthropic-coordination.html": "insights/anthropic-research-system-coordination-infrastructure/og.png",
    "og-insights-pr-review-incident.html": "insights/pr-review-is-becoming-incident-response/og.png",
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
}

# ---------------------------------------------------------------------------
# HTML og:image tag fixes
# Maps HTML file path (relative to ROOT) -> correct og:image URL
# ---------------------------------------------------------------------------

HTML_FIXES = {
    "site/about/index.html": "https://mnemehq.com/about/og.png",
    "site/architecture/index.html": "https://mnemehq.com/architecture/og.png",
    "site/architecture/decision-memory-vs-documentation/index.html": "https://mnemehq.com/architecture/decision-memory-vs-documentation/og.png",
    "site/architecture/how-retrieval-works/index.html": "https://mnemehq.com/architecture/how-retrieval-works/og.png",
    "site/benchmark/index.html": "https://mnemehq.com/benchmark/og.png",
    "site/concepts/index.html": "https://mnemehq.com/concepts/og.png",
    "site/concepts/agentic-development/index.html": "https://mnemehq.com/concepts/agentic-development/og.png",
    "site/concepts/ai-agent-drift/index.html": "https://mnemehq.com/concepts/ai-agent-drift/og.png",
    "site/concepts/ai-native-sdlc/index.html": "https://mnemehq.com/concepts/ai-native-sdlc/og.png",
    "site/concepts/architectural-compiler/index.html": "https://mnemehq.com/concepts/architectural-compiler/og.png",
    "site/concepts/architectural-drift/index.html": "https://mnemehq.com/concepts/architectural-drift/og.png",
    "site/concepts/architectural-governance/index.html": "https://mnemehq.com/concepts/architectural-governance/og.png",
    "site/concepts/decision-continuity/index.html": "https://mnemehq.com/concepts/decision-continuity/og.png",
    "site/concepts/deterministic-enforcement/index.html": "https://mnemehq.com/concepts/deterministic-enforcement/og.png",
    "site/concepts/enforcement-provenance/index.html": "https://mnemehq.com/concepts/enforcement-provenance/og.png",
    "site/concepts/governance-before-generation/index.html": "https://mnemehq.com/concepts/governance-before-generation/og.png",
    "site/concepts/governance-infrastructure/index.html": "https://mnemehq.com/concepts/governance-infrastructure/og.png",
    "site/concepts/governance-propagation/index.html": "https://mnemehq.com/concepts/governance-propagation/og.png",
    "site/concepts/intent-debt/index.html": "https://mnemehq.com/concepts/intent-debt/og.png",
    "site/concepts/multi-agent-continuity/index.html": "https://mnemehq.com/concepts/multi-agent-continuity/og.png",
    "site/concepts/precedence-semantics/index.html": "https://mnemehq.com/concepts/precedence-semantics/og.png",
    "site/concepts/verification-contracts/index.html": "https://mnemehq.com/concepts/verification-contracts/og.png",
    "site/docs/index.html": "https://mnemehq.com/docs/og.png",
    "site/docs/benchmark-methodology/index.html": "https://mnemehq.com/docs/og.png",
    "site/docs/cli/index.html": "https://mnemehq.com/docs/og.png",
    "site/docs/governance-violations/index.html": "https://mnemehq.com/docs/og.png",
    "site/docs/how-enforcement-works/index.html": "https://mnemehq.com/docs/og.png",
    "site/docs/supported-languages/index.html": "https://mnemehq.com/docs/og.png",
    "site/for/index.html": "https://mnemehq.com/for/og.png",
    "site/insights/ai-coding-governance-should-be-reviewable/index.html": "https://mnemehq.com/insights/ai-coding-governance-should-be-reviewable/og.png",
    "site/insights/github-copilot-space-framework/index.html": "https://mnemehq.com/insights/github-copilot-space-framework/og.png",
    "site/insights/harness-engineering-still-needs-governance/index.html": "https://mnemehq.com/insights/harness-engineering-still-needs-governance/og.png",
    "site/insights/why-observability-is-not-governance/index.html": "https://mnemehq.com/insights/why-observability-is-not-governance/og.png",
    "site/pilot/index.html": "https://mnemehq.com/pilot/og.png",
    "site/platforms/index.html": "https://mnemehq.com/platforms/og.png",
    "site/privacy/index.html": "https://mnemehq.com/privacy/og.png",
    "site/supported-languages/index.html": "https://mnemehq.com/supported-languages/og.png",
    "site/supported-languages/javascript-governance/index.html": "https://mnemehq.com/supported-languages/javascript-governance/og.png",
    "site/supported-languages/python-governance/index.html": "https://mnemehq.com/supported-languages/python-governance/og.png",
    "site/supported-languages/typescript-governance/index.html": "https://mnemehq.com/supported-languages/typescript-governance/og.png",
    "site/use-cases/index.html": "https://mnemehq.com/use-cases/og.png",
}

# ---------------------------------------------------------------------------
# Step 1: Write missing template files
# ---------------------------------------------------------------------------

def write_templates():
    written = 0
    skipped = 0
    for entry in TEMPLATES:
        filename, tag, heading, font_size, subtitle, url_path = entry
        dest = SITE_DIR / filename
        if dest.exists():
            print(f"  skip   {filename} (already exists)")
            skipped += 1
        else:
            html = make_template(tag, heading, font_size, subtitle, url_path)
            dest.write_text(html, encoding="utf-8")
            print(f"  wrote  {filename}")
            written += 1
    print(f"\nTemplates: {written} written, {skipped} skipped\n")
    return written, skipped


# ---------------------------------------------------------------------------
# Step 2: Update TEMPLATE_MAP in generate_og_images.py
# ---------------------------------------------------------------------------

def update_template_map():
    src = GENERATE_SCRIPT.read_text(encoding="utf-8")

    # Find what's already in the map
    existing_keys = set(re.findall(r'"(og-[^"]+\.html)":', src))

    new_entries = {k: v for k, v in NEW_MAP_ENTRIES.items() if k not in existing_keys}

    if not new_entries:
        print("TEMPLATE_MAP already up to date.\n")
        return 0

    # Group entries for readability
    groups = [
        ("# Insights — new", [k for k in new_entries if k.startswith("og-insights-")]),
        ("# Concepts", [k for k in new_entries if k.startswith("og-concepts-")]),
        ("# Docs", [k for k in new_entries if k.startswith("og-docs")]),
        ("# Architecture", [k for k in new_entries if k.startswith("og-architecture-")]),
        ("# Supported languages", [k for k in new_entries if k.startswith("og-supported-languages")]),
        ("# Misc", [k for k in new_entries if not any(
            k.startswith(p) for p in (
                "og-insights-", "og-concepts-", "og-docs",
                "og-architecture-", "og-supported-languages",
            )
        )]),
    ]

    lines = ["\n"]
    for comment, keys in groups:
        relevant = [k for k in keys if k in new_entries]
        if not relevant:
            continue
        lines.append(f"    {comment}\n")
        for k in relevant:
            lines.append(f'    "{k}": "{new_entries[k]}",\n')

    insertion_block = "".join(lines)

    # Insert just before the closing brace of TEMPLATE_MAP
    pattern = r'(TEMPLATE_MAP\s*=\s*\{.*?)(^\})'
    match = re.search(pattern, src, re.DOTALL | re.MULTILINE)
    if not match:
        print("ERROR: Could not find TEMPLATE_MAP closing brace.")
        return 0

    # Find the last entry line end position
    closing_brace_pos = match.start(2)
    new_src = src[:closing_brace_pos] + insertion_block + src[closing_brace_pos:]
    GENERATE_SCRIPT.write_text(new_src, encoding="utf-8")
    print(f"TEMPLATE_MAP updated: {len(new_entries)} entries added.\n")
    return len(new_entries)


# ---------------------------------------------------------------------------
# Step 3: Fix HTML og:image and twitter:image tags
# ---------------------------------------------------------------------------

def fix_html_tags():
    fixed = 0
    not_found = 0
    for rel_path, correct_url in HTML_FIXES.items():
        html_file = ROOT / rel_path.replace("/", "\\")
        if not html_file.exists():
            print(f"  MISSING  {rel_path}")
            not_found += 1
            continue

        content = html_file.read_text(encoding="utf-8")
        changed = False

        # Fix og:image
        old_og = f'<meta property="og:image" content="https://mnemehq.com/og.png" />'
        new_og = f'<meta property="og:image" content="{correct_url}" />'
        if old_og in content:
            content = content.replace(old_og, new_og)
            changed = True

        # Fix twitter:image
        old_tw = f'<meta name="twitter:image" content="https://mnemehq.com/og.png" />'
        new_tw = f'<meta name="twitter:image" content="{correct_url}" />'
        if old_tw in content:
            content = content.replace(old_tw, new_tw)
            changed = True

        if changed:
            html_file.write_text(content, encoding="utf-8")
            print(f"  fixed   {rel_path}")
            fixed += 1
        else:
            # Check if it's already correct
            if correct_url in content:
                print(f"  ok      {rel_path} (already correct)")
            else:
                print(f"  WARN    {rel_path} (tag format unexpected — manual check needed)")

    print(f"\nHTML fixes: {fixed} updated, {not_found} missing files\n")
    return fixed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== Step 1: Writing OG template files ===")
    write_templates()

    print("=== Step 2: Updating TEMPLATE_MAP ===")
    update_template_map()

    print("=== Step 3: Fixing HTML og:image tags ===")
    fix_html_tags()

    print("=== Done ===")
    print("Next: run  python scripts/generate_og_images.py  to render all images.")


if __name__ == "__main__":
    main()

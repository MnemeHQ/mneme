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
        "og-insights-anthropic-rsi.html",
        "Insights",
        "Recursive Self-Improvement Makes Engineering Governance Inevitable",
        "40px",
        "Anthropic: Claude now writes 80%+ of the code merged into its codebase.",
        "insights/anthropic-recursive-self-improvement-engineering-governance",
    ),
    (
        "og-insights-morph-reflexes.html",
        "Insights",
        "Agent Observability Is Not Engineering Governance",
        "46px",
        "Morph Reflexes watches how agents behave. Governance decides what they build.",
        "insights/morph-reflexes-agent-observability-engineering-governance",
    ),
    (
        "og-insights-nemo-toolkit.html",
        "Insights",
        "NVIDIA NeMo Agent Toolkit: Who Governs the Code?",
        "44px",
        "Workflow tooling for agents, and the governance layer it leaves open.",
        "insights/nvidia-nemo-agent-toolkit-engineering-governance",
    ),
    (
        "og-insights-palantir-agentic.html",
        "Insights",
        "Palantir's Agentic Governance Reveals a Missing Layer",
        "44px",
        "Agent governance controls what agents do. Engineering governance controls what they build.",
        "insights/palantir-agentic-governance-engineering-governance",
    ),
    (
        "og-insights-databricks-omnigent.html",
        "Insights",
        "Databricks Omnigent and the Agent Infrastructure Layer",
        "44px",
        "Orchestration coordinates agents. Governance preserves intent.",
        "insights/databricks-omnigent-agent-infrastructure-governance",
    ),
    (
        "og-insights-gartner-ai-governance.html",
        "Insights",
        "Gartner Defined AI Governance. Engineering Needs Its Own Layer.",
        "42px",
        "Governing AI systems is different from governing the code agents change.",
        "insights/gartner-ai-governance-engineering-governance",
    ),
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
    (
        "og-supported-languages-fastapi.html",
        "Framework",
        "FastAPI Governance",
        "62px",
        "Architectural governance for AI-generated FastAPI code.",
        "supported-languages/fastapi-governance",
    ),
    (
        "og-supported-languages-spring-boot.html",
        "Framework",
        "Spring Boot Governance",
        "52px",
        "Architectural governance for AI-generated Spring Boot code.",
        "supported-languages/spring-boot-governance",
    ),
    (
        "og-supported-languages-terraform.html",
        "Infrastructure",
        "Terraform Governance",
        "62px",
        "Architectural governance for AI-generated infrastructure as code.",
        "supported-languages/terraform-governance",
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
    # === BATCH: Market context + research + Antigravity cluster (May 2026) ===
    ("og-insights-ms-agentic-playbook.html", "Insights", "Microsoft's Agentic Transformation Playbook", "46px", "Why enterprise AI agents need governance infrastructure, not just better models.", "insights/microsoft-agentic-transformation-playbook-ai-agent-governance"),
    ("og-insights-constraint-decay.html", "Insights", "Constraint Decay in Coding Agents", "52px", "Agents satisfy loose specs but lose structural fidelity as constraints accumulate.", "insights/constraint-decay-coding-agents-architectural-governance"),
    ("og-insights-ai-peer-review.html", "Insights", "AI Peer Review and Context Loss", "52px", "GPT-5.2 outperformed top human reviewers — and still missed context already in the source.", "insights/ai-peer-review-context-loss-governance"),
    ("og-insights-ms-agent-forge.html", "Insights", "Microsoft Agent Forge and the Next AI Infrastructure Layer", "42px", "Once orchestration commoditizes, governance becomes the differentiator.", "insights/microsoft-agent-forge-enterprise-ai-infrastructure"),
    ("og-insights-machine-readable-prs.html", "Insights", "Machine-Readable Pull Requests", "52px", "Human-readable PRs explain. Machine-readable PRs allow verification.", "insights/machine-readable-pull-requests-agentic-development"),
    ("og-insights-long-context-governance.html", "Insights", "Long Context Does Not Eliminate Governance", "46px", "The reranker became optional. Retrieval did not. Governance is the missing layer.", "insights/long-context-windows-governance-infrastructure"),
    ("og-insights-agent-runtime-governance.html", "Insights", "Agent Runtime Governance", "52px", "What Google Managed Agents signals about the next AI infrastructure layer.", "insights/agent-runtime-governance"),
    ("og-insights-mistral-vibe.html", "Insights", "Mistral Vibe and AI Coding Infrastructure", "46px", "Coding agents are becoming multi-surface execution systems.", "insights/mistral-vibe-ai-coding-enterprise-infrastructure"),
    ("og-insights-coordination-governance.html", "Insights", "The Next AI Infrastructure Layer Is Coordination Governance", "40px", "Subagents parallelize execution. They also parallelize inconsistency.", "insights/coordination-governance-multi-agent-systems"),
    ("og-insights-determinism-probabilistic.html", "Insights", "Rebuilding Determinism Around Probabilistic Models", "42px", "The AI stack is reintroducing the layers software engineering already developed.", "insights/ai-stack-determinism-probabilistic-models"),
    ("og-insights-snowflake-report.html", "Insights", "Snowflake's AI Data Engineering Report", "46px", "Data engineering is evolving into governance engineering.", "insights/snowflake-ai-data-engineering-governance-infrastructure"),
    ("og-insights-claude-marketplace.html", "Insights", "The Emerging AI Engineering Control Plane", "46px", "What Anthropic's Claude Marketplace reveals about the post-Copilot stack.", "insights/anthropic-claude-marketplace-ai-engineering-control-plane"),
    ("og-insights-devin-governance.html", "Insights", "Devin and the Next Layer of AI Infrastructure", "46px", "Autonomous software engineers make the governance gap visible.", "insights/devin-ai-software-engineer-governance"),
    ("og-insights-antigravity-coordination.html", "Insights", "Antigravity Solves Coordination, Not Governance", "44px", "Antigravity makes agent work visible. The next layer has to make it governable.", "insights/antigravity-solves-coordination-not-governance"),
    ("og-insights-artifacts-not-governance.html", "Insights", "Artifacts Are Not Governance", "60px", "A screenshot can prove the browser opened. It cannot prove the architecture held.", "insights/artifacts-are-not-governance"),
    ("og-insights-agent-manager-control.html", "Insights", "The Agent Manager Is the New Control Plane", "46px", "Manager views without policy are dashboards. Add policy and they become control planes.", "insights/agent-manager-control-plane-governance"),
    ("og-insights-agent-first-ides.html", "Insights", "Why Agent-First IDEs Need Architectural Invariants", "42px", "Delegated tasks need shared constraints, encoded and enforced.", "insights/agent-first-ides-need-architectural-invariants"),
    ("og-insights-governance-category.html", "Insights", "The Next AI Infrastructure Category Is Governance", "42px", "Every infrastructure wave creates a governance layer. AI coding is next.", "insights/ai-infrastructure-governance-category"),
    ("og-insights-liskov-python.html", "Insights", "Liskov's Python Critique Predicts the Governance Problem", "40px", "Encapsulation that's advisory holds at human pace. It does not survive agent velocity.", "insights/barbara-liskov-python-encapsulation-ai-governance"),
    # === BATCH: Cursor Developer Habits Report (May 2026) ===
    ("og-insights-cursor-habits.html", "Insights", "The Cursor Developer Habits Report", "52px", "Why AI coding now needs governance infrastructure.", "insights/cursor-developer-habits-report-governance-infrastructure"),
    ("og-insights-dora-metrics.html", "Insights", "DORA Metrics Are Necessary But Insufficient for Agentic Development", "40px", "Delivery metrics can stay green while the architecture degrades. Governance is the missing layer.", "insights/dora-metrics-insufficient-for-agentic-development"),
    ("og-insights-gemini-deep-research.html", "Insights", "Google Gemini Deep Research Agent", "52px", "Why managed AI agents still need governance.", "insights/google-gemini-deep-research-agent-governance"),
    # === BATCH: Agentic strategy reports (June 2026) ===
    ("og-insights-convergence-trap.html", "Insights", "The Agentic Convergence Trap", "56px", "When rivals run the same agents on the same defaults, governance is the only moat left.", "insights/agentic-convergence-trap-architectural-governance"),
    ("og-insights-table-stakes-advantage.html", "Insights", "From AI Table Stakes to AI Advantage", "46px", "Models are table stakes. The edge competitors can't copy is the architecture you enforce.", "insights/mckinsey-ai-table-stakes-to-advantage"),
    ("og-insights-agents-not-employees.html", "Insights", "AI Agents Are Not Employees", "56px", "You can't delegate accountability to something that can't hold it. Constrain, don't trust.", "insights/ai-agents-are-not-employees-governance"),
    # === BATCH: Harness engineering cluster + two-markets (May 2026) ===
    ("og-insights-harness-engineering.html", "Insights", "Harness Engineering", "62px", "The execution layer between models and production.", "insights/what-is-harness-engineering"),
    ("og-insights-prompt-vs-harness.html", "Insights", "Prompt Engineering vs Harness Engineering", "44px", "From optimizing inputs to designing systems.", "insights/prompt-engineering-vs-harness-engineering"),
    ("og-insights-harness-verification.html", "Insights", "Harness Engineering Needs Verification", "46px", "Successful execution is not verifiable execution.", "insights/harness-engineering-verification-layer"),
    ("og-insights-two-markets.html", "Insights", "AI Agent Governance, Two Markets", "46px", "Runtime governance vs architectural governance.", "insights/ai-agent-governance-two-markets"),
    # === BATCH: New concepts ===
    ("og-concepts-runtime-governance.html", "Concept", "Runtime Governance", "62px", "Enforcement across long-running autonomous execution environments.", "concepts/runtime-governance"),
    ("og-concepts-autonomous-se-governance.html", "Concept", "Autonomous Software Engineering Governance", "44px", "The enforcement layer for AI-driven software execution systems.", "concepts/autonomous-software-engineering-governance"),
    ("og-concepts-agentic-ide-governance.html", "Concept", "Agentic IDE Governance", "62px", "The control layer for autonomous agents inside development environments.", "concepts/agentic-ide-governance"),
    ("og-concepts-multi-agent-drift.html", "Concept", "Multi-Agent Architectural Drift", "52px", "When parallel agents each make plausible changes without a shared enforcement layer.", "concepts/multi-agent-architectural-drift"),
    ("og-concepts-artifact-provenance.html", "Concept", "Artifact Provenance", "62px", "Provenance explains what happened. Governance constrains what is allowed.", "concepts/artifact-provenance"),
    ("og-concepts-antigravity-governance.html", "Concept", "Antigravity Governance", "62px", "Architectural control for agent-first IDEs.", "concepts/antigravity-governance"),
    ("og-concepts-ai-governance-infrastructure.html", "Concept", "AI Governance Infrastructure", "52px", "The deterministic enforcement layer for AI-assisted software development.", "concepts/ai-governance-infrastructure"),
    ("og-concepts-spec-driven-development.html", "Concept", "Spec-Driven Development", "56px", "A structured spec as the source of truth for what an agent builds — and the architectural layer it leaves open.", "concepts/spec-driven-development"),
    ("og-insights-spec-driven-dev.html", "Insights", "Spec-Driven Development Still Needs Governance", "40px", "A spec defines what to build, not which architectural decisions must hold while the agent builds it.", "insights/spec-driven-development-still-needs-governance"),
    # === BATCH: New integrations ===
    ("og-integration-ms-agent-forge.html", "Integration", "Architectural Governance for Microsoft Agent Forge", "40px", "Mneme adds deterministic governance on top of Agent Forge's execution substrate.", "integrations/microsoft-agent-forge"),
    ("og-integration-antigravity.html", "Integration", "Architectural Governance for Google Antigravity", "42px", "Repo-native governance alongside Antigravity's editor, terminal, and browser surfaces.", "integrations/antigravity"),
    # === BATCH: New works-with sub-pages ===
    ("og-works-with-claude-marketplace.html", "Works With", "Mneme Works Alongside the Claude Marketplace", "42px", "The architectural governance layer above generation, memory, orchestration, and review.", "works-with/claude-marketplace"),
    ("og-works-with-devin.html", "Works With", "Mneme Works Alongside Devin", "52px", "Devin executes. Mneme preserves architectural intent across that execution.", "works-with/devin"),
    ("og-works-with-antigravity.html", "Works With", "Mneme Works Alongside Google Antigravity", "44px", "Architectural governance alongside agent-first development environments.", "works-with/antigravity"),
    # === BATCH: New compare pages ===
    ("og-compare-devin-vs-architectural-governance.html", "Compare", "Devin vs Architectural Governance", "52px", "Why autonomous coding agents still need deterministic enforcement.", "compare/devin-vs-architectural-governance"),
    ("og-compare-google-antigravity-vs-mneme.html", "Compare", "Google Antigravity vs Mneme", "52px", "Agentic IDEs vs architectural governance. Different layers; they compose.", "compare/google-antigravity-vs-mneme"),
    ("og-compare-claude-md.html", "Compare", "Mneme HQ vs CLAUDE.md", "56px", "A CLAUDE.md tells the model your rules. Mneme enforces the ones that must hold.", "compare/claude-md"),
    ("og-integration-opencode.html", "Integration", "Architectural Governance for OpenCode", "44px", "OpenCode runs the agent across terminal, IDE, and desktop. Mneme keeps architectural decisions enforced across all three.", "integrations/opencode"),
    # === BATCH: June 2026 Post- insights ===
    ("og-insights-rule-files-retrieval.html", "Insights", "Rule Files vs Retrieval Memory", "52px", "Static instructions are an always-on prompt prefix. Prefixes do not scale past token budget, precedence, and scope.", "insights/rule-files-vs-retrieval-memory"),
    ("og-insights-governance-by-design.html", "Insights", "Beyond Security by Design: Governance by Design", "44px", "Critical properties get designed in, not bolted on. AI agents make governance the next 'by design' discipline.", "insights/beyond-security-by-design-governance-by-design"),
    ("og-insights-agents-launch-database.html", "Insights", "When Agents Launch the Database", "52px", "Agents now provision infrastructure, not just code. Repository-level governance cannot see past the repo.", "insights/when-agents-launch-the-database"),
    ("og-insights-ms-execution-containers.html", "Insights", "Microsoft Execution Containers", "52px", "OS-enforced isolation is one layer. Architectural governance is the layer it cannot replace.", "insights/microsoft-execution-containers-ai-agent-runtime-governance"),
    ("og-insights-agent-governance-sdlc.html", "Insights", "Agent Governance in the SDLC", "52px", "Multi-agent orchestration shifts software delivery from a generation problem to a governance problem.", "insights/agent-governance-in-the-sdlc"),
    ("og-insights-cloud-agents-durable.html", "Insights", "Cloud Agents Need More Than Durable Execution", "42px", "Durable execution keeps the agent running. Architectural governance keeps the system coherent.", "insights/cloud-agents-need-architectural-governance"),
    ("og-insights-latent-space-comms.html", "Insights", "Latent-Space Agent Communication", "52px", "Natural language is an accidental governance layer. Latent communication removes the surface we govern through.", "insights/latent-space-agent-communication-governance"),
    ("og-insights-runtime-harnesses.html", "Insights", "Runtime Harnesses for AI Agents", "52px", "Reliability comes from the harness around the model, not the model alone. Better models are not enough.", "insights/runtime-harnesses-for-ai-agents"),
    ("og-insights-search-as-code.html", "Insights", "Search as Code Is an Execution Surface", "48px", "When agents compose executable workflows instead of calling tools, tool governance becomes code-execution governance.", "insights/search-as-code-agent-execution-surface"),
    # === BATCH: June 2026 Post- insights, wave 2 (report responses) ===
    ("og-insights-ai-adoption-maturity.html", "Insights", "The AI Adoption Maturity Model", "52px", "Five levels, eight dimensions — and the governance execution gap engineering leaders own.", "insights/ai-adoption-maturity-model-engineering-analysis"),
    ("og-insights-bcg-operating-models.html", "Insights", "BCG's AI-Era Operating Models", "52px", "Flatter, faster, more autonomous — and a governance problem nobody designs for.", "insights/bcg-ai-era-operating-models-governance"),
    ("og-insights-ibm-tech-leader-study.html", "Insights", "IBM 2026 Tech Leader Study", "52px", "77% say AI adoption is outpacing governance. Control is becoming a design problem.", "insights/ibm-2026-tech-leader-study-agent-governance"),
    ("og-insights-github-agent-prs.html", "Insights", "Agent Pull Requests Are Everywhere", "48px", "Reviewers trust agent PRs more while debt rises. Review is the wrong layer to fix.", "insights/github-agent-pull-requests-review-wrong-layer"),
    ("og-insights-claude-code-skills.html", "Insights", "Claude Code Skills and Organizational Knowledge", "44px", "Knowledge is leaving the prompt. Executable knowledge makes governance unavoidable.", "insights/claude-code-skills-organizational-knowledge"),
    ("og-insights-bain-ai-dlc.html", "Insights", "Bain's AI Development Lifecycle Report", "46px", "The AI-DLC makes risk a first-class constraint — and governance an engineering surface.", "insights/bain-ai-development-lifecycle-governance"),
    ("og-insights-project-solara.html", "Insights", "Microsoft Project Solara", "56px", "Devices that run agents instead of apps. Governance has to follow the agent.", "insights/microsoft-project-solara-post-app-governance"),
    ("og-insights-ms-agent-platform.html", "Insights", "Microsoft's Agent Platform and the Governance Layer", "42px", "Agent HQ, ACS, Agent 365: governance is now a named layer of the agent stack.", "insights/microsoft-agent-platform-governance-layer"),
    ("og-insights-verification-tax.html", "Insights", "The Verification Tax of AI Coding Agents", "48px", "Generation is becoming abundant. Verification is becoming the scarce resource.", "insights/ai-coding-agent-verification-tax"),
    # === BATCH: June 2026 Post- insights, wave 3 ===
    ("og-insights-shared-memory-intent.html", "Insights", "Shared Memory Is Not Shared Intent", "52px", "AI coding teams get shared memory. That solves context distribution, not governance.", "insights/shared-memory-is-not-shared-intent"),
    ("og-insights-loop-engineering.html", "Insights", "Loop Engineering Is Not New", "54px", "Loops have been computing's core abstraction for seventy years. What's new is a probabilistic generator inside the loop.", "insights/loop-engineering-is-not-new"),
    ("og-insights-productivity-rework.html", "Insights", "AI Productivity Gains Lead to More Rework", "44px", "Faros 2026: throughput up 33.7%, bugs per developer up 54%, code churn up 861%.", "insights/ai-coding-productivity-gains-rework"),
    ("og-insights-copilot-review-economics.html", "Insights", "AI Code Review Is a Budget Line Item", "46px", "GitHub Copilot's usage-based billing meters code review. The real constraint is review economics.", "insights/github-copilot-usage-based-billing-review-economics"),
    # === BATCH: June 2026 Post- insights, wave 4 (agentic governance + regulated industries) ===
    ("og-insights-infrastructure-alone.html", "Insights", "Why the AI Race Won't Be Won on Infrastructure Alone", "40px", "Infrastructure explains how you access intelligence. Governance decides how much you can safely deploy.", "insights/ai-race-wont-be-won-on-infrastructure-alone"),
    ("og-insights-governance-layers-coding.html", "Insights", "Governance Layers for AI Coding Assistants", "50px", "Policy, memory, enforcement, auditability — the missing enterprise infrastructure.", "insights/governance-layers-for-ai-coding-assistants"),
    ("og-insights-okf-vs-governance.html", "Insights", "Open Knowledge Format vs Governance", "50px", "Google's OKF standardizes how agents find knowledge. Finding it is not following it.", "insights/open-knowledge-format-vs-governance"),
    ("og-insights-rsi-orchestration.html", "Insights", "Recursive Self-Improvement Is an Orchestration Problem", "42px", "The fastest feedback loops are in the system around the model, not the model itself.", "insights/recursive-self-improvement-orchestration-problem"),
    ("og-insights-governance-control-plane.html", "Insights", "The Next Layer Is a Governance Control Plane", "44px", "Frameworks coordinate execution. Meta-harnesses coordinate agents. Neither enforces architecture.", "insights/governance-control-plane-after-agent-frameworks"),
    ("og-insights-regulated-industries.html", "Insights", "AI Governance for Regulated Industries", "52px", "Where the cost of architectural drift and undocumented agent actions is highest.", "insights/ai-governance-for-regulated-industries"),
    ("og-insights-life-sciences.html", "Insights", "AI Coding Agents in Life Sciences", "52px", "FDA, GxP, validation. Governance before autonomy.", "insights/ai-coding-agents-life-sciences-governance"),
    ("og-insights-financial-services.html", "Insights", "AI Coding Agents in Financial Services", "48px", "Architectural drift is a compliance risk. Every change needs an audit trail.", "insights/ai-coding-agents-financial-services-audit-trail"),
    ("og-insights-enterprise-guardrails.html", "Insights", "Not All AI Guardrails Are the Same", "46px", "Data, model, application, infrastructure &mdash; and the fifth layer: architectural guardrails.", "insights/enterprise-ai-guardrails-five-layers"),
    # === gap cluster (PR B) ===
    ("og-insights-agent-guardrails.html", "Insights", "AI Coding-Agent Guardrails", "50px", "Runtime, prompt, policy, architectural. Which layer actually stops a bad change from landing.", "insights/ai-coding-agent-guardrails"),
    ("og-insights-agents-use-adrs.html", "Insights", "How AI Coding Agents Use ADRs", "50px", "An ADR nobody enforces is a comment. An ADR a machine checks is a guardrail.", "insights/how-ai-coding-agents-use-adrs"),
    ("og-insights-agent-architecture.html", "Insights", "AI Coding-Agent Architecture", "48px", "The layers between a model and production: model, harness, governance, intent.", "insights/ai-coding-agent-architecture"),
]

# ---------------------------------------------------------------------------
# TEMPLATE_MAP entries to add (template -> output relative to site/)
# Includes templates-to-create AND pre-existing ones missing from the map.
# ---------------------------------------------------------------------------

NEW_MAP_ENTRIES = {
    "og-insights-anthropic-rsi.html": "insights/anthropic-recursive-self-improvement-engineering-governance/og.png",
    "og-insights-morph-reflexes.html": "insights/morph-reflexes-agent-observability-engineering-governance/og.png",
    "og-insights-nemo-toolkit.html": "insights/nvidia-nemo-agent-toolkit-engineering-governance/og.png",
    "og-insights-palantir-agentic.html": "insights/palantir-agentic-governance-engineering-governance/og.png",
    "og-insights-databricks-omnigent.html": "insights/databricks-omnigent-agent-infrastructure-governance/og.png",
    "og-insights-gartner-ai-governance.html": "insights/gartner-ai-governance-engineering-governance/og.png",
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
    # June 2026 Post- insights, wave 2 (report responses)
    "og-insights-ai-adoption-maturity.html": "insights/ai-adoption-maturity-model-engineering-analysis/og.png",
    "og-insights-bcg-operating-models.html": "insights/bcg-ai-era-operating-models-governance/og.png",
    "og-insights-ibm-tech-leader-study.html": "insights/ibm-2026-tech-leader-study-agent-governance/og.png",
    "og-insights-github-agent-prs.html": "insights/github-agent-pull-requests-review-wrong-layer/og.png",
    "og-insights-claude-code-skills.html": "insights/claude-code-skills-organizational-knowledge/og.png",
    "og-insights-bain-ai-dlc.html": "insights/bain-ai-development-lifecycle-governance/og.png",
    "og-insights-project-solara.html": "insights/microsoft-project-solara-post-app-governance/og.png",
    "og-insights-ms-agent-platform.html": "insights/microsoft-agent-platform-governance-layer/og.png",
    "og-insights-verification-tax.html": "insights/ai-coding-agent-verification-tax/og.png",
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
    "og-supported-languages-fastapi.html": "supported-languages/fastapi-governance/og.png",
    "og-supported-languages-spring-boot.html": "supported-languages/spring-boot-governance/og.png",
    "og-supported-languages-terraform.html": "supported-languages/terraform-governance/og.png",
    # Misc
    "og-about.html": "about/og.png",
    "og-benchmark.html": "benchmark/og.png",
    "og-for-index.html": "for/og.png",
    "og-pilot.html": "pilot/og.png",
    "og-platforms.html": "platforms/og.png",
    "og-privacy.html": "privacy/og.png",
    "og-works-with.html": "works-with/og.png",
    "og-integration-claude-agent-sdk.html": "integrations/claude-agent-sdk/og.png",
    # Batch May 2026: insights
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
    "og-insights-convergence-trap.html": "insights/agentic-convergence-trap-architectural-governance/og.png",
    "og-insights-table-stakes-advantage.html": "insights/mckinsey-ai-table-stakes-to-advantage/og.png",
    "og-insights-agents-not-employees.html": "insights/ai-agents-are-not-employees-governance/og.png",
    "og-insights-harness-engineering.html": "insights/what-is-harness-engineering/og.png",
    "og-insights-prompt-vs-harness.html": "insights/prompt-engineering-vs-harness-engineering/og.png",
    "og-insights-harness-verification.html": "insights/harness-engineering-verification-layer/og.png",
    "og-insights-two-markets.html": "insights/ai-agent-governance-two-markets/og.png",
    # Batch May 2026: concepts
    "og-concepts-runtime-governance.html": "concepts/runtime-governance/og.png",
    "og-concepts-autonomous-se-governance.html": "concepts/autonomous-software-engineering-governance/og.png",
    "og-concepts-agentic-ide-governance.html": "concepts/agentic-ide-governance/og.png",
    "og-concepts-multi-agent-drift.html": "concepts/multi-agent-architectural-drift/og.png",
    "og-concepts-artifact-provenance.html": "concepts/artifact-provenance/og.png",
    "og-concepts-antigravity-governance.html": "concepts/antigravity-governance/og.png",
    "og-concepts-ai-governance-infrastructure.html": "concepts/ai-governance-infrastructure/og.png",
    "og-concepts-spec-driven-development.html": "concepts/spec-driven-development/og.png",
    "og-insights-spec-driven-dev.html": "insights/spec-driven-development-still-needs-governance/og.png",
    # Batch May 2026: integrations
    "og-integration-ms-agent-forge.html": "integrations/microsoft-agent-forge/og.png",
    "og-integration-antigravity.html": "integrations/antigravity/og.png",
    # Batch May 2026: works-with sub-pages
    "og-works-with-claude-marketplace.html": "works-with/claude-marketplace/og.png",
    "og-works-with-devin.html": "works-with/devin/og.png",
    "og-works-with-antigravity.html": "works-with/antigravity/og.png",
    # Batch May 2026: compare
    "og-compare-devin-vs-architectural-governance.html": "compare/devin-vs-architectural-governance/og.png",
    "og-compare-google-antigravity-vs-mneme.html": "compare/google-antigravity-vs-mneme/og.png",
    "og-compare-claude-md.html": "compare/claude-md/og.png",
    # June 2026 Post- batch
    "og-insights-rule-files-retrieval.html": "insights/rule-files-vs-retrieval-memory/og.png",
    "og-insights-governance-by-design.html": "insights/beyond-security-by-design-governance-by-design/og.png",
    "og-insights-agents-launch-database.html": "insights/when-agents-launch-the-database/og.png",
    "og-insights-ms-execution-containers.html": "insights/microsoft-execution-containers-ai-agent-runtime-governance/og.png",
    "og-insights-agent-governance-sdlc.html": "insights/agent-governance-in-the-sdlc/og.png",
    "og-insights-cloud-agents-durable.html": "insights/cloud-agents-need-architectural-governance/og.png",
    "og-insights-latent-space-comms.html": "insights/latent-space-agent-communication-governance/og.png",
    "og-insights-runtime-harnesses.html": "insights/runtime-harnesses-for-ai-agents/og.png",
    "og-insights-search-as-code.html": "insights/search-as-code-agent-execution-surface/og.png",
    "og-integration-opencode.html": "integrations/opencode/og.png",
    # June 2026 Post- batch, wave 3
    "og-insights-shared-memory-intent.html": "insights/shared-memory-is-not-shared-intent/og.png",
    "og-insights-loop-engineering.html": "insights/loop-engineering-is-not-new/og.png",
    "og-insights-productivity-rework.html": "insights/ai-coding-productivity-gains-rework/og.png",
    "og-insights-copilot-review-economics.html": "insights/github-copilot-usage-based-billing-review-economics/og.png",
    # June 2026 Post- batch, wave 4 (agentic governance + regulated industries)
    "og-insights-infrastructure-alone.html": "insights/ai-race-wont-be-won-on-infrastructure-alone/og.png",
    "og-insights-governance-layers-coding.html": "insights/governance-layers-for-ai-coding-assistants/og.png",
    "og-insights-okf-vs-governance.html": "insights/open-knowledge-format-vs-governance/og.png",
    "og-insights-rsi-orchestration.html": "insights/recursive-self-improvement-orchestration-problem/og.png",
    "og-insights-governance-control-plane.html": "insights/governance-control-plane-after-agent-frameworks/og.png",
    "og-insights-regulated-industries.html": "insights/ai-governance-for-regulated-industries/og.png",
    "og-insights-life-sciences.html": "insights/ai-coding-agents-life-sciences-governance/og.png",
    "og-insights-financial-services.html": "insights/ai-coding-agents-financial-services-audit-trail/og.png",
    "og-insights-enterprise-guardrails.html": "insights/enterprise-ai-guardrails-five-layers/og.png",
    # gap cluster (PR B)
    "og-insights-agent-guardrails.html": "insights/ai-coding-agent-guardrails/og.png",
    "og-insights-agents-use-adrs.html": "insights/how-ai-coding-agents-use-adrs/og.png",
    "og-insights-agent-architecture.html": "insights/ai-coding-agent-architecture/og.png",
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
    "site/supported-languages/fastapi-governance/index.html": "https://mnemehq.com/supported-languages/fastapi-governance/og.png",
    "site/supported-languages/spring-boot-governance/index.html": "https://mnemehq.com/supported-languages/spring-boot-governance/og.png",
    "site/supported-languages/terraform-governance/index.html": "https://mnemehq.com/supported-languages/terraform-governance/og.png",
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

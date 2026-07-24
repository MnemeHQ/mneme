"""Apply 5 review optimizations across all use-case pages."""
import re, os

SITE = os.path.join(os.path.dirname(__file__), '..', 'site')

# ── CSS replacements shared across all case-study pages ──────────────────────
OLD_HERO_TAG_CSS = (
    ".hero-tag { display: inline-block; background: rgba(200,240,96,0.07); "
    "border: 1px solid rgba(200,240,96,0.22); color: var(--accent); "
    "font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase; "
    "padding: 0.3rem 0.9rem; border-radius: 999px; margin-bottom: 2rem; }"
)
NEW_HERO_TAG_CSS = (
    ".hero-tag { display: inline-block; color: var(--muted); "
    "font-size: 0.7rem; letter-spacing: 0.06em; text-transform: uppercase; "
    "margin-bottom: 1.5rem; }"
)

RELATED_CSS = """
    .related-wrap { max-width: 860px; margin: 0 auto; padding: 3rem 2rem; border-top: 1px solid var(--border); }
    .related-links { display: flex; gap: 1.5rem; flex-wrap: wrap; margin-top: 0.75rem; }
    .related-links a { color: var(--accent); font-size: 0.82rem; text-decoration: none; }
    .related-links a:hover { color: var(--accent-dim); }"""

# Insert related CSS before </style>
def add_related_css(html):
    return html.replace("  </style>", RELATED_CSS + "\n  </style>", 1)

# ── Hero CTA: View on GitHub → Install Mneme ─────────────────────────────────
def fix_hero_cta(html):
    return html.replace(
        '<a href="https://github.com/mnemeHQ/mneme" class="btn-primary">View on GitHub</a>\n'
        '      <a href="/#how-it-works" class="btn-ghost">How it works</a>',
        '<a href="https://github.com/mnemeHQ/mneme" class="btn-primary">Install Mneme</a>\n'
        '      <a href="https://github.com/mnemeHQ/mneme" class="btn-ghost">View GitHub</a>'
    )

# ── Bottom CTA: View on GitHub → Install Mneme ───────────────────────────────
def fix_bottom_cta(html):
    return html.replace(
        '<a href="https://github.com/mnemeHQ/mneme" class="btn-primary">View on GitHub</a>\n'
        '      <a href="/use-cases/" class="btn-ghost">More use cases</a>',
        '<a href="https://github.com/mnemeHQ/mneme" class="btn-primary">Install Mneme</a>\n'
        '      <a href="/use-cases/" class="btn-ghost">More use cases</a>'
    )

# ── Related use cases block ───────────────────────────────────────────────────
def make_related(links):
    items = "\n    ".join(
        f'<a href="{url}">{label} →</a>' for url, label in links
    )
    return (
        '\n  <div class="related-wrap">\n'
        '    <div class="section-eyebrow">Related Use Cases</div>\n'
        '    <div class="related-links">\n'
        f'    {items}\n'
        '    </div>\n'
        '  </div>\n'
    )

RELATED = {
    "coding-assistant-governance": [
        ("/use-cases/legacy-codebase-memory/", "Legacy Codebase Memory"),
        ("/use-cases/security-compliance-guardrails/", "Security &amp; Compliance Guardrails"),
        ("/use-cases/multi-agent-workflow-governance/", "Multi-Agent Workflow Governance"),
    ],
    "legacy-codebase-memory": [
        ("/use-cases/coding-assistant-governance/", "Coding Assistant Governance"),
        ("/use-cases/security-compliance-guardrails/", "Security &amp; Compliance Guardrails"),
        ("/use-cases/multi-agent-workflow-governance/", "Multi-Agent Workflow Governance"),
    ],
    "security-compliance-guardrails": [
        ("/use-cases/coding-assistant-governance/", "Coding Assistant Governance"),
        ("/use-cases/data-platform-governance/", "Data Platform Governance"),
        ("/use-cases/multi-agent-workflow-governance/", "Multi-Agent Workflow Governance"),
    ],
    "data-platform-governance": [
        ("/use-cases/security-compliance-guardrails/", "Security &amp; Compliance Guardrails"),
        ("/use-cases/design-system-governance/", "Design System Governance"),
        ("/use-cases/multi-agent-workflow-governance/", "Multi-Agent Workflow Governance"),
    ],
    "design-system-governance": [
        ("/use-cases/coding-assistant-governance/", "Coding Assistant Governance"),
        ("/use-cases/data-platform-governance/", "Data Platform Governance"),
        ("/use-cases/multi-agent-workflow-governance/", "Multi-Agent Workflow Governance"),
    ],
    "multi-agent-workflow-governance": [
        ("/use-cases/coding-assistant-governance/", "Coding Assistant Governance"),
        ("/use-cases/security-compliance-guardrails/", "Security &amp; Compliance Guardrails"),
        ("/use-cases/data-platform-governance/", "Data Platform Governance"),
    ],
}

def insert_related(html, slug):
    block = make_related(RELATED[slug])
    return html.replace("\n  <div class=\"cta-footer\">", block + "  <div class=\"cta-footer\">", 1)

# ── Metric patches per page ───────────────────────────────────────────────────
METRIC_PATCHES = {
    "coding-assistant-governance": [
        (
            '<div class="metric-value">83%</div>\n'
            '        <div class="metric-label">of architectural violations caught before code generation</div>',
            '<div class="metric-value">Pre-flight</div>\n'
            '        <div class="metric-label">violations surfaced before code generation, not at review</div>'
        ),
    ],
    "design-system-governance": [
        (
            '<div class="metric-value">3x</div><div class="metric-label">fewer design review comments related to system violations</div>',
            '<div class="metric-value">Fewer</div><div class="metric-label">design review comments on token and accessibility violations after enforcement</div>'
        ),
    ],
    "multi-agent-workflow-governance": [
        (
            '<div class="metric-value">4x</div><div class="metric-label">pipeline stages where decisions are enforced vs. just CI</div>',
            '<div class="metric-value">4 stages</div><div class="metric-label">where decisions are enforced — planner, coder, reviewer, deployer</div>'
        ),
    ],
}

# ── Hub page: add intro copy above cards grid ─────────────────────────────────
HUB_INTRO = (
    '\n    <p class="hub-intro">Mneme enforces architectural, security, design, and workflow decisions '
    'wherever AI generates code or structured output. These reference architectures show how teams apply '
    'decision governance across different LLM-powered workflows.</p>'
)
HUB_INTRO_CSS = "\n    .hub-intro { font-size: 0.88rem; color: var(--muted); line-height: 1.8; max-width: 660px; margin: 0 auto; padding-bottom: 0; }"

# ── Process all case study pages ──────────────────────────────────────────────
case_studies = list(RELATED.keys())

for slug in case_studies:
    path = os.path.join(SITE, "use-cases", slug, "index.html")
    with open(path, encoding="utf-8") as f:
        html = f.read()

    html = html.replace(OLD_HERO_TAG_CSS, NEW_HERO_TAG_CSS)
    html = add_related_css(html)
    html = fix_hero_cta(html)
    html = fix_bottom_cta(html)
    html = insert_related(html, slug)

    for old, new in METRIC_PATCHES.get(slug, []):
        html = html.replace(old, new)

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  {slug}: done")

# ── Process hub page ──────────────────────────────────────────────────────────
hub_path = os.path.join(SITE, "use-cases", "index.html")
with open(hub_path, encoding="utf-8") as f:
    hub = f.read()

hub = hub.replace(
    "    footer { border-top",
    HUB_INTRO_CSS + "\n    footer { border-top"
)
hub = hub.replace(
    "\n    <div class=\"cards-grid\">",
    HUB_INTRO + "\n    <div class=\"cards-grid\">"
)

with open(hub_path, "w", encoding="utf-8") as f:
    f.write(hub)
print("  use-cases hub: done")

print("\nAll optimizations applied.")

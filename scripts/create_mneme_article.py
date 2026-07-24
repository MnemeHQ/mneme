import os
from pathlib import Path

# Load .env
_env = Path(__file__).parent.parent / '.env'
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            k, _, v = _line.partition('=')
            os.environ.setdefault(k.strip(), v.strip())

import urllib.request, urllib.parse, ssl, json

HOST = '152.89.79.37'
PORT = 2083
USER = 'cadafdd1'
TOKEN = os.environ.get('CPANEL_API_TOKEN', '')

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def cpanel_get(path):
    params = urllib.parse.urlencode({'dir': '/home/cadafdd1/public_html', 'file': path}).encode()
    req = urllib.request.Request(f'https://{HOST}:{PORT}/execute/Fileman/get_file_content', data=params, method='POST')
    req.add_header('Authorization', f'cpanel {USER}:{TOKEN}')
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return json.loads(r.read().decode())['data']['content']

def cpanel_put(path, content):
    params = urllib.parse.urlencode({'dir': '/home/cadafdd1/public_html', 'file': path, 'content': content}).encode()
    req = urllib.request.Request(f'https://{HOST}:{PORT}/execute/Fileman/save_file_content', data=params, method='POST')
    req.add_header('Authorization', f'cpanel {USER}:{TOKEN}')
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        d = json.loads(r.read().decode())
        return d.get('status') == 1

# Source the template structure from the local repo (NOT live cPanel).
#
# Why: when this script fetched `index.html` over the cPanel API, every new
# article inherited whatever HTML was live on the production server at the
# moment of generation. That created a propagation path for any CSS bug
# present on production — including the mobile-sticky-nav bug that took three
# fix attempts to land (commits e5970e2, a9d27a3, and PR #125). After this
# change, the template structure is bound to the repo's reviewed state.
_repo_index = Path(__file__).parent.parent / 'site' / 'index.html'
index = _repo_index.read_text(encoding='utf-8')

# Extract nav block
nav_start = index.find('<nav ')
nav_end = index.find('</nav>') + len('</nav>')
nav_html = index[nav_start:nav_end]

# Extract footer block
footer_start = index.find('<footer')
footer_end = index.find('</footer>') + len('</footer>')
footer_html = index[footer_start:footer_end]

# Extract <head> styles/links (everything between <head> and </head>)
head_start = index.find('<head>') + len('<head>')
head_end = index.find('</head>')
head_inner = index[head_start:head_end]

article_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Why I Built Mneme: Preventing AI Agent Architectural Drift | Theo Valmis</title>
<meta name="description" content="The problem with AI coding agents isn't intelligence — it's memory. Every session starts cold. Mneme is my answer to architectural drift in long-running AI-assisted projects." />
<meta property="og:title" content="Why I Built Mneme: Preventing AI Agent Architectural Drift" />
<meta property="og:description" content="The problem with AI coding agents isn't intelligence — it's memory. Every session starts cold. Mneme is my answer." />
<meta property="og:type" content="article" />
{head_inner}
<style>
  .article-hero {{
    background: #f9f6f0;
    padding: 80px 0 60px;
    border-bottom: 1px solid #e8e4dc;
  }}
  .article-hero .container {{ max-width: 740px; }}
  .article-category {{
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: #c1a26e;
    margin-bottom: 16px;
  }}
  .article-hero h1 {{
    font-size: 36px;
    font-weight: 800;
    color: #1a1a1a;
    line-height: 1.2;
    margin-bottom: 20px;
    letter-spacing: -0.02em;
  }}
  .article-meta {{
    font-size: 14px;
    color: #888;
  }}
  .article-body {{
    max-width: 740px;
    margin: 0 auto;
    padding: 60px 20px 80px;
    font-size: 17px;
    line-height: 1.8;
    color: #333;
  }}
  .article-body h2 {{
    font-size: 24px;
    font-weight: 700;
    color: #1a1a1a;
    margin: 48px 0 16px;
    letter-spacing: -0.01em;
  }}
  .article-body p {{ margin-bottom: 24px; }}
  .article-body blockquote {{
    border-left: 3px solid #c1a26e;
    margin: 36px 0;
    padding: 4px 0 4px 24px;
    color: #555;
    font-style: italic;
    font-size: 18px;
  }}
  .terminal-block {{
    background: #1a1a2e;
    border-radius: 8px;
    padding: 24px 28px;
    font-family: 'Courier New', monospace;
    font-size: 14px;
    line-height: 1.9;
    color: #ccc;
    margin: 32px 0;
    overflow-x: auto;
  }}
  .t-prompt {{ color: #6c63ff; }}
  .t-pass {{ color: #22c55e; }}
  .t-warn {{ color: #f59e0b; }}
  .t-fail {{ color: #ef4444; }}
  .t-muted {{ color: #666; }}
  .article-cta {{
    background: #f9f6f0;
    border-top: 1px solid #e8e4dc;
    padding: 60px 20px;
    text-align: center;
  }}
  .article-cta h3 {{
    font-size: 22px;
    font-weight: 700;
    color: #1a1a1a;
    margin-bottom: 12px;
  }}
  .article-cta p {{
    color: #666;
    margin-bottom: 24px;
    font-size: 16px;
  }}
  .btn-gold {{
    display: inline-block;
    background: #c1a26e;
    color: #fff;
    padding: 12px 28px;
    border-radius: 6px;
    font-weight: 700;
    font-size: 15px;
    text-decoration: none;
    margin: 0 6px 8px;
    transition: background 0.2s;
  }}
  .btn-gold:hover {{ background: #a8895a; color: #fff; }}
  .btn-outline-gold {{
    display: inline-block;
    border: 2px solid #c1a26e;
    color: #c1a26e;
    padding: 10px 26px;
    border-radius: 6px;
    font-weight: 700;
    font-size: 15px;
    text-decoration: none;
    margin: 0 6px 8px;
    transition: all 0.2s;
  }}
  .btn-outline-gold:hover {{ background: #c1a26e; color: #fff; }}
  @media (max-width: 768px) {{
    .article-hero h1 {{ font-size: 26px; }}
    .article-body {{ font-size: 16px; }}
  }}
</style>
</head>
<body id="page-top">

{nav_html}

<div class="article-hero">
  <div class="container">
    <p class="article-category">AI Systems &amp; Architecture</p>
    <h1>Why I Built Mneme:<br>Preventing AI Agent Architectural Drift</h1>
    <p class="article-meta">Theo Valmis &nbsp;&middot;&nbsp; April 2026 &nbsp;&middot;&nbsp; 6 min read</p>
  </div>
</div>

<div class="article-body">

<p>Every time you start a new session with an AI coding agent, it has forgotten everything. Not just the small things — the names, the syntax, the last error message. It has forgotten the decisions you made three weeks ago about why you chose Postgres over MongoDB. It has forgotten the auth pattern you locked in after a security review. It has forgotten that you explicitly ruled out a particular library because it caused problems in production.</p>

<p>The model starts cold. You start explaining. Again.</p>

<blockquote>"The problem with AI coding agents isn't intelligence. It's memory. Every session is the first session."</blockquote>

<p>I spent months working on a long-running project with AI assistants — Cursor, Claude Code, GPT-4 — and I noticed the same pattern repeating. The models were brilliant at individual tasks. But they had no continuity. No awareness of the constraints we had already resolved. No sense that this codebase had a history, a set of deliberate architectural choices, things that were decided and should stay decided.</p>

<h2>The Drift Problem</h2>

<p>I started calling it architectural drift. It happens gradually. The agent suggests a new dependency — one you already evaluated and rejected for good reason. You either catch it (friction, lost time) or you don't (technical debt, inconsistency). The agent reaches for a different database adapter because it's seen it in training more often than yours. The agent refactors a module using a pattern you explicitly moved away from six months ago.</p>

<p>None of this is the model's fault. These systems don't have access to your decision history. They can't know what you know. They see the code in front of them, not the conversation that led to it.</p>

<p>The standard advice is: put everything in your system prompt. Write a long CLAUDE.md. Add comments everywhere. Re-explain at the start of every session.</p>

<p>That's not a solution. That's manual memory management for a tool that's supposed to reduce cognitive load.</p>

<h2>What I Wanted</h2>

<p>I wanted something that would:</p>

<p><strong>Store decisions where the code lives.</strong> Not in a separate wiki. Not in a Notion database that nobody checks. Right in the repository, version-controlled, co-located with the work they govern.</p>

<p><strong>Inject those decisions automatically.</strong> Not by copying and pasting into every new chat. By having the tool surface the right constraints at the right moment — before the model has a chance to drift.</p>

<p><strong>Enforce, not just remind.</strong> A decision that can be ignored isn't a decision. It's a suggestion. I wanted something that could validate whether the current state of the codebase actually respects the decisions we've recorded — and flag the ones that don't.</p>

<h2>Building Mneme</h2>

<p>I built Mneme to solve this. The name comes from the Greek goddess of memory and remembrance — one of the original Muses. The idea is simple: your project has memory. Your AI assistant should too.</p>

<p>At its core, Mneme stores decisions in structured files that travel with your codebase:</p>

<div class="terminal-block">
<span class="t-prompt">$</span> mneme add "Use Postgres — no new databases without ADR"<br>
<span class="t-muted">Decision recorded. ID: ADR-001</span>
</div>

<p>Those decisions get committed with your code. They're in git. They're reviewable. They're auditable. When you start a new session, Mneme injects the relevant decisions into context — not all of them, just the ones that matter for what you're working on now.</p>

<p>And before you ship, you can run a pre-flight check:</p>

<div class="terminal-block">
<span class="t-prompt">$</span> mneme check --mode strict<br>
<span class="t-muted">Checking decisions against current context...</span><br>
<br>
<span class="t-pass">PASS</span>&nbsp; Storage decision enforced &mdash; Postgres locked, no new DBs<br>
<span class="t-pass">PASS</span>&nbsp; Auth pattern respected &mdash; JWT middleware unchanged<br>
<span class="t-warn">WARN</span>&nbsp; New dependency introduced &mdash; prisma not in approved list<br>
<span class="t-fail">FAIL</span>&nbsp; Violates ADR-004 &mdash; Repository pattern bypassed in user.service.ts<br>
<br>
<span class="t-muted">2 passed &middot; 1 warning &middot; 1 failure</span>
</div>

<p>PASS. WARN. FAIL. Clear signals you can act on before the model's suggestion becomes production code.</p>

<h2>Cursor and Claude Code Integration</h2>

<p>Because most AI-assisted development happens inside editors, Mneme can generate Cursor rules directly from your stored decisions:</p>

<div class="terminal-block">
<span class="t-prompt">$</span> mneme cursor generate<br>
<span class="t-muted">Generated .cursor/rules/mneme.mdc from 7 decisions</span>
</div>

<p>Those rules become editor-level guardrails. Every suggestion Cursor or Claude Code makes inside your project gets filtered through the constraints you've already established. You stop explaining. The model already knows.</p>

<h2>Why Now</h2>

<p>AI coding agents are getting better at an extraordinary rate. But the gap between what they can do in a single session and what they can maintain across a long-running project is growing, not shrinking. Better models don't fix the memory problem. Longer context windows help at the margins but don't solve continuity.</p>

<p>The projects that will get the most out of AI-assisted development aren't the ones with the best prompts. They're the ones with the best decision infrastructure — the ones where the codebase itself carries the memory of its own architectural intent.</p>

<p>That's what Mneme is for.</p>

<p>It's open source, repo-native, and CI-ready. If you're using Cursor, Claude Code, or any other AI coding tool on a project that has history — decisions made, patterns locked in, constraints established — I think you'll find it useful.</p>

</div>

<div class="article-cta">
  <div class="container">
    <h3>Try Mneme on your next project</h3>
    <p>Open source &middot; Repo-native &middot; Works with Cursor and Claude Code</p>
    <a href="https://mnemehq.com" target="_blank" rel="noopener" class="btn-gold">mnemehq.com</a>
    <a href="https://github.com/mnemeHQ/mneme" target="_blank" rel="noopener" class="btn-outline-gold"><i class="fa fa-github"></i> View on GitHub</a>
  </div>
</div>

{footer_html}

</body>
</html>
"""

ok = cpanel_put('why-i-built-mneme.html', article_html)
print('Deployed:', ok)

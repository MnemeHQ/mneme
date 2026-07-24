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

html = cpanel_get('index.html')

# 1. Meta description
html = html.replace(
    'content="Digital analytics consultant advising CMOs and CEOs on measurement strategy. 15+ years with FTSE 100 and S&P 500 brands. Founder of the Cannabis Price Index tracking 20,000+ products weekly."',
    'content="Digital Analytics, Data Infrastructure &amp; AI Systems Consultant. 15+ years with FTSE 100 and S&amp;P 500 brands. Creator of Mneme — project memory infrastructure for AI coding workflows."'
)

# 2. Page title (has replacement char from encoding)
for old_title in [
    'Theo Valmis \ufffd Cannabis Market Data & Digital Analytics Consultant',
    'Theo Valmis  Cannabis Market Data & Digital Analytics Consultant',
]:
    html = html.replace(old_title, 'Theo Valmis — Digital Analytics & AI Systems Consultant')

# 3+4. OG / Twitter tags
for old_desc in [
    'content="GA4, attribution modelling, BigQuery data pipelines, and CRO for S&P 500 and FTSE 100 brands. Founder of CannabisDealsUS and the Cannabis Price Index."',
]:
    html = html.replace(
        old_desc,
        'content="Digital Analytics, Data Infrastructure &amp; AI Systems Consulting. Creator of Mneme — decision enforcement for AI coding workflows. 15+ years with S&amp;P 500 and FTSE 100 brands."'
    )

for old_og in [
    'content="Theo Valmis \ufffd Digital Marketing Analytics Consultant"',
    'content="Theo Valmis  Digital Marketing Analytics Consultant"',
]:
    html = html.replace(old_og, 'content="Theo Valmis — Digital Analytics &amp; AI Systems Consultant"')

# 5. About paragraph
old_about = '<p id="text-aboutus">Passion in all aspects of life and logical thinking are the driving forces when problems arise and need to be solved.<br />\nStatistical analysis and the experimental method are the tools to interpret the world, fulfill ambitions and trying to predict the future in the best possible way.</p>'
new_about = (
    '<p id="text-aboutus">I build data and AI systems that improve operational reliability and decision quality.<br />'
    '\n15+ years delivering analytical rigour for S&amp;P 500 and FTSE 100 brands \xe2\x80\x94 now combining that foundation with AI infrastructure work.</p>'
    '\n<p style="margin-top:12px;">Currently building <strong><a href="https://mnemehq.com" target="_blank" rel="noopener" style="color:#c1a26e;">Mneme</a></strong> \xe2\x80\x94 a project memory and decision enforcement layer for AI coding agents, designed to prevent architectural drift and forgotten constraints in long-running software projects.</p>'
)
html = html.replace(old_about, new_about)

# 6. Bio h3
for old_bio in [
    '15+ years delivering analytical rigour for S&amp;P 500 and FTSE 100 brands. I combine measurement architecture, attribution modelling, and the experimental method to turn data into decisions \ufffd for agencies, enterprise clients, and founder-led platforms alike.',
    '15+ years delivering analytical rigour for S&amp;P 500 and FTSE 100 brands. I combine measurement architecture, attribution modelling, and the experimental method to turn data into decisions  for agencies, enterprise clients, and founder-led platforms alike.',
]:
    html = html.replace(
        f'<h3>{old_bio}</h3>',
        '<h3>15+ years delivering analytical rigour for S&amp;P 500 and FTSE 100 brands. I combine measurement architecture, attribution modelling, and AI systems design to turn data into decisions \u2014 for agencies, enterprise clients, and founder-led platforms alike. Creator of <a href="https://mnemehq.com" target="_blank" rel="noopener" style="color:#c1a26e;">Mneme</a>, decision enforcement infrastructure for AI coding workflows.</h3>'
    )

# 7. Expertise pills
html = html.replace(
    '<a class="expertise-pill">BigQuery</a>\n</div>',
    '<a class="expertise-pill">BigQuery</a>\n<a class="expertise-pill">AI Systems Design</a>\n<a class="expertise-pill">Agent Infrastructure</a>\n<a class="expertise-pill">Decision Enforcement</a>\n</div>'
)

# 8. Mneme project block
mneme_block = """<!--[Mneme Project]-->
<div class="container-fluid" style="background:#f9f6f0;padding:60px 0;">
<div class="container">
<div class="row">
<div class="col-md-12 text-center" style="margin-bottom:32px;">
<p style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:#c1a26e;margin-bottom:12px;">Current Project</p>
<h2 style="font-size:32px;font-weight:700;color:#313131;margin-bottom:8px;">Mneme &mdash; AI Decision Enforcement</h2>
<div style="border-top:2px solid #c1a26e;width:50px;margin:16px auto;"></div>
</div>
<div class="col-md-6">
<h3 style="font-size:18px;font-weight:700;color:#313131;margin-bottom:12px;">What it is</h3>
<p style="font-size:15px;color:#666;line-height:175%;margin-bottom:20px;">Mneme is a project memory and decision enforcement layer for AI coding workflows. It stores architectural decisions in your codebase and enforces them &mdash; preventing LLMs from reinventing your stack, bypassing your patterns, or ignoring constraints you have already resolved.</p>
<h3 style="font-size:18px;font-weight:700;color:#313131;margin-bottom:12px;">Why it exists</h3>
<p style="font-size:15px;color:#666;line-height:175%;">LLMs forget. Projects do not. Every session starts cold &mdash; repeating constraints, re-explaining decisions, watching the model drift. Mneme injects the right decisions at the right moment, so your AI assistant behaves like the same assistant over time.</p>
</div>
<div class="col-md-6">
<div style="background:#fff;border:1px solid #e8e8e8;border-top:3px solid #c1a26e;padding:28px 24px;margin-bottom:20px;font-family:monospace;font-size:13px;color:#333;line-height:190%;">
<span style="color:#6c63ff;">$</span> mneme check --mode strict<br/>
<span style="color:#aaa;">Checking decisions...</span><br/>
<span style="color:#22c55e;">PASS</span>&nbsp; Storage decision enforced &mdash; Postgres locked<br/>
<span style="color:#22c55e;">PASS</span>&nbsp; Auth pattern respected &mdash; JWT unchanged<br/>
<span style="color:#f59e0b;">WARN</span>&nbsp; New dependency introduced &mdash; not approved<br/>
<span style="color:#ef4444;">FAIL</span>&nbsp; Violates ADR-004 &mdash; Repository pattern bypassed
</div>
<a href="https://mnemehq.com" target="_blank" rel="noopener" class="btn btn-primary" style="margin-right:10px;">mnemehq.com</a>
<a href="https://github.com/mnemeHQ/mneme" target="_blank" rel="noopener" class="btn btn-primary"><i class="fa fa-github"></i> GitHub</a>
</div>
</div>
</div>
</div>
<!--[Mneme Project End]-->
"""
html = html.replace('<!--[Hire]-->', mneme_block + '<!--[Hire]-->')

# 9. Add Mneme to nav
html = html.replace(
    '<li><a class="page-scroll" href="Theo-Valmis-CV.pdf" target="_blank">CV</a></li>',
    '<li><a class="page-scroll" href="Theo-Valmis-CV.pdf" target="_blank">CV</a></li>\n\t<li><a href="https://mnemehq.com" target="_blank" rel="noopener" style="color:#c1a26e;font-weight:700;">Mneme</a></li>'
)

ok = cpanel_put('index.html', html)
print('Deployed:', ok)

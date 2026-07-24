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

# Add article link after the GitHub button in the Mneme block
old = '<a href="https://github.com/mnemeHQ/mneme" target="_blank" rel="noopener" class="btn btn-primary"><i class="fa fa-github"></i> GitHub</a>'
new = (
    '<a href="https://github.com/mnemeHQ/mneme" target="_blank" rel="noopener" class="btn btn-primary"><i class="fa fa-github"></i> GitHub</a>\n'
    '<br><br>\n'
    '<a href="/why-i-built-mneme.html" style="color:#c1a26e;font-size:14px;font-weight:600;">Read: Why I Built Mneme &rarr;</a>'
)
html = html.replace(old, new)

ok = cpanel_put('index.html', html)
print('Updated index:', ok)

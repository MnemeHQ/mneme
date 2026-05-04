import urllib.request, urllib.parse, ssl, json, os, subprocess
from pathlib import Path

# Load .env if present (never committed — credentials stay local)
_env = Path(__file__).parent.parent / '.env'
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            os.environ.setdefault(k.strip(), v.strip())

# ── Deploy guards ────────────────────────────────────────────────────────────
# Production deploys must originate from the canonical site working tree on
# main. Feature worktrees are never valid production deploy sources.

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_LOCAL  = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'site'))

def _git(args, cwd):
    return subprocess.check_output(['git'] + args, cwd=cwd).decode().strip()

# 1. Script repo must be on main and clean
script_branch = _git(['rev-parse', '--abbrev-ref', 'HEAD'], SCRIPT_DIR)
script_dirty  = '\n'.join(
    l for l in _git(['status', '--porcelain'], SCRIPT_DIR).splitlines()
    if not l.startswith('??')          # untracked files don't affect deploys
)
if script_branch != 'main':
    raise SystemExit(f"ERROR: repo is on '{script_branch}' — must be on main to deploy.")
if script_dirty:
    raise SystemExit(f"ERROR: working tree has uncommitted changes — commit or stash before deploying.")

# 2. site/ dir must also be on main if it is a separate git repo
try:
    site_branch = _git(['rev-parse', '--abbrev-ref', 'HEAD'], BASE_LOCAL)
    if site_branch != 'main':
        raise SystemExit(f"ERROR: site/ is on '{site_branch}' — must be on main to deploy.")
except subprocess.CalledProcessError:
    pass  # site/ is not a separate repo — fine

print(f"[OK] Branch: main  |  Clean: yes  |  Source: {BASE_LOCAL}")

# ── cPanel credentials — read from .env, never hardcoded ─────────────────────
HOST  = os.environ.get('CPANEL_HOST',  '152.89.79.37')
PORT  = os.environ.get('CPANEL_PORT',  '2083')
USER  = os.environ.get('CPANEL_USER',  'cadafdd1')
TOKEN = os.environ.get('CPANEL_API_TOKEN', '')
if not TOKEN:
    raise SystemExit('ERROR: CPANEL_API_TOKEN not set — add it to .env')
AUTH = f'cpanel {USER}:{TOKEN}'

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

BASE_REMOTE = '/home/cadafdd1/mnemehq.com'

# ── File manifest ────────────────────────────────────────────────────────────
FILES = [
    ('index.html',                                                                ''),
    ('sitemap.xml',                                                               ''),
    ('og.png',                                                                    ''),
    ('favicon.png',                                                               ''),
    ('logo-v2.png',                                                               ''),
    ('demo.html',                                                                 ''),
    (os.path.join('founder',   'index.html'),                                    'founder'),
    (os.path.join('contact',   'index.html'),                                    'contact'),
    (os.path.join('privacy',   'index.html'),                                    'privacy'),
    (os.path.join('use-cases', 'index.html'),                                    'use-cases'),
    (os.path.join('use-cases', 'coding-assistant-governance',  'index.html'),    'use-cases/coding-assistant-governance'),
    (os.path.join('use-cases', 'data-platform-governance',     'index.html'),    'use-cases/data-platform-governance'),
    (os.path.join('use-cases', 'design-system-governance',     'index.html'),    'use-cases/design-system-governance'),
    (os.path.join('use-cases', 'legacy-codebase-memory',       'index.html'),    'use-cases/legacy-codebase-memory'),
    (os.path.join('use-cases', 'multi-agent-workflow-governance', 'index.html'), 'use-cases/multi-agent-workflow-governance'),
    (os.path.join('use-cases', 'security-compliance-guardrails',  'index.html'), 'use-cases/security-compliance-guardrails'),
]

BINARY_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.svg'}

# ── Helpers ──────────────────────────────────────────────────────────────────
def mkdir(remote_path):
    parent, name = remote_path.rsplit('/', 1)
    params = {
        'cpanel_jsonapi_module': 'Fileman', 'cpanel_jsonapi_func': 'mkdir',
        'cpanel_jsonapi_version': '2', 'path': parent, 'name': name,
    }
    data = urllib.parse.urlencode(params).encode('utf-8')
    req = urllib.request.Request(
        f'https://{HOST}:{PORT}/json-api/cpanel', data=data,
        headers={'Authorization': AUTH},
    )
    with urllib.request.urlopen(req, context=ctx) as r:
        return json.loads(r.read())

def upload(local_path, remote_subdir):
    ext = os.path.splitext(local_path)[1].lower()
    is_binary = ext in BINARY_EXTS
    mode = 'rb' if is_binary else 'r'
    enc  = {} if is_binary else {'encoding': 'utf-8'}
    with open(local_path, mode, **enc) as f:
        content = f.read()
    if not is_binary:
        content = content.encode('utf-8')

    filename    = os.path.basename(local_path)
    remote_dir  = BASE_REMOTE + ('/' + remote_subdir if remote_subdir else '')
    content_type = 'image/png' if ext == '.png' else 'text/html'
    boundary    = '----MnemeDeploy2026'

    header = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="dir"\r\n\r\n{remote_dir}\r\n'
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="overwrite"\r\n\r\n1\r\n'
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file-1"; filename="{filename}"\r\n'
        f'Content-Type: {content_type}\r\n\r\n'
    ).encode('utf-8')
    body = header + content + f'\r\n--{boundary}--'.encode('utf-8')

    req = urllib.request.Request(
        f'https://{HOST}:{PORT}/execute/Fileman/upload_files', data=body,
        headers={'Authorization': AUTH, 'Content-Type': f'multipart/form-data; boundary={boundary}'},
    )
    with urllib.request.urlopen(req, context=ctx) as r:
        result = json.loads(r.read())
    ok = result.get('status') == 1 and result.get('data', {}).get('failed', 1) == 0
    return 'OK' if ok else f'FAIL: {result.get("errors", result)}'

# ── Deploy ───────────────────────────────────────────────────────────────────
for d in [
    BASE_REMOTE + '/founder',
    BASE_REMOTE + '/contact',
    BASE_REMOTE + '/privacy',
    BASE_REMOTE + '/use-cases/data-platform-governance',
    BASE_REMOTE + '/use-cases/design-system-governance',
    BASE_REMOTE + '/use-cases/multi-agent-workflow-governance',
]:
    mkdir(d)

for rel_path, subdir in FILES:
    local = os.path.normpath(os.path.join(BASE_LOCAL, rel_path))
    label = rel_path.replace(os.sep, '/')
    print(f'{label}: {upload(local, subdir)}')

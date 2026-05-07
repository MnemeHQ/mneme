import urllib.request, urllib.parse, urllib.error, ssl, json, os, subprocess, xml.etree.ElementTree as ET
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
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_LOCAL  = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'site'))

def _git(args, cwd):
    return subprocess.check_output(['git'] + args, cwd=cwd).decode().strip()

script_branch = _git(['rev-parse', '--abbrev-ref', 'HEAD'], SCRIPT_DIR)
script_dirty  = '\n'.join(
    l for l in _git(['status', '--porcelain'], SCRIPT_DIR).splitlines()
    if not l.startswith('??')
)
if script_branch != 'main':
    raise SystemExit(f"ERROR: repo is on '{script_branch}' - must be on main to deploy.")
if script_dirty:
    raise SystemExit(f"ERROR: working tree has uncommitted changes - commit or stash before deploying.")

try:
    site_branch = _git(['rev-parse', '--abbrev-ref', 'HEAD'], BASE_LOCAL)
    if site_branch != 'main':
        raise SystemExit(f"ERROR: site/ is on '{site_branch}' - must be on main to deploy.")
except subprocess.CalledProcessError:
    pass

print(f"[OK] Branch: main  |  Clean: yes  |  Source: {BASE_LOCAL}")

# ── Cloudflare credentials ───────────────────────────────────────────────────
CF_TOKEN   = os.environ.get('CF_API_TOKEN', '')
CF_ZONE_ID = os.environ.get('CF_ZONE_ID', '')

def purge_cf_cache():
    if not CF_TOKEN or not CF_ZONE_ID:
        print('[SKIP] Cloudflare cache purge - CF_API_TOKEN or CF_ZONE_ID not set')
        return
    payload = json.dumps({'purge_everything': True}).encode()
    req = urllib.request.Request(
        f'https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/purge_cache',
        data=payload,
        headers={'Authorization': f'Bearer {CF_TOKEN}', 'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req) as r:
        result = json.loads(r.read())
    if result.get('success'):
        print('[OK] Cloudflare cache purged')
    else:
        print(f'[WARN] Cloudflare purge failed: {result.get("errors")}')

# ── cPanel credentials ────────────────────────────────────────────────────────
HOST  = os.environ.get('CPANEL_HOST',  '152.89.79.37')
PORT  = os.environ.get('CPANEL_PORT',  '2083')
USER  = os.environ.get('CPANEL_USER',  'cadafdd1')
TOKEN = os.environ.get('CPANEL_API_TOKEN', '')
if not TOKEN:
    raise SystemExit('ERROR: CPANEL_API_TOKEN not set - add it to .env')
AUTH = f'cpanel {USER}:{TOKEN}'

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

BASE_REMOTE  = '/home/cadafdd1/mnemehq.com'
BINARY_EXTS  = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.svg'}

# ── Helpers ───────────────────────────────────────────────────────────────────
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
    with open(local_path, 'rb' if is_binary else 'r', **({} if is_binary else {'encoding': 'utf-8'})) as f:
        content = f.read()
    if not is_binary:
        content = content.encode('utf-8')

    filename     = os.path.basename(local_path)
    remote_dir   = BASE_REMOTE + ('/' + remote_subdir if remote_subdir else '')
    content_type = 'image/png' if ext == '.png' else 'text/html'
    boundary     = '----MnemeDeploy2026'
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

# ── Deploy: walk site/ — every file auto-included, zero manual maintenance ───
print(f"\n-- Deploying {BASE_LOCAL} -> {BASE_REMOTE} --")

# Collect dirs (sorted so parents are created before children) and files
remote_dirs = set()
files_to_upload = []
for dirpath, dirnames, filenames in os.walk(BASE_LOCAL):
    dirnames.sort()
    rel_dir = os.path.relpath(dirpath, BASE_LOCAL).replace(os.sep, '/')
    if rel_dir != '.':
        remote_dirs.add(rel_dir)
    for filename in sorted(filenames):
        local_path   = os.path.join(dirpath, filename)
        remote_subdir = '' if rel_dir == '.' else rel_dir
        label         = (rel_dir + '/' + filename) if rel_dir != '.' else filename
        files_to_upload.append((local_path, remote_subdir, label))

for d in sorted(remote_dirs):
    mkdir(BASE_REMOTE + '/' + d)

failures = []
for local_path, remote_subdir, label in files_to_upload:
    result = upload(local_path, remote_subdir)
    print(f'{label}: {result}')
    if result != 'OK':
        failures.append(label)

if failures:
    print(f"\nDEPLOY FAILED - {len(failures)} upload(s) failed:")
    for f in failures:
        print(f'  FAIL  {f}')
    raise SystemExit(1)

print(f"\n[OK] {len(files_to_upload)} files uploaded")

# ── Post-deploy verification: every sitemap URL must return 200 ───────────────
print("\n-- Post-deploy verification --")
sitemap_path = os.path.join(BASE_LOCAL, 'sitemap.xml')
tree = ET.parse(sitemap_path)
urls = [loc.text for loc in tree.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]

verify_failures = []
for url in urls:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception as e:
        status = str(e)
    ok = status == 200
    print(f'{"OK" if ok else "FAIL"}  {status}  {url}')
    if not ok:
        verify_failures.append((url, status))

if verify_failures:
    print(f"\nVERIFICATION FAILED - {len(verify_failures)} URL(s) not returning 200:")
    for url, status in verify_failures:
        print(f'  {status}  {url}')
    raise SystemExit(1)

print(f"\n[OK] All {len(urls)} sitemap URLs verified - deploy complete")

# ── Purge Cloudflare cache ────────────────────────────────────────────────────
print("\n-- Purging Cloudflare cache --")
purge_cf_cache()

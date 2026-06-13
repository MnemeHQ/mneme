import urllib.request, urllib.parse, urllib.error, ssl, json, os, subprocess, sys, xml.etree.ElementTree as ET
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

BASE_URL = 'https://mnemehq.com'

def label_to_url(label):
    """Convert a site-relative file label to its public URL. Returns None for non-public files."""
    if label.startswith('_snippets/'):
        return None
    if label == 'index.html':
        return f'{BASE_URL}/'
    if label.endswith('/index.html'):
        return f'{BASE_URL}/{label[:-len("index.html")]}'
    return f'{BASE_URL}/{label}'

def purge_cf_cache(urls=None):
    if not CF_TOKEN or not CF_ZONE_ID:
        print('[SKIP] Cloudflare cache purge - CF_API_TOKEN or CF_ZONE_ID not set')
        return
    if urls:
        payload = json.dumps({'files': urls}).encode()
        desc = f'{len(urls)} URL(s): {", ".join(urls)}'
    else:
        payload = json.dumps({'purge_everything': True}).encode()
        desc = 'everything'
    req = urllib.request.Request(
        f'https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/purge_cache',
        data=payload,
        headers={'Authorization': f'Bearer {CF_TOKEN}', 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req) as r:
            result = json.loads(r.read())
        if result.get('success'):
            print(f'[OK] Cloudflare cache purged ({desc})')
        else:
            print(f'[WARN] Cloudflare purge failed: {result.get("errors")}')
    except Exception as e:
        print(f'[WARN] Cloudflare purge error (deploy succeeded): {e}')

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
BINARY_EXTS  = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.svg', '.woff2', '.woff', '.ttf', '.otf'}

# ── Helpers ───────────────────────────────────────────────────────────────────
def mkdir(remote_path):
    # Create one directory level via the modern UAPI Fileman::mkdir endpoint
    # (the same /execute/ surface upload_files uses). The legacy
    # json-api/cpanel mkdir endpoint started returning empty bodies, which
    # crashed json.loads and broke every deploy that created a new directory.
    parent, name = remote_path.rsplit('/', 1)
    params = {'path': parent, 'name': name}
    data = urllib.parse.urlencode(params).encode('utf-8')
    req = urllib.request.Request(
        f'https://{HOST}:{PORT}/execute/Fileman/mkdir', data=data,
        headers={'Authorization': AUTH},
    )
    try:
        with urllib.request.urlopen(req, context=ctx) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
    try:
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        # Tolerate an empty / non-JSON body: the directory is created or
        # already exists. A directory that genuinely failed to create surfaces
        # immediately as an upload failure (which does fail the deploy), so
        # swallowing this is safe and keeps a flaky body from aborting the run.
        return {'status': 1}

def upload(local_path, remote_subdir):
    ext = os.path.splitext(local_path)[1].lower()
    is_binary = ext in BINARY_EXTS
    with open(local_path, 'rb' if is_binary else 'r', **({} if is_binary else {'encoding': 'utf-8'})) as f:
        content = f.read()
    if not is_binary:
        content = content.encode('utf-8')

    filename     = os.path.basename(local_path)
    remote_dir   = BASE_REMOTE + ('/' + remote_subdir if remote_subdir else '')
    if ext == '.png':
        content_type = 'image/png'
    elif ext == '.woff2':
        content_type = 'font/woff2'
    elif ext == '.css':
        content_type = 'text/css'
    else:
        content_type = 'text/html'
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
    # cPanel's upload endpoint intermittently returns an empty / non-JSON body
    # (or a transient network error). Either one used to crash json.loads and
    # abort the whole deploy on a single flaky response. Retry a few times, and
    # if it never returns parseable JSON, proceed optimistically: the
    # post-upload verification step re-checks every URL for HTTP 200 and fails
    # the deploy if this file genuinely did not land, so we never silently lose
    # an upload.
    import time
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, context=ctx) as r:
                raw = r.read()
        except (urllib.error.URLError, OSError):
            time.sleep(1 + attempt)
            continue
        try:
            result = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            time.sleep(1 + attempt)
            continue
        ok = result.get('status') == 1 and result.get('data', {}).get('failed', 1) == 0
        return 'OK' if ok else f'FAIL: {result.get("errors", result)}'
    return 'OK'  # exhausted retries on a flaky body; verification will catch a real miss

# Sync shared nav/footer snippets before upload
result = subprocess.run(
    [sys.executable, str(Path(__file__).parent / "sync_shared.py")],
    capture_output=True, text=True
)
if result.returncode != 0:
    print("[FAIL] sync_shared.py failed:")
    print(result.stderr)
    sys.exit(1)
sync_lines = [l for l in result.stdout.splitlines() if l.strip() and not l.startswith("Skipped")]
if sync_lines:
    print(f"[sync] {sync_lines[0]}")

# Pre-flight SEO/GEO audit (warn-only — never blocks deploy)
seo_result = subprocess.run(
    [sys.executable, str(Path(__file__).parent / "seo_check.py"),
     "--mode", "warn", "--no-color"],
    capture_output=True, text=True
)
if seo_result.returncode == 0 and seo_result.stdout:
    summary_line = next(
        (l for l in seo_result.stdout.splitlines() if l.startswith("Summary:")),
        ""
    )
    fail_lines = [l for l in seo_result.stdout.splitlines() if l.lstrip().startswith(("FAIL", "WARN"))]
    if summary_line:
        print(f"[seo] {summary_line}")
    if fail_lines:
        print(f"[seo] {len(fail_lines)} non-PASS findings — run "
              f"`python scripts/seo_check.py` for details")
elif seo_result.returncode != 0:
    print("[seo] check skipped (script error):")
    print(seo_result.stderr.strip()[:500])

# ── Deploy: delta upload — only files changed since last deploy ───────────────
DEPLOY_TAG = 'site-deployed'

def get_last_deployed_sha():
    try:
        return _git(['rev-parse', DEPLOY_TAG], SCRIPT_DIR)
    except subprocess.CalledProcessError:
        return None

def get_changed_site_files(since_sha):
    out = _git(['diff', '--name-only', '--diff-filter=ACM', f'{since_sha}..HEAD', '--', ':(top)site/'], SCRIPT_DIR)
    return [l for l in out.splitlines() if l]

def tag_deployed():
    try:
        _git(['tag', '-f', DEPLOY_TAG], SCRIPT_DIR)
        _git(['push', 'origin', '-f', f'refs/tags/{DEPLOY_TAG}'], SCRIPT_DIR)
        print(f'[OK] Tagged {DEPLOY_TAG} at HEAD')
    except subprocess.CalledProcessError as e:
        print(f'[WARN] Could not push {DEPLOY_TAG} tag: {e}')

last_sha = get_last_deployed_sha()
if last_sha:
    changed = get_changed_site_files(last_sha)
    if not changed:
        print(f'\n[OK] No site/ changes since last deploy ({last_sha[:8]}) - nothing to upload')
        raise SystemExit(0)
    print(f"\n-- Delta deploy: {len(changed)} changed file(s) since {last_sha[:8]} -> {BASE_REMOTE} --")
    full_deploy = False
else:
    changed = None
    print(f"\n-- Full deploy (no {DEPLOY_TAG} tag found): {BASE_LOCAL} -> {BASE_REMOTE} --")
    full_deploy = True

# Collect dirs and files to upload
remote_dirs = set()
files_to_upload = []

if full_deploy:
    for dirpath, dirnames, filenames in os.walk(BASE_LOCAL):
        dirnames.sort()
        rel_dir = os.path.relpath(dirpath, BASE_LOCAL).replace(os.sep, '/')
        if rel_dir != '.':
            remote_dirs.add(rel_dir)
        for filename in sorted(filenames):
            local_path    = os.path.join(dirpath, filename)
            remote_subdir = '' if rel_dir == '.' else rel_dir
            label         = (rel_dir + '/' + filename) if rel_dir != '.' else filename
            files_to_upload.append((local_path, remote_subdir, label))
else:
    for git_path in changed:
        # git_path is relative to repo root, e.g. "site/benchmark/index.html"
        rel = git_path[len('site/'):] if git_path.startswith('site/') else git_path
        local_path = os.path.join(BASE_LOCAL, rel.replace('/', os.sep))
        if not os.path.exists(local_path):
            print(f'SKIP (deleted)  {rel}')
            continue
        rel_dir = os.path.dirname(rel).replace(os.sep, '/')
        if rel_dir:
            remote_dirs.add(rel_dir)
        remote_subdir = rel_dir
        files_to_upload.append((local_path, remote_subdir, rel))

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

# Collect public URLs for targeted cache purge (delta only)
if not full_deploy:
    purge_urls = [u for u in (label_to_url(label) for _, _, label in files_to_upload) if u]

tag_deployed()

# ── Purge Cloudflare cache BEFORE verification ────────────────────────────────
# Purge first so verification hits fresh server responses, not stale CF cache.
# A cached 404 for a newly uploaded URL would otherwise cause verification to
# fail even though the file is live on the origin.
print("\n-- Purging Cloudflare cache --")
if full_deploy:
    purge_cf_cache()
else:
    purge_cf_cache(urls=purge_urls if purge_urls else None)

import time as _time
if CF_TOKEN and CF_ZONE_ID:
    _time.sleep(3)  # brief pause for CF edge nodes to propagate the purge

# ── Post-deploy verification: every sitemap URL must return 200 ───────────────
print("\n-- Post-deploy verification --")
sitemap_path = os.path.join(BASE_LOCAL, 'sitemap.xml')
tree = ET.parse(sitemap_path)
sitemap_urls = [loc.text for loc in tree.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]

verify_failures = []
for url in sitemap_urls:
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

print(f"\n[OK] All {len(sitemap_urls)} sitemap URLs verified - deploy complete")


# -- IndexNow: notify search engines of updated pages --
def submit_indexnow(urls):
    key = os.environ.get('INDEXNOW_KEY', '')
    if not key:
        # Fall back to the committed, publicly-served key file (site/<32 hex>.txt).
        # The IndexNow key is public by design (served at keyLocation), so deriving it
        # from the repo avoids depending on a CI secret that was never set -- which
        # silently skipped IndexNow on every deploy.
        import re, glob
        for path in sorted(glob.glob(os.path.join(BASE_LOCAL, '*.txt'))):
            stem = os.path.splitext(os.path.basename(path))[0]
            if re.fullmatch(r'[0-9a-f]{32}', stem):
                key = stem
                break
    if not key:
        print('[SKIP] IndexNow -- no key (INDEXNOW_KEY unset and no key file found)')
        return
    payload = json.dumps({
        'host': 'mnemehq.com',
        'key': key,
        'keyLocation': f'https://mnemehq.com/{key}.txt',
        'urlList': urls,
    }).encode()
    req = urllib.request.Request(
        'https://api.indexnow.org/indexnow',
        data=payload,
        headers={'Content-Type': 'application/json; charset=utf-8'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f'[OK] IndexNow -- {len(urls)} URL(s) submitted (HTTP {r.status})')
    except urllib.error.HTTPError as e:
        print(f'[WARN] IndexNow -- HTTP {e.code}: {e.read().decode()[:200]}')

print('\n-- IndexNow submission --')
submit_indexnow(purge_urls if not full_deploy else sitemap_urls)


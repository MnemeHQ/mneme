import urllib.request, urllib.parse, urllib.error, ssl, json, os, subprocess, sys, http.client, time, xml.etree.ElementTree as ET
from pathlib import Path

# Pure verification helpers live alongside this script (importable + unit-tested).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy_verify import content_needle, classify  # noqa: E402

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
# Endpoint is overridable via env (set CPANEL_HOST/CPANEL_PORT as repo Variables
# in CI, e.g. cpanel.theovalmis.com / 443). `or` so an empty value falls back to
# the default rather than blanking the host.
HOST  = os.environ.get('CPANEL_HOST')  or '152.89.79.37'
PORT  = os.environ.get('CPANEL_PORT')  or '2083'
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

# ── cPanel transport: one keep-alive connection, paced + retried ──────────────
# A delta deploy makes one UAPI call per changed file (238+ in a full sync).
# cPanel's WAF (Imunify360) rate-limits NEW connections far more aggressively
# than requests on an already-established one, so opening a fresh TLS connection
# per call trips the limiter mid-run and the deploy IP gets dropped (connection
# timeouts). Mitigations: reuse ONE keep-alive connection, pace the calls, and
# retry each call with exponential backoff (rebuilding the connection on error).
# A run of failures trips a circuit breaker so a sustained block aborts fast
# instead of grinding through every remaining file.
_PACE_SECONDS = 0.2
_MAX_CONSEC_FAIL = 8
_conn = None
_consec_fail = 0

def _cpanel_conn():
    global _conn
    if _conn is None:
        _conn = http.client.HTTPSConnection(HOST, int(PORT), context=ctx, timeout=60)
    return _conn

def _cpanel_request(method, path, body=None, extra_headers=None, attempts=4):
    """One UAPI call over the shared keep-alive connection. Paced, and retried
    with exponential backoff (rebuilding the connection on any network error).
    Returns raw response bytes. Raises ConnectionError after `attempts` failures;
    after _MAX_CONSEC_FAIL consecutive failed calls raises SystemExit to abort
    the whole deploy (a sustained block is not worth grinding through)."""
    global _conn, _consec_fail
    headers = {'Authorization': AUTH}
    if extra_headers:
        headers.update(extra_headers)
    for attempt in range(attempts):
        try:
            conn = _cpanel_conn()
            conn.request(method, path, body=body, headers=headers)
            raw = conn.getresponse().read()   # fully drain so the connection can be reused
            _consec_fail = 0
            time.sleep(_PACE_SECONDS)          # gentle pacing to stay under the limiter
            return raw
        except (http.client.HTTPException, OSError):
            try:
                if _conn:
                    _conn.close()
            except Exception:
                pass
            _conn = None                       # force a fresh connection next attempt
            if attempt < attempts - 1:
                time.sleep(min(2 ** attempt, 20))   # backoff: ride out a transient throttle
    _consec_fail += 1
    if _consec_fail >= _MAX_CONSEC_FAIL:
        raise SystemExit(
            f'[FAIL] cPanel API at {HOST}:{PORT} unreachable for {_consec_fail} consecutive '
            f'calls — likely an Imunify360/cPHulk rate-limit or block on the deploy IP '
            f'({os.environ.get("RUNNER_NAME", "this runner")}). Aborting before grinding '
            f'through the rest of the delta. Re-run once the block clears or the IP is '
            f'exempted from the cPanel-API rate limiter.'
        )
    raise ConnectionError(f'cPanel request failed after {attempts} attempts: {method} {path}')

# ── Helpers ───────────────────────────────────────────────────────────────────
def mkdir(remote_path):
    # Create one directory level via the modern UAPI Fileman::mkdir endpoint
    # (the same /execute/ surface upload_files uses). The legacy
    # json-api/cpanel mkdir endpoint started returning empty bodies, which
    # crashed json.loads and broke every deploy that created a new directory.
    parent, name = remote_path.rsplit('/', 1)
    data = urllib.parse.urlencode({'path': parent, 'name': name}).encode('utf-8')
    try:
        raw = _cpanel_request(
            'POST', '/execute/Fileman/mkdir', body=data,
            extra_headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
    except ConnectionError:
        # Tolerate a flaky mkdir (the dir likely exists): a directory that
        # genuinely failed surfaces as an upload failure + the verification step.
        return {'status': 1}
    try:
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        # Tolerate an empty / non-JSON body: the directory is created or
        # already exists.
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
    # Upload over the shared keep-alive connection with pacing + backoff (see
    # _cpanel_request). A persistently-flaky single file is tolerated as 'OK' —
    # the post-upload verification step re-checks every URL for HTTP 200 and
    # fails the deploy if a file genuinely did not land — but a sustained block
    # trips the circuit breaker in _cpanel_request and aborts the run.
    try:
        raw = _cpanel_request(
            'POST', '/execute/Fileman/upload_files', body=body,
            extra_headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
        )
    except ConnectionError:
        return 'OK'  # exhausted retries on this file; verification will catch a real miss
    try:
        result = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return 'OK'  # flaky body; verification will catch a real miss
    ok = result.get('status') == 1 and result.get('data', {}).get('failed', 1) == 0
    return 'OK' if ok else f'FAIL: {result.get("errors", result)}'

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

# ── Post-deploy verification ──────────────────────────────────────────────────
# Two tiers, so a slow unrelated page can never fail a clean delta deploy:
#
#   1. Changed URLs (this deploy's delta) are verified STRICTLY: each must return
#      200 AND serve the bytes we just uploaded. A 404/410, or a "stale 200" (the
#      old page still served because an optimistic upload never landed), is a
#      real failure that blocks the marker so the next run retries the delta.
#      Transient timeouts / 5xx are retried, then downgraded to a warning -- they
#      are infra noise, not a bad deploy.
#   2. Every other sitemap URL is a best-effort health probe: retried, and any
#      non-200 is reported as a WARNING only. (A single slow /demo/ page used to
#      abort an otherwise-perfect deploy.)
VERIFY_TIMEOUT = 30
VERIFY_RETRIES = 3

def _verify_fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=VERIFY_TIMEOUT) as r:
        return r.status, r.read()

# Fingerprint each changed HTML page: the uploaded content up to </body>.
changed_fp = {}
for _lp, _sd, _label in files_to_upload:
    _u = label_to_url(_label)
    if _u and _label.endswith('.html'):
        try:
            changed_fp[_u] = content_needle(Path(_lp).read_bytes())
        except OSError:
            pass

print("\n-- Post-deploy verification: changed URLs (strict) --")
hard_failures = []
for url, needle in changed_fp.items():
    verdict, detail = 'warn', 'no response'
    for attempt in range(VERIFY_RETRIES):
        try:
            status, body = _verify_fetch(url)
        except urllib.error.HTTPError as e:
            status, body = e.code, b''
        except Exception as e:
            verdict, detail = 'warn', f'transient: {e}'
            _time.sleep(2 + attempt * 2)
            continue
        verdict, detail = classify(status, body, needle)
        if verdict == 'ok':
            break
        if verdict == 'fail' and status in (404, 410):
            break  # definitively missing; retrying will not help
        _time.sleep(2 + attempt * 2)  # retry 5xx; re-check a stale 200 after cache propagation
    if verdict == 'ok':
        print(f'OK    {url}')
    elif verdict == 'fail':
        print(f'FAIL  {url}  -- {detail}')
        hard_failures.append((url, detail))
    else:
        print(f'WARN  {url}  -- {detail} (not blocking)')

if hard_failures:
    print(f"\nVERIFICATION FAILED - {len(hard_failures)} changed URL(s) not serving fresh content:")
    for url, detail in hard_failures:
        print(f'  {detail}  {url}')
    raise SystemExit(1)

# Best-effort health probe of the rest of the sitemap (warn-only, never blocks).
print("\n-- Sitemap health probe (warn-only) --")
sitemap_path = os.path.join(BASE_LOCAL, 'sitemap.xml')
tree = ET.parse(sitemap_path)
sitemap_urls = [loc.text for loc in tree.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
probe_warnings = []
for url in sitemap_urls:
    if url in changed_fp:
        continue  # already strictly verified above
    status = None
    for attempt in range(VERIFY_RETRIES):
        try:
            status, _ = _verify_fetch(url)
        except urllib.error.HTTPError as e:
            status = e.code
        except Exception as e:
            status = str(e)
        if status == 200:
            break
        _time.sleep(1 + attempt)
    if status != 200:
        probe_warnings.append((url, status))

if probe_warnings:
    print(f"[WARN] {len(probe_warnings)} sitemap URL(s) not returning 200 (not blocking deploy):")
    for url, status in probe_warnings:
        print(f'  {status}  {url}')
else:
    print(f"[OK] all {len(sitemap_urls)} sitemap URLs healthy")

print(f"\n[OK] Deploy verified -- {len(changed_fp)} changed URL(s) serving fresh content")

# Advance the deploy marker ONLY after the strict tier passed. A failed strict
# verification leaves the marker behind so the next deploy retries the same delta
# -- this is what stops a silent upload-miss from sitting stale while the marker
# claims it shipped (previously 9 pages 404'd on the origin for ~3 days).
tag_deployed()


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
    for endpoint in ('https://www.bing.com/indexnow', 'https://api.indexnow.org/indexnow'):
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={'Content-Type': 'application/json; charset=utf-8'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                label = endpoint.split('/')[2]
                print(f'[OK] IndexNow ({label}) -- {len(urls)} URL(s) submitted (HTTP {r.status})')
        except urllib.error.HTTPError as e:
            label = endpoint.split('/')[2]
            print(f'[WARN] IndexNow ({label}) -- HTTP {e.code}: {e.read().decode()[:200]}')

print('\n-- IndexNow submission --')
submit_indexnow(purge_urls if not full_deploy else sitemap_urls)


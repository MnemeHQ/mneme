"""Purge the entire Cloudflare cache for the mnemehq.com zone."""
import urllib.request, json, os
from pathlib import Path

_env = Path(__file__).parent.parent / '.env'
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            os.environ.setdefault(k.strip(), v.strip())

TOKEN   = os.environ.get('CF_API_TOKEN', '')
ZONE_ID = os.environ.get('CF_ZONE_ID', '')

if not TOKEN:
    raise SystemExit('ERROR: CF_API_TOKEN not set - add it to .env')
if not ZONE_ID:
    raise SystemExit('ERROR: CF_ZONE_ID not set - add it to .env')

payload = json.dumps({'purge_everything': True}).encode()
req = urllib.request.Request(
    f'https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/purge_cache',
    data=payload,
    headers={
        'Authorization': f'Bearer {TOKEN}',
        'Content-Type': 'application/json',
    },
    method='POST',
)

with urllib.request.urlopen(req) as r:
    result = json.loads(r.read())

if result.get('success'):
    print('[OK] Cloudflare cache purged')
else:
    raise SystemExit(f'ERROR: Cloudflare purge failed: {result.get("errors")}')

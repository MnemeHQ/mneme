#!/usr/bin/env python3
"""
Fix /integrations/adr-import/ WAF redirect.

Imunify360/ModSecurity flags "import" in the URL path as a SQL injection
keyword, challenges the request, then fails to redirect back (falls to /).

Strategies attempted in order:
  1. cPanel ModSecurity UAPI — list recent log entries (diagnostic)
  2. cPanel ModSecurity UAPI — list disableable rules
  3. cPanel ModSecurity UAPI — disable the specific rules that fire on this path
  4. Cloudflare WAF Custom Rules — skip rule for the exact path
  5. Cloudflare Page Rules — Cache Everything so origin is bypassed
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

TARGET_PATH = '/integrations/adr-import/'
CF_URL_PATTERN = 'mnemehq.com/integrations/adr-import/*'

CF_TOKEN = os.environ.get('CF_API_TOKEN', '')
CF_ZONE  = os.environ.get('CF_ZONE_ID', '')
CP_HOST  = os.environ.get('CPANEL_HOST', '152.89.79.37')
CP_PORT  = os.environ.get('CPANEL_PORT', '2083')
CP_USER  = os.environ.get('CPANEL_USER', 'cadafdd1')
CP_TOKEN = os.environ.get('CPANEL_API_TOKEN', '')

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def cp_uapi(module, func, params=None):
    qs = '&'.join(
        f'{k}={urllib.parse.quote(str(v), safe="")}'
        for k, v in (params or {}).items()
    )
    url = f'https://{CP_HOST}:{CP_PORT}/execute/{module}/{func}'
    if qs:
        url += f'?{qs}'
    req = urllib.request.Request(
        url,
        headers={'Authorization': f'cpanel {CP_USER}:{CP_TOKEN}'},
    )
    try:
        with urllib.request.urlopen(req, context=ctx) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {'error': str(e)}, e.code
    except Exception as e:
        return {'error': str(e)}, 0


def cf_req(method, path, data=None):
    req = urllib.request.Request(
        f'https://api.cloudflare.com/client/v4{path}',
        data=json.dumps(data).encode() if data else None,
        headers={
            'Authorization': f'Bearer {CF_TOKEN}',
            'Content-Type': 'application/json',
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {'error': str(e)}, e.code
    except Exception as e:
        return {'error': str(e)}, 0


wins = []
fails = []

# ── 1. cPanel: recent ModSecurity log entries (diagnostic) ───────────────────
print('=' * 60)
print('1. cPanel ModSecurity: list_log_entries (diagnostic)')
print('=' * 60)
if CP_TOKEN:
    r, s = cp_uapi('ModSecurity', 'list_log_entries')
    print(f'HTTP {s}')
    print(json.dumps(r, indent=2)[:3000])
else:
    print('[SKIP] CPANEL_API_TOKEN not set')

# ── 2. cPanel: list rules available to disable ────────────────────────────────
print()
print('=' * 60)
print('2. cPanel ModSecurity: list_rules_to_disable')
print('=' * 60)
if CP_TOKEN:
    r, s = cp_uapi('ModSecurity', 'list_rules_to_disable')
    print(f'HTTP {s}')
    rules_payload = r
    print(json.dumps(r, indent=2)[:3000])
else:
    rules_payload = {}
    print('[SKIP] CPANEL_API_TOKEN not set')

# ── 3. cPanel: disable SQL-injection rules that match "import" ────────────────
# OWASP CRS rule IDs commonly triggered by SQL keywords in URL paths:
#   942100  SQL Injection (libinjection)
#   942190  MSSQL code execution keywords
#   942200  MySQL comment / injection detection
#   942260  SQL auth bypass
#   942430  SQL character anomaly
#   949110  Inbound anomaly score exceeded (blocking rule)
SQL_INJECTION_RULE_IDS = [942100, 942190, 942200, 942260, 942430, 949110]

print()
print('=' * 60)
print('3. cPanel ModSecurity: disable_rule for SQL injection rules')
print('=' * 60)
if CP_TOKEN:
    # Find which of the known IDs are in the disableable list
    disableable = set()
    if isinstance(rules_payload, dict):
        for item in rules_payload.get('data', rules_payload.get('result', [])):
            rid = item.get('id') or item.get('rule_id')
            if rid:
                try:
                    disableable.add(int(rid))
                except ValueError:
                    pass

    if disableable:
        print(f'Disableable rule IDs found: {sorted(disableable)}')
        targets = disableable & set(SQL_INJECTION_RULE_IDS)
        print(f'SQL injection rules to disable: {sorted(targets)}')
        for rid in sorted(targets):
            r2, s2 = cp_uapi('ModSecurity', 'disable_rule', {'rule_id': rid})
            print(f'  disable_rule({rid}): HTTP {s2} → {r2}')
            if s2 == 200 and r2.get('status') == 1:
                wins.append(f'cPanel disable_rule({rid})')
            else:
                fails.append(f'cPanel disable_rule({rid})')
    else:
        print('No disableable rules listed — trying disable_rule directly by known IDs')
        for rid in SQL_INJECTION_RULE_IDS:
            r2, s2 = cp_uapi('ModSecurity', 'disable_rule', {'rule_id': rid})
            print(f'  disable_rule({rid}): HTTP {s2} → {r2}')
            if s2 == 200 and r2.get('status') == 1:
                wins.append(f'cPanel disable_rule({rid})')
else:
    print('[SKIP] CPANEL_API_TOKEN not set')
    fails.append('cPanel disable_rule')

# ── 4. Cloudflare: WAF Custom Rules — skip for exact path ────────────────────
print()
print('=' * 60)
print('4. Cloudflare: WAF Custom Rule (skip) for exact path')
print('=' * 60)
if CF_TOKEN and CF_ZONE:
    r, s = cf_req(
        'GET',
        f'/zones/{CF_ZONE}/rulesets/phases/http_request_firewall_custom/entrypoint',
    )
    print(f'GET entrypoint: HTTP {s}')
    skip_rule = {
        'action': 'skip',
        'action_parameters': {'ruleset': 'current'},
        'expression': f'http.request.uri.path eq "{TARGET_PATH}"',
        'description': 'Skip WAF for /integrations/adr-import/ (false positive on "import")',
        'enabled': True,
    }
    if s == 200 and r.get('success'):
        ruleset_id = r['result']['id']
        existing = r['result'].get('rules', [])
        already = any(
            rule.get('expression', '') == skip_rule['expression']
            for rule in existing
        )
        if already:
            print('Skip rule already exists — nothing to add.')
            wins.append('CF WAF skip (already present)')
        else:
            r2, s2 = cf_req(
                'PUT',
                f'/zones/{CF_ZONE}/rulesets/{ruleset_id}',
                {'rules': [skip_rule] + existing},
            )
            print(f'PUT ruleset: HTTP {s2}')
            print(json.dumps(r2, indent=2)[:1000])
            (wins if r2.get('success') else fails).append('CF WAF skip rule')
    elif s == 404:
        r2, s2 = cf_req('POST', f'/zones/{CF_ZONE}/rulesets', {
            'name': 'WAF Custom Rules',
            'kind': 'zone',
            'phase': 'http_request_firewall_custom',
            'rules': [skip_rule],
        })
        print(f'POST ruleset: HTTP {s2}')
        print(json.dumps(r2, indent=2)[:1000])
        (wins if r2.get('success') else fails).append('CF WAF skip rule')
    else:
        print(f'Unexpected response: {json.dumps(r, indent=2)[:500]}')
        fails.append('CF WAF skip rule')
else:
    print('[SKIP] CF credentials not set')

# ── 5. Cloudflare: Page Rule — Cache Everything ───────────────────────────────
print()
print('=' * 60)
print('5. Cloudflare: Page Rule (Cache Everything)')
print('=' * 60)
if CF_TOKEN and CF_ZONE:
    r, s = cf_req('POST', f'/zones/{CF_ZONE}/pagerules', {
        'targets': [{
            'target': 'url',
            'constraint': {'operator': 'matches', 'value': CF_URL_PATTERN},
        }],
        'actions': [
            {'id': 'cache_level', 'value': 'cache_everything'},
            {'id': 'edge_cache_ttl', 'value': 7200},
        ],
        'status': 'active',
        'priority': 1,
    })
    print(f'HTTP {s}')
    print(json.dumps(r, indent=2)[:1000])
    if r.get('success'):
        wins.append('CF Page Rule (Cache Everything)')
    elif s == 400 and any(
        'already exists' in str(e) or 'duplicate' in str(e).lower()
        for e in r.get('errors', [])
    ):
        print('Page Rule already exists.')
        wins.append('CF Page Rule (already present)')
    else:
        fails.append('CF Page Rule')
else:
    print('[SKIP] CF credentials not set')

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print('=' * 60)
print('SUMMARY')
print('=' * 60)
for name in wins:
    print(f'  OK    {name}')
for name in fails:
    print(f'  FAIL  {name}')

if not wins:
    print('\nAll strategies failed. Check token permissions.')
    sys.exit(1)

print(f'\n{len(wins)} strategy/strategies succeeded.')

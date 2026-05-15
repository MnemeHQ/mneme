#!/usr/bin/env python3
"""
Fetch Google PageSpeed Insights scores for mnemehq.com pages and load
results into BigQuery (mneme-hq-prod.analytics_raw.pagespeed).

The table is created on first run. Subsequent runs append rows so you
get a time-series view of Core Web Vitals.

Usage:
    python scripts/pagespeed_to_bq.py                   # all site pages
    python scripts/pagespeed_to_bq.py --url /insights/  # single URL prefix
    python scripts/pagespeed_to_bq.py --dry-run          # print JSON, skip BQ

Env vars (can also be in .env):
    MNEME_BQ_PROJECT                  default: mneme-hq-prod
    MNEME_BQ_LOCATION                 default: US
    MNEME_GOOGLE_APPLICATION_CREDENTIALS
    PAGESPEED_API_KEY                 Google PageSpeed Insights API key
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "site"
BASE_URL = "https://mnemehq.com/"
PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
DATASET = "analytics_raw"
TABLE = "pagespeed"
STRATEGIES = ("mobile", "desktop")

# Metrics extracted from the Lighthouse audit results
METRIC_KEYS = {
    "first-contentful-paint": "fcp_ms",
    "largest-contentful-paint": "lcp_ms",
    "total-blocking-time": "tbt_ms",
    "cumulative-layout-shift": "cls",
    "speed-index": "speed_index_ms",
    "interactive": "tti_ms",
}


def load_env():
    env_path = REPO / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


def collect_urls(prefix_filter: str | None) -> list[str]:
    urls: list[str] = []
    skip = {"privacy/index.html", "contact/index.html", "404.html"}
    for p in sorted(SITE.rglob("index.html")):
        rel = p.relative_to(SITE).as_posix()
        if rel in skip:
            continue
        if p.name.startswith("og-"):
            continue
        url = BASE_URL + rel.removesuffix("index.html")
        if prefix_filter and not url.startswith(BASE_URL.rstrip("/") + prefix_filter):
            continue
        urls.append(url)
    return urls


def fetch_psi(url: str, strategy: str, api_key: str) -> dict:
    params = urllib.parse.urlencode({
        "url": url,
        "strategy": strategy,
        "key": api_key,
        "category": "performance",
    })
    req_url = f"{PSI_ENDPOINT}?{params}"
    with urllib.request.urlopen(req_url, timeout=60) as resp:
        return json.loads(resp.read())


def extract_row(psi: dict, url: str, strategy: str, fetched_at: str) -> dict:
    cats = psi.get("lighthouseResult", {}).get("categories", {})
    perf_score = cats.get("performance", {}).get("score")
    audits = psi.get("lighthouseResult", {}).get("audits", {})

    row: dict = {
        "fetched_at": fetched_at,
        "url": url,
        "strategy": strategy,
        "performance_score": round(perf_score * 100) if perf_score is not None else None,
    }
    for audit_key, col in METRIC_KEYS.items():
        val = audits.get(audit_key, {}).get("numericValue")
        row[col] = round(val, 3) if val is not None else None

    # CrUX field data (real-user metrics), if available
    crux = psi.get("loadingExperience", {}).get("metrics", {})
    row["crux_lcp_ms"] = _crux_p75(crux, "LARGEST_CONTENTFUL_PAINT_MS")
    row["crux_fid_ms"] = _crux_p75(crux, "FIRST_INPUT_DELAY_MS")
    row["crux_cls"] = _crux_p75(crux, "CUMULATIVE_LAYOUT_SHIFT_SCORE")
    row["crux_inp_ms"] = _crux_p75(crux, "INTERACTION_TO_NEXT_PAINT")

    return row


def _crux_p75(metrics: dict, key: str) -> float | None:
    bucket = metrics.get(key, {}).get("percentile")
    if bucket is None:
        return None
    return round(bucket / 1000 if key.endswith("_MS") else bucket / 100, 3)


def bq_schema():
    from google.cloud import bigquery as bq
    F = bq.SchemaField
    return [
        F("fetched_at", "TIMESTAMP"),
        F("url", "STRING"),
        F("strategy", "STRING"),
        F("performance_score", "INTEGER"),
        F("fcp_ms", "FLOAT"),
        F("lcp_ms", "FLOAT"),
        F("tbt_ms", "FLOAT"),
        F("cls", "FLOAT"),
        F("speed_index_ms", "FLOAT"),
        F("tti_ms", "FLOAT"),
        F("crux_lcp_ms", "FLOAT"),
        F("crux_fid_ms", "FLOAT"),
        F("crux_cls", "FLOAT"),
        F("crux_inp_ms", "FLOAT"),
    ]


def ensure_table(client, project: str, location: str):
    from google.cloud import bigquery as bq
    from google.api_core.exceptions import NotFound

    dataset_ref = client.dataset(DATASET)
    table_ref = dataset_ref.table(TABLE)
    try:
        client.get_table(table_ref)
    except NotFound:
        table = bq.Table(f"{project}.{DATASET}.{TABLE}", schema=bq_schema())
        table.time_partitioning = bq.TimePartitioning(field="fetched_at")
        client.create_table(table)
        print(f"Created table {project}.{DATASET}.{TABLE}")


def main():
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="Filter: only pages whose URL starts with this path prefix (e.g. /insights/)")
    ap.add_argument("--dry-run", action="store_true", help="Print rows as JSON; skip BigQuery write")
    ap.add_argument("--delay", type=float, default=1.5, help="Seconds between API calls (default 1.5)")
    args = ap.parse_args()

    api_key = os.environ.get("PAGESPEED_API_KEY")
    if not api_key:
        print("FAIL: PAGESPEED_API_KEY not set")
        sys.exit(1)

    urls = collect_urls(args.url)
    if not urls:
        print("No pages found.")
        sys.exit(0)

    print(f"Pages  : {len(urls)}")
    print(f"Runs   : {len(urls) * len(STRATEGIES)} (mobile + desktop each)")

    if not args.dry_run:
        project = os.environ.get("MNEME_BQ_PROJECT", "mneme-hq-prod")
        location = os.environ.get("MNEME_BQ_LOCATION", "US")
        key_file = os.environ.get("MNEME_GOOGLE_APPLICATION_CREDENTIALS")
        if not key_file or not Path(key_file).exists():
            print(f"FAIL: BQ credentials not found: {key_file}")
            sys.exit(1)
        try:
            from google.oauth2 import service_account
            from google.cloud import bigquery
        except ImportError:
            print("FAIL: pip install google-cloud-bigquery")
            sys.exit(1)
        creds = service_account.Credentials.from_service_account_file(key_file)
        client = bigquery.Client(project=project, credentials=creds, location=location)
        ensure_table(client, project, location)

    rows: list[dict] = []
    fetched_at = datetime.datetime.utcnow().isoformat() + "Z"
    errors = 0

    for url in urls:
        for strategy in STRATEGIES:
            print(f"  {strategy:7}  {url}", end="", flush=True)
            try:
                psi = fetch_psi(url, strategy, api_key)
                row = extract_row(psi, url, strategy, fetched_at)
                rows.append(row)
                score = row.get("performance_score")
                print(f"  score={score}")
            except Exception as exc:
                print(f"  ERROR: {exc}")
                errors += 1
            time.sleep(args.delay)

    if args.dry_run:
        print(json.dumps(rows, indent=2))
        return

    if rows:
        table_id = f"{project}.{DATASET}.{TABLE}"
        errs = client.insert_rows_json(table_id, rows)
        if errs:
            print(f"BQ insert errors: {errs}")
            sys.exit(1)
        print(f"\nInserted {len(rows)} rows into {table_id}")

    if errors:
        print(f"\n{errors} fetch error(s) — check output above")
        sys.exit(1)


if __name__ == "__main__":
    main()

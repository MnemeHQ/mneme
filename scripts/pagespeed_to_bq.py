#!/usr/bin/env python3
"""
Fetch Google PageSpeed Insights scores for mnemehq.com pages and load
results into BigQuery (mneme-hq-prod.analytics_raw.pagespeed).

The table is created on first run. Subsequent runs append rows so you
get a time-series view of Core Web Vitals.

Each (url, strategy) is measured RUNS times and the median of each metric is
stored. A single Lighthouse run has very high LCP variance — re-measuring the
same unchanged page can swing the performance score by 30+ points, which reads
as a regression that never happened. The median across runs is what makes a
per-page number trustworthy enough to act on; `runs`, `performance_score_min`
and `performance_score_max` record the observed spread so noise stays visible
rather than being silently averaged away.

Usage:
    python scripts/pagespeed_to_bq.py                   # all site pages
    python scripts/pagespeed_to_bq.py --url /insights/  # single URL prefix
    python scripts/pagespeed_to_bq.py --runs 5           # more runs, tighter median
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
import statistics
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
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


def fetch_psi(url: str, strategy: str, api_key: str, attempts: int = 3) -> dict:
    """One PSI call. PSI intermittently returns 500s and read timeouts under load;
    those are transient and retrying the same URL succeeds."""
    params = urllib.parse.urlencode({
        "url": url,
        "strategy": strategy,
        "key": api_key,
        "category": "performance",
    })
    req_url = f"{PSI_ENDPOINT}?{params}"
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req_url, timeout=90) as resp:
                return json.loads(resp.read())
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(3 * 2 ** attempt)  # 3s, 6s
    raise last_exc  # type: ignore[misc]


def extract_metrics(psi: dict) -> dict:
    """Pull the metrics of a single PSI run into a flat dict."""
    cats = psi.get("lighthouseResult", {}).get("categories", {})
    perf_score = cats.get("performance", {}).get("score")
    audits = psi.get("lighthouseResult", {}).get("audits", {})

    m: dict = {
        "performance_score": round(perf_score * 100) if perf_score is not None else None,
    }
    for audit_key, col in METRIC_KEYS.items():
        val = audits.get(audit_key, {}).get("numericValue")
        m[col] = round(val, 3) if val is not None else None

    # CrUX field data (real-user metrics). Only present for URLs with enough
    # real traffic to form a CrUX sample; low-traffic pages return nothing.
    crux = psi.get("loadingExperience", {}).get("metrics", {})
    m["crux_lcp_ms"] = _crux_p75(crux, "LARGEST_CONTENTFUL_PAINT_MS")
    m["crux_fid_ms"] = _crux_p75(crux, "FIRST_INPUT_DELAY_MS")
    m["crux_cls"] = _crux_p75(crux, "CUMULATIVE_LAYOUT_SHIFT_SCORE")
    m["crux_inp_ms"] = _crux_p75(crux, "INTERACTION_TO_NEXT_PAINT")
    return m


def _median(values: list) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return statistics.median(present)


def build_row(samples: list[dict], url: str, strategy: str, fetched_at: str) -> dict:
    """Collapse N runs into one row of medians, keeping the score spread visible."""
    row: dict = {
        "fetched_at": fetched_at,
        "url": url,
        "strategy": strategy,
        "runs": len(samples),
    }

    scores = [s["performance_score"] for s in samples if s["performance_score"] is not None]
    med = _median([s["performance_score"] for s in samples])
    row["performance_score"] = round(med) if med is not None else None
    row["performance_score_min"] = min(scores) if scores else None
    row["performance_score_max"] = max(scores) if scores else None

    for col in list(METRIC_KEYS.values()) + ["crux_lcp_ms", "crux_fid_ms", "crux_cls", "crux_inp_ms"]:
        med = _median([s[col] for s in samples])
        row[col] = round(med, 3) if med is not None else None

    return row


def measure(url: str, strategy: str, api_key: str, runs: int, delay: float,
            fetched_at: str) -> dict:
    """Measure one (url, strategy) `runs` times and return a median row."""
    samples = []
    for i in range(runs):
        samples.append(extract_metrics(fetch_psi(url, strategy, api_key)))
        if i < runs - 1:
            time.sleep(delay)
    return build_row(samples, url, strategy, fetched_at)


def _crux_p75(metrics: dict, key: str) -> float | None:
    """CrUX p75 for one metric.

    CrUX reports timing percentiles already in milliseconds, so they are stored
    as-is. Only CLS needs scaling: its percentile is reported x100 (10 -> 0.10).
    """
    bucket = metrics.get(key, {}).get("percentile")
    if bucket is None:
        return None
    if key == "CUMULATIVE_LAYOUT_SHIFT_SCORE":
        return round(bucket / 100, 3)
    return round(float(bucket), 3)


def bq_schema():
    from google.cloud import bigquery as bq
    F = bq.SchemaField
    return [
        F("fetched_at", "TIMESTAMP"),
        F("url", "STRING"),
        F("strategy", "STRING"),
        F("performance_score", "INTEGER"),
        F("performance_score_min", "INTEGER"),
        F("performance_score_max", "INTEGER"),
        F("runs", "INTEGER"),
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
        table = client.get_table(table_ref)
    except NotFound:
        table = bq.Table(f"{project}.{DATASET}.{TABLE}", schema=bq_schema())
        table.time_partitioning = bq.TimePartitioning(field="fetched_at")
        client.create_table(table)
        print(f"Created table {project}.{DATASET}.{TABLE}")
        return

    # Additive migration: rows written before multi-run sampling lack these
    # columns. Appending NULLABLE fields leaves existing rows untouched.
    existing = {f.name for f in table.schema}
    missing = [f for f in bq_schema() if f.name not in existing]
    if missing:
        table.schema = list(table.schema) + missing
        client.update_table(table, ["schema"])
        print(f"Added columns: {', '.join(f.name for f in missing)}")


def main():
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="Filter: only pages whose URL starts with this path prefix (e.g. /insights/)")
    ap.add_argument("--dry-run", action="store_true", help="Print rows as JSON; skip BigQuery write")
    ap.add_argument("--delay", type=float, default=1.5, help="Seconds between API calls (default 1.5)")
    ap.add_argument("--runs", type=int, default=3,
                    help="PSI runs per url+strategy; the median is stored (default 3)")
    ap.add_argument("--workers", type=int, default=6,
                    help="Concurrent url+strategy measurements (default 6)")
    ap.add_argument("--max-error-pct", type=float, default=5.0,
                    help="Fail the run only if more than this %% of measurements error (default 5)")
    args = ap.parse_args()

    if args.runs < 1:
        print("FAIL: --runs must be >= 1")
        sys.exit(1)

    api_key = os.environ.get("PAGESPEED_API_KEY")
    if not api_key:
        print("FAIL: PAGESPEED_API_KEY not set")
        sys.exit(1)

    urls = collect_urls(args.url)
    if not urls:
        print("No pages found.")
        sys.exit(0)

    tasks = [(url, strategy) for url in urls for strategy in STRATEGIES]
    print(f"Pages  : {len(urls)}")
    print(f"Runs   : {len(tasks) * args.runs} "
          f"({len(tasks)} url+strategy x {args.runs} runs, median stored)")
    print(f"Workers: {args.workers}")

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
    lock = threading.Lock()

    def run_task(task):
        nonlocal errors
        url, strategy = task
        try:
            row = measure(url, strategy, api_key, args.runs, args.delay, fetched_at)
        except Exception as exc:
            with lock:
                errors += 1
                print(f"  {strategy:7}  {url}  ERROR: {exc}", flush=True)
            return
        with lock:
            rows.append(row)
            spread = row["performance_score_max"] - row["performance_score_min"] \
                if row["performance_score_min"] is not None else 0
            print(f"  {strategy:7}  {url}  score={row['performance_score']}"
                  f" (spread {spread})", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(run_task, tasks))

    if args.dry_run:
        print(json.dumps(rows, indent=2))
        return

    if rows:
        from google.cloud import bigquery as bq

        table_id = f"{project}.{DATASET}.{TABLE}"
        # Load job, not insert_rows_json: after ensure_table() adds a column the
        # streaming buffer's schema cache lags for several minutes and rejects
        # every row with "no such field". A load job sees the new schema at once
        # (and batch appends are free).
        job = client.load_table_from_json(
            rows,
            table_id,
            job_config=bq.LoadJobConfig(
                schema=bq_schema(),
                write_disposition=bq.WriteDisposition.WRITE_APPEND,
            ),
        )
        job.result()
        if job.errors:
            print(f"BQ load errors: {job.errors}")
            sys.exit(1)
        print(f"\nLoaded {len(rows)} rows into {table_id}")

    # A handful of PSI 500s/timeouts is normal at this volume and already
    # survived retries; failing the whole run on one blip just trains everyone
    # to ignore a permanently red job. Fail only on a systemic error rate.
    if errors:
        pct = 100 * errors / len(tasks)
        print(f"\n{errors}/{len(tasks)} measurement(s) failed ({pct:.1f}%)")
        if pct > args.max_error_pct:
            print(f"FAIL: error rate above --max-error-pct ({args.max_error_pct}%)")
            sys.exit(1)


if __name__ == "__main__":
    main()

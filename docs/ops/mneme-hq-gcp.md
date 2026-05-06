# Mneme HQ — GCP / BigQuery Reference

## GCP Project

| Field | Value |
|---|---|
| Project ID | `mneme-hq-prod` |
| Project name | Mneme HQ Prod |
| Billing account | `01C41B-59FB59-15D3F8` (shared billing account with cannabisdeals; separate project) |
| Region / location | `US` |

Room left for `mneme-hq-dev` when dev/prod separation becomes worthwhile.

## Service Account

| Field | Value |
|---|---|
| Name | `mneme-hq-app` |
| Roles | `roles/bigquery.dataEditor`, `roles/bigquery.jobUser` |
| Key file location | `~/.claude/mneme-hq-bq-credentials.json` (outside repo, outside version control) |

The key lives in `~/.claude/` — outside this repo entirely. See "What must never be committed" below.

Future hardening: scope `search-console-data-export@system.gserviceaccount.com` to dataset-level access
rather than project-wide IAM.

## BigQuery Datasets

All in location `US`.

| Dataset | Purpose |
|---|---|
| `analytics_<property_id>` | GA4 daily export — auto-created by GA4, not manually managed |
| `analytics_raw` | Raw imports that are not GA4 (e.g. CSV uploads, manual exports) |
| `searchconsole` | Google Search Console bulk export |
| `growth_ops` | CRM / outreach data from mneme-growth-ops |
| `staging` | Scratch / intermediate tables |

> **Search Console dataset is ALWAYS `searchconsole`**
> GSC enforces this naming; do not attempt custom naming or suffix. The pre-created
> `search_console` dataset was deleted — do not recreate it.

`product_telemetry` is intentionally absent. Add it only after a privacy/opt-in ADR is written and approved.

## Environment Variables

Use the `MNEME_BQ_*` prefix — these coexist in the same `.env` as the unprefixed `BIGQUERY_PROJECT` /
`GOOGLE_APPLICATION_CREDENTIALS` vars borrowed from cannabisdeals-data-platform. Do not rename without
updating both files.

```env
MNEME_BQ_PROJECT=mneme-hq-prod
MNEME_BQ_LOCATION=US
MNEME_GOOGLE_APPLICATION_CREDENTIALS=~/.claude/mneme-hq-bq-credentials.json
```

See [`.env.example`](../../.env.example) for the canonical placeholder list.

## Data Export Links

### GA4 → BigQuery (daily)

Property `G-ZZ9YG12PPX` (mnemehq.com) → BigQuery link to `mneme-hq-prod`.
GA4 auto-creates a dataset named `analytics_<numeric_property_id>` on first export.
Frequency: **daily**. Streaming not enabled (cost vs. need).

Verify first run:
```bash
bq ls --project_id=mneme-hq-prod | grep analytics
```

### Search Console bulk export

Property `https://mnemehq.com/` → BigQuery dataset `mneme-hq-prod.searchconsole`.
Frequency: **daily**. Export starts within 48 h of setup; GSC creates the dataset automatically.

## Critical Rules

- Never commit `.env` or any variant (`.env.local`, `.env.prod`, etc.)
- Never commit service account JSON key files — treat them like passwords
- Never reuse cannabisdeals credentials for Mneme HQ (separate project, separate key)
- Always use `MNEME_BQ_*` env vars for this project — never the unprefixed cannabisdeals names
- Search Console dataset name is fixed: **`searchconsole`** — do not use `search_console`

## What Must Never Be Committed

| File | Why |
|---|---|
| `.env` | Contains live credentials for all projects |
| `*.json` key files | Service account private keys |
| `~/.claude/mneme-hq-bq-credentials.json` | Mneme HQ SA key |
| `~/.claude/bq-credentials.json` | CannabisDeals SA key |

Both `.env` and `.env.*` (except `.env.example`) are covered by `.gitignore`. Key files live in
`~/.claude/` which is outside this repo entirely.

If a key is accidentally committed: rotate it immediately in GCP IAM → Service Accounts → Keys,
then remove from git history with `git filter-repo`.

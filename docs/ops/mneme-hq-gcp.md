# Mneme HQ — GCP / BigQuery Reference

## GCP Project

| Field | Value |
|---|---|
| Project ID | `mneme-hq-prod` |
| Project name | Mneme HQ Prod |
| Billing account | `01C41B-59FB59-15D3F8` (shared line with cannabisdeals, separate project) |
| Region / location | `US` |
| gcloud account | `hi@theovalmis.com` |

Room left for `mneme-hq-dev` when dev/prod separation becomes worthwhile.

## Service Account

| Field | Value |
|---|---|
| Email | `mneme-hq-app@mneme-hq-prod.iam.gserviceaccount.com` |
| Roles | `roles/bigquery.dataEditor`, `roles/bigquery.jobUser` |
| Key file | `C:/Users/hi/.claude/mneme-hq-bq-credentials.json` |

The key file lives outside the repo and outside version control. See "What must never be committed" below.

## BigQuery Datasets

All in location `US`.

| Dataset | Purpose |
|---|---|
| `analytics_raw` | GA4 → BigQuery daily export landing zone |
| `searchconsole` | Google Search Console bulk export (GSC forces this prefix; suffix omitted for cleanliness) |
| `growth_ops` | CRM / outreach data from mneme-growth-ops |
| `staging` | Scratch / dbt-style intermediate tables |

`product_telemetry` is intentionally absent. Add it only after a privacy/opt-in ADR is written and approved.

## Environment Variables

Use the `MNEME_BQ_*` prefix — these coexist in the same `.env` as the unprefixed `BIGQUERY_PROJECT` / `GOOGLE_APPLICATION_CREDENTIALS` vars borrowed from cannabisdeals-data-platform. Do not rename without updating both files.

```env
MNEME_BQ_PROJECT=mneme-hq-prod
MNEME_BQ_LOCATION=US
MNEME_GOOGLE_APPLICATION_CREDENTIALS=C:/Users/hi/.claude/mneme-hq-bq-credentials.json
```

See [`.env.example`](../../.env.example) for the canonical placeholder list.

## Data Export Links

### GA4 → BigQuery (daily)

Property `G-ZZ9YG12PPX` (mnemehq.com) → BigQuery link to `mneme-hq-prod`.  
Export lands in `analytics_raw` (or an auto-created `analytics_<property_id>` dataset — check after first run).  
Frequency: **daily**. Streaming not enabled (cost vs. need).

### Search Console bulk export

Property `https://mnemehq.com/` → BigQuery export to `mneme-hq-prod.searchconsole`.  
Frequency: **daily**. GSC always prefixes the dataset with `searchconsole`; no custom suffix was added.

## What Must Never Be Committed

| File | Why |
|---|---|
| `.env` | Contains live credentials for all projects |
| `*.json` key files | Service account private keys — treat like passwords |
| `C:/Users/hi/.claude/mneme-hq-bq-credentials.json` | Mneme HQ SA key |
| `C:/Users/hi/.claude/bq-credentials.json` | CannabisDeals SA key |

Both `.env` and `.env.*` (except `.env.example`) are covered by `.gitignore`. Key files live in `~/.claude/` which is outside this repo entirely.

If a key is accidentally committed: rotate it immediately in GCP IAM → Service Accounts → Keys, then remove from git history with `git filter-repo`.

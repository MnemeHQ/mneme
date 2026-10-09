---
id: ADR-032
title: "Opt-In Product Usage Measurement"
status: accepted
priority: foundational
date: 2026-10-09
scope: product.usage_measurement
---

# ADR-032: Opt-In Product Usage Measurement

**Status:** Accepted
**Date:** 2026-10-09
**Deciders:** Theo Valmis

---

## Context

Mneme needs a trustworthy, appropriately limited answer to whether the open
source product is being used. Package-download counts do not show whether a
runtime performs a meaningful operation, and invocation counts do not identify
unique developers, organizations, production deployments, or successful
governance outcomes.

The current product has three relevant execution surfaces:

1. the `mneme` CLI, whose central `main()` dispatch is one boundary but whose
   package also exposes separate hook entry points;
2. the Decision MCP server, whose six-tool capability surface is frozen by
   ADR-027; and
3. supported agent hooks, including Claude Code, Codex CLI, and Kiro adapters.

The current GCP reference intentionally omits a `product_telemetry` dataset
until an explicit privacy and opt-in decision is accepted. ADR-029 separately
defines enforcement-evidence binding. Product usage measurement cannot satisfy
that binding contract: an invocation count neither proves which decision or
rule governed an action nor binds the subject, applicability, and outcome.

Mneme is deterministic and local-first. Measurement must therefore be an
optional boundary capability. It must not introduce a network dependency into
retrieval, rule evaluation, enforcement, Decision Index persistence, MCP
authority, Audit, hooks, benchmarks, or ordinary CLI execution.

This ADR authorizes no implementation while its status is `proposed`.

## Decision

### 1. Measurement has a narrow, non-authoritative purpose

The measurement programme may report only these product-adoption metrics:

| Metric | Definition | Priority |
|---|---|---|
| Active opt-in instances | Distinct reporting identifiers that submitted at least one allowlisted meaningful operation in one fixed 30-day identifier epoch | P0 |
| MCP tool invocations | Aggregated calls to the six ADR-027 tools, grouped by tool | P0 |
| CLI usage | Aggregated completed substantive commands, excluding help, version, parse failures, and usage-measurement administration | P0 |
| Agent hook usage | Aggregated valid invocations of supported hook entry points, grouped by adapter and hook kind | P0 |
| Repeat usage | Opt-in instances active in more than one weekly bucket within a 30-day identifier epoch | P1 |

An instance is one consenting Mneme runtime profile. It is not a verified
person, installation, machine, repository, organization, customer, or
production deployment. The collector covers only opt-in instances that submit
data. No result may be represented as total Mneme adoption.

Invocation data is an untrusted operational signal. A public anonymous
collector can be undercounted, duplicated, automated, replayed, or deliberately
spoofed. It must not drive billing, access, security, enforcement, audit tiers,
decision authority, or claims that require verified identity.

### 2. Consent is explicit, versioned, and off by default

Usage measurement is disabled unless a person explicitly enables it after
installation. Package installation, upgrade, `mneme init`, `mneme setup`, MCP
server startup, hook installation, CI setup, and first use must not enable it,
prompt for it, or send a request.

The eventual CLI control surface must provide equivalent operations to:

```text
mneme usage enable [--submission manual|weekly]
mneme usage disable
mneme usage status
mneme usage preview
mneme usage purge
mneme usage submit
```

Exact spelling is an implementation detail, but the semantics are not:

- `enable` displays the current notice and records explicit consent with its
  policy version and time; weekly submission is selected explicitly rather
  than inferred from enablement;
- `disable` takes effect before the command returns, stops new counter writes,
  makes submission ineligible, and removes any Mneme-owned schedule on a
  best-effort basis;
- `status` is local and shows consent state, policy version, retained period,
  submission mode, scheduler state, and whether unsent aggregates exist;
- `preview` is local, performs no network access, and renders the exact
  schema-valid payload(s) that `submit` would send by materializing the same
  pending snapshot(s) defined below — the preview is those bytes, not an
  approximation of them;
- `purge` deletes local aggregates, the local identifier secret, submission
  receipts, pending snapshots, and consent state; and
- `submit` is the only component permitted to use the network, operates only on
  pending snapshot(s), and must refuse when consent is disabled or stale.

Command ownership across milestones is explicit. `enable`, `disable`, `status`,
`preview`, and `purge` are U1: local-only and never networked. `submit`, and any
scheduler that invokes it, are U2: the only usage operations permitted to open a
socket and the only ones that create or depend on a collector. U1 ships no
upload code, endpoint, or network dependency even though `preview` already
renders the exact U2 payload (section 10).

Snapshot semantics keep `preview`, `submit`, and retries consistent. For each
epoch that has no pending snapshot, the first `preview` or `submit` after new
counting freezes the then-current counters into one pending snapshot. Each
snapshot fixes, at freeze time, its `schema_version`, `identifier_epoch`,
epoch-scoped `instance_id`, `aggregates[]`, and one freshly generated
`payload_id`; those bytes never change afterward.

- `preview` renders exactly those frozen bytes and consumes nothing.
- `submit` transmits them, and a retry after a timeout, lost receipt, or
  ambiguous result re-sends the identical bytes under the same `payload_id`, so
  the collector deduplicates the retry instead of counting it twice.
- A snapshot clears only on an acknowledged receipt, local `purge`, or the
  35-day local-retention limit. While one is pending, later increments for that
  epoch remain unfrozen; after the pending snapshot clears, the next `preview`
  or `submit` freezes those increments into a new snapshot with a new
  `payload_id`. At most one snapshot per epoch is pending at a time, but an
  epoch may produce multiple sequential snapshots without collision. An
  expired snapshot is deleted locally and never submitted. `preview` never
  consumes counters or changes consent or identifiers; its only write is the
  snapshot materialization required to guarantee exact preview bytes.

Consent is bound to a published privacy-policy/schema version. A material
expansion of collected fields, purpose, linkage, retention, or recipient
invalidates existing consent and returns the client to disabled until the user
opts in again. A schema migration that only removes fields or narrows retention
does not require renewed consent.

Consent is *stale* when a recorded "enabled" state is bound to a policy/schema
version older than the client's current published version, or when consent state
is missing, unreadable, or otherwise cannot be confirmed current. Staleness is
the independent check that catches an invalidating material expansion even if the
stored flag was not yet reconciled to disabled. Neither section 3 counting nor
`submit` treats stale consent as current: `submit` refuses it with a
stale-consent result and leaves counters and snapshots untouched, and the user
restores a consenting state only by re-running `enable` against the current
notice.

Environment variables and configuration-management tools may automate the
same explicit action in a later implementation, but silence, inherited package
configuration, and mere process execution are never consent. Documentation for
headless enablement must state that the operator is accepting on behalf of that
runtime profile.

Revocation stops future collection and submission. Because submitted records
carry only short-lived pseudonyms and no account identity, the service cannot
promise selective deletion of an already submitted record. Short server-side
retention is the compensating control and must be stated in the notice.

### 3. Runtime collection is local aggregation, not event logging

When consent is current, thin adapters at the existing CLI, MCP, and hook
boundaries may increment local counters. They must not emit event-per-call
records. The local representation is an aggregate keyed only by:

```text
schema_version
30_day_epoch
weekly_bucket_within_epoch
surface
allowlisted_operation
execution_context
count
```

`30_day_epoch` is the pinned UTC epoch number defined in section 4. Counters are
partitioned by it: an increment is attributed to the epoch current at increment
time and is never merged into another epoch's totals.

`weekly_bucket_within_epoch` is `floor(day_within_epoch / 7)`, where
`day_within_epoch` is the whole number of UTC days since the epoch began. A
30-day epoch has five buckets: `0`–`3` are full seven-day weeks (days 0–6, 7–13,
14–20, 21–27) and `4` is the incomplete two-day remainder (days 28–29). Bucket
`4` is a first-class bucket for the repeat-usage metric even though it is
shorter; its brevity is a known, documented skew, not an error.

`execution_context` is one of `interactive`, `ci`, or `unknown`. It is derived
locally from whether a standard CI marker is present; marker names and values
are never stored or submitted. This dimension exists only to quantify likely
CI inflation.

The operation vocabulary is a closed, versioned enum. It may include:

- normalized substantive CLI command identifiers;
- the six exact ADR-027 MCP tool names; and
- normalized supported adapter/hook identifiers.

Arguments, inputs, outputs, verdicts, errors, durations, decision identifiers,
rule identifiers, repository identity, and exception payloads are not part of
the enum. Unknown operations are ignored locally, not serialized under their
raw names. Adding an operation name requires schema review; it does not happen
by passing an arbitrary string to the adapter.

A CLI counter is incremented only after dispatch to a recognized substantive
command and after its intended result and exit code have been finalized. An MCP
counter is incremented only after a recognized tool call has produced its
protocol response. A hook counter is incremented only after valid hook input
has produced the adapter response. Counting does not record whether an
enforcement result was allow, warn, reject, error, or not applicable.

Instrumentation coverage is exact and limited to these three boundaries. CLI
counting wraps the `main()` dispatch and does not observe the separately exposed
hook entry points; those entry points are counted once at the hook-adapter
boundary, so the two console entry-point families named in Context are each
covered exactly once with no double counting and no gap. MCP counting wraps the
six ADR-027 tool handlers. No other call site — library imports, internal
helpers, retries inside a single call, or benchmark/research entry points —
increments a product counter.

Help, version, usage-administration commands, parser failures, and server
startup are excluded. Benchmark and research harness operations must be
reported separately from product operations and must not qualify an instance
as product-active. This prevents the measurement and its own validation work
from manufacturing the headline adoption metric.

Local counter state has a maximum age of 35 days. A successful acknowledged
submission may remove the submitted counters immediately. Local state writes
use an implementation-owned user data directory, never the repository,
`.mneme/project_memory.json`, the Decision Index, or an ADR tree.

### 4. The instance identifier is pseudonymous and expires

On `enable`, the client generates a cryptographically random 256-bit local
secret. The secret is never transmitted and is the HMAC key below.

The 30-day epoch is pinned to UTC with a fixed origin. Epoch zero begins at the
Unix time origin `1970-01-01T00:00:00Z`; the current epoch number is
`floor(unix_seconds / (30 * 86400))` evaluated in UTC, independent of local time
zone, daylight saving, and host locale. Every client computes the same epoch
number for the same instant, so no client-supplied origin is transmitted and the
collector validates epochs against its own clock.

For each such epoch the client derives the reporting identifier as an HMAC,
keyed by the local secret, over a versioned domain separator and that epoch
number, truncating only after preserving at least 128 bits of output.

The resulting identifier:

- is stable only within that 30-day epoch;
- changes at the epoch boundary;
- cannot be linked across epochs by the collector from identifier material;
- changes immediately after `purge` followed by a new `enable`; and
- represents a runtime profile, not a natural person or organization.

No hardware identifier, hostname, username, account id, email, IP-derived id,
repository id, installation path, package-manager id, or advertising id may be
used to construct or supplement it.

The fixed-epoch boundary can slightly overcount a rolling 30-day view near a
rotation. Therefore the canonical P0 metric is fixed-epoch active instances,
not an exact rolling-30-day unique count. Any rolling estimate must disclose
the boundary error and must not attempt cross-epoch identity linkage.

### 5. The payload allowlist is minimal and closed

The submission payload contains only:

```text
schema_version
payload_id
identifier_epoch
instance_id
mneme_major_minor_version
aggregates[]:
  weekly_bucket
  surface
  operation
  execution_context
  count
```

A payload reports exactly one identifier epoch: `identifier_epoch` is the pinned
UTC epoch number, `instance_id` is that epoch's derived identifier, and every row
in `aggregates[]` belongs to that same epoch. Counters from two epochs are never
combined in one payload. A client holding unsent counters from more than one
epoch — for example a retained prior epoch and the current one — emits one
independent payload per epoch, each with its own epoch-scoped `instance_id` and
its own `payload_id`, so the collector cannot link them from payload material.
The contract is one identifier epoch per payload. An epoch may produce multiple
sequential payloads as new counters accrue after earlier snapshots are
acknowledged; a payload never spans epochs.

`payload_id` is an idempotency key for retry safety, not a durable instance
identity. It is bound to one counter snapshot (section 2): a given snapshot keeps
one `payload_id` across every retry, and two distinct snapshots in the same epoch
— for example an earlier manual submission and a later one covering newer
counters — carry different `payload_id`s, so the collector records them as
separate reports instead of deduplicating one away. `mneme_major_minor_version`
omits the patch/build version. Counts are non-negative bounded integers. Weekly
buckets are coarse positions inside the identifier epoch, not event timestamps.

The following are prohibited in local measurement state and submitted payloads:

- source code, prompts, queries, command arguments, standard input, standard
  output, or MCP/hook request and response bodies;
- file names, paths, working directories, repository URLs, remote names,
  branches, commit ids, or project-memory content;
- ADR text, titles, scopes, decision ids, version ids, rule ids, selectors,
  verdicts, violations, or enforcement traces;
- user, account, organization, device, host, advertising, or stable
  cross-epoch identifiers;
- credentials, environment-variable names or values, configuration values,
  IP addresses, user-agent details, stack traces, raw exceptions, and
  free-form strings; and
- timing, latency, or event-level timestamps.

The client serializer and collector both reject extra or unknown fields. The
collector does not silently discard them and accept the rest of a payload.

### 6. Submission is out of process from Mneme operations

`mneme usage submit` is the only network-capable component. A separately
installed schedule may invoke that command, but CLI product commands,
MCP handlers, MCP server startup, hooks, enforcement, Audit, Decision Index
operations, and benchmark/research execution never call the collector, perform
DNS resolution for it, wait for it, or spawn a reporter.

Scheduling is not part of U1. U2 may install an out-of-process weekly schedule
only when `weekly` submission was explicitly selected. The U2 implementation
plan must name supported operating systems, use native user-level scheduling,
make installation/removal observable through `status`, and prove that a stale
job re-checks current consent before opening a socket. Where a scheduler is not
supported, submission remains manual. The collector therefore measures
submitting opt-in profiles, not every locally enabled profile.

Submission is best-effort and bounded by short connect and total timeouts. A
timeout, DNS failure, TLS failure, server error, invalid receipt, corrupt local
state, unwritable counter store, or unavailable lock must never change an
operational command's output, exit code, MCP response, hook response,
enforcement verdict, Audit result, Decision Index state, or benchmark artifact.
The explicit `usage submit` command may itself return a submission-specific
failure because submission is its requested operation.

### 7. The collector is a separate, write-only operational boundary

The collector is not the Decision Index, proposal store, project memory,
enforcement-evidence store, Audit store, or benchmark store. It exposes one
versioned HTTPS ingestion route and no public query route.

The collector must:

- enforce TLS;
- reject bodies above a small documented maximum;
- validate the closed schema and enum values before any write;
- reject unknown fields, invalid epochs, future buckets, and out-of-range
  counts;
- deduplicate retries by `payload_id` within retention;
- rate-limit abusive sources without adding a durable source identifier;
- use a fixed, non-identifying client user agent;
- keep request bodies out of application and infrastructure logs; and
- return only a minimal receipt.

Anonymous reports are not cryptographically proof of real use. Rate limiting,
idempotency, bounded counts, and anomaly flags protect operations and improve
quality; they do not turn the metric into verified identity.

### 8. Storage is isolated, short-lived, and non-linkable

After this ADR is accepted and only during U2, infrastructure may create a
dedicated `product_telemetry` dataset and a dedicated least-privilege collector
identity. Existing Mneme application, analytics, Search Console, and growth
service accounts must not receive write access by default.

The storage contract is:

- accepted pseudonymous payload rows: maximum 35 days;
- idempotency receipts: maximum 35 days;
- security/access logs that may contain a source IP at the managed ingress:
  maximum 7 days, access-restricted, no request body, and not copied into
  `product_telemetry`;
- aggregate tables with all instance and payload identifiers removed: maximum
  13 months; and
- backups and temporary tables: no longer than the source class they copy.

The application must not read, derive, store, hash, truncate, enrich, or export
the source IP. Managed ingress behavior and log retention must be verified
before the first external report is accepted. If the platform cannot meet the
seven-day IP-log limit, U2 remains blocked pending a revised privacy decision.

The dataset must not be joined at instance or request level to GA4, Search
Console, `growth_ops`, CRM, package-download, account, support, outreach, or
repository data. Derived public or internal reporting uses aggregate groups
large enough to avoid singling out one reporting instance. Small cells are
suppressed under a documented threshold selected during U2 privacy review.

### 9. Usage measurement is not enforcement evidence

Nothing in local counters, a submitted payload, a collector receipt, or an
aggregate report satisfies ADR-029. Usage measurement does not bind a decision,
rule, subject, applicability result, configuration, or enforcement outcome.

Measurement adapters must not be inserted into `DecisionRetriever`,
`ConflictDetector`, deterministic rule evaluation, Decision Index persistence,
proposal authority, Audit tier computation, enforcement evidence, or benchmark
scoring. The Decision MCP surface remains exactly the six ADR-027 tools; no
seventh telemetry or usage tool is added.

### 10. Delivery is gated in four milestones

| Milestone | Permitted scope | Exit gate |
|---|---|---|
| U0 — architecture and privacy | This ADR and privacy review only | ADR accepted with named owners for privacy, security, and data retention |
| U1 — local counters | Consent controls, closed enums, local aggregation, preview/purge; no upload code or network dependency | Tests prove default-off behavior, zero unconsented writes/egress, bounded retention, and byte-for-byte operational equivalence |
| U2 — collection | Explicit submit command, optional explicitly selected out-of-process weekly schedule, minimal receiver, isolated storage, aggregate reporting | Threat/privacy review, scheduler lifecycle tests, infrastructure-log verification, strict-payload tests, abuse controls, and real end-to-end tests pass |
| U3 — measurement validation | Metric reconciliation and limitations report | Active/repeat calculations reproduced; CI inflation, retries, epoch rotation, spoofing, opt-in bias, and PyPI comparison documented |

Acceptance of this ADR authorizes U1 only. U2 requires a separate reviewed
implementation plan showing the concrete hosting, IAM, logging, deletion, and
cost controls. No collector, upload code, service account, endpoint, or
`product_telemetry` dataset is created in U0 or U1. All U1 and U2 changes remain
subject to ADR-022: they reach `main` only through a reviewed PR with squash
merge, never a direct push.

### 11. Required verification

U1 and U2 must add deterministic tests for at least these properties:

1. a clean install and every existing entry point are disabled by default;
2. without current consent there are zero counter writes and zero DNS/socket
   attempts;
3. enable, disable, status, preview, purge, consent-version invalidation, and
   secret rotation have the specified semantics;
4. unknown operations and free-form values cannot enter local state;
5. disabling prevents a concurrent or later submission from sending;
6. preview performs no network access and emits exactly the frozen snapshot
   bytes, including `payload_id`, that the next `submit` sends;
7. local I/O failure cannot alter CLI, MCP, hook, enforcement, Audit, Decision
   Index, or benchmark behavior;
8. stdout, stderr, exit codes, MCP JSON, hook responses, enforcement outcomes,
   benchmark outputs, and canonical test fixtures are identical with
   measurement disabled and enabled;
9. all existing canonical tests plus focused CLI/MCP/hook tests pass;
10. the collector rejects unknown fields, oversize bodies, invalid enums,
    out-of-range counts, stale/future epochs, and duplicate payload ids;
11. collector and infrastructure logs contain neither bodies nor identifiers
    beyond the approved short-lived classes;
12. retention deletion is exercised end to end rather than asserted only from
    configuration;
13. a submit retry reuses the same `payload_id` so the collector deduplicates
    it, while a second snapshot in the same epoch uses a distinct `payload_id`
    and is stored as a separate report; and
14. counters from different pinned UTC epochs are never combined in one payload,
    each epoch carries its own unlinkable `instance_id`, and the incomplete
    fifth weekly bucket is attributed to bucket `4`.

Tests must use socket/DNS denial or interception, not only a mocked collector,
to prove the no-egress invariant.

## Consequences

### Positive

- Mneme can measure opt-in product activity without collecting governed
  content or changing the deterministic runtime.
- The identifier and raw rows expire, limiting longitudinal tracking.
- Explicit submission mode and payload preview make the network boundary
  visible and inspectable.
- CLI, MCP, and hook coverage is complete without expanding MCP authority.
- CI activity can be analyzed separately instead of inflating interactive-use
  claims.

### Negative and accepted trade-offs

- Opt-in and explicit submission produce selection and non-response bias;
  absolute adoption remains unknowable from this system.
- Thirty-day identifier rotation prevents exact rolling-window uniqueness and
  long-term cohort retention.
- A public anonymous collector cannot prove a report came from a genuine human
  user or production deployment.
- Excluding arguments, outcomes, paths, and errors limits product diagnostics;
  that limitation is intentional.
- Manual-only profiles and unsupported schedulers reduce coverage; weekly
  reporting improves coverage but remains opt-in and non-response-biased.
- Managed ingress may transiently process source IP addresses; the design
  limits logging and retention but cannot claim the network never observes an
  address.

## Alternatives considered

**Rely on PyPI download counts.** Rejected as the primary metric because
downloads include mirrors, caches, CI, upgrades, and installations that never
execute Mneme. PyPI counts remain an external comparison in U3.

**Send one event per invocation.** Rejected because exact timing and event
sequences create unnecessary behavioral data and increase failure and cost
coupling. Local aggregation is sufficient for the approved metrics.

**Use a stable installation UUID.** Rejected because it permits indefinite
longitudinal tracking and still does not establish a unique person or
organization.

**Submit opportunistically from normal commands and hooks.** Rejected because
fail-open handling does not remove latency, DNS, process, or networking
dependencies from deterministic operations.

**Add an MCP usage tool.** Rejected because the ADR-027 tool list is an
authority boundary and telemetry administration is not a model capability.

**Reuse the Decision Index or enforcement trace.** Rejected because product
usage and authoritative decision/evidence state have different purposes,
schemas, retention, trust, and privacy boundaries.

**Join usage with growth or web analytics.** Rejected because the approved
metrics do not require identity enrichment and the linkage would materially
change the privacy purpose.

## Acceptance checklist

Before changing this ADR to `accepted`, reviewers must record:

- product owner approval of the metric definitions and claim limitations;
- architecture approval of the entry-point and noninterference boundaries;
- privacy approval of consent text, identifier epoch, payload, IP handling,
  retention, small-cell suppression, and revocation disclosure;
- security approval of the local secret, collector threat model, logging, rate
  limiting, and IAM separation; and
- a named data-retention owner and deletion-verification cadence.

## Related

- ADR-022: Main Is PR-Only with Squash Merge — all U1/U2 implementation lands on
  `main` only through a reviewed PR and squash merge; this ADR authorizes no
  direct change to `main`
- ADR-023: Canonical Decision Index and Runtime Projection Boundary
- ADR-027: Decision MCP Proposal Ingestion and Authority Boundary
- ADR-029: Enforcement Evidence Binding Semantics
- `docs/ops/mneme-hq-gcp.md`
- `pyproject.toml` console entry points
- `mneme/cli.py`
- `mneme/decision_mcp.py`
- supported adapters under `mneme/integrations/`

# Analytics and Learning — V2-10

## Outcome and boundary

V2-10 adds a durable, provider-neutral analytics learning loop after a successful V2-09
publication receipt. The accepted implementation is local/CI fixture collection and read-only
recommendation generation. It does not activate an official platform API, change a Trend/Idea
rank, delete content, mutate paid media, publish, or apply a recommendation.

The successful flow is:

```text
successful publication receipt
  -> idempotent analytics sync
  -> Redis delivery / PostgreSQL canonical state
  -> normalized nullable metric snapshot
  -> explainable winner assessment
  -> immutable video-feature evidence
  -> recommendation-only learning insights
```

PostgreSQL is canonical. Redis keys `npd:video-factory:v2:analytics:queued` and
`npd:video-factory:v2:analytics:processing` carry only transient identifiers. A worker restart
recovers incomplete canonical syncs without duplicating historical snapshots.

## Provider truth

`AnalyticsProvider` is the common contract. V2-10 registers:

- `fixture-analytics-v1`: deterministic, no network, `mock=true`, local/CI only;
- YouTube Analytics API: `not_configured` or `contract_only`;
- TikTok Video Insights API: `not_configured` or `contract_only`;
- Instagram Graph Insights API: `not_configured` or `contract_only`;
- Facebook Graph Video Insights API: `not_configured` or `contract_only`.

All provider-state responses state `external_calls_enabled=false`,
`real_provider_tested=false`, and `production_deployed=false`. An opaque credential reference can
describe future configuration but cannot enable a call in V2-10. Raw tokens, keys and secrets are
rejected and are never persisted or returned.

## Normalized metric contract

Every snapshot records the provider, source, source kind, platform, publication, collection time,
mock/external-call truth and one row per normalized metric:

- views, impressions and reach;
- watch time and average view duration in seconds;
- completion rate;
- likes, comments, shares and saves;
- followers gained, clicks and CTR;
- revenue and RPM in VND;
- observation-window hours.

Unsupported or unavailable values remain `null` with `supported=false`; they are never converted
to zero. This distinction is preserved in PostgreSQL, the API, E2E artifacts and Studio UI.

## Sync lifecycle and retry

Sync states are `scheduled`, `queued`, `running`, `retry_scheduled`, `succeeded`,
`not_configured`, `failed`, and `cancelled`. Initial and manual fixture syncs are allowed in
development/CI. Scheduled refresh is implemented as durable state but stays off under
`ANALYTICS_SCHEDULED_REFRESH_ENABLED=false`.

Rate-limit/provider failures use bounded exponential backoff. Once the configured maximum attempt
count is reached, the job becomes terminal instead of retrying indefinitely. Idempotency keys are
hashed; exact replay returns the same sync, while changed payload reuse fails with HTTP 409.

## Winner detection

The deterministic scorer evaluates available evidence for:

- view velocity;
- retention and completion;
- engagement, shares and saves;
- CTR and follower conversion;
- VND revenue efficiency and production-cost efficiency.

Each factor has its own score, weight and evidence. Missing factors remain unscored and do not
silently become zero. A minimum observation window, view count, data coverage and retention or
completion evidence is required before classification. The public state is one of:

- `winner_candidate`;
- `normal`;
- `underperforming`;
- `insufficient_data`.

Every assessment hard-codes `automatic_action=false`, `paid_media_mutation=false`, and
`content_deletion=false`.

## Feature and learning evidence

V2-10 captures the current project/publication context: Trend cluster, Idea, hook, duration,
scene count, subtitle template, voice/music profiles, visual strategy, niche, topic, CTA and mock
publishing time. Evidence records that Trend and Idea rank were not mutated.

Learning insights can recommend a Trend family, hook, duration, visual/subtitle/voice pattern,
publishing window or more data collection. Each insight includes a statement, recommendation,
confidence and evidence references. All insights hard-code `applied=false` and
`autonomous_execution=false`. Later phases may consume them only through a separately approved
contract and owner gate.

## API and Studio

- `POST /api/v1/projects/{project_id}/analytics/syncs`
- `GET /api/v1/projects/{project_id}/analytics`
- `GET /api/v1/projects/{project_id}/analytics/syncs`
- `GET /api/v1/projects/{project_id}/analytics/syncs/{sync_id}`
- `GET /api/v1/projects/{project_id}/analytics/snapshots`
- `GET /api/v1/projects/{project_id}/analytics/assessments`
- `GET /api/v1/projects/{project_id}/analytics/learning-insights`
- `GET /api/v1/projects/{project_id}/analytics/history`
- `GET /api/v1/analytics-providers`

The create route requires a 16–200 character `Idempotency-Key` and a successful publication
receipt. Studio exposes only “Chạy dữ liệu mô phỏng”, labels fixture evidence prominently, renders
missing values as “Không có dữ liệu”, and contains no official-provider or execution control.

## Configuration

Safe checked-in defaults:

```text
ANALYTICS_FIXTURE_ENABLED=true
ANALYTICS_EXTERNAL_EXECUTION_ENABLED=false
ANALYTICS_SCHEDULED_REFRESH_ENABLED=false
ANALYTICS_MAX_ATTEMPTS=3
ANALYTICS_RETRY_BASE_SECONDS=30
ANALYTICS_RETRY_MAX_SECONDS=900
```

Production startup rejects `ANALYTICS_FIXTURE_ENABLED=true`. V2-10 startup always rejects
`ANALYTICS_EXTERNAL_EXECUTION_ENABLED=true`. Platform credential values, if prepared later, must
be opaque `secret://`, `vault://`, or `external://` references.

## Intentional limits

- no production deployment;
- no official analytics API acceptance;
- no scheduled production polling;
- no cross-platform identity resolution or revenue attribution;
- no automatic Trend/Idea/template update;
- no content deletion, budget mutation, publishing or remediation;
- no API authentication/RBAC yet, so the stack remains localhost/CI only.

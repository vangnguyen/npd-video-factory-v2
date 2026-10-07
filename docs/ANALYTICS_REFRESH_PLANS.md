# Durable recurring analytics reads

This increment implements bounded recurring read intent in the API/worker/Studio stack. It does not enable an external runtime, accept Owner UAT, migrate a live database, publish media or certify ANALYTICS_READY. Native Studio integration, Meta collectors, independent AnalyticsProfile administration, real provider acceptance and production scheduler acceptance remain open.

## Owner controls

`/api/v1/projects/{project_id}/analytics/refresh-plans` creates and reads plans; `/{plan_id}/state` changes enablement with an expected revision; `/{plan_id}/history` reads audit. Verified human Owner identity is required for writes. Project-scoped readers can inspect plans and history. Create requires an idempotency key and binds immutable configuration, actor, workspace/project/publication, provider and destination fingerprint. Concurrent same-key creation produces one plan and one audit entry. Changed intent conflicts.

Plans default disabled. Enabling requires explicit read-only acknowledgment, the separate scheduled-read switch, available provider and an unchanged bound publication. Global publishing switches remain independent. Intervals are 1–168 hours with 1–365 occurrences. Owners can disable without an available provider. Revision conflicts require a fresh read; the UI does not replay an uncertain state mutation automatically.

YouTube supports an explicit fixed report interval or a rolling lookback of complete UTC calendar days. Rolling requests end on the preceding UTC date. Those requested dates do not establish provider coverage or completeness. TikTok uses cumulative counters. Fixture plans have no real report query. Unknown metrics and billed costs remain null.

## Persistence and execution

Additive migration `0023_ns_analytics_refresh` creates plans, immutable occurrence-to-sync bindings and plan audit. Existing analytics job and snapshot schemas are retained. Destructive downgrade is refused pending separate Owner approval. The migration is rehearsed only on owned SQLite evidence; no live schema is changed.

The scheduler selects at most 20 due plans per tick with conditional updates and skip-locked architecture. Each occurrence and existing queued sync are written in one transaction. Missed intervals create one current collection and record skipped slots; they do not cause a catch-up burst. The next due instant is admission time plus interval. Occurrence ordinals and stable sync idempotency keys survive restart. Exhaustion prevents new occurrences but keeps the last valid occurrence eligible; the UI displays the run limit independently of enablement.

Queue admission uses the existing durable recovery and atomic Redis-list admission architecture. A tick admits at most 20 new occurrences plus 100 existing due and 100 queued jobs. PostgreSQL skip-locked and actual Redis Lua execution/outage/soak are not tested on this host.

The processor checks the plan revision and current publication before collection, official clients check before each wire read, and reservation/completion hold the plan revision fence. Revocation blocks later reads and rejects in-flight results without snapshots or learning records. Provider errors after revocation terminate instead of scheduling another retry. Re-enabling creates a new revision and never revives an old occurrence. Confirmed transport and cost intent already observed remain in history; unknown actual billing stays null.

## Studio and evidence

Studio provides explicit create/read/enable/disable controls for the selected publication and source. Exact project/workspace checks, verified Owner role, text-node rendering, stable create keys, bounded 100-row reads and stale response guards are covered by the DOM harness. Real browser/viewport/Owner usability acceptance is still unverified. The list/history APIs are bounded but do not yet paginate.

The evidence index is `docs/north-star/analytics-refresh-evidence.json`. The fresh-process contract clones retained explicit mock analytics evidence, creates a disabled plan through authenticated ASGI, tests the disabled gate, enables explicitly in the fixture, collects one occurrence, creates and revokes another, and restores exact plan/audit/job/snapshot/cost state in another process. Two old snapshots remain identical; one new snapshot and two occurrence bindings persist. Three official-protocol mock requests occur, nine authenticated API calls occur, nine analytics cost records retain null actual cost. The first scheduler instant is explicitly a test clock fixture. Source database bytes and previous exports remain unchanged. No real credentials, paid calls, external calls, accepted media replacement or production deployment occur.

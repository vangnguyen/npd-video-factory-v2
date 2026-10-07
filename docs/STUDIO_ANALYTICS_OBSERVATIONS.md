# Studio analytics observations

The API Studio now requires a publication and analytics source selection. Fixture and official-adapter controls are explicit; fixture profile defaults to `normal`. YouTube collection requires two valid dates and offers optional estimated revenue in VND. TikTok's counters have no invented report interval. Workspace editor/Owner permission is required to enqueue; viewers may read history.

Official collection is enabled only for a configured adapter and a completed live publication receipt. A real transport refuses mock receipts. The worker still rechecks exact account/profile/receipt, read credentials, enablement and cost admission before every provider request. Selecting an option or refreshing the view performs no collection or publishing operation.

Read endpoints:

- `GET /api/v1/projects/{project_id}/publications/{publication_id}/analytics`
- `GET /api/v1/projects/{project_id}/publications/{publication_id}/analytics/snapshots`

Optional `provider_mode=fixture|official` filters syncs, snapshots, assessments and learning insights consistently. Project/workspace authorization applies before these reads; missing publication returns 404. All successful analytics responses use `Cache-Control: no-store`. Existing project-wide routes remain available.

History shows exact collected timestamps, source labels, requested intervals and nullable metrics. Its chart leaves missing values and changed report/source scopes disconnected. A single value remains visible as a point. Comparisons require the same workspace, project, publication, platform, provider, mock state, account binding and query. Differences are changes in returned report values; they do not prove view velocity or complete date coverage.

Changing project, publication or source clears the view and discards stale responses. Collection does not chain another mutation. An unknown submission outcome retains its idempotency key for explicit retry; a confirmed sync allows a later newly requested refresh. Polling captures project/source/sync identity and refuses to update another selection. In-progress syncs discovered by read refresh resume polling.

Evidence: authenticated owned SQLite/ASGI tests, frontend DOM harness, and fresh `analytics-read-contract-n4` copied from the retained mock publication database. The standalone contract performs six official mock reads and nine authenticated API calls, restores two immutable snapshots in a new process, and records six costs with actual cost null. Its source database remains byte-identical and no video is replaced.

The later [bounded history/channel increment](ANALYTICS_CHANNEL_OBSERVATIONS.md) adds explicit paginated observation reads and a workspace channel observation view. Its fresh n6 contract and evidence are retained separately from this original n4 rehearsal. Account-level collectors, recurring refresh, Native integration and complete AnalyticsProfile/operator configuration remain gaps.

No browser/viewport/Owner UAT, real account collection or production deployment is certified. `ANALYTICS_READY = NO`; the original North Star remains in scope.

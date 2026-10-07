# Channel learning snapshots

Master Spec section 51 and program Wave 12 remain in progress. This increment aggregates compatible observed performance into immutable, recommendation-only snapshots and connects reviewed guidance to Trend Radar, idea briefs, opportunity queues, draft projects and media plan provenance. It does not certify Native parity, real providers, Owner UAT, production deployment or final A/B/C acceptance.

## Evidence and scope

An editor, reviewer or Owner explicitly creates a snapshot using an existing published/live publication and its latest official-source analytics observation. Mock official transport is supported as mock evidence. The fixture analytics provider has no verified channel identity and cannot be promoted into an official channel cohort. No provider call, paid operation, publication, deletion, media budget change or render is performed by learning.

The bounded query reads the latest observation per publication, at most 501 candidate rows, and admits at most 100 distinct physical remote posts. Workspace, account/profile binding digest, platform, provider, source kind, transport, requested query, render format, frozen niche, winner policy and the availability/weights of scored factors must match. Exclusion counts and scan/selection truncation are explicit. This is a bounded sample, not an exhaustive channel history or account total. Requested dates do not prove complete provider coverage or equal post age.

Every admitted observation references its metric snapshot, assessment, final render, canonical timeline version, frozen feature-context digest and hashed remote post identity. A legacy or corrupt render context, insufficient assessment, incompatible factor basis or duplicate remote post is excluded. Full hook/visual annotations are recovered from frozen render context rather than a truncated legacy projection. Labels remain source annotations or edit facts; their semantics are not independently certified.

## Recommendations

The versioned policy defaults to three distinct posts per feature group, three known-feature comparison posts, at most 100 posts and a ten-point median assessment-score difference. Supported dimensions are trend family, hook, duration bucket, visual strategy, subtitle style, voice profile and publishing window. Unknown feature values do not become comparison categories. Up to 20 values per dimension are reported, with a truncation flag.

Both medians and their difference remain null until sample thresholds pass. Positive association meeting the configured difference yields a recommendation candidate; otherwise the result is insufficient data or no positive association. Each group retains sample/control snapshot references. The result describes an association between frozen features and relative winner-assessment scores. It is not a causal effect, significance test or future performance guarantee.

Actual publication timestamps are unavailable in current collectors. Publishing-window features and advice remain unavailable. Receipt, queue and collection times are never substituted. Missing retention/completion cannot create a sufficient assessment.

## Persistence and API

Migration `0024_ns_channel_learning` adds one table and preserves existing analytics/schema/history. It is rehearsed only on a new owned database; no live migration is performed. Deletion through foreign keys is restricted, and destructive downgrade requires a separate approved export/recovery procedure.

- `POST /api/v1/projects/{project_id}/analytics/learning-snapshots`: explicit editor-or-higher creation, `Idempotency-Key` required.
- `GET /api/v1/projects/{project_id}/analytics/learning-snapshots?limit=1..100`: bounded history.
- `GET /api/v1/workspaces/{workspace_id}/learning-snapshots/{id}`: exact immutable snapshot.
- `GET /api/v1/workspaces/{workspace_id}/learning-snapshots/{id}/recommendations`: reviewed advisory feedback.

Human authentication and workspace scope apply. New routes use no-store responses. The same key/request replays the original snapshot even after newer analytics arrive; key reuse with a different policy/publication conflicts. Concurrent identical creates persist one snapshot. A new explicit request/key records a later version. Snapshot schema, policy schema, content digest, actor, creation time and frozen source refs are retained. Reads verify scope, digest and persisted actor/time metadata. History pagination beyond the configured bound remains unfinished.

## Downstream integration and Studio

`learning_snapshot_id` is optional on Trend/Idea/Queue and MediaPlan requests. Services validate the immutable snapshot against workspace and niche before planning. Trend refresh returns a matching trend-family advisory reference. Global trend scores remain estimates. Idea briefs persist the complete recommendation reference and evidence; queues explicitly requesting a snapshot select briefs carrying that same snapshot. Draft projects inherit the reviewed brief and retain human approval/publishing defaults. Media plans persist guidance and fingerprint its immutable snapshot identity. Advice does not automatically change resolver priority, paid admission or selected assets. Unrequested legacy idea/media/queue fingerprints retain their original serialization.

Studio exposes explicit snapshot creation, bounded history, evidence groups and missing-data labels. Network-uncertain retries retain an idempotency key; a confirmed result permits a later explicit snapshot. Reviewed guidance may be attached to the next B-roll plan through an unchecked-by-default control. Trend Radar accepts the reviewed snapshot reference for future refresh/idea/queue requests. Voice/subtitle/visual recommendations are visible for human selection. Selecting and applying catalog templates directly from learning suggestions remains unfinished. Scope changes invalidate late responses and old advice; annotations render as text.

## Verification limits

Owned SQLite, API/ASGI and DOM tests are distinct from real provider, browser viewport, PostgreSQL, Native and production acceptance. The restart contract uses six explicit synthetic metric seeds, one official read adapter through MockTransport, fixture trends, nonplayable render bytes and fixture approval/receipts. It does not certify full media QC, paid generation, legal rights or Owner acceptance. Prior metrics and accepted media remain unchanged.

Continue personalized opportunity ranking, template catalog mapping/selection, Native integration, independent analytics/channel configuration, actual account/coverage acceptance and original Waves 0–16. `LEARNING_LOOP_READY = NO` and `IMPLEMENTATION_COMPLETE = NO`.

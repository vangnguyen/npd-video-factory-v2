# Personalized opportunity and subtitle review

Master Spec sections 8–12 and 51, program Waves 12–13. This increment combines existing global planning estimates with supported channel-history associations and makes subtitle recommendations selectable for human review. It remains recommendation-only. Native parity, semantic labels, actual provider/audience acceptance and final trend-to-learning production certification are unfinished.

## Bounded planning estimates

`learning_snapshot_id` explicitly opts Trend/Idea/Queue requests into a verified immutable channel snapshot. `learning_policy` is optional and requires that reference. `channel-ranking-policy-v1` defaults to history weight 0.25 and a maximum adjustment of 15 points; weight is configurable from 0 to 0.5 and the adjustment cap from 0 to 25. Ambiguous booleans, nonfinite values and out-of-range controls are rejected.

The matching historical trend-family group must have sufficient feature/control evidence from the channel-learning snapshot. Its descriptive median assessment-score difference is multiplied by the configured weight, bounded by the adjustment cap and added to the original planning score. The result is clamped to 0–100. Missing/unsupported history retains a null history difference/adjustment and exactly preserves the original score. Weight zero explicitly preserves the base estimate while retaining available history evidence.

The base global trend and idea scores remain unchanged. The separate personalized estimate records its algorithm version, policy, base score, adjustment, result, mock-history flag, learning digest and sample/control metric-snapshot references. It is a planning recommendation, never an observed or predicted future metric. No causal improvement, significance or performance guarantee is inferred.

Trend refresh/read returns the estimate and ranks proposals accordingly. `GET /api/v1/workspaces/{workspace_id}/trend-clusters` accepts the reviewed reference, niche and bounded policy query controls without collection or provider calls. Idea briefs persist the separate estimate. Explicitly personalized queues select briefs matching the same snapshot, algorithm and policy; queue items persist the exact estimate and source-trend score versions in their content fingerprint. Repeated unchanged requests replay the same queue. Policy changes produce a distinct run. Unrequested legacy serialization and scores remain unchanged.

All actions are reversible proposals. No rendering, deletion, media-budget change, paid admission or publishing is caused by ranking. The normal project/preview/human approval/render/QC/publish gates remain.

## Subtitle recommendations

`GET /api/v1/projects/{project_id}/analytics/learning-snapshots/{id}/subtitle-suggestions` checks project/workspace/niche and returns available versioned catalog starters matching a sufficiently supported historical subtitle-style association. The response records catalog version/hash, current subtitle/timeline versions, sample/control refs, score difference, compatibility and attention reasons.

The historical feature currently records position, animation, font family and font weight. Matching those fields is not proof that the full catalog template was used. Responses explicitly mark `historical_template_identity_verified=false`. Unknown styles are listed as unmatched, not converted into invented templates. A missing production package blocks selection. Word-timed starters require current cue word timestamps.

Studio reads suggestions explicitly, renders annotations as text and requires a button click to choose a starter into the existing subtitle form. It performs no save during the read or selection. A stale subtitle version or unavailable word timing prevents selection. The user reviews and saves through the existing version-checked subtitle route, which creates a new subtitle version and invalidates prior review/approval bindings as appropriate. Existing alignment checks still reject stale words after text/timing edits.

Trend Radar exposes an explicit read of ranking from stored history, configurable history weight, separate estimate labels and mock/missing-data indicators. Scope changes discard late responses. Choosing history never collects provider metrics, creates a project or starts a render.

## Evidence limits

Owned SQLite/ASGI/DOM and exact fresh-process restore are local/mock evidence. The contract uses six explicit synthetic metric histories, fixture trend clusters, three official-adapter MockTransport reads and four authenticated requests covering ranking, queue creation, subtitle suggestions and an explicit versioned template save. Historical metrics and the learning snapshot remain exact afterward. Style/render media/approval/receipts are fixtures; no playable media QC, legal-rights acceptance, browser viewport or Owner UAT is certified.

The first rehearsal caught a new route using the wrong application-state service name; the route/test now use the existing `production_package_service` registration. The next rehearsal reached restart export but exposed Windows console encoding for Vietnamese idea text; machine JSON output now uses Unicode escapes and restores the same strings. Failed logs/databases are retained.

`LEARNING_LOOP_READY = NO`, `TREND_RADAR_READY = NO`, `IMPLEMENTATION_COMPLETE = NO`, `REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO`, `PRODUCTION_DEPLOYED = NO`. Continue Native integration, channel/operator configuration, semantic feature validation, authoritative publication time, full first-class Trend Radar and original Waves 0–16.

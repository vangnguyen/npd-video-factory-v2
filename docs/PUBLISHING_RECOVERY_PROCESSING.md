# Publishing receipt recovery and processing

The YouTube worker remains opt-in through explicit dependency injection. Default publishing flags and the production factory remain disabled. This increment completes sealed-session recovery and observed processing records; it does not complete all platform adapters or Owner acceptance.

## Crash recovery

`PublishingSessionVault.recover_initialization()` accepts a scoped publication and exact dispatch version, never a client session URI. It finds the immutable encrypted receipt saved after the original initialization response. AES-GCM authentication, original key, scope, project, binding, byte count, URI and expiry must pass before a conditional transition from `init_intent` or `init_uncertain` to `upload_ready`. The transition increments the version, fences the old ticket and records one content-free event. It does not extend or overwrite the receipt.

This is local recovery of an already received response and makes no provider request. Revoked consent does not prevent recording that response. It still prevents the next upload chunk. Missing, expired, corrupted or foreign receipts remain review-required; the worker never starts another initialization to recover uncertainty.

## Processing and publication

`poll_processing()` checks the current bound account and reads only the exact uploaded video through official-format GET requests. Every request retains pre-wire cost admission. Selected observations contain processing, privacy and schedule; absent fields remain null. Raw provider bodies, tokens and session URIs are excluded from public evidence.

`PublishingProcessingJournal` checks workspace, project, upload byte completion, remote ID and transport mode. Each observation appends an audit event. A completed upload is insufficient for a receipt. Processing must succeed and observed visibility must match the request. A scheduled upload needs the exact observed private deadline; it remains `scheduled` without a publication receipt until the due video is observed public. Visibility or schedule disagreement requires review and never triggers an automatic correction or deletion. Receipts remain immutable across later polls. A processing failure requires review.

Mock processing can complete a mock publication record, with `mock=true`, `external_action=false`, `remote_url=null` and public `published=false`. No real post or watch URL is inferred from a fixture. Private or unlisted successful platform acceptance is distinguished by the observed privacy event; it does not imply public reach.

Protocol fields follow the official [video resource](https://developers.google.com/youtube/v3/docs/videos) and [videos.list](https://developers.google.com/youtube/v3/docs/videos/list) contracts. API audit restrictions and credential acceptance still require separate real-provider evidence.

## Verification and remaining work

Recovery/vault/worker: 33 passing checks. Processing/protocol: 23 passing checks. The owned completion rehearsal uses the preserved 4,256,257-byte synthetic portrait MP4, two actual full media QC scans, actual SQLite/AES and two independent Python processes. Recovery makes zero wire calls; processing uses mocked official responses. Six mock requests retain one initialization and six null actual costs. All human identities, approvals, account/OAuth/key data, provider responses and timeline/subtitle QC inputs are fixtures. The source hash remains unchanged. This is not final acceptance bundle A/B/C or Owner UAT.

Remaining: durable scheduler and bounded polling/backoff, per-publication worker ownership, efficient copy/QC reuse, atomic edit admission, real credential/key lifecycle and profile administration, thumbnail delivery, complete TikTok/Meta adapters, native queue/history/approval UI, production wiring and real-provider acceptance. No production database migration, paid call, real publishing, main merge or deployment was performed.

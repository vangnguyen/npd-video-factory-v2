# Native Meta asynchronous publishing component

The direct worker and shared bounded queue now support versioned Facebook Reels and Instagram Reels execution. The retained evidence uses actual local SQLite, Windows DPAPI and file bytes with explicitly mocked Meta, S3, Owner, platform eligibility and nonplayable media. It does not establish real-provider acceptance, rendered Studio usability, Owner UAT, full Mode A/B readiness or production deployment.

The original Master Spec remains authoritative. This is a Wave 9 component; 59 of the 64 broad capability groups remain open. Every applicable full completion flag remains NO.

## Versioned authority and original source

Existing `native-official-meta-publication-request-v1` reviews and snapshots retain `execution_supported=false`. Their configuration digests and history remain readable; they cannot be dispatched or silently converted into execution authority. A new request tagged `native-official-meta-publication-request-v2` must bind the exact current account proof, dry-run result, approved final, metadata, Meta configuration and media configuration. Its new snapshot requires its own finite human Owner publication grant.

`native-meta-distribution-registry-v2` adds a typed S3 execution capability. Every gate defaults false, and the factory masks manifest gates with explicit Owner enablement. Account identity, configured permissions and a media lease do not grant publication authority. Client-supplied provider URLs, tokens, arbitrary graphs or unreviewed metadata are not accepted.

The S3 dependency retains separate finite Owner media-disclosure consent and an exact media-selection acknowledgement. Selection binds publication SHA, dispatch version, original final job/hash/size, verified object version, result SHA and mock mode. A change in selection during account preflight is rejected before mutation. The URL is resolved again after preflight and remains an internal worker value. See [immutable media delivery](NATIVE_PUBLISHING_MEDIA_DELIVERY.md).

## Asynchronous provider states

The executor reuses the existing official HTTP protocol, scoped credential factory, worker fences, cost ledger, immutable publication journal and queue. It does not use browser publishing.

- Instagram: submit one REELS container, observe that original container until FINISHED, submit one `media_publish`, and retain the actual returned post ID. An unconfirmed publish response cannot be converted into a post ID from container status alone.
- Facebook: create one video job, submit the selected private file URL once to the validated fixed upload endpoint, observe upload status, submit finish once, then observe the original job. The finish acknowledgement starts processing; a receipt requires the actual ready status with upload, processing and publishing phases complete.

Each provider mutation has a committed scoped intent and a unique per-publication index. The finite queue runs only after its separate acknowledgement, respects current Owner authority, deadline, step ceiling and durable read backoff, and supports local cancellation. It does not renew consent, delete remote posts or replay a mutation.

This follows the official [Facebook hosted Reel workflow](https://www.postman.com/meta/facebook/request/cfr4gjf/2-b-upload-hosted-reel) and [Instagram Reels publishing collection](https://www.postman.com/meta/instagram/folder/y6xustx/reels-publishing). `v24.0` in local fixtures is an explicit fixture value; current application eligibility, permissions and configured API-version compatibility remain external acceptance work.

## Recovery, cost and private data

Three additive journals retain exact media selections, identity preflights and normalized Meta responses. Unknown outcomes use a separate nullable-response table; the existing generic publication response schema is unchanged. Every provider read/mutation records project, original final job, provider, operation, request digest and nullable actual cost. A stored estimate or mocked response is not a billed cost.

Interrupted recovery performs no credential read, SDK request or automatic replay. An unresolved cost intent becomes unknown; an already settled response hash remains preserved. A lost initialization response requires review and cannot create a second provider job. Unknown transfer/finish can only be reconciled through original-job status where that status proves the outcome. Unknown Instagram finish still requires external review because the original container ID is not the returned post ID.

Consent renewal is explicit, finite and bound to the same snapshot/job. It cannot authorize a second initialization. After media has been submitted, original-job status and finish remain available after later project edits or missing private S3 lease files, provided current publication authority and Meta configuration remain valid. A Facebook transfer still needs current canonical source and a fresh separate media consent/selection after publication consent renewal. The existing object can be reconciled read-only; it is not overwritten or uploaded again.

No token, signed URL, opaque request body or private provider error enters public DTOs, events, cost receipts or backups. Receipt reads validate original job, scope, response, cost and completion facts. Public backups include the new journals and refuse active publication work. Restored default-off history is checked in a separate process without keys or replay.

## Evidence and remaining work

New Meta38 PASS (161.507s), related Native204 PASS (285.039s) and final shared queue33 PASS (55.522s) cover the direct component. The33 queue cases overlap the204 and are not additional unique cases. Evidence is indexed in `docs/north-star/meta-execution-evidence.json`; the retained two-platform flow is under `recovery/20261007/meta-execution-flow-n1`. This folder name is historical; this component is recorded on 2026-10-10. Test failures and subsequent corrected runs remain separate evidence.

The protected Native startup/CLI/media HTTP controls are now connected and verified separately in [Native Meta runtime](NATIVE_META_RUNTIME.md). Its current related185/final26 tests and two actual signed HTTP mock flows supplement this original direct component evidence; overlapping suites are not summed. Studio review and media selection, platform-specific analytics, durable multipart delivery and every remaining original Master Spec requirement remain safe work. Real S3/Meta credentials, current permissions/API/app eligibility, separate Owner publishing enablement, browser/non-developer acceptance, genuine media, production isolation/Docker/soak and full A/B/C bundles remain separate. Real provider calls, paid operations, external posts, main merges and production deployments in this component are all zero. Owner listening/Phase 10 UAT remains deferred.

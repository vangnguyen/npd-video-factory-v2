# Native immutable publication metadata and schedules

Official Native reviews can now carry explicit `PublicationMetadata` in addition to a completed dry run's evidence. The existing human Owner, current final/render/QC, rights, target/account, protected configuration, separate approval and dispatch fences remain required. This is a partial publishing increment; automatic queue execution, durable scheduling, OAuth lifecycle, other platforms and real-provider/Owner acceptance remain outstanding.

## Frozen review, current initial admission

`Create.metadata` is optional. If omitted, the review inherits the completed dry run's metadata. Omitted/null metadata is excluded from the request fingerprint, preserving previous unscheduled idempotency keys. Explicit metadata is strictly validated, frozen in the request and review, separately checked against the official platform and protocol, and identified by `metadata_source=explicit_owner_request`. Changing it cannot reuse an idempotency key or an existing approval. Parent dry-run evidence, the project, canonical timeline, final render and human final review are unchanged.

New reviews persist `reviewed_at`. Source revalidation uses that frozen instant for metadata preflight, while continuing to recheck current project/document/final/rights/account/configuration and grants. Older snapshots without the additive fields remain readable; their creation instant supplies the metadata validation time when needed. Processing a known upload after the scheduled time no longer invalidates its original metadata review merely because wall-clock time advanced.

Initial approval, a new prepared-phase renewal, and every prepared/init-intent worker admission additionally validate the current clock before credential resolution, account reads or upload initialization. Native requires at least 60 seconds before a scheduled initialization, an internal margin for its bounded requests. This is not a claimed YouTube platform minimum. A completed initialization's known session retains its original metadata, offset and duplicate guard; later chunks/processing do not create a replacement session or silently change the time. Exact review/approval replay does not extend an existing grant.

YouTube accepts `publishAt` for a private video that has never been published, and a past scheduled timestamp can cause immediate publication. Native refuses past/too-close initial schedules and non-private scheduled metadata. These rules were checked against the [official video resource reference](https://developers.google.com/youtube/v3/docs/videos#status.publishAt) and the [official resumable protocol](https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol).

Numeric/boolean schedule values, missing time zones, unknown metadata fields and unchecked model-copy values are rejected. Revalidation suppresses serializer warnings before returning sanitized DTO errors, so malformed internal values are not printed. Existing protocol failures such as unsupported thumbnails, invalid title/description or schedule/privacy become scoped workflow errors without an upload.

## Processing and Studio

The existing typed processing observation remains authoritative. Before the scheduled time, processed/private video with the exact observed schedule stays pending. A wrong observed schedule, processing failure or wrong visibility requires review. After the scheduled time, Native requires an actual public visibility observation before a terminal receipt. It does not infer publication from time passing or byte-upload completion. Mock receipts remain `published=false`, `mock_publication_complete=true`, `external_action=false`.

The optional signed publishing panel now offers a local date/time input, labels the device time zone, and normalizes an explicitly chosen time to UTC. A new schedule requires private source metadata and at least a one-minute lead. Leaving it blank preserves the original request. The input is a review draft, not a canonical media edit or grant; creating/reading a review never sends. Workspace/project/revision changes reset it. Separate human approval and fresh per-step acknowledgement/state remain required.

## Verification and limits

Current tests: 103 publication-related Native cases and 297 full Studio cases pass, including ten new metadata/schedule cases and two new DOM cases. Full Native 846 PASS at `fac51977fa8bfb482670533b05bcfcf73ab6c81a` is prior to this increment, not a new full 856-case run. An initial test assertion confused equivalent `Z` and `+00:00` timestamp serialization; it now compares the represented instant. No product gate was loosened.

`scripts/north_star_native_official_publish_metadata.py` retains the owned signed HTTP rehearsal. Current evidence is `recovery/20261007/native-official-publish-metadata-flow-n1`, restored at `C:/vf-native-fixture-official-publish-metadata-restore-01`. It records 23 signed loopback requests and 12 mock provider requests: one initialization, three exact data chunks, a pending future private observation and a later public release observation. A stale processing version sends no additional request. The actual wire metadata matches the frozen review, and the served Studio module matches source bytes.

Media/QC/rights/account/OAuth/platform/human/clock/provider values are explicit nonplayable fixtures. Advancing this clock and changing mock replies do not constitute a real schedule, OAuth/provider/legal/media/browser/Owner acceptance. There are zero real publications, external provider calls, paid operations, new renders or inference calls. The accepted runtime is not enabled or reconfigured.

The archive excludes credentials and resumable URIs. All twelve publication/cost journals, original project/job/artifact hashes and the qualified receipt replay after restore and a fresh-process reopen with no credentials, profiles, vault or dispatcher configured. The preceding signed-controls receipt and all twelve journals also replay exactly under the new additive metadata model. No accepted video is replaced. Source/export/log/archive hashes are indexed in `docs/north-star/native-official-publish-metadata-evidence.json` and the increment preservation receipt.

The original Master Spec and continuously updated capability matrix remain authoritative. Continue durable queue execution/scheduling, secure OAuth acquisition/refresh/rotation, authentic receipts-to-analytics, other platforms and all remaining original safe waves. Owner listening/UAT remains deferred.

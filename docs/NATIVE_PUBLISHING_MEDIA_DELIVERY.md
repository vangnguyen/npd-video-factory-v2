# Native immutable publishing media delivery

This Wave 8/9 component prepares the exact approved final for a future official pull-URL publisher. It is implemented and verified with actual local byte streams, SQLite, Windows DPAPI and explicit S3/Meta/Owner/platform/nonplayable-media mocks. The separate versioned Meta executor is described in NATIVE_META_PUBLISHING.md; protected Native CLI/HTTP/Studio media controls, real-provider acceptance and the full North Star remain open.

The provider-neutral implementation is `apps/api/app/publishing_media_delivery.py`; its durable Native consent/cost/private-custody producer is `services/windows_native/publishing_media_delivery.py`. Existing generic object storage and YouTube/TikTok publishing remain in place.

## Admission and immutable objects

An exact typed storage profile selects HTTPS endpoint, bucket, region, credential alias and an optional HTTPS signing endpoint. The Native factory is disabled by default. It binds workspace, State root digest, protected lease directory, pinned credential ciphertext/expiry, explicit cost estimate, provider mode and configuration SHA. Startup hashes the configured ciphertext without decrypting or creating an SDK client. Credentials are never discovered through an ambient AWS chain; the lazy SDK receives explicit protected credentials.

The tagged request `native-publishing-media-delivery-request-v1` requires the publication/snapshot/configuration SHA, a new explicit `acknowledged_external_media_delivery=true`, bounded media-consent window, bounded signed-URL lifetime, independent external-cost ceiling and idempotency key. A dry-run or account check alone cannot grant disclosure consent. A current human Owner, current original publication grant, canonical project, physical approved final, original rights and platform validation must still pass. Every SDK request and local signing step repeats that admission check. Client-supplied URLs, credentials, endpoint and provider overrides are rejected.

Keys are server-derived: `workspaces/{workspace}/projects/{project}/jobs/{final-job}/{final-sha256}/final.mp4`. Creation uses streamed conditional `PutObject` with `IfNoneMatch='*'`, content length/type, SHA256 metadata and checksum. Existing objects are read rather than overwritten. HEAD metadata alone is insufficient: pinned-version or conditional GET streams every byte through a bounded SHA256 check. Source corruption and delivered-byte corruption fail.

This adapter uses single conditional PUT and explicitly rejects files above 5 GiB before source-open or SDK operations. Durable multipart delivery remains an implementation gap; the general ingest/production requirements have not been reduced. Pull-URL leases require a non-null object version. Their signature includes that exact `VersionId`; unversioned objects cannot receive a lease. Operators must separately configure a compatible versioned bucket and least-privilege storage access; no bucket, ACL, versioning, deletion or other infrastructure is changed by this component.

The contract follows [AWS conditional PutObject](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/put_object.html), [specific-version GetObject](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/get_object.html) and the documented [single PUT size limit](https://docs.aws.amazon.com/AmazonS3/latest/userguide/upload-objects.html). Storage-provider compatibility remains unverified outside mocks/offline SDK stubs.

## Consent, cost and recovery

Two additive journals record delivery snapshots and per-operation intents/responses. Every external HEAD/GET/PUT reserves an operation in the existing cost ledger before the SDK call, preserving project/job/provider/request scope and nullable billed cost. Live operations require a configured estimate, the separate delivery ceiling and the existing project budget gate. Fixture operations remain explicitly mock, unpaid and without external calls. Actual billed cost remains null when no billing receipt exists.

SDK retry attempts are bounded to one. An unconfirmed upload is not replayed. A new separately consented reconciliation request must reference the original delivery/scope/configuration and performs only reads; absent objects remain absent. Successful delivery cannot be processed again. Cancellation stops subsequent local steps and never deletes a remote object. Known responses after consent expiry or cancellation remain recorded; they do not authorize another request.

Normalized provider response evidence is committed before cost settlement. Recovery finishes a pending cost receipt from that original evidence, or marks an unresolved intent unknown, without loading credentials or contacting storage. A process interrupted while running becomes `outcome_unknown`. History validates the original publication/grant, operation ordering and cost foreign keys, while remaining available after grant revocation, project edits or keyless restore. Rehashed authority/private-field claims and removed/mismatched cost evidence are rejected.

Public backups include both optional journals and refuse queued/running delivery. They exclude protected S3 credentials and leases. Recovery is local history recovery; it does not recreate a private URL or resume a provider mutation.

## Private leases and consumer boundary

Credentials and URLs use separate DPAPI prefix/entropy domains outside the source checkout and owned State backup. Secret files are created exclusively with the existing private Windows DACL primitive. Lease ciphertext is pinned; URLs and SDK exception text are excluded from DTOs, SQLite receipts, events, source and public backups. SDK private request/signing logs are suppressed in the local request context.

Only `resolve_for_consumer` returns the private lease to an internal worker. It checks exact publication snapshot, raw consumer mock mode, current Owner/grant/configuration/canonical source, ciphertext, protected envelope, host-only signed headers, exact object/version, signed query scope and remaining lifetime. It performs no storage request. A mock lease cannot be resolved for a live consumer. Native configuration also requires the requested URL lifetime to fit inside the current credential lifetime; [AWS temporary-credential URL expiry](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html) may otherwise shorten validity.

Resolving this lease does not grant publishing authority. Existing Meta-v1 reviewed snapshots remain `execution_supported=false`, and the shared worker still rejects them before Meta credentials/intents/mutation. The opt-in Meta-v2 executor needs a new execution-capable versioned request and current publication intent; it cannot promote a legacy v1 review. No public URL endpoint or automatic publish path was added.

## Evidence and remaining acceptance

- Related Native suite: 127 PASS, 124.870 seconds, including backup/cost/Meta admission/signed HTTP/shared publication/TikTok worker. A final State-root binding change was followed by 16 focused Native PASS, 15.590 seconds, and a fresh retained recovery flow.
- Provider contract suite: 23 PASS, 1.09 seconds, with explicit in-memory S3 protocol and real installed boto3/botocore `Stubber`/local signing. No network request or real credential was used.
- Retained `publishing-media-flow-n2`: one conditional upload with deliberately lost reply, a new read-only recovery, six storage operations/nullable cost receipts, exact replay, current grant-revoke consumer refusal, public backup and separate-process keyless history/cost/project recovery. Backup SHA: `6afe23887f38b59920e10f27079a8002010ace80ae7491e2acd96c06a7de73f7`.
- Initial pytest attempt used the inaccessible ambient pytest temp root (1 passed/15 fixture errors); the retained reruns use newly owned test temp directories. No ambient ACL or historical data was changed. Earlier successful component iterations remain separate evidence, not additional unique-case counts.

Source/evidence index: `docs/north-star/publishing-media-evidence.json`. Test and flow logs live under `C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/`. This folder name is historical; this component was validated on 2026-10-10.

Still required: protected operator/runtime/HTTP/Studio wiring; genuine versioned-storage/provider/cost/permission acceptance; durable multipart delivery; protected Meta execution/runtime/Studio integration and real asynchronous provider acceptance; platform analytics; actual browser/Owner/media UAT; full Mode A/B and original A/B/C bundles; production isolation/Docker/soak/deployment acceptance. Real provider calls, paid operations, external posts, main merge and production deployments for this component are all zero. Counts remain 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED, with 59 broad groups unclosed.

# Reviewed internal B-roll resolution

This increment admits reuse of one registered supporting candidate already
saved on a B-roll plan item. It does not search stock, generate media, apply a
timeline edit, approve a project or publish a video. Legacy endpoints and
unmarked jobs keep their execution paths.

## Explicit human API

The route is
`/api/v1/projects/{project}/media-plans/{plan}/items/{item}/internal-resolution-review`.

- `GET` reads the exact canonical/source/plan/item/candidate context. It performs
  no SQL write, queue operation, object download or provider dispatch.
- `POST` requires an editor with human writes enabled, `acknowledged=true`,
  `asset_id`, the exact `context_sha256` and a stable `request_key`.
- `GET /requests/{key}/jobs/{job}` observes only the original linked job. A
  substituted plan, item, request, credential or job cannot borrow its receipt.
  Reads never follow a latest-job pointer or repair a queue handoff.

Public responses use `Cache-Control: no-store`. The admission receipt is
immutable. Later observations contain that original receipt alongside the
current exact job audit and `source_current`/`can_adopt` flags. A terminal job
whose inputs or selected output changed is not presented as adoptable.

## Durable job and queue custody

One existing `service_api_operations` row in namespace
`human:broll-internal-resolution.v1` and one ordinary internal resolution job
are committed in the same SQL transaction. Their private binding covers the
canonical timeline/version, saved source transcript, source custody, project
metadata, full plan/item, saved candidate list and candidate asset custody.
Replaying the same explicit request returns the same receipt and job.

Only an authorized explicit POST can hand off or hand off again. Production
Redis uses atomic `LREM` plus `RPUSH` for the same job ID. A missing atomic
adapter, failed connection or lost acknowledgement produces
`handoff_pending`; it cannot lose the durable job or invent a replacement.
There is no distributed exactly-once Redis/SQL claim. SQL owns the one logical
job and one live attempt. Duplicate deliveries are fenced at claim time.

Startup recovery skips marked reviewed jobs. In particular a crashed running
attempt stays read-only `unknown`; it is not automatically resumed, assigned a
new token or replaced. Explicit running-attempt recovery is separate work.

## Internal worker

The new server-owned marker selects a small branch in the existing resolution
service. A private operation in `worker:broll-internal-resolution.v1` owns a
single queued-to-running transition. Its random token is not returned in a
job, receipt or public observation.

The existing bounded object reader verifies provider, workspace/project key
prefix, byte count and SHA256 into an owned temporary directory. Cancelled I/O
is drained before cleanup. The existing internal materializer and normal
resolution completion are reused.

Immediately before normal completion writes, the same SQL transaction checks
the attempt token, exact full source/candidate/asset custody, current item
ownership and the materialized asset again. This check holds fresh SQL locks.
An asset's provider, object key, size, version, provenance, rights or license
cannot change silently while its checksum stays the same. A stale or cancelled
attempt cannot write a successful job/item/output or overwrite another item
selection. No timeline/history/preview/approval write is part of resolution.

Unknown rights remain review-only and nonpublishable. Restricted assets and
invalid visual/measurement metadata are rejected. The full publishing rights
gate and default publishing-off policy remain in force.

## Evidence limits

The focused tests use isolated SQLite, authenticated in-process ASGI, synthetic
source/ASR/media fixtures and owned local storage. They exercise actual
admission, queue uncertainty, byte verification, worker fencing, completion
and observation. They do not establish real provider, real media decoding,
PostgreSQL, browser UI, production deployment or Owner UAT acceptance.

Root integrates only the new router import and mount into its current main
file. It must preserve concurrent Studio, recovery and canonical-apply work.

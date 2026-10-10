# Native Meta Studio controls and immutable media selection

The shared Studio publication controller now accepts versioned Facebook/Instagram configuration, account proofs, publication snapshots, asynchronous job states and receipts. It reuses the existing Native signed API, canonical project/timeline, worker and finite queue. A separate media card handles disclosure and exact media selection. This is a Wave 9 component; full publishing and North Star acceptance remain incomplete.

## Operator flow

Read configuration and source pages, select the current approved dry-run video and exact Page/Instagram account proof, then prepare a new review. Studio uses the reviewed metadata and tagged Meta request; unsupported schedule overrides are hidden and rejected. Creating a review does not approve publication.

After separately approving publication, read the media configuration, acknowledge delivery of that exact final and its finite cost bound, then read/process the saved delivery. A successful delivery still requires an exact selection acknowledgement for the publication and current dispatch version. The first provider step and initial queue plan remain disabled until that selection matches the same publication and approval. The private signed URL is never a Studio input, public DTO or link.

Each manual step/status read needs a fresh action acknowledgement. Queue scheduling needs its own finite plan acknowledgement, start/deadline, step ceiling and interval. It does not renew consent. Account verification, publication approval, media disclosure, selection and queue consent remain distinct. Reconciliation can request readback of an existing media object; it cannot overwrite or send it again.

Known original Meta jobs in processing/finish/status phases remain available after later project edits. New source-byte operations stay bound to the current saved project and original current approval. Workspace/project/approval changes clear acknowledgements and invalidate late responses. Legacy v1 review history remains readable and execution-disabled; it cannot be promoted by selecting media or a newer configuration.

Strict public DTO checks retain provider job versus post identity, known/unknown status, nullable operation cost evidence, exact object scope/version/hash, and explicit mock versus real outcome labels. Unknown or private fields are rejected; histories use text rendering. Missing configuration retains readonly history and leaves source production usable. Existing YouTube/TikTok controls and purpose-specific analytics fences remain intact.

## Verification scope

Full Studio619 PASS (1879.5661ms), including19 new Meta/media/legacy cases. Current related Native HTTP20 PASS (71.070s). Earlier focused64 and Studio618/619 runs overlap these tests and are not additional unique-case totals. No whole Native/media/renderer/Docker regression is inferred.

`meta-studio-flow-n3` uses actual cookie/CSRF localhost HTTP through the real controllers with an explicit fake DOM, Meta/S3 protocol mocks, signed human Owner fixture, platform eligibility fixture and nonplayable media. Instagram uses25 UI API requests and three manual publication actions. Facebook uses21 UI API requests and one separately acknowledged finite queue, executed by the existing shared worker. Each has one storage write,15 nullable cost records and an observed mock receipt. A separate v1 fixture proves readonly review/state and blocked dispatch without SDK mutation.

Both public backups restore in new processes. The real Studio controllers read identical original publication/dispatch/media/queue history over signed HTTP, with default-off publishing, no private keys and no replay. This is component/local/mock evidence; it does not certify a genuinely produced video, non-developer browser use, real platform permissions, actual audience response or Owner UAT.

Chrome Work was available, but its direct owned localhost navigation reported `net::ERR_BLOCKED_BY_CLIENT`; the visible error page confirmed that restriction. The owned fixture and error tab were stopped/closed without changing another tab or bypassing the restriction. Browser rendering,1366/1920/2560 validation and Owner UAT remain unverified for this component. Evidence is indexed in `docs/north-star/meta-studio-evidence.json`; the first fixture-binding failure and corrected retained runs remain separate records.

## Remaining original scope

Continue platform-specific analytics, multipart storage delivery, secure OAuth/permission/app/version acceptance and every remaining Master Spec Mode A/B/media/intelligence/audio/multi-niche/trend/learning/Hub/production/full A/B/C requirement. Owner listening and Phase10 UAT remain deferred. Capability counts remain5 IMPLEMENTED_REAL /58 PARTIAL /1 NOT_VERIFIED:59 broad groups unclosed. IMPLEMENTATION_COMPLETE, REAL_PROVIDER_ACCEPTANCE_COMPLETE, PRODUCTION_DEPLOYED and VIDEO_FACTORY_NORTH_STAR_READY remain NO. No real provider call, paid operation, external post, main merge, production deployment or manual historical-data deletion occurred.

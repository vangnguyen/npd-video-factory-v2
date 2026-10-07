# Consent-gated publishing queue

A live create request validates current production approval/render/QC, rights, platform policy, the configured provider and scoped destination. It also independently requires all three Owner configuration gates. If every check passes, it persists `awaiting_publish_approval` with no receipt or external action. It never calls the immediate provider `publish()` method. Dry runs retain their existing deterministic provider path; the default official adapters remain contract-only and disabled.

Separate versioned human API endpoints are available:

- `POST /api/v1/projects/{project_id}/publications/{publication_id}/publish-approval`: Owner only, `Idempotency-Key` required. Strict body requires expected request/artifact/target digests and the literal boolean acknowledgment `true`; actor, role and target configuration cannot be supplied in the body.
- `POST .../publish-approval/revoke`: Owner only, exact publication-scoped approval identity. Records local revocation; it never deletes/cancels a remote post.
- `GET .../dispatch`: scoped viewer-readable fixed public projection, excluding private session refs, leases and nonce.

Both the API authorization layer and journal independently enforce Owner authority. The journal uses a fresh registered identity and fresh server destination configuration. Responses use `Cache-Control: no-store`. With no injected strict journal, consent/status endpoints fail closed with `PUBLISH_DISPATCH_NOT_CONFIGURED`. No journal or worker is enabled by the default app factory.

Grant creation performs no upload and leaves the parent queued. A later journal `prepare()` atomically creates the first dispatch and conditionally changes the parent to `publishing`; replay preserves one dispatch and emits one admission event. `publishing` denotes local dispatch state, not a successful remote post. Initialization still requires a separate committed ticket, and unknown initialization never repeats. Revocation prevents subsequent mutation admission. Recording an already-performed outcome remains distinct from permission for another chunk.

Publication/event timestamps normalize SQLite's UTC-naive reloads to UTC on read, preserving exact first-response/idempotent replay equality. No stored timestamps or accepted data are migrated. A malformed provider target is omitted from the blocked public snapshot after validation rather than persisting an unchecked model.

The isolated contract uses actual ASGI HTTP, SQLite and separate process reads. Its ready provider, verified capability policy, account/credentials, human/production/publish approvals, render and QC are explicitly fixtures. It performs zero provider requests, reads no real credentials and does not certify a real account, browser usability, Owner UAT or final North Star bundles.

Configured profile administration, worker scheduling/processing/receipts, OAuth/account verification, per-operation cost/budget admission, atomic edit admission, orphaned receipts, thumbnail support, complete platform adapters and Native publishing UI remain. `live_execution_enabled` stays false without an attached worker. Full Publishing Ready and Mode A/B Ready remain NO.

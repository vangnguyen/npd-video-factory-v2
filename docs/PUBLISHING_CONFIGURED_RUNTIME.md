# Configured YouTube publishing runtime

`YouTubePublishingRuntime` explicitly connects the scoped public profile registry,
separate Owner publish consent, durable work queue, encrypted resumable receipt,
fresh artifact QC and cost journal to the official bounded HTTP client. Constructing
or installing it performs no request, secret read, background task or enablement.
Default application startup remains contract-only and all publishing flags remain
disabled. Credentials and encryption keys are supplied by trusted server callbacks.

Live publication creation selects the workspace profile, requires an explicit
profile when multiple channels exist, and binds the full public configuration
revision and target to review. Configuration readiness is not account verification.
The worker verifies the account, current flags, profile, consent, artifact and budget
before a wire operation. Changed targets or revisions require review.

The provider returns a queued `PublicationSubmission`, separately from a completed
`PublicationReceipt`. Replayed submission reuses the existing work. Work scans are
bounded and scoped; claim races return `not_claimed` without inventing a database
transition. Profile resolution happens inside the owned scheduler step, so invalid
configuration becomes durable review state. Receipt status queries require the
exact stored receipt and workspace/channel target. A receipt alone does not authorize
remote deletion. No automatic production poller is started.

Mock transport execution is persisted on the publication before any wire operation.
Studio labels completed fixture records “Mock publish PASS”; their receipt has
`external_action=false` and no remote URL. An uploaded video still waits for observed
processing and requested visibility before a receipt is completed.

## Verification

The expanded runtime/profile/queue/scheduler/target/API selection passed 86 tests;
the added competing-worker batch test passed separately. Studio passed 123 tests.
The real-media contract uses a preserved synthetic 1080x1920 H.264/AAC file of
4,256,257 bytes, SHA256
`80de36cef34e3945a196e32928ee8d77e6a67100810501acfd38c35d99ebca2d`.
Two actual FFmpeg/FFprobe QC scans, six authenticated ASGI requests, SQLite/AES
persistence and two separate restarted processes complete one mock initialization,
lost final reply reconciliation and processing observation after consent revocation.
Eight provider requests use an explicit MockTransport; eight actual costs remain
null. No actual credentials, paid request or real publication are involved.

Unit identity, approvals, account/OAuth/key and media-QC inputs are fixtures; the
unit media header is intentionally non-playable. The real-media contract separately
replaces it with the physical synthetic source and actual QC. This contract is not
Owner UAT, a final North Star A/B/C bundle or production deployment.

## Remaining work

Persistent Owner configuration and secret custody, explicit production startup and
supervision, cancel/resume administration, Native distribution UI, atomic edit/wire
admission, QC/cache reuse, thumbnails, complete TikTok/Meta adapters, real account
acceptance, billing observation and shared project/provider budget coordination
remain unaccepted. No live schema, accepted media, production process, main branch
or deployment is changed by this increment.

# Native TikTok creator review and unsent drafts

This component extends the existing owned Native workflow. It provides an inert protected TikTok connection, explicit same-grant account and creator reads, immutable choices for an approved final video, signed local routes and Studio controls. It does not yet dispatch a TikTok publication. The existing YouTube publishing worker and canonical timeline remain the production implementation reused by subsequent distribution work.

## Configuration and custody

`--tiktok-publishing-registry` points to a protected registry outside the repository and public data root. Its schema is `native-tiktok-publishing-registry-v1`, with version 1, the bound workspace and unique bindings. Each binding contains the versioned TikTok profile, a credential alias, a protected token file and `creator_reads_enabled: false` by default. The profile contains an exact `PublishingTargetBinding`, `api_client_audited: false`, local `media_location: user_device` and bounded chunk size. Registry bytes and the typed connection are pinned for the process.

The dedicated DPAPI access record uses a distinct prefix and entropy, exact target/alias, aware expiry and exactly `video.publish` plus `user.info.basic`. Saving never overwrites an existing credential. Startup, discovery, history, backup and recovery do not decrypt it. Only explicit reads resolve the original ciphertext; a token with 90 seconds or less remaining is refused. Tokens and private paths are absent from public DTOs, response summaries, cost receipts and backups. There is no automatic refresh or grant selection.

`--enable-tiktok-creator-reads` is off by default and enables only the explicit creator-read component. A current authenticated Owner, CSRF and raw read consent are required. Mock transports require a separate acknowledgement and are rejected as production network injection. Publishing, scheduling and paid operation enablement are independent and remain off.

## Explicit read and draft flow

The Owner prepares a request against the current project revision, connection fingerprint and mock mode, then separately asks to fetch it. A durable claim precedes credential access. Two fixed official requests use the same current grant: stable `open_id` account confirmation followed by creator options. The second request stops if the first names another account or if identity, document, registry, claim, consent window or ciphertext changes. Each response retains its original hash and cost operation. Nickname, privacy options, interaction restrictions and maximum duration are structured evidence. A timeout is unknown and is never automatically replayed.

Studio displays the returned nickname, leaves privacy unselected, starts interactions unchecked and disables provider-restricted options. Commercial disclosure starts off; brand categories and required consents are explicit. Editable title, description, caption and normalized hashtags retain Vietnamese text; the combined TikTok caption is bounded in UTF-16 units. Video review, AI disclosure review and music confirmation are independent. A portrait player reads the existing approved final through the signed Native media route.

Saving a draft binds the creator check/result, exact current approved final job/file/QC, immutable job snapshot/result and final review. It does not mutate the timeline, approve publication, create a queue item or upload media. Historical drafts remain readable after local creator-check cancellation, but current consent is required for any new admission. Their original job and response/cost links are verified rather than trusting a rehashed draft alone.

Routes use `/api/connections/tiktok-creators` and `/api/projects/{id}/tiktok-creators/checks|drafts`; checks have explicit `fetch` and local `cancel` actions. Mutations require Owner permission and CSRF before body parsing. Pages are workspace/project scoped and bounded. Default-off restart recovers claimed checks as `outcome_unknown`, settles pending costs and never accesses a provider.

## Evidence and remaining work

See [retained evidence](north-star/tiktok-creator-evidence.json). Actual Windows DPAPI, SQLite journals, signed HTTP, public backup/restore and fresh-process keyless history have local evidence. Provider responses, audience identity, the final video bytes and human approvals in the retained fixture are explicitly synthetic. Studio DOM tests are not browser usability or Owner acceptance.

Real Direct Post eligibility requires independent confirmation: TikTok's current guidelines limit acceptable app purposes, require creator options and user consent, and distinguish local file transfer from server media transfer. A private utility for an owner's or team's accounts does not obtain eligibility through an Owner checkbox. This application's actual purpose and provider approval remain externally unverified. [TikTok content sharing guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines)

The remaining Native implementation must connect reviewed drafts to platform/rights validation, separate human publish approval, the existing durable publication/dispatch/queue/session journals, official initialization and sequential transfer, polling and receipt-bound analytics. Public publishing additionally requires actual app audit approval and credentials. Those behaviors, real-provider acceptance, full Mode A/B/C and production deployment remain incomplete; this document does not narrow the North Star.

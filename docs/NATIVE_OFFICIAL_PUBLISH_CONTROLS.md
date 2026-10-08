# Native signed publishing controls

The protected YouTube publishing journal, session vault and bounded worker now have a signed local HTTP adapter and an optional Studio panel. Automatic publishing remains disabled. Loading Studio, reading configuration or history, approving a review, and restarting the worker do not send an upload. A separately confirmed POST executes one bounded upload operation or processing read.

Implementation is partial against the original North Star. Real OAuth/account/platform/legal/provider/Owner acceptance, scheduling, the remaining platforms, thumbnails and authentic publication-to-analytics integration are outstanding. This increment does not certify Mode A, Mode B, Phase 10 Owner UAT or production deployment.

## Configuration and authority

`LocalServer` and the Native CLI accept:

- `--official-publish-registry`: the existing versioned publishing registry, outside source and state.
- `--official-publish-session-directory`: protected session storage, also outside source and state.
- `--enable-official-publishing`: explicit operator enablement, false by default. It requires the protected registry, session directory and a configured human authentication registry. Real use still requires separate Owner authorization.

The registry supplies the complete frozen target, profile version, category/disclosures, credential alias/mount and three independent gates. The operator flag gates those registry settings. Default startup does not decrypt tokens, initialize uploads, poll a platform or replace missing official credentials with mock results. Production clients come only from the protected registry. Direct factory injection is restricted to explicit mock transports with human authentication and is used by owned tests.

The read-only account registry remains separate. A current successful account check must match the exact target, mock/official mode, project revision and document. It is evidence for a review, not publish authority. A completed dry run similarly supplies frozen metadata and validation evidence without granting authority. The final render, full QC, exact human final review, rights gate and independently verified live platform capability are checked again by the existing journal. A protected token file alone cannot bypass any of these checks.

The accepted Native runtime has not been enabled or reconfigured. No production deployment, real publication, paid call or Owner UAT acceptance occurred.

## HTTP contract

All these routes retain the existing loopback-host, same-origin, signed human session, workspace and CSRF boundary. Unauthorized mutations fail before body parsing. Owner/manage permission is required for all mutations and connection configuration. Project history/detail/state require read permission. Responses use `Cache-Control: no-store` and return no bearer token, private mount path or resumable URI.

| Route | Behavior |
| --- | --- |
| `GET /api/connections/official-publishing` | Public frozen profiles and configured/not-configured vault status; no decryption or wire request. |
| `GET /api/projects/{project}/official-publications?limit=25&cursor=…` | Scope-bound history; 1–100 rows per page, opaque workspace/project cursor, checksum/receipt validation. |
| `GET /api/projects/{project}/official-publications/{publication}` | Immutable review and qualified terminal receipt, when present. |
| `GET /api/projects/{project}/official-publications/{publication}/state` | Current dispatch version, phase, acknowledged offset, opaque session reference, processing acceptance and durable backoff. |
| `POST /api/projects/{project}/official-publications` | Typed current-source review using explicit dry-run ID/hash, account-check ID, profile/configuration hash and idempotency key. No grant or send. |
| `POST …/{publication}/approve` | Separate explicit human Owner consent, expected snapshot hash and bounded lifetime. No send. |
| `POST …/{publication}/renew` | Explicit idempotent consent renewal with snapshot and dispatch-version binding; retains the known session and offset. No send. |
| `POST …/{publication}/cancel` | Revoke an unsent review/grant locally. An attempted/uncertain upload cannot be erased or restarted through cancellation. |
| `POST …/{publication}/step` | Expected snapshot and strict dispatch version; one existing worker initialization, chunk or reconciliation operation. |
| `POST …/{publication}/poll` | Expected snapshot/version; current consent and authenticated account are checked before observing uploaded-video processing/privacy. |

Client bodies cannot supply tokens, private session URIs, endpoints, provider mode or publish enablement. A stale dispatch version is rejected before another request. Interrupted initialization retains the one-init guard. A lost chunk response requires reconciliation of the existing session before more bytes. Consent renewal does not clear provider backoff, create another session, or authorize an uncertain initialization to restart. Processing confirmation remains separate from completion of the byte upload.

`Runner.start()` invokes existing local recovery once before its thread starts. It marks unfinished upload intents/cost operations uncertain without decrypting or sending. `Runner.run_one()` does not automatically select or send official publications. Manual routes are deliberately bounded while durable scheduling/queue execution remains outstanding.

## Studio behavior

`native_official_publication_review` is advertised only when human authentication is configured. The optional module is absent from legacy startup. The existing shot-centric shell moves the original account and official publishing cards into the video review area without duplicating nodes or changing their handlers. Existing dry-run controls remain separate.

Studio explicitly reads configuration, current dry-run/account evidence, paginated history and dispatch state. Selection is filtered to the current revision and exact target/mode. Review creation does not approve or send. Approval/renewal requires a separate checkbox. Every upload or processing step requires a fresh checkbox and a freshly read dispatch state. Unknown upload outcomes clear the displayed dispatch; the next action requires a state read. Unknown create/renewal outcomes retain the exact idempotency key for an explicit retry.

Saved/idle/unarchived project, Owner permission, workspace/revision binding and current state guard mutations. Working state blocks other Studio actions; late results cannot cross project, workspace, revision, dirty/active state or role changes. UI source/receipt validation preserves mock qualification. Provider text enters text nodes, not HTML. There is no OAuth secret input, provider browser automation, automatic polling or automatic publish retry.

## Verification and evidence

The current full Native and Studio regression results are indexed in `docs/north-star/native-official-publish-controls-evidence.json`. Seven new signed HTTP cases and ten new DOM cases cover roles/CSRF before body, current review/source/version fences, pagination/foreign scope/corrupt evidence, unknown initialization, exact renewal/create replay, local cancellation, stale responses, default disabled controls, nullable backoff and mock receipt qualification.

The retained rehearsal is `scripts/north_star_native_official_publish_controls.py`. Current evidence is `recovery/20261007/native-official-publish-controls-flow-n2` outside the repository. It records 30 actual signed loopback HTTP requests and 12 explicit mock wire requests: one initialization, three exact data chunks, one reconciliation of a lost first-chunk response, consent expiry/explicit renewal and separate processing confirmation. Actual Windows DPAPI loads comprise 30 scoped publishing-token decryptions and four separately scoped session decryptions. Configuration/status reads do not decrypt or send. The served Studio asset matches its source bytes.

The fixture is explicitly nonplayable. Full QC, rights, human identity, live platform verification, account evidence, OAuth and provider results are synthetic. These results are not a real media flow, legal acceptance, real OAuth/provider acceptance, browser usability test or Owner listening/UAT. Earlier n1 evidence is retained as a failed setup at its prior source point; n2 includes the required registry version.

The rehearsal archive excludes tokens, protected registry/private paths and session URIs. All twelve publication/cost journals, historical grants/renewals, qualified receipt, original fixture project/jobs and physical artifact hashes replay exactly after archive restore and a fresh-process reopen with no credential, factory, vault or dispatcher configured. Unknown costs remain null. No accepted artifact is replaced. Source/export/log/archive hashes and fresh accepted/live-source checks are retained with this increment's preservation receipt.

The full original Master Spec, current capability matrix and gap closure plan remain authoritative. Secure OAuth acquisition/refresh/rotation, durable queue/scheduling, other official platforms, thumbnails, real receipts-to-analytics, semantic/media/audio/cohort/learning/Hub isolation/hardening and final A/B/C acceptance work continue separately.

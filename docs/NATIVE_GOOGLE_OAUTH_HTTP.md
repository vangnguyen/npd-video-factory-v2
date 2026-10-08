# Signed Native Google OAuth operations

The Native server exposes explicit Owner actions over the preserved OAuth journal. Both operator enablement and a protected registry's `token_exchange_enabled` flag are required for a real network client. Registry loading validates public client slots, raw booleans, exact workspace, unique target/purpose combinations, bounded size and duplicate JSON keys. It performs no private decryption. Public registries and private custody must be outside Source and state; file/path/checksum changes fence the live runtime.

The CLI accepts `--google-oauth-registry`, `--google-oauth-directory` and `--enable-google-oauth`. Enabling exchanges without human authentication, protected registry/private directory, or with a live injected client fails before opening a server socket. Direct client/slot injection is restricted to explicit protocol mocks. Missing operator or registry enablement keeps exchanges disabled. The default server creates no OAuth journals or private directory unless configured or restoring existing OAuth history. Existing history can reopen with empty slots, no registry and disabled credentials. Native Session fields remain unchanged.

Owner discovery is `GET /api/connections/google-oauth`. Workspace/project histories are `GET /api/projects/{project}/google-oauth/authorizations` and `/operations`, with bounded limit/cursor parameters and read permission. Detail IDs remain scoped to their group and project. These reads verify original snapshots, source linkage and cost receipts without resolving credentials or granting authority.

Owner actions require the signed human session and its CSRF token before callback body parsing:

- `POST .../authorizations` starts a bounded intent; its redirect must be the current server's exact IPv4 loopback callback URI.
- `POST .../authorizations/{id}/authorization-url` returns the state-bearing Google authorization URL in a separate authenticated, no-store response. It is never retained in journals or rehearsal exports.
- `POST .../authorizations/{id}/exchange` accepts the private callback query in a bounded body plus the expected original snapshot hash. Query fields in history/discovery GET requests are rejected.
- `POST .../authorizations/{id}/cancel` cancels the exact pending intent locally.
- `POST .../refresh` requires a new explicit credential-operation consent, exact successful source result and original grant generation. Exact request-key replay reads history and performs no new exchange.

The Runner only recovers uncertain OAuth claims at startup. It has no OAuth polling, credential decryption, token exchange or background refresh step. An OAuth result does not select a credential, verify a channel, enable publishing/analytics, renew a production consent or mutate project media, approval or budgets. The existing account, read, publication, rights and finite-plan gates remain separate.

These signed API actions are implemented and tested with synthetic private values. Automatic external-browser callback reception, Studio sign-in/review controls, secure approved real client installation, account confirmation and explicit credential resolver selection remain unfinished. No anonymous callback exchange or browser automation is installed. Consequently the API rehearsal does not certify a completed human browser sign-in flow or genuine provider acceptance.

The retained rehearsal covers 15 actual signed HTTP requests, three fixed-endpoint mock token requests, two immutable grant generations, an unknown timeout, denial without cost/wire, explicit cancellation, nullable cost receipts, unchanged session/project and no automatic worker requests. Eight actual synthetic DPAPI files have protected current-user/LocalSystem DACLs. The public-only backup excludes tokens, callback code, PKCE state/verifier, client secrets and private ciphertext. All 76 workflow fixture journals, project, four authorization/four operation histories and original private receipts recover into a fresh root; history remains readable without the registry or private mount. Earlier OAuth and finite-refresh evidence also replays unchanged.

The shared protocol follows [Google's native-app OAuth documentation](https://developers.google.com/identity/protocols/oauth2/native-app) and [OAuth policies](https://developers.google.com/identity/protocols/oauth2/policies). Real authorization will require a manually operated external browser and approved credentials; publishing and production deployment still require their separate Owner approvals.

# Native Google OAuth loopback callback

`GET /oauth/google/callback` now completes an existing, bounded authorization prepared by the signed current Owner. This is a narrow native desktop redirect. It grants no Studio login, account verification, credential selection, read/background consent or publishing approval.

New private state consists of the authorization identity and the original 384-bit random suffix. The identity only locates the workspace-bound original record. The exact encrypted state and PKCE verifier still validate the response; neither appears in public journals or exports. Original intents without the new prefix keep the signed manual callback POST path and unchanged history.

Before private reads or dispatch, the kernel verifies operator and protected registry configuration, the original current Owner identity revision and expiry, project revision/document/editability, exact current-port redirect and the original finite consent window. The existing exchange checks private client/authorization/source/cost bindings again, atomically consumes the authorization and records a unique operation before contacting the token endpoint. Concurrent callbacks cannot dispatch a consumed code twice. Unknown outcomes and restart never replay automatically.

The callback permits a top-level external navigation without the Studio SameSite cookie. Host must be exactly `127.0.0.1:<current-port>` once. Supplied fetch mode/destination must describe a document navigation; supplied Origin must be the current loopback origin or Google's fixed accounts origin. Duplicate headers, GET bodies, transfer encoding, malformed/duplicate/broader fields and oversized queries refuse. Other routes retain their original session, same-origin and CSRF boundaries.

Responses are fixed HTML with no query, project, authorization, Owner, account, token or provider exception reflection. No-store, no-referrer, content-type enforcement and the existing CSP apply. No session cookie or redirect is issued. Synthetic protocol success is labelled explicitly. Denial consumes the intent without a token call/cost; uncertainty requires reviewing the original operation.

This implements the native callback handler only. No genuine OAuth client or browser authorization has been exercised. Studio consent/history controls, account confirmation, explicit credential resolver selection and production secret-service integration remain open. An obtained grant does not change existing account/publish/read/finite-refresh grants. Listening and Owner UAT remain deferred.

The desktop loopback and PKCE approach follows [Google's installed-app documentation](https://developers.google.com/identity/protocols/oauth2/native-app) and [desktop loopback guidance](https://developers.google.com/identity/protocols/oauth2/resources/loopback-migration). The human must authorize in an external browser; no embedded browser or browser automation is used.

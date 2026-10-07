# TikTok official publishing protocol

`tiktok_upload.py` implements inert official request builders and strict observation
parsers. Device media uses FILE_UPLOAD: a bounded chunk plan rounds the count down,
merges trailing bytes into the last chunk and sends sequential ranges. Internal
support is capped at 512 MiB; request bodies remain at most 16 MiB. Only documented
upload hosts/paths and bounded signed query fields are accepted. Upload hosts never
receive OAuth authorization. Expired sessions or uncertain initialization require
review; these helpers never send, retry or invent a vendor idempotency header.
[Media transfer contract](https://developers.tiktok.com/docs/en/content-posting-api-media-transfer-guide)

Post choices have no privacy/interaction defaults. The latest creator permissions,
duration limit, explicit commercial/AI disclosures and UTF-16 caption limit are
validated. Generic metadata cannot silently change visibility. Music-use and branded
policy confirmations are local admission fields and are excluded from vendor JSON.
Cover frames use timestamps; generic uploaded thumbnails and scheduling are rejected
until their supported orchestration stages exist.
[Direct Post contract](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post),
[Creator information](https://developers.tiktok.com/docs/en/content-posting-api-reference-query-creator-info)

Server media instead uses PULL_FROM_URL against a trusted, previously verified
ownership prefix. Exact HTTPS origin/path boundaries exclude traversal, encoded
separators, credentials, IP addresses and foreign prefixes. This helper does not
verify dashboard ownership, lifetime or redirects by accepting a string; production
configuration must establish those separately. No local URL is fetched.

Observed upload progress may be null. Private completion may have no public post ID;
the parser preserves that absence, rejects impossible counts/IDs/states and never
constructs a public URL. Raw provider errors are replaced by fixed codes.
[Status contract](https://developers.tiktok.com/docs/en/content-posting-api-reference-get-video-status)

`TikTokOAuthCredential` is an immutable in-memory credential, with hidden token,
exact reviewed workspace/profile/account/credential revision, aware expiry and
dedicated `video.publish` plus `user.info.basic` scopes. Tokens must outlive the
ninety-second wire window. `user.info` requests only `open_id`, whose exact match
establishes the destination; username/nickname is not substituted for this stable
application-specific identity. No OAuth acquisition, refresh or secret persistence
is implemented here.
[User information contract](https://developers.tiktok.com/docs/en/tiktok-api-v2-get-user-info)

## Provider acceptance constraint

TikTok currently excludes applications limited to private/internal team upload
utilities. It requires creator-facing controls, preview and explicit posting/music
consent; unaudited clients are limited to SELF_ONLY and private accounts. A suitable
authorized product and provider review are external acceptance requirements for the
intended Video Factory integration. Configuration booleans or fixture credentials
do not establish compliance or account audit. Safe implementation continues, but
TikTok real-provider acceptance remains BLOCKED_EXTERNAL.
[Current content sharing guidance](https://developers.tiktok.com/docs/en/content-sharing-guidelines)

## Verification and remaining work

147 selected credential/protocol tests pass: 81 new TikTok cases and the existing
YouTube/HTTP checks. A six-request MockTransport contract transfers the preserved
4,256,257-byte synthetic portrait source exactly, performs actual FFprobe inspection,
uses one initialization and observes processing then private completion with no
public ID. It exports five secret-free JSON evidence files. No real provider request,
paid operation or real credential is involved; actual costs remain null, and this
protocol-only contract creates no billing records. It is not a full QC run, durable
publishing runtime, Owner UAT or final A/B/C acceptance.

Durable TikTok dispatch/session custody, current consent/creator choices binding,
cost admission, supervised scheduling, verified-pull custody/lifetime, Studio UI,
provider review, credential lifecycle and real acceptance remain partial. Existing
YouTube runtime and disabled defaults are retained. There is no live migration,
publishing, deletion or production deployment.

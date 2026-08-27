# Publishing — V2-09

V2-09 adds a durable publishing validation and receipt layer. It does **not** activate live
publishing. The default and accepted mode is `dry_run`; the system validates the exact approved
final render, rights evidence, platform profile and provider state, then records a mock receipt
without contacting a social platform.

## Supported platform contracts

- YouTube via the official YouTube API contract;
- TikTok via the official TikTok Content Posting API contract;
- Instagram Reels via the official Instagram Graph API contract;
- Facebook via the official Facebook Graph API contract.

The official adapters are contract-only in V2-09. They contain no vendor SDK call, browser
automation, cookie reuse or protection bypass. Platform limits live in
`packages/contracts/publishing-capabilities.json`. The checked-in profiles are conservative,
versioned internal validation profiles and must not be represented as owner-verified live limits.

## Request and durable receipt

`POST /api/v1/projects/{project_id}/publish` requires an `Idempotency-Key` header and:

- the target platform;
- the exact final render ID;
- `mode=dry_run` for the accepted V2-09 path;
- title, description, caption, hashtags, thumbnail reference, privacy and optional scheduled time;
- a non-secret actor reference.

The service reserves the request in PostgreSQL before provider execution. The idempotency key is
stored only as a SHA-256 hash, while a canonical request fingerprint prevents the same key from
being reused with another payload. An exact replay returns the existing publication and receipt;
it never creates a second post or second provider operation.

The dry-run receipt records the provider key, platform, request fingerprint, creation time and the
literal facts `mock=true`, `external_action=false`, `duplicate_post_created=false`. It contains no
OAuth token, secret reference value, remote ID or remote URL.

## Required validation

Every dry-run validates:

1. the production package is current;
2. the supplied render is the latest `ready` final render and passed full QC;
3. the render is bound to the exact current owner-approved review/timeline/subtitle/audio tuple;
4. all active source, music and thumbnail assets belong to the project;
5. rights are explicit and production eligible; unknown or incomplete licensed rights fail closed;
6. duration, profile, dimensions, file size, codecs and metadata fit the versioned platform profile;
7. the selected provider supports the requested mode.

A failed validation is also durable. The API returns HTTP 409 with a stable error code and a
publication ID whose history proves `external_action=false`.

## Live publishing remains locked

All three independent runtime gates default to false:

```text
PUBLISH_ENABLED=false
PUBLISH_EXTERNAL_EXECUTION_ENABLED=false
PUBLISH_OWNER_GATE_ENABLED=false
```

Even if those values were changed together, V2-09 official adapters still report
`supports_live_publish=false` and refuse execution. A later owner-approved increment must add API
authentication/RBAC, workspace authorization, reviewed current platform limits, an accepted
official adapter, an external encrypted secret reference, monitoring, retry/cancel semantics and
production acceptance before any live path can exist.

Credential configuration is reference-only:

```text
PUBLISHING_CREDENTIAL_STORE=external
YOUTUBE_PUBLISHING_CREDENTIAL_REF=
TIKTOK_PUBLISHING_CREDENTIAL_REF=
INSTAGRAM_PUBLISHING_CREDENTIAL_REF=
FACEBOOK_PUBLISHING_CREDENTIAL_REF=
```

Only `secret://`, `vault://` or `external://` references are accepted. Raw tokens fail startup
validation. No credential or reference value is persisted in publication, event, project, job,
asset, cost or receipt records, and none is returned by the API.

## Studio behavior

The Publishing Panel reads the latest final render, platform profiles and durable history. It can
create only a dry-run receipt. It shows each approval, rights, platform and provider gate and has no
live-publish control. Reloading the Studio reads the same PostgreSQL-backed receipt rather than
manufacturing browser-local state.

## API reads

- `GET /api/v1/publishing-platforms`
- `GET /api/v1/projects/{project_id}/publications`
- `GET /api/v1/projects/{project_id}/publications/{publication_id}`
- `GET /api/v1/projects/{project_id}/publication-history`

## Intentional limits

- no live platform credentials;
- no external network request;
- no upload, scheduling, deletion or cancellation against a platform;
- no platform-side analytics polling in V2-09; the separate V2-10 fixture learning loop consumes
  only successful/mock receipt evidence and cannot change publishing state;
- no public API exposure, authentication/RBAC or AgentHub bridge (V2-11);
- no production deployment from this PR.

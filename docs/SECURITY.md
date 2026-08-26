# Security and safety — V2-04

## Defaults

- Publishing is absent and `PUBLISH_ENABLED=true` fails startup validation.
- Human approval is mandatory and `HUMAN_APPROVAL_REQUIRED=false` fails validation.
- API/renderer bind to localhost; PostgreSQL, Redis and MinIO are internal-only.
- Normal CI uses deterministic providers and no paid network call.
- No AgentHub, CRM, Ads, messaging or CMS credentials belong in this repository.
- Live trend providers are `not_configured`; the enabled dev/CI fixture is synthetic and startup
  rejects it in production.
- Trend references are metadata-only; no crawler, protection bypass, creator-media download or
  transcript-copy path exists.
- Auto Edit fixtures are synthetic and rejected at production startup. Live transcription stays
  `not_configured` until an owner-approved credential/adapter exists.

## Data and artifact controls

- Strict Pydantic/Zod/JSON Schema contracts reject unknown fields.
- IDs, filenames and object-key segments are constrained; path traversal is rejected.
- Artifact download requires a recorded name and verifies SHA-256 after object recovery.
- Idempotency keys are hashed before PostgreSQL persistence.
- Provider registry stores only a config reference; credentials are not returned by APIs.
- Runtime data, media, E2E artifacts and `.env` are git-ignored.
- Uploads use bounded part/file sizes, safe server-side names, SHA-256, magic-byte/MIME agreement,
  FFprobe validation and project-scoped object keys. Client extensions are never trusted.
- Source objects are immutable. Silence/highlight output is a reversible decision record only.

## Known security gate

V2-04 does not yet implement API authentication, RBAC or workspace membership. Localhost
binding is the only access boundary in this increment. Public routing and production
deployment are prohibited until those controls, rate limits and audit actor identity are
implemented and accepted.

## Credential contract

Only variable names/config references appear in source: `DATABASE_URL`, `OBJECT_STORAGE_*`,
optional `OPENAI_API_KEY`, `TRANSCRIPTION_PROVIDER` and future provider contract names. Real values must come from an
external secret manager. They must never be
stored in project snapshots, jobs, assets, provider metadata, costs, logs or Git.

AgentHub and V2 must not share database, Redis, packages or process memory. Future bridge
traffic requires authentication, replay protection, signed requests and versioned contracts.
